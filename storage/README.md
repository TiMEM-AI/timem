# Storage Layer

The storage layer of the system, providing unified multi-storage engine management and supporting multiple storage backends such as PostgreSQL, Qdrant, Neo4j, Redis, etc.

## 🏗️ Module Structure

```
storage/
├── memory_storage_manager.py    # Memory storage manager (unified entry point)
├── storage_adapter.py           # Storage adapter interface
├── postgres_adapter.py          # PostgreSQL adapter
├── vector_adapter.py            # Vector storage adapter
├── graph_adapter.py             # Graph storage adapter
├── cache_adapter.py             # Cache adapter
├── postgres_store.py            # PostgreSQL storage implementation
├── vector_store.py              # Vector storage implementation
├── graph_store.py               # Graph storage implementation
├── cache_manager.py             # Cache manager
├── connection_pool_manager.py    # Connection pool management
└── database.py                  # Database connection management
```

## 🎯 Core Features

### 1. **Unified Storage Interface** (`storage_adapter.py`)
Provides a unified storage adapter interface supporting multiple storage backends:

```python
class StorageAdapter(ABC):
    """Storage adapter base interface"""
    
    @abstractmethod
    async def create_memory(self, memory: Memory) -> str:
        """Create memory"""
        pass
    
    @abstractmethod
    async def get_memory(self, memory_id: str) -> Optional[Memory]:
        """Get memory"""
        pass
    
    @abstractmethod
    async def update_memory(self, memory_id: str, memory: Memory) -> bool:
        """Update memory"""
        pass
    
    @abstractmethod
    async def delete_memory(self, memory_id: str) -> bool:
        """Delete memory"""
        pass
```

### 2. **Memory Storage Manager** (`memory_storage_manager.py`)
Serves as a single entry point for the storage layer, unified management of all storage adapters:

```python
class MemoryStorageManager:
    """Memory storage manager - unified management of all storage adapters"""
    
    def __init__(
        self,
        postgres_adapter: Optional[PostgreSQLAdapter] = None,
        vector_adapter: Optional[VectorAdapter] = None,
        graph_adapter: Optional[GraphAdapter] = None,
        cache_adapter: Optional[CacheAdapter] = None,
        config_manager: Optional[ConfigManager] = None,
    ):
        """Initialize storage manager through dependency injection"""
        self.postgres_adapter = postgres_adapter
        self.vector_adapter = vector_adapter
        self.graph_adapter = graph_adapter
        self.cache_adapter = cache_adapter
        self.config_manager = config_manager
```

#### Core Methods
```python
# Memory CRUD operations
async def create_memory(self, memory: Memory) -> str:
    """Create memory"""
    # 1. Store to PostgreSQL
    memory_id = await self.postgres_adapter.create_memory(memory)
    
    # 2. Store to vector database
    if self.vector_adapter:
        await self.vector_adapter.create_memory(memory)
    
    # 3. Store to graph database
    if self.graph_adapter:
        await self.graph_adapter.create_memory(memory)
    
    # 4. Update cache
    if self.cache_adapter:
        await self.cache_adapter.set(f"memory:{memory_id}", memory)
    
    return memory_id

async def get_memory(self, memory_id: str) -> Optional[Memory]:
    """Get memory"""
    # 1. Check cache first
    if self.cache_adapter:
        cached_memory = await self.cache_adapter.get(f"memory:{memory_id}")
        if cached_memory:
            return cached_memory
    
    # 2. Query PostgreSQL
    memory = await self.postgres_adapter.get_memory(memory_id)
    if memory and self.cache_adapter:
        await self.cache_adapter.set(f"memory:{memory_id}", memory)
    
    return memory
```

### 3. **PostgreSQL Adapter** (`postgres_adapter.py`)
Handles storage and querying of relational data:

```python
class PostgreSQLAdapter(StorageAdapter):
    """PostgreSQL storage adapter"""
    
    async def create_memory(self, memory: Memory) -> str:
        """Create memory to PostgreSQL"""
        # Insert memory record
        memory_id = await self.postgres_store.create_memory(memory)
        return memory_id
    
    async def search_memories(
        self, 
        query: str, 
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 10
    ) -> List[Memory]:
        """Search memories in PostgreSQL"""
        return await self.postgres_store.search_memories(query, filters, limit)
```

### 4. **Vector Storage Adapter** (`vector_adapter.py`)
Handles storage and similarity search of vector data:

