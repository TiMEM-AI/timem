"""
Result Fusion Node

Responsible for fusing results from multiple retrieval strategies, performing deduplication and score calculation.
"""

from typing import Dict, List, Any, Optional, Set

from timem.workflows.retrieval_state import RetrievalState, RetrievalStateValidator
from timem.utils.logging import get_logger

logger = get_logger(__name__)


class ResultsFuser:
    """Result Fusion Node"""
    
    def __init__(self, state_validator: Optional[RetrievalStateValidator] = None):
        """
        Initialize result fuser
        
        Args:
            state_validator: State validator, creates new instance if None
        """
        self.state_validator = state_validator or RetrievalStateValidator()
        self.logger = get_logger(__name__)
        
        # Strategy weight configuration
        self.strategy_weights = {
            "semantic": 1.0,
            "temporal": 0.8,
            "keyword": 0.6,
            "hierarchical": 0.9,
            "contextual": 0.7
        }
    
    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run result fusion
        
        Args:
            state: Workflow state dictionary
            
        Returns:
            Updated state dictionary
        """
        try:
            # Convert to RetrievalState object
            retrieval_state = self._dict_to_state(state)
            
            self.logger.info("Start result fusion")
            
            # Step 1: Collect all retrieval results
            all_results = self._collect_all_results(retrieval_state)
            
            # Step 2: Deduplicate results
            deduplicated_results = self._deduplicate_results(all_results)
            
            # Step 3: Calculate fused scores
            fused_results = self._calculate_fused_scores(deduplicated_results, retrieval_state)
            
            # Step 4: Record strategy performance
            strategy_performance = self._calculate_strategy_performance(retrieval_state)
            
            # Step 5: Update state
            retrieval_state.fused_results = fused_results
            retrieval_state.strategy_performance = strategy_performance
            
            self.logger.info(f"Result fusion complete: {len(fused_results)} deduplicated results")
            
            return self._state_to_dict(retrieval_state)
            
        except Exception as e:
            error_msg = f"Result fusion failed: {str(e)}"
            self.logger.error(error_msg)
            state["errors"] = state.get("errors", []) + [error_msg]
            return state
    
    def _collect_all_results(self, state: RetrievalState) -> List[Dict[str, Any]]:
        """Collect all retrieval results"""
        all_results = []
        
        # Collect results from each strategy
        result_sources = [
            (state.semantic_results, "semantic"),
            (state.temporal_results, "temporal"),
            (state.keyword_results, "keyword"),
            (state.hierarchical_results, "hierarchical"),
            (state.contextual_results, "contextual")
        ]
        
        for results, source in result_sources:
            for result in results:
                # Ensure result has source marker
                if "retrieval_source" not in result:
                    result["retrieval_source"] = source
                all_results.append(result)
        
        self.logger.info(f"Collected {len(all_results)} raw results")
        return all_results
    
    def _deduplicate_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Deduplicate retrieval results"""
        seen_ids: Set[str] = set()
        deduplicated = []
        duplicate_count = 0
        
        for result in results:
            result_id = result.get("id", "")
            
            if not result_id:
                # Skip if no ID or generate temporary ID
                self.logger.warning("Found result without ID, skipping")
                continue
            
            if result_id not in seen_ids:
                seen_ids.add(result_id)
                deduplicated.append(result)
            else:
                # Record duplicates, may need to merge strategy info
                duplicate_count += 1
                self._merge_duplicate_result(deduplicated, result, result_id)
        
        self.logger.info(f"Deduplication complete: {len(deduplicated)} unique results, {duplicate_count} duplicates")
        return deduplicated
    
    def _merge_duplicate_result(self, deduplicated: List[Dict[str, Any]], 
                               duplicate_result: Dict[str, Any], result_id: str):
        """Merge information from duplicate results"""
        # Find existing result
        for existing in deduplicated:
            if existing.get("id") == result_id:
                # Merge retrieval source info
                existing_sources = existing.get("retrieval_sources", [existing.get("retrieval_source", "")])
                new_source = duplicate_result.get("retrieval_source", "")
                
                if new_source and new_source not in existing_sources:
                    existing_sources.append(new_source)
                
                existing["retrieval_sources"] = existing_sources
                
                # Keep highest score
                existing_score = existing.get("retrieval_score", 0)
                new_score = duplicate_result.get("retrieval_score", 0)
                if new_score > existing_score:
                    existing["retrieval_score"] = new_score
                    existing["best_retrieval_source"] = new_source
                
                break
    
    def _calculate_fused_scores(self, results: List[Dict[str, Any]], 
                               state: RetrievalState) -> List[Dict[str, Any]]:
        """Calculate fused scores"""
        for result in results:
            # ✨ Fix: Ensure None converts to default value
            base_score = result.get("retrieval_score") or 0.5
            source = result.get("retrieval_source", "semantic")
            
            # Get strategy weight
            weight = self._get_strategy_weight(source, state)
            
            # Calculate layer weight (if exists)
            layer_weight = result.get("layer_weight") or 1.0  # ✨ Fix: None converts to 1.0
            
            # Calculate multi-source weight (if result from multiple strategies)
            sources = result.get("retrieval_sources", [source])
            multi_source_bonus = min(1.2, 1.0 + len(sources) * 0.1)  # Max 20% bonus
            
            # Calculate final fused score
            fused_score = base_score * weight * layer_weight * multi_source_bonus
            
            # Limit score range
            result["fused_score"] = min(1.0, max(0.0, fused_score))
            
            # Save score calculation info (for debugging)
            result["score_breakdown"] = {
                "base_score": base_score,
                "strategy_weight": weight,
                "layer_weight": layer_weight,
                "multi_source_bonus": multi_source_bonus,
                "final_score": result["fused_score"]
            }
        
        return results
    
    def _get_strategy_weight(self, source: str, state: RetrievalState) -> float:
        """Get strategy weight"""
        # First check weight config in retrieval parameters
        weight_key = f"{source}_weight"
        param_weight = state.retrieval_params.get(weight_key)
        
        if param_weight is not None:
            return param_weight
        
        # Use default weight
        return self.strategy_weights.get(source, 0.5)
    
    def _calculate_strategy_performance(self, state: RetrievalState) -> Dict[str, Any]:
        """Calculate strategy performance statistics"""
        performance = {
            "semantic": len(state.semantic_results),
            "temporal": len(state.temporal_results),
            "keyword": len(state.keyword_results),
            "hierarchical": len(state.hierarchical_results),
            "contextual": len(state.contextual_results),
            "fused_total": len(state.fused_results)
        }
        
        # Calculate strategy coverage
        total_unique_results = len(state.fused_results)
        if total_unique_results > 0:
            for strategy, count in performance.items():
                if strategy != "fused_total":
                    performance[f"{strategy}_coverage"] = count / total_unique_results
        
        # Calculate strategy efficiency (result quality)
        for strategy in ["semantic", "temporal", "keyword", "hierarchical", "contextual"]:
            strategy_results = getattr(state, f"{strategy}_results", [])
            if strategy_results:
                avg_score = sum(r.get("retrieval_score", 0) for r in strategy_results) / len(strategy_results)
                performance[f"{strategy}_avg_score"] = avg_score
        
        return performance
    
    def _dict_to_state(self, state_dict: Dict[str, Any]) -> RetrievalState:
        """Convert dictionary to RetrievalState object"""
        state = RetrievalState()
        
        # Copy existing fields
        for key, value in state_dict.items():
            if hasattr(state, key):
                setattr(state, key, value)
                
        return state
    
    def _state_to_dict(self, state: RetrievalState) -> Dict[str, Any]:
        """Convert RetrievalState object to dictionary"""
        state_dict = {}
        
        # Copy all fields
        for key, value in state.__dict__.items():
            state_dict[key] = value
                
        return state_dict
