"""
Multi-dimensional Query Intent Understanding Framework
============================

This module implements an intent understanding system based on query intrinsic features,
avoiding hard-coded classification. Through multi-dimensional feature analysis,
dynamically selects retrieval strategy combinations.

Core Design Principles:
1. Don't rely on preset classifications, analyze query intrinsic features
2. Multi-dimensional feature extraction: temporal, entity, semantic, complexity, scope
3. Dynamically combine retrieval strategies based on features
4. Deep integration with TiMem hierarchical memory system

Author: TiMem Team
Date: 2024-12
"""

import re
import math
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
import jieba
from datetime import datetime, timedelta

from timem.workflows.retrieval_state import RetrievalState, RetrievalStrategy
from timem.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TemporalFeatures:
    """Temporal features"""
    has_time_entities: bool = False
    time_specificity: float = 0.0  # 0-1, time specificity level
    time_scope: str = "unknown"  # "point", "range", "relative", "unknown"
    time_entities: List[Dict[str, Any]] = field(default_factory=list)
    temporal_complexity: float = 0.0  # 0-1, temporal expression complexity


@dataclass
class EntityFeatures:
    """Entity features"""
    entity_count: int = 0
    entity_types: Set[str] = field(default_factory=set)
    named_entities: List[str] = field(default_factory=list)
    entity_relationships: List[Tuple[str, str]] = field(default_factory=list)
    entity_density: float = 0.0  # entity density = entity count / total words


@dataclass
class SemanticFeatures:
    """Semantic features"""
    query_intent_confidence: float = 0.0  # 0-1, intent clarity
    abstraction_level: float = 0.0  # 0-1, abstraction level (0=concrete, 1=abstract)
    emotional_tone: float = 0.0  # -1 to 1, emotional tendency
    semantic_density: float = 0.0  # semantic density
    contains_negation: bool = False  # whether contains negation


@dataclass
class ComplexityFeatures:
    """Complexity features"""
    syntactic_complexity: float = 0.0  # 0-1, syntactic complexity
    logical_complexity: float = 0.0  # 0-1, logical complexity  
    inference_depth: int = 0  # required reasoning depth 0-3
    ambiguity_level: float = 0.0  # 0-1, ambiguity level
    multi_hop_reasoning: bool = False  # whether requires multi-hop reasoning


@dataclass
class ScopeFeatures:
    """Scope features"""
    scope_breadth: float = 0.0  # 0-1, query scope breadth
    scope_depth: float = 0.0  # 0-1, query depth
    cross_session: bool = False  # whether cross-session
    cross_temporal: bool = False  # whether cross-temporal
    granularity_level: str = "medium"  # "fine", "medium", "coarse"


@dataclass
class QueryFeatures:
    """Composite feature representation of query"""
    temporal: TemporalFeatures = field(default_factory=TemporalFeatures)
    entity: EntityFeatures = field(default_factory=EntityFeatures)
    semantic: SemanticFeatures = field(default_factory=SemanticFeatures)
    complexity: ComplexityFeatures = field(default_factory=ComplexityFeatures)
    scope: ScopeFeatures = field(default_factory=ScopeFeatures)
    
    # Composite scores
    overall_complexity: float = 0.0  # overall complexity 0-1
    retrieval_difficulty: float = 0.0  # retrieval difficulty 0-1


