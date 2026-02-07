"""
TiMem User Service
Provides management functions for real users, including creation, query, update, and deletion
Users are stored in the users table, separated from the characters table (AI roles)
"""

import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_, or_
from sqlalchemy.orm import selectinload

from storage.postgres_store import User
from storage.base_storage_interface import UnifiedStorageInterface
from storage.memory_storage_manager import get_memory_storage_manager_async
from timem.utils.logging import get_logger

class UserService:
    """User Service - Manages real users (users table)"""
    
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
                # If using PostgreSQL, can also handle User table
                self.sql_store = storage_manager.default_adapter._postgres_store
            else:
                raise RuntimeError("Unable to get SQL storage instance")
        return self.sql_store
    
    async def create_user(self, 
                         username: str, 
                         display_name: Optional[str] = None,
                         description: Optional[str] = None,
                         metadata: Optional[Dict[str, Any]] = None,
                         user_id: Optional[str] = None) -> Dict[str, Any]:
        """Create user
        
        Args:
            username: Username (unique)
            display_name: Display name
            description: Description
            metadata: Metadata
            user_id: User ID (optional, auto-generated if not provided)
            
        Returns:
            Created user information
        """
        try:
            sql_store = await self._get_sql_store()
            
            # Check if username already exists
            existing = await self.get_user_by_username(username)
            if existing:
                raise ValueError(f"Username '{username}' already exists")
            
            # Generate ID
            if user_id is None:
                user_id = str(uuid.uuid4())
            
            # Create user record
            user_data = {
                "id": user_id,
                "username": username,
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
                    user = User(**user_data)
                    session.add(user)
                    await session.commit()
                    await session.refresh(user)
                    
                    self.logger.info(f"Successfully created user: {username} (ID: {user_id})")
                    
                    return {
                        "id": user.id,
                        "username": user.username,
                        "display_name": user.display_name,
                        "description": user.description,
                        "metadata": user.metadata_json,
                        "is_active": user.is_active,
                        "created_at": user.created_at,
                        "updated_at": user.updated_at
                    }
                except Exception as e:
                    await session.rollback()
                    raise e
                    
        except Exception as e:
            self.logger.error(f"Failed to create user: {e}")
            raise
    
    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user information by ID
        
        Args:
            user_id: User ID
            
        Returns:
            User information dictionary, if not found returns None
        """
        try:
            sql_store = await self._get_sql_store()
            
            session_cm = await sql_store._get_session_cm()
            async with session_cm as session:
                result = await session.execute(
                    select(User).where(User.id == user_id)
                )
                user = result.scalar_one_or_none()
                
                if user:
                    return {
                        "id": user.id,
                        "username": user.username,
                        "display_name": user.display_name,
                        "description": user.description,
                        "metadata": user.metadata_json,
                        "is_active": user.is_active,
                        "created_at": user.created_at,
                        "updated_at": user.updated_at
                    }
                return None
                    
        except Exception as e:
            self.logger.error(f"Failed to get user by ID: {e}")
            raise
    
    async def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user information by username
        
        Args:
            username: Username
            
        Returns:
            User information dictionary, if not found returns None
        """
        try:
            sql_store = await self._get_sql_store()
            
            session_cm = await sql_store._get_session_cm()
            async with session_cm as session:
                result = await session.execute(
                    select(User).where(User.username == username)
                )
                user = result.scalar_one_or_none()
                
                if user:
                    return {
                        "id": user.id,
                        "username": user.username,
                        "display_name": user.display_name,
                        "description": user.description,
                        "metadata": user.metadata_json,
                        "is_active": user.is_active,
                        "created_at": user.created_at,
                        "updated_at": user.updated_at
                    }
                return None
                    
        except Exception as e:
            self.logger.error(f"Failed to get user by username: {e}")
            raise
    
    async def get_users(self, 
                       is_active: Optional[bool] = None,
                       limit: int = 100) -> List[Dict[str, Any]]:
        """Get all users list
        
        Args:
            is_active: Active status filter
            limit: Return count limit
            
        Returns:
            List[Dict[str, Any]]: Users list
        """
        try:
            sql_store = await self._get_sql_store()
            
            session_cm = await sql_store._get_session_cm()
            async with session_cm as session:
                # Build query conditions
                conditions = []
                
                if is_active is not None:
                    conditions.append(User.is_active == is_active)
                
                # Build query
                query = select(User)
                if conditions:
                    query = query.where(and_(*conditions))
                
                # Add limit
                query = query.limit(limit)
                
                # Execute query
                result = await session.execute(query)
                users = result.scalars().all()
                
                # Convert to dictionary list
                user_list = []
                for user in users:
                    user_dict = {
                        "id": user.id,
                        "username": user.username,
                        "display_name": user.display_name,
                        "description": user.description,
                        "metadata": user.metadata_json,
                        "is_active": user.is_active,
                        "created_at": user.created_at.isoformat() if user.created_at else None,
                        "updated_at": user.updated_at.isoformat() if user.updated_at else None
                    }
                    user_list.append(user_dict)
                
                self.logger.info(f"Retrieved {len(user_list)} users")
                return user_list
                
        except Exception as e:
            self.logger.error(f"Failed to get users list: {e}")
            raise

    async def update_user(self, 
                         user_id: str,
                         username: Optional[str] = None,
                         display_name: Optional[str] = None,
                         description: Optional[str] = None,
                         metadata: Optional[Dict[str, Any]] = None,
                         is_active: Optional[bool] = None) -> Optional[Dict[str, Any]]:
        """Update user information
        
        Args:
            user_id: User ID
            username: Username
            display_name: Display name
            description: Description
            metadata: Metadata
            is_active: Active status
            
        Returns:
            Updated user information, if not found returns None
        """
        try:
            sql_store = await self._get_sql_store()
            
            # Check if user exists
            existing = await self.get_user_by_id(user_id)
            if not existing:
                return None
            
            # Check if username conflicts with other users
            if username and username != existing["username"]:
                username_conflict = await self.get_user_by_username(username)
                if username_conflict:
                    raise ValueError(f"Username '{username}' already exists")
            
            # Build update data
            update_data = {}
            if username is not None:
                update_data["username"] = username
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
                        update(User)
                        .where(User.id == user_id)
                        .values(**update_data)
                    )
                    await session.commit()
                    
                    self.logger.info(f"Successfully updated user: {user_id}")
                    
                    return await self.get_user_by_id(user_id)
                except Exception as e:
                    await session.rollback()
                    raise e
                    
        except Exception as e:
            self.logger.error(f"Failed to update user: {e}")
            raise
    
    async def delete_user(self, user_id: str) -> bool:
        """Delete user
        
        Args:
            user_id: User ID
            
        Returns:
            Whether deletion was successful
        """
        try:
            sql_store = await self._get_sql_store()
            
            # Check if user exists
            existing = await self.get_user_by_id(user_id)
            if not existing:
                return False
            
            session_cm = await sql_store._get_session_cm()
            async with session_cm as session:
                try:
                    await session.execute(
                        delete(User).where(User.id == user_id)
                    )
                    await session.commit()
                    
                    self.logger.info(f"Successfully deleted user: {user_id}")
                    return True
                except Exception as e:
                    await session.rollback()
                    raise e
                    
        except Exception as e:
            self.logger.error(f"Failed to delete user: {e}")
            raise
    
    async def ensure_user_registered(self, 
                                    username: str, 
                                    display_name: Optional[str] = None,
                                    metadata: Optional[Dict[str, Any]] = None) -> str:
        """Ensure user is registered, create if not exists
        
        Args:
            username: Username
            display_name: Display name
            metadata: Metadata
            
        Returns:
            User ID
        """
        # Check if already exists
        existing = await self.get_user_by_username(username)
        if existing:
            self.logger.info(f"User '{username}' already exists, ID: {existing['id']}")
            return existing["id"]
        
        # Create new user
        user_metadata = {"auto_registered": True}
        if metadata:
            user_metadata.update(metadata)
        
        user = await self.create_user(
            username=username,
            display_name=display_name or username,
            description=f"Conversation participant (user): {username}",
            metadata=user_metadata
        )
        
        self.logger.info(f"Successfully created new user: {username} (ID: {user['id']})")
        return user["id"]

# Global instance
_user_service = None

def get_user_service() -> UserService:
    """Get user service instance"""
    global _user_service
    if _user_service is None:
        _user_service = UserService()
    return _user_service

