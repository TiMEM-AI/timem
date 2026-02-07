"""
TiMem retrieval utility module - [Bottom-Up] retrieval core algorithm

Provides core algorithms such as session scoring and temporal association extraction,
supporting temporal hierarchy tracing retrieval strategy based on L1 memory scoring.

Complies with engineering design specifications:
1. Single responsibility: each function focuses on one functionality
2. Low coupling: decoupled from storage layer, called through interface
3. High cohesion: related functions aggregated in one module
4. Testable: pure function design, easy for unit testing
"""

import re
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Union
from collections import defaultdict
import calendar

from timem.utils.logging import get_logger

logger = get_logger(__name__)


class SessionScorer:
    """Session scorer - calculate session importance based on L1 memory scoring"""
    
    def __init__(self):
        self.logger = get_logger(__name__)
    
    def calculate_session_scores(self, l1_memories: List[Dict[str, Any]]) -> List[Tuple[str, float]]:
        """
        Calculate importance of each session based on L1 memory scoring
        
        Args:
            l1_memories: List of L1 memories, each memory contains fused_score and session information
            
        Returns:
            List of sessions sorted by score [(session_id, total_score), ...]
        """
        if not l1_memories:
            self.logger.warning("L1 memory list is empty, unable to calculate session scores")
            return []
        
        session_scores = defaultdict(float)
        processed_memories = 0
        
        for memory in l1_memories:
            try:
                # Extract session_id
                session_id = self._extract_session_id(memory)
                if session_id == 'unknown_session':
                    continue
                
                # Get memory score
                score = self._get_memory_score(memory)
                session_scores[session_id] += score
                processed_memories += 1
                
            except Exception as e:
                self.logger.warning(f"Error processing memory: {e}, skipping this memory")
                continue
        
        # Convert to sorted list
        sorted_sessions = sorted(
            session_scores.items(), 
            key=lambda x: x[1], 
            reverse=True
        )
        
        self.logger.info(f"Session scoring completed: processed {processed_memories} memories, "
                        f"found {len(sorted_sessions)} sessions")
        
        if sorted_sessions:
            best_session, best_score = sorted_sessions[0]
            self.logger.info(f"Highest scoring session: {best_session} (score: {best_score:.3f})")
        
        return sorted_sessions
    
    def extract_temporal_info_from_session_id(self, session_id: str) -> Dict[str, Any]:
        """
        Extract temporal information from session_id
        
        Args:
            session_id: Session identifier, supports multiple formats:
                       - "session_N" (simple format, use current time)
                       - "conv-26_session_N" (conversation format, use current time) 
                       - "session_YYYYMMDD_XXX" (complete format, extract actual date)
            
        Returns:
            Dictionary containing date, week, month information
        """
        try:
            # First try to extract complete date format
            date_match = re.search(r'session_(\d{8})', session_id)
            if date_match:
                date_str = date_match.group(1)  # "20241201"
                date_obj = datetime.strptime(date_str, '%Y%m%d')
            else:
                # If simple format (session_N or conv-26_session_N), use current time
                self.logger.warning(f"Unable to parse temporal information from session_id: {session_id}, using current time")
                date_obj = datetime.now()
                date_str = date_obj.strftime('%Y%m%d')
            
            # Calculate week start date (Monday of this week)
            week_start = date_obj - timedelta(days=date_obj.weekday())
            
            # Calculate month start date (first day of this month)
            month_start = date_obj.replace(day=1)
            
            return {
                "date": date_str,
                "week_start": week_start.strftime('%Y%m%d'),
                "month_start": month_start.strftime('%Y%m%d'),
            }
            
        except Exception as e:
            self.logger.error(f"Failed to extract temporal information {session_id}: {e}")
            return {}
    
    def _extract_session_id(self, memory: Dict[str, Any]) -> str:
        """
        Extract session_id from memory
        
        Supports multiple extraction methods:
        1. Get directly from session_id field
        2. Parse session information from title
        3. Extract from other metadata
        """
        # Method 1: Get directly from field
        if 'session_id' in memory and memory['session_id']:
            return str(memory['session_id'])
        
        # Method 2: Parse from title
        title = memory.get('title', '')
        if 'session_' in title:
            # Match format: "session_20241201_001 user_expert discussion"
            session_match = re.search(r'session_\d{8}_\d{3}', title)
            if session_match:
                return session_match.group(0)
            
            # Match other possible session formats
            session_match = re.search(r'session_[a-zA-Z0-9_]+', title)
            if session_match:
                return session_match.group(0)
        
        # Method 3: Look for session clues in content
        content = memory.get('content', '')
        if 'session' in content.lower():
            session_match = re.search(r'session[_\s]*([a-zA-Z0-9_]+)', content, re.IGNORECASE)
            if session_match:
                return f"session_{session_match.group(1)}"
        
        # Default return
        return 'unknown_session'
    
    def _get_memory_score(self, memory: Dict[str, Any]) -> float:
        """
        Get memory score
        
        Priority: fused_score > semantic_score > keyword_score > default value
        """
        score_fields = ['fused_score', 'semantic_score', 'keyword_score', 'bm25_score']
        
        for field in score_fields:
            if field in memory and memory[field] is not None:
                return float(memory[field])
        
        # If no score field, give base score based on memory quality features
        base_score = 0.5
        
        # Adjust score based on content length (longer content may be more important)
        content = memory.get('content', '')
        if len(content) > 200:
            base_score += 0.2
        elif len(content) > 100:
            base_score += 0.1
        
        # Adjust score based on title quality
        title = memory.get('title', '')
        if len(title) > 50:
            base_score += 0.1
        
        return base_score


