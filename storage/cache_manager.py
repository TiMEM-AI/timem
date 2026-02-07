"""
TiMem Cache Manager
Hot data caching based on Redis, async interface
"""

from redis import asyncio as aioredis
from redis.exceptions import ConnectionError, TimeoutError
from typing import Any, Optional
from timem.utils.logging import get_logger
from timem.utils.config_manager import get_storage_config
from timem.utils.json_utils import dumps, loads

class CacheManager:
    """Redis cache adapter"""
    def __init__(self, config: Optional[dict] = None):
        if config is None:
            # If no config provided, load from global config
            storage_config = get_storage_config()
            # Ensure safely getting cache config from possibly nested dictionary
            self.config = storage_config.get('cache', {})
        else:
            # Use passed-in dictionary config
            self.config = config
            
        self.logger = get_logger(__name__)
        self.redis: Optional[aioredis.Redis] = None
        self.pool = None

    async def connect(self):
        """Initialize and connect Redis client"""
        if self.redis and await self.is_connected():
            return  # Avoid duplicate connections
        try:
            # Get connection info from environment variables or config, avoid hardcoding localhost
            import os
            host = self.config.get('host') or os.getenv('REDIS_HOST', 'localhost')
            port = int(self.config.get('port') or os.getenv('REDIS_PORT', '6379'))
            password = self.config.get('password') or os.getenv('REDIS_PASSWORD')
            db = int(self.config.get('db', 0))
            
            # Use connection pool
            url = f"redis://{host}:{port}/{db}"
            self.pool = aioredis.ConnectionPool.from_url(
                url, 
                password=password, 
                encoding='utf-8', 
                decode_responses=True,
                max_connections=10,  # Set max connections
                socket_connect_timeout=5, # Set connection timeout
            )
            self.redis = aioredis.Redis(connection_pool=self.pool)

            # Test connection
            await self.redis.ping()
            self.logger.info(f"Redis client initialized successfully: {host}:{port}")
        except (ConnectionError, TimeoutError) as e:
            self.logger.error(f"Redis connection failed: {e}")
            self.redis = None
            self.pool = None
            raise
        except Exception as e:
            self.logger.error(f"Unknown error during Redis client initialization: {e}")
            self.redis = None
            self.pool = None
            raise

    async def is_connected(self) -> bool:
        """Check if Redis connection is healthy"""
        if not self.redis:
            return False
        try:
            return await self.redis.ping()
        except (ConnectionError, TimeoutError):
            return False

    async def ensure_connected(self):
        """Ensure client is connected, try to reconnect if not connected"""
        if not await self.is_connected():
            self.logger.info("Redis connection lost, attempting to reconnect...")
            await self.connect()

    async def set(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        """Set cache"""
        await self.ensure_connected()
        try:
            # Use custom JSON encoder to handle datetime objects
            val = dumps(value)
            await self.redis.set(key, val, ex=expire)
            self.logger.debug(f"Cache write: {key}")
            return True
        except Exception as e:
            self.logger.error(f"Cache write failed: {e}")
            return False

    async def get(self, key: str) -> Optional[Any]:
        """Get cache"""
        await self.ensure_connected()
        try:
            val = await self.redis.get(key)
            if val is not None:
                # Since decode_responses=True, redis.get() returns a string, can directly loads
                return loads(val)
            return None
        except Exception as e:
            self.logger.error(f"Cache read failed: {e}")
            return None

    async def delete(self, key: str) -> bool:
        """Delete cache"""
        await self.ensure_connected()
        try:
            result = await self.redis.delete(key)
            self.logger.debug(f"Cache delete: {key}")
            return result > 0
        except Exception as e:
            self.logger.error(f"Cache delete failed: {e}")
            return False

    async def scan(self, pattern: str = "*", count: int = 100) -> list:
        """
        Scan keys matching pattern
        
        Args:
            pattern: Match pattern, supports wildcards
            count: Number of keys to scan each time
            
        Returns:
            list: List of matching keys
        """
        await self.ensure_connected()
        try:
            keys = []
            cursor = 0
            
            while True:
                cursor, batch_keys = await self.redis.scan(
                    cursor=cursor, 
                    match=pattern, 
                    count=count
                )
                keys.extend(batch_keys)
                
                if cursor == 0:
                    break
            
            self.logger.debug(f"Scan pattern '{pattern}' found {len(keys)} keys")
            return keys
        except Exception as e:
            self.logger.error(f"Scan keys failed: {e}")
            return []

    async def delete_many(self, keys: list) -> int:
        """
        Batch delete keys
        
        Args:
            keys: List of keys to delete
            
        Returns:
            int: Number of keys successfully deleted
        """
        await self.ensure_connected()
        try:
            if not keys:
                return 0
                
            result = await self.redis.delete(*keys)
            self.logger.debug(f"Batch delete {len(keys)} keys, successfully deleted {result}")
            return result
        except Exception as e:
            self.logger.error(f"Batch delete keys failed: {e}")
            return 0

    async def flush_all(self) -> int:
        """Clear all keys in current database"""
        await self.ensure_connected()
        try:
            # flushdb is a sync command, but executed asynchronously in aioredis
            await self.redis.flushdb()
            self.logger.info("Redis database cleared")
            return 1 # Indicates operation successful
        except Exception as e:
            self.logger.error(f"Failed to clear Redis database: {e}", exc_info=True)
            return 0

    async def get_db_size(self) -> int:
        """Get number of keys in current database"""
        await self.ensure_connected()
        try:
            size = await self.redis.dbsize()
            return size
        except Exception as e:
            self.logger.error(f"Failed to get Redis database size: {e}", exc_info=True)
            return 0

    async def disconnect(self):
        """Disconnect cache service"""
        await self.close()
    
    async def close(self):
        """Close connection"""
        if self.redis:
            await self.redis.close()
        if self.pool:
            await self.pool.disconnect()
        self.redis = None
        self.pool = None
        self.logger.info("Redis connection closed")

# Factory method
def get_cache_manager() -> CacheManager:
    return CacheManager()

# TODO: Support batch operations, distributed locks, cache consistency and other advanced features