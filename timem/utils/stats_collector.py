"""
Comprehensive Statistics Collector - Academic Research Grade

Collects comprehensive statistics for memory generation systems, supporting:
1. LLM call statistics (tokens, latency, cost)
2. Memory quality statistics (count, length, relationships)
3. Performance statistics (time distribution, bottleneck analysis)
4. Resource consumption statistics (CPU, memory, storage)
5. Error and exception statistics
6. Concurrency and throughput statistics
7. Cost-benefit analysis
"""

import time
import json
import statistics
import uuid
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict, Counter
from dataclasses import dataclass, field, asdict
from enum import Enum

# TiMem project imports
from timem.utils.logging import get_logger

logger = get_logger(__name__)


class MemoryLevel(Enum):
    """Memory levels"""
    L1 = "L1_Fragment_Memory"
    L2 = "L2_Session_Memory"
    L3 = "L3_Daily_Memory"
    L4 = "L4_Weekly_Memory"
    L5 = "L5_Monthly_Memory"


class TriggerType(Enum):
    """Trigger types"""
    REALTIME = "Real-time_Generation"
    INTER_SESSION = "Inter-session_Completion"
    DAILY_BACKFILL = "Daily_Auto_Completion"
    FORCE_BACKFILL = "Force_Completion"
    MANUAL = "Manual_Trigger"


class ErrorType(Enum):
    """Error types"""
    LLM_API_ERROR = "LLM_API_Call_Error"
    LLM_TIMEOUT = "LLM_Timeout"
    LLM_PARSE_ERROR = "LLM_Output_Parse_Error"
    DATABASE_ERROR = "Database_Error"
    VECTOR_DB_ERROR = "Vector_DB_Error"
    NETWORK_ERROR = "Network_Error"
    VALIDATION_ERROR = "Data_Validation_Error"
    UNKNOWN_ERROR = "Unknown_Error"


@dataclass
class LLMCallStats:
    """Single LLM call statistics"""
    call_id: str  # Call ID
    timestamp: datetime  # Call timestamp
    memory_level: MemoryLevel  # Memory level
    trigger_type: TriggerType  # Trigger type
    
    # Token statistics
    prompt_tokens: int = 0  # Input tokens
    completion_tokens: int = 0  # Output tokens
    total_tokens: int = 0  # Total tokens
    
    # Performance statistics
    latency_ms: float = 0.0  # Response latency (milliseconds)
    ttft_ms: Optional[float] = None  # Time to first token (milliseconds)
    tokens_per_second: Optional[float] = None  # Generation speed
    
    # Context statistics
    context_items_count: int = 0  # Retrieved context count
    context_tokens: int = 0  # Context tokens
    context_truncated: bool = False  # Whether truncated
    
    # Result statistics
    success: bool = True  # Whether successful
    retry_count: int = 0  # Retry count
    error_type: Optional[ErrorType] = None  # Error type
    error_message: Optional[str] = None  # Error message
    
    # Model information
    model_name: str = ""  # Model name used
    
    # Cost estimation
    estimated_cost_usd: float = 0.0  # Estimated cost (USD)


@dataclass
class MemoryGenerationStats:
    """Single memory generation statistics"""
    memory_id: str  # Memory ID
    memory_level: MemoryLevel  # Memory level
    timestamp: datetime  # Generation timestamp
    trigger_type: TriggerType  # Trigger type
    
    # Memory content statistics
    content_length_chars: int = 0  # Content character count
    content_length_words: int = 0  # Content word count
    content_length_tokens: Optional[int] = None  # Content token count
    
    # Memory quality
    importance_score: Optional[float] = None  # Importance score
    entities_count: int = 0  # Entity count
    tags_count: int = 0  # Tag count
    
    # Relationship statistics
    parent_count: int = 0  # Parent memory count
    child_count: int = 0  # Child memory count
    historical_relations_count: int = 0  # Historical relations count
    
    # Generation process statistics
    llm_calls_count: int = 1  # LLM call count
    total_generation_time_ms: float = 0.0  # Total generation time (milliseconds)
    
    # Deduplication information
    is_duplicate: bool = False  # Whether duplicate
    duplicate_of: Optional[str] = None  # Duplicate source ID


@dataclass
class ProcessingPhaseStats:
    """Processing phase statistics"""
    phase_name: str  # Phase name
    start_time: float  # Start time
    end_time: float  # End time
    duration_ms: float = 0.0  # Duration (milliseconds)
    success: bool = True  # Whether successful
    error_message: Optional[str] = None  # Error message


