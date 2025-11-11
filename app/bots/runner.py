from __future__ import annotations

import argparse
import asyncio
import contextlib
import signal

from telegram.ext import Application

from app.bots.heartbeat import HeartbeatConfig, HeartbeatMonitor
from app.bots.registry import BotConfig, load_registry
from app.bots.supervisor import BotSupervisor
from app.commands.admin_handlers import register_admin_handlers
from app.commands.menu_handlers import register_menu_handlers
from app.commands.repository_handlers import register_repository_handlers
from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.core.logging import configure_logging, get_logger
from app.core.notifications import AdminNotifier
from app.domain.repositories import BotRepository
from app.domain.services import BotService
from app.infrastructure.db.base import get_session
from app.scheduling.category_scheduler import CategoryScheduler

logger = get_logger(__name__)


async def _bootstrap_bot_record(config: BotConfig) -> None:
    async with get_session() as session:
        repo = BotRepository(session)
        service = BotService(repo)
        try:
            bot = await repo.get_by_name(config.name)
        except NotFoundError:
            await service.register_bot(name=config.name, token=config.token, status="active")
        else:
            await service.update_token(bot_id=bot.id, token=config.token)


async def _heartbeat_callable(bot_name: str) -> None:
    async with get_session() as session:
        repo = BotRepository(session)
        service = BotService(repo)
        await service.heartbeat_by_name(bot_name)


async def run_bot(config: BotConfig) -> None:
    await _bootstrap_bot_record(config)

    application = (
        Application.builder()
        .token(config.token)
        .concurrent_updates(True)
        .build()
    )

    register_admin_handlers(application)
    register_menu_handlers(application)
    register_repository_handlers(application)

    monitor = HeartbeatMonitor(_heartbeat_callable)
    notifier = AdminNotifier(application.bot, get_settings().admin_ids)
    supervisor = BotSupervisor(notifier=notifier)
    scheduler = CategoryScheduler(application)
    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_event.set)

    try:
        await monitor.start(HeartbeatConfig(bot_name=config.name, interval=60))
        await supervisor.start()
        await scheduler.start()
        logger.info("bot.start", name=config.name, role=config.role)
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        await stop_event.wait()
    except asyncio.CancelledError:
        stop_event.set()
        raise
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        await monitor.stop()
        await supervisor.stop()
        await scheduler.stop()
        logger.info("bot.stop", name=config.name)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KingsCEO Telegram bot runner.")
    parser.add_argument("--bot", required=True, help="Nome do bot registrado (ex.: main, standby).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)
    registry = load_registry(settings)
    config = registry.get(args.bot)
    asyncio.run(run_bot(config))


if __name__ == "__main__":
    main()

