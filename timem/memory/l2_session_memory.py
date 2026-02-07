"""
TiMem L2 Session Overall Memory Implementation
Handles single-user-single-expert-single-session session overall memory aggregation
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import uuid

from langchain_core.prompts import PromptTemplate
from langchain_core.documents import Document

from llm import get_llm
from timem.models.memory import Memory, SessionMemory, MemoryLevel
from timem.memory.l1_fragment_memory import L1FragmentMemory
from timem.memory.memory_generator import MemoryGenerator
from timem.utils.config_manager import get_prompts_config
from timem.utils import time_utils
from timem.utils.time_utils import ensure_iso_string
from timem.utils.logging import get_logger

logger = get_logger(__name__)

@dataclass
class SessionSummary:
    """Session Summary"""
    session_id: str
    user_id: str
    expert_id: str
    summary: str
    key_topics: List[str]
    decision_points: List[Dict[str, Any]]
    fragments: List[L1FragmentMemory]
    importance_score: float
    created_at: datetime
    metadata: Dict[str, Any] = None

@dataclass
class SessionMemory:
    """Session Overall Memory"""
    id: str
    user_id: str
    expert_id: str
    session_id: str
    summary: str
    key_topics: List[str]
    decision_points: List[Dict[str, Any]]
    fragments: List[L1FragmentMemory]
    importance_score: float
    created_at: datetime
    metadata: Dict[str, Any] = None

class L2SessionMemory:
    """
    Responsible for aggregating L1 fragment memories from the session into a single L2 session memory.
    """
    def __init__(self, llm_adapter, prompts):
        self.llm = llm_adapter
        self.prompts = prompts

    async def summarize(self, fragments: List[L1FragmentMemory], user_id: str, expert_id: str, session_id: str) -> Optional[SessionMemory]:
        if not fragments:
            logger.warning("Cannot generate L2 session memory: L1 fragment list is empty")
            return None

        try:
            # 1. Collect summaries of all L1 fragments
            fragment_summaries = [f.summary for f in fragments if f.summary]
            if not fragment_summaries:
                logger.warning("Cannot generate L2 session memory: all L1 fragment summaries are empty")
                return None
                
            # 2. Call MemoryGenerator for session-level summary
            generator = MemoryGenerator()
            session_summary_content = await generator.generate_l2_content(fragment_summaries)
            
            # 3. Create SessionMemory object
            session_memory = SessionMemory(
                id=str(uuid.uuid4()),
                user_id=user_id,
                expert_id=expert_id,
                session_id=session_id,
                level=MemoryLevel.L2,
                content=session_summary_content,
                summary=session_summary_content, # Can be shortened as summary
                child_memory_ids=[f.id for f in fragments],
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            
            logger.info(f"Successfully generated L2 memory for session {session_id}")
            return session_memory
            
        except Exception as e:
            logger.error(f"Failed to generate L2 session memory: {e}", exc_info=True)
            return None
    
    async def _extract_session_topics(self, fragments: List[L1FragmentMemory]) -> List[str]:
        """Extract session topics"""
        if not fragments:
            return []
        
        # Collect all keywords
        all_keywords = []
        for fragment in fragments:
            # Handle different types of fragment objects
            if hasattr(fragment, 'keywords'):
                all_keywords.extend(fragment.keywords)
            elif isinstance(fragment, dict) and 'keywords' in fragment:
                all_keywords.extend(fragment['keywords'])
            else:
                # If no keywords attribute, try to extract from other fields
                if hasattr(fragment, 'content'):
                    # Simple keyword extraction
                    content = fragment.content
                elif isinstance(fragment, dict) and 'content' in fragment:
                    content = fragment['content']
                else:
                    content = str(fragment)
                
                # Simple keyword extraction
                import re
                keywords = re.findall(r'\b\w+\b', content)[:5]
                all_keywords.extend(keywords)
        
        # Topic clustering
        if self.topic_clustering_enabled:
            topics = await self._cluster_topics(all_keywords)
        else:
            # Simple frequency statistics
            from collections import Counter
            keyword_counts = Counter(all_keywords)
            topics = [kw for kw, count in keyword_counts.most_common(5)]
        
        return topics
    
    async def _cluster_topics(self, keywords: List[str]) -> List[str]:
        """Topic clustering"""
        # Simplified implementation: cluster based on keyword similarity
        if not keywords:
            return []
        
        # Deduplicate and calculate frequency
        from collections import Counter
        keyword_counts = Counter(keywords)
        
        # Select high-frequency keywords as topics
        topics = []
        for keyword, count in keyword_counts.most_common(10):
            if count >= 2:  # Appear at least 2 times
                topics.append(keyword)
        
        return topics[:5]  # Return top 5 topics
    
    async def _extract_decision_points(self, fragments: List[L1FragmentMemory]) -> List[Dict[str, Any]]:
        """Extract decision points"""
        decision_points = []
        
        for fragment in fragments:
            # Simplified implementation: identify decision points based on keywords
            decision_keywords = ["decide", "choose", "confirm", "plan", "suggest", "solution", "strategy"]
            
            # Get fragment's raw_dialogues
            raw_dialogues = []
            if hasattr(fragment, 'raw_dialogues'):
                raw_dialogues = fragment.raw_dialogues
            elif isinstance(fragment, dict) and 'raw_dialogues' in fragment:
                raw_dialogues = fragment['raw_dialogues']
            
            # Get fragment's id and importance_score
            fragment_id = getattr(fragment, 'id', None) or (fragment.get('id') if isinstance(fragment, dict) else None)
            importance_score = getattr(fragment, 'importance_score', 0.5) or (fragment.get('importance_score', 0.5) if isinstance(fragment, dict) else 0.5)
            
            for dialogue in raw_dialogues:
                if hasattr(dialogue, 'content'):
                    content = dialogue.content
                    speaker = getattr(dialogue, 'speaker', 'unknown')
                    timestamp = getattr(dialogue, 'timestamp', datetime.now())
                elif isinstance(dialogue, dict):
                    content = dialogue.get('content', '')
                    speaker = dialogue.get('speaker', 'unknown')
                    timestamp = dialogue.get('timestamp', datetime.now())
                else:
                    continue
                
                if any(keyword in content for keyword in decision_keywords):
                    decision_point = {
                        "content": content,
                        "speaker": speaker,
                        "timestamp": timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp),
                        "fragment_id": fragment_id,
                        "importance": importance_score,
                        "keywords": [kw for kw in decision_keywords if kw in content]
                    }
                    decision_points.append(decision_point)
        
        return decision_points
    
    async def _calculate_session_importance(self, fragments: List[L1FragmentMemory], 
                                          topics: List[str], decision_points: List[Dict[str, Any]]) -> float:
        """Calculate session importance"""
        if not fragments:
            return 0.0
        
        # Calculate importance based on multiple factors
        fragment_importance_sum = 0
        for f in fragments:
            if hasattr(f, 'importance_score'):
                fragment_importance_sum += f.importance_score
            elif isinstance(f, dict) and 'importance_score' in f:
                fragment_importance_sum += f['importance_score']
            else:
                fragment_importance_sum += 0.5
        
        factors = {
            "fragment_importance": fragment_importance_sum / len(fragments) if fragments else 0.5,
            "topic_diversity": min(len(topics) / 5, 1.0),
            "decision_density": min(len(decision_points) / 10, 1.0),
            "interaction_frequency": min(len(fragments) / 20, 1.0),
        }
        
        # Weighted calculation
        importance = (
            factors["fragment_importance"] * 0.4 +
            factors["topic_diversity"] * 0.2 +
            factors["decision_density"] * 0.3 +
            factors["interaction_frequency"] * 0.1
        )
        
        return min(importance, 1.0)
    
    async def _generate_session_memory(self, user_id: str, expert_id: str, sessions: List[SessionSummary]):
        """Generate session overall memory"""
        # Aggregate session information
        all_topics = []
        all_decisions = []
        all_fragments = []
        
        for session in sessions:
            all_topics.extend(session.key_topics)
            all_decisions.extend(session.decision_points)
            all_fragments.extend(session.fragments)
        
        # Aggregate topics
        aggregated_topics = await self._aggregate_topics(all_topics)
        
        # Aggregate decision points
        aggregated_decisions = await self._aggregate_decisions(all_decisions)
        
        # Analyze interaction patterns
        interaction_patterns = await self._analyze_interaction_patterns(sessions)
        
        # Generate session overall memory summary
        session_summary = await self._generate_session_content(sessions, aggregated_topics, aggregated_decisions)
        
        # Calculate session overall memory importance
        session_importance = await self._calculate_session_importance(all_fragments, aggregated_topics, aggregated_decisions)
        
        # Create session overall memory
        session_memory = SessionMemory(
            id=str(uuid.uuid4()),
            user_id=user_id,
            expert_id=expert_id,
            session_id=sessions[0].session_id, # Use first session's ID as overall memory ID
            summary=session_summary,
            key_topics=aggregated_topics,
            decision_points=aggregated_decisions,
            fragments=all_fragments,
            importance_score=session_importance,
            created_at=time_utils.get_current_timestamp(),
            metadata={
                "session_count": len(sessions),
                "fragment_count": len(all_fragments),
                "total_importance": sum(s.importance_score for s in sessions),
                "avg_session_importance": sum(s.importance_score for s in sessions) / len(sessions)
            }
        )
        
        # Store session overall memory
        self.session_memories[session_memory.session_id] = session_memory
        
        # Clean up processed sessions
        for session in sessions:
            if session.session_id in self.current_sessions:
                del self.current_sessions[session.session_id]
        
        self.logger.info(f"Generated session overall memory {session_memory.id}, user: {user_id}, expert: {expert_id}")
    
    async def _aggregate_topics(self, topics: List[str]) -> List[str]:
        """Aggregate topics"""
        if not topics:
            return []
        
        # Count topic frequency
        from collections import Counter
        topic_counts = Counter(topics)
        
        # Select high-frequency topics
        aggregated = []
        for topic, count in topic_counts.most_common(8):
            if count >= 2:  # Appear in at least 2 sessions
                aggregated.append(topic)
        
        return aggregated
    
    async def _aggregate_decisions(self, decisions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Aggregate decision points"""
        if not decisions:
            return []
        
        # Sort by importance
        sorted_decisions = sorted(decisions, key=lambda x: x["importance"], reverse=True)
        
        # Deduplication and merge similar decisions
        aggregated = []
        seen_contents = set()
        
        for decision in sorted_decisions:
            content = decision["content"]
            # Simplified deduplication: based on first 50 characters of content
            content_key = content[:50]
            
            if content_key not in seen_contents:
                seen_contents.add(content_key)
                aggregated.append(decision)
                
                if len(aggregated) >= 10:  # Limit number of decision points
                    break
        
        return aggregated
    
    async def _analyze_interaction_patterns(self, sessions: List[SessionSummary]) -> Dict[str, Any]:
        """Analyze interaction patterns"""
        if not sessions:
            return {}
        
        # Time distribution analysis
        session_times = [s.created_at for s in sessions]
        time_spans = []
        for i in range(1, len(session_times)):
            # Handle timestamp types
            if isinstance(session_times[i], (int, float)) and isinstance(session_times[i-1], (int, float)):
                span = session_times[i] - session_times[i-1]
            elif hasattr(session_times[i], 'timestamp') and hasattr(session_times[i-1], 'timestamp'):
                span = (session_times[i] - session_times[i-1]).total_seconds()
            else:
                span = 0  # Default value
            time_spans.append(span)
        
        # Interaction intensity analysis
        total_fragments = sum(len(s.fragments) for s in sessions)
        avg_fragments_per_session = total_fragments / len(sessions)
        
        # Topic evolution analysis
        topic_evolution = []
        for session in sessions:
            # Handle timestamp types
            if hasattr(session.created_at, 'isoformat'):
                timestamp = session.created_at.isoformat()
            else:
                timestamp = str(session.created_at)
            
            topic_evolution.append({
                "session_id": session.session_id,
                "topics": session.key_topics,
                "timestamp": timestamp
            })
        
        patterns = {
            "session_count": len(sessions),
            "avg_session_gap": sum(time_spans) / len(time_spans) if time_spans else 0,
            "interaction_intensity": avg_fragments_per_session,
            "topic_evolution": topic_evolution,
            "peak_interaction_time": str(max(session_times)) if session_times else "00:00:00",
            "interaction_duration": (max(session_times) - min(session_times)) if session_times else 0,
            "consistency_score": await self._calculate_consistency_score(sessions)
        }
        
        return patterns
    
    async def _calculate_consistency_score(self, sessions: List[SessionSummary]) -> float:
        """Calculate interaction consistency score"""
        if len(sessions) < 2:
            return 1.0
        
        # Calculate consistency based on topic overlap
        topic_sets = [set(s.key_topics) for s in sessions]
        
        total_similarity = 0
        pair_count = 0
        
        for i in range(len(topic_sets)):
            for j in range(i + 1, len(topic_sets)):
                if topic_sets[i] or topic_sets[j]:
                    intersection = len(topic_sets[i] & topic_sets[j])
                    union = len(topic_sets[i] | topic_sets[j])
                    similarity = intersection / union if union > 0 else 0
                    total_similarity += similarity
                    pair_count += 1
        
        return total_similarity / pair_count if pair_count > 0 else 0
    
    async def _generate_session_content(self, sessions: List[SessionSummary], 
                                    topics: List[str], decisions: List[Dict[str, Any]]) -> str:
        """Generate session overall memory summary"""
        # Collect session summaries
        session_summaries = [s.summary for s in sessions]
        
        # Construct session overall memory generation prompt
        prompt = f"""
        Based on the following information, generate today's interaction session overall memory:
        
        Number of sessions: {len(sessions)}
        Main topics: {', '.join(topics)}
        Number of important decisions: {len(decisions)}
        
        Session summaries:
        {chr(10).join(f"Session {i+1}: {summary}" for i, summary in enumerate(session_summaries))}
        
        Please generate a comprehensive session overall memory containing:
        1. Overview of today's interactions
        2. Main discussion topics
        3. Important decisions and progress
        4. Key insights and recommendations
        
        Keep length within 400 words.
        """
        
        # Call LLM to generate session overall memory
        session_summary = await self._call_llm_summarize(prompt)
        return session_summary
    
    async def _calculate_session_importance(self, fragments: List[L1FragmentMemory], 
                                        topics: List[str], decisions: List[Dict[str, Any]]) -> float:
        """Calculate session overall memory importance"""
        if not fragments:
            return 0.0
        
        # Calculate importance based on multiple factors
        factors = {
            "fragment_importance": sum(f.importance_score for f in fragments) / len(fragments) if fragments else 0.5,
            "topic_coverage": min(len(topics) / 8, 1.0),
            "decision_impact": min(len(decisions) / 5, 1.0),
            "interaction_frequency": min(len(fragments) / 10, 1.0),
        }
        
        # Weighted calculation
        importance = (
            factors["fragment_importance"] * 0.4 +
            factors["topic_coverage"] * 0.2 +
            factors["decision_impact"] * 0.2 +
            factors["interaction_frequency"] * 0.2
        )
        
        return min(importance, 1.0)
    
    async def _call_llm_summarize(self, prompt: str) -> str:
        """Call LLM for summarization (placeholder implementation)"""
        # Should call actual LLM API here
        # Temporarily return simplified summary
        lines = prompt.split('\n')
        content_lines = [line for line in lines if line.strip() and not line.startswith('Based')]
        
        if content_lines:
            summary_lines = content_lines[:5]
            return "AI session overall memory: " + " ".join(summary_lines)[:300]
        
        return "No session overall memory content"
    
    async def get_session_memory(self, session_id: str) -> Optional[SessionMemory]:
        """Get session overall memory for specified session"""
        return self.session_memories.get(session_id)
    
    async def search_session_memories(self, user_id: str, expert_id: str, 
                                  start_date: datetime, end_date: datetime) -> List[SessionMemory]:
        """Search session overall memories for specified time range"""
        results = []
        current_date = start_date.date()
        end_date = end_date.date()
        
        while current_date <= end_date:
            # Iterate through all sessions to find matching ones
            for session_memory in self.session_memories.values():
                if session_memory.user_id == user_id and session_memory.expert_id == expert_id and session_memory.created_at.date() == current_date:
                    results.append(session_memory)
            current_date += timedelta(days=1) # Search by day, may need more precise date range in actual applications
        
        return results
    
    async def get_topic_trends(self, user_id: str, expert_id: str, days: int = 7) -> Dict[str, Any]:
        """Get topic trend analysis"""
        end_date = time_utils.get_current_timestamp()
        start_date = end_date - timedelta(days=days)
        
        session_memories = await self.search_session_memories(user_id, expert_id, start_date, end_date)
        
        if not session_memories:
            return {"trends": [], "analysis": "No data available"}
        
        # Analyze topic trends
        topic_timeline = []
        all_topics = set()
        
        for memory in session_memories:
            topic_timeline.append({
                "date": memory.created_at.isoformat(),
                "topics": memory.key_topics,
                "importance": memory.importance_score
            })
            all_topics.update(memory.key_topics)
        
        # Calculate trend for each topic
        topic_trends = {}
        for topic in all_topics:
            trend = []
            for memory in session_memories:
                if topic in memory.key_topics:
                    trend.append({
                        "date": memory.created_at.isoformat(),
                        "present": True,
                        "importance": memory.importance_score
                    })
                else:
                    trend.append({
                        "date": memory.created_at.isoformat(),
                        "present": False,
                        "importance": 0
                    })
            topic_trends[topic] = trend
        
        return {
            "trends": topic_trends,
            "timeline": topic_timeline,
            "analysis": f"Analyzed {len(session_memories)} session overall memories over {days} days, found {len(all_topics)} topics"
        }
    
    def get_session_state(self) -> Dict[str, Any]:
        """Get current session state"""
        return {
            "pending_sessions": len(self.current_sessions),
            "session_memories_count": len(self.session_memories),
            "recent_sessions": [
                {
                    "session_id": s.session_id,
                    "user_id": s.user_id,
                    "expert_id": s.expert_id,
                    "topics": s.key_topics,
                    "importance": s.importance_score,
                    "created_at": s.created_at.isoformat()
                }
                for s in list(self.current_sessions.values())[-5:]
            ],
            "recent_session_memories": [
                {
                    "id": d.id,
                    "user_id": d.user_id,
                    "expert_id": d.expert_id,
                    "session_id": d.session_id,
                    "date": d.created_at.isoformat(),
                    "topics": d.key_topics,
                    "importance": d.importance_score
                }
                for d in list(self.session_memories.values())[-5:]
            ]
        }
    
    async def generate_session_memory(self, session_id: str, user_id: str, expert_id: str, 
                                    l1_memories: List[Any]) -> SessionMemory:
        """Generate session memory
        
        Args:
            session_id: Session ID
            user_id: User ID
            expert_id: Expert ID
            l1_memories: List of L1 memories
            
        Returns:
            Session memory object
        """
        try:
            # Convert to MemoryFragment format
            fragments = []
            for memory in l1_memories:
                if hasattr(memory, 'summary'):
                    fragment = L1FragmentMemory(
                        fragment_index=len(fragments),
                        summary=memory.summary,
                        original_text=memory.content if hasattr(memory, 'content') else memory.summary,
                        importance_score=memory.metadata.get('importance_score', 0.5) if hasattr(memory, 'metadata') else 0.5,
                        raw_dialogues=[]  # Simplified processing
                    )
                    fragments.append(fragment)
            
            # Generate session summary
            session_summary = await self._generate_session_content([], [], [])
            if fragments:
                summaries = [f.summary for f in fragments]
                session_summary = f"Session {session_id} memory: contains {len(fragments)} L1 memory fragments covering important dialogue content"
            
            # Extract key topics
            key_topics = await self._extract_session_topics(fragments)
            
            # Extract decision points
            decision_points = await self._extract_decision_points(fragments)
            
            # Calculate importance
            importance_score = await self._calculate_session_importance(fragments, key_topics, decision_points)
            
            # Create session memory
            session_memory = SessionMemory(
                id=str(uuid.uuid4()),
                user_id=user_id,
                expert_id=expert_id,
                session_id=session_id,
                summary=session_summary,
                key_topics=key_topics,
                decision_points=decision_points,
                fragments=fragments,
                importance_score=importance_score,
                created_at=datetime.now(),
                metadata={
                    "l1_fragment_count": len(fragments),
                    "session_duration": 0  # Simplified processing
                }
            )
            
            self.logger.info(f"Generated session memory: {session_id}, fragment count: {len(fragments)}")
            return session_memory
            
        except Exception as e:
            self.logger.error(f"Failed to generate session memory: {e}")
            # Return default session memory
            return SessionMemory(
                id=str(uuid.uuid4()),
                user_id=user_id,
                expert_id=expert_id,
                session_id=session_id,
                summary=f"Session {session_id} memory",
                key_topics=[],
                decision_points=[],
                fragments=[],
                importance_score=0.5,
                created_at=datetime.now(),
                metadata={"error": str(e)}
            )

    async def generate_session_memory_with_history(self, session_id: str, user_id: str, expert_id: str, 
                                                 l1_memories: List[Any], history_l2_memories: List[Any]) -> SessionMemory:
        """Generate session memory with history
        
        Args:
            session_id: Session ID
            user_id: User ID
            expert_id: Expert ID
            l1_memories: List of L1 memories
            history_l2_memories: List of historical L2 memories (retrieved from database)
            
        Returns:
            Session memory object
        """
        try:
            # Convert to MemoryFragment format
            fragments = []
            for memory in l1_memories:
                if hasattr(memory, 'summary'):
                    # Extract necessary information from stored memory
                    memory_id = getattr(memory, 'id', str(uuid.uuid4()))
                    memory_content = getattr(memory, 'content', memory.summary)
                    memory_summary = memory.summary
                    memory_created_at = getattr(memory, 'created_at', datetime.now())
                    memory_importance = 0.5
                    if hasattr(memory, 'metadata') and memory.metadata:
                        memory_importance = memory.metadata.get('importance_score', 0.5)
                    
                    fragment = L1FragmentMemory(
                        id=memory_id,
                        fragment_index=len(fragments),
                        content=memory_content,
                        raw_dialogues=[],  # Simplified processing, original dialogue records may not be available
                        summary=memory_summary,
                        keywords=[],  # Simplified processing
                        entities=[],  # Simplified processing
                        importance_score=memory_importance,
                        created_at=memory_created_at,
                        original_text=memory_content,
                        metadata=getattr(memory, 'metadata', {})
                    )
                    fragments.append(fragment)
            
            # Generate progressive session summary
            if history_l2_memories:
                # Build history context
                history_context = []
                for hist_memory in history_l2_memories[-3:]:  # Last 3 L2 memories
                    if hasattr(hist_memory, 'summary'):
                        history_context.append(f"Historical session summary: {hist_memory.summary}")
                    elif isinstance(hist_memory, dict) and 'summary' in hist_memory:
                        history_context.append(f"Historical session summary: {hist_memory['summary']}")
                
                # Use progressive summary
                session_summary = await self._generate_progressive_session_summary(fragments, history_context)
                self.logger.info(f"Using progressive session summary, history L2 memory count: {len(history_l2_memories)}")
            else:
                # Use independent summary
                session_summary = f"Session {session_id} memory: contains {len(fragments)} L1 memory fragments covering important dialogue content"
                self.logger.info("Using independent session summary")
            
            # Extract key topics
            key_topics = await self._extract_session_topics(fragments)
            
            # Extract decision points
            decision_points = await self._extract_decision_points(fragments)
            
            # Calculate importance
            importance_score = await self._calculate_session_importance(fragments, key_topics, decision_points)
            
            # Create session memory
            session_memory = SessionMemory(
                id=str(uuid.uuid4()),
                user_id=user_id,
                expert_id=expert_id,
                session_id=session_id,
                summary=session_summary,
                key_topics=key_topics,
                decision_points=decision_points,
                fragments=fragments,
                importance_score=importance_score,
                created_at=datetime.now(),
                metadata={
                    "l1_fragment_count": len(fragments),
                    "session_duration": 0,  # Simplified processing
                    "history_memory_count": len(history_l2_memories),
                    "is_progressive_summary": len(history_l2_memories) > 0
                }
            )
            
            self.logger.info(f"Generated session memory: {session_id}, fragment count: {len(fragments)}")
            return session_memory
            
        except Exception as e:
            self.logger.error(f"Failed to generate session memory: {e}")
            # Return default session memory
            return SessionMemory(
                id=str(uuid.uuid4()),
                user_id=user_id,
                expert_id=expert_id,
                session_id=session_id,
                summary=f"Session {session_id} memory",
                key_topics=[],
                decision_points=[],
                fragments=[],
                importance_score=0.5,
                created_at=datetime.now(),
                metadata={"error": str(e)}
            )
    
    async def _generate_progressive_session_summary(self, fragments: List[L1FragmentMemory], history_context: List[str]) -> str:
        """Generate progressive session summary
        
        Args:
            fragments: List of memory fragments
            history_context: List of history context
            
        Returns:
            Progressive session summary
        """
        try:
            # Build current session content
            current_summaries = [f.summary for f in fragments]
            current_content = f"Current session contains {len(fragments)} L1 memory fragments"
            
            # Build progressive summary prompt
            progressive_prompt = f"""
Based on the following historical session memories and current session L1 memory fragments, generate a more comprehensive session-level memory:

Historical session memories:
{chr(10).join(history_context)}

Current session L1 memory fragments:
{chr(10).join([f"- {summary}" for summary in current_summaries])}

Please generate a session-level memory that considers historical context:
"""
            
            # Use MockLLMAdapter to generate progressive session memory
            from llm.mock_adapter import MockLLMAdapter
            
            llm_service = MockLLMAdapter()
            enhanced_session_summary = await llm_service.generate_text(progressive_prompt)
            
            return enhanced_session_summary
            
        except Exception as e:
            self.logger.error(f"Failed to generate progressive session summary: {e}")
            return f"Session memory: contains {len(fragments)} L1 memory fragments covering important dialogue content"