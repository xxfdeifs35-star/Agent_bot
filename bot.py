from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import random
import logging

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = "8681929189:AAGR7Y-v1ohOTmyVrYhl2ugZrGsw06VDqbo"

players = {}  # {user_id: {"name": str, "balance": int, "games": {"uno": 0}, "wins": 0, "losses": 0}}
message_owners = {}  # {message_id: user_id}

async def set_commands(app):
    commands = [
        ("start", "🏠 Главное меню"),
        ("help", "📖 Помощь"),
        ("profile", "👤 Мой профиль"),
        ("games", "🎮 Все игры"),
        ("uno", "🃏 Играть в УНО"),
        ("top", "🏆 Рейтинг игроков"),
    ]
    await app.bot.set_my_commands(commands)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in players:
        players[user_id] = {
            "name": update.effective_user.full_name,
            "balance": 1000,
            "games": {"uno": 0},
            "wins": 0,
            "losses": 0
        }

    keyboard = [
        [InlineKeyboardButton("🎮 Игры", callback_data="games_menu")],
        [InlineKeyboardButton("👤 Профиль", callback_data="profile")],
        [InlineKeyboardButton("🏆 Рейтинг", callback_data="top")],
        [InlineKeyboardButton("📖 Помощь", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = f"""🎮 **Добро пожаловать, {players[user_id]['name']}!**

💰 Баланс: {players[user_id]['balance']} монет
🏆 Побед: {players[user_id]['wins']}
😢 Поражений: {players[user_id]['losses']}

Выбери действие:"""

    msg = await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    message_owners[msg.message_id] = user_id

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in players:
        await update.message.reply_text("❌ Ты ещё не зарегистрирован! Напиши /start")
        return

    player = players[user_id]

    text = f"""👤 **Твой профиль**

📛 Имя: {player['name']}
💰 Баланс: {player['balance']} монет
🏆 Побед: {player['wins']}
😢 Поражений: {player['losses']}

📊 Игр сыграно: {player['games']['uno']}"""

    keyboard = [[InlineKeyboardButton("🏠 В меню", callback_data="menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    message_owners[msg.message_id] = user_id

async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not players:
        await update.message.reply_text("📭 Пока нет игроков!")
        return

    sorted_players = sorted(players.items(), key=lambda x: x[1]['balance'], reverse=True)

    text = "🏆 **ТОП ИГРОКОВ**\n\n"
    for i, (uid, data) in enumerate(sorted_players[:10], 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        text += f"{medal} {data['name']} — {data['balance']} монет\n"

    keyboard = [[InlineKeyboardButton("🏠 В меню", callback_data="menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    message_owners[msg.message_id] = user_id

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """📖 **Помощь**

🃏 **УНО** — классическая карточная игра
👤 **Профиль** — твоя статистика
🏆 **Рейтинг** — топ игроков

**Скоро будут новые игры!**"""

    keyboard = [[InlineKeyboardButton("🏠 В меню", callback_data="menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    message_owners[msg.message_id] = update.effective_user.id

async def games(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """🎮 **Доступные игры**

🃏 **УНО** — классическая карточная игра

Скоро добавятся новые игры!"""

    keyboard = [
        [InlineKeyboardButton("🃏 УНО", callback_data="game_uno")],
        [InlineKeyboardButton("🏠 В меню", callback_data="menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    message_owners[msg.message_id] = update.effective_user.id

async def uno(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🃏 **Игра УНО**\n\nИгра скоро будет доступна!\nПодготовка идёт...", parse_mode='Markdown')
    message_owners[msg.message_id] = update.effective_user.id

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    msg_id = query.message.message_id

    owner = message_owners.get(msg_id)
    if owner is not None and owner != user_id:
        await query.answer("❌ Это не твоё меню!", show_alert=True)
        return

    await query.answer()
    data = query.data

    if data == "menu":
        keyboard = [
            [InlineKeyboardButton("🎮 Игры", callback_data="games_menu")],
            [InlineKeyboardButton("👤 Профиль", callback_data="profile")],
            [InlineKeyboardButton("🏆 Рейтинг", callback_data="top")],
            [InlineKeyboardButton("📖 Помощь", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if user_id in players:
            text = f"""🎮 **Главное меню**

💰 Баланс: {players[user_id]['balance']} монет
🏆 Побед: {players[user_id]['wins']}
😢 Поражений: {players[user_id]['losses']}"""
        else:
            text = "🎮 **Главное меню**"

        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    elif data == "games_menu":
        keyboard = [
            [InlineKeyboardButton("🃏 УНО", callback_data="game_uno")],
            [InlineKeyboardButton("🏠 Назад", callback_data="menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("🎮 **Выбери игру:**", reply_markup=reply_markup, parse_mode='Markdown')

    elif data == "game_uno":
        await query.edit_message_text("🃏 **Игра УНО**\n\nИгра скоро будет доступна!\nПодготовка идёт...", parse_mode='Markdown')

    elif data == "profile":
        if user_id not in players:
            await query.edit_message_text("❌ Ты ещё не зарегистрирован!", parse_mode='Markdown')
            return

        player = players[user_id]
        text = f"""👤 **Твой профиль**

📛 Имя: {player['name']}
💰 Баланс: {player['balance']} монет
🏆 Побед: {player['wins']}
😢 Поражений: {player['losses']}

📊 Игр сыграно: {player['games']['uno']}"""

        keyboard = [[InlineKeyboardButton("🏠 В меню", callback_data="menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    elif data == "top":
        sorted_players = sorted(players.items(), key=lambda x: x[1]['balance'], reverse=True)
        text = "🏆 **ТОП ИГРОКОВ**\n\n"
        for i, (uid, pdata) in enumerate(sorted_players[:10], 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            text += f"{medal} {pdata['name']} — {pdata['balance']} монет\n"

        keyboard = [[InlineKeyboardButton("🏠 В меню", callback_data="menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    elif data == "help":
        text = """📖 **Помощь**

🃏 **УНО** — классическая карточная игра
👤 **Профиль** — твоя статистика
🏆 **Рейтинг** — топ игроков

**Скоро будут новые игры!**"""

        keyboard = [[InlineKeyboardButton("🏠 В меню", callback_data="menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

def main():
    app = Application.builder().token(TOKEN).build()

    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(set_commands(app))

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CommandHandler("games", games))
    app.add_handler(CommandHandler("uno", uno))

    app.add_handler(CallbackQueryHandler(callback_handler))

    print("🎮 Бот Agent Bot запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
        
