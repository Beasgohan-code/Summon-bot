from storage import connect as db_connect
import string
import random
import logging
from datetime import datetime
from html import escape

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode, ChatType
from telegram.ext import ContextTypes

from config import (
    OWNER_ID, DB_NAME, DEFAULT_SPAWN_LIMIT, IMGBB_API_KEY,
    BOT_USERNAME, SUPPORT_CHAT, DB_CHANNEL_ID,
)
from database import (
    execute, fetch_one, fetch_all, fetch_value,
    is_banned, ban_user, unban_user, is_sudo,
    add_sudo_user, remove_sudo_user, 
    owns_character, add_to_collection, remove_from_collection,
    get_character, get_user, get_balance, add_balance, remove_balance,
    get_warn_count, add_warning,
    ensure_user, ensure_group,
    get_streak, update_streak,
)
from commands_user import check_ban, send_character_media
from media_urls import require_character_image_url, telegram_media_reference


logger = logging.getLogger(__name__)


def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


def has_sudo_privileges(user_id: int) -> bool:
    """Return whether a user has owner-level or delegated sudo access.

    The owner is intentionally not required to appear in ``sudo_users``.  The
    owner is the source of truth for full access, while that table contains
    only delegated administrators.
    """
    return is_owner(user_id) or is_sudo(user_id)


RARITY_DISPLAY = {
    1: "⚪ Common", 2: "🔵 Rare", 3: "💮 Special Edition", 
    4: "⭐ Legendary", 5: "🛸 Mythic Edition",
    6: "💝 Valentine Edition", 7: "🏖️ Summer Edition", 8: "🌧️ Rainy Edition", 
    9: "🎃 Halloween Edition", 10: "🎄 Christmas Edition", 11: "❄️ Winter Edition", 
    12: "🎇 New Year Edition",
    13: "🎍 Festival Edition", 14: "🎥 AMV Edition", 15: "🎉 Event Edition", 
    16: "🌌 Celestial Edition", 17: "💎 Luxury Edition", 18: "🔮 Limited Edition"
}

# ==========================
# SUDO CHECK
# ==========================
def check_sudo(update: Update):
    """Return whether the effective user is the owner or a sudo admin."""
    return has_sudo_privileges(update.effective_user.id)


async def _deny(update):
    if update.callback_query:
        await update.callback_query.answer("❌ 𝖠𝖽𝗆𝗂𝗇 𝗈𝗇𝗅𝗒", show_alert=True)
    else:
        await update.message.reply_text("❌ 𝖳𝗁𝗂𝗌 𝖼𝗈𝗆𝗆𝖺𝗇𝖽 𝗂𝗌 𝖺𝖽𝗆𝗂𝗇-𝗈𝗇𝗅𝗒.")
    return

def generate_code(length=7):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))




# ==========================
# /BAN
# ==========================
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    
    target_id = None
    target_username = "Unknown"
    
    # ✉️ റീപ്ലൈ വഴിയാണോ എന്ന് നോക്കുന്നു
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
        target_username = update.message.reply_to_message.from_user.username or "Unknown"
    # 🆔 ഐഡി വഴിയാണോ എന്ന് നോക്കുന്നു
    elif context.args:
        try: 
            target_id = int(context.args[0])
        except ValueError: 
            return await update.message.reply_text("❌ Invalid User ID.")

    if not target_id: 
        return await update.message.reply_text("💡 <b>Usage:</b> Reply to a message with <code>/ban</code> or use <code>/ban [user_id]</code>", parse_mode="HTML")
        
    if target_id == OWNER_ID: 
        return await update.message.reply_text("❌ Cannot ban yourself, Boss!")

    conn = db_connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1️⃣ മെയിൻ users ടേബിളിൽ ബാൻ 1 ആക്കുന്നു
    cursor.execute("INSERT OR IGNORE INTO users (user_id, banned) VALUES (?, 0)", (target_id,))
    cursor.execute("UPDATE users SET banned=1 WHERE user_id=?", (target_id,))
    
    # 2️⃣ നമ്മുടെ പുതിയ banned_users ടേബിളിലേക്കും കൂടി ഡാറ്റ കയറ്റുന്നു (സേഫ്റ്റിക്ക്)
    cursor.execute("INSERT OR REPLACE INTO banned_users (user_id, username) VALUES (?, ?)", (target_id, target_username))
    
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        f"🚫 <b>USER BANNED SUCCESSFULLY</b>\n\n"
        f"<blockquote>👤 <b>Target ID:</b> <code>{target_id}</code>\n"
        f"⚡ <b>Status:</b> Access Denied ❌</blockquote>", 
        parse_mode="HTML"
    )

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    
    target_id = None
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
    elif context.args:
        try: 
            target_id = int(context.args[0])
        except ValueError: 
            return await update.message.reply_text("❌ Invalid User ID.")

    if not target_id: 
        return await update.message.reply_text("💡 <b>Usage:</b> Reply to a message with <code>/unban</code> or use <code>/unban [user_id]</code>", parse_mode="HTML")

    conn = db_connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1️⃣ മെയിൻ ടേബിളിൽ ബാൻ മാറ്റുന്നു
    cursor.execute("UPDATE users SET banned=0 WHERE user_id=?", (target_id,))
    # 2️⃣ സ്പാം ബാൻ ടേബിളിൽ നിന്നും ഇവനെ ഒഴിവാക്കുന്നു
    cursor.execute("DELETE FROM banned_users WHERE user_id=?", (target_id,))
    
    conn.commit()
    conn.close()

    # 3️⃣ 🔄 മെമ്മറിയിലുള്ള അവന്റെ പഴയ സ്പാം കൗണ്ട് ഹിസ്റ്ററി ഫുൾ റീസെറ്റ് ആക്കുന്നു!
    global user_spam_counter
    if target_id in user_spam_counter:
        del user_spam_counter[target_id]

    await update.message.reply_text(
        f"✅ <b>USER UNBANNED SUCCESSFULLY</b>\n\n"
        f"<blockquote>👤 <b>Target ID:</b> <code>{target_id}</code>\n"
        f"✨ <b>Status:</b> Access Granted ✅</blockquote>", 
        parse_mode="HTML"
)

