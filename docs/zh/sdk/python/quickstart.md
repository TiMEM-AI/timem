# Python SDK 快速开始

TiMem Python SDK 提供了简单易用的接口来与 TiMem 云服务或自托管实例进行交互。

## 安装

### 使用 pip（推荐）

```bash
pip install timem-sdk
```

### 使用 poetry

```bash
poetry add timem-sdk
```

### 使用 pipenv

```bash
pipenv install timem-sdk
```

### 从源码安装

```bash
git clone https://github.com/your-org/timem.git
cd timem
pip install -e .
```

### 开发版本安装

```bash
pip install git+https://github.com/your-org/timem.git
```

## 初始化

### 基础配置

```python
from timem import TiMemClient

# 使用 API Key 初始化
client = TiMemClient(
    api_key="your-api-key-here"
)
```

### 环境变量配置（推荐）

**创建 `.env` 文件**：

```bash
TIMEM_API_KEY=timem_sk_xxxxx
TIMEM_API_URL=https://api.timem.ai/v1
```

**加载配置**：

```python
import os
from dotenv import load_dotenv
from timem import TiMemClient

load_dotenv()

client = TiMemClient(
    api_key=os.environ.get("TIMEM_API_KEY")
)
```

### 完整配置选项

```python
client = TiMemClient(
    api_key="your-api-key",
    base_url="https://api.timem.ai/v1",  # 自定义 API 地址
    timeout=30,                          # 请求超时（秒）
    max_retries=3,                       # 最大重试次数
    enable_logging=False                 # 启用日志
)
```

## 基础用法

### 1. 添加记忆

```python
from timem import TiMemClient

client = TiMemClient(api_key="your-api-key")

# 添加对话记忆
memory = client.add_memory(
    user_id="user_123",
    content="用户说他喜欢素食，特别是意大利菜",
    session_id="session_456",  # 可选
    metadata={                 # 可选的元数据
        "source": "chat",
        "timestamp": "2025-01-18T10:00:00Z",
        "confidence": 0.95
    }
)

print(f"记忆ID: {memory.id}")
print(f"记忆内容: {memory.content}")
print(f"记忆层级: {memory.level}")
print(f"创建时间: {memory.created_at}")
```

**响应示例**：

```python
Memory(
    id="mem_xxxxx",
    user_id="user_123",
    content="用户说他喜欢素食，特别是意大利菜",
    level="L1",
    session_id="session_456",
    created_at="2025-01-18T10:00:00Z"
)
```

### 2. 搜索记忆

```python
# 语义搜索
results = client.search_memories(
    user_id="user_123",
    query="用户的饮食偏好是什么？",
    limit=5
)

for memory in results:
    print(f"[{memory.level}] {memory.content}")
    print(f"相关度: {memory.score}")
    print(f"时间: {memory.created_at}")
    print("-" * 40)
```

**搜索选项**：

```python
results = client.search_memories(
    user_id="user_123",
    query="用户的饮食偏好",
    limit=10,                    # 返回数量
    level="L2",                  # 过滤层级
    session_id="session_456",    # 过滤会话
    date_from="2025-01-01",      # 日期范围
    date_to="2025-01-31"
)
```

### 3. 获取会话记忆

```python
# 获取特定会话的所有记忆
memories = client.get_session_memories(
    user_id="user_123",
    session_id="session_456",
    limit=100
)

for memory in memories:
    print(f"[{memory.level}] {memory.content}")
```

### 4. 批量添加对话

```python
# 从对话记录批量生成记忆
conversation = [
    {"role": "user", "content": "你好，我叫张三"},
    {"role": "assistant", "content": "你好张三！很高兴认识你。"},
    {"role": "user", "content": "我喜欢编程和AI研究"},
    {"role": "assistant", "content": "太棒了！我也是AI爱好者。"},
    {"role": "user", "content": "我主要使用Python"},
]

memories = client.add_conversation(
    user_id="user_123",
    session_id="session_456",
    conversation=conversation,
    generate_levels=["L1", "L2"]  # 生成 L1 和 L2 记忆
)

print(f"生成了 {len(memories)} 条记忆")
for memory in memories:
    print(f"[{memory.level}] {memory.content}")
```

### 5. 更新记忆

```python
# 更新记忆内容
updated_memory = client.update_memory(
    memory_id="mem_xxxxx",
    content="更新后的记忆内容",
    metadata={"updated": True}
)
```

### 6. 删除记忆

