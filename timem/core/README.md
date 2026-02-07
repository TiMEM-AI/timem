# TiMem Core - Core Service Layer

## Overview

This module implements the core service layer of the TiMem system, providing session state management, memory detection, connection pool management and other fundamental functions.

## Core Components

1. **SessionStateManager** - Session state manager
2. **MemoryExistenceChecker** - Memory existence checker
3. **MissingMemoryDetector** - Missing memory detector
4. **UnifiedConnectionManager** - Unified connection manager
5. **GlobalConnectionPool** - Global connection pool
6. **ExecutionState** - Execution state management

## Main Features

### 1. SessionStateManager - Session State Manager

**Function**: Manages session active/inactive state based on finite state machine

**State Transitions**:
```
[New Session] → active
active + 10 minutes no interaction → inactive (triggers L2 backfill)
active + new session created → inactive (immediately triggers L2 backfill)
inactive + new interaction → active (resets timer)
```

**Usage Example**:

```python
from timem.core.session_state_manager import get_session_state_manager

# Get manager instance
manager = await get_session_state_manager()

# Track user interaction
session_info = await manager.track_interaction(
    session_id="session_001",
    user_id="user_001",
    expert_id="expert_001",
    timestamp=datetime.now()
)

# Check inactive sessions
inactive_sessions = await manager.check_inactive_sessions()

# Get sessions pending L2 generation
pending_sessions = await manager.get_pending_l2_sessions("user_001", "expert_001")

# Mark L2 as generated
await manager.mark_l2_generated("session_001", "memory_l2_001")
```

**Configuration**:
```yaml
memory_generation:
  session_state:
    inactive_timeout_minutes: 10
    check_interval_seconds: 60
    auto_trigger_l2: true
```

---

### 2. MemoryExistenceChecker - Memory Existence Checker

**Function**: Checks if memory exists within specified time window, supports strict deduplication

**Time Window Definitions**:
- **L2**: Entire session (session_id + session start/end time)
- **L3**: Natural day (00:00:00 - 23:59:59)
- **L4**: Natural week (Monday 00:00:00 - Sunday 23:59:59)
- **L5**: Natural month (1st 00:00:00 - last day 23:59:59)

**Usage Example**:

```python
from timem.core.memory_existence_checker import (
    get_memory_existence_checker,
    TimeWindow
)

# Get checker instance
checker = await get_memory_existence_checker()

# Create time window (L3 daily)
time_window = TimeWindow(
    start_time=datetime(2025, 10, 11, 0, 0, 0),
    end_time=datetime(2025, 10, 11, 23, 59, 59),
    layer="L3"
)

# Check if memory exists
result = await checker.check_memory_exists(
    user_id="user_001",
    expert_id="expert_001",
    layer="L3",
    time_window=time_window
)

# Check result
if not result.exists:
    print("Memory missing, needs backfill")
elif result.partial:
    print(f"Memory incomplete, needs update: {result.memory_id}")
elif result.complete:
    print(f"Memory exists completely: {result.memory_id}")
```

**Configuration**:
```yaml
memory_generation:
  deduplication:
    strict_mode: true
    completeness_threshold: 0.95
```

---

### 3. MissingMemoryDetector - Missing Memory Detector

**Function**: Scans historical timeline to detect missing L2-L5 memories

**Detection Logic**:
- **L2**: Based on sessions, detects sessions without L2
- **L3**: Based on natural days, detects dates with L2 but no L3
- **L4**: Based on natural weeks, detects weeks with L3 but no L4
- **L5**: Based on natural months, detects months with L4 but no L5

**Usage Example**:

```python
from timem.core.missing_memory_detector import get_missing_memory_detector

# Get detector instance
detector = await get_missing_memory_detector()

# Detect missing L2 memories
l2_tasks = await detector.detect_missing_l2("user_001", "expert_001")

# Detect missing L3 memories
l3_tasks = await detector.detect_missing_l3(
    user_id="user_001",
    expert_id="expert_001",
    start_date=datetime(2025, 10, 1),
    end_date=datetime(2025, 10, 31)
)

# Detect all missing levels
all_tasks = await detector.detect_all_missing(
    user_id="user_001",
    expert_id="expert_001",
    layers=["L2", "L3", "L4", "L5"]
)

# Process tasks
for layer, tasks in all_tasks.items():
    print(f"{layer} level: {len(tasks)} missing")
    for task in tasks:
        print(f"  - {task.reason}: {task.time_window.start_time}")
```

