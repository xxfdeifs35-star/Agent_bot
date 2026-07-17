from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from datetime import datetime, timedelta
import random

TOKEN = "8681929189:AAGR7Y-v1ohOTmyVrYhl2ugZrGsw06VDqbo"

# Хранилище данных
user_messages = {}
profanity_on = False
adult_filter_on = False

# --- ЭТО НОВАЯ ФУНКЦИЯ (ВСТАВЛЯЕТЕ СЮДА) ---
async def set_commands(app):
    commands = [
        ("start", "Открыть главное меню"),
        ("menu", "Вернуться в главное меню"),
        ("game", "Открыть меню игр"),
        ("rules", "Показать правила сообщества"),
        ("about", "Информация о боте"),
        ("features", "Возможности бота"),
        ("commands", "Команды модерации"),
        ("warn", "Выдать предупреждение"),
        ("clearwarns", "Очистить предупреждения"),
        ("mute", "Выдать временный мут"),
        ("unmute", "Снять мут"),
        ("ban", "Заблокировать пользователя"),
        ("kick", "Исключить пользователя"),
        ("unban", "Разблокировать пользователя"),
        ("setrank", "Назначить ранг"),
        ("rank", "Показать ранг пользователя"),
        ("delrank", "Снять ранг"),
        ("links_on", "Включить фильтр ссылок"),
        ("links_off", "Отключить фильтр ссылок"),
        ("badwords_on", "Включить фильтр мата"),
        ("badwords_off", "Отключить фильтр мата"),
        ("addword", "Добавить запрещённое слово"),
        ("delword", "Удалить запрещённое слово"),
        ("allowdomain", "Разрешить домен"),
        ("deldomain", "Удалить разрешённый домен"),
        ("domains", "Список разрешённых доменов"),
        ("antiflood_on", "Включить антифлуд"),
        ("antiflood_off", "Отключить антифлуд"),
        ("anticaps_on", "Включить антикапс"),
        ("anticaps_off", "Отключить антикапс"),
    ]
    await app.bot.set_my_commands(commands)

# --- ДАЛЬШЕ ИДУТ ВСЕ ОСТАЛЬНЫЕ ФУНКЦИИ (start, menu, about_callback и т.д.) ---


# --- НОВЫЕ ПЕРЕМЕННЫЕ ДЛЯ МОДЕРАЦИИ ---
warns = {}
muted_users = {}
ranks = {}
links_filter_on = False
antiflood_on = False
anticaps_on = False
flood_tracker = {}
# --- ПЕРЕМЕННЫЕ ДЛЯ ИГРЫ "МАЙНЕР БИТКОЙНА" ---
bitcoin_miners = {}  # {user_id: {"btc": 0, "budget": 1000, "farms": [0,0,0,0,0]}}
bitcoin_price = 0
bitcoin_images = [
    "https://i.ibb.co/Zz2YpzFZ/1.jpg",
    "https://i.ibb.co/1GRNGcjL/2.jpg",
    "https://i.ibb.co/0yW6NXR2/3.jpg",
    "https://i.ibb.co/Qjp4ZK8X/4.jpg"
]
farm_images = [
    "https://i.ibb.co/Zz2YpzFZ/1.jpg",
    "https://i.ibb.co/1GRNGcjL/2.jpg",
    "https://i.ibb.co/0yW6NXR2/3.jpg",
    "https://i.ibb.co/Qjp4ZK8X/4.jpg"
]

# Данные ферм: [название, добыча в час, цена]
farms_data = [
    ["🖥️ Ферма 1 (Lv.1)", 0.00134, 150000],
    ["🖥️ Ферма 2 (Lv.2)", 0.00341, 500000],
    ["🖥️ Ферма 3 (Lv.3)", 0.00711, 250000000],
    ["🖥️ Ферма 4 (Lv.4)", 0.01014, 500000000],
    ["🖥️ Ферма 5 (Lv.5)", 0.05340, 1000000000]
]