# ==========================
# /WARN
# ==========================
async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_sudo(update):
        return await _deny(update)

    target = None
    reason = "No reason given"

    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user.id
        if context.args:
            reason = " ".join(context.args)
    elif context.args and context.args[0].isdigit():
        target = int(context.args[0])
        if len(context.args) > 1:
            reason = " ".join(context.args[1:])

    if not target:
        return await update.message.reply_text("𝖴𝗌𝖾: /warn ﹤user_id﹥ ﹤reason﹥ (𝗈𝗋 𝗋𝖾𝗉𝗅𝗒)")

    warned_by = update.effective_user.id
    add_warning(target, warned_by, reason)
    count = get_warn_count(target)

    await update.message.reply_text(
        f"⚠️ 𝖶𝖺𝗋𝗇𝖾𝖽 ﹤code﹥{target}﹤/code﹥ ({count}/3)\n𝖱𝖾𝖺𝗌𝗈𝗇: {reason}",
        parse_mode=ParseMode.HTML,
    )

    if count >= 3:
        ban_user(target, "", "3 warnings")
        await update.message.reply_text(f"🔨 𝖠𝗎𝗍𝗈-𝖡𝖺𝗇𝗇𝖾𝖽 𝖺𝖿𝗍𝖾𝗋 3 𝗐𝖺𝗋𝗇𝗂𝗇𝗀𝗌.")


# ==========================
# /REMOVE
# ==========================
async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: 
        return
        
    if len(context.args) < 2: 
        return await update.message.reply_text("/remove <user_id> <char_id>")
    
    user_id = context.args[0]
    char_id = context.args[1]

    # ഡാറ്റാബേസ് ഓപ്പറേഷൻസ്
    conn = db_connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_collection WHERE user_id=? AND character_id=?", (int(user_id), char_id))
    conn.commit()
    conn.close()

    # മെസ്സേജ് അയക്കാൻ ആവശ്യമായ ടെക്സ്റ്റ് സെറ്റ് ചെയ്യുന്നു
    response_text = (
        "<blockquote>\n"
        "🗑 <b>Remove character</b>\n"
        f"<b>From:</b> <a href='tg://user?id={user_id}'>User</a> (ID: <code>{user_id}</code>)\n"
        f"<b>Character ID:</b> <code>{char_id}</code>\n"
        "</blockquote>"
    )

    # മെസ്സേജ് ബോക്സ് അയക്കുന്നു
    await update.message.reply_text(response_text, parse_mode="HTML")



# ==========================
# /UPLOAD COMMAND
# ==========================
def _next_character_id(cursor) -> str:
    """Return the first unused numeric character ID."""
    cursor.execute("SELECT id FROM characters")
    existing_ids = set()
    for row in cursor.fetchall():
        try:
            existing_ids.add(int(row[0]))
        except (TypeError, ValueError):
            continue

    next_number = 1
    while next_number in existing_ids:
        next_number += 1
    return f"{next_number:02d}"


def _telegram_media_from_message(message):
    """Return the best Telegram file ID and its media type from a message."""
    if message.photo:
        return "photo", message.photo[-1].file_id
    if message.video:
        return "video", message.video.file_id
    if message.animation:
        return "animation", message.animation.file_id
    return None, None


