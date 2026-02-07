"""
Configuration context manager - Engineering-level configuration isolation solution

Core principles:
1. Configuration loaded only once during initialization
2. Configuration immutable after loading (frozen)
3. Each instance independent, no shared state
4. Resource cleanup ensured through context manager

Usage:
    # Ablation experiment mode
    with RetrievalConfigContext(config_path="config/ablation/e1.1/retrieval_config.yaml") as config:
        workflow = create_workflow(config)
        result = await workflow.run(input_data)
    
    # Normal mode
    with RetrievalConfigContext() as config:
        workflow = create_workflow(config)
        result = await workflow.run(input_data)
"""

import os
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class FrozenDict(dict):
    """Immutable dictionary - Prevent configuration from being accidentally modified"""
    
    def __setitem__(self, key, value):
        raise RuntimeError("Configuration is frozen and cannot be modified")
    
    def __delitem__(self, key):
        raise RuntimeError("Configuration is frozen and cannot be deleted")
    
    def clear(self):
        raise RuntimeError("Configuration is frozen and cannot be cleared")
    
    def pop(self, *args):
        raise RuntimeError("Configuration is frozen and cannot pop")
    
    def popitem(self):
        raise RuntimeError("Configuration is frozen and cannot popitem")
    
    def setdefault(self, *args):
        raise RuntimeError("Configuration is frozen and cannot setdefault")
    
    def update(self, *args, **kwargs):
        raise RuntimeError("Configuration is frozen and cannot update")


class RetrievalConfigContext:
    """
    Retrieval configuration context manager
    
    Features:
    - Configuration automatically frozen after loading
    - Support context manager protocol
    - Each instance independent, no shared state
    - Automatic resource cleanup
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration context
        
        Args:
            config_path: Configuration file path (absolute or relative path)
                        If None, use default path
        """
        self.config_path = config_path
        self._config: Optional[Dict[str, Any]] = None
        self._frozen = False
        
    def __enter__(self):
        """Enter context: load and freeze configuration"""
        self._load_config()
        self._freeze_config()
        logger.info(f"✅ Configuration context created and frozen: {self.config_path}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context: clean up resources"""
        logger.info(f"🔒 Configuration context closed: {self.config_path}")
        return False
    
    def _get_default_config_path(self) -> str:
        """Get default configuration path"""
        # Get project root directory from application configuration
        from timem.utils.config_manager import get_app_config
        app_config = get_app_config()
        project_root = app_config.get("project_root", os.getcwd())
        
        # Prioritize dataset-specific configuration
        try:
            from timem.utils.dataset_profile_manager import get_dataset_profile_manager
            profile_manager = get_dataset_profile_manager()
            dataset_name = profile_manager.current_profile_name
            
            dataset_config = os.path.join(
                project_root, "config", "datasets", dataset_name, "retrieval_config.yaml"
            )
            
            if os.path.exists(dataset_config):
                logger.info(f"📄 Using dataset-specific retrieval config: {dataset_name}")
                return dataset_config
        except Exception as e:
            logger.debug(f"Cannot get dataset-specific config: {e}")
        
        # Fall back to global configuration
        global_config = os.path.join(project_root, "config", "retrieval_config.yaml")
        logger.info(f"📄 Using global retrieval config")
        return global_config
    
    def _load_config(self):
        """Load configuration file"""
        if self._config is not None:
            logger.warning("⚠️ Configuration already loaded, skipping duplicate load")
            return
        
        # Determine configuration file path
        if self.config_path:
            config_file = Path(self.config_path).resolve()
            logger.info(f"🔧 Loading specified config: {config_file}")
        else:
            config_file = Path(self._get_default_config_path()).resolve()
            logger.info(f"📄 Loading default config: {config_file}")
        
        # Verify file exists
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_file}")
        
        # Load YAML configuration
        with open(config_file, 'r', encoding='utf-8') as f:
            self._config = yaml.safe_load(f)
        
        logger.info(f"✅ Configuration loaded: {config_file}")
        logger.info(f"   - Retrieval strategies: {list(self._config.get('retrieval_strategies', {}).keys())}")
        logger.info(f"   - Memory refiner: {'Enabled' if self._config.get('memory_refiner', {}).get('enabled') else 'Disabled'}")
        
        # Save configuration file path (for logging)
        self.config_path = str(config_file)
    
    def _freeze_config(self):
        """Freeze configuration to make it immutable"""
        if self._frozen:
            return
        
        def freeze_dict(d):
            """Recursively freeze dictionary"""
            frozen = {}
            for key, value in d.items():
                if isinstance(value, dict):
                    frozen[key] = freeze_dict(value)
                elif isinstance(value, list):
                    frozen[key] = tuple(freeze_dict(item) if isinstance(item, dict) else item for item in value)
                else:
                    frozen[key] = value
            return FrozenDict(frozen)
        
        self._config = freeze_dict(self._config)
        self._frozen = True
        logger.info("🔒 Configuration frozen (immutable)")
    
    def get_config(self) -> Dict[str, Any]:
        """Get complete configuration (read-only)"""
        if self._config is None:
            raise RuntimeError("Configuration not loaded, please enter context first")
        return self._config
    
    def get_retrieval_config(self) -> Dict[str, Any]:
        """Get retrieval configuration"""
        return self.get_config().get("retrieval", {})
    
    def get_strategy_config(self, strategy_name: str) -> Dict[str, Any]:
        """Get specific strategy configuration"""
        retrieval_strategies = self.get_config().get("retrieval_strategies", {})
        return retrieval_strategies.get(strategy_name, {})
    
    def get_memory_refiner_config(self) -> Dict[str, Any]:
        """Get memory refiner configuration"""
        return self.get_config().get("memory_refiner", {})
    
    def get_answer_generation_config(self) -> Dict[str, Any]:
        """Get answer generation configuration"""
        return self.get_config().get("answer_generation", {})

