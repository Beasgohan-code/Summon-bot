from storage import connect as db_connect
import time
import random
import re
import sqlite3
import logging
import requests

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
from telegram.constants import ChatAction, ParseMode

from config import (
    DB_NAME, GUESS_TIMEOUT, REWARD_COINS, REACTIONS, BOT_TOKEN, DB_CHANNEL_ID,
)

LOGGER = logging.getLogger(__name__)

# ==================== STATE ====================
ongoing_sessions: dict = {}  # chat_id -> session dict
streak_data: dict = {}       # chat_id -> {"current_streak": int, "last_correct_user": int}


# ==================== HELPERS ====================

def db_query(query: str, params: tuple = (), fetch: str = "all"):
    """Simple sqlite3 query helper matching your bot's style."""
    conn = db_connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(query, params)
    if fetch == "one":
        row = cur.fetchone()
    elif fetch == "all":
        row = cur.fetchall()
    else:
        row = None
    conn.commit()
    conn.close()
    return row


def async_react(chat_id: int, message_id: int):
    """Sets a random reaction via Telegram Bot API (sync, called in background)."""
    try:
        emoji = random.choice(REACTIONS)
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/setMessageReaction"
        requests.post(
            url,
            json={
                "chat_id": chat_id,
                "message_id": message_id,
                "reaction": [{"type": "emoji", "emoji": emoji}],
            },
            timeout=5,
        )
    except Exception as e:
        LOGGER.warning(f"react failed: {e}")


async def react_to_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    """Background task wrapper."""
    await context.application.create_task  # noop, just to silence linters
    # Run the sync request via the bot's event loop in a thread
    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, async_react, chat_id, message_id)


def get_random_character():
    try:
        rows = db_query("SELECT id, name, anime, rarity, msg_id FROM characters", fetch="all")
        if not rows:
            return None
        return dict(random.choice(rows))
    except Exception as e:
        LOGGER.error(f"get_random_character error: {e}")
        return None


def get_fresh_character(chat_id: int):
    if not hasattr(get_fresh_character, "recent_by_chat"):
        get_fresh_character.recent_by_chat = {}
    recent = get_fresh_character.recent_by_chat.setdefault(chat_id, [])
    for _ in range(8):
        char = get_random_character()
        if not char:
            return None
        if char["id"] not in recent:
            recent.append(char["id"])
            if len(recent) > 10:
                recent.pop(0)
            return char
    return char


def ensure_user(user_id: int, name: str = "User"):
    db_query(
        "INSERT OR IGNORE INTO users (user_id, first_name, balance) VALUES (?, ?, 0)",
        (user_id, name),
    )


def add_coins(user_id: int, amount: int):
    db_query(
        "UPDATE users SET balance = balance + ? WHERE user_id = ?",
        (amount, user_id),
    )


async def send_character(update: Update, context: ContextTypes.DEFAULT_TYPE, character: dict):
    """Send the character image with the guess prompt as its caption (single message)."""
    msg_id_value = str(character.get("msg_id", "")).strip()

    # Caption shown UNDER the photo (in a blockquote for visual separation)
    caption = (
        "<blockquote>✨ <b>Guess the character's name!</b>\n\n"
        f"⏳ You have <b>{GUESS_TIMEOUT // 60} minutes</b> to guess.\n"
        "💡 Type the name as a message — partial matches count!"
        "</blockquote>"
    )

    sent_image = False
    if msg_id_value and "_" in msg_id_value:
        file_type, file_id = msg_id_value.split("_", 1)
        try:
            if file_type == "photo":
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=file_id,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                )
            elif file_type == "video":
                await context.bot.send_video(
                    chat_id=update.effective_chat.id,
                    video=file_id,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                )
            elif file_type == "animation":
                await context.bot.send_animation(
                    chat_id=update.effective_chat.id,
                    animation=file_id,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                )
            else:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=file_id,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                )
            sent_image = True
        except Exception as e:
            LOGGER.warning(f"send_media failed for {file_type}: {e}")

    if not sent_image:
        # Fallback: text-only card (no image, but still show the prompt)
        await update.effective_message.reply_text(
            f"🎭 <b>{character.get('name', '???')}</b>\n"
            f"📺 {character.get('anime', '?')}\n"
            "<i>(image unavailable)</i>\n\n"
            + caption,
            parse_mode=ParseMode.HTML,
        )


def new_session(character: dict) -> dict:
    return {
        "current_character": character,
        "start_time": time.time(),
        "guessed": False,
        "guessed_user": None,
    }


# ==================== HANDLERS ====================

