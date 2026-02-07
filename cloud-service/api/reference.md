# TiMem 云服务 API 参考

TiMem 云服务 REST API 参考文档。

## 目录

- [基础信息](#基础信息)
- [认证](#认证)
- [API 端点](#api-端点)
- [错误处理](#错误处理)
- [使用示例](#使用示例)

---

## 基础信息

| 项目 | 值 |
|------|------|
| **Base URL** | `https://api.timem.cloud` (演示服务器) |
| **协议** | HTTP |
| **数据格式** | JSON |
| **认证方式** | Bearer Token (用户名/密码登录获取) |

---

## 认证

云服务使用**用户名/密码登录**获取访问令牌。

### 1. 登录获取 Token

```http
POST /api/v1/auth/login
Content-Type: application/json
```

**请求体：**
```json
{
  "username": "your_username",
  "password": "your_password"
}
```

**响应：**
```json
{
  "code": 200,
  "message": "Success",
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "bearer",
    "expires_in": 691200,
    "user": {
      "user_id": "usr_xxx",
      "username": "your_username",
      "status": "active"
    }
  }
}
```

### 2. 使用 Token 访问 API

所有 API 调用需要在请求头中携带 Token：

```http
Authorization: Bearer your_access_token
```

---

## API 端点

### 1. 添加对话记忆

与 AI 助手进行对话并自动生成记忆。

```http
POST /api/v1/sessions/chat
Content-Type: application/json
Authorization: Bearer {token}
```

**请求体：**
```json
{
  "user_id": "user_001",
  "character_id": "assistant",
  "message": "你好，我叫张明，是一名软件工程师",
  "session_id": "session_001"
}
```

**参数说明：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `user_id` | string | ✅ | 用户唯一标识符 |
| `character_id` | string | ✅ | AI 角色/助手标识符 |
| `message` | string | ✅ | 用户消息内容 |
| `session_id` | string | ❌ | 会话 ID，用于分组管理 |

**响应：**
```json
{
  "code": 200,
  "message": "Success",
  "data": {
    "memory_count": 1,
    "memory_id": "mem_xxx",
    "memories": [
      {
        "id": "mem_xxx",
        "memory": "用户叫张明，是一名软件工程师",
        "created_at": "2024-01-19T10:00:00Z"
      }
    ]
  }
}
```

---

### 2. 搜索记忆

根据查询内容搜索相关记忆。

```http
POST /api/v1/memory/search
Content-Type: application/json
Authorization: Bearer {token}
```

**请求体：**
```json
{
  "user_id": "user_001",
  "query_text": "用户的职业",
  "limit": 10
}
```

**参数说明：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `user_id` | string | ✅ | 用户唯一标识符 |
| `query_text` | string | ✅ | 搜索查询文本 |
| `limit` | int | ❌ | 返回数量限制（默认 10） |

**响应：**
```json
{
  "code": 200,
  "message": "Success",
  "data": {
    "total": 5,
    "results": [
      {
        "id": "mem_xxx",
        "memory": "用户是一名软件工程师",
        "score": 0.92,
        "metadata": {
          "session_id": "session_001",
          "character_id": "assistant",
          "created_at": "2024-01-19T10:00:00Z"
        }
      }
    ]
  }
}
```

---

### 3. 获取用户信息

获取当前登录用户的信息。

```http
GET /api/v1/auth/me
Authorization: Bearer {token}
```

**响应：**
```json
{
  "code": 200,
  "message": "Success",
  "data": {
    "user_id": "usr_xxx",
    "username": "your_username",
    "email": "user@example.com",
    "display_name": "Your Name",
    "status": "active",
    "created_at": "2024-01-01T00:00:00Z"
  }
}
```

---

### 4. 注册新用户

注册一个新用户账号。

```http
POST /api/v1/auth/register
Content-Type: application/json
```

**请求体：**
```json
{
  "username": "new_user",
  "password": "password123"
}
```

**响应：**
```json
{
  "code": 200,
  "message": "Success",
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "bearer",
    "user": {
      "user_id": "usr_xxx",
      "username": "new_user"
    }
  }
}
```

---

## 错误处理

### 错误响应格式

```json
{
  "code": 401,
  "message": "无效的访问令牌",
  "data": null
}
```

### HTTP 状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 请求成功 |
| 400 | 请求参数错误 |
| 401 | 未授权（无效的 Token） |
| 403 | 禁止访问 |
| 404 | 资源不存在 |
| 422 | 数据验证错误 |
| 429 | 超过速率限制 |
| 500 | 服务器内部错误 |

### 常见错误码

| 错误码 | 说明 |
|--------|------|
| `MISSING_QUERY_TEXT` | 缺少查询文本参数 |
| `INVALID_TOKEN` | 无效的访问令牌 |
| `NOT_AUTHENTICATED` | 未认证 |

---

## 使用示例

### 使用 cURL

#### 1. 登录获取 Token

```bash
# 登录
TOKEN=$(curl -s -X POST https://api.timem.cloud/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"test","password":"test123"}' | \
  python -c "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")

echo "Token: $TOKEN"
```

#### 2. 添加对话记忆

```bash
curl -X POST https://api.timem.cloud/api/v1/sessions/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "user_id": "user_001",
    "character_id": "assistant",
    "message": "你好，我叫张明，是一名软件工程师"
  }'
```

#### 3. 搜索记忆

```bash
curl -X POST https://api.timem.cloud/api/v1/memory/search \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "user_id": "user_001",
    "query_text": "用户的职业",
    "limit": 5
  }'
```

### 使用 Python SDK

```python
import asyncio
import os
from timem import AsyncMemory

async def main():
    # 从环境变量读取配置
    username = os.environ.get("TIMEM_USERNAME", "test")
    password = os.environ.get("TIMEM_PASSWORD", "test123")
    base_url = os.environ.get("TIMEM_BASE_URL", "https://api.timem.cloud")

    # 初始化客户端
    memory = AsyncMemory(
        api_key=username,
        base_url=base_url,
        username=username,
        password=password
    )

    # 添加记忆
    result = await memory.add(
        messages=[
            {"role": "user", "content": "你好，我叫张明"}
        ],
        user_id="user_001",
        character_id="assistant"
    )
    print(f"添加记忆: {result}")

    # 搜索记忆
    results = await memory.search(
        query="用户的名字",
        user_id="user_001"
    )
    print(f"搜索结果: {results}")

    # 关闭连接
    await memory.aclose()

asyncio.run(main())
```

---

## SDK 方法映射

| SDK 方法 | API 端点 | 说明 |
|----------|----------|------|
| `memory.add()` | `POST /api/v1/sessions/chat` | 添加对话记忆 |
| `memory.search()` | `POST /api/v1/memory/search` | 搜索记忆 |
| `memory.aclose()` | - | 关闭连接 |

---

## 速率限制

- 每个用户每秒最多 10 个请求
- 超出限制返回 429 状态码
- 建议在批量操作时添加适当延迟

---

## 下一步

- 查看 [认证说明](authentication.md) 了解详细认证流程
- 查看 [示例代码](../examples/) 学习完整用法