async def upload_character(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add a character from media replied to by the owner or a sudo admin.

    Usage: reply to a photo, video, or GIF with
    ``/upload <name> <anime> <rarity-id>``. Telegram file IDs are durable and
    are stored as a ``telegram:...`` reference; no local upload directory or
    bot-token-bearing URL is created.
    """
    user_id = update.effective_user.id
    if not has_sudo_privileges(user_id):
        return await update.message.reply_text("❌ You do not have Sudo privileges!")

    # Accept both the documented reply workflow and a command used as a
    # caption on the media itself.
    media_message = update.message.reply_to_message or update.message
    media_type, file_id = _telegram_media_from_message(media_message)
    if not file_id:
        return await update.message.reply_text(
            "❌ Reply to, or caption, a photo, video, or GIF with this command.\n\n"
            "💡 Usage: <code>/upload &lt;name&gt; &lt;anime&gt; &lt;rarity-id&gt;</code>\n"
            "Example: <code>/upload Yelan Genshin-impact 5</code>",
            parse_mode=ParseMode.HTML,
        )

    if len(context.args) != 3:
        return await update.message.reply_text(
            "❌ Invalid format.\n\n"
            "💡 Usage: <code>/upload &lt;name&gt; &lt;anime&gt; &lt;rarity-id&gt;</code>\n"
            "Reply to or caption the media you want to upload.",
            parse_mode=ParseMode.HTML,
        )

    char_name = context.args[0].replace("-", " ").strip().title()
    anime_name = context.args[1].replace("-", " ").strip().title()
    try:
        rarity_id = int(context.args[2])
        rarity = RARITY_DISPLAY[rarity_id]
    except (TypeError, ValueError, KeyError):
        return await update.message.reply_text("❌ Invalid rarity ID. Use a number from 1 to 18.")

    char_id = None
    conn = db_connect(DB_NAME)
    try:
        cursor = conn.cursor()
        char_id = _next_character_id(cursor)
        media_reference = telegram_media_reference(media_type, file_id)
        cursor.execute(
            """
            INSERT INTO characters (id, name, anime, rarity, image_url)
            VALUES (?, ?, ?, ?, ?)
            """,
            (char_id, char_name, anime_name, rarity, media_reference),
        )
        conn.commit()
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        logger.exception("Character upload failed for user %s", user_id)
        return await update.message.reply_text(f"❌ Character upload failed: {escape(str(exc))}")
    finally:
        conn.close()

    caption = (
        "✅ <b>Character uploaded successfully</b>\n\n"
        f"🆔 <b>ID:</b> <code>{escape(char_id)}</code>\n"
        f"👤 <b>Name:</b> {escape(char_name)}\n"
        f"🎌 <b>Anime:</b> {escape(anime_name)}\n"
        f"✨ <b>Rarity:</b> {escape(rarity)}\n"
        f"📂 <b>Media:</b> {escape(media_type.title())}"
    )

    # Keep the configured database/archive channel informed, but do not make a
    # successful database write fail because that optional notification failed.
    archive_chat = DB_CHANNEL_ID
    if archive_chat and archive_chat != update.effective_chat.id:
        try:
            await send_character_media(
                context.bot,
                archive_chat,
                media_reference,
                caption,
            )
        except Exception:
            logger.warning("Could not archive character %s", char_id, exc_info=True)

    await send_character_media(
        context.bot,
        update.effective_chat.id,
        media_reference,
        caption,
    )


# Character metadata additions use approved external URLs. Use /addchar (or
# /add) and /update when a URL is already available.

async def trigger_spawn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. സുരക്ഷാ ചെക്ക് (Sudo/Owner ആണോ എന്ന് പരിശോധിക്കുന്നു)
    # നിങ്ങളുടെ ബോട്ടിന്റെ രീതി അനുസരിച്ച് check_sudo(update) അല്ലെങ്കിൽ OWNER_ID ചെക്ക് ഉപയോഗിക്കാം
    if 'check_sudo' in globals():
        if not check_sudo(update):
            return
    elif 'OWNER_ID' in globals():
        if update.effective_user.id != OWNER_ID:
            return await update.message.reply_text("❌ Restricted Command! Not allowed.")
    else:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # 2. ഡാറ്റാബേസിൽ നിന്ന് ഒരു റാൻഡം ക്യാരക്ടറിനെ എടുക്കുന്നു
    db_file = DB_NAME
    conn = db_connect(db_file)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, name, anime, rarity, image_url
        FROM characters 
        ORDER BY RANDOM() 
        LIMIT 1
    """)
    char = cursor.fetchone()
    conn.close()

    if not char:
        return await update.message.reply_text("❌ No characters found in the database.")

    char_id, name, anime, rarity, image_url = char

    # 3. സപspawn ചെയ്ത ക്യാരക്ടറിന്റെ വിവരങ്ങൾ മെമ്മറിയിൽ സൂക്ഷിക്കുന്നു (ക്ലെയിം ചെയ്യാൻ വേണ്ടി)
    # ഗ്രൂപ്പ് ലെവലിൽ ട്രാക്ക് ചെയ്യാൻ chat_data ഉപയോഗിക്കുന്നതാണ് ഏറ്റവും ഉചിതം
    context.chat_data["active_spawn"] = {
        "id": char_id,
        "name": name.strip().lower(),
        "claimed": False
    }

    # ആദ്യത്തെ കോഡിലെ 'last_spawn' ലോജിക് കൂടി ബാക്ക്അപ്പ് ആയി നിലനിർത്തുന്നു (നിങ്ങളുടെ പക്കലുള്ള /summon കമാൻഡിന്റെ സപ്പോർട്ടിനായി)
    context.bot_data["last_spawn"] = {
        "char_id": char_id,
        "chat_id": chat_id,
    }

    # 4. പ്രീമിയം ലുക്കിലുള്ള ടെക്സ്റ്റ് ലേഔട്ട്
    text = (
        "🌠 <b>A Character has been spawned!</b>\n\n"
        "<blockquote>"
        f"🎌 <b>Anime:</b> {anime}\n"
        f"🏅 <b>Rarity:</b> {rarity}\n\n"
        f"⚡ Type <code>/summon [name]</code> to catch!"
        "</blockquote>"
    )

    # 5. മീഡിയ അയക്കുന്നു
    if 'send_character_media' in globals():
        try:
            await send_character_media(
                bot=context.bot, 
                chat_id=chat_id, 
                image_url=image_url,
                caption=text
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Media Error: {e}\n\n{text}", parse_mode=ParseMode.HTML)
    else:
        # ഒരുവേള ഫംഗ്ഷൻ ലഭ്യമല്ലെങ്കിൽ സാധാരണ ടെക്സ്റ്റ് അയക്കാൻ
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
# ==========================
# /CHECKSPAWN
# ==========================
async def checkspawn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1️⃣ ചാറ്റ് ടൈപ്പ് ചെക്ക്: പ്രൈവറ്റ് ഇൻബോക്സിൽ അടിച്ചാൽ ബ്ലോക്ക് ചെയ്യും
    if not update.effective_chat or update.effective_chat.type == ChatType.PRIVATE:
        return await update.message.reply_text("❌ This command can only be used inside Groups!")

    # ബാൻ ചെക്ക് (ഉണ്ടെങ്കിൽ)
    if 'check_ban' in globals() and await check_ban(update):
        return

    chat_id = update.effective_chat.id
    db_file = DB_NAME if 'DB_NAME' in globals() else "summon_collection.db"
    default_limit = DEFAULT_SPAWN_LIMIT if 'DEFAULT_SPAWN_LIMIT' in globals() else 100

    # 2️⃣ ഡാറ്റാബേസിൽ നിന്ന് ഗ്രൂപ്പ് സെറ്റിങ്സ് എടുക്കുന്നു
    conn = db_connect(db_file)
    cursor = conn.cursor()
    
    # ടേബിൾ ഇല്ലെങ്കിൽ എറർ വരാതിരിക്കാൻ നിർബന്ധമായും ക്രിയേറ്റ് ചെയ്യുന്നു
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS group_settings (
        chat_id INTEGER PRIMARY KEY,
        message_count INTEGER DEFAULT 0,
        spawn_limit INTEGER DEFAULT 100
    )
    """)
    
    cursor.execute("SELECT message_count, spawn_limit FROM group_settings WHERE chat_id = ?", (chat_id,))
    row = cursor.fetchone()
    conn.close()

    # 3️⃣ ഡാറ്റാബേസിൽ വിവരങ്ങൾ ഇല്ലെങ്കിൽ ഡിഫോൾട്ട് വാല്യൂസ് സെറ്റ് ചെയ്യുന്നു
    current_count = row[0] if row else 0
    spawn_limit = row[1] if row else default_limit
    
    # അടുത്ത സ്പാനിംഗിന് ഇനി എത്ര മെസ്സേജ് വേണമെന്ന് കണക്കാക്കുന്നു
    next_spawn = max(0, spawn_limit - current_count)

    # 4️⃣ പ്രീമിയം ബോക്സ് ലുക്കിലുള്ള ടെക്സ്റ്റ് ലേഔട്ട്
    text = (
        f"📊 <b>CHAT SPAWN STATUS</b>\n\n"
        f"<blockquote>"
        f"⚙️ <b>Current Limit:</b> {spawn_limit} messages\n"
        f"⏳ <b>Next Spawn In:</b> <code>{next_spawn}</code> messages\n"
        f"📈 <b>Progress:</b> <code>{current_count}/{spawn_limit}</code>"
        f"</blockquote>\n"
        f"<i>💬 Keep chatting to spawn the next character!</i>"
    )

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)
# ==========================
# /CHANGETIME
# ==========================
async def changetime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: 
        return

    if not context.args:
        return await update.message.reply_text(
            "💡 <b>Usage:</b> <code>/changetime [number]</code>\n"
            "Example: <code>/changetime 50</code>",
            parse_mode="HTML"
        )

    try:
        new_limit = int(context.args[0])
        if new_limit <= 0: raise ValueError
    except ValueError:
        return await update.message.reply_text("❌ Invalid number. Please provide a positive number.")

    chat_id = update.effective_chat.id

    conn = db_connect(DB_NAME)
    cursor = conn.cursor()
    
    # ഡാറ്റാബേസിൽ ഈ ഗ്രൂപ്പുണ്ടോ എന്ന് നോക്കി അപ്‌ഡേറ്റ് ചെയ്യുന്നു
    cursor.execute("SELECT message_count FROM group_settings WHERE chat_id = ?", (chat_id,))
    row = cursor.fetchone()
    current_count = row[0] if row else 0

    if not row:
        cursor.execute("INSERT INTO group_settings (chat_id, message_count, spawn_limit) VALUES (?, 0, ?)", (chat_id, new_limit))
    else:
        cursor.execute("UPDATE group_settings SET spawn_limit = ? WHERE chat_id = ?", (new_limit, chat_id))
    
    conn.commit()
    conn.close()

    next_spawn = max(0, new_limit - current_count)

    await update.message.reply_text(
        f"⚙️ <b>SPAWN LIMIT UPDATED!</b>\n\n"
        f"<blockquote>🎯 <b>New Limit for this chat:</b> {new_limit} messages\n"
        f"⏳ <b>Next Spawn In:</b> {next_spawn} messages</blockquote>",
        parse_mode="HTML"
    )


# ==========================================
# 📊 /CHANCE COMMAND (OWNER ONLY)
# ==========================================
async def change_chance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 🔐 Security Check: Only the bot owner can use this command
    if update.effective_user.id != OWNER_ID: 
        return
    
    # Check if correct arguments are provided
    if len(context.args) < 2:
        return await update.message.reply_text(
            "💡 <b>Usage:</b> <code>/chance <Rarity_Number> <New_Value></code>\n"
            "Example: <code>/chance 14 500</code> (Changes AMV Edition)", 
            parse_mode=ParseMode.HTML
        )
        
    try:
        rarity_id = int(context.args[0])
        new_val = int(context.args[1])
        if new_val < 0: 
            raise ValueError
    except ValueError:
        return await update.message.reply_text(
            "❌ <b>Invalid Input!</b> Please use numbers only.\n"
            "Example: <code>/chance 14 500</code>", 
            parse_mode=ParseMode.HTML
        )

    # Validate if the rarity ID exists within the 1-18 list
    if rarity_id not in RARITY_DISPLAY:
        return await update.message.reply_text(
            "❌ <b>Invalid ID!</b> Please use numbers between 1 and 18 only.",
            parse_mode=ParseMode.HTML
        )

    # Update the new chance value inside the database
    conn = db_connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE rarity_chances SET chance_value=? WHERE rarity_id=?", (new_val, rarity_id))
    conn.commit()
    conn.close()

    rarity_full_name = RARITY_DISPLAY[rarity_id]
    await update.message.reply_text(
        f"✅ <b>{rarity_full_name}</b> (ID: {rarity_id}) chance value has been updated to <b>{new_val}</b>!", 
        parse_mode=ParseMode.HTML
    )


# ==========================================
# 🎲 RANDOM CHARACTER CHOOSE SYSTEM
# ==========================================
def get_rarity():
    """Return a weighted display rarity from the configured spawn pool."""
    conn = db_connect(DB_NAME)
    try:
        rows = conn.execute(
            "SELECT rarity_id, rarity_name, chance_value FROM rarity_chances WHERE chance_value > 0"
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return None

    names = [RARITY_DISPLAY.get(row[0], row[1]) for row in rows]
    weights = [max(0, int(row[2])) for row in rows]
    return random.choices(names, weights=weights, k=1)[0]


def get_character_media(char_id):
    """Return the stored Telegram file ID or media URL for a character."""
    row = get_character(str(char_id))
    return row[4] if row else None


def get_random_character():
    """
    1. First, select a weighted rarity based on the configured drop rates.
    2. Try to fetch a random character belonging to that specific rarity from the DB.
    3. Fallback: If no characters exist in that rarity, pick any random character from the entire database.
    """
    # Pick a random rarity name based on the 1-18 system weight
    target_rarity = get_rarity() 
    
    conn = db_connect(DB_NAME)
    cursor = conn.cursor()
    
    # Try fetching characters belonging to the chosen target rarity
    cursor.execute("SELECT id, name, anime, rarity, image_url FROM characters WHERE rarity=?", (target_rarity,))
    chars = cursor.fetchall()
    
    if chars:
        conn.close()
        return random.choice(chars) # Return a random character from the target rarity
        
    # FALLBACK: If the chosen rarity has no characters uploaded yet,
    # pick any random character from the entire database to prevent a bot crash.
    cursor.execute("SELECT id, name, anime, rarity, image_url FROM characters")
    all_chars = cursor.fetchall()
    conn.close()
    
    return random.choice(all_chars) if all_chars else None

# ==========================================
# 📊 /CHANCE LIST (ONLY OWNER CAN CHECK)
# ==========================================
async def chance_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 🔐 ഓണർ ചെക്ക്: ഓണർക്ക് മാത്രമായി ലോക്ക് ചെയ്തു!
    if update.effective_user.id != OWNER_ID: 
        return

    try:
        conn = db_connect(DB_NAME)
        cursor = conn.cursor()
        
        # 1️⃣ ടേബിൾ നിർബന്ധമായും ക്രിയേറ്റ് ചെയ്യുന്നു
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS rarity_chances (
            rarity_id INTEGER PRIMARY KEY,
            rarity_name TEXT,
            chance_value INTEGER
        )
        """)
        
        # 2️⃣ ടേബിളിൽ ഡാറ്റ ഇല്ലെങ്കിൽ ഡിഫോൾട്ട് വാല്യൂസ് കയറ്റുന്നു (1-18)
        cursor.execute("SELECT COUNT(*) FROM rarity_chances")
        if cursor.fetchone()[0] == 0:
            default_chances = [
                (1, "Common", 4500), (2, "Rare", 2500), (3, "Special", 1200),
                (4, "Legendary", 600), (5, "Mythic", 300), (6, "Valentine", 50),
                (7, "Summer", 50), (8, "Rainy", 50), (9, "Halloween", 50),
                (10, "Christmas", 50), (11, "Winter", 50), (12, "New Year", 50),
                (13, "Festival", 40), (14, "AMV", 100), (15, "Event", 100),
                (16, "Celestial", 40), (17, "Luxury", 30), (18, "Limited", 20)
            ]
            cursor.executemany("INSERT OR IGNORE INTO rarity_chances VALUES (?, ?, ?)", default_chances)
            conn.commit()

        # 3️⃣ ഡാറ്റാബേസിൽ നിന്ന് ഐഡിയും പേരും ചാൻസും ഒന്നിച്ച് എടുക്കുന്നു
        cursor.execute("SELECT rarity_id, rarity_name, chance_value FROM rarity_chances ORDER BY rarity_id ASC")
        chances = cursor.fetchall()
        conn.close()

        text = "📊 <b>Drop Rates List (By Number):</b>\n\n<blockquote>"
        total = 0
        
        for r_id, r_name, val in chances:
            # RARITY_DISPLAY ഗ്ലോബൽ ലിസ്റ്റിൽ ഉണ്ടെങ്കിൽ അത് എടുക്കും, ഇല്ലെങ്കിൽ DB-യിലെ പേര് കാണിക്കും
            name = RARITY_DISPLAY.get(r_id, r_name) if 'RARITY_DISPLAY' in globals() else r_name
            text += f"<b>{r_id:02d}.</b> {name} -> <code>{val}</code>\n"
            total += val
            
        text += f"</blockquote>\n📈 Total Pool Weight: <b>{total:,}</b>\n"
        text += "💡 Usage: <code>/chance [number] [value]</code>"
        
        await update.message.reply_text(text, parse_mode="HTML")

    except Exception as e:
        # എന്തെങ്കിലും എറർ ഉണ്ടായാൽ ബോട്ട് ക്രാഷ് ആകാതെ ചാറ്റിൽ കാണിക്കും
        await update.message.reply_text(f"❌ Error: {str(e)}")

