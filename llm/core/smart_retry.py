"""
Smart retry strategy

Production-grade retry mechanism based on tenacity library:
1. Exponential backoff + random jitter
2. Retryable error classification
3. Maximum retry limit
4. Retry callbacks and monitoring
"""

import asyncio
import time
from typing import Optional, Callable, Any, Type, Tuple
from dataclasses import dataclass
import aiohttp

from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
    wait_random,
    before_sleep_log,
    after_log,
    RetryCallState,
)

from timem.utils.logging import get_logger

logger = get_logger(__name__)


class RetryableError(Exception):
    """Retryable error base class"""
    pass


class NetworkError(RetryableError):
    """Network error"""
    pass


class RateLimitError(RetryableError):
    """Rate limit error"""
    pass


class ServerError(RetryableError):
    """Server error"""
    pass


class TimeoutError(RetryableError):
    """Timeout error"""
    pass


@dataclass
class RetryConfig:
    """Retry configuration"""
    max_attempts: int = 3  # Maximum retry attempts
    base_delay: float = 1.0  # Base delay (seconds)
    max_delay: float = 10.0  # Maximum delay (seconds)
    exponential_base: int = 2  # Exponential base
    jitter: bool = True  # Whether to add random jitter
    jitter_max: float = 2.0  # Maximum jitter time (seconds)
    
    # Retryable exception types
    retryable_exceptions: Tuple[Type[Exception], ...] = (
        NetworkError,
        RateLimitError,
        ServerError,
        TimeoutError,
        aiohttp.ClientError,
        aiohttp.ServerTimeoutError,
        asyncio.TimeoutError,
    )


class SmartRetry:
    """
    Smart retry manager
    
    Provides unified retry strategy and error classification.
    """
    
    def __init__(self, config: Optional[RetryConfig] = None, name: str = "default"):
        """
        Initialize smart retry manager
        
        Args:
            config: Retry configuration
            name: Retrier name (for logging)
        """
        self.config = config or RetryConfig()
        self.name = name
        
        # Retry statistics
        self._total_attempts = 0
        self._total_retries = 0
        self._total_failures = 0
        
        logger.info(
            f"Smart retrier [{name}] initialized: "
            f"max_attempts={self.config.max_attempts}, "
            f"base_delay={self.config.base_delay}s"
        )
    
    def _is_retryable_error(self, exception: Exception) -> bool:
        """
        Determine if exception is retryable
        
        Args:
            exception: Exception object
            
        Returns:
            Whether retryable
        """
        # Check if configured retryable exception type
        if isinstance(exception, self.config.retryable_exceptions):
            return True
        
        # Check HTTP status code (if HTTP error)
        if isinstance(exception, aiohttp.ClientResponseError):
            status = exception.status
            # 429: rate limit, 5xx: server error
            if status == 429 or 500 <= status < 600:
                return True
        
        # Check error message keywords
        error_msg = str(exception).lower()
        retryable_keywords = [
            'connection', 'timeout', 'network', 'failed',
            'rate limit', 'too many requests', 'unavailable',
            'temporary', 'retry', '429', '500', '502', '503', '504'
        ]
        
        if any(keyword in error_msg for keyword in retryable_keywords):
            return True
        
        return False
    
    def _classify_error(self, exception: Exception) -> Type[RetryableError]:
        """
        Error classification
        
        Args:
            exception: Exception object
            
        Returns:
            Error type
        """
        if isinstance(exception, RetryableError):
            return type(exception)
        
        # HTTP response error
        if isinstance(exception, aiohttp.ClientResponseError):
            if exception.status == 429:
                return RateLimitError
            elif 500 <= exception.status < 600:
                return ServerError
        
        # Timeout error
        if isinstance(exception, (asyncio.TimeoutError, aiohttp.ServerTimeoutError)):
            return TimeoutError
        
        # Network connection error
        if isinstance(exception, (aiohttp.ClientConnectorError, aiohttp.ClientConnectionError)):
            return NetworkError
        
        # Other HTTP client error
        if isinstance(exception, aiohttp.ClientError):
            return NetworkError
        
        # String matching
        error_msg = str(exception).lower()
        if 'rate limit' in error_msg or '429' in error_msg:
            return RateLimitError
        elif 'timeout' in error_msg:
            return TimeoutError
        elif any(kw in error_msg for kw in ['connection', 'network']):
            return NetworkError
        elif any(kw in error_msg for kw in ['500', '502', '503', '504', 'server']):
            return ServerError
        
        # Default return NetworkError
        return NetworkError
    
    def _before_sleep_callback(self, retry_state: RetryCallState):
        """Callback before retry"""
        if retry_state.outcome and retry_state.outcome.failed:
            exception = retry_state.outcome.exception()
            attempt_number = retry_state.attempt_number
            
            # Classify error
            error_type = self._classify_error(exception)
            
            logger.warning(
                f"Retrier [{self.name}] attempt {attempt_number} failed "
                f"(error type: {error_type.__name__}): {exception}, "
                f"will retry after {retry_state.next_action.sleep}s"
            )
    
    def _after_callback(self, retry_state: RetryCallState):
        """Callback after retry"""
        self._total_attempts += 1
        
        if retry_state.attempt_number > 1:
            self._total_retries += retry_state.attempt_number - 1
        
        if retry_state.outcome and retry_state.outcome.failed:
            self._total_failures += 1
            logger.error(
                f"Retrier [{self.name}] final failure, attempts: {retry_state.attempt_number}"
            )
    
    async def execute(
        self, 
        func: Callable, 
        *args, 
        **kwargs
    ) -> Any:
        """
        Execute async function with retry
        
        Args:
            func: Async function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Function return value
            
        Raises:
            Exception: Original exception after retry failure
        """
        # Build wait strategy
        wait_strategy = wait_exponential(
            multiplier=self.config.base_delay,
            min=self.config.base_delay,
            max=self.config.max_delay,
            exp_base=self.config.exponential_base
        )
        
        if self.config.jitter:
            wait_strategy = wait_strategy + wait_random(0, self.config.jitter_max)
        
        # Create retrier
        retryer = AsyncRetrying(
            # Stop strategy: maximum attempts
            stop=stop_after_attempt(self.config.max_attempts),
            
            # Wait strategy: exponential backoff + jitter
            wait=wait_strategy,
            
            # Retry condition: retryable exceptions
            retry=retry_if_exception(self._is_retryable_error),
            
            # Callbacks
            before_sleep=self._before_sleep_callback,
            after=self._after_callback,
            
            # Re-raise exception
            reraise=True,
        )
        
        # Execute retry
        try:
            async for attempt in retryer:
                with attempt:
                    result = await func(*args, **kwargs)
                    return result
        except Exception as e:
            # Classify and log final failure
            error_type = self._classify_error(e)
            logger.error(
                f"Retrier [{self.name}] execution failed "
                f"(error type: {error_type.__name__}): {e}"
            )
            raise
    
    def get_stats(self) -> dict:
        """Get retry statistics"""
        return {
            "name": self.name,
            "total_attempts": self._total_attempts,
            "total_retries": self._total_retries,
            "total_failures": self._total_failures,
            "retry_rate": self._total_retries / self._total_attempts if self._total_attempts > 0 else 0,
            "failure_rate": self._total_failures / self._total_attempts if self._total_attempts > 0 else 0,
        }


