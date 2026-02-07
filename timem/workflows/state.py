"""
TiMem workflow state model

Define data structures and validation methods for workflow state, unified state management
"""

from typing import Dict, List, Any, Optional, Set, Union
from datetime import datetime
from pydantic import BaseModel, Field, validator
import json


class TimeWindow(BaseModel):
    """Time window model"""
    description: str = Field(..., description="Time window description")
    start_time: datetime = Field(..., description="Start time")
    end_time: datetime = Field(..., description="End time")

    class Config:
        arbitrary_types_allowed = True
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "description": self.description,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TimeWindow':
        """Create time window from dictionary"""
        if isinstance(data.get("start_time"), str):
            data["start_time"] = datetime.fromisoformat(data["start_time"])
        if isinstance(data.get("end_time"), str):
            data["end_time"] = datetime.fromisoformat(data["end_time"])
        return cls(**data)


class CollectionInfo(BaseModel):
    """Collection information model"""
    child_memory_layer: Optional[str] = Field(None, description="Child memory layer")
    historical_memory_layer: Optional[str] = Field(None, description="Historical memory layer")
    historical_memory_limit: Optional[int] = Field(None, description="Historical memory count limit")
    historical_memory_scope: Optional[str] = Field(None, description="Historical memory scope")
    time_window: Optional[TimeWindow] = Field(None, description="Time window")
    
    class Config:
        arbitrary_types_allowed = True
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        result = {
            "child_memory_layer": self.child_memory_layer,
            "historical_memory_layer": self.historical_memory_layer,
            "historical_memory_limit": self.historical_memory_limit,
            "historical_memory_scope": self.historical_memory_scope,
        }
        
        if self.time_window:
            result["time_window"] = self.time_window.to_dict()
            
        return result
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CollectionInfo':
        """Create collection information from dictionary"""
        if data.get("time_window"):
            data["time_window"] = TimeWindow.from_dict(data["time_window"])
        return cls(**data)


class MemoryDecision(BaseModel):
    """Memory decision model"""
    reason: str = Field(..., description="Decision reason")
    collection_info: CollectionInfo = Field(..., description="Collection information")
    
    class Config:
        arbitrary_types_allowed = True
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "reason": self.reason,
            "collection_info": self.collection_info.to_dict(),
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MemoryDecision':
        """Create memory decision from dictionary"""
        if isinstance(data.get("collection_info"), dict):
            data["collection_info"] = CollectionInfo.from_dict(data["collection_info"])
        return cls(**data)


class CollectedMemories(BaseModel):
    """Collected memories model"""
    child_memories: List[Dict[str, Any]] = Field(default_factory=list, description="Child memories list")
    historical_memories: List[Dict[str, Any]] = Field(default_factory=list, description="Historical memories list")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "child_memories": self.child_memories,
            "historical_memories": self.historical_memories,
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CollectedMemories':
        """Create collected memories from dictionary"""
        return cls(**data)


