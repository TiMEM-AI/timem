"""
Bottom-up retriever base class

Provides shared L1 retrieval logic, session scoring, temporal association queries and other core functionality.
All refactored retrievers (Simple/Hybrid/Complex) will inherit from this base class.

Architecture design principles:
1. Single Responsibility: Focus on bottom-up retrieval logic
2. Open-Closed: Open for extension, closed for modification
3. Liskov Substitution: Subclasses can completely replace the base class
4. Interface Segregation: Provide clear abstract interfaces
5. Dependency Inversion: Depend on abstractions rather than concrete implementations
"""

import asyncio
import math
import re
import time
from typing import Dict, List, Any, Optional, Tuple
from abc import ABC, abstractmethod
from datetime import datetime
from collections import Counter

from timem.workflows.retrieval_state import RetrievalState, RetrievalStrategy, RetrievalStateValidator
from timem.workflows.retrieval_utils import analyze_l1_memories_for_bottom_up_retrieval
from storage.memory_storage_manager import get_memory_storage_manager_async
from storage.postgres_store import PostgreSQLStore
from timem.utils.config_manager import get_storage_config
from timem.utils.retrieval_config_manager import get_retrieval_config
from timem.utils.logging import get_logger
from sqlalchemy.sql import text

logger = get_logger(__name__)