```python
class VectorAdapter(StorageAdapter):
    """Vector storage adapter"""
    
    async def create_memory(self, memory: Memory) -> str:
        """Create memory vector"""
        # Generate vector embedding
        embedding = await self.embedding_service.get_embedding(memory.content)
        
        # Store to vector database
        vector_id = await self.vector_store.create_vector(
            id=memory.id,
            vector=embedding,
            metadata=memory.metadata
        )
        return vector_id
    
    async def search_similar(
        self, 
        query_vector: List[float], 
        limit: int = 10
    ) -> List[VectorSearchResult]:
        """Vector similarity search"""
        return await self.vector_store.search_similar(query_vector, limit)
```

### 5. **Graph Storage Adapter** (`graph_adapter.py`)
Handles storage and relationship queries of graph data:

```python
class GraphAdapter(StorageAdapter):
    """Graph storage adapter"""
    
    async def create_memory(self, memory: Memory) -> str:
        """Create memory nodes and relationships"""
        # Create memory node
        node_id = await self.graph_store.create_node(
            id=memory.id,
            label="Memory",
            properties=memory.dict()
        )
        
        # Create relationships
        if memory.session_id:
            await self.graph_store.create_relationship(
                from_node=memory.session_id,
                to_node=memory.id,
                relationship_type="CONTAINS"
            )
        
        return node_id
    
    async def find_related_memories(
        self, 
        memory_id: str, 
        relationship_types: List[str]
    ) -> List[Memory]:
        """Find related memories"""
        return await self.graph_store.find_related_memories(
            memory_id, relationship_types
        )
```

### 6. **Cache Adapter** (`cache_adapter.py`)
Provides high-performance caching services:

```python
class CacheAdapter(StorageAdapter):
    """Cache adapter"""
    
    async def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """Set cache"""
        return await self.cache_manager.set(key, value, ttl)
    
    async def get(self, key: str) -> Optional[Any]:
        """Get cache"""
        return await self.cache_manager.get(key)
    
    async def delete(self, key: str) -> bool:
        """Delete cache"""
        return await self.cache_manager.delete(key)
```

## 🗄️ Storage Engines

### 1. **PostgreSQL Storage** (`postgres_store.py`)
Relational data storage supporting complex queries and transactions:

```python
class PostgreSQLStore:
    """PostgreSQL storage implementation"""
    
    async def create_memory(self, memory: Memory) -> str:
        """Create memory record"""
        query = """
        INSERT INTO memories (id, content, layer, memory_type, user_id, session_id, metadata, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """
        result = await self.execute(query, memory.dict())
        return result[0]
    
    async def search_memories(
        self, 
        query: str, 
        filters: Dict[str, Any], 
        limit: int
    ) -> List[Memory]:
        """Search memories"""
        # Build SQL query
        sql_query = self._build_search_query(query, filters, limit)
        results = await self.execute(sql_query)
        return [convert_dict_to_memory(row) for row in results]
```

### 2. **Vector Storage** (`vector_store.py`)
Vector similarity search supporting semantic retrieval:

```python
class VectorStore:
    """Vector storage implementation"""
    
    async def create_vector(
        self, 
        id: str, 
        vector: List[float], 
        metadata: Dict[str, Any]
    ) -> str:
        """Create vector point"""
        point = VectorPoint(
            id=id,
            vector=vector,
            payload=metadata
        )
        return await self.qdrant_client.upsert(
            collection_name="memories",
            points=[point]
        )
    
    async def search_similar(
        self, 
        query_vector: List[float], 
        limit: int
    ) -> List[VectorSearchResult]:
        """Vector similarity search"""
        results = await self.qdrant_client.search(
            collection_name="memories",
            query_vector=query_vector,
            limit=limit
        )
        return [VectorSearchResult.from_qdrant_result(r) for r in results]
```

### 3. **Graph Storage** (`graph_store.py`)
Graph relationship queries supporting complex relationship analysis:

```python
class GraphStore:
    """Graph storage implementation"""
    
    async def create_node(
        self, 
        id: str, 
        label: str, 
        properties: Dict[str, Any]
    ) -> str:
        """Create graph node"""
        query = f"""
        CREATE (n:{label} {{id: $id}})
        SET n += $properties
        RETURN n.id
        """
        result = await self.neo4j_session.run(query, id=id, properties=properties)
        return result.single()["n.id"]
    
    async def create_relationship(
        self, 
        from_node: str, 
        to_node: str, 
        relationship_type: str
    ) -> str:
        """Create relationship"""
        query = f"""
        MATCH (a), (b)
        WHERE a.id = $from_node AND b.id = $to_node
        CREATE (a)-[r:{relationship_type}]->(b)
        RETURN r
        """
        result = await self.neo4j_session.run(
            query, from_node=from_node, to_node=to_node
        )
        return result.single()["r"]
```

### 4. **Cache Management** (`cache_manager.py`)
Redis cache management providing high-performance caching services:

