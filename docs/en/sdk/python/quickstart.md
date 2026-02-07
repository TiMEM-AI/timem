# Python SDK Quick Start

TiMem Python SDK provides a simple and easy-to-use interface for interacting with TiMem Cloud Service or self-hosted instances.

## Installation

### Using pip (Recommended)

```bash
pip install timem-sdk
```

### Using poetry

```bash
poetry add timem-sdk
```

### Using pipenv

```bash
pipenv install timem-sdk
```

### Install from Source

```bash
git clone https://github.com/your-org/timem.git
cd timem
pip install -e .
```

### Install Development Version

```bash
pip install git+https://github.com/your-org/timem.git
```

## Initialization

### Basic Configuration

```python
from timem import TiMemClient

# Initialize with API Key
client = TiMemClient(
    api_key="your-api-key-here"
)
```

### Environment Variable Configuration (Recommended)

**Create `.env` file**:

```bash
TIMEM_API_KEY=timem_sk_xxxxx
TIMEM_API_URL=https://api.timem.cloud/v1
```

**Load configuration**:

```python
import os
from dotenv import load_dotenv
from timem import TiMemClient

load_dotenv()

client = TiMemClient(
    api_key=os.environ.get("TIMEM_API_KEY")
)
```

### Complete Configuration Options

```python
client = TiMemClient(
    api_key="your-api-key",
    base_url="https://api.timem.cloud/v1",  # Custom API address
    timeout=30,                          # Request timeout (seconds)
    max_retries=3,                       # Maximum retry attempts
    enable_logging=False                 # Enable logging
)
```

## Basic Usage

### 1. Add Memory

```python
from timem import TiMemClient

client = TiMemClient(api_key="your-api-key")

# Add conversation memory
memory = client.add_memory(
    user_id="user_123",
    content="User said they like vegetarian food, especially Italian cuisine",
    session_id="session_456",  # Optional
    metadata={                 # Optional metadata
        "source": "chat",
        "timestamp": "2026-02-08T10:00:00Z",
        "confidence": 0.95
    }
)

print(f"Memory ID: {memory.id}")
print(f"Memory content: {memory.content}")
print(f"Memory level: {memory.level}")
print(f"Created at: {memory.created_at}")
```

**Response Example**:

```python
Memory(
    id="mem_xxxxx",
    user_id="user_123",
    content="User said they like vegetarian food, especially Italian cuisine",
    level="L1",
    session_id="session_456",
    created_at="2026-02-08T10:00:00Z"
)
```

### 2. Search Memories

```python
# Semantic search
results = client.search_memories(
    user_id="user_123",
    query="What are the user's dietary preferences?",
    limit=5
)

for memory in results:
    print(f"[{memory.level}] {memory.content}")
    print(f"Relevance: {memory.score}")
    print(f"Time: {memory.created_at}")
    print("-" * 40)
```

**Search Options**:

```python
results = client.search_memories(
    user_id="user_123",
    query="User dietary preferences",
    limit=10,                    # Return count
    level="L2",                  # Filter by level
    session_id="session_456",    # Filter by session
    date_from="2026-01-01",      # Date range
    date_to="2026-01-31"
)
```

### 3. Get Session Memories

```python
# Get all memories for a specific session
memories = client.get_session_memories(
    user_id="user_123",
    session_id="session_456",
    limit=100
)

for memory in memories:
    print(f"[{memory.level}] {memory.content}")
```

### 4. Batch Add Conversations

```python
# Generate memories from conversation logs
conversation = [
    {"role": "user", "content": "Hello, my name is Zhang San"},
    {"role": "assistant", "content": "Hello Zhang San! Nice to meet you."},
    {"role": "user", "content": "I like programming and AI research"},
    {"role": "assistant", "content": "Great! I'm an AI enthusiast too."},
    {"role": "user", "content": "I mainly use Python"},
]

memories = client.add_conversation(
    user_id="user_123",
    session_id="session_456",
    conversation=conversation,
    generate_levels=["L1", "L2"]  # Generate L1 and L2 memories
)

print(f"Generated {len(memories)} memories")
for memory in memories:
    print(f"[{memory.level}] {memory.content}")
```

### 5. Update Memory

```python
# Update memory content
updated_memory = client.update_memory(
    memory_id="mem_xxxxx",
    content="Updated memory content",
    metadata={"updated": True}
)
```

### 6. Delete Memory

