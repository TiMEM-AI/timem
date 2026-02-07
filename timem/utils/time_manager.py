"""
TiMem centralized time manager

Provides unified time processing functions to solve time format inconsistency and timezone handling issues
Unified use of timezone-free datetime format to avoid timezone confusion.
"""

from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
import calendar


class TimeManager:
    """
    Centralized time manager providing unified time processing functions (timezone-free)
    """
    
    def __init__(self, timezone_offset: int = 8):
        """
        Initialize time manager
        
        Args:
            timezone_offset: Timezone offset, default is UTC+8, but actually uses timezone-free
        """
        self.timezone_offset = timezone_offset
        # Note: Although timezone_offset parameter is retained for backward compatibility, actually uses timezone-free
    
    def get_current_time(self) -> datetime:
        """
        Discourage using local current time in business logic; this method exists only for backward compatibility.
        If called, returns timezone-free current time, but upstream should avoid relying on it.
        """
        return datetime.now().replace(tzinfo=None)
    
    def get_current_time_utc(self) -> datetime:
        """Compatibility method, same as get_current_time."""
        return datetime.now().replace(tzinfo=None)
    
    def format_time(self, dt: datetime, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
        """
        Format time
        
        Args:
            dt: Time object (timezone-free)
            format_str: Format string
            
        Returns:
            Formatted time string
        """
        # Ensure timezone-free
        dt_no_tz = dt.replace(tzinfo=None) if dt.tzinfo else dt
        return dt_no_tz.strftime(format_str)
    
    def parse_time(self, time_str: str, format_str: str = "%Y-%m-%d %H:%M:%S") -> datetime:
        """
        Parse time string
        
        Args:
            time_str: Time string
            format_str: Format string
            
        Returns:
            Parsed time object (timezone-free)
        """
        dt = datetime.strptime(time_str, format_str)
        return dt  # Already timezone-free
    
    def parse_iso_time(self, time_str: str) -> datetime:
        """
        Parse ISO format time string
        
        Args:
            time_str: Time string
            
        Returns:
            Parsed time object (timezone-free)
        """
        dt = datetime.fromisoformat(time_str)
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    
    def ensure_timezone(self, dt: datetime) -> datetime:
        """
        Ensure time object is timezone-free (maintain method name compatibility)
        
        Args:
            dt: Time object
            
        Returns:
            Timezone-free time object
        """
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    
    def normalize_to_utc(self, dt: datetime) -> datetime:
        """
        Normalize time to timezone-free (maintain method name compatibility)
        
        Args:
            dt: Time object
            
        Returns:
            Timezone-free time object
        """
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    
    def is_same_day(self, dt1: datetime, dt2: datetime) -> bool:
        """
        Check if two times are on the same day
        
        Args:
            dt1: First time object (timezone-free)
            dt2: Second time object (timezone-free)
            
        Returns:
            Whether they are on the same day
        """
        dt1_no_tz = dt1.replace(tzinfo=None) if dt1.tzinfo else dt1
        dt2_no_tz = dt2.replace(tzinfo=None) if dt2.tzinfo else dt2
        return dt1_no_tz.date() == dt2_no_tz.date()
    
    def is_same_week(self, dt1: datetime, dt2: datetime) -> bool:
        """
        Check if two times are in the same week
        
        Args:
            dt1: First time object (timezone-free)
            dt2: Second time object (timezone-free)
            
        Returns:
            Whether they are in the same week
        """
        dt1_no_tz = dt1.replace(tzinfo=None) if dt1.tzinfo else dt1
        dt2_no_tz = dt2.replace(tzinfo=None) if dt2.tzinfo else dt2
        year1, week1, _ = dt1_no_tz.isocalendar()
        year2, week2, _ = dt2_no_tz.isocalendar()
        return (year1, week1) == (year2, week2)
    
    def is_same_month(self, dt1: datetime, dt2: datetime) -> bool:
        """
        Check if two times are in the same month
        
        Args:
            dt1: First time object (timezone-free)
            dt2: Second time object (timezone-free)
            
        Returns:
            Whether they are in the same month
        """
        dt1_no_tz = dt1.replace(tzinfo=None) if dt1.tzinfo else dt1
        dt2_no_tz = dt2.replace(tzinfo=None) if dt2.tzinfo else dt2
        return dt1_no_tz.year == dt2_no_tz.year and dt1_no_tz.month == dt2_no_tz.month
    
    def is_new_day(self, current_time: datetime, reference_time: datetime) -> bool:
        """
        Check if a new day has arrived
        
        Args:
            current_time: Current time (timezone-free)
            reference_time: Reference time (timezone-free)
            
        Returns:
            Whether a new day has arrived
        """
        current_no_tz = current_time.replace(tzinfo=None) if current_time.tzinfo else current_time
        reference_no_tz = reference_time.replace(tzinfo=None) if reference_time.tzinfo else reference_time
        return current_no_tz.date() > reference_no_tz.date()
    
    def is_new_week(self, current_time: datetime, reference_time: datetime) -> bool:
        """
        Check if a new week has arrived
        
        Args:
            current_time: Current time (timezone-free)
            reference_time: Reference time (timezone-free)
            
        Returns:
            Whether a new week has arrived
        """
        current_no_tz = current_time.replace(tzinfo=None) if current_time.tzinfo else current_time
        reference_no_tz = reference_time.replace(tzinfo=None) if reference_time.tzinfo else reference_time
        current_week = current_no_tz.isocalendar()[1]
        reference_week = reference_no_tz.isocalendar()[1]
        return current_week > reference_week
    
    def is_new_month(self, current_time: datetime, reference_time: datetime) -> bool:
        """
        Check if a new month has arrived
        
        Args:
            current_time: Current time (timezone-free)
            reference_time: Reference time (timezone-free)
            
        Returns:
            Whether a new month has arrived
        """
        current_no_tz = current_time.replace(tzinfo=None) if current_time.tzinfo else current_time
        reference_no_tz = reference_time.replace(tzinfo=None) if reference_time.tzinfo else reference_time
        return (current_no_tz.year, current_no_tz.month) > (reference_no_tz.year, reference_no_tz.month)
    
    def get_day_start(self, dt: datetime) -> datetime:
        """
        Get day start time
        
        Args:
            dt: Date time (timezone-free)
            
        Returns:
            Day start time (timezone-free)
        """
        dt_no_tz = dt.replace(tzinfo=None) if dt.tzinfo else dt
        return datetime(
            dt_no_tz.year,
            dt_no_tz.month,
            dt_no_tz.day,
            0, 0, 0
        )
    
    def get_day_end(self, dt: datetime) -> datetime:
        """
        Get day end time
        
        Args:
            dt: Date time (timezone-free)
            
        Returns:
            Day end time (timezone-free)
        """
        dt_no_tz = dt.replace(tzinfo=None) if dt.tzinfo else dt
        return datetime(
            dt_no_tz.year,
            dt_no_tz.month,
            dt_no_tz.day,
            23, 59, 59
        )
    
    def get_week_start(self, dt: datetime) -> datetime:
        """
        Get week start time (Monday)
        
        Args:
            dt: Date time (timezone-free)
            
        Returns:
            Week start time (timezone-free)
        """
        dt_no_tz = dt.replace(tzinfo=None) if dt.tzinfo else dt
        weekday = dt_no_tz.weekday()  # 0-6, 0 is Monday
        week_start_date = dt_no_tz - timedelta(days=weekday)
        return datetime(
            week_start_date.year,
            week_start_date.month,
            week_start_date.day,
            0, 0, 0
        )
    
    def get_week_end(self, dt: datetime) -> datetime:
        """
        Get week end time (Sunday)
        
        Args:
            dt: Date time (timezone-free)
            
        Returns:
            Week end time (timezone-free)
        """
        dt_no_tz = dt.replace(tzinfo=None) if dt.tzinfo else dt
        weekday = dt_no_tz.weekday()  # 0-6, 0 is Monday
        week_start_date = dt_no_tz - timedelta(days=weekday)
        week_end_date = week_start_date + timedelta(days=6)
        return datetime(
            week_end_date.year,
            week_end_date.month,
            week_end_date.day,
            23, 59, 59
        )
    
    def get_month_start(self, dt: datetime) -> datetime:
        """
        Get month start time
        
        Args:
            dt: Date time (timezone-free)
            
        Returns:
            Month start time (timezone-free)
        """
        dt_no_tz = dt.replace(tzinfo=None) if dt.tzinfo else dt
        return datetime(
            dt_no_tz.year,
            dt_no_tz.month,
            1,
            0, 0, 0
        )
    
    def get_month_end(self, dt: datetime) -> datetime:
        """
        Get month end time
        
        Args:
            dt: Date time (timezone-free)
            
        Returns:
            Month end time (timezone-free)
        """
        dt_no_tz = dt.replace(tzinfo=None) if dt.tzinfo else dt
        if dt_no_tz.month == 12:
            next_month = datetime(dt_no_tz.year + 1, 1, 1)
        else:
            next_month = datetime(dt_no_tz.year, dt_no_tz.month + 1, 1)
        month_end = next_month - timedelta(microseconds=1)
        return month_end
    
    def get_previous_day(self, dt: datetime) -> datetime:
        """
        Get previous day
        
        Args:
            dt: Date time (timezone-free)
            
        Returns:
            Previous day (timezone-free)
        """
        dt_no_tz = dt.replace(tzinfo=None) if dt.tzinfo else dt
        return dt_no_tz - timedelta(days=1)
    
    def get_previous_week(self, dt: datetime) -> datetime:
        """
        Get previous week
        
        Args:
            dt: Date time (timezone-free)
            
        Returns:
            Previous week (timezone-free)
        """
        dt_no_tz = dt.replace(tzinfo=None) if dt.tzinfo else dt
        return dt_no_tz - timedelta(weeks=1)
    
    def get_previous_month(self, dt: datetime) -> datetime:
        """
        Get previous month
        
        Args:
            dt: Date time (timezone-free)
            
        Returns:
            Previous month (timezone-free)
        """
        dt_no_tz = dt.replace(tzinfo=None) if dt.tzinfo else dt
        if dt_no_tz.month == 1:
            return datetime(dt_no_tz.year - 1, 12, dt_no_tz.day)
        else:
            return datetime(dt_no_tz.year, dt_no_tz.month - 1, dt_no_tz.day)
    
    def calculate_time_window(self, layer: str, reference_time: datetime) -> Dict[str, Any]:
        """
        Calculate time window
        
        Args:
            layer: Memory layer, such as "L1", "L2", "L3", "L4", "L5"
            reference_time: Reference time (timezone-free)
            
        Returns:
            Time window information
        """
        reference_time = self.ensure_timezone(reference_time)
        
        if layer == "L1":
            # L1 does not need time window, uses current session
            return {
                "description": "Current session time window",
                "start_time": reference_time - timedelta(minutes=60),  # Default 1 hour
                "end_time": reference_time
            }
        
        elif layer == "L2":
            # L2 uses current day time window
            day_start = self.get_day_start(reference_time)
            return {
                "description": f"{day_start.strftime('%Y-%m-%d')} session window",
                "start_time": day_start,
                "end_time": self.get_day_end(reference_time)
            }
        
        elif layer == "L3":
            # L3 uses current day time window
            day_start = self.get_day_start(reference_time)
            day_end = self.get_day_end(reference_time)
            return {
                "description": f"{day_start.strftime('%Y-%m-%d')} daily report window",
                "start_time": day_start,
                "end_time": day_end
            }
        
        elif layer == "L4":
            # L4 uses current week time window
            week_start = self.get_week_start(reference_time)
            week_end = self.get_week_end(reference_time)
            return {
                "description": f"{week_start.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')} weekly report window",
                "start_time": week_start,
                "end_time": week_end
            }
        
        elif layer == "L5":
            # L5 uses current month time window
            month_start = self.get_month_start(reference_time)
            month_end = self.get_month_end(reference_time)
            return {
                "description": f"{month_start.strftime('%Y-%m-%d')} to {month_end.strftime('%Y-%m-%d')} monthly report window",
                "start_time": month_start,
                "end_time": month_end
            }
        
        else:
            raise ValueError(f"Unsupported memory layer: {layer}")
    
    def calculate_l1_time_window(self, session_id: str, reference_time: datetime) -> Dict[str, Any]:
        """
        Calculate L1 time window
        
        Args:
            session_id: Session ID
            reference_time: Reference time (timezone-free)
            
        Returns:
            L1 time window
        """
        return self.calculate_time_window("L1", reference_time)
    
    def calculate_l2_time_window(self, reference_date: datetime) -> Dict[str, Any]:
        """
        Calculate L2 time window
        
        Args:
            reference_date: Reference date (timezone-free)
            
        Returns:
            L2 time window
        """
        return self.calculate_time_window("L2", reference_date)
    
    def calculate_l3_time_window(self, reference_date: datetime) -> Dict[str, Any]:
        """
        Calculate L3 time window
        
        Args:
            reference_date: Reference date (timezone-free)
            
        Returns:
            L3 time window
        """
        return self.calculate_time_window("L3", reference_date)
    
    def calculate_l4_time_window(self, reference_date: datetime) -> Dict[str, Any]:
        """
        Calculate L4 time window
        
        Args:
            reference_date: Reference date (timezone-free)
            
        Returns:
            L4 time window
        """
        return self.calculate_time_window("L4", reference_date)
    
    def calculate_l5_time_window(self, reference_date: datetime) -> Dict[str, Any]:
        """
        Calculate L5 time window
        
        Args:
            reference_date: Reference date (timezone-free)
            
        Returns:
            L5 time window
        """
        return self.calculate_time_window("L5", reference_date)
    
    def time_window_to_dict(self, time_window: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert time window to dictionary format
        
        Args:
            time_window: Time window
            
        Returns:
            Dictionary format time window
        """
        result = {}
        for key, value in time_window.items():
            if isinstance(value, datetime):
                result[key] = value.isoformat()
            else:
                result[key] = value
        return result
    
    def dict_to_time_window(self, time_window_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert dictionary format to time window
        
        Args:
            time_window_dict: Dictionary format time window
            
        Returns:
            Time window
        """
        result = {}
        for key, value in time_window_dict.items():
            if key in ['start_time', 'end_time'] and isinstance(value, str):
                try:
                    result[key] = datetime.fromisoformat(value)
                except ValueError:
                    result[key] = value
            else:
                result[key] = value
        return result
    
    def calculate_date_diff(self, dt1: datetime, dt2: datetime) -> int:
        """
        Calculate days difference between two dates
        
        Args:
            dt1: First date (timezone-free)
            dt2: Second date (timezone-free)
            
        Returns:
            Days difference
        """
        dt1_no_tz = dt1.replace(tzinfo=None) if dt1.tzinfo else dt1
        dt2_no_tz = dt2.replace(tzinfo=None) if dt2.tzinfo else dt2
        return (dt1_no_tz.date() - dt2_no_tz.date()).days
    
    def calculate_week_diff(self, dt1: datetime, dt2: datetime) -> int:
        """
        Calculate weeks difference between two dates
        
        Args:
            dt1: First date (timezone-free)
            dt2: Second date (timezone-free)
            
        Returns:
            Weeks difference
        """
        dt1_no_tz = dt1.replace(tzinfo=None) if dt1.tzinfo else dt1
        dt2_no_tz = dt2.replace(tzinfo=None) if dt2.tzinfo else dt2
        year1, week1, _ = dt1_no_tz.isocalendar()
        year2, week2, _ = dt2_no_tz.isocalendar()
        return (year1 - year2) * 52 + (week1 - week2)
    
    def calculate_month_diff(self, dt1: datetime, dt2: datetime) -> int:
        """
        Calculate months difference between two dates
        
        Args:
            dt1: First date (timezone-free)
            dt2: Second date (timezone-free)
            
        Returns:
            Months difference
        """
        dt1_no_tz = dt1.replace(tzinfo=None) if dt1.tzinfo else dt1
        dt2_no_tz = dt2.replace(tzinfo=None) if dt2.tzinfo else dt2
        return (dt1_no_tz.year - dt2_no_tz.year) * 12 + (dt1_no_tz.month - dt2_no_tz.month)


def get_time_manager() -> TimeManager:
    """
    Get time manager instance
    
    Returns:
        Time manager instance
    """
    return TimeManager()