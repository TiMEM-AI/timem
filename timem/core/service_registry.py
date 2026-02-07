"""
TiMem Service Registry

Unified management of all service lifecycles, providing service discovery and dependency injection.

Core Features:
1. Service registration and discovery
2. Dependency injection management
3. Service lifecycle management
4. Health check coordination
5. Failure recovery mechanism
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Type, Callable, List
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import threading

from timem.utils.logging import get_logger

logger = get_logger(__name__)


class ServiceType(Enum):
    """Service type enumeration"""
    MEMORY_GENERATION = "memory_generation"
    MEMORY_RETRIEVAL = "memory_retrieval"
    STORAGE_MANAGER = "storage_manager"
    CONNECTION_POOL = "connection_pool"
    USER_REGISTRATION = "user_registration"
    CHARACTER_SERVICE = "character_service"
    USER_SERVICE = "user_service"  # Real user service (users table)
    TIME_MANAGER = "time_manager"
    SESSION_TRACKER = "session_tracker"
    SESSION_CONTEXT_MANAGER = "session_context_manager"  # ✅ New: Session context manager
    EMBEDDING_SERVICE = "embedding_service"  # ✨ New: Embedding service (hot load)
    SCHEDULER = "scheduler"  # 🕐 New: Scheduled task scheduler


@dataclass
class ServiceInfo:
    """Service information"""
    name: str
    service_type: ServiceType
    instance: Any
    factory: Callable
    dependencies: List[ServiceType]
    initialized: bool = False
    last_health_check: Optional[datetime] = None
    error_count: int = 0
    max_errors: int = 5


class ServiceRegistry:
    """
    Service Registry - Singleton pattern
    
    Responsible for managing lifecycle and dependencies of all services
    """
    
    _instance: Optional['ServiceRegistry'] = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ServiceRegistry, cls).__new__(cls)
            cls._instance._initialize_instance()
        return cls._instance
    
    def _initialize_instance(self):
        """Initialize instance variables"""
        self._services: Dict[ServiceType, ServiceInfo] = {}
        self._initialization_order: List[ServiceType] = []
        self._shutdown_order: List[ServiceType] = []
        self._health_check_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        self._logger = get_logger(__name__)
    
    async def register_service(
        self,
        service_type: ServiceType,
        factory: Callable,
        dependencies: List[ServiceType] = None,
        max_errors: int = 5
    ):
        """
        Register service
        
        Args:
            service_type: Service type
            factory: Service factory function
            dependencies: List of dependent service types
            max_errors: Maximum error count
        """
        async with self._lock:
            if service_type in self._services:
                self._logger.warning(f"Service {service_type.value} already exists, will be overwritten")
            
            self._services[service_type] = ServiceInfo(
                name=service_type.value,
                service_type=service_type,
                instance=None,
                factory=factory,
                dependencies=dependencies or [],
                max_errors=max_errors
            )
            
            self._logger.info(f"Service {service_type.value} registered")
    
    async def get_service(self, service_type: ServiceType) -> Any:
        """
        Get service instance
        
        Args:
            service_type: Service type
            
        Returns:
            Service instance
        """
        if service_type not in self._services:
            raise ValueError(f"Service {service_type.value} not registered")
        
        service_info = self._services[service_type]
        
        # Initialize service if not already initialized
        if not service_info.initialized:
            await self._initialize_service(service_type)
        
        return service_info.instance
    
    async def _initialize_service(self, service_type: ServiceType):
        """Initialize service"""
        service_info = self._services[service_type]
        
        if service_info.initialized:
            return
        
        try:
            # Check dependent services
            for dep_type in service_info.dependencies:
                if dep_type not in self._services:
                    raise ValueError(f"Dependent service {dep_type.value} not registered")
                
                dep_info = self._services[dep_type]
                if not dep_info.initialized:
                    await self._initialize_service(dep_type)
            
            # Create service instance
            self._logger.info(f"Initializing service {service_type.value}...")
            service_info.instance = await service_info.factory()
            service_info.initialized = True
            service_info.error_count = 0
            
            # Update initialization order
            if service_type not in self._initialization_order:
                self._initialization_order.append(service_type)
            
            self._logger.info(f"✅ Service {service_type.value} initialized successfully")
            
        except Exception as e:
            service_info.error_count += 1
            self._logger.error(f"❌ Service {service_type.value} initialization failed: {e}")
            
            if service_info.error_count >= service_info.max_errors:
                self._logger.error(f"Service {service_type.value} reached maximum error count, marked as failed")
            
            raise
    
    async def initialize_all_services(self):
        """Initialize all services"""
        self._logger.info("🚀 Starting initialization of all services...")
        
        # Sort by dependencies
        sorted_services = self._topological_sort()
        
        for service_type in sorted_services:
            try:
                await self._initialize_service(service_type)
            except Exception as e:
                self._logger.error(f"Service {service_type.value} initialization failed: {e}")
                # Continue initializing other services
        
        self._logger.info("✅ All services initialized")
    
    def _topological_sort(self) -> List[ServiceType]:
        """Topological sort to determine service initialization order"""
        visited = set()
        temp_visited = set()
        result = []
        
        def visit(service_type: ServiceType):
            if service_type in temp_visited:
                raise ValueError(f"Circular dependency detected: {service_type.value}")
            if service_type in visited:
                return
            
            temp_visited.add(service_type)
            
            # Visit dependent services
            service_info = self._services[service_type]
            for dep_type in service_info.dependencies:
                visit(dep_type)
            
            temp_visited.remove(service_type)
            visited.add(service_type)
            result.append(service_type)
        
        for service_type in self._services:
            if service_type not in visited:
                visit(service_type)
        
        return result
    
    async def shutdown_all_services(self):
        """
        Shutdown all services
        
        Ensure correct shutdown order and complete resource cleanup
        """
        import asyncio
        
        self._logger.info("🛑 Starting shutdown of all services...")
        
        # Shutdown services in reverse order
        shutdown_order = list(reversed(self._initialization_order))
        
        for service_type in shutdown_order:
            try:
                await self._shutdown_service(service_type)
            except Exception as e:
                self._logger.error(f"❌ Error shutting down service {service_type.value}: {e}", exc_info=True)
        
        # Special handling for connection pool services (ensure complete cleanup)
        self._logger.info("📋 Cleaning up all database connection pools...")
        
        try:
            # 1. Clean up unified connection pool manager
            from timem.core.unified_connection_manager import get_unified_connection_manager
            connection_manager = await get_unified_connection_manager()
            if connection_manager and connection_manager._initialized:
                await connection_manager.cleanup_all_pools()
                self._logger.info("✅ Unified connection pool cleaned up")
        except Exception as e:
            self._logger.error(f"❌ Error cleaning up unified connection pool: {e}")
        
        try:
            # 2. Clean up global connection pool
            from timem.core.global_connection_pool import get_global_pool_manager
            global_pool = await get_global_pool_manager()  # 🔧 Fix: Add await
            if global_pool and hasattr(global_pool, '_engine') and global_pool._engine:
                await global_pool.force_cleanup()
                self._logger.info("✅ Global connection pool cleaned up")
        except Exception as e:
            self._logger.error(f"❌ Error cleaning up global connection pool: {e}")
        
        # Wait a moment to ensure all connections are closed
        await asyncio.sleep(0.5)
        
        # Reset registry state for hot reload
        self._initialization_order.clear()
        
        self._logger.info("✅ All services shut down, resources cleaned up")
    
    async def _shutdown_service(self, service_type: ServiceType):
        """Shutdown single service"""
        service_info = self._services[service_type]
        
        if not service_info.initialized:
            return
        
        try:
            # If service has shutdown method, call it
            if hasattr(service_info.instance, 'shutdown'):
                await service_info.instance.shutdown()
            
            service_info.initialized = False
            service_info.instance = None
            
            self._logger.info(f"✅ Service {service_type.value} shut down")
            
        except Exception as e:
            self._logger.error(f"❌ Error shutting down service {service_type.value}: {e}")
    
    async def health_check_all(self) -> Dict[ServiceType, bool]:
        """Check health status of all services"""
        results = {}
        
        for service_type, service_info in self._services.items():
            if not service_info.initialized:
                results[service_type] = False
                continue
            
            try:
                # If service has health_check method, call it
                if hasattr(service_info.instance, 'health_check'):
                    health_result = await service_info.instance.health_check()
                    results[service_type] = health_result.get('status') == 'ready' if isinstance(health_result, dict) else bool(health_result)
                else:
                    results[service_type] = True
                
                service_info.last_health_check = datetime.now()
                
            except Exception as e:
                self._logger.error(f"Service {service_type.value} health check failed: {e}")
                results[service_type] = False
                service_info.error_count += 1
        
        return results
    
    def get_service_status(self) -> Dict[str, Any]:
        """Get status of all services"""
        status = {}
        
        for service_type, service_info in self._services.items():
            status[service_type.value] = {
                "initialized": service_info.initialized,
                "error_count": service_info.error_count,
                "max_errors": service_info.max_errors,
                "last_health_check": service_info.last_health_check,
                "dependencies": [dep.value for dep in service_info.dependencies]
            }
        
        return status


# Global service registry instance
_service_registry: Optional[ServiceRegistry] = None
_registry_lock = asyncio.Lock()


async def get_service_registry() -> ServiceRegistry:
    """Get service registry singleton"""
    global _service_registry
    
    if _service_registry is None:
        async with _registry_lock:
            if _service_registry is None:
                _service_registry = ServiceRegistry()
    
    return _service_registry


async def register_core_services():
    """Register core services"""
    registry = await get_service_registry()
    
    # ✨ Register Embedding service (hot load, no dependencies, initialize first)
    async def create_embedding_service():
        from llm.embedding_service import init_embedding_service
        service = await init_embedding_service()
        logger.info("✅ Embedding service hot loaded, model preloading completed")
        return service
    
    await registry.register_service(
        ServiceType.EMBEDDING_SERVICE,
        factory=create_embedding_service,
        dependencies=[]
    )
    
    # Register connection pool service
    # 🔧 Fix: factory returns coroutine, no need to wrap again
    async def connection_pool_factory():
        from timem.core.global_connection_pool import get_global_pool_manager
        return await get_global_pool_manager()
    
    await registry.register_service(
        ServiceType.CONNECTION_POOL,
        factory=connection_pool_factory,
        dependencies=[]
    )
    
    # Register storage manager service
    async def create_storage_manager():
        from storage.memory_storage_manager import MemoryStorageManager
        manager = MemoryStorageManager()
        await manager._create_default_adapters()
        return manager
    
    await registry.register_service(
        ServiceType.STORAGE_MANAGER,
        factory=create_storage_manager,
        dependencies=[ServiceType.CONNECTION_POOL]
    )
    
    # Register user registration service
    async def create_user_registration_service():
        from services.user_registration_service import get_user_registration_service
        return await get_user_registration_service()
    
    await registry.register_service(
        ServiceType.USER_REGISTRATION,
        factory=create_user_registration_service,
        dependencies=[ServiceType.CHARACTER_SERVICE]
    )
    
    # Register memory generation service
    async def create_memory_generation_service():
        from services.memory_generation_service import get_memory_generation_service
        return await get_memory_generation_service()
    
    await registry.register_service(
        ServiceType.MEMORY_GENERATION,
        factory=create_memory_generation_service,
        dependencies=[ServiceType.STORAGE_MANAGER, ServiceType.CONNECTION_POOL]
    )
    
    # Register character service
    async def create_character_service():
        from services.character_service import get_character_service
        return get_character_service()
    
    await registry.register_service(
        ServiceType.CHARACTER_SERVICE,
        factory=create_character_service,
        dependencies=[]
    )
    
    # Register user service
    async def create_user_service():
        from services.user_service import get_user_service
        return get_user_service()
    
    await registry.register_service(
        ServiceType.USER_SERVICE,
        factory=create_user_service,
        dependencies=[]
    )
    
    # ✅ Register session context manager (preheat to avoid first request delay)
    async def create_session_context_manager():
        from services.session_context_manager import get_session_context_manager
        manager = await get_session_context_manager()
        logger.info("✅ Session context manager preheated")
        return manager
    
    await registry.register_service(
        ServiceType.SESSION_CONTEXT_MANAGER,
        factory=create_session_context_manager,
        dependencies=[ServiceType.CONNECTION_POOL]
    )
    
    # 🕐 Register scheduled task scheduler (for daily auto-completion)
    async def create_scheduler_service():
        from services.scheduler_service import get_scheduler_service
        scheduler = await get_scheduler_service()
        logger.info("🕐 Scheduled task scheduler registered")
        return scheduler
    
    await registry.register_service(
        ServiceType.SCHEDULER,
        factory=create_scheduler_service,
        dependencies=[ServiceType.MEMORY_GENERATION, ServiceType.CONNECTION_POOL]
    )
    
    logger.info("Core services registration completed")


async def get_service(service_type: ServiceType) -> Any:
    """Convenience function to get service instance"""
    registry = await get_service_registry()
    return await registry.get_service(service_type)


async def initialize_all_services():
    """Convenience function to initialize all services"""
    registry = await get_service_registry()
    await registry.initialize_all_services()
    
    # Start scheduled task scheduler
    try:
        scheduler = await get_service(ServiceType.SCHEDULER)
        if scheduler and hasattr(scheduler, 'start'):
            await scheduler.start()
            logger.info("🕐 Scheduled task scheduler started")
    except Exception as e:
        logger.warning(f"⚠️ Scheduled task scheduler startup failed: {e}")


async def shutdown_all_services():
    """Convenience function to shutdown all services"""
    # First shutdown scheduled task scheduler
    try:
        scheduler = await get_service(ServiceType.SCHEDULER)
        if scheduler and hasattr(scheduler, 'shutdown'):
            await scheduler.shutdown()
            logger.info("🕐 Scheduled task scheduler shut down")
    except Exception as e:
        logger.warning(f"⚠️ Scheduled task scheduler shutdown failed: {e}")
    
    # Then shutdown other services
    registry = await get_service_registry()
    await registry.shutdown_all_services()
