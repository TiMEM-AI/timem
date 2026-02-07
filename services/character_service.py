"""
TiMem Character Registration Service
Provides character role management functions, including creation, query, update, and deletion
"""

import asyncio
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_, or_
from sqlalchemy.orm import selectinload

from storage.postgres_store import Character
from storage.base_storage_interface import UnifiedStorageInterface
from storage.memory_storage_manager import get_memory_storage_manager_async
from timem.utils.logging import get_logger

class CharacterService:
    """Character Registration Service"""
    
    def __init__(self):
        self.logger = get_logger(__name__)
        self.sql_store: Optional[UnifiedStorageInterface] = None
        
    async def _get_sql_store(self) -> UnifiedStorageInterface:
        """Get SQL storage instance (through storage manager)"""
        if self.sql_store is None:
            storage_manager = await get_memory_storage_manager_async()
            # Get SQL adapter's underlying storage from storage manager
            if hasattr(storage_manager.default_adapter, '_sql_store'):
                self.sql_store = storage_manager.default_adapter._sql_store
            elif hasattr(storage_manager.default_adapter, '_postgres_store'):
                # If using PostgreSQL, can also handle Character table
                self.sql_store = storage_manager.default_adapter._postgres_store
            else:
                raise RuntimeError("Unable to get SQL storage instance")
        return self.sql_store
    
    async def create_character(self, 
                             name: str, 
                             character_type: str = "user",  # Unified use of user
                             display_name: Optional[str] = None,
                             description: Optional[str] = None,
                             metadata: Optional[Dict[str, Any]] = None,
                             character_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a character role
        
        Args:
            name: Character name
            character_type: Character type (user/expert/assistant/other)
            display_name: Display name
            description: Description
            metadata: Metadata
            character_id: Character ID (optional, auto-generated if not provided)
            
        Returns:
            Created character information
        """
        try:
            sql_store = await self._get_sql_store()
            
            # Check if name already exists
            existing = await self.get_character_by_name(name)
            if existing:
                raise ValueError(f"Character name '{name}' already exists")
            
            # Generate ID
            if character_id is None:
                character_id = str(uuid.uuid4())
            
            # Create character record
            character_data = {
                "id": character_id,
                "name": name,
                "character_type": character_type,
                "display_name": display_name,
                "description": description,
                "metadata_json": metadata or {},
                "is_active": True,
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            }
            
            session_cm = await sql_store._get_session_cm()
            async with session_cm as session:
                try:
                    character = Character(**character_data)
                    session.add(character)
                    await session.commit()
                    await session.refresh(character)
                    
                    self.logger.info(f"Successfully created character: {name} (ID: {character_id})")
                    
                    return {
                        "id": character.id,
                        "name": character.name,
                        "character_type": character.character_type,
                        "display_name": character.display_name,
                        "description": character.description,
                        "metadata": character.metadata_json,
                        "is_active": character.is_active,
                        "created_at": character.created_at,
                        "updated_at": character.updated_at
                    }
                except Exception as e:
                    await session.rollback()
                    raise e
                    
        except Exception as e:
            self.logger.error(f"Failed to create character: {e}")
            raise
    
    async def get_character_by_id(self, character_id: str) -> Optional[Dict[str, Any]]:
        """Get character information by ID
        
        Args:
            character_id: Character ID
            
        Returns:
            Character information dictionary, if not found returns None
        """
        try:
            sql_store = await self._get_sql_store()
            
            session_cm = await sql_store._get_session_cm()
            async with session_cm as session:
                result = await session.execute(
                    select(Character).where(Character.id == character_id)
                )
                character = result.scalar_one_or_none()
                
                if character:
                    return {
                        "id": character.id,
                        "name": character.name,
                        "character_type": character.character_type,
                        "display_name": character.display_name,
                        "description": character.description,
                        "metadata": character.metadata_json,
                        "is_active": character.is_active,
                        "created_at": character.created_at,
                        "updated_at": character.updated_at
                    }
                return None
                    
        except Exception as e:
            self.logger.error(f"Failed to get character by ID: {e}")
            raise
    
    async def get_character_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get character information by name
        
        Args:
            name: Character name
            
        Returns:
            Character information dictionary, if not found returns None
        """
        try:
            sql_store = await self._get_sql_store()
            
            session_cm = await sql_store._get_session_cm()
            async with session_cm as session:
                result = await session.execute(
                    select(Character).where(Character.name == name)
                )
                character = result.scalar_one_or_none()
                
                if character:
                    return {
                        "id": character.id,
                        "name": character.name,
                        "character_type": character.character_type,
                        "display_name": character.display_name,
                        "description": character.description,
                        "metadata": character.metadata_json,
                        "is_active": character.is_active,
                        "created_at": character.created_at,
                        "updated_at": character.updated_at
                    }
                return None
                    
        except Exception as e:
            self.logger.error(f"Failed to get character by name: {e}")
            raise
    
    async def get_characters(self, 
                           character_type: Optional[str] = None,
                           is_active: Optional[bool] = None,
                           limit: int = 100) -> List[Dict[str, Any]]:
        """Get all character roles list
        
        Args:
            character_type: Character type filter
            is_active: Active status filter
            limit: Return count limit
            
        Returns:
            List[Dict[str, Any]]: Character roles list
        """
        try:
            sql_store = await self._get_sql_store()
            
            session_cm = await sql_store._get_session_cm()
            async with session_cm as session:
                # Build query conditions
                conditions = []
                
                if character_type:
                    conditions.append(Character.character_type == character_type)
                
                if is_active is not None:
                    conditions.append(Character.is_active == is_active)
                
                # Build query
                query = select(Character)
                if conditions:
                    query = query.where(and_(*conditions))
                
                # Add limit
                query = query.limit(limit)
                
                # Execute query
                result = await session.execute(query)
                characters = result.scalars().all()
                
                # Convert to dictionary list
                character_list = []
                for char in characters:
                    character_dict = {
                        "character_id": char.id,  # Use id field as character_id
                        "name": char.name,
                        "character_type": char.character_type,
                        "display_name": char.display_name,
                        "description": char.description,
                        "is_active": char.is_active,
                        "created_at": char.created_at.isoformat() if char.created_at else None,
                        "updated_at": char.updated_at.isoformat() if char.updated_at else None,
                        "metadata": char.metadata_json  # Use metadata_json field
                    }
                    character_list.append(character_dict)
                
                self.logger.info(f"Retrieved {len(character_list)} character roles")
                return character_list
                
        except Exception as e:
            self.logger.error(f"Failed to get character roles list: {e}")
            raise

    async def search_characters(self, 
                              name: Optional[str] = None,
                              character_type: Optional[str] = None,
                              is_active: Optional[bool] = None,
                              page: int = 1,
                              size: int = 20) -> Dict[str, Any]:
        """Search character roles
        
        Args:
            name: Character name (supports fuzzy search)
            character_type: Character type
            is_active: Active status
            page: Page number
            size: Page size
            
        Returns:
            Search results
        """
        try:
            sql_store = await self._get_sql_store()
            
            session_cm = await sql_store._get_session_cm()
            async with session_cm as session:
                # Build query conditions
                conditions = []
                
                if name:
                    conditions.append(Character.name.ilike(f"%{name}%"))
                
                if character_type:
                    conditions.append(Character.character_type == character_type)
                
                if is_active is not None:
                    conditions.append(Character.is_active == is_active)
                
                # Build query
                query = select(Character)
                if conditions:
                    query = query.where(and_(*conditions))
                
                # Add pagination
                offset = (page - 1) * size
                query = query.offset(offset).limit(size)
                
                # Execute query
                result = await session.execute(query)
                characters = result.scalars().all()
                
                # Count total
                count_query = select(Character)
                if conditions:
                    count_query = count_query.where(and_(*conditions))
                count_result = await session.execute(count_query)
                total = len(count_result.scalars().all())
                
                # Convert to dictionary list
                character_list = []
                for character in characters:
                    character_list.append({
                        "id": character.id,
                        "name": character.name,
                        "character_type": character.character_type,
                        "display_name": character.display_name,
                        "description": character.description,
                        "metadata": character.metadata_json,
                        "is_active": character.is_active,
                        "created_at": character.created_at,
                        "updated_at": character.updated_at
                    })
                
                return {
                    "characters": character_list,
                    "total": total,
                    "page": page,
                    "size": size
                }
                    
        except Exception as e:
            self.logger.error(f"Failed to search characters: {e}")
            raise
    
    async def update_character(self, 
                             character_id: str,
                             name: Optional[str] = None,
                             character_type: Optional[str] = None,
                             display_name: Optional[str] = None,
                             description: Optional[str] = None,
                             metadata: Optional[Dict[str, Any]] = None,
                             is_active: Optional[bool] = None) -> Optional[Dict[str, Any]]:
        """Update character information
        
        Args:
            character_id: Character ID
            name: Character name
            character_type: Character type
            display_name: Display name
            description: Description
            metadata: Metadata
            is_active: Active status
            
        Returns:
            Updated character information, if not found returns None
        """
        try:
            sql_store = await self._get_sql_store()
            
            # Check if character exists
            existing = await self.get_character_by_id(character_id)
            if not existing:
                return None
            
            # Check if name conflicts with other characters
            if name and name != existing["name"]:
                name_conflict = await self.get_character_by_name(name)
                if name_conflict:
                    raise ValueError(f"Character name '{name}' already exists")
            
            # Build update data
            update_data = {}
            if name is not None:
                update_data["name"] = name
            if character_type is not None:
                update_data["character_type"] = character_type
            if display_name is not None:
                update_data["display_name"] = display_name
            if description is not None:
                update_data["description"] = description
            if metadata is not None:
                update_data["metadata_json"] = metadata
            if is_active is not None:
                update_data["is_active"] = is_active
            
            update_data["updated_at"] = datetime.now()
            
            if not update_data:
                return existing
            
            session_cm = await sql_store._get_session_cm()
            async with session_cm as session:
                try:
                    await session.execute(
                        update(Character)
                        .where(Character.id == character_id)
                        .values(**update_data)
                    )
                    await session.commit()
                    
                    self.logger.info(f"Successfully updated character: {character_id}")
                    
                    return await self.get_character_by_id(character_id)
                except Exception as e:
                    await session.rollback()
                    raise e
                    
        except Exception as e:
            self.logger.error(f"Failed to update character: {e}")
            raise
    
    async def delete_character(self, character_id: str) -> bool:
        """Delete character role
        
        Args:
            character_id: Character ID
            
        Returns:
            Whether deletion was successful
        """
        try:
            sql_store = await self._get_sql_store()
            
            # Check if character exists
            existing = await self.get_character_by_id(character_id)
            if not existing:
                return False
            
            session_cm = await sql_store._get_session_cm()
            async with session_cm as session:
                try:
                    await session.execute(
                        delete(Character).where(Character.id == character_id)
                    )
                    await session.commit()
                    
                    self.logger.info(f"Successfully deleted character: {character_id}")
                    return True
                except Exception as e:
                    await session.rollback()
                    raise e
                    
        except Exception as e:
            self.logger.error(f"Failed to delete character: {e}")
            raise
    
    async def get_character_id_by_name(self, name: str) -> Optional[str]:
        """Get character ID by name
        
        Args:
            name: Character name
            
        Returns:
            Character ID, if not found returns None
        """
        character = await self.get_character_by_name(name)
        return character["id"] if character else None
    
    async def get_character_name_by_id(self, character_id: str) -> Optional[str]:
        """Get character name by ID
        
        Args:
            character_id: Character ID
            
        Returns:
            Character name, if not found returns None
        """
        character = await self.get_character_by_id(character_id)
        return character["name"] if character else None
    
    async def register_character_from_conversation_id(self, conversation_id: str) -> str:
        """Extract character information from conversation ID and register
        
        Args:
            conversation_id: Conversation ID (format: conv26_1756314553_Caroline)
            
        Returns:
            Registered character ID
        """
        try:
            # Parse conversation ID format: conv26_1756314553_Caroline
            parts = conversation_id.split('_')
            if len(parts) >= 3:
                # Extract character name (last part)
                character_name = parts[-1]
                
                # Determine character type
                character_type = "user"  # Default to user
                
                # Check if already exists
                existing = await self.get_character_by_name(character_name)
                if existing:
                    return existing["id"]
                
                # Create new character
                character = await self.create_character(
                    name=character_name,
                    character_type=character_type,
                    display_name=character_name,
                    description=f"Automatically registered character from conversation ID: {conversation_id}",
                    metadata={"source": "conversation_id", "conversation_id": conversation_id}
                )
                
                return character["id"]
            else:
                raise ValueError(f"Invalid conversation ID format: {conversation_id}")
                
        except Exception as e:
            self.logger.error(f"Failed to register character from conversation ID: {e}")
            raise

    async def register_characters_from_conversation_data(self, speakers: List[str], conversation_id: str = None) -> Tuple[str, str]:
        """Register users from speakers list in conversation data and return IDs of first and second speakers
        
        Args:
            speakers: List of speakers, containing two names [speaker1, speaker2]
            conversation_id: Conversation ID, optional, used for metadata recording
            
        Returns:
            Tuple[str, str]: (speaker1_id, speaker2_id)
        """
        if len(speakers) != 2:
            raise ValueError(f"Speakers list should contain 2 speakers, currently has {len(speakers)}")
        
        speaker1_name, speaker2_name = speakers[0], speakers[1]
        self.logger.info(f"Start registering speakers: {speaker1_name} and {speaker2_name}")
        
        # Register first speaker
        speaker1_id = await self.ensure_character_registered(
            name=speaker1_name,
            source_info={"conversation_id": conversation_id, "role": "speaker1"} if conversation_id else None
        )
        
        # Register second speaker
        speaker2_id = await self.ensure_character_registered(
            name=speaker2_name,
            source_info={"conversation_id": conversation_id, "role": "speaker2"} if conversation_id else None
        )
        
        self.logger.info(f"Successfully registered speakers: {speaker1_name} (ID: {speaker1_id}) and {speaker2_name} (ID: {speaker2_id})")
        return speaker1_id, speaker2_id

    async def ensure_character_registered(self, 
                                        name: str, 
                                        source_info: Dict[str, Any] = None) -> str:
        """Ensure character is registered, create if not exists
        
        Args:
            name: Character name
            source_info: Source information for metadata
            
        Returns:
            Character ID
        """
        # Check if already exists
        existing = await self.get_character_by_name(name)
        if existing:
            self.logger.info(f"Character '{name}' already exists, ID: {existing['id']}")
            return existing["id"]
        
        # Create new character
        metadata = {"auto_registered": True}
        if source_info:
            metadata.update(source_info)
        
        character = await self.create_character(
            name=name,
            character_type="user",  # Default to user
            display_name=name,
            description=f"Conversation participant: {name}",
            metadata=metadata
        )
        
        self.logger.info(f"Successfully created new character: {name} (ID: {character['id']})")
        return character["id"]

    async def get_character_ids_by_names(self, names: List[str]) -> Dict[str, Optional[str]]:
        """Batch get character IDs
        
        Args:
            names: List of character names
            
        Returns:
            Dict[str, Optional[str]]: Mapping from name to ID, None if not found
        """
        result = {}
        for name in names:
            character = await self.get_character_by_name(name)
            result[name] = character["id"] if character else None
        return result

    async def validate_character_pair_for_memory_generation(self, speaker1_id: str, speaker2_id: str) -> Tuple[bool, str]:
        """Validate if speaker pair is suitable for memory generation
        
        Args:
            speaker1_id: First speaker ID
            speaker2_id: Second speaker ID
            
        Returns:
            Tuple[bool, str]: (is_valid, error_message)
        """
        try:
            # Check if first speaker exists
            speaker1 = await self.get_character_by_id(speaker1_id)
            if not speaker1:
                return False, f"Speaker ID does not exist: {speaker1_id}"
            
            speaker2 = await self.get_character_by_id(speaker2_id)
            if not speaker2:
                return False, f"Speaker ID does not exist: {speaker2_id}"
            
            # Check if speakers are active
            if not speaker1.get("is_active", True):
                return False, f"Speaker is disabled: {speaker1['name']} ({speaker1_id})"
            
            if not speaker2.get("is_active", True):
                return False, f"Speaker is disabled: {speaker2['name']} ({speaker2_id})"
            
            # Ensure two speakers are not the same person
            if speaker1_id == speaker2_id:
                return False, f"Two speakers cannot be the same person: {speaker1['name']}"
            
            self.logger.info(f"Speaker validation passed: {speaker1['name']} ({speaker1_id}) and {speaker2['name']} ({speaker2_id})")
            return True, ""
            
        except Exception as e:
            return False, f"Speaker pair validation failed: {str(e)}"

# Global instance
_character_service = None

def get_character_service() -> CharacterService:
    """Get character registration service instance"""
    global _character_service
    if _character_service is None:
        _character_service = CharacterService()
    return _character_service
