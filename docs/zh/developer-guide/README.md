# TiMem 开发者快速入门

欢迎来到 TiMem 开发！本指南将帮助你在 30 分钟内搭建开发环境，并了解 TiMem 的核心架构。

## 🎯 快速导航

- [开发环境搭建](#开发环境搭建)
- [项目结构](#项目结构)
- [核心概念](#核心概念)
- [第一个程序](#第一个程序)
- [核心API](#核心api)
- [测试指南](#测试指南)
- [调试技巧](#调试技巧)

---

## 🛠️ 开发环境搭建

### 前置要求

- **Python**: 3.9+
- **Git**: 2.20+
- **Docker**: 20.10+ (用于数据库)
- **IDE**: 推荐使用 VS Code + Python 插件

### 1. 克隆仓库

```bash
git clone https://github.com/anomalyco/timem.git
cd timem
```

### 2. 创建虚拟环境

```bash
# 使用 venv
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate  # Windows

# 或使用 conda
conda create -n timem python=3.11
conda activate timem
```

### 3. 安装依赖

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 或手动安装
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 4. 启动数据库

```bash
# 使用 Docker 启动所有依赖服务
docker-compose -f migration/docker-compose.yml up -d

# 验证服务
docker-compose -f migration/docker-compose.yml ps
```

### 5. 配置环境

```bash
# 复制环境模板
cp .env.example .env

# 编辑配置 (至少配置数据库连接)
vim .env
```

**最小配置示例**:
```bash
# 数据库
DATABASE_URL=postgresql://timem:password@localhost:5432/timem

# Redis
REDIS_URL=redis://localhost:6379/0

# Qdrant
QDRANT_URL=http://localhost:6333

# LLM (至少配置一个)
OPENAI_API_KEY=your_openai_key
```

### 6. 初始化数据库

```bash
# 运行迁移
alembic upgrade head

# 或使用初始化脚本
python scripts/init_db.py
```

### 7. 验证安装

```bash
# 运行测试
pytest tests/ -v

# 启动开发服务器
python -m timem.api.main
```

---

## 📁 项目结构

```
timem/
├── 📁 timem/                    # 核心代码
│   ├── 📁 core/                 # 核心逻辑
│   │   ├── 📄 catchup_detector.py   # 回填检测器
│   │   ├── 📄 memory_tree.py        # 记忆树实现
│   │   └── 📄 prompt_engine.py     # 提示词引擎
│   ├── 📁 memory/                # 记忆管理
│   │   ├── 📄 base_memory.py        # 记忆基类
│   │   ├── 📄 fragment.py           # L1 片段记忆
│   │   ├── 📄 session.py            # L2 会话记忆
│   │   ├── 📄 daily.py              # L3 日报记忆
│   │   ├── 📄 weekly.py             # L4 周报记忆
│   │   └── 📄 profile.py            # L5 用户画像
│   ├── 📁 workflows/             # 工作流引擎
│   │   └── 📄 backfill_workflow.py  # 回填工作流
│   └── 📁 utils/                 # 工具模块
│       ├── 📄 expert_helper.py      # Expert 工具
│       └── 📄 date_utils.py         # 日期工具
├── 📁 services/                   # 服务层
│   ├── 📄 scheduled_backfill_service.py  # 定时回填服务
│   └── 📄 memory_generation_service.py    # 记忆生成服务
├── 📁 storage/                   # 存储层
│   ├── 📄 memory_storage_manager.py       # 记忆存储管理
│   └── 📄 vector_store.py               # 向量存储
├── 📁 tests/                     # 测试代码
│   ├── 📁 unit/                 # 单元测试
│   ├── 📁 integration/          # 集成测试
│   └── 📁 e2e/                  # 端到端测试
├── 📁 docs/                      # 文档
├── 📁 config/                    # 配置文件
├── 📁 migration/                  # 数据库迁移
└── 📁 scripts/                   # 辅助脚本
```

---

## 🧠 核心概念

### 1. Temporal Memory Tree (TMT)

TiMem 的核心是 5 级记忆层次：

```
L5: Profile (用户画像)
  ↑ 从 L4 抽象而来
L4: Weekly (周报记忆)
  ↑ 从 L3 聚合而来
L3: Daily (日报记忆)
  ↑ 从 L2 总结而来
L2: Session (会话记忆)
  ↑ 从 L1 片段提取而来
L1: Fragment (片段记忆)
  ↑ 原始对话片段
```

### 2. 回填机制

记忆会按时间顺序自动回填：

```python
# 自动回填流程
async def backfill_flow(user_id: str, expert_id: str):
    # 1. 检测缺失的 L2 记忆
    l2_tasks = await detector.detect_missing_l2_sessions(...)

    # 2. 生成 L2 记忆
    l2_memories = await generate_l2_memories(l2_tasks)

    # 3. 检测缺失的 L3 记忆
    l3_tasks = await detector.detect_missing_l3_reports(...)

    # 4. 生成 L3 记忆
    l3_memories = await generate_l3_memories(l3_tasks)

    # ... 继续到 L4, L5
```

### 3. expert_id 概念

expert_id 表示对话中的另一方：

```python
# 单 expert 场景
user_id="user_001"      # 终端用户
expert_id="assistant"   # AI 助手

# 多 expert 场景
user_id="user_001"
expert_id="teacher_ai"     # 语文老师
expert_id="math_teacher"  # 数学老师
expert_id="doctor_ai"     # 医疗顾问

# 新特性: 回填所有 expert
user_id="user_001"
expert_id=None  # None 表示所有 expert
```

---

## 🚀 第一个程序

让我们创建一个简单的记忆管理程序：

```python
import asyncio
from datetime import datetime, date
from timem import AsyncMemory
from timem.core.catchup_detector import CatchUpDetector
from services.scheduled_backfill_service import get_scheduled_backfill_service

async def my_first_timem_app():
    """我的第一个 TiMem 应用"""
    print("🚀 启动 TiMem 应用...")

    # 1. 添加对话记忆
    memory = AsyncMemory(
        api_key="your-api-key",
        base_url="http://localhost:8000"
    )

    # 添加对话
    result = await memory.add(
        messages=[
            {"role": "user", "content": "我想学习 Python"},
            {"role": "assistant", "content": "好的，我来教你！"}
        ],
        user_id="user_001",
        expert_id="teacher_ai",
        session_id="session_001"
    )

    print(f"✅ 添加记忆: {result['success']}")

    # 2. 搜索相关记忆
    results = await memory.search(
        query="学习 Python",
        user_id="user_001",
        limit=5
    )

    print(f"🔍 找到 {results.get('total', 0)} 条相关记忆")

    # 3. 手动触发 L2-L5 回填
    backfill_service = get_scheduled_backfill_service()

    result = await backfill_service.backfill_for_user(
        user_id="user_001",
        expert_id=None,  # 回填所有 expert
        layers=["L2", "L3", "L4", "L5"]
    )

    print(f"📊 回填完成: {result['completed']}/{result['total_tasks']} 任务")

    await memory.aclose()

if __name__ == "__main__":
    asyncio.run(my_first_timem_app())
```

运行程序：

```bash
python examples/my_first_app.py
```

---

## 🔧 核心 API

### 1. 记忆存储 API

#### 添加记忆

```python
from timem import AsyncMemory

memory = AsyncMemory(...)

# 添加 L1 片段记忆
result = await memory.add(
    messages=[
        {"role": "user", "content": "..."},
        {"role": "assistant", "content": "..."}
    ],
    user_id="user_001",
    expert_id="assistant",
    session_id="session_001"
)
```

#### 搜索记忆

```python
# 简单搜索
results = await memory.search(
    query="用户偏好",
    user_id="user_001",
    limit=10
)

# 复杂搜索
results = await memory.search(
    query="技术偏好",
    user_id="user_001",
    expert_id="assistant",  # 指定 expert
    level="L5",  # 指定记忆层级
    time_range={
        "start": "2026-01-01",
        "end": "2026-01-31"
    },
    limit=20
)
```

### 2. 回填 API

#### 手动回填

```python
from services.scheduled_backfill_service import get_scheduled_backfill_service

service = get_scheduled_backfill_service()

# 回填所有 expert
result = await service.backfill_for_user(
    user_id="user_001",
    expert_id=None,  # 所有 expert
    layers=["L2", "L3", "L4", "L5"]
)

# 回填指定 expert
result = await service.backfill_for_user(
    user_id="user_001",
    expert_id="teacher_ai",
    layers=["L2", "L3"]
)

# 强制更新模式
from timem.core.catchup_detector import CatchUpDetector

detector = CatchUpDetector()
tasks = await detector.detect_manual_completion(
    user_id="user_001",
    expert_id="teacher_ai",
    force_update=True,
    manual_timestamp=datetime.now()
)
```

#### 定时回填配置

```python
# 在 config/settings.yaml 中配置
memory_generation:
  scheduled_backfill:
    enabled: true
    schedule: "0 2 * * *"  # 每天凌晨2点
    batch_size: 10
    parallel_tasks: 3
```

### 3. 存储管理 API

```python
from storage.memory_storage_manager import get_memory_storage_manager_async

manager = await get_memory_storage_manager_async()

# 获取用户的所有 L1 记忆
l1_memories = await manager.search_memories(
    query={
        "user_id": "user_001",
        "level": "L1"
    },
    options={
        "limit": 100,
        "sort": {"created_at": "desc"}
    }
)

# 获取指定 expert 的 L2 记忆
l2_memories = await manager.search_memories(
    query={
        "user_id": "user_001",
        "expert_id": "teacher_ai",
        "level": "L2"
    },
    options={"limit": 50}
)

# 按日期范围获取记忆
from datetime import datetime, date

start_date = date(2026, 1, 1)
end_date = date(2026, 1, 31)

memories = await manager.search_memories(
    query={
        "user_id": "user_001",
        "time_window_start": {"$gte": start_date},
        "time_window_end": {"$lte": end_date}
    }
)
```

---

## 🧪 测试指南

### 运行测试

```bash
# 运行所有测试
pytest

# 运行特定测试文件
pytest tests/unit/test_catchup_detector.py -v

# 运行测试并显示覆盖率
pytest --cov=timem --cov-report=html

# 并行运行测试
pytest -n 4
```

### 编写测试

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from timem.core.catchup_detector import CatchUpDetector

class TestCatchUpDetector:
    @pytest.fixture
    async def detector(self):
        return CatchUpDetector()

    @pytest.mark.asyncio
    async def test_detect_missing_l2_sessions(self, detector):
        """测试 L2 会话检测"""
        # 模拟数据
        user_id = "test_user"
        expert_id = "test_expert"

        # 执行测试
        sessions = await detector._detect_missing_l2_sessions(
            user_id=user_id,
            expert_id=expert_id,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31)
        )

        # 断言
        assert isinstance(sessions, list)
        # ... 更多断言

    @pytest.mark.asyncio
    async def test_force_update_mode(self, detector):
        """测试 force_update 模式"""
        tasks = await detector.detect_manual_completion(
            user_id="test_user",
            expert_id="test_expert",
            force_update=True,
            manual_timestamp=datetime.now()
        )

        assert len(tasks) > 0
        assert all(task.force_update for task in tasks)
```

### 集成测试

```python
import pytest
from services.scheduled_backfill_service import get_scheduled_backfill_service

@pytest.mark.integration
@pytest.mark.asyncio
async def test_complete_backfill_flow():
    """测试完整的回填流程"""
    user_id = "integration_test_user"
    expert_id = "test_expert"

    service = get_scheduled_backfill_service()

    # 执行回填
    result = await service.backfill_for_user(
        user_id=user_id,
        expert_id=expert_id,
        layers=["L2", "L3"]
    )

    # 验证结果
    assert result['completed'] > 0
    assert result['total_tasks'] > 0
```

---

## 🐛 调试技巧

### 1. 日志配置

```python
# 在代码中启用详细日志
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# 启用 TiMem 特定日志
logging.getLogger('timem').setLevel(logging.DEBUG)
logging.getLogger('catchup_detector').setLevel(logging.DEBUG)
```

### 2. 使用调试器

```python
import pdb

async def my_function():
    # 设置断点
    pdb.set_trace()

    # 或者使用 ipdb (推荐)
    import ipdb; ipdb.set_trace()
```

### 3. 测试数据检查

```python
# 检查数据库中的记忆
from storage.memory_storage_manager import get_memory_storage_manager_async

manager = await get_memory_storage_manager_async()

# 获取所有记忆层级
for level in ["L1", "L2", "L3", "L4", "L5"]:
    memories = await manager.search_memories(
        query={
            "user_id": "test_user",
            "level": level
        }
    )
    print(f"{level}: {len(memories)} 条记忆")

    # 打印第一条记忆详情
    if memories:
        print(f"  示例: {memories[0]}")
```

### 4. 性能分析

```python
import time
import asyncio

async def timed_function(func, *args, **kwargs):
    """测量函数执行时间"""
    start = time.time()
    result = await func(*args, **kwargs)
    end = time.time()
    print(f"{func.__name__} 耗时: {end - start:.2f} 秒")
    return result

# 使用示例
result = await timed_function(
    detector.detect_manual_completion,
    user_id="user_001",
    expert_id="assistant"
)
```

---

## 📚 学习资源

### 核心文档

- **TMT 架构**: [timem/README.md](../../timem/README.md)
- **记忆层次**: [timem/memory/README.md](../../timem/memory/README.md)
- **工作流引擎**: [timem/workflows/README.md](../../timem/workflows/README.md)
- **API 参考**: [../api-reference/overview.md](../api-reference/overview.md)

### 测试报告

- **L3-L5 修复**: [../../L3L5_BACKFIX_FIX_REPORT.md](../../L3L5_BACKFIX_FIX_REPORT.md)
- **expert_id 变更**: [../../EXPERT_ID_OPTIONAL_CHANGES.md](../../EXPERT_ID_OPTIONAL_CHANGES.md)

### 实践项目

- **回填功能**: [BACKFILL_GUIDE.md](../../BACKFILL_GUIDE.md)
- **示例代码**: [../../cloud-service/examples/](../../cloud-service/examples/)

---

## 🤝 贡献代码

### 开发流程

1. Fork 仓库
2. 创建功能分支: `git checkout -b feature/your-feature`
3. 编写测试
4. 确保测试通过: `pytest`
5. 提交代码: `git commit -m "feat: your feature"`
6. 推送分支: `git push origin feature/your-feature`
7. 创建 Pull Request

### 代码规范

- 遵循 PEP 8
- 使用 Black 格式化: `black .`
- 使用 isort 排序导入: `isort .`
- 类型提示: 使用 `typing` 模块
- 文档字符串: 使用 Google 风格

### 提交规范

```
<type>(<scope>): <subject>

<body>

<footer>
```

示例:
```
feat(core): 添加 expert_id 可选参数支持

实现 expert_id 参数可选功能，支持回填所有 expert
- 修改 backfill_for_user 方法签名
- 添加 get_all_experts_for_user 工具函数
- 完善测试用例

Closes #123
```

---

**维护者**: TiMem Team
**最后更新**: 2026-01-26
**版本**: v1.0.0
