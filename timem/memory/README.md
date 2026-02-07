# TiMem Memory Hierarchy Module

This module implements the multi-level memory generation functionality of the TiMem system, supporting a five-level memory system from fragment-level to monthly-level.

## 🏗️ Architecture Design

### Memory Hierarchy System

```
L5 Monthly Memory (L5HighLevelMemory)
    ↑ Aggregation
L4 Weekly Memory (L4WeeklyMemory)  
    ↑ Aggregation
L3 Daily Memory (L3DailyMemory)
    ↑ Aggregation  
L2 Session Memory (L2SessionMemory)
    ↑ Aggregation
L1 Fragment Memory (L1FragmentMemory)
```

### Core Components

- **MemoryGenerator**: Unified memory generator coordinating all-level memory generation
- **L1FragmentMemory**: L1 fragment-level memory generator
- **L2SessionMemory**: L2 session-level memory generator  
- **L3DailyMemory**: L3 daily-level memory generator
- **L4WeeklyMemory**: L4 weekly-level memory generator
- **L5HighLevelMemory**: L5 monthly-level memory generator

## 📋 Level-by-Level Feature Explanation

### L1 Fragment-Level Memory (L1FragmentMemory)

**Function**: Handles fragment-level memory for single conversations, enabling real-time memory fragment updates.

**Features**:
- Fragment division: Every n conversation turns form a fragment
- Progressive fragment summarization: `M_{F_l} = Summarize(λ·F_l ⊕ (1-λ)·M_{F_{l-1}})`
- Supports incremental updates and real-time generation

**Usage Example**:
```python
from timem.memory.l1_fragment_memory import L1FragmentMemory

# Create L1 memory generator
l1_generator = L1FragmentMemory()

# Process dialogue fragment
fragment_memory = await l1_generator.process_fragment(
    session_id="session_001",
    user_id="user_001", 
    expert_id="expert_001",
    dialogues=[
        {"speaker": "user", "content": "I want to learn Python", "timestamp": "2025-01-01T10:00:00"},
        {"speaker": "expert", "content": "Python is a great programming language", "timestamp": "2025-01-01T10:01:00"}
    ]
)
```

### L2 Session-Level Memory (L2SessionMemory)

**Function**: Handles summary memory for complete sessions, aggregating all content from a single session.

**Features**:
- Overall session summary generation
- Key information extraction and structuring
- Support for session-level knowledge graph construction

**Usage Example**:
```python
from timem.memory.l2_session_memory import L2SessionMemory

# Create L2 memory generator
l2_generator = L2SessionMemory()

# Generate session memory
session_memory = await l2_generator.generate_session_memory(
    session_id="session_001",
    user_id="user_001",
    expert_id="expert_001", 
    session_dialogues=[...],
    l1_fragments=[...]
)
```

### L3 Daily-Level Memory (L3DailyMemory)

**Function**: Handles comprehensive memory for daily activities, aggregating all sessions within a single day.

**Features**:
- Daily activity pattern recognition
- Knowledge evolution trajectory analysis
- Learning progress tracking

**Usage Example**:
```python
from timem.memory.l3_daily_memory import L3DailyMemory

# Create L3 memory generator
l3_generator = L3DailyMemory()

# Generate daily memory
daily_memory = await l3_generator.generate_daily_memory(
    user_id="user_001",
    expert_id="expert_001",
    target_date=datetime(2025, 1, 1),
    session_memories=[...]
)
```

### L4 Weekly-Level Memory (L4WeeklyMemory)

**Function**: Handles summary memory for weekly activities, identifying long-term learning patterns.

**Features**:
- Weekly learning pattern analysis
- Knowledge system construction
- Learning effectiveness assessment

### L5 Monthly-Level Memory (L5HighLevelMemory)

**Function**: Handles high-level abstract memory for monthly activities, forming long-term knowledge graphs.

**Features**:
- Monthly knowledge system summary
- Learning path planning
- Basis for personalized recommendations

## 🔧 Unified Memory Generator (MemoryGenerator)

### Core Functions

```python
from timem.memory.memory_generator import MemoryGenerator

# Create memory generator
generator = MemoryGenerator(llm_provider="openai")

# Generate memory for specified level
memory = await generator.generate_memory(
    level="L2",
    user_id="user_001",
    expert_id="expert_001", 
    input_data={
        "session_id": "session_001",
        "dialogues": [...],
        "time_range": {...}
    }
)
```

### Batch Generation

```python
# Batch generate memories for multiple levels
memories = await generator.generate_multi_level_memories(
    user_id="user_001",
    expert_id="expert_001",
    levels=["L1", "L2", "L3"],
    input_data={...}
)
```

## 📊 Memory Data Structure

### Unified Memory Model

```python
from timem.models.memory import Memory, MemoryLevel

# Memory object structure
memory = Memory(
    id="memory_001",
    user_id="user_001", 
    expert_id="expert_001",
    level=MemoryLevel.L2,
    title="Python Learning Session Summary",
    content="User learned Python basic syntax...",
    time_window_start=datetime(2025, 1, 1, 10, 0, 0),
    time_window_end=datetime(2025, 1, 1, 11, 0, 0),
    child_memory_ids=["l1_001", "l1_002"],
    historical_memory_ids=["l1_003"]
)
```

