"""
TiMem Unified Memory Indexer

Provides unified memory indexing logic to replace duplicate indexing code in various processors
"""

from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import logging
import json
import time
import asyncio
from functools import lru_cache

from timem.workflows.state import MemoryState
from timem.utils.time_window_calculator import TimeWindowCalculator
from storage.memory_storage_manager import get_memory_storage_manager_async
from timem.utils.logging import get_logger
from timem.utils.time_utils import parse_time, ensure_iso_string, get_utc_now

logger = get_logger(__name__)

class UnifiedMemoryIndexer:
    """Unified memory indexer"""
    
    def __init__(self):
        """Initialize unified memory indexer"""
        self._storage_manager = None
        self.time_calculator = TimeWindowCalculator()
        self._cache = {}  # In-memory cache
        self._cache_ttl = 300  # Cache time-to-live (seconds)
        self._retry_count = 3  # Query retry count
        self._retry_delay = 1  # Retry delay (seconds)
        self._max_cache_size = 1000  # Maximum cache entries
        logger.info("Unified memory indexer initialized")
    
    async def _ensure_storage_manager(self):
        """Ensure storage manager is initialized"""
        if not self._storage_manager:
            try:
                self._storage_manager = await get_memory_storage_manager_async()
                logger.info("Storage manager initialized successfully")
            except Exception as e:
                logger.error(f"Storage manager initialization failed: {e}", exc_info=True)
                raise

    async def _execute_with_retry(self, func, *args, **kwargs):
        """
        Execute function with retry on failure
        
        Args:
            func: Async function to execute
            args: Function arguments
            kwargs: Function keyword arguments
            
        Returns:
            Function execution result
        """
        retry_count = kwargs.pop('retry_count', self._retry_count)
        retry_delay = kwargs.pop('retry_delay', self._retry_delay)
        
        for attempt in range(retry_count):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                if attempt < retry_count - 1:
                    logger.warning(f"Execution of {func.__name__} failed (attempt {attempt+1}/{retry_count}): {e}, will retry in {retry_delay}s")
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(f"Execution of {func.__name__} failed (attempt {attempt+1}/{retry_count}): {e}", exc_info=True)
                    raise

    def _get_cache_key(self, *args):
        """Generate cache key"""
        return f"memory_indexer:{':'.join(str(arg) for arg in args)}"

    def _get_cached_result(self, cache_key):
        """Get cached result"""
        if cache_key in self._cache:
            cache_entry = self._cache[cache_key]
            if time.time() < cache_entry['expiry']:
                logger.debug(f"Cache hit: {cache_key}")
                return cache_entry['data']
            else:
                # Cache expired
                del self._cache[cache_key]
        return None

    def _set_cached_result(self, cache_key, data, ttl=None):
        """Set cached result"""
        # Check cache size and clean up oldest entries if too large
        if len(self._cache) >= self._max_cache_size:
            # Sort by expiry time and remove first 20% of entries
            entries = sorted(self._cache.items(), key=lambda x: x[1]['expiry'])
            entries_to_remove = entries[:int(len(entries) * 0.2)]
            for key, _ in entries_to_remove:
                del self._cache[key]
            logger.info(f"Cache limit exceeded, cleaned up {len(entries_to_remove)} entries")
        
        if ttl is None:
            ttl = self._cache_ttl
        self._cache[cache_key] = {
            'data': data,
            'expiry': time.time() + ttl,
            'created_at': time.time()
        }
        logger.debug(f"Cache updated: {cache_key}")
    
    async def get_child_memories(self, 
                              state: MemoryState, 
                              layer: str, 
                              time_window: Optional[Dict[str, Any]] = None) -> List[str]:
        """
        Get child memory ID list
        
        Args:
            state: Workflow state
            layer: Current memory layer (layer whose child memories need to be retrieved)
            time_window: Time window containing start and end
            
        Returns:
            Child memory ID list
        """
        user_id = state.get("user_id", "")
        expert_id = state.get("expert_id", "")
        session_id = state.get("session_id", "")
        
        # Parameter validation
        if not layer:
            logger.warning("Layer not specified when retrieving child memories")
            return []
            
        if not user_id or not expert_id:
            logger.warning(f"user_id or expert_id not provided when retrieving child memories: user_id={user_id}, expert_id={expert_id}")
            return []
            
        # Build cache key
        cache_key = self._get_cache_key("child", user_id, expert_id, layer, 
                               session_id, 
                               str(time_window.get("start") if time_window else None),
                               str(time_window.get("end") if time_window else None))
        
        # Check cache
        cached_result = self._get_cached_result(cache_key)
        if cached_result is not None:
            return cached_result
            
        try:
            await self._ensure_storage_manager()
            
            # Parse time window
            start_time = None
            end_time = None
            if time_window:
                if isinstance(time_window.get("start"), str):
                    start_time = parse_time(time_window.get("start"))
                else:
                    start_time = time_window.get("start")
                    
                if isinstance(time_window.get("end"), str):
                    end_time = parse_time(time_window.get("end"))
                else:
                    end_time = time_window.get("end")
            
            # Determine child memory layer based on current layer
            # Key fix: each layer only retrieves its direct child layer
            memory_ids = []
            if layer == "L1":
                # L1 has no child memories
                memory_ids = []
            elif layer == "L2":
                # L2's child memories are L1 memories in current session
                memory_ids = await self._execute_with_retry(
                    self._get_l1_memories_in_session, 
                    state, session_id
                )
            elif layer == "L3":
                # L3's child memories are all L2 memories in the day
                memory_ids = await self._execute_with_retry(
                    self._get_l2_memories_in_day,
                    state, start_time, end_time
                )
            elif layer == "L4":
                # L4's child memories are all L3 memories in the week
                memory_ids = await self._execute_with_retry(
                    self._get_l3_memories_in_week,
                    state, start_time, end_time
                )
            elif layer == "L5":
                # L5's child memories are all L4 memories in the month
                memory_ids = await self._execute_with_retry(
                    self._get_l4_memories_in_month,
                    state, start_time, end_time
                )
            else:
                logger.warning(f"Unsupported child memory layer: {layer}")
                memory_ids = []
                
            # Cache result
            self._set_cached_result(cache_key, memory_ids)
            
            # Log results
            memory_count = len(memory_ids)
            if memory_count > 0:
                logger.info(f"Retrieved {memory_count} {layer} child memories")
            else:
                logger.warning(f"No {layer} child memories found")
                
            return memory_ids
                
        except Exception as e:
            error_msg = f"Failed to retrieve {layer} child memories: {str(e)}"
            logger.error(error_msg, exc_info=True)
            # Return empty list on error to avoid cascading failures
            return []
    
    async def get_historical_memories(self, 
                                   state: MemoryState, 
                                   layer: str, 
                                   limit: int = None) -> List[str]:
        """
        Get historical memory ID list
        
        Args:
            state: Workflow state
            layer: Memory layer
            limit: Maximum return count, use global config if None
            
        Returns:
            Historical memory ID list
        """
        user_id = state.get("user_id", "")
        expert_id = state.get("expert_id", "")
        session_id = state.get("session_id", "")
        
        # Use global config if limit not specified
        if limit is None:
            from timem.utils.config_manager import get_app_config
            app_config = get_app_config()
            limit = app_config.get("memory", {}).get("historical_memory_limit", 3)
        
        # Parameter validation
        if not layer:
            logger.warning("Layer not specified when retrieving historical memories")
            return []
            
        if not user_id or not expert_id:
            logger.warning(f"user_id or expert_id not provided when retrieving historical memories: user_id={user_id}, expert_id={expert_id}")
            return []
            
        # Build cache key
        cache_key = self._get_cache_key("historical", user_id, expert_id, layer, session_id, limit)
        
        # Check cache
        cached_result = self._get_cached_result(cache_key)
        if cached_result is not None:
            return cached_result
            
        try:
            await self._ensure_storage_manager()
            
            # Get historical memories of same layer
            # Key fix: each layer only retrieves historical memories of same layer
            memory_ids = []
            if layer == "L1":
                # L1 historical memories are limited to within session
                memory_ids = await self._execute_with_retry(
                    self._get_l1_historical_memories,
                    state, session_id, limit
                )
            elif layer == "L2":
                # L2 historical memories are L2 memories from other sessions
                memory_ids = await self._execute_with_retry(
                    self._get_general_historical_memories,
                    state, layer, limit
                )
            elif layer == "L3":
                # L3 historical memories are L3 memories from other dates
                memory_ids = await self._execute_with_retry(
                    self._get_general_historical_memories,
                    state, layer, limit
                )
            elif layer == "L4":
                # L4 historical memories are L4 memories from other weeks
                memory_ids = await self._execute_with_retry(
                    self._get_general_historical_memories,
                    state, layer, limit
                )
            elif layer == "L5":
                # L5 historical memories are L5 memories from other months
                memory_ids = await self._execute_with_retry(
                    self._get_general_historical_memories,
                    state, layer, limit
                )
            else:
                logger.warning(f"Unsupported historical memory layer: {layer}")
                memory_ids = []
                
            # Cache result
            self._set_cached_result(cache_key, memory_ids)
            
            # Log results
            memory_count = len(memory_ids)
            if memory_count > 0:
                logger.info(f"Retrieved {memory_count} {layer} historical memories")
            else:
                logger.warning(f"No {layer} historical memories found")
                
            return memory_ids
                
        except Exception as e:
            error_msg = f"Failed to retrieve {layer} historical memories: {str(e)}"
            logger.error(error_msg, exc_info=True)
            # Return empty list on error to avoid cascading failures
            return []
    
    async def calculate_time_windows(self, 
                                  state: MemoryState) -> Dict[str, Dict[str, datetime]]:
        """
        Calculate time windows for each layer
        
        Args:
            state: Workflow state
            
        Returns:
            Time window dictionary for each layer (timezone-naive)
        """
        # Strictly use external time, avoid datetime.now fallback
        reference_time = None
        
        # 1. Prioritize original_timestamp
        if "original_timestamp" in state and state["original_timestamp"]:
            reference_time = state["original_timestamp"]
            logger.debug(f"Using original_timestamp: {reference_time}")
        
        # 2. Otherwise use timestamp field
        elif "timestamp" in state and state["timestamp"]:
            timestamp = state["timestamp"]
            try:
                if isinstance(timestamp, str):
                    reference_time = parse_time(timestamp)
                elif isinstance(timestamp, datetime):
                    reference_time = timestamp
                logger.debug(f"Using timestamp: {reference_time}")
            except Exception as e:
                logger.error(f"Failed to parse timestamp: {e}")
        
        # 3. Check time fields in metadata
        elif "metadata" in state and isinstance(state["metadata"], dict):
            metadata = state["metadata"]
            for time_field in ["timestamp", "session_time", "created_at", "time"]:
                if time_field in metadata and metadata[time_field]:
                    try:
                        if isinstance(metadata[time_field], str):
                            reference_time = parse_time(metadata[time_field])
                        elif isinstance(metadata[time_field], datetime):
                            reference_time = metadata[time_field]
                        logger.debug(f"Using metadata.{time_field}: {reference_time}")
                        break
                    except Exception as e:
                        logger.error(f"Failed to parse metadata.{time_field}: {e}")
        
        # If no valid time found, raise exception instead of using datetime.now
        if reference_time is None:
            error_msg = "Unable to retrieve valid time from external data, memory indexing failed"
            logger.error(error_msg)
            logger.error(f"Time fields in state: {[k for k in state.keys() if 'time' in k.lower() or 'timestamp' in k.lower()]}")
            raise ValueError(error_msg)
        
        # Ensure time is timezone-naive
        if reference_time.tzinfo is not None:
            reference_time = reference_time.replace(tzinfo=None)
        
        logger.info(f"Using reference time: {reference_time}")
        
        # Calculate time windows for each layer
        time_windows = {}
        for level in ["L1", "L2", "L3", "L4", "L5"]:
            time_windows[level] = self.time_calculator.calculate_time_window(level, reference_time)
            logger.debug(f"{level} time window: {time_windows[level]['start']} - {time_windows[level]['end']}")
        
        return time_windows
    
    async def batch_get_memories_by_ids(self, memory_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Batch retrieve memory objects
        
        Args:
            memory_ids: List of memory IDs
            
        Returns:
            List of memory objects
        """
        if not memory_ids:
            return []
            
        # Try to get from cache
        memories = []
        missing_ids = []
        for memory_id in memory_ids:
            if memory_id in self._cache:
                memories.append(self._cache[memory_id])
            else:
                missing_ids.append(memory_id)
        
        # If all cache hits
        if not missing_ids:
            return memories
        
        # Query memories not in cache
        try:
            async_tasks = [self._storage_manager.retrieve_memory(memory_id) for memory_id in missing_ids]
            fetched_memories = await asyncio.gather(*async_tasks, return_exceptions=True)
            
            # Process results and cache
            for i, memory in enumerate(fetched_memories):
                if memory is not None and not isinstance(memory, Exception):
                    # Ensure memory object has id attribute or key
                    memory_id = missing_ids[i]  # Use request ID as default
                    
                    if hasattr(memory, 'id') and memory.id is not None:
                        memory_id = memory.id
                        self._cache[memory_id] = memory
                        memories.append(memory)
                    elif isinstance(memory, dict) and 'id' in memory and memory['id'] is not None:
                        memory_id = memory['id']
                        self._cache[memory_id] = memory
                        memories.append(memory)
                    else:
                        # If no id or id is None, use request id
                        # Add id field
                        if isinstance(memory, dict):
                            memory['id'] = memory_id
                        elif hasattr(memory, '__dict__'):
                            memory.id = memory_id
                        else:
                            # If memory is neither dict nor has __dict__, create wrapper object
                            memory = {'id': memory_id, 'content': str(memory)}
                        self._cache[memory_id] = memory
                        memories.append(memory)
                elif isinstance(memory, Exception):
                    logger.error(f"Failed to retrieve memory (ID: {missing_ids[i]}): {memory}")
                else:
                    logger.warning(f"Memory does not exist (ID: {missing_ids[i]})")
            
            return memories
                
        except Exception as e:
            logger.error(f"Batch memory retrieval failed: {e}")
            return memories  # Return memories already retrieved from cache
            
    def _memory_to_dict(self, memory) -> Dict[str, Any]:
        """Convert memory object to dictionary"""
        if not memory:
            return {}
            
        if isinstance(memory, dict):
            return memory
            
        memory_dict = {
            "id": getattr(memory, "id", ""),
            "user_id": getattr(memory, "user_id", ""),
            "expert_id": getattr(memory, "expert_id", ""),
            "session_id": getattr(memory, "session_id", ""),
            "level": getattr(memory, "level", ""),
            "title": getattr(memory, "title", ""),  # Fix: Add missing title field
            # Unified: no longer output summary field
            "content": getattr(memory, "content", ""),
            # Remove historical fields like original_text/metadata
            "created_at": getattr(memory, "created_at", None),
            "updated_at": getattr(memory, "updated_at", None),
            "child_memory_ids": getattr(memory, "child_memory_ids", []) or [],
            "historical_memory_ids": getattr(memory, "historical_memory_ids", []) or []
        }
        
        # Fix: Ensure level and layer field compatibility
        if "level" in memory_dict and memory_dict["level"]:
            memory_dict["layer"] = memory_dict["level"]  # Maintain compatibility
        elif "layer" in memory_dict and memory_dict["layer"]:
            memory_dict["level"] = memory_dict["layer"]  # Unified use of level
        
        return memory_dict
    
    async def get_latest_memory_by_user_expert_layer(self, user_id: str, expert_id: str, layer: str) -> Optional[Dict[str, Any]]:
        """
        Get the latest memory for a user-expert combination at the specified layer
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            layer: Memory layer
            
        Returns:
            Optional[Dict[str, Any]]: Latest memory, or None if not found
        """
        if not user_id or not expert_id or not layer:
            logger.warning("Complete parameters not provided when retrieving latest memory")
            return None
            
        try:
            await self._ensure_storage_manager()
            
            # Query latest memory at specified layer
            query = {
                "user_id": user_id,
                "expert_id": expert_id,
                "layer": layer
            }
            
            options = {
                "sort_by": "created_at",
                "sort_order": "desc",
                "limit": 1
            }
            
            memories = await self._storage_manager.search_memories(query, options)
            
            if not memories or len(memories) == 0:
                logger.info(f"No {layer} layer memory found for user({user_id})-expert({expert_id})")
                return None
                
            # Return latest memory
            memory = memories[0]
            logger.info(f"Retrieved latest {layer} memory: {memory.get('id', 'unknown') if isinstance(memory, dict) else getattr(memory, 'id', 'unknown')}")
            
            # Convert to dictionary format
            if isinstance(memory, dict):
                return memory
            else:
                return self._memory_to_dict(memory)
                
        except Exception as e:
            logger.error(f"Failed to retrieve latest memory: {e}", exc_info=True)
            return None

    async def get_session_last_time(self, user_id: str, expert_id: str) -> Optional[datetime]:
        """
        Get the last session time for a user-expert combination
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            
        Returns:
            Optional[datetime]: Last session time, or None if not found
        """
        if not user_id or not expert_id:
            logger.warning("user_id or expert_id not provided when retrieving last session time")
            return None
            
        try:
            await self._ensure_storage_manager()
            
            # Query latest L2 session memory
            query = {
                "user_id": user_id,
                "expert_id": expert_id,
                "layer": "L2"
            }
            
            options = {
                "sort_by": "created_at",
                "sort_order": "desc",
                "limit": 1
            }
            
            memories = await self._storage_manager.search_memories(query, options)
            
            if not memories or len(memories) == 0:
                logger.warning(f"No historical session memory found for user({user_id})-expert({expert_id})")
                return None
                
            # Get latest session time
            memory = memories[0]
            if isinstance(memory, dict):
                created_at = memory.get("created_at")
            else:
                created_at = getattr(memory, "created_at", None)
                
            if not created_at:
                logger.warning("Session memory missing created_at field")
                return None
                
            # Parse time string
            if isinstance(created_at, str):
                try:
                    created_at = parse_time(created_at)
                except Exception as e:
                    logger.error(f"Failed to parse session time: {e}", exc_info=True)
                    return None
            
            logger.info(f"Retrieved latest session time: {created_at.isoformat()}")
            return created_at
            
        except Exception as e:
            logger.error(f"Failed to retrieve last session time: {e}", exc_info=True)
            return None

    async def get_memories_by_time_window(
        self, 
        user_id: str, 
        expert_id: str, 
        layer: str, 
        start_time: Any, 
        end_time: Any, 
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get memory list by time window
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            layer: Memory layer, e.g. "L1", "L2"
            start_time: Start time, can be datetime object or ISO format string
            end_time: End time, can be datetime object or ISO format string
            limit: Maximum return count
            
        Returns:
            List of memory objects
        """
        try:
            await self._ensure_storage_manager()
            
            # Convert time to ISO string
            start_time_str = ensure_iso_string(start_time)
            end_time_str = ensure_iso_string(end_time)
            
            if not start_time_str or not end_time_str:
                logger.error(f"Invalid time window parameters: start={start_time}, end={end_time}")
                return []
            
            # Build query conditions
            query = {
                "user_id": user_id,
                "expert_id": expert_id,
                "layer": layer,
                "time_range": {
                    "start": start_time_str,
                    "end": end_time_str
                }
            }
            options = {"limit": limit, "order_by": "created_at", "order_direction": "desc"}
            
            # Execute query
            logger.info(f"Searching {layer} memory from sql storage, time window: {start_time_str} to {end_time_str}")
            memories = await self._storage_manager.search_memories(query, options, "sql")
            
            logger.info(f"Retrieved {len(memories)} {layer} memories within time window")
            
            return memories
            
        except Exception as e:
            logger.error(f"Failed to retrieve memories within time window: {e}", exc_info=True)
            return []
    
    async def check_memory_exists(self, memory_id: str) -> bool:
        """
        Check if memory exists
        
        Args:
            memory_id: Memory ID
            
        Returns:
            bool: Whether memory exists
        """
        if not memory_id:
            return False
            
        try:
            await self._ensure_storage_manager()
            
            memory = await self._execute_with_retry(
                self._storage_manager.retrieve_memory,
                memory_id
            )
            
            return memory is not None
            
        except Exception as e:
            logger.error(f"Failed to check memory existence: {e}", exc_info=True)
            return False
    
    async def _get_l1_memories_in_session(self, state: MemoryState, session_id: str) -> List[str]:
        """Get list of L1 memory IDs in session"""
        user_id = state.get("user_id", "")
        expert_id = state.get("expert_id", "")
        
        if not session_id:
            logger.warning("session_id not provided when retrieving L1 memories")
            return []
            
        if not user_id or not expert_id:
            logger.warning("user_id or expert_id not provided when retrieving L1 memories")
            return []
            
        try:
            # Use search_memories method, add user_id and expert_id conditions
            query = {
                "user_id": user_id,
                "expert_id": expert_id,
                "session_id": session_id,
                "layer": "L1"
            }
            
            # Add sort options, ensure sorting by creation time
            options = {
                "sort_by": "created_at",
                "sort_order": "asc"
            }
            
            memories = await self._storage_manager.search_memories(query, options)
            memory_ids = [memory.id for memory in memories] if memories else []
            
            logger.info(f"Retrieved {len(memory_ids)} L1 memories in session {session_id}")
            return memory_ids
            
        except Exception as e:
            logger.error(f"Failed to retrieve L1 memories in session: {e}", exc_info=True)
            return []
    
    async def _get_l2_memories_in_day(self, state: MemoryState, start_time: datetime, end_time: datetime) -> List[str]:
        """Get list of L2 memory IDs within date range"""
        user_id = state.get("user_id", "")
        expert_id = state.get("expert_id", "")
        
        if not user_id or not expert_id:
            logger.warning("user_id or expert_id not provided when retrieving L2 memories")
            return []
        
        if not start_time or not end_time:
            logger.warning("Time range not provided when retrieving L2 memories")
            return []
            
        try:
            # Ensure timestamp format is correct
            start_iso = ensure_iso_string(start_time)
            end_iso = ensure_iso_string(end_time)
            
            # Use search_memories method - use standard time field names
            query = {
                "user_id": user_id,
                "expert_id": expert_id,
                "layer": "L2"
            }
            
            # Add sort options, ensure sorting by creation time
            options = {
                "start_time": start_iso,  # Use standard time field names
                "end_time": end_iso,      # Use standard time field names
                "sort_by": "created_at",
                "sort_order": "asc"
            }
            
            memories = await self._storage_manager.search_memories(query, options)
            memory_ids = [memory.id for memory in memories] if memories else []
            
            logger.info(f"Retrieved {len(memory_ids)} L2 memories within date range")
            return memory_ids
            
        except Exception as e:
            logger.error(f"Failed to retrieve L2 memories within date range: {e}", exc_info=True)
            return []
    
    async def _get_l3_memories_in_week(self, state: MemoryState, start_time: datetime, end_time: datetime) -> List[str]:
        """Get list of L3 memory IDs within week range"""
        user_id = state.get("user_id", "")
        expert_id = state.get("expert_id", "")
        
        if not user_id or not expert_id:
            logger.warning("user_id or expert_id not provided when retrieving L3 memories")
            return []
            
        if not start_time or not end_time:
            logger.warning("Time range not provided when retrieving L3 memories")
            return []
            
        try:
            # Ensure timestamp format is correct
            start_iso = ensure_iso_string(start_time)
            end_iso = ensure_iso_string(end_time)
            
            # Use search_memories method - use standard time field names
            query = {
                "user_id": user_id,
                "expert_id": expert_id,
                "layer": "L3"
            }
            
            # Add sort options, ensure sorting by creation time
            options = {
                "start_time": start_iso,  # Use standard time field names
                "end_time": end_iso,      # Use standard time field names
                "sort_by": "created_at",
                "sort_order": "asc"
            }
            
            memories = await self._storage_manager.search_memories(query, options)
            memory_ids = [memory.id for memory in memories] if memories else []
            
            logger.info(f"Retrieved {len(memory_ids)} L3 memories within week range")
            return memory_ids
            
        except Exception as e:
            logger.error(f"Failed to retrieve L3 memories within week range: {e}", exc_info=True)
            return []
    
    async def _get_l4_memories_in_month(self, state: MemoryState, start_time: datetime, end_time: datetime) -> List[str]:
        """Get list of L4 memory IDs within month range"""
        user_id = state.get("user_id", "")
        expert_id = state.get("expert_id", "")
        
        if not user_id or not expert_id:
            logger.warning("user_id or expert_id not provided when retrieving L4 memories")
            return []
            
        if not start_time or not end_time:
            logger.warning("Time range not provided when retrieving L4 memories")
            return []
            
        try:
            # Ensure timestamp format is correct
            start_iso = ensure_iso_string(start_time)
            end_iso = ensure_iso_string(end_time)
            
            # Use search_memories method - use standard time field names
            query = {
                "user_id": user_id,
                "expert_id": expert_id,
                "layer": "L4"
            }
            
            # Add sort options, ensure sorting by creation time
            options = {
                "start_time": start_iso,  # Use standard time field names
                "end_time": end_iso,      # Use standard time field names
                "sort_by": "created_at",
                "sort_order": "asc"
            }
            
            memories = await self._storage_manager.search_memories(query, options)
            memory_ids = [memory.id for memory in memories] if memories else []
            
            logger.info(f"Retrieved {len(memory_ids)} L4 memories within month range")
            return memory_ids
            
        except Exception as e:
            logger.error(f"Failed to retrieve L4 memories within month range: {e}", exc_info=True)
            return []
    
    async def _get_l1_historical_memories(self, state: MemoryState, session_id: str, limit: int) -> List[str]:
        """Get list of historical L1 memory IDs in session"""
        user_id = state.get("user_id", "")
        expert_id = state.get("expert_id", "")
        
        if not session_id:
            logger.warning("session_id not provided when retrieving historical L1 memories")
            return []
            
        if not user_id or not expert_id:
            logger.warning("user_id or expert_id not provided when retrieving historical L1 memories")
            return []
            
        try:
            # Use search_memories method, add user_id and expert_id conditions
            query = {
                "user_id": user_id,
                "expert_id": expert_id,
                "session_id": session_id,
                "layer": "L1"
            }
            
            options = {
                "sort_by": "created_at",
                "sort_order": "desc",
                "limit": limit
            }
            
            memories = await self._storage_manager.search_memories(query, options)
            memory_ids = [memory.id for memory in memories] if memories else []
            
            logger.info(f"Retrieved {len(memory_ids)} historical L1 memories in session {session_id}")
            return memory_ids
            
        except Exception as e:
            logger.error(f"Failed to retrieve historical L1 memories in session: {e}", exc_info=True)
            return []
    
    async def _get_general_historical_memories(self, state: MemoryState, layer: str, limit: int) -> List[str]:
        """Get list of general historical memory IDs"""
        user_id = state.get("user_id", "")
        expert_id = state.get("expert_id", "")
        
        if not user_id or not expert_id or not layer:
            logger.warning(f"Incomplete parameters when retrieving historical memories: user_id={user_id}, expert_id={expert_id}, layer={layer}")
            return []
            
        try:
            # Use search_memories method
            query = {
                "user_id": user_id,
                "expert_id": expert_id,
                "layer": layer
            }
            
            options = {
                "sort_by": "created_at",
                "sort_order": "desc",
                "limit": limit
            }
            
            memories = await self._storage_manager.search_memories(query, options)
            memory_ids = [memory.id for memory in memories] if memories else []
            
            logger.info(f"Retrieved {len(memory_ids)} historical memories at {layer} layer")
            return memory_ids
            
        except Exception as e:
            logger.error(f"Failed to retrieve historical memories: {e}", exc_info=True)
            return []
            
    async def search_memories(self, query: Dict[str, Any], options: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Search memories
        
        Args:
            query: Query conditions
            options: Query options
            
        Returns:
            List of memory objects
        """
        try:
            await self._ensure_storage_manager()
            
            # Try to get from cache
            cache_key = self._get_cache_key("search_memories", str(query), str(options))
            cached_result = self._get_cached_result(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Search from storage
            memories = await self._execute_with_retry(
                self._storage_manager.search_memories, query, options
            )
            
            if memories:
                # Convert to dictionary format
                memory_dicts = [self._memory_to_dict(memory) for memory in memories]
                
                # Cache results
                self._set_cached_result(cache_key, memory_dicts)
                
                return memory_dicts
            
            return []
            
        except Exception as e:
            logger.error(f"Failed to search memories: {str(e)}", exc_info=True)
            return []

    async def get_memories_by_session(self, user_id: str, expert_id: str, session_id: str, layer: str) -> List[Dict[str, Any]]:
        """
        Get memory list by session ID
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            session_id: Session ID
            layer: Memory layer
            
        Returns:
            List of memory objects
        """
        if not user_id or not expert_id or not session_id or not layer:
            logger.warning("Incomplete parameters when retrieving session memories")
            return []
            
        try:
            await self._ensure_storage_manager()
            
            # Build query conditions
            query = {
                "user_id": user_id,
                "expert_id": expert_id,
                "session_id": session_id,
                "layer": layer
            }
            
            # Add sort options
            options = {
                "sort_by": "created_at",
                "sort_order": "asc"
            }
            
            # Execute query
            memories = await self._storage_manager.search_memories(query, options)
            
            # Convert to dictionary format
            memory_dicts = [self._memory_to_dict(memory) for memory in memories]
            
            logger.info(f"Retrieved {len(memory_dicts)} {layer} memories in session {session_id}")
            return memory_dicts
            
        except Exception as e:
            logger.error(f"Failed to retrieve session memories: {e}", exc_info=True)
            return []

    async def get_memory_by_id(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """
        Get memory by ID
        
        Args:
            memory_id: Memory ID
            
        Returns:
            Memory object, or None if not found
        """
        if not memory_id:
            return None
            
        # Build cache key
        cache_key = self._get_cache_key("memory", memory_id)
        
        # Check cache
        cached_result = self._get_cached_result(cache_key)
        if cached_result is not None:
            return cached_result
            
        try:
            await self._ensure_storage_manager()
            
            # Use retrieve_memory method
            memory = await self._execute_with_retry(
                self._storage_manager.retrieve_memory,
                memory_id
            )
            
            if not memory:
                logger.warning(f"Memory not found: {memory_id}")
                return None
                
            # Convert to dictionary
            result = self._memory_to_dict(memory)
            
            # Cache result
            self._set_cached_result(cache_key, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to retrieve memory: {e}", exc_info=True)
            return None

    def clear_cache(self, pattern: str = None):
        """
        Clear cache
        
        Args:
            pattern: Optional matching pattern for selective cache clearing
        """
        if pattern is None:
            # Clear all cache
            self._cache = {}
            logger.info("All cache cleared")
            return
            
        # Clear cache matching specific pattern
        keys_to_remove = [k for k in self._cache if pattern in k]
            
        for key in keys_to_remove:
            del self._cache[key]
            
        logger.info(f"Cleared {len(keys_to_remove)} cache entries matching pattern '{pattern}'")

    def clear_cache_for_user(self, user_id: str, expert_id: str):
        """
        Clear cache for specific user and expert
        
        Args:
            user_id: User ID
            expert_id: Expert ID
        """
        if not user_id or not expert_id:
            return
            
        pattern = f":{user_id}:{expert_id}:"
        self.clear_cache(pattern)
        logger.info(f"Cleared cache for user({user_id}) and expert({expert_id})")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics
        
        Returns:
            Cache statistics
        """
        total_entries = len(self._cache)
        expired_entries = 0
        now = time.time()
        
        for entry in self._cache.values():
            if entry['expiry'] < now:
                expired_entries += 1
                
        return {
            "total_entries": total_entries,
            "active_entries": total_entries - expired_entries,
            "expired_entries": expired_entries,
            "max_size": self._max_cache_size
        }

# Create singleton
_memory_indexer_instance = None

def get_memory_indexer() -> UnifiedMemoryIndexer:
    """Get unified memory indexer instance"""
    global _memory_indexer_instance
    if not _memory_indexer_instance:
        _memory_indexer_instance = UnifiedMemoryIndexer()
    return _memory_indexer_instance