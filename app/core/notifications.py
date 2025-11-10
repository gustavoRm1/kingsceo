from __future__ import annotations

from typing import Iterable

from telegram import Bot

from app.core.logging import get_logger

logger = get_logger(__name__)


class AdminNotifier:
    """Utility to send alerts to configured administrators."""

    def __init__(self, bot: Bot, admin_ids: Iterable[int]):
        self._bot = bot
        self._admin_ids = [admin_id for admin_id in admin_ids if admin_id]

    def has_recipients(self) -> bool:
        return bool(self._admin_ids)

    async def send(self, message: str, *, level: str = "INFO") -> None:
        if not self.has_recipients():
            logger.warning("notifier.no_admins", message=message, level=level)
            return
        payload = f"[{level}] {message}"
        for admin_id in self._admin_ids:
            try:
                await self._bot.send_message(chat_id=admin_id, text=payload)
            except Exception as exc:  # pragma: no cover - best effort
                logger.warning("notifier.failed", admin_id=admin_id, error=str(exc), level=level)

