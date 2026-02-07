"""
TiMem Cache Storage Adapter
Implements StorageAdapter interface, provides cache storage functionality based on Redis
"""

import asyncio
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timezone
import uuid
import json

from redis import asyncio as aioredis

from timem.utils.logging import get_logger
from timem.utils.config_manager import get_storage_config
from timem.utils.time_parser import time_parser
from timem.models.memory import Memory
from storage.storage_adapter import StorageAdapter
from storage.cache_manager import CacheManager


class CacheAdapter(StorageAdapter):
    """Cache storage adapter - implemented based on Redis, follows StorageAdapter interface"""
    
    def __init__(self, config_manager: Optional[Any] = None):
        """
        Initialize cache storage adapter
        
        Args:
            config_manager: Config manager instance, use global instance if not provided
        """
        from timem.utils.config_manager import get_config_manager
        self.config_manager = config_manager or get_config_manager()
        
        # Refresh config to ensure dataset config takes effect
        self.config_manager.reload_config()
        
        self.config = self.config_manager.get_config("storage.cache")

        self.logger = get_logger(__name__)
        self._is_available = False
        
        # Create CacheManager instance, pass config
        self.cache_manager = CacheManager(self.config)
        self.logger.info(f"CacheAdapter initialization complete, config: {self.config.get('host')}:{self.config.get('port')}")
        
        # Cache prefix, used to distinguish different types of data
        self.key_prefix = "timem:memory:"
        
        # Default expiration time
        self.default_expire = self.config.get('expire', 3600)
    
    async def connect(self) -> bool:
        """
        Connect to storage
        
        Returns:
            bool: Whether connection was successful
        """
        try:
            await self.cache_manager.connect()
            self._is_available = True
            self.logger.info("Cache storage connected successfully")
            return True
        except Exception as e:
            self.logger.error(f"Cache storage connection failed: {e}")
            self._is_available = False
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from storage"""
        try:
            await self.cache_manager.disconnect()
            self._is_available = False
            self.logger.info("Cache storage disconnected")
        except Exception as e:
            self.logger.error(f"Error disconnecting cache storage: {e}")
    
    async def is_available(self) -> bool:
        """
        Check if storage is available
        
        Returns:
            bool: Whether storage is available
        """
        if not self._is_available:
            # Try to connect on first check
            return await self.connect()
        
        # If already marked as available, perform a health check
        try:
            is_healthy = await self.cache_manager.is_connected()
            if not is_healthy:
                self.logger.warning("Cache connection health check failed, will attempt to reconnect.")
                self._is_available = False
                return await self.connect()
            return True
        except Exception as e:
            self.logger.error(f"Error checking cache availability: {e}")
            self._is_available = False
            return False
    
    def _generate_cache_key(self, memory_id: str) -> str:
        """
        Generate cache key name
        
        Args:
            memory_id: Memory ID
            
        Returns:
            str: Cache key name
        """
        return f"{self.key_prefix}{memory_id}"
    
    def _generate_index_key(self, index_type: str, key: str) -> str:
        """
        Generate index cache key name
        
        Args:
            index_type: Index type
            key: Index key
            
        Returns:
            str: Index cache key name
        """
        return f"{self.key_prefix}index:{index_type}:{key}"
    
    async def store_memory(self, memory: Any) -> str:
        """
        Store memory object
        
        Args:
            memory: Memory object or dictionary
            
        Returns:
            str: Storage ID
        """
        if not await self.is_available():
            self.logger.warning("Cache storage unavailable, skipping store operation")
            raise Exception("Cache storage unavailable")
        
        try:
            # Unified conversion to Memory object to call to_payload
            if not isinstance(memory, Memory):
                from timem.models.memory import convert_dict_to_memory
                mem_instance = convert_dict_to_memory(memory)
            else:
                mem_instance = memory

            memory_id = mem_instance.id
            payload = mem_instance.to_payload()
            
            # Generate cache key name
            cache_key = self._generate_cache_key(memory_id)
            
            # Store to cache
            success = await self.cache_manager.set(cache_key, payload, expire=self.default_expire)
            
            if success:
                self.logger.info(f"Successfully cached memory: {memory_id}")
                return memory_id
            else:
                raise Exception(f"Cache storage failed: {memory_id}")
            
        except Exception as e:
            self.logger.error(f"Failed to cache memory: {e}", exc_info=True)
            raise

    async def retrieve_memory(self, memory_id: str) -> Optional[Any]:
        """
        Get memory object by ID
        """
        memory_dict = await self.get_memory_by_id(memory_id)
        if memory_dict:
            try:
                return Memory(**memory_dict)
            except Exception as e:
                self.logger.error(f"Failed to build Memory object from cache data: {e}")
                return None
        return None

    async def get_memory_by_id(self, memory_id: str, level: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get memory object by ID
        
        Args:
            memory_id: Memory ID
            level: Memory level (not used in cache)
            
        Returns:
            Optional[Dict[str, Any]]: Memory object dictionary
        """
        if not await self.is_available():
            self.logger.warning("Cache storage unavailable, skipping get operation")
            return None
        
        try:
            cache_key = self._generate_cache_key(memory_id)
            memory_data = await self.cache_manager.get(cache_key)
            
            if memory_data:
                self.logger.info(f"Successfully retrieved memory from cache: {memory_id}")
                return memory_data
            else:
                self.logger.info(f"Cache miss: {memory_id}")
                return None
        except Exception as e:
            self.logger.error(f"Failed to retrieve memory from cache: {e}")
            return None

    async def search_memories(self, 
                            query: Dict[str, Any], 
                            options: Dict[str, Any] = None) -> List[Any]:
        """
        Search memories
        
        Args:
            query: Query conditions, supports user_id, expert_id, layer, session_id fields
            options: Search options, supports limit etc.
            
        Returns:
            List of memories matching conditions
        """
        if not await self.is_available():
            return []
        
        # Default options
        if options is None:
            options = {}
        
        limit = options.get("limit", 100)
        
        try:
            memory_ids = []
            
            # Find from index
            if "user_id" in query and "level" in query:
                # Use user level index
                user_index_key = self._generate_index_key("user", query["user_id"])
                user_index = await self.cache_manager.get(user_index_key) or {}
                
                level = query["level"]
                memory_ids = user_index.get(level, [])
                
            elif "expert_id" in query and "level" in query:
                # Use expert level index
                expert_index_key = self._generate_index_key("expert", query["expert_id"])
                expert_index = await self.cache_manager.get(expert_index_key) or {}
                
                level = query["level"]
                memory_ids = expert_index.get(level, [])
                
            elif "session_id" in query:
                # Use session index
                session_index_key = self._generate_index_key("session", query["session_id"])
                memory_ids = await self.cache_manager.get(session_index_key) or []
            
            # If no index found, return empty list
            if not memory_ids:
                return []
            
            # Limit return count
            memory_ids = memory_ids[:limit]
            
            # Batch retrieve memory objects
            memories = []
            for memory_id in memory_ids:
                memory = await self.retrieve_memory(memory_id)
                if memory:
                    # Filter conditions
                    if "user_id" in query and getattr(memory, "user_id", None) != query["user_id"]:
                        continue
                    if "expert_id" in query and getattr(memory, "expert_id", None) != query["expert_id"]:
                        continue
                    if "level" in query and getattr(memory, "level", None) != query["level"]:
                        continue
                    
                    memories.append(memory)
            
            self.logger.info(f"Cache search successful, found {len(memories)} records")
            return memories
            
        except Exception as e:
            self.logger.error(f"Cache search failed: {e}")
            return []
    
    async def update_memory(self, memory_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update memory object
        
        Args:
            memory_id: Memory ID
            updates: Fields to update
            
        Returns:
            bool: Whether update was successful
        """
        if not await self.is_available():
            return False
        
        try:
            # First get current memory
            memory_dict = await self.cache_manager.get(self._generate_cache_key(memory_id))
            
            if not memory_dict:
                self.logger.warning(f"Failed to update cache memory: Memory ID {memory_id} does not exist")
                return False
            
            # Update fields
            for field, value in updates.items():
                # Special handling for time fields
                if field in ["created_at", "updated_at"] and hasattr(value, 'isoformat'):
                    memory_dict[field] = value.isoformat()
                else:
                    memory_dict[field] = value
            
            # Set update time
            memory_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
            
            # Store back to cache
            cache_key = self._generate_cache_key(memory_id)
            success = await self.cache_manager.set(cache_key, memory_dict, expire=self.default_expire)
            
            if success:
                self.logger.info(f"Successfully updated cache memory: {memory_id}")
                return True
            else:
                self.logger.warning(f"Cache storage returned update failed: {memory_id}")
                return False
            
        except Exception as e:
            self.logger.error(f"Failed to update cache memory: {e}", exc_info=True)
            return False
    
    async def delete_memory(self, memory_id: str, level: Optional[str] = None) -> bool:
        """
        Delete memory
        
        Args:
            memory_id: Memory ID
            level: Memory level (optional)
            
        Returns:
            bool: Whether deletion was successful
        """
        if not await self.is_available():
            return False
        
        try:
            # Delete main memory data
            cache_key = self._generate_cache_key(memory_id)
            await self.cache_manager.delete(cache_key)
            
            # Delete index data
            index_keys = [
                self._generate_index_key("user_expert", f"{memory_id}"),
                self._generate_index_key("level", f"{memory_id}"),
                self._generate_index_key("session", f"{memory_id}")
            ]
            
            for index_key in index_keys:
                await self.cache_manager.delete(index_key)
            
            self.logger.info(f"Successfully deleted memory from cache: {memory_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to delete cache memory: {e}")
            return False

    async def clear_cache(self) -> bool:
        """
        Clear all cache data
        
        Returns:
            bool: Whether clearing was successful
        """
        try:
            if not await self.is_available():
                return False
            
            # Delete all keys starting with timem:memory:
            pattern = f"{self.key_prefix}*"
            keys = await self.cache_manager.scan(pattern)
            
            if keys:
                await self.cache_manager.delete_many(keys)
                self.logger.info(f"Successfully cleared cache, deleted {len(keys)} keys")
            else:
                self.logger.info("Cache is already empty")
            
            return True
        except Exception as e:
            self.logger.error(f"Failed to clear cache: {e}")
            return False

    async def flush_all(self) -> bool:
        """
        Clear all cache - extended method
        
        Returns:
            bool: Whether clearing was successful
        """
        if not await self.is_available():
            return False
        
        try:
            # Note: Here should implement a safer clear method
            # Actual implementation should use Redis KEYS and SCAN commands, but may require more complex handling in aioredis
            self.logger.warning("Clear all cache functionality not fully implemented")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to clear cache: {e}")
            return False

    # Remove index-related methods because they are not fully or correctly implemented in this adapter
    # _update_indices, _generate_index_key etc.
    # Search logic should also be simplified because it relies on not fully implemented indexes

    async def clear_all_data(self) -> Dict[str, Any]:
        """Clear all cache data"""
        if not await self.is_available():
            return {"success": False, "error": "Cache storage unavailable"}

        try:
            cleared_count = await self.cache_manager.flush_all()
            return {"success": True, "message": f"Cache cleared, {cleared_count} keys removed."}
        except Exception as e:
            self.logger.error(f"Failed to clear cache data: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def get_stats(self) -> Dict[str, Any]:
        """Get cache storage statistics"""
        if not await self.is_available():
            return {"success": False, "error": "Cache storage unavailable"}

        try:
            key_count = await self.cache_manager.get_db_size()
            return {"success": True, "stats": {"key_count": key_count}}
        except Exception as e:
            self.logger.error(f"Failed to get cache storage statistics: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

# Factory method
def get_cache_adapter(config_manager: Optional[Any] = None) -> CacheAdapter:
    """Get cache storage adapter instance"""
    return CacheAdapter(config_manager=config_manager)