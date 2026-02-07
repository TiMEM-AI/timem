"""
Intelligent Intent Resolver
==========================

This module serves as an upgraded entry point for the TiMem retrieval workflow,
integrating multi-dimensional query analysis and intelligent strategy composition,
replacing the original simple classification method with more accurate and flexible intent understanding.

Core Features:
1. Integrate the multi-dimensional query analyzer
2. Seamlessly connect with existing TiMem retrieval workflow
3. Provide backward-compatible interface
4. Support progressive upgrade

Author: TiMem Team
Date: 2024-12
"""

from typing import Dict, Any, Optional
from dataclasses import asdict

from timem.workflows.retrieval_state import RetrievalState, RetrievalStateValidator, QueryCategory, RetrievalStrategy
from timem.workflows.retrieval_nodes.multi_dimensional_query_analyzer import (
    MultiDimensionalQueryAnalyzer, 
    FeatureBasedStrategyComposer,
    QueryFeatures
)
from timem.utils.logging import get_logger

logger = get_logger(__name__)


class IntelligentIntentResolver:
    """
    Intelligent Intent Resolver
    
    Serves as a new entry point for TiMem retrieval workflow, providing more intelligent
    query understanding and strategy selection capabilities. Compatible with existing workflow
    interfaces and supports progressive upgrades.
    """
    
    def __init__(self, state_validator: Optional[RetrievalStateValidator] = None):
        """
        Initialize intelligent intent resolver
        
        Args:
            state_validator: State validator
        """
        self.state_validator = state_validator or RetrievalStateValidator()
        self.logger = get_logger(__name__)
        
        # Initialize core components
        self.query_analyzer = MultiDimensionalQueryAnalyzer()
        self.strategy_composer = FeatureBasedStrategyComposer()
        
        # Compatibility mapping
        self.compatibility_mapping = self._build_compatibility_mapping()
        
        self.logger.info("Intelligent intent resolver initialized")
    
    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute intelligent intent analysis
        
        Args:
            state: Workflow state dictionary
            
        Returns:
            Updated state dictionary with analysis results and strategy configuration
        """
        try:
            # Convert to RetrievalState object
            retrieval_state = self._dict_to_state(state)
            
            self.logger.info(f"🧠 Starting intelligent intent analysis: {retrieval_state.question}")
            
            # Step 1: Multi-dimensional query analysis
            query_features = await self.query_analyzer.analyze_query(
                retrieval_state.question,
                context={
                    "user_id": retrieval_state.user_id,
                    "expert_id": retrieval_state.expert_id,
                    "character_ids": retrieval_state.character_ids
                }
            )
            
            # Step 2: Feature-based strategy composition
            strategy_config = await self.strategy_composer.compose_retrieval_strategy(
                query_features,
                context=retrieval_state.context
            )
            
            # Step 3: Update retrieval state
            self._update_retrieval_state(retrieval_state, query_features, strategy_config)
            
            # Step 4: Compatibility handling (provide required fields for existing workflow)
            self._ensure_compatibility(retrieval_state, query_features)
            
            # Step 5: Validate results
            warnings = self.state_validator.validate_query_analysis(retrieval_state)
            retrieval_state.warnings.extend(warnings)
            
            self.logger.info(f"✅ Intent analysis completed - Strategies: {[s.value for s in retrieval_state.selected_strategies]}, "
                           f"Complexity: {query_features.overall_complexity:.2f}")
            
            # Save feature analysis results in state (for debugging and optimization)
            state_dict = self._state_to_dict(retrieval_state)
            state_dict['_query_features'] = asdict(query_features)
            state_dict['_strategy_config'] = strategy_config
            
            return state_dict
            
        except Exception as e:
            error_msg = f"Intelligent intent analysis failed: {str(e)}"
            self.logger.error(error_msg)
            state["errors"] = state.get("errors", []) + [error_msg]
            
            # Fallback to basic analysis
            return await self._fallback_analysis(state)
    
    def _update_retrieval_state(self, 
                               retrieval_state: RetrievalState, 
                               query_features: QueryFeatures, 
                               strategy_config: Dict[str, Any]):
        """Update retrieval state"""
        
        # Update strategy selection
        retrieval_state.selected_strategies = strategy_config["selected_strategies"]
        retrieval_state.retrieval_params = strategy_config["strategy_params"]
        
        # Update feature extraction results
        retrieval_state.time_entities = query_features.temporal.time_entities
        retrieval_state.key_entities = query_features.entity.named_entities
        
        # Generate query intent description
        retrieval_state.query_intent = self._generate_intent_description(query_features)
        
        # Set strategy weights (if not already in retrieval_params)
        for strategy, weight in strategy_config["strategy_weights"].items():
            weight_key = f"{strategy}_weight"
            if weight_key not in retrieval_state.retrieval_params:
                retrieval_state.retrieval_params[weight_key] = weight
    
    def _ensure_compatibility(self, retrieval_state: RetrievalState, query_features: QueryFeatures):
        """Ensure compatibility with existing workflow"""
        
        # For compatibility with existing code, we still need to set query_category
        # But this time based on intelligent mapping from feature analysis results
        retrieval_state.query_category = self._map_features_to_category(query_features)
        
        # Ensure key fields exist
        if not retrieval_state.key_entities:
            retrieval_state.key_entities = query_features.entity.named_entities
        
        if not retrieval_state.time_entities:
            retrieval_state.time_entities = query_features.temporal.time_entities
    
    def _map_features_to_category(self, query_features: QueryFeatures) -> QueryCategory:
        """
        Intelligently map multi-dimensional features to compatible query categories
        
        This mapping is not hard-coded classification, but intelligent inference based on features
        """
        
        # Temporal features dominate
        if (query_features.temporal.has_time_entities and 
            query_features.temporal.time_specificity > 0.6):
            return QueryCategory.TEMPORAL
        
        # High abstraction level, requires reasoning
        elif (query_features.semantic.abstraction_level > 0.6 or 
              query_features.complexity.inference_depth > 1):
            return QueryCategory.INFERENTIAL
        
        # Requires detailed information, broad scope
        elif (query_features.scope.scope_breadth > 0.7 or 
              query_features.scope.scope_depth > 0.6):
            return QueryCategory.DETAILED
        
        # Contains negation or high ambiguity, possibly adversarial query
        elif (query_features.semantic.contains_negation or 
              query_features.complexity.ambiguity_level > 0.7):
            return QueryCategory.ADVERSARIAL
        
        # Default to factual query
        else:
            return QueryCategory.FACTUAL
    
    def _generate_intent_description(self, query_features: QueryFeatures) -> str:
        """Generate natural language description of query intent"""
        
        components = []
        
        # Temporal feature description
        if query_features.temporal.has_time_entities:
            if query_features.temporal.time_scope == "point":
                components.append("specific time point query")
            elif query_features.temporal.time_scope == "range":
                components.append("time range query")
            else:
                components.append("time-related query")
        
        # Complexity description
        if query_features.overall_complexity > 0.7:
            components.append("high complexity")
        elif query_features.overall_complexity > 0.4:
            components.append("medium complexity")
        else:
            components.append("simple")
        
        # Abstraction level description
        if query_features.semantic.abstraction_level > 0.7:
            components.append("abstract concept query")
        elif query_features.semantic.abstraction_level < 0.3:
            components.append("concrete fact query")
        
        # Reasoning requirement description
        if query_features.complexity.multi_hop_reasoning:
            components.append("multi-hop reasoning")
        elif query_features.complexity.inference_depth > 1:
            components.append("requires reasoning")
        
        # Scope description
        if query_features.scope.scope_breadth > 0.7:
            components.append("broad scope")
        elif query_features.scope.cross_session:
            components.append("cross-session")
        
        return ", ".join(components) if components else "standard query"
    
    async def _fallback_analysis(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback analysis - used when main analysis fails"""
        self.logger.warning("Using fallback analysis mode")
        
        try:
            retrieval_state = self._dict_to_state(state)
            
            # Simple keyword analysis
            question_lower = retrieval_state.question.lower()
            
            # Basic strategy selection
            retrieval_state.selected_strategies = [RetrievalStrategy.SEMANTIC, RetrievalStrategy.FULLTEXT]
            
            # Simple category judgment
            if any(word in question_lower for word in ["when", "time", "date"]):
                retrieval_state.query_category = QueryCategory.TEMPORAL
                retrieval_state.selected_strategies.append(RetrievalStrategy.TEMPORAL)
            elif any(word in question_lower for word in ["why", "how"]):
                retrieval_state.query_category = QueryCategory.INFERENTIAL
                retrieval_state.selected_strategies.append(RetrievalStrategy.CONTEXTUAL)
            else:
                retrieval_state.query_category = QueryCategory.FACTUAL
            
            retrieval_state.query_intent = "fallback analysis mode"
            
            return self._state_to_dict(retrieval_state)
            
        except Exception as e:
            self.logger.error(f"Fallback analysis also failed: {str(e)}")
            return state
    
    def _build_compatibility_mapping(self) -> Dict[str, Any]:
        """Build compatibility mapping configuration"""
        return {
            "legacy_categories": {
                QueryCategory.FACTUAL: ["semantic", "fulltext", "keyword"],
                QueryCategory.TEMPORAL: ["temporal", "semantic", "fulltext"],
                QueryCategory.INFERENTIAL: ["semantic", "contextual", "fulltext"],
                QueryCategory.DETAILED: ["semantic", "hierarchical", "fulltext"],
                QueryCategory.ADVERSARIAL: ["semantic", "keyword", "contextual", "fulltext"]
            },
            "default_params": {
                "max_total_results": 20,
                "final_result_limit": 10,
                "score_threshold_global": 0.3
            }
        }
    
    def _dict_to_state(self, state_dict: Dict[str, Any]) -> RetrievalState:
        """Convert dictionary to RetrievalState object"""
        state = RetrievalState()
        
        # Copy existing fields
        for key, value in state_dict.items():
            if hasattr(state, key) and not key.startswith('_'):  # Ignore internal fields
                setattr(state, key, value)
                
        return state
    
    def _state_to_dict(self, state: RetrievalState) -> Dict[str, Any]:
        """Convert RetrievalState object to dictionary"""
        state_dict = {}
        
        # Copy all fields
        for key, value in state.__dict__.items():
            state_dict[key] = value
                
        return state_dict


