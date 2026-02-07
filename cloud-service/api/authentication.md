# TiMem 云服务认证指南

TiMem 云服务使用**用户名/密码**认证方式，通过登录获取访问令牌（Token）。

## 目录

- [认证流程](#认证流程)
- [获取访问凭证](#获取访问凭证)
- [SDK 使用方式](#sdk-使用方式)
- [环境变量配置](#环境变量配置)
- [安全建议](#安全建议)
- [故障排查](#故障排查)

---

## 认证流程

TiMem 云服务采用 **JWT Token** 认证方式：

```
1. 用户名 + 密码 → 登录 → 获取 Token
2. Token → 携带在请求头 → 访问 API
3. Token 过期 → 重新登录 → 获取新 Token
```

### Token 有效期

- 默认有效期：8 天（691200 秒）
- 过期后需要重新登录获取新 Token

---

## 获取访问凭证

### 方式一：演示服务器（测试用）

| 项目 | 值 |
|------|------|
| **用户名** | `test` |
| **密码** | `test123` |
| **服务地址** | `https://api.timem.cloud` |

### 方式二：注册正式账号

1. 访问 [TiMem 云服务官网](https://www.ktechhub.com)
2. 注册账号
3. 登录后获取凭据

### 方式三：API 注册

```bash
# 注册新用户
curl -X POST https://api.timem.cloud/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "your_username",
    "password": "your_password"
  }'
```

---

## SDK 使用方式

### 初始化客户端

```python
from timem import AsyncMemory

# 方式一：直接传入凭据
memory = AsyncMemory(
    api_key="your_username",           # 用户名
    base_url="https://api.timem.cloud",
    username="your_username",          # 用户名
    password="your_password"           # 密码
)
```

SDK 会自动处理登录和 Token 管理：

1. 首次调用 API 时自动登录
2. 获取 Token 并缓存
3. Token 过期后自动重新登录

### 使用环境变量

```python
import os
from dotenv import load_dotenv
from timem import AsyncMemory

# 加载 .env 文件
load_dotenv()

# 读取环境变量
username = os.environ.get("TIMEM_USERNAME")
password = os.environ.get("TIMEM_PASSWORD")
base_url = os.environ.get("TIMEM_BASE_URL", "https://api.timem.cloud")

# 创建客户端
memory = AsyncMemory(
    api_key=username,
    base_url=base_url,
    username=username,
    password=password
)
```

---

## 环境变量配置

### 1. 创建 .env 文件

在项目根目录或 `examples/` 目录下创建 `.env` 文件：

```bash
# TiMem 云服务配置
TIMEM_USERNAME=your_username
TIMEM_PASSWORD=your_password
TIMEM_BASE_URL=https://api.timem.cloud

# 可选：LLM API Key（用于 AI 助手示例）
# ZHIPUAI_API_KEY=your_zhipuai_key
```

### 2. 添加到 .gitignore

```bash
# .gitignore
.env
.env.local
*.env
```

### 3. 环境变量说明

| 变量名 | 必填 | 默认值 | 说明 |
|--------|:----:|--------|------|
| `TIMEM_USERNAME` | ✅ | - | TiMem 云服务用户名 |
| `TIMEM_PASSWORD` | ✅ | - | TiMem 云服务密码 |
| `TIMEM_BASE_URL` | ❌ | `https://api.timem.cloud` | 云服务地址 |
| `ZHIPUAI_API_KEY` | ❌ | - | 智谱AI API Key（可选） |

---

## 安全建议

### 1. 保护凭据

```bash
# .gitignore
.env           # 添加到 .gitignore
.env.local
*.env
*.pem
```

### 2. 使用环境变量

```python
# 错误示例 - 硬编码凭据
memory = AsyncMemory(
    api_key="my_username",
    password="my_password"  # 危险！不要这样做
)

# 正确示例 - 使用环境变量
memory = AsyncMemory(
    api_key=os.environ.get("TIMEM_USERNAME"),
    password=os.environ.get("TIMEM_PASSWORD")
)
```

### 3. 区分环境

```bash
# .env.development
TIMEM_USERNAME=dev_user
TIMEM_PASSWORD=dev_password

# .env.production
TIMEM_USERNAME=prod_user
TIMEM_PASSWORD=prod_password
```

### 4. 定期更换密码

建议定期更换云服务密码，尤其是在发现安全问题时。

---

## 故障排查

### 401 Unauthorized

**错误响应：**
```json
{
  "code": 401,
  "message": "无效的访问令牌"
}
```

**原因：**
- Token 无效或过期
- 用户名或密码错误

**解决方案：**
```python
# 检查凭据
print(f"Username: {os.environ.get('TIMEM_USERNAME')}")
print(f"Password set: {bool(os.environ.get('TIMEM_PASSWORD'))}")

# 确保环境变量已加载
load_dotenv()
```

### 403 Forbidden

**错误响应：**
```json
{
  "code": 403,
  "message": "Not authenticated"
}
```

**原因：**
- 未提供认证信息
- Token 格式错误

**解决方案：**
```python
# 确保传入正确的参数
memory = AsyncMemory(
    api_key=username,
    username=username,
    password=password
)
```

### 429 Too Many Requests

**错误响应：**
```json
{
  "code": 429,
  "message": "Rate limit exceeded"
}
```

**原因：**
- 请求频率超过限制
- 每秒最多 10 个请求

**解决方案：**
```python
import asyncio

# 添加延迟
async def batch_operations():
    for item in items:
        await memory.add(...)
        await asyncio.sleep(0.2)  # 添加 200ms 延迟
```

### 连接失败

**错误响应：**
```
ConnectionError: Failed to establish connection
```

**原因：**
- 网络问题
- 服务地址错误
- 服务不可用

**解决方案：**
```python
# 检查服务是否可用
import httpx

try:
    response = httpx.get("https://api.timem.cloud/health")
    print(f"Service status: {response.json()}")
except Exception as e:
    print(f"Connection failed: {e}")
```

---

## 完整示例

```python
import asyncio
import os
from dotenv import load_dotenv
from timem import AsyncMemory

async def main():
    """主函数 - 演示完整的认证和使用流程"""

    # 1. 加载环境变量
    load_dotenv()

    # 2. 获取配置
    username = os.environ.get("TIMEM_USERNAME")
    password = os.environ.get("TIMEM_PASSWORD")
    base_url = os.environ.get("TIMEM_BASE_URL", "https://api.timem.cloud")

    # 3. 验证配置
    if not username or not password:
        print("Error: 请设置 TIMEM_USERNAME 和 TIMEM_PASSWORD 环境变量")
        print("\n创建 .env 文件：")
        print("  TIMEM_USERNAME=your_username")
        print("  TIMEM_PASSWORD=your_password")
        return

    # 4. 初始化客户端（会自动登录）
    print(f"连接 TiMem 云服务...")
    memory = AsyncMemory(
        api_key=username,
        base_url=base_url,
        username=username,
        password=password
    )
    print("  [OK] 连接成功！")

    # 5. 添加记忆
    print("\n添加对话记忆...")
    result = await memory.add(
        messages=[
            {"role": "user", "content": "你好，我叫张明"}
        ],
        user_id="user_001",
        character_id="assistant"
    )
    print(f"  [{'OK' if result['success'] else 'FAIL'}] 添加{'成功' if result['success'] else '失败'}")

    # 6. 搜索记忆
    print("\n搜索记忆...")
    results = await memory.search(
        query="用户的名字",
        user_id="user_001"
    )
    print(f"  [OK] 找到 {results.get('total', 0)} 条记忆")

    # 7. 关闭连接
    await memory.aclose()
    print("\n连接已关闭。")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 下一步

- 查看 [API 参考](reference.md) 了解完整 API
- 查看 [示例代码](../examples/) 学习完整用法：
  - [01_quick_start.py](../examples/01_quick_start.py) - 快速开始
  - [02_add_memory.py](../examples/02_add_memory.py) - 添加记忆
  - [03_search_memory.py](../examples/03_search_memory.py) - 搜索记忆
  - [04_chat_demo.py](../examples/04_chat_demo.py) - 完整聊天演示
