"""
TiMem Dataset Profile Manager
Supports independent database/collection configuration for different datasets, implementing data isolation
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from timem.utils.logging import get_logger

logger = get_logger(__name__)


class DatasetProfileManager:
    """Dataset profile manager"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize dataset profile manager
        
        Args:
            config_path: Dataset profile config file path, default is config/dataset_profiles.yaml
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "config" / "dataset_profiles.yaml"
        
        self.config_path = Path(config_path)
        self.profiles = self._load_profiles()
        self.current_profile_name = self._get_active_profile_name()
        self.current_profile = self._load_current_profile()
        
        logger.info(f"Dataset profile manager initialized, current profile: {self.current_profile_name}")
    
    def _load_profiles(self) -> Dict[str, Any]:
        """Load all dataset profiles"""
        if not self.config_path.exists():
            logger.warning(f"Dataset profile config file not found: {self.config_path}, using default profile")
            return self._get_default_profile()
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                profiles = yaml.safe_load(f)
            
            if not profiles:
                logger.warning("Dataset profile config file is empty, using default profile")
                return self._get_default_profile()
            
            logger.info(f"Successfully loaded {len(profiles)} dataset profiles")
            return profiles
        
        except Exception as e:
            logger.error(f"Failed to load dataset profile config file: {e}, using default profile")
            return self._get_default_profile()
    
    def _get_default_profile(self) -> Dict[str, Any]:
        """Get default profile"""
        return {
            "default": {
                "description": "Default dataset profile",
                "storage": {
                    "vector": {
                        "collection_name": "timem_memories"
                    },
                    "sql": {
                        "postgres": {
                            "database": "timem_db"
                        }
                    },
                    "graph": {
                        "database": "neo4j"
                    }
                },
                "enabled": True
            }
        }
    
    def _get_active_profile_name(self) -> str:
        """
        Get current active dataset profile name
        
        Priority:
        1. Environment variable TIMEM_DATASET_PROFILE
        2. Default value "default"
        """
        profile_name = os.getenv("TIMEM_DATASET_PROFILE", "default")
        
        if profile_name not in self.profiles:
            logger.warning(
                f"Specified dataset profile '{profile_name}' does not exist, "
                f"available profiles: {list(self.profiles.keys())}, using default profile"
            )
            profile_name = "default"
        
        return profile_name
    
    def _load_current_profile(self) -> Dict[str, Any]:
        """Load current active dataset profile"""
        profile = self.profiles.get(self.current_profile_name, {})
        
        if not profile.get("enabled", True):
            logger.warning(f"Dataset profile '{self.current_profile_name}' is disabled, using default profile")
            return self.profiles.get("default", {})
        
        return profile
    
    def get_collection_name(self) -> str:
        """Get current dataset's Qdrant collection name"""
        return self.current_profile.get("storage", {}).get("vector", {}).get("collection_name", "timem_memories")
    
    def get_postgres_database(self) -> str:
        """Get current dataset's PostgreSQL database name"""
        return self.current_profile.get("storage", {}).get("sql", {}).get("postgres", {}).get("database", "timem_db")
    
    def get_neo4j_database(self) -> str:
        """Get current dataset's Neo4j database name"""
        return self.current_profile.get("storage", {}).get("graph", {}).get("database", "neo4j")
    
    def get_profile_metadata(self) -> Dict[str, Any]:
        """Get current dataset's metadata"""
        return self.current_profile.get("metadata", {})
    
    def get_description(self) -> str:
        """Get current dataset's description"""
        return self.current_profile.get("description", "")
    
    def list_available_profiles(self) -> Dict[str, str]:
        """List all available dataset profiles"""
        return {
            name: profile.get("description", "")
            for name, profile in self.profiles.items()
            if profile.get("enabled", True)
        }
    
    def switch_profile(self, profile_name: str) -> bool:
        """
        Switch to specified dataset profile
        
        Args:
            profile_name: Dataset profile name
            
        Returns:
            bool: Whether switch was successful
            
        Note:
            This method is only valid in current process, not persistent
            To persist, set environment variable TIMEM_DATASET_PROFILE
        """
        if profile_name not in self.profiles:
            logger.error(f"Dataset profile '{profile_name}' does not exist")
            return False
        
        profile = self.profiles[profile_name]
        if not profile.get("enabled", True):
            logger.error(f"Dataset profile '{profile_name}' is disabled")
            return False
        
        self.current_profile_name = profile_name
        self.current_profile = profile
        
        logger.info(f"Switched to dataset profile: {profile_name}")
        return True
    
    def get_storage_config_overrides(self) -> Dict[str, Any]:
        """
        Get current dataset profile's storage config overrides
        Used to override default config in settings.yaml
        
        Returns:
            Dict[str, Any]: Storage config override dictionary
        """
        overrides = {}
        storage_config = self.current_profile.get("storage", {})
        
        # Qdrant config override (🔧 fix: add storage prefix)
        vector_config = storage_config.get("vector", {})
        if "collection_name" in vector_config:
            overrides["storage.vector.collection_name"] = vector_config["collection_name"]
        if "url" in vector_config:
            overrides["storage.vector.url"] = vector_config["url"]
        # 🆕 If no complete URL but has host and port, build URL
        elif "host" in vector_config and "port" in vector_config:
            host = vector_config["host"]
            port = vector_config["port"]
            overrides["storage.vector.url"] = f"http://{host}:{port}"
        
        # PostgreSQL config override (🔧 fix: add storage prefix)
        postgres_config = storage_config.get("sql", {}).get("postgres", {})
        if "database" in postgres_config:
            overrides["storage.sql.postgres.database"] = postgres_config["database"]
        if "host" in postgres_config:
            overrides["storage.sql.postgres.host"] = postgres_config["host"]
        if "port" in postgres_config:
            overrides["storage.sql.postgres.port"] = postgres_config["port"]
        if "user" in postgres_config:
            overrides["storage.sql.postgres.user"] = postgres_config["user"]
        if "password" in postgres_config:
            overrides["storage.sql.postgres.password"] = postgres_config["password"]
        
        # Neo4j config override (🔧 fix: add storage prefix)
        graph_config = storage_config.get("graph", {})
        if "database" in graph_config:
            overrides["storage.graph.database"] = graph_config["database"]
        if "uri" in graph_config:
            overrides["storage.graph.uri"] = graph_config["uri"]
        # 🆕 If no complete URI but has host and port, build URI
        elif "host" in graph_config and "bolt_port" in graph_config:
            host = graph_config["host"]
            port = graph_config["bolt_port"]
            overrides["storage.graph.uri"] = f"bolt://{host}:{port}"
        if "user" in graph_config:
            overrides["storage.graph.user"] = graph_config["user"]
        if "password" in graph_config:
            overrides["storage.graph.password"] = graph_config["password"]
        
        # Redis config override (🔧 fix: add storage prefix)
        cache_config = storage_config.get("cache", {})
        if "host" in cache_config:
            overrides["storage.cache.host"] = cache_config["host"]
        if "port" in cache_config:
            overrides["storage.cache.port"] = cache_config["port"]
        if "password" in cache_config:
            overrides["storage.cache.password"] = cache_config["password"]
        if "db" in cache_config:
            overrides["storage.cache.db"] = cache_config["db"]
        
        return overrides
    
    def get_llm_config_overrides(self) -> Dict[str, Any]:
        """
        Get current dataset profile's LLM config overrides
        Used to override default LLM config in settings.yaml
        
        Returns:
            Dict[str, Any]: LLM config override dictionary
        """
        overrides = {}
        llm_config = self.current_profile.get("llm", {})
        
        # LLM provider override
        if "default_provider" in llm_config:
            overrides["llm.default_provider"] = llm_config["default_provider"]
        
        # Other LLM config overrides (if needed)
        if "timeout" in llm_config:
            overrides["llm.timeout"] = llm_config["timeout"]
        if "max_retries" in llm_config:
            overrides["llm.max_retries"] = llm_config["max_retries"]
        
        return overrides
    
    def is_test_profile(self) -> bool:
        """Determine if current is test profile"""
        return self.current_profile.get("metadata", {}).get("is_test", False)
    
    def get_dataset_path(self) -> Optional[str]:
        """Get current dataset's data file path"""
        return self.current_profile.get("metadata", {}).get("dataset_path")
    
    def get_docker_config(self) -> Dict[str, Any]:
        """Get current dataset's Docker configuration"""
        return self.current_profile.get("docker", {})
    
    def get_docker_compose_file(self) -> str:
        """Get current dataset's docker-compose file name"""
        return self.current_profile.get("docker", {}).get("compose_file", "docker-compose.yml")
    
    def get_docker_project_name(self) -> str:
        """Get current dataset's Docker project name"""
        return self.current_profile.get("docker", {}).get("project_name", "timem")
    
    def get_container_ports(self) -> Dict[str, int]:
        """Get current dataset's container port mappings"""
        return self.current_profile.get("metadata", {}).get("container_ports", {})


# Global singleton
_dataset_profile_manager: Optional[DatasetProfileManager] = None


def get_dataset_profile_manager(force_reload: bool = False) -> DatasetProfileManager:
    """Get global dataset profile manager instance"""
    global _dataset_profile_manager
    if _dataset_profile_manager is None or force_reload:
        _dataset_profile_manager = DatasetProfileManager()
    return _dataset_profile_manager


def get_active_dataset_profile() -> str:
    """Get current active dataset profile name"""
    return get_dataset_profile_manager().current_profile_name


def get_collection_name_for_dataset() -> str:
    """Get current dataset's Qdrant collection name"""
    return get_dataset_profile_manager().get_collection_name()


def get_postgres_database_for_dataset() -> str:
    """Get current dataset's PostgreSQL database name"""
    return get_dataset_profile_manager().get_postgres_database()


def get_neo4j_database_for_dataset() -> str:
    """Get current dataset's Neo4j database name"""
    return get_dataset_profile_manager().get_neo4j_database()

