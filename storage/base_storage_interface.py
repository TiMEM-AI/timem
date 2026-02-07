"""
TiMem Unified Storage Interface Standard

Defines abstract interfaces that all storage implementations must follow, ensuring:
1. High cohesion: Each interface has single, clear responsibility
2. Low coupling: Minimal dependencies between interfaces
3. Layered: Clear abstraction levels
4. Clear responsibility: CRUD, retrieval, and management functions separated
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, AsyncGenerator
from datetime import datetime


class BaseStorageInterface(ABC):
    """
    Storage layer base interface
    
    Defines core CRUD operation contracts for all storage implementations
    """
    
    # ==================== Connection Management ====================
    
    @abstractmethod
    async def connect(self) -> bool:
        """
        Establish database connection
        
        Returns:
            bool: Whether connection was successful
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> bool:
        """
        Close database connection
        
        Returns:
            bool: Whether disconnection was successful
        """
        pass
    
    @abstractmethod
    async def is_available(self) -> bool:
        """
        Check if database is available
        
        Returns:
            bool: Whether database is available
        """
        pass
    
    # ==================== Memory CRUD Operations ====================
    
    @abstractmethod
    async def store_memory(self, memory_data: Dict[str, Any]) -> Optional[str]:
        """
        Store single memory
        
        Args:
            memory_data: Memory data dictionary
            
        Returns:
            Optional[str]: Returns memory ID on success, None on failure
        """
        pass
    
    @abstractmethod
    async def batch_store_memories(self, memory_records: List[Dict[str, Any]]) -> List[str]:
        """
        Batch store memories
        
        Args:
            memory_records: List of memory data
            
        Returns:
            List[str]: List of successfully stored memory IDs
        """
        pass
    
    @abstractmethod
    async def get_memory_by_id(self, memory_id: str, level: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get memory by ID
        
        Args:
            memory_id: Memory ID
            level: Memory level (optional)
            
        Returns:
            Optional[Dict[str, Any]]: Memory data, returns None if not found
        """
        pass
    
    @abstractmethod
    async def update_memory(self, memory_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update memory
        
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
        Delete memory
        
        Args:
            memory_id: Memory ID
            
        Returns:
            bool: Whether deletion was successful
        """
        pass
    
    # ==================== Memory Retrieval Operations ====================
    
    @abstractmethod
    async def search_memories(self, 
                            query_text: Optional[str] = None,
                            user_id: Optional[str] = None,
                            expert_id: Optional[str] = None,
                            level: Optional[str] = None,
                            limit: int = 20) -> List[Dict[str, Any]]:
        """
        Search memories (basic retrieval)
        
        Args:
            query_text: Query text
            user_id: User ID filter
            expert_id: Expert ID filter
            level: Memory level filter
            limit: Result count limit
            
        Returns:
            List[Dict[str, Any]]: List of search results
        """
        pass
    
    @abstractmethod
    async def find_memories_by_criteria(self, **criteria) -> List[Dict[str, Any]]:
        """
        Find memories by criteria
        
        Args:
            **criteria: Query conditions
            
        Returns:
            List[Dict[str, Any]]: List of matching memories
        """
        pass
    
    # ==================== Data Management Operations ====================
    
    @abstractmethod
    async def clear_all_data(self) -> bool:
        """
        Clear all data (mainly for testing)
        
        Returns:
            bool: Whether clearing was successful
        """
        pass
    
    @abstractmethod
    async def get_data_statistics(self) -> Dict[str, Any]:
        """
        Get data statistics
        
        Returns:
            Dict[str, Any]: Data statistics information
        """
        pass


class AdvancedSearchInterface(ABC):
    """
    Advanced Search Interface
    
    Defines extended search functionality, such as full-text search, semantic search, etc.
    """
    
    @abstractmethod
    async def fulltext_search(self,
                            query_text: str,
                            user_id: Optional[str] = None,
                            expert_id: Optional[str] = None,
                            level: Optional[str] = None,
                            limit: int = 20,
                            min_score: float = 0.0) -> List[Dict[str, Any]]:
        """
        Full-text search
        
        Args:
            query_text: Query text
            user_id: User ID filter
            expert_id: Expert ID filter
            level: Memory level filter
            limit: Result count limit
            min_score: Minimum score threshold
            
        Returns:
            List[Dict[str, Any]]: Full-text search results with score information
        """
        pass


class SessionManagementInterface(ABC):
    """
    Session Management Interface
    
    Defines session-related operations
    """
    
    @abstractmethod
    async def create_session(self, user_id: str, expert_id: str, session_id: Optional[str] = None) -> str:
        """
        Create session
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            session_id: Session ID (optional, auto-generated)
            
        Returns:
            str: Session ID
        """
        pass
    
    @abstractmethod
    async def get_session_memories(self, session_id: str, level: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get session-related memories
        
        Args:
            session_id: Session ID
            level: Memory level filter
            
        Returns:
            List[Dict[str, Any]]: List of session memories
        """
        pass


class UnifiedStorageInterface(BaseStorageInterface, AdvancedSearchInterface, SessionManagementInterface):
    """
    Unified Storage Interface
    
    Complete interface definition integrating all storage functionality
    Inherits all sub-interfaces to ensure implementation classes provide complete functionality
    """
    pass


# Storage layer contract validator
class StorageContractValidator:
    """
    Storage layer contract validator
    
    Validates whether storage implementation complies with interface standards
    """
    
    @staticmethod
    def validate_interface_compliance(storage_instance: Any) -> Dict[str, bool]:
        """
        Validate whether storage instance complies with interface contract
        
        Args:
            storage_instance: Storage instance
            
        Returns:
            Dict[str, bool]: Interface compliance check results
        """
        required_methods = [
            'connect', 'disconnect', 'is_available',
            'store_memory', 'batch_store_memories', 'get_memory_by_id',
            'update_memory', 'delete_memory', 'search_memories',
            'find_memories_by_criteria', 'clear_all_data', 'get_data_statistics',
            'fulltext_search', 'create_session', 'get_session_memories'
        ]
        
        compliance_results = {}
        for method_name in required_methods:
            has_method = hasattr(storage_instance, method_name)
            is_callable = callable(getattr(storage_instance, method_name, None)) if has_method else False
            compliance_results[method_name] = has_method and is_callable
        
        return compliance_results
    
    @staticmethod
    def get_compliance_report(compliance_results: Dict[str, bool]) -> str:
        """
        Generate compliance report
        
        Args:
            compliance_results: Compliance check results
            
        Returns:
            str: Formatted report
        """
        total_methods = len(compliance_results)
        compliant_methods = sum(compliance_results.values())
        compliance_rate = compliant_methods / total_methods
        
        report = f"Interface compliance: {compliant_methods}/{total_methods} ({compliance_rate:.1%})\n"
        
        missing_methods = [method for method, compliant in compliance_results.items() if not compliant]
        if missing_methods:
            report += f"Missing methods: {', '.join(missing_methods)}"
        
        return report
