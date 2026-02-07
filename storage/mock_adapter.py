"""
TiMem Mock Storage Adapter

Mock storage adapter for testing, implements storage interface but stores data in memory
"""

import copy
import asyncio
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional, Union

from storage.storage_adapter import StorageAdapter
from timem.utils.logging import get_logger

logger = get_logger(__name__)


class MockStorageAdapter(StorageAdapter):
    """
    Mock storage adapter, implements all StorageAdapter interfaces, but stores data in memory
    Suitable for testing environment
    """
    
    def __init__(self, config=None):
        """Initialize mock storage adapter"""
        self.memories = {}  # In-memory stored memories, key is memory ID
        self.memory_count = 0  # Memory counter
        self.is_connected = False  # Connection status
        self.logger = get_logger(__name__)
        self.logger.info("Mock storage adapter initialization complete")
        
    async def connect(self) -> bool:
        """Connect to storage service"""
        self.is_connected = True
        self.logger.info("Mock storage adapter connected successfully")
        return True
        
    async def disconnect(self) -> bool:
        """Disconnect from storage service"""
        self.is_connected = False
        self.memories.clear()
        self.logger.info("Mock storage adapter disconnected")
        return True
        
    async def is_available(self) -> bool:
        """Check if storage service is available"""
        return self.is_connected
        
    async def store_memory(self, memory: Any) -> str:
        """
        Store memory object
        
        Args:
            memory: Memory object (dictionary or object with to_dict method)
            
        Returns:
            str: Memory ID
        """
        try:
            # Convert memory to dictionary
            memory_dict = memory.to_dict() if hasattr(memory, 'to_dict') else copy.deepcopy(memory) if isinstance(memory, dict) else vars(memory)
            
            # Ensure has ID
            if 'id' not in memory_dict or not memory_dict['id']:
                memory_dict['id'] = str(uuid.uuid4())
                
            # Ensure has timestamp
            if 'created_at' not in memory_dict or not memory_dict['created_at']:
                memory_dict['created_at'] = datetime.now().isoformat()
                
            # Store memory
            memory_id = memory_dict['id']
            self.memories[memory_id] = memory_dict
            self.memory_count += 1
            
            self.logger.debug(f"Mock storage adapter stored memory successfully: {memory_id}")
            return memory_id
            
        except Exception as e:
            self.logger.error(f"Mock storage adapter failed to store memory: {str(e)}")
            raise
            
    async def retrieve_memory(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve memory object
        
        Args:
            memory_id: Memory ID
            
        Returns:
            Optional[Dict[str, Any]]: Memory object, returns None if not found
        """
        memory = self.memories.get(memory_id)
        if memory:
            self.logger.debug(f"Mock storage adapter retrieved memory successfully: {memory_id}")
        else:
            self.logger.debug(f"Mock storage adapter memory not found: {memory_id}")
        return copy.deepcopy(memory) if memory else None
        
    async def get_memory_by_id(self, memory_id: str, level: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get memory by ID
        
        Args:
            memory_id: Memory ID
            level: Memory level (optional)
            
        Returns:
            Optional[Dict[str, Any]]: Memory object, returns None if not found
        """
        memory = self.memories.get(memory_id)
        if memory and level and memory.get('layer') != level:
            return None
        return copy.deepcopy(memory) if memory else None
        
    async def update_memory(self, memory_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update memory object
        
        Args:
            memory_id: Memory ID
            updates: Fields to update
            
        Returns:
            bool: Whether update was successful
        """
        if memory_id in self.memories:
            self.memories[memory_id].update(updates)
            self.logger.debug(f"Mock storage adapter updated memory successfully: {memory_id}")
            return True
        else:
            self.logger.debug(f"Mock storage adapter failed to update memory, memory does not exist: {memory_id}")
            return False
            
    async def delete_memory(self, memory_id: str, level: Optional[str] = None, **kwargs) -> bool:
        """
        Delete memory object
        
        Args:
            memory_id: Memory ID
            level: Memory level (optional)
            **kwargs: Additional parameters
            
        Returns:
            bool: Whether deletion was successful
        """
        if memory_id in self.memories:
            if level and self.memories[memory_id].get('layer') != level:
                return False
                
            del self.memories[memory_id]
            self.logger.debug(f"Mock storage adapter deleted memory successfully: {memory_id}")
            return True
        else:
            self.logger.debug(f"Mock storage adapter failed to delete memory, memory does not exist: {memory_id}")
            return False
            
    async def search_memories(self, query: Dict[str, Any], options: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Search memories
        
        Args:
            query: Query conditions
            options: Query options (optional)
            
        Returns:
            List[Dict[str, Any]]: List of memories matching conditions
        """
        options = options or {}
        limit = options.get('limit', 100)
        sort_by = options.get('sort_by', 'created_at')
        sort_order = options.get('sort_order', 'asc')  # 'asc' or 'desc'
        
        # Filter memories matching conditions
        filtered_memories = []
        for memory in self.memories.values():
            match = True
            
            # Filter conditions
            for key, value in query.items():
                # Handle time range query
                if key == 'start_time' and 'created_at' in memory:
                    memory_time = self._parse_time(memory['created_at'])
                    query_time = self._parse_time(value)
                    if memory_time < query_time:
                        match = False
                        break
                elif key == 'end_time' and 'created_at' in memory:
                    memory_time = self._parse_time(memory['created_at'])
                    query_time = self._parse_time(value)
                    if memory_time > query_time:
                        match = False
                        break
                # Handle text query (simulate vector search)
                elif key == 'query_text' and 'content' in memory:
                    if value.lower() not in memory['content'].lower():
                        match = False
                        break
                # Handle regular field matching
                elif key in memory and memory[key] != value:
                    match = False
                    break
                elif key not in memory and key not in ['start_time', 'end_time', 'query_text']:
                    match = False
                    break
                    
            if match:
                filtered_memories.append(copy.deepcopy(memory))
                
        # Sort
        try:
            filtered_memories.sort(
                key=lambda m: m.get(sort_by, ''),
                reverse=(sort_order.lower() == 'desc')
            )
        except Exception:
            # If sorting fails, ignore sorting
            pass
            
        # Apply limit
        if limit > 0:
            filtered_memories = filtered_memories[:limit]
            
        self.logger.debug(f"Mock storage adapter found {len(filtered_memories)} memories")
        return filtered_memories
        
    async def count_memories(self, query: Dict[str, Any]) -> int:
        """
        Count memories matching conditions
        
        Args:
            query: Query conditions
            
        Returns:
            int: Number of memories
        """
        memories = await self.search_memories(query)
        return len(memories)
        
    def _parse_time(self, time_str):
        """Parse time string to datetime object"""
        if isinstance(time_str, datetime):
            return time_str
            
        try:
            return datetime.fromisoformat(time_str)
        except (ValueError, TypeError):
            try:
                return datetime.strptime(time_str, '%Y-%m-%dT%H:%M:%S.%fZ')
            except (ValueError, TypeError):
                try:
                    return datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
                except (ValueError, TypeError):
                    return datetime.min


# Mock storage adapter instance
_mock_adapter_instance = None

def get_mock_adapter():
    """Get mock storage adapter instance"""
    global _mock_adapter_instance
    if _mock_adapter_instance is None:
        _mock_adapter_instance = MockStorageAdapter()
    return _mock_adapter_instance