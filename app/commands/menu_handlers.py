from __future__ import annotations

import math
from typing import Final

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.error import BadRequest

from app.core.config import get_settings
from app.core.exceptions import AlreadyExistsError, NotFoundError
from app.core.utils import weighted_choice
from app.domain import models
from app.domain.repositories import CategoryRepository, GroupRepository, MediaRepositoryMapRepository
from app.domain.services import CategoryService, GroupService, MediaRepositoryService
from app.infrastructure.db.base import get_session

MENU_PREFIX: Final = "menu:"
STATE_KEY: Final = "menu_pending"
WELCOME_STATE_KEY: Final = "welcome_state"
WELCOME_PANEL_CACHE_KEY: Final = "welcome_panels"
GROUPS_PAGE_SIZE: Final = 8
GROUP_CATEGORY_PAGE_SIZE: Final = 8


def _build_main_menu() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("Adicione-me a um grupo", callback_data=f"{MENU_PREFIX}add_to_group")],
        [InlineKeyboardButton("Criar categoria (/setcategoria)", callback_data=f"{MENU_PREFIX}setcategoria")],
        [InlineKeyboardButton("Visão de categorias", callback_data=f"{MENU_PREFIX}viewcats")],
        [InlineKeyboardButton("Gerenciar grupos", callback_data=f"{MENU_PREFIX}groups")],
        [InlineKeyboardButton("Adicionar copy (/addcopy)", callback_data=f"{MENU_PREFIX}addcopy")],
        [InlineKeyboardButton("Adicionar botão (/setbotao)", callback_data=f"{MENU_PREFIX}setbotao")],
        [InlineKeyboardButton("Configurar repositório (/setrepositorio)", callback_data=f"{MENU_PREFIX}setrepos")],
    ]
    return InlineKeyboardMarkup(buttons)


def _init_welcome_state(context: ContextTypes.DEFAULT_TYPE, category: models.CategoryDTO) -> None:
    context.user_data[WELCOME_STATE_KEY] = {
        "action": "welcome",
        "category_id": category.id,
        "category_slug": category.slug,
        "category_name": category.name,
        "step": "mode",
        "mode": None,
        "copy_strategy": None,
        "copy_text": None,
        "media_strategy": None,
        "media_file_id": None,
        "buttons_selected": set(),
    }


def _get_welcome_state(context: ContextTypes.DEFAULT_TYPE) -> dict | None:
    return context.user_data.get(WELCOME_STATE_KEY)


def _clear_welcome_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(WELCOME_STATE_KEY, None)


