from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ChatMemberHandler, ContextTypes
)
import random
import logging
import time

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = "8681929189:AAGR7Y-v1ohOTmyVrYhl2ugZrGsw06VDqbo"

players = {}          # {user_id: {"name", "balance", "games": {"uno": 0}, "wins", "losses"}}
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
PAY_WINDOW = 24 * 3600

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
    lines = [f"🃏 **Лобби УНО** ({len(state['players'])}/{MAX_PLAYERS})\n"]
    for i, uid in enumerate(state['players'], 1):
        lines.append(f"{i}. {players[uid]['name']}")
    if len(state['players']) < MIN_PLAYERS:
        lines.append(f"\nЖдём ещё игроков (мин. {MIN_PLAYERS})...")
    else:
        lines.append("\nМожно начинать!")
    return "\n".join(lines)

def lobby_keyboard(state):
    keyboard = [[InlineKeyboardButton("✅ Присоединиться", callback_data="uno_join")]]
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
    }
    games_uno[chat_id] = state

    msg = await update.message.reply_text(
        lobby_text(state), reply_markup=lobby_keyboard(state), parse_mode='Markdown'
    )
    state['message_id'] = msg.message_id

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
        msg = await context.bot.send_message(chat_id, text, parse_mode='Markdown')
        state['message_id'] = msg.message_id

async def send_hand(chat_id, uid, context: ContextTypes.DEFAULT_TYPE, new=False):
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
    players[winner_uid]['balance'] += 100
    for uid in state['players']:
        players[uid]['games']['uno'] += 1
        if uid != winner_uid:
            players[uid]['losses'] += 1
        try:
            await context.bot.send_message(
                uid, f"🏆 Игра окончена! Победитель: **{players[winner_uid]['name']}**", parse_mode='Markdown'
            )
        except Exception:
            pass
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=state['message_id'],
            text=f"🏆 **Игра УНО завершена!**\n\nПобедитель: {players[winner_uid]['name']} 🎉",
            parse_mode='Markdown'
        )
    except Exception:
        pass
    del games_uno[chat_id]

# ================= УНО: КОЛБЭКИ =================

async def uno_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    data = query.data

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
        del games_uno[chat_id]
        await query.answer("Игра отменена")
        await query.edit_message_text("❌ Лобби УНО отменено.")
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
        del games_coin[chat_id]
        return

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
    del games_roulette[chat_id]

async def roulette_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    data = query.data
    state = games_roulette.get(chat_id)

    if not state:
        await query.answer("❌ Игра не найдена", show_alert=True)
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
                await query.edit_message_text(
                    roul_status_text(state, f"💥 БАХ! {name} выбывает из игры."),
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔫 Выстрелить", callback_data="roul_shoot")]]),
                    parse_mode='Markdown'
                )
            except Exception:
                pass
        else:
            state['turn_idx'] = (state['turn_idx'] + 1) % len(state['alive'])
            try:
                await query.edit_message_text(
                    roul_status_text(state, "🔫 Осечка... повезло!"),
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔫 Выстрелить", callback_data="roul_shoot")]]),
                    parse_mode='Markdown'
                )
            except Exception:
                pass
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

    del games_roulette[chat_id]
    await update.message.reply_text("⛔ Русская рулетка остановлена, ставки возвращены.")

# ================= ПЕРЕВОД МОНЕТ =================

def sent_last_24h(uid):
    now = time.time()
    log = players[uid].setdefault('transfer_log', [])
    log[:] = [(ts, amt) for ts, amt in log if now - ts < PAY_WINDOW]
    return sum(amt for _, amt in log)

async def pay_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender_id = update.effective_user.id

    if sender_id not in players:
        players[sender_id] = {
            "name": update.effective_user.full_name,
            "balance": 1000, "games": {"uno": 0}, "wins": 0, "losses": 0
        }

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "💸 Чтобы перевести монеты — ответь на сообщение игрока командой:\n`/pay <сумма>`",
            parse_mode='Markdown'
        )
        return

    target_user = update.message.reply_to_message.from_user
    if target_user.is_bot:
        await update.message.reply_text("❌ Нельзя переводить монеты боту.")
        return
    if target_user.id == sender_id:
        await update.message.reply_text("❌ Нельзя переводить монеты самому себе.")
        return

    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text("Использование: `/pay <сумма>` (ответом на сообщение игрока)", parse_mode='Markdown')
        return

    amount = int(args[0])
    if amount <= 0:
        await update.message.reply_text("❌ Сумма должна быть больше нуля.")
        return
    if players[sender_id]['balance'] < amount:
        await update.message.reply_text(f"❌ Недостаточно монет. Баланс: {players[sender_id]['balance']}")
        return

    already_sent = sent_last_24h(sender_id)
    if already_sent + amount > PAY_LIMIT:
        remaining = PAY_LIMIT - already_sent
        await update.message.reply_text(
            f"❌ Превышен лимит переводов: {PAY_LIMIT} монет за 24 часа.\n"
            f"Уже отправлено за последние 24ч: {already_sent}\nОсталось доступно: {max(remaining, 0)}"
        )
        return

    if target_user.id not in players:
        players[target_user.id] = {
            "name": target_user.full_name,
            "balance": 1000, "games": {"uno": 0}, "wins": 0, "losses": 0
        }

    players[sender_id]['balance'] -= amount
    players[target_user.id]['balance'] += amount
    players[sender_id].setdefault('transfer_log', []).append((time.time(), amount))

    await update.message.reply_text(
        f"💸 {players[sender_id]['name']} перевёл {amount} монет игроку {players[target_user.id]['name']}!"
    )

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
        try:
            msg = await context.bot.send_message(
                chat_id, await cookies_board_text(state),
                reply_markup=cookies_board_keyboard(state), parse_mode='Markdown'
            )
            state['message_id'] = msg.message_id
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
            winner = state['host'] if eater_is_host else state['host']
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

    del games_cookies[chat_id]
    await update.message.reply_text("⛔ Игра в печеньки остановлена, ставки возвращены.")

