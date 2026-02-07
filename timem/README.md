# Core Engine (Anonymized Artifact)

This directory contains the core modules of an anonymized LLM-based memory management system for reproducing experiments in a submitted paper. The implementation focuses on multi-level memory generation, storage, and retrieval, and uses a LangGraph-based workflow engine.

## Overall Architecture

```
timem/
├── core/           # Core service layer - session state management, memory detection, connection pool, etc.
├── memory/         # Memory hierarchy module - L1-L5 memory generators
├── workflows/      # Workflow engine - LangGraph-based memory generation and retrieval process
├── models/         # Data models - unified memory data structure and validation
├── services/       # Business service layer - user service, character service, memory scanning, etc.
└── utils/          # Utility function library - logging, time management, text processing, etc.
```

## Core Features

### 1. **Five-Level Memory Architecture**
- **L1 Fragment Memory**: Single-conversation fragment-level memory, generated in real-time
- **L2 Session Memory**: Complete conversation summary memory, generated at the end of the conversation
- **L3 Daily Memory**: Daily activity comprehensive memory, generated daily
- **L4 Weekly Memory**: Weekly activity summary memory, generated weekly
- **L5 High-Level Memory**: Monthly activity high-level abstract memory, generated monthly

### 2. **LangGraph Workflow Engine**
- Modern workflow engine based on LangGraph
- Supports complex workflow orchestration and state management
- Built-in error handling and retry mechanism
- Supports parallel processing and asynchronous execution

### 3. **Intelligent Memory Generation**
- Multi-strategy memory generation algorithm
- Automatic deduplication and completeness checking
- Support for batch backfill and historical retrieval
- Time-based memory weight management

### 4. **Advanced Retrieval System**
- Hybrid strategy combining semantic and keyword retrieval
- Multi-dimensional query analysis and intelligent intent recognition
- Result fusion and intelligent ranking
- Real-time retrieval and cache optimization support

## 🚀 Quick Start

### Basic Usage

```python
from timem import get_memory_generator, run_memory_generation
from timem.workflows.memory_retrieval import MemoryRetrievalWorkflow

# Get memory generator
generator = get_memory_generator()

# Run memory generation
result = await run_memory_generation({
    "user_id": "user_001",
    "expert_id": "expert_001", 
    "session_id": "session_001",
    "dialogues": [...],
    "time_range": {
        "start": "2025-01-01T00:00:00",
        "end": "2025-01-01T23:59:59"
    }
})

# Memory retrieval
retrieval_workflow = MemoryRetrievalWorkflow()
results = await retrieval_workflow.retrieve_memories(
    query="user learning preferences",
    user_id="user_001",
    expert_id="expert_001",
    max_results=10
)
```

## 📁 Directory Structure

### `/core` - Core Service Layer
Responsible for system's fundamental services, including session state management, memory detection, connection pool management and other core functions.

**Main Components:**
- `SessionStateManager`: Session state manager
- `MemoryExistenceChecker`: Memory existence checker
- `MissingMemoryDetector`: Missing memory detector
- `UnifiedConnectionManager`: Unified connection manager
- `ExecutionState`: Execution state management
- `ServiceRegistry`: Service registry

### `/memory` - Memory Hierarchy Module
Implements generation logic for L1-L5 level memories, each level has corresponding generator.

**Main Components:**
- `MemoryGenerator`: Unified memory generator
- `L1FragmentMemory`: L1 fragment memory generator
- `L2SessionMemory`: L2 session memory generator
- `L3DailyMemory`: L3 daily memory generator
- `L4WeeklyMemory`: L4 weekly memory generator
- `L5HighLevelMemory`: L5 high-level memory generator

### `/workflows` - Workflow Engine
Workflow engine implemented based on LangGraph, containing complete process of memory generation and retrieval.

**Main Components:**
- `MemoryGenerationWorkflow`: Memory generation workflow
- `MemoryRetrievalWorkflow`: Memory retrieval workflow
- `/nodes`: Workflow node implementations
- `/retrieval_nodes`: Retrieval node implementations

### `/models` - Data Models
Defines unified data structures and validation rules to ensure data consistency.

**Main Components:**
- `Memory`: Unified memory model
- `MemoryLevel`: Memory level enumeration
- Various validators and converters

### `/services` - Business Service Layer
Implements specific business logic, including user management, character management, memory scanning, etc.

