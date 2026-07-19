from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ChatMemberHandler, MessageHandler, filters, ContextTypes
)
import random
import logging
import time
import asyncio
import json
import os

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = "8681929189:AAGR7Y-v1ohOTmyVrYhl2ugZrGsw06VDqbo"

players = {}          # {user_id: {"name", "balance", "games": {"uno": 0}, "wins", "losses"}}
username_to_id = {}    # {username_lowercase: user_id} -- для поиска по @username
message_owners = {}   # {message_id: user_id}  -- non-uno menu lock
games_uno = {}         # {chat_id: game_state}
games_coin = {}        # {chat_id: {"host","bet","status","message_id"}}
games_roulette = {}    # {chat_id: game_state}
games_cookies = {}     # {chat_id: game_state}
chat_players = {}      # {chat_id: set(user_id)} -- кто играл в этом чате

MAX_PLAYERS = 4
MIN_PLAYERS = 2
MAX_ROULETTE = 6
MIN_ROULETTE = 2
COOKIES_TOTAL = 30
PAY_LIMIT = 45000
CREDIT_MAX = 300000
BANKER_USERNAME = "SANS_ZM"
CREDIT_COMMISSION = 0.15
CREDIT_MINUTES = 30
USD_START_RATE = 44.0
USD_UPDATE_SECONDS = 120
USD_MAX_CHANGE = 0.15
BTC_START_RATE = 60000.0
BTC_MAX_CHANGE = 0.10
MIN_DICE = 2
MAX_DICE = 6
DATA_FILE = "bot_data.json"
AUTOSAVE_SECONDS = 15

credits = {}  # {user_id: {"amount": int, "taken_at": ts, "chat_id": int}}
usd_rate = USD_START_RATE  # монет за 1 доллар
btc_rate = BTC_START_RATE  # долларов за 1 BTC
games_dice = {}  # {chat_id: game_state}

# ================= БОТЫ-ИГРОКИ (ИИ ОППОНЕНТЫ) =================

BOT_NAME_POOL = ["Вася", "Петя", "Коля", "Дима", "Женя", "Саня", "Игорь", "Толя"]
_bot_id_counter = 0

def is_bot(uid):
    return uid < 0

def create_bot_player():
    global _bot_id_counter
    _bot_id_counter -= 1
    uid = _bot_id_counter
    name = f"🤖 Бот-{random.choice(BOT_NAME_POOL)}"
    players[uid] = {
        "name": name, "balance": 10**9, "games": {"uno": 0},
        "wins": 0, "losses": 0, "is_bot": True
    }
    return uid

