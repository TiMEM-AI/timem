"""
LongMemEval-S Dataset Memory Generation Real System Simulation Test (🚀 Full 500 users mode)

⚠️ Important: This test can only run under longmemeval_s dataset configuration
    - Need to start container first: python scripts/dev/manage_containers.py start --profile longmemeval_s
    - Need to set: export TIMEM_DATASET_PROFILE=longmemeval_s
    - Or in .env file: TIMEM_DATASET_PROFILE=longmemeval_s

🚀 Full mode:
- Process complete data for all 500 users (loaded from complete_data_by_user directory)
- Process all sessions for each user
- Process all turns for each session (merge every 2 messages into 1 turn)
- Parallel processing: 40 users (40 API keys, PostgreSQL connection pool 100)

Dataset characteristics:
- 500 users, each user as 1 conversation
- Each user has multiple sessions and multiple turns
- Contains 6 question types:
  · single-session-user
  · single-session-assistant
  · single-session-preference
  · multi-session
  · knowledge-update
  · temporal-reasoning

Simulate real system operation:
1. Auto backfill at midnight (from first session date to last session date + 1 day)
2. For multiple sessions in a day, backfill L2 between sessions (simulate session inactivity)
3. Use force mode on last day to force backfill
4. Observe when system backfills and when it skips
"""

import os
import sys
import time
import asyncio
import json
import logging
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional, Set
from collections import defaultdict
import threading
from pathlib import Path

# Add project root directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest

# ⚠️ Import dataset guard (before importing services)
from timem.utils.dataset_guard import DatasetGuard, require_dataset, print_current_dataset

from services.memory_generation_service import (
    MemoryGenerationService,
    MemoryGenerationRequest,
    get_memory_generation_service
)
from timem.core.catchup_detector import CatchUpDetector
from timem.core.backfill_task_sorter import BackfillTaskSorter
from timem.core.service_registry import register_core_services, initialize_all_services, shutdown_all_services
from timem.utils.logging import get_logger
from timem.utils.time_parser import time_parser

# Import statistics collector
from timem.utils.stats_collector import ComprehensiveStatsCollector
from experiments.utils.stats_helper import StatsTestHelper

# Set logging level
logging.getLogger().setLevel(logging.WARNING)
logging.getLogger('timem').setLevel(logging.INFO)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('sqlalchemy').setLevel(logging.WARNING)

logger = get_logger(__name__)


class ParallelSimConfig:
    """Parallel simulation configuration"""
    
    def __init__(self, max_concurrent_users: int = 40):  # 🚀 Full mode: 40 concurrent (matching 40 API keys)
        self.max_concurrent_users = max_concurrent_users


class RealisticSimStats:
    """Real simulation statistics"""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        self.total_days = 0
        self.days_with_sessions = 0
        self.days_with_backfill = 0
        self.days_skipped = 0
        self.total_sessions = 0
        self.total_turns = 0
        self.total_l1_generated = 0
        self.total_l2_generated = 0
        self.total_l3_generated = 0
        self.total_l4_generated = 0
        self.total_l5_generated = 0
        self.inter_session_l2_count = 0
        self.daily_backfill_count = 0
        self.force_backfill_count = 0
        self.daily_logs = []  # Daily processing logs
        self.start_time = None
        self.end_time = None
    
    def log_day(self, day: date, log_entry: Dict[str, Any]):
        """Log daily processing"""
        self.daily_logs.append({
            "date": day,
            **log_entry
        })
    
    def get_summary(self):
        if self.start_time and self.end_time:
            total_time = self.end_time - self.start_time
        else:
            total_time = 0
        
        return {
            "total_days": self.total_days,
            "days_with_sessions": self.days_with_sessions,
            "days_with_backfill": self.days_with_backfill,
            "days_skipped": self.days_skipped,
            "total_sessions": self.total_sessions,
            "total_turns": self.total_turns,
            "total_l1_generated": self.total_l1_generated,
            "total_l2_generated": self.total_l2_generated,
            "total_l3_generated": self.total_l3_generated,
            "total_l4_generated": self.total_l4_generated,
            "total_l5_generated": self.total_l5_generated,
            "inter_session_l2_count": self.inter_session_l2_count,
            "daily_backfill_count": self.daily_backfill_count,
            "force_backfill_count": self.force_backfill_count,
            "total_execution_time": total_time
        }


async def register_user_and_assistant(user_id: str, question_type: str, global_expert_id: str = None):
    """Register user and assistant"""
    try:
        from services.user_service import get_user_service
        import uuid
        import time
        
        user_service = get_user_service()
        
        timestamp_suffix = int(time.time() * 1000) % 100000
        unique_suffix = str(uuid.uuid4())[:8]
        
        # Register user
        unique_username = f"longmemeval_user_{user_id}_{timestamp_suffix}_{unique_suffix}"
        user = await user_service.create_user(
            username=unique_username,
            display_name=f"LongMemEval User {user_id}",
            description=f"[LONGMEMEVAL_S] {question_type} type user: {user_id}",
            metadata={
                "user_id": user_id,
                "question_type": question_type,
                "role": "user",
                "test_type": "longmemeval_s_sim",
                "dataset": "longmemeval_s"
            }
        )
        user_db_id = user["id"]
        
        # If global expert ID provided, use global expert; otherwise create dedicated assistant
        if global_expert_id:
            assistant_id = global_expert_id
            print(f"[LONGMEMEVAL_S] Register user {user_id}: User (ID: {user_db_id}) & Use global expert (ID: {assistant_id})")
        else:
            # Create dedicated assistant (keep original logic)
            from services.character_service import get_character_service
            character_service = get_character_service()
            
            timestamp_suffix_2 = int(time.time() * 1000) % 100000 + 1
            unique_suffix_2 = str(uuid.uuid4())[:8]
            
            unique_assistant_name = f"longmemeval_assistant_{user_id}_{timestamp_suffix_2}_{unique_suffix_2}"
            assistant_character = await character_service.create_character(
                name=unique_assistant_name,
                character_type="expert",
                display_name=f"Assistant for {user_id}",
                description=f"[LONGMEMEVAL_S] AI assistant for user {user_id}",
                metadata={
                    "user_id": user_id,
                    "question_type": question_type,
                    "role": "assistant",
                    "test_type": "longmemeval_s_sim",
                    "dataset": "longmemeval_s"
                }
            )
            assistant_id = assistant_character["id"]
            print(f"[LONGMEMEVAL_S] Register user {user_id}: User (ID: {user_db_id}) & Dedicated assistant (ID: {assistant_id})")
        
        return user_db_id, assistant_id
        
    except Exception as e:
        logger.error(f"User {user_id} registration failed: {e}")
        raise RuntimeError(f"User {user_id} registration failed: {e}")


