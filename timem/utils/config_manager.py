"""
TiMem Configuration Manager
- Support loading configuration from multiple YAML files.
- Support referencing environment variables in YAML using `${VAR_NAME}` format.
"""

import os
import re
import yaml
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional
from dotenv import load_dotenv

# WARNING: Load environment variables from .env file before loading ConfigManager
_env_path = Path(__file__).parent.parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path, override=True)

# Configure standard logging to avoid circular dependencies
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Define a global variable to hold ConfigManager singleton
_config_manager_instance = None


class ConfigManager:
    """
    Configuration manager class that encapsulates all configuration loading and access logic.
    This is a singleton pattern implementation to ensure the entire application shares one config instance.
    """
    _instance = None
    _config_cache: Dict[str, Any] = {}

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(ConfigManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, settings_file: Optional[Path] = None, prompts_file: Optional[Path] = None):
        """
        Initialize the configuration manager.

        Args:
            settings_file: Path to settings.yaml file. If None, use default path.
            prompts_file: Path to prompts.yaml file. If None, use default path.
        """
        # Prevent duplicate initialization
        if hasattr(self, '_initialized') and self._initialized:
            return
        
        logger.info("Initializing configuration manager...")
        
        # Try to import python-dotenv and load .env file
        self._load_dotenv()

        # Define configuration file paths
        self.config_dir = Path(__file__).parent.parent.parent / "config"
        self.settings_file = settings_file or self.config_dir / "settings.yaml"
        self.prompts_file = prompts_file or self.config_dir / "prompts.yaml"
        
        # NEW: Dataset-specific configuration directory
        self.datasets_config_dir = self.config_dir / "datasets"

        # Initialize config cache as empty dict to avoid accessing empty cache in reload_config
        self._config_cache = {}
        
        self.reload_config()
        self._initialized = True

    def _load_dotenv(self):
        """Load .env file"""
        try:
            from dotenv import load_dotenv
            env_file = Path(__file__).parent.parent.parent / ".env"
            if env_file.exists():
                load_dotenv(env_file)
                logger.info(f"Loaded environment variables file: {env_file}")
            else:
                logger.debug(f".env file not found: {env_file}")
        except ImportError:
            logger.debug("python-dotenv not installed, skipping .env file loading")

    def _substitute_env_vars(self, raw_config: Any) -> Any:
        """Recursively substitute environment variables in configuration"""
        if isinstance(raw_config, dict):
            return {k: self._substitute_env_vars(v) for k, v in raw_config.items()}
        if isinstance(raw_config, list):
            return [self._substitute_env_vars(i) for i in raw_config]
        if isinstance(raw_config, str):
            pattern = r'\$\{([^}]+)\}'
            def replace_var(match):
                var_expr = match.group(1)
                var_name, _, default_value = var_expr.partition(':')
                return os.getenv(var_name.strip(), default_value.strip() or None)
            return re.sub(pattern, replace_var, raw_config)
        return raw_config
    
    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deep merge two dictionaries, override overwrites base
        
        Args:
            base: Base configuration dictionary
            override: Override configuration dictionary
        
        Returns:
            Merged dictionary
        """
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    
    def _load_dataset_config(self, config_type: str) -> Dict[str, Any]:
        """
        Load dataset-specific configuration with full inheritance support
        
        Inheritance rules:
        1. First load global configuration (config/{config_type}.yaml)
        2. Then load dataset-specific configuration (config/datasets/{dataset_name}/{config_type}.yaml)
        3. Deep merge: dataset configuration overrides global configuration
        
        Args:
            config_type: Configuration file type (without .yaml suffix)
        
        Returns:
            Merged configuration dictionary
        """
        # Load global configuration
        global_config_path = self.config_dir / f"{config_type}.yaml"
        global_config = self._load_yaml_file(global_config_path)
        
        # Get current dataset
        try:
            from timem.utils.dataset_profile_manager import get_dataset_profile_manager
            profile_manager = get_dataset_profile_manager()
            dataset_name = profile_manager.current_profile_name
            
            # NEW: Check for custom configuration path
            current_profile = profile_manager.current_profile
            # Try direct access (backward compatible)
            config_location = current_profile.get('config_location')
            # If not, try to get from metadata
            if not config_location:
                config_location = current_profile.get('metadata', {}).get('config_location')
            
            if config_location:
                # If config_location is defined, use that path (relative to project root)
                project_root = self.config_dir.parent
                dataset_config_dir = project_root / config_location
                logger.debug(f"Using custom dataset config path: {dataset_config_dir} (from config_location)")
            else:
                # Default to config/datasets/{dataset_name}
                dataset_config_dir = self.datasets_config_dir / dataset_name
                
        except Exception as e:
            logger.debug(f"Unable to get dataset information, using global configuration: {e}")
            return global_config
        
        # Load dataset-specific configuration
        dataset_config_path = dataset_config_dir / f"{config_type}.yaml"
        
        if not dataset_config_path.exists():
            logger.debug(f"Dataset-specific configuration does not exist: {dataset_config_path}, using global configuration")
            return global_config
        
        dataset_config = self._load_yaml_file(dataset_config_path)
        
        # If dataset configuration is empty, directly return global configuration
        if not dataset_config:
            logger.info(f"📄 {config_type}.yaml: Using global configuration (dataset configuration is empty)")
            return global_config
        
        # Deep merge configurations
        merged_config = self._deep_merge(global_config, dataset_config)
        logger.info(f"📄 {config_type}.yaml: Global configuration + {dataset_name} dataset override")
        
        return merged_config

    @lru_cache(maxsize=2)  # Cache settings and prompts files
    def _load_yaml_file(self, file_path: Path) -> Dict[str, Any]:
        """Load and parse a single YAML file"""
        if not file_path.exists():
            logger.warning(f"Configuration file not found: {file_path}")
            return {}
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_config = yaml.safe_load(f) or {}
            return self._substitute_env_vars(raw_config)
        except Exception as e:
            logger.error(f"Failed to load or parse configuration file {file_path}: {e}", exc_info=True)
            return {}

    def reload_config(self):
        """Reload all configuration files and clear cache"""
        logger.info("Reloading configuration...")
        self._config_cache.clear()
        self._load_yaml_file.cache_clear()
        
        # Load settings (no dataset-specific version needed)
        settings = self._load_yaml_file(self.settings_file)
        
        # NEW: Load prompt configuration (supports dataset-specific version)
        logger.info("📚 Loading dataset-specific configuration...")
        prompts = self._load_dataset_config("prompts")
        qa_prompts = self._load_dataset_config("qa_prompts")
        multi_stage_qa_prompts = self._load_dataset_config("multi_stage_qa_prompts")
        eval_prompts = self._load_dataset_config("eval_prompt")
        
        # Merge all configurations
        self._config_cache = {
            **settings,
            "prompts": prompts,
            "qa_prompts": qa_prompts,
            "multi_stage_qa_prompts": multi_stage_qa_prompts,
            "eval_prompts": eval_prompts
        }
        
        # TOOL: Clear cache for convenience access functions (only clear cached ones)
        self.get_config.cache_clear()
        self.get_app_config.cache_clear()
        # Note: get_storage_config, get_llm_config, etc. have cache decorators removed, no need to clear
        
        # 🆕 Apply dataset configuration overrides (storage and LLM configuration)
        self._apply_dataset_profile_overrides()
        
        # TOOL: Clear cache again to ensure overridden configuration takes effect immediately
        self.get_config.cache_clear()
        self.get_app_config.cache_clear()
        
        # 🔧 Key fix: Clear LLM manager cache to ensure LLM provider override takes effect
        try:
            from llm.llm_manager import _get_llm_cached
            _get_llm_cached.cache_clear()
            logger.info("✅ Cleared LLM manager cache to ensure provider override takes effect")
        except Exception as e:
            logger.debug(f"Failed to clear LLM cache (may not be imported): {e}")
        
        logger.info("✅ Configuration successfully reloaded")
    
    def _apply_dataset_profile_overrides(self):
        """Apply dataset configuration overrides (if exist)"""
        try:
            # Delayed import to avoid circular dependency
            from timem.utils.dataset_profile_manager import get_dataset_profile_manager
            
            profile_manager = get_dataset_profile_manager()
            
            # Get storage configuration overrides
            storage_overrides = profile_manager.get_storage_config_overrides()
            
            # Get LLM configuration overrides
            llm_overrides = profile_manager.get_llm_config_overrides()
            
            # Merge all overrides
            all_overrides = {**storage_overrides, **llm_overrides}
            
            if not all_overrides:
                logger.debug("No dataset configuration overrides to apply")
                return
            
            # Ensure storage configuration exists
            if 'storage' not in self._config_cache:
                self._config_cache['storage'] = {}
            
            # Ensure llm configuration exists
            if 'llm' not in self._config_cache:
                self._config_cache['llm'] = {}
            
            # Apply override configuration
            for key_path, value in all_overrides.items():
                self._set_config_value(key_path, value)
                logger.info(f"✅ Dataset configuration override: {key_path} = {value}")
            
            # Record current dataset information
            logger.info(f"📊 Current dataset: {profile_manager.current_profile_name}")
            logger.info(f"  - Qdrant URL: {storage_overrides.get('storage.vector.url', 'N/A')}")
            logger.info(f"  - Qdrant Collection: {profile_manager.get_collection_name()}")
            logger.info(f"  - PostgreSQL Port: {storage_overrides.get('storage.sql.postgres.port', 'N/A')}")
            logger.info(f"  - PostgreSQL Database: {profile_manager.get_postgres_database()}")
            logger.info(f"  - Neo4j URI: {storage_overrides.get('storage.graph.uri', 'N/A')}")
            logger.info(f"  - Neo4j Database: {profile_manager.get_neo4j_database()}")
            logger.info(f"  - Redis Port: {storage_overrides.get('storage.cache.port', 'N/A')}")
            
            # Record LLM configuration information
            if llm_overrides:
                logger.info(f"  - LLM Provider: {llm_overrides.get('llm.default_provider', 'N/A')}")
        
        except Exception as e:
            logger.debug(f"Failed to apply dataset configuration overrides (may not have dataset management configured): {e}")
    
    def _set_config_value(self, key_path: str, value: Any):
        """Set nested configuration value"""
        keys = key_path.split('.')
        
        # TOOL: Support multiple configuration types: navigate from root configuration
        # First key determines configuration type (storage, llm, etc.)
        config = self._config_cache
        
        # Navigate to parent of target location, create intermediate dicts if necessary
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            config = config[key]
        
        # Set final value
        config[keys[-1]] = value

    @lru_cache(maxsize=128)
    def get_config(self, section: Optional[str] = None) -> Any:
        """
        Get specified section of configuration.

        Args:
            section (str, optional): Top-level key name of configuration (e.g., "app", "llm", "prompts", "qa_prompts").
                                     Support nested access with dots.
                                     If None, return all configuration.

        Returns:
            Any: Requested configuration section.
        """
        if not section:
            return self._config_cache

        keys = section.split('.')
        value = self._config_cache
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
        return value
    
    # --- Convenience access methods ---
    @lru_cache(maxsize=1)
    def get_app_config(self) -> Dict[str, Any]:
        return self.get_config("app")

    def get_storage_config(self) -> Dict[str, Any]:
        """
        Get storage configuration
        
        TOOL: Do not use cache to ensure latest configuration is returned (supports dataset configuration override)
        """
        return self.get_config("storage")

    def get_llm_config(self) -> Dict[str, Any]:
        """
        Get LLM configuration
        
        TOOL: Do not use cache to ensure latest configuration is returned (supports dataset configuration override)
        """
        return self.get_config("llm")

    def get_prompts_config(self) -> Dict[str, Any]:
        """
        Get prompt configuration
        
        TOOL: Do not use cache to ensure latest configuration is returned
        """
        return self.get_config("prompts")

    def get_importance_scoring_config(self) -> Dict[str, Any]:
        """
        Get importance scoring configuration
        
        TOOL: Do not use cache to ensure latest configuration is returned
        """
        return self.get_config("memory.importance_scoring")

# Try to import python-dotenv, load .env file if available
try:
    from dotenv import load_dotenv
    # Load .env file
    env_file = Path(__file__).parent.parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        logger.info(f"Loaded environment variables file: {env_file}")
    else:
        logger.debug(f".env file not found: {env_file}")
except ImportError:
    logger.debug("python-dotenv not installed, skipping .env file loading")

# Define configuration file paths
CONFIG_DIR = Path(__file__).parent.parent.parent / "config"
SETTINGS_FILE = CONFIG_DIR / "settings.yaml"
PROMPTS_FILE = CONFIG_DIR / "prompts.yaml"
QA_PROMPTS_FILE = CONFIG_DIR / "qa_prompts.yaml"
MULTI_STAGE_QA_PROMPTS_FILE = CONFIG_DIR / "multi_stage_qa_prompts.yaml"


# Cache loaded configuration
_config_cache: Dict[str, Any] = {}

def _substitute_env_vars(raw_config: Any) -> Any:
    """Recursively substitute environment variables in configuration"""
    if isinstance(raw_config, dict):
        return {k: _substitute_env_vars(v) for k, v in raw_config.items()}
    if isinstance(raw_config, list):
        return [_substitute_env_vars(i) for i in raw_config]
    if isinstance(raw_config, str):
        # Match ${VAR_NAME:default_value} or ${VAR_NAME}
        pattern = r'\$\{([^}]+)\}'
        def replace_var(match):
            var_expr = match.group(1)
            var_name, _, default_value = var_expr.partition(':')
            return os.getenv(var_name.strip(), default_value.strip())
        return re.sub(pattern, replace_var, raw_config)
    return raw_config

@lru_cache(maxsize=None)
def _load_yaml_file(file_path: Path) -> Dict[str, Any]:
    """Load and parse a single YAML file"""
    if not file_path.exists():
        logger.warning(f"Configuration file not found: {file_path}")
        return {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            raw_config = yaml.safe_load(f) or {}
        # Environment variable substitution
        return _substitute_env_vars(raw_config)
    except Exception as e:
        logger.error(f"Failed to load or parse configuration file {file_path}: {e}")
        return {}

def get_config(section: Optional[str] = None) -> Dict[str, Any]:
    """
    Get specified section of configuration.

    Args:
        section (str, optional): Top-level key name of configuration (e.g., "app", "llm", "prompts", "qa_prompts").
                                 If None, return all configuration.

    Returns:
        Dict[str, Any]: Requested configuration section.
    """
    # NEW: Use ConfigManager instance to load to ensure dataset version management support
    config_manager = get_config_manager()
    return config_manager.get_config(section)

# --- Global singleton access functions ---
def get_config_manager(settings_file: Optional[Path] = None, prompts_file: Optional[Path] = None) -> ConfigManager:
    """
    Get global singleton instance of ConfigManager.
    """
    global _config_manager_instance
    if _config_manager_instance is None:
        _config_manager_instance = ConfigManager(settings_file=settings_file, prompts_file=prompts_file)
    return _config_manager_instance

# Convenience access functions (now access via ConfigManager instance)
def get_app_config() -> Dict[str, Any]:
    return get_config_manager().get_app_config()

def get_storage_config() -> Dict[str, Any]:
    return get_config_manager().get_storage_config()

def get_llm_config() -> Dict[str, Any]:
    return get_config_manager().get_llm_config()

def get_prompts_config() -> Dict[str, Any]:
    return get_config_manager().get_prompts_config()

def get_importance_scoring_config() -> Dict[str, Any]:
    """Get importance scoring configuration"""
    return get_config_manager().get_importance_scoring_config()


def reload_config():
    """Reload configuration"""
    get_config_manager().reload_config()

if __name__ == '__main__':
    # Example usage
    config_manager = get_config_manager()

    print("--- Application Configuration ---")
    print(config_manager.get_app_config())

    print("\n--- LLM Configuration ---")
    print(config_manager.get_llm_config())

    print("\n--- Prompt Configuration (L1) ---")
    prompts = config_manager.get_prompts_config()
    print(prompts.get("l1_session_summary"))
    
    # Simulate environment variables (use placeholders, actual deployment requires setting real API Key)
    os.environ["OPENAI_API_KEY"] = "your_openai_api_key_here"
    config_manager.reload_config()
    
    print("\n--- LLM Configuration After Reload (should show environment variables) ---")
    print(config_manager.get_llm_config())
    
    print("\n--- Nested Access Example ---")
    print(f"OpenAI Model: {config_manager.get_config('llm.providers.openai.model')}") 