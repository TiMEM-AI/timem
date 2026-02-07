"""
JSON utility class

Provides JSON serialization and deserialization tools, especially for handling datetime objects
"""

import json
from datetime import datetime, date
from typing import Any

class DateTimeEncoder(json.JSONEncoder):
    """
    Custom JSON encoder, handles serialization of datetime and date objects
    
    Converts datetime and date objects to ISO8601 format strings
    """
    
    def default(self, obj: Any) -> Any:
        """
        Handle serialization of special types
        
        Args:
            obj: Object to serialize
            
        Returns:
            Object that can be serialized by json module
        """
        if isinstance(obj, (datetime, date)):
            # Convert datetime object to ISO8601 format string
            return obj.isoformat()
        
        # Let parent class handle unrecognized types
        return super().default(obj)


def dumps(obj: Any, **kwargs) -> str:
    """
    Serialize object to JSON string
    
    Supports serialization of datetime and date objects
    
    Args:
        obj: Object to serialize
        **kwargs: Other parameters to pass to json.dumps
        
    Returns:
        JSON string
    """
    return json.dumps(obj, cls=DateTimeEncoder, **kwargs)


def loads(s: str, **kwargs) -> Any:
    """
    Deserialize JSON string to object
    
    Args:
        s: JSON string
        **kwargs: Other parameters to pass to json.loads
        
    Returns:
        Python object
    """
    return json.loads(s, **kwargs)