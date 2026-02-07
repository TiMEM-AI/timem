#!/usr/bin/env python3
"""
TiMem Memory Retrieval Workflow - Real Data Test Script

This is a core experiment script and should not be deleted.
It uses real user and expert data from the database for testing.
Refer to the style of test_embedding_quick.py to generate a complete test report.
"""

import asyncio
import sys
import os
import json
import time
import signal
from datetime import datetime
from typing import List, Dict, Any, Optional
from tqdm import tqdm
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import threading

# Add the project root directory to the path.
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
sys.path.insert(0, project_root)

try:
    from timem.workflows.memory_retrieval import run_memory_retrieval
    from timem.utils.enhanced_qa_loader import load_enhanced_conv26_questions_for_testing
    from timem.utils.retrieval_config_manager import get_retrieval_config_manager
    from timem.utils.character_id_resolver import get_character_id_resolver
    from timem.utils.conversation_loader import get_conversation_loader
except ImportError as e:
    print(f"❌ Import failed: {e}")
    print(f"💡 Current working directory: {os.getcwd()}")
    print(f"💡 Project root directory: {project_root}")
    print(f"💡 Python path: {sys.path[:3]}...")
    sys.exit(1)


class PerformanceMetrics:
    """A collector for performance metrics."""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        """Resets all metrics."""
        self.start_time = None
        self.end_time = None
        self.retrieval_start_time = None
        self.retrieval_end_time = None
        self.llm_first_response_time = None
        self.llm_generation_start_time = None
        self.llm_generation_end_time = None
        
        # Detailed timestamp records.
        self.timestamps = {}
        
        # Statistical metrics.
        self.metrics = {
            'total_execution_time': 0.0,
            'retrieval_time': 0.0,
            'llm_total_time': 0.0,
            'llm_first_response_delay': 0.0,
            'llm_generation_time': 0.0,
            'input_tokens': 0,
            'output_tokens': 0,
            'total_tokens': 0,
            'retrieved_memories_count': 0,
            'l1_memories_count': 0,
            'l2_memories_count': 0,
            'formatted_memories_count': 0,
            'answer_length': 0,
            'confidence_score': 0.0
        }
    
    def mark_timestamp(self, event_name: str):
        """Records a timestamp for a given event."""
        self.timestamps[event_name] = time.perf_counter()
    
    def start_test(self):
        """Starts the test."""
        self.start_time = time.perf_counter()
        self.mark_timestamp('test_start')
    
    def start_retrieval(self):
        """Starts the retrieval process."""
        self.retrieval_start_time = time.perf_counter()
        self.mark_timestamp('retrieval_start')
    
    def end_retrieval(self):
        """Ends the retrieval process."""
        self.retrieval_end_time = time.perf_counter()
        self.mark_timestamp('retrieval_end')
        if self.retrieval_start_time:
            self.metrics['retrieval_time'] = self.retrieval_end_time - self.retrieval_start_time
    
    def mark_llm_first_response(self):
        """Marks the time of the LLM's first response."""
        self.llm_first_response_time = time.perf_counter()
        self.mark_timestamp('llm_first_response')
        if self.retrieval_end_time:
            self.metrics['llm_first_response_delay'] = self.llm_first_response_time - self.retrieval_end_time
    
    def start_llm_generation(self):
        """Starts the LLM generation process."""
        self.llm_generation_start_time = time.perf_counter()
        self.mark_timestamp('llm_generation_start')
    
    def end_llm_generation(self):
        """Ends the LLM generation process."""
        self.llm_generation_end_time = time.perf_counter()
        self.mark_timestamp('llm_generation_end')
        if self.llm_generation_start_time:
            self.metrics['llm_generation_time'] = self.llm_generation_end_time - self.llm_generation_start_time
        if self.retrieval_end_time and self.llm_generation_end_time:
            self.metrics['llm_total_time'] = self.llm_generation_end_time - self.retrieval_end_time
    
    def end_test(self):
        """Ends the test."""
        self.end_time = time.perf_counter()
        self.mark_timestamp('test_end')
        if self.start_time:
            self.metrics['total_execution_time'] = self.end_time - self.start_time
    
    def update_token_usage(self, input_tokens: int = 0, output_tokens: int = 0):
        """Updates the token usage metrics."""
        self.metrics['input_tokens'] = input_tokens
        self.metrics['output_tokens'] = output_tokens
        self.metrics['total_tokens'] = input_tokens + output_tokens
    
    def update_retrieval_stats(self, memories: List[Dict], formatted_memories: List[str]):
        """Updates the retrieval statistics."""
        self.metrics['retrieved_memories_count'] = len(memories)
        self.metrics['l1_memories_count'] = len([m for m in memories if m.get('level') == 'L1'])
        self.metrics['l2_memories_count'] = len([m for m in memories if m.get('level') == 'L2'])
        self.metrics['formatted_memories_count'] = len(formatted_memories)
    
    def update_answer_stats(self, answer: str, confidence: float):
        """Updates the answer statistics."""
        self.metrics['answer_length'] = len(answer)
        self.metrics['confidence_score'] = confidence
    
    def get_metrics_dict(self) -> Dict[str, Any]:
        """Gets all collected metrics."""
        return {
            **self.metrics,
            'timestamps': self.timestamps.copy()
        }


class ConcurrentConfig:
    """A class for concurrent configuration."""
    
    def __init__(self, max_concurrent_requests: int = 20, batch_delay: float = 0.5, 
                 max_retries: int = 20, retry_delays: List[float] = None, timeout: float = 60.0):
        self.max_concurrent_requests = max_concurrent_requests
        self.batch_delay = batch_delay
        self.max_retries = max_retries
        self.retry_delays = retry_delays or [1.0, 2.0, 3.0]  # Tiered waiting times: 1s, 2s, 3s.
        self.timeout = timeout


