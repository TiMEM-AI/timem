"""
TiMem L5 High-Dimensional Memory Module
Implements high-dimensional memory management for multi-user-multi-expert-multi-session-periodic-update
Cross-dimensional fusion of user deep profiles and expert service patterns
"""

import asyncio
import uuid
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import json
import numpy as np
from collections import defaultdict, Counter

from timem.utils.logging import get_logger
from timem.utils import time_utils
from timem.utils.text_processing import LLMTextProcessor


class HighLevelMemoryType(Enum):
    """High-dimensional memory types"""
    USER_PROFILE = "user_profile"           # User deep profile
    EXPERT_PATTERN = "expert_pattern"       # Expert service pattern
    CROSS_DIMENSION = "cross_dimension"     # Cross-dimensional fusion


class UserProfileType(Enum):
    """User profile types"""
    COMPREHENSIVE = "comprehensive"         # Comprehensive profile
    DOMAIN_SPECIFIC = "domain_specific"     # Domain-specific
    BEHAVIOR_FOCUSED = "behavior_focused"   # Behavior-focused


@dataclass
class UserDeepProfile:
    """User deep profile"""
    user_id: str
    profile_type: UserProfileType
    core_interests: List[str]
    expertise_areas: List[str]
    learning_patterns: Dict[str, Any]
    decision_patterns: Dict[str, Any]
    interaction_preferences: Dict[str, Any]
    personality_traits: Dict[str, Any]
    knowledge_gaps: List[str]
    growth_trajectory: Dict[str, Any]
    expert_relationships: Dict[str, Any]
    prediction_insights: List[str]
    confidence_score: float
    created_at: datetime
    updated_at: datetime  # New field
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "user_id": self.user_id,
            "profile_type": self.profile_type.value,
            "core_interests": self.core_interests,
            "expertise_areas": self.expertise_areas,
            "learning_patterns": self.learning_patterns,
            "decision_patterns": self.decision_patterns,
            "interaction_preferences": self.interaction_preferences,
            "personality_traits": self.personality_traits,
            "knowledge_gaps": self.knowledge_gaps,
            "growth_trajectory": self.growth_trajectory,
            "expert_relationships": self.expert_relationships,
            "prediction_insights": self.prediction_insights,
            "confidence_score": self.confidence_score,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()  # New field
        }


@dataclass
class ExpertServicePattern:
    """Expert service pattern"""
    expert_id: str
    service_strengths: List[str]
    service_weaknesses: List[str]
    user_segment_performance: Dict[str, float]
    peak_service_times: List[str]
    knowledge_gaps: List[str]
    skill_development_areas: List[str]
    collaboration_opportunities: List[str]
    service_statistics: Dict[str, Any]
    trend_analysis: Dict[str, Any]
    updated_at: datetime  # New field
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "expert_id": self.expert_id,
            "service_strengths": self.service_strengths,
            "service_weaknesses": self.service_weaknesses,
            "user_segment_performance": self.user_segment_performance,
            "peak_service_times": self.peak_service_times,
            "knowledge_gaps": self.knowledge_gaps,
            "skill_development_areas": self.skill_development_areas,
            "collaboration_opportunities": self.collaboration_opportunities,
            "service_statistics": self.service_statistics,
            "trend_analysis": self.trend_analysis,
            "updated_at": self.updated_at.isoformat()  # New field
        }


@dataclass
class CrossDimensionInsight:
    """Cross-dimensional insight"""
    insight_type: str
    description: str
    involved_dimensions: List[str]
    confidence: float
    supporting_evidence: List[str]
    actionable_recommendations: List[str]
    updated_at: datetime  # New field
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "insight_type": self.insight_type,
            "description": self.description,
            "involved_dimensions": self.involved_dimensions,
            "confidence": self.confidence,
            "supporting_evidence": self.supporting_evidence,
            "actionable_recommendations": self.actionable_recommendations,
            "updated_at": self.updated_at.isoformat()  # New field
        }


