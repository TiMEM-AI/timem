# API 认证指南

本文档详细介绍 TiMem API 的认证机制、API Key 管理和安全最佳实践。

## 认证概述

TiMem API 使用 **Bearer Token** 认证方式。每个 API 请求都需要在 HTTP Header 中包含有效的 API Key。

```http
Authorization: Bearer YOUR_API_KEY
```

## 获取 API Key

### 注册账号

1. 访问 [TiMem 云平台](https://cloud.timem.ai)
2. 点击 **Sign Up** 注册账号
3. 验证邮箱地址

### 创建 API Key

1. 登录云平台
2. 进入 **Settings** → **API Keys**
3. 点击 **Create New Key**
4. 填写以下信息：
   - **Key Name**: 密钥名称（如 "Production", "Development"）
   - **Key Type**: 密钥类型（Production/Test/Limited）
   - **Permissions**: 权限范围（Read/Write/Admin）
5. 点击 **Create**
6. **重要**: 复制密钥，它只显示一次！

### API Key 格式

有效的 API Key 格式：

```
timem_sk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

- 前缀: `timem_sk_`
- 长度: 64 字符
- 字符集: 小写字母和数字

## 使用 API Key

### Python SDK

```python
from timem import TiMemClient
import os

# 方式1: 直接传入
client = TiMemClient(api_key="timem_sk_xxxxx")

# 方式2: 环境变量（推荐）
client = TiMemClient(api_key=os.environ.get("TIMEM_API_KEY"))
```

### 环境变量配置

创建 `.env` 文件：

```bash
# TiMem API Configuration
TIMEM_API_KEY=timem_sk_xxxxx
TIMEM_API_URL=https://api.timem.ai/v1
```

加载环境变量：

```python
from dotenv import load_dotenv
import os

load_dotenv()

api_key = os.environ.get("TIMEM_API_KEY")
```

### cURL

```bash
# 设置环境变量
export TIMEM_API_KEY="timem_sk_xxxxx"

# 使用环境变量
curl -H "Authorization: Bearer $TIMEM_API_KEY" \
  https://api.timem.ai/v1/memories
```

### JavaScript/TypeScript

```javascript
import { TiMemClient } from 'timem-sdk';

// 方式1: 直接传入
const client = new TiMemClient({
  apiKey: 'timem_sk_xxxxx'
});

// 方式2: 环境变量
const client = new TiMemClient({
  apiKey: process.env.TIMEM_API_KEY
});
```

## API Key 类型与权限

### Production Key

**用途**: 生产环境

**权限**:
- ✅ 读取记忆
- ✅ 创建记忆
- ✅ 更新记忆
- ✅ 删除记忆
- ✅ 管理用户
- ✅ 管理会话

**建议**:
- 用于生产环境
- 定期轮换
- 限制 IP 地址

### Test Key

**用途**: 开发和测试

**权限**:
- ✅ 读取记忆
- ✅ 创建记忆
- ❌ 删除记忆
- ❌ 管理用户

**建议**:
- 用于开发环境
- 不应用于生产
- 可以公开分享（测试用）

### Limited Key

**用途**: 特定功能限制

**可配置权限**:
- 只读访问
- 仅特定端点
- 仅特定用户

**建议**:
- 用于第三方集成
- 用于受限功能
- 严格限制权限

## 安全最佳实践

### ✅ 推荐做法

#### 1. 使用环境变量

```bash
# .env 文件
TIMEM_API_KEY=timem_sk_xxxxx
```

```python
# 代码中读取
import os
api_key = os.environ.get("TIMEM_API_KEY")
```

#### 2. 使用密钥管理服务

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

#### 3. 定期轮换 API Key

```python
import os
from timem import TiMemClient

def rotate_api_key():
    """轮换 API Key"""
    old_key = os.environ.get("TIMEM_API_KEY_OLD")
    new_key = os.environ.get("TIMEM_API_KEY_NEW")

    # 测试新密钥
    test_client = TiMemClient(api_key=new_key)
    try:
        test_client.list_memories(limit=1)
        print("新密钥工作正常")
    except Exception as e:
        print(f"新密钥测试失败: {e}")
        return False

    # 更新应用配置
    # ... 更新配置的逻辑 ...
    print("密钥轮换成功")
    return True
```

**轮换策略**:
- **开发密钥**: 每周轮换
- **测试密钥**: 每月轮换
- **生产密钥**: 每季度轮换
- **发现泄露时**: 立即轮换

#### 4. 限制 API Key 权限

只授予必要的权限：

```python
# 只读客户端
read_only_client = TiMemClient(
    api_key="timem_read_only_xxxxx",
    permissions=["read"]
)

# 写入客户端
write_client = TiMemClient(
    api_key="timem_write_xxxxx",
    permissions=["read", "write"]
)
```

#### 5. 使用 IP 白名单

在云平台配置 IP 白名单：

```
允许的 IP 地址:
- 203.0.113.1/32 (生产服务器)
- 198.51.100.0/24 (办公室网络)
```

### ❌ 避免做法

#### 1. 不要硬编码 API Key

```python
# ❌ 错误示例
api_key = "timem_sk_1234567890"  # 不要这样做！

# ✅ 正确做法
api_key = os.environ.get("TIMEM_API_KEY")
```

#### 2. 不要提交 API Key 到版本控制

**在 `.gitignore` 中添加**:

```gitignore
# 环境变量文件
.env
.env.local
.env.*.local

# 密钥文件
secrets.yaml
secrets.json
*.key
```

**检测已提交的密钥**:

```bash
# 搜索可能的密钥
git log --all --full-history --source -- "**/.env"
git log --all --full-history --source -- "**/secrets.*"
```

#### 3. 不要在前端代码中使用生产密钥

```javascript
// ❌ 错误：前端暴露密钥
const client = new TiMemClient({
  apiKey: 'timem_sk_production_xxxxx'  // 任何人都能看到！
});

// ✅ 正确：通过后端代理
// 前端调用后端 API，后端使用密钥调用 TiMem
```

#### 4. 不要在日志中记录密钥

```python
# ❌ 错误
print(f"Using API key: {api_key}")  # 密钥会出现在日志中
logger.info(f"API key: {api_key}")

# ✅ 正确
print(f"Using API key: {api_key[:10]}...")  # 只显示前几个字符
logger.info("API key configured")
```

## API Key 轮换

### 轮换步骤

1. **创建新密钥**:
   - 在云平台创建新的 API Key
   - 设置相同的权限和限制

2. **测试新密钥**:
   ```python
   new_client = TiMemClient(api_key="new_key")
   new_client.list_memories(limit=1)  # 测试读取权限
   ```

3. **更新应用配置**:
   - 更新环境变量
   - 重新部署应用

4. **验证**:
   - 确认应用使用新密钥正常工作

5. **删除旧密钥**:
   - 等待24-48小时确认无问题
   - 在云平台删除旧密钥

### 零停机轮换

```python
import os
from timem import TiMemClient

class ApiKeyRotator:
    def __init__(self):
        self.primary_key = os.environ.get("TIMEM_API_KEY")
        self.secondary_key = os.environ.get("TIMEM_API_KEY_BACKUP")

    def get_client(self):
        """获取可用的客户端"""
        # 尝试主密钥
        try:
            client = TiMemClient(api_key=self.primary_key)
            client.list_memories(limit=1)
            return client
        except:
            pass

        # 尝试备用密钥
        if self.secondary_key:
            return TiMemClient(api_key=self.secondary_key)

        raise Exception("没有可用的 API Key")
```

## 故障排查

### 401 Unauthorized

**原因**:
- API Key 无效
- API Key 已过期
- API Key 被撤销

**解决方案**:

1. 验证密钥格式:
   ```bash
   echo $TIMEM_API_KEY | grep -E "^timem_sk_[a-z0-9]{64}$"
   ```

2. 检查密钥是否过期:
   - 登录云平台查看密钥状态

3. 重新生成密钥:
   - 删除旧密钥
   - 创建新密钥
   - 更新应用配置

### 403 Forbidden

**原因**:
- API Key 权限不足
- IP 地址不在白名单
- 超过配额限制

**解决方案**:

1. 检查密钥权限:
   - 确认密钥有所需权限
   - 升级密钥类型或创建新密钥

2. 检查 IP 白名单:
   - 确认当前 IP 在白名单中
   - 添加当前 IP 到白名单

3. 检查配额:
   - 查看使用量统计
   - 升级计划

### 429 Rate Limit

**原因**: 超过速率限制

**解决方案**:

1. 实现指数退避:
   ```python
   import time

   def call_with_retry(client, max_retries=3):
       for attempt in range(max_retries):
           try:
               return client.add_memory(...)
           except RateLimitError:
               if attempt < max_retries - 1:
                   wait_time = 2 ** attempt  # 1, 2, 4 秒
                   time.sleep(wait_time)
               else:
                   raise
   ```

2. 使用批量操作减少请求数

3. 升级到更高限额的计划

## 配置示例

### Python 项目

```python
# config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    TIMEM_API_KEY = os.environ.get("TIMEM_API_KEY")
    TIMEM_API_URL = os.environ.get("TIMEM_API_URL", "https://api.timem.ai/v1")
    TIMEM_TIMEOUT = int(os.environ.get("TIMEM_TIMEOUT", "30"))

# .env
TIMEM_API_KEY=timem_sk_xxxxx
TIMEM_API_URL=https://api.timem.ai/v1
TIMEM_TIMEOUT=30
```

### Django 项目

```python
# settings.py
import os
from dotenv import load_dotenv

load_dotenv()

TIMEM_API_KEY = os.environ.get("TIMEM_API_KEY")
TIMEM_API_URL = os.environ.get("TIMEM_API_URL", "https://api.timem.ai/v1")
```

### Node.js 项目

```javascript
// .env
TIMEM_API_KEY=timem_sk_xxxxx
TIMEM_API_URL=https://api.timem.ai/v1

// config.js
require('dotenv').config();

module.exports = {
  apiKey: process.env.TIMEM_API_KEY,
  apiUrl: process.env.TIMEM_API_URL || 'https://api.timem.ai/v1'
};
```

## 审计与监控

### 密钥使用监控

在云平台查看：
- API 调用次数
- 最后使用时间
- 使用的 IP 地址
- 使用的端点

### 异常检测

设置告警：
- 未知 IP 地址使用密钥
- 使用量突然增加
- 异常的 API 调用模式
- 失败的认证尝试

### 审计日志

定期检查：
```bash
# 查看最近7天的使用记录
curl -H "Authorization: Bearer $TIMEM_API_KEY" \
  https://api.timem.ai/v1/audit-logs?days=7
```

## 参考资源

- [API 概述](overview.md) - API 总览
- [Python SDK](../sdk/python/quickstart.md) - SDK 使用指南
- [云平台](https://cloud.timem.ai) - 密钥管理
- [故障排查](../troubleshooting.md) - 常见问题