class MultiDimensionalQueryAnalyzer:
    """Multi-dimensional query analyzer."""
    
    def __init__(self):
        self.logger = get_logger(__name__)
        
        # Initialize Chinese tokenization (use basic mode, avoid paddle dependency issues)
        # jieba.enable_paddle()  # Temporarily disable paddle mode
        
        # Temporal keyword patterns
        self.temporal_patterns = self._build_temporal_patterns()
        
        # Entity recognition patterns
        self.entity_patterns = self._build_entity_patterns()
        
        # Semantic analysis patterns
        self.semantic_patterns = self._build_semantic_patterns()
        
        # Complexity indicators
        self.complexity_indicators = self._build_complexity_indicators()
        
    async def analyze_query(self, query: str, context: Dict[str, Any] = None) -> QueryFeatures:
        """
        Multi-dimensional query feature analysis.
        
        Args:
            query: User query text
            context: Context information (user_id, character_ids, etc.)
            
        Returns:
            QueryFeatures: Multi-dimensional query features
        """
        self.logger.info(f"Start multi-dimensional query analysis: {query}")
        
        # 1. Basic preprocessing
        processed_query = self._preprocess_query(query)
        tokens = self._tokenize_query(processed_query)
        
        # 2. Extract multi-dimensional features
        temporal_features = await self._extract_temporal_features(query, tokens)
        entity_features = await self._extract_entity_features(query, tokens, context)
        semantic_features = await self._extract_semantic_features(query, tokens)
        complexity_features = await self._extract_complexity_features(query, tokens)
        scope_features = await self._extract_scope_features(query, tokens, context)
        
        # 3. Calculate composite features
        query_features = QueryFeatures(
            temporal=temporal_features,
            entity=entity_features,
            semantic=semantic_features,
            complexity=complexity_features,
            scope=scope_features
        )
        
        # 4. Calculate composite scores
        query_features.overall_complexity = self._calculate_overall_complexity(query_features)
        query_features.retrieval_difficulty = self._calculate_retrieval_difficulty(query_features)
        
        self.logger.info(
            f"Query analysis complete - complexity: {query_features.overall_complexity:.2f}, "
            f"retrieval difficulty: {query_features.retrieval_difficulty:.2f}"
        )
        
        return query_features
    
    async def _extract_temporal_features(self, query: str, tokens: List[str]) -> TemporalFeatures:
        """Extract temporal features"""
        features = TemporalFeatures()
        
        # Detect time entities
        time_entities = []
        for pattern_name, pattern in self.temporal_patterns.items():
            matches = re.finditer(pattern, query, re.IGNORECASE)
            for match in matches:
                time_entities.append({
                    "text": match.group(),
                    "type": pattern_name,
                    "position": match.span()
                })
        
        features.time_entities = time_entities
        features.has_time_entities = len(time_entities) > 0
        
        # Calculate time specificity (higher score for more specific, especially focus on when questions)
        if time_entities:
            specificity_scores = []
            has_when_question = False
            
            for entity in time_entities:
                entity_type = entity["type"]
                
                # Prioritize when questions and time interrogatives
                if entity_type in ["when_questions", "time_interrogatives"]:
                    has_when_question = True
                    specificity_scores.append(0.8)  # when questions are strong time signals
                elif entity_type in ["specific_date", "specific_time"]:
                    specificity_scores.append(1.0)
                elif entity_type in ["year_month", "year"]:
                    specificity_scores.append(0.7)
                elif entity_type in ["relative_time", "season"]:
                    specificity_scores.append(0.4)
                elif entity_type in ["time_units", "temporal_prepositions", "time_of_day"]:
                    specificity_scores.append(0.3)
                else:
                    specificity_scores.append(0.2)
            
            # Base specificity score
            base_specificity = max(specificity_scores) if specificity_scores else 0
            
            # If contains when question, boost specificity
            if has_when_question:
                features.time_specificity = min(base_specificity + 0.2, 1.0)
            else:
                features.time_specificity = base_specificity
        
        # Determine time scope type
        if any("to" in e["text"] or "from" in e["text"].lower() or "since" in e["text"].lower() 
               for e in time_entities):
            features.time_scope = "range"
        elif any(pattern in query.lower() for pattern in ["before", "after", "ago", "before", "after"]):
            features.time_scope = "relative"
        elif time_entities:
            features.time_scope = "point"
        
        # Calculate temporal complexity (enhance when question detection weight)
        temporal_keywords = ["before", "after", "during", "since", "while", "then", "before", "after", "during", "since", "while", "then"]
        temporal_keyword_count = sum(1 for keyword in temporal_keywords if keyword in query.lower())
        
        # Check if has when question
        has_when_query = any(entity["type"] in ["when_questions", "time_interrogatives"] for entity in time_entities)
        
        # Base complexity calculation
        base_complexity = temporal_keyword_count / 3.0
        
        # If has when question, boost temporal complexity (indicates clear time query)
        if has_when_query:
            features.temporal_complexity = min(base_complexity + 0.5, 1.0)
        else:
            features.temporal_complexity = min(base_complexity, 1.0)
        
        return features
    
    async def _extract_entity_features(self, query: str, tokens: List[str], context: Dict[str, Any] = None) -> EntityFeatures:
        """Extract entity features"""
        features = EntityFeatures()
        
        # Use simple entity recognition (can be replaced with more advanced NER)
        named_entities = []
        entity_types = set()
        
        # Person name detection (common Chinese surnames + English capitalized words)
        for token in tokens:
            if self._is_person_name(token):
                named_entities.append(token)
                entity_types.add("PERSON")
        
        # Location detection
        location_keywords = ["University", "School", "Company", "Hospital", "Park", "Road", "Street", "City", "District", "Province", "Country"]
        for token in tokens:
            if any(keyword in token for keyword in location_keywords) or token.istitle():
                if token not in named_entities:  # Avoid duplicates
                    named_entities.append(token)
                    entity_types.add("LOCATION")
        
        # Organization detection
        org_keywords = ["Company", "College", "Department", "Organization", "Association", "Bureau", "Committee"]
        for token in tokens:
            if any(keyword in token for keyword in org_keywords):
                if token not in named_entities:
                    named_entities.append(token)
                    entity_types.add("ORGANIZATION")
        
        features.named_entities = named_entities
        features.entity_count = len(named_entities)
        features.entity_types = entity_types
        features.entity_density = len(named_entities) / max(len(tokens), 1)
        
        # Simple entity relationship detection
        relationships = []
        relation_keywords = ["and", "with", "of", "at", "to", "from", "to", "with", "at", "in"]
        for i, token in enumerate(tokens):
            if token in relation_keywords and i > 0 and i < len(tokens) - 1:
                if tokens[i-1] in named_entities and tokens[i+1] in named_entities:
                    relationships.append((tokens[i-1], tokens[i+1]))
        
        features.entity_relationships = relationships
        
        return features
    
    async def _extract_semantic_features(self, query: str, tokens: List[str]) -> SemanticFeatures:
        """Extract semantic features"""
        features = SemanticFeatures()
        
        # Intent clarity (based on question words and language structure)
        question_words = ["what", "who", "which", "how", "why", "when", "where", "what", "who", "how", "why", "when"]
        question_word_count = sum(1 for word in question_words if word in query.lower())
        features.query_intent_confidence = min(question_word_count / 2.0, 1.0)
        
        # Abstraction level (abstract vocabulary vs concrete vocabulary)
        abstract_keywords = ["concept", "idea", "feeling", "impression", "character", "feature", "ability", "quality", "attitude", 
                           "relationship", "feeling", "impression", "character", "ability", "quality"]
        concrete_keywords = ["did", "went", "bought", "said", "saw", "heard", 
                           "did", "went", "bought", "said", "saw", "heard"]
        
        abstract_count = sum(1 for word in abstract_keywords if word in query.lower())
        concrete_count = sum(1 for word in concrete_keywords if word in query.lower())
        
        if abstract_count + concrete_count > 0:
            features.abstraction_level = abstract_count / (abstract_count + concrete_count)
        else:
            features.abstraction_level = 0.5  # Neutral
        
        # Negation detection
        negation_words = ["not", "no", "never", "none", "not", "no", "never", "none"]
        features.contains_negation = any(word in query.lower() for word in negation_words)
        
        # Semantic density (content words vs function words)
        content_words = [token for token in tokens if len(token) > 1 and not token in ["of", "the", "is", "in", "at", "and", "the", "is", "in", "at"]]
        features.semantic_density = len(content_words) / max(len(tokens), 1)
        
        return features
    
    async def _extract_complexity_features(self, query: str, tokens: List[str]) -> ComplexityFeatures:
        """Extract complexity features"""
        features = ComplexityFeatures()
        
        # Syntactic complexity (based on sentence length and structure)
        sentence_length = len(tokens)
        clause_count = query.count(',') + query.count(',') + query.count('.') + query.count('.') + 1
        features.syntactic_complexity = min((sentence_length / 20.0) + (clause_count / 3.0), 1.0)
        
        # Logical complexity (based on logical connectors)
        logical_connectors = ["but", "however", "because", "so", "if", "although", "unless", 
                            "but", "however", "because", "so", "if", "although", "unless"]
        logical_count = sum(1 for connector in logical_connectors if connector in query.lower())
        features.logical_complexity = min(logical_count / 2.0, 1.0)
        
        # Inference depth (based on reasoning indicators)
        reasoning_indicators = {
            0: ["is", "has", "did", "is", "has", "did"],  # Direct facts
            1: ["why", "how", "why", "how"],  # One-level reasoning
            2: ["might", "should", "would", "might", "should", "would"],  # Two-level reasoning
            3: ["suppose", "assume", "if", "suppose", "assume", "if"]  # Three-level reasoning
        }
        
        max_depth = 0
        for depth, indicators in reasoning_indicators.items():
            if any(indicator in query.lower() for indicator in indicators):
                max_depth = max(max_depth, depth)
        
        features.inference_depth = max_depth
        
        # Multi-hop reasoning detection
        multi_hop_indicators = ["then", "next", "after", "also", "additionally", "then", "next", "after", "also", "additionally"]
        features.multi_hop_reasoning = any(indicator in query.lower() for indicator in multi_hop_indicators)
        
        # Ambiguity level (based on fuzzy vocabulary)
        ambiguous_words = ["some", "maybe", "probably", "seems", "appears", "some", "maybe", "probably", "seems", "appears"]
        ambiguous_count = sum(1 for word in ambiguous_words if word in query.lower())
        features.ambiguity_level = min(ambiguous_count / 3.0, 1.0)
        
        return features
    
    async def _extract_scope_features(self, query: str, tokens: List[str], context: Dict[str, Any] = None) -> ScopeFeatures:
        """Extract scope features"""
        features = ScopeFeatures()
        
        # Scope breadth (based on scope indicators)
        scope_indicators = {
            "narrow": ["this", "that", "this", "today", "this", "that", "today"],
            "medium": ["recent", "this week", "this month", "recent", "this week", "this month"],
            "broad": ["all", "everything", "always", "all", "all", "everything", "all", "all"]
        }
        
        if any(word in query.lower() for word in scope_indicators["broad"]):
            features.scope_breadth = 1.0
        elif any(word in query.lower() for word in scope_indicators["medium"]):
            features.scope_breadth = 0.6
        elif any(word in query.lower() for word in scope_indicators["narrow"]):
            features.scope_breadth = 0.3
        else:
            features.scope_breadth = 0.5  # Default medium
        
        # Depth analysis (based on detail requirements)
        detail_indicators = ["detail", "specific", "comprehensive", "thorough", "detail", "specific", "comprehensive", "thorough"]
        detail_count = sum(1 for indicator in detail_indicators if indicator in query.lower())
        features.scope_depth = min(detail_count / 2.0, 1.0)
        
        # Cross-session/cross-temporal detection
        cross_indicators = ["previous", "history", "past", "always", "previous", "history", "past", "always"]
        features.cross_session = any(indicator in query.lower() for indicator in cross_indicators)
        features.cross_temporal = features.cross_session  # Simplified handling
        
        # Granularity level
        if any(word in query.lower() for word in ["overall", "general", "overall", "general"]):
            features.granularity_level = "coarse"
        elif any(word in query.lower() for word in ["precise", "specific", "exact", "precise", "specific", "exact"]):
            features.granularity_level = "fine"
        else:
            features.granularity_level = "medium"
        
        return features
    
    def _calculate_overall_complexity(self, features: QueryFeatures) -> float:
        """Calculate overall complexity score (optimized version - improve complex query detection sensitivity)"""
        
        # Basic complexity factors (reweight, more sensitive)
        complexity_factors = []
        
        # 1. Temporal complexity factor (increase weight, time queries should be detected)
        temporal_factor = features.temporal.temporal_complexity * 0.25
        complexity_factors.append(temporal_factor)
        
        # 2. Entity complexity factor (consider entity count and density)
        entity_factor = min(features.entity.entity_count / 5.0, 1.0) * 0.2  # Lower threshold, 5 entities = complex
        if features.entity.entity_density > 0.3:  # High entity density also increases complexity
            entity_factor += 0.1
        complexity_factors.append(entity_factor)
        
        # 3. Semantic abstraction factor (increase weight)
        semantic_factor = features.semantic.abstraction_level * 0.25
        complexity_factors.append(semantic_factor)
        
        # 4. Syntactic complexity factor
        syntactic_factor = features.complexity.syntactic_complexity * 0.15
        complexity_factors.append(syntactic_factor)
        
        # 5. Logical complexity factor (increase weight)
        logical_factor = features.complexity.logical_complexity * 0.2
        complexity_factors.append(logical_factor)
        
        # 6. Inference depth factor (significantly increase weight)
        if features.complexity.inference_depth > 0:
            inference_factor = min(features.complexity.inference_depth / 2.0, 1.0) * 0.3  # Depth 1 gives 0.15 score
        else:
            inference_factor = 0
        complexity_factors.append(inference_factor)
        
        # 7. Scope complexity factor (new)
        scope_factor = (features.scope.scope_breadth * 0.5 + features.scope.scope_depth * 0.5) * 0.15
        complexity_factors.append(scope_factor)
        
        # Calculate base complexity
        base_complexity = sum(complexity_factors)
        
        # Special case enhancement
        bonus_complexity = 0
        
        # If contains negation, increase complexity
        if features.semantic.contains_negation:
            bonus_complexity += 0.15
            
        # If multi-hop reasoning, significantly increase complexity
        if features.complexity.multi_hop_reasoning:
            bonus_complexity += 0.2
            
        # If query intent unclear, increase complexity
        if features.semantic.query_intent_confidence < 0.5:
            bonus_complexity += 0.1
            
        # Final complexity
        final_complexity = min(base_complexity + bonus_complexity, 1.0)
        
        return final_complexity
    
    def _calculate_retrieval_difficulty(self, features: QueryFeatures) -> float:
        """Calculate retrieval difficulty score"""
        difficulty_factors = [
            features.scope.scope_breadth * 0.3,  # Broader scope = harder
            (1 - features.semantic.query_intent_confidence) * 0.2,  # Unclear intent = harder
            features.complexity.ambiguity_level * 0.2,  # More ambiguity = harder
            (1 - features.temporal.time_specificity) * 0.15,  # Less specific time = harder
            (features.entity.entity_count / 10.0) * 0.15  # More entities = more complex
        ]
        
        return min(sum(difficulty_factors), 1.0)
    
    # Helper methods
    def _preprocess_query(self, query: str) -> str:
        """Preprocess query text"""
        # Simple text cleaning
        query = re.sub(r'\s+', ' ', query.strip())
        return query
    
    def _tokenize_query(self, query: str) -> List[str]:
        """Tokenize query"""
        # Detect language and select tokenization method
        if re.search(r'[\u4e00-\u9fff]', query):
            # Chinese tokenization
            return list(jieba.cut(query))
        else:
            # English tokenization
            return re.findall(r'\b\w+\b', query.lower())
    
    def _is_person_name(self, token: str) -> bool:
        """Determine if token is a person name"""
        chinese_surnames = ['Wang', 'Li', 'Zhang', 'Liu', 'Chen', 'Yang', 'Zhao', 'Huang', 'Zhou', 'Wu', 'Xu', 'Sun', 'Hu', 'Zhu', 'Gao', 'Lin', 'He', 'Guo', 'Ma', 'Luo']
        
        # Chinese person name detection
        if len(token) >= 2 and token[0] in chinese_surnames:
            return True
        
        # English person name detection (simple rule: capitalized and appropriate length)
        if token.istitle() and 2 <= len(token) <= 15:
            return True
        
        return False
    
    def _build_temporal_patterns(self) -> Dict[str, str]:
        """Build temporal patterns"""
        return {
            # High-weight time indicators - clear time queries
            "when_questions": r'\b(?:when\s+did|when\s+was|when\s+were|when\s+will|when\s+does|when\s+do|at\s+what\s+time|when|when)\b',
            "time_interrogatives": r'\b(?:what\s+time|which\s+day|what\s+date|what time|which day|what date)\b',
            
            # Specific time expressions
            "specific_date": r'\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{1,2}-\d{1,2}',
            "year_month": r'\d{4}-\d{1,2}|\d{1,2}/\d{4}',
            "year": r'\d{4}',
            
            # Relative time expressions
            "relative_time": r'yesterday|today|tomorrow|last\s+\w+|this\s+\w+|next\s+\w+|ago|before|after',
            "season": r'spring|summer|autumn|winter',
            "time_of_day": r'morning|afternoon|evening|night|midnight|dawn',
            
            # Time units and concepts
            "time_units": r'\b(?:second|minute|hour|day|week|month|year|decade|century)\b',
            "temporal_prepositions": r'\b(?:during|while|since|until|from|to|during|from|to)\b'
        }
    
    def _build_entity_patterns(self) -> Dict[str, str]:
        """Build entity patterns"""
        return {
            "person": r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*',
            "location": r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*',
            "organization": r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*'
        }
    
    def _build_semantic_patterns(self) -> Dict[str, List[str]]:
        """Build semantic patterns"""
        return {
            "question_words": ["where", "what", "who", "how", "why", "when", "where", "what", "who", "how", "why", "when"],
            "abstract_concepts": ["concept", "idea", "feeling", "impression", "character", "feature", "ability", "quality", "attitude"],
            "concrete_actions": ["did", "went", "bought", "said", "saw", "heard", "did", "went", "bought", "said"]
        }
    
    def _build_complexity_indicators(self) -> Dict[str, List[str]]:
        """Build complexity indicators"""
        return {
            "logical_connectors": ["but", "however", "because", "so", "if", "although", "unless"],
            "reasoning_words": ["why", "how", "might", "should", "would", "suppose"],
            "scope_words": ["all", "everything", "always", "always", "recent", "this week"]
        }


