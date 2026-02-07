"""
QA Question Loader

Responsible for loading and managing conv26 question data, providing question filtering and classification functions.
"""

import os
import json
from typing import List, Dict, Any, Optional
from timem.utils.logging import get_logger

logger = get_logger(__name__)


class QALoader:
    """QA question loader"""
    
    def __init__(self, data_file: Optional[str] = None):
        """
        Initialize QA loader
        
        Args:
            data_file: Data file path, if None use default path
        """
        self.data_file = data_file or "data/conv26_questions.json"
        self.qa_data = None
        self._load_data()
    
    def _load_data(self):
        """Load QA data"""
        try:
            if not os.path.exists(self.data_file):
                logger.warning(f"QA data file not found: {self.data_file}")
                self.qa_data = []
                return
            
            with open(self.data_file, 'r', encoding='utf-8') as f:
                self.qa_data = json.load(f)
            
            logger.info(f"Successfully loaded QA data: {len(self.qa_data)} records")
            
        except Exception as e:
            logger.error(f"Failed to load QA data: {str(e)}")
            self.qa_data = []
    
    def get_questions_by_categories(self, categories: List[int], limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get questions by categories
        
        Args:
            categories: Question category list
            limit: Limit number of questions returned, if None return all
            
        Returns:
            Filtered question list
        """
        if not self.qa_data:
            logger.warning("No available QA data")
            # Filter questions by specified categories
        filtered_questions = []
        for qa in self.qa_data:
            category = qa.get("category")
            if category in categories:
                filtered_questions.append(qa)
        
        # Apply count limit
        if limit is not None:
            filtered_questions = filtered_questions[:limit]
        
        logger.info(f"Filtered {len(filtered_questions)} questions by categories {categories}")
        return filtered_questions
    
    def get_conv26_questions_for_testing(self, categories: List[int] = [1, 2, 3, 4], limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get conv26 questions for testing
        
        Args:
            categories: Question category list, default includes categories 1-4
            limit: Limit number of questions returned, if None return all questions
            
        Returns:
            Formatted test case list
        """
        # Get filtered questions
        questions = self.get_questions_by_categories(categories, limit)
        
        # Convert to test case format
        test_cases = []
        for i, qa in enumerate(questions, 1):
            test_case = {
                "question": qa["question"],
                "expected_answer": str(qa["answer"]),  # Ensure answer is string
                "category": qa["category"],
                "evidence": qa.get("evidence", []),
                "question_id": f"Q{i}"
            }
            test_cases.append(test_case)
        
        # Print statistics
        self._print_question_statistics(questions, test_cases)
        
        return test_cases
    
    def _print_question_statistics(self, questions: List[Dict[str, Any]], test_cases: List[Dict[str, Any]]):
        """Print question statistics"""
        print(f"\ud83d\udcda Successfully loaded {len(test_cases)} conv-26 questions (categories 1-4)")
        
        # Count category distribution
        category_counts = {}
        for qa in questions:
            cat = qa.get("category", 0)
            category_counts[cat] = category_counts.get(cat, 0) + 1
        
        print(f"\ud83d\udcc8 Category distribution:")
        for cat in sorted(category_counts.keys()):
            print(f"   Category {cat}: {category_counts[cat]} questions")
        
        # Display specific question information
        print(f"\n\ud83d\udccf Test question details:")
        for i, qa in enumerate(questions, 1):
            print(f"   {i}. [{qa.get('category', 'N/A')}] {qa['question'][:60]}...")
    
    def get_category_meanings(self) -> Dict[int, str]:
        """Get category meaning explanations"""
        return {
            1: "Entity recognition",
            2: "Time recognition", 
            3: "Reasoning and judgment",
            4: "Open domain QA",
            5: "Adversarial QA"
        }
    
    def reload_data(self):
        """Reload data"""
        logger.info("Reloading QA data")
        self._load_data()
    
    def get_total_question_count(self) -> int:
        """Get total question count"""
        return len(self.qa_data) if self.qa_data else 0
    
    def get_questions_by_category(self, category: int) -> List[Dict[str, Any]]:
        """Get all questions of specified category"""
        if not self.qa_data:
            return []
        
        return [qa for qa in self.qa_data if qa.get("category") == category]


# Global QA loader instance
_qa_loader = None


def get_qa_loader(data_file: Optional[str] = None) -> QALoader:
    """
    Get QA loader instance
    
    Args:
        data_file: Data file path, if None use default path
        
    Returns:
        QA loader instance
    """
    global _qa_loader
    
    if _qa_loader is None:
        _qa_loader = QALoader(data_file)
    
    return _qa_loader


def load_conv26_questions_for_testing(categories: List[int] = [1, 2, 3, 4], limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Convenience function to load conv26 questions for testing
    
    Args:
        categories: Question category list, default includes categories 1-4
        limit: Limit number of questions returned, if None return all questions
        
    Returns:
        Formatted test case list
    """
    loader = get_qa_loader()
    return loader.get_conv26_questions_for_testing(categories, limit)
