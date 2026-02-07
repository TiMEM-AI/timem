"""
Strategy Selection Node

Intelligently selects appropriate retrieval strategy combinations based on retrieval-planning results.
Supports multiple strategy configurations and parameter adjustments.
"""

from typing import Dict, List, Any, Optional

from timem.workflows.retrieval_state import RetrievalState, RetrievalStateValidator, QueryCategory, RetrievalStrategy
from timem.utils.config_manager import get_app_config
from timem.utils.retrieval_config_manager import get_retrieval_config_manager
from timem.utils.logging import get_logger

logger = get_logger(__name__)

class StrategySelector:
    """Strategy Selection Node"""
    
    def __init__(self, 
                 config: Optional[Dict[str, Any]] = None,
                 state_validator: Optional[RetrievalStateValidator] = None):
        """
        Initialize the strategy selector
        
        Args:
            config: Configuration information, auto-fetched if None
            state_validator: State validator, creates new instance if None
        """
        self.config = config or get_app_config()
        self.state_validator = state_validator or RetrievalStateValidator()
        self.logger = get_logger(__name__)
        
        # Get retrieval configuration manager
        self.retrieval_config_manager = get_retrieval_config_manager()
        
        # Load strategy configuration from config file
        self._load_strategy_config()
    
    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run strategy selection
        
        Args:
            state: Workflow state dictionary
            
        Returns:
            Updated state dictionary
        """
        try:
            # Convert to RetrievalState object
            retrieval_state = self._dict_to_state(state)
            
            self.logger.info("Start strategy selection")
            
            # Step 1: Select base strategies based on query category
            base_strategies = self._select_base_strategies(retrieval_state)
            
            # Step 2: Adjust strategies based on context information
            adjusted_strategies = self._adjust_strategies_by_context(base_strategies, retrieval_state)
            
            # Step 3: Apply user preferences and configuration
            final_strategies = self._apply_user_preferences(adjusted_strategies, retrieval_state)
            
            # Step 4: Configure strategy parameters
            strategy_params = self._configure_strategy_parameters(final_strategies, retrieval_state)
            
            # Step 5: Set results
            retrieval_state.selected_strategies = final_strategies
            retrieval_state.retrieval_params = strategy_params
            
            self.logger.info(f"Strategy selection completed: {[s.value for s in final_strategies]}")
            
            return self._state_to_dict(retrieval_state)
            
        except Exception as e:
            error_msg = f"Strategy selection failed: {str(e)}"
            self.logger.error(error_msg)
            state["errors"] = state.get("errors", []) + [error_msg]
            return state
    
    def _select_base_strategies(self, state: RetrievalState) -> List[RetrievalStrategy]:
        """Select base strategies based on query category"""
        if state.query_category in self.default_strategies:
            strategies = self.default_strategies[state.query_category].copy()
        else:
            # Default to semantic retrieval
            strategies = [RetrievalStrategy.SEMANTIC]
        
        self.logger.info(f"Select strategies based on query category {state.query_category.name if state.query_category else 'Unknown'}: {[s.value for s in strategies]}")
        return strategies
    
    def _adjust_strategies_by_context(self, strategies: List[RetrievalStrategy], state: RetrievalState) -> List[RetrievalStrategy]:
        """Adjust strategies based on context information"""
        adjusted = strategies.copy()
        
        # If time entities exist, ensure temporal retrieval is included
        if state.time_entities and RetrievalStrategy.TEMPORAL not in adjusted:
            adjusted.append(RetrievalStrategy.TEMPORAL)
            self.logger.info("Detected time entities, adding temporal retrieval strategy")
        
        # If query is complex (multiple key entities), add keyword retrieval
        if len(state.key_entities) > 5 and RetrievalStrategy.KEYWORD not in adjusted:
            adjusted.append(RetrievalStrategy.KEYWORD)
            self.logger.info("Detected complex query, adding keyword retrieval strategy")
        
        # If multiple characters, may need contextual retrieval
        if len(state.character_ids) > 2 and RetrievalStrategy.CONTEXTUAL not in adjusted:
            adjusted.append(RetrievalStrategy.CONTEXTUAL)
            self.logger.info("Detected multi-character query, adding contextual retrieval strategy")
        
        # Read force-enabled strategies from config file
        for strategy_name in self.force_enable_strategies:
            try:
                strategy = RetrievalStrategy(strategy_name)
                if strategy not in adjusted:
                    adjusted.append(strategy)
                    self.logger.info(f"Force-enable strategy: {strategy_name}")
            except ValueError:
                self.logger.warning(f"Unknown force-enable strategy: {strategy_name}")
        
        return adjusted
    
    def _apply_user_preferences(self, strategies: List[RetrievalStrategy], state: RetrievalState) -> List[RetrievalStrategy]:
        """Apply user preferences and configuration"""
        # Check if there are strategy preference settings in config
        user_prefs = state.context.get("strategy_preferences", {})
        
        # If user explicitly specifies semantic-only retrieval
        if user_prefs.get("semantic_only", False):
            return [RetrievalStrategy.SEMANTIC]
        
        # If user disables certain strategies
        disabled_strategies = user_prefs.get("disabled_strategies", [])
        filtered_strategies = [s for s in strategies if s.value not in disabled_strategies]
        
        # If user requires adding specific strategies
        required_strategies = user_prefs.get("required_strategies", [])
        for strategy_name in required_strategies:
            try:
                strategy = RetrievalStrategy(strategy_name)
                if strategy not in filtered_strategies:
                    filtered_strategies.append(strategy)
            except ValueError:
                self.logger.warning(f"Unknown strategy: {strategy_name}")
        
        # Ensure at least one strategy
        if not filtered_strategies:
            filtered_strategies = [RetrievalStrategy.SEMANTIC]
            self.logger.warning("All strategies filtered, fallback to semantic retrieval")
        
        return filtered_strategies
    
    def _configure_strategy_parameters(self, strategies: List[RetrievalStrategy], state: RetrievalState) -> Dict[str, Any]:
        """Configure strategy parameters"""
        params = {}
        
        # Merge parameters from all strategies
        for strategy in strategies:
            if strategy in self.strategy_params:
                strategy_params = self.strategy_params[strategy].copy()
                
                # Add prefix for each strategy
                for key, value in strategy_params.items():
                    param_key = f"{strategy.value}_{key}"
                    params[param_key] = value
        
        # Add global parameters
        params.update({
            "max_total_results": self.config.get("max_total_results", 20),
            "final_result_limit": self.config.get("final_result_limit", 10),
            "score_threshold_global": self.config.get("score_threshold_global", 0.0)  # Adjust to lowest threshold
        })
        
        # Adjust parameters based on query complexity
        if len(state.key_entities) > 8:
            # Complex query, increase result count
            params["max_total_results"] = params.get("max_total_results", 20) + 10
            params["final_result_limit"] = params.get("final_result_limit", 10) + 5
        
        # If time limit exists, adjust time window
        if state.time_entities:
            params["temporal_time_window_days"] = min(
                params.get("temporal_time_window_days", 30),
                365  # Maximum one year
            )
        
        # Apply user-defined parameters
        user_params = state.context.get("retrieval_params", {})
        # Also get parameters from retrieval_config
        retrieval_config = getattr(state, 'retrieval_config', {})
        if retrieval_config:
            # Convert retrieval_config parameters to retrieval_params format
            if 'hierarchical' in retrieval_config:
                hierarchical_config = retrieval_config['hierarchical']
                if 'layer_limits' in hierarchical_config:
                    layer_limits = hierarchical_config['layer_limits']
                    user_params.update({
                        'hierarchical_L1_limit': layer_limits.get('L1', 10),
                        'hierarchical_L2_limit': layer_limits.get('L2', 3),
                    })
                if 'final_limits' in hierarchical_config:
                    final_limits = hierarchical_config['final_limits']
                    user_params.update({
                        'hierarchical_L1_final_limit': final_limits.get('L1', 5),
                        'hierarchical_L2_final_limit': final_limits.get('L2', 1)
                    })
        params.update(user_params)
        
        self.logger.info(f"Configure strategy parameters: {len(params)} parameters")
        return params
    
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
            if key == 'selected_strategies':
                # Strategy list needs special handling
                state_dict[key] = value
            else:
                state_dict[key] = value
                
        return state_dict
    
    def _load_strategy_config(self):
        """Load strategy configuration from config file"""
        try:
            # Get strategy selection configuration
            strategy_config = self.retrieval_config_manager.get_config().get("strategy_selection", {})
            
            # Load default strategy configuration
            self.default_strategies = {}
            default_strategies_config = strategy_config.get("default_strategies", {})
            
            for category_name, strategy_names in default_strategies_config.items():
                try:
                    category = QueryCategory[category_name]
                    strategies = []
                    for strategy_name in strategy_names:
                        try:
                            strategy = RetrievalStrategy(strategy_name)
                            strategies.append(strategy)
                        except ValueError:
                            self.logger.warning(f"Unknown strategy: {strategy_name}")
                    self.default_strategies[category] = strategies
                except KeyError:
                    self.logger.warning(f"Unknown query category: {category_name}")
            
            # Load force-enable strategies
            self.force_enable_strategies = strategy_config.get("force_enable_strategies", [])
            
            # Load strategy weights
            self.strategy_weights = strategy_config.get("strategy_weights", {})
            
            # Load strategy parameter configuration
            self.strategy_params = self._build_strategy_params()
            
            self.logger.info("Strategy configuration loaded")
            
        except Exception as e:
            self.logger.error(f"Failed to load strategy configuration: {str(e)}")
            self._load_fallback_config()
    
    def _build_strategy_params(self) -> Dict[RetrievalStrategy, Dict[str, Any]]:
        """Build strategy parameter configuration"""
        params = {}
        
        # Get configuration for each strategy
        retrieval_config = self.retrieval_config_manager.get_config()
        
        # Semantic retrieval parameters
        semantic_config = retrieval_config.get("semantic", {})
        params[RetrievalStrategy.SEMANTIC] = {
            "top_k": semantic_config.get("top_k", 10),
            "score_threshold": semantic_config.get("score_threshold", 0.0),  # Adjust to lowest threshold
            "weight": semantic_config.get("weight", 1.0)
        }
        
        # Temporal retrieval parameters
        temporal_config = retrieval_config.get("temporal", {})
        params[RetrievalStrategy.TEMPORAL] = {
            "top_k": temporal_config.get("top_k", 8),
            "time_window_days": temporal_config.get("time_window_days", 30),
            "weight": temporal_config.get("weight", 0.8)
        }
        
        # Keyword retrieval parameters
        keyword_config = retrieval_config.get("keyword", {})
        params[RetrievalStrategy.KEYWORD] = {
            "top_k": keyword_config.get("top_k", 5),
            "min_match_score": keyword_config.get("min_match_score", 0.2),
            "weight": keyword_config.get("weight", 0.6)
        }
        
        # Hierarchical retrieval parameters
        hierarchical_config = retrieval_config.get("hierarchical", {})
        params[RetrievalStrategy.HIERARCHICAL] = {
            "L1_limit": hierarchical_config.get("layer_limits", {}).get("L1", 10),
            "L2_limit": hierarchical_config.get("layer_limits", {}).get("L2", 3),
            "L3_limit": hierarchical_config.get("layer_limits", {}).get("L3", 0),
            "L4_limit": hierarchical_config.get("layer_limits", {}).get("L4", 0),
            "L5_limit": hierarchical_config.get("layer_limits", {}).get("L5", 0),
            "weight": hierarchical_config.get("layer_weights", {}).get("L2", 0.9),
            "hierarchical_sorting": hierarchical_config.get("hierarchical_sorting", True),
            "L1_sort_method": hierarchical_config.get("sorting_methods", {}).get("L1", "relevance"),
            "L2_sort_method": hierarchical_config.get("sorting_methods", {}).get("L2", "temporal")
        }
        
        # Contextual retrieval parameters
        contextual_config = retrieval_config.get("contextual", {})
        params[RetrievalStrategy.CONTEXTUAL] = {
            "top_k": contextual_config.get("top_k", 6),
            "context_depth": contextual_config.get("context_depth", 2),
            "weight": contextual_config.get("weight", 0.7)
        }
        
        return params
    
    def _load_fallback_config(self):
        """Load fallback configuration (when config file loading fails)"""
        self.logger.info("Using fallback strategy configuration")
        
        # Default strategy configuration
        self.default_strategies = {
            QueryCategory.TEMPORAL: [RetrievalStrategy.TEMPORAL, RetrievalStrategy.SEMANTIC],
            QueryCategory.FACTUAL: [RetrievalStrategy.SEMANTIC, RetrievalStrategy.KEYWORD],
            QueryCategory.INFERENTIAL: [RetrievalStrategy.SEMANTIC, RetrievalStrategy.CONTEXTUAL],
            QueryCategory.DETAILED: [RetrievalStrategy.SEMANTIC, RetrievalStrategy.HIERARCHICAL],
            QueryCategory.ADVERSARIAL: [RetrievalStrategy.SEMANTIC, RetrievalStrategy.KEYWORD, RetrievalStrategy.CONTEXTUAL]
        }
        
        # Force-enable strategies
        self.force_enable_strategies = ["hierarchical"]
        
        # Strategy weights
        self.strategy_weights = {
            "semantic": 1.0,
            "temporal": 0.8,
            "keyword": 0.6,
            "hierarchical": 0.9,
            "contextual": 0.7
        }
        
        # Strategy parameter configuration
        self.strategy_params = {
            RetrievalStrategy.SEMANTIC: {
                "top_k": 10,
                "score_threshold": 0.0,  # Adjust to lowest threshold
                "weight": 1.0
            },
            RetrievalStrategy.TEMPORAL: {
                "top_k": 8,
                "time_window_days": 30,
                "weight": 0.8
            },
            RetrievalStrategy.KEYWORD: {
                "top_k": 5,
                "min_match_score": 0.2,
                "weight": 0.6
            },
            RetrievalStrategy.HIERARCHICAL: {
                "L1_limit": 10,
                "L2_limit": 3,
                "L3_limit": 0,
                "L4_limit": 0,
                "L5_limit": 0,
                "weight": 0.9,
                "hierarchical_sorting": True,
                "L1_sort_method": "relevance",
                "L2_sort_method": "temporal"
            },
            RetrievalStrategy.CONTEXTUAL: {
                "top_k": 6,
                "context_depth": 2,
                "weight": 0.7
            }
        }