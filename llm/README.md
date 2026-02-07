# LLM Adapter Layer

This module provides a unified large language model interface for the anonymized system, supporting multiple LLM providers including OpenAI, Claude, ZhipuAI, Qwen, etc.

## 🏗️ Module Structure

```
llm/
├── base_llm.py                    # LLM base interface
├── llm_manager.py                 # LLM manager
├── embedding_service.py           # Embedding service
├── http_client_manager.py         # HTTP client manager
├── openai_adapter.py              # OpenAI adapter
├── claude_adapter.py              # Claude adapter
├── zhipuai_adapter.py             # ZhipuAI adapter
├── qwen_adapter.py                # Qwen API adapter (DashScope)
├── qwen_local_adapter.py          # Qwen local adapter
├── qwen_embedding_adapter.py      # Qwen embedding adapter
├── cst_adapter.py                 # CST cloud adapter
├── mock_adapter.py                # Mock adapter
└── core/                          # Core functionality modules
    ├── resilient_client.py        # Resilient client
    ├── circuit_breaker.py         # Circuit breaker
    ├── smart_retry.py             # Smart retry
    ├── adaptive_rate_limiter.py   # Adaptive rate limiter
    ├── fallback_manager.py        # Fallback manager
    └── metrics_collector.py       # Metrics collector
```

## 🎯 Core Features

### 1. **Unified LLM Interface** (`base_llm.py`)
Provides a unified LLM interface supporting multiple providers:

```python
class BaseLLM(ABC):
    """LLM base interface"""
    
    @abstractmethod
    async def generate(
        self, 
        messages: List[Dict[str, str]], 
        **kwargs
    ) -> str:
        """Generate text"""
        pass
    
    @abstractmethod
    async def generate_stream(
        self, 
        messages: List[Dict[str, str]], 
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Stream text generation"""
        pass
    
    @abstractmethod
    async def get_embedding(self, text: str) -> List[float]:
        """Get text embedding"""
        pass
```

### 2. **LLM Manager** (`llm_manager.py`)
Dynamically loads and manages different LLM adapters:

```python
def get_llm(provider: Optional[str] = None) -> BaseLLM:
    """Get LLM adapter instance for specified provider"""
    if provider is None:
        provider = get_llm_config().get("default_provider", "openai")
    
    return _get_llm_cached(provider)

@lru_cache(maxsize=4)
def _get_llm_cached(provider: str) -> BaseLLM:
    """Get LLM adapter instance (cached version)"""
    if provider == "openai":
        return OpenAIAdapter()
    elif provider == "claude":
        return ClaudeAdapter()
    elif provider == "zhipuai":
        return ZhipuAIAdapter()
    elif provider == "cst":
        return CSTCloudAdapter()
    elif provider == "qwen":
        return QwenAdapter()
    elif provider == "qwen_local":
        return QwenLocalAdapter()
    elif provider == "mock":
        return MockLLMAdapter()
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")
```

### 3. **OpenAI 适配器** (`openai_adapter.py`)
OpenAI GPT 系列模型适配器：

```python
class OpenAIAdapter(BaseLLM):
    """OpenAI 适配器"""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-3.5-turbo"):
        self.client = OpenAI(api_key=api_key)
        self.model = model
    
    async def generate(
        self, 
        messages: List[Dict[str, str]], 
        **kwargs
    ) -> str:
        """生成文本"""
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            **kwargs
        )
        return response.choices[0].message.content
    
    async def generate_stream(
        self, 
        messages: List[Dict[str, str]], 
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """流式生成文本"""
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
            **kwargs
        )
        
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
```

### 4. **Claude 适配器** (`claude_adapter.py`)
Anthropic Claude 模型适配器：

```python
class ClaudeAdapter(BaseLLM):
    """Claude 适配器"""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "claude-3-sonnet-20240229"):
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model
    
    async def generate(
        self, 
        messages: List[Dict[str, str]], 
        **kwargs
    ) -> str:
        """生成文本"""
        # 转换消息格式
        claude_messages = self._convert_messages(messages)
        
        response = await self.client.messages.create(
            model=self.model,
            messages=claude_messages,
            **kwargs
        )
        return response.content[0].text
```

### 5. **智谱AI 适配器** (`zhipuai_adapter.py`)
智谱AI GLM 系列模型适配器：

```python
class ZhipuAIAdapter(BaseLLM):
    """智谱AI 适配器"""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "glm-4"):
        self.client = ZhipuAI(api_key=api_key)
        self.model = model
    
    async def generate(
        self, 
        messages: List[Dict[str, str]], 
        **kwargs
    ) -> str:
        """生成文本"""
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            **kwargs
        )
        return response.choices[0].message.content
```