def bots_menu_keyboard(prefix, remaining):
    keyboard = []
    row = []
    for n in range(1, remaining + 1):
        row.append(InlineKeyboardButton(str(n), callback_data=f"{prefix}_addbots_{n}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"{prefix}_bots_back")])
    return InlineKeyboardMarkup(keyboard)

# ================= СОХРАНЕНИЕ ДАННЫХ =================

def save_data():
    try:
        data = {
            "players": {str(uid): p for uid, p in players.items()},
            "credits": {str(uid): c for uid, c in credits.items()},
            "username_to_id": username_to_id,
            "usd_rate": usd_rate,
            "btc_rate": btc_rate,
        }
        tmp_path = DATA_FILE + ".tmp"
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp_path, DATA_FILE)
    except Exception as e:
        logging.error(f"Ошибка сохранения данных: {e}")

def load_data():
    global usd_rate, btc_rate
    if not os.path.exists(DATA_FILE):
        return
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for uid_str, p in data.get("players", {}).items():
            players[int(uid_str)] = p
        for uid_str, c in data.get("credits", {}).items():
            credits[int(uid_str)] = c
        username_to_id.update(data.get("username_to_id", {}))
        usd_rate = data.get("usd_rate", USD_START_RATE)
        btc_rate = data.get("btc_rate", BTC_START_RATE)
        logging.info(f"Данные загружены: {len(players)} игроков")
    except Exception as e:
        logging.error(f"Ошибка загрузки данных: {e}")

async def autosave_loop():
    while True:
        await asyncio.sleep(AUTOSAVE_SECONDS)
        save_data()

# ================= УНО: КОЛОДА И ЛОГИКА =================

COLORS = ['R', 'Y', 'G', 'B']
COLOR_EMOJI = {'R': '🔴', 'Y': '🟡', 'G': '🟢', 'B': '🔵', None: '⬛'}
COLOR_NAME = {'R': 'Красный', 'Y': 'Жёлтый', 'G': 'Зелёный', 'B': 'Синий'}

def build_deck():
    deck = []
    for c in COLORS:
        deck.append((c, '0'))
        for v in ['1', '2', '3', '4', '5', '6', '7', '8', '9', 'SKIP', 'REV', '+2']:
            deck.append((c, v))
            deck.append((c, v))
    for _ in range(4):
        deck.append((None, 'WILD'))
        deck.append((None, '+4'))
    random.shuffle(deck)
    return deck

def card_text(card):
    c, v = card
    return f"{COLOR_EMOJI[c]}{v}"

def is_playable(card, current_color, top_card):
    c, v = card
    _, tv = top_card
    if c is None:
        return True
    if c == current_color:
        return True
    if v == tv:
        return True
    return False

def draw_cards(state, uid, n):
    for _ in range(n):
        if not state['deck']:
            top = state['discard'][-1]
            rest = state['discard'][:-1]
            random.shuffle(rest)
            state['deck'] = rest
            state['discard'] = [top]
            if not state['deck']:
                break
        state['hands'][uid].append(state['deck'].pop())

def apply_effect_and_advance(state, card):
    n = len(state['players'])
    c, v = card
    idx = state['turn_idx']

    if v == 'SKIP':
        idx = (idx + state['direction']) % n
        idx = (idx + state['direction']) % n
    elif v == 'REV':
        state['direction'] *= -1
        if n == 2:
            idx = (idx + state['direction']) % n
            idx = (idx + state['direction']) % n
        else:
            idx = (idx + state['direction']) % n
    elif v == '+2':
        target = (idx + state['direction']) % n
        draw_cards(state, state['players'][target], 2)
        idx = (target + state['direction']) % n
    elif v == '+4':
        target = (idx + state['direction']) % n
        draw_cards(state, state['players'][target], 4)
        idx = (target + state['direction']) % n
    else:
        idx = (idx + state['direction']) % n

    state['turn_idx'] = idx

# ================= УНО: ЛОББИ =================

def lobby_text(state):
    bet_line = f"💰 Ставка: {state['bet']} монет | Банк: {state['bet'] * len(state['players'])} монет\n" if state['bet'] > 0 else ""
    lines = [f"🃏 **Лобби УНО** ({len(state['players'])}/{MAX_PLAYERS})\n{bet_line}"]
    for i, uid in enumerate(state['players'], 1):
        lines.append(f"{i}. {players[uid]['name']}")
    if len(state['players']) < MIN_PLAYERS:
        lines.append(f"\nЖдём ещё игроков (мин. {MIN_PLAYERS})...")
    else:
        lines.append("\nМожно начинать!")
    return "\n".join(lines)

def lobby_keyboard(state):
    keyboard = [[InlineKeyboardButton("✅ Присоединиться", callback_data="uno_join")]]
    if len(state['players']) < MAX_PLAYERS:
        keyboard.append([InlineKeyboardButton("🤖 Играть с ботом", callback_data="uno_bots_menu")])
    if len(state['players']) >= MIN_PLAYERS:
        keyboard.append([InlineKeyboardButton("🚀 Начать игру", callback_data="uno_start")])
    keyboard.append([InlineKeyboardButton("❌ Отменить", callback_data="uno_cancel")])
    return InlineKeyboardMarkup(keyboard)

def track_chat_player(chat_id, user_id):
    chat_players.setdefault(chat_id, set()).add(user_id)

async def can_dm(user_id, context: ContextTypes.DEFAULT_TYPE):
    try:
        msg = await context.bot.send_message(user_id, "🤖 Проверка личных сообщений...")
        try:
            await context.bot.delete_message(user_id, msg.message_id)
        except Exception:
            pass
        return True
    except Exception:
        return False

async def pin_game_message(bot, chat_id, message_id):
    try:
        await bot.pin_chat_message(chat_id, message_id, disable_notification=True)
    except Exception:
        pass

async def unpin_game_message(bot, chat_id, message_id):
    try:
        await bot.unpin_chat_message(chat_id, message_id)
    except Exception:
        pass

async def create_lobby(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await can_dm(user_id, context):
        me = await context.bot.get_me()
        keyboard = [[InlineKeyboardButton("✉️ Открыть личку с ботом", url=f"https://t.me/{me.username}")]]
        await update.message.reply_text(
            "❌ Чтобы играть в УНО, сначала напиши боту в личку /start — карты приходят туда.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if user_id not in players:
        players[user_id] = {
            "name": update.effective_user.full_name,
            "balance": 1000,
            "games": {"uno": 0},
            "wins": 0,
            "losses": 0
        }

    existing = games_uno.get(chat_id)
    if existing and existing['status'] in ('waiting', 'active'):
        await update.message.reply_text("⚠️ В этом чате уже есть активная игра/лобби УНО!")
        return

    bet = 0
    if context.args and context.args[0].isdigit():
        bet = int(context.args[0])
        if bet > 0 and players[user_id]['balance'] < bet:
            await update.message.reply_text(f"❌ Недостаточно монет. Баланс: {players[user_id]['balance']}")
            return

    if bet > 0:
        players[user_id]['balance'] -= bet

    state = {
        "players": [user_id],
        "hands": {},
        "deck": [],
        "discard": [],
        "turn_idx": 0,
        "direction": 1,
        "current_color": None,
        "status": "waiting",
        "host": user_id,
        "chat_id": chat_id,
        "message_id": None,
        "dm_msg": {},
        "awaiting_color": None,
        "bet": bet,
    }
    games_uno[chat_id] = state

    msg = await update.message.reply_text(
        lobby_text(state), reply_markup=lobby_keyboard(state), parse_mode='Markdown'
    )
    state['message_id'] = msg.message_id
    await pin_game_message(context.bot, chat_id, msg.message_id)

async def start_uno_game(chat_id, context: ContextTypes.DEFAULT_TYPE):
    state = games_uno[chat_id]
    state['deck'] = build_deck()

    for uid in state['players']:
        state['hands'][uid] = [state['deck'].pop() for _ in range(7)]

    first = state['deck'].pop()
    while first[0] is None:
        state['deck'].insert(0, first)
        random.shuffle(state['deck'])
        first = state['deck'].pop()
    state['discard'] = [first]
    state['current_color'] = first[0]
    state['status'] = 'active'
    state['turn_idx'] = 0

    await update_public_status(chat_id, context)
    for uid in state['players']:
        await send_hand(chat_id, uid, context, new=True)
    await maybe_bot_turn_uno(chat_id, context)

async def update_public_status(chat_id, context: ContextTypes.DEFAULT_TYPE):
    state = games_uno[chat_id]
    top = state['discard'][-1]
    current_uid = state['players'][state['turn_idx']]
    lines = [
        "🃏 **УНО — идёт игра**\n",
        f"Верхняя карта: {card_text(top)}",
        f"Текущий цвет: {COLOR_EMOJI[state['current_color']]} {COLOR_NAME.get(state['current_color'], '')}",
        f"\n▶️ Ход: **{players[current_uid]['name']}**\n"
    ]
    for uid in state['players']:
        marker = "👉 " if uid == current_uid else "   "
        lines.append(f"{marker}{players[uid]['name']}: {len(state['hands'][uid])} карт")
    text = "\n".join(lines)
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=state['message_id'], text=text, parse_mode='Markdown'
        )
    except Exception:
        old_id = state['message_id']
        msg = await context.bot.send_message(chat_id, text, parse_mode='Markdown')
        state['message_id'] = msg.message_id
        await unpin_game_message(context.bot, chat_id, old_id)
        await pin_game_message(context.bot, chat_id, msg.message_id)

async def maybe_bot_turn_uno(chat_id, context: ContextTypes.DEFAULT_TYPE):
    state = games_uno.get(chat_id)
    if not state or state['status'] != 'active':
        return
    current_uid = state['players'][state['turn_idx']]
    if not is_bot(current_uid):
        return
    await asyncio.sleep(1.5)
    state = games_uno.get(chat_id)
    if not state or state['status'] != 'active':
        return
    if state['players'][state['turn_idx']] != current_uid:
        return
    await bot_play_uno(chat_id, current_uid, context)

async def bot_play_uno(chat_id, uid, context: ContextTypes.DEFAULT_TYPE):
    state = games_uno.get(chat_id)
    if not state or state['status'] != 'active':
        return
    hand = state['hands'][uid]
    top = state['discard'][-1]
    playable = [i for i, c in enumerate(hand) if is_playable(c, state['current_color'], top)]

    if playable:
        idx = random.choice(playable)
        card = hand.pop(idx)
        state['discard'].append(card)

        if not hand:
            await finish_game(chat_id, uid, context)
            return

        c, v = card
        state['current_color'] = random.choice(COLORS) if c is None else c
        apply_effect_and_advance(state, card)
    else:
        draw_cards(state, uid, 1)
        state['turn_idx'] = (state['turn_idx'] + state['direction']) % len(state['players'])

    await update_public_status(chat_id, context)
    await refresh_all_hands(chat_id, context)
    await maybe_bot_turn_uno(chat_id, context)

async def send_hand(chat_id, uid, context: ContextTypes.DEFAULT_TYPE, new=False):
    if is_bot(uid):
        return
    state = games_uno[chat_id]
    hand = state['hands'][uid]
    top = state['discard'][-1]
    is_turn = state['players'][state['turn_idx']] == uid

    keyboard = []
    for i, card in enumerate(hand):
        label = card_text(card)
        if is_turn and is_playable(card, state['current_color'], top):
            label = "▶️ " + label
        keyboard.append([InlineKeyboardButton(label, callback_data=f"uno_play_{chat_id}_{i}")])
    if is_turn:
        keyboard.append([InlineKeyboardButton("🃏 Взять карту", callback_data=f"uno_draw_{chat_id}")])

    text = f"Твоя рука ({len(hand)} карт)\nВерхняя карта на столе: {card_text(top)} | Цвет: {COLOR_EMOJI[state['current_color']]}"
    if is_turn:
        text = "🟢 **ТВОЙ ХОД**\n\n" + text
    else:
        text = f"⏳ Ход другого игрока\n\n{text}"

    markup = InlineKeyboardMarkup(keyboard)
    msg_id = state['dm_msg'].get(uid)
    if new or not msg_id:
        try:
            msg = await context.bot.send_message(uid, text, reply_markup=markup, parse_mode='Markdown')
            state['dm_msg'][uid] = msg.message_id
        except Exception:
            pass
    else:
        try:
            await context.bot.edit_message_text(
                chat_id=uid, message_id=msg_id, text=text, reply_markup=markup, parse_mode='Markdown'
            )
        except Exception:
            try:
                msg = await context.bot.send_message(uid, text, reply_markup=markup, parse_mode='Markdown')
                state['dm_msg'][uid] = msg.message_id
            except Exception:
                pass

async def refresh_all_hands(chat_id, context: ContextTypes.DEFAULT_TYPE):
    state = games_uno[chat_id]
    for uid in state['players']:
        await send_hand(chat_id, uid, context)

async def finish_game(chat_id, winner_uid, context: ContextTypes.DEFAULT_TYPE):
    state = games_uno[chat_id]
    players[winner_uid]['wins'] += 1
    if state['bet'] > 0:
        pot = state['bet'] * len(state['players'])
        players[winner_uid]['balance'] += pot
        prize_text = f"💰 Забрал банк: {pot} монет"
    else:
        players[winner_uid]['balance'] += 100
        prize_text = "💰 Получил: 100 монет"
    for uid in state['players']:
        players[uid]['games']['uno'] += 1
        if uid != winner_uid:
            players[uid]['losses'] += 1
        if is_bot(uid):
            continue
        try:
            await context.bot.send_message(
                uid, f"🏆 Игра окончена! Победитель: **{players[winner_uid]['name']}**\n{prize_text}", parse_mode='Markdown'
            )
        except Exception:
            pass
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=state['message_id'],
            text=f"🏆 **Игра УНО завершена!**\n\nПобедитель: {players[winner_uid]['name']} 🎉\n{prize_text}",
            parse_mode='Markdown'
        )
    except Exception:
        pass
    await unpin_game_message(context.bot, chat_id, state['message_id'])
    del games_uno[chat_id]
    save_data()

# ================= УНО: КОЛБЭКИ =================

async def uno_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    data = query.data

    if data == "uno_bots_menu":
        chat_id = update.effective_chat.id
        state = games_uno.get(chat_id)
        if not state or state['status'] != 'waiting':
            await query.answer("❌ Лобби не найдено", show_alert=True)
            return
        if user_id != state['host']:
            await query.answer("❌ Только хост может добавлять ботов", show_alert=True)
            return
        remaining = MAX_PLAYERS - len(state['players'])
        if remaining <= 0:
            await query.answer("❌ Лобби уже заполнено", show_alert=True)
            return
        await query.answer()
        await query.edit_message_text(
            f"🤖 Сколько ботов добавить? (свободно мест: {remaining})",
            reply_markup=bots_menu_keyboard("uno", remaining)
        )
        return

    if data == "uno_bots_back":
        chat_id = update.effective_chat.id
        state = games_uno.get(chat_id)
        if not state:
            await query.answer()
            return
        await query.answer()
        await query.edit_message_text(lobby_text(state), reply_markup=lobby_keyboard(state), parse_mode='Markdown')
        return

    if data.startswith("uno_addbots_"):
        chat_id = update.effective_chat.id
        state = games_uno.get(chat_id)
        if not state or state['status'] != 'waiting':
            await query.answer("❌ Лобби не найдено", show_alert=True)
            return
        if user_id != state['host']:
            await query.answer("❌ Только хост может добавлять ботов", show_alert=True)
            return
        count = int(data.split("_")[2])
        added = 0
        for _ in range(count):
            if len(state['players']) >= MAX_PLAYERS:
                break
            bot_uid = create_bot_player()
            if state['bet'] > 0:
                players[bot_uid]['balance'] -= state['bet']
            state['players'].append(bot_uid)
            added += 1
        await query.answer(f"Добавлено ботов: {added}")
        await query.edit_message_text(lobby_text(state), reply_markup=lobby_keyboard(state), parse_mode='Markdown')
        return

    if data == "uno_join":
        chat_id = update.effective_chat.id
        state = games_uno.get(chat_id)
        if not state or state['status'] != 'waiting':
            await query.answer("❌ Лобби не найдено или игра уже началась", show_alert=True)
            return
        if user_id in state['players']:
            await query.answer("Ты уже в игре!", show_alert=True)
            return
        if len(state['players']) >= MAX_PLAYERS:
            await query.answer("❌ Лобби заполнено (макс. 4)", show_alert=True)
            return
        if not await can_dm(user_id, context):
            me = await context.bot.get_me()
            await query.answer(
                "❌ Сначала напиши боту в личку /start — карты приходят туда!", show_alert=True
            )
            return
        if user_id not in players:
            players[user_id] = {
                "name": update.effective_user.full_name,
                "balance": 1000, "games": {"uno": 0}, "wins": 0, "losses": 0
            }
        if state['bet'] > 0 and players[user_id]['balance'] < state['bet']:
            await query.answer(f"❌ Недостаточно монет. Нужно: {state['bet']}", show_alert=True)
            return
        if state['bet'] > 0:
            players[user_id]['balance'] -= state['bet']
        state['players'].append(user_id)
        await query.answer("Ты присоединился!")
        await query.edit_message_text(
            lobby_text(state), reply_markup=lobby_keyboard(state), parse_mode='Markdown'
        )
        return

    if data == "uno_cancel":
        chat_id = update.effective_chat.id
        state = games_uno.get(chat_id)
        if not state:
            await query.answer()
            return
        if user_id != state['host']:
            await query.answer("❌ Только хост может отменить", show_alert=True)
            return
        if state['bet'] > 0:
            for uid in state['players']:
                players[uid]['balance'] += state['bet']
        await unpin_game_message(context.bot, chat_id, state['message_id'])
        del games_uno[chat_id]
        await query.answer("Игра отменена, ставки возвращены" if state['bet'] > 0 else "Игра отменена")
        await query.edit_message_text("❌ Лобби УНО отменено." + (" Ставки возвращены." if state['bet'] > 0 else ""))
        return

    if data == "uno_start":
        chat_id = update.effective_chat.id
        state = games_uno.get(chat_id)
        if not state or state['status'] != 'waiting':
            await query.answer("❌ Лобби не найдено", show_alert=True)
            return
        if user_id != state['host']:
            await query.answer("❌ Только хост может начать игру", show_alert=True)
            return
        if len(state['players']) < MIN_PLAYERS:
            await query.answer(f"❌ Нужно минимум {MIN_PLAYERS} игрока", show_alert=True)
            return
        await query.answer("Игра начинается!")
        await start_uno_game(chat_id, context)
        return

    if data.startswith("uno_play_"):
        _, _, chat_id_str, idx_str = data.split("_")
        chat_id = int(chat_id_str)
        idx = int(idx_str)
        state = games_uno.get(chat_id)
        if not state or state['status'] != 'active':
            await query.answer("❌ Игра не найдена", show_alert=True)
            return
        current_uid = state['players'][state['turn_idx']]
        if user_id != current_uid:
            await query.answer("❌ Сейчас не твой ход!", show_alert=True)
            return
        hand = state['hands'][user_id]
        if idx >= len(hand):
            await query.answer("❌ Такой карты нет", show_alert=True)
            return
        card = hand[idx]
        top = state['discard'][-1]
        if not is_playable(card, state['current_color'], top):
            await query.answer("❌ Эту карту нельзя сыграть", show_alert=True)
            return

        hand.pop(idx)
        state['discard'].append(card)
        await query.answer()

        if not hand:
            await finish_game(chat_id, user_id, context)
            return

        c, v = card
        if c is None:
            state['awaiting_color'] = user_id
            state['pending_card'] = card
            keyboard = [[InlineKeyboardButton(f"{COLOR_EMOJI[col]} {COLOR_NAME[col]}", callback_data=f"uno_color_{chat_id}_{col}")] for col in COLORS]
            try:
                await context.bot.edit_message_text(
                    chat_id=user_id, message_id=state['dm_msg'].get(user_id),
                    text="🎨 Выбери цвет:", reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except Exception:
                await context.bot.send_message(user_id, "🎨 Выбери цвет:", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        state['current_color'] = c
        apply_effect_and_advance(state, card)
        await update_public_status(chat_id, context)
        await refresh_all_hands(chat_id, context)
        await maybe_bot_turn_uno(chat_id, context)
        return

    if data.startswith("uno_draw_"):
        chat_id = int(data.split("_")[2])
        state = games_uno.get(chat_id)
        if not state or state['status'] != 'active':
            await query.answer("❌ Игра не найдена", show_alert=True)
            return
        current_uid = state['players'][state['turn_idx']]
        if user_id != current_uid:
            await query.answer("❌ Сейчас не твой ход!", show_alert=True)
            return
        draw_cards(state, user_id, 1)
        state['turn_idx'] = (state['turn_idx'] + state['direction']) % len(state['players'])
        await query.answer("Ты взял карту")
        await update_public_status(chat_id, context)
        await refresh_all_hands(chat_id, context)
        await maybe_bot_turn_uno(chat_id, context)
        return

    if data.startswith("uno_color_"):
        _, _, chat_id_str, color = data.split("_")
        chat_id = int(chat_id_str)
        state = games_uno.get(chat_id)
        if not state or state['awaiting_color'] != user_id:
            await query.answer("❌ Не твой выбор", show_alert=True)
            return
        state['current_color'] = color
        card = state['pending_card']
        state['awaiting_color'] = None
        apply_effect_and_advance(state, card)
        await query.answer(f"Цвет: {COLOR_NAME[color]}")
        try:
            await query.edit_message_text(f"Выбран цвет: {COLOR_EMOJI[color]} {COLOR_NAME[color]}")
        except Exception:
            pass
        await update_public_status(chat_id, context)
        await refresh_all_hands(chat_id, context)
        await maybe_bot_turn_uno(chat_id, context)
        return

# ================= ОРЁЛ ИЛИ РЕШКА =================

SIDE_NAME = {'eagle': 'Орёл', 'tail': 'Решка'}

def coin_text(state, result=None):
    if result is None:
        return (f"🪙 **Орёл или Решка**\n\n"
                f"Вызов от {players[state['host']]['name']}\n"
                f"Ставка: {state['bet']} монет\n"
                f"Хост выбрал: {SIDE_NAME[state['host_side']]}\n\n"
                f"Кто примет вызов?")
    winner_uid, side = result
    loser_uid = state['host'] if winner_uid != state['host'] else state['opponent']
    return (f"🪙 **{SIDE_NAME[side]}!**\n\n"
            f"🏆 Победитель: {players[winner_uid]['name']} (+{state['bet']} монет)\n"
            f"😢 Проигравший: {players[loser_uid]['name']} (-{state['bet']} монет)")

async def coin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if user_id not in players:
        players[user_id] = {
            "name": update.effective_user.full_name,
            "balance": 1000, "games": {"uno": 0}, "wins": 0, "losses": 0
        }

    if games_coin.get(chat_id) and games_coin[chat_id]['status'] in ('picking', 'waiting'):
        await update.message.reply_text("⚠️ В этом чате уже есть открытый вызов Орёл/Решка!")
        return

    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("Использование: /coin <ставка>\nНапример: /coin 100")
        return

    bet = int(args[0])
    if bet <= 0:
        await update.message.reply_text("❌ Ставка должна быть больше нуля.")
        return
    if players[user_id]['balance'] < bet:
        await update.message.reply_text(f"❌ Недостаточно монет. Баланс: {players[user_id]['balance']}")
        return

    state = {"host": user_id, "bet": bet, "status": "picking", "message_id": None, "opponent": None, "host_side": None}
    games_coin[chat_id] = state

    keyboard = [
        [InlineKeyboardButton("🦅 Орёл", callback_data="coin_pick_eagle"),
         InlineKeyboardButton("👑 Решка", callback_data="coin_pick_tail")],
        [InlineKeyboardButton("❌ Отменить", callback_data="coin_cancel")]
    ]
    msg = await update.message.reply_text(
        f"🪙 Ставка: {bet} монет\n\nВыбери свою сторону:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    state['message_id'] = msg.message_id
    await pin_game_message(context.bot, chat_id, msg.message_id)

async def coin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    data = query.data
    state = games_coin.get(chat_id)

    if not state or state['status'] not in ('picking', 'waiting'):
        await query.answer("❌ Вызов не найден", show_alert=True)
        return

    if data == "coin_cancel":
        if user_id != state['host']:
            await query.answer("❌ Только автор вызова может отменить", show_alert=True)
            return
        await unpin_game_message(context.bot, chat_id, state['message_id'])
        del games_coin[chat_id]
        await query.answer("Вызов отменён")
        await query.edit_message_text("❌ Вызов Орёл/Решка отменён.")
        return

    if data in ("coin_pick_eagle", "coin_pick_tail"):
        if state['status'] != 'picking':
            await query.answer("❌ Сторона уже выбрана", show_alert=True)
            return
        if user_id != state['host']:
            await query.answer("❌ Только автор вызова выбирает сторону", show_alert=True)
            return
        state['host_side'] = 'eagle' if data == "coin_pick_eagle" else 'tail'
        state['status'] = 'waiting'
        await query.answer()
        keyboard = [
            [InlineKeyboardButton("🎲 Принять вызов", callback_data="coin_join")],
            [InlineKeyboardButton("❌ Отменить", callback_data="coin_cancel")]
        ]
        await query.edit_message_text(coin_text(state), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return

    if data == "coin_join":
        if state['status'] != 'waiting':
            await query.answer("❌ Вызов ещё не готов", show_alert=True)
            return
        if user_id == state['host']:
            await query.answer("❌ Нельзя принять свой же вызов!", show_alert=True)
            return
        if user_id not in players:
            players[user_id] = {
                "name": update.effective_user.full_name,
                "balance": 1000, "games": {"uno": 0}, "wins": 0, "losses": 0
            }
        if players[user_id]['balance'] < state['bet']:
            await query.answer(f"❌ Недостаточно монет. Нужно: {state['bet']}", show_alert=True)
            return

        state['opponent'] = user_id
        state['status'] = 'done'
        await query.answer()

        players[state['host']]['balance'] -= state['bet']
        players[user_id]['balance'] -= state['bet']

        side = random.choice(['eagle', 'tail'])
        winner_uid = state['host'] if side == state['host_side'] else user_id
        players[winner_uid]['balance'] += state['bet'] * 2
        players[winner_uid]['wins'] += 1
        loser_uid = user_id if winner_uid == state['host'] else state['host']
        players[loser_uid]['losses'] += 1

        await query.edit_message_text(coin_text(state, (winner_uid, side)), parse_mode='Markdown')
        await unpin_game_message(context.bot, chat_id, state['message_id'])
        del games_coin[chat_id]
        return

async def stop_coin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    state = games_coin.get(chat_id)

    if not state or state['status'] not in ('picking', 'waiting'):
        await update.message.reply_text("📭 В этом чате сейчас нет открытого вызова Орёл/Решка.")
        return

    allowed = user_id == state['host']
    if not allowed and update.effective_chat.type != "private":
        member = await context.bot.get_chat_member(chat_id, user_id)
        allowed = member.status in ("administrator", "creator")
    if not allowed:
        await update.message.reply_text("❌ Отменить вызов может только его автор или админ группы.")
        return

    try:
        if state.get('message_id'):
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=state['message_id'],
                text="⛔ **Вызов Орёл/Решка отменён.**", parse_mode='Markdown'
            )
            await unpin_game_message(context.bot, chat_id, state['message_id'])
    except Exception:
        pass

    del games_coin[chat_id]
    await update.message.reply_text("⛔ Вызов Орёл/Решка отменён.")

# ================= РУССКАЯ РУЛЕТКА =================

def roul_lobby_text(state):
    lines = [f"🔫 **Русская рулетка** ({len(state['players'])}/{MAX_ROULETTE})\n",
              f"Ставка на входе: {state['bet']} монет\n💰 Банк: {state['bet'] * len(state['players'])} монет\n"]
    for i, uid in enumerate(state['players'], 1):
        lines.append(f"{i}. {players[uid]['name']}")
    if len(state['players']) < MIN_ROULETTE:
        lines.append(f"\nЖдём ещё игроков (мин. {MIN_ROULETTE})...")
    else:
        lines.append("\nМожно начинать!")
    return "\n".join(lines)

def roul_lobby_keyboard(state):
    keyboard = [[InlineKeyboardButton("✅ Присоединиться", callback_data="roul_join")]]
    if len(state['players']) < MAX_ROULETTE:
        keyboard.append([InlineKeyboardButton("🤖 Играть с ботом", callback_data="roul_bots_menu")])
    if len(state['players']) >= MIN_ROULETTE:
        keyboard.append([InlineKeyboardButton("🚀 Начать игру", callback_data="roul_start")])
    keyboard.append([InlineKeyboardButton("❌ Отменить", callback_data="roul_cancel")])
    return InlineKeyboardMarkup(keyboard)

def roul_status_text(state, log=""):
    alive = state['alive']
    current_uid = alive[state['turn_idx']]
    lines = [
        "🔫 **Русская рулетка — идёт игра**\n",
        f"💰 Банк: {state['pot']} монет",
        f"Осталось игроков: {len(alive)}\n"
    ]
    if log:
        lines.append(log + "\n")
    lines.append(f"▶️ Ход: **{players[current_uid]['name']}**")
    for uid in alive:
        marker = "👉 " if uid == current_uid else "   "
        lines.append(f"{marker}{players[uid]['name']}")
    return "\n".join(lines)

async def roulette_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if user_id not in players:
        players[user_id] = {
            "name": update.effective_user.full_name,
            "balance": 1000, "games": {"uno": 0}, "wins": 0, "losses": 0
        }

    existing = games_roulette.get(chat_id)
    if existing and existing['status'] in ('waiting', 'active'):
        await update.message.reply_text("⚠️ В этом чате уже есть лобби/игра Русская рулетка!")
        return

    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("Использование: /roulette <ставка>\nНапример: /roulette 50")
        return

    bet = int(args[0])
    if bet <= 0:
        await update.message.reply_text("❌ Ставка должна быть больше нуля.")
        return
    if players[user_id]['balance'] < bet:
        await update.message.reply_text(f"❌ Недостаточно монет. Баланс: {players[user_id]['balance']}")
        return

    players[user_id]['balance'] -= bet
    state = {
        "players": [user_id], "alive": [], "turn_idx": 0,
        "bet": bet, "pot": bet, "status": "waiting", "host": user_id,
        "chat_id": chat_id, "message_id": None,
    }
    games_roulette[chat_id] = state

    msg = await update.message.reply_text(
        roul_lobby_text(state), reply_markup=roul_lobby_keyboard(state), parse_mode='Markdown'
    )
    state['message_id'] = msg.message_id
    await pin_game_message(context.bot, chat_id, msg.message_id)

async def start_roulette_game(chat_id, context: ContextTypes.DEFAULT_TYPE):
    state = games_roulette[chat_id]
    state['alive'] = list(state['players'])
    random.shuffle(state['alive'])
    state['turn_idx'] = 0
    state['status'] = 'active'
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=state['message_id'],
            text=roul_status_text(state, "🎲 Барабан прокручен, начинаем!"),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔫 Выстрелить", callback_data="roul_shoot")]]),
            parse_mode='Markdown'
        )
    except Exception:
        pass
    await maybe_bot_turn_roulette(chat_id, context)

async def finish_roulette(chat_id, winner_uid, context: ContextTypes.DEFAULT_TYPE):
    state = games_roulette[chat_id]
    players[winner_uid]['balance'] += state['pot']
    players[winner_uid]['wins'] += 1
    for uid in state['players']:
        if uid != winner_uid:
            players[uid]['losses'] += 1
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=state['message_id'],
            text=f"🏆 **Игра окончена!**\n\nВыжил и забрал банк ({state['pot']} монет): {players[winner_uid]['name']} 🎉",
            parse_mode='Markdown'
        )
    except Exception:
        pass
    await unpin_game_message(context.bot, chat_id, state['message_id'])
    del games_roulette[chat_id]
    save_data()

async def resolve_roulette_shot(chat_id, user_id, context: ContextTypes.DEFAULT_TYPE):
    state = games_roulette.get(chat_id)
    if not state or state['status'] != 'active':
        return
    shot = random.randint(1, 6) == 1

    if shot:
        name = players[user_id]['name']
        state['alive'].pop(state['turn_idx'])
        if state['turn_idx'] >= len(state['alive']):
            state['turn_idx'] = 0
        if len(state['alive']) == 1:
            await finish_roulette(chat_id, state['alive'][0], context)
            return
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=state['message_id'],
                text=roul_status_text(state, f"💥 БАХ! {name} выбывает из игры."),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔫 Выстрелить", callback_data="roul_shoot")]]),
                parse_mode='Markdown'
            )
        except Exception:
            pass
    else:
        state['turn_idx'] = (state['turn_idx'] + 1) % len(state['alive'])
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=state['message_id'],
                text=roul_status_text(state, "🔫 Осечка... повезло!"),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔫 Выстрелить", callback_data="roul_shoot")]]),
                parse_mode='Markdown'
            )
        except Exception:
            pass

    await maybe_bot_turn_roulette(chat_id, context)

