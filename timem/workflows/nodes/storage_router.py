"""
TiMem Storage Router Node
Responsible for routing generated memories to different storage backends
"""
import logging
from typing import Dict, Any

from timem.workflows.state import MemoryState
from storage.memory_storage_manager import MemoryStorageManager, get_memory_storage_manager_async
from timem.utils.memory_accessor import get_memory_id, get_memory_level
from timem.utils.logging import get_logger

logger = get_logger(__name__)

class StorageRouter:
    """
    Storage router node that distributes memories to appropriate storage adapters based on type and state
    """
    def __init__(self, storage_manager: MemoryStorageManager = None, state_validator=None):
        self.storage_manager = storage_manager
        self.state_validator = state_validator
        self._is_manager_initialized = storage_manager is not None
        logger.info("Storage router initialized")

    async def _ensure_storage_manager(self):
        """Asynchronously initialize storage manager if needed"""
        if not self._is_manager_initialized:
            self.storage_manager = await get_memory_storage_manager_async()
            self._is_manager_initialized = True

    async def run(self, state: MemoryState) -> Dict[str, Any]:
        """Store generated memories to appropriate database based on memory layer and content"""
        logger.info("StorageRouter: Starting storage execution")
        try:
            if self.state_validator:
                errors = self.state_validator.validate_storage_router_input(state)
                if errors:
                    raise ValueError(f"StorageRouter input state validation failed: {errors}")

            await self._ensure_storage_manager()

            generated_memories = state.get("generated_memories", [])
            if not generated_memories:
                logger.warning("No generated memories available for storage")
                state["stored_memories"] = []
                state["storage_results"] = []
                state["success"] = True
                return state

            # Strictly follow upstream generation strategy, no deduplication at this stage
            unique_memories = [m for m in generated_memories if m and get_memory_id(m)]
            if not unique_memories:
                logger.warning("No valid memories available for storage")
                state["stored_memories"] = []
                state["storage_results"] = []
                state["success"] = True
                return state

            logger.info(f"StorageRouter: Number of memories to store: {len(unique_memories)}")

            storage_adapters = state.get("storage_adapters", ["sql", "vector", "cache"])
            
            # Extract ExecutionState from state (if available)
            execution_state = state.get("execution_state", None)
            
            # Pass execution_state to storage manager
            results = await self.storage_manager.batch_store_memories(
                memories=unique_memories,
                storage_types=storage_adapters,
                execution_state=execution_state
            )

            stored_memories = []
            errors = []
            for memory, result in zip(unique_memories, results):
                if result and result.get("success"):
                    stored_memories.append(memory)
                else:
                    errors.append(f"Memory {get_memory_id(memory)} storage failed: {result.get('error', 'Unknown error')}")

            state["stored_memories"] = stored_memories
            state["storage_results"] = results
            
            if errors:
                logger.error(f"Errors in storage operation: {'; '.join(errors)}")
                state["success"] = False
            else:
                state["success"] = True
                logger.info(f"Successfully stored {len(stored_memories)} memories")
            
            return state

        except Exception as e:
            logger.error(f"StorageRouter execution failed: {e}", exc_info=True)
            state["success"] = False
            return state

    async def _check_existing_memory(self, memory: Any) -> bool:
        # Deprecated: no deduplication at this stage
        return False
