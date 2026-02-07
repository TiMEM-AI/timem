"""
Adaptive rate limiter

Smart rate limiting based on token bucket algorithm:
1. Support independent QPS configuration per provider
2. Dynamically adjust based on 429 response
3. Priority queue support
4. Real-time QPS monitoring
"""

import asyncio
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

from timem.utils.logging import get_logger

logger = get_logger(__name__)


class Priority(int, Enum):
    """Request priority"""
    HIGH = 1  # High priority (conversation)
    NORMAL = 2  # Normal priority
    LOW = 3  # Low priority (batch memory generation)


class RateLimitExceeded(Exception):
    """Rate limit exceeded exception"""
    pass


@dataclass
class RateLimitConfig:
    """Rate limit configuration"""
    qps: float = 50.0  # Requests per second
    burst: int = 10  # Burst capacity (token bucket size)
    
    # Adaptive configuration
    adaptive: bool = True  # Whether to enable adaptive
    min_qps: float = 10.0  # Minimum QPS (adaptive lower limit)
    max_qps: float = 200.0  # Maximum QPS (adaptive upper limit)
    adjust_factor: float = 0.8  # Adjustment factor when 429 triggered
    recovery_factor: float = 1.1  # Adjustment factor for recovery
    recovery_interval: float = 60.0  # Recovery detection interval (seconds)


@dataclass
class RateLimitStats:
    """Rate limit statistics"""
    total_requests: int = 0
    allowed_requests: int = 0
    rejected_requests: int = 0
    rate_limit_hits: int = 0  # Number of times 429 triggered
    current_qps: float = 0.0
    configured_qps: float = 0.0
    avg_wait_time: float = 0.0
    total_wait_time: float = 0.0


class TokenBucket:
    """
    Token bucket algorithm implementation
    
    Used for smooth rate limiting.
    """
    
    def __init__(self, rate: float, capacity: int):
        """
        Initialize token bucket
        
        Args:
            rate: Token generation rate (per second)
            capacity: Bucket capacity
        """
        self.rate = rate
        self.capacity = capacity
        self.tokens = float(capacity)
        self.last_update = time.time()
        self._lock = asyncio.Lock()
    
    def _refill(self):
        """Refill tokens"""
        now = time.time()
        elapsed = now - self.last_update
        
        # Add new tokens
        new_tokens = elapsed * self.rate
        self.tokens = min(self.capacity, self.tokens + new_tokens)
        self.last_update = now
    
    async def acquire(self, tokens: int = 1, timeout: Optional[float] = None) -> bool:
        """
        Acquire tokens
        
        Args:
            tokens: Number of tokens needed
            timeout: Timeout time (seconds), None means infinite wait
            
        Returns:
            Whether tokens were successfully acquired
            
        Raises:
            RateLimitExceeded: Timeout without acquiring tokens
        """
        start_time = time.time()
        
        while True:
            async with self._lock:
                self._refill()
                
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return True
                
                # Calculate wait time needed
                needed_tokens = tokens - self.tokens
                wait_time = needed_tokens / self.rate
            
            # Check timeout
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    raise RateLimitExceeded(f"Token acquisition timeout: {timeout}s")
                
                # Adjust wait time
                wait_time = min(wait_time, timeout - elapsed)
            
            # Wait and retry
            await asyncio.sleep(wait_time)
    
    def update_rate(self, new_rate: float):
        """Update token generation rate"""
        with self._lock:
            self._refill()
            self.rate = new_rate