class MemoryState(Dict[str, Any]):
    """
    Workflow state class providing standardized state management and validation
    
    Uses Dict as base class while providing structured access methods and validation functionality
    """
    
    @classmethod
    def create(cls, 
               user_id: str,
               expert_id: str, 
               session_id: str,
               content: str,
               timestamp: Optional[Union[str, datetime]] = None,
               execution_state: Optional[Any] = None) -> 'MemoryState':
        """
        Create new workflow state
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            session_id: Session ID
            content: Content
            timestamp: Timestamp, must provide external time source, cannot use current time
            execution_state: Execution state object for concurrent state management
            
        Returns:
            Initialized state object
        """
        # Strictly require external time source, cannot use datetime.now
        if timestamp is None:
            raise ValueError("Must provide external timestamp, cannot use current time as memory generation time")
        elif isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp)
            except ValueError as e:
                raise ValueError(f"Cannot parse timestamp string: {timestamp}, error: {e}")
        
        # Ensure timestamp has no timezone
        if timestamp.tzinfo is not None:
            timestamp = timestamp.replace(tzinfo=None)
            
        state = cls({
            "user_id": user_id,
            "expert_id": expert_id,
            "session_id": session_id,
            "content": content,
            "timestamp": timestamp,
            "original_timestamp": timestamp,  # Save original timestamp
            "execution_state": execution_state,  # Add execution state support
            "memory_decisions": {},
            "collected_memories": {},
            "generated_memories": [],
            "processing_order": [],
            "pending_memory_layers": [],
            "storage_results": []
        })
        
        return state
    
    def add_memory_decision(self, layer: str, decision: Union[MemoryDecision, Dict[str, Any]]) -> None:
        """
        Add memory decision
        
        Args:
            layer: Memory layer
            decision: Decision object or dictionary
        """
        if not isinstance(decision, MemoryDecision):
            decision = MemoryDecision.from_dict(decision)
            
        if "memory_decisions" not in self:
            self["memory_decisions"] = {}
            
        self["memory_decisions"][layer] = decision.to_dict()
    
    def add_collected_memory(self, layer: str, collected: Union[CollectedMemories, Dict[str, Any]]) -> None:
        """
        Add collected memory
        
        Args:
            layer: Memory layer
            collected: Collected memory object or dictionary
        """
        if not isinstance(collected, CollectedMemories):
            collected = CollectedMemories.from_dict(collected)
            
        if "collected_memories" not in self:
            self["collected_memories"] = {}
            
        self["collected_memories"][layer] = collected.to_dict()
    
    def add_generated_memory(self, memory: Dict[str, Any]) -> None:
        """
        Add generated memory
        
        Args:
            memory: Memory object
        """
        if "generated_memories" not in self:
            self["generated_memories"] = []
            
        self["generated_memories"].append(memory)
    
    def add_processing_layer(self, layer: str) -> None:
        """
        Add processing layer
        
        Args:
            layer: Memory layer
        """
        if "processing_order" not in self:
            self["processing_order"] = []
            
        if layer not in self["processing_order"]:
            self["processing_order"].append(layer)
    
    def add_pending_layer(self, layer: str) -> None:
        """
        Add pending layer
        
        Args:
            layer: Memory layer
        """
        if "pending_memory_layers" not in self:
            self["pending_memory_layers"] = []
            
        if layer not in self["pending_memory_layers"]:
            self["pending_memory_layers"].append(layer)
    
    def remove_pending_layer(self, layer: str) -> None:
        """
        Remove pending layer
        
        Args:
            layer: Memory layer
        """
        if "pending_memory_layers" in self and layer in self["pending_memory_layers"]:
            self["pending_memory_layers"].remove(layer)
    
    def add_storage_result(self, result: Dict[str, Any]) -> None:
        """
        Add storage result
        
        Args:
            result: Storage result
        """
        if "storage_results" not in self:
            self["storage_results"] = []
            
        self["storage_results"].append(result)
    
    def set_error(self, error: str) -> None:
        """
        Set error message
        
        Args:
            error: Error description
        """
        self["error"] = error
    
    def to_json(self) -> str:
        """
        Serialize to JSON
        
        Returns:
            JSON string
        """
        state_copy = self.copy()
        
        # Handle datetime objects
        if "timestamp" in state_copy and isinstance(state_copy["timestamp"], datetime):
            state_copy["timestamp"] = state_copy["timestamp"].isoformat()
        
        # Handle datetime in decisions
        if "memory_decisions" in state_copy:
            for layer, decision in state_copy["memory_decisions"].items():
                if "collection_info" in decision and "time_window" in decision["collection_info"]:
                    time_window = decision["collection_info"]["time_window"]
                    if "start_time" in time_window and isinstance(time_window["start_time"], datetime):
                        time_window["start_time"] = time_window["start_time"].isoformat()
                    if "end_time" in time_window and isinstance(time_window["end_time"], datetime):
                        time_window["end_time"] = time_window["end_time"].isoformat()
        
        return json.dumps(state_copy)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'MemoryState':
        """
        Deserialize from JSON
        
        Args:
            json_str: JSON string
            
        Returns:
            State object
        """
        state_dict = json.loads(json_str)
        
        # Handle datetime objects
        if "timestamp" in state_dict and isinstance(state_dict["timestamp"], str):
            state_dict["timestamp"] = datetime.fromisoformat(state_dict["timestamp"])
        
        # Handle datetime in decisions
        if "memory_decisions" in state_dict:
            for layer, decision in state_dict["memory_decisions"].items():
                if "collection_info" in decision and "time_window" in decision["collection_info"]:
                    time_window = decision["collection_info"]["time_window"]
                    if "start_time" in time_window and isinstance(time_window["start_time"], str):
                        time_window["start_time"] = datetime.fromisoformat(time_window["start_time"])
                    if "end_time" in time_window and isinstance(time_window["end_time"], str):
                        time_window["end_time"] = datetime.fromisoformat(time_window["end_time"])
        
        return cls(state_dict)
    
    def validate(self) -> List[str]:
        """
        Validate state integrity
        
        Returns:
            List of error messages, empty list if no errors
        """
        errors = []
        
        # Check required fields
        required_fields = [
            "user_id", "expert_id", "session_id", "content", "timestamp"
        ]
        
        for field in required_fields:
            if field not in self or self[field] is None:
                errors.append(f"Missing required field: {field}")
        
        # Validate timestamp is datetime type
        if "timestamp" in self and not isinstance(self["timestamp"], datetime):
            errors.append(f"timestamp must be datetime type, currently: {type(self['timestamp'])}")
        
        # Validate memory_decisions structure
        if "memory_decisions" in self:
            if not isinstance(self["memory_decisions"], dict):
                errors.append("memory_decisions must be dict type")
            else:
                for layer, decision in self["memory_decisions"].items():
                    if not isinstance(decision, dict):
                        errors.append(f"memory_decisions[{layer}] must be dict type")
                        continue
                    
                    if "reason" not in decision:
                        errors.append(f"memory_decisions[{layer}] missing reason field")
                    
                    if "collection_info" not in decision:
                        errors.append(f"memory_decisions[{layer}] missing collection_info field")
                    elif not isinstance(decision["collection_info"], dict):
                        errors.append(f"memory_decisions[{layer}].collection_info must be dict type")
                    else:
                        collection_info = decision["collection_info"]
                        if "time_window" in collection_info and collection_info["time_window"] is not None:
                            time_window = collection_info["time_window"]
                            if not isinstance(time_window, dict):
                                errors.append(f"memory_decisions[{layer}].collection_info.time_window must be dict type")
                            else:
                                if "start_time" not in time_window or time_window["start_time"] is None:
                                    errors.append(f"memory_decisions[{layer}].collection_info.time_window missing start_time")
                                if "end_time" not in time_window or time_window["end_time"] is None:
                                    errors.append(f"memory_decisions[{layer}].collection_info.time_window missing end_time")
        
        # Validate collected_memories structure
        if "collected_memories" in self:
            if not isinstance(self["collected_memories"], dict):
                errors.append("collected_memories must be dict type")
        
        # Validate generated_memories structure
        if "generated_memories" in self:
            if not isinstance(self["generated_memories"], list):
                errors.append("generated_memories must be list type")
        
        # Validate processing_order structure
        if "processing_order" in self:
            if not isinstance(self["processing_order"], list):
                errors.append("processing_order must be list type")
        
        # Validate pending_memory_layers structure
        if "pending_memory_layers" in self:
            if not isinstance(self["pending_memory_layers"], list):
                errors.append("pending_memory_layers must be list type")
        
        return errors


