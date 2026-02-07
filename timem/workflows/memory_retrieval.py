"""
TiMem Memory Retrieval Workflow (Refactored Version)

Intelligent memory retrieval system based on LangGraph, adopting modular node architecture with support for multiple retrieval strategies.
The refactored version provides clearer responsibility separation, better maintainability and extensibility.
"""

import asyncio
import sys
import time
import traceback
from datetime import datetime
from typing import Dict, List, Any, Optional
import atexit

from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph

from timem.workflows.retrieval_state import (
    RetrievalState, RetrievalStateValidator, create_initial_retrieval_state
)
from timem.workflows.retrieval_nodes import (
    CharacterResolver, AnswerGenerator
)
from timem.workflows.retrieval_nodes.llm_retrieval_planner import LLMRetrievalPlanner
# V1 Retrievers (Original Version)
from timem.workflows.retrieval_nodes.simple_retriever import SimpleRetriever
from timem.workflows.retrieval_nodes.hybrid_retriever import HybridRetriever
from timem.workflows.retrieval_nodes.complex_retriever import ComplexRetriever
from timem.utils.logging import get_logger
from timem.utils.config_manager import get_app_config
from timem.utils.retrieval_config_manager import get_retrieval_config_manager

logger = get_logger(__name__)


class MemoryRetrievalWorkflow:
    """
    Memory Retrieval Workflow Class (Intelligent Hierarchical Version + Bottom-Up Refactored Version)
    
    Responsible for coordinating the complete memory retrieval process, adopting intelligent hierarchical retrieval architecture:
    1. Character Name Resolution (CharacterResolver)
    2. LLM Retrieval Planning (LLMRetrievalPlanner) - Intelligent query complexity analysis and keyword extraction
    3. Intelligent Retrieval Strategy Selection:
       V1 (Original Version):
       - Simple Retrieval (SimpleRetriever) - Complexity 0: L1(top5) + L2(top1)
       - Hybrid Retrieval (HybridRetriever) - Complexity 1: L1(top5) + L2(top1) + L3(top1) + L4(top1)
       - Complex Retrieval (ComplexRetriever) - Complexity 2: L3(top2) + L4(top1) + L5(top1)
       
       V2 (Bottom-Up Refactored Version):
       - Simple Retrieval (SimpleRetriever) - L1(top5) → session scoring → Best session's L2
       - Hybrid Retrieval (HybridRetriever) - L1(top5) → session scoring → Best session's L3 daily report + L4 weekly report
       - Complex Retrieval (ComplexRetriever) - L1(top5) → session scoring → Best session's L5 monthly profile
    4. Answer Generation (AnswerGenerator)
    
    Note: The cleanup() method should be called to release resources after use.
    """
    
    def __init__(self, 
                 config: Optional[Dict[str, Any]] = None,
                 state_validator: Optional[RetrievalStateValidator] = None,
                 debug_mode: bool = False,
                 use_v2_retrievers: bool = True,
                 retrieval_config_manager = None):  # 🔧 Engineering-level refactoring: Support dependency injection of config manager
        """
        Initialize workflow (synchronous part)
        
        Args:
            config: Configuration information, auto-fetched if None
            state_validator: State validator, creates new instance if None
            debug_mode: Whether to enable debug mode
            use_v2_retrievers: Whether to use V2 Bottom-Up retrievers, default True
            retrieval_config_manager: Config manager instance (for ablation studies, uses global singleton if None)
        """
        self.config = config or get_app_config()
        self.state_validator = state_validator or RetrievalStateValidator()
        self.debug_mode = debug_mode
        self.use_v2_retrievers = use_v2_retrievers
        
        # Get retrieval config manager (supports dependency injection)
        self.retrieval_config_manager = retrieval_config_manager or get_retrieval_config_manager()
        
        # Check V2 retriever settings from config file
        if self.config and 'retrieval' in self.config:
            retrieval_config = self.config['retrieval']
            self.use_v2_retrievers = retrieval_config.get('use_v2_retrievers', self.use_v2_retrievers)
            # Ablation study: support a forced strategy (disables intelligent routing from the LLM retrieval planner)
            self.forced_strategy = retrieval_config.get('forced_strategy', None)
        else:
            self.forced_strategy = None
        
        # Workflow components and state
        self.app = None  # LangGraph application, compiled in async initialization
        self.graph = None  # LangGraph state graph
        self.nodes = {}  # Workflow node instances
        self.use_memory_refiner = False  # Whether to enable memory refiner, initialized in _build_graph
        
        self.logger = get_logger(__name__)
        self.logger.info(f"Initialize memory retrieval workflow, debug mode: {self.debug_mode}")
        
        # 🧪 Ablation study: Log forced strategy configuration
        if self.forced_strategy:
            self.logger.warning(f"🧪 Ablation study mode: Force use {self.forced_strategy.upper()} strategy (disable intelligent routing)")
            if self.debug_mode:
                print(f"🧪 Ablation study mode: Force use {self.forced_strategy.upper()} strategy")
    
    async def _async_init(self):
        """
        Async initialization part for building and compiling the graph
        
        Includes dependency injection, graph construction and compilation
        """
        logger.info(f"Initialize workflow, debug mode: {self.debug_mode}")
            
        # Build and compile graph
        self.graph = await self._build_graph()
        self.app = self.graph.compile()
        logger.info("Workflow graph compiled successfully")
    
    @classmethod
    async def create(cls, **kwargs):
        """
        Async factory method for creating and initializing workflow instances
        
        Args:
            **kwargs: Parameters passed to __init__
            
        Returns:
            Initialized workflow instance
        """
        instance = cls(**kwargs)
        await instance._async_init()
        return instance
    
    async def _build_graph(self) -> StateGraph:
        """
        Build workflow graph
        
        Create all node instances, set up dependency injection, build graph structure
        
        Returns:
            Built StateGraph object
        """
        if self.debug_mode:
            print("🔧 Building memory retrieval workflow graph...")
        
        logger.info("Start building workflow graph")
        
        # Create state graph - use Dict[str, Any] as state type
        # LangGraph requires concrete types rather than typing.Dict
        from typing import Dict as TypingDict, Any
        workflow = StateGraph(TypingDict[str, Any])
        
        # Create core node instances, inject dependencies
        self.nodes["character_resolver"] = CharacterResolver(
            state_validator=self.state_validator
        )
        
        self.nodes["llm_retrieval_planner"] = LLMRetrievalPlanner(
            debug_mode=self.debug_mode
        )
        
        # Choose retriever version based on configuration
        retriever_version = "Bottom-Up" if self.use_v2_retrievers else "V1 Original"
        logger.info(f"Using retriever version: {retriever_version}")
        
        if self.use_v2_retrievers:
            # Use Bottom-Up retrievers
            # Get configuration for each strategy
            simple_config = self.retrieval_config_manager.get_strategy_config("simple")
            hybrid_config = self.retrieval_config_manager.get_strategy_config("hybrid")
            complex_config = self.retrieval_config_manager.get_strategy_config("complex")
            
            self.nodes["simple_retriever"] = SimpleRetriever(
                state_validator=self.state_validator,
                strategy_config=simple_config
            )
            
            self.nodes["hybrid_retriever"] = HybridRetriever(
                state_validator=self.state_validator,
                strategy_config=hybrid_config
            )
            
            self.nodes["complex_retriever"] = ComplexRetriever(
                state_validator=self.state_validator,
                strategy_config=complex_config
            )
            
            if self.debug_mode:
                print("🔧 Using Bottom-Up retrievers")
        else:
            # Use V1 original retrievers (backward compatible)
            self.nodes["simple_retriever"] = SimpleRetriever(
                state_validator=self.state_validator
            )
            
            self.nodes["hybrid_retriever"] = HybridRetriever(
                state_validator=self.state_validator
            )
            
            self.nodes["complex_retriever"] = ComplexRetriever(
                state_validator=self.state_validator
            )
            
            if self.debug_mode:
                print("🔧 Using V1 original retrievers")
        
        # Choose answer generator based on configuration (single-stage vs multi-stage COT)
        answer_gen_config = self.retrieval_config_manager.get_config().get("answer_generation", {})
        answer_gen_mode = answer_gen_config.get("mode", "single")
        
        if answer_gen_mode == "multi_stage_cot" and answer_gen_config.get("multi_stage_cot", {}).get("enabled", False):
            # Use multi-stage COT answer generator
            from timem.workflows.retrieval_nodes.multi_stage_answer_generator import MultiStageAnswerGenerator
            
            # Create fallback single-stage generator
            fallback_generator = AnswerGenerator(state_validator=self.state_validator)
            
            self.nodes["answer_generator"] = MultiStageAnswerGenerator(
                state_validator=self.state_validator,
                fallback_generator=fallback_generator
            )
            logger.info("✨ Using multi-stage COT answer generator")
            if self.debug_mode:
                print("✨ Using multi-stage COT answer generator")
        else:
            # Use single-stage answer generator
            self.nodes["answer_generator"] = AnswerGenerator(
                state_validator=self.state_validator
            )
            logger.info("Using single-stage answer generator")
            if self.debug_mode:
                print("Using single-stage answer generator")
        
        # Create memory refiner node (if enabled)
        memory_refiner_config = self.retrieval_config_manager.get_config().get("memory_refiner", {})
        if memory_refiner_config.get("enabled", False):
            from timem.workflows.retrieval_nodes.memory_refiner import MemoryRefiner
            self.nodes["memory_refiner"] = MemoryRefiner(
                state_validator=self.state_validator,
                debug_mode=self.debug_mode
            )
            self.use_memory_refiner = True
            logger.info("✨ Enable memory refiner")
            if self.debug_mode:
                print("✨ Enable memory refiner")
        else:
            self.use_memory_refiner = False
            logger.info("🚫 Memory refiner disabled")
            if self.debug_mode:
                print("🚫 Memory refiner disabled")
        
        # Add core nodes to graph
        workflow.add_node("character_resolver", self.nodes["character_resolver"].run)
        workflow.add_node("llm_retrieval_planner", self._llm_retrieval_planner_wrapper)
        workflow.add_node("retrieval_router", self._retrieval_router)
        workflow.add_node("simple_retriever", self.nodes["simple_retriever"].run)
        workflow.add_node("hybrid_retriever", self.nodes["hybrid_retriever"].run)
        workflow.add_node("complex_retriever", self.nodes["complex_retriever"].run)
        
        # Add memory refiner node (if enabled)
        if self.use_memory_refiner:
            workflow.add_node("memory_refiner", self.nodes["memory_refiner"].run)
        
        workflow.add_node("answer_generator", self.nodes["answer_generator"].run)
        
        # Set entry point
        workflow.set_entry_point("character_resolver")
        
        # Set node connections - intelligent hierarchical retrieval process
        workflow.add_edge("character_resolver", "llm_retrieval_planner")
        workflow.add_edge("llm_retrieval_planner", "retrieval_router")
        
        # Conditional routing: Choose different retrievers based on retrieval strategy
        workflow.add_conditional_edges(
            "retrieval_router",
            self._route_retrieval_strategy,
            {
                "simple": "simple_retriever",
                "hybrid": "hybrid_retriever", 
                "complex": "complex_retriever"
            }
        )
        
        # ✨ Fix: Add conditional routing to decide whether to skip LLM generation or perform memory refining based on configuration
        # Dynamically build routing map, only include relevant routing when memory refiner is enabled
        if self.use_memory_refiner:
            retrieval_routes = {
                "memory_refiner": "memory_refiner",
                "answer_generation": "answer_generator",
                "direct_return": END
            }
        else:
            retrieval_routes = {
                "answer_generation": "answer_generator",
                "direct_return": END
            }
        
        workflow.add_conditional_edges(
            "simple_retriever",
            self._route_after_retrieval,
            retrieval_routes
        )
        
        workflow.add_conditional_edges(
            "hybrid_retriever", 
            self._route_after_retrieval,
            retrieval_routes
        )
        
        workflow.add_conditional_edges(
            "complex_retriever",
            self._route_after_retrieval,
            retrieval_routes
        )
        
        # Routing after memory refining (if enabled)
        if self.use_memory_refiner:
            workflow.add_conditional_edges(
                "memory_refiner",
                self._route_after_memory_refiner,
                {
                    "answer_generation": "answer_generator",
                    "direct_return": END
                }
            )
        
        # Reflection routing: Check if reflection is needed
        workflow.add_conditional_edges(
            "answer_generator",
            self._route_reflection,
            {
                "reflection": "reflection_handler",
                "end": END
            }
        )
        
        # Add reflection handler node
        workflow.add_node("reflection_handler", self._reflection_handler)
        workflow.add_edge("reflection_handler", "llm_retrieval_planner")
        
        logger.info("Workflow graph construction completed")
        if self.debug_mode:
            print("✅ Workflow graph construction completed")
            
        return workflow
    
    async def _llm_retrieval_planner_wrapper(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        LLM retrieval planner wrapper method, integrating LLMRetrievalPlanner into the workflow
        
        Args:
            state: Workflow state dictionary
            
        Returns:
            Updated state dictionary
        """
        try:
            question = state.get("question", "")
            if not question.strip():
                self.logger.warning("Question is empty; skipping LLM retrieval planning")
                return state
            
            self.logger.info(f"Start LLM retrieval planning: {question}")
            
            # Use LLMRetrievalPlanner to analyze query
            complexity, keywords = await self.nodes["llm_retrieval_planner"].analyze_query_complexity(question)
            
            # 🆕 Check if there is forced complexity override (for ablation studies)
            retrieval_config = self.retrieval_config_manager.get_config().get('retrieval', {})
            forced_complexity = retrieval_config.get('forced_complexity_level')
            
            if forced_complexity is not None:
                original_complexity = complexity
                complexity = forced_complexity
                self.logger.warning(f"🔧 Forced complexity override: {original_complexity} → {complexity}")
            
            # Update state
            state["query_complexity"] = complexity
            state["key_entities"] = keywords
            state["query_intent"] = f"Complexity level: {complexity}"
            
            # Set query category based on complexity
            if complexity == 0:
                state["query_category"] = "FACTUAL"
            elif complexity == 1:
                state["query_category"] = "MIXED"
            else:
                state["query_category"] = "INFERENTIAL"
            
            # Temporarily store retrieval-planning results; they will be merged into the final routing event later
            state["_query_analysis_temp"] = {
                "complexity": complexity,
                "complexity_desc": {0: "Simple query", 1: "Mixed query", 2: "Complex query"}.get(complexity, "Unknown"),
                "keywords": keywords,
                "forced_override": forced_complexity is not None  # Record if forced override
            }
            
            # ⚠️ Add detailed logging: record the set values
            self.logger.info("✅ LLM retrieval planner set state:")
            self.logger.info(f"   query_complexity = {state.get('query_complexity')}")
            self.logger.info(f"   query_category = {state.get('query_category')}")
            self.logger.info(f"   key_entities = {state.get('key_entities')}")
            if forced_complexity is not None:
                self.logger.info(f"   ⚠️ Forced complexity override in effect")
            
            return state
            
        except Exception as e:
            error_msg = f"LLM retrieval planning failed: {str(e)}"
            self.logger.error(error_msg)
            state["errors"] = state.get("errors", []) + [error_msg]
            return state
    
    async def _retrieval_router(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Retrieval router - Select retrieval strategy based on query complexity (restored normal routing logic)
        
        🧪 Ablation study support:
        - If forced_strategy is set, force use the specified strategy, skip intelligent routing
        
        Args:
            state: Workflow state dictionary
            
        Returns:
            Updated state dictionary containing retrieval strategy information
        """
        self.logger.warning("=" * 80)
        self.logger.warning("🔀 _retrieval_router method called!")
        self.logger.warning("=" * 80)
        try:
            # 🔧 Key fix: Dynamically read the latest configuration each time instead of using cached self.forced_strategy
            current_retrieval_config = self.retrieval_config_manager.get_config().get('retrieval', {})
            forced_strategy_from_config = current_retrieval_config.get('forced_strategy', None)
            
            self.logger.warning(f"🔍 Check forced_strategy configuration: {forced_strategy_from_config}")
            self.logger.warning(f"🔍 Does state have retrieval_strategy: {'retrieval_strategy' in state}")
            if 'retrieval_strategy' in state:
                self.logger.warning(f"🔍 retrieval_strategy value in state: {state.get('retrieval_strategy')}")
            
            # 🧪 Ablation study: If forced strategy is configured, use it directly
            if forced_strategy_from_config:
                forced_strategy_lower = forced_strategy_from_config.lower()
                if forced_strategy_lower not in ['simple', 'hybrid', 'complex']:
                    self.logger.error(f"Invalid forced strategy: {forced_strategy_from_config}, fallback to intelligent routing")
                else:
                    state["retrieval_strategy"] = forced_strategy_lower
                    state["forced_strategy_mode"] = True  # Mark as forced strategy mode
                    
                    # Set strategy description
                    strategy_descriptions = {
                        'simple': f"Force simple retrieval {'V2' if self.use_v2_retrievers else 'V1'} (ablation study)",
                        'hybrid': f"Force hybrid retrieval {'V2' if self.use_v2_retrievers else 'V1'} (ablation study)",
                        'complex': f"Force complex retrieval {'V2' if self.use_v2_retrievers else 'V1'} (ablation study)"
                    }
                    state["retrieval_description"] = strategy_descriptions[forced_strategy_lower]
                    
                    self.logger.warning(f"🧪 Ablation study: Force use {forced_strategy_lower.upper()} strategy (dynamically read from config)")
                    
                    return state
            
            # Normal process: Select retrieval strategy based on complexity
            complexity = state.get("query_complexity", 0)
            question = state.get("question", "")
            keywords = state.get("key_entities", [])
            category = state.get("query_category", "UNKNOWN")
            
            # ⚠️ Add detailed logging: Check received state
            self.logger.info(f"📍 Retrieval router received state:")
            self.logger.info(f"   query_complexity = {complexity}")
            self.logger.info(f"   query_category = {category}")
            self.logger.info(f"   question = {question[:80]}...")
            
            # Select retrieval strategy based on complexity (restored normal logic)
            if complexity == 0:
                # Simple retrieval: local retrieval, only needs L1 and L2
                state["retrieval_strategy"] = "simple"
                if self.use_v2_retrievers:
                    state["retrieval_description"] = "Simple retrieval V2: L1(top5) → session scoring → Best session's L2"
                    strategy_desc = "Simple retrieval (V2)"
                else:
                    state["retrieval_description"] = "Simple retrieval V1: L1(top5) + L2(top1)"
                    strategy_desc = "Simple retrieval (V1)"
                self.logger.info("Select simple retrieval strategy")
                
            elif complexity == 1:
                # Hybrid retrieval: associative retrieval, needs L1, L2, L3, L4
                state["retrieval_strategy"] = "hybrid"
                if self.use_v2_retrievers:
                    state["retrieval_description"] = "Hybrid retrieval V2: L1(top5) → session scoring → Best session's L3 daily report + L4 weekly report"
                    strategy_desc = "Hybrid retrieval (V2)"
                else:
                    state["retrieval_description"] = "Hybrid retrieval V1: L1(top5) + L2(top1) + L3(top1) + L4(top1)"
                    strategy_desc = "Hybrid retrieval (V1)"
                self.logger.info("Select hybrid retrieval strategy")
                
            else:  # complexity == 2
                # Complex retrieval: deep retrieval, needs L3, L4, L5
                state["retrieval_strategy"] = "complex"
                if self.use_v2_retrievers:
                    state["retrieval_description"] = "Complex retrieval V2: L1(top5) → session scoring → Best session's L5 monthly profile"
                    strategy_desc = "Complex retrieval (V2)"
                else:
                    state["retrieval_description"] = "Complex retrieval V1: L3(top2) + L4(top1) + L5(top1)"
                    strategy_desc = "Complex retrieval (V1)"
                self.logger.info("Select complex retrieval strategy")
            
            # 📤 Create merged query understanding thinking event (contains complexity, keywords, and strategy information)
            query_analysis = state.get("_query_analysis_temp", {})
            complexity_desc = query_analysis.get("complexity_desc", "Unknown")
            complexity_level = query_analysis.get("complexity", 0)
            
            keywords_display = ", ".join(keywords[:5]) if keywords else "None"
            if len(keywords) > 5:
                keywords_display += f" and {len(keywords)} more"
            
            # Merged description: query type + keywords + strategy
            description = f"Understood as {complexity_desc}, extracted {len(keywords)} keywords, using {strategy_desc} strategy"
            
            # Store thinking event information in state
            if "thinking_events" not in state:
                state["thinking_events"] = []
            
            state["thinking_events"].append({
                "step_type": "query_understanding",
                "step_name": "Query Intent Understanding",
                "description": description,
                "status": "completed",
                "progress": 1.0,
                "data": {
                    "complexity_level": complexity_level,
                    "complexity_desc": complexity_desc,
                    "keywords": keywords,
                    "keywords_count": len(keywords),
                    "strategy": state["retrieval_strategy"],
                    "strategy_description": state["retrieval_description"]
                }
            })
            
            # Clean up temporary data
            state.pop("_query_analysis_temp", None)
            
            # ⚠️ Add detailed logging: record the final set strategy
            self.logger.info(f"✅ Retrieval router set strategy:")
            self.logger.info(f"   retrieval_strategy = {state.get('retrieval_strategy')}")
            self.logger.info(f"   retrieval_description = {state.get('retrieval_description')}")
            
            return state
            
        except Exception as e:
            error_msg = f"Retrieval routing failed: {str(e)}"
            self.logger.error(error_msg)
            state["errors"] = state.get("errors", []) + [error_msg]
            return state
    
    def _route_retrieval_strategy(self, state: Dict[str, Any]) -> str:
        """
        Routing decision function - Select next node based on retrieval strategy
        
        🔧 Important: This method should be called after _retrieval_router,
        retrieval_strategy should already be set by _retrieval_router
        
        Args:
            state: Workflow state dictionary
            
        Returns:
            Name of the next node
        """
        try:
            # 🔧 Key fix: If retrieval_router hasn't set strategy, there's an execution order problem
            if "retrieval_strategy" not in state:
                self.logger.error("❌ retrieval_strategy not set! retrieval_router may not have executed")
                self.logger.error(f"   Current state keys: {list(state.keys())}")
                # Emergency fallback: Set based on complexity
                complexity = state.get("query_complexity", 0)
                if complexity == 0:
                    strategy = "simple"
                elif complexity == 1:
                    strategy = "hybrid"
                else:
                    strategy = "complex"
                self.logger.warning(f"   Emergency fallback: Set strategy={strategy} based on complexity={complexity}")
                state["retrieval_strategy"] = strategy
            else:
                strategy = state["retrieval_strategy"]
            
            self.logger.info(f"Routing decision: Select {strategy} retriever")
            return strategy
            
        except Exception as e:
            self.logger.error(f"Routing decision failed: {str(e)}")
            return "simple"  # Default to simple retrieval
    
    def _route_after_retrieval(self, state: Dict[str, Any]) -> str:
        """
        Post-retrieval routing decision function - Decide whether to perform memory refining or skip LLM generation
        
        Routing priority:
        1. If memory refiner is enabled → memory_refiner
        2. If memory-only return mode → direct_return
        3. Otherwise → answer_generation
        
        Args:
            state: Workflow state dictionary
            
        Returns:
            Name of next node ("memory_refiner", "answer_generation" or "direct_return")
        """
        try:
            # 🔧 Key fix: Dynamically read the latest configuration each time instead of using cached self.use_memory_refiner
            memory_refiner_config = self.retrieval_config_manager.get_config().get("memory_refiner", {})
            is_refiner_enabled = memory_refiner_config.get("enabled", False)
            
            # ✅ First check if memory refiner is enabled
            if is_refiner_enabled:
                self.logger.info("🔀 ============ Post-retrieval routing decision ============")
                self.logger.info("➡️ Routing decision: memory_refiner → MemoryRefiner (dynamically read from config)")
                self.logger.info(f"   - Number of retrieval results: {len(state.get('ranked_results', []))}")
                self.logger.info("🔀 ============ Routing decision completed ============")
                return "memory_refiner"
            else:
                self.logger.info("🔀 ============ Post-retrieval routing decision ============")
                self.logger.info("🚫 Memory refiner disabled, skip memory refining (dynamically read from config)")
                self.logger.info(f"   - Number of retrieval results: {len(state.get('ranked_results', []))}")
            
            # ✅ Use unified configuration judgment function
            from timem.workflows.retrieval_config import should_skip_llm_generation, get_retrieval_mode_description
            
            should_skip = should_skip_llm_generation(state)
            return_memories_only = state.get("return_memories_only", False)
            mode_desc = get_retrieval_mode_description(return_memories_only)
            
            # ✨ Enhanced logging: complete output of configuration status and debug information
            self.logger.info("🔀 ============ Post-retrieval routing decision ============")
            self.logger.info(f"🔀 Retrieval mode: {mode_desc}")
            self.logger.info(f"🔀 Configuration check:")
            self.logger.info(f"   - return_memories_only: {return_memories_only}")
            self.logger.info(f"   - Number of state keys: {len(state.keys())}")
            self.logger.info(f"   - Number of retrieval results: {len(state.get('ranked_results', []))}")
            
            if should_skip:
                self.logger.info("✅ Routing decision: direct_return → END (return memories only)")
                self.logger.info("🔀 ============ Routing decision completed ============")
                return "direct_return"
            else:
                self.logger.info("➡️ Routing decision: answer_generation → AnswerGenerator")
                self.logger.info("🔀 ============ Routing decision completed ============")
                return "answer_generation"
                
        except Exception as e:
            self.logger.error(f"❌ Post-retrieval routing decision failed: {e}", exc_info=True)
            # Default to answer generation (safe mode)
            return "answer_generation"
    
    def _route_after_memory_refiner(self, state: Dict[str, Any]) -> str:
        """
        Post-memory refiner routing decision function - Decide whether to continue LLM generation
        
        Args:
            state: Workflow state dictionary
            
        Returns:
            Name of next node ("answer_generation" or "direct_return")
        """
        try:
            from timem.workflows.retrieval_config import should_skip_llm_generation
            
            should_skip = should_skip_llm_generation(state)
            filtered_count = state.get("refined_memory_count", 0)
            original_count = state.get("original_memory_count", 0)
            retention_rate = state.get("refinement_retention_rate", 0.0)
            refiner_failed = state.get("memory_refiner_failed", False)
            
            self.logger.info("🔀 ============ Post-memory refiner routing decision ============")
            self.logger.info(f"   - Before filtering: {original_count} memories")
            self.logger.info(f"   - After filtering: {filtered_count} memories")
            self.logger.info(f"   - Retention rate: {retention_rate:.1%}")
            self.logger.info(f"   - Refiner failed: {refiner_failed}")
            
            if should_skip:
                self.logger.info("✅ Routing decision: direct_return → END (return filtered memories only)")
                self.logger.info("🔀 ============ Routing decision completed ============")
                return "direct_return"
            else:
                self.logger.info("➡️ Routing decision: answer_generation → AnswerGenerator")
                self.logger.info("🔀 ============ Routing decision completed ============")
                return "answer_generation"
                
        except Exception as e:
            self.logger.error(f"❌ Post-memory refiner routing decision failed: {e}", exc_info=True)
            # Default to answer generation (safe mode)
            return "answer_generation"
    
    def _route_reflection(self, state: Dict[str, Any]) -> str:
        """
        Reflection routing decision function - Check if reflection is needed
        
        Args:
            state: Workflow state dictionary
            
        Returns:
            Name of next node ("reflection" or "end")
        """
        try:
            needs_reflection = state.get("needs_reflection", False)
            reflection_count = state.get("reflection_count", 0)
            max_reflections = state.get("max_reflections", 3)
            
            if needs_reflection and reflection_count < max_reflections:
                self.logger.info(f"🤔 Trigger reflection mechanism (Round {reflection_count + 1})")
                return "reflection"
            else:
                if reflection_count >= max_reflections:
                    self.logger.info(f"Maximum reflection count ({max_reflections}) reached, end process")
                return "end"
                
        except Exception as e:
            self.logger.error(f"Reflection routing decision failed: {str(e)}")
            return "end"
    
    async def _reflection_handler(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Reflection handler - Prepare re-retrieval with optimized question
        
        Args:
            state: Workflow state dictionary
            
        Returns:
            Updated state dictionary
        """
        try:
            self.logger.info("🤔 Start reflection handling")
            
            # Update reflection count
            reflection_count = state.get("reflection_count", 0) + 1
            state["reflection_count"] = reflection_count
            state["in_reflection_mode"] = True
            
            # Get optimized question
            optimized_question = state.get("optimized_question", "")
            if not optimized_question:
                self.logger.warning("Optimized question not found, use original question")
                optimized_question = state.get("original_question", state.get("question", ""))
            
            # Save original question (if not already saved)
            if "original_question" not in state:
                state["original_question"] = state.get("question", "")
            
            # Update question to optimized question
            state["question"] = optimized_question
            
            # Reset retrieval-related state
            state["needs_reflection"] = False
            state["ranked_results"] = []
            state["total_memories_searched"] = 0
            
            # Expand L1 memory count (2x/3x/4x)
            l1_multiplier = min(reflection_count + 1, 4)  # Max 4x
            state["l1_expansion_multiplier"] = l1_multiplier
            
            self.logger.info(f"🔄 Reflection Round {reflection_count}:")
            self.logger.info(f"   Original question: {state.get('original_question', '')}")
            self.logger.info(f"   Optimized question: {optimized_question}")
            self.logger.info(f"   L1 expansion multiplier: {l1_multiplier}x")
            self.logger.info(f"   Reflection reason: {state.get('reflection_reason', '')}")
            
            # Record reflection history
            if "reflection_history" not in state:
                state["reflection_history"] = []
            
            state["reflection_history"].append({
                "round": reflection_count,
                "original_question": state.get("original_question", ""),
                "optimized_question": optimized_question,
                "reason": state.get("reflection_reason", ""),
                "l1_multiplier": l1_multiplier
            })
            
            return state
            
        except Exception as e:
            error_msg = f"Reflection handling failed: {str(e)}"
            self.logger.error(error_msg)
            state["errors"] = state.get("errors", []) + [error_msg]
            state["needs_reflection"] = False  # Stop reflection
            return state
    
    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run memory retrieval workflow
        
        Args:
            input_data: Input data, must contain question field
            
        Returns:
            Final workflow state containing retrieval results, answer and possible error information
        """
        start_time = time.time()
        checkpoint = None
        current_step = "init"
        
        try:
            if self.debug_mode:
                print(f"\n🚀 Start executing memory retrieval workflow...")
                
            logger.info(f"Start executing workflow, input question: {input_data.get('question', '')}")
            
            # 1. Validate input data
            current_step = "validate_input"
            errors = self.state_validator.validate_input(input_data)
            if errors:
                error_msg = f"Input validation failed: {', '.join(errors)}"
                logger.error(error_msg)
                return self._create_error_response(error_msg)
            
            # 2. Create initial state
            current_step = "create_initial_state"
            try:
                # ✅ Normalize configuration (handle backward compatibility and deprecated fields)
                from timem.workflows.retrieval_config import normalize_retrieval_config, get_retrieval_mode_description
                
                normalized_config = normalize_retrieval_config(input_data)
                return_memories_only = normalized_config.get("return_memories_only", False)
                mode_desc = get_retrieval_mode_description(return_memories_only)
                
                # Check if multi-stage COT is enabled
                answer_gen_config = self.retrieval_config_manager.get_config().get("answer_generation", {})
                answer_gen_mode = answer_gen_config.get("mode", "single")
                use_multi_stage_cot = (answer_gen_mode == "multi_stage_cot" and 
                                      answer_gen_config.get("multi_stage_cot", {}).get("enabled", False))
                
                # Debug logging: record COT configuration status
                logger.info(f"🔍 Answer generation configuration check:")
                logger.info(f"  - Generation mode: {answer_gen_mode}")
                logger.info(f"  - Multi-stage COT enabled: {answer_gen_config.get('multi_stage_cot', {}).get('enabled', False)}")
                logger.info(f"  - Final use_multi_stage_cot: {use_multi_stage_cot}")
                
                # Create initial state dictionary
                initial_state = {
                    "question": normalized_config.get("question", ""),
                    "user_id": normalized_config.get("user_id", ""),
                    "expert_id": normalized_config.get("expert_id", ""),
                    "user_name": normalized_config.get("user_name", ""),
                    "expert_name": normalized_config.get("expert_name", ""),
                    "character_ids": normalized_config.get("character_ids", []),
                    "user_group_ids": normalized_config.get("user_group_ids", []),
                    "user_group_filter": normalized_config.get("user_group_filter", {}),
                    "context": normalized_config.get("context", {}),
                    "retrieval_config": normalized_config.get("retrieval_config", {}),
                    # ✅ Only use standard configuration items
                    "return_memories_only": return_memories_only,
                    # Multi-stage COT configuration
                    "use_multi_stage_cot": use_multi_stage_cot,
                    "errors": [],
                    "warnings": []
                }
                
                # ✅ New: Validate user group configuration
                if initial_state["user_group_ids"]:
                    if len(initial_state["user_group_ids"]) < 2:
                        logger.warning(f"⚠️ Insufficient user_group_ids ({len(initial_state['user_group_ids'])}), need at least 2 IDs")
                        # Clear invalid user_group_ids
                        initial_state["user_group_ids"] = []
                    else:
                        logger.info(f"✅ User group isolation enabled: {initial_state['user_group_ids']}")
                
                logger.info(f"Create initial state: question={initial_state['question'][:50]}..., retrieval mode={mode_desc}")
            except Exception as e:
                error_msg = f"Create initial state failed: {str(e)}"
                logger.error(error_msg)
                return self._create_error_response(error_msg, traceback.format_exc())
            
            # 3. Create state checkpoint
            checkpoint = initial_state.copy()
            logger.info(f"Create state checkpoint")
            
            # 3.5. Check if using Naive RAG workflow (for ablation studies only)
            retrieval_config = initial_state.get("retrieval_config", {})
            use_naive_rag = retrieval_config.get("use_naive_rag", False)
            
            if use_naive_rag:
                logger.info("🔀 Detected use_naive_rag=True, switch to Naive RAG workflow")
                current_step = "naive_rag_workflow"
                
                # Import Naive RAG workflow
                from timem.workflows.naive_rag_workflow import NaiveRAGWorkflow
                
                # Get Naive RAG configuration
                naive_rag_layers = retrieval_config.get("naive_rag_layers", ['L1', 'L2', 'L3', 'L4', 'L5'])
                naive_rag_top_k = retrieval_config.get("naive_rag_top_k", 20)
                
                logger.info(f"Naive RAG configuration: layers={naive_rag_layers}, top_k={naive_rag_top_k}")
                
                # Create Naive RAG workflow instance
                naive_workflow = NaiveRAGWorkflow(
                    config=self.config,
                    debug_mode=self.debug_mode,
                    enabled_layers=naive_rag_layers,
                    top_k=naive_rag_top_k
                )
                
                # Execute Naive RAG workflow
                naive_result = await naive_workflow.run(initial_state)
                
                # Clean up resources
                await naive_workflow.cleanup()
                
                # Return result
                end_time = time.time()
                naive_result["execution_time"] = end_time - start_time
                logger.info(f"Naive RAG workflow execution completed, elapsed time: {end_time - start_time:.2f}s")
                
                return naive_result
            
            # 4. Execute workflow graph (normal process)
            current_step = "execute_workflow"
            try:
                if self.debug_mode:
                    print(f"🔄 Execute workflow nodes...")
                    
                logger.info("Start executing LangGraph workflow")
                
                # Check if hybrid retrieval is enabled
                logger.info("Using simplified hybrid retrieval strategy: LLM keyword SQL + Qdrant semantic retrieval")
                if self.debug_mode:
                    print(f"🔍 Hybrid retrieval configuration: LLM keyword generation + PostgreSQL BM25 + Qdrant semantic retrieval")
                
                # Set maximum execution time to prevent long blocking
                max_execution_time = self.retrieval_config_manager.get_max_execution_time()
                
                # Retry logic
                max_retries = 20  # Set retry limit to 20
                retry_count = 0
                
                while retry_count <= max_retries:
                    try:
                        # Update state when retrying
                        if retry_count > 0:
                            initial_state["retry_count"] = retry_count
                            initial_state["is_retry"] = True
                            logger.info(f"Start retry {retry_count}")
                        
                        final_state = await asyncio.wait_for(
                            self.app.ainvoke(initial_state),
                            timeout=max_execution_time
                        )
                        
                        # Check if retry is needed
                        if final_state.get("needs_retry") and retry_count < max_retries:
                            retry_reason = final_state.get("retry_reason", "Unknown error")
                            logger.warning(f"Retrieval failed, need retry: {retry_reason}")
                            retry_count += 1
                            
                            # Reset state for retry
                            initial_state = self._prepare_retry_state(initial_state, retry_reason, retry_count)
                            continue
                        else:
                            # Success or maximum retry count reached
                            break
                            
                    except asyncio.TimeoutError:
                        if retry_count < max_retries:
                            logger.warning(f"Workflow execution timeout, prepare retry (Round {retry_count + 1})")
                            retry_count += 1
                            continue
                        else:
                            error_msg = f"Workflow execution timeout, exceeded {max_execution_time}s, retried {max_retries} times"
                            logger.error(error_msg)
                            return self._create_error_response(error_msg, None, checkpoint)
                
                # Check if there are errors
                if final_state.get("errors"):
                    logger.error(f"Errors occurred during workflow execution: {final_state['errors']}")
                    if self.debug_mode:
                        print(f"⚠️ Errors occurred during workflow execution: {final_state['errors']}")
                    final_state["success"] = False
                else:
                    final_state["success"] = True
                    logger.info("Workflow execution successful")
                
                # 5. Add execution statistics
                current_step = "finalize"
                end_time = time.time()
                execution_time = end_time - start_time
                
                final_state["execution_stats"] = {
                    "start_time": start_time,
                    "end_time": end_time,
                    "execution_time": execution_time,
                    "timestamp": datetime.now().isoformat()
                }
                
                # 6. Build standardized response
                response = self._build_response(final_state, execution_time)
                
                # 7. Output execution summary
                if self.debug_mode:
                    print(f"\n✅ Workflow execution completed")
                    print(f"⏱️ Execution time: {execution_time:.2f} seconds")
                    print(f"🎯 Confidence: {response.get('confidence', 0.0):.3f}")
                    print(f"📚 Retrieved memories: {len(response.get('retrieved_memories', []))} items")
                
                logger.info(f"Workflow execution completed, elapsed time: {execution_time:.2f}s")
                return response
                
            except ValueError as ve:
                error_msg = f"Workflow interrupted due to validation failure: {ve} (current step: {current_step})"
                logger.error(error_msg)
                if self.debug_mode:
                    print(f"❌ {error_msg}")
                return self._create_error_response(str(ve), traceback.format_exc(), checkpoint)
                
            except Exception as e:
                error_msg = f"Unhandled exception during workflow execution: {e} (current step: {current_step})"
                logger.error(error_msg)
                logger.error(traceback.format_exc())
                if self.debug_mode:
                    print(f"❌ {error_msg}")
                return self._create_error_response(str(e), traceback.format_exc(), checkpoint)
                
        except Exception as e:
            error_msg = f"Unhandled exception during workflow execution: {e} (current step: {current_step})"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            if self.debug_mode:
                print(f"❌ {error_msg}")
            return self._create_error_response(str(e), traceback.format_exc(), checkpoint)
    
    def _build_response(self, final_state: Dict[str, Any], execution_time: float) -> Dict[str, Any]:
        """Build standardized response"""
        try:
            # Build strategy list based on actual strategies used
            retrieval_strategy = final_state.get("retrieval_strategy", "simple")
            strategies_used = ["llm_query_analysis"]
            
            if retrieval_strategy == "simple":
                strategies_used.append("simple_retrieval")
            elif retrieval_strategy == "hybrid":
                strategies_used.append("hybrid_retrieval")
            elif retrieval_strategy == "complex":
                strategies_used.append("complex_retrieval")
            
            # Get query category and complexity
            query_category = final_state.get("query_category", "UNKNOWN")
            query_complexity = final_state.get("query_complexity", 0)
            
            # ⚠️ Add detailed logging: check consistency of final state
            self.logger.info(f"📍 State when building response:")
            self.logger.info(f"   query_complexity = {query_complexity}")
            self.logger.info(f"   query_category = {query_category}")
            self.logger.info(f"   retrieval_strategy = {retrieval_strategy}")
            
            # Consistency check and auto-fix
            category_map = {0: "FACTUAL", 1: "MIXED", 2: "INFERENTIAL"}
            strategy_map = {0: "simple", 1: "hybrid", 2: "complex"}
            reverse_category_map = {"FACTUAL": 0, "MIXED": 1, "INFERENTIAL": 2}
            
            expected_category = category_map.get(query_complexity, "UNKNOWN")
            expected_strategy = strategy_map.get(query_complexity, "unknown")
            
            # 🔧 Auto-fix logic: prioritize trusting query_category (set directly by LLM)
            if query_category != expected_category and query_category in reverse_category_map:
                corrected_complexity = reverse_category_map[query_category]
                self.logger.warning(f"🔧 Auto-fix: complexity {query_complexity} → {corrected_complexity} (based on category={query_category})")
                query_complexity = corrected_complexity
                
                # Also fix strategy
                corrected_strategy = strategy_map.get(query_complexity, "simple")
                if corrected_strategy != retrieval_strategy:
                    self.logger.warning(f"🔧 Auto-fix: strategy {retrieval_strategy} → {corrected_strategy} (based on corrected complexity)")
                    retrieval_strategy = corrected_strategy
            
            # Verify consistency after fix (skip when ablation study forces strategy)
            retrieval_config = self.retrieval_config_manager.get_config().get('retrieval', {})
            forced_strategy = retrieval_config.get('forced_strategy')
            
            # 🔧 Only verify consistency in non-forced strategy mode
            if not forced_strategy:
                final_expected_category = category_map.get(query_complexity, "UNKNOWN")
                final_expected_strategy = strategy_map.get(query_complexity, "unknown")
                
                if query_category != final_expected_category:
                    self.logger.error(f"❌ Fix failed! query_category={query_category} still inconsistent with complexity={query_complexity}")
                
                if retrieval_strategy != final_expected_strategy:
                    self.logger.error(f"❌ Fix failed! retrieval_strategy={retrieval_strategy} still inconsistent with complexity={query_complexity}")
            else:
                self.logger.debug(f"✅ Forced strategy mode ({forced_strategy}), skip consistency verification")
            
            # Build reflection information
            reflection_info = {
                "reflection_count": final_state.get("reflection_count", 0),
                "reflection_history": final_state.get("reflection_history", []),
                "original_question": final_state.get("original_question", final_state.get("question", "")),
                "l1_expansion_multiplier": final_state.get("l1_expansion_multiplier", 1)
            }
            
            response = {
                "question": final_state.get("question", ""),
                "answer": final_state.get("answer", ""),
                "confidence": final_state.get("confidence", 0.0),
                "evidence": final_state.get("evidence", []),
                "formatted_context_memories": final_state.get("formatted_context_memories", []),  # Add formatted memory content
                "retrieval_metadata": {
                    "retrieval_time": execution_time,
                    "total_memories_searched": final_state.get("total_memories_searched", 0),
                    "strategies_used": strategies_used,
                    "strategy_performance": final_state.get("strategy_performance", {}),
                    "query_category": query_category,
                    "query_complexity": query_complexity,
                    "retrieval_strategy": retrieval_strategy,
                    "retrieval_description": final_state.get("retrieval_description", ""),
                    "llm_keywords": final_state.get("key_entities", [])
                },
                "reflection_info": reflection_info,  # Add reflection information
                "retrieved_memories": final_state.get("ranked_results", []),
                "thinking_events": final_state.get("thinking_events", []),  # 📤 Add thinking events list
                "errors": final_state.get("errors", []),
                "warnings": final_state.get("warnings", []),
                # Multi-stage COT related fields
                "use_multi_stage_cot": final_state.get("use_multi_stage_cot", False),
                "cot_evidence": final_state.get("cot_evidence"),
                "cot_reasoning": final_state.get("cot_reasoning"),
                "cot_full_reasoning": final_state.get("cot_full_reasoning"),
                "cot_stage_times": final_state.get("cot_stage_times", {}),
                "cot_stage_tokens": final_state.get("cot_stage_tokens", {}),
                # Single-step COT related fields
                "use_single_cot": final_state.get("use_single_cot", False),
                "cot_full_response": final_state.get("cot_full_response"),
                "cot_format_valid": final_state.get("cot_format_valid"),
                "cot_retry_count": final_state.get("cot_retry_count"),
                # 🔧 Ablation study: memory refiner status (ensure passed to final result)
                "memory_refiner_enabled": final_state.get("memory_refiner_enabled", False),
                "memories_before_memory_refiner": final_state.get("memories_before_memory_refiner", []),
                "memories_after_memory_refiner": final_state.get("memories_after_memory_refiner", [])
            }
            
            # ✨ Pass thinking event to response
            if "thinking_event" in final_state:
                response["thinking_event"] = final_state["thinking_event"]
                logger.info(f"📤 Pass thinking event to response: {final_state['thinking_event'].step.step_name}")
            
            return response
        except Exception as e:
            logger.error(f"Build response failed: {str(e)}")
            return self._create_error_response(f"Build response failed: {str(e)}")
    
    def _create_error_response(self, error_msg: str, traceback_info: str = None, checkpoint: Dict = None) -> Dict[str, Any]:
        """Create standardized error response - trigger retry instead of hardcoded error"""
        # Check if should retry
        should_retry = self._should_retry_workflow(error_msg, checkpoint)
        
        if should_retry:
            # Set retry flag to restart workflow
            response = {
                "question": checkpoint.get("question", "") if checkpoint else "",
                "needs_retry": True,
                "retry_reason": error_msg,
                "success": False,
                "errors": [error_msg],
                "timestamp": datetime.now().isoformat()
            }
        else:
            # True final error response (no hardcoded messages)
            response = {
                "question": checkpoint.get("question", "") if checkpoint else "",
                "answer": "",  # Remove hardcoded error message
                "confidence": 0.0,
                "evidence": [],
                "retrieval_metadata": {
                    "retrieval_time": 0.0,
                    "total_memories_searched": 0,
                    "strategies_used": [],
                    "strategy_performance": {},
                    "query_category": None
                },
                "retrieved_memories": [],
                "errors": [error_msg],
                "warnings": [],
                "success": False,
                "timestamp": datetime.now().isoformat()
            }
        
        if traceback_info:
            response["traceback"] = traceback_info
            
        if checkpoint:
            response["checkpoint"] = checkpoint
            
        return response
    
    def _should_retry_workflow(self, error_msg: str, checkpoint: Dict = None) -> bool:
        """Determine whether to retry the workflow"""
        # Check retry count
        retry_count = checkpoint.get("retry_count", 0) if checkpoint else 0
        max_retries = 20  # Maximum retry count
        
        if retry_count >= max_retries:
            logger.warning(f"Maximum retry count {max_retries} reached, stop retrying")
            return False
        
        # Check if it's a retryable error type
        retryable_errors = [
            "Intent understanding failed",
            "L1 retrieval returned no results", 
            "Retrieved empty memory",
            "Session scoring failed",
            "No valid session found",
            "Keyword extraction failed"
        ]
        
        for retryable_error in retryable_errors:
            if retryable_error in error_msg:
                logger.info(f"Detected retryable error: {error_msg}, prepare retry (Round {retry_count + 1})")
                return True
        
        logger.info(f"Error not retryable: {error_msg}")
        return False
    
    def _prepare_retry_state(self, original_state: Dict[str, Any], retry_reason: str, retry_count: int) -> Dict[str, Any]:
        """Prepare state for retry"""
        # Create new state copy
        retry_state = {
            "question": original_state.get("question", ""),
            "user_id": original_state.get("user_id", ""),
            "expert_id": original_state.get("expert_id", ""),
            "user_name": original_state.get("user_name", ""),
            "expert_name": original_state.get("expert_name", ""),
            "character_ids": original_state.get("character_ids", []),
            "user_group_ids": original_state.get("user_group_ids", []),
            "user_group_filter": original_state.get("user_group_filter", {}),
            "context": original_state.get("context", {}),
            "retrieval_config": original_state.get("retrieval_config", {}),
            "retry_count": retry_count,
            "is_retry": True,
            "retry_reason": retry_reason,
            "errors": [],
            "warnings": []
        }
        
        # Remove state that might cause problems
        retry_state.pop("needs_retry", None)
        retry_state.pop("ranked_results", None)
        retry_state.pop("total_memories_searched", None)
        retry_state.pop("retrieval_success", None)
        
        logger.info(f"Prepare retry state (Round {retry_count}), reason: {retry_reason}")
        return retry_state
    
    async def cleanup(self):
        """Clean up workflow resources"""
        logger.info("Start cleaning up workflow resources...")
        
        # Clean up node resources
        for node_name, node in self.nodes.items():
            if hasattr(node, 'cleanup') and callable(getattr(node, 'cleanup')):
                try:
                    if asyncio.iscoroutinefunction(node.cleanup):
                        await node.cleanup()
                    else:
                        node.cleanup()
                    logger.info(f"Node {node_name} resources cleaned up")
                except Exception as e:
                    logger.error(f"Error cleaning up node {node_name} resources: {e}")
        
        # Clean up other resources
        self.app = None
        self.graph = None
        
        logger.info("Workflow resource cleanup completed")


# Global workflow instance and lock
_workflow_instance = None
_workflow_lock = asyncio.Lock()
_cleanup_registered = False
_cleanup_done = False


def _cleanup_workflow_sync():
    """Synchronously clean up workflow resources"""
    global _workflow_instance
    global _cleanup_done
    if _workflow_instance is None:
        return
    # If cleanup is already done, don't repeat
    if _cleanup_done or getattr(_workflow_instance, "_is_cleaned", False):
        return
    try:
        # Ensure resources are released when process exits (create new event loop for async cleanup)
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_workflow_instance.cleanup())
        finally:
            loop.close()
        _cleanup_done = True
    except Exception as e:
        # Exit phase, avoid writing complex logs
        try:
            import sys
            sys.stderr.write(f"[TiMem] Failed to clean up workflow resources on exit: {e}\n")
        except Exception:
            pass


async def get_retrieval_workflow(debug_mode: bool = False, 
                                use_v2_retrievers: bool = True) -> MemoryRetrievalWorkflow:
    """
    Get memory retrieval workflow singleton instance
    
    Args:
        debug_mode: Whether to enable debug mode
        use_v2_retrievers: Whether to use V2 Bottom-Up retrievers, default True
        
    Returns:
        Workflow instance
        
    Note:
        Should call cleanup() method on workflow instance to release resources after use
    """
    global _workflow_instance
    if _workflow_instance is None:
        async with _workflow_lock:
            if _workflow_instance is None:
                retriever_version = "V2 Bottom-Up" if use_v2_retrievers else "V1 Original"
                logger.info(f"Create global workflow instance, debug mode: {debug_mode}, retriever version: {retriever_version}")
        _workflow_instance = await MemoryRetrievalWorkflow.create(
            debug_mode=debug_mode, 
            use_v2_retrievers=use_v2_retrievers
        )
        # Register process exit cleanup hook (only register once)
        global _cleanup_registered
        if not _cleanup_registered:
            try:
                atexit.register(_cleanup_workflow_sync)
                _cleanup_registered = True
            except Exception as e:
                logger.warning(f"Failed to register exit cleanup hook: {e}")
    
    # If instance exists but has been cleaned up, reinitialize
    if getattr(_workflow_instance, "app", None) is None or getattr(_workflow_instance, "graph", None) is None:
        async with _workflow_lock:
            if getattr(_workflow_instance, "app", None) is None or getattr(_workflow_instance, "graph", None) is None:
                logger.info("Detected global workflow has been cleaned up or not initialized, reinitializing...")
                await _workflow_instance._async_init()
    
    return _workflow_instance


async def run_memory_retrieval(input_data: Dict[str, Any], 
                               debug_mode: bool = False,
                               use_v2_retrievers: bool = True,
                               config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Main function to run memory retrieval workflow
    
    Args:
        input_data: Input data, must contain question field, optionally contains retrieval_config field
        debug_mode: Whether to enable debug mode
        use_v2_retrievers: Whether to use V2 Bottom-Up retrievers, default True
        config_path: Configuration file path (for ablation studies, use independent config context if provided)
        
    Returns:
        Workflow execution result
    """
    # 🔧 Engineering-level config isolation: If config path is provided, **force disable all caching, create brand new workflow instance**
    if config_path:
        logger.info(f"✅ Ablation study mode: Use independent config context - {config_path}")
        from timem.utils.config_context import RetrievalConfigContext
        
        # Create independent config context
        with RetrievalConfigContext(config_path) as config_ctx:
            # 🔑 Key: Directly create brand new config manager instance, don't use global singleton
            from timem.utils.retrieval_config_manager import RetrievalConfigManager
            isolated_config_manager = RetrievalConfigManager.__new__(RetrievalConfigManager)
            isolated_config_manager.config_path = config_path
            isolated_config_manager._config = config_ctx.get_config()
            
            # 🔑 Key: Directly create brand new workflow instance, bypass singleton mechanism
            isolated_workflow = MemoryRetrievalWorkflow(
                retrieval_config_manager=isolated_config_manager,
                debug_mode=debug_mode,
                use_v2_retrievers=use_v2_retrievers
            )
            
            # Initialize workflow
            await isolated_workflow._async_init()
            
            # Execute workflow
            result = await isolated_workflow.run(input_data)
            logger.info("✅ Ablation study workflow execution completed")
            return result
    else:
        # Normal mode: Use global config and singleton workflow
        workflow = await get_retrieval_workflow(debug_mode, use_v2_retrievers)
        return await workflow.run(input_data)
