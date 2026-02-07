"""
TiMem Dataset Parsing Module

Used to parse locomo format dialogue data, supporting batch processing and dialogue grouping.
"""

import json
import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path

from timem.utils.logging import get_logger

logger = get_logger(__name__)

@dataclass
class DialogueTurn:
    """Dialogue turn data class"""
    speaker: str
    dia_id: str
    text: str
    img_url: Optional[List[str]] = None
    blip_caption: Optional[str] = None
    query: Optional[str] = None

@dataclass
class ConversationSession:
    """Conversation session data class"""
    sample_id: str
    session_id: str
    date_time: str
    speaker_a: str
    speaker_b: str
    dialogues: List[DialogueTurn]
    total_turns: int

class LocomoDatasetParser:
    """Locomo dataset parser"""
    
    def __init__(self, data_dir: str = "data/locomo10_smart_split"):
        self.data_dir = Path(data_dir)
        self.logger = logging.getLogger(__name__)
    
    def load_conversation_file(self, file_path: str) -> ConversationSession:
        """Load single conversation file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Parse dialogue turns
            dialogues = []
            for dialogue in data.get("dialogues", []):
                turn = DialogueTurn(
                    speaker=dialogue.get("speaker", ""),
                    dia_id=dialogue.get("dia_id", ""),
                    text=dialogue.get("text", ""),
                    img_url=dialogue.get("img_url"),
                    blip_caption=dialogue.get("blip_caption"),
                    query=dialogue.get("query")
                )
                dialogues.append(turn)
            
            # Create session object
            session = ConversationSession(
                sample_id=data.get("sample_id", ""),
                session_id=data.get("session_id", ""),
                date_time=data.get("date_time", ""),
                speaker_a=data.get("speaker_a", ""),
                speaker_b=data.get("speaker_b", ""),
                dialogues=dialogues,
                total_turns=data.get("total_turns", 0)
            )
            
            self.logger.info(f"Successfully loaded conversation file: {file_path}, turns: {len(dialogues)}")
            return session
            
        except Exception as e:
            self.logger.error(f"Failed to load conversation file: {file_path}, error: {e}")
            raise
    
    def load_all_conversations(self) -> List[ConversationSession]:
        """Load all conversation files"""
        conversations = []
        
        if not self.data_dir.exists():
            self.logger.error(f"Data directory does not exist: {self.data_dir}")
            return conversations
        
        # Find all JSON files
        json_files = list(self.data_dir.glob("*.json"))
        
        for file_path in json_files:
            try:
                session = self.load_conversation_file(str(file_path))
                conversations.append(session)
            except Exception as e:
                self.logger.error(f"Failed to load file: {file_path}, error: {e}")
                continue
        
        self.logger.info(f"Successfully loaded {len(conversations)} conversation sessions")
        return conversations
    
    def group_dialogues_by_pairs(self, session: ConversationSession, 
                                group_size: int = 2) -> List[List[DialogueTurn]]:
        """Group dialogues by pairs"""
        dialogues = session.dialogues
        groups = []
        
        for i in range(0, len(dialogues), group_size):
            group = dialogues[i:i + group_size]
            groups.append(group)
        
        return groups
    
    def create_dialogue_pairs(self, session: ConversationSession) -> List[Dict[str, Any]]:
        """Create dialogue pairs, each group contains one sentence from each party"""
        pairs = []
        dialogues = session.dialogues
        
        for i in range(0, len(dialogues) - 1, 2):
            # Ensure enough dialogue turns
            if i + 1 < len(dialogues):
                pair = {
                    "session_id": session.session_id,
                    "sample_id": session.sample_id,
                    "date_time": session.date_time,
                    "speaker_a": session.speaker_a,
                    "speaker_b": session.speaker_b,
                    "turn_1": {
                        "speaker": dialogues[i].speaker,
                        "dia_id": dialogues[i].dia_id,
                        "text": dialogues[i].text,
                        "img_url": dialogues[i].img_url,
                        "blip_caption": dialogues[i].blip_caption,
                        "query": dialogues[i].query
                    },
                    "turn_2": {
                        "speaker": dialogues[i + 1].speaker,
                        "dia_id": dialogues[i + 1].dia_id,
                        "text": dialogues[i + 1].text,
                        "img_url": dialogues[i + 1].img_url,
                        "blip_caption": dialogues[i + 1].blip_caption,
                        "query": dialogues[i + 1].query
                    }
                }
                pairs.append(pair)
        
        return pairs
    
    def format_for_timem(self, dialogue_pair: Dict[str, Any], 
                        user_id: str = "test_user", 
                        expert_id: str = "test_expert") -> Dict[str, Any]:
        """Format dialogue pair as TiMem input format"""
        # Merge text from two dialogue turns
        turn_1_text = dialogue_pair["turn_1"]["text"]
        turn_2_text = dialogue_pair["turn_2"]["text"]
        
        # Build dialogue content
        dialogue_content = f"{dialogue_pair['turn_1']['speaker']}: {turn_1_text}\n{dialogue_pair['turn_2']['speaker']}: {turn_2_text}"
        
        # Build metadata
        metadata = {
            "dialogue_type": "conversation",
            "session_id": dialogue_pair["session_id"],
            "sample_id": dialogue_pair["sample_id"],
            "speaker_a": dialogue_pair["speaker_a"],
            "speaker_b": dialogue_pair["speaker_b"],
            "turn_1": {
                "speaker": dialogue_pair["turn_1"]["speaker"],
                "dia_id": dialogue_pair["turn_1"]["dia_id"],
                "img_url": dialogue_pair["turn_1"]["img_url"],
                "blip_caption": dialogue_pair["turn_1"]["blip_caption"],
                "query": dialogue_pair["turn_1"]["query"]
            },
            "turn_2": {
                "speaker": dialogue_pair["turn_2"]["speaker"],
                "dia_id": dialogue_pair["turn_2"]["dia_id"],
                "img_url": dialogue_pair["turn_2"]["img_url"],
                "blip_caption": dialogue_pair["turn_2"]["blip_caption"],
                "query": dialogue_pair["turn_2"]["query"]
            }
        }
        
        return {
            "session_id": dialogue_pair["session_id"],
            "user_id": user_id,
            "expert_id": expert_id,
            "content": dialogue_content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata
        }

def get_dataset_parser(data_dir: str = "data/locomo10_smart_split") -> LocomoDatasetParser:
    """Get dataset parser instance"""
    return LocomoDatasetParser(data_dir)