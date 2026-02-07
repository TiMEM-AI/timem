"""
Retrieval planning node.

This node analyzes the user query and extracts structured signals (e.g., query category,
temporal entities, keywords, and intent). The output is used by downstream components
to select appropriate retrieval strategies.
"""

import re
from typing import Dict, List, Any, Optional

from timem.workflows.retrieval_state import RetrievalState, RetrievalStateValidator, QueryCategory
from timem.utils.logging import get_logger

logger = get_logger(__name__)


class RetrievalPlanner:
    """Retrieval planning node."""
    
    def __init__(self, state_validator: Optional[RetrievalStateValidator] = None):
        """
        Initialize retrieval planner
        
        Args:
            state_validator: State validator, create new instance if None
        """
        self.state_validator = state_validator or RetrievalStateValidator()
        self.logger = get_logger(__name__)
        
        # Predefined keyword patterns
        self.temporal_keywords = {
            "en": ["when", "what time", "date", "year", "month", "day", "ago", "before", "after", "during", "since"],
            "zh": ["What time", "Time", "Year", "Month", "Day", "Before", "After", "During", "Since"]
        }
        
        self.factual_keywords = {
            "en": ["what", "who", "where", "which", "how many", "is", "are", "did", "does"],
            "zh": ["What", "Who", "Where", "Which", "How many", "Is", "Are", "Did", "Does"]
        }
        
        self.inferential_keywords = {
            "en": ["why", "how", "would", "could", "should", "likely", "probably", "might"],
            "zh": ["Why", "How", "Would", "Could", "Should", "Likely", "Probably", "Might"]
        }
        
        # Time entity patterns
        self.time_patterns = [
            r'\b\d{4}\b',  # Year
            r'\b\d{1,2}/\d{1,2}/\d{4}\b',  # Date MM/DD/YYYY
            r'\b\d{4}-\d{1,2}-\d{1,2}\b',  # Date YYYY-MM-DD
            r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b',
            r'\b\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b',
            r'\b(Today|Yesterday|Tomorrow|Last week|Next week|Last month|Next month|Last year|Next year)\b',  # English time expressions
            r'\b(\u4eca\u5929|\u6628\u5929|\u660e\u5929|\u524d\u4e00\u5468|\u4e0b\u4e00\u5468|\u524d\u4e00\u6708|\u4e0b\u4e00\u6708|\u524d\u4e00\u5e74|\u4e0b\u4e00\u5e74)\b'  # Chinese time expressions
        ]
        
        # Stop words
        self.stop_words = {
            "en": {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by", 
                   "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does", 
                   "did", "will", "would", "could", "should", "may", "might", "must", "can"},
            "zh": {"\u7684", "\u4e86", "\u5728", "\u662f", "\u6211", "\u4f60", "\u4ed6", "\u5f53", "\u4eec", "\u8fd9", "\u9f99", "\u6709", "\u6ca1", "\u4e0d", 
                   "\u4e5f", "\u90fd", "\u5f88", "\u5c31", "\u8fd9", "\u662f", "\u4e00", "\u4e2a", "\u4e24", "\u4e09", "\u56db", "\u4e94", "\u4e03", "\u516d", "\u4e5d", "\u4e00", "\u4e2a", "\u4e24", "\u4e09", "\u56db", "\u4e94", "\u4e03", "\u516d", "\u4e5d"}
        }
    
    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run retrieval planning
        
        Args:
            state: Workflow state dictionary
            
        Returns:
            Updated state dictionary
        """
        try:
            # Convert to RetrievalState object
            retrieval_state = self._dict_to_state(state)
            
            self.logger.info(f"Start retrieval planning: {retrieval_state.question}")
            
            # Step 1: Categorize query
            retrieval_state.query_category = await self._categorize_query(retrieval_state.question)
            
            # Step 2: Extract time entities
            retrieval_state.time_entities = await self._extract_time_entities(retrieval_state.question)
            
            # Step 3: Extract key entities
            retrieval_state.key_entities = await self._extract_key_entities(retrieval_state.question)
            
            # Step 4: Analyze query intent
            retrieval_state.query_intent = await self._analyze_intent(retrieval_state.question)
            
            # Step 5: Validate analysis results
            warnings = self.state_validator.validate_query_analysis(retrieval_state)
            retrieval_state.warnings.extend(warnings)
            
            self.logger.info(
                f"Retrieval planning complete: category={retrieval_state.query_category.name if retrieval_state.query_category else 'Unknown'}, "
                f"time_entities={len(retrieval_state.time_entities)}, key_entities={len(retrieval_state.key_entities)}"
            )
            
            return self._state_to_dict(retrieval_state)
            
        except Exception as e:
            error_msg = f"Retrieval planning failed: {str(e)}"
            self.logger.error(error_msg)
            state["errors"] = state.get("errors", []) + [error_msg]
            return state
    
    async def _categorize_query(self, question: str) -> QueryCategory:
        """Categorize user query"""
        question_lower = question.lower()
        
        # Detect language
        is_chinese = bool(re.search(r'[\u4e00-\u9fff]', question))
        lang = "zh" if is_chinese else "en"
        
        # Temporal query detection
        temporal_keywords = self.temporal_keywords[lang]
        if any(keyword in question_lower for keyword in temporal_keywords):
            return QueryCategory.TEMPORAL
        
        # Factual query detection
        factual_keywords = self.factual_keywords[lang]
        if any(keyword in question_lower for keyword in factual_keywords):
            return QueryCategory.FACTUAL
        
        # Inferential query detection
        inferential_keywords = self.inferential_keywords[lang]
        if any(keyword in question_lower for keyword in inferential_keywords):
            return QueryCategory.INFERENTIAL
        
        # Default to detailed information query
        return QueryCategory.DETAILED
    
    async def _extract_time_entities(self, question: str) -> List[Dict[str, Any]]:
        """Extract time entities"""
        time_entities = []
        
        for pattern in self.time_patterns:
            matches = re.finditer(pattern, question, re.IGNORECASE)
            for match in matches:
                time_entities.append({
                    "text": match.group(),
                    "start": match.start(),
                    "end": match.end(),
                    "type": "temporal",
                    "pattern": pattern
                })
        
        # Deduplicate and sort by position
        unique_entities = []
        seen_spans = set()
        
        for entity in time_entities:
            span = (entity["start"], entity["end"])
            if span not in seen_spans:
                seen_spans.add(span)
                unique_entities.append(entity)
        
        unique_entities.sort(key=lambda x: x["start"])
        
        self.logger.info(f"Extracted {len(unique_entities)} time entities")
        return unique_entities
    
    async def _extract_key_entities(self, question: str) -> List[str]:
        """Extract key entities"""
        # Detect language
        is_chinese = bool(re.search(r'[\u4e00-\u9fff]', question))
        lang = "zh" if is_chinese else "en"
        stop_words = self.stop_words[lang]
        
        # Basic keyword extraction
        if is_chinese:
            # Chinese processing: simple character-based splitting
            words = []
            # Extract mixed Chinese-English vocabulary
            word_pattern = r'[\u4e00-\u9fff]+|[a-zA-Z]+\w*'
            matches = re.findall(word_pattern, question)
            words.extend(matches)
        else:
            # English processing: split by word boundaries
            words = re.findall(r'\b\w+\b', question.lower())
        
        # Filter stop words and short words
        key_entities = []
        for word in words:
            word_clean = word.strip().lower()
            if (len(word_clean) > 2 and 
                word_clean not in stop_words and 
                word_clean not in key_entities):
                key_entities.append(word_clean)
        
        # Limit keyword count
        key_entities = key_entities[:15]
        
        self.logger.info(f"Extracted {len(key_entities)} key entities")
        return key_entities
    
    async def _analyze_intent(self, question: str) -> str:
        """Analyze query intent"""
        question_lower = question.lower()
        
        # Detect language
        is_chinese = bool(re.search(r'[\u4e00-\u9fff]', question))
        
        if is_chinese:
            # Chinese intent analysis
            if any(word in question_lower for word in ["\u4ec0\u4e48\u6642\u524d", "\u4ec0\u4e48\u65f6\u95f4", "\u6642\u95f4"]):
                return "temporal_query"
            elif any(word in question_lower for word in ["\u4ec0\u4e48", "\u8fd9\u4e2a", "\u8fd9\u4e9b"]):
                return "factual_query"
            elif any(word in question_lower for word in ["\u8c01\u4eba", "\u8fd9\u4eba"]):
                return "entity_query"
            elif any(word in question_lower for word in ["\u5728\u5f53\u4e0a", "\u5728\u8fd9\u91cc"]):
                return "location_query"
            elif any(word in question_lower for word in ["\u4ec0\u4e48\u4e0d", "\u6c42\u4e0d", "\u4ec0\u4e48\u65b9\u5f0f"]):
                return "causal_query"
            else:
                return "general_query"
        else:
            # English intent analysis
            if "when" in question_lower:
                return "temporal_query"
            elif "what" in question_lower:
                return "factual_query"
            elif "who" in question_lower:
                return "entity_query"
            elif "where" in question_lower:
                return "location_query"
            elif any(word in question_lower for word in ["why", "how"]):
                return "causal_query"
            else:
                return "general_query"
    
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
            if key == 'query_category' and value:
                state_dict[key] = value  # Keep enum object
            else:
                state_dict[key] = value
                
        return state_dict