async def maybe_bot_turn_roulette(chat_id, context: ContextTypes.DEFAULT_TYPE):
    state = games_roulette.get(chat_id)
    if not state or state['status'] != 'active':
        return
    current_uid = state['alive'][state['turn_idx']]
    if not is_bot(current_uid):
        return
    await asyncio.sleep(1.5)
    state = games_roulette.get(chat_id)
    if not state or state['status'] != 'active':
        return
    if state['alive'][state['turn_idx']] != current_uid:
        return
    await resolve_roulette_shot(chat_id, current_uid, context)

async def roulette_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    data = query.data
    state = games_roulette.get(chat_id)

    if not state:
        await query.answer("❌ Игра не найдена", show_alert=True)
        return

    if data == "roul_bots_menu":
        if state['status'] != 'waiting':
            await query.answer("❌ Игра уже началась", show_alert=True)
            return
        if user_id != state['host']:
            await query.answer("❌ Только хост может добавлять ботов", show_alert=True)
            return
        remaining = MAX_ROULETTE - len(state['players'])
        if remaining <= 0:
            await query.answer("❌ Лобби уже заполнено", show_alert=True)
            return
        await query.answer()
        await query.edit_message_text(
            f"🤖 Сколько ботов добавить? (свободно мест: {remaining})",
            reply_markup=bots_menu_keyboard("roul", remaining)
        )
        return

    if data == "roul_bots_back":
        await query.answer()
        await query.edit_message_text(roul_lobby_text(state), reply_markup=roul_lobby_keyboard(state), parse_mode='Markdown')
        return

    if data.startswith("roul_addbots_"):
        if state['status'] != 'waiting':
            await query.answer("❌ Игра уже началась", show_alert=True)
            return
        if user_id != state['host']:
            await query.answer("❌ Только хост может добавлять ботов", show_alert=True)
            return
        count = int(data.split("_")[2])
        added = 0
        for _ in range(count):
            if len(state['players']) >= MAX_ROULETTE:
                break
            bot_uid = create_bot_player()
            players[bot_uid]['balance'] -= state['bet']
            state['players'].append(bot_uid)
            state['pot'] += state['bet']
            added += 1
        await query.answer(f"Добавлено ботов: {added}")
        await query.edit_message_text(roul_lobby_text(state), reply_markup=roul_lobby_keyboard(state), parse_mode='Markdown')
        return

    if data == "roul_cancel":
        if state['status'] != 'waiting':
            await query.answer("❌ Игра уже началась", show_alert=True)
            return
        if user_id != state['host']:
            await query.answer("❌ Только хост может отменить", show_alert=True)
            return
        for uid in state['players']:
            players[uid]['balance'] += state['bet']
        await unpin_game_message(context.bot, chat_id, state['message_id'])
        del games_roulette[chat_id]
        await query.answer("Игра отменена, ставки возвращены")
        await query.edit_message_text("❌ Лобби Русской рулетки отменено, ставки возвращены.")
        return

    if data == "roul_join":
        if state['status'] != 'waiting':
            await query.answer("❌ Лобби не найдено или игра уже началась", show_alert=True)
            return
        if user_id in state['players']:
            await query.answer("Ты уже в игре!", show_alert=True)
            return
        if len(state['players']) >= MAX_ROULETTE:
            await query.answer("❌ Лобби заполнено (макс. 6)", show_alert=True)
            return
        if user_id not in players:
            players[user_id] = {
                "name": update.effective_user.full_name,
                "balance": 1000, "games": {"uno": 0}, "wins": 0, "losses": 0
            }
        if players[user_id]['balance'] < state['bet']:
            await query.answer(f"❌ Недостаточно монет. Нужно: {state['bet']}", show_alert=True)
            return
        players[user_id]['balance'] -= state['bet']
        state['players'].append(user_id)
        state['pot'] += state['bet']
        await query.answer("Ты присоединился!")
        await query.edit_message_text(
            roul_lobby_text(state), reply_markup=roul_lobby_keyboard(state), parse_mode='Markdown'
        )
        return

    if data == "roul_start":
        if state['status'] != 'waiting':
            await query.answer("❌ Лобби не найдено", show_alert=True)
            return
        if user_id != state['host']:
            await query.answer("❌ Только хост может начать игру", show_alert=True)
            return
        if len(state['players']) < MIN_ROULETTE:
            await query.answer(f"❌ Нужно минимум {MIN_ROULETTE} игрока", show_alert=True)
            return
        await query.answer("Игра начинается!")
        await start_roulette_game(chat_id, context)
        return

    if data == "roul_shoot":
        if state['status'] != 'active':
            await query.answer("❌ Игра не найдена", show_alert=True)
            return
        current_uid = state['alive'][state['turn_idx']]
        if user_id != current_uid:
            await query.answer("❌ Сейчас не твой ход!", show_alert=True)
            return
        await query.answer()
        await resolve_roulette_shot(chat_id, user_id, context)
        return

