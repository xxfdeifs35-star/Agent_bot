from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from datetime import datetime, timedelta
import random

TOKEN = "8681929189:AAGR7Y-v1ohOTmyVrYhl2ugZrGsw06VDqbo"

# Хранилище данных
user_messages = {}
profanity_on = False
adult_filter_on = False


# --- ДАЛЬШЕ ИДУТ ВСЕ ОСТАЛЬНЫЕ ФУНКЦИИ (start, menu, about_callback и т.д.) ---
# --- НАСТРОЙКА КНОПКИ МЕНЮ ---
async def set_commands(app):
    commands = [
        ("start", "Открыть главное меню"),
        ("menu", "Вернуться в главное меню"),
        ("rules", "Правила сообщества"),
        ("about", "Информация о боте"),
        ("features", "Возможности бота"),
        ("commands", "Команды модерации"),
        ("ban", "Заблокировать пользователя"),
        ("kick", "Исключить пользователя"),
        ("mute", "Замутить пользователя"),
        ("unmute", "Размутить пользователя"),
        ("warn", "Выдать предупреждение"),
        ("clearwarns", "Очистить предупреждения"),
        ("setrank", "Назначить ранг"),
        ("rank", "Показать ранг"),
        ("delrank", "Снять ранг"),
        ("anticaps_on", "Включить антикапс"),
        ("anticaps_off", "Отключить антикапс"),
        ("antiflood_on", "Включить антифлуд"),
        ("antiflood_off", "Отключить антифлуд"),
        ("links_on", "Включить фильтр ссылок"),
        ("links_off", "Отключить фильтр ссылок"),
    ]
    await app.bot.set_my_commands(commands)

# --- НОВЫЕ ПЕРЕМЕННЫЕ ДЛЯ МОДЕРАЦИИ ---
warns = {}
muted_users = {}
ranks = {}
links_filter_on = False
antiflood_on = False
anticaps_on = False
flood_tracker = {}

