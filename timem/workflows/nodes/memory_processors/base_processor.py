"""
Base Memory Processor

Base class for all memory level processors, providing common memory processing logic
"""
import json
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Union
from datetime import datetime
import uuid

from timem.models.memory import Memory, MemoryLevel
from timem.workflows.state import MemoryState
from storage.memory_storage_manager import get_memory_storage_manager_async
from timem.memory.memory_generator import MemoryGenerator
from llm.llm_manager import get_llm
from llm.embedding_service import get_embedding_service
from timem.utils.time_parser import time_parser
from timem.utils.time_window_calculator import TimeWindowCalculator  # Import unified time window calculation tool
from timem.workflows.nodes.memory_indexer import get_memory_indexer  # Update to unified memory indexer
from timem.utils.logging import get_logger

logger = get_logger(__name__)

class BaseMemoryProcessor(ABC):
    """Base class for memory processors, providing common memory processing logic"""

    def __init__(self):
        """Initialize base class"""
        self.llm = get_llm()
        self.memory_generator = MemoryGenerator()
        self._storage_manager = None
        self.memory_indexer = get_memory_indexer()  # Use unified memory indexer
        self.time_calculator = TimeWindowCalculator()
        logger.info(f"{self.__class__.__name__} initialized, using LLM: {self.llm.__class__.__name__}")

    @property
    def memory_level(self) -> str:
        """Return memory level, subclasses must implement"""
        raise NotImplementedError("Subclasses must implement memory_level property")
    
    @property
    def child_level(self) -> str:
        """Return child memory level, subclasses must implement"""
        raise NotImplementedError("Subclasses must implement child_level property")
    
    async def run(self, state: MemoryState) -> MemoryState:
        """
        Workflow node interface, process memory generation and convert to appropriate objects.
        
        Args:
            state: Workflow state
            
        Returns:
            Updated workflow state
        """
        logger.info(f"Executing memory processor: {self.__class__.__name__}")
        print(f"\n Executing {self.memory_level} level memory processing - Session ID: {state.get('session_id', 'unknown')}")
        
        try:
            # Call processing logic to generate memory
            memory_dict_state = await self.process(state)
            generated_memory_dict = memory_dict_state.get("generated_memory")

            if not generated_memory_dict:
                raise Exception(f"{self.memory_level} process and memory generation failed.")
            
            # Add memory level
            if "level" not in generated_memory_dict:
                generated_memory_dict["level"] = self.get_memory_level_enum()
            
            # Convert to Memory object (subclasses can override this method to implement specific conversion logic)
            memory_obj = self.dict_to_memory_object(generated_memory_dict)
            
            state["generated_memory"] = memory_obj
            state["error"] = None
            
            # Get memory ID, supporting both object and dictionary formats
            memory_id = memory_obj.get("id") if isinstance(memory_obj, dict) else getattr(memory_obj, "id", "unknown")
            
            print(f" {self.memory_level} memory object created successfully: {memory_id}")
            logger.info(f"{self.memory_level} memory object created successfully: {memory_id}")

        except Exception as e:
            error_msg = f"{self.memory_level} level memory processing node error: {e}"
            logger.error(error_msg, exc_info=True)
            print(f" {self.memory_level} processing exception: {e}")
            state["error"] = error_msg
            
        return state

    async def _create_memory_base(self, state: MemoryState) -> Dict[str, Any]:
        """Create basic structure of a memory object"""
        # Prioritize using existing generated_memory ID in state, otherwise create new ID
        memory_id = state.get("generated_memory", {}).get("id") or str(uuid.uuid4())

        # Get time window
        time_windows = await self._get_time_windows(state)
        time_window = time_windows.get(self.memory_level, {})
        
        # Get external time as memory creation time
        reference_time = None
        if "original_timestamp" in state and state["original_timestamp"]:
            reference_time = state["original_timestamp"]
        elif "timestamp" in state and state["timestamp"]:
            timestamp = state["timestamp"]
            if isinstance(timestamp, str):
                reference_time = time_parser.parse_session_time(timestamp)
            elif isinstance(timestamp, datetime):
                reference_time = timestamp
        
        # If no external time, use end time of time window
        if reference_time is None:
            reference_time = time_window.get("end")
            if reference_time is None:
                raise ValueError("Unable to get valid time for memory creation")
        
        # Ensure time has no timezone
        if reference_time.tzinfo is not None:
            reference_time = reference_time.replace(tzinfo=None)

        # Get child and historical memories
        child_memory_ids = await self._get_child_memories(state, time_windows)
        historical_memory_ids = await self._get_historical_memories(state)
        
        # Build base dictionary (keep only unified fields)
        memory_dict = {
            "id": memory_id,
            "user_id": state.get("user_id", ""),
            "expert_id": state.get("expert_id", ""),
            "session_id": state.get("session_id", ""),
            "level": self.get_memory_level_enum(),
            "created_at": reference_time,
            "updated_at": reference_time,
            "child_memory_ids": child_memory_ids,
            "historical_memory_ids": historical_memory_ids,
        }
        logger.info(f"{self.memory_level} memory base structure created: ID={memory_id}, Children={len(child_memory_ids)}, History={len(historical_memory_ids)}")
        return memory_dict

    async def process(self, state: MemoryState) -> MemoryState:
        """
        Core processing logic, implement specific memory generation process.
        
        Args:
            state: Workflow state
            
        Returns:
            Workflow state containing generated memory
        """
        try:
            # Create basic structure of memory object
            memory_dict = await self._create_memory_base(state)
            
            # Subclasses extend on this basis, adding specific memory generation logic
            # For example, call LLM to generate summary and populate memory_dict["summary"]

            state["generated_memory"] = memory_dict
            return state
            
        except Exception as e:
            error_msg = f"Error occurred during {self.memory_level} memory generation: {str(e)}"
            logger.error(error_msg, exc_info=True)
            
            state["generated_memory"] = None
            state["generation_errors"] = state.get("generation_errors", []) + [error_msg]
            return state
    
    async def _ensure_storage_manager(self):
        """Ensure storage manager is initialized"""
        if not self._storage_manager:
            self._storage_manager = await get_memory_storage_manager_async()

    async def _get_time_windows(self, state: MemoryState) -> Dict[str, Dict[str, datetime]]:
        """
        Get time windows for each level
        
        Args:
            state: Workflow state
            
        Returns:
            Dictionary of time windows for each level (no timezone)
        """
        # Strictly use external time, avoid datetime.now fallback
        reference_time = None
        
        # 1. Prioritize using original_timestamp
        if "original_timestamp" in state and state["original_timestamp"]:
            reference_time = state["original_timestamp"]
            logger.debug(f"Using original_timestamp: {reference_time}")
        
        # 2. Otherwise use timestamp field
        elif "timestamp" in state and state["timestamp"]:
            timestamp = state["timestamp"]
            try:
                if isinstance(timestamp, str):
                    reference_time = time_parser.parse_session_time(timestamp)
                elif isinstance(timestamp, datetime):
                    reference_time = timestamp
                logger.debug(f"Using timestamp: {reference_time}")
            except Exception as e:
                logger.error(f"Failed to parse timestamp: {e}")
        
        # No longer fallback to get time from metadata, must be passed from external source
        
        # If no valid time is found, raise an exception instead of using datetime.now
        if reference_time is None:
            error_msg = "Unable to get valid time from external data, memory generation failed"
            logger.error(error_msg)
            logger.error(f"Time fields in state: {[k for k in state.keys() if 'time' in k.lower() or 'timestamp' in k.lower()]}")
            raise ValueError(error_msg)
        
        # Ensure time has no timezone
        if reference_time.tzinfo is not None:
            reference_time = reference_time.replace(tzinfo=None)
        
        logger.info(f"Using reference time: {reference_time}")
        
        # Calculate time windows for each level
        time_windows = {}
        for level in ["L1", "L2", "L3", "L4", "L5"]:
            time_windows[level] = self.time_calculator.calculate_time_window(level, reference_time)
        
        return time_windows

    async def _get_child_memories(self, state: MemoryState, time_windows: Dict[str, Dict[str, datetime]]) -> List[str]:
        """
        Get list of child memory IDs
        
        Args:
            state: Workflow state
            time_windows: Time window dictionary
            
        Returns:
            List of child memory IDs
        """
        if not self.child_level:
            return []
            
        user_id = state.get("user_id", "")
        expert_id = state.get("expert_id", "")
        session_id = state.get("session_id", "")
        
        time_window = time_windows.get(self.memory_level, {})
        
        try:
            # Call unified memory indexer to get child memories
            child_memories = await self.memory_indexer.get_child_memories(
                state=state,
                layer=self.child_level,
                time_window=time_window
            )
            
            logger.info(f"Retrieved {self.child_level} child memories: {len(child_memories)} items")
            return child_memories
            
        except Exception as e:
            logger.error(f"Failed to retrieve child memories: {e}", exc_info=True)
            return []

    async def _get_historical_memories(self, state: MemoryState, limit: int = None) -> List[str]:
        """
        Get list of historical memory IDs
        
        Args:
            state: Workflow state
            limit: Maximum return count, if None use global configuration
            
        Returns:
            List of historical memory IDs
        """
        user_id = state.get("user_id", "")
        expert_id = state.get("expert_id", "")
        
        # If no limit specified, use global configuration
        if limit is None:
            from timem.utils.config_manager import get_app_config
            app_config = get_app_config()
            limit = app_config.get("memory", {}).get("historical_memory_limit", 3)
        
        try:
            # Call unified memory indexer to get historical memories
            historical_memories = await self.memory_indexer.get_historical_memories(
                state=state,
                layer=self.memory_level,
                limit=limit
            )
            
            logger.info(f"Retrieved {self.memory_level} historical memories: {len(historical_memories)} items")
            return historical_memories
            
        except Exception as e:
            logger.error(f"Failed to retrieve historical memories: {e}", exc_info=True)
            return []

    def get_memory_level_enum(self) -> MemoryLevel:
        """Get memory level enum value"""
        if self.memory_level == "L1":
            return MemoryLevel.L1
        elif self.memory_level == "L2":
            return MemoryLevel.L2
        elif self.memory_level == "L3":
            return MemoryLevel.L3
        elif self.memory_level == "L4":
            return MemoryLevel.L4
        elif self.memory_level == "L5":
            return MemoryLevel.L5
        else:
            raise ValueError(f"Unsupported memory level: {self.memory_level}")

    def dict_to_memory_object(self, memory_dict: Dict[str, Any]) -> Any:
        """
        Convert dictionary to memory object
        
        Subclasses must override this method to implement specific conversion logic
        
        Args:
            memory_dict: Memory dictionary
            
        Returns:
            Memory object
        """
        try:
            # Ensure required fields exist
            for field in ["child_memory_ids", "historical_memory_ids"]:
                if field not in memory_dict:
                    memory_dict[field] = []
                    
            # Ensure time fields are in string format
            for time_field in ["created_at", "updated_at"]:
                if time_field in memory_dict and not isinstance(memory_dict[time_field], str):
                    from timem.utils.time_utils import ensure_iso_string
                    memory_dict[time_field] = ensure_iso_string(memory_dict[time_field])
            
            # Record detailed logs for debugging conversion issues
            logger.debug(f"Converting memory dictionary to object, level: {self.memory_level}, ID: {memory_dict.get('id', 'unknown')}")
            logger.debug(f"Memory fields: {list(memory_dict.keys())}")
            
            # Fix: Base class no longer returns dictionary, but throws exception to prompt subclass implementation
            raise NotImplementedError(f"{self.__class__.__name__} must implement dict_to_memory_object method")
            
        except Exception as e:
            logger.error(f"Error occurred while converting memory dictionary to object: {str(e)}", exc_info=True)
            # Record detailed dictionary structure for debugging
            logger.debug(f"Problem memory dictionary: {json.dumps(memory_dict, default=str)}")
            return memory_dict  # Return original dictionary on failure