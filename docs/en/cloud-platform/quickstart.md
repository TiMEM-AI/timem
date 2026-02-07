# TiMem Cloud Service Quick Start

TiMem Cloud Service provides a ready-to-use memory management solution without deployment. This document helps you quickly get started with TiMem Cloud Service.

## Overview

TiMem Cloud Service offers:

- **Zero Deployment**: No need to configure servers or databases
- **Auto Scaling**: Automatically scales based on traffic
- **High Availability**: 99.9% SLA guarantee
- **Professional Support**: Priority technical support
- **Real-time Monitoring**: Complete usage analytics and monitoring

## 5-Minute Quick Start

### Step 1: Register Account

Visit [TiMem Cloud Platform](https://cloud.timem.cloud) and register an account.

**Registration Methods**:
- Email registration
- GitHub login
- Google login

### Step 2: Get API Key

1. After login, navigate to **Settings** → **API Keys**
2. Click **Create New Key**
3. Set key information:
   - **Key Name**: Key name (e.g., "Production")
   - **Key Type**: Key type (Production/Test)
   - **Permissions**: Permission scope
4. Click **Create**
5. **Important**: Copy the generated key (only shown once!)

```
Example API Key: timem_sk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### Step 3: Install SDK

```bash
pip install timem-sdk
```

### Step 4: Configure Environment Variables

Create a `.env` file:

```bash
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

### Step 5: Test Connection

```python
from timem import TiMemClient

client = TiMemClient(
    api_key=os.environ.get("TIMEM_API_KEY")
)

# Test adding memory
memory = client.add_memory(
    user_id="test_user",
    content="This is a test memory"
)

print(f"Success! Memory ID: {memory.id}")
print(f"Memory content: {memory.content}")
```

**Expected Output**:

```
Success! Memory ID: mem_abc123xyz
Memory content: This is a test memory
```

## Choose the Right Plan

### Free Plan

**For**: Development testing, small projects

| Feature | Quota |
|---------|-------|
| **API Calls** | 10,000 times/month |
| **Users** | 1,000 |
| **Memory Storage** | 10,000 records |
| **Data Retention** | 7 days |
| **Support** | Community forum |

**Get Started**: Register for free to start

### Starter Plan ($49/month)

**For**: Startups, small applications

| Feature | Quota |
|---------|-------|
| **API Calls** | 100,000 times/month |
| **Users** | 10,000 |
| **Memory Storage** | 100,000 records |
| **Data Retention** | 30 days |
| **Support** | Email support (48h response) |

**Includes**:
- ✅ All Free plan features
- ✅ Basic analytics reports
- ✅ 99% SLA

### Professional Plan ($199/month)

**For**: Growing companies

| Feature | Quota |
|---------|-------|
| **API Calls** | 1,000,000 times/month |
| **Users** | 100,000 |
| **Memory Storage** | 1,000,000 records |
| **Data Retention** | 90 days |
| **Support** | Priority email support (24h response) |

**Includes**:
- ✅ All Starter plan features
- ✅ Advanced analytics dashboard
- ✅ Custom model configuration
- ✅ Webhook support
- ✅ 99.9% SLA

### Enterprise Plan (Custom)

**For**: Large enterprises

| Feature | Quota |
|---------|-------|
| **API Calls** | Unlimited |
| **Users** | Unlimited |
| **Memory Storage** | Unlimited |
| **Data Retention** | Permanent |
| **Support** | Dedicated support manager |

**Includes**:
- ✅ All Professional plan features
- ✅ Private deployment options
- ✅ Dedicated support manager
- ✅ Custom SLA
- ✅ Compliance certifications (SOC2, GDPR)
- ✅ Technical consulting

### Plan Comparison

| Feature | Free | Starter | Professional | Enterprise |
|---------|------|---------|--------------|------------|
| API Calls | 10K/month | 100K/month | 1M/month | Unlimited |
| Users | 1K | 10K | 100K | Unlimited |
| Data Retention | 7 days | 30 days | 90 days | Permanent |
| SLA | None | 99% | 99.9% | Custom |
| Support | Community | Email | Priority | Dedicated |
| Analytics | Basic | Basic | Advanced | Complete |
| Webhook | ❌ | ❌ | ✅ | ✅ |
| Private Deployment | ❌ | ❌ | ❌ | ✅ |

## Cloud Service vs Self-Hosted

| Feature | Cloud Service | Self-Hosted |
|---------|---------------|-------------|
| **Deployment Complexity** | No deployment | Need to configure servers, databases |
| **Maintenance Cost** | No maintenance | Need technical team for maintenance |
| **Scaling** | Auto scaling | Manual scaling |
| **Data Control** | Cloud storage | Full control |
| **Cost** | Pay-as-you-go | Fixed cost |
| **Customization** | Limited customization | Full customization |
| **Time to Market** | Immediate use | Configuration time needed |
| **Security** | Professional team | Your responsibility |

### When to Choose Cloud Service?

✅ **Choose Cloud Service** if:
- Want quick integration
- Don't want to manage infrastructure
- Need auto scaling
- Small team size
- Need professional support

### When to Choose Self-Hosted?

✅ **Choose Self-Hosted** if:
- Data must be stored locally
- Need deep customization
- Have professional DevOps team
- Cost sensitive (at scale)
- Special compliance requirements

## Migrating from Self-Hosted to Cloud Service

### Step 1: Export Data

Export data from self-hosted instance:

```python
# Export script
import json
from timem import TiMemClient

local_client = TiMemClient(
    base_url="http://localhost:8000",
    api_key="local-key"
)

# Get all users
users = local_client.list_users()

# Export data
export_data = {
    "users": [],
    "memories": []
}

for user in users:
    export_data["users"].append({
        "id": user.id,
        "metadata": user.metadata
    })

    # Get all memories for user
    memories = local_client.get_user_memories(user_id=user.id)
    export_data["memories"].extend([
        {
            "user_id": m.user_id,
            "content": m.content,
            "level": m.level,
            "metadata": m.metadata
        }
        for m in memories
    ])

# Save to file
with open("backup.json", "w") as f:
    json.dump(export_data, f)
```

### Step 2: Import to Cloud Service

```python
from timem import TiMemClient
import json

# Connect to cloud service
cloud_client = TiMemClient(
    api_key="timem_sk_xxxxx"
)

# Load backup data
with open("backup.json") as f:
    data = json.load(f)

# Import users
for user_data in data["users"]:
    try:
        cloud_client.create_user(
            user_id=user_data["id"],
            metadata=user_data["metadata"]
        )
    except Exception as e:
        print(f"User {user_data['id']} may already exist: {e}")

# Import memories
for memory_data in data["memories"]:
    try:
        cloud_client.add_memory(
            user_id=memory_data["user_id"],
            content=memory_data["content"],
            level=memory_data.get("level"),
            metadata=memory_data.get("metadata")
        )
    except Exception as e:
        print(f"Memory import failed: {e}")

print("Data import completed!")
```

### Step 3: Update Application Configuration

```python
# Update API address
client = TiMemClient(
    api_key=os.environ.get("TIMEM_API_KEY"),
    base_url="https://api.timem.cloud/v1"  # Cloud service address
)
```

## Monitoring and Analytics

### Access Dashboard

Log in to [Cloud Platform](https://cloud.timem.cloud) to view:

- **Usage Statistics**: API call count, user count
- **Performance Metrics**: Latency, success rate
- **Error Logs**: Failed requests, error types
- **Cost Analysis**: Current costs, trend predictions

### Set Up Alerts

```python
# Configure alert rules in cloud platform
alerts = [
    {
        "name": "API Call Anomaly",
        "condition": "error_rate > 5%",
        "action": "email"
    },
    {
        "name": "Quota Warning",
        "condition": "usage > 80%",
        "action": "webhook"
    }
]
```

## Technical Support

### Free Users

- **Documentation**: [https://docs.timem.cloud](https://docs.timem.cloud)
- **Community Forum**: [https://community.timem.cloud](https://community.timem.cloud)
- **GitHub Issues**: [Report Issue](https://github.com/your-org/timem/issues)

### Paid Users

- **Email Support**: support@timem.cloud
- **Response Time**:
  - Starter: 48 hours
  - Professional: 24 hours
  - Enterprise: Dedicated support

### Enterprise Support

- **Dedicated Support Manager**
- **Technical Consulting Services**
- **Custom Training**
- **Priority Feature Requests**

## FAQ

### How is billing calculated?

- Monthly subscription, billed by plan
- Overages billed based on excess usage
- Enterprise billed by custom contract

### Is data secure?

- All data transmission uses HTTPS encryption
- Data storage uses AES-256 encryption
- Regular security audits
- SOC 2 Type II certified (Enterprise)

### Can I cancel anytime?

- Yes, cancel subscription anytime
- Service stops at end of current billing period after cancellation
- Data export available for 30 days

### How to upgrade/downgrade plan?

1. Log in to cloud platform
2. Navigate to **Billing** → **Plan**
3. Select new plan
4. Confirm changes

Upgrades take effect immediately, downgrades take effect next billing cycle.

## Next Steps

- [Python SDK Quick Start](../sdk/python/quickstart.md)
- [API Reference](../api-reference/overview.md)
- [Pricing Details](pricing.md)
- [Cloud Service Features](features/)

## Related Links

- **Cloud Platform**: https://cloud.timem.cloud
- **Management Console**: https://dashboard.timem.cloud
- **Status Page**: https://status.timem.cloud
- **Pricing**: https://cloud.timem.cloud/pricing