### Hierarchy Relationships

- **child_memory_ids**: List of child memory IDs (subordinate memories)
- **historical_memory_ids**: List of historical memory IDs (same-level historical memories)
- **time_window**: Time window defining the time range covered by memory

## ⚙️ Configuration Guide

### Memory Generation Configuration

```yaml
memory_generation:
  l1:
    fragment_size: 5  # Number of conversation turns per fragment
    update_ratio: 0.7  # Progressive update ratio
  l2:
    session_timeout: 600  # Session timeout (seconds)
    min_dialogues: 3  # Minimum conversation turns
  l3:
    daily_aggregation: true  # Enable daily aggregation
    pattern_analysis: true  # Enable pattern analysis
```

### LLM Configuration

```yaml
llm:
  provider: "openai"  # LLM provider
  model: "gpt-4"  # Model name
  temperature: 0.7  # Generation temperature
  max_tokens: 2000  # Maximum tokens
```

## 🚀 Usage Workflow

### 1. Initialize Generator

```python
from timem.memory.memory_generator import MemoryGenerator

# Use default configuration
generator = MemoryGenerator()

# Specify LLM provider
generator = MemoryGenerator(llm_provider="zhipuai")
```

### 2. Generate Memory

```python
# Single-level generation
l2_memory = await generator.generate_memory(
    level="L2",
    user_id="user_001",
    expert_id="expert_001",
    input_data={
        "session_id": "session_001",
        "dialogues": session_dialogues,
        "time_range": {
            "start": "2025-01-01T10:00:00",
            "end": "2025-01-01T11:00:00"
        }
    }
)

# Multi-level batch generation
memories = await generator.generate_multi_level_memories(
    user_id="user_001",
    expert_id="expert_001", 
    levels=["L1", "L2", "L3"],
    input_data=generation_data
)
```

### 3. Handle Results

```python
# Check generation result
if memory.status == "success":
    print(f"Memory generated successfully: {memory.id}")
    print(f"Title: {memory.title}")
    print(f"Content: {memory.content}")
else:
    print(f"Memory generation failed: {memory.error}")
```

## 🔍 Advanced Features

### Memory Deduplication

```python
# Check if memory exists
exists = await generator.check_memory_exists(
    user_id="user_001",
    expert_id="expert_001",
    level="L2",
    time_window={
        "start": "2025-01-01T10:00:00",
        "end": "2025-01-01T11:00:00"
    }
)

if exists:
    print("Memory already exists, skip generation")
else:
    # Generate new memory
    memory = await generator.generate_memory(...)
```

### Incremental Update

```python
# Incrementally update existing memory
updated_memory = await generator.update_memory(
    memory_id="memory_001",
    new_data={
        "dialogues": additional_dialogues,
        "time_range": extended_range
    }
)
```

### Batch Processing

```python
# Batch generate memories for multiple users
batch_results = await generator.batch_generate_memories([
    {
        "user_id": "user_001",
        "expert_id": "expert_001", 
        "level": "L2",
        "input_data": {...}
    },
    {
        "user_id": "user_002",
        "expert_id": "expert_001",
        "level": "L2", 
        "input_data": {...}
    }
])
```

## 🧪 Testing

### Unit Tests

```bash
# Test L1 fragment memory
pytest tests/unit/test_l1_fragment_memory.py -v

# Test L2 session memory
pytest tests/unit/test_l2_session_memory.py -v

# Test memory generator
pytest tests/unit/test_memory_generator.py -v
```

### Integration Tests

```bash
# Test multi-level memory generation
pytest tests/integration/test_multi_level_memory.py -v

# Test memory deduplication
pytest tests/integration/test_memory_deduplication.py -v
```

## 📈 Performance Optimization

### Concurrent Processing

```python
# Concurrently generate memories for multiple levels
import asyncio

async def generate_all_levels():
    tasks = [
        generator.generate_memory(level="L1", ...),
        generator.generate_memory(level="L2", ...),
        generator.generate_memory(level="L3", ...)
    ]
    
    results = await asyncio.gather(*tasks)
    return results
```

### Caching Mechanism

```python
# Enable memory caching
generator = MemoryGenerator(
    enable_cache=True,
    cache_ttl=3600  # Cache for 1 hour
)
```

## 🚨 Troubleshooting

### Common Issues

1. **LLM call failure**
   - Check API key configuration
   - Verify network connectivity
   - Review error logs

2. **Poor memory generation quality**
   - Adjust prompt templates
   - Optimize input data quality
   - Adjust generation parameters

3. **Performance issues**
   - Enable concurrent processing
   - Optimize batch processing size
   - Use caching mechanism

### Debug Mode

```python
# Enable debug mode
generator = MemoryGenerator(debug_mode=True)

# View detailed logs
import logging
logging.getLogger("timem.memory").setLevel(logging.DEBUG)
```

## 📚 Related Documentation

- [Workflow Engine](../workflows/README.md)
- [Data Models](../models/README.md)
- [Core Services](../core/README.md)
- [Utility Functions](../utils/README.md)