# ==========================
# /SUDOLIST
# ==========================
async def addsudo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        return await update.message.reply_text("❌ Only the Bot Owner can add Sudo users!")

    target_user_id = None
    target_username = "Unknown"

    # Message reply addsudo
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        target_user_id = target_user.id
        target_username = target_user.username if target_user.username else target_user.first_name
    # Direct ID input (e.g., /addsudo 12345678)
    elif context.args:
        try:
            target_user_id = int(context.args[0])
            conn = db_connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("SELECT username FROM users WHERE user_id = ?", (target_user_id,))
            user_row = cursor.fetchone()
            conn.close()
            if user_row and user_row[0]:
                target_username = user_row[0]
        except ValueError:
            return await update.message.reply_text("⚠️ Invalid User ID! It must be a numerical Telegram ID.")

    if not target_user_id:
        return await update.message.reply_text("💡 <b>Usage:</b>\n1. Reply to a user with <code>/addsudo</code>\n2. Type <code>/addsudo &lt;user_id&gt;</code>", parse_mode="HTML")

    if is_owner(target_user_id):
        return await update.message.reply_text("⚡ This user is the Bot Owner and already has full privileges!")

    conn = db_connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("SELECT 1 FROM sudo_users WHERE user_id = ?", (target_user_id,))
    if cursor.fetchone():
        conn.close()
        return await update.message.reply_text(f"⚠️ <b>{target_username}</b> is already in the Sudo list!")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO sudo_users (user_id, username, added_at) VALUES (?, ?, ?)", (target_user_id, target_username, now_str))
    conn.commit()
    conn.close()

    success_text = (
        "👑 <b>New Sudo User Added!</b>\n\n"
        f"<blockquote>👤 <b>User:</b> {target_username}\n"
        f"🆔 <b>ID:</b> <code>{target_user_id}</code>\n"
        f"🕒 <b>Time:</b> {now_str}</blockquote>\n"
        "They now have privileges to add, update, and delete characters!"
    )
    await update.message.reply_text(success_text, parse_mode="HTML")