# --- 150+ МАТЕРНЫХ СЛОВ ---
bad_words = [
    # === ОСНОВНЫЕ МАТЫ (50+) ===
    'хуй', 'хуи', 'хуя', 'хую', 'хуем', 'хуе', 'хуйня', 'хуйло', 'хуйню',
    'пизда', 'пизде', 'пизду', 'пиздой', 'пиздец', 'пиздить', 'пиздюк',
    'бля', 'блять', 'блядь', 'бляд', 'блядский', 'блядство', 'блядун',
    'сука', 'суки', 'суке', 'суку', 'сукой', 'сучара', 'сучий', 'сукин',
    'залупа', 'залупе', 'залупой', 'залупный',
    'ебать', 'ебат', 'ебал', 'ебала', 'ебало', 'ебану', 'ебанутый', 'ебануться',
    'ёбаный', 'ёбанный', 'ёбань', 'ёбнул', 'ёбнутый',
    'еблан', 'ебланище', 'ебло', 'ебучий', 'ебущий', 'ебеня',
    'нахуй', 'похуй', 'схуй', 'дохуя', 'охуеть', 'охуительный', 'охуенно',
    'пиздец', 'пиздить', 'пиздюк', 'пиздабол', 'пиздатый',
    'пидор', 'пидорас', 'пидрила', 'пидрище', 'пидорнутый',
    'гандон', 'гандонский', 'гандоновский',
    'мудила', 'мудище', 'мудень', 'мудят', 'мудильник',
    'мудак', 'мудачье', 'мудацкий', 'мудовозка',
    'ссать', 'ссышь', 'ссыт', 'ссань', 'ссанина', 'ссучий',
    'срать', 'срите', 'срал', 'срала', 'срач', 'срань', 'сраный',
    'говно', 'говнище', 'говнюк', 'говнар', 'говняный', 'говённый',
    'дерьмо', 'дерьмовий', 'дерьмовый', 'дерьмяный',
    'пездюк', 'паскуда', 'паскуда', 'тварь', 'твари', 'тварюга', 'тварюшка',
    'выблядок', 'блядский', 'блядун', 'блядовитый',
    'заебать', 'заебало', 'заебись', 'заебон', 'заебулька',
    'наеб', 'наебать', 'наебка', 'наебщик',
    'проебать', 'проебали', 'проебал', 'проебон',
    'уебок', 'уебище', 'уёбищный', 'уебан',
    'хер', 'херня', 'херовий', 'херовый', 'херь', 'херануть', 'херасе',
    'хрен', 'хреново', 'хреновый', 'хрень', 'хреновина',
    'долбоёб', 'долбаёб', 'долбодятел', 'долбоящер',
    'даун', 'даунище', 'даунячий', 'даунский',
    'дебил', 'дебилище', 'дебильный', 'дебилизм',
    'идиот', 'идиотище', 'идиотский', 'идиотина',
    'кретин', 'кретинище', 'кретинский', 'кретинизм',
    'олух', 'олуховый', 'олуховатый', 'олухованский',
    'лох', 'лохня', 'лоховский', 'лохотрон', 'лошара',
    'чмо', 'чмошник', 'чмодрочер', 'чмокалка',
    'шлюха', 'шлюшка', 'шлюшище', 'шлюхадра',
    
    # === С ЗАМЕНОЙ БУКВ (30+) ===
    'xуй', 'xуи', 'xуя', 'xую', 'xуем', 'xуе',
    'пuзда', 'пuзде', 'пuзду', 'пuздой',
    'бляmь', 'бляm', 'блядu',
    'сyка', 'сyки', 'сyке', 'сyку', 'сyкой',
    'зaлупa', 'зaлупе', 'зaлупой',
    'eбaть', 'eбaт', 'eбaл', 'eбaлa',
    'нaхуй', 'пoхуй', 'дoxуя',
    'пuздец', 'пuздить', 'пuздюк',
    'пuдор', 'пuдорас', 'гaндон',
    'мyдилa', 'мyдень', 'мyдяm',
    'мyдaк', 'мyдaцкий',
    'cpaть', 'ccать', 'cpaл', 'cpaч',
    'гoвнo', 'гoвнюк', 'гoвнище',
    'дepьмo', 'дepьмовый',
    'твapь', 'твapюгa',
    'выблядoк', 'блядcкий',
    'зaeбaть', 'зaeбaлo', 'зaeбиcь',
    'нaеб', 'нaeбaть', 'пpoeбaть',
    'yeбoк', 'yeбищe', 'yeбaн',
    'хep', 'хepня', 'хepовый',
    'хpeн', 'хpeнoвo', 'хpeнь',
    'дoлбoeб', 'дoлбaеб',
    'дayн', 'дayнищe',
    'дeбил', 'дeбильный',
    'идuoт', 'идuoтищe',
    'кpeтин', 'кpeтинизм',
    'oлyx', 'oлyxoвый',
    'лox', 'лoxoтpoн',
    'чмo', 'чмoшник',
    'шлюxa', 'шлюшкa',
    'e6aть', 'e6aт', 'e6aл',
    'xoй', 'xои', 'xоя',
]

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
    
    # --- АНТИКАПС ---
async def anticaps_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global anticaps_on
    anticaps_on = True
    await update.message.reply_text("🔠 Антикапс ВКЛЮЧЕН (сообщения с большим количеством заглавных букв будут удаляться)")

async def anticaps_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global anticaps_on
    anticaps_on = False
    await update.message.reply_text("🔠 Антикапс ВЫКЛЮЧЕН")

# --- АНТИФЛУД ---
async def antiflood_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global antiflood_on
    antiflood_on = True
    await update.message.reply_text("🌊 Антифлуд ВКЛЮЧЕН (сообщения чаще 5 раз в 10 секунд будут удаляться)")

async def antiflood_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global antiflood_on
    antiflood_on = False
    await update.message.reply_text("🌊 Антифлуд ВЫКЛЮЧЕН")

# --- ФИЛЬТР ССЫЛОК ---
async def links_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global links_filter_on
    links_filter_on = True
    await update.message.reply_text("🔗 Фильтр ссылок ВКЛЮЧЕН")