@dataclass
class HighLevelMemory:
    """High-dimensional memory"""
    id: str
    memory_type: HighLevelMemoryType
    user_profiles: Dict[str, UserDeepProfile]
    expert_patterns: Dict[str, ExpertServicePattern]
    cross_dimension_insights: List[CrossDimensionInsight]
    importance_score: float
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "memory_type": self.memory_type.value,
            "user_profiles": {k: v.to_dict() for k, v in self.user_profiles.items()},
            "expert_patterns": {k: v.to_dict() for k, v in self.expert_patterns.items()},
            "cross_dimension_insights": [insight.to_dict() for insight in self.cross_dimension_insights],
            "importance_score": self.importance_score,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata
        }


class L5HighLevelMemory:
    """L5 high-dimensional memory processor"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.logger = get_logger(__name__)
        
        self.logger.info("Initializing L5 high-dimensional memory processor")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "config": self.config,
            "initialized": True
        }
    
    async def generate_high_level_memory(self, user_id: str, l4_memories: List[Any]) -> HighLevelMemory:
        """Generate high-level memory
        
        Args:
            user_id: User ID
            l4_memories: List of L4 memories
            
        Returns:
            High-level memory object
        """
        try:
            # Simplified user profile generation
            user_profile = UserDeepProfile(
                user_id=user_id,
                profile_type=UserProfileType.COMPREHENSIVE,
                core_interests=["learning", "growth"],
                expertise_areas=["general domain"],
                learning_patterns={"style": "progressive", "pace": "moderate"},
                decision_patterns={"approach": "analytical", "speed": "moderate"},
                interaction_preferences={"frequency": "moderate", "depth": "deep"},
                personality_traits={"openness": 0.7, "conscientiousness": 0.8},
                knowledge_gaps=["advanced skills"],
                growth_trajectory={"direction": "upward", "pace": "stable"},
                expert_relationships={"diversity": "moderate", "depth": "deep"},
                prediction_insights=["continuous learning", "skill improvement"],
                confidence_score=0.8,
                created_at=datetime.now()
            )
            
            # Simplified expert pattern analysis
            expert_pattern = ExpertServicePattern(
                expert_id="system",
                service_strengths=["knowledge transfer", "problem solving"],
                service_weaknesses=["advanced skills"],
                user_segment_performance={"general": 0.8},
                peak_service_times=["morning", "afternoon"],
                knowledge_gaps=["cutting-edge technology"],
                skill_development_areas=["advanced analysis"],
                collaboration_opportunities=["cross-domain collaboration"],
                service_statistics={"total_sessions": len(l4_memories)},
                trend_analysis={"growth": "stable"}
            )
            
            # Simplified cross-dimension insight
            cross_dimension_insight = CrossDimensionInsight(
                insight_type="user-expert matching",
                description="Good matching between user and expert across multiple dimensions",
                involved_dimensions=["learning patterns", "interaction preferences"],
                confidence=0.8,
                supporting_evidence=["historical interaction records", "learning progress"],
                actionable_recommendations=["continue deepening collaboration", "explore new domains"]
            )
            
            # Create high-level memory
            high_level_memory = HighLevelMemory(
                id=str(uuid.uuid4()),
                memory_type=HighLevelMemoryType.USER_PROFILE,
                user_profiles={user_id: user_profile},
                expert_patterns={"system": expert_pattern},
                cross_dimension_insights=[cross_dimension_insight],
                importance_score=0.8,
                created_at=datetime.now(),
                metadata={
                    "l4_weekly_count": len(l4_memories),
                    "memory_type": "user_profile"
                }
            )
            
            self.logger.info(f"Generated high-level memory: {user_id}, L4 memory count: {len(l4_memories)}")
            return high_level_memory
            
        except Exception as e:
            self.logger.error(f"Failed to generate high-level memory: {e}")
            # Return default high-level memory
            return HighLevelMemory(
                id=str(uuid.uuid4()),
                memory_type=HighLevelMemoryType.USER_PROFILE,
                user_profiles={},
                expert_patterns={},
                cross_dimension_insights=[],
                importance_score=0.5,
                created_at=datetime.now(),
                metadata={"error": str(e)}
            )
    
    async def generate_high_level_memory_with_history(self, user_id: str, l4_memories: List[Any], 
                                                     history_l5_memories: List[Any]) -> HighLevelMemory:
        """Generate high-level memory with history using progressive summary
        
        Args:
            user_id: User ID
            l4_memories: List of L4 memories
            history_l5_memories: List of historical L5 memories (retrieved from database)
            
        Returns:
            High-level memory object
        """
        try:
            # Generate progressive user profile
            if history_l5_memories:
                # Build history context
                history_context = []
                for hist_memory in history_l5_memories[-3:]:  # Last 3 L5 memories
                    if hasattr(hist_memory, 'summary'):
                        history_context.append(f"Historical high-level memory: {hist_memory.summary}")
                    elif isinstance(hist_memory, dict) and 'summary' in hist_memory:
                        history_context.append(f"Historical high-level memory: {hist_memory['summary']}")
                
                # Use progressive generation
                user_profile = await self._generate_progressive_user_profile(user_id, l4_memories, history_context)
                self.logger.info(f"Using progressive high-level memory generation, history L5 memory count: {len(history_l5_memories)}")
            else:
                # Use independent generation
                user_profile = UserDeepProfile(
                    user_id=user_id,
                    profile_type=UserProfileType.COMPREHENSIVE,
                    core_interests=["learning", "growth"],
                    expertise_areas=["general domain"],
                    learning_patterns={"style": "progressive", "pace": "moderate"},
                    decision_patterns={"approach": "analytical", "speed": "moderate"},
                    interaction_preferences={"frequency": "moderate", "depth": "deep"},
                    personality_traits={"openness": 0.7, "conscientiousness": 0.8},
                    knowledge_gaps=["advanced skills"],
                    growth_trajectory={"direction": "upward", "pace": "stable"},
                    expert_relationships={"diversity": "moderate", "depth": "deep"},
                    prediction_insights=["continuous learning", "skill improvement"],
                    confidence_score=0.8,
                    created_at=datetime.now()
                )
                self.logger.info("Using independent high-level memory generation")
            
            # Simplified expert pattern analysis
            expert_pattern = ExpertServicePattern(
                expert_id="system",
                service_strengths=["knowledge transfer", "problem solving"],
                service_weaknesses=["advanced skills"],
                user_segment_performance={"general": 0.8},
                peak_service_times=["morning", "afternoon"],
                knowledge_gaps=["cutting-edge technology"],
                skill_development_areas=["advanced analysis"],
                collaboration_opportunities=["cross-domain collaboration"],
                service_statistics={"total_sessions": len(l4_memories)},
                trend_analysis={"growth": "stable"}
            )
            
            # Simplified cross-dimension insight
            cross_dimension_insight = CrossDimensionInsight(
                insight_type="user-expert matching",
                description="Good matching between user and expert across multiple dimensions",
                involved_dimensions=["learning patterns", "interaction preferences"],
                confidence=0.8,
                supporting_evidence=["historical interaction records", "learning progress"],
                actionable_recommendations=["continue deepening collaboration", "explore new domains"]
            )
            
            # Create high-level memory
            high_level_memory = HighLevelMemory(
                id=str(uuid.uuid4()),
                memory_type=HighLevelMemoryType.USER_PROFILE,
                user_profiles={user_id: user_profile},
                expert_patterns={"system": expert_pattern},
                cross_dimension_insights=[cross_dimension_insight],
                importance_score=0.8,
                created_at=datetime.now(),
                metadata={
                    "l4_weekly_count": len(l4_memories),
                    "memory_type": "user_profile",
                    "history_memory_count": len(history_l5_memories),
                    "is_progressive_summary": len(history_l5_memories) > 0
                }
            )
            
            self.logger.info(f"Generated high-level memory: {user_id}, L4 memory count: {len(l4_memories)}")
            return high_level_memory
            
        except Exception as e:
            self.logger.error(f"Failed to generate high-level memory: {e}")
            # Return default high-level memory
            return HighLevelMemory(
                id=str(uuid.uuid4()),
                memory_type=HighLevelMemoryType.USER_PROFILE,
                user_profiles={},
                expert_patterns={},
                cross_dimension_insights=[],
                importance_score=0.5,
                created_at=datetime.now(),
                metadata={"error": str(e)}
            )
    
    async def _generate_progressive_user_profile(self, user_id: str, l4_memories: List[Any], 
                                               history_context: List[str]) -> UserDeepProfile:
        """Generate progressive user profile
        
        Args:
            user_id: User ID
            l4_memories: List of L4 memories
            history_context: List of history context
            
        Returns:
            Progressive user profile
        """
        try:
            # Build current user content
            current_summaries = [memory.summary for memory in l4_memories if hasattr(memory, 'summary')]
            current_content = f"Current user contains {len(l4_memories)} L4 weekly report memories"
            
            # Build progressive profile prompt
            progressive_prompt = f"""
