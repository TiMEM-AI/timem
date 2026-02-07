"""
Result Ranking Node

Responsible for re-ranking fused retrieval results and applying multiple ranking strategies.
"""

from typing import Dict, List, Any, Optional
import math

from timem.workflows.retrieval_state import RetrievalState, RetrievalStateValidator
from timem.utils.logging import get_logger

logger = get_logger(__name__)


class ResultsRanker:
    """Result ranking node"""
    
    def __init__(self, state_validator: Optional[RetrievalStateValidator] = None):
        """
        Initialize result ranker
        
        Args:
            state_validator: State validator, creates new instance if None
        """
        self.state_validator = state_validator or RetrievalStateValidator()
        self.logger = get_logger(__name__)
    
    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run result ranking
        
        Args:
            state: Workflow state dictionary
            
        Returns:
            Updated state dictionary
        """
        try:
            # Convert to RetrievalState object
            retrieval_state = self._dict_to_state(state)
            
            self.logger.info("Starting result ranking")
            
            if not retrieval_state.fused_results:
                self.logger.warning("No fused results to rank")
                retrieval_state.ranked_results = []
                return self._state_to_dict(retrieval_state)
            
            # Step 1: Apply multiple ranking strategies
            ranked_results = self._apply_ranking_strategies(retrieval_state)
            
            # Step 2: Diversity optimization
            diversified_results = self._apply_diversity_optimization(ranked_results)
            
            # Step 3: Apply result limits
            final_results = self._apply_result_limits(diversified_results, retrieval_state)
            
            # Step 4: Add ranking metadata
            final_results = self._add_ranking_metadata(final_results)
            
            # Step 5: Update state
            retrieval_state.ranked_results = final_results
            
            self.logger.info(f"Result ranking completed: Top {len(final_results)} results")
            
            return self._state_to_dict(retrieval_state)
            
        except Exception as e:
            error_msg = f"Result ranking failed: {str(e)}"
            self.logger.error(error_msg)
            state["errors"] = state.get("errors", []) + [error_msg]
            return state
    
    def _apply_ranking_strategies(self, state: RetrievalState) -> List[Dict[str, Any]]:
        """Apply multiple ranking strategies - includes hierarchical retrieval Session-aware re-ranking algorithm"""
        results = state.fused_results.copy()
        
        # Check if hierarchical sorting is enabled
        if self._is_hierarchical_sorting_enabled(state):
            self.logger.info("Enabling hierarchical retrieval re-ranking strategy")
            return self._apply_hierarchical_ranking(results, state)
        else:
            self.logger.info("Applying traditional Session-aware re-ranking algorithm")
            return self._apply_traditional_ranking(results, state)
    
    def _is_hierarchical_sorting_enabled(self, state: RetrievalState) -> bool:
        """Check if hierarchical sorting is enabled"""
        # Check hierarchical sorting parameter in state
        hierarchical_sorting = state.retrieval_params.get("hierarchical_sorting", False)
        
        # Check hierarchical sorting configuration in config manager
        try:
            from timem.utils.retrieval_config_manager import get_retrieval_config_manager
            config_manager = get_retrieval_config_manager()
            config_hierarchical_sorting = config_manager.is_hierarchical_sorting_enabled()
            
            # If hierarchical sorting is enabled in config, enable it
            if config_hierarchical_sorting:
                return True
        except Exception as e:
            self.logger.warning(f"Failed to get config: {e}")
        
        # Fallback to state parameter
        return hierarchical_sorting
    
    def _apply_hierarchical_ranking(self, results: List[Dict[str, Any]], state: RetrievalState) -> List[Dict[str, Any]]:
        """Apply hierarchical retrieval re-ranking strategy"""
        self.logger.info("Executing hierarchical retrieval re-ranking strategy")
        
        # Step 1: Separate results by level
        l1_results, l2_results = self._separate_by_level(results)
        self.logger.info(f"Hierarchical results: L1={len(l1_results)}, L2={len(l2_results)}")
        
        # Step 2: Rank L1 results using existing method (relevance + Session-aware)
        ranked_l1 = self._apply_traditional_ranking(l1_results, state)
        
        # Step 3: Rank L2 results by time
        ranked_l2 = self._apply_temporal_ranking_for_l2(l2_results, state)
        
        # Step 4: Concatenate results: L1 first, then L2
        final_results = ranked_l1 + ranked_l2
        
        self.logger.info(f"Hierarchical re-ranking completed: L1={len(ranked_l1)}, L2={len(ranked_l2)}, Total={len(final_results)}")
        return final_results
    
    def _separate_by_level(self, results: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Separate results by level"""
        l1_results = []
        l2_results = []
        
        for result in results:
            level = result.get("level", "").upper()
            if level == "L1":
                l1_results.append(result)
            elif level == "L2":
                l2_results.append(result)
            else:
                # Other levels temporarily classified as L1
                l1_results.append(result)
        
        return l1_results, l2_results
    
    def _apply_temporal_ranking_for_l2(self, l2_results: List[Dict[str, Any]], state: RetrievalState) -> List[Dict[str, Any]]:
        """Apply temporal ranking for L2 results"""
        if not l2_results:
            return []
        
        self.logger.info(f"Applying temporal ranking to {len(l2_results)} L2 results")
        
        # Sort by timestamp (newest first)
        sorted_l2 = sorted(l2_results, 
                          key=lambda x: self._extract_memory_timestamp(x), 
                          reverse=True)
        
        # Add ranking markers
        for i, result in enumerate(sorted_l2):
            result["l2_temporal_rank"] = i + 1
            result["sorting_method"] = "temporal"
        
        return sorted_l2
    
    def _apply_traditional_ranking(self, results: List[Dict[str, Any]], state: RetrievalState) -> List[Dict[str, Any]]:
        """Apply traditional Session-aware re-ranking algorithm"""
        # Step 1: Group memories by session_id
        session_groups = self._group_by_session(results)
        self.logger.info(f"Grouped results: {len(session_groups)} sessions")
        
        # Step 2: Sort by time within each session + sort sessions by highest similarity
        reordered_results = self._apply_session_temporal_ordering(session_groups)
        
        # Step 3: Apply traditional auxiliary ranking strategies (maintain session order)
        reordered_results = self._apply_freshness_boost(reordered_results, state)
        reordered_results = self._apply_completeness_boost(reordered_results, state) 
        reordered_results = self._apply_relevance_refinement(reordered_results, state)
        
        return reordered_results
    
    def _group_by_session(self, results: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Group memories by session_id"""
        session_groups = {}
        
        for result in results:
            session_id = result.get("session_id", "unknown_session")
            
            if session_id not in session_groups:
                session_groups[session_id] = []
                
            session_groups[session_id].append(result)
            
        return session_groups
    
    def _apply_session_temporal_ordering(self, session_groups: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """Apply Session-aware temporal ordering"""
        # Step 1: Sort by time within each session
        for session_id, memories in session_groups.items():
            memories.sort(key=lambda x: self._extract_memory_timestamp(x))
            self.logger.debug(f"Session {session_id}: sorted {len(memories)} memories by time")
        
        # Step 2: Calculate highest similarity score for each session
        session_scores = {}
        for session_id, memories in session_groups.items():
            max_score = max(memory.get("fused_score", 0.0) for memory in memories)
            session_scores[session_id] = max_score
        
        # Step 3: Sort sessions by highest score
        sorted_sessions = sorted(session_groups.keys(), 
                               key=lambda s: session_scores[s], 
                               reverse=True)
        
        # Step 4: Concatenate memories from all sessions in order
        final_results = []
        for session_id in sorted_sessions:
            session_memories = session_groups[session_id]
            final_results.extend(session_memories)
            self.logger.debug(f"Added Session {session_id}: {len(session_memories)} memories (highest score: {session_scores[session_id]:.4f})")
        
        self.logger.info(f"Session-aware re-ranking completed: {len(final_results)} memories, {len(sorted_sessions)} sessions")
        return final_results
    
    def _extract_memory_timestamp(self, memory: Dict[str, Any]) -> str:
        """Extract memory timestamp for sorting"""
        # Try multiple time fields in priority order
        time_fields = [
            "timestamp", 
            "created_at", 
            "updated_at",
            "time_window_start",
            "start_time",
            "memory_timestamp"
        ]
        
        for field in time_fields:
            if field in memory and memory[field]:
                return str(memory[field])
        
        # If no time field found, return default value
        return "1900-01-01T00:00:00"
    
    def _apply_freshness_boost(self, results: List[Dict[str, Any]], 
                              state: RetrievalState) -> List[Dict[str, Any]]:
        """Apply freshness boost"""
        # If query is time-related, boost ranking of newer memories
        if state.query_intent == "temporal_query" or state.time_entities:
            for result in results:
                # Can calculate freshness bonus based on memory timestamp
                # Simplified implementation: check if timestamp field exists
                if "timestamp" in result or "created_at" in result:
                    freshness_bonus = 0.05  # 5% freshness bonus
                    current_score = result.get("fused_score") or 0  # Fix: Convert None to 0
                    result["fused_score"] = min(1.0, current_score + freshness_bonus)
                    result["freshness_boosted"] = True
        
        # Re-sort (ensure None converts to 0.0)
        results.sort(key=lambda x: x.get("fused_score") or 0.0, reverse=True)
        return results
    
    def _apply_completeness_boost(self, results: List[Dict[str, Any]], 
                                 state: RetrievalState) -> List[Dict[str, Any]]:
        """Apply completeness boost"""
        for result in results:
            content = result.get("content", "")
            title = result.get("title", "")
            
            # Calculate content completeness score
            completeness_score = 0.0
            
            # Check content length
            if len(content) > 100:
                completeness_score += 0.02
            
            # Check if has title
            if title:
                completeness_score += 0.01
            
            # Check if has relationship information
            if result.get("child_memory_ids") or result.get("relations"):
                completeness_score += 0.02
            
            # Apply completeness bonus
            if completeness_score > 0:
                current_score = result.get("fused_score", 0)
                result["fused_score"] = min(1.0, current_score + completeness_score)
                result["completeness_boosted"] = True
        
        # Re-sort
        results.sort(key=lambda x: x.get("fused_score", 0.0), reverse=True)
        return results
    
    def _apply_relevance_refinement(self, results: List[Dict[str, Any]], 
                                   state: RetrievalState) -> List[Dict[str, Any]]:
        """Apply relevance refinement"""
        # Check result match with query keywords
        query_keywords = [kw.lower() for kw in state.key_entities]
        
        if not query_keywords:
            return results
        
        for result in results:
            content = result.get("content", "").lower()
            title = result.get("title", "").lower()
            
            # Calculate keyword match ratio
            keyword_matches = 0
            for keyword in query_keywords:
                if keyword in content or keyword in title:
                    keyword_matches += 1
            
            if keyword_matches > 0:
                match_ratio = keyword_matches / len(query_keywords)
                relevance_bonus = match_ratio * 0.03  # Max 3% bonus
                
                current_score = result.get("fused_score", 0)
                result["fused_score"] = min(1.0, current_score + relevance_bonus)
                result["keyword_matches"] = keyword_matches
                result["relevance_boosted"] = True
        
        # Re-sort
        results.sort(key=lambda x: x.get("fused_score", 0.0), reverse=True)
        return results
    
    def _apply_diversity_optimization(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply diversity optimization"""
        if len(results) <= 3:
            return results  # Too few results, no need for diversity optimization
        
        optimized_results = []
        remaining_results = results.copy()
        
        # Select first highest-scoring result
        if remaining_results:
            best_result = remaining_results.pop(0)
            optimized_results.append(best_result)
        
        # Apply diversity selection strategy
        while remaining_results and len(optimized_results) < len(results):
            best_candidate = None
            best_diversity_score = -1
            
            for candidate in remaining_results:
                # Calculate diversity with already-selected results
                diversity_score = self._calculate_diversity_score(candidate, optimized_results)
                relevance_score = candidate.get("fused_score", 0)
                
                # Balance relevance and diversity
                combined_score = 0.7 * relevance_score + 0.3 * diversity_score
                
                if combined_score > best_diversity_score:
                    best_diversity_score = combined_score
                    best_candidate = candidate
            
            if best_candidate:
                remaining_results.remove(best_candidate)
                optimized_results.append(best_candidate)
            else:
                break
        
        return optimized_results
    
    def _calculate_diversity_score(self, candidate: Dict[str, Any], 
                                  selected_results: List[Dict[str, Any]]) -> float:
        """Calculate diversity score between candidate and selected results"""
        if not selected_results:
            return 1.0
        
        candidate_content = candidate.get("content", "").lower()
        candidate_level = candidate.get("level", "")
        candidate_user = candidate.get("user_id", "")
        
        diversity_scores = []
        
        for selected in selected_results:
            selected_content = selected.get("content", "").lower()
            selected_level = selected.get("level", "")
            selected_user = selected.get("user_id", "")
            
            # Calculate content similarity (simplified)
            content_similarity = self._calculate_simple_similarity(candidate_content, selected_content)
            
            # Level diversity
            level_diversity = 1.0 if candidate_level != selected_level else 0.5
            
            # User diversity
            user_diversity = 1.0 if candidate_user != selected_user else 0.7
            
            # Combined diversity score
            diversity_score = (1.0 - content_similarity) * level_diversity * user_diversity
            diversity_scores.append(diversity_score)
        
        # Return average diversity score
        return sum(diversity_scores) / len(diversity_scores)
    
    def _calculate_simple_similarity(self, text1: str, text2: str) -> float:
        """Calculate simple similarity between two texts"""
        if not text1 or not text2:
            return 0.0
        
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0.0
    
    def _apply_result_limits(self, results: List[Dict[str, Any]], 
                            state: RetrievalState) -> List[Dict[str, Any]]:
        """Apply hierarchical result limits: keep top3 for L1 after re-ranking, top1 for L2"""
        # Check if hierarchical sorting is enabled
        if self._is_hierarchical_sorting_enabled(state):
            return self._apply_hierarchical_limits(results, state)
        else:
            # Traditional limit method
            final_limit = state.retrieval_params.get("final_result_limit", 10)
            limited_results = results[:final_limit]
            
            if len(results) > final_limit:
                self.logger.info(f"Applying traditional result limit: {len(results)} -> {len(limited_results)}")
            
            return limited_results
    
    def _apply_hierarchical_limits(self, results: List[Dict[str, Any]], 
                                 state: RetrievalState) -> List[Dict[str, Any]]:
        """Apply hierarchical result limits: keep top5 for L1 after re-ranking, top1 for L2"""
        # Separate results by level
        l1_results, l2_results = self._separate_by_level(results)
        
        # Get hierarchical limits from config file with reasonable defaults
        l1_limit = 5  # Default L1 keeps 5
        l2_limit = 1  # Default L2 keeps 1
        
        try:
            # First try to get from retrieval_config
            if hasattr(state, 'retrieval_config') and state.retrieval_config:
                hierarchical_config = state.retrieval_config.get('hierarchical', {})
                final_limits = hierarchical_config.get('final_limits', {})
                l1_limit = final_limits.get('L1', 5)  # Get L1 limit from final_limits, default 5
                l2_limit = final_limits.get('L2', 1)  # Get L2 limit from final_limits, default 1
                self.logger.info(f"Got hierarchical limits from retrieval_config: L1={l1_limit}, L2={l2_limit}")
            else:
                # Fallback to retrieval_params
                l1_limit = state.retrieval_params.get("hierarchical_L1_final_limit", 5)
                l2_limit = state.retrieval_params.get("hierarchical_L2_final_limit", 1)
                self.logger.info(f"Got hierarchical limits from retrieval_params: L1={l1_limit}, L2={l2_limit}")
                
        except Exception as e:
            self.logger.error(f"Failed to get config: {e}")
            # If config retrieval fails, use default values
            l1_limit = 5
            l2_limit = 1
        
        # Limit L1 results
        limited_l1 = l1_results[:l1_limit]
        
        # Limit L2 results
        limited_l2 = l2_results[:l2_limit]
        
        # Concatenate results: L1 first, then L2
        final_results = limited_l1 + limited_l2
        
        self.logger.info(f"Applied hierarchical result limits: L1={len(l1_results)}->{len(limited_l1)}(top{l1_limit}), L2={len(l2_results)}->{len(limited_l2)}(top{l2_limit}), Total={len(final_results)}")
        
        return final_results
    
    def _add_ranking_metadata(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Add ranking metadata"""
        for i, result in enumerate(results):
            result["final_rank"] = i + 1
            result["ranking_timestamp"] = self._get_current_timestamp()
            
            # Add ranking explanation
            ranking_factors = []
            if result.get("freshness_boosted"):
                ranking_factors.append("freshness")
            if result.get("completeness_boosted"):
                ranking_factors.append("completeness")
            if result.get("relevance_boosted"):
                ranking_factors.append("relevance")
            
            result["ranking_factors"] = ranking_factors
        
        return results
    
    def _get_current_timestamp(self) -> str:
        """Get current timestamp"""
        from datetime import datetime
        return datetime.now().isoformat()
    
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