### 5.5. **通义千问 API 适配器** (`qwen_adapter.py`)
阿里云通义千问系列模型适配器，使用 DashScope API（兼容 OpenAI 格式）：

```python
class QwenAdapter(BaseLLM):
    """Qwen API 适配器（兼容OpenAI格式 + 弹性架构）"""
    
    def __init__(self, config: Optional[ModelConfig] = None):
        # 从配置文件加载
        qwen_config = get_llm_config().get("providers", {}).get("qwen", {})
        self.api_key = qwen_config.get("api_key", "")
        self.base_url = qwen_config.get("base_url", 
            "https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.model = qwen_config.get("model", "qwen-plus")
    
    async def chat(self, messages: List[Message], **kwargs) -> ChatResponse:
        """聊天对话（使用弹性架构）"""
        # 使用断路器、重试、限流等机制
        response = await self._execute_http_request(request_data, api_key)
        return ChatResponse(...)
```

**配置示例** (`config/settings.yaml`):
```yaml
llm:
  providers:
    qwen:
      api_key: "sk-xxxxx"  # 阿里云 API Key
      base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
      model: "qwen-plus"  # 可选: qwen-turbo, qwen-plus, qwen-max
      temperature: 0.7
      max_tokens: 2048
      timeout: 90
      max_retries: 3
```

**使用示例**:
```python
from llm import get_llm
from llm.base_llm import Message, MessageRole

# 获取 Qwen 适配器
qwen = get_llm("qwen")

# 聊天对话
messages = [
    Message(role=MessageRole.USER, content="你好，请介绍一下你自己。")
]
response = await qwen.chat(messages)
print(response.content)
```

### 6. **嵌入服务** (`embedding_service.py`)
统一的文本嵌入服务：

```python
class EmbeddingService:
    """嵌入服务"""
    
    def __init__(self, provider: str = "openai"):
        self.provider = provider
        self.embedding_client = self._get_embedding_client()
    
    async def get_embedding(self, text: str) -> List[float]:
        """获取文本嵌入"""
        if self.provider == "openai":
            return await self._get_openai_embedding(text)
        elif self.provider == "qwen":
            return await self._get_qwen_embedding(text)
        else:
            raise ValueError(f"不支持的嵌入提供商: {self.provider}")
    
    async def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """批量获取嵌入"""
        embeddings = []
        for text in texts:
            embedding = await self.get_embedding(text)
            embeddings.append(embedding)
        return embeddings
```

## 🔧 核心功能模块

### 1. **弹性客户端** (`core/resilient_client.py`)
提供高可用的 HTTP 客户端：

```python
class ResilientClient:
    """弹性 HTTP 客户端"""
    
    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url
        self.timeout = timeout
        self.circuit_breaker = CircuitBreaker()
        self.retry_strategy = SmartRetry()
    
    async def request(
        self, 
        method: str, 
        url: str, 
        **kwargs
    ) -> Response:
        """发送请求"""
        # 熔断器检查
        if not self.circuit_breaker.can_execute():
            raise CircuitBreakerOpenError("熔断器已打开")
        
        # 智能重试
        return await self.retry_strategy.execute(
            self._make_request, method, url, **kwargs
        )
```

### 2. **熔断器** (`core/circuit_breaker.py`)
防止级联故障：

```python
class CircuitBreaker:
    """熔断器"""
    
    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def can_execute(self) -> bool:
        """检查是否可以执行请求"""
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.timeout:
                self.state = "HALF_OPEN"
                return True
            return False
        return True
    
    def record_success(self):
        """记录成功"""
        self.failure_count = 0
        self.state = "CLOSED"
    
    def record_failure(self):
        """记录失败"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
```

### 3. **智能重试** (`core/smart_retry.py`)
自适应重试策略：

```python
class SmartRetry:
    """智能重试策略"""
    
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
    
    async def execute(self, func, *args, **kwargs):
        """执行函数并重试"""
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                
                if attempt < self.max_retries:
                    delay = self._calculate_delay(attempt)
                    await asyncio.sleep(delay)
                else:
                    break
        
        raise last_exception
    
    def _calculate_delay(self, attempt: int) -> float:
        """计算重试延迟"""
        return self.base_delay * (2 ** attempt) + random.uniform(0, 1)
```

### 4. **自适应限流** (`core/adaptive_rate_limiter.py`)
动态调整请求频率：

