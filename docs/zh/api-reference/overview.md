# TiMem REST API 概述

TiMem REST API 提供了完整的记忆管理和检索功能，可以通过 HTTP 请求与 TiMem 服务进行交互。

## 基本信息

- **Base URL**: `https://api.timem.ai/v1`
- **认证方式**: Bearer Token (API Key)
- **数据格式**: JSON
- **字符编码**: UTF-8
- **API 版本**: v1.0

## 获取 API Key

### 步骤

1. 访问 [TiMem 云平台](https://cloud.timem.ai)
2. 注册/登录账号
3. 进入 **Settings** -> **API Keys**
4. 点击 **Create New Key**
5. 设置密钥名称和权限
6. 复制生成的密钥（只显示一次！）

### API Key 类型

| 类型 | 权限 | 用途 |
|------|------|------|
| **Production Key** | 完全权限 | 生产环境使用 |
| **Test Key** | 读取权限 | 测试和开发 |
| **Limited Key** | 自定义权限 | 特定功能限制 |

## API 端点总览

### 记忆管理

| 方法 | 端点 | 描述 |
|------|------|------|
| `POST` | `/memories` | 添加新记忆 |
| `GET` | `/memories` | 搜索记忆 |
| `GET` | `/memories/{id}` | 获取单个记忆 |
| `PUT` | `/memories/{id}` | 更新记忆 |
| `DELETE` | `/memories/{id}` | 删除记忆 |

### 会话管理

| 方法 | 端点 | 描述 |
|------|------|------|
| `POST` | `/sessions` | 创建会话 |
| `GET` | `/sessions/{id}` | 获取会话详情 |
| `GET` | `/sessions/{id}/memories` | 获取会话的所有记忆 |
| `DELETE` | `/sessions/{id}` | 删除会话 |

### 用户管理

| 方法 | 端点 | 描述 |
|------|------|------|
| `POST` | `/users` | 创建用户 |
| `GET` | `/users/{id}` | 获取用户信息 |
| `PUT` | `/users/{id}` | 更新用户信息 |
| `DELETE` | `/users/{id}` | 删除用户 |

### 批量操作

| 方法 | 端点 | 描述 |
|------|------|------|
| `POST` | `/memories/batch` | 批量添加记忆 |
| `POST` | `/conversations` | 从对话批量生成记忆 |

## 认证

所有 API 请求需要在 Header 中包含 API Key：

```http
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json
```

## 请求示例

### 使用 Python SDK（推荐）

```python
from timem import TiMemClient

client = TiMemClient(api_key="your-api-key")
memory = client.add_memory(
    user_id="user123",
    content="用户喜欢素食"
)
```

### 使用 cURL

```bash
curl -X POST https://api.timem.ai/v1/memories \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "content": "用户喜欢素食"
  }'
```

### 使用 JavaScript

```javascript
import { TiMemClient } from 'timem-sdk';

const client = new TiMemClient({
  apiKey: 'your-api-key'
});

const memory = await client.addMemory({
  userId: 'user123',
  content: '用户喜欢素食'
});
```

## 响应格式

### 成功响应

```json
{
  "success": true,
  "data": {
    "id": "mem_xxxxx",
    "user_id": "user123",
    "content": "用户喜欢素食",
    "level": "L1",
    "created_at": "2025-01-18T10:00:00Z"
  }
}
```

### 错误响应

```json
{
  "success": false,
  "error": {
    "code": "invalid_api_key",
    "message": "提供的 API Key 无效",
    "details": {}
  }
}
```

## HTTP 状态码

| 状态码 | 含义 | 说明 |
|--------|------|------|
| `200 OK` | 成功 | 请求成功 |
| `201 Created` | 创建成功 | 资源创建成功 |
| `400 Bad Request` | 请求错误 | 请求参数错误或缺失 |
| `401 Unauthorized` | 未授权 | API Key 无效或过期 |
| `403 Forbidden` | 禁止访问 | API Key 权限不足 |
| `404 Not Found` | 未找到 | 资源不存在 |
| `429 Too Many Requests` | 请求过多 | 超过速率限制 |
| `500 Internal Server Error` | 服务器错误 | 服务器内部错误 |

## 速率限制

### 免费计划
- **请求限制**: 100 请求/分钟
- **每日限制**: 10,000 请求/天

### Starter 计划 ($49/月)
- **请求限制**: 1,000 请求/分钟
- **每日限制**: 100,000 请求/天

### Professional 计划 ($199/月)
- **请求限制**: 10,000 请求/分钟
- **每日限制**: 1,000,000 请求/天

### Enterprise 计划
- **请求限制**: 无限制

### 速率限制响应

当超过限制时，API 返回 `429` 状态码：

```json
{
  "error": {
    "code": "rate_limit_exceeded",
    "message": "超过速率限制",
    "retry_after": 60
  }
}
```

响应头包含：
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1642579200
Retry-After: 60
```

## 核心概念

### 记忆层次（Memory Levels）

TiMem 将记忆组织为 5 个层次：

| 层级 | 名称 | 时间粒度 | 描述 |
|------|------|----------|------|
| L1 | Fragment | 实时 | 细粒度的对话证据 |
| L2 | Session | 会话 | 非冗余的事件摘要 |
| L3 | Day | 天 | 日常惯例和兴趣 |
| L4 | Week | 周 | 演化的行为模式 |
| L5 | Profile | 月 | 稳定的人格表示 |

### 用户与会话

- **User**: 使用 TiMem 的最终用户（如应用的终端用户）
- **Session**: 单次对话会话，属于某个用户
- **Memory**: 属于某个用户和会话的记忆片段

## 最佳实践

### 1. 错误处理

```python
from timem import TiMemClient
from timem.exceptions import TiMemAPIError, RateLimitError

client = TiMemClient(api_key="your-api-key")

try:
    memory = client.add_memory(user_id="user123", content="...")
except RateLimitError:
    print("请求过于频繁，请稍后重试")
except TiMemAPIError as e:
    print(f"API 错误: {e}")
```

### 2. 批量操作

对于大量数据，使用批量 API 提高效率：

```python
# 批量添加记忆
memories = [
    {"content": "记忆1"},
    {"content": "记忆2"},
    {"content": "记忆3"}
]

client.add_memories_batch(user_id="user123", memories=memories)
```

### 3. 异步请求

对于异步应用，使用异步 SDK：

```python
import asyncio
from timem import AsyncTiMemClient

async def main():
    client = AsyncTiMemClient(api_key="your-api-key")
    memory = await client.add_memory(
        user_id="user123",
        content="异步添加记忆"
    )

asyncio.run(main())
```

## SDK 与 API 对比

| 特性 | REST API | Python SDK |
|------|----------|------------|
| 易用性 | 需要手动处理 HTTP | 简单的方法调用 |
| 类型提示 | 无 | 有 |
| 错误处理 | 手动解析错误 | 自动异常 |
| 异步支持 | 需要自己实现 | 内置异步客户端 |
| 重试逻辑 | 需要自己实现 | 自动重试 |
| 推荐场景 | 非 Python 语言 | Python 应用 |

## 变更日志

### v1.0.0 (2025-01-18)

**新增**:
- 记忆管理 API
- 会话管理 API
- 用户管理 API
- 批量操作 API

**计划中**:
- Webhook 支持
- 更多过滤和排序选项
- 实时订阅

## 参考资源

- [认证指南](authentication.md) - API Key 管理和安全实践
- [Python SDK](../sdk/python/quickstart.md) - Python SDK 使用指南
- [云服务定价](../cloud-platform/pricing.md) - 计划和定价
- [故障排查](../troubleshooting.md) - 常见问题解决

## 支持

- **文档**: [https://docs.timem.ai](https://docs.timem.ai)
- **状态页面**: [https://status.timem.ai](https://status.timem.ai)
- **支持邮箱**: support@timem.ai
- **GitHub Issues**: [报告问题](https://github.com/your-org/timem/issues)
