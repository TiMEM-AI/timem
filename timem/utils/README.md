# TiMem Utility Functions Library

This module provides various auxiliary functions and tools for the TiMem system, including logging, time management, text processing, configuration management and other core tools.

## 🏗️ Module Structure

```
utils/
├── logging.py                    # Logging system
├── time_manager.py              # Time manager
├── text_processing.py            # Text processing tools
├── config_manager.py            # Configuration manager
├── memory_accessor.py           # Memory accessor
├── session_tracker.py           # Session tracker
├── prompt_manager.py            # Prompt manager
├── character_id_resolver.py     # Character ID resolver
├── chinese_tokenizer.py         # Chinese tokenizer
├── conversation_loader.py       # Conversation loader
├── dataset_parser.py            # Dataset parser
├── dialogue_simulator.py        # Dialogue simulator
├── enhanced_qa_loader.py       # Enhanced QA loader
├── qa_loader.py                 # QA loader
├── locomo_parser.py             # Locomo parser
├── json_utils.py                # JSON utilities
├── qdrant_utils.py              # Qdrant utilities
├── retrieval_config_manager.py  # Retrieval configuration manager
├── session_tracker_postgres.py  # PostgreSQL session tracker
├── memory_object_utils.py       # Memory object utilities
├── time_formatter.py            # Time formatter
├── time_parser.py               # Time parser
├── time_utils.py                # Time utilities
├── time_window_calculator.py    # Time window calculator
├── high_volume_logging.py       # High-volume logging
├── standard_high_volume_logging.py  # Standard high-volume logging
└── standard_logging.py          # Standard logging
```

## 🔧 Core Tool Modules

### 1. Logging System (logging.py)

**Features**: Provides unified logging functionality supporting multi-level and multi-category log output.

