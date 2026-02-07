"""
TiMem Cloud Service - Chat Demo with Memory

This example demonstrates a complete AI chat assistant with memory:
1. Initialize TiMem memory client with username/password
2. Search relevant memories before responding
3. Save conversation to memory after each exchange
4. Uses mock responses when LLM is unavailable

Usage:
    python 04_chat_demo.py

Requirements:
    - Configure .env file with TIMEM_USERNAME and TIMEM_PASSWORD
    - Optionally configure TIMEM_BASE_URL and ZHIPUAI_API_KEY
"""

import os
import sys
import asyncio
from datetime import datetime
from typing import List, Dict, Optional

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
    ZHIPUAI_API_KEY = os.getenv("ZHIPUAI_API_KEY", "")

    if not TIMEM_USERNAME or not TIMEM_PASSWORD:
        print("=" * 60)
        print("TiMem Chat Demo")
        print("=" * 60)
        print("\nError: TIMEM_USERNAME or TIMEM_PASSWORD not found")
        sys.exit(1)

    return TIMEM_USERNAME, TIMEM_PASSWORD, TIMEM_BASE_URL, ZHIPUAI_API_KEY


class TiMemChatDemo:
    """Chat assistant with TiMem memory integration"""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        username: str,
        password: str,
        llm_api_key: str = None,
    ):
        """Initialize the chat demo"""
        self.user_id = "chat_demo_user"
        self.session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.chat_history: List[Dict] = []

        self.memory = AsyncMemory(
            api_key=api_key, base_url=base_url, username=username, password=password
        )

        self.llm = None
        if llm_api_key:
            try:
                from openai import OpenAI

                self.llm = OpenAI(
                    api_key=llm_api_key,
                    base_url="https://open.bigmodel.cn/api/paas/v4",
                )
                print("  [OK] ZhipuAI LLM connected")
            except ImportError:
                print("  [WARN] openai package not installed, using mock responses")
        else:
            print("  [INFO] ZHIPUAI_API_KEY not set, using mock responses")

    async def search_memories(self, query: str, limit: int = 5) -> List[Dict]:
        """Search relevant memories"""
        result = await self.memory.search(
            query=query,
            user_id=self.user_id,
            limit=limit,
        )
        return result.get("results", []) if result.get("success") else []

    async def add_memory(self, messages: List[Dict]) -> bool:
        """Save conversation to memory"""
        result = await self.memory.add(
            messages=messages,
            user_id=self.user_id,
            character_id="chat_assistant",
            session_id=self.session_id,
        )
        return result.get("success", False)

    def build_context(self, memories: List[Dict]) -> str:
        """Build context from memories"""
        if not memories:
            return "(First conversation - no prior context)"

        context_parts = ["Previous conversations:\n"]
        for mem in memories:
            content = mem.get("memory", "")
            context_parts.append(f"- {content}")
        return "\n".join(context_parts)

    def generate_response(self, user_message: str, context: str) -> str:
        """Generate response (mock or real LLM)"""
        if self.llm:
            try:
                from openai import OpenAI

                response = self.llm.chat.completions.create(
                    model="glm-4.5-flash",
                    messages=[
                        {
                            "role": "system",
                            "content": f"You are a helpful assistant. {context}",
                        },
                        {"role": "user", "content": user_message},
                    ],
                    temperature=0.7,
                    max_tokens=200,
                )
                return response.choices[0].message.content
            except Exception as e:
                print(f"  [WARN] LLM call failed: {e}")

        return self.mock_response(user_message, context)

    def mock_response(self, message: str, context: str) -> str:
        """Mock response when LLM is unavailable"""
        msg = message.lower()

        if any(greet in msg for greet in ["hello", "hi", "你好", "嗨"]):
            return "Hello! I'm your AI assistant with memory. How can I help you today?"
        elif "name" in msg or "名字" in msg:
            if "first conversation" in context.lower():
                return "I don't know your name yet. This is our first conversation!"
            return "Based on our previous conversations, I should know you!"
        elif "remember" in msg or "记住" in msg:
            return "I'll remember that! Feel free to ask me about our previous chats."
        elif "who are you" in msg or "你是谁" in msg:
            return "I'm an AI assistant powered by TiMem, which gives me long-term memory capabilities!"
        else:
            return f"You said: {message}\n(This is a mock response. Configure ZHIPUAI_API_KEY for real LLM.)"

    async def chat(self, user_message: str) -> str:
        """Process user message and generate response"""
        print(f"\n[User] {user_message}")

        memories = await self.search_memories(user_message, limit=3)
        context = self.build_context(memories)

        response = self.generate_response(user_message, context)

        print(f"[Assistant] {response}")

        messages = [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": response},
        ]
        await self.add_memory(messages)

        self.chat_history.extend(messages)

        return response

    async def close(self):
        """Close connections"""
        await self.memory.aclose()


async def main():
    print("=" * 60)
    print("TiMem Cloud Service - Chat Demo with Memory")
    print("=" * 60)

    TIMEM_USERNAME, TIMEM_PASSWORD, TIMEM_BASE_URL, ZHIPUAI_API_KEY = load_config()

    print(f"\nConfiguration:")
    print(f"  Base URL: {TIMEM_BASE_URL}")

    demo = TiMemChatDemo(
        api_key=TIMEM_USERNAME,
        base_url=TIMEM_BASE_URL,
        username=TIMEM_USERNAME,
        password=TIMEM_PASSWORD,
        llm_api_key=ZHIPUAI_API_KEY,
    )

    print(f"  User ID: {demo.user_id}")
    print(f"  Session ID: {demo.session_id}")

    print("\n" + "-" * 60)
    print("Demo Conversation (auto-run, press Ctrl+C to stop)")
    print("-" * 60)

    demo_messages = [
        "Hello! My name is Wang Fang.",
        "I'm a product manager working on AI products.",
        "Do you remember my name and profession?",
        "I'm also interested in machine learning.",
        "Who am I?",
    ]

    try:
        for msg in demo_messages:
            await demo.chat(msg)
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n\n[Demo interrupted by user]")

    await demo.close()

    print("\n" + "=" * 60)
    print("Chat Demo Completed!")
    print("=" * 60)
    print("\nThis demo showed:")
    print("  [OK] Memory search before responding")
    print("  [OK] Context-aware responses")
    print("  [OK] Automatic conversation saving")
    print("  [OK] Cross-session memory retrieval")


if __name__ == "__main__":
    asyncio.run(main())