```python
# Delete single memory
client.delete_memory(memory_id="mem_xxxxx")

# Delete all memories in a session
client.delete_session_memories(
    user_id="user_123",
    session_id="session_456"
)
```

## Complete Examples

### AI Assistant Integration

```python
import os
from dotenv import load_dotenv
from timem import TiMemClient

load_dotenv()

class AIAssistant:
    """AI Assistant integrated with TiMem"""

    def __init__(self):
        self.client = TiMemClient(
            api_key=os.environ.get("TIMEM_API_KEY")
        )
        self.user_id = "user_123"
        self.session_id = "session_456"

    def chat(self, message: str) -> str:
        """Process user message and generate response"""

        # 1. Retrieve relevant memories
        memories = self.client.search_memories(
            user_id=self.user_id,
            query=message,
            limit=3
        )

        # 2. Build context
        context = self._build_context(memories)

        # 3. Call LLM to generate response
        response = self._generate_response(message, context)

        # 4. Save conversation memory
        self._save_conversation(message, response)

        return response

    def _build_context(self, memories):
        """Build context"""
        if not memories:
            return "(No historical memories)"

        context_parts = []
        for memory in memories:
            context_parts.append(f"- {memory.content}")

        return "Known information:\n" + "\n".join(context_parts)

    def _generate_response(self, message: str, context: str) -> str:
        """Generate response (example using OpenAI)"""
        from openai import OpenAI

        llm = OpenAI()

        prompt = f"""{context}

User message: {message}

Please generate a personalized response based on known information."""

        completion = llm.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}]
        )

        return completion.choices[0].message.content

    def _save_conversation(self, user_message: str, assistant_message: str):
        """Save conversation memory"""
        conversation = [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": assistant_message}
        ]

        self.client.add_conversation(
            user_id=self.user_id,
            session_id=self.session_id,
            conversation=conversation
        )

# Usage example
if __name__ == "__main__":
    assistant = AIAssistant()

    # First conversation
    response1 = assistant.chat("Hello, my name is Li Ming")
    print(f"Assistant: {response1}")

    # Second conversation (assistant will remember user's name)
    response2 = assistant.chat("Do you remember my name?")
    print(f"Assistant: {response2}")
```

### Customer Support Bot

```python
from timem import TiMemClient
from datetime import datetime

class SupportBot:
    """Customer Support Bot"""

    def __init__(self):
        self.client = TiMemClient(api_key="your-api-key")

    def handle_ticket(self, user_id: str, message: str):
        """Handle support ticket"""

        # Search related issue history
        history = self.client.search_memories(
            user_id=user_id,
            query=message,
            limit=5
        )

        # Check for similar issues
        if history and history[0].score > 0.9:
            # High similarity, possibly duplicate issue
            return f"I see you asked a similar question before: {history[0].content}"

        # Save new issue
        self.client.add_memory(
            user_id=user_id,
            content=f"User issue: {message}",
            metadata={
                "type": "ticket",
                "timestamp": datetime.now().isoformat(),
                "resolved": False
            }
        )

        return "Your issue has been recorded, we will process it soon."

    def resolve_ticket(self, user_id: str, solution: str):
        """Record solution"""

        self.client.add_memory(
            user_id=user_id,
            content=f"Solution: {solution}",
            metadata={"type": "solution", "resolved": True}
        )
```

## Async Support

SDK provides complete async API:

```python
import asyncio
from timem import AsyncTiMemClient

async def main():
    client = AsyncTiMemClient(api_key="your-api-key")

    # Async add memory
    memory = await client.add_memory(
        user_id="user_123",
        content="User likes vegetarian food"
    )

    # Async search
    results = await client.search_memories(
        user_id="user_123",
        query="dietary preferences"
    )

    # Batch async operations
    tasks = [
        client.add_memory(user_id="user_123", content=f"memory{i}")
        for i in range(10)
    ]
    memories = await asyncio.gather(*tasks)

    print(f"Batch added {len(memories)} memories")

asyncio.run(main())
```

## Error Handling

```python
from timem import TiMemClient
from timem.exceptions import (
    TiMemAPIError,
    AuthenticationError,
    RateLimitError,
    NotFoundError,
    ValidationError
)

client = TiMemClient(api_key="your-api-key")

try:
    memory = client.add_memory(
        user_id="user_123",
        content="Test content"
    )

except AuthenticationError:
    print("API Key is invalid or expired")

except RateLimitError as e:
    print(f"Too many requests, please retry after {e.retry_after} seconds")

except NotFoundError:
    print("Resource not found")

except ValidationError as e:
    print(f"Parameter validation failed: {e.errors}")

except TiMemAPIError as e:
    print(f"API error: {e.message} (code: {e.code})")

except Exception as e:
    print(f"Unknown error: {e}")
```