class AdaptiveRateLimiter:
    """
    Adaptive rate limiter
    
    Based on token bucket algorithm, supports dynamic QPS adjustment.
    """
    
    def __init__(
        self, 
        name: str, 
        config: Optional[RateLimitConfig] = None
    ):
        """
        Initialize rate limiter
        
        Args:
            name: Rate limiter name (usually provider name)
            config: Rate limit configuration
        """
        self.name = name
        self.config = config or RateLimitConfig()
        
        # Current QPS
        self._current_qps = self.config.qps
        
        # Token bucket
        self._bucket = TokenBucket(self._current_qps, self.config.burst)
        
        # Statistics
        self._stats = RateLimitStats(
            configured_qps=self._current_qps,
            current_qps=self._current_qps
        )
        
        # QPS monitoring
        self._request_times: list[float] = []
        self._qps_window = 1.0  # 1 second window
        
        # Recovery task
        self._recovery_task: Optional[asyncio.Task] = None
        
        # Last time 429 was triggered
        self._last_rate_limit_time = 0.0
        
        # Lock
        self._lock = asyncio.Lock()
        
        logger.info(
            f"Rate limiter [{name}] initialized: "
            f"qps={self.config.qps}, burst={self.config.burst}, "
            f"adaptive={self.config.adaptive}"
        )
    
    def _calculate_current_qps(self) -> float:
        """Calculate current actual QPS"""
        now = time.time()
        cutoff = now - self._qps_window
        
        # Remove old request times
        self._request_times = [t for t in self._request_times if t > cutoff]
        
        # Calculate QPS
        if not self._request_times:
            return 0.0
        
        return len(self._request_times) / self._qps_window
    
    async def _start_recovery(self):
        """Start QPS recovery task"""
        if self._recovery_task and not self._recovery_task.done():
            return
        
        async def recovery_loop():
            """Recovery loop"""
            while True:
                try:
                    await asyncio.sleep(self.config.recovery_interval)
                    
                    # Check if recovery needed
                    time_since_last_limit = time.time() - self._last_rate_limit_time
                    if time_since_last_limit >= self.config.recovery_interval:
                        async with self._lock:
                            old_qps = self._current_qps
                            new_qps = min(
                                self._current_qps * self.config.recovery_factor,
                                self.config.max_qps
                            )
                            
                            if new_qps != old_qps:
                                self._current_qps = new_qps
                                self._bucket.update_rate(new_qps)
                                self._stats.current_qps = new_qps
                                
                                logger.info(
                                    f"Rate limiter [{self.name}] QPS recovery: "
                                    f"{old_qps:.1f} → {new_qps:.1f}"
                                )
                
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Rate limiter [{self.name}] recovery task exception: {e}")
        
        self._recovery_task = asyncio.create_task(recovery_loop())
    
    async def acquire(
        self, 
        priority: Priority = Priority.NORMAL, 
        timeout: Optional[float] = 60.0
    ) -> bool:
        """
        Acquire request permission
        
        Args:
            priority: Request priority
            timeout: Timeout time (seconds)
            
        Returns:
            Whether permission was successfully acquired
            
        Raises:
            RateLimitExceeded: Timeout without acquiring permission
        """
        start_time = time.time()
        
        # Update statistics
        self._stats.total_requests += 1
        
        # Priority handling (high priority gets more token capacity)
        tokens_needed = 1
        if priority == Priority.HIGH:
            tokens_needed = 1  # High priority normal consumption
        elif priority == Priority.LOW:
            tokens_needed = 1  # Low priority also normal consumption (controlled via timeout)
        
        try:
            # Acquire tokens
            await self._bucket.acquire(tokens_needed, timeout)
            
            # Record request time
            now = time.time()
            self._request_times.append(now)
            
            # Update statistics
            wait_time = now - start_time
            self._stats.allowed_requests += 1
            self._stats.total_wait_time += wait_time
            self._stats.avg_wait_time = (
                self._stats.total_wait_time / self._stats.allowed_requests
            )
            self._stats.current_qps = self._calculate_current_qps()
            
            return True
        
        except RateLimitExceeded:
            self._stats.rejected_requests += 1
            logger.warning(
                f"Rate limiter [{self.name}] rejected request "
                f"(timeout: {timeout}s, priority: {priority.name})"
            )
            raise
    
    async def report_rate_limit(self):
        """
        Report 429 rate limit triggered
        
        Trigger adaptive adjustment to lower QPS.
        """
        if not self.config.adaptive:
            return
        
        async with self._lock:
            self._stats.rate_limit_hits += 1
            self._last_rate_limit_time = time.time()
            
            old_qps = self._current_qps
            new_qps = max(
                self._current_qps * self.config.adjust_factor,
                self.config.min_qps
            )
            
            if new_qps != old_qps:
                self._current_qps = new_qps
                self._bucket.update_rate(new_qps)
                self._stats.current_qps = new_qps
                
                logger.warning(
                    f"Rate limiter [{self.name}] detected 429 response, lowering QPS: "
                    f"{old_qps:.1f} → {new_qps:.1f}"
                )
            
            # Start recovery task
            await self._start_recovery()
    
    def update_qps(self, new_qps: float):
        """
        Manually update QPS
        
        Args:
            new_qps: New QPS value
        """
        with self._lock:
            old_qps = self._current_qps
            self._current_qps = max(self.config.min_qps, min(new_qps, self.config.max_qps))
            self._bucket.update_rate(self._current_qps)
            self._stats.current_qps = self._current_qps
            self._stats.configured_qps = new_qps
            
            logger.info(
                f"Rate limiter [{self.name}] QPS updated: "
                f"{old_qps:.1f} → {self._current_qps:.1f}"
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics"""
        return {
            "name": self.name,
            "configured_qps": self._stats.configured_qps,
            "current_qps": self._calculate_current_qps(),
            "target_qps": self._current_qps,
            "total_requests": self._stats.total_requests,
            "allowed_requests": self._stats.allowed_requests,
            "rejected_requests": self._stats.rejected_requests,
            "rate_limit_hits": self._stats.rate_limit_hits,
            "avg_wait_time": self._stats.avg_wait_time,
            "allow_rate": (
                self._stats.allowed_requests / self._stats.total_requests 
                if self._stats.total_requests > 0 else 0.0
            ),
        }
    
    async def close(self):
        """Close rate limiter"""
        if self._recovery_task:
            self._recovery_task.cancel()
            try:
                await self._recovery_task
            except asyncio.CancelledError:
                pass
        
        logger.info(f"Rate limiter [{self.name}] closed")


class RateLimiterManager:
    """
    Rate limiter manager
    
    Manages independent rate limiters for different providers.
    """
    
    def __init__(self):
        """Initialize rate limiter manager"""
        self._limiters: Dict[str, AdaptiveRateLimiter] = {}
        self._lock = asyncio.Lock()
        logger.info("Rate limiter manager initialized")
    
    async def get_limiter(
        self, 
        name: str, 
        config: Optional[RateLimitConfig] = None
    ) -> AdaptiveRateLimiter:
        """
        Get or create rate limiter
        
        Args:
            name: Rate limiter name
            config: Rate limit configuration (used only on creation)
            
        Returns:
            AdaptiveRateLimiter instance
        """
        if name not in self._limiters:
            async with self._lock:
                if name not in self._limiters:
                    self._limiters[name] = AdaptiveRateLimiter(name, config)
        
        return self._limiters[name]
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all rate limiters"""
        return {
            name: limiter.get_stats()
            for name, limiter in self._limiters.items()
        }
    
    async def close_all(self):
        """Close all rate limiters"""
        for limiter in self._limiters.values():
            await limiter.close()
        logger.info("All rate limiters closed")


# Global rate limiter manager (singleton)
_global_limiter_manager: Optional[RateLimiterManager] = None
_global_limiter_lock = asyncio.Lock()


async def get_global_limiter_manager() -> RateLimiterManager:
    """
    Get global rate limiter manager (singleton)
    
    Returns:
        RateLimiterManager instance
    """
    global _global_limiter_manager
    
    if _global_limiter_manager is None:
        async with _global_limiter_lock:
            if _global_limiter_manager is None:
                _global_limiter_manager = RateLimiterManager()
                logger.info("Global rate limiter manager initialized")
    
    return _global_limiter_manager

