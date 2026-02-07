"""
Zhipu AI Adapter (Production-grade - True Async I/O)
Implements concrete interface for Zhipu AI API using production-grade resilient architecture
"""
import os
import time
import asyncio
from typing import Any, Dict, List, Optional, AsyncIterator
import aiohttp
import httpx
import json

from llm.base_llm import BaseLLM, Message, MessageRole, ChatResponse, EmbeddingResponse, ModelConfig, handle_llm_errors
from llm.core import (
    AsyncHTTPPool, get_global_http_pool,
    CircuitBreaker, CircuitBreakerConfig, get_global_breaker_manager,
    SmartRetry, RetryConfig, get_global_retry_manager,
    AdaptiveRateLimiter, RateLimitConfig, Priority, get_global_limiter_manager,
    MetricsCollector, LLMMetrics, get_global_metrics_collector,
    NoFallbackPolicy, get_global_no_fallback_policy,
)
from llm.file_prompt_collector import get_file_prompt_collector
from timem.utils.config_manager import get_llm_config
from timem.utils.logging import get_logger

logger = get_logger(__name__)


class ZhipuAIAdapter(BaseLLM):
    """
    Zhipu AI model adapter (Production-grade - True Async I/O + Resilient architecture)
    """
    def __init__(self, config: Optional[ModelConfig] = None):
        # Get configuration
        llm_config = get_llm_config().get("providers", {}).get("zhipuai", {})
        
        if config is None:
            config = ModelConfig(
                model_name=llm_config.get("model", "glm-4-flash"),
                temperature=llm_config.get("temperature", 0.7),
                max_tokens=llm_config.get("max_tokens", 2048)
            )
        
        super().__init__(config)
        
        # First get API key from config file
        self.api_key = llm_config.get("api_key") or os.getenv("ZHIPUAI_API_KEY")
        if not self.api_key:
            raise ValueError("Zhipu AI API Key not found. Please set API key in config file or environment variable.")
        
        self.base_url = "https://open.bigmodel.cn/api/paas/v4"
        
        # Initialize multi-API key support
        self.api_keys = []
        self._current_key_index = 0
        self._init_multi_api_keys(llm_config)
        
        # Embedding model configuration
        embedding_config = get_llm_config().get("embedding", {})
        self.embedding_model_name = embedding_config.get("model", "embedding-3")
        
        self.supported_models = ["glm-4.5", "glm-4.5-flash", "glm-4-flash", "glm-4", "glm-3-turbo", "glm-z1-flash"]
        
        # Resilient components (lazy initialization)
        self._http_pool: Optional[AsyncHTTPPool] = None
        self._circuit_breaker: Optional[CircuitBreaker] = None
        self._rate_limiter: Optional[AdaptiveRateLimiter] = None
        self._retrier: Optional[SmartRetry] = None
        self._metrics_collector: Optional[MetricsCollector] = None
        self._no_fallback_policy: Optional[NoFallbackPolicy] = None
        self._initialized = False
        self._init_lock = asyncio.Lock()
        
        logger.info(f"Zhipu AI adapter initialized successfully: model={config.model_name}")
        logger.info(f"Multi-API keys: {len(self.api_keys)} keys")

    def _init_multi_api_keys(self, zhipuai_config: Dict[str, Any]):
        """Initialize multi-API key support"""
        # Add primary API key
        if self.api_key:
            self.api_keys.append(self.api_key)
        
        # Add test API keys
        test_api_key_number = zhipuai_config.get("test_api_key_number", 0)
        for i in range(1, test_api_key_number + 1):
            test_key = zhipuai_config.get(f"test_api_key_{i}")
            if test_key:
                self.api_keys.append(test_key)
        
        logger.info(f"Initialized {len(self.api_keys)} API keys")

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
            
            # Initialize circuit breaker (optimized for LLM calls: more tolerant circuit breaking)
            breaker_manager = await get_global_breaker_manager()
            self._circuit_breaker = await breaker_manager.get_breaker(
                "zhipuai",
                CircuitBreakerConfig(
                    failure_threshold=20,  # Increased failure threshold to avoid temporary network issues triggering circuit break
                    failure_rate_threshold=0.8,  # Only break at 80% failure rate
                    min_calls_threshold=5,  # Need at least 5 calls to calculate failure rate
                    time_window=60.0,  # Extended time window to 60 seconds
                    recovery_timeout=60.0,  # Extended recovery time to 60 seconds
                )
            )
            
            # Initialize rate limiter
            # ZhipuAI glm-4-flash: 1 key supports 20 concurrent, dynamically set QPS based on key count
            num_keys = len(self.api_keys) if self.api_keys else 1
            # Each key supports 20 concurrent, considering average response time 2 seconds, approximately 10 QPS per key
            base_qps = num_keys * 15.0  # 15 QPS per key (conservative estimate)
            burst_capacity = num_keys * 20  # 20 concurrent per key
            
            limiter_manager = await get_global_limiter_manager()
            self._rate_limiter = await limiter_manager.get_limiter(
                "zhipuai",
                RateLimitConfig(
                    qps=base_qps,
                    burst=min(burst_capacity, 100),  # Burst = key count * 20, max 100
                    adaptive=True,
                    min_qps=10.0,
                    max_qps=num_keys * 30.0,  # Maximum = key count * 30
                )
            )
            
            logger.info(f"ZhipuAI rate limiter config: keys={num_keys}, qps={base_qps:.1f}, burst={min(burst_capacity, 100)}")
            
            # Initialize retrier
            retry_manager = get_global_retry_manager()
            self._retrier = retry_manager.get_retrier(
                "zhipuai",
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
                logger.info(f"✅ NoFallback policy enabled, strict_mode={self._no_fallback_policy.strict_mode}")
            
            self._initialized = True
            logger.info("Zhipu AI adapter resilient components initialization complete")

    async def chat(self, messages: List[Message], **kwargs) -> ChatResponse:
        """Chat conversation (production-grade - true async + resilient architecture)"""
        await self._ensure_initialized()
        
        start_time = time.time()
        api_key = self._get_api_key()
        
        try:
            # Convert message format
            messages_for_api = []
            for msg in messages:
                messages_for_api.append({"role": msg.role.value, "content": msg.content})
            
            # Build request data
            request_data = self._get_model_specific_params(self.config.model_name, **kwargs)
            request_data['messages'] = messages_for_api
            
            # Collect prompt for accurate token calculation
            prompt_collector = get_file_prompt_collector()
            prompt_record_id = None
            if prompt_collector.enabled:
                prompt_record_id = prompt_collector.record_chat_prompt(
                    messages=messages_for_api,
                    model=self.config.model_name,
                    metadata=kwargs.get("metadata", {})
                )
            
            # Apply rate limiting
            await self._rate_limiter.acquire(priority=Priority.NORMAL, timeout=60.0)
            
            # Execute via circuit breaker (with retry)
            result = await self._circuit_breaker.call(
                self._retrier.execute,
                self._execute_http_request,
                request_data,
                api_key
            )
            
            # Parse response
            response_time = time.time() - start_time
            
            # Extract response content
            content = ""
            if result.get("choices") and len(result["choices"]) > 0:
                content = result["choices"][0]["message"]["content"] or ""
            
            # Clean thinking content (for glm-z1-flash)
            content = self._clean_thinking_content(content, self.config.model_name)
            
            # Extract real token information
            usage_data = result.get("usage", {})
            prompt_tokens = usage_data.get("prompt_tokens", 0)
            completion_tokens = usage_data.get("completion_tokens", 0)
            total_tokens = usage_data.get("total_tokens", 0)
            
            # If API doesn't return token info, use estimation
            if total_tokens == 0:
                total_tokens = self.calculate_tokens(content)
                completion_tokens = total_tokens
                prompt_tokens = 0  # Cannot accurately estimate input
            
            # Apply NoFallback policy to validate response
            if self._no_fallback_policy and self._no_fallback_policy.enabled and self._no_fallback_policy.strict_mode:
                if not self._no_fallback_policy.validate_response(content):
                    error_msg = f"Detected invalid response (possibly fallback content): {content[:100]}..."
                    logger.error(error_msg)
                    raise ValueError(error_msg)
            
            chat_response = ChatResponse(
                content=content,
                finish_reason="stop",
                model=self.config.model_name,
                usage={
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens
                },
                response_time=response_time,
                metadata={
                    "provider": "zhipuai",
                    "api_key_used": api_key[:10] + "...",
                    "resilient": True,
                    "no_fallback": self._no_fallback_policy.enabled if self._no_fallback_policy else False,
                    "prompt_record_id": prompt_record_id  # Collect prompt for accurate token calculation
                }
            )
            
            # Record success metrics
            self._metrics_collector.record(LLMMetrics(
                provider="zhipuai",
                model=self.config.model_name,
                timestamp=start_time,
                success=True,
                latency=response_time,
                tokens=self.calculate_tokens(content)
            ))
            
            logger.debug(f"Zhipu AI chat success, elapsed: {response_time:.2f}s")
            return chat_response
            
        except aiohttp.ClientResponseError as e:
            # Detect 429 rate limit
            if e.status == 429:
                await self._rate_limiter.report_rate_limit()
            
            # Record failure metrics
            self._metrics_collector.record(LLMMetrics(
                provider="zhipuai",
                model=self.config.model_name,
                timestamp=start_time,
                success=False,
                latency=time.time() - start_time,
                error=str(e)
            ))
            
            logger.error(f"Zhipu AI chat failed (HTTP {e.status}): {e}", exc_info=True)
            raise
        
        except Exception as e:
            # Record failure metrics
            self._metrics_collector.record(LLMMetrics(
                provider="zhipuai",
                model=self.config.model_name,
                timestamp=start_time,
                success=False,
                latency=time.time() - start_time,
                error=str(e)
            ))
            
            logger.error(f"Zhipu AI chat failed: {e}", exc_info=True)
            raise
    
    async def _execute_http_request(self, request_data: dict, api_key: str) -> dict:
        """Execute true async HTTP request"""
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # Use global connection pool session (engineering-grade - fast failure detection)
        async with self._http_pool.get_session("zhipuai") as session:
            async with session.post(
                url,
                json=request_data,
                headers=headers,
                # Fine-grained timeout configuration: millisecond-level failure detection
                timeout=aiohttp.ClientTimeout(
                    total=60.0,  # Total timeout 60 seconds
                    connect=3.0,  # TCP connection 3 second timeout
                    sock_connect=2.0,  # Socket connection 2 second timeout
                    sock_read=30.0  # Socket read 30 second timeout
                )
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise aiohttp.ClientResponseError(
                        request_info=response.request_info,
                        history=response.history,
                        status=response.status,
                        message=f"Zhipu AI API error: {error_text}"
                    )
                
                return await response.json()
    
    def _get_model_specific_params(self, model_name: str, **kwargs) -> Dict[str, Any]:
        """Get model-specific parameter configuration"""
        params = {
            "model": model_name,
            "temperature": kwargs.get('temperature', self.config.temperature),
            "top_p": kwargs.get('top_p', 0.7),
            "max_tokens": kwargs.get('max_tokens', self.config.max_tokens)
        }
        
        # For glm-z1-flash, remove thinking-related parameters
        if model_name == "glm-z1-flash":
            params.pop('enable_thinking', None)
            params.pop('thinking', None)
            params.pop('think_mode', None)
            params['stream'] = kwargs.get('stream', False)
            
            logger.info(f"glm-z1-flash model config: removed thinking parameters")
        
        return params
    
    def _clean_thinking_content(self, content: str, model_name: str) -> str:
        """Clean thinking-related content from GLM-Z1-Flash response"""
        if model_name != "glm-z1-flash":
            return content
        
        if not content:
            return content
        
        import re
        
        # Remove thinking tags
        cleaned_content = re.sub(r'<think[^>]*>.*?</think>', '', content, flags=re.DOTALL | re.IGNORECASE)
        cleaned_content = re.sub(r'<thinking[^>]*>.*?</thinking>', '', cleaned_content, flags=re.DOTALL | re.IGNORECASE)
        
        # Clean extra whitespace
        cleaned_content = re.sub(r'\n\s*\n\s*\n+', '\n\n', cleaned_content)
        cleaned_content = cleaned_content.strip()
        
        if not cleaned_content:
            cleaned_content = "Sorry, unable to provide accurate answer."
        
        return cleaned_content
    
    async def chat_stream(self, messages: List[Message], **kwargs) -> AsyncIterator[str]:
        """Streaming chat conversation (production-grade - true async streaming + resilient architecture)"""
        await self._ensure_initialized()
        
        start_time = time.time()
        api_key = self._get_api_key()
        
        # Convert message format
        messages_for_api = []
        for msg in messages:
            messages_for_api.append({"role": msg.role.value, "content": msg.content})
        
        # Build request data
        request_data = self._get_model_specific_params(self.config.model_name, **kwargs)
        request_data['messages'] = messages_for_api
        request_data['stream'] = True  # Enable streaming
        
        # Apply rate limiting
        await self._rate_limiter.acquire(priority=Priority.NORMAL, timeout=60.0)
        
        # Content collection for NoFallback validation
        collected_content = []
        
        # Execute streaming request directly (cannot be wrapped by circuit breaker)
        async def _execute_stream():
            """Internal function to execute streaming request"""
            url = f"{self.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            # Use global connection pool session (engineering-grade - fast failure detection)
            async with self._http_pool.get_session("zhipuai") as session:
                async with session.post(
                    url,
                    json=request_data,
                    headers=headers,
                    # Fine-grained timeout configuration: millisecond-level failure detection
                    timeout=aiohttp.ClientTimeout(
                        total=120.0,  # Total timeout 120 seconds (streaming may be longer)
                        connect=3.0,  # TCP connection 3 second timeout
                        sock_connect=2.0,  # Socket connection 2 second timeout
                        sock_read=30.0  # Socket read 30 second timeout
                    )
                ) as response:
                    
                    if response.status != 200:
                        error_text = await response.text()
                        raise aiohttp.ClientResponseError(
                            request_info=response.request_info,
                            history=response.history,
                            status=response.status,
                            message=f"Zhipu AI streaming API error: {error_text}"
                        )
                    
                    # Stream read response
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
                                        content = delta["content"]
                                        # Clean thinking content (for glm-z1-flash)
                                        cleaned_content = self._clean_thinking_content(content, self.config.model_name)
                                        if cleaned_content:
                                            collected_content.append(cleaned_content)
                                            yield cleaned_content
                            except json.JSONDecodeError:
                                continue
        
        try:
            # Execute streaming request directly (cannot be wrapped by circuit breaker)
            async for chunk in _execute_stream():
                yield chunk
            
            # After streaming ends, apply NoFallback policy to validate complete content
            if self._no_fallback_policy and self._no_fallback_policy.enabled and self._no_fallback_policy.strict_mode:
                full_content = "".join(collected_content)
                if full_content and not self._no_fallback_policy.validate_response(full_content):
                    error_msg = f"Streaming response validation failed (detected fallback content): {full_content[:100]}..."
                    logger.error(error_msg)
                    raise ValueError(error_msg)
            
            # Record success metrics
            response_time = time.time() - start_time
            self._metrics_collector.record(LLMMetrics(
                provider="zhipuai",
                model=self.config.model_name,
                timestamp=start_time,
                success=True,
                latency=response_time,
                tokens=self.calculate_tokens("".join(collected_content))
            ))
            
            # After streaming generation completes successfully, save prompt for accurate token calculation
            prompt_collector = get_file_prompt_collector()
            if prompt_collector.enabled:
                # Extract metadata from kwargs
                metadata = kwargs.get("metadata", {})
                prompt_collector.record_chat_prompt(
                    messages=messages_for_api,
                    model=self.config.model_name,
                    memory_level=metadata.get("memory_level"),
                    trigger_type=metadata.get("trigger_type"),
                    metadata=metadata
                )
            
        except aiohttp.ClientConnectorError as e:
            # Network connection error
            logger.error(f"Zhipu AI streaming connection failed: {e}")
            self._metrics_collector.record(LLMMetrics(
                provider="zhipuai",
                model=self.config.model_name,
                timestamp=start_time,
                success=False,
                latency=time.time() - start_time,
                error=f"Connection failed: {e}"
            ))
            raise
        
        except aiohttp.ClientResponseError as e:
            # Detect 429 rate limit
            if e.status == 429:
                await self._rate_limiter.report_rate_limit()
            
            logger.error(f"Zhipu AI streaming API error (HTTP {e.status}): {e}")
            self._metrics_collector.record(LLMMetrics(
                provider="zhipuai",
                model=self.config.model_name,
                timestamp=start_time,
                success=False,
                latency=time.time() - start_time,
                error=str(e)
            ))
            raise
        
        except Exception as e:
            logger.error(f"Zhipu AI streaming call failed: {e}")
            self._metrics_collector.record(LLMMetrics(
                provider="zhipuai",
                model=self.config.model_name,
                timestamp=start_time,
                success=False,
                latency=time.time() - start_time,
                error=str(e)
            ))
            raise
    
    async def complete(self, prompt: str, **kwargs) -> str:
        """Text completion"""
        messages = [Message(role=MessageRole.USER, content=prompt)]
        response = await self.chat(messages, **kwargs)
        return response.content
    
    async def embed(self, text: str, **kwargs) -> EmbeddingResponse:
        """Text embedding (refactored)"""
        await self._ensure_initialized()

        start_time = time.time()

        # Use embedding model
        embedding_model = kwargs.get("model", "embedding-3")

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

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

            # Use httpx.AsyncClient for async request
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.base_url + "/embeddings",
                    headers=headers,
                    json=request_data
                )
                response.raise_for_status()
                result = response.json()

            response_time = time.time() - start_time

            # Extract embedding vector
            embedding = result["data"][0]["embedding"]

            return EmbeddingResponse(
                embedding=embedding,
                model=embedding_model,
                usage=result.get("usage", {}),
                response_time=response_time,
                metadata={
                    "prompt_tokens": result.get("usage", {}).get("prompt_tokens", 0),
                    "total_tokens": result.get("usage", {}).get("total_tokens", 0),
                    "embedding_dimension": len(embedding),
                    "api_key_used": api_key[:10] + "..."
                }
            )

        except httpx.HTTPStatusError as e:
            error_detail = e.response.text if e.response else str(e)
            status_code = e.response.status_code if e.response else "Unknown"
            logger.error(f"ZhipuAI embedding HTTP error: {status_code} - {error_detail}")
            raise
        except Exception as e:
            logger.error(f"ZhipuAI embedding call failed: {e}")
            raise

    async def embed_batch(self, texts: List[str], **kwargs) -> List[EmbeddingResponse]:
        """Batch text embedding (refactored)"""
        # ZhipuAI supports batch embedding
        await self._ensure_initialized()

        start_time = time.time()

        # Use embedding model
        embedding_model = kwargs.get("model", "embedding-3")

        # Limit batch size
        batch_size = min(len(texts), 100)  # ZhipuAI max 100 texts per request
        texts_to_embed = texts[:batch_size]

        request_data = {
            "model": embedding_model,
            "input": texts_to_embed,
            "encoding_format": "float"
        }

        # Use API key round-robin
        api_key = self._get_api_key()
        try:
            # Apply rate limiting
            await self._rate_limiter.acquire(priority=Priority.NORMAL, timeout=60.0)

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

            # Use httpx.AsyncClient for async request
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.base_url + "/embeddings",
                    headers=headers,
                    json=request_data
                )
                response.raise_for_status()
                result = response.json()

            response_time = time.time() - start_time

            # Extract embedding vectors
            embeddings = [item["embedding"] for item in result["data"]]

            # Create EmbeddingResponse for each text
            responses = []
            for i, embedding in enumerate(embeddings):
                responses.append(EmbeddingResponse(
                    embedding=embedding,
                    model=embedding_model,
                    usage=result.get("usage", {}),
                    response_time=response_time,
                    metadata={
                        "prompt_tokens": result.get("usage", {}).get("prompt_tokens", 0),
                        "total_tokens": result.get("usage", {}).get("total_tokens", 0),
                        "embedding_dimension": len(embedding),
                        "api_key_used": api_key[:10] + "..."
                    }
                ))

            return responses

        except httpx.HTTPStatusError as e:
            error_detail = e.response.text if e.response else str(e)
            logger.error(f"ZhipuAI batch embedding HTTP error: {e.status_code} - {error_detail}")
            raise
        except Exception as e:
            logger.error(f"ZhipuAI batch embedding call failed: {e}")
            raise
    
    async def summarize(self, text: str, **kwargs) -> str:
        """Text summarization"""
        prompt = f"Please summarize the following text:\n\n{text}"
        return await self.complete(prompt, **kwargs)
    
    async def validate_model(self, model_name: str) -> bool:
        """Validate if model is available"""
        return model_name in self.supported_models
    
    async def get_model_info(self, model_name: str) -> Dict[str, Any]:
        """Get model information"""
        return {
            "model_name": model_name,
            "provider": "zhipuai",
            "type": "chat",
            "supported": model_name in self.supported_models,
        }
