"""
TiMem Time Window Calculator

Provides unified implementation of time window calculation for memory levels, supports L1-L5 level time window calculation
Uniformly uses timezone-naive datetime format to avoid timezone confusion issues.
"""

from datetime import datetime, timedelta, date
from typing import Dict, Any, Optional, Tuple

class TimeWindowCalculator:
    """Time window calculator"""
    
    @staticmethod
    def calculate_l1_time_window(reference_time: datetime) -> Dict[str, datetime]:
        """
        Calculate L1 fragment-level memory time window
        
        Args:
            reference_time: Reference time point (timezone-naive)
            
        Returns:
            Dict[str, datetime]: Time window dictionary with start and end (timezone-naive)
        """
        # Ensure timezone-naive
        ref_time = reference_time.replace(tzinfo=None) if reference_time.tzinfo else reference_time
        
        # L1 is usually generated in real-time, use same time point as start and end
        return {
            "start": ref_time,
            "end": ref_time
        }
    
    @staticmethod
    def calculate_l2_time_window(reference_time: datetime) -> Dict[str, datetime]:
        """
        Calculate L2 session-level memory time window
        
        Args:
            reference_time: Reference time point (timezone-naive)
            
        Returns:
            Dict[str, datetime]: Time window dictionary with start and end (timezone-naive)
        """
        # Ensure timezone-naive
        ref_time = reference_time.replace(tzinfo=None) if reference_time.tzinfo else reference_time
        
        # L2 is session-level, use reference time's day start to day end as window
        day_start = datetime(
            ref_time.year, 
            ref_time.month,
            ref_time.day,
            0, 0, 0
        )
        
        day_end = datetime(
            ref_time.year, 
            ref_time.month,
            ref_time.day,
            23, 59, 59
        )
        
        return {
            "start": day_start,
            "end": day_end
        }
    
    @staticmethod
    def calculate_l3_time_window(reference_time: datetime) -> Dict[str, datetime]:
        """
        Calculate L3 daily-level memory time window
        
        Args:
            reference_time: Reference time point (timezone-naive)
            
        Returns:
            Dict[str, datetime]: Time window dictionary with start and end (timezone-naive)
        """
        # Ensure timezone-naive
        ref_time = reference_time.replace(tzinfo=None) if reference_time.tzinfo else reference_time
        
        # L3 is daily-level, range is entire date
        day_start = datetime(
            ref_time.year, 
            ref_time.month,
            ref_time.day,
            0, 0, 0
        )
        
        day_end = datetime(
            ref_time.year, 
            ref_time.month,
            ref_time.day,
            23, 59, 59
        )
        
        return {
            "start": day_start,
            "end": day_end
        }
    
    @staticmethod
    def calculate_l4_time_window(reference_time: datetime) -> Dict[str, datetime]:
        """
        Calculate L4 weekly-level memory time window
        
        Args:
            reference_time: Reference time point (timezone-naive)
            
        Returns:
            Dict[str, datetime]: Time window dictionary with start and end (timezone-naive)
        """
        # Ensure timezone-naive
        ref_time = reference_time.replace(tzinfo=None) if reference_time.tzinfo else reference_time
        
        # Get current date weekday
        weekday = ref_time.weekday()  # 0-6, 0 is Monday
        
        # Calculate this week start date (Monday)
        week_start_date = ref_time - timedelta(days=weekday)
        week_start = datetime(
            week_start_date.year,
            week_start_date.month,
            week_start_date.day,
            0, 0, 0
        )
        
        # Calculate this week end date (Sunday)
        week_end_date = week_start_date + timedelta(days=6)
        week_end = datetime(
            week_end_date.year,
            week_end_date.month,
            week_end_date.day,
            23, 59, 59
        )
        
        return {
            "start": week_start,
            "end": week_end
        }
    
    @staticmethod
    def calculate_l5_time_window(reference_time: datetime) -> Dict[str, datetime]:
        """
        Calculate L5 monthly-level memory time window
        
        Args:
            reference_time: Reference time point (timezone-naive)
            
        Returns:
            Dict[str, datetime]: Time window dictionary with start and end (timezone-naive)
        """
        # Ensure timezone-naive
        ref_time = reference_time.replace(tzinfo=None) if reference_time.tzinfo else reference_time
        
        # Calculate month start
        month_start = datetime(
            ref_time.year,
            ref_time.month,
            1,  # First day of month
            0, 0, 0
        )
        
        # Calculate next month start (to determine month end)
        if ref_time.month == 12:
            next_month = datetime(
                ref_time.year + 1,
                1,
                1,
                0, 0, 0
            )
        else:
            next_month = datetime(
                ref_time.year,
                ref_time.month + 1,
                1,
                0, 0, 0
            )
        
        # Month end is one microsecond before next month start
        month_end = next_month - timedelta(microseconds=1)
        
        return {
            "start": month_start,
            "end": month_end
        }
    
    @staticmethod
    def calculate_time_window(memory_level: str, reference_time: datetime) -> Dict[str, datetime]:
        """
        Calculate time window based on memory level
        
        Args:
            memory_level: Memory level (L1, L2, L3, L4, L5)
            reference_time: Reference time point (timezone-naive)
            
        Returns:
            Dict[str, datetime]: Time window dictionary with start and end (timezone-naive)
        """
        if memory_level == "L1":
            return TimeWindowCalculator.calculate_l1_time_window(reference_time)
        elif memory_level == "L2":
            return TimeWindowCalculator.calculate_l2_time_window(reference_time)
        elif memory_level == "L3":
            return TimeWindowCalculator.calculate_l3_time_window(reference_time)
        elif memory_level == "L4":
            return TimeWindowCalculator.calculate_l4_time_window(reference_time)
        elif memory_level == "L5":
            return TimeWindowCalculator.calculate_l5_time_window(reference_time)
        else:
            raise ValueError(f"Unsupported memory level: {memory_level}")
    
    @staticmethod
    def is_same_day(dt1: datetime, dt2: datetime) -> bool:
        """
        Determine if two times are on the same day
        
        Args:
            dt1: First time point (timezone-naive)
            dt2: Second time point (timezone-naive)
            
        Returns:
            bool: Whether on same day
        """
        # Ensure timezone-naive
        dt1_no_tz = dt1.replace(tzinfo=None) if dt1.tzinfo else dt1
        dt2_no_tz = dt2.replace(tzinfo=None) if dt2.tzinfo else dt2
        return dt1_no_tz.date() == dt2_no_tz.date()
    
    @staticmethod
    def is_different_day(dt1: datetime, dt2: datetime) -> bool:
        """
        Determine if two times are on different dates
        
        Args:
            dt1: First time point (timezone-naive)
            dt2: Second time point (timezone-naive)
            
        Returns:
            bool: Whether on different days
        """
        return not TimeWindowCalculator.is_same_day(dt1, dt2)
    
    @staticmethod
    def is_same_week(dt1: datetime, dt2: datetime) -> bool:
        """
        Determine if two times are in the same week
        
        Args:
            dt1: First time point (timezone-naive)
            dt2: Second time point (timezone-naive)
            
        Returns:
            bool: Whether in same week
        """
        # Ensure timezone-naive
        dt1_no_tz = dt1.replace(tzinfo=None) if dt1.tzinfo else dt1
        dt2_no_tz = dt2.replace(tzinfo=None) if dt2.tzinfo else dt2
        year1, week1, _ = dt1_no_tz.isocalendar()
        year2, week2, _ = dt2_no_tz.isocalendar()
        return (year1, week1) == (year2, week2)
    
    @staticmethod
    def is_different_week(dt1: datetime, dt2: datetime) -> bool:
        """
        Determine if two times are in different weeks
        
        Args:
            dt1: First time point (timezone-naive)
            dt2: Second time point (timezone-naive)
            
        Returns:
            bool: Whether in different weeks
        """
        return not TimeWindowCalculator.is_same_week(dt1, dt2)
    
    @staticmethod
    def is_same_month(dt1: datetime, dt2: datetime) -> bool:
        """
        Determine if two times are in the same month
        
        Args:
            dt1: First time point (timezone-naive)
            dt2: Second time point (timezone-naive)
            
        Returns:
            bool: Whether in same month
        """
        # Ensure timezone-naive
        dt1_no_tz = dt1.replace(tzinfo=None) if dt1.tzinfo else dt1
        dt2_no_tz = dt2.replace(tzinfo=None) if dt2.tzinfo else dt2
        return dt1_no_tz.year == dt2_no_tz.year and dt1_no_tz.month == dt2_no_tz.month 
        
    @staticmethod
    def is_different_month(dt1: datetime, dt2: datetime) -> bool:
        """
        Determine if two times are in different months
        
        Args:
            dt1: First time point (timezone-naive)
            dt2: Second time point (timezone-naive)
            
        Returns:
            bool: Whether in different months
        """
        return not TimeWindowCalculator.is_same_month(dt1, dt2)
        
    @staticmethod
    def get_day_start_end(timestamp: datetime) -> Tuple[datetime, datetime]:
        """
        Get day start and end time
        
        Args:
            timestamp: Date time (timezone-naive)
            
        Returns:
            Tuple[datetime, datetime]: Day start and end time (timezone-naive)
        """
        # Ensure timezone-naive
        ts_no_tz = timestamp.replace(tzinfo=None) if timestamp.tzinfo else timestamp
        
        day_start = datetime(
            ts_no_tz.year,
            ts_no_tz.month,
            ts_no_tz.day,
            0, 0, 0
        )
        
        day_end = datetime(
            ts_no_tz.year,
            ts_no_tz.month,
            ts_no_tz.day,
            23, 59, 59, 999999
        )
        
        return day_start, day_end
        
    @staticmethod
    def get_week_start_end(timestamp: datetime) -> Tuple[datetime, datetime]:
        """
        Get week start and end time
        
        Args:
            timestamp: Date time (timezone-naive)
            
        Returns:
            Tuple[datetime, datetime]: Week start and end time (timezone-naive)
        """
        # Ensure timezone-naive
        ts_no_tz = timestamp.replace(tzinfo=None) if timestamp.tzinfo else timestamp
        
        weekday = ts_no_tz.weekday()  # 0-6, 0 is Monday
        
        # Calculate this week start date (Monday)
        week_start_date = ts_no_tz - timedelta(days=weekday)
        week_start = datetime(
            week_start_date.year,
            week_start_date.month,
            week_start_date.day,
            0, 0, 0
        )
        
        # Calculate this week end date (Sunday)
        week_end_date = week_start_date + timedelta(days=6)
        week_end = datetime(
            week_end_date.year,
            week_end_date.month,
            week_end_date.day,
            23, 59, 59, 999999
        )
        
        return week_start, week_end
        
    @staticmethod
    def get_month_start_end(timestamp: datetime) -> Tuple[datetime, datetime]:
        """
        Get month start and end time
        
        Args:
            timestamp: Date time (timezone-naive)
            
        Returns:
            Tuple[datetime, datetime]: Month start and end time (timezone-naive)
        """
        # Ensure timezone-naive
        ts_no_tz = timestamp.replace(tzinfo=None) if timestamp.tzinfo else timestamp
        
        # Calculate month start
        month_start = datetime(
            ts_no_tz.year,
            ts_no_tz.month,
            1,  # First day of month
            0, 0, 0
        )
        
        # Calculate next month start (to determine month end)
        if ts_no_tz.month == 12:
            next_month = datetime(
                ts_no_tz.year + 1,
                1,
                1,
                0, 0, 0
            )
        else:
            next_month = datetime(
                ts_no_tz.year,
                ts_no_tz.month + 1,
                1,
                0, 0, 0
            )
        
        # Month end is one microsecond before next month start
        month_end = next_month - timedelta(microseconds=1)
        
        return month_start, month_end