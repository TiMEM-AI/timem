"""
Asynchronous HTTP Connection Pool Manager

Provides production-grade HTTP connection pool management with features:
1. True async I/O (based on aiohttp)
2. Independent connection pool per provider
3. Connection health checks and automatic recovery
4. Fine-grained timeout control
5. Connection pool statistics and monitoring
"""

import asyncio
import time
from typing import Dict, Optional, Any
from dataclasses import dataclass
from contextlib import asynccontextmanager
import aiohttp
from aiohttp import ClientSession, ClientTimeout, TCPConnector

from timem.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PoolConfig:
    """Connection pool configuration (engineering-level optimization - fast failure detection)"""
    max_connections: int = 100  # Maximum connections
    max_connections_per_host: int = 20  # Max connections per host
    keepalive_timeout: float = 30.0  # Keep-alive timeout (seconds)
    connect_timeout: float = 3.0  # TCP connection timeout (seconds) - reduced to 3s for fast failure
    sock_connect: float = 2.0  # Socket connection timeout (seconds) - must establish within 2s
    sock_read: float = 30.0  # Socket read timeout (seconds)
    read_timeout: float = 60.0  # Read timeout (seconds)
    total_timeout: float = 90.0  # Total timeout (seconds)
    
    # Health check configuration
    health_check_enabled: bool = True
    health_check_interval: float = 60.0  # Health check interval (seconds)
    
    # Reconnection configuration
    auto_reconnect: bool = True
    max_reconnect_attempts: int = 3


@dataclass
class PoolStats:
    """Connection pool statistics"""
    total_requests: int = 0
    active_connections: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_latency: float = 0.0
    last_health_check: float = 0.0
    
    @property
    def avg_latency(self) -> float:
        """Average latency"""
        if self.successful_requests == 0:
            return 0.0
        return self.total_latency / self.successful_requests
    
    @property
    def success_rate(self) -> float:
        """Success rate"""
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests


class AsyncHTTPPool:
    """
    Asynchronous HTTP Connection Pool Manager
    
    Maintains independent connection pools for each LLM provider, providing true async I/O capability.
    """
    
    def __init__(self, default_config: Optional[PoolConfig] = None):
        """
        Initialize connection pool manager
        
        Args:
            default_config: Default connection pool configuration
        """
        self.default_config = default_config or PoolConfig()
        
        # Connection pools for each provider
        self._sessions: Dict[str, ClientSession] = {}
        
        # Configuration for each provider (can override default)
        self._provider_configs: Dict[str, PoolConfig] = {}
        
        # Connection pool statistics
        self._stats: Dict[str, PoolStats] = {}
        
        # Health check tasks
        self._health_check_tasks: Dict[str, asyncio.Task] = {}
        
        # Initialization lock
        self._init_lock = asyncio.Lock()
        
        # Closed flag
        self._closed = False
        
        logger.info(
            f"Async HTTP connection pool manager initialized: "
            f"max_connections={self.default_config.max_connections}, "
            f"keepalive_timeout={self.default_config.keepalive_timeout}s"
        )
    
    async def configure_provider(
        self, 
        provider: str, 
        config: PoolConfig,
        base_url: Optional[str] = None
    ):
        """
        Configure connection pool for specific provider
        
        Args:
            provider: Provider name (e.g., 'openai', 'zhipuai')
            config: Connection pool configuration
            base_url: Base URL (for health checks)
        """
        self._provider_configs[provider] = config
        logger.info(f"Configured provider {provider} connection pool: max_conn={config.max_connections}")
    
    async def _create_session(self, provider: str) -> ClientSession:
        """
        Create new HTTP session
        
        Args:
            provider: Provider name
            
        Returns:
            ClientSession instance
        """
        config = self._provider_configs.get(provider, self.default_config)
        
        # Create optimized TCP connector (engineering-level - fast failure)
        connector = TCPConnector(
            limit=config.max_connections,
            limit_per_host=config.max_connections_per_host,
            ttl_dns_cache=300,  # DNS cache 5 minutes
            enable_cleanup_closed=True,
            force_close=False,  # Reuse connections
            keepalive_timeout=config.keepalive_timeout,
            # Performance optimization parameters
            family=0,  # AF_UNSPEC, auto-select IPv4/IPv6
            ssl=None,  # Don't preset SSL context, let session handle it
            use_dns_cache=True,  # Enable DNS cache
            resolver=None,  # Use default resolver
        )
        
        # Create fine-grained timeout configuration (millisecond-level detection)
        timeout = ClientTimeout(
            total=config.total_timeout,
            connect=config.connect_timeout,  # TCP connection timeout: 3s
            sock_connect=config.sock_connect,  # Socket connection timeout: 2s
            sock_read=config.sock_read  # Socket read timeout: 30s
        )
        
        # Create session
        session = ClientSession(
            connector=connector,
            timeout=timeout,
            headers={
                "User-Agent": "TiMem-AsyncHTTPPool/1.0",
            },
            raise_for_status=False,  # Handle errors manually
            trust_env=True  # Trust environment proxy settings
        )
        
        logger.info(f"Created new HTTP session for {provider}")
        return session
    
    async def _ensure_session(self, provider: str) -> ClientSession:
        """
        Ensure provider session is created
        
        Args:
            provider: Provider name
            
        Returns:
            ClientSession instance
        """
        if self._closed:
            raise RuntimeError("Connection pool is closed")
        
        if provider not in self._sessions or self._sessions[provider].closed:
            async with self._init_lock:
                if provider not in self._sessions or self._sessions[provider].closed:
                    self._sessions[provider] = await self._create_session(provider)
                    self._stats[provider] = PoolStats()
                    
                    # Start health check
                    config = self._provider_configs.get(provider, self.default_config)
                    if config.health_check_enabled:
                        await self._start_health_check(provider)
        
        return self._sessions[provider]
    
    @asynccontextmanager
    async def get_session(self, provider: str):
        """
        Get provider HTTP session (context manager)
        
        Args:
            provider: Provider name
            
        Yields:
            ClientSession instance
            
        Example:
            async with pool.get_session('openai') as session:
                async with session.post(url, json=data) as response:
                    return await response.json()
        """
        session = await self._ensure_session(provider)
        try:
            yield session
        except Exception as e:
            logger.error(f"Provider {provider} HTTP request exception: {e}")
            raise
    
    async def request(
        self,
        provider: str,
        method: str,
        url: str,
        **kwargs
    ) -> aiohttp.ClientResponse:
        """
        Send HTTP request
        
        Args:
            provider: Provider name
            method: HTTP method
            url: Request URL
            **kwargs: Other request parameters
            
        Returns:
            HTTP response object
        """
        session = await self._ensure_session(provider)
        stats = self._stats[provider]
        
        stats.total_requests += 1
        stats.active_connections += 1
        start_time = time.time()
        
        try:
            response = await session.request(method, url, **kwargs)
            
            # Update statistics
            latency = time.time() - start_time
            stats.successful_requests += 1
            stats.total_latency += latency
            
            logger.debug(
                f"[{provider}] {method} {url} - "
                f"status={response.status}, latency={latency:.3f}s"
            )
            
            return response
            
        except Exception as e:
            stats.failed_requests += 1
            logger.error(f"[{provider}] {method} {url} - failed: {e}")
            raise
        finally:
            stats.active_connections -= 1
    
    async def _start_health_check(self, provider: str):
        """
        Start health check task
        
        Args:
            provider: Provider name
        """
        if provider in self._health_check_tasks:
            # Health check task already exists
            return
        
        config = self._provider_configs.get(provider, self.default_config)
        
        async def health_check_loop():
            """Health check loop"""
            while not self._closed:
                try:
                    await asyncio.sleep(config.health_check_interval)
                    
                    # Check if session is closed
                    if provider in self._sessions:
                        session = self._sessions[provider]
                        if session.closed:
                            logger.warning(f"Provider {provider} session closed, attempting to recreate")
                            if config.auto_reconnect:
                                self._sessions[provider] = await self._create_session(provider)
                        
                        # Update health check time
                        self._stats[provider].last_health_check = time.time()
                        
                        logger.debug(f"Provider {provider} health check completed")
                
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Provider {provider} health check exception: {e}")
        
        # Create and start task
        task = asyncio.create_task(health_check_loop())
        self._health_check_tasks[provider] = task
        logger.info(f"Started health check task for provider {provider}")
    
    def get_stats(self, provider: Optional[str] = None) -> Dict[str, Any]:
        """
        Get connection pool statistics
        
        Args:
            provider: Provider name (None means all providers)
            
        Returns:
            Statistics dictionary
        """
        if provider:
            if provider not in self._stats:
                return {}
            
            stats = self._stats[provider]
            return {
                "provider": provider,
                "total_requests": stats.total_requests,
                "active_connections": stats.active_connections,
                "successful_requests": stats.successful_requests,
                "failed_requests": stats.failed_requests,
                "avg_latency": stats.avg_latency,
                "success_rate": stats.success_rate,
                "last_health_check": stats.last_health_check,
            }
        
        # Return statistics for all providers
        return {
            prov: self.get_stats(prov)
            for prov in self._stats.keys()
        }
    
    async def close(self, provider: Optional[str] = None):
        """
        Close connection pool
        
        Args:
            provider: Provider name (None means close all)
        """
        if provider:
            # Close specific provider
            if provider in self._health_check_tasks:
                self._health_check_tasks[provider].cancel()
                try:
                    await self._health_check_tasks[provider]
                except asyncio.CancelledError:
                    pass
                del self._health_check_tasks[provider]
            
            if provider in self._sessions:
                await self._sessions[provider].close()
                del self._sessions[provider]
                logger.info(f"Provider {provider} connection pool closed")
        else:
            # Close all providers
            self._closed = True
            
            # Cancel all health check tasks
            for task in self._health_check_tasks.values():
                task.cancel()
            
            if self._health_check_tasks:
                await asyncio.gather(*self._health_check_tasks.values(), return_exceptions=True)
            
            # Close all sessions
            for provider, session in self._sessions.items():
                await session.close()
                logger.info(f"Provider {provider} connection pool closed")
            
            self._sessions.clear()
            self._health_check_tasks.clear()
            logger.info("All connection pools closed")
    
    async def __aenter__(self):
        """Async context manager entry"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()


# Global connection pool instance (singleton pattern)
_global_http_pool: Optional[AsyncHTTPPool] = None
_global_pool_lock = asyncio.Lock()


async def get_global_http_pool() -> AsyncHTTPPool:
    """
    Get global HTTP connection pool (singleton)
    
    Returns:
        AsyncHTTPPool instance
    """
    global _global_http_pool
    
    if _global_http_pool is None or _global_http_pool._closed:
        async with _global_pool_lock:
            if _global_http_pool is None or _global_http_pool._closed:
                # Load from configuration
                from timem.utils.config_manager import get_llm_config
                llm_config = get_llm_config()
                
                # Connection pool configuration
                pool_config_dict = llm_config.get("resilience", {}).get("connection_pool", {})
                default_config = PoolConfig(
                    max_connections=pool_config_dict.get("max_connections", 100),
                    max_connections_per_host=pool_config_dict.get("max_connections_per_host", 20),
                    keepalive_timeout=pool_config_dict.get("keepalive_timeout", 30.0),
                    connect_timeout=pool_config_dict.get("connect_timeout", 3.0),  # Reduced to 3s
                    sock_connect=pool_config_dict.get("sock_connect", 2.0),  # Socket connection 2s
                    sock_read=pool_config_dict.get("sock_read", 30.0),  # Read 30s
                    read_timeout=pool_config_dict.get("read_timeout", 60.0),
                    total_timeout=pool_config_dict.get("total_timeout", 90.0),
                )
                
                _global_http_pool = AsyncHTTPPool(default_config)
                logger.info("Global HTTP connection pool initialized")
    
    return _global_http_pool


async def close_global_http_pool():
    """Close global HTTP connection pool"""
    global _global_http_pool
    if _global_http_pool is not None:
        await _global_http_pool.close()
        _global_http_pool = None
        logger.info("Global HTTP connection pool closed")