@dataclass
class TurnProcessingStats:
    """Single turn dialogue processing statistics"""
    turn_id: str  # Turn ID
    session_id: str  # Session ID
    timestamp: datetime  # Processing timestamp
    
    # Overall statistics
    total_time_ms: float = 0.0  # Total processing time
    success: bool = True  # Whether successful
    
    # Phase-wise time
    phases: List[ProcessingPhaseStats] = field(default_factory=list)
    
    # Generated memories
    generated_memories: List[str] = field(default_factory=list)  # Memory ID list
    
    # LLM calls
    llm_calls: List[str] = field(default_factory=list)  # LLM call ID list


@dataclass
class SessionProcessingStats:
    """Session processing statistics"""
    session_id: str  # Session ID
    start_time: datetime  # Start time
    end_time: Optional[datetime] = None  # End time
    
    # Session basic information
    total_turns: int = 0  # Total turn count
    total_dialogues: int = 0  # Total dialogue count
    
    # Time statistics
    total_processing_time_ms: float = 0.0  # Total processing time
    
    # Generation statistics
    l1_generated: int = 0
    l2_generated: int = 0
    
    # Turn details
    turns: List[str] = field(default_factory=list)  # Turn ID list


@dataclass
class DayProcessingStats:
    """Daily processing statistics"""
    date: date  # Date
    
    # Basic information
    has_sessions: bool = False  # Whether has sessions
    sessions_count: int = 0  # Session count
    turns_count: int = 0  # Dialogue turn count
    
    # Trigger statistics
    daily_backfill_triggered: bool = False  # Whether daily completion triggered
    inter_session_backfill_count: int = 0  # Inter-session completion count
    
    # Generation statistics
    l1_generated: int = 0
    l2_generated: int = 0
    l3_generated: int = 0
    l4_generated: int = 0
    l5_generated: int = 0
    
    # Time statistics
    total_processing_time_ms: float = 0.0
    
    # Session details
    sessions: List[str] = field(default_factory=list)  # Session ID list


@dataclass
class ResourceSnapshot:
    """Resource usage snapshot"""
    timestamp: datetime
    
    # CPU
    cpu_percent: Optional[float] = None  # CPU usage percentage
    
    # Memory
    memory_used_mb: Optional[float] = None  # Memory usage (MB)
    memory_percent: Optional[float] = None  # Memory usage percentage
    
    # Storage
    db_connections: Optional[int] = None  # Database connection count
    vector_db_connections: Optional[int] = None  # Vector DB connection count


