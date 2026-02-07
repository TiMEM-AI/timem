"""
Error Handler Node

Handles errors that may occur in the workflow
"""
from typing import Dict, List, Any, Optional
import traceback
from datetime import datetime

from timem.workflows.state import MemoryState
from timem.utils.logging import get_logger

logger = get_logger(__name__)


class ErrorHandler:
    """Error handler node that handles errors that may occur in the workflow"""
    
    def __init__(self):
        """Initialize error handler node"""
        logger.info("Error handler node initialized")
    
    async def run(self, state: MemoryState) -> MemoryState:
        """Handle errors that may occur in the workflow"""
        print(f"\n{'='*60}")
        print(f"🆘 ErrorHandler starting execution")
        logger.info("ErrorHandler: Starting error handling")

        all_errors = state.get("error", "")
        if isinstance(all_errors, str):
            all_errors = [e for e in all_errors.split('|') if e]
        elif all_errors is None:
            all_errors = []

        print(f"  - [Info] Initially found {len(all_errors)} errors")
        
        # Check and log generated memories even if there are errors
        generated_memories = state.get("generated_memories", [])
        if generated_memories:
            print(f"  - [Info] Found {len(generated_memories)} generated memories (even in error flow)")
            logger.info(f"ErrorHandler: Found {len(generated_memories)} generated memories despite errors.")
            for i, mem_obj in enumerate(generated_memories):
                # Access Pydantic object attributes directly, no longer use .get()
                if hasattr(mem_obj, 'id') and hasattr(mem_obj, 'level'):
                    print(f"    - Memory {i+1}: ID={mem_obj.id}, Level={mem_obj.level.value}")
                else:
                    print(f"    - Memory {i+1}: Invalid memory object")

        # Set final error message
        final_error_message = "; ".join(all_errors)
        state["error"] = final_error_message
        print(f"  - [Final Error Summary] {final_error_message}")
        
        print(f"ErrorHandler execution completed")
        print(f"{'='*60}")
        return state

# Compatible with old version LangGraph error handling interface
def run(self, state: MemoryState, error: Exception = None) -> MemoryState:
    """
    Handle errors during workflow execution (compatible with old LangGraph version)
    
    Args:
        state: Workflow state
        error: Caught exception
        
    Returns:
        Updated workflow state containing error information
    """
    logger.info("Executing error handling (compatibility mode)")
    
    if error:
        # Update error information in state
        error_msg = f"Workflow execution error: {str(error)}"
        logger.error(error_msg)
        print(f"❌ Error handling: {error_msg}")
        
        # Get detailed error information
        import traceback
        stack_trace = traceback.format_exc()
        logger.error(stack_trace)
        print(f"❌ Error stack: {stack_trace}")
        
        state = state.copy() if isinstance(state, dict) else {}
        state["exception"] = error
        state["traceback"] = stack_trace
        state["validation_passed"] = False
        state["error"] = str(error)
    
    # Use async method to handle errors
    # Note: In sync context, we cannot directly await
    try:
        import asyncio
        # Check if in event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return {
                    "status": "error",
                    "success": False,
                    "memory_layer": "error",
                    "memory_id": "",
                    "errors": [str(error)] if error else [],
                    "timestamp": datetime.now().isoformat(),
                    "memory_count": 0,
                    "memory_layers": [],
                    "memory_ids": []
                }
        except RuntimeError:
            # No running event loop
            pass
    except Exception as e:
        logger.error(f"Error occurred while handling error: {e}")
    
    # Build standardized error response
    response = {
        "status": "error",
        "success": False,
        "memory_layer": "error",
        "memory_id": "",
        "errors": [str(error)] if error else [],
        "timestamp": datetime.now().isoformat(),
        "memory_count": 0,
        "memory_layers": [],
        "memory_ids": []
    }
    
    # Preserve some key fields from original state
    if isinstance(state, dict):
        for field in ["session_id", "user_id", "expert_id", "content", "timestamp"]:
            if field in state:
                response[field] = state[field]
    
    logger.info("Error handling completed, returning standardized error response")
    print(f"✓ Error handling completed, returning standardized error response")
    
    return response