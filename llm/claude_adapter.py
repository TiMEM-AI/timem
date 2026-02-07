"""
TiMem Claude LLM Adapter
Implements concrete interface for Claude API
"""

import asyncio
import time
from typing import Dict, List, Optional, Any, AsyncIterator
from typing import Tuple
import httpx
import json

from llm.base_llm import (
    BaseLLM, Message, MessageRole, ChatResponse, EmbeddingResponse, ModelConfig,
    ModelType, handle_llm_errors
)
from timem.utils.logging import get_logger

class ClaudeAdapter(BaseLLM):
    """Claude API Adapter"""
    
    def __init__(self, config: ModelConfig, api_key: str, base_url: str = "https://api.anthropic.com"):
        super().__init__(config)
        self.api_key = api_key
        self.base_url = base_url
        self.model_type = ModelType.CHAT
        self.logger = get_logger(__name__)
        
        # Supported models list
        self.supported_models = [
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
            "claude-instant-1.2"
        ]
        
        # Chat model configuration
        self.chat_models = {
            "claude-3-opus-20240229": {"max_tokens": 4096, "context_window": 200000},
            "claude-3-sonnet-20240229": {"max_tokens": 4096, "context_window": 200000},
            "claude-3-haiku-20240307": {"max_tokens": 4096, "context_window": 200000},
            "claude-instant-1.2": {"max_tokens": 4096, "context_window": 100000}
        }
        
        self.logger.info(f"Initializing Claude adapter, model: {self.config.model_name}")
    
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers"""
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
    
    def _convert_messages(self, messages: List[Message]) -> Tuple[str, List[Dict]]:
        """Convert messages to Claude format"""
        system_prompt = ""
        claude_messages = []
        
        for message in messages:
            if message.role == MessageRole.SYSTEM:
                system_prompt = message.content
            else:
                claude_messages.append({
                    "role": message.role.value,
                    "content": message.content
                })
        
        return system_prompt, claude_messages
    
    @handle_llm_errors
    async def chat(self, messages: List[Message], **kwargs) -> ChatResponse:
        """Chat conversation"""
        start_time = time.time()
        
        # Convert message format
        system_prompt, claude_messages = self._convert_messages(messages)
        
        # Build request data
        request_data = {
            "model": self.config.model_name,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens or 1024),
            "temperature": kwargs.get("temperature", self.config.temperature),
            "messages": claude_messages
        }
        
        if system_prompt:
            request_data["system"] = system_prompt
        
        # Send request
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/v1/messages",
                headers=self._get_headers(),
                json=request_data
            )
            
            if response.status_code != 200:
                error_data = response.json() if response.text else {"error": "Unknown error"}
                raise Exception(f"Claude API error: {response.status_code}, {error_data}")
            
            result = response.json()
        
        # Parse response
        response_time = time.time() - start_time
        
        chat_response = ChatResponse(
            content=result["content"][0]["text"],
            finish_reason=result.get("stop_reason", "stop"),
            model=result["model"],
            usage=result.get("usage", {}),
            response_time=response_time,
            metadata={
                "input_tokens": result.get("usage", {}).get("input_tokens", 0),
                "output_tokens": result.get("usage", {}).get("output_tokens", 0),
                "stop_sequence": result.get("stop_sequence")
            }
        )
        
        self.logger.debug(f"Claude chat completed, elapsed: {response_time:.2f}s")
        return chat_response
    
    @handle_llm_errors
    async def chat_stream(self, messages: List[Message], **kwargs) -> AsyncIterator[str]:
        """Streaming chat conversation"""
        system_prompt, claude_messages = self._convert_messages(messages)
        
        request_data = {
            "model": self.config.model_name,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens or 1024),
            "temperature": kwargs.get("temperature", self.config.temperature),
            "messages": claude_messages,
            "stream": True
        }
        
        if system_prompt:
            request_data["system"] = system_prompt
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/v1/messages",
                headers=self._get_headers(),
                json=request_data
            ) as response:
                
                if response.status_code != 200:
                    error_data = await response.aread()
                    raise Exception(f"Claude API error: {response.status_code}, {error_data}")
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        
                        if data_str.strip() == "[DONE]":
                            break
                        
                        try:
                            data = json.loads(data_str)
                            if data.get("type") == "content_block_delta":
                                delta = data.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    yield delta.get("text", "")
                        except json.JSONDecodeError:
                            continue
    
    @handle_llm_errors
    async def complete(self, prompt: str, **kwargs) -> str:
        """Text completion"""
        messages = [Message(role=MessageRole.USER, content=prompt)]
        response = await self.chat(messages, **kwargs)
        return response.content
    
    @handle_llm_errors
    async def embed(self, text: str, **kwargs) -> EmbeddingResponse:
        """Text embedding (Claude does not support, placeholder)"""
        raise NotImplementedError("Claude does not support embedding functionality")
    
    @handle_llm_errors
    async def embed_batch(self, texts: List[str], **kwargs) -> List[EmbeddingResponse]:
        """Batch text embedding (Claude does not support)"""
        raise NotImplementedError("Claude does not support embedding functionality")
    
    @handle_llm_errors
    async def summarize(self, text: str, **kwargs) -> str:
        """Text summarization"""
        max_length = kwargs.get("max_length", 200)
        language = kwargs.get("language", "English")
        
        # Use prompt manager
        from timem.utils.prompt_manager import get_prompt_manager
        
        prompt_manager = get_prompt_manager()
        prompt_template = prompt_manager.get_prompt("general_text_summary")
        
        if not prompt_template:
            # If prompt not found, fallback to default implementation
            system_prompt = f"""You are a professional text summarization assistant. Please summarize the following text with requirements:
1. Keep length within {max_length} characters
2. Retain key information and core viewpoints
3. Maintain logical clarity and coherence"""
        
        user_prompt = f"Please summarize the following text:\n\n{text}"
        
        messages = self.format_chat_prompt(system_prompt, user_prompt)
        response = await self.chat(messages, **kwargs)
        
        return response.content
    
    async def validate_model(self, model_name: str) -> bool:
        """Validate if model is available"""
        return model_name in self.supported_models
    
    async def get_model_info(self, model_name: str) -> Dict[str, Any]:
        """Get model information"""
        if model_name in self.chat_models:
            return {
                "model": model_name,
                "provider": "anthropic",
                "type": "chat",
                **self.chat_models[model_name]
            }
        else:
            return {"error": f"Unsupported model: {model_name}"}