"""
Dataset Configuration Guard
Ensures experimental code is consistent with configured datasets, prevents misoperations
"""

import os
import functools
import inspect
from pathlib import Path
from typing import Optional, Callable
from dotenv import load_dotenv
from timem.utils.logging import get_logger
from timem.utils.dataset_profile_manager import get_dataset_profile_manager

# Load environment variables from .env file before guard module loads
_env_path = Path(__file__).parent.parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path, override=True)

logger = get_logger(__name__)


class DatasetConfigError(Exception):
    """Dataset configuration error"""
    pass


class DatasetGuard:
    """Dataset configuration guard"""
    
    @staticmethod
    def get_current_dataset() -> str:
        """Get current active dataset configuration"""
        try:
            manager = get_dataset_profile_manager()
            return manager.current_profile_name
        except Exception as e:
            logger.error(f"Failed to get current dataset configuration: {e}")
            return "unknown"
    
    @staticmethod
    def get_dataset_info() -> dict:
        """Get detailed information of current dataset"""
        try:
            manager = get_dataset_profile_manager()
            return {
                "profile_name": manager.current_profile_name,
                "description": manager.get_description(),
                "collection_name": manager.get_collection_name(),
                "postgres_database": manager.get_postgres_database(),
                "neo4j_database": manager.get_neo4j_database(),
                "docker_compose_file": manager.get_docker_compose_file(),
                "docker_project_name": manager.get_docker_project_name(),
                "container_ports": manager.get_container_ports(),
                "metadata": manager.get_profile_metadata()
            }
        except Exception as e:
            logger.error(f"Failed to get dataset information: {e}")
            return {}
    
    @staticmethod
    def validate_dataset(
        expected_dataset,  # Union[str, List[str]]
        allow_test: bool = False,
        strict: bool = True
    ) -> bool:
        """
        Validate if current dataset configuration matches expectation
        
        Args:
            expected_dataset: Expected dataset name (str or list)
            allow_test: Whether to allow test dataset
            strict: Whether strict mode (raise exception if not matching)
            
        Returns:
            bool: Whether validation passed
            
        Raises:
            DatasetConfigError: Raised when config not matching in strict mode
        """
        current_dataset = DatasetGuard.get_current_dataset()
        
        # If test dataset allowed and current is test, pass
        if allow_test and current_dataset == "test":
            logger.info(f"Dataset validation passed: currently using test dataset (allowed)")
            return True
        
        # Unified handling as list
        expected_list = expected_dataset if isinstance(expected_dataset, list) else [expected_dataset]
        
        # Check if matching
        if current_dataset in expected_list:
            logger.info(f"Dataset validation passed: {current_dataset}")
            return True
        
        # Not matching
        expected_str = " or ".join(expected_list) if len(expected_list) > 1 else expected_list[0]
        error_msg = (
            f"Dataset configuration mismatch!\n"
            f"  Expected dataset: {expected_str}\n"
            f"  Current dataset: {current_dataset}\n"
            f"  \n"
            f"  Please switch to the correct dataset:\n"
            f"    export TIMEM_DATASET_PROFILE={expected_list[0]}  # Linux/Mac\n"
            f"    $env:TIMEM_DATASET_PROFILE=\"{expected_list[0]}\"  # Windows\n"
            f"  \n"
            f"  Or set in .env file:\n"
            f"    TIMEM_DATASET_PROFILE={expected_list[0]}\n"
        )
        
        if strict:
            logger.error(error_msg)
            raise DatasetConfigError(error_msg)
        else:
            logger.warning(error_msg)
            return False
    
    @staticmethod
    def require_dataset(
        dataset_name,  # Union[str, List[str]]
        allow_test: bool = False,
        show_warning: bool = True
    ):
        """
        Decorator: require function to run under specified dataset configuration
        
        Args:
            dataset_name: Required dataset name (str or list)
            allow_test: Whether to allow test dataset
            show_warning: Whether to show warning information
            
        Example:
            @DatasetGuard.require_dataset("default")
            async def test_locomo_experiment():
                # Only runs under default dataset
                pass
            
            @DatasetGuard.require_dataset(["default", "segment_param"], allow_test=True)
            async def test_segment_param():
                # Runs under default, segment_param or test dataset
                pass
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                # Validate dataset configuration
                if show_warning:
                    print(f"\n{'='*80}")
                    print(f"Dataset configuration validation")
                    print(f"{'='*80}")
                    print(f"  Function: {func.__name__}")
                    print(f"  Required dataset: {dataset_name}")
                    print(f"  Allow test dataset: {'Yes' if allow_test else 'No'}")
                    print(f"{'='*80}\n")
                
                DatasetGuard.validate_dataset(
                    expected_dataset=dataset_name,
                    allow_test=allow_test,
                    strict=True
                )
                
                # Show current configuration information
                if show_warning:
                    info = DatasetGuard.get_dataset_info()
                    print(f"Dataset validation passed, current configuration:")
                    print(f"  Dataset: {info.get('profile_name')}")
                    print(f"  Description: {info.get('description')}")
                    print(f"  PostgreSQL: localhost:{info.get('container_ports', {}).get('postgres', 5432)}")
                    print(f"  Qdrant: localhost:{info.get('container_ports', {}).get('qdrant', 6333)}")
                    print(f"  Neo4j: localhost:{info.get('container_ports', {}).get('neo4j_bolt', 7687)}")
                    print(f"  Redis: localhost:{info.get('container_ports', {}).get('redis', 6379)}")
                    print()
                
                return func(*args, **kwargs)
            
            # Support async functions
            if inspect.iscoroutinefunction(func):
                @functools.wraps(func)
                async def async_wrapper(*args, **kwargs):
                    # Validate dataset configuration
                    if show_warning:
                        print(f"\n{'='*80}")
                        print(f"Dataset configuration validation")
                        print(f"{'='*80}")
                        print(f"  Function: {func.__name__}")
                        print(f"  Required dataset: {dataset_name}")
                        print(f"  Allow test dataset: {'Yes' if allow_test else 'No'}")
                        print(f"{'='*80}\n")
                    
                    DatasetGuard.validate_dataset(
                        expected_dataset=dataset_name,
                        allow_test=allow_test,
                        strict=True
                    )
                    
                    # Show current configuration information
                    if show_warning:
                        info = DatasetGuard.get_dataset_info()
                        print(f"Dataset validation passed, current configuration:")
                        print(f"  Dataset: {info.get('profile_name')}")
                        print(f"  Description: {info.get('description')}")
                        print(f"  PostgreSQL: localhost:{info.get('container_ports', {}).get('postgres', 5432)}")
                        print(f"  Qdrant: localhost:{info.get('container_ports', {}).get('qdrant', 6333)}")
                        print(f"  Neo4j: localhost:{info.get('container_ports', {}).get('neo4j_bolt', 7687)}")
                        print(f"  Redis: localhost:{info.get('container_ports', {}).get('redis', 6379)}")
                        print()
                    
                    return await func(*args, **kwargs)
                
                return async_wrapper
            
            return wrapper
        
        return decorator
    
    @staticmethod
    def print_current_dataset():
        """
        Print current dataset configuration
        
        Returns:
            str: Dataset configuration information
        """
        info = DatasetGuard.get_dataset_info()
        
        print(f"\n{'='*80}")
        print(f"Current dataset configuration")
        print(f"{'='*80}")
        print(f"  Dataset name: {info.get('profile_name')}")
        print(f"  Description: {info.get('description')}")
        print(f"  \n  Database configuration:")
        print(f"    PostgreSQL database: {info.get('postgres_database')}")
        print(f"    Qdrant collection: {info.get('collection_name')}")
        print(f"    Neo4j database: {info.get('neo4j_database')}")
        print(f"  \n  Docker configuration:")
        print(f"    Compose file: {info.get('docker_compose_file')}")
        print(f"    Project name: {info.get('docker_project_name')}")
        
        container_ports = info.get('container_ports', {})
        if container_ports:
            print(f"  \n  Container ports:")
            print(f"    PostgreSQL: localhost:{container_ports.get('postgres', 5432)}")
            print(f"    Qdrant: localhost:{container_ports.get('qdrant', 6333)}")
            print(f"    Neo4j HTTP: localhost:{container_ports.get('neo4j_http', 7474)}")
            print(f"    Neo4j Bolt: localhost:{container_ports.get('neo4j_bolt', 7687)}")
            print(f"    Redis: localhost:{container_ports.get('redis', 6379)}")
        
        metadata = info.get('metadata', {})
        if metadata:
            print(f"  \n  Metadata:")
            for key, value in metadata.items():
                print(f"    {key}: {value}")
        
        print(f"{'='*80}\n")
    
    @staticmethod
    def warn_destructive_operation(operation_name: str):
        """
        Warn about destructive operation
        
        Args:
            operation_name: Operation name
        """
        current = DatasetGuard.get_current_dataset()
        
        print(f"\n{'⚠️ '*40}")
        print(f"⚠️  Warning: about to perform destructive operation!")
        print(f"{'⚠️ '*40}")
        print(f"  Target dataset: {operation_name}")
        print(f"  Current configuration: {current}")
        print(f"  \n  ✅ Dataset configuration matched")
        print(f"  The following operations will be executed on dataset: {operation_name}")
        print(f"    - Clear database")
        print(f"    - Regenerate memory")
        print(f"    - Other destructive operations")
        print(f"{'⚠️ '*40}\n")


# Convenience functions
def require_dataset(dataset_name: str, allow_test: bool = False):
    """
    Decorator: require function to run under specified dataset configuration
    
    Example:
        @require_dataset("default")
        async def test_locomo():
            pass
    """
    return DatasetGuard.require_dataset(dataset_name, allow_test)


def validate_dataset(expected_dataset: str, allow_test: bool = False):
    """
    Validate current dataset configuration
    
    Example:
        validate_dataset("longmemeval_s")
    """
    return DatasetGuard.validate_dataset(expected_dataset, allow_test, strict=True)


def get_current_dataset() -> str:
    """Get current dataset name"""
    return DatasetGuard.get_current_dataset()


def print_current_dataset():
    """Print current dataset information"""
    DatasetGuard.print_current_dataset()