async def stop_roulette_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    state = games_roulette.get(chat_id)

    if not state:
        await update.message.reply_text("📭 В этом чате сейчас нет игры Русская рулетка.")
        return

    allowed = user_id == state['host']
    if not allowed and update.effective_chat.type != "private":
        member = await context.bot.get_chat_member(chat_id, user_id)
        allowed = member.status in ("administrator", "creator")
    if not allowed:
        await update.message.reply_text("❌ Остановить игру может только хост или админ группы.")
        return

    for uid in state['players']:
        players[uid]['balance'] += state['bet']

    try:
        if state.get('message_id'):
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=state['message_id'],
                text="⛔ **Русская рулетка остановлена, ставки возвращены.**", parse_mode='Markdown'
            )
    except Exception:
        pass

    if state.get('message_id'):
        await unpin_game_message(context.bot, chat_id, state['message_id'])
    del games_roulette[chat_id]
    await update.message.reply_text("⛔ Русская рулетка остановлена, ставки возвращены.")
    save_data()

# ================= КОСТИ =================

def dice_lobby_text(state):
    lines = [f"🎲 **Кости** ({len(state['players'])}/{MAX_DICE})\n",
              f"💰 Ставка: {state['bet']} монет | Банк: {state['bet'] * len(state['players'])} монет\n"]
    for i, uid in enumerate(state['players'], 1):
        lines.append(f"{i}. {players[uid]['name']}")
    if len(state['players']) < MIN_DICE:
        lines.append(f"\nЖдём ещё игроков (мин. {MIN_DICE})...")
    else:
        lines.append("\nМожно начинать!")
    return "\n".join(lines)

def dice_lobby_keyboard(state):
    keyboard = [[InlineKeyboardButton("✅ Присоединиться", callback_data="dice_join")]]
    if len(state['players']) < MAX_DICE:
        keyboard.append([InlineKeyboardButton("🤖 Играть с ботом", callback_data="dice_bots_menu")])
    if len(state['players']) >= MIN_DICE:
        keyboard.append([InlineKeyboardButton("🚀 Начать игру", callback_data="dice_start")])
    keyboard.append([InlineKeyboardButton("❌ Отменить", callback_data="dice_cancel")])
    return InlineKeyboardMarkup(keyboard)

def dice_board_keyboard(state):
    keyboard = []
    row = []
    for n in range(1, 7):
        if n in state['picks']:
            row.append(InlineKeyboardButton(f"{n} ({players[state['picks'][n]]['name']})", callback_data="dice_noop"))
        else:
            row.append(InlineKeyboardButton(str(n), callback_data=f"dice_pick_{n}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)

def dice_board_text(state):
    current_uid = state['players'][state['turn_idx']]
    lines = [
        "🎲 **Кости — выбор чисел**\n",
        f"💰 Банк: {state['bet'] * len(state['players'])} монет\n",
        f"▶️ Ход: **{players[current_uid]['name']}**\n",
        "Выбери свободное число от 1 до 6:"
    ]
    return "\n".join(lines)

async def dice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if user_id not in players:
        players[user_id] = {
            "name": update.effective_user.full_name,
            "balance": 1000, "games": {"uno": 0}, "wins": 0, "losses": 0
        }

    existing = games_dice.get(chat_id)
    if existing and existing['status'] in ('waiting', 'picking'):
        await update.message.reply_text("⚠️ В этом чате уже есть лобби/игра Кости!")
        return

    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("Использование: /dice <ставка>\nНапример: /dice 100")
        return

    bet = int(args[0])
    if bet <= 0:
        await update.message.reply_text("❌ Ставка должна быть больше нуля.")
        return
    if players[user_id]['balance'] < bet:
        await update.message.reply_text(f"❌ Недостаточно монет. Баланс: {players[user_id]['balance']}")
        return

    players[user_id]['balance'] -= bet
    state = {
        "players": [user_id], "bet": bet, "status": "waiting", "host": user_id,
        "chat_id": chat_id, "message_id": None, "picks": {}, "turn_idx": 0,
    }
    games_dice[chat_id] = state

    msg = await update.message.reply_text(
        dice_lobby_text(state), reply_markup=dice_lobby_keyboard(state), parse_mode='Markdown'
    )
    state['message_id'] = msg.message_id
    await pin_game_message(context.bot, chat_id, msg.message_id)

async def finish_dice(chat_id, context: ContextTypes.DEFAULT_TYPE):
    state = games_dice[chat_id]
    roll = random.randint(1, 6)
    pot = state['bet'] * len(state['players'])
    winner_uid = state['picks'].get(roll)

    if winner_uid:
        players[winner_uid]['balance'] += pot
        players[winner_uid]['wins'] += 1
        for uid in state['players']:
            if uid != winner_uid:
                players[uid]['losses'] += 1
        text = f"🎲 **Выпало: {roll}!**\n\n🏆 Угадал и забрал банк ({pot} монет): {players[winner_uid]['name']} 🎉"
    else:
        text = f"🎲 **Выпало: {roll}!**\n\nНикто не угадал это число — весь банк ({pot} монет) сгорает."

    try:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=state['message_id'], text=text, parse_mode='Markdown')
    except Exception:
        pass
    await unpin_game_message(context.bot, chat_id, state['message_id'])
    del games_dice[chat_id]
    save_data()

async def resolve_dice_pick(chat_id, user_id, num, context: ContextTypes.DEFAULT_TYPE):
    state = games_dice.get(chat_id)
    if not state or state['status'] != 'picking':
        return
    state['picks'][num] = user_id

    if len(state['picks']) == len(state['players']):
        await finish_dice(chat_id, context)
        return

    state['turn_idx'] += 1
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=state['message_id'],
            text=dice_board_text(state), reply_markup=dice_board_keyboard(state), parse_mode='Markdown'
        )
    except Exception:
        pass
    await maybe_bot_turn_dice(chat_id, context)

async def maybe_bot_turn_dice(chat_id, context: ContextTypes.DEFAULT_TYPE):
    state = games_dice.get(chat_id)
    if not state or state['status'] != 'picking':
        return
    current_uid = state['players'][state['turn_idx']]
    if not is_bot(current_uid):
        return
    await asyncio.sleep(1.5)
    state = games_dice.get(chat_id)
    if not state or state['status'] != 'picking':
        return
    if state['players'][state['turn_idx']] != current_uid:
        return
    free_numbers = [n for n in range(1, 7) if n not in state['picks']]
    num = random.choice(free_numbers)
    await resolve_dice_pick(chat_id, current_uid, num, context)

