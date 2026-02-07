"""
TiMem Qwen LLM Adapter (Compatible with OpenAI API)
Implements concrete interface for Qwen API using production-grade resilient architecture
Supports Alibaba Cloud Lingji Model Service (DashScope)
"""

import asyncio
import time
from typing import Dict, List, Optional, Any, AsyncIterator
import json
import aiohttp

from llm.base_llm import (
    BaseLLM, Message, MessageRole, ChatResponse, EmbeddingResponse, ModelConfig,
    ModelType, handle_llm_errors
)
from llm.core import (
    AsyncHTTPPool, get_global_http_pool,
    CircuitBreaker, CircuitBreakerConfig, get_global_breaker_manager,
    SmartRetry, RetryConfig, get_global_retry_manager,
    AdaptiveRateLimiter, RateLimitConfig, Priority, get_global_limiter_manager,
    MetricsCollector, LLMMetrics, get_global_metrics_collector,
    NoFallbackPolicy, get_global_no_fallback_policy,
)
from llm.file_prompt_collector import get_file_prompt_collector
from timem.utils.logging import get_logger

class QwenAdapter(BaseLLM):
    """Qwen API Adapter (Compatible with OpenAI format + Resilient architecture)"""
    
    def __init__(self, config: Optional[ModelConfig] = None):
        # Load configuration from config file
        from timem.utils.config_manager import get_llm_config
        
        llm_config = get_llm_config()
        qwen_config = llm_config.get("providers", {}).get("qwen", {})
        
        # If no config passed, create from config file
        if config is None:
            config = ModelConfig(
                model_name=qwen_config.get("model", "qwen-plus"),
                temperature=qwen_config.get("temperature", 0.7),
                max_tokens=qwen_config.get("max_tokens", 2048),
                top_p=1.0,
                frequency_penalty=0.0,
                presence_penalty=0.0,
                stop=None,
                stream=False
            )
        
        super().__init__(config)
        self.api_key = qwen_config.get("api_key", "")
        self.base_url = qwen_config.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.timeout = qwen_config.get("timeout", 60)
        self.model_type = ModelType.CHAT
        self.logger = get_logger(__name__)
        
        # Initialize multi-API key support
        self.api_keys = []
        self._current_key_index = 0
        self._init_multi_api_keys(qwen_config)
        
        # Resilient components (lazy initialization)
        self._http_pool: Optional[AsyncHTTPPool] = None
        self._circuit_breaker: Optional[CircuitBreaker] = None
        self._rate_limiter: Optional[AdaptiveRateLimiter] = None
        self._retrier: Optional[SmartRetry] = None
        self._metrics_collector: Optional[MetricsCollector] = None
        self._no_fallback_policy: Optional[NoFallbackPolicy] = None
        self._initialized = False
        self._init_lock = asyncio.Lock()
        
        # Validate required configuration
        if not self.api_key or self.api_key == "":
            self.logger.warning("Qwen API key not configured. Please set in config file")
        
        self.logger.info(f"Initializing Qwen adapter: base_url={self.base_url}, model={config.model_name}")
        self.logger.info(f"Multi-API keys: {len(self.api_keys)} keys")
        
        # Supported models list
        self.supported_models = [
            "qwen-turbo",
            "qwen-plus",
            "qwen-max",
            "qwen-max-longcontext",
            "qwen-vl-plus",
            "qwen-vl-max",
            "qwen2.5-72b-instruct",
            "qwen2.5-32b-instruct",
            "qwen2.5-14b-instruct",
            "qwen2.5-7b-instruct",
            "qwen3-32b",
            "qwen3-14b",
            "qwen3-8b",
            "qwen3-235b-a22b",  # Qwen3 235B A22B version
            "qwen3-next-80b-a3b-instruct",  # Qwen3-Next 80B A3B Instruct version
        ]
        
        # Chat model configuration
        self.chat_models = {
            "qwen-turbo": {"max_tokens": 6000, "context_window": 8000},
            "qwen-plus": {"max_tokens": 6000, "context_window": 32000},
            "qwen-max": {"max_tokens": 6000, "context_window": 30000},
            "qwen-max-longcontext": {"max_tokens": 6000, "context_window": 28000},
            "qwen2.5-72b-instruct": {"max_tokens": 8000, "context_window": 32768},
            "qwen2.5-32b-instruct": {"max_tokens": 8000, "context_window": 32768},
            "qwen2.5-14b-instruct": {"max_tokens": 8000, "context_window": 32768},
            "qwen2.5-7b-instruct": {"max_tokens": 8000, "context_window": 32768},
            "qwen3-32b": {"max_tokens": 8000, "context_window": 32768},
            "qwen3-14b": {"max_tokens": 8000, "context_window": 32768},
            "qwen3-8b": {"max_tokens": 8000, "context_window": 32768},
            "qwen3-235b-a22b": {"max_tokens": 8000, "context_window": 32768},
            "qwen3-next-80b-a3b-instruct": {"max_tokens": 8000, "context_window": 32768},
        }

    def _init_multi_api_keys(self, qwen_config: Dict[str, Any]):
        """Initialize multi-API key support"""
        # Add primary API key
        if self.api_key:
            self.api_keys.append(self.api_key)
        
        # Add test API keys
        test_api_key_number = qwen_config.get("test_api_key_number", 0)
        for i in range(1, test_api_key_number + 1):
            test_key = qwen_config.get(f"test_api_key_{i}")
            if test_key and test_key.startswith("sk-"):  # Only add valid API keys
                self.api_keys.append(test_key)
        
        self.logger.info(f"Initialized {len(self.api_keys)} API keys")

    def _get_api_key(self) -> str:
        """Get API key (round-robin)"""
        if len(self.api_keys) == 0:
            return self.api_key
        
        if len(self.api_keys) == 1:
            return self.api_keys[0]
        
        # Round-robin API keys
        key = self.api_keys[self._current_key_index]
        self._current_key_index = (self._current_key_index + 1) % len(self.api_keys)
        return key
    
    async def _ensure_initialized(self):
        """Ensure resilient components are initialized"""
        if self._initialized:
            return
        
        async with self._init_lock:
            if self._initialized:
                return
            
            # Initialize HTTP connection pool
            self._http_pool = await get_global_http_pool()
            
            # Initialize circuit breaker
            breaker_manager = await get_global_breaker_manager()
            self._circuit_breaker = await breaker_manager.get_breaker(
                "qwen",
                CircuitBreakerConfig(
                    failure_threshold=5,
                    recovery_timeout=30.0,
                )
            )
            
            # Initialize rate limiter
            num_keys = len(self.api_keys) if self.api_keys else 1
            base_qps = num_keys * 0.8  # 0.8 QPS per key
            
            limiter_manager = await get_global_limiter_manager()
            self._rate_limiter = await limiter_manager.get_limiter(
                "qwen",
                RateLimitConfig(
                    qps=max(base_qps, 5.0),  # Minimum 5 QPS
                    burst=min(num_keys, 10),  # Burst = key count
                    adaptive=True,
                    min_qps=5.0,
                    max_qps=num_keys * 2.0,  # Maximum = key count * 2
                )
            )
            
            self.logger.info(f"Qwen rate limiter config: keys={num_keys}, qps={base_qps:.1f}, burst={min(num_keys, 10)}")
            
            # Initialize retrier
            retry_manager = get_global_retry_manager()
            self._retrier = retry_manager.get_retrier(
                "qwen",
                RetryConfig(
                    max_attempts=3,
                    base_delay=1.0,
                    max_delay=10.0,
                )
            )
            
            # Initialize metrics collector
            self._metrics_collector = get_global_metrics_collector()
            
            # Initialize NoFallback policy
            self._no_fallback_policy = get_global_no_fallback_policy()
            if self._no_fallback_policy.enabled:
                self.logger.info("✅ NoFallback policy enabled, strict_mode=%s", self._no_fallback_policy.strict_mode)
            
            self._initialized = True
            self.logger.info("Qwen adapter resilient components initialization complete")
        
    def _get_headers(self, api_key: Optional[str] = None) -> Dict[str, str]:
        """Get request headers"""
        use_api_key = api_key or self.api_key
        return {
            "Authorization": f"Bearer {use_api_key}",
            "Content-Type": "application/json",
            "User-Agent": "TiMem/1.0"
        }
    
    def _message_to_dict(self, message: Message) -> Dict[str, str]:
        """Convert message to OpenAI format"""
        return {
            "role": message.role.value,
            "content": message.content
        }
    
    async def chat(self, messages: List[Message], **kwargs) -> ChatResponse:
        """Chat conversation (using resilient architecture)"""
        await self._ensure_initialized()
        
        start_time = time.time()
        api_key = self._get_api_key()
        
        try:
            # 🔧 Configuration priority: call parameters > initialization config
            # Support dynamic model specification via kwargs, critical for dataset-level config.get("model", self.config.model_name)
            
            # 🚨 Strict model validation: intercept non-Qwen model requests (prevent calling OpenAI etc via Qwen API)
            model = kwargs.get("model", self.config.model_name)
            if model not in self.supported_models:
                error_msg = (
                    f"🚨 Model interception: Qwen adapter only supports Qwen series models!\n"
                    f"   Requested model: {model}\n"
                    f"   Supported models: {', '.join(self.supported_models)}\n"
                    f"   ⚠️ Forbidden to call non-Qwen models (e.g., gpt-4o-mini) via Qwen API, this will incur high proxy fees!"
                )
                self.logger.error(error_msg)
                raise ValueError(error_msg)
            
            temperature = kwargs.get("temperature", self.config.temperature)
            max_tokens = kwargs.get("max_tokens", self.config.max_tokens)
            
            # 📊 Log actual model used
            if model != self.config.model_name:
                self.logger.info(f"🔄 Dynamic model switch: {self.config.model_name} → {model}")
            
            # Build request data (OpenAI compatible format)
            request_data = {
                "model": model,
                "messages": [self._message_to_dict(msg) for msg in messages],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False,
                "enable_thinking": False  # Disable thinking mode
            }
            
            # Optional parameters
            if "top_p" in kwargs:
                request_data["top_p"] = kwargs["top_p"]
            elif self.config.top_p != 1.0:
                request_data["top_p"] = self.config.top_p
            
            # Add stop words
            if self.config.stop:
                request_data["stop"] = self.config.stop
            
            # Collect prompt for accurate token calculation
            prompt_collector = get_file_prompt_collector()
            prompt_record_id = None
            if prompt_collector.enabled:
                messages_dict = [self._message_to_dict(msg) for msg in messages]
                prompt_record_id = prompt_collector.record_chat_prompt(
                    messages=messages_dict,
                    model=model,
                    metadata=kwargs.get("metadata", {})
                )
            
            # 1. Apply rate limiting
            await self._rate_limiter.acquire(priority=Priority.NORMAL, timeout=60.0)
            
            # 2. Execute via circuit breaker (with retry)
            result = await self._circuit_breaker.call(
                self._retrier.execute,
                self._execute_http_request,
                request_data,
                api_key
            )
            
            # 3. Parse response
            response_time = time.time() - start_time
            choice = result["choices"][0]
            usage_data = result.get("usage", {})
            
            # Save complete token information
            prompt_tokens = usage_data.get("prompt_tokens", 0)
            completion_tokens = usage_data.get("completion_tokens", 0)
            total_tokens = usage_data.get("total_tokens", prompt_tokens + completion_tokens)
            
            content = choice["message"]["content"]
            
            # 3.5 Apply NoFallback policy to validate response
            if self._no_fallback_policy.enabled and self._no_fallback_policy.strict_mode:
                if not self._no_fallback_policy.validate_response(content):
                    error_msg = f"Detected invalid response (possibly fallback content): {content[:100]}..."
                    self.logger.error(error_msg)
                    raise ValueError(error_msg)
            
            chat_response = ChatResponse(
                content=content,
                finish_reason=choice["finish_reason"],
                model=result["model"],
                usage={
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens
                },
                response_time=response_time,
                metadata={
                    "provider": "qwen",
                    "api_key_used": api_key[:10] + "...",
                    "resilient": True,
                    "no_fallback": self._no_fallback_policy.enabled if self._no_fallback_policy else False,
                    "prompt_record_id": prompt_record_id
                }
            )
            
            # 4. Record success metrics
            self._metrics_collector.record(LLMMetrics(
                provider="qwen",
                model=result["model"],
                timestamp=start_time,
                success=True,
                latency=response_time,
                tokens=total_tokens
            ))
            
            self.logger.debug(f"Qwen chat success, elapsed: {response_time:.2f}s, tokens: {total_tokens}")
            return chat_response
            
        except aiohttp.ClientResponseError as e:
            # Detect 429 rate limit
            if e.status == 429:
                await self._rate_limiter.report_rate_limit()
            
            # Record failure metrics
            self._metrics_collector.record(LLMMetrics(
                provider="qwen",
                model=self.config.model_name,
                timestamp=start_time,
                success=False,
                latency=time.time() - start_time,
                error=str(e)
            ))
            
            self.logger.error(f"Qwen chat failed (HTTP {e.status}): {e}", exc_info=True)
            raise
        
        except Exception as e:
            # Record failure metrics
            self._metrics_collector.record(LLMMetrics(
                provider="qwen",
                model=self.config.model_name,
                timestamp=start_time,
                success=False,
                latency=time.time() - start_time,
                error=str(e)
            ))
            
            self.logger.error(f"Qwen chat failed: {e}", exc_info=True)
            raise
    
    async def _execute_http_request(self, request_data: dict, api_key: str) -> dict:
        """Execute true async HTTP request"""
        url = f"{self.base_url}/chat/completions"
        headers = self._get_headers(api_key)
        
        # Use global connection pool session
        async with self._http_pool.get_session("qwen") as session:
            async with session.post(
                url,
                json=request_data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise aiohttp.ClientResponseError(
                        request_info=response.request_info,
                        history=response.history,
                        status=response.status,
                        message=f"Qwen API error: {error_text}"
                    )
                
                return await response.json()

    async def stream_chat(self, messages: List[Message], **kwargs) -> AsyncIterator[str]:
        """Streaming chat conversation"""
        await self._ensure_initialized()
        api_key = self._get_api_key()
        
        # Get model
        model = kwargs.get("model", self.config.model_name)
        
        # 🚨 Strict model validation: intercept non-Qwen model requests
        if model not in self.supported_models:
            error_msg = (
                f"🚨 Model interception: Qwen adapter only supports Qwen series models!\n"
                f"   Requested model: {model}\n"
                f"   Supported models: {', '.join(self.supported_models)}\n"
                f"   ⚠️ Forbidden to call non-Qwen models (e.g., gpt-4o-mini) via Qwen API, this will incur high proxy fees!"
            )
            self.logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Build request data
        request_data = {
            "model": model,
            "messages": [self._message_to_dict(msg) for msg in messages],
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "stream": True,
            "enable_thinking": False  # Disable thinking mode
        }
        
        url = f"{self.base_url}/chat/completions"
        headers = self._get_headers(api_key)
        
        async with self._http_pool.get_session("qwen") as session:
            async with session.post(
                url,
                json=request_data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise aiohttp.ClientResponseError(
                        request_info=response.request_info,
                        history=response.history,
                        status=response.status,
                        message=f"Qwen API error: {error_text}"
                    )
                
                # Stream processing
                async for line in response.content:
                    line = line.decode('utf-8').strip()
                    if line.startswith('data: '):
                        data = line[6:]
                        if data == '[DONE]':
                            break
                        
                        try:
                            chunk = json.loads(data)
                            if 'choices' in chunk and len(chunk['choices']) > 0:
                                delta = chunk['choices'][0].get('delta', {})
                                content = delta.get('content', '')
                                if content:
                                    yield content
                        except json.JSONDecodeError:
                            continue

    async def chat_stream(self, messages: List[Message], **kwargs) -> AsyncIterator[str]:
        """Streaming chat conversation (implemented in stream_chat method)"""
        async for content in self.stream_chat(messages, **kwargs):
            yield content

    async def complete(self, prompt: str, **kwargs) -> str:
        """Text completion"""
        # Convert prompt to chat format
        messages = [Message(role=MessageRole.USER, content=prompt)]
        response = await self.chat(messages, **kwargs)
        return response.content

    async def embed(self, text: str, **kwargs) -> EmbeddingResponse:
        """Generate text embedding
        Note: Qwen's embedding API endpoint may differ, needs adjustment based on actual API
        """
        raise NotImplementedError("Qwen embedding functionality please use qwen_embedding_adapter")

    async def embed_batch(self, texts: List[str], **kwargs) -> List[EmbeddingResponse]:
        """Batch text embedding"""
        raise NotImplementedError("Qwen embedding functionality please use qwen_embedding_adapter")

    async def summarize(self, text: str, **kwargs) -> str:
        """Text summarization"""
        messages = [
            Message(role=MessageRole.SYSTEM, content="Please provide a concise summary of the following text."),
            Message(role=MessageRole.USER, content=text)
        ]
        response = await self.chat(messages, **kwargs)
        return response.content

    async def validate_model(self, model_name: str) -> bool:
        """Validate if model is available"""
        return model_name in self.supported_models

    async def get_model_info(self, model_name: str) -> Dict[str, Any]:
        """Get model information"""
        if model_name in self.chat_models:
            return self.chat_models[model_name]
        return {}

    async def close(self):
        """Close adapter resources"""
        # Resilient components are managed globally, no need to close separately
        self.logger.info("Qwen adapter closed")
