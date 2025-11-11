from __future__ import annotations

import contextlib

from telegram import Update
from telegram.constants import ChatMemberStatus, ChatType
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from app.core.logging import get_logger
from app.domain.repositories import CategoryRepository, MediaRepositoryMapRepository
from app.domain.services import CategoryService, MediaRepositoryService
from app.infrastructure.db.base import get_session

logger = get_logger(__name__)


def _extract_media(update: Update):
    message = update.effective_message
    if not message:
        return None

    if message.photo:
        return "photo", message.photo[-1].file_id, message.caption
    if message.video:
        return "video", message.video.file_id, message.caption
    if message.document:
        return "document", message.document.file_id, message.caption
    if message.animation:
        return "animation", message.animation.file_id, message.caption
    return None


async def repository_media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    message = update.effective_message
    user = update.effective_user
    sender_chat = message.sender_chat

    if not chat or not message:
        return
    if chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        return

    media_payload = _extract_media(update)
    if not media_payload:
        return

    async with get_session() as session:
        mapping_repo = MediaRepositoryMapRepository(session)
        category_repo = CategoryRepository(session)
        repo_service = MediaRepositoryService(mapping_repo, category_repo)
        mapping = await repo_service.get_mapping(chat.id)
        if not mapping:
            return
        category_service = CategoryService(category_repo)
        category = await category_service.get_category_by_id(mapping.category_id)

        if user:
            member = await context.bot.get_chat_member(chat.id, user.id)
            if member.status not in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}:
                logger.info(
                    "repository.media.skip_not_admin",
                    chat_id=chat.id,
                    category=category.slug,
                    user_id=user.id,
                )
                return
        elif sender_chat and sender_chat.id == chat.id:
            # Anonymous owner/admin posting as the group
            pass
        else:
            logger.info(
                "repository.media.skip_no_sender_admin",
                chat_id=chat.id,
                category=category.slug,
            )
            return

        media_type, file_id, caption = media_payload
        exists = await category_service.media_exists(category.id, file_id)
        if exists:
            logger.info(
                "repository.media.duplicate",
                chat_id=chat.id,
                category=category.slug,
                user_id=user.id if user else None,
            )
            return
        media_dto = await category_service.add_media(
            category.id,
            media_type=media_type,
            file_id=file_id,
            caption=caption,
            weight=1,
        )
        logger.info(
            "repository.media.saved",
            chat_id=chat.id,
            category=category.slug,
            media_type=media_type,
            media_id=media_dto.id,
        )
        await message.reply_text(
            f"✅ Mídia registrada para a categoria `{category.slug}`.",
            parse_mode="Markdown",
            quote=True,
        )


async def service_cleanup_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    message = update.effective_message
    if not chat or not message:
        return
    async with get_session() as session:
        repo_service = MediaRepositoryService(MediaRepositoryMapRepository(session), CategoryRepository(session))
        mapping = await repo_service.get_mapping(chat.id)
    if mapping and mapping.clean_service_messages:
        with contextlib.suppress(Exception):
            await context.bot.delete_message(chat.id, message.message_id)


def register_repository_handlers(application: Application) -> None:
    application.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS
            & (filters.PHOTO | filters.VIDEO | filters.Document.ALL | filters.ANIMATION),
            repository_media_handler,
        )
    )
    application.add_handler(
        MessageHandler(filters.StatusUpdate.ALL, service_cleanup_handler)
    )


