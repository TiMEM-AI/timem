# TiMem Documentation Center

Welcome to the TiMem documentation center! Here you'll find complete documentation for using TiMem.

## 📚 Quick Navigation

### Quick Start
- **[5-Minute Quick Start](sdk/python/quickstart.md)** - Python SDK quick start
- **[Cloud Service Quick Start](../cloud-service/README.md)** - TiMem cloud service guide
- **[Self-Hosted Deployment Guide](../DEPLOYMENT.md)** - Deploy TiMem on your own server

### Core Concepts
- **[TiMem Architecture Overview](../README.md#-how-it-works)** - Understand TiMem's core design
- **[5-Level Memory Hierarchy](../timem/memory/README.md)** - L1-L5 memory structure explained
- **[Workflow Engine](../timem/workflows/README.md)** - LangGraph workflow implementation

### API & SDK
- **[API Overview](api-reference/overview.md)** - REST API overview and quick reference
- **[Authentication Guide](api-reference/authentication.md)** - API key management and security practices
- **[Python SDK](sdk/python/quickstart.md)** - Python SDK usage guide
- **[Developer Guide](developer-guide/README.md)** - Complete development guide

### Cloud Service
- **[Cloud Service Overview](../cloud-service/README.md)** - TiMem cloud service introduction
- **[Quick Start](../cloud-service/README.md#-quick-start)** - Get started with cloud service in 5 minutes
- **[API Reference](../cloud-service/api/reference.md)** - REST API reference
- **[Authentication Guide](api-reference/authentication.md)** - API authentication instructions

### Experiments & Evaluation
- **[Experiment Guide](../experiments/README.md)** - Reproduce paper experimental results
- **[Dataset Preparation](../experiments/dataset_utils/README.md)** - Dataset processing instructions

### Troubleshooting
- **[Troubleshooting Guide](troubleshooting.md)** - Common issues and solutions

## 🎯 Choose Your Usage Method

### Self-Hosted (Open Source)

If you want full control of TiMem on your own server:

1. Read the [Deployment Guide](../DEPLOYMENT.md)
2. Check [Example Code](../examples/README.md)
3. Refer to the main [README](../README.md)

**Best for**:
- Complete data locality
- Customization and extensions
- Research and experimentation

### Cloud Service (Online)

If you want to use TiMem cloud service without deployment:

1. Read [Cloud Service Quick Start](../cloud-service/README.md#-quick-start)
2. Register on the cloud platform and get API Key
3. Use Python SDK or REST API

**Best for**:
- Quick integration into existing applications
- No infrastructure management
- Auto-scaling and high availability

## 📖 Documentation Versions

| Document | Version | Status |
|----------|---------|--------|
| Open Source | v1.0.0 | ✅ Stable |
| Cloud Service | v1.0.0+ | 🔄 Continuously Updated |

## 🆘 Get Help

### Documentation Feedback

If you find documentation issues or have improvement suggestions:
- Submit a [GitHub Issue](https://github.com/TiMEM-AI/timem/issues)
- Open a [Pull Request](https://github.com/TiMEM-AI/timem/pulls)

### Technical Support

- **Contributing Guide**: [CONTRIBUTING.md](https://github.com/TiMEM-AI/timem/blob/main/CONTRIBUTING.md)
- **Bug Reports**: [GitHub Issues](https://github.com/TiMEM-AI/timem/issues)
- **Email Support**: support@timem.ai (cloud service paid users only)

## 📚 Learning Paths

### Beginners

1. Read the main [README](../README.md) to understand TiMem overview
2. Run [simple examples](../cloud-service/examples/) to experience core features
3. Learn [5-level memory hierarchy](../timem/memory/README.md) to understand architecture
4. Check [use cases](../cloud-service/examples/) to learn usage patterns

### Developers

1. Read the [Deployment Guide](../DEPLOYMENT.md) to set up environment
2. Learn [API Reference](api-reference/overview.md) to understand interfaces
3. Use [Developer Guide](developer-guide/README.md) to get started quickly
4. Reference [workflow documentation](../timem/workflows/README.md) for customization

### Researchers

1. Read [paper experiments](../experiments/README.md) to reproduce results
2. Study [memory hierarchy implementation](../timem/memory/README.md) for algorithm details
3. Analyze [backfill mechanism](../BACKFILL_GUIDE.md) design
4. Explore [configuration options](../config/README.md) to tune parameters

## 🔗 Related Links

- **GitHub Repository**: https://github.com/TiMEM-AI/timem
- **PyPI Package**: https://pypi.org/project/timem-ai/
- **Cloud Platform**: https://timem.cloud
- **License**: [SSPL](../LICENSE)

---

**Last Updated**: 2026-02-08
