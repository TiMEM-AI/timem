"""
Session State Manager Node

Manages session state in memory generation workflow, determines session start/end
"""
import time
from datetime import datetime, timedelta
from typing import Dict, Any

from timem.workflows.state import MemoryState
from timem.utils.logging import get_logger
from timem.utils.time_parser import time_parser

logger = get_logger(__name__)


class SessionStateManager:
    """Session state manager node that handles session state and determines session start/end"""
    
    def __init__(self):
        """Initialize session state manager node"""
        logger.info("Session state manager node initialized")
        # Session timeout threshold (seconds), default 30 minutes
        self.session_timeout = 30 * 60
        # Session state cache, stores state for each session
        self._session_cache = {}
    
    async def run(self, state: MemoryState) -> MemoryState:
        """
        Handle session state and determine session start/end
        
        Args:
            state: Memory workflow state
            
        Returns:
            Updated workflow state
        """
        logger.info(f"Processing session state: {state['session_id']}")
        
        try:
            session_id = state["session_id"]
            timestamp = state["timestamp"]
            
            # Parse timestamp
            current_time = self._parse_session_time(timestamp)
            
            # Initialize session state
            session_state = {
                "session_id": session_id,
                "last_activity": current_time.timestamp(),
                "start_time": None,
                "end_time": None,
                "message_count": 0,
                "is_active": True
            }
            
            # Check if it's a new session
            is_new_dialogue = False
            if session_id not in self._session_cache:
                is_new_dialogue = True
                session_state["start_time"] = current_time.timestamp()
                self._session_cache[session_id] = session_state
                logger.info(f"Detected new session: {session_id}")
            else:
                # Get existing session state
                existing_state = self._session_cache[session_id]
                last_activity = existing_state["last_activity"]
                
                # Check if session has expired
                if current_time.timestamp() - last_activity > self.session_timeout:
                    is_new_dialogue = True
                    session_state["start_time"] = current_time.timestamp()
                    logger.info(f"Session {session_id} has timed out, treat as new session")
                else:
                    # Update existing session state
                    session_state = existing_state
                    session_state["last_activity"] = current_time.timestamp()
                    session_state["message_count"] += 1
            
            # Update session cache
            self._session_cache[session_id] = session_state
            
            # Calculate session duration
            session_duration = None
            if session_state["start_time"] is not None:
                session_duration = current_time.timestamp() - session_state["start_time"]
            
            # Update state
            updated_state = {
                **state,
                "session_state": session_state,
                "is_new_dialogue": is_new_dialogue,
                "session_duration": session_duration
            }
            
            return updated_state
            
        except Exception as e:
            error_msg = f"Error occurred while processing session state: {str(e)}"
            logger.error(error_msg)
            return {
                **state,
                "error": error_msg,
                "validation_passed": False
            }
    
    def _parse_session_time(self, time_str: str) -> datetime:
        """Parse time string to datetime object"""
        return time_parser.parse_session_time(time_str) 