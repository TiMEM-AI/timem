"""
Hierarchical Retrieval Node

Responsible for memory retrieval in TiMem hierarchical architecture,
performing specialized retrieval for different memory levels (L1-L5)
"""

from typing import Dict, List, Any, Optional

from timem.workflows.retrieval_state import RetrievalState, RetrievalStateValidator, RetrievalStrategy
from storage.memory_storage_manager import get_memory_storage_manager_async
from timem.utils.logging import get_logger

logger = get_logger(__name__)


class HierarchicalRetriever:
    """Hierarchical Retrieval Node - Specialized for L1/L2 hierarchical retrieval"""
    
    def __init__(self, 
                 storage_manager=None,
                 state_validator: Optional[RetrievalStateValidator] = None):
        """
        Initialize hierarchical retrieval node
        
        Args:
            storage_manager: Storage manager
            state_validator: State validator
        """
        self.storage_manager = storage_manager
        self.state_validator = state_validator or RetrievalStateValidator()
        self.logger = get_logger(__name__)
    
    async def _get_storage_manager(self):
        """Get storage manager instance"""
        if self.storage_manager is None:
            self.storage_manager = await get_memory_storage_manager_async()
        return self.storage_manager
    
    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run hierarchical retrieval
        
        Args:
            state: Workflow state dictionary
            
        Returns:
            Updated state dictionary
        """
        try:
            # Convert to RetrievalState object
            retrieval_state = self._dict_to_state(state)
            
            # Check if hierarchical retrieval is needed
            if RetrievalStrategy.HIERARCHICAL not in retrieval_state.selected_strategies:
                self.logger.info("Skip hierarchical retrieval (strategy not selected)")
                return self._state_to_dict(retrieval_state)
            
            self.logger.info("Start hierarchical retrieval")
            
            # Perform hierarchical search
            results = await self._perform_hierarchical_search(retrieval_state)
            
            # Update state
            retrieval_state.hierarchical_results = results
            retrieval_state.total_memories_searched += len(results)
            
            self.logger.info(f"Hierarchical retrieval complete: {len(results)} results")
            
            return self._state_to_dict(retrieval_state)
            
        except Exception as e:
            error_msg = f"Hierarchical retrieval failed: {str(e)}"
            self.logger.error(error_msg)
            state["errors"] = state.get("errors", []) + [error_msg]
            return state
    
    async def _perform_hierarchical_search(self, state: RetrievalState) -> List[Dict[str, Any]]:
        """Perform hierarchical search - L1 retrieves top 10, L2 retrieves top 3"""
        all_results = []
        
        # Get hierarchical retrieval configuration
        l1_limit = state.retrieval_params.get("hierarchical_L1_limit", 10)
        l2_limit = state.retrieval_params.get("hierarchical_L2_limit", 3)
        
        self.logger.info(f"Hierarchical retrieval config: L1={l1_limit}, L2={l2_limit}")
        
        try:
            # Retrieve L1 memories (top 10)
            if l1_limit > 0:
                l1_results = await self._search_l1_memories(state, l1_limit)
                all_results.extend(l1_results)
                self.logger.info(f"L1 retrieval complete: {len(l1_results)} results")
            
            # Retrieve L2 memories (top 3)
            if l2_limit > 0:
                l2_results = await self._search_l2_memories(state, l2_limit)
                all_results.extend(l2_results)
                self.logger.info(f"L2 retrieval complete: {len(l2_results)} results")
            
            # Add level markers and sorting info to results
            processed_results = self._process_hierarchical_results(all_results)
            
            return processed_results
            
        except Exception as e:
            self.logger.error(f"Hierarchical retrieval execution failed: {str(e)}")
            return []
    
    async def _search_l1_memories(self, state: RetrievalState, limit: int) -> List[Dict[str, Any]]:
        """Retrieve L1 memories (fragment-level memories)"""
        try:
            storage_manager = await self._get_storage_manager()
            
            # Build L1 query
            query = {
                "query_text": state.question,
                "level": "L1"
            }
            
            # Add character filter
            if state.character_ids:
                query["character_ids"] = state.character_ids
            
            # Configure retrieval options
            options = {
                "limit": limit,
                "score_threshold": 0.3,  # L1 uses lower threshold for more candidates
                "sort_by": "relevance"   # L1 sorted by relevance
            }
            
            # Execute vector search
            results = await storage_manager.search_memories(query, options, "vector")
            
            # Process results
            processed_results = []
            for i, result in enumerate(results):
                result_dict = self._convert_to_dict(result)
                result_dict.update({
                    "level": "L1",
                    "retrieval_source": "hierarchical_l1",
                    "retrieval_strategy": RetrievalStrategy.HIERARCHICAL.value,
                    "l1_rank": i + 1,
                    "sorting_method": "relevance"
                })
                processed_results.append(result_dict)
            
            return processed_results
            
        except Exception as e:
            self.logger.error(f"L1 memory retrieval failed: {str(e)}")
            return []
    
    async def _search_l2_memories(self, state: RetrievalState, limit: int) -> List[Dict[str, Any]]:
        """Retrieve L2 memories (session-level memories)"""
        try:
            storage_manager = await self._get_storage_manager()
            
            # Build L2 query
            query = {
                "query_text": state.question,
                "level": "L2"
            }
            
            # Add character filter
            if state.character_ids:
                query["character_ids"] = state.character_ids
            
            # Configure retrieval options
            options = {
                "limit": limit,
                "score_threshold": 0.4,  # L2 uses medium threshold
                "sort_by": "temporal"    # L2 sorted by time
            }
            
            # Execute vector search
            results = await storage_manager.search_memories(query, options, "vector")
            
            # Process results
            processed_results = []
            for i, result in enumerate(results):
                result_dict = self._convert_to_dict(result)
                result_dict.update({
                    "level": "L2",
                    "retrieval_source": "hierarchical_l2",
                    "retrieval_strategy": RetrievalStrategy.HIERARCHICAL.value,
                    "l2_rank": i + 1,
                    "sorting_method": "temporal"
                })
                processed_results.append(result_dict)
            
            return processed_results
            
        except Exception as e:
            self.logger.error(f"L2 memory retrieval failed: {str(e)}")
            return []
    
    def _process_hierarchical_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process hierarchical retrieval results, add metadata"""
        for result in results:
            # Ensure score field exists
            if "retrieval_score" not in result:
                result["retrieval_score"] = result.get("vector_score", 0.8)
            
            # Add level weight
            level = result.get("level", "")
            if level == "L1":
                result["level_weight"] = 0.8
            elif level == "L2":
                result["level_weight"] = 0.9
            else:
                result["level_weight"] = 0.5
        
        return results
    
    def _convert_to_dict(self, result: Any) -> Dict[str, Any]:
        """Convert retrieval result to dictionary format"""
        if hasattr(result, 'to_dict'):
            return result.to_dict()
        elif isinstance(result, dict):
            return result.copy()
        else:
            return {"content": str(result)}
    
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
