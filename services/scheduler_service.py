"""
Scheduled Task Scheduling Service

Implements scheduled backfill tasks using APScheduler
"""

import asyncio
from datetime import datetime
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from timem.utils.logging import get_logger
from services.scheduled_backfill_service import (
    ScheduledBackfillService,
    BackfillReport
)
from services.session_memory_scanner import (
    get_session_memory_scanner,
    SessionScanResult
)

logger = get_logger(__name__)


class SchedulerService:
    """
    Scheduled Task Scheduling Service
    
    Features:
    1. Manage scheduled tasks using APScheduler
    2. Trigger memory backfill at 2:00 AM daily
    3. Support manual backfill triggering
    4. Monitoring and logging
    """
    
    def __init__(self):
        self.scheduler: Optional[AsyncIOScheduler] = None
        self.backfill_service: Optional[ScheduledBackfillService] = None
        self.session_scanner = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize scheduler"""
        if self._initialized:
            return
        
        logger.info(" Initializing scheduled task scheduler...")
        
        # Create scheduler
        self.scheduler = AsyncIOScheduler()
        
        # Create backfill service
        self.backfill_service = ScheduledBackfillService()
        
        # Create session memory scan service
        self.session_scanner = await get_session_memory_scanner()
        
        # Add daily backfill task
        if self.backfill_service.enabled:
            schedule_time = self.backfill_service.config.get("schedule", "0 2 * * *")
            
            self.scheduler.add_job(
                self._run_daily_backfill,
                trigger=CronTrigger.from_crontab(schedule_time),
                id="daily_memory_backfill",
                name="Daily Memory Backfill",
                replace_existing=True,
                max_instances=1  # Ensure only one instance runs at a time
            )
            
            logger.info(f" Added daily backfill task: {schedule_time}")
            logger.info(f"   Next execution time: {self.scheduler.get_job('daily_memory_backfill').next_run_time}")
        else:
            logger.warning(" Scheduled backfill is disabled, skipping task registration")
        
        # Add session memory scan task
        if self.session_scanner.enabled:
            scan_interval = self.session_scanner.config.get("scan_interval_minutes", 10)
            
            self.scheduler.add_job(
                self._run_session_memory_scan,
                trigger="interval",
                minutes=scan_interval,
                id="session_memory_scan",
                name="Session Memory Scan",
                replace_existing=True,
                max_instances=1  # Ensure only one instance runs at a time
            )
            
            logger.info(f" Added session memory scan task: every {scan_interval} minutes")
        else:
            logger.warning(" Session memory scan is disabled, skipping task registration")
        
        self._initialized = True
    
    async def start(self):
        """Start scheduler"""
        if not self._initialized:
            await self.initialize()
        
        if self.scheduler and not self.scheduler.running:
            self.scheduler.start()
            logger.info(" Scheduled task scheduler started")
            
            # Display all registered tasks
            jobs = self.scheduler.get_jobs()
            if jobs:
                logger.info(f" Registered tasks: {len(jobs)}")
                for job in jobs:
                    logger.info(f"   - {job.name} (ID: {job.id}), Next run: {job.next_run_time}")
            else:
                logger.warning(" No registered tasks found")
    
    async def shutdown(self):
        """Shutdown scheduler"""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=True)
            logger.info(" Scheduled task scheduler shutdown")
    
    async def _run_daily_backfill(self):
        """Execute daily backfill task"""
        try:
            logger.info("=" * 80)
            logger.info(" [Scheduled Task] Triggered daily memory backfill")
            logger.info(f" Trigger time: {datetime.now()}")
            logger.info("=" * 80)
            
            # Execute backfill
            start_time = datetime.now()
            report = await self.backfill_service.run_daily_backfill()
            duration = (datetime.now() - start_time).total_seconds()
            
            # Record results
            logger.info("\n" + "=" * 80)
            logger.info(" Daily backfill task completed")
            logger.info(f" Total time: {duration:.2f}s")
            logger.info(f" Users processed: {report.total_users}")
            logger.info(f" Total tasks: {report.total_tasks}")
            logger.info(f" Completed: {report.completed_tasks}")
            logger.info(f" Failed: {report.failed_tasks}")
            
            success_rate = (report.completed_tasks / report.total_tasks * 100) if report.total_tasks > 0 else 0
            logger.info(f" Success rate: {success_rate:.1f}%")
            
            # Alert judgment
            if report.failed_tasks > 0:
                logger.warning(f" {report.failed_tasks} tasks failed, please check logs")
                # TODO: Send alert notification
            
            if report.total_tasks == 0:
                logger.info(" No backfill needed, all user memories are up to date")
            
            logger.info("=" * 80 + "\n")
            
            # TODO: Store report to database for monitoring dashboard display
            
        except Exception as e:
            logger.error(f" Daily backfill task execution exception: {e}", exc_info=True)
            logger.error(f"❌ Daily backfill task execution exception: {e}", exc_info=True)
            # TODO: Send emergency alert
    
    async def _run_session_memory_scan(self):
        """Execute session memory scan task"""
        try:
            logger.debug("🔍 [Scheduled Task] Triggered session memory scan")
            
            # Execute scan
            start_time = datetime.now()
            result = await self.session_scanner.scan_and_process()
            duration = (datetime.now() - start_time).total_seconds()
            
            # Record results (only log in detail when there is activity)
            if result.scanned_sessions > 0:
                logger.info(
                    f"🔍 Session memory scan completed: scanned={result.scanned_sessions}, "
                    f"created={result.generated_memories}, updated={result.updated_memories}, "
                    f"failed={result.failed_sessions}, duration={duration:.1f}s"
                )
                
                if result.errors:
                    logger.warning(f"⚠️ Errors during scan: {result.errors[:3]}")  # Only show first 3 errors
            else:
                logger.debug("🔍 Session memory scan completed, no sessions to process")
                
        except Exception as e:
            logger.error(f"❌ Session memory scan task exception: {e}", exc_info=True)
    
    def trigger_manual_backfill(self):
        """Manually trigger backfill task (execute immediately)"""
        if self.scheduler and self.scheduler.running:
            job_id = f"manual_backfill_{int(datetime.now().timestamp())}"
            self.scheduler.add_job(
                self._run_daily_backfill,
                id=job_id,
                name="Manual trigger backfill",
                max_instances=1
            )
            logger.info(f"🔘 Added manual backfill task: {job_id}")
            return job_id
        else:
            logger.error("Scheduler is not running, cannot trigger manual backfill")
            return None
    
    def trigger_manual_session_scan(self):
        """Manually trigger session memory scan (execute immediately)"""
        if self.scheduler and self.scheduler.running:
            job_id = f"manual_session_scan_{int(datetime.now().timestamp())}"
            self.scheduler.add_job(
                self._run_session_memory_scan,
                id=job_id,
                name="Manual trigger session scan",
                max_instances=1
            )
            logger.info(f"🔍 Added manual session scan task: {job_id}")
            return job_id
        else:
            logger.error("Scheduler is not running, cannot trigger manual session scan")
            return None
    
    def get_scheduler_status(self) -> dict:
        """Get scheduler status"""
        if not self.scheduler:
            return {"status": "not_initialized"}
        
        return {
            "status": "running" if self.scheduler.running else "stopped",
            "jobs": [
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                    "pending": job.pending
                }
                for job in self.scheduler.get_jobs()
            ]
        }


# Global singleton
_scheduler_service: Optional[SchedulerService] = None
_service_lock = asyncio.Lock()


async def get_scheduler_service() -> SchedulerService:
    """Get scheduler service singleton"""
    global _scheduler_service
    
    if _scheduler_service is None:
        async with _service_lock:
            if _scheduler_service is None:
                _scheduler_service = SchedulerService()
                await _scheduler_service.initialize()
    
    return _scheduler_service


async def cleanup_scheduler_service():
    """Cleanup scheduler service"""
    global _scheduler_service
    
    if _scheduler_service is not None:
        await _scheduler_service.shutdown()
        _scheduler_service = None

