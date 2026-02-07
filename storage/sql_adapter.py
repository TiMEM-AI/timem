"""
SQL Adapter V3 - LEGACY/BACKUP Version
Adapted for new multi-table SQL schema and Memory V3 model

⚠️  Warning: This module is marked as LEGACY backup version
📌 Current status: Backup/backward compatibility support
🎯 Main adapter: PostgreSQL (storage/postgres_adapter.py)
🔄 Switching method: Modify sql.provider to "mysql" in config/settings.yaml

📅 Legacy annotation date: 2025-09-01
📝 Legacy reason: Successfully migrated to PostgreSQL, MySQL adapter kept as backup plan
"""
import logging
from typing import Any, Dict, List, Optional

from timem.models.memory import (Memory, MemoryLevel, create_memory_by_level, FragmentMemory)
from storage.sql_store import SQLStore
from storage.storage_adapter import StorageAdapter
from timem.utils.logging import get_logger

logger = get_logger(__name__)

class SQLAdapter(StorageAdapter):
    """
    SQL Storage Adapter V3 - LEGACY/BACKUP Version
    
    ⚠️  This class is marked as LEGACY backup version
    🎯 Current main adapter: PostgreSQLAdapter
    
    - Responsible for converting between Memory V3 Pydantic model and flat dictionaries required by SQLStore V3.
    - Kept for backward compatibility and emergency rollback support
    """

    def __init__(self, sql_store: SQLStore):
        if not isinstance(sql_store, SQLStore):
            raise TypeError(f"sql_store must be an instance of SQLStore, not {type(sql_store)}")
        self._sql_store = sql_store
        logger.info("SQLAdapter V3 initialized.")
    
    # ==================== Unified interface proxy methods ====================
    
    async def get_data_statistics(self) -> Dict[str, Any]:
        """Get data statistics"""
        return await self._sql_store.get_data_statistics()
    
    async def fulltext_search(self,
                            query_text: str,
                            user_id: Optional[str] = None,
                            expert_id: Optional[str] = None,
                            level: Optional[str] = None,
                            limit: int = 20,
                            min_score: float = 0.0) -> List[Dict[str, Any]]:
        """Full-text search (MySQL uses LIKE simulation)"""
        return await self._sql_store.fulltext_search(
            query_text=query_text,
            user_id=user_id,
            expert_id=expert_id,
            level=level,
            limit=limit,
            min_score=min_score
        )
    
    async def search_memories(self, 
                            query_text: Optional[str] = None,
                            user_id: Optional[str] = None,
                            expert_id: Optional[str] = None,
                            level: Optional[str] = None,
                            limit: int = 20) -> List[Dict[str, Any]]:
        """Search memories"""
        return await self._sql_store.search_memories(
            query_text=query_text,
            user_id=user_id,
            expert_id=expert_id,
            level=level,
            limit=limit
        )
    
    async def find_memories_by_criteria(self, **criteria) -> List[Dict[str, Any]]:
        """Find memories by criteria"""
        return await self._sql_store.find_memories_by_criteria(**criteria)
    
    async def create_session(self, user_id: str, expert_id: str, session_id: Optional[str] = None) -> str:
        """Create session"""
        return await self._sql_store.create_session(user_id, expert_id, session_id)
    
    async def get_session_memories(self, session_id: str, level: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get session-related memories"""
        return await self._sql_store.get_session_memories(session_id, level)

    def _memory_to_db_record(self, memory: Memory) -> Dict[str, Any]:
        """Convert V3 Memory Pydantic model to flat dictionary required by SQLStore V3."""
        # Add debug info to confirm time window values
        logger.info(f"🔍 [SQLAdapter] Converting memory object: id={memory.id}, level={memory.level}")
        logger.info(f"🔍 [SQLAdapter] Memory object time window: {memory.time_window_start} to {memory.time_window_end}")
        
        # Key: Use python mode to preserve native types like datetime, avoid string comparison in SQL layer
        db_record = memory.model_dump(mode='python', exclude_none=True)

        # level is already a string enum, use directly
        db_record['level'] = memory.level.value
        
        # Special handling for L1 dialogue_turns
        if isinstance(memory, FragmentMemory):
            db_record['dialogue_turns_json'] = db_record.pop('dialogue_turns', None)

        # Add debug info to confirm converted time window
        logger.info(f"🔍 [SQLAdapter] Converted time window: {db_record.get('time_window_start')} to {db_record.get('time_window_end')}")
        
        logger.debug(f"Converted Memory (ID: {memory.id}) to DB record for SQLStore.")
        return db_record

    def _db_record_to_memory(self, db_record: Dict[str, Any]) -> Memory:
        """Convert flat dictionary from SQLStore V3 to V3 Memory Pydantic model."""
        if not db_record:
            raise ValueError("Cannot convert an empty dictionary to a Memory object.")

        # Convert dialogue_turns_json back to dialogue_turns
        if 'dialogue_turns_json' in db_record:
            db_record['dialogue_turns'] = db_record.pop('dialogue_turns_json')
        elif db_record.get('level') == 'L1' and 'dialogue_turns' not in db_record:
            # Provide default dialogue_turns field for L1 memory
            db_record['dialogue_turns'] = []

        # Clean up deprecated fields (if still passed from upstream)
        db_record.pop('metadata', None)
        memory_obj = create_memory_by_level(**db_record)
        
        logger.debug(f"Converted DB record (ID: {db_record.get('id')}) to Memory object.")
        return memory_obj

    async def store_memory(
        self, 
        memory: Memory,
        execution_state: Optional['ExecutionState'] = None  # ✅ Add execution_state parameter to keep interface consistent
    ) -> bool:
        """Store a single memory."""
        # (This method is not used by batch_store_memories, but kept for single-store use cases)
        try:
            db_record = self._memory_to_db_record(memory)
            # a single store is a batch of one
            ids = await self._sql_store.batch_store_memories([db_record])
            if ids:
                logger.info(f"Successfully stored memory {ids[0]} (Level: {memory.level.value}).")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to store memory {getattr(memory, 'id', 'N/A')}: {str(e)}", exc_info=True)
            return False

    async def batch_store_memories(
        self, 
        memories: List[Memory],
        execution_state: Optional['ExecutionState'] = None  # ✅ Add execution_state parameter to keep interface consistent
    ) -> bool:
        """Batch store memories."""
        if not memories:
            return True
        try:
            db_records = [self._memory_to_db_record(mem) for mem in memories]
            ids = await self._sql_store.batch_store_memories(db_records)
            if len(ids) == len(memories):
                logger.info(f"Successfully stored a batch of {len(memories)} memories.")
                return True
            logger.warning(f"Batch store partially failed. Stored {len(ids)} of {len(memories)}.")
            return False
        except Exception as e:
            logger.error(f"Failed to batch store memories: {e}", exc_info=True)
            return False

    async def retrieve_memory(self, memory_id: str) -> Optional[Memory]:
        """Retrieve a single complete memory by ID."""
        try:
            db_record = await self._sql_store.get_full_memory_by_id(memory_id)
            if db_record:
                return self._db_record_to_memory(db_record)
            logger.warning(f"Memory with ID {memory_id} not found.")
            return None
        except Exception as e:
            logger.error(f"Failed to retrieve memory {memory_id}: {e}", exc_info=True)
            return None

    async def update_memory(self, memory_id: str, updates: Dict[str, Any]) -> bool:
        """Update specified memory."""
        try:
            success = await self._sql_store.update_memory(memory_id, updates)
            if success:
                logger.info(f"Successfully updated memory {memory_id}.")
            else:
                logger.warning(f"Update failed for memory {memory_id}, it may not exist.")
            return success
        except Exception as e:
            logger.error(f"Failed to update memory {memory_id}: {e}", exc_info=True)
            return False

    async def search_memories(self, query: Optional[Dict[str, Any]] = None, options: Optional[Dict[str, Any]] = None, **kwargs) -> List[Memory]:
        """Search memories by arbitrary conditions (unified interface). Compatible with old signature passing bare parameters (kwargs).
        Note: Need to pass time window (start_time/end_time) from options to SQL layer for filtering.
        """
        try:
            criteria: Dict[str, Any] = {}
            if isinstance(query, dict):
                criteria.update(query)
            if kwargs:
                criteria.update(kwargs)
            # Merge options into criteria, especially time window
            if isinstance(options, dict):
                tm = None
                try:
                    from timem.utils.time_manager import get_time_manager
                    tm = get_time_manager()
                except Exception:
                    tm = None
                # Only pass filter keys supported by SQLStore
                if "start_time" in options and options["start_time"]:
                    start_raw = options["start_time"]
                    if isinstance(start_raw, str) and tm:
                        try:
                            start_raw = tm.parse_iso_time(start_raw)
                        except Exception:
                            pass
                    criteria["start_time"] = start_raw
                if "end_time" in options and options["end_time"]:
                    end_raw = options["end_time"]
                    if isinstance(end_raw, str) and tm:
                        try:
                            end_raw = tm.parse_iso_time(end_raw)
                        except Exception:
                            pass
                    criteria["end_time"] = end_raw
                if "limit" in options and options["limit"]:
                    criteria["limit"] = options["limit"]

            # Handle layer parameter - convert it to level (unified parameter name)
            if "layer" in criteria and "level" not in criteria:
                criteria["level"] = criteria.pop("layer")
            
            db_records = await self._sql_store.find_memories(**criteria)
            return [self._db_record_to_memory(rec) for rec in db_records]
        except Exception as e:
            logger.error(f"Failed to search memories with criteria {query or kwargs} and options {options}: {str(e)}", exc_info=True)
            return []

    async def delete_memory(self, memory_id: str) -> bool:
        """Hard delete a memory from database."""
        try:
            success = await self._sql_store.delete_memory(memory_id)
            if success:
                logger.info(f"Successfully hard-deleted memory {memory_id}.")
            else:
                logger.warning(f"Hard delete failed for memory {memory_id}, it may not exist.")
            return success
        except Exception as e:
            logger.error(f"Failed to hard-delete memory {memory_id}: {e}", exc_info=True)
            return False

    async def delete_memories_by_user_expert(self, user_id: str, expert_id: str) -> bool:
        """Delete all memories for specified user and expert."""
        try:
            # First search all matching memories
            memories = await self.search_memories(user_id=user_id, expert_id=expert_id)
            if not memories:
                logger.info(f"No memories found for user {user_id} and expert {expert_id}.")
                return True
            
            # Delete memories one by one
            deleted_count = 0
            for memory in memories:
                try:
                    success = await self.delete_memory(memory.id)
                    if success:
                        deleted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete memory {memory.id}: {e}")
            
            logger.info(f"Successfully deleted {deleted_count}/{len(memories)} memories for user {user_id} and expert {expert_id}.")
            return deleted_count == len(memories)
        except Exception as e:
            logger.error(f"Failed to delete memories for user {user_id} and expert {expert_id}: {e}", exc_info=True)
            return False

    async def clear_all_data(self) -> bool:
        """Delete all data (mainly for testing)."""
        try:
            await self._sql_store.clear_all_data()
            logger.info("Successfully cleared all data from SQL storage via adapter.")
            return True
        except Exception as e:
            logger.error(f"Failed to clear all data: {e}", exc_info=True)
            return False

    async def is_available(self) -> bool:
        return self._sql_store._is_available

    async def connect(self):
        await self._sql_store.connect()

    async def disconnect(self):
        await self._sql_store.close()

    async def get_memory_by_id(self, memory_id: str, level: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get memory by ID and level"""
        try:
            db_record = await self._sql_store.get_memory_by_id(memory_id, level)
            if db_record:
                return self._db_record_to_memory(db_record).model_dump(mode='json')
            logger.warning(f"Memory with ID {memory_id} not found.")
            return None
        except Exception as e:
            logger.error(f"Failed to retrieve memory {memory_id}: {e}", exc_info=True)
            return None

    async def query_memories_by_session(self, user_id: str, expert_id: str, session_id: str, level: str) -> List[Dict[str, Any]]:
        """Query memories of specific level by session ID"""
        try:
            db_records = await self._sql_store.query_memories_by_session(user_id, expert_id, session_id, level)
            return [self._db_record_to_memory(rec).model_dump(mode='json') for rec in db_records]
        except Exception as e:
            logger.error(f"Failed to query memories by session: {e}", exc_info=True)
            return []

    async def query_latest_memories(self, user_id: str, expert_id: str, level: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Query latest memories"""
        try:
            db_records = await self._sql_store.query_latest_memories(user_id, expert_id, level, limit)
            return [self._db_record_to_memory(rec).model_dump(mode='json') for rec in db_records]
        except Exception as e:
            logger.error(f"Failed to query latest memories: {e}", exc_info=True)
            return []
