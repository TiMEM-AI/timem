"""
Result ranking node

Responsible for intelligently ranking fused retrieval results,
applying multiple ranking strategies to optimize result quality
"""

from typing import Dict, List, Any, Optional

from timem.workflows.retrieval_state import RetrievalState, RetrievalStateValidator
from timem.utils.logging import get_logger

logger = get_logger(__name__)


class ResultRanker:
    """Result ranking node - reference memory_generation node design"""
    
    def __init__(self, 
                 state_validator: Optional[RetrievalStateValidator] = None):
        """
        Initialize result ranking node
        
        Args:
            state_validator: State validator
        """
        self.state_validator = state_validator or RetrievalStateValidator()
        self.logger = get_logger(__name__)
    
    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run result ranking node
        
        Args:
            state: Current state dictionary
            
        Returns:
            Updated state dictionary
        """
        try:
            self.logger.info(" Start re-ranking results")
            
            # Convert dictionary to RetrievalState object
            retrieval_state = RetrievalState(**state)
            
            if not retrieval_state.fused_results:
                self.logger.info(" Skip result ranking: no fused results")
                retrieval_state.ranked_results = []
                return retrieval_state.to_dict()
            
            # Apply multiple ranking strategies
            ranked_results = await self._rank_results(retrieval_state)
            
            # Apply diversity optimization
            diversified_results = self._apply_diversity_optimization(ranked_results, retrieval_state)
            
            # Limit final result count
            final_limit = retrieval_state.retrieval_params.get("final_result_limit", 10)
            final_results = diversified_results[:final_limit]
            
            retrieval_state.ranked_results = final_results
            
            self.logger.info(f" Result ranking complete: Top {len(final_results)} results")
            
            # Log ranking details (debug info)
            self._log_ranking_details(final_results)
            
            # Convert back to dictionary format and return
            return retrieval_state.to_dict()
            
        except Exception as e:
            self.logger.error(f" Result ranking failed: {str(e)}")
            state["errors"] = state.get("errors", []) + [f"Result ranking failed: {str(e)}"]
            state["success"] = False
            return state
    
    async def _rank_results(self, state: RetrievalState) -> List[Dict[str, Any]]:
        """Rank results"""
        results = state.fused_results.copy()
        
        # Apply multiple ranking factors
        for result in results:
            try:
                final_score = self._calculate_final_ranking_score(result, state)
                result["final_ranking_score"] = final_score
                
            except Exception as e:
                self.logger.warning(f"Failed to calculate final ranking score: {e}")
                result["final_ranking_score"] = result.get("fused_score", 0.5)
        
        # Sort by final ranking score (ensure None values are converted to 0.0)
        ranked_results = sorted(
            results,
            key=lambda x: x.get("final_ranking_score") or 0.0,  
            reverse=True
        )
        
        return ranked_results
    
    def _calculate_final_ranking_score(self, result: Dict[str, Any], state: RetrievalState) -> float:
        """Calculate final ranking score"""
        try:
            # Base fused score (ensure None values are converted to default value)
            base_score = result.get("fused_score") or 0.5  
            
            # Query relevance bonus
            query_relevance_bonus = self._calculate_query_relevance_bonus(result, state)
            
            # Level priority bonus
            level_priority_bonus = self._calculate_level_priority_bonus(result, state)
            
            # Multi-strategy consistency bonus
            consistency_bonus = self._calculate_consistency_bonus(result)
            
            # Content completeness bonus
            completeness_bonus = self._calculate_completeness_bonus(result)
            
            # Calculate final score
            final_score = base_score * (
                1 + query_relevance_bonus + level_priority_bonus + 
                consistency_bonus + completeness_bonus
            )
            
            # Apply penalty factors
            penalty = self._calculate_penalty_factors(result, state)
            final_score *= (1 - penalty)
            
            # Ensure score is within a reasonable range
            final_score = max(0.0, min(1.0, final_score))
            
            return final_score
            
        except Exception as e:
            self.logger.warning(f"Failed to calculate final ranking score: {e}")
            return result.get("fused_score", 0.5)
    
    def _calculate_query_relevance_bonus(self, result: Dict[str, Any], state: RetrievalState) -> float:
        """Calculate query relevance bonus"""
        try:
            content = result.get("content", "").lower()
            question = state.question.lower()
            
            # Keyword matching ratio
            question_words = set(question.split())
            content_words = set(content.split())
            
            if len(question_words) > 0:
                match_ratio = len(question_words & content_words) / len(question_words)
                return match_ratio * 0.1  # Maximum 10% bonus
            
            return 0.0
            
        except Exception:
            return 0.0
    
    def _calculate_level_priority_bonus(self, result: Dict[str, Any], state: RetrievalState) -> float:
        """Calculate level priority bonus"""
        try:
            level = result.get("level", "Unknown")
            query_category = state.query_category
            
            # Prioritize levels based on query type
            if query_category and query_category.value == "temporal":
                # Temporal queries prioritize L1 and L2
                if level in ["L1", "L2"]:
                    return 0.05
            elif query_category and query_category.value == "inferential":
                # Inferential queries prioritize high-level memories
                if level in ["L3", "L4", "L5"]:
                    return 0.05
            elif query_category and query_category.value == "factual":
                # Factual queries prioritize L2 session memories
                if level == "L2":
                    return 0.08
            
            return 0.0
            
        except Exception:
            return 0.0
    
    def _calculate_consistency_bonus(self, result: Dict[str, Any]) -> float:
        """Calculate multi-strategy consistency bonus"""
        try:
            # If result is retrieved by multiple strategies, give consistency bonus
            retrieval_sources = result.get("retrieval_sources", [])
            source_count = len(retrieval_sources) if retrieval_sources else 1
            
            if source_count >= 3:
                return 0.08  # 3 or more strategies: 8% bonus
            elif source_count == 2:
                return 0.05  # 2 strategies: 5% bonus
            
            return 0.0
            
        except Exception:
            return 0.0
    
    def _calculate_completeness_bonus(self, result: Dict[str, Any]) -> float:
        """Calculate content completeness bonus"""
        try:
            content = result.get("content", "")
            
            # Check content completeness metrics
            completeness_score = 0.0
            
            # Medium length
            if 100 <= len(content) <= 800:
                completeness_score += 0.02
            
            # Contains specific information (numbers, dates, etc.)
            import re
            if re.search(r'\d+', content):
                completeness_score += 0.01
            
            # Contains structured information
            if any(punct in content for punct in [':', '：', '-', '•']):
                completeness_score += 0.01
            
            return completeness_score
            
        except Exception:
            return 0.0
    
    def _calculate_penalty_factors(self, result: Dict[str, Any], state: RetrievalState) -> float:
        """Calculate penalty factors"""
        try:
            penalty = 0.0
            
            # Content too short penalty
            content = result.get("content", "")
            if len(content) < 20:
                penalty += 0.1
            
            # Missing time info penalty (for temporal queries)
            if (state.query_category and state.query_category.value == "temporal" and 
                not result.get("timestamp")):
                penalty += 0.05
            
            # Level mismatch penalty
            if result.get("layer_mismatch", False):
                penalty += 0.03
            
            return min(0.3, penalty)  # Maximum penalty 30%
            
        except Exception:
            return 0.0
    
    def _apply_diversity_optimization(self, ranked_results: List[Dict[str, Any]], 
                                    state: RetrievalState) -> List[Dict[str, Any]]:
        """Apply diversity optimization"""
        try:
            if len(ranked_results) <= 5:
                return ranked_results  # Too few results, no need for diversity optimization
            
            optimized_results = []
            used_levels = set()
            used_sessions = set()
            
            # Round 1: Select high-scoring results from different levels
            for result in ranked_results:
                level = result.get("level", "Unknown")
                session_id = result.get("session_id", "")
                
                # Prioritize selecting results from different levels
                if level not in used_levels:
                    optimized_results.append(result)
                    used_levels.add(level)
                    if session_id:
                        used_sessions.add(session_id)
            
            # Round 2: Select results from different sessions in remaining results
            remaining_results = [r for r in ranked_results if r not in optimized_results]
            for result in remaining_results:
                session_id = result.get("session_id", "")
                
                if session_id not in used_sessions:
                    optimized_results.append(result)
                    used_sessions.add(session_id)
                
                # Limit diversity selection count
                if len(optimized_results) >= len(ranked_results) * 0.8:
                    break
            
            # Round 3: Fill remaining positions with original ranking
            for result in remaining_results:
                if result not in optimized_results:
                    optimized_results.append(result)
            
            self.logger.info(f"Diversity optimization: levels={len(used_levels)}, sessions={len(used_sessions)}")
            
            return optimized_results
            
        except Exception as e:
            self.logger.warning(f"Diversity optimization failed: {e}")
            return ranked_results
    
    def _log_ranking_details(self, results: List[Dict[str, Any]]) -> None:
        """Log ranking details (debug info)"""
        try:
            if not results:
                return
            
            self.logger.info(" Top 5 ranking result details:")
            for i, result in enumerate(results[:5]):
                level = result.get("level", "Unknown")
                score = result.get("final_ranking_score", 0.0)
                sources = result.get("retrieval_sources", [result.get("retrieval_source", "")])
                content_preview = result.get("content", "")[:50] + "..." if len(result.get("content", "")) > 50 else result.get("content", "")
                
                self.logger.info(f"  [{i+1}] [{level}] score={score:.3f} sources={sources} content=\"{content_preview}\"")
                
        except Exception as e:
            self.logger.warning(f"Failed to log ranking details: {e}")
