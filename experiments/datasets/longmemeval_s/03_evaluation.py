#!/usr/bin/env python3
"""
LongMemEval-S Answer Evaluation Script (supports 20 concurrent + batch processing + detailed output)

✅ Use longmemeval native evaluation method to evaluate generated answers
- Specialized evaluation prompts for different task types
- Support off-by-one tolerance for temporal reasoning tasks
- Support special tasks like knowledge update and preference reasoning
- Default: LongMemEval native evaluation + traditional metrics (F1, BLEU, METEOR, BERTScore)
- 🚀 Support 20 concurrent LLM evaluations, significantly improving evaluation speed
- 🚀 Support batch processing of traditional metrics (refer to timem_qa_evaluation.py), especially BERTScore batch GPU acceleration
- 📊 Generate detailed CSV evaluation result tables (refer to timem_qa_evaluation.py)

Output files:
1. *_scores_TIMESTAMP.json - Complete evaluation results (JSON format)
2. *_scores_TIMESTAMP_scores_table.csv - Detailed evaluation scores table for each question
3. *_scores_TIMESTAMP_summary_table.csv - Summary statistics table grouped by question type

Usage:
1. Basic run (auto find latest file, LLM evaluation + traditional metrics, 20 concurrent):
   python experiments/datasets/longmemeval_s/03_evaluation.py
   
2. Specify input file:
   python experiments/datasets/longmemeval_s/03_evaluation.py --input logs/longmemeval_s/answers_xxx.json
   
3. Use only LLM evaluation (don't calculate traditional metrics):
   python experiments/datasets/longmemeval_s/03_evaluation.py --disable-traditional
   
4. Use only traditional metrics (faster, don't call LLM):
   python experiments/datasets/longmemeval_s/03_evaluation.py --traditional-only
   
5. Specify LLM evaluation model:
   python experiments/datasets/longmemeval_s/03_evaluation.py --eval-model gpt-4o-mini
   
6. Customize concurrent parameters (default 20 concurrent):
   python experiments/datasets/longmemeval_s/03_evaluation.py --max-concurrent 30 --batch-delay 0.3
   
7. Customize timeout and retries:
   python experiments/datasets/longmemeval_s/03_evaluation.py --timeout 60 --max-retries 30
   
8. Specify output file:
   python experiments/datasets/longmemeval_s/03_evaluation.py --output my_scores.json

Concurrent parameters description:
--max-concurrent: Maximum concurrent requests (default 20)
--batch-delay: Delay between batches in seconds (default 0.5s)
--max-retries: Maximum number of retries (default 20)
--timeout: Single request timeout in seconds (default 30s)
"""

import os
import sys
import json
import argparse
import asyncio
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
import numpy as np
from collections import defaultdict, Counter
from tqdm import tqdm
from dataclasses import dataclass

# Add project root directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
# Go up from experiments/datasets/longmemeval_s to find project root (TiMem_demo)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
sys.path.insert(0, project_root)

# Import LLM related types
from llm.base_llm import Message, MessageRole

# Import longmemeval evaluation tools
longmemeval_eval_available = False
try:
    # [UPDATED] Import from new location: config/datasets/longmemeval_s/evaluate_qa.py
    longmemeval_path = os.path.join(project_root, "config", "datasets", "longmemeval_s")
    if os.path.exists(longmemeval_path):
        sys.path.insert(0, longmemeval_path)
        # Import longmemeval native evaluation functions
        from evaluate_qa import get_anscheck_prompt, chat_completions_with_backoff as longmemeval_chat_with_backoff
        longmemeval_eval_available = True
        print(f"✅ Successfully imported longmemeval native evaluation module")
    else:
        print(f"⚠️ longmemeval evaluation module path not found: {longmemeval_path}")
except Exception as e:
    print(f"⚠️ Failed to import longmemeval evaluation module: {e}")
    print(f"   Will use built-in evaluation method as fallback")


# Async task tracker
class AsyncTaskManager:
    """Async task manager for tracking and cleaning up all async tasks"""
    
    def __init__(self):
        self.active_tasks: set = set()
        self.is_shutting_down = False
        self._lock = asyncio.Lock()
    
    async def create_task(self, coro, name: str = None):
        """Create and track async task"""
        if self.is_shutting_down:
            return None
            
        task = asyncio.create_task(coro)
        async with self._lock:
            self.active_tasks.add(task)
        
        # Add completion callback to auto clean up completed tasks
        task.add_done_callback(lambda t: asyncio.create_task(self._remove_task(t)))
        return task
    
    async def _remove_task(self, task):
        """Remove task from active tasks set"""
        async with self._lock:
            self.active_tasks.discard(task)
    
    async def shutdown(self, timeout: float = 5.0):
        """Gracefully shutdown all tasks"""
        self.is_shutting_down = True
        
        async with self._lock:
            if not self.active_tasks:
                return
            
            print(f"🔄 Canceling {len(self.active_tasks)} active tasks...")
            
            # Cancel all tasks
            for task in self.active_tasks:
                if not task.done():
                    task.cancel()
            
            # Wait for tasks to complete or timeout
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self.active_tasks, return_exceptions=True),
                    timeout=timeout
                )
                print("✅ All tasks successfully canceled")
            except asyncio.TimeoutError:
                print(f"⚠️ Task cancellation timeout ({timeout}s), force cleanup")
            except Exception:
                pass  # Ignore exceptions when canceling tasks
            
            self.active_tasks.clear()


# Concurrent configuration
@dataclass
class ConcurrentEvalConfig:
    """Concurrent evaluation configuration class"""
    
    def __init__(self, max_concurrent_requests: int = 20, batch_delay: float = 0.5, 
                 max_retries: int = 20, retry_delays: List[float] = None, timeout: float = 30.0):
        self.max_concurrent_requests = max_concurrent_requests
        self.batch_delay = batch_delay
        self.max_retries = max_retries
        self.retry_delays = retry_delays or [1.0, 2.0, 3.0]  # Tiered wait times: 1s, 2s, 3s
        self.timeout = timeout


