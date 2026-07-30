import base64
import os
import aiohttp
from pathlib import Path
import string
import random
import sqlite3
import logging
from datetime import datetime

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


logger = logging.getLogger(__name__)

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
    """Returns True if user is owner or sudo."""
    user_id = update.effective_user.id
    if user_id == OWNER_ID or is_sudo(user_id):
        return True
    return False


async def _deny(update):
    if update.callback_query:
        await update.callback_query.answer("❌ 𝖠𝖽𝗆𝗂𝗇 𝗈𝗇𝗅𝗒", show_alert=True)
    else:
        await update.message.reply_text("❌ 𝖳𝗁𝗂𝗌 𝖼𝗈𝗆𝗆𝖺𝗇𝖽 𝗂𝗌 𝖺𝖽𝗆𝗂𝗇-𝗈𝗇𝗅𝗒.")
    return

def generate_code(length=7):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def is_owner(user_id):
    return user_id == OWNER_ID

def is_sudo(user_id):
    if is_owner(user_id):
        return True

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM sudo_users WHERE user_id = ?", (user_id,))
    exists = cursor.fetchone()
    conn.close()
    return exists is not None


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

    conn = sqlite3.connect(DB_NAME)
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

    conn = sqlite3.connect(DB_NAME)
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
    conn = sqlite3.connect(DB_NAME)
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



# ====== TEMP STORAGE ======
PENDING_UPLOADS = {}
COUNTER = {"n": 0}

def new_upload_id():
    COUNTER["n"] += 1
    return f"u{COUNTER['n']}"


# ==========================
# UPLOAD HOST FUNCTIONS
# ==========================
async def upload_to_catbox(local_path: str) -> str:
    url = "https://catbox.moe/user/api.php"
    async with aiohttp.ClientSession() as session:
        data = aiohttp.FormData()
        data.add_field('reqtype', 'fileupload')
        data.add_field('fileToUpload',
                       open(local_path, 'rb'),
                       filename=Path(local_path).name)
        async with session.post(url, data=data) as resp:
            if resp.status != 200:
                raise Exception(f"HTTP {resp.status}")
            return (await resp.text()).strip()