class ComprehensiveStatsCollector:
    """Comprehensive statistics collector"""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        """Reset all statistics"""
        # ===== 1. LLM call statistics =====
        self.llm_calls: Dict[str, LLMCallStats] = {}  # call_id -> stats
        self.llm_calls_by_level: Dict[MemoryLevel, List[str]] = defaultdict(list)
        self.llm_calls_by_trigger: Dict[TriggerType, List[str]] = defaultdict(list)
        
        # ===== 2. Memory generation statistics =====
        self.memories: Dict[str, MemoryGenerationStats] = {}  # memory_id -> stats
        self.memories_by_level: Dict[MemoryLevel, List[str]] = defaultdict(list)
        self.memories_by_trigger: Dict[TriggerType, List[str]] = defaultdict(list)
        
        # ===== 3. Processing flow statistics =====
        self.turns: Dict[str, TurnProcessingStats] = {}  # turn_id -> stats
        self.sessions: Dict[str, SessionProcessingStats] = {}  # session_id -> stats
        self.days: Dict[date, DayProcessingStats] = {}  # date -> stats
        
        # ===== 4. Resource statistics =====
        self.resource_snapshots: List[ResourceSnapshot] = []
        
        # ===== 5. Error statistics =====
        self.errors: List[Dict[str, Any]] = []
        self.errors_by_type: Dict[ErrorType, int] = Counter()
        
        # ===== 6. Global counters =====
        self.global_counters = {
            # Basic counters
            "total_conversations": 0,
            "total_sessions": 0,
            "total_turns": 0,
            "total_dialogues": 0,
            "total_days": 0,
            
            # Memory counters
            "total_memories_generated": 0,
            "total_memories_l1": 0,
            "total_memories_l2": 0,
            "total_memories_l3": 0,
            "total_memories_l4": 0,
            "total_memories_l5": 0,
            "total_duplicates": 0,
            
            # Trigger counters
            "realtime_triggers": 0,
            "inter_session_triggers": 0,
            "daily_backfill_triggers": 0,
            "force_backfill_triggers": 0,
            
            # LLM call counters
            "total_llm_calls": 0,
            "total_llm_successes": 0,
            "total_llm_failures": 0,
            "total_llm_retries": 0,
            
            # Token counters
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_tokens": 0,
            
            # Database operation counters
            "total_db_queries": 0,
            "total_db_writes": 0,
            "total_vector_db_queries": 0,
            "total_vector_db_writes": 0,
        }
        
        # ===== 7. Time statistics =====
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        
        # ===== 8. Cost statistics =====
        self.total_cost_usd: float = 0.0
        
    def start_collection(self):
        """Start collecting statistics"""
        self.start_time = time.perf_counter()
    
    def end_collection(self):
        """End collecting statistics"""
        self.end_time = time.perf_counter()
    
    # ===== LLM call statistics methods =====
    
    def record_llm_call(self, call_stats: LLMCallStats):
        """Record LLM call"""
        self.llm_calls[call_stats.call_id] = call_stats
        self.llm_calls_by_level[call_stats.memory_level].append(call_stats.call_id)
        self.llm_calls_by_trigger[call_stats.trigger_type].append(call_stats.call_id)
        
        # Update global counters
        self.global_counters["total_llm_calls"] += 1
        if call_stats.success:
            self.global_counters["total_llm_successes"] += 1
        else:
            self.global_counters["total_llm_failures"] += 1
        self.global_counters["total_llm_retries"] += call_stats.retry_count
        
        # Update token counters
        self.global_counters["total_prompt_tokens"] += call_stats.prompt_tokens
        self.global_counters["total_completion_tokens"] += call_stats.completion_tokens
        self.global_counters["total_tokens"] += call_stats.total_tokens
        
        # Update cost
        self.total_cost_usd += call_stats.estimated_cost_usd
        
        # Record errors
        if not call_stats.success and call_stats.error_type:
            self.errors_by_type[call_stats.error_type] += 1
            self.errors.append({
                "timestamp": call_stats.timestamp,
                "type": call_stats.error_type.value,
                "message": call_stats.error_message,
                "call_id": call_stats.call_id,
                "context": f"{call_stats.memory_level.value} - {call_stats.trigger_type.value}"
            })
    
    # ===== Memory generation statistics methods =====
    
    def record_memory_generation(self, memory_stats: MemoryGenerationStats):
        """Record memory generation"""
        self.memories[memory_stats.memory_id] = memory_stats
        self.memories_by_level[memory_stats.memory_level].append(memory_stats.memory_id)
        self.memories_by_trigger[memory_stats.trigger_type].append(memory_stats.memory_id)
        
        # Update global counters
        self.global_counters["total_memories_generated"] += 1
        level_key = f"total_memories_{memory_stats.memory_level.value.split('_')[0].lower()}"
        self.global_counters[level_key] += 1
        
        if memory_stats.is_duplicate:
            self.global_counters["total_duplicates"] += 1
        
        # Update trigger counters
        trigger_mapping = {
            TriggerType.REALTIME: "realtime_triggers",
            TriggerType.INTER_SESSION: "inter_session_triggers",
            TriggerType.DAILY_BACKFILL: "daily_backfill_triggers",
            TriggerType.FORCE_BACKFILL: "force_backfill_triggers"
        }
        if memory_stats.trigger_type in trigger_mapping:
            self.global_counters[trigger_mapping[memory_stats.trigger_type]] += 1
    
    # ===== Processing flow statistics methods =====
    
    def record_turn_processing(self, turn_stats: TurnProcessingStats):
        """Record dialogue turn processing"""
        self.turns[turn_stats.turn_id] = turn_stats
        self.global_counters["total_turns"] += 1
    
    def record_session_processing(self, session_stats: SessionProcessingStats):
        """Record session processing"""
        self.sessions[session_stats.session_id] = session_stats
        self.global_counters["total_sessions"] += 1
    
    def record_day_processing(self, day_stats: DayProcessingStats):
        """Record daily processing"""
        self.days[day_stats.date] = day_stats
        self.global_counters["total_days"] += 1
    
    # ===== Global counter update methods =====
    
    def _update_global_counters(self):
        """
        Recalculate global counters
        
        When LLM call records are updated (e.g., prompt_tokens from 0 to actual value),
        call this method to recalculate statistics in global_counters
        """
        # Recalculate token statistics
        all_calls = list(self.llm_calls.values())
        if all_calls:
            self.global_counters["total_prompt_tokens"] = sum(c.prompt_tokens for c in all_calls)
            self.global_counters["total_completion_tokens"] = sum(c.completion_tokens for c in all_calls)
            self.global_counters["total_tokens"] = sum(c.total_tokens for c in all_calls)
        
        # Recalculate cost
        self.total_cost_usd = sum(c.estimated_cost_usd for c in all_calls) if all_calls else 0.0
    
    # ===== Resource statistics methods =====
    
    def record_resource_snapshot(self, snapshot: ResourceSnapshot):
        """Record resource snapshot"""
        self.resource_snapshots.append(snapshot)
    
    def capture_current_resources(self):
        """Capture current resource usage"""
        try:
            import psutil
            process = psutil.Process()
            
            snapshot = ResourceSnapshot(
                timestamp=datetime.now(),
                cpu_percent=process.cpu_percent(),
                memory_used_mb=process.memory_info().rss / 1024 / 1024,
                memory_percent=process.memory_percent()
            )
            self.record_resource_snapshot(snapshot)
        except ImportError:
            # psutil not installed, skip
            pass
        except Exception as e:
            # Other errors, log but don't interrupt
            pass
    
    # ===== Analysis methods =====
    
    def get_llm_token_stats(self, by_level: bool = False, by_trigger: bool = False) -> Dict[str, Any]:
        """Get LLM token statistics"""
        all_calls = list(self.llm_calls.values())
        
        if not all_calls:
            return {"total_calls": 0}
        
        result = {
            "total_calls": len(all_calls),
            "successful_calls": sum(1 for c in all_calls if c.success),
            "failed_calls": sum(1 for c in all_calls if not c.success),
            "total_prompt_tokens": sum(c.prompt_tokens for c in all_calls),
            "total_completion_tokens": sum(c.completion_tokens for c in all_calls),
            "total_tokens": sum(c.total_tokens for c in all_calls),
            "avg_prompt_tokens": statistics.mean(c.prompt_tokens for c in all_calls),
            "avg_completion_tokens": statistics.mean(c.completion_tokens for c in all_calls),
            "avg_total_tokens": statistics.mean(c.total_tokens for c in all_calls),
            "median_prompt_tokens": statistics.median(c.prompt_tokens for c in all_calls),
            "median_completion_tokens": statistics.median(c.completion_tokens for c in all_calls),
            "max_prompt_tokens": max(c.prompt_tokens for c in all_calls),
            "max_completion_tokens": max(c.completion_tokens for c in all_calls),
            "min_prompt_tokens": min(c.prompt_tokens for c in all_calls),
            "min_completion_tokens": min(c.completion_tokens for c in all_calls),
        }
        
        if len(all_calls) > 1:
            result["stdev_prompt_tokens"] = statistics.stdev(c.prompt_tokens for c in all_calls)
            result["stdev_completion_tokens"] = statistics.stdev(c.completion_tokens for c in all_calls)
        
        # Statistics by level
        if by_level:
            result["by_level"] = {}
            for level in MemoryLevel:
                level_calls = [self.llm_calls[cid] for cid in self.llm_calls_by_level[level]]
                if level_calls:
                    result["by_level"][level.value] = {
                        "calls": len(level_calls),
                        "total_tokens": sum(c.total_tokens for c in level_calls),
                        "avg_tokens": statistics.mean(c.total_tokens for c in level_calls),
                    }
        
        # Statistics by trigger type
        if by_trigger:
            result["by_trigger"] = {}
            for trigger in TriggerType:
                trigger_calls = [self.llm_calls[cid] for cid in self.llm_calls_by_trigger[trigger]]
                if trigger_calls:
                    result["by_trigger"][trigger.value] = {
                        "calls": len(trigger_calls),
                        "total_tokens": sum(c.total_tokens for c in trigger_calls),
                        "avg_tokens": statistics.mean(c.total_tokens for c in trigger_calls),
                    }
        
        return result
    
    def get_llm_latency_stats(self, by_level: bool = False) -> Dict[str, Any]:
        """Get LLM latency statistics"""
        successful_calls = [c for c in self.llm_calls.values() if c.success and c.latency_ms > 0]
        
        if not successful_calls:
            return {"total_calls": 0}
        
        latencies = [c.latency_ms for c in successful_calls]
        
        result = {
            "total_calls": len(successful_calls),
            "avg_latency_ms": statistics.mean(latencies),
            "median_latency_ms": statistics.median(latencies),
            "max_latency_ms": max(latencies),
            "min_latency_ms": min(latencies),
            "p95_latency_ms": self._percentile(latencies, 95),
            "p99_latency_ms": self._percentile(latencies, 99),
        }
        
        if len(latencies) > 1:
            result["stdev_latency_ms"] = statistics.stdev(latencies)
        
        # Token generation speed statistics
        speeds = [c.tokens_per_second for c in successful_calls if c.tokens_per_second]
        if speeds:
            result["avg_tokens_per_second"] = statistics.mean(speeds)
            result["median_tokens_per_second"] = statistics.median(speeds)
        
        # Statistics by level
        if by_level:
            result["by_level"] = {}
            for level in MemoryLevel:
                level_calls = [self.llm_calls[cid] for cid in self.llm_calls_by_level[level] 
                              if self.llm_calls[cid].success and self.llm_calls[cid].latency_ms > 0]
                if level_calls:
                    level_latencies = [c.latency_ms for c in level_calls]
                    result["by_level"][level.value] = {
                        "calls": len(level_calls),
                        "avg_latency_ms": statistics.mean(level_latencies),
                        "median_latency_ms": statistics.median(level_latencies),
                        "max_latency_ms": max(level_latencies),
                    }
        
        return result
    
    def get_memory_quality_stats(self, by_level: bool = False) -> Dict[str, Any]:
        """Get memory quality statistics"""
        all_memories = list(self.memories.values())
        
        if not all_memories:
            return {"total_memories": 0}
        
        # Content length statistics
        char_lengths = [m.content_length_chars for m in all_memories if m.content_length_chars > 0]
        word_lengths = [m.content_length_words for m in all_memories if m.content_length_words > 0]
        
        result = {
            "total_memories": len(all_memories),
            "duplicate_count": sum(1 for m in all_memories if m.is_duplicate),
            "duplicate_rate": sum(1 for m in all_memories if m.is_duplicate) / len(all_memories),
        }
        
        if char_lengths:
            result["avg_content_length_chars"] = statistics.mean(char_lengths)
            result["median_content_length_chars"] = statistics.median(char_lengths)
            result["max_content_length_chars"] = max(char_lengths)
            result["min_content_length_chars"] = min(char_lengths)
        
        if word_lengths:
            result["avg_content_length_words"] = statistics.mean(word_lengths)
            result["median_content_length_words"] = statistics.median(word_lengths)
        
        # Relationship statistics
        parent_counts = [m.parent_count for m in all_memories]
        child_counts = [m.child_count for m in all_memories]
        
        if parent_counts:
            result["avg_parent_count"] = statistics.mean(parent_counts)
            result["max_parent_count"] = max(parent_counts)
        
        if child_counts:
            result["avg_child_count"] = statistics.mean(child_counts)
            result["max_child_count"] = max(child_counts)
        
        # Statistics by level
        if by_level:
            result["by_level"] = {}
            for level in MemoryLevel:
                level_memories = [self.memories[mid] for mid in self.memories_by_level[level]]
                if level_memories:
                    level_char_lengths = [m.content_length_chars for m in level_memories if m.content_length_chars > 0]
                    result["by_level"][level.value] = {
                        "count": len(level_memories),
                        "avg_length_chars": statistics.mean(level_char_lengths) if level_char_lengths else 0,
                    }
        
        return result
    
    def get_time_distribution(self) -> Dict[str, Any]:
        """Get time distribution statistics"""
        if not self.start_time or not self.end_time:
            return {"total_time_seconds": 0}
        
        total_time = self.end_time - self.start_time
        
        # Analyze phase time distribution (extracted from turns)
        phase_times = defaultdict(list)
        for turn in self.turns.values():
            for phase in turn.phases:
                phase_times[phase.phase_name].append(phase.duration_ms)
        
        phase_stats = {}
        total_phase_time = 0
        for phase_name, times in phase_times.items():
            if times:
                total_phase_time += sum(times)
                phase_stats[phase_name] = {
                    "total_ms": sum(times),
                    "avg_ms": statistics.mean(times),
                    "count": len(times),
                }
        
        # Calculate percentage
        if total_phase_time > 0:
            for phase_name in phase_stats:
                phase_stats[phase_name]["percentage"] = (
                    phase_stats[phase_name]["total_ms"] / total_phase_time * 100
                )
        
        return {
            "total_time_seconds": total_time,
            "phase_breakdown": phase_stats,
            "avg_turn_processing_ms": statistics.mean(
                [t.total_time_ms for t in self.turns.values()]
            ) if self.turns else 0,
        }
    
    def get_resource_stats(self) -> Dict[str, Any]:
        """Get resource usage statistics"""
        if not self.resource_snapshots:
            return {"snapshots_count": 0}
        
        cpu_values = [s.cpu_percent for s in self.resource_snapshots if s.cpu_percent is not None]
        memory_values = [s.memory_used_mb for s in self.resource_snapshots if s.memory_used_mb is not None]
        
        result = {
            "snapshots_count": len(self.resource_snapshots),
        }
        
        if cpu_values:
            result["cpu"] = {
                "avg_percent": statistics.mean(cpu_values),
                "max_percent": max(cpu_values),
                "min_percent": min(cpu_values),
            }
        
        if memory_values:
            result["memory"] = {
                "avg_mb": statistics.mean(memory_values),
                "max_mb": max(memory_values),
                "min_mb": min(memory_values),
            }
        
        return result
    
    def get_error_stats(self) -> Dict[str, Any]:
        """Get error statistics"""
        return {
            "total_errors": len(self.errors),
            "errors_by_type": {
                error_type.value: count 
                for error_type, count in self.errors_by_type.items()
            },
            "error_rate": len(self.errors) / self.global_counters["total_llm_calls"] 
                         if self.global_counters["total_llm_calls"] > 0 else 0,
        }
    
    def get_cost_analysis(self) -> Dict[str, Any]:
        """Get cost analysis"""
        return {
            "total_cost_usd": self.total_cost_usd,
            "cost_per_memory": self.total_cost_usd / self.global_counters["total_memories_generated"]
                              if self.global_counters["total_memories_generated"] > 0 else 0,
            "cost_per_turn": self.total_cost_usd / self.global_counters["total_turns"]
                            if self.global_counters["total_turns"] > 0 else 0,
            "cost_breakdown_by_level": self._calculate_cost_by_level(),
        }
    
    def get_throughput_stats(self) -> Dict[str, Any]:
        """Get throughput statistics"""
        if not self.start_time or not self.end_time:
            return {"total_time_seconds": 0}
        
        total_time = self.end_time - self.start_time
        
        return {
            "total_time_seconds": total_time,
            "turns_per_second": self.global_counters["total_turns"] / total_time if total_time > 0 else 0,
            "memories_per_second": self.global_counters["total_memories_generated"] / total_time if total_time > 0 else 0,
            "tokens_per_second": self.global_counters["total_tokens"] / total_time if total_time > 0 else 0,
        }
    
    def get_comprehensive_summary(self) -> Dict[str, Any]:
        """Get comprehensive summary"""
        return {
            "global_counters": self.global_counters,
            "llm_token_stats": self.get_llm_token_stats(by_level=True, by_trigger=True),
            "llm_latency_stats": self.get_llm_latency_stats(by_level=True),
            "memory_quality_stats": self.get_memory_quality_stats(by_level=True),
            "time_distribution": self.get_time_distribution(),
            "resource_stats": self.get_resource_stats(),
            "error_stats": self.get_error_stats(),
            "cost_analysis": self.get_cost_analysis(),
            "throughput_stats": self.get_throughput_stats(),
        }
    
    def export_to_json(self, filepath: str):
        """Export statistics to JSON file"""
        summary = self.get_comprehensive_summary()
        
        # Add raw data (optional)
        summary["raw_data"] = {
            "llm_calls": [asdict(c) for c in self.llm_calls.values()],
            "memories": [asdict(m) for m in self.memories.values()],
            "errors": self.errors,
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
    
    def export_to_csv(self, output_dir: str):
        """Export statistics to CSV files"""
        import csv
        import os
        
        os.makedirs(output_dir, exist_ok=True)
        
        # Export LLM call data
        llm_calls_file = os.path.join(output_dir, "llm_calls.csv")
        if self.llm_calls:
            with open(llm_calls_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=asdict(list(self.llm_calls.values())[0]).keys())
                writer.writeheader()
                for call in self.llm_calls.values():
                    row = asdict(call)
                    # Handle enum types
                    row['memory_level'] = row['memory_level'].value if row['memory_level'] else ''
                    row['trigger_type'] = row['trigger_type'].value if row['trigger_type'] else ''
                    row['error_type'] = row['error_type'].value if row['error_type'] else ''
                    writer.writerow(row)
        
        # Export memory data
        memories_file = os.path.join(output_dir, "memories.csv")
        if self.memories:
            with open(memories_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=asdict(list(self.memories.values())[0]).keys())
                writer.writeheader()
                for memory in self.memories.values():
                    row = asdict(memory)
                    row['memory_level'] = row['memory_level'].value if row['memory_level'] else ''
                    row['trigger_type'] = row['trigger_type'].value if row['trigger_type'] else ''
                    writer.writerow(row)
    
    # ===== Helper methods =====
    
    def _percentile(self, data: List[float], percentile: int) -> float:
        """Calculate percentile"""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]
    
    def _calculate_cost_by_level(self) -> Dict[str, float]:
        """Calculate cost by level"""
        cost_by_level = {}
        for level in MemoryLevel:
            level_calls = [self.llm_calls[cid] for cid in self.llm_calls_by_level[level]]
            cost_by_level[level.value] = sum(c.estimated_cost_usd for c in level_calls)
        return cost_by_level


