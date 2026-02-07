"""
Memory object unified processing tools

Provides unified memory object conversion, validation and processing functions
"""

from typing import Dict, List, Any, Optional, Union
from timem.models.memory import (
    Memory, FragmentMemory, SessionMemory, DailyMemory, 
    WeeklyMemory, MonthlyMemory, MemoryLevel
)
from timem.utils.logging import get_logger

logger = get_logger(__name__)


class MemoryObjectUtils:
    """Memory object unified processing tool class"""
    
    @staticmethod
    def ensure_field_compatibility(memory_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ensure memory object field compatibility
        
        Args:
            memory_dict: Memory dictionary
            
        Returns:
            Compatible memory dictionary
        """
        if not isinstance(memory_dict, dict):
            return memory_dict
            
        # Create copy to avoid modifying original object
        result = memory_dict.copy()
        
        # 🔧 Ensure level and layer field compatibility
        if "level" in result and result["level"]:
            if "layer" not in result:
                result["layer"] = result["level"]  # Maintain compatibility
        elif "layer" in result and result["layer"]:
            if "level" not in result:
                result["level"] = result["layer"]  # Unify using level
        
        # Ensure required fields exist
        required_fields = {
            "child_memory_ids": [],
            "historical_memory_ids": [],
            "metadata": {}
        }
        
        for field, default_value in required_fields.items():
            if field not in result:
                result[field] = default_value
        
        return result
    
    @staticmethod
    def memory_to_dict(memory: Union[Memory, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Convert memory object to dictionary format
        
        Args:
            memory: Memory object or dictionary
            
        Returns:
            Dictionary format memory data
        """
        if isinstance(memory, dict):
            return MemoryObjectUtils.ensure_field_compatibility(memory)
        
        try:
            # Try multiple conversion methods
            if hasattr(memory, 'model_dump'):
                memory_dict = memory.model_dump(mode='json', exclude_none=True)
            elif hasattr(memory, 'to_dict'):
                memory_dict = memory.to_dict()
            elif hasattr(memory, 'dict'):
                memory_dict = memory.dict()
            elif hasattr(memory, '__dict__'):
                memory_dict = memory.__dict__.copy()
                # Ensure level field exists
                if hasattr(memory, 'level'):
                    memory_dict["level"] = str(memory.level) if memory.level else "Unknown"
            else:
                logger.warning(f"Cannot convert memory object: {type(memory)}")
                return {}
            
            # Ensure field compatibility
            return MemoryObjectUtils.ensure_field_compatibility(memory_dict)
            
        except Exception as e:
            logger.error(f"Failed to convert memory object: {e}")
            return {}
    
    @staticmethod
    def dict_to_memory_object(memory_dict: Dict[str, Any], memory_level: str) -> Union[Memory, Dict[str, Any]]:
        """
        Convert dictionary to corresponding memory object
        
        Args:
            memory_dict: Memory dictionary
            memory_level: Memory level (L1, L2, L3, L4, L5)
            
        Returns:
            Memory object or dictionary
        """
        try:
            # Ensure field compatibility
            memory_dict = MemoryObjectUtils.ensure_field_compatibility(memory_dict)
            
            # Ensure required fields exist
            if "id" not in memory_dict:
                import uuid
                memory_dict["id"] = str(uuid.uuid4())
            
            if "created_at" not in memory_dict:
                from timem.utils.time_utils import ensure_iso_string
                from datetime import datetime
                memory_dict["created_at"] = ensure_iso_string(datetime.now())
            
            if "updated_at" not in memory_dict:
                memory_dict["updated_at"] = memory_dict["created_at"]
            
            # Create corresponding memory object based on level
            if memory_level == "L1":
                return FragmentMemory(
                    id=memory_dict.get("id", ""),
                    user_id=memory_dict.get("user_id", ""),
                    expert_id=memory_dict.get("expert_id", ""),
                    session_id=memory_dict.get("session_id", ""),
                    level=MemoryLevel.L1,
                    title=memory_dict.get("title", ""),
                    content=memory_dict.get("content", ""),
                    dialogue_turns=memory_dict.get("dialogue_turns", []),
                    created_at=memory_dict.get("created_at", ""),
                    updated_at=memory_dict.get("updated_at", ""),
                    child_memory_ids=memory_dict.get("child_memory_ids", []),
                    historical_memory_ids=memory_dict.get("historical_memory_ids", []),
                    metadata=memory_dict.get("metadata", {})
                )
            elif memory_level == "L2":
                return SessionMemory(
                    id=memory_dict.get("id", ""),
                    user_id=memory_dict.get("user_id", ""),
                    expert_id=memory_dict.get("expert_id", ""),
                    session_id=memory_dict.get("session_id", ""),
                    level=MemoryLevel.L2,
                    title=memory_dict.get("title", ""),
                    content=memory_dict.get("content", ""),
                    created_at=memory_dict.get("created_at", ""),
                    updated_at=memory_dict.get("updated_at", ""),
                    child_memory_ids=memory_dict.get("child_memory_ids", []),
                    historical_memory_ids=memory_dict.get("historical_memory_ids", []),
                    metadata=memory_dict.get("metadata", {})
                )
            elif memory_level == "L3":
                return DailyMemory(
                    id=memory_dict.get("id", ""),
                    user_id=memory_dict.get("user_id", ""),
                    expert_id=memory_dict.get("expert_id", ""),
                    session_id=memory_dict.get("session_id", ""),
                    level=MemoryLevel.L3,
                    title=memory_dict.get("title", ""),
                    content=memory_dict.get("content", ""),
                    created_at=memory_dict.get("created_at", ""),
                    updated_at=memory_dict.get("updated_at", ""),
                    child_memory_ids=memory_dict.get("child_memory_ids", []),
                    historical_memory_ids=memory_dict.get("historical_memory_ids", []),
                    date_value=memory_dict.get("date_value"),
                    metadata=memory_dict.get("metadata", {})
                )
            elif memory_level == "L4":
                return WeeklyMemory(
                    id=memory_dict.get("id", ""),
                    user_id=memory_dict.get("user_id", ""),
                    expert_id=memory_dict.get("expert_id", ""),
                    session_id=memory_dict.get("session_id", ""),
                    level=MemoryLevel.L4,
                    title=memory_dict.get("title", ""),
                    content=memory_dict.get("content", ""),
                    created_at=memory_dict.get("created_at", ""),
                    updated_at=memory_dict.get("updated_at", ""),
                    child_memory_ids=memory_dict.get("child_memory_ids", []),
                    historical_memory_ids=memory_dict.get("historical_memory_ids", []),
                    year=memory_dict.get("year"),
                    week_number=memory_dict.get("week_number"),
                    metadata=memory_dict.get("metadata", {})
                )
            elif memory_level == "L5":
                return MonthlyMemory(
                    id=memory_dict.get("id", ""),
                    user_id=memory_dict.get("user_id", ""),
                    expert_id=memory_dict.get("expert_id", ""),
                    session_id=memory_dict.get("session_id", ""),
                    level=MemoryLevel.L5,
                    title=memory_dict.get("title", ""),
                    content=memory_dict.get("content", ""),
                    created_at=memory_dict.get("created_at", ""),
                    updated_at=memory_dict.get("updated_at", ""),
                    child_memory_ids=memory_dict.get("child_memory_ids", []),
                    historical_memory_ids=memory_dict.get("historical_memory_ids", []),
                    year=memory_dict.get("year"),
                    month=memory_dict.get("month"),
                    metadata=memory_dict.get("metadata", {})
                )
            else:
                logger.warning(f"Unknown memory level: {memory_level}")
                return memory_dict
                
        except Exception as e:
            logger.error(f"Failed to convert dictionary to memory object: {e}")
            return memory_dict
    
    @staticmethod
    def batch_convert_memories_to_dict(memories: List[Union[Memory, Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """
        Batch convert memory objects to dictionary format
        
        Args:
            memories: Memory object list
            
        Returns:
            Dictionary format memory data list
        """
        converted = []
        for i, memory in enumerate(memories):
            try:
                memory_dict = MemoryObjectUtils.memory_to_dict(memory)
                if memory_dict:
                    converted.append(memory_dict)
                else:
                    logger.warning(f"Memory {i} conversion failed, skipping")
            except Exception as e:
                logger.error(f"Error converting memory {i}: {e}")
                continue
        
        return converted
    
    @staticmethod
    def validate_memory_object(memory: Union[Memory, Dict[str, Any]]) -> bool:
        """
        Validate memory object completeness
        
        Args:
            memory: Memory object or dictionary
            
        Returns:
            Whether valid
        """
        try:
            if isinstance(memory, dict):
                required_fields = ["id", "user_id", "expert_id", "content"]
                for field in required_fields:
                    if field not in memory or not memory[field]:
                        logger.warning(f"Memory object missing required field: {field}")
                        return False
            else:
                # Check object type
                if not hasattr(memory, 'id') or not memory.id:
                    logger.warning("Memory object missing ID")
                    return False
                if not hasattr(memory, 'content') or not memory.content:
                    logger.warning("Memory object missing content")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating memory object: {e}")
            return False


# Convenience functions
def ensure_memory_field_compatibility(memory_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure memory object field compatibility"""
    return MemoryObjectUtils.ensure_field_compatibility(memory_dict)


def convert_memory_to_dict(memory: Union[Memory, Dict[str, Any]]) -> Dict[str, Any]:
    """Convert memory object to dictionary format"""
    return MemoryObjectUtils.memory_to_dict(memory)


def convert_dict_to_memory(memory_dict: Dict[str, Any], memory_level: str) -> Union[Memory, Dict[str, Any]]:
    """Convert dictionary to corresponding memory object"""
    return MemoryObjectUtils.dict_to_memory_object(memory_dict, memory_level)


def batch_convert_memories(memories: List[Union[Memory, Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Batch convert memory objects to dictionary format"""
    return MemoryObjectUtils.batch_convert_memories_to_dict(memories)


def validate_memory(memory: Union[Memory, Dict[str, Any]]) -> bool:
    """Validate memory object completeness"""
    return MemoryObjectUtils.validate_memory_object(memory)


