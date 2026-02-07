"""
Unified HTTP Client Management Module

Provides engineering-grade HTTP client management with support for:
1. Connection pool reuse
2. Fine-grained timeout control (connection timeout, read timeout, write timeout)
3. Automatic retry mechanism
4. Concurrency control
5. Performance monitoring
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any, Callable
from enum import Enum
import httpx

from timem.utils.logging import get_logger

logger = get_logger(__name__)


class HTTPErrorType(Enum):
    """HTTP error type classification"""
    # Retryable errors
    NETWORK_ERROR = "network_error"  # Network error (connection failed, timeout, etc.)
    SERVER_ERROR = "server_error"    # 5xx server error
    RATE_LIMIT = "rate_limit"       # 429 rate limit
    
    # Non-retryable errors
    CLIENT_ERROR = "client_error"    # 4xx client error (except 429)
    AUTH_ERROR = "auth_error"        # 401/403 authentication error
    NOT_FOUND = "not_found"         # 404 not found
    
    # Unknown error
    UNKNOWN = "unknown"


@dataclass
class TimeoutConfig:
    """Timeout configuration"""
    connect_timeout: float = 30.0      # Connection timeout (seconds)
    read_timeout: float = 60.0         # Read timeout (seconds)
    write_timeout: float = 60.0        # Write timeout (seconds)
    pool_timeout: float = 30.0         # Connection pool timeout (seconds)
    
    def to_httpx_timeout(self) -> httpx.Timeout:
        """Convert to httpx.Timeout object"""
        return httpx.Timeout(
            connect=self.connect_timeout,
            read=self.read_timeout,
            write=self.write_timeout,
            pool=self.pool_timeout
        )


@dataclass
class RetryConfig:
    """Retry configuration"""
    max_retries: int = 3               # Maximum retry attempts
    base_delay: float = 0.5            # Base delay (seconds)
    max_delay: float = 10.0            # Maximum delay (seconds)
    backoff_factor: float = 2.0        # Backoff factor
    jitter: bool = True                # Whether to add random jitter
    retry_on_status: list = None       # Status codes to retry on
    
    def __post_init__(self):
        if self.retry_on_status is None:
            # Default to retrying 5xx server errors and 429 rate limit
            self.retry_on_status = [429, 500, 502, 503, 504]


@dataclass
class ConnectionPoolConfig:
    """Connection pool configuration"""
    max_connections: int = 100          # Maximum connections
    max_keepalive_connections: int = 20 # Maximum keepalive connections
    keepalive_expiry: float = 30.0      # Keepalive expiry (seconds)


class HTTPClientManager:
    """Unified HTTP Client Manager
    
    Provides the following features:
    1. Connection pool management
    2. Timeout control
    3. Retry mechanism
    4. Error handling
    5. Performance monitoring
    """
    
    def __init__(
        self,
        timeout_config: Optional[TimeoutConfig] = None,
        retry_config: Optional[RetryConfig] = None,
        pool_config: Optional[ConnectionPoolConfig] = None
    ):
        self.timeout_config = timeout_config or TimeoutConfig()
        self.retry_config = retry_config or RetryConfig()
        self.pool_config = pool_config or ConnectionPoolConfig()
        
        # Create async HTTP client
        self._client: Optional[httpx.AsyncClient] = None
        self._init_lock = asyncio.Lock()
        
        # Performance statistics
        self._stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "retried_requests": 0,
            "total_retry_count": 0,
            "total_latency": 0.0
        }
        
        logger.info(f"HTTP client manager initialized: "
                   f"connect timeout={self.timeout_config.connect_timeout}s, "
                   f"read timeout={self.timeout_config.read_timeout}s, "
                   f"max retries={self.retry_config.max_retries}")
    
    async def _ensure_client(self):
        """Ensure HTTP client is initialized"""
        if self._client is None:
            async with self._init_lock:
                if self._client is None:
                    limits = httpx.Limits(
                        max_connections=self.pool_config.max_connections,
                        max_keepalive_connections=self.pool_config.max_keepalive_connections,
                        keepalive_expiry=self.pool_config.keepalive_expiry
                    )
                    
                    self._client = httpx.AsyncClient(
                        timeout=self.timeout_config.to_httpx_timeout(),
                        limits=limits,
                        http2=True  # Enable HTTP/2 support
                    )
                    logger.info("Async HTTP client initialized")
    
    def _classify_error(self, error: Exception) -> HTTPErrorType:
        """Classify HTTP error
        
        Args:
            error: Error object
        
        Returns:
            HTTPErrorType: Error type
        """
        error_msg = str(error).lower()
        
        # HTTP response error
        if isinstance(error, httpx.HTTPStatusError):
            status_code = error.response.status_code
            if status_code == 429:
                return HTTPErrorType.RATE_LIMIT
            elif status_code in (401, 403):
                return HTTPErrorType.AUTH_ERROR
            elif status_code == 404:
                return HTTPErrorType.NOT_FOUND
            elif 400 <= status_code < 500:
                return HTTPErrorType.CLIENT_ERROR
            elif 500 <= status_code < 600:
                return HTTPErrorType.SERVER_ERROR
        
        # Network-related error
        if isinstance(error, (httpx.ConnectError, httpx.ConnectTimeout)):
            return HTTPErrorType.NETWORK_ERROR
        
        if isinstance(error, (httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout)):
            return HTTPErrorType.NETWORK_ERROR
        
        # String matching
        network_keywords = [
            'connection', 'timeout', 'network', 'failed',
            'refused', 'reset', 'broken pipe', 'no route'
        ]
        if any(keyword in error_msg for keyword in network_keywords):
            return HTTPErrorType.NETWORK_ERROR
        
        return HTTPErrorType.UNKNOWN
    
    def _should_retry(self, error_type: HTTPErrorType, attempt: int) -> bool:
        """Determine if retry is needed
        
        Args:
            error_type: Error type
            attempt: Attempt number
        
        Returns:
            bool: Whether to retry
        """
        if attempt >= self.retry_config.max_retries:
            return False
        
        # Retryable error types
        retryable_types = {
            HTTPErrorType.NETWORK_ERROR,
            HTTPErrorType.SERVER_ERROR,
            HTTPErrorType.RATE_LIMIT,
            HTTPErrorType.UNKNOWN  # Also retry unknown errors
        }
        
        return error_type in retryable_types
    
    def _calculate_retry_delay(self, attempt: int) -> float:
        """Calculate retry delay
        
        Args:
            attempt: Attempt number
        
        Returns:
            float: Retry delay
        """
        # Exponential backoff
        delay = min(
            self.retry_config.base_delay * (self.retry_config.backoff_factor ** attempt),
            self.retry_config.max_delay
        )
        
        # Add random jitter (to avoid thundering herd effect)
        if self.retry_config.jitter:
            import random
            delay = delay * (0.5 + random.random())
        
        return delay
    
    async def request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        timeout_override: Optional[TimeoutConfig] = None,
        retry_override: Optional[RetryConfig] = None,
        **kwargs
    ) -> httpx.Response:
        """
        Send HTTP request (with automatic retry)
        
        Args:
            method: HTTP method
            url: Request URL
            headers: Request headers
            json_data: JSON data
            params: Query parameters
            timeout_override: Override default timeout configuration
            retry_override: Override default retry configuration
            **kwargs: Other httpx parameters
        
        Returns:
            httpx.Response: Response object
        
        Raises:
            httpx.HTTPError: HTTP request error
        """
        await self._ensure_client()
        
        retry_config = retry_override or self.retry_config
        timeout_config = timeout_override or self.timeout_config
        
        self._stats["total_requests"] += 1
        start_time = time.time()
        
        last_error = None
        for attempt in range(retry_config.max_retries + 1):
            try:
                # Send request
                response = await self._client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=json_data,
                    params=params,
                    timeout=timeout_config.to_httpx_timeout(),
                    **kwargs
                )
                
                # Check response status
                response.raise_for_status()
                
                # Success
                latency = time.time() - start_time
                self._stats["successful_requests"] += 1
                self._stats["total_latency"] += latency
                
                if attempt > 0:
                    self._stats["retried_requests"] += 1
                    self._stats["total_retry_count"] += attempt
                    logger.info(f"Request successful (after {attempt} retries): {method} {url}, latency={latency:.2f}s")
                else:
                    logger.debug(f"Request successful: {method} {url}, latency={latency:.2f}s")
                
                return response
                
            except Exception as e:
                last_error = e
                error_type = self._classify_error(e)
                
                # Determine if retry is needed
                should_retry = self._should_retry(error_type, attempt)
                
                if should_retry:
                    delay = self._calculate_retry_delay(attempt)
                    logger.warning(
                        f"Request failed (attempt {attempt + 1}/{retry_config.max_retries + 1}), "
                        f"error type={error_type.value}, "
                        f"{delay:.2f} seconds before retrying: {method} {url} - {str(e)[:100]}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"Request failed (non-retryable), error type={error_type.value}: "
                        f"{method} {url} - {e}"
                    )
                    break
        
        # All retries failed
        self._stats["failed_requests"] += 1
        latency = time.time() - start_time
        self._stats["total_latency"] += latency
        
        logger.error(
            f"Request failed (all retries exhausted): {method} {url}, "
            f"total attempts={retry_config.max_retries + 1}, "
            f"total latency={latency:.2f}s"
        )
        raise last_error
    
    async def get(self, url: str, **kwargs) -> httpx.Response:
        """Execute GET request
        
        Args:
            url: Request URL
            **kwargs: Other parameters
        
        Returns:
            httpx.Response: Response object
        """
        return await self.request("GET", url, **kwargs)
    
    async def post(self, url: str, **kwargs) -> httpx.Response:
        """Execute POST request
        
        Args:
            url: Request URL
            **kwargs: Other parameters
        
        Returns:
            httpx.Response: Response object
        """
        return await self.request("POST", url, **kwargs)
    
    async def put(self, url: str, **kwargs) -> httpx.Response:
        """Execute PUT request
        
        Args:
            url: Request URL
            **kwargs: Other parameters
        
        Returns:
            httpx.Response: Response object
        """
        return await self.request("PUT", url, **kwargs)
    
    async def delete(self, url: str, **kwargs) -> httpx.Response:
        """Execute DELETE request
        
        Args:
            url: Request URL
            **kwargs: Other parameters
        
        Returns:
            httpx.Response: Response object
        """
        return await self.request("DELETE", url, **kwargs)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get performance statistics
        
        Returns:
            Dict[str, Any]: Statistics
        """
        stats = self._stats.copy()
        if stats["successful_requests"] > 0:
            stats["avg_latency"] = stats["total_latency"] / stats["successful_requests"]
            stats["success_rate"] = stats["successful_requests"] / stats["total_requests"]
        else:
            stats["avg_latency"] = 0.0
            stats["success_rate"] = 0.0
        
        return stats
    
    def reset_stats(self):
        """Reset statistics"""
        self._stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "retried_requests": 0,
            "total_retry_count": 0,
            "total_latency": 0.0
        }
    
    async def close(self):
        """Close HTTP client"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.info("HTTP client closed")
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self._ensure_client()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()


# Global client manager instance (singleton)
_global_client_manager: Optional[HTTPClientManager] = None
_global_client_lock = asyncio.Lock()


async def get_global_http_client() -> HTTPClientManager:
    """Get global HTTP client manager (singleton)"""
    global _global_client_manager
    
    if _global_client_manager is None:
        async with _global_client_lock:
            if _global_client_manager is None:
                # Load timeout and retry settings from configuration
                from timem.utils.config_manager import get_llm_config
                llm_config = get_llm_config()
                
                timeout_config = TimeoutConfig(
                    connect_timeout=llm_config.get("connect_timeout", 30.0),
                    read_timeout=llm_config.get("read_timeout", 60.0),
                    write_timeout=llm_config.get("write_timeout", 60.0),
                    pool_timeout=llm_config.get("pool_timeout", 30.0)
                )
                
                retry_config = RetryConfig(
                    max_retries=llm_config.get("max_retries", 3),
                    base_delay=llm_config.get("retry_base_delay", 0.5),
                    max_delay=llm_config.get("retry_max_delay", 10.0),
                    backoff_factor=llm_config.get("retry_backoff_factor", 2.0),
                    jitter=llm_config.get("retry_jitter", True)
                )
                
                pool_config = ConnectionPoolConfig(
                    max_connections=llm_config.get("max_connections", 100),
                    max_keepalive_connections=llm_config.get("max_keepalive_connections", 20),
                    keepalive_expiry=llm_config.get("keepalive_expiry", 30.0)
                )
                
                _global_client_manager = HTTPClientManager(
                    timeout_config=timeout_config,
                    retry_config=retry_config,
                    pool_config=pool_config
                )
                
                logger.info("Global HTTP client manager initialization complete")
    
    return _global_client_manager


async def close_global_http_client():
    """Close global HTTP client manager"""
    global _global_client_manager
    if _global_client_manager is not None:
        await _global_client_manager.close()
        _global_client_manager = None

