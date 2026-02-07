"""
TiMem Character ID Resolver
Used to get database ID by character name, support user group isolation
"""

import asyncio
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass

from services.character_service import CharacterService
from timem.utils.logging import get_logger


@dataclass
class UserGroup:
    """User group information"""
    conversation_id: str
    speaker_a: str
    speaker_b: str
    speaker_a_id: Optional[str] = None
    speaker_b_id: Optional[str] = None
    user_group_ids: Optional[Set[str]] = None  # User group ID set


class CharacterIdResolver:
    """Character ID resolver"""
    
    def __init__(self):
        self.character_service = CharacterService()
        self.logger = get_logger(__name__)
        self._character_cache: Dict[str, str] = {}  # Name to ID cache
        
    async def get_character_id_by_name(self, name: str) -> Optional[str]:
        """Get character ID by name
        
        Args:
            name: Character name
            
        Returns:
            Character ID, or None if not found
        """
        try:
            # Check cache first
            if name in self._character_cache:
                return self._character_cache[name]
            
            # Query from database
            character_info = await self.character_service.get_character_by_name(name)
            
            if character_info:
                character_id = character_info["id"]
                # Update cache
                self._character_cache[name] = character_id
                self.logger.info(f"Successfully got character {name} ID: {character_id}")
                return character_id
            else:
                self.logger.warning(f"Character {name} ID not found")
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to get character {name} ID: {e}")
            return None
    
    async def resolve_user_group(self, conversation_id: str, speaker_a: str, speaker_b: str) -> Optional[UserGroup]:
        """Resolve user group information
        
        Args:
            conversation_id: Conversation ID
            speaker_a: Speaker A
            speaker_b: Speaker B
            
        Returns:
            User group information, or None if resolution failed
        """
        try:
            # Get IDs for both speakers
            speaker_a_id = await self.get_character_id_by_name(speaker_a)
            speaker_b_id = await self.get_character_id_by_name(speaker_b)
            
            if not speaker_a_id or not speaker_b_id:
                self.logger.error(f"Cannot get complete ID information for user group {speaker_a} & {speaker_b}")
                return None
            
            # Create user group ID set (bidirectional relationship)
            user_group_ids = {speaker_a_id, speaker_b_id}
            
            user_group = UserGroup(
                conversation_id=conversation_id,
                speaker_a=speaker_a,
                speaker_b=speaker_b,
                speaker_a_id=speaker_a_id,
                speaker_b_id=speaker_b_id,
                user_group_ids=user_group_ids
            )
            
            self.logger.info(f"Successfully resolved user group {conversation_id}: {speaker_a}({speaker_a_id}) & {speaker_b}({speaker_b_id})")
            return user_group
            
        except Exception as e:
            self.logger.error(f"Failed to resolve user group {conversation_id}: {e}")
            return None
    
    async def resolve_multiple_user_groups(self, conversations: Dict[str, Dict[str, Any]]) -> Dict[str, UserGroup]:
        """Batch resolve multiple user groups
        
        Args:
            conversations: Conversation information dictionary
            
        Returns:
            Mapping from conversation ID to user group
        """
        user_groups = {}
        
        for conv_id, conv_info in conversations.items():
            speaker_a = conv_info.get("speaker_a")
            speaker_b = conv_info.get("speaker_b")
            
            if speaker_a and speaker_b:
                user_group = await self.resolve_user_group(conv_id, speaker_a, speaker_b)
                if user_group:
                    user_groups[conv_id] = user_group
            else:
                self.logger.warning(f"Conversation {conv_id} missing speaker information")
        
        self.logger.info(f"Successfully resolved {len(user_groups)} user groups")
        return user_groups
    
    def get_user_group_filter_conditions(self, user_group: UserGroup) -> Dict[str, Any]:
        """Get user group filter conditions for database query
        
        Args:
            user_group: User group information
            
        Returns:
            Filter condition dictionary with user_id and expert_id conditions
        """
        if not user_group.user_group_ids:
            return {}
        
        # User group contains two IDs, need to query all possible combinations
        # Including: (user_id=A, expert_id=B) and (user_id=B, expert_id=A)
        user_group_list = list(user_group.user_group_ids)
        
        filter_conditions = {
            "user_group_ids": user_group_list,
            "sql_conditions": [
                # Condition 1: user_id=A, expert_id=B
                {
                    "user_id": user_group_list[0],
                    "expert_id": user_group_list[1]
                },
                # Condition 2: user_id=B, expert_id=A  
                {
                    "user_id": user_group_list[1],
                    "expert_id": user_group_list[0]
                }
            ]
        }
        
        return filter_conditions
    
    async def validate_user_group_exists(self, user_group: UserGroup) -> bool:
        """Validate if user group has related memories in database
        
        Args:
            user_group: User group information
            
        Returns:
            Whether related memories exist
        """
        try:
            # Can add validation logic here to check if database has memories for this user group
            # Temporarily return True, can validate in actual usage later
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to validate user group {user_group.conversation_id}: {e}")
            return False


# Global instance
_character_id_resolver_instance = None

def get_character_id_resolver() -> CharacterIdResolver:
    """Get character ID resolver instance"""
    global _character_id_resolver_instance
    if _character_id_resolver_instance is None:
        _character_id_resolver_instance = CharacterIdResolver()
    return _character_id_resolver_instance

