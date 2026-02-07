"""
TiMem CatchUpDetector - Catch-up Detector (Refactored)

Responsible for detecting missing memories for automatic backfill triggering

Core logic:
1. Daily midnight backfill: detect missing memories from previous day
2. Force backfill: backfill current latest memories
3. Inter-session backfill: backfill L2 for specified session
"""

from typing import Dict, List, Set, Optional
from datetime import datetime, date, timedelta
from dataclasses import dataclass
from calendar import monthrange

from timem.utils.logging import get_logger
from storage.memory_storage_manager import MemoryStorageManager
from timem.core.memory_existence_checker import MemoryExistenceChecker

logger = get_logger(__name__)


@dataclass
class BackfillTask:
    """Backfill task"""
    user_id: str
    expert_id: str
    layer: str  # L2, L3, L4, L5
    session_id: Optional[str] = None  # Used for L2
    time_window: Optional[Dict] = None  # Used for L3/L4/L5
    timestamp: Optional[datetime] = None
    force_update: bool = False  # Whether to force update existing memory


class CatchUpDetector:
    """
    Catch-up Detector (Missing Detection) - Refactored
    
    Responsibilities:
    1. Daily midnight backfill: detect missing memories from previous day
    2. Force backfill: backfill current latest memories
    3. Inter-session backfill: backfill L2 for specified session
    
    Backfill logic:
    - L2: all sessions from previous day without L2
    - L3: daily report from previous day (if has L2)
    - L4: weekly report from last week (if cross-week and week has L3)
    - L5: monthly report from last month (if cross-month and month has L4)
    """
    
    def __init__(
        self,
        storage_manager: Optional[MemoryStorageManager] = None,
        existence_checker: Optional[MemoryExistenceChecker] = None
    ):
        """
        Initialize detector
        
        Args:
            storage_manager: Storage manager
            existence_checker: Existence checker
        """
        self.storage_manager = storage_manager
        self.existence_checker = existence_checker
        logger.info("CatchUpDetector initialization completed")
    
    async def _ensure_dependencies(self):
        """Ensure dependencies are initialized"""
        if not self.storage_manager:
            from storage.memory_storage_manager import get_memory_storage_manager_async
            self.storage_manager = await get_memory_storage_manager_async()
        
        if not self.existence_checker:
            self.existence_checker = MemoryExistenceChecker(self.storage_manager)
    
    async def detect_missing_for_yesterday(
        self,
        user_id: str,
        expert_id: str,
        yesterday: date
    ) -> List[BackfillTask]:
        """
        Detect missing memories from previous day (core logic for daily midnight backfill)
        
        Process:
        1. Query all sessions from previous day
        2. Check if L2 exists for each session
        3. Check if L3 exists for previous day
        4. Check if cross-week, if yes detect L4 from last week
        5. Check if cross-month, if yes detect L5 from last month
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            yesterday: Date of previous day
        
        Returns:
            List of backfill tasks
        """
        await self._ensure_dependencies()
        
        logger.info(f"[DAILY_BACKFILL] Detect missing memories from previous day: date={yesterday}, user={user_id}, expert={expert_id}")
        
        all_tasks = []
        
        # 1. Query all sessions from previous day
        yesterday_start = datetime.combine(yesterday, datetime.min.time())
        yesterday_end = datetime.combine(yesterday, datetime.max.time())
        
        sessions = await self._get_sessions_in_day(user_id, expert_id, yesterday)
        logger.info(f"[DAILY_BACKFILL] Sessions from previous day: {len(sessions)}")
        
        # 2. Detect L2 (all sessions from previous day)
        for session in sessions:
            session_id = session.get("session_id") or session.get("id")
            
            # Check if L2 exists
            l2_exists = await self.existence_checker.check_l2_exists(
                user_id, expert_id, session_id
            )
            
            if not l2_exists:
                # Fix: Set L2 memory time to 23:59:59 of session day
                # Get session start time and extract date
                session_start = session.get("start_time") or yesterday_start
                if isinstance(session_start, str):
                    from timem.utils.time_utils import parse_time
                    session_start = parse_time(session_start)
                
                # L2 time = 23:59:59 of session day
                from datetime import time as dt_time
                session_date = session_start.date()
                l2_timestamp = datetime.combine(session_date, dt_time(23, 59, 59))
                
                logger.info(f"[DAILY_BACKFILL] Set L2 time to end of session day: {session_start.date()} 23:59:59 = {l2_timestamp}")
                
                all_tasks.append(BackfillTask(
                    user_id=user_id,
                    expert_id=expert_id,
                    layer="L2",
                    session_id=session_id,
                    timestamp=l2_timestamp
                ))
                logger.info(f"[DAILY_BACKFILL] Add L2 task: session={session_id}, timestamp={l2_timestamp}")
        
        # 3. Detect L3 (daily report from previous day)
        # Fix: If previous day has sessions, L3 should be generated, no need to check if L2 exists
        # Reason: L2 task may be pending in same batch, should not skip L3 because L2 not yet stored
        if len(sessions) > 0:
            # Check if L3 already exists
            query = {
                "user_id": user_id,
                "expert_id": expert_id,
                "layer": "L3",
                "time_window_start": yesterday_start,
                "time_window_end": yesterday_end
            }
            l3_memories = await self.storage_manager.search_memories(query, {})
            l3_exists = len(l3_memories) > 0
            
            if not l3_exists:
                all_tasks.append(BackfillTask(
                    user_id=user_id,
                    expert_id=expert_id,
                    layer="L3",
                    time_window={
                        "start_time": yesterday_start,
                        "end_time": yesterday_end
                    },
                    timestamp=yesterday_end
                ))
                logger.info(f"[DAILY_BACKFILL] Add L3 task: date={yesterday}, previous day has {len(sessions)} sessions")
            else:
                logger.info(f"[DAILY_BACKFILL] L3 already exists, skip")
        
        # 4. Check if cross-week, detect L4 from last week
        today = yesterday + timedelta(days=1)
        yesterday_week_start = yesterday - timedelta(days=yesterday.weekday())
        today_week_start = today - timedelta(days=today.weekday())
        
        if yesterday_week_start != today_week_start:
            # Cross-week detected, detect L4 from last week
            logger.info(f"[DAILY_BACKFILL] Cross-week detected: last week={yesterday_week_start}")
            
            last_week_start = yesterday_week_start
            last_week_end_date = last_week_start + timedelta(days=6)
            
            # Handle boundary case: if Sunday exceeds month end of yesterday's month, L4 time window is Monday to month end
            last_month_last_day = monthrange(yesterday.year, yesterday.month)[1]
            month_end_date = yesterday.replace(day=last_month_last_day)
            
            if last_week_end_date > month_end_date:
                # Incomplete week: Monday to month end
                last_week_end = datetime.combine(month_end_date, datetime.max.time())
                limit_end_date = month_end_date
                logger.info(f"[DAILY_BACKFILL] Incomplete week detected (cross-month): {last_week_start} to {month_end_date}")
            else:
                # Complete week: Monday to Sunday
                last_week_end = datetime.combine(last_week_end_date, datetime.max.time())
                limit_end_date = None
            
            # Fix: Check if week has sessions (not check L3)
            # Reason: L3 task may be pending in same batch, should check original data source (sessions)
            has_sessions_in_week = await self._check_has_sessions_in_week(
                user_id, expert_id, last_week_start
            )
            
            if has_sessions_in_week:
                # Check if L4 exists
                query = {
                    "user_id": user_id,
                    "expert_id": expert_id,
                    "layer": "L4",
                    "time_window_start": datetime.combine(last_week_start, datetime.min.time()),
                    "time_window_end": last_week_end
                }
                l4_memories = await self.storage_manager.search_memories(query, {})
                l4_exists = len(l4_memories) > 0
                
                if not l4_exists:
                    all_tasks.append(BackfillTask(
                        user_id=user_id,
                        expert_id=expert_id,
                        layer="L4",
                        time_window={
                            "start_time": datetime.combine(last_week_start, datetime.min.time()),
                            "end_time": last_week_end
                        },
                        timestamp=last_week_end
                    ))
                    logger.info(f"[DAILY_BACKFILL] Add L4 task: week={last_week_start}, week has sessions")
                else:
                    logger.info(f"[DAILY_BACKFILL] L4 already exists, skip")
            else:
                logger.warning(f"[DAILY_BACKFILL] Last week has no sessions, skip L4 generation")
        
        # 5. Check if cross-month, detect L5 from last month
        if yesterday.month != today.month:
            # Cross-month detected, detect L5 from last month
            logger.info(f"[DAILY_BACKFILL] Cross-month detected: last month={yesterday.year}-{yesterday.month}")
            
            last_month_start = yesterday.replace(day=1)
            last_month_last_day = monthrange(yesterday.year, yesterday.month)[1]
            last_month_end_date = yesterday.replace(day=last_month_last_day)
            last_month_end = datetime.combine(last_month_end_date, datetime.max.time())
            
            # Boundary fix: cross-month but not cross-week, force generate incomplete weekly report at month end
            # Scenario: Jan 31 (Wed) has sessions, Feb 1 cross-month but still in same week
            # No cross-week trigger, but need to generate incomplete weekly report at month end for Jan L5 to see
            if yesterday_week_start == today_week_start:
                # Cross-month but not cross-week: force generate incomplete weekly report at month end
                logger.info(f"[DAILY_BACKFILL] Cross-month but not cross-week, check incomplete weekly report at month end")
                
                # Time range of week at month end: week_start to last_month_end
                month_end_week_start = yesterday - timedelta(days=yesterday.weekday())
                
                # Fix: Check if week has sessions (not check L3)
                has_sessions_in_incomplete_week = await self._check_has_sessions_in_week(
                    user_id, expert_id, month_end_week_start, limit_end_date=last_month_end_date
                )
                
                if has_sessions_in_incomplete_week:
                    # Check if L4 exists
                    l4_check_query = {
                        "user_id": user_id,
                        "expert_id": expert_id,
                        "layer": "L4",
                        "time_window_start": datetime.combine(month_end_week_start, datetime.min.time()),
                        "time_window_end": last_month_end
                    }
                    l4_check_memories = await self.storage_manager.search_memories(l4_check_query, {})
                    
                    if len(l4_check_memories) == 0:
                        # Force generate incomplete weekly report at month end (up to month end)
                        all_tasks.append(BackfillTask(
                            user_id=user_id,
                            expert_id=expert_id,
                            layer="L4",
                            time_window={
                                "start_time": datetime.combine(month_end_week_start, datetime.min.time()),
                                "end_time": last_month_end
                            },
                            timestamp=last_month_end
                        ))
                        logger.info(f"[DAILY_BACKFILL] Add L4 task (cross-month not cross-week): week={month_end_week_start} to {last_month_end_date}, week has sessions")
                    else:
                        logger.info(f"[DAILY_BACKFILL] Incomplete weekly report at month end already exists")
                else:
                    logger.warning(f"[DAILY_BACKFILL] Week at month end has no sessions, skip incomplete weekly report generation")
            
            # Fix: Check if month has sessions (not check L4)
            # Reason: L4 task may be pending in same batch, should check original data source (sessions)
            has_sessions_in_month = await self._check_has_sessions_in_month(
                user_id, expert_id, last_month_start
            )
            
            if has_sessions_in_month:
                # Check if L5 exists
                query = {
                    "user_id": user_id,
                    "expert_id": expert_id,
                    "layer": "L5",
                    "time_window_start": datetime.combine(last_month_start, datetime.min.time()),
                    "time_window_end": last_month_end
                }
                l5_memories = await self.storage_manager.search_memories(query, {})
                l5_exists = len(l5_memories) > 0
                
                if not l5_exists:
                    all_tasks.append(BackfillTask(
                        user_id=user_id,
                        expert_id=expert_id,
                        layer="L5",
                        time_window={
                            "start_time": datetime.combine(last_month_start, datetime.min.time()),
                            "end_time": last_month_end
                        },
                        timestamp=last_month_end
                    ))
                    logger.info(f"[DAILY_BACKFILL] Add L5 task: month={last_month_start}, month has sessions")
                else:
                    logger.info(f"[DAILY_BACKFILL] L5 already exists, skip")
            else:
                logger.warning(f"[DAILY_BACKFILL] Last month has no sessions, skip L5 generation")
        
        logger.info(f"[DAILY_BACKFILL] Detection completed: total {len(all_tasks)} missing memories")
        return all_tasks
    
    async def detect_missing_in_recent_months(
        self,
        user_id: str,
        expert_id: str,
        month_count: int = 2,
        force: bool = False,
        force_timestamp: Optional[datetime] = None
    ) -> List[BackfillTask]:
        """
        Detect missing memories in recent N months
        
        Two modes:
        - force=False (regular mode): detect yesterday's L2/L3 and completed L4/L5
        - force=True (force mode): detect L4/L5 in incomplete week/month of latest session
        
        Recommended usage:
        1. Call force=False for regular detection
        2. Call force=True to backfill incomplete windows
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            month_count: Detect recent N months (default 2)
            force: Whether to use force backfill mode
            force_timestamp: Timestamp for force backfill
        
        Returns:
            List[BackfillTask]
        """
        await self._ensure_dependencies()
        
        timestamp = force_timestamp or datetime.now()
        
        if force:
            # Force mode: only backfill L4/L5 in incomplete window of latest session
            logger.info(f"[BACKFILL] Force mode: user={user_id}, expert={expert_id}")
            return await self._detect_force_incomplete_windows(user_id, expert_id, timestamp)
        else:
            # Regular mode: detect all missing from yesterday
            yesterday = (timestamp.date() if isinstance(timestamp, datetime) else timestamp) - timedelta(days=1)
            logger.info(f"[BACKFILL] Regular mode: user={user_id}, expert={expert_id}, yesterday={yesterday}")
            return await self.detect_missing_for_yesterday(user_id, expert_id, yesterday)
    
    async def detect_manual_completion(
        self,
        user_id: str,
        expert_id: str,
        force_update: bool = True,
        manual_timestamp: Optional[datetime] = None
    ) -> List[BackfillTask]:
        """
        Manual backfill API (corresponds to frontend "Backfill Now" button)
        
        Two modes:
        1. **Force update mode** (force_update=True):
           - Include current incomplete windows: today's L3, this week's L4, this month's L5
           - Include latest session's L2 (even if exists)
           - Suitable for user wanting to update latest memories
           
        2. **Regular detection mode** (force_update=False):
           - Only detect missing in completed windows: yesterday's L3, last week's L4, last month's L5
           - Only detect non-existent L2 session memories
           - Suitable for user wanting to backfill historical missing
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            force_update: Whether to use force update mode (include current incomplete windows)
            manual_timestamp: Timestamp for manual backfill (used as generation time)
        
        Returns:
            List of backfill tasks
        """
        await self._ensure_dependencies()
        
        tasks = []
        timestamp = manual_timestamp or datetime.now()
        
        logger.info(f"[MANUAL] Start manual backfill: user={user_id}, expert={expert_id}, force_update={force_update}, timestamp={timestamp}")
        
        try:
            if force_update:
                # Force update mode: include historical missing + force update current incomplete windows
                logger.info("[FORCE] Force update mode: detect historical missing + force update current incomplete windows")
                
                # 1. First detect missing in historical content (completed time windows)
                await self._detect_regular_missing_tasks(user_id, expert_id, timestamp, tasks)
                historical_tasks_count = len(tasks)
                logger.info(f"[FORCE] Historical missing detection completed: {historical_tasks_count} tasks")
                
                # 2. Then detect force update for current incomplete windows
                await self._detect_force_update_tasks(user_id, expert_id, timestamp, tasks)
                current_tasks_count = len(tasks) - historical_tasks_count
                logger.info(f"[FORCE] Current window force update detection completed: {current_tasks_count} tasks")
                
                # Fix: deduplicate to avoid duplicate L4/L5 in same time window
                tasks = self._deduplicate_tasks(tasks)
                logger.info(f"[FORCE] Tasks after deduplication: {len(tasks)}")
                
            else:
                # Regular detection mode: only detect missing in completed time windows
                await self._detect_regular_missing_tasks(user_id, expert_id, timestamp, tasks)
            
            logger.info(f"[MANUAL] Manual backfill detection completed: total {len(tasks)} tasks")
            return tasks
            
        except Exception as e:
            logger.error(f"[MANUAL] Manual backfill detection failed: {e}", exc_info=True)
            return tasks
    
    async def _detect_force_update_tasks(
        self,
        user_id: str,
        expert_id: str,
        timestamp: datetime,
        tasks: List[BackfillTask]
    ) -> None:
        """
        Force update mode: force generate current incomplete windows
        
        Core principle: generate regardless of existence, but with strict idempotency constraints
        
        Include:
        - Today's L3 (generate regardless)
        - This week's L4 (generate regardless)
        - This month's L5 (generate regardless)
        
        Note:
        - L2 session memories handled by _detect_regular_missing_tasks, avoid duplication
        - Only handle L3/L4/L5 force update here
        
        Idempotency constraints:
        - Existing memory: force_update=True (modify)
        - Non-existing memory: force_update=False (create)
        """
        logger.info("[FORCE] Force update mode: only detect L3/L4/L5 update for current incomplete windows")
        
        # Fix: Use date from passed timestamp, not actual today
        # This allows using simulated time in tests
        today = timestamp.date() if isinstance(timestamp, datetime) else timestamp
        logger.info(f"[FORCE] Using date: {today} (from timestamp: {timestamp})")
        
        # Fix: Skip L2 detection, avoid duplication with _detect_regular_missing_tasks
        # L2 session memories handled by _detect_regular_missing_tasks
        logger.info("[FORCE] Skip L2 detection, handled by regular detection mode")
        
        # 1. Force update today's L3 (generate regardless)
        today_sessions = await self._get_sessions_in_day(user_id, expert_id, today)
        if today_sessions:
            # Check if L3 already exists
            today_start = datetime.combine(today, datetime.min.time())
            today_end = datetime.combine(today, datetime.max.time())
            
            query = {
                "user_id": user_id,
                "expert_id": expert_id,
                "layer": "L3",
                "time_window_start": today_start,
                "time_window_end": today_end
            }
            l3_memories = await self.storage_manager.search_memories(query, {})
            l3_exists = len(l3_memories) > 0
            
            # Force update: generate regardless, but with strict idempotency constraints
            task = BackfillTask(
                user_id=user_id,
                expert_id=expert_id,
                layer="L3",
                time_window={
                    "start_time": today_start,
                    "end_time": today_end
                },
                timestamp=timestamp,
                force_update=l3_exists  # Modify if exists, create if not
            )
            tasks.append(task)
            
            if l3_exists:
                logger.info(f"[FORCE] L3 exists, mark as modify task: date={today}")
            else:
                logger.info(f"[FORCE] L3 not exists, mark as create task: date={today}")
        
        # 2. Force update this week's L4 (generate regardless)
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        
        # Fix: Handle cross-month boundary, L4 time window ends at month end
        last_day_of_month = monthrange(today.year, today.month)[1]
        month_end_date = today.replace(day=last_day_of_month)
        
        if week_end > month_end_date:
            # Weekly report crosses month, end at month end
            week_end = month_end_date
            logger.info(f"[FORCE] L4 weekly report crosses month, end at month end: {week_start} to {week_end}")
        
        has_sessions_this_week = await self._check_has_sessions_in_week(user_id, expert_id, week_start, limit_end_date=week_end)
        if has_sessions_this_week:
            # Check if L4 already exists
            week_start_dt = datetime.combine(week_start, datetime.min.time())
            week_end_dt = datetime.combine(week_end, datetime.max.time())
            
            query = {
                "user_id": user_id,
                "expert_id": expert_id,
                "layer": "L4",
                "time_window_start": week_start_dt,
                "time_window_end": week_end_dt
            }
            l4_memories = await self.storage_manager.search_memories(query, {})
            l4_exists = len(l4_memories) > 0
            
            # Force update: generate regardless, but with strict idempotency constraints
            task = BackfillTask(
                user_id=user_id,
                expert_id=expert_id,
                layer="L4",
                time_window={
                    "start_time": week_start_dt,
                    "end_time": week_end_dt
                },
                timestamp=timestamp,
                force_update=l4_exists  # Modify if exists, create if not
            )
            tasks.append(task)
            
            if l4_exists:
                logger.info(f"[FORCE] L4 exists, mark as modify task: week={week_start}")
            else:
                logger.info(f"[FORCE] L4 not exists, mark as create task: week={week_start}")
        
        # 3. Force update this month's L5 (generate regardless)
        month_start = today.replace(day=1)
        last_day = monthrange(today.year, today.month)[1]
        month_end = today.replace(day=last_day)
        has_sessions_this_month = await self._check_has_sessions_in_month(user_id, expert_id, month_start)
        if has_sessions_this_month:
            # Check if L5 already exists
            month_start_dt = datetime.combine(month_start, datetime.min.time())
            month_end_dt = datetime.combine(month_end, datetime.max.time())
            
            query = {
                "user_id": user_id,
                "expert_id": expert_id,
                "layer": "L5",
                "time_window_start": month_start_dt,
                "time_window_end": month_end_dt
            }
            l5_memories = await self.storage_manager.search_memories(query, {})
            l5_exists = len(l5_memories) > 0
            
            # Force update: generate regardless, but with strict idempotency constraints
            task = BackfillTask(
                user_id=user_id,
                expert_id=expert_id,
                layer="L5",
                time_window={
                    "start_time": month_start_dt,
                    "end_time": month_end_dt
                },
                timestamp=timestamp,
                force_update=l5_exists  # Modify if exists, create if not
            )
            tasks.append(task)
            
            if l5_exists:
                logger.info(f"[FORCE] L5 exists, mark as modify task: month={month_start}")
            else:
                logger.info(f"[FORCE] L5 not exists, mark as create task: month={month_start}")
    
    async def _detect_regular_missing_tasks(
        self,
        user_id: str,
        expert_id: str,
        timestamp: datetime,
        tasks: List[BackfillTask]
    ) -> None:
        """
        Regular detection mode: only detect missing in completed time windows
        
        Include:
        - Non-existent L2 session memories
        - Yesterday's L3 (if not exists)
        - Last week's L4 (if not exists and last week completed)
        - Last month's L5 (if not exists and last month completed)
        """
        logger.info("[REGULAR] Regular detection mode: detect missing in completed time windows")
        
        # 1. Detect all missing L2 session memories
        await self._detect_missing_l2_sessions(user_id, expert_id, timestamp, tasks)
        
        # Fix: Use passed timestamp instead of date.today(), avoid time inconsistency in tests
        today = timestamp.date() if isinstance(timestamp, datetime) else timestamp
        
        # 2. Detect yesterday's L3 (if not exists)
        yesterday = today - timedelta(days=1)
        await self._detect_missing_l3_for_date(user_id, expert_id, yesterday, timestamp, tasks)
        
        # 3. Detect last week's L4 (if last week completed and not exists)
        current_week_start = today - timedelta(days=today.weekday())
        last_week_start = current_week_start - timedelta(days=7)
        last_week_end = last_week_start + timedelta(days=6)
        
        # Fix: Ensure last week completed (last Sunday must be before today)
        if last_week_end < today:  
            logger.info(f"[REGULAR] Detect last week L4: {last_week_start} to {last_week_end} (completed)")
            await self._detect_missing_l4_for_week(user_id, expert_id, last_week_start, timestamp, tasks)
        else:
            logger.info(f"[REGULAR] Last week not completed, skip L4 detection")
        
        # 4. Detect last month's L5 (if last month completed and not exists)
        current_month_start = today.replace(day=1)
        if today > current_month_start:  # Not first day of month, month has started
            last_month_end_date = current_month_start - timedelta(days=1)
            last_month_start = last_month_end_date.replace(day=1)
            logger.info(f"[REGULAR] Detect last month L5: {last_month_start} to {last_month_end_date} (completed)")
            await self._detect_missing_l5_for_month(user_id, expert_id, last_month_start, timestamp, tasks)
        else:
            logger.info(f"[REGULAR] Today is first day of month, skip L5 detection")
    
    async def _detect_force_incomplete_windows(
        self,
        user_id: str,
        expert_id: str,
        timestamp: datetime
    ) -> List[BackfillTask]:
        """
        Force mode specific: detect L4/L5 backfill for incomplete week/month of latest session
        
        Note:
        - **Only detect L4 and L5** (weekly and monthly reports), not L3 (daily handled by regular backfill)
        - Detect incomplete week and month of latest session
        - Add tasks regardless of memory existence (distinguish via force_update flag)
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            timestamp: Generation timestamp
        
        Returns:
            List of backfill tasks (only L4 and L5)
        """
        tasks = []
        
        # Get latest session date
        latest_session_date = await self._get_latest_session_date(user_id, expert_id)
        
        if not latest_session_date:
            logger.info(f"[FORCE] No sessions found, skip")
            return tasks
        
        logger.info(f"[FORCE] Latest session date: {latest_session_date}")
        
        # 1. Detect L4 for this week (incomplete weekly report)
        week_start = latest_session_date - timedelta(days=latest_session_date.weekday())
        week_end = week_start + timedelta(days=6)
        
        # Fix: Handle cross-month boundary, L4 time window ends at month end
        last_day_of_month = monthrange(latest_session_date.year, latest_session_date.month)[1]
        month_end_date = latest_session_date.replace(day=last_day_of_month)
        
        if week_end > month_end_date:
            # Weekly report crosses month, end at month end
            week_end = month_end_date
            logger.info(f"[FORCE] L4 weekly report crosses month, end at month end: {week_start} to {week_end}")
        
        has_sessions_in_week = await self._check_has_sessions_in_week(user_id, expert_id, week_start, limit_end_date=week_end)
        
        if has_sessions_in_week:
            query = {
                "user_id": user_id,
                "expert_id": expert_id,
                "layer": "L4",
                "time_window_start": datetime.combine(week_start, datetime.min.time()),
                "time_window_end": datetime.combine(week_end, datetime.max.time())
            }
            l4_memories = await self.storage_manager.search_memories(query, {})
            l4_exists = len(l4_memories) > 0
            
            # Force mode: add regardless of existence (idempotency guaranteed by storage layer)
            tasks.append(BackfillTask(
                user_id=user_id,
                expert_id=expert_id,
                layer="L4",
                time_window={
                    "start_time": datetime.combine(week_start, datetime.min.time()),
                    "end_time": datetime.combine(week_end, datetime.max.time())
                },
                timestamp=timestamp,
                force_update=l4_exists  # Update if exists, create if not
            ))
            logger.info(f"[FORCE] Add L4 task: week={week_start} to {week_end}, force_update={l4_exists}")
        
        # 2. Detect L5 for this month (incomplete monthly report)
        month_start = latest_session_date.replace(day=1)
        last_day = monthrange(latest_session_date.year, latest_session_date.month)[1]
        month_end = latest_session_date.replace(day=last_day)
        
        has_sessions_in_month = await self._check_has_sessions_in_month(user_id, expert_id, month_start)
        
        if has_sessions_in_month:
            query = {
                "user_id": user_id,
                "expert_id": expert_id,
                "layer": "L5",
                "time_window_start": datetime.combine(month_start, datetime.min.time()),
                "time_window_end": datetime.combine(month_end, datetime.max.time())
            }
            l5_memories = await self.storage_manager.search_memories(query, {})
            l5_exists = len(l5_memories) > 0
            
            # Force mode: add regardless of existence (idempotency guaranteed by storage layer)
            tasks.append(BackfillTask(
                user_id=user_id,
                expert_id=expert_id,
                layer="L5",
                time_window={
                    "start_time": datetime.combine(month_start, datetime.min.time()),
                    "end_time": datetime.combine(month_end, datetime.max.time())
                },
                timestamp=timestamp,
                force_update=l5_exists  # Update if exists, create if not
            ))
            logger.info(f"[FORCE] Add L5 task: month={month_start} to {month_end}, force_update={l5_exists}")
        
        logger.info(f"[FORCE] Detection completed: total {len(tasks)} tasks")
        return tasks
    
    async def _detect_force_current_latest(
        self,
        user_id: str,
        expert_id: str,
        force_timestamp: Optional[datetime] = None
    ) -> List[BackfillTask]:
        """
        Force backfill current latest daily/weekly/monthly memories (force mode) - Deprecated, kept for backward compatibility
        
        ⚠️ This method is deprecated, use detect_missing_in_recent_months(force=True)
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            force_timestamp: Timestamp for force backfill (used as generation time)
        
        Returns:
            List of force backfill tasks
        """
        logger.warning("[DEPRECATED] _detect_force_current_latest is deprecated, delegating to detect_missing_in_recent_months")
        
        # Delegate to new unified interface
        return await self.detect_missing_in_recent_months(
            user_id=user_id,
            expert_id=expert_id,
            month_count=2,
            force=True,
            force_timestamp=force_timestamp
        )
    
    async def detect_specific_session_l2(
        self,
        user_id: str,
        expert_id: str,
        session_id: str,
        timestamp: Optional[datetime] = None
    ) -> List[BackfillTask]:
        """
        Detect L2 missing for specific session (for inter-session backfill)
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            session_id: Session ID
            timestamp: Backfill timestamp
        
        Returns:
            L2 backfill task list (max 1)
        """
        await self._ensure_dependencies()
        
        tasks = []
        
        # Check if L2 exists
        l2_exists = await self.existence_checker.check_l2_exists(
            user_id, expert_id, session_id
        )
        
        if not l2_exists:
            tasks.append(BackfillTask(
                user_id=user_id,
                expert_id=expert_id,
                layer="L2",
                session_id=session_id,
                timestamp=timestamp or datetime.now()
            ))
            logger.info(f"[SESSION_L2] Detected missing L2: session={session_id}")
        
        return tasks
    
    # ==================== Helper Methods ====================
    
    def _deduplicate_tasks(self, tasks: List[BackfillTask]) -> List[BackfillTask]:
        """
        Deduplicate task list, avoid duplicate memories in same time window
        
        Deduplication rules:
        - L2: deduplicate by (user_id, expert_id, layer, session_id)
        - L3/L4/L5: deduplicate by (user_id, expert_id, layer, time_window)
        - Keep force_update=True tasks (prioritize force update)
        
        Args:
            tasks: Task list to deduplicate
        
        Returns:
            Deduplicated task list
        """
        if not tasks:
            return tasks
        
        seen = {}
        deduplicated = []
        
        for task in tasks:
            # Generate unique key
            if task.layer == "L2":
                key = (task.user_id, task.expert_id, task.layer, task.session_id)
            else:
                # L3/L4/L5 deduplicate by time window
                if task.time_window:
                    start = task.time_window.get("start_time")
                    end = task.time_window.get("end_time")
                    key = (task.user_id, task.expert_id, task.layer, start, end)
                else:
                    # No time window, skip deduplication
                    deduplicated.append(task)
                    continue
            
            # Check if already exists
            if key in seen:
                existing_task = seen[key]
                # If new task is force_update, replace old task
                if task.force_update and not existing_task.force_update:
                    logger.info(f"[DEDUP] Replace task: {task.layer} - {key} (keep force_update=True)")
                    seen[key] = task
                    # Update task in deduplicated list
                    for i, t in enumerate(deduplicated):
                        if t is existing_task:
                            deduplicated[i] = task
                            break
                else:
                    logger.info(f"[DEDUP] Skip duplicate task: {task.layer} - {key}")
            else:
                seen[key] = task
                deduplicated.append(task)
        
        removed_count = len(tasks) - len(deduplicated)
        if removed_count > 0:
            logger.info(f"[DEDUP] Deduplication completed: removed {removed_count} duplicate tasks")
        
        return deduplicated
    
    async def _get_sessions_in_day(
        self,
        user_id: str,
        expert_id: str,
        target_date: date
    ) -> List[Dict]:
        """
        Get all sessions for specified date

        Enhancement: Support detecting from both memory_sessions table and L1 memories
        - If memory_sessions has records, use them (original behavior)
        - If memory_sessions is empty, extract sessions from L1 memories in core_memories

        Args:
            user_id: User ID
            expert_id: Expert ID
            target_date: Target date

        Returns:
            List of sessions
        """
        try:
            from timem.core.global_connection_pool import get_global_pool_manager

            pool_manager = await get_global_pool_manager()
            day_start = datetime.combine(target_date, datetime.min.time())
            day_end = datetime.combine(target_date, datetime.max.time())

            # Step 1: Try to get sessions from memory_sessions table (original behavior)
            async with pool_manager.get_managed_session() as session:
                from sqlalchemy import text

                result = await session.execute(
                    text("""
                        SELECT id, start_time, updated_at
                        FROM memory_sessions
                        WHERE user_id = :user_id
                        AND expert_id = :expert_id
                        AND start_time >= :day_start
                        AND start_time <= :day_end
                        ORDER BY start_time
                    """),
                    {
                        "user_id": user_id,
                        "expert_id": expert_id,
                        "day_start": day_start,
                        "day_end": day_end
                    }
                )

                rows = result.fetchall()
                sessions = [
                    {
                        "session_id": row[0],
                        "id": row[0],
                        "start_time": row[1],
                        "updated_at": row[2],
                        "source": "memory_sessions"
                    }
                    for row in rows
                ]

                # Add debug logging
                if sessions:
                    logger.info(f"[DAILY_BACKFILL] Found {len(sessions)} sessions from memory_sessions: {[s['session_id'] for s in sessions]}")

            # Step 2: If no sessions found, extract from L1 memories (fallback)
            if not sessions:
                logger.info(f"[DAILY_BACKFILL] No sessions in memory_sessions for {target_date}, checking L1 memories")

                # Query L1 memories for the target date
                l1_memories = await self.storage_manager.search_memories(
                    query={
                        "user_id": user_id,
                        "expert_id": expert_id,
                        "level": "L1"
                    },
                    options={"limit": 1000}
                )

                logger.info(f"[DAILY_BACKFILL] Found {len(l1_memories)} L1 memories total, filtering by date")

                # Filter L1 memories by target date (check time_window_start)
                sessions_map = {}
                for memory in l1_memories:
                    if isinstance(memory, dict):
                        time_window_start = memory.get("time_window_start")
                    else:
                        time_window_start = memory.time_window_start

                    # Convert to datetime if needed
                    if isinstance(time_window_start, str):
                        from timem.utils.time_utils import parse_time
                        time_window_start = parse_time(time_window_start)

                    # Check if this memory is within the target date
                    if time_window_start and day_start <= time_window_start <= day_end:
                        # Group by time_window (same time_window = same session)
                        session_key = time_window_start.isoformat() if hasattr(time_window_start, 'isoformat') else str(time_window_start)

                        if session_key not in sessions_map:
                            sessions_map[session_key] = {
                                "session_id": f"l1_session_{target_date.strftime('%Y%m%d')}_{int(time_window_start.timestamp())}",
                                "id": f"l1_session_{target_date.strftime('%Y%m%d')}_{int(time_window_start.timestamp())}",
                                "start_time": time_window_start,
                                "updated_at": datetime.now(),
                                "source": "l1_memory"
                            }

                sessions = list(sessions_map.values())
                logger.info(f"[DAILY_BACKFILL] Extracted {len(sessions)} sessions from L1 memories for {target_date}")

            return sessions

        except Exception as e:
            logger.error(f"Failed to get sessions for specified date: {e}", exc_info=True)
            return []
    
    async def _get_latest_session_date(
        self,
        user_id: str,
        expert_id: str
    ) -> Optional[date]:
        """
        Get latest session date
        
        Args:
            user_id: User ID
            expert_id: Expert ID
        
        Returns:
            Latest session date, None if not found
        """
        try:
            from timem.core.global_connection_pool import get_global_pool_manager
            
            pool_manager = await get_global_pool_manager()
            
            async with pool_manager.get_managed_session() as session:
                from sqlalchemy import text, func, select
                # Fix: MemorySession is defined in postgres_store, not session_tracker
                from storage.postgres_store import MemorySession
                
                result = await session.execute(
                    select(func.max(MemorySession.start_time)).where(
                        MemorySession.user_id == user_id,
                        MemorySession.expert_id == expert_id
                    )
                )
                
                row = result.fetchone()
                if row and row[0]:
                    return row[0].date()
                
                return None
                
        except Exception as e:
            logger.error(f"Failed to get latest session date: {e}", exc_info=True)
            return None
    
    async def _check_has_sessions_in_week(
        self,
        user_id: str,
        expert_id: str,
        week_start: date,
        limit_end_date: Optional[date] = None
    ) -> bool:
        """
        Check if specified week has valid sessions
        
        Fix: Unified check logic, only check if sessions exist, not check child memories
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            week_start: Monday date
            limit_end_date: Limit end date (for cross-month boundary, default Sunday)
        
        Returns:
            Whether week has valid sessions
        """
        try:
            week_end = week_start + timedelta(days=6)
            
            # Handle cross-month boundary: if limit end date specified, use smaller one
            if limit_end_date and week_end > limit_end_date:
                week_end = limit_end_date
                logger.debug(f"[L4_CHECK] Week {week_start} crosses month, limit check to {limit_end_date}")
            
            # Check if week has sessions
            for day_offset in range(7):
                current_day = week_start + timedelta(days=day_offset)
                if current_day > week_end:
                    break
                sessions = await self._get_sessions_in_day(user_id, expert_id, current_day)
                if len(sessions) > 0:
                    logger.debug(f"[L4_CHECK] Week {week_start} has valid sessions")
                    return True
            
            logger.debug(f"[L4_CHECK] Week {week_start} has no sessions, skip L4")
            return False
            
        except Exception as e:
            logger.error(f"Failed to check week sessions: {e}", exc_info=True)
            return False
    
    async def _check_has_sessions_in_month(
        self,
        user_id: str,
        expert_id: str,
        month_start: date
    ) -> bool:
        """
        Check if specified month has valid sessions
        
        Fix: Unified check logic, only check if sessions exist, not check child memories
        
        Args:
            user_id: User ID
            expert_id: Expert ID
            month_start: First day of month
        
        Returns:
            Whether month has valid sessions
        """
        try:
            last_day = monthrange(month_start.year, month_start.month)[1]
            month_end = month_start.replace(day=last_day)
            
            # Check if month has sessions
            current_day = month_start
            while current_day <= month_end:
                sessions = await self._get_sessions_in_day(user_id, expert_id, current_day)
                if len(sessions) > 0:
                    logger.debug(f"[L5_CHECK] Month {month_start} has valid sessions")
                    return True
                current_day += timedelta(days=1)
            
            logger.debug(f"[L5_CHECK] Month {month_start} has no sessions, skip L5")
            return False
            
        except Exception as e:
            logger.error(f"Failed to check month sessions: {e}", exc_info=True)
            return False
    
    async def _detect_missing_l2_sessions(
        self,
        user_id: str,
        expert_id: str,
        timestamp: datetime,
        tasks: List[BackfillTask]
    ) -> None:
        """
        Detect all missing L2 session memories

        Enhancement: Support detecting from both memory_sessions table and L1 memories
        - If memory_sessions has records, use them (original behavior)
        - If memory_sessions is empty, extract sessions from L1 memories in core_memories
        """
        try:
            from timem.core.global_connection_pool import get_global_pool_manager
            from datetime import time as dt_time

            pool_manager = await get_global_pool_manager()
            all_sessions = []

            # Step 1: Try to get sessions from memory_sessions table (original behavior)
            async with pool_manager.get_managed_session() as session:
                from sqlalchemy import text

                result = await session.execute(
                    text("""
                        SELECT id, start_time, updated_at
                        FROM memory_sessions
                        WHERE user_id = :user_id
                        AND expert_id = :expert_id
                        ORDER BY start_time DESC
                        LIMIT 100
                    """),
                    {
                        "user_id": user_id,
                        "expert_id": expert_id
                    }
                )

                rows = result.fetchall()
                all_sessions = [
                    {
                        "session_id": row[0],
                        "id": row[0],
                        "start_time": row[1],
                        "updated_at": row[2],
                        "source": "memory_sessions"
                    }
                    for row in rows
                ]

                logger.info(f"[REGULAR] Found {len(all_sessions)} sessions in memory_sessions table")

                # Step 2: If no sessions found, extract from L1 memories (fallback)
                if not all_sessions:
                    logger.info(f"[REGULAR] No sessions in memory_sessions, checking L1 memories in core_memories")

                    # Query L1 memories to extract session information
                    l1_memories = await self.storage_manager.search_memories(
                        query={
                            "user_id": user_id,
                            "expert_id": expert_id,
                            "level": "L1"
                        },
                        options={"limit": 1000}
                    )

                    logger.info(f"[REGULAR] Found {len(l1_memories)} L1 memories")

                    # Group L1 memories by time_window to identify sessions
                    # Sessions with same time_window are considered the same session
                    sessions_map = {}  # {time_window_start: [memories]}
                    for memory in l1_memories:
                        if isinstance(memory, dict):
                            time_window_start = memory.get("time_window_start")
                            time_window_end = memory.get("time_window_end")
                        else:
                            time_window_start = memory.time_window_start
                            time_window_end = memory.time_window_end

                        # Use time_window_start as session identifier
                        if time_window_start:
                            session_key = time_window_start.isoformat() if hasattr(time_window_start, 'isoformat') else str(time_window_start)

                            if session_key not in sessions_map:
                                sessions_map[session_key] = {
                                    "start_time": time_window_start,
                                    "end_time": time_window_end,
                                    "memories": []
                                }
                            sessions_map[session_key]["memories"].append(memory)

                    # Convert to session format
                    for session_key, session_data in sessions_map.items():
                        session_start = session_data["start_time"]

                        # Generate a session_id from time_window_start
                        if isinstance(session_start, str):
                            from timem.utils.time_utils import parse_time
                            session_start = parse_time(session_start)

                        session_date = session_start.date()
                        session_id = f"l1_session_{session_date.strftime('%Y%m%d')}_{int(session_start.timestamp())}"

                        all_sessions.append({
                            "session_id": session_id,
                            "id": session_id,
                            "start_time": session_start,
                            "updated_at": timestamp,
                            "source": "l1_memory",
                            "date": session_date
                        })

                    logger.info(f"[REGULAR] Extracted {len(all_sessions)} sessions from L1 memories")

                # Step 3: Check each session's L2 existence
                logger.info(f"[REGULAR] Check L2 memory for {len(all_sessions)} sessions")

                for session in all_sessions:
                    session_id = session.get("session_id") or session.get("id")

                    # Check if L2 exists
                    l2_exists = await self.existence_checker.check_l2_exists(
                        user_id, expert_id, session_id
                    )

                    if not l2_exists:
                        # Set L2 memory time to 23:59:59 of session day
                        session_start = session.get("start_time")
                        if isinstance(session_start, str):
                            from timem.utils.time_utils import parse_time
                            session_start = parse_time(session_start)

                        # L2 time = 23:59:59 of session day
                        session_date = session.get("date") if session.get("date") else session_start.date()
                        l2_timestamp = datetime.combine(session_date, dt_time(23, 59, 59))

                        tasks.append(BackfillTask(
                            user_id=user_id,
                            expert_id=expert_id,
                            layer="L2",
                            session_id=session_id,
                            timestamp=l2_timestamp,
                            force_update=False  # Regular mode does not force update
                        ))
                        source = session.get("source", "unknown")
                        logger.info(f"[REGULAR] Add L2 task: session={session_id}, date={session_date}, source={source}")

        except Exception as e:
            logger.error(f"Failed to detect missing L2 sessions: {e}", exc_info=True)
    
    async def _detect_missing_l3_for_date(
        self,
        user_id: str,
        expert_id: str,
        target_date: date,
        timestamp: datetime,
        tasks: List[BackfillTask]
    ) -> None:
        """Detect if L3 memory is missing for specified date"""
        # Check if date has sessions
        sessions = await self._get_sessions_in_day(user_id, expert_id, target_date)
        if not sessions:
            return
        
        # Check if L3 exists
        query = {
            "user_id": user_id,
            "expert_id": expert_id,
            "layer": "L3",
            "time_window_start": datetime.combine(target_date, datetime.min.time()),
            "time_window_end": datetime.combine(target_date, datetime.max.time())
        }
        l3_memories = await self.storage_manager.search_memories(query, {})
        l3_exists = len(l3_memories) > 0
        
        if not l3_exists:
            tasks.append(BackfillTask(
                user_id=user_id,
                expert_id=expert_id,
                layer="L3",
                time_window={
                    "start_time": datetime.combine(target_date, datetime.min.time()),
                    "end_time": datetime.combine(target_date, datetime.max.time())
                },
                timestamp=timestamp,
                force_update=False  # Regular mode does not force update
            ))
            logger.info(f"[REGULAR] Add L3 task: date={target_date}")
    
    async def _detect_missing_l4_for_week(
        self,
        user_id: str,
        expert_id: str,
        week_start: date,
        timestamp: datetime,
        tasks: List[BackfillTask]
    ) -> None:
        """Detect if L4 memory is missing for specified week"""
        # Fix: Handle cross-month boundary, L4 time window ends at month end
        week_end = week_start + timedelta(days=6)
        last_day_of_month = monthrange(week_start.year, week_start.month)[1]
        month_end_date = week_start.replace(day=last_day_of_month)
        
        if week_end > month_end_date:
            # Weekly report crosses month, end at month end
            week_end = month_end_date
            logger.info(f"[REGULAR] L4 weekly report crosses month, end at month end: {week_start} to {week_end}")
        
        # Check if week has sessions
        has_sessions = await self._check_has_sessions_in_week(user_id, expert_id, week_start, limit_end_date=week_end)
        if not has_sessions:
            return
        
        # Check if L4 exists
        query = {
            "user_id": user_id,
            "expert_id": expert_id,
            "layer": "L4",
            "time_window_start": datetime.combine(week_start, datetime.min.time()),
            "time_window_end": datetime.combine(week_end, datetime.max.time())
        }
        l4_memories = await self.storage_manager.search_memories(query, {})
        l4_exists = len(l4_memories) > 0
        
        if not l4_exists:
            tasks.append(BackfillTask(
                user_id=user_id,
                expert_id=expert_id,
                layer="L4",
                time_window={
                    "start_time": datetime.combine(week_start, datetime.min.time()),
                    "end_time": datetime.combine(week_end, datetime.max.time())
                },
                timestamp=timestamp,
                force_update=False  # Regular mode does not force update
            ))
            logger.info(f"[REGULAR] Add L4 task: week={week_start}")
    
    async def _detect_missing_l5_for_month(
        self,
        user_id: str,
        expert_id: str,
        month_start: date,
        timestamp: datetime,
        tasks: List[BackfillTask]
    ) -> None:
        """Detect if L5 memory is missing for specified month"""
        # Check if month has sessions
        has_sessions = await self._check_has_sessions_in_month(user_id, expert_id, month_start)
        if not has_sessions:
            return
        
        # Check if L5 exists
        last_day = monthrange(month_start.year, month_start.month)[1]
        month_end = month_start.replace(day=last_day)
        query = {
            "user_id": user_id,
            "expert_id": expert_id,
            "layer": "L5",
            "time_window_start": datetime.combine(month_start, datetime.min.time()),
            "time_window_end": datetime.combine(month_end, datetime.max.time())
        }
        l5_memories = await self.storage_manager.search_memories(query, {})
        l5_exists = len(l5_memories) > 0
        
        if not l5_exists:
            tasks.append(BackfillTask(
                user_id=user_id,
                expert_id=expert_id,
                layer="L5",
                time_window={
                    "start_time": datetime.combine(month_start, datetime.min.time()),
                    "end_time": datetime.combine(month_end, datetime.max.time())
                },
                timestamp=timestamp,
                force_update=False  # Regular mode does not force update
            ))
            logger.info(f"[REGULAR] Add L5 task: month={month_start}")
    
    async def detect_multi_expert_completion(
        self,
        user_id: str,
        expert_ids: List[str] = None,
        force_update: bool = True,
        manual_timestamp: Optional[datetime] = None
    ) -> Dict[str, List[BackfillTask]]:
        """
        Multi-expert backfill detection
        
        Independently perform backfill detection for different expert groups of same user
        
        Args:
            user_id: User ID
            expert_ids: List of expert IDs, if None auto-detect all experts with interaction records
            force_update: Whether to use force update mode
            manual_timestamp: Timestamp for manual backfill
        
        Returns:
            Task dictionary grouped by expert ID {expert_id: [BackfillTask, ...]}
        """
        await self._ensure_dependencies()
        
        timestamp = manual_timestamp or datetime.now()
        logger.info(f"[MULTI-EXPERT] Start multi-expert backfill detection: user={user_id}, force_update={force_update}")
        
        # If no expert list specified, auto-detect
        if expert_ids is None:
            expert_ids = await self._get_user_expert_list(user_id)
        
        if not expert_ids:
            logger.warning(f"[MULTI-EXPERT] User {user_id} has no experts found")
            return {}
        
        logger.info(f"[MULTI-EXPERT] Detect {len(expert_ids)} experts: {expert_ids}")
        
        # Independently detect for each expert
        results = {}
        for expert_id in expert_ids:
            try:
                logger.info(f"[MULTI-EXPERT] Detecting expert {expert_id}...")
                tasks = await self.detect_manual_completion(
                    user_id=user_id,
                    expert_id=expert_id,
                    force_update=force_update,
                    manual_timestamp=timestamp
                )
                results[expert_id] = tasks
                logger.info(f"[MULTI-EXPERT] Expert {expert_id} detection completed: {len(tasks)} tasks")
            except Exception as e:
                logger.error(f"[MULTI-EXPERT] Expert {expert_id} detection failed: {e}", exc_info=True)
                results[expert_id] = []
        
        total_tasks = sum(len(tasks) for tasks in results.values())
        logger.info(f"[MULTI-EXPERT] Multi-expert detection completed: {len(expert_ids)} experts, total {total_tasks} tasks")
        
        return results
    
    async def _get_user_expert_list(self, user_id: str) -> List[str]:
        """Get all expert list associated with user"""
        try:
            from storage.postgres_store import get_postgres_store
            from sqlalchemy import text
            
            postgres_store = await get_postgres_store()
            async with postgres_store.get_session() as db_session:
                query = text("""
                    SELECT DISTINCT expert_id
                    FROM memory_sessions
                    WHERE user_id = :user_id
                    ORDER BY expert_id
                """)
                
                result = await db_session.execute(query, {"user_id": user_id})
                expert_rows = result.fetchall()
                expert_list = [row[0] for row in expert_rows]
            
            logger.info(f"[MULTI-EXPERT] User {user_id} associated experts: {expert_list}")
            return expert_list
            
        except Exception as e:
            logger.error(f"[MULTI-EXPERT] Failed to get user expert list: {e}", exc_info=True)
            return []
