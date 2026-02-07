"""
TiMem Workflow State Manager

Responsible for managing workflow state, recording processed memories and their time information, session information and other decision-making required information,
avoiding duplicate processing and duplicate memory generation.
"""

import asyncio
from typing import Dict, List, Any, Optional, Set, Tuple
from datetime import datetime, date
import logging
import json
import os
import uuid

from timem.utils.logging import get_logger
from timem.utils.time_manager import get_time_manager, TimeManager

logger = get_logger(__name__)


class WorkflowStateManager:
    """
    Workflow State Manager
    
    Responsible for managing workflow state, recording processed memories and their time information, session information and other decision-making required information,
    avoiding duplicate processing and duplicate memory generation.
    """
    
    def __init__(self, time_manager: Optional[TimeManager] = None, state_file: Optional[str] = None):
        """
        Initialize the workflow state manager
        
        Args:
            time_manager: Time manager, auto-fetch if None
            state_file: State file path, use default if None
        """
        self.time_manager = time_manager or get_time_manager()
        self.state_file = state_file or os.path.join(os.path.dirname(__file__), "..", "..", "data", "workflow_state.json")
        self.lock = asyncio.Lock()
        
        # State data structure
        self._state = {
            # Processed L1 memories
            "processed_l1_memories": {},  # {user_id+expert_id+session_id: {memory_id: timestamp}}
            
            # Processed L2 memories
            "processed_l2_memories": {},  # {user_id+expert_id+session_id: {memory_id: timestamp}}
            
            # Processed L3 memories (by date)
            "processed_l3_memories": {},  # {user_id+expert_id+date_str: {memory_id: timestamp}}
            
            # Processed L4 memories (by week)
            "processed_l4_memories": {},  # {user_id+expert_id+year+week: {memory_id: timestamp}}
            
            # Processed L5 memories (by month)
            "processed_l5_memories": {},  # {user_id+expert_id+year+month: {memory_id: timestamp}}
            
            # Last processed timestamp
            "last_processed_timestamps": {},  # {user_id+expert_id: timestamp}
            
            # Session processing records
            "session_records": {},  # {session_id: {user_id, expert_id, start_time, last_processed_time}}
            
            # Last processing time for user-expert pairs
            "user_expert_last_times": {},  # {user_id+expert_id: {last_day, last_week, last_month}}
        }
        
        # Try to load state
        self._load_state()
    
    def _load_state(self) -> None:
        """Load state file"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, "r", encoding="utf-8") as f:
                    loaded_state = json.load(f)
                    # Merge loaded state
                    for key, value in loaded_state.items():
                        if key in self._state:
                            self._state[key] = value
                logger.info(f"Workflow state loaded from {self.state_file}")
            else:
                logger.info(f"Workflow state file {self.state_file} does not exist, will use empty state")
        except Exception as e:
            logger.error(f"Failed to load workflow state: {e}")
    
    async def _save_state(self) -> None:
        """Save state to file"""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            
            # Save state
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self._state, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Workflow state saved to {self.state_file}")
        except Exception as e:
            logger.error(f"Failed to save workflow state: {e}")
    
    async def clear_session_state(self, session_id: str) -> None:
        """
        Clear state for specified session
        
        According to TiMem research architecture: workflow state should not be permanently retained, only retained within work loop
        and released after all memories are persisted
        
        Args:
            session_id: Session ID
        """
        try:
            async with self.lock:
                # Clear session records
                if session_id in self._state["session_records"]:
                    del self._state["session_records"][session_id]
                    logger.info(f"Cleared state records for session {session_id}")
                
                # Clear related L1 and L2 memory records
                for key in list(self._state["processed_l1_memories"].keys()):
                    if session_id in key:
                        del self._state["processed_l1_memories"][key]
                        logger.info(f"Cleared L1 memory records for session {session_id}")
                
                for key in list(self._state["processed_l2_memories"].keys()):
                    if session_id in key:
                        del self._state["processed_l2_memories"][key]
                        logger.info(f"Cleared L2 memory records for session {session_id}")
                
                # Save cleaned state
                await self._save_state()
                
        except Exception as e:
            logger.error(f"Failed to clear session state: {e}")
    
    async def clear_all_state(self) -> None:
        """
        Clear all workflow state
        
        According to TiMem research architecture: workflow state should not be permanently retained
        """
        try:
            async with self.lock:
                # Reset all state
                self._state = {
                    "processed_l1_memories": {},
                    "processed_l2_memories": {},
                    "processed_l3_memories": {},
                    "processed_l4_memories": {},
                    "processed_l5_memories": {},
                    "last_processed_timestamps": {},
                    "session_records": {},
                    "user_expert_last_times": {},
                }
                
                # Save empty state
                await self._save_state()
                
                logger.info("Cleared all workflow state")
                
        except Exception as e:
            logger.error(f"Failed to clear all state: {e}")
    
    def _get_key(self, user_id: str, expert_id: str) -> str:
        """Get key for user-expert pair"""
        return f"{user_id}:{expert_id}"
    
    def _get_session_key(self, user_id: str, expert_id: str, session_id: str) -> str:
        """Get session key"""
        return f"{user_id}:{expert_id}:{session_id}"
    
    def _get_date_key(self, user_id: str, expert_id: str, dt: datetime) -> str:
        """Get date key"""
        date_str = dt.strftime("%Y-%m-%d")
        return f"{user_id}:{expert_id}:{date_str}"
    
    def _get_week_key(self, user_id: str, expert_id: str, dt: datetime) -> str:
        """Get week key"""
        year, week, _ = dt.isocalendar()
        return f"{user_id}:{expert_id}:{year}:{week}"
    
    def _get_month_key(self, user_id: str, expert_id: str, dt: datetime) -> str:
        """Get month key"""
        return f"{user_id}:{expert_id}:{dt.year}:{dt.month}"
    
    async def register_session(self, session_id: str, user_id: str, expert_id: str, timestamp: datetime) -> None:
        """
        Register session
        
        Args:
            session_id: Session ID
            user_id: User ID
            expert_id: Expert ID
            timestamp: Timestamp
        """
        async with self.lock:
            self._state["session_records"][session_id] = {
                "user_id": user_id,
                "expert_id": expert_id,
                "start_time": timestamp.isoformat(),
                "last_processed_time": timestamp.isoformat()
            }
            await self._save_state()
    
    async def update_session_time(self, session_id: str, timestamp: datetime) -> None:
        """
        Update session last processing time
        
        Args:
            session_id: Session ID
            timestamp: Timestamp
        """
        async with self.lock:
            if session_id in self._state["session_records"]:
                self._state["session_records"][session_id]["last_processed_time"] = timestamp.isoformat()
                await self._save_state()
    
    async def register_l1_memory(self, user_id: str, expert_id: str, session_id: str, memory_id: str, timestamp: datetime) -> None:
        """
        Register L1 memory
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            session_id: Session ID
            memory_id: Memory ID
            timestamp: Timestamp
        """
        async with self.lock:
            key = self._get_session_key(user_id, expert_id, session_id)
            if key not in self._state["processed_l1_memories"]:
                self._state["processed_l1_memories"][key] = {}
            
            self._state["processed_l1_memories"][key][memory_id] = timestamp.isoformat()
            
            # Update last processing time
            user_expert_key = self._get_key(user_id, expert_id)
            self._state["last_processed_timestamps"][user_expert_key] = timestamp.isoformat()
            
            await self._save_state()
    
    async def register_l2_memory(self, user_id: str, expert_id: str, session_id: str, memory_id: str, timestamp: datetime) -> None:
        """
        Register L2 memory
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            session_id: Session ID
            memory_id: Memory ID
            timestamp: Timestamp
        """
        async with self.lock:
            key = self._get_session_key(user_id, expert_id, session_id)
            if key not in self._state["processed_l2_memories"]:
                self._state["processed_l2_memories"][key] = {}
            
            self._state["processed_l2_memories"][key][memory_id] = timestamp.isoformat()
            await self._save_state()
    
    async def register_l3_memory(self, user_id: str, expert_id: str, memory_id: str, timestamp: datetime) -> None:
        """
        Register L3 memory
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            memory_id: Memory ID
            timestamp: Timestamp
        """
        async with self.lock:
            key = self._get_date_key(user_id, expert_id, timestamp)
            if key not in self._state["processed_l3_memories"]:
                self._state["processed_l3_memories"][key] = {}
            
            self._state["processed_l3_memories"][key][memory_id] = timestamp.isoformat()
            
            # Update user-expert pair last processing date
            user_expert_key = self._get_key(user_id, expert_id)
            if user_expert_key not in self._state["user_expert_last_times"]:
                self._state["user_expert_last_times"][user_expert_key] = {}
            
            self._state["user_expert_last_times"][user_expert_key]["last_day"] = timestamp.date().isoformat()
            
            await self._save_state()
    
    async def register_l4_memory(self, user_id: str, expert_id: str, memory_id: str, timestamp: datetime) -> None:
        """
        Register L4 memory
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            memory_id: Memory ID
            timestamp: Timestamp
        """
        async with self.lock:
            key = self._get_week_key(user_id, expert_id, timestamp)
            if key not in self._state["processed_l4_memories"]:
                self._state["processed_l4_memories"][key] = {}
            
            self._state["processed_l4_memories"][key][memory_id] = timestamp.isoformat()
            
            # Update user-expert pair last processing week
            user_expert_key = self._get_key(user_id, expert_id)
            if user_expert_key not in self._state["user_expert_last_times"]:
                self._state["user_expert_last_times"][user_expert_key] = {}
            
            year, week, _ = timestamp.isocalendar()
            self._state["user_expert_last_times"][user_expert_key]["last_week"] = f"{year}-{week}"
            
            await self._save_state()
    
    async def register_l5_memory(self, user_id: str, expert_id: str, memory_id: str, timestamp: datetime) -> None:
        """
        Register L5 memory
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            memory_id: Memory ID
            timestamp: Timestamp
        """
        async with self.lock:
            key = self._get_month_key(user_id, expert_id, timestamp)
            if key not in self._state["processed_l5_memories"]:
                self._state["processed_l5_memories"][key] = {}
            
            self._state["processed_l5_memories"][key][memory_id] = timestamp.isoformat()
            
            # Update user-expert pair last processing month
            user_expert_key = self._get_key(user_id, expert_id)
            if user_expert_key not in self._state["user_expert_last_times"]:
                self._state["user_expert_last_times"][user_expert_key] = {}
            
            self._state["user_expert_last_times"][user_expert_key]["last_month"] = f"{timestamp.year}-{timestamp.month}"
            
            await self._save_state()
    
    async def is_l1_processed(self, user_id: str, expert_id: str, session_id: str, content: str) -> bool:
        """
        Check if L1 memory is processed
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            session_id: Session ID
            content: Content
            
        Returns:
            bool: Whether processed
        """
        async with self.lock:
            key = self._get_session_key(user_id, expert_id, session_id)
            if key not in self._state["processed_l1_memories"]:
                return False
            
            # Since L1 memory has no fixed ID, we use content hash to determine if processed
            content_hash = str(hash(content))
            
            # Check if there is matching content hash
            for memory_id, _ in self._state["processed_l1_memories"][key].items():
                if memory_id.endswith(content_hash):
                    return True
            
            return False
    
    async def is_l2_processed(self, user_id: str, expert_id: str, session_id: str) -> bool:
        """
        Check if L2 memory is processed
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            session_id: Session ID
            
        Returns:
            bool: Whether processed
        """
        async with self.lock:
            key = self._get_session_key(user_id, expert_id, session_id)
            return key in self._state["processed_l2_memories"] and len(self._state["processed_l2_memories"][key]) > 0
    
    async def is_l3_processed(self, user_id: str, expert_id: str, target_date: datetime) -> bool:
        """
        Check if L3 memory is processed
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            target_date: Target date
            
        Returns:
            bool: Whether processed
        """
        async with self.lock:
            key = self._get_date_key(user_id, expert_id, target_date)
            return key in self._state["processed_l3_memories"] and len(self._state["processed_l3_memories"][key]) > 0
    
    async def is_l4_processed(self, user_id: str, expert_id: str, target_date: datetime) -> bool:
        """
        Check if L4 memory is processed
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            target_date: Target date
            
        Returns:
            bool: Whether processed
        """
        async with self.lock:
            key = self._get_week_key(user_id, expert_id, target_date)
            return key in self._state["processed_l4_memories"] and len(self._state["processed_l4_memories"][key]) > 0
    
    async def is_l5_processed(self, user_id: str, expert_id: str, target_date: datetime) -> bool:
        """
        Check if L5 memory is processed
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            target_date: Target date
            
        Returns:
            bool: Whether processed
        """
        async with self.lock:
            key = self._get_month_key(user_id, expert_id, target_date)
            return key in self._state["processed_l5_memories"] and len(self._state["processed_l5_memories"][key]) > 0
    
    async def get_last_processed_timestamp(self, user_id: str, expert_id: str) -> Optional[datetime]:
        """
        Get last processing timestamp
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            
        Returns:
            Optional[datetime]: Last processing timestamp, None if not available
        """
        async with self.lock:
            key = self._get_key(user_id, expert_id)
            if key in self._state["last_processed_timestamps"]:
                timestamp_str = self._state["last_processed_timestamps"][key]
                try:
                    return datetime.fromisoformat(timestamp_str)
                except ValueError:
                    return None
            return None
    
    async def get_last_day(self, user_id: str, expert_id: str) -> Optional[date]:
        """
        Get last processing date
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            
        Returns:
            Optional[date]: Last processing date, None if not available
        """
        async with self.lock:
            key = self._get_key(user_id, expert_id)
            if key in self._state["user_expert_last_times"] and "last_day" in self._state["user_expert_last_times"][key]:
                date_str = self._state["user_expert_last_times"][key]["last_day"]
                try:
                    return date.fromisoformat(date_str)
                except ValueError:
                    return None
            return None
    
    async def get_last_week(self, user_id: str, expert_id: str) -> Optional[Tuple[int, int]]:
        """
        Get last processing week
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            
        Returns:
            Optional[Tuple[int, int]]: Last processing week (year, week), None if not available
        """
        async with self.lock:
            key = self._get_key(user_id, expert_id)
            if key in self._state["user_expert_last_times"] and "last_week" in self._state["user_expert_last_times"][key]:
                week_str = self._state["user_expert_last_times"][key]["last_week"]
                try:
                    year, week = week_str.split("-")
                    return (int(year), int(week))
                except (ValueError, IndexError):
                    return None
            return None
    
    async def get_last_month(self, user_id: str, expert_id: str) -> Optional[Tuple[int, int]]:
        """
        Get last processing month
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            
        Returns:
            Optional[Tuple[int, int]]: Last processing month (year, month), None if not available
        """
        async with self.lock:
            key = self._get_key(user_id, expert_id)
            if key in self._state["user_expert_last_times"] and "last_month" in self._state["user_expert_last_times"][key]:
                month_str = self._state["user_expert_last_times"][key]["last_month"]
                try:
                    year, month = month_str.split("-")
                    return (int(year), int(month))
                except (ValueError, IndexError):
                    return None
            return None
    
    async def clear_state(self) -> None:
        """Clear state"""
        async with self.lock:
            self._state = {
                "processed_l1_memories": {},
                "processed_l2_memories": {},
                "processed_l3_memories": {},
                "processed_l4_memories": {},
                "processed_l5_memories": {},
                "last_processed_timestamps": {},
                "session_records": {},
                "user_expert_last_times": {},
            }
            await self._save_state()
            
    async def close(self) -> None:
        """Close workflow state manager and save state"""
        try:
            await self._save_state()
            logger.info("Workflow state manager state saved")
        except Exception as e:
            logger.error(f"Failed to save workflow state: {e}")

    async def get_last_processed_time(self, user_id: str, expert_id: str) -> Optional[datetime]:
        """
        Get user-expert combination last processing time
        
        🔧 New: Support TokenGenerator time interval judgment
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            
        Returns:
            Last processing time, None if not available
        """
        try:
            async with self.lock:
                key = f"{user_id}_{expert_id}"
                
                # Get from last processing timestamp
                if key in self._state["last_processed_timestamps"]:
                    last_time = self._state["last_processed_timestamps"][key]
                    if isinstance(last_time, str):
                        return self.time_manager.parse_iso_time(last_time)
                    elif isinstance(last_time, datetime):
                        return last_time
                
                # Get from L1 memory records
                l1_key = f"{user_id}_{expert_id}_*"
                for k in self._state["processed_l1_memories"]:
                    if k.startswith(f"{user_id}_{expert_id}_"):
                        for memory_id, timestamp in self._state["processed_l1_memories"][k].items():
                            if isinstance(timestamp, str):
                                parsed_time = self.time_manager.parse_iso_time(timestamp)
                            else:
                                parsed_time = timestamp
                            
                            if parsed_time:
                                return parsed_time
                
                # Get from L2 memory records
                l2_key = f"{user_id}_{expert_id}_*"
                for k in self._state["processed_l2_memories"]:
                    if k.startswith(f"{user_id}_{expert_id}_"):
                        for memory_id, timestamp in self._state["processed_l2_memories"][k].items():
                            if isinstance(timestamp, str):
                                parsed_time = self.time_manager.parse_iso_time(timestamp)
                            else:
                                parsed_time = timestamp
                            
                            if parsed_time:
                                return parsed_time
                
                return None
                
        except Exception as e:
            logger.error(f"Failed to get last processing time: {e}")
            return None


# Global workflow state manager instance
_workflow_state_manager = None
_workflow_state_manager_lock = asyncio.Lock()


async def get_workflow_state_manager() -> WorkflowStateManager:
    """
    Get workflow state manager instance
    
    Returns:
        WorkflowStateManager: Workflow state manager instance
    """
    global _workflow_state_manager
    
    if _workflow_state_manager is None:
        async with _workflow_state_manager_lock:
            if _workflow_state_manager is None:
                _workflow_state_manager = WorkflowStateManager()
    
    return _workflow_state_manager
