"""
TiMem Database Connection Management [Deprecated]

This module is deprecated, please use the new storage adapter system:
- storage.storage_adapter: Common interface
- storage.sql_adapter: SQL storage
- storage.vector_adapter: Vector storage
- storage.graph_adapter: Graph storage
- storage.cache_adapter: Cache storage
- storage.memory_storage_manager: Unified manager
"""

import warnings
import asyncio
from typing import Optional, Dict, Any, List
import functools
from contextlib import asynccontextmanager

from timem.utils.logging import get_logger
from storage.memory_storage_manager import get_memory_storage_manager, get_memory_storage_manager_async

logger = get_logger(__name__)

# Display deprecation warning
warnings.warn(
    "storage.database module is deprecated, please use the new storage adapter system. "
    "See storage.memory_storage_manager and adapter modules",
    DeprecationWarning,
    stacklevel=2
)


class DatabaseConnectionError(Exception):
    """Database connection error"""
    pass


class Database:
    """
    Database Manager [Deprecated]
    
    This class is deprecated, kept only for backward compatibility.
    Please use storage.memory_storage_manager.MemoryStorageManager instead
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize database manager"""
        self._storage_manager = None
        self._connected = False
        logger.warning("Using deprecated Database class, please use MemoryStorageManager instead")
        
    async def _ensure_storage_manager(self):
        """Ensure storage manager is initialized"""
        if not self._storage_manager:
            self._storage_manager = await get_memory_storage_manager_async()
    
    async def connect_all(self):
        """Connect to all databases"""
        logger.warning("Calling deprecated connect_all method, use new storage adapter system instead")
        await self._ensure_storage_manager()
        self._connected = True
        return self._storage_manager
    
    async def disconnect_all(self):
        """Disconnect from all databases"""
        logger.warning("Calling deprecated disconnect_all method, use new storage adapter system instead")
        if self._storage_manager:
            await self._storage_manager.close()
        self._connected = False
    
    async def test_all_connections(self) -> Dict[str, bool]:
        """Test all database connections"""
        logger.warning("Calling deprecated test_all_connections method, use new storage adapter system instead")
        await self._ensure_storage_manager()
        
        # Get storage status
        status = getattr(self._storage_manager, "storage_status", {})
        
        return {
            'mysql': status.get('sql', False),
            'neo4j': status.get('graph', False),
            'qdrant': status.get('vector', False),
            'redis': status.get('cache', False)
        }
    
    @property
    def is_connected(self) -> bool:
        """Check if connected"""
        return self._connected
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check"""
        connection_status = await self.test_all_connections()
        
        return {
            'status': 'healthy' if any(connection_status.values()) else 'unhealthy',
            'connections': connection_status,
            'timestamp': asyncio.get_event_loop().time()
        }


# Backward compatible global functions

_database = None

def get_database() -> Database:
    """
    Get database instance [Deprecated]
    
    This function is deprecated, please use get_memory_storage_manager instead
    """
    global _database
    if _database is None:
        _database = Database()
    return _database


async def init_database():
    """
    Initialize database connection [Deprecated]
    
    This function is deprecated, please use get_memory_storage_manager_async instead
    """
    logger.warning("Calling deprecated init_database, use get_memory_storage_manager_async instead")
    db = get_database()
    await db.connect_all()
    return db


async def close_database():
    """
    Close database connection [Deprecated]
    
    This function is deprecated
    """
    logger.warning("Calling deprecated close_database")
    db = get_database()
    await db.disconnect_all()


# Dependency injection functions - keep backward compatibility
@asynccontextmanager
async def get_mysql_session():
    """Get MySQL session [Deprecated]"""
    logger.warning("Calling deprecated get_mysql_session")
    db = get_database()
    await db._ensure_storage_manager()
    
    # This part is only for API compatibility
    class MockSession:
        async def execute(self, *args, **kwargs):
            logger.warning("Using deprecated MySQL session to execute query")
            return None
            
    yield MockSession()


# Other backward compatible functions
async def get_neo4j_session():
    """Get Neo4j session [Deprecated]"""
    logger.warning("Calling deprecated get_neo4j_session")
    return None


async def get_qdrant_client():
    """Get Qdrant client [Deprecated]"""
    logger.warning("Calling deprecated get_qdrant_client")
    return None


async def get_redis_client():
    """Get Redis client [Deprecated]"""
    logger.warning("Calling deprecated get_redis_client")
    return None 