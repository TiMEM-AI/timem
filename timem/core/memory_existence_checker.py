"""
TiMem Memory Existence Checker

Check if memory exists within specified time window, support strict deduplication and completeness judgment
"""

from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

from timem.utils.logging import get_logger
from timem.utils.time_manager import get_time_manager
from timem.utils.time_utils import parse_time, ensure_iso_string

logger = get_logger(__name__)


class MemoryCompleteness(str, Enum):
    """Memory completeness enumeration"""
    COMPLETE = "complete"  # Complete memory
    PARTIAL = "partial"    # Incomplete memory (e.g., manually generated memory not covering entire window)
    MISSING = "missing"    # Does not exist


@dataclass
class TimeWindow:
    """Time window"""
    start_time: datetime
    end_time: datetime
    layer: str  # L2, L3, L4, L5
    session_id: Optional[str] = None  # Only for L2
    
    def duration_seconds(self) -> float:
        """Window duration in seconds"""
        return (self.end_time - self.start_time).total_seconds()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "layer": self.layer,
            "session_id": self.session_id,
            "duration_seconds": self.duration_seconds()
        }


@dataclass
class MemoryExistenceResult:
    """Memory existence check result"""
    exists: bool
    completeness: MemoryCompleteness
    memory_id: Optional[str] = None
    memory: Optional[Dict[str, Any]] = None
    generation_mode: Optional[str] = None  # 'auto' or 'manual'
    
    @property
    def complete(self) -> bool:
        """Whether it is complete memory"""
        return self.completeness == MemoryCompleteness.COMPLETE
    
    @property
    def partial(self) -> bool:
        """Whether it is incomplete memory"""
        return self.completeness == MemoryCompleteness.PARTIAL
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "exists": self.exists,
            "completeness": self.completeness.value,
            "memory_id": self.memory_id,
            "generation_mode": self.generation_mode,
            "complete": self.complete,
            "partial": self.partial
        }


