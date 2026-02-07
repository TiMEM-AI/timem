# Business Service Layer

The business service layer of the system, providing core business logic implementation including memory generation, session management, user services, scheduling services and other key business functions.

## 🏗️ Module Structure

```
services/
├── memory_generation_service.py    # Memory generation service
├── session_context_manager.py     # Session context management
├── session_memory_scanner.py      # Session memory scanner
├── user_service.py                # User service
├── user_registration_service.py   # User registration service
├── character_service.py           # Character service
├── scheduler_service.py           # Scheduler service
└── scheduled_backfill_service.py  # Scheduled backfill service
```

## 🎯 Core Services

### 1. **Memory Generation Service** (`memory_generation_service.py`)
LangGraph-based memory generation service supporting five-level memory architecture:

```python
class MemoryGenerationService:
    """Memory generation service - engineering architecture best practices"""
    
    def __init__(self):
        self.status = ServiceStatus.INITIALIZING
        self.metrics = ServiceMetrics()
        self.workflow = None
        self.storage_manager = None
        self._lock = threading.Lock()
    
    async def initialize(self):
        """Initialize service"""
        with self._lock:
            if self.status != ServiceStatus.INITIALIZING:
                return
            
            try:
                # Initialize workflow
                self.workflow = MemoryGenerationWorkflow()
                await self.workflow.initialize()
                
                # Initialize storage manager
                self.storage_manager = MemoryStorageManager()
                await self.storage_manager.initialize()
                
                self.status = ServiceStatus.READY
                logger.info("Memory generation service initialized")
                
            except Exception as e:
                self.status = ServiceStatus.ERROR
                logger.error(f"Memory generation service initialization failed: {e}")
                raise
```

#### Core Functions
```python
async def generate_memory(
    self, 
    session_id: str, 
    user_id: str, 
    dialogue_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Generate memory"""
    try:
        # Create execution state
        execution_state = ExecutionState(
            session_id=session_id,
            user_id=user_id,
            dialogue_data=dialogue_data
        )
        
        # Execute workflow
        result = await self.workflow.execute(execution_state)
        
        # Update metrics
        self.metrics.total_requests += 1
        self.metrics.successful_requests += 1
        
        return result
        
    except Exception as e:
        self.metrics.failed_requests += 1
        logger.error(f"Memory generation failed: {e}")
        raise
```

### 2. **Session Context Management** (`session_context_manager.py`)
Manages session context information and state:

```python
class SessionContextManager:
    """Session context manager"""
    
    def __init__(self):
        self.active_sessions = {}
        self.session_metadata = {}
        self._lock = threading.Lock()
    
    async def create_session(
        self, 
        session_id: str, 
        user_id: str, 
        expert_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create session"""
        with self._lock:
            session_data = {
                "session_id": session_id,
                "user_id": user_id,
                "expert_id": expert_id,
                "created_at": datetime.now(),
                "last_activity": datetime.now(),
                "message_count": 0,
                "status": "active"
            }
            
            self.active_sessions[session_id] = session_data
            self.session_metadata[session_id] = {
                "context": [],
                "memories": [],
                "preferences": {}
            }
            
            return session_data
    
    async def update_context(
        self, 
        session_id: str, 
        message: Dict[str, Any]
    ):
        """Update session context"""
        if session_id in self.session_metadata:
            self.session_metadata[session_id]["context"].append(message)
            
            # Maintain context length
            max_context = 50
            if len(self.session_metadata[session_id]["context"]) > max_context:
                self.session_metadata[session_id]["context"] = \
                    self.session_metadata[session_id]["context"][-max_context:]
    
    async def get_session_context(self, session_id: str) -> Dict[str, Any]:
        """Get session context"""
        return self.session_metadata.get(session_id, {})
```

### 3. **Session Memory Scanner** (`session_memory_scanner.py`)
Automatically scans sessions and generates L2 memories:

```python
class SessionMemoryScanner:
    """Session memory scanner"""
    
    def __init__(self, memory_generation_service: MemoryGenerationService):
        self.memory_generation_service = memory_generation_service
        self.scan_interval = 300  # 5分钟扫描一次
        self.running = False
    
    async def start_scanning(self):
        """Start scanning"""
        self.running = True
        while self.running:
            try:
                await self._scan_sessions()
                await asyncio.sleep(self.scan_interval)
            except Exception as e:
                logger.error(f"Session scanning failed: {e}")
                await asyncio.sleep(60)  # Wait 1 minute after error
    
    async def _scan_sessions(self):
        """Scan sessions"""
        # Get sessions to scan
        sessions_to_scan = await self._get_sessions_to_scan()
        
        for session in sessions_to_scan:
            try:
                await self._generate_session_memory(session)
            except Exception as e:
                logger.error(f"Generate session memory failed {session['session_id']}: {e}")
    
    async def _generate_session_memory(self, session: Dict[str, Any]):
        """Generate session memory"""
        # Get session dialogue data
        dialogue_data = await self._get_session_dialogue(session["session_id"])
        
        if len(dialogue_data) < 2:  # At least 2 messages needed
            return
        
        # Generate L2 session memory
        await self.memory_generation_service.generate_memory(
            session_id=session["session_id"],
            user_id=session["user_id"],
            dialogue_data=dialogue_data
        )
```

### 4. **User Service** (`user_service.py`)
User-related business logic:

```python
class UserService:
    """User service"""
    
    def __init__(self, storage_manager: MemoryStorageManager):
        self.storage_manager = storage_manager
    
    async def create_user(
        self, 
        username: str, 
        email: str, 
        password: str,
        full_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create user"""
        # Validate user data
        await self._validate_user_data(username, email, password)
        
        # Create user record
        user_data = {
            "username": username,
            "email": email,
            "password_hash": self._hash_password(password),
            "full_name": full_name,
            "created_at": datetime.now(),
            "is_active": True
        }
        
        user_id = await self.storage_manager.create_user(user_data)
        return {"user_id": user_id, "username": username}
    
    async def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        """Get user profile"""
        user = await self.storage_manager.get_user(user_id)
        if not user:
            raise ValueError("User does not exist")
        
        # Get user statistics
        stats = await self._get_user_stats(user_id)
        
        return {
            "user_id": user_id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "created_at": user.created_at,
            "stats": stats
        }
    
    async def _get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """Get user statistics"""
        # Get memory count
        memory_count = await self.storage_manager.count_user_memories(user_id)
        
        # Get session count
        session_count = await self.storage_manager.count_user_sessions(user_id)
        
        # Get activity score
        activity_score = await self._calculate_activity_score(user_id)
        
        return {
            "memory_count": memory_count,
            "session_count": session_count,
            "activity_score": activity_score
        }
```

### 5. **Character Service** (`character_service.py`)
Manages expert characters and agents:

```python
class CharacterService:
    """Character service"""
    
    def __init__(self, storage_manager: MemoryStorageManager):
        self.storage_manager = storage_manager
    
    async def create_character(
        self, 
        name: str, 
        description: str, 
        system_prompt: str,
        user_id: str,
        model_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create character"""
        character_data = {
            "name": name,
            "description": description,
            "system_prompt": system_prompt,
            "user_id": user_id,
            "model_config": model_config or {},
            "created_at": datetime.now(),
            "is_active": True
        }
        
        character_id = await self.storage_manager.create_character(character_data)
        return {"character_id": character_id, "name": name}
    
    async def get_character(self, character_id: str) -> Dict[str, Any]:
        """Get character information"""
        character = await self.storage_manager.get_character(character_id)
        if not character:
            raise ValueError("Character does not exist")
        
        return {
            "character_id": character_id,
            "name": character.name,
            "description": character.description,
            "system_prompt": character.system_prompt,
            "model_config": character.model_config,
            "created_at": character.created_at,
            "is_active": character.is_active
        }
    
    async def update_character(
        self, 
        character_id: str, 
        updates: Dict[str, Any]
    ) -> bool:
        """Update character"""
        allowed_fields = ["name", "description", "system_prompt", "model_config"]
        filtered_updates = {k: v for k, v in updates.items() if k in allowed_fields}
        
        if not filtered_updates:
            return False
        
        filtered_updates["updated_at"] = datetime.now()
        return await self.storage_manager.update_character(character_id, filtered_updates)
```

### 6. **Scheduler Service** (`scheduler_service.py`)
Scheduled task management:

```python
class SchedulerService:
    """Scheduler service"""
    
    def __init__(self):
        self.scheduled_tasks = {}
        self.running = False
    
    async def start_scheduler(self):
        """Start scheduler"""
        self.running = True
        while self.running:
            try:
                await self._execute_scheduled_tasks()
                await asyncio.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Scheduler execution failed: {e}")
    
    async def schedule_task(
        self, 
        task_id: str, 
        task_func: callable, 
        schedule_time: datetime,
        **kwargs
    ):
        """Schedule task"""
        self.scheduled_tasks[task_id] = {
            "task_func": task_func,
            "schedule_time": schedule_time,
            "kwargs": kwargs,
            "status": "scheduled"
        }
    
    async def _execute_scheduled_tasks(self):
        """Execute scheduled tasks"""
        now = datetime.now()
        
        for task_id, task_info in self.scheduled_tasks.items():
            if (task_info["status"] == "scheduled" and 
                task_info["schedule_time"] <= now):
                
                try:
                    await task_info["task_func"](**task_info["kwargs"])
                    task_info["status"] = "completed"
                except Exception as e:
                    logger.error(f"Task execution failed {task_id}: {e}")
                    task_info["status"] = "failed"
```

### 7. **Scheduled Backfill Service** (`scheduled_backfill_service.py`)
Automatically backfills missing memories:

```python
class ScheduledBackfillService:
    """Scheduled backfill service"""
    
    def __init__(
        self, 
        memory_generation_service: MemoryGenerationService,
        storage_manager: MemoryStorageManager
    ):
        self.memory_generation_service = memory_generation_service
        self.storage_manager = storage_manager
        self.backfill_interval = 3600  # 1小时执行一次
        self.running = False
    
    async def start_backfill_service(self):
        """Start backfill service"""
        self.running = True
        while self.running:
            try:
                await self._execute_backfill()
                await asyncio.sleep(self.backfill_interval)
            except Exception as e:
                logger.error(f"Backfill service execution failed: {e}")
    
    async def _execute_backfill(self):
        """Execute backfill"""
        # Find sessions to backfill
        sessions_to_backfill = await self._find_sessions_to_backfill()
        
        for session in sessions_to_backfill:
            try:
                await self._backfill_session_memories(session)
            except Exception as e:
                logger.error(f"Backfill session failed {session['session_id']}: {e}")
    
    async def _backfill_session_memories(self, session: Dict[str, Any]):
        """Backfill session memories"""
        # Get session dialogue data
        dialogue_data = await self.storage_manager.get_session_dialogue(
            session["session_id"]
        )
        
        if not dialogue_data:
            return
        
        # Generate missing memories
        await self.memory_generation_service.generate_memory(
            session_id=session["session_id"],
            user_id=session["user_id"],
            dialogue_data=dialogue_data
        )
```

## 🚀 Usage Examples

### Initialize Services
```python
from services.memory_generation_service import MemoryGenerationService
from services.session_context_manager import SessionContextManager
from services.user_service import UserService

# Create service instances
memory_service = MemoryGenerationService()
context_manager = SessionContextManager()
user_service = UserService(storage_manager)

# Initialize services
await memory_service.initialize()
```

### Memory Generation
```python
# Generate memory
dialogue_data = {
    "messages": [
        {"role": "user", "content": "I like machine learning"},
        {"role": "assistant", "content": "Machine learning is an interesting field"}
    ],
    "session_metadata": {"topic": "machine_learning"}
}

result = await memory_service.generate_memory(
    session_id="session_123",
    user_id="user_456",
    dialogue_data=dialogue_data
)

print(f"Generated memory: {result['memories']}")
```

### Session Management
```python
# Create session
session = await context_manager.create_session(
    session_id="session_123",
    user_id="user_456",
    expert_id="expert_789"
)

# Update context
message = {"role": "user", "content": "Hello"}
await context_manager.update_context("session_123", message)

# Get session context
context = await context_manager.get_session_context("session_123")
print(f"Session context: {context}")
```

### User Management
```python
# Create user
user = await user_service.create_user(
    username="testuser",
    email="test@example.com",
    password="secure_password_here",  # Use strong password
    full_name="Test User"
)

# Get user profile
profile = await user_service.get_user_profile(user["user_id"])
print(f"User profile: {profile}")
```

## 📊 Performance Optimization

### 1. **Connection Pool Management**
```python
class ServiceConnectionManager:
    """Service connection manager"""
    
    def __init__(self):
        self.connection_pools = {}
    
    async def get_connection(self, service_type: str):
        """Get connection"""
        if service_type not in self.connection_pools:
            self.connection_pools[service_type] = await self._create_pool(service_type)
        
        return self.connection_pools[service_type]
    
    async def _create_pool(self, service_type: str):
        """Create connection pool"""
        if service_type == "database":
            return await self._create_db_pool()
        elif service_type == "redis":
            return await self._create_redis_pool()
        # Other service types...
```