```python
# 删除单条记忆
client.delete_memory(memory_id="mem_xxxxx")

# 删除会话的所有记忆
client.delete_session_memories(
    user_id="user_123",
    session_id="session_456"
)
```

## 完整示例

### AI 助手集成

```python
import os
from dotenv import load_dotenv
from timem import TiMemClient

load_dotenv()

class AIAssistant:
    """集成 TiMem 的 AI 助手"""

    def __init__(self):
        self.client = TiMemClient(
            api_key=os.environ.get("TIMEM_API_KEY")
        )
        self.user_id = "user_123"
        self.session_id = "session_456"

    def chat(self, message: str) -> str:
        """处理用户消息并生成回复"""

        # 1. 检索相关记忆
        memories = self.client.search_memories(
            user_id=self.user_id,
            query=message,
            limit=3
        )

        # 2. 构建上下文
        context = self._build_context(memories)

        # 3. 调用 LLM 生成回复
        response = self._generate_response(message, context)

        # 4. 保存对话记忆
        self._save_conversation(message, response)

        return response

    def _build_context(self, memories):
        """构建上下文"""
        if not memories:
            return "（无历史记忆）"

        context_parts = []
        for memory in memories:
            context_parts.append(f"- {memory.content}")

        return "已知信息：\n" + "\n".join(context_parts)

    def _generate_response(self, message: str, context: str) -> str:
        """生成回复（示例使用 OpenAI）"""
        from openai import OpenAI

        llm = OpenAI()

        prompt = f"""{context}

用户消息：{message}

请根据已知信息生成个性化回复。"""

        completion = llm.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}]
        )

        return completion.choices[0].message.content

    def _save_conversation(self, user_message: str, assistant_message: str):
        """保存对话记忆"""
        conversation = [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": assistant_message}
        ]

        self.client.add_conversation(
            user_id=self.user_id,
            session_id=self.session_id,
            conversation=conversation
        )

# 使用示例
if __name__ == "__main__":
    assistant = AIAssistant()

    # 第一次对话
    response1 = assistant.chat("你好，我叫李明")
    print(f"助手: {response1}")

    # 第二次对话（助手会记住用户的名字）
    response2 = assistant.chat("你还记得我的名字吗？")
    print(f"助手: {response2}")
```

### 客服机器人

```python
from timem import TiMemClient
from datetime import datetime

class SupportBot:
    """客服机器人"""

    def __init__(self):
        self.client = TiMemClient(api_key="your-api-key")

    def handle_ticket(self, user_id: str, message: str):
        """处理工单"""

        # 搜索相关问题历史
        history = self.client.search_memories(
            user_id=user_id,
            query=message,
            limit=5
        )

        # 检查是否有类似问题
        if history and history[0].score > 0.9:
            # 高相似度，可能是重复问题
            return f"我看到您之前问过类似问题：{history[0].content}"

        # 保存新问题
        self.client.add_memory(
            user_id=user_id,
            content=f"用户问题：{message}",
            metadata={
                "type": "ticket",
                "timestamp": datetime.now().isoformat(),
                "resolved": False
            }
        )

        return "您的问题已记录，我们会尽快处理。"

    def resolve_ticket(self, user_id: str, solution: str):
        """记录解决方案"""

        self.client.add_memory(
            user_id=user_id,
            content=f"解决方案：{solution}",
            metadata={"type": "solution", "resolved": True}
        )
```

## 异步支持

SDK 提供完整的异步 API：

```python
import asyncio
from timem import AsyncTiMemClient

async def main():
    client = AsyncTiMemClient(api_key="your-api-key")

    # 异步添加记忆
    memory = await client.add_memory(
        user_id="user_123",
        content="用户喜欢吃素食"
    )

    # 异步搜索
    results = await client.search_memories(
        user_id="user_123",
        query="饮食偏好"
    )

    # 批量异步操作
    tasks = [
        client.add_memory(user_id="user_123", content=f"记忆{i}")
        for i in range(10)
    ]
    memories = await asyncio.gather(*tasks)

    print(f"批量添加了 {len(memories)} 条记忆")

asyncio.run(main())
```

## 错误处理

```python
from timem import TiMemClient
from timem.exceptions import (
    TiMemAPIError,
    AuthenticationError,
    RateLimitError,
    NotFoundError,
    ValidationError
)

client = TiMemClient(api_key="your-api-key")

try:
    memory = client.add_memory(
        user_id="user_123",
        content="测试内容"
    )

except AuthenticationError:
    print("API Key 无效或已过期")

except RateLimitError as e:
    print(f"请求过于频繁，请 {e.retry_after} 秒后重试")

except NotFoundError:
    print("资源不存在")

except ValidationError as e:
    print(f"参数验证失败: {e.errors}")

except TiMemAPIError as e:
    print(f"API 错误: {e.message} (代码: {e.code})")

except Exception as e:
    print(f"未知错误: {e}")
```