### 4. UnifiedConnectionManager - Unified Connection Manager

**Function**: Unified database connection management with connection pool and failover mechanism.

**Usage Example**:
```python
from timem.core.unified_connection_manager import get_connection_manager

# Get connection manager
manager = await get_connection_manager()

# Get database connection
connection = await manager.get_connection()

# Execute database operation
result = await connection.execute("SELECT * FROM memories")
```

### 5. GlobalConnectionPool - Global Connection Pool

**Function**: Manages global database connection pool for optimized connection reuse and performance.

**Usage Example**:
```python
from timem.core.global_connection_pool import get_global_pool_manager

# Get pool manager
pool_manager = get_global_pool_manager()

# Configure connection pool
await pool_manager.configure_pool(
    min_connections=5,
    max_connections=20,
    timeout=30
)
```

### 6. ExecutionState - Execution State Management

**Function**: Manages task execution state with concurrent control and state tracking.

**Usage Example**:
```python
from timem.core.execution_state import ExecutionState

# Create execution state
state = ExecutionState(task_id="task_001")

# Update execution status
await state.update_status("running")
await state.update_progress(50)

# Get execution status
status = await state.get_status()
```

## 🚀 Usage Examples

### Basic Usage

```python
from timem.core import (
    get_session_state_manager,
    get_memory_existence_checker,
    get_missing_memory_detector
)

# Get core services
session_manager = await get_session_state_manager()
existence_checker = await get_memory_existence_checker()
missing_detector = await get_missing_memory_detector()

# Track session state
await session_manager.track_interaction(
    session_id="session_001",
    user_id="user_001",
    expert_id="expert_001",
    timestamp=datetime.now()
)

# Check if memory exists
exists = await existence_checker.check_memory_exists(
    user_id="user_001",
    expert_id="expert_001",
    layer="L2",
    time_window=time_window
)

# Detect missing memories
missing_tasks = await missing_detector.detect_missing_l2(
    user_id="user_001",
    expert_id="expert_001"
)
```

## ⚙️ Configuration Guide

### Core Configuration

```yaml
core:
  session_state:
    inactive_timeout_minutes: 10
    check_interval_seconds: 60
    auto_trigger_l2: true
  memory_detection:
    strict_mode: true
    completeness_threshold: 0.95
  connection_pool:
    min_connections: 5
    max_connections: 20
    timeout: 30
```

## 🧪 Testing

### Unit Tests

```bash
# Test session state manager
pytest tests/unit/test_session_state_manager.py -v

# Test memory existence checker
pytest tests/unit/test_memory_existence_checker.py -v

# Test missing memory detector
pytest tests/unit/test_missing_memory_detector.py -v

# Test connection manager
pytest tests/unit/test_connection_manager.py -v
```

### Integration Tests

```bash
# Test core services integration
pytest tests/integration/test_core_services.py -v
```

## 📈 Performance Optimization

### Connection Pool Optimization

```python
# Configure connection pool parameters
await pool_manager.configure_pool(
    min_connections=10,
    max_connections=50,
    timeout=60,
    retry_count=3
)
```

### Cache Optimization

```python
# Enable session state caching
session_manager = await get_session_state_manager(
    enable_cache=True,
    cache_ttl=3600
)
```

## 🚨 Troubleshooting

### Common Issues

1. **Connection pool exhausted**
   - Check connection pool configuration
   - Increase max connections
   - Optimize connection usage

2. **Session state out of sync**
   - Check background task status
   - Verify configuration parameters
   - Review log information

3. **Memory detection inaccuracy**
   - Check time window configuration
   - Verify database indexes
   - Adjust detection parameters

### Debug Mode

```python
# Enable debug mode
session_manager = await get_session_state_manager(debug=True)
existence_checker = await get_memory_existence_checker(debug=True)
```

## 📚 Related Documentation

- [Memory Hierarchy Module](../memory/README.md)
- [Workflow Engine](../workflows/README.md)
- [Data Models](../models/README.md)
- [Utility Functions](../utils/README.md)
- [Business Services](../services/README.md)

