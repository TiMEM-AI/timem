"""
Input Validation Node

Responsible for validating completeness and format correctness of input data for memory generation workflow
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from timem.workflows.state import MemoryState
from timem.utils.logging import get_logger

logger = get_logger(__name__)


class InputValidationNode:
    """Input validation node, check completeness and validity of input data"""
    
    def __init__(self):
        """Initialize input validation node"""
        logger.info("Initialize input validation node")
    
    async def run(self, state: MemoryState) -> MemoryState:
        """
        Validate completeness and validity of input data
        
        Args:
            state: Memory workflow state
            
        Returns:
            Updated workflow state
        """
        logger.info("Executing input validation")
        
        try:
            # Extract required input fields
            input_data = state.get("input_data", {})
            
            if not input_data:
                error_msg = "Input data is empty"
                logger.error(error_msg)
                return {
                    **state,
                    "validation_passed": False,
                    "error": error_msg
                }
            
            # Validate if required fields exist
            required_fields = ["session_id", "user_id", "expert_id", "timestamp", "content"]
            missing_fields = []
            
            # Check missing fields and try to set default values
            for field in required_fields:
                if field not in input_data or input_data[field] is None:
                    if field == "timestamp":
                        # Provide default value for timestamp
                        input_data["timestamp"] = datetime.now().isoformat()
                        logger.warning(f"Timestamp field missing, set default value: {input_data['timestamp']}")
                    elif field == "metadata":
                        # Provide default value for metadata
                        input_data["metadata"] = {}
                        logger.warning("Metadata field is missing, set to empty dictionary")
                    else:
                        # Other fields still need to be reported as missing
                        missing_fields.append(field)
            
            if missing_fields:
                error_msg = f"Input data missing required fields: {', '.join(missing_fields)}"
                logger.error(error_msg)
                
                # Print complete input data to help debug
                logger.debug(f"Input data: {input_data}")
                
                return {
                    **state,
                    "validation_passed": False,
                    "error": error_msg
                }
            
            # Validate field format and validity
            session_id = input_data.get("session_id", "")
            if not isinstance(session_id, str) or not session_id:
                error_msg = "Invalid session ID"
                logger.error(error_msg)
                return {
                    **state,
                    "validation_passed": False,
                    "error": error_msg
                }
            
            # Extract and validate other required fields
            user_id = input_data.get("user_id", "")
            expert_id = input_data.get("expert_id", "")
            timestamp = input_data.get("timestamp", "")
            content = input_data.get("content", "")
            metadata = input_data.get("metadata", {})
            
            # Ensure metadata is dictionary type
            if not isinstance(metadata, dict):
                logger.warning(f"Metadata is not dictionary type, converted: {metadata}")
                metadata = {"original": str(metadata)}
            
            # Update input data
            input_data.update({
                "session_id": session_id,
                "user_id": user_id,
                "expert_id": expert_id,
                "timestamp": timestamp,
                "content": content,
                "metadata": metadata
            })
            
            # Update state
            updated_state = {
                **state,
                "input_data": input_data,  # Update possibly corrected input data
                "validation_passed": True,
                "error": None,
                "session_id": session_id,
                "user_id": user_id,
                "expert_id": expert_id,
                "timestamp": timestamp,
                "content": content,
                "metadata": metadata
            }
            
            logger.info("Input validation passed")
            return updated_state
            
        except Exception as e:
            error_msg = f"Error occurred during input validation: {str(e)}"
            logger.error(error_msg)
            import traceback
            logger.error(traceback.format_exc())
            return {
                **state,
                "validation_passed": False,
                "error": error_msg
            } 