class MemoryExistenceChecker:
    """
    Memory Existence Checker
    
    Core Features:
    1. Check if memory exists within specified time window
    2. Determine if memory is complete (covers entire time window)
    3. Distinguish between manually generated and auto-generated memory
    4. Support strict mode (only one memory per window)
    
    Time Window Definition:
    - L2: Entire session (session_id + session start/end time)
    - L3: Natural day (00:00:00 - 23:59:59)
    - L4: Natural week (Monday 00:00:00 - Sunday 23:59:59)
    - L5: Natural month (1st 00:00:00 - last day 23:59:59)
    """
    
    def __init__(
        self,
        storage_manager=None,
        strict_mode: bool = True,
        completeness_threshold: float = 0.95
    ):
        """
        Initialize memory existence checker
        
        Args:
            storage_manager: Storage manager
            strict_mode: Whether to enable strict mode (only one memory per window)
            completeness_threshold: Completeness threshold (0.95 means 95% coverage is considered complete)
        """
        self._storage_manager = storage_manager
        self.strict_mode = strict_mode
        self.completeness_threshold = completeness_threshold
        self.time_manager = get_time_manager()
        
        logger.info(
            f"MemoryExistenceChecker initialization: "
            f"strict_mode={strict_mode}, "
            f"threshold={completeness_threshold}"
        )
    
    async def _ensure_storage_manager(self):
        """Ensure storage manager is initialized"""
        if not self._storage_manager:
            from storage.memory_storage_manager import get_memory_storage_manager_async
            self._storage_manager = await get_memory_storage_manager_async()
    
    async def check_memory_exists(
        self,
        user_id: str,
        expert_id: str,
        layer: str,
        time_window: TimeWindow
    ) -> MemoryExistenceResult:
        """
        Check if memory exists within specified time window
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            layer: Memory layer (L2/L3/L4/L5)
            time_window: Time window
            
        Returns:
            MemoryExistenceResult: Existence check result
        """
        await self._ensure_storage_manager()
        
        # Build query conditions
        query = self._build_query(user_id, expert_id, layer, time_window)
        
        # Query memories
        memories = await self._query_memories(query)
        
        if not memories:
            return MemoryExistenceResult(
                exists=False,
                completeness=MemoryCompleteness.MISSING
            )
        
        # If strict mode and multiple memories exist, log warning
        if self.strict_mode and len(memories) > 1:
            logger.warning(
                f"Multiple memories found in strict mode: "
                f"user={user_id}, expert={expert_id}, layer={layer}, "
                f"count={len(memories)}"
            )
        
        # Select best memory (most recent)
        memory = self._select_best_memory(memories)
        
        # Check completeness
        completeness = await self._check_completeness(memory, time_window)
        
        # Get generation mode
        generation_mode = self._extract_generation_mode(memory)
        
        result = MemoryExistenceResult(
            exists=True,
            completeness=completeness,
            memory_id=memory.get("id") if isinstance(memory, dict) else getattr(memory, "id", None),
            memory=memory if isinstance(memory, dict) else self._memory_to_dict(memory),
            generation_mode=generation_mode
        )
        
        logger.debug(
            f"Existence check completed: layer={layer}, "
            f"exists={result.exists}, completeness={result.completeness.value}"
        )
        
        return result
    
    async def is_memory_complete(
        self,
        memory_id: str,
        expected_time_window: TimeWindow
    ) -> bool:
        """
        Check if single memory is complete
        
        Args:
            memory_id: Memory ID
            expected_time_window: Expected time window
            
        Returns:
            Whether complete
        """
        await self._ensure_storage_manager()
        
        # Get memory
        memory = await self._storage_manager.retrieve_memory(memory_id)
        
        if not memory:
            logger.warning(f"Memory does not exist: {memory_id}")
            return False
        
        # Check completeness
        completeness = await self._check_completeness(memory, expected_time_window)
        
        return completeness == MemoryCompleteness.COMPLETE
    
    async def find_incomplete_memories(
        self,
        user_id: str,
        expert_id: str,
        layer: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """
        Find incomplete memories within time range
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            layer: Memory layer
            start_date: Start date
            end_date: End date
            
        Returns:
            List of incomplete memories
        """
        await self._ensure_storage_manager()
        
        # Query all memories within time range
        query = {
            "user_id": user_id,
            "expert_id": expert_id,
            "layer": layer,
            "time_range": {
                "start": ensure_iso_string(start_date),
                "end": ensure_iso_string(end_date)
            }
        }
        
        memories = await self._query_memories(query)
        
        incomplete_memories = []
        
        for memory in memories:
            # Calculate expected time window
            memory_start = self._extract_time_window_start(memory)
            if not memory_start:
                continue
            
            expected_window = self._calculate_expected_window(layer, memory_start)
            
            # Check completeness
            completeness = await self._check_completeness(memory, expected_window)
            
            if completeness == MemoryCompleteness.PARTIAL:
                memory_dict = memory if isinstance(memory, dict) else self._memory_to_dict(memory)
                memory_dict["completeness"] = completeness.value
                incomplete_memories.append(memory_dict)
        
        logger.info(
            f"Find incomplete memories: layer={layer}, "
            f"total={len(memories)}, incomplete={len(incomplete_memories)}"
        )
        
        return incomplete_memories
    
    async def check_l2_exists(
        self,
        user_id: str,
        expert_id: str,
        session_id: str
    ) -> bool:
        """
        Check if L2 memory exists
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            session_id: Session ID
            
        Returns:
            Whether L2 memory exists
        """
        await self._ensure_storage_manager()
        
        try:
            # Query L2 memory
            query = {
                "user_id": user_id,
                "expert_id": expert_id,
                "level": "L2",
                "session_id": session_id
            }
            
            memories = await self._query_memories(query)
            exists = len(memories) > 0
            
            logger.debug(
                f"Check L2 memory: user={user_id}, expert={expert_id}, "
                f"session={session_id}, exists={exists}"
            )
            
            return exists
            
        except Exception as e:
            logger.error(f"Check L2 memory failed: {e}", exc_info=True)
            return False
    
    # ========================================
    # Private methods
    # ========================================
    
    def _build_query(
        self,
        user_id: str,
        expert_id: str,
        layer: str,
        time_window: TimeWindow
    ) -> Dict[str, Any]:
        """Build query conditions"""
        query = {
            "user_id": user_id,
            "expert_id": expert_id,
            "layer": layer
        }
        
        # L2 uses session_id query
        if layer == "L2" and time_window.session_id:
            query["session_id"] = time_window.session_id
        else:
            # L3-L5 use time range query
            query["time_range"] = {
                "start": ensure_iso_string(time_window.start_time),
                "end": ensure_iso_string(time_window.end_time)
            }
        
        return query
    
    async def _query_memories(self, query: Dict[str, Any]) -> List[Any]:
        """Query memories"""
        try:
            options = {
                "sort_by": "created_at",
                "sort_order": "desc",
                "limit": 10  # Return at most 10 (normally should be only 1)
            }
            
            memories = await self._storage_manager.search_memories(query, options)
            return memories if memories else []
        except Exception as e:
            logger.error(f"Query memories failed: {e}", exc_info=True)
            return []
    
    def _select_best_memory(self, memories: List[Any]) -> Any:
        """Select best memory (most recent)"""
        if not memories:
            return None
        
        # Already sorted by created_at in descending order, take first
        return memories[0]
    
    async def _check_completeness(
        self,
        memory: Any,
        expected_window: TimeWindow
    ) -> MemoryCompleteness:
        """
        Check memory completeness
        
        Completeness judgment:
        - L2: Based on session_id, considered complete if memory exists (L2 is session-level)
        - L3-L5: memory.time_window_end - memory.time_window_start >= expected window size * threshold
        """
        # 🔧 Fix: L2 memory based on session_id, considered complete if exists
        if expected_window.layer == "L2":
            # L2 memory is session-level, considered complete if memory exists
            # No need to check time window completeness as session time window is dynamic
            logger.debug(f"L2 memory completeness check: based on session_id, return COMPLETE directly")
            return MemoryCompleteness.COMPLETE
        
        # Extract memory time window
        memory_start = self._extract_time_window_start(memory)
        memory_end = self._extract_time_window_end(memory)
        
        if not memory_start or not memory_end:
            # If time window info is missing, check for is_complete flag
            is_complete = self._extract_is_complete(memory)
            if is_complete is None:
                # Default to complete (backward compatible)
                return MemoryCompleteness.COMPLETE
            return MemoryCompleteness.COMPLETE if is_complete else MemoryCompleteness.PARTIAL
        
        # Calculate actual coverage time
        actual_duration = (memory_end - memory_start).total_seconds()
        
        # Calculate expected time
        expected_duration = expected_window.duration_seconds()
        
        # Determine completeness
        coverage_ratio = actual_duration / expected_duration if expected_duration > 0 else 0
        
        logger.debug(
            f"Completeness check: actual={actual_duration}s, "
            f"expected={expected_duration}s, ratio={coverage_ratio:.2f}"
        )
        
        if coverage_ratio >= self.completeness_threshold:
            return MemoryCompleteness.COMPLETE
        else:
            return MemoryCompleteness.PARTIAL
    
    def _extract_time_window_start(self, memory: Any) -> Optional[datetime]:
        """Extract time window start time"""
        if isinstance(memory, dict):
            start = memory.get("time_window_start")
        else:
            start = getattr(memory, "time_window_start", None)
        
        if isinstance(start, str):
            try:
                return parse_time(start)
            except:
                return None
        return start
    
    def _extract_time_window_end(self, memory: Any) -> Optional[datetime]:
        """Extract time window end time"""
        if isinstance(memory, dict):
            end = memory.get("time_window_end")
        else:
            end = getattr(memory, "time_window_end", None)
        
        if isinstance(end, str):
            try:
                return parse_time(end)
            except:
                return None
        return end
    
    def _extract_is_complete(self, memory: Any) -> Optional[bool]:
        """Extract is_complete flag"""
        if isinstance(memory, dict):
            metadata = memory.get("metadata", {})
            if isinstance(metadata, dict):
                return metadata.get("is_complete")
        else:
            metadata = getattr(memory, "metadata", {})
            if isinstance(metadata, dict):
                return metadata.get("is_complete")
        return None
    
    def _extract_generation_mode(self, memory: Any) -> Optional[str]:
        """Extract generation mode (auto/manual)"""
        if isinstance(memory, dict):
            metadata = memory.get("metadata", {})
            if isinstance(metadata, dict):
                return metadata.get("generation_mode")
        else:
            metadata = getattr(memory, "metadata", {})
            if isinstance(metadata, dict):
                return metadata.get("generation_mode")
        return None
    
    def _calculate_expected_window(
        self,
        layer: str,
        reference_time: datetime
    ) -> TimeWindow:
        """
        Calculate expected time window
        
        Args:
            layer: Memory layer
            reference_time: Reference time
            
        Returns:
            Expected time window
        """
        if layer == "L3":
            # Natural day
            start = self.time_manager.get_day_start(reference_time)
            end = self.time_manager.get_day_end(reference_time)
        elif layer == "L4":
            # Natural week
            start = self.time_manager.get_week_start(reference_time)
            end = self.time_manager.get_week_end(reference_time)
        elif layer == "L5":
            # Natural month
            start = self.time_manager.get_month_start(reference_time)
            end = self.time_manager.get_month_end(reference_time)
        else:
            # L2 or other, default to 1 hour before and after reference time
            start = reference_time - timedelta(hours=1)
            end = reference_time + timedelta(hours=1)
        
        return TimeWindow(
            start_time=start,
            end_time=end,
            layer=layer
        )
    
    def _memory_to_dict(self, memory: Any) -> Dict[str, Any]:
        """Convert memory object to dictionary"""
        if isinstance(memory, dict):
            return memory
        
        return {
            "id": getattr(memory, "id", None),
            "user_id": getattr(memory, "user_id", None),
            "expert_id": getattr(memory, "expert_id", None),
            "session_id": getattr(memory, "session_id", None),
            "level": getattr(memory, "level", None),
            "content": getattr(memory, "content", None),
            "time_window_start": getattr(memory, "time_window_start", None),
            "time_window_end": getattr(memory, "time_window_end", None),
            "created_at": getattr(memory, "created_at", None),
            "metadata": getattr(memory, "metadata", {})
        }


# Global singleton
_memory_existence_checker_instance = None


async def get_memory_existence_checker(
    storage_manager=None,
    strict_mode: bool = True
) -> MemoryExistenceChecker:
    """
    Get memory existence checker singleton
    
    Args:
        storage_manager: Storage manager
        strict_mode: Whether to enable strict mode
        
    Returns:
        MemoryExistenceChecker instance
    """
    global _memory_existence_checker_instance
    
    if _memory_existence_checker_instance is None:
        _memory_existence_checker_instance = MemoryExistenceChecker(
            storage_manager=storage_manager,
            strict_mode=strict_mode
        )
    
    return _memory_existence_checker_instance