```python
class CacheManager:
    """Cache manager"""
    
    async def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """Set cache"""
        serialized_value = json.dumps(value, default=str)
        return await self.redis_client.setex(key, ttl, serialized_value)
    
    async def get(self, key: str) -> Optional[Any]:
        """Get cache"""
        cached_value = await self.redis_client.get(key)
        if cached_value:
            return json.loads(cached_value)
        return None
    
    async def delete(self, key: str) -> bool:
        """Delete cache"""
        result = await self.redis_client.delete(key)
        return result > 0
```

## 🔧 Connection Pool Management

### Connection Pool Manager (`connection_pool_manager.py`)
Unified management of various database connection pools:

```python
class ConnectionPoolManager:
    """Connection pool manager"""
    
    def __init__(self):
        self.postgres_pool = None
        self.redis_pool = None
        self.neo4j_driver = None
        self.qdrant_client = None
    
    async def initialize_pools(self, config: Dict[str, Any]):
        """Initialize all connection pools"""
        # PostgreSQL connection pool
        self.postgres_pool = await self._create_postgres_pool(config["postgres"])
        
        # Redis connection pool
        self.redis_pool = await self._create_redis_pool(config["redis"])
        
        # Neo4j driver
        self.neo4j_driver = await self._create_neo4j_driver(config["neo4j"])
        
        # Qdrant client
        self.qdrant_client = await self._create_qdrant_client(config["qdrant"])
    
    async def close_all_pools(self):
        """Close all connection pools"""
        if self.postgres_pool:
            await self.postgres_pool.close()
        if self.redis_pool:
            await self.redis_pool.close()
        if self.neo4j_driver:
            await self.neo4j_driver.close()
```

## 🚀 Usage Examples

### Initialize Storage Manager
```python
from storage.memory_storage_manager import MemoryStorageManager
from storage.postgres_adapter import PostgreSQLAdapter
from storage.vector_adapter import VectorAdapter
from storage.graph_adapter import GraphAdapter
from storage.cache_adapter import CacheAdapter

# Create adapters
postgres_adapter = PostgreSQLAdapter()
vector_adapter = VectorAdapter()
graph_adapter = GraphAdapter()
cache_adapter = CacheAdapter()

# Create storage manager
storage_manager = MemoryStorageManager(
    postgres_adapter=postgres_adapter,
    vector_adapter=vector_adapter,
    graph_adapter=graph_adapter,
    cache_adapter=cache_adapter
)

# Initialize storage manager
await storage_manager.initialize()
```

### Memory Operations
```python
from timem.models.memory import Memory, MemoryLayer, MemoryType

# Create memory
memory = Memory(
    content="User likes topics related to machine learning",
    layer=MemoryLayer.L1,
    memory_type=MemoryType.PREFERENCE,
    user_id="user_123",
    session_id="session_456",
    metadata={"topic": "machine_learning", "importance": 0.8}
)

# Create memory
memory_id = await storage_manager.create_memory(memory)
print(f"Memory created successfully: {memory_id}")

# Get memory
retrieved_memory = await storage_manager.get_memory(memory_id)
print(f"Retrieved memory: {retrieved_memory.content}")

# Search memories
search_results = await storage_manager.search_memories(
    query="machine learning",
    filters={"layer": "L1"},
    limit=10
)
print(f"Found {len(search_results)} memories")
```

### Vector Search
```python
# Vector similarity search
similar_memories = await storage_manager.search_similar_memories(
    query="AI development trends",
    limit=5
)

for memory in similar_memories:
    print(f"Similar memory: {memory.content} (similarity: {memory.similarity_score})"
```

### Graph Relationship Query
```python
# Find related memories
related_memories = await storage_manager.find_related_memories(
    memory_id="memory_123",
    relationship_types=["RELATED_TO", "SIMILAR_TO"]
)

for memory in related_memories:
    print(f"Related memory: {memory.content}")
```

## 📊 Performance Optimization

### 1. **Connection Pool Optimization**
```python
# PostgreSQL connection pool configuration
postgres_config = {
    "min_size": 5,
    "max_size": 20,
    "max_queries": 50000,
    "max_inactive_connection_lifetime": 300
}

# Redis connection pool configuration
redis_config = {
    "max_connections": 50,
    "retry_on_timeout": True,
    "socket_keepalive": True
}
```

