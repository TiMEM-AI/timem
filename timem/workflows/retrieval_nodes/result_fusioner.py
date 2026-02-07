"""
Result fusion node

Responsible for fusing and deduplicating results from multiple retrieval strategies,
calculating comprehensive scores
"""

from typing import Dict, List, Any, Optional

from timem.workflows.retrieval_state import RetrievalState, RetrievalStateValidator
from timem.utils.logging import get_logger

logger = get_logger(__name__)


class ResultFusioner:
    """Result fusion node - reference memory_generation node design"""
    
    def __init__(self, 
                 state_validator: Optional[RetrievalStateValidator] = None):
        """
        Initialize result fusion node
        
        Args:
            state_validator: State validator
        """
        self.state_validator = state_validator or RetrievalStateValidator()
        self.logger = get_logger(__name__)
    
    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run result fusion node
        
        Args:
            state: Current state dictionary
            
        Returns:
            Updated state dictionary
        """
        try:
            self.logger.info("🔀 Start result fusion")
            
            # Convert dictionary to RetrievalState object
            retrieval_state = RetrievalState(**state)
            
            # Collect all retrieval results
            all_results = self._collect_all_results(retrieval_state)
            
            # Deduplicate results
            deduplicated_results = self._deduplicate_results(all_results)
            
            # Calculate fused scores
            fused_results = self._calculate_fused_scores(deduplicated_results, retrieval_state)
            
            # Update state
            retrieval_state.fused_results = fused_results
            
            # Record strategy performance statistics
            retrieval_state.strategy_performance = self._calculate_strategy_performance(retrieval_state)
            
            self.logger.info(f"🔀 Result fusion complete: {len(fused_results)} deduplicated results")
            
            # Convert back to dictionary format and return
            return retrieval_state.to_dict()
            
        except Exception as e:
            self.logger.error(f"❌ Result fusion failed: {str(e)}")
            state["errors"] = state.get("errors", []) + [f"Result fusion failed: {str(e)}"]
            state["success"] = False
            return state
    
    def _collect_all_results(self, state: RetrievalState) -> List[Dict[str, Any]]:
        """Collect all retrieval results"""
        all_results = []
        
        # Collect results from each strategy
        result_sources = [
            ("semantic", state.semantic_results),
            ("temporal", state.temporal_results),
            ("keyword", state.keyword_results),
            ("hierarchical", state.hierarchical_results),
            ("contextual", state.contextual_results)
        ]
        
        for source_name, results in result_sources:
            if results:
                self.logger.info(f"Collecting {source_name} retrieval results: {len(results)} items")
                all_results.extend(results)
        
        self.logger.info(f"Total collected {len(all_results)} raw results")
        return all_results
    
    def _deduplicate_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Deduplicate retrieval results"""
        seen_ids = set()
        deduplicated = []
        duplicate_count = 0
        
        for result in results:
            result_id = result.get("id", "")
            if result_id and result_id not in seen_ids:
                seen_ids.add(result_id)
                deduplicated.append(result)
            else:
                duplicate_count += 1
                # If duplicate result, try to merge information
                self._merge_duplicate_result(result, deduplicated, result_id)
        
        self.logger.info(f"Deduplication complete: removed {duplicate_count} duplicate results, kept {len(deduplicated)} items")
        return deduplicated
    
    def _merge_duplicate_result(self, duplicate_result: Dict[str, Any], 
                              existing_results: List[Dict[str, Any]], 
                              result_id: str) -> None:
        """Merge information from duplicate results"""
        try:
            # Find existing result
            existing_result = None
            for result in existing_results:
                if result.get("id") == result_id:
                    existing_result = result
                    break
            
            if existing_result is None:
                return
            
            # Merge retrieval source information
            existing_sources = existing_result.get("retrieval_sources", [])
            new_source = duplicate_result.get("retrieval_source", "")
            
            if new_source and new_source not in existing_sources:
                existing_sources.append(new_source)
                existing_result["retrieval_sources"] = existing_sources
            
            # Keep higher score
            existing_score = existing_result.get("retrieval_score", 0.0)
            new_score = duplicate_result.get("retrieval_score", 0.0)
            
            if new_score > existing_score:
                existing_result["retrieval_score"] = new_score
                existing_result["primary_source"] = new_source
            
            # Accumulate weighted scores
            existing_weighted = existing_result.get("weighted_score", 0.0)
            new_weighted = duplicate_result.get("weighted_score", 0.0)
            existing_result["weighted_score"] = max(existing_weighted, new_weighted)
            
        except Exception as e:
            self.logger.warning(f"Failed to merge duplicate results: {e}")
    
    def _calculate_fused_scores(self, results: List[Dict[str, Any]], 
                              state: RetrievalState) -> List[Dict[str, Any]]:
        """Calculate fused scores"""
        for result in results:
            try:
                # Get base information
                base_score = result.get("retrieval_score", 0.5)
                source = result.get("retrieval_source", "")
                weighted_score = result.get("weighted_score", base_score)
                
                # Get strategy weight
                weight_key = f"{source}_weight"
                strategy_weight = state.retrieval_params.get(weight_key, 0.5)
                
                # Get hierarchical weight
                level = result.get("level", "Unknown")
                hierarchical_weights = state.retrieval_params.get("hierarchical_layer_weights", {})
                layer_weight = hierarchical_weights.get(level, 1.0)
                
                # Multi-source bonus: if result comes from multiple retrieval strategies, give bonus
                retrieval_sources = result.get("retrieval_sources", [source] if source else [])
                multi_source_bonus = min(0.2, len(retrieval_sources) * 0.05)  # Max 20% bonus
                
                # Time freshness bonus
                freshness_bonus = self._calculate_freshness_bonus(result)
                
                # Content quality bonus
                quality_bonus = self._calculate_quality_bonus(result)
                
                # Calculate final fused score
                fused_score = (
                    weighted_score * strategy_weight * layer_weight * 
                    (1 + multi_source_bonus + freshness_bonus + quality_bonus)
                )
                
                # Ensure score is in reasonable range
                fused_score = max(0.0, min(1.0, fused_score))
                
                result["fused_score"] = fused_score
                result["score_components"] = {
                    "base_score": base_score,
                    "strategy_weight": strategy_weight,
                    "layer_weight": layer_weight,
                    "multi_source_bonus": multi_source_bonus,
                    "freshness_bonus": freshness_bonus,
                    "quality_bonus": quality_bonus
                }
                
            except Exception as e:
                self.logger.warning(f"Failed to calculate fused score: {e}")
                result["fused_score"] = result.get("retrieval_score", 0.5)
        
        return results
    
    def _calculate_freshness_bonus(self, result: Dict[str, Any]) -> float:
        """Calculate time freshness bonus"""
        try:
            from datetime import datetime, timedelta
            
            timestamp = result.get("timestamp")
            if not timestamp:
                return 0.0
            
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            
            now = datetime.now()
            age = (now - timestamp).total_seconds() / (24 * 3600)  # days
            
            # Newer memories get higher bonus
            if age <= 1:
                return 0.1      # Within 1 day: 10% bonus
            elif age <= 7:
                return 0.05     # Within 1 week: 5% bonus
            elif age <= 30:
                return 0.02     # Within 1 month: 2% bonus
            else:
                return 0.0      # Over 1 month: no bonus
            
        except Exception:
            return 0.0
    
    def _calculate_quality_bonus(self, result: Dict[str, Any]) -> float:
        """Calculate content quality bonus"""
        try:
            content = result.get("content", "")
            if not content:
                return 0.0
            
            # Content length bonus (moderate length is best)
            content_length = len(content)
            if 50 <= content_length <= 500:
                length_bonus = 0.05
            elif 500 < content_length <= 1000:
                length_bonus = 0.03
            else:
                length_bonus = 0.0
            
            # Structured content bonus (contains punctuation, etc.)
            structure_score = 0.0
            if "。" in content or "." in content:
                structure_score += 0.01
            if "?" in content or "？" in content:
                structure_score += 0.01
            if ":" in content or "：" in content:
                structure_score += 0.01
            
            return length_bonus + structure_score
            
        except Exception:
            return 0.0
    
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
        
        # Calculate average score for each strategy
        for strategy_name in ["semantic", "temporal", "keyword", "hierarchical", "contextual"]:
            results = getattr(state, f"{strategy_name}_results", [])
            if results:
                avg_score = sum(r.get("retrieval_score", 0.0) for r in results) / len(results)
                performance[f"{strategy_name}_avg_score"] = round(avg_score, 3)
            else:
                performance[f"{strategy_name}_avg_score"] = 0.0
        
        # Calculate average score after fusion
        if state.fused_results:
            fused_avg_score = sum(r.get("fused_score", 0.0) for r in state.fused_results) / len(state.fused_results)
            performance["fused_avg_score"] = round(fused_avg_score, 3)
        else:
            performance["fused_avg_score"] = 0.0
        
        return performance