```python
class AdaptiveRateLimiter:
    """自适应限流器"""
    
    def __init__(self, initial_rate: int = 100, max_rate: int = 1000):
        self.current_rate = initial_rate
        self.max_rate = max_rate
        self.min_rate = 10
        self.success_count = 0
        self.error_count = 0
    
    async def acquire(self) -> bool:
        """获取请求许可"""
        if self._should_rate_limit():
            return False
        
        # 更新统计信息
        self._update_metrics()
        return True
    
    def _should_rate_limit(self) -> bool:
        """判断是否应该限流"""
        # 基于错误率调整限流
        total_requests = self.success_count + self.error_count
        if total_requests > 0:
            error_rate = self.error_count / total_requests
            if error_rate > 0.1:  # 错误率超过10%
                self.current_rate = max(self.min_rate, self.current_rate * 0.8)
            elif error_rate < 0.01:  # 错误率低于1%
                self.current_rate = min(self.max_rate, self.current_rate * 1.1)
        
        return self._is_rate_limited()
```

### 5. **降级管理** (`core/fallback_manager.py`)
自动降级到备用服务：

```python
class FallbackManager:
    """降级管理器"""
    
    def __init__(self, primary_provider: str, fallback_providers: List[str]):
        self.primary_provider = primary_provider
        self.fallback_providers = fallback_providers
        self.current_provider = primary_provider
    
    async def execute_with_fallback(self, func, *args, **kwargs):
        """执行函数并自动降级"""
        providers = [self.current_provider] + self.fallback_providers
        
        for provider in providers:
            try:
                llm = get_llm(provider)
                return await func(llm, *args, **kwargs)
            except Exception as e:
                logger.warning(f"提供商 {provider} 失败: {e}")
                continue
        
        raise Exception("所有提供商都不可用")
```

## 🚀 使用示例

### 基本使用
```python
from llm import get_llm

# 获取 LLM 实例
llm = get_llm("openai")

# 生成文本
messages = [
    {"role": "user", "content": "请解释什么是机器学习"}
]
response = await llm.generate(messages)
print(response)

# 流式生成
async for chunk in llm.generate_stream(messages):
    print(chunk, end="")
```

### 嵌入向量
```python
from llm.embedding_service import EmbeddingService

# 创建嵌入服务
embedding_service = EmbeddingService("openai")

# 获取文本嵌入
text = "机器学习是人工智能的一个分支"
embedding = await embedding_service.get_embedding(text)
print(f"嵌入维度: {len(embedding)}")

# 批量获取嵌入
texts = ["文本1", "文本2", "文本3"]
embeddings = await embedding_service.get_embeddings_batch(texts)
print(f"批量嵌入数量: {len(embeddings)}")
```

### 弹性客户端
```python
from llm.core.resilient_client import ResilientClient

# 创建弹性客户端
client = ResilientClient("https://api.openai.com/v1")

# 发送请求（自动重试和熔断）
response = await client.request(
    "POST",
    "/chat/completions",
    json={
        "model": "gpt-3.5-turbo",
        "messages": [{"role": "user", "content": "Hello"}]
    }
)
```

### 降级管理
```python
from llm.core.fallback_manager import FallbackManager

# 创建降级管理器
fallback_manager = FallbackManager(
    primary_provider="openai",
    fallback_providers=["claude", "zhipuai"]
)

# 执行请求（自动降级）
async def generate_text(llm, messages):
    return await llm.generate(messages)

response = await fallback_manager.execute_with_fallback(
    generate_text, messages
)
```

## 📊 性能优化

### 1. **连接池管理**
```python
class HTTPClientManager:
    """HTTP 客户端管理器"""
    
    def __init__(self):
        self.connector = aiohttp.TCPConnector(
            limit=100,  # 总连接数
            limit_per_host=30,  # 每个主机的连接数
            ttl_dns_cache=300,  # DNS 缓存时间
            use_dns_cache=True,
        )
        self.session = aiohttp.ClientSession(connector=self.connector)
    
    async def close(self):
        """关闭连接池"""
        await self.session.close()
        await self.connector.close()
```

### 2. **缓存策略**
```python
class LLMCache:
    """LLM 缓存"""
    
    def __init__(self, ttl: int = 3600):
        self.cache = {}
        self.ttl = ttl
    
    def get_cache_key(self, messages: List[Dict], **kwargs) -> str:
        """生成缓存键"""
        content = json.dumps(messages, sort_keys=True)
        return hashlib.md5(content.encode()).hexdigest()
    
    async def get(self, key: str) -> Optional[str]:
        """获取缓存"""
        if key in self.cache:
            cached_data = self.cache[key]
            if time.time() - cached_data["timestamp"] < self.ttl:
                return cached_data["response"]
        return None
    
    async def set(self, key: str, response: str):
        """设置缓存"""
        self.cache[key] = {
            "response": response,
            "timestamp": time.time()
        }
```