class MemoryRetrievalTester:
    """A tester for the memory retrieval workflow that supports asynchronous context management."""
    
    def __init__(self, concurrent_config: ConcurrentConfig = None):
        # Load all QA data, grouped by conversation, for testing.
        self.qa_data = None  # To be initialized in an asynchronous method.
        self.conversation_groups = {}  # Data grouped by conversation.
        self.session_summaries = {}  # Conversation summary information.
        
        # Get the retrieval configuration manager.
        self.retrieval_config_manager = get_retrieval_config_manager()
        
        # Get the user group resolver and conversation loader.
        self.character_resolver = get_character_id_resolver()
        self.conversation_loader = get_conversation_loader()
        
        # Concurrent configuration.
        self.concurrent_config = concurrent_config or ConcurrentConfig()
        self.semaphore = asyncio.Semaphore(self.concurrent_config.max_concurrent_requests)
        
        # Statistical information.
        self.concurrent_stats = {
            'total_batches': 0,
            'successful_batches': 0,
            'failed_batches': 0,
            'total_retries': 0,
            'avg_batch_time': 0.0
        }
        
        # Conversation information mapping - will be dynamically retrieved from the database.
        self.conversation_speakers = {}
        
        # Resource management flag.
        self._is_initialized = False
    
    async def __aenter__(self):
        """Entry point for the asynchronous context manager."""
        await self._initialize_async_resources()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit point for the asynchronous context manager. Ensures resources are properly cleaned up."""
        await self._cleanup_resources()
    
    async def _initialize_async_resources(self):
        """Initializes asynchronous resources."""
        if self._is_initialized:
            return
            
        # Add other asynchronous initialization logic here.
        self._is_initialized = True
        print("✅ Tester asynchronous resources initialized.")
    
    async def _cleanup_resources(self):
        """Cleans up all resources (fast version, avoids blocking on Ctrl+C)."""
        if not self._is_initialized:
            return
            
        print("🧹 Quickly cleaning up resources...")
        
        try:
            # Quickly clean up, with timeout protection for each step.
            await self._force_cancel_remaining_tasks()
            await self._cleanup_database_connections()
            
            try:
                await asyncio.wait_for(self._cleanup_http_pools(), timeout=0.3)
            except asyncio.TimeoutError:
                print("⚠️ HTTP connection pool cleanup timed out.")
            except:
                pass
            
            self._is_initialized = False
            print("✅ Resources cleaned up.")
            
        except Exception as e:
            # A cleanup failure should not block exit.
            self._is_initialized = False
    
    async def _cleanup_http_pools(self):
        """Cleans up the HTTP connection pool."""
        try:
            # Clean up the global HTTP connection pool.
            from llm.core.async_http_pool import close_global_http_pool
            await close_global_http_pool()
            print("✅ Global HTTP connection pool closed.")
        except Exception as e:
            print(f"⚠️ HTTP connection pool cleanup failed: {e}")
    
    async def _cleanup_database_connections(self):
        """Cleans up database connections (fast version, avoids blocking on Ctrl+C)."""
        try:
            # 🔧 Critical fix: Clean up the UnifiedConnectionManager's monitoring tasks.
            try:
                from timem.core.unified_connection_manager import cleanup_unified_connection_manager
                await asyncio.wait_for(cleanup_unified_connection_manager(), timeout=1.0)
                print("✅ Unified connection pool manager closed (including monitoring tasks).")
            except asyncio.TimeoutError:
                print("⚠️ Unified connection pool manager closure timed out.")
            except Exception as e:
                print(f"⚠️ Unified connection pool manager closure failed: {e}")
            
            # Quickly close the old connection pool manager (for backward compatibility).
            try:
                from storage.connection_pool_manager import shutdown_connection_pool
                await asyncio.wait_for(shutdown_connection_pool(), timeout=0.5)
                print("✅ Old connection pool manager closed.")
            except asyncio.TimeoutError:
                print("⚠️ Old connection pool manager closure timed out. Skipping.")
            except:
                pass
            
            # Quickly dispose of PostgreSQL connections.
            try:
                from storage.postgres_store import get_postgres_store
                postgres_store = await get_postgres_store()
                if hasattr(postgres_store, 'engine') and postgres_store.engine:
                    await asyncio.wait_for(postgres_store.engine.dispose(), timeout=0.5)
                    print("✅ PostgreSQL connections cleaned up.")
            except asyncio.TimeoutError:
                print("⚠️ PostgreSQL cleanup timed out. Skipping.")
            except:
                pass
                
        except Exception as e:
            # A cleanup failure should not block exit.
            print(f"⚠️ Database connection cleanup exception: {e}")
    
    async def _force_cancel_remaining_tasks(self):
        """Force-cancels all remaining asynchronous tasks (fast version, avoids blocking on Ctrl+C)."""
        try:
            # Get all tasks in the current event loop.
            current_task = asyncio.current_task()
            all_tasks = [task for task in asyncio.all_tasks() if task != current_task and not task.done()]
            
            if all_tasks:
                print(f"🔄 Canceling {len(all_tasks)} unfinished tasks...")
                
                # Cancel all tasks without waiting.
                for task in all_tasks:
                    if not task.done():
                        task.cancel()
                
                # Quickly try to collect results without blocking.
                try:
                    await asyncio.wait(all_tasks, timeout=0.3, return_when=asyncio.ALL_COMPLETED)
                    print("✅ Tasks canceled.")
                except:
                    print("⚠️ Some tasks are still running, but this will not block exit.")
            
        except Exception as e:
            # A cleanup failure should not block exit.
            pass
    
    async def load_conversation_speakers_from_database(self):
        """Loads conversation speaker information from the database."""
        print("🔍 Loading conversation speaker information from the database...")
        print("=" * 60)
        
        try:
            from storage.postgres_store import get_postgres_store
            from sqlalchemy import text
            
            postgres_store = await get_postgres_store()
            
            async with postgres_store.get_session() as session:
                # Load conversation speaker information from the memory_sessions table, not the core_memories table.
                query = text("""
                SELECT DISTINCT
                    ms.id as session_id,
                    ms.user_id,
                    ms.expert_id,
                    u.username as user_name,
                    u.display_name as user_display,
                    c.name as expert_name,
                    c.display_name as expert_display,
                    c.character_type
                FROM memory_sessions ms
                LEFT JOIN users u ON ms.user_id = u.id
                LEFT JOIN characters c ON ms.expert_id = c.id
                WHERE ms.id LIKE 'conv-%'
                ORDER BY ms.id
                """)
                
                result = await session.execute(query)
                sessions = result.fetchall()
                
                print(f"📊 Found {len(sessions)} conversation sessions.")
                
                # Build the conversation-to-speaker mapping.
                for session in sessions:
                    # Extract conv_id from session_id (e.g., 'conv-26_session_1' -> 'conv-26').
                    session_id = session.session_id
                    if session_id.startswith('conv-'):
                        conv_id = session_id.split('_')[0]  # Extract the 'conv-26' part.
                    else:
                        continue
                    
                    user_id = session.user_id
                    expert_id = session.expert_id
                    user_name = session.user_display or session.user_name or f"Unknown_{user_id[:8]}"
                    expert_name = session.expert_display or session.expert_name or f"Unknown_{expert_id[:8]}"
                    
                    # Save the conversation-to-speaker mapping only once for each conversation to avoid duplicates.
                    if conv_id not in self.conversation_speakers:
                        self.conversation_speakers[conv_id] = {
                            "speaker_a": user_name,
                            "speaker_b": expert_name,
                            "speaker_a_id": user_id,
                            "speaker_b_id": expert_id
                        }
                        
                        print(f"✅ {conv_id}: {user_name} & {expert_name}")
                        print(f"   User ID: {user_id[:8]}...")
                        print(f"   Expert ID: {expert_id[:8]}...")
                        print(f"   Expert Type: {session.character_type}")
                
                print(f"📊 Successfully mapped {len(self.conversation_speakers)} conversations.")
                return True
                
        except Exception as e:
            print(f"❌ Failed to load conversation speaker information: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def load_qa_data(self, categories=[1, 2, 3, 4], limit=None):
        """
        Load all QA data for categories and group by conversation
        
        Args:
            categories: The categories to test.
            limit: The maximum number of questions per group. `None` means no limit.
        """
        print("🔄 Loading QA data and conversation summaries...")
        
        # First, load conversation speaker information from the database.
        print("🔍 Loading conversation speaker information from the database...")
        await self.load_conversation_speakers_from_database()
        
        # Load the QA data files.
        qa_files = [
            "data/locomo10_smart_split/locomo10_qa_001.json",
            "data/locomo10_smart_split/locomo10_qa_002.json", 
            "data/locomo10_smart_split/locomo10_qa_003.json",
            "data/locomo10_smart_split/locomo10_qa_004.json"
        ]
        
        all_qa_data = []
        for qa_file in qa_files:
            try:
                if os.path.exists(qa_file):
                    with open(qa_file, 'r', encoding='utf-8') as f:
                        qa_data = json.load(f)
                        all_qa_data.extend(qa_data)
                        print(f"✅ Loaded {qa_file}: {len(qa_data)} records.")
                else:
                    print(f"⚠️ File not found: {qa_file}")
            except Exception as e:
                print(f"❌ Failed to load {qa_file}: {e}")
        
        if not all_qa_data:
            print("❌ Unable to load QA data. Using fallback test cases.")
            return await self.get_fallback_test_cases()
        
        # Load conversation summary data.
        summary_file = "data/locomo10_smart_split/locomo10_field_session_summary.json"
        try:
            if os.path.exists(summary_file):
                with open(summary_file, 'r', encoding='utf-8') as f:
                    summary_data = json.load(f)
                    for item in summary_data:
                        sample_id = item.get("sample_id", "")
                        self.session_summaries[sample_id] = item.get("session_summary", {})
                print(f"✅ Loaded conversation summaries: {len(self.session_summaries)} conversations.")
            else:
                print(f"⚠️ Conversation summary file not found: {summary_file}")
        except Exception as e:
            print(f"❌ Failed to load conversation summaries: {e}")
        
        # Group by conversation and apply filters.
        self.conversation_groups = {}
        for qa_item in all_qa_data:
            # Get QA information - QA information is in the 'qa' field.
            qa_info = qa_item.get("qa", {})
            
            # Filter by category.
            category = qa_info.get("category")
            if category not in categories:
                continue
                
            source_record = qa_item.get("source_record", "")
            if not source_record:
                continue
                
            if source_record not in self.conversation_groups:
                self.conversation_groups[source_record] = []
            
            # Add the complete qa_item to the group, but ensure QA information is accessible.
            enhanced_item = qa_item.copy()
            enhanced_item.update({
                "question": qa_info.get("question", ""),
                "answer": qa_info.get("answer", ""),
                "expected_answer": qa_info.get("answer", ""),  # Use 'answer' as 'expected_answer'.
                "category": category,
                "evidence": qa_info.get("evidence", [])
            })
            
            self.conversation_groups[source_record].append(enhanced_item)
        
        # Apply the quantity limit.
        if limit is not None:
            for conv_id in self.conversation_groups:
                self.conversation_groups[conv_id] = self.conversation_groups[conv_id][:limit]
        
        # Display grouping statistics.
        print(f"\n📊 Data grouping statistics:")
        total_questions = 0
        for conv_id, questions in self.conversation_groups.items():
            print(f"  {conv_id}: {len(questions)} questions")
            total_questions += len(questions)
        print(f"  Total: {total_questions} questions")
        
        # Add user group information to QA data
        print(f"\n🔗 Adding user group information to the QA data...")
        await self.enhance_qa_data_with_user_groups()
        
        return self.conversation_groups
    
    async def enhance_qa_data_with_user_groups(self):
        """Adds user group information to the QA data."""
        enhanced_groups = {}
        
        for conv_id, questions in self.conversation_groups.items():
            if conv_id not in self.conversation_speakers:
                print(f"⚠️ Speaker information not found for {conv_id}. Skipping.")
                continue
            
            speakers = self.conversation_speakers[conv_id]
            speaker_a = speakers["speaker_a"]
            speaker_b = speakers["speaker_b"]
            speaker_a_id = speakers["speaker_a_id"]
            speaker_b_id = speakers["speaker_b_id"]
            
            # Directly use the character IDs obtained from the database.
            user_group_ids = [speaker_a_id, speaker_b_id]
            
            print(f"✅ {conv_id}: {speaker_a} & {speaker_b} (IDs: {user_group_ids})")
            
            # Add user group information to each question.
            enhanced_questions = []
            for question in questions:
                enhanced_question = question.copy()
                enhanced_question.update({
                    "speaker_a": speaker_a,
                    "speaker_b": speaker_b,
                    "speaker_a_id": speaker_a_id,
                    "speaker_b_id": speaker_b_id,
                    "user_group_ids": user_group_ids,
                    "session_summary": self.session_summaries.get(conv_id, {})
                })
                enhanced_questions.append(enhanced_question)
            
            enhanced_groups[conv_id] = enhanced_questions
        
        self.conversation_groups = enhanced_groups
        return enhanced_groups
    
    async def _monitor_connection_pool_health(self):
        """
        🔧 Engineering-level fix: Monitor connection pool health (proactive intervention).

        Engineering principles:
        - Monitor and record.
        - Trigger emergency cleanup when approaching exhaustion.
        - Prevent "too many clients" errors.
        """
        try:
            from storage.postgres_store import get_postgres_store
            postgres_store = await get_postgres_store()
            
            if hasattr(postgres_store, 'engine') and postgres_store.engine:
                pool = postgres_store.engine.pool
                if hasattr(pool, 'size'):
                    pool_size = pool.size()
                    checked_out = pool.checkedout()
                    checked_in = pool_size - checked_out
                    utilization = (checked_out / pool_size * 100) if pool_size > 0 else 0
                    
                    # 🔧 Proactive intervention: Trigger cleanup when utilization is too high.
                    if utilization > 90:
                        print(
                            f"⚠️ Connection pool is nearing exhaustion: {utilization:.1f}% "
                            f"(in use: {checked_out}, idle: {checked_in}, total: {pool_size})"
                        )
                        # Trigger an emergency cleanup.
                        await self._emergency_cleanup_sessions(postgres_store)
                        
                    elif utilization > 80:
                        print(
                            f"📊 High connection pool utilization: {utilization:.1f}% "
                            f"(in use: {checked_out}, idle: {checked_in})"
                        )
                    
                    # 🔧 Display session tracking statistics.
                    if hasattr(postgres_store, '_session_stats'):
                        stats = postgres_store._session_stats
                        print(
                            f"📊 Session statistics: opened={stats['total_opened']}, "
                            f"closed={stats['total_closed']}, "
                            f"leaked={stats['total_leaked']}, "
                            f"force_closed={stats['total_forced_closed']}"
                        )
                    
                    return {
                        "pool_size": pool_size,
                        "checked_out": checked_out,
                        "checked_in": checked_in,
                        "utilization_percent": utilization
                    }
        except Exception as e:
            # A monitoring failure should not affect the process.
            print(f"⚠️ Connection pool monitoring failed: {e}")
            pass
        
        return None
    
    async def _emergency_cleanup_sessions(self, postgres_store):
        """🔧 Engineering-level fix: Perform an emergency cleanup of leaked sessions."""
        try:
            print("🚨 Triggering emergency session cleanup...")
            
            # Clean up leaked sessions.
            if hasattr(postgres_store, '_cleanup_leaked_sessions'):
                await postgres_store._cleanup_leaked_sessions()
                print("✅ Emergency cleanup complete.")
            
            # Wait for the connection to be released.
            await asyncio.sleep(1.0)
            
        except Exception as e:
            print(f"❌ Emergency cleanup failed: {e}")
    
    async def _cleanup_batch_sessions(self):
        """🔧 Engineering-level fix: Force-clean all sessions between batches."""
        try:
            print("🧹 Performing inter-batch session cleanup...")
            
            from storage.postgres_store import get_postgres_store
            postgres_store = await get_postgres_store()
            
            # Force-clean all leaked sessions.
            if hasattr(postgres_store, '_cleanup_leaked_sessions'):
                await postgres_store._cleanup_leaked_sessions()
            
            # Wait for connections to be fully released.
            await asyncio.sleep(1.0)
            
            print("✅ Inter-batch cleanup complete.")
            
        except Exception as e:
            print(f"⚠️ Inter-batch cleanup failed: {e}")
    
    
    
    async def run_memory_retrieval_with_metrics(self, retrieval_request: Dict[str, Any], 
                                               perf_metrics: PerformanceMetrics, 
                                               debug_mode: bool = False):
        """Executes memory retrieval with performance monitoring."""
        try:
            # Mark the overall start time.
            workflow_start_time = time.perf_counter()
            
            # Run the retrieval workflow.
            result = await run_memory_retrieval(retrieval_request, debug_mode=debug_mode)
            
            # Mark the overall end time.
            workflow_end_time = time.perf_counter()
            total_workflow_time = workflow_end_time - workflow_start_time
            
            # Extract detailed time breakdown information from the results.
            retrieval_metadata = result.get('retrieval_metadata', {})
            strategy_performance = retrieval_metadata.get('strategy_performance', {})
            
            # Calculate the time for each stage.
            # 1. Extract retrieval time (get the actual retriever execution time from strategy_performance).
            pure_retrieval_time = 0.0
            if strategy_performance:
                # Get the execution time for all retrievers.
                for key, value in strategy_performance.items():
                    if isinstance(value, (int, float)) and value > 0:
                        pure_retrieval_time = max(pure_retrieval_time, value)
            
            # If strategy_performance is not available, use the time from retrieval_metadata.
            if pure_retrieval_time == 0.0:
                pure_retrieval_time = retrieval_metadata.get('retrieval_time', total_workflow_time * 0.7)
            
            # 2. Estimate LLM time (total time - retrieval time).
            # Empirical estimate: intent understanding LLM ~30%, QA LLM ~70%.
            estimated_llm_total_time = total_workflow_time - pure_retrieval_time
            estimated_intent_llm_time = estimated_llm_total_time * 0.3  # For intent understanding.
            estimated_qa_llm_time = estimated_llm_total_time * 0.7      # For answer generation.
            
            # Ensure the time is reasonable.
            estimated_llm_total_time = max(0.1, estimated_llm_total_time)
            estimated_intent_llm_time = max(0.05, estimated_intent_llm_time)
            estimated_qa_llm_time = max(0.05, estimated_qa_llm_time)
            
            # Update performance metrics.
            perf_metrics.end_retrieval()
            
            # Manually set a more accurate time breakdown.
            # Set the retrieval time.
            perf_metrics.retrieval_start_time = workflow_start_time
            perf_metrics.retrieval_end_time = workflow_start_time + pure_retrieval_time
            perf_metrics.metrics['retrieval_time'] = pure_retrieval_time
            
            # Set the LLM time.
            llm_start_time = workflow_start_time + pure_retrieval_time
            perf_metrics.llm_first_response_time = llm_start_time + estimated_intent_llm_time
            perf_metrics.llm_generation_start_time = llm_start_time + estimated_intent_llm_time
            perf_metrics.llm_generation_end_time = llm_start_time + estimated_llm_total_time
            
            perf_metrics.metrics['llm_first_response_delay'] = estimated_intent_llm_time
            perf_metrics.metrics['llm_generation_time'] = estimated_qa_llm_time  
            perf_metrics.metrics['llm_total_time'] = estimated_llm_total_time
            
            # Try to get token usage information.
            if 'usage' in result:
                usage = result['usage']
                perf_metrics.update_token_usage(
                    input_tokens=usage.get('prompt_tokens', 0),
                    output_tokens=usage.get('completion_tokens', 0)
                )
            elif 'token_usage' in result:
                usage = result['token_usage']
                perf_metrics.update_token_usage(
                    input_tokens=usage.get('input_tokens', 0),
                    output_tokens=usage.get('output_tokens', 0)
                )
            
            # Update retrieval statistics.
            memories = result.get('retrieved_memories', [])
            formatted_memories = result.get('formatted_context_memories', [])
            perf_metrics.update_retrieval_stats(memories, formatted_memories)
            
            # Update answer statistics.
            answer = result.get('answer', '')
            confidence = result.get('confidence', 0.0)
            perf_metrics.update_answer_stats(answer, confidence)
            
            # Add debug information.
            if debug_mode:
                print(f"🔍 Time breakdown debug:")
                print(f"  Total workflow time: {total_workflow_time:.3f}s")
                print(f"  Pure retrieval time: {pure_retrieval_time:.3f}s") 
                print(f"  LLM total time: {estimated_llm_total_time:.3f}s")
                print(f"    - Intent understanding: {estimated_intent_llm_time:.3f}s")
                print(f"    - Answer generation: {estimated_qa_llm_time:.3f}s")
                print(f"  Strategy performance: {strategy_performance}")
            
            return result
            
        except Exception as e:
            # End monitoring even if an error occurs.
            perf_metrics.end_retrieval()
            perf_metrics.end_test()
            raise e
    
    async def get_fallback_test_cases(self):
        """Provides fallback test cases (the first 10 original questions with user group mapping)."""
        print("🔄 Using fallback test cases.")
        
        # First, get user group information for conv-26.
        try:
            user_group = await self.character_resolver.resolve_user_group(
                conversation_id="conv-26",
                speaker_a="Caroline", 
                speaker_b="Melanie"
            )
            
            if user_group:
                print(f"✅ Successfully obtained conv-26 user group information: {user_group.speaker_a}({user_group.speaker_a_id}) & {user_group.speaker_b}({user_group.speaker_b_id}).")
                user_group_ids = list(user_group.user_group_ids)
                speaker_a = user_group.speaker_a
                speaker_b = user_group.speaker_b
                speaker_a_id = user_group.speaker_a_id
                speaker_b_id = user_group.speaker_b_id
            else:
                print("⚠️ Unable to obtain conv-26 user group information. Using empty values.")
                user_group_ids = []
                speaker_a = "Caroline"
                speaker_b = "Melanie" 
                speaker_a_id = None
                speaker_b_id = None
                
        except Exception as e:
            print(f"❌ Failed to obtain conv-26 user group information: {e}.")
            user_group_ids = []
            speaker_a = "Caroline"
            speaker_b = "Melanie"
            speaker_a_id = None
            speaker_b_id = None
        
        fallback_questions = [
            {
                "question": "When did Caroline go to the LGBTQ support group?",
                "expected_answer": "7 May 2023",
                "category": 2,
                "evidence": ["D1:3"],
                "question_id": "Q1"
            },
            {
                "question": "When did Melanie paint a sunrise?",
                "expected_answer": "2022",
                "category": 2,
                "evidence": ["D1:12"],
                "question_id": "Q2"
            },
            {
                "question": "What fields would Caroline be likely to pursue in her education?",
                "expected_answer": "Psychology, counseling certification",
                "category": 3,
                "evidence": ["D1:9", "D1:11"],
                "question_id": "Q3"
            },
            {
                "question": "What did Caroline research?",
                "expected_answer": "Adoption agencies",
                "category": 1,
                "evidence": ["D2:8"],
                "question_id": "Q4"
            },
            {
                "question": "What is Caroline's identity?",
                "expected_answer": "Transgender woman",
                "category": 1,
                "evidence": ["D1:5"],
                "question_id": "Q5"
            },
            {
                "question": "When did Melanie run a charity race?",
                "expected_answer": "The sunday before 25 May 2023",
                "category": 2,
                "evidence": ["D2:1"],
                "question_id": "Q6"
            },
            {
                "question": "When is Melanie planning on going camping?",
                "expected_answer": "June 2023",
                "category": 2,
                "evidence": ["D2:7"],
                "question_id": "Q7"
            },
            {
                "question": "What is Caroline's relationship status?",
                "expected_answer": "Single",
                "category": 1,
                "evidence": ["D3:13", "D2:14"],
                "question_id": "Q8"
            },
            {
                "question": "When did Caroline give a speech at a school?",
                "expected_answer": "The week before 9 June 2023",
                "category": 2,
                "evidence": ["D3:1"],
                "question_id": "Q9"
            },
            {
                "question": "When did Caroline meet up with her friends, family, and mentors?",
                "expected_answer": "The week before 9 June 2023",
                "category": 2,
                "evidence": ["D3:11"],
                "question_id": "Q10"
            }
        ]
        
        # Add user group information to each test case.
        enhanced_fallback_cases = []
        for test_case in fallback_questions:
            enhanced_case = test_case.copy()
            enhanced_case.update({
                "source_record": "conv-26",
                "speaker_a": speaker_a,
                "speaker_b": speaker_b,
                "speaker_a_id": speaker_a_id,
                "speaker_b_id": speaker_b_id,
                "user_group_ids": user_group_ids,
                "user_group": None  # A complete UserGroup object can be set if needed.
            })
            enhanced_fallback_cases.append(enhanced_case)
        
        print(f"🔄 Fallback test cases have been enhanced with {len(enhanced_fallback_cases)} questions.")
        if user_group_ids:
            print(f"👥 User group information: {speaker_a} & {speaker_b} (IDs: {user_group_ids}).")
        else:
            print("⚠️ User group ID is empty. Please check the character registration status.")
            
        return enhanced_fallback_cases
    
    def _should_retry_result(self, result: Dict[str, Any], errors: List, warnings: List, 
                           answer: str, memories: List, retry_count: int, 
                           enable_smart_retry: bool = True) -> tuple[bool, str]:
        """
        Intelligently determines whether a retry is necessary.

        Optimization notes:
        - 🔧 COT format priority: If the COT format is valid, it means the LLM understood and responded correctly, so it should not be retried just because the answer is short.
        - 🔧 Allow short answers: Supports valid short answers like "No," "Yes," "2022," etc.
        - Relax confidence filtering: Lowered from 0.3 to 0.05, and confidence is not checked when the COT format is valid.
        - Optimized memory count check: Retry only when there are no memories and the answer is empty.
        - Added success protection: If the COT format is valid or intent understanding is successful, minor retry conditions are ignored.
        - Added retry limit: Avoids infinite retries by stopping within a reasonable range.

        Retry trigger conditions (from highest to lowest priority):
        1. Obvious errors are present.
        2. A technical issue is detected in the answer.
        3. Intent understanding has failed (no retrieval results).
        4. The answer is completely empty.
        5. The retrieval strategy execution has failed.
        6. The COT format is invalid AND the answer is too short (< 3 characters).
        7. Confidence is extremely low (< 0.05) AND the COT format is invalid AND the answer is empty.
        
        Args:
            result: The retrieval result.
            errors: A list of errors.
            warnings: A list of warnings.
            answer: The generated answer.
            memories: The retrieved memories.
            retry_count: The current retry count.
            
        Returns:
            (A boolean indicating whether to retry, The reason for retrying)
        """
        # Check retry conditions.
        retry_reasons = []
        
        # If smart retry is not enabled, only check for basic error conditions.
        if not enable_smart_retry:
            # Retry only if there are obvious errors.
            if errors:
                retry_reasons.append(f"Detected {len(errors)} errors")
        else:
            # Smart retry: Check for various quality issues.
            # 1. Retry on error.
            if errors:
                retry_reasons.append(f"Detected {len(errors)} errors")
            
            # 2. Retry when there are no retrieval results (intent understanding failed).
            # However, cases where the memory refiner correctly filtered results should be excluded.
            if not memories or len(memories) == 0:
                # Check if memory refining was performed.
                retrieval_metadata = result.get('retrieval_metadata', {})
                memory_refined = result.get('memory_refined', False)
                memory_refiner_failed = result.get('memory_refiner_failed', False)
                original_memory_count = result.get('original_memory_count', 0)
                
                # If the memory refiner successfully filtered memories and the original memory count was > 0, do not retry.
                if memory_refined and not memory_refiner_failed and original_memory_count > 0:
                    print(f"✅ Relevance analyzer correctly filtered memories: {original_memory_count} -> 0.")
                    # Do not add a retry reason, as this is a normal result of relevance filtering.
                else:
                    # This indicates a true intent understanding failure or memory refining failure.
                    if retry_count == 0:
                        retry_reasons.append("Intent understanding failed - no retrieval results (requires reprocessing from the beginning).")
                    else:
                        retry_reasons.append(f"Still no retrieval results after {retry_count} retries.")
            
            # 3. Detect answers indicating technical issues (high-priority retry condition).
            if answer and ("Sorry, a technical issue occurred during answer generation" in answer or 
                          "Sorry, an error occurred while processing your request" in answer or
                          "technical issue" in answer):
                retry_reasons.append(f"Detected an answer indicating a technical issue. Retrying.")
            
            # 4. Check if the COT format is valid.
            # 🔧 Key improvement: If the COT format is valid, it means the LLM understood and responded in the correct format, so it should not be retried just because the answer is short.
            cot_format_valid = result.get('cot_format_valid', False)
            use_single_cot = result.get('use_single_cot', False)
            
            # 5. Retry if the answer is empty (but exclude cases where the COT format is valid).
            # If COT is used and the format is valid, even a short answer is considered valid (e.g., "No," "Yes," "2022").
            if not answer or len(answer.strip()) == 0:
                # Retry only if the answer is completely empty.
                retry_reasons.append(f"Answer is completely empty.")
            elif not cot_format_valid and len(answer.strip()) < 3:
                # Only retry due to a short answer if the COT format is invalid.
                retry_reasons.append(f"Answer is too short and COT format is invalid (length: {len(answer)}).")
            
            # 6. Retry when the number of memories is unusually low (but don't be too strict).
            # Only retry if there are no memories and the answer is also empty.
            # 🔧 Improvement: Exclude cases where memory refining correctly filtered results, and only check if the answer is empty.
            if (not memories or len(memories) == 0) and (not answer or len(answer.strip()) == 0):
                # Double-check if this is a correct filtering by the memory refining.
                retrieval_metadata = result.get('retrieval_metadata', {})
                memory_refined = result.get('memory_refined', False)
                memory_refiner_failed = result.get('memory_refiner_failed', False)
                original_memory_count = result.get('original_memory_count', 0)
                
                if not (memory_refined and not memory_refiner_failed and original_memory_count > 0):
                    # Only add a retry reason if it was not a correct filtering by the memory refining.
                    retry_reasons.append(f"No memories and the answer is empty ({len(memories)} memories).")
            
            # 7. Retry on low confidence - switch to more lenient conditions.
            # 🔧 Improvement: If the COT format is valid, do not retry even if confidence is low.
            confidence = result.get('confidence', 1.0)
            # Only retry if confidence is extremely low (< 0.05), the COT format is invalid, and the answer is empty.
            if confidence < 0.05 and not cot_format_valid and (not answer or len(answer.strip()) == 0):
                retry_reasons.append(f"Confidence is extremely low and the answer is invalid ({confidence:.2f}).")
            
            # 8. Retry on retrieval strategy failure.
            retrieval_metadata = result.get('retrieval_metadata', {})
            if retrieval_metadata.get('retrieval_failed', False):
                retry_reasons.append("Retrieval strategy execution failed.")
            
            # 9. Retry if more than half of the retrieved memories have an "unknown" source (but ignore if the COT format is valid).
            if not cot_format_valid and memories and len(memories) > 0:
                unknown_sources = sum(1 for m in memories if m.get('retrieval_source') == 'unknown')
                if unknown_sources > len(memories) / 2:
                    retry_reasons.append(f"Memory sources are unclear ({unknown_sources}/{len(memories)}).")
            
            # 10. If the COT format is valid or intent understanding was successful, retry more cautiously.
            # Avoid retrying an already successful result for a minor issue.
            if (cot_format_valid or (memories and len(memories) > 0 and answer and len(answer.strip()) > 0)):
                # If the COT format is valid or if there are already memories and an answer, only keep critical retry conditions.
                critical_retry_reasons = []
                for reason in retry_reasons:
                    if any(keyword in reason for keyword in ["error", "technical issue", "strategy failed", "completely empty", "intent understanding failed"]):
                        critical_retry_reasons.append(reason)
                
                # If there are only non-critical reasons, clear the retry reasons.
                if not critical_retry_reasons and len(retry_reasons) > 0:
                    if cot_format_valid:
                        print(f"✅ COT format is valid. Ignoring minor retry conditions: {retry_reasons}")
                    else:
                        print(f"✅ Intent understanding was successful. Ignoring minor retry conditions: {retry_reasons}")
                    retry_reasons = critical_retry_reasons
        
        # Decide whether to retry.
        should_retry = bool(retry_reasons) and retry_count < self.concurrent_config.max_retries
        
        # Fix: Remove incorrect early-stopping logic.
        # As long as there is a reason to retry and the maximum number of retries has not been reached, it should continue.
        # It should not stop retrying just because there are partial memories or an answer, as other parts of the process may still have issues.
        retry_reason = "; ".join(retry_reasons) if retry_reasons else "No retry needed."
        
        # Add debug information to help understand the reason for retrying.
        if should_retry:
            print(f"🔄 Retry decision: Retrying for the {retry_count + 1} time.")
            print(f"   Reason: {retry_reason}")
            print(f"   Answer length: {len(answer) if answer else 0}")
            print(f"   Number of memories: {len(memories) if memories else 0}")
            print(f"   Confidence: {result.get('confidence', 1.0):.3f}")
            print(f"   Number of errors: {len(errors) if errors else 0}")
        else:
            print(f"✅ No retry needed: {retry_reason}")
        
        return should_retry, retry_reason
    
    def _adjust_retry_config(self, retrieval_config: Dict[str, Any], retry_count: int, 
                           has_no_results: bool = False) -> Dict[str, Any]:
        """
        Adjusts retrieval configuration parameters based on the number of retries and failure reasons to improve the success rate.

        Args:
            retrieval_config: The original retrieval configuration.
            retry_count: The number of retries.
            has_no_results: Whether the retry is due to a complete lack of retrieval results (intent understanding failure).

        Returns:
            The adjusted retrieval configuration.
        """
        # Copy the configuration to avoid modifying the original.
        adjusted_config = retrieval_config.copy()
        
        if has_no_results:
            # Strategy for handling intent understanding failure: perform a full retry without changing any configuration.
            print(f"🔄 Intent understanding failure retry strategy: Full retry, keeping original configuration unchanged (retry {retry_count}).")
            print(f"   - Keep user group filtering: Enabled")
            print(f"   - Keep retrieval strategy: Unchanged")
            print(f"   - Keep retrieval parameters: Unchanged")
            print(f"   - Re-passing question and character IDs to continue execution.")
            
            # Do not modify any configuration; return the original configuration directly.
            return adjusted_config
                
        else:
            # Original progressive retry strategy (for cases with partial but low-quality results).
            if retry_count == 1:
                # Increase the number of retrievals.
                hierarchical = adjusted_config.get('hierarchical', {}).copy()
                layer_limits = hierarchical.get('layer_limits', {}).copy()
                final_limits = hierarchical.get('final_limits', {}).copy()
                
                layer_limits['L1'] = min(30, int(layer_limits.get('L1', 20) * 1.5))
                layer_limits['L2'] = min(5, layer_limits.get('L2', 3) + 2)
                final_limits['L1'] = min(8, final_limits.get('L1', 5) + 3)
                final_limits['L2'] = min(3, final_limits.get('L2', 1) + 2)
                
                hierarchical['layer_limits'] = layer_limits
                hierarchical['final_limits'] = final_limits
                adjusted_config['hierarchical'] = hierarchical
                
            elif retry_count == 2:
                # Lower the threshold.
                semantic = adjusted_config.get('semantic', {}).copy()
                semantic['score_threshold'] = max(0.1, semantic.get('score_threshold', 0.3) - 0.1)
                adjusted_config['semantic'] = semantic
                
                global_config = adjusted_config.get('global', {}).copy()
                global_config['score_threshold_global'] = max(0.1, global_config.get('score_threshold_global', 0.3) - 0.1)
                adjusted_config['global'] = global_config
                
            elif retry_count >= 3:
                # Enable more retrieval strategies.
                temporal = adjusted_config.get('temporal', {}).copy()
                temporal['top_k'] = max(temporal.get('top_k', 8), 12)
                temporal['time_window_days'] = max(temporal.get('time_window_days', 30), 60)
                adjusted_config['temporal'] = temporal
                
                keyword = adjusted_config.get('keyword', {}).copy()
                keyword['top_k'] = max(keyword.get('top_k', 10), 15)
                keyword['min_match_score'] = max(0.1, keyword.get('min_match_score', 0.2) - 0.1)
                adjusted_config['keyword'] = keyword
        
        return adjusted_config
    
    def _build_test_result_from_last_attempt(self, test_case: Dict[str, Any], conv_id: str,
                                           question_index: int, global_question_index: int,
                                           last_result: Dict[str, Any], success: bool, 
                                           status: str, retry_count: int, last_error: str) -> Dict[str, Any]:
        """Builds a test result from the last attempt."""
        # Extract information from the last result.
        answer = last_result.get('answer', '')
        memories = last_result.get('retrieved_memories', [])
        errors = last_result.get('errors', [])
        warnings = last_result.get('warnings', [])
        retrieval_metadata = last_result.get('retrieval_metadata', {})
        
        # Build memory details....
        memory_details = []
        formatted_memories = last_result.get('formatted_context_memories', [])
        
        if memories:
            for j, memory in enumerate(memories, 1):
                memory_details.append({
                    "rank": j,
                    "memory_id": memory.get('id', 'N/A'),
                    "title": memory.get('title', 'N/A'),
                    "level": memory.get('level', 'Unknown'),
                    "score": memory.get('fused_score', 0.0),
                    "session_id": memory.get('session_id', 'N/A'),
                    "user_id": memory.get('user_id', 'N/A'),
                    "expert_id": memory.get('expert_id', 'N/A'),
                    "content": memory.get('content', '')
                })
        
        # Collect memory retrieval details....
        memory_retrieval_details = []
        for memory in memories:
            memory_detail = {
                "memory_id": memory.get('id', 'N/A'),
                "retrieval_strategy": memory.get('retrieval_strategy', 'unknown'),
                "retrieval_source": memory.get('retrieval_source', 'unknown'),
                "matched_keywords": memory.get('matched_keywords', []),
                "level": memory.get('level', 'Unknown'),
                "score": memory.get('fused_score', 0.0)
            }
            memory_retrieval_details.append(memory_detail)
        
        # Build the complete test result.
        test_result = {
            "test_info": {
                "question": test_case['question'],
                "expected_answer": test_case['expected_answer'],
                "category": test_case.get('category', 4),
                "evidence": test_case.get('evidence', []),
                "source_record": test_case.get('source_record', ''),
                "speaker_a": test_case.get('speaker_a', ''),
                "speaker_b": test_case.get('speaker_b', ''),
                "user_group_ids": test_case.get('user_group_ids', []),
                "conversation_id": conv_id,
                "question_index": question_index,
                "global_question_index": global_question_index
            },
            "execution": {
                "success": success,
                "execution_time": 0.0,  # Unable to get an accurate time.
                "confidence": last_result.get('confidence', 0.0),
                "status": status,
                "retry_count": retry_count,
                "retry_reason": last_error
            },
            "response": {
                "answer": answer,
                "answer_length": len(answer)
            },
            "formatted_memories": {
                "count": len(formatted_memories),
                "content": formatted_memories
            },
            "memories": {
                "total_count": len(memories),
                "l1_count": len([m for m in memories if m.get('level') == 'L1']),
                "l2_count": len([m for m in memories if m.get('level') == 'L2']),
                "details": memory_details
            },
            "retrieval_info": {
                "primary_strategy": retrieval_metadata.get('retrieval_strategy', 'unknown'),
                "strategies_used": retrieval_metadata.get('strategies_used', []),
                "llm_keywords": retrieval_metadata.get('llm_keywords', []),
                "query_category": str(retrieval_metadata.get('query_category', 'unknown')),
                "query_complexity": str(retrieval_metadata.get('query_complexity', 'unknown')),
                "memory_retrieval_details": memory_retrieval_details,
                "strategy_performance": retrieval_metadata.get('strategy_performance', {}),
                "retrieval_description": retrieval_metadata.get('retrieval_description', '')
            },
            "performance_metrics": {},  # Empty performance metrics....
            "issues": {
                "errors": errors,
                "warnings": warnings
            },
            # 🔧 Add COT-related fields
            "use_single_cot": last_result.get('use_single_cot', False),
            "cot_full_response": last_result.get('cot_full_response', ''),
            "cot_format_valid": last_result.get('cot_format_valid', False),
            "cot_retry_count": last_result.get('cot_retry_count', 0),
            "cot_reasoning": last_result.get('cot_reasoning', ''),
            # Relevance filtering fields
            "memory_refined": last_result.get('memory_refined', False),
            "original_memory_count": last_result.get('original_memory_count', 0),
            "refined_memory_count": last_result.get('refined_memory_count', 0),
            "refinement_retention_rate": last_result.get('refinement_retention_rate', 0.0),
            "memory_refiner_metadata": last_result.get('memory_refiner_metadata', {})
        }
        
        return test_result
    
    async def execute_single_test_case(self, test_case: Dict[str, Any], conv_id: str, 
                                     question_index: int, global_question_index: int,
                                     retrieval_config: Dict[str, Any], 
                                     debug_timing: bool = False) -> Dict[str, Any]:
        """Executes a single test case asynchronously with an enhanced retry mechanism."""
        async with self.semaphore:  # Control concurrency.
            retry_count = 0
            last_error = None
            last_result = None
            
            while retry_count <= self.concurrent_config.max_retries:
                # 🔧 Monitor connection pool health before each retry.
                if retry_count > 0:
                    await self._monitor_connection_pool_health()
                
                try:
                    # Create a performance monitor.
                    perf_metrics = PerformanceMetrics()
                    perf_metrics.start_test()
                    
                    # Build the retrieval request with user group isolation information.
                    retrieval_request = {
                        "question": test_case['question'],
                        "context": {},
                        "retrieval_config": retrieval_config
                    }
                    
                    # Add user group isolation information.
                    if test_case.get('user_group_ids'):
                        retrieval_request["user_group_ids"] = test_case['user_group_ids']
                        retrieval_request["user_group_filter"] = {
                            "enabled": True,
                            "user_ids": test_case['user_group_ids'],
                            "conversation_id": test_case.get('source_record', ''),
                            "speaker_a": test_case.get('speaker_a', ''),
                            "speaker_b": test_case.get('speaker_b', ''),
                            "speaker_a_id": test_case.get('speaker_a_id', ''),
                            "speaker_b_id": test_case.get('speaker_b_id', '')
                        }
                    
                    # Start the retrieval phase.
                    perf_metrics.start_retrieval()
                    
                    # Wrap the retrieval execution with a timeout.
                    result = await asyncio.wait_for(
                        self.run_memory_retrieval_with_metrics(
                            retrieval_request, perf_metrics, debug_mode=debug_timing
                        ),
                        timeout=self.concurrent_config.timeout
                    )
                    
                    # End performance monitoring.
                    perf_metrics.end_test()
                    
                    execution_time = perf_metrics.metrics['total_execution_time']
                    
                    # Extract retrieval metadata.
                    retrieval_metadata = result.get('retrieval_metadata', {})
                    
                    # Analyze the results.
                    strategies_used = retrieval_metadata.get('strategies_used', [])
                    retrieval_strategy = retrieval_metadata.get('retrieval_strategy', 'unknown')
                    llm_keywords = retrieval_metadata.get('llm_keywords', [])
                    query_category = retrieval_metadata.get('query_category', 'unknown')
                    query_complexity = retrieval_metadata.get('query_complexity', 'unknown')
                    
                    # Get the complete answer.
                    answer = result.get('answer', '')
                    
                    # Analyze the retrieved memories.
                    memories = result.get('retrieved_memories', [])
                    memory_details = []
                    
                    # Display formatted memory content.
                    formatted_memories = result.get('formatted_context_memories', [])
                    
                    if memories:
                        # Save memory details to the result.
                        for j, memory in enumerate(memories, 1):
                            memory_details.append({
                                "rank": j,
                                "memory_id": memory.get('id', 'N/A'),
                                "title": memory.get('title', 'N/A'),
                                "level": memory.get('level', 'Unknown'),
                                "score": memory.get('fused_score', 0.0),
                                "session_id": memory.get('session_id', 'N/A'),
                                "user_id": memory.get('user_id', 'N/A'),
                                "expert_id": memory.get('expert_id', 'N/A'),
                                "content": memory.get('content', '')
                            })
                    
                    # Check for errors and warnings.
                    errors = result.get('errors', [])
                    warnings = result.get('warnings', [])
                    
                    # Evaluate the test results.
                    basic_success = not bool(errors) and len(answer) > 0 and len(memories) > 0
                    
                    # Smart retry decision: even a basic success may require a retry.
                    # Note: ENABLE_SMART_RETRY is defined in the main function and passed in from outside.
                    # For simplicity, this is temporarily hardcoded as True but can be passed as a parameter later.
                    should_retry, retry_reason = self._should_retry_result(
                        result, errors, warnings, answer, memories, retry_count, enable_smart_retry=True
                    )
                    
                    # If a retry is needed, save the current result and continue the retry loop.
                    if should_retry:
                        last_result = result
                        last_error = f"Poor result quality requires a retry: {retry_reason}"
                        self.concurrent_stats['total_retries'] += 1
                        
                        # Check if the retry is due to no retrieval results (intent understanding failed).
                        has_no_results = not memories or len(memories) == 0
                        # Check if the retry is due to a technical error in the answer.
                        is_technical_error = answer and ("Sorry, a technical issue occurred during answer generation" in answer or 
                                                        "Sorry, an error occurred while processing your request" in answer or
                                                        "technical issue" in answer)
                        
                        if has_no_results:
                            print(f"🔄 Detected intent understanding failure. Enabling full reprocessing strategy (retry {retry_count + 1}).")
                        elif is_technical_error:
                            print(f"⚠️ Detected a technical error in the answer. Enabling enhanced retry strategy (retry {retry_count + 1}).")
                            print(f"   Technical error content: {answer[:100]}..." if len(answer) > 100 else f"   Technical error content: {answer}")
                        
                        # Adjust configuration parameters for the next retry.
                        retrieval_config = self._adjust_retry_config(
                            retrieval_config, retry_count + 1, has_no_results=has_no_results
                        )
                        
                        retry_count += 1
                        if retry_count <= self.concurrent_config.max_retries:
                            delay_index = min(retry_count - 1, len(self.concurrent_config.retry_delays) - 1)
                            retry_delay = self.concurrent_config.retry_delays[delay_index]
                            if is_technical_error:
                                print(f"⏳ Technical error retry. Waiting {retry_delay}s before retry {retry_count}...")
                            else:
                                print(f"⏳ Retrying... waiting {retry_delay}s...")
                            await asyncio.sleep(retry_delay)
                        continue  # Continue the retry loop.
                    
                    # Determine the final success status and status description.
                    success = basic_success
                    status = "✅ Success" if success else "⚠️ Partial success" if len(answer) > 0 else "❌ Failed"
                    
                    # If there is a retry history, reflect it in the status.
                    if retry_count > 0:
                        # Determine the retry type.
                        if not memories or len(memories) == 0:
                            retry_type = "Intent understanding retry"
                        elif answer and ("Sorry, a technical issue occurred during answer generation" in answer or 
                                        "Sorry, an error occurred while processing your request" in answer or
                                        "technical issue" in answer):
                            retry_type = "Technical error retry"
                        else:
                            retry_type = "Quality optimization retry"
                        
                        status += f" (successful after {retry_type} {retry_count} times)"
                        print(f"✅ Retry successful: obtained result after {retry_type} {retry_count} times.")
                        print(f"   - Final memory count: {len(memories)}.")
                        print(f"   - Final answer length: {len(answer)} characters.")
                        print(f"   - Final confidence: {result.get('confidence', 0.0):.3f}.")
                    
                    # Collect the retrieval source and matched keywords for each memory.
                    memory_retrieval_details = []
                    for memory in memories:
                        memory_detail = {
                            "memory_id": memory.get('id', 'N/A'),
                            "retrieval_strategy": memory.get('retrieval_strategy', 'unknown'),
                            "retrieval_source": memory.get('retrieval_source', 'unknown'),
                            "matched_keywords": memory.get('matched_keywords', []),
                            "level": memory.get('level', 'Unknown'),
                            "score": memory.get('fused_score', 0.0)
                        }
                        memory_retrieval_details.append(memory_detail)
                    
                    # Record detailed results (including performance metrics and retrieval strategy information)
                    test_result = {
                        "test_info": {
                            "question": test_case['question'],
                            "expected_answer": test_case['expected_answer'],
                            "category": test_case.get('category', 4),
                            "evidence": test_case.get('evidence', []),
                            "source_record": test_case.get('source_record', ''),
                            "speaker_a": test_case.get('speaker_a', ''),
                            "speaker_b": test_case.get('speaker_b', ''),
                            "user_group_ids": test_case.get('user_group_ids', []),
                            "conversation_id": conv_id,
                            "question_index": question_index,
                            "global_question_index": global_question_index
                        },
                        "execution": {
                            "success": success,
                            "execution_time": execution_time,
                            "confidence": result.get('confidence', 0.0),
                            "status": status,
                            "retry_count": retry_count
                        },
                        "response": {
                            "answer": answer,
                            "answer_length": len(answer)
                        },
                        "formatted_memories": {
                            "count": len(formatted_memories),
                            "content": formatted_memories
                        },
                        "memories": {
                            "total_count": len(memories),
                            "l1_count": len([m for m in memories if m.get('level') == 'L1']),
                            "l2_count": len([m for m in memories if m.get('level') == 'L2']),
                            "details": memory_details
                        },
                        "retrieval_info": {
                            "primary_strategy": retrieval_strategy,
                            "strategies_used": strategies_used,
                            "llm_keywords": llm_keywords,
                            "query_category": str(query_category) if query_category is not None else 'unknown',
                            "query_complexity": str(query_complexity) if query_complexity is not None else 'unknown',
                            "memory_retrieval_details": memory_retrieval_details,
                            "strategy_performance": retrieval_metadata.get('strategy_performance', {}),
                            "retrieval_description": retrieval_metadata.get('retrieval_description', '')
                        },
                        "performance_metrics": perf_metrics.get_metrics_dict(),
                        "issues": {
                            "errors": errors,
                            "warnings": warnings
                        },
                        # 🔧 Add COT-related fields
                        "use_single_cot": result.get('use_single_cot', False),
                        "cot_full_response": result.get('cot_full_response', ''),
                        "cot_format_valid": result.get('cot_format_valid', False),
                        "cot_retry_count": result.get('cot_retry_count', 0),
                        "cot_reasoning": result.get('cot_reasoning', ''),
                        # Relevance filtering fields
                        "memory_refined": result.get('memory_refined', False),
                        "original_memory_count": result.get('original_memory_count', 0),
                        "refined_memory_count": result.get('refined_memory_count', 0),
                        "refinement_retention_rate": result.get('refinement_retention_rate', 0.0),
                        "memory_refiner_metadata": result.get('memory_refiner_metadata', {})
                    }
                    
                    return test_result
                    
                except asyncio.TimeoutError as e:
                    last_error = f"Timeout after {self.concurrent_config.timeout}s"
                    self.concurrent_stats['total_retries'] += 1
                    retry_count += 1
                    print(f"❌ Timeout error. Retrying from the beginning ({retry_count}): {last_error}")
                    # 🔧 Monitor connection pool status (after exception)
                    await self._monitor_connection_pool_health()
                    
                except Exception as e:
                    error_message = str(e)
                    # Detect PostgreSQL connection errors
                    is_pg_error = "too many clients" in error_message.lower() or \
                                 "connection pool" in error_message.lower() or \
                                 "psycopg" in error_message.lower() or \
                                 "database" in error_message.lower()
                    
                    # Detect OpenAI connection errors or other network errors
                    if "Remote host did not respond correctly after a period of time" in error_message or \
                       "Connection host did not respond" in error_message or \
                       "OpenAI call encountered non-network error" in error_message or \
                       "Network connection" in error_message or \
                       "Connection" in error_message or \
                       "timeout" in error_message.lower() or \
                       "Connection timeout" in error_message or \
                       "Network timeout" in error_message or \
                       "Request timeout" in error_message or \
                       "API call failed" in error_message or \
                       "Connection failed" in error_message or \
                       "ConnectionError" in error_message or \
                       "TimeoutError" in error_message or \
                       "HTTPSConnectionPool" in error_message:
                        last_error = f"Network/connection error: {error_message}"
                        print(f"❌ Network connection error. Retrying from the beginning: {error_message}")
                    elif is_pg_error:
                        last_error = f"Database connection error: {error_message}"
                        print(f"❌ PostgreSQL connection error. Forcing connection pool cleanup: {error_message}")
                    else:
                        last_error = f"Exception: {error_message}"
                        print(f"❌ System exception. Retrying from the beginning: {error_message}")
                    
                    self.concurrent_stats['total_retries'] += 1
                    retry_count += 1
                    
                    # 🔧 Monitor connection pool status (after exception)
                    await self._monitor_connection_pool_health()
                
                # Retry logic in case of an exception - full retry from the beginning.
                if retry_count <= self.concurrent_config.max_retries:
                    print(f"🔄 Starting full retry {retry_count} (restarting from the beginning of the process).")
                    
                    # Important: Reset all state and start from the beginning.
                    # Do not call _adjust_retry_config; keep the original config to ensure a restart.
                    
                    # Use a tiered wait time: 1-10 seconds.
                    delay_index = min(retry_count - 1, len(self.concurrent_config.retry_delays) - 1)
                    retry_delay = self.concurrent_config.retry_delays[delay_index]
                    print(f"⏳ Waiting {retry_delay}s before retrying from the beginning...")
                    await asyncio.sleep(retry_delay)
                    
                    # Continue the loop to restart the entire process from the beginning of the while loop.
                    continue
            
            # All retries failed. Return the best result or an error result.
            
            # If there is a partially successful result, return the last result (which may be a partial success).
            if last_result is not None:
                # Use the last result, but mark it as failed after the retry.
                last_answer = last_result.get('answer', '')
                last_memories = last_result.get('retrieved_memories', [])
                last_errors = last_result.get('errors', [])
                
                # Re-evaluate the last result.
                final_success = not bool(last_errors) and len(last_answer) > 0 and len(last_memories) > 0
                final_status = f"⚠️ Partial success after {retry_count} full retries" if len(last_answer) > 0 else f"❌ Failed after {retry_count} full retries"
                
                print(f"⚠️ Using the last partially successful result (retried {retry_count} times).")
                
                # Use the last partially successful result to build the return result.
                return self._build_test_result_from_last_attempt(
                    test_case, conv_id, question_index, global_question_index,
                    last_result, final_success, final_status, retry_count, last_error
                )
            
            # No successful result was achieved. Returning an error result.
            print(f"❌ Question {global_question_index}: completely failed after {retry_count} full retries.")
            print(f"   Last error: {last_error}")
            
            error_perf_metrics = PerformanceMetrics()
            error_result = {
                "test_info": {
                    "question": test_case['question'],
                    "expected_answer": test_case['expected_answer'],
                    "category": test_case.get('category', 4),
                    "evidence": test_case.get('evidence', []),
                    "source_record": test_case.get('source_record', ''),
                    "speaker_a": test_case.get('speaker_a', ''),
                    "speaker_b": test_case.get('speaker_b', ''),
                    "user_group_ids": test_case.get('user_group_ids', []),
                    "conversation_id": conv_id,
                    "question_index": question_index,
                    "global_question_index": global_question_index
                },
                "execution": {
                    "success": False,
                    "execution_time": 0.0,
                    "confidence": 0.0,
                    "status": f"❌ Completely failed after {retry_count} full retries",
                    "retry_count": retry_count,
                    "final_error": last_error
                },
                "response": {
                    "answer": "",
                    "answer_length": 0
                },
                "formatted_memories": {
                    "count": 0,
                    "content": []
                },
                "memories": {
                    "total_count": 0,
                    "l1_count": 0,
                    "l2_count": 0,
                    "details": []
                },
                "retrieval_info": {
                    "primary_strategy": "unknown",
                    "strategies_used": [],
                    "llm_keywords": [],
                    "query_category": "unknown",
                    "query_complexity": "unknown",
                    "memory_retrieval_details": [],
                    "strategy_performance": {},
                    "retrieval_description": "Test failed; no retrieval information available."
                },
                "performance_metrics": error_perf_metrics.get_metrics_dict(),
                "issues": {
                    "errors": [f"Execution failed: {last_error}"],
                    "warnings": []
                }
            }
            return error_result
    
    def _create_error_result(self, task: Dict[str, Any], error_message: str) -> Dict[str, Any]:
        """Creates an error result object."""
        test_case = task['test_case']
        conv_id = task['conv_id']
        question_index = task['question_index']
        global_question_index = task['global_question_index']
        
        error_perf_metrics = PerformanceMetrics()
        error_result = {
            "test_info": {
                "question": test_case['question'],
                "expected_answer": test_case['expected_answer'],
                "category": test_case.get('category', 4),
                "evidence": test_case.get('evidence', []),
                "source_record": test_case.get('source_record', ''),
                "speaker_a": test_case.get('speaker_a', ''),
                "speaker_b": test_case.get('speaker_b', ''),
                "user_group_ids": test_case.get('user_group_ids', []),
                "conversation_id": conv_id,
                "question_index": question_index,
                "global_question_index": global_question_index
            },
            "execution": {
                "success": False,
                "execution_time": 0.0,
                "confidence": 0.0,
                "status": "❌ Failed",
                "retry_count": 0
            },
            "response": {
                "answer": "",
                "answer_length": 0
            },
            "formatted_memories": {
                "count": 0,
                "content": []
            },
            "memories": {
                "total_count": 0,
                "l1_count": 0,
                "l2_count": 0,
                "details": []
            },
            "retrieval_info": {
                "primary_strategy": "unknown",
                "strategies_used": [],
                "llm_keywords": [],
                "query_category": "unknown",
                "query_complexity": "unknown",
                "memory_retrieval_details": [],
                "strategy_performance": {},
                "retrieval_description": "Task execution failed; no retrieval information available."
            },
            "performance_metrics": error_perf_metrics.get_metrics_dict(),
            "issues": {
                "errors": [error_message],
                "warnings": []
            }
        }
        return error_result
        
    async def test_with_real_data(self, categories=[1, 2, 3, 4], limit=None, selected_conversations=None, debug_timing=False):
        """
        Test memory retrieval workflow with real data (supports grouped testing)
        
        Args:
            categories: Question categories to test, default [1, 2, 3, 4]
            limit: Max questions per group, None means no limit
            selected_conversations: Select specific conversations to test, None means test all
        """
        print("🧪 Testing memory retrieval workflow with real data...")
        
        # Load QA data and group by conversation
        await self.load_qa_data(categories=categories, limit=limit)
        
        # Add user group information to QA data
        await self.enhance_qa_data_with_user_groups()
        
        # Filter conversations to test
        if selected_conversations:
            filtered_groups = {conv_id: questions for conv_id, questions in self.conversation_groups.items() 
                             if conv_id in selected_conversations}
            self.conversation_groups = filtered_groups
        
        # Count test cases
        total_questions = sum(len(questions) for questions in self.conversation_groups.values())
        total_conversations = len(self.conversation_groups)
        
        print(f"\n📋 Test overview:")
        print(f"  Conversations: {total_conversations}")
        print(f"  Total questions: {total_questions}")
        print(f"  Test categories: {categories}")
        print(f"  Quantity limit: {limit if limit else 'Unlimited'}")
        
        # Get retrieval parameters from config file
        retrieval_config = self.retrieval_config_manager.get_config()
        
        # Extract hierarchical retrieval config for display
        hierarchical_config = retrieval_config.get("hierarchical", {})
        layer_limits = hierarchical_config.get("layer_limits", {})
        final_limits = hierarchical_config.get("final_limits", {})
        
        print(f"\n🔧 Retrieval parameter configuration:")
        print(f"  L1: Retrieve top{layer_limits.get('L1', 10)} -> Keep top{final_limits.get('L1', 5)} after reranking")
        print(f"  L2: Retrieve top{layer_limits.get('L2', 3)} -> Keep top{final_limits.get('L2', 1)} after reranking")
        print(f"  Total: Max {final_limits.get('L1', 5) + final_limits.get('L2', 1)} memories (L1:{final_limits.get('L1', 5)} + L2:{final_limits.get('L2', 1)})")
        
        # Rebuild test task structure, support concurrent batch execution
        all_tasks = []
        question_counter = 0
        
        # Collect all test tasks
        for conv_id, questions in self.conversation_groups.items():
            print(f"\n🗣️ Preparing conversation group: {conv_id}")
            print(f"👥 Participants: {questions[0]['speaker_a']} & {questions[0]['speaker_b']}")
            print(f"📊 Question count: {len(questions)}")
            if questions[0]['user_group_ids']:
                print(f"🔒 User group IDs: {', '.join(questions[0]['user_group_ids'])}")
            
            for i, test_case in enumerate(questions, 1):
                question_counter += 1
                task = {
                    'test_case': test_case,
                    'conv_id': conv_id,
                    'question_index': i,
                    'global_question_index': question_counter,
                    'retrieval_config': retrieval_config
                }
                all_tasks.append(task)
        
        print(f"\n🚀 Start concurrent test execution")
        print(f"📊 Concurrency configuration:")
        print(f"  Max concurrent threads: {self.concurrent_config.max_concurrent_requests} (using 20 API keys)")
        print(f"  Inter-batch delay: {self.concurrent_config.batch_delay}s")
        print(f"  Max retries: {self.concurrent_config.max_retries}")
        print(f"  Request timeout: {self.concurrent_config.timeout}s")
        print(f"  Retry wait tiered: {' → '.join([f'{d}s' for d in self.concurrent_config.retry_delays])}")
        print(f"  Technical error detection: Detect 'Sorry, technical error occurred during answer generation' etc and retry")
        print(f"📋 Pending tasks: {len(all_tasks)}")
        print(f"🔑 API key configuration:")
        print(f"  20 API keys in config file auto-rotate")
        print(f"  Each concurrent thread uses different API key independently")
        print(f"  Underlying LLM adapter supports multi-API key load balancing")
        print(f"  Rate limiting: Completely disabled, supports true ultra-high concurrency")
        
        # Execute tasks by batch
        batch_size = self.concurrent_config.max_concurrent_requests
        results = []
        total_batches = (len(all_tasks) + batch_size - 1) // batch_size
        
        # Create overall progress bar
        with tqdm(total=len(all_tasks), desc="🧪 Concurrent test progress", unit="qa", 
                 bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
                 ncols=120, colour='green') as main_pbar:
            
            for batch_idx in range(total_batches):
                start_idx = batch_idx * batch_size
                end_idx = min(start_idx + batch_size, len(all_tasks))
                batch_tasks = all_tasks[start_idx:end_idx]
                
                self.concurrent_stats['total_batches'] += 1
                batch_start_time = time.perf_counter()
                
                print(f"\n{'='*80}")
                print(f"🔥 Execute batch {batch_idx + 1}/{total_batches}")
                print(f"📊 Current batch: {len(batch_tasks)} tasks (tasks {start_idx + 1}-{end_idx})")
                print(f"⏱️ Start time: {datetime.now().strftime('%H:%M:%S')}")
                print(f"{'='*80}")
                
                # Update main progress bar description
                main_pbar.set_description(f"🧪 Batch {batch_idx + 1}/{total_batches}")
                
                try:
                    # Create concurrent tasks
                    concurrent_tasks = []
                    for task in batch_tasks:
                        concurrent_task = self.execute_single_test_case(
                            task['test_case'],
                            task['conv_id'],
                            task['question_index'],
                            task['global_question_index'],
                            task['retrieval_config'],
                            debug_timing
                        )
                        concurrent_tasks.append(concurrent_task)
                    
                    # Execute batch concurrent tasks
                    batch_results = await asyncio.gather(*concurrent_tasks, return_exceptions=True)
                    
                    # Process batch results
                    batch_successes = 0
                    for i, result in enumerate(batch_results):
                        if isinstance(result, Exception):
                            # Handle exception results
                            print(f"⚠️ Task {start_idx + i + 1} execution exception: {result}")
                            # Create error result object
                            task = batch_tasks[i]
                            error_result = self._create_error_result(task, str(result))
                            results.append(error_result)
                        else:
                            # Normal result
                            results.append(result)
                            if result['execution']['success']:
                                batch_successes += 1
                    
                    self.concurrent_stats['successful_batches'] += 1
                    batch_end_time = time.perf_counter()
                    batch_duration = batch_end_time - batch_start_time
                    self.concurrent_stats['avg_batch_time'] = (
                        (self.concurrent_stats['avg_batch_time'] * (batch_idx) + batch_duration) / 
                        (batch_idx + 1)
                    )
                    
                    # Display batch result statistics
                    print(f"\n📊 Batch {batch_idx + 1} completion statistics:")
                    print(f"  Execution time: {batch_duration:.2f}s")
                    print(f"  Successful tasks: {batch_successes}/{len(batch_tasks)}")
                    print(f"  Success rate: {batch_successes/len(batch_tasks)*100:.1f}%")
                    print(f"  Total retries: {self.concurrent_stats['total_retries']}")
                    print(f"  Average batch time: {self.concurrent_stats['avg_batch_time']:.2f}s")
                    
                    # Display partial detailed results (max 3)
                    print(f"\n🔍 Batch result samples (showing first 3):")
                    for i, result in enumerate(batch_results[:3]):
                        if not isinstance(result, Exception):
                            task_num = start_idx + i + 1
                            status = result['execution']['status']
                            question = result['test_info']['question'][:50] + "..." if len(result['test_info']['question']) > 50 else result['test_info']['question']
                            exec_time = result['execution']['execution_time']
                            memories_count = result['memories']['total_count']
                            answer_length = result['response']['answer_length']
                            retry_count = result['execution'].get('retry_count', 0)
                            
                            print(f"  {task_num}. {status}")
                            print(f"     Q: {question}")
                            print(f"     Execution: {exec_time:.3f}s, Memories: {memories_count}, Answer: {answer_length} chars")
                            if retry_count > 0:
                                print(f"     Retries: {retry_count} times")
                    
                    if len(batch_results) > 3:
                        print(f"  ... {len(batch_results) - 3} more results not displayed")
                    
                    # 🔧 Monitor connection pool health after batch completion
                    await self._monitor_connection_pool_health()
                        
                except Exception as e:
                    print(f"❌ Batch {batch_idx + 1} execution failed: {str(e)}")
                    self.concurrent_stats['failed_batches'] += 1
                    
                    # Create error results for failed batch
                    for task in batch_tasks:
                        error_result = self._create_error_result(task, f"Batch execution failed: {str(e)}")
                        results.append(error_result)
                    
                    # 🔧 Monitor connection pool status after batch failure
                    await self._monitor_connection_pool_health()
                
                # Update main progress bar
                main_pbar.update(len(batch_tasks))
                
                # 🔧 Engineering-level fix: force session cleanup between batches
                await self._cleanup_batch_sessions()
                
                # Delay between batches
                if batch_idx < total_batches - 1:  # Not the last batch
                    print(f"⏳ Delay between batches {self.concurrent_config.batch_delay}s...")
                    await asyncio.sleep(self.concurrent_config.batch_delay)
        
        # Display final concurrent statistics
        print(f"\n{'='*80}")
        print(f"🏁 Concurrent execution completion statistics")
        print(f"{'='*80}")
        print(f"📊 Batch statistics:")
        print(f"  Total batches: {self.concurrent_stats['total_batches']}")
        print(f"  Successful batches: {self.concurrent_stats['successful_batches']}")
        print(f"  Failed batches: {self.concurrent_stats['failed_batches']}")
        print(f"  Batch success rate: {(self.concurrent_stats['successful_batches'] / max(self.concurrent_stats['total_batches'], 1)) * 100:.1f}%")
        print(f"  Average batch time: {self.concurrent_stats['avg_batch_time']:.2f}s")
        print(f"  Total retries: {self.concurrent_stats['total_retries']}")
        
        # Calculate concurrent efficiency metrics
        successful_tasks = sum(1 for r in results if r['execution']['success'])
        total_execution_time = sum(r['execution']['execution_time'] for r in results if r['execution']['execution_time'] > 0)
        avg_task_time = total_execution_time / len(results) if len(results) > 0 else 0
        theoretical_sequential_time = avg_task_time * len(all_tasks)
        actual_total_time = self.concurrent_stats['avg_batch_time'] * self.concurrent_stats['total_batches']
        speedup_ratio = theoretical_sequential_time / actual_total_time if actual_total_time > 0 else 0
        
        print(f"📋 Task statistics:")
        print(f"  Total tasks: {len(all_tasks)}")
        print(f"  Successful tasks: {successful_tasks}")
        print(f"  Task success rate: {successful_tasks / len(results) * 100:.1f}%")
        print(f"🚀 Concurrency efficiency analysis:")
        print(f"  Average single task time: {avg_task_time:.2f}s")
        print(f"  Theoretical sequential execution time: {theoretical_sequential_time:.2f}s")
        print(f"  Actual concurrent execution time: {actual_total_time:.2f}s")
        print(f"  Concurrency speedup ratio: {speedup_ratio:.2f}x")
        print(f"  Concurrency efficiency: {(speedup_ratio / self.concurrent_config.max_concurrent_requests * 100):.1f}%")
        print(f"🔑 API key rotation (20 API keys):")
        print(f"  ✓ 20 API keys from config file auto-rotate")
        print(f"  ✓ Each concurrent thread uses different API key independently")
        print(f"  ✓ Underlying LLM adapter auto load-balancing")
        print(f"  ✓ Rate limiting: completely removed, no wait time")
        print(f"  ✓ Support true ultra-high concurrency (20 threads executing simultaneously)")
        print(f"  ✓ No 'rate limit triggered' prompts")
        print(f"  ✓ Guarantee stability in high concurrency scenarios")
        
        return results
    
    async def generate_report(self, results: List[Dict[str, Any]]):
        """Generate test report"""
        print(f"\n{'='*80}")
        print(f"📊 Generating test report")
        print(f"{'='*80}")
        
        # Ensure logs directory exists
        os.makedirs("logs/tests", exist_ok=True)
        
        # Generate report filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"memory_retrieval_test_report_{timestamp}.json"
        filepath = f"logs/tests/{filename}"
        
        # Calculate statistics
        total_tests = len(results)
        successful_tests = sum(1 for r in results if r['execution']['success'])
        failed_tests = total_tests - successful_tests
        
        execution_times = [r['execution']['execution_time'] for r in results if r['execution']['execution_time'] > 0]
        confidences = [r['execution']['confidence'] for r in results if r['execution']['confidence'] > 0]
        
        # Build report content
        conversation_tested = list(set(case.get('test_info', {}).get('conversation_id', '') for case in results))
        
        report = {
            "test_info": {
                "timestamp": datetime.now().isoformat(),
                "total_test_cases": total_tests,
                "total_conversations": len(conversation_tested),
                "conversations_tested": conversation_tested,
                "test_cases": [f"Q{case.get('test_info', {}).get('global_question_index', i+1)}: {case.get('test_info', {}).get('question', '')[:50]}..." for i, case in enumerate(results[:20])],  # Only display first 20
                "user_groups_tested": list(set(case.get('test_info', {}).get('source_record', '') for case in results if case.get('test_info', {}).get('source_record')))
            },
            "statistics": {
                "success_rate": f"{successful_tests/total_tests*100:.1f}%" if total_tests > 0 else "0%",
                "successful_tests": successful_tests,
                "failed_tests": failed_tests,
                "total_tests": total_tests
            },
            "performance": {
                "avg_execution_time": sum(execution_times) / len(execution_times) if execution_times else 0,
                "min_execution_time": min(execution_times) if execution_times else 0,
                "max_execution_time": max(execution_times) if execution_times else 0,
                "avg_confidence": sum(confidences) / len(confidences) if confidences else 0
            },
            "detailed_results": results
        }
        
        # Save report
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2, default=str)
            
            print(f"📄 Detailed test report saved: {filepath}")
            
        except Exception as e:
            print(f"❌ Failed to save report: {e}")
        
        # Print console summary
        self.print_summary(report)
        
        return report
    
    async def generate_evaluation_data(self, results: List[Dict[str, Any]]):
        """Generate data format for evaluation framework"""
        print(f"\n{'='*80}")
        print(f"📊 Generating evaluation data file")
        print(f"{'='*80}")
        
        # Ensure logs directory exists
        os.makedirs("logs/tests", exist_ok=True)
        
        # Generate evaluation data filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"memory_retrieval_eval_data_{timestamp}.json"
        filepath = f"logs/tests/{filename}"
        
        # Build evaluation data format - fully compliant with task_eval framework requirements
        eval_data = {
            "sample_id": "memory_retrieval_multi_conversation_test",
            "qa": []
        }
        
        for i, result in enumerate(results):
            # Get test case information directly from result (new format includes complete information)
            test_info = result.get('test_info', {})
            
            # Get retrieval information
            retrieval_info = result.get('retrieval_info', {})
            
            # Extract answer content
            full_answer = result['response']['answer']  # Full answer
            
            # If single-step COT was used, extract FINAL_ANSWER from cot_full_response as concise answer
            if result.get('use_single_cot', False) and result.get('cot_full_response'):
                # Try to extract <FINAL_ANSWER> part from COT response
                import re
                match = re.search(r'<FINAL_ANSWER>\s*(.*?)\s*</FINAL_ANSWER>', 
                                result.get('cot_full_response', ''), re.DOTALL)
                if match:
                    predicted_answer = match.group(1).strip()  # Concise answer (for F1/RL)
                    predicted_full_context = result.get('cot_full_response', '')  # Full answer (for LLJ)
                else:
                    # If extraction failed, use full answer
                    predicted_answer = full_answer
                    predicted_full_context = full_answer
            else:
                # Non-COT mode, both are the same
                predicted_answer = full_answer
                predicted_full_context = full_answer
            
            qa_item = {
                "question": test_info.get('question', ''),
                "answer": test_info.get('expected_answer', ''),  # Standard answer
                "category": test_info.get('category', 4),  # Get category from original QA data
                "prediction": predicted_answer,  # Concise answer (for F1/RL scoring)
                "predicted_answer": predicted_answer,  # Concise answer (explicit field)
                "predicted_full_context": predicted_full_context,  # Full answer (for LLJ scoring)
                "evidence": test_info.get('evidence', []),  # Get evidence from original QA data
                "test_id": f"Q{test_info.get('global_question_index', i+1)}",
                "execution_time": result['execution']['execution_time'],
                "confidence": result['execution']['confidence'],
                "memories_count": result['memories']['total_count'],
                "formatted_memories_count": result['formatted_memories']['count'],
                # Add user group information
                "source_record": test_info.get('source_record', ''),
                "conversation_id": test_info.get('conversation_id', ''),
                "speaker_a": test_info.get('speaker_a', ''),
                "speaker_b": test_info.get('speaker_b', ''),
                "user_group_ids": test_info.get('user_group_ids', []),
                "question_index": test_info.get('question_index', i+1),
                "global_question_index": test_info.get('global_question_index', i+1),
                # Add retrieval strategy and keyword information
                "retrieval_strategy": retrieval_info.get('primary_strategy', 'unknown'),
                "strategies_used": retrieval_info.get('strategies_used', []),
                "llm_keywords": retrieval_info.get('llm_keywords', []),
                "query_category": retrieval_info.get('query_category', 'unknown'),
                "query_complexity": retrieval_info.get('query_complexity', 'unknown'),
                "strategy_performance": retrieval_info.get('strategy_performance', {}),
                "retrieval_description": retrieval_info.get('retrieval_description', ''),
                "memory_retrieval_details": retrieval_info.get('memory_retrieval_details', []),
                # Multi-stage COT related information (for debugging and analysis)
                "cot_evidence": result.get('cot_evidence', {}),
                "cot_reasoning": result.get('cot_reasoning', {}),
                "cot_full_reasoning": result.get('cot_full_reasoning', ''),
                "cot_stage_times": result.get('cot_stage_times', {}),
                "cot_stage_tokens": result.get('cot_stage_tokens', {}),
                "use_multi_stage_cot": result.get('use_multi_stage_cot', False),
                # Single-step COT related information (for debugging and analysis)
                "use_single_cot": result.get('use_single_cot', False),
                "cot_full_response": result.get('cot_full_response', ''),  # Full COT output (includes reasoning and answer)
                "cot_format_valid": result.get('cot_format_valid', False),  # Is format valid
                "cot_retry_count": result.get('cot_retry_count', 0),  # Retry count
                # Relevance filtering protection mechanism information
                "memory_refined": result.get('memory_refined', False),  # Whether relevance filtering was performed
                "original_memory_count": result.get('original_memory_count', 0),  # Memory count before filtering
                "refined_memory_count": result.get('refined_memory_count', 0),  # Memory count after filtering
                "refinement_retention_rate": result.get('refinement_retention_rate', 0.0),  # Filter retention rate
                "fallback_used": result.get('memory_refiner_metadata', {}).get('fallback_used', False),  # Whether protection mechanism was used
                "fallback_reason": result.get('memory_refiner_metadata', {}).get('fallback_reason', '')  # Protection mechanism reason
            }
            eval_data['qa'].append(qa_item)
        
        # Save evaluation data
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(eval_data, f, ensure_ascii=False, indent=2, default=str)
            
            print(f"📄 Evaluation data saved: {filepath}")
            print(f"📋 Contains {len(eval_data['qa'])} QA pairs")
            
        except Exception as e:
            print(f"❌ Failed to save evaluation data: {e}")
        
        return eval_data, filepath
    
    async def generate_performance_report(self, results: List[Dict[str, Any]]):
        """Generate detailed performance statistics report"""
        print(f"\n{'='*80}")
        print(f"📈 Generating performance statistics report")
        print(f"{'='*80}")
        
        # Ensure logs directory exists
        os.makedirs("logs/tests", exist_ok=True)
        
        # Generate performance report filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Collect all performance data
        performance_data = []
        for i, result in enumerate(results):
            metrics = result.get('performance_metrics', {})
            test_info = result.get('test_info', {})
            retrieval_info = result.get('retrieval_info', {})
            
            perf_row = {
                'test_id': f"Q{test_info.get('global_question_index', i+1)}",
                'conversation_id': test_info.get('conversation_id', ''),
                'question': test_info.get('question', '')[:50] + '...' if len(test_info.get('question', '')) > 50 else test_info.get('question', ''),
                'success': result.get('execution', {}).get('success', False),
                'total_execution_time': metrics.get('total_execution_time', 0.0),
                'retrieval_time': metrics.get('retrieval_time', 0.0),
                'llm_total_time': metrics.get('llm_total_time', 0.0),
                'llm_first_response_delay': metrics.get('llm_first_response_delay', 0.0),
                'llm_generation_time': metrics.get('llm_generation_time', 0.0),
                'input_tokens': metrics.get('input_tokens', 0),
                'output_tokens': metrics.get('output_tokens', 0),
                'total_tokens': metrics.get('total_tokens', 0),
                'retrieved_memories_count': metrics.get('retrieved_memories_count', 0),
                'l1_memories_count': metrics.get('l1_memories_count', 0),
                'l2_memories_count': metrics.get('l2_memories_count', 0),
                'answer_length': metrics.get('answer_length', 0),
                'confidence_score': metrics.get('confidence_score', 0.0),
                'speaker_a': test_info.get('speaker_a', ''),
                'speaker_b': test_info.get('speaker_b', ''),
                'user_group_ids': ','.join(test_info.get('user_group_ids', [])),
                # Add retrieval strategy and keyword information
                'primary_strategy': retrieval_info.get('primary_strategy', 'unknown'),
                'strategies_used': ','.join(retrieval_info.get('strategies_used', [])),
                'llm_keywords': ','.join(retrieval_info.get('llm_keywords', [])),
                'query_category': retrieval_info.get('query_category', 'unknown'),
                'query_complexity': retrieval_info.get('query_complexity', 'unknown'),
                'retrieval_description': retrieval_info.get('retrieval_description', '')[:100] + '...' if len(retrieval_info.get('retrieval_description', '')) > 100 else retrieval_info.get('retrieval_description', '')
            }
            performance_data.append(perf_row)
        
        # Create DataFrame
        try:
            df = pd.DataFrame(performance_data)
            
            # Save detailed performance data to CSV
            csv_filename = f"performance_metrics_detailed_{timestamp}.csv"
            csv_filepath = f"logs/tests/{csv_filename}"
            df.to_csv(csv_filepath, index=False, encoding='utf-8')
            print(f"📄 Detailed performance data CSV saved: {csv_filepath}")
            
            # Save detailed performance data to Excel (if available)
            try:
                excel_filename = f"performance_metrics_detailed_{timestamp}.xlsx"
                excel_filepath = f"logs/tests/{excel_filename}"
                with pd.ExcelWriter(excel_filepath, engine='openpyxl') as writer:
                    df.to_excel(writer, sheet_name='Detailed Data', index=False)
                    
                    # Create statistics summary table
                    summary_data = self._generate_performance_summary(df)
                    summary_df = pd.DataFrame(summary_data)
                    summary_df.to_excel(writer, sheet_name='Statistics Summary', index=False)
                    
                    # Group statistics by conversation
                    conv_stats = self._generate_conversation_performance_stats(df)
                    conv_df = pd.DataFrame(conv_stats)
                    conv_df.to_excel(writer, sheet_name='Conversation Group Stats', index=False)
                    
                print(f"📄 Detailed performance data Excel saved: {excel_filepath}")
            except ImportError:
                print(f"⚠️ Unable to generate Excel file (missing openpyxl), only CSV file generated")
                
        except Exception as e:
            print(f"❌ Failed to generate performance report: {e}")
            return None, None
        
        # Generate performance statistics JSON
        performance_stats = self._calculate_performance_statistics(performance_data)
        json_filename = f"performance_statistics_{timestamp}.json"
        json_filepath = f"logs/tests/{json_filename}"
        
        try:
            with open(json_filepath, 'w', encoding='utf-8') as f:
                json.dump(performance_stats, f, ensure_ascii=False, indent=2, default=str)
            print(f"📄 Performance statistics JSON saved: {json_filepath}")
        except Exception as e:
            print(f"❌ Failed to save performance statistics JSON: {e}")
        
        # Print console performance summary
        self._print_performance_summary(performance_stats)
        
        return csv_filepath, json_filepath
    
    def _generate_performance_summary(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Generate performance statistics summary"""
        summary = []
        
        # Time metrics statistics
        time_metrics = ['total_execution_time', 'retrieval_time', 'llm_total_time', 
                       'llm_first_response_delay', 'llm_generation_time']
        
        for metric in time_metrics:
            if metric in df.columns and df[metric].sum() > 0:
                summary.append({
                    'metric_name': metric,
                    'mean_seconds': df[metric].mean(),
                    'median_seconds': df[metric].median(),
                    'min_seconds': df[metric].min(),
                    'max_seconds': df[metric].max(),
                    'std_seconds': df[metric].std(),
                    'p95_seconds': df[metric].quantile(0.95)
                })
        
        # Token metrics statistics
        token_metrics = ['input_tokens', 'output_tokens', 'total_tokens']
        for metric in token_metrics:
            if metric in df.columns and df[metric].sum() > 0:
                summary.append({
                    'metric_name': metric,
                    'mean': df[metric].mean(),
                    'median': df[metric].median(),
                    'min': df[metric].min(),
                    'max': df[metric].max(),
                    'total': df[metric].sum(),
                    'std': df[metric].std()
                })
        
        return summary
    
    def _generate_conversation_performance_stats(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Generate performance statistics grouped by conversation"""
        conv_stats = []
        
        if 'conversation_id' in df.columns:
            for conv_id in df['conversation_id'].unique():
                conv_df = df[df['conversation_id'] == conv_id]
                
                conv_stats.append({
                    'conversation_id': conv_id,
                    'participants': f"{conv_df.iloc[0]['speaker_a']} & {conv_df.iloc[0]['speaker_b']}" if len(conv_df) > 0 else '',
                    'question_count': len(conv_df),
                    'successful_count': conv_df['success'].sum(),
                    'success_rate_percent': (conv_df['success'].sum() / len(conv_df) * 100) if len(conv_df) > 0 else 0,
                    'avg_execution_time_seconds': conv_df['total_execution_time'].mean(),
                    'avg_retrieval_time_seconds': conv_df['retrieval_time'].mean(),
                    'avg_llm_time_seconds': conv_df['llm_total_time'].mean(),
                    'avg_token_count': conv_df['total_tokens'].mean(),
                    'avg_memory_count': conv_df['retrieved_memories_count'].mean(),
                    'avg_confidence': conv_df['confidence_score'].mean()
                })
        
        return conv_stats
    
    def _calculate_performance_statistics(self, performance_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate detailed performance statistics"""
        if not performance_data:
            return {}
        
        # Basic statistics
        total_tests = len(performance_data)
        successful_tests = sum(1 for p in performance_data if p['success'])
        
        # Time statistics
        execution_times = [p['total_execution_time'] for p in performance_data if p['total_execution_time'] > 0]
        retrieval_times = [p['retrieval_time'] for p in performance_data if p['retrieval_time'] > 0]
        llm_times = [p['llm_total_time'] for p in performance_data if p['llm_total_time'] > 0]
        
        # Token statistics
        total_input_tokens = sum(p['input_tokens'] for p in performance_data)
        total_output_tokens = sum(p['output_tokens'] for p in performance_data)
        total_tokens = sum(p['total_tokens'] for p in performance_data)
        
        # Memory statistics
        total_memories = sum(p['retrieved_memories_count'] for p in performance_data)
        avg_memories = total_memories / total_tests if total_tests > 0 else 0
        
        # Retrieval strategy statistics
        strategy_counts = {}
        category_counts = {}
        complexity_counts = {}
        keywords_stats = []
        
        for p in performance_data:
            # Strategy statistics
            strategy = p.get('primary_strategy', 'unknown')
            strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1
            
            # Query category statistics
            category = p.get('query_category', 'unknown')
            category_counts[category] = category_counts.get(category, 0) + 1
            
            # Query complexity statistics
            complexity = p.get('query_complexity', 'unknown')
            complexity_counts[complexity] = complexity_counts.get(complexity, 0) + 1
            
            # Keyword statistics
            keywords = p.get('llm_keywords', '')
            if keywords and keywords != '':
                keyword_list = keywords.split(',')
                keywords_stats.extend([kw.strip() for kw in keyword_list if kw.strip()])
        
        # Count most frequent keywords
        from collections import Counter
        keyword_counter = Counter(keywords_stats)
        top_keywords = keyword_counter.most_common(10)
        
        return {
            "basic_stats": {
                "total_tests": total_tests,
                "successful_tests": successful_tests,
                "success_rate": successful_tests / total_tests if total_tests > 0 else 0,
                "failure_rate": (total_tests - successful_tests) / total_tests if total_tests > 0 else 0
            },
            "time_performance": {
                "execution_time": {
                    "avg": sum(execution_times) / len(execution_times) if execution_times else 0,
                    "min": min(execution_times) if execution_times else 0,
                    "max": max(execution_times) if execution_times else 0,
                    "median": sorted(execution_times)[len(execution_times)//2] if execution_times else 0
                },
                "retrieval_time": {
                    "avg": sum(retrieval_times) / len(retrieval_times) if retrieval_times else 0,
                    "min": min(retrieval_times) if retrieval_times else 0,
                    "max": max(retrieval_times) if retrieval_times else 0
                },
                "llm_time": {
                    "avg": sum(llm_times) / len(llm_times) if llm_times else 0,
                    "min": min(llm_times) if llm_times else 0,
                    "max": max(llm_times) if llm_times else 0
                }
            },
            "token_usage": {
                "total_input_tokens": total_input_tokens,
                "total_output_tokens": total_output_tokens,
                "total_tokens": total_tokens,
                "avg_input_tokens": total_input_tokens / total_tests if total_tests > 0 else 0,
                "avg_output_tokens": total_output_tokens / total_tests if total_tests > 0 else 0,
                "avg_total_tokens": total_tokens / total_tests if total_tests > 0 else 0
            },
            "memory_stats": {
                "total_memories_retrieved": total_memories,
                "avg_memories_per_question": avg_memories,
                "memory_efficiency": total_memories / total_tests if total_tests > 0 else 0
            },
            "retrieval_strategy_analysis": {
                "strategy_distribution": strategy_counts,
                "query_category_distribution": category_counts,
                "query_complexity_distribution": complexity_counts,
                "top_keywords": top_keywords,
                "total_unique_keywords": len(keyword_counter),
                "avg_keywords_per_query": len(keywords_stats) / total_tests if total_tests > 0 else 0
            }
        }
    
    def _print_performance_summary(self, performance_stats: Dict[str, Any]):
        """Print performance statistics summary"""
        print(f"\n📊 Performance Statistics Summary:")
        
        basic = performance_stats.get('basic_stats', {})
        print(f"  Basic Statistics:")
        print(f"    Total tests: {basic.get('total_tests', 0)}")
        print(f"    Successful tests: {basic.get('successful_tests', 0)}")
        print(f"    Success rate: {basic.get('success_rate', 0)*100:.1f}%")
        
        time_perf = performance_stats.get('time_performance', {})
        if time_perf:
            print(f"\n  Time Performance:")
            exec_time = time_perf.get('execution_time', {})
            if exec_time.get('avg', 0) > 0:
                print(f"    Average execution time: {exec_time.get('avg', 0):.3f}s")
                print(f"    Fastest execution time: {exec_time.get('min', 0):.3f}s")
                print(f"    Slowest execution time: {exec_time.get('max', 0):.3f}s")
            
            retr_time = time_perf.get('retrieval_time', {})
            if retr_time.get('avg', 0) > 0:
                print(f"    Average retrieval time: {retr_time.get('avg', 0):.3f}s")
            
            llm_time = time_perf.get('llm_time', {})
            if llm_time.get('avg', 0) > 0:
                print(f"    Average LLM time: {llm_time.get('avg', 0):.3f}s")
        
        token_usage = performance_stats.get('token_usage', {})
        if token_usage.get('total_tokens', 0) > 0:
            print(f"\n  Token Usage Statistics:")
            print(f"    Total input tokens: {token_usage.get('total_input_tokens', 0):,}")
            print(f"    Total output tokens: {token_usage.get('total_output_tokens', 0):,}")
            print(f"    Total tokens: {token_usage.get('total_tokens', 0):,}")
            print(f"    Average tokens per question: {token_usage.get('avg_total_tokens', 0):.1f}")
        
        memory_stats = performance_stats.get('memory_stats', {})
        if memory_stats.get('total_memories_retrieved', 0) > 0:
            print(f"\n  Memory Retrieval Statistics:")
            print(f"    Total memories retrieved: {memory_stats.get('total_memories_retrieved', 0)}")
            print(f"    Average memories per question: {memory_stats.get('avg_memories_per_question', 0):.1f}")
        
        # Retrieval strategy analysis summary
        strategy_analysis = performance_stats.get('retrieval_strategy_analysis', {})
        if strategy_analysis:
            print(f"\n  Retrieval Strategy Analysis:")
            
            # Strategy distribution
            strategy_dist = strategy_analysis.get('strategy_distribution', {})
            if strategy_dist:
                print(f"    Primary retrieval strategies:")
                for strategy, count in strategy_dist.items():
                    percentage = (count / performance_stats.get('basic_stats', {}).get('total_tests', 1)) * 100
                    print(f"      {strategy}: {count} times ({percentage:.1f}%)")
            
            # Query category distribution
            category_dist = strategy_analysis.get('query_category_distribution', {})
            if category_dist:
                print(f"    Query category distribution:")
                for category, count in category_dist.items():
                    percentage = (count / performance_stats.get('basic_stats', {}).get('total_tests', 1)) * 100
                    print(f"      {category}: {count} times ({percentage:.1f}%)")
            
            # Keyword statistics
            top_keywords = strategy_analysis.get('top_keywords', [])
            if top_keywords:
                print(f"    Top keywords (top 5):")
                for keyword, count in top_keywords[:5]:
                    print(f"      '{keyword}': {count} times")
                
            total_keywords = strategy_analysis.get('total_unique_keywords', 0)
            avg_keywords = strategy_analysis.get('avg_keywords_per_query', 0)
            if total_keywords > 0:
                print(f"    Total unique keywords: {total_keywords}")
                print(f"    Average keywords per question: {avg_keywords:.1f}")
    
    def print_evaluation_summary(self, eval_data: Dict[str, Any]):
        """Print evaluation data summary"""
        print(f"\n📊 Evaluation Data Summary:")
        print(f"  Sample ID: {eval_data['sample_id']}")
        print(f"  Number of QA pairs: {len(eval_data['qa'])}")
        
        # Collect statistics for each category
        categories = {}
        conversations = {}
        answer_lengths = []
        confidence_scores = []
        memory_counts = []
        
        for qa in eval_data['qa']:
            # Category statistics
            cat = qa['category']
            categories[cat] = categories.get(cat, 0) + 1
            
            # Conversation statistics
            conv = qa.get('source_record', 'unknown')
            conversations[conv] = conversations.get(conv, 0) + 1
            
            # Answer length statistics
            if qa['prediction']:
                answer_lengths.append(len(qa['prediction']))
            
            # Confidence score statistics
            confidence_scores.append(qa['confidence'])
            
            # Memory count statistics
            memory_counts.append(qa['memories_count'])
        
        print(f"\n📈 Data Statistics:")
        print(f"  Question category distribution: {categories}")
        print(f"  Conversation distribution: {conversations}")
        
        # Display category meanings
        category_meanings = {
            1: "Entity Recognition",
            2: "Time Recognition", 
            3: "Reasoning and Judgment",
            4: "Open Domain QA",
            5: "Adversarial QA"
        }
        print(f"  Category meanings:")
        for cat, meaning in category_meanings.items():
            if cat in categories:
                print(f"    Category {cat} ({meaning}): {categories[cat]} items")
        
        # Retrieval strategy statistics
        retrieval_strategies = {}
        query_categories = {}
        keyword_stats = []
        
        for qa in eval_data['qa']:
            # Retrieval strategy statistics
            strategy = qa.get('retrieval_strategy', 'unknown')
            retrieval_strategies[strategy] = retrieval_strategies.get(strategy, 0) + 1
            
            # Query category statistics
            query_cat = qa.get('query_category', 'unknown')
            query_categories[query_cat] = query_categories.get(query_cat, 0) + 1
            
            # Keyword collection
            keywords = qa.get('llm_keywords', [])
            if isinstance(keywords, list):
                keyword_stats.extend(keywords)
            elif isinstance(keywords, str) and keywords:
                # If string, split and process
                keyword_stats.extend([k.strip() for k in keywords.split(',') if k.strip()])
        
        if retrieval_strategies:
            print(f"\n  Retrieval strategy distribution:")
            for strategy, count in retrieval_strategies.items():
                percentage = (count / len(eval_data['qa'])) * 100
                print(f"    {strategy}: {count} items ({percentage:.1f}%)")
        
        if query_categories and any(cat != 'unknown' for cat in query_categories.keys()):
            print(f"  Query category distribution:")
            for query_cat, count in query_categories.items():
                if query_cat != 'unknown':
                    percentage = (count / len(eval_data['qa'])) * 100
                    print(f"    {query_cat}: {count} items ({percentage:.1f}%)")
        
        if keyword_stats:
            from collections import Counter
            keyword_counter = Counter(keyword_stats)
            top_keywords = keyword_counter.most_common(5)
            print(f"  Top keywords (top 5):")
            for keyword, count in top_keywords:
                print(f"    '{keyword}': {count} times")
            print(f"  Total unique keywords: {len(keyword_counter)}")
        
        if answer_lengths:
            print(f"  Answer length statistics:")
            print(f"    Average length: {sum(answer_lengths)/len(answer_lengths):.1f}")
            print(f"    Shortest length: {min(answer_lengths)}")
            print(f"    Longest length: {max(answer_lengths)}")
        
        if confidence_scores:
            print(f"  Confidence score statistics:")
            print(f"    Average confidence: {sum(confidence_scores)/len(confidence_scores):.3f}")
            print(f"    Highest confidence: {max(confidence_scores):.3f}")
            print(f"    Lowest confidence: {min(confidence_scores):.3f}")
        
        if memory_counts:
            print(f"  Memory retrieval statistics:")
            print(f"    Average memory count: {sum(memory_counts)/len(memory_counts):.1f}")
            print(f"    Maximum memory count: {max(memory_counts)}")
            print(f"    Minimum memory count: {min(memory_counts)}")
        
        print(f"\n💡 Evaluation notes:")
        print(f"  - Question category distribution: contains multiple types, suitable for comprehensive evaluation")
        print(f"  - Categories 1-3: suitable for F1, BERT Score and Rouge-L evaluation")
        print(f"  - Category 4: open domain QA, suitable for all metrics evaluation")
        print(f"  - Category 5: adversarial QA, requires special handling")
        print(f"  - Recommend using F1 Score as the main evaluation metric")
    
    def print_summary(self, report: Dict[str, Any]):
        """Print test summary"""
        print(f"\n📋 Test Summary:")
        print(f"  Total test cases: {report['statistics']['total_tests']}")
        print(f"  Successful cases: {report['statistics']['successful_tests']}")
        print(f"  Failed cases: {report['statistics']['failed_tests']}")
        print(f"  Success rate: {report['statistics']['success_rate']}")
        
        if report['performance']['avg_execution_time'] > 0:
            print(f"\n📈 Performance Statistics:")
            print(f"  Average execution time: {report['performance']['avg_execution_time']:.3f}s")
            print(f"  Fastest execution time: {report['performance']['min_execution_time']:.3f}s")
            print(f"  Slowest execution time: {report['performance']['max_execution_time']:.3f}s")
            
        if report['performance']['avg_confidence'] > 0:
            print(f"  Average confidence: {report['performance']['avg_confidence']:.3f}")
        
        # Detailed results
        print(f"\n📝 Detailed Results:")
        for i, result in enumerate(report['detailed_results'], 1):
            status_icon = "✅" if result['execution']['success'] else "❌"
            question = result['test_info']['question']
            expected = result['test_info']['expected_answer']
            
            print(f"  {i}. {status_icon} Q{i}")
            print(f"     Question: {question}")
            print(f"     Expected: {expected}")
            print(f"     Status: {result['execution']['status']}")
            print(f"     Execution time: {result['execution']['execution_time']:.3f}s")
            print(f"     Confidence: {result['execution']['confidence']:.3f}")
            print(f"     Memory count: {result['memories']['total_count']}")
            print(f"     Answer length: {result['response']['answer_length']}")
            
            if result['issues']['errors']:
                print(f"     Errors: {result['issues']['errors']}")
            if result['issues']['warnings']:
                print(f"     Warnings: {result['issues']['warnings']}")
            print()


# Global variables for graceful shutdown
shutdown_event = None
tester_instance = None

async def main():
    """Main test function - using async context manager and graceful shutdown"""
    global tester_instance, shutdown_event
    
    # Create shutdown event
    shutdown_event = asyncio.Event()
    
    # 🔧 Fix: use default signal handling directly, let KeyboardInterrupt be raised naturally
    # Don't customize signal handler, let asyncio.run() handle KeyboardInterrupt correctly
    # signal.signal(signal.SIGINT, signal.SIG_DFL) is already the default behavior
    
    print("="*80)
    print("🚀 TiMem Memory Retrieval Workflow - Multi-conversation User Isolation Test")
    print("Using all conversations from locomo10_qa_001-004.json, test user group isolation functionality")
    print("📊 Support grouping tests by conversation, category filtering and quantity limits")
    print("🔒 Ensure only retrieving memories within specified user groups, protecting user privacy")
    print("="*80)
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # Configure test parameters - optimize connection pool usage
        TEST_CATEGORIES = [1,2,3,4]  # Test categories
        TEST_LIMIT = None # Maximum questions per group, reduced to 2 to quickly verify connection pool fix
        #SELECTED_CONVERSATIONS = ["conv-26"]  # Only test specified conversation, reduce connection pool pressure
        SELECTED_CONVERSATIONS = None  # Select specific conversation, set to None to test all conversations
        DEBUG_TIMING = False  # Enable timing breakdown debugging
        ENABLE_SMART_RETRY = True  # Enable smart retry mechanism 
        
        print(f"🔧 Test Configuration:")
        print(f"  Test categories: {TEST_CATEGORIES}")
        print(f"  Per-group limit: {TEST_LIMIT if TEST_LIMIT else 'Unlimited'}")
        print(f"  Selected conversations: {SELECTED_CONVERSATIONS if SELECTED_CONVERSATIONS else 'All conversations'}")
        print(f"  Concurrency mode: Enabled (20 threads batch execution, using 20 API keys)")
        print(f"  API keys: 20 keys auto-rotate load balancing")
        print(f"  Retry mechanism: Enhanced smart retry (max 10 times, tiered wait 1s→10s)")
        print(f"  Retry triggers: errors/technical issue answers/short answers/insufficient memories/low confidence/unclear sources")
        print(f"  Technical issue handling: Specially detect 'Sorry, a technical issue occurred during answer generation' errors")
        print(f"  Intent understanding failure handling: Full retry strategy")
        print(f"    - Keep user group filtering: Always enabled")
        print(f"    - Keep retrieval strategy: Unchanged")
        print(f"    - Keep retrieval parameters: Unchanged")
        print(f"    - Re-pass question and character ID, continue execution")
        
        # Create concurrent config - use 20 concurrent threads and 20 API keys from config file
        concurrent_config = ConcurrentConfig(
            max_concurrent_requests=20,  # Set 20 concurrent threads
            batch_delay=0.5,             # 0.5 second delay between batches
            max_retries=10,              # Maximum 10 retries
            retry_delays=[1.0, 2.0, 3.0, 4.0, 5.0],  # Tiered retry intervals: 1-5 seconds
            timeout=120.0                # Single request timeout 120 seconds
        )
        
        # Display concurrent config information
        print(f"✅ High Concurrency Configuration:")
        print(f"  Concurrent threads: 20 (using 20 API keys from config file)")
        print(f"  Batch delay: 0.5 seconds")
        print(f"  Maximum retries: 10 times")
        print(f"  Retry interval: 1s→5s (tiered wait)")
        print(f"  API key rotation: Auto load-balancing at underlying layer")
        print(f"  Rate limiting: Completely removed, supports true ultra-high concurrency")
        
        # Use async context manager
        async with MemoryRetrievalTester(concurrent_config=concurrent_config) as tester:
            
            tester_instance = tester  # Save global reference
            
            # Run tests
            results = await tester.test_with_real_data(
                categories=TEST_CATEGORIES,
                limit=TEST_LIMIT,
                selected_conversations=SELECTED_CONVERSATIONS,
                debug_timing=DEBUG_TIMING
            )
            
            if results:
                # Generate report
                report = await tester.generate_report(results)
                
                # Generate evaluation data
                eval_data, eval_filepath = await tester.generate_evaluation_data(results)
                
                # Generate performance statistics report
                perf_csv_path, perf_json_path = await tester.generate_performance_report(results)
                
                # Print evaluation data summary
                tester.print_evaluation_summary(eval_data)

                success_count = sum(1 for r in results if r['execution']['success'])
                total_conversations = len(set(r.get('test_info', {}).get('conversation_id', '') for r in results))
                
                print(f"\n🎉 Test Completed!")
                print(f"📊 Test Statistics:")
                print(f"  Number of conversation groups: {total_conversations}")
                print(f"  Total questions: {len(results)}")
                print(f"  Successful questions: {success_count}")
                print(f"  Success rate: {success_count/len(results)*100:.1f}%")
                print(f"📄 Evaluation data saved to: {eval_filepath}")
                
                if perf_csv_path and perf_json_path:
                    print(f"📈 Performance statistics report saved:")
                    print(f"  Detailed data CSV: {perf_csv_path}")
                    print(f"  Statistics summary JSON: {perf_json_path}")
                    # Excel file path displayed in performance report method, not repeated here
                
                print(f"\n💡 Evaluation Data Usage Instructions:")
                print(f"  1. Evaluation data format adapted for task_eval framework")
                print(f"  2. Support multi-conversation group testing with complete user group isolation information")
                print(f"  3. Each question contains conversation group information and user group IDs")
                print(f"  4. Available evaluation metrics:")
                print(f"     ✅ F1 Score - based on stemming matching")
                print(f"     ✅ BERT Score - based on semantic similarity")
                print(f"     ✅ Rouge-L Score - based on text overlap")
                print(f"     ✅ Exact Match - suitable for factual questions")
                print(f"     ✅ Recall - suitable for questions with evidence field")
                
                print(f"\n📈 Performance Analysis Report Instructions:")
                print(f"  1. CSV file contains detailed performance data for each test case")
                print(f"  2. JSON file contains aggregated performance statistics and analysis")
                print(f"  3. Excel file (if available) contains detailed analysis with multiple worksheets")
                print(f"  4. Performance metrics include:")
                print(f"     📊 Execution time breakdown (retrieval time + LLM time)")
                print(f"     📊 Token usage statistics (input/output tokens)")
                print(f"     📊 Memory retrieval statistics (L1/L2 level memory count)")
                print(f"     📊 Retrieval strategy analysis (strategy distribution, keyword statistics)")
                print(f"     📊 Query category and complexity analysis")
                print(f"     📊 Performance comparison by conversation group")
                print(f"     📊 Success rate and confidence analysis")
                print(f"\n  5. Recommended evaluation command:")
                print(f"     python -m task_eval.evaluate_qa \\")
                print(f"       --data-file {eval_filepath} \\")
                print(f"       --out-file {eval_filepath.replace('.json', '_scores.json')} \\")
                print(f"       --model timem-memory-retrieval")
                print(f"\n  6. Or use TiMem-specific evaluation script:")
                print(f"     python -m task_eval.timem_qa_evaluation \\")
                print(f"       --data-file {eval_filepath} \\")
                print(f"       --out-file {eval_filepath.replace('.json', '_timem_scores.json')} \\")
                print(f"       --verbose")
                print(f"\n🔒 User Group Isolation Verification:")
                print(f"  - Each question contains complete user group context information")
                print(f"  - Retrieval workflow configured with user group filtering to ensure only retrieving memories within specified user groups")
                print(f"  - Test results include user group isolation execution status")
                print(f"  - Support analyzing test results by conversation group")
            else:
                print("\n❌ Test Failed")
        
        # Program completed normally
        
        print("👋 Program exited normally")
            
    except KeyboardInterrupt:
        print("\n⚠️ Program interrupted by user (Ctrl+C), exiting immediately...")
        # Return directly, don't attempt cleanup (cleanup already done in __aexit__)
        return
    except Exception as e:
        print(f"\n❌ Error occurred during testing: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup already done in __aexit__, do minimal processing here
        pass


if __name__ == "__main__":
    import warnings
    import logging
    
    # Suppress aiohttp and asyncio cleanup warnings
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    warnings.filterwarnings("ignore", message=".*SSL.*")
    warnings.filterwarnings("ignore", message=".*unclosed.*")
    warnings.filterwarnings("ignore", message=".*Unclosed client session.*")
    warnings.filterwarnings("ignore", message=".*Unclosed connector.*")
    warnings.filterwarnings("ignore", message=".*Fatal error on SSL transport.*")
    
    # Lower asyncio log level to avoid showing normal connection cleanup errors
    asyncio_logger = logging.getLogger('asyncio')
    asyncio_logger.setLevel(logging.CRITICAL)
    
    # Lower aiohttp log level
    aiohttp_logger = logging.getLogger('aiohttp')
    aiohttp_logger.setLevel(logging.CRITICAL)
    
    exit_code = 0
    
    try:
        # 🔧 Fix: use asyncio.run(), which automatically manages event loop and resource cleanup
        # Exception handling already done inside main() function, just need to catch outermost exceptions here
        asyncio.run(main())
        print("🔚 Program exit completed")
    except KeyboardInterrupt:
        print("\n⚠️ Program interrupted externally")
        exit_code = 130  # Standard exit code for SIGINT
    except Exception as e:
        print(f"\n❌ Program exited abnormally: {e}")
        import traceback
        traceback.print_exc()
        exit_code = 1
    
    # 🔧 Normal exit, no need for forced sys.exit()
    # asyncio.run() automatically cleans up event loop, program should exit normally
    if exit_code != 0:
        import sys
        sys.exit(exit_code)
