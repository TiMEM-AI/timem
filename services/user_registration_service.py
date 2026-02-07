"""
TiMem User Registration Service - Independent Service Interface

Provides user and expert registration, management, and query functions
"""

import asyncio
import uuid
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from timem.utils.logging import get_logger
from timem.core.service_registry import ServiceType, get_service

logger = get_logger(__name__)


class UserType(Enum):
    """User type enumeration"""
    USER = "user"
    EXPERT = "expert"
    BOTH = "both"  # Both user and expert


@dataclass
class UserInfo:
    """User information"""
    user_id: str
    expert_id: str
    user_name: str
    expert_name: str
    speakers: List[str]
    conv_id: str
    created_at: datetime
    metadata: Dict[str, Any]


class UserRegistrationService:
    """
    User Registration Service
    
    Provides user and expert registration, management, and query functions
    """
    
    def __init__(self):
        self._logger = get_logger(__name__)
        self._registered_users: Dict[str, UserInfo] = {}
        self._user_counter = 0
        self._lock = asyncio.Lock()
    
    async def register_conversation_users(
        self, 
        speakers: List[str], 
        conv_id: str,
        user_type: UserType = UserType.BOTH,
        custom_names: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> UserInfo:
        """
        Register users and experts for conversation
        
        Args:
            speakers: List of speakers
            conv_id: Conversation ID
            user_type: User type (USER/EXPERT/BOTH)
            custom_names: Custom user and expert names
            metadata: Additional metadata
            
        Returns:
            UserInfo: User information
        """
        async with self._lock:
            try:
                # Check if already registered
                if conv_id in self._registered_users:
                    self._logger.info(f"Users for conversation {conv_id} already exist, returning existing user information")
                    return self._registered_users[conv_id]
                
                # Generate unique user identifiers
                timestamp_suffix = int(time.time() * 1000) % 100000
                unique_suffix = str(uuid.uuid4())[:8]
                
                # Create user and expert
                user_id = None
                expert_id = None
                user_name = None
                expert_name = None
                
                if user_type in [UserType.USER, UserType.BOTH]:
                    # Create user
                    if custom_names and "user_name" in custom_names:
                        user_name = custom_names["user_name"]
                    else:
                        user_name = f"{speakers[0]}_{conv_id}_user_{timestamp_suffix}_{unique_suffix}"
                    
                    user_id = await self._create_character(
                        name=user_name,
                        character_type="user",
                        display_name=f"{speakers[0]} ({conv_id})",
                        description=f"[SERVICE] {conv_id} conversation participant: {speakers[0]} - Service user instance"
                    )
                
                if user_type in [UserType.EXPERT, UserType.BOTH]:
                    # Create expert
                    if custom_names and "expert_name" in custom_names:
                        expert_name = custom_names["expert_name"]
                    else:
                        expert_name = f"{speakers[1]}_{conv_id}_expert_{timestamp_suffix + 1}_{unique_suffix}"
                    
                    expert_id = await self._create_character(
                        name=expert_name,
                        character_type="user",
                        display_name=f"{speakers[1]} ({conv_id})",
                        description=f"[SERVICE] {conv_id} conversation participant: {speakers[1]} - Service user instance"
                    )
                
                # Create user information
                user_info = UserInfo(
                    user_id=user_id or "",
                    expert_id=expert_id or "",
                    user_name=user_name or "",
                    expert_name=expert_name or "",
                    speakers=speakers,
                    conv_id=conv_id,
                    created_at=datetime.now(),
                    metadata=metadata or {}
                )
                
                # Store user information
                self._registered_users[conv_id] = user_info
                self._user_counter += 1
                
                self._logger.info(f"Successfully registered conversation users {conv_id}: {speakers[0]} & {speakers[1]}")
                self._logger.info(f"  - User ID: {user_id}")
                self._logger.info(f"  - Expert ID: {expert_id}")
                
                return user_info
                
            except Exception as e:
                self._logger.error(f"Failed to register conversation users {conv_id}: {e}")
                raise
    
    async def register_single_user(
        self,
        name: str,
        character_type: str = "user",
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Register a single user
        
        Args:
            name: Username
            character_type: Character type
            display_name: Display name
            description: Description
            metadata: Metadata
            
        Returns:
            str: User ID
        """
        try:
            user_id = await self._create_character(
                name=name,
                character_type=character_type,
                display_name=display_name or name,
                description=description or f"User: {name}"
            )
            
            self._logger.info(f"Successfully registered user: {name} (ID: {user_id})")
            return user_id
            
        except Exception as e:
            self._logger.error(f"Failed to register user {name}: {e}")
            raise
    
    async def get_user_info(self, conv_id: str) -> Optional[UserInfo]:
        """
        Get user information
        
        Args:
            conv_id: Conversation ID
            
        Returns:
            UserInfo: User information, if not found returns None
        """
        return self._registered_users.get(conv_id)
    
    async def list_registered_users(self) -> List[UserInfo]:
        """
        List all registered users
        
        Returns:
            List[UserInfo]: User information list
        """
        return list(self._registered_users.values())
    
    async def delete_user(self, conv_id: str) -> bool:
        """
        Delete user
        
        Args:
            conv_id: Conversation ID
            
        Returns:
            bool: Whether deletion was successful
        """
        async with self._lock:
            if conv_id in self._registered_users:
                user_info = self._registered_users[conv_id]
                
                # Delete characters (if supported)
                try:
                    if user_info.user_id:
                        await self._delete_character(user_info.user_id)
                    if user_info.expert_id:
                        await self._delete_character(user_info.expert_id)
                except Exception as e:
                    self._logger.warning(f"Failed to delete character: {e}")
                
                # Delete from registration table
                del self._registered_users[conv_id]
                self._user_counter -= 1
                
                self._logger.info(f"Successfully deleted user {conv_id}")
                return True
            else:
                self._logger.warning(f"User {conv_id} does not exist")
                return False
    
    async def clear_all_users(self) -> int:
        """
        Clear all users
        
        Returns:
            int: Number of deleted users
        """
        async with self._lock:
            count = len(self._registered_users)
            
            # Delete all characters
            for user_info in self._registered_users.values():
                try:
                    if user_info.user_id:
                        await self._delete_character(user_info.user_id)
                    if user_info.expert_id:
                        await self._delete_character(user_info.expert_id)
                except Exception as e:
                    self._logger.warning(f"Failed to delete character: {e}")
            
            # Clear registration table
            self._registered_users.clear()
            self._user_counter = 0
            
            self._logger.info(f"Cleared {count} users")
            return count
    
    async def _create_character(
        self,
        name: str,
        character_type: str,
        display_name: str,
        description: str
    ) -> str:
        """Create character"""
        try:
            from services.character_service import get_character_service
            
            character_service = get_character_service()
            character = await character_service.create_character(
                name=name,
                character_type=character_type,
                display_name=display_name,
                description=description
            )
            
            return character["id"]
            
        except Exception as e:
            self._logger.error(f"Failed to create character {name}: {e}")
            raise
    
    async def _delete_character(self, character_id: str) -> bool:
        """Delete character"""
        try:
            from services.character_service import get_character_service
            
            character_service = get_character_service()
            await character_service.delete_character(character_id)
            return True
            
        except Exception as e:
            self._logger.warning(f"Failed to delete character {character_id}: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics"""
        return {
            "total_registered_users": self._user_counter,
            "active_conversations": len(self._registered_users),
            "registered_conv_ids": list(self._registered_users.keys())
        }


# Global service instance
_user_registration_service: Optional[UserRegistrationService] = None
_service_lock = asyncio.Lock()


async def get_user_registration_service() -> UserRegistrationService:
    """Get user registration service instance"""
    global _user_registration_service
    
    async with _service_lock:
        if _user_registration_service is None:
            _user_registration_service = UserRegistrationService()
        
        return _user_registration_service


# Convenience functions
async def register_conversation_users(
    speakers: List[str], 
    conv_id: str,
    user_type: UserType = UserType.BOTH,
    custom_names: Optional[Dict[str, str]] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> UserInfo:
    """Convenience function: Register conversation users"""
    service = await get_user_registration_service()
    return await service.register_conversation_users(
        speakers=speakers,
        conv_id=conv_id,
        user_type=user_type,
        custom_names=custom_names,
        metadata=metadata
    )


async def get_conversation_users(conv_id: str) -> Optional[UserInfo]:
    """Convenience function: Get conversation user information"""
    service = await get_user_registration_service()
    return await service.get_user_info(conv_id)

