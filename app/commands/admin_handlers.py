from __future__ import annotations

import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatMemberStatus, ChatType
from telegram.ext import Application, ChatMemberHandler, CommandHandler, ContextTypes, filters

from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.domain.repositories import CategoryRepository, GroupRepository, MediaRepositoryMapRepository
from app.domain.services import CategoryService, GroupService, MediaRepositoryService
from app.infrastructure.db.base import get_session


def _is_admin(update: Update) -> bool:
    settings = get_settings()
    if not update.effective_user:
        return False
    return update.effective_user.id in settings.admin_ids


def _private_or_admin(update: Update) -> bool:
    chat = update.effective_chat
    if not chat:
        return False
    return chat.type == ChatType.PRIVATE and _is_admin(update)


async def _require_admin(update: Update) -> bool:
    if not _is_admin(update):
        if update.effective_chat and update.effective_chat.type == ChatType.PRIVATE:
            await update.effective_chat.send_message("Acesso negado.")
        return False
    return True


async def cmd_setcategoria(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat:
        return

    # Grupo: vincular categoria existente ao grupo
    if chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}:
        if not context.args:
            await message.reply_text("Uso: /setcategoria <slug_categoria>")
            return
        slug = context.args[0]

        user = update.effective_user
        sender_chat = message.sender_chat
        is_global_admin = _is_admin(update)
        user_is_chat_admin = False
        if sender_chat and sender_chat.id == chat.id:
            user_is_chat_admin = True
        elif user:
            try:
                admins = await context.bot.get_chat_administrators(chat.id)
            except Exception:
                admins = []
            user_is_chat_admin = any(admin.user.id == user.id for admin in admins)

        if not (is_global_admin or user_is_chat_admin):
            await message.reply_text("Somente administradores podem vincular uma categoria ao grupo.")
            return

        bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
        if bot_member.status not in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}:
            await message.reply_text("O bot precisa ser administrador do grupo para enviar conteúdos.")
            return

        async with get_session() as session:
            category_service = CategoryService(CategoryRepository(session))
            group_service = GroupService(GroupRepository(session))
            try:
                category = await category_service.get_category_by_slug(slug)
            except NotFoundError:
                await message.reply_text(f"Categoria '{slug}' não encontrada. Crie-a antes em privado.")
                return
            group = await group_service.upsert_group(
                chat_id=chat.id,
                title=chat.title,
                category_id=category.id,
            )
        await message.reply_text(
            f"Grupo vinculado à categoria `{category.slug}`.\n"
            f"Nome da categoria: {category.name}\n"
            f"Chat ID: `{group.telegram_chat_id}`",
            parse_mode="Markdown",
        )
        return

    # Privado: criar nova categoria
    if not await _require_admin(update):
        return
    if not context.args:
        await message.reply_text("Uso: /setcategoria <nome>")
        return
    name = " ".join(context.args)
    async with get_session() as session:
        service = CategoryService(CategoryRepository(session))
        category = await service.create_category(name)
    await message.reply_text(
        f"Categoria criada: {category.name} (slug={category.slug}).\n"
        "Use este slug para vincular grupos com /setcategoria <slug> dentro do grupo.",
    )


async def _get_category_id(service: CategoryService, slug: str) -> int:
    category = await service.get_category_by_slug(slug)
    return category.id


async def cmd_addcopy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return
    if not await _require_admin(update):
        return
    if not context.args:
        await message.reply_text("Uso: /addcopy <slug_categoria> [peso]")
        return
    slug = context.args[0]
    weight = int(context.args[1]) if len(context.args) > 1 else 1
    text_source = (
        message.reply_to_message.text
        if message.reply_to_message
        else " ".join(context.args[1:])
    )
    if not text_source:
        await message.reply_text("Forneca o texto na mesma mensagem ou responda a um texto.")
        return
    async with get_session() as session:
        service = CategoryService(CategoryRepository(session))
        category_id = await _get_category_id(service, slug)
        copy = await service.add_copy(category_id, text=text_source, weight=weight)
    await message.reply_text(f"Copy adicionada para {slug} (id={copy.id}).")


_URL_PATTERN = re.compile(r"^https?://")


async def cmd_setbotao(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return
    if not await _require_admin(update):
        return
    if len(context.args) < 3:
        await message.reply_text("Uso: /setbotao <slug_categoria> <label> <url> [peso]")
        return
    slug = context.args[0]
    label = context.args[1]
    url = context.args[2]
    if not _URL_PATTERN.match(url):
        await message.reply_text("URL invalida. Use http:// ou https://")
        return
    weight = int(context.args[3]) if len(context.args) > 3 else 1
    async with get_session() as session:
        service = CategoryService(CategoryRepository(session))
        category_id = await _get_category_id(service, slug)
        button = await service.add_button(category_id, label=label, url=url, weight=weight)
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(button.label, url=button.url)]])
    await message.reply_text(
        f"Botao adicionado para {slug} (id={button.id}).",
        reply_markup=keyboard,
    )


