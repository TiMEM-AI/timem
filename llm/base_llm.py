"""
TiMem Base LLM Interface
Defines unified large language model interface specification
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Union, AsyncIterator
from dataclasses import dataclass
from enum import Enum

from timem.utils.logging import get_logger

class ModelType(str, Enum):
    """Model type enumeration"""
    CHAT = "chat"
    COMPLETION = "completion"
    EMBEDDING = "embedding"
    SUMMARIZATION = "summarization"

class MessageRole(str, Enum):
    """Message role enumeration"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION = "function"

@dataclass
class Message:
    """Message structure"""
    role: MessageRole
    content: str
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class ChatResponse:
    """Chat response structure"""
    content: str
    finish_reason: str
    model: str
    usage: Dict[str, int]
    response_time: float
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class EmbeddingResponse:
    """Embedding response structure"""
    embedding: List[float]
    model: str
    usage: Dict[str, int]
    response_time: float
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class ModelConfig:
    """Model configuration"""
    model_name: str
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    stop: Optional[List[str]] = None
    stream: bool = False
    
class BaseLLM(ABC):
    """Base LLM interface"""
    
    def __init__(self, config: ModelConfig):
        self.config = config
        self.model_type = ModelType.CHAT
        self.supported_models = []
        self.api_key = None
        self.base_url = None
        
    @abstractmethod
    async def chat(self, messages: List[Message], **kwargs) -> ChatResponse:
        """Chat conversation"""
        pass
    
    async def chat_batch(self, batch_messages: List[List[Message]], **kwargs) -> List[ChatResponse]:
        """
        Batch concurrent chat conversations
        
        Args:
            batch_messages: List of message lists, each sublist represents one conversation
            **kwargs: Other parameters
            
        Returns:
            List of ChatResponse, corresponding to input order
        """
        # Default implementation: use asyncio.gather for concurrent calls
        import asyncio
        tasks = [self.chat(messages, **kwargs) for messages in batch_messages]
        return await asyncio.gather(*tasks)
    
    @abstractmethod
    async def chat_stream(self, messages: List[Message], **kwargs) -> AsyncIterator[str]:
        """Streaming chat conversation"""
        pass
    
    @abstractmethod
    async def complete(self, prompt: str, **kwargs) -> str:
        """Text completion"""
        pass
    
    @abstractmethod
    async def embed(self, text: str, **kwargs) -> EmbeddingResponse:
        """Text embedding"""
        pass
    
    @abstractmethod
    async def embed_batch(self, texts: List[str], **kwargs) -> List[EmbeddingResponse]:
        """Batch text embedding"""
        pass
    
    @abstractmethod
    async def summarize(self, text: str, **kwargs) -> str:
        """Text summarization"""
        pass
    
    @abstractmethod
    async def validate_model(self, model_name: str) -> bool:
        """Validate if model is available"""
        pass
    
    @abstractmethod
    async def get_model_info(self, model_name: str) -> Dict[str, Any]:
        """Get model information"""
        pass
    
    # Utility methods
    def create_message(self, role: MessageRole, content: str, metadata: Optional[Dict[str, Any]] = None) -> Message:
        """Create message"""
        return Message(role=role, content=content, metadata=metadata)
    
    def format_chat_prompt(self, system_prompt: str, user_message: str) -> List[Message]:
        """Format chat prompt"""
        messages = []
        if system_prompt:
            messages.append(self.create_message(MessageRole.SYSTEM, system_prompt))
        messages.append(self.create_message(MessageRole.USER, user_message))
        return messages
    
    def calculate_tokens(self, text) -> int:
        """Calculate token count (simplified implementation)"""
        # Ensure text is string type
        if not isinstance(text, str):
            text = str(text) if text is not None else ""
        
        # Simplified calculation: Chinese by character, English by word
        chinese_chars = sum(1 for char in text if '\u4e00' <= char <= '\u9fff')
        english_words = len([word for word in text.split() if word.isalpha()])
        return chinese_chars + english_words
    
    def validate_config(self) -> bool:
        """Validate configuration"""
        if not self.config.model_name:
            return False
        if self.config.temperature < 0 or self.config.temperature > 2:
            return False
        if self.config.max_tokens and self.config.max_tokens <= 0:
            return False
        return True

class BaseEmbeddingService(ABC):
    """Embedding service base class"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.logger = get_logger(self.__class__.__name__)
    
    @abstractmethod
    async def embed_text(self, text: str) -> List[float]:
        """Text embedding"""
        pass
    
    @abstractmethod
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Batch text embedding"""
        pass
    
    @abstractmethod
    def get_dimension(self) -> int:
        """Get vector dimension"""
        pass

class LLMError(Exception):
    """LLM error base class"""
    pass

class ModelNotFoundError(LLMError):
    """Model not found error"""
    pass

class RateLimitError(LLMError):
    """Rate limit error"""
    pass

class AuthenticationError(LLMError):
    """Authentication error"""
    pass

class InvalidRequestError(LLMError):
    """Invalid request error"""
    pass

class ServiceUnavailableError(LLMError):
    """Service unavailable error"""
    pass

# Decorators
def handle_llm_errors(func):
    """
    LLM error handling decorator
    
    Supports both regular async functions and async generator functions
    """
    import inspect
    import functools
    
    # Check if it's an async generator function
    if inspect.isasyncgenfunction(func):
        @functools.wraps(func)
        async def async_gen_wrapper(*args, **kwargs):
            try:
                async for item in func(*args, **kwargs):
                    yield item
            except Exception as e:
                # Convert to specific LLM error based on error type
                if "model not found" in str(e).lower():
                    raise ModelNotFoundError(f"Model not found: {e}")
                elif "rate limit" in str(e).lower():
                    raise RateLimitError(f"Rate limit: {e}")
                elif "authentication" in str(e).lower():
                    raise AuthenticationError(f"Authentication failed: {e}")
                elif "invalid request" in str(e).lower():
                    raise InvalidRequestError(f"Invalid request: {e}")
                elif "service unavailable" in str(e).lower():
                    raise ServiceUnavailableError(f"Service unavailable: {e}")
                else:
                    raise LLMError(f"LLM error: {e}")
        
        return async_gen_wrapper
    else:
        @functools.wraps(func)
        async def async_func_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                # Convert to specific LLM error based on error type
                if "model not found" in str(e).lower():
                    raise ModelNotFoundError(f"Model not found: {e}")
                elif "rate limit" in str(e).lower():
                    raise RateLimitError(f"Rate limit: {e}")
                elif "authentication" in str(e).lower():
                    raise AuthenticationError(f"Authentication failed: {e}")
                elif "invalid request" in str(e).lower():
                    raise InvalidRequestError(f"Invalid request: {e}")
                elif "service unavailable" in str(e).lower():
                    raise ServiceUnavailableError(f"Service unavailable: {e}")
                else:
                    raise LLMError(f"LLM error: {e}")
        
        return async_func_wrapper