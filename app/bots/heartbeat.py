from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from typing import Awaitable, Callable

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class HeartbeatConfig:
    bot_name: str
    interval: int = 60


class HeartbeatMonitor:
    def __init__(self, heartbeat_callable: Callable[[str], Awaitable[None]]):
        self._heartbeat_callable = heartbeat_callable
        self._task: asyncio.Task | None = None

    async def start(self, config: HeartbeatConfig) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._run(config))

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self, config: HeartbeatConfig) -> None:
        logger.info("heartbeat.start", bot=config.bot_name, interval=config.interval)
        try:
            while True:
                await asyncio.sleep(config.interval)
                try:
                    await self._heartbeat_callable(config.bot_name)
                except Exception as exc:
                    logger.error("heartbeat.error", bot=config.bot_name, error=str(exc))
        except asyncio.CancelledError:
            logger.info("heartbeat.stop", bot=config.bot_name)
            raise
