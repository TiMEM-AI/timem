"""
Resilient LLM Client

Integrates circuit breaker, rate limiting, retry, fallback and other resilience mechanisms to provide unified LLM calling interface.
"""

import asyncio
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from llm.core.async_http_pool import AsyncHTTPPool, get_global_http_pool
from llm.core.circuit_breaker import (
    CircuitBreaker, CircuitBreakerConfig, CircuitBreakerError,
    get_global_breaker_manager
)
from llm.core.smart_retry import SmartRetry, RetryConfig, get_global_retry_manager
from llm.core.adaptive_rate_limiter import (
    AdaptiveRateLimiter, RateLimitConfig, RateLimitExceeded, Priority,
    get_global_limiter_manager
)
from llm.core.fallback_manager import FallbackManager, get_global_fallback_manager
from llm.base_llm import ChatResponse, Message

from timem.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ResilienceConfig:
    """Resilience configuration"""
    # Circuit breaker configuration
    circuit_breaker_enabled: bool = True
    circuit_breaker_config: Optional[CircuitBreakerConfig] = None
    
    # Rate limiter configuration
    rate_limiter_enabled: bool = True
    rate_limiter_config: Optional[RateLimitConfig] = None
    
    # Retry configuration
    retry_enabled: bool = True
    retry_config: Optional[RetryConfig] = None
    
    # Fallback configuration
    fallback_enabled: bool = True
    
    # Total timeout
    total_timeout: float = 90.0


@dataclass
class RequestContext:
    """Request context"""
    request_id: str
    provider: str
    model: str
    priority: Priority = Priority.NORMAL
    start_time: float = 0.0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.start_time == 0.0:
            self.start_time = time.time()
        if self.metadata is None:
            self.metadata = {}