# ==========================================
# 2️⃣ SUDO LIST COMMAND (/sudolist) - Sudo Only
# ==========================================
async def sudolist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not has_sudo_privileges(user_id):
        return await update.message.reply_text("❌ You do not have permission to view the Sudo List!")

    conn = db_connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, added_at FROM sudo_users ORDER BY added_at ASC")
    rows = cursor.fetchall()
    conn.close()

    text = "👑 <b>OFFICIAL SUDO LIST</b> 👑\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n"
    text += f"👑 <b>Owner:</b> <code>{OWNER_ID}</code> (Full Access)\n\n"

    if not rows:
        text += "<i>No other Sudo users added yet.</i>"
    else:
        text += "⚡ <b>Sudo Admins:</b>\n"
        for idx, (s_id, s_name, added_time) in enumerate(rows, 1):
            name_display = f"@{s_name}" if s_name != "Unknown" else "No Username"
            text += f"<b>{idx:02d}.</b> {name_display} | 🆔 <code>{s_id}</code>\n"
            text += f"   └ <i>Added: {added_time}</i>\n"

    text += "\n━━━━━━━━━━━━━━━━━━━━"
    await update.message.reply_text(text, parse_mode="HTML")


# ==========================================
# 3️⃣ EDIT SUDO COMMAND (/editsudo) - Owner Only
# ==========================================
async def editsudo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        return await update.message.reply_text("❌ Only the Bot Owner can edit the Sudo list!")

    conn = db_connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username FROM sudo_users")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return await update.message.reply_text("⚠️ There are no Sudo users in the list to edit!")

    keyboard = []
    for s_id, s_name in rows:
        display_name = f"@{s_name}" if s_name != "Unknown" else f"ID: {s_id}"
        keyboard.append([
            InlineKeyboardButton(f"⚙️ Manage {display_name}", callback_data=f"manage_sudo_{s_id}")
        ])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("⚙️ <b>Sudo Management Panel</b>\nSelect an admin to update or remove:", reply_markup=reply_markup, parse_mode="HTML")


