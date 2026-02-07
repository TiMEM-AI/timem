"""
TiMem Unified Storage Adapter Interface

Provides unified interface definitions for all storage implementations
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Union
from datetime import datetime

class StorageAdapter(ABC):
    """Unified storage adapter interface"""
    
    # Adapter registry for testing
    _adapter_registry = {}
    
    @classmethod
    def register_adapter_type(cls, adapter_type: str, adapter_instance: 'StorageAdapter'):
        """
        Register adapter instance, mainly for testing
        
        Args:
            adapter_type: Adapter type name
            adapter_instance: Adapter instance
        """
        cls._adapter_registry[adapter_type] = adapter_instance
    
    @classmethod
    def get_registered_adapter(cls, adapter_type: str) -> Optional['StorageAdapter']:
        """
        Get registered adapter instance
        
        Args:
            adapter_type: Adapter type name
            
        Returns:
            Adapter instance, or None if not found
        """
        return cls._adapter_registry.get(adapter_type)
    
    @abstractmethod
    async def connect(self) -> bool:
        """
        Connect to storage
        
        Returns:
            bool: Whether connection was successful
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from storage"""
        pass
    
    @abstractmethod
    async def is_available(self) -> bool:
        """
        Check if storage is available
        
        Returns:
            bool: Whether storage is available
        """
        pass
    
    @abstractmethod
    async def store_memory(self, memory: Any) -> str:
        """
        Store memory object
        
        Args:
            memory: Memory object
            
        Returns:
            str: Storage ID
        """
        pass
    
    @abstractmethod
    async def retrieve_memory(self, memory_id: str) -> Optional[Any]:
        """
        Retrieve memory object
        
        Args:
            memory_id: Memory ID
            
        Returns:
            Memory object, or None if not found
        """
        pass
    
    @abstractmethod
    async def search_memories(self, 
                           query: Dict[str, Any], 
                           options: Dict[str, Any] = None) -> List[Any]:
        """
        Search memories
        
        Args:
            query: Query conditions
            options: Search options
            
        Returns:
            List of memories matching the conditions
        """
        pass
    
    @abstractmethod
    async def update_memory(self, memory_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update memory object
        
        Args:
            memory_id: Memory ID
            updates: Fields to update
            
        Returns:
            bool: Whether update was successful
        """
        pass
    
    @abstractmethod
    async def delete_memory(self, memory_id: str) -> bool:
        """
        Delete memory object
        
        Args:
            memory_id: Memory ID
            
        Returns:
            bool: Whether deletion was successful
        """
        pass