class LongMemEvalSScorer:
    """LongMemEval-S Scorer (supports batch processing)"""
    
    def __init__(self, use_cuda: bool = True, verbose: bool = False, batch_size: int = 32):
        self.use_cuda = use_cuda
        self.verbose = verbose
        self.batch_size = batch_size
        
        # CUDA device configuration
        import torch
        self.device = 'cuda' if (self.use_cuda and torch.cuda.is_available()) else 'cpu'
        
        # Initialize evaluation tools
        self._init_scorers()
        
        # BERTScore batch processing state
        self.bert_model_loaded = False
    
    def _init_scorers(self):
        """Initialize various scorers"""
        print(f"\n{'='*80}")
        print(f"🔧 Initializing evaluation tools")
        print(f"{'='*80}")
        
        # 1. Import necessary libraries
        try:
            import nltk
            nltk_data_path = os.path.join(project_root, "nltk_data")
            if os.path.exists(nltk_data_path):
                nltk.data.path.insert(0, nltk_data_path)
            print("✅ NLTK loaded")
        except ImportError:
            print("⚠️ NLTK not installed")
        
        # 2. Initialize BERTScore (batch processing version)
        try:
            from bert_score import score as bert_score
            self.bert_score_fn = bert_score
            print("✅ BERTScore loaded (batch processing mode)")
            
            # Test BERTScore functionality to ensure model is loaded
            if self.bert_score_fn:
                try:
                    test_scores = self.bert_score_fn(
                        ["test prediction"], 
                        ["test reference"], 
                        lang='en', 
                        verbose=False, 
                        device=self.device
                    )
                    self.bert_model_loaded = True
                    print(f"✅ BERTScore model initialized successfully, device: {self.device}")
                except Exception as e:
                    print(f"⚠️ BERTScore model initialization failed: {e}")
                    self.bert_model_loaded = False
        except ImportError:
            print("⚠️ BERTScore not installed")
            self.bert_score_fn = None
            self.bert_model_loaded = False
        
        # 3. Initialize METEOR
        try:
            from nltk.translate import meteor_score
            self.meteor_score_fn = meteor_score.meteor_score
            print("✅ METEOR loaded")
        except ImportError:
            print("⚠️ METEOR not installed")
            self.meteor_score_fn = None
    
    def calculate_f1(self, prediction: str, reference: str) -> float:
        """Calculate F1 score"""
        # Ensure inputs are string type
        prediction = str(prediction) if prediction is not None else ""
        reference = str(reference) if reference is not None else ""
        
        pred_tokens = set(prediction.lower().split())
        ref_tokens = set(reference.lower().split())
        
        if not pred_tokens or not ref_tokens:
            return 0.0
        
        common = pred_tokens & ref_tokens
        if not common:
            return 0.0
        
        precision = len(common) / len(pred_tokens)
        recall = len(common) / len(ref_tokens)
        
        if precision + recall == 0:
            return 0.0
        
        f1 = 2 * precision * recall / (precision + recall)
        return f1
    
    def calculate_bleu(self, prediction: str, reference: str, n: int = 1) -> float:
        """Calculate BLEU score"""
        try:
            from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction
            
            # Ensure inputs are string type
            prediction = str(prediction) if prediction is not None else ""
            reference = str(reference) if reference is not None else ""
            
            pred_tokens = prediction.lower().split()
            ref_tokens = [reference.lower().split()]
            
            weights = [1.0/n] * n + [0.0] * (4-n)
            smoothing = SmoothingFunction().method1
            
            score = sentence_bleu(ref_tokens, pred_tokens, 
                                weights=weights, 
                                smoothing_function=smoothing)
            return score
        except:
            return 0.0
    
    def calculate_rouge_l(self, prediction: str, reference: str) -> float:
        """Calculate Rouge-L score"""
        try:
            from rouge import Rouge
            rouge = Rouge()
            # Ensure inputs are string type
            prediction = str(prediction) if prediction is not None else ""
            reference = str(reference) if reference is not None else ""
            scores = rouge.get_scores(prediction, reference)[0]
            return scores['rouge-l']['f']
        except:
            # Simple LCS implementation
            # Ensure inputs are string type
            prediction = str(prediction) if prediction is not None else ""
            reference = str(reference) if reference is not None else ""
            pred_tokens = prediction.lower().split()
            ref_tokens = reference.lower().split()
            
            m, n = len(pred_tokens), len(ref_tokens)
            dp = [[0] * (n+1) for _ in range(m+1)]
            
            for i in range(1, m+1):
                for j in range(1, n+1):
                    if pred_tokens[i-1] == ref_tokens[j-1]:
                        dp[i][j] = dp[i-1][j-1] + 1
                    else:
                        dp[i][j] = max(dp[i-1][j], dp[i][j-1])
            
            lcs_length = dp[m][n]
            
            if m == 0 or n == 0:
                return 0.0
            
            precision = lcs_length / m
            recall = lcs_length / n
            
            if precision + recall == 0:
                return 0.0
            
            f1 = 2 * precision * recall / (precision + recall)
            return f1
    
    def calculate_meteor(self, prediction: str, reference: str) -> float:
        """Calculate METEOR score"""
        if self.meteor_score_fn is None:
            return 0.0
        
        try:
            # Ensure inputs are string type
            prediction = str(prediction) if prediction is not None else ""
            reference = str(reference) if reference is not None else ""
            
            pred_tokens = prediction.lower().split()
            ref_tokens = [reference.lower().split()]
            
            score = self.meteor_score_fn(ref_tokens, pred_tokens)
            return score
        except:
            return 0.0
    
    def calculate_bert_score(self, prediction: str, reference: str) -> float:
        """Calculate BERTScore F1 (single)"""
        if self.bert_score_fn is None or not self.bert_model_loaded:
            return 0.0
        
        try:
            # Ensure inputs are string type
            prediction = str(prediction) if prediction is not None else ""
            reference = str(reference) if reference is not None else ""
            P, R, F1 = self.bert_score_fn(
                [prediction], 
                [reference],
                lang="en",
                verbose=False,
                device=self.device
            )
            return F1.item()
        except:
            return 0.0
    
    def calculate_bert_score_batch(self, predictions: list, references: list) -> list:
        """Batch calculate BERTScore F1 (GPU optimized version)"""
        if self.bert_score_fn is None or not self.bert_model_loaded:
            return [0.0] * len(predictions)
        
        try:
            # Ensure all inputs are string type
            safe_predictions = [str(p) if p is not None else "" for p in predictions]
            safe_references = [str(r) if r is not None else "" for r in references]
            
            # Batch calculate BERTScore
            P, R, F1 = self.bert_score_fn(
                safe_predictions, 
                safe_references,
                lang="en",
                verbose=False,
                device=self.device
            )
            
            # Return F1 scores list
            scores = [max(0.0, min(1.0, f1.item())) for f1 in F1]
            return scores
        except Exception as e:
            if self.verbose:
                print(f"⚠️ BERTScore batch calculation failed: {e}")
            return [0.0] * len(predictions)
    
    def calculate_exact_match(self, prediction: str, reference: str) -> float:
        """Calculate exact match"""
        # Ensure inputs are string type
        prediction = str(prediction) if prediction is not None else ""
        reference = str(reference) if reference is not None else ""
        
        pred_normalized = prediction.lower().strip()
        ref_normalized = reference.lower().strip()
        return 1.0 if pred_normalized == ref_normalized else 0.0
    
    def score_qa_pair(self, prediction: str, reference: str) -> Dict[str, float]:
        """Score a single QA pair"""
        scores = {
            "f1": self.calculate_f1(prediction, reference),
            "bleu_1": self.calculate_bleu(prediction, reference, n=1),
            "bleu_2": self.calculate_bleu(prediction, reference, n=2),
            "rouge_l": self.calculate_rouge_l(prediction, reference),
            "meteor": self.calculate_meteor(prediction, reference),
            "bert_score_f1": self.calculate_bert_score(prediction, reference),
            "exact_match": self.calculate_exact_match(prediction, reference)
        }
        
        return scores
    
    def score_qa_batch(self, predictions: list, references: list) -> list:
        """Batch score QA pairs (GPU optimized version)"""
        batch_size = len(predictions)
        
        if self.verbose:
            print(f"🔄 Starting batch scoring: {batch_size} QA pairs")
        
        # Pre-validate all input data
        safe_predictions = []
        safe_references = []
        
        for i in range(batch_size):
            try:
                safe_p = str(predictions[i]) if i < len(predictions) and predictions[i] is not None else ""
                safe_r = str(references[i]) if i < len(references) and references[i] is not None else ""
                
                safe_predictions.append(safe_p)
                safe_references.append(safe_r)
                
            except Exception as e:
                if self.verbose:
                    print(f"⚠️ Data validation failed QA {i+1}: {e}")
                safe_predictions.append("")
                safe_references.append("")
        
        # Batch calculate BERTScore F1 (GPU optimized)
        bert_scores = []
        if self.bert_score_fn and self.bert_model_loaded:
            try:
                if self.verbose:
                    print(f"🚀 Batch calculating BERTScore F1 (device: {self.device})...")
                bert_scores = self.calculate_bert_score_batch(safe_predictions, safe_references)
                if self.verbose:
                    print(f"✅ BERTScore F1 batch calculation complete")
            except Exception as e:
                if self.verbose:
                    print(f"⚠️ BERTScore F1 batch calculation failed: {e}")
                bert_scores = [0.0] * batch_size
        else:
            bert_scores = [0.0] * batch_size
        
        # Calculate other metrics for each QA pair
        batch_results = []
        for i in range(batch_size):
            result = {}
            
            if not safe_predictions[i] or not safe_references[i]:
                result = {
                    "f1": 0.0,
                    "bleu_1": 0.0,
                    "bleu_2": 0.0,
                    "rouge_l": 0.0,
                    "meteor": 0.0,
                    "bert_score_f1": 0.0,
                    "exact_match": 0.0
                }
                batch_results.append(result)
                continue
            
            try:
                # F1 Score calculation
                try:
                    result['f1'] = self.calculate_f1(safe_predictions[i], safe_references[i])
                except Exception as e:
                    if self.verbose:
                        print(f"⚠️ F1 Score calculation failed QA {i+1}: {e}")
                    result['f1'] = 0.0
                
                # BLEU-1 calculation
                try:
                    result['bleu_1'] = self.calculate_bleu(safe_predictions[i], safe_references[i], n=1)
                except Exception as e:
                    if self.verbose:
                        print(f"⚠️ BLEU-1 calculation failed QA {i+1}: {e}")
                    result['bleu_1'] = 0.0
                
                # BLEU-2 calculation
                try:
                    result['bleu_2'] = self.calculate_bleu(safe_predictions[i], safe_references[i], n=2)
                except Exception as e:
                    if self.verbose:
                        print(f"⚠️ BLEU-2 calculation failed QA {i+1}: {e}")
                    result['bleu_2'] = 0.0
                
                # Rouge-L Score calculation
                try:
                    result['rouge_l'] = self.calculate_rouge_l(safe_predictions[i], safe_references[i])
                except Exception as e:
                    if self.verbose:
                        print(f"⚠️ Rouge-L calculation failed QA {i+1}: {e}")
                    result['rouge_l'] = 0.0
                
                # METEOR calculation
                try:
                    result['meteor'] = self.calculate_meteor(safe_predictions[i], safe_references[i])
                except Exception as e:
                    if self.verbose:
                        print(f"⚠️ METEOR calculation failed QA {i+1}: {e}")
                    result['meteor'] = 0.0
                
                # BERTScore F1 (using batch calculation results)
                if i < len(bert_scores):
                    result['bert_score_f1'] = bert_scores[i]
                else:
                    result['bert_score_f1'] = 0.0
                
                # Exact Match calculation
                try:
                    result['exact_match'] = self.calculate_exact_match(safe_predictions[i], safe_references[i])
                except Exception as e:
                    if self.verbose:
                        print(f"⚠️ Exact Match calculation failed QA {i+1}: {e}")
                    result['exact_match'] = 0.0
                
            except Exception as e:
                if self.verbose:
                    print(f"⚠️ QA {i+1} scoring failed: {e}")
                result = {
                    "f1": 0.0,
                    "bleu_1": 0.0,
                    "bleu_2": 0.0,
                    "rouge_l": 0.0,
                    "meteor": 0.0,
                    "bert_score_f1": 0.0,
                    "exact_match": 0.0
                }
            
            batch_results.append(result)
        
        if self.verbose:
            print(f"✅ Batch scoring complete: {len(batch_results)} results")
        return batch_results


