"""
Simple Retriever - Bottom-Up Upgrade Version

Based on BottomUpRetrieverBase implementation, adding session scoring mechanism and L2 automatic association supplement:
1. Maintain original 80-90% high accuracy rate
2. L1 hybrid retrieval (BM25 keywords + Qdrant semantic retrieval)
3. Session scoring analysis to determine the most relevant session
4. Automatically associate L2 session memories corresponding to best session
5. Time-ordered combination of final results

Design principles:
- Backward compatible: maintain interface consistency with original SimpleRetriever
- Performance first: ensure no degradation of existing retrieval performance
- Progressive improvement: enhance functionality on existing success basis
"""

import time
from typing import Dict, List, Any, Optional

from timem.workflows.retrieval_nodes.bottom_up_retriever_base import BottomUpRetrieverBase
from timem.utils.logging import get_logger

logger = get_logger(__name__)


class SimpleRetriever(BottomUpRetrieverBase):
    """
    Simple Retriever - Bottom-Up Upgrade Version
    
    Improvements compared to original version:
    1. Inherit complete L1 hybrid retrieval logic from base class
    2. Automatically perform session scoring analysis
    3. Intelligently associate L2 memories of best session
    4. Maintain 80-90% high accuracy performance
    """
    
    def __init__(self, strategy_config: Optional[Dict[str, Any]] = None, **kwargs):
        """Initialize SimpleRetriever"""
        # First process strategy_config, then pass to parent class
        super().__init__(strategy_config=strategy_config, **kwargs)
        
        # Read layer_limits and final_limits from strategy config
        self.strategy_config = strategy_config or {}
        layer_limits = self.strategy_config.get('layer_limits', {})
        final_limits = self.strategy_config.get('final_limits', {})
        
        # 🆕 Read enabled layers list from config
        self.enabled_layers = self.strategy_config.get('layers', ['L1', 'L2', 'L5'])
        self.logger.info(f"Enabled layers: {self.enabled_layers}")
        
        # 🆕 Read whether to disable bottom-up mechanism from config
        self.disable_bottom_up = self.strategy_config.get('disable_bottom_up', False)
        if self.disable_bottom_up:
            self.logger.warning(f"⚠️ Bottom-up mechanism disabled, will only retrieve L1 memories")
        
        # Configure coarse and fine ranking limits for each layer
        self.l1_coarse_top_k = layer_limits.get('L1', 40)  # Coarse ranking count
        self.l1_final_top_k = final_limits.get('L1', 20)   # Fine ranking count  
        self.l2_final_top_k = final_limits.get('L2', 1)    # L2 count
        self.l5_final_top_k = final_limits.get('L5', 1)    # L5 count (monthly report)
        
        # Set strategy name for parent class
        self.strategy_name = 'simple'
        
        self.logger.info(f"Initialize SimpleRetriever - Bottom-Up Upgrade Version")
        self.logger.info(f"   Enabled layers: {self.enabled_layers}")
        self.logger.info(f"   L1 coarse: {self.l1_coarse_top_k} items, L1 fine: {self.l1_final_top_k} items, L2: {self.l2_final_top_k} items, L5: {self.l5_final_top_k} items")
    
    def get_retriever_name(self) -> str:
        """Get retriever name"""
        return "SimpleRetriever"
    
    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run simple retrieval (LangGraph node standard interface)
        
        Implement bottom-up strategy:
        1. L1 hybrid retrieval (top5)
        2. Session scoring analysis
        3. L2 memory association of best session
        4. Time-ordered combination
        
        Args:
            state: workflow state dictionary
            
        Returns:
            updated state dictionary
        """
        try:
            start_time = time.time()
            self.logger.info("🚀 Start SimpleRetriever retrieval process")
            
            # Validate input
            question = state.get("question", "").strip()
            if not question:
                error_msg = "Question cannot be empty"
                self.logger.error(error_msg)
                state["errors"] = state.get("errors", []) + [error_msg]
                return state
            
            llm_keywords = state.get("key_entities", [])
            self.logger.info(f"Retrieved LLM keywords: {llm_keywords}")
            
            # Check if L1 is in enabled_layers
            if 'L1' not in self.enabled_layers:
                self.logger.warning(f"L1 not in enabled_layers ({self.enabled_layers}), skipping L1 retrieval, executing direct high-level retrieval")
                # Directly retrieve memories in enabled_layers (no L1 starting point and bottom-up)
                return await self._direct_high_level_retrieval(state, llm_keywords)
            
            # Step 1: L1 hybrid retrieval (inherit base class success logic) - coarse then fine ranking
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
            
            # Step 2: Session scoring analysis
            self.logger.info("Step 2: Session scoring analysis")
            session_analysis = self.analyze_l1_for_session(l1_results)
            
            best_session_id = session_analysis.get('best_session_id')
            if not best_session_id:
                error_msg = "No valid session found"
                self.logger.warning(error_msg)
                state["errors"] = state.get("errors", []) + [error_msg]
                state["needs_retry"] = True
                state["retry_reason"] = error_msg
                return state
            
            # Step 3: Multi-starting-point chain traversal to retrieve parent memories (by configured layers)
            self.logger.info(f"Step 3: Multi-starting-point chain traversal for parent memories (layers: {self.enabled_layers})")
            
            # Check if bottom-up mechanism is disabled
            if self.disable_bottom_up:
                self.logger.warning("Bottom-up mechanism disabled, skipping parent memory retrieval")
                parent_memories = {}
            else:
                # Dynamically build target_levels and target_counts based on configured layers
                target_levels = [layer for layer in self.enabled_layers if layer != 'L1']  # Exclude L1 (already retrieved)
                target_counts = {}
                for layer in target_levels:
                    if layer == 'L2':
                        target_counts[layer] = self.l2_final_top_k
                    elif layer == 'L5':
                        target_counts[layer] = self.l5_final_top_k
                    else:
                        # For other layers, read from final_limits
                        target_counts[layer] = self.strategy_config.get('final_limits', {}).get(layer, 1)
                
                self.logger.info(f"Target levels and counts: {target_counts}")
                
                # If no other layers need retrieval, skip this step
                if not target_levels:
                    self.logger.info("Only L1 enabled, skipping parent memory retrieval")
                    parent_memories = {}
                else:
                    # Engineering-level fix: force bottom-level memory retrieval, raise exception on failure
                    try:
                        parent_memories = await self.get_parent_memories_by_chain(
                            l1_results, target_levels, target_counts, state
                        )
                    except Exception as e:
                        # Bottom-up has already retried 3 times and still failed, this is a critical error
                        error_msg = f"Bottom-up chain traversal completely failed (auto-retried 3 times): {e}"
                        self.logger.error(error_msg)
                        state["errors"] = state.get("errors", []) + [error_msg]
                        state["needs_retry"] = True
                        state["retry_reason"] = "bottom_up_chain_failed"
                        # Engineering fix: do not allow returning only L1, must mark as failed
                        raise Exception(error_msg)
            
            # Engineering-level fix: dynamically validate each layer retrieval (only when bottom-up not disabled)
            if not self.disable_bottom_up:
                for layer in target_levels:
                    layer_memories = parent_memories.get(layer, [])
                    expected_count = target_counts.get(layer, 0)
                    
                    if not layer_memories and expected_count > 0:
                        # No parent memory retrieved for this layer, log warning
                        warning_msg = f"Bottom-up did not retrieve {layer} parent memories (expected {expected_count}), may be missing parent-child relationships in database"
                        self.logger.warning(warning_msg)
                        state["warnings"] = state.get("warnings", []) + [warning_msg]
                    else:
                        self.logger.info(f"Successfully retrieved {layer} memories: {len(layer_memories)} items")
            
            # Step 4: Combine and deduplicate results
            self.logger.info("Step 4: Combine and deduplicate results")
            
            # Fix: global deduplication logic, avoid qdrant_semantic and bottom_up duplicates
            all_results = []
            seen_ids = set()
            
            # Add L1 memories (highest priority)
            for mem in l1_results:
                mem_id = mem.get('id') or mem.get('memory_id')
                if mem_id and mem_id not in seen_ids:
                    all_results.append(mem)
                    seen_ids.add(mem_id)
            
            # Dynamically add each layer parent memories (deduplication) (only when bottom-up not disabled)
            if not self.disable_bottom_up:
                for layer in target_levels:
                    layer_memories = parent_memories.get(layer, [])
                    expected_count = target_counts.get(layer, 0)
                    
                    if layer_memories:
                        added_count = 0
                        duplicate_count = 0
                        for memory in layer_memories:
                            mem_id = memory.get('id') or memory.get('memory_id')
                            if mem_id and mem_id not in seen_ids:
                                all_results.append(memory)
                                seen_ids.add(mem_id)
                                added_count += 1
                            elif mem_id:
                                duplicate_count += 1
                                self.logger.debug(f"  Skipped duplicate {layer}: {memory.get('title', 'untitled')[:40]}...")
                        
                        self.logger.info(f"Successfully associated {added_count} {layer} memories (target {expected_count}, skipped {duplicate_count} duplicates)")
                    else:
                        if expected_count > 0:
                            self.logger.warning(f"Did not associate any {layer} parent memories")
            else:
                self.logger.info("Bottom-up disabled, using only L1 memories")
            
            # Time-ordered sorting
            final_results = self._time_ordered_sort(all_results)
            
            # Build final result
            execution_time = time.time() - start_time
            result = self._build_final_result(state, final_results, session_analysis, execution_time)
            
            self.logger.info(f"SimpleRetriever completed: {len(final_results)} results, "
                           f"elapsed {execution_time:.2f}s")
            self.logger.info(f"   Result distribution: L1={len([r for r in final_results if r.get('level') == 'L1'])}, "
                           f"L2={len([r for r in final_results if r.get('level') == 'L2'])}")
            
            return result
            
        except Exception as e:
            error_msg = f"SimpleRetriever execution failed: {str(e)}"
            self.logger.error(error_msg)
            state["errors"] = state.get("errors", []) + [error_msg]
            return state
    
    def _time_ordered_sort(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Sort results by time

        Sorting rules:
        1. Sort each enabled layer by time
        2. Combine in layer order: L1 → L2 → L3 → L4 → L5

        Fixed to respect enabled_layers configuration
        """
        try:
            # Use self.enabled_layers to determine which layers to include
            layer_order = [layer for layer in ['L1', 'L2', 'L3', 'L4', 'L5']
                          if layer in self.enabled_layers]

            # Separate each layer memories
            layer_results = {}
            for layer in layer_order:
                layer_results[layer] = [r for r in results if r.get("level") == layer]
                layer_results[layer].sort(key=lambda x: self._extract_memory_timestamp(x))

            # Combine in order
            final_results = []
            for layer in layer_order:
                final_results.extend(layer_results[layer])

            # Log results
            result_counts = {layer: len(layer_results.get(layer, [])) for layer in layer_order}
            self.logger.info(f"Time sorting completed (enabled_layers={self.enabled_layers}): {result_counts}")

            return final_results

        except Exception as e:
            self.logger.error(f"Time sorting failed: {e}")
            return results  # Return original results
    
    def _extract_memory_timestamp(self, memory: Dict[str, Any]) -> str:
        """Extract memory timestamp for sorting"""
        # Try multiple possible timestamp fields
        for field in ["created_at", "time_window_start", "timestamp", "time", "date"]:
            if field in memory and memory[field]:
                return str(memory[field])
        
        # If no timestamp found, return default value
        return "1970-01-01T00:00:00"
    
    async def _direct_high_level_retrieval(self, state: Dict[str, Any], 
                                           llm_keywords: List[str]) -> Dict[str, Any]:
        """
        Direct high-level memory retrieval (L2-L5), without L1 starting point
        
        For scenarios like E2.4/E2.5:
        - No L1 in configuration
        - Directly retrieve L2/L3/L4/L5 layer memories
        - Use hybrid retrieval (BM25 + semantic)
        - Sort by time
        
        Args:
            state: Current state
            llm_keywords: LLM keywords
            
        Returns:
            Updated state with retrieval results
        """
        import time
        start_time = time.time()
        
        self.logger.info(f"Direct high-level retrieval mode: {self.enabled_layers}")
        
        try:
            all_results = []
            seen_ids = set()
            
            # Iterate through each layer in enabled_layers
            for layer in self.enabled_layers:
                # Get target count for this layer
                layer_limit = self.strategy_config.get('final_limits', {}).get(layer, 10)
                
                if layer_limit == 0:
                    self.logger.info(f"Skipping {layer} (limit=0)")
                    continue
                
                self.logger.info(f"Retrieving {layer} layer memories (target {layer_limit} items)")
                
                # Use hybrid retrieval (BM25 + semantic)
                layer_results = await self._retrieve_single_level(
                    state=state,
                    level=layer,
                    llm_keywords=llm_keywords,
                    top_k=layer_limit
                )
                
                # Deduplicate and add
                added = 0
                for mem in layer_results:
                    mem_id = mem.get('id') or mem.get('memory_id')
                    if mem_id and mem_id not in seen_ids:
                        all_results.append(mem)
                        seen_ids.add(mem_id)
                        added += 1
                
                self.logger.info(f"{layer} retrieval completed: obtained {len(layer_results)}, added {added} (after deduplication)")
            
            # Sort by time
            final_results = self._time_ordered_sort(all_results)
            
            # Build result (no session analysis)
            execution_time = time.time() - start_time
            
            # Build simplified session_analysis (placeholder)
            session_analysis = {
                'best_session_id': None,
                'best_session_score': 0.0,
                'retrieval_mode': 'direct_high_level'
            }
            
            result = self._build_final_result(state, final_results, session_analysis, execution_time)
            
            self.logger.info(f"Direct high-level retrieval completed: {len(final_results)} results, elapsed {execution_time:.2f}s")
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
        """
        Retrieve memories for a single layer (using hybrid retrieval)
        
        Args:
            state: Current state
            level: Layer (L2/L3/L4/L5)
            llm_keywords: LLM keywords
            top_k: Number of items to retrieve
            
        Returns:
            Retrieval results for this layer
        """
        try:
            # Convert state format
            retrieval_state = self._dict_to_state(state)
            
            # Directly call BM25 and semantic retrieval, then fuse (using correct parameters)
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
            
            # Fine ranking take top_k
            return fused_results[:top_k]
            
        except Exception as e:
            self.logger.error(f"Retrieving {level} failed: {e}")
            return []
    
    def _build_final_result(self, original_state: Dict[str, Any], 
                          final_results: List[Dict[str, Any]],
                          session_analysis: Dict[str, Any],
                          execution_time: float) -> Dict[str, Any]:
        """Build final state result"""
        try:
            # Update original state
            updated_state = original_state.copy()
            
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
            updated_state["strategy_performance"]["simple_retrieval"] = execution_time
            
            # Add retrieval metadata
            updated_state["retrieval_metadata"] = {
                "strategy_name": self.strategy_name,
                "strategy_description": self.strategy_config.get("description", ""),
                "time_associated": True,
                "session_based": True,
                "levels_included": list(set(r.get("level") for r in final_results if r.get("level"))),
                "retrieved_counts": {
                    "L1": len([m for m in final_results if m.get("level") == "L1"]),
                    "L2": len([m for m in final_results if m.get("level") == "L2"]),
                    "L5": len([m for m in final_results if m.get("level") == "L5"]),
                }
            }
            
            # Ensure no error markers
            if not updated_state.get("errors"):
                updated_state["retrieval_success"] = True
            
            return updated_state
            
        except Exception as e:
            self.logger.error(f"Build final result failed: {e}")
            # Return basic result
            original_state["ranked_results"] = final_results
            original_state["errors"] = original_state.get("errors", []) + [f"Build result failed: {str(e)}"]
            return original_state
    
    def _create_empty_result(self, original_state: Dict[str, Any]) -> Dict[str, Any]:
        """Create empty result"""
        updated_state = original_state.copy()
        updated_state["ranked_results"] = []
        updated_state["total_memories_searched"] = 0
        updated_state["retrieval_time"] = 0.0
        updated_state["retrieval_success"] = False
        return updated_state


# For backward compatibility, can provide an adapter function
def create_simple_retriever(**kwargs) -> SimpleRetriever:
    """
    Factory function: create SimpleRetriever instance
    
    Args:
        **kwargs: Parameters to pass to constructor
        
    Returns:
        SimpleRetriever instance
    """
    return SimpleRetriever(**kwargs)