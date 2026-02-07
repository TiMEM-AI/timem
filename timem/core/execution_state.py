"""
Execution State - Independent state management at user group level

Design Principles:
1. Lightweight: Quick creation and destruction
2. Isolation: Completely independent, no shared state
3. Transferability: Pass through parameters, not stored globally
4. Thread safety: Each state independent, no lock protection needed

Purpose:
- Provide independent execution state for each user group/session
- Track session turns, temporary data and other state
- Eliminate global state contention, achieve zero-contention concurrency
"""

from datetime import datetime
from typing import Dict, Any, Optional, Set
import uuid
from timem.utils.logging import get_logger

logger = get_logger(__name__)


class ExecutionState:
    """
    Execution State - Independent state management at user group level
    
    Each user group/session/request should have an independent ExecutionState instance,
    ensuring state is completely isolated and avoiding concurrency contention.
    
    Examples:
        >>> # Create state
        >>> state = ExecutionState(user_id="user1", expert_id="expert1", session_id="session1")
        >>>
        >>> # Track session turns
        >>> state.set_session_max_turn("session1", 5)
        >>> max_turn = state.get_session_max_turn("session1")
        >>>
        >>> # Store temporary data
        >>> state.set_temp_data("processing_step", "l1_generation")
        >>>
        >>> # Pass to storage layer
        >>> await storage.batch_store_memories(memories, execution_state=state)
    """
    
    def __init__(
        self, 
        user_id: str, 
        expert_id: str, 
        session_id: Optional[str] = None,
        context_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize execution state
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            session_id: Session ID (optional)
            state_id: State ID (optional, for tracking and debugging)
            metadata: Additional metadata (optional)
        """
        # Basic identifiers
        self.state_id = context_id or str(uuid.uuid4())  # Maintain backward compatibility
        self.user_id = user_id
        self.expert_id = expert_id
        self.session_id = session_id
        
        # Session turn tracking (independent state)
        # key: session_id, value: max_turn_number
        self._session_turn_tracker: Dict[str, int] = {}
        
        # Session creation tracking (avoid duplicate creation)
        # Record already created session_ids
        self._created_sessions: Set[str] = set()
        
        # Temporary data storage (for cross-step data transfer)
        # Can store any temporary information needed during processing
        self._temp_data: Dict[str, Any] = {}
        
        # Metadata (for extension and debugging)
        self._metadata: Dict[str, Any] = metadata or {}
        
        # Timestamps
        self._created_at = datetime.now()
        self._last_accessed = self._created_at
        
        # Statistics
        self._stats = {
            "memories_created": 0,
            "memories_updated": 0,
            "queries_executed": 0,
            "errors": 0
        }
        
        logger.debug(f"Create execution state: {self}")
    
    # ==================== Session turn management ===================="
    
    def get_session_max_turn(self, session_id: str) -> int:
        """
        Get maximum turn count for specified session
        
        Args:
            session_id: Session ID
            
        Returns:
            int: Maximum turn count (returns 0 if session doesn't exist)
        """
        self._last_accessed = datetime.now()
        return self._session_turn_tracker.get(session_id, 0)
    
    def set_session_max_turn(self, session_id: str, turn_number: int):
        """
        Set maximum turn count for specified session
        
        Args:
            session_id: Session ID
            turn_number: Turn count
        """
        self._last_accessed = datetime.now()
        old_value = self._session_turn_tracker.get(session_id, 0)
        self._session_turn_tracker[session_id] = turn_number
        
        logger.debug(f"[{self.state_id}] Update session turn: {session_id} {old_value} -> {turn_number}")
    
    def increment_session_turn(self, session_id: str, count: int = 1) -> int:
        """
        Increment turn count for specified session
        
        Args:
            session_id: Session ID
            count: Amount to increment (default 1)
            
        Returns:
            int: Updated turn count
        """
        self._last_accessed = datetime.now()
        current = self.get_session_max_turn(session_id)
        new_turn = current + count
        self.set_session_max_turn(session_id, new_turn)
        return new_turn
    
    def get_all_session_turns(self) -> Dict[str, int]:
        """Get turn tracking information for all sessions"""
        return self._session_turn_tracker.copy()
    
    # ==================== Session creation management ====================
    
    def mark_session_created(self, session_id: str):
        """Mark session as created"""
        self._created_sessions.add(session_id)
        logger.debug(f"[{self.state_id}] Mark session created: {session_id}")
    
    def is_session_created(self, session_id: str) -> bool:
        """Check if session is created"""
        return session_id in self._created_sessions
    
    def get_created_sessions(self) -> Set[str]:
        """Get all created sessions"""
        return self._created_sessions.copy()
    
    # ==================== Temporary data management ====================
    
    def set_temp_data(self, key: str, value: Any):
        """
        Store temporary data
        
        Args:
            key: Data key
            value: Data value
        """
        self._temp_data[key] = value
        logger.debug(f"[{self.state_id}] Set temporary data: {key}")
    
    def get_temp_data(self, key: str, default: Any = None) -> Any:
        """
        Get temporary data
        
        Args:
            key: Data key
            default: Default value (if key doesn't exist)
            
        Returns:
            Any: Data value or default value
        """
        return self._temp_data.get(key, default)
    
    def remove_temp_data(self, key: str) -> Any:
        """
        Remove and return temporary data
        
        Args:
            key: Data key
            
        Returns:
            Any: Removed data value (returns None if doesn't exist)
        """
        return self._temp_data.pop(key, None)
    
    def clear_temp_data(self):
        """Clear all temporary data"""
        self._temp_data.clear()
        logger.debug(f"[{self.state_id}] Clear temporary data")
    
    def get_all_temp_data(self) -> Dict[str, Any]:
        """Get all temporary data"""
        return self._temp_data.copy()
    
    # ==================== Metadata management ====================
    
    def set_metadata(self, key: str, value: Any):
        """
        Set metadata
        
        Args:
            key: Metadata key
            value: Metadata value
        """
        self._metadata[key] = value
    
    def get_metadata(self, key: str, default: Any = None) -> Any:
        """
        Get metadata
        
        Args:
            key: Metadata key
            default: Default value (if key doesn't exist)
            
        Returns:
            Any: Metadata value or default value
        """
        return self._metadata.get(key, default)
    
    def update_metadata(self, metadata: Dict[str, Any]):
        """
        Batch update metadata
        
        Args:
            metadata: Metadata dictionary
        """
        self._metadata.update(metadata)
    
    def get_all_metadata(self) -> Dict[str, Any]:
        """Get all metadata"""
        return self._metadata.copy()
    
    # ==================== Statistics ====================
    
    def increment_stat(self, stat_name: str, count: int = 1):
        """
        Increment statistic count
        
        Args:
            stat_name: Statistic name
            count: Amount to increment
        """
        if stat_name in self._stats:
            self._stats[stat_name] += count
        else:
            self._stats[stat_name] = count
    
    def get_stat(self, stat_name: str, default: int = 0) -> int:
        """
        Get statistic value
        
        Args:
            stat_name: Statistic name
            default: Default value
            
        Returns:
            int: Statistic value
        """
        return self._stats.get(stat_name, default)
    
    def get_all_stats(self) -> Dict[str, int]:
        """Get all statistics"""
        return self._stats.copy()
    
    # ==================== Utility methods ====================
    
    def get_elapsed_time(self) -> float:
        """
        Get context alive time in seconds
        
        Returns:
            float: Time from creation to now (seconds)
        """
        return (datetime.now() - self._created_at).total_seconds()
    
    def get_idle_time(self) -> float:
        """
        Get context idle time in seconds
        
        Returns:
            float: Time from last access to now (seconds)
        """
        return (datetime.now() - self._last_accessed).total_seconds()
    
    def get_last_timestamp(self, user_id: str, expert_id: str) -> Optional[datetime]:
        """
        Get last processing timestamp for user group
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            
        Returns:
            Optional[datetime]: Last processing timestamp, None if not exists
        """
        timestamp_key = f"{user_id}_{expert_id}_last_timestamp"
        return self._temp_data.get(timestamp_key)
    
    def set_last_timestamp(self, user_id: str, expert_id: str, timestamp: datetime) -> None:
        """
        Set last processing timestamp for user group
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            timestamp: Timestamp
        """
        timestamp_key = f"{user_id}_{expert_id}_last_timestamp"
        self._temp_data[timestamp_key] = timestamp
        self._last_accessed = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary (for logging, debugging and serialization)
        
        Returns:
            Dict[str, Any]: Context information dictionary
        """
        return {
            "state_id": self.state_id,
            "user_id": self.user_id,
            "expert_id": self.expert_id,
            "session_id": self.session_id,
            "session_turn_tracker": self._session_turn_tracker.copy(),
            "created_sessions": list(self._created_sessions),
            "temp_data_keys": list(self._temp_data.keys()),  # Only return keys to avoid sensitive data leakage
            "metadata": self._metadata.copy(),
            "created_at": self._created_at.isoformat(),
            "last_accessed": self._last_accessed.isoformat(),
            "elapsed_time": self.get_elapsed_time(),
            "idle_time": self.get_idle_time(),
            "stats": self._stats.copy()
        }
    
    def __repr__(self) -> str:
        """String representation"""
        return (
            f"ExecutionState("
            f"id={self.state_id[:8]}..., "
            f"user={self.user_id}, "
            f"expert={self.expert_id}, "
            f"session={self.session_id}, "
            f"sessions_tracked={len(self._session_turn_tracker)})"
        )
    
    def __str__(self) -> str:
        """User-friendly string representation"""
        return self.__repr__()
