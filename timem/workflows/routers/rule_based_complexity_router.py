#!/usr/bin/env python3
"""
Rule-based question complexity-aware router

Uses heuristic rules to determine question complexity based on QA data analysis
"""

import re
from enum import Enum
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

class ComplexityLevel(Enum):
    """Question complexity level"""
    SIMPLE = "simple"      # Simple questions: single entity, time-based queries
    MEDIUM = "medium"      # Medium questions: require aggregating multiple information
    COMPLEX = "complex"    # Complex questions: require reasoning, prediction, analysis

@dataclass
class ComplexityAssessment:
    """Complexity assessment result"""
    level: ComplexityLevel
    confidence: float
    reasoning: str
    features: Dict[str, Any]

class RuleBasedComplexityRouter:
    """Rule-based complexity router"""
    
    def __init__(self):
        """Initialize router"""
        # Simple question patterns
        self.simple_patterns = {
            'time_queries': [
                r'^when did .+ (go|do|say|visit|run|paint|sign|give)',
                r'^when (is|was) .+ (planning|going)',
                r'^when did .+ get .+',
            ],
            'single_fact_queries': [
                r'^what (is|did) .+ (identity|research|do|say)',
                r'^what .+ (research|study|buy)',
                r'^who (is|was|did) .+',
                r'^where (is|did) .+ (go|live|move)',
                r'^how (many|much|long) .+',
            ],
            'single_entity_questions': [
                r'^what is .+\'s .+',  # "What is Caroline's identity?"
                r'^(who|what|where|when) .+ (specific|particular)',
            ]
        }
        
        # Medium question patterns
        self.medium_patterns = {
            'aggregation_queries': [
                r'^what (fields|activities|types|kinds|ways) .+',
                r'^what .+ (like|enjoy|do) .+',
                r'^where (has|have) .+ (been|gone|visited|camped)',
                r'^what .+ (books|items|things) .+',
                r'^(list|name) .+ that .+',
            ],
            'multi_aspect_queries': [
                r'^what .+ and .+',  # Queries containing "and"
                r'^which .+ (are|were|would)',
                r'^describe .+',
            ]
        }
        
        # Complex question patterns
        self.complex_patterns = {
            'prediction_queries': [
                r'^would .+ (likely|probably|be|go|do)',
                r'^will .+ (be|do|have)',
                r'^is .+ likely to .+',
                r'would .+ soon',
            ],
            'reasoning_queries': [
                r'^why (did|does|would) .+',
                r'^how (did|does|do) .+ feel',
                r'^(analyze|explain|compare) .+',
                r'^what (motivated|inspired|caused) .+',
            ],
            'judgment_queries': [
                r'^(should|could|might) .+',
                r'^do you think .+',
                r'^is it (possible|likely) .+',
            ],
            'conditional_queries': [
                r'^if .+ then .+',
                r'^assuming .+',
                r'^given that .+',
            ]
        }
        
        # Complexity indicator word weights
        self.complexity_indicators = {
            'simple_words': {
                'when': 0.8, 'what': 0.6, 'where': 0.7, 'who': 0.8, 'how_many': 0.9
            },
            'medium_words': {
                'types': 0.7, 'kinds': 0.7, 'activities': 0.6, 'ways': 0.6
            },
            'complex_words': {
                'would': 0.8, 'likely': 0.9, 'analyze': 0.9, 'why': 0.7, 'feel': 0.8,
                'compare': 0.9, 'predict': 0.9, 'if': 0.6
            }
        }
    
    def assess_complexity(self, question: str) -> ComplexityAssessment:
        """
        Assess question complexity
        
        Args:
            question: Input question
            
        Returns:
            ComplexityAssessment: Complexity assessment result
        """
        question_lower = question.lower().strip()
        features = self._extract_features(question_lower)
        
        # Rule scoring
        simple_score = self._calculate_pattern_score(question_lower, self.simple_patterns)
        medium_score = self._calculate_pattern_score(question_lower, self.medium_patterns)
        complex_score = self._calculate_pattern_score(question_lower, self.complex_patterns)
        
        # Vocabulary indicator scoring
        simple_word_score = self._calculate_word_score(question_lower, self.complexity_indicators['simple_words'])
        medium_word_score = self._calculate_word_score(question_lower, self.complexity_indicators['medium_words'])
        complex_word_score = self._calculate_word_score(question_lower, self.complexity_indicators['complex_words'])
        
        # Combined scoring
        total_simple = simple_score * 0.7 + simple_word_score * 0.3
        total_medium = medium_score * 0.7 + medium_word_score * 0.3
        total_complex = complex_score * 0.7 + complex_word_score * 0.3
        
        # Special rule adjustments
        total_simple, total_medium, total_complex = self._apply_special_rules(
            question_lower, features, total_simple, total_medium, total_complex
        )
        
        # Determine complexity level
        scores = {
            ComplexityLevel.SIMPLE: total_simple,
            ComplexityLevel.MEDIUM: total_medium,
            ComplexityLevel.COMPLEX: total_complex
        }
        
        best_level = max(scores.keys(), key=lambda x: scores[x])
        confidence = scores[best_level]
        
        # If all scores are low, default to simple
        if confidence < 0.3:
            best_level = ComplexityLevel.SIMPLE
            confidence = 0.5
        
        reasoning = self._generate_reasoning(question_lower, features, scores)
        
        return ComplexityAssessment(
            level=best_level,
            confidence=min(confidence, 1.0),
            reasoning=reasoning,
            features=features
        )
    
    def _extract_features(self, question: str) -> Dict[str, Any]:
        """Extract question features"""
        features = {
            'length': len(question.split()),
            'has_when': 'when' in question,
            'has_what': 'what' in question,
            'has_would': 'would' in question,
            'has_why': 'why' in question,
            'has_how_feel': 'how' in question and 'feel' in question,
            'has_likely': 'likely' in question,
            'has_and': ' and ' in question,
            'question_words': self._count_question_words(question),
            'starts_with_when': question.startswith('when'),
            'starts_with_what': question.startswith('what'),
            'starts_with_would': question.startswith('would'),
            'ends_with_question': question.endswith('?'),
        }
        return features
    
    def _count_question_words(self, question: str) -> int:
        """Count number of question words"""
        question_words = ['what', 'when', 'where', 'who', 'why', 'how', 'which', 'would']
        return sum(1 for word in question_words if word in question)
    
    def _calculate_pattern_score(self, question: str, patterns: Dict[str, List[str]]) -> float:
        """Calculate pattern matching score"""
        total_score = 0
        match_count = 0
        
        for category, pattern_list in patterns.items():
            for pattern in pattern_list:
                if re.search(pattern, question):
                    total_score += 1.0
                    match_count += 1
        
        return total_score / max(1, len([p for sublist in patterns.values() for p in sublist]))
    
    def _calculate_word_score(self, question: str, word_weights: Dict[str, float]) -> float:
        """Calculate vocabulary indicator score"""
        total_score = 0
        for word, weight in word_weights.items():
            if word == 'how_many':
                if 'how many' in question or 'how much' in question:
                    total_score += weight
            elif word in question:
                total_score += weight
        
        return min(total_score, 1.0)
    
    def _apply_special_rules(self, question: str, features: Dict[str, Any], 
                           simple: float, medium: float, complex: float) -> tuple:
        """Apply special rules to adjust scores"""
        
        # Rule 1: "When did" questions are usually simple
        if question.startswith('when did'):
            simple += 0.3
        
        # Rule 2: Questions containing "would" are usually complex
        if 'would' in question:
            complex += 0.4
        
        # Rule 3: Questions containing "types", "kinds", "activities" etc. are usually medium complexity
        listing_words = ['types', 'kinds', 'activities', 'ways', 'fields']
        if any(word in question for word in listing_words):
            medium += 0.3
        
        # Rule 4: Very long questions may be more complex
        if features['length'] > 12:
            complex += 0.2
        elif features['length'] < 6:
            simple += 0.2
        
        # Rule 5: Emotion-related questions are complex
        emotion_words = ['feel', 'emotion', 'mood', 'happy', 'sad', 'excited']
        if any(word in question for word in emotion_words):
            complex += 0.3
        
        return simple, medium, complex
    
    def _generate_reasoning(self, question: str, features: Dict[str, Any], 
                          scores: Dict[ComplexityLevel, float]) -> str:
        """Generate reasoning explanation"""
        reasoning_parts = []
        
        if features['starts_with_when']:
            reasoning_parts.append("Time query starting with 'when'")
        if features['starts_with_what']:
            reasoning_parts.append("Fact query starting with 'what'")
        if features['starts_with_would']:
            reasoning_parts.append("Predictive query starting with 'would'")
        
        if features['has_likely']:
            reasoning_parts.append("Contains 'likely', indicates need for reasoning")
        if features['has_and']:
            reasoning_parts.append("Contains 'and', may need multi-aspect information")
        
        if features['length'] > 10:
            reasoning_parts.append("Question is long, may involve complex concepts")
        elif features['length'] < 6:
            reasoning_parts.append("Question is short, usually direct query")
        
        if not reasoning_parts:
            reasoning_parts.append("Based on general heuristic rules")
        
        best_score = max(scores.values())
        reasoning = f"Reasoning basis: {'; '.join(reasoning_parts)}. Highest score: {best_score:.2f}"
        
        return reasoning

# Test function
def test_rule_based_router():
    """Test rule-based router"""
    router = RuleBasedComplexityRouter()
    
    test_questions = [
        # Simple questions
        "When did Caroline go to the LGBTQ support group?",
        "What did Caroline research?",
        "Who is Caroline?",
        
        # Medium questions  
        "What fields would Caroline be likely to pursue in her education?",
        "What activities does Melanie partake in?",
        "Where has Melanie camped?",
        
        # Complex questions
        "Would Melanie go on another roadtrip soon?",
        "Why did Melanie choose to use colors and patterns in her pottery project?",
        "How did Melanie feel while watching the meteor shower?"
    ]
    
    print("=== Rule-based Router Test Results ===")
    for question in test_questions:
        result = router.assess_complexity(question)
        print(f"\nQuestion: {question}")
        print(f"Complexity: {result.level.value}")
        print(f"Confidence: {result.confidence:.3f}")
        print(f"Reasoning: {result.reasoning}")

if __name__ == "__main__":
    test_rule_based_router()
