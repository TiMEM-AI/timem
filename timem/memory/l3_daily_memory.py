"""
TiMem L3 Daily-level Memory Implementation
Handles single-user-single-expert-multi-session daily memory aggregation
"""

import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from collections import defaultdict, Counter

from timem.utils import time_utils
from timem.utils.text_processing import LLMTextProcessor
from timem.utils.logging import get_logger
from timem.memory.l2_session_memory import SessionMemory


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
class DailyMemory:
    """Daily Memory"""
    id: str
    user_id: str
    expert_id: str
    date: datetime
    summary: str
    key_topics: List[str]
    interaction_patterns: List[InteractionPattern]
    knowledge_evolution: List[KnowledgeEvolution]
    session_memories: List[SessionMemory]
    trend_analysis: Dict[str, Any]
    importance_score: float
    created_at: datetime
    metadata: Dict[str, Any] = None

class L3DailyMemory:
    """L3 Daily-level Memory Processor"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.pattern_window = config.get("pattern_window", 7)
        self.trend_analysis_enabled = config.get("trend_analysis", True)
        self.update_frequency = config.get("update_frequency", "daily")
        self.gamma = config.get("gamma", 0.8)  # Time decay factor
        
        self.text_processor = LLMTextProcessor()
        self.logger = get_logger(__name__)
        
        # Current daily report state
        self.session_buffer: Dict[str, List[SessionMemory]] = {}  # key: user_id:expert_id
        self.daily_memories: Dict[str, DailyMemory] = {}  # key: user_id:expert_id:date
        
        self.logger.info(f"Initialized L3 daily-level memory processor, pattern window: {self.pattern_window} days")
    
    async def add_session_memory(self, session_memory: SessionMemory) -> bool:
        """
        Add session memory, may trigger daily report generation
        
        Args:
            session_memory: Session memory object
            
        Returns:
            Whether daily report generation was triggered
        """
        user_expert_key = f"{session_memory.user_id}:{session_memory.expert_id}"
        
        if user_expert_key not in self.session_buffer:
            self.session_buffer[user_expert_key] = []
        
        self.session_buffer[user_expert_key].append(session_memory)
        self.logger.info(f"Added session memory {session_memory.id}, user: {session_memory.user_id}, expert: {session_memory.expert_id}")
        
        # Sort by time
        self.session_buffer[user_expert_key].sort(key=lambda x: x.session_start)
        
        # Check if daily report generation is needed
        if len(self.session_buffer[user_expert_key]) >= self.pattern_window:
            await self._generate_daily_memory(session_memory.user_id, session_memory.expert_id)
            return True
        
        return False
    
    async def _generate_daily_memory(self, user_id: str, expert_id: str):
        """Generate daily memory"""
        user_expert_key = f"{user_id}:{expert_id}"
        session_memories = self.session_buffer.get(user_expert_key, [])
        
        if not session_memories:
            return
        
        # Get recent 7 days of sessions
        recent_sessions = session_memories[-self.pattern_window:]
        
        # Determine daily report time range
        daily_date = recent_sessions[0].session_start
        
        # Analyze interaction patterns
        interaction_patterns = await self._analyze_interaction_patterns(recent_sessions)
        
        # Track knowledge evolution
        knowledge_evolution = await self._track_knowledge_evolution(recent_sessions)
        
        # Perform trend analysis
        trend_analysis = await self._perform_trend_analysis(recent_sessions)
        
        # Aggregate key topics
        key_topics = await self._aggregate_daily_topics(recent_sessions)
        
        # Generate daily summary
        daily_summary = await self._generate_daily_summary(recent_sessions, interaction_patterns, knowledge_evolution)
        
        # Calculate daily importance
        importance_score = await self._calculate_daily_importance(recent_sessions, interaction_patterns, knowledge_evolution)
        
        # Create daily memory
        daily_memory = DailyMemory(
            id=str(uuid.uuid4()),
            user_id=user_id,
            expert_id=expert_id,
            date=daily_date,
            summary=daily_summary,
            key_topics=key_topics,
            interaction_patterns=interaction_patterns,
            knowledge_evolution=knowledge_evolution,
            session_memories=recent_sessions,
            trend_analysis=trend_analysis,
            importance_score=importance_score,
            created_at=daily_date,  # Use daily report date as creation time
            metadata={
                "session_count": len(recent_sessions),
                "total_interactions": sum(len(s.metadata.get('interactions', [])) for s in recent_sessions if hasattr(s, 'metadata') and s.metadata),
                "avg_session_importance": sum(s.importance_score for s in recent_sessions) / len(recent_sessions),
                "pattern_count": len(interaction_patterns),
                "evolution_count": len(knowledge_evolution)
            }
        )
        
        # Store daily memory
        day_key = f"{user_id}:{expert_id}:{daily_date.strftime('%Y-%m-%d')}"
        self.daily_memories[day_key] = daily_memory
        
        # Clean up processed sessions (keep last few days for pattern continuity)
        if len(session_memories) > self.pattern_window:
            self.session_buffer[user_expert_key] = session_memories[-(self.pattern_window-3):]
        
        self.logger.info(f"Generated daily memory {daily_memory.id}, user: {user_id}, expert: {expert_id}")
    
    async def _analyze_interaction_patterns(self, session_memories: List[SessionMemory]) -> List[InteractionPattern]:
        """Analyze interaction patterns"""
        patterns = []
        
        # 1. Time pattern analysis
        time_pattern = await self._analyze_time_patterns(session_memories)
        if time_pattern:
            patterns.append(time_pattern)
        
        # 2. Topic pattern analysis
        topic_pattern = await self._analyze_topic_patterns(session_memories)
        if topic_pattern:
            patterns.append(topic_pattern)
        
        # 3. Intensity pattern analysis
        intensity_pattern = await self._analyze_intensity_patterns(session_memories)
        if intensity_pattern:
            patterns.append(intensity_pattern)
        
        # 4. Cyclical pattern analysis
        cyclical_pattern = await self._analyze_cyclical_patterns(session_memories)
        if cyclical_pattern:
            patterns.append(cyclical_pattern)
        
        return patterns
    
    async def _analyze_time_patterns(self, session_memories: List[SessionMemory]) -> Optional[InteractionPattern]:
        """Analyze time patterns"""
        if not session_memories:
            return None
        
        # Analyze daily interaction time distribution
        peak_times = []
        for session in session_memories:
            # Get interaction pattern information from session metadata, skip if not available
            if hasattr(session, 'metadata') and session.metadata and session.metadata.get("interaction_patterns", {}).get("peak_interaction_time"):
                peak_times.append(session.metadata["interaction_patterns"]["peak_interaction_time"])
        
        if not peak_times:
            return None
        
        # Count most common interaction times
        time_counter = Counter(peak_times)
        most_common_time, frequency = time_counter.most_common(1)[0]
        
        confidence = frequency / len(peak_times)
        
        if confidence > 0.3:  # At least 30% consistency
            return InteractionPattern(
                pattern_type="temporal",
                description=f"User tends to interact at {most_common_time}",
                frequency=frequency,
                confidence=confidence,
                examples=[f"Date: {s.created_at.date()}, Time: {s.metadata.get('interaction_patterns', {}).get('peak_interaction_time', 'N/A')}" 
                         for s in session_memories if s.metadata and s.metadata.get("interaction_patterns", {}).get('peak_interaction_time') == most_common_time],
                metadata={
                    "peak_time": most_common_time,
                    "frequency_distribution": dict(time_counter)
                }
            )
        
        return None
    
    async def _analyze_topic_patterns(self, session_memories: List[SessionMemory]) -> Optional[InteractionPattern]:
        """Analyze topic patterns"""
        if not session_memories:
            return None
        
        # Collect all topics
        all_topics = []
        for session in session_memories:
            if hasattr(session, 'key_topics') and session.key_topics:
                all_topics.extend(session.key_topics)
        
        if not all_topics:
            return None
        
        # Analyze topic persistence
        topic_counter = Counter(all_topics)
        persistent_topics = [topic for topic, count in topic_counter.items() if count >= 3]
        
        if persistent_topics:
            return InteractionPattern(
                pattern_type="thematic",
                description=f"Persistent topics: {', '.join(persistent_topics[:3])}",
                frequency=len(persistent_topics),
                confidence=len(persistent_topics) / len(set(all_topics)),
                examples=[f"Topic: {topic}, Occurrences: {count}" for topic, count in topic_counter.most_common(5)],
                metadata={
                    "persistent_topics": persistent_topics,
                    "topic_distribution": dict(topic_counter)
                }
            )
        
        return None
    
    async def _analyze_cyclical_patterns(self, session_memories: List[SessionMemory]) -> Optional[InteractionPattern]:
        """Analyze cyclical patterns"""
        if len(session_memories) < 7:
            return None
        
        # Analyze weekly pattern
        weekday_activity = defaultdict(list)
        for session in session_memories:
            weekday = session.session_start.weekday()  # 0=Monday, 6=Sunday
            weekday_activity[weekday].append(session.importance_score)
        
        # Calculate average activity for each weekday
        weekday_avg = {}
        for weekday, scores in weekday_activity.items():
            weekday_avg[weekday] = sum(scores) / len(scores)
        
        if len(weekday_avg) >= 3:  # At least 3 days of data
            weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            max_day = max(weekday_avg.keys(), key=lambda x: weekday_avg[x])
            min_day = min(weekday_avg.keys(), key=lambda x: weekday_avg[x])
            
            pattern_strength = weekday_avg[max_day] - weekday_avg[min_day]
            
            if pattern_strength > 0.2:  # Significant difference
                return InteractionPattern(
                    pattern_type="cyclical",
                    description=f"Cyclical pattern: {weekday_names[max_day]} most active, {weekday_names[min_day]} least active",
                    frequency=pattern_strength,
                    confidence=pattern_strength / max(weekday_avg.values()),
                    examples=[f"{weekday_names[day]}: {score:.2f}" for day, score in weekday_avg.items()],
                    metadata={
                        "weekday_pattern": weekday_avg,
                        "peak_day": max_day,
                        "low_day": min_day,
                        "pattern_strength": pattern_strength
                    }
                )
        
        return None
    
    async def _track_knowledge_evolution(self, session_memories: List[SessionMemory]) -> List[KnowledgeEvolution]:
        """Track knowledge evolution"""
        evolutions = []
        
        # Collect timeline for all topics
        topic_timeline = defaultdict(list)
        for i, session in enumerate(session_memories):
            for topic in session.key_topics:
                topic_timeline[topic].append({
                    "day": i,
                    "date": session.session_start,
                    "importance": session.importance_score,
                    "present": True
                })
        
        # Analyze evolution for each topic
        for topic, timeline in topic_timeline.items():
            evolution = await self._analyze_topic_evolution(topic, timeline, session_memories)
            if evolution:
                evolutions.append(evolution)
        
        return evolutions
    
    async def _analyze_topic_evolution(self, topic: str, timeline: List[Dict[str, Any]], 
                                     session_memories: List[SessionMemory]) -> Optional[KnowledgeEvolution]:
        """Analyze topic evolution"""
        if len(timeline) < 2:
            return None
        
        # Calculate trend strength
        days = [entry["day"] for entry in timeline]
        importances = [entry["importance"] for entry in timeline]
        
        # Simple linear trend analysis
        n = len(days)
        if n < 3:
            return None
        
        # Calculate correlation coefficient
        mean_day = sum(days) / n
        mean_importance = sum(importances) / n
        
        numerator = sum((days[i] - mean_day) * (importances[i] - mean_importance) for i in range(n))
        denominator = (sum((days[i] - mean_day) ** 2 for i in range(n)) * 
                      sum((importances[i] - mean_importance) ** 2 for i in range(n))) ** 0.5
        
        if denominator == 0:
            return None
        
        correlation = numerator / denominator
        
        # Determine evolution type
        if correlation > 0.3:
            evolution_type = "growing"
            prediction = f"Topic '{topic}' shows growth trend and is expected to continue receiving attention"
        elif correlation < -0.3:
            evolution_type = "declining"
            prediction = f"Topic '{topic}' shows declining trend and attention may further decrease"
        else:
            evolution_type = "stable"
            prediction = f"Topic '{topic}' remains stable and continues to receive attention"
        
        # Identify key milestones
        milestones = []
        for entry in timeline:
            if entry["importance"] > 0.7:  # High importance event
                milestones.append({
                    "date": entry["date"].isoformat(),
                    "event": f"Topic '{topic}' reached high importance",
                    "importance": entry["importance"]
                })
        
        return KnowledgeEvolution(
            topic=topic,
            evolution_type=evolution_type,
            trend_strength=abs(correlation),
            key_milestones=milestones,
            prediction=prediction,
            metadata={
                "timeline": timeline,
                "correlation": correlation,
                "appearances": len(timeline),
                "avg_importance": mean_importance
            }
        )
    
    async def _perform_trend_analysis(self, session_memories: List[SessionMemory]) -> Dict[str, Any]:
        """Perform trend analysis"""
        if not session_memories:
            return {}
        
        # Overall trend analysis
        importance_trend = [session.importance_score for session in session_memories]
        session_trend = [len(session.metadata.get('interactions', [])) for session in session_memories if hasattr(session, 'metadata') and session.metadata]
        
        # Calculate trend direction
        importance_direction = self._calculate_trend_direction(importance_trend)
        session_direction = self._calculate_trend_direction(session_trend)
        
        # Topic diversity trend
        diversity_trend = []
        for session in session_memories:
            diversity_trend.append(len(session.key_topics))
        
        diversity_direction = self._calculate_trend_direction(diversity_trend)
        
        return {
            "importance_trend": {
                "direction": importance_direction,
                "values": importance_trend,
                "analysis": self._interpret_trend(importance_direction, "importance")
            },
            "session_trend": {
                "direction": session_direction,
                "values": session_trend,
                "analysis": self._interpret_trend(session_direction, "session count")
            },
            "diversity_trend": {
                "direction": diversity_direction,
                "values": diversity_trend,
                "analysis": self._interpret_trend(diversity_direction, "topic diversity")
            },
            "overall_analysis": await self._generate_trend_analysis(
                importance_direction, session_direction, diversity_direction
            )
        }
    
    def _calculate_trend_direction(self, values: List[float]) -> str:
        """Calculate trend direction"""
        if len(values) < 2:
            return "stable"
        
        # Simple trend calculation
        first_half = values[:len(values)//2]
        second_half = values[len(values)//2:]
        
        first_avg = sum(first_half) / len(first_half)
        second_avg = sum(second_half) / len(second_half)
        
        diff = second_avg - first_avg
        
        if diff > 0.1:
            return "increasing"
        elif diff < -0.1:
            return "decreasing"
        else:
            return "stable"
    
    def _interpret_trend(self, direction: str, metric: str) -> str:
        """Interpret trend"""
        if direction == "increasing":
            return f"{metric} shows upward trend"
        elif direction == "decreasing":
            return f"{metric} shows downward trend"
        else:
            return f"{metric} remains stable"
    
    async def _generate_trend_analysis(self, importance_dir: str, session_dir: str, diversity_dir: str) -> str:
        """Generate trend analysis summary"""
        analyses = []
        
        if importance_dir == "increasing":
            analyses.append("Interaction importance continues to increase")
        elif importance_dir == "decreasing":
            analyses.append("Interaction importance has declined")
        
        if session_dir == "increasing":
            analyses.append("Interaction frequency increases")
        elif session_dir == "decreasing":
            analyses.append("Interaction frequency decreases")
        
        if diversity_dir == "increasing":
            analyses.append("Discussion topics become more diverse")
        elif diversity_dir == "decreasing":
            analyses.append("Discussion topics tend to concentrate")
        
        if not analyses:
            return "All metrics remain stable"
        
        return ", ".join(analyses)
    
    async def _aggregate_daily_topics(self, session_memories: List[SessionMemory]) -> List[str]:
        """Aggregate daily topics"""
        all_topics = []
        for session in session_memories:
            all_topics.extend(session.key_topics)
        
        # Count topic frequency
        topic_counter = Counter(all_topics)
        
        # Select high-frequency topics
        daily_topics = []
        for topic, count in topic_counter.most_common(10):
            if count >= 3:  # Appear at least 3 times
                daily_topics.append(topic)
        
        return daily_topics
    
    async def _generate_daily_summary(self, session_memories: List[SessionMemory], 
                                     patterns: List[InteractionPattern], 
                                     evolutions: List[KnowledgeEvolution]) -> str:
        """Generate daily summary"""
        # Construct daily summary prompt
        session_summaries = [f"Date {s.session_start.date()}: {s.summary}" for s in session_memories]
        pattern_descriptions = [p.description for p in patterns]
        evolution_descriptions = [f"{e.topic}: {e.prediction}" for e in evolutions]
        
        prompt = f"""
        Based on the following information, generate today's interaction daily report:
        
        Today's session summary:
        {chr(10).join(session_summaries)}
        
        Identified interaction patterns:
        {chr(10).join(pattern_descriptions)}
        
        Knowledge evolution trends:
        {chr(10).join(evolution_descriptions)}
        
        Please generate a comprehensive daily report containing:
        1. Overall review of today's interactions
        2. Analysis of main interaction patterns
        3. Summary of knowledge evolution trends
        4. Next week's predictions and recommendations
        
        Keep length within 600 words.
        """
        
        # Call LLM to generate daily report
        daily_summary = await self._call_llm_summarize(prompt)
        return daily_summary
    
    async def _calculate_daily_importance(self, session_memories: List[SessionMemory],
                                         patterns: List[InteractionPattern],
                                         evolutions: List[KnowledgeEvolution]) -> float:
        """Calculate daily importance"""
        if not session_memories:
            return 0.0
        
        # Calculate importance based on multiple factors
        factors = {
            "avg_session_importance": sum(s.importance_score for s in session_memories) / len(session_memories),
            "pattern_richness": min(len(patterns) / 4, 1.0),
            "evolution_activity": min(len(evolutions) / 5, 1.0),
            "consistency": self._calculate_daily_consistency(session_memories),
        }
        
        # Weighted calculation
        importance = (
            factors["avg_session_importance"] * 0.4 +
            factors["pattern_richness"] * 0.2 +
            factors["evolution_activity"] * 0.2 +
            factors["consistency"] * 0.2
        )
        
        return min(importance, 1.0)
    
    def _calculate_daily_consistency(self, session_memories: List[SessionMemory]) -> float:
        """Calculate daily consistency"""
        if len(session_memories) < 2:
            return 1.0
        
        # Consistency based on session importance
        importance_scores = [s.importance_score for s in session_memories]
        mean_importance = sum(importance_scores) / len(importance_scores)
        variance = sum((score - mean_importance) ** 2 for score in importance_scores) / len(importance_scores)
        
        # Consistency = 1 - normalized variance
        consistency = 1 - min(variance, 1.0)
        return consistency
    
    async def _call_llm_summarize(self, prompt: str) -> str:
        """Call LLM for summarization (placeholder implementation)"""
        # Should call actual LLM API here
        # Temporarily return simplified summary
        lines = prompt.split('\n')
        content_lines = [line for line in lines if line.strip() and not line.startswith('Based')]
        
        if content_lines:
            summary_lines = content_lines[:6]
            return "AI Daily Report: " + " ".join(summary_lines)[:500]
        
        return "No daily report content"
    
    async def get_daily_memory(self, user_id: str, expert_id: str, date: datetime) -> Optional[DailyMemory]:
        """Get daily memory for specified date"""
        day_key = f"{user_id}:{expert_id}:{date.strftime('%Y-%m-%d')}"
        return self.daily_memories.get(day_key)
    
    async def search_daily_memories(self, user_id: str, expert_id: str, 
                                   days: int = 7, reference_date: Optional[datetime] = None) -> List[DailyMemory]:
        """Search daily memories for recent days"""
        results = []
        # Use provided reference date, or use current time if not provided
        current_day = reference_date or datetime.now()
        
        for i in range(days):
            day_date = current_day - timedelta(days=i)
            day_key = f"{user_id}:{expert_id}:{day_date.strftime('%Y-%m-%d')}"
            if day_key in self.daily_memories:
                results.append(self.daily_memories[day_key])
        
        return results
    
    async def get_pattern_analysis(self, user_id: str, expert_id: str, days: int = 7) -> Dict[str, Any]:
        """Get pattern analysis report"""
        daily_memories = await self.search_daily_memories(user_id, expert_id, days)
        
        if not daily_memories:
            return {"patterns": [], "analysis": "No data available"}
        
        # Aggregate all patterns
        all_patterns = []
        for daily in daily_memories:
            all_patterns.extend(daily.interaction_patterns)
        
        # Pattern classification statistics
        pattern_stats = defaultdict(list)
        for pattern in all_patterns:
            pattern_stats[pattern.pattern_type].append(pattern)
        
        # Generate analysis report
        analysis = {
            "pattern_types": dict(pattern_stats),
            "pattern_count": len(all_patterns),
            "days_analyzed": len(daily_memories),
            "dominant_patterns": self._identify_dominant_patterns(all_patterns),
            "pattern_evolution": self._analyze_pattern_evolution(daily_memories),
            "recommendations": await self._generate_pattern_recommendations(pattern_stats)
        }
        
        return analysis
    
    def _identify_dominant_patterns(self, patterns: List[InteractionPattern]) -> List[Dict[str, Any]]:
        """Identify dominant patterns"""
        if not patterns:
            return []
        
        # Sort by confidence
        sorted_patterns = sorted(patterns, key=lambda x: x.confidence, reverse=True)
        
        dominant = []
        for pattern in sorted_patterns[:5]:  # Take top 5
            dominant.append({
                "type": pattern.pattern_type,
                "description": pattern.description,
                "confidence": pattern.confidence,
                "frequency": pattern.frequency
            })
        
        return dominant
    
    def _analyze_pattern_evolution(self, daily_memories: List[DailyMemory]) -> Dict[str, Any]:
        """Analyze pattern evolution"""
        if len(daily_memories) < 2:
            return {"evolution": "insufficient_data"}
        
        # Sort by time
        sorted_memories = sorted(daily_memories, key=lambda x: x.date)
        
        # Analyze pattern changes
        pattern_changes = []
        for i in range(1, len(sorted_memories)):
            prev_patterns = {p.pattern_type for p in sorted_memories[i-1].interaction_patterns}
            curr_patterns = {p.pattern_type for p in sorted_memories[i].interaction_patterns}
            
            new_patterns = curr_patterns - prev_patterns
            lost_patterns = prev_patterns - curr_patterns
            
            if new_patterns or lost_patterns:
                pattern_changes.append({
                    "day": sorted_memories[i].date.strftime('%Y-%m-%d'),
                    "new_patterns": list(new_patterns),
                    "lost_patterns": list(lost_patterns)
                })
        
        return {
            "evolution": "analyzed",
            "changes": pattern_changes,
            "stability": len(pattern_changes) / len(sorted_memories)
        }
    
    async def _generate_pattern_recommendations(self, pattern_stats: Dict[str, List[InteractionPattern]]) -> List[str]:
        """Generate pattern recommendations"""
        recommendations = []
        
        # Generate recommendations based on pattern type
        if "temporal" in pattern_stats:
            recommendations.append("Recommend scheduling important interactions during user active hours")
        
        if "thematic" in pattern_stats:
            recommendations.append("Recommend deepening discussions around continuously focused topics")
        
        if "intensity" in pattern_stats:
            intensity_patterns = pattern_stats["intensity"]
            if any(p.metadata.get("pattern_type") == "volatile" for p in intensity_patterns):
                recommendations.append("Recommend balancing interaction intensity to avoid excessive fluctuations")
        
        if "cyclical" in pattern_stats:
            recommendations.append("Recommend adjusting service strategy based on cyclical patterns")
        
        return recommendations
    
    def get_daily_state(self) -> Dict[str, Any]:
        """Get current daily report state"""
        return {
            "session_buffer_size": sum(len(sessions) for sessions in self.session_buffer.values()),
            "daily_memories_count": len(self.daily_memories),
            "active_users": len(self.session_buffer),
            "recent_dailies": [
                {
                    "id": d.id,
                    "user_id": d.user_id,
                    "expert_id": d.expert_id,
                    "date": d.date.isoformat(),
                    "topics": d.key_topics,
                    "pattern_count": len(d.interaction_patterns),
                    "evolution_count": len(d.knowledge_evolution),
                    "importance": d.importance_score
                }
                for d in list(self.daily_memories.values())[-5:]
            ]
        }
    
    async def generate_daily_memory(self, user_id: str, expert_id: str, 
                                  l2_memories: List[Any], date: datetime) -> DailyMemory:
        """Generate daily memory
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            l2_memories: List of L2 memories
            date: Date
            
        Returns:
            Daily memory object
        """
        try:
            # Convert to SessionMemory format
            session_memories = []
            for memory in l2_memories:
                if hasattr(memory, 'summary'):
                    session_memory = SessionMemory(
                        id=memory.memory_id if hasattr(memory, 'memory_id') else str(uuid.uuid4()),
                        user_id=user_id,
                        expert_id=expert_id,
                        session_id=memory.session_id if hasattr(memory, 'session_id') else "unknown",
                        summary=memory.summary,
                        key_topics=memory.metadata.get('key_topics', []) if hasattr(memory, 'metadata') else [],
                        decision_points=memory.metadata.get('decision_points', []) if hasattr(memory, 'metadata') else [],
                        fragments=[],
                        importance_score=memory.metadata.get('importance_score', 0.5) if hasattr(memory, 'metadata') else 0.5,
                        created_at=memory.timestamp if hasattr(memory, 'timestamp') else datetime.now(),
                        metadata=memory.metadata if hasattr(memory, 'metadata') else {}
                    )
                    session_memories.append(session_memory)
            
            # Analyze interaction patterns
            interaction_patterns = await self._analyze_interaction_patterns(session_memories)
            
            # Track knowledge evolution
            knowledge_evolution = await self._track_knowledge_evolution(session_memories)
            
            # Perform trend analysis
            trend_analysis = await self._perform_trend_analysis(session_memories)
            
            # Aggregate topics
            key_topics = await self._aggregate_daily_topics(session_memories)
            
            # Generate daily summary
            daily_summary = await self._generate_daily_summary(session_memories, interaction_patterns, knowledge_evolution)
            
            # Calculate importance
            importance_score = await self._calculate_daily_importance(session_memories, interaction_patterns, knowledge_evolution)
            
            # Create daily memory
            daily_memory = DailyMemory(
                id=str(uuid.uuid4()),
                user_id=user_id,
                expert_id=expert_id,
                date=date,
                summary=daily_summary,
                key_topics=key_topics,
                interaction_patterns=interaction_patterns,
                knowledge_evolution=knowledge_evolution,
                session_memories=session_memories,
                trend_analysis=trend_analysis,
                importance_score=importance_score,
                created_at=datetime.now(),
                metadata={
                    "l2_session_count": len(session_memories),
                    "date": date.isoformat()
                }
            )
            
            self.logger.info(f"Generated daily memory: {user_id}:{expert_id}, session count: {len(session_memories)}")
            return daily_memory
            
        except Exception as e:
            self.logger.error(f"Failed to generate daily memory: {e}")
            # Return default daily memory
            return DailyMemory(
                id=str(uuid.uuid4()),
                user_id=user_id,
                expert_id=expert_id,
                date=date,
                summary=f"日报记忆：{date.strftime('%Y-%m-%d')}",
                key_topics=[],
                interaction_patterns=[],
                knowledge_evolution=[],
                session_memories=[],
                trend_analysis={},
                importance_score=0.5,
                created_at=datetime.now(),
                metadata={"error": str(e)}
            )
    
    async def generate_daily_memory_with_history(self, user_id: str, expert_id: str, 
                                                l2_memories: List[Any], date: datetime, 
                                                history_l3_memories: List[Any]) -> DailyMemory:
        """生成日报记忆，使用历史记忆进行递进式摘要
        
        Args:
            user_id: 用户ID
            expert_id: 专家ID
            l2_memories: L2记忆列表
            date: 日期
            history_l3_memories: 历史L3记忆列表（从数据库检索）
            
        Returns:
            日报记忆对象
        """
        try:
            # 转换为SessionMemory格式
            session_memories = []
            for memory in l2_memories:
                # 处理从数据库检索的记忆对象
                if hasattr(memory, 'summary'):
                    # 从数据库对象创建SessionMemory
                    session_memory = SessionMemory(
                        id=memory.memory_id if hasattr(memory, 'memory_id') else str(uuid.uuid4()),
                        user_id=user_id,
                        expert_id=expert_id,
                        session_id=memory.session_id if hasattr(memory, 'session_id') else "unknown",
                        summary=memory.summary,
                        key_topics=memory.metadata.get('key_topics', []) if hasattr(memory, 'metadata') else [],
                        decision_points=memory.metadata.get('decision_points', []) if hasattr(memory, 'metadata') else [],
                        fragments=[],
                        importance_score=memory.metadata.get('importance_score', 0.5) if hasattr(memory, 'metadata') else 0.5,
                        created_at=memory.timestamp if hasattr(memory, 'timestamp') else datetime.now(),
                        metadata=memory.metadata if hasattr(memory, 'metadata') else {}
                    )
                    session_memories.append(session_memory)
                elif isinstance(memory, dict):
                    # 处理字典格式的记忆对象
                    session_memory = SessionMemory(
                        id=memory.get('memory_id', str(uuid.uuid4())),
                        user_id=user_id,
                        expert_id=expert_id,
                        session_id=memory.get('session_id', "unknown"),
                        summary=memory.get('summary', ''),
                        key_topics=memory.get('metadata', {}).get('key_topics', []),
                        decision_points=memory.get('metadata', {}).get('decision_points', []),
                        fragments=[],
                        importance_score=memory.get('metadata', {}).get('importance_score', 0.5),
                        created_at=memory.get('timestamp', datetime.now()),
                        metadata=memory.get('metadata', {})
                    )
                    session_memories.append(session_memory)
            
            # 分析交互模式
            interaction_patterns = await self._analyze_interaction_patterns(session_memories)
            
            # 跟踪知识演化
            knowledge_evolution = await self._track_knowledge_evolution(session_memories)
            
            # 执行趋势分析
            trend_analysis = await self._perform_trend_analysis(session_memories)
            
            # 聚合主题
            key_topics = await self._aggregate_daily_topics(session_memories)
            
            # 生成递进式日报摘要
            if history_l3_memories:
                # 构建历史上下文
                history_context = []
                for hist_memory in history_l3_memories[-3:]:  # 最近3个L3记忆
                    if hasattr(hist_memory, 'summary'):
                        history_context.append(f"历史日报摘要: {hist_memory.summary}")
                    elif isinstance(hist_memory, dict) and 'summary' in hist_memory:
                        history_context.append(f"历史日报摘要: {hist_memory['summary']}")
                
                # 使用递进式摘要
                daily_summary = await self._generate_progressive_daily_summary(
                    session_memories, interaction_patterns, knowledge_evolution, history_context
                )
                self.logger.info(f"使用递进式日报摘要，历史L3记忆数量: {len(history_l3_memories)}")
            else:
                # 使用独立摘要
                daily_summary = await self._generate_daily_summary(session_memories, interaction_patterns, knowledge_evolution)
                self.logger.info("使用独立日报摘要")
            
            # 计算重要性
            importance_score = await self._calculate_daily_importance(session_memories, interaction_patterns, knowledge_evolution)
            
            # 创建日报记忆
            daily_memory = DailyMemory(
                id=str(uuid.uuid4()),
                user_id=user_id,
                expert_id=expert_id,
                date=date,
                summary=daily_summary,
                key_topics=key_topics,
                interaction_patterns=interaction_patterns,
                knowledge_evolution=knowledge_evolution,
                session_memories=session_memories,
                trend_analysis=trend_analysis,
                importance_score=importance_score,
                created_at=datetime.now(),
                metadata={
                    "l2_session_count": len(session_memories),
                    "date": date.isoformat(),
                    "history_memory_count": len(history_l3_memories),
                    "is_progressive_summary": len(history_l3_memories) > 0
                }
            )
            
            self.logger.info(f"生成日报记忆: {user_id}:{expert_id}, 会话数量: {len(session_memories)}")
            return daily_memory
            
        except Exception as e:
            self.logger.error(f"生成日报记忆失败: {e}")
            # 返回默认日报记忆
            return DailyMemory(
                id=str(uuid.uuid4()),
                user_id=user_id,
                expert_id=expert_id,
                date=date,
                summary=f"日报记忆：{date.strftime('%Y-%m-%d')}",
                key_topics=[],
                interaction_patterns=[],
                knowledge_evolution=[],
                session_memories=[],
                trend_analysis={},
                importance_score=0.5,
                created_at=datetime.now(),
                metadata={"error": str(e)}
            )
    
    async def _generate_progressive_daily_summary(self, session_memories: List[SessionMemory], 
                                                 patterns: List[InteractionPattern], 
                                                 evolutions: List[KnowledgeEvolution],
                                                 history_context: List[str]) -> str:
        """Generate progressive daily summary
        
        Args:
            session_memories: List of session memories
            patterns: List of interaction patterns
            evolutions: List of knowledge evolutions
            history_context: List of history context
            
        Returns:
            Progressive daily summary
        """
        try:
            # Build current daily report content
            current_summaries = [s.summary for s in session_memories]
            current_content = f"Current daily report contains {len(session_memories)} session memories"
            
            # Build progressive summary prompt
            progressive_prompt = f"""
Based on the following historical daily memories and current daily L2 session memories, generate a more comprehensive daily-level memory:

Historical daily memories:
{chr(10).join(history_context)}

Current daily L2 session memories:
{chr(10).join([f"- {summary}" for summary in current_summaries])}

Please generate a daily-level memory that considers historical context:
"""
            
            # Use MockLLMAdapter to generate progressive daily memory
            from llm.mock_adapter import MockLLMAdapter
            
            llm_service = MockLLMAdapter()
            enhanced_daily_summary = await llm_service.generate_text(progressive_prompt)
            
            return enhanced_daily_summary
            
        except Exception as e:
            self.logger.error(f"Failed to generate progressive daily summary: {e}")
            return f"Daily memory: {datetime.now().strftime('%Y-%m-%d')}, contains {len(session_memories)} sessions"