class LongMemEvalNativeEvaluator:
    """LongMemEval native evaluator (using TiMem unified LLM manager) - supports concurrent evaluation"""
    
    def __init__(
        self,
        eval_model: Optional[str] = None,
        verbose: bool = False,
        concurrent_config: Optional[ConcurrentEvalConfig] = None
    ):
        self.verbose = verbose
        self.llm_manager = None
        self.eval_model = eval_model
        self._is_initialized = False
        
        # Concurrent configuration
        self.concurrent_config = concurrent_config or ConcurrentEvalConfig()
        self.semaphore = asyncio.Semaphore(self.concurrent_config.max_concurrent_requests)
        
        # Async task manager
        self.task_manager = AsyncTaskManager()
        
        # Concurrent statistics
        self.concurrent_stats = {
            'total_evaluations': 0,
            'successful_evaluations': 0,
            'failed_evaluations': 0,
            'total_retries': 0,
            'avg_eval_time': 0.0
        }
        
        # Get evaluation model from dataset configuration
        if not eval_model:
            try:
                from timem.utils.config_manager import get_config_manager
                config_manager = get_config_manager()
                # Prioritize reading from eval_llm_config, backward compatible with eval_model field
                eval_config = config_manager.get_config("eval_prompt") or {}
                eval_llm_config = eval_config.get("eval_llm_config", {})
                
                # If eval_llm_config exists, use its model
                if eval_llm_config and "model" in eval_llm_config:
                    self.eval_model = eval_llm_config["model"]
                    self.eval_temperature = eval_llm_config.get("temperature", 0.0)
                    self.eval_max_tokens = eval_llm_config.get("max_tokens", 500)
                # Otherwise use old eval_model field
                else:
                    self.eval_model = eval_config.get("eval_model", "gpt-4o-mini")
                    self.eval_temperature = 0.0
                    self.eval_max_tokens = 500
            except Exception as e:
                print(f"⚠️ Failed to read evaluation model from config: {e}, using default")
                self.eval_model = "gpt-4o-mini"
                self.eval_temperature = 0.0
                self.eval_max_tokens = 500
        else:
            # If model specified via parameter, use default other parameters
            self.eval_temperature = 0.0
            self.eval_max_tokens = 500
        
        print(f"\n🤖 LongMemEval native evaluator initialization (concurrent version)")
        print(f"   🎯 Evaluation model: {self.eval_model}")
        print(f"   🌡️ Temperature: {self.eval_temperature}")
        print(f"   📝 Max tokens: {self.eval_max_tokens}")
        print(f"   🔧 Using TiMem unified LLM manager")
        print(f"   ⚡ Max concurrent: {self.concurrent_config.max_concurrent_requests}")
        print(f"   ⏱️ Batch delay: {self.concurrent_config.batch_delay}s")
        print(f"   🔄 Retry strategy: Tiered wait {' → '.join([f'{d}s' for d in self.concurrent_config.retry_delays])}")
    
    def _get_llm(self):
        """Get LLM instance (lazy initialization)"""
        if self.llm_manager is None:
            from llm.llm_manager import get_llm
            self.llm_manager = get_llm()
        return self.llm_manager
    
    async def __aenter__(self):
        """Async context manager entry"""
        self._is_initialized = True
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - ensure resources are properly cleaned up"""
        await self._cleanup_resources()
    
    async def _cleanup_resources(self):
        """Clean up all resources"""
        if not self._is_initialized:
            return
            
        print("🧹 Starting evaluator resource cleanup...")
        
        try:
            # 1. First close task manager, cancel all active tasks
            await self.task_manager.shutdown(timeout=3.0)
            
            # 2. Clean up LLM adapter
            try:
                from llm.core.async_http_pool import close_global_http_pool
                await close_global_http_pool()
                print("✅ Global HTTP connection pool closed")
            except Exception as e:
                print(f"⚠️ Global HTTP connection pool cleanup failed: {e}")
            
            # 3. Wait for all aiohttp resources to be fully released
            await asyncio.sleep(0.1)
            
            self._is_initialized = False
            print("✅ Evaluator resource cleanup complete")
            
        except Exception as e:
            print(f"⚠️ Error during resource cleanup: {e}")
    
    async def _chat_with_retry(self, prompt: str, max_retries: int = None) -> str:
        """Call LLM using TiMem LLM adapter (with retry and timeout)"""
        llm = self._get_llm()
        max_retries = max_retries or self.concurrent_config.max_retries
        
        for attempt in range(max_retries + 1):
            try:
                # Build message using Message object
                messages = [Message(role=MessageRole.USER, content=prompt)]
                
                # Use configured evaluation model parameters to call LLM
                response = await asyncio.wait_for(
                    llm.chat(
                        messages=messages,
                        model=self.eval_model,
                        temperature=self.eval_temperature,
                        max_tokens=self.eval_max_tokens
                    ),
                    timeout=self.concurrent_config.timeout
                )
                
                # ChatResponse object has content attribute
                return response.content.strip()
                
            except asyncio.TimeoutError:
                self.concurrent_stats['total_retries'] += 1
                if attempt < max_retries:
                    delay_index = min(attempt, len(self.concurrent_config.retry_delays) - 1)
                    retry_delay = self.concurrent_config.retry_delays[delay_index]
                    if self.verbose:
                        print(f"⚠️ LLM call timeout (attempt {attempt + 1}/{max_retries + 1}): waiting {retry_delay}s before retry...")
                    await asyncio.sleep(retry_delay)
                else:
                    raise Exception(f"LLM call timeout ({self.concurrent_config.timeout}s) after {max_retries} retries")
            except Exception as e:
                self.concurrent_stats['total_retries'] += 1
                if attempt < max_retries:
                    delay_index = min(attempt, len(self.concurrent_config.retry_delays) - 1)
                    retry_delay = self.concurrent_config.retry_delays[delay_index]
                    if self.verbose:
                        print(f"⚠️ LLM call failed (attempt {attempt + 1}/{max_retries + 1}): {e}")
                        print(f"   Waiting {retry_delay}s before retry...")
                    await asyncio.sleep(retry_delay)
                else:
                    raise
    
    async def evaluate_single_qa(
        self,
        question: str,
        answer: str,
        prediction: str,
        question_type: str = "single-session-user",
        is_abstention: bool = False,
        qa_index: int = 0
    ) -> Dict[str, Any]:
        """
        Evaluate a single QA pair using longmemeval native method (with semaphore concurrency control)
        
        Args:
            question: Question
            answer: Standard answer
            prediction: Model prediction
            question_type: Question type (single-session-user, temporal-reasoning, etc.)
            is_abstention: Whether it's a refusal to answer
            qa_index: QA pair index (for logging)
        
        Returns:
            Evaluation result dictionary
        """
        if not longmemeval_eval_available:
            return {
                "success": False,
                "error": "longmemeval evaluation module not available"
            }
        
        async with self.semaphore:  # Control concurrency
            retry_count = 0
            last_error = None
            
            while retry_count <= self.concurrent_config.max_retries:
                try:
                    # Ensure answer and prediction are strings
                    answer_str = str(answer) if answer is not None else ""
                    prediction_str = str(prediction) if prediction is not None else ""
                    
                    # Use longmemeval native prompt
                    prompt = get_anscheck_prompt(
                        task=question_type,
                        question=question,
                        answer=answer_str,
                        response=prediction_str,
                        abstention=is_abstention
                    )
                    
                    # Call LLM for evaluation (using TiMem unified interface)
                    eval_response = await self._chat_with_retry(prompt, max_retries=3)
                    
                    # Determine if correct (longmemeval standard: contains "yes")
                    is_correct = 'yes' in eval_response.lower()
                    
                    if self.verbose:
                        print(f"\nQuestion {qa_index}: {question[:100]}...")
                        print(f"Answer: {answer_str[:100]}...")
                        print(f"Prediction: {prediction_str[:100]}...")
                        print(f"Evaluation: {eval_response} -> {'✓' if is_correct else '✗'}")
                    
                    self.concurrent_stats['successful_evaluations'] += 1
                    return {
                        "success": True,
                        "is_correct": is_correct,
                        "score": 1.0 if is_correct else 0.0,
                        "reason": eval_response,
                        "raw_response": eval_response,
                        "question_type": question_type,
                        "retry_count": retry_count
                    }
                    
                except asyncio.TimeoutError:
                    last_error = f"Evaluation timeout after {self.concurrent_config.timeout}s"
                    self.concurrent_stats['total_retries'] += 1
                    retry_count += 1
                    if self.verbose:
                        print(f"⚠️ Evaluation timeout (attempt {retry_count}/{self.concurrent_config.max_retries + 1}): {last_error}")
                    
                    if retry_count <= self.concurrent_config.max_retries:
                        delay_index = min(retry_count - 1, len(self.concurrent_config.retry_delays) - 1)
                        retry_delay = self.concurrent_config.retry_delays[delay_index]
                        await asyncio.sleep(retry_delay)
                    else:
                        break
                        
                except Exception as e:
                    last_error = str(e)
                    self.concurrent_stats['total_retries'] += 1
                    retry_count += 1
                    if self.verbose:
                        print(f"⚠️ Evaluation failed (attempt {retry_count}/{self.concurrent_config.max_retries + 1}): {e}")
                    
                    if retry_count <= self.concurrent_config.max_retries:
                        delay_index = min(retry_count - 1, len(self.concurrent_config.retry_delays) - 1)
                        retry_delay = self.concurrent_config.retry_delays[delay_index]
                        await asyncio.sleep(retry_delay)
                    else:
                        break
            
            # All retries failed
            self.concurrent_stats['failed_evaluations'] += 1
            return {
                "success": False,
                "error": f"Evaluation failed (retry {retry_count-1} times): {last_error}",
                "score": 0.0,
                "reason": "",
                "raw_response": "",
                "question_type": question_type,
                "retry_count": retry_count - 1
            }
    
    async def evaluate_batch(
        self,
        qa_pairs: List[Dict[str, Any]],
        show_progress: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Batch concurrent evaluation (true concurrent version)
        
        Args:
            qa_pairs: QA pair list, each containing question, answer, prediction, question_type
            show_progress: Whether to show progress bar
        
        Returns:
            Evaluation result list
        """
        if not qa_pairs:
            return []
        
        print(f"🚀 Starting batch concurrent evaluation (total {len(qa_pairs)} questions)")
        
        # Execute tasks in batches
        batch_size = self.concurrent_config.max_concurrent_requests
        results = []
        total_batches = (len(qa_pairs) + batch_size - 1) // batch_size
        
        # Accuracy statistics
        total_processed = 0
        total_correct = 0
        
        # Create overall progress bar
        with tqdm(total=len(qa_pairs), desc=f"🤖 LongMemEval concurrent evaluation", unit="qa", 
                 bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
                 ncols=120, colour='cyan') as main_pbar:
            
            for batch_idx in range(total_batches):
                start_idx = batch_idx * batch_size
                end_idx = min(start_idx + batch_size, len(qa_pairs))
                batch_data = qa_pairs[start_idx:end_idx]
                
                batch_start_time = asyncio.get_event_loop().time()
                
                print(f"\n{'='*60}")
                print(f"📦 Evaluation batch {batch_idx + 1}/{total_batches}")
                print(f"📊 Current batch: {len(batch_data)} tasks (tasks {start_idx + 1}-{end_idx})")
                print(f"{'='*60}")
                
                # Update main progress bar description
                main_pbar.set_description(f"🤖 Batch {batch_idx + 1}/{total_batches}")
                
                try:
                    # Create concurrent tasks (using task manager)
                    concurrent_tasks = []
                    for i, qa_item in enumerate(batch_data):
                        try:
                            # Use task manager to create task
                            task = await self.task_manager.create_task(
                                self.evaluate_single_qa(
                                    question=qa_item.get("question", ""),
                                    answer=qa_item.get("answer", ""),
                                    prediction=qa_item.get("prediction", ""),
                                    question_type=qa_item.get("question_type", "single-session-user"),
                                    is_abstention=qa_item.get("is_abstention", False),
                                    qa_index=start_idx + i
                                ),
                                name=f"eval_{start_idx + i}"
                            )
                            if task:
                                concurrent_tasks.append(task)
                        except Exception as e:
                            print(f"⚠️ Failed to create evaluation task {start_idx + i + 1}: {e}")
                            # Create a failed task result coroutine
                            async def failed_task():
                                return {
                                    "success": False,
                                    "error": f"Task creation failed: {str(e)}",
                                    "score": 0.0,
                                    "reason": "",
                                    "raw_response": "",
                                    "question_type": "unknown",
                                    "retry_count": 0
                                }
                            failed_task_obj = await self.task_manager.create_task(failed_task(), name=f"failed_task_{start_idx + i}")
                            if failed_task_obj:
                                concurrent_tasks.append(failed_task_obj)
                    
                    # Execute batch concurrent tasks
                    if concurrent_tasks:
                        batch_results = await asyncio.gather(*concurrent_tasks, return_exceptions=True)
                    else:
                        batch_results = []
                    
                    # Process batch results
                    batch_successes = 0
                    batch_processed = 0
                    for i, result in enumerate(batch_results):
                        if isinstance(result, Exception):
                            # Handle exception result
                            print(f"⚠️ Evaluation task {start_idx + i + 1} execution exception: {result}")
                            error_result = {
                                "success": False,
                                "error": f"Task execution exception: {str(result)}",
                                "score": 0.0,
                                "reason": "",
                                "raw_response": "",
                                "question_type": "unknown",
                                "retry_count": 0
                            }
                            results.append(error_result)
                            self.concurrent_stats['failed_evaluations'] += 1
                            batch_processed += 1
                        else:
                            # Normal result
                            results.append(result)
                            self.concurrent_stats['total_evaluations'] += 1
                            batch_processed += 1
                            if result.get('success') and result.get('is_correct'):
                                batch_successes += 1
                                self.concurrent_stats['successful_evaluations'] += 1
                    
                    # Update overall statistics
                    total_processed += batch_processed
                    total_correct += batch_successes
                    
                    batch_end_time = asyncio.get_event_loop().time()
                    batch_duration = batch_end_time - batch_start_time
                    
                    # Calculate batch accuracy and cumulative accuracy
                    batch_accuracy = (batch_successes / batch_processed * 100) if batch_processed > 0 else 0.0
                    cumulative_accuracy = (total_correct / total_processed * 100) if total_processed > 0 else 0.0
                    
                    # Display batch result statistics
                    print(f"  Execution time: {batch_duration:.2f}s")
                    print(f"  Batch success: {batch_successes}/{batch_processed} ({batch_accuracy:.1f}%)")
                    print(f"  📊 Cumulative accuracy: {total_correct}/{total_processed} ({cumulative_accuracy:.1f}%)")
                    print(f"  📈 Current overall progress: {total_processed}/{len(qa_pairs)} ({total_processed/len(qa_pairs)*100:.1f}%)")
                    
                except Exception as e:
                    print(f"❌ Evaluation batch {batch_idx + 1} execution failed: {str(e)}")
                    
                    # Create error results for failed batch
                    batch_failed = 0
                    for _ in batch_data:
                        error_result = {
                            "success": False,
                            "error": f"Batch execution failed: {str(e)}",
                            "is_correct": False,
                            "eval_response": "",
                            "question_type": "unknown",
                            "retry_count": 0
                        }
                        results.append(error_result)
                        self.concurrent_stats['failed_evaluations'] += 1
                        batch_failed += 1
                    
                    # Update overall statistics (failed batch)
                    total_processed += batch_failed
                    
                    # Display failed batch statistics
                    cumulative_accuracy = (total_correct / total_processed * 100) if total_processed > 0 else 0.0
                    print(f"  Batch failed: 0/{batch_failed} (0.0%)")
                    print(f"  📊 Cumulative accuracy: {total_correct}/{total_processed} ({cumulative_accuracy:.1f}%)")
                    print(f"  📈 Current overall progress: {total_processed}/{len(qa_pairs)} ({total_processed/len(qa_pairs)*100:.1f}%)")
                
                # Update main progress bar
                main_pbar.update(len(batch_data))
                
                # Delay between batches
                if batch_idx < total_batches - 1:  # Not the last batch
                    current_accuracy = (total_correct / total_processed * 100) if total_processed > 0 else 0.0
                    print(f"⏳ Batch delay {self.concurrent_config.batch_delay}s... (current accuracy: {current_accuracy:.1f}%)")
                    await asyncio.sleep(self.concurrent_config.batch_delay)
        
        # Display final evaluation statistics
        print(f"\n🏁 Concurrent evaluation completion statistics:")
        print(f"  Total evaluations: {total_processed}")
        print(f"  Successful evaluations: {total_correct}")
        print(f"  Failed evaluations: {total_processed - total_correct}")
        print(f"  Total retries: {self.concurrent_stats['total_retries']}")
        
        final_accuracy = (total_correct / max(total_processed, 1)) * 100
        print(f"  🎯 Final evaluation accuracy: {final_accuracy:.1f}%")
        
        return results