**Main Components:**
- `UserService`: User service
- `CharacterService`: Character service
- `MemoryGenerationService`: Memory generation service
- `SessionMemoryScanner`: Session memory scanner

### `/utils` - Utility Function Library
Provides various auxiliary functions, including logging, time management, text processing, etc.

**Main Components:**
- `logging`: Logging system
- `time_manager`: Time manager
- `text_processing`: Text processing
- `config_manager`: Configuration manager

## 🔧 Configuration Guide

### Environment Variables
```bash
# Database configuration
DATABASE_URL=postgresql://user:password@localhost:5432/timem
REDIS_URL=redis://localhost:6379
QDRANT_URL=http://localhost:6333
NEO4J_URL=bolt://localhost:7687

# LLM configuration
LLM_PROVIDER=openai
OPENAI_API_KEY=your_api_key
CLAUDE_API_KEY=your_claude_key
ZHIPUAI_API_KEY=your_zhipuai_key

# Logging configuration
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_FILE=logs/timem.log

# Performance configuration
MAX_CONCURRENT_REQUESTS=100
MEMORY_CACHE_TTL=3600
VECTOR_CACHE_SIZE=10000
```

### Configuration Files
Main configuration files are located in `config/` directory:
- `settings.yaml`: System settings
- `prompts.yaml`: Prompt configuration
- `retrieval_config.yaml`: Retrieval configuration
- `eval_prompt.yaml`: Evaluation prompt configuration

## 🧪 Testing

Run test suite:

```bash
# Run all tests
pytest tests/

# Run unit tests
pytest tests/unit/

# Run integration tests
pytest tests/integration/

# Run performance tests
pytest tests/performance/
```

## 📊 Performance Optimization

### Connection Pool Management
- Use `UnifiedConnectionManager` for unified database connection management
- Support connection pool warm-up and dynamic adjustment
- Automatic failover and reconnection mechanism

### Caching Strategy
- Memory generation result caching
- Retrieval result caching
- Session state caching
- Multi-level cache architecture

### Asynchronous Processing
- Fully asynchronous architecture design
- Batch processing optimization
- Concurrent control mechanism
- Intelligent load balancing

## 🛡️ Security Features

### Data Security
- End-to-end encryption transmission
- Sensitive data desensitization
- Access control
- Audit logging

### Privacy Protection
- User data isolation
- Memory data anonymization
- Compliance checking
- Data lifecycle management

## 🚨 Troubleshooting

### Common Issues

1. **Memory generation failure**
   - Check LLM API configuration
   - Verify prompt templates
   - Review error logs
   - Check network connectivity

2. **Inaccurate retrieval results**
   - Check vector index status
   - Verify retrieval configuration
   - Adjust retrieval strategy parameters
   - Check data quality

3. **Performance issues**
   - Check database connection pool
   - Optimize query statements
   - Adjust concurrent parameters
   - Monitor resource usage

### Log Analysis
```bash
# View error logs
grep "ERROR" logs/timem.log

# View performance logs
grep "PERFORMANCE" logs/timem.log

# View memory generation logs
grep "MEMORY_GENERATION" logs/timem.log

# View retrieval logs
grep "RETRIEVAL" logs/timem.log
```

## 🔄 Version Updates

### Current Version: v2.1.0

**Main Features:**
- ✅ Five-level memory architecture
- ✅ LangGraph workflow engine
- ✅ Intelligent retrieval engine
- ✅ State management mechanism
- ✅ Unified data model
- ✅ Multi-storage engine support
- ✅ Real-time memory update
- ✅ Memory quality assessment

**Planned Features:**
- 🔄 Personalized recommendations
- 🔄 Multi-modal memory support
- 🔄 Memory sentiment analysis
- 🔄 Cross-platform synchronization

## 📚 Related Documentation

- [API Reference](../../docs/API_reference/)
- [Architecture Design](../../docs/architecture/)
- [Deployment Guide](../../DEPLOYMENT.md)
- [Storage Layer Documentation](../storage/README.md)
- [LLM Adapter Documentation](../llm/README.md)
- [Application Layer Documentation](../app/README.md)

## 🤝 Contributing Guide

1. Fork the project
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## 📄 License

This project is licensed under the MIT License - see [LICENSE](../../LICENSE) file for details.