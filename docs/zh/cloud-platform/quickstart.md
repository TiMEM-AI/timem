# TiMem 云服务快速开始

TiMem 云服务提供无需部署、即开即用的记忆管理解决方案。本文档帮助您快速开始使用 TiMem 云服务。

## 概述

TiMem 云服务提供：

- **零部署**: 无需配置服务器或数据库
- **自动扩容**: 根据流量自动扩展
- **高可用性**: 99.9% SLA 保证
- **专业支持**: 优先技术支持
- **实时监控**: 完整的使用分析和监控

## 5 分钟快速开始

### 步骤 1: 注册账号

访问 [TiMem 云平台](https://cloud.timem.ai) 并注册账号。

**注册方式**:
- 邮箱注册
- GitHub 登录
- Google 登录

### 步骤 2: 获取 API Key

1. 登录后进入 **Settings** → **API Keys**
2. 点击 **Create New Key**
3. 设置密钥信息：
   - **Key Name**: 密钥名称（如 "Production"）
   - **Key Type**: 密钥类型（Production/Test）
   - **Permissions**: 权限范围
4. 点击 **Create**
5. **重要**: 复制生成的密钥（只显示一次！）

```
示例 API Key: timem_sk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 步骤 3: 安装 SDK

```bash
pip install timem-sdk
```

### 步骤 4: 配置环境变量

创建 `.env` 文件：

```bash
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

### 步骤 5: 测试连接

```python
from timem import TiMemClient

client = TiMemClient(
    api_key=os.environ.get("TIMEM_API_KEY")
)

# 测试添加记忆
memory = client.add_memory(
    user_id="test_user",
    content="这是一条测试记忆"
)

print(f"成功！记忆ID: {memory.id}")
print(f"记忆内容: {memory.content}")
```

**预期输出**:

```
成功！记忆ID: mem_abc123xyz
记忆内容: 这是一条测试记忆
```

## 选择适合的计划

### 免费计划

**适合**: 开发测试、小型项目

| 特性 | 配额 |
|------|------|
| **API 调用** | 10,000 次/月 |
| **用户数量** | 1,000 |
| **记忆存储** | 10,000 条 |
| **数据保留** | 7 天 |
| **支持** | 社区论坛 |

**开始使用**: 免费注册即可开始

### Starter 计划 ($49/月)

**适合**: 初创公司、小型应用

| 特性 | 配额 |
|------|------|
| **API 调用** | 100,000 次/月 |
| **用户数量** | 10,000 |
| **记忆存储** | 100,000 条 |
| **数据保留** | 30 天 |
| **支持** | 邮件支持（48h响应） |

**包含功能**:
- ✅ 所有免费计划功能
- ✅ 基础分析报告
- ✅ 99% SLA

### Professional 计划 ($199/月)

**适合**: 成长型公司

| 特性 | 配额 |
|------|------|
| **API 调用** | 1,000,000 次/月 |
| **用户数量** | 100,000 |
| **记忆存储** | 1,000,000 条 |
| **数据保留** | 90 天 |
| **支持** | 优先邮件支持（24h响应） |

**包含功能**:
- ✅ 所有 Starter 计划功能
- ✅ 高级分析仪表板
- ✅ 自定义模型配置
- ✅ Webhook 支持
- ✅ 99.9% SLA

### Enterprise 计划（定制）

**适合**: 大型企业

| 特性 | 配额 |
|------|------|
| **API 调用** | 无限制 |
| **用户数量** | 无限制 |
| **记忆存储** | 无限制 |
| **数据保留** | 永久 |
| **支持** | 专属支持经理 |

**包含功能**:
- ✅ 所有 Professional 计划功能
- ✅ 私有部署选项
- ✅ 专属支持经理
- ✅ 定制 SLA
- ✅ 合规认证（SOC2, GDPR）
- ✅ 技术咨询

### 计划对比

| 功能 | 免费版 | Starter | Professional | Enterprise |
|------|--------|---------|--------------|------------|
| API 调用 | 10K/月 | 100K/月 | 1M/月 | 无限 |
| 用户数 | 1K | 10K | 100K | 无限 |
| 数据保留 | 7天 | 30天 | 90天 | 永久 |
| SLA | 无 | 99% | 99.9% | 定制 |
| 支持 | 社区 | 邮件 | 优先 | 专属 |
| 分析 | 基础 | 基础 | 高级 | 完整 |
| Webhook | ❌ | ❌ | ✅ | ✅ |
| 私有部署 | ❌ | ❌ | ❌ | ✅ |

## 云服务 vs 自托管

| 特性 | 云服务 | 自托管 |
|------|--------|--------|
| **部署复杂度** | 无需部署 | 需要配置服务器、数据库 |
| **维护成本** | 无需维护 | 需要技术团队维护 |
| **扩容能力** | 自动扩容 | 手动扩容 |
| **数据控制** | 云端存储 | 完全控制 |
| **成本** | 按量付费 | 固定成本 |
| **定制化** | 有限定制 | 完全定制 |
| **上线速度** | 立即使用 | 需要配置时间 |
| **安全性** | 专业团队 | 自己负责 |

### 何时选择云服务？

✅ **选择云服务**，如果：
- 希望快速集成
- 不想管理基础设施
- 需要自动扩容
- 团队规模较小
- 需要专业支持

### 何时选择自托管？

✅ **选择自托管**，如果：
- 数据必须本地存储
- 需要深度定制
- 有专业运维团队
- 成本敏感（大规模）
- 合规要求特殊

## 从自托管迁移到云服务

### 步骤 1: 导出数据

从自托管实例导出数据：

```python
# 导出脚本
import json
from timem import TiMemClient

local_client = TiMemClient(
    base_url="http://localhost:8000",
    api_key="local-key"
)

# 获取所有用户
users = local_client.list_users()

# 导出数据
export_data = {
    "users": [],
    "memories": []
}

for user in users:
    export_data["users"].append({
        "id": user.id,
        "metadata": user.metadata
    })

    # 获取用户的所有记忆
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

# 保存到文件
with open("backup.json", "w") as f:
    json.dump(export_data, f)
```

### 步骤 2: 导入到云服务

```python
from timem import TiMemClient
import json

# 连接云服务
cloud_client = TiMemClient(
    api_key="timem_sk_xxxxx"
)

# 加载备份数据
with open("backup.json") as f:
    data = json.load(f)

# 导入用户
for user_data in data["users"]:
    try:
        cloud_client.create_user(
            user_id=user_data["id"],
            metadata=user_data["metadata"]
        )
    except Exception as e:
        print(f"用户 {user_data['id']} 可能已存在: {e}")

# 导入记忆
for memory_data in data["memories"]:
    try:
        cloud_client.add_memory(
            user_id=memory_data["user_id"],
            content=memory_data["content"],
            level=memory_data.get("level"),
            metadata=memory_data.get("metadata")
        )
    except Exception as e:
        print(f"记忆导入失败: {e}")

print("数据导入完成！")
```

### 步骤 3: 更新应用配置

```python
# 更新 API 地址
client = TiMemClient(
    api_key=os.environ.get("TIMEM_API_KEY"),
    base_url="https://api.timem.ai/v1"  # 云服务地址
)
```

## 监控和分析

### 访问仪表板

登录 [云平台](https://cloud.timem.ai) 查看：

- **使用量统计**: API 调用次数、用户数量
- **性能指标**: 延迟、成功率
- **错误日志**: 失败请求、错误类型
- **成本分析**: 当前费用、趋势预测

### 设置告警

```python
# 在云平台配置告警规则
alerts = [
    {
        "name": "API 调用异常",
        "condition": "error_rate > 5%",
        "action": "email"
    },
    {
        "name": "配额预警",
        "condition": "usage > 80%",
        "action": "webhook"
    }
]
```

## 技术支持

### 免费用户

- **文档**: [https://docs.timem.ai](https://docs.timem.ai)
- **社区论坛**: [https://community.timem.ai](https://community.timem.ai)
- **GitHub Issues**: [报告问题](https://github.com/your-org/timem/issues)

### 付费用户

- **邮件支持**: support@timem.ai
- **响应时间**:
  - Starter: 48 小时
  - Professional: 24 小时
  - Enterprise: 专属支持

### Enterprise 支持

- **专属支持经理**
- **技术咨询服务**
- **定制培训**
- **优先处理功能请求**

## 常见问题

### 如何计费？

- 按月订阅，按计划计费
- 超出配额后按超额部分计费
- Enterprise 按定制合同计费

### 数据安全吗？

- 所有数据传输使用 HTTPS 加密
- 数据存储使用 AES-256 加密
- 定期安全审计
- SOC 2 Type II 认证（Enterprise）

### 可以随时取消吗？

- 可以，随时取消订阅
- 取消后服务在当前计费周期结束后停止
- 数据导出功能可用 30 天

### 如何升级/降级计划？

1. 登录云平台
2. 进入 **Billing** → **Plan**
3. 选择新计划
4. 确认变更

升级立即生效，降级在下一计费周期生效。

## 下一步

- [Python SDK 快速开始](../sdk/python/quickstart.md)
- [API 参考](../api-reference/overview.md)
- [定价详情](pricing.md)
- [云服务功能](features/)

## 相关链接

- **云平台**: https://cloud.timem.ai
- **管理控制台**: https://dashboard.timem.ai
- **状态页面**: https://status.timem.ai
- **定价**: https://cloud.timem.ai/pricing