## Advanced Features

### Custom Memory Levels

```python
# Generate memories at specific levels
client.add_memory(
    user_id="user_123",
    content="User likes vegetarian food",
    level="L2",  # Specify level directly
    metadata={"type": "preference"}
)

# Get memories at specific levels
memories = client.search_memories(
    user_id="user_123",
    query="preferences",
    level="L2"  # Search only L2 memories
)
```

### Batch Operations

```python
# Batch add memories
memories_data = [
    {"content": "Memory1", "metadata": {"index": 1}},
    {"content": "Memory2", "metadata": {"index": 2}},
    {"content": "Memory3", "metadata": {"index": 3}},
]

memories = client.add_memories_batch(
    user_id="user_123",
    memories=memories_data
)

print(f"Batch added {len(memories)} memories")
```

### Metadata Filtering

```python
# Add memory with metadata
client.add_memory(
    user_id="user_123",
    content="User purchased premium plan",
    metadata={
        "type": "purchase",
        "plan": "premium",
        "amount": 99.99
    }
)

# Filter by metadata when searching
results = client.search_memories(
    user_id="user_123",
    query="purchase records",
    metadata_filter={
        "type": "purchase",
        "plan": "premium"
    }
)
```

## Testing and Debugging

### Use Test Keys

```python
import os

# Use test key in development environment
if os.environ.get("ENVIRONMENT") == "development":
    api_key = os.environ.get("TIMEM_TEST_API_KEY")
else:
    api_key = os.environ.get("TIMEM_API_KEY")

client = TiMemClient(api_key=api_key)
```

### Enable Logging

```python
import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# SDK will output detailed logs
client = TiMemClient(
    api_key="your-api-key",
    enable_logging=True
)
```

### Mock Responses (Testing)

```python
from unittest.mock import Mock, patch

# Don't call real API during testing
with patch('timem.client.TiMemClient.add_memory') as mock_add:
    mock_add.return_value = Mock(id="test_mem_123")

    client = TiMemClient(api_key="test-key")
    memory = client.add_memory(user_id="test", content="test")

    print(memory.id)  # test_mem_123
```

## Performance Optimization

### Connection Pool

```python
from timem import TiMemClient

# SDK automatically manages connection pool
client = TiMemClient(
    api_key="your-api-key",
    max_connections=100,      # Maximum connections
    max_keepalive_connections=20  # Keep alive connections
)
```

### Batch Processing

```python
# Use batch operations to reduce network round trips
memories = [f"memory{i}" for i in range(100)]

# ✅ Good: Batch add
client.add_memories_batch(
    user_id="user_123",
    memories=[{"content": m} for m in memories]
)

# ❌ Bad: Add one by one
for memory in memories:
    client.add_memory(user_id="user_123", content=memory)
```

## Configuration Management

### Configuration File

```python
# config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    TIMEM_API_KEY = os.environ.get("TIMEM_API_KEY")
    TIMEM_API_URL = os.environ.get("TIMEM_API_URL", "https://api.timem.cloud/v1")
    TIMEM_TIMEOUT = int(os.environ.get("TIMEM_TIMEOUT", "30"))
    TIMEM_MAX_RETRIES = int(os.environ.get("TIMEM_MAX_RETRIES", "3"))

# Usage
from timem import TiMemClient
from config import Config

client = TiMemClient(
    api_key=Config.TIMEM_API_KEY,
    base_url=Config.TIMEM_API_URL,
    timeout=Config.TIMEM_TIMEOUT,
    max_retries=Config.TIMEM_MAX_RETRIES
)
```

## Next Steps

- [Configuration Guide](configuration.md) - Detailed configuration options
- [Advanced Usage](advanced-usage.md) - Advanced features and tips
- [API Reference](../../api-reference/overview.md) - Complete API documentation
- [Complete Examples](../../examples/ai-assistant.md) - AI assistant complete implementation

## Get Help

- **Documentation**: [https://docs.timem.cloud](https://docs.timem.cloud)
- **GitHub Issues**: [Report Issue](https://github.com/your-org/timem/issues)
- **Email Support**: support@timem.cloud
