"""
Circuit breaker pattern implementation

Provides fault isolation and fast failure mechanism to prevent system cascade:
1. Three-state machine: CLOSED (normal) → OPEN (tripped) → HALF_OPEN (probing)
2. Failure rate-based tripping decision
3. Automatic recovery probing
4. Support independent circuit breaker per provider
"""

import asyncio
import time
from enum import Enum
from typing import Optional, Callable, Any, Dict
from dataclasses import dataclass, field
from collections import deque

from timem.utils.logging import get_logger

logger = get_logger(__name__)


class CircuitState(str, Enum):
    """Circuit breaker state"""
    CLOSED = "closed"  # Normal state, requests pass through normally
    OPEN = "open"  # Tripped state, reject all requests
    HALF_OPEN = "half_open"  # Half-open state, allow partial requests to probe recovery


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration"""
    # Failure threshold configuration
    failure_threshold: int = 5  # Failure count threshold
    failure_rate_threshold: float = 0.5  # Failure rate threshold (0-1)
    min_calls_threshold: int = 10  # Minimum call count (calculate failure rate only after reaching this)
    
    # Time window configuration
    time_window: float = 10.0  # Statistics time window (seconds)
    recovery_timeout: float = 30.0  # Recovery timeout (seconds, OPEN→HALF_OPEN)
    
    # Half-open state configuration
    half_open_max_calls: int = 1  # Maximum calls allowed in half-open state
    half_open_success_threshold: int = 1  # Success count threshold in half-open state (recover when reached)
    
    # Exception whitelist (these exceptions don't count as failures)
    excluded_exceptions: tuple = ()


@dataclass
class CallRecord:
    """Call record"""
    timestamp: float
    success: bool
    exception: Optional[Exception] = None


@dataclass
class CircuitBreakerStats:
    """Circuit breaker statistics"""
    state: CircuitState = CircuitState.CLOSED
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0  # Calls rejected by circuit breaker
    last_state_change: float = field(default_factory=time.time)
    last_failure_time: float = 0.0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    
    @property
    def failure_rate(self) -> float:
        """Failure rate"""
        if self.total_calls == 0:
            return 0.0
        return self.failed_calls / self.total_calls


class CircuitBreakerError(Exception):
    """Circuit breaker error (raised when tripped)"""
    pass


class CircuitBreaker:
    """
    Circuit breaker implementation
    
    Automatically detects faults and trips to prevent system cascade.
    """
    
    def __init__(
        self, 
        name: str, 
        config: Optional[CircuitBreakerConfig] = None
    ):
        """
        Initialize circuit breaker
        
        Args:
            name: Circuit breaker name (usually provider name)
            config: Circuit breaker configuration
        """
        self.name = name
        self.config = config or CircuitBreakerConfig()
        
        # Current state
        self._state = CircuitState.CLOSED
        
        # Call records (using sliding time window)
        self._call_records: deque[CallRecord] = deque()
        
        # Statistics
        self._stats = CircuitBreakerStats()
        
        # State change time
        self._state_changed_at = time.time()
        
        # Half-open state count
        self._half_open_calls = 0
        self._half_open_successes = 0
        
        # Lock (protect state)
        self._lock = asyncio.Lock()
        
        logger.info(
            f"Circuit breaker [{name}] initialized: "
            f"failure_threshold={self.config.failure_threshold}, "
            f"recovery_timeout={self.config.recovery_timeout}s"
        )
    
    @property
    def state(self) -> CircuitState:
        """Get current state"""
        return self._state
    
    @property
    def stats(self) -> CircuitBreakerStats:
        """Get statistics"""
        self._stats.state = self._state
        return self._stats
    
    def _clean_old_records(self):
        """Clean expired call records"""
        now = time.time()
        cutoff_time = now - self.config.time_window
        
        while self._call_records and self._call_records[0].timestamp < cutoff_time:
            self._call_records.popleft()
    
    def _calculate_failure_rate(self) -> float:
        """Calculate current failure rate"""
        if not self._call_records:
            return 0.0
        
        failures = sum(1 for record in self._call_records if not record.success)
        return failures / len(self._call_records)
    
    def _should_trip(self) -> bool:
        """Determine if should trip"""
        # Clean old records
        self._clean_old_records()
        
        # Check if minimum call count reached
        if len(self._call_records) < self.config.min_calls_threshold:
            return False
        
        # Check failure rate
        failure_rate = self._calculate_failure_rate()
        if failure_rate >= self.config.failure_rate_threshold:
            return True
        
        # Check consecutive failures
        if self._stats.consecutive_failures >= self.config.failure_threshold:
            return True
        
        return False
    
    def _transition_to(self, new_state: CircuitState):
        """State transition"""
        old_state = self._state
        if old_state == new_state:
            return
        
        self._state = new_state
        self._state_changed_at = time.time()
        self._stats.last_state_change = self._state_changed_at
        
        # Reset half-open state count
        if new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
            self._half_open_successes = 0
        
        logger.warning(
            f"Circuit breaker [{self.name}] state changed: {old_state.value} → {new_state.value}, "
            f"failure_rate={self._calculate_failure_rate():.2%}, "
            f"consecutive_failures={self._stats.consecutive_failures}"
        )
    
    async def _check_state_transition(self):
        """Check and perform state transition"""
        async with self._lock:
            now = time.time()
            
            if self._state == CircuitState.CLOSED:
                # CLOSED state: check if should trip
                if self._should_trip():
                    self._transition_to(CircuitState.OPEN)
            
            elif self._state == CircuitState.OPEN:
                # OPEN state: check if recovery timeout reached
                if now - self._state_changed_at >= self.config.recovery_timeout:
                    self._transition_to(CircuitState.HALF_OPEN)
            
            elif self._state == CircuitState.HALF_OPEN:
                # HALF_OPEN state: check if should recover or re-trip
                if self._half_open_successes >= self.config.half_open_success_threshold:
                    self._transition_to(CircuitState.CLOSED)
                    # Clean records, restart
                    self._call_records.clear()
                    self._stats.consecutive_failures = 0
                elif self._half_open_calls >= self.config.half_open_max_calls:
                    # Half-open reached max calls but no success, re-trip
                    if self._half_open_successes == 0:
                        self._transition_to(CircuitState.OPEN)
    
    async def call(
        self, 
        func: Callable, 
        *args, 
        **kwargs
    ) -> Any:
        """
        Call function through circuit breaker
        
        Args:
            func: Async function to call
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Function return value
            
        Raises:
            CircuitBreakerError: Raised when circuit breaker is tripped
            Exception: Function call exception
        """
        # Check state transition
        await self._check_state_transition()
        
        # Check if can call
        if self._state == CircuitState.OPEN:
            self._stats.rejected_calls += 1
            raise CircuitBreakerError(
                f"Circuit breaker [{self.name}] is tripped, rejecting call"
            )
        
        if self._state == CircuitState.HALF_OPEN:
            async with self._lock:
                if self._half_open_calls >= self.config.half_open_max_calls:
                    self._stats.rejected_calls += 1
                    raise CircuitBreakerError(
                        f"Circuit breaker [{self.name}] half-open max calls reached, rejecting call"
                    )
                self._half_open_calls += 1
        
        # Execute call
        start_time = time.time()
        success = False
        exception = None
        
        try:
            result = await func(*args, **kwargs)
            success = True
            return result
        
        except Exception as e:
            exception = e
            
            # Check if whitelist exception
            if self.config.excluded_exceptions and isinstance(e, self.config.excluded_exceptions):
                # Whitelist exceptions don't count as failures
                logger.debug(f"Circuit breaker [{self.name}] ignoring whitelist exception: {type(e).__name__}")
                raise
            
            # Log failure
            logger.warning(f"Circuit breaker [{self.name}] call failed: {e}")
            raise
        
        finally:
            # Record call result
            async with self._lock:
                # Add call record
                record = CallRecord(
                    timestamp=start_time,
                    success=success,
                    exception=exception
                )
                self._call_records.append(record)
                
                # Update statistics
                self._stats.total_calls += 1
                if success:
                    self._stats.successful_calls += 1
                    self._stats.consecutive_failures = 0
                    self._stats.consecutive_successes += 1
                    
                    # Half-open success count
                    if self._state == CircuitState.HALF_OPEN:
                        self._half_open_successes += 1
                else:
                    self._stats.failed_calls += 1
                    self._stats.consecutive_successes = 0
                    self._stats.consecutive_failures += 1
                    self._stats.last_failure_time = start_time
            
            # Check state transition again
            await self._check_state_transition()
    
    def reset(self):
        """Reset circuit breaker (manual recovery)"""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._call_records.clear()
            self._stats.consecutive_failures = 0
            self._stats.consecutive_successes = 0
            self._half_open_calls = 0
            self._half_open_successes = 0
            logger.info(f"Circuit breaker [{self.name}] manually reset")
    
    def get_stats_dict(self) -> Dict[str, Any]:
        """Get statistics dictionary"""
        return {
            "name": self.name,
            "state": self._state.value,
            "total_calls": self._stats.total_calls,
            "successful_calls": self._stats.successful_calls,
            "failed_calls": self._stats.failed_calls,
            "rejected_calls": self._stats.rejected_calls,
            "failure_rate": self._stats.failure_rate,
            "consecutive_failures": self._stats.consecutive_failures,
            "consecutive_successes": self._stats.consecutive_successes,
            "last_state_change": self._stats.last_state_change,
            "last_failure_time": self._stats.last_failure_time,
            "time_since_last_failure": time.time() - self._stats.last_failure_time if self._stats.last_failure_time > 0 else 0,
        }


class CircuitBreakerManager:
    """
    Circuit breaker manager
    
    Manages independent circuit breaker instances for different providers.
    """
    
    def __init__(self):
        """Initialize circuit breaker manager"""
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()
        logger.info("Circuit breaker manager initialized")
    
    async def get_breaker(
        self, 
        name: str, 
        config: Optional[CircuitBreakerConfig] = None
    ) -> CircuitBreaker:
        """
        Get or create circuit breaker
        
        Args:
            name: Circuit breaker name
            config: Circuit breaker configuration (used only on creation)
            
        Returns:
            CircuitBreaker instance
        """
        if name not in self._breakers:
            async with self._lock:
                if name not in self._breakers:
                    self._breakers[name] = CircuitBreaker(name, config)
        
        return self._breakers[name]
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all circuit breakers"""
        return {
            name: breaker.get_stats_dict()
            for name, breaker in self._breakers.items()
        }
    
    def reset_all(self):
        """Reset all circuit breakers"""
        for breaker in self._breakers.values():
            breaker.reset()
        logger.info("All circuit breakers reset")


# Global circuit breaker manager (singleton)
_global_breaker_manager: Optional[CircuitBreakerManager] = None
_global_breaker_lock = asyncio.Lock()


async def get_global_breaker_manager() -> CircuitBreakerManager:
    """
    Get global circuit breaker manager (singleton)
    
    Returns:
        CircuitBreakerManager instance
    """
    global _global_breaker_manager
    
    if _global_breaker_manager is None:
        async with _global_breaker_lock:
            if _global_breaker_manager is None:
                _global_breaker_manager = CircuitBreakerManager()
                logger.info("Global circuit breaker manager initialized")
    
    return _global_breaker_manager

