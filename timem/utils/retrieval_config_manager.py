"""
Retrieval Configuration Manager

Responsible for loading and managing configuration files for TiMem memory retrieval system,
providing a unified configuration access interface.
"""

import os
import yaml
from typing import Dict, Any, Optional
from pathlib import Path

from timem.utils.logging import get_logger
from timem.utils.config_manager import get_app_config

logger = get_logger(__name__)


class RetrievalConfigManager:
    """Retrieval configuration manager"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize retrieval configuration manager
        
        Args:
            config_path: Configuration file path, if None use default path
        
        Priority:
        1. Passed config_path parameter
        2. Environment variable TIMEM_RETRIEVAL_CONFIG_PATH (for ablation experiments)
        3. Default path
        """
        import os
        
        # Support environment variable to specify config path (for complete isolation of ablation experiments)
        env_config_path = os.environ.get('TIMEM_RETRIEVAL_CONFIG_PATH')
        
        if config_path:
            self.config_path = config_path
            logger.info(f"Using passed config path: {config_path}")
        elif env_config_path:
            self.config_path = env_config_path
            logger.info(f"Loading config from environment variable: {env_config_path}")
        else:
            self.config_path = self._get_default_config_path()
            # logger.info already printed in _get_default_config_path
        
        self._config = None
        self._load_config()
    
    def _get_default_config_path(self) -> str:
        """
        Get default configuration file path
        
        Priority:
        1. Dataset-specific config: config/datasets/{dataset_name}/retrieval_config.yaml
        2. Global config: config/retrieval_config.yaml
        """
        # Get project root directory from application config
        app_config = get_app_config()
        project_root = app_config.get("project_root", os.getcwd())
        
        # Prioritize using dataset-specific config
        try:
            from timem.utils.dataset_profile_manager import get_dataset_profile_manager
            profile_manager = get_dataset_profile_manager()
            dataset_name = profile_manager.current_profile_name
            
            # Check if there is a custom config path
            current_profile = profile_manager.current_profile
            # Try to get directly (for backward compatibility)
            config_location = current_profile.get('config_location')
            # If not, try to get from metadata
            if not config_location:
                config_location = current_profile.get('metadata', {}).get('config_location')
            
            if config_location:
                # If config_location is defined, use that path
                # Note: config_location is usually relative to project root
                dataset_config_dir = os.path.join(project_root, config_location)
                logger.debug(f"Using custom dataset config path: {dataset_config_dir} (from config_location)")
            else:
                # Default to config/datasets/{dataset_name}
                dataset_config_dir = os.path.join(project_root, "config", "datasets", dataset_name)
            
            # Build dataset-specific config path
            dataset_config = os.path.join(dataset_config_dir, "retrieval_config.yaml")
            
            if os.path.exists(dataset_config):
                logger.info(f"Using dataset-specific retrieval config: {dataset_name} ({dataset_config})")
                return dataset_config
            else:
                logger.debug(f"Dataset-specific retrieval config does not exist: {dataset_config}")
        except Exception as e:
            logger.debug(f"Unable to get dataset information, using global config: {e}")
        
        # Fallback to global config file path
        config_path = os.path.join(project_root, "config", "retrieval_config.yaml")
        
        # If config file does not exist, try other possible locations
        if not os.path.exists(config_path):
            # Try config folder in current directory
            current_config = os.path.join("config", "retrieval_config.yaml")
            if os.path.exists(current_config):
                config_path = current_config
            else:
                # Try config folder in parent directory
                parent_config = os.path.join("..", "config", "retrieval_config.yaml")
                if os.path.exists(parent_config):
                    config_path = parent_config
        
        return config_path
    
    def _load_config(self):
        """Load configuration file"""
        try:
            if not os.path.exists(self.config_path):
                logger.warning(f"Retrieval config file does not exist: {self.config_path}")
                logger.info("Using built-in default config (with memory refiner enabled)")
                self._config = self._get_default_config()
                return
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f)
            
            logger.info(f"Successfully loaded retrieval config file: {self.config_path}")
            
            # Diagnostic log: show memory refiner status
            refiner_config = self._config.get("memory_refiner", {})
            is_enabled = refiner_config.get("enabled", False)
            logger.info(f"Memory refiner status: {'Enabled' if is_enabled else 'Disabled'}")
            
        except Exception as e:
            logger.error(f"Failed to load retrieval config file: {str(e)}")
            logger.info("Using built-in default config (with memory refiner enabled)")
            self._config = self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default config - structure consistent with retrieval_config.yaml"""
        return {
            "retrieval": {
                "use_v2_retrievers": True,
                "max_execution_time": 30,
                "semantic": {
                    "weight": 0.9,
                    "score_threshold": 0.0  # Adjust to lowest threshold to ensure all questions match
                },
                "keyword": {
                    "weight": 0.1,
                    "bm25_k1": 1.5,
                    "bm25_b": 0.75
                }
            },
            "retrieval_strategies": {
                "simple": {
                    "description": "Simple retrieval: L1(top40 coarse ranking+top10 fine ranking) + L2(top1)",
                    "layers": ["L1", "L2"],
                    "layer_limits": {
                        "L1": 40,
                        "L2": 2
                    },
                    "final_limits": {
                        "L1": 20,
                        "L2": 1
                    },
                    "use_cases": ["Fact queries", "Direct information retrieval"]
                },
                "hybrid": {
                    "description": "Hybrid retrieval: L1(top40 coarse ranking+top10 fine ranking) + L2(top1) + L3(top1) + L4(top1)",
                    "layers": ["L1", "L2", "L3", "L4"],
                    "layer_limits": {
                        "L1": 40,
                        "L2": 2,
                        "L3": 1,
                        "L4": 1
                    },
                    "final_limits": {
                        "L1": 20,
                        "L2": 2,
                        "L3": 1,
                        "L4": 1
                    },
                    "use_cases": ["Correlation analysis", "Pattern recognition", "Medium complexity queries"]
                },
                "complex": {
                    "description": "Complex retrieval: L1(top40 coarse ranking+top10 fine ranking) + L3(top2) + L4(top1) + L5(top1)",
                    "layers": ["L1", "L3", "L4", "L5"],
                    "layer_limits": {
                        "L1": 40,
                        "L3": 2,
                        "L4": 2,
                        "L5": 1
                    },
                    "final_limits": {
                        "L1": 20,
                        "L3": 2,
                        "L4": 1,
                        "L5": 1
                    },
                    "use_cases": ["Deep analysis", "Complex reasoning", "Advanced pattern matching"]
                }
            },
            "memory_refiner": {
                "enabled": True,  # Default enable memory refiner
                "llm_model": "gpt-4o-mini",
                "llm_provider": "openai",
                "temperature": 0.3,
                "max_tokens": 1024,
                "timeout": 30,
                "strategy_aware": True,
                "prompt_config": {
                    "include_reasoning": True,
                    "show_memory_metadata": True
                },
                "prompt_templates": {
                    "complexity_0": "memory_refiner_simple",
                    "complexity_1": "memory_refiner_hybrid",
                    "complexity_2": "memory_refiner_complex"
                },
                "retry": {
                    "max_retries": 3,
                    "fallback_on_error": True,
                    "retry_on_empty": True,
                    "retry_on_parse_error": True
                },
                "empty_result_protection": {
                    "enabled": True,
                    "min_original_count": 3,
                    "fallback_count": 5
                }
            },
            "answer_generation": {
                "mode": "single",
                "single_cot": {
                    "enabled": True,
                    "llm_model": "gpt-4o-mini",
                    "temperature": 0.7,
                    "max_tokens": 2048,
                    "max_retries": 3,
                    "strict_format": True,
                    "retry_prompt_enhancement": True
                },
                "multi_stage_cot": {
                    "enabled": False,
                    "fallback_to_single_stage": True,
                    "stage1_llm_model": "gpt-4o-mini",
                    "stage2_llm_model": "gpt-4o-mini",
                    "stage3_llm_model": "gpt-4o-mini",
                    "timeout_per_stage": 60,
                    "max_retry_on_parse_error": 3,
                    "enable_stage_caching": False
                }
            }
        }
    
    def get_config(self) -> Dict[str, Any]:
        """Get complete config"""
        return self._config
    
    def get_retrieval_config(self) -> Dict[str, Any]:
        """Get retrieval config"""
        return self._config.get("retrieval", {})
    
    def get_strategy_config(self, strategy_name: str) -> Dict[str, Any]:
        """Get config for specific strategy"""
        retrieval_strategies = self._config.get("retrieval_strategies", {})
        return retrieval_strategies.get(strategy_name, {})
    
    def get_layer_limit(self, strategy_name: str, layer: str) -> int:
        """Get retrieval count limit for specific strategy and layer"""
        strategy_config = self.get_strategy_config(strategy_name)
        layer_limits = strategy_config.get("layer_limits", {})
        return layer_limits.get(layer, 0)
    
    def get_layer_final_limit(self, strategy_name: str, layer: str) -> int:
        """Get final result count limit for specific strategy and layer"""
        strategy_config = self.get_strategy_config(strategy_name)
        final_limits = strategy_config.get("final_limits", {})
        return final_limits.get(layer, 5 if layer == "L1" else 3)
    
    def get_all_layer_final_limits(self, strategy_name: str) -> Dict[str, int]:
        """Get final result count limits for all layers of specific strategy"""
        strategy_config = self.get_strategy_config(strategy_name)
        final_limits = strategy_config.get("final_limits", {})
        return final_limits.copy()
    
    def get_max_execution_time(self) -> int:
        """Get maximum execution time"""
        return self._config.get("retrieval", {}).get("max_execution_time", 30)
    
    def get_semantic_config(self) -> Dict[str, Any]:
        """Get semantic retrieval config"""
        return self._config.get("retrieval", {}).get("semantic", {})
    
    def get_keyword_config(self) -> Dict[str, Any]:
        """Get keyword retrieval config"""
        return self._config.get("retrieval", {}).get("keyword", {})
    
    def is_v2_retrievers_enabled(self) -> bool:
        """Check if retrievers are enabled"""
        return self._config.get("retrieval", {}).get("use_v2_retrievers", True)
    
    def reload_config(self):
        """Reload configuration file"""
        logger.info("Reloading retrieval config file")
        self._load_config()
    
    def override_config(self, new_config: Dict[str, Any]):
        """
        Override current config (for ablation experiments)
        
        Args:
            new_config: New complete config dictionary
        """
        logger.info("Overriding retrieval config (ablation experiment mode)")
        self._config = new_config
        logger.info("Config overridden")
    
    def validate_config(self) -> bool:
        """Validate config validity"""
        try:
            # Check required config sections
            required_sections = ["retrieval", "retrieval_strategies"]
            for section in required_sections:
                if section not in self._config:
                    logger.error(f"Missing required config section: {section}")
                    return False
            
            # Check retrieval config
            retrieval = self._config.get("retrieval", {})
            required_retrieval = ["use_v2_retrievers", "max_execution_time", "semantic", "keyword"]
            for item in required_retrieval:
                if item not in retrieval:
                    logger.error(f"Retrieval config missing: {item}")
                    return False
            
            # Check strategy config
            strategies = self._config.get("retrieval_strategies", {})
            required_strategies = ["simple", "hybrid", "complex"]
            for strategy in required_strategies:
                if strategy not in strategies:
                    logger.error(f"Missing strategy config: {strategy}")
                    return False
                
                strategy_config = strategies[strategy]
                required_strategy_items = ["layers", "layer_limits", "final_limits"]
                for item in required_strategy_items:
                    if item not in strategy_config:
                        logger.error(f"Strategy {strategy} config missing: {item}")
                        return False
            
            logger.info("Retrieval config validation passed")
            return True
            
        except Exception as e:
            logger.error(f"Config validation failed: {str(e)}")
            return False


# Global config manager instance
_retrieval_config_manager = None
_last_config_path = None  # Record last used config path


def get_retrieval_config_manager(config_path: Optional[str] = None, force_reinit: bool = False) -> RetrievalConfigManager:
    """
    Get retrieval config manager instance
    
    Args:
        config_path: Configuration file path, if None use default path
        force_reinit: Whether to force re-initialization (use when switching configs in ablation experiments)
        
    Returns:
        Retrieval config manager instance
    """
    import os
    global _retrieval_config_manager, _last_config_path
    
    # Check environment variable config path (for ablation experiment isolation)
    env_config_path = os.environ.get('TIMEM_RETRIEVAL_CONFIG_PATH')
    current_config_path = config_path or env_config_path or None
    
    # If config path changes or force re-initialization, recreate instance
    if force_reinit or (_last_config_path != current_config_path and current_config_path is not None):
        if _retrieval_config_manager is not None:
            logger.info(f"Config path changed, re-initializing config manager")
            logger.info(f"   Old path: {_last_config_path}")
            logger.info(f"   New path: {current_config_path}")
        _retrieval_config_manager = None
        _last_config_path = current_config_path
    
    if _retrieval_config_manager is None:
        _retrieval_config_manager = RetrievalConfigManager(config_path)
    
    return _retrieval_config_manager


def get_retrieval_config() -> Dict[str, Any]:
    """
    Convenience function to get retrieval config
    
    Returns:
        Retrieval config dictionary
    """
    return get_retrieval_config_manager().get_config()
