"""
PostgreSQL Full-Text Search Node
Specialized handling of PostgreSQL's ts_vector and BM25 full-text search functionality
Resolves retrieval issues with semantic similarity but factual conflicts
"""

from typing import Dict, List, Any, Optional
import asyncio

from timem.workflows.retrieval_state import RetrievalState, RetrievalStrategy
from storage.postgres_adapter import get_postgres_adapter
from storage.memory_storage_manager import get_memory_storage_manager_async
from timem.utils.logging import get_logger

logger = get_logger(__name__)


class FullTextRetriever:
    """
    PostgreSQL Full-Text Search Node
    Leverages PostgreSQL's powerful full-text search capabilities to solve exact matching problems
    """
    
    def __init__(self, 
                 storage_manager=None,
                 postgres_adapter=None):
        """
        Initialize the full-text search node
        
        Args:
            storage_manager: Storage manager
            postgres_adapter: PostgreSQL adapter
        """
        self.storage_manager = storage_manager
        self.postgres_adapter = postgres_adapter
        self.logger = get_logger(__name__)

    async def _get_storage_manager(self):
        """Get the storage manager"""
        if self.storage_manager is None:
            self.storage_manager = await get_memory_storage_manager_async()
        return self.storage_manager

    async def _get_postgres_adapter(self):
        """Get the PostgreSQL adapter"""
        if self.postgres_adapter is None:
            self.postgres_adapter = await get_postgres_adapter()
        return self.postgres_adapter

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run full-text search
        
        Args:
            state: Workflow state dictionary
            
        Returns:
            Updated state dictionary
        """
        try:
            # Convert to RetrievalState object
            retrieval_state = self._dict_to_state(state)
            
            # Check if full-text search needs to be executed
            if RetrievalStrategy.FULLTEXT not in retrieval_state.selected_strategies:
                self.logger.info("Skip full-text search (strategy not selected)")
                return self._state_to_dict(retrieval_state)

            self.logger.info("Start PostgreSQL full-text search")
            
            # Execute full-text search
            results = await self._perform_fulltext_search(retrieval_state)
            
            # Update state
            retrieval_state.fulltext_results = results
            retrieval_state.total_memories_searched += len(results)
            
            self.logger.info(f"PostgreSQL full-text search completed: {len(results)} results")
            
            return self._state_to_dict(retrieval_state)
            
        except Exception as e:
            self.logger.error(f"❌ PostgreSQL full-text search failed: {str(e)}")
            state["errors"] = state.get("errors", []) + [f"Full-text search failed: {str(e)}"]
            state["success"] = False
            return state

    async def _perform_fulltext_search(self, state: RetrievalState) -> List[Dict[str, Any]]:
        """Execute PostgreSQL full-text search"""
        try:
            postgres_adapter = await self._get_postgres_adapter()
            
            # 🔧 Optimization: Avoid duplicate tokenization
            # state.question needs tokenization, state.key_entities is already a keyword list
            from timem.utils.chinese_tokenizer import tokenize_for_postgres, prepare_keywords_for_postgres
            
            # Tokenize the question
            question_tokenized = tokenize_for_postgres(state.question, is_tokenized=False)
            
            # Key entities are already tokenized, prepare them directly
            keywords_prepared = prepare_keywords_for_postgres(state.key_entities) if state.key_entities else ""
            
            # Combine tokenization results
            query_components = [question_tokenized]
            if keywords_prepared:
                query_components.append(keywords_prepared)
            
            query_text = " ".join(query_components)
            
            # Execute BM25 search (marked as tokenized)
            bm25_results = await postgres_adapter.search_memories_bm25(
                query_text=query_text,
                user_id=state.user_id,
                expert_id=state.expert_id,
                limit=state.retrieval_params.get("max_results_per_strategy", 20),
                is_tokenized=True  # Already tokenized at application layer
            )
            
            # Process results, add retrieval metadata
            processed_results = []
            for i, result in enumerate(bm25_results):
                result_dict = {
                    **result,
                    "retrieval_strategy": RetrievalStrategy.FULLTEXT.value,
                    "retrieval_source": "postgres_bm25",
                    "fulltext_rank": i + 1,
                    "bm25_score": result.get("bm25_score", 0.0),
                    "ts_rank_score": result.get("ts_rank_score", 0.0),
                    "sorting_method": "bm25"
                }
                processed_results.append(result_dict)
            
            # Execute standard ts_rank search in parallel as supplement
            tsrank_results = await self._perform_tsrank_search(state, postgres_adapter)
            
            # Merge two types of search results, BM25 takes priority
            combined_results = self._merge_fulltext_results(processed_results, tsrank_results)
            
            return combined_results
            
        except Exception as e:
            self.logger.error(f"PostgreSQL full-text search execution failed: {str(e)}")
            return []

    async def _perform_tsrank_search(self, state: RetrievalState, postgres_adapter) -> List[Dict[str, Any]]:
        """Execute ts_rank supplementary search"""
        try:
            # Use PostgreSQL native ts_rank
            store = await postgres_adapter._ensure_store()
            
            # 🔧 Optimization: Avoid duplicate tokenization
            from timem.utils.chinese_tokenizer import tokenize_for_postgres, prepare_keywords_for_postgres
            
            question_tokenized = tokenize_for_postgres(state.question, is_tokenized=False)
            keywords_prepared = prepare_keywords_for_postgres(state.key_entities) if state.key_entities else ""
            
            query_components = [question_tokenized]
            if keywords_prepared:
                query_components.append(keywords_prepared)
            query_text = " ".join(query_components)
            
            tsrank_results = await store.search_memories_fulltext(
                query_text=query_text,
                user_id=state.user_id,
                expert_id=state.expert_id,
                limit=10,  # Fewer supplementary results
                use_bm25=False,  # Use ts_rank
                is_tokenized=True  # Already tokenized
            )
            
            # Add retrieval metadata
            processed_results = []
            for i, result in enumerate(tsrank_results):
                result_dict = {
                    **result,
                    "retrieval_strategy": RetrievalStrategy.FULLTEXT.value,
                    "retrieval_source": "postgres_tsrank",
                    "tsrank_rank": i + 1,
                    "sorting_method": "ts_rank"
                }
                processed_results.append(result_dict)
            
            return processed_results
            
        except Exception as e:
            self.logger.warning(f"ts_rank supplementary search failed: {e}")
            return []

    def _merge_fulltext_results(self, bm25_results: List[Dict[str, Any]], 
                               tsrank_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Merge BM25 and ts_rank search results"""
        
        # Use memory ID as key to avoid duplicates
        seen_memory_ids = set()
        merged_results = []
        
        # Add BM25 results first
        for result in bm25_results:
            memory_id = result.get("id")
            if memory_id and memory_id not in seen_memory_ids:
                result["fulltext_method"] = "bm25_primary"
                merged_results.append(result)
                seen_memory_ids.add(memory_id)
        
        # Add ts_rank-only results
        for result in tsrank_results:
            memory_id = result.get("id")
            if memory_id and memory_id not in seen_memory_ids:
                result["fulltext_method"] = "tsrank_supplement"
                merged_results.append(result)
                seen_memory_ids.add(memory_id)
        
        self.logger.info(f"Merge full-text search results: BM25({len(bm25_results)}) + ts_rank({len(tsrank_results)}) = {len(merged_results)}")
        
        return merged_results

    def _dict_to_state(self, state_dict: Dict[str, Any]) -> RetrievalState:
        """Convert dictionary to RetrievalState object"""
        try:
            return RetrievalState.from_dict(state_dict)
        except Exception as e:
            self.logger.error(f"State conversion failed: {e}")
            # Return basic state
            return RetrievalState(
                question=state_dict.get("question", ""),
                user_id=state_dict.get("user_id", ""),
                expert_id=state_dict.get("expert_id", ""),
                selected_strategies=state_dict.get("selected_strategies", [])
            )

    def _state_to_dict(self, state: RetrievalState) -> Dict[str, Any]:
        """Convert RetrievalState object to dictionary"""
        try:
            return state.to_dict()
        except Exception as e:
            self.logger.error(f"State conversion failed: {e}")
            return {
                "question": state.question,
                "user_id": state.user_id,
                "expert_id": state.expert_id,
                "success": True,
                "fulltext_results": getattr(state, 'fulltext_results', [])
            }


