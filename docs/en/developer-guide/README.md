# TiMem Developer Quick Start

Welcome to TiMem development! This guide will help you set up your development environment in 30 minutes and understand TiMem's core architecture.

## 🎯 Quick Navigation

- [Development Environment Setup](#development-environment-setup)
- [Project Structure](#project-structure)
- [Core Concepts](#core-concepts)
- [First Program](#first-program)
- [Core APIs](#core-apis)
- [Testing Guide](#testing-guide)
- [Debugging Tips](#debugging-tips)

---

## 🛠️ Development Environment Setup

### Prerequisites

- **Python**: 3.9+
- **Git**: 2.20+
- **Docker**: 20.10+ (for databases)
- **IDE**: Recommended VS Code + Python extension

### 1. Clone Repository

```bash
git clone https://github.com/anomalyco/timem.git
cd timem
```

### 2. Create Virtual Environment

```bash
# Using venv
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate  # Windows

# Or using conda
conda create -n timem python=3.11
conda activate timem
```

### 3. Install Dependencies

```bash
# Install development dependencies
pip install -e ".[dev]"

# Or manually install
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 4. Start Databases

```bash
# Start all dependency services using Docker
docker-compose -f migration/docker-compose.yml up -d

# Verify services
docker-compose -f migration/docker-compose.yml ps
```

### 5. Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit configuration (at least configure database connection)
vim .env
```

**Minimum Configuration Example**:
```bash
# Database
DATABASE_URL=postgresql://timem:password@localhost:5432/timem

# Redis
REDIS_URL=redis://localhost:6379/0

# Qdrant
QDRANT_URL=http://localhost:6333

# LLM (configure at least one)
OPENAI_API_KEY=your_openai_key
```

### 6. Initialize Database

```bash
# Run migrations
alembic upgrade head

# Or use initialization script
python scripts/init_db.py
```

### 7. Verify Installation

```bash
# Run tests
pytest tests/ -v

# Start development server
python -m timem.api.main
```

---

## 📁 Project Structure

```
timem/
├── 📁 timem/                    # Core code
│   ├── 📁 core/                 # Core logic
│   │   ├── 📄 catchup_detector.py   # Backfill detector
│   │   ├── 📄 memory_tree.py        # Memory tree implementation
│   │   └── 📄 prompt_engine.py     # Prompt engine
│   ├── 📁 memory/                # Memory management
│   │   ├── 📄 base_memory.py        # Memory base class
│   │   ├── 📄 fragment.py           # L1 fragment memory
│   │   ├── 📄 session.py            # L2 session memory
│   │   ├── 📄 daily.py              # L3 daily report memory
│   │   ├── 📄 weekly.py             # L4 weekly report memory
│   │   └── 📄 profile.py            # L5 user profile
│   ├── 📁 workflows/             # Workflow engine
│   │   └── 📄 backfill_workflow.py  # Backfill workflow
│   └── 📁 utils/                 # Utility modules
│       ├── 📄 expert_helper.py      # Expert utilities
│       └── 📄 date_utils.py         # Date utilities
├── 📁 services/                   # Service layer
│   ├── 📄 scheduled_backfill_service.py  # Scheduled backfill service
│   └── 📄 memory_generation_service.py    # Memory generation service
├── 📁 storage/                   # Storage layer
│   ├── 📄 memory_storage_manager.py       # Memory storage manager
│   └── 📄 vector_store.py               # Vector storage
├── 📁 tests/                     # Test code
│   ├── 📁 unit/                 # Unit tests
│   ├── 📁 integration/          # Integration tests
│   └── 📁 e2e/                  # End-to-end tests
├── 📁 docs/                      # Documentation
├── 📁 config/                    # Configuration files
├── 📁 migration/                  # Database migrations
└── 📁 scripts/                   # Utility scripts
```

---

## 🧠 Core Concepts

### 1. Temporal Memory Tree (TMT)

The core of TiMem is a 5-level memory hierarchy:

```
L5: Profile (User Profile)
  ↑ Abstracted from L4
L4: Weekly (Weekly Report Memory)
  ↑ Aggregated from L3
L3: Daily (Daily Report Memory)
  ↑ Summarized from L2
L2: Session (Session Memory)
  ↑ Extracted from L1
L1: Fragment (Fragment Memory)
  ↑ Raw conversation fragments
```

### 2. Backfill Mechanism

Memories are automatically backfilled in chronological order:

```python
# Automatic backfill process
async def backfill_flow(user_id: str, expert_id: str):
    # 1. Detect missing L2 memories
    l2_tasks = await detector.detect_missing_l2_sessions(...)

    # 2. Generate L2 memories
    l2_memories = await generate_l2_memories(l2_tasks)

    # 3. Detect missing L3 memories
    l3_tasks = await detector.detect_missing_l3_reports(...)

    # 4. Generate L3 memories
    l3_memories = await generate_l3_memories(l3_tasks)

    # ... Continue to L4, L5
```

### 3. expert_id Concept

expert_id represents the other party in the conversation:

```python
# Single expert scenario
user_id="user_001"      # End user
expert_id="assistant"   # AI assistant

# Multi expert scenario
user_id="user_001"
expert_id="teacher_ai"     # Language teacher
expert_id="math_teacher"  # Math teacher
expert_id="doctor_ai"     # Medical consultant

# New feature: backfill all experts
user_id="user_001"
expert_id=None  # None means all experts
```

---

## 🚀 First Program

Let's create a simple memory management program:

```python
import asyncio
from datetime import datetime, date
from timem import AsyncMemory
from timem.core.catchup_detector import CatchUpDetector
from services.scheduled_backfill_service import get_scheduled_backfill_service

async def my_first_timem_app():
    """My first TiMem application"""
    print("🚀 Starting TiMem application...")

    # 1. Add conversation memory
    memory = AsyncMemory(
        api_key="your-api-key",
        base_url="http://localhost:8000"
    )

    # Add conversation
    result = await memory.add(
        messages=[
            {"role": "user", "content": "I want to learn Python"},
            {"role": "assistant", "content": "Great, I'll teach you!"}
        ],
        user_id="user_001",
        expert_id="teacher_ai",
        session_id="session_001"
    )

    print(f"✅ Memory added: {result['success']}")

    # 2. Search related memories
    results = await memory.search(
        query="learn Python",
        user_id="user_001",
        limit=5
    )

    print(f"🔍 Found {results.get('total', 0)} related memories")

    # 3. Manually trigger L2-L5 backfill
    backfill_service = get_scheduled_backfill_service()

    result = await backfill_service.backfill_for_user(
        user_id="user_001",
        expert_id=None,  # Backfill all experts
        layers=["L2", "L3", "L4", "L5"]
    )

    print(f"📊 Backfill completed: {result['completed']}/{result['total_tasks']} tasks")

    await memory.aclose()

if __name__ == "__main__":
    asyncio.run(my_first_timem_app())
```

Run the program:

```bash
python examples/my_first_app.py
```

---

## 🔧 Core APIs

### 1. Memory Storage API

#### Add Memory

```python
from timem import AsyncMemory

memory = AsyncMemory(...)

# Add L1 fragment memory
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

#### Search Memory

```python
# Simple search
results = await memory.search(
    query="user preferences",
    user_id="user_001",
    limit=10
)

# Complex search
results = await memory.search(
    query="tech preferences",
    user_id="user_001",
    expert_id="assistant",  # Specify expert
    level="L5",  # Specify memory level
    time_range={
        "start": "2026-01-01",
        "end": "2026-01-31"
    },
    limit=20
)
```

### 2. Backfill API

#### Manual Backfill

```python
from services.scheduled_backfill_service import get_scheduled_backfill_service

service = get_scheduled_backfill_service()

# Backfill all experts
result = await service.backfill_for_user(
    user_id="user_001",
    expert_id=None,  # All experts
    layers=["L2", "L3", "L4", "L5"]
)

# Backfill specific expert
result = await service.backfill_for_user(
    user_id="user_001",
    expert_id="teacher_ai",
    layers=["L2", "L3"]
)

# Force update mode
from timem.core.catchup_detector import CatchUpDetector

detector = CatchUpDetector()
tasks = await detector.detect_manual_completion(
    user_id="user_001",
    expert_id="teacher_ai",
    force_update=True,
    manual_timestamp=datetime.now()
)
```

#### Scheduled Backfill Configuration

```python
# Configure in config/settings.yaml
memory_generation:
  scheduled_backfill:
    enabled: true
    schedule: "0 2 * * *"  # Daily at 2 AM
    batch_size: 10
    parallel_tasks: 3
```

### 3. Storage Management API

```python
from storage.memory_storage_manager import get_memory_storage_manager_async

manager = await get_memory_storage_manager_async()

# Get all L1 memories for a user
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

# Get L2 memories for specific expert
l2_memories = await manager.search_memories(
    query={
        "user_id": "user_001",
        "expert_id": "teacher_ai",
        "level": "L2"
    },
    options={"limit": 50}
)

# Get memories by date range
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

## 🧪 Testing Guide

### Run Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/unit/test_catchup_detector.py -v

# Run tests with coverage
pytest --cov=timem --cov-report=html

# Run tests in parallel
pytest -n 4
```

### Write Tests

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
        """Test L2 session detection"""
        # Mock data
        user_id = "test_user"
        expert_id = "test_expert"

        # Execute test
        sessions = await detector._detect_missing_l2_sessions(
            user_id=user_id,
            expert_id=expert_id,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31)
        )

        # Assertions
        assert isinstance(sessions, list)
        # ... more assertions

    @pytest.mark.asyncio
    async def test_force_update_mode(self, detector):
        """Test force_update mode"""
        tasks = await detector.detect_manual_completion(
            user_id="test_user",
            expert_id="test_expert",
            force_update=True,
            manual_timestamp=datetime.now()
        )

        assert len(tasks) > 0
        assert all(task.force_update for task in tasks)
```

### Integration Tests

```python
import pytest
from services.scheduled_backfill_service import get_scheduled_backfill_service

@pytest.mark.integration
@pytest.mark.asyncio
async def test_complete_backfill_flow():
    """Test complete backfill flow"""
    user_id = "integration_test_user"
    expert_id = "test_expert"

    service = get_scheduled_backfill_service()

    # Execute backfill
    result = await service.backfill_for_user(
        user_id=user_id,
        expert_id=expert_id,
        layers=["L2", "L3"]
    )

    # Verify results
    assert result['completed'] > 0
    assert result['total_tasks'] > 0
```

---

## 🐛 Debugging Tips

### 1. Log Configuration

```python
# Enable verbose logging in code
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Enable TiMem-specific logging
logging.getLogger('timem').setLevel(logging.DEBUG)
logging.getLogger('catchup_detector').setLevel(logging.DEBUG)
```

### 2. Use Debugger

```python
import pdb

async def my_function():
    # Set breakpoint
    pdb.set_trace()

    # Or use ipdb (recommended)
    import ipdb; ipdb.set_trace()
```

### 3. Test Data Inspection

```python
# Check memories in database
from storage.memory_storage_manager import get_memory_storage_manager_async

manager = await get_memory_storage_manager_async()

# Get all memory levels
for level in ["L1", "L2", "L3", "L4", "L5"]:
    memories = await manager.search_memories(
        query={
            "user_id": "test_user",
            "level": level
        }
    )
    print(f"{level}: {len(memories)} memories")

    # Print first memory details
    if memories:
        print(f"  Example: {memories[0]}")
```

### 4. Performance Profiling

```python
import time
import asyncio

async def timed_function(func, *args, **kwargs):
    """Measure function execution time"""
    start = time.time()
    result = await func(*args, **kwargs)
    end = time.time()
    print(f"{func.__name__} took: {end - start:.2f} seconds")
    return result

# Usage example
result = await timed_function(
    detector.detect_manual_completion,
    user_id="user_001",
    expert_id="assistant"
)
```

---

## 📚 Learning Resources

### Core Documentation

- **TMT Architecture**: [timem/README.md](../../timem/README.md)
- **Memory Hierarchy**: [timem/memory/README.md](../../timem/memory/README.md)
- **Workflow Engine**: [timem/workflows/README.md](../../timem/workflows/README.md)
- **API Reference**: [../api-reference/overview.md](../api-reference/overview.md)

### Test Reports

- **L3-L5 Fix**: [../../L3L5_BACKFIX_FIX_REPORT.md](../../L3L5_BACKFIX_FIX_REPORT.md)
- **expert_id Changes**: [../../EXPERT_ID_OPTIONAL_CHANGES.md](../../EXPERT_ID_OPTIONAL_CHANGES.md)

### Practice Projects

- **Backfill Feature**: [BACKFILL_GUIDE.md](../../BACKFILL_GUIDE.md)
- **Example Code**: [../../cloud-service/examples/](../../cloud-service/examples/)

---

## 🤝 Contributing Code

### Development Workflow

1. Fork repository
2. Create feature branch: `git checkout -b feature/your-feature`
3. Write tests
4. Ensure tests pass: `pytest`
5. Commit code: `git commit -m "feat: your feature"`
6. Push branch: `git push origin feature/your-feature`
7. Create Pull Request

### Code Standards

- Follow PEP 8
- Use Black formatting: `black .`
- Use isort for import sorting: `isort .`
- Type hints: Use `typing` module
- Docstrings: Use Google style

### Commit Convention

```
<type>(<scope>): <subject>

<body>

<footer>
```

Example:
```
feat(core): Add expert_id optional parameter support

Implement expert_id parameter optional functionality, support backfill for all experts
- Modify backfill_for_user method signature
- Add get_all_experts_for_user utility function
- Complete test cases

Closes #123
```

---

**Maintainer**: TiMem Team
**Last Updated**: 2026-02-08
**Version**: v1.0.0