class LegacyCompatibilityWrapper:
    """
    Legacy Compatibility Wrapper
    
    Provides the same interface as the original RetrievalPlanner for smooth migration
    """
    
    def __init__(self, use_intelligent_resolver: bool = True):
        """
        Initialize compatibility wrapper
        
        Args:
            use_intelligent_resolver: Whether to use the new intelligent resolver
        """
        self.use_intelligent_resolver = use_intelligent_resolver
        
        if use_intelligent_resolver:
            self.resolver = IntelligentIntentResolver()
        else:
            # Fallback: import the legacy rule-based retrieval planner
            from timem.workflows.retrieval_nodes.retrieval_planner import RetrievalPlanner
            self.resolver = RetrievalPlanner()
        
        self.logger = get_logger(__name__)
    
    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Run retrieval planning (compatible with the legacy interface)."""
        
        if self.use_intelligent_resolver:
            self.logger.info("🚀 Using intelligent intent resolver")
            return await self.resolver.run(state)
        else:
            self.logger.info("Using legacy retrieval planner")
            return await self.resolver.run(state)


# Convenience function: quick feature analysis
async def quick_analyze_query(query: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Quick retrieval planning helper
    
    Args:
        query: Query text
        context: Context information
        
    Returns:
        Analysis result dictionary
    """
    analyzer = MultiDimensionalQueryAnalyzer()
    composer = FeatureBasedStrategyComposer()
    
    # Analyze features
    features = await analyzer.analyze_query(query, context)
    
    # Compose strategies
    strategy_config = await composer.compose_retrieval_strategy(features, context)
    
    # Map features to QueryCategory
    query_category = _map_features_to_category(features)
    
    return {
        "query": query,
        "query_category": query_category,
        "features": asdict(features),
        "strategy_config": strategy_config,
        "recommended_strategies": [s.value for s in strategy_config["selected_strategies"]],
        "complexity_level": strategy_config["retrieval_profile"]["complexity_level"],
        "primary_focus": strategy_config["retrieval_profile"]["primary_focus"]
    }