async def dice_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    data = query.data
    state = games_dice.get(chat_id)

    if data == "dice_noop":
        await query.answer()
        return

    if not state:
        await query.answer("❌ Игра не найдена", show_alert=True)
        return

    if data == "dice_bots_menu":
        if state['status'] != 'waiting':
            await query.answer("❌ Игра уже началась", show_alert=True)
            return
        if user_id != state['host']:
            await query.answer("❌ Только хост может добавлять ботов", show_alert=True)
            return
        remaining = MAX_DICE - len(state['players'])
        if remaining <= 0:
            await query.answer("❌ Лобби уже заполнено", show_alert=True)
            return
        await query.answer()
        await query.edit_message_text(
            f"🤖 Сколько ботов добавить? (свободно мест: {remaining})",
            reply_markup=bots_menu_keyboard("dice", remaining)
        )
        return

    if data == "dice_bots_back":
        await query.answer()
        await query.edit_message_text(dice_lobby_text(state), reply_markup=dice_lobby_keyboard(state), parse_mode='Markdown')
        return

    if data.startswith("dice_addbots_"):
        if state['status'] != 'waiting':
            await query.answer("❌ Игра уже началась", show_alert=True)
            return
        if user_id != state['host']:
            await query.answer("❌ Только хост может добавлять ботов", show_alert=True)
            return
        count = int(data.split("_")[2])
        added = 0
        for _ in range(count):
            if len(state['players']) >= MAX_DICE:
                break
            bot_uid = create_bot_player()
            players[bot_uid]['balance'] -= state['bet']
            state['players'].append(bot_uid)
            added += 1
        await query.answer(f"Добавлено ботов: {added}")
        await query.edit_message_text(dice_lobby_text(state), reply_markup=dice_lobby_keyboard(state), parse_mode='Markdown')
        return

    if data == "dice_cancel":
        if state['status'] != 'waiting':
            await query.answer("❌ Игра уже началась", show_alert=True)
            return
        if user_id != state['host']:
            await query.answer("❌ Только хост может отменить", show_alert=True)
            return
        for uid in state['players']:
            players[uid]['balance'] += state['bet']
        await unpin_game_message(context.bot, chat_id, state['message_id'])
        del games_dice[chat_id]
        await query.answer("Игра отменена, ставки возвращены")
        await query.edit_message_text("❌ Лобби Костей отменено, ставки возвращены.")
        save_data()
        return

    if data == "dice_join":
        if state['status'] != 'waiting':
            await query.answer("❌ Лобби не найдено или игра уже началась", show_alert=True)
            return
        if user_id in state['players']:
            await query.answer("Ты уже в игре!", show_alert=True)
            return
        if len(state['players']) >= MAX_DICE:
            await query.answer("❌ Лобби заполнено (макс. 6)", show_alert=True)
            return
        if user_id not in players:
            players[user_id] = {
                "name": update.effective_user.full_name,
                "balance": 1000, "games": {"uno": 0}, "wins": 0, "losses": 0
            }
        if players[user_id]['balance'] < state['bet']:
            await query.answer(f"❌ Недостаточно монет. Нужно: {state['bet']}", show_alert=True)
            return
        players[user_id]['balance'] -= state['bet']
        state['players'].append(user_id)
        await query.answer("Ты присоединился!")
        await query.edit_message_text(
            dice_lobby_text(state), reply_markup=dice_lobby_keyboard(state), parse_mode='Markdown'
        )
        return

    if data == "dice_start":
        if state['status'] != 'waiting':
            await query.answer("❌ Лобби не найдено", show_alert=True)
            return
        if user_id != state['host']:
            await query.answer("❌ Только хост может начать игру", show_alert=True)
            return
        if len(state['players']) < MIN_DICE:
            await query.answer(f"❌ Нужно минимум {MIN_DICE} игрока", show_alert=True)
            return
        random.shuffle(state['players'])
        state['status'] = 'picking'
        await query.answer("Игра начинается!")
        await query.edit_message_text(
            dice_board_text(state), reply_markup=dice_board_keyboard(state), parse_mode='Markdown'
        )
        await maybe_bot_turn_dice(chat_id, context)
        return

    if data.startswith("dice_pick_"):
        if state['status'] != 'picking':
            await query.answer("❌ Игра не найдена", show_alert=True)
            return
        current_uid = state['players'][state['turn_idx']]
        if user_id != current_uid:
            await query.answer("❌ Сейчас не твой ход!", show_alert=True)
            return
        num = int(data.split("_")[2])
        if num in state['picks']:
            await query.answer("❌ Это число уже занято", show_alert=True)
            return
        await query.answer(f"Выбрано число {num}")
        await resolve_dice_pick(chat_id, user_id, num, context)
        return

async def stop_dice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    state = games_dice.get(chat_id)

    if not state:
        await update.message.reply_text("📭 В этом чате сейчас нет игры Кости.")
        return

    allowed = user_id == state['host']
    if not allowed and update.effective_chat.type != "private":
        member = await context.bot.get_chat_member(chat_id, user_id)
        allowed = member.status in ("administrator", "creator")
    if not allowed:
        await update.message.reply_text("❌ Остановить игру может только хост или админ группы.")
        return

    for uid in state['players']:
        players[uid]['balance'] += state['bet']

    try:
        if state.get('message_id'):
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=state['message_id'],
                text="⛔ **Игра Кости остановлена, ставки возвращены.**", parse_mode='Markdown'
            )
            await unpin_game_message(context.bot, chat_id, state['message_id'])
    except Exception:
        pass

    del games_dice[chat_id]
    await update.message.reply_text("⛔ Игра Кости остановлена, ставки возвращены.")
    save_data()

# ================= ПЕРЕВОД МОНЕТ =================

async def pay_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender_id = update.effective_user.id

    if sender_id not in players:
        players[sender_id] = {
            "name": update.effective_user.full_name,
            "balance": 1000, "games": {"uno": 0}, "wins": 0, "losses": 0
        }
    ensure_usd(sender_id)

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "💸 Чтобы перевести — ответь на сообщение игрока командой:\n"
            "`/pay <сумма>` — монеты\n`/pay <сумма> $` — доллары",
            parse_mode='Markdown'
        )
        return

    target_user = update.message.reply_to_message.from_user
    if target_user.is_bot:
        await update.message.reply_text("❌ Нельзя переводить боту.")
        return
    if target_user.id == sender_id:
        await update.message.reply_text("❌ Нельзя переводить самому себе.")
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "Использование:\n`/pay <сумма>` — монеты\n`/pay <сумма> $` — доллары",
            parse_mode='Markdown'
        )
        return

    in_usd = len(args) > 1 and args[1].lower() in ('$', 'usd', 'доллар', 'доллары', 'долларов')

    if target_user.id not in players:
        players[target_user.id] = {
            "name": target_user.full_name,
            "balance": 1000, "games": {"uno": 0}, "wins": 0, "losses": 0
        }
    ensure_usd(target_user.id)

    if in_usd:
        try:
            amount = float(args[0])
        except ValueError:
            await update.message.reply_text("❌ Введи число, например: /pay 2.5 $")
            return
        if amount <= 0:
            await update.message.reply_text("❌ Сумма должна быть больше нуля.")
            return
        if players[sender_id]['usd'] < amount:
            await update.message.reply_text(f"❌ Недостаточно долларов. У тебя: {round(players[sender_id]['usd'], 4)} $")
            return

        players[sender_id]['usd'] -= amount
        players[target_user.id]['usd'] += amount
        await update.message.reply_text(
            f"💸 {players[sender_id]['name']} перевёл {amount} $ игроку {players[target_user.id]['name']}!"
        )
    else:
        if not args[0].isdigit():
            await update.message.reply_text("❌ Введи целое число монет, например: /pay 500")
            return
        amount = int(args[0])
        if amount <= 0:
            await update.message.reply_text("❌ Сумма должна быть больше нуля.")
            return
        if players[sender_id]['balance'] < amount:
            await update.message.reply_text(f"❌ Недостаточно монет. Баланс: {players[sender_id]['balance']}")
            return

        if amount > PAY_LIMIT:
            await update.message.reply_text(f"❌ Максимум за один перевод: {PAY_LIMIT} монет.")
            return

        players[sender_id]['balance'] -= amount
        players[target_user.id]['balance'] += amount

        await update.message.reply_text(
            f"💸 {players[sender_id]['name']} перевёл {amount} монет игроку {players[target_user.id]['name']}!"
        )

    save_data()

# ================= ОТРАВЛЕННЫЕ ПЕЧЕНЬКИ =================

def cookies_challenge_text(state):
    return (f"🍪 **Отравленные печеньки**\n\n"
            f"Вызов от {players[state['host']]['name']}\n"
            f"Ставка: {state['bet']} монет\n\n"
            f"Правила: каждый тайно травит одну печеньку из {COOKIES_TOTAL} в личке боту, "
            f"потом едим по очереди — кто съест отравленную, тот проигрывает.\n\n"
            f"Кто примет вызов?")

def cookies_board_keyboard(state, disabled=False):
    keyboard = []
    row = []
    for i in range(1, COOKIES_TOTAL + 1):
        if i in state['eaten']:
            label = "✅"
            cb = "cook_noop"
        else:
            label = "🍪"
            cb = f"cook_noop" if disabled else f"cook_eat_{i}"
        row.append(InlineKeyboardButton(label, callback_data=cb))
        if len(row) == 6:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)

def cookies_poison_keyboard(chat_id, prefix):
    keyboard = []
    row = []
    for i in range(1, COOKIES_TOTAL + 1):
        row.append(InlineKeyboardButton(str(i), callback_data=f"{prefix}_{chat_id}_{i}"))
        if len(row) == 6:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)

async def cookies_board_text(state):
    current_uid = state['host'] if state['turn'] == 'host' else state['opponent']
    return (f"🍪 **Отравленные печеньки**\n\n"
            f"💰 Банк: {state['bet'] * 2} монет\n"
            f"Съедено: {len(state['eaten'])}/{COOKIES_TOTAL}\n\n"
            f"▶️ Ход: **{players[current_uid]['name']}**\n\n"
            f"Выбирай печеньку!")

async def cookies_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if user_id not in players:
        players[user_id] = {
            "name": update.effective_user.full_name,
            "balance": 1000, "games": {"uno": 0}, "wins": 0, "losses": 0
        }

    if games_cookies.get(chat_id) and games_cookies[chat_id]['status'] != 'done':
        await update.message.reply_text("⚠️ В этом чате уже есть открытая игра в печеньки!")
        return

    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("Использование: /cookies <ставка>\nНапример: /cookies 100")
        return

    bet = int(args[0])
    if bet <= 0:
        await update.message.reply_text("❌ Ставка должна быть больше нуля.")
        return
    if players[user_id]['balance'] < bet:
        await update.message.reply_text(f"❌ Недостаточно монет. Баланс: {players[user_id]['balance']}")
        return

    if not await can_dm(user_id, context):
        me = await context.bot.get_me()
        keyboard = [[InlineKeyboardButton("✉️ Открыть личку с ботом", url=f"https://t.me/{me.username}")]]
        await update.message.reply_text(
            "❌ Нужно сначала написать боту в личку /start — травить печеньки нужно там.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    state = {
        "host": user_id, "opponent": None, "bet": bet, "status": "waiting",
        "host_poison": None, "opp_poison": None, "eaten": set(), "turn": "host",
        "chat_id": chat_id, "message_id": None,
    }
    games_cookies[chat_id] = state

    keyboard = [
        [InlineKeyboardButton("🍪 Принять вызов", callback_data="cook_join")],
        [InlineKeyboardButton("❌ Отменить", callback_data="cook_cancel")]
    ]
    msg = await update.message.reply_text(cookies_challenge_text(state), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    state['message_id'] = msg.message_id
    await pin_game_message(context.bot, chat_id, msg.message_id)

async def finish_cookies(chat_id, winner_uid, context: ContextTypes.DEFAULT_TYPE, reason: str, draw=False):
    state = games_cookies[chat_id]
    if draw:
        players[state['host']]['balance'] += state['bet']
        players[state['opponent']]['balance'] += state['bet']
        text = f"🍪 **Ничья!** {reason}\nСтавки возвращены."
    else:
        loser_uid = state['opponent'] if winner_uid == state['host'] else state['host']
        players[winner_uid]['balance'] += state['bet'] * 2
        players[winner_uid]['wins'] += 1
        players[loser_uid]['losses'] += 1
        text = f"🍪 **{reason}**\n\n🏆 Победитель: {players[winner_uid]['name']} (+{state['bet']} монет)"
    try:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=state['message_id'], text=text, parse_mode='Markdown')
    except Exception:
        pass
    await unpin_game_message(context.bot, chat_id, state['message_id'])
    state['status'] = 'done'
    del games_cookies[chat_id]

