from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timezone

from app.core.logging import get_logger
from app.domain.repositories import CategoryRepository
from app.domain.services import CategoryService
from app.infrastructure.db.base import get_session
from app.scheduling.dispatcher import DispatchEngine


logger = get_logger(__name__)


class CategoryScheduler:
    def __init__(self, application, *, tick_seconds: int = 60) -> None:
        self.application = application
        self.tick_seconds = tick_seconds
        self._task: asyncio.Task | None = None
        self._engine = DispatchEngine(application)

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._run())
        logger.info("scheduler.start", tick=self.tick_seconds)

    async def stop(self) -> None:
        if not self._task:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        logger.info("scheduler.stop")

    async def _run(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.tick_seconds)
                await self._process()
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - safety net
            logger.exception("scheduler.loop_error")

    async def _process(self) -> None:
        try:
            async with get_session() as session:
                service = CategoryService(CategoryRepository(session))
                due_categories = await service.list_due_for_dispatch(now=datetime.now(timezone.utc))
                if not due_categories:
                    return
                for category in due_categories:
                    try:
                        await self._engine.dispatch_category(category.slug)
                        await service.record_dispatch(category.id, dispatched_at=datetime.now(timezone.utc))
                    except Exception:
                        logger.exception("scheduler.dispatch_error", category=category.slug)
                await session.commit()
        except Exception:
            logger.exception("scheduler.process_error")

