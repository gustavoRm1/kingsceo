from __future__ import annotations

from typing import Final

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, filters
from telegram.error import BadRequest

MENU_PREFIX: Final = "menu:"


def _build_main_menu() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("Adicione-me a um grupo", callback_data=f"{MENU_PREFIX}add_to_group")],
        [InlineKeyboardButton("Criar categoria (/setcategoria)", callback_data=f"{MENU_PREFIX}setcategoria")],
        [InlineKeyboardButton("Adicionar mídia (/addmidia)", callback_data=f"{MENU_PREFIX}addmidia")],
        [InlineKeyboardButton("Adicionar copy (/addcopy)", callback_data=f"{MENU_PREFIX}addcopy")],
        [InlineKeyboardButton("Adicionar botão (/setbotao)", callback_data=f"{MENU_PREFIX}setbotao")],
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
        "addmidia": (
            "Associa mídias a uma categoria.\n"
            "1. Responda à mídia desejada ou envie a mídia junto com o comando.\n"
            "2. Execute, por exemplo: `/addmidia coroas photo 2`\n"
            "Tipos: photo, video, document, animation. Peso opcional (padrão 1)."
        ),
        "addcopy": (
            "Registra textos (copies) ligados à categoria.\n"
            "Exemplo: responda a uma mensagem de texto com `/addcopy coroas 3` para peso 3.\n"
            "Sem resposta, o texto pode ser passado após o slug."
        ),
        "setbotao": (
            "Cria botões inline para a categoria.\n"
            "Exemplo: `/setbotao coroas \"Assinar\" https://exemplo.com 2`\n"
            "A URL deve começar com http:// ou https://. Peso opcional."
        ),
        "setboasvindas": (
            "Define a mensagem de boas-vindas para grupos/canais associados.\n"
            "Responda ao conteúdo desejado (texto/mídia/botões) e envie `/setboasvindas coroas mode=all`.\n"
            "Modos: all, text, media, buttons, none."
        ),
    }

    message = responses.get(action, "Escolha uma opção do menu.")
    try:
        if query.message and query.message.text == message:
            await query.answer("Mensagem já exibida. Use o comando conforme orientação.", show_alert=False)
            return
        await query.edit_message_text(text=message, reply_markup=_build_main_menu())
    except BadRequest as exc:  # pragma: no cover - cenário interativo
        if "Message is not modified" in str(exc):
            await query.answer("Mensagem já exibida. Use o comando conforme orientação.", show_alert=False)
        else:
            raise


def register_menu_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("start", start_command, filters=filters.ChatType.PRIVATE))
    application.add_handler(CallbackQueryHandler(menu_callback, pattern=f"^{MENU_PREFIX}"))

