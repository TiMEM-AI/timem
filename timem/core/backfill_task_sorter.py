"""
TiMem BackfillTaskSorter - Backfill Task Sorter

Responsible for complex sorting of backfill tasks, ensuring correct dependencies
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, date, timedelta
from collections import defaultdict

from timem.utils.logging import get_logger

logger = get_logger(__name__)


class BackfillTaskSorter:
    """
    Backfill Task Sorter (Sorting Algorithm)
    
    Responsibilities:
    1. Sort BackfillTask lists
    2. Implement complex sorting logic: date-layer mixed sorting
    3. Ensure correct dependencies
    
    Sorting Rules (Example):
    - All L2 from earliest date
    - Daily L3 from earliest date
    - All L2 from second earliest date
    - Daily L3 from second earliest date
    - L4 from earliest week containing these dates
    - And so on...
    
    Key Points:
    - Pure function, no side effects
    - Highly testable
    - Algorithm can be independently optimized
    """
    
    def sort_tasks(
        self,
        tasks: List[Any]
    ) -> List[Any]:
        """
        Sort backfill tasks
        
        Algorithm:
        1. Group by date
        2. Group by layer
        3. Interleave (same day L2→L3→next day L2→L3...)
        4. Insert week-level and month-level memories at appropriate positions
        
        Args:
            tasks: Unsorted task list
        
        Returns:
            Sorted task list
        """
        if not tasks:
            return []
        
        logger.info(f"Starting sort of {len(tasks)} tasks")
        
        # 1. Group by layer
        tasks_by_layer = self._group_by_layer(tasks)
        
        # 2. Sort each layer by time
        for layer in tasks_by_layer:
            tasks_by_layer[layer].sort(key=self._get_task_timestamp)
        
        # 3. Interleave by date and layer
        sorted_tasks = self._interleave_tasks(tasks_by_layer)
        
        logger.info(f"Sort completed: {len(sorted_tasks)} tasks")
        
        return sorted_tasks
    
    def _group_by_layer(
        self, 
        tasks: List[Any]
    ) -> Dict[str, List[Any]]:
        """
        Group tasks by layer
        
        Args:
            tasks: Task list
        
        Returns:
            Tasks grouped by layer dictionary
        """
        grouped = defaultdict(list)
        
        for task in tasks:
            layer = task.layer
            grouped[layer].append(task)
        
        return grouped
    
    def _get_task_timestamp(self, task: Any) -> datetime:
        """
        Get task timestamp (for sorting)
        
        Args:
            task: Task object
        
        Returns:
            Timestamp
        """
        if task.timestamp:
            return task.timestamp
        elif task.time_window and "start_time" in task.time_window:
            return task.time_window["start_time"]
        else:
            return datetime.min
    
    def _get_task_date(self, task: Any) -> date:
        """
        Get task date (for grouping)
        
        Args:
            task: Task object
        
        Returns:
            Date
        """
        timestamp = self._get_task_timestamp(task)
        return timestamp.date()
    
    def _interleave_tasks(
        self,
        tasks_by_layer: Dict[str, List[Any]]
    ) -> List[Any]:
        """
        Interleave tasks
        
        Algorithm:
        1. Extract all dates
        2. Iterate by date
        3. For each date, add L2→L3 in order
        4. Insert L4 at week end
        5. Insert L5 at month end
        
        Args:
            tasks_by_layer: Tasks grouped by layer
        
        Returns:
            Sorted task list
        """
        sorted_tasks = []
        
        # Extract all dates from L2 and L3 tasks (to drive loop)
        l2_tasks = tasks_by_layer.get("L2", [])
        l3_tasks_list = tasks_by_layer.get("L3", [])
        
        # Merge L2 and L3 dates (handle even if only L3 exists)
        dates_with_l2 = set(self._get_task_date(t) for t in l2_tasks)
        dates_with_l3 = set(self._get_task_date(t) for t in l3_tasks_list)
        all_dates = sorted(dates_with_l2 | dates_with_l3)
        
        # Build L2 and L3 index by date
        l2_by_date = self._index_tasks_by_date(l2_tasks)
        l3_by_date = self._index_tasks_by_date(l3_tasks_list)
        
        # L4 and L5 tasks
        l4_tasks = tasks_by_layer.get("L4", [])
        l5_tasks = tasks_by_layer.get("L5", [])
        
        # Track inserted L4 and L5
        inserted_l4_weeks = set()
        inserted_l5_months = set()
        
        # Iterate by date
        for i, current_date in enumerate(all_dates):
            next_date = all_dates[i + 1] if i + 1 < len(all_dates) else None
            
            # 1. Add all L2 from current day
            if current_date in l2_by_date:
                sorted_tasks.extend(l2_by_date[current_date])
            
            # 2. Add L3 from current day
            if current_date in l3_by_date:
                sorted_tasks.extend(l3_by_date[current_date])
            
            # 3. Check if should insert L4 (week end)
            if self._should_insert_l4(current_date, next_date):
                # Find L4 task for this week
                week_start = self._get_week_start(current_date)
                
                for l4_task in l4_tasks:
                    l4_week_start = self._get_week_start(self._get_task_date(l4_task))
                    if l4_week_start == week_start and l4_week_start not in inserted_l4_weeks:
                        sorted_tasks.append(l4_task)
                        inserted_l4_weeks.add(l4_week_start)
            
            # 4. Check if should insert L5 (month end)
            if self._should_insert_l5(current_date, next_date):
                # Find L5 task for this month
                month_start = self._get_month_start(current_date)
                
                for l5_task in l5_tasks:
                    l5_month_start = self._get_month_start(self._get_task_date(l5_task))
                    if l5_month_start == month_start and l5_month_start not in inserted_l5_months:
                        sorted_tasks.append(l5_task)
                        inserted_l5_months.add(l5_month_start)
        
        # Add remaining L4 and L5 tasks (if any)
        for l4_task in l4_tasks:
            l4_week_start = self._get_week_start(self._get_task_date(l4_task))
            if l4_week_start not in inserted_l4_weeks:
                sorted_tasks.append(l4_task)
        
        for l5_task in l5_tasks:
            l5_month_start = self._get_month_start(self._get_task_date(l5_task))
            if l5_month_start not in inserted_l5_months:
                sorted_tasks.append(l5_task)
        
        return sorted_tasks
    
    def _index_tasks_by_date(
        self,
        tasks: List[Any]
    ) -> Dict[date, List[Any]]:
        """
        Index tasks by date
        
        Args:
            tasks: Task list
        
        Returns:
            Tasks indexed by date dictionary
        """
        indexed = defaultdict(list)
        
        for task in tasks:
            task_date = self._get_task_date(task)
            indexed[task_date].append(task)
        
        return indexed
    
    def _should_insert_l4(
        self, 
        current_date: date, 
        next_date: Optional[date]
    ) -> bool:
        """
        Determine if should insert L4 (week end)
        
        Args:
            current_date: Current date
            next_date: Next date
        
        Returns:
            Whether should insert L4
        """
        if next_date is None:
            # Last date, insert L4
            return True
        
        # Check if current and next dates are in same week
        current_week = self._get_week_start(current_date)
        next_week = self._get_week_start(next_date)
        
        # If not in same week, week has ended
        return current_week != next_week
    
    def _should_insert_l5(
        self, 
        current_date: date, 
        next_date: Optional[date]
    ) -> bool:
        """
        Determine if should insert L5 (month end)
        
        Args:
            current_date: Current date
            next_date: Next date
        
        Returns:
            Whether should insert L5
        """
        if next_date is None:
            # Last date, insert L5
            return True
        
        # Check if current and next dates are in same month
        current_month = self._get_month_start(current_date)
        next_month = self._get_month_start(next_date)
        
        # If not in same month, month has ended
        return current_month != next_month
    
    def _get_week_start(self, target_date: date) -> date:
        """
        Get Monday of the week containing target date
        
        Args:
            target_date: Target date
        
        Returns:
            Monday date
        """
        # weekday() returns 0=Monday, 6=Sunday
        days_to_monday = target_date.weekday()
        week_start = target_date - timedelta(days=days_to_monday)
        return week_start
    
    def _get_month_start(self, target_date: date) -> date:
        """
        Get first day of month containing target date
        
        Args:
            target_date: Target date
        
        Returns:
            First day of month
        """
        return target_date.replace(day=1)
