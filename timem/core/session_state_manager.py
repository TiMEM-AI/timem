"""
TiMem Session State Manager

Manages session active/inactive state based on finite state machine, supports 10-minute timeout mechanism
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from enum import Enum
import asyncio
from dataclasses import dataclass

from timem.utils.logging import get_logger
from timem.utils.time_manager import get_time_manager

logger = get_logger(__name__)


class SessionState(str, Enum):
    """Session state enumeration"""
    ACTIVE = "active"
    INACTIVE = "inactive"


@dataclass
class SessionInfo:
    """Session information"""
    session_id: str
    user_id: str
    expert_id: str
    state: SessionState
    last_interaction_time: datetime
    l2_generated: bool
    l2_memory_id: Optional[str] = None
    created_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "expert_id": self.expert_id,
            "state": self.state.value,
            "last_interaction_time": self.last_interaction_time.isoformat() if self.last_interaction_time else None,
            "l2_generated": self.l2_generated,
            "l2_memory_id": self.l2_memory_id,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class SessionStateManager:
    """
    Session State Manager
    
    Core Features:
    1. Track session active/inactive state
    2. Detect 10-minute no-interaction timeout
    3. Trigger L2 completion decision on state transition
    4. Support manual marking session as inactive
    
    State Machine Model:
    - [New session] → active
    - active + 10 minutes no interaction → inactive (trigger L2 completion)
    - active + create other session → inactive (trigger L2 completion immediately)
    - inactive + new interaction → active (reset timer)
    - active + interaction within 10 minutes → active (reset timer)
    """
    
    def __init__(
        self,
        db_session=None,
        inactive_timeout_minutes: int = 10,
        check_interval_seconds: int = 60
    ):
        """
        Initialize session state manager
        
        Args:
            db_session: Database session (for PostgreSQL storage)
            inactive_timeout_minutes: Timeout minutes, default 10 minutes
            check_interval_seconds: Check interval seconds, default 60 seconds
        """
        self.db_session = db_session
        self.inactive_timeout = timedelta(minutes=inactive_timeout_minutes)
        self.check_interval = check_interval_seconds
        self.time_manager = get_time_manager()
        
        # Memory cache (optional, reduce database queries)
        self._session_cache: Dict[str, SessionInfo] = {}
        self._cache_lock = asyncio.Lock()
        
        logger.info(
            f"SessionStateManager initialization: "
            f"timeout={inactive_timeout_minutes} minutes, "
            f"check_interval={check_interval_seconds} seconds"
        )
    
    async def track_interaction(
        self,
        session_id: str,
        user_id: str,
        expert_id: str,
        timestamp: Optional[datetime] = None
    ) -> SessionInfo:
        """
        Track session interaction, update last interaction time
        
        State transition logic:
        - If session doesn't exist → create new session (active)
        - If session is inactive → convert to active (reset timer)
        - If session is active → update last interaction time (reset timer)
        
        Args:
            session_id: Session ID
            user_id: User ID
            expert_id: Expert ID
            timestamp: Interaction timestamp, default current time
            
        Returns:
            Updated session information
        """
        if timestamp is None:
            timestamp = self.time_manager.get_current_time()
        
        # Ensure time has no timezone
        if timestamp.tzinfo is not None:
            timestamp = timestamp.replace(tzinfo=None)
        
        # Check if creating other session
        # If user has other active sessions under same expert, mark them as inactive
        await self._check_and_deactivate_other_sessions(user_id, expert_id, session_id)
        
        # Get or create session information
        session_info = await self._get_or_create_session(
            session_id, user_id, expert_id, timestamp
        )
        
        # State transition
        old_state = session_info.state
        new_state = SessionState.ACTIVE
        
        if old_state == SessionState.INACTIVE:
            logger.info(
                f"Session state transition: {session_id} "
                f"{old_state.value} → {new_state.value} (user returned)"
            )
        
        # Update session information
        session_info.state = new_state
        session_info.last_interaction_time = timestamp
        
        # Persist to database
        await self._update_session(session_info)
        
        # Update cache
        async with self._cache_lock:
            self._session_cache[session_id] = session_info
        
        logger.debug(
            f"Track interaction: session={session_id}, "
            f"user={user_id}, expert={expert_id}, "
            f"state={new_state.value}"
        )
        
        return session_info
    
    async def check_inactive_sessions(
        self,
        user_id: Optional[str] = None,
        expert_id: Optional[str] = None
    ) -> List[SessionInfo]:
        """
        Check and mark timed-out active sessions as inactive
        
        Args:
            user_id: Optional, only check sessions of specific user
            expert_id: Optional, only check sessions of specific expert
            
        Returns:
            List of newly marked inactive sessions
        """
        current_time = self.time_manager.get_current_time()
        timeout_threshold = current_time - self.inactive_timeout
        
        # Get all active sessions
        active_sessions = await self._get_active_sessions(user_id, expert_id)
        
        newly_inactive = []
        
        for session in active_sessions:
            # Check if timed out
            if session.last_interaction_time < timeout_threshold:
                logger.info(
                    f"Session timeout: {session.session_id} "
                    f"last_interaction={session.last_interaction_time.isoformat()}, "
                    f"timeout_threshold={timeout_threshold.isoformat()}"
                )
                
                # Mark as inactive
                session.state = SessionState.INACTIVE
                await self._update_session(session)
                
                newly_inactive.append(session)
                
                # Remove from cache (force next read from database)
                async with self._cache_lock:
                    self._session_cache.pop(session.session_id, None)
        
        if newly_inactive:
            logger.info(f"Detected {len(newly_inactive)} timed-out sessions")
        
        return newly_inactive
    
    async def mark_inactive_and_trigger_l2(
        self,
        session_id: str,
        user_id: str,
        expert_id: str
    ) -> SessionInfo:
        """
        Manually mark session as inactive and trigger L2 completion
        
        Use case: When user creates new session, immediately mark old session as inactive
        
        Args:
            session_id: Session ID
            user_id: User ID
            expert_id: Expert ID
            
        Returns:
            Updated session information
        """
        session_info = await self._get_session(session_id)
        
        if not session_info:
            logger.warning(f"Attempting to mark non-existent session as inactive: {session_id}")
            # Create session information (already in inactive state)
            session_info = SessionInfo(
                session_id=session_id,
                user_id=user_id,
                expert_id=expert_id,
                state=SessionState.INACTIVE,
                last_interaction_time=self.time_manager.get_current_time(),
                l2_generated=False
            )
            await self._update_session(session_info)
            return session_info
        
        if session_info.state == SessionState.ACTIVE:
            logger.info(f"Manually mark session as inactive: {session_id}")
            session_info.state = SessionState.INACTIVE
            await self._update_session(session_info)
            
            # Remove from cache
            async with self._cache_lock:
                self._session_cache.pop(session_id, None)
        
        return session_info
    
    async def get_pending_l2_sessions(
        self,
        user_id: str,
        expert_id: str
    ) -> List[SessionInfo]:
        """
        Get list of sessions that need L2 memory generation
        
        Filter conditions:
        - State is inactive
        - l2_generated=False
        - Belongs to specified user-expert combination
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            
        Returns:
            List of sessions pending L2 generation
        """
        # Get all inactive sessions that haven't generated L2
        inactive_sessions = await self._get_inactive_sessions(user_id, expert_id)
        
        pending = [
            session for session in inactive_sessions
            if not session.l2_generated
        ]
        
        logger.info(
            f"Pending L2 sessions: user={user_id}, expert={expert_id}, "
            f"total={len(pending)}"
        )
        
        return pending
    
    async def mark_l2_generated(
        self,
        session_id: str,
        l2_memory_id: str
    ) -> None:
        """
        Mark session's L2 memory as generated
        
        Args:
            session_id: Session ID
            l2_memory_id: Generated L2 memory ID
        """
        session_info = await self._get_session(session_id)
        
        if not session_info:
            logger.warning(f"Attempting to mark non-existent session: {session_id}")
            return
        
        session_info.l2_generated = True
        session_info.l2_memory_id = l2_memory_id
        
        await self._update_session(session_info)
        
        logger.info(f"Mark L2 generated: session={session_id}, memory={l2_memory_id}")
    
    async def get_session_info(self, session_id: str) -> Optional[SessionInfo]:
        """
        Get session information
        
        Args:
            session_id: Session ID
            
        Returns:
            Session information, returns None if not exists
        """
        return await self._get_session(session_id)
    
    # ========================================
    # Private methods: Database operations
    # ========================================
    
    async def _get_or_create_session(
        self,
        session_id: str,
        user_id: str,
        expert_id: str,
        timestamp: datetime
    ) -> SessionInfo:
        """Get or create session information"""
        # First query from cache
        async with self._cache_lock:
            if session_id in self._session_cache:
                return self._session_cache[session_id]
        
        # Query from database
        session_info = await self._get_session(session_id)
        
        if not session_info:
            # Create new session
            session_info = SessionInfo(
                session_id=session_id,
                user_id=user_id,
                expert_id=expert_id,
                state=SessionState.ACTIVE,
                last_interaction_time=timestamp,
                l2_generated=False,
                created_at=timestamp
            )
            await self._update_session(session_info)
            logger.info(f"Create new session: {session_id}")
        
        # Update cache
        async with self._cache_lock:
            self._session_cache[session_id] = session_info
        
        return session_info
    
    async def _get_session(self, session_id: str) -> Optional[SessionInfo]:
        """Query session information from database"""
        if not self.db_session:
            # If no database connection, use PostgreSQL version of SessionTracker
            from timem.utils.session_tracker_postgres import get_session_tracker_postgres
            tracker = await get_session_tracker_postgres(self.db_session)
            
            session_data = await tracker.get_session_info(session_id)
            if not session_data:
                return None
            
            return SessionInfo(
                session_id=session_data["id"],
                user_id=session_data["user_id"],
                expert_id=session_data["expert_id"],
                state=SessionState(session_data.get("state", "active")),
                last_interaction_time=session_data.get("last_interaction_time", session_data["start_time"]),
                l2_generated=session_data.get("l2_generated", False),
                l2_memory_id=session_data.get("l2_memory_id"),
                created_at=session_data.get("start_time")
            )
        
        # TODO: Query using db_session
        # Need to implement based on actual database model
        logger.warning("db_session query not implemented, returning None")
        return None
    
    async def _update_session(self, session_info: SessionInfo) -> None:
        """Update session information to database"""
        if not self.db_session:
            # If no database connection, use PostgreSQL version of SessionTracker
            from timem.utils.session_tracker_postgres import get_session_tracker_postgres
            tracker = await get_session_tracker_postgres(self.db_session)
            
            # Update session metadata
            await tracker.update_session_metadata(
                session_info.session_id,
                {
                    "state": session_info.state.value,
                    "last_interaction_time": session_info.last_interaction_time.isoformat(),
                    "l2_generated": session_info.l2_generated,
                    "l2_memory_id": session_info.l2_memory_id
                }
            )
            return
        
        # TODO: Update using db_session
        # Need to implement based on actual database model
        logger.warning("db_session update not implemented")
    
    async def _get_active_sessions(
        self,
        user_id: Optional[str] = None,
        expert_id: Optional[str] = None
    ) -> List[SessionInfo]:
        """Query active sessions"""
        if not self.db_session:
            from timem.utils.session_tracker_postgres import get_session_tracker_postgres
            tracker = await get_session_tracker_postgres(self.db_session)
            
            # Get all active sessions
            all_sessions = await tracker.get_all_active_sessions()
            
            # Filter conditions
            sessions = []
            for session_data in all_sessions:
                if user_id and session_data["user_id"] != user_id:
                    continue
                if expert_id and session_data["expert_id"] != expert_id:
                    continue
                
                # Only keep sessions marked as active
                if session_data.get("state") == "active":
                    sessions.append(SessionInfo(
                        session_id=session_data["id"],
                        user_id=session_data["user_id"],
                        expert_id=session_data["expert_id"],
                        state=SessionState.ACTIVE,
                        last_interaction_time=session_data.get("last_interaction_time", session_data["start_time"]),
                        l2_generated=session_data.get("l2_generated", False),
                        l2_memory_id=session_data.get("l2_memory_id")
                    ))
            
            return sessions
        
        # TODO: Query using db_session
        logger.warning("db_session query for active sessions not implemented, returning empty list")
        return []
    
    async def _get_inactive_sessions(
        self,
        user_id: str,
        expert_id: str
    ) -> List[SessionInfo]:
        """Query inactive sessions"""
        if not self.db_session:
            from timem.utils.session_tracker_postgres import get_session_tracker_postgres
            tracker = await get_session_tracker_postgres(self.db_session)
            
            # Get all sessions for user-expert combination
            all_sessions = await tracker.get_all_sessions(user_id, expert_id)
            
            # Filter inactive sessions
            sessions = []
            for session_data in all_sessions:
                if session_data.get("state") == "inactive":
                    sessions.append(SessionInfo(
                        session_id=session_data["id"],
                        user_id=session_data["user_id"],
                        expert_id=session_data["expert_id"],
                        state=SessionState.INACTIVE,
                        last_interaction_time=session_data.get("last_interaction_time", session_data["start_time"]),
                        l2_generated=session_data.get("l2_generated", False),
                        l2_memory_id=session_data.get("l2_memory_id")
                    ))
            
            return sessions
        
        # TODO: Query using db_session
        logger.warning("db_session query for inactive sessions not implemented, returning empty list")
        return []
    
    async def _check_and_deactivate_other_sessions(
        self,
        user_id: str,
        expert_id: str,
        current_session_id: str
    ) -> None:
        """
        Check and mark other active sessions as inactive
        
        Scenario: When user creates new session under same expert, old sessions should be immediately marked as inactive
        """
        active_sessions = await self._get_active_sessions(user_id, expert_id)
        
        for session in active_sessions:
            if session.session_id != current_session_id:
                logger.info(
                    f"Detected new session creation, marking old session as inactive: "
                    f"old={session.session_id}, new={current_session_id}"
                )
                session.state = SessionState.INACTIVE
                await self._update_session(session)


# Global singleton
_session_state_manager_instance = None
_session_state_manager_lock = asyncio.Lock()


async def get_session_state_manager(
    db_session=None,
    inactive_timeout_minutes: int = 10
) -> SessionStateManager:
    """
    Get session state manager singleton
    
    Args:
        db_session: Database session
        inactive_timeout_minutes: Timeout minutes
        
    Returns:
        SessionStateManager instance
    """
    global _session_state_manager_instance
    
    if _session_state_manager_instance is None:
        async with _session_state_manager_lock:
            if _session_state_manager_instance is None:
                _session_state_manager_instance = SessionStateManager(
                    db_session=db_session,
                    inactive_timeout_minutes=inactive_timeout_minutes
                )
    
    return _session_state_manager_instance

