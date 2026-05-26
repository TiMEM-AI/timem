# TiMem Local Deployment Guide

This guide walks you through deploying TiMem (self-hosted) on your local machine.

## Quick Install (One-Line CLI)

The fastest way to install TiMem is using the built-in CLI:

```bash
# 1. Clone the repository
git clone https://github.com/TiMEM-AI/timem-ai.git
cd timem-ai

# 2. Install the package (includes CLI)
pip install -e .

# 3. Run the interactive setup wizard
timem setup wizard
```

**Even faster — one-line setup with your API key:**

```bash
timem setup quick --provider openai --api-key sk-your-key-here
```

## CLI Commands Reference

| Command | Description |
|---------|-------------|
| `timem setup wizard` | Full interactive setup (recommended for first-time) |
| `timem setup quick` | Minimal setup with command-line args |
| `timem start` | Start PostgreSQL and Qdrant containers |
| `timem stop` | Stop all database containers |
| `timem restart` | Restart database containers |
| `timem status` | Show container status |
| `timem db logs` | View container logs |
| `timem config init` | Create or update `.env` file |
| `timem config show` | Show current config (keys hidden) |
| `timem doctor` | Run environment diagnostics |
| `timem doctor test-connection` | Test database connectivity |

## Manual Setup (Without CLI)

If you prefer manual control over each step:

### Prerequisites

| Requirement | Minimum Version | Purpose |
|-------------|-----------------|---------|
| Python | 3.9+ | Runtime environment |
| Docker | 20.10+ | Database containers |
| Docker Compose | 2.0+ | Orchestration |
| Git | 2.20+ | Source control |

### Step 1: Environment Setup

```bash
# Create virtual environment
python -m venv .venv

# Activate
source .venv/bin/activate        # Linux/Mac
.venv\Scripts\activate          # Windows

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Database Deployment

```bash
# Start PostgreSQL and Qdrant containers
cd migration && docker-compose up -d

# Verify services are healthy
docker-compose ps
```

**Services started:**
- PostgreSQL on port `15432`
- Qdrant on port `16333` (HTTP) / `16334` (gRPC)

### Step 3: Configuration

Create `.env` from `.env.example` and fill in your API key:

```bash
cp .env.example .env
# Edit .env with your preferred editor
```

**Required fields:**
- `OPENAI_API_KEY` (or Claude/ZhipuAI/Qwen key)
- Database connection (pre-filled for local Docker)

### Step 4: Verification

```bash
# Check Python imports
python -c "from timem import AsyncMemory; print('SDK OK')"

# Check database connectivity
python -c "import asyncpg; print('PostgreSQL OK')"
python -c "from qdrant_client import QdrantClient; print('Qdrant OK')"
```

### Step 5: First Run

```bash
# Cloud SDK Example
python cloud-service/examples/01_quick_start.py
```

## Common Commands Reference

```bash
# Activate environment
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Start databases
cd migration && docker-compose up -d
# Or using CLI:
timem start

# Stop databases
cd migration && docker-compose down
# Or using CLI:
timem stop

# Reset database data (caution: destroys all data)
cd migration && docker-compose down -v

# View database logs
cd migration && docker-compose logs -f postgres
cd migration && docker-compose logs -f qdrant
# Or using CLI:
timem db logs postgres -f

# Run examples
cd cloud-service/examples
python 01_quick_start.py
python 02_add_memory.py
python 03_search_memory.py
python 04_chat_demo.py
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Port already in use | Change ports in `migration/docker-compose.yml` or stop conflicting services |
| Docker not running | Start Docker Desktop or `sudo systemctl start docker` |
| Import errors | Ensure virtual environment is activated and `pip install -r requirements.txt` succeeded |
| Database connection refused | Wait 30-60s after `docker-compose up` for initialization; check `docker-compose ps` |
| Out of memory during pip install | Use `pip install --no-cache-dir -r requirements.txt` |
| CLI not found after install | Ensure `pip install -e .` completed; try `python -m timem.cli --help` |

## Platform-Specific Notes

### Windows
- Use PowerShell or Git Bash for best compatibility
- Docker Desktop required (WSL2 backend recommended)
- Activate with `.venv\Scripts\activate`

### macOS
- Docker Desktop or Colima for container runtime
- May need `brew install postgresql libpq` for psycopg2 compilation

### Linux
- Add user to `docker` group to avoid sudo: `sudo usermod -aG docker $USER`
- PostgreSQL client libraries: `sudo apt install libpq-dev` (Debian/Ubuntu)

## Architecture Overview

```
TiMem Self-Hosted Stack

  [Your Application]
         |
    [timem SDK]  --- API --->  [TiMem Cloud]
         |                        (optional)
    [Core Modules]
    - timem.core        (memory tree, consolidation)
    - timem.memory      (L1-L5 hierarchy)
    - timem.workflows   (LangGraph pipelines)
    - services/         (business logic)
    - storage/          (persistence layer)
         |
    [Databases - Docker]
    - PostgreSQL  :15432  (relational data)
    - Qdrant      :16333  (vector storage)
    - Redis       :16379  (cache, optional)
    - Neo4j       :17474  (graph, optional)
```

## Next Steps After Deployment

1. **Read the developer guide**: [docs/en/developer-guide/README.md](../docs/en/developer-guide/README.md)
2. **Try examples**: [cloud-service/examples/](../cloud-service/examples/)
3. **Run experiments**: [experiments/README.md](../experiments/README.md)
4. **Configure your LLM**: Edit `.env` to set your preferred provider and model

## Resources

- [Main Documentation](../docs/en/README.md)
- [Developer Guide](../docs/en/developer-guide/README.md)
- [API Reference](../docs/en/api-reference/overview.md)
- [Troubleshooting](../docs/en/troubleshooting.md)
