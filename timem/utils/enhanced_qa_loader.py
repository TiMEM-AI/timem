"""
TiMem Enhanced QA Question Loader
Supports loading questions from locomo10_qa_001.json and integrating conversation and user group information
"""

import os
import json
import asyncio
from typing import List, Dict, Any, Optional, Set
from pathlib import Path

from timem.utils.logging import get_logger
from timem.utils.conversation_loader import get_conversation_loader
from timem.utils.character_id_resolver import get_character_id_resolver, UserGroup


class EnhancedQALoader:
    """Enhanced QA question loader"""
    
    def __init__(self, data_file: Optional[str] = None):
        """
        Initialize enhanced QA loader
        
        Args:
            data_file: Data file path, if None use default path
        """
        self.data_file = data_file or "data/locomo10_smart_split/locomo10_qa_001.json"
        self.qa_data = None
        self.conversation_loader = get_conversation_loader()
        self.character_resolver = get_character_id_resolver()
        self.logger = get_logger(__name__)
        self._user_groups_cache: Dict[str, UserGroup] = {}
        
        # Load data
        self._load_data()
    
    def _load_data(self):
        """Load QA data"""
        try:
            if not os.path.exists(self.data_file):
                self.logger.warning(f"QA data file does not exist: {self.data_file}")
                self.qa_data = []
                return
            
            with open(self.data_file, 'r', encoding='utf-8') as f:
                self.qa_data = json.load(f)
            
            self.logger.info(f"Successfully loaded QA data: {len(self.qa_data)} records")
            
        except Exception as e:
            self.logger.error(f"Failed to load QA data: {str(e)}")
            self.qa_data = []
    
    async def _resolve_user_groups(self, conversations: Set[str]) -> Dict[str, UserGroup]:
        """Resolve user group information
        
        Args:
            conversations: Set of conversation IDs to resolve
            
        Returns:
            Mapping from conversation ID to user group
        """
        # Load all conversation information
        conv_info_dict = {}
        for conv_id in conversations:
            conv_info = self.conversation_loader.load_conversation_data(conv_id)
            if conv_info:
                conv_info_dict[conv_id] = conv_info
        
        # Batch resolve user groups
        user_groups = await self.character_resolver.resolve_multiple_user_groups(conv_info_dict)
        
        # Update cache
        self._user_groups_cache.update(user_groups)
        
        return user_groups
    
    async def get_enhanced_test_cases(self, 
                                    categories: List[int] = [1, 2, 3, 4], 
                                    limit: Optional[int] = None,
                                    conversation_filter: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Get enhanced test cases with conversation and user group information
        
        Args:
            categories: List of question categories, default includes categories 1-4
            limit: Limit number of questions returned, if None return all questions
            conversation_filter: Conversation filter, only include specified conversations
            
        Returns:
            List of enhanced test cases
        """
        if not self.qa_data:
            self.logger.warning("No available QA data")
            return []
        
        # Filter questions
        filtered_questions = []
        conversations_needed = set()
        
        for qa_item in self.qa_data:
            qa = qa_item.get("qa", {})
            source_record = qa_item.get("source_record", "")
            
            # Check category filter
            category = qa.get("category")
            if category not in categories:
                continue
            
            # Check conversation filter
            if conversation_filter and source_record not in conversation_filter:
                continue
            
            # Collect required conversations
            if source_record:
                conversations_needed.add(source_record)
            
            filtered_questions.append(qa_item)
        
        # Apply count limit
        if limit is not None:
            filtered_questions = filtered_questions[:limit]
        
        # Resolve user group information
        user_groups = await self._resolve_user_groups(conversations_needed)
        
        # Build enhanced test cases
        enhanced_test_cases = []
        for i, qa_item in enumerate(filtered_questions, 1):
            qa = qa_item.get("qa", {})
            source_record = qa_item.get("source_record", "")
            
            # Get user group information
            user_group = user_groups.get(source_record)
            
            test_case = {
                "question": qa["question"],
                "expected_answer": str(qa["answer"]),  # Ensure answer is string
                "category": qa["category"],
                "evidence": qa.get("evidence", []),
                "question_id": f"Q{i}",
                "source_record": source_record,
                "user_group": user_group,
                "user_group_ids": list(user_group.user_group_ids) if user_group else [],
                "speaker_a": user_group.speaker_a if user_group else None,
                "speaker_b": user_group.speaker_b if user_group else None,
                "speaker_a_id": user_group.speaker_a_id if user_group else None,
                "speaker_b_id": user_group.speaker_b_id if user_group else None
            }
            enhanced_test_cases.append(test_case)
        
        # Print statistics
        await self._print_enhanced_statistics(filtered_questions, enhanced_test_cases, user_groups)
        
        return enhanced_test_cases
    
    async def _print_enhanced_statistics(self, 
                                       questions: List[Dict[str, Any]], 
                                       test_cases: List[Dict[str, Any]], 
                                       user_groups: Dict[str, UserGroup]):
        """Print enhanced statistics"""
        print(f"📚 Successfully loaded {len(test_cases)} enhanced test cases")
        
        # Count category distribution
        category_counts = {}
        conversation_counts = {}
        
        for test_case in test_cases:
            # Category statistics
            cat = test_case.get("category", 0)
            category_counts[cat] = category_counts.get(cat, 0) + 1
            
            # Conversation statistics
            conv = test_case.get("source_record", "unknown")
            conversation_counts[conv] = conversation_counts.get(conv, 0) + 1
        
        print(f"📊 Category distribution:")
        for cat in sorted(category_counts.keys()):
            print(f"   Category {cat}: {category_counts[cat]} questions")
        
        print(f"📊 Conversation distribution:")
        for conv in sorted(conversation_counts.keys()):
            user_group = user_groups.get(conv)
            speakers_info = f"({user_group.speaker_a} & {user_group.speaker_b})" if user_group else "(Unknown)"
            print(f"   {conv}: {conversation_counts[conv]} questions {speakers_info}")
        
        print(f"👥 User group information:")
        for conv_id, user_group in user_groups.items():
            print(f"   {conv_id}: {user_group.speaker_a}({user_group.speaker_a_id}) & {user_group.speaker_b}({user_group.speaker_b_id})")
        
        # Display specific question information
        print(f"\n📝 Test question details:")
        for i, test_case in enumerate(test_cases, 1):
            conv_info = f"[{test_case.get('source_record', 'N/A')}]" if test_case.get('source_record') else ""
            print(f"   {i}. [{test_case.get('category', 'N/A')}] {conv_info} {test_case['question'][:50]}...")
    
    def get_user_group_filter_conditions(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        """Get user group filter conditions for test case
        
        Args:
            test_case: Test case
            
        Returns:
            Filter condition dictionary
        """
        user_group = test_case.get("user_group")
        if not user_group:
            return {}
        
        return self.character_resolver.get_user_group_filter_conditions(user_group)
    
    def get_conversation_speakers(self, conversation_id: str) -> Optional[tuple]:
        """Get speaker information for specified conversation
        
        Args:
            conversation_id: Conversation ID
            
        Returns:
            (speaker_a, speaker_b) tuple, returns None if failed
        """
        return self.conversation_loader.get_conversation_speakers(conversation_id)
    
    def reload_data(self):
        """Reload data"""
        self.logger.info("Reloading QA data")
        self._load_data()
        # Clear cache
        self._user_groups_cache.clear()
    
    def get_total_question_count(self) -> int:
        """Get total question count"""
        return len(self.qa_data) if self.qa_data else 0
    
    def get_questions_by_category(self, category: int) -> List[Dict[str, Any]]:
        """Get all questions for specified category"""
        if not self.qa_data:
            return []
        
        return [qa_item for qa_item in self.qa_data if qa_item.get("qa", {}).get("category") == category]
    
    def get_questions_by_conversation(self, conversation_id: str) -> List[Dict[str, Any]]:
        """Get all questions for specified conversation"""
        if not self.qa_data:
            return []
        
        return [qa_item for qa_item in self.qa_data if qa_item.get("source_record") == conversation_id]


# Global enhanced QA loader instance
_enhanced_qa_loader = None


def get_enhanced_qa_loader(data_file: Optional[str] = None) -> EnhancedQALoader:
    """
    Get enhanced QA loader instance
    
    Args:
        data_file: Data file path, if None use default path
        
    Returns:
        Enhanced QA loader instance
    """
    global _enhanced_qa_loader
    
    if _enhanced_qa_loader is None:
        _enhanced_qa_loader = EnhancedQALoader(data_file)
    
    return _enhanced_qa_loader


async def load_enhanced_conv26_questions_for_testing(categories: List[int] = [1, 2, 3, 4], 
                                                   limit: Optional[int] = None,
                                                   conversation_filter: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Convenience function to load enhanced conv26 questions for testing
    
    Args:
        categories: List of question categories, default includes categories 1-4
        limit: Limit number of questions returned, if None return all questions
        conversation_filter: Conversation filter, only include specified conversations
        
    Returns:
        List of enhanced test cases
    """
    loader = get_enhanced_qa_loader()
    return await loader.get_enhanced_test_cases(categories, limit, conversation_filter)
