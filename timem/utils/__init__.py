"""
TiMem utilities module
"""

# Lazy imports to avoid circular dependencies and startup delays
def get_logger(name: str):
    """Get logger (lazy import)"""
    from .logging import get_logger as _get_logger
    return _get_logger(name)

def get_current_timestamp():
    """Get current timestamp (lazy import)"""
    from .time_utils import get_current_timestamp as _get_current_timestamp
    return _get_current_timestamp()

def get_text_processor():
    """Get text processor (lazy import)"""
    from .text_processing import TextProcessor
    return TextProcessor()

def get_config(section=None):
    """Get configuration (lazy import)"""
    from .config_manager import get_config as _get_config
    return _get_config(section)

def reload_config():
    """Reload configuration (lazy import)"""
    from .config_manager import reload_config as _reload_config
    return _reload_config()

def get_app_config():
    """Get application configuration (lazy import)"""
    from .config_manager import get_app_config as _get_app_config
    return _get_app_config()

def get_storage_config():
    """Get storage configuration (lazy import)"""
    from .config_manager import get_storage_config as _get_storage_config
    return _get_storage_config()

def get_llm_config():
    """Get LLM configuration (lazy import)"""
    from .config_manager import get_llm_config as _get_llm_config
    return _get_llm_config()

def get_prompts_config():
    """Get prompts configuration (lazy import)"""
    from .config_manager import get_prompts_config as _get_prompts_config
    return _get_prompts_config()

def get_prompt_manager():
    """Get prompt manager (lazy import)"""
    from .prompt_manager import get_prompt_manager as _get_prompt_manager
    return _get_prompt_manager()

def get_time_parser():
    """Get time parser (lazy import)"""
    from .time_parser import time_parser as _time_parser
    return _time_parser

__all__ = [
    "get_logger",
    "get_current_timestamp", 
    "get_text_processor",
    "get_config",
    "reload_config",
    "get_app_config",
    "get_storage_config",
    "get_llm_config",
    "get_prompts_config",
    "get_prompt_manager",
    "get_time_parser"
] 