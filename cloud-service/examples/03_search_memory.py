"""
TiMem Cloud Service - Search Memory Examples

This example demonstrates various ways to search memories:
1. Basic search by query
2. Search with limit
3. Search specific user/session
4. Cross-session search

Usage:
    python 03_search_memory.py

Requirements:
    - Run 02_add_memory.py first to add test data
    - Configure .env file with TIMEM_USERNAME and TIMEM_PASSWORD
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
        print("TiMem Search Memory Examples")
        print("=" * 60)
        print("\nError: TIMEM_USERNAME or TIMEM_PASSWORD not found")
        sys.exit(1)

    return TIMEM_USERNAME, TIMEM_PASSWORD, TIMEM_BASE_URL


async def example_1_basic_search():
    """Example 1: Basic search by query"""
    print("\n[Example 1] Basic Search")
    print("-" * 50)

    result = await memory.search(
        query="hiking photography",
        user_id="add_example_user",
        limit=5,
    )

    if result.get("success"):
        total = result.get("total", 0)
        results = result.get("results", [])
        print(f"  [OK] Found {total} memories matching 'hiking photography'")
        for i, mem in enumerate(results[:3], 1):
            content = mem.get("memory", "")[:60]
            score = mem.get("score", 0)
            print(f"     {i}. [Score: {score:.2f}] {content}...")
    else:
        print(f"  [FAIL] {result.get('message', 'Unknown error')}")


async def example_2_search_with_limit():
    """Example 2: Search with result limit"""
    print("\n[Example 2] Search with Limit")
    print("-" * 50)

    result = await memory.search(
        query="Tokyo trip travel",
        user_id="add_example_user",
        limit=3,
    )

    if result.get("success"):
        total = result.get("total", 0)
        results = result.get("results", [])
        print(f"  [OK] Found {total} memories (showing top {len(results)})")
        for i, mem in enumerate(results, 1):
            content = mem.get("memory", "")[:60]
            score = mem.get("score", 0)
            print(f"     {i}. [Score: {score:.2f}] {content}...")
    else:
        print(f"  [FAIL] {result.get('message', 'Unknown error')}")


async def example_3_search_specific_user():
    """Example 3: Search for specific user"""
    print("\n[Example 3] Search Specific User")
    print("-" * 50)

    users = ["alice", "bob", "charlie"]
    for user_id in users:
        result = await memory.search(
            query="",
            user_id=user_id,
            limit=3,
        )

        if result.get("success"):
            total = result.get("total", 0)
            print(f"  [OK] {user_id}: {total} memories")
        else:
            print(f"  [FAIL] {user_id}: {result.get('message', 'Unknown error')}")


async def example_4_cross_session_search():
    """Example 4: Cross-session search (session_id=None)"""
    print("\n[Example 4] Cross-Session Search")
    print("-" * 50)

    result = await memory.search(
        query="software developer AI",
        user_id="bob",
        session_id=None,
        limit=5,
    )

    if result.get("success"):
        total = result.get("total", 0)
        results = result.get("results", [])
        print(f"  [OK] Found {total} memories across all sessions")
        for i, mem in enumerate(results[:3], 1):
            content = mem.get("memory", "")[:60]
            score = mem.get("score", 0)
            print(f"     {i}. [Score: {score:.2f}] {content}...")
    else:
        print(f"  [FAIL] {result.get('message', 'Unknown error')}")


async def example_5_search_with_character():
    """Example 5: Search with specific character"""
    print("\n[Example 5] Search with Character")
    print("-" * 50)

    result = await memory.search(
        query="",
        user_id="add_example_user",
        character_id="travel_assistant",
        limit=5,
    )

    if result.get("success"):
        total = result.get("total", 0)
        results = result.get("results", [])
        print(f"  [OK] Found {total} memories with character 'travel_assistant'")
        for i, mem in enumerate(results[:3], 1):
            content = mem.get("memory", "")[:60]
            print(f"     {i}. {content}...")
    else:
        print(f"  [FAIL] {result.get('message', 'Unknown error')}")


async def main():
    global memory

    print("=" * 60)
    print("TiMem Cloud Service - Search Memory Examples")
    print("=" * 60)

    TIMEM_USERNAME, TIMEM_PASSWORD, TIMEM_BASE_URL = load_config()
    print(f"\nBase URL: {TIMEM_BASE_URL}")
    print("\nNote: Run 02_add_memory.py first to add test data")

    memory = AsyncMemory(
        api_key=TIMEM_USERNAME,
        base_url=TIMEM_BASE_URL,
        username=TIMEM_USERNAME,
        password=TIMEM_PASSWORD,
    )

    await example_1_basic_search()
    await asyncio.sleep(0.5)

    await example_2_search_with_limit()
    await asyncio.sleep(0.5)

    await example_3_search_specific_user()
    await asyncio.sleep(0.5)

    await example_4_cross_session_search()
    await asyncio.sleep(0.5)

    await example_5_search_with_character()

    await memory.aclose()

    print("\n" + "=" * 60)
    print("Search Memory Examples Completed!")
    print("=" * 60)
    print("\nKey takeaways:")
    print("  [OK] search() finds memories matching query text")
    print("  [OK] limit controls maximum results returned")
    print("  [OK] session_id=None searches across all sessions")
    print("  [OK] character_id filters by assistant role")
    print("  [OK] Results include 'score' (relevance) and 'memory' (content)")
    print("\nNext: See 04_chat_demo.py for complete integration")


if __name__ == "__main__":
    asyncio.run(main())