### 2. **Caching Strategy**
```python
class ServiceCache:
    """Service cache"""
    
    def __init__(self, ttl: int = 3600):
        self.cache = {}
        self.ttl = ttl
    
    async def get(self, key: str) -> Optional[Any]:
        """Get cache"""
        if key in self.cache:
            cached_data = self.cache[key]
            if time.time() - cached_data["timestamp"] < self.ttl:
                return cached_data["value"]
        return None
    
    async def set(self, key: str, value: Any):
        """Set cache"""
        self.cache[key] = {
            "value": value,
            "timestamp": time.time()
        }
```

### 3. **Batch Processing**
```python
class BatchProcessor:
    """Batch processor"""
    
    def __init__(self, batch_size: int = 100):
        self.batch_size = batch_size
        self.pending_items = []
    
    async def add_item(self, item: Any):
        """Add item to batch"""
        self.pending_items.append(item)
        
        if len(self.pending_items) >= self.batch_size:
            await self._process_batch()
    
    async def _process_batch(self):
        """Process batch"""
        if not self.pending_items:
            return
        
        batch = self.pending_items[:self.batch_size]
        self.pending_items = self.pending_items[self.batch_size:]
        
        # Process batch in parallel
        tasks = [self._process_item(item) for item in batch]
        await asyncio.gather(*tasks)
```

## 🛡️ Error Handling

### Service Exceptions
```python
class ServiceException(Exception):
    """Service base exception"""
    pass

class MemoryGenerationError(ServiceException):
    """Memory generation exception"""
    pass

class SessionContextError(ServiceException):
    """Session context exception"""
    pass

class UserServiceError(ServiceException):
    """User service exception"""
    pass
```

### Error Handling Strategy
```python
class ServiceErrorHandler:
    """Service error handler"""
    
    @staticmethod
    async def handle_error(error: Exception, context: Dict[str, Any]):
        """Handle error"""
        logger.error(f"Service error: {error}", extra=context)
        
        if isinstance(error, MemoryGenerationError):
            # Memory generation error handling
            await ServiceErrorHandler._handle_memory_error(error, context)
        elif isinstance(error, SessionContextError):
            # Session context error handling
            await ServiceErrorHandler._handle_session_error(error, context)
        else:
            # Generic error handling
            await ServiceErrorHandler._handle_generic_error(error, context)
```

## 📝 Development Guide

### Adding New Services
1. Create service class inheriting from base service interface
2. Implement core business methods
3. Add error handling and logging
4. Write unit and integration tests

### Service Design Principles
1. **Single Responsibility**: Each service handles one business function
2. **Dependency Injection**: Inject dependencies through constructor
3. **Asynchronous Processing**: Use async methods for performance
4. **Error Handling**: Proper exception handling and logging
5. **Resource Management**: Clean up temporary resources promptly

## 🧪 Testing

### Unit Tests
```python
import pytest
from services.memory_generation_service import MemoryGenerationService

@pytest.mark.asyncio
async def test_memory_generation():
    """Test memory generation"""
    service = MemoryGenerationService()
    await service.initialize()
    
    dialogue_data = {
        "messages": [{"role": "user", "content": "Hello"}]
    }
    
    result = await service.generate_memory(
        session_id="test_session",
        user_id="test_user",
        dialogue_data=dialogue_data
    )
    
    assert result is not None
    assert "memories" in result
```

### Integration Tests
```python
@pytest.mark.asyncio
async def test_service_integration():
    """Test service integration"""
    # Test collaboration of multiple services
    memory_service = MemoryGenerationService()
    context_manager = SessionContextManager()
    
    await memory_service.initialize()
    
    # Create session
    session = await context_manager.create_session("session_1", "user_1")
    
    # Generate memory
    result = await memory_service.generate_memory(
        session_id="session_1",
        user_id="user_1",
        dialogue_data={"messages": []}
    )
    
    assert result is not None
```

## 📚 Related Documentation

- [TiMem Core Module](../timem/README.md)
- [Storage Layer Documentation](../storage/README.md)
- [LLM Adapter Documentation](../llm/README.md)
- [API Application Layer Documentation](../app/README.md)
