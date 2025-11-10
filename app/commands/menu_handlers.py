from __future__ import annotations

from typing import Final

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, filters

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
            "Abra o grupo ou canal no Telegram, adicione o bot e promova-o a administrador com permissão para enviar mensagens, "
            "mídias e botões. Somente assim as publicações automáticas funcionarão."
        ),
        "setcategoria": (
            "Cria uma categoria e define o slug usado nos demais comandos.\n"
            "Exemplo: `/setcategoria Coroas`\n"
            "O bot responderá com `slug=coroas`, que deve ser usado nos próximos passos."
        ),
        "addmidia": (
            "Associa mídias a uma categoria especificada pelo slug. Tipos aceitos: photo, video, document, animation.\n"
            "Exemplo: responda a uma foto e envie `/addmidia coroas photo 2` para cadastrar com peso 2.\n"
            "Quando peso não é informado, assume 1."
        ),
        "addcopy": (
            "Armazena textos que serão enviados de forma aleatória junto das mídias.\n"
            "Exemplo: `/addcopy coroas 3 Parágrafo da copy...` ou responda a uma mensagem de texto com `/addcopy coroas`.\n"
            "O peso (opcional) aumenta a chance de seleção."
        ),
        "setbotao": (
            "Registra botões inline para a categoria.\n"
            "Exemplo: `/setbotao coroas \"Assinar agora\" https://exemplo.com 2`\n"
            "Lembre-se de incluir uma URL completa (http/https). Peso opcional."
        ),
        "setboasvindas": (
            "Configura a mensagem de boas-vindas dos grupos/canais vinculados à categoria. Responda ao conteúdo desejado e use:\n"
            "`/setboasvindas coroas mode=all`\n"
            "Modos disponíveis: all, text, media, buttons, none."
        ),
    }

    message = responses.get(action, "Escolha uma opção do menu.")
    await query.edit_message_text(text=message, reply_markup=_build_main_menu())


def register_menu_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("start", start_command, filters=filters.ChatType.PRIVATE))
    application.add_handler(CallbackQueryHandler(menu_callback, pattern=f"^{MENU_PREFIX}"))