# ===== Helper utility functions =====

def extract_token_info_from_chat_response(chat_response) -> Tuple[int, int, int]:
    """
    Extract token information from ChatResponse
    
    Args:
        chat_response: llm.base_llm.ChatResponse object or dict
        
    Returns:
        (prompt_tokens, completion_tokens, total_tokens)
    """
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    
    try:
        # Try to get from usage field
        usage = None
        if hasattr(chat_response, 'usage'):
            usage = chat_response.usage
        elif isinstance(chat_response, dict) and 'usage' in chat_response:
            usage = chat_response['usage']
        
        if usage:
            # OpenAI format: prompt_tokens, completion_tokens, total_tokens
            if isinstance(usage, dict):
                prompt_tokens = usage.get('prompt_tokens', 0)
                completion_tokens = usage.get('completion_tokens', 0)
                total_tokens = usage.get('total_tokens', 0)
                
                # If only total_tokens, try to get from other fields
                if total_tokens > 0 and prompt_tokens == 0 and completion_tokens == 0:
                    # Some APIs may use input_tokens/output_tokens
                    prompt_tokens = usage.get('input_tokens', 0)
                    completion_tokens = usage.get('output_tokens', 0)
                    if prompt_tokens == 0 and completion_tokens == 0:
                        # Estimate: assume 1:2 ratio
                        prompt_tokens = int(total_tokens * 0.6)
                        completion_tokens = total_tokens - prompt_tokens
            elif hasattr(usage, '__dict__'):
                # usage is an object
                prompt_tokens = getattr(usage, 'prompt_tokens', 0) or getattr(usage, 'input_tokens', 0)
                completion_tokens = getattr(usage, 'completion_tokens', 0) or getattr(usage, 'output_tokens', 0)
                total_tokens = getattr(usage, 'total_tokens', 0)
        
        # If total_tokens is 0, calculate it
        if total_tokens == 0 and (prompt_tokens > 0 or completion_tokens > 0):
            total_tokens = prompt_tokens + completion_tokens
            
    except Exception as e:
        logger.warning(f"Failed to extract token information: {e}")
    
    return prompt_tokens, completion_tokens, total_tokens


