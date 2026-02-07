"""
TiMem Graph Storage Adapter
Implements StorageAdapter interface, provides graph database storage functionality based on Neo4j
"""

import asyncio
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timezone
import uuid
from dataclasses import dataclass, asdict
import json

from timem.utils.logging import get_logger
from timem.utils.config_manager import get_storage_config
from timem.utils.time_parser import time_parser
from timem.models.memory import Memory
from storage.storage_adapter import StorageAdapter
from storage.graph_store import GraphStore, GraphNode, GraphRelationship


class GraphAdapter(StorageAdapter):
    """Graph storage adapter - implemented based on Neo4j, follows StorageAdapter interface"""
    
    def __init__(self, config_manager: Optional[Any] = None):
        """
        Initialize graph storage adapter
        
        Args:
            config_manager: Config manager instance, use global instance if not provided
        """
        from timem.utils.config_manager import get_config_manager
        self.config_manager = config_manager or get_config_manager()
        
        # Refresh config to ensure dataset config takes effect
        self.config_manager.reload_config()
        
        self.config = self.config_manager.get_config("storage.graph")

        self.logger = get_logger(__name__)
        self._is_available = False
        
        # Create GraphStore instance, pass config
        self.graph_store = GraphStore(self.config)
        self.logger.info(f"✅ GraphAdapter initialization complete, config: {self.config.get('uri')}")
    
    async def connect(self) -> bool:
        """
        Connect to storage
        
        Returns:
            bool: Whether connection was successful
        """
        try:
            await self.graph_store.connect()
            self._is_available = True
            self.logger.info("Graph storage connected successfully")
            return True
        except Exception as e:
            self.logger.error(f"Graph storage connection failed: {e}")
            self._is_available = False
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from storage"""
        try:
            await self.graph_store.disconnect()
            self._is_available = False
            self.logger.info("Graph storage disconnected")
        except Exception as e:
            self.logger.error(f"Error disconnecting graph storage: {e}")
    
    async def is_available(self) -> bool:
        """
        Check if storage is available
        
        Returns:
            bool: Whether storage is available
        """
        if not self._is_available:
            return await self.connect()
        return self._is_available
    
    async def _memory_to_node_properties(self, memory: Any) -> Dict[str, Any]:
        """
        Generate node properties from memory object
        
        Args:
            memory: Memory object
            
        Returns:
            Dict[str, Any]: Node properties
        """
        properties = {}
        
        # Helper to get attribute from object or dict
        def get_mem_attr(mem: Any, attr: str) -> Any:
            if isinstance(mem, dict):
                return mem.get(attr)
            return getattr(mem, attr, None)

        # Extract core fields to properties
        for field in ["id", "user_id", "expert_id", "session_id", "level", "content", "created_at", "updated_at"]:
            value = get_mem_attr(memory, field)
            if value is not None:
                # Handle datetime type fields
                if field in ["created_at", "updated_at"] and hasattr(value, "isoformat"):
                    value = value.isoformat()
                properties[field] = value
        
        # Handle metadata
        meta_data = get_mem_attr(memory, "meta_data") or {}

        # Add index fields
        for field in ["child_memory_ids", "historical_memory_ids", "parent_memory_id", 
                     "trace_path", "time_window_start", "time_window_end"]:
            value = get_mem_attr(memory, field)
            if value is not None:
                # Handle datetime type fields
                if field in ["time_window_start", "time_window_end"] and hasattr(value, "isoformat"):
                    value = value.isoformat()
                meta_data[field] = value
        
        # Serialize metadata to JSON string
        if meta_data:
            # Use a custom serializer to handle non-serializable types if necessary
            properties["meta_data"] = json.dumps(meta_data, default=str)
        
        # Ensure timestamp is added if created_at is not present
        if 'created_at' not in properties:
            timestamp = get_mem_attr(memory, "timestamp")
            if timestamp:
                if hasattr(timestamp, "isoformat"):
                    properties["created_at"] = timestamp.isoformat()
                else:
                    properties["created_at"] = str(timestamp)
        
        return properties
    
    async def _create_memory_graph(self, memory: Any) -> str:
        """
        Create graph structure for memory object
        
        Args:
            memory: Memory object
            
        Returns:
            str: Node ID
        """
        # Get memory_id correctly from dict or object
        if isinstance(memory, dict):
            memory_id = memory.get("id") or str(uuid.uuid4())
        else:
            memory_id = getattr(memory, "id", None) or str(uuid.uuid4())

        # Get memory_level correctly from dict or object
        memory_level = "L1" # Default level
        level_attr = None
        if isinstance(memory, dict):
            level_attr = memory.get("level") or memory.get("layer")
        else:
            level_attr = getattr(memory, "level", getattr(memory, "layer", None))
        
        if level_attr:
            # Handle enum by getting its value
            memory_level = level_attr.value if hasattr(level_attr, 'value') else str(level_attr)
            
        # Generate node properties
        properties = await self._memory_to_node_properties(memory)
        
        # Create memory node
        node_id = await self.graph_store.create_node(
            labels=["Memory", memory_level],
            properties=properties,
            node_id=memory_id
        )
        
        # Handle user relationship
        user_id = None
        if hasattr(memory, "user_id") and memory.user_id:
            user_id = memory.user_id
        elif isinstance(memory, dict) and memory.get("user_id"):
            user_id = memory.get("user_id")
        else:
            user_id = None

        if user_id:
            # Create or get user node
            try:
                user_node = await self.graph_store.get_node(user_id)
                if not user_node:
                    await self.graph_store.create_node(
                        labels=["User"],
                        properties={"id": user_id, "name": user_id},
                        node_id=user_id
                    )
                
                # Create memory to user relationship
                await self.graph_store.create_relationship(
                    start_node_id=memory_id,
                    end_node_id=user_id,
                    rel_type="BELONGS_TO",
                    properties={"created_at": properties.get("created_at", datetime.now().isoformat())}
                )
            except Exception as e:
                self.logger.warning(f"Failed to create user relationship: {e}")
        
        # Handle expert relationship
        expert_id = None
        if hasattr(memory, "expert_id") and memory.expert_id:
            expert_id = memory.expert_id
        elif isinstance(memory, dict) and memory.get("expert_id"):
            expert_id = memory.get("expert_id")
        else:
            expert_id = None

        if expert_id:
            # Create or get expert node
            try:
                expert_node = await self.graph_store.get_node(expert_id)
                if not expert_node:
                    await self.graph_store.create_node(
                        labels=["Expert"],
                        properties={"id": expert_id, "name": expert_id},
                        node_id=expert_id
                    )
                
                # Create memory to expert relationship
                await self.graph_store.create_relationship(
                    start_node_id=memory_id,
                    end_node_id=expert_id,
                    rel_type="HANDLED_BY",
                    properties={"created_at": properties.get("created_at", datetime.now().isoformat())}
                )
            except Exception as e:
                self.logger.warning(f"Failed to create expert relationship: {e}")
        
        # Handle parent-child relationship
        parent_id = None
        if isinstance(memory, dict):
            parent_id = memory.get("parent_id") or memory.get("parent_memory_id")
        else:
            parent_id = getattr(memory, "parent_id", getattr(memory, "parent_memory_id", None))
        
        if parent_id:
            try:
                # Ensure parent node exists
                parent_node = await self.graph_store.get_node(parent_id)
                if not parent_node:
                    self.logger.warning(f"Parent node {parent_id} does not exist, cannot create CHILD_OF relationship.")
                else:
                    # Create child memory to parent memory relationship
                    await self.graph_store.create_relationship(
                        start_node_id=memory_id,
                        end_node_id=parent_id,
                        rel_type="CHILD_OF",
                        properties={"created_at": properties.get("created_at", datetime.now().isoformat())}
                    )
            except Exception as e:
                self.logger.error(f"Failed to create parent-child relationship: {e}", exc_info=True)
        
        # Handle historical relationship
        historical_ids = None
        if hasattr(memory, "historical_memory_ids") and memory.historical_memory_ids:
            historical_ids = memory.historical_memory_ids
        elif isinstance(memory, dict) and memory.get("historical_memory_ids"):
            historical_ids = memory.get("historical_memory_ids")

        if historical_ids:
            for historical_id in historical_ids:
                try:
                    # Create current memory to historical memory relationship
                    await self.graph_store.create_relationship(
                        start_node_id=memory_id,
                        end_node_id=historical_id,
                        rel_type="FOLLOWS",
                        properties={"created_at": properties.get("created_at", datetime.now().isoformat())}
                    )
                except Exception as e:
                    self.logger.warning(f"Failed to create historical relationship: {e}")
        
        return node_id
    
    async def _node_to_memory(self, node: GraphNode) -> Memory:
        """
        Convert graph node to memory object
        
        Args:
            node: Graph node
            
        Returns:
            Memory: Memory object
        """
        properties = node.properties
        
        # Parse metadata
        meta_data = {}
        if "meta_data" in properties:
            try:
                meta_data = json.loads(properties["meta_data"])
            except:
                meta_data = {}
        
        # Extract index fields
        child_memory_ids = meta_data.get("child_memory_ids", [])
        historical_memory_ids = meta_data.get("historical_memory_ids", [])
        parent_memory_id = meta_data.get("parent_memory_id")
        trace_path = meta_data.get("trace_path", [])
        time_window_start = meta_data.get("time_window_start")
        time_window_end = meta_data.get("time_window_end")
        
        # Parse time
        created_at = None
        if "created_at" in properties:
            try:
                created_at = time_parser.parse_session_time(properties["created_at"])
            except:
                pass
        
        updated_at = None
        if "updated_at" in properties:
            try:
                updated_at = time_parser.parse_session_time(properties["updated_at"])
            except:
                pass
        
        # Build memory object
        memory = Memory(
            id=properties.get("id"),
            user_id=properties.get("user_id"),
            expert_id=properties.get("expert_id"),
            session_id=properties.get("session_id"),
            level=properties.get("level", "L1"),
            content=properties.get("content"),
            meta_data=meta_data,
            child_memory_ids=child_memory_ids,
            historical_memory_ids=historical_memory_ids,
            parent_memory_id=parent_memory_id,
            trace_path=trace_path,
            time_window_start=time_window_start,
            time_window_end=time_window_end,
            created_at=created_at,
            updated_at=updated_at,
            memory_timestamp=properties.get("created_at")
        )
        
        return memory
    
    async def store_memory(self, memory: Any) -> str:
        """
        Store memory object
        
        Args:
            memory: Memory object or dictionary
            
        Returns:
            str: Storage ID
        """
        if not await self.is_available():
            self.logger.warning("Graph storage unavailable, skipping store operation")
            raise Exception("Graph storage unavailable")
        
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
            
            # Create memory graph structure
            node_id = await self._create_memory_graph(memory)
            
            self.logger.info(f"Successfully stored memory graph structure: {node_id}")
            return node_id
            
        except Exception as e:
            self.logger.error(f"Failed to store memory graph structure: {e}")
            raise
    
    async def retrieve_memory(self, memory_id: str) -> Optional[Any]:
        """
        Retrieve memory object
        
        Args:
            memory_id: Memory ID
            
        Returns:
            Memory object, returns None if not found
        """
        if not await self.is_available():
            return None
        
        try:
            # Get memory node
            node = await self.graph_store.get_node(memory_id)
            if not node:
                return None
            
            # Convert to memory object
            memory = await self._node_to_memory(node)
            
            # Get associated relationships
            try:
                # Get child memory relationships
                child_relationships = await self.graph_store.find_relationships(
                    end_node_id=memory_id,
                    rel_type="CHILD_OF"
                )
                child_ids = [rel.start_node for rel in child_relationships]
                if child_ids and (not memory.child_memory_ids or len(child_ids) > len(memory.child_memory_ids)):
                    memory.child_memory_ids = child_ids
                
                # Get historical memory relationships
                historical_relationships = await self.graph_store.find_relationships(
                    end_node_id=memory_id,
                    rel_type="FOLLOWS"
                )
                historical_ids = [rel.start_node for rel in historical_relationships]
                if historical_ids and (not memory.historical_memory_ids or len(historical_ids) > len(memory.historical_memory_ids)):
                    memory.historical_memory_ids = historical_ids
                
                # Get parent memory relationship
                parent_relationships = await self.graph_store.find_relationships(
                    start_node_id=memory_id,
                    rel_type="CHILD_OF"
                )
                if parent_relationships and not memory.parent_memory_id:
                    memory.parent_memory_id = parent_relationships[0].end_node
            except Exception as e:
                self.logger.warning(f"Failed to get associated relationships: {e}")
            
            return memory
            
        except Exception as e:
            self.logger.error(f"Failed to retrieve memory graph structure: {e}")
            return None
    
    async def search_memories(self, 
                           query: Dict[str, Any], 
                           options: Dict[str, Any] = None) -> List[Any]:
        """
        Search memories
        
        Args:
            query: Query conditions, supports user_id, expert_id, layer, session_id and other fields
            options: Search options, supports limit, etc.
            
        Returns:
            List of memories matching the conditions
        """
        if not await self.is_available():
            return []
        
        # Default options
        if options is None:
            options = {}
        
        limit = options.get("limit", 100)
        
        try:
            # Build Cypher query
            match_clause = "MATCH (m:Memory)"
            where_clauses = []
            parameters = {}
            
            # Handle level filter
            if "layer" in query:
                where_clauses.append("m.level = $layer")
                parameters["layer"] = query["layer"]
            elif "level" in query:
                where_clauses.append("m.level = $level")
                parameters["level"] = query["level"]
            
            # Handle user filter
            if "user_id" in query:
                where_clauses.append("m.user_id = $user_id")
                parameters["user_id"] = query["user_id"]
            
            # Handle expert filter
            if "expert_id" in query:
                where_clauses.append("m.expert_id = $expert_id")
                parameters["expert_id"] = query["expert_id"]
            
            # Handle session filter
            if "session_id" in query:
                where_clauses.append("m.session_id = $session_id")
                parameters["session_id"] = query["session_id"]
            
            # Handle time range
            if "start_time" in query:
                where_clauses.append("m.created_at >= $start_time")
                start_time = query["start_time"]
                if hasattr(start_time, "isoformat"):
                    parameters["start_time"] = start_time.isoformat()
                else:
                    parameters["start_time"] = str(start_time)
            
            if "end_time" in query:
                where_clauses.append("m.created_at <= $end_time")
                end_time = query["end_time"]
                if hasattr(end_time, "isoformat"):
                    parameters["end_time"] = end_time.isoformat()
                else:
                    parameters["end_time"] = str(end_time)
            
            # Build WHERE clause
            where_clause = ""
            if where_clauses:
                where_clause = "WHERE " + " AND ".join(where_clauses)
            
            # Build complete query
            cypher_query = f"{match_clause} {where_clause} RETURN m LIMIT {limit}"
            
            # Execute query
            result = await self.graph_store.run_cypher_query(cypher_query, parameters)
            
            # Convert to memory objects
            memories = []
            for node in result.nodes:
                try:
                    memory = await self._node_to_memory(node)
                    memories.append(memory)
                except Exception as e:
                    self.logger.warning(f"Failed to convert node to memory object: {e}")
            
            self.logger.info(f"Graph search successful, found {len(memories)} records")
            return memories
            
        except Exception as e:
            self.logger.error(f"Graph search failed: {e}")
            return []
    
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
                self.logger.warning(f"Failed to update memory: Memory ID {memory_id} does not exist")
                return False
            
            # Update memory object fields
            for field, value in updates.items():
                setattr(current_memory, field, value)
            
            # Set update time
            current_memory.updated_at = datetime.now(timezone.utc)
            
            # Convert to node properties
            properties = await self._memory_to_node_properties(current_memory)
            
            # Update node
            result = await self.graph_store.update_node(memory_id, properties)
            
            # Update relationships
            try:
                # Handle parent-child relationship update
                if "parent_memory_id" in updates and updates["parent_memory_id"]:
                    new_parent_id = updates["parent_memory_id"]
                    
                    # Find existing parent relationship and delete
                    existing_parent_rels = await self.graph_store.find_relationships(
                        start_node_id=memory_id,
                        rel_type="CHILD_OF"
                    )
                    for rel in existing_parent_rels:
                        await self.graph_store.delete_relationship(rel.id)
                    
                    # Create new parent relationship
                    await self.graph_store.create_relationship(
                        start_node_id=memory_id,
                        end_node_id=new_parent_id,
                        rel_type="CHILD_OF",
                        properties={"created_at": properties.get("created_at", datetime.now().isoformat())}
                    )
                
                # Handle historical memory relationship update
                if "historical_memory_ids" in updates and updates["historical_memory_ids"]:
                    new_historical_ids = updates["historical_memory_ids"]
                    
                    # Find existing historical relationship and delete
                    existing_hist_rels = await self.graph_store.find_relationships(
                        start_node_id=memory_id,
                        rel_type="FOLLOWS"
                    )
                    for rel in existing_hist_rels:
                        await self.graph_store.delete_relationship(rel.id)
                    
                    # Create new historical relationships
                    for hist_id in new_historical_ids:
                        await self.graph_store.create_relationship(
                            start_node_id=memory_id,
                            end_node_id=hist_id,
                            rel_type="FOLLOWS",
                            properties={"created_at": properties.get("created_at", datetime.now().isoformat())}
                        )
            except Exception as e:
                self.logger.warning(f"Failed to update memory relationships: {e}")
            
            if result:
                self.logger.info(f"Successfully updated memory graph structure: {memory_id}")
            else:
                self.logger.warning(f"Graph store returned update failure: {memory_id}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to update memory graph structure: {e}")
            return False
    
    async def delete_memory(self, memory_id: str) -> bool:
        """
        Delete memory object
        
        Args:
            memory_id: Memory ID
            
        Returns:
            bool: Whether deletion was successful
        """
        if not await self.is_available():
            return False
        
        try:
            # Delete memory graph structure
            result = await self.graph_store.delete_memory_graph(memory_id)
            
            if result:
                self.logger.info(f"Successfully deleted memory graph structure: {memory_id}")
            else:
                self.logger.warning(f"Graph store returned deletion failure: {memory_id}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to delete memory graph structure: {e}")
            return False
    
    async def get_memory_graph(self, memory_id: str, depth: int = 2) -> Dict[str, Any]:
        """
        Get memory graph structure - extension method
        
        Args:
            memory_id: Memory ID
            depth: Traversal depth
            
        Returns:
            Dict[str, Any]: Graph structure data
        """
        if not await self.is_available():
            return {"nodes": [], "relationships": []}
        
        try:
            # Traverse memory graph
            paths = await self.graph_store.traverse_memory_graph(memory_id, max_depth=depth)
            
            # Collect all nodes and relationships
            nodes_map = {}
            rels_map = {}
            
            for path in paths:
                for node in path.nodes:
                    nodes_map[node.id] = {
                        "id": node.id,
                        "labels": node.labels,
                        "properties": node.properties
                    }
                
                for rel in path.relationships:
                    rels_map[rel.id] = {
                        "id": rel.id,
                        "type": rel.type,
                        "source": rel.start_node,
                        "target": rel.end_node,
                        "properties": rel.properties
                    }
            
            # Build return result
            graph_data = {
                "nodes": list(nodes_map.values()),
                "relationships": list(rels_map.values()),
                "center_id": memory_id
            }
            
            return graph_data
            
        except Exception as e:
            self.logger.error(f"Failed to get memory graph structure: {e}")
            return {"nodes": [], "relationships": [], "center_id": memory_id}

    async def find_relationships(self, start_node_id: Optional[str] = None,
                               start_node_level: Optional[str] = None, # Not used by store, but kept for signature consistency
                               end_node_id: Optional[str] = None,
                               rel_type: Optional[str] = None,
                               limit: int = 100) -> List[GraphRelationship]:
        """
        Finds relationships in the graph store.
        This is a wrapper around the graph_store's find_relationships method.
        """
        if not await self.is_available():
            self.logger.warning("Graph store is not available.")
            return []
        try:
            return await self.graph_store.find_relationships(
                start_node_id=start_node_id,
                end_node_id=end_node_id,
                rel_type=rel_type,
                limit=limit
            )
        except Exception as e:
            self.logger.error(f"Failed to find relationships in graph adapter: {e}", exc_info=True)
            return []

    async def clear_all_data(self) -> Dict[str, Any]:
        """Clear all graph data"""
        if not await self.is_available():
            return {"success": False, "error": "Graph store unavailable"}

        try:
            summary = await self.graph_store.clear_all_data()
            deleted_info = {
                "nodes_deleted": summary.nodes_deleted,
                "relationships_deleted": summary.relationships_deleted
            }
            return {"success": True, "message": f"Graph data cleared: {deleted_info}"}
        except Exception as e:
            self.logger.error(f"Failed to clear graph data: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def get_stats(self) -> Dict[str, Any]:
        """Get graph store statistics"""
        if not await self.is_available():
            return {"success": False, "error": "Graph store unavailable"}

        try:
            stats = await self.graph_store.get_stats()
            return {"success": True, "stats": stats}
        except Exception as e:
            self.logger.error(f"Failed to get graph store statistics: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def get_memory_by_id(self, memory_id: str, level: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Retrieves a memory by its ID and returns it as a dictionary.
        This method relies on the more comprehensive retrieve_memory to fetch the full object.
        """
        try:
            memory_obj = await self.retrieve_memory(memory_id)
            if memory_obj:
                if hasattr(memory_obj, 'model_dump'):
                    return memory_obj.model_dump()
                elif hasattr(memory_obj, 'to_dict'):
                    return memory_obj.to_dict()
                elif isinstance(memory_obj, dict):
                    return memory_obj
                else:
                    return memory_obj.__dict__
            return None
        except Exception as e:
            self.logger.error(f"Failed to get memory from graph database: {e}", exc_info=True)
            return None

    async def get_memories_by_session(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        if not await self.is_available():
            self.logger.warning("Graph store unavailable, skipping get operation")
            return []
        
        try:
            # Build Cypher query
            match_clause = "MATCH (m:Memory)"
            where_clauses = []
            parameters = {}
            
            # Handle session filter
            if session_id:
                where_clauses.append("m.session_id = $session_id")
                parameters["session_id"] = session_id
            
            # Build WHERE clause
            where_clause = ""
            if where_clauses:
                where_clause = "WHERE " + " AND ".join(where_clauses)
            
            # Build complete query
            cypher_query = f"{match_clause} {where_clause} RETURN m LIMIT {limit}"
            
            # Execute query
            result = await self.graph_store.run_cypher_query(cypher_query, parameters)
            
            # Convert to memory objects
            memories = []
            for node in result.nodes:
                try:
                    memory = await self._node_to_memory(node)
                    memories.append(memory)
                except Exception as e:
                    self.logger.warning(f"Failed to convert node to memory object: {e}")
            
            self.logger.info(f"Graph search successful, found {len(memories)} records")
            return memories
            
        except Exception as e:
            self.logger.error(f"Graph search failed: {e}")
            return []

# Factory method
def get_graph_adapter(config_manager: Optional[Any] = None) -> GraphAdapter:
    """Get graph storage adapter instance"""
    return GraphAdapter(config_manager=config_manager)