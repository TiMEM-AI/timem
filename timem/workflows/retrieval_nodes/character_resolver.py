"""
Character name resolution node

Responsible for parsing character information from input and mapping character names to character IDs in the database.
Supports intelligent resolution strategies to avoid unnecessary database queries.
"""

from typing import Dict, List, Any, Optional
import re

from timem.workflows.retrieval_state import RetrievalState, RetrievalStateValidator
from services.character_service import get_character_service, CharacterService
from timem.utils.logging import get_logger

logger = get_logger(__name__)


class CharacterResolver:
    """Character name resolution node"""
    
    def __init__(self, 
                 character_service: Optional[CharacterService] = None,
                 state_validator: Optional[RetrievalStateValidator] = None):
        """
        Initialize character resolver
        
        Args:
            character_service: Character service instance, auto-fetch if None
            state_validator: State validator, create new instance if None
        """
        self.character_service = character_service
        self.state_validator = state_validator or RetrievalStateValidator()
        self.logger = get_logger(__name__)
        
    async def _get_character_service(self) -> CharacterService:
        """Get character service instance"""
        if self.character_service is None:
            self.character_service = get_character_service()
        return self.character_service
        
    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run character name resolution
        
        Args:
            state: Workflow state dictionary
            
        Returns:
            Updated state dictionary
        """
        try:
            # Convert to RetrievalState object while preserving extra fields
            retrieval_state, extra_fields = self._dict_to_state(state)
            
            self.logger.info("Start character name resolution")
            
            # Step 1: Check if sufficient character ID information exists
            if self._has_sufficient_character_ids(retrieval_state):
                self.logger.info("Sufficient character ID information exists, skip resolution")
                retrieval_state.character_ids = self._collect_existing_ids(retrieval_state)
                return self._state_to_dict(retrieval_state, extra_fields)
            
            # Step 2: Use provided character names (if any)
            if retrieval_state.user_name or retrieval_state.expert_name:
                await self._resolve_from_provided_names(retrieval_state)
            
            # Step 3: Parse character names from question content (if still needed)
            if not retrieval_state.character_ids:
                await self._resolve_from_question_content(retrieval_state)
            
            # Step 4: Validate resolution results
            warnings = self.state_validator.validate_character_resolution(retrieval_state)
            retrieval_state.warnings.extend(warnings)
            
            # Step 5: Set backward compatibility fields
            self._set_backward_compatibility(retrieval_state)
            
            self.logger.info(f"Character resolution complete, found {len(retrieval_state.character_ids)} character IDs")
            
            # Restore extra fields when returning
            return self._state_to_dict(retrieval_state, extra_fields)
            
        except Exception as e:
            error_msg = f"Character name resolution failed: {str(e)}"
            self.logger.error(error_msg)
            state["errors"] = state.get("errors", []) + [error_msg]
            return state
    
    def _has_sufficient_character_ids(self, state: RetrievalState) -> bool:
        """Check if sufficient character ID information exists"""
        # If character_ids already set, sufficient
        if state.character_ids:
            return True
            
        # If has user_id or expert_id, also sufficient
        if state.user_id or state.expert_id:
            return True
            
        # If has user_group_ids, test code has provided correct ID combination, use directly
        if hasattr(state, 'user_group_ids') and state.user_group_ids:
            return True
            
        return False
    
    def _collect_existing_ids(self, state: RetrievalState) -> List[str]:
        """Collect existing character IDs"""
        ids = []
        
        if state.character_ids:
            ids.extend(state.character_ids)
            
        if state.user_id and state.user_id not in ids:
            ids.append(state.user_id)
            
        if state.expert_id and state.expert_id not in ids:
            ids.append(state.expert_id)
        
        # Prioritize user_group_ids from test code
        if hasattr(state, 'user_group_ids') and state.user_group_ids:
            ids = state.user_group_ids.copy()
            self.logger.info(f"Using user group IDs from test code: {ids}")
            
        return ids
    
    async def _resolve_from_provided_names(self, state: RetrievalState):
        """Resolve IDs from provided character names"""
        character_service = await self._get_character_service()
        
        # Resolve user name
        if state.user_name and not state.user_id:
            try:
                user_id = await character_service.get_character_id_by_name(state.user_name)
                if user_id:
                    state.user_id = user_id
                    if user_id not in state.character_ids:
                        state.character_ids.append(user_id)
                    self.logger.info(f"Resolved user name '{state.user_name}' -> ID: {state.user_id}")
                else:
                    state.warnings.append(f"No ID found for user name '{state.user_name}'")
            except Exception as e:
                state.warnings.append(f"Failed to resolve user name: {e}")
        
        # Resolve expert name
        if state.expert_name and not state.expert_id:
            try:
                expert_id = await character_service.get_character_id_by_name(state.expert_name)
                if expert_id:
                    state.expert_id = expert_id
                    if expert_id not in state.character_ids:
                        state.character_ids.append(expert_id)
                    self.logger.info(f"Resolved expert name '{state.expert_name}' -> ID: {state.expert_id}")
                else:
                    state.warnings.append(f"No ID found for expert name '{state.expert_name}'")
            except Exception as e:
                state.warnings.append(f"Failed to resolve expert name: {e}")
    
    async def _resolve_from_question_content(self, state: RetrievalState):
        """Resolve character names from question content"""
        try:
            character_service = await self._get_character_service()
            self.logger.info("Extracting character names from question content...")
            
            # Get character data
            all_characters_result = await character_service.search_characters(size=1000)
            all_characters = all_characters_result.get('characters', [])
            self.logger.info(f"Total {len(all_characters)} characters in database")
            
            # Optimization: preprocess question text, only convert once
            question_lower = state.question.lower()
            matched_characters = []
            
            # Use smarter matching strategy
            for character in all_characters:
                character_name = character.get('name', '').strip()
                character_id = character.get('id', '')
                
                if not character_name or not character_id:
                    continue
                    
                # Multiple matching strategies
                if self._is_name_match(character_name, question_lower):
                    matched_characters.append({
                        'name': character_name,
                        'id': character_id,
                        'position': question_lower.find(character_name.lower())
                    })
                    self.logger.info(f"Found character in question: {character_name} (ID: {character_id})")
            
            # Sort by position in question
            matched_characters.sort(key=lambda x: x['position'])
            
            # Collect all found character IDs
            for char in matched_characters:
                if char['id'] not in state.character_ids:
                    state.character_ids.append(char['id'])
            
            # Set user and expert IDs (backward compatibility)
            if len(matched_characters) >= 2:
                state.user_id = matched_characters[0]['id']
                state.expert_id = matched_characters[1]['id']
                self.logger.info(f"Assigned user ID: {state.user_id} ({matched_characters[0]['name']})")
                self.logger.info(f"Assigned expert ID: {state.expert_id} ({matched_characters[1]['name']})")
            elif len(matched_characters) == 1:
                state.user_id = matched_characters[0]['id']
                self.logger.info(f"Assigned user ID: {state.user_id} ({matched_characters[0]['name']})")
                
        except Exception as e:
            error_msg = f"Failed to parse characters from question content: {str(e)}"
            self.logger.error(error_msg)
            state.warnings.append(error_msg)
    
    def _is_name_match(self, character_name: str, question_lower: str) -> bool:
        """Check if character name matches in question"""
        name_lower = character_name.lower()
        
        # Exact match
        if name_lower in question_lower:
            return True
            
        # First initial match (e.g., "Caroline" matches "C.")
        if len(character_name) > 1:
            first_initial = character_name[0].lower() + '.'
            if first_initial in question_lower:
                return True
                
        # Partial match (for compound names)
        if ' ' in character_name:
            parts = character_name.split()
            if any(part.lower() in question_lower for part in parts if len(part) > 2):
                return True
                
        return False
    
    def _set_backward_compatibility(self, state: RetrievalState):
        """Set backward compatibility fields"""
        # Prioritize user_group_ids from test code
        if hasattr(state, 'user_group_ids') and state.user_group_ids:
            if len(state.user_group_ids) >= 2:
                state.user_id = state.user_group_ids[0]
                state.expert_id = state.user_group_ids[1]
                self.logger.info(f"Using ID combination from test code: user_id={state.user_id}, expert_id={state.expert_id}")
            elif len(state.user_group_ids) == 1:
                state.user_id = state.user_group_ids[0]
                self.logger.info(f"Using user_id from test code: {state.user_id}")
            
            # Update character_ids
            state.character_ids = state.user_group_ids.copy()
        else:
            # Ensure user_id and expert_id fields are set
            if state.character_ids:
                if not state.user_id:
                    state.user_id = state.character_ids[0]
                if not state.expert_id and len(state.character_ids) > 1:
                    state.expert_id = state.character_ids[1]
                    
            # Ensure character_ids contains user_id and expert_id
            for char_id in [state.user_id, state.expert_id]:
                if char_id and char_id not in state.character_ids:
                    state.character_ids.append(char_id)
    
    def _dict_to_state(self, state_dict: Dict[str, Any]):
        """
        Convert dictionary to RetrievalState object and preserve extra fields
        
        Returns:
            (RetrievalState object, extra fields dictionary)
        """
        from typing import Tuple
        
        state = RetrievalState(
            question=state_dict.get("question", ""),
            user_id=state_dict.get("user_id", ""),
            expert_id=state_dict.get("expert_id", ""), 
            user_name=state_dict.get("user_name", ""),
            expert_name=state_dict.get("expert_name", ""),
            character_ids=state_dict.get("character_ids", []),
            context=state_dict.get("context", {}),
            errors=state_dict.get("errors", []),
            warnings=state_dict.get("warnings", [])
        )
        
        # Add user_group_ids attribute (if exists)
        if 'user_group_ids' in state_dict:
            state.user_group_ids = state_dict.get("user_group_ids", [])
        
        # Extract and preserve all extra fields (especially return_memories_only config fields)
        known_fields = {
            'question', 'user_id', 'expert_id', 'user_name', 'expert_name',
            'character_ids', 'context', 'errors', 'warnings', 'user_group_ids'
        }
        extra_fields = {k: v for k, v in state_dict.items() if k not in known_fields}
        
        if extra_fields:
            self.logger.debug(f"Preserving extra fields: {list(extra_fields.keys())}")
            
        return state, extra_fields
    
    def _state_to_dict(self, state: RetrievalState, extra_fields: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Convert RetrievalState object to dictionary and restore extra fields
        
        Args:
            state: RetrievalState object
            extra_fields: Extra fields dictionary (including return_memories_only config)
        """
        result = {
            "question": state.question,
            "user_id": state.user_id,
            "expert_id": state.expert_id,
            "user_name": state.user_name,
            "expert_name": state.expert_name,
            "character_ids": state.character_ids,
            "context": state.context,
            "errors": state.errors,
            "warnings": state.warnings
        }
        
        # Add user_group_ids (if exists)
        if hasattr(state, 'user_group_ids'):
            result["user_group_ids"] = state.user_group_ids
        
        # Restore all extra fields (especially return_memories_only config)
        if extra_fields:
            result.update(extra_fields)
            if 'return_memories_only' in extra_fields:
                self.logger.debug(f"Restoring config field: return_memories_only={extra_fields['return_memories_only']}")
            
        return result
