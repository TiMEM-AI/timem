#!/usr/bin/env python3
"""
LongMemEval-S Memory Retrieval and Answer Generation Script

Based on TiMem memory retrieval workflow, perform QA generation on longmemeval_s dataset
- Load question data from questions_by_user/ (contains 28 abstract questions)
- Test all 500 users by default
- Use global expert for retrieval (longmemeval_s feature)
- Generate answers and save in evaluation format
- Support high concurrency batch processing (default 50 concurrent)

Usage:
1. Basic run (load all users):
   python experiments/datasets/longmemeval_s/02_memory_retrieval.py
   
2. Limit number of users (traditional mode):
   python experiments/datasets/longmemeval_s/02_memory_retrieval.py --num-users 10
   
3. Select N users from each of 6 question types (type selection mode):
   python experiments/datasets/longmemeval_s/02_memory_retrieval.py --use-type-selection --users-per-type 10
   
4. Limit number of questions per user:
   python experiments/datasets/longmemeval_s/02_memory_retrieval.py --questions-per-user 5

5. Specify output file:
   python experiments/datasets/longmemeval_s/02_memory_retrieval.py --output logs/longmemeval_s_answers.json

6. Customize concurrency parameters:
   python experiments/datasets/longmemeval_s/02_memory_retrieval.py --concurrent 40 --max-retries 5 --timeout 180


Parameter description:
  --users-per-type N        Number of users selected per question type (only in use-type-selection mode, default None=no limit)
  --questions-per-user N    Number of questions processed per user (default None=all)
  --use-type-selection      Use type selection strategy (select N users from each of 6 types)
  --no-type-selection       Use traditional mode to load first N users (default enabled)
  --num-users N             Number of users to load in traditional mode (default None=all 500 users)
  --output PATH             Output file path (default auto-generate timestamp filename)
  --concurrent N            Number of concurrent requests (default 50)
  --batch-delay N           Delay between batches in seconds (default 0.5)
  --max-retries N           Maximum number of retries (default 3)
  --timeout N               Single request timeout in seconds (default 120)
"""

import os
import sys
import json
import asyncio
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from tqdm import tqdm
import time

# Add project root directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
# File is in experiments/datasets/longmemeval_s/ directory, need to go up 3 levels to project root
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
sys.path.insert(0, project_root)

from timem.workflows.memory_retrieval import run_memory_retrieval
from timem.workflows.naive_rag_workflow import run_naive_rag
from timem.utils.retrieval_config_manager import get_retrieval_config_manager
from timem.utils.dataset_guard import DatasetGuard, require_dataset, print_current_dataset

# Import statistics collector
from timem.utils.stats_collector import ComprehensiveStatsCollector
from experiments.utils.stats_helper import StatsTestHelper


class ConcurrentConfig:
    """Concurrent configuration class"""
    
    def __init__(self, max_concurrent_requests: int = 10, batch_delay: float = 0.5, 
                 max_retries: int = 3, retry_delays: List[float] = None, timeout: float = 120.0):
        self.max_concurrent_requests = max_concurrent_requests
        self.batch_delay = batch_delay
        self.max_retries = max_retries
        self.retry_delays = retry_delays or [1.0, 2.0, 3.0]  # Tiered wait times: 1s, 2s, 3s
        self.timeout = timeout


def select_users_by_question_type(questions_dir: Path, users_per_type: int = 4, 
                                  exclude_users: set = None) -> tuple[list, dict]:
    """
    Select first N users from each of 6 question types (consistent with test_longmemeval_s_sim.py)
    
    Question types:
    1. single-session-user
    2. single-session-assistant
    3. single-session-preference
    4. multi-session
    5. knowledge-update
    6. temporal-reasoning
    
    Args:
        questions_dir: Path to questions directory
        users_per_type: Number of users to select per question type, default 4
        exclude_users: Set of user IDs to exclude (original_dataset_id)
    
    Returns:
        selected_user_ids: List of selected user IDs (with user_ prefix)
        users_by_type: Dictionary of users grouped by question type
    """
    if not questions_dir.exists():
        print(f"❌ questions_by_user directory does not exist: {questions_dir}")
        return [], {}
    
    if exclude_users is None:
        exclude_users = set()
    
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
    excluded_count = 0  # Count of excluded users
    
    # Get all question files and sort (ensure consistent order)
    question_files = sorted(questions_dir.glob("user_*_questions.json"))
    
    for qtype in question_types:
        for question_file in question_files:
            # Extract user_id from filename: user_001be529_questions.json -> user_001be529
            file_stem = question_file.stem  # user_001be529_questions
            if file_stem.endswith("_questions"):
                user_id = file_stem[:-10]  # Remove "_questions", keep "user_001be529"
            else:
                continue
            
            # Extract original_dataset_id (remove user_ prefix) and check if in exclusion list
            original_id = user_id.replace("user_", "")
            if original_id in exclude_users:
                excluded_count += 1
                continue  # Skip users in exclusion list
            
            try:
                with open(question_file, 'r', encoding='utf-8') as f:
                    questions_data = json.load(f)
                    
                    # questions_data is an array, iterate directly
                    if not isinstance(questions_data, list):
                        continue
                    
                    # Check if user has this type of question
                    has_this_type = any(
                        q.get("question_type") == qtype 
                        for q in questions_data
                    )
                    
                    if has_this_type and user_id not in users_by_type[qtype]:
                        users_by_type[qtype].append(user_id)
                        
                        # Stop searching this type after reaching desired count (if users_per_type is not None)
                        if users_per_type is not None and len(users_by_type[qtype]) >= users_per_type:
                            break
                            
            except Exception as e:
                print(f"Failed to read question file {question_file}: {e}")
                continue
        
        # Add to total list
        if users_per_type is None:
            selected_user_ids.extend(users_by_type[qtype])  # All users
        else:
            selected_user_ids.extend(users_by_type[qtype][:users_per_type])  # Limited count
    
    # Deduplicate (a user may have multiple types of questions)
    selected_user_ids = list(dict.fromkeys(selected_user_ids))
    
    print(f"\n{'='*80}")
    if users_per_type is None:
        print(f"🎯 User selection strategy: Load all users from 6 question types")
    else:
        print(f"🎯 User selection strategy: Select {users_per_type} users from each of 6 types")
    print(f"{'='*80}")
    for qtype, uids in users_by_type.items():
        if users_per_type is None:
            selected_uids = uids  # All users
        else:
            selected_uids = uids[:users_per_type]  # Limited count
        print(f"  {qtype}: {len(selected_uids)} users")
        if selected_uids and len(selected_uids) <= 10:
            # Only show detailed IDs when <=10 users
            display_ids = [uid.replace('user_', '') for uid in selected_uids]
            print(f"    ({', '.join(display_ids)})")
        elif selected_uids:
            # Show only first 5 when more than 10 users
            display_ids = [uid.replace('user_', '') for uid in selected_uids[:5]]
            print(f"    ({', '.join(display_ids)}... total {len(selected_uids)})")
    print(f"\n  Total selected: {len(selected_user_ids)} users (after deduplication)")
    print(f"{'='*80}\n")
    
    return selected_user_ids, users_by_type