class BottomUpRetrieverBase(ABC):
    """
    Bottom-up retriever base class
    
    Provides common functionality for all refactored retrievers:
    1. L1 hybrid retrieval (BM25 keywords + Qdrant semantic search)
    2. Session scoring algorithm
    3. Temporal association memory query
    4. Unified state management and error handling
    """
    
    def __init__(self, 
                 storage_manager: Optional[Any] = None,
                 state_validator: Optional[RetrievalStateValidator] = None,
                 strategy_config: Optional[Dict[str, Any]] = None,
                 **kwargs):
        """
        Initialize bottom-up retriever base class
        
        Args:
            storage_manager: Storage manager, auto-fetched if None
            state_validator: State validator, creates new instance if None
            strategy_config: Strategy configuration for subclasses
            **kwargs: Other keyword arguments
        """
        self.storage_manager = storage_manager
        self.state_validator = state_validator or RetrievalStateValidator()
        self.logger = get_logger(self.__class__.__name__)
        
        # Load retrieval parameters from config file
        self.retrieval_config = get_retrieval_config()
        
        # Weighted fusion weights
        semantic_config = self.retrieval_config.get('retrieval', {}).get('semantic', {})
        keyword_config = self.retrieval_config.get('retrieval', {}).get('keyword', {})
        self.semantic_weight = semantic_config.get('weight', 0.9)
        self.keyword_weight = keyword_config.get('weight', 0.1)
        
        # Cross-layer retrieval mode (pure RAG mode: no layer distinction, mixed retrieval of all memories)
        self.cross_layer_retrieval = self.retrieval_config.get('retrieval', {}).get('cross_layer_retrieval', False)
        
        self.logger.info(f"Initializing {self.__class__.__name__}, "
                        f"semantic_weight={self.semantic_weight}, keyword_weight={self.keyword_weight}, "
                        f"cross_layer_retrieval={self.cross_layer_retrieval}")
    
    # ==================== Abstract methods: subclasses must implement ====================
    
    @abstractmethod
    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run retriever (LangGraph node standard interface)
        
        Args:
            state: Workflow state dictionary
            
        Returns:
            Updated state dictionary
        """
        pass
    
    @abstractmethod  
    def get_retriever_name(self) -> str:
        """Get retriever name for logging and performance statistics"""
        pass
    
    # ==================== Shared core functionality: L1 hybrid retrieval ====================
    
    def get_top_k_from_config(self, strategy_name: str, use_coarse_ranking: bool = False) -> int:
        """
        Get top_k parameter from config
        
        Args:
            strategy_name: Strategy name, e.g., 'simple', 'hybrid', 'complex'
            use_coarse_ranking: Whether to use coarse ranking count (layer_limits) or fine ranking count (final_limits)
            
        Returns:
            top_k parameter value
        """
        strategy_config = self.retrieval_config.get('retrieval_strategies', {}).get(strategy_name, {})
        
        if use_coarse_ranking:
            # Use coarse ranking count (layer_limits)
            layer_limits = strategy_config.get('layer_limits', {})
            return layer_limits.get('L1', 40)  # Default 40, can be overridden by config
        else:
            # Use fine ranking count (final_limits)
            final_limits = strategy_config.get('final_limits', {})
            return final_limits.get('L1', 20)  # Default 20, can be overridden by config

    async def perform_l1_retrieval(self, state: Dict[str, Any], 
                                 llm_keywords: List[str], 
                                 top_k: int = None,
                                 coarse_ranking: bool = True) -> List[Dict[str, Any]]:
        """
        Execute L1 hybrid retrieval - V2 correct logic
        
        Coarse ranking phase:
        1. Semantic search 40 + keyword search 40
        2. Deduplicate and merge to get 40-80 memories
        3. Supplement missing scores (semantic + keyword)
        4. Calculate weighted fusion score
        
        Fine ranking phase:
        5. Select top 20 based on weighted score
        6. Sort by temporal order
        
        Args:
            state: Retrieval state dictionary
            llm_keywords: List of keywords generated by LLM
            top_k: Number of final results to return, fetched from config if None
            coarse_ranking: Whether to perform coarse ranking first, default True
            
        Returns:
            L1 hybrid retrieval result list (final results after fine ranking)
        """
        strategy_name = state.get('retrieval_strategy', 'simple')
        
        # Get coarse and fine ranking counts
        coarse_top_k = self.get_top_k_from_config(strategy_name, use_coarse_ranking=True)
        if top_k is None:
            top_k = self.get_top_k_from_config(strategy_name, use_coarse_ranking=False)
        
        try:
            # Check if L1 expansion is needed (reflection mechanism)
            l1_multiplier = state.get("l1_expansion_multiplier", 1)
            expanded_coarse_top_k = coarse_top_k * l1_multiplier
            expanded_final_top_k = top_k * l1_multiplier
            
            reflection_info = f" (reflection expansion {l1_multiplier}x)" if l1_multiplier > 1 else ""
            self.logger.info(f"🔍 Starting L1 hybrid retrieval ({self.get_retriever_name()}){reflection_info}")
            
            start_time = time.time()
            
            # Convert state format
            retrieval_state = self._dict_to_state(state)
            
            if coarse_ranking:
                # V2 correct logic: coarse ranking phase
                self.logger.info(f"📊 Coarse ranking phase: semantic {expanded_coarse_top_k} + keyword {expanded_coarse_top_k}")
                
                # Execute two types of retrieval in parallel
                keyword_task = self._execute_bm25_search_with_limit(retrieval_state, llm_keywords, "L1", expanded_coarse_top_k)
                semantic_task = self._execute_semantic_search_with_limit(retrieval_state, "L1", expanded_coarse_top_k)
                
                keyword_results, semantic_results = await asyncio.gather(
                    keyword_task, semantic_task, return_exceptions=True
                )
                
                # Handle exceptions
                if isinstance(keyword_results, Exception):
                    self.logger.error(f"L1 BM25 keyword search failed: {keyword_results}")
                    keyword_results = []
                if isinstance(semantic_results, Exception):
                    self.logger.error(f"L1 Qdrant semantic search failed: {semantic_results}")
                    semantic_results = []
                
                # Deduplicate and merge: dedup based on memory_id
                coarse_results = await self._merge_and_deduplicate_results(
                    keyword_results, semantic_results, retrieval_state
                )
                
                actual_coarse_count = len(coarse_results)
                self.logger.info(f"🔄 Coarse ranking merge: keyword {len(keyword_results)} + semantic {len(semantic_results)} → deduped {actual_coarse_count}")
                
                # Fine ranking phase: select top N based on weighted score
                self.logger.info(f"✨ Fine ranking phase: select top {expanded_final_top_k} from {actual_coarse_count}")
                final_results = await self._fine_ranking_by_weighted_score(
                    coarse_results, expanded_final_top_k
                )
                
                # Save coarse ranking results for L2-L5 use
                state["l1_coarse_results"] = coarse_results
                
            else:
                # Direct fine ranking mode (backward compatible)
                self.logger.info(f"🔄 Direct fine ranking mode: {expanded_final_top_k}")
                
                # Execute BM25 keyword + Qdrant semantic search in parallel
                keyword_task = self._execute_bm25_search(retrieval_state, llm_keywords, "L1")
                semantic_task = self._execute_semantic_search(retrieval_state, "L1")
                
                keyword_results, semantic_results = await asyncio.gather(
                    keyword_task, semantic_task, return_exceptions=True
                )
                
                # Handle exceptions
                if isinstance(keyword_results, Exception):
                    self.logger.error(f"L1 BM25 keyword search failed: {keyword_results}")
                    keyword_results = []
                if isinstance(semantic_results, Exception):
                    self.logger.error(f"L1 Qdrant semantic search failed: {semantic_results}")
                    semantic_results = []
                
                # Weighted fusion
                fused_results = await self._weighted_fusion(
                    keyword_results, semantic_results, retrieval_state
                )
                
                final_results = fused_results[:expanded_final_top_k]
            
            execution_time = time.time() - start_time
            self.logger.info(f"✅ L1 hybrid retrieval completed: {len(final_results)} results, "
                           f"elapsed time {execution_time:.2f}s")
            
            return final_results
            
        except Exception as e:
            self.logger.error(f"L1 hybrid retrieval failed: {str(e)}")
            return []
    
    # ==================== Shared core functionality: Session scoring analysis ====================
    
    def analyze_l1_for_session(self, l1_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze L1 memories to determine best session and temporal information
        
        Args:
            l1_results: L1 retrieval result list
            
        Returns:
            Analysis result containing best session, temporal info, etc.
        """
        try:
            self.logger.info(f"🔄 Starting session analysis, L1 memory count: {len(l1_results)}")
            
            # Use utility module for analysis
            analysis_result = analyze_l1_memories_for_bottom_up_retrieval(l1_results)
            
            if analysis_result['best_session_id']:
                self.logger.info(f"🎯 Determined best session: {analysis_result['best_session_id']}, "
                               f"score: {analysis_result['best_session_score']:.3f}")
                
                # Output temporal information
                temporal = analysis_result['temporal_info']
                if temporal:
                    self.logger.info(f"📅 Temporal info: date={temporal.get('date')}, "
                                   f"week={temporal.get('week')}, month={temporal.get('month')}")
            else:
                self.logger.warning("No valid session found")
            
            return analysis_result
            
        except Exception as e:
            self.logger.error(f"Session analysis failed: {str(e)}")
            return {'best_session_id': None, 'temporal_info': {}}
    
    # ==================== Shared core functionality: Temporal association memory query ====================
    
    async def get_parent_memories_by_chain(self, l1_results: List[Dict[str, Any]], target_levels: List[str], 
                                           target_counts: Dict[str, int] = None, 
                                           state: Dict[str, Any] = None) -> Dict[str, List[Dict[str, Any]]]:
        """
        Bottom-up algorithm: extract parent memories from L1 fine-ranked results (supports skip-level config with cascading traversal)
        
        Core improvements:
        1. Support skip-level config (e.g., L1→L3) via complete chain (L1→L2→L3) cascading
        2. Strict deduplication control, ensuring collection count per level <= target_count
        3. Traverse all L1 to ensure no memories missed due to early termination
        4. Engineering fix: add retry mechanism to handle temporary failures like connection pool exhaustion
        
        Args:
            l1_results: L1 fine-ranked result list (20 items, sorted by relevance)
            target_levels: Target level list, e.g., ["L2"] or ["L3", "L4", "L5"]
            target_counts: Expected count per level, e.g., {"L2": 4, "L3": 2}
            state: Workflow state (for coarse ranking results for session scoring, optional)
            
        Returns:
            Dict[level, List[memories]]: Parent memory list per level
        """
        max_retries = 3
        retry_delays = [1.0, 2.0, 3.0]
        
        for retry_attempt in range(max_retries):
            try:
                return await self._execute_bottom_up_chain(l1_results, target_levels, target_counts, state)
            except Exception as e:
                error_msg = str(e)
                is_retriable = any(keyword in error_msg.lower() for keyword in [
                    "too many clients", "connection pool", "connection", "timeout", 
                    "database", "psycopg", "asyncpg"
                ])
                
                if is_retriable and retry_attempt < max_retries - 1:
                    delay = retry_delays[min(retry_attempt, len(retry_delays) - 1)]
                    self.logger.warning(
                        f"🔄 Bottom-up failed to get parent memories (retriable error), retry {retry_attempt + 1}, waiting {delay}s: {error_msg}"
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    # Non-retriable error or max retries reached
                    if retry_attempt < max_retries - 1:
                        self.logger.error(f"❌ Bottom-up failed (non-retriable error): {error_msg}")
                    else:
                        self.logger.error(f"❌ Bottom-up failed (retried {max_retries} times): {error_msg}")
                    raise  # Re-raise exception for caller to handle
        
        # Theoretically unreachable, but return empty result for safety
        return {level: [] for level in target_levels}
    
    async def _execute_bottom_up_chain(self, l1_results: List[Dict[str, Any]], target_levels: List[str], 
                                      target_counts: Dict[str, int] = None, 
                                      state: Dict[str, Any] = None) -> Dict[str, List[Dict[str, Any]]]:
        """
        Execute core logic of bottom-up chain traversal (internal method for retry)
        
        Args:
            Same as get_parent_memories_by_chain
            
        Returns:
            Dict[level, List[memories]]: Parent memory list per level
        """
        try:
            storage_manager = await self._get_storage_manager()
            
            # Connection pool health check and alert
            try:
                pool_status = await storage_manager.check_pool_health()
                if pool_status.get('available', False):
                    utilization = pool_status.get('utilization_percent', 0)
                    if utilization > 80:
                        self.logger.warning(f"⚠️ Connection pool utilization high: {utilization:.1f}%")
                    elif utilization > 90:
                        self.logger.error(f"❌ Connection pool near exhaustion: {utilization:.1f}%")
            except Exception as e:
                self.logger.debug(f"Connection pool health check failed: {e}")
            
            result_memories = {level: [] for level in target_levels}
            
            # Create independent dedup set for each level
            collected_ids_by_level = {level: set() for level in target_levels}
            
            # L2 special handling: dedup by session ID (not memory ID) to avoid collecting same L2 from multiple L1s in same session
            collected_l2_sessions = set() if "L2" in target_levels else None
            
            # Set default target counts
            if target_counts is None:
                strategy_name = getattr(self, 'strategy_name', 'simple')
                strategy_config = self.retrieval_config.get('retrieval_strategies', {}).get(strategy_name, {})
                final_limits = strategy_config.get('final_limits', {})
                target_counts = {level: final_limits.get(level, 1) for level in target_levels}
                self.logger.info(f"Using default target_counts: {target_counts}")
            else:
                self.logger.info(f"Using provided target_counts: {target_counts}")
            
            self.logger.info(f"🎯 Bottom-up algorithm started")
            self.logger.info(f"   Input: {len(l1_results)} L1 fine-ranked results")
            self.logger.info(f"   Target levels: {target_levels}")
            self.logger.info(f"   Target counts: {target_counts}")
            
            # Key fix: distinguish traversal path from collection levels
            # chain_levels: complete layer-by-layer traversal path (L2→L3→L4→L5)
            # target_levels: actual levels to collect (may skip levels, e.g., L2, L5)
            max_target_level_num = max([int(level[1]) for level in target_levels])
            chain_levels = [f"L{i}" for i in range(2, max_target_level_num + 1)]
            
            self.logger.info(f"   Traversal chain: {chain_levels} (complete path)")
            self.logger.info(f"   Collection levels: {target_levels} (config levels only)")
            
            # Core algorithm: traverse all L1 fine-ranked results
            processed_l1_count = 0
            for l1_idx, l1_memory in enumerate(l1_results, 1):
                # Check if all target levels are satisfied
                all_satisfied = all(
                    len(result_memories[level]) >= target_counts.get(level, 0) 
                    for level in target_levels
                )
                if all_satisfied:
                    self.logger.info(f"✅ All target levels satisfied, stopping at L1 #{l1_idx}")
                    break
                
                # Get L1 memory ID
                l1_id = l1_memory.get('id') or l1_memory.get('memory_id')
                if not l1_id:
                    self.logger.debug(f"L1#{l1_idx} has no valid ID, skipping")
                    continue
                
                processed_l1_count += 1
                self.logger.debug(f"🔗 Processing L1#{l1_idx}: {l1_id[:20]}...")
                
                # Key fix: execute complete chain traversal but only collect target_levels
                try:
                    # Traverse complete path
                    full_parent_chain = await storage_manager.get_parent_memories_chain(l1_id, chain_levels)
                    
                    if not full_parent_chain:
                        self.logger.debug(f"   No parent memory chain found")
                        continue
                    
                    # Filter: keep only levels in target_levels
                    parent_chain = {level: mem for level, mem in full_parent_chain.items() if level in target_levels}
                    
                    if not parent_chain:
                        self.logger.debug(f"   Traversed to {list(full_parent_chain.keys())}, but no collection needed for target_levels={target_levels}")
                        continue
                    
                    self.logger.debug(f"   Traversed to: {list(full_parent_chain.keys())} → Collecting: {list(parent_chain.keys())}")
                    
                except Exception as e:
                    self.logger.warning(f"   Chain traversal failed: {e}")
                    continue
                
                # Key fix: only collect levels specified in target_levels
                # parent_chain may contain L2/L3/L4/L5, but only save those in target_levels
                for level in target_levels:
                    # Check if this level was found in traversal chain
                    if level not in parent_chain:
                        self.logger.debug(f"   {level} level not in traversal chain, skipping")
                        continue
                    
                    # Check if this level is already full
                    current_count = len(result_memories[level])
                    target_count = target_counts.get(level, 0)
                    
                    if current_count >= target_count:
                        continue  # This level is full
                    
                    # Get parent memory from traversal chain (only target level)
                    parent_memory = parent_chain.get(level)
                    if not parent_memory:
                        self.logger.debug(f"   {level} level has no parent memory")
                        continue
                    
                    parent_id = parent_memory.get('id')
                    if not parent_id:
                        self.logger.debug(f"   {level} level parent memory has no ID")
                        continue
                    
                    # Key fix: L2 dedups by session, other levels by ID
                    if level == "L2":
                        # L2 is session-level memory, dedup by session_id
                        session_id = parent_memory.get('session_id')
                        if not session_id:
                            # If no session_id field, extract from title or other fields
                            session_id = self._extract_session_id_from_memory(parent_memory)
                        
                        if not session_id:
                            # Unable to extract session_id, use memory ID as fallback
                            session_id = parent_id
                            self.logger.debug(f"   L2 unable to extract session_id, using memory ID: {parent_id[:15]}...")
                        
                        if session_id in collected_l2_sessions:
                            self.logger.debug(f"   L2 session={session_id} already exists, skipping")
                            continue
                        
                        # Record this session as collected
                        collected_l2_sessions.add(session_id)
                    else:
                        # L3-L5 dedup by ID
                        if parent_id in collected_ids_by_level[level]:
                            self.logger.debug(f"   {level} ID={parent_id[:15]}... already exists, skipping")
                            continue
                    
                    # Collect this parent memory
                    parent_memory.update({
                        "retrieval_source": f"bottom_up_{level.lower()}",
                        "retrieval_strategy": "chain_traversal",
                        "chain_origin_l1_id": l1_id,
                        "chain_origin_l1_rank": l1_idx,
                        "level": level
                    })
                    
                    result_memories[level].append(parent_memory)
                    collected_ids_by_level[level].add(parent_id)
                    
                    new_count = len(result_memories[level])
                    self.logger.info(f"   ✅ Collected {level}: {parent_memory.get('title', 'untitled')[:40]}... "
                                   f"({new_count}/{target_count})")
            
            # Summarize collection results
            summary = []
            warnings = []
            for level in target_levels:
                collected = len(result_memories[level])
                target = target_counts.get(level, 0)
                summary.append(f"{level}:{collected}/{target}")
                
                if collected < target:
                    warnings.append(f"{level} not satisfied ({collected}<{target})")
            
            self.logger.info(f"🎯 Bottom-up completed: {', '.join(summary)} (processed {processed_l1_count} L1s)")
            
            if warnings:
                self.logger.warning(f"⚠️ Some levels not reached target: {', '.join(warnings)}")
            
            # Sort by L1 original order (maintain relevance sorting)
            for level in target_levels:
                if result_memories[level]:
                    result_memories[level].sort(key=lambda x: x.get('chain_origin_l1_rank', 999))
            
            return result_memories
            
        except Exception as e:
            # Do not catch exception here, let it propagate to retry logic
            self.logger.error(f"Bottom-up execution failed: {e}", exc_info=True)
            raise  # Re-raise for outer retry logic to handle
    
    async def get_l3_by_date(self, date_str: str, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Get L3 daily memory by date
        
        Args:
            date_str: Date string in YYYYMMDD format
            state: Retrieval state
            
        Returns:
            L3 memory dictionary, or None if not found
        """
        try:
            self.logger.info(f"📅 Getting L3 daily memory: date={date_str}")
            
            # Parse date
            year = int(date_str[:4])
            month = int(date_str[4:6])
            day = int(date_str[6:8])
            target_date = datetime(year, month, day)
            
            storage_manager = await self._get_storage_manager()
            user_id = state.get("user_id", "")
            expert_id = state.get("expert_id", "")
            
            # Get L3 memory for specified date
            l3_memories = await storage_manager.get_memories_by_date(
                user_id=user_id,
                expert_id=expert_id,
                layer="L3",
                date=target_date
            )
            
            if l3_memories:
                l3_memory = l3_memories[0]  # Get first (usually one L3 per day)
                
                # Convert format
                if hasattr(l3_memory, 'to_dict'):
                    result = l3_memory.to_dict()
                elif isinstance(l3_memory, dict):
                    result = l3_memory.copy()
                else:
                    result = {"content": str(l3_memory)}
                
                result.update({
                    "retrieval_source": "date_l3",
                    "retrieval_strategy": "temporal_associated",
                    "associated_date": date_str,
                    "level": "L3"
                })
                
                self.logger.info(f"✅ Found L3 memory: {result.get('title', 'untitled')[:50]}...")
                return result
            else:
                self.logger.warning(f"No L3 memory found for date: {date_str}")
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to get L3 memory: {e}")
            return None
    
    async def get_l4_by_week(self, week_start: datetime, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get L4 weekly memory by week start date"""
        try:
            self.logger.info(f"📆 Getting L4 weekly memory: week_start={week_start.strftime('%Y-%m-%d')}")
            
            storage_manager = await self._get_storage_manager()
            user_id = state.get("user_id", "")
            expert_id = state.get("expert_id", "")
            
            l4_memories = await storage_manager.get_memories_by_week(
                user_id=user_id,
                expert_id=expert_id,
                layer="L4", 
                week_start=week_start
            )
            
            if l4_memories:
                l4_memory = l4_memories[0]
                
                if hasattr(l4_memory, 'to_dict'):
                    result = l4_memory.to_dict()
                elif isinstance(l4_memory, dict):
                    result = l4_memory.copy()
                else:
                    result = {"content": str(l4_memory)}
                
                result.update({
                    "retrieval_source": "week_l4",
                    "retrieval_strategy": "temporal_associated",
                    "associated_week": week_start.strftime('%Y-%m-%d'),
                    "level": "L4"
                })
                
                self.logger.info(f"✅ Found L4 memory: {result.get('title', 'untitled')[:50]}...")
                return result
            else:
                self.logger.warning(f"No L4 memory found for week: {week_start.strftime('%Y-%m-%d')}")
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to get L4 memory: {e}")
            return None
    
    async def get_l5_by_month(self, month_start: datetime, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get L5 monthly memory by month start date"""
        try:
            self.logger.info(f"🗓️ Getting L5 monthly memory: month_start={month_start.strftime('%Y-%m')}")
            
            storage_manager = await self._get_storage_manager()
            user_id = state.get("user_id", "")
            expert_id = state.get("expert_id", "")
            
            l5_memories = await storage_manager.get_memories_by_month(
                user_id=user_id,
                expert_id=expert_id,
                layer="L5",
                month_start=month_start
            )
            
            if l5_memories:
                l5_memory = l5_memories[0]
                
                if hasattr(l5_memory, 'to_dict'):
                    result = l5_memory.to_dict()
                elif isinstance(l5_memory, dict):
                    result = l5_memory.copy()
                else:
                    result = {"content": str(l5_memory)}
                
                result.update({
                    "retrieval_source": "month_l5",
                    "retrieval_strategy": "temporal_associated",
                    "associated_month": month_start.strftime('%Y-%m'),
                    "level": "L5"
                })
                
                self.logger.info(f"✅ Found L5 memory: {result.get('title', 'untitled')[:50]}...")
                return result
            else:
                self.logger.warning(f"No L5 memory found for month: {month_start.strftime('%Y-%m')}")
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to get L5 memory: {e}")
            return None
    
    # ==================== Shared underlying retrieval methods ====================
    
    async def _execute_bm25_search(self, state: RetrievalState, 
                                 keywords: List[str], level: str) -> List[Dict[str, Any]]:
        """Execute BM25 keyword search (reuse SimpleRetriever logic)"""
        if not keywords:
            self.logger.warning(f"No keywords available for {level} BM25 search")
            return []
        
        try:
            storage_config = get_storage_config()
            postgres_config = storage_config.get('sql', {}).get('postgres', {})
            store = PostgreSQLStore(postgres_config)
            await store.connect()
            
            # Build query conditions
            where_conditions = []
            
            # User group filtering logic: prioritize user group filter, fallback to single user ID
            if state.user_group_ids and len(state.user_group_ids) >= 2:
                # Implement bidirectional filtering: memory must contain both IDs, ensuring it's within both parties' group
                id_a, id_b = state.user_group_ids[0], state.user_group_ids[1]
                user_group_condition = (
                    f"((cm.user_id = '{id_a}' AND cm.expert_id = '{id_b}') OR "
                    f"(cm.user_id = '{id_b}' AND cm.expert_id = '{id_a}') )"

                )
                where_conditions.append(user_group_condition)
                self.logger.info(f"Apply user group filtering: [{id_a}, {id_b}] bidirectional group match")
            else:
                # Fallback to original single user filtering logic
                if state.user_id:
                    where_conditions.append(f"(cm.user_id LIKE '%{state.user_id}%' OR cm.expert_id LIKE '%{state.user_id}%')")
                if state.expert_id:
                    where_conditions.append(f"(cm.user_id LIKE '%{state.expert_id}%' OR cm.expert_id LIKE '%{state.expert_id}%')")
            
            # Cross-layer retrieval mode: do not filter by level, retrieve all level memories
            if not self.cross_layer_retrieval:
                where_conditions.append(f"cm.level = '{level}'")
            
            where_clause = f"WHERE {' AND '.join(where_conditions)}" if where_conditions else ""
            
            # Get memories for BM25 calculation
            async with store.get_session() as session:
                # Fix: JOIN level tables to get session_id
                query = f"""
                SELECT 
                    cm.id, cm.user_id, cm.expert_id, cm.level, cm.title, cm.content, 
                    cm.time_window_start, cm.time_window_end, cm.created_at,
                    COALESCE(l1.session_id, l2.session_id) AS session_id
                FROM core_memories cm
                LEFT JOIN l1_fragment_memories l1 ON cm.id = l1.memory_id AND cm.level = 'L1'
                LEFT JOIN l2_session_memories l2 ON cm.id = l2.memory_id AND cm.level = 'L2'
                {where_clause}
                ORDER BY cm.created_at
                """
                result = await session.execute(text(query))
                rows = result.fetchall()
            
            if not rows:
                self.logger.warning(f"No {level} level memories found for BM25 search")
                return []
            
            # Use BM25 algorithm to calculate relevance scores
            bm25_results = await self._calculate_bm25_scores(rows, keywords, state)
            
            self.logger.info(f"{level} BM25 keyword search completed: {len(bm25_results)} results")
            return bm25_results[:10]  # Limit result count
                
        except Exception as e:
            self.logger.error(f"{level} BM25 keyword search failed: {e}")
            return []
    
    async def _execute_semantic_search(self, state: RetrievalState, level: str) -> List[Dict[str, Any]]:
        """Execute Qdrant semantic search (reuse SimpleRetriever logic)"""
        try:
            storage_manager = await self._get_storage_manager()
            
            query = {"query_text": state.question}
            
            # Fix: prioritize user_group_ids (enforce isolation, consistent with BM25 search)
            if state.user_group_ids and len(state.user_group_ids) >= 2:
                query["user_group_ids"] = state.user_group_ids
                self.logger.info(f"🔒 Semantic search enabled user group isolation: {state.user_group_ids}")
            # Fallback logic (only when no user_group_ids)
            else:
                # Ensure at least one user identifier for security check
                if state.user_id:
                    query["user_id"] = state.user_id
                elif state.expert_id:
                    query["user_id"] = state.expert_id
                elif state.user_group_ids and len(state.user_group_ids) > 0:
                    query["user_id"] = state.user_group_ids[0]
                
                # Add expert_id if exists
                if state.expert_id:
                    query["expert_id"] = state.expert_id
            
            # Cross-layer retrieval mode: do not filter by level, retrieve all level memories
            if self.cross_layer_retrieval:
                filter_conditions = {}  # Do not filter by level
                self.logger.info(f"🌐 Cross-layer retrieval mode: retrieve all level memories (no limit version)")
            else:
                filter_conditions = {"level": level}
            
            options = {
                "limit": 20,
                "score_threshold": 0.0,  # Adjust to lowest threshold to ensure all questions match
                "sort_by": "relevance",
                "filter": filter_conditions
            }
            
            self.logger.info(f"Executing {level} Qdrant semantic search, question: {state.question}")
            
            all_results = await storage_manager.search_memories(query, options, storage_type="vector")
            
            processed_results = []
            missing_session_ids = []  # Record memories missing session_id
            
            for idx, result in enumerate(all_results):
                try:
                    if hasattr(result, 'to_dict'):
                        result_dict = result.to_dict()
                    elif isinstance(result, dict):
                        result_dict = result.copy()
                    else:
                        result_dict = {"content": str(result)}
                    
                    semantic_score = result_dict.get("vector_score", result_dict.get("retrieval_score", 0.0))
                    
                    result_dict.update({
                        "retrieval_source": "qdrant_semantic",
                        "retrieval_strategy": RetrievalStrategy.SEMANTIC.value,
                        "semantic_score": semantic_score,
                        "level": level
                    })
                    
                    # Check if session_id is missing
                    if not result_dict.get('session_id') or result_dict.get('session_id') == 'unknown':
                        memory_id = result_dict.get('id')
                        if memory_id and level in ['L1', 'L2']:
                            missing_session_ids.append((memory_id, level, idx))
                    
                    processed_results.append(result_dict)
                    
                except Exception as e:
                    self.logger.warning(f"Error processing {level} semantic search result: {e}")
                    continue
            
            # Supplement missing session_id
            if missing_session_ids:
                self.logger.info(f"Detected {len(missing_session_ids)} {level} memories missing session_id, attempting to supplement from PostgreSQL")
                await self._supplement_session_ids_from_postgres(processed_results, missing_session_ids)
            
            final_results = processed_results[:10]
            self.logger.info(f"{level} Qdrant semantic search completed: {len(final_results)} results")
            return final_results
            
        except Exception as e:
            self.logger.error(f"{level} Qdrant semantic search failed: {e}")
            return []
    
    # ==================== Utility methods ====================
    
    def _extract_session_id_from_memory(self, memory: Dict[str, Any]) -> Optional[str]:
        """
        Extract session ID from L2 memory
        
        L2 memory ID format is typically: uuid (standard format)
        But title may contain session info: "Session Memory - conv-26_session_4"
        
        Args:
            memory: L2 memory dictionary
            
        Returns:
            session_id or None
        """
        # Prioritize getting from session_id field
        if 'session_id' in memory and memory['session_id']:
            return memory['session_id']
        
        # Extract session info from title
        title = memory.get('title', '')
        if title:
            # Match pattern: "Session Memory - conv-XX_session_Y"
            match = re.search(r'conv-\d+_session_\d+', title)
            if match:
                return match.group(0)
        
        # Extract from ID (L2 ID may contain session info)
        memory_id = memory.get('id', '')
        if 'session' in memory_id.lower():
            return memory_id
        
        # Unable to extract, return ID as fallback
        return memory_id
    
    async def _get_storage_manager(self):
        """Get storage manager instance"""
        if self.storage_manager is None:
            self.storage_manager = await get_memory_storage_manager_async()
        return self.storage_manager
    
    def _dict_to_state(self, state_dict: Dict[str, Any]) -> RetrievalState:
        """Convert dictionary to RetrievalState object"""
        state = RetrievalState()
        for key, value in state_dict.items():
            if hasattr(state, key):
                setattr(state, key, value)
        return state
    
    def _state_to_dict(self, state: RetrievalState) -> Dict[str, Any]:
        """Convert RetrievalState object to dictionary"""
        return {key: value for key, value in state.__dict__.items()}
    
    async def _calculate_bm25_scores(self, rows: List, keywords: List[str], 
                                    state: RetrievalState) -> List[Dict[str, Any]]:
        """
        Calculate BM25 relevance scores (reuse SimpleRetriever successful implementation)
        
        Args:
            rows: Database query results
            keywords: Keyword list
            state: Retrieval state
            
        Returns:
            BM25 scored result list
        """
        try:
            # BM25 algorithm implementation
            class BM25:
                def __init__(self, k1=1.5, b=0.75):
                    self.k1 = k1
                    self.b = b
                    self.documents = []
                    self.doc_freqs = []
                    self.idf = {}
                    self.doc_len = []
                    self.avgdl = 0
                
                def add_document(self, document):
                    self.documents.append(document)
                
                def build_index(self):
                    # Tokenization and statistics
                    for doc in self.documents:
                        words = re.findall(r'\b\w+\b', doc.lower())
                        self.doc_freqs.append(Counter(words))
                        self.doc_len.append(len(words))
                    
                    # Calculate average document length
                    self.avgdl = sum(self.doc_len) / len(self.doc_len) if self.doc_len else 0
                    
                    # Calculate IDF
                    total_docs = len(self.documents)
                    for doc_freq in self.doc_freqs:
                        for word in doc_freq:
                            if word not in self.idf:
                                doc_count = sum(1 for df in self.doc_freqs if word in df)
                                self.idf[word] = math.log(total_docs / doc_count)
                
                def score(self, query, doc_idx):
                    score = 0
                    words = re.findall(r'\b\w+\b', query.lower())
                    
                    for word in words:
                        if word in self.doc_freqs[doc_idx]:
                            tf = self.doc_freqs[doc_idx][word]
                            idf = self.idf.get(word, 0)
                            score += idf * (tf * (self.k1 + 1)) / (tf + self.k1 * (1 - self.b + self.b * self.doc_len[doc_idx] / self.avgdl))
                    
                    return score
                
                def search(self, query, top_k=20):
                    scores = []
                    for i in range(len(self.documents)):
                        score = self.score(query, i)
                        scores.append((i, score))
                    
                    # Sort by score
                    scores.sort(key=lambda x: x[1], reverse=True)
                    return scores[:top_k]
                
                def score_all_documents(self, query):
                    """Calculate BM25 scores for all documents, including zero scores"""
                    scores = []
                    for i in range(len(self.documents)):
                        score = self.score(query, i)
                        scores.append((i, score))
                    return scores
            
            # Build BM25 index
            bm25 = BM25()
            memories = []
            
            for row in rows:
                memory = {
                    'id': row[0],
                    'user_id': row[1],
                    'expert_id': row[2],
                    'level': row[3],
                    'title': row[4],
                    'content': row[5],
                    'time_window_start': row[6],
                    'time_window_end': row[7],
                    'created_at': row[8],
                    'session_id': row[9] if len(row) > 9 else None
                }
                memories.append(memory)
                
                # Build document text
                doc_text = f"{memory['title']} {memory['content']}"
                bm25.add_document(doc_text)
            
            # Build index
            bm25.build_index()
            
            # Search using keywords
            query_text = ' '.join(keywords)
            # Fix: calculate BM25 scores for all memories, not just top_k
            # This ensures all semantically retrieved memories get keyword scores (unmatched set to 0)
            bm25_scores = bm25.score_all_documents(query_text)
            
            # Process results
            results = []
            
            for i, (doc_idx, score) in enumerate(bm25_scores):
                memory = memories[doc_idx]
                
                # Fix: use session_id directly from database
                session_id = memory.get('session_id', 'unknown')
                
                result = {
                    'id': memory['id'],
                    'user_id': memory['user_id'],
                    'expert_id': memory['expert_id'],
                    'level': memory['level'],
                    'title': memory['title'],
                    'content': memory['content'],
                    'session_id': session_id,
                    'time_window_start': memory['time_window_start'],
                    'time_window_end': memory['time_window_end'],
                    'created_at': memory['created_at'],
                    'bm25_score': score,
                    'retrieval_source': 'bm25_keyword',
                    'retrieval_strategy': RetrievalStrategy.KEYWORD.value,
                    'matched_keywords': keywords
                }
                
                results.append(result)
            
            matched_count = len([r for r in results if r['bm25_score'] > 0])
            self.logger.info(f"BM25 scoring completed: {len(results)} total ({matched_count} matched)")
            return results
            
        except Exception as e:
            self.logger.error(f"BM25 score calculation failed: {e}")
            return []
    
    async def _weighted_fusion(self, keyword_results: List[Dict[str, Any]], 
                             semantic_results: List[Dict[str, Any]], 
                             state: RetrievalState) -> List[Dict[str, Any]]:
        """
        Weighted fusion of keyword and semantic search results (reuse SimpleRetriever successful implementation)
        
        Args:
            keyword_results: BM25 keyword search results
            semantic_results: Qdrant semantic search results
            state: Retrieval state
            
        Returns:
            Weighted fused result list
        """
        self.logger.info("🔄 Starting weighted fusion of BM25 keyword and Qdrant semantic search results")
        
        # Collect all results
        all_results = []
        seen_ids = set()
        
        # Score normalization function
        def normalize_score(score, max_score):
            return score / max_score if max_score > 0 else 0
        
        # Calculate max scores for normalization (ensure None converts to 0)
        max_bm25_score = max([r.get("bm25_score") or 0 for r in keyword_results]) if keyword_results else 1.0
        max_semantic_score = max([r.get("semantic_score") or 0 for r in semantic_results]) if semantic_results else 1.0
        
        # Process keyword search results
        for result in keyword_results:
            result_id = result.get("id")
            if result_id and result_id not in seen_ids:
                # Normalize BM25 score and apply weight
                bm25_score = result.get("bm25_score", 0)
                normalized_bm25 = normalize_score(bm25_score, max_bm25_score)
                
                result["fused_score"] = normalized_bm25 * self.keyword_weight
                result["keyword_score_normalized"] = normalized_bm25
                result["semantic_score_normalized"] = 0.0  # Temporarily set to 0, will update if semantic score exists
                
                all_results.append(result)
                seen_ids.add(result_id)
        
        # Process semantic search results, fuse duplicate results
        for result in semantic_results:
            result_id = result.get("id")
            semantic_score = result.get("semantic_score", 0)
            normalized_semantic = normalize_score(semantic_score, max_semantic_score)
            
            if result_id and result_id not in seen_ids:
                # New result: only semantic score
                result["fused_score"] = normalized_semantic * self.semantic_weight
                result["keyword_score_normalized"] = 0.0
                result["semantic_score_normalized"] = normalized_semantic
                
                all_results.append(result)
                seen_ids.add(result_id)
                
            elif result_id in seen_ids:
                # Duplicate result: fuse keyword and semantic scores
                for existing_result in all_results:
                    if existing_result.get("id") == result_id:
                        existing_result["semantic_score_normalized"] = normalized_semantic
                        existing_result["fused_score"] = (
                            existing_result.get("keyword_score_normalized", 0) * self.keyword_weight +
                            normalized_semantic * self.semantic_weight
                        )
                        
                        # Merge retrieval source information
                        existing_sources = existing_result.get("retrieval_sources", [])
                        if "qdrant_semantic" not in existing_sources:
                            existing_result["retrieval_sources"] = existing_sources + ["qdrant_semantic"]
                        
                        # Update retrieval strategy to both (hit by both keyword and semantic search)
                        if existing_result.get("retrieval_strategy") == "keyword":
                            existing_result["retrieval_strategy"] = "both"
                        
                        break
        
        # Sort by fused score
        all_results.sort(key=lambda x: x.get("fused_score", 0.0), reverse=True)
        
        self.logger.info(f"Weighted fusion completed: {len(all_results)} results")
        
        # Output score distribution after weighted fusion (top 10)
        if all_results:
            self.logger.info(f"📊 Score distribution after weighted fusion (top 10):")
            for idx, result in enumerate(all_results[:10], 1):
                fused_score = result.get("fused_score", 0.0)
                bm25_norm = result.get("keyword_score_normalized", 0.0)
                semantic_norm = result.get("semantic_score_normalized", 0.0)
                strategy = result.get("retrieval_strategy", "unknown")
                title = result.get("title", "untitled")[:40]
                self.logger.info(f"   #{idx} fused={fused_score:.4f} (bm25_norm={bm25_norm:.4f}*{self.keyword_weight} + "
                               f"semantic_norm={semantic_norm:.4f}*{self.semantic_weight}), "
                               f"strategy={strategy}, title={title}...")
        
        return all_results
    
    # ==================== V2 version new methods ====================
    
    async def _execute_bm25_search_with_limit(self, state: RetrievalState, 
                                            keywords: List[str], level: str, 
                                            limit: int) -> List[Dict[str, Any]]:
        """Execute BM25 keyword search (with specified count limit)"""
        if not keywords:
            self.logger.warning(f"No keywords available for {level} BM25 search")
            return []
        
        try:
            storage_config = get_storage_config()
            postgres_config = storage_config.get('sql', {}).get('postgres', {})
            store = PostgreSQLStore(postgres_config)
            await store.connect()
            
            # Build query conditions (reuse existing logic)
            where_conditions = []
            
            # User group filtering logic
            if state.user_group_ids and len(state.user_group_ids) >= 2:
                id_a, id_b = state.user_group_ids[0], state.user_group_ids[1]
                user_group_condition = (
                    f"((cm.user_id = '{id_a}' AND cm.expert_id = '{id_b}') OR "
                    f"(cm.user_id = '{id_b}' AND cm.expert_id = '{id_a}'))"
                )
                where_conditions.append(user_group_condition)
            else:
                if state.user_id:
                    where_conditions.append(f"(cm.user_id LIKE '%{state.user_id}%' OR cm.expert_id LIKE '%{state.user_id}%')")
                if state.expert_id:
                    where_conditions.append(f"(cm.user_id LIKE '%{state.user_id}%' OR cm.expert_id LIKE '%{state.expert_id}%')")
            
            # Cross-layer retrieval mode: do not filter by level, retrieve all level memories
            if not self.cross_layer_retrieval:
                where_conditions.append(f"cm.level = '{level}'")
            where_clause = f"WHERE {' AND '.join(where_conditions)}" if where_conditions else ""
            
            # Get memories for BM25 calculation
            async with store.get_session() as session:
                # Fix: JOIN level tables to get session_id
                query = f"""
                SELECT 
                    cm.id, cm.user_id, cm.expert_id, cm.level, cm.title, cm.content, 
                    cm.time_window_start, cm.time_window_end, cm.created_at,
                    COALESCE(l1.session_id, l2.session_id) AS session_id
                FROM core_memories cm
                LEFT JOIN l1_fragment_memories l1 ON cm.id = l1.memory_id AND cm.level = 'L1'
                LEFT JOIN l2_session_memories l2 ON cm.id = l2.memory_id AND cm.level = 'L2'
                {where_clause}
                ORDER BY cm.created_at
                """
                result = await session.execute(text(query))
                rows = result.fetchall()
            
            if not rows:
                self.logger.warning(f"No {level} level memories found for BM25 search")
                return []
            
            # Use BM25 algorithm to calculate relevance scores
            bm25_results = await self._calculate_bm25_scores(rows, keywords, state)
            
            # Fix: do not apply count limit, return all BM25 scored results
            # This ensures all semantically retrieved memories get keyword scores (unmatched set to 0)
            self.logger.info(f"{level} BM25 keyword search completed: {len(bm25_results)} results (scored all memories)")
            
            # Output score distribution of BM25 search results (top 10)
            if bm25_results:
                self.logger.info(f"📊 {level} BM25 search results (top 10, sorted by relevance):")
                for idx, result in enumerate(bm25_results[:10], 1):
                    bm25_score = result.get("bm25_score", 0.0)
                    title = result.get("title", "untitled")[:40]
                    timestamp = result.get("created_at") or result.get("time_window_start") or result.get("timestamp", "N/A")
                    self.logger.info(f"   #{idx} bm25_score={bm25_score:.4f}, time={timestamp}, title={title}...")
            
            return bm25_results
                
        except Exception as e:
            self.logger.error(f"{level} BM25 keyword search failed: {e}")
            return []
    
    async def _execute_semantic_search_with_limit(self, state: RetrievalState, level: str, 
                                                limit: int) -> List[Dict[str, Any]]:
        """Execute Qdrant semantic search (with specified count limit)"""
        try:
            storage_manager = await self._get_storage_manager()
            
            query = {"query_text": state.question}
            
            # Fix: prioritize user_group_ids (enforce isolation, consistent with BM25 search)
            if state.user_group_ids and len(state.user_group_ids) >= 2:
                query["user_group_ids"] = state.user_group_ids
                self.logger.info(f"🔒 Semantic search enabled user group isolation: {state.user_group_ids}")
            # Fallback logic (only when no user_group_ids)
            else:
                # Ensure at least one user identifier for security check
                if state.user_id:
                    query["user_id"] = state.user_id
                elif state.expert_id:
                    query["user_id"] = state.expert_id
                elif state.user_group_ids and len(state.user_group_ids) > 0:
                    query["user_id"] = state.user_group_ids[0]
                
                # Add expert_id if exists
                if state.expert_id:
                    query["expert_id"] = state.expert_id
            
            # Cross-layer retrieval mode: do not filter by level, retrieve all level memories
            if self.cross_layer_retrieval:
                filter_conditions = {}  # Do not filter by level
                self.logger.info(f"🌐 Cross-layer retrieval mode: retrieve all level memories, limit={limit}")
            else:
                filter_conditions = {"level": level}
            
            options = {
                "limit": limit,  # Use specified limit count
                "score_threshold": 0.0,  # Adjust to lowest threshold to ensure all questions match
                "sort_by": "relevance",
                "filter": filter_conditions
            }
            
            self.logger.info(f"Executing {level} Qdrant semantic search, question: {state.question}, limit: {limit}")
            
            all_results = await storage_manager.search_memories(query, options, storage_type="vector")
            
            processed_results = []
            missing_session_ids = []  # Record memories missing session_id
            
            for result in all_results:
                if hasattr(result, 'to_dict'):
                    result_dict = result.to_dict()
                elif isinstance(result, dict):
                    result_dict = result.copy()
                else:
                    self.logger.warning(f"Unknown result type: {type(result)}")
                    continue
                
                # Add retrieval source marker
                result_dict["retrieval_source"] = "qdrant_semantic"
                result_dict["retrieval_strategy"] = "semantic"
                
                # Fix: map vector_score/retrieval_score to semantic_score
                if "vector_score" in result_dict and result_dict["vector_score"] is not None:
                    result_dict["semantic_score"] = result_dict["vector_score"]
                elif "retrieval_score" in result_dict and result_dict["retrieval_score"] is not None:
                    result_dict["semantic_score"] = result_dict["retrieval_score"]
                else:
                    result_dict["semantic_score"] = 0.0
                
                # Check and record memories missing session_id
                if not result_dict.get('session_id') or result_dict.get('session_id') == 'unknown':
                    memory_id = result_dict.get('id')
                    memory_level = result_dict.get('level', level)
                    if memory_id:
                        missing_session_ids.append((memory_id, memory_level, len(processed_results)))
                
                processed_results.append(result_dict)
            
            # Supplement missing session_id
            if missing_session_ids:
                self.logger.warning(f"Detected {len(missing_session_ids)} memories missing session_id, attempting to supplement from PostgreSQL")
                await self._supplement_session_ids_from_postgres(processed_results, missing_session_ids)
            
            self.logger.info(f"{level} Qdrant semantic search completed: {len(processed_results)} results (limit {limit})")
            
            # Output score distribution of semantic search results (top 10)
            if processed_results:
                self.logger.info(f"📊 {level} semantic search results (top 10):")
                for idx, result in enumerate(processed_results[:10], 1):
                    semantic_score = result.get("semantic_score", 0.0)
                    title = result.get("title", "untitled")[:40]
                    timestamp = result.get("created_at") or result.get("time_window_start") or result.get("timestamp", "N/A")
                    self.logger.info(f"   #{idx} semantic_score={semantic_score:.4f}, time={timestamp}, title={title}...")
            
            return processed_results
            
        except Exception as e:
            self.logger.error(f"{level} Qdrant semantic search failed: {e}")
            return []
    
    async def _supplement_session_ids_from_postgres(self, results: List[Dict[str, Any]], 
                                            missing_items: List[tuple]) -> None:
        """
        Supplement missing session_id from PostgreSQL
        
        Args:
            results: Result list (will be modified in place)
            missing_items: Missing items list, format: [(memory_id, level, result_index), ...]
        """
        try:
            from storage.postgres_store import PostgreSQLStore
            from timem.utils.config_manager import get_storage_config
            
            storage_config = get_storage_config()
            postgres_config = storage_config.get('sql', {}).get('postgres', {})
            store = PostgreSQLStore(postgres_config)
            await store.connect()
            
            supplement_count = 0
            for memory_id, level, result_idx in missing_items:
                try:
                    # Query corresponding level table based on level
                    async with store.get_session() as session:
                        if level == 'L1':
                            from sqlalchemy import text
                            query = text("SELECT session_id FROM l1_fragment_memories WHERE memory_id = :memory_id")
                        elif level == 'L2':
                            from sqlalchemy import text
                            query = text("SELECT session_id FROM l2_session_memories WHERE memory_id = :memory_id")
                        else:
                            # Other levels not supported yet
                            continue
                        
                        result = await session.execute(query, {"memory_id": memory_id})
                        row = result.fetchone()
                        
                        if row and row[0]:
                            # Update session_id in result dictionary
                            results[result_idx]['session_id'] = row[0]
                            supplement_count += 1
                            self.logger.debug(f"✅ Supplemented session_id for memory {memory_id}: {row[0]}")
                        else:
                            self.logger.debug(f"⚠️ No session_id found for memory {memory_id}")
                except Exception as e:
                    self.logger.warning(f"Failed to supplement session_id for memory {memory_id}: {e}")
                    continue
            
            self.logger.info(f"✨ Successfully supplemented session_id for {supplement_count}/{len(missing_items)} memories")
                
        except Exception as e:
            self.logger.error(f"Failed to supplement session_id from PostgreSQL: {e}")
    
    async def _merge_and_deduplicate_results(self, keyword_results: List[Dict[str, Any]], 
                                           semantic_results: List[Dict[str, Any]], 
                                           state: RetrievalState) -> List[Dict[str, Any]]:
        """
        Merge and deduplicate two types of search results, and supplement missing scores
        
        Args:
            keyword_results: BM25 keyword search results
            semantic_results: Qdrant semantic search results
            state: Retrieval state
            
        Returns:
            Deduplicated merged results with complete semantic and keyword scores for each memory
        """
        self.logger.info("🔄 Starting merge, deduplication and score supplementation")
        
        # Set and result storage for deduplication
        seen_ids = set()
        merged_results = []
        
        # Mapping for score supplementation
        keyword_score_map = {r.get("id"): r.get("bm25_score", 0) for r in keyword_results if r.get("id")}
        semantic_score_map = {r.get("id"): r.get("semantic_score", 0) for r in semantic_results if r.get("id")}
        
        # Calculate normalization parameters (ensure None converts to 0)
        max_bm25_score = max([r.get("bm25_score") or 0 for r in keyword_results]) if keyword_results else 1.0
        max_semantic_score = max([r.get("semantic_score") or 0 for r in semantic_results]) if semantic_results else 1.0
        
        def normalize_score(score, max_score):
            return score / max_score if max_score > 0 else 0
        
        # Process all unique memory IDs
        all_memory_ids = set()
        all_memory_ids.update(keyword_score_map.keys())
        all_memory_ids.update(semantic_score_map.keys())
        
        # Create mapping from ID to complete memory object
        memory_objects = {}
        for result in keyword_results + semantic_results:
            memory_id = result.get("id")
            if memory_id and memory_id not in memory_objects:
                memory_objects[memory_id] = result
        
        # Create complete scoring records for each unique memory
        for memory_id in all_memory_ids:
            if memory_id in seen_ids:
                continue
                
            # Get base memory object
            base_memory = memory_objects.get(memory_id, {})
            if not base_memory:
                self.logger.warning(f"Memory object not found: {memory_id}")
                continue
            
            # Get both types of scores
            bm25_score = keyword_score_map.get(memory_id, 0)
            semantic_score = semantic_score_map.get(memory_id, 0)
            
            # Normalize scores
            normalized_bm25 = normalize_score(bm25_score, max_bm25_score)
            normalized_semantic = normalize_score(semantic_score, max_semantic_score)
            
            # Calculate weighted fusion score
            fused_score = (normalized_bm25 * self.keyword_weight + 
                          normalized_semantic * self.semantic_weight)
            
            # Create complete memory record
            complete_memory = base_memory.copy()
            complete_memory.update({
                "bm25_score": bm25_score,
                "semantic_score": semantic_score,
                "keyword_score_normalized": normalized_bm25,
                "semantic_score_normalized": normalized_semantic,
                "fused_score": fused_score,
                "retrieval_sources": []
            })
            
            # Mark retrieval sources
            if memory_id in keyword_score_map:
                complete_memory["retrieval_sources"].append("postgres_bm25")
            if memory_id in semantic_score_map:
                complete_memory["retrieval_sources"].append("qdrant_semantic")
            
            # Set retrieval strategy
            if len(complete_memory["retrieval_sources"]) > 1:
                complete_memory["retrieval_strategy"] = "both"
            elif "postgres_bm25" in complete_memory["retrieval_sources"]:
                complete_memory["retrieval_strategy"] = "keyword"
            else:
                complete_memory["retrieval_strategy"] = "semantic"
            
            merged_results.append(complete_memory)
            seen_ids.add(memory_id)
        
        # Sort by fused score
        merged_results.sort(key=lambda x: x.get("fused_score", 0.0), reverse=True)
        
        self.logger.info(f"Merge and dedup completed: keyword {len(keyword_results)} + semantic {len(semantic_results)} "
                        f"→ {len(merged_results)} after dedup")
        self.logger.info(f"Score supplementation: {len([r for r in merged_results if r['retrieval_strategy'] == 'both'])} hit both")
        
        # Output score distribution after merge (top 10)
        if merged_results:
            self.logger.info(f"📊 Score distribution after merge (top 10, sorted by fused_score):")
            for idx, result in enumerate(merged_results[:10], 1):
                fused_score = result.get("fused_score", 0.0)
                bm25_score = result.get("bm25_score", 0.0)
                semantic_score = result.get("semantic_score", 0.0)
                strategy = result.get("retrieval_strategy", "unknown")
                title = result.get("title", "untitled")[:40]
                self.logger.info(f"   #{idx} fused={fused_score:.4f} (bm25={bm25_score:.4f}, semantic={semantic_score:.4f}), "
                               f"strategy={strategy}, title={title}...")
        
        return merged_results
    
    async def _fine_ranking_by_weighted_score(self, coarse_results: List[Dict[str, Any]], 
                                            final_top_k: int) -> List[Dict[str, Any]]:
        """
        Fine ranking based on weighted scores and sort by time order
        
        Coarse-fine ranking process:
        1. Coarse ranking: select top N from all results by fused_score (most relevant N)
        2. Fine ranking: sort these N by time (ensure causal chain coherence)
        
        Args:
            coarse_results: Coarse ranking result list (with complete scores)
            final_top_k: Number of memories to return finally
            
        Returns:
            Fine-ranked result list sorted by time
        """
        self.logger.info(f"🎯 ======== Starting fine ranking ========")
        self.logger.info(f"🎯 Coarse ranking result count: {len(coarse_results)}, target fine ranking count: {final_top_k}")
        
        # Output score distribution of coarse ranking results (top 10)
        if coarse_results:
            self.logger.info(f"📊 Coarse ranking result score distribution (top 10):")
            for idx, result in enumerate(coarse_results[:10], 1):
                fused_score = result.get("fused_score", 0.0)
                bm25_score = result.get("bm25_score", 0.0)
                semantic_score = result.get("semantic_score", 0.0)
                title = result.get("title", "untitled")[:50]
                timestamp = result.get("created_at") or result.get("time_window_start") or result.get("timestamp", "N/A")
                self.logger.info(f"   #{idx} fused={fused_score:.4f}, bm25={bm25_score:.4f}, "
                               f"semantic={semantic_score:.4f}, time={timestamp}, title={title}...")
        
        # Step 1: Coarse ranking - select top N by fused_score (most relevant N)
        if len(coarse_results) <= final_top_k:
            # If coarse ranking results don't exceed requirement, use all
            selected_results = coarse_results[:]
            self.logger.warning(f"⚠️ Coarse ranking results less than {final_top_k}, using all {len(selected_results)}")
        else:
            # Select top N by fused_score (core of coarse ranking)
            sorted_by_score = sorted(coarse_results, key=lambda x: x.get("fused_score", 0.0), reverse=True)
            selected_results = sorted_by_score[:final_top_k]
            self.logger.info(f"✅ Coarse ranking completed: selected top {final_top_k} most relevant from {len(coarse_results)}")
        
        # Output scores of memories selected by coarse ranking (before fine ranking)
        self.logger.info(f"📊 {len(selected_results)} memories selected by coarse ranking:")
        for idx, result in enumerate(selected_results, 1):
            fused_score = result.get("fused_score", 0.0)
            title = result.get("title", "untitled")[:40]
            timestamp = result.get("created_at") or result.get("time_window_start") or result.get("timestamp", "N/A")
            self.logger.info(f"   #{idx} fused={fused_score:.4f}, time={timestamp}, title={title}...")
        
        # Step 2: Fine ranking - sort selected top N by time (ensure causal chain coherence)
        def extract_timestamp(memory):
            # Try multiple possible timestamp fields
            for field in ["created_at", "time_window_start", "timestamp"]:
                if field in memory and memory[field]:
                    return str(memory[field])
            return "1970-01-01T00:00:00"
        
        time_sorted_results = sorted(selected_results, key=extract_timestamp)
        
        self.logger.info(f"✅ Fine ranking completed: reordered {len(selected_results)} memories by time")
        
        # Output memory order after fine ranking
        self.logger.info(f"📊 {len(time_sorted_results)} memories after fine ranking (by time order):")
        for idx, result in enumerate(time_sorted_results, 1):
            fused_score = result.get("fused_score", 0.0)
            title = result.get("title", "untitled")[:40]
            timestamp = result.get("created_at") or result.get("time_window_start") or result.get("timestamp", "N/A")
            self.logger.info(f"   #{idx} fused={fused_score:.4f}, time={timestamp}, title={title}...")
        
        # Output fine ranking statistics
        strategy_counts = Counter(r.get("retrieval_strategy", "unknown") for r in time_sorted_results)
        self.logger.info(f"📈 Fine ranking result source distribution: {dict(strategy_counts)}")
        self.logger.info(f"🎯 ======== Fine ranking completed ========")
        
        return time_sorted_results
    
    async def direct_retrieve_high_level_memories(self, state: Dict[str, Any],
                                                   target_level: str,
                                                   target_count: int,
                                                   llm_keywords: List[str] = None) -> List[Dict[str, Any]]:
        """
        Direct retrieval of high-level memories (dual-path retrieval supplement)
        
        When bottom-up chain traversal cannot find enough high-level memories, use this method for direct retrieval supplement.
        Uses mixed strategy of semantic search + keyword search.
        
        Args:
            state: Retrieval state dictionary
            target_level: Target level, e.g., 'L5', 'L4', 'L3'
            target_count: Number of memories to retrieve
            llm_keywords: List of keywords extracted by LLM (optional)
            
        Returns:
            List of retrieved high-level memories
        """
        try:
            self.logger.info(f"🔍 Starting dual-path direct retrieval of {target_level} memories (target count: {target_count})")
            
            if target_count <= 0:
                return []
            
            question = state.get("question", "")
            user_id = state.get("user_id")
            expert_id = state.get("expert_id")
            
            if not question or not user_id or not expert_id:
                self.logger.warning(f"Missing necessary parameters, unable to execute dual-path retrieval")
                return []
            
            # Ensure storage_manager is initialized
            if not self.storage_manager:
                self.storage_manager = await get_memory_storage_manager_async()
            
            # Construct retrieval filter conditions (limit to level)
            filters = {
                "level": target_level,
                "user_id": user_id
            }
            
            # Use mixed retrieval (semantic + keyword)
            # 1. Semantic search
            semantic_results = []
            try:
                self.logger.info(f"  Executing semantic search {target_level}...")
                semantic_results = await self.storage_manager.semantic_search(
                    query_text=question,
                    user_id=user_id,
                    expert_id=expert_id,
                    top_k=target_count * 2,  # Retrieve more to allow fusion
                    level_filter=target_level
                )
                self.logger.info(f"  Semantic search obtained {len(semantic_results)} results")
            except Exception as e:
                self.logger.warning(f"Semantic search {target_level} failed: {e}")
            
            # 2. Keyword search (if keywords provided)
            keyword_results = []
            if llm_keywords:
                try:
                    self.logger.info(f"  Executing keyword search {target_level}...")
                    # Use PostgreSQL for keyword search
                    keyword_results = await self._keyword_search_high_level(
                        user_id, expert_id, llm_keywords, target_level, target_count * 2
                    )
                    self.logger.info(f"  Keyword search obtained {len(keyword_results)} results")
                except Exception as e:
                    self.logger.warning(f"Keyword search {target_level} failed: {e}")
            
            # 3. Merge, deduplicate and calculate fused scores
            if not semantic_results and not keyword_results:
                self.logger.warning(f"Dual-path search returned no results")
                return []
            
            # Simple merge and deduplication
            seen_ids = set()
            merged_results = []
            
            # Add semantic search results
            for result in semantic_results:
                memory_id = result.get("id") or result.get("memory_id")
                if memory_id and memory_id not in seen_ids:
                    seen_ids.add(memory_id)
                    result["retrieval_source"] = "semantic_direct"
                    merged_results.append(result)
            
            # Add keyword search results
            for result in keyword_results:
                memory_id = result.get("id") or result.get("memory_id")
                if memory_id and memory_id not in seen_ids:
                    seen_ids.add(memory_id)
                    result["retrieval_source"] = "keyword_direct"
                    merged_results.append(result)
            
            # Sort by score and take top_k
            def get_score(r):
                return r.get("fused_score") or r.get("semantic_score") or r.get("bm25_score") or 0
            
            merged_results.sort(key=get_score, reverse=True)
            final_results = merged_results[:target_count]
            
            self.logger.info(f"✅ Dual-path search completed: obtained {len(final_results)} {target_level} memories")
            for idx, result in enumerate(final_results, 1):
                title = result.get("title", "untitled")[:40]
                score = get_score(result)
                source = result.get("retrieval_source", "unknown")
                self.logger.info(f"  #{idx} {target_level}: {title}... (score={score:.4f}, source={source})")
            
            return final_results
            
        except Exception as e:
            self.logger.error(f"Dual-path direct search {target_level} failed: {e}")
            return []
    
    async def _keyword_search_high_level(self, user_id: str, expert_id: str,
                                         keywords: List[str], target_level: str,
                                         top_k: int) -> List[Dict[str, Any]]:
        """
        Use keywords to search high-level memories in PostgreSQL
        
        Args:
            user_id: User ID
            expert_id: Expert ID  
            keywords: Keyword list
            target_level: Target level
            top_k: Number of results to return
            
        Returns:
            List of search results
        """
        try:
            # Determine table name
            table_map = {
                "L2": "l2_session_memories",
                "L3": "l3_daily_memories",
                "L4": "l4_weekly_memories",
                "L5": "l5_monthly_memories"
            }
            
            table_name = table_map.get(target_level)
            if not table_name:
                self.logger.warning(f"Unsupported level: {target_level}")
                return []
            
            # Build search query (using full-text search)
            search_query = " | ".join(keywords)  # PostgreSQL ts_query format
            
            # Get PostgreSQL connection
            storage_config = get_storage_config()
            store = PostgreSQLStore(storage_config)
            
            async with store.get_session() as session:
                # Use full-text search
                query = text(f"""
                    SELECT memory_id, content, title, 
                           ts_rank(to_tsvector('english', content), to_tsquery('english', :search_query)) as rank
                    FROM {table_name}
                    WHERE user_id = :user_id 
                      AND expert_id = :expert_id
                      AND to_tsvector('english', content) @@ to_tsquery('english', :search_query)
                    ORDER BY rank DESC
                    LIMIT :limit
                """)
                
                result = await session.execute(query, {
                    "user_id": user_id,
                    "expert_id": expert_id,
                    "search_query": search_query,
                    "limit": top_k
                })
                
                rows = result.fetchall()
                
                results = []
                for row in rows:
                    results.append({
                        "id": row[0],
                        "memory_id": row[0],
                        "content": row[1],
                        "title": row[2],
                        "bm25_score": float(row[3]) if row[3] else 0.0,
                        "level": target_level
                    })
                
                return results
                
        except Exception as e:
            self.logger.error(f"Keyword search for high-level memories failed: {e}")
            return []