async def links_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global links_filter_on
    links_filter_on = False
    await update.message.reply_text("🔗 Фильтр ссылок ВЫКЛЮЧЕН")

# --- БЛОКИРОВКА/РАЗБЛОКИРОВКА (для групп) ---
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответьте на сообщение пользователя, чтобы забанить")
        return
    
    user_id = update.message.reply_to_message.from_user.id
    try:
        await update.effective_chat.ban_member(user_id)
        await update.message.reply_text(f"🔨 Пользователь заблокирован!")
    except:
        await update.message.reply_text("❌ Недостаточно прав или пользователь админ")

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответьте на сообщение пользователя, чтобы разблокировать")
        return
    
    user_id = update.message.reply_to_message.from_user.id
    try:
        await update.effective_chat.unban_member(user_id)
        await update.message.reply_text(f"🔓 Пользователь разблокирован!")
    except:
        await update.message.reply_text("❌ Недостаточно прав")

async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответьте на сообщение пользователя, чтобы кикнуть")
        return
    
    user_id = update.message.reply_to_message.from_user.id
    try:
        await update.effective_chat.ban_member(user_id)
        await update.effective_chat.unban_member(user_id)
        await update.message.reply_text(f"👢 Пользователь исключён!")
    except:
        await update.message.reply_text("❌ Недостаточно прав")

# --- МУТ/РАЗМУТ ---
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответьте на сообщение пользователя, чтобы замутить")
        return
    
    user_id = update.message.reply_to_message.from_user.id
    try:
        await update.effective_chat.restrict_member(user_id, permissions={'can_send_messages': False})
        await update.message.reply_text(f"🔇 Пользователь замучен!")
    except:
        await update.message.reply_text("❌ Недостаточно прав")

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответьте на сообщение пользователя, чтобы размутить")
        return
    
    user_id = update.message.reply_to_message.from_user.id
    try:
        await update.effective_chat.restrict_member(user_id, permissions={'can_send_messages': True})
        await update.message.reply_text(f"🔊 Пользователь размучен!")
    except:
        await update.message.reply_text("❌ Недостаточно прав")

# --- ПРЕДУПРЕЖДЕНИЯ ---
async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответьте на сообщение пользователя, чтобы выдать предупреждение")
        return
    
    user_id = update.message.reply_to_message.from_user.id
    user_name = update.message.reply_to_message.from_user.full_name
    
    if user_id not in warns:
        warns[user_id] = 0
    warns[user_id] += 1
    
    await update.message.reply_text(f"⚠️ {user_name} получил предупреждение! ({warns[user_id]}/3)")
    
    if warns[user_id] >= 3:
        try:
            await update.effective_chat.ban_member(user_id)
            await update.message.reply_text(f"🔨 {user_name} забанен за 3 предупреждения!")
        except:
            await update.message.reply_text("❌ Недостаточно прав для бана")

async def clearwarns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответьте на сообщение пользователя")
        return
    
    user_id = update.message.reply_to_message.from_user.id
    if user_id in warns:
        warns[user_id] = 0
        await update.message.reply_text(f"✅ Предупреждения очищены!")
    else:
        await update.message.reply_text("❌ У пользователя нет предупреждений")

# --- РАНГИ ---
async def setrank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответьте на сообщение пользователя")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Укажите ранг: /setrank Новичок")
        return
    
    user_id = update.message.reply_to_message.from_user.id
    rank_name = ' '.join(context.args)
    ranks[user_id] = rank_name
    await update.message.reply_text(f"👑 Ранг '{rank_name}' назначен!")

async def rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.reply_to_message:
        user_id = update.message.reply_to_message.from_user.id
        user_name = update.message.reply_to_message.from_user.full_name
        rank_name = ranks.get(user_id, "Новичок")
        await update.message.reply_text(f"👑 Ранг {user_name}: {rank_name}")
    else:
        user_id = update.effective_user.id
        rank_name = ranks.get(user_id, "Новичок")
        await update.message.reply_text(f"👑 Твой ранг: {rank_name}")

