# TiMem Experiments

This directory contains **reproduction scripts** for TiMem evaluation on benchmark datasets.

## Datasets

| Dataset | Description | Location |
|---------|-------------|----------|
| **LoCoMo** | Long-context conversations | `experiments/datasets/locomo/` |
| **LongMemEval-S** | Long-term memory evaluation | `experiments/datasets/longmemeval_s/` |

## Experiment Structure

Each dataset follows the same **3-step pipeline**:

```
01_memory_generation.py → 02_memory_retrieval.py → 03_evaluation.py
        │                          │                     │
        ▼                          ▼                     ▼
   Generate TMT            Retrieve memories       Calculate accuracy
```

### Step 1: Memory Generation

**Script**: `01_memory_generation.py`

**Purpose**: Generate L1-L5 memories from dialogues

**Input**: Raw dialogue files from `data/`

**Output**: Memories stored in databases

**Run**:
```bash
cd experiments/datasets/locomo
python 01_memory_generation.py
```

### Step 2: Memory Retrieval

**Script**: `02_memory_retrieval.py`

**Purpose**: Retrieve relevant memories for each query

**Input**: Queries from evaluation set

**Output**: Retrieved memories with rankings

**Run**:
```bash
python 02_memory_retrieval.py
```

### Step 3: Evaluation

**Script**: `03_evaluation.py`

**Purpose**: Calculate accuracy metrics

**Input**: Retrieved memories + ground truth

**Output**: Accuracy scores

**Run**:
```bash
python 03_evaluation.py
```

## Expected Results

### LoCoMo

- **Accuracy**: 75.30%
- **Improvement**: +26.8% over baseline

### LongMemEval-S

- **Accuracy**: 52.20%
- **Efficiency**: 91% faster, 90% fewer tokens

## Prerequisites

1. **Start databases**:
   ```bash
   cd migration
   docker-compose up -d
   ```

2. **Prepare datasets**:
   ```bash
   python experiments/dataset_utils/dataset_splitter.py --split-all
   ```

3. **Configure environment**:
   ```bash
   cp env.example .env
   # Edit .env with your API keys
   ```

## Troubleshooting

### Issue: Out of memory errors

**Solution**: Reduce batch size in `config/settings.yaml`

### Issue: Slow generation

**Solution**: Use faster LLM (e.g., GPT-4o-mini instead of GPT-4)

### Issue: Database connection errors

**Solution**: Check Docker containers are running:
```bash
docker ps
```

## See Also

- [Dataset Preparation](dataset_utils/README.md)
- [Configuration Guide](../config/README.md)
- [Main README](../README.md)
