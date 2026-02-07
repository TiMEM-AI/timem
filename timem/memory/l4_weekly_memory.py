"""
TiMem L4 Weekly-level Memory Implementation
Handles single-user-single-expert-multi-session weekly memory aggregation with weekly updates
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from collections import defaultdict, Counter

from timem.utils import time_utils
from timem.utils.text_processing import LLMTextProcessor
from timem.utils.logging import get_logger
from timem.memory.l3_daily_memory import DailyMemory


@dataclass
class InteractionPattern:
    """Interaction Pattern"""
    pattern_type: str
    description: str
    frequency: float
    confidence: float
    examples: List[str]
    metadata: Dict[str, Any] = None


@dataclass
class KnowledgeEvolution:
    """Knowledge Evolution"""
    topic: str
    evolution_type: str  # "emerging", "growing", "declining", "stable"
    trend_strength: float
    key_milestones: List[Dict[str, Any]]
    prediction: str
    metadata: Dict[str, Any] = None


@dataclass
class WeeklyMemory:
    """Weekly Memory"""
    id: str
    user_id: str
    expert_id: str
    week_start: datetime
    week_end: datetime
    summary: str
    key_topics: List[str]
    interaction_patterns: List[InteractionPattern]
    knowledge_evolution: List[KnowledgeEvolution]
    daily_memories: List[DailyMemory]
    trend_analysis: Dict[str, Any]
    importance_score: float
    created_at: datetime
    metadata: Dict[str, Any] = None


class L4WeeklyMemory:
    """L4 Weekly-level Memory Processor"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.pattern_window = config.get("pattern_window", 7)  # Pattern window size
        self.update_frequency = config.get("update_frequency", "weekly")
        self.trend_analysis_enabled = config.get("trend_analysis", True)
        
        self.text_processor = LLMTextProcessor()
        self.logger = get_logger(__name__)
        
        # Daily memory buffer
        self.daily_buffer: Dict[str, Dict[str, List[DailyMemory]]] = defaultdict(lambda: defaultdict(list))
        self.weekly_memories: Dict[str, WeeklyMemory] = {}
        
        self.logger.info(f"Initialized L4 weekly-level memory processor, pattern window: {self.pattern_window} days")
    
    async def add_daily_memory(self, user_id: str, expert_id: str, daily_memory: DailyMemory) -> bool:
        """
        Add daily memory, may trigger weekly memory generation
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            daily_memory: Daily memory
            
        Returns:
            Whether weekly memory generation was triggered
        """
        # Add to buffer
        self.daily_buffer[user_id][expert_id].append(daily_memory)
        
        # Sort by time
        self.daily_buffer[user_id][expert_id].sort(key=lambda x: x.date)
        
        self.logger.info(f"Added daily memory to L4 buffer, user: {user_id}, expert: {expert_id}")
        
        # Check if aggregation conditions are met
        if self._check_aggregation_conditions(user_id, expert_id):
            await self._generate_weekly_memory(user_id, expert_id)
            return True
        
        return False
    
    def _check_aggregation_conditions(self, user_id: str, expert_id: str) -> bool:
        """Check if aggregation conditions are met"""
        if user_id not in self.daily_buffer or expert_id not in self.daily_buffer[user_id]:
            return False
        
        # Check if pattern window is reached
        if len(self.daily_buffer[user_id][expert_id]) < self.pattern_window:
            return False
        
        # Check if update frequency is met
        if self.update_frequency == "weekly":
            # If weekly update, only consider memories in current week
            # Use earliest memory date as reference, not current time
            if self.daily_buffer[user_id][expert_id]:
                earliest_memory_date = self.daily_buffer[user_id][expert_id][0].date
                # Should be based on external time, not datetime.now
                # Temporarily skip time check, let caller decide whether to aggregate
                pass
        elif self.update_frequency == "daily":
            # If daily update, only consider memories in current day
            # Use earliest memory date as reference, not current time
            if self.daily_buffer[user_id][expert_id]:
                earliest_memory_date = self.daily_buffer[user_id][expert_id][0].date
                # Should be based on external time, not datetime.now
                # Temporarily skip time check, let caller decide whether to aggregate
                pass
        
        return True
    
    async def _generate_weekly_memory(self, user_id: str, expert_id: str):
        """Generate weekly memory"""
        daily_memories = self.daily_buffer[user_id][expert_id]
        
        if not daily_memories:
            raise ValueError("No available daily memories to generate weekly report")
        
        # Use earliest memory date as week start time
        earliest_memory = min(daily_memories, key=lambda x: x.date)
        week_start_date = earliest_memory.date
        
        # Calculate week end time (7 days later)
        week_end_date = week_start_date + timedelta(days=6)
        
        # Extract key topics
        key_topics = self._extract_key_topics(daily_memories)
        
        # Analyze interaction patterns
        interaction_patterns = await self._analyze_interaction_patterns(daily_memories)
        
        # Analyze knowledge evolution
        knowledge_evolution = await self._analyze_knowledge_evolution(daily_memories)
        
        # Analyze trends
        trend_analysis = await self._analyze_trends(daily_memories, knowledge_evolution)
        
        # Calculate importance score
        importance_score = await self._calculate_importance_score(daily_memories, trend_analysis)
        
        # Create weekly memory object
        new_weekly_memory = WeeklyMemory(
            id=str(uuid.uuid4()),
            user_id=user_id,
            expert_id=expert_id,
            week_start=week_start_date,
            week_end=week_end_date,
            summary=f"User {user_id} and expert {expert_id} interaction summary for this week",
            key_topics=key_topics,
            interaction_patterns=interaction_patterns,
            knowledge_evolution=knowledge_evolution,
            daily_memories=daily_memories,
            trend_analysis=trend_analysis,
            importance_score=importance_score,
            created_at=earliest_memory.created_at if hasattr(earliest_memory, 'created_at') else week_start_date,
            metadata={
                'user_id': user_id,
                'expert_id': expert_id,
                'update_frequency': self.update_frequency,
                'pattern_window': self.pattern_window
            }
        )
        
        # Update storage
        self.weekly_memories[f"{user_id}:{expert_id}:{new_weekly_memory.week_start.strftime('%Y%m%d')}"] = new_weekly_memory
        
        # Clean up daily buffer
        self.daily_buffer[user_id][expert_id] = []
        
        self.logger.info(f"Generated weekly memory {new_weekly_memory.id}, user: {user_id}, expert: {expert_id}")
    
    def _extract_key_topics(self, daily_memories: List[DailyMemory]) -> List[str]:
        """Extract key topics"""
        topic_counter = Counter()
        
        for memory in daily_memories:
            if hasattr(memory, 'key_topics') and memory.key_topics:
                for topic in memory.key_topics:
                    topic_counter[topic] += 1
        
        # Select high-frequency topics as key topics
        key_topics = [topic for topic, count in topic_counter.most_common(10) if count >= 2]
        return key_topics
    
    async def _analyze_interaction_patterns(self, daily_memories: List[DailyMemory]) -> List[InteractionPattern]:
        """Analyze interaction patterns"""
        patterns = []
        
        # Analyze interaction frequency
        interaction_counts = defaultdict(int)
        for memory in daily_memories:
            for interaction in memory.metadata.get('interactions', []) if hasattr(memory, 'metadata') and memory.metadata else []:
                interaction_counts[interaction.interaction_type] += 1
        
        # Simulate LLM output
        for interaction_type, count in interaction_counts.items():
            patterns.append(InteractionPattern(
                pattern_type=interaction_type,
                description=f"User tends to {interaction_type} interaction",
                frequency=count / len(daily_memories),
                confidence=0.9, # Simulate confidence
                examples=[f"User performed {interaction_type} interaction on {memory.date}"],
                metadata={
                    'interaction_type': interaction_type,
                    'count': count
                }
            ))
        
        return patterns
    
    async def _analyze_knowledge_evolution(self, daily_memories: List[DailyMemory]) -> List[KnowledgeEvolution]:
        """Analyze knowledge evolution"""
        evolution_data = defaultdict(lambda: {
            'emerging_count': 0,
            'growing_count': 0,
            'declining_count': 0,
            'stable_count': 0,
            'total_strength': 0.0
        })
        
        for memory in daily_memories:
            if hasattr(memory, 'knowledge_evolution') and memory.knowledge_evolution:
                for evolution in memory.knowledge_evolution:
                    if hasattr(evolution, 'topic') and hasattr(evolution, 'evolution_type') and hasattr(evolution, 'trend_strength'):
                        evolution_data[evolution.topic][evolution.evolution_type] += 1
                        evolution_data[evolution.topic]['total_strength'] += evolution.trend_strength
        
        evolutions = []
        for topic, data in evolution_data.items():
            total_strength = data['total_strength']
            total_count = sum(data.values())
            
            # Simulate LLM prediction
            prediction = "stable"
            if total_strength > 0.5:
                prediction = "growth"
            elif total_strength < -0.5:
                prediction = "decline"
            
            evolutions.append(KnowledgeEvolution(
                topic=topic,
                evolution_type=max(data, key=data.get), # Get the most obvious trend type
                trend_strength=total_strength / total_count if total_count > 0 else 0.0,
                key_milestones=[], # Simulate milestones
                prediction=prediction,
                metadata={
                    'total_strength': total_strength,
                    'total_count': total_count
                }
            ))
        
        return evolutions
    
    async def _analyze_trends(self, daily_memories: List[DailyMemory], knowledge_evolution: List[KnowledgeEvolution]) -> Dict[str, Any]:
        """Analyze trends"""
        trends = {}
        
        # Simulate LLM analysis
        trends['interaction_trend'] = "Interaction frequency remains stable"
        trends['knowledge_growth'] = "Knowledge mastery level remains stable"
        
        # More complex analysis can be based on knowledge_evolution
        if knowledge_evolution:
            avg_strength = sum(e.trend_strength for e in knowledge_evolution) / len(knowledge_evolution)
            if avg_strength > 0.3:
                trends['knowledge_growth'] = "User knowledge mastery level shows growth trend"
            elif avg_strength < -0.3:
                trends['knowledge_growth'] = "User knowledge mastery level shows decline trend"
        
        return trends
    
    async def _calculate_importance_score(self, daily_memories: List[DailyMemory], trend_analysis: Dict[str, Any]) -> float:
        """Calculate importance score"""
        # Simulate LLM scoring
        score = 0.5
        
        # Consider interaction frequency
        interaction_count = sum(len(m.metadata.get('interactions', [])) for m in daily_memories if hasattr(m, 'metadata') and m.metadata)
        if interaction_count > 5:
            score += 0.1
        elif interaction_count < 2:
            score -= 0.05
        
        # Consider knowledge evolution strength
        if trend_analysis.get('knowledge_growth') and 'growth' in trend_analysis['knowledge_growth']:
            score += 0.1
        elif trend_analysis.get('knowledge_growth') and 'decline' in trend_analysis['knowledge_growth']:
            score -= 0.05
        
        # Consider time decay
        time_decay = self._calculate_time_decay(daily_memories[0].date)
        score *= time_decay
        
        return min(max(score, 0.0), 1.0)
    
    def _calculate_time_decay(self, date: datetime) -> float:
        """Calculate time decay factor"""
        # Use external time instead of current time
        # Reference time needs to be passed in, temporarily return fixed value
        # In actual use, decay should be calculated based on external time
        return 1.0  # Temporarily return 1.0 to avoid using datetime.now
    
    async def get_weekly_memory(self, user_id: str, expert_id: str, week_start: datetime) -> Optional[WeeklyMemory]:
        """Get weekly memory for specified week"""
        key = f"{user_id}:{expert_id}:{week_start.strftime('%Y%m%d')}"
        return self.weekly_memories.get(key)
    
    async def get_recent_weekly_memories(self, user_id: str, expert_id: str, count: int = 5) -> List[WeeklyMemory]:
        """Get recent weekly memories"""
        memories = []
        for key, memory in self.weekly_memories.items():
            if memory.user_id == user_id and memory.expert_id == expert_id:
                memories.append(memory)
        
        # Sort by time and return most recent
        memories.sort(key=lambda x: x.created_at, reverse=True)
        return memories[:count]
    
    def get_multi_expert_state(self) -> Dict[str, Any]:
        """Get multi-expert state"""
        return {
            "daily_buffer_size": sum(len(expert_memories) for user_memories in self.daily_buffer.values() 
                                   for expert_memories in user_memories.values()),
            "weekly_memories_count": len(self.weekly_memories),
            "pattern_window": self.pattern_window,
            "update_frequency": self.update_frequency
        }
    
    async def generate_weekly_memory(self, user_id: str, expert_id: str, 
                                   l3_memories: List[Any], week_start: datetime) -> WeeklyMemory:
        """Generate weekly memory
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            l3_memories: List of L3 memories
            week_start: Week start time
            
        Returns:
            Weekly memory object
        """
        try:
            # Convert to DailyMemory format
            daily_memories = []
            for memory in l3_memories:
                if hasattr(memory, 'summary'):
                    # Use memory timestamp, if not available use week start time
                    memory_timestamp = memory.timestamp if hasattr(memory, 'timestamp') else week_start
                    memory_created_at = memory.created_at if hasattr(memory, 'created_at') else week_start
                    
                    daily_memory = DailyMemory(
                        id=memory.memory_id if hasattr(memory, 'memory_id') else str(uuid.uuid4()),
                        user_id=user_id,
                        expert_id=expert_id,
                        date=memory_timestamp,
                        summary=memory.summary,
                        key_topics=memory.metadata.get('key_topics', []) if hasattr(memory, 'metadata') else [],
                        interaction_patterns=[],
                        knowledge_evolution=[],
                        session_memories=[],
                        trend_analysis={},
                        importance_score=memory.metadata.get('importance_score', 0.5) if hasattr(memory, 'metadata') else 0.5,
                        created_at=memory_created_at,
                        metadata=memory.metadata if hasattr(memory, 'metadata') else {}
                    )
                    daily_memories.append(daily_memory)
            
            # Analyze interaction patterns
            interaction_patterns = await self._analyze_interaction_patterns(daily_memories)
            
            # Analyze knowledge evolution
            knowledge_evolution = await self._analyze_knowledge_evolution(daily_memories)
            
            # Analyze trends
            trend_analysis = await self._analyze_trends(daily_memories, knowledge_evolution)
            
            # Extract key topics
            key_topics = self._extract_key_topics(daily_memories)
            
            # Generate weekly summary
            weekly_summary = f"Weekly memory: {week_start.strftime('%Y-%m-%d')} to {(week_start + timedelta(days=6)).strftime('%Y-%m-%d')}, containing {len(daily_memories)} daily memories"
            
            # Calculate importance
            importance_score = await self._calculate_importance_score(daily_memories, trend_analysis)
            
            # Create weekly memory object
            weekly_memory = WeeklyMemory(
                id=str(uuid.uuid4()),
                user_id=user_id,
                expert_id=expert_id,
                week_start=week_start,
                week_end=week_start + timedelta(days=6),
                summary=weekly_summary,
                key_topics=key_topics,
                interaction_patterns=interaction_patterns,
                knowledge_evolution=knowledge_evolution,
                daily_memories=daily_memories,
                trend_analysis=trend_analysis,
                importance_score=importance_score,
                created_at=week_start,  # Use week start time as creation time
                metadata={
                    "l3_daily_count": len(daily_memories),
                    "week_start": week_start.isoformat()
                }
            )
            
            self.logger.info(f"Generated weekly memory: {user_id}:{expert_id}, daily count: {len(daily_memories)}")
            return weekly_memory
            
        except Exception as e:
            self.logger.error(f"Failed to generate weekly memory: {e}")
            # Return default weekly memory
            return WeeklyMemory(
                id=str(uuid.uuid4()),
                user_id=user_id,
                expert_id=expert_id,
                week_start=week_start,
                week_end=week_start + timedelta(days=6),
                summary=f"Weekly memory: {week_start.strftime('%Y-%m-%d')}",
                key_topics=[],
                interaction_patterns=[],
                knowledge_evolution=[],
                daily_memories=[],
                trend_analysis={},
                importance_score=0.5,
                created_at=week_start,  # Use week start time as creation time
                metadata={"error": str(e)}
            )
    
    async def generate_weekly_memory_with_history(self, user_id: str, expert_id: str, 
                                                 l3_memories: List[Any], week_start: datetime,
                                                 history_l4_memories: List[Any]) -> WeeklyMemory:
        """Generate weekly memory with progressive summary using historical memories
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            l3_memories: List of L3 memories
            week_start: Week start time
            history_l4_memories: List of historical L4 memories (retrieved from database)
            
        Returns:
            Weekly memory object
        """
        try:
            # Convert to DailyMemory format
            daily_memories = []
            for memory in l3_memories:
                if hasattr(memory, 'summary'):
                    # Use memory timestamp, if not available use week start time
                    memory_timestamp = memory.timestamp if hasattr(memory, 'timestamp') else week_start
                    memory_created_at = memory.created_at if hasattr(memory, 'created_at') else week_start
                    
                    daily_memory = DailyMemory(
                        id=memory.memory_id if hasattr(memory, 'memory_id') else str(uuid.uuid4()),
                        user_id=user_id,
                        expert_id=expert_id,
                        date=memory_timestamp,
                        summary=memory.summary,
                        key_topics=memory.metadata.get('key_topics', []) if hasattr(memory, 'metadata') else [],
                        interaction_patterns=[],
                        knowledge_evolution=[],
                        session_memories=[],
                        trend_analysis={},
                        importance_score=memory.metadata.get('importance_score', 0.5) if hasattr(memory, 'metadata') else 0.5,
                        created_at=memory_created_at,
                        metadata=memory.metadata if hasattr(memory, 'metadata') else {}
                    )
                    daily_memories.append(daily_memory)
            
            # Analyze interaction patterns
            interaction_patterns = await self._analyze_interaction_patterns(daily_memories)
            
            # Analyze knowledge evolution
            knowledge_evolution = await self._analyze_knowledge_evolution(daily_memories)
            
            # Analyze trends
            trend_analysis = await self._analyze_trends(daily_memories, knowledge_evolution)
            
            # Extract key topics
            key_topics = self._extract_key_topics(daily_memories)
            
            # Generate progressive weekly summary
            if history_l4_memories:
                # Build historical context
                history_context = []
                for hist_memory in history_l4_memories[-3:]:  # Last 3 L4 memories
                    if hasattr(hist_memory, 'summary'):
                        history_context.append(f"Historical weekly summary: {hist_memory.summary}")
                    elif isinstance(hist_memory, dict) and 'summary' in hist_memory:
                        history_context.append(f"Historical weekly summary: {hist_memory['summary']}")
                
                # Use progressive summary
                weekly_summary = await self._generate_progressive_weekly_summary(
                    daily_memories, interaction_patterns, knowledge_evolution, history_context, week_start
                )
                self.logger.info(f"Using progressive weekly summary, historical L4 memory count: {len(history_l4_memories)}")
            else:
                # Use independent summary
                weekly_summary = f"Weekly memory: {week_start.strftime('%Y-%m-%d')} to {(week_start + timedelta(days=6)).strftime('%Y-%m-%d')}, containing {len(daily_memories)} daily memories"
                self.logger.info("Using independent weekly summary")
            
            # Calculate importance
            importance_score = await self._calculate_importance_score(daily_memories, trend_analysis)
            
            # Create weekly memory
            weekly_memory = WeeklyMemory(
                id=str(uuid.uuid4()),
                user_id=user_id,
                expert_id=expert_id,
                week_start=week_start,
                week_end=week_start + timedelta(days=6),
                summary=weekly_summary,
                key_topics=key_topics,
                interaction_patterns=interaction_patterns,
                knowledge_evolution=knowledge_evolution,
                daily_memories=daily_memories,
                trend_analysis=trend_analysis,
                importance_score=importance_score,
                created_at=datetime.now(),
                metadata={
                    "l3_daily_count": len(daily_memories),
                    "week_start": week_start.isoformat(),
                    "history_memory_count": len(history_l4_memories),
                    "is_progressive_summary": len(history_l4_memories) > 0
                }
            )
            
            self.logger.info(f"Generated weekly memory: {user_id}:{expert_id}, daily count: {len(daily_memories)}")
            return weekly_memory
            
        except Exception as e:
            self.logger.error(f"Failed to generate weekly memory: {e}")
            # Return default weekly memory
            return WeeklyMemory(
                id=str(uuid.uuid4()),
                user_id=user_id,
                expert_id=expert_id,
                week_start=week_start,
                week_end=week_start + timedelta(days=6),
                summary=f"Weekly memory: {week_start.strftime('%Y-%m-%d')}",
                key_topics=[],
                interaction_patterns=[],
                knowledge_evolution=[],
                daily_memories=[],
                trend_analysis={},
                importance_score=0.5,
                created_at=datetime.now(),
                metadata={"error": str(e)}
            )
    
    async def _generate_progressive_weekly_summary(self, daily_memories: List[DailyMemory], 
                                                  patterns: List[InteractionPattern], 
                                                  evolutions: List[KnowledgeEvolution],
                                                  history_context: List[str], week_start: datetime) -> str:
        """Generate progressive weekly summary
        
        Args:
            daily_memories: List of daily memories
            patterns: List of interaction patterns
            evolutions: List of knowledge evolution
            history_context: List of historical context
            week_start: Week start time
            
        Returns:
            Progressive weekly summary
        """
        try:
            # Build current weekly content
            current_summaries = [d.summary for d in daily_memories]
            current_content = f"Current weekly report contains {len(daily_memories)} daily memories"
            
            # Build progressive summary prompt
            progressive_prompt = f"""
Based on the following historical weekly memories and current L3 daily memories of the weekly report, generate a more comprehensive weekly-level memory:

Historical weekly memories:
{chr(10).join(history_context)}

Current L3 daily memories of the weekly report:
{chr(10).join([f"- {summary}" for summary in current_summaries])}

Please generate a weekly-level memory considering historical context:
"""
            
            # Use MockLLMAdapter to generate progressive weekly memory
            from llm.mock_adapter import MockLLMAdapter
            
            llm_service = MockLLMAdapter()
            enhanced_weekly_summary = await llm_service.generate_text(progressive_prompt)
            
            return enhanced_weekly_summary
            
        except Exception as e:
            self.logger.error(f"Failed to generate progressive weekly summary: {e}")
            return f"Weekly memory: {week_start.strftime('%Y-%m-%d')} to {(week_start + timedelta(days=6)).strftime('%Y-%m-%d')}, containing {len(daily_memories)} daily memories"
