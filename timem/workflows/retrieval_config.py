"""
Retrieval workflow configuration specification

Define standard configuration items and deprecated configuration item handling logic to ensure configuration consistency and backward compatibility.
"""

import warnings
from typing import Dict, Any, Tuple, List
from dataclasses import dataclass
from timem.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RetrievalWorkflowConfig:
    """Retrieval workflow configuration data class"""
    
    # ✅ Standard configuration items
    return_memories_only: bool = False
    """
    Whether to only return memories (without generating LLM answer)
    
    - True: Dialogue mode, directly return retrieved memories without calling LLM to generate answer
           Applicable scenario: Dialogue system integration, memories as context passed to dialogue LLM
    - False: QA mode, use LLM to generate answer based on memories
            Applicable scenario: Independent QA service, retrieval workflow generates answer itself
    
    Examples:
        # Dialogue mode
        config = RetrievalWorkflowConfig(return_memories_only=True)
        
        # QA mode
        config = RetrievalWorkflowConfig(return_memories_only=False)
    """


def normalize_retrieval_config(input_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize retrieval configuration, handle backward compatibility and deprecated fields
    
    This function ensures:
    1. Unified use of return_memories_only as standard configuration item
    2. Backward compatibility with skip_llm_generation (deprecated, emit warning)
    3. Handle configuration conflicts (both fields exist and inconsistent)
    
    Args:
        input_config: Original input configuration dictionary
        
    Returns:
        Normalized configuration dictionary, only contains return_memories_only
        
    Examples:
        >>> # Use standard configuration
        >>> config = normalize_retrieval_config({"return_memories_only": True})
        >>> config["return_memories_only"]
        True
        
        >>> # Use deprecated configuration (will emit warning)
        >>> config = normalize_retrieval_config({"skip_llm_generation": True})
        >>> config["return_memories_only"]
        True
        
        >>> # Configuration conflict (prioritize standard configuration)
        >>> config = normalize_retrieval_config({
        ...     "return_memories_only": True,
        ...     "skip_llm_generation": False
        ... })
        >>> config["return_memories_only"]
        True
    """
    config = input_config.copy()
    
    # ⚠️ Backward compatibility: handle deprecated skip_llm_generation
    if "skip_llm_generation" in config:
        skip_llm_value = config["skip_llm_generation"]
        
        if "return_memories_only" not in config:
            # Case 1: Only old configuration, use old configuration value
            config["return_memories_only"] = skip_llm_value
            
            # Emit deprecation warning
            warnings.warn(
                "Configuration item 'skip_llm_generation' is deprecated, please use 'return_memories_only' instead.\n"
                "In v2.0, 'skip_llm_generation' will be removed.\n"
                "Migration method: change skip_llm_generation to return_memories_only",
                DeprecationWarning,
                stacklevel=2
            )
            logger.warning(
                f"Detected deprecated configuration skip_llm_generation={skip_llm_value}, "
                f"automatically converted to return_memories_only={skip_llm_value}"
            )
        else:
            # Case 2: Both exist, check if consistent
            return_memories_value = config["return_memories_only"]
            
            if skip_llm_value != return_memories_value:
                # Configuration conflict: emit warning and prioritize standard configuration
                warnings.warn(
                    f"Configuration conflict: skip_llm_generation={skip_llm_value} "
                    f"inconsistent with return_memories_only={return_memories_value}. "
                    f"Will use return_memories_only={return_memories_value}.",
                    UserWarning,
                    stacklevel=2
                )
                logger.warning(
                    f"Configuration conflict: prioritize return_memories_only={return_memories_value}"
                )
            else:
                # Both values consistent, only log (no warning to avoid noise)
                logger.debug(
                    f"Detected redundant configuration: skip_llm_generation and return_memories_only "
                    f"values consistent ({skip_llm_value}), recommend removing skip_llm_generation"
                )
        
        # Remove deprecated field (no longer used internally)
        del config["skip_llm_generation"]
    
    # Ensure return_memories_only exists
    if "return_memories_only" not in config:
        config["return_memories_only"] = False  # Default value: QA mode
        logger.debug("return_memories_only not specified, using default value: False (QA mode)")
    
    return config


def should_skip_llm_generation(state: Dict[str, Any]) -> bool:
    """
    Determine whether to skip LLM generation (unified judgment logic)
    
    This is a globally unified judgment function, all places that need to check this configuration should use this function.
    
    Args:
        state: Workflow state dictionary
        
    Returns:
        True: Skip LLM generation, only return memories
        False: Use LLM to generate answer
        
    Examples:
        >>> state = {"return_memories_only": True}
        >>> should_skip_llm_generation(state)
        True
        
        >>> state = {"return_memories_only": False}
        >>> should_skip_llm_generation(state)
        False
        
        >>> # Backward compatible with old configuration
        >>> state = {"skip_llm_generation": True}
        >>> should_skip_llm_generation(state)
        True
    """
    # Normalize configuration (handle backward compatibility)
    normalized = normalize_retrieval_config(state)
    
    # Return standard configuration value
    return normalized.get("return_memories_only", False)


def get_retrieval_mode_description(return_memories_only: bool) -> str:
    """
    Get description text of retrieval mode
    
    Args:
        return_memories_only: Configuration value
        
    Returns:
        Mode description text
    """
    if return_memories_only:
        return "Dialogue mode (return memories only)"
    else:
        return "QA mode (generate answer)"


# Configuration validation function
def validate_retrieval_config(config: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate the validity of retrieval configuration
    
    Args:
        config: Configuration dictionary
        
    Returns:
        (is_valid, errors): Validation result and error list
    """
    errors = []
    
    # Check return_memories_only type
    if "return_memories_only" in config:
        value = config["return_memories_only"]
        if not isinstance(value, bool):
            errors.append(
                f"return_memories_only must be boolean, current type: {type(value).__name__}"
            )
    
    # Check deprecated fields
    if "skip_llm_generation" in config:
        # This is not an error, just will emit a warning
        pass
    
    is_valid = len(errors) == 0
    return is_valid, errors


# Export configuration constants
class RetrievalMode:
    """Retrieval mode constants"""
    DIALOGUE = True   # Dialogue mode: return memories only
    QA = False        # QA mode: generate answer

