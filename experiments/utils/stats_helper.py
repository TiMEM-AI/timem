"""
Test Statistics Helper Module

For integrating statistics collection in test_memory_generation_realistic_sim.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from datetime import datetime
from typing import Dict, Any, List, Optional
import uuid

from timem.utils.stats_collector import (
    ComprehensiveStatsCollector,
    LLMCallStats,
    MemoryGenerationStats,
    TurnProcessingStats,
    SessionProcessingStats,
    DayProcessingStats,
    ProcessingPhaseStats,
    MemoryLevel,
    TriggerType,
    ErrorType,
    extract_token_info_from_chat_response,
    estimate_llm_cost,
    count_chinese_words,
    count_tokens_estimate
)
from timem.utils.logging import get_logger

logger = get_logger(__name__)


class StatsTestHelper:
    """Test statistics helper class"""
    
    def __init__(self, stats_collector: ComprehensiveStatsCollector):
        self.collector = stats_collector
        self.current_phases: Dict[str, List[ProcessingPhaseStats]] = {}  # turn_id -> phases
        self.current_turn_start_times: Dict[str, float] = {}  # turn_id -> start_time
    
    def parse_memory_level(self, level_str: str) -> MemoryLevel:
        """Parse memory level"""
        if not level_str:
            return MemoryLevel.L1
        
        level_str = str(level_str).upper()
        if "L1" in level_str or "FRAGMENT" in level_str:
            return MemoryLevel.L1
        elif "L2" in level_str or "SESSION" in level_str:
            return MemoryLevel.L2
        elif "L3" in level_str or "DAILY" in level_str:
            return MemoryLevel.L3
        elif "L4" in level_str or "WEEKLY" in level_str:
            return MemoryLevel.L4
        elif "L5" in level_str or "MONTHLY" in level_str:
            return MemoryLevel.L5
        else:
            return MemoryLevel.L1
    
    def parse_trigger_type(self, trigger_str: str) -> TriggerType:
        """Parse trigger type"""
        if not trigger_str:
            return TriggerType.REALTIME
        
        trigger_str = str(trigger_str).lower()
        if "realtime" in trigger_str:
            return TriggerType.REALTIME
        elif "inter_session" in trigger_str or "inter-session" in trigger_str:
            return TriggerType.INTER_SESSION
        elif "daily" in trigger_str:
            return TriggerType.DAILY_BACKFILL
        elif "force" in trigger_str:
            return TriggerType.FORCE_BACKFILL
        else:
            return TriggerType.MANUAL
    
    def _detect_model_name(self) -> str:
        """
        Auto-detect LLM model name
        
        Priority:
        1. Environment variable LLM_MODEL
        2. Default value gpt-4o-mini
        """
        import os
        
        # Try to get from environment variable
        model_from_env = os.environ.get("LLM_MODEL") or os.environ.get("DEFAULT_LLM_MODEL")
        if model_from_env:
            return model_from_env
        
        # Return default value (mainstream OpenAI model)
        return "gpt-4o-mini"
    
    def extract_memories_from_result(self, result) -> List[Dict[str, Any]]:
        """Extract memory list from result"""
        memories = []
        
        # Try multiple ways to get memories
        if hasattr(result, 'memories'):
            memories_raw = result.memories
        elif isinstance(result, dict):
            memories_raw = result.get('memories', result.get('generated_memories', []))
        else:
            return []
        
        # Ensure it's a list
        if not isinstance(memories_raw, list):
            memories_raw = [memories_raw] if memories_raw else []
        
        # Convert to list of dictionaries
        for mem in memories_raw:
            if isinstance(mem, dict):
                memories.append(mem)
            elif hasattr(mem, '__dict__'):
                memories.append(vars(mem))
            else:
                # Try to convert
                try:
                    mem_dict = {
                        'id': getattr(mem, 'id', None) or getattr(mem, 'memory_id', str(uuid.uuid4())),
                        'level': getattr(mem, 'level', None),
                        'content': getattr(mem, 'content', ''),
                    }
                    memories.append(mem_dict)
                except Exception as e:
                    logger.warning(f"Unable to convert memory object: {e}")
        
        return memories
    
    def record_memories_from_result(
        self, 
        result, 
        trigger_type: str = "realtime_generation",
        turn_id: Optional[str] = None,
        estimate_llm_calls: bool = True,
        model_name: Optional[str] = None
    ) -> List[str]:
        """
        Extract and record memory statistics from result
        
        Args:
            result: Result returned by service
            trigger_type: Trigger type
            turn_id: Turn ID
            estimate_llm_calls: Whether to estimate LLM call statistics (when real data unavailable)
            model_name: LLM model name (auto-detect if None)
        
        Returns:
            List of generated memory IDs
        """
        memories = self.extract_memories_from_result(result)
        memory_ids = []
        
        trigger = self.parse_trigger_type(trigger_type)
        timestamp = datetime.now()
        
        # 🆕 If model_name is not specified, try to get from environment variable or config
        if model_name is None:
            model_name = self._detect_model_name()
        
        for mem in memories:
            try:
                # Extract basic information
                memory_id = str(mem.get('id', uuid.uuid4()))
                memory_ids.append(memory_id)
                
                # Extract memory level
                level_raw = mem.get('level', 'L1')
                if hasattr(level_raw, 'value'):
                    level_str = level_raw.value
                else:
                    level_str = str(level_raw)
                memory_level = self.parse_memory_level(level_str)
                
                # Extract content
                content = mem.get('content', '')
                
                # Create statistics record
                memory_stats = MemoryGenerationStats(
                    memory_id=memory_id,
                    memory_level=memory_level,
                    timestamp=timestamp,
                    trigger_type=trigger,
                    content_length_chars=len(content),
                    content_length_words=count_chinese_words(content),
                    content_length_tokens=count_tokens_estimate(content),
                    importance_score=mem.get('importance_score'),
                    parent_count=len(mem.get('parent_ids', [])),
                    child_count=len(mem.get('child_ids', [])),
                )
                
                self.collector.record_memory_generation(memory_stats)
                
                # 🆕 Use tiktoken to calculate LLM call statistics (if enabled)
                if estimate_llm_calls and content:
                    self._estimate_and_record_llm_call(
                        memory_id=memory_id,
                        memory_level=memory_level,
                        trigger=trigger,
                        content=content,
                        timestamp=timestamp,
                        model_name=model_name  # 🔧 Use detected model name
                    )
                
            except Exception as e:
                logger.warning(f"Failed to record memory statistics: {e}")
        
        return memory_ids
    
    def _estimate_and_record_llm_call(
        self,
        memory_id: str,
        memory_level: MemoryLevel,
        trigger: TriggerType,
        content: str,
        timestamp: datetime,
        model_name: str = "gpt-4o-mini",  # 🔧 Changed default to gpt-4o-mini
        actual_prompt_tokens: int = None
    ):
        """
        Use tiktoken to accurately calculate and record LLM call statistics
        
        - For output tokens: use tiktoken for accurate calculation (99% accurate for OpenAI models, estimated for others)
        - For input tokens: read from prompt file with tiktoken accurate calculation
        - For latency and cost: estimated based on token count
        """
        from timem.utils.stats_collector import (
            LLMCallStats,
            estimate_llm_cost
        )
        from timem.utils.token_counter import count_tokens
        import time
        
        # 🆕 Use tiktoken for accurate output token calculation
        # OpenAI models: 99% accurate
        # Other models: 70-85% accurate (estimated)
        completion_tokens = count_tokens(content, model=model_name)
        
        # 🆕 Use actual input tokens (read from prompt file)
        # If not provided, temporarily set to 0, will be updated in batch from prompt file later
        prompt_tokens = actual_prompt_tokens if actual_prompt_tokens is not None else 0
        total_tokens = prompt_tokens + completion_tokens
        
        # Estimate latency (based on token count, assuming 20 tokens/s)
        estimated_latency_ms = (total_tokens / 20.0) * 1000
        
        # Estimate cost
        cost = estimate_llm_cost(prompt_tokens, completion_tokens, model_name)
        
        # Create LLM call statistics record
        call_stats = LLMCallStats(
            call_id=f"estimated_{memory_id}",
            timestamp=timestamp,
            memory_level=memory_level,
            trigger_type=trigger,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=estimated_latency_ms,
            tokens_per_second=completion_tokens / (estimated_latency_ms / 1000) if estimated_latency_ms > 0 else 0,
            success=True,
            model_name=model_name,
            estimated_cost_usd=cost
        )
        
        self.collector.record_llm_call(call_stats)
    
    def update_tokens_from_prompt_file(self, prompt_file: str):
        """
        Read actual token count from prompt file and update statistics
        
        This method will:
        1. Read all records from prompt file
        2. Group by memory_level and trigger_type
        3. Update LLM call statistics in collector, replacing estimated values with actual token counts
        """
        import json
        from pathlib import Path
        from timem.models.memory import MemoryLevel
        from timem.utils.stats_collector import TriggerType
        
        prompt_file_path = Path(prompt_file)
        if not prompt_file_path.exists():
            logger.warning(f"Prompt file does not exist: {prompt_file}")
            return
        
        # Read prompt file and group by level and trigger type
        prompt_tokens_by_level_trigger = {}
        prompt_model_by_level_trigger = {}  # 🆕 Record model name for each level/trigger type
        total_prompts = 0
        detected_models = set()  # 🆕 Collect all detected model names
        
        try:
            with open(prompt_file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if not line.strip():
                        continue
                    
                    try:
                        record = json.loads(line)
                        memory_level = record.get('memory_level')
                        trigger_type = record.get('trigger_type')
                        prompt_tokens = record.get('prompt_tokens', 0)
                        model = record.get('model', 'gpt-4o-mini')  # 🆕 Extract model name
                        
                        detected_models.add(model)
                        
                        if memory_level and trigger_type:
                            key = (memory_level, trigger_type)
                            if key not in prompt_tokens_by_level_trigger:
                                prompt_tokens_by_level_trigger[key] = []
                                prompt_model_by_level_trigger[key] = model  # 🆕 Record first model
                            prompt_tokens_by_level_trigger[key].append(prompt_tokens)
                            total_prompts += 1
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse prompt record: {e}")
                        continue
            
            logger.info(f"✅ Read {total_prompts} records from prompt file")
            if detected_models:
                logger.info(f"🔍 Detected models: {', '.join(detected_models)}")
            
            # Update LLM call statistics in collector
            updated_count = 0
            model_updated_count = 0  # 🆕 Count model name updates
            for call_stats in self.collector.llm_calls:
                memory_level_str = call_stats.memory_level.value if hasattr(call_stats.memory_level, 'value') else str(call_stats.memory_level)
                trigger_type_str = call_stats.trigger_type.value if hasattr(call_stats.trigger_type, 'value') else str(call_stats.trigger_type)
                
                # Try to match
                key = (memory_level_str, trigger_type_str)
                if key in prompt_tokens_by_level_trigger and prompt_tokens_by_level_trigger[key]:
                    # Use first prompt token count for this level and trigger type (FIFO)
                    actual_prompt_tokens = prompt_tokens_by_level_trigger[key].pop(0)
                    
                    # 🆕 Update model name (if different)
                    actual_model = prompt_model_by_level_trigger.get(key, call_stats.model_name)
                    if actual_model != call_stats.model_name:
                        logger.debug(f"Update model name: {call_stats.model_name} -> {actual_model}")
                        call_stats.model_name = actual_model
                        model_updated_count += 1
                    
                    # Update statistics
                    call_stats.prompt_tokens = actual_prompt_tokens
                    call_stats.total_tokens = actual_prompt_tokens + call_stats.completion_tokens
                    
                    # 🔧 Recalculate cost (using updated model name)
                    from timem.utils.stats_collector import estimate_llm_cost
                    call_stats.estimated_cost_usd = estimate_llm_cost(
                        actual_prompt_tokens,
                        call_stats.completion_tokens,
                        call_stats.model_name  # Use updated model name
                    )
                    
                    updated_count += 1
            
            logger.info(f"✅ Updated {updated_count} LLM call statistics with actual input tokens")
            if model_updated_count > 0:
                logger.info(f"✅ Updated {model_updated_count} LLM call statistics with model names")
            
            # Recalculate global statistics
            self.collector._update_global_counters()
            
        except Exception as e:
            logger.error(f"Failed to update token statistics from prompt file: {e}")
            import traceback
            traceback.print_exc()
    
    def start_turn_processing(self, turn_id: str):
        """Start recording turn processing"""
        import time
        self.current_turn_start_times[turn_id] = time.perf_counter()
        self.current_phases[turn_id] = []
    
    def end_turn_processing(
        self,
        turn_id: str,
        session_id: str,
        generated_memory_ids: List[str],
        success: bool = True
    ):
        """End turn processing and record statistics"""
        import time
        
        if turn_id not in self.current_turn_start_times:
            logger.warning(f"Start time not found for turn {turn_id}")
            return
        
        end_time = time.perf_counter()
        start_time = self.current_turn_start_times[turn_id]
        total_time_ms = (end_time - start_time) * 1000
        
        phases = self.current_phases.get(turn_id, [])
        
        turn_stats = TurnProcessingStats(
            turn_id=turn_id,
            session_id=session_id,
            timestamp=datetime.now(),
            total_time_ms=total_time_ms,
            success=success,
            phases=phases,
            generated_memories=generated_memory_ids,
        )
        
        self.collector.record_turn_processing(turn_stats)
        
        # Cleanup
        del self.current_turn_start_times[turn_id]
        if turn_id in self.current_phases:
            del self.current_phases[turn_id]
    
    def record_day_stats(
        self,
        date,
        has_sessions: bool = False,
        sessions_count: int = 0,
        turns_count: int = 0,
        daily_backfill_triggered: bool = False,
        inter_session_backfill_count: int = 0,
        l1_generated: int = 0,
        l2_generated: int = 0,
        l3_generated: int = 0,
        l4_generated: int = 0,
        l5_generated: int = 0,
        total_processing_time_ms: float = 0.0,
        sessions: List[str] = None
    ):
        """Record daily statistics"""
        day_stats = DayProcessingStats(
            date=date,
            has_sessions=has_sessions,
            sessions_count=sessions_count,
            turns_count=turns_count,
            daily_backfill_triggered=daily_backfill_triggered,
            inter_session_backfill_count=inter_session_backfill_count,
            l1_generated=l1_generated,
            l2_generated=l2_generated,
            l3_generated=l3_generated,
            l4_generated=l4_generated,
            l5_generated=l5_generated,
            total_processing_time_ms=total_processing_time_ms,
            sessions=sessions or []
        )
        
        self.collector.record_day_processing(day_stats)
    
    def print_summary(self, detailed: bool = True):
        """Print statistics summary"""
        summary = self.collector.get_comprehensive_summary()
        
        print("\n" + "="*80)
        print("📊 Memory Generation Statistics Summary")
        print("="*80)
        
        # Global counters
        counters = summary['global_counters']
        print(f"\n📈 Basic Statistics:")
        print(f"  Total sessions: {counters['total_sessions']}")
        print(f"  Total conversation turns: {counters['total_turns']}")
        print(f"  Total days: {counters['total_days']}")
        
        print(f"\n💾 Memory Generation Statistics:")
        print(f"  L1 memories: {counters['total_memories_l1']} items")
        print(f"  L2 memories: {counters['total_memories_l2']} items")
        print(f"  L3 memories: {counters['total_memories_l3']} items")
        print(f"  L4 memories: {counters['total_memories_l4']} items")
        print(f"  L5 memories: {counters['total_memories_l5']} items")
        print(f"  Total: {counters['total_memories_generated']} items")
        
        # Token statistics
        token_stats = summary['llm_token_stats']
        
        # Check if tiktoken is available
        try:
            from timem.utils.token_counter import get_token_counter
            counter = get_token_counter()
            tiktoken_available = counter._tiktoken_available
        except:
            tiktoken_available = False
        
        print(f"\n🎯 Token Statistics:")
        if tiktoken_available:
            print(f"  ✅ Using tiktoken for accurate calculation (99% accurate for OpenAI models, estimated for others)")
            print(f"  ✅ Input tokens read from prompt file (tiktoken accurate calculation)")
            print(f"  ✅ Output tokens using tiktoken accurate calculation")
        else:
            print(f"  ⚠️  Using estimation method (tiktoken not installed)")
        
        print(f"  Total calls: {token_stats.get('total_calls', 0)}")
        print(f"  Successful calls: {token_stats.get('successful_calls', 0)}")
        print(f"  Failed calls: {token_stats.get('failed_calls', 0)}")
        print(f"  Total tokens: {token_stats.get('total_tokens', 0):,}")
        print(f"  Input tokens: {token_stats.get('total_prompt_tokens', 0):,} {'(tiktoken accurate)' if tiktoken_available else '(estimated)'}")
        print(f"  Output tokens: {token_stats.get('total_completion_tokens', 0):,} {'(tiktoken accurate)' if tiktoken_available else '(estimated)'}")
        print(f"  Average tokens per call: {token_stats.get('avg_total_tokens', 0):.1f}")
        
        # Latency statistics
        latency_stats = summary['llm_latency_stats']
        if latency_stats.get('total_calls', 0) > 0:
            print(f"\n⏱️ Latency Statistics (estimated values):")
            print(f"  Average latency: {latency_stats.get('avg_latency_ms', 0):.1f} ms")
            print(f"  Median latency: {latency_stats.get('median_latency_ms', 0):.1f} ms")
            print(f"  P95 latency: {latency_stats.get('p95_latency_ms', 0):.1f} ms")
            print(f"  P99 latency: {latency_stats.get('p99_latency_ms', 0):.1f} ms")
            print(f"  Max latency: {latency_stats.get('max_latency_ms', 0):.1f} ms")
            if latency_stats.get('avg_tokens_per_second'):
                print(f"  Average generation speed: {latency_stats.get('avg_tokens_per_second', 0):.1f} tokens/s")
        
        # Cost statistics
        cost_stats = summary['cost_analysis']
        print(f"\n💰 Cost Statistics (estimated values, based on glm-4-flash pricing):")
        print(f"  Total cost: ${cost_stats.get('total_cost_usd', 0):.4f}")
        print(f"  Cost per memory: ${cost_stats.get('cost_per_memory', 0):.6f}")
        print(f"  Cost per turn: ${cost_stats.get('cost_per_turn', 0):.6f}")
        
        # Throughput statistics
        throughput_stats = summary['throughput_stats']
        total_time = throughput_stats.get('total_time_seconds', 0)
        if total_time > 0:
            print(f"\n🚀 Throughput Statistics:")
            print(f"  Total execution time: {total_time:.2f} seconds ({total_time/60:.2f} minutes)")
            print(f"  Conversation processing speed: {throughput_stats.get('turns_per_second', 0):.2f} turns/second")
            print(f"  Memory generation speed: {throughput_stats.get('memories_per_second', 0):.2f} items/second")
            print(f"  Token processing speed: {throughput_stats.get('tokens_per_second', 0):.1f} tokens/second")
        
        # Error statistics
        error_stats = summary['error_stats']
        if error_stats.get('total_errors', 0) > 0:
            print(f"\n❌ Error Statistics:")
            print(f"  Total errors: {error_stats['total_errors']}")
            print(f"  Error rate: {error_stats.get('error_rate', 0)*100:.2f}%")
            for error_type, count in error_stats.get('errors_by_type', {}).items():
                print(f"  - {error_type}: {count}")
        
        # Detailed token statistics by level
        if detailed and 'by_level' in token_stats:
            print(f"\n📊 Token Statistics by Level:")
            for level, level_stats in token_stats['by_level'].items():
                print(f"  {level}:")
                print(f"    Calls: {level_stats.get('calls', 0)}")
                print(f"    Total tokens: {level_stats.get('total_tokens', 0):,}")
                print(f"    Average tokens: {level_stats.get('avg_tokens', 0):.1f}")
        
        print("="*80 + "\n")
    
    def export_results(self, json_path: str, csv_dir: str):
        """Export statistics results"""
        try:
            self.collector.export_to_json(json_path)
            print(f"✅ JSON statistics exported to: {json_path}")
        except Exception as e:
            logger.error(f"Failed to export JSON: {e}")
        
        try:
            self.collector.export_to_csv(csv_dir)
            print(f"✅ CSV statistics exported to: {csv_dir}")
        except Exception as e:
            logger.error(f"Failed to export CSV: {e}")