async def cmd_setboasvindas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return
    if not await _require_admin(update):
        return
    if not context.args:
        await message.reply_text("Uso: /setboasvindas <slug_categoria> mode=<all|text|media|buttons|none>")
        return
    slug = context.args[0]
    mode = "all"
    for arg in context.args[1:]:
        if arg.startswith("mode="):
            mode = arg.split("=", 1)[1]
    source = message.reply_to_message or message
    media_id = None
    if source.photo:
        media_id = source.photo[-1].file_id
    elif source.video:
        media_id = source.video.file_id
    elif source.animation:
        media_id = source.animation.file_id
    text = source.text or source.caption
    buttons = None
    if source.reply_markup and source.reply_markup.inline_keyboard:
        buttons = [
            {"label": btn.text, "url": btn.url}
            for row in source.reply_markup.inline_keyboard
            for btn in row
            if btn.url
        ]
    copy_random = any(arg.lower() == "copy=random" for arg in context.args[1:])
    media_random = any(arg.lower() == "media=random" for arg in context.args[1:])
    async with get_session() as session:
        service = CategoryService(CategoryRepository(session))
        category_id = await _get_category_id(service, slug)
        await service.update_welcome(
            category_id,
            mode=mode,
            text=text,
            media_id=media_id,
            buttons=buttons,
            use_random_copy=copy_random,
            use_random_media=media_random,
        )
    toggles = []
    if copy_random:
        toggles.append("copy aleatória")
    if media_random:
        toggles.append("mídia aleatória")
    toggle_text = " | ".join(toggles) if toggles else "uso padrão (primeiro item)"
    await message.reply_text(f"Boas-vindas configuradas para {slug} (modo={mode}). {toggle_text}.")


async def cmd_setrepositorio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat:
        return
    if chat.type not in {ChatType.SUPERGROUP, ChatType.GROUP}:
        await message.reply_text("Execute este comando dentro do grupo ou supergrupo que será o repositório.")
        return
    if not context.args:
        await message.reply_text("Uso: /setrepositorio <slug_categoria>")
        return
    slug = context.args[0]
    user = update.effective_user
    sender_chat = message.sender_chat
    is_global_admin = _is_admin(update)
    user_is_chat_admin = False
    if sender_chat and sender_chat.id == chat.id:
        user_is_chat_admin = True
    elif user:
        try:
            admins = await context.bot.get_chat_administrators(chat.id)
        except Exception:
            admins = []
        user_is_chat_admin = any(admin.user.id == user.id for admin in admins)
    if not (is_global_admin or user_is_chat_admin):
        await message.reply_text("Somente administradores podem definir o repositório.")
        return
    bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
    if bot_member.status not in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}:
        await message.reply_text("O bot precisa ser administrador do grupo para cadastrar mídias automaticamente.")
        return
    async with get_session() as session:
        category_service = CategoryService(CategoryRepository(session))
        repo_service = MediaRepositoryService(MediaRepositoryMapRepository(session), CategoryRepository(session))
        try:
            mapping = await repo_service.assign_repository(chat_id=chat.id, category_slug=slug)
            category = await category_service.get_category_by_slug(slug)
        except NotFoundError as exc:
            await message.reply_text(str(exc))
            return
    await message.reply_text(
        f"Grupo configurado como repositório da categoria `{category.slug}`.\n"
        f"Nome: {category.name}\nChat ID: `{mapping.chat_id}`",
        parse_mode="Markdown",
    )


async def my_chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_member_update = update.my_chat_member
    chat = update.effective_chat
    if not chat_member_update or not chat:
        return

    if chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        return

    new_status = chat_member_update.new_chat_member.status
    if new_status not in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}:
        return

    old_status = chat_member_update.old_chat_member.status if chat_member_update.old_chat_member else None
    if old_status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}:
        return

    async with get_session() as session:
        group_service = GroupService(GroupRepository(session))
        await group_service.upsert_group(chat_id=chat.id, title=chat.title, category_id=None)


def register_admin_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("setcategoria", cmd_setcategoria))
    application.add_handler(CommandHandler("addcopy", cmd_addcopy, filters=filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("setbotao", cmd_setbotao, filters=filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("setboasvindas", cmd_setboasvindas, filters=filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("setrepositorio", cmd_setrepositorio))
    application.add_handler(ChatMemberHandler(my_chat_member_handler))

