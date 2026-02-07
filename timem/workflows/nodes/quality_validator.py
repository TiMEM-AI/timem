"""
Quality Validation Node

Evaluates the quality of generated memories
"""
from typing import Dict, List, Any, Optional
import random

from timem.models.memory import Memory
from timem.workflows.state import MemoryState
from timem.utils.logging import get_logger

logger = get_logger(__name__)


class QualityValidator:
    """Quality validation node that evaluates the quality of generated memories"""
    
    def __init__(self):
        """Initialize quality validation node"""
        logger.info("Quality validation node initialized")
        
        # Quality threshold configuration
        self._quality_thresholds = {
            "L1": 0.6,  # L1 fragment memory quality threshold
            "L2": 0.65,  # L2 session memory quality threshold
            "L3": 0.7,  # L3 daily memory quality threshold
            "L4": 0.75,  # L4 weekly memory quality threshold
            "L5": 0.8,  # L5 monthly memory quality threshold
        }
    
    async def run(self, state: MemoryState) -> MemoryState:
        """
        Evaluate the quality of generated memories
        
        Args:
            state: Workflow state
            
        Returns:
            Updated workflow state
        """
        logger.info("Executing quality validation")
        
        try:
            # Get generated memory
            memory = state.get("generated_memory")
            
            if memory is None:
                quality_feedback = ["No memory available for evaluation"]
                logger.warning("No memory available for evaluation")
                return {
                    **state,
                    "quality_passed": False,
                    "memory_quality_score": 0.0,
                    "quality_feedback": quality_feedback
                }
            
            # Evaluate memory quality
            quality_score = await self._evaluate_quality(memory)
            
            # Get memory layer, prioritize level attribute, compatible with memory_level attribute
            memory_level = None
            if hasattr(memory, "level"):
                memory_level = str(memory.level)
            elif hasattr(memory, "memory_level"):
                memory_level = str(memory.memory_level)
            else:
                memory_level = "unknown"
                logger.warning(f"Unable to determine memory layer: {getattr(memory, 'id', 'unknown')}")
            
            # Get quality threshold for corresponding layer
            threshold = self._quality_thresholds.get(memory_level, 0.7)
            
            # Determine if quality validation passed
            quality_passed = quality_score >= threshold
            
            # Generate quality feedback
            quality_feedback = []
            
            if quality_passed:
                quality_feedback.append(f"{memory_level} memory quality evaluation passed, score: {quality_score:.2f}")
            else:
                quality_feedback.append(f"{memory_level} memory quality evaluation failed, score: {quality_score:.2f}, threshold: {threshold:.2f}")
            
            # Check memory content length
            content_length = len(memory.content) if hasattr(memory, "content") else 0
            if content_length < 50:
                quality_feedback.append(f"Memory content too short, only {content_length} characters")
                quality_passed = False
            
            # Check if required child memories are present
            child_memory_ids = memory.child_memory_ids if hasattr(memory, "child_memory_ids") else []
            if memory_level != "L1" and not child_memory_ids:
                quality_feedback.append("Missing required child memory indices")
                quality_passed = False
            
            # Update state
            updated_state = {
                **state,
                "quality_passed": quality_passed,
                "memory_quality_score": quality_score,
                "quality_feedback": quality_feedback
            }
            
            logger.info(f"Quality validation result: {quality_passed}, score: {quality_score:.2f}")
            return updated_state
            
        except Exception as e:
            error_msg = f"Error occurred during quality validation: {str(e)}"
            logger.error(error_msg)
            return {
                **state,
                "quality_passed": False,
                "memory_quality_score": 0.0,
                "quality_feedback": [error_msg]
            }
    
    async def _evaluate_quality(self, memory: Memory) -> float:
        """Evaluate memory quality, return score between 0.0-1.0"""
        def safe_get_attr(obj, attr, default=None):
            return getattr(obj, attr) if hasattr(obj, attr) else default
        
        try:
            # Simple quality evaluation: content length
            content = safe_get_attr(memory, "content", "")
            content_length = len(content)
            
            # Simple quality scoring, can be extended to more complex scoring system later
            if content_length > 1000:
                score = 0.9  # Rich content
            elif content_length > 500:
                score = 0.8  # Fairly rich content
            elif content_length > 200:
                score = 0.7  # Medium content
            elif content_length > 100:
                score = 0.6  # Limited content
            else:
                score = 0.5  # Very limited content
            
            return score
            
        except Exception as e:
            logger.error(f"Error occurred while evaluating memory quality: {str(e)}")
            return 0.5  # Default medium quality 

    def validate_memory_quality(self, memory) -> Dict[str, Any]:
        """Validate memory quality, return validation result"""
        try:
            logger.info("Executing quality validation")
            
            # Default quality score
            quality_score = 0.5
            
            # Get memory ID
            memory_id = getattr(memory, "id", "unknown")
            
            # Get memory layer, prioritize level attribute, compatible with memory_level attribute
            memory_level = None
            if hasattr(memory, "level"):
                memory_level = str(memory.level)
            elif hasattr(memory, "memory_level"):
                memory_level = str(memory.memory_level)
            else:
                memory_level = "unknown"
                logger.warning(f"Unable to determine memory layer: {memory_id}")
            
            # Get quality threshold for corresponding layer
            threshold = self._quality_thresholds.get(memory_level, 0.7)
            
            # Perform quality evaluation
            # TODO: Implement actual quality evaluation logic
            quality_score = 0.5 + random.random() * 0.5
            
            # Record quality evaluation results
            quality_feedback = []
            
            # Determine if quality validation passed
            passed = quality_score >= threshold
            if passed:
                quality_feedback.append(f"{memory_level} memory quality evaluation passed, score: {quality_score:.2f}")
            else:
                quality_feedback.append(f"{memory_level} memory quality evaluation failed, score: {quality_score:.2f}, threshold: {threshold:.2f}")
            
            # Completeness check
            # Check child memory associations
            child_memory_ids = []
            if hasattr(memory, "child_memory_ids"):
                child_memory_ids = memory.child_memory_ids
            elif isinstance(memory, dict) and "child_memory_ids" in memory:
                child_memory_ids = memory["child_memory_ids"]
                
            if memory_level != "L1" and not child_memory_ids:
                quality_feedback.append(f"Warning: {memory_level} memory has no associated child memories")
            
            # Record validation results
            logger.info(f"Quality validation result: {passed}, score: {quality_score:.2f}")
            
            return {
                "memory_id": memory_id,
                "quality_score": quality_score,
                "quality_threshold": threshold,
                "passed": passed,
                "feedback": quality_feedback
            }
        
        except Exception as e:
            logger.error(f"Error occurred during quality validation: {e}", exc_info=True)
            return {
                "memory_id": getattr(memory, "id", "unknown"),
                "quality_score": 0.0,
                "quality_threshold": 0.7,
                "passed": False,
                "feedback": [f"Quality validation error: {str(e)}"]
            }