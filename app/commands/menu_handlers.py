from __future__ import annotations

from typing import Final

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.error import BadRequest

from app.core.config import get_settings
from app.core.exceptions import AlreadyExistsError, NotFoundError
from app.core.utils import weighted_choice
from app.domain.repositories import CategoryRepository, MediaRepositoryMapRepository
from app.domain.services import CategoryService, MediaRepositoryService
from app.infrastructure.db.base import get_session

MENU_PREFIX: Final = "menu:"
STATE_KEY: Final = "menu_pending"


def _build_main_menu() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("Adicione-me a um grupo", callback_data=f"{MENU_PREFIX}add_to_group")],
        [InlineKeyboardButton("Criar categoria (/setcategoria)", callback_data=f"{MENU_PREFIX}setcategoria")],
        [InlineKeyboardButton("Visão de categorias", callback_data=f"{MENU_PREFIX}viewcats")],
        [InlineKeyboardButton("Adicionar copy (/addcopy)", callback_data=f"{MENU_PREFIX}addcopy")],
        [InlineKeyboardButton("Adicionar botão (/setbotao)", callback_data=f"{MENU_PREFIX}setbotao")],
        [InlineKeyboardButton("Configurar repositório (/setrepositorio)", callback_data=f"{MENU_PREFIX}setrepos")],
        [InlineKeyboardButton("Configurar boas-vindas (/setboasvindas)", callback_data=f"{MENU_PREFIX}setboasvindas")],
    ]
    return InlineKeyboardMarkup(buttons)


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

    if action == "setcategoria":
        if not _is_admin(update):
            await query.answer("Acesso restrito a administradores.", show_alert=True)
            return
        context.user_data[STATE_KEY] = {"action": "setcategoria"}

    if action == "back":
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

    if action.startswith("viewcats:"):
        _, _, id_part = action.partition(":")
        if not id_part.isdigit():
            await query.answer("Categoria inválida.", show_alert=True)
            return
        category_id = int(id_part)
        async with get_session() as session:
            category_service = CategoryService(CategoryRepository(session))
            repo_service = MediaRepositoryService(MediaRepositoryMapRepository(session), CategoryRepository(session))
            try:
                category = await category_service.get_category_by_id(category_id)
            except NotFoundError:
                await query.edit_message_text(
                    "Categoria não encontrada.",
                    reply_markup=_build_main_menu(),
                )
                return
            repositories = await repo_service.list_by_category(category_id)
        copy_count = len(category.copies or [])
        button_count = len(category.buttons or [])
        media_count = len(category.media_items or [])
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
        if repositories:
            for repo in repositories[:5]:
                repo_preview += f"\n  • Chat ID: `{repo.chat_id}`"
            if len(repositories) > 5:
                repo_preview += f"\n  • ... +{len(repositories)-5} outros"
        else:
            repo_preview = "\n  • Nenhum repositório ativo"
        detail_message = (
            f"*{category.name}* (`{category.slug}`)\n"
            f"- Mídias cadastradas: {media_count}\n"
            f"- Copies: {copy_count}{copies_preview}\n"
            f"- Botões: {button_count}{buttons_preview}\n"
            f"- Repositórios:{repo_preview}\n"
        )
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🎲 Copy aleatória", callback_data=f"{MENU_PREFIX}randcopy:{category.id}")],
                [InlineKeyboardButton("🎲 Mídia aleatória", callback_data=f"{MENU_PREFIX}randmedia:{category.id}")],
                [InlineKeyboardButton("⬅️ Voltar às categorias", callback_data=f"{MENU_PREFIX}viewcats")],
                [InlineKeyboardButton("🏠 Menu principal", callback_data=f"{MENU_PREFIX}back")],
            ]
        )
        await query.edit_message_text(
            detail_message,
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
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

    if action.startswith("setbotao:"):
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
                    "Categoria não encontrada.",
                    reply_markup=_build_main_menu(),
                )
                return
        if not _is_admin(update):
            await query.edit_message_text(
                "Apenas administradores podem adicionar botões.",
                reply_markup=_build_main_menu(),
            )
            return
        context.user_data[STATE_KEY] = {
            "action": "setbotao_label",
            "category_id": category.id,
            "category_slug": category.slug,
            "category_name": category.name,
            "button_count": len(category.buttons or []),
        }
        await query.edit_message_text(
            f"Categoria selecionada: {category.name}.\n"
            "Envie o texto do botão (label) nesta conversa.",
        )
        return

    responses = {
        "add_to_group": (
            "Abra o grupo ou canal e adicione o bot. Promova-o a administrador com permissão para enviar mensagens, mídias e botões.\n"
            "Sem essas permissões, os envios automáticos não funcionarão."
        ),
        "setcategoria": (
            "Cria uma categoria e o slug usado pelos demais comandos.\n"
            "Exemplo: `/setcategoria Coroas`\n"
            "Resposta esperada: `slug=coroas`. Anote para usar nos próximos comandos."
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
            "Define a mensagem de boas-vindas para grupos/canais associados.\n"
            "Responda ao conteúdo desejado (texto/mídia/botões) e envie `/setboasvindas coroas mode=all`.\n"
            "Modos: all, text, media, buttons, none."
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
        await chat.send_message(
            f"Copy registrada para a categoria `{category_slug}` com peso {weight}.",
            parse_mode="Markdown",
            reply_markup=_build_main_menu(),
        )
        context.user_data.pop(STATE_KEY, None)
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
        await chat.send_message(
            f"Botão registrado para a categoria `{category_slug}`.\n"
            f"Label: {label}\nURL: {url}\nPosição: {weight}{position_note}",
            parse_mode="Markdown",
            reply_markup=_build_main_menu(),
        )
        context.user_data.pop(STATE_KEY, None)



def register_menu_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("start", start_command, filters=filters.ChatType.PRIVATE))
    application.add_handler(CallbackQueryHandler(menu_callback, pattern=f"^{MENU_PREFIX}"))
    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.TEXT & (~filters.COMMAND),
            menu_text_handler,
        )
    )

