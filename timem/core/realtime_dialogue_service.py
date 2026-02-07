#!/usr/bin/env python3
"""
TiMem Realtime Dialogue Processing Service
Based on LangGraph workflow to implement real-time processing of external dialogue data
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, List, Optional, Any, AsyncGenerator
from dataclasses import dataclass
from dateutil.parser import parse as parse_locomo_datetime

from timem.utils.config_manager import get_config
from timem.utils.logging import get_logger
# Workflow module cleaned up, ready for LangGraph reconstruction

logger = get_logger(__name__)

@dataclass
class DialogueMessage:
    """Dialogue message data structure"""
    speaker: str                     # Speaker
    text: str                        # Dialogue content
    session_id: str                  # Session ID
    timestamp: datetime              # Timestamp
    user_id: str                     # User ID
    expert_id: str                   # Expert ID
    metadata: Dict[str, Any]         # Metadata

class RealtimeDialogueService:
    """Realtime dialogue processing service - based on LangGraph workflow"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or get_config("realtime_dialogue")
        
        # Initialize LangGraph workflow service
        # Workflow module cleaned up, ready for LangGraph reconstruction
        
        # Session state management
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
        
        logger.info("Realtime dialogue processing service initialization completed")
    
    async def initialize(self):
        """Initialize service"""
        try:
            # Workflow module cleaned up, ready for LangGraph reconstruction
            
            logger.info("Realtime dialogue processing service startup completed")
            
        except Exception as e:
            logger.error(f"Realtime dialogue processing service initialization failed: {e}", exc_info=True)
            raise
    
    async def process_dialogue_message(self, message: DialogueMessage) -> List[Dict]:
        """Process a single dialogue message
        
        Args:
            message: Dialogue message
            
        Returns:
            List of generated memory records
        """
        try:
            logger.info(f"Processing dialogue message: {message.session_id} - {message.speaker}")
            
            # Update session state
            session_key = f"{message.user_id}_{message.expert_id}_{message.session_id}"
            if session_key not in self.active_sessions:
                self.active_sessions[session_key] = {
                    "message_count": 0,
                    "last_activity": message.timestamp,
                    "speakers": set(),
                    "start_time": message.timestamp
                }
            
            session_state = self.active_sessions[session_key]
            session_state["message_count"] += 1
            session_state["last_activity"] = message.timestamp
            session_state["speakers"].add(message.speaker)
            
            # Workflow module cleaned up, ready for LangGraph reconstruction
            generated_memories = []
            
            logger.info(f"Dialogue message processing completed, generated memories: {len(generated_memories)} items")
            return generated_memories
            
        except Exception as e:
            logger.error(f"Failed to process dialogue message: {e}", exc_info=True)
            return []
    
    async def process_locomo_dialogue(self, dialogue_data: Dict) -> List[Dict]:
        """Process Locomo format dialogue data
        
        Args:
            dialogue_data: Locomo format dialogue data
            
        Returns:
            List of generated memory records
        """
        try:
            # Parse Locomo data format
            session_id = dialogue_data.get("session_id", "unknown")
            user_id = dialogue_data.get("speaker_a", "user")
            expert_id = dialogue_data.get("speaker_b", "expert")
            date_time = dialogue_data.get("date_time", "")
            
            # Parse timestamp
            try:
                if date_time:
                    timestamp = parse_locomo_datetime(date_time)
                    if not timestamp:
                        timestamp = datetime.now()
                        logger.warning(f"Unable to parse timestamp {date_time}, using current time")
                else:
                    timestamp = datetime.now()
                    logger.warning("No timestamp provided, using current time")
            except Exception as e:
                timestamp = datetime.now()
                logger.error(f"Timestamp parsing failed: {e}, using current time")
            
            # Process each dialogue turn
            all_generated_memories = []
            
            for dialogue in dialogue_data.get("dialogues", []):
                # Create dialogue message
                message = DialogueMessage(
                    speaker=dialogue.get("speaker", "Unknown"),
                    text=dialogue.get("text", ""),
                    session_id=session_id,
                    timestamp=timestamp,
                    user_id=user_id,
                    expert_id=expert_id,
                    metadata={
                        "dia_id": dialogue.get("dia_id", ""),
                        "img_url": dialogue.get("img_url", []),
                        "blip_caption": dialogue.get("blip_caption", ""),
                        "query": dialogue.get("query", ""),
                        "date_time": date_time,
                        **dialogue
                    }
                )
                
                # Process dialogue message
                generated_memories = await self.process_dialogue_message(message)
                all_generated_memories.extend(generated_memories)
            
            # Session processing completed, no longer need to simulate session end
            
            logger.info(f"Locomo dialogue processing completed, total generated memories: {len(all_generated_memories)} items")
            return all_generated_memories
            
        except Exception as e:
            logger.error(f"Failed to process Locomo dialogue: {e}", exc_info=True)
            return []
    
    async def process_batch_dialogues(self, dialogues: List[Dict]) -> List[Dict]:
        """Batch process dialogue data
        
        Args:
            dialogues: List of dialogue data
            
        Returns:
            List of generated memory records
        """
        try:
            all_generated_memories = []
            
            for dialogue_data in dialogues:
                generated_memories = await self.process_locomo_dialogue(dialogue_data)
                all_generated_memories.extend(generated_memories)
            
            logger.info(f"Batch dialogue processing completed, total generated memories: {len(all_generated_memories)} items")
            return all_generated_memories
            
        except Exception as e:
            logger.error(f"Batch dialogue processing failed: {e}", exc_info=True)
            return []
    
    async def stream_process_dialogues(self, dialogues: List[Dict]) -> AsyncGenerator[List[Dict], None]:
        """Stream process dialogue data
        
        Args:
            dialogues: List of dialogue data
            
        Yields:
            List of memory records generated for each session
        """
        try:
            for dialogue_data in dialogues:
                generated_memories = await self.process_locomo_dialogue(dialogue_data)
                yield generated_memories
                
        except Exception as e:
            logger.error(f"Stream dialogue processing failed: {e}", exc_info=True)
            yield []
    
    async def get_memory_status(self, user_id: str, expert_id: str) -> Dict:
        """Get memory status"""
        try:
            # Workflow module cleaned up, ready for LangGraph reconstruction
            memory_status = {}
            
            # Add session state information
            session_key = f"{user_id}_{expert_id}_"
            active_sessions = {}
            for key, state in self.active_sessions.items():
                if key.startswith(session_key):
                    active_sessions[key] = {
                        "message_count": state["message_count"],
                        "last_activity": state["last_activity"].isoformat(),
                        "speakers": list(state["speakers"]),
                        "start_time": state["start_time"].isoformat()
                    }
            
            memory_status["active_sessions"] = active_sessions
            return memory_status
            
        except Exception as e:
            logger.error(f"Failed to get memory status: {e}")
            return {
                "user_id": user_id,
                "expert_id": expert_id,
                "memory_counts": {},
                "active_sessions": {}
            }
    
    async def search_memories(self, query: str, user_id: str = None, 
                            expert_id: str = None, layer: str = None) -> List[Dict]:
        """Search memories"""
        try:
            # Workflow module cleaned up, ready for LangGraph reconstruction
            return []
        except Exception as e:
            logger.error(f"Failed to search memories: {e}")
            return []
    
    async def get_session_info(self, session_id: str, user_id: str, expert_id: str) -> Dict:
        """Get session information"""
        try:
            session_key = f"{user_id}_{expert_id}_{session_id}"
            if session_key in self.active_sessions:
                state = self.active_sessions[session_key]
                return {
                    "session_id": session_id,
                    "user_id": user_id,
                    "expert_id": expert_id,
                    "message_count": state["message_count"],
                    "last_activity": state["last_activity"].isoformat(),
                    "speakers": list(state["speakers"]),
                    "start_time": state["start_time"].isoformat(),
                    "duration": (state["last_activity"] - state["start_time"]).total_seconds()
                }
            else:
                return {
                    "session_id": session_id,
                    "user_id": user_id,
                    "expert_id": expert_id,
                    "message_count": 0,
                    "status": "not_found"
                }
        except Exception as e:
            logger.error(f"Failed to get session information: {e}")
            return {
                "session_id": session_id,
                "user_id": user_id,
                "expert_id": expert_id,
                "error": str(e)
            }
    
    async def close_session(self, session_id: str, user_id: str, expert_id: str) -> bool:
        """Close session"""
        try:
            session_key = f"{user_id}_{expert_id}_{session_id}"
            if session_key in self.active_sessions:
                # Remove session state, no longer need to send session end message
                del self.active_sessions[session_key]
                
                logger.info(f"Session closed: {session_id}")
                return True
            else:
                logger.warning(f"Session does not exist: {session_id}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to close session: {e}")
            return False
    
    async def close(self):
        """Close service"""
        # Close all active sessions
        for session_key in list(self.active_sessions.keys()):
            parts = session_key.split("_", 2)
            if len(parts) >= 3:
                user_id, expert_id, session_id = parts[0], parts[1], parts[2]
                await self.close_session(session_id, user_id, expert_id)
        
        # Close LangGraph workflow service
        # Workflow module cleaned up, ready for LangGraph reconstruction
        
        logger.info("Realtime dialogue processing service closed")

# Global service instance
_realtime_service: Optional[RealtimeDialogueService] = None

async def get_realtime_service() -> RealtimeDialogueService:
    """Get global realtime dialogue processing service instance"""
    global _realtime_service
    if _realtime_service is None:
        _realtime_service = RealtimeDialogueService()
        await _realtime_service.initialize()
    return _realtime_service

async def close_realtime_service():
    """Close global realtime dialogue processing service"""
    global _realtime_service
    if _realtime_service is not None:
        await _realtime_service.close()
        _realtime_service = None 