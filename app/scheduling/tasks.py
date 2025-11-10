from __future__ import annotations

from datetime import timedelta
from typing import Iterable

from telegram.ext import Application, JobQueue

from app.core.logging import get_logger
from app.scheduling.dispatcher import DispatchEngine

logger = get_logger(__name__)


def schedule_category_dispatch(
    application: Application,
    *,
    slug: str,
    interval_minutes: int = 60,
    allow_media: bool = True,
    allow_copy: bool = True,
    allow_buttons: bool = True,
) -> None:
    dispatcher = DispatchEngine(application)

    async def job_callback(context) -> None:  # type: ignore[override]
        await dispatcher.dispatch_category(
            slug,
            allow_media=allow_media,
            allow_copy=allow_copy,
            allow_buttons=allow_buttons,
        )

    job_queue: JobQueue = application.job_queue
    job_queue.run_repeating(job_callback, interval=timedelta(minutes=interval_minutes), name=f"dispatch:{slug}")

