"""
APScheduler setup for periodic model retraining.

- full_retrain : runs daily at a configured hour (default 2:00 AM)
- partial_update: runs every N minutes (default 30)
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings
from app.services.recommendation.model_manager import engine

logger = logging.getLogger(__name__)

# Thread pool for CPU-bound training work
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="retrain")

scheduler = AsyncIOScheduler()


def _run_full_retrain() -> None:
    """Synchronous wrapper executed in the thread pool."""
    try:
        result = engine.full_retrain()
        logger.info("Scheduled full retrain result: %s", result)
    except Exception:
        logger.exception("Scheduled full retrain FAILED")


def _run_partial_update() -> None:
    """Synchronous wrapper executed in the thread pool."""
    try:
        result = engine.partial_update()
        logger.info("Scheduled partial update result: %s", result)
    except Exception:
        logger.exception("Scheduled partial update FAILED")


async def _async_full_retrain() -> None:
    """Run full retrain in a thread so we don't block the event loop."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(_executor, _run_full_retrain)


async def _async_partial_update() -> None:
    """Run partial update in a thread so we don't block the event loop."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(_executor, _run_partial_update)


def start_scheduler() -> None:
    """Register jobs and start the APScheduler."""
    # Daily full retrain
    scheduler.add_job(
        _async_full_retrain,
        trigger=CronTrigger(
            hour=settings.RETRAIN_HOUR,
            minute=settings.RETRAIN_MINUTE,
        ),
        id="full_retrain",
        name="Daily full retrain",
        replace_existing=True,
        max_instances=1,
    )

    # Periodic partial update
    scheduler.add_job(
        _async_partial_update,
        trigger=IntervalTrigger(
            minutes=settings.PARTIAL_UPDATE_INTERVAL_MINUTES,
        ),
        id="partial_update",
        name="Periodic partial update",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.start()
    logger.info(
        "Scheduler started — full retrain at %02d:%02d daily, "
        "partial update every %d minutes",
        settings.RETRAIN_HOUR,
        settings.RETRAIN_MINUTE,
        settings.PARTIAL_UPDATE_INTERVAL_MINUTES,
    )


def stop_scheduler() -> None:
    """Gracefully shut down the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
