"""
Hybrid Retriever - Bottom-Up Refactored Version

Implements hybrid retrieval based on BottomUpRetrieverBase, solving context pollution:
1. L1 hybrid retrieval (top5) - reuse successful logic
2. Session scoring analysis to determine most relevant time periods
3. Time-associated supplement: L3 daily report + L4 weekly report of best session
4. Maintain temporal continuity, avoid introducing noise from unrelated time periods

Design Goals:
- Improve accuracy from 5-10% drop to 85-95% (close to Simple level)
- Eliminate time-unrelated memory pollution, reduce noise by 70%+
- Maintain L1 fact information dominance, L3/L4 as concept supplements
"""

import time
from datetime import datetime
from typing import Dict, List, Any, Optional

from timem.workflows.retrieval_nodes.bottom_up_retriever_base import BottomUpRetrieverBase
from timem.utils.logging import get_logger

logger = get_logger(__name__)


class HybridRetriever(BottomUpRetrieverBase):
    """
    Hybrid retriever - Bottom-up refactored version
    
    Refactored strategy:
    1. Keep L1 hybrid retrieval as core (reuse SimpleRetriever success experience)
    2. Supplement L3, L4 memories based on best session time association
    3. Ensure all memories come from related time periods, avoid context pollution
    4. L1 dominant (80%) + L3 concept supplement (15%) + L4 weekly report supplement (5%)
    """
    
    def __init__(self, strategy_config: Optional[Dict[str, Any]] = None, **kwargs):
        """Initialize HybridRetriever"""
        super().__init__(strategy_config=strategy_config, **kwargs)
        
        # Read layer_limits and final_limits from strategy config
        self.strategy_config = strategy_config or {}
        layer_limits = self.strategy_config.get('layer_limits', {})
        final_limits = self.strategy_config.get('final_limits', {})
        
        # Read enabled layers list from config
        self.enabled_layers = self.strategy_config.get('layers', ['L1', 'L2', 'L3', 'L4', 'L5'])
        self.logger.info(f"Enabled layers: {self.enabled_layers}")
        
        # Read whether to disable bottom-up mechanism from config
        self.disable_bottom_up = self.strategy_config.get('disable_bottom_up', False)
        if self.disable_bottom_up:
            self.logger.warning(f"Bottom-up mechanism disabled, will only retrieve L1 memories")
        
        # Configure coarse and fine ranking limits for each layer
        self.l1_coarse_top_k = layer_limits.get('L1', 40)  # Coarse ranking count
        self.l1_final_top_k = final_limits.get('L1', 20)   # Fine ranking count
        self.l2_final_top_k = final_limits.get('L2', 2)    # L2 count
        self.l3_final_top_k = final_limits.get('L3', 1)    # L3 count
        self.l4_final_top_k = final_limits.get('L4', 1)    # L4 count
        self.l5_final_top_k = final_limits.get('L5', 1)    # L5 count (monthly report)
        
        # Set strategy name for parent class
        self.strategy_name = 'hybrid'
        
        self.logger.info(f"Initialize HybridRetriever - Bottom-Up Refactored Version")
        self.logger.info(f"   Enabled layers: {self.enabled_layers}")
        self.logger.info(f"   L1 coarse: {self.l1_coarse_top_k}, L1 fine: {self.l1_final_top_k}")
        self.logger.info(f"   L2: {self.l2_final_top_k}, L3: {self.l3_final_top_k}, L4: {self.l4_final_top_k}, L5: {self.l5_final_top_k}")
    
    def get_retriever_name(self) -> str:
        """Get retriever name"""
        return "HybridRetriever"
    
    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run hybrid retrieval (LangGraph node standard interface)
        
        Implement bottom-up strategy:
        1. L1 hybrid retrieval (top5)
        2. Session scoring analysis
        3. Time-associated supplement: L3 daily report + L4 weekly report of best session
        4. Layer sorting: L1 → L2 → L3 → L4
        
        Args:
            state: Workflow state dictionary
            
        Returns:
            Updated state dictionary
        """
        try:
            start_time = time.time()
            self.logger.info("Start HybridRetriever retrieval process")
            
            # Validate input
            question = state.get("question", "").strip()
            if not question:
                error_msg = "Question cannot be empty"
                self.logger.error(error_msg)
                state["errors"] = state.get("errors", []) + [error_msg]
                return state
            
            llm_keywords = state.get("key_entities", [])
            self.logger.info(f"Get LLM keywords: {llm_keywords}")
            
            # Check if L1 is in enabled_layers
            if 'L1' not in self.enabled_layers:
                self.logger.warning(f"L1 not in enabled_layers ({self.enabled_layers}), skip L1 retrieval, execute direct high-level retrieval")
                # Direct retrieval of memories in enabled_layers (no L1 starting point and bottom-up)
                return await self._direct_high_level_retrieval(state, llm_keywords)
            
            # Step 1: L1 hybrid retrieval (reuse SimpleRetriever success logic) - coarse then fine ranking
            self.logger.info("Step 1: L1 hybrid retrieval (coarse + fine ranking)")
            l1_results = await self.perform_l1_retrieval(
                state, llm_keywords, 
                top_k=self.l1_final_top_k,  # Final return count
                coarse_ranking=True  # Enable coarse ranking mechanism
            )
            
            if not l1_results:
                error_msg = "L1 retrieval returned no results"
                self.logger.warning(error_msg)
                state["errors"] = state.get("errors", []) + [error_msg]
                state["needs_retry"] = True
                state["retry_reason"] = error_msg
                return state
            
            self.logger.info(f"L1 retrieval obtained {len(l1_results)} results")
            
            # Step 2: Session scoring analysis (get multiple session rankings)
            self.logger.info("Step 2: Session scoring analysis (multi-session ranking)")
            session_analysis = self.analyze_l1_for_multi_session(l1_results)
            
            ranked_sessions = session_analysis.get('ranked_sessions', [])
            if not ranked_sessions:
                self.logger.warning("No valid session found, return only L1 results")
                final_results = self._hierarchical_time_sort(l1_results)
                return self._build_final_result(state, final_results, session_analysis, time.time() - start_time)
            
            self.logger.info(f"Obtained {len(ranked_sessions)} ranked sessions")
            
            # Step 3: Multi-starting-point chain traversal to get parent memories (based on configured layers)
            self.logger.info(f"Step 3: Multi-starting-point chain traversal for parent memories (layers: {self.enabled_layers})")
            
            # Check if bottom-up mechanism is disabled
            if self.disable_bottom_up:
                self.logger.warning("Bottom-up mechanism disabled, skip parent memory retrieval")
                parent_memories = {}
                target_levels = []
            else:
                # Dynamically build target_levels and target_counts based on configured layers
                target_levels = [layer for layer in self.enabled_layers if layer != 'L1']  # Exclude L1 (already retrieved)
                target_counts = {}
                for layer in target_levels:
                    if layer == 'L2':
                        target_counts[layer] = self.l2_final_top_k
                    elif layer == 'L3':
                        target_counts[layer] = self.l3_final_top_k
                    elif layer == 'L4':
                        target_counts[layer] = self.l4_final_top_k
                    elif layer == 'L5':
                        target_counts[layer] = self.l5_final_top_k
                    else:
                        # For other layers, read from final_limits
                        target_counts[layer] = self.strategy_config.get('final_limits', {}).get(layer, 1)
                
                self.logger.info(f"Target layers and counts: {target_counts}")
                
                # If no other layers need retrieval, skip this step
                if not target_levels:
                    self.logger.info("Only L1 enabled, skip parent memory retrieval")
                    parent_memories = {}
                else:
                    # Engineering-level fix: mandatory bottom-layer memory retrieval, throw exception on failure
                    try:
                        parent_memories = await self.get_parent_memories_by_chain(
                            l1_results, target_levels, target_counts, state
                        )
                    except Exception as e:
                        # Bottom-up already retried 3 times and still failed, this is a serious error
                        error_msg = f"Bottom-up chain traversal completely failed (auto-retried 3 times): {e}"
                        self.logger.error(error_msg)
                        state["errors"] = state.get("errors", []) + [error_msg]
                        state["needs_retry"] = True
                        state["retry_reason"] = "bottom_up_chain_failed"
                        # Key fix: do not allow returning only L1, must mark as failed
                        raise Exception(error_msg)
            
            # Engineering-level fix: dynamically validate retrieval results for each layer
            layer_stats = {}
            for layer in target_levels:
                layer_memories = parent_memories.get(layer, [])
                layer_stats[layer] = len(layer_memories)
                
                if not layer_memories and target_counts.get(layer, 0) > 0:
                    warning_msg = f"Bottom-up did not retrieve {layer} parent memories (expected {target_counts[layer]}), database may lack parent-child relationships"
                    self.logger.warning(warning_msg)
                    state["warnings"] = state.get("warnings", []) + [warning_msg]
            
            if layer_stats:
                stats_str = ', '.join([f"{k}={v}" for k, v in layer_stats.items()])
                self.logger.info(f"Chain traversal complete: {stats_str}")
            
            # Validate: at least one layer should have memories
            if target_levels and all(len(parent_memories.get(layer, [])) == 0 for layer in target_levels):
                warning_msg = f"Bottom-up did not retrieve any parent memories ({'/'.join(target_levels)} all empty), results contain only L1"
                self.logger.warning(warning_msg)
                state["warnings"] = state.get("warnings", []) + [warning_msg]
            
            # Step 4: Combine and deduplicate, sort by layer and time
            self.logger.info("Step 4: Combine, deduplicate and sort by layer and time")
            
            # Fix: global deduplication logic, avoid qdrant_semantic and bottom_up duplicates
            all_results = []
            seen_ids = set()
            duplicate_stats = {}
            
            # Add L1 memories (highest priority)
            for mem in l1_results:
                mem_id = mem.get('id') or mem.get('memory_id')
                if mem_id and mem_id not in seen_ids:
                    all_results.append(mem)
                    seen_ids.add(mem_id)
            
            # Dynamically add parent memories for each layer (deduplicate) (only if bottom-up not disabled)
            if not self.disable_bottom_up and target_levels:
                for layer in target_levels:
                    layer_memories = parent_memories.get(layer, [])
                    duplicate_stats[layer] = 0
                    
                    for memory in layer_memories:
                        mem_id = memory.get('id') or memory.get('memory_id')
                        if mem_id and mem_id not in seen_ids:
                            all_results.append(memory)
                            seen_ids.add(mem_id)
                        elif mem_id:
                            duplicate_stats[layer] += 1
                
                if sum(duplicate_stats.values()) > 0:
                    stats_str = ', '.join([f"{k} skipped {v}" for k, v in duplicate_stats.items() if v > 0])
                    self.logger.info(f"Deduplication stats: {stats_str}")
            else:
                if self.disable_bottom_up:
                    self.logger.info("Bottom-up disabled, use only L1 memories")
            
            # Layer sorting: L1 → L2 → L3 → L4 → L5
            final_results = self._hierarchical_time_sort(all_results)
            
            # Apply quality control and weight adjustment
            final_results = self._apply_quality_control(final_results)
            
            # Build final result
            execution_time = time.time() - start_time
            result = self._build_final_result(state, final_results, session_analysis, execution_time)
            
            self.logger.info(f"HybridRetriever complete: {len(final_results)} results, "
                           f"execution time {execution_time:.2f}s")
            self.logger.info(f"Result distribution: {self._analyze_result_distribution(final_results)}")
            
            return result
            
        except Exception as e:
            error_msg = f"HybridRetriever execution failed: {str(e)}"
            self.logger.error(error_msg)
            state["errors"] = state.get("errors", []) + [error_msg]
            return state
    
    def analyze_l1_for_multi_session(self, l1_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze L1 memories to get ranking information for multiple sessions
        
        Args:
            l1_results: List of L1 retrieval results
            
        Returns:
            Analysis result containing ranked_sessions
        """
        try:
            from timem.workflows.retrieval_utils import SessionScorer
            
            scorer = SessionScorer()
            session_scores = scorer.calculate_session_scores(l1_results)
            
            if not session_scores:
                return {'ranked_sessions': []}
            
            # Build ranked_sessions list containing session_id, score and temporal_info
            ranked_sessions = []
            for session_id, score in session_scores:
                temporal_info = scorer.extract_temporal_info_from_session_id(session_id)
                ranked_sessions.append({
                    'session_id': session_id,
                    'score': score,
                    'temporal_info': temporal_info
                })
            
            self.logger.info(f"Multi-session analysis complete: {len(ranked_sessions)} sessions")
            return {'ranked_sessions': ranked_sessions}
            
        except Exception as e:
            self.logger.error(f"Multi-session analysis failed: {str(e)}")
            return {'ranked_sessions': []}
    
    async def _get_multi_session_memories(self, ranked_sessions: List[Dict[str, Any]], 
                                        state: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Retrieve L2, L3, L4 memories based on multiple sessions (deduplication sequential strategy)
        According to config: hybrid retrieval strategy needs L1 + L2 + L3 + L4
        
        Args:
            ranked_sessions: Session list sorted by score
            state: Workflow state
            
        Returns:
            Dictionary containing l2_memories, l3_memories, l4_memories
        """
        try:
            storage_manager = await self._get_storage_manager()
            
            l2_memories = []
            l3_memories = []
            l4_memories = []
            
            # Sets for deduplication
            seen_l2_sessions = set()
            seen_l3_dates = set()
            seen_l4_weeks = set()
            
            # Target counts (from config: L2=1, L3=1, L4=1)
            target_l2_count = self.l2_final_top_k
            target_l3_count = self.l3_final_top_k
            target_l4_count = self.l4_final_top_k
            
            self.logger.info("Start multi-session memory retrieval (deduplication sequential strategy)")
            
            for i, session_info in enumerate(ranked_sessions):
                session_id = session_info['session_id']
                temporal_info = session_info['temporal_info']
                
                self.logger.info(f"Processing Session {i+1}: {session_id}")
                
                # Retrieve L2 session memories (deduplicate)
                if len(l2_memories) < target_l2_count and session_id not in seen_l2_sessions:
                    try:
                        l2_result = await storage_manager.get_memories_by_session(
                            user_id=state.get("user_id", ""),
                            expert_id=state.get("expert_id", ""),
                            session_id=session_id,
                            layer="L2"
                        )
                        if l2_result:
                            l2_memories.extend(l2_result[:1])  # At most 1 per session
                            seen_l2_sessions.add(session_id)
                            self.logger.info(f"Retrieved L2 memory: {session_id} ({len(l2_result)} items)")
                        else:
                            self.logger.info(f"L2 memory empty: {session_id}")
                    except Exception as e:
                        self.logger.warning(f"Failed to retrieve L2 memory {session_id}: {e}")
                
                # Retrieve L3 daily report memories (deduplicate)
                if len(l3_memories) < target_l3_count:
                    date_key = temporal_info.get('date')
                    if date_key and date_key not in seen_l3_dates:
                        try:
                            # Convert date string to datetime object
                            date_obj = temporal_info.get('date_obj') or datetime.strptime(date_key, '%Y%m%d')
                            l3_result = await storage_manager.get_memories_by_date(
                                user_id=state.get("user_id", ""),
                                expert_id=state.get("expert_id", ""),
                                layer="L3",
                                date=date_obj
                            )
                            if l3_result:
                                l3_memories.extend(l3_result[:1])  # At most 1 per date
                                seen_l3_dates.add(date_key)
                                self.logger.info(f"Retrieved L3 memory: {date_key} ({len(l3_result)} items)")
                            else:
                                self.logger.info(f"L3 memory empty: {date_key}")
                        except Exception as e:
                            self.logger.warning(f"Failed to retrieve L3 memory {date_key}: {e}")
                
                # Retrieve L4 weekly report memories (deduplicate)
                if len(l4_memories) < target_l4_count:
                    week_start = temporal_info.get('week_start')
                    if week_start:
                        week_key = week_start.strftime('%Y-%m-%d') if hasattr(week_start, 'strftime') else str(week_start)
                        if week_key not in seen_l4_weeks:
                            try:
                                l4_result = await storage_manager.get_memories_by_week(
                                    user_id=state.get("user_id", ""),
                                    expert_id=state.get("expert_id", ""),
                                    layer="L4",
                                    week_start=week_start
                                )
                                if l4_result:
                                    l4_memories.extend(l4_result[:1])  # At most 1 per week
                                    seen_l4_weeks.add(week_key)
                                    self.logger.info(f"Retrieved L4 memory: {week_key} ({len(l4_result)} items)")
                                else:
                                    self.logger.info(f"L4 memory empty: {week_key}")
                            except Exception as e:
                                self.logger.warning(f"Failed to retrieve L4 memory {week_key}: {e}")
                
                # If target count reached, end early
                if (len(l2_memories) >= target_l2_count and 
                    len(l3_memories) >= target_l3_count and 
                    len(l4_memories) >= target_l4_count):
                    self.logger.info("Target memory count reached, ending early")
                    break
            
            # Statistics
            final_l2_count = len(l2_memories)
            final_l3_count = len(l3_memories)
            final_l4_count = len(l4_memories)
            
            self.logger.info(f"Multi-session memory retrieval complete:")
            self.logger.info(f"   L2 memories: {final_l2_count}/{target_l2_count} (dedup sessions: {len(seen_l2_sessions)})")
            self.logger.info(f"   L3 memories: {final_l3_count}/{target_l3_count} (dedup dates: {len(seen_l3_dates)})")
            self.logger.info(f"   L4 memories: {final_l4_count}/{target_l4_count} (dedup weeks: {len(seen_l4_weeks)})")
            
            return {
                'l2_memories': l2_memories,
                'l3_memories': l3_memories,
                'l4_memories': l4_memories,
                'l2_sessions_used': list(seen_l2_sessions),
                'l3_dates_used': list(seen_l3_dates),
                'l4_weeks_used': list(seen_l4_weeks)
            }
            
        except Exception as e:
            self.logger.error(f"Multi-session memory retrieval failed: {str(e)}")
            return {'l2_memories': [], 'l3_memories': [], 'l4_memories': []}
    
    def _hierarchical_time_sort(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Sort results by layer and time
        
        Sorting rules:
        1. Group by layer: L1, L2, L3, L4, L5
        2. Sort by time within each layer
        3. Final order: all L1 + all L2 + all L3 + all L4 + all L5
        """
        try:
            # Fix: group by layer (include L5)
            l1_results = [r for r in results if r.get("level") == "L1"]
            l2_results = [r for r in results if r.get("level") == "L2"]
            l3_results = [r for r in results if r.get("level") == "L3"]
            l4_results = [r for r in results if r.get("level") == "L4"]
            l5_results = [r for r in results if r.get("level") == "L5"]
            
            # Sort by time within each layer
            l1_results.sort(key=lambda x: self._extract_memory_timestamp(x))
            l2_results.sort(key=lambda x: self._extract_memory_timestamp(x))
            l3_results.sort(key=lambda x: self._extract_memory_timestamp(x))
            l4_results.sort(key=lambda x: self._extract_memory_timestamp(x))
            l5_results.sort(key=lambda x: self._extract_memory_timestamp(x))
            
            # Fix: combine all layers (include L5)
            final_results = l1_results + l2_results + l3_results + l4_results + l5_results
            
            self.logger.info(f"Layer sorting complete: L1={len(l1_results)}, L2={len(l2_results)}, "
                           f"L3={len(l3_results)}, L4={len(l4_results)}, L5={len(l5_results)}")
            
            return final_results
            
        except Exception as e:
            self.logger.error(f"Layer sorting failed: {e}")
            return results  # Return original results
    
    def _apply_quality_control(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Apply quality control and weight adjustment
        
        Ensure:
        1. L1 fact information dominance
        2. L3, L4 as concept supplements with lower weights
        3. Remove possible low-quality memories
        """
        try:
            controlled_results = []
            
            for result in results:
                level = result.get("level", "L1")
                
                # Set layer weights
                if level == "L1":
                    result["hierarchy_weight"] = 1.0  # L1 dominant
                elif level == "L2":
                    result["hierarchy_weight"] = 0.8  # L2 support
                elif level == "L3":
                    result["hierarchy_weight"] = 0.3  # L3 concept supplement
                elif level == "L4":
                    result["hierarchy_weight"] = 0.2  # L4 weekly supplement
                elif level == "L5":
                    result["hierarchy_weight"] = 0.15  # L5 monthly supplement
                else:
                    result["hierarchy_weight"] = 0.1  # Other layers
                
                # Adjust fused score
                original_score = result.get("fused_score", 0.5)
                result["adjusted_score"] = original_score * result["hierarchy_weight"]
                
                # Quality filtering: keep all L1 memories, L3/L4 need minimum relevance
                if level == "L1":
                    controlled_results.append(result)
                elif level == "L2":
                    controlled_results.append(result)
                elif level in ["L3", "L4", "L5"]:
                    # L3, L4, L5: bottom-up retrieval, must be included
                    title = result.get("title", "")
                    controlled_results.append(result)
                    self.logger.debug(f"Keep {level} memory: {title[:30]}...")
                else:
                    controlled_results.append(result)
            
            self.logger.info(f"Quality control complete: {len(results)} -> {len(controlled_results)}")
            return controlled_results
            
        except Exception as e:
            self.logger.error(f"Quality control failed: {e}")
            return results
    
    def _extract_memory_timestamp(self, memory: Dict[str, Any]) -> str:
        """Extract memory timestamp for sorting"""
        # Try multiple possible timestamp fields
        for field in ["created_at", "time_window_start", "timestamp", "time", "date"]:
            if field in memory and memory[field]:
                return str(memory[field])
        
        # If no timestamp found, return default value
        return "1970-01-01T00:00:00"
    
    def _analyze_result_distribution(self, results: List[Dict[str, Any]]) -> str:
        """Analyze result distribution"""
        try:
            level_counts = {}
            for result in results:
                level = result.get("level", "Unknown")
                level_counts[level] = level_counts.get(level, 0) + 1
            
            distribution = ", ".join([f"{level}={count}" for level, count in level_counts.items()])
            return distribution
        except:
            return "Analysis failed"
    
    def _build_final_result(self, original_state: Dict[str, Any], 
                          final_results: List[Dict[str, Any]],
                          session_analysis: Dict[str, Any],
                          execution_time: float) -> Dict[str, Any]:
        """Build final state result"""
        try:
            # Update original state
            updated_state = original_state.copy()
            
            # Explicitly preserve conversation mode config field (ensure LangGraph routing works correctly)
            # Use return_memories_only as standard config item
            updated_state["return_memories_only"] = original_state.get("return_memories_only", False)
            
            # Add retrieval results
            updated_state["ranked_results"] = final_results
            updated_state["total_memories_searched"] = len(final_results)
            updated_state["retrieval_time"] = execution_time
            
            # Add session analysis information
            if session_analysis.get('best_session_id'):
                updated_state["best_session_id"] = session_analysis['best_session_id']
                updated_state["best_session_score"] = session_analysis['best_session_score']
                updated_state["session_analysis"] = session_analysis
                updated_state["temporal_info"] = session_analysis.get('temporal_info', {})
            
            # Add strategy performance metrics
            if "strategy_performance" not in updated_state:
                updated_state["strategy_performance"] = {}
            updated_state["strategy_performance"]["hybrid_retrieval"] = execution_time
            
            # Add retrieval metadata
            # Add retrieval metadata and layer statistics
            updated_state["retrieval_metadata"] = {
                "strategy_name": self.strategy_name,
                "strategy_description": self.strategy_config.get("description", ""),
                "time_associated": True,
                "session_based": True,
                "levels_included": list(set(r.get("level") for r in final_results if r.get("level"))),
                "retrieved_counts": {
                    "L1": len([m for m in final_results if m.get("level") == "L1"]),
                    "L2": len([m for m in final_results if m.get("level") == "L2"]),
                    "L3": len([m for m in final_results if m.get("level") == "L3"]),
                    "L4": len([m for m in final_results if m.get("level") == "L4"]),
                    "L5": len([m for m in final_results if m.get("level") == "L5"]),
                }
            }
            
            # Ensure no error flag
            if not updated_state.get("errors"):
                updated_state["retrieval_success"] = True
            
            return updated_state
            
        except Exception as e:
            self.logger.error(f"Failed to build final result: {e}")
            # Return basic result
            original_state["ranked_results"] = final_results
            original_state["errors"] = original_state.get("errors", []) + [f"Failed to build result: {str(e)}"]
            return original_state
    
    async def _direct_high_level_retrieval(self, state: Dict[str, Any], 
                                           llm_keywords: List[str]) -> Dict[str, Any]:
        """
        Direct retrieval of high-level memories (L2-L5), no L1 starting point
        (Same implementation as SimpleRetriever)
        """
        import time
        start_time = time.time()
        
        self.logger.info(f"Direct high-level retrieval mode: {self.enabled_layers}")
        
        try:
            all_results = []
            seen_ids = set()
            
            # Iterate through each layer in enabled_layers
            for layer in self.enabled_layers:
                layer_limit = self.strategy_config.get('final_limits', {}).get(layer, 10)
                
                if layer_limit == 0:
                    self.logger.info(f"Skipping {layer} (limit=0)")
                    continue
                
                self.logger.info(f"Searching {layer} level memories (target {layer_limit} items)")
                
                # Use hybrid retrieval
                layer_results = await self._retrieve_single_level(
                    state=state,
                    level=layer,
                    llm_keywords=llm_keywords,
                    top_k=layer_limit
                )
                
                # Remove duplicates and add
                added = 0
                for mem in layer_results:
                    mem_id = mem.get('id') or mem.get('memory_id')
                    if mem_id and mem_id not in seen_ids:
                        all_results.append(mem)
                        seen_ids.add(mem_id)
                        added += 1
                
                self.logger.info(f"{layer} search complete: obtained {len(layer_results)} items, added {added} items (after deduplication)")
            
            # Sort by time (reuse base class method)
            final_results = sorted(all_results, key=lambda x: x.get('timestamp', ''), reverse=True)
            
            # Build result
            execution_time = time.time() - start_time
            session_analysis = {
                'best_session_id': None,
                'best_session_score': 0.0,
                'retrieval_mode': 'direct_high_level'
            }
            
            result = self._build_final_result(state, final_results, session_analysis, execution_time)
            
            self.logger.info(f"Direct high-level retrieval complete: {len(final_results)} items, took {execution_time:.2f}s")
            for layer in self.enabled_layers:
                layer_count = len([r for r in final_results if r.get('level') == layer])
                if layer_count > 0:
                    self.logger.info(f"   {layer}: {layer_count} items")
            
            return result
            
        except Exception as e:
            error_msg = f"Direct high-level retrieval failed: {str(e)}"
            self.logger.error(error_msg)
            state["errors"] = state.get("errors", []) + [error_msg]
            state["needs_retry"] = True
            state["retry_reason"] = error_msg
            return state
    
    async def _retrieve_single_level(self, state: Dict[str, Any], level: str, 
                                     llm_keywords: List[str], top_k: int) -> List[Dict[str, Any]]:
        """Retrieve single level memories (using hybrid retrieval)"""
        try:
            # Convert state format
            retrieval_state = self._dict_to_state(state)
            
            # Directly call BM25 and semantic search, then fuse (using correct parameters)
            bm25_results = await self._execute_bm25_search(
                retrieval_state,  # First parameter: RetrievalState
                llm_keywords,     # Second parameter: keyword list
                level             # Third parameter: layer
            )
            
            semantic_results = await self._execute_semantic_search(
                retrieval_state,  # First parameter: RetrievalState
                level             # Second parameter: layer
            )
            
            # Fuse results (using weighted fusion method)
            fused_results = await self._weighted_fusion(
                bm25_results, 
                semantic_results, 
                retrieval_state
            )
            
            return fused_results[:top_k]
            
        except Exception as e:
            self.logger.error(f"Failed to retrieve {level}: {e}")
            return []
    
    def _create_empty_result(self, original_state: Dict[str, Any]) -> Dict[str, Any]:
        """Create empty result"""
        updated_state = original_state.copy()
        updated_state["ranked_results"] = []
        updated_state["total_memories_searched"] = 0
        updated_state["retrieval_time"] = 0.0
        updated_state["retrieval_success"] = False
        return updated_state


# Factory function
def create_hybrid_retriever(**kwargs) -> HybridRetriever:
    """
    Factory function: create HybridRetriever instance
    
    Args:
        **kwargs: parameters passed to constructor
        
    Returns:
        HybridRetriever instance
    """
    return HybridRetriever(**kwargs)