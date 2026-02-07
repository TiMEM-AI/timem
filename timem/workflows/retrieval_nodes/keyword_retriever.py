"""
Keyword retrieval node

Responsible for memory retrieval based on keyword matching,
suitable for queries that exactly match specific entities or concepts
"""

from typing import Dict, List, Any, Optional

from timem.workflows.retrieval_state import RetrievalState, RetrievalStateValidator, RetrievalStrategy
from storage.memory_storage_manager import get_memory_storage_manager_async
from timem.utils.logging import get_logger

logger = get_logger(__name__)


class KeywordRetriever:
    """Keyword retrieval node"""
    
    def __init__(self, 
                 storage_manager=None,
                 state_validator: Optional[RetrievalStateValidator] = None):
        """
        Initialize keyword retrieval node
        
        Args:
            storage_manager: Storage manager
            state_validator: State validator
        """
        self.storage_manager = storage_manager
        self.state_validator = state_validator or RetrievalStateValidator()
        self.logger = get_logger(__name__)
    
    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run keyword retrieval node
        
        Args:
            state: Current state dictionary
            
        Returns:
            Updated state dictionary
        """
        try:
            # Convert dictionary to RetrievalState object
            retrieval_state = RetrievalState(**state)
            
            # Check if keyword retrieval strategy is selected
            strategy_values = [s.value if hasattr(s, 'value') else str(s) for s in retrieval_state.selected_strategies]
            if RetrievalStrategy.KEYWORD.value not in strategy_values and RetrievalStrategy.KEYWORD not in retrieval_state.selected_strategies:
                self.logger.info("⏭️ Skip keyword retrieval: strategy not selected")
                return retrieval_state.to_dict()
            
            # Check if key entities exist
            if not retrieval_state.key_entities:
                self.logger.info("⏭️ Skip keyword retrieval: no key entities")
                return retrieval_state.to_dict()
            
            self.logger.info(f"🔑 Start keyword retrieval, key entity count: {len(retrieval_state.key_entities)}")
            
            # Initialize storage manager
            if not self.storage_manager:
                self.storage_manager = await get_memory_storage_manager_async()
            
            # Perform keyword retrieval
            results = await self._perform_keyword_search(retrieval_state)
            
            # Process and mark results
            processed_results = await self._process_results(results, retrieval_state)
            
            retrieval_state.keyword_results = processed_results
            retrieval_state.total_memories_searched += len(processed_results)
            
            self.logger.info(f"Keyword search completed: {len(processed_results)} results")
            
            # Convert back to dictionary format and return
            return retrieval_state.to_dict()
            
        except Exception as e:
            self.logger.error(f"Keyword search failed: {str(e)}")
            state["errors"] = state.get("errors", []) + [f"Keyword search failed: {str(e)}"]
            state["success"] = False
            return state
    
    async def _perform_keyword_search(self, state: RetrievalState) -> List[Any]:
        """Perform keyword-based retrieval"""
        all_results = []
        
        try:
            # Retrieve for each key entity
            for entity in state.key_entities:
                query = {
                    "user_id": state.user_id,
                    "expert_id": state.expert_id,
                    "content_contains": entity  # Content contains retrieval
                }
                
                options = {
                    "limit": state.retrieval_params.get("max_results_per_strategy", 20)
                }
                
                self.logger.info(f"Keyword retrieval: '{entity}'")
                
                # Retrieve from SQL storage (keyword retrieval is primarily SQL LIKE query)
                temp_results = await self.storage_manager.sql_adapter.search_memories(query, options)
                
                # Add keyword relevance score and create a wrapper dictionary for each result
                processed_temp_results = []
                for result in temp_results:
                    keyword_relevance = self._calculate_keyword_relevance(result, entity)
                    
                    # Create a wrapper dictionary instead of modifying the original object
                    result_wrapper = {
                        "memory_object": result,
                        "keyword_relevance": keyword_relevance,
                        "matched_keyword": entity
                    }
                    processed_temp_results.append(result_wrapper)

                all_results.extend(processed_temp_results)
                
                self.logger.info(f"Keyword '{entity}' retrieved {len(temp_results)} results")
            
            return all_results
            
        except Exception as e:
            self.logger.error(f"Keyword retrieval execution failed: {str(e)}")
            raise
    
    def _calculate_keyword_relevance(self, result: Any, keyword: str) -> float:
        """
        Calculate keyword relevance score.

        This function calculates the relevance of a keyword in a given result.
        The score is based on the frequency of the keyword in the result content,
        the position of the keyword in the content, and whether the keyword is an exact match.

        Args:
            result: The result object containing the content to be searched.
            keyword: The keyword to be searched for.

        Returns:
            A float value representing the keyword relevance score.
        """
        try:
            content = getattr(result, 'content', '').lower()
            keyword_lower = keyword.lower()
            
            if not content or not keyword_lower:
                return 0.1
            
            # Calculate the frequency of the keyword in the content
            count = content.count(keyword_lower)
            if count == 0:
                return 0.1
            
            # Calculate the relevance based on the frequency and content length
            content_words = len(content.split())
            if content_words == 0:
                return 0.1
            
            # Frequency score
            frequency_score = min(1.0, count / content_words * 20)  # Normalize frequency
            
            # Position score: higher weight for keywords at the beginning
            first_occurrence = content.find(keyword_lower)
            if first_occurrence != -1:
                position_score = 1.0 - (first_occurrence / len(content)) * 0.3
            else:
                position_score = 0.5
            
            # Exact match bonus
            exact_match_bonus = 0.0
            if f" {keyword_lower} " in f" {content} ":  # Exact word match
                exact_match_bonus = 0.2
            
            # Comprehensive score
            relevance = (frequency_score * 0.6 + position_score * 0.3 + exact_match_bonus)
            return min(1.0, max(0.1, relevance))
            
        except Exception as e:
            self.logger.warning(f"Failed to calculate keyword relevance: {e}")
            return 0.5
    
    async def _process_results(self, results: List[Any], state: RetrievalState) -> List[Dict[str, Any]]:
        """Process retrieval results and convert to unified format"""
        processed_results = []
        
        # Deduplicate (based on ID)
        seen_ids = set()
        
        for i, result in enumerate(results):
            try:
                # Handle wrapped results or original results
                if isinstance(result, dict) and "memory_object" in result:
                    # This is a wrapped result
                    memory_obj = result["memory_object"]
                    keyword_relevance = result["keyword_relevance"]
                    matched_keyword = result["matched_keyword"]
                    
                    result_id = getattr(memory_obj, 'id', f"keyword_{i}")
                    if result_id in seen_ids:
                        continue
                    seen_ids.add(result_id)
                    
                    # Convert Memory object to dictionary
                    if hasattr(memory_obj, 'to_dict'):
                        result_dict = memory_obj.to_dict()
                    else:
                        result_dict = {
                            "id": result_id,
                            "content": getattr(memory_obj, 'content', ''),
                            "level": getattr(memory_obj, 'level', 'Unknown'),
                            "user_id": getattr(memory_obj, 'user_id', state.user_id),
                            "expert_id": getattr(memory_obj, 'expert_id', state.expert_id),
                            "timestamp": getattr(memory_obj, 'timestamp', None)
                        }
                else:
                    # This is an original result
                    result_id = getattr(result, 'id', f"keyword_{i}")
                    if result_id in seen_ids:
                        continue
                    seen_ids.add(result_id)
                    
                    if hasattr(result, 'to_dict'):
                        result_dict = result.to_dict()
                    elif isinstance(result, dict):
                        result_dict = result.copy()
                    else:
                        result_dict = {
                            "id": result_id,
                            "content": getattr(result, 'content', str(result)),
                            "level": getattr(result, 'level', 'Unknown'),
                            "user_id": getattr(result, 'user_id', state.user_id),
                            "expert_id": getattr(result, 'expert_id', state.expert_id),
                            "timestamp": getattr(result, 'timestamp', None)
                        }
                    
                    # Calculate keyword relevance
                    keyword_relevance = 0.6  # Default value
                    matched_keyword = ""
                
                # Add retrieval source and score information
                result_dict["retrieval_source"] = "keyword"
                result_dict["retrieval_score"] = keyword_relevance
                result_dict["matched_keyword"] = matched_keyword
                
                # Apply keyword weight
                keyword_weight = state.retrieval_params.get("keyword_weight", 0.7)
                result_dict["weighted_score"] = result_dict["retrieval_score"] * keyword_weight
                
                # Filter low-score results
                min_score = state.retrieval_params.get("keyword_min_score", 0.3)
                if result_dict["retrieval_score"] < min_score:
                    continue
                
                processed_results.append(result_dict)
                
            except Exception as e:
                self.logger.warning(f"Processing keyword retrieval result[{i}] failed: {str(e)}")
                continue
        
        # Sort by keyword relevance
        processed_results.sort(key=lambda x: x.get("retrieval_score", 0.0), reverse=True)
        
        self.logger.info(f"Keyword retrieval result processing complete: {len(processed_results)} valid results")
        
        return processed_results
