"""
Memory Time Sorter
Responsible for sorting child and historical memories by time to ensure correct logical order during memory generation.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from timem.utils.logging import get_logger
from timem.utils.time_manager import TimeManager
from timem.utils.time_formatter import get_time_formatter

logger = get_logger(__name__)

class MemoryTimeSorter:
    """
    Memory time sorter that ensures memories are arranged in correct time order
    """
    
    def __init__(self, time_manager: Optional[TimeManager] = None):
        self.time_manager = time_manager or TimeManager()
        self.time_formatter = get_time_formatter()
    
    def sort_child_memories(self, child_memories: List[Dict[str, Any]], 
                           sort_order: str = "asc") -> List[Dict[str, Any]]:
        """
        Sort child memories by time
        
        Args:
            child_memories: List of child memories
            sort_order: Sort order, "asc" for ascending (far to near), "desc" for descending (near to far)
            
        Returns:
            Sorted list of child memories
        """
        if not child_memories:
            return []
        
        logger.info(f"🔍 [MemoryTimeSorter] Starting to sort {len(child_memories)} child memories by time")
        
        # Extract time information and sort
        memories_with_time = []
        for memory in child_memories:
            if isinstance(memory, dict):
                content = memory.get('content', '')
                created_at = memory.get('created_at')
                memory_id = memory.get('id', 'unknown')
            else:
                content = getattr(memory, 'content', '')
                created_at = getattr(memory, 'created_at', None)
                memory_id = getattr(memory, 'id', 'unknown')
            
            # Parse time
            parsed_time = None
            if created_at:
                try:
                    if isinstance(created_at, str):
                        parsed_time = self.time_manager.parse_iso_time(created_at)
                    elif isinstance(created_at, datetime):
                        parsed_time = created_at
                except Exception as e:
                    logger.warning(f"⚠️ [MemoryTimeSorter] Failed to parse time: {created_at}, error: {e}")
                    parsed_time = None
            
            memories_with_time.append({
                'memory': memory,
                'content': content,
                'created_at': created_at,
                'parsed_time': parsed_time,
                'memory_id': memory_id
            })
        
        # Sort by time
        # Memories with time sorted by time, memories without time placed at the end
        try:
            memories_with_time.sort(key=lambda x: (
                x['parsed_time'] is None,  # Memories without time placed at the end
                x['parsed_time'] or datetime.min  # Memories with time sorted by time
            ))
            
            # Adjust order based on sort_order
            if sort_order == "desc":
                memories_with_time.reverse()
            
            # Record sorted memories
            sorted_memories = [item['memory'] for item in memories_with_time]
            
            # Record sorting details
            time_info = []
            for item in memories_with_time[:5]:  # Only record time info for first 5
                time_str = item['created_at'] if item['created_at'] else "No time"
                time_info.append(f"{item['memory_id']}: {time_str}")
            
            logger.info(f"✅ [MemoryTimeSorter] Child memory sorting completed, order: {sort_order}")
            logger.info(f"📅 [MemoryTimeSorter] First 5 memories time: {' | '.join(time_info)}")
            
            return sorted_memories
            
        except Exception as e:
            logger.error(f"❌ [MemoryTimeSorter] Child memory sorting failed: {e}")
            # Return original order on sorting failure
            return child_memories
    
    def sort_historical_memories(self, historical_memories: List[Dict[str, Any]], 
                                limit: int = 3, sort_order: str = "desc") -> List[Dict[str, Any]]:
        """
        Sort and limit historical memories by time
        
        Args:
            historical_memories: List of historical memories
            limit: Limit count
            sort_order: Sort order, "desc" for descending (newest first), "asc" for ascending (oldest first)
            
        Returns:
            Sorted and limited list of historical memories
        """
        if not historical_memories:
            return []
        
        logger.info(f"🔍 [MemoryTimeSorter] Starting to sort {len(historical_memories)} historical memories by time")
        
        # Extract time information and sort
        memories_with_time = []
        for memory in historical_memories:
            if isinstance(memory, dict):
                content = memory.get('content', '')
                created_at = memory.get('created_at')
                memory_id = memory.get('id', 'unknown')
            else:
                content = getattr(memory, 'content', '')
                created_at = getattr(memory, 'created_at', None)
                memory_id = getattr(memory, 'id', 'unknown')
            
            # Parse time
            parsed_time = None
            if created_at:
                try:
                    if isinstance(created_at, str):
                        parsed_time = self.time_manager.parse_iso_time(created_at)
                    elif isinstance(created_at, datetime):
                        parsed_time = created_at
                except Exception as e:
                    logger.warning(f"⚠️ [MemoryTimeSorter] Failed to parse historical memory time: {created_at}, error: {e}")
                    parsed_time = None
            
            memories_with_time.append({
                'memory': memory,
                'content': content,
                'created_at': created_at,
                'parsed_time': parsed_time,
                'memory_id': memory_id
            })
        
        # Sort by time
        # Memories with time sorted by time, memories without time placed at the end
        try:
            memories_with_time.sort(key=lambda x: (
                x['parsed_time'] is None,  # Memories without time placed at the end
                x['parsed_time'] or datetime.min  # Memories with time sorted by time
            ))
            
            # Adjust order based on sort_order
            if sort_order == "desc":
                memories_with_time.reverse()
            
            # Limit count
            limited_memories = memories_with_time[:limit]
            sorted_memories = [item['memory'] for item in limited_memories]
            
            # Record sorting results
            time_info = []
            for item in limited_memories:
                time_str = item['created_at'] if item['created_at'] else "No time"
                time_info.append(f"{item['memory_id']}: {time_str}")
            
            logger.info(f"✅ [MemoryTimeSorter] Historical memory sorting completed, order: {sort_order}, limit: {limit}")
            logger.info(f"📅 [MemoryTimeSorter] Sorted historical memory time: {' | '.join(time_info)}")
            
            return sorted_memories
            
        except Exception as e:
            logger.error(f"❌ [MemoryTimeSorter] Historical memory sorting failed: {e}")
            # Return first limit items of original order on sorting failure
            return historical_memories[:limit]
    
    def format_memories_for_prompt(self, memories: List[Dict[str, Any]], 
                                  memory_type: str = "child") -> str:
        """
        Format sorted memories as text in prompts
        
        Args:
            memories: Sorted list of memories
            memory_type: Memory type, "child" for child memories, "historical" for historical memories
            
        Returns:
            Formatted text
        """
        if not memories:
            return ""
        
        logger.info(f"🔍 [MemoryTimeSorter] Starting to format {memory_type} memories, count: {len(memories)}")
        
        formatted_parts = []
        for i, memory in enumerate(memories):
            if isinstance(memory, dict):
                content = memory.get('content', '')
                created_at = memory.get('created_at')
                memory_id = memory.get('id', 'unknown')
            else:
                content = getattr(memory, 'content', '')
                created_at = getattr(memory, 'created_at', None)
                memory_id = getattr(memory, 'id', 'unknown')
            
            if not content or not content.strip():
                continue
            
            # Format text
            if memory_type == "child":
                # Child memories: format by sequence number and time
                if created_at:
                    time_str = self._format_time_for_display(created_at)
                    formatted_parts.append(f"Fragment {i+1} [{time_str}]: {content}")
                else:
                    formatted_parts.append(f"Fragment {i+1}: {content}")
            else:
                # Historical memories: format by time, use concise date format
                if created_at:
                    time_str = self._format_time_for_display(created_at)
                    # For historical memories, use "Session:" identifier
                    formatted_parts.append(f"[{time_str}] Session: {content}")
                else:
                    formatted_parts.append(content)
        
        result = "\n\n".join(formatted_parts)
        logger.info(f"✅ [MemoryTimeSorter] {memory_type} memory formatting completed, length: {len(result)} characters")
        
        return result 
    
    def _format_time_for_display(self, time_value) -> str:
        """
        Format time value to concise display format - using unified time formatter
        
        Args:
            time_value: Time value (string or datetime object)
            
        Returns:
            Formatted time string
        """
        # Use unified time formatter
        return self.time_formatter.format_time_for_display(time_value)