### 3. **批量处理**
```python
class BatchProcessor:
    """批量处理器"""
    
    def __init__(self, batch_size: int = 10, delay: float = 0.1):
        self.batch_size = batch_size
        self.delay = delay
        self.pending_requests = []
    
    async def add_request(self, request):
        """添加请求到批次"""
        self.pending_requests.append(request)
        
        if len(self.pending_requests) >= self.batch_size:
            await self._process_batch()
    
    async def _process_batch(self):
        """处理批次"""
        if not self.pending_requests:
            return
        
        batch = self.pending_requests[:self.batch_size]
        self.pending_requests = self.pending_requests[self.batch_size:]
        
        # 并行处理批次
        tasks = [self._process_request(req) for req in batch]
        await asyncio.gather(*tasks)
```

## 🛡️ 错误处理

### 异常类型
```python
class LLMError(Exception):
    """LLM 基础异常"""
    pass

class RateLimitError(LLMError):
    """限流异常"""
    pass

class AuthenticationError(LLMError):
    """认证异常"""
    pass

class ServiceUnavailableError(LLMError):
    """服务不可用异常"""
    pass
```

### 错误处理策略
```python
class ErrorHandler:
    """错误处理器"""
    
    @staticmethod
    async def handle_error(error: Exception) -> str:
        """处理错误"""
        if isinstance(error, RateLimitError):
            await asyncio.sleep(1)  # 等待后重试
            raise error
        elif isinstance(error, AuthenticationError):
            logger.error("认证失败，请检查 API Key")
            raise error
        elif isinstance(error, ServiceUnavailableError):
            logger.warning("服务暂时不可用，尝试降级")
            raise error
        else:
            logger.error(f"未知错误: {error}")
            raise error
```

## 📝 开发指南

### 添加新 LLM 提供商
1. 继承 `BaseLLM` 基类
2. 实现所有抽象方法
3. 在 `llm_manager.py` 中注册
4. 添加相应的配置

### 新适配器示例
```python
class NewLLMAdapter(BaseLLM):
    """新 LLM 适配器"""
    
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.client = NewLLMClient(api_key)
    
    async def generate(
        self, 
        messages: List[Dict[str, str]], 
        **kwargs
    ) -> str:
        """生成文本"""
        response = await self.client.generate(
            messages=messages,
            model=self.model,
            **kwargs
        )
        return response.text
    
    async def generate_stream(
        self, 
        messages: List[Dict[str, str]], 
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """流式生成"""
        async for chunk in self.client.generate_stream(
            messages=messages,
            model=self.model,
            **kwargs
        ):
            yield chunk.text
    
    async def get_embedding(self, text: str) -> List[float]:
        """获取嵌入"""
        return await self.client.get_embedding(text)
```

## 🧪 测试

### 单元测试
```python
import pytest
from llm import get_llm
from llm.mock_adapter import MockLLMAdapter

@pytest.mark.asyncio
async def test_llm_generation():
    """测试 LLM 生成"""
    llm = MockLLMAdapter()
    
    messages = [{"role": "user", "content": "Hello"}]
    response = await llm.generate(messages)
    
    assert response is not None
    assert isinstance(response, str)

@pytest.mark.asyncio
async def test_embedding():
    """测试嵌入"""
    llm = MockLLMAdapter()
    
    text = "测试文本"
    embedding = await llm.get_embedding(text)
    
    assert embedding is not None
    assert isinstance(embedding, list)
    assert len(embedding) > 0
```

### 集成测试
```python
@pytest.mark.asyncio
async def test_fallback_mechanism():
    """测试降级机制"""
    fallback_manager = FallbackManager(
        primary_provider="openai",
        fallback_providers=["claude", "mock"]
    )
    
    messages = [{"role": "user", "content": "Hello"}]
    response = await fallback_manager.execute_with_fallback(
        lambda llm, msgs: llm.generate(msgs),
        messages
    )
    
    assert response is not None
```

## 📚 相关文档

- [TiMem 核心模块](../timem/README.md)
- [存储层文档](../storage/README.md)
- [API 应用层](../app/README.md)
- [OpenAI API 文档](https://platform.openai.com/docs)
- [Claude API 文档](https://docs.anthropic.com/)
- [智谱AI 文档](https://open.bigmodel.cn/dev/api)
