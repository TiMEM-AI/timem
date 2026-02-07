"""
TiMem Graph Storage Adapter
Implements graph database storage and query functionality based on Neo4j
"""

import asyncio
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import json
import uuid
from dataclasses import dataclass, asdict
from neo4j import GraphDatabase, Result
from neo4j.exceptions import ServiceUnavailable, ClientError

from timem.utils.logging import get_logger
from timem.utils.config_manager import get_storage_config


@dataclass
class GraphNode:
    """Graph node data structure"""
    id: str
    labels: List[str]
    properties: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


@dataclass
class GraphRelationship:
    """Graph relationship data structure"""
    id: str
    type: str
    start_node: str
    end_node: str
    properties: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


@dataclass
class GraphPath:
    """Graph path data structure"""
    nodes: List[GraphNode]
    relationships: List[GraphRelationship]
    length: int
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


@dataclass
class GraphQueryResult:
    """Graph query result"""
    nodes: List[GraphNode]
    relationships: List[GraphRelationship]
    paths: List[GraphPath]
    raw_data: List[Dict[str, Any]]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


class GraphStore:
    """Graph storage adapter - based on Neo4j"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.logger = get_logger(__name__)
        
        if config is None:
            # Get latest config from ConfigManager each time (supports dataset config)
            try:
                from timem.utils.config_manager import get_config_manager
                config_manager = get_config_manager()
                storage_config = config_manager.get_storage_config()
                graph_config = storage_config.get('graph', {})
                
                import os
                self.config = {
                    'uri': graph_config.get('uri') or os.getenv('NEO4J_URI'),
                    'user': graph_config.get('user') or os.getenv('NEO4J_USER', 'neo4j'),
                    'password': graph_config.get('password') or os.getenv('NEO4J_PASSWORD'),
                    'database': graph_config.get('database', 'neo4j'),
                    'timeout': graph_config.get('timeout', 30),
                    'retry_count': graph_config.get('retry_count', 3)
                }
                self.logger.info(f"Loaded config from ConfigManager: uri={self.config.get('uri')}, database={self.config.get('database')}")
            except Exception as e:
                # If config loading fails, use environment variables (no hardcoded defaults)
                import os
                self.logger.warning(f"Failed to load config from ConfigManager, using environment variables: {e}")
                self.config = {
                    'uri': os.getenv('NEO4J_URI'),
                    'user': os.getenv('NEO4J_USER', 'neo4j'),
                    'password': os.getenv('NEO4J_PASSWORD'),
                    'database': os.getenv('NEO4J_DATABASE', 'neo4j'),
                    'timeout': int(os.getenv('NEO4J_TIMEOUT', '30')),
                    'retry_count': int(os.getenv('NEO4J_RETRY_COUNT', '3'))
                }
        else:
            self.config = config
            
        self.driver = None
        self.database = self.config.get('database', 'neo4j')
        self._initialized = False
        
    async def _ensure_initialized(self):
        """Ensure driver is initialized"""
        if not self._initialized:
            await self._initialize_driver()
    
    async def _initialize_driver(self):
        """Initialize Neo4j driver"""
        try:
            # Get connection info from config, no hardcoded defaults
            import os
            uri = self.config.get('uri') or os.getenv('NEO4J_URI')
            user = self.config.get('user') or os.getenv('NEO4J_USER', 'neo4j')
            password = self.config.get('password') or os.getenv('NEO4J_PASSWORD')
            
            if not uri:
                raise ValueError("Neo4j URI not configured, please set NEO4J_URI in dataset_profiles.yaml or environment variables")
            if not password:
                raise ValueError("Neo4j password not configured, please set NEO4J_PASSWORD in dataset_profiles.yaml or environment variables")
            
            self.logger.info(f"Connecting to Neo4j: {uri}")
            
            self.driver = GraphDatabase.driver(uri, auth=(user, password))
            
            # Test connection
            await self._verify_connectivity()
            
            # Create unique constraint for id attribute (if not exists)
            await self._create_uniqueness_constraints()
            
            self._initialized = True
            self.logger.info(f"Neo4j driver initialized successfully: {uri}")
            
        except Exception as e:
            self.logger.error(f"Neo4j driver initialization failed: {e}")
            raise
    
    async def _verify_connectivity(self):
        """Verify connectivity"""
        try:
            # Use synchronous method to verify connection
            self.driver.verify_connectivity()
        except Exception as e:
            raise Exception(f"Neo4j connection verification failed: {e}")
    
    async def create_node(self, labels: List[str], properties: Dict[str, Any], 
                         node_id: Optional[str] = None) -> str:
        """Create node"""
        await self._ensure_initialized()
        node_id = node_id or str(uuid.uuid4())
        
        try:
            # Build label string
            labels_str = ':'.join(labels)
            
            # Build property string
            properties['id'] = node_id
            
            query = f"""
            MERGE (n:{labels_str} {{id: $node_id}})
            SET n = $properties
            RETURN n.id as id
            """
            
            self.logger.info(f"Executing Cypher for node creation: query='{query}', params={{'node_id': '{node_id}', 'properties': {properties}}}")
            
            with self.driver.session(database=self.database) as session:
                result = session.run(query, node_id=node_id, properties=properties)
                record = result.single()
                
                if record:
                    self.logger.debug(f"Node created successfully: {node_id}")
                    return record['id']
                else:
                    raise Exception("Node creation failed")
                    
        except Exception as e:
            self.logger.error(f"Node creation failed: {e}")
            raise
    
    async def create_relationship(self, start_node_id: str, end_node_id: str, 
                                 rel_type: str, properties: Dict[str, Any] = None,
                                 rel_id: Optional[str] = None) -> str:
        """Create relationship"""
        await self._ensure_initialized()
        rel_id = rel_id or str(uuid.uuid4())
        properties = properties or {}
        properties['id'] = rel_id
        
        try:
            query = """
            MATCH (a {id: $start_node_id}), (b {id: $end_node_id})
            CREATE (a)-[r:%s $properties]->(b)
            RETURN r.id as id
            """ % rel_type
            
            with self.driver.session(database=self.database) as session:
                result = session.run(query, 
                                   start_node_id=start_node_id, 
                                   end_node_id=end_node_id,
                                   properties=properties)
                record = result.single()
                
                if record:
                    self.logger.debug(f"Relationship created successfully: {rel_id}")
                    return record['id']
                else:
                    raise Exception("Relationship creation failed")
                    
        except Exception as e:
            self.logger.error(f"Relationship creation failed: {e}")
            raise
    
    async def _create_uniqueness_constraints(self):
        """Create uniqueness constraint for node id attribute"""
        queries = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (m:Memory) REQUIRE m.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (e:Expert) REQUIRE e.id IS UNIQUE"
        ]
        try:
            with self.driver.session(database=self.database) as session:
                for query in queries:
                    session.run(query)
            self.logger.info("Created uniqueness constraint for id attribute")
        except Exception as e:
            self.logger.warning(f"Failed to create uniqueness constraint (may already exist): {e}")

    async def get_node(self, node_id: str) -> Optional[GraphNode]:
        """Get node"""
        await self._ensure_initialized()
        
        try:
            query = "MATCH (n {id: $node_id}) RETURN n, labels(n) as labels"
            self.logger.info(f"Executing Cypher for getting node: query='{query}', params={{'node_id': '{node_id}'}}")
            
            with self.driver.session(database=self.database) as session:
                result = session.run(query, node_id=node_id)
                record = result.single()
                
                if record:
                    node = record['n']
                    labels = record['labels']
                    
                    return GraphNode(
                        id=node['id'],
                        labels=labels,
                        properties=dict(node)
                    )
                    
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to get node: {e}")
            return None
    
    async def get_nodes_by_label(self, label: str, limit: int = 100) -> List[GraphNode]:
        """Get nodes by label"""
        await self._ensure_initialized()
        
        try:
            query = f"MATCH (n:{label}) RETURN n, labels(n) as labels LIMIT {limit}"
            
            with self.driver.session(database=self.database) as session:
                result = session.run(query)
                nodes = []
                
                for record in result:
                    node = record['n']
                    labels = record['labels']
                    
                    nodes.append(GraphNode(
                        id=node['id'],
                        labels=labels,
                        properties=dict(node)
                    ))
                
                return nodes
                
        except Exception as e:
            self.logger.error(f"Failed to get nodes by label: {e}")
            return []
    
    async def find_nodes(self, properties: Dict[str, Any], 
                        labels: Optional[List[str]] = None,
                        limit: int = 100) -> List[GraphNode]:
        """Find nodes by properties"""
        await self._ensure_initialized()
        
        try:
            # Build query
            label_clause = ""
            if labels:
                label_clause = f":{':'.join(labels)}"
            
            # Build property conditions
            property_conditions = []
            parameters = {}
            
            for key, value in properties.items():
                param_name = f"param_{key}"
                property_conditions.append(f"n.{key} = ${param_name}")
                parameters[param_name] = value
            
            where_clause = " AND ".join(property_conditions)
            
            query = f"MATCH (n{label_clause}) WHERE {where_clause} RETURN n, labels(n) as labels LIMIT {limit}"
            
            with self.driver.session(database=self.database) as session:
                result = session.run(query, **parameters)
                nodes = []
                
                for record in result:
                    node = record['n']
                    labels = record['labels']
                    
                    nodes.append(GraphNode(
                        id=node['id'],
                        labels=labels,
                        properties=dict(node)
                    ))
                
                return nodes
                
        except Exception as e:
            self.logger.error(f"Failed to find nodes: {e}")
            return []
    
    async def find_relationships(self, start_node_id: Optional[str] = None,
                               end_node_id: Optional[str] = None,
                               rel_type: Optional[str] = None,
                               limit: int = 100) -> List[GraphRelationship]:
        """
        Find relationships
        """
        await self._ensure_initialized()
        
        try:
            # Build query conditions
            conditions = []
            params = {}
            
            if start_node_id:
                conditions.append("a.id = $start_node_id")
                params["start_node_id"] = start_node_id
                
            if end_node_id:
                conditions.append("b.id = $end_node_id")
                params["end_node_id"] = end_node_id
                
            if rel_type:
                conditions.append("type(r) = $rel_type")
                params["rel_type"] = rel_type
            
            # Build WHERE clause
            where_clause = ""
            if conditions:
                where_clause = "WHERE " + " AND ".join(conditions)
            
            # Build query
            query = f"""
            MATCH (a)-[r]->(b)
            {where_clause}
            RETURN r, type(r) as type, a.id as start_node, b.id as end_node
            LIMIT {limit}
            """
            
            result = await self.run_cypher_query(query, params)
            
            relationships = []
            for record in result.raw_data:
                rel_data = record.get("r", {})
                rel_id = rel_data.get("id", str(uuid.uuid4()))
                
                relationship = GraphRelationship(
                    id=rel_id,
                    type=record.get("type", ""),
                    start_node=record.get("start_node", ""),
                    end_node=record.get("end_node", ""),
                    properties=rel_data.get("properties", {})
                )
                relationships.append(relationship)
            
            return relationships
            
        except Exception as e:
            self.logger.error(f"Failed to find relationships: {e}")
            return []
    
    async def find_paths(self, start_node_id: str, end_node_id: str,
                        max_depth: int = 3, 
                        relationship_types: Optional[List[str]] = None) -> List[GraphPath]:
        """Find path"""
        await self._ensure_initialized()
        
        try:
            # Build query
            rel_filter = ""
            if relationship_types:
                rel_types = "|".join(relationship_types)
                rel_filter = f":{rel_types}"
            
            query = f"""
            MATCH path = (start {{id: $start_node_id}})-[r{rel_filter}*1..{max_depth}]-(end {{id: $end_node_id}})
            RETURN path
            LIMIT 10
            """
            
            with self.driver.session(database=self.database) as session:
                result = session.run(query, start_node_id=start_node_id, end_node_id=end_node_id)
                paths = []
                
                for record in result:
                    path = record['path']
                    nodes = []
                    relationships = []
                    
                    # Parse path nodes and relationships
                    for i, node in enumerate(path.nodes):
                        nodes.append(GraphNode(
                            id=node['id'],
                            labels=list(node.labels),
                            properties=dict(node)
                        ))
                    
                    for rel in path.relationships:
                        relationships.append(GraphRelationship(
                            id=rel['id'],
                            type=rel.type,
                            start_node=rel.start_node['id'],
                            end_node=rel.end_node['id'],
                            properties=dict(rel)
                        ))
                    
                    paths.append(GraphPath(
                        nodes=nodes,
                        relationships=relationships,
                        length=len(relationships)
                    ))
                
                return paths
                
        except Exception as e:
            self.logger.error(f"Failed to find path: {e}")
            return []
    
    async def run_cypher_query(self, query: str, parameters: Dict[str, Any] = None) -> GraphQueryResult:
        """Execute Cypher query"""
        await self._ensure_initialized()
        parameters = parameters or {}
        
        try:
            with self.driver.session(database=self.database) as session:
                result = session.run(query, **parameters)
                
                nodes = []
                relationships = []
                paths = []
                raw_data = []
                
                for record in result:
                    raw_data.append(dict(record))
                    
                    # Parse record nodes, relationships, and paths
                    for value in record.values():
                        if hasattr(value, 'labels'):  # Node
                            nodes.append(GraphNode(
                                id=value['id'],
                                labels=list(value.labels),
                                properties=dict(value)
                            ))
                        elif hasattr(value, 'type'):  # Relationship
                            relationships.append(GraphRelationship(
                                id=value['id'],
                                type=value.type,
                                start_node=value.start_node['id'],
                                end_node=value.end_node['id'],
                                properties=dict(value)
                            ))
                        elif hasattr(value, 'nodes'):  # Path
                            path_nodes = []
                            path_relationships = []
                            
                            for node in value.nodes:
                                path_nodes.append(GraphNode(
                                    id=node['id'],
                                    labels=list(node.labels),
                                    properties=dict(node)
                                ))
                            
                            for rel in value.relationships:
                                path_relationships.append(GraphRelationship(
                                    id=rel['id'],
                                    type=rel.type,
                                    start_node=rel.start_node['id'],
                                    end_node=rel.end_node['id'],
                                    properties=dict(rel)
                                ))
                            
                            paths.append(GraphPath(
                                nodes=path_nodes,
                                relationships=path_relationships,
                                length=len(path_relationships)
                            ))
                
                return GraphQueryResult(
                    nodes=nodes,
                    relationships=relationships,
                    paths=paths,
                    raw_data=raw_data
                )
                
        except Exception as e:
            self.logger.error(f"Failed to execute Cypher query: {e}")
            raise
    
    async def update_node(self, node_id: str, properties: Dict[str, Any]) -> bool:
        """Update node"""
        await self._ensure_initialized()
        
        try:
            # Build SET clause
            set_clauses = []
            parameters = {'node_id': node_id}
            
            for key, value in properties.items():
                param_name = f"prop_{key}"
                set_clauses.append(f"n.{key} = ${param_name}")
                parameters[param_name] = value
            
            set_clause = ", ".join(set_clauses)
            query = f"MATCH (n {{id: $node_id}}) SET {set_clause} RETURN n"
            
            with self.driver.session(database=self.database) as session:
                result = session.run(query, **parameters)
                record = result.single()
                
                if record:
                    self.logger.debug(f"Node updated successfully: {node_id}")
                    return True
                else:
                    return False
                    
        except Exception as e:
            self.logger.error(f"Failed to update node: {e}")
            return False
    
    async def update_relationship(self, rel_id: str, properties: Dict[str, Any]) -> bool:
        """Update relationship"""
        await self._ensure_initialized()
        
        try:
            # Build SET clause
            set_clauses = []
            parameters = {'rel_id': rel_id}
            
            for key, value in properties.items():
                param_name = f"prop_{key}"
                set_clauses.append(f"r.{key} = ${param_name}")
                parameters[param_name] = value
            
            set_clause = ", ".join(set_clauses)
            query = f"MATCH ()-[r {{id: $rel_id}}]->() SET {set_clause} RETURN r"
            
            with self.driver.session(database=self.database) as session:
                result = session.run(query, **parameters)
                record = result.single()
                
                if record:
                    self.logger.debug(f"Relationship updated successfully: {rel_id}")
                    return True
                else:
                    return False
                    
        except Exception as e:
            self.logger.error(f"Failed to update relationship: {e}")
            return False
    
    async def delete_node(self, node_id: str) -> bool:
        """Delete node"""
        await self._ensure_initialized()
        
        try:
            query = "MATCH (n {id: $node_id}) DETACH DELETE n"
            
            with self.driver.session(database=self.database) as session:
                result = session.run(query, node_id=node_id)
                summary = result.consume()
                
                if summary.counters.nodes_deleted > 0:
                    self.logger.debug(f"Node deleted successfully: {node_id}")
                    return True
                else:
                    return False
                    
        except Exception as e:
            self.logger.error(f"Failed to delete node: {e}")
            return False
    
    async def delete_relationship(self, rel_id: str) -> bool:
        """Delete relationship"""
        await self._ensure_initialized()
        
        try:
            query = "MATCH ()-[r {id: $rel_id}]->() DELETE r"
            
            with self.driver.session(database=self.database) as session:
                result = session.run(query, rel_id=rel_id)
                summary = result.consume()
                
                if summary.counters.relationships_deleted > 0:
                    self.logger.info(f"Relationship deleted successfully: {rel_id}")
                    return True
                else:
                    self.logger.warning(f"Relationship not found: {rel_id}")
                    return False
                    
        except Exception as e:
            self.logger.error(f"Failed to delete relationship: {e}")
            return False
    
    async def delete_memory_graph(self, memory_id: str) -> bool:
        """Delete memory graph"""
        await self._ensure_initialized()
        
        try:
            # Delete memory node and its relationships
            query = """
            MATCH (m:Memory {id: $memory_id})
            OPTIONAL MATCH (m)-[r]-()
            DELETE r, m
            """
            
            with self.driver.session(database=self.database) as session:
                result = session.run(query, memory_id=memory_id)
                summary = result.consume()
                
                if summary.counters.nodes_deleted > 0:
                    self.logger.info(f"Memory graph deleted successfully: {memory_id}")
                    return True
                else:
                    self.logger.warning(f"Memory node not found: {memory_id}")
                    return False
                    
        except Exception as e:
            self.logger.error(f"Failed to delete memory graph: {e}")
            return False
    
    async def get_node_neighbors(self, node_id: str, 
                               direction: str = "both", 
                               relationship_types: Optional[List[str]] = None,
                               limit: int = 100) -> List[GraphNode]:
        """Get node neighbors"""
        await self._ensure_initialized()
        
        try:
            # Build relationship pattern
            if direction == "outgoing":
                rel_pattern = "-[r]->"
            elif direction == "incoming":
                rel_pattern = "<-[r]-"
            else:  # both
                rel_pattern = "-[r]-"
            
            # Add relationship type filter
            if relationship_types:
                rel_types = "|".join(relationship_types)
                rel_pattern = f"-[r:{rel_types}]-"
            
            query = f"MATCH (n {{id: $node_id}}){rel_pattern}(neighbor) RETURN neighbor, labels(neighbor) as labels LIMIT {limit}"
            
            with self.driver.session(database=self.database) as session:
                result = session.run(query, node_id=node_id)
                neighbors = []
                
                for record in result:
                    node = record['neighbor']
                    labels = record['labels']
                    
                    neighbors.append(GraphNode(
                        id=node['id'],
                        labels=labels,
                        properties=dict(node)
                    ))
                
                return neighbors
                
        except Exception as e:
            self.logger.error(f"Failed to get node neighbors: {e}")
            return []
    
    async def create_memory_graph(self, memory_data: Dict[str, Any]) -> str:
        """Create memory graph"""
        await self._ensure_initialized()
        
        try:
            memory_id = memory_data.get('id', str(uuid.uuid4()))
            
            # Handle created_at field
            created_at = memory_data.get('created_at')
            if isinstance(created_at, str):
                # If already a string, use it directly
                created_at_str = created_at
            elif hasattr(created_at, 'isoformat'):
                # If datetime object, convert to ISO format
                created_at_str = created_at.isoformat()
            else:
                # Default to current time
                created_at_str = datetime.utcnow().isoformat()
            
            # Create memory node
            memory_properties = {
                'id': memory_id,
                'layer': memory_data.get('layer', 'L1'),
                'content': memory_data.get('content', ''),
                'user_id': memory_data.get('user_id'),
                'expert_id': memory_data.get('expert_id'),
                'created_at': created_at_str,
                'importance_score': memory_data.get('importance_score', 0.0)
            }
            
            # Create memory node
            await self.create_node(['Memory'], memory_properties, memory_id)
            
            # If user ID is present, create user node and relationship
            if memory_data.get('user_id'):
                user_id = memory_data['user_id']
                user_properties = {
                    'id': user_id,
                    'username': memory_data.get('username', 'unknown'),
                    'type': 'user'
                }
                
                # Create or update user node
                await self.create_node(['User'], user_properties, user_id)
                
                # Create BELONGS_TO relationship
                await self.create_relationship(
                    memory_id, user_id, 'BELONGS_TO',
                    {'created_at': created_at_str}
                )
            
            # If expert ID is present, create expert node and relationship
            if memory_data.get('expert_id'):
                expert_id = memory_data['expert_id']
                expert_properties = {
                    'id': expert_id,
                    'name': memory_data.get('expert_name', 'unknown'),
                    'domain': memory_data.get('domain', 'general'),
                    'type': 'expert'
                }
                
                # Create or update expert node
                await self.create_node(['Expert'], expert_properties, expert_id)
                
                # Create HANDLED_BY relationship
                await self.create_relationship(
                    memory_id, expert_id, 'HANDLED_BY',
                    {'created_at': created_at_str}
                )
            
            self.logger.info(f"Memory graph created successfully: {memory_id}")
            return memory_id
            
        except Exception as e:
            self.logger.error(f"Failed to create memory graph: {e}")
            raise
    
    async def traverse_memory_graph(self, start_node_id: str, 
                                  max_depth: int = 3,
                                  relationship_types: Optional[List[str]] = None) -> List[GraphPath]:
        """Traverse memory graph"""
        await self._ensure_initialized()
        
        try:
            # Build relationship filter
            rel_filter = ""
            if relationship_types:
                rel_types = "|".join(relationship_types)
                rel_filter = f":{rel_types}"
            
            query = f"""
            MATCH path = (start {{id: $start_node_id}})-[r{rel_filter}*1..{max_depth}]-(connected)
            RETURN path
            ORDER BY length(path)
            LIMIT 50
            """
            
            with self.driver.session(database=self.database) as session:
                result = session.run(query, start_node_id=start_node_id)
                paths = []
                
                for record in result:
                    path = record['path']
                    nodes = []
                    relationships = []
                    
                    # Parse path nodes and relationships
                    for node in path.nodes:
                        nodes.append(GraphNode(
                            id=node['id'],
                            labels=list(node.labels),
                            properties=dict(node)
                        ))
                    
                    for rel in path.relationships:
                        relationships.append(GraphRelationship(
                            id=rel['id'],
                            type=rel.type,
                            start_node=rel.start_node['id'],
                            end_node=rel.end_node['id'],
                            properties=dict(rel)
                        ))
                    
                    paths.append(GraphPath(
                        nodes=nodes,
                        relationships=relationships,
                        length=len(relationships)
                    ))
                
                return paths
                
        except Exception as e:
            self.logger.error(f"Failed to traverse memory graph: {e}")
            return []
    
    async def connect(self):
        """Connect to graph database"""
        try:
            await self._ensure_initialized()
            self.logger.info("Graph storage connected successfully")
        except Exception as e:
            self.logger.error(f"Failed to connect to graph storage: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from graph database"""
        try:
            await self.close()
            self.logger.info("Graph storage disconnected successfully")
        except Exception as e:
            self.logger.error(f"Failed to disconnect from graph storage: {e}")
    
    async def close(self):
        """Close Neo4j driver"""
        try:
            if self.driver:
                self.driver.close()
                self.driver = None
                self._initialized = False
                self.logger.info("Neo4j driver closed successfully")
        except Exception as e:
            self.logger.error(f"Failed to close Neo4j driver: {e}")
        finally:
            self._initialized = False

    async def clear_all_data(self) -> Dict[str, int]:
        """Clear all data"""
        await self._ensure_initialized()
        try:
            with self.driver.session(database=self.database) as session:
                result = session.run("MATCH (n) DETACH DELETE n")
                summary = result.consume()
                deleted_info = {
                    "nodes_deleted": summary.counters.nodes_deleted,
                    "relationships_deleted": summary.counters.relationships_deleted
                }
                self.logger.info(f"Graph data cleared successfully: {deleted_info}")
                return deleted_info
        except Exception as e:
            self.logger.error(f"Failed to clear graph data: {e}", exc_info=True)
            raise

    async def get_stats(self) -> Dict[str, int]:
        """Get graph database statistics"""
        await self._ensure_initialized()
        try:
            with self.driver.session(database=self.database) as session:
                # Get node count
                node_result = session.run("MATCH (n) RETURN count(n) AS node_count")
                node_count = node_result.single()["node_count"]
                # Get relationship count
                rel_result = session.run("MATCH ()-[r]->() RETURN count(r) AS rel_count")
                rel_count = rel_result.single()["rel_count"]
                stats = {"node_count": node_count, "relationship_count": rel_count}
                return stats
        except Exception as e:
            self.logger.error(f"Failed to get graph statistics: {e}", exc_info=True)
            raise

# Factory method
def get_graph_store() -> GraphStore:
    return GraphStore() 