# Convenient decorator
def smart_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    name: str = "default"
):
    """
    Smart retry decorator
    
    Args:
        max_attempts: Maximum retry attempts
        base_delay: Base delay (seconds)
        max_delay: Maximum delay (seconds)
        name: Retrier name
        
    Example:
        @smart_retry(max_attempts=3, base_delay=1.0)
        async def call_llm_api():
            # LLM API call
            pass
    """
    config = RetryConfig(
        max_attempts=max_attempts,
        base_delay=base_delay,
        max_delay=max_delay,
    )
    retry_manager = SmartRetry(config, name)
    
    def decorator(func):
        async def wrapper(*args, **kwargs):
            return await retry_manager.execute(func, *args, **kwargs)
        return wrapper
    
    return decorator


class RetryManager:
    """
    Retry manager
    
    Manages independent retriers for different providers.
    """
    
    def __init__(self):
        """Initialize retry manager"""
        self._retriers: dict[str, SmartRetry] = {}
        logger.info("Retry manager initialized")
    
    def get_retrier(
        self, 
        name: str, 
        config: Optional[RetryConfig] = None
    ) -> SmartRetry:
        """
        Get or create retrier
        
        Args:
            name: Retrier name
            config: Retry configuration (used only on creation)
            
        Returns:
            SmartRetry instance
        """
        if name not in self._retriers:
            self._retriers[name] = SmartRetry(config, name)
        
        return self._retriers[name]
    
    def get_all_stats(self) -> dict[str, dict]:
        """Get statistics for all retriers"""
        return {
            name: retrier.get_stats()
            for name, retrier in self._retriers.items()
        }


# Global retry manager (singleton)
_global_retry_manager: Optional[RetryManager] = None


def get_global_retry_manager() -> RetryManager:
    """
    Get global retry manager (singleton)
    
    Returns:
        RetryManager instance
    """
    global _global_retry_manager
    
    if _global_retry_manager is None:
        _global_retry_manager = RetryManager()
        logger.info("Global retry manager initialized")
    
    return _global_retry_manager

