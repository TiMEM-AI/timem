"""
TiMem Core Engine Package
"""

# Version information
__version__ = "1.0.0"

# Lazy imports to avoid circular dependencies
def _import_core_modules():
    """Lazy import core modules"""
    from .utils.logging import get_logger, init_logging
    from .memory.memory_generator import MemoryGenerator
    from .workflows.memory_generation import MemoryGenerationWorkflow, run_memory_generation
    from storage.memory_storage_manager import get_memory_storage_manager_async
    
    return get_logger, init_logging, MemoryGenerator, MemoryGenerationWorkflow, run_memory_generation, get_memory_storage_manager_async

# Convenience access functions
def get_logger(name: str):
    """Get logger (lazy initialization)"""
    from .utils.logging import get_logger as _get_logger
    return _get_logger(name)

def init_logging():
    """Initialize logging system (lazy initialization)"""
    from .utils.logging import init_logging as _init_logging
    return _init_logging()

def get_memory_generator():
    """Get memory generator (lazy initialization)"""
    from .memory.memory_generator import MemoryGenerator
    return MemoryGenerator()

def get_memory_generation_workflow():
    """Get memory generation workflow (lazy initialization)"""
    from .workflows.memory_generation import MemoryGenerationWorkflow
    return MemoryGenerationWorkflow()

def run_memory_generation(input_data):
    """Run memory generation (lazy initialization)"""
    from .workflows.memory_generation import run_memory_generation as _run_memory_generation
    return _run_memory_generation(input_data)

def get_storage_manager():
    """Get storage manager (lazy initialization)"""
    from storage.memory_storage_manager import get_memory_storage_manager_async
    import asyncio
    
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(get_memory_storage_manager_async())

# Export main interfaces
__all__ = [
    "get_logger",
    "init_logging",
    "get_memory_generator",
    "get_memory_generation_workflow",
    "run_memory_generation",
    "get_storage_manager",
    # Cloud SDK
    "AsyncMemory",
]

# Lazy import for AsyncMemory to avoid circular dependencies
def _get_async_memory():
    """Get AsyncMemory class (lazy initialization)"""
    from .cloud.async_memory import AsyncMemory
    return AsyncMemory

# AsyncMemory compatibility
def __getattr__(name: str):
    if name == "AsyncMemory":
        return _get_async_memory()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")