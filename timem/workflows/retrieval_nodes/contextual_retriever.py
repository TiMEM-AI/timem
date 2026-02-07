"""
Contextual retrieval node

Responsible for context expansion based on existing retrieval results,
discovering related child memories and historical memories through memory relationships
"""

from typing import Dict, List, Any, Optional

from timem.workflows.retrieval_state import RetrievalState, RetrievalStateValidator, RetrievalStrategy
from storage.memory_storage_manager import get_memory_storage_manager_async
from timem.utils.logging import get_logger

logger = get_logger(__name__)


class ContextualRetriever:
    """Contextual retrieval node - reference memory_generation node design"""
    
    def __init__(self, 
                 storage_manager=None,
                 state_validator: Optional[RetrievalStateValidator] = None):
        """
        Initialize contextual retrieval node
        
        Args:
            storage_manager: Storage manager
            state_validator: State validator
        """
        self.storage_manager = storage_manager
        self.state_validator = state_validator or RetrievalStateValidator()
        self.logger = get_logger(__name__)
    
    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run contextual retrieval node
        
        Args:
            state: Current state dictionary
            
        Returns:
            Updated state dictionary
        """
        try:
            # Convert dictionary to RetrievalState object
            retrieval_state = RetrievalState(**state)
            
            # Check if contextual retrieval strategy is selected
            strategy_values = [s.value if hasattr(s, 'value') else str(s) for s in retrieval_state.selected_strategies]
            if RetrievalStrategy.CONTEXTUAL.value not in strategy_values and RetrievalStrategy.CONTEXTUAL not in retrieval_state.selected_strategies:
                self.logger.info("⏭️ Skip contextual retrieval: strategy not selected")
                return retrieval_state.to_dict()
            
            # Check if there are other retrieval results as contextual basis
            all_current_results = (
                retrieval_state.semantic_results + 
                retrieval_state.temporal_results + 
                retrieval_state.keyword_results + 
                retrieval_state.hierarchical_results
            )
            
            if not all_current_results:
                self.logger.info("⏭️ Skip contextual retrieval: no base retrieval results")
                return retrieval_state.to_dict()
            
            self.logger.info(f"🔗 Start contextual retrieval, base result count: {len(all_current_results)}")
            
            # Initialize storage manager
            if not self.storage_manager:
                self.storage_manager = await get_memory_storage_manager_async()
            
            # Perform contextual retrieval
            results = await self._perform_contextual_search(retrieval_state, all_current_results)
            
            # Process and mark results
            processed_results = await self._process_results(results, retrieval_state)
            
            retrieval_state.contextual_results = processed_results
            retrieval_state.total_memories_searched += len(processed_results)
            
            self.logger.info(f"🔗 Contextual retrieval complete: {len(processed_results)} results")
            
            # Convert back to dictionary format and return
            return retrieval_state.to_dict()
            
        except Exception as e:
            self.logger.error(f"❌ Contextual retrieval failed: {str(e)}")
            state["errors"] = state.get("errors", []) + [f"Contextual retrieval failed: {str(e)}"]
            state["success"] = False
            return state
    
    async def _perform_contextual_search(self, state: RetrievalState, base_results: List[Dict[str, Any]]) -> List[Any]:
        """Perform context-based retrieval"""
        all_results = []
        
        try:
            # Only expand context for top-scoring results to avoid over-expansion
            top_results = sorted(base_results, 
                               key=lambda x: x.get("retrieval_score", 0.0), 
                               reverse=True)[:5]
            
            for i, result in enumerate(top_results):
                self.logger.info(f"Expanding context for base result #{i+1}: {result.get('id', 'unknown')}")
                
                # Get related memories
                related_memories = await self._get_related_memories(result)
                
                # Add context information to related memories
                for related in related_memories:
                    related.context_parent_id = result.get("id", "")
                    related.context_parent_score = result.get("retrieval_score", 0.6)
                    related.context_relation_type = getattr(related, 'relation_type', 'child')
                
                all_results.extend(related_memories)
                
                self.logger.info(f"Expanded from result {result.get('id', 'unknown')} to {len(related_memories)} related memories")
            
            return all_results
            
        except Exception as e:
            self.logger.error(f"Contextual retrieval execution failed: {str(e)}")
            raise
    
    async def _get_related_memories(self, memory: Dict[str, Any]) -> List[Any]:
        """Get related memories"""
        related_memories = []
        
        try:
            memory_id = memory.get("id", "")
            if not memory_id:
                return related_memories
            
            # 1. Get related memories via child memory IDs
            child_ids = memory.get("child_memory_ids", [])
            if child_ids:
                for child_id in child_ids[:3]:  # Limit count to avoid over-expansion
                    try:
                        child_memory = await self.storage_manager.sql_adapter.retrieve_memory(child_id)
                        if child_memory:
                            child_memory.relation_type = 'child'
                            related_memories.append(child_memory)
                    except Exception as e:
                        self.logger.warning(f"Failed to get child memory {child_id}: {e}")
                        continue
            
            # 2. Get related memories via historical memory IDs
            historical_ids = memory.get("historical_memory_ids", [])
            if historical_ids:
                for hist_id in historical_ids[:2]:  # Limit count
                    try:
                        hist_memory = await self.storage_manager.sql_adapter.retrieve_memory(hist_id)
                        if hist_memory:
                            hist_memory.relation_type = 'historical'
                            related_memories.append(hist_memory)
                    except Exception as e:
                        self.logger.warning(f"Failed to get historical memory {hist_id}: {e}")
                        continue
            
            # 3. Get related memories via relation field
            relations = memory.get("relations", [])
            if relations:
                for relation in relations[:3]:  # Limit count
                    try:
                        if isinstance(relation, dict):
                            target_id = relation.get("target_memory_id", "")
                            relation_type = relation.get("relation_type", "related")
                        else:
                            target_id = getattr(relation, 'target_memory_id', "")
                            relation_type = getattr(relation, 'relation_type', "related")
                        
                        if target_id:
                            related_memory = await self.storage_manager.sql_adapter.retrieve_memory(target_id)
                            if related_memory:
                                related_memory.relation_type = relation_type
                                related_memories.append(related_memory)
                    except Exception as e:
                        self.logger.warning(f"Failed to get relation memory: {e}")
                        continue
            
            # 4. Get related memories based on same session ID (applicable to L1 memories)
            if memory.get("level") == "L1":
                session_id = memory.get("session_id", "")
                if session_id:
                    try:
                        # Find other memories in the same session
                        query = {
                            "user_id": memory.get("user_id", ""),
                            "expert_id": memory.get("expert_id", ""),
                            "session_id": session_id
                        }
                        options = {"limit": 3}  # Limit count
                        
                        session_memories = await self.storage_manager.sql_adapter.search_memories(query, options)
                        for session_memory in session_memories:
                            if getattr(session_memory, 'id', '') != memory_id:  # Exclude self
                                session_memory.relation_type = 'session'
                                related_memories.append(session_memory)
                    except Exception as e:
                        self.logger.warning(f"Failed to get session-related memories: {e}")
            
            self.logger.info(f"Retrieved {len(related_memories)} related memories")
            return related_memories
            
        except Exception as e:
            self.logger.error(f"Failed to get related memories: {str(e)}")
            return []
    
    async def _process_results(self, results: List[Any], state: RetrievalState) -> List[Dict[str, Any]]:
        """Process contextual retrieval results"""
        processed_results = []
        
        # Deduplicate (based on ID)
        seen_ids = set()
        
        for i, result in enumerate(results):
            try:
                # Get result ID
                result_id = getattr(result, 'id', f"contextual_{i}")
                if result_id in seen_ids:
                    continue
                seen_ids.add(result_id)
                
                # Convert to dictionary format
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
                
                # Add retrieval source information
                result_dict["retrieval_source"] = "contextual"
                
                # Get context-related information
                context_parent_id = getattr(result, 'context_parent_id', '')
                context_parent_score = getattr(result, 'context_parent_score', 0.6)
                relation_type = getattr(result, 'relation_type', 'related')
                
                result_dict["context_parent_id"] = context_parent_id
                result_dict["relation_type"] = relation_type
                
                # Calculate contextual relevance score
                # Contextual memory score is based on parent memory score with certain discount
                relation_weights = {
                    'child': 0.9,      # Child memory has higher weight
                    'historical': 0.8, # Historical memory has medium weight
                    'session': 0.7,    # Session memory has medium weight
                    'related': 0.6,    # General relation has lower weight
                }
                
                relation_weight = relation_weights.get(relation_type, 0.6)
                contextual_score = context_parent_score * relation_weight
                
                result_dict["retrieval_score"] = contextual_score
                
                # Apply contextual weight
                contextual_weight = state.retrieval_params.get("contextual_weight", 0.6)
                result_dict["weighted_score"] = contextual_score * contextual_weight
                
                processed_results.append(result_dict)
                
            except Exception as e:
                self.logger.warning(f"Processing contextual retrieval result[{i}] failed: {str(e)}")
                continue
        
        # Sort by contextual relevance
        processed_results.sort(key=lambda x: x.get("retrieval_score", 0.0), reverse=True)
        
        self.logger.info(f"Contextual retrieval result processing complete: {len(processed_results)} valid results")
        
        return processed_results
