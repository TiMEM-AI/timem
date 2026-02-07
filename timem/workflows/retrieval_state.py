"""
TiMem memory retrieval state management

Define state classes and validators for retrieval workflow to ensure data flow integrity and consistency.
"""

from typing import Dict, List, Any, Optional, Union
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime

from timem.utils.logging import get_logger

logger = get_logger(__name__)


class QueryCategory(Enum):
    """Query type classification"""
    FACTUAL = 1      # Factual query
    TEMPORAL = 2     # Temporal query  
    INFERENTIAL = 3  # Inferential query
    DETAILED = 4     # Detailed information query
    ADVERSARIAL = 5  # Adversarial query


class RetrievalStrategy(Enum):
    """Retrieval strategy type"""
    SEMANTIC = "semantic"           # Semantic retrieval
    TEMPORAL = "temporal"           # Temporal retrieval
    KEYWORD = "keyword"             # Keyword retrieval
    HIERARCHICAL = "hierarchical"   # Hierarchical retrieval
    CONTEXTUAL = "contextual"       # Contextual retrieval
    FULLTEXT = "fulltext"           # PostgreSQL full-text retrieval


@dataclass
class RetrievalState:
    """Retrieval workflow state"""
    # Input
    question: str = ""
    user_id: str = ""
    expert_id: str = ""
    user_name: str = ""  # User name
    expert_name: str = ""  # Expert name
    character_ids: List[str] = field(default_factory=list)  # List of all related character IDs
    # User group isolation related fields
    user_group_ids: List[str] = field(default_factory=list)  # User group ID list for isolation retrieval
    user_group_filter: Dict[str, Any] = field(default_factory=dict)  # User group filter configuration
    context: Dict[str, Any] = field(default_factory=dict)
    retrieval_config: Dict[str, Any] = field(default_factory=dict)  # Retrieval configuration parameters
    
    # Question analysis results
    query_category: Optional[QueryCategory] = None
    time_entities: List[Dict[str, Any]] = field(default_factory=list)
    key_entities: List[str] = field(default_factory=list)
    query_intent: str = ""
    
    # Retrieval strategy
    selected_strategies: List[RetrievalStrategy] = field(default_factory=list)
    retrieval_params: Dict[str, Any] = field(default_factory=dict)
    
    # Retrieval results
    semantic_results: List[Dict[str, Any]] = field(default_factory=list)
    temporal_results: List[Dict[str, Any]] = field(default_factory=list)
    keyword_results: List[Dict[str, Any]] = field(default_factory=list)
    hierarchical_results: List[Dict[str, Any]] = field(default_factory=list)
    contextual_results: List[Dict[str, Any]] = field(default_factory=list)
    fulltext_results: List[Dict[str, Any]] = field(default_factory=list)
    
    # Fused results
    fused_results: List[Dict[str, Any]] = field(default_factory=list)
    ranked_results: List[Dict[str, Any]] = field(default_factory=list)
    
    # Answer generation
    answer: str = ""
    confidence: float = 0.0
    evidence: List[str] = field(default_factory=list)
    formatted_context_memories: List[str] = field(default_factory=list)  # Formatted context memories (for test reports)
    
    # Multi-Stage COT related fields (Multi-Stage Chain-of-Thought)
    use_multi_stage_cot: bool = False  # Whether to enable multi-stage COT
    cot_evidence: Optional[Dict[str, Any]] = None  # Stage 1: Evidence collection result
    cot_reasoning: Optional[Union[Dict[str, Any], str]] = None  # Stage 2: Deep reasoning result (multi-step COT is dict, single-step COT is string)
    cot_final_answer: Optional[str] = None  # Stage 3: Concise final answer
    cot_full_reasoning: Optional[str] = None  # Complete reasoning chain (for debugging)
    cot_stage_times: Dict[str, float] = field(default_factory=dict)  # Time spent in each stage
    cot_stage_tokens: Dict[str, int] = field(default_factory=dict)  # Token usage in each stage
    
    # Single-Step COT related fields (Single-Step Chain-of-Thought)
    use_single_cot: bool = False  # Whether to use single-step COT mode
    cot_full_response: str = ""  # Complete COT response (contains REASONING and FINAL_ANSWER)
    cot_format_valid: bool = False  # Whether COT format is valid
    cot_retry_count: int = 0  # COT format retry count
    
    # Metadata
    retrieval_time: float = 0.0
    total_memories_searched: int = 0
    strategy_performance: Dict[str, float] = field(default_factory=dict)
    
    # Memory refining related fields
    memory_refined: bool = False  # Whether memory refining is applied
    memory_refiner_failed: bool = False  # Whether refining failed (fallback to no refining)
    original_memory_count: int = 0  # Number of memories before refining
    refined_memory_count: int = 0  # Number of memories after refining
    refinement_retention_rate: float = 0.0  # Retention rate (0.0-1.0)
    memory_refiner_metadata: Dict[str, Any] = field(default_factory=dict)  # Refiner metadata (reasoning, retry count, etc.)
    
    # Error handling
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def validate(self) -> List[str]:
        """Validate state integrity"""
        errors = []
        
        # Check required fields
        if not self.question.strip():
            errors.append("Question cannot be empty")
            
        # Check character information
        if not self.user_id and not self.expert_id and not self.character_ids:
            if not self.user_name and not self.expert_name:
                # This is acceptable, meaning character needs to be parsed from question
                pass
            
        return errors
    
    def copy(self) -> 'RetrievalState':
        """Create state copy"""
        return RetrievalState(
            question=self.question,
            user_id=self.user_id,
            expert_id=self.expert_id,
            user_name=self.user_name,
            expert_name=self.expert_name,
            character_ids=self.character_ids.copy(),
            user_group_ids=self.user_group_ids.copy(),
            user_group_filter=self.user_group_filter.copy(),
            context=self.context.copy(),
            retrieval_config=self.retrieval_config.copy(),
            query_category=self.query_category,
            time_entities=self.time_entities.copy(),
            key_entities=self.key_entities.copy(),
            query_intent=self.query_intent,
            selected_strategies=self.selected_strategies.copy(),
            retrieval_params=self.retrieval_params.copy(),
            semantic_results=self.semantic_results.copy(),
            temporal_results=self.temporal_results.copy(),
            keyword_results=self.keyword_results.copy(),
            hierarchical_results=self.hierarchical_results.copy(),
            contextual_results=self.contextual_results.copy(),
            fused_results=self.fused_results.copy(),
            ranked_results=self.ranked_results.copy(),
            answer=self.answer,
            confidence=self.confidence,
            evidence=self.evidence.copy(),
            formatted_context_memories=self.formatted_context_memories.copy(),
            # Multi-stage COT fields
            use_multi_stage_cot=self.use_multi_stage_cot,
            cot_evidence=self.cot_evidence,
            cot_reasoning=self.cot_reasoning,
            cot_final_answer=self.cot_final_answer,
            cot_full_reasoning=self.cot_full_reasoning,
            cot_stage_times=self.cot_stage_times.copy(),
            cot_stage_tokens=self.cot_stage_tokens.copy(),
            # Metadata
            retrieval_time=self.retrieval_time,
            total_memories_searched=self.total_memories_searched,
            strategy_performance=self.strategy_performance.copy(),
            errors=self.errors.copy(),
            warnings=self.warnings.copy()
        )