# ==========================================
# 🎮 CALLBACK HANDLER FOR EDIT SUDO BUTTONS
# ==========================================
async def sudo_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if not is_owner(user_id):
        return await query.answer("❌ You are not the Bot Owner!", show_alert=True)

    data = query.data
    await query.answer()

    if data.startswith("manage_sudo_"):
        target_id = int(data.replace("manage_sudo_", ""))
        
        conn = db_connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM sudo_users WHERE user_id = ?", (target_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return await query.message.edit_text("❌ This user is no longer in the Sudo list.")

        username = row[0]
        # ✅ Keep / ❌ Remove buttons
        keyboard = [
            [
                InlineKeyboardButton("❌ Remove Sudo", callback_data=f"rem_sudo_{target_id}"),
                InlineKeyboardButton("✅ Keep Sudo", callback_data="cancel_sudo")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text(
            f"❓ <b>Are you sure you want to remove Sudo privileges for:</b>\n\n"
            f"👤 <b>Username:</b> @{username}\n"
            f"🆔 <b>ID:</b> <code>{target_id}</code>",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )

    elif data.startswith("rem_sudo_"):
        target_id = int(data.replace("rem_sudo_", ""))

        conn = db_connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM sudo_users WHERE user_id = ?", (target_id,))
        row = cursor.fetchone()
        
        if row:
            username = row[0]
            cursor.execute("DELETE FROM sudo_users WHERE user_id = ?", (target_id,))
            conn.commit()
            success = True
        else:
            username = "User"
            success = False
            
        conn.close()

        if success:
            await query.message.edit_text(f"❌ <b>Privileges Revoked!</b>\n\n👤 @{username} (ID: <code>{target_id}</code>) has been successfully removed from the Sudo list.", parse_mode="HTML")
        else:
            await query.message.edit_text("❌ Failed to remove the user. They might have already been removed.")

    elif data == "cancel_sudo":
        await query.message.edit_text("✅ Action cancelled. No changes were made to the Sudo List.")



# ==========================
# /add COMMAND (SUDO)
# ==========================
async def add_character(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create a character with a direct approved HTTPS image URL.

    Usage: /addchar <name> <anime> <rarity-id> <image-url>
    (``/add`` is an alias. ``/upload`` is reserved for replied Telegram media.)
    """
    if not has_sudo_privileges(update.effective_user.id):
        return await update.message.reply_text("❌ You do not have Sudo privileges!")
    if len(context.args) != 4:
        return await update.message.reply_text(
            "💡 Usage: <code>/addchar &lt;name&gt; &lt;anime&gt; &lt;rarity-id&gt; "
            "&lt;Catbox-or-ImgBB-HTTPS-URL&gt;</code>\n"
            "Aliases: <code>/add</code>. <code>/upload</code> uses replied media.",
            parse_mode=ParseMode.HTML,
        )

    char_name = context.args[0].replace("-", " ").title()
    anime_name = context.args[1].replace("-", " ").title()
    try:
        rarity = RARITY_DISPLAY[int(context.args[2])]
        image_url = require_character_image_url(context.args[3])
    except (ValueError, KeyError) as exc:
        return await update.message.reply_text(f"❌ {exc}")

    conn = db_connect(DB_NAME)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM characters")
        existing_ids = {int(row[0]) for row in cursor.fetchall() if str(row[0]).isdigit()}
        next_number = 1
        while next_number in existing_ids:
            next_number += 1
        char_id = f"{next_number:02d}"
        cursor.execute(
            "INSERT INTO characters (id, name, anime, rarity, image_url) VALUES (?, ?, ?, ?, ?)",
            (char_id, char_name, anime_name, rarity, image_url),
        )
        conn.commit()
    finally:
        conn.close()

    caption = (
        f"📝 <b>New Character Added</b>\n\n"
        f"🆔 <code>{char_id}</code>\n"
        f"🎌 {anime_name}\n👤 {char_name}\n✨ {rarity}\n"
        "🌐 Verified external image URL"
    )
    await send_character_media(context.bot, update.effective_chat.id, image_url, caption)

# ==========================================
# 🔄 UPDATED: /update COMMAND WITH WEB HOSTS
# ==========================================
async def update_character(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Update character metadata or its approved external image URL."""
    if not has_sudo_privileges(update.effective_user.id):
        return await update.message.reply_text("❌ You do not have Sudo privileges!")
    if len(context.args) < 3:
        return await update.message.reply_text(
            "💡 Usage: <code>/update &lt;id&gt; image &lt;Catbox-or-ImgBB-HTTPS-URL&gt;</code>\n"
            "Other fields: <code>name</code>, <code>anime</code>, <code>rarity</code>.",
            parse_mode=ParseMode.HTML,
        )

    char_id = context.args[0].zfill(2)
    field = context.args[1].lower()
    raw_value = " ".join(context.args[2:]).strip()
    if field not in {"name", "anime", "rarity", "image"}:
        return await update.message.reply_text("❌ Invalid field. Use name, anime, rarity, or image.")

    if field == "image":
        try:
            value = require_character_image_url(raw_value)
        except ValueError as exc:
            return await update.message.reply_text(f"❌ {exc}")
        column = "image_url"
    elif field == "rarity":
        try:
            value = RARITY_DISPLAY[int(raw_value)]
        except (ValueError, KeyError):
            return await update.message.reply_text("❌ Rarity must be an ID from 1 to 18.")
        column = "rarity"
    else:
        value = raw_value.replace("-", " ").title()
        column = field

    conn = db_connect(DB_NAME)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name, anime, rarity FROM characters WHERE id = ?", (char_id,))
        if not cursor.fetchone():
            return await update.message.reply_text(f"❌ Character with ID {char_id} was not found.")
        cursor.execute(f"UPDATE characters SET {column} = ? WHERE id = ?", (value, char_id))
        conn.commit()
    finally:
        conn.close()

    await update.message.reply_text(
        f"✅ <b>Character Updated</b>\n\n🆔 <code>{char_id}</code>\n"
        f"⚙️ {field.title()}: <code>{value}</code>",
        parse_mode=ParseMode.HTML,
    )

# 3️⃣ DELETE CHARACTER (/deletechar)
async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not has_sudo_privileges(user_id):
        return await update.message.reply_text("❌ You do not have Sudo privileges!")

    if not context.args:
        return await update.message.reply_text("💡 Usage: <code>/deletechar <ID></code>", parse_mode="HTML")

    char_id = context.args[0]

    conn = db_connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM characters WHERE id = ?", (char_id,))
    char_data = cursor.fetchone()
    if not char_data:
        conn.close()
        return await update.message.reply_text(f"❌ Character with ID <code>{char_id}</code> was not found in the database!")

    char_name = char_data[0]

    cursor.execute("DELETE FROM characters WHERE id = ?", (char_id,))
    cursor.execute("DELETE FROM user_collection WHERE character_id = ?", (char_id,))
    
    conn.commit()
    conn.close()
    await update.message.reply_text(f"🗑️ <b>Character Deleted!</b>\n\n<b>{char_name}</b> (ID: {char_id}) has been removed from the database and user collections.")

# /REMOVEALL
async def removeall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id != OWNER_ID:
        return await update.message.reply_text("❌ Not allowed")

    if not context.args:
        return await update.message.reply_text("Usage: /removeall <user_id>")

    target_id = int(context.args[0])

    # 👤 get user info
    conn = db_connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT username FROM users WHERE user_id=?", (target_id,))
    user = cursor.fetchone()
    conn.close()

    name = f"@{user[0]}" if user and user[0] else "Unknown"

    text = (
        f"⚠️ <b>CONFIRM HAREM DELETE</b>\n\n"
        f"<blockquote>"
        f"👤 <b>User:</b> {name} (<code>{target_id}</code>)\n"
        f"💀 This will delete ALL characters\n"
        f"</blockquote>"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💀 CONFIRM DELETE", callback_data=f"rmall_yes_{target_id}"),
            InlineKeyboardButton("❌ CANCEL", callback_data="rmall_no")
        ]
    ])

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard
    )

