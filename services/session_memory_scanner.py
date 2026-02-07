"""
Session Memory Scheduled Scan Service

Features:
1. Periodically scan user sessions
2. Check session last interaction time
3. Automatically generate or update L2 session memories
4. Ensure idempotency constraints
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from timem.utils.logging import get_logger
from timem.workflows.memory_generation import MemoryGenerationWorkflow
from timem.core.catchup_detector import CatchUpDetector, BackfillTask
from storage.memory_storage_manager import get_memory_storage_manager_async
from timem.utils.time_parser import TimeParser
from timem.utils.config_manager import get_config
from timem.core.global_connection_pool import get_global_pool_manager
from sqlalchemy import text

logger = get_logger(__name__)


@dataclass
class SessionScanResult:
    """Session scan result"""
    scanned_sessions: int
    eligible_sessions: int
    generated_memories: int
    updated_memories: int
    failed_sessions: int
    errors: List[str]


@dataclass
class PendingSession:
    """Pending session"""
    session_id: str
    user_id: str
    expert_id: str
    last_interaction_time: datetime
    has_existing_l2: bool
    should_update: bool


class SessionMemoryScanner:
    """
    Session Memory Scheduled Scanner
    
    Core Features:
    1. Scan all active user sessions
    2. Check if session last interaction time exceeds configured timeout
    3. Automatically generate or update L2 memories for qualifying sessions
    4. Ensure idempotency constraints: at most one L2 memory per session
    """
    
    def __init__(self):
        self.config = self._load_config()
        self.enabled = self.config.get("enabled", True)
        self.interaction_timeout_minutes = self.config.get("interaction_timeout_minutes", 10)
        self.batch_size = self.config.get("batch_size", 20)
        self.max_concurrent_tasks = self.config.get("max_concurrent_tasks", 5)
        self.exclude_recent_minutes = self.config.get("exclude_recent_minutes", 1)
        
        # Initialize dependency services (lazy initialization)
        self.memory_workflow: Optional[MemoryGenerationWorkflow] = None
        self.catchup_detector: Optional[CatchUpDetector] = None
        self.storage_manager = None
        self.pool_manager = None
        
        # Concurrency control
        self._semaphore = asyncio.Semaphore(self.max_concurrent_tasks)
        
        logger.info(
            f"SessionMemoryScanner initialized: enabled={self.enabled}, "
            f"timeout={self.interaction_timeout_minutes} minutes, "
            f"batch_size={self.batch_size}"
        )
    
    def _load_config(self) -> Dict[str, Any]:
        """Load settings from configuration file"""
        try:
            config = get_config()
            return config.get("memory", {}).get("session_memory_scan", {})
        except Exception as e:
            logger.warning(f"Failed to load session scan configuration, using default: {e}")
            return {}
    
    async def _ensure_dependencies(self):
        """Ensure dependency services are initialized"""
        if not self.storage_manager:
            self.storage_manager = await get_memory_storage_manager_async()
        
        if not self.memory_workflow:
            self.memory_workflow = MemoryGenerationWorkflow()
        
        if not self.catchup_detector:
            self.catchup_detector = CatchUpDetector()
        
        if not self.pool_manager:
            self.pool_manager = await get_global_pool_manager()
    
    async def scan_and_process(self) -> SessionScanResult:
        """
        Scan and process session memories
        
        Returns:
            SessionScanResult: Scan processing result
        """
        if not self.enabled:
            logger.debug("Session memory scan is disabled, skipping processing")
            return SessionScanResult(0, 0, 0, 0, 0, [])
        
        try:
            logger.info("Starting session memory scheduled scan...")
            
            # Ensure dependency services
            await self._ensure_dependencies()
            
            # Get all pending sessions
            pending_sessions = await self._get_pending_sessions()
            
            if not pending_sessions:
                logger.info("No sessions found that need processing")
                return SessionScanResult(0, 0, 0, 0, 0, [])
            
            logger.info(f"Found {len(pending_sessions)} pending sessions")
            
            # Process sessions in batches
            result = SessionScanResult(
                scanned_sessions=len(pending_sessions),
                eligible_sessions=len(pending_sessions),
                generated_memories=0,
                updated_memories=0,
                failed_sessions=0,
                errors=[]
            )
            
            # Process sessions in batches
            for i in range(0, len(pending_sessions), self.batch_size):
                batch = pending_sessions[i:i + self.batch_size]
                batch_results = await self._process_session_batch(batch)
                
                # Aggregate results
                for batch_result in batch_results:
                    if batch_result["success"]:
                        if batch_result["action"] == "created":
                            result.generated_memories += 1
                        elif batch_result["action"] == "updated":
                            result.updated_memories += 1
                    else:
                        result.failed_sessions += 1
                        if batch_result.get("error"):
                            result.errors.append(batch_result["error"])
            
            logger.info(
                f"Session memory scan completed: scanned={result.scanned_sessions}, "
                f"created={result.generated_memories}, updated={result.updated_memories}, "
                f"failed={result.failed_sessions}"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Session memory scan exception: {e}", exc_info=True)
            return SessionScanResult(0, 0, 0, 0, 0, [str(e)])
    
    async def _get_pending_sessions(self) -> List[PendingSession]:
        """
        Get all pending sessions
        
        Returns:
            List[PendingSession]: List of pending sessions
        """
        try:
            # Query user group status directly from database
            # cutoff_time: Timeout time point (e.g., 10 minutes ago), sessions before this time need processing
            # exclude_recent_time: Exclude recent time point (e.g., 1 minute ago), avoid processing ongoing sessions
            cutoff_time = datetime.now() - timedelta(minutes=self.interaction_timeout_minutes)
            exclude_recent_time = datetime.now() - timedelta(minutes=self.exclude_recent_minutes)
            
            # Query conditions:
            # 1. Last interaction time before cutoff_time (already timed out)
            # 2. Last interaction time before exclude_recent_time (not just interacted)
            # Note: Since cutoff_time < exclude_recent_time, condition 2 is actually redundant, simplify to use condition 1 only
            query = text("""
                SELECT 
                    user_id, 
                    expert_id, 
                    last_session_id, 
                    last_interaction_time
                FROM user_expert_states
                WHERE last_interaction_time IS NOT NULL
                  AND last_interaction_time <= :cutoff_time
                  AND last_session_id IS NOT NULL
                ORDER BY last_interaction_time ASC
            """)
            
            async with self.pool_manager.get_managed_session(context="session_memory_scan") as session:
                result = await session.execute(
                    query, 
                    {
                        "cutoff_time": cutoff_time
                    }
                )
                rows = result.fetchall()
            
            logger.info(f"Scanned {len(rows)} sessions that may need processing (last interaction before {self.interaction_timeout_minutes} minutes ago)")
            
            pending_sessions = []
            
            for row in rows:
                user_id = row[0]
                expert_id = row[1]
                session_id = row[2]
                last_interaction_time = row[3]
                
                # Check if L2 memory already exists
                has_existing_l2 = await self._check_existing_l2_memory(
                    user_id, 
                    expert_id, 
                    session_id
                )
                
                # Decide whether to process this session
                should_process = False
                should_update = False
                
                if not has_existing_l2:
                    # No L2 memory, need to generate
                    should_process = True
                    should_update = False
                else:
                    # L2 memory exists, check if update is needed
                    should_update_needed = await self._should_update_l2_memory(
                        user_id,
                        expert_id,
                        session_id,
                        last_interaction_time
                    )
                    if should_update_needed:
                        should_process = True
                        should_update = True
                
                if should_process:
                    pending_sessions.append(PendingSession(
                        session_id=session_id,
                        user_id=user_id,
                        expert_id=expert_id,
                        last_interaction_time=last_interaction_time,
                        has_existing_l2=has_existing_l2,
                        should_update=should_update
                    ))
            
            return pending_sessions
            
        except Exception as e:
            logger.error(f"Failed to get pending sessions: {e}", exc_info=True)
            return []
    
    async def _check_existing_l2_memory(
        self, 
        user_id: str, 
        expert_id: str, 
        session_id: Optional[str]
    ) -> bool:
        """
        Check if specified session already has L2 memory
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            session_id: Session ID
            
        Returns:
            bool: Whether L2 memory already exists
        """
        if not session_id:
            return False
        
        try:
            query = {
                "user_id": user_id,
                "expert_id": expert_id,
                "layer": "L2",
                "session_id": session_id
            }
            
            memories = await self.storage_manager.search_memories(query, {"limit": 1})
            return len(memories) > 0
            
        except Exception as e:
            logger.error(f"Failed to check L2 memory existence: {e}", exc_info=True)
            return False
    
    async def _should_update_l2_memory(
        self,
        user_id: str,
        expert_id: str,
        session_id: str,
        last_interaction_time: datetime
    ) -> bool:
        """
        Check if L2 memory needs to be updated
        
        When a session has new interactions, need to regenerate L2 memory to include latest content
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            session_id: Session ID
            last_interaction_time: Last interaction time
            
        Returns:
            bool: Whether update is needed
        """
        try:
            # Get existing L2 memory
            query = {
                "user_id": user_id,
                "expert_id": expert_id,
                "layer": "L2",
                "session_id": session_id
            }
            
            memories = await self.storage_manager.search_memories(query, {"limit": 1})
            if not memories:
                return False
            
            memory = memories[0]
            memory_created_at = memory.get("created_at")
            
            if not memory_created_at:
                return True  # Cannot determine creation time, assume update is needed
            
            # Parse memory creation time
            if isinstance(memory_created_at, str):
                memory_created_at = TimeParser.parse_time(memory_created_at)
            
            # If last interaction time is later than memory creation time, there are new interactions, need update
            return last_interaction_time > memory_created_at
            
        except Exception as e:
            logger.error(f"Failed to check L2 memory update requirement: {e}", exc_info=True)
            return True  # Assume update is needed on error
    
    async def _process_session_batch(self, sessions: List[PendingSession]) -> List[Dict[str, Any]]:
        """
        Batch process sessions
        
        Args:
            sessions: List of sessions
            
        Returns:
            List[Dict[str, Any]]: List of processing results
        """
        tasks = []
        for session in sessions:
            task = asyncio.create_task(self._process_single_session(session))
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        formatted_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                formatted_results.append({
                    "success": False,
                    "session_id": sessions[i].session_id,
                    "error": str(result)
                })
            else:
                formatted_results.append(result)
        
        return formatted_results
    
    async def _process_single_session(self, session: PendingSession) -> Dict[str, Any]:
        """
        Process single session L2 memory generation or update
        
        Args:
            session: Pending session
            
        Returns:
            Dict[str, Any]: Processing result
        """
        async with self._semaphore:
            try:
                logger.debug(
                    f" Processing session memory: session_id={session.session_id}, "
                    f"user_id={session.user_id}, expert_id={session.expert_id}, "
                    f"update={session.should_update}"
                )
                
                # Create BackfillTask
                task = BackfillTask(
                    user_id=session.user_id,
                    expert_id=session.expert_id,
                    layer="L2",
                    session_id=session.session_id,
                    timestamp=datetime.now(),
                    force_update=session.has_existing_l2  # Mark as update if already exists
                )
                
                # Execute memory generation/update
                result = await self.memory_workflow.run_single_memory(task)
                
                if result.get("success"):
                    action = "updated" if session.should_update else "created"
                    
                    # Get memory_id (may be direct field or in memory object)
                    memory_id = result.get("memory_id")
                    if not memory_id:
                        memory_obj = result.get("memory")
                        if memory_obj:
                            # memory may be object or dictionary
                            memory_id = getattr(memory_obj, 'id', None) or (memory_obj.get('id') if isinstance(memory_obj, dict) else None)
                    
                    logger.info(
                        f"✅ Session memory {action} succeeded: session_id={session.session_id}, "
                        f"memory_id={memory_id or 'unknown'}"
                    )
                    
                    return {
                        "success": True,
                        "session_id": session.session_id,
                        "action": action,
                        "memory_id": memory_id
                    }
                else:
                    error_msg = result.get("error", "Unknown error")
                    logger.error(f"❌ Session memory processing failed: session_id={session.session_id}, error={error_msg}")
                    
                    return {
                        "success": False,
                        "session_id": session.session_id,
                        "error": error_msg
                    }
                    
            except Exception as e:
                logger.error(f"❌ Session memory processing exception: session_id={session.session_id}, error={e}", exc_info=True)
                return {
                    "success": False,
                    "session_id": session.session_id,
                    "error": str(e)
                }


# Global singleton
_scanner_service: Optional[SessionMemoryScanner] = None
_scanner_lock = asyncio.Lock()


async def get_session_memory_scanner() -> SessionMemoryScanner:
    """Get session memory scanner singleton"""
    global _scanner_service
    
    if _scanner_service is None:
        async with _scanner_lock:
            if _scanner_service is None:
                _scanner_service = SessionMemoryScanner()
    
    return _scanner_service
