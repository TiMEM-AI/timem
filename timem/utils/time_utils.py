"""
TiMem Time Utility Module

Provides unified time processing utility functions, including:
1. Time format standardization
2. Time serialization and deserialization
3. Time type conversion
4. Time comparison and calculation
5. Unified timezone-naive handling

This module ensures consistency of time processing throughout the project, especially in storage layer and cross-component interactions.
Uniformly uses timezone-naive datetime format to avoid timezone confusion issues.
"""
from datetime import datetime, timedelta
from typing import Union, Dict, Any, Optional
import json

from timem.utils.time_parser import time_parser
from timem.utils.logging import get_logger

logger = get_logger(__name__)

def get_current_time() -> datetime:
    """Get current time (timezone-naive) - only for internal system time, not for memory generation"""
    return datetime.now()

def ensure_datetime(dt: Union[str, datetime]) -> datetime:
    """
    Ensure input is datetime object (timezone-naive)
    
    Args:
        dt: Time string or datetime object
        
    Returns:
        Timezone-naive datetime object
    """
    if isinstance(dt, datetime):
        # If datetime object, remove timezone info
        if dt.tzinfo is not None:
            return dt.replace(tzinfo=None)
        return dt
    elif isinstance(dt, str):
        # If string, parse to datetime
        return parse_time(dt)
    else:
        raise ValueError(f"Unsupported time type: {type(dt)}")

def ensure_iso_format(dt: datetime) -> str:
    """Ensure datetime object is converted to ISO 8601 format string (timezone-naive)"""
    if not isinstance(dt, datetime):
        return str(dt)
    
    # Ensure timezone-naive
    dt_no_tz = dt.replace(tzinfo=None) if dt.tzinfo else dt
    return dt_no_tz.isoformat()

def ensure_iso_string(dt: Union[datetime, str]) -> str:
    """Ensure input is ISO format string (timezone-naive)"""
    if isinstance(dt, datetime):
        return ensure_iso_format(dt)
    return dt

def parse_iso_time(iso_str: str) -> datetime:
    """Parse ISO 8601 format time string (returns timezone-naive datetime)"""
    try:
        dt = datetime.fromisoformat(iso_str)
        # Remove timezone info
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    except ValueError:
        # Try handling format with Z
        try:
            dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
            return dt.replace(tzinfo=None)
        except ValueError:
            raise ValueError(f"Cannot parse time string: {iso_str}")

