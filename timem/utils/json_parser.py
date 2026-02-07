"""
Robust JSON Parser

Handles various JSON formats from LLM outputs, including:
- Standard JSON format
- JSON wrapped in Markdown code blocks
- Responses mixing text and JSON
- Incomplete or corrupted JSON
"""

import json
import re
from typing import Dict, Any, Optional, List
from timem.utils.logging import get_logger

logger = get_logger(__name__)


class JSONParseError(Exception):
    """JSON parse error"""
    pass


class RobustJSONParser:
    """Robust JSON parser, handles various formats from LLM outputs"""
    
    def __init__(self):
        self.logger = get_logger(__name__)
    
    def parse_llm_json_response(self, response: str, expected_keys: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Parse LLM JSON response with fault tolerance
        
        Args:
            response: Original LLM response text
            expected_keys: List of expected JSON keys for validation
            
        Returns:
            Parsed JSON dictionary
            
        Raises:
            JSONParseError: Raised when all parsing strategies fail
        """
        if not response or not isinstance(response, str):
            raise JSONParseError("Response is empty or not a string")
        
        # Strategy 1: Direct parse standard JSON
        try:
            result = json.loads(response.strip())
            if self._validate_json(result, expected_keys):
                self.logger.debug("Strategy 1 success: Standard JSON parse")
                return result
        except json.JSONDecodeError:
            pass
        
        # Strategy 2: Extract JSON from Markdown code block
        try:
            result = self._extract_from_markdown_code_block(response)
            if result and self._validate_json(result, expected_keys):
                self.logger.debug("Strategy 2 success: Markdown code block extraction")
                return result
        except Exception as e:
            self.logger.debug(f"Strategy 2 failed: {e}")
        
        # Strategy 3: Use regex to extract JSON object
        try:
            result = self._extract_with_regex(response)
            if result and self._validate_json(result, expected_keys):
                self.logger.debug("Strategy 3 success: Regex extraction")
                return result
        except Exception as e:
            self.logger.debug(f"Strategy 3 failed: {e}")
        
        # Strategy 4: Clean common format issues and retry
        try:
            cleaned_response = self._clean_common_issues(response)
            result = json.loads(cleaned_response)
            if self._validate_json(result, expected_keys):
                self.logger.debug("Strategy 4 success: Parse after cleaning")
                return result
        except Exception as e:
            self.logger.debug(f"Strategy 4 failed: {e}")
        
        # Strategy 5: Fix common JSON errors
        try:
            fixed_response = self._fix_common_json_errors(response)
            result = json.loads(fixed_response)
            if self._validate_json(result, expected_keys):
                self.logger.debug("Strategy 5 success: Parse after error fixing")
                return result
        except Exception as e:
            self.logger.debug(f"Strategy 5 failed: {e}")
        
        # All strategies failed
        error_msg = f"All JSON parsing strategies failed. First 100 chars of response: {response[:100]}"
        self.logger.error(error_msg)
        raise JSONParseError(error_msg)
    
    def _extract_from_markdown_code_block(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract JSON from Markdown code block"""
        # Match ```json ... ``` or ``` ... ```
        patterns = [
            r'```json\s*\n(.*?)\n```',
            r'```\s*\n(.*?)\n```',
            r'```json\s*(.*?)```',
            r'```\s*(.*?)```'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.DOTALL | re.MULTILINE)
            for match in matches:
                try:
                    return json.loads(match.strip())
                except json.JSONDecodeError:
                    continue
        
        return None
    
    def _extract_with_regex(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract JSON object using regex"""
        # Try to find the outermost braces
        # This regex attempts to match complete JSON objects
        pattern = r'\{(?:[^{}]|(?:\{(?:[^{}]|(?:\{[^{}]*\}))*\}))*\}'
        
        matches = re.findall(pattern, text, re.DOTALL)
        
        # Try from longest match first (likely most complete)
        for match in sorted(matches, key=len, reverse=True):
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue
        
        return None
    
    def _clean_common_issues(self, text: str) -> str:
        """Clean common formatting issues"""
        # Remove BOM marker
        text = text.replace('\ufeff', '')
        
        # Remove possible leading/trailing text (keep content between braces)
        # Find first { and last }
        first_brace = text.find('{')
        last_brace = text.rfind('}')
        
        if first_brace != -1 and last_brace != -1 and first_brace < last_brace:
            text = text[first_brace:last_brace + 1]
        
        # Remove extra whitespace
        text = text.strip()
        
        return text
    
    def _fix_common_json_errors(self, text: str) -> str:
        """Fix common JSON errors"""
        # Clean basic issues first
        text = self._clean_common_issues(text)
        
        # Fix single quotes to double quotes (but be careful with quotes inside strings)
        # This is a simplified version, may not be perfect
        # text = text.replace("'", '"')
        
        # Remove trailing commas (after last element in array or object)
        text = re.sub(r',\s*}', '}', text)
        text = re.sub(r',\s*]', ']', text)
        
        # Try to fix missing quotes (complex, only do basic handling)
        # Fix patterns like {key: "value"} to {"key": "value"}
        text = re.sub(r'(\{|,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1 "\2":', text)
        
        return text
    
    def _validate_json(self, json_obj: Any, expected_keys: Optional[List[str]] = None) -> bool:
        """Validate JSON object"""
        if not isinstance(json_obj, dict):
            return False
        
        # If no expected keys, any dict passes
        if not expected_keys:
            return True
        
        # Check if all expected keys are present
        missing_keys = [key for key in expected_keys if key not in json_obj]
        
        if missing_keys:
            self.logger.debug(f"Missing expected keys: {missing_keys}")
            # Even if some keys are missing, partial match is acceptable
            # At least half of keys must match
            matched_keys = len(expected_keys) - len(missing_keys)
            if matched_keys < len(expected_keys) / 2:
                return False
        
        return True
    
    def parse_with_fallback(self, response: str, expected_keys: Optional[List[str]] = None, 
                           fallback_value: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Parse JSON, return fallback value if parsing fails
        
        Args:
            response: LLM response
            expected_keys: List of expected keys
            fallback_value: Default value when parsing fails
            
        Returns:
            Parsed result or fallback value
        """
        try:
            return self.parse_llm_json_response(response, expected_keys)
        except JSONParseError as e:
            self.logger.warning(f"JSON parsing failed, using fallback value: {e}")
            return fallback_value or {}


# Global singleton
_parser_instance = None


def get_json_parser() -> RobustJSONParser:
    """Get JSON parser singleton"""
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = RobustJSONParser()
    return _parser_instance

