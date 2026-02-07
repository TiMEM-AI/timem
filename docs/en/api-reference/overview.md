# TiMem REST API Overview

The TiMem REST API provides comprehensive memory management and retrieval capabilities, allowing you to interact with the TiMem service through HTTP requests.

## Basic Information

- **Base URL**: `https://api.timem.cloud/v1`
- **Authentication**: Bearer Token (API Key)
- **Data Format**: JSON
- **Character Encoding**: UTF-8
- **API Version**: v1.0

## Getting an API Key

### Steps

1. Visit [TiMem Cloud Platform](https://console.timem.cloud)
2. Register/Login to your account
3. Go to **Settings** -> **API Keys**
4. Click **Create New Key**
5. Set key name and permissions
6. Copy the generated key (displayed only once!)

### API Key Types

| Type | Permissions | Purpose |
|------|-------------|---------|
| **Production Key** | Full permissions | Production use |
| **Test Key** | Read permissions | Testing and development |
| **Limited Key** | Custom permissions | Specific feature restrictions |

## API Endpoints Overview

### Memory Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/memories` | Add new memory |
| `GET` | `/memories` | Search memories |
| `GET` | `/memories/{id}` | Get single memory |
| `PUT` | `/memories/{id}` | Update memory |
| `DELETE` | `/memories/{id}` | Delete memory |

### Session Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/sessions` | Create session |
| `GET` | `/sessions/{id}` | Get session details |
| `GET` | `/sessions/{id}/memories` | Get all memories in session |
| `DELETE` | `/sessions/{id}` | Delete session |

### User Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/users` | Create user |
| `GET` | `/users/{id}` | Get user information |
| `PUT` | `/users/{id}` | Update user information |
| `DELETE` | `/users/{id}` | Delete user |

### Batch Operations

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/memories/batch` | Batch add memories |
| `POST` | `/conversations` | Generate memories from conversations |

## Authentication

All API requests must include the API Key in the Header:

```http
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json
```

## Request Examples

### Using Python SDK (Recommended)

```python
from timem import AsyncMemory

memory = AsyncMemory(
    api_key="your-api-key",
    base_url="https://api.timem.cloud"
)

result = await memory.add(
    messages=[{"role": "user", "content": "User likes vegetarian food"}],
    user_id="user123"
)
```

### Using cURL

```bash
curl -X POST https://api.timem.cloud/v1/memories \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "messages": [{"role": "user", "content": "User likes vegetarian food"}]
  }'
```

## Response Format

### Success Response

```json
{
  "success": true,
  "data": {
    "id": "mem_xxxxx",
    "user_id": "user123",
    "level": "L1",
    "created_at": "2026-02-08T10:00:00Z"
  }
}
```

### Error Response

```json
{
  "success": false,
  "error": {
    "code": "invalid_api_key",
    "message": "The provided API Key is invalid",
    "details": {}
  }
}
```

## HTTP Status Codes

| Status Code | Meaning | Description |
|-------------|---------|-------------|
| `200 OK` | Success | Request successful |
| `201 Created` | Created | Resource created successfully |
| `400 Bad Request` | Bad Request | Invalid or missing request parameters |
| `401 Unauthorized` | Unauthorized | Invalid or expired API Key |
| `403 Forbidden` | Forbidden | Insufficient API Key permissions |
| `404 Not Found` | Not Found | Resource does not exist |
| `429 Too Many Requests` | Too Many Requests | Rate limit exceeded |
| `500 Internal Server Error` | Server Error | Internal server error |

## Core Concepts

### Memory Levels

TiMem organizes memories into 5 levels:

| Level | Name | Time Granularity | Description |
|-------|------|------------------|-------------|
| L1 | Fragment | Real-time | Fine-grained conversation evidence |
| L2 | Session | Session | Non-redundant event summaries |
| L3 | Day | Day | Daily routines and interests |
| L4 | Week | Week | Evolving behavioral patterns |
| L5 | Profile | Month | Stable persona representations |

### Users and Sessions

- **User**: End user of TiMem (e.g., application's end user)
- **Session**: Single conversation session belonging to a user
- **Memory**: Memory fragment belonging to a user and session

## Best Practices

### 1. Error Handling

```python
from timem import AsyncMemory

memory = AsyncMemory(api_key="your-api-key")

try:
    result = await memory.add(
        messages=[{"role": "user", "content": "..."}],
        user_id="user123"
    )
except Exception as e:
    print(f"API Error: {e}")
```

### 2. Batch Operations

For large amounts of data, use batch APIs for efficiency:

```python
# Add multiple conversations
for conversation in conversations:
    await memory.add(
        messages=conversation["messages"],
        user_id="user123"
    )
```

### 3. Async Requests

For async applications, use the async SDK:

```python
import asyncio
from timem import AsyncMemory

async def main():
    memory = AsyncMemory(api_key="your-api-key")
    result = await memory.add(
        messages=[{"role": "user", "content": "Async memory addition"}],
        user_id="user123"
    )

asyncio.run(main())
```

## SDK vs API Comparison

| Feature | REST API | Python SDK |
|---------|----------|------------|
| Ease of Use | Manual HTTP handling | Simple method calls |
| Type Hints | No | Yes |
| Error Handling | Manual error parsing | Auto exceptions |
| Async Support | Implement yourself | Built-in async client |
| Retry Logic | Implement yourself | Auto retry |
| Recommended For | Non-Python languages | Python applications |

## Changelog

### v1.0.0 (2026-02-08)

**Added**:
- Memory management API
- Session management API
- User management API
- Batch operations API

**Planned**:
- Webhook support
- More filtering and sorting options
- Real-time subscriptions

## Resources

- [Authentication Guide](authentication.md) - API Key management and security practices
- [Python SDK](../sdk/python/quickstart.md) - Python SDK usage guide
- [Troubleshooting](../troubleshooting.md) - Common problem solutions

## Support

- **Documentation**: [https://github.com/TiMEM-AI/timem](https://github.com/TiMEM-AI/timem)
- **GitHub Issues**: [Report Issues](https://github.com/TiMEM-AI/timem/issues)