class LongMemEvalSEvaluator:
    """LongMemEval-S Evaluator (unified interface) - supports concurrent evaluation"""
    
    def __init__(
        self, 
        use_cuda: bool = True,
        verbose: bool = False,
        enable_traditional: bool = False,
        traditional_only: bool = False,
        eval_model: Optional[str] = None,
        concurrent_config: Optional[ConcurrentEvalConfig] = None
    ):
        self.use_cuda = use_cuda
        self.verbose = verbose
        self.enable_traditional = enable_traditional
        self.traditional_only = traditional_only
        self.concurrent_config = concurrent_config or ConcurrentEvalConfig()
        
        # Initialize traditional scorer (if needed) - supports batch processing
        if enable_traditional or traditional_only:
            self.scorer = LongMemEvalSScorer(use_cuda=use_cuda, verbose=verbose, batch_size=32)
        else:
            self.scorer = None
        
        # Initialize LongMemEval native evaluator (enabled by default, uses TiMem LLM manager, supports concurrent)
        if not traditional_only and longmemeval_eval_available:
            self.native_evaluator = LongMemEvalNativeEvaluator(
                eval_model=eval_model,
                verbose=verbose,
                concurrent_config=concurrent_config
            )
        else:
            self.native_evaluator = None
            if not traditional_only:
                print("⚠️ LongMemEval native evaluation not available, will use traditional metrics only")
    
    async def evaluate_answers(self, answers_data: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate answer data"""
        print(f"\n{'='*80}")
        print(f"📊 Starting evaluation")
        print(f"{'='*80}")
        
        qa_results = answers_data.get("qa_results", [])
        
        if not qa_results:
            print("❌ No QA result data found")
            return {}
        
        print(f"Total questions: {len(qa_results)}")
        
        # Determine evaluation mode
        if self.traditional_only:
            eval_mode = "Traditional metrics only"
        elif self.enable_traditional and self.native_evaluator:
            eval_mode = "LongMemEval native + traditional metrics"
        elif self.native_evaluator:
            eval_mode = "LongMemEval native evaluation"
        else:
            eval_mode = "Traditional metrics"
        
        print(f"Evaluation mode: {eval_mode}")
        
        # Filter successful results
        valid_results = [r for r in qa_results if r.get("success")]
        print(f"Valid results: {len(valid_results)}")
        
        if not valid_results:
            print("❌ No valid evaluation results")
            return {}
        
        # Load question types from question file (as a fallback)
        question_types_map = self._load_question_types()
        
        # 1. LongMemEval native evaluation (priority)
        native_scores = {}
        native_by_type = {}
        eval_results = []  # Save LLM evaluation results
        if self.native_evaluator and not self.traditional_only:
            print(f"\n{'─'*80}")
            print(f"🎯 LongMemEval native evaluation")
            print(f"{'─'*80}")
            
            # Prepare evaluation data
            qa_pairs = []
            for result in valid_results:
                # Prioritize using question type from answer file, read from question file if not available (backward compatible)
                question_type = result.get("question_type")
                if not question_type or question_type == "unknown":
                    user_id = result.get("user_id", "")
                    question_idx = result.get("question_idx", 1)
                    question_type = question_types_map.get((user_id, question_idx), "unknown")
                
                # Check if it's a refusal to answer question (via user_id)
                is_abstention = "_abs" in str(result.get("user_id", ""))
                
                qa_pairs.append({
                    "question": result.get("question", ""),
                    "answer": result.get("answer", ""),
                    "prediction": result.get("prediction", ""),
                    "question_type": question_type,
                    "is_abstention": is_abstention
                })
            
            # Batch evaluation (async call)
            eval_results = await self.native_evaluator.evaluate_batch(qa_pairs, show_progress=True)
            
            # Aggregate results
            correct_count = sum(1 for r in eval_results if r.get("success") and r.get("is_correct"))
            total_count = sum(1 for r in eval_results if r.get("success"))
            
            if total_count > 0:
                accuracy = correct_count / total_count
                
                # Aggregate by question type
                type_accuracy = defaultdict(lambda: {"correct": 0, "total": 0})
                for qa, eval_res in zip(qa_pairs, eval_results):
                    if eval_res.get("success"):
                        qtype = qa.get("question_type", "unknown")
                        type_accuracy[qtype]["total"] += 1
                        if eval_res.get("is_correct"):
                            type_accuracy[qtype]["correct"] += 1
                
                # Calculate accuracy for each type
                native_by_type = {
                    qtype: {
                        "accuracy": stats["correct"] / stats["total"] if stats["total"] > 0 else 0.0,
                        "correct": stats["correct"],
                        "total": stats["total"]
                    }
                    for qtype, stats in type_accuracy.items()
                }
                
                # Calculate task-averaged accuracy (longmemeval standard)
                task_accuracies = [stats["accuracy"] for stats in native_by_type.values()]
                task_avg_accuracy = np.mean(task_accuracies) if task_accuracies else 0.0
                
                native_scores = {
                    "overall_accuracy": {
                        "value": accuracy,
                        "correct": correct_count,
                        "total": total_count
                    },
                    "task_averaged_accuracy": {
                        "value": task_avg_accuracy,
                        "task_count": len(task_accuracies)
                    }
                }
                
                print(f"\n✅ LongMemEval native evaluation results:")
                print(f"  Overall Accuracy: {accuracy:.4f} ({correct_count}/{total_count})")
                print(f"  Task-Averaged Accuracy: {task_avg_accuracy:.4f}")
                print(f"\n  By task type:")
                for qtype, stats in native_by_type.items():
                    print(f"    {qtype}: {stats['accuracy']:.4f} ({stats['correct']}/{stats['total']})")
        
        # 2. Traditional metrics evaluation (optional) - using batch processing optimization
        traditional_scores = {}
        traditional_scores_per_question = []  # Save traditional metrics scores for each question
        if self.enable_traditional and self.scorer:
            print(f"\n{'─'*80}")
            print(f"📈 Computing traditional evaluation metrics (batch processing mode)")
            print(f"{'─'*80}")
            
            # Prepare batch evaluation data
            print(f"📋 Preparing batch evaluation data...")
            all_predictions = []
            all_references = []
            
            for result in valid_results:
                prediction = result.get("prediction", "")
                reference = result.get("answer", "")
                
                # Ensure string type
                prediction_str = str(prediction) if prediction is not None else ""
                reference_str = str(reference) if reference is not None else ""
                
                all_predictions.append(prediction_str)
                all_references.append(reference_str)
            
            print(f"✅ Batch data preparation complete: {len(all_predictions)} QA pairs")
            
            # Batch processing (using same batch size as timem_qa_evaluation.py)
            batch_size = self.scorer.batch_size
            total_batches = (len(all_predictions) + batch_size - 1) // batch_size
            
            all_scores = defaultdict(list)
            
            print(f"🚀 Starting batch evaluation, batch size: {batch_size}, using {'CUDA' if self.use_cuda else 'CPU'}...")
            
            with tqdm(total=len(all_predictions), desc="📊 Traditional metrics batch evaluation", unit="qa",
                     bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
                     ncols=120, colour='green') as pbar:
                
                for batch_idx in range(total_batches):
                    batch_start = batch_idx * batch_size
                    batch_end = min(batch_start + batch_size, len(all_predictions))
                    
                    if self.verbose:
                        print(f"\n📦 Processing batch {batch_idx + 1}/{total_batches} (QA {batch_start+1}-{batch_end})")
                    
                    # Batch evaluation
                    batch_scores = self.scorer.score_qa_batch(
                        all_predictions[batch_start:batch_end],
                        all_references[batch_start:batch_end]
                    )
                    
                    # Collect scores (both aggregate statistics and per-question scores)
                    for scores in batch_scores:
                        traditional_scores_per_question.append(scores)
                        for metric, score in scores.items():
                            all_scores[metric].append(score)
                    
                    pbar.update(batch_end - batch_start)
            
            # Calculate averages
            traditional_scores = {
                metric: {
                    "mean": np.mean(scores) if scores else 0.0,
                    "std": np.std(scores) if scores else 0.0,
                    "min": np.min(scores) if scores else 0.0,
                    "max": np.max(scores) if scores else 0.0,
                    "count": len(scores)
                }
                for metric, scores in all_scores.items()
            }
            
            print(f"\n✅ Batch evaluation complete! Traditional metrics results:")
            for metric, stats in traditional_scores.items():
                print(f"  {metric:15s}: {stats['mean']:.4f} (±{stats['std']:.4f})")
        
        # 3. Merge LLM evaluation results and traditional metrics into detailed_results
        enhanced_results = []
        for idx, result in enumerate(valid_results):
            enhanced_result = result.copy()
            
            # Prioritize using question type from answer file, read from question file if not available (backward compatible)
            question_type = result.get("question_type")
            if not question_type or question_type == "unknown":
                user_id = result.get("user_id", "")
                question_idx = result.get("question_idx", 1)
                question_type = question_types_map.get((user_id, question_idx), "unknown")
            enhanced_result["question_type"] = question_type
            
            # Add LLM evaluation results (if available)
            if eval_results and idx < len(eval_results):
                eval_res = eval_results[idx]
                # Fix field name: eval_response not evaluation/response
                eval_response_text = eval_res.get("eval_response", "N/A")
                enhanced_result["llm_evaluation"] = eval_response_text
                enhanced_result["is_correct"] = eval_res.get("is_correct", False)
                enhanced_result["eval_response"] = eval_response_text
            
            # Add traditional metrics scores (if available)
            if traditional_scores_per_question and idx < len(traditional_scores_per_question):
                trad_scores = traditional_scores_per_question[idx]
                enhanced_result["traditional_metrics"] = trad_scores
            
            enhanced_results.append(enhanced_result)
        
        # 4. Calculate traditional metrics statistics by type
        traditional_scores_by_type = {}
        if traditional_scores_per_question:
            type_groups = defaultdict(lambda: defaultdict(list))
            for idx, result in enumerate(enhanced_results):
                qtype = result.get("question_type", "unknown")
                if idx < len(traditional_scores_per_question):
                    trad_scores = traditional_scores_per_question[idx]
                    for metric, score in trad_scores.items():
                        type_groups[qtype][metric].append(score)
            
            # Calculate statistics for each type
            traditional_scores_by_type = {
                qtype: {
                    metric: {
                        "mean": np.mean(scores) if scores else 0.0,
                        "std": np.std(scores) if scores else 0.0,
                        "count": len(scores)
                    }
                    for metric, scores in metrics.items()
                }
                for qtype, metrics in type_groups.items()
            }
        
        # 5. Build evaluation results
        evaluation_result = {
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "total_questions": len(qa_results),
                "valid_questions": len(valid_results),
                "evaluation_mode": eval_mode,
                "source_data": answers_data.get("metadata", {})
            },
            "longmemeval_native_scores": native_scores,
            "longmemeval_by_type": native_by_type,
            "traditional_scores": traditional_scores,
            "traditional_scores_by_type": traditional_scores_by_type,
            "detailed_results": enhanced_results
        }
        
        return evaluation_result
    
    def _load_question_types(self) -> Dict[tuple, str]:
        """
        Load question type mapping from question files
        Returns {(user_id, question_idx): question_type} dictionary
        """
        question_types_map = {}
        questions_dir = Path("data/longmemeval_s_split/questions_by_user")
        
        if not questions_dir.exists():
            print(f"⚠️ Warning: Question directory not found: {questions_dir}")
            return question_types_map
        
        try:
            for json_file in questions_dir.glob("user_*_questions.json"):
                # Extract user_id from filename
                filename = json_file.stem  # e.g., "user_001be529_questions"
                parts = filename.split('_')
                if len(parts) >= 2:
                    user_id = f"user_{parts[1]}"
                    if len(parts) > 2 and parts[2] != "questions":
                        # Handle user_xxx_abs_questions case
                        user_id = f"user_{parts[1]}_{parts[2]}"
                else:
                    continue
                
                # Read question file
                with open(json_file, 'r', encoding='utf-8') as f:
                    questions_data = json.load(f)
                
                # questions_data is a list
                for question_item in questions_data:
                    if isinstance(question_item, dict):
                        question_idx = question_item.get("question_index", 1)
                        question_type = question_item.get("question_type", "unknown")
                        question_types_map[(user_id, question_idx)] = question_type
        except Exception as e:
            print(f"⚠️ Error loading question types: {e}")
        
        return question_types_map
    
    def _calculate_type_statistics(self, results: List[Dict]) -> Dict[str, Any]:
        """Calculate statistics by question type"""
        type_groups = defaultdict(list)
        
        for result in results:
            # Extract question type from user_id (assuming in metadata)
            # longmemeval_s question types need to be obtained from original data
            question_type = result.get("question_type", "unknown")
            type_groups[question_type].append(result)
        
        type_stats = {}
        for qtype, group_results in type_groups.items():
            type_stats[qtype] = {
                "count": len(group_results),
                "success_rate": sum(1 for r in group_results if r.get("success")) / len(group_results)
            }
        
        return type_stats
    
    def generate_score_table(self, evaluation_result: Dict[str, Any], output_file: str):
        """Generate detailed score table file (CSV format)"""
        print(f"\n📊 Generating detailed score table...")
        
        try:
            from pathlib import Path
            
            # Create CSV format table
            csv_content = []
            
            # Headers
            headers = [
                "User_ID", "Question_Index", "Question_Type", "Question", 
                "Standard_Answer", "Prediction", "Confidence"
            ]
            
            # Add LongMemEval native evaluation columns
            headers.extend(["LLM_Evaluation", "Is_Correct", "Eval_Response"])
            
            # Add traditional metrics columns
            if evaluation_result.get("traditional_scores"):
                headers.extend([
                    "F1", "BLEU-1", "BLEU-2", "Rouge-L", 
                    "METEOR", "BERTScore-F1", "Exact_Match"
                ])
            
            # Add retrieval metadata columns
            headers.extend([
                "Memories_Count", "Retrieval_Strategy", 
                "Query_Category", "Question_Date"
            ])
            
            csv_content.append(",".join(headers))
            
            # Data rows
            detailed_results = evaluation_result.get("detailed_results", [])
            for result in detailed_results:
                # Handle fields containing commas
                question = str(result.get('question', '')).replace('"', '""')
                answer = str(result.get('answer', '')).replace('"', '""')
                prediction = str(result.get('prediction', '')).replace('"', '""')
                eval_response = str(result.get('eval_response', 'N/A')).replace('"', '""')
                
                # Wrap fields containing commas with double quotes
                question = f'"{question}"' if ',' in question else question
                answer = f'"{answer}"' if ',' in answer else answer
                prediction = f'"{prediction}"' if ',' in prediction else prediction
                eval_response = f'"{eval_response}"' if ',' in eval_response else eval_response
                
                # Build data row
                row = [
                    str(result.get('user_id', 'N/A')),
                    str(result.get('question_idx', 'N/A')),
                    str(result.get('question_type', 'unknown')),
                    question,
                    answer,
                    prediction,
                    str(result.get('confidence', 'N/A'))
                ]
                
                # Add LongMemEval evaluation results
                row.extend([
                    str(result.get('llm_evaluation', 'N/A')),
                    str(result.get('is_correct', 'N/A')),
                    eval_response
                ])
                
                # Add traditional metrics values (read from traditional_metrics field)
                if evaluation_result.get("traditional_scores"):
                    trad_metrics = result.get('traditional_metrics', {})
                    row.extend([
                        str(round(trad_metrics.get('f1', 0), 6)) if trad_metrics.get('f1') is not None else 'N/A',
                        str(round(trad_metrics.get('bleu_1', 0), 6)) if trad_metrics.get('bleu_1') is not None else 'N/A',
                        str(round(trad_metrics.get('bleu_2', 0), 6)) if trad_metrics.get('bleu_2') is not None else 'N/A',
                        str(round(trad_metrics.get('rouge_l', 0), 6)) if trad_metrics.get('rouge_l') is not None else 'N/A',
                        str(round(trad_metrics.get('meteor', 0), 6)) if trad_metrics.get('meteor') is not None else 'N/A',
                        str(round(trad_metrics.get('bert_score_f1', 0), 6)) if trad_metrics.get('bert_score_f1') is not None else 'N/A',
                        str(round(trad_metrics.get('exact_match', 0), 6)) if trad_metrics.get('exact_match') is not None else 'N/A'
                    ])
                
                # Add retrieval metadata
                retrieval_metadata = result.get('retrieval_metadata', {})
                row.extend([
                    str(result.get('memories_count', 'N/A')),
                    str(retrieval_metadata.get('retrieval_strategy', 'N/A')),
                    str(retrieval_metadata.get('query_category', 'N/A')),
                    str(result.get('question_date', 'N/A'))
                ])
                
                csv_content.append(",".join(row))
            
            # Generate CSV filename
            output_path = Path(output_file)
            csv_file = str(output_path.with_name(output_path.stem + '_scores_table').with_suffix('.csv'))
            
            with open(csv_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(csv_content))
            
            print(f"✅ Detailed score table saved: {csv_file}")
            
            # Generate summary statistics table
            self.generate_summary_table(evaluation_result, output_file)
            
        except Exception as e:
            print(f"❌ Failed to generate score table: {e}")
            import traceback
            traceback.print_exc()
    
    def generate_summary_table(self, evaluation_result: Dict[str, Any], output_file: str):
        """Generate summary statistics table (CSV format)"""
        try:
            from pathlib import Path
            
            # Create summary statistics CSV
            summary_content = []
            
            # Headers
            summary_headers = ["Question_Type", "Question_Count"]
            
            # Add LongMemEval metrics columns
            summary_headers.extend([
                "LLM_Accuracy", "LLM_Correct_Count", "LLM_Total_Count"
            ])
            
            # Add traditional metrics columns (if available)
            if evaluation_result.get("traditional_scores"):
                summary_headers.extend([
                    "F1_Mean", "BLEU1_Mean", "BLEU2_Mean", "RougeL_Mean",
                    "METEOR_Mean", "BERTScore_Mean", "ExactMatch_Mean"
                ])
            
            summary_content.append(",".join(summary_headers))
            
            # Overall statistics row
            metadata = evaluation_result.get("metadata", {})
            native_scores = evaluation_result.get("longmemeval_native_scores", {})
            
            overall_row = [
                "Overall",
                str(metadata.get('valid_questions', 0))
            ]
            
            overall_acc = native_scores.get("overall_accuracy", {})
            overall_row.extend([
                str(round(overall_acc.get('value', 0), 4)),
                str(overall_acc.get('correct', 0)),
                str(overall_acc.get('total', 0))
            ])
            
            # Add traditional metrics averages (if available)
            traditional_scores = evaluation_result.get("traditional_scores", {})
            if traditional_scores:
                overall_row.extend([
                    str(round(traditional_scores.get('f1', {}).get('mean', 0), 4)),
                    str(round(traditional_scores.get('bleu_1', {}).get('mean', 0), 4)),
                    str(round(traditional_scores.get('bleu_2', {}).get('mean', 0), 4)),
                    str(round(traditional_scores.get('rouge_l', {}).get('mean', 0), 4)),
                    str(round(traditional_scores.get('meteor', {}).get('mean', 0), 4)),
                    str(round(traditional_scores.get('bert_score_f1', {}).get('mean', 0), 4)),
                    str(round(traditional_scores.get('exact_match', {}).get('mean', 0), 4))
                ])
            
            summary_content.append(",".join(overall_row))
            
            # Statistics rows grouped by task type
            native_by_type = evaluation_result.get("longmemeval_by_type", {})
            traditional_by_type = evaluation_result.get("traditional_scores_by_type", {})
            
            for qtype, stats in native_by_type.items():
                type_row = [
                    qtype,
                    str(stats.get('total', 0))
                ]
                
                type_row.extend([
                    str(round(stats.get('accuracy', 0), 4)),
                    str(stats.get('correct', 0)),
                    str(stats['total'])
                ])
                
                # Traditional metrics (read from traditional_scores_by_type)
                if traditional_scores and traditional_by_type:
                    type_trad = traditional_by_type.get(qtype, {})
                    type_row.extend([
                        str(round(type_trad.get('f1', {}).get('mean', 0), 4)),
                        str(round(type_trad.get('bleu_1', {}).get('mean', 0), 4)),
                        str(round(type_trad.get('bleu_2', {}).get('mean', 0), 4)),
                        str(round(type_trad.get('rouge_l', {}).get('mean', 0), 4)),
                        str(round(type_trad.get('meteor', {}).get('mean', 0), 4)),
                        str(round(type_trad.get('bert_score_f1', {}).get('mean', 0), 4)),
                        str(round(type_trad.get('exact_match', {}).get('mean', 0), 4))
                    ])
                
                summary_content.append(",".join(type_row))
            
            # Generate summary statistics filename
            output_path = Path(output_file)
            summary_file = str(output_path.with_name(output_path.stem + '_summary_table').with_suffix('.csv'))
            
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(summary_content))
            
            print(f"✅ Summary statistics table saved: {summary_file}")
            
        except Exception as e:
            print(f"❌ Failed to generate summary statistics table: {e}")
            import traceback
            traceback.print_exc()
    
    def print_summary(self, evaluation_result: Dict[str, Any]):
        """Print evaluation summary"""
        print(f"\n{'='*80}")
        print(f"📊 Evaluation Summary")
        print(f"{'='*80}")
        
        metadata = evaluation_result.get("metadata", {})
        print(f"Total questions: {metadata.get('total_questions', 0)}")
        print(f"Valid questions: {metadata.get('valid_questions', 0)}")
        print(f"Evaluation mode: {metadata.get('evaluation_mode', 'unknown')}")
        
        # LongMemEval native evaluation results
        native_scores = evaluation_result.get("longmemeval_native_scores", {})
        if native_scores:
            print(f"\n🎯 LongMemEval Native Evaluation:")
            
            overall_acc = native_scores.get("overall_accuracy", {})
            if overall_acc:
                print(f"  Overall Accuracy: {overall_acc.get('value', 0):.4f} ({overall_acc.get('correct', 0)}/{overall_acc.get('total', 0)})")
            
            task_avg_acc = native_scores.get("task_averaged_accuracy", {})
            if task_avg_acc:
                print(f"  Task-Averaged Accuracy: {task_avg_acc.get('value', 0):.4f} (across {task_avg_acc.get('task_count', 0)} tasks)")
        
        # By task type
        native_by_type = evaluation_result.get("longmemeval_by_type", {})
        if native_by_type:
            print(f"\n  By task type:")
            for qtype, stats in native_by_type.items():
                print(f"    {qtype:30s}: {stats['accuracy']:.4f} ({stats['correct']}/{stats['total']})")
        
        # Traditional metrics
        traditional_scores = evaluation_result.get("traditional_scores", {})
        if traditional_scores:
            print(f"\n📈 Traditional evaluation metrics:")
            for metric, stats in traditional_scores.items():
                if isinstance(stats, dict) and "mean" in stats:
                    print(f"  {metric:20s}: {stats['mean']:.4f} (±{stats['std']:.4f})")


def find_latest_answers_file() -> Optional[Path]:
    """
    Automatically find the latest answer file from the logs/ directory
    
    Returns:
        Path to the latest answer file, or None if not found
    """
    # Search directories
    search_dirs = [
        Path("logs/longmemeval_s"),
        Path("logs"),
    ]
    
    latest_file = None
    latest_time = 0
    
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        
        # Find all answers_*.json files (exclude scores and detailed_memories files)
        for file_path in search_dir.glob("answers_*.json"):
            if "_scores_" in file_path.name or "_detailed_memories" in file_path.name:
                continue
            
            # Get file modification time
            mtime = file_path.stat().st_mtime
            if mtime > latest_time:
                latest_time = mtime
                latest_file = file_path
    
    return latest_file


async def main():
    """Main function"""
    # Set dataset environment variable (ensure using longmemeval_s config)
    os.environ["TIMEM_DATASET_PROFILE"] = "longmemeval_s"
    print(f"✅ Dataset configuration: longmemeval_s")
    
    # Parse arguments
    parser = argparse.ArgumentParser(
        description="LongMemEval-S Answer Evaluation Script (using longmemeval native evaluation method)"
    )
    parser.add_argument("--input", type=str, default=None,
                       help="Answer data file path (default auto find latest file in logs/)")
    parser.add_argument("--output", type=str, default=None,
                       help="Evaluation result output path (default auto generate)")
    
    # Evaluation mode options
    parser.add_argument("--traditional-only", action="store_true",
                       help="Use only traditional metrics (F1, BLEU, etc.), no LLM evaluation")
    parser.add_argument("--disable-traditional", action="store_true",
                       help="Disable traditional metrics (default enable LongMemEval native + traditional)")
    
    # LLM evaluation configuration
    parser.add_argument("--eval-model", type=str, default=None,
                       help="Evaluation LLM model (default read from global config, usually gpt-4o-mini)")
    
    # Concurrent configuration options
    parser.add_argument("--max-concurrent", type=int, default=20,
                       help="Maximum concurrent requests (default 20)")
    parser.add_argument("--batch-delay", type=float, default=0.5,
                       help="Delay between batches in seconds (default 0.5s)")
    parser.add_argument("--max-retries", type=int, default=20,
                       help="Maximum number of retries (default 20)")
    parser.add_argument("--timeout", type=float, default=30.0,
                       help="Single request timeout in seconds (default 30s)")
    
    # Other options
    parser.add_argument("--no-cuda", action="store_true",
                       help="Disable CUDA (only affects BERTScore in traditional metrics)")
    parser.add_argument("--verbose", action="store_true",
                       help="Verbose output")
    args = parser.parse_args()
    
    print("="*80)
    print("📊 LongMemEval-S Answer Evaluation Script")
    print("="*80)
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Determine input file
    if args.input:
        input_file = Path(args.input)
    else:
        print(f"\n🔍 Auto finding latest answer file...")
        input_file = find_latest_answers_file()
        if not input_file:
            print(f"❌ Answer file not found")
            print(f"   Please place answers_*.json file in logs/ or logs/longmemeval_s/ directory")
            print(f"   Or use --input parameter to specify file path")
            return 1
        print(f"✅ Found latest file: {input_file}")
    
    # Check input file
    if not input_file.exists():
        print(f"❌ Input file not found: {input_file}")
        return 1
    
    print(f"\nInput file: {input_file}")
    print(f"File size: {input_file.stat().st_size / 1024:.2f} KB")
    print(f"Modified time: {datetime.fromtimestamp(input_file.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # 1. Load answer data
        print(f"\n{'='*80}")
        print(f"📂 Loading answer data")
        print(f"{'='*80}")
        
        with open(input_file, 'r', encoding='utf-8') as f:
            answers_data = json.load(f)
        
        qa_results = answers_data.get('qa_results', [])
        
        # Count users
        user_ids = set(result.get('user_id', 'unknown') for result in qa_results)
        
        print(f"✅ Successfully loaded answer data")
        print(f"User count: {len(user_ids)}")
        print(f"Question count: {len(qa_results)}")
        
        # 2. Create concurrent configuration
        concurrent_config = ConcurrentEvalConfig(
            max_concurrent_requests=args.max_concurrent,
            batch_delay=args.batch_delay,
            max_retries=args.max_retries,
            timeout=args.timeout
        )
        
        print(f"\n{'='*80}")
        print(f"🔧 Concurrent Configuration")
        print(f"{'='*80}")
        print(f"Max concurrent: {concurrent_config.max_concurrent_requests}")
        print(f"Batch delay: {concurrent_config.batch_delay}s")
        print(f"Max retries: {concurrent_config.max_retries}")
        print(f"Retry tiers: {' → '.join([f'{d}s' for d in concurrent_config.retry_delays])}")
        print(f"Single request timeout: {concurrent_config.timeout}s")
        
        # 3. Initialize evaluator
        # Enable traditional metrics by default (unless user explicitly disables or chooses traditional only)
        enable_traditional = not args.disable_traditional and not args.traditional_only
        
        evaluator = LongMemEvalSEvaluator(
            use_cuda=not args.no_cuda,
            verbose=args.verbose,
            enable_traditional=enable_traditional,
            traditional_only=args.traditional_only,
            eval_model=args.eval_model,
            concurrent_config=concurrent_config
        )
        
        # 4. Execute evaluation (using async context manager)
        if evaluator.native_evaluator:
            async with evaluator.native_evaluator:
                evaluation_result = await evaluator.evaluate_answers(answers_data)
        else:
            evaluation_result = await evaluator.evaluate_answers(answers_data)
        
        # 5. Save results
        if args.output:
            output_file = args.output
        else:
            # Generate output filename based on input file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = str(input_file.parent / f"{input_file.stem}_scores_{timestamp}.json")
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(evaluation_result, f, ensure_ascii=False, indent=2)
        
        print(f"\n{'='*80}")
        print(f"💾 Evaluation results saved")
        print(f"{'='*80}")
        print(f"File path: {output_file}")
        
        # 6. Generate detailed score table and summary statistics table (refer to timem_qa_evaluation.py)
        evaluator.generate_score_table(evaluation_result, output_file)
        
        # 7. Print summary
        evaluator.print_summary(evaluation_result)
        
        # 8. Print concurrent statistics
        if evaluator.native_evaluator and not args.traditional_only:
            print(f"\n{'='*80}")
            print(f"🚀 Concurrent Evaluation Statistics")
            print(f"{'='*80}")
            stats = evaluator.native_evaluator.concurrent_stats
            print(f"Total evaluations: {stats['total_evaluations']}")
            print(f"Successful evaluations: {stats['successful_evaluations']}")
            print(f"Failed evaluations: {stats['failed_evaluations']}")
            print(f"Total retries: {stats['total_retries']}")
            if stats['total_evaluations'] > 0:
                success_rate = (stats['successful_evaluations'] / stats['total_evaluations']) * 100
                print(f"Success rate: {success_rate:.1f}%")
        
        # 9. Display all generated files
        print(f"\n{'='*80}")
        print(f"📁 Generated Files")
        print(f"{'='*80}")
        output_path = Path(output_file)
        print(f"📄 Evaluation Result JSON: {output_file}")
        print(f"📊 Detailed Score Table: {output_path.with_name(output_path.stem + '_scores_table').with_suffix('.csv')}")
        print(f"📈 Summary Statistics Table: {output_path.with_name(output_path.stem + '_summary_table').with_suffix('.csv')}")
        print(f"{'='*80}")
        
    except Exception as e:
        print(f"\n❌ Evaluation failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        # Clean up LLM resources
        try:
            from llm.core.async_http_pool import close_global_http_pool
            from llm.http_client_manager import close_global_http_client
            
            # Close HTTP connection pool
            await close_global_http_pool()
            await close_global_http_client()
            
            print("\n✅ Resource cleanup complete")
        except Exception as cleanup_error:
            print(f"\n⚠️ Resource cleanup warning: {cleanup_error}")
    
    print(f"\nEnd time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code if exit_code else 0)