class LongMemEvalSQuestionLoader:
    """LongMemEval-S Question Loader"""
    
    def __init__(self, data_dir: str = "data/longmemeval_s_split"):
        self.data_dir = Path(data_dir)
        self.questions_dir = self.data_dir / "questions_by_user"
        self.sessions_dir = self.data_dir / "sessions_by_user"
    
    def load_users_questions(
        self, 
        num_users: int = None,
        users_per_type: int = 4,
        questions_per_user: int = None,
        use_type_selection: bool = True,
        exclude_users: bool = False
    ) -> Dict[str, Dict]:
        """
        Load user question data
        
        Args:
            num_users: Number of users to load (traditional mode, used when use_type_selection=False)
            users_per_type: Number of users to select per question type (used when use_type_selection=True)
            questions_per_user: Limit number of questions per user (None=all questions)
            use_type_selection: Whether to use type selection strategy (True=select N from each of 6 types)
            exclude_users: (unused; kept for backward compatibility)
        
        Returns:
            {user_id: {
                "user_id": str,
                "question_type": str,
                "questions": [...]
            }}
        """
        print(f"\n{'='*80}")
        print(f"📂 Loading LongMemEval-S question data")
        print(f"{'='*80}")
        print(f"Data directory: {self.questions_dir}")
        
        if not self.questions_dir.exists():
            raise FileNotFoundError(f"Question directory does not exist: {self.questions_dir}")
        
        # Reproducibility: do not special-case any subset of users
        exclude_users = set()
        
        # Select users
        if use_type_selection:
            # Use type selection strategy: select N users from each of 6 types
            selected_user_ids, users_by_type = select_users_by_question_type(
                self.questions_dir, 
                users_per_type=users_per_type,
                exclude_users=exclude_users
            )
        else:
            # Traditional mode: load first N users (include _abs abstract users)
            question_files = sorted(self.questions_dir.glob("user_*_questions.json"))
            # No longer filter _abs files since abstract questions also need testing
            
            # Apply exclusion logic
            filtered_files = []
            excluded_count = 0
            for f in question_files:
                user_id = f.stem.replace('_questions', '')
                original_id = user_id.replace('user_', '')
                if original_id not in exclude_users:
                    filtered_files.append(f)
                else:
                    excluded_count += 1
            
            # If num_users is None, load all users
            if num_users is None:
                question_files = filtered_files
                print(f"Found {len(filtered_files)} user question files")
                print(f"Loading all {len(filtered_files)} users\n")
            else:
                question_files = filtered_files[:num_users]
                if exclude_users:
                    print(f"Found {len(filtered_files)} user question files")
                else:
                    print(f"Found {len(filtered_files)} user question files")
                print(f"Loading first {len(question_files)} users\n")
            
            selected_user_ids = [f.stem.replace('_questions', '') for f in question_files]
            users_by_type = {}
        
        # Load question data for selected users
        users_data = {}
        
        for user_id in selected_user_ids:
            question_file = self.questions_dir / f"{user_id}_questions.json"
            
            if not question_file.exists():
                print(f"⚠️ Question file does not exist: {question_file.name}")
                continue
            
            try:
                with open(question_file, 'r', encoding='utf-8') as f:
                    questions = json.load(f)
                
                # Question file is an array
                if not isinstance(questions, list):
                    print(f"⚠️ Skip invalid file (not an array): {question_file.name}")
                    continue
                
                if not questions:
                    print(f"⚠️ Skip empty file: {question_file.name}")
                    continue
                
                # Limit question count (if specified)
                if questions_per_user is not None and questions_per_user > 0:
                    original_count = len(questions)
                    questions = questions[:questions_per_user]
                    print(f"  📊 {user_id}: Limited questions {original_count} → {len(questions)}")
                
                # Get question_type from first question
                question_type = questions[0].get("question_type", "unknown") if questions else "unknown"
                
                users_data[user_id] = {
                    "user_id": user_id,
                    "question_type": question_type,
                    "questions": questions,
                    "file_path": str(question_file)
                }
                
                print(f"✅ {user_id}: {question_type} type, {len(questions)} questions")
                
            except Exception as e:
                print(f"❌ Failed to load {question_file.name}: {e}")
                import traceback
                traceback.print_exc()
        
        print(f"\n{'='*80}")
        print(f"📊 Loading complete")
        print(f"{'='*80}")
        print(f"Successfully loaded users: {len(users_data)}")
        total_questions = sum(len(data["questions"]) for data in users_data.values())
        print(f"Total questions: {total_questions}")
        if questions_per_user:
            print(f"Questions per user limit: {questions_per_user}")
        print(f"{'='*80}\n")
        
        return users_data


