"""




Directly writes prompts to files, not resident in memory
Used for prompt collection in single tests
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any
import threading


class FilePromptCollector:
    """
    File Prompt Collector (thread-safe)
    
    Features:
    - Directly writes prompts to JSON files
    - Not resident in memory
    - Supports real-time appending
    """
    
    def __init__(self, output_file: str, enabled: bool = True):
        self.enabled = enabled
        self.output_file = Path(output_file)
        self._lock = threading.Lock()
        self._counter = 0
        
        # Ensure output directory exists
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        
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
        Record chat format prompt and write directly to file
        
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
            
            record = {
                "record_id": record_id,
                "timestamp": datetime.now().isoformat(),
                "model": model,
                "prompt_type": "chat",
                "messages": messages,
                "prompt_tokens": prompt_tokens,
                "memory_level": memory_level,
                "trigger_type": trigger_type,
                "conversation_id": conversation_id,
                "session_id": session_id,
                "turn_id": turn_id,
                "metadata": metadata
            }
            
            # Write directly to file (append mode)
            self._write_to_file(record)
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
        Record completion format prompt and write directly to file
        
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
            
            record = {
                "record_id": record_id,
                "timestamp": datetime.now().isoformat(),
                "model": model,
                "prompt_type": "completion",
                "prompt": prompt,
                "prompt_tokens": prompt_tokens,
                "memory_level": memory_level,
                "trigger_type": trigger_type,
                "conversation_id": conversation_id,
                "session_id": session_id,
                "turn_id": turn_id,
                "metadata": metadata
            }
            
            # Write directly to file (append mode)
            self._write_to_file(record)
            return record_id
    
    def _write_to_file(self, record: Dict[str, Any]):
        """Write record to file (append mode)"""
        try:
            # Write in JSON Lines format using append mode
            with open(self.output_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')
        except Exception as e:
            print(f"Warning: Failed to write prompt file: {e}")
    
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
    
    def get_file_stats(self) -> Dict[str, Any]:
        """Get file statistics"""
        try:
            if not self.output_file.exists():
                return {
                    "file_exists": False,
                    "total_prompts": 0,
                    "file_size_bytes": 0
                }
            
            # Read file statistics
            total_prompts = 0
            total_tokens = 0
            
            with open(self.output_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        try:
                            record = json.loads(line)
                            total_prompts += 1
                            total_tokens += record.get("prompt_tokens", 0)
                        except json.JSONDecodeError:
                            continue
            
            return {
                "file_exists": True,
                "total_prompts": total_prompts,
                "total_prompt_tokens": total_tokens,
                "file_size_bytes": self.output_file.stat().st_size,
                "tiktoken_used": self._tiktoken_available
            }
        except Exception as e:
            return {
                "file_exists": False,
                "error": str(e),
                "total_prompts": 0
            }
    
    def export_to_readable_format(self, output_file: str):
        """Export to readable format"""
        try:
            if not self.output_file.exists():
                return
            
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.output_file, 'r', encoding='utf-8') as f_in, \
                 open(output_path, 'w', encoding='utf-8') as f_out:
                
                f_out.write("=" * 80 + "\n")
                f_out.write("LLM Prompt Collection Report\n")
                f_out.write("=" * 80 + "\n")
                f_out.write(f"Generated at: {datetime.now().isoformat()}\n")
                f_out.write(f"Source file: {self.output_file}\n")
                f_out.write(f"Tiktoken available: {self._tiktoken_available}\n\n")
                
                for i, line in enumerate(f_in, 1):
                    if line.strip():
                        try:
                            record = json.loads(line)
                            
                            f_out.write(f"\n{'='*80}\n")
                            f_out.write(f"Prompt #{i}\n")
                            f_out.write(f"{'='*80}\n")
                            f_out.write(f"ID: {record.get('record_id', 'N/A')}\n")
                            f_out.write(f"Time: {record.get('timestamp', 'N/A')}\n")
                            f_out.write(f"Model: {record.get('model', 'N/A')}\n")
                            f_out.write(f"Type: {record.get('prompt_type', 'N/A')}\n")
                            f_out.write(f"Tokens: {record.get('prompt_tokens', 0)}\n")
                            f_out.write(f"Level: {record.get('memory_level', 'N/A')}\n")
                            f_out.write(f"Trigger: {record.get('trigger_type', 'N/A')}\n")
                            f_out.write(f"\nContent:\n")
                            f_out.write("-" * 80 + "\n")
                            
                            if record.get('prompt_type') == 'chat':
                                for msg in record.get('messages', []):
                                    f_out.write(f"\n[{msg.get('role', 'unknown')}]\n")
                                    f_out.write(msg.get('content', ''))
                                    f_out.write("\n")
                            else:
                                f_out.write(record.get('prompt', ''))
                            
                            f_out.write("\n")
                            
                        except json.JSONDecodeError:
                            continue
                
                f_out.write(f"\n{'='*80}\n")
                f_out.write("Report End\n")
                f_out.write(f"{'='*80}\n")
                
        except Exception as e:
            print(f"Warning: Failed to export readable format: {e}")


# Global singleton
_global_file_prompt_collector: Optional[FilePromptCollector] = None


def get_file_prompt_collector(output_file: str = None, enabled: bool = True) -> FilePromptCollector:
    """Get global file prompt collector"""
    global _global_file_prompt_collector
    if _global_file_prompt_collector is None or (output_file and _global_file_prompt_collector.output_file != Path(output_file)):
        if output_file is None:
            output_file = f"logs/prompts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        _global_file_prompt_collector = FilePromptCollector(output_file, enabled)
    return _global_file_prompt_collector


def enable_file_prompt_collection(output_file: str = None):
    """Enable file prompt collection"""
    collector = get_file_prompt_collector(output_file)
    collector.enabled = True


def disable_file_prompt_collection():
    """Disable file prompt collection"""
    collector = get_file_prompt_collector()
    collector.enabled = False
