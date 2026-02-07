"""
Dataset Utilities Package
Provides processing functionality for Locomo and LongMemEval datasets.

Main Features:
1. Locomo dataset processing: Load, parse and convert Locomo dialogue data
2. LongMemEval dataset processing: Load and process LongMemEval-S dataset questions and sessions

Usage:
```python
# Use Locomo dataset parser
from experiments.dataset_utils import LocomoParser, get_dataset_parser

# Use LongMemEval dataset loader
from experiments.dataset_utils import LongMemEvalSQuestionLoader
```
"""

from pathlib import Path

# Define data directory paths
LOCOMO_DATA_DIR = Path("data/locomo10_smart_split")
LONGMEMEVAL_DATA_DIR = Path("data/longmemeval_s_split")

# Export main classes
from .locomo.locomo_parser import (
    LocomoParser, 
    DialogueTurn, 
    ConversationSession,
    get_dataset_parser
)
from .longmemeval.longmemeval_loader import LongMemEvalSQuestionLoader

__all__ = [
    'LocomoParser',
    'DialogueTurn',
    'ConversationSession',
    'LongMemEvalSQuestionLoader',
    'get_dataset_parser',
    'LOCOMO_DATA_DIR',
    'LONGMEMEVAL_DATA_DIR'
]