async def nguess_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a new round of /nguess in a group."""
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await update.effective_message.reply_text("❌ /nguess only works in groups!")
        return

    chat_id = chat.id

    # Already running?
    if chat_id in ongoing_sessions and ongoing_sessions[chat_id].get("current_character"):
        sess = ongoing_sessions[chat_id]
        elapsed = int(time.time() - sess["start_time"])
        await update.effective_message.reply_text(
            f"🎮 A round is already running! ({elapsed}s elapsed)\n"
            f"💡 Type the character's name to guess."
        )
        return

    await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
    char = get_fresh_character(chat_id)
    if not char:
        await update.effective_message.reply_text(
            "⚠️ No characters in the database. Add some with /upload first!"
        )
        return

    ongoing_sessions[chat_id] = new_session(char)
    await send_character(update, context, char)


async def nguess_dm_block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "❌ /nguess only works in groups! Add me to a group to play."
    )


async def handle_guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle any text message in groups — check if it's a guess."""
    LOGGER.warning(f"NGUESS_HANDLE_GUESS_FIRED: text='{update.effective_message.text if update.effective_message else None}' chat_id={update.effective_chat.id if update.effective_chat else None} sessions={list(ongoing_sessions.keys())}")
    if not update.effective_message or not update.effective_message.text:
        return
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        return
    if update.effective_message.text.startswith("/"):
        return

    chat_id = chat.id
    if chat_id not in ongoing_sessions:
        return

    session = ongoing_sessions[chat_id]
    if "current_character" not in session or session.get("guessed"):
        return

    char = session["current_character"]
    correct_name = (char.get("name") or "").strip().lower()
    if not correct_name:
        LOGGER.error(f"Character {char.get('id')} missing 'name'")
        return

    # Timeout
    if time.time() - session["start_time"] > GUESS_TIMEOUT:
        await update.effective_message.reply_text(
            f"⏳ Time's up! The answer was: <b>{char['name']}</b>",
            parse_mode=ParseMode.HTML,
        )
        next_char = get_fresh_character(chat_id)
        if next_char:
            ongoing_sessions[chat_id] = new_session(next_char)
            await send_character(update, context, next_char)
        else:
            ongoing_sessions.pop(chat_id, None)
        return

    guess = update.effective_message.text.strip().lower()
    if not guess:
        return

    # Match: word boundary on either side
    if re.search(r"\b" + re.escape(guess) + r"\b", correct_name) or \
       re.search(r"\b" + re.escape(correct_name) + r"\b", guess):

        user = update.effective_user
        user_id = user.id
        session["guessed"] = True
        session["guessed_user"] = user_id

        # Streak
        if chat_id not in streak_data:
            streak_data[chat_id] = {"current_streak": 0, "last_correct_user": None}
        streak_data[chat_id]["current_streak"] += 1
        streak_data[chat_id]["last_correct_user"] = user_id
        current_streak = streak_data[chat_id]["current_streak"]

        # Reward
        ensure_user(user_id, user.first_name or "User")
        add_coins(user_id, REWARD_COINS)

        await update.effective_message.reply_text(
            f"🎉 <b>Correct, {user.mention_html()}!</b>\n"
            f"💰 +{REWARD_COINS} coins  •  🔥 Streak: <b>{current_streak}</b>",
            parse_mode=ParseMode.HTML,
        )

        # React (background, fire-and-forget)
        msg_id = update.effective_message.message_id
        import asyncio
        asyncio.create_task(react_to_message(context, chat_id, msg_id))

        # Streak milestone rewards
        if current_streak in (50, 100):
            reward = 1000 if current_streak == 50 else 2000
            last_uid = streak_data[chat_id]["last_correct_user"]
            ensure_user(last_uid, "User")
            add_coins(last_uid, reward)
            await update.effective_message.reply_text(
                f"🏆 <b>Streak {current_streak} milestone!</b>\n"
                f"<a href='tg://user?id={last_uid}'>User</a> earned "
                f"{reward} bonus coins! 💎",
                parse_mode=ParseMode.HTML,
            )
            streak_data[chat_id]["current_streak"] = 0
            streak_data[chat_id]["last_correct_user"] = None

        # Next round after a short pause
        await asyncio.sleep(2)
        next_char = get_fresh_character(chat_id)
        if next_char:
            ongoing_sessions[chat_id] = new_session(next_char)
            await send_character(update, context, next_char)
        else:
            ongoing_sessions.pop(chat_id, None)


async def nguess_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Force-end the current round in this group."""
    chat_id = update.effective_chat.id
    if chat_id in ongoing_sessions:
        char = ongoing_sessions[chat_id].get("current_character")
        ongoing_sessions.pop(chat_id, None)
        await update.effective_message.reply_text(
            f"🛑 Round ended. Answer was: <b>{char['name'] if char else '?'}</b>",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.effective_message.reply_text("ℹ️ No active round.")


# ==================== REGISTER ====================

def register(application):
    """Register all nguess handlers. Call this AFTER the application is built."""
    application.add_handler(CommandHandler("nguess", nguess_cmd, filters=filters.ChatType.GROUPS))
    application.add_handler(CommandHandler("nguess", nguess_dm_block, filters=filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("nguess_end", nguess_end, filters=filters.ChatType.GROUPS))

    # Guess text handler — group=-1 makes it run BEFORE catch_all (group=0)
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS,
            handle_guess,
        ),
        group=-1,
    )

