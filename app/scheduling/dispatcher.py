from __future__ import annotations

import asyncio

from cachetools import TTLCache
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatMemberStatus
from telegram.error import Forbidden
from telegram.ext import Application

from app.core.logging import get_logger
from app.core.notifications import AdminNotifier
from app.domain.models import Payload
from app.domain.repositories import CategoryRepository, GroupRepository, MediaRepositoryMapRepository
from app.domain.services import CategoryService, GroupService, MediaRepositoryService
from app.infrastructure.db.base import get_session

logger = get_logger(__name__)


class DispatchEngine:
    def __init__(
        self,
        application: Application,
        *,
        admin_cache_ttl: int = 300,
        notifier: AdminNotifier | None = None,
    ) -> None:
        self.application = application
        self._admin_cache = TTLCache(maxsize=512, ttl=admin_cache_ttl)
        self._notifier = notifier

    async def dispatch_category(
        self,
        slug: str,
        *,
        allow_media: bool = True,
        allow_copy: bool = True,
        allow_buttons: bool = True,
    ) -> None:
        async with get_session() as session:
            category_service = CategoryService(CategoryRepository(session))
            group_service = GroupService(GroupRepository(session))
            repo_service = MediaRepositoryService(
                MediaRepositoryMapRepository(session), CategoryRepository(session)
            )
            category = await category_service.get_category_by_slug(slug)
            has_repo = bool(await repo_service.list_by_category(category.id))
            payload = await category_service.random_payload(
                category.id,
                allow_media=allow_media and has_repo,
                allow_copy=allow_copy,
                allow_buttons=allow_buttons,
            )
            groups = await group_service.list_by_category(category.id)

        results = await asyncio.gather(
            *[self._send_payload(group.telegram_chat_id, payload) for group in groups],
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                logger.error("dispatch.category_error", slug=slug, error=str(result))
                if self._notifier and self._notifier.has_recipients():
                    await self._notifier.send(
                        f"Falha ao enviar categoria {slug}: {result}", level="ERROR"
                    )

    async def _send_payload(self, chat_id: int, payload: Payload) -> None:
        if not await self._ensure_admin(chat_id):
            logger.warning("dispatch.skip_not_admin", chat_id=chat_id)
            return

        markup = None
        if payload.buttons:
            keyboard = [
                [InlineKeyboardButton(button.label, url=button.url)]
                for button in payload.buttons
            ]
            markup = InlineKeyboardMarkup(keyboard)

        try:
            if payload.media:
                caption = payload.media.caption or (payload.message.text if payload.message else None)
                logger.info(
                    "dispatch.media",
                    chat_id=chat_id,
                    media_type=payload.media.media_type,
                    has_spoiler=payload.media_spoiler,
                    media_id=payload.media.id if hasattr(payload.media, "id") else None,
                )
                if payload.media.media_type == "photo":
                    await self.application.bot.send_photo(
                        chat_id=chat_id,
                        photo=payload.media.file_id,
                        caption=caption,
                        has_spoiler=payload.media_spoiler,
                        reply_markup=markup,
                    )
                elif payload.media.media_type == "video":
                    await self.application.bot.send_video(
                        chat_id=chat_id,
                        video=payload.media.file_id,
                        caption=caption,
                        has_spoiler=payload.media_spoiler,
                        reply_markup=markup,
                    )
                elif payload.media.media_type == "document":
                    await self.application.bot.send_document(
                        chat_id=chat_id,
                        document=payload.media.file_id,
                        caption=caption,
                        reply_markup=markup,
                    )
                elif payload.media.media_type == "animation":
                    await self.application.bot.send_animation(
                        chat_id=chat_id,
                        animation=payload.media.file_id,
                        caption=caption,
                        has_spoiler=payload.media_spoiler,
                        reply_markup=markup,
                    )
                else:
                    logger.warning("dispatch.unsupported_media", chat_id=chat_id, media_type=payload.media.media_type)
                    return
                return

            if payload.message:
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text=payload.message.text,
                    reply_markup=markup,
                )
                return

            if payload.buttons:
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text="Escolha uma opcao:",
                    reply_markup=markup,
                )
        except Forbidden:
            logger.warning("dispatch.forbidden", chat_id=chat_id)
        except Exception as exc:
            logger.error("dispatch.error", chat_id=chat_id, error=str(exc))

    async def _ensure_admin(self, chat_id: int) -> bool:
        if chat_id in self._admin_cache:
            return True
        try:
            member = await self.application.bot.get_chat_member(chat_id, self.application.bot.id)
        except Forbidden:
            return False
        if member.status not in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}:
            return False
        self._admin_cache[chat_id] = True
        return True