class TemporalInfoExtractor:
    """Temporal information extractor - extract temporal hierarchy information from session_id"""
    
    def __init__(self):
        self.logger = get_logger(__name__)
    
    def extract_temporal_info(self, session_id: str) -> Dict[str, Any]:
        """
        Extract temporal information from session_id
        
        Args:
            session_id: Session ID, expected format: "session_20241201_001"
            
        Returns:
            Dictionary containing temporal information with date, week, month, etc.
        """
        try:
            # Standard format parsing: session_YYYYMMDD_sequence
            if re.match(r'session_\d{8}_\d{3}', session_id):
                date_part = session_id.split('_')[1]  # "20241201"
                return self._parse_date_string(date_part)
            
            # Try other possible temporal formats
            # Format: session_2024-12-01_001
            date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', session_id)
            if date_match:
                year, month, day = date_match.groups()
                date_str = f"{year}{month}{day}"
                return self._parse_date_string(date_str)
            
            # Format: session_20241201
            date_match = re.search(r'(\d{8})', session_id)
            if date_match:
                date_str = date_match.group(1)
                return self._parse_date_string(date_str)
            
            # If unable to parse, return current temporal information
            self.logger.warning(f"Unable to parse temporal information from session_id: {session_id}, using current time")
            return self._get_current_temporal_info()
            
        except Exception as e:
            self.logger.error(f"Failed to extract temporal information: {e}")
            return self._get_current_temporal_info()
    
    def _parse_date_string(self, date_str: str) -> Dict[str, Any]:
        """
        Parse date string and calculate related temporal information
        
        Args:
            date_str: Date string in format YYYYMMDD
        """
        try:
            # Parse date
            year = int(date_str[:4])
            month = int(date_str[4:6])
            day = int(date_str[6:8])
            
            session_date = datetime(year, month, day)
            
            # Calculate week information
            iso_year, iso_week, _ = session_date.isocalendar()
            week_id = f"{iso_year}W{iso_week:02d}"
            
            # Calculate week start date (Monday)
            week_start = session_date - timedelta(days=session_date.weekday())
            
            # Calculate month information
            month_id = f"{year}{month:02d}"
            month_start = datetime(year, month, 1)
            
            # Build temporal information
            temporal_info = {
                'date': date_str,
                'date_obj': session_date,
                'week': week_id,
                'week_start': week_start,
                'month': month_id,
                'month_start': month_start,
                'year': year,
                'month_num': month,
                'day': day
            }
            
            self.logger.debug(f"Parse temporal information: {session_date.strftime('%Y-%m-%d')} -> "
                            f"week {week_id}, month {month_id}")
            
            return temporal_info
            
        except Exception as e:
            self.logger.error(f"Failed to parse date string: {e}")
            return self._get_current_temporal_info()
    
    def _get_current_temporal_info(self) -> Dict[str, Any]:
        """Get current temporal information as default value"""
        now = datetime.now()
        date_str = now.strftime('%Y%m%d')
        return self._parse_date_string(date_str)


