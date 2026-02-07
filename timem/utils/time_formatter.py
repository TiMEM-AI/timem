"""
Unified time formatting tool

Provides common time formatting functions for each layer to avoid code duplication.
Supports intelligent conversion and unified output of multiple time formats.
"""

from typing import Optional, Union
from datetime import datetime
import re
from timem.utils.logging import get_logger

logger = get_logger(__name__)


class TimeFormatter:
    """Unified time formatting tool class"""
    
    def __init__(self, language: str = "en"):
        """
        Initialize time formatter
        
        Args:
            language: Output language, supports "zh" and "en"
        """
        self.language = language.lower()
        if self.language not in ["zh", "en"]:
            self.language = "en"
            logger.warning(f"Unsupported language: {language}, using English by default")
    
    def format_time_for_display(self, time_value: Union[str, datetime, None]) -> str:
        """
        Format time value to concise display format
        
        Args:
            time_value: Time value (string, datetime object or None)
            
        Returns:
            Formatted time string
        """
        if not time_value:
            return ""
        
        try:
            if isinstance(time_value, str):
                return self._format_string_time(time_value)
            elif isinstance(time_value, datetime):
                return self._format_datetime_time(time_value)
            else:
                return str(time_value)
        except Exception as e:
            logger.warning(f"Time formatting failed: {time_value}, error: {e}")
            return self._fallback_format(time_value)
    
    def _format_string_time(self, time_str: str) -> str:
        """Format string time"""
        # If it's ISO format time string, extract only date part
        if "T" in time_str:
            try:
                # Parse ISO format time
                if time_str.endswith("Z"):
                    dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                else:
                    dt = datetime.fromisoformat(time_str)
                
                return self._format_datetime_time(dt)
            except Exception:
                # Parse failed, try to extract date part directly
                return self._extract_date_part(time_str)
        else:
            # If not ISO format, check other formats
            # If it's year format (like "2022"), return directly
            if time_str.isdigit() and len(time_str) == 4:
                return time_str
            # If it's YYYY-MM-DD format, convert to target format
            elif "-" in time_str and len(time_str) == 10 and time_str.count("-") == 2:
                if self.language == "zh":
                    return time_str  # Chinese keeps original format
                else:
                    return self._convert_to_english_date_format(time_str)
            # Return original time string directly
            return time_str
    
    def _format_datetime_time(self, dt: datetime) -> str:
        """Format datetime object"""
        if self.language == "zh":
            # Chinese format: YYYY-MM-DD
            return dt.strftime("%Y-%m-%d")
        else:
            # English format: DD Month YYYY
            return self._convert_to_english_date_format(dt.strftime("%Y-%m-%d"))
    
    def _extract_date_part(self, time_str: str) -> str:
        """Extract date part from time string"""
        if "T" in time_str and len(time_str) >= 10:
            # Try to extract first 10 characters as date
            date_part = time_str[:10]
            if "-" in date_part and date_part.count("-") == 2:
                if self.language == "zh":
                    return date_part
                else:
                    return self._convert_to_english_date_format(date_part)
        # If all failed, return original string
        return time_str
    
    def _convert_to_english_date_format(self, date_str: str) -> str:
        """Convert YYYY-MM-DD format to English date format (e.g.: 9 June 2023)"""
        if not date_str or "-" not in date_str:
            return date_str
        
        try:
            # Parse date
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            
            # English month names
            month_names = [
                "January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December"
            ]
            
            # Get month name (index starts from 0)
            month_name = month_names[dt.month - 1]
            
            # Format: 9 June 2023
            return f"{dt.day} {month_name} {dt.year}"
            
        except Exception as e:
            logger.warning(f"Failed to convert to English date format: {e}, using original format: {date_str}")
            return date_str
    
    def _fallback_format(self, time_value) -> str:
        """Fallback handling when formatting fails"""
        if isinstance(time_value, str):
            # Try to extract date part
            return self._extract_date_part(time_value)
        else:
            # Convert to string
            return str(time_value)
    
    def update_language(self, new_language: str):
        """Update output language"""
        if new_language.lower() in ["zh", "en"]:
            self.language = new_language.lower()
            logger.info(f"Time formatter language updated to: {self.language}")
        else:
            logger.warning(f"Invalid language configuration: {new_language}, keeping current configuration: {self.language}")
    
    def get_current_language(self) -> str:
        """Get current language configuration"""
        return self.language


# Global time formatter instance
_global_time_formatter = None


def get_time_formatter(language: str = None) -> TimeFormatter:
    """
    Get global time formatter instance
    
    Args:
        language: Output language, if None get from global config
        
    Returns:
        Time formatter instance
    """
    global _global_time_formatter
    if _global_time_formatter is None:
        # If no language specified, get from global config
        if language is None:
            try:
                from .config_manager import get_config
                app_config = get_config("app")
                language = app_config.get("language", "en")
                logger.info(f"Time formatter using global language configuration: {language}")
            except Exception as e:
                logger.warning(f"Failed to get global language configuration: {e}, using default 'en'")
                language = "en"
        
        _global_time_formatter = TimeFormatter(language)
    return _global_time_formatter


def update_global_time_formatter_language(language: str):
    """Update global time formatter's language configuration"""
    formatter = get_time_formatter()
    formatter.update_language(language)
