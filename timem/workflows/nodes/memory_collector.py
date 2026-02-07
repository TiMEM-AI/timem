"""
TiMem MemoryCollector Node

Responsible for collecting child memories and historical memories needed for memory generation
Refactored from HistoryCollector, enhanced session mode and time window mode support
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
from dataclasses import dataclass
import logging

from timem.utils.logging import get_logger
from timem.utils.time_utils import parse_time
from storage.memory_storage_manager import MemoryStorageManager

logger = get_logger(__name__)


@dataclass
class CollectedMemories:
    """Collected memory data structure"""
    child_memories: List[Any]
    historical_memories: List[Any]


class MemoryCollector:
    """
    Memory collector (refactored version)
    
    Responsibilities:
    1. Collect child memories and historical memories from database
    2. Support session mode (L1/L2) and time window mode (L3/L4/L5)
    3. Data conversion and cleaning
    
    Does not include:
    - Decision on whether collection is needed (decided by caller)
    - Post-collection processing logic (only returns data)
    """
    
    def __init__(self, storage_manager: Optional[MemoryStorageManager] = None):
        """
        Initialize memory collector
        
        Args:
            storage_manager: Storage manager (dependency injection)
        """
        self.storage_manager = storage_manager
        logger.info("MemoryCollector initialized")
    
    async def _ensure_storage_manager(self):
        """Ensure storage manager is initialized"""
        if not self.storage_manager:
            from storage.memory_storage_manager import get_memory_storage_manager_async
            self.storage_manager = await get_memory_storage_manager_async()
    
    async def collect_for_layer(
        self,
        layer: str,
        user_id: str,
        expert_id: str,
        session_id: Optional[str] = None,
        time_window: Optional[Dict[str, Any]] = None,
        historical_limit: int = 3
    ) -> CollectedMemories:
        """
        Collect memories for specified layer
        
        Args:
            layer: Memory layer (L1-L5)
            user_id: User ID
            expert_id: Expert ID
            session_id: Session ID (session mode)
            time_window: Time window (time window mode)
            historical_limit: Historical memory limit
        
        Returns:
            CollectedMemories object
        
        Collection rules:
        - L1: child_memories=[], historical=first k L1 in same session
        - L2: child_memories=all L1 in session, historical=first k L2 of same user
        - L3: child_memories=all L2 in time window, historical=first k L3 from previous days
        - L4: child_memories=all L3 in time window, historical=first k L4 from previous weeks
        - L5: child_memories=all L4 in time window, historical=first k L5 from previous months
        """
        await self._ensure_storage_manager()
        
        logger.info(f"Starting to collect {layer} memories: user={user_id}, expert={expert_id}, session={session_id}")
        
        if layer == "L1":
            return await self._collect_l1(user_id, expert_id, session_id, historical_limit)
        elif layer == "L2":
            return await self._collect_l2(user_id, expert_id, session_id, historical_limit)
        elif layer == "L3":
            return await self._collect_l3(user_id, expert_id, time_window, historical_limit)
        elif layer == "L4":
            return await self._collect_l4(user_id, expert_id, time_window, historical_limit)
        elif layer == "L5":
            return await self._collect_l5(user_id, expert_id, time_window, historical_limit)
        else:
            raise ValueError(f"Unsupported memory layer: {layer}")
    
    async def _collect_l1(
        self, 
        user_id: str, 
        expert_id: str, 
        session_id: str,
        historical_limit: int
    ) -> CollectedMemories:
        """
        Collect L1 memories (session mode)
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            session_id: Session ID
            historical_limit: Historical memory limit
        
        Returns:
            CollectedMemories object
        """
        # L1 has no child memories
        child_memories = []
        
        # Historical memories: first k L1 in same session
        historical_memories = await self._query_memories_by_session(
            user_id, expert_id, session_id, "L1", historical_limit
        )
        
        logger.info(f"L1 collection completed: child_memories=0, historical_memories={len(historical_memories)}")
        
        return CollectedMemories(
            child_memories=child_memories,
            historical_memories=historical_memories
        )
    
    async def _collect_l2(
        self,
        user_id: str,
        expert_id: str,
        session_id: str,
        historical_limit: int
    ) -> CollectedMemories:
        """
        Collect L2 memories (session mode)
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            session_id: Session ID
            historical_limit: Historical memory limit
        
        Returns:
            CollectedMemories object
        """
        # Child memories: all L1 in session
        child_memories = await self._query_memories_by_session(
            user_id, expert_id, session_id, "L1", limit=None
        )
        
        # Historical memories: first k L2 of same user
        historical_memories = await self._query_historical_memories(
            user_id, expert_id, "L2", historical_limit
        )
        
        logger.info(f"L2 collection completed: child_memories={len(child_memories)}, historical_memories={len(historical_memories)}")
        
        return CollectedMemories(
            child_memories=child_memories,
            historical_memories=historical_memories
        )
    
    async def _collect_l3(
        self,
        user_id: str,
        expert_id: str,
        time_window: Dict[str, Any],
        historical_limit: int
    ) -> CollectedMemories:
        """
        Collect L3 memories (time window mode)
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            time_window: Time window
            historical_limit: Historical memory limit
        
        Returns:
            CollectedMemories object
        """
        # Child memories: all L2 in time window
        child_memories = await self._query_memories_by_time_window(
            user_id, expert_id, "L2", time_window
        )
        
        # Historical memories: first k L3 from previous days
        historical_memories = await self._query_historical_memories(
            user_id, expert_id, "L3", historical_limit
        )
        
        logger.info(f"L3 collection completed: child_memories={len(child_memories)}, historical_memories={len(historical_memories)}")
        
        return CollectedMemories(
            child_memories=child_memories,
            historical_memories=historical_memories
        )
    
    async def _collect_l4(
        self,
        user_id: str,
        expert_id: str,
        time_window: Dict[str, Any],
        historical_limit: int
    ) -> CollectedMemories:
        """
        Collect L4 memories (time window mode)
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            time_window: Time window
            historical_limit: Historical memory limit
        
        Returns:
            CollectedMemories object
        """
        # Child memories: all L3 in time window
        child_memories = await self._query_memories_by_time_window(
            user_id, expert_id, "L3", time_window
        )
        
        # Historical memories: first k L4 from previous weeks
        historical_memories = await self._query_historical_memories(
            user_id, expert_id, "L4", historical_limit
        )
        
        logger.info(f"L4 collection completed: child_memories={len(child_memories)}, historical_memories={len(historical_memories)}")
        
        return CollectedMemories(
            child_memories=child_memories,
            historical_memories=historical_memories
        )
    
    async def _collect_l5(
        self,
        user_id: str,
        expert_id: str,
        time_window: Dict[str, Any],
        historical_limit: int
    ) -> CollectedMemories:
        """
        Collect L5 memories (time window mode)
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            time_window: Time window
            historical_limit: Historical memory limit
        
        Returns:
            CollectedMemories object
        """
        # Child memories: all L4 in time window
        child_memories = await self._query_memories_by_time_window(
            user_id, expert_id, "L4", time_window
        )
        
        # Historical memories: first k L5 from previous months
        historical_memories = await self._query_historical_memories(
            user_id, expert_id, "L5", historical_limit
        )
        
        logger.info(f"L5 collection completed: child_memories={len(child_memories)}, historical_memories={len(historical_memories)}")
        
        return CollectedMemories(
            child_memories=child_memories,
            historical_memories=historical_memories
        )
    
    async def _query_memories_by_session(
        self,
        user_id: str,
        expert_id: str,
        session_id: str,
        layer: str,
        limit: Optional[int] = None
    ) -> List[Any]:
        """
        Query memories by session
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            session_id: Session ID
            layer: Memory layer
            limit: Limit count
        
        Returns:
            List of memories
        """
        try:
            query = {
                "user_id": user_id,
                "expert_id": expert_id,
                "session_id": session_id,
                "level": layer
            }
            
            options = {}
            if limit is not None:
                options["limit"] = limit
            
            memories = await self.storage_manager.search_memories(query, options)
            logger.debug(f"Session query: found {len(memories)} {layer} memories")
            
            return memories
            
        except Exception as e:
            logger.error(f"Session query failed: {e}")
            return []
    
    async def _query_memories_by_time_window(
        self,
        user_id: str,
        expert_id: str,
        layer: str,
        time_window: Dict[str, Any]
    ) -> List[Any]:
        """
        Query memories by time window
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            layer: Memory layer
            time_window: Time window
        
        Returns:
            List of memories
        """
        try:
            start_time = time_window.get("start_time")
            end_time = time_window.get("end_time")
            
            # Ensure time is datetime object
            if isinstance(start_time, str):
                start_time = parse_time(start_time)
            if isinstance(end_time, str):
                end_time = parse_time(end_time)
            
            query = {
                "user_id": user_id,
                "expert_id": expert_id,
                "level": layer,
                "time_range": {
                    "start": start_time,
                    "end": end_time
                }
            }
            
            memories = await self.storage_manager.search_memories(query, {})
            logger.debug(f"Time window query: found {len(memories)} {layer} memories")
            
            return memories
            
        except Exception as e:
            logger.error(f"Time window query failed: {e}")
            return []
    
    async def _query_historical_memories(
        self,
        user_id: str,
        expert_id: str,
        layer: str,
        limit: int
    ) -> List[Any]:
        """
        Query historical memories
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            layer: Memory layer
            limit: Limit count
        
        Returns:
            List of memories
        """
        try:
            query = {
                "user_id": user_id,
                "expert_id": expert_id,
                "level": layer
            }
            
            options = {
                "limit": limit,
                "order_by": "created_at",
                "order": "desc"
            }
            
            memories = await self.storage_manager.search_memories(query, options)
            logger.debug(f"Historical memory query: found {len(memories)} {layer} memories")
            
            return memories
            
        except Exception as e:
            logger.error(f"Historical memory query failed: {e}")
            return []

