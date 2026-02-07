"""
Memory processor module

Contains only base processor class
Concrete L1-L5 processors have been migrated to unified_processors.py
"""

from timem.workflows.nodes.memory_processors.base_processor import BaseMemoryProcessor

__all__ = [
    "BaseMemoryProcessor",
]
