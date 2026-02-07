# TiMem Cloud SDK

云端服务模块，提供云端记忆存储和同步功能。

## 目录结构

```
cloud/
├── __init__.py              # 模块导出
└── async_memory.py          # 异步记忆客户端
```

## 核心组件说明

### async_memory.py - 异步记忆客户端

**职责**: 提供云端记忆存储和同步的异步 API

**主要功能**:
- 异步添加记忆
- 异步检索记忆
- 异步更新记忆
- 异步删除记忆

**使用示例**:

```python
from timem.cloud import AsyncMemory

# 创建异步记忆客户端
memory = AsyncMemory(api_key="your-api-key")

# 异步添加记忆
await memory.add(
    user_id="user123",
    expert_id="expert456",
    content="用户想学习Python"
)

# 异步检索记忆
results = await memory.search(
    user_id="user123",
    expert_id="expert456",
    query="用户的学习偏好"
)

# 异步更新记忆
await memory.update(
    memory_id="memory789",
    content="更新后的记忆内容"
)

# 异步删除记忆
await memory.delete(memory_id="memory789")
```

## 与本地模块的区别

| 特性 | Cloud SDK | 本地模块 |
|------|-----------|----------|
| 部署方式 | 云端服务 | 本地部署 |
| 数据存储 | 云端数据库 | 本地数据库 |
| 扩展性 | 自动扩展 | 需手动扩展 |
| 维护成本 | 低 | 高 |
| 延迟 | 网络延迟 | 低延迟 |

## 配置

### 环境变量

```bash
# API 密钥
TIMEM_API_KEY="your-api-key"

# 云端服务地址
TIMEM_API_URL="https://api.timem.ai"
```

### 直接初始化

```python
from timem.cloud import AsyncMemory

memory = AsyncMemory(
    api_key="your-api-key",
    host="https://api.timem.ai",
    timeout=30
)
```

## API 参考

### AsyncMemory

#### `add(user_id, expert_id, content, metadata=None)`
添加新记忆

#### `search(user_id, expert_id, query, limit=10)`
搜索记忆

#### `update(memory_id, content)`
更新记忆

#### `delete(memory_id)`
删除记忆

#### `list(user_id, expert_id, level=None, limit=100)`
列出记忆

## 最佳实践

1. **使用连接池**: 对于高并发场景，使用连接池管理请求
2. **错误处理**: 始终捕获和处理可能的异常
3. **批量操作**: 使用批量 API 减少网络开销
4. **缓存策略**: 对频繁访问的数据使用本地缓存

## 依赖

- httpx: 异步 HTTP 客户端
- pydantic: 数据验证

## 相关文档

- [主模块](../__init__.py)
- [本地记忆模块](../memory/README.md)
- [工作流引擎](../workflows/README.md)