def estimate_llm_cost(
    prompt_tokens: int,
    completion_tokens: int,
    model_name: str = "gpt-4"
) -> float:
    """Estimate LLM call cost (USD)"""
    
    # Price table (October 2025, updated)
    pricing = {
        "gpt-4": {"input": 0.03 / 1000, "output": 0.06 / 1000},
        "gpt-4-turbo": {"input": 0.01 / 1000, "output": 0.03 / 1000},
        "gpt-4o": {"input": 0.0025 / 1000, "output": 0.01 / 1000},
        "gpt-3.5-turbo": {"input": 0.0005 / 1000, "output": 0.0015 / 1000},
        "claude-3-opus": {"input": 0.015 / 1000, "output": 0.075 / 1000},
        "claude-3-sonnet": {"input": 0.003 / 1000, "output": 0.015 / 1000},
        "claude-3-5-sonnet": {"input": 0.003 / 1000, "output": 0.015 / 1000},
        "glm-4": {"input": 0.001 / 1000, "output": 0.001 / 1000},
        "glm-4-flash": {"input": 0.0001 / 1000, "output": 0.0001 / 1000},
        "deepseek": {"input": 0.0001 / 1000, "output": 0.0002 / 1000},
        "default": {"input": 0.001 / 1000, "output": 0.002 / 1000},
    }
    
    # Find matching model
    model_pricing = None
    model_name_lower = model_name.lower()
    for model_key in pricing:
        if model_key.lower() in model_name_lower:
            model_pricing = pricing[model_key]
            break
    
    if not model_pricing:
        model_pricing = pricing["default"]
    
    cost = (
        prompt_tokens * model_pricing["input"] +
        completion_tokens * model_pricing["output"]
    )
    
    return cost


