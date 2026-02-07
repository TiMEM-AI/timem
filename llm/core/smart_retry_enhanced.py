"""
Enhanced smart retry mechanism

Provides multiple retry strategies to ensure requests eventually succeed, never using fallback content.
"""

import asyncio
import time
import random
from enum import Enum
from typing import Callable, Any, Optional, List
from dataclasses import dataclass

from timem.utils.logging import get_logger
from timem.utils.config_manager import get_llm_config

logger = get_logger(__name__)


class RetryStrategy(Enum):
    """Retry strategy"""
    FAST_FAIL = "fast_fail"         # Fast fail, max 2 attempts
    NORMAL = "normal"                # Normal retry, max 3 attempts
    AGGRESSIVE = "aggressive"        # Aggressive retry, max 5 attempts
    GUARANTEED = "guaranteed"        # Guaranteed success, max 10 attempts


@dataclass
class EnhancedRetryConfig:
    """Enhanced retry configuration"""
    strategy: RetryStrategy = RetryStrategy.NORMAL
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0
    jitter: bool = True
    multi_key_fallback: bool = True  # Support multi-key rotation
    guaranteed_response: bool = False  # Guaranteed response mode


class EnhancedSmartRetry:
    """Enhanced smart retrier"""
    
    def __init__(self, name: str, config: Optional[EnhancedRetryConfig] = None):
        """
        Initialize enhanced retrier
        
        Args:
            name: Retrier name
            config: Retry configuration
        """
        self.name = name
        self.config = config or EnhancedRetryConfig()
        
        # Statistics
        self._consecutive_failures = 0
        self._total_attempts = 0
        self._total_successes = 0
        self._total_failures = 0
        self._last_success_time = time.time()
        
        logger.info(
            f"Enhanced retrier [{name}] initialized: strategy={self.config.strategy.value}, "
            f"max_attempts={self.config.max_attempts}, guaranteed={self.config.guaranteed_response}"
        )
    
    async def execute_with_strategy(
        self,
        func: Callable,
        strategy: Optional[RetryStrategy] = None,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute retry based on strategy
        
        Args:
            func: Async function to execute
            strategy: Retry strategy (None uses default)
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Function execution result
            
        Raises:
            Exception from last attempt
        """
        strategy = strategy or self.config.strategy
        
        # Determine retry parameters based on strategy
        if strategy == RetryStrategy.FAST_FAIL:
            max_attempts = 2
            base_delay = 0.5
        elif strategy == RetryStrategy.NORMAL:
            max_attempts = 3
            base_delay = 1.0
        elif strategy == RetryStrategy.AGGRESSIVE:
            max_attempts = 5
            base_delay = 0.5
        elif strategy == RetryStrategy.GUARANTEED:
            max_attempts = 10
            base_delay = 2.0
        else:
            max_attempts = self.config.max_attempts
            base_delay = self.config.base_delay
        
        # If guaranteed response mode, use more attempts
        if self.config.guaranteed_response:
            max_attempts = max(max_attempts, 10)
        
        last_exception = None
        
        for attempt in range(max_attempts):
            self._total_attempts += 1
            
            try:
                # Execute function
                result = await func(*args, **kwargs)
                
                # Validate response
                if not self._is_valid_response(result):
                    logger.warning(
                        f"Retrier [{self.name}] invalid response, attempt {attempt + 1}/{max_attempts}"
                    )
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(base_delay * 0.5)
                        continue
                    else:
                        raise ValueError("Invalid response and max retries reached")
                
                # Success
                self._consecutive_failures = 0
                self._total_successes += 1
                self._last_success_time = time.time()
                
                logger.debug(
                    f"Retrier [{self.name}] execution succeeded, attempts: {attempt + 1}"
                )
                
                return result
                
            except Exception as e:
                last_exception = e
                self._consecutive_failures += 1
                
                # Log failure
                logger.warning(
                    f"Retrier [{self.name}] attempt {attempt + 1}/{max_attempts} failed: "
                    f"{type(e).__name__}: {e}"
                )
                
                # Check if can retry
                if attempt >= max_attempts - 1:
                    # Guaranteed response mode: continue retrying even after max attempts
                    if self.config.guaranteed_response and strategy == RetryStrategy.GUARANTEED:
                        logger.error(
                            f"Retrier [{self.name}] guaranteed response mode, continuing retry..."
                        )
                        await asyncio.sleep(base_delay * 2)
                        # Don't increment attempt, continue loop
                        attempt -= 1  # Offset for loop increment
                        max_attempts += 1  # Increase max attempts
                        continue
                    else:
                        # Log final failure
                        self._total_failures += 1
                        logger.error(
                            f"Retrier [{self.name}] final failure, total attempts: {attempt + 1}, "
                            f"consecutive failures: {self._consecutive_failures}"
                        )
                        raise
                
                # Calculate retry delay
                delay = self._calculate_adaptive_delay(
                    attempt,
                    base_delay,
                    strategy
                )
                
                logger.info(
                    f"Retrier [{self.name}] will retry after {delay:.2f}s..."
                )
                
                await asyncio.sleep(delay)
        
        # Should not reach here (protective code)
        if last_exception:
            self._total_failures += 1
            raise last_exception
    
    async def execute_with_multi_keys(
        self,
        func: Callable,
        api_keys: List[str],
        *args,
        **kwargs
    ) -> Any:
        """
        Retry using multiple API Keys
        
        Automatically switch to next key when one fails to improve success rate
        
        Args:
            func: Function to execute (accepts api_key as first parameter)
            api_keys: List of API Keys
            *args: Other positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Function execution result
        """
        if not api_keys:
            raise ValueError("API key list is empty")
        
        last_exception = None
        
        for key_index, api_key in enumerate(api_keys):
            try:
                logger.debug(
                    f"Retrier [{self.name}] trying API Key #{key_index + 1}/{len(api_keys)}"
                )
                
                result = await func(api_key, *args, **kwargs)
                
                # Success
                logger.info(
                    f"Retrier [{self.name}] API Key #{key_index + 1} succeeded"
                )
                return result
                
            except Exception as e:
                last_exception = e
                logger.warning(
                    f"Retrier [{self.name}] API Key #{key_index + 1} failed: {e}"
                )
                
                # If there are other keys, continue after brief delay
                if key_index < len(api_keys) - 1:
                    await asyncio.sleep(0.5)
                else:
                    # All keys failed
                    logger.error(
                        f"Retrier [{self.name}] all {len(api_keys)} API Keys failed"
                    )
                    raise
        
        # Protective code
        if last_exception:
            raise last_exception
    
    def _calculate_adaptive_delay(
        self,
        attempt: int,
        base_delay: float,
        strategy: RetryStrategy
    ) -> float:
        """
        Calculate adaptive retry delay
        
        Args:
            attempt: Current attempt number (starting from 0)
            base_delay: Base delay
            strategy: Retry strategy
            
        Returns:
            Delay time (seconds)
        """
        # Exponential backoff: delay = base_delay * (exponential_base ^ attempt)
        delay = base_delay * (self.config.exponential_base ** attempt)
        
        # Adjust based on consecutive failures
        if self._consecutive_failures > 5:
            # Multiple consecutive failures, increase delay
            delay *= 1.5
            logger.debug(
                f"Retrier [{self.name}] {self._consecutive_failures} consecutive failures, increasing delay"
            )
        
        # Adjust based on strategy
        if strategy == RetryStrategy.FAST_FAIL:
            delay *= 0.5  # Fast fail, reduce delay
        elif strategy == RetryStrategy.AGGRESSIVE:
            delay *= 0.7  # Aggressive retry, slightly reduce delay
        elif strategy == RetryStrategy.GUARANTEED:
            delay *= 1.2  # Guaranteed success, slightly increase delay
        
        # Add jitter (avoid thundering herd)
        if self.config.jitter:
            jitter_factor = 0.8 + random.random() * 0.4  # 0.8-1.2
            delay *= jitter_factor
        
        # Limit maximum delay
        max_delay = self.config.max_delay
        if strategy == RetryStrategy.GUARANTEED:
            max_delay = max(max_delay, 30.0)  # Guaranteed success strategy allows longer delay
        
        delay = min(delay, max_delay)
        
        return delay
    
    def _is_valid_response(self, response: Any) -> bool:
        """
        Validate response validity
        
        Args:
            response: Response object
            
        Returns:
            Whether valid
        """
        if not response:
            return False
        
        # Check ChatResponse
        if hasattr(response, 'content'):
            content = response.content
            if not content or len(content.strip()) == 0:
                return False
            
            # Check if error message
            error_indicators = [
                "error", "failed", "unable", "failed",
                "sorry", "apologize", "sorry"
            ]
            content_lower = content.lower()
            
            # If content is too short and contains error indicators, may be invalid response
            if len(content) < 50 and any(ind in content_lower for ind in error_indicators):
                logger.debug(f"Response appears invalid: {content[:100]}")
                return False
        
        return True
    
    def get_statistics(self) -> dict:
        """Get statistics"""
        success_rate = (
            self._total_successes / self._total_attempts
            if self._total_attempts > 0
            else 0.0
        )
        
        return {
            "name": self.name,
            "total_attempts": self._total_attempts,
            "total_successes": self._total_successes,
            "total_failures": self._total_failures,
            "success_rate": success_rate,
            "consecutive_failures": self._consecutive_failures,
            "last_success_time": self._last_success_time,
        }
    
    def reset_statistics(self):
        """Reset statistics"""
        self._consecutive_failures = 0
        self._total_attempts = 0
        self._total_successes = 0
        self._total_failures = 0
        logger.info(f"Retrier [{self.name}] statistics reset")


# Global enhanced retry manager
class EnhancedRetryManager:
    """Enhanced retry manager"""
    
    def __init__(self):
        """Initialize manager"""
        self._retriers: dict[str, EnhancedSmartRetry] = {}
        logger.info("Enhanced retry manager initialized")
    
    def get_retrier(
        self,
        name: str,
        config: Optional[EnhancedRetryConfig] = None
    ) -> EnhancedSmartRetry:
        """
        Get or create retrier
        
        Args:
            name: Retrier name
            config: Retry configuration
            
        Returns:
            Enhanced retrier instance
        """
        if name not in self._retriers:
            if config is None:
                # Load from config file
                llm_config = get_llm_config()
                retry_config_dict = llm_config.get("resilience", {}).get("retry", {})
                
                strategy_name = retry_config_dict.get("strategy", "normal")
                strategy = RetryStrategy(strategy_name)
                
                config = EnhancedRetryConfig(
                    strategy=strategy,
                    max_attempts=retry_config_dict.get("max_attempts", 3),
                    base_delay=retry_config_dict.get("base_delay", 1.0),
                    max_delay=retry_config_dict.get("max_delay", 30.0),
                    exponential_base=retry_config_dict.get("exponential_base", 2.0),
                    jitter=retry_config_dict.get("jitter", True),
                    multi_key_fallback=retry_config_dict.get("multi_key_fallback", True),
                    guaranteed_response=retry_config_dict.get("guaranteed_response", False),
                )
            
            self._retriers[name] = EnhancedSmartRetry(name, config)
        
        return self._retriers[name]
    
    def get_all_statistics(self) -> dict:
        """Get statistics for all retriers"""
        return {
            name: retrier.get_statistics()
            for name, retrier in self._retriers.items()
        }


# Global singleton
_global_enhanced_retry_manager: Optional[EnhancedRetryManager] = None


def get_global_enhanced_retry_manager() -> EnhancedRetryManager:
    """Get global enhanced retry manager"""
    global _global_enhanced_retry_manager
    
    if _global_enhanced_retry_manager is None:
        _global_enhanced_retry_manager = EnhancedRetryManager()
        logger.info("Global enhanced retry manager initialized")
    
    return _global_enhanced_retry_manager

