"""
TiMem LayerMemoryGenerator - Single Layer Memory Generator (Simplified Version)

Responsible for generating a single memory for a single layer
Refactored from MultiLayerMemoryGenerator, removing batch loop logic
"""

from typing import Dict, List, Any, Optional
from datetime import datetime

from timem.utils.logging import get_logger
from timem.memory.memory_generator import MemoryGenerator
from timem.models.memory import create_memory_by_level, MemoryLevel
from timem.workflows.nodes.memory_collector import CollectedMemories

logger = get_logger(__name__)


class LayerMemoryGenerator:
    """
    Single Layer Memory Generator (Simplified Version)
    
    Responsibilities:
    1. Generate memory content based on collected data
    2. Call LLM service
    3. Construct Memory object
    
    Not included:
    - Data collection (handled by MemoryCollector)
    - Data storage (handled by StorageRouter)
    - Batch logic (only generates a single memory)
    - Cold and hot data concatenation (all inputs come from the database)
    """
    
    def __init__(self, memory_generator: Optional[MemoryGenerator] = None):
        """
        Initialize generator
        
        Args:
            memory_generator: LLM service (dependency injection)
        """
        self.memory_generator = memory_generator or MemoryGenerator()
        
        # Initialize processors for each layer (using unified unified_processors)
        from timem.workflows.nodes.unified_processors import (
            L1Processor,
            L2MemoryProcessor,
            L3MemoryProcessor,
            L4MemoryProcessor,
            L5MemoryProcessor
        )
        from timem.utils.time_manager import get_time_manager
        
        time_manager = get_time_manager()
        
        self.processors = {
            "L1": L1Processor(),  # L1 uses new interface, no need for time_manager
            "L2": L2MemoryProcessor(time_manager),
            "L3": L3MemoryProcessor(time_manager),
            "L4": L4MemoryProcessor(time_manager),
            "L5": L5MemoryProcessor(time_manager)
        }
        
        logger.info("LayerMemoryGenerator initialized (simplified version)")
    
    async def generate(
        self,
        layer: str,
        user_id: str,
        expert_id: str,
        session_id: Optional[str],
        time_window: Optional[Dict[str, Any]],
        collected_memories: CollectedMemories,
        timestamp: datetime
    ) -> Any:
        """
        Generate a single memory
        
        Args:
            layer: Memory layer (L1-L5)
            user_id: User ID
            expert_id: Expert ID
            session_id: Session ID (used by L1/L2)
            time_window: Time window (used by L3/L4/L5)
            collected_memories: Collected child and historical memories
            timestamp: Timestamp
        
        Returns:
            Memory object
        
        Process:
        1. Select corresponding Processor
        2. Build state object
        3. Call Processor.process()
        4. Return Memory object
        """
        logger.info(f"Starting to generate {layer} memory: user={user_id}, expert={expert_id}")
        
        if layer not in self.processors:
            raise ValueError(f"Unsupported memory layer: {layer}")
        
        # Build state object (format required by Processor)
        state = self._build_state(
            layer, user_id, expert_id, session_id,
            time_window, timestamp
        )
        
        # Call corresponding Processor
        processor = self.processors[layer]
        
        try:
            # L1 uses new interface (only pass state), L2-L5 use old interface (pass multiple parameters)
            if layer == "L1":
                # Build complete state for L1 (containing child and historical memories)
                state_for_l1 = state.copy()
                state_for_l1["L1_historical_memory_ids"] = [
                    m.get("id") if isinstance(m, dict) else getattr(m, "id", None)
                    for m in collected_memories.historical_memories
                    if (m.get("id") if isinstance(m, dict) else getattr(m, "id", None)) is not None
                ]
                result_state = await processor.process(state_for_l1)
                # Extract memory from returned state
                memory = result_state.get("generated_memory") or result_state.get("memory")
            else:
                # L2-L5 use old interface
                memory = await processor.process(
                    state=state,
                    user_id=user_id,
                    expert_id=expert_id,
                    layer=layer,
                    child_memories=collected_memories.child_memories,
                    historical_memories=collected_memories.historical_memories
                )
            
            logger.info(f"{layer} memory generation successful: id={getattr(memory, 'id', 'Unknown')}")
            
            return memory
            
        except Exception as e:
            logger.error(f"{layer} memory generation failed: {e}", exc_info=True)
            raise
    
    def _build_state(
        self,
        layer: str,
        user_id: str,
        expert_id: str,
        session_id: Optional[str],
        time_window: Optional[Dict[str, Any]],
        timestamp: datetime
    ) -> Dict[str, Any]:
        """
        Build state object
        
        Args:
            layer: Memory layer
            user_id: User ID
            expert_id: Expert ID
            session_id: Session ID
            time_window: Time window
            timestamp: Timestamp
        
        Returns:
            State dictionary
        """
        state = {
            "user_id": user_id,
            "expert_id": expert_id,
            "session_id": session_id or "",
            "timestamp": timestamp,
            "original_timestamp": timestamp,
            "memory_decisions": {
                layer: {
                    "collection_info": {
                        "time_window": time_window or {}
                    }
                }
            }
        }
        
        return state

