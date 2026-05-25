"""TiMem memory models

Defines data models for memory to solve data format inconsistency issues
"""

from typing import Dict, List, Any, Optional, Set, Union
from datetime import datetime, date
from enum import Enum
from pydantic import BaseModel, Field, validator, model_validator
import uuid
import json

from timem.utils.time_manager import get_time_manager


class MemoryLevel(str, Enum):
    """Memory level enumeration"""
    L1 = "L1"  # Fragment-level memory
    L2 = "L2"  # Session-level memory
    L3 = "L3"  # Daily-level memory
    L4 = "L4"  # Weekly-level memory
    L5 = "L5"  # Monthly-level memory


class Memory(BaseModel):
    """Unified memory base model V3 - aligned with new SQL schema"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Memory ID, globally unique")
    user_id: str = Field(..., description="User ID")
    expert_id: str = Field(..., description="Expert ID")
    level: MemoryLevel = Field(..., description="Memory level")
    title: str = Field(..., description="Memory title")
    content: str = Field(..., description="Core memory content")
    status: str = Field(default="active", description="Memory status (active, archived, deleted)")
    
    # Time window
    # Uniformly provided by upstream generation strategy, local current time is prohibited
    time_window_start: datetime = Field(..., description="Time window start covered by memory (from dataset time or its derivation)")
    time_window_end: datetime = Field(..., description="Time window end covered by memory (from dataset time or its derivation)")

    # Relationship IDs
    child_memory_ids: List[str] = Field(default_factory=list, description="Child memory ID list")
    historical_memory_ids: List[str] = Field(default_factory=list, description="Historical memory ID list")

    # Other
    # Uniformly provided by upstream generation strategy, local current time is prohibited
    created_at: datetime = Field(..., description="Creation time (from dataset time or its derivation)")
    updated_at: datetime = Field(..., description="Update time (from dataset time or its derivation)")
    
    # Backward compatible/optional fields
    session_id: Optional[str] = Field(None, description="Session ID (mainly for L1/L2)")
    
    # Retrieval-related fields
    vector_score: Optional[float] = Field(None, description="Vector similarity score (for semantic retrieval)")
    retrieval_score: Optional[float] = Field(None, description="General retrieval score")

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {datetime: lambda dt: dt.isoformat()}

    @validator('level', pre=True)
    def validate_level(cls, level):
        """Validate memory level"""
        if isinstance(level, str):
            return MemoryLevel(level)
        return level
    
    @validator('created_at', 'updated_at', 'time_window_start', 'time_window_end', pre=True)
    def validate_dates(cls, v):
        """Validate dates, ensure ISO format string or datetime object, and force timezone-naive"""
        if isinstance(v, str):
            v = get_time_manager().parse_iso_time(v)
        if isinstance(v, datetime) and v.tzinfo is not None:
            return v.replace(tzinfo=None)
        return v

    @model_validator(mode='before')
    @classmethod
    def fill_missing_time_fields(cls, data: Any):
        """Fill missing time fields before creation for test compatibility:
        - If missing(updated_at), backfill with created_at
        - If missing(created_at), backfill with time_window_start
        - If missing(time_window_start/time_window_end), backfill with created_at
        - If all above missing, fallback to TimeManager.get_current_time()
        Note: Fallback is for test compatibility only, production should always provide via generation strategy.
        """
        if not isinstance(data, dict):
            return data
        tm = get_time_manager()
        created_at = data.get('created_at')
        updated_at = data.get('updated_at')
        tw_start = data.get('time_window_start')
        tw_end = data.get('time_window_end')
        # Parse string to datetime (keep tz naive)
        def norm(x):
            if isinstance(x, str):
                x_dt = tm.parse_iso_time(x)
                return x_dt.replace(tzinfo=None) if x_dt and x_dt.tzinfo is not None else x_dt
            if isinstance(x, datetime) and x.tzinfo is not None:
                return x.replace(tzinfo=None)
            return x
        created_at = norm(created_at)
        updated_at = norm(updated_at)
        tw_start = norm(tw_start)
        tw_end = norm(tw_end)
        # Fallback order
        now_fallback = tm.get_current_time()
        if created_at is None:
            created_at = tw_start or now_fallback
        if updated_at is None:
            updated_at = created_at
        if tw_start is None:
            tw_start = created_at
        if tw_end is None:
            tw_end = tw_start
        data['created_at'] = created_at
        data['updated_at'] = updated_at
        data['time_window_start'] = tw_start
        data['time_window_end'] = tw_end
        return data

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        # ✨ Fix: do not exclude_none, ensure important fields like session_id are not lost
        # Even if session_id is None, keep the field for proper frontend handling
        result = self.model_dump(mode='json', exclude_none=False)
        
        # ✨ Manual handling: only exclude truly None and unimportant fields
        # Keep important fields: session_id, vector_score, retrieval_score, level, etc.
        important_fields = {'session_id', 'vector_score', 'retrieval_score', 'level', 'id', 'user_id', 'expert_id', 'title', 'content'}
        filtered_result = {}
        for key, value in result.items():
            if value is not None or key in important_fields:
                filtered_result[key] = value
        
        return filtered_result

    def to_payload(self) -> Dict[str, Any]:
        """Convert to storage payload format"""
        payload = self.to_dict()
        
        # ✨ Ensure key fields exist and are correct
        # Even if some fields are None, explicitly set them to avoid loss in Qdrant
        if 'session_id' not in payload:
            payload['session_id'] = None
        
        return payload

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Memory':
        """Create memory from dictionary"""
        return create_memory_by_level(**data)


class FragmentMemory(Memory):
    """Fragment-level memory model (L1)"""
    level: MemoryLevel = MemoryLevel.L1
    dialogue_turns: List[Dict[str, Any]] = Field(..., description="Original dialogue turns")
    original_turn_start: Optional[int] = Field(None, description="Original turn start number")
    original_turn_end: Optional[int] = Field(None, description="Original turn end number")

class SessionMemory(Memory):
    """Session-level memory model (L2)"""
    level: MemoryLevel = MemoryLevel.L2

class DailyMemory(Memory):
    """Daily-level memory model (L3)"""
    level: MemoryLevel = MemoryLevel.L3
    date_value: date = Field(..., description="Specific date corresponding to memory")

class WeeklyMemory(Memory):
    """Weekly-level memory model (L4)"""
    level: MemoryLevel = MemoryLevel.L4
    year: int = Field(..., description="Year")
    week_number: int = Field(..., description="Week number")

class MonthlyMemory(Memory):
    """Monthly-level memory model (L5)"""
    level: MemoryLevel = MemoryLevel.L5
    year: int = Field(..., description="Year")
    month: int = Field(..., description="Month")



def create_memory_by_level(**kwargs) -> Memory:
    """
    Create memory object based on level
    
    Args:
        **kwargs: Memory attributes, must include 'level'
        
    Returns:
        Memory object
    """
    level = kwargs.get("level")
    if not level:
        raise ValueError("Memory attributes must include 'level' field")
        
    if isinstance(level, str):
        level = MemoryLevel(level)
    
    memory_classes = {
        MemoryLevel.L1: FragmentMemory,
        MemoryLevel.L2: SessionMemory,
        MemoryLevel.L3: DailyMemory,
        MemoryLevel.L4: WeeklyMemory,
        MemoryLevel.L5: MonthlyMemory
    }
    
    memory_class = memory_classes.get(level, Memory)
    return memory_class(**kwargs)


def convert_dict_to_memory(memory_dict: Dict[str, Any]) -> Memory:
    """
    Convert dictionary to memory object
    
    Args:
        memory_dict: Memory dictionary
        
    Returns:
        Memory object
    """
    level = memory_dict.get("level")
    if level:
        return create_memory_by_level(**memory_dict)
    else:
        return Memory.from_dict(memory_dict)
