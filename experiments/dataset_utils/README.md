# Dataset Utilities

This module provides utilities for loading, parsing, and processing different datasets used in TiMem experiments.

## 📁 Directory Structure

```
experiments/dataset_utils/
├── locomo/                     # Locomo dataset utilities
│   ├── __init__.py
│   └── locomo_parser.py       # Locomo data parser
├── longmemeval/               # LongMemEval dataset utilities
│   ├── __init__.py
│   └── longmemeval_loader.py  # LongMemEval data loader
├── __init__.py
└── dataset_splitter.py        # Dataset splitting utilities
```

## 🔧 Core Components

### Locomo Dataset Utilities

#### `locomo_parser.py`
Parses Locomo dataset files and converts them to TiMem format.

**Features**:
- Parse conversation data
- Extract user and expert information
- Handle dialogue turns
- Generate memory-relevant metadata

**Usage**:
```python
from experiments.dataset_utils.locomo.locomo_parser import LocomoParser

parser = LocomoParser()
conversations = parser.parse("path/to/locomo/data")

for conv in conversations:
    print(f"User: {conv.user_id}")
    print(f"Expert: {conv.expert_id}")
    print(f"Dialogues: {len(conv.dialogues)}")
```

### LongMemEval Dataset Utilities

#### `longmemeval_loader.py`
Loads and processes LongMemEval dataset with 500 users.

**Features**:
- Load user profiles
- Parse conversation history
- Handle multi-session data
- Support different question types

**Usage**:
```python
from experiments.dataset_utils.longmemeval.longmemeval_loader import LongMemEvalLoader

loader = LongMemEvalLoader()
users = loader.load("path/to/longmemeval/data")

for user in users:
    print(f"User ID: {user.user_id}")
    print(f"Sessions: {len(user.sessions)}")
    print(f"Total turns: {user.total_turns}")
```

### Dataset Splitting

#### `dataset_splitter.py`
Utilities for splitting datasets for training, validation, and testing.

**Features**:
- Train/val/test split
- Stratified splitting
- User-level splitting
- Session-level splitting

**Usage**:
```python
from experiments.dataset_utils.dataset_splitter import DatasetSplitter

splitter = DatasetSplitter(train_ratio=0.7, val_ratio=0.15, test_ratio=0.15)

train_data, val_data, test_data = splitter.split(dataset)

print(f"Train: {len(train_data)} samples")
print(f"Val: {len(val_data)} samples")
print(f"Test: {len(test_data)} samples")
```

## 📊 Data Formats

### Conversation Format
```python
{
    "user_id": "user_001",
    "expert_id": "expert_001",
    "session_id": "session_001",
    "start_time": "2025-01-01T10:00:00",
    "end_time": "2025-01-01T11:00:00",
    "dialogues": [
        {
            "speaker": "user",
            "content": "Hello",
            "timestamp": "2025-01-01T10:00:00"
        },
        {
            "speaker": "expert",
            "content": "Hi there!",
            "timestamp": "2025-01-01T10:01:00"
        }
    ]
}
```

### User Profile Format
```python
{
    "user_id": "user_001",
    "name": "John Doe",
    "sessions": [
        {
            "session_id": "session_001",
            "expert_id": "expert_001",
            "start_time": "2025-01-01T10:00:00",
            "end_time": "2025-01-01T11:00:00",
            "turn_count": 10
        }
    ],
    "total_turns": 100,
    "question_types": ["single-session-user", "multi-session"]
}
```

## 🚀 Usage Examples

### Load Locomo Dataset
```python
from experiments.dataset_utils.locomo.locomo_parser import LocomoParser

parser = LocomoParser()
conversations = parser.parse("data/locomo")

# Process conversations
for conv in conversations:
    print(f"Processing {conv.session_id}")
    # Your processing logic
```

### Load LongMemEval Dataset
```python
from experiments.dataset_utils.longmemeval.longmemeval_loader import LongMemEvalLoader

loader = LongMemEvalLoader()
users = loader.load("data/longmemeval_s")

# Filter by question type
single_session_users = [u for u in users if "single-session" in u.question_types]
print(f"Found {len(single_session_users)} single-session users")
```

### Split Dataset
```python
from experiments.dataset_utils.dataset_splitter import DatasetSplitter

splitter = DatasetSplitter(
    train_ratio=0.7,
    val_ratio=0.15,
    test_ratio=0.15,
    random_seed=42
)

train, val, test = splitter.split(conversations)

# Save splits
import json
with open("train.json", "w") as f:
    json.dump(train, f)
```

## 🧪 Testing

Run dataset utility tests:

```bash
# Test Locomo parser
pytest tests/unit/test_locomo_parser.py -v

# Test LongMemEval loader
pytest tests/unit/test_longmemeval_loader.py -v

# Test dataset splitter
pytest tests/unit/test_dataset_splitter.py -v
```

## 📈 Performance Considerations

- **Memory efficiency**: Load data in batches for large datasets
- **Caching**: Cache parsed data to avoid re-parsing
- **Parallel processing**: Use multiprocessing for large-scale parsing

## 🛠️ Troubleshooting

### Issue: Data parsing fails
- Check data file format
- Verify file encoding (UTF-8)
- Review error logs for details

### Issue: Memory issues with large datasets
- Use batch processing
- Implement streaming data loading
- Consider data sampling

### Issue: Inconsistent data format
- Validate data schema
- Use data validation tools
- Check for missing fields

## 📚 Related Documentation

- [Locomo Dataset](../config/datasets/locomo/README.md)
- [LongMemEval Dataset](../config/datasets/longmemeval_s/README.md)
- [Experiment Guide](../experiments/datasets/README.md)