async def delrank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответьте на сообщение пользователя")
        return
    
    user_id = update.message.reply_to_message.from_user.id
    if user_id in ranks:
        del ranks[user_id]
        await update.message.reply_text(f"✅ Ранг снят!")
    else:
        await update.message.reply_text("❌ У пользователя нет ранга")

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
        
# --- ОЧИСТКА ТЕКСТА ОТ ТОЧЕК, ПОДЧЁРКИВАНИЙ И ЗАМЕНА БУКВ ДЛЯ ПРОВЕРКИ МАТОВ ---
def clean_text_for_badwords(text):
    # Удаляем точки, нижние подчёркивания, пробелы, дефисы и другие разделители
    text = text.replace('.', '').replace('_', '').replace('-', '').replace(' ', '').replace('*', '').replace('!', '').replace('?', '').replace('(', '').replace(')', '').replace('@', '').replace('#', '').replace('$', '').replace('%', '').replace('^', '').replace('&', '')
    
    # Заменяем цифры на буквы (для обхода)
    text = text.replace('1', 'л').replace('3', 'з').replace('4', 'ч').replace('5', 'с').replace('6', 'б').replace('0', 'о')
    
    # Заменяем латиницу на кириллицу (для обхода)
    replacements = {
        'a': 'а', 'b': 'в', 'c': 'с', 'e': 'е', 'h': 'х', 'k': 'к', 
        'm': 'м', 'o': 'о', 'p': 'р', 't': 'т', 'x': 'х', 'y': 'у',
        'u': 'и', 'i': 'и', 'n': 'н', 'r': 'р', 's': 'с', 'v': 'в'
    }
    
    for lat, cyr in replacements.items():
        text = text.replace(lat, cyr)
    
    return text.lower()

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
        # Очищаем текст через функцию clean_text_for_badwords
        clean_text = clean_text_for_badwords(text)
        
        found_bad = False
        for word in bad_words:
            # Проверяем вхождение слова в очищенный текст
            if word in clean_text:
                found_bad = True
                break
            
            # Проверяем без учёта регистра
            if word in text.lower():
                found_bad = True
                break
        
        if found_bad:
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
     
