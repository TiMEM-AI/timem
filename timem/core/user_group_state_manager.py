"""
TiMem User Group State Manager
For persisting and managing state of each (user_id, expert_id) combination

Core Features:
1. CRUD operations on user group state
2. Atomic updates of statistics
3. Maintenance of latest memory references
4. Concurrent-safe state access

Design Principles:
- All operations are atomic
- Support transactional updates
- Provide caching mechanism for performance improvement
"""

import asyncio
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from sqlalchemy import text, select, update, insert
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine
from sqlalchemy.dialects.postgresql import insert as pg_insert

from timem.utils.logging import get_logger
from timem.core.execution_state import ExecutionState

logger = get_logger(__name__)


class UserGroupState:
    """User group state model"""
    
    def __init__(
        self,
        id: str,
        user_id: str,
        expert_id: str,
        last_session_id: Optional[str] = None,
        last_interaction_time: Optional[datetime] = None,
        total_sessions: int = 0,
        total_memories_l1: int = 0,
        total_memories_l2: int = 0,
        total_memories_l3: int = 0,
        total_memories_l4: int = 0,
        total_memories_l5: int = 0,
        latest_l1_memory_id: Optional[str] = None,
        latest_l2_memory_id: Optional[str] = None,
        latest_l3_memory_id: Optional[str] = None,
        latest_l4_memory_id: Optional[str] = None,
        latest_l5_memory_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None
    ):
        self.id = id
        self.user_id = user_id
        self.expert_id = expert_id
        self.last_session_id = last_session_id
        self.last_interaction_time = last_interaction_time
        self.total_sessions = total_sessions
        self.total_memories_l1 = total_memories_l1
        self.total_memories_l2 = total_memories_l2
        self.total_memories_l3 = total_memories_l3
        self.total_memories_l4 = total_memories_l4
        self.total_memories_l5 = total_memories_l5
        self.latest_l1_memory_id = latest_l1_memory_id
        self.latest_l2_memory_id = latest_l2_memory_id
        self.latest_l3_memory_id = latest_l3_memory_id
        self.latest_l4_memory_id = latest_l4_memory_id
        self.latest_l5_memory_id = latest_l5_memory_id
        self.metadata = metadata or {}
        self.created_at = created_at
        self.updated_at = updated_at
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "expert_id": self.expert_id,
            "last_session_id": self.last_session_id,
            "last_interaction_time": self.last_interaction_time.isoformat() if self.last_interaction_time else None,
            "total_sessions": self.total_sessions,
            "total_memories": {
                "L1": self.total_memories_l1,
                "L2": self.total_memories_l2,
                "L3": self.total_memories_l3,
                "L4": self.total_memories_l4,
                "L5": self.total_memories_l5,
                "total": sum([
                    self.total_memories_l1,
                    self.total_memories_l2,
                    self.total_memories_l3,
                    self.total_memories_l4,
                    self.total_memories_l5
                ])
            },
            "latest_memories": {
                "L1": self.latest_l1_memory_id,
                "L2": self.latest_l2_memory_id,
                "L3": self.latest_l3_memory_id,
                "L4": self.latest_l4_memory_id,
                "L5": self.latest_l5_memory_id
            },
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
    
    @classmethod
    def from_db_row(cls, row: Any) -> 'UserGroupState':
        """Create instance from database row"""
        return cls(
            id=row.id if hasattr(row, 'id') else row[0],
            user_id=row.user_id if hasattr(row, 'user_id') else row[1],
            expert_id=row.expert_id if hasattr(row, 'expert_id') else row[2],
            last_session_id=row.last_session_id if hasattr(row, 'last_session_id') else row[3],
            last_interaction_time=row.last_interaction_time if hasattr(row, 'last_interaction_time') else row[4],
            total_sessions=row.total_sessions if hasattr(row, 'total_sessions') else row[5],
            total_memories_l1=row.total_memories_l1 if hasattr(row, 'total_memories_l1') else row[6],
            total_memories_l2=row.total_memories_l2 if hasattr(row, 'total_memories_l2') else row[7],
            total_memories_l3=row.total_memories_l3 if hasattr(row, 'total_memories_l3') else row[8],
            total_memories_l4=row.total_memories_l4 if hasattr(row, 'total_memories_l4') else row[9],
            total_memories_l5=row.total_memories_l5 if hasattr(row, 'total_memories_l5') else row[10],
            latest_l1_memory_id=row.latest_l1_memory_id if hasattr(row, 'latest_l1_memory_id') else row[11],
            latest_l2_memory_id=row.latest_l2_memory_id if hasattr(row, 'latest_l2_memory_id') else row[12],
            latest_l3_memory_id=row.latest_l3_memory_id if hasattr(row, 'latest_l3_memory_id') else row[13],
            latest_l4_memory_id=row.latest_l4_memory_id if hasattr(row, 'latest_l4_memory_id') else row[14],
            latest_l5_memory_id=row.latest_l5_memory_id if hasattr(row, 'latest_l5_memory_id') else row[15],
            metadata=row.metadata if hasattr(row, 'metadata') else (row[16] if len(row) > 16 else {}),
            created_at=row.created_at if hasattr(row, 'created_at') else (row[17] if len(row) > 17 else None),
            updated_at=row.updated_at if hasattr(row, 'updated_at') else (row[18] if len(row) > 18 else None)
        )