class AdvancedFullTextRetriever(FullTextRetriever):
    """
    Advanced Full-Text Retriever
    Implements intelligent combination of multiple PostgreSQL full-text search strategies
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.search_strategies = {
            "exact_match": self._exact_match_search,
            "phrase_search": self._phrase_search,
            "fuzzy_search": self._fuzzy_search,
            "semantic_fulltext": self._semantic_fulltext_search
        }

    async def _exact_match_search(self, state: RetrievalState) -> List[Dict[str, Any]]:
        """Exact match search, solves sunrise vs sunset problem"""
        postgres_adapter = await self._get_postgres_adapter()
        store = await postgres_adapter._ensure_store()
        
        exact_results = []
        
        # Perform exact match for each key entity
        for entity in state.key_entities:
            try:
                # Use PostgreSQL's exact phrase matching (supports mixed Chinese-English)
                query_sql = """
                SELECT *, 
                       ts_rank_cd(content_tsvector || title_tsvector, phraseto_tsquery('timem_config', %s)) as exact_score
                FROM core_memories 
                WHERE (content_tsvector || title_tsvector) @@ phraseto_tsquery('timem_config', %s)
                AND (%s = ANY(string_to_array(lower(content), ' ')) OR %s = ANY(string_to_array(lower(title), ' ')))
                ORDER BY exact_score DESC
                LIMIT 10
                """
                
                # Here we need to execute native SQL in PostgreSQL
                # Simplified implementation: use existing BM25 search with added exact match scoring
                entity_results = await postgres_adapter.search_memories_bm25(
                    query_text=f'"{entity}"',  # Use quotes for phrase search
                    user_id=state.user_id,
                    expert_id=state.expert_id,
                    limit=10
                )
                
                for result in entity_results:
                    # Check if entity appears exactly in content
                    content = result.get("content", "").lower()
                    title = result.get("title", "").lower()
                    
                    if entity.lower() in content.split() or entity.lower() in title.split():
                        result["exact_match_entity"] = entity
                        result["exact_match_score"] = result.get("bm25_score", 0.0) * 1.2  # Exact match weighting
                        exact_results.append(result)
                        
            except Exception as e:
                self.logger.warning(f"Exact match search failed for '{entity}': {e}")
        
        return exact_results

    async def _phrase_search(self, state: RetrievalState) -> List[Dict[str, Any]]:
        """Phrase search, preserves word order"""
        postgres_adapter = await self._get_postgres_adapter()
        
        # Search the question as a phrase
        phrase_query = f'"{state.question}"'
        
        phrase_results = await postgres_adapter.search_memories_bm25(
            query_text=phrase_query,
            user_id=state.user_id,
            expert_id=state.expert_id,
            limit=15
        )
        
        for result in phrase_results:
            result["search_type"] = "phrase"
            result["phrase_match_score"] = result.get("bm25_score", 0.0)
        
        return phrase_results

    async def _fuzzy_search(self, state: RetrievalState) -> List[Dict[str, Any]]:
        """Fuzzy search, handles spelling variants"""
        postgres_adapter = await self._get_postgres_adapter()
        store = await postgres_adapter._ensure_store()
        
        # Here we can implement PostgreSQL's trigram similarity search (pg_trgm extension)
        # Currently using standard BM25, can be extended in the future
        fuzzy_results = await postgres_adapter.search_memories_bm25(
            query_text=state.question,
            user_id=state.user_id,
            expert_id=state.expert_id,
            limit=15
        )
        
        for result in fuzzy_results:
            result["search_type"] = "fuzzy"
            result["fuzzy_match_score"] = result.get("bm25_score", 0.0)
        
        return fuzzy_results

    async def _semantic_fulltext_search(self, state: RetrievalState) -> List[Dict[str, Any]]:
        """Semantic full-text search, combines semantic understanding with full-text matching"""
        postgres_adapter = await self._get_postgres_adapter()
        
        # Expand query: add synonyms and related concepts
        expanded_query = await self._expand_query(state.question, state.key_entities)
        
        semantic_results = await postgres_adapter.search_memories_bm25(
            query_text=expanded_query,
            user_id=state.user_id,
            expert_id=state.expert_id,
            limit=20
        )
        
        for result in semantic_results:
            result["search_type"] = "semantic_fulltext"
            result["expanded_query"] = expanded_query
            result["semantic_fulltext_score"] = result.get("bm25_score", 0.0)
        
        return semantic_results

    async def _expand_query(self, question: str, entities: List[str]) -> str:
        """Expand query, add synonyms and related concepts"""
        # Simplified query expansion, can integrate dictionary or LLM in the future
        expansion_map = {
            "sunrise": "sunrise dawn morning daybreak",
            "sunset": "sunset dusk evening twilight", 
            "paint": "paint draw sketch create art",
            "when": "when time date",
            "where": "where location place"
        }
        
        expanded_terms = [question]
        
        for entity in entities:
            entity_lower = entity.lower()
            if entity_lower in expansion_map:
                expanded_terms.append(expansion_map[entity_lower])
            else:
                expanded_terms.append(entity)
        
        expanded_query = " ".join(expanded_terms)
        self.logger.info(f"Query expansion: '{question}' -> '{expanded_query}'")
        
        return expanded_query

    async def _perform_fulltext_search(self, state: RetrievalState) -> List[Dict[str, Any]]:
        """Execute multi-strategy full-text search"""
        all_results = []
        
        try:
            # Execute multiple retrieval strategies in parallel
            search_tasks = []
            
            # 1. Exact match search (highest priority)
            search_tasks.append(self._exact_match_search(state))
            
            # 2. Phrase search
            search_tasks.append(self._phrase_search(state))
            
            # 3. Semantic full-text search
            search_tasks.append(self._semantic_fulltext_search(state))
            
            # 4. Fuzzy search (as supplement)
            search_tasks.append(self._fuzzy_search(state))
            
            # Execute all searches in parallel
            search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
            
            # Merge results
            for i, results in enumerate(search_results):
                if isinstance(results, Exception):
                    self.logger.warning(f"Search strategy {i} failed: {results}")
                    continue
                
                if isinstance(results, list):
                    all_results.extend(results)
            
            # Deduplicate and rank
            deduplicated_results = self._deduplicate_and_rank(all_results)
            
            self.logger.info(f"Full-text search merge results: {len(all_results)} -> {len(deduplicated_results)} (after deduplication)")
            
            return deduplicated_results
            
        except Exception as e:
            self.logger.error(f"Multi-strategy full-text search failed: {e}")
            return []

    def _deduplicate_and_rank(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Deduplicate and re-rank full-text search results"""
        
        # Deduplicate by memory ID, keep the highest-scoring version
        memory_scores = {}
        memory_results = {}
        
        for result in results:
            memory_id = result.get("id")
            if not memory_id:
                continue
            
            # Calculate combined score
            combined_score = self._calculate_combined_fulltext_score(result)
            
            if memory_id not in memory_scores or combined_score > memory_scores[memory_id]:
                memory_scores[memory_id] = combined_score
                result["combined_fulltext_score"] = combined_score
                memory_results[memory_id] = result
        
        # Sort by combined score
        sorted_results = sorted(
            memory_results.values(),
            key=lambda x: x.get("combined_fulltext_score", 0.0),
            reverse=True
        )
        
        return sorted_results[:20]  # Return top 20

    def _calculate_combined_fulltext_score(self, result: Dict[str, Any]) -> float:
        """Calculate combined full-text search score"""
        base_score = 0.0
        
        # BM25 score (highest weight)
        bm25_score = result.get("bm25_score", 0.0)
        if bm25_score > 0:
            base_score += bm25_score * 0.6
        
        # Exact match bonus
        if result.get("exact_match_entity"):
            base_score += 0.3
        
        # ts_rank score
        ts_rank_score = result.get("ts_rank_score", 0.0) 
        if ts_rank_score > 0:
            base_score += ts_rank_score * 0.2
        
        # Search type weight
        search_type = result.get("search_type", "")
        type_weights = {
            "exact": 1.0,
            "phrase": 0.9,
            "semantic_fulltext": 0.8,
            "fuzzy": 0.7
        }
        
        type_weight = type_weights.get(search_type, 0.5)
        base_score *= type_weight
        
        return min(1.0, base_score)  # Limit to 0-1 range

    def _dict_to_state(self, state_dict: Dict[str, Any]) -> RetrievalState:
        """Convert dictionary to state object (simplified implementation)"""
        return RetrievalState(
            question=state_dict.get("question", ""),
            user_id=state_dict.get("user_id", ""),
            expert_id=state_dict.get("expert_id", ""),
            key_entities=state_dict.get("key_entities", []),
            selected_strategies=state_dict.get("selected_strategies", []),
            retrieval_params=state_dict.get("retrieval_params", {})
        )

    def _state_to_dict(self, state: RetrievalState) -> Dict[str, Any]:
        """Convert state object to dictionary (simplified implementation)"""
        return {
            "question": state.question,
            "user_id": state.user_id,
            "expert_id": state.expert_id,
            "key_entities": state.key_entities,
            "selected_strategies": state.selected_strategies,
            "retrieval_params": state.retrieval_params,
            "fulltext_results": getattr(state, 'fulltext_results', []),
            "total_memories_searched": getattr(state, 'total_memories_searched', 0),
            "success": True
        }
