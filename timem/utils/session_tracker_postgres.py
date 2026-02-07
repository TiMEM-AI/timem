"""
TiMem Session Tracker - PostgreSQL Version

Provides database-level atomic turn number operations, solves turn number duplication in concurrent scenarios

Core Features:
1. Atomic turn number increment
2. Session creation and management
3. Concurrent-safe state tracking

Design Principles:
- Use SELECT FOR UPDATE to implement row locking
- Transactional operations ensure atomicity
- Support high concurrency scenarios
"""

import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from timem.utils.logging import get_logger
from timem.utils.time_manager import get_time_manager

logger = get_logger(__name__)


class SessionTrackerPostgres:
    """
    PostgreSQL-based session tracker
    
    Provides database-level atomic operations, ensures concurrent safety
    """
    
    def __init__(self, db_session: AsyncSession):
        """
        Initialize session tracker
        
        Args:
            db_session: Database session (supports async)
        """
        self.db_session = db_session
        self.time_manager = get_time_manager()
        self.logger = get_logger(__name__)
    
    async def get_next_turn_number_atomic(
        self,
        session_id: str,
        user_id: str,
        expert_id: str
    ) -> int:
        """
        Atomically get next turn number
        
        Uses database row locking (SELECT FOR UPDATE) to ensure concurrent safety
        
        Args:
            session_id: Session ID
            user_id: User ID
            expert_id: Expert ID
            
        Returns:
            Next turn number
            
        Raises:
            ValueError: If session does not exist
        """
        try:
            # Key: Use SELECT FOR UPDATE to add row lock
            query = text("""
                SELECT turn_counter
                FROM memory_sessions 
                WHERE id = :session_id 
                AND user_id = :user_id 
                AND expert_id = :expert_id
                FOR UPDATE
            """)
            
            result = await self.db_session.execute(
                query,
                {
                    "session_id": session_id,
                    "user_id": user_id,
                    "expert_id": expert_id
                }
            )
            row = result.fetchone()
            
            if not row:
                # Session does not exist, raise exception
                raise ValueError(
                    f"Session does not exist: session_id={session_id}, "
                    f"user_id={user_id}, expert_id={expert_id}"
                )
            
            current_turn = row[0] or 0
            next_turn = current_turn + 1
            
            # Atomically update turn_counter
            update_query = text("""
                UPDATE memory_sessions 
                SET turn_counter = :next_turn,
                    updated_at = :now
                WHERE id = :session_id
            """)
            
            await self.db_session.execute(
                update_query,
                {
                    "next_turn": next_turn,
                    "now": datetime.now(),
                    "session_id": session_id
                }
            )
            
            # Commit transaction (release row lock)
            await self.db_session.commit()
            
            self.logger.debug(
                f"✅ Atomically get turn number: {session_id} -> {next_turn} "
                f"(user={user_id}, expert={expert_id})"
            )
            
            return next_turn
            
        except ValueError:
            # Session does not exist, raise upward
            raise
        except Exception as e:
            self.logger.error(f"❌ Atomically get turn number failed: {e}")
            await self.db_session.rollback()
            raise
    
    async def register_session(
        self,
        session_id: str,
        user_id: str,
        expert_id: str,
        start_time: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Register new session
        
        Args:
            session_id: Session ID
            user_id: User ID
            expert_id: Expert ID
            start_time: Start time (optional, default current time)
            metadata: Metadata (optional)
            
        Returns:
            Whether registration was successful (returns False if already exists)
        """
        try:
            if start_time is None:
                start_time = self.time_manager.get_current_time()
            
            query = text("""
                INSERT INTO memory_sessions (
                    id, user_id, expert_id, start_time, 
                    is_active, turn_counter, created_at, updated_at
                )
                VALUES (
                    :id, :user_id, :expert_id, :start_time,
                    true, 0, :now, :now
                )
                ON CONFLICT (id) DO NOTHING
            """)
            
            now = datetime.now()
            result = await self.db_session.execute(
                query,
                {
                    "id": session_id,
                    "user_id": user_id,
                    "expert_id": expert_id,
                    "start_time": start_time,
                    "now": now
                }
            )
            
            await self.db_session.commit()
            
            # Check if insert was successful (rowcount > 0 means insert succeeded)
            success = result.rowcount > 0
            
            if success:
                self.logger.info(f"✅ Session registered: {session_id}")
            else:
                self.logger.debug(f"⚠️ Session already exists: {session_id}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"❌ Register session failed: {e}")
            await self.db_session.rollback()
            raise
    
    async def get_session(
        self,
        session_id: str,
        user_id: str,
        expert_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get session information
        
        Args:
            session_id: Session ID
            user_id: User ID
            expert_id: Expert ID
            
        Returns:
            Session information dictionary, returns None if not exists
        """
        try:
            query = text("""
                SELECT id, user_id, expert_id, start_time, end_time,
                       is_active, turn_counter, created_at, updated_at
                FROM memory_sessions
                WHERE id = :session_id 
                AND user_id = :user_id 
                AND expert_id = :expert_id
            """)
            
            result = await self.db_session.execute(
                query,
                {
                    "session_id": session_id,
                    "user_id": user_id,
                    "expert_id": expert_id
                }
            )
            row = result.fetchone()
            
            if row:
                return {
                    "id": row[0],
                    "user_id": row[1],
                    "expert_id": row[2],
                    "start_time": row[3],
                    "end_time": row[4],
                    "is_active": row[5],
                    "turn_counter": row[6],
                    "created_at": row[7],
                    "updated_at": row[8]
                }
            return None
            
        except Exception as e:
            self.logger.error(f"❌ Get session failed: {e}")
            raise
    
    async def update_session_turn_counter(
        self,
        session_id: str,
        turn_number: int
    ) -> bool:
        """
        Update session's turn_counter (non-atomic operation, only for correction)
        
        Args:
            session_id: Session ID
            turn_number: New turn number
            
        Returns:
            Whether update was successful
        """
        try:
            query = text("""
                UPDATE memory_sessions 
                SET turn_counter = :turn_number,
                    updated_at = :now
                WHERE id = :session_id
            """)
            
            result = await self.db_session.execute(
                query,
                {
                    "turn_number": turn_number,
                    "now": datetime.now(),
                    "session_id": session_id
                }
            )
            
            await self.db_session.commit()
            
            return result.rowcount > 0
            
        except Exception as e:
            self.logger.error(f"❌ Update turn_counter failed: {e}")
            await self.db_session.rollback()
            raise
    
    async def close_session(
        self,
        session_id: str,
        user_id: str,
        expert_id: str
    ) -> bool:
        """
        Close session
        
        Args:
            session_id: Session ID
            user_id: User ID
            expert_id: Expert ID
            
        Returns:
            Whether close was successful
        """
        try:
            query = text("""
                UPDATE memory_sessions 
                SET is_active = false,
                    end_time = :now,
                    updated_at = :now
                WHERE id = :session_id 
                AND user_id = :user_id 
                AND expert_id = :expert_id
            """)
            
            now = datetime.now()
            result = await self.db_session.execute(
                query,
                {
                    "now": now,
                    "session_id": session_id,
                    "user_id": user_id,
                    "expert_id": expert_id
                }
            )
            
            await self.db_session.commit()
            
            success = result.rowcount > 0
            
            if success:
                self.logger.info(f"✅ Session closed: {session_id}")
            else:
                self.logger.warning(f"⚠️ Session does not exist or cannot be closed: {session_id}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"❌ Close session failed: {e}")
            await self.db_session.rollback()
            raise
    
    async def get_active_sessions(
        self,
        user_id: str,
        expert_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get list of active sessions
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            
        Returns:
            Session list
        """
        try:
            query = text("""
                SELECT id, user_id, expert_id, start_time, turn_counter,
                       created_at, updated_at
                FROM memory_sessions
                WHERE user_id = :user_id 
                AND expert_id = :expert_id
                AND is_active = true
                ORDER BY start_time DESC
            """)
            
            result = await self.db_session.execute(
                query,
                {"user_id": user_id, "expert_id": expert_id}
            )
            rows = result.fetchall()
            
            return [
                {
                    "id": row[0],
                    "user_id": row[1],
                    "expert_id": row[2],
                    "start_time": row[3],
                    "turn_counter": row[4],
                    "created_at": row[5],
                    "updated_at": row[6]
                }
                for row in rows
            ]
            
        except Exception as e:
            self.logger.error(f"❌ Get active sessions failed: {e}")
            raise
    
    async def get_all_sessions(
        self,
        user_id: str,
        expert_id: str,
        include_inactive: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get all sessions list (including active and inactive)
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            include_inactive: Whether to include inactive sessions, default True
            
        Returns:
            Session list
        """
        try:
            if include_inactive:
                query = text("""
                    SELECT id, user_id, expert_id, start_time, end_time, 
                           is_active, turn_counter, created_at, updated_at
                    FROM memory_sessions
                    WHERE user_id = :user_id 
                    AND expert_id = :expert_id
                    ORDER BY start_time DESC
                """)
            else:
                query = text("""
                    SELECT id, user_id, expert_id, start_time, end_time,
                           is_active, turn_counter, created_at, updated_at
                    FROM memory_sessions
                    WHERE user_id = :user_id 
                    AND expert_id = :expert_id
                    AND is_active = true
                    ORDER BY start_time DESC
                """)
            
            result = await self.db_session.execute(
                query,
                {"user_id": user_id, "expert_id": expert_id}
            )
            rows = result.fetchall()
            
            return [
                {
                    "id": row[0],
                    "user_id": row[1],
                    "expert_id": row[2],
                    "start_time": row[3],
                    "end_time": row[4],
                    "is_active": row[5],
                    "turn_counter": row[6],
                    "created_at": row[7],
                    "updated_at": row[8]
                }
                for row in rows
            ]
            
        except Exception as e:
            self.logger.error(f"❌ Get all sessions failed: {e}")
            raise


# Global instance management (optional)
async def get_session_tracker_postgres(db_session: AsyncSession) -> SessionTrackerPostgres:
    """
    Get PostgreSQL session tracker instance
    
    Args:
        db_session: Database session
        
    Returns:
        SessionTrackerPostgres instance
    """
    return SessionTrackerPostgres(db_session)