class LongMemEvalSRetrievalGenerator:
    """LongMemEval-S Retrieval Generator"""
    
    def __init__(self, global_expert_id: str, concurrent_config: ConcurrentConfig = None, 
                 stats_helper: Optional[StatsTestHelper] = None, prompt_file: str = None,
                 config_path: str = None):
        """
        Initialize generator
        
        Args:
            global_expert_id: Global expert ID
            concurrent_config: Concurrent configuration
            stats_helper: Statistics collector
            prompt_file: Prompt file path
            config_path: Configuration file path (for ablation experiments)
        """
        self.global_expert_id = global_expert_id
        self.concurrent_config = concurrent_config or ConcurrentConfig()
        self.semaphore = asyncio.Semaphore(self.concurrent_config.max_concurrent_requests)
        self.stats_helper = stats_helper  # Statistics collector
        self.prompt_file = prompt_file  # Prompt file path
        self.config_path = config_path  # Save config path, create context during execution
        
        # Concurrent statistics
        self.concurrent_stats = {
            'total_batches': 0,
            'successful_batches': 0,
            'failed_batches': 0,
            'total_retries': 0,
            'avg_batch_time': 0.0
        }
        
        # Retrieval performance statistics
        self.retrieval_stats = {
            'total_retrievals': 0,
            'successful_retrievals': 0,
            'failed_retrievals': 0,
            'total_retrieval_time': 0.0,
            'retrieval_times': [],
            'memories_retrieved': [],
            'avg_memories_per_retrieval': 0.0
        }
        
        print(f"\n{'='*80}")
        print(f"🔧 Retrieval Generator Initialization")
        print(f"{'='*80}")
        print(f"Global Expert ID: {global_expert_id}")
        print(f"Concurrent Requests: {self.concurrent_config.max_concurrent_requests}")
        print(f"Statistics Collection: {'Enabled' if stats_helper else 'Disabled'}")
    
    async def get_user_db_id(self, user_id: str) -> Optional[str]:
        """Get user's DB ID from database
        
        Args:
            user_id: user_id extracted from filename, e.g., "user_0a995998"
        
        Returns:
            User's database ID, e.g., "f8a787e3-1d2b-41cf-87f2-c6e0a86eb61a"
        
        Query logic:
            Filename: user_0a995998_questions.json
            user_id: user_0a995998
            Database username: longmemeval_user_0a995998_51709_02729f6a
            Match pattern: username LIKE 'longmemeval_user_0a995998%'
        """
        try:
            from storage.postgres_store import get_postgres_store
            from sqlalchemy import text
            
            postgres_store = await get_postgres_store()
            
            async with postgres_store.get_session() as session:
                # Build query pattern: longmemeval_user_0a995998_%
                # username format: longmemeval_user_0a995998_51709_02729f6a
                # Match via username LIKE pattern, not using metadata
                query = text("""
                    SELECT id, username FROM users 
                    WHERE username LIKE :pattern 
                    LIMIT 1
                """)
                
                # Build match pattern: longmemeval_<user_id>_%
                pattern = f"longmemeval_{user_id}_%"
                
                result = await session.execute(query, {"pattern": pattern})
                row = result.fetchone()
                
                if row:
                    db_id = row[0]
                    username = row[1]
                    print(f"  ✅ Found user {user_id}")
                    print(f"     Database username: {username}")
                    print(f"     Database ID: {db_id}")
                    return db_id
                
                # If not found, try looser matching (user_id anywhere)
                print(f"  ⚠️ Exact match not found, trying loose match...")
                pattern = f"%{user_id}%"
                
                result = await session.execute(query, {"pattern": pattern})
                row = result.fetchone()
                
                if row:
                    db_id = row[0]
                    username = row[1]
                    print(f"  ✅ Found user {user_id} via loose match")
                    print(f"     Database username: {username}")
                    print(f"     Database ID: {db_id}")
                    return db_id
                
                print(f"  ❌ No DB record found for user {user_id}")
                print(f"     Query pattern: longmemeval_{user_id}_%")
                print(f"     Please confirm test_longmemeval_s_sim.py has been run to generate memories")
                return None
                    
        except Exception as e:
            print(f"❌ Failed to get user DB ID {user_id}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def generate_answer_for_question(
        self, 
        question_data: Dict[str, Any],
        user_db_id: str,
        user_id: str,
        question_idx: int,
        global_question_index: int = None
    ) -> Dict[str, Any]:
        """Generate answer for a single question (with retry mechanism)"""
        async with self.semaphore:
            retry_count = 0
            last_error = None
            
            while retry_count <= self.concurrent_config.max_retries:
                try:
                    question = question_data.get("question", "")
                    question_date = question_data.get("question_date", "")  # Extract question date
                    question_type = question_data.get("question_type", "unknown")  # Extract question type
                    
                    if not question:
                        print(f"⚠️ Question {question_idx} is empty")
                        return {
                            "success": False,
                            "user_id": user_id,
                            "question_idx": question_idx,
                            "question": "",
                            "question_date": question_date,
                            "question_type": question_type,  # Save question type
                            "answer": question_data.get("answer", ""),
                            "prediction": "",
                            "error": "Question text is empty",
                            "retry_count": retry_count
                        }
                    
                    # Build retrieval request
                    retrieval_request = {
                        "question": question,
                        "context": {
                            "question_date": question_date  # Pass question date
                        },
                        "retrieval_config": {},  # Config passed via config_path, no need to include in request
                        # longmemeval_s uses user group isolation
                        "user_group_ids": [user_db_id, self.global_expert_id],
                        "user_group_filter": {
                            "enabled": True,
                            "user_ids": [user_db_id, self.global_expert_id],
                            "speaker_a_id": user_db_id,
                            "speaker_b_id": self.global_expert_id
                        }
                    }
                    
                    # Execute retrieval (with timeout control)
                    # Note: LLM call statistics automatically collected via FilePromptCollector
                    retrieval_start = time.perf_counter()
                    
                    # Check if using Naive RAG workflow
                    if self.config_path:
                        # Ablation mode: read from config file
                        import yaml
                        with open(self.config_path, 'r', encoding='utf-8') as f:
                            config = yaml.safe_load(f)
                        retrieval_section = config.get('retrieval', {})
                        use_naive_rag = retrieval_section.get('use_naive_rag', False)
                    else:
                        # Normal mode: don't use Naive RAG
                        use_naive_rag = False
                        retrieval_section = {}
                    
                    if use_naive_rag:
                        # Use Naive RAG workflow
                        naive_rag_layers = retrieval_section.get('naive_rag_layers', ['L1', 'L2', 'L3', 'L4', 'L5'])
                        naive_rag_top_k = retrieval_section.get('naive_rag_top_k', 20)
                        result = await asyncio.wait_for(
                            run_naive_rag(
                                retrieval_request, 
                                debug_mode=False, 
                                enabled_layers=naive_rag_layers,
                                top_k=naive_rag_top_k
                            ),
                            timeout=self.concurrent_config.timeout
                        )
                    else:
                        # Use standard retrieval workflow
                        result = await asyncio.wait_for(
                            run_memory_retrieval(
                                retrieval_request, 
                                debug_mode=False,
                                config_path=self.config_path  # Pass config path (for ablation experiments)
                            ),
                            timeout=self.concurrent_config.timeout
                        )
                    
                    retrieval_end = time.perf_counter()
                    retrieval_time = retrieval_end - retrieval_start
                    
                    # Check if result is None
                    if result is None:
                        last_error = "run_memory_retrieval returned None"
                        print(f"❌ Question {question_idx} retrieval returned None (retry {retry_count + 1})")
                        raise Exception(last_error)
                    
                    # Extract answer
                    answer = result.get("answer", "")
                    confidence = result.get("confidence", 0.0)
                    memories = result.get("retrieved_memories", [])
                    
                    # Record retrieval performance statistics
                    self.retrieval_stats['total_retrievals'] += 1
                    self.retrieval_stats['successful_retrievals'] += 1
                    self.retrieval_stats['total_retrieval_time'] += retrieval_time
                    self.retrieval_stats['retrieval_times'].append(retrieval_time)
                    self.retrieval_stats['memories_retrieved'].append(len(memories))
                    
                    # Extract detailed memory information (for diagnostics)
                    memory_details = []
                    for memory in memories:
                        memory_details.append({
                            "memory_id": memory.get("id", ""),
                            "level": memory.get("level", ""),
                            "title": memory.get("title", ""),
                            "content": memory.get("content", ""),
                            "timestamp": memory.get("timestamp", ""),
                            "session_id": memory.get("session_id", ""),
                            "fused_score": memory.get("fused_score", 0.0),
                            "retrieval_source": memory.get("retrieval_source", "unknown")
                        })
                    
                    # Extract memory refining information (if available)
                    memory_refiner_info = {
                        "enabled": result.get("memory_refined", False),
                        "original_count": result.get("original_memory_count", len(memories)),
                        "refined_count": result.get("refined_memory_count", len(memories)),
                        "retention_rate": result.get("refinement_retention_rate", 1.0),
                        "refiner_metadata": result.get("memory_refiner_metadata", {})
                    }
                    
                    # Build return result
                    return {
                        "success": True,
                        "user_id": user_id,
                        "question_idx": question_idx,
                        "question": question,
                        "question_date": question_date,  # Question date
                        "question_type": question_type,  # Question type (for evaluation template selection)
                        "answer": question_data.get("answer", ""),  # Standard answer
                        "prediction": answer,  # Generated answer
                        "confidence": confidence,
                        "memories_count": len(memories),
                        "retrieval_metadata": result.get("retrieval_metadata", {}),
                        # New: detailed memory information
                        "memory_details": memory_details,
                        "memory_refiner_info": memory_refiner_info,
                        "formatted_memories": result.get("formatted_context_memories", []),
                        "retry_count": retry_count
                    }
                    
                except asyncio.TimeoutError as e:
                    last_error = f"Timeout after {self.concurrent_config.timeout}s"
                    self.concurrent_stats['total_retries'] += 1
                    retry_count += 1
                    print(f"❌ Question {question_idx} timeout, retry {retry_count}: {last_error}")
                    
                except Exception as e:
                    last_error = str(e)
                    self.concurrent_stats['total_retries'] += 1
                    retry_count += 1
                    print(f"❌ Question {question_idx} generation failed (retry {retry_count}): {e}")
                
                # Retry logic
                if retry_count <= self.concurrent_config.max_retries:
                    delay_index = min(retry_count - 1, len(self.concurrent_config.retry_delays) - 1)
                    retry_delay = self.concurrent_config.retry_delays[delay_index]
                    print(f"⏳ Waiting {retry_delay}s before retry...")
                    await asyncio.sleep(retry_delay)
                    continue
            
            # All retries failed
            print(f"❌ Question {question_idx} still failed after {retry_count} retries")
            
            # Record failure statistics
            self.retrieval_stats['total_retrievals'] += 1
            self.retrieval_stats['failed_retrievals'] += 1
            
            return {
                "success": False,
                "user_id": user_id,
                "question_idx": question_idx,
                "question": question_data.get("question", ""),
                "question_date": question_data.get("question_date", ""),
                "question_type": question_data.get("question_type", "unknown"),  # Save question type
                "answer": question_data.get("answer", ""),
                "prediction": "",
                "error": f"Failed after {retry_count} retries: {last_error}",
                "retry_count": retry_count
            }
    
    async def generate_answers_for_user(
        self, 
        user_id: str, 
        user_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Generate answers for all questions of a single user"""
        print(f"\n{'─'*80}")
        print(f"👤 Processing user: {user_id}")
        print(f"Question type: {user_data['question_type']}")
        print(f"Number of questions: {len(user_data['questions'])}")
        print(f"{'─'*80}")
        
        # Get user DB ID
        user_db_id = await self.get_user_db_id(user_id)
        if not user_db_id:
            print(f"⚠️ Skip user {user_id} (no DB record found)")
            return []
        
        print(f"User DB ID: {user_db_id}")
        
        # Process all questions concurrently
        tasks = []
        for idx, question_data in enumerate(user_data["questions"], 1):
            task = self.generate_answer_for_question(
                question_data, user_db_id, user_id, idx
            )
            tasks.append(task)
        
        # Execute concurrent tasks
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        valid_results = []
        success_count = 0
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"❌ Question {i+1} exception: {result}")
                # Extract type from original question data
                question_type = user_data["questions"][i].get("question_type", "unknown") if i < len(user_data["questions"]) else "unknown"
                valid_results.append({
                    "success": False,
                    "user_id": user_id,
                    "question_idx": i+1,
                    "question_type": question_type,  # Save question type
                    "error": str(result)
                })
            else:
                valid_results.append(result)
                if result.get("success"):
                    success_count += 1
        
        print(f"\n✅ User {user_id} completed: {success_count}/{len(valid_results)} successful")
        
        return valid_results
    
    async def generate_answers_for_all_users(
        self, 
        users_data: Dict[str, Dict]
    ) -> Dict[str, Any]:
        """Generate answers for all users (batch concurrent processing)"""
        # Engineering-level config management: config loaded via config_path on each call, no need to reload
        if self.config_path:
            print(f"✅ Ablation experiment mode: config path = {self.config_path}")
        else:
            print(f"✅ Normal mode: using default config")
        
        # Check if using Naive RAG
        if self.config_path:
            import yaml
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            retrieval_section = config.get('retrieval', {})
            use_naive_rag = retrieval_section.get('use_naive_rag', False)
            naive_rag_layers = retrieval_section.get('naive_rag_layers', ['L1', 'L2', 'L3', 'L4', 'L5'])
            
            if use_naive_rag:
                print(f"🔧 Using Naive RAG workflow")
                print(f"   - Enabled layers: {naive_rag_layers}")
                print(f"   - Top-K: {retrieval_section.get('naive_rag_top_k', 20)}")
            else:
                print(f"🔧 Using standard retrieval workflow")
                forced_strategy = retrieval_section.get('forced_strategy')
                if forced_strategy:
                    print(f"   - Forced strategy: {forced_strategy}")
                else:
                    print(f"   - Intelligent routing: Enabled")
        else:
            print(f"🔧 Using standard retrieval workflow (default intelligent routing)")
        print()
        print(f"\n{'='*80}")
        print(f"🚀 Starting batch concurrent answer generation")
        print(f"{'='*80}")
        print(f"Number of users: {len(users_data)}")
        print(f"Concurrent config: {self.concurrent_config.max_concurrent_requests} concurrent requests")
        print(f"Batch delay: {self.concurrent_config.batch_delay}s")
        print(f"Maximum retries: {self.concurrent_config.max_retries}")
        print(f"Request timeout: {self.concurrent_config.timeout}s")
        
        # 1. Pre-fetch all user DB IDs
        user_db_id_map = {}
        print(f"\n📋 Pre-fetching user DB IDs...")
        for user_id in users_data.keys():
            user_db_id = await self.get_user_db_id(user_id)
            if user_db_id:
                user_db_id_map[user_id] = user_db_id
                print(f"  ✅ {user_id}: {user_db_id[:8]}...")
            else:
                print(f"  ❌ {user_id}: Not found")
        
        # 2. Build all tasks
        all_tasks = []
        global_question_index = 0
        
        print(f"\n📋 Building task list...")
        for user_id, user_data in users_data.items():
            user_db_id = user_db_id_map.get(user_id)
            if not user_db_id:
                print(f"⚠️ Skip user {user_id} (no DB record found)")
                continue
            
            print(f"  👤 {user_id}: {len(user_data['questions'])} questions")
            
            for idx, question_data in enumerate(user_data["questions"], 1):
                global_question_index += 1
                task = {
                    'question_data': question_data,
                    'user_db_id': user_db_id,
                    'user_id': user_id,
                    'question_idx': idx,
                    'global_question_index': global_question_index
                }
                all_tasks.append(task)
        
        print(f"\n📊 Task statistics:")
        print(f"  Pending tasks: {len(all_tasks)}")
        print(f"  Valid users: {len(user_db_id_map)}")
        
        # 3. Batch concurrent execution
        total_start_time = time.perf_counter()
        batch_size = self.concurrent_config.max_concurrent_requests
        all_results = []
        total_batches = (len(all_tasks) + batch_size - 1) // batch_size
        
        # Create overall progress bar
        with tqdm(total=len(all_tasks), desc="🧪 Concurrent generation progress", unit="qa", 
                 bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
                 ncols=120, colour='green') as main_pbar:
            
            for batch_idx in range(total_batches):
                start_idx = batch_idx * batch_size
                end_idx = min(start_idx + batch_size, len(all_tasks))
                batch_tasks = all_tasks[start_idx:end_idx]
                
                self.concurrent_stats['total_batches'] += 1
                batch_start_time = time.perf_counter()
                
                print(f"\n{'='*80}")
                print(f"🔥 Executing batch {batch_idx + 1}/{total_batches}")
                print(f"📊 Current batch: {len(batch_tasks)} tasks (tasks {start_idx + 1}-{end_idx})")
                print(f"⏱️ Start time: {datetime.now().strftime('%H:%M:%S')}")
                print(f"{'='*80}")
                
                # Update main progress bar description
                main_pbar.set_description(f"🧪 Batch {batch_idx + 1}/{total_batches}")
                
                try:
                    # Create concurrent tasks
                    concurrent_tasks = []
                    for task in batch_tasks:
                        concurrent_task = self.generate_answer_for_question(
                            task['question_data'],
                            task['user_db_id'],
                            task['user_id'],
                            task['question_idx'],
                            task['global_question_index']
                        )
                        concurrent_tasks.append(concurrent_task)
                    
                    # Execute batch concurrent tasks
                    batch_results = await asyncio.gather(*concurrent_tasks, return_exceptions=True)
                    
                    # Process batch results
                    batch_successes = 0
                    for i, result in enumerate(batch_results):
                        if isinstance(result, Exception):
                            # Handle exception result
                            print(f"⚠️ Task {start_idx + i + 1} execution exception: {result}")
                            task = batch_tasks[i]
                            error_result = {
                                "success": False,
                                "user_id": task['user_id'],
                                "question_idx": task['question_idx'],
                                "question": task['question_data'].get("question", ""),
                                "question_date": task['question_data'].get("question_date", ""),
                                "question_type": task['question_data'].get("question_type", "unknown"),  # Save question type
                                "answer": task['question_data'].get("answer", ""),
                                "prediction": "",
                                "error": str(result),
                                "retry_count": 0
                            }
                            all_results.append(error_result)
                        else:
                            # Normal result
                            all_results.append(result)
                            if result.get('success'):
                                batch_successes += 1
                    
                    self.concurrent_stats['successful_batches'] += 1
                    batch_end_time = time.perf_counter()
                    batch_duration = batch_end_time - batch_start_time
                    self.concurrent_stats['avg_batch_time'] = (
                        (self.concurrent_stats['avg_batch_time'] * batch_idx + batch_duration) / 
                        (batch_idx + 1)
                    )
                    
                    # Display batch result statistics
                    print(f"\n📊 Batch {batch_idx + 1} completion statistics:")
                    print(f"  Execution time: {batch_duration:.2f}s")
                    print(f"  Successful tasks: {batch_successes}/{len(batch_tasks)}")
                    print(f"  Success rate: {batch_successes/len(batch_tasks)*100:.1f}%")
                    print(f"  Total retries: {self.concurrent_stats['total_retries']}")
                    print(f"  Average batch time: {self.concurrent_stats['avg_batch_time']:.2f}s")
                    
                except Exception as e:
                    print(f"❌ Batch {batch_idx + 1} execution failed: {str(e)}")
                    self.concurrent_stats['failed_batches'] += 1
                    
                    # Create error results for failed batch
                    for task in batch_tasks:
                        error_result = {
                            "success": False,
                            "user_id": task['user_id'],
                            "question_idx": task['question_idx'],
                            "question": task['question_data'].get("question", ""),
                            "question_date": task['question_data'].get("question_date", ""),
                            "question_type": task['question_data'].get("question_type", "unknown"),  # Save question type
                            "answer": task['question_data'].get("answer", ""),
                            "prediction": "",
                            "error": f"Batch execution failed: {str(e)}",
                            "retry_count": 0
                        }
                        all_results.append(error_result)
                
                # Update main progress bar
                main_pbar.update(len(batch_tasks))
                
                # Delay between batches
                if batch_idx < total_batches - 1:
                    print(f"⏳ Batch delay {self.concurrent_config.batch_delay}s...")
                    await asyncio.sleep(self.concurrent_config.batch_delay)
        
        total_end_time = time.perf_counter()
        total_time = total_end_time - total_start_time
        
        # Aggregate results
        success_count = sum(1 for r in all_results if r.get("success"))
        
        print(f"\n{'='*80}")
        print(f"✅ Answer generation completed")
        print(f"{'='*80}")
        print(f"📊 Batch statistics:")
        print(f"  Total batches: {self.concurrent_stats['total_batches']}")
        print(f"  Successful batches: {self.concurrent_stats['successful_batches']}")
        print(f"  Failed batches: {self.concurrent_stats['failed_batches']}")
        print(f"  Average batch time: {self.concurrent_stats['avg_batch_time']:.2f}s")
        print(f"  Total retries: {self.concurrent_stats['total_retries']}")
        
        print(f"\n📋 Task statistics:")
        print(f"  Total questions: {len(all_results)}")
        print(f"  Successful: {success_count}")
        print(f"  Failed: {len(all_results) - success_count}")
        print(f"  Success rate: {success_count/len(all_results)*100:.1f}%")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Average per question: {total_time/len(all_results):.2f}s")
        
        # Concurrent efficiency analysis
        theoretical_sequential_time = total_time
        speedup_ratio = theoretical_sequential_time / total_time if total_time > 0 else 1
        print(f"\n🚀 Concurrent efficiency analysis:")
        print(f"  Concurrent speedup ratio: {speedup_ratio:.2f}x")
        print(f"  Concurrent efficiency: {(speedup_ratio / self.concurrent_config.max_concurrent_requests * 100):.1f}%")
        
        # Calculate retrieval performance statistics
        if self.retrieval_stats['retrieval_times']:
            import statistics
            self.retrieval_stats['avg_memories_per_retrieval'] = (
                statistics.mean(self.retrieval_stats['memories_retrieved']) 
                if self.retrieval_stats['memories_retrieved'] else 0
            )
            retrieval_times = self.retrieval_stats['retrieval_times']
            self.retrieval_stats['avg_retrieval_time'] = statistics.mean(retrieval_times)
            self.retrieval_stats['median_retrieval_time'] = statistics.median(retrieval_times)
            self.retrieval_stats['p95_retrieval_time'] = statistics.quantiles(retrieval_times, n=20)[18] if len(retrieval_times) >= 20 else max(retrieval_times)
            self.retrieval_stats['min_retrieval_time'] = min(retrieval_times)
            self.retrieval_stats['max_retrieval_time'] = max(retrieval_times)
        
        # Print retrieval performance statistics
        print(f"\n📊 Retrieval performance statistics:")
        print(f"  Total retrievals: {self.retrieval_stats['total_retrievals']}")
        print(f"  Successful retrievals: {self.retrieval_stats['successful_retrievals']}")
        print(f"  Failed retrievals: {self.retrieval_stats['failed_retrievals']}")
        print(f"  Success rate: {self.retrieval_stats['successful_retrievals']/self.retrieval_stats['total_retrievals']*100:.1f}%")
        if self.retrieval_stats.get('avg_retrieval_time'):
            print(f"  Average retrieval time: {self.retrieval_stats['avg_retrieval_time']:.2f}s")
            print(f"  Median retrieval time: {self.retrieval_stats['median_retrieval_time']:.2f}s")
            print(f"  P95 retrieval time: {self.retrieval_stats['p95_retrieval_time']:.2f}s")
            print(f"  Fastest retrieval: {self.retrieval_stats['min_retrieval_time']:.2f}s")
            print(f"  Slowest retrieval: {self.retrieval_stats['max_retrieval_time']:.2f}s")
            print(f"  Average memories per retrieval: {self.retrieval_stats['avg_memories_per_retrieval']:.1f}")
        
        # Clean up large lists in retrieval statistics (avoid large JSON)
        retrieval_stats_summary = {k: v for k, v in self.retrieval_stats.items() 
                                   if k not in ['retrieval_times', 'memories_retrieved']}
        
        # Build output data
        output_data = {
            "metadata": {
                "dataset": "longmemeval_s",
                "timestamp": datetime.now().isoformat(),
                "total_users": len(users_data),
                "total_questions": len(all_results),
                "success_count": success_count,
                "success_rate": success_count/len(all_results) if all_results else 0,
                "total_time_seconds": total_time,
                "global_expert_id": self.global_expert_id,
                "prompt_file": self.prompt_file,  # Prompt file path
                "concurrent_config": {
                    "max_concurrent_requests": self.concurrent_config.max_concurrent_requests,
                    "batch_delay": self.concurrent_config.batch_delay,
                    "max_retries": self.concurrent_config.max_retries,
                    "timeout": self.concurrent_config.timeout
                },
                "concurrent_stats": self.concurrent_stats,
                "retrieval_stats": retrieval_stats_summary  # Retrieval statistics
            },
            "qa_results": all_results
        }
        
        return output_data


async def main():
    """Main function"""
    # Parse arguments
    parser = argparse.ArgumentParser(description="LongMemEval-S Answer Generation Script")
    
    # User selection strategy parameters
    parser.add_argument("--users-per-type", type=int, default=None,
                       help="Number of users selected per question type (default None=no limit, load all complete users)")
    parser.add_argument("--questions-per-user", type=int, default=None,
                       help="Number of questions processed per user (default None=all)")
    parser.add_argument("--use-type-selection", dest="use_type_selection", 
                       action="store_true", default=False,
                       help="Use type selection strategy (select N users from each of 6 types)")
    parser.add_argument("--no-type-selection", dest="use_type_selection", 
                       action="store_false",
                       help="Use traditional mode to load the first N users (default enabled)")
    parser.add_argument("--num-users", type=int, default=None,
                       help="Number of users loaded in traditional mode (default None=all 500 users)")
    
    # Output parameters
    parser.add_argument("--output", type=str, 
                       default=None,
                       help="Output file path (default auto-generate)")
    
    # Ablation experiment parameters
    parser.add_argument('--config', type=str, default=None, 
                       help='Ablation experiment config file path (complete isolation mode)')
    
    # Limit parameters (unified with locomo interface)
    parser.add_argument('--limit', type=int, default=0, 
                       help='Limit total number of questions (0=all, >0=limit, unified with locomo interface)')
    
    # Concurrent parameters
    parser.add_argument("--concurrent", type=int, default=50,
                       help="Number of concurrent requests (default 50)")
    parser.add_argument("--batch-delay", type=float, default=0.5,
                       help="Delay between batches in seconds (default 0.5)")
    parser.add_argument("--max-retries", type=int, default=3,
                       help="Maximum number of retries (default 3)")
    parser.add_argument("--timeout", type=float, default=120.0,
                       help="Single request timeout in seconds (default 120)")
    args = parser.parse_args()
    
    print("="*80)
    print("🚀 LongMemEval-S Answer Generation Script")
    print("="*80)
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Set dataset to longmemeval_s (data isolation + port isolation)
    os.environ['TIMEM_DATASET_PROFILE'] = 'longmemeval_s'
    print(f"✅ Dataset set to: longmemeval_s")
    
    # Check dataset configuration
    print_current_dataset()
    
    # Initialize statistics collector
    stats_collector = ComprehensiveStatsCollector()
    stats_helper = StatsTestHelper(stats_collector)
    stats_collector.start_collection()
    print(f"✅ Statistics collector started")
    
    # Enable file prompt collection (for accurate token calculation)
    from llm.file_prompt_collector import get_file_prompt_collector, enable_file_prompt_collection
    timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    prompt_file = f"logs/longmemeval_s/prompts_{timestamp_str}.jsonl"
    os.makedirs("logs/longmemeval_s", exist_ok=True)
    enable_file_prompt_collection(prompt_file)
    file_prompt_collector = get_file_prompt_collector(prompt_file)
    print(f"✅ File prompt collector started (tiktoken available: {file_prompt_collector._tiktoken_available})")
    print(f"📁 Prompts will be saved to: {prompt_file}\n")
    
    try:
        # 1. Load question data
        loader = LongMemEvalSQuestionLoader()
        
        print(f"\n{'='*80}")
        print(f"🎯 Loading configuration")
        print(f"{'='*80}")
        if args.use_type_selection:
            print(f"Mode: Type selection strategy (select users from 6 types)")
            if args.users_per_type:
                print(f"  Users per type: {args.users_per_type}")
                print(f"  Total users (estimated): ~{args.users_per_type * 6} (6 types)")
            else:
                print(f"  Users per type: All (no limit)")
                print(f"  Total users (estimated): ~500 users")
        else:
            print(f"Mode: Traditional mode (load users sequentially)")
            if args.num_users:
                print(f"  Users to load: {args.num_users}")
            else:
                print(f"  Users to load: All users")
        
        if args.questions_per_user:
            print(f"  Questions per user limit: {args.questions_per_user}")
        else:
            print(f"  Questions per user limit: All questions")
        
        print(f"{'='*80}")
        
        users_data = loader.load_users_questions(
            num_users=args.num_users,
            users_per_type=args.users_per_type,
            questions_per_user=args.questions_per_user,
            use_type_selection=args.use_type_selection,
            exclude_users=False
        )
        
        if not users_data:
            print("❌ No question data loaded")
            return
        
        # Apply --limit parameter (unified with locomo interface)
        if args.limit > 0:
            print(f"\n⚠️  Applying total question limit: {args.limit}")
            
            # Calculate total questions
            total_questions_before = sum(len(data["questions"]) for data in users_data.values())
            
            # Collect questions from all users, then truncate to first N
            limited_users_data = {}
            question_count = 0
            
            for user_id, user_data in users_data.items():
                if question_count >= args.limit:
                    break
                
                # Calculate how many questions current user can include
                remaining = args.limit - question_count
                user_questions = user_data["questions"][:remaining]
                
                if user_questions:
                    limited_users_data[user_id] = {
                        "questions": user_questions,
                        "user_type": user_data.get("user_type", "unknown")
                    }
                    question_count += len(user_questions)
            
            users_data = limited_users_data
            total_questions_after = sum(len(data["questions"]) for data in users_data.values())
            
            print(f"   Original questions: {total_questions_before}")
            print(f"   After limit: {total_questions_after}")
            print(f"   Affected users: {len(users_data)}")
        
        # 2. Get global expert ID
        print(f"\n{'='*80}")
        print(f"🔍 Finding global expert")
        print(f"{'='*80}")
        
        from storage.postgres_store import get_postgres_store
        from sqlalchemy import text
        
        postgres_store = await get_postgres_store()
        
        async with postgres_store.get_session() as session:
            # Query global expert via name field
            query = text("""
                SELECT id, name, display_name 
                FROM characters 
                WHERE name = 'longmemeval_global_expert'
                LIMIT 1
            """)
            
            result = await session.execute(query)
            row = result.fetchone()
            
            if not row:
                print("❌ Global expert not found (name='longmemeval_global_expert')")
                print("   Please run test_longmemeval_s_sim.py first to generate memories")
                return
            
            global_expert_id = row[0]
            expert_name = row[1]
            expert_display = row[2]
            
        print(f"✅ Found global expert:")
        print(f"   ID: {global_expert_id}")
        print(f"   Name: {expert_name}")
        print(f"   Display: {expert_display}")
        
        # 2.5. Handle ablation experiment configuration
        if args.config:
            config_path = Path(args.config)
            if not config_path.exists():
                raise FileNotFoundError(f"Ablation config file not found: {config_path}")
            
            print(f"\n🔧 Ablation experiment mode: using independent config initialization")
            print(f"   Config file: {config_path}")
            
            # Preview config (don't load globally)
            import yaml
            with open(config_path, 'r', encoding='utf-8') as f:
                config_preview = yaml.safe_load(f)
            
            forced_strategy = config_preview.get('retrieval', {}).get('forced_strategy')
            use_naive_rag = config_preview.get('retrieval', {}).get('use_naive_rag', False)
            
            if use_naive_rag:
                print(f"   Workflow mode: Naive RAG")
            elif forced_strategy:
                print(f"   Forced strategy: {forced_strategy}")
            else:
                print(f"   Intelligent routing: Enabled")
        else:
            config_path = None
            print(f"✅ Will use default config: config/datasets/longmemeval_s/retrieval_config.yaml")
        
        # 3. Initialize generator (configure concurrent parameters)
        concurrent_config = ConcurrentConfig(
            max_concurrent_requests=args.concurrent,
            batch_delay=args.batch_delay,
            max_retries=args.max_retries,
            retry_delays=[1.0, 2.0, 3.0],  # Tiered retry intervals
            timeout=args.timeout
        )
        
        print(f"\n{'='*80}")
        print(f"🔧 Concurrent configuration")
        print(f"{'='*80}")
        print(f"Concurrent threads: {concurrent_config.max_concurrent_requests}")
        print(f"Batch delay: {concurrent_config.batch_delay}s")
        print(f"Maximum retries: {concurrent_config.max_retries}")
        print(f"Retry intervals: {' → '.join([f'{d}s' for d in concurrent_config.retry_delays])}")
        print(f"Request timeout: {concurrent_config.timeout}s")
        
        generator = LongMemEvalSRetrievalGenerator(
            global_expert_id=global_expert_id,
            concurrent_config=concurrent_config,
            stats_helper=stats_helper,  # Pass statistics collector
            prompt_file=prompt_file,  # Pass prompt file path
            config_path=str(config_path) if config_path else None  # Pass config path
        )
        
        # 4. Generate answers
        output_data = await generator.generate_answers_for_all_users(users_data)
        
        # 5. Save results
        os.makedirs("logs/longmemeval_s", exist_ok=True)
        
        if args.output:
            output_file = args.output
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"logs/longmemeval_s/answers_{timestamp}.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        print(f"\n{'='*80}")
        print(f"💾 Answers saved")
        print(f"{'='*80}")
        print(f"File path: {output_file}")
        print(f"Total questions: {len(output_data['qa_results'])}")
        
        # 6. Save detailed memory diagnostic file (similar to test_retrieval_real_data.py)
        detailed_file = output_file.replace('.json', '_detailed_memories.json')
        
        detailed_data = {
            "metadata": output_data["metadata"],
            "diagnostics": {
                "purpose": "Detailed memory retrieval diagnostics",
                "description": "Contains complete memory retrieval details and memory refining information for each question",
                "use_cases": [
                    "Diagnose memory refining issues",
                    "Analyze memory retrieval quality",
                    "Verify user group isolation",
                    "Debug answer generation issues"
                ]
            },
            "questions": []
        }
        
        for qa_result in output_data["qa_results"]:
            question_detail = {
                "user_id": qa_result["user_id"],
                "question_idx": qa_result["question_idx"],
                "question": qa_result["question"],
                "question_date": qa_result.get("question_date", ""),
                "answer": qa_result["answer"],
                "prediction": qa_result["prediction"],
                "confidence": qa_result["confidence"],
                
                # Retrieval statistics
                "retrieval_summary": {
                    "total_memories_searched": qa_result["retrieval_metadata"].get("total_memories_searched", 0),
                    "final_memories_count": qa_result["memories_count"],
                    "retrieval_strategy": qa_result["retrieval_metadata"].get("retrieval_strategy", "unknown"),
                    "query_category": qa_result["retrieval_metadata"].get("query_category", "unknown"),
                    "query_complexity": qa_result["retrieval_metadata"].get("query_complexity", "unknown"),
                    "llm_keywords": qa_result["retrieval_metadata"].get("llm_keywords", [])
                },
                
                # Relevance filtering details
                "memory_refiner": qa_result.get("memory_refiner_info", {}),
                
                # Detailed memory list
                "memories": qa_result.get("memory_details", []),
                
                # Formatted memories (actual ones passed to LLM)
                "formatted_memories": qa_result.get("formatted_memories", [])
            }
            
            # Add filtering warning (if retention rate is too high)
            if question_detail["memory_refiner"].get("enabled", False):
                retention_rate = question_detail["memory_refiner"].get("retention_rate", 1.0)
                if retention_rate < 0.2:  # Retention rate below 20%
                    question_detail["warning"] = f"⚠️ Relevance filtering rate too high (only {retention_rate*100:.1f}% retained), may affect answer quality"
            
            detailed_data["questions"].append(question_detail)
        
        with open(detailed_file, 'w', encoding='utf-8') as f:
            json.dump(detailed_data, f, ensure_ascii=False, indent=2)
        
        print(f"\n📊 Detailed memory diagnostic file saved")
        print(f"File path: {detailed_file}")
        print(f"Contents:")
        print(f"  - Complete memory retrieval details for each question")
        print(f"  - Relevance filtering before/after comparison")
        print(f"  - Formatted memory content (passed to LLM)")
        print(f"  - Retrieval strategy and keyword analysis")
        
        print(f"\n💡 Next steps:")
        print(f"1. Use evaluation script to assess answer quality:")
        print(f"   python task_eval/longmemeval_s_evaluation.py --input {output_file}")
        print(f"\n2. Analyze memory retrieval details:")
        print(f"   View {detailed_file}")
        print(f"   Focus on 'memory_refiner' and 'warning' fields")
        
        # 7. Stop statistics collection and generate report
        stats_collector.end_collection()
        print(f"\n{'='*80}")
        print(f"📊 Generating statistics report")
        print(f"{'='*80}")
        
        # Update actual input tokens from prompt file (replace estimation)
        print(f"🔄 Updating actual input tokens from prompt file...")
        stats_helper.update_tokens_from_prompt_file(prompt_file)
        
        # Print statistics summary
        print(f"\n📈 Statistics summary:")
        stats_helper.print_summary(detailed=True)
        
        # Export statistics data
        stats_json_path = f"logs/longmemeval_s/stats_{timestamp_str}.json"
        stats_csv_dir = f"logs/longmemeval_s/stats_csv_{timestamp_str}"
        
        stats_helper.export_results(stats_json_path, stats_csv_dir)
        
        # Export prompt data (readable format)
        prompt_readable_path = f"logs/longmemeval_s/prompts_{timestamp_str}.txt"
        file_prompt_collector.export_to_readable_format(prompt_readable_path)
        
        # Print prompt statistics
        prompt_stats = file_prompt_collector.get_file_stats()
        print(f"\n📝 Prompt statistics:")
        print(f"  Total prompts: {prompt_stats['total_prompts']}")
        print(f"  Total input tokens: {prompt_stats.get('total_prompt_tokens', 0):,} ({'tiktoken accurate' if prompt_stats.get('tiktoken_used', False) else 'estimated'})")
        print(f"  File size: {prompt_stats.get('file_size_bytes', 0):,} bytes")
        
        print(f"\n{'='*80}")
        print(f"💾 All files saved")
        print(f"{'='*80}")
        print(f"📋 Answer files:")
        print(f"  - Answer JSON: {output_file}")
        print(f"  - Detailed memories: {detailed_file}")
        print(f"\n📊 Statistics files:")
        print(f"  - Statistics JSON: {stats_json_path}")
        print(f"  - Statistics CSV: {stats_csv_dir}/")
        print(f"\n📝 Prompt files:")
        print(f"  - Prompt raw: {prompt_file}")
        print(f"  - Prompt readable: {prompt_readable_path}")
        print(f"{'='*80}")
        
    except Exception as e:
        print(f"\n❌ Execution failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        # Clean up resources
        try:
            # Stop statistics collector
            try:
                stats_collector.end_collection()
                print(f"\n✅ Statistics collector stopped")
            except Exception as stats_error:
                print(f"\n⚠️ Statistics collector stop warning: {stats_error}")
            
            # Disable prompt collection
            try:
                from llm.file_prompt_collector import disable_file_prompt_collection
                disable_file_prompt_collection()
                print(f"✅ Prompt collector stopped")
            except Exception as prompt_error:
                print(f"⚠️ Prompt collector stop warning: {prompt_error}")
            
            from llm.core.async_http_pool import close_global_http_pool
            from llm.http_client_manager import close_global_http_client
            
            # Close HTTP connection pool
            await close_global_http_pool()
            await close_global_http_client()
            
            print("✅ Resource cleanup complete")
        except Exception as cleanup_error:
            print(f"\n⚠️ Resource cleanup warning: {cleanup_error}")
    
    print(f"\n End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code if exit_code else 0)


