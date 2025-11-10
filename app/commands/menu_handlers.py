from __future__ import annotations

from typing import Final

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, filters

MENU_PREFIX: Final = "menu:"


def _build_main_menu() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("Adicione-me a um grupo", callback_data=f"{MENU_PREFIX}add_to_group")],
        [InlineKeyboardButton("Grupo", callback_data=f"{MENU_PREFIX}group")],
        [InlineKeyboardButton("Canal", callback_data=f"{MENU_PREFIX}channel")],
        [InlineKeyboardButton("Suporte", callback_data=f"{MENU_PREFIX}support")],
        [InlineKeyboardButton("Informações", callback_data=f"{MENU_PREFIX}info")],
        [InlineKeyboardButton("Languages", callback_data=f"{MENU_PREFIX}languages")],
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
        "add_to_group": "Para me adicionar a um grupo, utilize o Telegram, adicione-me como admin e garanta permissões para enviar mensagens.",
        "group": "Use /setcategoria, /addmidia, /addcopy e /setbotao para configurar suas categorias e envios para grupos.",
        "channel": "Para canais, certifique-se de que o bot é administrador. Configure as categorias e associe-as ao canal desejado.",
        "support": "Precisa de ajuda? Entre em contato com o suporte ou acione o administrador configurado.",
        "info": "KingsCEO Bot permite gerenciar múltiplos bots, categorias e envios automáticos via PostgreSQL. Consulte o README para detalhes.",
        "languages": "Em breve suporte multilíngue. Por enquanto, a interface está disponível em Português.",
    }

    message = responses.get(action, "Escolha uma opção do menu.")
    await query.edit_message_text(text=message, reply_markup=_build_main_menu())


def register_menu_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("start", start_command, filters=filters.ChatType.PRIVATE))
    application.add_handler(CallbackQueryHandler(menu_callback, pattern=f"^{MENU_PREFIX}"))

