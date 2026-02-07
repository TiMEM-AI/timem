# TiMem 文档中心

欢迎来到 TiMem 文档中心！这里包含了使用 TiMem 所需的完整文档。

## 📚 快速导航

### 快速开始
- **[5分钟快速上手](sdk/python/quickstart.md)** - Python SDK 快速入门
- **[云服务快速开始](../cloud-service/README.md)** - TiMem 云服务使用指南
- **[本地部署指南](../DEPLOYMENT.md)** - 在自己的服务器上部署 TiMem

### 核心概念
- **[TiMem 架构概述](../README.md#-how-it-works)** - 了解 TiMem 的核心设计
- **[五级记忆层次](../timem/memory/README.md)** - L1-L5 记忆结构详解
- **[工作流引擎](../timem/workflows/README.md)** - LangGraph 工作流实现

### API 与 SDK
- **[API 概述](api-reference/overview.md)** - REST API 总览和快速参考
- **[认证指南](api-reference/authentication.md)** - API Key 管理和安全实践
- **[Python SDK](sdk/python/quickstart.md)** - Python SDK 使用指南
- **[开发者指南](developer-guide/README.md)** - 完整开发指南

### 云服务
- **[云服务概述](../cloud-service/README.md)** - TiMem 云服务介绍
- **[快速开始](../cloud-service/README.md#-quick-start)** - 5分钟上手云服务
- **[API 参考](../cloud-service/api/reference.md)** - REST API 参考
- **[认证指南](api-reference/authentication.md)** - API 认证说明

### 实验与评估
- **[实验指南](../experiments/README.md)** - 复现论文实验结果
- **[数据集准备](../experiments/dataset_utils/README.md)** - 数据集处理说明

### 故障排查
- **[故障排查指南](troubleshooting.md)** - 常见问题和解决方案

## 🎯 选择你的使用方式

### 自托管（开源版）

如果你希望在自己的服务器上完全控制 TiMem：

1. 阅读[本地部署指南](../DEPLOYMENT.md)
2. 查看[示例代码](examples/README.md)
3. 参考主 [README](../README.md)

**适合场景**:
- 需要数据完全在本地
- 需要自定义和扩展
- 研究和实验目的

### 云服务（线上版）

如果你希望使用 TiMem 云服务，无需部署：

1. 阅读[云服务快速开始](../cloud-service/README.md#-quick-start)
2. 在云平台注册并获取 API Key
3. 使用 Python SDK 或 REST API

**适合场景**:
- 快速集成到现有应用
- 无需管理基础设施
- 需要自动扩容和高可用

## 📖 文档版本

| 文档 | 版本 | 状态 |
|------|------|------|
| 开源版本 | v1.0.0 | ✅ 稳定 |
| 云服务 | v1.0.0+ | 🔄 持续更新 |

## 🆘 获取帮助

### 文档反馈

如果发现文档问题或有改进建议，请：
- 提交 [GitHub Issue](https://github.com/your-org/timem/issues)
- 发起 [Pull Request](https://github.com/your-org/timem/pulls)

### 技术支持

- **贡献指南**: [CONTRIBUTING.md](https://github.com/TiMEM-AI/timem/blob/main/CONTRIBUTING.md)
- **Bug 报告**: [GitHub Issues](https://github.com/TiMEM-AI/timem/issues)
- **邮件支持**: support@timem.ai（仅云服务付费用户）

## 📚 学习路径

### 初学者

1. 阅读[主 README](../README.md)了解 TiMem 概述
2. 运行[简单示例](examples/README.md)体验核心功能
3. 学习[五级记忆层次](../timem/memory/README.md)理解架构
4. 查看[使用案例](examples/README.md)学习使用方式

### 开发者

1. 阅读[部署指南](../DEPLOYMENT.md)设置环境
2. 学习[API 参考](api-reference/overview.md)了解接口
3. 使用[开发者指南](developer-guide/README.md)快速入门
4. 参考[工作流文档](../timem/workflows/README.md)进行定制

### 研究者

1. 阅读[论文实验](../experiments/README.md)复现结果
2. 研究[记忆层次实现](../timem/memory/README.md)算法细节
3. 分析[回填机制](../BACKFILL_GUIDE.md)设计
4. 探索[配置选项](../config/README.md)调整参数

## 🔗 相关链接

- **GitHub 仓库**: https://github.com/your-org/timem
- **PyPI 包**: https://pypi.org/project/timem/
- **云平台**: https://cloud.timem.ai
- **许可证**: [Apache 2.0](../LICENSE)

---

**最后更新**: 2025-01-18