async def _prompt_welcome_mode(query, category_name: str) -> None:
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Texto + mídia + botões", callback_data=f"{MENU_PREFIX}welcome_mode:all"),
            ],
            [
                InlineKeyboardButton("Somente texto", callback_data=f"{MENU_PREFIX}welcome_mode:text"),
                InlineKeyboardButton("Somente mídia", callback_data=f"{MENU_PREFIX}welcome_mode:media"),
            ],
            [
                InlineKeyboardButton("Somente botões", callback_data=f"{MENU_PREFIX}welcome_mode:buttons"),
                InlineKeyboardButton("Desativar boas-vindas", callback_data=f"{MENU_PREFIX}welcome_mode:none"),
            ],
        ]
    )
    await query.edit_message_text(
        f"Categoria selecionada: *{category_name}*\n"
        "Escolha o modo de boas-vindas:",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


async def _prompt_welcome_copy_options(target, has_copies: bool, *, edit: bool = True) -> None:
    rows = [
        [InlineKeyboardButton("Copy aleatória", callback_data=f"{MENU_PREFIX}welcome_copy:random")],
        [InlineKeyboardButton("Sem copy", callback_data=f"{MENU_PREFIX}welcome_copy:none")],
    ]
    if has_copies:
        rows.insert(0, [InlineKeyboardButton("Selecionar copy existente", callback_data=f"{MENU_PREFIX}welcome_copy:select")])
    rows.append([InlineKeyboardButton("Digitar copy personalizada", callback_data=f"{MENU_PREFIX}welcome_copy:manual")])
    text = "Como deseja configurar o texto de boas-vindas?"
    markup = InlineKeyboardMarkup(rows)
    if edit:
        await target.edit_message_text(text, reply_markup=markup)
    else:
        await target.reply_text(text, reply_markup=markup)


async def _prompt_welcome_copy_selection(target, copies, *, edit: bool = True) -> None:
    rows = []
    for copy in copies:
        label = (copy.text[:40] + ("..." if len(copy.text) > 40 else "")).replace("`", "´")
        rows.append(
            [InlineKeyboardButton(label, callback_data=f"{MENU_PREFIX}welcome_copy_select:{copy.id}")]
        )
    rows.append([InlineKeyboardButton("⬅️ Voltar", callback_data=f"{MENU_PREFIX}welcome_copy")])
    text = "Selecione a copy que será usada nas boas-vindas:"
    markup = InlineKeyboardMarkup(rows)
    if edit:
        await target.edit_message_text(text, reply_markup=markup)
    else:
        await target.reply_text(text, reply_markup=markup)


async def _prompt_welcome_media_options(target, has_media: bool, *, edit: bool = True) -> None:
    rows = [
        [InlineKeyboardButton("Mídia aleatória", callback_data=f"{MENU_PREFIX}welcome_media:random")],
        [InlineKeyboardButton("Sem mídia", callback_data=f"{MENU_PREFIX}welcome_media:none")],
    ]
    if has_media:
        rows.insert(0, [InlineKeyboardButton("Selecionar mídia cadastrada", callback_data=f"{MENU_PREFIX}welcome_media:select")])
    rows.append([InlineKeyboardButton("Informar file_id manualmente", callback_data=f"{MENU_PREFIX}welcome_media:manual")])
    text = "Escolha a mídia para a saudação:"
    markup = InlineKeyboardMarkup(rows)
    if edit:
        await target.edit_message_text(text, reply_markup=markup)
    else:
        await target.reply_text(text, reply_markup=markup)


async def _prompt_welcome_media_selection(target, medias, *, edit: bool = True) -> None:
    rows = []
    for media in medias:
        caption = (media.caption or "(sem legenda)").replace("`", "´")
        caption = caption[:40] + ("..." if len(caption) > 40 else "")
        rows.append(
            [InlineKeyboardButton(f"{media.media_type} • {caption}", callback_data=f"{MENU_PREFIX}welcome_media_select:{media.id}")]
        )
    rows.append([InlineKeyboardButton("⬅️ Voltar", callback_data=f"{MENU_PREFIX}welcome_media")])
    text = "Selecione a mídia para as boas-vindas:"
    markup = InlineKeyboardMarkup(rows)
    if edit:
        await target.edit_message_text(text, reply_markup=markup)
    else:
        await target.reply_text(text, reply_markup=markup)


async def _prompt_welcome_buttons(target, state, category_buttons, *, edit: bool = True) -> None:
    selected = state["buttons_selected"]
    rows = []
    for button in category_buttons:
        prefix = "✅" if button.id in selected else "▫️"
        rows.append(
            [
                InlineKeyboardButton(
                    f"{prefix} {button.label}",
                    callback_data=f"{MENU_PREFIX}welcome_btn_toggle:{button.id}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton("Selecionar todos", callback_data=f"{MENU_PREFIX}welcome_btn_all"),
            InlineKeyboardButton("Limpar", callback_data=f"{MENU_PREFIX}welcome_btn_clear"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton("Concluir", callback_data=f"{MENU_PREFIX}welcome_btn_done"),
        ]
    )
    text = "Marque os botões que deseja incluir na mensagem de boas-vindas:"
    markup = InlineKeyboardMarkup(rows)
    if edit:
        await target.edit_message_text(text, reply_markup=markup)
    else:
        await target.reply_text(text, reply_markup=markup)


async def _show_welcome_summary(target, context, category, state, *, edit: bool = True) -> None:
    copy_strategy = state.get("copy_strategy")
    media_strategy = state.get("media_strategy")
    buttons_selected = state.get("buttons_selected", set())

    copy_desc = "Não enviar copy"
    if copy_strategy == "random":
        copy_desc = "Copy aleatória (iterando entre as cadastradas)"
    elif copy_strategy == "selected":
        preview = (state.get("copy_text") or "").replace("`", "´")
        copy_desc = f"Copy fixa (primeiras linhas):\n{preview[:120]}"
    elif copy_strategy == "manual":
        preview = (state.get("copy_text") or "").replace("`", "´")
        copy_desc = f"Copy personalizada:\n{preview[:120]}"

    media_desc = "Sem mídia"
    if media_strategy == "random":
        media_desc = "Mídia aleatória (entre mídias cadastradas/repositório)"
    elif media_strategy == "selected":
        media_desc = f"Mídia fixa (file_id): `{state.get('media_file_id')}`"
    elif media_strategy == "manual":
        media_desc = f"Mídia personalizada (file_id): `{state.get('media_file_id')}`"

    buttons_desc = "Nenhum botão"
    if buttons_selected:
        lines = []
        button_map = {btn.id: btn for btn in category.buttons}
        for button_id in buttons_selected:
            button = button_map.get(button_id)
            if button:
                lines.append(f"- {button.label.replace('`', '´')} → {button.url}")
        if lines:
            buttons_desc = "\n".join(lines)

    summary = (
        f"*Resumo das boas-vindas — {category.name}*\n\n"
        f"*Modo:* {state.get('mode')}\n\n"
        f"*Copy:* {copy_desc}\n\n"
        f"*Mídia:* {media_desc}\n\n"
        f"*Botões:*\n{buttons_desc}"
    )
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Confirmar", callback_data=f"{MENU_PREFIX}welcome_confirm")],
            [InlineKeyboardButton("↩️ Recomeçar", callback_data=f"{MENU_PREFIX}welcome_restart")],
            [InlineKeyboardButton("🏠 Menu principal", callback_data=f"{MENU_PREFIX}back")],
        ]
    )
    if edit:
        await target.edit_message_text(
            summary,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
    else:
        await target.reply_text(
            summary,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )


async def _render_category_detail(update: Update, query, context: ContextTypes.DEFAULT_TYPE, category: models.CategoryDTO) -> None:
    async with get_session() as session:
        repo_service = MediaRepositoryService(MediaRepositoryMapRepository(session), CategoryRepository(session))
        repositories = await repo_service.list_by_category(category.id)

    copy_count = len(category.copies or [])
    button_count = len(category.buttons or [])
    media_count = len(category.media_items or [])
    copy_mode_label = "🔁 aleatória" if category.use_random_copy else "➡️ sequencial"
    media_mode_label = "🔁 aleatória" if category.use_random_media else "➡️ sequencial"
    copies_preview = ""
    for entry in (category.copies or [])[:3]:
        snippet = entry.text[:120].replace("`", "´")
        copies_preview += f"\n  • {snippet}"
        if len(entry.text) > 120:
            copies_preview += "..."
    if not copies_preview:
        copies_preview = "\n  • Nenhuma copy cadastrada"
    buttons_preview = ""
    for entry in (category.buttons or [])[:3]:
        buttons_preview += f"\n  • {entry.label} → {entry.url}"
    if not buttons_preview:
        buttons_preview = "\n  • Nenhum botão cadastrado"
    repo_preview = ""
    repo_button_rows: list[list[InlineKeyboardButton]] = []
    if repositories:
        for repo in repositories[:5]:
            status_label = "ON" if repo.clean_service_messages else "OFF"
            repo_preview += f"\n  • Chat ID: `{repo.chat_id}` (serviços: {status_label})"
            if _is_admin(update):
                repo_button_rows.append(
                    [
                        InlineKeyboardButton(
                            f"🧹 Serviços {status_label}",
                            callback_data=f"{MENU_PREFIX}cat_repo_toggle:{repo.id}",
                        )
                    ]
                )
        if len(repositories) > 5:
            repo_preview += f"\n  • ... +{len(repositories)-5} outros"
    else:
        repo_preview = "\n  • Nenhum repositório ativo"
    detail_message = (
        f"*{category.name}* (`{category.slug}`)\n"
        f"- Mídias cadastradas: {media_count} ({media_mode_label})\n"
        f"- Copies: {copy_count} ({copy_mode_label}){copies_preview}\n"
        f"- Botões: {button_count}{buttons_preview}\n"
        f"- Repositórios:{repo_preview}\n"
    )
    rows = [
        [InlineKeyboardButton("🎲 Copy aleatória", callback_data=f"{MENU_PREFIX}randcopy:{category.id}")],
        [InlineKeyboardButton("🎲 Mídia aleatória", callback_data=f"{MENU_PREFIX}randmedia:{category.id}")],
    ]
    if _is_admin(update):
        spoiler_label = "🎭 Spoiler nas mídias: ON" if category.use_spoiler_media else "🎭 Spoiler nas mídias: OFF"
        rows.append([InlineKeyboardButton(spoiler_label, callback_data=f"{MENU_PREFIX}cat_spoiler:{category.id}")])
        rows.append(
            [
                InlineKeyboardButton("🆕 Criar copy", callback_data=f"{MENU_PREFIX}cat_create_copy:{category.id}"),
                InlineKeyboardButton("✏️ Editar copy", callback_data=f"{MENU_PREFIX}cat_edit_copy:{category.id}"),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton("🆕 Criar botão", callback_data=f"{MENU_PREFIX}cat_create_button:{category.id}"),
                InlineKeyboardButton("✏️ Editar botões", callback_data=f"{MENU_PREFIX}cat_edit_button:{category.id}"),
            ]
        )
        rows.append([InlineKeyboardButton("⚙️ Configurar boas-vindas", callback_data=f"{MENU_PREFIX}cat_welcome:{category.id}")])
        rows.extend(repo_button_rows)
    rows.append([InlineKeyboardButton("⬅️ Voltar às categorias", callback_data=f"{MENU_PREFIX}viewcats")])
    rows.append([InlineKeyboardButton("🏠 Menu principal", callback_data=f"{MENU_PREFIX}back")])
    keyboard = InlineKeyboardMarkup(rows)
    await query.edit_message_text(
        detail_message,
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


def _store_welcome_panel(context: ContextTypes.DEFAULT_TYPE, *, category_id: int, chat_id: int, message_id: int) -> None:
    panels = context.user_data.setdefault(WELCOME_PANEL_CACHE_KEY, {})
    panels[category_id] = {"chat_id": chat_id, "message_id": message_id}


def _build_welcome_panel_text(category: models.CategoryDTO) -> str:
    if category.use_random_copy:
        copy_desc = "Copy aleatória"
    elif category.welcome_text:
        truncated = category.welcome_text[:120]
        if len(category.welcome_text) > 120:
            truncated += "..."
        copy_desc = truncated.replace("`", "´")
    else:
        copy_desc = "Nenhuma copy definida"

    if category.use_random_media:
        media_desc = "Mídia aleatória"
    elif category.welcome_media_id:
        media_desc = f"Mídia fixa (`{category.welcome_media_id}`)"
    else:
        media_desc = "Mídia desativada"

    buttons_data = category.welcome_buttons or []
    if isinstance(buttons_data, list):
        buttons_count = len(buttons_data)
    elif isinstance(buttons_data, dict):
        buttons_count = len(buttons_data)
    else:
        buttons_count = 0

    return (
        f"*Configurar boas-vindas*\n"
        f"Categoria: *{category.name}* (`{category.slug}`)\n"
        f"- Modo atual: `{category.welcome_mode}`\n"
        f"- Copy: {copy_desc}\n"
        f"- Mídia: {media_desc}\n"
        f"- Botões selecionados: {buttons_count}"
    )


def _build_welcome_panel_keyboard(category: models.CategoryDTO) -> InlineKeyboardMarkup:
    media_toggle_label = "🎞 Mídia aleatória: ON" if category.use_random_media else "🎞 Mídia aleatória: OFF"
    rows = [
        [
            InlineKeyboardButton("🆕 Criar copy", callback_data=f"{MENU_PREFIX}welcome_create_copy:{category.id}"),
            InlineKeyboardButton("✏️ Editar copy", callback_data=f"{MENU_PREFIX}welcome_edit_copy:{category.id}"),
        ],
        [
            InlineKeyboardButton("🗑️ Excluir copy", callback_data=f"{MENU_PREFIX}welcome_delete_copy:{category.id}"),
            InlineKeyboardButton("🗑️ Excluir botão", callback_data=f"{MENU_PREFIX}welcome_delete_button:{category.id}"),
        ],
        [
            InlineKeyboardButton("🆕 Criar botão", callback_data=f"{MENU_PREFIX}welcome_create_button:{category.id}"),
            InlineKeyboardButton("✏️ Editar botões", callback_data=f"{MENU_PREFIX}welcome_edit_button:{category.id}"),
        ],
        [
            InlineKeyboardButton(media_toggle_label, callback_data=f"{MENU_PREFIX}welcome_media_random:{category.id}"),
            InlineKeyboardButton("🚫 Não usar mídia", callback_data=f"{MENU_PREFIX}welcome_media_disable:{category.id}"),
        ],
        [
            InlineKeyboardButton("⬅️ Voltar", callback_data=f"{MENU_PREFIX}welcome_back:{category.id}"),
        ],
    ]
    return InlineKeyboardMarkup(rows)


async def _render_welcome_panel(update: Update, query, context: ContextTypes.DEFAULT_TYPE, category: models.CategoryDTO) -> None:
    text = _build_welcome_panel_text(category)
    keyboard = _build_welcome_panel_keyboard(category)
    try:
        message = await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
    except BadRequest:
        chat = query.message.chat if query.message else update.effective_chat
        if chat:
            await _refresh_welcome_panel(context, category.id, chat=chat)
        return
    if message:
        chat_id = message.chat_id if hasattr(message, "chat_id") else (query.message.chat_id if query.message else None)
        if chat_id is not None:
            _store_welcome_panel(
                context,
                category_id=category.id,
                chat_id=chat_id,
                message_id=message.message_id,
            )


async def _refresh_welcome_panel(context: ContextTypes.DEFAULT_TYPE, category_id: int, *, chat) -> None:
    async with get_session() as session:
        service = CategoryService(CategoryRepository(session))
        category = await service.get_category_by_id(category_id)
    text = _build_welcome_panel_text(category)
    keyboard = _build_welcome_panel_keyboard(category)
    panels = context.user_data.get(WELCOME_PANEL_CACHE_KEY, {})
    panel_info = panels.get(category_id)
    if panel_info:
        try:
            await context.bot.edit_message_text(
                text=text,
                chat_id=panel_info["chat_id"],
                message_id=panel_info["message_id"],
                parse_mode="Markdown",
                reply_markup=keyboard,
            )
            return
        except BadRequest:
            pass
    sent = await chat.send_message(text, parse_mode="Markdown", reply_markup=keyboard)
    _store_welcome_panel(context, category_id=category_id, chat_id=sent.chat_id, message_id=sent.message_id)


def _prepare_welcome_update_payload(category: models.CategoryDTO) -> dict:
    return {
        "mode": category.welcome_mode,
        "text": category.welcome_text,
        "media_id": category.welcome_media_id,
        "buttons": category.welcome_buttons if category.welcome_buttons else None,
        "use_random_copy": category.use_random_copy,
        "use_random_media": category.use_random_media,
    }


async def _start_addcopy_flow(query, context: ContextTypes.DEFAULT_TYPE, category: models.CategoryDTO, *, return_to: str | None = None) -> None:
    state = {
        "action": "addcopy",
        "category_id": category.id,
        "category_slug": category.slug,
        "category_name": category.name,
    }
    if return_to:
        state["return_to"] = return_to
    context.user_data[STATE_KEY] = state
    await query.message.reply_text(
        f"Categoria `{category.slug}` selecionada.\n"
        "Envie o texto da copy nesta conversa.\n"
        "Opcionalmente, defina peso usando `texto || peso` (ex.: `Oferta VIP || 3`).",
        parse_mode="Markdown",
    )
    await query.answer("Aguardando texto da copy.", show_alert=False)


async def _start_edit_copy_flow(query, context: ContextTypes.DEFAULT_TYPE, category: models.CategoryDTO, *, return_to: str | None = None) -> None:
    copies = list(category.copies or [])
    if not copies:
        await query.answer("Nenhuma copy cadastrada.", show_alert=True)
        return
    rows = []
    for copy in copies:
        label = (copy.text[:40] + ("..." if len(copy.text) > 40 else "")).replace("`", "´")
        rows.append(
            [InlineKeyboardButton(label, callback_data=f"{MENU_PREFIX}cat_edit_copy_select:{category.id}:{copy.id}")]
        )
    rows.append([InlineKeyboardButton("⬅️ Cancelar", callback_data=f"{MENU_PREFIX}back")])
    state = {"action": "editcopy_select", "category_id": category.id}
    if return_to:
        state["return_to"] = return_to
    context.user_data[STATE_KEY] = state
    await query.message.reply_text(
        "Selecione a copy que deseja editar:",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def _start_add_button_flow(query, context: ContextTypes.DEFAULT_TYPE, category: models.CategoryDTO, *, return_to: str | None = None) -> None:
    state = {
        "action": "setbotao_label",
        "category_id": category.id,
        "category_slug": category.slug,
        "category_name": category.name,
        "button_count": len(category.buttons or []),
    }
    if return_to:
        state["return_to"] = return_to
    context.user_data[STATE_KEY] = state
    await query.message.reply_text(
        f"Categoria `{category.slug}` selecionada.\nEnvie o texto do botão (label).",
        parse_mode="Markdown",
    )
    await query.answer("Aguardando label do botão.", show_alert=False)


async def _start_edit_button_flow(query, context: ContextTypes.DEFAULT_TYPE, category: models.CategoryDTO, *, return_to: str | None = None) -> None:
    buttons = list(category.buttons or [])
    if not buttons:
        await query.answer("Nenhum botão cadastrado.", show_alert=True)
        return
    rows = []
    for button in buttons:
        label = button.label.replace("`", "´")
        rows.append(
            [
                InlineKeyboardButton(
                    f"{label} → {button.url}",
                    callback_data=f"{MENU_PREFIX}cat_edit_button_select:{category.id}:{button.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton("⬅️ Cancelar", callback_data=f"{MENU_PREFIX}back")])
    state = {"action": "editbutton_select", "category_id": category.id}
    if return_to:
        state["return_to"] = return_to
    context.user_data[STATE_KEY] = state
    await query.message.reply_text(
        "Selecione o botão que deseja editar:",
        reply_markup=InlineKeyboardMarkup(rows),
    )

async def _start_delete_copy_flow(query, context: ContextTypes.DEFAULT_TYPE, category: models.CategoryDTO, *, return_to: str | None = None) -> None:
    copies = list(category.copies or [])
    if not copies:
        await query.answer("Nenhuma copy cadastrada.", show_alert=True)
        return
    rows: list[list[InlineKeyboardButton]] = []
    for copy in copies:
        label = (copy.text[:40] + ("..." if len(copy.text) > 40 else "")).replace("`", "´")
        rows.append(
            [InlineKeyboardButton(label, callback_data=f"{MENU_PREFIX}cat_delete_copy_select:{category.id}:{copy.id}")]
        )
    rows.append([InlineKeyboardButton("⬅️ Cancelar", callback_data=f"{MENU_PREFIX}back")])
    state = {"action": "deletecopy_select", "category_id": category.id}
    if return_to:
        state["return_to"] = return_to
    context.user_data[STATE_KEY] = state
    await query.message.reply_text(
        "Selecione a copy que deseja remover:",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def _start_delete_button_flow(query, context: ContextTypes.DEFAULT_TYPE, category: models.CategoryDTO, *, return_to: str | None = None) -> None:
    buttons = list(category.buttons or [])
    if not buttons:
        await query.answer("Nenhum botão cadastrado.", show_alert=True)
        return
    rows: list[list[InlineKeyboardButton]] = []
    for button in buttons:
        label = button.label.replace("`", "´")
        rows.append(
            [
                InlineKeyboardButton(
                    f"{label} → {button.url}",
                    callback_data=f"{MENU_PREFIX}cat_delete_button_select:{category.id}:{button.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton("⬅️ Cancelar", callback_data=f"{MENU_PREFIX}back")])
    state = {"action": "deletebutton_select", "category_id": category.id}
    if return_to:
        state["return_to"] = return_to
    context.user_data[STATE_KEY] = state
    await query.message.reply_text(
        "Selecione o botão que deseja remover:",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def _fetch_groups() -> list[models.GroupDTO]:
    async with get_session() as session:
        service = GroupService(GroupRepository(session))
        groups = list(await service.list_all())
    groups.sort(key=lambda g: ((g.title or "").lower(), g.telegram_chat_id))
    return groups


async def _render_groups_index(query, context: ContextTypes.DEFAULT_TYPE, page: int = 0) -> None:
    groups = await _fetch_groups()
    total = len(groups)
    if total == 0:
        await query.edit_message_text(
            "Nenhum grupo identificado ainda.\n"
            "Adicione o bot como administrador nos grupos e execute `/setcategoria <slug>` dentro deles.",
            reply_markup=_build_main_menu(),
        )
        return

    total_pages = max(1, math.ceil(total / GROUPS_PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))
    start = page * GROUPS_PAGE_SIZE
    chunk = groups[start : start + GROUPS_PAGE_SIZE]

    rows: list[list[InlineKeyboardButton]] = []
    for group in chunk:
        label = group.title or f"Chat {group.telegram_chat_id}"
        suffix = " ✅" if group.category_id else " ⚠️"
        rows.append(
            [
                InlineKeyboardButton(
                    f"{label}{suffix}",
                    callback_data=f"{MENU_PREFIX}group_detail:{group.telegram_chat_id}",
                )
            ]
        )

    nav_row: list[InlineKeyboardButton] = []
    if total_pages > 1:
        if page > 0:
            nav_row.append(
                InlineKeyboardButton("⬅️ Anterior", callback_data=f"{MENU_PREFIX}groups_page:{page-1}")
            )
        nav_row.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav_row.append(
                InlineKeyboardButton("Próxima ➡️", callback_data=f"{MENU_PREFIX}groups_page:{page+1}")
            )
    if nav_row:
        rows.append(nav_row)

    rows.append([InlineKeyboardButton("🏠 Menu principal", callback_data=f"{MENU_PREFIX}back")])

    await query.edit_message_text(
        "Selecione o grupo para gerenciar:",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def _render_group_detail(update: Update, query, context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    async with get_session() as session:
        group_service = GroupService(GroupRepository(session))
        group = await group_service.get_by_chat(chat_id)
        if not group:
            await query.answer("Grupo não encontrado.", show_alert=True)
            return
        category_name = "Não vinculado"
        category_slug = None
        if group.category_id is not None:
            category_service = CategoryService(CategoryRepository(session))
            try:
                category = await category_service.get_category_by_id(group.category_id)
                category_name = category.name
                category_slug = category.slug
            except NotFoundError:
                category_name = "Categoria removida"
                category_slug = None

    chat_link = None
    try:
        tg_chat = await context.bot.get_chat(chat_id)
        if tg_chat.username:
            chat_link = f"https://t.me/{tg_chat.username}"
        elif tg_chat.invite_link:
            chat_link = tg_chat.invite_link
    except Exception:
        chat_link = None

    title = group.title or "—"
    link_text = chat_link or "Indisponível"
    category_line = category_name
    if category_slug:
        category_line += f" (slug: {category_slug})"

    detail_text = (
        "Gestão de Grupo\n\n"
        f"Nome: {title}\n"
        f"Chat ID: {group.telegram_chat_id}\n"
        f"Categoria atual: {category_line}\n"
        f"Link: {link_text}"
    )

    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton("🔄 Definir categoria", callback_data=f"{MENU_PREFIX}group_set_category:{group.telegram_chat_id}")],
    ]
    if group.category_id is not None:
        rows.append(
            [
                InlineKeyboardButton(
                    "🧹 Desvincular categoria",
                    callback_data=f"{MENU_PREFIX}group_unlink:{group.telegram_chat_id}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton("⬅️ Voltar à lista de grupos", callback_data=f"{MENU_PREFIX}groups"),
        ]
    )
    rows.append([InlineKeyboardButton("🏠 Menu principal", callback_data=f"{MENU_PREFIX}back")])

    try:
        await query.edit_message_text(
            detail_text,
            reply_markup=InlineKeyboardMarkup(rows),
        )
    except BadRequest as exc:
        if "Message is not modified" in str(exc):
            return
        raise


async def _render_group_category_selector(query, chat_id: int, page: int = 0) -> None:
    async with get_session() as session:
        service = CategoryService(CategoryRepository(session))
        categories = await service.list_categories()

    total = len(categories)
    if total == 0:
        await query.answer("Nenhuma categoria cadastrada.", show_alert=True)
        return

    total_pages = max(1, math.ceil(total / GROUP_CATEGORY_PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))
    start = page * GROUP_CATEGORY_PAGE_SIZE
    chunk = categories[start : start + GROUP_CATEGORY_PAGE_SIZE]

    rows: list[list[InlineKeyboardButton]] = []
    for category in chunk:
        rows.append(
            [
                InlineKeyboardButton(
                    category.name,
                    callback_data=f"{MENU_PREFIX}group_choose_category:{chat_id}:{category.id}",
                )
            ]
        )

    nav_row: list[InlineKeyboardButton] = []
    if total_pages > 1:
        if page > 0:
            nav_row.append(
                InlineKeyboardButton("⬅️", callback_data=f"{MENU_PREFIX}group_categories_page:{chat_id}:{page-1}")
            )
        nav_row.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav_row.append(
                InlineKeyboardButton("➡️", callback_data=f"{MENU_PREFIX}group_categories_page:{chat_id}:{page+1}")
            )
    if nav_row:
        rows.append(nav_row)

    rows.append(
        [
            InlineKeyboardButton(
                "⬅️ Voltar ao grupo",
                callback_data=f"{MENU_PREFIX}group_detail:{chat_id}",
            )
        ]
    )

    await query.edit_message_text(
        "Selecione a categoria que deseja vincular:",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    if not chat:
        return
    greeting = f"Olá {user.first_name}!" if user and user.first_name else "Olá!"
    text = (
        f"{greeting} Eu sou o KingsCEO Bot.\n"
        "Escolha uma das opções abaixo para navegar pelas configurações."
    )
    await chat.send_message(text=text, reply_markup=_build_main_menu())


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data or ""
    action = data.removeprefix(MENU_PREFIX)

    if action == "noop":
        return

    if action == "setcategoria":
        if not _is_admin(update):
            await query.answer("Acesso restrito a administradores.", show_alert=True)
            return
        context.user_data[STATE_KEY] = {"action": "setcategoria"}

    if action == "back":
        _clear_welcome_state(context)
        context.user_data.pop(STATE_KEY, None)
        context.user_data.pop(STATE_KEY, None)
        await query.edit_message_text(
            "Menu principal. Escolha uma das opções abaixo.",
            reply_markup=_build_main_menu(),
        )
        return

    if action == "viewcats":
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            categories = await service.list_categories()
        if not categories:
            await query.edit_message_text(
                "Nenhuma categoria cadastrada ainda.",
                reply_markup=_build_main_menu(),
            )
            return
        rows = []
        for idx in range(0, len(categories), 2):
            row = categories[idx : idx + 2]
            rows.append(
                [
                    InlineKeyboardButton(cat.name, callback_data=f"{MENU_PREFIX}viewcats:{cat.id}")
                    for cat in row
                ]
            )
        rows.append([InlineKeyboardButton("⬅️ Voltar", callback_data=f"{MENU_PREFIX}back")])
        await query.edit_message_text(
            "Selecione a categoria para visualizar detalhes:",
            reply_markup=InlineKeyboardMarkup(rows),
        )
        return
    if action == "groups":
        if not _is_admin(update):
            await query.answer("Acesso restrito a administradores.", show_alert=True)
            return
        await _render_groups_index(query, context)
        return
    if action.startswith("groups_page:"):
        if not _is_admin(update):
            await query.answer("Acesso restrito a administradores.", show_alert=True)
            return
        _, _, page_part = action.partition(":")
        page = int(page_part) if page_part.isdigit() else 0
        await _render_groups_index(query, context, page=page)
        return
    if action.startswith("group_detail:"):
        if not _is_admin(update):
            await query.answer("Acesso restrito a administradores.", show_alert=True)
            return
        _, _, chat_part = action.partition(":")
        if not chat_part.lstrip("-").isdigit():
            await query.answer("Grupo inválido.", show_alert=True)
            return
        chat_id = int(chat_part)
        await _render_group_detail(update, query, context, chat_id)
        return
    if action.startswith("group_set_category:"):
        if not _is_admin(update):
            await query.answer("Acesso restrito a administradores.", show_alert=True)
            return
        _, _, chat_part = action.partition(":")
        if not chat_part.lstrip("-").isdigit():
            await query.answer("Grupo inválido.", show_alert=True)
            return
        chat_id = int(chat_part)
        await _render_group_category_selector(query, chat_id, page=0)
        return
    if action.startswith("group_categories_page:"):
        if not _is_admin(update):
            await query.answer("Acesso restrito a administradores.", show_alert=True)
            return
        parts = action.split(":")
        if len(parts) != 3 or not parts[1].lstrip("-").isdigit() or not parts[2].isdigit():
            await query.answer("Página inválida.", show_alert=True)
            return
        chat_id = int(parts[1])
        page = int(parts[2])
        await _render_group_category_selector(query, chat_id, page=page)
        return
    if action.startswith("group_choose_category:"):
        if not _is_admin(update):
            await query.answer("Acesso restrito a administradores.", show_alert=True)
            return
        parts = action.split(":")
        if len(parts) != 3 or not parts[1].lstrip("-").isdigit() or not parts[2].isdigit():
            await query.answer("Seleção inválida.", show_alert=True)
            return
        chat_id = int(parts[1])
        category_id = int(parts[2])
        async with get_session() as session:
            group_service = GroupService(GroupRepository(session))
            category_service = CategoryService(CategoryRepository(session))
            try:
                await category_service.get_category_by_id(category_id)
            except NotFoundError:
                await query.answer("Categoria não encontrada.", show_alert=True)
                return
            await group_service.update_category(chat_id=chat_id, category_id=category_id)
        await query.answer("Categoria vinculada.", show_alert=False)
        await _render_group_detail(update, query, context, chat_id)
        return
    if action.startswith("group_unlink:"):
        if not _is_admin(update):
            await query.answer("Acesso restrito a administradores.", show_alert=True)
            return
        _, _, chat_part = action.partition(":")
        if not chat_part.lstrip("-").isdigit():
            await query.answer("Grupo inválido.", show_alert=True)
            return
        chat_id = int(chat_part)
        async with get_session() as session:
            group_service = GroupService(GroupRepository(session))
            try:
                await group_service.update_category(chat_id=chat_id, category_id=None)
            except NotFoundError:
                await query.answer("Grupo não encontrado.", show_alert=True)
                return
        await query.answer("Grupo desvinculado.", show_alert=False)
        await _render_group_detail(update, query, context, chat_id)
        return

    if action.startswith("viewcats:"):
        _, _, id_part = action.partition(":")
        if not id_part.isdigit():
            await query.answer("Categoria inválida.", show_alert=True)
            return
        category_id = int(id_part)
        async with get_session() as session:
            category_service = CategoryService(CategoryRepository(session))
            try:
                category = await category_service.get_category_by_id(category_id)
            except NotFoundError:
                await query.edit_message_text(
                    "Categoria não encontrada.",
                    reply_markup=_build_main_menu(),
                )
                return
        await _render_category_detail(update, query, context, category)
        return
    if action.startswith("cat_spoiler:"):
        if not _is_admin(update):
            await query.answer("Acesso restrito a administradores.", show_alert=True)
            return
        _, _, id_part = action.partition(":")
        if not id_part.isdigit():
            await query.answer("Categoria inválida.", show_alert=True)
            return
        category_id = int(id_part)
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            try:
                current = await service.get_category_by_id(category_id)
            except NotFoundError:
                await query.answer("Categoria não encontrada.", show_alert=True)
                return
            await service.set_spoiler(category_id, enabled=not current.use_spoiler_media)
            refreshed = await service.get_category_by_id(category_id)
        await query.answer(
            "Spoiler nas mídias ativado."
            if not current.use_spoiler_media
            else "Spoiler nas mídias desativado.",
            show_alert=False,
        )
        await _render_category_detail(update, query, context, refreshed)
        return
    if action.startswith("cat_repo_toggle:"):
        if not _is_admin(update):
            await query.answer("Acesso restrito a administradores.", show_alert=True)
            return
        _, _, id_part = action.partition(":")
        if not id_part.isdigit():
            await query.answer("Repositório inválido.", show_alert=True)
            return
        mapping_id = int(id_part)
        async with get_session() as session:
            mapping_repo = MediaRepositoryMapRepository(session)
            category_repo = CategoryRepository(session)
            repo_service = MediaRepositoryService(mapping_repo, category_repo)
            mapping = await repo_service.get_mapping_by_id(mapping_id)
            if not mapping:
                await query.answer("Repositório não encontrado.", show_alert=True)
                return
            updated_mapping = await repo_service.set_cleanup(mapping_id, enabled=not mapping.clean_service_messages)
            category_service = CategoryService(category_repo)
            category = await category_service.get_category_by_id(updated_mapping.category_id)
        await query.answer(
            "Mensagens de serviço serão apagadas automaticamente."
            if not mapping.clean_service_messages
            else "Mensagens de serviço deixarão de ser apagadas.",
            show_alert=False,
        )
        await _render_category_detail(update, query, context, category)
        return
    if action.startswith("randcopy:"):
        _, _, id_part = action.partition(":")
        if not id_part.isdigit():
            await query.answer("Categoria inválida.", show_alert=True)
            return
        category_id = int(id_part)
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            try:
                category = await service.get_category_by_id(category_id)
            except NotFoundError:
                await query.answer("Categoria não encontrada.", show_alert=True)
                return
        copies = list(category.copies or [])
        if not copies:
            await query.answer("Nenhuma copy cadastrada.", show_alert=True)
            return
        if len(copies) == 1:
            await query.message.reply_text(
                "Existe apenas uma copy cadastrada. Ela será usada sempre que necessário:\n\n"
                f"{copies[0].text}"
            )
            return
        chosen = weighted_choice([(c, c.weight or 1) for c in copies])
        chosen_text = chosen.text if chosen else copies[0].text
        await query.message.reply_text(
            "Copy aleatória selecionada (considerando pesos configurados):\n\n"
            f"{chosen_text}"
        )
        return

    if action.startswith("cat_create_copy:"):
        if not _is_admin(update):
            await query.answer("Acesso restrito a administradores.", show_alert=True)
            return
        _, _, id_part = action.partition(":")
        if not id_part.isdigit():
            await query.answer("Categoria inválida.", show_alert=True)
            return
        category_id = int(id_part)
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            try:
                category = await service.get_category_by_id(category_id)
            except NotFoundError:
                await query.answer("Categoria não encontrada.", show_alert=True)
                return
        await _start_addcopy_flow(query, context, category)
        return

    if action.startswith("cat_edit_copy:"):
        if not _is_admin(update):
            await query.answer("Acesso restrito a administradores.", show_alert=True)
            return
        _, _, id_part = action.partition(":")
        if not id_part.isdigit():
            await query.answer("Categoria inválida.", show_alert=True)
            return
        category_id = int(id_part)
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            try:
                category = await service.get_category_by_id(category_id)
            except NotFoundError:
                await query.answer("Categoria não encontrada.", show_alert=True)
                return
        await _start_edit_copy_flow(query, context, category)
        return

    if action.startswith("cat_edit_copy_select:"):
        pending = context.user_data.get(STATE_KEY) or {}
        if pending.get("action") != "editcopy_select":
            await query.answer("Fluxo expirado.", show_alert=True)
            return
        parts = action.split(":")
        if len(parts) != 3:
            await query.answer("Copy inválida.", show_alert=True)
            return
        category_id = int(parts[1])
        copy_id = int(parts[2])
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            try:
                category = await service.get_category_by_id(category_id)
            except NotFoundError:
                await query.answer("Categoria não encontrada.", show_alert=True)
                return
        copy_obj = next((c for c in category.copies or [] if c.id == copy_id), None)
        if not copy_obj:
            await query.answer("Copy não encontrada.", show_alert=True)
            return
        context.user_data[STATE_KEY] = {
            "action": "editcopy",
            "category_id": category.id,
            "category_slug": category.slug,
            "copy_id": copy_obj.id,
            "current_weight": copy_obj.weight or 1,
            "return_to": pending.get("return_to"),
        }
        await query.edit_message_text(
            "Copy selecionada. Envie o novo texto.\n"
            "Você pode usar `texto || peso` para ajustar o peso (padrão mantém o atual).",
            reply_markup=None,
        )
        return
    if action.startswith("cat_delete_copy_select:"):
        pending = context.user_data.get(STATE_KEY) or {}
        if pending.get("action") != "deletecopy_select":
            await query.answer("Fluxo expirado.", show_alert=True)
            return
        parts = action.split(":")
        if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
            await query.answer("Copy inválida.", show_alert=True)
            return
        category_id = int(parts[1])
        copy_id = int(parts[2])
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            try:
                category = await service.get_category_by_id(category_id)
            except NotFoundError:
                await query.answer("Categoria não encontrada.", show_alert=True)
                return
            copy_obj = next((c for c in category.copies or [] if c.id == copy_id), None)
            if not copy_obj:
                await query.answer("Copy não encontrada.", show_alert=True)
                return
            await service.delete_copy(copy_id)
        context.user_data.pop(STATE_KEY, None)
        await query.answer("Copy removida.", show_alert=False)
        chat = query.message.chat if query.message else update.effective_chat
        if chat:
            await _refresh_welcome_panel(context, category_id, chat=chat)
        await query.edit_message_text("Copy removida.")
        return

    if action.startswith("cat_create_button:"):
        if not _is_admin(update):
            await query.answer("Acesso restrito a administradores.", show_alert=True)
            return
        _, _, id_part = action.partition(":")
        if not id_part.isdigit():
            await query.answer("Categoria inválida.", show_alert=True)
            return
        category_id = int(id_part)
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            try:
                category = await service.get_category_by_id(category_id)
            except NotFoundError:
                await query.answer("Categoria não encontrada.", show_alert=True)
                return
        await _start_add_button_flow(query, context, category)
        return

    if action.startswith("cat_edit_button:"):
        if not _is_admin(update):
            await query.answer("Acesso restrito a administradores.", show_alert=True)
            return
        _, _, id_part = action.partition(":")
        if not id_part.isdigit():
            await query.answer("Categoria inválida.", show_alert=True)
            return
        category_id = int(id_part)
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            try:
                category = await service.get_category_by_id(category_id)
            except NotFoundError:
                await query.answer("Categoria não encontrada.", show_alert=True)
                return
        await _start_edit_button_flow(query, context, category)
        return

    if action.startswith("cat_edit_button_select:"):
        pending = context.user_data.get(STATE_KEY) or {}
        if pending.get("action") != "editbutton_select":
            await query.answer("Fluxo expirado.", show_alert=True)
            return
        parts = action.split(":")
        if len(parts) != 3:
            await query.answer("Botão inválido.", show_alert=True)
            return
        category_id = int(parts[1])
        button_id = int(parts[2])
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            try:
                category = await service.get_category_by_id(category_id)
            except NotFoundError:
                await query.answer("Categoria não encontrada.", show_alert=True)
                return
        button = next((b for b in category.buttons or [] if b.id == button_id), None)
        if not button:
            await query.answer("Botão não encontrado.", show_alert=True)
            return
        context.user_data[STATE_KEY] = {
            "action": "editbutton_label",
            "category_id": category.id,
            "category_slug": category.slug,
            "button_id": button.id,
            "current_label": button.label,
            "current_url": button.url,
            "current_weight": button.weight or 1,
            "return_to": pending.get("return_to"),
        }
        await query.edit_message_text(
            f"Botão selecionado:\n*{button.label}* → {button.url}\nPosição atual: {button.weight or 1}\n\n"
            "Envie o novo label ou `/skip` para manter.",
            parse_mode="Markdown",
        )
        return
    if action.startswith("cat_delete_button_select:"):
        pending = context.user_data.get(STATE_KEY) or {}
        if pending.get("action") != "deletebutton_select":
            await query.answer("Fluxo expirado.", show_alert=True)
            return
        parts = action.split(":")
        if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
            await query.answer("Botão inválido.", show_alert=True)
            return
        category_id = int(parts[1])
        button_id = int(parts[2])
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            try:
                category = await service.get_category_by_id(category_id)
            except NotFoundError:
                await query.answer("Categoria não encontrada.", show_alert=True)
                return
            button = next((b for b in category.buttons or [] if b.id == button_id), None)
            if not button:
                await query.answer("Botão não encontrado.", show_alert=True)
                return
            await service.delete_button(button_id)
        context.user_data.pop(STATE_KEY, None)
        await query.answer("Botão removido.", show_alert=False)
        chat = query.message.chat if query.message else update.effective_chat
        if chat:
            await _refresh_welcome_panel(context, category_id, chat=chat)
        await query.edit_message_text("Botão removido.")
        return

    if action.startswith("randmedia:"):
        _, _, id_part = action.partition(":")
        if not id_part.isdigit():
            await query.answer("Categoria inválida.", show_alert=True)
            return
        category_id = int(id_part)
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            try:
                category = await service.get_category_by_id(category_id)
            except NotFoundError:
                await query.answer("Categoria não encontrada.", show_alert=True)
                return
        medias = list(category.media_items or [])
        if not medias:
            await query.answer("Nenhuma mídia cadastrada.", show_alert=True)
            return
        chosen = weighted_choice([(m, m.weight or 1) for m in medias])
        chosen = chosen or medias[0]
        caption = chosen.caption or "(sem legenda)"
        await query.message.reply_text(
            "Mídia aleatória selecionada (considerando pesos configurados):\n\n"
            f"Tipo: {chosen.media_type}\n"
            f"Legenda: {caption}\n"
            f"file_id: `{chosen.file_id}`",
            parse_mode="Markdown",
        )
        return

    if action == "addcopy":
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            categories = await service.list_categories()
        if not categories:
            await query.edit_message_text(
                "Nenhuma categoria encontrada. Crie uma categoria primeiro.",
                reply_markup=_build_main_menu(),
            )
            return
        rows = []
        for idx in range(0, len(categories), 2):
            row = categories[idx : idx + 2]
            rows.append(
                [
                    InlineKeyboardButton(cat.name, callback_data=f"{MENU_PREFIX}addcopy:{cat.id}")
                    for cat in row
                ]
            )
        keyboard = InlineKeyboardMarkup(rows)
        await query.edit_message_text(
            "Selecione a categoria para adicionar a copy:",
            reply_markup=keyboard,
        )
        return

    if action.startswith("addcopy:"):
        _, _, id_part = action.partition(":")
        if not id_part.isdigit():
            await query.answer("Categoria inválida.", show_alert=True)
            return
        category_id = int(id_part)
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            try:
                category = await service.get_category_by_id(category_id)
            except NotFoundError:
                await query.edit_message_text(
                    "Categoria não encontrada. Tente novamente.",
                    reply_markup=_build_main_menu(),
                )
                return
        if not _is_admin(update):
            await query.edit_message_text(
                "Apenas administradores podem registrar copies.",
                reply_markup=_build_main_menu(),
            )
            return
        context.user_data[STATE_KEY] = {
            "action": "addcopy",
            "category_id": category.id,
            "category_slug": category.slug,
            "category_name": category.name,
        }
        await query.edit_message_text(
            f"Categoria selecionada: {category.name}.\n"
            "Envie o texto da copy nesta conversa.\n"
            "Opcionalmente, defina peso usando `texto || peso` (ex.: `Oferta VIP || 3`).",
        )
        return

    if action == "setbotao":
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            categories = await service.list_categories()
        if not categories:
            await query.edit_message_text(
                "Nenhuma categoria encontrada. Crie uma categoria primeiro.",
                reply_markup=_build_main_menu(),
            )
            return
        rows = []
        for idx in range(0, len(categories), 2):
            row = categories[idx : idx + 2]
            rows.append(
                [
                    InlineKeyboardButton(cat.name, callback_data=f"{MENU_PREFIX}setbotao:{cat.id}")
                    for cat in row
                ]
            )
        rows.append([InlineKeyboardButton("⬅️ Voltar", callback_data=f"{MENU_PREFIX}back")])
        await query.edit_message_text(
            "Selecione a categoria para adicionar um botão:",
            reply_markup=InlineKeyboardMarkup(rows),
        )
        return

    if action.startswith("cat_welcome:"):
        if not _is_admin(update):
            await query.answer("Acesso restrito a administradores.", show_alert=True)
            return
        _, _, id_part = action.partition(":")
        if not id_part.isdigit():
            await query.answer("Categoria inválida.", show_alert=True)
            return
        category_id = int(id_part)
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            try:
                category = await service.get_category_by_id(category_id)
            except NotFoundError:
                await query.answer("Categoria não encontrada.", show_alert=True)
                return
        _clear_welcome_state(context)
        await _render_welcome_panel(update, query, context, category)
        return
    if action.startswith("welcome_back:"):
        _, _, id_part = action.partition(":")
        if not id_part.isdigit():
            await query.answer("Categoria inválida.", show_alert=True)
            return
        category_id = int(id_part)
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            try:
                category = await service.get_category_by_id(category_id)
            except NotFoundError:
                await query.answer("Categoria não encontrada.", show_alert=True)
                return
        await _render_category_detail(update, query, context, category)
        return
    if action.startswith("welcome_media_random:"):
        if not _is_admin(update):
            await query.answer("Acesso restrito a administradores.", show_alert=True)
            return
        _, _, id_part = action.partition(":")
        if not id_part.isdigit():
            await query.answer("Categoria inválida.", show_alert=True)
            return
        category_id = int(id_part)
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            try:
                category = await service.get_category_by_id(category_id)
            except NotFoundError:
                await query.answer("Categoria não encontrada.", show_alert=True)
                return
            payload = _prepare_welcome_update_payload(category)
            payload["use_random_media"] = True
            payload["media_id"] = None
            if payload["mode"] not in {"media", "all"}:
                has_text = bool(payload["text"])
                has_buttons = bool(payload["buttons"])
                payload["mode"] = "all" if (has_text or has_buttons) else "media"
            await service.update_welcome(
                category.id,
                mode=payload["mode"],
                text=payload["text"],
                media_id=payload["media_id"],
                buttons=payload["buttons"],
                use_random_copy=payload["use_random_copy"],
                use_random_media=payload["use_random_media"],
            )
            updated = await service.get_category_by_id(category.id)
        await query.answer("Mídia aleatória ativada nas boas-vindas.", show_alert=False)
        await _render_welcome_panel(update, query, context, updated)
        return
    if action.startswith("welcome_media_disable:"):
        if not _is_admin(update):
            await query.answer("Acesso restrito a administradores.", show_alert=True)
            return
        _, _, id_part = action.partition(":")
        if not id_part.isdigit():
            await query.answer("Categoria inválida.", show_alert=True)
            return
        category_id = int(id_part)
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            try:
                category = await service.get_category_by_id(category_id)
            except NotFoundError:
                await query.answer("Categoria não encontrada.", show_alert=True)
                return
            payload = _prepare_welcome_update_payload(category)
            payload["use_random_media"] = False
            payload["media_id"] = None
            if payload["mode"] in {"all", "media"}:
                if payload["text"]:
                    payload["mode"] = "text"
                elif payload["buttons"]:
                    payload["mode"] = "buttons"
                else:
                    payload["mode"] = "none"
            await service.update_welcome(
                category.id,
                mode=payload["mode"],
                text=payload["text"],
                media_id=payload["media_id"],
                buttons=payload["buttons"],
                use_random_copy=payload["use_random_copy"],
                use_random_media=payload["use_random_media"],
            )
            updated = await service.get_category_by_id(category.id)
        await query.answer("Mídia desativada nas boas-vindas.", show_alert=False)
        await _render_welcome_panel(update, query, context, updated)
        return
    if action.startswith("welcome_create_copy:"):
        if not _is_admin(update):
            await query.answer("Acesso restrito a administradores.", show_alert=True)
            return
        _, _, id_part = action.partition(":")
        if not id_part.isdigit():
            await query.answer("Categoria inválida.", show_alert=True)
            return
        category_id = int(id_part)
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            try:
                category = await service.get_category_by_id(category_id)
            except NotFoundError:
                await query.answer("Categoria não encontrada.", show_alert=True)
                return
        await _start_addcopy_flow(query, context, category, return_to="welcome")
        return
    if action.startswith("welcome_edit_copy:"):
        if not _is_admin(update):
            await query.answer("Acesso restrito a administradores.", show_alert=True)
            return
        _, _, id_part = action.partition(":")
        if not id_part.isdigit():
            await query.answer("Categoria inválida.", show_alert=True)
            return
        category_id = int(id_part)
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            try:
                category = await service.get_category_by_id(category_id)
            except NotFoundError:
                await query.answer("Categoria não encontrada.", show_alert=True)
                return
        await _start_edit_copy_flow(query, context, category, return_to="welcome")
        return
    if action.startswith("welcome_delete_copy:"):
        if not _is_admin(update):
            await query.answer("Acesso restrito a administradores.", show_alert=True)
            return
        _, _, id_part = action.partition(":")
        if not id_part.isdigit():
            await query.answer("Categoria inválida.", show_alert=True)
            return
        category_id = int(id_part)
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            try:
                category = await service.get_category_by_id(category_id)
            except NotFoundError:
                await query.answer("Categoria não encontrada.", show_alert=True)
                return
        await _start_delete_copy_flow(query, context, category, return_to="welcome")
        return
    if action.startswith("welcome_create_button:"):
        if not _is_admin(update):
            await query.answer("Acesso restrito a administradores.", show_alert=True)
            return
        _, _, id_part = action.partition(":")
        if not id_part.isdigit():
            await query.answer("Categoria inválida.", show_alert=True)
            return
        category_id = int(id_part)
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            try:
                category = await service.get_category_by_id(category_id)
            except NotFoundError:
                await query.answer("Categoria não encontrada.", show_alert=True)
                return
        await _start_add_button_flow(query, context, category, return_to="welcome")
        return
    if action.startswith("welcome_edit_button:"):
        if not _is_admin(update):
            await query.answer("Acesso restrito a administradores.", show_alert=True)
            return
        _, _, id_part = action.partition(":")
        if not id_part.isdigit():
            await query.answer("Categoria inválida.", show_alert=True)
            return
        category_id = int(id_part)
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            try:
                category = await service.get_category_by_id(category_id)
            except NotFoundError:
                await query.answer("Categoria não encontrada.", show_alert=True)
                return
        await _start_edit_button_flow(query, context, category, return_to="welcome")
        return
    if action.startswith("welcome_delete_button:"):
        if not _is_admin(update):
            await query.answer("Acesso restrito a administradores.", show_alert=True)
            return
        _, _, id_part = action.partition(":")
        if not id_part.isdigit():
            await query.answer("Categoria inválida.", show_alert=True)
            return
        category_id = int(id_part)
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            try:
                category = await service.get_category_by_id(category_id)
            except NotFoundError:
                await query.answer("Categoria não encontrada.", show_alert=True)
                return
        await _start_delete_button_flow(query, context, category, return_to="welcome")
        return

    if action.startswith("welcome_cat:"):
        _, _, id_part = action.partition(":")
        if not id_part.isdigit():
            await query.answer("Categoria inválida.", show_alert=True)
            return
        category_id = int(id_part)
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            try:
                category = await service.get_category_by_id(category_id)
            except NotFoundError:
                await query.edit_message_text(
                    "Categoria não encontrada. Tente novamente.",
                    reply_markup=_build_main_menu(),
                )
                return
        _init_welcome_state(context, category)
        state = _get_welcome_state(context)
        async with get_session() as session:
            repo_service = MediaRepositoryService(MediaRepositoryMapRepository(session), CategoryRepository(session))
            repositories = await repo_service.list_by_category(category.id)
        state["repositories_count"] = len(repositories)
        await _prompt_welcome_mode(query, category.name)
        return

    if action.startswith("welcome_mode:"):
        state = _get_welcome_state(context)
        if not state:
            await query.edit_message_text("Fluxo expirado. Recomece.", reply_markup=_build_main_menu())
            return
        _, _, mode = action.partition(":")
        state["mode"] = mode
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            category = await service.get_category_by_id(state["category_id"])
        if mode == "none":
            state["copy_strategy"] = "none"
            state["copy_text"] = None
            state["media_strategy"] = "none"
            state["media_file_id"] = None
            state["buttons_selected"] = set()
            await _show_welcome_summary(query, context, category, state)
            state["step"] = "summary"
            return
        await _prompt_welcome_copy_options(query, bool(category.copies))
        state["step"] = "copy"
        return

    if action.startswith("welcome_copy"):
        state = _get_welcome_state(context)
        if not state:
            await query.edit_message_text("Fluxo expirado. Recomece.", reply_markup=_build_main_menu())
            return
        _, _, choice = action.partition(":")
        if not choice:
            async with get_session() as session:
                service = CategoryService(CategoryRepository(session))
                category = await service.get_category_by_id(state["category_id"])
            await _prompt_welcome_copy_options(query, bool(category.copies))
            return
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            category = await service.get_category_by_id(state["category_id"])
        if choice == "random":
            state["copy_strategy"] = "random"
            state["copy_text"] = None
            await _prompt_welcome_media_options(query, bool(category.media_items))
            state["step"] = "media"
            return
        if choice == "none":
            state["copy_strategy"] = "none"
            state["copy_text"] = None
            await _prompt_welcome_media_options(query, bool(category.media_items))
            state["step"] = "media"
            return
        if choice == "manual":
            state["copy_strategy"] = "manual_pending"
            state["step"] = "welcome_copy_manual"
            await query.edit_message_text(
                "Envie a copy personalizada para as boas-vindas.",
                reply_markup=None,
            )
            return
        if choice == "select":
            if not category.copies:
                await query.answer("Nenhuma copy disponível.", show_alert=True)
                return
            await _prompt_welcome_copy_selection(query, category.copies)
            return

    if action.startswith("welcome_copy_select:"):
        state = _get_welcome_state(context)
        if not state:
            await query.edit_message_text("Fluxo expirado.", reply_markup=_build_main_menu())
            return
        _, _, id_part = action.partition(":")
        if not id_part.isdigit():
            await query.answer("Copy inválida.", show_alert=True)
            return
        copy_id = int(id_part)
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            category = await service.get_category_by_id(state["category_id"])
        matching = next((copy for copy in category.copies or [] if copy.id == copy_id), None)
        if not matching:
            await query.answer("Copy não encontrada.", show_alert=True)
            return
        state["copy_strategy"] = "selected"
        state["copy_text"] = matching.text
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            category = await service.get_category_by_id(state["category_id"])
        await _prompt_welcome_media_options(query, bool(category.media_items))
        state["step"] = "media"
        return

    if action.startswith("welcome_media"):
        state = _get_welcome_state(context)
        if not state:
            await query.edit_message_text("Fluxo expirado.", reply_markup=_build_main_menu())
            return
        _, _, choice = action.partition(":")
        if not choice:
            async with get_session() as session:
                service = CategoryService(CategoryRepository(session))
                category = await service.get_category_by_id(state["category_id"])
            await _prompt_welcome_media_options(query, bool(category.media_items))
            return
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            category = await service.get_category_by_id(state["category_id"])
        if choice == "random":
            state["media_strategy"] = "random"
            state["media_file_id"] = None
            await _prompt_welcome_buttons(query, state, category.buttons or [])
            state["step"] = "buttons"
            return
        if choice == "none":
            state["media_strategy"] = "none"
            state["media_file_id"] = None
            await _prompt_welcome_buttons(query, state, category.buttons or [])
            state["step"] = "buttons"
            return
        if choice == "manual":
            state["media_strategy"] = "manual_pending"
            state["step"] = "welcome_media_manual"
            await query.edit_message_text("Envie o file_id da mídia que deseja usar nas boas-vindas.")
            return
        if choice == "select":
            if not category.media_items:
                await query.answer("Nenhuma mídia disponível.", show_alert=True)
                return
            await _prompt_welcome_media_selection(query, category.media_items)
            return

    if action.startswith("welcome_media_select:"):
        state = _get_welcome_state(context)
        if not state:
            await query.edit_message_text("Fluxo expirado.", reply_markup=_build_main_menu())
            return
        _, _, id_part = action.partition(":")
        if not id_part.isdigit():
            await query.answer("Mídia inválida.", show_alert=True)
            return
        media_id = int(id_part)
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            category = await service.get_category_by_id(state["category_id"])
        media = next((m for m in category.media_items or [] if m.id == media_id), None)
        if not media:
            await query.answer("Mídia não encontrada.", show_alert=True)
            return
        state["media_strategy"] = "selected"
        state["media_file_id"] = media.file_id
        await _prompt_welcome_buttons(query, state, category.buttons or [])
        state["step"] = "buttons"
        return

    if action.startswith("welcome_btn_toggle:"):
        state = _get_welcome_state(context)
        if not state:
            await query.edit_message_text("Fluxo expirado.", reply_markup=_build_main_menu())
            return
        _, _, id_part = action.partition(":")
        if not id_part.isdigit():
            await query.answer("Botão inválido.", show_alert=True)
            return
        button_id = int(id_part)
        selected = state["buttons_selected"]
        if button_id in selected:
            selected.remove(button_id)
        else:
            selected.add(button_id)
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            category = await service.get_category_by_id(state["category_id"])
        await _prompt_welcome_buttons(query, state, category.buttons or [])
        return

    if action == "welcome_btn_all":
        state = _get_welcome_state(context)
        if not state:
            await query.edit_message_text("Fluxo expirado.", reply_markup=_build_main_menu())
            return
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            category = await service.get_category_by_id(state["category_id"])
        state["buttons_selected"] = {btn.id for btn in category.buttons or []}
        await _prompt_welcome_buttons(query, state, category.buttons or [])
        return

    if action == "welcome_btn_clear":
        state = _get_welcome_state(context)
        if not state:
            await query.edit_message_text("Fluxo expirado.", reply_markup=_build_main_menu())
            return
        state["buttons_selected"] = set()
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            category = await service.get_category_by_id(state["category_id"])
        await _prompt_welcome_buttons(query, state, category.buttons or [])
        return

    if action == "welcome_btn_done":
        state = _get_welcome_state(context)
        if not state:
            await query.edit_message_text("Fluxo expirado.", reply_markup=_build_main_menu())
            return
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            category = await service.get_category_by_id(state["category_id"])
        await _show_welcome_summary(query, context, category, state)
        state["step"] = "summary"
        return

    if action == "welcome_restart":
        state = _get_welcome_state(context)
        if not state:
            await query.edit_message_text("Fluxo expirado.", reply_markup=_build_main_menu())
            return
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            category = await service.get_category_by_id(state["category_id"])
        _init_welcome_state(context, category)
        await _prompt_welcome_mode(query, category.name)
        return

    if action == "welcome_confirm":
        state = _get_welcome_state(context)
        if not state:
            await query.edit_message_text("Fluxo expirado.", reply_markup=_build_main_menu())
            return
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            category = await service.get_category_by_id(state["category_id"])
            buttons_map = {btn.id: btn for btn in category.buttons or []}
            selected_buttons = [
                {"label": buttons_map[btn_id].label, "url": buttons_map[btn_id].url}
                for btn_id in state["buttons_selected"]
                if btn_id in buttons_map
            ]
            copy_strategy = state.get("copy_strategy")
            media_strategy = state.get("media_strategy")
            welcome_text = None
            use_random_copy = False
            if copy_strategy == "random":
                use_random_copy = True
            elif copy_strategy in {"selected", "manual"}:
                welcome_text = state.get("copy_text")
            welcome_media_id = None
            use_random_media = False
            if media_strategy == "random":
                use_random_media = True
            elif media_strategy in {"selected", "manual"}:
                welcome_media_id = state.get("media_file_id")
            await service.update_welcome(
                category.id,
                mode=state.get("mode", "all"),
                text=welcome_text,
                media_id=welcome_media_id,
                buttons=selected_buttons,
                use_random_copy=use_random_copy,
                use_random_media=use_random_media,
            )
            category = await service.get_category_by_id(category.id)
        _clear_welcome_state(context)
        context.user_data.pop(STATE_KEY, None)
        await _render_category_detail(update, query, context, category)
        return

    if action == "setrepos":
        await query.edit_message_text(
            "Para definir um repositório, execute `/setrepositorio <slug>` dentro do grupo desejado (o bot e quem aciona devem ser administradores).",
            parse_mode="Markdown",
            reply_markup=_build_main_menu(),
        )
        return

    responses = {
        "add_to_group": (
            "Abra o grupo ou canal e adicione o bot. Promova-o a administrador com permissão para enviar mensagens, mídias e botões.\n"
            "Sem essas permissões, os envios automáticos não funcionarão."
        ),
        "setcategoria": (
            "Cria uma categoria em conversa privada e informa o slug.\n"
            "Depois, dentro do grupo desejado, use `/setcategoria <slug>` (bot e usuário precisam ser admins) para vincular o grupo à categoria."
        ),
        "addcopy": (
            "Registra textos (copies) ligados à categoria.\n"
            "Exemplo: responda a uma mensagem de texto com `/addcopy coroas 3` para peso 3.\n"
            "Sem resposta, o texto pode ser passado após o slug."
        ),
        "viewcats": (
            "Visualize todas as categorias, incluindo copies, botões e repositórios vinculados."
        ),
        "setbotao": (
            "Cria botões inline para a categoria.\n"
            "A posição define a ordem de exibição (1 fica no topo)."
        ),
        "setrepos": (
            "Define o grupo atual como repositório de mídias de uma categoria.\n"
            "No grupo desejado execute `/setrepositorio <slug>` (o bot e o usuário devem ser administradores).\n"
            "Toda mídia enviada por admins será cadastrada automaticamente na categoria."
        ),
        "setboasvindas": (
            "Abra o painel de boas-vindas para escolher modo, copy, mídia e botões de forma guiada."
        ),
    }

    message = responses.get(action, "Escolha uma opção do menu.")
    if action == "setcategoria":
        message += "\n\nEnvie agora o nome da nova categoria neste chat."

    try:
        current_text = query.message.text if query.message else ""
        if current_text == message:
            await query.answer("Mensagem já exibida. Use o comando conforme orientação.", show_alert=False)
            return
        reply_markup = None if action == "setcategoria" else _build_main_menu()
        await query.edit_message_text(text=message, reply_markup=reply_markup)
    except BadRequest as exc:  # pragma: no cover - cenário interativo
        if "Message is not modified" in str(exc):
            await query.answer("Mensagem já exibida. Use o comando conforme orientação.", show_alert=False)
        else:
            raise


def _is_admin(update: Update) -> bool:
    user = update.effective_user
    if not user:
        return False
    settings = get_settings()
    return user.id in settings.admin_ids


async def menu_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    message = update.effective_message
    if not chat or not message or not message.text:
        return

    welcome_state = _get_welcome_state(context)
    if welcome_state:
        step = welcome_state.get("step")
        if step == "welcome_copy_manual":
            text = message.text.strip()
            if not text:
                await chat.send_message("Texto inválido. Envie novamente.")
                return
            welcome_state["copy_strategy"] = "manual"
            welcome_state["copy_text"] = text
            async with get_session() as session:
                service = CategoryService(CategoryRepository(session))
                category = await service.get_category_by_id(welcome_state["category_id"])
            await _prompt_welcome_media_options(message, bool(category.media_items), edit=False)
            welcome_state["step"] = "media"
            return
        if step == "welcome_media_manual":
            file_id = message.text.strip()
            if not file_id:
                await chat.send_message("file_id inválido. Envie novamente.")
                return
            welcome_state["media_strategy"] = "manual"
            welcome_state["media_file_id"] = file_id
            async with get_session() as session:
                service = CategoryService(CategoryRepository(session))
                category = await service.get_category_by_id(welcome_state["category_id"])
            await _prompt_welcome_buttons(message, welcome_state, category.buttons or [], edit=False)
            welcome_state["step"] = "buttons"
            return

    pending = context.user_data.get(STATE_KEY)
    if not pending:
        return

    action = pending.get("action")
    if action == "setcategoria":
        if not _is_admin(update):
            await chat.send_message("Apenas administradores podem criar categorias.")
            context.user_data.pop(STATE_KEY, None)
            return
        name = message.text.strip()
        if not name:
            await chat.send_message("Nome inválido. Envie um texto não vazio para criar a categoria.")
            return
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            try:
                category = await service.create_category(name=name)
            except AlreadyExistsError as exc:
                await chat.send_message(str(exc), reply_markup=_build_main_menu())
            else:
                await chat.send_message(
                    f"Categoria criada com sucesso!\nNome: {category.name}\nSlug: `{category.slug}`",
                    parse_mode="Markdown",
                    reply_markup=_build_main_menu(),
                )
        context.user_data.pop(STATE_KEY, None)
    elif action == "addcopy":
        if not _is_admin(update):
            await chat.send_message("Apenas administradores podem adicionar copies.")
            context.user_data.pop(STATE_KEY, None)
            return
        text_raw = message.text.strip()
        if not text_raw:
            await chat.send_message("Texto inválido. Envie novamente.")
            return
        if "||" in text_raw:
            text_part, weight_part = text_raw.split("||", 1)
            copy_text = text_part.strip()
            weight_part = weight_part.strip()
            if not weight_part.isdigit():
                await chat.send_message("Peso inválido. Use um número inteiro maior que zero (ex.: `Copy teste || 2`).")
                return
            weight = int(weight_part)
            if weight <= 0:
                await chat.send_message("Peso deve ser maior que zero.")
                return
        else:
            copy_text = text_raw
            weight = 1
        if not copy_text:
            await chat.send_message("Texto inválido. Envie novamente.")
            return
        category_id = pending.get("category_id")
        category_slug = pending.get("category_slug")
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            await service.add_copy(category_id, text=copy_text, weight=weight)
        return_to = pending.get("return_to")
        ack_message = f"Copy registrada para a categoria `{category_slug}` com peso {weight}."
        if return_to == "welcome":
            await chat.send_message(ack_message, parse_mode="Markdown")
            await _refresh_welcome_panel(context, category_id, chat=chat)
        else:
            await chat.send_message(
                ack_message,
                parse_mode="Markdown",
                reply_markup=_build_main_menu(),
            )
        context.user_data.pop(STATE_KEY, None)
        return
    elif action == "editcopy":
        text_raw = message.text.strip()
        if not text_raw:
            await chat.send_message("Texto inválido. Envie novamente.")
            return
        current_weight = pending.get("current_weight", 1)
        if "||" in text_raw:
            text_part, weight_part = text_raw.split("||", 1)
            copy_text = text_part.strip()
            weight_part = weight_part.strip()
            if not weight_part.isdigit():
                await chat.send_message("Peso inválido. Use `texto || peso` com peso inteiro.")
                return
            weight = int(weight_part)
            if weight <= 0:
                await chat.send_message("Peso deve ser maior que zero.")
                return
        else:
            copy_text = text_raw
            weight = current_weight
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            await service.update_copy(pending["copy_id"], text=copy_text, weight=weight)
        category_id = pending.get("category_id")
        return_to = pending.get("return_to")
        ack_message = f"Copy atualizada para a categoria `{pending.get('category_slug')}`."
        if return_to == "welcome" and category_id:
            await chat.send_message(ack_message, parse_mode="Markdown")
            await _refresh_welcome_panel(context, category_id, chat=chat)
        else:
            await chat.send_message(
                ack_message,
                parse_mode="Markdown",
                reply_markup=_build_main_menu(),
            )
        context.user_data.pop(STATE_KEY, None)
        return
    elif action == "editbutton_label":
        text_raw = message.text.strip()
        if text_raw.lower() == "/skip":
            pending["new_label"] = pending.get("current_label")
        elif text_raw:
            pending["new_label"] = text_raw
        else:
            await chat.send_message("Texto inválido. Envie novamente ou /skip.")
            return
        pending["action"] = "editbutton_url"
        await chat.send_message(
            "Envie a nova URL do botão ou `/skip` para manter.",
            parse_mode="Markdown",
        )
    elif action == "editbutton_url":
        text_raw = message.text.strip()
        if text_raw.lower() == "/skip":
            pending["new_url"] = pending.get("current_url")
        elif text_raw.lower().startswith(("http://", "https://")):
            pending["new_url"] = text_raw
        else:
            await chat.send_message("URL inválida. Use http:// ou https:// ou /skip para manter.")
            return
        pending["action"] = "editbutton_weight"
        await chat.send_message(
            f"Envie a nova posição do botão (inteiro) ou `/skip` para manter ({pending.get('current_weight')}).",
            parse_mode="Markdown",
        )
    elif action == "editbutton_weight":
        text_raw = message.text.strip()
        if text_raw.lower() == "/skip":
            weight = pending.get("current_weight", 1)
        elif text_raw.isdigit() and int(text_raw) > 0:
            weight = int(text_raw)
        else:
            await chat.send_message("Posição inválida. Use número inteiro maior que zero ou /skip.")
            return
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            await service.update_button(
                pending["button_id"],
                label=pending.get("new_label", pending.get("current_label")),
                url=pending.get("new_url", pending.get("current_url")),
                weight=weight,
            )
        category_id = pending.get("category_id")
        return_to = pending.get("return_to")
        ack_message = f"Botão atualizado na categoria `{pending.get('category_slug')}`."
        if return_to == "welcome" and category_id:
            await chat.send_message(ack_message, parse_mode="Markdown")
            await _refresh_welcome_panel(context, category_id, chat=chat)
        else:
            await chat.send_message(
                ack_message,
                parse_mode="Markdown",
                reply_markup=_build_main_menu(),
            )
        context.user_data.pop(STATE_KEY, None)
        return
    elif action == "setbotao_label":
        if not _is_admin(update):
            await chat.send_message("Apenas administradores podem adicionar botões.")
            context.user_data.pop(STATE_KEY, None)
            return
        label = message.text.strip()
        if not label:
            await chat.send_message("Texto inválido. Envie novamente o nome do botão.")
            return
        pending["button_label"] = label
        pending["action"] = "setbotao_url"
        await chat.send_message("Agora envie a URL do botão (deve começar com http:// ou https://).")
    elif action == "setbotao_url":
        url = message.text.strip()
        if not url.lower().startswith(("http://", "https://")):
            await chat.send_message("URL inválida. Envie uma URL iniciando com http:// ou https://.")
            return
        pending["button_url"] = url
        pending["action"] = "setbotao_weight"
        await chat.send_message(
            "Informe a posição do botão (número inteiro, 1 fica no topo). "
            "Se enviar qualquer outro texto, usaremos automaticamente a próxima posição disponível."
        )
    elif action == "setbotao_weight":
        weight_text = message.text.strip()
        base_count = pending.get("button_count", 0)
        auto_assigned = False
        if not weight_text.isdigit():
            weight = base_count + 1
            auto_assigned = True
        else:
            weight = int(weight_text)
            if weight <= 0:
                weight = base_count + 1
                auto_assigned = True
        category_id = pending.get("category_id")
        category_slug = pending.get("category_slug")
        label = pending.get("button_label")
        url = pending.get("button_url")
        async with get_session() as session:
            service = CategoryService(CategoryRepository(session))
            await service.add_button(category_id, label=label, url=url, weight=weight)
        position_note = " (posição automática)" if auto_assigned else ""
        return_to = pending.get("return_to")
        ack_message = (
            f"Botão registrado para a categoria `{category_slug}`.\n"
            f"Label: {label}\nURL: {url}\nPosição: {weight}{position_note}"
        )
        if return_to == "welcome":
            await chat.send_message(ack_message, parse_mode="Markdown")
            await _refresh_welcome_panel(context, category_id, chat=chat)
        else:
            await chat.send_message(
                ack_message,
                parse_mode="Markdown",
                reply_markup=_build_main_menu(),
            )
        context.user_data.pop(STATE_KEY, None)
        return



def register_menu_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("start", start_command, filters=filters.ChatType.PRIVATE))
    application.add_handler(CallbackQueryHandler(menu_callback, pattern=f"^{MENU_PREFIX}"))
    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.TEXT & (~filters.COMMAND),
            menu_text_handler,
        )
    )

