"""
TiMem Memory Storage Manager
Unified management of storage adapters, serving as a single entry point for the storage layer
"""

import uuid
import asyncio
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple, Union
from enum import Enum

from timem.models.memory import Memory, convert_dict_to_memory
from timem.utils.logging import get_logger
from timem.utils.config_manager import get_storage_config

# Support execution state
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from timem.core.execution_state import ExecutionState

# Import unified interface and adapter implementations
from storage.postgres_adapter import PostgreSQLAdapter
from storage.vector_adapter import VectorAdapter
from storage.graph_adapter import GraphAdapter
from storage.cache_adapter import CacheAdapter
from storage.storage_adapter import StorageAdapter
from timem.utils.config_manager import ConfigManager


class MemoryStorageManager:
    """Memory Storage Manager - Unified management of storage adapters, single entry point for storage layer V2 (PostgreSQL only)"""

    def __init__(
        self,
        postgres_adapter: Optional[PostgreSQLAdapter] = None,
        vector_adapter: Optional[VectorAdapter] = None,
        graph_adapter: Optional[GraphAdapter] = None,
        cache_adapter: Optional[CacheAdapter] = None,
        config_manager: Optional[ConfigManager] = None,
    ):
        """
        Initialize storage manager through dependency injection.
        Allows creating and configuring adapters externally, then passing them in.
        
        Note: This system only supports PostgreSQL, not MySQL.
        """
        self.logger = get_logger(__name__)
        self.config_manager = config_manager
        self.postgres_adapter = postgres_adapter
        self.vector_adapter = vector_adapter
        self.graph_adapter = graph_adapter
        self.cache_adapter = cache_adapter

        self.adapters: Dict[str, StorageAdapter] = {}
        if postgres_adapter:
            self.adapters["postgres"] = postgres_adapter
            # Backward compatibility: register postgres adapter as sql
            self.adapters["sql"] = postgres_adapter
        if vector_adapter:
            self.adapters["vector"] = vector_adapter
        if graph_adapter:
            self.adapters["graph"] = graph_adapter
        if cache_adapter:
            self.adapters["cache"] = cache_adapter
        
        # Use only PostgreSQL as the default adapter
        self.default_adapter = postgres_adapter or vector_adapter or graph_adapter or cache_adapter
        
        # Storage status tracking
        self.storage_status = {
            "postgres": False,
            "vector": False,
            "graph": False,
            "cache": False
        }
        
        # Initialization status
        self._initialized = False
        
        # 🔧 New: Connection pool lifecycle management
        self._connection_pool_monitor = {
            'active_connections': 0,
            'max_connections': 0,
            'connection_errors': 0,
            'last_cleanup': 0
        }
        
        self.logger.info("MemoryStorageManager V2 initialized with injected adapters.")
    
    async def monitor_connection_pool(self):
        """Monitor connection pool status"""
        try:
            if self.postgres_adapter and hasattr(self.postgres_adapter, '_postgres_store'):
                postgres_store = self.postgres_adapter._postgres_store
                if hasattr(postgres_store, 'engine') and postgres_store.engine:
                    pool = postgres_store.engine.pool
                    if hasattr(pool, 'size') and hasattr(pool, 'checked_in') and hasattr(pool, 'checked_out'):
                        pool_size = pool.size()
                        checked_in = pool.checked_in()
                        checked_out = pool.checked_out()
                        
                        self._connection_pool_monitor['active_connections'] = checked_out
                        self._connection_pool_monitor['max_connections'] = pool_size + getattr(pool, 'max_overflow', 0)
                        
                        # Log warning if connection pool utilization is too high
                        if checked_out > pool_size * 0.8:
                            self.logger.warning(f"Connection pool utilization too high: {checked_out}/{pool_size + getattr(pool, 'max_overflow', 0)}")
                        
                        return {
                            'pool_size': pool_size,
                            'checked_in': checked_in,
                            'checked_out': checked_out,
                            'max_overflow': getattr(pool, 'max_overflow', 0)
                        }
        except Exception as e:
            self.logger.warning(f"Connection pool monitoring failed: {e}")
            self._connection_pool_monitor['connection_errors'] += 1
        
        return None
    
    async def force_cleanup_connections(self):
        """Force cleanup all connections"""
        try:
            self.logger.info("Starting forced cleanup of all storage connections...")
            cleanup_count = 0
            
            # Clean up PostgreSQL connections
            if hasattr(self, 'postgres_adapter') and self.postgres_adapter:
                try:
                    await self.postgres_adapter.disconnect()
                    cleanup_count += 1
                    self.logger.info("✅ PostgreSQL adapter connection cleaned up")
                except Exception as e:
                    self.logger.error(f"Failed to clean up PostgreSQL adapter connection: {e}")
            
            # Clean up vector connections
            if hasattr(self, 'vector_adapter') and self.vector_adapter:
                try:
                    if hasattr(self.vector_adapter, 'disconnect'):
                        await self.vector_adapter.disconnect()
                        cleanup_count += 1
                        self.logger.info("✅ Vector adapter connection cleaned up")
                except Exception as e:
                    self.logger.error(f"Failed to clean up vector adapter connection: {e}")
            
            self.logger.info(f"✅ Forced connection cleanup completed, cleaned up {cleanup_count} connections")
            return cleanup_count
            
        except Exception as e:
            self.logger.error(f"Failed to force cleanup connections: {e}")
            return 0
    
    async def close_all_connections(self):
        """Close all connections (for normal cleanup)"""
        try:
            self.logger.info("Starting to close all storage connections...")
            cleanup_count = 0
            
            # Close PostgreSQL connections
            if hasattr(self, 'postgres_adapter') and self.postgres_adapter:
                try:
                    await self.postgres_adapter.disconnect()
                    cleanup_count += 1
                    self.logger.info("✅ PostgreSQL adapter connection closed")
                except Exception as e:
                    self.logger.error(f"Failed to close PostgreSQL adapter connection: {e}")
            
            # Close vector connections
            if hasattr(self, 'vector_adapter') and self.vector_adapter:
                try:
                    if hasattr(self.vector_adapter, 'disconnect'):
                        await self.vector_adapter.disconnect()
                        cleanup_count += 1
                        self.logger.info("✅ Vector adapter connection closed")
                except Exception as e:
                    self.logger.error(f"Failed to close vector adapter connection: {e}")
            
            self.logger.info(f"✅ All connections closed, closed {cleanup_count} connections")
            return cleanup_count
            
        except Exception as e:
            self.logger.error(f"Failed to close connections: {e}")
            return 0

    async def _create_default_adapters(self):
        """Create default adapters based on configuration - PostgreSQL only, no fallback mechanism"""
        try:
            # Get storage configuration
            storage_config = get_storage_config()
            sql_config = storage_config.get('sql', {})
            sql_provider = sql_config.get('provider', 'postgres')  # Default PostgreSQL
            
            self.logger.info(f"Creating storage adapters based on configuration, SQL provider: {sql_provider}")
            
            # 🔧 Fix: PostgreSQL only, remove MySQL fallback logic
            if sql_provider == 'postgres':
                await self._create_postgres_adapter()
            else:
                # 🔧 Fix: Non-PostgreSQL providers not supported, throw error directly
                error_msg = f"Unsupported SQL provider: {sql_provider}. System only supports PostgreSQL, no fallback mechanism"
                self.logger.error(error_msg)
                raise ValueError(error_msg)
            
            # Create vector adapter
            await self._create_vector_adapter()
            
        except Exception as e:
            # 🔧 Fix: Throw error directly when creating default adapters fails, no fallback
            error_msg = f"Failed to create default adapters: {e}. System requires PostgreSQL to be running online, no fallback mechanism"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)

    async def _create_postgres_adapter(self):
        """Create PostgreSQL adapter - using unified connection pool manager"""
        try:
            from storage.postgres_adapter import PostgreSQLAdapter, create_postgres_adapter
            from storage.postgres_store import create_postgres_store
            from timem.core.unified_connection_manager import get_unified_connection_manager, ConnectionPoolType
            
            # 🔧 New architecture: Use unified connection pool manager to avoid multi-instance pool issues
            unified_manager = await get_unified_connection_manager()
            
            # 1. Create PostgreSQL storage instance (now using unified connection pool)
            postgres_store = await create_postgres_store()
            
            # 🔧 Fix: Ensure PostgreSQL connection succeeds, throw exception if fails
            if not postgres_store._is_available:
                raise RuntimeError("PostgreSQL storage instance connection failed")
            
            # 2. Create PostgreSQL adapter instance
            postgres_adapter = PostgreSQLAdapter(postgres_store)
            await postgres_adapter.connect()
            
            # 🔧 Fix: Verify adapter connection status
            if not await postgres_adapter.is_available():
                raise RuntimeError("PostgreSQL adapter connection verification failed")
            
            # 🔧 Fix: Simplify availability check, test connection directly
            if await postgres_adapter.is_available():
                self.postgres_adapter = postgres_adapter
                self.adapters["postgres"] = postgres_adapter
                # Register postgres adapter as sql too (backward compatible)
                self.adapters["sql"] = postgres_adapter
                self.default_adapter = postgres_adapter
                
                # 🔧 New architecture: Record unified connection pool status
                stats = await unified_manager.get_stats(ConnectionPoolType.POSTGRES)
                if stats:
                    self.logger.info(f"PostgreSQL adapter created successfully - using unified connection pool (status: {stats.status}, utilization: {stats.utilization_percent:.1f}%)")
                else:
                    self.logger.info("PostgreSQL adapter created successfully - using unified connection pool")
            else:
                # 🔧 Fix: Throw error directly when PostgreSQL unavailable, no fallback
                error_msg = "PostgreSQL unavailable, system requires PostgreSQL to be running online, no fallback mechanism"
                self.logger.error(error_msg)
                raise RuntimeError(error_msg)
                
        except Exception as e:
            # 🔧 Fix: Throw error directly when PostgreSQL adapter creation fails, no fallback
            error_msg = f"Failed to create PostgreSQL adapter: {e}. System requires PostgreSQL to be running online, no fallback mechanism"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)

    # 🔧 Deprecated: MySQL adapter no longer supported, system only supports PostgreSQL
    # async def _create_mysql_adapter(self):
    #     """Create MySQL adapter (LEGACY fallback version) - Deprecated"""
    #     # This method is deprecated, system only supports PostgreSQL, no fallback mechanism
    #     raise RuntimeError("MySQL adapter deprecated, system only supports PostgreSQL, no fallback mechanism")

    async def _create_vector_adapter(self):
        """Create vector adapter"""
        try:
            from storage.vector_adapter import VectorAdapter
            
            vector_adapter = VectorAdapter(self.config_manager)
            self.vector_adapter = vector_adapter
            self.adapters["vector"] = vector_adapter
            self.logger.info("Vector adapter registered (lazy connection)")
            
        except Exception as e:
            self.logger.warning(f"Failed to register vector adapter (can be ignored, can retry later): {e}")

    async def initialize(self):
        """Initialization entry point for backward compatibility with old test cases, equivalent to ensure_initialized."""
        await self.ensure_initialized()
    
    async def ensure_initialized(self):
        """Ensure storage manager is initialized"""
        if not self._initialized:
            # If no adapters, create default adapters based on configuration
            if not self.adapters:
                await self._create_default_adapters()
            
            # Check availability of storage adapters - PostgreSQL only
            for storage_type, adapter in self.adapters.items():
                if adapter:
                    try:
                        # Check PostgreSQL storage
                        if storage_type == "postgres" and hasattr(adapter, '_postgres_store'):
                            if await adapter.is_available():
                                self.storage_status[storage_type] = True
                                self.logger.info("PostgreSQL storage initialized")
                            else:
                                # 🔧 Fix: Throw error directly when PostgreSQL unavailable, no fallback
                                error_msg = f"PostgreSQL storage unavailable, system requires PostgreSQL to be running online, no fallback mechanism"
                                self.logger.error(error_msg)
                                raise RuntimeError(error_msg)
                        # Check SQL storage (as alias for PostgreSQL)
                        elif storage_type == "sql":
                            if hasattr(adapter, '_postgres_store'):
                                # SQL adapter is actually PostgreSQL adapter
                                if await adapter.is_available():
                                    self.storage_status[storage_type] = True
                                    self.logger.info("SQL storage (PostgreSQL) initialized")
                                else:
                                    # 🔧 Fix: Throw error directly when PostgreSQL unavailable, no fallback
                                    error_msg = f"SQL storage (PostgreSQL) unavailable, system requires PostgreSQL to be running online, no fallback mechanism"
                                    self.logger.error(error_msg)
                                    raise RuntimeError(error_msg)
                            else:
                                # 🔧 Fix: Non-PostgreSQL SQL storage not supported, throw error directly
                                error_msg = f"Unsupported SQL storage type, system only supports PostgreSQL, no fallback mechanism"
                                self.logger.error(error_msg)
                                raise RuntimeError(error_msg)
                        # For other adapters (vector storage, etc.), try to check availability
                        else:
                            try:
                                if hasattr(adapter, 'is_available') and callable(adapter.is_available):
                                    available = await adapter.is_available()
                                    self.storage_status[storage_type] = available
                                    if available:
                                        self.logger.info(f"{storage_type} storage initialized")
                                else:
                                    self.storage_status[storage_type] = False
                            except Exception:
                                self.storage_status[storage_type] = False
                    except Exception as e:
                        # 🔧 Fix: Throw error directly when PostgreSQL-related storage fails, no fallback
                        if storage_type in ["postgres", "sql"]:
                            error_msg = f"{storage_type} storage initialization failed: {e}. System requires PostgreSQL to be running online, no fallback mechanism"
                            self.logger.error(error_msg)
                            raise RuntimeError(error_msg)
                        else:
                            self.logger.warning(f"{storage_type} storage initialization failed: {e}")
                            self.storage_status[storage_type] = False
            
            self._initialized = True

    async def store_memory(
        self, 
        memory: Any, 
        storage_types: Optional[List[str]] = None,
        execution_state: Optional['ExecutionState'] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Store a single memory object - delegate to unified storage method
        
        Args:
            memory: Memory object
            storage_types: Storage types to store
            execution_state: Execution state
            **kwargs: Additional parameters to pass to adapters
            
        Returns:
            Storage result dictionary
            
        Note:
            This method delegates to batch_store_memories to ensure unified storage path
        """
        # Delegate to unified batch storage method
        self.logger.debug("Single storage delegated to batch storage method")
        
        # Wrap single memory into list
        memories = [memory] if memory else []
        
        # Call batch storage method
        batch_results = await self.batch_store_memories(
            memories=memories,
            storage_types=storage_types,
            execution_state=execution_state,
            **kwargs
        )
        
        # Extract first result (if any)
        if batch_results:
            result = batch_results[0]
            # Convert batch storage result format to single storage result format
            single_result = {
                "memory_id": result.get("memory_id"),
                "success": result.get("success", False),
                "error": result.get("error")
            }
            
            # Add success status for each storage type
            for storage_type, storage_result in result.get("storage_results", {}).items():
                single_result[f"{storage_type}_success"] = storage_result.get("success", False)
                if not storage_result.get("success", False) and storage_result.get("error"):
                    single_result[f"{storage_type}_error"] = storage_result.get("error")
            
            return single_result
        else:
            # No memory to store
            return {"memory_id": None, "success": False, "error": "No memory to store"}

    
    async def batch_store_memories(
        self, 
        memories: List[Any], 
        storage_types: Optional[List[str]] = None,
        execution_state: Optional['ExecutionState'] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Batch store memory objects - unified storage method
        
        This is the only memory storage entry point in the system, ensuring all memory storage goes through this method
        
        Args:
            memories: List of memory objects
            storage_types: Storage types to store
            execution_state: Execution state (for state management and concurrency isolation)
            **kwargs: Additional parameters for specific adapters
            
        Returns:
            List[Dict[str, Any]]: List of storage results for each memory
        """
        await self.ensure_initialized()

        if not memories:
            self.logger.warning("Batch storage: No memories to store")
            return []

        # Ensure each memory has an ID
        processed_memories = []
        for memory in memories:
            memory_id = None
            if hasattr(memory, 'model_dump'):
                # Pydantic object
                memory_dict = memory.model_dump()
                memory_id = memory_dict.get('id')
            elif hasattr(memory, 'get'):
                # Dictionary format
                memory_id = memory.get('id')
            else:
                # Object format, try direct attribute access
                memory_id = getattr(memory, 'id', None)
            
            if not memory_id:
                # Memory without ID, generate one
                import uuid
                memory_id = str(uuid.uuid4())
                if hasattr(memory, 'model_dump'):
                    # Pydantic object cannot set attributes directly, skip
                    self.logger.warning(f"Pydantic object missing ID, skipping: {type(memory)}")
                    continue
                elif hasattr(memory, 'get'):
                    memory['id'] = memory_id
                else:
                    setattr(memory, 'id', memory_id)
            
            processed_memories.append(memory)

        # First, invalidate cache for all memories in batch
        if self.cache_adapter and await self.cache_adapter.is_available():
            for memory in processed_memories:
                memory_id = None
                if hasattr(memory, 'model_dump'):
                    memory_dict = memory.model_dump()
                    memory_id = memory_dict.get('id')
                elif hasattr(memory, 'get'):
                    memory_id = memory.get('id')
                else:
                    memory_id = getattr(memory, 'id', None)
                
                if memory_id:
                    try:
                        await self.cache_adapter.delete_memory(memory_id)
                    except Exception as e:
                        self.logger.warning(f"Failed to invalidate cache for memory {memory_id} in batch: {e}")

        if storage_types is None:
            storage_types = [k for k, v in self.storage_status.items() if v]
        
        # Initialize results for each memory
        results = []
        for memory in processed_memories:
            memory_id = None
            if hasattr(memory, 'model_dump'):
                memory_dict = memory.model_dump()
                memory_id = memory_dict.get('id')
            elif hasattr(memory, 'get'):
                memory_id = memory.get('id')
            else:
                memory_id = getattr(memory, 'id', None)
                
            results.append({
                "memory_id": memory_id,
                "success": False,
                "error": None,
                "storage_results": {}
            })
        
        # Store by storage type - this is the only storage path
        for storage_type in storage_types:
            if storage_type not in self.adapters:
                continue
                
            adapter = self.adapters[storage_type]
            if not await adapter.is_available():
                for result in results:
                    result["storage_results"][storage_type] = {"success": False, "error": f"{storage_type} not available"}
                continue
            
            try:
                # Prefer batch storage method
                if hasattr(adapter, 'batch_store_memories'):
                    self.logger.debug(f"Using batch storage: {storage_type}, memory count: {len(processed_memories)}")
                    
                    if storage_type in ['postgres', 'sql']:
                        batch_result = await adapter.batch_store_memories(processed_memories, execution_state=execution_state, **kwargs)
                    else:
                        batch_result = await adapter.batch_store_memories(processed_memories, **kwargs)
                    
                    # Handle batch storage results
                    if isinstance(batch_result, list):
                        # Returned is ID list or result list
                        for i, result in enumerate(results):
                            if i < len(batch_result):
                                if isinstance(batch_result[i], str):
                                    # Returned is ID
                                    result["storage_results"][storage_type] = {"success": True, "id": batch_result[i]}
                                    result["success"] = True
                                elif isinstance(batch_result[i], dict):
                                    # Returned is result dictionary
                                    result["storage_results"][storage_type] = batch_result[i]
                                    if batch_result[i].get("success", False):
                                        result["success"] = True
                            else:
                                result["storage_results"][storage_type] = {"success": False, "error": "No result for this memory"}
                    else:
                        # Returned is single result, apply to all memories
                        for result in results:
                            result["storage_results"][storage_type] = {"success": bool(batch_result), "result": batch_result}
                            if batch_result:
                                result["success"] = True
                else:
                    # Adapter does not support batch storage, use single storage method
                    self.logger.debug(f"Adapter does not support batch storage, using single storage: {storage_type}")
                    for i, memory in enumerate(processed_memories):
                        try:
                            if storage_type in ['postgres', 'sql']:
                                individual_result = await adapter.store_memory(memory, execution_state=execution_state, **kwargs)
                            else:
                                individual_result = await adapter.store_memory(memory, **kwargs)
                            
                            results[i]["storage_results"][storage_type] = {"success": bool(individual_result), "id": individual_result}
                            if individual_result:
                                results[i]["success"] = True
                                
                        except Exception as e:
                            results[i]["storage_results"][storage_type] = {"success": False, "error": str(e)}
                            
            except Exception as e:
                self.logger.error(f"Storage failed: {storage_type}, error: {e}")
                for result in results:
                    result["storage_results"][storage_type] = {"success": False, "error": str(e)}
        
        return results
    
    async def retrieve_memory(self, memory_id: str, preferred_storage: str = None) -> Optional[Any]:
        """
        Retrieve memory object
        
        Args:
            memory_id: Memory ID
            preferred_storage: Preferred storage type, if not provided prefer cache then SQL
            
        Returns:
            Optional[Any]: Memory object, return None if not found
        """
        await self.ensure_initialized()
        
        # Define storage query order
        storage_order = []
        
        # If preferred storage type is specified
        if preferred_storage and preferred_storage in self.adapters and self.storage_status.get(preferred_storage, False):
            storage_order.append(preferred_storage)
        
        # Add default query order: cache > SQL > vector > graph
        if "cache" not in storage_order and self.storage_status.get("cache", False):
            storage_order.append("cache")
        if "sql" not in storage_order and self.storage_status.get("sql", False):
            storage_order.append("sql")
        if "vector" not in storage_order and self.storage_status.get("vector", False):
            storage_order.append("vector")
        if "graph" not in storage_order and self.storage_status.get("graph", False):
            storage_order.append("graph")
        
        # Query each storage in order
        memory = None
        for storage_type in storage_order:
            try:
                adapter = self.adapters[storage_type]
                memory = await adapter.retrieve_memory(memory_id)
                if memory:
                    self.logger.debug(f"Retrieved memory from {storage_type} storage: {memory_id}")
                    break
            except Exception as e:
                self.logger.error(f"Failed to retrieve memory from {storage_type} storage: {e}")
        
        # If memory found from non-cache storage, cache it
        if memory and "cache" in self.adapters and self.storage_status.get("cache", False) and storage_type != "cache":
            try:
                cache_adapter = self.adapters["cache"]
                await cache_adapter.store_memory(memory)
                self.logger.debug(f"Memory cached: {memory_id}")
            except Exception as e:
                self.logger.warning(f"Failed to cache memory: {e}")
        
        return memory
    
    async def get_memory_by_id(self, memory_id: str, level: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get memory by ID, prefer cache, then SQL (if level provided), finally fallback to generic retrieval.
        """
        await self.ensure_initialized()
        memory = None

        # 1. Prefer to get from cache
        if self.cache_adapter and await self.cache_adapter.is_available():
            try:
                memory = await self.cache_adapter.retrieve_memory(memory_id)
                if memory:
                    self.logger.debug(f"Memory retrieved from cache: {memory_id}")
            except Exception as e:
                self.logger.warning(f"Failed to retrieve from cache, will fallback. Error: {e}")
                memory = None

        # 2. If cache miss, get from PostgreSQL (if level provided)
        if not memory and level and self.postgres_adapter and await self.postgres_adapter.is_available():
            self.logger.debug(f"Cache miss for {memory_id}, trying PostgreSQL with level {level}.")
            memory = await self.postgres_adapter.get_memory_by_id(memory_id, level=level)
            if memory and self.cache_adapter and await self.cache_adapter.is_available():
                try:
                    await self.cache_adapter.store_memory(memory)
                    self.logger.debug(f"Memory {memory_id} stored to cache after SQL fetch.")
                except Exception as e:
                    self.logger.warning(f"Failed to populate cache for memory {memory_id}: {e}")
        
        # 3. If still not found, use generic retrieve_memory as fallback
        if not memory:
            self.logger.debug(f"Memory {memory_id} not found in cache or by specific level, using generic retrieve.")
            memory = await self.retrieve_memory(memory_id)

        if memory is None:
            return None
        
        # Convert to dictionary format
        if hasattr(memory, 'to_dict'):
            return memory.to_dict()
        elif hasattr(memory, '__dict__'):
            return {k: v for k, v in memory.__dict__.items() if not k.startswith('_')}
        elif isinstance(memory, dict):
            return memory
        else:
            # If cannot convert, return basic attributes
            return {
                'id': getattr(memory, 'id', memory_id),
                'content': getattr(memory, 'content', ''),
                'created_at': getattr(memory, 'created_at', ''),
                'session_id': getattr(memory, 'session_id', ''),
                'user_id': getattr(memory, 'user_id', ''),
                'expert_id': getattr(memory, 'expert_id', ''),
                'layer': getattr(memory, 'layer', ''),
                'original_text': getattr(memory, 'original_text', '')
            }
    
    async def search_memories(self, query: Dict[str, Any], options: Dict[str, Any] = None, 
                           storage_type: str = None) -> List[Any]:
        """
        Search memories
        
        Args:
            query: Query conditions
            options: Search options
            storage_type: Storage type to use, auto-select if not provided
            
        Returns:
            List[Any]: List of memories matching conditions
        """
        await self.ensure_initialized()
        
        # Enhanced security check: require at least one authentication method
        has_user_group = query.get('user_group_ids') and len(query.get('user_group_ids', [])) >= 2
        has_user_id = query.get('user_id')
        has_character_ids = query.get('character_ids')
        
        if not (has_user_group or has_user_id or has_character_ids):
            self.logger.error("🚨 Security error: search_memories missing authentication parameters (user_group_ids/user_id/character_ids)")
            # ✅ New: Log security audit event
            await self._log_security_event("UNAUTHORIZED_SEARCH_ATTEMPT", {
                "query": str(query)[:200],
                "timestamp": datetime.now().isoformat()
            })
            return []
        
        # ✅ Prefer user_group_ids (strongest isolation)
        if has_user_group:
            self.logger.info(f"✅ Using user group isolation mode: {query['user_group_ids']}")
        
        # If options not provided
        if options is None:
            options = {}
        
        # Determine storage type to use
        if not storage_type:
            # Auto-select storage type based on query conditions
            if "query_text" in query:
                # Prefer PostgreSQL for full-text search
                if "postgres" in self.adapters and self.storage_status.get("postgres", False):
                    storage_type = "postgres"
                elif "vector" in query:
                    storage_type = "vector"  # Semantic query uses vector storage
                else:
                    storage_type = "postgres"  # Fallback to PostgreSQL
            elif "vector" in query:
                storage_type = "vector"  # Pure vector query
            elif "graph" in query:
                storage_type = "graph"   # Graph query uses graph storage
            else:
                # Default storage selection: PostgreSQL > Vector
                if "postgres" in self.adapters and self.storage_status.get("postgres", False):
                    storage_type = "postgres"
                else:
                    storage_type = "sql"
        
        # Ensure selected storage type is available
        if storage_type not in self.adapters or not self.storage_status.get(storage_type, False):
            # If vector storage, try to reconnect
            if storage_type == "vector" and storage_type in self.adapters:
                self.logger.info(f"Vector storage unavailable, trying to reconnect...")
                vector_adapter = self.adapters[storage_type]
                if await vector_adapter.is_available():
                    self.storage_status[storage_type] = True
                    self.logger.info("Vector storage reconnected successfully")
                else:
                    self.logger.warning("Vector storage reconnection failed, using default storage")
            
            # If still unavailable, try to use other available storage
            if not self.storage_status.get(storage_type, False):
                self.logger.warning(f"{storage_type} storage unavailable, trying to use default storage")
                # Try to use available storage (priority: postgres > sql > vector > graph > cache)
                for st in ["postgres", "sql", "vector", "graph", "cache"]:
                    if st in self.adapters and self.storage_status.get(st, False):
                        storage_type = st
                        break
                else:
                    self.logger.error("No available storage")
                    return []
        
        try:
            # Apply user group filter logic
            enhanced_query = self._apply_user_group_filter(query)
            
            # Execute search
            adapter = self.adapters[storage_type]
            # Unified interface: adapter.search_memories(query, options)
            memories = await adapter.search_memories(query=enhanced_query, options=options)
            self.logger.info(f"Found {len(memories)} memories from {storage_type} storage")
            return memories
            
        except Exception as e:
            self.logger.error(f"Failed to search memories from {storage_type} storage: {e}")
            return []
    
    def _apply_user_group_filter(self, query: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply user group filter logic, implement bidirectional filtering (union of [A,B] and [B,A])
        
        Args:
            query: Original query conditions
            
        Returns:
            Enhanced query conditions with user group filter logic
        """
        enhanced_query = query.copy()
        
        # Check if user group filtering is needed
        user_group_ids = query.get("user_group_ids")
        if not user_group_ids or len(user_group_ids) < 2:
            # If no user group IDs or less than 2 IDs, return original query
            return enhanced_query
        
        # Extract two IDs from user group
        id_a, id_b = user_group_ids[0], user_group_ids[1]
        
        # Implement bidirectional filter logic:
        # Query condition: memory must contain both IDs, but no strict role correspondence required
        # Support four combinations: (A,B), (B,A), (A,A), (B,B) - ensure memories within both parties
        user_group_filter = {
            "$or": [
                # Combination 1: A is user, B is expert
                {"user_id": id_a, "expert_id": id_b},
                # Combination 2: B is user, A is expert  
                {"user_id": id_b, "expert_id": id_a},

            ]
        }
        
        # If there are other filter conditions, need to merge
        if "user_id" in enhanced_query or "expert_id" in enhanced_query:
            # Remove original separate user_id and expert_id conditions, replace with user group condition
            enhanced_query.pop("user_id", None)
            enhanced_query.pop("expert_id", None)
        
        # Apply user group filter condition
        if "$and" in enhanced_query:
            # If already has $and condition, add to it
            enhanced_query["$and"].append(user_group_filter)
        elif any(key.startswith("$") for key in enhanced_query.keys()):
            # If already has other logical operators, wrap in $and
            other_conditions = {k: v for k, v in enhanced_query.items() if k != "user_group_ids"}
            enhanced_query = {
                "$and": [other_conditions, user_group_filter]
            }
        else:
            # Simple merge
            enhanced_query.update(user_group_filter)
        
        # ✅ Keep user_group_ids for vector adapter use (vector adapter needs original user_group_ids list)
        # PostgreSQL adapter uses $or condition, vector adapter uses user_group_ids
        # enhanced_query.pop("user_group_ids", None)  # No longer delete
        
        self.logger.info(f"Apply user group filter: user_group_ids=[{id_a}, {id_b}] -> bidirectional query condition")
        return enhanced_query
    
    async def get_memory(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """
        Get single memory object (API compatibility method)
        
        Args:
            memory_id: Memory ID
            
        Returns:
            Memory object dictionary, return None if not found
        """
        return await self.get_memory_by_id(memory_id)
    
    async def get_memory_by_id(self, memory_id: str, storage_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get memory object by memory ID (for chain backtracking)
        
        Args:
            memory_id: Memory ID
            storage_type: Storage type, default use postgres
            
        Returns:
            Memory object dictionary, return None if not found
        """
        await self.ensure_initialized()
        
        # Default use postgres storage
        if not storage_type:
            if self.storage_status.get("postgres", False):
                storage_type = "postgres"
            elif self.storage_status.get("sql", False):
                storage_type = "sql"
            else:
                self.logger.error("No available SQL storage to query memory ID")
                return None
        
        try:
            self.logger.debug(f"Query memory ID: {memory_id}, storage type: {storage_type}")
            adapter = self.adapters[storage_type]
            
            # 🔧 Fix: Call get_memory_by_id directly instead of search_memories
            # Avoid triggering user_id security check in find_memories
            memory = await adapter.get_memory_by_id(memory_id)
            
            if not memory:
                self.logger.debug(f"Memory with ID {memory_id} not found")
                return None
            
            self.logger.debug(f"Query result: memory found")
            
            # Convert Pydantic model to dictionary
            if hasattr(memory, 'model_dump'):
                memory_dict = memory.model_dump()
            elif hasattr(memory, 'dict'):
                memory_dict = memory.dict()
            elif hasattr(memory, '__dict__'):
                memory_dict = memory.__dict__.copy()
            elif isinstance(memory, dict):
                memory_dict = memory.copy()
            else:
                memory_dict = {"content": str(memory), "id": memory_id}
            
            # Ensure id field exists
            if 'id' not in memory_dict:
                memory_dict['id'] = memory_id
            
            self.logger.debug(f"Found memory by ID {memory_id}")
            return memory_dict
                
        except Exception as e:
            self.logger.error(f"Failed to query memory by ID {memory_id}: {e}", exc_info=True)
            return None
    
    async def get_parent_memories_chain(self, child_memory_id: str, target_levels: List[str] = None) -> Dict[str, Dict[str, Any]]:
        """
        Strictly chain backtrack parent memories by child memory ID (single session optimization, avoid connection pool leaks)
        Chain search in strict order L1->L2->L3->L4->L5, no skipping
        
        Optimization: Use single database session to complete entire chain backtracking, avoid:
        - Opening new session for each query causing connection pool exhaustion
        - Connection leaks from unclosed sessions
        
        Args:
            child_memory_id: Child memory ID (usually L1 memory)
            target_levels: Target level list, e.g. ["L2", "L3", "L4", "L5"]
            
        Returns:
            Dict[level, memory]: Parent memory dictionary for each level
        """
        if target_levels is None:
            target_levels = ["L2", "L3", "L4", "L5"]
        
        result_chain = {}
        current_memory_id = child_memory_id
        
        try:
            # Ensure PostgreSQL adapter is available
            if not self.postgres_adapter:
                self.logger.error("PostgreSQL adapter unavailable")
                return {}
            
            store = await self.postgres_adapter._ensure_store()
            
            # Key optimization: Use single session to complete entire chain backtracking
            async with store.get_session() as session:
                # Strictly backtrack by level order: L2 -> L3 -> L4 -> L5
                # target_levels is actually complete backtracking chain (should be named chain_levels)
                for target_level in target_levels:
                    # Query parent memory relationships in current session
                    parent_ids = await self._get_parent_ids_in_session(session, current_memory_id)
                    if not parent_ids:
                        self.logger.debug(f"Memory {current_memory_id} has no parent memory, stop chain backtracking")
                        break
                    
                    # Find target level parent memory in current session
                    found_parent = None
                    for parent_id in parent_ids:
                        parent_memory = await self._get_memory_in_session(session, parent_id, target_level)
                        if not parent_memory:
                            continue
                        
                        parent_level = parent_memory.get('level')
                        if parent_level == target_level:
                            found_parent = parent_memory
                            result_chain[target_level] = parent_memory
                            current_memory_id = parent_id  # Prepare for next level search
                            self.logger.debug(f"Found {target_level} parent memory: {parent_memory.get('title', 'untitled')[:50]}")
                            break
                    
                    # If no parent memory found for current level, stop chain backtracking
                    if not found_parent:
                        self.logger.debug(f"No parent memory found for {target_level} level, stop chain backtracking")
                        break
            
            # Session will auto-close when async with ends
            self.logger.info(f"Parent memory chain backtracking completed: {list(result_chain.keys())}")
            return result_chain
            
        except ImportError as e:
            self.logger.error(f" asyncpg not installed or import failed: {e}")
            return {}
        except Exception as e:
            # Check if connection pool related error
            error_msg = str(e).lower()
            if 'too many connections' in error_msg or 'connection pool' in error_msg:
                self.logger.error(f" SQL connection pool exhausted: {e}", exc_info=True)
            elif 'postgres' in error_msg or 'database' in error_msg:
                self.logger.error(f" PostgreSQL error: {e}", exc_info=True)
            else:
                self.logger.error(f" Chain backtracking failed {child_memory_id}: {e}", exc_info=True)
            return {}
    
    async def _get_parent_ids_in_session(self, session, child_id: str) -> List[str]:
        """
        Query parent memory IDs in given session (avoid opening new session)
        
        Args:
            session: Already opened AsyncSession
            child_id: Child memory ID
            
        Returns:
            List[str]: List of parent memory IDs
        """
        try:
            from storage.postgres_store import MemoryChildRelation
            from sqlalchemy import select
            
            stmt = select(MemoryChildRelation.parent_id).where(
                MemoryChildRelation.child_id == child_id
            )
            result = await session.execute(stmt)
            parent_ids = [row[0] for row in result.fetchall()]
            
            self.logger.debug(f"Memory {child_id} found {len(parent_ids)} parent memories: {parent_ids[:3]}...")
            return parent_ids
            
        except Exception as e:
            self.logger.error(f"Failed to query parent memory relationships in session {child_id}: {e}")
            return []
    
    async def _get_memory_in_session(self, session, memory_id: str, expected_level: str = None) -> Optional[Dict[str, Any]]:
        """
        Query memory in given session (get complete content from CoreMemory table, avoid opening new session)
        
        Fix: L2-L5 tables are only association tables, content stored in CoreMemory, need to verify level then query CoreMemory
        
        Args:
            session: Already opened AsyncSession
            memory_id: Memory ID (parent_id, which is core_memory's id)
            expected_level: Expected level (L1-L5), skip level validation if None
            
        Returns:
            Optional[Dict]: Memory dictionary, return None if not found
        """
        try:
            from storage.postgres_store import CoreMemory
            from sqlalchemy import select
            
            # Key fix: Query directly from CoreMemory table
            # 🔧 Key fix: Query directly from CoreMemory table
            # parent_id is core_memory's id, can query directly with it
            stmt = select(CoreMemory).where(CoreMemory.id == memory_id)
            result = await session.execute(stmt)
            row = result.fetchone()
            
            if not row:
                return None
            
            core_memory = row[0]
            actual_level = core_memory.level
            
            # 🔧 Fix: If expected_level is None, skip level validation (for skip-level backtracking)
            if expected_level is not None and actual_level != expected_level:
                self.logger.debug(f"Memory {memory_id} level mismatch: expected {expected_level}, actual {actual_level}")
                return None
            
            # Convert to dictionary
            memory_dict = {
                'id': core_memory.id,
                'memory_id': core_memory.id,  # Backward compatible field
                'user_id': core_memory.user_id,
                'expert_id': core_memory.expert_id,
                'level': core_memory.level,
                'title': core_memory.title,
                'content': core_memory.content,
                'status': core_memory.status,
                'created_at': core_memory.created_at.isoformat() if core_memory.created_at else None,
                'updated_at': core_memory.updated_at.isoformat() if core_memory.updated_at else None,
                'time_window_start': core_memory.time_window_start.isoformat() if core_memory.time_window_start else None,
                'time_window_end': core_memory.time_window_end.isoformat() if core_memory.time_window_end else None,
            }
            
            # For L2, try to supplement session_id (based on actual_level)
            if actual_level == "L2":
                try:
                    from storage.postgres_store import L2SessionMemory
                    stmt_l2 = select(L2SessionMemory).where(L2SessionMemory.memory_id == memory_id)
                    result_l2 = await session.execute(stmt_l2)
                    row_l2 = result_l2.fetchone()
                    if row_l2:
                        memory_dict['session_id'] = row_l2[0].session_id
                except:
                    pass
            
            return memory_dict
            
        except Exception as e:
            self.logger.warning(f"Failed to query memory in session {memory_id} (level={expected_level}): {e}")
            return None
    
    async def check_pool_health(self) -> Dict[str, Any]:
        """
        Check connection pool health status
        
        Returns:
            Dict: Connection pool status information, including utilization_percent etc
        """
        try:
            if not self.postgres_adapter:
                return {"available": False, "error": "PostgreSQL adapter not available"}
            
            # Try to get status from unified connection pool manager
            try:
                from timem.core.unified_connection_manager import get_unified_connection_manager, ConnectionPoolType
                
                manager = await get_unified_connection_manager()
                stats = await manager.get_stats(ConnectionPoolType.POSTGRES)
                
                if stats:
                    utilization = 0
                    if stats.total_connections > 0:
                        utilization = (stats.checked_out / stats.total_connections) * 100
                    
                    return {
                        "available": True,
                        "pool_size": stats.pool_size,
                        "checked_in": stats.checked_in,
                        "checked_out": stats.checked_out,
                        "overflow": stats.overflow,
                        "total_connections": stats.total_connections,
                        "utilization_percent": utilization,
                        "status": stats.status,
                        "error_count": stats.error_count,
                        "warning_count": stats.warning_count
                    }
            except Exception as e:
                self.logger.debug(f"Unable to get status from unified connection pool manager: {e}")
            
            # Fallback: return basic status
            return {
                "available": True,
                "utilization_percent": 0,
                "status": "unknown"
            }
            
        except Exception as e:
            self.logger.error(f"Failed to check connection pool health status: {e}")
            return {
                "available": False,
                "error": str(e),
                "utilization_percent": 0
            }
    
    async def get_parent_memory_ids_from_relations(self, child_memory_id: str) -> List[str]:
        """
        Query parent memory ID list from memory_child_relations table
        
        Args:
            child_memory_id: Child memory ID
            
        Returns:
            List[str]: List of parent memory IDs
        """
        await self.ensure_initialized()
        
        try:
            if not self.postgres_adapter:
                self.logger.error("PostgreSQL adapter unavailable")
                return []
            
            # Use PostgreSQL storage to directly query relations table
            store = await self.postgres_adapter._ensure_store()
            
            # Use AsyncSession to execute query
            async with store.get_session() as session:
                from storage.postgres_store import MemoryChildRelation
                from sqlalchemy import select
                
                # Query parent_id
                stmt = select(MemoryChildRelation.parent_id).where(
                    MemoryChildRelation.child_id == child_memory_id
                )
                result = await session.execute(stmt)
                parent_ids = [row[0] for row in result.fetchall()]
                
                self.logger.debug(f"Memory {child_memory_id} found {len(parent_ids)} parent memories: {parent_ids[:3]}...")
                return parent_ids
            
        except Exception as e:
            self.logger.error(f"Failed to query parent memory relationships {child_memory_id}: {e}")
            return []
    
    async def update_memory(self, memory_id: str, updates: Dict[str, Any], storage_types: Optional[List[str]] = None) -> Dict[str, bool]:
        """
        Update memory object
        
        Args:
            memory_id: Memory ID
            updates: Fields to update
            storage_types: Storage types to update, update all available if not provided
            
        Returns:
            Dict[str, bool]: Update results for each storage type
        """
        await self.ensure_initialized()
        
        # Determine storage types to update
        if storage_types is None:
            storage_types = [k for k, v in self.storage_status.items() if v]
        
        results = {}
        
        # Update each storage in sequence
        for storage_type in storage_types:
            if storage_type in self.adapters and self.storage_status.get(storage_type, False):
                try:
                    adapter = self.adapters[storage_type]
                    success = await adapter.update_memory(memory_id, updates)
                    results[storage_type] = success
                    self.logger.debug(f"Memory update {'succeeded' if success else 'failed'} in {storage_type} storage: {memory_id}")
                except Exception as e:
                    self.logger.error(f"Failed to update memory in {storage_type} storage: {e}")
                    results[storage_type] = False
        
        return results
    
    async def delete_memory(self, memory_id: str, level: Optional[str] = None, storage_types: Optional[List[str]] = None, **kwargs) -> Dict[str, Any]:
        """
        Delete memory object
        
        Args:
            memory_id: Memory ID
            level: Memory level, used to determine storage table
            storage_types: Storage types to delete, delete all available if not provided
            **kwargs: Additional parameters for specific adapters (e.g. wait_for_vector_indexing=True)
            
        Returns:
            Dict[str, Any]: Delete result dictionary with success key
        """
        await self.ensure_initialized()

        # **Key: Always invalidate cache before delete**
        if self.cache_adapter and await self.cache_adapter.is_available():
            try:
                await self.cache_adapter.delete_memory(memory_id)
                self.logger.debug(f"Cache invalidated for memory_id: {memory_id} before deleting.")
            except Exception as e:
                self.logger.warning(f"Failed to invalidate cache for memory {memory_id} on delete: {e}")
        
        # Determine storage types to delete
        if storage_types is None:
            storage_types = [k for k, v in self.storage_status.items() if v]
        
        results = {}
        overall_success = False
        
        # Delete each storage in sequence
        for storage_type in storage_types:
            adapter = self.adapters.get(storage_type)
            if adapter and self.storage_status.get(storage_type, False):
                try:
                    params = {"memory_id": memory_id}
                    # Only pass level to adapters that need it (currently only vector adapter)
                    if storage_type == 'vector' and level:
                        params["level"] = level
                    
                    # Pass additional parameters to vector adapter
                    if storage_type == 'vector':
                        params.update(kwargs)

                    success = await adapter.delete_memory(**params)
                    
                    results[storage_type] = success
                    if success:
                        overall_success = True
                    self.logger.debug(f"Memory in {storage_type} delete success={success}: {memory_id}")
                except Exception as e:
                    self.logger.error(f"Failed to delete memory from {storage_type}: {e}", exc_info=True)
                    results[storage_type] = False
        
        return {"success": overall_success, "results": results}
    
    async def delete_memories_by_session(self, user_id: str, expert_id: str, session_id: str, 
                                      storage_types: Optional[List[str]] = None, **kwargs) -> Dict[str, Any]:
        """
        Precisely delete all memories of specified session
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            session_id: Session ID
            storage_types: Storage types to delete, delete all available if not provided
            **kwargs: Additional parameters for specific adapters
            
        Returns:
            Dict[str, Any]: Dictionary with deletion result details
        """
        await self.ensure_initialized()
        
        # First get all memories of this session (only find L1 and L2 levels, because L3-L5 not stored by session)
        all_memories = []
        for layer in ["L1", "L2"]:  # Only find levels that support session_id
            try:
                memories = await self.get_memories_by_session(user_id, expert_id, session_id, layer)
                if memories:
                    all_memories.extend(memories)
                    self.logger.info(f"Found {len(memories)} {layer} memories in session {session_id}")
            except Exception as e:
                self.logger.warning(f"Failed to find {layer} memories: {e}")
        
        # For L3-L5 levels, since they are not directly associated with specific sessions, need special handling
        # But in this delete operation, we mainly focus on precise deletion of L1 and L2 memories
        
        if not all_memories:
            self.logger.info(f"No memories found in session {session_id}")
            return {"success": True, "deleted_count": 0, "memory_ids": []}
        
        # Determine storage types to delete
        if storage_types is None:
            # For delete operation, we need to check all possibly available storage, not just connected ones
            available_storage_types = []
            for storage_type in ['sql', 'vector', 'graph', 'cache']:
                if storage_type in self.adapters:
                    # For vector storage, try to connect to ensure availability
                    if storage_type == 'vector' and not self.storage_status.get('vector', False):
                        try:
                            vector_adapter = self.adapters['vector']
                            if await vector_adapter.is_available():
                                self.storage_status['vector'] = True
                                available_storage_types.append(storage_type)
                        except Exception as e:
                            self.logger.warning(f"Vector storage unavailable: {e}")
                    elif self.storage_status.get(storage_type, False):
                        available_storage_types.append(storage_type)
            
            storage_types = available_storage_types
        
        self.logger.info(f"Available storage types: {storage_types}")
        self.logger.info(f"Storage status: {self.storage_status}")
        
        deleted_memory_ids = []
        deletion_results = {}
        total_deleted = 0
        
        # Delete memories one by one
        for memory in all_memories:
            memory_id = memory.get("id") if isinstance(memory, dict) else getattr(memory, "id", None)
            if not memory_id:
                continue
                
            layer = memory.get("level") if isinstance(memory, dict) else getattr(memory, "level", None)
            # If level is enum object, convert to string
            if hasattr(layer, 'value'):
                layer = layer.value
            
            # Invalidate cache
            if self.cache_adapter and await self.cache_adapter.is_available():
                try:
                    await self.cache_adapter.delete_memory(memory_id)
                except Exception as e:
                    self.logger.warning(f"Failed to invalidate cache for memory {memory_id}: {e}")
            
            # Delete from each storage
            memory_deletion_success = False
            for storage_type in storage_types:
                adapter = self.adapters.get(storage_type)
                if adapter and self.storage_status.get(storage_type, False):
                    try:
                        params = {"memory_id": memory_id}
                        # Pass level information to vector adapter
                        if storage_type == 'vector' and layer:
                            params["level"] = layer
                        
                        # Pass additional parameters to vector adapter
                        if storage_type == 'vector':
                            params.update(kwargs)
                        
                        success = await adapter.delete_memory(**params)
                        
                        if storage_type not in deletion_results:
                            deletion_results[storage_type] = []
                        deletion_results[storage_type].append({
                            "memory_id": memory_id,
                            "success": success
                        })
                        
                        if success:
                            memory_deletion_success = True
                            
                    except Exception as e:
                        self.logger.error(f"Failed to delete memory {memory_id} from {storage_type}: {e}")
                        if storage_type not in deletion_results:
                            deletion_results[storage_type] = []
                        deletion_results[storage_type].append({
                            "memory_id": memory_id,
                            "success": False,
                            "error": str(e)
                        })
            
            if memory_deletion_success:
                deleted_memory_ids.append(memory_id)
                total_deleted += 1
                self.logger.info(f"Successfully deleted memory: {memory_id}")
            else:
                self.logger.warning(f"Failed to delete memory: {memory_id}")
        
        self.logger.info(f"Session {session_id} deletion completed: {total_deleted}/{len(all_memories)} memories")
        
        return {
            "success": total_deleted > 0,
            "deleted_count": total_deleted,
            "total_found": len(all_memories),
            "memory_ids": deleted_memory_ids,
            "deletion_results": deletion_results
        }
    
    # Helper method: Get session dialogue history
    async def get_session_dialogues(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Get dialogue history of session
        
        Query all dialogue turns of specified session from dialogue_originals table
        
        Args:
            session_id: Session ID
            
        Returns:
            Dialogue history list, sorted by turn_number
        """
        await self.ensure_initialized()
        
        try:
            # Prefer PostgreSQL adapter
            if self.postgres_adapter and self.storage_status.get("postgres", False):
                dialogues = await self.postgres_adapter.get_session_dialogues(session_id)
            # Fallback to SQL adapter
            elif self.postgres_adapter and self.storage_status.get("postgres", False):
                dialogues = await self.postgres_adapter.get_session_dialogues(session_id)
            else:
                self.logger.warning("No available SQL storage adapter to get dialogue history")
                dialogues = []
            
            self.logger.info(f"Retrieved dialogue history for session {session_id}: {len(dialogues)} records")
            return dialogues
            
        except Exception as e:
            self.logger.error(f"Failed to get session dialogue history: {e}", exc_info=True)
            return []
    
    async def list_memories(self, filters: Dict[str, Any], page: int = 1, size: int = 20, 
                           sort_by: str = "created_at", order: str = "desc") -> Dict[str, Any]:
        """
        Get memory list (support filtering, pagination and sorting)
        
        Args:
            filters: Filter conditions dictionary (layer, user_id, expert_id, session_id, status etc)
            page: Page number (starting from 1)
            size: Page size
            sort_by: Sort field
            order: Sort direction (asc/desc)
            
        Returns:
            Dictionary containing memories and total
        """
        await self.ensure_initialized()
        
        # � Security enhancement: Force require user_id parameter
        if "user_id" not in filters or not filters["user_id"]:
            self.logger.error("🚨 Security error: list_memories call missing user_id parameter, rejecting query")
            return {"memories": [], "total": 0}
        
        try:
            # Build query conditions
            query = {}
            options = {
                "limit": size,
                "offset": (page - 1) * size,
                "sort_by": sort_by,
                "sort_order": order
            }
            
            # Extract query conditions from filters
            # ✅ Fix: Support both layer and level parameters
            if "layer" in filters:
                query["level"] = filters["layer"]
            elif "level" in filters:
                query["level"] = filters["level"]
            
            # � Force user filtering
            query["user_id"] = filters["user_id"]
            
            if "expert_id" in filters:
                query["expert_id"] = filters["expert_id"]
            if "session_id" in filters:
                query["session_id"] = filters["session_id"]
            if "status" in filters:
                query["status"] = filters["status"]
            
            # Time range filtering
            if "start_time" in filters:
                options["start_time"] = filters["start_time"]
            if "end_time" in filters:
                options["end_time"] = filters["end_time"]
            
            # Use search_memories method to query
            memories = await self.search_memories(query, options, storage_type="sql")
            
            # Convert to dictionary format
            memories_list = []
            for mem in memories:
                if isinstance(mem, dict):
                    memories_list.append(mem)
                else:
                    # Memory object to dictionary
                    mem_dict = mem.model_dump() if hasattr(mem, 'model_dump') else mem.__dict__
                    memories_list.append(mem_dict)
            
            self.logger.info(f"Query memory list: filters={filters}, returned={len(memories_list)} records")
            
            return {
                "memories": memories_list,
                "total": len(memories_list)  # Note: this returns current query result count, not total
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get memory list: {e}", exc_info=True)
            return {
                "memories": [],
                "total": 0
            }
    
    # Helper method: Query by time window
    async def get_memories_by_time_window(self, user_id: str, expert_id: str, layer: str, 
                                       start_time: datetime, end_time: datetime) -> List[Any]:
        """Get memory list by time window (pass time window to options, use level field)."""
        query = {
            "user_id": user_id,
            "expert_id": expert_id,
            "level": layer,
        }
        options = {
            "start_time": start_time,
            "end_time": end_time,
        }
        return await self.search_memories(query, options)
    
    async def get_memories_by_session(self, user_id: str, expert_id: str, session_id: str, layer: str) -> List[Any]:
        """Get memory list by session ID"""
        query = {
            "user_id": user_id,
            "expert_id": expert_id,
            "session_id": session_id,
            "level": layer  # ✅ Fix: Use level instead of layer, consistent with database field
        }
        return await self.search_memories(query)
    
    async def get_memories_by_date(self, user_id: str, expert_id: str, layer: str, date: datetime) -> List[Any]:
        """Get memory list by date"""
        start_date = datetime(date.year, date.month, date.day)
        end_date = start_date + timedelta(days=1) - timedelta(microseconds=1)
        return await self.get_memories_by_time_window(user_id, expert_id, layer, start_date, end_date)
    
    async def get_memories_by_week(self, user_id: str, expert_id: str, layer: str, week_start: datetime) -> List[Any]:
        """Get memory list by week start date"""
        start_date = week_start
        end_date = start_date + timedelta(days=7) - timedelta(microseconds=1)
        return await self.get_memories_by_time_window(user_id, expert_id, layer, start_date, end_date)
    
    async def get_memories_by_month(self, user_id: str, expert_id: str, layer: str, month_start: datetime) -> List[Any]:
        """Get memory list by month start date"""
        start_date = month_start
        # Calculate first day of next month
        if month_start.month == 12:
            next_month = month_start.replace(year=month_start.year + 1, month=1)
        else:
            next_month = month_start.replace(month=month_start.month + 1)
        end_date = next_month - timedelta(microseconds=1)
        return await self.get_memories_by_time_window(user_id, expert_id, layer, start_date, end_date)
    
    async def get_memory_count(self, user_id: str, expert_id: str, layer: str, 
                             start_date: Optional[datetime] = None, 
                             end_date: Optional[datetime] = None) -> int:
        """Get count of memories matching conditions"""
        query = {
            "user_id": user_id,
            "expert_id": expert_id,
            "level": layer
        }
        options = {}
        if start_date:
            options["start_time"] = start_date
        if end_date:
            options["end_time"] = end_date
        
        memories = await self.search_memories(query, options)
        return len(memories)
    
    # Semantic search method
    async def semantic_search(self, query_text: str, user_id: Optional[str] = None, 
                           expert_id: Optional[str] = None, layer: Optional[str] = None,
                           limit: int = 10) -> List[Any]:
        """
        Semantic search memories
        
        Args:
            query_text: Query text
            user_id: User ID
            expert_id: Expert ID
            layer: Memory level
            limit: Maximum number of results to return
            
        Returns:
            List[Any]: List of related memories
        """
        await self.ensure_initialized()
        
        # Ensure vector storage is available
        if "vector" not in self.adapters or not self.storage_status.get("vector", False):
            self.logger.error("Vector storage unavailable, cannot perform semantic search")
            return []
        
        try:
            # Build vector search query
            query = {
                "query_text": query_text
            }
            if user_id:
                query["user_id"] = user_id
            if expert_id:
                query["expert_id"] = expert_id
            if layer:
                query["layer"] = layer
                
            options = {
                "limit": limit,
                "score_threshold": 0.0  # Adjust to lowest threshold to ensure all questions can match
            }
            
            # Execute vector search
            memories = await self.search_memories(query, options, storage_type="vector")
            self.logger.info(f"Semantic search successful, found {len(memories)} records")
            return memories
            
        except Exception as e:
            self.logger.error(f"Semantic search failed: {e}")
            return []
    
    async def search_similar_memories(self, user_id: str, expert_id: str, query_text: str, 
                                   limit: int = 10, level: Optional[str] = None,
                                   score_threshold: Optional[float] = None) -> List[Any]:
        """
        Search similar memories (alias for semantic_search)
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            query_text: Query text
            limit: Result count limit
            level: Memory level (optional)
            score_threshold: Score threshold (optional)
            
        Returns:
            List[Any]: List of similar memories
        """
        if self.vector_adapter and await self.vector_adapter.is_available():
            try:
                return await self.vector_adapter.search(
                    user_id=user_id,
                    expert_id=expert_id,
                    query_text=query_text,
                    limit=limit,
                    level=level,
                    score_threshold=score_threshold
                )
            except Exception as e:
                self.logger.error(f"Semantic search failed: {e}")
                return []
        
        self.logger.warning("Vector storage unavailable, cannot perform semantic search")
        return []
    
    # Graph structure query method
    async def get_memory_graph(self, memory_id: str, depth: int = 2) -> Dict[str, Any]:
        """
        Get memory graph structure
        
        Args:
            memory_id: Memory ID
            depth: Graph traversal depth
            
        Returns:
            Dict[str, Any]: Graph structure data
        """
        await self.ensure_initialized()
        
        # Ensure graph storage is available
        if "graph" not in self.adapters or not self.storage_status.get("graph", False):
            self.logger.error("Graph storage unavailable, cannot get memory graph structure")
            return {"nodes": [], "relationships": []}
        
        try:
            # Use graph adapter to get memory graph structure
            graph_adapter = self.adapters["graph"]
            if hasattr(graph_adapter, "get_memory_graph"):
                return await graph_adapter.get_memory_graph(memory_id, depth)
            else:
                self.logger.warning("Graph adapter does not support get_memory_graph method")
                return {"nodes": [], "relationships": []}
        except Exception as e:
            self.logger.error(f"Failed to get memory graph structure: {e}")
            return {"nodes": [], "relationships": []}
    
    # Close connections
    async def close(self):
        """Close all storage connections"""
        for storage_type, adapter in self.adapters.items():
            try:
                if hasattr(adapter, 'disconnect') and callable(adapter.disconnect):
                    await adapter.disconnect()
                    self.logger.info(f"{storage_type} storage connection closed")
                elif hasattr(adapter, 'close') and callable(adapter.close):
                    try:
                        if asyncio.iscoroutinefunction(adapter.close):
                            await adapter.close()
                        else:
                            adapter.close()
                    except RuntimeError:
                        # Cleanup after event loop closure
                        try:
                            adapter.close()
                        except Exception:
                            pass
                    self.logger.info(f"{storage_type} storage connection closed")
                else:
                    self.logger.warning(f"{storage_type} adapter has no disconnect or close method")
                    
                self.storage_status[storage_type] = False
            except Exception as e:
                self.logger.error(f"Error closing {storage_type} storage connection: {e}")
        
        self._initialized = False
        self.logger.info("All storage connections closed")
    
    def get_connection_pool_status(self) -> Dict[str, Any]:
        """
        Get connection pool status for all storage adapters
        
        Returns:
            Dict[str, Any]: Connection pool status for each storage adapter
        """
        status = {
            "timestamp": time.time(),
            "adapters": {},
            "overall_status": "unknown"
        }
        
        # Check PostgreSQL connection pool status
        if hasattr(self, 'postgres_adapter') and self.postgres_adapter:
            try:
                if hasattr(self.postgres_adapter, 'get_connection_pool_status'):
                    postgres_status = self.postgres_adapter.get_connection_pool_status()
                    status["adapters"]["postgres"] = postgres_status
                else:
                    status["adapters"]["postgres"] = {"status": "unknown"}
            except Exception as e:
                status["adapters"]["postgres"] = {"status": "error", "error": str(e)}
        
        # PostgreSQL connection pool status already checked above, no need to repeat
        
        # Check vector storage status
        if self.vector_adapter:
            try:
                if hasattr(self.vector_adapter, 'is_available'):
                    # Note: cannot use await here because get_connection_pool_status is synchronous method
                    # Vector storage status check will be done asynchronously in monitor_connection_pools
                    status["adapters"]["vector"] = {"status": "unknown"}
                else:
                    status["adapters"]["vector"] = {"status": "unknown"}
            except Exception as e:
                status["adapters"]["vector"] = {"status": "error", "error": str(e)}
        
        # Calculate overall status
        adapter_statuses = [adapter.get("status", "unknown") for adapter in status["adapters"].values()]
        if "exhausted" in adapter_statuses:
            status["overall_status"] = "exhausted"
        elif "error" in adapter_statuses:
            status["overall_status"] = "error"
        elif "high_utilization" in adapter_statuses:
            status["overall_status"] = "high_utilization"
        elif all(s in ["healthy", "available"] for s in adapter_statuses):
            status["overall_status"] = "healthy"
        else:
            status["overall_status"] = "mixed"
        
        return status
    
    async def monitor_connection_pools(self) -> Dict[str, Any]:
        """
        Monitor all connection pool status, detect potential issues
        
        Returns:
            Dict[str, Any]: Monitoring results and recommendations
        """
        status = self.get_connection_pool_status()
        issues = []
        recommendations = []
        
        # Check PostgreSQL connection pool
        if "postgres" in status["adapters"]:
            postgres_status = status["adapters"]["postgres"]
            if postgres_status.get("status") == "exhausted":
                issues.append("PostgreSQL connection pool exhausted")
                recommendations.append("Increase PostgreSQL connection pool size or reduce concurrent connections")
            elif postgres_status.get("status") == "high_utilization":
                issues.append("PostgreSQL connection pool utilization too high")
                recommendations.append("Consider increasing PostgreSQL connection pool size")
            elif postgres_status.get("utilization_percent", 0) > 80:
                issues.append(f"PostgreSQL connection pool utilization too high: {postgres_status.get('utilization_percent')}%")
                recommendations.append("Monitor PostgreSQL connection pool usage")
        
        # Check SQL adapter
        if "sql" in status["adapters"]:
            sql_status = status["adapters"]["sql"]
            if sql_status.get("status") == "exhausted":
                issues.append("SQL adapter connection pool exhausted")
                recommendations.append("Check SQL adapter connection pool configuration")
        
        # Check vector storage
        if "vector" in status["adapters"]:
            vector_status = status["adapters"]["vector"]
            if vector_status.get("status") == "unavailable":
                issues.append("Vector storage unavailable")
                recommendations.append("Check vector storage connection status")
        
        # Asynchronously check vector storage status
        if self.vector_adapter:
            try:
                if hasattr(self.vector_adapter, 'is_available'):
                    vector_available = await self.vector_adapter.is_available()
                    if not vector_available:
                        issues.append("Vector storage connection unavailable")
                        recommendations.append("Check vector storage connection status")
            except Exception as e:
                issues.append(f"Vector storage status check failed: {e}")
                recommendations.append("Check vector storage configuration")
        
        return {
            "status": status,
            "issues": issues,
            "recommendations": recommendations,
            "timestamp": time.time()
        }
    
    async def close_all_connections(self):
        """
        Force close all storage connections
        
        This method will try to close all possible connections, including:
        1. Storage adapter connections
        2. SQL connection pools and connections
        3. Vector storage client
        4. Graph database sessions and drivers
        5. Redis connections
        
        Regardless of whether an error occurs, it will attempt to close all connections
        """
        self.logger.info("Attempting to force close all storage connections...")
        
        # First try to close normally
        try:
            await self.close()
        except Exception as e:
            self.logger.error(f"Failed to close all connections: {e}", exc_info=True)
        
        # SQL adapter has been removed, only using PostgreSQL
        
        # PostgreSQL adapter specific close
        if hasattr(self, 'postgres_adapter') and self.postgres_adapter:
            try:
                if hasattr(self.postgres_adapter, 'cleanup_connection_pool'):
                    success = await self.postgres_adapter.cleanup_connection_pool()
                    if success:
                        self.logger.info("✅ PostgreSQL connection pool cleanup successful")
                    else:
                        self.logger.warning("⚠️ PostgreSQL connection pool cleanup incomplete")
                elif hasattr(self.postgres_adapter, 'force_close_all_connections'):
                    await self.postgres_adapter.force_close_all_connections()
                    self.logger.info("PostgreSQL connection pool forcefully cleaned")
            except Exception as e:
                self.logger.error(f"Failed to close PostgreSQL connection pool: {e}")
        
        # Vector storage specific close
        if self.vector_adapter:
            try:
                if hasattr(self.vector_adapter, 'client') and self.vector_adapter.client:
                    try:
                        # Most vector clients don't have explicit close methods, just set to None
                        self.vector_adapter.client = None
                        self.logger.info("Vector storage client released")
                    except Exception as e:
                        self.logger.error(f"Failed to release vector client: {e}")
            except Exception as e:
                self.logger.error(f"Failed to close vector storage: {e}")
                
        # Graph storage specific close
        if self.graph_adapter:
            try:
                # Close Neo4j driver and sessions
                if hasattr(self.graph_adapter, 'store') and self.graph_adapter.store:
                    if hasattr(self.graph_adapter.store, 'close_driver') and callable(self.graph_adapter.store.close_driver):
                        await self.graph_adapter.store.close_driver()
                        self.logger.info("Graph storage driver closed")
            except Exception as e:
                self.logger.error(f"Failed to close graph storage driver: {e}")
        
        # Cache adapter specific close
        if self.cache_adapter:
            try:
                if hasattr(self.cache_adapter, 'manager') and self.cache_adapter.manager:
                    if hasattr(self.cache_adapter.manager, 'close') and callable(self.cache_adapter.manager.close):
                        self.cache_adapter.manager.close()
                        self.logger.info("Cache connection closed")
            except Exception as e:
                self.logger.error(f"Failed to close cache connection: {e}")
        
        # Reset status and references
        for key in self.storage_status:
            self.storage_status[key] = False
            
        self.adapters = {}
        # self.sql_adapter has been removed, only using postgres_adapter
        self.vector_adapter = None
        self.graph_adapter = None
        self.cache_adapter = None
        self.default_adapter = None
        self._initialized = False
        
        self.logger.info("All storage connections forcefully closed")
        return True  # Return cleanup success flag
    
    async def _log_security_event(self, event_type: str, details: Dict[str, Any]):
        """
        Log security audit event
        
        Args:
            event_type: Event type (e.g., UNAUTHORIZED_SEARCH_ATTEMPT)
            details: Event details
        """
        try:
            audit_log = {
                "event_type": event_type,
                "timestamp": datetime.now().isoformat(),
                "details": details
            }
            self.logger.warning(f"🔐 Security audit: {event_type} - {details}")
            
            # TODO: Optionally write to dedicated audit log table
            # if self.postgres_adapter and await self.postgres_adapter.is_available():
            #     await self.postgres_adapter.log_security_event(audit_log)
        except Exception as e:
            self.logger.error(f"Failed to log security event: {e}")


_storage_manager_instance_async: MemoryStorageManager | None = None
_storage_manager_lock = asyncio.Lock()

# Factory method (sync version keeps original behavior: returns new instance each time)
def get_memory_storage_manager() -> MemoryStorageManager:
    """Get memory storage manager (sync version)"""
    return MemoryStorageManager()

async def get_memory_storage_manager_async() -> MemoryStorageManager:
    """Get memory storage manager (async singleton) - PostgreSQL priority"""
    global _storage_manager_instance_async
    if _storage_manager_instance_async is None:
        async with _storage_manager_lock:
            if _storage_manager_instance_async is None:
                storage_manager = MemoryStorageManager()
                
                # Use unified adapter creation logic, PostgreSQL priority
                await storage_manager._create_default_adapters()
                
                # Set vector adapter (lazy connection)
                try:
                    from storage.vector_adapter import VectorAdapter
                    vector_adapter = VectorAdapter(storage_manager.config_manager)
                    storage_manager.vector_adapter = vector_adapter
                    storage_manager.adapters["vector"] = vector_adapter
                    storage_manager.storage_status["vector"] = False
                    storage_manager.logger.info("Vector adapter registered in singleton manager (lazy connection)")
                except Exception as e:
                    storage_manager.logger.warning(f"Failed to register vector adapter (can be ignored, retry later): {e}")

                # Important: Call ensure_initialized to update status, then mark as initialized
                await storage_manager.ensure_initialized()
                
                # Ensure there is an available default adapter
                if not storage_manager.default_adapter:
                    storage_manager.logger.error("No available storage adapter")
                    raise RuntimeError("Storage manager initialization failed: no available adapters")
                
                adapter_type = type(storage_manager.default_adapter).__name__
                storage_manager.logger.info(f"Storage manager async singleton initialization complete, default adapter: {adapter_type}")
                storage_manager.logger.info(f"Storage status: {storage_manager.storage_status}")
                
                _storage_manager_instance_async = storage_manager
    return _storage_manager_instance_async