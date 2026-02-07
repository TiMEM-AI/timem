"""
TiMem Cloud Service - Add Memory Examples

This example demonstrates various ways to add memories:
1. Single conversation
2. Multiple messages
3. Different users and sessions

Usage:
    python 02_add_memory.py

Requirements:
    - Configure .env file with TIMEM_USERNAME and TIMEM_PASSWORD
"""

import os
import sys
import asyncio
from datetime import datetime

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
        print("TiMem Add Memory Examples")
        print("=" * 60)
        print("\nError: TIMEM_USERNAME or TIMEM_PASSWORD not found")
        sys.exit(1)

    return TIMEM_USERNAME, TIMEM_PASSWORD, TIMEM_BASE_URL


async def example_1_simple_conversation():
    """Example 1: Simple conversation with single exchange"""
    print("\n[Example 1] Simple Conversation")
    print("-" * 50)

    messages = [
        {"role": "user", "content": "Hello! My name is Li Ming."},
        {"role": "assistant", "content": "Nice to meet you, Li Ming!"},
    ]

    result = await memory.add(
        messages=messages,
        user_id="add_example_user",
        character_id="assistant",
        session_id="session_1",
    )

    if result.get("success"):
        print(f"  [OK] Added {result.get('total', 0)} memories")
    else:
        print(f"  [FAIL] {result.get('message', 'Unknown error')}")


async def example_2_multi_message():
    """Example 2: Multiple messages in one call"""
    print("\n[Example 2] Multiple Messages")
    print("-" * 50)

    messages = [
        {"role": "user", "content": "I'm planning a trip to Tokyo next month"},
        {
            "role": "assistant",
            "content": "That sounds exciting! Tokyo has amazing culture and food.",
        },
        {
            "role": "user",
            "content": "Yes! I want to visit temples and try authentic Japanese food",
        },
        {
            "role": "assistant",
            "content": "I recommend Senso-ji Temple and the Tsukiji Market area!",
        },
    ]

    result = await memory.add(
        messages=messages,
        user_id="add_example_user",
        character_id="travel_assistant",
        session_id="session_2",
    )

    if result.get("success"):
        print(
            f"  [OK] Added {result.get('total', 0)} memories from multi-message conversation"
        )
    else:
        print(f"  [FAIL] {result.get('message', 'Unknown error')}")


async def example_3_different_users():
    """Example 3: Different users, same assistant"""
    print("\n[Example 3] Different Users")
    print("-" * 50)

    users = [
        ("alice", "I love hiking and photography"),
        ("bob", "I'm a software developer working on AI projects"),
        ("charlie", "I run a small bakery in downtown"),
    ]

    for user_id, content in users:
        messages = [{"role": "user", "content": content}]
        result = await memory.add(
            messages=messages,
            user_id=user_id,
            character_id="personal_assistant",
            session_id=f"session_{user_id}",
        )
        status = "OK" if result.get("success") else "FAIL"
        print(f"  [{status}] {user_id}: {content[:30]}...")


async def example_4_single_message():
    """Example 4: Single user message only"""
    print("\n[Example 4] Single Message")
    print("-" * 50)

    messages = [{"role": "user", "content": "Remind me to call mom at 7pm today"}]

    result = await memory.add(
        messages=messages,
        user_id="add_example_user",
        character_id="assistant",
        session_id="session_reminder",
    )

    if result.get("success"):
        print(f"  [OK] Added reminder: {result.get('total', 0)} memories")
    else:
        print(f"  [FAIL] {result.get('message', 'Unknown error')}")


async def main():
    global memory

    print("=" * 60)
    print("TiMem Cloud Service - Add Memory Examples")
    print("=" * 60)

    TIMEM_USERNAME, TIMEM_PASSWORD, TIMEM_BASE_URL = load_config()
    print(f"\nBase URL: {TIMEM_BASE_URL}")

    memory = AsyncMemory(
        api_key=TIMEM_USERNAME,
        base_url=TIMEM_BASE_URL,
        username=TIMEM_USERNAME,
        password=TIMEM_PASSWORD,
    )

    await example_1_simple_conversation()
    await asyncio.sleep(0.5)

    await example_2_multi_message()
    await asyncio.sleep(0.5)

    await example_3_different_users()
    await asyncio.sleep(0.5)

    await example_4_single_message()

    await memory.aclose()

    print("\n" + "=" * 60)
    print("Add Memory Examples Completed!")
    print("=" * 60)
    print("\nKey takeaways:")
    print("  [OK] add() accepts list of message dictionaries")
    print("  [OK] Each message has 'role' (user/assistant) and 'content'")
    print("  [OK] user_id identifies the user")
    print("  [OK] character_id identifies the assistant role")
    print("  [OK] session_id groups related conversations")
    print("\nNext: See 03_search_memory.py to retrieve these memories")


if __name__ == "__main__":
    asyncio.run(main())
