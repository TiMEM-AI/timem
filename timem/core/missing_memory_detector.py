"""
TiMem Missing Memory Detector

Scans historical timeline, detects missing L2-L5 memories, generates backfill task list
"""

from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta, date
from dataclasses import dataclass
from collections import defaultdict

from timem.utils.logging import get_logger
from timem.utils.time_manager import get_time_manager
from timem.utils.time_utils import parse_time, ensure_iso_string
from timem.core.memory_existence_checker import (
    MemoryExistenceChecker,
    TimeWindow,
    MemoryCompleteness
)

logger = get_logger(__name__)


@dataclass
class BackfillTask:
    """Backfill task"""
    layer: str
    user_id: str
    expert_id: str
    time_window: TimeWindow
    reason: str  # Reason: 'missing' or 'incomplete'
    priority: int = 0  # Priority (smaller is higher priority)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "layer": self.layer,
            "user_id": self.user_id,
            "expert_id": self.expert_id,
            "time_window": self.time_window.to_dict(),
            "reason": self.reason,
            "priority": self.priority
        }


class MissingMemoryDetector:
    """
    Missing Memory Detector
    
    Core functions:
    1. Scan historical timeline of user-expert combinations
    2. Detect missing time windows for each layer
    3. Generate backfill task list (in chronological order)
    4. Support specifying date range or auto-detect full range
    
    Detection logic:
    - L2: Based on sessions, detect sessions without L2 memories
    - L3: Based on natural days, detect dates with L1 but no L3
    - L4: Based on natural weeks, detect weeks with L3 but no L4
    - L5: Based on natural months, detect months with L4 but no L5
    """
    
    def __init__(
        self,
        storage_manager=None,
        existence_checker: Optional[MemoryExistenceChecker] = None
    ):
        """
        Initialize missing memory detector
        
        Args:
            storage_manager: Storage manager
            existence_checker: Memory existence checker
        """
        self._storage_manager = storage_manager
        self.existence_checker = existence_checker
        self.time_manager = get_time_manager()
        
        logger.info("MissingMemoryDetector initialization completed")
    
    async def _ensure_dependencies(self):
        """Ensure dependencies are initialized"""
        if not self._storage_manager:
            from storage.memory_storage_manager import get_memory_storage_manager_async
            self._storage_manager = await get_memory_storage_manager_async()
        
        if not self.existence_checker:
            from timem.core.memory_existence_checker import get_memory_existence_checker
            self.existence_checker = await get_memory_existence_checker(self._storage_manager)
    
    async def detect_missing_l2(
        self,
        user_id: str,
        expert_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[BackfillTask]:
        """
        Detect missing L2 session memories
        
        Logic:
        1. Query all sessions
        2. For each session, check if L2 memory exists
        3. If not, add to missing list
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            start_date: Start date (optional)
            end_date: End date (optional)
            
        Returns:
            List of L2 backfill tasks
        """
        await self._ensure_dependencies()
        
        logger.info(f"Start detecting L2 missing: user={user_id}, expert={expert_id}")
        
        # Query all sessions
        sessions = await self._get_all_sessions(user_id, expert_id, start_date, end_date)
        
        tasks = []
        
        for session in sessions:
            session_id = session["id"]
            session_start = session["start_time"]
            session_end = session.get("end_time") or session_start + timedelta(hours=1)
            
            # Create time window
            time_window = TimeWindow(
                start_time=session_start,
                end_time=session_end,
                layer="L2",
                session_id=session_id
            )
            
            # Check if L2 memory already exists
            exists_result = await self.existence_checker.check_memory_exists(
                user_id, expert_id, "L2", time_window
            )
            
            if not exists_result.exists:
                # Missing, add task
                task = BackfillTask(
                    layer="L2",
                    user_id=user_id,
                    expert_id=expert_id,
                    time_window=time_window,
                    reason="missing",
                    priority=self._calculate_priority(session_start)
                )
                tasks.append(task)
                
            elif exists_result.partial:
                # Incomplete, add update task
                task = BackfillTask(
                    layer="L2",
                    user_id=user_id,
                    expert_id=expert_id,
                    time_window=time_window,
                    reason="incomplete",
                    priority=self._calculate_priority(session_start)
                )
                tasks.append(task)
        
        # Sort by time
        tasks.sort(key=lambda t: t.time_window.start_time)
        
        logger.info(f"L2 missing detection completed: missing={len([t for t in tasks if t.reason == 'missing'])}, "
                   f"incomplete={len([t for t in tasks if t.reason == 'incomplete'])}")
        
        return tasks
    
    async def detect_missing_l3(
        self,
        user_id: str,
        expert_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[BackfillTask]:
        """
        Detect missing L3 daily report memories
        
        ✅ Bottom-up logic (fixed version):
        1. Query all sessions (get real time from session table)
        2. Check which sessions have L2 memories
        3. Group sessions with L2 by date
        4. For each date with L2, check if L3 exists
        5. If no L3, mark as missing
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            start_date: Start date (optional)
            end_date: End date (optional)
            
        Returns:
            List of L3 backfill tasks
        """
        await self._ensure_dependencies()
        
        logger.info(f"Start detecting L3 missing: user={user_id}, expert={expert_id}")
        
        # 1. Query all sessions (get real session times)
        sessions = await self._get_all_sessions(user_id, expert_id, start_date, end_date)
        
        if not sessions:
            logger.info("No sessions, no need to detect L3")
            return []
        
        logger.info(f"Found {len(sessions)} sessions")
        
        # 2. Check which sessions have L2 memories and group by date
        sessions_by_date = defaultdict(list)
        sessions_with_l2_by_date = defaultdict(list)
        
        for session in sessions:
            session_id = session["id"]
            session_start = session["start_time"]
            
            # Ensure time format consistency
            if isinstance(session_start, str):
                from timem.utils.time_utils import parse_time
                session_start = parse_time(session_start)
            
            # Remove timezone
            session_start = session_start.replace(tzinfo=None) if session_start.tzinfo else session_start
            date_key = session_start.date()
            
            # Record that this date has sessions
            sessions_by_date[date_key].append(session)
            
            # Check if this session has L2 memory
            session_end = session.get("end_time") or session_start + timedelta(hours=1)
            if isinstance(session_end, str):
                from timem.utils.time_utils import parse_time
                session_end = parse_time(session_end)
            session_end = session_end.replace(tzinfo=None) if session_end.tzinfo else session_end
            
            time_window = TimeWindow(
                start_time=session_start,
                end_time=session_end,
                layer="L2",
                session_id=session_id
            )
            
            l2_exists = await self.existence_checker.check_memory_exists(
                user_id, expert_id, "L2", time_window
            )
            
            if l2_exists.exists:
                sessions_with_l2_by_date[date_key].append(session)
        
        logger.info(f"Sessions span {len(sessions_by_date)} days")
        logger.info(f"Of which {len(sessions_with_l2_by_date)} days have L2 memories")
        
        # 3. For each date with L2, check if L3 exists
        tasks = []
        
        for date_key in sorted(sessions_with_l2_by_date.keys()):
            # Create time window for the day
            day_start = self.time_manager.get_day_start(datetime.combine(date_key, datetime.min.time()))
            day_end = self.time_manager.get_day_end(datetime.combine(date_key, datetime.min.time()))
            
            time_window = TimeWindow(
                start_time=day_start,
                end_time=day_end,
                layer="L3"
            )
            
            # Check if L3 memory already exists
            exists_result = await self.existence_checker.check_memory_exists(
                user_id, expert_id, "L3", time_window
            )
            
            if not exists_result.exists:
                # Missing L3
                task = BackfillTask(
                    layer="L3",
                    user_id=user_id,
                    expert_id=expert_id,
                    time_window=time_window,
                    reason="missing",
                    priority=self._calculate_priority(day_start)
                )
                tasks.append(task)
                logger.debug(f"Found L3 missing: {date_key} (has {len(sessions_with_l2_by_date[date_key])} sessions with L2)")
                
            elif exists_result.partial:
                # L3 incomplete
                task = BackfillTask(
                    layer="L3",
                    user_id=user_id,
                    expert_id=expert_id,
                    time_window=time_window,
                    reason="incomplete",
                    priority=self._calculate_priority(day_start)
                )
                tasks.append(task)
                logger.debug(f"Found L3 incomplete: {date_key}")
        
        logger.info(f"L3 missing detection completed: missing={len([t for t in tasks if t.reason == 'missing'])}, "
                   f"incomplete={len([t for t in tasks if t.reason == 'incomplete'])}")
        
        return tasks
    
    async def detect_missing_l4(
        self,
        user_id: str,
        expert_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[BackfillTask]:
        """
        Detect missing L4 weekly report memories
        
        ✅ Bottom-up logic:
        1. Query all L3 memories
        2. Group L3 memories by week
        3. For each week with L3, check if L4 exists
        4. If no L4, mark as missing
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            start_date: Start date (optional)
            end_date: End date (optional)
            
        Returns:
            List of L4 backfill tasks
        """
        await self._ensure_dependencies()
        
        logger.info(f"Start detecting L4 missing: user={user_id}, expert={expert_id}")
        
        # 1. Query all L3 memories
        l3_memories = await self._storage_manager.search_memories(
            query={
                "user_id": user_id,
                "expert_id": expert_id,
                "level": "L3"
            },
            options={
                "limit": 10000
            }
        )
        
        if not l3_memories:
            logger.info("No L3 memories, no need to detect L4")
            return []
        
        logger.info(f"Found {len(l3_memories)} L3 memories")
        
        # 2. Group L3 memories by week (use time_window_start for accurate time)
        l3_by_week = defaultdict(list)
        for mem in l3_memories:
            # Prefer time_window_start (actual start time of time window)
            mem_time = None
            if hasattr(mem, 'time_window_start') and mem.time_window_start:
                mem_time = mem.time_window_start
            elif isinstance(mem, dict) and mem.get('time_window_start'):
                mem_time = mem.get('time_window_start')
            elif hasattr(mem, 'timestamp') and mem.timestamp:
                mem_time = mem.timestamp
            elif hasattr(mem, 'created_at') and mem.created_at:
                mem_time = mem.created_at
            elif isinstance(mem, dict):
                mem_time = mem.get('timestamp') or mem.get('created_at')
            
            if mem_time:
                if isinstance(mem_time, str):
                    from timem.utils.time_utils import parse_time
                    mem_time = parse_time(mem_time)
                
                # Remove timezone
                mem_time = mem_time.replace(tzinfo=None) if mem_time.tzinfo else mem_time
                
                # Apply date range filter
                if start_date and mem_time < start_date:
                    continue
                if end_date and mem_time > end_date:
                    continue
                
                # Get the week this date belongs to
                week_start = self.time_manager.get_week_start(mem_time)
                l3_by_week[week_start].append(mem)
        
        logger.info(f"L3 memories span {len(l3_by_week)} weeks")
        
        # 3. For each week with L3, check if L4 exists
        tasks = []
        
        for week_start in sorted(l3_by_week.keys()):
            week_end = self.time_manager.get_week_end(week_start)
            
            time_window = TimeWindow(
                start_time=week_start,
                end_time=week_end,
                layer="L4"
            )
            
            # Check if L4 memory already exists
            exists_result = await self.existence_checker.check_memory_exists(
                user_id, expert_id, "L4", time_window
            )
            
            if not exists_result.exists:
                task = BackfillTask(
                    layer="L4",
                    user_id=user_id,
                    expert_id=expert_id,
                    time_window=time_window,
                    reason="missing",
                    priority=self._calculate_priority(week_start)
                )
                tasks.append(task)
                logger.debug(f"Found L4 missing: {week_start.date()} (has {len(l3_by_week[week_start])} L3)")
                
            elif exists_result.partial:
                task = BackfillTask(
                    layer="L4",
                    user_id=user_id,
                    expert_id=expert_id,
                    time_window=time_window,
                    reason="incomplete",
                    priority=self._calculate_priority(week_start)
                )
                tasks.append(task)
                logger.debug(f"Found L4 incomplete: {week_start.date()}")
        
        logger.info(f"L4 missing detection completed: missing={len([t for t in tasks if t.reason == 'missing'])}, "
                   f"incomplete={len([t for t in tasks if t.reason == 'incomplete'])}")
        
        return tasks
    
    async def detect_missing_l5(
        self,
        user_id: str,
        expert_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[BackfillTask]:
        """
        Detect missing L5 monthly report memories
        
        ✅ Bottom-up logic:
        1. Query all L4 memories
        2. Group L4 memories by month
        3. For each month with L4, check if L5 exists
        4. If no L5, mark as missing
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            start_date: Start date (optional)
            end_date: End date (optional)
            
        Returns:
            List of L5 backfill tasks
        """
        await self._ensure_dependencies()
        
        logger.info(f"Start detecting L5 missing: user={user_id}, expert={expert_id}")
        
        # 1. Query all L4 memories
        l4_memories = await self._storage_manager.search_memories(
            query={
                "user_id": user_id,
                "expert_id": expert_id,
                "level": "L4"
            },
            options={
                "limit": 10000
            }
        )
        
        if not l4_memories:
            logger.info("No L4 memories, no need to detect L5")
            return []
        
        logger.info(f"Found {len(l4_memories)} L4 memories")
        
        # 2. Group L4 memories by month (use time_window_start for accurate time)
        l4_by_month = defaultdict(list)
        for mem in l4_memories:
            # Prefer time_window_start (actual start time of time window)
            mem_time = None
            if hasattr(mem, 'time_window_start') and mem.time_window_start:
                mem_time = mem.time_window_start
            elif isinstance(mem, dict) and mem.get('time_window_start'):
                mem_time = mem.get('time_window_start')
            elif hasattr(mem, 'timestamp') and mem.timestamp:
                mem_time = mem.timestamp
            elif hasattr(mem, 'created_at') and mem.created_at:
                mem_time = mem.created_at
            elif isinstance(mem, dict):
                mem_time = mem.get('timestamp') or mem.get('created_at')
            
            if mem_time:
                if isinstance(mem_time, str):
                    from timem.utils.time_utils import parse_time
                    mem_time = parse_time(mem_time)
                
                # Remove timezone
                mem_time = mem_time.replace(tzinfo=None) if mem_time.tzinfo else mem_time
                
                # Apply date range filter
                if start_date and mem_time < start_date:
                    continue
                if end_date and mem_time > end_date:
                    continue
                
                # Get the month this date belongs to
                month_start = self.time_manager.get_month_start(mem_time)
                l4_by_month[month_start].append(mem)
        
        logger.info(f"L4 memories span {len(l4_by_month)} months")
        
        # 3. For each month with L4, check if L5 exists
        tasks = []
        
        for month_start in sorted(l4_by_month.keys()):
            month_end = self.time_manager.get_month_end(month_start)
            
            time_window = TimeWindow(
                start_time=month_start,
                end_time=month_end,
                layer="L5"
            )
            
            # Check if L5 memory already exists
            exists_result = await self.existence_checker.check_memory_exists(
                user_id, expert_id, "L5", time_window
            )
            
            if not exists_result.exists:
                task = BackfillTask(
                    layer="L5",
                    user_id=user_id,
                    expert_id=expert_id,
                    time_window=time_window,
                    reason="missing",
                    priority=self._calculate_priority(month_start)
                )
                tasks.append(task)
                logger.debug(f"Found L5 missing: {month_start.date()} (has {len(l4_by_month[month_start])} L4)")
                
            elif exists_result.partial:
                task = BackfillTask(
                    layer="L5",
                    user_id=user_id,
                    expert_id=expert_id,
                    time_window=time_window,
                    reason="incomplete",
                    priority=self._calculate_priority(month_start)
                )
                tasks.append(task)
                logger.debug(f"Found L5 incomplete: {month_start.date()}")
        
        logger.info(f"L5 missing detection completed: missing={len([t for t in tasks if t.reason == 'missing'])}, "
                   f"incomplete={len([t for t in tasks if t.reason == 'incomplete'])}")
        
        return tasks
    
    async def detect_all_missing(
        self,
        user_id: str,
        expert_id: str,
        layers: List[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, List[BackfillTask]]:
        """
        Detect missing memories for all layers
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            layers: List of layers to detect, default ["L2", "L3", "L4", "L5"]
            start_date: Start date (optional)
            end_date: End date (optional)
            
        Returns:
            Dictionary of tasks grouped by layer
        """
        if layers is None:
            layers = ["L2", "L3", "L4", "L5"]
        
        logger.info(f"Start comprehensive detection of missing memories: user={user_id}, expert={expert_id}, layers={layers}")
        
        tasks_by_layer = {}
        
        if "L2" in layers:
            tasks_by_layer["L2"] = await self.detect_missing_l2(user_id, expert_id, start_date, end_date)
        
        if "L3" in layers:
            tasks_by_layer["L3"] = await self.detect_missing_l3(user_id, expert_id, start_date, end_date)
        
        if "L4" in layers:
            tasks_by_layer["L4"] = await self.detect_missing_l4(user_id, expert_id, start_date, end_date)
        
        if "L5" in layers:
            tasks_by_layer["L5"] = await self.detect_missing_l5(user_id, expert_id, start_date, end_date)
        
        # Count total tasks
        total_tasks = sum(len(tasks) for tasks in tasks_by_layer.values())
        
        logger.info(f"Comprehensive detection completed: total tasks={total_tasks}")
        for layer, tasks in tasks_by_layer.items():
            logger.info(f"  {layer}: {len(tasks)} tasks")
        
        return tasks_by_layer
    
    async def detect_all_missing_cascaded(
        self,
        user_id: str,
        expert_id: str,
        layers: List[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        include_incomplete: bool = False
    ) -> Dict[str, List[BackfillTask]]:
        """
        Cascading detection of missing memories for all layers
        
        Difference from detect_all_missing:
        - When detecting higher layers, "pending" lower layers are also considered as existing
        - For example: when detecting L4, both "existing L3" + "pending L3" are considered as existing
        - This generates a complete backfill plan including all needed higher-level memories
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            layers: List of layers to detect, default ["L2", "L3", "L4", "L5"]
            start_date: Start date (optional)
            end_date: End date (optional)
            include_incomplete: Whether to include current incomplete windows (today/this week/this month)
            
        Returns:
            Dictionary of tasks grouped by layer
        """
        if layers is None:
            layers = ["L2", "L3", "L4", "L5"]
        
        logger.info(f"Start cascading detection of missing memories: user={user_id}, expert={expert_id}, layers={layers}")
        
        tasks_by_layer = {}
        
        # Step 1: Detect L2 missing
        if "L2" in layers:
            tasks_by_layer["L2"] = await self.detect_missing_l2(user_id, expert_id, start_date, end_date)
            logger.info(f"L2 detection completed: {len(tasks_by_layer['L2'])} missing tasks")
        
        # Step 2: Detect L3 missing (based on existing L2 + pending L2)
        if "L3" in layers:
            tasks_by_layer["L3"] = await self._detect_missing_l3_cascaded(
                user_id, expert_id, start_date, end_date,
                pending_l2_tasks=tasks_by_layer.get("L2", []),
                include_incomplete=include_incomplete
            )
            logger.info(f"L3 detection completed: {len(tasks_by_layer['L3'])} missing tasks")
        
        # Step 3: Detect L4 missing (based on existing L3 + pending L3)
        if "L4" in layers:
            tasks_by_layer["L4"] = await self._detect_missing_l4_cascaded(
                user_id, expert_id, start_date, end_date,
                pending_l3_tasks=tasks_by_layer.get("L3", []),
                include_incomplete=include_incomplete
            )
            logger.info(f"L4 detection completed: {len(tasks_by_layer['L4'])} missing tasks")
        
        # Step 4: Detect L5 missing (based on existing L4 + pending L4)
        if "L5" in layers:
            tasks_by_layer["L5"] = await self._detect_missing_l5_cascaded(
                user_id, expert_id, start_date, end_date,
                pending_l4_tasks=tasks_by_layer.get("L4", []),
                include_incomplete=include_incomplete
            )
            logger.info(f"L5 detection completed: {len(tasks_by_layer['L5'])} missing tasks")
        
        # Count total tasks
        total_tasks = sum(len(tasks) for tasks in tasks_by_layer.values())
        
        logger.info(f"Cascading detection completed: total tasks={total_tasks}")
        for layer, tasks in tasks_by_layer.items():
            logger.info(f"  {layer}: {len(tasks)} tasks")
        
        return tasks_by_layer
    
    def generate_ordered_backfill_plan(
        self,
        tasks_by_layer: Dict[str, List[BackfillTask]]
    ) -> List[BackfillTask]:
        """
        Generate ordered backfill plan
        
        Sorting rules:
        1. Time constraint: generate older first, then newer
        2. Layer constraint: generate lower layers first (L2), then higher layers (L3->L4->L5)
        3. Same day: L2 -> L3, same week: L3 -> L4, same month: L4 -> L5
        
        Example order:
        - Week 1 session 1 L2
        - Week 1 session 2 L2
        - Week 1 some day L3
        - Week 1 L4
        - Week 2 session 3 L2
        - Week 2 session 4 L2
        - Week 2 some day L3
        - Week 2 L4
        - Entire month L5
        
        Args:
            tasks_by_layer: Dictionary of tasks grouped by layer
            
        Returns:
            Ordered list of tasks
        """
        logger.info("Start generating ordered backfill plan...")
        
        all_tasks = []
        for layer in ["L2", "L3", "L4", "L5"]:
            if layer in tasks_by_layer:
                all_tasks.extend(tasks_by_layer[layer])
        
        # Custom sorting function
        def task_sort_key(task: BackfillTask):
            """
            Generate task sorting key
            
            Returns tuple: (primary_time, layer_priority, secondary_time)
            - primary_time: Task start time (earlier is higher priority)
            - layer_priority: L2=0, L3=1, L4=2, L5=3
            - secondary_time: Task end time (distinguish tasks at same layer/time)
            """
            layer_priority = {"L2": 0, "L3": 1, "L4": 2, "L5": 3}
            
            start_time = task.time_window.start_time
            end_time = task.time_window.end_time
            layer_p = layer_priority.get(task.layer, 99)
            
            # Ensure time is datetime object
            if isinstance(start_time, str):
                start_time = parse_time(start_time)
            if isinstance(end_time, str):
                end_time = parse_time(end_time)
            
            return (start_time, layer_p, end_time)
        
        # Sort
        sorted_tasks = sorted(all_tasks, key=task_sort_key)
        
        # Assign priority to tasks (smaller number = higher priority)
        for i, task in enumerate(sorted_tasks):
            task.priority = i
        
        logger.info(f"✓ Ordered backfill plan generated: total {len(sorted_tasks)} tasks")
        
        # Print plan summary
        if sorted_tasks:
            logger.info("\nBackfill plan summary (first 10 tasks):")
            for i, task in enumerate(sorted_tasks[:10]):
                start_time = task.time_window.start_time
                if isinstance(start_time, str):
                    start_time = parse_time(start_time)
                logger.info(
                    f"  {i+1}. {task.layer} - "
                    f"{start_time.strftime('%Y-%m-%d %H:%M')} - "
                    f"{task.reason}"
                )
            
            if len(sorted_tasks) > 10:
                logger.info(f"  ... {len(sorted_tasks) - 10} more tasks")
        
        return sorted_tasks
    
    # ========================================
    # Private methods
    # ========================================
    
    async def _get_all_sessions(
        self,
        user_id: str,
        expert_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Query all sessions"""
        try:
            # Get database session
            from storage.postgres_store import get_postgres_store
            postgres_store = await get_postgres_store()
            
            async with postgres_store.get_session() as db_session:
                from timem.utils.session_tracker_postgres import SessionTrackerPostgres
                tracker = SessionTrackerPostgres(db_session)
                
                sessions = await tracker.get_all_sessions(user_id, expert_id)
            
            # Filter date range
            if start_date or end_date:
                filtered = []
                for session in sessions:
                    session_time = session["start_time"]
                    # Ensure time format consistency
                    if isinstance(session_time, str):
                        from timem.utils.time_utils import parse_time
                        session_time = parse_time(session_time)
                    
                    if start_date and session_time < start_date:
                        continue
                    if end_date and session_time > end_date:
                        continue
                    filtered.append(session)
                return filtered
            
            return sessions
            
        except Exception as e:
            logger.error(f"Query sessions failed: {e}", exc_info=True)
            return []
    
    async def _get_l1_time_range(
        self,
        user_id: str,
        expert_id: str
    ) -> Optional[Dict[str, datetime]]:
        """Get time range of L1 memories"""
        return await self._get_memory_time_range(user_id, expert_id, "L1")
    
    async def _get_memory_time_range(
        self,
        user_id: str,
        expert_id: str,
        layer: str
    ) -> Optional[Dict[str, datetime]]:
        """Get time range of memories for specified layer"""
        try:
            logger.info(f"Query {layer} memory time range: user={user_id}, expert={expert_id}")
            
            # Use storage_manager to query directly
            await self._ensure_dependencies()
            
            # Query using storage_manager's search method
            # Note: database column name is level, not layer
            memories = await self._storage_manager.search_memories(
                query={
                    "user_id": user_id,
                    "expert_id": expert_id,
                    "level": layer
                },
                options={
                    "limit": 1000
                }
            )
            
            logger.info(f"Found {len(memories)} {layer} memories")
            
            if not memories:
                logger.info(f"No {layer} memories")
                return None
            
            # Extract timestamps
            dates = []
            for memory in memories:
                # Prefer timestamp, then created_at
                date = None
                if hasattr(memory, 'timestamp') and memory.timestamp:
                    date = memory.timestamp
                elif hasattr(memory, 'created_at') and memory.created_at:
                    date = memory.created_at
                elif isinstance(memory, dict):
                    date = memory.get('timestamp') or memory.get('created_at')
                
                if date:
                    if isinstance(date, str):
                        date = parse_time(date)
                    dates.append(date)
            
            if not dates:
                logger.warning(f"{layer} memories have no valid timestamps")
                return None
            
            min_date = min(dates)
            max_date = max(dates)
            
            logger.info(f"{layer} memory time range: {min_date} - {max_date}")
            
            return {
                "min_date": min_date,
                "max_date": max_date
            }
            
        except Exception as e:
            logger.error(f"Get memory time range failed: {e}", exc_info=True)
            return None
    
    async def _has_memories_in_window(
        self,
        user_id: str,
        expert_id: str,
        layer: str,
        start_time: datetime,
        end_time: datetime
    ) -> bool:
        """Check if memories exist in time window"""
        try:
            logger.debug(f"Check {layer} memories: window={start_time.date()} - {end_time.date()}")
            
            # Use storage_manager to query directly
            await self._ensure_dependencies()
            
            # Query all memories for this layer
            # Note: database column name is level, not layer
            memories = await self._storage_manager.search_memories(
                query={
                    "user_id": user_id,
                    "expert_id": expert_id,
                    "level": layer
                },
                options={
                    "limit": 1000
                }
            )
            
            if not memories:
                logger.debug(f"No {layer} memories")
                return False
            
            # Check if memories exist in time window
            for memory in memories:
                # Get memory timestamp
                mem_time = None
                if hasattr(memory, 'timestamp') and memory.timestamp:
                    mem_time = memory.timestamp
                elif hasattr(memory, 'created_at') and memory.created_at:
                    mem_time = memory.created_at
                elif isinstance(memory, dict):
                    mem_time = memory.get('timestamp') or memory.get('created_at')
                
                if mem_time:
                    if isinstance(mem_time, str):
                        mem_time = parse_time(mem_time)
                    
                    # Remove timezone info for comparison
                    mem_time = mem_time.replace(tzinfo=None) if mem_time.tzinfo else mem_time
                    start_time_clean = start_time.replace(tzinfo=None) if start_time.tzinfo else start_time
                    end_time_clean = end_time.replace(tzinfo=None) if end_time.tzinfo else end_time
                    
                    if start_time_clean <= mem_time <= end_time_clean:
                        logger.debug(f"Found {layer} memory in time window: {mem_time}")
                        return True
            
            logger.debug(f"No {layer} memories in time window")
            return False
            
        except Exception as e:
            logger.error(f"Check memory existence failed: {e}", exc_info=True)
            return False
    
    async def _detect_missing_l3_cascaded(
        self,
        user_id: str,
        expert_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        pending_l2_tasks: List[BackfillTask] = None,
        include_incomplete: bool = False
    ) -> List[BackfillTask]:
        """
        Cascading detection of L3 missing (treat pending L2 as existing)
        
        Detection logic:
        1. Query all sessions
        2. Identify sessions with L2 memories (including existing + pending)
        3. Group by date
        4. Check if each date has L3
        
        Args:
            pending_l2_tasks: List of pending L2 backfill tasks
        """
        # Build set of pending L2 sessions and dates
        pending_l2_sessions = set()
        pending_l2_dates = set()
        
        if pending_l2_tasks:
            for task in pending_l2_tasks:
                # Get session_id from time_window
                if hasattr(task.time_window, 'session_id') and task.time_window.session_id:
                    session_id = task.time_window.session_id
                    pending_l2_sessions.add(session_id)
                    
                    # Also record date
                    start_time = task.time_window.start_time
                    if isinstance(start_time, str):
                        start_time = parse_time(start_time)
                    pending_l2_dates.add(start_time.date())
        
        logger.info(f"Cascading L3 detection: considering {len(pending_l2_sessions)} pending L2 sessions, "
                   f"involving {len(pending_l2_dates)} dates")
        
        # Call original method to get base L3 missing
        base_l3_tasks = await self.detect_missing_l3(user_id, expert_id, start_date, end_date)
        
        # For dates with pending L2, check if need to add L3 tasks
        if pending_l2_dates:
            logger.info("Check if dates with pending L2 need L3 generation...")
            
            for date_obj in pending_l2_dates:
                dt_start = datetime.combine(date_obj, datetime.min.time())
                dt_end = datetime.combine(date_obj, datetime.max.time())
                
                # Check if this date is already in base_l3_tasks
                already_marked = False
                for task in base_l3_tasks:
                    task_date = task.time_window.start_time
                    if isinstance(task_date, str):
                        task_date = parse_time(task_date)
                    if task_date.date() == date_obj:
                        already_marked = True
                        break
                
                if not already_marked:
                    # Check if L3 already exists
                    has_l3 = await self.existence_checker.check_memory_exists(
                        user_id=user_id,
                        expert_id=expert_id,
                        layer="L3",
                        time_window=TimeWindow(
                            start_time=dt_start,
                            end_time=dt_end,
                            layer="L3"
                        )
                    )
                    
                    if not has_l3.exists:
                        logger.debug(f"Pending L2 date needs L3: {date_obj}")
                        base_l3_tasks.append(BackfillTask(
                            layer="L3",
                            user_id=user_id,
                            expert_id=expert_id,
                            time_window=TimeWindow(
                                start_time=dt_start,
                                end_time=dt_end,
                                layer="L3"
                            ),
                            reason="missing",
                            priority=self._calculate_priority(dt_start)
                        ))
        
        # Filter current incomplete dates
        today = datetime.now().date()
        filtered_tasks = []
        
        for task in base_l3_tasks:
            task_date = task.time_window.start_time
            if isinstance(task_date, str):
                task_date = parse_time(task_date)
            
            # If task is for today
            if task_date.date() == today:
                if not include_incomplete:
                    # Do not include incomplete windows, filter directly
                    logger.debug(f"Filter today's L3: {task_date.date()} (incomplete)")
                    continue
                else:
                    # Include incomplete windows, check if L3 already exists
                    existing_l3_result = await self.existence_checker.check_memory_exists(
                        user_id=user_id,
                        expert_id=expert_id,
                        layer="L3",
                        time_window=task.time_window
                    )
                    
                    if existing_l3_result.exists:
                        # L3 exists, query L3 creation time
                        existing_l3 = await self.storage_manager.search(
                            filters={
                                "user_id": user_id,
                                "expert_id": expert_id,
                                "level": "L3",
                                "status": "active"
                            },
                            vector_store=False,
                            sql_store=True
                        )
                        
                        # Find today's L3
                        today_l3 = None
                        for mem in existing_l3:
                            mem_time = mem.get('time_window_start')
                            if mem_time:
                                if isinstance(mem_time, str):
                                    mem_time = parse_time(mem_time)
                                if mem_time.date() == today:
                                    today_l3 = mem
                                    break
                        
                        if today_l3:
                            # Check if there are new dialogues (after L3 creation)
                            l3_created_at = today_l3.get('created_at')
                            if isinstance(l3_created_at, str):
                                l3_created_at = parse_time(l3_created_at)
                            
                            day_start = datetime.combine(today, datetime.min.time())
                            day_end = datetime.combine(today, datetime.max.time())
                            
                            has_new = await self._has_new_dialogues_since(
                                user_id, expert_id,
                                day_start, day_end,
                                l3_created_at
                            )
                            
                            if not has_new:
                                logger.debug(f"Filter today's L3: {task_date.date()} (no new dialogues)")
                                continue
                            else:
                                logger.debug(f"Keep today's L3: {task_date.date()} (has new dialogues)")
            
            # Not today or passed check, keep this task
            filtered_tasks.append(task)
        
        logger.info(f"Filtered L3 tasks: {len(filtered_tasks)} (original {len(base_l3_tasks)})")
        base_l3_tasks = filtered_tasks
        
        logger.info(f"Cascading L3 detection completed: total {len(base_l3_tasks)} L3 missing tasks")
        return base_l3_tasks
    
    async def _detect_missing_l4_cascaded(
        self,
        user_id: str,
        expert_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        pending_l3_tasks: List[BackfillTask] = None,
        include_incomplete: bool = False
    ) -> List[BackfillTask]:
        """
        Cascading detection of L4 missing (treat pending L3 as existing)
        
        Detection logic:
        1. Query all L3 memories (existing)
        2. Add pending L3 tasks
        3. Group by week
        4. Check if each week has L4
        
        Args:
            pending_l3_tasks: List of pending L3 backfill tasks
        """
        await self._ensure_dependencies()
        
        logger.info(f"Start cascading detection of L4 missing: user={user_id}, expert={expert_id}")
        
        # 1. Query all existing L3 memories
        l3_memories = await self._storage_manager.search_memories(
            query={
                "user_id": user_id,
                "expert_id": expert_id,
                "level": "L3"
            }
        )
        
        logger.info(f"Found {len(l3_memories)} existing L3 memories")
        
        # 2. Merge pending L3 tasks
        all_l3_dates = set()  # Store all dates with L3
        
        # Extract dates from existing L3
        for mem in l3_memories:
            mem_time = None
            if hasattr(mem, 'time_window_start') and mem.time_window_start:
                mem_time = mem.time_window_start
            elif hasattr(mem, 'timestamp') and mem.timestamp:
                mem_time = mem.timestamp
            elif isinstance(mem, dict):
                mem_time = mem.get('time_window_start') or mem.get('timestamp')
            
            if mem_time:
                if isinstance(mem_time, str):
                    mem_time = parse_time(mem_time)
                mem_time = mem_time.replace(tzinfo=None) if mem_time.tzinfo else mem_time
                
                # Apply date range filter
                if start_date and mem_time < start_date:
                    continue
                if end_date and mem_time > end_date:
                    continue
                
                all_l3_dates.add(mem_time.date())
        
        # Extract dates from pending L3 tasks
        if pending_l3_tasks:
            logger.info(f"Considering {len(pending_l3_tasks)} pending L3 tasks")
            for task in pending_l3_tasks:
                task_time = task.time_window.start_time
                if isinstance(task_time, str):
                    task_time = parse_time(task_time)
                task_time = task_time.replace(tzinfo=None) if task_time.tzinfo else task_time
                all_l3_dates.add(task_time.date())
        
        if not all_l3_dates:
            logger.info("No L3 memories (including pending), no need to detect L4")
            return []
        
        logger.info(f"Total {len(all_l3_dates)} days with L3 memories (including pending)")
        
        # 3. Group by week
        l3_by_week = defaultdict(list)
        for date_obj in all_l3_dates:
            dt = datetime.combine(date_obj, datetime.min.time())
            week_start = self.time_manager.get_week_start(dt)
            l3_by_week[week_start].append(date_obj)
        
        logger.info(f"L3 spans {len(l3_by_week)} weeks")
        
        # 4. Check if each week has L4
        tasks = []
        for week_start, dates in sorted(l3_by_week.items()):
            week_end = self.time_manager.get_week_end(week_start)
            
            # Apply date range filter
            if start_date and week_end < start_date:
                continue
            if end_date and week_start > end_date:
                continue
            
            # Check if week already has L4
            has_l4 = await self.existence_checker.check_memory_exists(
                user_id=user_id,
                expert_id=expert_id,
                layer="L4",
                time_window=TimeWindow(
                    start_time=week_start,
                    end_time=week_end,
                    layer="L4"
                )
            )
            
            if not has_l4.exists:
                logger.debug(f"Found L4 missing: {week_start.date()} (has {len(dates)} days with L3)")
                tasks.append(BackfillTask(
                    layer="L4",
                    user_id=user_id,
                    expert_id=expert_id,
                    time_window=TimeWindow(
                        start_time=week_start,
                        end_time=week_end,
                        layer="L4"
                    ),
                    reason="missing",
                    priority=self._calculate_priority(week_start)
                ))
        
        # Filter current incomplete weeks
        current_week_start = self.time_manager.get_week_start(datetime.now())
        filtered_tasks = []
        
        for task in tasks:
            task_week_start = task.time_window.start_time
            if isinstance(task_week_start, str):
                task_week_start = parse_time(task_week_start)
            
            # If task is for current week
            if task_week_start >= current_week_start:
                if not include_incomplete:
                    # Do not include incomplete windows, filter directly
                    logger.debug(f"Filter current week L4: {task_week_start.date()} (incomplete)")
                    continue
                else:
                    # Include incomplete windows, check if L4 already exists
                    existing_l4_result = await self.existence_checker.check_memory_exists(
                        user_id=user_id,
                        expert_id=expert_id,
                        layer="L4",
                        time_window=task.time_window
                    )
                    
                    if existing_l4_result.exists:
                        # L4 exists, query L4 creation time
                        week_end = self.time_manager.get_week_end(task_week_start)
                        existing_l4 = await self.storage_manager.search(
                            filters={
                                "user_id": user_id,
                                "expert_id": expert_id,
                                "level": "L4",
                                "status": "active"
                            },
                            vector_store=False,
                            sql_store=True
                        )
                        
                        # Find current week's L4
                        current_week_l4 = None
                        for mem in existing_l4:
                            mem_time = mem.get('time_window_start')
                            if mem_time:
                                if isinstance(mem_time, str):
                                    mem_time = parse_time(mem_time)
                                mem_week_start = self.time_manager.get_week_start(mem_time)
                                if mem_week_start >= current_week_start:
                                    current_week_l4 = mem
                                    break
                        
                        if current_week_l4:
                            # Check if there are new dialogues (after L4 creation)
                            l4_created_at = current_week_l4.get('created_at')
                            if isinstance(l4_created_at, str):
                                l4_created_at = parse_time(l4_created_at)
                            
                            has_new = await self._has_new_dialogues_since(
                                user_id, expert_id,
                                task_week_start, week_end,
                                l4_created_at
                            )
                            
                            if not has_new:
                                logger.debug(f"Filter current week L4: {task_week_start.date()} (no new dialogues)")
                                continue
                            else:
                                logger.debug(f"Keep current week L4: {task_week_start.date()} (has new dialogues)")
            
            # Not current week or passed check, keep this task
            filtered_tasks.append(task)
        
        logger.info(f"Filtered L4 tasks: {len(filtered_tasks)} (original {len(tasks)})")
        tasks = filtered_tasks
        
        logger.info(f"L4 missing detection completed: missing={len(tasks)}")
        return tasks
    
    async def _detect_missing_l5_cascaded(
        self,
        user_id: str,
        expert_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        pending_l4_tasks: List[BackfillTask] = None,
        include_incomplete: bool = False
    ) -> List[BackfillTask]:
        """
        Cascading detection of L5 missing (treat pending L4 as existing)
        
        Detection logic:
        1. Query all L4 memories (existing)
        2. Add pending L4 tasks
        3. Group by month
        4. Check if each month has L5
        
        Args:
            pending_l4_tasks: List of pending L4 backfill tasks
        """
        await self._ensure_dependencies()
        
        logger.info(f"Start cascading detection of L5 missing: user={user_id}, expert={expert_id}")
        
        # 1. Query all existing L4 memories
        l4_memories = await self._storage_manager.search_memories(
            query={
                "user_id": user_id,
                "expert_id": expert_id,
                "level": "L4"
            }
        )
        
        logger.info(f"Found {len(l4_memories)} existing L4 memories")
        
        # 2. Merge pending L4 tasks
        all_l4_weeks = set()  # Store all weeks with L4
        
        # Extract weeks from existing L4
        for mem in l4_memories:
            mem_time = None
            if hasattr(mem, 'time_window_start') and mem.time_window_start:
                mem_time = mem.time_window_start
            elif hasattr(mem, 'timestamp') and mem.timestamp:
                mem_time = mem.timestamp
            elif isinstance(mem, dict):
                mem_time = mem.get('time_window_start') or mem.get('timestamp')
            
            if mem_time:
                if isinstance(mem_time, str):
                    mem_time = parse_time(mem_time)
                mem_time = mem_time.replace(tzinfo=None) if mem_time.tzinfo else mem_time
                
                # Apply date range filter
                if start_date and mem_time < start_date:
                    continue
                if end_date and mem_time > end_date:
                    continue
                
                week_start = self.time_manager.get_week_start(mem_time)
                all_l4_weeks.add(week_start.date())
        
        # Extract weeks from pending L4 tasks
        if pending_l4_tasks:
            logger.info(f"Considering {len(pending_l4_tasks)} pending L4 tasks")
            for task in pending_l4_tasks:
                task_time = task.time_window.start_time
                if isinstance(task_time, str):
                    task_time = parse_time(task_time)
                task_time = task_time.replace(tzinfo=None) if task_time.tzinfo else task_time
                week_start = self.time_manager.get_week_start(task_time)
                all_l4_weeks.add(week_start.date())
        
        if not all_l4_weeks:
            logger.info("No L4 memories (including pending), no need to detect L5")
            return []
        
        logger.info(f"Total {len(all_l4_weeks)} weeks with L4 memories (including pending)")
        
        # 3. Group by month
        l4_by_month = defaultdict(list)
        for week_date in all_l4_weeks:
            dt = datetime.combine(week_date, datetime.min.time())
            month_start = self.time_manager.get_month_start(dt)
            l4_by_month[month_start].append(week_date)
        
        logger.info(f"L4 spans {len(l4_by_month)} months")
        
        # 4. Check if each month has L5
        tasks = []
        for month_start, weeks in sorted(l4_by_month.items()):
            month_end = self.time_manager.get_month_end(month_start)
            
            # Apply date range filter
            if start_date and month_end < start_date:
                continue
            if end_date and month_start > end_date:
                continue
            
            # Check if month already has L5
            has_l5 = await self.existence_checker.check_memory_exists(
                user_id=user_id,
                expert_id=expert_id,
                layer="L5",
                time_window=TimeWindow(
                    start_time=month_start,
                    end_time=month_end,
                    layer="L5"
                )
            )
            
            if not has_l5.exists:
                logger.debug(f"Found L5 missing: {month_start.strftime('%Y-%m')} (has {len(weeks)} weeks with L4)")
                tasks.append(BackfillTask(
                    layer="L5",
                    user_id=user_id,
                    expert_id=expert_id,
                    time_window=TimeWindow(
                        start_time=month_start,
                        end_time=month_end,
                        layer="L5"
                    ),
                    reason="missing",
                    priority=self._calculate_priority(month_start)
                ))
        
        # Filter current incomplete months
        current_month_start = self.time_manager.get_month_start(datetime.now())
        filtered_tasks = []
        
        for task in tasks:
            task_month_start = task.time_window.start_time
            if isinstance(task_month_start, str):
                task_month_start = parse_time(task_month_start)
            
            # If task is for current month
            if task_month_start >= current_month_start:
                if not include_incomplete:
                    # Do not include incomplete windows, filter directly
                    logger.debug(f"Filter current month L5: {task_month_start.strftime('%Y-%m')} (incomplete)")
                    continue
                else:
                    # Include incomplete windows, check if L5 already exists
                    existing_l5_result = await self.existence_checker.check_memory_exists(
                        user_id=user_id,
                        expert_id=expert_id,
                        layer="L5",
                        time_window=task.time_window
                    )
                    
                    if existing_l5_result.exists:
                        # L5 exists, query L5 creation time
                        month_end = self.time_manager.get_month_end(task_month_start)
                        existing_l5 = await self.storage_manager.search(
                            filters={
                                "user_id": user_id,
                                "expert_id": expert_id,
                                "level": "L5",
                                "status": "active"
                            },
                            vector_store=False,
                            sql_store=True
                        )
                        
                        # Find current month's L5
                        current_month_l5 = None
                        for mem in existing_l5:
                            mem_time = mem.get('time_window_start')
                            if mem_time:
                                if isinstance(mem_time, str):
                                    mem_time = parse_time(mem_time)
                                mem_month_start = self.time_manager.get_month_start(mem_time)
                                if mem_month_start >= current_month_start:
                                    current_month_l5 = mem
                                    break
                        
                        if current_month_l5:
                            # Check if there are new dialogues (after L5 creation)
                            l5_created_at = current_month_l5.get('created_at')
                            if isinstance(l5_created_at, str):
                                l5_created_at = parse_time(l5_created_at)
                            
                            has_new = await self._has_new_dialogues_since(
                                user_id, expert_id,
                                task_month_start, month_end,
                                l5_created_at
                            )
                            
                            if not has_new:
                                logger.debug(f"Filter current month L5: {task_month_start.strftime('%Y-%m')} (no new dialogues)")
                                continue
                            else:
                                logger.debug(f"Keep current month L5: {task_month_start.strftime('%Y-%m')} (has new dialogues)")
            
            # Not current month or passed check, keep this task
            filtered_tasks.append(task)
        
        logger.info(f"Filtered L5 tasks: {len(filtered_tasks)} (original {len(tasks)})")
        tasks = filtered_tasks
        
        logger.info(f"L5 missing detection completed: missing={len(tasks)}")
        return tasks
    
    async def _has_new_dialogues_since(
        self,
        user_id: str,
        expert_id: str,
        start_time: datetime,
        end_time: datetime,
        since_time: Optional[datetime] = None
    ) -> bool:
        """
        Check if there are new dialogues in time window (after since_time)
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            start_time: Time window start
            end_time: Time window end
            since_time: Reference time (check dialogues after this time), if None check any dialogues
            
        Returns:
            True if new dialogues exist, False otherwise
        """
        try:
            from sqlalchemy import text
            from storage.postgres_store import get_postgres_store
            
            postgres_store = await get_postgres_store()
            
            async with postgres_store.get_session() as db_session:
                # Query dialogue_turns table
                if since_time:
                    query = text("""
                        SELECT COUNT(*) as count
                        FROM dialogue_turns
                        WHERE user_id = :user_id
                          AND expert_id = :expert_id
                          AND timestamp >= :start_time
                          AND timestamp <= :end_time
                          AND timestamp > :since_time
                    """)
                    result = await db_session.execute(query, {
                        "user_id": user_id,
                        "expert_id": expert_id,
                        "start_time": start_time,
                        "end_time": end_time,
                        "since_time": since_time
                    })
                else:
                    query = text("""
                        SELECT COUNT(*) as count
                        FROM dialogue_turns
                        WHERE user_id = :user_id
                          AND expert_id = :expert_id
                          AND timestamp >= :start_time
                          AND timestamp <= :end_time
                    """)
                    result = await db_session.execute(query, {
                        "user_id": user_id,
                        "expert_id": expert_id,
                        "start_time": start_time,
                        "end_time": end_time
                    })
                
                row = result.fetchone()
                count = row[0] if row else 0
                
                logger.debug(
                    f"Dialogue check: {start_time.date()} - {end_time.date()}, "
                    f"since={since_time.isoformat() if since_time else 'None'}, "
                    f"count={count}"
                )
                
                return count > 0
        except Exception as e:
            logger.error(f"Check new dialogues failed: {e}", exc_info=True)
            # Conservative handling on error, return True to allow backfill
            return True
    
    def _calculate_priority(self, time: datetime) -> int:
        """
        Calculate task priority
        
        Older tasks have higher priority (smaller number)
        """
        # Use days since now as priority
        days_ago = (datetime.now() - time).days
        return -days_ago  # Negative number so older tasks have higher priority


# Global singleton
_missing_memory_detector_instance = None


async def get_missing_memory_detector(
    storage_manager=None
) -> MissingMemoryDetector:
    """
    Get missing memory detector singleton
    
    Args:
        storage_manager: Storage manager
        
    Returns:
        MissingMemoryDetector instance
    """
    global _missing_memory_detector_instance
    
    if _missing_memory_detector_instance is None:
        _missing_memory_detector_instance = MissingMemoryDetector(
            storage_manager=storage_manager
        )
    
    return _missing_memory_detector_instance

