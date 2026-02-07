"""
Scheduled Backfill Service (Refactored Version)

Implements scheduled backfill using new CatchUpDetector and MemoryGenerationService.run_backfill()
"""

import asyncio
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
import yaml

from timem.utils.logging import get_logger
from timem.core.catchup_detector import CatchUpDetector, BackfillTask
from timem.core.backfill_task_sorter import BackfillTaskSorter
from timem.utils.time_manager import get_time_manager
from timem.utils.expert_helper import get_all_experts_for_user

logger = get_logger(__name__)


@dataclass
class BackfillReport:
    """Backfill report"""
    start_time: datetime
    end_time: Optional[datetime] = None
    total_users: int = 0
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    skipped_tasks: int = 0
    errors: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        duration = (self.end_time - self.start_time).total_seconds() if self.end_time else 0
        return {
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": duration,
            "total_users": self.total_users,
            "total_tasks": self.total_tasks,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "skipped_tasks": self.skipped_tasks,
            "success_rate": self.completed_tasks / self.total_tasks if self.total_tasks > 0 else 0,
            "error_count": len(self.errors)
        }


class ScheduledBackfillService:
    """
    Scheduled Backfill Service (Refactored Version)
    
    Features:
    1. Use CatchUpDetector to detect missing memories
    2. Use MemoryGenerationService.run_backfill() to perform backfill
    3. Support automatic backfill at midnight
    4. Concurrency control and error handling
    """
    
    def __init__(
        self,
        catchup_detector: Optional[CatchUpDetector] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize scheduled backfill service
        
        Args:
            catchup_detector: CatchUp detector (new architecture)
            config: Configuration parameters
        """
        self.catchup_detector = catchup_detector or CatchUpDetector()
        self.task_sorter = BackfillTaskSorter()
        self.memory_service = None  # Lazy initialization
        self.time_manager = get_time_manager()
        
        # Load configuration
        self.config = config or self._load_config()
        self.enabled = self.config.get("enabled", False)
        self.batch_size = self.config.get("batch_size", 10)
        self.parallel_tasks = self.config.get("parallel_tasks", 3)
        self.layers = self.config.get("layers", ["L2", "L3", "L4", "L5"])
        self.lookback_days = self.config.get("lookback_days", 30)
        
        # Concurrency control
        self._semaphore = asyncio.Semaphore(self.parallel_tasks)
        
        logger.info(
            f"ScheduledBackfillService initialized (refactored version): "
            f"enabled={self.enabled}, batch_size={self.batch_size}, "
            f"parallel_tasks={self.parallel_tasks}"
        )
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from settings.yaml"""
        try:
            with open("config/settings.yaml", "r", encoding="utf-8") as f:
                settings = yaml.safe_load(f)
                return settings.get("memory_generation", {}).get("scheduled_backfill", {})
        except Exception as e:
            logger.warning(f"Failed to load configuration, using default: {e}")
            return {}
    
    async def run_daily_backfill(
        self, 
        user_expert_pairs: Optional[List[Tuple[str, str]]] = None
    ) -> BackfillReport:
        """
        Execute daily backfill task (using new architecture)
        
        Args:
            user_expert_pairs: List of user-expert pairs, if None get all active pairs from database
            
        Returns:
            BackfillReport: Backfill report
        """
        if not self.enabled:
            logger.info("Scheduled backfill service is disabled, skipping execution")
            return BackfillReport(
                start_time=datetime.now(),
                end_time=datetime.now()
            )
        
        # Initialize memory generation service
        if not self.memory_service:
            from services.memory_generation_service import get_memory_generation_service
            self.memory_service = await get_memory_generation_service()
        
        report = BackfillReport(start_time=datetime.now())
        yesterday = (datetime.now() - timedelta(days=1)).date()
        
        logger.info("=" * 60)
        logger.info("Start executing daily memory backfill task (refactored version)")
        logger.info(f"Time: {report.start_time}")
        logger.info(f"Yesterday: {yesterday}")
        logger.info(f"Configuration: batch_size={self.batch_size}, parallel_tasks={self.parallel_tasks}")
        logger.info("=" * 60)
        
        try:
            # 1. Get user-expert pairs that need backfill
            if user_expert_pairs is None:
                user_expert_pairs = await self._get_active_user_expert_pairs()
            
            report.total_users = len(user_expert_pairs)
            logger.info(f"Found {report.total_users} active user-expert pairs")
            
            # 2. Process in batches
            for i in range(0, len(user_expert_pairs), self.batch_size):
                batch = user_expert_pairs[i:i + self.batch_size]
                batch_num = i // self.batch_size + 1
                total_batches = (len(user_expert_pairs) + self.batch_size - 1) // self.batch_size
                
                logger.info(f"\nProcessing batch {batch_num}/{total_batches} ({len(batch)} pairs)")
                
                # Concurrently process users in batch
                tasks = [
                    self._backfill_for_user_async(user_id, expert_id, yesterday, report)
                    for user_id, expert_id in batch
                ]
                await asyncio.gather(*tasks, return_exceptions=True)
            
            report.end_time = datetime.now()
            
            # 3. Output report
            self._log_report(report)
            
            return report
            
        except Exception as e:
            logger.error(f"Daily backfill task execution failed: {e}", exc_info=True)
            report.end_time = datetime.now()
            report.errors.append({
                "type": "fatal_error",
                "message": str(e),
                "timestamp": datetime.now().isoformat()
            })
            return report
    
    async def _backfill_for_user_async(
        self,
        user_id: str,
        expert_id: str,
        yesterday: date,
        report: BackfillReport
    ):
        """Backfill for single user (with concurrency control, using new architecture)"""
        async with self._semaphore:
            try:
                # 1. Use new detection method - detect missing memories from yesterday
                tasks = await self.catchup_detector.detect_missing_for_yesterday(
                    user_id=user_id,
                    expert_id=expert_id,
                    yesterday=yesterday
                )
                
                if not tasks:
                    logger.debug(f"User {user_id[:8]}... - Expert {expert_id[:8]}...: No missing memories")
                    return
                
                report.total_tasks += len(tasks)
                logger.info(f"User {user_id[:8]}... - Expert {expert_id[:8]}...: Detected {len(tasks)} missing tasks")
                
                # 2. Sort tasks
                sorted_tasks = self.task_sorter.sort_tasks(tasks)
                
                # 3. Use new backfill method
                result = await self.memory_service.run_backfill(sorted_tasks)
                
                # 4. Update report
                if result.success:
                    completed = len(result.memories)
                    report.completed_tasks += completed
                    logger.info(f"User {user_id[:8]}... - Expert {expert_id[:8]}...: Backfill succeeded {completed} memories")
                else:
                    report.failed_tasks += len(tasks)
                    logger.error(f"User {user_id[:8]}... - Expert {expert_id[:8]}...: Backfill failed - {result.error}")
                    
            except Exception as e:
                logger.error(f"User {user_id[:8]}... - Expert {expert_id[:8]}... backfill exception: {e}", exc_info=True)
                report.errors.append({
                    "user_id": user_id,
                    "expert_id": expert_id,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                })
    
    async def backfill_for_user(
        self,
        user_id: str,
        expert_id: Optional[str] = None,
        layers: List[str] = None,
        report: Optional[BackfillReport] = None
    ) -> Dict[str, Any]:
        """
        Backfill memories for user (by layer order, generate and store one by one)

        [UPDATED] expert_id is now optional:
        - If expert_id is None or empty: backfill for ALL experts of this user
        - If expert_id is specified: backfill only for that specific expert

        Refactoring points:
        1. Strictly follow L2→L3→L4→L5 order
        2. Check dependency layer completeness before each layer
        3. Generate one and store one (no longer batch)
        4. Update progress in real time

        Args:
            user_id: User ID
            expert_id: Expert ID (optional, None means all experts)
            layers: List of layers to backfill (default: ["L2", "L3", "L4", "L5"])
            report: Backfill report (optional)

        Returns:
            Dict containing completed, failed, layers and other information
        """
        if layers is None:
            layers = ["L2", "L3", "L4", "L5"]

        # If expert_id is not specified, get all experts for this user
        if not expert_id:
            logger.info(f"\n{'='*40}")
            logger.info(f"Start backfill: user={user_id}, expert_id=ALL")
            logger.info(f"{'='*40}")

            # Get all experts for this user
            expert_ids = await get_all_experts_for_user(user_id)

            if not expert_ids:
                logger.warning(f"User {user_id} has no experts, skipping backfill")
                return {
                    "user_id": user_id,
                    "expert_id": "ALL",
                    "layers": {},
                    "total_tasks": 0,
                    "completed": 0,
                    "failed": 0,
                    "skipped": 0,
                    "expert_count": 0,
                    "expert_results": {}
                }

            logger.info(f"Found {len(expert_ids)} experts for user {user_id}: {expert_ids}")

            # Backfill for each expert
            expert_results = {}
            total_completed = 0
            total_failed = 0
            total_skipped = 0
            total_tasks = 0

            for exp_id in expert_ids:
                logger.info(f"\n{'-'*40}")
                logger.info(f"Backfilling expert {exp_id} for user {user_id}")
                logger.info(f"{'-'*40}")

                expert_result = await self.backfill_for_user(
                    user_id=user_id,
                    expert_id=exp_id,
                    layers=layers,
                    report=report
                )

                expert_results[exp_id] = expert_result
                total_completed += expert_result.get("completed", 0)
                total_failed += expert_result.get("failed", 0)
                total_skipped += expert_result.get("skipped", 0)
                total_tasks += expert_result.get("total_tasks", 0)

            # Aggregate results
            result = {
                "user_id": user_id,
                "expert_id": "ALL",
                "layers": {},  # Aggregated across all experts
                "total_tasks": total_tasks,
                "completed": total_completed,
                "failed": total_failed,
                "skipped": total_skipped,
                "expert_count": len(expert_ids),
                "expert_results": expert_results
            }

            logger.info(f"\nUser {user_id} backfill completed (ALL experts):")
            logger.info(f"  - Expert count: {len(expert_ids)}")
            logger.info(f"  - Total tasks: {result['total_tasks']}")
            logger.info(f"  - Completed: {result['completed']}")
            logger.info(f"  - Failed: {result['failed']}")
            logger.info(f"  - Skipped: {result['skipped']}")

            return result

        # expert_id is specified - backfill for that specific expert
        logger.info(f"\n{'='*40}")
        logger.info(f"Start backfill: user={user_id}, expert={expert_id}")
        logger.info(f"{'='*40}")

        result = {
            "user_id": user_id,
            "expert_id": expert_id,
            "layers": {},
            "total_tasks": 0,
            "completed": 0,
            "failed": 0,
            "skipped": 0
        }

        try:
            # 1. Detect missing memories for all layers
            all_missing = await self.catchup_detector.detect_manual_completion(
                user_id=user_id,
                expert_id=expert_id,
                force_update=False
            )
            
            # Count total tasks
            result["total_tasks"] = len(all_missing)
            if report:
                report.total_tasks = len(all_missing)
            
            if result["total_tasks"] == 0:
                logger.info(f"User {user_id} has no missing memories")
                return result
            
            logger.info(f"Detected {result['total_tasks']} missing memories")
            
            # 2. Group tasks by layer
            tasks_by_layer = {}
            for task in all_missing:
                layer = task.layer
                if layer not in tasks_by_layer:
                    tasks_by_layer[layer] = []
                tasks_by_layer[layer].append(task)
            
            # 3. Backfill each layer in order
            for layer in ["L2", "L3", "L4", "L5"]:
                if layer not in layers:
                    continue
                
                tasks = tasks_by_layer.get(layer, [])
                if not tasks:
                    continue
                
                logger.info(f"\nStart backfill {layer} ({len(tasks)} tasks)")
                
                layer_result = await self._backfill_single_layer(
                    user_id, expert_id, layer, tasks
                )
                
                result["layers"][layer] = layer_result
                result["completed"] += layer_result["completed"]
                result["failed"] += layer_result["failed"]
                result["skipped"] += layer_result["skipped"]
                
                if report:
                    report.completed_tasks += layer_result["completed"]
                    report.failed_tasks += layer_result["failed"]
                    report.skipped_tasks += layer_result["skipped"]
                    if layer_result.get("errors"):
                        report.errors.extend(layer_result["errors"])
            
            logger.info(f"\nUser {user_id} backfill completed:")
            logger.info(f"  - Total tasks: {result['total_tasks']}")
            logger.info(f"  - Completed: {result['completed']}")
            logger.info(f"  - Failed: {result['failed']}")
            logger.info(f"  - Skipped: {result['skipped']}")
            
            return result
            
        except Exception as e:
            logger.error(f"User {user_id} backfill failed: {e}", exc_info=True)
            if report:
                report.errors.append({
                    "type": "user_error",
                    "user_id": user_id,
                    "expert_id": expert_id,
                    "message": str(e),
                    "timestamp": datetime.now().isoformat()
                })
            result["failed"] = result["total_tasks"]
            return result
    
    async def _backfill_single_layer(
        self,
        user_id: str,
        expert_id: str,
        layer: str,
        tasks: List[BackfillTask]
    ) -> Dict[str, Any]:
        """
        Backfill memories for single layer (using new run_backfill interface)
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            layer: Memory layer
            tasks: List of backfill tasks
            
        Returns:
            Layer backfill result
        """
        logger.info(f"Backfill {layer} layer: {len(tasks)} tasks")
        
        # Ensure memory_service is initialized
        if not self.memory_service:
            from services.memory_generation_service import get_memory_generation_service
            self.memory_service = await get_memory_generation_service()
        
        # Use BackfillTaskSorter to sort tasks
        sorted_tasks = self.task_sorter.sort_tasks(tasks)
        
        # Use new run_backfill method for batch processing
        result = await self.memory_service.run_backfill(sorted_tasks)
        
        # Process results
        if result.success:
            completed = len(result.memories)
            failed = 0
        else:
            completed = 0
            failed = len(tasks)
        
        logger.info(
            f"{layer} layer backfill completed: "
            f"success={completed}/{len(tasks)}"
        )
        
        return {
            "layer": layer,
            "total": len(tasks),
            "completed": completed,
            "failed": failed,
            "skipped": 0,
            "errors": [] if result.success else [{"error": result.error}]
        }
    
    async def _generate_memory_for_task(self, task: BackfillTask) -> bool:
        """
        Generate memory for backfill task
        
        Args:
            task: Backfill task
            
        Returns:
            Whether memory was successfully generated (returns False if already exists)
        """
        # Ensure memory_service is initialized
        if not self.memory_service:
            from services.memory_generation_service import get_memory_generation_service
            self.memory_service = await get_memory_generation_service()
        
        # This method is no longer used because we now use memory_service.run_backfill()
        # Keep this method for backward compatibility, but it will not be called
        logger.warning(f"_generate_memory_for_task method is deprecated, please use memory_service.run_backfill()")
        return False
    
    async def _get_active_user_expert_pairs(self) -> List[Tuple[str, str]]:
        """
        Get active user-expert pairs
        
        Query from database the user-expert groups with recent activity
        
        Returns:
            [(user_id, expert_id), ...]
        """
        try:
            from timem.core.global_connection_pool import get_global_pool_manager
            from sqlalchemy import text
            
            pool_manager = await get_global_pool_manager()
            
            # Option 1: Query from memory_sessions table (if table exists and has last_activity field)
            # Option 2: Query from core_memories table for recently active user-expert groups
            query = text("""
                SELECT DISTINCT user_id, expert_id
                FROM core_memories
                WHERE created_at >= NOW() - INTERVAL :days DAY
                ORDER BY created_at DESC
            """)
            
            async with pool_manager.get_managed_session() as session:
                result = await session.execute(query, {"days": self.lookback_days})
                pairs = [(str(row.user_id), str(row.expert_id)) for row in result]
            
            logger.info(f"Queried {len(pairs)} active user-expert groups (last {self.lookback_days} days)")
            return pairs
            
        except Exception as e:
            logger.error(f"Failed to query active user-expert pairs: {e}", exc_info=True)
            # Fallback: return empty list
            return []
    
    def _log_report(self, report: BackfillReport):
        """Log backfill report"""
        logger.info("\n" + "=" * 60)
        logger.info("Daily backfill task completion report")
        logger.info("=" * 60)
        
        report_dict = report.to_dict()
        
        logger.info(f"Start time: {report_dict['start_time']}")
        logger.info(f"End time: {report_dict['end_time']}")
        logger.info(f"Duration: {report_dict['duration_seconds']:.2f} seconds")
        logger.info(f"Users processed: {report.total_users}")
        logger.info(f"Total tasks: {report.total_tasks}")
        logger.info(f"Completed: {report.completed_tasks}")
        logger.info(f"Failed: {report.failed_tasks}")
        logger.info(f"Skipped: {report.skipped_tasks}")
        logger.info(f"Success rate: {report_dict['success_rate']:.2%}")
        
        if report.errors:
            logger.info(f"\nError count: {len(report.errors)}")
            for i, error in enumerate(report.errors[:10], 1):  # Only show first 10 errors
                logger.error(f"  {i}. {error.get('type', 'unknown')}: {error.get('message', 'N/A')}")
            if len(report.errors) > 10:
                logger.error(f"  ... {len(report.errors) - 10} more errors")
        
        logger.info("=" * 60)


# Global singleton
_scheduled_backfill_service = None


def get_scheduled_backfill_service() -> ScheduledBackfillService:
    """Get scheduled backfill service singleton"""
    global _scheduled_backfill_service
    if _scheduled_backfill_service is None:
        _scheduled_backfill_service = ScheduledBackfillService()
    return _scheduled_backfill_service