class UserGroupStateManager:
    """
    User Group State Manager
    
    Responsible for managing state information of all user-expert groups, including:
    - Last interaction time
    - Statistics
    - Latest memory references
    """
    
    def __init__(self, db_session: AsyncSession):
        """
        Initialize manager
        
        Args:
            db_session: Database session (supports async)
        """
        self.db_session = db_session
        self.logger = get_logger(__name__)
        
        # Memory cache (optional, to reduce database queries)
        self._cache: Dict[str, UserGroupState] = {}
        self._cache_enabled = True
        self._cache_ttl = 300  # 5-minute cache
    
    def _get_cache_key(self, user_id: str, expert_id: str) -> str:
        """Get cache key"""
        return f"{user_id}:{expert_id}"
    
    async def get_state(
        self, 
        user_id: str, 
        expert_id: str,
        use_cache: bool = True
    ) -> Optional[UserGroupState]:
        """
        Get user group state
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            use_cache: Whether to use cache
            
        Returns:
            UserGroupState or None (if not exists)
        """
        cache_key = self._get_cache_key(user_id, expert_id)
        
        # Check cache
        if use_cache and self._cache_enabled and cache_key in self._cache:
            self.logger.debug(f"Get user group state from cache: {cache_key}")
            return self._cache[cache_key]
        
        # Query from database
        try:
            query = text("""
                SELECT id, user_id, expert_id, last_session_id, last_interaction_time,
                       total_sessions, total_memories_l1, total_memories_l2, 
                       total_memories_l3, total_memories_l4, total_memories_l5,
                       latest_l1_memory_id, latest_l2_memory_id, latest_l3_memory_id,
                       latest_l4_memory_id, latest_l5_memory_id, metadata,
                       created_at, updated_at
                FROM user_expert_states
                WHERE user_id = :user_id AND expert_id = :expert_id
            """)
            
            result = await self.db_session.execute(
                query,
                {"user_id": user_id, "expert_id": expert_id}
            )
            row = result.fetchone()
            
            if row:
                state = UserGroupState.from_db_row(row)
                
                # Update cache
                if self._cache_enabled:
                    self._cache[cache_key] = state
                
                self.logger.debug(f"Get user group state from database: {cache_key}")
                return state
            else:
                self.logger.debug(f"User group state does not exist: {cache_key}")
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to get user group state: {e}")
            raise
    
    async def create_or_update_state(
        self,
        user_id: str,
        expert_id: str,
        session_id: Optional[str] = None,
        memory_level: Optional[str] = None,
        memory_id: Optional[str] = None,
        increment_session: bool = False
    ) -> UserGroupState:
        """
        Create or update user group state (atomic operation)
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            session_id: Session ID (optional)
            memory_level: Memory level (L1-L5, optional)
            memory_id: Memory ID (optional)
            increment_session: Whether to increment session count
            
        Returns:
            Updated UserGroupState
        """
        try:
            # Use PostgreSQL ON CONFLICT for upsert
            # Note: This assumes PostgreSQL; MySQL would need different syntax
            
            # Build update fields
            update_fields = {
                "last_interaction_time": datetime.now()
            }
            
            if session_id:
                update_fields["last_session_id"] = session_id
            
            # Build insert initial values
            insert_values = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "expert_id": expert_id,
                "last_session_id": session_id,
                "last_interaction_time": datetime.now(),
                "total_sessions": 1 if increment_session else 0,
                "total_memories_l1": 1 if memory_level == "L1" else 0,
                "total_memories_l2": 1 if memory_level == "L2" else 0,
                "total_memories_l3": 1 if memory_level == "L3" else 0,
                "total_memories_l4": 1 if memory_level == "L4" else 0,
                "total_memories_l5": 1 if memory_level == "L5" else 0,
                "latest_l1_memory_id": memory_id if memory_level == "L1" else None,
                "latest_l2_memory_id": memory_id if memory_level == "L2" else None,
                "latest_l3_memory_id": memory_id if memory_level == "L3" else None,
                "latest_l4_memory_id": memory_id if memory_level == "L4" else None,
                "latest_l5_memory_id": memory_id if memory_level == "L5" else None,
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            }
            
            # Build ON CONFLICT update statement
            query = text("""
                INSERT INTO user_expert_states (
                    id, user_id, expert_id, last_session_id, last_interaction_time,
                    total_sessions, total_memories_l1, total_memories_l2, 
                    total_memories_l3, total_memories_l4, total_memories_l5,
                    latest_l1_memory_id, latest_l2_memory_id, latest_l3_memory_id,
                    latest_l4_memory_id, latest_l5_memory_id, created_at, updated_at
                )
                VALUES (
                    :id, :user_id, :expert_id, :last_session_id, :last_interaction_time,
                    :total_sessions, :total_memories_l1, :total_memories_l2,
                    :total_memories_l3, :total_memories_l4, :total_memories_l5,
                    :latest_l1_memory_id, :latest_l2_memory_id, :latest_l3_memory_id,
                    :latest_l4_memory_id, :latest_l5_memory_id, :created_at, :updated_at
                )
                ON CONFLICT (user_id, expert_id) DO UPDATE SET
                    last_session_id = COALESCE(:last_session_id, user_expert_states.last_session_id),
                    last_interaction_time = :last_interaction_time,
                    total_sessions = user_expert_states.total_sessions + :increment_sessions,
                    total_memories_l1 = user_expert_states.total_memories_l1 + :increment_l1,
                    total_memories_l2 = user_expert_states.total_memories_l2 + :increment_l2,
                    total_memories_l3 = user_expert_states.total_memories_l3 + :increment_l3,
                    total_memories_l4 = user_expert_states.total_memories_l4 + :increment_l4,
                    total_memories_l5 = user_expert_states.total_memories_l5 + :increment_l5,
                    latest_l1_memory_id = COALESCE(:update_l1_id, user_expert_states.latest_l1_memory_id),
                    latest_l2_memory_id = COALESCE(:update_l2_id, user_expert_states.latest_l2_memory_id),
                    latest_l3_memory_id = COALESCE(:update_l3_id, user_expert_states.latest_l3_memory_id),
                    latest_l4_memory_id = COALESCE(:update_l4_id, user_expert_states.latest_l4_memory_id),
                    latest_l5_memory_id = COALESCE(:update_l5_id, user_expert_states.latest_l5_memory_id),
                    updated_at = :last_interaction_time
            """)
            
            # Prepare parameters
            params = {
                **insert_values,
                "increment_sessions": 1 if increment_session else 0,
                "increment_l1": 1 if memory_level == "L1" else 0,
                "increment_l2": 1 if memory_level == "L2" else 0,
                "increment_l3": 1 if memory_level == "L3" else 0,
                "increment_l4": 1 if memory_level == "L4" else 0,
                "increment_l5": 1 if memory_level == "L5" else 0,
                "update_l1_id": memory_id if memory_level == "L1" else None,
                "update_l2_id": memory_id if memory_level == "L2" else None,
                "update_l3_id": memory_id if memory_level == "L3" else None,
                "update_l4_id": memory_id if memory_level == "L4" else None,
                "update_l5_id": memory_id if memory_level == "L5" else None
            }
            
            await self.db_session.execute(query, params)
            await self.db_session.commit()
            
            # Clear cache
            cache_key = self._get_cache_key(user_id, expert_id)
            if cache_key in self._cache:
                del self._cache[cache_key]
            
            # Get updated state
            updated_state = await self.get_state(user_id, expert_id, use_cache=False)
            
            self.logger.info(f"✅ User group state updated: {user_id}:{expert_id}")
            return updated_state
            
        except Exception as e:
            self.logger.error(f"❌ Failed to update user group state: {e}")
            await self.db_session.rollback()
            raise
    
    async def update_after_memory_generation(
        self,
        user_id: str,
        expert_id: str,
        session_id: str,
        memories: List[Dict[str, Any]]
    ) -> UserGroupState:
        """
        Batch update state after memory generation
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            session_id: Session ID
            memories: List of generated memories (includes level and id)
            
        Returns:
            Updated UserGroupState
        """
        try:
            # Count memories by level
            memory_counts = {
                "L1": 0, "L2": 0, "L3": 0, "L4": 0, "L5": 0
            }
            latest_memories = {
                "L1": None, "L2": None, "L3": None, "L4": None, "L5": None
            }
            
            for memory in memories:
                level = memory.get("level")
                memory_id = memory.get("id")
                
                if level in memory_counts:
                    memory_counts[level] += 1
                    latest_memories[level] = memory_id  # Save last one as latest
            
            # Build batch update SQL
            query = text("""
                INSERT INTO user_expert_states (
                    id, user_id, expert_id, last_session_id, last_interaction_time,
                    total_sessions, total_memories_l1, total_memories_l2, 
                    total_memories_l3, total_memories_l4, total_memories_l5,
                    latest_l1_memory_id, latest_l2_memory_id, latest_l3_memory_id,
                    latest_l4_memory_id, latest_l5_memory_id, created_at, updated_at
                )
                VALUES (
                    :id, :user_id, :expert_id, :session_id, :now,
                    0, :count_l1, :count_l2, :count_l3, :count_l4, :count_l5,
                    :latest_l1, :latest_l2, :latest_l3, :latest_l4, :latest_l5,
                    :now, :now
                )
                ON CONFLICT (user_id, expert_id) DO UPDATE SET
                    last_session_id = :session_id,
                    last_interaction_time = :now,
                    total_memories_l1 = user_expert_states.total_memories_l1 + :count_l1,
                    total_memories_l2 = user_expert_states.total_memories_l2 + :count_l2,
                    total_memories_l3 = user_expert_states.total_memories_l3 + :count_l3,
                    total_memories_l4 = user_expert_states.total_memories_l4 + :count_l4,
                    total_memories_l5 = user_expert_states.total_memories_l5 + :count_l5,
                    latest_l1_memory_id = COALESCE(:latest_l1, user_expert_states.latest_l1_memory_id),
                    latest_l2_memory_id = COALESCE(:latest_l2, user_expert_states.latest_l2_memory_id),
                    latest_l3_memory_id = COALESCE(:latest_l3, user_expert_states.latest_l3_memory_id),
                    latest_l4_memory_id = COALESCE(:latest_l4, user_expert_states.latest_l4_memory_id),
                    latest_l5_memory_id = COALESCE(:latest_l5, user_expert_states.latest_l5_memory_id),
                    updated_at = :now
            """)
            
            now = datetime.now()
            params = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "expert_id": expert_id,
                "session_id": session_id,
                "now": now,
                "count_l1": memory_counts["L1"],
                "count_l2": memory_counts["L2"],
                "count_l3": memory_counts["L3"],
                "count_l4": memory_counts["L4"],
                "count_l5": memory_counts["L5"],
                "latest_l1": latest_memories["L1"],
                "latest_l2": latest_memories["L2"],
                "latest_l3": latest_memories["L3"],
                "latest_l4": latest_memories["L4"],
                "latest_l5": latest_memories["L5"]
            }
            
            await self.db_session.execute(query, params)
            await self.db_session.commit()
            
            # Clear cache
            cache_key = self._get_cache_key(user_id, expert_id)
            if cache_key in self._cache:
                del self._cache[cache_key]
            
            self.logger.info(
                f"✅ State updated after memory generation: {user_id}:{expert_id}, "
                f"L1:{memory_counts['L1']}, L2:{memory_counts['L2']}, "
                f"L3:{memory_counts['L3']}, L4:{memory_counts['L4']}, L5:{memory_counts['L5']}"
            )
            
            return await self.get_state(user_id, expert_id, use_cache=False)
            
        except Exception as e:
            self.logger.error(f"❌ Failed to update state after memory generation: {e}")
            await self.db_session.rollback()
            raise
    
    async def get_or_create_state(
        self,
        user_id: str,
        expert_id: str
    ) -> UserGroupState:
        """
        Get or create user group state
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            
        Returns:
            UserGroupState
        """
        state = await self.get_state(user_id, expert_id)
        
        if state is None:
            # Create new state
            state = await self.create_or_update_state(user_id, expert_id)
        
        return state
    
    def clear_cache(self):
        """Clear cache"""
        self._cache.clear()
        self.logger.debug("User group state cache cleared")


# Global singleton manager (optional)
_user_group_state_manager: Optional[UserGroupStateManager] = None
_manager_lock = asyncio.Lock()


async def get_user_group_state_manager(db_session: AsyncSession) -> UserGroupStateManager:
    """
    Get user group state manager instance
    
    Args:
        db_session: Database session
        
    Returns:
        UserGroupStateManager instance
    """
    # Create independent manager instance for each session to avoid session conflicts
    return UserGroupStateManager(db_session)

