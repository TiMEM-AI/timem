# TiMem 云服务 SDK 使用指南

TiMem 云服务提供托管的记忆管理解决方案，无需部署基础设施即可快速集成。

## 目录

- [🚀 快速开始](#-快速开始)
- [🔑 获取访问凭证](#-获取访问凭证)
- [📦 安装 SDK](#-安装-sdk)
- [💻 基本使用](#-基本使用)
- [📖 API 参考](#-api-参考)
- [📂 示例代码](#-示例代码)
- [🆚 云服务 vs 自托管](#-云服务-vs-自托管)

---

## 🚀 快速开始

### 1. 获取访问凭证

访问 TiMem 云服务需要用户名和密码进行认证。

**方式一：通过演示服务器测试**
- 用户名：`test`
- 密码：`test123`
- 服务地址：`http://58.87.76.109:8000`

**方式二：获取正式账号**
请访问 [TiMem 云服务官网](https://www.ktechhub.com) 注册账号获取凭据。

### 2. 安装 SDK

```bash
# 从源码安装（开发版）
pip install -e .

# 或等待正式发布后使用
# pip install timem
```

### 3. 快速示例

```python
import asyncio
from timem import AsyncMemory

async def main():
    # 初始化客户端
    memory = AsyncMemory(
        api_key="your_username",
        base_url="http://58.87.76.109:8000",
        username="your_username",
        password="your_password"
    )

    # 添加对话记忆
    result = await memory.add(
        messages=[
            {"role": "user", "content": "你好，我叫张明"},
            {"role": "assistant", "content": "你好张明！"}
        ],
        user_id="user_001",
        character_id="assistant",
        session_id="session_001"
    )

    print(f"添加记忆: {'成功' if result['success'] else '失败'}")
    print(f"生成记忆数: {result.get('total', 0)}")

    # 搜索相关记忆
    results = await memory.search(
        query="用户的职业",
        user_id="user_001",
        limit=5
    )

    print(f"找到 {results.get('total', 0)} 条相关记忆")

    # 关闭连接
    await memory.aclose()

asyncio.run(main())
```

---

## 🔑 获取访问凭证

### 认证方式

TiMem 云服务使用**用户名/密码认证**方式：

1. 用户名：通过注册获得
2. 密码：通过注册获得
3. 首次登录后可以创建 API Key 供程序使用

### 使用环境变量（推荐）

创建 `.env` 文件：

```bash
# TiMem 云服务配置
TIMEM_USERNAME=your_username
TIMEM_PASSWORD=your_password
TIMEM_BASE_URL=http://58.87.76.109:8000
```

在代码中加载：

```python
from dotenv import load_dotenv
import os

load_dotenv()  # 加载 .env 文件

username = os.environ.get("TIMEM_USERNAME")
password = os.environ.get("TIMEM_PASSWORD")
base_url = os.environ.get("TIMEM_BASE_URL", "http://58.87.76.109:8000")
```

---

## 📦 安装 SDK

### 从源码安装

```bash
# 克隆仓库
git clone https://github.com/your-org/timem.git
cd timem

# 安装依赖
pip install -e .

# 或只安装云服务所需依赖
pip install httpx python-dotenv
```

### 依赖说明

| 包名 | 版本 | 说明 |
|------|------|------|
| `httpx` | >=0.24.0 | 异步 HTTP 客户端 |
| `python-dotenv` | >=1.0.0 | 环境变量加载（可选） |

---

## 💻 基本使用

### 初始化客户端

```python
from timem import AsyncMemory

# 方式一：直接传入凭据
memory = AsyncMemory(
    api_key="username",
    base_url="http://58.87.76.109:8000",
    username="username",
    password="password"
)

# 方式二：从环境变量读取
import os
from dotenv import load_dotenv

load_dotenv()

memory = AsyncMemory(
    api_key=os.environ.get("TIMEM_USERNAME"),
    base_url=os.environ.get("TIMEM_BASE_URL", "http://58.87.76.109:8000"),
    username=os.environ.get("TIMEM_USERNAME"),
    password=os.environ.get("TIMEM_PASSWORD")
)
```

### 添加记忆

```python
# 添加对话记忆
result = await memory.add(
    messages=[
        {"role": "user", "content": "我是一名软件工程师"},
        {"role": "assistant", "content": "软件工程师，很棒的职业！"}
    ],
    user_id="user_001",
    character_id="assistant",  # AI 角色 ID
    session_id="session_001"   # 会话 ID（可选）
)

# 检查结果
if result["success"]:
    print(f"成功添加 {result.get('total', 0)} 条记忆")
    for mem in result.get("memories", []):
        print(f"  - {mem.get('memory', '')[:50]}...")
```

### 搜索记忆

```python
# 语义搜索
results = await memory.search(
    query="用户的职业和技能",
    user_id="user_001",
    limit=10
)

if results["success"]:
    print(f"找到 {results.get('total', 0)} 条相关记忆：")
    for mem in results.get("results", []):
        score = mem.get("score", 0)
        content = mem.get("memory", "")
        print(f"  [{score:.2f}] {content[:60]}...")
```

### 关闭连接

```python
# 方式一：直接关闭
await memory.aclose()

# 方式二：使用上下文管理器
async with AsyncMemory(...) as memory:
    # 使用内存...
    pass  # 自动关闭
```

---

## 📖 API 参考

### AsyncMemory 类

#### 构造函数

```python
AsyncMemory(
    api_key: str,           # API Key 或用户名
    base_url: str = "https://api.timem.ai/v1",  # 基础 URL
    username: str = None,   # 用户名（用于登录认证）
    password: str = None    # 密码（用于登录认证）
)
```

#### add() - 添加记忆

```python
result = await memory.add(
    messages: List[Dict[str, str]],  # 对话消息列表
    user_id: str,                     # 用户 ID
    character_id: str,                # 角色 ID
    session_id: str = None,           # 会话 ID（可选）
    **kwargs                         # 其他参数
) -> Dict[str, Any]
```

**参数说明：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `messages` | List[Dict] | 是 | 对话消息列表，每条消息包含 `role` 和 `content` |
| `user_id` | str | 是 | 用户唯一标识 |
| `character_id` | str | 是 | AI 角色 ID |
| `session_id` | str | 否 | 会话 ID，用于分组管理 |

**返回结果：**

```python
{
    "success": True,
    "total": 1,
    "memory_id": "mem_xxx",
    "memories": [
        {
            "id": "mem_xxx",
            "memory": "生成的记忆内容",
            "score": 0.95,
            "created_at": "2024-01-01T00:00:00Z"
        }
    ]
}
```

#### search() - 搜索记忆

```python
results = await memory.search(
    query: str,              # 搜索查询
    user_id: str,            # 用户 ID
    limit: int = 10,         # 返回数量限制
    session_id: str = None,  # 会话 ID（可选）
    character_id: str = None,# 角色 ID（可选）
    **kwargs                 # 其他参数
) -> Dict[str, Any]
```

**返回结果：**

```python
{
    "success": True,
    "total": 5,
    "results": [
        {
            "id": "mem_xxx",
            "memory": "用户是一名软件工程师",
            "score": 0.92,
            "metadata": {...}
        }
    ]
}
```

#### close() / aclose() - 关闭连接

```python
await memory.aclose()   # 异步关闭（推荐）
await memory.close()    # 兼容方法
```

---

## 📂 示例代码

示例文件位于 [`examples/`](examples/) 目录：

| 文件 | 说明 | 状态 |
|------|------|:----:|
| [01_quick_start.py](examples/01_quick_start.py) | 快速开始示例 | ✅ |
| [02_add_memory.py](examples/02_add_memory.py) | 添加记忆示例 | ✅ |
| [03_search_memory.py](examples/03_search_memory.py) | 搜索记忆示例 | ✅ |
| [04_chat_demo.py](examples/04_chat_demo.py) | 完整聊天演示 | ✅ |

### 运行示例

```bash
cd cloud-service/examples

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件填入您的凭据

# 运行示例
python -X utf8 01_quick_start.py
```

### 配置示例 (.env)

```bash
# TiMem 云服务配置（必需）
TIMEM_USERNAME=test          # 用户名
TIMEM_PASSWORD=test123       # 密码
TIMEM_BASE_URL=http://58.87.76.109:8000

# 可选：LLM API Key（用于 AI 助手示例）
# ZHIPUAI_API_KEY=your_zhipuai_key
```

### ⚠️ 已知问题

1. **搜索端点服务器 bug**：演示服务器的 `/api/v1/memory/search` 端点有服务器端 bug（返回 500 错误），SDK 已通过使用 `/api/v1/sessions` 端点作为替代方案解决此问题
2. **部分数据查询可能返回空结果**：由于服务器端数据库配置问题，某些查询可能返回空结果

如遇到问题，请：
- 检查 `.env` 文件配置是否正确
- 确认用户名和密码是否有效
- 联系技术支持获取帮助

---

## 🆚 云服务 vs 自托管

| 特性 | 云服务 | 自托管 |
|:--------|:--------|:--------|
| **部署** | 无需部署 | 需要配置 |
| **维护** | 平台管理 | 自己维护 |
| **数据控制** | 云端存储 | 完全控制 |
| **定制化** | 有限定制 | 完全定制 |
| **成本** | 按量付费 | 固定成本 |

### 选择建议

**选择云服务**，如果：
- 希望快速集成
- 不想管理基础设施
- 需要自动扩容

**选择自托管**，如果：
- 数据必须本地存储
- 需要深度定制
- 有专业运维团队

---

## 📞 技术支持

- 官网：[https://www.ktechhub.com](https://www.ktechhub.com)
- 文档：[https://docs.timem.ai](https://docs.timem.ai)
- GitHub：[https://github.com/your-org/timem](https://github.com/your-org/timem)

---

## 📝 更新日志

**v1.0.0** (2026-01-19)
- 初始云服务版本
- 支持异步内存管理
- 支持语义搜索
- 支持对话记忆存储
