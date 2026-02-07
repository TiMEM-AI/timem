"""
TiMem OpenAI LLM Adapter (Refactored - True Async I/O)
Implements concrete interface for OpenAI API using production-grade resilient architecture
"""

import asyncio
import time
from typing import Dict, List, Optional, Any, AsyncIterator
import json
import aiohttp

# Import httpx for legacy methods (backward compatibility)
try:
    import httpx
except ImportError:
    httpx = None  # type: ignore

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

class OpenAIAdapter(BaseLLM):
    """OpenAI API Adapter (Refactored - True Async I/O + Resilient Architecture)"""
    
    def __init__(self, config: Optional[ModelConfig] = None):
        # Load configuration from config file
        from timem.utils.config_manager import get_llm_config
        
        llm_config = get_llm_config()
        openai_config = llm_config.get("providers", {}).get("openai", {})
        
        # If no config passed, create from config file
        if config is None:
            config = ModelConfig(
                model_name=openai_config.get("model", "gpt-4o-mini"),
                temperature=openai_config.get("temperature", 0.7),
                max_tokens=openai_config.get("max_tokens", 2048),
                top_p=1.0,
                frequency_penalty=0.0,
                presence_penalty=0.0,
                stop=None,
                stream=False
            )
        
        super().__init__(config)
        self.api_key = openai_config.get("api_key", "")
        self.base_url = openai_config.get("base_url", "https://api.openai.com/v1")
        self.timeout = openai_config.get("timeout", 60)
        self.model_type = ModelType.CHAT
        self.logger = get_logger(__name__)
        
        # Initialize multi-API key support
        self.api_keys = []
        self._current_key_index = 0
        self._init_multi_api_keys(openai_config)
        
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
            self.logger.warning("OpenAI API key not configured. Please set OPENAI_API_KEY environment variable or configure in config file")
        
        self.logger.info(f"Initializing OpenAI adapter (refactored): base_url={self.base_url}, model={config.model_name}")
        self.logger.info(f"Multi-API keys: {len(self.api_keys)} keys")
        
        # Supported models list
        self.supported_models = [
            "gpt-4",
            "gpt-4-turbo",
            "gpt-4o-mini",
            "gpt-4o",
            "gpt-3.5-turbo",
            "gpt-3.5-turbo-16k",
            "text-embedding-ada-002",
            "text-embedding-3-small",
            "text-embedding-3-large"
        ]
        
        # Embedding model configuration
        self.embedding_models = {
            "text-embedding-ada-002": {"dimensions": 1536, "max_tokens": 8192},
            "text-embedding-3-small": {"dimensions": 1536, "max_tokens": 8192},
            "text-embedding-3-large": {"dimensions": 3072, "max_tokens": 8192}
        }
        
        # Chat model configuration
        self.chat_models = {
            "gpt-4": {"max_tokens": 8192, "context_window": 128000},
            "gpt-4-turbo": {"max_tokens": 4096, "context_window": 128000},
            "gpt-4o": {"max_tokens": 4096, "context_window": 128000},
            "gpt-4o-mini": {"max_tokens": 16384, "context_window": 128000},
            "gpt-3.5-turbo": {"max_tokens": 4096, "context_window": 16385},
            "gpt-3.5-turbo-16k": {"max_tokens": 16384, "context_window": 16385}
        }

    def _init_multi_api_keys(self, openai_config: Dict[str, Any]):
        """Initialize multi-API key support"""
        # Add primary API key
        if self.api_key:
            self.api_keys.append(self.api_key)
        
        # Add test API keys
        test_api_key_number = openai_config.get("test_api_key_number", 0)
        for i in range(1, test_api_key_number + 1):
            test_key = openai_config.get(f"test_api_key_{i}")
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
                "openai",
                CircuitBreakerConfig(
                    failure_threshold=5,
                    recovery_timeout=30.0,
                )
            )
            
            # Initialize rate limiter
            # OpenAI: 1 key supports 1 concurrent, dynamically set QPS based on key count
            num_keys = len(self.api_keys) if self.api_keys else 1
            # Conservative estimate: 1 QPS per key, with margin for network latency
            base_qps = num_keys * 0.8  # 0.8 QPS per key
            
            limiter_manager = await get_global_limiter_manager()
            self._rate_limiter = await limiter_manager.get_limiter(
                "openai",
                RateLimitConfig(
                    qps=max(base_qps, 5.0),  # Minimum 5 QPS
                    burst=min(num_keys, 10),  # Burst = key count
                    adaptive=True,
                    min_qps=5.0,
                    max_qps=num_keys * 2.0,  # Maximum = key count * 2
                )
            )
            
            self.logger.info(f"OpenAI rate limiter config: keys={num_keys}, qps={base_qps:.1f}, burst={min(num_keys, 10)}")
            
            # Initialize retrier
            retry_manager = get_global_retry_manager()
            self._retrier = retry_manager.get_retrier(
                "openai",
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
            self.logger.info("OpenAI adapter resilient components initialization complete")
        
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
        """Chat conversation (refactored - true async + resilient architecture)"""
        await self._ensure_initialized()
        
        start_time = time.time()
        api_key = self._get_api_key()
        
        try:
            # 🔧 Configuration priority: call parameters > initialization config
            # Support dynamic model specification via kwargs, critical for dataset-level config
            model = kwargs.get("model", self.config.model_name)
            
            # 🚨 Strict model validation: intercept non-OpenAI model requests (prevent calling Qwen etc via OpenAI API)
            if model not in self.supported_models:
                error_msg = (
                    f"🚨 Model interception: OpenAI adapter only supports OpenAI series models!\n"
                    f"   Requested model: {model}\n"
                    f"   Supported models: {', '.join(self.supported_models)}\n"
                    f"   ⚠️ Forbidden to call non-OpenAI models (e.g., qwen3-32b) via OpenAI API!"
                )
                self.logger.error(error_msg)
                raise ValueError(error_msg)
            
            temperature = kwargs.get("temperature", self.config.temperature)
            max_tokens = kwargs.get("max_tokens", self.config.max_tokens)
            
            # 📊 Log actual model used (for debugging and audit)
            if model != self.config.model_name:
                self.logger.info(f"🔄 Dynamic model switch: {self.config.model_name} → {model}")
            
            # Build request data
            request_data = {
                "model": model,  # 🔧 Use dynamic model
                "messages": [self._message_to_dict(msg) for msg in messages],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "top_p": kwargs.get("top_p", self.config.top_p),
                "frequency_penalty": kwargs.get("frequency_penalty", self.config.frequency_penalty),
                "presence_penalty": kwargs.get("presence_penalty", self.config.presence_penalty),
                "stream": False
            }
            
            # Add stop words
            if self.config.stop:
                request_data["stop"] = self.config.stop
            
            # 🆕 Collect prompt for accurate token calculation
            prompt_collector = get_file_prompt_collector()
            prompt_record_id = None
            if prompt_collector.enabled:
                messages_dict = [self._message_to_dict(msg) for msg in messages]
                prompt_record_id = prompt_collector.record_chat_prompt(
                    messages=messages_dict,
                    model=model,  # 🔧 Use actual model name
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
            
            # 🔧 Save complete token information
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
                    "provider": "openai",
                    "api_key_used": api_key[:10] + "...",
                    "resilient": True,
                    "no_fallback": self._no_fallback_policy.enabled if self._no_fallback_policy else False,
                    "prompt_record_id": prompt_record_id  # 🆕 Associate prompt record
                }
            )
            
            # 4. Record success metrics
            self._metrics_collector.record(LLMMetrics(
                provider="openai",
                model=result["model"],
                timestamp=start_time,
                success=True,
                latency=response_time,
                tokens=total_tokens
            ))
            
            self.logger.debug(f"OpenAI chat success, elapsed: {response_time:.2f}s, tokens: {total_tokens}")
            return chat_response
            
        except aiohttp.ClientResponseError as e:
            # Detect 429 rate limit
            if e.status == 429:
                await self._rate_limiter.report_rate_limit()
            
            # Record failure metrics
            self._metrics_collector.record(LLMMetrics(
                provider="openai",
                model=self.config.model_name,
                timestamp=start_time,
                success=False,
                latency=time.time() - start_time,
                error=str(e)
            ))
            
            self.logger.error(f"OpenAI chat failed (HTTP {e.status}): {e}", exc_info=True)
            raise
        
        except Exception as e:
            # Record failure metrics
            self._metrics_collector.record(LLMMetrics(
                provider="openai",
                model=self.config.model_name,
                timestamp=start_time,
                success=False,
                latency=time.time() - start_time,
                error=str(e)
            ))
            
            self.logger.error(f"OpenAI chat failed: {e}", exc_info=True)
            raise
    
    async def _execute_http_request(self, request_data: dict, api_key: str) -> dict:
        """Execute true async HTTP request"""
        url = f"{self.base_url}/chat/completions"
        headers = self._get_headers(api_key)
        
        # Use global connection pool session
        async with self._http_pool.get_session("openai") as session:
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
                        message=f"OpenAI API error: {error_text}"
                    )
                
                return await response.json()

    @handle_llm_errors
    async def _chat_internal_legacy(self, messages: List[Message], **kwargs) -> ChatResponse:
        """Internal chat implementation (legacy, kept for compatibility)"""
        start_time = time.time()
        
        # Build request data
        request_data = {
            "model": self.config.model_name,
            "messages": [self._message_to_dict(msg) for msg in messages],
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "top_p": kwargs.get("top_p", self.config.top_p),
            "frequency_penalty": kwargs.get("frequency_penalty", self.config.frequency_penalty),
            "presence_penalty": kwargs.get("presence_penalty", self.config.presence_penalty),
            "stream": False
        }
        
        # Add stop words
        if self.config.stop:
            request_data["stop"] = self.config.stop
        
        # Send request
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._get_headers(),
                json=request_data
            )
            
            if response.status_code != 200:
                error_data = response.json() if response.text else {"error": "Unknown error"}
                raise Exception(f"OpenAI API error: {response.status_code}, {error_data}")
            
            result = response.json()
        
        # Parse response
        response_time = time.time() - start_time
        choice = result["choices"][0]
        
        # Unified usage format, consistent with ZhipuAI
        usage_data = result.get("usage", {})
        total_tokens = usage_data.get("total_tokens", 0)
        
        chat_response = ChatResponse(
            content=choice["message"]["content"],
            finish_reason=choice["finish_reason"],
            model=result["model"],
            usage={"total_tokens": total_tokens},  # Unified format: only includes total_tokens
            response_time=response_time,
            metadata={
                "provider": "openai",
                "concurrent": True
            }
        )
        
        self.logger.debug(f"OpenAI chat complete, elapsed: {response_time:.2f}s, tokens: {chat_response.usage}")
        return chat_response
    
    @handle_llm_errors
    async def chat_stream(self, messages: List[Message], **kwargs) -> AsyncIterator[str]:
        """Streaming chat conversation (refactored - true async)"""
        await self._ensure_initialized()
        
        api_key = self._get_api_key()
        
        # Get model
        model = kwargs.get("model", self.config.model_name)
        
        # 🚨 Strict model validation: intercept non-OpenAI model requests
        if model not in self.supported_models:
            error_msg = (
                f"🚨 Model interception: OpenAI adapter only supports OpenAI series models!\n"
                f"   Requested model: {model}\n"
                f"   Supported models: {', '.join(self.supported_models)}\n"
                f"   ⚠️ Forbidden to call non-OpenAI models (e.g., qwen3-32b) via OpenAI API!"
            )
            self.logger.error(error_msg)
            raise ValueError(error_msg)
        
        request_data = {
            "model": model,
            "messages": [self._message_to_dict(msg) for msg in messages],
            "temperature": kwargs.get("temperature", self.config.temperature),
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "top_p": kwargs.get("top_p", self.config.top_p),
            "frequency_penalty": kwargs.get("frequency_penalty", self.config.frequency_penalty),
            "presence_penalty": kwargs.get("presence_penalty", self.config.presence_penalty),
            "stream": True
        }
        
        if self.config.stop:
            request_data["stop"] = self.config.stop
        
        url = f"{self.base_url}/chat/completions"
        headers = self._get_headers(api_key)
        
        # Apply rate limiting
        await self._rate_limiter.acquire(priority=Priority.NORMAL, timeout=60.0)
        
        # Content collection for NoFallback validation
        collected_content = []
        
        async with self._http_pool.get_session("openai") as session:
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
                        message=f"OpenAI API error: {error_text}"
                    )
                
                async for line_bytes in response.content:
                    line = line_bytes.decode('utf-8').strip()
                    
                    if line.startswith("data: "):
                        data_str = line[6:]  # Remove "data: " prefix
                        
                        if data_str.strip() == "[DONE]":
                            break
                        
                        try:
                            data = json.loads(data_str)
                            if "choices" in data and len(data["choices"]) > 0:
                                delta = data["choices"][0].get("delta", {})
                                if "content" in delta:
                                    content_chunk = delta["content"]
                                    collected_content.append(content_chunk)
                                    yield content_chunk
                        except json.JSONDecodeError:
                            continue
        
        # After streaming ends, apply NoFallback policy to validate complete content
        if self._no_fallback_policy and self._no_fallback_policy.enabled and self._no_fallback_policy.strict_mode:
            full_content = "".join(collected_content)
            if full_content and not self._no_fallback_policy.validate_response(full_content):
                error_msg = f"Streaming response validation failed (detected fallback content): {full_content[:100]}..."
                self.logger.error(error_msg)
                raise ValueError(error_msg)
        
        # 🆕 After streaming generation completes successfully, save prompt for accurate token calculation
        prompt_collector = get_file_prompt_collector()
        if prompt_collector.enabled:
            messages_dict = [self._message_to_dict(msg) for msg in messages]
            # Extract metadata from kwargs
            metadata = kwargs.get("metadata", {})
            prompt_collector.record_chat_prompt(
                messages=messages_dict,
                model=self.config.model_name,
                memory_level=metadata.get("memory_level"),
                trigger_type=metadata.get("trigger_type"),
                metadata=metadata
            )
    
    @handle_llm_errors
    async def complete(self, prompt: str, **kwargs) -> str:
        """Text completion"""
        # Convert completion to chat format
        messages = [Message(role=MessageRole.USER, content=prompt)]
        response = await self.chat(messages, **kwargs)
        return response.content
    
    @handle_llm_errors
    async def embed(self, text: str, **kwargs) -> EmbeddingResponse:
        """Text embedding (refactored - true async)"""
        await self._ensure_initialized()
        
        start_time = time.time()
        
        # Use embedding model or default model
        embedding_model = kwargs.get("model", "text-embedding-ada-002")
        
        request_data = {
            "model": embedding_model,
            "input": text,
            "encoding_format": "float"
        }
        
        # Use API key round-robin
        api_key = self._get_api_key()
        try:
            # Apply rate limiting
            await self._rate_limiter.acquire(priority=Priority.NORMAL, timeout=60.0)
            
            # Send request
            url = f"{self.base_url}/embeddings"
            headers = self._get_headers(api_key)
            
            async with self._http_pool.get_session("openai") as session:
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
                            message=f"OpenAI Embedding API error: {error_text}"
                        )
                    
                    result = await response.json()
            
            # Parse response
            response_time = time.time() - start_time
            
            embedding_response = EmbeddingResponse(
                embedding=result["data"][0]["embedding"],
                model=result["model"],
                usage=result.get("usage", {}),
                response_time=response_time,
                metadata={
                    "prompt_tokens": result.get("usage", {}).get("prompt_tokens", 0),
                    "total_tokens": result.get("usage", {}).get("total_tokens", 0),
                    "embedding_dimension": len(result["data"][0]["embedding"]),
                    "api_key_used": api_key[:10] + "..."
                }
            )
            
            self.logger.debug(f"OpenAI embedding complete, elapsed: {response_time:.2f}s, dimension: {len(embedding_response.embedding)}")
            return embedding_response
            
        except Exception as e:
            self.logger.error(f"OpenAI embedding failed (API Key: {api_key[:10]}...): {e}")
            raise
        finally:
            self._return_api_key(api_key)
    
    @handle_llm_errors
    async def embed_batch(self, texts: List[str], **kwargs) -> List[EmbeddingResponse]:
        """Batch text embedding"""
        start_time = time.time()
        
        embedding_model = kwargs.get("model", "text-embedding-ada-002")
        batch_size = kwargs.get("batch_size", 100)  # OpenAI batch size limit
        
        # Process in batches
        results = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            request_data = {
                "model": embedding_model,
                "input": batch,
                "encoding_format": "float"
            }
            
            # Use API key round-robin
            api_key = self._get_api_key()
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        f"{self.base_url}/embeddings",
                        headers=self._get_headers(api_key),
                        json=request_data
                    )
                
                if response.status_code != 200:
                    error_data = response.json() if response.text else {"error": "Unknown error"}
                    raise Exception(f"OpenAI Embedding API error: {response.status_code}, {error_data}")
                
                result = response.json()
                
                # Process batch results
                for j, embedding_data in enumerate(result["data"]):
                    embedding_response = EmbeddingResponse(
                        embedding=embedding_data["embedding"],
                        model=result["model"],
                        usage=result.get("usage", {}),
                        response_time=time.time() - start_time,
                        metadata={
                            "batch_index": i + j,
                            "text_length": len(batch[j]),
                            "embedding_dimension": len(embedding_data["embedding"]),
                            "api_key_used": api_key[:10] + "..."
                        }
                    )
                    results.append(embedding_response)
                    
            except Exception as e:
                self.logger.error(f"OpenAI batch embedding failed (API Key: {api_key[:10]}...): {e}")
                raise
            finally:
                self._return_api_key(api_key)
        
        self.logger.debug(f"OpenAI batch embedding complete, count: {len(results)}, elapsed: {time.time() - start_time:.2f}s")
        return results

    async def chat_batch(self, batch_messages: List[List[Message]], **kwargs) -> List[ChatResponse]:
        """
        Batch concurrent chat conversations (fully utilize multi-API key concurrency)
        
        Args:
            batch_messages: List of message lists, each sublist represents one conversation
            **kwargs: Other parameters
            
        Returns:
            List of ChatResponse, corresponding to input order
        """
        if not batch_messages:
            return []
        
        self.logger.info(f"Starting batch concurrent chat, task count: {len(batch_messages)}")
        start_time = time.time()
        
        # Create concurrent task list
        tasks = []
        for i, messages in enumerate(batch_messages):
            task = self._chat_with_concurrency_control(messages, **kwargs)
            tasks.append(task)
        
        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results, convert exceptions to error responses
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # Create error response
                error_response = ChatResponse(
                    content=f"Batch chat task {i+1} failed: {str(result)}",
                    finish_reason="error",
                    model=self.config.model_name,
                    usage={"total_tokens": 0},
                    response_time=0.0,
                    metadata={
                        "error": str(result),
                        "task_index": i,
                        "provider": "openai",
                        "concurrent": True
                    }
                )
                final_results.append(error_response)
            else:
                final_results.append(result)
        
        total_time = time.time() - start_time
        successful_tasks = sum(1 for r in final_results if r.finish_reason != "error")
        
        self.logger.info(f"Batch concurrent chat complete: {successful_tasks}/{len(batch_messages)} successful, elapsed: {total_time:.2f}s")
        self.logger.info(f"Concurrency efficiency: average {total_time/len(batch_messages):.2f}s per task")
        
        return final_results
    
    @handle_llm_errors
    async def summarize(self, text: str, **kwargs) -> str:
        """Text summarization"""
        max_length = kwargs.get("max_length", 200)
        
        # Use prompt manager
        from timem.utils.prompt_manager import get_prompt_manager
        
        prompt_manager = get_prompt_manager()
        prompt_template = prompt_manager.get_prompt("general_text_summary")
        
        if not prompt_template:
            # If prompt not found, fall back to default implementation
            system_prompt = f"""You are a professional text summarization assistant. Please summarize the following text with these requirements:
1. Keep length within {max_length} characters
2. Retain key information and core viewpoints
3. Maintain logical clarity and coherence"""
            user_prompt = f"Please summarize the following text:\n\n{text}"
            messages = self.format_chat_prompt(system_prompt, user_prompt)
        else:
            # Use prompt template
            formatted_prompt = prompt_template.format(text=text, max_length=max_length)
            messages = self.format_chat_prompt("", formatted_prompt)
        
        response = await self.chat(messages, **kwargs)
        return response.content
    
    async def validate_model(self, model_name: str) -> bool:
        """Validate if model is available"""
        try:
            # Try to get model information
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/models/{model_name}",
                    headers=self._get_headers()
                )
                return response.status_code == 200
        except Exception as e:
            self.logger.warning(f"Model validation failed: {model_name}, error: {e}")
            return False
    
    async def get_model_info(self, model_name: str) -> Dict[str, Any]:
        """Get model information"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/models/{model_name}",
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    model_data = response.json()
                    
                    # Add local configuration information
                    if model_name in self.chat_models:
                        model_data.update(self.chat_models[model_name])
                    elif model_name in self.embedding_models:
                        model_data.update(self.embedding_models[model_name])
                    
                    return model_data
                else:
                    return {"error": f"Failed to get model information: {response.status_code}"}
        except Exception as e:
            return {"error": f"Error occurred while getting model information: {e}"}
    
    async def get_available_models(self) -> List[Dict[str, Any]]:
        """Get available models list"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/models",
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    return response.json().get("data", [])
                else:
                    return []
        except Exception as e:
            self.logger.error(f"Failed to get available models list: {e}")
            return []
    
    async def estimate_cost(self, messages: List[Message], **kwargs) -> Dict[str, Any]:
        """Estimate API call cost"""
        # Simplified cost estimation (actual prices may vary)
        model_pricing = {
            "gpt-4": {"input": 0.00003, "output": 0.00006},  # per token
            "gpt-4-turbo": {"input": 0.00001, "output": 0.00003},
            "gpt-3.5-turbo": {"input": 0.0000015, "output": 0.000002},
            "text-embedding-ada-002": {"input": 0.0000001, "output": 0},
            "text-embedding-3-small": {"input": 0.00000002, "output": 0},
            "text-embedding-3-large": {"input": 0.00000013, "output": 0}
        }
        
        model_name = self.config.model_name
        pricing = model_pricing.get(model_name, {"input": 0, "output": 0})
        
        # Calculate input tokens
        input_tokens = sum(self.calculate_tokens(msg.content) for msg in messages)
        
        # Estimate output tokens (based on max_tokens or default value)
        output_tokens = kwargs.get("max_tokens", self.config.max_tokens or 100)
        
        # Calculate cost
        input_cost = input_tokens * pricing["input"]
        output_cost = output_tokens * pricing["output"]
        total_cost = input_cost + output_cost
        
        return {
            "model": model_name,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "input_cost": input_cost,
            "output_cost": output_cost,
            "total_cost": total_cost,
            "currency": "USD"
        }
    
    def get_context_window(self, model_name: str) -> int:
        """Get model context window size"""
        if model_name in self.chat_models:
            return self.chat_models[model_name]["context_window"]
        elif model_name in self.embedding_models:
            return self.embedding_models[model_name]["max_tokens"]
        else:
            return 4096  # Default value
    
    def truncate_messages(self, messages: List[Message], max_tokens: int) -> List[Message]:
        """Truncate messages to fit context window"""
        if not messages:
            return messages
        
        # Calculate total tokens of current messages
        total_tokens = sum(self.calculate_tokens(msg.content) for msg in messages)
        
        if total_tokens <= max_tokens:
            return messages
        
        # Keep system message and last user message
        truncated = []
        if messages[0].role == MessageRole.SYSTEM:
            truncated.append(messages[0])
            messages = messages[1:]
        
        # Add messages from back to front until token limit is reached
        current_tokens = sum(self.calculate_tokens(msg.content) for msg in truncated)
        
        for msg in reversed(messages):
            msg_tokens = self.calculate_tokens(msg.content)
            if current_tokens + msg_tokens <= max_tokens:
                truncated.insert(-1 if truncated and truncated[0].role == MessageRole.SYSTEM else 0, msg)
                current_tokens += msg_tokens
            else:
                break
        
        return truncated 