# --- ГЛАВНОЕ МЕНЮ ---
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, есть ли сообщение
    if not update.message:
        return
    
    keyboard = [
        [InlineKeyboardButton("⛏️ Майнер Биткойна", callback_data="bitcoin_game")],
        [InlineKeyboardButton("🛡️ Модерация", callback_data="moderation_menu")],
        [InlineKeyboardButton("📋 Команды", callback_data="commands_menu")],
        [InlineKeyboardButton("📜 Правила", callback_data="rules")],
        [InlineKeyboardButton("🚀 Возможности", callback_data="features")],
        [InlineKeyboardButton("ℹ️ О боте", callback_data="about")],
        [InlineKeyboardButton("➕ Добавить бота в группу", url="https://t.me/AgentTCK_bot?startgroup=true")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = """🏠 **Главное меню**

⛏️ Добро пожаловать в мир криптовалют!

Выберите раздел:"""

    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
# --- О БОТЕ (кнопка) ---
async def about_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🏠 Назад в меню", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = """🤖 **АГЕНТ ТЦК**

Современный помощник для защиты
и управления Telegram-сообществами.

━━━━━━━━━━━━━━━━━━

**Версия:** 1.0 Alpha
**Статус:** 🟢 Работает
**Платформа:** Telebot Creator

Бот помогает администрации бороться
со спамом, рекламой и нарушителями.

🛡️ **Основные функции:**
• Анти-спам (повторы сообщений)
• Фильтр матов
• Фильтр 18+ контента
• Статистика пользователей
• Игры для группы

🚧 Проект находится в разработке.
Новые функции уже в пути!

━━━━━━━━━━━━━━━━━━
© 2026 Agent TCK Team"""

    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
#menu callback
async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🎮 Игры", callback_data="games_menu")],
        [InlineKeyboardButton("🛡️ Модерация", callback_data="moderation_menu")],
        [InlineKeyboardButton("📋 Команды", callback_data="commands_menu")],
        [InlineKeyboardButton("📜 Правила", callback_data="rules")],
        [InlineKeyboardButton("🚀 Возможности", callback_data="features")],
        [InlineKeyboardButton("ℹ️ О боте", callback_data="about")],
        [InlineKeyboardButton("➕ Добавить бота в группу", url="https://t.me/AgentTCK_bot?startgroup=true")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text("🏠 **Главное меню**\n\nВыберите раздел:", reply_markup=reply_markup, parse_mode='Markdown')
    except:
        await query.message.reply_text("🏠 **Главное меню**\n\nВыберите раздел:", reply_markup=reply_markup, parse_mode='Markdown')
    
async def moderation_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🚫 Фильтр матов", callback_data="badwords_menu")],
        [InlineKeyboardButton("🔗 Фильтр ссылок", callback_data="links_menu")],
        [InlineKeyboardButton("🌊 Антифлуд", callback_data="antiflood_menu")],
        [InlineKeyboardButton("🔞 18+ фильтр", callback_data="adult_menu")],
        [InlineKeyboardButton("🏠 Назад", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text("🛡️ **Модерация**\n\nВыберите раздел:", reply_markup=reply_markup, parse_mode='Markdown')

async def commands_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🏠 Назад", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = """📋 **Доступные команды:**

**🎮 Игры:**
/game — Открыть меню игр

**🛡️ Модерация:**
/warn — Выдать предупреждение
/clearwarns — Очистить предупреждения
/mute — Выдать временный мут
/unmute — Снять мут
/ban — Заблокировать пользователя
/kick — Исключить пользователя
/unban — Разблокировать пользователя

**👑 Ранги:**
/setrank — Назначить ранг
/rank — Показать ранг пользователя
/delrank — Снять ранг

**🚫 Фильтры:**
/links_on — Включить фильтр ссылок
/links_off — Отключить фильтр ссылок
/badwords_on — Включить фильтр мата
/badwords_off — Отключить фильтр мата
/addword — Добавить запрещённое слово
/delword — Удалить запрещённое слово

**🌊 Защита от спама:**
/antiflood_on — Включить антифлуд
/antiflood_off — Отключить антифлуд
/anticaps_on — Включить антикапс
/anticaps_off — Отключить антикапс

**ℹ️ Другое:**
/start — Открыть главное меню
/rules — Показать правила сообщества
/about — Информация о боте
/menu — Вернуться в главное меню
/features — Возможности бота
/commands — Команды модерации"""

    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# --- ПРАВИЛА (кнопка) ---
async def rules_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [[InlineKeyboardButton("🏠 Назад", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = """📜 **Правила сообщества:**

1️⃣ **Не спамить** — повторяющиеся сообщения удаляются
2️⃣ **Не материться** — фильтр матов
3️⃣ **Не флудить** — антифлуд
4️⃣ **Уважать друг друга** — без оскорблений
5️⃣ **Запрещена реклама** — фильтр ссылок

🚫 Нарушение правил = предупреждение или бан!"""
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# --- ВОЗМОЖНОСТИ (кнопка) ---
async def features_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [[InlineKeyboardButton("🏠 Назад", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = """🚀 **Возможности бота:**

⛏️ **Игры:**
• Майнер Биткойна

🛡️ **Модерация:**
• Фильтр матов
• Фильтр ссылок
• Антифлуд
• Антикапс

👑 **Ранги:**
• Назначение/снятие рангов

📊 **Статистика:**
• Информация о пользователе

💬 **Команды без /:**
• напиши "ранг" — узнать свой ранг
• ответь на сообщение и напиши "мут" — замутить
• ответь на сообщение и напиши "варн" — предупреждение
• напиши "бан @username" — заблокировать
• напиши "кик @username" — исключить"""
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
# --- ФИЛЬТРЫ ---
async def profanity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global profanity_on
    profanity_on = True
    await update.message.reply_text("🚫 Фильтр матов ВКЛЮЧЕН")

async def unprofanity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global profanity_on
    profanity_on = False
    await update.message.reply_text("✅ Фильтр матов ВЫКЛЮЧЕН")

async def on18(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global adult_filter_on
    adult_filter_on = True
    await update.message.reply_text("🔞 Фильтр 18+ ВКЛЮЧЕН")

async def un18(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global adult_filter_on
    adult_filter_on = False
    await update.message.reply_text("✅ Фильтр 18+ ВЫКЛЮЧЕН")
    
# --- ИГРА "МАЙНЕР БИТКОЙНА" ---
async def bitcoin_game_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    
    user_id = update.effective_user.id
    
    # Инициализация данных игрока
    if user_id not in bitcoin_miners:
        bitcoin_miners[user_id] = {
            "btc": 0.0,
            "budget": 1000.0,
            "farms": [0, 0, 0, 0, 0]
        }
    
    global bitcoin_price
    bitcoin_price = round(random.uniform(45000, 75000), 2)
    
    # Рандомная картинка
    img = random.choice(bitcoin_images)
    
    player = bitcoin_miners[user_id]
    total_farms = sum(player["farms"])
    total_hash = sum([player["farms"][i] * farms_data[i][1] for i in range(5)])
    total_hash = round(total_hash, 8)
    
    keyboard = [
        [InlineKeyboardButton("📊 Инфо", callback_data="btc_info")],
        [InlineKeyboardButton("💰 Купить BTC", callback_data="btc_buy")],
        [InlineKeyboardButton("🔄 Обновить курс", callback_data="bitcoin_game")],
        [InlineKeyboardButton("🏠 Назад в меню", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"""⛏️ **Майнер Биткойна**

💰 **Курс BTC:** ${bitcoin_price:,.2f}
₿ **Ваши BTC:** {player['btc']:.8f}
💵 **Бюджет:** ${player['budget']:,.2f}

━━━━━━━━━━━━━━━━━━
⚡ **Фермы:** {total_farms}
⏱️ **Добыча в час:** {total_hash:.8f} BTC
━━━━━━━━━━━━━━━━━━

💡 Нажмите "Инфо" для правил игры
🔄 Нажмите "Обновить курс" для смены картинки"""

    try:
        # Сначала отправляем КАРТИНКУ
        await query.message.reply_photo(img)
        # Потом отправляем ТЕКСТ с кнопками
        await query.edit_message_text(
            text, 
            reply_markup=reply_markup, 
            parse_mode='Markdown'
        )
    except Exception as e:
        # Если не получилось отредактировать - отправляем новым сообщением
        await query.message.reply_photo(img)
        await query.message.reply_text(
            text, 
            reply_markup=reply_markup, 
            parse_mode='Markdown'
        )
        
# --- СТАРТ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, есть ли сообщение
    if not update.message:
        return
    
    keyboard = [
        [InlineKeyboardButton("🏠 Перейти в меню", callback_data="main_menu")],
        [InlineKeyboardButton("➕ Присоединить в группу", url="https://t.me/AgentTCK_bot?startgroup=true")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = """🤖 **Привет! Я Агент ТЦК!**

⛏️ Добро пожаловать в мир криптовалют!

Я — современный помощник для защиты и управления Telegram-сообществами, а также твой гид в мире Биткойна!

Нажмите кнопку ниже, чтобы открыть меню или нажмите ещё ниже чтобы добавить бота в вашу группу"""

    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# --- ИНФО ОБ ИГРЕ ---
async def btc_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="bitcoin_game")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = """📖 **Правила игры:**

1️⃣ **Стартовый бюджет:** $1,000
2️⃣ **Курс BTC** обновляется каждые 5 минут (от $45,000 до $75,000)
3️⃣ **Покупай фермы** для добычи BTC:
   • Ферма 1: 0.00134 BTC/час → $150,000
   • Ферма 2: 0.00341 BTC/час → $500,000
   • Ферма 3: 0.00711 BTC/час → $250,000,000
   • Ферма 4: 0.01014 BTC/час → $500,000,000
   • Ферма 5: 0.05340 BTC/час → $1,000,000,000
4️⃣ **Продавай BTC** по текущему курсу
5️⃣ **Цель:** стать миллиардером! 🚀

💡 Чем больше ферм — тем больше BTC в час!"""

    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# --- ПОКУПКА BTC ---
async def btc_buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("⭐ 5 звёзд → $10,000", callback_data="buy_btc_5")],
        [InlineKeyboardButton("⭐ 15 звёзд → $50,000", callback_data="buy_btc_15")],
        [InlineKeyboardButton("⭐ 25 звёзд → $100,000", callback_data="buy_btc_25")],
        [InlineKeyboardButton("⭐ 40 звёзд → $500,000", callback_data="buy_btc_40")],
        [InlineKeyboardButton("⭐ 75 звёзд → $1,000,000", callback_data="buy_btc_75")],
        [InlineKeyboardButton("⭐ 95 звёзд → $5,000,000", callback_data="buy_btc_95")],
        [InlineKeyboardButton("🔙 Назад", callback_data="bitcoin_game")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "💰 **Покупка BTC за звёзды:**\n\nВыберите сумму:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        user = update.effective_user
        name = user.full_name
        username = f"@{user.username}" if user.username else "нет"
        await update.message.reply_text(
            f"📊 **Информация о тебе:**\n"
            f"Имя: {name}\n"
            f"Юзернейм: {username}\n"
            f"ID: `{user.id}`",
            parse_mode='Markdown'
        )
    else:
        name = ' '.join(context.args)
        await update.message.reply_text(f"🔍 Ищу: {name}... (в разработке)")

# --- СТАРТ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    
    keyboard = [
        [InlineKeyboardButton("🏠 Перейти в меню", callback_data="main_menu")],
        [InlineKeyboardButton("➕ Присоединить в группу", url="https://t.me/AgentTCK_bot?startgroup=true")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = """🤖 **Привет! Я Агент ТЦК!**

⛏️ Добро пожаловать в мир криптовалют!

Я — современный помощник для защиты и управления Telegram-сообществами, а также твой гид в мире Биткойна!

Нажмите кнопку ниже, чтобы открыть меню или нажмите ещё ниже чтобы добавить бота в вашу группу"""

    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
# --- АНТИ-СПАМ ---
async def check_duplicates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == 'private':
        return
    
    user_id = update.effective_user.id
    now = datetime.now()
    
    text = ""
    if update.message.text:
        text = update.message.text
    elif update.message.caption:
        text = update.message.caption
    
    if profanity_on and text:
        bad_words = ['хуй', 'пизда', 'бля', 'сука', 'залупа', 'ебать']
        if any(word in text.lower() for word in bad_words):
            await update.message.delete()
            await update.message.reply_text(f"🚫 {update.effective_user.first_name}, маты запрещены!")
            return
    
    msg_id = None
    msg_type = "unknown"
    
    if update.message.text:
        msg_id = update.message.text
        msg_type = "text"
    elif update.message.sticker:
        msg_id = update.message.sticker.file_unique_id
        msg_type = "sticker"
    elif update.message.animation:
        msg_id = update.message.animation.file_unique_id
        msg_type = "gif"
    else:
        return
    
    key = f"{user_id}_{msg_type}_{msg_id}"
    
    if key not in user_messages:
        user_messages[key] = []
    
    user_messages[key] = [t for t in user_messages[key] if now - t < timedelta(minutes=30)]
    user_messages[key].append(now)
    
    if len(user_messages[key]) > 3:
        await update.message.delete()
        await update.message.reply_text(f"⚠️ {update.effective_user.first_name}, не спамь!")
        user_messages[key] = []

async def handle_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.text and update.message.text.startswith('/'):
        return
    await check_duplicates(update, context)

async def games_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("⛏️ Майнер Биткойна", callback_data="bitcoin_game")],
        [InlineKeyboardButton("🏠 Назад", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text("🎮 **Меню игр**\n\nВыберите игру:", reply_markup=reply_markup, parse_mode='Markdown')
     
# --- ОБРАБОТКА КОМАНД БЕЗ / (текстом) ---
async def handle_text_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    text = update.message.text.lower().strip()
    user = update.effective_user
    chat = update.effective_chat
    
    # Ответ на сообщение (если есть)
    reply_to = update.message.reply_to_message
    target_user = reply_to.from_user if reply_to else None
    
    # --- КОМАНДЫ БЕЗ / ---
    if text == "ранг":
        if target_user:
            await update.message.reply_text(f"👑 Ранг пользователя {target_user.full_name}: Новичок")
        else:
            await update.message.reply_text(f"👑 Твой ранг: Новичок")
    
    elif text == "снять ранг":
        if target_user:
            await update.message.reply_text(f"✅ Ранг снят с {target_user.full_name}")
        else:
            await update.message.reply_text("❌ Ответьте на сообщение пользователя, чтобы снять ранг")
    
    elif text.startswith("бан "):
        name = text[4:].strip()
        if name:
            await update.message.reply_text(f"🔨 Пользователь {name} заблокирован!")
        else:
            await update.message.reply_text("❌ Укажите пользователя: бан @username")
    
    elif text.startswith("кик "):
        name = text[4:].strip()
        if name:
            await update.message.reply_text(f"👢 Пользователь {name} исключён!")
        else:
            await update.message.reply_text("❌ Укажите пользователя: кик @username")
    
    elif text == "мут":
        if target_user:
            await update.message.reply_text(f"🔇 {target_user.full_name} замучен на 5 минут!")
        else:
            await update.message.reply_text("❌ Ответьте на сообщение пользователя, чтобы замутить")
    
    elif text == "размут":
        if target_user:
            await update.message.reply_text(f"🔊 {target_user.full_name} размучен!")
        else:
            await update.message.reply_text("❌ Ответьте на сообщение пользователя, чтобы размутить")
    
    elif text == "варн":
        if target_user:
            await update.message.reply_text(f"⚠️ {target_user.full_name} получил предупреждение!")
        else:
            await update.message.reply_text("❌ Ответьте на сообщение пользователя, чтобы выдать предупреждение")
    
    elif text == "очистить варны":
        if target_user:
            await update.message.reply_text(f"✅ Предупреждения {target_user.full_name} очищены!")
        else:
            await update.message.reply_text("❌ Ответьте на сообщение пользователя")
    
    elif text == "правила":
        rules_text = """📜 **Правила сообщества:**

1️⃣ Не спамить
2️⃣ Не материться
3️⃣ Не флудить
4️⃣ Уважать друг друга
5️⃣ Запрещена реклама

Нарушение правил = предупреждение или бан!"""
        await update.message.reply_text(rules_text, parse_mode='Markdown')
    
    elif text == "возможности":
        features_text = """🚀 **Возможности бота:**

🎮 **Игры:**
• Угадай число

🛡️ **Модерация:**
• Фильтр матов
• Фильтр ссылок
• Антифлуд
• Антикапс

👑 **Ранги:**
• Назначение/снятие рангов

📊 **Статистика:**
• Информация о пользователе"""
        await update.message.reply_text(features_text, parse_mode='Markdown')

# --- ОСНОВНАЯ ФУНКЦИЯ ---
def main():
    app = Application.builder().token(TOKEN).build()
    
    # Настройка кнопки меню (синхронно)
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(set_commands(app))
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("profanity", profanity))
    app.add_handler(CommandHandler("unprofanity", unprofanity))
    app.add_handler(CommandHandler("on18", on18))
    app.add_handler(CommandHandler("un18", un18))
    app.add_handler(CommandHandler("info", info))
    
    # Обработка кнопок
    app.add_handler(CallbackQueryHandler(about_callback, pattern="about"))
    app.add_handler(CallbackQueryHandler(main_menu_callback, pattern="main_menu"))
    app.add_handler(CallbackQueryHandler(games_menu_callback, pattern="games_menu"))
    app.add_handler(CallbackQueryHandler(moderation_menu_callback, pattern="moderation_menu"))
    app.add_handler(CallbackQueryHandler(commands_menu_callback, pattern="commands_menu"))
    app.add_handler(CallbackQueryHandler(rules_callback, pattern="rules"))
    app.add_handler(CallbackQueryHandler(features_callback, pattern="features"))
    app.add_handler(CallbackQueryHandler(bitcoin_game_callback, pattern="bitcoin_game"))
    app.add_handler(CallbackQueryHandler(btc_info_callback, pattern="btc_info"))
    app.add_handler(CallbackQueryHandler(btc_buy_callback, pattern="btc_buy"))
    
    # Обработка текстовых команд (без /)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_commands))
    # Обработка остальных сообщений (стикеры, GIF)
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND & ~filters.TEXT, handle_all))
    
    print("🤖 Бот Агент ТЦК запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
