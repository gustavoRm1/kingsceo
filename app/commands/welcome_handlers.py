from __future__ import annotations

from typing import Sequence

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatMemberStatus, ChatType
from telegram.ext import Application, ChatMemberHandler, ContextTypes

from app.core.logging import get_logger
from app.core.utils import weighted_choice
from app.domain import models
from app.domain.repositories import CategoryRepository, GroupRepository, MediaRepositoryMapRepository
from app.domain.services import CategoryService, GroupService, MediaRepositoryService
from app.infrastructure.db.base import get_session

logger = get_logger(__name__)


def _choose_text(category: models.CategoryDTO) -> str | None:
    if category.welcome_text:
        return category.welcome_text
    copies: Sequence[models.CopyDTO] | None = category.copies
    if not copies:
        return None
    if category.use_random_copy and copies:
        choice = weighted_choice([(copy, copy.weight or 1) for copy in copies])
        if choice:
            return choice.text
    return copies[0].text


def _choose_media(
    category: models.CategoryDTO,
    *,
    has_repository: bool,
) -> tuple[str, str, str | None] | None:
    """
    Returns (media_type, file_id, caption)
    """
    if not has_repository and not category.welcome_media_id:
        return None

    medias: Sequence[models.MediaDTO] | None = category.media_items
    if category.welcome_media_id:
        if medias:
            for media in medias:
                if media.file_id == category.welcome_media_id:
                    return media.media_type, media.file_id, media.caption
        # fallback assume photo if not found
        return "photo", category.welcome_media_id, None

    if not medias:
        return None

    selected: models.MediaDTO | None
    if category.use_random_media:
        selected = weighted_choice([(media, media.weight or 1) for media in medias])
    else:
        selected = medias[0]

    if not selected:
        return None
    return selected.media_type, selected.file_id, selected.caption


def _build_buttons(category: models.CategoryDTO) -> InlineKeyboardMarkup | None:
    data = category.welcome_buttons or []
    if not data:
        return None
    rows: list[list[InlineKeyboardButton]] = []
    for entry in data:
        label = entry.get("label")
        url = entry.get("url")
        if label and url:
            rows.append([InlineKeyboardButton(label, url=url)])
    if not rows:
        return None
    return InlineKeyboardMarkup(rows)


async def welcome_chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_member = update.chat_member
    chat = update.effective_chat
    if not chat_member or not chat:
        return

    if chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        return

    new_status = chat_member.new_chat_member.status
    old_status = chat_member.old_chat_member.status
    if new_status not in {ChatMemberStatus.MEMBER}:
        return
    if old_status == new_status:
        return

    user = chat_member.new_chat_member.user
    if not user or user.is_bot:
        return

    async with get_session() as session:
        group_service = GroupService(GroupRepository(session))
        group = await group_service.get_by_chat(chat.id)
        if not group or group.category_id is None:
            return

        category_service = CategoryService(CategoryRepository(session))
        repo_service = MediaRepositoryService(
            MediaRepositoryMapRepository(session), CategoryRepository(session)
        )
        try:
            category = await category_service.get_category_by_id(group.category_id)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("welcome.category_missing", chat_id=chat.id, error=str(exc))
            return
        repositories = await repo_service.list_by_category(category.id)

    if category.welcome_mode == "none":
        return

    has_repo = bool(repositories)
    text = _choose_text(category)
    media_payload = _choose_media(category, has_repository=has_repo)
    buttons = _build_buttons(category)

    # Compose greeting mentioning the user
    base_greeting = f"Bem-vindo, {user.full_name}!"
    if text:
        text = f"{base_greeting}\n\n{text}"
    else:
        text = base_greeting if category.welcome_mode in {"all", "text", "buttons"} else None

    bot = context.bot
    try:
        if category.welcome_mode in {"all", "media"} and media_payload:
            media_type, file_id, caption = media_payload
            caption_text = text or caption or ""
            if media_type == "photo":
                await bot.send_photo(
                    chat_id=chat.id,
                    photo=file_id,
                    caption=caption_text or None,
                    has_spoiler=category.use_spoiler_media,
                    reply_markup=buttons,
                )
            elif media_type == "video":
                await bot.send_video(
                    chat_id=chat.id,
                    video=file_id,
                    caption=caption_text or None,
                    has_spoiler=category.use_spoiler_media,
                    reply_markup=buttons,
                )
            elif media_type == "document":
                await bot.send_document(
                    chat_id=chat.id,
                    document=file_id,
                    caption=caption_text or None,
                    reply_markup=buttons,
                )
            elif media_type == "animation":
                await bot.send_animation(
                    chat_id=chat.id,
                    animation=file_id,
                    caption=caption_text or None,
                    has_spoiler=category.use_spoiler_media,
                    reply_markup=buttons,
                )
            else:
                logger.warning(
                    "welcome.unsupported_media",
                    chat_id=chat.id,
                    media_type=media_type,
                )
            if category.welcome_mode == "all" and text and not media_payload:
                await bot.send_message(chat_id=chat.id, text=text, reply_markup=buttons)
            return

        if category.welcome_mode in {"all", "text"} and text:
            await bot.send_message(chat_id=chat.id, text=text, reply_markup=buttons)
            return

        if category.welcome_mode in {"all", "buttons"} and buttons:
            await bot.send_message(
                chat_id=chat.id,
                text=text or base_greeting,
                reply_markup=buttons,
            )
            return
    except Exception as exc:  # pragma: no cover - log but continue
        logger.exception("welcome.send_error", chat_id=chat.id, error=str(exc))


def register_welcome_handlers(application: Application) -> None:
    application.add_handler(ChatMemberHandler(welcome_chat_member_handler))