async def cookies_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    data = query.data

    if data == "cook_noop":
        await query.answer()
        return

    if data == "cook_join":
        chat_id = update.effective_chat.id
        state = games_cookies.get(chat_id)
        if not state or state['status'] != 'waiting':
            await query.answer("❌ Вызов не найден", show_alert=True)
            return
        if user_id == state['host']:
            await query.answer("❌ Нельзя принять свой же вызов!", show_alert=True)
            return
        if user_id not in players:
            players[user_id] = {
                "name": update.effective_user.full_name,
                "balance": 1000, "games": {"uno": 0}, "wins": 0, "losses": 0
            }
        if players[user_id]['balance'] < state['bet']:
            await query.answer(f"❌ Недостаточно монет. Нужно: {state['bet']}", show_alert=True)
            return
        if not await can_dm(user_id, context):
            await query.answer("❌ Сначала напиши боту в личку /start!", show_alert=True)
            return

        state['opponent'] = user_id
        state['status'] = 'host_poison'
        players[state['host']]['balance'] -= state['bet']
        players[user_id]['balance'] -= state['bet']
        await query.answer("Вызов принят!")
        await query.edit_message_text(
            "🍪 **Игра началась!**\n\nИгроки тайно травят печеньки в личке боту...", parse_mode='Markdown'
        )
        try:
            await context.bot.send_message(
                state['host'], "🍪 Выбери печеньку (1-30), которую отравишь для соперника:",
                reply_markup=cookies_poison_keyboard(chat_id, "cook_hp")
            )
        except Exception:
            pass
        return

    if data == "cook_cancel":
        chat_id = update.effective_chat.id
        state = games_cookies.get(chat_id)
        if not state or state['status'] != 'waiting':
            await query.answer("❌ Нельзя отменить сейчас", show_alert=True)
            return
        if user_id != state['host']:
            await query.answer("❌ Только автор вызова может отменить", show_alert=True)
            return
        await unpin_game_message(context.bot, chat_id, state['message_id'])
        del games_cookies[chat_id]
        await query.answer("Вызов отменён")
        await query.edit_message_text("❌ Вызов в печеньки отменён.")
        return

    if data.startswith("cook_hp_"):
        _, _, chat_id_str, num_str = data.split("_")
        chat_id = int(chat_id_str)
        num = int(num_str)
        state = games_cookies.get(chat_id)
        if not state or state['status'] != 'host_poison' or user_id != state['host']:
            await query.answer("❌ Недоступно", show_alert=True)
            return
        state['host_poison'] = num
        state['status'] = 'opp_poison'
        await query.answer(f"Печенька №{num} отравлена!")
        await query.edit_message_text(f"☠️ Ты отравил печеньку №{num}. Ждём соперника...")
        try:
            await context.bot.send_message(
                state['opponent'], "🍪 Выбери печеньку (1-30), которую отравишь для соперника:",
                reply_markup=cookies_poison_keyboard(chat_id, "cook_op")
            )
        except Exception:
            pass
        return

    if data.startswith("cook_op_"):
        _, _, chat_id_str, num_str = data.split("_")
        chat_id = int(chat_id_str)
        num = int(num_str)
        state = games_cookies.get(chat_id)
        if not state or state['status'] != 'opp_poison' or user_id != state['opponent']:
            await query.answer("❌ Недоступно", show_alert=True)
            return
        state['opp_poison'] = num
        state['status'] = 'eating'
        await query.answer(f"Печенька №{num} отравлена!")
        await query.edit_message_text(f"☠️ Ты отравил печеньку №{num}. Начинаем есть!")
        old_message_id = state['message_id']
        try:
            msg = await context.bot.send_message(
                chat_id, await cookies_board_text(state),
                reply_markup=cookies_board_keyboard(state), parse_mode='Markdown'
            )
            state['message_id'] = msg.message_id
            await unpin_game_message(context.bot, chat_id, old_message_id)
            await pin_game_message(context.bot, chat_id, msg.message_id)
        except Exception:
            pass
        return

    if data.startswith("cook_eat_"):
        chat_id = update.effective_chat.id
        state = games_cookies.get(chat_id)
        if not state or state['status'] != 'eating':
            await query.answer("❌ Игра не найдена", show_alert=True)
            return
        current_uid = state['host'] if state['turn'] == 'host' else state['opponent']
        if user_id != current_uid:
            await query.answer("❌ Сейчас не твой ход!", show_alert=True)
            return
        num = int(data.split("_")[2])
        if num in state['eaten']:
            await query.answer("❌ Эта печенька уже съедена", show_alert=True)
            return

        state['eaten'].add(num)
        await query.answer()

        if num == state['host_poison'] and num == state['opp_poison']:
            await finish_cookies(chat_id, None, context, f"Печенька №{num} была отравлена с обеих сторон!", draw=True)
            return
        if num == state['host_poison']:
            eater_is_host = (current_uid == state['host'])
            winner = state['host'] if not eater_is_host else state['opponent']
            await finish_cookies(chat_id, winner, context, f"💀 Печенька №{num} была отравлена!")
            return
        if num == state['opp_poison']:
            eater_is_opp = (current_uid == state['opponent'])
            winner = state['opponent'] if not eater_is_opp else state['host']
            await finish_cookies(chat_id, winner, context, f"💀 Печенька №{num} была отравлена!")
            return

        state['turn'] = 'opponent' if state['turn'] == 'host' else 'host'
        try:
            await query.edit_message_text(
                await cookies_board_text(state), reply_markup=cookies_board_keyboard(state), parse_mode='Markdown'
            )
        except Exception:
            pass
        return

async def stop_cookies_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    state = games_cookies.get(chat_id)

    if not state or state['status'] == 'done':
        await update.message.reply_text("📭 В этом чате сейчас нет игры в печеньки.")
        return

    allowed = user_id in (state['host'], state['opponent'])
    if not allowed and update.effective_chat.type != "private":
        member = await context.bot.get_chat_member(chat_id, user_id)
        allowed = member.status in ("administrator", "creator")
    if not allowed:
        await update.message.reply_text("❌ Остановить игру может только участник или админ группы.")
        return

    if state['opponent']:
        players[state['host']]['balance'] += state['bet']
        players[state['opponent']]['balance'] += state['bet']

    try:
        if state.get('message_id'):
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=state['message_id'],
                text="⛔ **Игра в печеньки остановлена, ставки возвращены.**", parse_mode='Markdown'
            )
    except Exception:
        pass

    if state.get('message_id'):
        await unpin_game_message(context.bot, chat_id, state['message_id'])
    del games_cookies[chat_id]
    await update.message.reply_text("⛔ Игра в печеньки остановлена, ставки возвращены.")

# ================= КРЕДИТ =================

async def collect_debt(user_id, chat_id, bot):
    if user_id not in credits:
        return
    info = credits.pop(user_id)
    amount = info['amount']
    if user_id not in players:
        return

    players[user_id]['balance'] -= amount
    balance = players[user_id]['balance']
    name = players[user_id]['name']

    text = f"🕴️ **К {name} пришли коллекторы!**\n\nЗа неоплаченный кредит забрали {amount} монет."
    if balance < 0:
        text += f"\n⚠️ Денег не хватило — счёт ушёл в минус: {balance} монет."
    else:
        text += f"\nБаланс: {balance} монет."

    try:
        await bot.send_message(chat_id, text, parse_mode='Markdown')
    except Exception:
        pass
    try:
        await bot.send_message(user_id, text, parse_mode='Markdown')
    except Exception:
        pass

async def schedule_collection(user_id, chat_id, bot):
    await asyncio.sleep(CREDIT_MINUTES * 60)
    await collect_debt(user_id, chat_id, bot)
    
async def credit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if user_id not in players:
        players[user_id] = {
            "name": update.effective_user.full_name,
            "balance": 1000, "games": {"uno": 0}, "wins": 0, "losses": 0
        }

    if user_id in credits:
        info = credits[user_id]
        remaining = max(0, CREDIT_MINUTES * 60 - (time.time() - info['taken_at']))
        await update.message.reply_text(
            f"❌ У тебя уже есть активный кредит на {info['amount']} монет.\n"
            f"Автосписание через {int(remaining // 60)} мин. Погасить раньше: /payback"
        )
        return

    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text(f"Использование: /credit <сумма>\nМаксимум: {CREDIT_MAX} монет")
        return

    amount = int(args[0])
    if amount <= 0:
        await update.message.reply_text("❌ Сумма должна быть больше нуля.")
        return
    if amount > CREDIT_MAX:
        await update.message.reply_text(f"❌ Максимальная сумма кредита: {CREDIT_MAX} монет.")
        return

    # расчёт комиссии (тихо, без упоминаний)
    commission = round(amount * CREDIT_COMMISSION)
    payout = amount - commission

    # начисляем игроку сумму за вычетом комиссии
    players[user_id]['balance'] += payout

    # тихо переводим комиссию банкиру (если он существует)
    banker_uid = username_to_id.get(BANKER_USERNAME.lower())
    if banker_uid and banker_uid != user_id and banker_uid in players:
        players[banker_uid]['balance'] += commission

    # записываем кредит
    credits[user_id] = {"amount": amount, "taken_at": time.time(), "chat_id": chat_id}
    asyncio.create_task(schedule_collection(user_id, chat_id, context.bot))

    # Сообщение БЕЗ упоминаний о комиссии и банкире
    await update.message.reply_text(
        f"💳 **Кредит выдан: {amount} монет**\n\n"
        f"На баланс зачислено: {payout} монет\n\n"
        f"Баланс: {players[user_id]['balance']} монет\n\n"
        f"⏰ Через {CREDIT_MINUTES} минут придут коллекторы и спишут {amount} монет автоматически.\n"
        f"Погасить раньше: /payback",
        parse_mode='Markdown'
    )
    save_data()
    
async def payback_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in credits:
        await update.message.reply_text("📭 У тебя нет активного кредита.")
        return

    amount = credits[user_id]['amount']
    if players[user_id]['balance'] < amount:
        await update.message.reply_text(
            f"❌ Недостаточно монет для погашения. Нужно: {amount}, у тебя: {players[user_id]['balance']}"
        )
        return

    players[user_id]['balance'] -= amount
    del credits[user_id]
    await update.message.reply_text(f"✅ Кредит на {amount} монет погашен досрочно!\nБаланс: {players[user_id]['balance']} монет")
    save_data()

# ================= БИРЖА: ДОЛЛАР ($) =================

def ensure_usd(uid):
    players[uid].setdefault('usd', 0.0)

async def usd_rate_loop():
    global usd_rate, btc_rate
    while True:
        await asyncio.sleep(USD_UPDATE_SECONDS)
        change = random.uniform(-USD_MAX_CHANGE, USD_MAX_CHANGE)
        usd_rate = round(max(1.0, usd_rate * (1 + change)), 2)
        btc_change = random.uniform(-BTC_MAX_CHANGE, BTC_MAX_CHANGE)
        btc_rate = round(max(100.0, btc_rate * (1 + btc_change)), 2)

async def rate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"💵 **Курс доллара**\n\n1 $ = {usd_rate} монет\n\nОбновляется каждые {USD_UPDATE_SECONDS // 60} минуты случайным образом.",
        parse_mode='Markdown'
    )

async def buyusd_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in players:
        players[user_id] = {
            "name": update.effective_user.full_name,
            "balance": 1000, "games": {"uno": 0}, "wins": 0, "losses": 0
        }
    ensure_usd(user_id)

    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text(f"Использование: /buyusd <монеты>\nКурс: 1 $ = {usd_rate} монет")
        return

    coins = int(args[0])
    if coins <= 0:
        await update.message.reply_text("❌ Сумма должна быть больше нуля.")
        return
    if players[user_id]['balance'] < coins:
        await update.message.reply_text(f"❌ Недостаточно монет. Баланс: {players[user_id]['balance']}")
        return

    usd_bought = round(coins / usd_rate, 4)
    players[user_id]['balance'] -= coins
    players[user_id]['usd'] += usd_bought

    await update.message.reply_text(
        f"💵 Куплено: {usd_bought} $ по курсу {usd_rate}\n\n"
        f"Баланс: {players[user_id]['balance']} монет | {round(players[user_id]['usd'], 4)} $"
    )
    save_data()

async def sellusd_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in players:
        players[user_id] = {
            "name": update.effective_user.full_name,
            "balance": 1000, "games": {"uno": 0}, "wins": 0, "losses": 0
        }
    ensure_usd(user_id)

    args = context.args
    if not args:
        await update.message.reply_text(f"Использование: /sellusd <доллары>\nКурс: 1 $ = {usd_rate} монет")
        return

    try:
        usd_amount = float(args[0])
    except ValueError:
        await update.message.reply_text("❌ Введи число, например: /sellusd 2.5")
        return

    if usd_amount <= 0:
        await update.message.reply_text("❌ Сумма должна быть больше нуля.")
        return
    if players[user_id]['usd'] < usd_amount:
        await update.message.reply_text(f"❌ Недостаточно долларов. У тебя: {round(players[user_id]['usd'], 4)} $")
        return

    coins_gained = round(usd_amount * usd_rate)
    players[user_id]['usd'] -= usd_amount
    players[user_id]['balance'] += coins_gained

    await update.message.reply_text(
        f"💵 Продано: {usd_amount} $ по курсу {usd_rate}\n\n"
        f"Получено: {coins_gained} монет\n"
        f"Баланс: {players[user_id]['balance']} монет | {round(players[user_id]['usd'], 4)} $"
    )
    save_data()

# ================= БИРЖА: BTC =================

def ensure_btc(uid):
    players[uid].setdefault('btc', 0.0)

async def btcrate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"₿ **Курс BTC**\n\n1 BTC = {btc_rate} $ = {round(btc_rate * usd_rate)} монет\n\n"
        f"Обновляется каждые {USD_UPDATE_SECONDS // 60} минуты случайным образом.",
        parse_mode='Markdown'
    )

def parse_currency_arg(args, idx):
    if len(args) > idx and args[idx].lower() in ('$', 'usd', 'доллар', 'доллары', 'долларов'):
        return 'usd'
    return 'coins'

