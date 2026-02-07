"""
Connection Pool Bootstrap
Ensure global connection pool manager is initialized at application startup to avoid race conditions
"""

import asyncio
from typing import Optional, Dict, Any
from timem.utils.logging import get_logger
from storage.connection_pool_manager import initialize_connection_pool, get_connection_pool_manager
from timem.utils.config_manager import ConfigManager

logger = get_logger(__name__)

class ConnectionPoolBootstrap:
    """Connection Pool Bootstrap"""
    
    _initialized = False
    _initialization_lock = asyncio.Lock()
    
    @classmethod
    async def initialize_global_pool(cls, config: Optional[Dict[str, Any]] = None) -> bool:
        """Initialize global connection pool"""
        if cls._initialized:
            return True
            
        async with cls._initialization_lock:
            if cls._initialized:
                return True
                
            try:
                if config is None:
                    config_manager = ConfigManager()
                    postgres_config = config_manager.get_storage_config().get('sql', {}).get('postgres', {})
                else:
                    postgres_config = config
                
                logger.info("Starting initialization of global PostgreSQL connection pool...")
                success = await initialize_connection_pool(postgres_config)
                
                if success:
                    cls._initialized = True
                    logger.info("✅ Global PostgreSQL connection pool initialized successfully")
                    
                    # Verify connection pool status
                    pool_manager = get_connection_pool_manager()
                    stats = pool_manager.get_connection_stats()
                    logger.info(f"Connection pool status: {stats}")
                    
                    return True
                else:
                    logger.error("❌ Global PostgreSQL connection pool initialization failed")
                    return False
                    
            except Exception as e:
                logger.error(f"Global connection pool initialization exception: {e}", exc_info=True)
                return False
    
    @classmethod
    def is_initialized(cls) -> bool:
        """Check if initialized"""
        return cls._initialized
    
    @classmethod
    async def ensure_initialized(cls) -> bool:
        """Ensure connection pool is initialized"""
        if not cls._initialized:
            return await cls.initialize_global_pool()
        return True

# Global initialization function
async def bootstrap_connection_pool(config: Optional[Dict[str, Any]] = None) -> bool:
    """Bootstrap connection pool initialization"""
    return await ConnectionPoolBootstrap.initialize_global_pool(config)

# Convenience function
async def ensure_connection_pool() -> bool:
    """Ensure connection pool is initialized"""
    return await ConnectionPoolBootstrap.ensure_initialized()
