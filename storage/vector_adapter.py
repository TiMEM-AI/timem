"""
TiMem Vector Storage Adapter
Implements StorageAdapter interface, provides vector storage functionality based on Qdrant
"""

import asyncio
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timezone
import uuid
from dataclasses import dataclass, asdict
import json
import time

from qdrant_client import QdrantClient, models
from qdrant_client.http import models
from qdrant_client.http.exceptions import ResponseHandlingException
from qdrant_client.http.models import UpdateStatus

from timem.utils.logging import get_logger
from timem.utils.config_manager import get_storage_config
from timem.utils.qdrant_utils import ensure_collection_with_correct_dim
from timem.utils.time_parser import time_parser
from timem.utils.json_utils import dumps, loads
from timem.models.memory import Memory, convert_dict_to_memory
from storage.storage_adapter import StorageAdapter
from storage.vector_store import VectorStore, VectorSearchResult


class VectorAdapter(StorageAdapter):
    """Vector storage adapter - implemented based on Qdrant, follows StorageAdapter interface"""
    
    def __init__(self, config_manager: Optional[Any] = None):
        """
        Initialize vector storage adapter
        
        Args:
            config_manager: Configuration manager instance, uses global instance if not provided
        """
        from timem.utils.config_manager import get_config_manager
        self.config_manager = config_manager or get_config_manager()
        
        # Refresh config to ensure dataset configuration takes effect
        self.config_manager.reload_config()
        
        self.config = self.config_manager.get_config("storage.vector")

        self.logger = get_logger(__name__)
        self._is_available = False
        
        # Create VectorStore instance, pass configuration
        self.vector_store = VectorStore(self.config)
        self.logger.info(f"VectorAdapter initialization completed, config: {self.config.get('url')}")
    
    async def connect(self) -> bool:
        """
        Connect to storage
        
        Returns:
            bool: Whether connection was successful
        """
        try:
            await self.vector_store.connect()
            await self.vector_store.create_collection()
            self._is_available = True
            self.logger.info("Vector storage connection successful")
            return True
        except Exception as e:
            self.logger.error(f"Vector storage connection failed: {e}")
            self._is_available = False
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from storage"""
        try:
            await self.vector_store.disconnect()
            self._is_available = False
            self.logger.info("Vector storage connection disconnected")
        except Exception as e:
            self.logger.error(f"Error occurred when disconnecting vector storage: {e}")
    
    async def is_available(self) -> bool:
        """
        Check if storage is available
        
        Returns:
            bool: Whether storage is available
        """
        if not self._is_available:
            # Try to connect
            success = await self.connect()
            if success:
                self.logger.info("Vector storage connection successful, now available")
            else:
                self.logger.warning("Vector storage connection failed, will use default storage")
            return success
        
        # If previously connected, perform health check
        try:
            # Simple health check: try to get collection info
            await self.vector_store._ensure_initialized()
            return True
        except Exception as e:
            self.logger.warning(f"Vector storage health check failed, attempting to reconnect: {e}")
            self._is_available = False
            return await self.connect()
    
    async def _memory_to_embedding(self, memory: Any) -> List[float]:
        """
        Extract or generate embedding vector from memory object
        
        Args:
            memory: Memory object
            
        Returns:
            List[float]: Embedding vector
        """
        # Check if memory object already has vector
        if hasattr(memory, "embedding") and memory.embedding:
            return memory.embedding
            
        # Check if there is original content for generating vector
        content = None
        if hasattr(memory, "content") and memory.content:
            content = memory.content
        elif isinstance(memory, dict):
            if "content" in memory and memory["content"]:
                content = memory["content"]
        
        if not content:
            # Changed to warning and use memory ID as content to avoid errors due to empty content
            memory_id = getattr(memory, "id", None)
            if not memory_id and isinstance(memory, dict):
                memory_id = memory.get("id")
            
            if memory_id:
                self.logger.warning(f"Memory {memory_id} has no content available for vectorization, will use ID as content")
                content = f"memory_id:{memory_id}"
            else:
                self.logger.warning("Memory object has no ID and no content available for vectorization, using default placeholder")
                content = "empty_memory_placeholder"
        
        # Call embedding service to generate vector
        try:
            from llm.embedding_service import get_embedding_service
            embedding_service = get_embedding_service()
            embedding = await embedding_service.embed_text(content)
            self.logger.debug(f"Successfully generated embedding vector, dimension: {len(embedding)}")
            return embedding
        except Exception as e:
            # If embedding service fails, use zero vector as fallback
            self.logger.error(f"Embedding service call failed: {e}")
            vector_size = self.config.get('vector_size', 384)
            self.logger.warning(f"Using zero vector instead of actual embedding, dimension {vector_size} (fallback)")
            return [0.0] * vector_size
    
    async def _memory_to_payload(self, memory: Any) -> Dict[str, Any]:
        """
        Generate payload data for vector storage from memory object, ensuring key fields are not lost.
        """
        mem_instance: Memory
        original_session_id = None  # Save original session_id

        if isinstance(memory, Memory):
            mem_instance = memory
        elif isinstance(memory, dict):
            # Key fix: first save session_id from original dict
            original_session_id = memory.get('session_id')
            self.logger.debug(f"Extract original session_id from dict: {original_session_id}")
            
            try:
                # Use Pydantic's model_validate to create model instance from dict
                # This ensures all fields (including those with defaults) are correctly populated
                mem_instance = Memory.model_validate(memory)
            except Exception as e:
                self.logger.error(f"Cannot convert dict to Memory object: {e}", exc_info=True)
                # As fallback, return dict copy directly, but this may be incomplete
                return memory.copy()
        else:
            self.logger.warning(f"Cannot create payload for type {type(memory)}, returning empty dict")
            return {}
        
        # Use to_payload method to get complete, serializable dict
        try:
            payload = mem_instance.to_payload()
            
            # Key fix: if original dict has session_id but payload doesn't or is None, restore it
            if original_session_id is not None:
                if 'session_id' not in payload or payload.get('session_id') is None:
                    self.logger.info(f"Restore original session_id to payload: {original_session_id}")
                    payload['session_id'] = original_session_id
            
            # Add integer timestamp field for time range filtering
            if 'created_at' in payload and payload['created_at']:
                try:
                    # created_at may be datetime object or iso string
                    created_at_val = payload['created_at']
                    if isinstance(created_at_val, str):
                        dt = datetime.fromisoformat(created_at_val.replace('Z', '+00:00'))
                    else:
                        dt = created_at_val
                    payload['created_at_ts'] = int(dt.timestamp())
                except (ValueError, TypeError) as e:
                    self.logger.warning(f"Cannot create timestamp for created_at: {e}")
            
            # Log final session_id for debugging
            self.logger.debug(f"Final payload session_id: {payload.get('session_id', 'missing')}")
            
            return payload
        except Exception as e:
            self.logger.error(f"Memory.to_payload() execution failed: {e}", exc_info=True)
            # Fallback again in case to_payload fails
            return mem_instance.model_dump(mode="json")

    
    async def store_memory(self, memory: Any, wait_for_vector_indexing: bool = False) -> str:
        """
        Store memory object
        
        Args:
            memory: Memory object or dict
            wait_for_vector_indexing: Whether to wait for vector indexing update to complete
            
        Returns:
            str: Storage ID
        """
        if not await self.is_available():
            self.logger.warning("Vector storage not available, skipping storage operation")
            raise Exception("Vector storage not available")
        
        try:
            # Ensure memory object has ID
            if isinstance(memory, dict):
                memory_id = memory.get("id") or str(uuid.uuid4())
                if not memory.get("id"):
                    memory["id"] = memory_id
            else:
                memory_id = getattr(memory, "id", None) or str(uuid.uuid4())
                if not hasattr(memory, "id") or not memory.id:
                    memory.id = memory_id
            
            # Get or generate vector
            vector = await self._memory_to_embedding(memory)
            
            # Generate payload
            payload = await self._memory_to_payload(memory)
            self.logger.info(f"Storing memory {memory_id} with payload: {payload}")
            
            # Store vector
            result_id = await self.vector_store.store_vector(
                vector=vector,
                payload=payload,
                point_id=memory_id,
                wait=wait_for_vector_indexing
            )
            
            self.logger.info(f"Successfully stored memory vector: {result_id}")
            return result_id
            
        except Exception as e:
            self.logger.error(f"Failed to store memory vector: {e}")
            raise
    
    async def retrieve_memory(self, memory_id: str) -> Optional[Any]:
        """
        Retrieve memory object
        
        Args:
            memory_id: Memory ID
            
        Returns:
            Memory object, returns None if not exists
        """
        if not await self.is_available():
            return None
        
        try:
            # Use VectorStore to get vector
            vector_result = await self.vector_store.get_vector(memory_id)
            if not vector_result:
                return None
            
            # Build Memory object from payload
            return Memory(**vector_result.payload)
            
        except Exception as e:
            self.logger.error(f"Failed to retrieve memory vector: {e}")
            return None
    
    async def search_memories(self, 
                            query: Dict[str, Any], 
                            options: Dict[str, Any] = None) -> List[Any]:
        """
        Search memories
        
        Args:
            query: Query conditions, supports vector, query_text, user_id, expert_id, layer, start_time, end_time and other fields
            options: Search options, supports limit, score_threshold, etc.
            
        Returns:
            List of memories matching conditions
        """
        if not await self.is_available():
            return []
        
        # Default options
        if options is None:
            options = {}
        
        limit = options.get("limit", 10)
        score_threshold = options.get("score_threshold", 0.0)  # Adjust to lowest threshold to ensure all queries match
        
        try:
            # Build filter conditions
            filter_conditions = {}
            
            # Key fix: prioritize extracting filter conditions from options["filter"]
            if options and "filter" in options and isinstance(options["filter"], dict):
                filter_conditions.update(options["filter"])
                self.logger.info(f"Extract filter conditions from options.filter: {options['filter']}")
            
            # Key fix: prioritize user_group_ids (forced isolation, highest priority)
            if "user_group_ids" in query and query["user_group_ids"]:
                filter_conditions["user_group_ids"] = query["user_group_ids"]
                self.logger.info(f"Vector retrieval enabled user group isolation: {query['user_group_ids']}")
            # Handle character_ids (only effective when no user_group_ids)
            elif "character_ids" in query and query["character_ids"]:
                # Use OR condition matching: user_id or expert_id in character_ids list
                filter_conditions["character_ids"] = query["character_ids"]
            else:
                # User and expert filtering (backward compatible)
                if "user_id" in query:
                    filter_conditions["user_id"] = query["user_id"]
                if "expert_id" in query:
                    filter_conditions["expert_id"] = query["expert_id"]
            
            # Memory layer filtering (if in query, override options)
            if "layer" in query:
                filter_conditions["level"] = query["layer"]
            elif "level" in query:
                filter_conditions["level"] = query["level"]
            
            # Session ID filtering
            if "session_id" in query:
                filter_conditions["session_id"] = query["session_id"]
            
            # Time range filtering
            if "start_time" in query or "end_time" in query:
                time_range = {}
                if "start_time" in query:
                    time_range["gte"] = query["start_time"]
                if "end_time" in query:
                    time_range["lte"] = query["end_time"]
                # Use created_at field for time filtering
                filter_conditions["created_at"] = time_range

            # Add debug info
            self.logger.info(f"Search query: {query}")
            self.logger.info(f"Filter conditions: {filter_conditions}")
            self.logger.info(f"Search options: {options}")
            
            # Use vector for query
            vector_results = []
            query_vector = None
            
            # If vector is directly provided
            if "vector" in query and isinstance(query["vector"], list):
                query_vector = query["vector"]
            
            # If text query is provided
            elif "query_text" in query and query["query_text"]:
                # Call embedding service to generate vector
                try:
                    from llm.embedding_service import get_embedding_service
                    embedding_service = get_embedding_service()
                    query_vector = await embedding_service.embed_text(query["query_text"])
                    self.logger.debug(f"Successfully generated query vector, dimension: {len(query_vector)}")
                except Exception as e:
                    # If embedding service fails, use zero vector as fallback
                    self.logger.error(f"Query embedding service call failed: {e}")
                    vector_size = self.config.get('vector_size', 384)
                    self.logger.warning(f"Using zero vector instead of actual query embedding, dimension {vector_size} (fallback)")
                    query_vector = [0.0] * vector_size
            
            if query_vector:
                # Execute vector search
                vector_results = await self.vector_store.search_vectors(
                    query_vector=query_vector,
                    limit=limit,
                    score_threshold=score_threshold,
                    filter_conditions=filter_conditions
                )
            else:
                # If no vector or text query provided, execute regular filter search
                # Note: Qdrant is primarily a vector database, filter search without vector may have poor performance
                self.logger.warning("No vector or text query provided, vector database search efficiency may be low")
                
                # Query first 100 records as alternatives
                # This is just an example, actual implementation may need to use sql_adapter for filter queries
                vector_results = await self.vector_store.search_vectors(
                    query_vector=[0.0] * self.config.get('vector_size', 384),
                    limit=100,
                    filter_conditions=filter_conditions
                )
            
            # Convert results to memory objects
            memories = []
            for result in vector_results:
                payload = result.payload or {}
                self.logger.info(f"Retrieved vector point with payload: {payload}")
                payload["vector_id"] = result.id
                
                # Directly set similarity score to payload so Memory object can receive it
                payload["vector_score"] = result.score
                payload["retrieval_score"] = result.score  # Set generic retrieval score
                
                # Key fix: ensure session_id field exists (extract from metadata)
                if "session_id" not in payload or not payload.get("session_id"):
                    # Try to extract session_id from metadata
                    if "metadata" in payload and isinstance(payload["metadata"], dict):
                        session_id_from_meta = payload["metadata"].get("session_id")
                        if session_id_from_meta:
                            payload["session_id"] = session_id_from_meta
                            self.logger.debug(f"Extract session_id from metadata: {session_id_from_meta}")
                
                # Also keep in metadata for backward compatibility
                if "metadata" not in payload:
                    payload["metadata"] = {}
                if "metadata" in payload and isinstance(payload["metadata"], dict):
                    payload["metadata"]["vector_score"] = result.score
                
                try:
                    # Don't use Memory object's to_dict(), directly return payload dict
                    # This avoids session_id loss caused by exclude_none=True
                    memory_dict = payload.copy()
                    memories.append(memory_dict)
                    self.logger.debug(f"Successfully created memory dict with session_id: {memory_dict.get('session_id', 'unknown')}")
                except Exception as e:
                    self.logger.warning(f"Failed to process memory object: {e}. Payload: {payload}")
                    memories.append(payload) # Fallback to returning the raw payload dict
            
            self.logger.info(f"Vector search successful, found {len(memories)} records")
            return memories
            
        except Exception as e:
            self.logger.error(f"Vector search failed: {e}")
            return []
    
    async def search(self, user_id: str, expert_id: str, query_text: str, 
                   limit: int, level: Optional[str] = None, score_threshold: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Search similar memories in vector storage (compatible with old interface, calls search_memories)
        """
        query = {
            "query_text": query_text,
            "user_id": user_id,
            "expert_id": expert_id,
        }
        if level:
            query["level"] = level
            
        options = {
            "limit": limit,
            "score_threshold": score_threshold
        }
        
        return await self.search_memories(query, options)

    async def update_memory(self, memory_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update memory object
        
        Args:
            memory_id: Memory ID
            updates: Fields to update
            
        Returns:
            bool: Whether update was successful
        """
        if not await self.is_available():
            return False
        
        try:
            # First get current memory
            current_memory = await self.retrieve_memory(memory_id)
            if not current_memory:
                self.logger.warning(f"Update memory failed: Memory ID {memory_id} does not exist")
                return False
            
            # Update memory object fields (only update existing fields)
            for field, value in updates.items():
                if hasattr(current_memory, field):
                    setattr(current_memory, field, value)
                else:
                    self.logger.debug(f"Skip non-existent field: {field}")
            
            # Set update time
            current_memory.updated_at = datetime.now(timezone.utc)
            
            # Regenerate vector and payload
            vector = await self._memory_to_embedding(current_memory)
            payload = await self._memory_to_payload(current_memory)
            
            # Update vector storage
            result = await self.vector_store.update_vector(
                point_id=memory_id,
                vector=vector,
                payload=payload
            )
            
            if result:
                self.logger.info(f"Successfully updated memory vector: {memory_id}")
            else:
                self.logger.warning(f"Vector storage returned update failure: {memory_id}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to update memory vector: {e}")
            return False
    
    async def delete_memory(self, memory_id: str, level: Optional[str] = None, wait_for_vector_indexing: bool = False) -> bool:
        """
        Delete memory
        
        Args:
            memory_id: Memory ID
            level: Memory layer (optional, but will be ignored as unified collection is used)
            wait_for_vector_indexing: Whether to wait for vector indexing to complete
            
        Returns:
            bool: Whether deletion was successful
        """
        try:
            # Note: we ignore level parameter as we use unified collection timem_memories, not layer-based collections
            success = await self.vector_store.delete_memory(memory_id, collection_name=None, wait=wait_for_vector_indexing)
            if success:
                self.logger.info(f"Successfully deleted memory: {memory_id}")
            return success
        except Exception as e:
            self.logger.error(f"Failed to delete memory: {e}")
            return False

    async def delete_memories_by_user_expert(self, user_id: str, expert_id: str) -> bool:
        """
        Delete all memories of specified user and expert
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            
        Returns:
            bool: Whether deletion was successful
        """
        try:
            # Search all matching memories
            query = {
                "user_id": user_id,
                "expert_id": expert_id
            }
            
            memories = await self.search_memories(query, {"limit": 1000})
            if not memories:
                self.logger.info(f"No memories found for user {user_id} and expert {expert_id}")
                return True
            
            # Delete memories one by one
            deleted_count = 0
            for memory in memories:
                try:
                    memory_id = memory.get("id") if isinstance(memory, dict) else getattr(memory, "id", None)
                    if memory_id:
                        success = await self.delete_memory(memory_id)
                        if success:
                            deleted_count += 1
                except Exception as e:
                    self.logger.warning(f"Failed to delete memory {memory_id}: {e}")
            
            self.logger.info(f"Successfully deleted {deleted_count}/{len(memories)} memories, user: {user_id}, expert: {expert_id}")
            return deleted_count == len(memories)
        except Exception as e:
            self.logger.error(f"Failed to delete memories for user {user_id} and expert {expert_id}: {e}")
            return False

    async def batch_store_memories(self, memories: List[Any], wait_for_vector_indexing: bool = False) -> List[str]:
        """
        Batch store memory objects - extension method
        
        Args:
            memories: List of memory objects
            wait_for_vector_indexing: Whether to wait for vector indexing update to complete
            
        Returns:
            List[str]: List of storage IDs
        """
        if not await self.is_available():
            raise Exception("Vector storage not available")
        
        try:
            vector_points = []
            memory_ids = []
            
            for memory in memories:
                # Ensure memory object has ID
                memory_id = getattr(memory, "id", None) or str(uuid.uuid4())
                if not hasattr(memory, "id") or not memory.id:
                    memory.id = memory_id
                
                # Get or generate vector
                vector = await self._memory_to_embedding(memory)
                
                # Generate payload
                payload = await self._memory_to_payload(memory)
                
                # Add to batch list
                vector_points.append({
                    "id": memory_id,
                    "vector": vector,
                    "payload": payload
                })
                memory_ids.append(memory_id)
            
            # Use VectorStore's batch storage method
            if vector_points:
                from storage.vector_store import VectorPoint
                vector_point_objects = [
                    VectorPoint(id=p["id"], vector=p["vector"], payload=p["payload"])
                    for p in vector_points
                ]
                await self.vector_store.store_vectors(vector_point_objects, wait=wait_for_vector_indexing)
                self.logger.info(f"Successfully batch stored memory vectors: {len(memory_ids)} records")
            
            return memory_ids
            
        except Exception as e:
            self.logger.error(f"Failed to batch store memory vectors: {e}")
            raise

    async def clear_all_data(self) -> Dict[str, Any]:
        """Clear all vector data (implemented by recreating collection)"""
        if not await self.is_available():
            return {"success": False, "error": "Vector storage not available"}
        
        try:
            await self.vector_store.recreate_collection()
            return {"success": True, "message": "Collection successfully recreated"}
        except Exception as e:
            self.logger.error(f"Failed to clear vector data: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def get_stats(self) -> Dict[str, Any]:
        """Get vector storage statistics"""
        if not await self.is_available():
            return {"success": False, "error": "Vector storage not available"}

        try:
            info = await self.vector_store.get_collection_info()
            if info:
                stats = {
                    "vector_count": info.get("points_count", 0),
                    "segment_count": info.get("segments_count", 0),
                    "config": info.get("config", {})
                }
                return {"success": True, "stats": stats}
            else:
                return {"success": False, "error": "Cannot get collection info"}
        except Exception as e:
            self.logger.error(f"Failed to get vector storage statistics: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

# Factory method
def get_vector_adapter(config_manager: Optional[Any] = None) -> VectorAdapter:
    """Get vector storage adapter instance"""
    return VectorAdapter(config_manager=config_manager)