# API Authentication Guide

This document provides detailed information about TiMem API authentication mechanisms, API Key management, and security best practices.

## Authentication Overview

TiMem API uses **Bearer Token** authentication. Each API request must include a valid API Key in the HTTP Header.

```http
Authorization: Bearer YOUR_API_KEY
```

## Getting an API Key

### Register an Account

1. Visit [TiMem Cloud Platform](https://cloud.timem.cloud)
2. Click **Sign Up** to register an account
3. Verify your email address

### Create an API Key

1. Log in to the cloud platform
2. Navigate to **Settings** → **API Keys**
3. Click **Create New Key**
4. Fill in the following information:
   - **Key Name**: Key name (e.g., "Production", "Development")
   - **Key Type**: Key type (Production/Test/Limited)
   - **Permissions**: Permission scope (Read/Write/Admin)
5. Click **Create**
6. **Important**: Copy the key, it will only be shown once!

### API Key Format

Valid API Key format:

```
timem_sk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

- Prefix: `timem_sk_`
- Length: 64 characters
- Character set: lowercase letters and numbers

## Using an API Key

### Python SDK

```python
from timem import TiMemClient
import os

# Method 1: Direct input
client = TiMemClient(api_key="timem_sk_xxxxx")

# Method 2: Environment variable (recommended)
client = TiMemClient(api_key=os.environ.get("TIMEM_API_KEY"))
```

### Environment Variable Configuration

Create a `.env` file:

```bash
# TiMem API Configuration
TIMEM_API_KEY=timem_sk_xxxxx
TIMEM_API_URL=https://api.timem.cloud/v1
```

Load environment variables:

```python
from dotenv import load_dotenv
import os

load_dotenv()

api_key = os.environ.get("TIMEM_API_KEY")
```

### cURL

```bash
# Set environment variable
export TIMEM_API_KEY="timem_sk_xxxxx"

# Use environment variable
curl -H "Authorization: Bearer $TIMEM_API_KEY" \
  https://api.timem.cloud/v1/memories
```

### JavaScript/TypeScript

```javascript
import { TiMemClient } from 'timem-sdk';

// Method 1: Direct input
const client = new TiMemClient({
  apiKey: 'timem_sk_xxxxx'
});

// Method 2: Environment variable
const client = new TiMemClient({
  apiKey: process.env.TIMEM_API_KEY
});
```

## API Key Types and Permissions

### Production Key

**Purpose**: Production environment

**Permissions**:
- ✅ Read memories
- ✅ Create memories
- ✅ Update memories
- ✅ Delete memories
- ✅ Manage users
- ✅ Manage sessions

**Recommendations**:
- Use for production environments
- Rotate regularly
- Restrict IP addresses

### Test Key

**Purpose**: Development and testing

**Permissions**:
- ✅ Read memories
- ✅ Create memories
- ❌ Delete memories
- ❌ Manage users

**Recommendations**:
- Use for development environments
- Should not be used in production
- Can be shared publicly (for testing)

### Limited Key

**Purpose**: Specific feature restrictions

**Configurable Permissions**:
- Read-only access
- Specific endpoints only
- Specific users only

**Recommendations**:
- Use for third-party integrations
- Use for restricted features
- Strictly limit permissions

## Security Best Practices

### ✅ Recommended Practices

#### 1. Use Environment Variables

```bash
# .env file
TIMEM_API_KEY=timem_sk_xxxxx
```

```python
# Read in code
import os
api_key = os.environ.get("TIMEM_API_KEY")
```

#### 2. Use Key Management Services

**AWS Secrets Manager**:
```python
import boto3
import json

client = boto3.client('secretsmanager')
response = client.get_secret_value(SecretId='timem/api_key')
secret = json.loads(response['SecretString'])
api_key = secret['api_key']
```

**Azure Key Vault**:
```python
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

credential = DefaultAzureCredential()
client = SecretClient(vault_url="https://your-vault.vault.azure.net", credential=credential)
api_key = client.get_secret("timem-api-key").value
```

**Google Secret Manager**:
```python
from google.cloud import secretmanager

client = secretmanager.SecretManagerServiceClient()
name = "projects/PROJECT/secrets/timem-api-key/versions/latest"
response = client.access_secret_version(name=name)
api_key = response.payload.data.decode('UTF-8')
```

#### 3. Regularly Rotate API Keys

```python
import os
from timem import TiMemClient

def rotate_api_key():
    """Rotate API Key"""
    old_key = os.environ.get("TIMEM_API_KEY_OLD")
    new_key = os.environ.get("TIMEM_API_KEY_NEW")

    # Test new key
    test_client = TiMemClient(api_key=new_key)
    try:
        test_client.list_memories(limit=1)
        print("New key works correctly")
    except Exception as e:
        print(f"New key test failed: {e}")
        return False

    # Update application configuration
    # ... update configuration logic ...
    print("Key rotation successful")
    return True
```

**Rotation Strategy**:
- **Development keys**: Rotate weekly
- **Test keys**: Rotate monthly
- **Production keys**: Rotate quarterly
- **When leakage is discovered**: Rotate immediately

#### 4. Limit API Key Permissions

Only grant necessary permissions:

```python
# Read-only client
read_only_client = TiMemClient(
    api_key="timem_read_only_xxxxx",
    permissions=["read"]
)

# Write client
write_client = TiMemClient(
    api_key="timem_write_xxxxx",
    permissions=["read", "write"]
)
```

#### 5. Use IP Whitelists

Configure IP whitelists in the cloud platform:

```
Allowed IP addresses:
- 203.0.113.1/32 (production server)
- 198.51.100.0/24 (office network)
```

### ❌ Practices to Avoid

#### 1. Don't Hardcode API Keys

```python
# ❌ Wrong example
api_key = "timem_sk_1234567890"  # Don't do this!

# ✅ Correct approach
api_key = os.environ.get("TIMEM_API_KEY")
```

#### 2. Don't Commit API Keys to Version Control

**Add to `.gitignore`**:

```gitignore
# Environment variable files
.env
.env.local
.env.*.local

# Key files
secrets.yaml
secrets.json
*.key
```

**Detect committed keys**:

```bash
# Search for possible keys
git log --all --full-history --source -- "**/.env"
git log --all --full-history --source -- "**/secrets.*"
```

#### 3. Don't Use Production Keys in Frontend Code

```javascript
// ❌ Wrong: frontend exposes key
const client = new TiMemClient({
  apiKey: 'timem_sk_production_xxxxx'  // Anyone can see this!
});

// ✅ Correct: proxy through backend
// Frontend calls backend API, backend uses key to call TiMem
```

#### 4. Don't Log Keys

```python
# ❌ Wrong
print(f"Using API key: {api_key}")  # Key appears in logs
logger.info(f"API key: {api_key}")

# ✅ Correct
print(f"Using API key: {api_key[:10]}...")  # Show only first few characters
logger.info("API key configured")
```

## API Key Rotation

### Rotation Steps

1. **Create new key**:
   - Create a new API Key in the cloud platform
   - Set the same permissions and restrictions

2. **Test new key**:
   ```python
   new_client = TiMemClient(api_key="new_key")
   new_client.list_memories(limit=1)  # Test read permission
   ```

3. **Update application configuration**:
   - Update environment variables
   - Redeploy application

4. **Verify**:
   - Confirm application works correctly with new key

5. **Delete old key**:
   - Wait 24-48 hours to confirm no issues
   - Delete old key in cloud platform

### Zero-Downtime Rotation

```python
import os
from timem import TiMemClient

class ApiKeyRotator:
    def __init__(self):
        self.primary_key = os.environ.get("TIMEM_API_KEY")
        self.secondary_key = os.environ.get("TIMEM_API_KEY_BACKUP")

    def get_client(self):
        """Get available client"""
        # Try primary key
        try:
            client = TiMemClient(api_key=self.primary_key)
            client.list_memories(limit=1)
            return client
        except:
            pass

        # Try backup key
        if self.secondary_key:
            return TiMemClient(api_key=self.secondary_key)

        raise Exception("No available API Key")
```

## Troubleshooting

### 401 Unauthorized

**Causes**:
- API Key is invalid
- API Key has expired
- API Key has been revoked

**Solutions**:

1. Verify key format:
   ```bash
   echo $TIMEM_API_KEY | grep -E "^timem_sk_[a-z0-9]{64}$"
   ```

2. Check if key has expired:
   - Log in to cloud platform to check key status

3. Regenerate key:
   - Delete old key
   - Create new key
   - Update application configuration

### 403 Forbidden

**Causes**:
- Insufficient API Key permissions
- IP address not in whitelist
- Quota limit exceeded

**Solutions**:

1. Check key permissions:
   - Confirm key has required permissions
   - Upgrade key type or create new key

2. Check IP whitelist:
   - Confirm current IP is in whitelist
   - Add current IP to whitelist

3. Check quota:
   - View usage statistics
   - Upgrade plan

### 429 Rate Limit

**Cause**: Rate limit exceeded

**Solutions**:

1. Implement exponential backoff:
   ```python
   import time

   def call_with_retry(client, max_retries=3):
       for attempt in range(max_retries):
           try:
               return client.add_memory(...)
           except RateLimitError:
               if attempt < max_retries - 1:
                   wait_time = 2 ** attempt  # 1, 2, 4 seconds
                   time.sleep(wait_time)
               else:
                   raise
   ```

2. Use batch operations to reduce request count

3. Upgrade to a plan with higher limits

## Configuration Examples

### Python Project

```python
# config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    TIMEM_API_KEY = os.environ.get("TIMEM_API_KEY")
    TIMEM_API_URL = os.environ.get("TIMEM_API_URL", "https://api.timem.cloud/v1")
    TIMEM_TIMEOUT = int(os.environ.get("TIMEM_TIMEOUT", "30"))

# .env
TIMEM_API_KEY=timem_sk_xxxxx
TIMEM_API_URL=https://api.timem.cloud/v1
TIMEM_TIMEOUT=30
```

### Django Project

```python
# settings.py
import os
from dotenv import load_dotenv

load_dotenv()

TIMEM_API_KEY = os.environ.get("TIMEM_API_KEY")
TIMEM_API_URL = os.environ.get("TIMEM_API_URL", "https://api.timem.cloud/v1")
```

### Node.js Project

```javascript
// .env
TIMEM_API_KEY=timem_sk_xxxxx
TIMEM_API_URL=https://api.timem.cloud/v1

// config.js
require('dotenv').config();

module.exports = {
  apiKey: process.env.TIMEM_API_KEY,
  apiUrl: process.env.TIMEM_API_URL || 'https://api.timem.cloud/v1'
};
```

## Audit and Monitoring

### Key Usage Monitoring

View in cloud platform:
- Number of API calls
- Last used time
- IP addresses used
- Endpoints used

### Anomaly Detection

Set up alerts:
- Unknown IP address using key
- Sudden increase in usage
- Abnormal API call patterns
- Failed authentication attempts

### Audit Logs

Regular checks:
```bash
# View usage records for the last 7 days
curl -H "Authorization: Bearer $TIMEM_API_KEY" \
  https://api.timem.cloud/v1/audit-logs?days=7
```

## Reference Resources

- [API Overview](overview.md) - API overview
- [Python SDK](../sdk/python/quickstart.md) - SDK usage guide
- [Cloud Platform](https://cloud.timem.cloud) - Key management
- [Troubleshooting](../troubleshooting.md) - Common issues
