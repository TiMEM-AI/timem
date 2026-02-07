"""
Semantic retrieval node

Responsible for executing semantic retrieval based on vector similarity, supporting character filtering and multiple retrieval strategies.
"""

from typing import Dict, List, Any, Optional

from timem.workflows.retrieval_state import RetrievalState, RetrievalStateValidator, RetrievalStrategy
from storage.memory_storage_manager import get_memory_storage_manager_async
from timem.utils.logging import get_logger

logger = get_logger(__name__)


class SemanticRetriever:
    """Semantic retrieval node"""
    
    def __init__(self, 
                 storage_manager: Optional[Any] = None,
                 state_validator: Optional[RetrievalStateValidator] = None):
        """
        Initialize semantic retriever
        
        Args:
            storage_manager: Storage manager, auto-fetch if None
            state_validator: State validator, create new instance if None
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
        Run semantic retrieval
        
        Args:
            state: Workflow state dictionary
            
        Returns:
            Updated state dictionary
        """
        try:
            # Convert to RetrievalState object
            retrieval_state = self._dict_to_state(state)
            
            # Check if semantic retrieval is needed
            if RetrievalStrategy.SEMANTIC not in retrieval_state.selected_strategies:
                self.logger.info("Skip semantic retrieval (strategy not selected)")
                return self._state_to_dict(retrieval_state)
            
            self.logger.info("Start semantic retrieval")
            
            # Check if hierarchical retrieval is enabled
            if self._is_hierarchical_enabled(retrieval_state):
                self.logger.info("Enable hierarchical semantic retrieval")
                results = await self._perform_hierarchical_semantic_search(retrieval_state)
            else:
                self.logger.info("Use traditional semantic retrieval")
                # Step 1: Build retrieval query
                query = self._build_semantic_query(retrieval_state)
                
                # Step 2: Configure retrieval options
                options = self._configure_retrieval_options(retrieval_state)
                
                # Step 3: Execute vector search
                raw_results = await self._execute_vector_search(query, options)
                
                # Step 4: Process search results
                results = self._process_search_results(raw_results, retrieval_state)
            
            # Step 5: Update state
            retrieval_state.semantic_results = results
            retrieval_state.total_memories_searched += len(results)
            
            self.logger.info(f"Semantic retrieval complete: {len(results)} results")
            
            return self._state_to_dict(retrieval_state)
            
        except Exception as e:
            error_msg = f"Semantic retrieval failed: {str(e)}"
            self.logger.error(error_msg)
            state["errors"] = state.get("errors", []) + [error_msg]
            return state
    
    def _is_hierarchical_enabled(self, state: RetrievalState) -> bool:
        """Check if hierarchical retrieval is enabled"""
        return RetrievalStrategy.HIERARCHICAL in state.selected_strategies
    
    async def _perform_hierarchical_semantic_search(self, state: RetrievalState) -> List[Dict[str, Any]]:
        """Perform hierarchical semantic retrieval"""
        all_results = []
        
        # Get hierarchical retrieval configuration
        l1_limit = state.retrieval_params.get("hierarchical_L1_limit", 10)
        l2_limit = state.retrieval_params.get("hierarchical_L2_limit", 3)
        
        self.logger.info(f"Hierarchical retrieval config: L1={l1_limit}, L2={l2_limit}")
        
        # Search L1 memories
        if l1_limit > 0:
            l1_results = await self._search_by_level(state, "L1", l1_limit)
            all_results.extend(l1_results)
            self.logger.info(f"L1 retrieval complete: {len(l1_results)} results")
        
        # Search L2 memories
        if l2_limit > 0:
            l2_results = await self._search_by_level(state, "L2", l2_limit)
            all_results.extend(l2_results)
            self.logger.info(f"L2 retrieval complete: {len(l2_results)} results")
        
        # Process all results
        processed_results = self._process_search_results(all_results, state)
        
        return processed_results
    
    async def _search_by_level(self, state: RetrievalState, level: str, limit: int) -> List[Any]:
        """Search memories by level"""
        try:
            # Build level query
            query = self._build_semantic_query(state)
            query["level"] = level
            
            # Configure retrieval options
            options = {
                "limit": limit,
                "score_threshold": 0.0  # Adjust to lowest threshold
            }
            
            # Execute search
            results = await self._execute_vector_search(query, options)
            
            # Add level mark to results
            for result in results:
                if hasattr(result, 'to_dict'):
                    result_dict = result.to_dict()
                elif isinstance(result, dict):
                    result_dict = result.copy()
                else:
                    result_dict = {"content": str(result)}
                
                result_dict["level"] = level
                result_dict["retrieval_source"] = f"semantic_{level.lower()}"
                result_dict["retrieval_strategy"] = RetrievalStrategy.SEMANTIC.value
                
                # Replace original result with processed result
                if hasattr(result, 'to_dict'):
                    # If result object has to_dict method, create a wrapper object
                    class WrappedResult:
                        def __init__(self, data):
                            self._data = data
                        
                        def to_dict(self):
                            return self._data
                    
                    result = WrappedResult(result_dict)
                else:
                    result = result_dict
            
            return results
            
        except Exception as e:
            self.logger.error(f"Level {level} retrieval failed: {str(e)}")
            return []
    
    def _build_semantic_query(self, state: RetrievalState) -> Dict[str, Any]:
        """Build semantic retrieval query"""
        query = {
            "query_text": state.question
        }
        
        # Add character filter condition
        if state.character_ids:
            # Use character_ids for OR condition matching
            query["character_ids"] = state.character_ids
            self.logger.info(f"Using character ID filter: {state.character_ids}")
        else:
            # If no character IDs, perform comprehensive retrieval
            self.logger.info("No character ID found, perform comprehensive retrieval")
        
        # Add time filter (if time entities exist)
        if state.time_entities:
            # Can add time range filter based on time entities
            # Simplified processing for now, can be expanded in the future
            pass
        
        return query
    
    def _configure_retrieval_options(self, state: RetrievalState) -> Dict[str, Any]:
        """Configure retrieval options"""
        # Get semantic retrieval configuration from retrieval parameters
        top_k = state.retrieval_params.get("semantic_top_k", 10)
        score_threshold = state.retrieval_params.get("semantic_score_threshold", 0.0)  # Adjust to lowest threshold
        
        options = {
            "limit": top_k,
            "score_threshold": score_threshold
        }
        
        self.logger.info(f"Semantic retrieval config: top_k={top_k}, score_threshold={score_threshold}")
        return options
    
    async def _execute_vector_search(self, query: Dict[str, Any], options: Dict[str, Any]) -> List[Any]:
        """Execute vector search"""
        try:
            storage_manager = await self._get_storage_manager()
            results = await storage_manager.search_memories(query, options, "vector")
            return results
        except Exception as e:
            self.logger.error(f"Vector search execution failed: {str(e)}")
            raise
    
    def _process_search_results(self, results: List[Any], state: RetrievalState) -> List[Dict[str, Any]]:
        """Process search results, unify format and add metadata"""
        processed_results = []
        
        for i, result in enumerate(results):
            try:
                # Convert result to dictionary format
                if hasattr(result, 'to_dict'):
                    result_dict = result.to_dict()
                elif isinstance(result, dict):
                    result_dict = result.copy()
                else:
                    result_dict = {"content": str(result)}
                
                # Add retrieval source mark
                result_dict["retrieval_source"] = "semantic"
                result_dict["retrieval_strategy"] = RetrievalStrategy.SEMANTIC.value
                
                # Ensure score field exists
                if "retrieval_score" not in result_dict:
                    result_dict["retrieval_score"] = result_dict.get("vector_score", 0.8)
                
                # Add ranking information
                result_dict["retrieval_rank"] = i + 1
                
                # Validate result completeness
                if self._validate_result(result_dict):
                    processed_results.append(result_dict)
                else:
                    self.logger.warning(f"Result {i} validation failed, skip")
                    
            except Exception as e:
                self.logger.warning(f"Error processing result {i}: {str(e)}")
                continue
        
        return processed_results
    
    def _validate_result(self, result: Dict[str, Any]) -> bool:
        """Validate completeness of single search result"""
        required_fields = ["id", "content"]
        
        for field in required_fields:
            if field not in result or not result[field]:
                return False
        
        # Check if score is reasonable
        score = result.get("retrieval_score", 0)
        if not isinstance(score, (int, float)) or score < 0:
            return False
        
        return True
    
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