### 2. **Cache Strategy**
```python
# Multi-level caching strategy
class CacheStrategy:
    L1_CACHE_TTL = 300      # 5 minutes
    L2_CACHE_TTL = 3600     # 1 hour
    L3_CACHE_TTL = 86400    # 24 hours
    
    async def get_with_cache(self, key: str):
        # L1: Memory cache
        if key in self.memory_cache:
            return self.memory_cache[key]
        
        # L2: Redis cache
        cached_value = await self.redis_client.get(key)
        if cached_value:
            self.memory_cache[key] = cached_value
            return cached_value
        
        # L3: Database query
        value = await self.database_query(key)
        await self.redis_client.setex(key, self.L2_CACHE_TTL, value)
        self.memory_cache[key] = value
        return value
```

### 3. **Batch Operations**
```python
# Batch create memories
async def batch_create_memories(self, memories: List[Memory]) -> List[str]:
    """Batch create memories to improve performance"""
    # Batch insert to PostgreSQL
    memory_ids = await self.postgres_adapter.batch_create_memories(memories)
    
    # Batch insert to vector database
    if self.vector_adapter:
        await self.vector_adapter.batch_create_memories(memories)
    
    # Batch create graph relationships
    if self.graph_adapter:
        await self.graph_adapter.batch_create_relationships(memories)
    
    return memory_ids
```

## 🛡️ Data Consistency

### Transaction Management
```python
async def create_memory_with_transaction(self, memory: Memory) -> str:
    """Create memory using transaction to ensure data consistency"""
    async with self.postgres_adapter.begin_transaction():
        try:
            # 1. Create PostgreSQL record
            memory_id = await self.postgres_adapter.create_memory(memory)
            
            # 2. Create vector
            if self.vector_adapter:
                await self.vector_adapter.create_memory(memory)
            
            # 3. Create graph node
            if self.graph_adapter:
                await self.graph_adapter.create_memory(memory)
            
            # 4. Update cache
            if self.cache_adapter:
                await self.cache_adapter.set(f"memory:{memory_id}", memory)
            
            return memory_id
            
        except Exception as e:
            # Rollback transaction
            await self.postgres_adapter.rollback_transaction()
            raise e
```

### Data Synchronization
```python
async def sync_storage_engines(self, memory_id: str):
    """Synchronize storage engine data"""
    # Get data from primary storage (PostgreSQL)
    memory = await self.postgres_adapter.get_memory(memory_id)
    if not memory:
        return
    
    # Synchronize to other storage engines
    if self.vector_adapter:
        await self.vector_adapter.update_memory(memory)
    
    if self.graph_adapter:
        await self.graph_adapter.update_memory(memory)
    
    if self.cache_adapter:
        await self.cache_adapter.set(f"memory:{memory_id}", memory)
```

## 📝 Development Guide

### Adding New Storage Engine
1. Inherit from `StorageAdapter` base class
2. Implement all abstract methods
3. Integrate in `MemoryStorageManager`
4. Add corresponding configuration and connection management

### Storage Adapter Example
```python
class NewStorageAdapter(StorageAdapter):
    """New storage adapter"""
    
    async def create_memory(self, memory: Memory) -> str:
        """Create memory"""
        # Implement creation logic
        pass
    
    async def get_memory(self, memory_id: str) -> Optional[Memory]:
        """Get memory"""
        # Implement retrieval logic
        pass
    
    # Implement other abstract methods...
```

## 🧪 Testing

### Unit Tests
```python
import pytest
from storage.memory_storage_manager import MemoryStorageManager
from storage.postgres_adapter import PostgreSQLAdapter

@pytest.mark.asyncio
async def test_create_memory():
    """Test creating memory"""
    storage_manager = MemoryStorageManager()
    await storage_manager.initialize()
    
    memory = Memory(
        content="Test memory",
        layer=MemoryLayer.L1,
        memory_type=MemoryType.FACT
    )
    
    memory_id = await storage_manager.create_memory(memory)
    assert memory_id is not None
    
    retrieved_memory = await storage_manager.get_memory(memory_id)
    assert retrieved_memory.content == "Test memory"
```

### Integration Tests
```python
@pytest.mark.asyncio
async def test_storage_integration():
    """Test storage integration"""
    # Test multi-storage engine consistency
    memory = Memory(...)
    memory_id = await storage_manager.create_memory(memory)
    
    # Verify all storage engines have data
    postgres_memory = await storage_manager.postgres_adapter.get_memory(memory_id)
    vector_memory = await storage_manager.vector_adapter.get_memory(memory_id)
    graph_memory = await storage_manager.graph_adapter.get_memory(memory_id)
    
    assert postgres_memory is not None
    assert vector_memory is not None
    assert graph_memory is not None
```

## 📚 Related Documentation

- [TiMem Core Module](../timem/README.md)
- [API Application Layer](../app/README.md)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Qdrant Documentation](https://qdrant.tech/documentation/)
- [Neo4j Documentation](https://neo4j.com/docs/)
- [Redis Documentation](https://redis.io/documentation)