async def upload_to_imgbb(local_path: str) -> str:
    if not IMGBB_API_KEY:
        raise Exception("IMGBB_API_KEY not set in config.py")

    url = f"https://api.imgbb.com/1/upload?key={IMGBB_API_KEY}"
    async with aiohttp.ClientSession() as session:
        data = aiohttp.FormData()
        with open(local_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode()
        data.add_field('image', encoded)
        async with session.post(url, data=data) as resp:
            result = await resp.json()
            if not result.get("success"):
                raise Exception(str(result))
            return result["data"]["url"]


# ==========================
# /upload COMMAND
# ==========================
async def upload_character(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return await update.message.reply_text("❌ Not allowed")

    reply = update.message.reply_to_message
    if not reply:
        return await update.message.reply_text(
            "❌ <b>Error: Please reply to an image, video, or GIF!</b>\n\n"
            "💡 <b>Usage:</b> Reply to media with:\n"
            "<code>/upload [Char-Name] [Anime-Name] [Rarity_Number]</code>\n"
            "Example: <code>/upload Son-gohan dragon-ball 3</code>",
            parse_mode="HTML"
        )

    # 1. Media handling
    file_id = None
    file_type = None
    if reply.photo:
        file_id = reply.photo[-1].file_id
        file_type = "photo"
    elif reply.video:
        file_id = reply.video.file_id
        file_type = "video"
    elif reply.animation:
        file_id = reply.animation.file_id
        file_type = "animation"
    else:
        return await update.message.reply_text("❌ Unsupported media type! Use Photo, Video, or GIF.")

    # 2. Args check
    if len(context.args) != 3:
        return await update.message.reply_text(
            "❌ <b>Invalid Format!</b>\n\n"
            "💡 <b>Format:</b> <code>/upload [Char-Name] [Anime-Name] [Rarity_Number]</code>\n"
            "Example: <code>/upload Son-gohan dragon-ball 3</code>",
            parse_mode="HTML"
        )

    local_path = None
    conn = None
    
    try:
        char_name = context.args[0].replace("-", " ").title()
        anime_name = context.args[1].replace("-", " ").title()
        rarity_id = int(context.args[2])

        if rarity_id not in RARITY_DISPLAY:
            return await update.message.reply_text("❌ Invalid Rarity ID! Use 1-18.")

        rarity = RARITY_DISPLAY[rarity_id]

        # 3. Generate next ID (gap-filling)
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM characters")
        existing_ids = []
        for row in cursor.fetchall():
            try:
                existing_ids.append(int(row[0]))
            except ValueError:
                continue

        next_number = 1
        while next_number in existing_ids:
            next_number += 1
        char_id = f"{next_number:02d}"

        # 4. Download to ~/summon-bot/uploads/
        import os
        upload_dir = os.path.expanduser("~/summon-bot/uploads")
        os.makedirs(upload_dir, exist_ok=True)
        local_path = os.path.join(upload_dir, f"upload_{char_id}_{file_type}")
        # Remove old file if exists
        if os.path.exists(local_path):
            os.remove(local_path)
        try:
            if file_type == "photo":
                tg_file = await context.bot.get_file(reply.photo[-1].file_id)
            elif file_type == "video":
                tg_file = await context.bot.get_file(reply.video.file_id)
            elif file_type == "animation":
                tg_file = await context.bot.get_file(reply.animation.file_id)
            else:
                return await update.message.reply_text("❌ Unsupported media type!")

            await tg_file.download_to_drive(local_path)
        except Exception as e:
            return await update.message.reply_text(f"❌ Download failed: {e}")

        # 5. Store pending
        upload_id = new_upload_id()
        PENDING_UPLOADS[upload_id] = {
            "file_id": file_id,
            "file_type": file_type,
            "char_id": char_id,
            "char_name": char_name,
            "anime": anime_name,
            "rarity": rarity,
            "local_path": local_path,
        }

        # 6. Forward to DB channel
        uploader = update.effective_user
        uploader_mention = f"<a href='tg://user?id={uploader.id}'>{uploader.first_name}</a>"

        caption_text = (
            f"📝 <b>New Character Added!</b>\n\n"
            f"🆔 <b>ID:</b> <code>{char_id}</code>\n"
            f"<blockquote>🎌 <b>Anime:</b> {anime_name}\n"
            f"👤 <b>Name:</b> {char_name}\n"
            f"✨ <b>Rarity:</b> {rarity}\n"
            f"📂 <b>Type:</b> {file_type.upper()}</blockquote>\n"
            f"👑 <b>Uploaded By:</b> {uploader_mention}"
        )

        if file_type == "photo":
            await context.bot.send_photo(chat_id=DB_CHANNEL_ID, photo=file_id, caption=caption_text, parse_mode="HTML")
        elif file_type == "video":
            await context.bot.send_video(chat_id=DB_CHANNEL_ID, video=file_id, caption=caption_text, parse_mode="HTML")
        elif file_type == "animation":
            await context.bot.send_animation(chat_id=DB_CHANNEL_ID, animation=file_id, caption=caption_text, parse_mode="HTML")

    except Exception as e:
        if conn: conn.close()
        if local_path and Path(local_path).exists():
            Path(local_path).unlink(missing_ok=True)
        return await update.message.reply_text(f"❌ Database/Channel Error: {e}")

    # 7. Save to DB (file_id as backup, no URL yet)
    db_file_value = f"{file_type}_{file_id}"
    cursor.execute(
        """INSERT OR REPLACE INTO characters 
           (id, name, anime, rarity, msg_id, img_url, img_url2) 
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (char_id, char_name, anime_name, rarity, db_file_value, None, None)
    )
    conn.commit()
    conn.close()

    # 8. Show buttons
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📤 Catbox", callback_data=f"up_cb|{upload_id}"),
            InlineKeyboardButton("📤 ImgBB", callback_data=f"up_ib|{upload_id}"),
        ],
        [
            InlineKeyboardButton("⏭ Skip (file_id only)", callback_data=f"up_skip|{upload_id}"),
        ],
    ])

    await update.message.reply_text(
        f"📝 <b>Character Saved (file_id backup)!</b>\n\n"
        f"🆔 <b>ID:</b> <code>{char_id}</code>\n"
        f"👤 <b>Name:</b> {char_name}\n"
        f"📺 <b>Anime:</b> {anime_name}\n"
        f"✨ <b>Rarity:</b> {rarity}\n"
        f"📂 <b>Type:</b> {file_type.upper()}\n"
        f"📁 <b>Backup:</b> file_id ✅\n\n"
        f"<b>Upload to a web host for in-app display?</b>",
        parse_mode="HTML",
        reply_markup=keyboard
    )


# ==========================
# CALLBACK HANDLER
# ==========================
async def upload_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if not data.startswith("up_"):
        return
    
    parts = data.split("|", 1)
    if len(parts) != 2:
        return
    
    action, upload_id = parts
    action = action.replace("up_", "")
    
    pending = PENDING_UPLOADS.get(upload_id)
    if not pending:
        await query.edit_message_text("❌ Session expired. Re-upload with /upload.")
        return
    
    char_id = pending["char_id"]
    file_id = pending["file_id"]
    local_path = pending["local_path"]
    
    # ====== SKIP ======
    if action == "skip":
        await query.edit_message_text(
            f"✅ <b>Done!</b>\n\n"
            f"🆔 <code>{char_id}</code> — {pending['char_name']}\n"
            f"📁 file_id: ✅\n"
            f"🌐 URL: <i>skipped (file_id only)</i>",
            parse_mode="HTML"
        )
        del PENDING_UPLOADS[upload_id]
        if local_path and Path(local_path).exists():
            Path(local_path).unlink(missing_ok=True)
        return
    
    # ====== UPLOAD ======
    host_name = "Catbox" if action == "cb" else "ImgBB"
    await query.edit_message_text(f"⏳ Uploading to <b>{host_name}</b>...", parse_mode="HTML")
    
    img_url = None
    error = None
    
    try:
        if action == "cb":
            img_url = await upload_to_catbox(local_path)
        elif action == "ib":
            img_url = await upload_to_imgbb(local_path)
    except Exception as e:
        error = str(e)
    finally:
        if local_path and Path(local_path).exists():
            Path(local_path).unlink(missing_ok=True)
    
    # ====== FAILED → file_id already saved ======
    if not img_url:
        await query.edit_message_text(
            f"⚠️ <b>{host_name} upload failed</b>\n\n"
            f"🆔 <code>{char_id}</code> — {pending['char_name']}\n"
            f"📁 file_id: ✅ (saved as backup)\n"
            f"❌ Error: <code>{error}</code>\n\n"
            f"<i>Character is still saved with file_id only.</i>",
            parse_mode="HTML"
        )
        del PENDING_UPLOADS[upload_id]
        return
    
    # ====== SUCCESS → save URL to DB ======
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        if action == "cb":
            cursor.execute(
                "UPDATE characters SET img_url = ? WHERE id = ?",
                (img_url, char_id)
            )
        elif action == "ib":
            cursor.execute(
                "UPDATE characters SET img_url2 = ? WHERE id = ?",
                (img_url, char_id)
            )
        
        conn.commit()
        conn.close()
    except Exception as e:
        await query.edit_message_text(
            f"⚠️ <b>Uploaded but DB save failed</b>\n\n"
            f"🆔 <code>{char_id}</code>\n"
            f"🌐 {img_url}\n"
            f"❌ DB Error: <code>{e}</code>",
            parse_mode="HTML"
        )
        del PENDING_UPLOADS[upload_id]
        return
    
    # ====== ALL GOOD ======
    await query.edit_message_text(
        f"✅ <b>Character Saved!</b>\n\n"
        f"🆔 <code>{char_id}</code> — {pending['char_name']}\n"
        f"📁 file_id: ✅\n"
        f"🌐 {host_name}: {img_url}",
        parse_mode="HTML"
    )
    del PENDING_UPLOADS[upload_id]


# ==========================
# /SPAWN
# ==========================
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
    db_file = DB_NAME if 'DB_NAME' in globals() else "summon.db"
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, name, anime, rarity, msg_id 
        FROM characters 
        ORDER BY RANDOM() 
        LIMIT 1
    """)
    char = cursor.fetchone()
    conn.close()

    if not char:
        return await update.message.reply_text("❌ No characters found in the database.")

    char_id, name, anime, rarity, msg_id = char

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
                db_msg_id=msg_id, 
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
    conn = sqlite3.connect(db_file)
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

    conn = sqlite3.connect(DB_NAME)
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
    conn = sqlite3.connect(DB_NAME)
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
def get_random_character():
    """
    1. First, select a weighted rarity based on the configured drop rates.
    2. Try to fetch a random character belonging to that specific rarity from the DB.
    3. Fallback: If no characters exist in that rarity, pick any random character from the entire database.
    """
    # Pick a random rarity name based on the 1-18 system weight
    target_rarity = get_rarity() 
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Try fetching characters belonging to the chosen target rarity
    cursor.execute("SELECT id, name, anime, rarity, msg_id FROM characters WHERE rarity=?", (target_rarity,))
    chars = cursor.fetchall()
    
    if chars:
        conn.close()
        return random.choice(chars) # Return a random character from the target rarity
        
    # FALLBACK: If the chosen rarity has no characters uploaded yet,
    # pick any random character from the entire database to prevent a bot crash.
    cursor.execute("SELECT id, name, anime, rarity, msg_id FROM characters")
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
        conn = sqlite3.connect(DB_NAME)
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
            conn = sqlite3.connect(DB_NAME)
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

    conn = sqlite3.connect(DB_NAME)
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
    
    if not is_sudo(user_id):
        return await update.message.reply_text("❌ You do not have permission to view the Sudo List!")

    conn = sqlite3.connect(DB_NAME)
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

    conn = sqlite3.connect(DB_NAME)
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
        
        conn = sqlite3.connect(DB_NAME)
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

        conn = sqlite3.connect(DB_NAME)
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
    user_id = update.effective_user.id

    # 🎯 Sudo Privilege Check
    if not is_sudo(user_id):
        return await update.message.reply_text("❌ You do not have Sudo privileges!")

    reply = update.message.reply_to_message
    if not reply:
        return await update.message.reply_text(
            "❌ <b>Error: Please reply to an image, video, or GIF!</b>\n\n"
            "💡 <b>Usage:</b> Reply to media with:\n"
            "<code>/add [Char-Name] [Anime-Name] [Rarity_Number]</code>\n"
            "Example: <code>/add Son-gohan dragon-ball 3</code>",
            parse_mode="HTML"
        )

    # 1. Media handling
    file_id = None
    file_type = None
    if reply.photo:
        file_id = reply.photo[-1].file_id
        file_type = "photo"
    elif reply.video:
        file_id = reply.video.file_id
        file_type = "video"
    elif reply.animation:
        file_id = reply.animation.file_id
        file_type = "animation"
    else:
        return await update.message.reply_text("❌ Unsupported media type! Use Photo, Video, or GIF.")

    # 2. Args check
    if len(context.args) != 3:
        return await update.message.reply_text(
            "❌ <b>Invalid Format!</b>\n\n"
            "💡 <b>Format:</b> <code>/add [Char-Name] [Anime-Name] [Rarity_Number]</code>\n"
            "Example: <code>/add Son-gohan dragon-ball 3</code>",
            parse_mode="HTML"
        )

    local_path = None
    conn = None

    try:
        char_name = context.args[0].replace("-", " ").title()
        anime_name = context.args[1].replace("-", " ").title()
        rarity_id = int(context.args[2])

        if rarity_id not in RARITY_DISPLAY:
            return await update.message.reply_text("❌ Invalid Rarity ID! Use 1-18.")

        rarity = RARITY_DISPLAY[rarity_id]

        # 3. Generate next ID (gap-filling)
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM characters")
        existing_ids = []
        for row in cursor.fetchall():
            try:
                existing_ids.append(int(row[0]))
            except ValueError:
                continue

        next_number = 1
        while next_number in existing_ids:
            next_number += 1
        char_id = f"{next_number:02d}"

        # 4. Download to ~/summon-bot/uploads/
        import os
        upload_dir = os.path.expanduser("~/summon-bot/uploads")
        os.makedirs(upload_dir, exist_ok=True)
        local_path = os.path.join(upload_dir, f"upload_{char_id}_{file_type}")
        # Remove old file if exists
        if os.path.exists(local_path):
            os.remove(local_path)
        try:
            if file_type == "photo":
                tg_file = await context.bot.get_file(reply.photo[-1].file_id)
            elif file_type == "video":
                tg_file = await context.bot.get_file(reply.video.file_id)
            elif file_type == "animation":
                tg_file = await context.bot.get_file(reply.animation.file_id)
            else:
                return await update.message.reply_text("❌ Unsupported media type!")

            await tg_file.download_to_drive(local_path)
        except Exception as e:
            return await update.message.reply_text(f"❌ Download failed: {e}")

        # 5. Store pending
        upload_id = new_upload_id()
        PENDING_UPLOADS[upload_id] = {
            "file_id": file_id,
            "file_type": file_type,
            "char_id": char_id,
            "char_name": char_name,
            "anime": anime_name,
            "rarity": rarity,
            "local_path": local_path,
        }

        # 6. Forward to DB channel
        uploader = update.effective_user
        uploader_mention = f"<a href='tg://user?id={uploader.id}'>{uploader.first_name}</a>"

        caption_text = (
            f"📝 <b>New Character Added!</b>\n\n"
            f"🆔 <b>ID:</b> <code>{char_id}</code>\n"
            f"<blockquote>🎌 <b>Anime:</b> {anime_name}\n"
            f"👤 <b>Name:</b> {char_name}\n"
            f"✨ <b>Rarity:</b> {rarity}\n"
            f"📂 <b>Type:</b> {file_type.upper()}</blockquote>\n"
            f"👑 <b>Uploaded By:</b> {uploader_mention}"
        )

        if file_type == "photo":
            await context.bot.send_photo(chat_id=DB_CHANNEL_ID, photo=file_id, caption=caption_text, parse_mode="HTML")
        elif file_type == "video":
            await context.bot.send_video(chat_id=DB_CHANNEL_ID, video=file_id, caption=caption_text, parse_mode="HTML")
        elif file_type == "animation":
            await context.bot.send_animation(chat_id=DB_CHANNEL_ID, animation=file_id, caption=caption_text, parse_mode="HTML")

    except Exception as e:
        if conn: conn.close()
        if local_path and Path(local_path).exists():
            Path(local_path).unlink(missing_ok=True)
        return await update.message.reply_text(f"❌ Database/Channel Error: {e}")

    # 7. Save to DB (file_id as backup, no URL yet)
    db_file_value = f"{file_type}_{file_id}"
    cursor.execute(
        """INSERT OR REPLACE INTO characters
           (id, name, anime, rarity, msg_id, img_url, img_url2)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (char_id, char_name, anime_name, rarity, db_file_value, None, None)
    )
    conn.commit()
    conn.close()

    # 8. Show buttons
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📤 Catbox", callback_data=f"up_cb|{upload_id}"),
            InlineKeyboardButton("📤 ImgBB", callback_data=f"up_ib|{upload_id}"),
        ],
        [
            InlineKeyboardButton("⏭ Skip (file_id only)", callback_data=f"up_skip|{upload_id}"),
        ],
    ])

    await update.message.reply_text(
        f"📝 <b>Character Saved (file_id backup)!</b>\n\n"
        f"🆔 <b>ID:</b> <code>{char_id}</code>\n"
        f"👤 <b>Name:</b> {char_name}\n"
        f"📺 <b>Anime:</b> {anime_name}\n"
        f"✨ <b>Rarity:</b> {rarity}\n"
        f"📂 <b>Type:</b> {file_type.upper()}\n"
        f"📁 <b>Backup:</b> file_id ✅\n\n"
        f"<b>Upload to a web host for in-app display?</b>",
        parse_mode="HTML",
        reply_markup=keyboard
    )

# ==========================================
# 🔄 UPDATED: /update COMMAND WITH WEB HOSTS
# ==========================================
async def update_character(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # 🎯 Sudo Privilege Check
    if not is_sudo(user_id):
        return await update.message.reply_text("❌ You do not have Sudo privileges!")

    # ഒട്ടും ആർഗ്യുമെന്റ്സ് ഇല്ലെങ്കിൽ ഹെൽപ്പ് മെസ്സേജ് കാണിക്കുന്നു
    if len(context.args) < 1:
        return await update.message.reply_text(
            "❌ <b>Invalid Format!</b>\n\n"
            "💡 <b>Usage Examples:</b>\n"
            "• <code>/update 678 name Raiden-shogun</code>\n"
            "• <code>/update 478 rarity 18</code>\n"
            "• <code>/update 748 anime Genshin-Impact</code>\n"
            "• <code>/update 587 image</code> (Reply to an image/video/gif)",
            parse_mode="HTML"
        )

    # ആട്ടോമാറ്റിക്കായി ഐഡി പാഡ് ചെയ്യുന്നു (e.g., '1' becomes '01')
    char_id = context.args[0].zfill(2)
    field_to_update = context.args[1].lower() if len(context.args) > 1 else "image"

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # ഡാറ്റാബേസിൽ ഈ ക്യാരക്ടർ ഉണ്ടോ എന്ന് നോക്കുന്നു
    cursor.execute("SELECT name, anime, rarity, msg_id FROM characters WHERE id = ?", (char_id,))
    existing_char = cursor.fetchone()

    if not existing_char:
        conn.close()
        return await update.message.reply_text(f"❌ <b>Character with ID {char_id} not found!</b>", parse_mode="HTML")

    current_name, current_anime, current_rarity, current_msg_id = existing_char

    updated_value = ""
    db_field = ""
    local_path = None

    # 1️⃣ IMAGE/MEDIA UPDATE HANDLING (നിന്റെ അപ്‌ലോഡ് സിസ്റ്റവുമായി കണക്ട് ചെയ്തത്)
    if field_to_update in ["image", "media"]:
        reply = update.message.reply_to_message
        if not reply:
            conn.close()
            return await update.message.reply_text("❌ <b>Error: Please reply to an image, video, or GIF to update!</b>", parse_mode="HTML")

        file_id, file_type = None, None
        if reply.photo:
            file_id = reply.photo[-1].file_id
            file_type = "photo"
        elif reply.video:
            file_id = reply.video.file_id
            file_type = "video"
        elif reply.animation:
            file_id = reply.animation.file_id
            file_type = "animation"
        else:
            conn.close()
            return await update.message.reply_text("❌ Unsupported media type! Please use Photo, Video, or GIF.")

        current_msg_id = f"{file_type}_{file_id}"
        db_field = "msg_id"
        updated_value = f"New {file_type.upper()} linked!"

        # ഫയൽ ലോക്കലായി ~/summon-bot/uploads/-ലേക്ക് ഡൗൺലോഡ് ചെയ്യുന്നു
        upload_dir = os.path.expanduser("~/summon-bot/uploads")
        os.makedirs(upload_dir, exist_ok=True)
        local_path = os.path.join(upload_dir, f"upload_{char_id}_{file_type}")
        
        if os.path.exists(local_path):
            os.remove(local_path)
            
        try:
            tg_file = await context.bot.get_file(file_id)
            await tg_file.download_to_drive(local_path)
        except Exception as e:
            conn.close()
            return await update.message.reply_text(f"❌ Download failed: {e}")

        # അപ്‌ലോഡ് കോൾബാക്കിന് വേണ്ടി PENDING_UPLOADS-ലേക്ക് വിവരങ്ങൾ മാറ്റുന്നു
        upload_id = new_upload_id()
        PENDING_UPLOADS[upload_id] = {
            "file_id": file_id,
            "file_type": file_type,
            "char_id": char_id,
            "char_name": current_name,
            "anime": current_anime,
            "rarity": current_rarity,
            "local_path": local_path,
        }

    # 2️⃣ NAME UPDATE HANDLING
    elif field_to_update == "name":
        if len(context.args) < 3:
            conn.close()
            return await update.message.reply_text("❌ Please provide the new name! Example: <code>/update 678 name Son-goku</code>", parse_mode="HTML")
        new_name = " ".join(context.args[2:]).replace("-", " ").title()
        current_name = new_name
        db_field = "name"
        updated_value = new_name

    # 3️⃣ ANIME UPDATE HANDLING
    elif field_to_update == "anime":
        if len(context.args) < 3:
            conn.close()
            return await update.message.reply_text("❌ Please provide the new anime name! Example: <code>/update 748 anime Dragon-Ball</code>", parse_mode="HTML")
        new_anime = " ".join(context.args[2:]).replace("-", " ").title()
        current_anime = new_anime
        db_field = "anime"
        updated_value = new_anime

    # 4️⃣ RARITY UPDATE HANDLING
    elif field_to_update == "rarity":
        if len(context.args) < 3:
            conn.close()
            return await update.message.reply_text("❌ Please provide the new rarity ID! Example: <code>/update 478 rarity 18</code>", parse_mode="HTML")
        try:
            rarity_id = int(context.args[2])
            if rarity_id not in RARITY_DISPLAY:
                conn.close()
                return await update.message.reply_text("❌ Invalid Rarity ID! Use a number from 1 to 18.")
            new_rarity = RARITY_DISPLAY[rarity_id]
            current_rarity = new_rarity
            db_field = "rarity"
            updated_value = new_rarity
        except ValueError:
            conn.close()
            return await update.message.reply_text("❌ Rarity must be a valid number!")
    else:
        conn.close()
        return await update.message.reply_text("❌ Invalid field! You can only update <code>name</code>, <code>anime</code>, <code>rarity</code>, or <code>image</code>.", parse_mode="HTML")

    # ഡാറ്റാബേസ് അപ്‌ഡേറ്റ് ചെയ്യുന്നു (ഇമേജ് ആണെങ്കിൽ img_url ലിങ്കുകൾ തൽക്കാലം ക്ലിയർ ചെയ്യുന്നു, പുതിയ അപ്‌ലോഡ് വരുന്നത് കൊണ്ട്)
    if db_field == "msg_id":
        cursor.execute(
            "UPDATE characters SET msg_id = ?, img_url = NULL, img_url2 = NULL WHERE id = ?",
            (current_msg_id, char_id)
        )
    else:
        cursor.execute(f"UPDATE characters SET {db_field} = ? WHERE id = ?", (updated_value, char_id))
        
    conn.commit()
    conn.close()

    # ഡാറ്റാബേസ് ചാനലിലേക്ക് പുതിയ ലോഗ് മെസ്സേജ് അയക്കുന്നു
    file_type = "photo"
    file_id = current_msg_id
    if "_" in str(current_msg_id):
        file_type, file_id = str(current_msg_id).split("_", 1)

    uploader_mention = f"<a href='tg://user?id={update.effective_user.id}'>{update.effective_user.first_name}</a>"
    caption_text = (
        f"🔄 <b>Character Updated!</b>\n\n"
        f"🆔 <b>ID:</b> <code>{char_id}</code>\n"
        f"<blockquote>🎌 <b>Anime:</b> {current_anime}\n"
        f"👤 <b>Name:</b> {current_name}\n"
        f"✨ <b>Rarity:</b> {current_rarity}\n"
        f"📢 <b>Updated Field:</b> {field_to_update.upper()}</blockquote>\n"
        f"👑 <b>Updated By:</b> {uploader_mention}"
    )

    try:
        if file_type == "photo":
            await context.bot.send_photo(chat_id=DB_CHANNEL_ID, photo=file_id, caption=caption_text, parse_mode="HTML")
        elif file_type == "video":
            await context.bot.send_video(chat_id=DB_CHANNEL_ID, video=file_id, caption=caption_text, parse_mode="HTML")
        elif file_type == "animation":
            await context.bot.send_animation(chat_id=DB_CHANNEL_ID, animation=file_id, caption=caption_text, parse_mode="HTML")
    except Exception as e:
        print(f"Error sending update to log channel: {e}")

    # ഇമേജ് അപ്‌ഡേറ്റ് ആണെങ്കിൽ വെബ് ഹോസ്റ്റ് ബട്ടണുകൾ കാണിക്കും (നിന്റെ അപ്‌ലോഡ് കോൾബാക്ക് ഇത് തനിയെ ഹാൻഡിൽ ചെയ്യും)
    if db_field == "msg_id":
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📤 Catbox", callback_data=f"up_cb|{upload_id}"),
                InlineKeyboardButton("📤 ImgBB", callback_data=f"up_ib|{upload_id}"),
            ],
            [
                InlineKeyboardButton("⏭ Skip (file_id only)", callback_data=f"up_skip|{upload_id}"),
            ],
        ])
        return await update.message.reply_text(
            f"🔄 <b>Character Saved (file_id backup)!</b>\n\n"
            f"🆔 <b>ID:</b> <code>{char_id}</code>\n"
            f"👤 <b>Name:</b> {current_name}\n"
            f"📂 <b>Type:</b> {file_type.upper()}\n"
            f"📁 <b>Backup:</b> file_id ✅\n\n"
            f"<b>Upload this new media to a web host?</b>",
            parse_mode="HTML",
            reply_markup=keyboard
        )

    # ടെക്സ്റ്റ് ഫീൽഡ് അപ്‌ഡേറ്റ് മെസ്സേജ്
    await update.message.reply_text(
        f"✅ <b>Character Updated Successfully!</b>\n\n"
        f"🆔 <b>ID:</b> <code>{char_id}</code>\n"
        f"⚙️ <b>Changed:</b> {field_to_update.title()} -> <code>{updated_value}</code>",
        parse_mode="HTML"
    )

# 3️⃣ DELETE CHARACTER (/deletechar)
async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_sudo(user_id):
        return await update.message.reply_text("❌ You do not have Sudo privileges!")

    if not context.args:
        return await update.message.reply_text("💡 Usage: <code>/deletechar <ID></code>", parse_mode="HTML")

    char_id = context.args[0]

    conn = sqlite3.connect(DB_NAME)
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
    conn = sqlite3.connect(DB_NAME)
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

        conn = sqlite3.connect(DB_NAME)
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

    conn = sqlite3.connect(DB_NAME)
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

    conn = sqlite3.connect(DB_NAME)
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
        msg_id = get_character_media(char_id)  # Replace with your own function if needed

        await send_character_media(
            context.bot,
            update.effective_chat.id,
            msg_id,
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

    conn = sqlite3.connect(DB_NAME)
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
        SELECT name, anime, rarity, msg_id
        FROM characters
        WHERE id=?
    """, (char_id,))

    char = cursor.fetchone()

    conn.commit()
    conn.close()

    # 🎉 response
    if char:
        name, anime, rarity, msg_id = char

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
                msg_id,
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



