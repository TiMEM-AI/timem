"""TiMem dialogue-related data models (minimal version, for open-source experiments only)

Extracts classes required for experiment pipeline from the full version
"""

from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict


class ThinkingStepType(str, Enum):
    """Thinking step type enumeration"""
    CONTEXT_LOADING = "context_loading"          # Context loading
    QUERY_UNDERSTANDING = "query_understanding"  # Query intent understanding
    QUERY_ANALYSIS = "query_analysis"            # Query analysis
    MEMORY_RETRIEVAL = "memory_retrieval"        # Memory retrieval
    CROSS_SESSION_SEARCH = "cross_session_search"  # Cross-session search
    MEMORY_INTEGRATION = "memory_integration"    # Memory integration
    RESPONSE_GENERATION = "response_generation"  # Response generation
    MEMORY_STORAGE = "memory_storage"            # Memory storage
    MEMORY_GENERATION_L1 = "memory_generation_l1"  # L1 memory generation (streaming)
    MEMORY_GENERATION_L2 = "memory_generation_l2"  # L2 memory generation (streaming)


class RetrievedMemoryDetail(BaseModel):
    """Retrieved memory details"""
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "memory_id": "mem_l1_abc123",
                "content": "User mentioned high work pressure recently, often working overtime until late night",
                "level": "L1",
                "score": 0.89,
                "session_id": "sess_previous_001",
                "timestamp": "2024-10-01T14:30:00Z",
                "metadata": {
                    "expert_id": "expert_psy_001",
                    "keywords": ["pressure", "overtime", "work"]
                }
            }
        }
    )
    
    memory_id: str = Field(..., description="Memory ID")
    content: str = Field(..., description="Memory content")
    level: str = Field(..., description="Memory level (L1-L5)")
    score: float = Field(..., ge=0.0, le=1.0, description="Relevance score")
    session_id: Optional[str] = Field(None, description="Belonging session ID")
    timestamp: Optional[str] = Field(None, description="Memory timestamp")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Memory metadata")


class ThinkingStep(BaseModel):
    """Thinking step"""
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "step_type": "memory_retrieval",
                "step_name": "Retrieve cross-session memory",
                "description": "Retrieving historical memories related to current question...",
                "status": "processing",
                "progress": 0.5,
                "data": {
                    "retrieved_count": 5,
                    "memories": []
                }
            }
        }
    )
    
    step_type: ThinkingStepType = Field(..., description="Step type")
    step_name: str = Field(..., description="Step name")
    description: str = Field(..., description="Step description")
    status: str = Field(..., description="Status: processing/completed/failed")
    progress: Optional[float] = Field(None, ge=0.0, le=1.0, description="Progress (0-1)")
    data: Optional[Dict[str, Any]] = Field(None, description="Step-related data")


class SSEThinkingEvent(BaseModel):
    """SSE thinking process event"""
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "step": {
                    "step_type": "memory_retrieval",
                    "step_name": "Retrieve cross-session memory",
                    "description": "Found 5 relevant memories",
                    "status": "completed",
                    "progress": 1.0,
                    "data": {
                        "retrieved_count": 5,
                        "sessions_hit": ["sess_001", "sess_002"]
                    }
                },
                "retrieved_memories": [],
                "timestamp": "2024-10-10T10:30:00Z"
            }
        }
    )
    
    step: ThinkingStep = Field(..., description="Current thinking step")
    retrieved_memories: Optional[List[RetrievedMemoryDetail]] = Field(
        None,
        description="List of retrieved memory details"
    )
    timestamp: str = Field(..., description="Event timestamp")


__all__ = [
    "ThinkingStepType",
    "ThinkingStep",
    "RetrievedMemoryDetail",
    "SSEThinkingEvent",
]