async def removeall_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    # ❌ cancel
    if data == "rmall_no":
        return await query.edit_message_text("❌ Action cancelled.")

    # 💀 confirm delete
    if data.startswith("rmall_yes_"):
        target_id = int(data.split("_")[2])

        conn = db_connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM user_collection
            WHERE user_id=?
        """, (target_id,))

        conn.commit()
        conn.close()

        text = (
            f"💀 <b>HAREM DELETED</b>\n\n"
            f"<blockquote>"
            f"👤 User: <code>{target_id}</code>\n"
            f"🗑️ All characters removed successfully\n"
            f"</blockquote>"
        )

        await query.edit_message_text(text, parse_mode="HTML")

# ==========================
# /TRANSFER
# ==========================
async def transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return await update.message.reply_text("❌ Not allowed")

    if len(context.args) != 2:
        return await update.message.reply_text(
            "Usage: /transfer <from_user_id> <to_user_id>"
        )

    try:
        from_id = int(context.args[0])
        to_id = int(context.args[1])
    except ValueError:
        return await update.message.reply_text("❌ Invalid user ID")

    conn = db_connect(DB_NAME)
    cursor = conn.cursor()

    # Get source harem
    cursor.execute("""
        SELECT character_id, count
        FROM user_collection
        WHERE user_id=?
    """, (from_id,))
    
    characters = cursor.fetchall()

    if not characters:
        conn.close()
        return await update.message.reply_text("❌ Source user has no characters")

    # Move all characters
    for char_id, count in characters:
        cursor.execute("""
            INSERT INTO user_collection (user_id, character_id, count)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, character_id)
            DO UPDATE SET count = count + excluded.count
        """, (to_id, char_id, count))

    # Delete source harem
    cursor.execute("""
        DELETE FROM user_collection
        WHERE user_id=?
    """, (from_id,))

    conn.commit()
    conn.close()

    text = (
        f"🔄 <b>Harem transfer completed</b>\n\n"
        f"<blockquote>"
        f"📤 <b>From:</b> <code>{from_id}</code>\n"
        f"📥 <b>To:</b> <code>{to_id}</code>\n"
        f"🎴 <b>Characters Moved:</b> {len(characters)}\n"
        f"</blockquote>"
    )

    await update.message.reply_text(text, parse_mode="HTML")


# ==========================
# /GEN
# ==========================
async def gen_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id != OWNER_ID:
        return await update.message.reply_text("❌ Not allowed")

    if len(context.args) < 2:
        return await update.message.reply_text("Usage: /gen <char_id> <count>")

    try:
        char_id = context.args[0]
        count = int(context.args[1])
    except ValueError:
        return await update.message.reply_text("❌ Count must be a number.")

    code = generate_code()

    conn = db_connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM characters WHERE id=?", (char_id,))
    char = cursor.fetchone()

    if not char:
        conn.close()
        return await update.message.reply_text("❌ Character not found")

    cursor.execute("""
        INSERT INTO redeem_codes (code, character_id, uses, created_by)
        VALUES (?, ?, ?, ?)
    """, (code, char_id, count, user_id))

    conn.commit()
    conn.close()

    text = (
        f"👑 <b>Redeem Code Generated!</b>\n\n"
        f"<blockquote>"
        f"🔑 Code: <code>{code}</code>\n"
        f"🆔 Char ID: <code>{char_id}</code>\n"
        f"📦 Uses: <code>{count}</code>"
        f"</blockquote>"
    )

    # If you have character media
    try:
        image_url = get_character_media(char_id)  # Replace with your own function if needed

        await send_character_media(
            context.bot,
            update.effective_chat.id,
            image_url,
            text
        )
    except Exception:
        await update.message.reply_text(
            text,
            parse_mode="HTML"
        )



async def redeem_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Usage: /redeem <code>")

    user = update.effective_user
    code = context.args[0].upper()

    conn = db_connect(DB_NAME)
    cursor = conn.cursor()

    # 🔑 get code
    cursor.execute("""
        SELECT character_id, uses
        FROM redeem_codes
        WHERE code=?
    """, (code,))

    data = cursor.fetchone()

    if not data:
        conn.close()
        return await update.message.reply_text("❌ Invalid or expired code")

    char_id, uses = data

    if uses <= 0:
        conn.close()
        return await update.message.reply_text("❌ Code already used")

    # 🔻 reduce uses
    cursor.execute("""
        UPDATE redeem_codes
        SET uses = uses - 1
        WHERE code=?
    """, (code,))

    # 🎴 add character
    cursor.execute("""
        INSERT INTO user_collection (user_id, character_id, count)
        VALUES (?, ?, 1)
        ON CONFLICT(user_id, character_id)
        DO UPDATE SET count = count + 1
    """, (user.id, char_id))

    # 🎴 get character info
    cursor.execute("""
        SELECT name, anime, rarity, image_url
        FROM characters
        WHERE id=?
    """, (char_id,))

    char = cursor.fetchone()

    conn.commit()
    conn.close()

    # 🎉 response
    if char:
        name, anime, rarity, image_url = char

        text = (
            f"🎉 <b>Redeem successfull!</b>\n\n"
            f"<blockquote>"
            f"👤 <b>User:</b> {user.mention_html()} (<code>{user.id}</code>)\n"
            f"🎴 <b>Name:</b> {name}\n"
            f"🎌 <b>Anime:</b> {anime}\n"
            f"⭐ <b>Rarity:</b> {rarity}\n"
            f"🆔 <b>ID:</b> {char_id}\n"
            f"</blockquote>"
        )

        try:
            await send_character_media(
                context.bot,
                update.effective_chat.id,
                image_url,
                text
            )
        except:
            await update.message.reply_text(text, parse_mode="HTML")



# ==========================
# /BROADCAST
# ==========================
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return await _deny(update)

    if not context.args and not update.message.reply_to_message:
        return await update.message.reply_text("𝖴𝗌𝖾: /broadcast ﹤text﹥ 𝗈𝗋 𝗋𝖾𝗉𝗅𝗒 𝗍𝗈 𝖺 𝗆𝖾𝗌𝗌𝖺𝗀𝖾")

    if update.message.reply_to_message:
        text = update.message.reply_to_message.text or update.message.reply_to_message.caption
    else:
        text = " ".join(context.args)

    users = fetch_all("SELECT user_id FROM users")
    sent = 0
    failed = 0

    status = await update.message.reply_text(f"📢 𝖡𝗋𝗈𝖺𝖽𝖼𝖺𝗌𝗍𝗂𝗇𝗀 𝗍𝗈 {len(users)} 𝗎𝗌𝖾𝗋𝗌...")

    for (uid,) in users:
        try:
            await context.bot.send_message(chat_id=uid, text=f"📢 <b>𝖠𝖭𝖭𝖮𝖴𝖭𝖢𝖤𝖬𝖤𝖭𝖳</b>\n\n{text}", parse_mode=ParseMode.HTML)
            sent += 1
        except Exception:
            failed += 1

    await status.edit_text(f"✅ 𝖡𝗋𝗈𝖺𝖽𝖼𝖺𝗌𝗍 𝖽𝗈𝗇𝖾!\n📤 𝖲𝖾𝗇𝗍: {sent}\n❌ 𝖥𝖺𝗂𝗅𝖾𝖽: {failed}")


# ==========================
# /SAVEGROUP
# ==========================
async def save_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sudo+ command to manually register a group."""
    if not check_sudo(update):
        return await _deny(update)

    chat = update.effective_chat
    if chat.type == ChatType.PRIVATE:
        return await update.message.reply_text("❌ 𝖴𝗌𝖾 𝗂𝗇 𝖺 𝗀𝗋𝗈𝗎𝗉.")

    ensure_group(chat.id, chat.title)
    await update.message.reply_text(f"✅ 𝖦𝗋𝗈𝗎𝗉 𝗋𝖾𝗀𝗂𝗌𝗍𝖾𝗋𝖾𝖽: {chat.title}")

