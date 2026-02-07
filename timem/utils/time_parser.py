"""
TiMem unified time parsing module

Provides unified time parsing functionality, including:
1. Parse Locomo format to ISO format
2. Determine if a new day or new week has arrived based on real calendar
3. Calculate memory timestamps for each layer based on memory generation logic
4. Unify time format to ISO 8601 standard (timezone-free)
"""
from datetime import datetime, timedelta, date
from typing import Optional, Dict, Any, Tuple
import re
import logging
from timem.utils.logging import get_logger

logger = get_logger(__name__)

class TimeParser:
    """Unified time parser - based on ISO 8601 standard (timezone-free)"""
    
    def __init__(self):
        self.logger = logger
    
    def parse_session_time(self, time_str: str) -> datetime:
        """
        Parse session time string, unified return ISO format datetime object (timezone-free)
        
        Args:
            time_str: Time string, supports multiple formats
            
        Returns:
            Parsed datetime object (ISO format, timezone-free)
            
        Raises:
            ValueError: When unable to parse time format
        """
        if not time_str or not isinstance(time_str, str):
            raise ValueError(f"Invalid time string: {time_str}")
        
        try:
            # Clean string
            clean_str = time_str.strip()
            
            # Try multiple time formats (prioritize LongMemEval format)
            parsed_time = self._try_parse_longmemeval_format(clean_str)
            if parsed_time:
                return self._ensure_iso_format(parsed_time)
            
            parsed_time = self._try_parse_locomo_format(clean_str)
            if parsed_time:
                return self._ensure_iso_format(parsed_time)
            
            parsed_time = self._try_parse_iso_format(clean_str)
            if parsed_time:
                return self._ensure_iso_format(parsed_time)
            
            parsed_time = self._try_parse_standard_format(clean_str)
            if parsed_time:
                return self._ensure_iso_format(parsed_time)
            
            # If all formats fail to parse, raise exception
            raise ValueError(f"Unable to parse time format: {time_str}")
            
        except Exception as e:
            self.logger.error(f"Time parsing failed: {time_str}, error: {e}")
            raise ValueError(f"Time parsing failed: {time_str}, error: {e}")
    
    # Add parse method as alias for parse_session_time
    def parse(self, time_str: str) -> datetime:
        """
        Parse time string (alias for parse_session_time)
        
        Args:
            time_str: Time string
            
        Returns:
            Parsed datetime object (timezone-free)
        """
        return self.parse_session_time(time_str)
    
    def _ensure_iso_format(self, dt: datetime) -> datetime:
        """
        Ensure datetime object conforms to ISO format standard (timezone-free)
        
        Args:
            dt: Input datetime object
            
        Returns:
            ISO format datetime object (timezone-free)
        """
        # Remove timezone information, ensure timezone-free
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        
        return dt
    
    def _try_parse_locomo_format(self, time_str: str) -> Optional[datetime]:
        """Parse Locomo format: "1:56 pm on 8 May, 2023" """
        try:
            # Fix regex to be more flexible
            pattern = r'(\d{1,2}):(\d{2})\s*(am|pm)\s*on\s*(\d{1,2})\s+(\w+),\s*(\d{4})'
            match = re.search(pattern, time_str, re.IGNORECASE)
            
            if not match:
                return None
            
            hour, minute, ampm, day, month_name, year = match.groups()
            
            # Convert hour to 24-hour format
            hour = int(hour)
            if ampm.lower() == 'pm' and hour != 12:
                hour += 12
            elif ampm.lower() == 'am' and hour == 12:
                hour = 0
            
            # Month name mapping
            month_map = {
                'january': 1, 'jan': 1,
                'february': 2, 'feb': 2,
                'march': 3, 'mar': 3,
                'april': 4, 'apr': 4,
                'may': 5,
                'june': 6, 'jun': 6,
                'july': 7, 'jul': 7,
                'august': 8, 'aug': 8,
                'september': 9, 'sep': 9,
                'october': 10, 'oct': 10,
                'november': 11, 'nov': 11,
                'december': 12, 'dec': 12
            }
            
            month = month_map.get(month_name.lower())
            if not month:
                return None
            
            # Create datetime object (timezone-free)
            dt = datetime(
                year=int(year),
                month=month,
                day=int(day),
                hour=hour,
                minute=int(minute)
            )
            
            return dt
            
        except Exception as e:
            self.logger.debug(f"Locomo format parsing failed: {time_str}, error: {e}")
            return None
    
    def _try_parse_iso_format(self, time_str: str) -> Optional[datetime]:
        """Parse ISO format: "2024-05-15T14:30:00Z" """
        try:
            # Try to parse ISO 8601 format
            if 'T' in time_str and ('Z' in time_str or '+' in time_str or '-' in time_str[-6:]):
                dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                return dt.replace(tzinfo=None)  # Remove timezone information
            elif 'T' in time_str:
                # ISO format without timezone information, parse directly
                dt = datetime.fromisoformat(time_str)
                return dt  # Already timezone-free
            else:
                return None
        except Exception as e:
            self.logger.debug(f"ISO format parsing failed: {time_str}, error: {e}")
            return None
    
    def _try_parse_longmemeval_format(self, time_str: str) -> Optional[datetime]:
        """Parse LongMemEval format: "2023/05/20 (Sat) 07:47" """
        try:
            # Match format: YYYY/MM/DD (Day) HH:MM
            pattern = r'(\d{4})/(\d{2})/(\d{2})\s*\([A-Za-z]+\)\s*(\d{2}):(\d{2})'
            match = re.match(pattern, time_str.strip())
            
            if not match:
                return None
            
            year, month, day, hour, minute = match.groups()
            
            # Create datetime object (timezone-free)
            dt = datetime(
                year=int(year),
                month=int(month),
                day=int(day),
                hour=int(hour),
                minute=int(minute)
            )
            
            return dt
            
        except Exception as e:
            self.logger.debug(f"LongMemEval format parsing failed: {time_str}, error: {e}")
            return None
    
    def _try_parse_standard_format(self, time_str: str) -> Optional[datetime]:
        """Parse standard format: "2024-05-15 14:30:00" """
        try:
            # Try to parse standard format
            if ' ' in time_str and '-' in time_str:
                dt = datetime.fromisoformat(time_str)
                return dt  # Already timezone-free
            else:
                return None
        except Exception as e:
            self.logger.debug(f"Standard format parsing failed: {time_str}, error: {e}")
            return None
    
    def to_iso_string(self, dt: datetime) -> str:
        """
        Convert datetime object to ISO string format (timezone-free)
        
        Args:
            dt: datetime object
            
        Returns:
            ISO format string (timezone-free)
        """
        dt = self._ensure_iso_format(dt)
        return dt.isoformat()
    
    def to_iso_timestamp(self, dt: datetime) -> float:
        """
        Convert datetime object to ISO timestamp
        
        Args:
            dt: datetime object
            
        Returns:
            ISO timestamp
        """
        dt = self._ensure_iso_format(dt)
        return dt.timestamp()
    
    def calculate_memory_timestamps(self, session_time: datetime) -> Dict[str, datetime]:
        """
        Calculate memory timestamps for each layer
        
        Args:
            session_time: Session time (timezone-free)
            
        Returns:
            Dictionary of memory timestamps for each layer
        """
        session_time = self._ensure_iso_format(session_time)
        
        # Calculate timestamps for each layer
        timestamps = {
            "L1": session_time,  # L1 uses session time
            "L2": session_time,  # L2 uses session time
            "L3": session_time,  # L3 uses session time
            "L4": session_time,  # L4 uses session time
            "L5": session_time   # L5 uses session time
        }
        
        return timestamps
    
    def calculate_time_windows(self, session_time: datetime) -> Dict[str, Dict[str, datetime]]:
        """
        Calculate time windows for each layer
        
        Args:
            session_time: Session time (timezone-free)
            
        Returns:
            Dictionary of time windows for each layer
        """
        session_time = self._ensure_iso_format(session_time)
        session_date = session_time.date()
        
        # L1/L2: session time window
        l1_window = {
            "start": session_time,
            "end": session_time
        }
        l2_window = {
            "start": session_time,
            "end": session_time
        }
        
        # L3: current day time window
        day_start = datetime.combine(session_date, datetime.min.time())
        day_end = datetime.combine(session_date, datetime.max.time().replace(microsecond=0))
        l3_window = {
            "start": day_start,
            "end": day_end
        }
        
        # L4: current week time window
        week_start = session_date - timedelta(days=session_date.weekday())
        week_end = week_start + timedelta(days=6)
        week_start_dt = datetime.combine(week_start, datetime.min.time())
        week_end_dt = datetime.combine(week_end, datetime.max.time().replace(microsecond=0))
        l4_window = {
            "start": week_start_dt,
            "end": week_end_dt
        }
        
        # L5: current month time window
        month_start = session_date.replace(day=1)
        if session_date.month == 12:
            next_month = session_date.replace(year=session_date.year + 1, month=1, day=1)
        else:
            next_month = session_date.replace(month=session_date.month + 1, day=1)
        month_end = next_month - timedelta(days=1)
        month_start_dt = datetime.combine(month_start, datetime.min.time())
        month_end_dt = datetime.combine(month_end, datetime.max.time().replace(microsecond=0))
        l5_window = {
            "start": month_start_dt,
            "end": month_end_dt
        }
        
        return {
            "L1": l1_window,
            "L2": l2_window,
            "L3": l3_window,
            "L4": l4_window,
            "L5": l5_window
        }
    
    def is_new_day(self, current_date: date, last_date: Optional[date]) -> bool:
        """
        Check if a new day has arrived
        
        Args:
            current_date: Current date
            last_date: Last date
            
        Returns:
            Whether a new day has arrived
        """
        if last_date is None:
            return True
        return current_date > last_date
    
    def is_new_week(self, current_date: date, last_date: Optional[date]) -> bool:
        """
        Check if a new week has arrived
        
        Args:
            current_date: Current date
            last_date: Last date
            
        Returns:
            Whether a new week has arrived
        """
        if last_date is None:
            return True
        
        # Calculate week numbers for current and last dates
        current_week = current_date.isocalendar()[1]
        last_week = last_date.isocalendar()[1]
        
        return current_week > last_week
    
    def is_new_month(self, current_date: date, last_date: Optional[date]) -> bool:
        """
        Check if a new month has arrived
        
        Args:
            current_date: Current date
            last_date: Last date
            
        Returns:
            Whether a new month has arrived
        """
        if last_date is None:
            return True
        
        return (current_date.year, current_date.month) > (last_date.year, last_date.month)
    
    def get_week_end_date(self, target_date: date) -> date:
        """
        Get the end date of the week containing the specified date (Sunday)
        
        Args:
            target_date: Target date
            
        Returns:
            Week end date
        """
        weekday = target_date.weekday()  # 0-6, 0 is Monday
        days_to_sunday = 6 - weekday
        return target_date + timedelta(days=days_to_sunday)
    
    def get_month_end_date(self, target_date: date) -> date:
        """
        Get the end date of the month containing the specified date
        
        Args:
            target_date: Target date
            
        Returns:
            Month end date
        """
        if target_date.month == 12:
            next_month = target_date.replace(year=target_date.year + 1, month=1, day=1)
        else:
            next_month = target_date.replace(month=target_date.month + 1, day=1)
        return next_month - timedelta(days=1)
    
    def get_month_range(self, year: int, month: int) -> Tuple[datetime, datetime]:
        """
        Get the start and end times of the specified year and month
        
        Args:
            year: Year
            month: Month
            
        Returns:
            Month start and end times
        """
        month_start = datetime(year, month, 1)
        
        if month == 12:
            next_month = datetime(year + 1, 1, 1)
        else:
            next_month = datetime(year, month + 1, 1)
        
        month_end = next_month - timedelta(microseconds=1)
        
        return month_start, month_end
    
    def should_trigger_daily_aggregation(self, current_date: date, last_daily_date: Optional[date]) -> bool:
        """
        Check if daily aggregation should be triggered
        
        Args:
            current_date: Current date
            last_daily_date: Last daily report date
            
        Returns:
            Whether daily aggregation should be triggered
        """
        if last_daily_date is None:
            return True
        
        return current_date > last_daily_date
    
    def should_trigger_weekly_aggregation(self, current_date: date, last_weekly_date: Optional[date]) -> bool:
        """
        Check if weekly aggregation should be triggered
        
        Args:
            current_date: Current date
            last_weekly_date: Last weekly report date
            
        Returns:
            Whether weekly aggregation should be triggered
        """
        if last_weekly_date is None:
            return True
        
        # Calculate week numbers for current and last weekly report dates
        current_week = current_date.isocalendar()[1]
        last_week = last_weekly_date.isocalendar()[1]
        
        return current_week > last_week
    
    def should_trigger_monthly_aggregation(self, current_date: date, last_monthly_date: Optional[date]) -> bool:
        """
        Check if monthly aggregation should be triggered
        
        Args:
            current_date: Current date
            last_monthly_date: Last monthly report date
            
        Returns:
            Whether monthly aggregation should be triggered
        """
        if last_monthly_date is None:
            return True
        
        return (current_date.year, current_date.month) > (last_monthly_date.year, last_monthly_date.month)
    
    def should_trigger_periodic_aggregation(self, first_interaction: datetime, last_interaction: datetime, 
                                         min_days: int = 30) -> bool:
        """
        Check if periodic aggregation should be triggered
        
        Args:
            first_interaction: First interaction time
            last_interaction: Last interaction time
            min_days: Minimum days
            
        Returns:
            Whether periodic aggregation should be triggered
        """
        time_diff = last_interaction - first_interaction
        return time_diff.days >= min_days
    
    def get_memory_layer_timestamps(self, session_data: Dict[str, Any]) -> Dict[str, datetime]:
        """
        Get memory layer timestamps from session data
        
        Args:
            session_data: Session data
            
        Returns:
            Memory layer timestamps
        """
        session_time = self._get_session_time(session_data)
        return self.calculate_memory_timestamps(session_time)
    
    def _get_session_time(self, session_data: Dict[str, Any]) -> datetime:
        """
        Get session time from session data
        
        Args:
            session_data: Session data
            
        Returns:
            Session time
        """
        # Try to get time from different fields
        time_fields = ['timestamp', 'session_time', 'created_at', 'time']
        
        for field in time_fields:
            if field in session_data and session_data[field]:
                time_value = session_data[field]
                if isinstance(time_value, str):
                    return self.parse_session_time(time_value)
                elif isinstance(time_value, datetime):
                    return self._ensure_iso_format(time_value)
        
        # If no time field found, use current time
        return datetime.now()
    
    def validate_session_time(self, session_data: Dict[str, Any]) -> bool:
        """
        Validate if session time is valid
        
        Args:
            session_data: Session data
            
        Returns:
            Whether time is valid
        """
        try:
            self._get_session_time(session_data)
            return True
        except Exception:
            return False

# Create global instance
time_parser = TimeParser()