class RetrievalStateValidator:
    """Retrieval state validator"""
    
    def __init__(self):
        self.logger = get_logger(__name__)
    
    def validate_input(self, state: Union[RetrievalState, Dict[str, Any]]) -> List[str]:
        """Validate input state"""
        errors = []
        
        if isinstance(state, dict):
            # Validate from dictionary
            if not state.get("question", "").strip():
                errors.append("Question cannot be empty")
        elif isinstance(state, RetrievalState):
            # Validate from state object
            errors.extend(state.validate())
        else:
            errors.append(f"Unsupported state type: {type(state)}")
            
        return errors
    
    def validate_character_resolution(self, state: RetrievalState) -> List[str]:
        """Validate character resolution result"""
        warnings = []
        
        if not state.character_ids and not state.user_id and not state.expert_id:
            warnings.append("No character ID found, will perform comprehensive retrieval")
            
        return warnings
    
    def validate_query_analysis(self, state: RetrievalState) -> List[str]:
        """Validate retrieval-planning results."""
        warnings = []
        
        if not state.query_category:
            warnings.append("Query category not determined")
            
        if not state.key_entities:
            warnings.append("No key entities extracted")
            
        return warnings
    
    def validate_retrieval_results(self, state: RetrievalState) -> List[str]:
        """Validate retrieval results"""
        warnings = []
        
        if not state.semantic_results and RetrievalStrategy.SEMANTIC in state.selected_strategies:
            warnings.append("Semantic retrieval returned no results")
            
        if not state.fused_results:
            warnings.append("No retrieval results found")
            
        return warnings
    
    def validate_final_output(self, state: RetrievalState) -> List[str]:
        """Validate final output"""
        errors = []
        
        if not state.answer.strip():
            errors.append("No answer generated")
            
        if state.confidence < 0.0 or state.confidence > 1.0:
            errors.append(f"Confidence out of range: {state.confidence}")
            
        return errors


def create_initial_retrieval_state(input_data: Dict[str, Any]) -> RetrievalState:
    """Create initial retrieval state"""
    return RetrievalState(
        question=input_data.get("question", ""),
        user_id=input_data.get("user_id", ""),
        expert_id=input_data.get("expert_id", ""),
        user_name=input_data.get("user_name", ""),
        expert_name=input_data.get("expert_name", ""),
        character_ids=input_data.get("character_ids", []),
        user_group_ids=input_data.get("user_group_ids", []),
        user_group_filter=input_data.get("user_group_filter", {}),
        context=input_data.get("context", {}),
        retrieval_config=input_data.get("retrieval_config", {})
    )