def _map_features_to_category(features: QueryFeatures) -> QueryCategory:
    """
    Map multi-dimensional features to QueryCategory
    
    Args:
        features: Query feature analysis results
        
    Returns:
        Predicted QueryCategory
    """
    # Classification decision based on features
    
    # Optimized version - lower thresholds, improve complex query recognition accuracy
    
    # 1. Temporal localization - raised priority, significantly lowered threshold
    # As long as any temporal features are detected, prioritize temporal classification
    if (features.temporal.has_time_entities or 
        features.temporal.time_specificity > 0.2 or  # Significantly lowered from 0.5 to 0.2
        features.temporal.temporal_complexity > 0.3):  # Add temporal complexity check
        return QueryCategory.TEMPORAL
    
    # 2. Long-distance reasoning - significantly lowered threshold, added conditions  
    if (features.complexity.inference_depth > 0 or  # Changed from >1 to >0, any reasoning counts as complex
        features.complexity.multi_hop_reasoning or
        features.overall_complexity > 0.4 or  # Significantly lowered from 0.7 to 0.4
        (features.semantic.abstraction_level > 0.4 and features.entity.entity_count > 1)):
        return QueryCategory.INFERENTIAL
    
    # 3. Character description open-ended - lowered threshold
    if (features.scope.scope_breadth > 0.4 or  # Lowered from 0.7 to 0.4
        features.scope.scope_depth > 0.4 or   # Added depth check
        (features.semantic.abstraction_level > 0.5 and features.entity.entity_count > 2)):
        return QueryCategory.DETAILED
    
    # 4. Adversarial detection - lowered threshold
    if (features.semantic.contains_negation or 
        features.complexity.ambiguity_level > 0.5 or  # Lowered from higher threshold
        (features.overall_complexity > 0.3 and 
         features.semantic.query_intent_confidence < 0.5)):
        return QueryCategory.ADVERSARIAL
    
    # 5. Factual statement - raised standard, only truly simple queries classified as FACTUAL
    if (features.overall_complexity < 0.25 and  # Must be very low complexity
        features.entity.entity_count <= 1 and  # Very few entities
        not features.temporal.has_time_entities and  # No temporal features at all
        features.complexity.inference_depth == 0 and  # No reasoning required
        features.semantic.abstraction_level < 0.3):  # Very low abstraction level
        return QueryCategory.FACTUAL
    
    # 6. Default to inferential (avoid over-classification as FACTUAL)
    return QueryCategory.INFERENTIAL


# Configuration class: Intent resolution configuration
class IntentResolutionConfig:
    """Intent resolution configuration class"""
    
    def __init__(self):
        self.enable_intelligent_resolver = True
        self.fallback_on_error = True
        self.log_feature_analysis = False
        self.compatibility_mode = True
        
        # Feature weight configuration
        self.feature_weights = {
            "temporal": 0.25,
            "entity": 0.20,
            "semantic": 0.25,
            "complexity": 0.15,
            "scope": 0.15
        }
        
        # Strategy selection thresholds
        self.strategy_thresholds = {
            "temporal_threshold": 0.3,
            "entity_density_threshold": 0.3,
            "complexity_threshold": 0.6,
            "scope_breadth_threshold": 0.6
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format"""
        return {
            "enable_intelligent_resolver": self.enable_intelligent_resolver,
            "fallback_on_error": self.fallback_on_error,
            "log_feature_analysis": self.log_feature_analysis,
            "compatibility_mode": self.compatibility_mode,
            "feature_weights": self.feature_weights,
            "strategy_thresholds": self.strategy_thresholds
        }