async def buybtc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in players:
        players[user_id] = {
            "name": update.effective_user.full_name,
            "balance": 1000, "games": {"uno": 0}, "wins": 0, "losses": 0
        }
    ensure_usd(user_id)
    ensure_btc(user_id)

    args = context.args
    if not args:
        await update.message.reply_text(
            "Использование:\n`/buybtc <монеты>` — купить за монеты\n`/buybtc <сумма> $` — купить за доллары\n"
            f"Курс: 1 BTC = {btc_rate} $ = {round(btc_rate * usd_rate)} монет",
            parse_mode='Markdown'
        )
        return

    currency = parse_currency_arg(args, 1)
    try:
        spend = float(args[0])
    except ValueError:
        await update.message.reply_text("❌ Введи число.")
        return
    if spend <= 0:
        await update.message.reply_text("❌ Сумма должна быть больше нуля.")
        return

    if currency == 'usd':
        if players[user_id]['usd'] < spend:
            await update.message.reply_text(f"❌ Недостаточно долларов. У тебя: {round(players[user_id]['usd'], 4)} $")
            return
        btc_bought = spend / btc_rate
        players[user_id]['usd'] -= spend
        spend_label = f"{spend} $"
    else:
        spend = int(spend)
        if players[user_id]['balance'] < spend:
            await update.message.reply_text(f"❌ Недостаточно монет. Баланс: {players[user_id]['balance']}")
            return
        usd_equiv = spend / usd_rate
        btc_bought = usd_equiv / btc_rate
        players[user_id]['balance'] -= spend
        spend_label = f"{spend} монет"

    players[user_id]['btc'] += btc_bought

    await update.message.reply_text(
        f"₿ Куплено: {round(btc_bought, 8)} BTC за {spend_label}\n\n"
        f"Баланс: {players[user_id]['balance']} монет | {round(players[user_id]['usd'], 4)} $ | {round(players[user_id]['btc'], 8)} BTC"
    )
    save_data()

async def sellbtc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in players:
        players[user_id] = {
            "name": update.effective_user.full_name,
            "balance": 1000, "games": {"uno": 0}, "wins": 0, "losses": 0
        }
    ensure_usd(user_id)
    ensure_btc(user_id)

    args = context.args
    if not args:
        await update.message.reply_text(
            "Использование:\n`/sellbtc <btc> монеты` — продать за монеты (по умолчанию)\n`/sellbtc <btc> $` — продать за доллары\n"
            f"Курс: 1 BTC = {btc_rate} $ = {round(btc_rate * usd_rate)} монет",
            parse_mode='Markdown'
        )
        return

    currency = parse_currency_arg(args, 1)
    try:
        btc_amount = float(args[0])
    except ValueError:
        await update.message.reply_text("❌ Введи число.")
        return
    if btc_amount <= 0:
        await update.message.reply_text("❌ Сумма должна быть больше нуля.")
        return
    if players[user_id]['btc'] < btc_amount:
        await update.message.reply_text(f"❌ Недостаточно BTC. У тебя: {round(players[user_id]['btc'], 8)} BTC")
        return

    usd_value = btc_amount * btc_rate
    players[user_id]['btc'] -= btc_amount

    if currency == 'usd':
        players[user_id]['usd'] += usd_value
        gained_label = f"{round(usd_value, 4)} $"
    else:
        coins_gained = round(usd_value * usd_rate)
        players[user_id]['balance'] += coins_gained
        gained_label = f"{coins_gained} монет"

    await update.message.reply_text(
        f"₿ Продано: {btc_amount} BTC по курсу {btc_rate} $\n\n"
        f"Получено: {gained_label}\n"
        f"Баланс: {players[user_id]['balance']} монет | {round(players[user_id]['usd'], 4)} $ | {round(players[user_id]['btc'], 8)} BTC"
    )
    save_data()

# ================= ОБЫЧНЫЕ КОМАНДЫ =================

async def touch_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user and user.username:
        username_to_id[user.username.lower()] = user.id

async def set_commands(app):
    commands = [
        ("start", "🏠 Главное меню"),
        ("help", "📖 Помощь"),
        ("profile", "👤 Мой профиль"),
        ("games", "🎮 Все игры"),
        ("uno", "🃏 Играть в УНО"),
        ("stopuno", "⛔ Остановить игру УНО"),
        ("coin", "🪙 Орёл или решка"),
        ("stopcoin", "⛔ Отменить вызов Монетка"),
        ("roulette", "🔫 Русская рулетка"),
        ("stoproulette", "⛔ Остановить рулетку"),
        ("dice", "🎲 Кости"),
        ("stopdice", "⛔ Остановить кости"),
        ("cookies", "🍪 Отравленные печеньки"),
        ("stopcookies", "⛔ Остановить печеньки"),
        ("pay", "💸 Перевести монеты"),
        ("credit", "💳 Взять кредит"),
        ("payback", "✅ Погасить кредит"),
        ("rate", "💵 Курс доллара"),
        ("buyusd", "📈 Купить доллары"),
        ("sellusd", "📉 Продать доллары"),
        ("btcrate", "₿ Курс биткоина"),
        ("buybtc", "₿ Купить биткоин"),
        ("sellbtc", "₿ Продать биткоин"),
        ("top", "🏆 Рейтинг игроков"),
    ]
    await app.bot.set_my_commands(commands)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type

    if user_id not in players:
        players[user_id] = {
            "name": update.effective_user.full_name,
            "balance": 1000, "games": {"uno": 0}, "wins": 0, "losses": 0
        }

    keyboard = [
        [InlineKeyboardButton("🎮 Игры", callback_data="games_menu")],
        [InlineKeyboardButton("👤 Профиль", callback_data="profile")],
        [InlineKeyboardButton("💸 Перевести монеты", callback_data="pay_info")],
        [InlineKeyboardButton("🏆 Рейтинг", callback_data="top")],
        [InlineKeyboardButton("📖 Помощь", callback_data="help")]
    ]

    if chat_type == "private":
        me = await context.bot.get_me()
        keyboard.append([InlineKeyboardButton("➕ Добавить в группу", url=f"https://t.me/{me.username}?startgroup=true")])
        text = f"""👋 **Привет, {players[user_id]['name']}!**

Я игровой бот 🎮 Умею играть в УНО с друзьями прямо в группе, вести рейтинг и баланс монет.

💰 Баланс: {players[user_id]['balance']} монет

Добавь меня в группу с друзьями и запусти /uno — или жми кнопки ниже 👇"""
    else:
        text = f"""🎮 **Добро пожаловать, {players[user_id]['name']}!**

💰 Баланс: {players[user_id]['balance']} монет
🏆 Побед: {players[user_id]['wins']}
😢 Поражений: {players[user_id]['losses']}

Выбери действие:"""

    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    message_owners[msg.message_id] = user_id

