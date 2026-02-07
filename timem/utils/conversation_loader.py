"""
TiMem Conversation Data Loader
Used to load conversation information from locomo10_smart_split dataset and extract character names
"""

import json
import os
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

from timem.utils.logging import get_logger


class ConversationLoader:
    """Conversation data loader"""
    
    def __init__(self, data_dir: str = "data/locomo10_smart_split"):
        self.data_dir = Path(data_dir)
        self.logger = get_logger(__name__)
        
    def load_conversation_data(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Load data for specified conversation
        
        Args:
            conversation_id: Conversation ID, e.g. "conv-26"
            
        Returns:
            Conversation data dict containing speaker_a and speaker_b info
        """
        try:
            # Find first session file for this conversation
            session_files = list(self.data_dir.glob(f"locomo10_timem_{conversation_id}_session_*.json"))
            
            if not session_files:
                self.logger.warning(f"No session files found for conversation {conversation_id}")
                return None
            
            # Use first session file to get speaker info
            first_session_file = sorted(session_files)[0]
            
            with open(first_session_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            
            # Extract speaker info
            conversation_info = {
                "conversation_id": conversation_id,
                "speaker_a": session_data.get("speaker_a"),
                "speaker_b": session_data.get("speaker_b"),
                "session_count": len(session_files),
                "source_file": str(first_session_file)
            }
            
            self.logger.info(f"Successfully loaded conversation {conversation_id}: {conversation_info['speaker_a']} & {conversation_info['speaker_b']}")
            return conversation_info
            
        except Exception as e:
            self.logger.error(f"Failed to load conversation {conversation_id}: {e}")
            return None
    
    def get_all_conversations(self) -> Dict[str, Dict[str, Any]]:
        """Get all available conversation information
        
        Returns:
            Mapping from conversation ID to conversation info
        """
        conversations = {}
        
        try:
            # Find all timem session files
            session_files = list(self.data_dir.glob("locomo10_timem_conv-*_session_*.json"))
            
            for session_file in session_files:
                # Extract conversation_id from filename
                filename = session_file.name
                if "conv-" in filename:
                    conversation_id = filename.split("_session_")[0].replace("locomo10_timem_", "")
                    
                    if conversation_id not in conversations:
                        # Load conversation info
                        conv_info = self.load_conversation_data(conversation_id)
                        if conv_info:
                            conversations[conversation_id] = conv_info
            
            self.logger.info(f"Found {len(conversations)} conversations total")
            return conversations
            
        except Exception as e:
            self.logger.error(f"Failed to get all conversations: {e}")
            return {}
    
    def get_conversation_speakers(self, conversation_id: str) -> Optional[Tuple[str, str]]:
        """Get two speaker names for specified conversation
        
        Args:
            conversation_id: Conversation ID
            
        Returns:
            (speaker_a, speaker_b) tuple, returns None if failed
        """
        conv_info = self.load_conversation_data(conversation_id)
        if conv_info and conv_info.get("speaker_a") and conv_info.get("speaker_b"):
            return (conv_info["speaker_a"], conv_info["speaker_b"])
        return None


# Global instance
_conversation_loader_instance = None

def get_conversation_loader() -> ConversationLoader:
    """Get conversation loader instance"""
    global _conversation_loader_instance
    if _conversation_loader_instance is None:
        _conversation_loader_instance = ConversationLoader()
    return _conversation_loader_instance
