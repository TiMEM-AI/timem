"""
TiMem Locomo Dataset Parser
Responsible for parsing locomo dataset and converting it to TiMem memory model format.
"""
import json
import os
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime, timedelta
import re

from timem.models.memory import (
    Message, MessageRole, MemoryFragment, Memory, MemoryLevel,
    L1FragmentMemory, Entity, Relationship, KeyInformation, MemoryType
)
from timem.utils.logging import get_logger

logger = get_logger(__name__)

class LocomoParser:
    """
    Locomo Dataset Parser
    
    Responsible for parsing dialogue data in locomo dataset and converting it to TiMem memory model format.
    """
    
    def __init__(self, data_dir: str = "data/locomo10_smart_split"):
        """
        Initialize parser
        
        Args:
            data_dir: Path to locomo dataset directory
        """
        self.data_dir = Path(data_dir)
        self.logger = logger
        
        if not self.data_dir.exists():
            raise FileNotFoundError(f"Data directory does not exist: {data_dir}")
        
        self.logger.info(f"Initialize Locomo parser, data directory: {self.data_dir}")
    
    def list_sessions(self) -> List[str]:
        """
        List all available session files
        
        Returns:
            List of session file paths
        """
        session_files = []
        pattern = re.compile(r'locomo10_timem_conv-\d+_session_\d+\.json')
        
        for file_path in self.data_dir.glob("*.json"):
            if pattern.match(file_path.name):
                session_files.append(str(file_path))
        
        session_files.sort()
        self.logger.info(f"Found {len(session_files)} session files")
        return session_files
    
    def parse_session_file(self, file_path: str) -> Dict[str, Any]:
        """
        Parse a single session file
        
        Args:
            file_path: Session file path
            
        Returns:
            Parsed session data
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.logger.debug(f"Successfully parsed file: {file_path}")
            return data
        except Exception as e:
            self.logger.error(f"Failed to parse file {file_path}: {e}")
            raise
    
    def convert_to_messages(self, dialogues: List[Dict[str, Any]]) -> List[Message]:
        """
        Convert locomo dialogues to TiMem message format
        
        Args:
            dialogues: locomo dialogue data
            
        Returns:
            Converted message list
        """
        messages = []
        
        for dialogue in dialogues:
            try:
                # Keep original speaker name
                speaker = dialogue.get("speaker", "unknown")
                
                # Dynamically determine role: all speakers are treated as user role
                # This preserves original character names without hardcoding
                role = MessageRole.USER
                
                # Build message content
                content = dialogue.get("text", "")
                
                # If there are images, add to content
                if dialogue.get("img_url"):
                    img_urls = dialogue["img_url"]
                    if isinstance(img_urls, list) and img_urls:
                        content += f"\n[Image: {img_urls[0]}]"
                
                # If there is image caption, add to content
                if dialogue.get("blip_caption"):
                    content += f"\n[Image caption: {dialogue['blip_caption']}]"
                
                # Create message, use dialogue ID as timestamp substitute
                # Since locomo dataset has no precise timestamp, we use dialogue ID sequence number
                dia_id = dialogue.get("dia_id", "")
                timestamp = self._parse_dia_id_to_timestamp(dia_id)
                
                # Create message
                message = Message(
                    role=role,
                    content=content.strip(),
                    timestamp=timestamp,
                    metadata={
                        "speaker": speaker,  # Keep original speaker name
                        "dia_id": dialogue.get("dia_id"),
                        "img_url": dialogue.get("img_url"),
                        "blip_caption": dialogue.get("blip_caption"),
                        "query": dialogue.get("query")
                    }
                )
                messages.append(message)
                
            except Exception as e:
                self.logger.warning(f"Skip problematic dialogue: {dialogue.get('dia_id', 'unknown')}, error: {e}")
                continue
        
        return messages
    
    def _parse_dia_id_to_timestamp(self, dia_id: str) -> float:
        """
        Convert dialogue ID to timestamp
        
        Args:
            dia_id: Dialogue ID, format like "D1:1", "D1:2" etc
            
        Returns:
            Timestamp
        """
        try:
            # Parse dialogue ID, extract sequence number
            if ":" in dia_id:
                parts = dia_id.split(":")
                if len(parts) == 2:
                    # Use sequence number as basis for timestamp
                    sequence_num = int(parts[1])
                    # Use 2023-05-08 as base time, 1 minute interval per dialogue
                    base_time = datetime(2023, 5, 8, 13, 56, 0)  # 1:56 pm on 8 May, 2023
                    timestamp = base_time + timedelta(minutes=sequence_num - 1)
                    return timestamp.timestamp()
        except (ValueError, IndexError):
            pass
        
        # If parsing fails, return current time
        return datetime.utcnow().timestamp()
    
    def extract_entities(self, messages: List[Message]) -> List[Entity]:
        """
        Extract entities from messages
        
        Args:
            messages: Message list
            
        Returns:
            List of extracted entities
        """
        entities = []
        speakers_seen = set()
        
        # Dynamically extract speaker information from messages
        for message in messages:
            content = message.content
            speaker = message.metadata.get("speaker", "unknown") if message.metadata else "unknown"
            
            # Dynamically add speaker entity
            if speaker != "unknown" and speaker not in speakers_seen:
                entities.append(Entity(
                    name=speaker,
                    type="person",
                    attributes={"role": "speaker"},
                    extracted_from=message.metadata.get("dia_id")
                ))
                speakers_seen.add(speaker)
            
            # Extract location names
            if "Japan" in content or "Japanese" in content:
                entities.append(Entity(
                    name="Japan",
                    type="location",
                    attributes={"category": "country"},
                    extracted_from=message.metadata.get("dia_id")
                ))
            
            if "Boston" in content:
                entities.append(Entity(
                    name="Boston",
                    type="location",
                    attributes={"category": "city"},
                    extracted_from=message.metadata.get("dia_id")
                ))
        
        # Deduplication
        unique_entities = []
        seen = set()
        for entity in entities:
            key = (entity.name, entity.type)
            if key not in seen:
                seen.add(key)
                unique_entities.append(entity)
        
        return unique_entities
    
    def extract_key_information(self, messages: List[Message]) -> List[KeyInformation]:
        """
        Extract key information from messages
        
        Args:
            messages: Message list
            
        Returns:
            List of extracted key information
        """
        key_info = []
        
        for message in messages:
            content = message.content
            
            # Identify decisional information
            if any(keyword in content.lower() for keyword in ["plan", "going", "trip", "stay", "move"]):
                key_info.append(KeyInformation(
                    content=content,
                    type=MemoryType.DECISIONAL,
                    importance=0.8
                ))
            
            # Identify factual information
            elif any(keyword in content.lower() for keyword in ["mansion", "place", "park", "event"]):
                key_info.append(KeyInformation(
                    content=content,
                    type=MemoryType.FACTUAL,
                    importance=0.7
                ))
            
            # Identify emotional information
            elif any(keyword in content.lower() for keyword in ["excited", "awesome", "amazing", "great"]):
                key_info.append(KeyInformation(
                    content=content,
                    type=MemoryType.EMOTIONAL,
                    importance=0.6
                ))
        
        return key_info
    
    def create_memory_fragment(self, session_data: Dict[str, Any]) -> L1FragmentMemory:
        """
        Create memory fragment from session data
        
        Args:
            session_data: Session data
            
        Returns:
            Created memory fragment
        """
        try:
            # Convert messages
            messages = self.convert_to_messages(session_data["dialogues"])
            
            # Extract entities and key information
            entities = self.extract_entities(messages)
            key_info = self.extract_key_information(messages)
            
            # Create fragment ID
            fragment_id = f"{session_data['sample_id']}_{session_data['session_id']}"
            
            # Create memory fragment
            # Must obtain valid timestamp from session_data
            created_at = None
            if "date_time" in session_data and session_data["date_time"]:
                parsed_time = self.parse_locomo_datetime(session_data["date_time"])
                if parsed_time:
                    created_at = parsed_time.timestamp()
            
            # If no valid timestamp, reject processing
            if created_at is None:
                raise ValueError(f"Session {session_data.get('session_id', 'unknown')} missing valid timestamp, cannot process")
            
            fragment = L1FragmentMemory(
                id=fragment_id,
                session_id=session_data["session_id"],
                dialogue=messages,
                summary="",  # Initially empty, will be generated by summarizer later
                keywords=self._extract_keywords(messages),
                key_information=key_info,
                entities=entities,
                importance=self._calculate_importance(messages),
                temporal_position=int(session_data["session_id"].split("_")[-1]),
                created_at=created_at  # Set correct timestamp
            )
            
            self.logger.debug(f"Created memory fragment: {fragment_id}")
            return fragment
            
        except Exception as e:
            self.logger.error(f"Failed to create memory fragment: {e}")
            raise
    
    def create_session_memory(self, fragments: List[L1FragmentMemory]) -> Memory:
        """
        Create session memory from memory fragments
        
        Args:
            fragments: List of memory fragments
            
        Returns:
            Created session memory
        """
        if not fragments:
            raise ValueError("Fragment list cannot be empty")
        
        # Get session_id from first fragment
        session_id = fragments[0].session_id
        
        # Merge entities and key information from all fragments
        all_entities = []
        all_key_info = []
        all_keywords = []
        
        for fragment in fragments:
            all_entities.extend(fragment.entities)
            all_key_info.extend(fragment.key_information)
            all_keywords.extend(fragment.keywords)
        
        # Deduplicate
        unique_entities = self._deduplicate_entities(all_entities)
        unique_keywords = list(set(all_keywords))
        
        # Create session memory
        session_memory = Memory(
            id=f"session_{session_id}",
            user_id="Calvin",
            expert_id="Dave",
            session_id=session_id,
            summary="",  # Will be generated by summarizer later
            keywords=unique_keywords,
            key_information=all_key_info,
            entities=unique_entities,
            importance=sum(f.importance for f in fragments) / len(fragments),
            fragments=[f.id for f in fragments],
            raw_content=self._combine_fragment_content(fragments)
        )
        
        return session_memory
    
    def _extract_keywords(self, messages: List[Message]) -> List[str]:
        """Extract keywords"""
        keywords = []
        
        for message in messages:
            content = message.content.lower()
            
            # Simple keyword extraction
            if "japan" in content or "japanese" in content:
                keywords.append("Japan")
            if "boston" in content:
                keywords.append("Boston")
            if "mansion" in content:
                keywords.append("mansion")
            if "trip" in content:
                keywords.append("trip")
            if "music" in content or "musician" in content:
                keywords.append("music")
            if "park" in content:
                keywords.append("park")
            if "culture" in content:
                keywords.append("culture")
        
        return list(set(keywords))
    
    def _calculate_importance(self, messages: List[Message]) -> float:
        """Calculate importance score"""
        importance = 0.5
        
        # Adjust importance based on message count
        if len(messages) > 15:
            importance += 0.2
        elif len(messages) > 10:
            importance += 0.1
        
        # Adjust based on content complexity
        total_length = sum(len(msg.content) for msg in messages)
        if total_length > 1000:
            importance += 0.1
        
        return min(importance, 1.0)
    
    def _deduplicate_entities(self, entities: List[Entity]) -> List[Entity]:
        """Deduplicate entities"""
        unique_entities = []
        seen = set()
        
        for entity in entities:
            key = (entity.name, entity.type)
            if key not in seen:
                seen.add(key)
                unique_entities.append(entity)
        
        return unique_entities
    
    def _combine_fragment_content(self, fragments: List[L1FragmentMemory]) -> str:
        """Combine fragment content"""
        content_parts = []
        
        for fragment in fragments:
            fragment_content = []
            for message in fragment.dialogue:
                fragment_content.append(f"{message.role.value}: {message.content}")
            content_parts.append("\n".join(fragment_content))
        
        return "\n\n---\n\n".join(content_parts)
    
    def load_session_data(self, sample_id: str) -> List[Dict[str, Any]]:
        """
        Load all session data for specified sample
        
        Args:
            sample_id: Sample ID (e.g. "conv-50")
            
        Returns:
            List of session data
        """
        session_files = self.list_sessions()
        matching_files = [f for f in session_files if sample_id in f]
        
        sessions = []
        for file_path in matching_files:
            try:
                session_data = self.parse_session_file(file_path)
                sessions.append(session_data)
            except Exception as e:
                self.logger.warning(f"Skipping file {file_path}: {e}")
        
        # Sort by session ID
        sessions.sort(key=lambda x: int(x["session_id"].split("_")[-1]))
        
        self.logger.info(f"Loaded {len(sessions)} sessions, sample ID: {sample_id}")
        return sessions
    
    def get_available_samples(self) -> List[str]:
        """
        Get all available sample IDs
        
        Returns:
            List of sample IDs
        """
        session_files = self.list_sessions()
        samples = set()
        
        for file_path in session_files:
            # Extract sample ID from filename
            filename = os.path.basename(file_path)
            match = re.search(r'conv-(\d+)', filename)
            if match:
                samples.add(f"conv-{match.group(1)}")
        
        sample_list = sorted(list(samples))
        self.logger.info(f"Found {len(sample_list)} samples")
        return sample_list