Based on the following historical high-level memories and current user's L4 weekly report memories, generate a more comprehensive user deep profile:

Historical high-level memories:
{chr(10).join(history_context)}

Current user's L4 weekly report memories:
{chr(10).join([f"- {summary}" for summary in current_summaries])}

Please generate a user deep profile that considers historical context:
"""
            
            # Use MockLLMAdapter to generate progressive user profile
            from llm.mock_adapter import MockLLMAdapter
            
            llm_service = MockLLMAdapter()
            enhanced_profile_summary = await llm_service.generate_text(progressive_prompt)
            
            # Generate user profile based on progressive summary
            user_profile = UserDeepProfile(
                user_id=user_id,
                profile_type=UserProfileType.COMPREHENSIVE,
                core_interests=["learning", "growth", "progressive development"],
                expertise_areas=["general domain", "progressive skills"],
                learning_patterns={"style": "progressive", "pace": "moderate", "progressive": True},
                decision_patterns={"approach": "analytical", "speed": "moderate", "progressive": True},
                interaction_preferences={"frequency": "moderate", "depth": "deep", "progressive": True},
                personality_traits={"openness": 0.8, "conscientiousness": 0.8, "progressive": True},
                knowledge_gaps=["advanced skills", "progressive skills"],
                growth_trajectory={"direction": "upward", "pace": "stable", "progressive": True},
                expert_relationships={"diversity": "moderate", "depth": "deep", "progressive": True},
                prediction_insights=["continuous learning", "skill improvement", "progressive development"],
                confidence_score=0.9,
                created_at=datetime.now()
            )
            
            return user_profile
            
        except Exception as e:
            self.logger.error(f"Failed to generate progressive user profile: {e}")
            # Return default user profile
            return UserDeepProfile(
                user_id=user_id,
                profile_type=UserProfileType.COMPREHENSIVE,
                core_interests=["learning", "growth"],
                expertise_areas=["general domain"],
                learning_patterns={"style": "progressive", "pace": "moderate"},
                decision_patterns={"approach": "analytical", "speed": "moderate"},
                interaction_preferences={"frequency": "moderate", "depth": "deep"},
                personality_traits={"openness": 0.7, "conscientiousness": 0.8},
                knowledge_gaps=["advanced skills"],
                growth_trajectory={"direction": "upward", "pace": "stable"},
                expert_relationships={"diversity": "moderate", "depth": "deep"},
                prediction_insights=["continuous learning", "skill improvement"],
                confidence_score=0.8,
                created_at=datetime.now()
            )