class MemoryStateValidator:
    """
    State validator for validating workflow state integrity and correctness
    """
    
    @staticmethod
    def validate_state(state: MemoryState) -> List[str]:
        """
        Validate state integrity
        
        Args:
            state: Workflow state
            
        Returns:
            List of error messages, empty list if no errors
        """
        return state.validate()
    
    @staticmethod
    def validate_token_generator_input(state: MemoryState) -> List[str]:
        """
        Validate TokenGenerator node input state
        
        Args:
            state: Workflow state
            
        Returns:
            List of error messages, empty list if no errors
        """
        errors = []
        
        # Check basic fields
        required_fields = [
            "user_id", "expert_id", "session_id", "content", "timestamp"
        ]
        
        for field in required_fields:
            if field not in state or state[field] is None:
                errors.append(f"TokenGenerator input missing required field: {field}")
        
        return errors
    
    @staticmethod
    def validate_token_generator_output(state: MemoryState) -> List[str]:
        """
        Validate TokenGenerator node output state
        
        Args:
            state: Workflow state
            
        Returns:
            List of error messages, empty list if no errors
        """
        errors = []
        
        # Check basic fields
        if "memory_decisions" not in state or not state["memory_decisions"]:
            errors.append("TokenGenerator output missing memory_decisions field")
        
        if "pending_memory_layers" not in state or not state["pending_memory_layers"]:
            errors.append("TokenGenerator output missing pending_memory_layers field")
        
        # Validate memory_decisions and pending_memory_layers consistency
        if "memory_decisions" in state and "pending_memory_layers" in state:
            decision_layers = set(state["memory_decisions"].keys())
            pending_layers = set(state["pending_memory_layers"])
            
            # All pending layers should exist in decisions
            invalid_pending = pending_layers - decision_layers
            if invalid_pending:
                errors.append(f"TokenGenerator output pending_memory_layers contains invalid layers: {invalid_pending}")
        
        return errors
    
    @staticmethod
    def validate_history_collector_input(state: MemoryState) -> List[str]:
        """
        Validate HistoryCollector node input state
        
        Args:
            state: Workflow state
            
        Returns:
            List of error messages, empty list if no errors
        """
        errors = []
        
        # Check basic fields
        required_fields = [
            "user_id", "expert_id", "session_id", "timestamp"
        ]
        
        for field in required_fields:
            if field not in state or state[field] is None:
                errors.append(f"HistoryCollector input missing required field: {field}")
        
        if "memory_decisions" not in state or not state["memory_decisions"]:
            errors.append("HistoryCollector input missing memory_decisions field")
        
        if "pending_memory_layers" not in state or not state["pending_memory_layers"]:
            errors.append("HistoryCollector input missing pending_memory_layers field")
        
        return errors
    
    @staticmethod
    def validate_history_collector_output(state: MemoryState) -> List[str]:
        """
        Validate HistoryCollector node output state
        
        Args:
            state: Workflow state
            
        Returns:
            List of error messages, empty list if no errors
        """
        errors = []
        
        # Check collected_memories field
        if "collected_memories" not in state or not state["collected_memories"]:
            errors.append("HistoryCollector output missing collected_memories field")
        
        # Validate collected_memories structure
        if "collected_memories" in state and "memory_decisions" in state:
            collected_layers = set(state["collected_memories"].keys())
            decision_layers = set(state["memory_decisions"].keys())
            
            # All collected layers should exist in decisions
            invalid_collected = collected_layers - decision_layers
            if invalid_collected:
                errors.append(f"HistoryCollector output collected_memories contains invalid layers: {invalid_collected}")
            
            # Check if collected content is complete for each layer
            for layer in collected_layers.intersection(decision_layers):
                collected = state["collected_memories"].get(layer, {})
                if not isinstance(collected, dict):
                    errors.append(f"HistoryCollector output collected_memories[{layer}] must be dict type")
                    continue
                
                if "child_memories" not in collected:
                    errors.append(f"HistoryCollector output collected_memories[{layer}] missing child_memories field")
                
                if "historical_memories" not in collected:
                    errors.append(f"HistoryCollector output collected_memories[{layer}] missing historical_memories field")
        
        return errors
    
    @staticmethod
    def validate_memory_generator_input(state: MemoryState) -> List[str]:
        """
        Validate MultiLayerMemoryGenerator node input state
        
        Args:
            state: Workflow state
            
        Returns:
            List of error messages, empty list if no errors
        """
        errors = []
        
        # Check basic fields
        required_fields = [
            "user_id", "expert_id", "session_id", "timestamp"
        ]
        
        for field in required_fields:
            if field not in state or state[field] is None:
                errors.append(f"MultiLayerMemoryGenerator input missing required field: {field}")
        
        if "memory_decisions" not in state or not state["memory_decisions"]:
            errors.append("MultiLayerMemoryGenerator input missing memory_decisions field")
        
        if "collected_memories" not in state or not state["collected_memories"]:
            errors.append("MultiLayerMemoryGenerator input missing collected_memories field")
        
        if "pending_memory_layers" not in state or not state["pending_memory_layers"]:
            errors.append("MultiLayerMemoryGenerator input missing pending_memory_layers field")
            
        # Validate collected_memories contains all pending_memory_layers
        if "collected_memories" in state and "pending_memory_layers" in state:
            collected_layers = set(state["collected_memories"].keys())
            pending_layers = set(state["pending_memory_layers"])
            
            missing_collected = pending_layers - collected_layers
            if missing_collected:
                errors.append(f"MultiLayerMemoryGenerator input collected_memories missing pending layers: {missing_collected}")
        
        return errors
    
    @staticmethod
    def validate_memory_generator_output(state: MemoryState) -> List[str]:
        """
        Validate MultiLayerMemoryGenerator node output state
        
        Args:
            state: Workflow state
            
        Returns:
            List of error messages, empty list if no errors
        """
        errors = []
        
        # Check generated_memories field (allow empty)
        if "generated_memories" not in state:
            errors.append("MultiLayerMemoryGenerator output missing generated_memories field")
        
        # Check processing_order field
        if "processing_order" not in state or not state["processing_order"]:
            errors.append("MultiLayerMemoryGenerator output missing processing_order field")
            
        # Validate generated memory format (if present)
        if "generated_memories" in state and state["generated_memories"]:
            for i, memory in enumerate(state["generated_memories"]):
                if memory is None:
                    errors.append(f"MultiLayerMemoryGenerator output generated_memories[{i}] is None")
                    continue
                    
                if not isinstance(memory, dict) and not hasattr(memory, 'id'):
                    errors.append(f"MultiLayerMemoryGenerator output generated_memories[{i}] invalid format, missing id attribute")
                    
                memory_id = None
                if isinstance(memory, dict):
                    memory_id = memory.get('id')
                elif hasattr(memory, 'id'):
                    memory_id = memory.id
                    
                if not memory_id:
                    errors.append(f"MultiLayerMemoryGenerator output generated_memories[{i}] missing valid id")
        
        return errors
    
    @staticmethod
    def validate_storage_router_input(state: MemoryState) -> List[str]:
        """
        Validate StorageRouter node input state
        
        Args:
            state: Workflow state
            
        Returns:
            List of error messages, empty list if no errors
        """
        errors = []
        
        # Check generated_memories field
        if "generated_memories" not in state or not state["generated_memories"]:
            errors.append("StorageRouter input missing generated_memories field")
            
        # Validate generated memories have valid IDs
        if "generated_memories" in state and state["generated_memories"]:
            for i, memory in enumerate(state["generated_memories"]):
                if memory is None:
                    errors.append(f"StorageRouter input generated_memories[{i}] is None")
                    continue
                    
                memory_id = None
                if isinstance(memory, dict) and 'id' in memory:
                    memory_id = memory['id']
                elif hasattr(memory, 'id'):
                    memory_id = memory.id
                
                if not memory_id:
                    errors.append(f"StorageRouter input generated_memories[{i}] missing valid id")
        
        return errors
    
    @staticmethod
    def validate_storage_router_output(state: MemoryState) -> List[str]:
        """
        Validate StorageRouter node output state
        
        Args:
            state: Workflow state
            
        Returns:
            List of error messages, empty list if no errors
        """
        errors = []
        
        # Check storage_results field
        if "storage_results" not in state:
            errors.append("StorageRouter output missing storage_results field")
        
        # Check success field
        if "success" not in state:
            errors.append("StorageRouter output missing success field")
        
        # If successful, check memory_ids field
        if state.get("success") and "memory_ids" not in state:
            errors.append("StorageRouter output successful but missing memory_ids field")
        
        return errors
    
    @staticmethod
    def recover_state(state: MemoryState, previous_state: Optional[MemoryState] = None) -> MemoryState:
        """
        Recover state and fix issues in state
        
        Args:
            state: Current workflow state
            previous_state: Previous valid state for rollback
            
        Returns:
            Fixed state
        """
        # If there is a previous valid state, rollback directly
        if previous_state is not None:
            return previous_state.copy()
        
        # Try to fix current state
        fixed_state = state.copy()
        
        # Ensure basic fields exist
        for field in ["user_id", "expert_id", "session_id", "content"]:
            if field not in fixed_state or fixed_state[field] is None:
                fixed_state[field] = ""
        
        # Special handling for timestamp field - strictly require external time
        if "timestamp" not in fixed_state or fixed_state["timestamp"] is None:
            error_msg = "State recovery failed: missing external timestamp, cannot use current time as memory generation time"
            raise ValueError(error_msg)
        
        # Ensure structured fields exist
        if "memory_decisions" not in fixed_state:
            fixed_state["memory_decisions"] = {}
            
        if "collected_memories" not in fixed_state:
            fixed_state["collected_memories"] = {}
            
        if "generated_memories" not in fixed_state:
            fixed_state["generated_memories"] = []
            
        if "processing_order" not in fixed_state:
            fixed_state["processing_order"] = []
            
        if "pending_memory_layers" not in fixed_state:
            fixed_state["pending_memory_layers"] = []
            
        if "storage_results" not in fixed_state:
            fixed_state["storage_results"] = []
            
        # Fix memory_decisions and pending_memory_layers consistency
        if "memory_decisions" in fixed_state and "pending_memory_layers" in state:
            decision_layers = set(fixed_state["memory_decisions"].keys())
            
            # Remove pending layers not in decisions
            valid_pending_layers = [
                layer for layer in state["pending_memory_layers"]
                if layer in decision_layers
            ]
            fixed_state["pending_memory_layers"] = valid_pending_layers
        
        # Fix collected_memories consistency
        if "memory_decisions" in fixed_state and "collected_memories" in fixed_state:
            decision_layers = set(fixed_state["memory_decisions"].keys())
            collected_layers = set(fixed_state["collected_memories"].keys())
            
            # Remove collected memories not in decisions
            invalid_collected = collected_layers - decision_layers
            if invalid_collected:
                for layer in invalid_collected:
                    if layer in fixed_state["collected_memories"]:
                        del fixed_state["collected_memories"][layer]
            
            # Ensure each collected memory has child_memories and historical_memories
            for layer in fixed_state["collected_memories"]:
                collected = fixed_state["collected_memories"][layer]
                if isinstance(collected, dict):
                    if "child_memories" not in collected:
                        collected["child_memories"] = []
                    if "historical_memories" not in collected:
                        collected["historical_memories"] = []
        
        # Clean up invalid generated memories
        if "generated_memories" in fixed_state:
            valid_memories = []
            for memory in fixed_state["generated_memories"]:
                if memory is not None:
                    # Check if has id
                    has_id = False
                    if isinstance(memory, dict) and 'id' in memory:
                        has_id = bool(memory['id'])
                    elif hasattr(memory, 'id'):
                        has_id = bool(memory.id)
                    
                    if has_id:
                        valid_memories.append(memory)
            
            fixed_state["generated_memories"] = valid_memories
        
        return fixed_state