def standardize_dict_times(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Standardize time fields in dictionary, unify all time values to ISO format string (timezone-naive)
    
    Common time fields include: created_at, updated_at, timestamp etc
    
    Args:
        data: Dictionary containing time fields
        
    Returns:
        Standardized dictionary (does not modify original dictionary)
    """
    if not isinstance(data, dict):
        return data
        
    result = data.copy()
    time_fields = [
        "created_at", "updated_at", "timestamp", 
        "start_time", "end_time", "time", "date", 
        "reference_time", "last_updated"
    ]
    
    for field in time_fields:
        if field in result and result[field] is not None:
            result[field] = ensure_iso_string(result[field])
            
    # Handle nested time window
    if "time_window" in result and isinstance(result["time_window"], dict):
        if "start" in result["time_window"]:
            result["time_window"]["start"] = ensure_iso_string(result["time_window"]["start"])
        if "end" in result["time_window"]:
            result["time_window"]["end"] = ensure_iso_string(result["time_window"]["end"])
            
    # Handle time fields in metadata
    if "metadata" in result and isinstance(result["metadata"], dict):
        # Handle time fields in metadata
        for field in ["created_at", "updated_at", "time_window_start", "time_window_end"]:
            if field in result["metadata"] and result["metadata"][field] is not None:
                result["metadata"][field] = ensure_iso_string(result["metadata"][field])
                
    return result

def is_date_between(target_date: Union[str, datetime], 
                  start_date: Union[str, datetime], 
                  end_date: Union[str, datetime]) -> bool:
    """
    Check if target date is between two dates (inclusive)
    
    Args:
        target_date: Target date
        start_date: Start date
        end_date: End date
        
    Returns:
        Returns True if target date is in range; otherwise returns False
    """
    target = parse_time(target_date)
    start = parse_time(start_date)
    end = parse_time(end_date)
    
    if not all([target, start, end]):
        return False
        
    return start <= target <= end

def get_utc_now() -> datetime:
    """
    Get current time (timezone-naive) - only for internal system time, not for memory generation
    
    Returns:
        Timezone-naive current datetime object
    """
    return datetime.now()

def get_utc_now_iso() -> str:
    """
    Get current time in ISO format string (timezone-naive) - only for internal system time, not for memory generation
    
    Returns:
        ISO format current time string
    """
    return ensure_iso_string(get_utc_now())

def json_serialize_time(obj: Any) -> Any:
    """
    Custom JSON serialization function to handle datetime objects
    
    Args:
        obj: Object to serialize
        
    Returns:
        JSON serializable object
    """
    if isinstance(obj, datetime):
        return ensure_iso_string(obj)
    raise TypeError(f"Type {type(obj)} cannot be serialized to JSON")

def safe_json_dumps(data: Any) -> str:
    """
    Safely serialize object to JSON string, correctly handle datetime objects
    
    Args:
        data: Object to serialize
        
    Returns:
        JSON string
    """
    return json.dumps(data, default=json_serialize_time)

def safe_json_loads(json_str: str) -> Any:
    """
    Safely deserialize JSON string to object
    
    Args:
        json_str: JSON string
        
    Returns:
        Deserialized object
    """
    return json.loads(json_str)

def extract_date_part(dt: Union[str, datetime]) -> datetime:
    """
    Extract date part (time set to 00:00:00)
    
    Args:
        dt: Date time
        
    Returns:
        Datetime object with only date part (time set to 00:00:00, timezone-naive)
    """
    datetime_obj = parse_time(dt)
    if not datetime_obj:
        return None
    
    return datetime(
        year=datetime_obj.year, 
        month=datetime_obj.month, 
        day=datetime_obj.day
    )

def date_diff_days(date1: Union[str, datetime], date2: Union[str, datetime]) -> int:
    """
    Calculate the number of days between two dates
    
    Args:
        date1: First date
        date2: Second date
        
    Returns:
        Absolute value of days difference
    """
    dt1 = parse_time(date1)
    dt2 = parse_time(date2)
    
    if not dt1 or not dt2:
        return None
        
    # Extract date part
    dt1_date = extract_date_part(dt1)
    dt2_date = extract_date_part(dt2)
    
    # Calculate difference
    delta = abs((dt1_date - dt2_date).days)
    return delta

def update_memory_timestamps(memory: Any) -> Any:
    """
    Update memory object timestamps to standard format (timezone-naive)
    
    Args:
        memory: Memory object
        
    Returns:
        Updated memory object
    """
    if not memory:
        return memory
        
    # Object attribute processing
    if hasattr(memory, 'created_at') and memory.created_at:
        memory.created_at = ensure_iso_string(memory.created_at)
        
    if hasattr(memory, 'updated_at') and memory.updated_at:
        memory.updated_at = ensure_iso_string(memory.updated_at)
        
    # Dictionary processing
    if isinstance(memory, dict):
        return standardize_dict_times(memory)
        
    return memory 

def parse_time(time_str: Union[str, datetime]) -> datetime:
    """
    Convert time string or datetime object to timezone-naive datetime object
    """
    if isinstance(time_str, datetime):
        # If datetime object, remove timezone info
        return time_str.replace(tzinfo=None) if time_str.tzinfo else time_str
    
    if isinstance(time_str, str):
        try:
            # Try parsing ISO format
            dt = datetime.fromisoformat(time_str)
            return dt.replace(tzinfo=None) if dt.tzinfo else dt
        except ValueError:
            try:
                # Try handling format with Z
                dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                return dt.replace(tzinfo=None)
            except ValueError:
                # Try standard format
                try:
                    dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                    return dt
                except ValueError:
                    raise ValueError(f"Cannot parse time string: {time_str}")
    
    raise ValueError(f"Unsupported time type: {type(time_str)}")

def calculate_time_window(base_time: Union[str, datetime], window_days: int) -> Dict[str, datetime]:
    """
    Calculate N days time window before given time point (timezone-naive)
    """
    end_time = parse_time(base_time)
    start_time = end_time - timedelta(days=window_days)
    
    return {
        "start_time": start_time,
        "end_time": end_time
    }

def normalize_datetime(dt: Union[str, datetime]) -> datetime:
    """
    Normalize datetime object, ensure timezone-naive
    
    Args:
        dt: Time string or datetime object
        
    Returns:
        Timezone-naive datetime object
    """
    return parse_time(dt)

def compare_times(time1: Union[str, datetime], time2: Union[str, datetime]) -> int:
    """
    Compare two times
    
    Args:
        time1: First time
        time2: Second time
        
    Returns:
        -1: time1 < time2
         0: time1 == time2
         1: time1 > time2
    """
    dt1 = parse_time(time1)
    dt2 = parse_time(time2)
    
    if dt1 < dt2:
        return -1
    elif dt1 == dt2:
        return 0
    else:
        return 1 