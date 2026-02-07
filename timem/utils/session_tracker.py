"""
TiMem Session Tracker

Provides persistent session state management, solving unreliable session ID tracking issues
"""

from typing import Dict, Any, Optional, List, Set, Tuple
from datetime import datetime
import json
import os
import aiosqlite
import asyncio
import logging

from timem.utils.time_manager import get_time_manager

logger = logging.getLogger(__name__)


class SessionTracker:
    """
    Session tracker, persistently stores session state, provides reliable session query interface
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize session tracker
        
        Args:
            db_path: Database path, if None use in-memory database
        """
        self.time_manager = get_time_manager()
        self.db_path = db_path or ":memory:"
        self._lock = asyncio.Lock()
        self._conn: Optional[aiosqlite.Connection] = None
        
    async def _initialize_db(self) -> None:
        """Initialize database connection and tables"""
        async with self._lock:
            if self._conn is None:
                self._conn = await aiosqlite.connect(self.db_path)
                self._conn.row_factory = aiosqlite.Row
                
                async with self._conn.cursor() as cursor:
                    # Create sessions table
                    await cursor.execute('''
                    CREATE TABLE IF NOT EXISTS sessions (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        expert_id TEXT NOT NULL,
                        start_time TEXT NOT NULL,
                        end_time TEXT,
                        is_active INTEGER DEFAULT 1,
                        metadata TEXT
                    )
                    ''')
                    
                    # Create index
                    await cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_sessions_user_expert 
                    ON sessions(user_id, expert_id)
                    ''')
                    
                    # Create processed sessions table (for tracking processed sessions)
                    await cursor.execute('''
                    CREATE TABLE IF NOT EXISTS processed_sessions (
                        session_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        expert_id TEXT NOT NULL,
                        processed_at TEXT NOT NULL
                    )
                    ''')
                    
                    # Create processed sessions index
                    await cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_processed_user_expert 
                    ON processed_sessions(user_id, expert_id)
                    ''')
                
                await self._conn.commit()
    
    async def _ensure_connection(self) -> None:
        """Ensure database connection is valid"""
        if self._conn is None:
            await self._initialize_db()
    
    async def register_session(self, session_id: str, user_id: str, expert_id: str, 
                         start_time: Optional[datetime] = None, 
                         metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Register new session
        
        Args:
            session_id: Session ID
            user_id: User ID
            expert_id: Expert ID
            start_time: Start time, if None use current time
            metadata: Session metadata
        """
        await self._ensure_connection()
        
        if start_time is None:
            start_time = self.time_manager.get_current_time()
            
        start_time_str = start_time.isoformat()
        metadata_str = json.dumps(metadata) if metadata else "{}"
        
        async with self._lock:
            async with self._conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)) as cursor:
                existing = await cursor.fetchone()
            
            if existing:
                await self._conn.execute(
                    """UPDATE sessions 
                    SET user_id = ?, expert_id = ?, start_time = ?, is_active = 1, metadata = ? 
                    WHERE id = ?""",
                    (user_id, expert_id, start_time_str, metadata_str, session_id)
                )
            else:
                await self._conn.execute(
                    """INSERT INTO sessions 
                    (id, user_id, expert_id, start_time, is_active, metadata) 
                    VALUES (?, ?, ?, ?, 1, ?)""",
                    (session_id, user_id, expert_id, start_time_str, metadata_str)
                )
                
            await self._conn.commit()
            logger.debug(f"Session registered {session_id} (user: {user_id}, expert: {expert_id})")
    
    async def close_session(self, session_id: str, end_time: Optional[datetime] = None) -> None:
        """
        Close session
        
        Args:
            session_id: Session ID
            end_time: End time, if None use current time
        """
        await self._ensure_connection()
        
        if end_time is None:
            end_time = self.time_manager.get_current_time()
            
        end_time_str = end_time.isoformat()
        
        async with self._lock:
            await self._conn.execute(
                "UPDATE sessions SET end_time = ?, is_active = 0 WHERE id = ?",
                (end_time_str, session_id)
            )
            await self._conn.commit()
            logger.debug(f"Session closed {session_id}")
    
    async def mark_session_processed(self, session_id: str, user_id: str, expert_id: str) -> None:
        """
        Mark session as processed
        
        Args:
            session_id: Session ID
            user_id: User ID
            expert_id: Expert ID
        """
        await self._ensure_connection()
        
        processed_at = self.time_manager.get_current_time().isoformat()
        
        async with self._lock:
            async with self._conn.execute("SELECT session_id FROM processed_sessions WHERE session_id = ?", (session_id,)) as cursor:
                existing = await cursor.fetchone()
            
            if not existing:
                await self._conn.execute(
                    """INSERT INTO processed_sessions 
                    (session_id, user_id, expert_id, processed_at) 
                    VALUES (?, ?, ?, ?)""",
                    (session_id, user_id, expert_id, processed_at)
                )
                await self._conn.commit()
                logger.debug(f"Session {session_id} marked as processed")
    
    async def is_session_processed(self, session_id: str) -> bool:
        """
        Check if session has been processed
        
        Args:
            session_id: Session ID
            
        Returns:
            Whether session has been processed
        """
        await self._ensure_connection()
        
        async with self._lock:
            async with self._conn.execute("SELECT session_id FROM processed_sessions WHERE session_id = ?", (session_id,)) as cursor:
                return await cursor.fetchone() is not None
    
    async def is_new_session(self, user_id: str, expert_id: str, session_id: str) -> bool:
        """
        Check if session is new.
        
        Logic:
        1. If no sessions exist for this user-expert combination, current session is new
        2. If sessions exist for this user-expert combination and current session ID is not in processed list, current session is new
        3. This ensures first session is correctly identified as new, meeting TiMem architecture requirements
        """
        await self._ensure_connection()
        
        async with self._lock:
            # First check if any sessions exist for this user-expert combination
            async with self._conn.execute(
                "SELECT COUNT(*) as count FROM sessions WHERE user_id = ? AND expert_id = ?", 
                (user_id, expert_id)
            ) as cursor:
                row = await cursor.fetchone()
                total_sessions = row['count'] if row else 0
            
            if total_sessions == 0:
                # No sessions exist for this user-expert combination, current session is new
                return True
            
            # Check if current session has been processed
            async with self._conn.execute(
                "SELECT COUNT(*) as count FROM processed_sessions WHERE session_id = ?", 
                (session_id,)
            ) as cursor:
                row = await cursor.fetchone()
                is_processed = row['count'] > 0 if row else False
            
            # If current session has not been processed, it is new
            return not is_processed
    
    async def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get session information
        
        Args:
            session_id: Session ID
            
        Returns:
            Session information, or None if not exists
        """
        await self._ensure_connection()
        
        async with self._lock:
            async with self._conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)) as cursor:
                row = await cursor.fetchone()
            
            if not row:
                return None
                
            metadata = json.loads(row['metadata']) if row['metadata'] else {}
            
            return {
                'id': row['id'],
                'user_id': row['user_id'],
                'expert_id': row['expert_id'],
                'start_time': self.time_manager.parse_iso_time(row['start_time']),
                'end_time': self.time_manager.parse_iso_time(row['end_time']) if row['end_time'] else None,
                'is_active': bool(row['is_active']),
                'metadata': metadata
            }
    
    async def get_previous_session(self, user_id: str, expert_id: str, 
                             current_session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get previous session
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            current_session_id: Current session ID, exclude this session if provided
            
        Returns:
            Previous session information, or None if not exists
        """
        await self._ensure_connection()
        
        async with self._lock:
            if current_session_id:
                query = "SELECT * FROM sessions WHERE user_id = ? AND expert_id = ? AND id != ? ORDER BY start_time DESC LIMIT 1"
                params = (user_id, expert_id, current_session_id)
            else:
                query = "SELECT * FROM sessions WHERE user_id = ? AND expert_id = ? ORDER BY start_time DESC LIMIT 1"
                params = (user_id, expert_id)
                
            async with self._conn.execute(query, params) as cursor:
                row = await cursor.fetchone()
            
            if not row:
                return None
                
            metadata = json.loads(row['metadata']) if row['metadata'] else {}
            
            return {
                'id': row['id'],
                'user_id': row['user_id'],
                'expert_id': row['expert_id'],
                'start_time': self.time_manager.parse_iso_time(row['start_time']),
                'end_time': self.time_manager.parse_iso_time(row['end_time']) if row['end_time'] else None,
                'is_active': bool(row['is_active']),
                'metadata': metadata
            }
    
    async def get_previous_session_id(self, user_id: str, expert_id: str, 
                               current_session_id: Optional[str] = None) -> Optional[str]:
        """
        Get previous session ID
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            current_session_id: Current session ID, exclude this session if provided
            
        Returns:
            Previous session ID, or None if not exists
        """
        previous_session = await self.get_previous_session(user_id, expert_id, current_session_id)
        return previous_session['id'] if previous_session else None
    
    async def get_sessions_by_date(self, user_id: str, expert_id: str, 
                            target_date: datetime) -> List[Dict[str, Any]]:
        """
        Get sessions for specific date
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            target_date: Target date
            
        Returns:
            Session list
        """
        await self._ensure_connection()
        
        day_start = self.time_manager.get_day_start(target_date).isoformat()
        day_end = self.time_manager.get_day_end(target_date).isoformat()
        
        async with self._lock:
            async with self._conn.execute(
                """SELECT * FROM sessions 
                WHERE user_id = ? AND expert_id = ? 
                AND start_time >= ? AND start_time <= ? 
                ORDER BY start_time ASC""",
                (user_id, expert_id, day_start, day_end)
            ) as cursor:
                rows = await cursor.fetchall()
            
            result = []
            
            for row in rows:
                metadata = json.loads(row['metadata']) if row['metadata'] else {}
                
                session_info = {
                    'id': row['id'],
                    'user_id': row['user_id'],
                    'expert_id': row['expert_id'],
                    'start_time': self.time_manager.parse_iso_time(row['start_time']),
                    'end_time': self.time_manager.parse_iso_time(row['end_time']) if row['end_time'] else None,
                    'is_active': bool(row['is_active']),
                    'metadata': metadata
                }
                result.append(session_info)
                
            return result
    
    async def find_session_by_date(self, user_id: str, expert_id: str, 
                           target_date: datetime) -> Optional[Dict[str, Any]]:
        """
        Find session for specific date
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            target_date: Target date
            
        Returns:
            Session information, or None if not exists
        """
        sessions = await self.get_sessions_by_date(user_id, expert_id, target_date)
        return sessions[0] if sessions else None
    
    async def find_session_id_by_date(self, user_id: str, expert_id: str, 
                               target_date: datetime) -> Optional[str]:
        """
        Find session ID for specific date
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            target_date: Target date
            
        Returns:
            Session ID, or None if not exists
        """
        session = await self.find_session_by_date(user_id, expert_id, target_date)
        return session['id'] if session else None
    
    async def get_all_sessions(self, user_id: str, expert_id: str, 
                        limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get all sessions list
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            limit: Limit count, default 100
            
        Returns:
            Session list
        """
        await self._ensure_connection()
        
        async with self._lock:
            async with self._conn.execute(
                """SELECT * FROM sessions 
                WHERE user_id = ? AND expert_id = ? 
                ORDER BY start_time DESC LIMIT ?""",
                (user_id, expert_id, limit)
            ) as cursor:
                rows = await cursor.fetchall()

            result = []
            
            for row in rows:
                metadata = json.loads(row['metadata']) if row['metadata'] else {}
                
                session_info = {
                    'id': row['id'],
                    'user_id': row['user_id'],
                    'expert_id': row['expert_id'],
                    'start_time': self.time_manager.parse_iso_time(row['start_time']),
                    'end_time': self.time_manager.parse_iso_time(row['end_time']) if row['end_time'] else None,
                    'is_active': bool(row['is_active']),
                    'metadata': metadata
                }
                result.append(session_info)
                
            return result
    
    async def get_active_sessions(self, user_id: str, expert_id: str) -> List[Dict[str, Any]]:
        """
        Get active sessions list
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            
        Returns:
            Active sessions list
        """
        await self._ensure_connection()
        
        async with self._lock:
            async with self._conn.execute(
                """SELECT * FROM sessions 
                WHERE user_id = ? AND expert_id = ? AND is_active = 1 
                ORDER BY start_time DESC""",
                (user_id, expert_id)
            ) as cursor:
                rows = await cursor.fetchall()

            result = []
            
            for row in rows:
                metadata = json.loads(row['metadata']) if row['metadata'] else {}
                
                session_info = {
                    'id': row['id'],
                    'user_id': row['user_id'],
                    'expert_id': row['expert_id'],
                    'start_time': self.time_manager.parse_iso_time(row['start_time']),
                    'end_time': self.time_manager.parse_iso_time(row['end_time']) if row['end_time'] else None,
                    'is_active': bool(row['is_active']),
                    'metadata': metadata
                }
                result.append(session_info)
                
            return result
    
    async def update_session_metadata(self, session_id: str, metadata: Dict[str, Any]) -> None:
        """
        Update session metadata
        
        Args:
            session_id: Session ID
            metadata: Metadata
        """
        await self._ensure_connection()
        
        async with self._lock:
            async with self._conn.execute("SELECT metadata FROM sessions WHERE id = ?", (session_id,)) as cursor:
                row = await cursor.fetchone()
            
            if row:
                existing_metadata = json.loads(row['metadata']) if row['metadata'] else {}
                updated_metadata = {**existing_metadata, **metadata}
                
                await self._conn.execute(
                    "UPDATE sessions SET metadata = ? WHERE id = ?",
                    (json.dumps(updated_metadata), session_id)
                )
                await self._conn.commit()
                logger.debug(f"Session {session_id} metadata updated")
    
    async def close(self) -> None:
        """Close database connection"""
        async with self._lock:
            if self._conn:
                await self._conn.close()
                self._conn = None


# Global session tracker instance
_session_tracker_instance = None
_session_tracker_lock = asyncio.Lock()

async def get_session_tracker(db_path: Optional[str] = None) -> SessionTracker:
    """
    Get global session tracker instance
    
    Args:
        db_path: Database path, if None use default path
        
    Returns:
        Session tracker instance
    """
    global _session_tracker_instance
    if _session_tracker_instance is None:
        async with _session_tracker_lock:
            if _session_tracker_instance is None:
                if db_path is None:
                    # Default database path
                    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    db_path = os.path.join(base_dir, "..", "data", "session_tracker.db")
                    
                    # Ensure directory exists
                    os.makedirs(os.path.dirname(db_path), exist_ok=True)
                    
                _session_tracker_instance = SessionTracker(db_path)
                await _session_tracker_instance._initialize_db()
    return _session_tracker_instance
