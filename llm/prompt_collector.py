"""
LLM Prompt Collector

Collects prompt information from LLM calls for:
1. Accurately calculate input token count (using tiktoken)
2. Save prompts for debugging and analysis
3. Generate statistical reports
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict
import threading


@dataclass
class PromptRecord:
    """Prompt record"""
    record_id: str
    timestamp: str
    model: str
    prompt_type: str  # "chat" or "completion"
    messages: Optional[List[Dict[str, str]]] = None  # for chat
    prompt: Optional[str] = None  # for completion
    prompt_tokens: int = 0  # Accurately calculated token count
    memory_level: Optional[str] = None
    trigger_type: Optional[str] = None
    conversation_id: Optional[str] = None
    session_id: Optional[str] = None
    turn_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class PromptCollector:
    """
    Prompt Collector (thread-safe)
    
    Features:
    - Collect prompts from all LLM calls
    - Use tiktoken to accurately calculate input tokens
    - Save to JSON file
    - Generate statistical reports
    """
    
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.prompts: List[PromptRecord] = []
        self._lock = threading.Lock()
        self._counter = 0
        
        # Try to import tiktoken
        self._tiktoken_available = False
        try:
            import tiktoken
            self._tiktoken = tiktoken
            self._tiktoken_available = True
            self._encodings = {}  # Cache encoders
        except ImportError:
            self._tiktoken = None
    
    def record_chat_prompt(
        self,
        messages: List[Dict[str, str]],
        model: str = "gpt-4",
        memory_level: Optional[str] = None,
        trigger_type: Optional[str] = None,
        conversation_id: Optional[str] = None,
        session_id: Optional[str] = None,
        turn_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Record chat format prompt
        
        Returns:
            record_id: Record ID
        """
        if not self.enabled:
            return ""
        
        with self._lock:
            self._counter += 1
            record_id = f"prompt_{self._counter}_{int(time.time()*1000)}"
            
            # Calculate input token count
            prompt_tokens = self._count_tokens_for_messages(messages, model)
            
            record = PromptRecord(
                record_id=record_id,
                timestamp=datetime.now().isoformat(),
                model=model,
                prompt_type="chat",
                messages=messages,
                prompt_tokens=prompt_tokens,
                memory_level=memory_level,
                trigger_type=trigger_type,
                conversation_id=conversation_id,
                session_id=session_id,
                turn_id=turn_id,
                metadata=metadata
            )
            
            # Save to memory
            self.prompts.append(record)
            return record_id
    
    def record_completion_prompt(
        self,
        prompt: str,
        model: str = "gpt-4",
        memory_level: Optional[str] = None,
        trigger_type: Optional[str] = None,
        conversation_id: Optional[str] = None,
        session_id: Optional[str] = None,
        turn_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Record completion format prompt
        
        Returns:
            record_id: Record ID
        """
        if not self.enabled:
            return ""
        
        with self._lock:
            self._counter += 1
            record_id = f"prompt_{self._counter}_{int(time.time()*1000)}"
            
            # Calculate input token count
            prompt_tokens = self._count_tokens(prompt, model)
            
            record = PromptRecord(
                record_id=record_id,
                timestamp=datetime.now().isoformat(),
                model=model,
                prompt_type="completion",
                prompt=prompt,
                prompt_tokens=prompt_tokens,
                memory_level=memory_level,
                trigger_type=trigger_type,
                conversation_id=conversation_id,
                session_id=session_id,
                turn_id=turn_id,
                metadata=metadata
            )
            
            self.prompts.append(record)
            return record_id
    
    def _get_encoding(self, model: str):
        """Get or cache encoder"""
        if not self._tiktoken_available:
            return None
        
        if model in self._encodings:
            return self._encodings[model]
        
        try:
            encoding = self._tiktoken.encoding_for_model(model)
        except KeyError:
            # Model not supported, use default encoding
            encoding = self._tiktoken.get_encoding("cl100k_base")
        
        self._encodings[model] = encoding
        return encoding
    
    def _count_tokens(self, text: str, model: str) -> int:
        """Use tiktoken to accurately calculate token count"""
        if not self._tiktoken_available:
            # Fallback to estimation
            return self._estimate_tokens(text)
        
        try:
            encoding = self._get_encoding(model)
            return len(encoding.encode(text))
        except Exception:
            return self._estimate_tokens(text)
    
    def _count_tokens_for_messages(
        self,
        messages: List[Dict[str, str]],
        model: str
    ) -> int:
        """
        Accurately calculate token count for messages
        
        Reference: https://github.com/openai/openai-cookbook/blob/main/examples/How_to_count_tokens_with_tiktoken.ipynb
        """
        if not self._tiktoken_available:
            # Fallback to estimation
            total = sum(self._estimate_tokens(m.get("content", "")) for m in messages)
            return total + len(messages) * 4
        
        try:
            encoding = self._get_encoding(model)
            
            # Choose counting method based on model
            if model in ["gpt-3.5-turbo", "gpt-3.5-turbo-0613", 
                         "gpt-3.5-turbo-16k", "gpt-3.5-turbo-0125"]:
                tokens_per_message = 4
                tokens_per_name = -1
            elif model.startswith("gpt-4"):
                tokens_per_message = 3
                tokens_per_name = 1
            else:
                tokens_per_message = 4
                tokens_per_name = -1
            
            num_tokens = 0
            for message in messages:
                num_tokens += tokens_per_message
                for key, value in message.items():
                    num_tokens += len(encoding.encode(str(value)))
                    if key == "name":
                        num_tokens += tokens_per_name
            
            num_tokens += 3  # Each reply starts with assistant
            
            return num_tokens
            
        except Exception:
            # Fallback on error
            total = sum(self._estimate_tokens(m.get("content", "")) for m in messages)
            return total + len(messages) * 4
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count (fallback method)"""
        if not text:
            return 0
        
        import re
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        other_chars = len(text) - chinese_chars
        
        # Chinese: ~1.5 chars/token, English: ~4 chars/token
        estimated_tokens = int(chinese_chars / 1.5 + other_chars / 4)
        return max(estimated_tokens, 1)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics"""
        with self._lock:
            if not self.prompts:
                return {
                    "total_prompts": 0,
                    "total_prompt_tokens": 0,
                    "tiktoken_used": self._tiktoken_available
                }
            
            total_tokens = sum(p.prompt_tokens for p in self.prompts)
            avg_tokens = total_tokens / len(self.prompts) if self.prompts else 0
            
            # Statistics by level
            by_level = {}
            for prompt in self.prompts:
                level = prompt.memory_level or "unknown"
                if level not in by_level:
                    by_level[level] = {"count": 0, "tokens": 0}
                by_level[level]["count"] += 1
                by_level[level]["tokens"] += prompt.prompt_tokens
            
            # Statistics by trigger type
            by_trigger = {}
            for prompt in self.prompts:
                trigger = prompt.trigger_type or "unknown"
                if trigger not in by_trigger:
                    by_trigger[trigger] = {"count": 0, "tokens": 0}
                by_trigger[trigger]["count"] += 1
                by_trigger[trigger]["tokens"] += prompt.prompt_tokens
            
            return {
                "total_prompts": len(self.prompts),
                "total_prompt_tokens": total_tokens,
                "avg_prompt_tokens": avg_tokens,
                "max_prompt_tokens": max(p.prompt_tokens for p in self.prompts),
                "min_prompt_tokens": min(p.prompt_tokens for p in self.prompts),
                "tiktoken_used": self._tiktoken_available,
                "by_level": by_level,
                "by_trigger": by_trigger
            }
    
    def export_to_json(self, filepath: str, include_content: bool = True):
        """
        Export to JSON file
        
        Args:
            filepath: Output file path
            include_content: Whether to include complete prompt content
        """
        with self._lock:
            data = {
                "meta": {
                    "export_time": datetime.now().isoformat(),
                    "total_prompts": len(self.prompts),
                    "tiktoken_available": self._tiktoken_available,
                },
                "statistics": self.get_statistics(),
                "prompts": []
            }
            
            for prompt in self.prompts:
                prompt_dict = asdict(prompt)
                
                # If not including content, remove messages and prompt fields
                if not include_content:
                    prompt_dict.pop("messages", None)
                    prompt_dict.pop("prompt", None)
                
                data["prompts"].append(prompt_dict)
            
            Path(filepath).parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
    
    def export_prompts_only(self, filepath: str):
        """
        Export only prompt content (for debugging and analysis)
        
        Format: one prompt per file, or merged into one file
        """
        with self._lock:
            output = []
            
            for i, prompt in enumerate(self.prompts, 1):
                output.append(f"\n{'='*80}")
                output.append(f"Prompt #{i}")
                output.append(f"{'='*80}")
                output.append(f"ID: {prompt.record_id}")
                output.append(f"Time: {prompt.timestamp}")
                output.append(f"Model: {prompt.model}")
                output.append(f"Type: {prompt.prompt_type}")
                output.append(f"Tokens: {prompt.prompt_tokens}")
                output.append(f"Level: {prompt.memory_level or 'N/A'}")
                output.append(f"Trigger: {prompt.trigger_type or 'N/A'}")
                output.append(f"\nContent:")
                output.append("-" * 80)
                
                if prompt.prompt_type == "chat":
                    for msg in prompt.messages:
                        output.append(f"\n[{msg['role']}]")
                        output.append(msg['content'])
                else:
                    output.append(prompt.prompt)
                
                output.append("")
            
            Path(filepath).parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write('\n'.join(output))
    
    def clear(self):
        """Clear collected data"""
        with self._lock:
            self.prompts.clear()
            self._counter = 0
    
    def get_prompt_by_id(self, record_id: str) -> Optional[PromptRecord]:
        """Get prompt record by ID"""
        with self._lock:
            for prompt in self.prompts:
                if prompt.record_id == record_id:
                    return prompt
        return None


# Global singleton
_global_prompt_collector: Optional[PromptCollector] = None


def get_prompt_collector(enabled: bool = True) -> PromptCollector:
    """Get global prompt collector"""
    global _global_prompt_collector
    if _global_prompt_collector is None:
        _global_prompt_collector = PromptCollector(enabled=enabled)
    return _global_prompt_collector


def enable_prompt_collection():
    """Enable prompt collection"""
    collector = get_prompt_collector()
    collector.enabled = True


def disable_prompt_collection():
    """Disable prompt collection"""
    collector = get_prompt_collector()
    collector.enabled = False