async def process_realistic_simulation(
    user_id: str,
    user_data: dict,
    user_info: dict,
    service: MemoryGenerationService,
    stats: RealisticSimStats,
    user_idx: int,
    total_users: int,
    stats_helper: Optional[StatsTestHelper] = None
) -> dict:
    """
    Real system simulation processing (LongMemEval-S version)
    
    Workflow:
    1. Analyze session times, get first and last dates
    2. Organize sessions by date
    3. Daily simulation:
       - Days with sessions: process sessions, if multiple sessions in a day backfill L2 between sessions
       - Daily midnight: trigger auto backfill (detect previous day's memories)
    4. Last day + 1: use force mode to force backfill
    """
    sessions_data = user_data["sessions"]
    question_type = user_data.get("question_type", "unknown")
    user_db_id = user_info["user_id"]
    assistant_id = user_info["assistant_id"]
    
    print(f"\n{'='*80}")
    print(f"[LONGMEMEVAL_S] Start real system simulation: User {user_id}")
    print(f"[LONGMEMEVAL_S] Question type: {question_type}")
    print(f"[LONGMEMEVAL_S] Total sessions: {len(sessions_data)}")
    print(f"{'='*80}\n")
    
    # 1. Analyze sessions, organize by date
    sessions_by_date = defaultdict(list)
    session_details = {}
    
    # 🚀 Full mode: process all sessions
    print(f"[LONGMEMEVAL_S] 🚀 Full generation mode: process all {len(sessions_data)} sessions")
    
    for session_info in sessions_data:
        session_id = session_info.get("session_id")
        date_time_str = session_info.get("session_date", "")
        
        try:
            # Parse time "2023/05/20 (Sat) 07:47"
            session_time = time_parser.parse(date_time_str)
            session_date = session_time.date()
            
            sessions_by_date[session_date].append({
                "session_id": session_id,
                "session_time": session_time,
                "session_data": session_info
            })
            
            session_details[session_id] = {
                "time": session_time,
                "date": session_date,
                "turns": session_info.get("turns", [])
            }
        except Exception as e:
            logger.error(f"Failed to parse session time {session_id}: {e}")
            continue
    
    if not sessions_by_date:
        print(f"[LONGMEMEVAL_S] No valid session data")
        return {"success": False, "error": "No valid sessions"}
    
    # 2. Get date range
    all_dates = sorted(sessions_by_date.keys())
    first_date = all_dates[0]
    last_date = all_dates[-1]
    simulation_end_date = last_date + timedelta(days=1)  # Last day + 1
    
    print(f"[LONGMEMEVAL_S] Time range: {first_date} to {last_date}")
    print(f"[LONGMEMEVAL_S] Simulation days: {(simulation_end_date - first_date).days + 1} days")
    print(f"[LONGMEMEVAL_S] Session days: {len(sessions_by_date)} days")
    print(f"[LONGMEMEVAL_S] Total sessions: {sum(len(sessions) for sessions in sessions_by_date.values())}")
    print()
    
    # 3. Daily simulation
    current_date = first_date
    total_turns = 0
    total_l1 = 0
    total_l2 = 0
    total_l3 = 0
    total_l4 = 0
    total_l5 = 0
    inter_session_l2 = 0
    daily_backfill = 0
    force_backfill = 0
    simulation_interrupted = False
    
    while current_date <= simulation_end_date:
        day_log = {
            "has_sessions": False,
            "sessions_count": 0,
            "turns_count": 0,
            "backfill_triggered": False,
            "force_mode": False,
            "l1_generated": 0,
            "l2_generated": 0,
            "l3_generated": 0,
            "l4_generated": 0,
            "l5_generated": 0
        }
        
        print(f"\n{'─'*80}")
        print(f"📅 [{current_date}] Start simulation")
        print(f"{'─'*80}")
        
        # Auto backfill at midnight (detect previous day's memories)
        if current_date > first_date:  # Start from second day
            print(f"\n  🌙 [Midnight 00:00:01] Trigger auto backfill detection")
            day_log["backfill_triggered"] = True
            
            try:
                print(f"      🔍 Detect missing memories from previous day")
                
                detector = CatchUpDetector()
                # LongMemEval config: trigger at next day 00:00:01
                backfill_timestamp = datetime.combine(current_date, datetime.min.time()) + timedelta(seconds=1)
                tasks = await detector.detect_missing_in_recent_months(
                    user_id=user_db_id,
                    expert_id=assistant_id,
                    month_count=2,
                    force=False,
                    force_timestamp=backfill_timestamp
                )
                daily_backfill += 1
                
                if tasks:
                    sorter = BackfillTaskSorter()
                    sorted_tasks = sorter.sort_tasks(tasks)
                    
                    print(f"      📋 Pending backfill tasks: {len(sorted_tasks)}")
                    for task in sorted_tasks[:5]:
                        print(f"          - {task.layer}: {task.session_id or task.time_window}")
                    if len(sorted_tasks) > 5:
                        print(f"          ... {len(sorted_tasks) - 5} more tasks")
                    
                    result = await service.run_backfill(sorted_tasks)
                    
                    # Count generated memories
                    generated_memories = result.memories if hasattr(result, 'memories') else result.get("generated_memories", [])
                    for memory in generated_memories:
                        mem_level = None
                        if hasattr(memory, 'level'):
                            mem_level = memory.level
                        elif isinstance(memory, dict) and 'level' in memory:
                            mem_level = memory['level']
                            
                        if mem_level:
                            mem_level_str = mem_level.value if hasattr(mem_level, 'value') else str(mem_level)
                            if "L2" in mem_level_str:
                                total_l2 += 1
                                day_log["l2_generated"] += 1
                            elif "L3" in mem_level_str:
                                total_l3 += 1
                                day_log["l3_generated"] += 1
                            elif "L4" in mem_level_str:
                                total_l4 += 1
                                day_log["l4_generated"] += 1
                            elif "L5" in mem_level_str:
                                total_l5 += 1
                                day_log["l5_generated"] += 1
                    
                    # Record statistics
                    if stats_helper:
                        stats_helper.record_memories_from_result(
                            result,
                            trigger_type="daily_auto_backfill"
                        )
                    
                    print(f"      ✅ Auto backfill completed: L2={day_log['l2_generated']}, L3={day_log['l3_generated']}, L4={day_log['l4_generated']}, L5={day_log['l5_generated']}")
                else:
                    print(f"      ⏭ No backfill needed")
                    
            except Exception as e:
                logger.error(f"Auto backfill exception: {e}")
                print(f"      ✗ Auto backfill exception: {e}")
        
        # Check if current day has sessions
        if current_date in sessions_by_date:
            day_log["has_sessions"] = True
            day_sessions = sessions_by_date[current_date]
            day_sessions.sort(key=lambda s: s["session_time"])
            
            print(f"✅ Current day has {len(day_sessions)} sessions")
            
            day_log["sessions_count"] = len(day_sessions)
            
            # Process all sessions for current day
            for session_idx, session_info in enumerate(day_sessions, 1):
                session_id = session_info["session_id"]
                session_time = session_info["session_time"]
                session_data = session_info["session_data"]
                turns = session_data.get("turns", [])
                
                # New logic: merge every 2 messages (1 user-assistant pair) into 1 turn
                # Calculate turn count (round up, include incomplete turns)
                total_turns_available = (len(turns) + 1) // 2
                
                print(f"\n  📝 Session {session_idx}/{len(day_sessions)}: {session_id}")
                print(f"      Session start time: {session_time.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"      Total messages: {len(turns)}")
                print(f"      Merged turns: {total_turns_available} (max 2 messages per turn, 1 dialogue pair)")
                
                # Full mode: process all turns
                max_turns = total_turns_available
                session_last_turn_timestamp = session_time
                
                if max_turns == 0:
                    print(f"      ⚠️ Session turn count insufficient, skip processing")
                    continue
                
                print(f"      🚀 Full generation mode: process all {max_turns} merged turns")
                
                for turn_idx in range(max_turns):
                    # Calculate message range for current turn
                    dialogue_start_idx = turn_idx * 2
                    dialogue_end_idx = min(dialogue_start_idx + 2, len(turns))
                    
                    # Extract all messages for current turn
                    turn_messages = turns[dialogue_start_idx:dialogue_end_idx]
                    
                    if not turn_messages:
                        break
                    
                    # Build merged dialogue content
                    # Merge all user-assistant pairs into one content
                    content_parts = []
                    valid_pairs = 0
                    
                    # Every 2 messages form one dialogue pair
                    for i in range(0, len(turn_messages), 2):
                        if i + 1 >= len(turn_messages):
                            # Last message unpaired, handle separately
                            last_msg = turn_messages[i]
                            role = last_msg.get("role", "unknown")
                            content_text = last_msg.get("content", "")
                            content_parts.append(f"{role.capitalize()}: {content_text}")
                            logger.warning(f"Session {session_id} turn {turn_idx+1} last message unpaired: {role}")
                            break
                        
                        first_msg = turn_messages[i]
                        second_msg = turn_messages[i + 1]
                        
                        # Smart role matching: support both user→assistant and assistant→user patterns
                        if first_msg.get("role") == "user" and second_msg.get("role") == "assistant":
                            user_content = first_msg.get("content", "")
                            assistant_content = second_msg.get("content", "")
                        elif first_msg.get("role") == "assistant" and second_msg.get("role") == "user":
                            user_content = second_msg.get("content", "")
                            assistant_content = first_msg.get("content", "")
                        else:
                            logger.warning(f"Session {session_id} turn {turn_idx+1} pair {i//2+1} role mismatch (first: {first_msg.get('role')}, second: {second_msg.get('role')})")
                            continue
                        
                        content_parts.append(f"User: {user_content}\nAssistant: {assistant_content}")
                        valid_pairs += 1
                    
                    if not content_parts:
                        logger.warning(f"Session {session_id} turn {turn_idx+1} no valid dialogue pairs, skip")
                        continue
                    
                    # Merge all dialogue pairs, separated by blank lines
                    content = "\n\n".join(content_parts)
                    
                    # Calculate timestamp: 5 seconds interval between merged turns
                    turn_timestamp = session_time + timedelta(seconds=turn_idx * 5)
                    session_last_turn_timestamp = turn_timestamp
                    
                    print(f"      Turn {turn_idx+1}/{max_turns}: {len(turn_messages)} messages ({valid_pairs} complete dialogue pairs)")
                    
                    # Call service.generate_memory() to generate L1
                    try:
                        request = MemoryGenerationRequest(
                            user_id=user_db_id,
                            expert_id=assistant_id,
                            session_id=session_id,
                            content=content,
                            timestamp=turn_timestamp,
                            metadata={
                                "user_id": user_id,
                                "question_type": question_type,
                                "session_id": session_id,
                                "turn_idx": turn_idx + 1,
                                "merged_turn": True,  # Mark this as merged turn
                                "message_count": len(turn_messages),  # Actual message count
                                "pair_count": valid_pairs,  # Complete dialogue pair count
                                "dataset": "longmemeval_s"
                            }
                        )
                        
                        result = await service.generate_memory(request)
                        
                        if result.success:
                            total_turns += 1
                            day_log["turns_count"] += 1
                            
                            # Count L1
                            generated_memories = result.memories if hasattr(result, 'memories') else []
                            for mem in generated_memories:
                                mem_level = None
                                if hasattr(mem, 'level'):
                                    mem_level = mem.level
                                elif isinstance(mem, dict) and 'level' in mem:
                                    mem_level = mem['level']
                                    
                                if mem_level:
                                    mem_level_str = mem_level.value if hasattr(mem_level, 'value') else str(mem_level)
                                    if "L1" in mem_level_str:
                                        total_l1 += 1
                                        day_log["l1_generated"] += 1
                            
                            # Record statistics
                            if stats_helper:
                                stats_helper.record_memories_from_result(
                                    result,
                                    trigger_type="realtime_generation",
                                    turn_id=f"{user_id}_{session_id}_turn_{turn_idx+1}"
                                )
                            
                            print(f"      ✓ Turn {turn_idx+1} processed successfully (time: {turn_timestamp.strftime('%Y-%m-%d %H:%M:%S')}, generated L1: {sum(1 for m in generated_memories if 'L1' in str(getattr(m, 'level', m.get('level', ''))))} items)")
                        else:
                            print(f"      ✗ Turn {turn_idx+1} processing failed: {result.error or 'Unknown error'}")
                            
                    except KeyboardInterrupt:
                        print(f"\n      ⚠️ User interrupted, stop processing dialogue")
                        simulation_interrupted = True
                        break
                    except Exception as e:
                        logger.error(f"Turn {turn_idx+1} processing exception: {e}")
                        print(f"      ✗ Turn {turn_idx+1} processing exception: {e}")
                    
                    await asyncio.sleep(0.05)
                
                if simulation_interrupted:
                    break
                
                # Inter-session L2 backfill: only trigger when multiple sessions on same day
                if len(day_sessions) > 1 and session_idx < len(day_sessions):
                    print(f"\n  🔄 Inter-session L2 backfill detection (current day has {len(day_sessions)} sessions, current is {session_idx})")
                    
                    try:
                        # Inter-session L2 backfill time = last turn time + 10 minutes
                        l2_timestamp = session_last_turn_timestamp + timedelta(minutes=10)
                        print(f"      Session {session_id} last turn time: {session_last_turn_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
                        print(f"      Session {session_id} L2 generation time (last turn + 10 min): {l2_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
                        
                        detector = CatchUpDetector()
                        l2_tasks = await detector.detect_specific_session_l2(
                            user_id=user_db_id,
                            expert_id=assistant_id,
                            session_id=session_id,
                            timestamp=l2_timestamp
                        )
                        
                        if l2_tasks:
                            sorter = BackfillTaskSorter()
                            sorted_tasks = sorter.sort_tasks(l2_tasks)
                            result = await service.run_backfill(sorted_tasks)
                            
                            # Count generated L2 memories
                            l2_count = 0
                            generated_memories = result.memories if hasattr(result, 'memories') else result.get("generated_memories", [])
                            for memory in generated_memories:
                                mem_level = None
                                if hasattr(memory, 'level'):
                                    mem_level = memory.level
                                elif isinstance(memory, dict) and 'level' in memory:
                                    mem_level = memory['level']
                                if mem_level:
                                    mem_level_str = mem_level.value if hasattr(mem_level, 'value') else str(mem_level)
                                    if "L2" in mem_level_str:
                                        l2_count += 1
                            
                            total_l2 += l2_count
                            inter_session_l2 += l2_count
                            day_log["l2_generated"] += l2_count
                            
                            # Record statistics
                            if stats_helper:
                                stats_helper.record_memories_from_result(
                                    result,
                                    trigger_type="inter_session_backfill"
                                )
                            
                            print(f"      ✅ Inter-session L2 backfill completed: {l2_count} items")
                        else:
                            print(f"      ⏭ L2 already exists, no backfill needed")
                            
                    except Exception as e:
                        logger.error(f"Inter-session L2 backfill exception: {e}")
                        print(f"      ✗ Inter-session L2 backfill exception: {e}")
            
            if simulation_interrupted:
                break
        else:
            print(f"⏭ No sessions today")
        
        # If interrupted, break day loop
        if simulation_interrupted:
            break
        
        # Record daily log
        stats.log_day(current_date, day_log)
        stats.total_days += 1
        if day_log["has_sessions"]:
            stats.days_with_sessions += 1
        if day_log["backfill_triggered"]:
            stats.days_with_backfill += 1
        if not day_log["has_sessions"] and not day_log["backfill_triggered"]:
            stats.days_skipped += 1
        
        # Next day
        current_date += timedelta(days=1)
        await asyncio.sleep(0.1)
    
    # If interrupted, return early
    if simulation_interrupted:
        print(f"\n[LONGMEMEVAL_S] ⚠️ Simulation interrupted, return partial results")
        return {
            "user_id": user_id,
            "success": False,
            "error": "Simulation interrupted by user",
            "total_turns": total_turns,
            "total_l1": total_l1,
            "total_l2": total_l2
        }
    
    # Final backfill: run on last session date + 1 day
    print(f"\n{'='*80}")
    print(f"[LONGMEMEVAL_S] Final backfill: last session date + 1")
    print(f"{'='*80}")
    
    final_timestamp = simulation_end_date + timedelta(days=1)
    print(f"  Backfill time: {final_timestamp.strftime('%Y-%m-%d')} 02:00")
    
    try:
        detector = CatchUpDetector()
        
        # Step 0: backfill missing L2 (especially last session)
        print(f"\n  🔧 Step 0: backfill all missing L2 session memories")
        l2_tasks = []
        try:
            # Use detector's internal method to detect all missing L2
            await detector._ensure_dependencies()
            await detector._detect_missing_l2_sessions(
                user_id=user_db_id,
                expert_id=assistant_id,
                timestamp=datetime.combine(final_timestamp, datetime.min.time()) + timedelta(hours=1),
                tasks=l2_tasks
            )
            
            if l2_tasks:
                print(f"      📋 Pending L2 backfill tasks: {len(l2_tasks)}")
                sorter = BackfillTaskSorter()
                sorted_l2_tasks = sorter.sort_tasks(l2_tasks)
                result = await service.run_backfill(sorted_l2_tasks)
                
                # Count generated L2 memories
                l2_count = 0
                generated_memories = result.memories if hasattr(result, 'memories') else result.get("generated_memories", [])
                for memory in generated_memories:
                    mem_level = None
                    if hasattr(memory, 'level'):
                        mem_level = memory.level
                    elif isinstance(memory, dict) and 'level' in memory:
                        mem_level = memory['level']
                    if mem_level:
                        mem_level_str = mem_level.value if hasattr(mem_level, 'value') else str(mem_level)
                        if "L2" in mem_level_str:
                            l2_count += 1
                            total_l2 += 1
                
                print(f"      ✅ L2 backfill completed: {l2_count} items")
            else:
                print(f"      ⏭ All L2 already exists, no backfill needed")
        except Exception as e:
            logger.error(f"Step 0 L2 backfill exception: {e}")
            print(f"      ✗ L2 backfill exception: {e}")
        
        # Step 1: regular backfill (detect missing from last session date)
        print(f"\n  🔍 Step 1: regular backfill (detect yesterday's missing memories)")
        regular_tasks = await detector.detect_missing_in_recent_months(
            user_id=user_db_id,
            expert_id=assistant_id,
            month_count=2,
            force=False,
            force_timestamp=datetime.combine(final_timestamp, datetime.min.time()) + timedelta(hours=2)
        )
        
        if regular_tasks:
            print(f"      📋 Pending backfill tasks: {len(regular_tasks)}")
            for task in regular_tasks:
                print(f"          - {task.layer}: {task.session_id or task.time_window}")
            
            sorter = BackfillTaskSorter()
            sorted_regular_tasks = sorter.sort_tasks(regular_tasks)
            result = await service.run_backfill(sorted_regular_tasks)
            
            # Count generated memories
            generated_memories = result.memories if hasattr(result, 'memories') else result.get("generated_memories", [])
            regular_l2_count = regular_l3_count = regular_l4_count = regular_l5_count = 0
            for memory in generated_memories:
                mem_level = None
                if hasattr(memory, 'level'):
                    mem_level = memory.level
                elif isinstance(memory, dict) and 'level' in memory:
                    mem_level = memory['level']
                    
                if mem_level:
                    mem_level_str = mem_level.value if hasattr(mem_level, 'value') else str(mem_level)
                    if "L2" in mem_level_str:
                        total_l2 += 1
                        regular_l2_count += 1
                    elif "L3" in mem_level_str:
                        total_l3 += 1
                        regular_l3_count += 1
                    elif "L4" in mem_level_str:
                        total_l4 += 1
                        regular_l4_count += 1
                    elif "L5" in mem_level_str:
                        total_l5 += 1
                        regular_l5_count += 1
            
            # Record statistics
            if stats_helper:
                stats_helper.record_memories_from_result(
                    result,
                    trigger_type="daily_auto_backfill"
                )
            
            print(f"      ✅ Auto backfill completed: L2={regular_l2_count}, L3={regular_l3_count}, L4={regular_l4_count}, L5={regular_l5_count}")
        else:
            print(f"      ⏭ No pending backfill tasks")
        
        # Step 2: force backfill (backfill incomplete weeks/months L4/L5)
        print(f"\n  ⚡ Step 2: force backfill (backfill incomplete weeks/months L4/L5)")
        force_tasks = await detector.detect_missing_in_recent_months(
            user_id=user_db_id,
            expert_id=assistant_id,
            month_count=2,
            force=True,
            force_timestamp=datetime.combine(final_timestamp, datetime.min.time()) + timedelta(hours=2)
        )
        
        if force_tasks:
            print(f"      📋 Pending backfill tasks: {len(force_tasks)}")
            for task in force_tasks:
                print(f"          - {task.layer}: {task.time_window}, force_update={task.force_update}")
            
            sorter = BackfillTaskSorter()
            sorted_force_tasks = sorter.sort_tasks(force_tasks)
            result = await service.run_backfill(sorted_force_tasks)
            
            # Count generated memories
            generated_memories = result.memories if hasattr(result, 'memories') else result.get("generated_memories", [])
            force_l4_count = force_l5_count = 0
            for memory in generated_memories:
                mem_level = None
                if hasattr(memory, 'level'):
                    mem_level = memory.level
                elif isinstance(memory, dict) and 'level' in memory:
                    mem_level = memory['level']
                    
                if mem_level:
                    mem_level_str = mem_level.value if hasattr(mem_level, 'value') else str(mem_level)
                    if "L4" in mem_level_str:
                        total_l4 += 1
                        force_l4_count += 1
                    elif "L5" in mem_level_str:
                        total_l5 += 1
                        force_l5_count += 1
            
            # Record statistics
            if stats_helper:
                stats_helper.record_memories_from_result(
                    result,
                    trigger_type="force_backfill"
                )
            
            print(f"      ✅ Force backfill completed: L4={force_l4_count}, L5={force_l5_count}")
            force_backfill += 1
        else:
            print(f"      ⏭ No pending backfill tasks")
        
    except Exception as e:
        print(f"  ❌ Final backfill failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Update statistics
    stats.total_sessions = sum(len(sessions) for sessions in sessions_by_date.values())
    stats.total_turns = total_turns
    stats.total_l1_generated = total_l1
    stats.total_l2_generated = total_l2
    stats.total_l3_generated = total_l3
    stats.total_l4_generated = total_l4
    stats.total_l5_generated = total_l5
    stats.inter_session_l2_count = inter_session_l2
    stats.daily_backfill_count = daily_backfill
    stats.force_backfill_count = force_backfill
    
    print(f"\n{'='*80}")
    print(f"[LONGMEMEVAL_S] Simulation completed: User {user_id}")
    print(f"{'='*80}\n")
    
    return {
        "user_id": user_id,
        "success": True,
        "total_days": stats.total_days,
        "total_sessions": stats.total_sessions,
        "total_turns": total_turns,
        "total_l1": total_l1,
        "total_l2": total_l2,
        "total_l3": total_l3,
        "total_l4": total_l4,
        "total_l5": total_l5,
        "inter_session_l2": inter_session_l2,
        "daily_backfill": daily_backfill,
        "force_backfill": force_backfill
    }


async def process_user_wrapper(
    user_id: str,
    user_data: dict,
    user_info: dict,
    service: MemoryGenerationService,
    user_idx: int,
    total_users: int,
    semaphore: asyncio.Semaphore,
    config: ParallelSimConfig,
    stats_helper: Optional[StatsTestHelper] = None
) -> Dict[str, Any]:
    """
    Wrapper function for parallel processing single user
    """
    async with semaphore:
        start_time = time.perf_counter()
        
        try:
            print(f"\n[PARALLEL_SIM] [{user_idx}/{total_users}] Start processing user {user_id}")
            
            # Create independent statistics for each user
            user_stats = RealisticSimStats()
            user_stats.start_time = start_time
            
            result = await process_realistic_simulation(
                user_id=user_id,
                user_data=user_data,
                user_info=user_info,
                service=service,
                stats=user_stats,
                user_idx=user_idx,
                total_users=total_users,
                stats_helper=stats_helper
            )
            
            end_time = time.perf_counter()
            processing_time = end_time - start_time
            
            result.update({
                "processing_time": processing_time,
                "thread_id": threading.get_ident(),
                "stats": user_stats.get_summary()
            })
            
            print(f"\n[PARALLEL_SIM] [{user_idx}/{total_users}] ✅ User {user_id} processing completed, time: {processing_time:.2f}s")
            
            return result
            
        except Exception as e:
            end_time = time.perf_counter()
            processing_time = end_time - start_time
            
            logger.error(f"[{user_id}] Processing exception: {e}")
            print(f"\n[PARALLEL_SIM] [{user_idx}/{total_users}] ❌ User {user_id} processing exception: {e}")
            
            return {
                "user_id": user_id,
                "success": False,
                "error": str(e),
                "processing_time": processing_time,
                "thread_id": threading.get_ident()
            }


def load_all_users():
    """Load all 500 users' session data from sessions_by_user directory"""
    sessions_dir = Path("data/longmemeval_s_split/sessions_by_user")
    
    if not sessions_dir.exists():
        logger.error(f"sessions_by_user directory does not exist: {sessions_dir}")
        return {}, []
    
    users_data = {}
    user_files = list(sessions_dir.glob("user_*.json"))
    
    # Full mode: load all 500 users' session data
    logger.info(f"Found {len(user_files)} user session files")
    
    for user_file in user_files:
        try:
            with open(user_file, 'r', encoding='utf-8') as f:
                user_data = json.load(f)
                
                user_id = user_data.get("user_id")
                if not user_id:
                    logger.warning(f"User file missing user_id: {user_file}")
                    continue
                
                users_data[user_id] = user_data
                
        except Exception as e:
            logger.error(f"Failed to load user file {user_file}: {e}")
    
    user_ids = list(users_data.keys())
    logger.info(f"✅ Successfully loaded {len(users_data)} users' session data")
    
    return users_data, user_ids


def select_users_by_question_type(users_per_type: int = 4):
    """
    Select first N users from each of 6 question types
    
    Question types:
    1. single-session-user
    2. single-session-assistant
    3. single-session-preference
    4. multi-session
    5. knowledge-update
    6. temporal-reasoning
    
    Args:
        users_per_type: Number of users to select per question type, default 4
    
    Returns:
        selected_user_ids: List of selected user IDs
        users_by_type: Dictionary of users grouped by question type
    """
    questions_dir = Path("data/longmemeval_s_split/questions_by_user")
    
    if not questions_dir.exists():
        logger.error(f"questions_by_user directory does not exist: {questions_dir}")
        return [], {}
    
    # 6 question types
    question_types = [
        "single-session-user",
        "single-session-assistant",
        "single-session-preference",
        "multi-session",
        "knowledge-update",
        "temporal-reasoning"
    ]
    
    users_by_type = {qtype: [] for qtype in question_types}
    selected_user_ids = []
    
    # Get all question files and sort (ensure consistent order)
    question_files = sorted(questions_dir.glob("user_*_questions.json"))
    
    for qtype in question_types:
        for question_file in question_files:
            # Extract user_id from filename: user_001be529_questions.json -> 001be529
            file_stem = question_file.stem  # user_001be529_questions
            if file_stem.startswith("user_") and file_stem.endswith("_questions"):
                user_id = file_stem[5:-10]  # Remove "user_" and "_questions"
            else:
                continue
            
            try:
                with open(question_file, 'r', encoding='utf-8') as f:
                    questions_data = json.load(f)
                    
                    # questions_data is an array, iterate directly
                    if not isinstance(questions_data, list):
                        logger.warning(f"Question file format incorrect: {question_file}")
                        continue
                    
                    # Check if this user has this type of question
                    has_this_type = any(
                        q.get("question_type") == qtype 
                        for q in questions_data
                    )
                    
                    if has_this_type and user_id not in users_by_type[qtype]:
                        users_by_type[qtype].append(user_id)
                        
                        # Stop searching this type after reaching desired count
                        if len(users_by_type[qtype]) >= users_per_type:
                            break
                            
            except Exception as e:
                logger.error(f"Failed to read question file {question_file}: {e}")
                continue
        
        # Add to total list
        selected_user_ids.extend(users_by_type[qtype][:users_per_type])
        
        logger.info(f"Question type '{qtype}': selected {len(users_by_type[qtype][:users_per_type])} users - {users_by_type[qtype][:users_per_type]}")
    
    # Remove duplicates (a user may have multiple types of questions)
    selected_user_ids = list(dict.fromkeys(selected_user_ids))
    
    logger.info(f"Total selected {len(selected_user_ids)} deduplicated users")
    
    return selected_user_ids, users_by_type


@pytest.mark.asyncio
@require_dataset("longmemeval_s", allow_test=True)  # Dataset guard decorator
async def test_longmemeval_s_realistic_simulation():
    """
    LongMemEval-S Dataset - Real System Simulation Test (🚀 Full 500 users mode)
    
    ⚠️ This test can only run under longmemeval_s dataset configuration
    ⚠️ This test will clear the database, please confirm configuration is correct!
    ⚠️ Ensure longmemeval_s container environment has been started
    
    🚀 Full mode:
    - Process complete data for all 500 users
    - Process all sessions for each user
    - Process all turns for each session (merge every 2 messages into 1 turn)
    - Use gpt-4o-mini model (40 API keys, connection pool 100)
    
    Simulate real system operation:
    1. Auto backfill at midnight
    2. Inter-session L2 backfill
    3. Force backfill
    4. Detailed behavior observation logs
    5. Parallel processing 40 users (maintain 40 concurrent tasks)
    """
    # Print current configuration info
    print_current_dataset()
    
    # Warn destructive operation
    DatasetGuard.warn_destructive_operation("longmemeval_s")
    
    # Verify container isolation configuration
    info = DatasetGuard.get_dataset_info()
    container_ports = info.get('container_ports', {})
    
    print(f"\n[LONGMEMEVAL_S] ✅ Container isolation verification")
    print(f"[LONGMEMEVAL_S] Current dataset: {info.get('profile_name')}")
    print(f"[LONGMEMEVAL_S] Dedicated container ports:")
    print(f"  - PostgreSQL: localhost:{container_ports.get('postgres', 5432)} (dedicated: {container_ports.get('postgres') != 5432})")
    print(f"  - Qdrant: localhost:{container_ports.get('qdrant', 6333)} (dedicated: {container_ports.get('qdrant') != 6333})")
    print(f"  - Neo4j: localhost:{container_ports.get('neo4j_bolt', 7687)} (dedicated: {container_ports.get('neo4j_bolt') != 7687})")
    print(f"  - Redis: localhost:{container_ports.get('redis', 6379)} (dedicated: {container_ports.get('redis') != 6379})")
    
    # Verify using dedicated ports
    if container_ports.get('postgres') == 5432 or container_ports.get('qdrant') == 6333:
        raise RuntimeError(
            "❌ Container port configuration error! Detected default port usage, may pollute default dataset.\n"
            f"   Current PostgreSQL port: {container_ports.get('postgres', 5432)}\n"
            f"   Current Qdrant port: {container_ports.get('qdrant', 6333)}\n"
            f"   Please ensure longmemeval_s dedicated container is started.\n"
            f"   Run: python scripts/dev/manage_containers.py start --profile longmemeval_s"
        )
    
    print(f"[LONGMEMEVAL_S] ✅ Container isolation verification passed, using dedicated container environment")
    
    # Load user data
    users_data, user_ids = load_all_users()
    assert len(users_data) > 0, "Must successfully load at least one user"
    
    # Full mode: process all 500 users
    test_user_ids = user_ids
    
    print(f"\n[LONGMEMEVAL_S] LongMemEval-S Real System Simulation Test (🚀 Full 500 users mode)")
    print(f"[LONGMEMEVAL_S] Dataset total users: {len(user_ids)}")
    print(f"[LONGMEMEVAL_S] 🚀 Full mode:")
    print(f"[LONGMEMEVAL_S]    - Process all {len(test_user_ids)} users")
    print(f"[LONGMEMEVAL_S]    - Process all sessions for each user")
    print(f"[LONGMEMEVAL_S]    - Process all turns for each session (merge every 2 messages into 1 turn)")
    print(f"[LONGMEMEVAL_S] 40 users parallel processing (gpt-4o-mini, 40 API keys, 100 connection pool)")
    
    # Create statistics collector
    stats_collector = ComprehensiveStatsCollector()
    stats_helper = StatsTestHelper(stats_collector)
    stats_collector.start_collection()
    print(f"[LONGMEMEVAL_S] ✅ Statistics collector started")
    
    # Enable file prompt collection
    from llm.file_prompt_collector import get_file_prompt_collector, enable_file_prompt_collection
    prompt_file = f"logs/longmemeval_s_sim_prompts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    enable_file_prompt_collection(prompt_file)
    file_prompt_collector = get_file_prompt_collector(prompt_file)
    print(f"[LONGMEMEVAL_S] ✅ File prompt collector started (tiktoken available: {file_prompt_collector._tiktoken_available})")
    print(f"[LONGMEMEVAL_S] 📁 Prompts will be saved to: {prompt_file}")
    
    try:
        # 1. Register core services
        print("[LONGMEMEVAL_S] Register core services...")
        await register_core_services()
        
        # 2. Initialize all services (but don't start scheduler)
        print("[LONGMEMEVAL_S] Initialize all services...")
        from timem.core.service_registry import get_service_registry, ServiceType
        registry = await get_service_registry()
        await registry.initialize_all_services()
        print("[LONGMEMEVAL_S] ⚠️ Test mode: skip scheduler startup (avoid timestamp pollution)")
        
        # 3. Get memory generation service
        print("[LONGMEMEVAL_S] Get memory generation service...")
        service = await get_memory_generation_service()
        
        # 4. Clear database
        print("[LONGMEMEVAL_S] Clear database...")
        from timem.core.global_connection_pool import get_global_pool_manager
        pool_manager = await get_global_pool_manager()
        
        async with pool_manager.get_managed_session() as session:
            from sqlalchemy import text
            
            await session.execute(text("DELETE FROM memory_child_relations"))
            await session.execute(text("DELETE FROM memory_historical_relations"))
            await session.execute(text("DELETE FROM l1_fragment_memories"))
            await session.execute(text("DELETE FROM l2_session_memories"))
            await session.execute(text("DELETE FROM l3_daily_memories"))
            await session.execute(text("DELETE FROM l4_weekly_memories"))
            await session.execute(text("DELETE FROM l5_monthly_memories"))
            await session.execute(text("DELETE FROM dialogue_originals"))
            await session.execute(text("DELETE FROM core_memories"))
            await session.execute(text("DELETE FROM memory_sessions"))
            await session.execute(text("DELETE FROM characters"))
            await session.execute(text("DELETE FROM users WHERE username != 'postgres_init_complete'"))
            
            await session.commit()
            print("[LONGMEMEVAL_S] PostgreSQL database cleared completely")
        
        # 5. Clear Qdrant
        print("[LONGMEMEVAL_S] Clear Qdrant vector database...")
        try:
            from timem.core.service_registry import get_service, ServiceType
            storage_manager = await get_service(ServiceType.STORAGE_MANAGER)
            
            vector_adapter = getattr(storage_manager, "vector_adapter", None)
            if vector_adapter:
                await vector_adapter.connect()
                await vector_adapter.clear_all_data()
                await asyncio.sleep(1.0)
                print("[LONGMEMEVAL_S] Qdrant vector storage cleared")
        except Exception as e:
            print(f"[LONGMEMEVAL_S] Qdrant clear failed: {e}")
        
        # 6. Register global expert (shared by all users)
        print("[LONGMEMEVAL_S] Register global expert...")
        try:
            from services.character_service import get_character_service
            character_service = get_character_service()
            
            global_expert = await character_service.create_character(
                name="longmemeval_global_expert",
                character_type="expert",
                display_name="LongMemEval Global Expert",
                description="Global AI assistant for all users",
                metadata={
                    "role": "global_expert",
                    "test_type": "longmemeval_s_sim",
                    "dataset": "longmemeval_s"
                }
            )
            global_expert_id = global_expert["id"]
            print(f"[LONGMEMEVAL_S] Global expert registered successfully (ID: {global_expert_id})")
        except Exception as e:
            print(f"[LONGMEMEVAL_S] Global expert registration failed: {e}")
            pytest.skip(f"Global expert registration failed, skip test: {e}")
        
        # 7. Register all users
        print(f"[LONGMEMEVAL_S] Register all {len(user_ids)} users...")
        users_info = {}
        
        for user_id in user_ids:  # Register all users
            user_data = users_data[user_id]
            question_type = user_data.get("question_type", "unknown")
            
            try:
                user_db_id, _ = await register_user_and_assistant(user_id, question_type, global_expert_id)
                users_info[user_id] = {
                    "user_id": user_db_id,
                    "assistant_id": global_expert_id,  # All users share the same expert
                    "question_type": question_type
                }
                if user_id in test_user_ids:
                    print(f"[LONGMEMEVAL_S] User {user_id} registered successfully (selected for test)")
                else:
                    print(f"[LONGMEMEVAL_S] User {user_id} registered successfully (not selected)")
            except Exception as e:
                print(f"[LONGMEMEVAL_S] User {user_id} registration failed: {e}")
                if user_id in test_user_ids:
                    pytest.skip(f"User {user_id} registration failed, skip test: {e}")
        
        print(f"[LONGMEMEVAL_S] All {len(user_ids)} users registered")
        
        # 8. Configure 40 users parallel processing (full mode)
        config = ParallelSimConfig(max_concurrent_users=40)  # Full mode: 40 concurrent
        global_stats_start_time = time.perf_counter()
        
        # 9. Create semaphore to control concurrency
        semaphore = asyncio.Semaphore(config.max_concurrent_users)
        
        # 10. Process all 500 users (full mode)
        print(f"\n[LONGMEMEVAL_S] Start processing all {len(test_user_ids)} users (full mode: all sessions and turns)...")
        
        concurrent_tasks = []
        for user_idx, user_id in enumerate(test_user_ids, 1):
            user_data = users_data[user_id]
            user_info = users_info[user_id]
            
            task = process_user_wrapper(
                user_id=user_id,
                user_data=user_data,
                user_info=user_info,
                service=service,
                user_idx=user_idx,
                total_users=len(test_user_ids),
                semaphore=semaphore,
                config=config,
                stats_helper=stats_helper
            )
            concurrent_tasks.append(task)
        
        # Execute parallel tasks
        user_results = await asyncio.gather(*concurrent_tasks, return_exceptions=True)
        
        global_stats_end_time = time.perf_counter()
        total_execution_time = global_stats_end_time - global_stats_start_time
        
        # Process results and aggregate statistics
        successful_count = 0
        failed_count = 0
        total_turns = 0
        total_l1 = 0
        total_l2 = 0
        total_l3 = 0
        total_l4 = 0
        total_l5 = 0
        
        for i, result in enumerate(user_results):
            user_id = test_user_ids[i]
            
            if isinstance(result, Exception):
                failed_count += 1
                print(f"[LONGMEMEVAL_S] User {user_id}: execution exception - {result}")
            else:
                if result.get("success", False):
                    successful_count += 1
                    total_turns += result.get("total_turns", 0)
                    total_l1 += result.get("total_l1", 0)
                    total_l2 += result.get("total_l2", 0)
                    total_l3 += result.get("total_l3", 0)
                    total_l4 += result.get("total_l4", 0)
                    total_l5 += result.get("total_l5", 0)
                    print(f"[LONGMEMEVAL_S] User {user_id}: processing successful - {result.get('total_turns', 0)} turns")
                else:
                    failed_count += 1
                    error_msg = result.get("error", "Unknown error")
                    print(f"[LONGMEMEVAL_S] User {user_id}: processing failed - {error_msg}")
        
        # Output summary
        print(f"\n{'='*80}")
        print(f"[LONGMEMEVAL_S] Real system simulation completed (40 users parallel, full 500 users) - Summary")
        print(f"{'='*80}")
        print(f"  Test users: {len(test_user_ids)}")
        print(f"  Successful users: {successful_count}")
        print(f"  Failed users: {failed_count}")
        
        # Avoid division by zero
        if len(test_user_ids) > 0:
            print(f"  Success rate: {successful_count / len(test_user_ids) * 100:.1f}%")
            print(f"  Total dialogue turns: {total_turns}")
            print(f"  Generated memory statistics:")
            print(f"    - L1: {total_l1} items")
            print(f"    - L2: {total_l2} items")
            print(f"    - L3: {total_l3} items")
            print(f"    - L4: {total_l4} items")
            print(f"    - L5: {total_l5} items")
            print(f"  Total execution time: {total_execution_time:.2f} seconds")
            print(f"  Average processing time: {total_execution_time / len(test_user_ids):.2f} seconds/user")
        else:
            print(f"  Warning: no users selected!")
        print(f"{'='*80}\n")
        
        # Verify results
        assert len(test_user_ids) > 0, "Must select at least one user for testing"
        assert successful_count > 0, "At least one user should be processed successfully"
        assert total_turns > 0, "Should process at least one dialogue turn"
        assert total_l1 > 0, "Should generate L1 memories"
        
        # Detailed verification: in full processing mode, L1 and L2 count depends on actual data
        print(f"\n[LONGMEMEVAL_S] Memory count verification:")
        print(f"  Actual L1 count: {total_l1}")
        print(f"  Actual L2 count: {total_l2}")
        print(f"  L3-L5 count: L3={total_l3}, L4={total_l4}, L5={total_l5}")
        print(f"  Note: in full processing mode, memory count depends on each user's actual session and turn count")
        
        print(f"\n[LONGMEMEVAL_S] LongMemEval-S real system simulation test (full 500 users, 40 concurrent) passed")
        
        # Stop statistics collection and generate report
        stats_collector.end_collection()
        print(f"\n[LONGMEMEVAL_S] Generate statistics report...")
        
        # Update actual input tokens from prompt file
        print(f"\n[LONGMEMEVAL_S] Update actual input tokens from prompt file...")
        stats_helper.update_tokens_from_prompt_file(prompt_file)
        
        # Print statistics summary
        stats_helper.print_summary(detailed=True)
        
        # Export statistics data
        import os
        os.makedirs("logs", exist_ok=True)
        json_path = f"logs/longmemeval_s_sim_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        csv_dir = f"logs/longmemeval_s_sim_stats_csv_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        stats_helper.export_results(json_path, csv_dir)
        
        # Export prompt data
        prompt_readable_path = f"logs/longmemeval_s_sim_prompts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        file_prompt_collector.export_to_readable_format(prompt_readable_path)
        
        # Print prompt statistics
        prompt_stats = file_prompt_collector.get_file_stats()
        print(f"\n[LONGMEMEVAL_S] Prompt statistics:")
        print(f"  Total prompts: {prompt_stats['total_prompts']}")
        print(f"  Total input tokens: {prompt_stats.get('total_prompt_tokens', 0):,} ({'tiktoken accurate' if prompt_stats.get('tiktoken_used', False) else 'estimated'})")
        print(f"  File size: {prompt_stats.get('file_size_bytes', 0):,} bytes")
        
        print(f"\n[LONGMEMEVAL_S] Statistics data exported:")
        print(f"  - Statistics JSON: {json_path}")
        print(f"  - Statistics CSV: {csv_dir}/")
        print(f"  - Prompt raw: {prompt_file}")
        print(f"  - Prompt readable: {prompt_readable_path}")
        
    finally:
        # Cleanup services
        print(f"\n[LONGMEMEVAL_S] Cleanup services...")
        try:
            # Stop statistics collection
            stats_collector.end_collection()
            print(f"[LONGMEMEVAL_S] Statistics collector stopped")
            
            # Disable prompt collection
            from llm.file_prompt_collector import disable_file_prompt_collection
            disable_file_prompt_collection()
            print(f"[LONGMEMEVAL_S] Prompt collector stopped")
            
            # Use timeout mechanism
            await asyncio.wait_for(
                shutdown_all_services(),
                timeout=30.0
            )
            print(f"[LONGMEMEVAL_S] Service cleanup completed")
        except asyncio.TimeoutError:
            print(f"[LONGMEMEVAL_S] Service cleanup timeout (30 seconds), force exit")
        except KeyboardInterrupt:
            print(f"[LONGMEMEVAL_S] Cleanup interrupted, exit immediately")
        except Exception as e:
            print(f"[LONGMEMEVAL_S] Service cleanup failed: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    import signal
    import sys
    
    # Setup signal handler
    def signal_handler(signum, frame):
        print(f"\n\n[LONGMEMEVAL_S] ⚠️ Received interrupt signal, cleaning up...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Run test
    try:
        asyncio.run(test_longmemeval_s_realistic_simulation())
    except KeyboardInterrupt:
        print(f"\n\n[LONGMEMEVAL_S] ⚠️ Test interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n[LONGMEMEVAL_S] ❌ Test execution failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
