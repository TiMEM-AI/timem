#!/usr/bin/env python3
"""
Mock LLM Adapter
Equivalent status to ZHIPU, OPENAI and other real adapters
Returns mock memory data in proper format, supporting TiMem's various memory level generation
"""

import random
import string
import asyncio
import json
from typing import List, Dict, Any, Optional, AsyncIterator
from datetime import datetime, timedelta
import uuid

from llm.base_llm import BaseLLM, Message, MessageRole, ChatResponse, EmbeddingResponse, ModelConfig
from timem.utils.logging import get_logger

logger = get_logger(__name__)

class MockLLMAdapter(BaseLLM):
    """Mock LLM Adapter - Equivalent status to ZHIPU, OPENAI and other real adapters"""
    
    def __init__(self, config: Dict[str, Any] = None):
        model_config = ModelConfig(
            model_name="mock-llm",
            temperature=0.7,
            max_tokens=2048
        )
        super().__init__(model_config)
        self.provider = "mock"
        self.model_name = "mock-llm"  # Add model_name attribute
        
        # Mock topic list
        self.topics = [
            "Time Management", "Stress Management", "Work-Life Balance", "Career Development", 
            "Interpersonal Relationships", "Healthy Habits", "Financial Planning", "Learning Methods",
            "Emotional Management", "Communication Skills", "Leadership", "Creativity"
        ]
        
        # Mock user sentiment/attitude
        self.attitudes = [
            "Positive", "Focused", "Curious", "Open", "Enthusiastic", 
            "Cautious", "Hesitant", "Confused", "Concerned", "Stressed"
        ]
        
        # Mock expert methods
        self.methods = [
            "Time Audit Method", "Pomodoro Technique", "Priority Matrix", "Goal Decomposition",
            "Scenario Simulation", "Case Analysis", "Brainstorming", "Reflective Journaling",
            "Action Plan", "Follow-up Mechanism"
        ]
        
        logger.info(f"Mock LLM adapter initialized successfully: {self.model_name}")
    
    def _generate_random_text(self, length: int = 50) -> str:
        """Generate random text"""
        chars = string.ascii_letters + string.digits + "，。！？；："
        return ''.join(random.choice(chars) for _ in range(length))
    
    def _generate_random_id(self) -> str:
        """Generate random ID"""
        return str(uuid.uuid4())[:8]
    
    def _get_random_items(self, items_list, count=2):
        """Randomly get specified number of items from list"""
        return random.sample(items_list, min(count, len(items_list)))
    
    def _generate_l1_memory(self) -> Dict[str, Any]:
        """Generate L1 fragment-level memory JSON"""
        topics = self._get_random_items(self.topics, 1)
        attitude = random.choice(self.attitudes)
        
        content = f"User discussed {topics[0]} topic, showing {attitude} attitude. This is an important conversation segment containing key information about {topics[0]}."
        
        return {
            "memory_type": "L1",
            "content": content,
            "summary": f"Conversation segment about {topics[0]}",
            "keywords": [topics[0], attitude, "conversation segment"],
            "sentiment": random.choice(["positive", "neutral", "negative"]),
            "importance": random.uniform(0.5, 1.0),
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "token_count": random.randint(50, 150),
                "source": "mock-llm"
            }
        }
    
    def _generate_l2_memory(self) -> Dict[str, Any]:
        """Generate L2 session-level memory JSON"""
        topics = self._get_random_items(self.topics, 2)
        methods = self._get_random_items(self.methods, 1)
        attitude = random.choice(self.attitudes)
        
        content = f"In this session, user and expert discussed {topics[0]} and {topics[1]} topics. User showed {attitude} attitude, expert helped user solve problems through {methods[0]}. Overall session effectiveness was good, user gained new insights about {topics[0]}."
        
        return {
            "memory_type": "L2",
            "content": content,
            "summary": f"Session summary about {topics[0]} and {topics[1]}",
            "topics": topics,
            "methods_used": methods,
            "user_attitude": attitude,
            "session_effectiveness": random.uniform(0.6, 0.95),
            "key_insights": [
                f"User understood the importance of {topics[0]}",
                f"Expert shared {methods[0]} method",
                f"Determined next steps to improve {topics[1]}"
            ],
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "token_count": random.randint(150, 300),
                "source": "mock-llm"
            }
        }
    
    def _generate_l3_memory(self) -> Dict[str, Any]:
        """Generate L3 daily report-level memory JSON"""
        topics = self._get_random_items(self.topics, 3)
        methods = self._get_random_items(self.methods, 2)
        attitude = random.choice(self.attitudes)
        
        content = f"Today user and expert had multiple exchanges, mainly discussing {topics[0]}, {topics[1]} and {topics[2]} topics. User showed {attitude} learning attitude, expert provided guidance through {methods[0]} and {methods[1]} methods. User made significant progress in {topics[0]}, gained deeper understanding of {topics[1]}, and started exploring {topics[2]}. Overall progress was smooth, achieved expected learning goals."
        
        return {
            "memory_type": "L3",
            "content": content,
            "summary": f"Today's learning summary about {topics[0]}, {topics[1]} and {topics[2]}",
            "date": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
            "topics_covered": topics,
            "methods_used": methods,
            "user_attitude": attitude,
            "progress_assessment": random.uniform(0.7, 0.9),
            "achievements": [
                f"Mastered basic concepts of {topics[0]}",
                f"Can apply {methods[0]} to solve practical problems",
                f"Started exploring advanced content of {topics[2]}"
            ],
            "next_steps": [
                f"Deeply study application scenarios of {topics[1]}",
                f"Practice using {methods[1]} to improve efficiency",
                f"Prepare practical project for {topics[2]}"
            ],
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "session_count": random.randint(2, 5),
                "token_count": random.randint(300, 500),
                "source": "mock-llm"
            }
        }
    
    def _generate_l4_memory(self) -> Dict[str, Any]:
        """Generate L4 weekly report-level memory JSON"""
        topics = self._get_random_items(self.topics, 4)
        methods = self._get_random_items(self.methods, 3)
        
        content = f"This week user and expert had in-depth exchanges centered on {topics[0]}, {topics[1]}, {topics[2]} and {topics[3]} core topics. Expert helped user establish knowledge system through {methods[0]}, {methods[1]} and {methods[2]} methods. User performed excellently in {topics[0]}, mastered key concepts; made breakthrough in {topics[1]}, can apply independently; gained systematic understanding of {topics[2]}; started exploring application scenarios of {topics[3]}. Overall learning progress steadily improved, knowledge system continuously refined, achieved weekly learning goals."
        
        return {
            "memory_type": "L4",
            "content": content,
            "summary": f"This week's multi-topic learning summary including {topics[0]}, {topics[1]}",
            "week": f"{datetime.now().isocalendar()[0]}-W{datetime.now().isocalendar()[1]}",
            "topics_covered": topics,
            "methods_used": methods,
            "learning_progress": {
                topics[0]: random.uniform(0.7, 0.9),
                topics[1]: random.uniform(0.6, 0.8),
                topics[2]: random.uniform(0.5, 0.7),
                topics[3]: random.uniform(0.3, 0.6)
            },
            "key_achievements": [
                f"Mastered core principles and application methods of {topics[0]}",
                f"Can independently apply {methods[0]} to solve complex problems",
                f"Established knowledge connections about {topics[1]} and {topics[2]}",
                f"Started applying {topics[3]} to practical scenarios"
            ],
            "growth_areas": [
                f"Advanced application scenarios of {topics[0]}",
                f"In-depth exploration of {topics[3]}",
                f"Proficient application of {methods[2]}"
            ],
            "next_week_focus": [
                f"Deepen practical application of {topics[1]}",
                f"Systematically study advanced content of {topics[3]}",
                f"Comprehensively apply {methods[0]} and {methods[1]} to improve efficiency"
            ],
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "daily_memory_count": random.randint(3, 7),
                "session_count": random.randint(5, 12),
                "token_count": random.randint(500, 800),
                "source": "mock-llm"
            }
        }
    
    def _generate_l5_memory(self) -> Dict[str, Any]:
        """Generate L5 monthly/high-dimensional memory JSON"""
        topics = self._get_random_items(self.topics, 5)
        methods = self._get_random_items(self.methods, 4)
        
        content = f"Over the past month, user systematically studied {topics[0]}, {topics[1]}, {topics[2]}, {topics[3]} and {topics[4]} core domains under expert guidance. Expert applied {methods[0]}, {methods[1]}, {methods[2]} and {methods[3]} various methods to help user establish complete knowledge system. User demonstrated continuous learning pattern, able to integrate various knowledge points, and started forming own learning methodology. Performed outstandingly in {topics[0]} and {topics[1]}, reached advanced application level; {topics[2]} and {topics[3]} have solid foundation; {topics[4]} steadily improving. User has formed systematic thinking, able to independently solve complex problems, demonstrated significant growth."
        
        return {
            "memory_type": "L5",
            "content": content,
            "summary": f"Monthly learning summary: systematic improvement across {topics[0]}, {topics[1]} and other domains",
            "month": datetime.now().strftime("%Y-%m"),
            "topics_mastered": topics[:2],
            "topics_proficient": topics[2:4],
            "topics_developing": [topics[4]],
            "methods_mastered": methods,
            "learning_pattern": "Continuous systematic learning, focus on practical application, good at integrating knowledge",
            "competency_assessment": {
                topics[0]: random.uniform(0.8, 0.95),
                topics[1]: random.uniform(0.75, 0.9),
                topics[2]: random.uniform(0.7, 0.85),
                topics[3]: random.uniform(0.65, 0.8),
                topics[4]: random.uniform(0.5, 0.7)
            },
            "major_achievements": [
                f"Established complete knowledge system of {topics[0]}",
                f"Can flexibly apply {methods[0]} and {methods[1]} to solve complex problems",
                f"Integrated knowledge of {topics[1]} and {topics[2]}",
                f"Developed personalized learning method for {topics[3]}"
            ],
            "growth_trajectory": "Steadily rising, learning efficiency continuously improving, knowledge application ability significantly enhanced",
            "long_term_goals": [
                f"Professional-level application of {topics[0]} and {topics[1]}",
                f"Systematically master all content of {topics[4]}",
                f"Develop personal knowledge management system based on {methods[2]}"
            ],
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "weekly_memory_count": random.randint(3, 5),
                "daily_memory_count": random.randint(12, 25),
                "session_count": random.randint(20, 40),
                "token_count": random.randint(800, 1200),
                "source": "mock-llm"
            }
        }
    
    def _wrap_zhipu_response(self, content: str) -> str:
        """Wrap content in Zhipu LLM API style response format"""
        return json.dumps({
            "code": 200,
            "msg": "success",
            "data": {
                "choices": [
                    {"content": content, "role": "assistant"}
                ],
                "usage": {
                    "prompt_tokens": random.randint(50, 200),
                    "completion_tokens": random.randint(30, 100),
                    "total_tokens": random.randint(80, 300)
                }
            }
        }, ensure_ascii=False)
        
    def _is_identity_query(self, prompt: str) -> bool:
        """Check if query is about identity/model"""
        keywords = [
            "who are you", "what model", "what are you", "who am i talking to"
        ]
        return any(k in prompt.lower() for k in keywords)

    async def generate_text(self, prompt: str, **kwargs) -> str:
        """Generate text - main interface of mock LLM"""
        logger.debug(f"Mock LLM generating text, input length: {len(prompt)}")
        
        # Identity/model related questions, directly return identity statement
        if self._is_identity_query(prompt):
            identity = "I am an AI assistant implemented with default model, deeply integrated with Cursor IDE, able to efficiently handle your programming and technical questions. I can help with any programming-related content! What would you like to do now?"
            return self._wrap_zhipu_response(identity)

        # Recognize memory level based on input content and return corresponding response
        try:
            if "L1" in prompt or "fragment" in prompt.lower():
                logger.info("Mock LLM generating L1 fragment-level memory")
                memory_json = self._generate_l1_memory()
                return self._wrap_zhipu_response(json.dumps(memory_json, ensure_ascii=False))
                
            elif "L2" in prompt or "session" in prompt.lower():
                logger.info("Mock LLM generating L2 session-level memory")
                memory_json = self._generate_l2_memory()
                return self._wrap_zhipu_response(json.dumps(memory_json, ensure_ascii=False))
                
            elif "L3" in prompt or "daily" in prompt.lower():
                logger.info("Mock LLM generating L3 daily report-level memory")
                memory_json = self._generate_l3_memory()
                return self._wrap_zhipu_response(json.dumps(memory_json, ensure_ascii=False))
                
            elif "L4" in prompt or "weekly" in prompt.lower():
                logger.info("Mock LLM generating L4 weekly report-level memory")
                memory_json = self._generate_l4_memory()
                return self._wrap_zhipu_response(json.dumps(memory_json, ensure_ascii=False))
                
            elif "L5" in prompt or "monthly" in prompt.lower():
                logger.info("Mock LLM generating L5 high-dimensional memory")
                memory_json = self._generate_l5_memory()
                return self._wrap_zhipu_response(json.dumps(memory_json, ensure_ascii=False))
                
            else:
                # Default to L1 memory
                logger.info("Mock LLM unable to recognize memory type, generating L1 memory by default")
                memory_json = self._generate_l1_memory()
                return self._wrap_zhipu_response(json.dumps(memory_json, ensure_ascii=False))
        except Exception as e:
            logger.error(f"Error generating memory JSON: {str(e)}")
            # Return a simple but valid JSON
            return self._wrap_zhipu_response(json.dumps({"content": "This is mock memory content", "memory_type": "unknown"}))
    
    async def generate_summary(self, content: str, max_length: int = 200) -> str:
        """Generate text summary"""
        if not content:
            return "No content provided"
        # Simply return the first N characters of the content
        return content[:min(len(content), max_length)] + "..."
    
    def _generate_memory_timestamp(self, memory_type: str) -> datetime:
        """Generate appropriate timestamp for different memory levels"""
        now = datetime.now()
        
        # Return a suitable timestamp based on memory level
        if memory_type == "L1":
            return now - timedelta(minutes=random.randint(5, 30))
        elif memory_type == "L2":
            return now - timedelta(hours=random.randint(1, 6))
        elif memory_type == "L3":
            return now - timedelta(days=random.randint(1, 3))
        elif memory_type == "L4":
            return now - timedelta(weeks=random.randint(1, 3))
        elif memory_type == "L5":
            return now - timedelta(days=random.randint(30, 90))
        else:
            return now
            
    async def generate_memory_summary(self, memory_level: str, child_summaries: List[str], 
                                     historical_summaries: List[str] = None, 
                                     metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Generate memory summary - for MockLLM environment
        
        Args:
            memory_level: Memory level
            child_summaries: List of child memory summaries
            historical_summaries: List of historical memory summaries
            metadata: Metadata
            
        Returns:
            Dict containing generation results
        """
        # Generate different summaries based on memory level
        if memory_level == "L1":
            summary = f"L1 fragment memory summary (Mock): contains {len(child_summaries)} child items"
            timestamp = self._generate_memory_timestamp("L1")
        elif memory_level == "L2":
            summary = f"L2 session memory summary (Mock): contains {len(child_summaries)} conversation segments"
            timestamp = self._generate_memory_timestamp("L2")
        elif memory_level == "L3":
            day_info = metadata.get("day", "unknown date") if metadata else "unknown date"
            summary = f"L3 daily report summary (Mock): {day_info}, contains {len(child_summaries)} sessions"
            timestamp = self._generate_memory_timestamp("L3")
        elif memory_level == "L4":
            summary = f"L4 weekly report summary (Mock): contains {len(child_summaries)} daily reports"
            timestamp = self._generate_memory_timestamp("L4")
        elif memory_level == "L5":
            summary = f"L5 monthly report summary (Mock): contains {len(child_summaries)} weekly reports"
            timestamp = self._generate_memory_timestamp("L5")
        else:
            summary = f"Unknown type memory summary (Mock): contains {len(child_summaries)} child memories"
            timestamp = self._generate_memory_timestamp("L1")
        
        # Construct complete memory object
        memory_data = {
            "memory_id": str(uuid.uuid4()),
            "summary": summary,
            "content": f"This is {memory_level} level memory content. {summary}",
            "level": memory_level,
            "timestamp": timestamp.isoformat(),
            "created_at": datetime.now().isoformat(),
            "user_id": metadata.get("user_id", "default_user") if metadata else "default_user",
            "expert_id": metadata.get("expert_id", "default_expert") if metadata else "default_expert",
            "session_id": metadata.get("session_id", "default_session") if metadata else "default_session",
            "child_memory_ids": [str(uuid.uuid4()) for _ in range(min(3, len(child_summaries)))]
        }
        
        # Simulate LLM response JSON structure
        mock_response = {
            "data": {
                "choices": [
                    {
                        "content": json.dumps(memory_data, ensure_ascii=False)
                    }
                ]
            }
        }
        
        return mock_response
    
    async def generate_progressive_summary(self, text: str, context: str = "") -> str:
        """Generate progressive summary"""
        return await self.generate_text(f"Based on historical context, please generate a progressive summary for the following content: {text}")
    
    async def generate_session_summary(self, fragments: List) -> str:
        """Generate session summary"""
        return await self.generate_text("L2 Please generate a summary for the entire session")
    
    async def generate_daily_summary(self, sessions: List) -> str:
        """Generate daily report summary"""
        return await self.generate_text("L3 Please generate a daily report summary for today's sessions")
    
    async def generate_weekly_summary(self, daily_memories: List) -> str:
        """Generate weekly report summary"""
        return await self.generate_text("L4 Please generate a weekly report summary for this week's memories")
    
    async def generate_user_profile(self, weekly_memories: List) -> str:
        """Generate user profile"""
        return await self.generate_text("L5 Please generate a user profile summary")
    
    async def generate_expert_memory(self, user_profiles: List) -> str:
        """Generate expert memory"""
        return await self.generate_text("Please generate an expert memory summary")
    
    async def chat_completion(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """Chat completion interface"""
        # Extract the last user message
        user_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_message = msg.get("content", "")
                break
        
        return await self.generate_text(user_message)
    
    def is_available(self) -> bool:
        """Check if adapter is available"""
        return True
    
    async def test_connection(self) -> bool:
        """Test connection"""
        return True
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get model information"""
        return {
            "provider": "mock",
            "model_name": "mock-llm",
            "type": "text-generation",
            "max_tokens": 4096,
            "temperature": 0.7
        }
    
    # Implement BaseLLM abstract methods
    async def chat(self, messages: List[Message], **kwargs) -> ChatResponse:
        """Chat conversation"""
        content = await self.generate_text("Chat conversation")
        return ChatResponse(
            content=content,
            finish_reason="stop",
            model=self.config.model_name,
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            response_time=0.1
        )
    
    async def chat_stream(self, messages: List[Message], **kwargs) -> AsyncIterator[str]:
        """Streaming chat conversation"""
        content = await self.generate_text("Streaming chat conversation")
        yield content
    
    async def complete(self, prompt: str, **kwargs) -> str:
        """Text completion"""
        return await self.generate_text(prompt)
    
    async def embed(self, text: str, **kwargs) -> EmbeddingResponse:
        """Text embedding"""
        # Generate random vector
        embedding = [random.uniform(-1, 1) for _ in range(384)]
        return EmbeddingResponse(
            embedding=embedding,
            model=self.config.model_name,
            usage={"prompt_tokens": 0, "total_tokens": 0},
            response_time=0.1
        )
    
    async def embed_batch(self, texts: List[str], **kwargs) -> List[EmbeddingResponse]:
        """Batch text embedding"""
        responses = []
        for text in texts:
            responses.append(await self.embed(text, **kwargs))
        return responses
    
    async def summarize(self, text: str, **kwargs) -> str:
        """Text summarization"""
        return await self.generate_text(f"Please summarize the following content: {text}")
    
    async def validate_model(self, model_name: str) -> bool:
        """Validate if model is available"""
        return True
    
    async def get_model_info(self, model_name: str) -> Dict[str, Any]:
        """Get model information"""
        return {
            "provider": "mock",
            "model_name": model_name,
            "type": "text-generation",
            "max_tokens": 4096,
            "temperature": 0.7
        }