import time
from collections import defaultdict
import logging
import sqlite3
from telegram import Update
from telegram.ext import ContextTypes
from config import SPAM_LIMIT, DB_NAME
from database import is_banned, ban_user, get_random_character # keeping from your imports
from auto_spawn import trigger_weighted_spawn, hint_callback, auto_spawn_watcher

logger = logging.getLogger(__name__)

# Per-user message tracker for spam prevention
user_message_log = defaultdict(list)


# ==================== 🚀 AUTO SPAWN ENGINE ====================
async def trigger_spawn_auto(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Fetches a random character and summons them to the group chat."""
    char = get_random_character()
    if not char: 
        return
        
    char_id, name, anime, rarity, msg_id = char

    context.chat_data["active_spawn"] = {
        "id": char_id,
        "name": name.strip().lower(),
        "claimed": False
    }

    # 🎯 അനിമൊയും റാരിറ്റിയും മാത്രം blockquote-ലേക്ക് മാറ്റി!
    text = (
        f"💌 <b>A mysterious summon has been detected!</b>\n\n"
        f"<blockquote>🎌 <b>Anime:</b> {anime}\n"
        f"🏅 <b>Rarity:</b> {rarity}</blockquote>\n\n"
        f"⚡ Type /summon [name] to claim them!"
    )

    try:
        await send_character_media(context.bot, chat_id, msg_id, text)
    except Exception as e:
        logger.error(f"Spawn error: {e}")
        await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")


# ==================== 📊 UNIFIED MESSAGE, SPAM, & GROUP TRACKER ====================
async def track_messages_and_save_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1️⃣ ചാറ്റ് ഉണ്ടെന്നും അത് പ്രൈവറ്റ് അല്ലെന്നും ഉറപ്പുവരുത്തുന്നു
    if not update.effective_chat or update.effective_chat.type == "private" or not update.effective_user:
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name if update.effective_user else "User"

    # ⚠️ ഒരു കാരണവശാലും കമാൻഡുകൾ നമ്മൾ കൗണ്ട് ചെയ്യരുത് (eg: /changetime, /check)
    if update.message and update.message.text:
        text = update.message.text.strip()
        if text.startswith("/"):
            return

    # 🚫 SPAM CHECK BLOCK 
    now = time.time()
    user_message_log[user_id].append(now)
    
    # Keep only last 60s of messages
    user_message_log[user_id] = [t for t in user_message_log[user_id] if now - t < 60]

    # If over limit, ban and stop execution
    if len(user_message_log[user_id]) > SPAM_LIMIT and not is_banned(user_id):
        try:
            ban_user(user_id, update.effective_user.username or "", "Spam")
            await update.message.reply_text(
                f"🔨 <code>{user_id}</code> banned for spam.",
                parse_mode="HTML",
            )
            return  # Stop processing further logic for this spam user
        except Exception as e:
            logger.debug(f"Spam ban failed: {e}")

    # 🗄️ DATABASE & SPAWN LOGIC 
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # PART A: ഗ്രൂപ്പ് ഡാറ്റാബേസിൽ ഉണ്ടെന്ന് ഉറപ്പാക്കുന്നു
        cursor.execute("INSERT OR IGNORE INTO groups (chat_id) VALUES (?)", (chat_id,))

        # PART B: കൗണ്ടിങ് ലോജിക്
        cursor.execute("SELECT message_count, spawn_limit FROM group_settings WHERE chat_id = ?", (chat_id,))
        row = cursor.fetchone()

        if not row:
            cursor.execute("INSERT INTO group_settings (chat_id, message_count, spawn_limit) VALUES (?, 1, 100)", (chat_id,))
            current_count = 1
            spawn_limit = 100
        else:
            current_count = row[0] + 1
            spawn_limit = row[1]
            cursor.execute("UPDATE group_settings SET message_count = ? WHERE chat_id = ?", (current_count, chat_id))

        conn.commit()
        conn.close()

        # 🎯 ലൈവ് പ്രിന്റ്: ബോട്ട് റൺ ചെയ്യുമ്പോൾ ടെർമിനലിൽ ഇത് കാണണം!
        print(f"📈 [LIVE COUNT] Group: {chat_id} | User: {user_name} | Count: {current_count}/{spawn_limit}")

        # 🚀 ലിമിറ്റ് ആയാൽ ക്യാരക്ടറെ സ്പോൺ ചെയ്യിക്കുന്നു
        if current_count >= spawn_limit:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("UPDATE group_settings SET message_count = 0 WHERE chat_id = ?", (chat_id,))
            conn.commit()
            conn.close()

            print(f"🎯 Spawn limit reached in {chat_id}! Triggering auto spawn...")
            await trigger_weighted_spawn(context, chat_id)

    except Exception as e:
        logger.error(f"Error in track_messages_and_save_group: {e}")