## 高级功能

### 自定义记忆层级

```python
# 生成特定层级的记忆
client.add_memory(
    user_id="user_123",
    content="用户喜欢素食",
    level="L2",  # 直接指定层级
    metadata={"type": "preference"}
)

# 获取特定层级的记忆
memories = client.search_memories(
    user_id="user_123",
    query="偏好",
    level="L2"  # 只搜索 L2 记忆
)
```

### 批量操作

```python
# 批量添加记忆
memories_data = [
    {"content": "记忆1", "metadata": {"index": 1}},
    {"content": "记忆2", "metadata": {"index": 2}},
    {"content": "记忆3", "metadata": {"index": 3}},
]

memories = client.add_memories_batch(
    user_id="user_123",
    memories=memories_data
)

print(f"批量添加了 {len(memories)} 条记忆")
```

### 元数据过滤

```python
# 添加带元数据的记忆
client.add_memory(
    user_id="user_123",
    content="用户购买了高级套餐",
    metadata={
        "type": "purchase",
        "plan": "premium",
        "amount": 99.99
    }
)

# 搜索时过滤元数据
results = client.search_memories(
    user_id="user_123",
    query="购买记录",
    metadata_filter={
        "type": "purchase",
        "plan": "premium"
    }
)
```

## 测试与调试

### 使用测试密钥

```python
import os

# 开发环境使用测试密钥
if os.environ.get("ENVIRONMENT") == "development":
    api_key = os.environ.get("TIMEM_TEST_API_KEY")
else:
    api_key = os.environ.get("TIMEM_API_KEY")

client = TiMemClient(api_key=api_key)
```

### 启用日志

```python
import logging

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# SDK 会输出详细日志
client = TiMemClient(
    api_key="your-api-key",
    enable_logging=True
)
```

### 模拟响应（测试）

```python
from unittest.mock import Mock, patch

# 测试时不调用真实 API
with patch('timem.client.TiMemClient.add_memory') as mock_add:
    mock_add.return_value = Mock(id="test_mem_123")

    client = TiMemClient(api_key="test-key")
    memory = client.add_memory(user_id="test", content="test")

    print(memory.id)  # test_mem_123
```

## 性能优化

### 连接池

```python
from timem import TiMemClient

# SDK 自动管理连接池
client = TiMemClient(
    api_key="your-api-key",
    max_connections=100,      # 最大连接数
    max_keepalive_connections=20  # 保持活跃的连接
)
```

### 批量处理

```python
# 使用批量操作减少网络往返
memories = [f"记忆{i}" for i in range(100)]

# ✅ 好：批量添加
client.add_memories_batch(
    user_id="user_123",
    memories=[{"content": m} for m in memories]
)

# ❌ 差：逐条添加
for memory in memories:
    client.add_memory(user_id="user_123", content=memory)
```

## 配置管理

### 配置文件

```python
# config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    TIMEM_API_KEY = os.environ.get("TIMEM_API_KEY")
    TIMEM_API_URL = os.environ.get("TIMEM_API_URL", "https://api.timem.ai/v1")
    TIMEM_TIMEOUT = int(os.environ.get("TIMEM_TIMEOUT", "30"))
    TIMEM_MAX_RETRIES = int(os.environ.get("TIMEM_MAX_RETRIES", "3"))

# 使用
from timem import TiMemClient
from config import Config

client = TiMemClient(
    api_key=Config.TIMEM_API_KEY,
    base_url=Config.TIMEM_API_URL,
    timeout=Config.TIMEM_TIMEOUT,
    max_retries=Config.TIMEM_MAX_RETRIES
)
```

## 下一步

- [配置说明](configuration.md) - 详细配置选项
- [高级用法](advanced-usage.md) - 高级功能和技巧
- [API 参考](../../api-reference/overview.md) - 完整 API 文档
- [完整示例](../../examples/ai-assistant.md) - AI 助手完整实现

## 获取帮助

- **文档**: [https://docs.timem.ai](https://docs.timem.ai)
- **GitHub Issues**: [报告问题](https://github.com/your-org/timem/issues)
- **邮件支持**: support@timem.ai
