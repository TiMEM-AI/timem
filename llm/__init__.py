"""
TiMem LLM Adapters
LLM adapter module
"""

from .base_llm import BaseLLM
from .claude_adapter import ClaudeAdapter
from .openai_adapter import OpenAIAdapter
from .zhipuai_adapter import ZhipuAIAdapter
from .qwen_adapter import QwenAdapter
from .qwen_embedding_adapter import Qwen3EmbeddingService

def get_llm(provider: str, **kwargs) -> BaseLLM:
    # ... (implementation of get_llm)
    pass

__all__ = [
    "BaseLLM",
    "ClaudeAdapter",
    "OpenAIAdapter",
    "ZhipuAIAdapter",
    "QwenAdapter",
    "Qwen3EmbeddingService",
    "get_llm",
]