from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.logging import get_logger
from app.domain.repositories import BotRepository, GroupRepository
from app.domain.services import BotService, GroupService
from app.infrastructure.db.base import get_session
from app.infrastructure.db.models import BotFailoverLog

logger = get_logger(__name__)


@dataclass(slots=True)
class SupervisorConfig:
    interval_seconds: int = 30
    heartbeat_timeout_seconds: int = 120


class BotSupervisor:
    def __init__(self, config: SupervisorConfig | None = None) -> None:
        self.config = config or SupervisorConfig()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if not self._task:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _loop(self) -> None:
        logger.info("supervisor.start", interval=self.config.interval_seconds)
        try:
            while True:
                await asyncio.sleep(self.config.interval_seconds)
                try:
                    await self._check_bots()
                except Exception as exc:
                    logger.error("supervisor.error", error=str(exc))
        except asyncio.CancelledError:
            logger.info("supervisor.stop")
            raise

    async def _check_bots(self) -> None:
        async with get_session() as session:
            bot_repo = BotRepository(session)
            group_repo = GroupRepository(session)
            bot_service = BotService(bot_repo)
            group_service = GroupService(group_repo)

            bots = await bot_repo.list()
            now = datetime.now(tz=UTC)
            offline_bots = []
            standby_bots = []
            for bot in bots:
                timeout = timedelta(seconds=bot.heartbeat_interval_seconds or self.config.heartbeat_timeout_seconds)
                if bot.last_heartbeat and now - bot.last_heartbeat <= timeout:
                    if bot.status != "active":
                        await bot_service.update_status(bot.id, status="active")
                    if bot.status == "standby":
                        standby_bots.append(bot)
                    continue
                offline_bots.append(bot)
                await bot_service.update_status(bot.id, status="offline")

            active_bots = [bot for bot in bots if bot.status == "active"]
            if not active_bots and standby_bots:
                for standby in standby_bots:
                    await bot_service.update_status(standby.id, status="active")
                    active_bots.append(standby)

            for bot in offline_bots:
                groups = await group_repo.active_groups_for_bot(bot.id)
                for group in groups:
                    replacement = self._choose_replacement(active_bots, bot.id)
                    await group_service.assign_bot(group.id, replacement.id if replacement else None)
                    session.add(
                        BotFailoverLog(
                            group_id=group.id,
                            old_bot_id=bot.id,
                            new_bot_id=replacement.id if replacement else None,
                            reason="heartbeat timeout",
                        )
                    )
                    logger.info(
                        "supervisor.failover",
                        group_id=group.id,
                        from_bot=bot.name,
                        to_bot=replacement.name if replacement else None,
                    )

    def _choose_replacement(self, bots, failed_bot_id: int):
        candidates = [bot for bot in bots if bot.id != failed_bot_id]
        if not candidates:
            return None
        return sorted(candidates, key=lambda b: b.last_heartbeat or datetime.min, reverse=True)[0]

