# TiMem Troubleshooting Guide

This document helps you resolve common issues when using TiMem.

## Table of Contents

- [Installation Issues](#installation-issues)
- [Connection Issues](#connection-issues)
- [Memory Issues](#memory-issues)
- [Performance Issues](#performance-issues)
- [API Issues](#api-issues)

## Installation Issues

### Issue: pip install fails with dependency conflicts

**Symptoms**: Error messages about conflicting package versions during installation.

**Solution**:
```bash
# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# Upgrade pip first
pip install --upgrade pip

# Install with specific versions
pip install -r requirements.txt
```

### Issue: Database connection fails during setup

**Symptoms**: "Connection refused" or "Database not found" errors.

**Solution**:
1. Ensure Docker is running: `docker ps`
2. Start database services:
```bash
cd migration
docker-compose up -d
```
3. Check database status: `docker-compose ps`

## Connection Issues

### Issue: Cannot connect to TiMem server

**Symptoms**: "Connection refused" or timeout errors.

**Solutions**:

1. **Check if server is running**:
```bash
# Check process
ps aux | grep timem

# Check port
netstat -an | grep 8000
```

2. **Verify configuration**:
```python
# Check base_url in your code
memory = AsyncMemory(
    base_url="http://localhost:8000"  # Ensure correct
)
```

3. **Test connection**:
```bash
curl http://localhost:8000/health
```

### Issue: Authentication errors

**Symptoms**: "Invalid API key" or "Unauthorized" errors.

**Solutions**:

1. **For cloud service**:
```python
# Verify API key
memory = AsyncMemory(
    api_key="your-api-key",  # Check from console
    base_url="https://api.timem.cloud"
)
```

2. **For self-hosted**:
```bash
# Check username/password
export TIMEM_USERNAME=your_username
export TIMEM_PASSWORD=your_password
```

## Memory Issues

### Issue: Memory not being saved

**Symptoms**: `add()` returns success but search finds nothing.

**Solutions**:

1. **Check required parameters**:
```python
result = await memory.add(
    messages=[...],
    user_id="user_001",      # Required
    character_id="assistant", # Required
    session_id="session_001"  # Required
)
```

2. **Verify backfill configuration**:
```yaml
# config/settings.yaml
memory_generation:
  scheduled_backfill:
    enabled: true
    layers: ["L2", "L3", "L4", "L5"]
```

3. **Manual trigger backfill**:
```python
from services.scheduled_backfill_service import get_scheduled_backfill_service

service = get_scheduled_backfill_service()
await service.backfill_for_user(
    user_id="user_001",
    layers=["L2", "L3", "L4", "L5"]
)
```

### Issue: Search returns no results

**Symptoms**: `search()` returns empty results.

**Solutions**:

1. **Check if memories exist**:
```python
results = await memory.search(
    query="test",
    user_id="user_001",
    limit=10
)
print(results)  # Check response
```

2. **Use broader query**:
```python
# Too specific
await memory.search(query="exact phrase match")

# Better
await memory.search(query="general keyword")
```

3. **Verify memory levels**:
```python
# Specify which levels to search
await memory.search(
    query="test",
    level="L1,L2,L3,L4,L5"
)
```

## Performance Issues

### Issue: Slow memory generation

**Symptoms**: Memory generation takes too long.

**Solutions**:

1. **Enable caching**:
```yaml
# config/settings.yaml
memory_generation:
  optimization:
    cache_enabled: true
    cache_ttl: 3600
```

2. **Adjust batch size**:
```yaml
memory_generation:
  scheduled_backfill:
    batch_size: 50  # Increase for better throughput
```

3. **Use concurrent processing**:
```yaml
parallel_tasks: 5  # Increase parallelism
```

### Issue: High memory usage

**Symptoms**: TiMem process consumes too much memory.

**Solutions**:

1. **Limit concurrent tasks**:
```yaml
parallel_tasks: 3  # Reduce from default
```

2. **Enable memory cleanup**:
```python
# Regularly close connections
await memory.aclose()
```

3. **Monitor with metrics**:
```python
from timem.utils.stats_collector import StatsCollector

collector = StatsCollector()
print(collector.get_memory_stats())
```

## API Issues

### Issue: 500 Internal Server Error

**Symptoms**: API calls return 500 errors.

**Solutions**:

1. **Check server logs**:
```bash
# Check application logs
tail -f logs/timem.log

# Check Docker logs
docker-compose logs -f
```

2. **Verify input format**:
```python
# Correct format
messages = [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi there"}
]
```

3. **Check database status**:
```bash
# PostgreSQL
docker exec -it postgres psql -U timem -d timem

# Qdrant
curl http://localhost:6333/collections
```

### Issue: Rate limiting errors

**Symptoms**: "Too many requests" errors.

**Solutions**:

1. **For cloud service**:
- Upgrade to higher tier plan
- Implement client-side rate limiting

2. **For self-hosted**:
```yaml
# Adjust rate limits
api:
  rate_limit:
    enabled: true
    requests_per_minute: 1000  # Increase as needed
```

## Getting More Help

If none of the above solutions work:

1. **Check logs**:
   ```bash
   tail -f logs/timem.log
   ```

2. **Enable debug mode**:
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

3. **Report the issue**:
   - GitHub Issues: https://github.com/TiMEM-AI/timem/issues
   - Include: error messages, logs, configuration, steps to reproduce

## Common Error Messages

| Error | Cause | Solution |
|-------|-------|----------|
| `Connection refused` | Server not running | Start TiMem server |
| `Invalid API key` | Wrong credentials | Verify API key from console |
| `Database not found` | Database not initialized | Run `docker-compose up -d` |
| `Memory not found` | No memories for user | Add some memories first |
| `Timeout` | Request too slow | Check network, increase timeout |

---

**Last Updated**: 2026-02-08
