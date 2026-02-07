"""
TiMem LLM Core Infrastructure Layer

Provides core components for production-grade LLM calls:
- AsyncHTTPPool: True async HTTP connection pool management
- CircuitBreaker: Circuit breaker pattern, fault isolation
- SmartRetry: Smart retry strategy
- ResilientLLMClient: Resilient LLM client
- AdaptiveRateLimiter: Adaptive rate limiter
- FallbackManager: Fallback strategy management
- MetricsCollector: Monitoring metrics collection
"""

# Connection pool
from llm.core.async_http_pool import (
    AsyncHTTPPool,
    get_global_http_pool,
    close_global_http_pool
)

# Circuit breaker
from llm.core.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitBreakerConfig,
    CircuitBreakerError,
    get_global_breaker_manager
)

# Smart retry
from llm.core.smart_retry import (
    SmartRetry,
    RetryConfig,
    RetryableError,
    get_global_retry_manager
)

# Rate limiter
from llm.core.adaptive_rate_limiter import (
    AdaptiveRateLimiter,
    RateLimitConfig,
    Priority,
    RateLimitExceeded,
    get_global_limiter_manager
)

# Resilient client
from llm.core.resilient_client import (
    ResilientLLMClient,
)

# Fallback management
from llm.core.fallback_manager import (
    FallbackManager,
    FallbackChain,
    get_global_fallback_manager
)

# Monitoring metrics
from llm.core.metrics_collector import (
    MetricsCollector,
    LLMMetrics,
    get_global_metrics_collector
)

# Phase 1 Optimization components
# Adaptive timeout
from llm.core.adaptive_timeout import (
    AdaptiveTimeout,
    TimeoutConfig,
    get_global_adaptive_timeout
)

# Enhanced retry
from llm.core.smart_retry_enhanced import (
    EnhancedSmartRetry,
    EnhancedRetryConfig,
    RetryStrategy,
    get_global_enhanced_retry_manager
)

# Disable Fallback
from llm.core.no_fallback_policy import (
    NoFallbackPolicy,
    get_global_no_fallback_policy
)

# Streaming optimization
from llm.core.streaming_optimizer import (
    StreamingOptimizer,
    get_global_streaming_optimizer
)

__all__ = [
    # HTTP connection pool
    "AsyncHTTPPool",
    "get_global_http_pool",
    "close_global_http_pool",
    
    # Circuit breaker
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitState",
    "CircuitBreakerError",
    "get_global_breaker_manager",
    
    # Smart retry
    "SmartRetry",
    "RetryConfig",
    "RetryableError",
    "get_global_retry_manager",
    
    # Rate limiter
    "AdaptiveRateLimiter",
    "RateLimitConfig",
    "Priority",
    "RateLimitExceeded",
    "get_global_limiter_manager",
    
    # Resilient client
    "ResilientLLMClient",
    
    # Fallback management
    "FallbackManager",
    "FallbackChain",
    "get_global_fallback_manager",
    
    # Monitoring metrics
    "MetricsCollector",
    "LLMMetrics",
    "get_global_metrics_collector",
    
    # Phase 1 Optimization components
    # Adaptive timeout
    "AdaptiveTimeout",
    "TimeoutConfig",
    "get_global_adaptive_timeout",
    
    # Enhanced retry
    "EnhancedSmartRetry",
    "EnhancedRetryConfig",
    "RetryStrategy",
    "get_global_enhanced_retry_manager",
    
    # Disable Fallback
    "NoFallbackPolicy",
    "get_global_no_fallback_policy",
    
    # Streaming optimization
    "StreamingOptimizer",
    "get_global_streaming_optimizer",
]

__version__ = "1.0.0"

