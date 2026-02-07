# Configuration

This directory contains all configuration files for this anonymized artifact, organized by functionality.

## 📁 Directory Structure

```
config/
├── dataset_profiles.yaml       # Dataset configuration profiles
├── datasets/                   # Dataset-specific configurations
│   ├── default/               # Default dataset (Locomo)
│   ├── locomo/                # Locomo dataset configuration
│   └── longmemeval_s/         # LongMemEval-S dataset configuration
├── eval_prompt.yaml           # Evaluation prompt templates
├── prompts.yaml               # LLM prompt templates
├── qa_prompts.yaml            # QA-specific prompt templates
└── settings.yaml              # System settings
```

## 🔧 Main Configuration Files

### `dataset_profiles.yaml`
Defines available dataset profiles and their settings.

**Usage**:
```bash
export TIMEM_DATASET_PROFILE=default  # or locomo, longmemeval_s, test
```

### `settings.yaml`
System-wide settings including:
- Database configuration
- LLM provider settings
- Cache configuration
- Logging settings
- Performance tuning parameters

### `prompts.yaml`
LLM prompt templates for:
- Memory generation
- Memory retrieval
- Intent analysis
- Query processing

### `qa_prompts.yaml`
Question-answering specific prompts for:
- Answer generation
- Question classification
- Relevance scoring

### `eval_prompt.yaml`
Evaluation prompt templates for:
- Traditional metric evaluation
- LLM-based evaluation
- Quality assessment

## 📊 Dataset Configurations

### `datasets/default/`
Default dataset configuration (Locomo dataset).

### `datasets/locomo/`
Locomo dataset specific configuration:
- Data paths
- Processing parameters
- Memory generation settings

### `datasets/longmemeval_s/`
LongMemEval-S dataset specific configuration:
- 500 user dataset settings
- Concurrent processing parameters
- Evaluation settings

## 🚀 Configuration Usage

### Load Configuration
```python
from timem.utils.config_context import ConfigContext

# Load default configuration
config = ConfigContext.load()

# Load specific dataset profile
config = ConfigContext.load(profile="longmemeval_s")
```

### Access Configuration Values
```python
# Get database URL
db_url = config.get("database.url")

# Get LLM settings
llm_provider = config.get("llm.provider")
llm_model = config.get("llm.model")

# Get memory generation settings
memory_config = config.get("memory_generation")
```

## ⚙️ Environment Variables

Key environment variables:
- `TIMEM_DATASET_PROFILE`: Dataset profile to use (default, locomo, longmemeval_s, test)
- `TIMEM_CONFIG_DIR`: Configuration directory path
- `DATABASE_URL`: Database connection string
- `REDIS_URL`: Redis connection string
- `QDRANT_URL`: Qdrant vector database URL

## 📝 Configuration Best Practices

1. **Profile-specific settings**: Use dataset profiles for different configurations
2. **Environment variables**: Override settings via environment variables for deployment
3. **Secrets management**: Store sensitive data (API keys, passwords) in environment variables
4. **Version control**: Keep configuration templates in git, exclude sensitive data

## 🔐 Security Considerations

- Never commit API keys or passwords to version control
- Use environment variables for sensitive configuration
- Restrict file permissions on configuration files
- Regularly rotate credentials

## 📚 Related Documentation

- [Dataset Configuration Guide](./datasets/README.md)
- [System Settings Reference](./settings.yaml)
- [Prompt Templates](./prompts.yaml)
