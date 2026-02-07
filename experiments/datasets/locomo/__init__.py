"""
Locomo Dataset Experiment

Dataset configuration: default or test
Data source: data/locomo10_smart_split/

Experiment workflow:
1. 01_memory_generation.py - Memory generation (real system simulation)
2. 02_memory_retrieval.py - Memory retrieval and QA generation
3. 03_evaluation.py - QA evaluation (traditional metrics + LLM evaluation)

Usage:
- Memory generation: pytest experiments/datasets/locomo/01_memory_generation.py
- Memory retrieval: python experiments/datasets/locomo/02_memory_retrieval.py
- Evaluation: python experiments/datasets/locomo/03_evaluation.py
"""
