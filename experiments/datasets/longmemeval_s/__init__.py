"""
LongMemEval-S Dataset Experiment

Dataset configuration: longmemeval_s
Data source: data/longmemeval_s_split/

Experiment workflow:
1. 01_memory_generation.py - Memory generation (real system simulation, 500 users)
2. 02_memory_retrieval.py - Memory retrieval and answer generation
3. 03_evaluation.py - LongMemEval native evaluation + traditional metrics

Usage:
- Memory generation: pytest experiments/datasets/longmemeval_s/01_memory_generation.py
- Memory retrieval: python experiments/datasets/longmemeval_s/02_memory_retrieval.py
- Evaluation: python experiments/datasets/longmemeval_s/03_evaluation.py
"""