class ResilientLLMClient:
    """
    Resilient LLM Client
    
    Integrates all resilience mechanisms to provide reliable LLM calling capability.
    """
    
    def __init__(
        self,
        provider: str,
        config: Optional[ResilienceConfig] = None
    ):
        """
        Initialize resilient client
        
        Args:
            provider: Provider name
            config: Resilience configuration
        """
        self.provider = provider
        self.config = config or ResilienceConfig()
        
        # Async initialization flag
        self._initialized = False
        self._init_lock = asyncio.Lock()
        
        # Components (lazy initialization)
        self._http_pool: Optional[AsyncHTTPPool] = None
        self._circuit_breaker: Optional[CircuitBreaker] = None
        self._rate_limiter: Optional[AdaptiveRateLimiter] = None
        self._retrier: Optional[SmartRetry] = None
        self._fallback_manager: Optional[FallbackManager] = None
        
        # Statistics
        self._stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "circuit_breaker_trips": 0,
            "rate_limit_rejects": 0,
            "retries": 0,
            "fallbacks": 0,
            "total_latency": 0.0,
        }
        
        logger.info(f"Resilient LLM client created: provider={provider}")
    
    async def _ensure_initialized(self):
        """Ensure components are initialized"""
        if self._initialized:
            return
        
        async with self._init_lock:
            if self._initialized:
                return
            
            # Initialize HTTP connection pool
            self._http_pool = await get_global_http_pool()
            
            # Initialize circuit breaker
            if self.config.circuit_breaker_enabled:
                breaker_manager = await get_global_breaker_manager()
                self._circuit_breaker = await breaker_manager.get_breaker(
                    self.provider,
                    self.config.circuit_breaker_config
                )
            
            # Initialize rate limiter
            if self.config.rate_limiter_enabled:
                limiter_manager = await get_global_limiter_manager()
                self._rate_limiter = await limiter_manager.get_limiter(
                    self.provider,
                    self.config.rate_limiter_config
                )
            
            # Initialize retrier
            if self.config.retry_enabled:
                retry_manager = get_global_retry_manager()
                self._retrier = retry_manager.get_retrier(
                    self.provider,
                    self.config.retry_config
                )
            
            # Initialize fallback manager
            if self.config.fallback_enabled:
                self._fallback_manager = await get_global_fallback_manager()
            
            self._initialized = True
            logger.info(f"Resilient LLM client [{self.provider}] initialized")
    
    async def chat(
        self,
        messages: List[Message],
        model: str,
        context: Optional[RequestContext] = None,
        **kwargs
    ) -> ChatResponse:
        """
        Resilient chat interface
        
        Args:
            messages: Message list
            model: Model name
            context: Request context
            **kwargs: Other parameters
            
        Returns:
            ChatResponse
            
        Raises:
            Exception: Raised after all resilience mechanisms fail
        """
        await self._ensure_initialized()
        
        # Create context
        if context is None:
            import uuid
            context = RequestContext(
                request_id=str(uuid.uuid4())[:8],
                provider=self.provider,
                model=model
            )
        
        self._stats["total_requests"] += 1
        start_time = time.time()
        
        try:
            # 1. Check circuit breaker
            if self._circuit_breaker:
                # Execute through circuit breaker
                result = await self._circuit_breaker.call(
                    self._execute_with_resilience,
                    messages,
                    model,
                    context,
                    **kwargs
                )
            else:
                result = await self._execute_with_resilience(
                    messages,
                    model,
                    context,
                    **kwargs
                )
            
            # Success
            latency = time.time() - start_time
            self._stats["successful_requests"] += 1
            self._stats["total_latency"] += latency
            
            logger.info(
                f"[{self.provider}] Request succeeded "
                f"(id={context.request_id}, model={model}, latency={latency:.2f}s)"
            )
            
            return result
        
        except CircuitBreakerError as e:
            # Circuit breaker tripped
            self._stats["circuit_breaker_trips"] += 1
            logger.error(f"[{self.provider}] Circuit breaker tripped: {e}")
            raise
        
        except RateLimitExceeded as e:
            # Rate limit rejected
            self._stats["rate_limit_rejects"] += 1
            logger.error(f"[{self.provider}] Rate limit rejected: {e}")
            raise
        
        except Exception as e:
            # Other errors
            self._stats["failed_requests"] += 1
            logger.error(f"[{self.provider}] Request failed: {e}", exc_info=True)
            raise
    
    async def _execute_with_resilience(
        self,
        messages: List[Message],
        model: str,
        context: RequestContext,
        **kwargs
    ) -> ChatResponse:
        """
        Execute request with resilience mechanisms
        
        Args:
            messages: Message list
            model: Model name
            context: Request context
            **kwargs: Other parameters
            
        Returns:
            ChatResponse
        """
        # 2. Apply rate limiting
        if self._rate_limiter:
            try:
                await self._rate_limiter.acquire(
                    priority=context.priority,
                    timeout=60.0
                )
            except RateLimitExceeded:
                logger.warning(f"[{self.provider}] Rate limit wait timeout")
                raise
        
        # 3. Execute request (with retry)
        if self._retrier:
            response = await self._retrier.execute(
                self._execute_http_request,
                messages,
                model,
                context,
                **kwargs
            )
        else:
            response = await self._execute_http_request(
                messages,
                model,
                context,
                **kwargs
            )
        
        return response
    
    async def _execute_http_request(
        self,
        messages: List[Message],
        model: str,
        context: RequestContext,
        **kwargs
    ) -> ChatResponse:
        """
        Execute actual HTTP request
        
        Args:
            messages: Message list
            model: Model name
            context: Request context
            **kwargs: Other parameters
            
        Returns:
            ChatResponse
        """
        # Need to call corresponding API based on provider
        # This logic will be implemented during adapter refactoring
        # For now, raise NotImplementedError
        raise NotImplementedError(
            "HTTP request execution needs to be implemented in specific Adapter"
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics"""
        stats = self._stats.copy()
        
        # Calculate derived metrics
        if stats["total_requests"] > 0:
            stats["success_rate"] = stats["successful_requests"] / stats["total_requests"]
            stats["failure_rate"] = stats["failed_requests"] / stats["total_requests"]
            stats["avg_latency"] = stats["total_latency"] / stats["successful_requests"] if stats["successful_requests"] > 0 else 0
        else:
            stats["success_rate"] = 0.0
            stats["failure_rate"] = 0.0
            stats["avg_latency"] = 0.0
        
        # Add component statistics
        if self._circuit_breaker:
            stats["circuit_breaker"] = self._circuit_breaker.get_stats_dict()
        
        if self._rate_limiter:
            stats["rate_limiter"] = self._rate_limiter.get_stats()
        
        if self._retrier:
            stats["retrier"] = self._retrier.get_stats()
        
        return stats
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Health check
        
        Returns:
            Health status information
        """
        await self._ensure_initialized()
        
        health = {
            "provider": self.provider,
            "status": "healthy",
            "components": {}
        }
        
        # Check circuit breaker state
        if self._circuit_breaker:
            breaker_stats = self._circuit_breaker.get_stats_dict()
            health["components"]["circuit_breaker"] = {
                "state": breaker_stats["state"],
                "healthy": breaker_stats["state"] != "open"
            }
            if breaker_stats["state"] == "open":
                health["status"] = "unhealthy"
        
        # Check rate limiter state
        if self._rate_limiter:
            limiter_stats = self._rate_limiter.get_stats()
            health["components"]["rate_limiter"] = {
                "current_qps": limiter_stats["current_qps"],
                "healthy": limiter_stats["allow_rate"] > 0.8
            }
        
        # Check HTTP connection pool
        if self._http_pool:
            pool_stats = self._http_pool.get_stats(self.provider)
            health["components"]["http_pool"] = {
                "active_connections": pool_stats.get("active_connections", 0),
                "success_rate": pool_stats.get("success_rate", 0),
                "healthy": pool_stats.get("success_rate", 0) > 0.9
            }
        
        # Overall status
        component_health = [
            comp.get("healthy", True)
            for comp in health["components"].values()
        ]
        if component_health and not all(component_health):
            health["status"] = "degraded"
        
        return health


class ResilientClientFactory:
    """Resilient client factory"""
    
    _clients: Dict[str, ResilientLLMClient] = {}
    _lock = asyncio.Lock()
    
    @classmethod
    async def get_client(
        cls,
        provider: str,
        config: Optional[ResilienceConfig] = None
    ) -> ResilientLLMClient:
        """
        Get or create resilient client
        
        Args:
            provider: Provider name
            config: Resilience configuration
            
        Returns:
            ResilientLLMClient instance
        """
        if provider not in cls._clients:
            async with cls._lock:
                if provider not in cls._clients:
                    cls._clients[provider] = ResilientLLMClient(provider, config)
                    await cls._clients[provider]._ensure_initialized()
        
        return cls._clients[provider]
    
    @classmethod
    def get_all_stats(cls) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all clients"""
        return {
            provider: client.get_stats()
            for provider, client in cls._clients.items()
        }
    
    @classmethod
    async def health_check_all(cls) -> Dict[str, Dict[str, Any]]:
        """Health check for all clients"""
        results = {}
        for provider, client in cls._clients.items():
            results[provider] = await client.health_check()
        return results

