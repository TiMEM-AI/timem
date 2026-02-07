<p align="center">
  <a href="https://github.com/TiMEM-AI/timem-ai">
    <img src="assets/timem.jpg" width="800px" alt="TiMem - Temporal-Hierarchical Memory System">
  </a>
</p>

<p align="center">
  <strong>TiMem: Make Your AI Evolve Over Time</strong>
</p>

<p align="center">
  <em>Temporal-Hierarchical Memory Consolidation for Long-Horizon Conversational Agents</em>
</p>

<p align="center">
  Transform <strong>endless</strong> dialogues into <strong>structured, multi-level memories</strong> with a <strong>Temporal Memory Tree (TMT)</strong> — from fine-grained evidence to stable persona.
</p>

<p align="center">
  <a href="#-quick-start"><strong>🚀 Quick Start</strong></a>
  ·
  <a href="#-core-concepts"><strong>🧠 Core Concepts</strong></a>
  ·
  <a href="#-examples"><strong>📖 Examples</strong></a>
  ·
  <a href="#-cloud-service"><strong>☁️ Cloud Service</strong></a>
  ·
  <a href="docs/en/README.md"><strong>📚 Documentation Index</strong></a>
  ·
  <a href="README_CN.md"><strong>🇨🇳 中文文档</strong></a>
  ·
  <a href="#-research"><strong>📄 Research</strong></a>
</p>

<p align="center">
  <a href="https://timem.ai">
    <img src="https://img.shields.io/badge/website-timem.ai-blue" alt="Website">
  </a>
  <a href="https://pypi.org/project/timem-ai">
    <img src="https://img.shields.io/pypi/v/timem-ai?color=%2334D058&label=pypi%20package" alt="PyPI Version">
  </a>
  <a href="https://github.com/TiMEM-AI/timem-ai/blob/main/LICENSE">
    <img src="https://img.shields.io/badge/license-SSPL-red" alt="License: SSPL">
  </a>
  <a href="https://github.com/TiMEM-AI/timem-ai/stargazers">
    <img src="https://img.shields.io/github/stars/TiMEM-AI/timem" alt="Stars">
  </a>
</p>

> **🎉 TiMem v1.0 is now available!** This release includes cloud service support, simplified SDK usage, and research-backed memory consolidation.

## 🔥 TiMem Highlights

- **5-Level Temporal Hierarchy**: Explicit temporal ordering from fragments to stable persona
- **No Fine-tuning Required**: Instruction-guided memory consolidation
- **Complexity-Aware Recall**: Adaptive retrieval based on query complexity
- **State-of-the-Art Performance**: Leading results on LoCoMo and  LongMemmEval-S benchmark

# Introduction