class FeatureBasedStrategyComposer:
    """Feature-based strategy composer"""
    
    def __init__(self):
        self.logger = get_logger(__name__)
    
    async def compose_retrieval_strategy(self, features: QueryFeatures, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Compose retrieval strategy based on query features
        
        Args:
            features: Query features
            context: Context information
            
        Returns:
            Strategy configuration dictionary
        """
        self.logger.info("Start composing retrieval strategy based on features")
        
        # 1. Select retrieval strategies
        strategies = self._select_retrieval_strategies(features)
        
        # 2. Determine memory layer mapping
        layer_mapping = self._determine_layer_mapping(features)
        
        # 3. Dynamically adjust parameters
        strategy_params = self._adjust_strategy_parameters(features, strategies)
        
        # 4. Set strategy weights
        strategy_weights = self._calculate_strategy_weights(features, strategies)
        
        result = {
            "selected_strategies": strategies,
            "layer_mapping": layer_mapping,
            "strategy_params": strategy_params,
            "strategy_weights": strategy_weights,
            "retrieval_profile": self._generate_retrieval_profile(features)
        }
        
        self.logger.info(f"Strategy composition complete: {len(strategies)} strategies, "
                        f"primary layers: {layer_mapping.get('primary_layers', [])}")
        
        return result
    
    def _select_retrieval_strategies(self, features: QueryFeatures) -> List[RetrievalStrategy]:
        """Select retrieval strategies based on features"""
        strategies = []
        
        # Base strategy: semantic retrieval (always included)
        strategies.append(RetrievalStrategy.SEMANTIC)
        
        # Temporal strategy selection
        if features.temporal.has_time_entities or features.temporal.temporal_complexity > 0.3:
            strategies.append(RetrievalStrategy.TEMPORAL)
        
        # Fulltext retrieval (effective for concrete fact queries)
        if features.semantic.abstraction_level < 0.5 or features.entity.entity_count > 0:
            strategies.append(RetrievalStrategy.FULLTEXT)
        
        # Keyword retrieval (for high entity density queries)
        if features.entity.entity_density > 0.3 or features.overall_complexity > 0.6:
            strategies.append(RetrievalStrategy.KEYWORD)
        
        # Hierarchical retrieval (based on scope and depth)
        if features.scope.scope_breadth > 0.6 or features.scope.scope_depth > 0.5:
            strategies.append(RetrievalStrategy.HIERARCHICAL)
        
        # Contextual retrieval (for complex reasoning queries)
        if (features.complexity.inference_depth > 1 or 
            features.complexity.multi_hop_reasoning or
            len(features.entity.entity_relationships) > 0):
            strategies.append(RetrievalStrategy.CONTEXTUAL)
        
        return list(set(strategies))  # Deduplicate
    
    def _determine_layer_mapping(self, features: QueryFeatures) -> Dict[str, Any]:
        """Determine memory layer mapping"""
        
        # Determine primary retrieval layers based on query features
        primary_layers = []
        secondary_layers = []
        
        # L1: Detailed fragments - suitable for concrete fact queries
        if (features.semantic.abstraction_level < 0.4 or 
            features.temporal.time_specificity > 0.7 or
            features.scope.granularity_level == "fine"):
            primary_layers.append("L1")
        
        # L2: Session-level - suitable for medium complexity queries
        if (0.3 <= features.semantic.abstraction_level <= 0.7 or
            features.entity.entity_count > 1 or
            features.scope.granularity_level == "medium"):
            primary_layers.append("L2")
        
        # L3: Daily report - suitable for cross-session queries
        if (features.scope.cross_session or
            features.scope.scope_breadth > 0.6 or
            features.complexity.inference_depth > 1):
            secondary_layers.append("L3")
        
        # L4/L5: High-level - suitable for abstract and long-term analysis
        if (features.semantic.abstraction_level > 0.7 or
            features.scope.scope_breadth > 0.8 or
            features.complexity.inference_depth > 2):
            secondary_layers.extend(["L4", "L5"])
        
        # Default strategy
        if not primary_layers:
            primary_layers = ["L1", "L2"]
        
        return {
            "primary_layers": primary_layers,
            "secondary_layers": secondary_layers,
            "layer_weights": self._calculate_layer_weights(features, primary_layers, secondary_layers)
        }
    
    def _adjust_strategy_parameters(self, features: QueryFeatures, strategies: List[RetrievalStrategy]) -> Dict[str, Any]:
        """Dynamically adjust strategy parameters"""
        params = {}
        
        # Adjust top_k based on complexity
        base_top_k = 10
        complexity_multiplier = 1 + features.overall_complexity * 0.5
        adjusted_top_k = int(base_top_k * complexity_multiplier)
        
        for strategy in strategies:
            strategy_key = strategy.value
            
            if strategy == RetrievalStrategy.SEMANTIC:
                params[f"{strategy_key}_top_k"] = adjusted_top_k
                params[f"{strategy_key}_score_threshold"] = max(0.2, 0.4 - features.complexity.ambiguity_level * 0.2)
                
            elif strategy == RetrievalStrategy.TEMPORAL:
                # Adjust time window based on temporal features
                if features.temporal.time_scope == "range":
                    params[f"{strategy_key}_time_window_days"] = 365
                elif features.temporal.time_specificity > 0.8:
                    params[f"{strategy_key}_time_window_days"] = 30
                else:
                    params[f"{strategy_key}_time_window_days"] = 90
                params[f"{strategy_key}_top_k"] = min(adjusted_top_k, 8)
                
            elif strategy == RetrievalStrategy.FULLTEXT:
                params[f"{strategy_key}_top_k"] = adjusted_top_k + 5
                params[f"{strategy_key}_min_bm25_score"] = 0.1
                
            elif strategy == RetrievalStrategy.KEYWORD:
                params[f"{strategy_key}_top_k"] = max(5, adjusted_top_k // 2)
                params[f"{strategy_key}_min_match_score"] = 0.15
                
            elif strategy == RetrievalStrategy.HIERARCHICAL:
                # Adjust layer limits based on query features
                if "L1" in features.scope.granularity_level or features.semantic.abstraction_level < 0.4:
                    params[f"{strategy_key}_L1_limit"] = 15
                    params[f"{strategy_key}_L2_limit"] = 5
                else:
                    params[f"{strategy_key}_L1_limit"] = 8
                    params[f"{strategy_key}_L2_limit"] = 3
                
            elif strategy == RetrievalStrategy.CONTEXTUAL:
                params[f"{strategy_key}_context_depth"] = min(3, features.complexity.inference_depth + 1)
                params[f"{strategy_key}_top_k"] = max(6, adjusted_top_k // 2)
        
        return params
    
    def _calculate_strategy_weights(self, features: QueryFeatures, strategies: List[RetrievalStrategy]) -> Dict[str, float]:
        """Calculate strategy weights"""
        weights = {}
        
        for strategy in strategies:
            if strategy == RetrievalStrategy.SEMANTIC:
                # Semantic retrieval base weight, adjusted by query intent clarity
                weights[strategy.value] = 0.8 + features.semantic.query_intent_confidence * 0.2
                
            elif strategy == RetrievalStrategy.TEMPORAL:
                # Temporal retrieval weight based on temporal features
                weights[strategy.value] = 0.6 + features.temporal.time_specificity * 0.3
                
            elif strategy == RetrievalStrategy.FULLTEXT:
                # Full-text retrieval has higher weight for concrete queries
                weights[strategy.value] = 0.9 + (1 - features.semantic.abstraction_level) * 0.3
                
            elif strategy == RetrievalStrategy.KEYWORD:
                # Keyword retrieval based on entity density
                weights[strategy.value] = 0.5 + features.entity.entity_density * 0.4
                
            elif strategy == RetrievalStrategy.HIERARCHICAL:
                # Hierarchical retrieval based on scope breadth
                weights[strategy.value] = 0.7 + features.scope.scope_breadth * 0.3
                
            elif strategy == RetrievalStrategy.CONTEXTUAL:
                # Contextual retrieval based on reasoning complexity
                weights[strategy.value] = 0.6 + (features.complexity.inference_depth / 3.0) * 0.4
        
        return weights
    
    def _calculate_layer_weights(self, features: QueryFeatures, primary_layers: List[str], secondary_layers: List[str]) -> Dict[str, float]:
        """Calculate memory layer weights"""
        weights = {
            "L1": 0.8,
            "L2": 0.9,
            "L3": 0.7,
            "L4": 0.6,
            "L5": 0.5
        }
        
        # Adjust weights based on query features
        if features.semantic.abstraction_level < 0.3:
            # Concrete query, boost L1 weight
            weights["L1"] = 0.95
        elif features.semantic.abstraction_level > 0.7:
            # Abstract query, boost high-level weights
            weights["L3"] = 0.8
            weights["L4"] = 0.75
            weights["L5"] = 0.7
        
        # Boost primary layer weights
        for layer in primary_layers:
            weights[layer] = min(weights[layer] + 0.1, 1.0)
        
        return weights
    
    def _generate_retrieval_profile(self, features: QueryFeatures) -> Dict[str, Any]:
        """Generate retrieval profile summary"""
        return {
            "complexity_level": "high" if features.overall_complexity > 0.7 else 
                              "medium" if features.overall_complexity > 0.4 else "low",
            "primary_focus": self._determine_primary_focus(features),
            "retrieval_breadth": "broad" if features.scope.scope_breadth > 0.7 else
                               "narrow" if features.scope.scope_breadth < 0.3 else "medium",
            "time_sensitivity": features.temporal.has_time_entities,
            "entity_richness": features.entity.entity_count,
            "reasoning_required": features.complexity.inference_depth > 1
        }
    
    def _determine_primary_focus(self, features: QueryFeatures) -> str:
        """Determine primary retrieval focus"""
        if features.temporal.has_time_entities and features.temporal.time_specificity > 0.6:
            return "temporal"
        elif features.entity.entity_density > 0.4:
            return "entity_centric"
        elif features.semantic.abstraction_level > 0.7:
            return "conceptual"
        elif features.complexity.inference_depth > 1:
            return "analytical"
        else:
            return "factual"