# --- ОБРАБОТКА КОМАНД БЕЗ / (текстом) НА РУССКОМ ---
async def handle_text_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    text = update.message.text.lower().strip()
    reply_to = update.message.reply_to_message
    target_user = reply_to.from_user if reply_to else None
    
    # --- КОМАНДЫ НА РУССКОМ ---
    if text in ["ранг", "мой ранг", "узнать ранг"]:
        if target_user:
            user_id = target_user.id
            rank_name = ranks.get(user_id, "Новичок")
            await update.message.reply_text(f"👑 Ранг {target_user.full_name}: {rank_name}")
        else:
            user_id = update.effective_user.id
            rank_name = ranks.get(user_id, "Новичок")
            await update.message.reply_text(f"👑 Твой ранг: {rank_name}")
    
    elif text in ["снять ранг", "убрать ранг", "удалить ранг"]:
        if target_user:
            user_id = target_user.id
            if user_id in ranks:
                del ranks[user_id]
                await update.message.reply_text(f"✅ Ранг снят с {target_user.full_name}")
            else:
                await update.message.reply_text("❌ У пользователя нет ранга")
        else:
            await update.message.reply_text("❌ Ответьте на сообщение пользователя")
    
    elif text.startswith("бан ") or text.startswith("забанить "):
        name = text.replace("бан ", "").replace("забанить ", "").strip()
        if name:
            await update.message.reply_text(f"🔨 Пользователь {name} заблокирован!")
        else:
            await update.message.reply_text("❌ Укажите: бан @username")
    
    elif text.startswith("кик ") or text.startswith("выгнать ") or text.startswith("исключить "):
        name = text.replace("кик ", "").replace("выгнать ", "").replace("исключить ", "").strip()
        if name:
            await update.message.reply_text(f"👢 Пользователь {name} исключён!")
        else:
            await update.message.reply_text("❌ Укажите: кик @username")
    
    elif text in ["мут", "замутить", "заткнуть"]:
        if target_user:
            await update.message.reply_text(f"🔇 {target_user.full_name} замучен!")
        else:
            await update.message.reply_text("❌ Ответьте на сообщение пользователя")
    
    elif text in ["размут", "размутить", "отмутить"]:
        if target_user:
            await update.message.reply_text(f"🔊 {target_user.full_name} размучен!")
        else:
            await update.message.reply_text("❌ Ответьте на сообщение пользователя")
    
    elif text in ["варн", "предупреждение", "выдать варн"]:
        if target_user:
            user_id = target_user.id
            if user_id not in warns:
                warns[user_id] = 0
            warns[user_id] += 1
            await update.message.reply_text(f"⚠️ {target_user.full_name} получил предупреждение! ({warns[user_id]}/3)")
        else:
            await update.message.reply_text("❌ Ответьте на сообщение пользователя")
    
    elif text in ["очистить варны", "сбросить варны", "убрать предупреждения"]:
        if target_user:
            user_id = target_user.id
            if user_id in warns:
                warns[user_id] = 0
                await update.message.reply_text(f"✅ Предупреждения {target_user.full_name} очищены!")
            else:
                await update.message.reply_text("❌ У пользователя нет предупреждений")
        else:
            await update.message.reply_text("❌ Ответьте на сообщение пользователя")
    
    elif text in ["правила", "показать правила"]:
        rules_text = """📜 **Правила сообщества:**

1️⃣ Не спамить
2️⃣ Не материться
3️⃣ Не флудить
4️⃣ Уважать друг друга
5️⃣ Запрещена реклама

Нарушение = предупреждение или бан!"""
        await update.message.reply_text(rules_text, parse_mode='Markdown')
    
    elif text in ["возможности", "что умеешь", "функции", "команды"]:
        features_text = """🚀 **Возможности бота:**

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

💬 **Команды на русском:**
• "ранг" — узнать свой ранг
• "мут" (ответом) — замутить
• "варн" (ответом) — предупреждение
• "бан @username" — заблокировать
• "кик @username" — исключить"""
        await update.message.reply_text(features_text, parse_mode='Markdown')
        
        # --- ПРИВЕТСТВИЕ НОВЫМ УЧАСТНИКАМ ---
async def welcome_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, есть ли новые участники
    if not update.message or not update.message.new_chat_members:
        return
    
    # Проходим по всем новым участникам
    for member in update.message.new_chat_members:
        # Пропускаем ботов
        if member.is_bot:
            continue
        
        # Приветственное сообщение
        welcome_text = f"""🎉 **Добро пожаловать, {member.full_name}!**

🤖 Я — **Агент ТЦК**, твой помощник в этом чате!

📜 Ознакомься с правилами: /rules
🚀 Узнай мои возможности: /features
⛏️ Поиграй в Майнер Биткойна: /menu

Приятного общения! 🎊"""

        await update.message.reply_text(welcome_text, parse_mode='Markdown')
        
def main():
    app = Application.builder().token(TOKEN).build()
    
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
    app.add_handler(CommandHandler("anticaps_on", anticaps_on))
    app.add_handler(CommandHandler("anticaps_off", anticaps_off))
    app.add_handler(CommandHandler("antiflood_on", antiflood_on))
    app.add_handler(CommandHandler("antiflood_off", antiflood_off))
    app.add_handler(CommandHandler("links_on", links_on))
    app.add_handler(CommandHandler("links_off", links_off))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(CommandHandler("kick", kick))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("warn", warn))
    app.add_handler(CommandHandler("clearwarns", clearwarns))
    app.add_handler(CommandHandler("setrank", setrank))
    app.add_handler(CommandHandler("rank", rank))
    app.add_handler(CommandHandler("delrank", delrank))
    
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
    
    # Приветствие новых участников
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_members))
    
    # Обработка текстовых команд (без /) на русском
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_commands))
    
    # Обработка остальных сообщений (стикеры, GIF)
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND & ~filters.TEXT, handle_all))
    
    print("🤖 Бот Агент ТЦК запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