async def on_bot_added_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status
    if old_status in ('left', 'kicked') and new_status in ('member', 'administrator'):
        chat = result.chat
        keyboard = [
            [InlineKeyboardButton("🃏 Начать УНО", callback_data="game_uno")],
            [InlineKeyboardButton("📖 Помощь", callback_data="help")]
        ]
        text = f"""🎮 **Всем привет!** Меня добавили в «{chat.title}»!

Я умею играть в 🃏 **УНО** прямо здесь, вести рейтинг и баланс монет игроков.

Чтобы начать — напишите /uno (или жмите кнопку ниже). Собираем от 2 до 4 игроков!"""
        await context.bot.send_message(chat.id, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in players:
        await update.message.reply_text("❌ Ты ещё не зарегистрирован! Напиши /start")
        return
    player = players[user_id]
    usd_line = f"💵 Доллары: {round(player.get('usd', 0), 4)} $\n" if player.get('usd', 0) else ""
    btc_line = f"₿ BTC: {round(player.get('btc', 0), 8)}\n" if player.get('btc', 0) else ""
    text = f"""👤 **Твой профиль**

📛 Имя: {player['name']}
💰 Баланс: {player['balance']} монет
{usd_line}{btc_line}🏆 Побед: {player['wins']}
😢 Поражений: {player['losses']}

📊 Игр сыграно: {player['games']['uno']}"""
    keyboard = [[InlineKeyboardButton("🏠 В меню", callback_data="menu")]]
    msg = await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
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
    msg = await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    message_owners[msg.message_id] = user_id

HELP_TEXT = f"""📖 **Помощь**

**Общие команды**
/start — главное меню
/profile — твой профиль (баланс, победы/поражения)
/top — рейтинг игроков по балансу
/games — список всех игр
/help — эта справка

━━━━━━━━━━━━━━━

🃏 **УНО**
Карточная игра на 2-4 игрока в группе.
• `/uno` — создать лобби без ставки, кнопка "Присоединиться" добавляет игроков (макс. 4)
• `/uno <ставка>` — например `/uno 100`, все входящие вносят ту же сумму, победитель забирает банк
• Хост жмёт "🚀 Начать игру" (нужно минимум 2)
• Карты и ход приходят каждому игроку в **личку** — поэтому перед игрой нужно написать боту `/start` в личке
• Ходишь картой того же цвета, значения, или чёрной (Wild)
• Спецкарты: Skip (пропуск хода), Reverse (смена направления), +2 / +4 (следующий берёт карты и пропускает ход), Wild/+4 позволяют выбрать цвет
• Побеждает тот, кто первым избавится от всех карт — забирает банк (или +100 монет, если играли бесплатно)
• `/stopuno` — принудительно остановить игру, ставки вернутся всем (хост или админ группы)

━━━━━━━━━━━━━━━

🪙 **Монетка (Орёл или Решка)**
Дуэль 1 на 1 на ставку.
• `/coin <ставка>` — например `/coin 100`
• Хост выбирает сторону (🦅 Орёл или 👑 Решка)
• Соперник жмёт "🎲 Принять вызов" и автоматически получает противоположную сторону
• Бот подбрасывает монетку — победитель забирает обе ставки
• `/stopcoin` — отменить открытый вызов (автор или админ группы)

━━━━━━━━━━━━━━━

🔫 **Русская рулетка**
От 2 до 6 игроков, до последнего выжившего.
• `/roulette <ставка>` — например `/roulette 50`, все вносят одинаковую сумму в банк
• Хост жмёт "🚀 Начать игру" (нужно минимум 2 игрока)
• По очереди жмёте "🔫 Выстрелить" — шанс выбыть 1 из 6 при каждом выстреле
• Игра идёт раундами, пока не останется один — он забирает весь банк
• `/stoproulette` — принудительно остановить, ставки вернутся всем

━━━━━━━━━━━━━━━

🍪 **Отравленные печеньки**
Дуэль 1 на 1, 30 печенек на столе.
• `/cookies <ставка>` — например `/cookies 100`
• Соперник жмёт "🍪 Принять вызов"
• Каждый тайно травит одну печеньку (1-30) в личке боту — по очереди, начинает создавший вызов
• После этого едите печеньки по очереди — кто съест отравленную (свою или чужую), тот проигрывает и теряет ставку
• `/stopcookies` — принудительно остановить, ставки вернутся всем

━━━━━━━━━━━━━━━

🎲 **Кости**
От 2 до 6 игроков, каждый ставит одну и ту же сумму.
• `/dice <ставка>` — например `/dice 100`
• Хост жмёт "🚀 Начать игру" (нужно минимум 2 игрока)
• По очереди выбираете свободное число от 1 до 6
• Когда все выбрали — бот кидает кубик: у кого выпавший номер, тот забирает весь банк
• Если выпавший номер никто не занял — весь банк сгорает
• `/stopdice` — принудительно остановить, ставки вернутся всем

━━━━━━━━━━━━━━━

💸 **Перевод**
• Ответь на сообщение игрока командой `/pay <сумма>` — монеты
• Или `/pay <сумма> $` — доллары
• Лимит: не больше {PAY_LIMIT} монет за один перевод (можно переводить сколько угодно раз подряд)

━━━━━━━━━━━━━━━

💳 **Кредит**
• `/credit <сумма>` — максимум {CREDIT_MAX} монет, только один активный кредит одновременно
• Кредит выдаётся без комиссии — на баланс зачисляется вся сумма, а возвращать нужно будет ту же сумму кредита
• Через {CREDIT_MINUTES} минут долг спишется автоматически — придут коллекторы и заберут всю сумму кредита
• Если денег не хватит — баланс уйдёт в минус
• Погасить раньше самому: `/payback`

━━━━━━━━━━━━━━━

💵 **Доллар ($) — биржа**
• `/rate` — текущий курс (стартует с {USD_START_RATE} монет за $, дальше меняется случайно каждые {USD_UPDATE_SECONDS // 60} минуты)
• `/buyusd <монеты>` — купить доллары за монеты по текущему курсу
• `/sellusd <доллары>` — продать доллары обратно в монеты по текущему курсу
• Курс скачет случайно ±{int(USD_MAX_CHANGE * 100)}% каждые {USD_UPDATE_SECONDS // 60} минуты — можно ловить моменты подешевле/подороже

━━━━━━━━━━━━━━━

₿ **Биткоин (BTC) — биржа**
• `/btcrate` — текущий курс (стартует с {BTC_START_RATE} $ за 1 BTC, тоже случайно меняется каждые {USD_UPDATE_SECONDS // 60} минуты)
• `/buybtc <монеты>` — купить BTC за монеты
• `/buybtc <сумма> $` — купить BTC за доллары
• `/sellbtc <btc>` — продать BTC за монеты
• `/sellbtc <btc> $` — продать BTC за доллары

━━━━━━━━━━━━━━━


💰 Баланс, победы и поражения одни на все игры и не привязаны к конкретной группе — рейтинг `/top` глобальный.
📌 Пока лобби/игра активны, их сообщение закреплено в чате — открепляется автоматически после окончания. Для этого у бота должны быть права на закрепление сообщений в группе.
🤖 В лобби УНО, Русской рулетки и Костей есть кнопка "Играть с ботом" — можно добить лобби ботами вместо живых игроков, они ходят автоматически."""

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🏠 В меню", callback_data="menu")]]
    msg = await update.message.reply_text(HELP_TEXT, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    message_owners[msg.message_id] = update.effective_user.id

async def games(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """🎮 **Доступные игры**

🃏 **УНО** — карточная игра для 2-4 игроков
🪙 **Монетка** — орёл или решка на ставку, 1 на 1
🔫 **Русская рулетка** — ставка на всех, стреляют по кругу, выживает и забирает банк последний (2-6 игроков)
🍪 **Отравленные печеньки** — тайно травите печеньки и едите по очереди, 1 на 1
🎲 **Кости** — каждый выбирает число 1-6, угадавший забирает банк (2-6 игроков)"""
    keyboard = [
        [InlineKeyboardButton("🃏 УНО", callback_data="game_uno")],
        [InlineKeyboardButton("🪙 Монетка", callback_data="game_coin_info")],
        [InlineKeyboardButton("🔫 Русская рулетка", callback_data="game_roulette_info")],
        [InlineKeyboardButton("🍪 Печеньки", callback_data="game_cookies_info")],
        [InlineKeyboardButton("🎲 Кости", callback_data="game_dice_info")],
        [InlineKeyboardButton("🏠 В меню", callback_data="menu")]
    ]
    msg = await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    message_owners[msg.message_id] = update.effective_user.id

async def uno_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await create_lobby(update, context)

async def stop_uno_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    state = games_uno.get(chat_id)

    if not state:
        await update.message.reply_text("📭 В этом чате сейчас нет игры УНО.")
        return

    allowed = user_id == state['host']
    if not allowed and update.effective_chat.type != "private":
        member = await context.bot.get_chat_member(chat_id, user_id)
        allowed = member.status in ("administrator", "creator")

    if not allowed:
        await update.message.reply_text("❌ Остановить игру может только хост или админ группы.")
        return

    if state.get('bet', 0) > 0:
        for uid in state['players']:
            players[uid]['balance'] += state['bet']

    for uid in state['players']:
        if uid != user_id and not is_bot(uid):
            try:
                await context.bot.send_message(uid, "⛔ Игра УНО была принудительно завершена.")
            except Exception:
                pass

    try:
        if state.get('message_id'):
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=state['message_id'],
                text="⛔ **Игра УНО остановлена.**", parse_mode='Markdown'
            )
    except Exception:
        pass

    if state.get('message_id'):
        await unpin_game_message(context.bot, chat_id, state['message_id'])
    del games_uno[chat_id]
    await update.message.reply_text("⛔ Игра УНО остановлена.")

# ================= ОБЫЧНЫЙ CALLBACK (МЕНЮ) =================

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    data = query.data

    if data == "game_uno":
        chat_id = update.effective_chat.id
        existing = games_uno.get(chat_id)
        if existing and existing['status'] in ('waiting', 'active'):
            await query.answer("⚠️ Игра уже идёт в этом чате", show_alert=True)
            return
        if not await can_dm(user_id, context):
            await query.answer("❌ Сначала напиши боту в личку /start — карты приходят туда!", show_alert=True)
            return
        if user_id not in players:
            players[user_id] = {
                "name": update.effective_user.full_name,
                "balance": 1000, "games": {"uno": 0}, "wins": 0, "losses": 0
            }
        state = {
            "players": [user_id], "hands": {}, "deck": [], "discard": [],
            "turn_idx": 0, "direction": 1, "current_color": None,
            "status": "waiting", "host": user_id, "chat_id": chat_id,
            "message_id": None, "dm_msg": {}, "awaiting_color": None, "bet": 0,
        }
        games_uno[chat_id] = state
        await query.answer()
        await query.edit_message_text(lobby_text(state), reply_markup=lobby_keyboard(state), parse_mode='Markdown')
        state['message_id'] = query.message.message_id
        await pin_game_message(context.bot, chat_id, state['message_id'])
        return

    if context.user_data.get('menu_owner') and context.user_data['menu_owner'] != user_id:
        if message_owners.get(query.message.message_id) and message_owners[query.message.message_id] != user_id:
            await query.answer("❌ Это не твоё меню!", show_alert=True)
            return

    await query.answer()

    if data == "menu":
        keyboard = [
            [InlineKeyboardButton("🎮 Игры", callback_data="games_menu")],
            [InlineKeyboardButton("👤 Профиль", callback_data="profile")],
            [InlineKeyboardButton("💸 Перевести монеты", callback_data="pay_info")],
            [InlineKeyboardButton("🏆 Рейтинг", callback_data="top")],
            [InlineKeyboardButton("📖 Помощь", callback_data="help")]
        ]
        if user_id in players:
            text = f"""🎮 **Главное меню**

💰 Баланс: {players[user_id]['balance']} монет
🏆 Побед: {players[user_id]['wins']}
😢 Поражений: {players[user_id]['losses']}"""
        else:
            text = "🎮 **Главное меню**"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    elif data == "games_menu":
        keyboard = [
            [InlineKeyboardButton("🃏 УНО", callback_data="game_uno")],
            [InlineKeyboardButton("🪙 Монетка", callback_data="game_coin_info")],
            [InlineKeyboardButton("🔫 Русская рулетка", callback_data="game_roulette_info")],
            [InlineKeyboardButton("🍪 Печеньки", callback_data="game_cookies_info")],
            [InlineKeyboardButton("🎲 Кости", callback_data="game_dice_info")],
            [InlineKeyboardButton("🏠 Назад", callback_data="menu")]
        ]
        await query.edit_message_text("🎮 **Выбери игру:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    elif data == "game_dice_info":
        text = """🎲 **Кости**

От 2 до 6 игроков, каждый ставит одну и ту же сумму. По очереди выбираете свободное число от 1 до 6. Когда все выбрали — бот кидает кубик: чей номер выпал, тот забирает весь банк. Если номер никто не занял — ставки возвращаются всем.

Использование: `/dice <ставка>`
Например: `/dice 100`"""
        keyboard = [[InlineKeyboardButton("🏠 В меню", callback_data="menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    elif data == "game_coin_info":
        text = """🪙 **Орёл или Решка**

Дуэль на двоих — ставите одинаковую сумму, хост выбирает орла или решку, соперник автоматически получает другую сторону. Бот подкидывает монетку, победитель забирает всё.

Использование: `/coin <ставка>`
Например: `/coin 100`"""
        keyboard = [[InlineKeyboardButton("🏠 В меню", callback_data="menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    elif data == "game_roulette_info":
        text = """🔫 **Русская рулетка**

От 2 до 6 игроков, каждый ставит одну и ту же сумму. По кругу нажимаете "Выстрелить" (1 шанс из 6 выбыть). Игра идёт раундами, пока не останется один — он забирает весь банк.

Использование: `/roulette <ставка>`
Например: `/roulette 50`"""
        keyboard = [[InlineKeyboardButton("🏠 В меню", callback_data="menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    elif data == "game_cookies_info":
        text = """🍪 **Отравленные печеньки**

Дуэль на двоих, 30 печенек на столе. Каждый тайно травит одну печеньку в личке боту, потом едите по очереди — кто съест отравленную (свою или чужую), тот проигрывает.

Использование: `/cookies <ставка>`
Например: `/cookies 100`"""
        keyboard = [[InlineKeyboardButton("🏠 В меню", callback_data="menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    elif data == "pay_info":
        text = f"""💸 **Перевод монет**

Ответь на сообщение игрока в группе командой:
`/pay <сумма>`

Например: `/pay 500`

⚠️ Лимит: не больше {PAY_LIMIT} монет за один перевод (переводов можно делать сколько угодно)."""
        keyboard = [[InlineKeyboardButton("🏠 В меню", callback_data="menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

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
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    elif data == "top":
        sorted_players = sorted(players.items(), key=lambda x: x[1]['balance'], reverse=True)
        text = "🏆 **ТОП ИГРОКОВ**\n\n"
        for i, (uid, pdata) in enumerate(sorted_players[:10], 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            text += f"{medal} {pdata['name']} — {pdata['balance']} монет\n"
        keyboard = [[InlineKeyboardButton("🏠 В меню", callback_data="menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    elif data == "help":
        keyboard = [[InlineKeyboardButton("🏠 В меню", callback_data="menu")]]
        await query.edit_message_text(HELP_TEXT, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# ================= ГЛАВНАЯ ФУНКЦИЯ =================

async def post_init(app):
    await set_commands(app)
    asyncio.create_task(usd_rate_loop())
    asyncio.create_task(autosave_loop())

def main():
    load_data()
    app = Application.builder().token(TOKEN).post_init(post_init).build()

    app.add_handler(MessageHandler(filters.ALL, touch_username), group=-1)
    app.add_handler(CallbackQueryHandler(touch_username), group=-1)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CommandHandler("games", games))
    app.add_handler(CommandHandler("uno", uno_command))
    app.add_handler(CommandHandler("stopuno", stop_uno_command))
    app.add_handler(CommandHandler("coin", coin_command))
    app.add_handler(CommandHandler("stopcoin", stop_coin_command))
    app.add_handler(CommandHandler("roulette", roulette_command))
    app.add_handler(CommandHandler("stoproulette", stop_roulette_command))
    app.add_handler(CommandHandler("dice", dice_command))
    app.add_handler(CommandHandler("stopdice", stop_dice_command))
    app.add_handler(CommandHandler("pay", pay_command))
    app.add_handler(CommandHandler("credit", credit_command))
    app.add_handler(CommandHandler("payback", payback_command))
    app.add_handler(CommandHandler("rate", rate_command))
    app.add_handler(CommandHandler("buyusd", buyusd_command))
    app.add_handler(CommandHandler("sellusd", sellusd_command))
    app.add_handler(CommandHandler("btcrate", btcrate_command))
    app.add_handler(CommandHandler("buybtc", buybtc_command))
    app.add_handler(CommandHandler("sellbtc", sellbtc_command))
    app.add_handler(CommandHandler("cookies", cookies_command))
    app.add_handler(CommandHandler("stopcookies", stop_cookies_command))

    app.add_handler(ChatMemberHandler(on_bot_added_to_group, ChatMemberHandler.MY_CHAT_MEMBER))

    app.add_handler(CallbackQueryHandler(uno_callback_handler, pattern="^uno_"))
    app.add_handler(CallbackQueryHandler(coin_callback_handler, pattern="^coin_"))
    app.add_handler(CallbackQueryHandler(roulette_callback_handler, pattern="^roul_"))
    app.add_handler(CallbackQueryHandler(dice_callback_handler, pattern="^dice_"))
    app.add_handler(CallbackQueryHandler(cookies_callback_handler, pattern="^cook_"))
    app.add_handler(CallbackQueryHandler(callback_handler))

    print("🎮 Бот Agent Bot запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
        