[TiMem](https://github.com/TiMEM-AI/timem-ai) enhances AI assistants and agents with a **Temporal Memory Tree (TMT)** — an intelligent memory system that organizes memories in a 5-level hierarchical structure with explicit temporal ordering.

### Key Features & Use Cases

**Core Capabilities:**
- **Temporal Memory Tree (TMT)**: 5-level hierarchy with explicit temporal ordering
- **Semantic-guided Consolidation**: No fine-tuning required, instruction-guided
- **Complexity-aware Recall**: Adapts retrieval scope to query complexity
- **Multi-LLM Support**: OpenAI, Claude, ZhipuAI, Qwen, local models

**Applications:**
- **AI Assistants**: Consistent, context-rich conversations over long sessions
- **Customer Support**: Recall user history across sessions for personalized help
- **Education**: Track learning progress and adapt to student needs
- **Productivity**: Build persistent user profiles over time

## 🚀 Quick Start

Choose between our hosted cloud service or self-hosted deployment:

### Cloud Service (Recommended)

Get started in minutes without managing infrastructure:

```bash
# 1. Install SDK
pip install timem-ai

# 2. Configure credentials

export TIMEM_BASE_URL=https://api.timem.cloud
```

```python
import asyncio
from timem import AsyncMemory

async def main():
    # Initialize client
    memory = AsyncMemory(
        api_key="YOUR_API_KEY",
        base_url="https://api.timem.cloud"
    )

    # Add conversation memory
    result = await memory.add(
        messages=[
            {"role": "user", "content": "Hello, my name is Zhang Ming"},
            {"role": "assistant", "content": "Hello Zhang Ming!"}
        ],
        user_id="user_001",
        character_id="assistant",
        session_id="session_001"
    )
    print(f"Add memory: {'Success' if result['success'] else 'Failed'}")

    # Search relevant memories
    results = await memory.search(
        query="user's name",
        user_id="user_001",
        limit=5
    )
    print(f"Found {results.get('total', 0)} relevant memories")

    await memory.aclose()

asyncio.run(main())
```

### Self-Hosted (Open Source)

Requires database setup but offers full control:

```bash
# Clone repository
git clone https://github.com/TiMEM-AI/timem-ai.git
cd timem

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Start databases
cd migration && docker-compose up -d
```

## 📖 Examples

Example files are located in [`cloud-service/examples/`](cloud-service/examples/):

| File | Description |
|------|------|
| [01_quick_start.py](cloud-service/examples/01_quick_start.py) | Quick start - Get started in 5 minutes |
| [02_add_memory.py](cloud-service/examples/02_add_memory.py) | Add memory examples |
| [03_search_memory.py](cloud-service/examples/03_search_memory.py) | Search memory examples |
| [04_chat_demo.py](cloud-service/examples/04_chat_demo.py) | Chat demo - AI assistant with memory |

### Run Examples

```bash
cd cloud-service/examples

# Configure environment variables
export TIMEM_BASE_URL=https://api.timem.cloud
export TIMEM_API_KEY=your_api_key

# Run examples
python 01_quick_start.py
python 02_add_memory.py
python 03_search_memory.py
python 04_chat_demo.py
```

## 🧠 Core Concepts

### System Architecture

<p align="center">
  <img src="assets/timem-framework.jpg" width="1000px" alt="TiMem System Architecture">
</p>

**TiMem's architecture consists of three core components:**

1. **Memory Consolidation (Left)**: Transforms raw conversations into hierarchical memories through semantic-guided consolidation across 5 levels (L1-L5)

2. **Temporal Memory Tree (Center)**: Organizes memories with explicit temporal ordering, from fine-grained fragments (L1) to stable persona profiles (L5)

3. **Complexity-Aware Recall (Right)**: Adapts retrieval scope based on query complexity, balancing precision and efficiency

### How It Works

```
User: "I want to learn Python"

L1: Extract facts → "User wants to learn Python"
L2: Summarize session → "User started Python learning journey"
L3: Daily pattern → "User is actively learning Python this week"
L4: Weekly trend → "User's learning schedule is weekday evenings"
L5: Stable profile → "User = Python developer in training"
```

Later query: "What is the user's technical background?"

→ **Complexity Analysis**: Simple factual query
→ **Hierarchical Recall**: Check L1 → L5
→ **Result**: User is learning Python (from L5 profile)
→ **Response**: "Based on our conversations, you're learning Python..."

## ☁️ Cloud Service

TiMem Cloud Service is a fully managed version that requires no deployment.

### 🌐 Console Access

[**Console**](https://console.timem.cloud) — Manage your TiMem cloud service (China)

> **Note**: Universal console (timem.ai) will be available soon.

### Quick Start

See full guide: [cloud-service/README.md](cloud-service/README.md)

### Cloud Service vs Self-Hosted

| Feature | Cloud Service | Self-Hosted |
|:--------|:--------------|:------------|
| **Deployment** | None required | Full setup |
| **Maintenance** | Platform managed | Self-managed |
| **Data Control** | Cloud storage | Full control |
| **Cost** | Pay-per-use | Fixed cost |
| **Customization** | Limited | Full |

### Related Documentation

| Document | Description |
|:---------|:------------|
| [cloud-service/README.md](cloud-service/README.md) | Complete cloud service guide |
| [cloud-service/api/authentication.md](cloud-service/api/authentication.md) | Authentication guide |
| [cloud-service/api/reference.md](cloud-service/api/reference.md) | REST API reference |

## 📄 Research

### Paper

**TiMem: Temporal-Hierarchical Memory Consolidation for Long-Horizon Conversational Agents**

Long-horizon conversational agents have to manage ever-growing interaction histories that quickly exceed the finite context windows of large language models (LLMs). Existing memory frameworks provide limited support for temporally structured information across hierarchical levels, often leading to fragmented memories and unstable long-horizon personalization.

We present TiMem, a temporal–hierarchical memory framework that organizes conversations through a **Temporal Memory Tree (TMT)**, enabling systematic memory consolidation from raw conversational observations to progressively abstracted persona representations.

### Core Properties

1. **Temporal-Hierarchical Organization**: TMT provides explicit temporal ordering across 5 hierarchical levels
2. **Semantic-Guided Consolidation**: Memory integration across hierarchical levels without fine-tuning
3. **Complexity-Aware Memory Recall**: Balances precision and efficiency across queries of varying complexity

### Benchmark Results

| Benchmark | Metric | TiMem Performance |
|:----------|:-------|:------------------|
| **LoCoMo** | Accuracy | **75.30%** (State-of-the-Art) |
| **LongMemEval-S** | Accuracy | **76.88%** (State-of-the-Art) |
| **LoCoMo** | Memory Reduction | **52.20%** fewer tokens recalled |

**Manifold Analysis**: TiMem demonstrates clear persona separation on LoCoMo and reduced dispersion on LongMemEval-S, treating temporal continuity as a first-class organizing principle for long-horizon memory in conversational agents.

**Full Paper**: [arXiv:2601.02845](https://arxiv.org/abs/2601.02845)

## 🎉 📋 Changelog

Continuously maintained and upgraded:

- **2026.02.08** - Open source repository officially launched
- **2026.02.01** - Cloud service beta preview released
- **2026.01.06** - TiMem research paper published

---

## 📚 Documentation & Support

### 📖 Documentation
- **[Full Documentation](docs/en/README.md)** - Complete docs hub
- **[Developer Guide](docs/en/developer-guide/README.md)** - 30-min developer quickstart

### 🔧 API & SDK
- **[API Reference](docs/en/api-reference/overview.md)** - REST API docs
- **[Python SDK](docs/en/sdk/python/quickstart.md)** - Python integration
- **[Authentication](docs/en/api-reference/authentication.md)** - Auth guide

### 🛠️ Support
- **Issues**: [GitHub Issues](https://github.com/TiMEM-AI/timem/issues)
- **Contributing**: [CONTRIBUTING.md](CONTRIBUTING.md)
- **Troubleshooting**: [docs/en/troubleshooting.md](docs/en/troubleshooting.md)

## 📝 Citation

If you use TiMem in your research, please cite:

```bibtex
@misc{li2026timemtemporalhierarchicalmemoryconsolidation,
      title={TiMem: Temporal-Hierarchical Memory Consolidation for Long-Horizon Conversational Agents},
      author={Kai Li and Xuanqing Yu and Ziyi Ni and Yi Zeng and Yao Xu and Zheqing Zhang and Xin Li and Jitao Sang and Xiaogang Duan and Xuelei Wang and Chengbao Liu and Jie Tan},
      year={2026},
      eprint={2601.02845},
      archivePrefix={arXiv},
      primaryClass={cs.CL},
      url={https://arxiv.org/abs/2601.02845},
}
```

## ⚖️ License

Server Side Public License (SSPL) v1 — see the [LICENSE](LICENSE) file for details.

**Note:** This license requires that if you make the functionality of TiMem available to others as a network service, you must make your modifications (including all supporting software) available under the same license. This ensures cloud providers who use TiMem commercially contribute their improvements back to the community.

---

<p align="center">
  <strong>⭐ Star us on GitHub if TiMem helps you!</strong>
  <br><br>
  Supported by the TiMem team
</p>
