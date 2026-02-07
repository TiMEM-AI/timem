# Contributing to TiMem

Thank you for your interest in contributing to TiMem! We welcome contributions in all forms, including but not limited to:

- Reporting bugs
- Discussing code status
- Submitting fixes
- Proposing new features
- Becoming a maintainer

We use GitHub to host code, track issues and feature requests, and receive pull requests.

---

## Contribution Flow

### 1. Fork and Clone Repository

```bash
# 1. Fork this repository to your GitHub account
# 2. Clone your fork
git clone https://github.com/YOUR_USERNAME/timem.git
cd timem

# 3. Add upstream repository
git remote add upstream https://github.com/TiMEM-AI/timem.git
```

### 2. Create Feature Branch

```bash
# Create a feature branch from main
git checkout main
git pull upstream main
git checkout -b feature/your-feature-name

# Or fix a bug
git checkout -b fix/your-bug-fix
```

### 3. Development

- Follow [Code Standards](#code-standards)
- Add [Tests](#testing-requirements) for your code
- Update relevant [Documentation](#documentation-requirements)

### 4. Commit Your Changes

```bash
# Add changed files
git add .

# Commit (follow commit message convention)
git commit -m "feat: add new feature description"
```

**Commit Message Convention**:

```
<type>(<scope>): <short description>

<full description>

<closes issue>
```

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation update
- `style`: Code formatting (doesn't affect code execution)
- `refactor`: Refactoring (neither new feature nor fix)
- `perf`: Performance optimization
- `test`: Adding tests
- `chore`: Build process or auxiliary tool changes

### 5. Push to Your Fork

```bash
git push origin feature/your-feature-name
```

### 6. Create Pull Request

1. Visit the original repository on GitHub
2. Click "New Pull Request"
3. Select your feature branch
4. Fill in the PR template
5. Wait for code review

---

## Development Environment Setup

### Python Version Requirements

TiMem supports Python 3.10+. We recommend using Python 3.13 for development.

### Install Dependencies

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Install development dependencies
pip install pytest pytest-cov pytest-asyncio ruff pre-commit
```

### Pre-commit Hooks

We use pre-commit to ensure code quality:

```bash
# Install pre-commit hooks
pre-commit install

# Manually run pre-commit
pre-commit run --all-files
```

---

## Code Standards

### Code Style

We use [Ruff](https://docs.astral.sh/ruff/) for code checking and formatting:

```bash
# Check code
ruff check .

# Auto-fix
ruff check --fix .

# Format code
ruff format .
```

### Type Annotations

TiMem uses Python type annotations. All public functions and methods should have type annotations:

```python
from typing import List, Dict, Optional

def generate_memory(
    user_id: str,
    expert_id: str,
    session_id: str,
    conversation: List[Dict[str, str]],
) -> Optional[Memory]:
    """Generate memory.

    Args:
        user_id: User ID
        expert_id: Expert ID
        session_id: Session ID
        conversation: Conversation list

    Returns:
        Generated memory object, or None if failed
    """
    ...
```

### Naming Conventions

- **Modules**: lowercase with underscores: `memory_generator.py`
- **Classes**: PascalCase: `MemoryGenerator`
- **Functions and methods**: lowercase with underscores: `generate_memory`
- **Constants**: UPPER_CASE with underscores: `MAX_MEMORY_SIZE`
- **Private methods**: single underscore prefix: `_internal_method`

### Docstrings

Use Google-style docstrings:

```python
def retrieve_memories(
    query: str,
    user_id: str,
    limit: int = 10,
) -> List[Memory]:
    """Retrieve memories based on query.

    Args:
        query: Query text
        user_id: User ID
        limit: Maximum number of memories to return

    Returns:
        List of retrieved memories

    Raises:
        ValueError: If query is empty
        DatabaseError: If database connection fails
    """
    ...
```

---

## Testing Requirements

### Running Tests

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/unit/test_memory_generator.py

# Run specific test
pytest tests/unit/test_memory_generator.py::test_generate_memory

# With coverage report
pytest tests/ --cov=timem --cov-report=html
```

### Test Structure

```
tests/
├── unit/              # Unit tests
├── integration/       # Integration tests
└── conftest.py        # pytest configuration
```

### Testing Standards

- Test files start with `test_`
- Test functions start with `test_`
- Use descriptive test names
- Each test should be independent
- Use fixtures to share test data

```python
import pytest

def test_memory_generation_with_valid_input():
    """Test memory generation with valid input."""
    # Arrange
    generator = MemoryGenerator()
    conversation = [...]

    # Act
    result = generator.generate_memory(...)

    # Assert
    assert result is not None
    assert result.title != ""
```

---

## Documentation Requirements

### Code Documentation

- All public APIs must have docstrings
- Complex logic should have explanatory comments
- Update relevant README and API documentation

### Markdown Documentation

- Use clear heading hierarchy
- Add code examples
- Keep language concise and clear

---

## Issue Reporting

### Bug Reports

When reporting bugs, please provide:

1. Clear problem description
2. Steps to reproduce
3. Expected behavior
4. Actual behavior
5. Environment information (Python version, OS, etc.)
6. Relevant log output

Use our [Bug Report Template](.github/ISSUE_TEMPLATE/bug_report.yml).

### Feature Requests

When proposing features, please explain:

1. Feature description
2. Use cases
3. Suggested implementation
4. Possible alternatives

Use our [Feature Request Template](.github/ISSUE_TEMPLATE/feature_request.yml).

---

## Pull Request Guidelines

### PR Checklist

Before submitting a PR, please confirm:

- [ ] Code follows project standards
- [ ] Necessary tests added
- [ ] All tests pass
- [ ] Relevant documentation updated
- [ ] Commit message is clear
- [ ] PR description is complete

### PR Review Process

1. **Automated Checks**: CI will automatically run tests and code checks
2. **Code Review**: Maintainers will review your code
3. **Feedback**: Make changes based on feedback if needed
4. **Merge**: After review approval, your PR will be merged

---

## Development Resources

### Project Structure

```
timem-oss/
├── timem/           # Core code
├── llm/            # LLM adapters
├── storage/        # Storage layer
├── services/       # Service layer
├── experiments/    # Experiment scripts
├── tests/          # Test code
├── examples/       # Example code
└── config/         # Configuration files
```

### Key Documentation

- [README.md](README.md) - Project overview
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) - Architecture design
- [API Reference](docs/api-reference/overview.md) - API documentation
- [Deployment Guide](DEPLOYMENT.md) - Deployment instructions

### Getting Help

- **GitHub Issues**: Report bugs and feature requests
- **Discussions**: Technical discussions and questions
- **Email**: Contact maintainers (if necessary)

---

## Code of Conduct

### Our Pledge

To foster an open and welcoming environment, we pledge to make participation in our project a harassment-free experience for everyone, regardless of experience level, gender, gender identity and expression, sexual orientation, disability, personal appearance, body size, race, ethnicity, age, religion, or nationality.

### Our Standards

Positive behavior includes:
- Using welcoming and inclusive language
- Respecting differing viewpoints and experiences
- Gracefully accepting constructive criticism
- Focusing on what is best for the community
- Showing empathy towards other community members

Unacceptable behavior includes:
- Use of sexualized language or imagery
- Personal or political attacks
- Public or private harassment
- Publishing others' private information without explicit permission
- Other unprofessional or inappropriate conduct

---

## License

By contributing code, you agree that your contributions will be released under the same [Apache 2.0 License](LICENSE) as the project.

---

## Acknowledgments

Thank you to all developers who contribute to TiMem! Your contributions make this project better.

---

## Contact

- **Project Homepage**: https://github.com/TiMEM-AI/timem
- **Issue Tracker**: https://github.com/TiMEM-AI/timem/issues
- **Discussions**: https://github.com/TiMEM-AI/timem/discussions

---

Thank you again for your contribution! Let's make TiMem better together.