# ================= ОБЫЧНЫЕ КОМАНДЫ =================

async def set_commands(app):
    commands = [
        ("start", "🏠 Главное меню"),
        ("help", "📖 Помощь"),
        ("profile", "👤 Мой профиль"),
        ("games", "🎮 Все игры"),
        ("uno", "🃏 Играть в УНО"),
        ("stopuno", "⛔ Остановить игру УНО"),
        ("coin", "🪙 Орёл или решка"),
        ("roulette", "🔫 Русская рулетка"),
        ("stoproulette", "⛔ Остановить рулетку"),
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
    text = f"""👤 **Твой профиль**

📛 Имя: {player['name']}
💰 Баланс: {player['balance']} монет
🏆 Побед: {player['wins']}
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

HELP_TEXT = """📖 **Помощь**

**Общие команды**
/start — главное меню
/profile — твой профиль (баланс, победы/поражения)
/top — рейтинг игроков по балансу
/games — список всех игр
/help — эта справка

━━━━━━━━━━━━━━━

🃏 **УНО**
Карточная игра на 2-4 игрока в группе.
• `/uno` — создать лобби, кнопка "Присоединиться" добавляет игроков (макс. 4)
• Хост жмёт "🚀 Начать игру" (нужно минимум 2)
• Карты и ход приходят каждому игроку в **личку** — поэтому перед игрой нужно написать боту `/start` в личке
• Ходишь картой того же цвета, значения, или чёрной (Wild)
• Спецкарты: Skip (пропуск хода), Reverse (смена направления), +2 / +4 (следующий берёт карты и пропускает ход), Wild/+4 позволяют выбрать цвет
• Побеждает тот, кто первым избавится от всех карт — получает +100 монет
• `/stopuno` — принудительно остановить игру (хост или админ группы)

━━━━━━━━━━━━━━━

🪙 **Монетка (Орёл или Решка)**
Дуэль 1 на 1 на ставку.
• `/coin <ставка>` — например `/coin 100`
• Хост выбирает сторону (🦅 Орёл или 👑 Решка)
• Соперник жмёт "🎲 Принять вызов" и автоматически получает противоположную сторону
• Бот подбрасывает монетку — победитель забирает обе ставки

━━━━━━━━━━━━━━━

🔫 **Русская рулетка**
От 2 до 6 игроков, до последнего выжившего.
• `/roulette <ставка>` — например `/roulette 50`, все вносят одинаковую сумму в банк
• Хост жмёт "🚀 Начать игру" (нужно минимум 2 игрока)
• По очереди жмёте "🔫 Выстрелить" — шанс выбыть 1 из 6 при каждом выстреле
• Игра идёт раундами, пока не останется один — он забирает весь банк
• `/stoproulette` — принудительно остановить, ставки вернутся всем

━━━━━━━━━━━━━━━

💰 Баланс, победы и поражения одни на все игры и не привязаны к конкретной группе — рейтинг `/top` глобальный."""

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🏠 В меню", callback_data="menu")]]
    msg = await update.message.reply_text(HELP_TEXT, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    message_owners[msg.message_id] = update.effective_user.id

async def games(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """🎮 **Доступные игры**

🃏 **УНО** — карточная игра для 2-4 игроков
🪙 **Монетка** — орёл или решка на ставку, 1 на 1
🔫 **Русская рулетка** — ставка на всех, стреляют по кругу, выживает и забирает банк последний (2-6 игроков)"""
    keyboard = [
        [InlineKeyboardButton("🃏 УНО", callback_data="game_uno")],
        [InlineKeyboardButton("🪙 Монетка", callback_data="game_coin_info")],
        [InlineKeyboardButton("🔫 Русская рулетка", callback_data="game_roulette_info")],
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

    for uid in state['players']:
        if uid != user_id:
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
            "message_id": None, "dm_msg": {}, "awaiting_color": None,
        }
        games_uno[chat_id] = state
        await query.answer()
        await query.edit_message_text(lobby_text(state), reply_markup=lobby_keyboard(state), parse_mode='Markdown')
        state['message_id'] = query.message.message_id
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
            [InlineKeyboardButton("🏠 Назад", callback_data="menu")]
        ]
        await query.edit_message_text("🎮 **Выбери игру:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

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
    app.add_handler(CommandHandler("uno", uno_command))
    app.add_handler(CommandHandler("stopuno", stop_uno_command))
    app.add_handler(CommandHandler("coin", coin_command))
    app.add_handler(CommandHandler("roulette", roulette_command))
    app.add_handler(CommandHandler("stoproulette", stop_roulette_command))

    app.add_handler(ChatMemberHandler(on_bot_added_to_group, ChatMemberHandler.MY_CHAT_MEMBER))

    app.add_handler(CallbackQueryHandler(uno_callback_handler, pattern="^uno_"))
    app.add_handler(CallbackQueryHandler(coin_callback_handler, pattern="^coin_"))
    app.add_handler(CallbackQueryHandler(roulette_callback_handler, pattern="^roul_"))
    app.add_handler(CallbackQueryHandler(callback_handler))

    print("🎮 Бот Agent Bot запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
