# Dataset Experiments (Anonymized Artifact)

## 📁 Directory Structure

Reorganized code is organized by dataset, with each dataset containing a complete experiment workflow (generation → retrieval → evaluation):

```
experiments/
  datasets/
    locomo/                                    # Locomo dataset experiments
      01_memory_generation.py                  # Memory generation (real system simulation)
      02_memory_retrieval.py                   # Memory retrieval and QA generation
      03_evaluation.py                         # QA evaluation
      __init__.py
    longmemeval_s/                            # LongMemEval-S dataset experiments
      01_memory_generation.py                  # Memory generation (500 users)
      02_memory_retrieval.py                   # Memory retrieval and answer generation
      03_evaluation.py                         # LongMemEval native evaluation
      __init__.py
  utils/                                       # Shared utilities
    stats_helper.py                            # Statistics collection helper
    __init__.py
```

## 🎯 Locomo Dataset Experiment Workflow

### 1️⃣ Memory Generation (`01_memory_generation.py`)
**Function**: Simulate real system operation and generate multi-level memories (L1-L5)

**Dataset Configuration**: `default` or `test`

**How to Run**:
```bash
# Set dataset configuration
export TIMEM_DATASET_PROFILE=default  # or test

# Run memory generation
pytest experiments/datasets/locomo/01_memory_generation.py -v
```

**Features**:
- Real system simulation: automatic backfill at midnight daily
- L2 generation between sessions
- Force mode backfill on last day
- Complete L1-L5 level memory generation

### 2️⃣ Memory Retrieval (`02_memory_retrieval.py`)
**Function**: Perform QA based on generated memories and generate evaluation data

**How to Run**:
```bash
python experiments/datasets/locomo/02_memory_retrieval.py
```

**Output**: 
- `logs/tests/memory_retrieval_eval_data_*.json` - Evaluation data file

### 3️⃣ Evaluation (`03_evaluation.py`)
**Function**: Evaluate retrieval results (traditional metrics + LLM evaluation)

**How to Run**:
```bash
# Auto-find latest evaluation data file
python experiments/datasets/locomo/03_evaluation.py

# Or specify file
python experiments/datasets/locomo/03_evaluation.py --data-file path/to/eval_data.json
```

**Evaluation Metrics**:
- Traditional metrics: F1, Rouge-L, BLEU-1, BLEU-2, METEOR, BERTScore-F1, Similarity
- LLM evaluation: GPT-4 or GLM-4-flash CORRECT/WRONG evaluation for question types 1-4

---

## 🚀 LongMemEval-S Dataset Experiment Workflow

### 1️⃣ Memory Generation (`01_memory_generation.py`)
**Function**: Generate complete multi-level memories for 500 users

**Dataset Configuration**: `longmemeval_s`

**How to Run**:
```bash
# Start containers
python scripts/dev/manage_containers.py start --profile longmemeval_s

# Set dataset configuration
export TIMEM_DATASET_PROFILE=longmemeval_s

# Run memory generation (full 500 users, 40 concurrent)
pytest experiments/datasets/longmemeval_s/01_memory_generation.py -v
```

**Features**:
- Full mode: 500 users
- 40 concurrent processing
- Process all sessions and turns for each user
- Real system simulation: daily backfill + inter-session L2 + final force backfill

### 2️⃣ Memory Retrieval (`02_memory_retrieval.py`)
**Function**: Perform QA based on generated memories, supporting 6 question types

**How to Run**:
```bash
# Basic run (all 500 users)
python experiments/datasets/longmemeval_s/02_memory_retrieval.py

# Limit number of users
python experiments/datasets/longmemeval_s/02_memory_retrieval.py --num-users 10

# Select N users from each of 6 question types
python experiments/datasets/longmemeval_s/02_memory_retrieval.py --use-type-selection --users-per-type 10

```

**Question Types**:
1. single-session-user
2. single-session-assistant
3. single-session-preference
4. multi-session
5. knowledge-update
6. temporal-reasoning

**Output**: 
- `logs/longmemeval_s/answers_*.json` - Answer file

### 3️⃣ Evaluation (`03_evaluation.py`)
**Function**: LongMemEval native evaluation + traditional metrics

**How to Run**:
```bash
# Auto-find latest answer file
python experiments/datasets/longmemeval_s/03_evaluation.py

# Specify input file
python experiments/datasets/longmemeval_s/03_evaluation.py --input path/to/answers.json

# LLM evaluation only (no traditional metrics)
python experiments/datasets/longmemeval_s/03_evaluation.py --disable-traditional

# Traditional metrics only (no LLM calls)
python experiments/datasets/longmemeval_s/03_evaluation.py --traditional-only
```

**Evaluation Metrics**:
- LongMemEval native evaluation: specialized prompts for different task types
- Traditional metrics: F1, Rouge-L, BLEU, METEOR, BERTScore

**Output Files**:
1. `*_scores_*.json` - Complete evaluation results
2. `*_scores_*_scores_table.csv` - Detailed evaluation scores table
3. `*_scores_*_summary_table.csv` - Summary statistics by question type

---

## Shared Utilities

### `stats_helper.py`
Statistics collection helper for both datasets.

**How to Use**:
```python
from experiments.utils.stats_helper import StatsTestHelper

stats_helper = StatsTestHelper()
# ... use statistics collection features
```

---

## Migration Notes

### Original File Location Mapping

**Locomo Dataset**:
- ~~`tests/integration/test_memory_generation_realistic_sim.py`~~ → `experiments/datasets/locomo/01_memory_generation.py`
- ~~`tests/integration/root_tests/test_retrieval_real_data.py`~~ → `experiments/datasets/locomo/02_memory_retrieval.py`
- ~~`experiments/code/evaluation/timem_qa_evaluation.py`~~ → `experiments/datasets/locomo/03_evaluation.py`

**LongMemEval-S Dataset**:
- ~~`tests/integration/test_longmemeval_s_sim.py`~~ → `experiments/datasets/longmemeval_s/01_memory_generation.py`
- ~~`experiments/code/evaluation/longmemeval_s_retrieval_generation.py`~~ → `experiments/datasets/longmemeval_s/02_memory_retrieval.py`
- ~~`experiments/code/evaluation/longmemeval_s_evaluation.py`~~ → `experiments/datasets/longmemeval_s/03_evaluation.py`

**Shared Utilities**:
- ~~`tests/integration/stats_test_helper.py`~~ → `experiments/utils/stats_helper.py`

---

## Reorganization Advantages

1. **Clear organization structure**: Grouped by dataset, each dataset contains complete experiment workflow
2. **Unified naming convention**: Use numeric prefix (01, 02, 03) to identify experiment steps
3. **Easy to maintain**: Related code centralized in same directory
4. **Easy to extend**: Adding new datasets follows same structure
5. **Clear dependencies**: Understand experiment workflow through filenames

---

## Important Notes

1. **Dataset configuration**: Ensure correct `TIMEM_DATASET_PROFILE` environment variable is set
2. **Execution order**: Must execute in order 01 → 02 → 03
3. **Data dependencies**: 
   - 02 depends on memory data generated by 01
   - 03 depends on evaluation data generated by 02
4. **Old files**: Original files remain in original locations and can be safely deleted

---

**Last Updated**: 2025-12-10