**Characteristics**:
- Simplified logging system using only print to avoid blocking
- Support for multi-level logs (TRACE, DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Support for multi-category logs (SYSTEM, WORKFLOW, STORAGE, LLM, MEMORY)
- Thread-safe logging

**Usage Example**:
```python
from timem.utils.logging import get_logger, init_logging

# Initialize logging system
init_logging()

# Get logger instance
logger = get_logger(__name__)

# Log messages
logger.info("System started successfully")
logger.error("Processing failed", extra={"error_code": "E001"})
logger.debug("Debug information", extra={"data": {...}})
```

### 2. Time Manager (time_manager.py)

**Features**: Provides unified time processing functions to solve issues like inconsistent time formats and non-unified timezone handling.

**Characteristics**:
- Unified use of timezone-naive datetime format
- Provides time window calculation functionality
- Supports time format conversion and validation
- Avoids timezone confusion issues

**Usage Example**:
```python
from timem.utils.time_manager import get_time_manager

# Get time manager instance
time_manager = get_time_manager()

# Get current time
current_time = time_manager.get_current_time()

# Calculate time window
time_window = time_manager.calculate_time_window(
    start_time="2025-01-01T00:00:00",
    end_time="2025-01-01T23:59:59",
    level="L3"
)

# Format time
formatted_time = time_manager.format_time(current_time)
```

### 3. Text Processing Tools (text_processing.py)

**Features**: Provides text cleaning, tokenization, keyword extraction, summary generation and other functions.

**Characteristics**:
- LLM-based implementation, independent of traditional tokenization frameworks
- Support for Chinese text processing
- Provides text similarity calculation
- Supports keyword extraction and summary generation

**Usage Example**:
```python
from timem.utils.text_processing import LLMTextProcessor

# Create text processor
processor = LLMTextProcessor()

# Clean text
cleaned_text = await processor.clean_text("Original text content")

# Extract keywords
keywords = await processor.extract_keywords("Text content")

# Generate summary
summary = await processor.generate_summary("Long text content", max_length=200)

# Calculate text similarity
similarity = await processor.calculate_similarity("Text 1", "Text 2")
```

### 4. Configuration Manager (config_manager.py)

**Features**: Provides unified configuration management supporting loading configuration from multiple YAML files.

**Characteristics**:
- Support for multi-file configuration loading
- Support for environment variable references (`${VAR_NAME}` format)
- Provides configuration caching and hot reload
- Supports configuration validation and default values

**Usage Example**:
```python
from timem.utils.config_manager import get_config

# Get configuration manager
config = get_config()

# Get configuration values
llm_config = config.get_llm_config()
database_config = config.get_database_config()

# Get specific configuration
api_key = config.get("llm.openai.api_key")
timeout = config.get("workflow.timeout", default=300)
```

## 📊 Data Processing Tools

### 1. Memory Accessor (memory_accessor.py)

**Features**: Provides unified memory data access interface.

**Usage Example**:
```python
from timem.utils.memory_accessor import get_memory_indexer

# Get memory indexer
indexer = get_memory_indexer()

# Search memories
memories = await indexer.search_memories(
    query="Learning preferences",
    user_id="user_001",
    expert_id="expert_001",
    limit=10
)
```

### 2. Session Tracker (session_tracker.py)

**Features**: Tracks and manages user session state.

**Usage Example**:
```python
from timem.utils.session_tracker import get_session_tracker

# Get session tracker
tracker = get_session_tracker()

# Track session
await tracker.track_session(
    session_id="session_001",
    user_id="user_001",
    expert_id="expert_001"
)

# Get session state
session_state = await tracker.get_session_state("session_001")
```

### 3. Prompt Manager (prompt_manager.py)

**Features**: Manages LLM prompt templates.

**Usage Example**:
```python
from timem.utils.prompt_manager import get_prompt_manager

# Get prompt manager
prompt_manager = get_prompt_manager()

# Get prompt
prompt = prompt_manager.get_prompt("memory_generation", "L2")

# Render prompt
rendered_prompt = prompt_manager.render_prompt(
    "memory_generation", 
    "L2",
    context={"dialogues": [...], "user_id": "user_001"}
)
```

## 🔍 Professional Tool Modules

### 1. Character ID Resolver (character_id_resolver.py)

**Features**: Parses and processes character ID information.

**Usage Example**:
```python
from timem.utils.character_id_resolver import CharacterIDResolver

# Create character ID resolver
resolver = CharacterIDResolver()

# Resolve character ID
character_info = await resolver.resolve_character_id("expert_001")

# Get character information
role_info = await resolver.get_character_info("expert_001")
```

### 2. Chinese Tokenizer (chinese_tokenizer.py)

**Features**: Specialized Chinese text tokenization processing.

**Usage Example**:
```python
from timem.utils.chinese_tokenizer import ChineseTokenizer

# Create Chinese tokenizer
tokenizer = ChineseTokenizer()

# Tokenize
tokens = await tokenizer.tokenize("Chinese text content")

# Count tokens
token_count = await tokenizer.count_tokens("Chinese text content")
```

### 3. Conversation Loader (conversation_loader.py)

**Features**: Loads and processes conversation data.

**Usage Example**:
```python
from timem.utils.conversation_loader import ConversationLoader

# Create conversation loader
loader = ConversationLoader()

# Load conversation data
dialogues = await loader.load_conversations(
    user_id="user_001",
    expert_id="expert_001",
    time_range={...}
)
```

## 📈 High-Concurrency Tools

### 1. High-Volume Logging (high_volume_logging.py)

**Features**: Logging system specifically designed for high-concurrency scenarios.

**Characteristics**:
- Asynchronous logging
- Batch log processing
- Memory optimization
- Performance monitoring

**Usage Example**:
```python
from timem.utils.high_volume_logging import HighVolumeLogger

# Create high-volume logger
logger = HighVolumeLogger()

# Log asynchronously
await logger.log_async("INFO", "Processing completed", extra={"count": 1000})

# Batch logging
await logger.log_batch([
    {"level": "INFO", "message": "Processing 1", "extra": {...}},
    {"level": "INFO", "message": "Processing 2", "extra": {...}}
])
```

### 2. Standard High-Volume Logging (standard_high_volume_logging.py)

**Features**: Standardized high-concurrency log processing.

**Usage Example**:
```python
from timem.utils.standard_high_volume_logging import StandardHighVolumeLogger

# Create standard high-volume logger
logger = StandardHighVolumeLogger()

# Log performance metrics
await logger.log_performance("memory_generation", duration=1.5, memory_usage="100MB")
```

## 🛠️ Database Tools

### 1. PostgreSQL Session Tracker (session_tracker_postgres.py)

**Features**: PostgreSQL-based session tracking implementation.

**Usage Example**:
```python
from timem.utils.session_tracker_postgres import PostgresSessionTracker

# Create PostgreSQL session tracker
tracker = PostgresSessionTracker()

# Track session
await tracker.track_session(
    session_id="session_001",
    user_id="user_001",
    expert_id="expert_001",
    metadata={...}
)
```

### 2. Qdrant Tools (qdrant_utils.py)

**Features**: Utility functions for interacting with Qdrant vector database.

**Usage Example**:
```python
from timem.utils.qdrant_utils import QdrantUtils

# Create Qdrant utilities
qdrant_utils = QdrantUtils()

# Create collection
await qdrant_utils.create_collection("memories", dimension=768)

# Insert vectors
await qdrant_utils.insert_vectors("memories", vectors=[...])

# Search vectors
results = await qdrant_utils.search_vectors("memories", query_vector=[...], limit=10)
```

## 📊 Time Processing Tools

### 1. Time Formatter (time_formatter.py)

**Features**: Provides conversion and formatting of various time formats.

**Usage Example**:
```python
from timem.utils.time_formatter import TimeFormatter

# Create time formatter
formatter = TimeFormatter()

# Format time
formatted_time = formatter.format_datetime(datetime.now())

# Parse time string
parsed_time = formatter.parse_datetime("2025-01-01T10:00:00")
```

### 2. Time Window Calculator (time_window_calculator.py)

**Features**: Calculates various time windows and ranges.

**Usage Example**:
```python
from timem.utils.time_window_calculator import TimeWindowCalculator

# Create time window calculator
calculator = TimeWindowCalculator()

# Calculate daily time window
daily_window = calculator.calculate_daily_window("2025-01-01")

# Calculate weekly time window
weekly_window = calculator.calculate_weekly_window("2025-01-01")
```

## 🧪 Testing Tools

### 1. Dialogue Simulator (dialogue_simulator.py)

**Features**: Simulates user conversation data for testing.

**Usage Example**:
```python
from timem.utils.dialogue_simulator import DialogueSimulator

# Create dialogue simulator
simulator = DialogueSimulator()

# Generate simulated dialogues
dialogues = await simulator.generate_dialogues(
    user_id="user_001",
    expert_id="expert_001",
    count=10
)
```

### 2. Dataset Parser (dataset_parser.py)

**Features**: Parses datasets in various formats.

**Usage Example**:
```python
from timem.utils.dataset_parser import DatasetParser

# Create dataset parser
parser = DatasetParser()

# Parse JSON dataset
data = await parser.parse_json_dataset("data/dataset.json")

# Parse CSV dataset
data = await parser.parse_csv_dataset("data/dataset.csv")
```

## ⚙️ Configuration Guide

### Logging Configuration

```yaml
logging:
  level: "INFO"
  format: "json"
  output: "console"
  file_path: "logs/timem.log"
  max_file_size: "100MB"
  backup_count: 5
```

### Time Manager Configuration

```yaml
time_manager:
  timezone_offset: 8
  default_format: "%Y-%m-%dT%H:%M:%S"
  strict_mode: true
```

### Text Processing Configuration

```yaml
text_processing:
  llm_provider: "openai"
  model: "gpt-4"
  max_tokens: 2000
  temperature: 0.7
```

## 🚀 Best Practices

### 1. Logging Best Practices

```python
# Use structured logging
logger.info("Processing completed", extra={
    "user_id": "user_001",
    "session_id": "session_001",
    "duration": 1.5,
    "memory_count": 10
})

# Use appropriate log levels
logger.debug("Debug information")  # Development debugging
logger.info("General information")   # Normal operation
logger.warning("Warning message") # Potential issues
logger.error("Error message")  # Error situations
logger.critical("Critical error") # System crash
```

### 2. Time Processing Best Practices

```python
# Use time manager consistently
time_manager = get_time_manager()

# Avoid using datetime.now() directly
current_time = time_manager.get_current_time()

# Use standard time format
formatted_time = time_manager.format_time(current_time)
```

### 3. Configuration Management Best Practices

```python
# Use configuration manager
config = get_config()

# Provide default values
timeout = config.get("workflow.timeout", default=300)

# Validate configuration
if not config.get("llm.api_key"):
    raise ValueError("LLM API key not configured")
```

## Unit Tests

```bash
# Test logging system
pytest tests/unit/test_logging.py -v

# Test time manager
pytest tests/unit/test_time_manager.py -v

# Test text processing
pytest tests/unit/test_text_processing.py -v

# Test configuration manager
pytest tests/unit/test_config_manager.py -v
```

### Integration Tests

```bash
# Test utilities integration
pytest tests/integration/test_utils_integration.py -v

# Test high-concurrency scenarios
pytest tests/integration/test_high_volume.py -v
```

## 📈 Performance Optimization

### 1. Logging Performance Optimization

```python
# Use asynchronous logging
await logger.log_async("INFO", "Processing completed")

# Batch log processing
await logger.log_batch(log_entries)

# Enable log caching
logger = get_logger(__name__, enable_cache=True)
```

### 2. Time Processing Performance Optimization

```python
# Use time caching
time_manager = get_time_manager(enable_cache=True)

# Batch time calculations
time_windows = time_manager.calculate_batch_time_windows(dates)
```

### 3. Configuration Performance Optimization

```python
# Enable configuration caching
config = get_config(enable_cache=True)

# Preload configurations
config.preload_configs(["llm", "database", "workflow"])
```

## 🚨 Troubleshooting

### Common Issues

1. **Logging failures**
   - Check log file permissions
   - Verify logging configuration
   - Check disk space

2. **Time format errors**
   - Use unified time manager
   - Check time format configuration
   - Verify timezone settings

3. **Configuration loading failures**
   - Check configuration file paths
   - Verify YAML syntax
   - Check environment variables

### Debug Mode

```python
# Enable debug mode
logger = get_logger(__name__, debug=True)
time_manager = get_time_manager(debug=True)
config = get_config(debug=True)
```

## 📚 Related Documentation

- [Memory Hierarchy Module](../memory/README.md)
- [Workflow Engine](../workflows/README.md)
- [Data Models](../models/README.md)
- [Core Services](../core/README.md)
