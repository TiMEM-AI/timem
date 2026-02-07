# TiMem 故障排查指南

本文档帮助您解决使用 TiMem 时遇到的常见问题。

## 目录

- [数据库问题](#数据库问题)
- [API Key 问题](#api-key-问题)
- [导入错误](#导入错误)
- [性能问题](#性能问题)
- [记忆生成问题](#记忆生成问题)
- [数据集配置问题](#数据集配置问题)
- [获取帮助](#获取帮助)

---

## 数据库问题

### 数据库连接错误

**错误信息**: `connection refused` 或 `host not found`

**原因**: Docker 容器未启动或端口配置错误

**解决方案**:

1. 检查 Docker 容器状态:
```bash
docker ps
```

2. 如果没有容器运行，启动数据库:
```bash
cd migration
docker-compose up -d
```

3. 验证端口是否正确:
```bash
docker-compose ps
```

4. 检查 `.env` 文件中的端口配置是否与 `docker-compose.yml` 匹配

### 端口冲突

**错误信息**: `port is already allocated`

**原因**: 端口已被其他服务占用

**解决方案**:

1. 查找占用端口的进程:
```bash
# Windows
netstat -ano | findstr :15432

# Linux/Mac
lsof -i :15432
```

2. 修改 `migration/docker-compose.yml` 中的端口映射

3. 或者在 `.env` 文件中修改对应的端口配置

### 数据库为空

**症状**: 记忆检索返回空结果

**解决方案**:

1. 确认已运行记忆生成脚本:
```bash
cd experiments/datasets/locomo
python 01_memory_generation.py
```

2. 检查数据库中是否有数据:
```bash
docker exec -it timem-postgres-1 psql -U timem_user -d timem_db -c "SELECT COUNT(*) FROM memory_store;"
```

---

## API Key 问题

### 401 Unauthorized

**错误信息**: `401 Unauthorized` 或 `invalid api key`

**原因**: API Key 无效或未配置

**解决方案**:

1. 检查 `.env` 文件是否存在:
```bash
cat .env | grep API_KEY
```

2. 确认 API Key 格式正确（没有多余空格）:
```bash
# 正确格式
OPENAI_API_KEY=sk-xxxxxxxxxxxx

# 错误格式（有前导空格）
 OPENAI_API_KEY=sk-xxxxxxxxxxxx
```

3. 验证 API Key 在提供商平台是否有效:
   - OpenAI: https://platform.openai.com/api-keys
   - Anthropic: https://console.anthropic.com/settings/keys
   - 智谱AI: https://open.bigmodel.cn/usercenter/apikeys
   - 通义千问: https://dashscope.console.aliyun.com/apiKey

### 429 Rate Limit

**错误信息**: `429 Too Many Requests` 或 `rate limit exceeded`

**原因**: API 请求过于频繁

**解决方案**:

1. 添加请求延迟:
```python
import time

# 在 API 调用之间添加延迟
time.sleep(1)
```

2. 减少批量大小:
```yaml
# 在 config/settings.yaml 中
batch_size: 5  # 从更大的值减少到 5
```

3. 升级 API 计划以获得更高的速率限制

### API 配额不足

**症状**: API 调用失败但错误信息不明确

**解决方案**:

1. 检查 API 提供商控制台的配额使用情况

2. 切换到更便宜的模型:
```bash
# 使用 GPT-4o-mini 代替 GPT-4
export OPENAI_MODEL=gpt-4o-mini
```

---

## 导入错误

### ModuleNotFoundError

**错误信息**: `ModuleNotFoundError: No module named 'xxx'`

**原因**: 依赖包未安装

**解决方案**:

1. 安装所有依赖:
```bash
pip install -r requirements.txt
```

2. 如果使用虚拟环境，确保已激活:
```bash
# Windows
.venv\Scripts\activate

# Linux/Mac
source .venv/bin/activate
```

3. 重新安装特定包:
```bash
pip install package-name
```

### AttributeError

**错误信息**: `AttributeError: module 'xxx' has no attribute 'yyy'`

**原因**: 版本不兼容

**解决方案**:

1. 检查依赖版本:
```bash
pip list | grep package-name
```

2. 更新到兼容版本:
```bash
pip install --upgrade package-name
```

3. 参考 `requirements.txt` 中的版本要求

---

## 性能问题

### 记忆生成缓慢

**症状**: 生成记忆需要很长时间

**解决方案**:

1. 使用更快的模型:
```bash
# .env 文件
OPENAI_MODEL=gpt-4o-mini  # 比 gpt-4 快得多
```

2. 减少批处理大小:
```yaml
# config/settings.yaml
batch_size: 5
```

3. 使用调试模式（不写入数据库）:
```python
gen = MemoryGenerator(debug_mode=True)
```

4. 启用缓存:
```yaml
# config/settings.yaml
cache_enabled: true
```

### 内存占用过高

**症状**: 程序运行时内存占用持续增长

**解决方案**:

1. 减少批处理大小

2. 定期清理缓存:
```python
import gc
gc.collect()
```

3. 使用流式处理:
```python
# 逐条处理而不是批量处理
for item in items:
    process(item)
```

---

## 记忆生成问题

### 记忆质量差

**症状**: 生成的记忆不准确或不相关

**解决方案**:

1. 检查提示词配置:
```bash
# 查看 config/prompts/ 中的提示词
ls config/prompts/
```

2. 使用更强大的模型:
```bash
export OPENAI_MODEL=gpt-4
```

3. 调整温度参数:
```yaml
# config/settings.yaml
temperature: 0.3  # 降低温度以获得更确定的结果
```

### 没有生成记忆

**症状**: 运行脚本后没有生成任何记忆

**解决方案**:

1. 检查输入数据格式是否正确

2. 查看日志输出:
```bash
# 运行时启用详细日志
export LOG_LEVEL=DEBUG
python script.py
```

3. 确认对话数据不为空

---

## 数据集配置问题

### 数据集未找到

**错误信息**: `FileNotFoundError` 或 `dataset not found`

**解决方案**:

1. 确认数据集文件位置:
```bash
ls data/
```

2. 运行数据集分割脚本:
```bash
python experiments/dataset_utils/dataset_splitter.py --split-all
```

3. 检查 `TIMEM_DATASET_PROFILE` 配置:
```bash
# .env 文件
TIMEM_DATASET_PROFILE=default  # 或 longmemeval_s
```

### 数据集格式错误

**症状**: 数据集加载失败

**解决方案**:

1. 参考正确的数据格式示例

2. 验证 JSON 格式:
```bash
python -m json.tool data/your_file.json
```

3. 检查必需字段是否存在

---

## 最佳实践

### 1. 开发环境设置

```bash
# 使用虚拟环境
python -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境
cp env.example .env
# 编辑 .env 文件添加你的 API Keys
```

### 2. 调试技巧

```python
# 启用调试模式
import logging
logging.basicConfig(level=logging.DEBUG)

# 使用小数据集测试
gen = MemoryGenerator(debug_mode=True)
```

### 3. 监控资源使用

```bash
# 监控 Docker 容器
docker stats

# 检查数据库大小
docker exec -it timem-postgres-1 psql -U timem_user -d timem_db -c "\l+"
```

---

## 获取帮助

如果以上解决方案无法解决您的问题：

### 文档资源

- [主 README](../README.md) - 项目概述
- [部署指南](../DEPLOYMENT_CN.md) - 详细部署说明
- [配置说明](../config/README.md) - 配置参数详解

### 社区支持

- **GitHub Issues**: [报告问题](https://github.com/your-org/timem/issues)
- **GitHub Discussions**: [提问讨论](https://github.com/your-org/timem/discussions)

### 提交问题时请包含

1. **环境信息**:
   ```bash
   python --version
   pip list | grep timem
   docker --version
   ```

2. **错误信息**: 完整的错误堆栈跟踪

3. **复现步骤**: 如何复现问题的详细说明

4. **配置信息**: `.env` 文件中的关键配置（隐藏敏感信息）

---

## 常见错误速查表

| 错误代码 | 错误信息 | 快速解决方案 |
|---------|---------|-------------|
| 401 | Unauthorized | 检查 API Key 配置 |
| 429 | Rate Limit | 减少请求频率或升级计划 |
| 500 | Internal Server Error | 检查日志文件 |
| FileNotFoundError | File not found | 检查数据路径配置 |
| ModuleNotFoundError | Module not found | 运行 `pip install -r requirements.txt` |
| ConnectionRefused | Connection refused | 启动 Docker 容器 |
| TimeoutError | Request timeout | 增加超时时间或检查网络 |

---

## 更多资源

- [API 参考](api-reference/overview.md)
- [SDK 使用指南](sdk/python/quickstart.md)
- [云服务文档](cloud-platform/quickstart.md)