class BottomUpRetrieverUtils:
    """[Bottom-Up] retrieval utility class - integrate core algorithms"""
    
    def __init__(self):
        self.session_scorer = SessionScorer()
        self.temporal_extractor = TemporalInfoExtractor()
        self.logger = get_logger(__name__)
    
    def analyze_l1_memories_for_session(self, l1_memories: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze L1 memories to determine best session and temporal information
        
        Args:
            l1_memories: List of L1 memories
            
        Returns:
            Analysis result containing best session, temporal information, scoring details, etc.
        """
        try:
            # Step 1: Calculate session scores
            session_scores = self.session_scorer.calculate_session_scores(l1_memories)
            
            if not session_scores:
                self.logger.warning("No valid session found, returning empty result")
                return self._create_empty_result()
            
            # Step 2: Get best session and temporal information
            best_session_id, best_score = session_scores[0]
            temporal_info = self.temporal_extractor.extract_temporal_info(best_session_id)
            
            # Step 3: Statistical information
            session_distribution = self._analyze_session_distribution(l1_memories, session_scores)
            
            # Build result
            result = {
                'best_session_id': best_session_id,
                'best_session_score': best_score,
                'temporal_info': temporal_info,
                'session_scores': session_scores[:5],  # Keep only top 5
                'session_distribution': session_distribution,
                'total_sessions': len(session_scores),
                'processed_memories': len(l1_memories)
            }
            
            self.logger.info(f"L1 memory analysis completed: best_session={best_session_id}, "
                           f"score={best_score:.3f}, involving {len(session_scores)} sessions")
            
            return result
            
        except Exception as e:
            self.logger.error(f"L1 memory analysis failed: {e}")
            return self._create_empty_result()
    
    def _analyze_session_distribution(self, l1_memories: List[Dict[str, Any]], 
                                    session_scores: List[Tuple[str, float]]) -> Dict[str, Any]:
        """Analyze session distribution"""
        session_memory_count = defaultdict(int)
        
        for memory in l1_memories:
            session_id = self.session_scorer._extract_session_id(memory)
            if session_id != 'unknown_session':
                session_memory_count[session_id] += 1
        
        # Build distribution statistics
        distribution = {
            'session_memory_counts': dict(session_memory_count),
            'top_session_coverage': 0.0,
            'concentration_ratio': 0.0
        }
        
        if session_scores and len(l1_memories) > 0:
            top_session_id = session_scores[0][0]
            top_count = session_memory_count.get(top_session_id, 0)
            distribution['top_session_coverage'] = top_count / len(l1_memories)
            
            # Calculate concentration (ratio of top 3 sessions to total memories)
            top3_count = sum(session_memory_count.get(session_id, 0) 
                           for session_id, _ in session_scores[:3])
            distribution['concentration_ratio'] = top3_count / len(l1_memories)
        
        return distribution
    
    def _create_empty_result(self) -> Dict[str, Any]:
        """Create empty analysis result"""
        return {
            'best_session_id': None,
            'best_session_score': 0.0,
            'temporal_info': {},
            'session_scores': [],
            'session_distribution': {},
            'total_sessions': 0,
            'processed_memories': 0
        }


# Convenient function interface
def analyze_l1_memories_for_bottom_up_retrieval(l1_memories: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Convenient function: analyze L1 memories to prepare session and temporal information for [Bottom-Up] retrieval
    
    Args:
        l1_memories: List of L1 memories
        
    Returns:
        Analysis result containing best session and temporal information
    """
    utils = BottomUpRetrieverUtils()
    return utils.analyze_l1_memories_for_session(l1_memories)


def extract_session_temporal_info(session_id: str) -> Dict[str, Any]:
    """
    Convenient function: extract temporal information from session_id
    
    Args:
        session_id: Session ID
        
    Returns:
        Dictionary containing temporal information
    """
    extractor = TemporalInfoExtractor()
    return extractor.extract_temporal_info(session_id)