def count_chinese_words(text: str) -> int:
    """Count words (characters) in Chinese text"""
    import re
    # Remove whitespace
    text = re.sub(r'\s+', '', text)
    # Count Chinese characters
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    # Count English words
    english_words = len(re.findall(r'[a-zA-Z]+', text))
    return chinese_chars + english_words


def count_tokens_estimate(text: str, model: str = "gpt-4") -> int:
    """
    Calculate token count for text
    
    - If tiktoken available and model is OpenAI: use precise counting (99%+ accuracy)
    - Otherwise: use estimation method (70-85% accuracy)
    
    Args:
        text: Text to calculate
        model: Model name (default gpt-4)
        
    Returns:
        Token count
    """
    try:
        from timem.utils.token_counter import count_tokens
        return count_tokens(text, model)
    except ImportError:
        # If token_counter module unavailable, downgrade to simple estimation
        import re
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        other_chars = len(text) - chinese_chars
        estimated_tokens = int(chinese_chars / 1.5 + other_chars / 4)
        return max(estimated_tokens, 1)


# ===== Memory generator statistics wrapper =====

class MemoryGeneratorStatsWrapper:
    """
    MemoryGenerator statistics wrapper
    
    Used to wrap MemoryGenerator generation methods and automatically collect statistics
    """
    
    def __init__(self, collector: ComprehensiveStatsCollector):
        self.collector = collector
        self.logger = logger
    
    def parse_memory_level(self, level_str: str) -> MemoryLevel:
        """Parse memory level"""
        level_str = level_str.upper()
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
            return MemoryLevel.L1  # Default
    
    def parse_trigger_type(self, trigger_str: str) -> TriggerType:
        """Parse trigger type"""
        if not trigger_str:
            return TriggerType.REALTIME
        
        trigger_str = trigger_str.lower()
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
    
    async def wrap_generate_method(
        self,
        generate_func,
        level: str,
        trigger_type: str = "realtime",
        model_name: str = "unknown",
        **kwargs
    ):
        """
        Wrap generation method to collect statistics
        
        Args:
            generate_func: Original generation function (async)
            level: Memory level (e.g., "L1", "L2", etc.)
            trigger_type: Trigger type
            model_name: Model name
            **kwargs: Parameters to pass to generate_func
            
        Returns:
            Tuple of generated content and ChatResponse object: (content, chat_response)
        """
        call_id = str(uuid.uuid4())
        start_time = time.perf_counter()
        timestamp = datetime.now()
        
        memory_level = self.parse_memory_level(level)
        trigger = self.parse_trigger_type(trigger_type)
        
        try:
            # Execute generation
            result = await generate_func(**kwargs)
            
            # Calculate latency
            end_time = time.perf_counter()
            latency_ms = (end_time - start_time) * 1000
            
            # result may be string (content) or tuple (content, chat_response)
            content = None
            chat_response = None
            
            if isinstance(result, tuple) and len(result) == 2:
                content, chat_response = result
            elif isinstance(result, str):
                content = result
            else:
                content = str(result)
            
            # Extract token information
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0
            
            if chat_response:
                prompt_tokens, completion_tokens, total_tokens = extract_token_info_from_chat_response(chat_response)
            
            # If no token information, estimate
            if total_tokens == 0 and content:
                completion_tokens = count_tokens_estimate(content)
                # Try to get input content from kwargs to estimate prompt_tokens
                if 'child_contents' in kwargs:
                    prompt_tokens = sum(count_tokens_estimate(c) for c in kwargs['child_contents'] if c)
                elif 'new_dialogue' in kwargs:
                    prompt_tokens = count_tokens_estimate(kwargs['new_dialogue'])
                total_tokens = prompt_tokens + completion_tokens
            
            # Calculate generation speed
            tokens_per_second = completion_tokens / (latency_ms / 1000) if latency_ms > 0 and completion_tokens > 0 else None
            
            # Estimate cost
            cost = estimate_llm_cost(prompt_tokens, completion_tokens, model_name)
            
            # Create statistics record
            call_stats = LLMCallStats(
                call_id=call_id,
                timestamp=timestamp,
                memory_level=memory_level,
                trigger_type=trigger,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                latency_ms=latency_ms,
                tokens_per_second=tokens_per_second,
                success=True,
                model_name=model_name,
                estimated_cost_usd=cost
            )
            
            # Record statistics
            self.collector.record_llm_call(call_stats)
            
            return result
            
        except Exception as e:
            # Record failure
            end_time = time.perf_counter()
            latency_ms = (end_time - start_time) * 1000
            
            error_type = self._classify_error(e)
            
            call_stats = LLMCallStats(
                call_id=call_id,
                timestamp=timestamp,
                memory_level=memory_level,
                trigger_type=trigger,
                latency_ms=latency_ms,
                success=False,
                error_type=error_type,
                error_message=str(e),
                model_name=model_name
            )
            
            self.collector.record_llm_call(call_stats)
            
            raise
    
    def _classify_error(self, exception: Exception) -> ErrorType:
        """Classify error type"""
        error_msg = str(exception).lower()
        
        if "timeout" in error_msg:
            return ErrorType.LLM_TIMEOUT
        elif "api" in error_msg or "request" in error_msg:
            return ErrorType.LLM_API_ERROR
        elif "parse" in error_msg or "json" in error_msg:
            return ErrorType.LLM_PARSE_ERROR
        elif "database" in error_msg or "sql" in error_msg:
            return ErrorType.DATABASE_ERROR
        elif "vector" in error_msg or "qdrant" in error_msg:
            return ErrorType.VECTOR_DB_ERROR
        elif "network" in error_msg or "connection" in error_msg:
            return ErrorType.NETWORK_ERROR
        else:
            return ErrorType.UNKNOWN_ERROR

