"""
TiMem Cloud Service - Quick Start Example

This example demonstrates the basic usage of TiMem cloud service:
1. Initialize AsyncMemory client with username/password
2. Add conversation memories
3. Search for relevant memories

Usage:
    python 01_quick_start.py

Requirements:
    - Configure .env file with TIMEM_USERNAME and TIMEM_PASSWORD
    - Optionally configure TIMEM_BASE_URL (default: http://localhost:8000)
"""

import os
import sys
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from dotenv import load_dotenv

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
env_path = os.path.join(project_root, ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)

from timem import AsyncMemory


def load_config():
    """Load configuration from environment variables"""
    TIMEM_USERNAME = os.getenv("TIMEM_USERNAME", "")
    TIMEM_PASSWORD = os.getenv("TIMEM_PASSWORD", "")
    TIMEM_BASE_URL = os.getenv("TIMEM_BASE_URL", "http://localhost:8000")

    if not TIMEM_USERNAME or not TIMEM_PASSWORD:
        print("=" * 60)
        print("TiMem Quick Start Example")
        print("=" * 60)
        print("\nError: TIMEM_USERNAME or TIMEM_PASSWORD not found")
        print("\nPlease configure your credentials:")
        print("  1. Copy .env.example to .env")
        print("  2. Edit .env and set TIMEM_USERNAME and TIMEM_PASSWORD")
        print("  3. Optionally set TIMEM_BASE_URL")
        print("\nFor demo server:")
        print("  TIMEM_USERNAME=test")
        print("  TIMEM_PASSWORD=test123")
        print("  TIMEM_BASE_URL=http://58.87.76.109:8000")
        print("=" * 60)
        sys.exit(1)

    return TIMEM_USERNAME, TIMEM_PASSWORD, TIMEM_BASE_URL


async def main():
    print("=" * 60)
    print("TiMem Cloud Service - Quick Start Example")
    print("=" * 60)

    TIMEM_USERNAME, TIMEM_PASSWORD, TIMEM_BASE_URL = load_config()

    print(f"\nConfiguration:")
    print(f"  Username: {TIMEM_USERNAME}")
    print(f"  Base URL: {TIMEM_BASE_URL}")

    memory = AsyncMemory(
        api_key=TIMEM_USERNAME,
        base_url=TIMEM_BASE_URL,
        username=TIMEM_USERNAME,
        password=TIMEM_PASSWORD,
    )

    print("\n[Step 1] Add conversation memory...")
    messages = [
        {"role": "user", "content": "Hello, my name is Zhang Ming"},
        {"role": "assistant", "content": "Hello Zhang Ming! Nice to meet you."},
        {
            "role": "user",
            "content": "I am a software engineer interested in AI research",
        },
    ]

    result = await memory.add(
        messages=messages,
        user_id="demo_user",
        character_id="assistant",
        session_id="demo_session",
    )

    if result.get("success"):
        print(f"  [OK] Memory added successfully! Total: {result.get('total', 0)}")
    else:
        print(
            f"  [FAIL] Failed to add memory: {result.get('message', 'Unknown error')}"
        )
        await memory.aclose()
        return

    print("\n[Step 2] Search for relevant memories...")
    result = await memory.search(
        query="What is the user's profession?",
        user_id="demo_user",
        limit=5,
    )

    if result.get("success"):
        total = result.get("total", 0)
        results = result.get("results", [])
        print(f"  [OK] Found {total} related memories:")
        for i, mem in enumerate(results[:3], 1):
            content = mem.get("memory", "")[:60]
            score = mem.get("score", 0)
            print(f"     {i}. [Score: {score:.2f}] {content}...")
    else:
        print(f"  [FAIL] Search failed: {result.get('message', 'Unknown error')}")

    await memory.aclose()

    print("\n" + "=" * 60)
    print("Quick Start Example Completed!")
    print("=" * 60)
    print("\nYou learned:")
    print("  [OK] How to initialize AsyncMemory client")
    print("  [OK] How to add conversation memories with add()")
    print("  [OK] How to search memories with search()")
    print("\nNext steps:")
    print("  - See 02_add_memory.py for more add examples")
    print("  - See 03_search_memory.py for more search examples")
    print("  - See 04_chat_demo.py for complete chat integration")


if __name__ == "__main__":
    asyncio.run(main())
