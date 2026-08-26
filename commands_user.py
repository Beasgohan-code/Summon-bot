from storage import connect as db_connect
import sqlite3
import asyncio
import logging
import random
import time
from datetime import datetime, timedelta
from collections import defaultdict

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode, ChatType
from telegram.ext import ContextTypes

from config import (
    BOT_USERNAME, DB_NAME, OWNER_USERNAME, OWNER_ID,
    SUPPORT_CHAT, UPDATE_CHANNEL, START_MEDIA,
    STARTING_BALANCE, DAILY_REWARD,
    SPIN_MIN_REWARD, SPIN_MAX_REWARD,
    SPIN_BONUS_MIN, SPIN_BONUS_MAX, RARITY_EMOJI,
    SPIN_LUCKY_CHANCE, SPIN_COOLDOWN_HOURS,
    HCLAIM_COOLDOWN_HOURS, PRICE, HIGH_TIER,
    REFRESH_ALLOWED, REFRESH_PRICE, DEFAULT_FONT, SHOP_IMAGE, TOP_IMAGE
)
from database import (
    init_db, execute, fetch_one, fetch_all, fetch_value,
    check_and_register_user, is_banned, ban_user, unban_user,
    ensure_user, get_balance, add_balance, remove_balance,
    is_sudo, add_sudo_user, remove_sudo_user,
    owns_character, add_to_collection, remove_from_collection,
    get_user_collection, get_user_unique_count,
    get_character, get_random_character, get_character_count,
    get_user, get_top_anime, get_total_groups,
    get_total_users, get_total_coins, get_popular_character,
    get_top_by_money, get_top_by_collection,
    get_streak, update_streak,
    has_achievement, unlock_achievement,
    get_market_pool, clear_market_pool, add_to_market_pool,
    remove_from_market_pool, log_market_transaction,
    get_user_pref, set_collection_mode, toggle_profile_glow,
    set_font_pref,
    ACHIEVEMENTS, STREAK_BONUS_TIERS, STREAK_RESET_DAYS,
    MARKET_POOL_SIZE, MARKET_REFRESH_PRICE, MARKET_SELL_BACK_PERCENT,
)
from font import stylize_block, FONT_MAPS
from media_urls import is_allowed_character_image_url

logger = logging.getLogger(__name__)


# ==========================
# FONT ENGINE
# ==========================
def _get_user_font(user_id: int) -> str:
    row = fetch_one("SELECT font_pref FROM users WHERE user_id = ?", (user_id,))
    if row and row[0] and row[0] in FONT_MAPS:
        return row[0]
    return DEFAULT_FONT


def f(text: str, user_id: int = None) -> str:
    font = _get_user_font(user_id) if user_id else DEFAULT_FONT
    return stylize_block(text, font)


async def send_character_media(bot, chat_id, image_url, caption, reply_markup=None):
    """Send an approved external character image or a text fallback.

    Character media is intentionally URL-only. Telegram file IDs, typed media
    prefixes, and arbitrary hosts are never sent from this path.
    """
    if not is_allowed_character_image_url(image_url):
        return await bot.send_message(
            chat_id=chat_id,
            text=caption,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
    try:
        return await bot.send_photo(
            chat_id=chat_id,
            photo=image_url,
            caption=caption,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.warning("send_character_media failed for approved image URL: %s", exc)
        return await bot.send_message(
            chat_id=chat_id,
            text=caption,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )

       
# BAN CHECK
# ==========================
async def check_ban(update: Update) -> bool:
    user_id = update.effective_user.id
    conn = db_connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("SELECT banned FROM users WHERE user_id=?", (user_id,))
    user_row = cursor.fetchone()
    

    cursor.execute("SELECT 1 FROM banned_users WHERE user_id=?", (user_id,))
    spam_row = cursor.fetchone()
    
    conn.close()
    

    if (user_row and user_row[0] == 1) or spam_row:
        if update.message: 
            await update.message.reply_text(
                "🚫 <b>ACCESS DENIED</b> 🚫\n\n"
                "<blockquote>⚠️ You are banned from using this bot!\n"
                "💬 Contact the Owner if you think this is a mistake.</blockquote>",
                parse_mode="HTML"
            )
        return True

    return False


# ==========================
# UPTIME
# ==========================
START_TIME = time.time()


def get_uptime():
    uptime = int(time.time() - START_TIME)
    h, rem = divmod(uptime, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m}m {s}s"


# ==========================
# LOADING
# ==========================
async def loading_animation(message):
    try:
        msg = await message.reply_text("⏳ Loading...")
        await asyncio.sleep(0.3)
        await msg.edit_text("⚡ Connecting...")
        await asyncio.sleep(0.3)
        await msg.edit_text("🚀 Ready!")
        await asyncio.sleep(0.3)
        await msg.delete()
    except Exception:
        pass


# ==========================================
# /START & HOME TEXT BUILDER (Spam ഒഴിവാക്കാൻ)
# ==========================================
def get_start_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # Ping
    try:
        
        msg_date = update.message.date if update.message else update.callback_query.message.date
        ping = round((time.time() - msg_date.timestamp()) * 1000)
    except Exception:
        ping = 0
        
    uptime = get_uptime() if 'get_uptime' in globals() else "Active"

    caption = (
        "🍃 <b>𝖶𝖤𝖫𝖢𝖮𝖬𝖤 𝖳𝖮 𝖲𝖴𝖬𝖬𝖮𝖭  𝖶𝖮𝖱𝖫𝖣</b> 🫧\n\n"
        f"👋 𝖧𝖾𝗅𝗅𝗈 {user.mention_html()}\n\n"
        "<blockquote>"
        "🔮 𝖲𝗍𝖾𝗉 𝗂𝗇𝗍𝗈 𝗍𝗁𝖾 𝗎𝗅𝗍𝗂𝗆𝖺𝗍𝖾 𝖺𝗇𝗂𝗆𝖾 𝗎𝗇𝗂𝗏𝖾𝗋𝗌𝖾.\n"
        "𝖢𝗈𝗅𝗅𝖾𝖼𝗍, 𝖲𝗎𝗆𝗆𝗈𝗇 𝖺𝗇𝖽 𝖳𝗋𝖺𝖽𝖾 𝗒𝗈𝗎𝗋 𝖿𝖺𝗏𝗈𝗋𝗂𝗍𝖾 𝖺𝗇𝗂𝗆𝖾 𝖼ʜ𝖺𝗋𝖺𝖼𝗍𝖾𝗋𝗌.\n\n"
        "𝖡𝗎𝗂𝗅𝖽 𝗒𝗈𝗎𝗋 𝖽𝗋𝖾𝖺𝗆 𝖼𝗈𝗅𝗅𝖾𝖼𝗍𝗂𝗈𝗇 𝖺𝗇𝖽 𝖻𝖾𝖼𝗈𝗆𝖾 𝗍𝗁𝖾 𝗌𝗍𝗋𝗈𝗇𝗀𝖾𝗌𝗍 𝖲𝗎𝗆𝗆𝗈𝗇𝖾𝗋!"
        "</blockquote>\n\n"
        f"⚡ <b>𝖯𝗂𝗇𝗀 :</b> <code>{ping} ms</code>\n"
        f"⏳ <b>𝖴𝗉𝗍𝗂𝗆𝖾 :</b> <code>{uptime}</code>\n"
        "💰 <b>𝖲𝗍𝖺𝗋𝗍𝖾𝗋 𝖡𝗈𝗇𝗎𝗌 :</b> <code>+500 𝖢𝗈𝗂𝗇𝗌</code>\n\n"
        "<i>𝖴𝗌𝖾 𝗍𝗁𝖾 𝖻𝗎𝗍𝗍𝗈𝗇𝗌 𝖻𝖾𝗅𝗈𝗐 𝗍𝗈 𝗀𝖾𝗍 𝗌𝗍𝖺𝗋𝗍𝖾𝖽.</i>"
    )

    # BOT_USERNAME, SUPPORT_CHAT, UPDATE_CHANNEL, OWNER_USERNAME എന്നിവ നിങ്ങളുടെ ഗ്ലോബൽ വേരിയബിളുകൾ ആയിരിക്കണം
    b_user = BOT_USERNAME if 'BOT_USERNAME' in globals() else "bot"
    s_chat = SUPPORT_CHAT if 'SUPPORT_CHAT' in globals() else "https://t.me"
    u_chan = UPDATE_CHANNEL if 'UPDATE_CHANNEL' in globals() else "https://t.me"
    o_user = OWNER_USERNAME if 'OWNER_USERNAME' in globals() else "admin"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Me", url=f"https://t.me/{BOT_USERNAME}?startgroup=true")],
        [InlineKeyboardButton("💬 Support", url=SUPPORT_CHAT), InlineKeyboardButton("📢 Channel", url=UPDATE_CHANNEL)],
        [InlineKeyboardButton("❓ Help", callback_data="open_help")],
        [InlineKeyboardButton("👑 Owner", url=f"https://t.me/{OWNER_USERNAME}")],
    ])
    
    return caption, keyboard


# ==========================
# /START COMMAND
# ==========================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'check_ban' in globals() and await check_ban(update):
        return
        
    user = update.effective_user
    if 'check_and_register_user' in globals():
        check_and_register_user(user.id, user.username, user.first_name)
        
    if 'loading_animation' in globals():
        await loading_animation(update.message)

    
    if update.effective_chat.type != ChatType.PRIVATE:
        b_user = BOT_USERNAME if 'BOT_USERNAME' in globals() else "bot"
        s_chat = SUPPORT_CHAT if 'SUPPORT_CHAT' in globals() else "https://t.me"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add Me", url=f"https://t.me/{b_user}?startgroup=true"),
             InlineKeyboardButton("💬 Support", url=s_chat)],
        ])
        if 'send' in globals():
            return await update.message.reply_text(f"✨ Thanks for adding me!", user_id=user.id, reply_markup=keyboard)
        else:
            return await update.message.reply_text("✨ Thanks for adding me!", reply_markup=keyboard)

    caption, keyboard = get_start_content(update, context)


    s_media = START_MEDIA if 'START_MEDIA' in globals() else []
    media = random.choice(s_media) if s_media else None
    
    if media:
        try:
            if media.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                return await update.message.reply_photo(photo=media, caption=caption, parse_mode=ParseMode.HTML, reply_markup=keyboard)
            elif media.lower().endswith(".gif"):
                return await update.message.reply_animation(animation=media, caption=caption, parse_mode=ParseMode.HTML, reply_markup=keyboard)
            else:
                return await update.message.reply_video(video=media, caption=caption, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        except Exception:
            pass
            
    await update.message.reply_text(text=caption, parse_mode=ParseMode.HTML, reply_markup=keyboard)


# ==========================================
# 1. HELP DATA CONFIGURATION 
# ==========================================
HELP_DATA = {
    "summon": {
        "HELP_NAME": "⌁ ꜱᴜᴍᴍᴏɴ ⚡",
        "HELP": "<b>⚡ SUMMON COMMANDS</b>\n\n"
                "<blockquote>"
                "⚡ <b>/summon</b> — Summon a random character\n"
                "🎰 <b>/spin</b> — Spin the reward wheel\n"
                "🎯 <b>/hclaim</b> — Claim characters"
                "</blockquote>"
    },
    "collection": {
        "HELP_NAME": "⌁ ᴄᴏʟʟᴇᴄᴛɪᴏɴ 📚",
        "HELP": "<b>📚 COLLECTION COMMANDS</b>\n\n"
                "<blockquote>"
                "🴴 <b>/collection</b> or <b>/harem</b> — View and manage your collection\n\n"
                "⭐ <b>/fav &lt;id&gt;</b> — Set your harem cover character\n\n"
                "🎁 <b>/gift &lt;id&gt;</b> — Gift a character to another user"
                "</blockquote>"
    },
    "search": {
        "HELP_NAME": "⌁ ꜱᴇᴀʀᴄʜ 🔍",
        "HELP": "<b>🔍 SEARCH COMMANDS</b>\n\n"
                "<blockquote>"
                "🔍 <b>/search &lt;name&gt;</b> — Find characters by name\n\n"
                "🔎 <b>/check &lt;id&gt;</b> — Inspect character profile details"
                "</blockquote>"
    },
    "balance": {
        "HELP_NAME": "⌁ ʙᴀʟᴀɴᴄᴇ / ᴘᴀʏ 💰",
        "HELP": "<b>💰 ECONOMY COMMANDS</b>\n\n"
                "<blockquote>"
                "💰 <b>/bal</b> or <b>/balance</b> — Check your coin balance\n\n"
                "📆 <b>/daily</b> — Claim your daily reward coins\n\n"
                "💸 <b>/pay &lt;amount&gt;</b> — Transfer coins to another user"
                "</blockquote>"
    },
    "shop": {
        "HELP_NAME": "⌁ ꜱʜᴏᴘ 🛒",
        "HELP": "<b>🛒 SHOP & MARKET COMMANDS</b>\n\n"
                "<blockquote>"
                "🛒 <b>/shop</b> — Browse and purchase official characters\n\n"
                "🏪 <b>/market</b> — Open player marketplace\n\n"
                "💰 <b>/sell &lt;id&gt;</b> — Sell your character to the market"
                "</blockquote>"
    },
    "top": {
        "HELP_NAME": "⌁ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ 🏆",
        "HELP": "<b>🏆 LEADERBOARD COMMANDS</b>\n\n"
                "<blockquote>"
                "🏆 <b>/top</b> — View top collectors and rankings\n\n"
                "🎖️ <b>/rank</b> — Check your global rank"
                "</blockquote>"
    },
    "features": {
        "HELP_NAME": "⌁ ꜰᴇᴀᴛᴜʀᴇꜱ 🆕",
        "HELP": "<b>🆕 ADDITIONAL FEATURES</b>\n\n"
                "<blockquote>"
                "🔥 <b>/streak</b> — Check daily login streak\n"
                "🏅 <b>/achievements</b> — View unlocked medals\n"
                "📊 <b>/stats</b> — View bot or user data\n"
                "👤 <b>/profile</b> — View user profile card\n"
                "🎛️ <b>/hmode</b> — Change harem display mode\n"
                "🎨 <b>/font</b> — Change custom text fonts"
                "</blockquote>"
    }, 
    "admin": {
        "HELP_NAME": "⌁ ᴀᴅᴍɪɴ ⚠️",
        "HELP": "<b>⚠️ ADMIN COMMANDS</b>\n\n"
                "<blockquote>"
                "🚫 <b>/ban</b> — Ban a user from the bot\n"
                "✅ <b>/unban</b> — Unban a restricted user\n"
                "⚠️ <b>/warn</b> — Issue a warning to a user\n"
                "❌ <b>/remove</b> — Remove a specific character"
                "</blockquote>"
    }
}

# ==========================================
# 2. KEYBOARD BUILDER
# ==========================================
def build_help_keyboard():
    rows = []
    current = []

    for key, value in HELP_DATA.items():
        current.append(InlineKeyboardButton(value["HELP_NAME"], callback_data=f"help_{key}"))
        if len(current) == 2:
            rows.append(current)
            current = []

    if current:
        rows.append(current)

    rows.insert(0, [InlineKeyboardButton("🏡 ʙᴀᴄᴋ ᴛᴏ ʜᴏᴍᴇ", callback_data="help_home")])
    return InlineKeyboardMarkup(rows)

# ==========================================
# 3. COMMAND HANDLERS
# ==========================================
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'check_ban' in globals() and await check_ban(update):
        return

    text = (
        "<b>📖 HELP MENU</b>\n\n"
        "<blockquote>"
        "🎴 Choose a category below\n\n"
        "📌 All commands start with <code>/</code>"
        "</blockquote>"
    )

    try:
        await sen(update, text, user_id=update.effective_user.id, reply_markup=build_help_keyboard())
    except NameError:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=build_help_keyboard())

# ==========================================
# CALLBACK HANDLER
# ==========================================
async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    
    if data in ("open_help_home", "help_home"):
        caption, keyboard = get_start_content(update, context)
        try:

            await query.message.edit_caption(caption=caption, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        except Exception:
            try:

                await query.message.edit_text(text=caption, parse_mode=ParseMode.HTML, reply_markup=keyboard)
            except Exception:
                pass
        return


    if data == "open_help":
        text = (
            "<b>📖 HELP MENU</b>\n\n"
            "<blockquote>"
            "🎴 Choose a category below\n\n"
            "📌 All commands start with <code>/</code>"
            "</blockquote>"
        )
        try:
            await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=build_help_keyboard())
        except Exception:
            try:
                await query.message.edit_text(text=text, parse_mode=ParseMode.HTML, reply_markup=build_help_keyboard())
            except Exception:
                pass
        return

    if not data.startswith("help_"):
        return

    module = data.replace("help_", "")
    module_data = HELP_DATA.get(module)

    if not module_data:
        return await query.answer("Category not found.", show_alert=True)


    back_markup = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ ʙᴀᴄᴋ ᴛᴏ ᴍᴇɴᴜ", callback_data="open_help")]])

    try:
        
        await query.message.edit_caption(caption=module_data["HELP"], parse_mode=ParseMode.HTML, reply_markup=back_markup)
    except Exception:
        try:
            await query.message.edit_text(text=module_data["HELP"], parse_mode=ParseMode.HTML, reply_markup=back_markup)
        except Exception:
            pass

# ==========================
# /BALANCE
# ==========================
async def view_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if 'check_ban' in globals() and await check_ban(update):
        return
    
    user = update.effective_user
    

    if 'check_and_register_user' in globals():
        check_and_register_user(user.id, user.username, user.first_name)
    

    db_file = DB_NAME
    
    conn = db_connect(db_file)
    cursor = conn.cursor()
    
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (user.id,))
    row = cursor.fetchone()
    balance = row[0] if row else 0
    

    try:
   
        cursor.execute("SELECT COUNT(DISTINCT character_id) FROM user_collection WHERE user_id=?", (user.id,))
        coll_row = cursor.fetchone()
        collection_count = coll_row[0] if coll_row else 0
    except sqlite3.OperationalError:

        collection_count = 0
        
    conn.close()
    

    text = (
        f"<blockquote>👤 <b>Summoner:</b> {user.mention_html()}\n\n"
        f"💰 <b>Balance:</b> <code>{balance}</code> Coins\n"
        f"📚 <b>Collection:</b> <code>{collection_count}</code> Characters</blockquote>"
    )
    
    # 5. മറുപടി അയക്കുന്നു
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)
# ==========================
# /PING
# ==========================
async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update):
        return

    started = time.perf_counter()
    message = await update.message.reply_text("🏓 Checking connection...")
    latency_ms = round((time.perf_counter() - started) * 1000)
    await message.edit_text(
        f"🏓 <b>Pong!</b>\n\n"
        f"⚡ Telegram round-trip: <code>{latency_ms} ms</code>\n"
        f"⏳ Uptime: <code>{get_uptime()}</code>",
        parse_mode=ParseMode.HTML,
    )


# ==========================
# /DAILY
# ==========================
async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. ബാൻ ചെക്ക് ചെയ്യുന്നു
    if 'check_ban' in globals() and await check_ban(update):
        return

    user = update.effective_user
    user_id = user.id

    # 2. യൂസർ രജിസ്ട്രേഷൻ (നിങ്ങളുടെ ഫംഗ്ഷനിലെ ആർഗ്യുമെന്റ്സ് അനുസരിച്ച്)
    if 'check_and_register_user' in globals():
        try:
            check_and_register_user(user_id, user.username, user.first_name)
        except TypeError:
            check_and_register_user(user_id, user.username)

    # DB_NAME ഗ്ലോബൽ വേരിയബിൾ ആണെന്ന് ഉറപ്പുവരുത്തുക
    db_file = DB_NAME

    conn = db_connect(db_file)
    cursor = conn.cursor()

    # 3. last_daily കോളം ഉണ്ടെന്ന് ഉറപ്പുവരുത്തുന്നു (നിങ്ങളുടെ പ്രിയപ്പെട്ട ഓട്ടോമാറ്റിക് ആൾട്ടർ ഫീച്ചർ)
    cursor.execute("PRAGMA table_info(users)")
    columns = [c[1] for c in cursor.fetchall()]
    if "last_daily" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN last_daily TEXT")
        conn.commit()

    # 4. അവസാനം ക്ലെയിം ചെയ്ത സമയം എടുക്കുന്നു
    cursor.execute("SELECT last_daily FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()

    now = datetime.now()

    # 🎰 റാൻഡം റിവാർഡ് (100 മുതൽ 300 കോയിൻസ് വരെ)
    reward = random.randint(100, 300)

    # ⏳ 24 മണിക്കൂർ കൂൾഡൗൺ ചെക്ക്
    if row and row[0]:
        try:
            last_time = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
        except Exception:
            last_time = None

        if last_time and now < last_time + timedelta(hours=24):
            time_left = (last_time + timedelta(hours=24)) - now
            hours, remainder = divmod(int(time_left.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)

            conn.close()

            # കൂൾഡൗൺ മെസ്സേജ്
            cooldown_text = (
                f"⏳ <b>Cooldown Active!</b>\n\n"
                f"<blockquote>⚠️ You already claimed daily reward!\n"
                f"🕒 Come back after: <b>{hours}h {minutes}m</b></blockquote>"
            )
            return await update.message.reply_text(cooldown_text, parse_mode=ParseMode.HTML)

    # 🧲 COIN MAGNET CHECK & BONUS
    has_magnet = cursor.execute("""
        SELECT id, uses_remaining FROM user_inventory 
        WHERE user_id=? AND item_id='magnet' AND uses_remaining>0 
              AND expires_at>datetime('now')
        ORDER BY expires_at ASC LIMIT 1
    """, (user_id,)).fetchone()

    magnet_text = ""
    if has_magnet:
        magnet_id, current_uses = has_magnet
        reward += 2000  # ഒറിജിനൽ റിവാർഡിന്റെ കൂടെ 2000 കൂട്ടുന്നു
        
        # പുതിയ യൂസേജ് കണക്കാക്കുന്നു
        new_uses = current_uses - 1
        
        cursor.execute("UPDATE user_inventory SET uses_remaining = ? WHERE id=?", (new_uses, magnet_id))
        cursor.execute("DELETE FROM user_inventory WHERE id=? AND uses_remaining<=0", (magnet_id,))
        
        # മെസ്സേജിൽ കാണിക്കാൻ വേണ്ടി മാഗ്നറ്റ് സ്റ്റാറ്റസ് സെറ്റ് ചെയ്യുന്നു
        magnet_text = f"\n🧲 <b>Coin Magnet:</b> Activated (Remaining: {new_uses})"

    # 💰 ബാലൻസും സമയവും അപ്‌ഡേറ്റ് ചെയ്യുന്നു
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute(
        "UPDATE users SET balance = COALESCE(balance, 0) + ?, last_daily = ? WHERE user_id = ?",
        (reward, now_str, user_id)
    )
    conn.commit()
    conn.close()

    # 🎉 വിജയകരമായി ക്ലെയിം ചെയ്ത മെസ്സേജ് (മാഗ്നറ്റ് ഉണ്ടെങ്കിൽ മാത്രം താഴെ അത് കാണിക്കും)
    success_text = (
        f"🎁 <b>DAILY REWARD CLAIMED!</b>\n\n"
        f"<blockquote>"
        f"👤 <b>User:</b> {user.mention_html()}\n"
        f"💰 <b>Reward:</b> +{reward} Coins{magnet_text}"
        f"</blockquote>\n"
        f"✨ Come back tomorrow!"
    )

    await update.message.reply_text(success_text, parse_mode=ParseMode.HTML)


# ==========================
# /SPIN
# ==========================
async def spin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. ബാൻ ചെക്ക് ചെയ്യുന്നു
    if 'check_ban' in globals() and await check_ban(update):
        return

    user = update.effective_user
    user_id = user.id

    # 2. യൂസർ രജിസ്ട്രേഷൻ ഉറപ്പുവരുത്തുന്നു
    if 'check_and_register_user' in globals():
        try:
            check_and_register_user(user_id, user.username, user.first_name)
        except TypeError:
            check_and_register_user(user_id, user.username)

    # DB_NAME ഗ്ലോബൽ വേരിയബിൾ ആണെന്ന് ഉറപ്പുവരുത്തുക
    db_file = DB_NAME
    
    conn = db_connect(db_file)
    cursor = conn.cursor()

    # 3. അവസാനം സ്പിൻ ചെയ്ത സമയം ഡാറ്റാബേസിൽ നിന്ന് എടുക്കുന്നു
    cursor.execute("SELECT last_spin FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()

    now = datetime.now()

    # ⏳ 24 മണിക്കൂർ കൂൾഡൗൺ ചെക്ക്
    if row and row[0]:
        try:
            # ആദ്യത്തെ കോഡിലെ isoformat അല്ലെങ്കിൽ രണ്ടാമത്തേതിലെ strftime എന്നിവയിൽ ഏതായാലും ക്രാഷ് ആകാതിരിക്കാൻ
            if "T" in row[0]:
                last_time = datetime.fromisoformat(row[0])
            else:
                last_time = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
        except Exception:
            last_time = None

        if last_time and now < last_time + timedelta(hours=24):
            time_left = (last_time + timedelta(hours=24)) - now
            hours, remainder = divmod(int(time_left.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)

            conn.close()
            
            cooldown_text = (
                f"⏳ <b>Cooldown Active!</b>\n\n"
                f"<blockquote>⚠️ You already used your daily spin!\n"
                f"🕒 Come back after: <b>{hours}h {minutes}m</b></blockquote>"
            )
            return await update.message.reply_text(cooldown_text, parse_mode=ParseMode.HTML)

    # 🎁 ബേസ് റിവാർഡ് (15,000 മുതൽ 50,000 കോയിൻസ് വരെ)
    reward = random.randint(15000, 50000)

    # 💎 10% ലക്കി ബോണസ് ചാൻസ് (രണ്ടാമത്തെ കോഡിലെ കിടിലൻ ലോജിക്)
    lucky_text = ""
    if random.randint(1, 10) == 1:  
        bonus = random.randint(10000, 30000)
        reward += bonus
        lucky_text = f"\n\n🍀 <b>LUCKY BONUS!</b> +<code>{bonus:,}</code> coins 😈"

    # 4. ഡാറ്റാബേസിൽ കോയിൻസും സമയവും അപ്‌ഡേറ്റ് ചെയ്യുന്നു
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute("""
        UPDATE users
        SET balance = COALESCE(balance, 0) + ?,
            last_spin = ?
        WHERE user_id = ?
    """, (reward, now_str, user_id))

    conn.commit()
    conn.close()

    # 🎉 സ്പിൻ റിസൾട്ട് മെസ്സേജ് (പ്രീമിയം ബ്ലോക്ക്-കോട്ട് ലുക്ക്)
    success_text = (
        f"🎰 <b>Daily spin result</b>\n\n"
        f"<blockquote>"
        f"👤 <b>User:</b> {user.mention_html()}\n"
        f"💰 Reward: <b>{reward:,} coins</b>"
        f"{lucky_text}"
        f"</blockquote>"
    )

    await update.message.reply_text(success_text, parse_mode=ParseMode.HTML)



async def set_claim_chance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return

    if len(context.args) < 2:
        return await update.message.reply_text(
            "💡 <b>Usage:</b> <code>/setclaim [rarity_id] [chance_weight]</code>\n"
            "Example: <code>/setclaim 14 0.4</code> (Set AMV to 0.4)\n"
            "📝 <i>Set to 0 to turn that edition OFF!</i>", 
            parse_mode="HTML"
        )

    try:
        rarity_id = int(context.args[0])
        new_chance = float(context.args[1])
    except ValueError:
        return await update.message.reply_text("❌ Rarity ID and Chance must be numbers!")

    if rarity_id < 1 or rarity_id > 18:
        return await update.message.reply_text("❌ Rarity ID must be between 1 and 18!")

    conn = db_connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE claim_list SET chance=? WHERE rarity_id=?", (new_chance, rarity_id))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"✅ <b>Claim List Updated!</b>\n🎯 Rarity <b>{rarity_id}</b> chance weight is now <b>{new_chance}</b>", parse_mode="HTML")


async def view_claim_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 📊 ആർക്കും ഗ്രൂപ്പിൽ നിലവിലെ ചാൻസ് റേറ്റ് എത്രയെന്ന് നോക്കാൻ വേണ്ടിയുള്ളതാണ്
    conn = db_connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1 മുതൽ 18 വരെയുള്ള റാരിറ്റി ചാൻസുകൾ ഡാറ്റാബേസിൽ നിന്ന് എടുക്കുന്നു
    cursor.execute("SELECT rarity_id, chance FROM claim_list ORDER BY rarity_id ASC")
    rows = cursor.fetchall()
    conn.close()

    text = "📊 <b>HCLAIM RARITY CHANCE LIST</b>\n\n"
    for r_id, chance in rows:
        # ചാൻസ് 0-ൽ കൂടുതൽ ആണെങ്കിൽ ആ നമ്പർ കാണിക്കും, 0 ആണെങ്കിൽ OFF എന്ന് കാണിക്കും
        status = f"<code>{chance}</code>" if chance > 0 else "❌ <b>OFF</b>"
        text += f"• Rarity {r_id:02d} — {status}\n"

    await update.message.reply_text(text, parse_mode="HTML")

# ==========================
# /SUMMON
# ==========================

# ==========================
# /COLLECTION
# ==========================
def get_rarity_id(rarity_text):
    rarity_map = {
        "Common": 1, "Rare": 2, "Special Edition": 3, "Legendary": 4, "Mythic Edition": 5,
        "Valentine Edition": 6, "Summer Edition": 7, "Rainy Edition": 8, "Halloween Edition": 9,
        "Christmas Edition": 10, "Winter Edition": 11, "New Year Edition": 12, "Festival Edition": 13,
        "AMV Edition": 14, "Event Edition": 15, "Celestial Edition": 16, "Luxury Edition": 17, "Limited Edition": 18
    }
    for key, value in rarity_map.items():
        if key in rarity_text:
            return value
    return 1

# ==========================================
# 🎒 MAIN COLLECTION COMMAND
# ==========================================
async def collection_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update):
        return

    user_id = update.effective_user.id
    anime_filter = " ".join(context.args).strip().title() if context.args else None

    if anime_filter:
        context.user_data['anime_filter'] = anime_filter
    else:
        context.user_data.pop('anime_filter', None)

    await send_collection_page(update, context, user_id, page=0)

# ==========================================
# 📄 CORE FUNCTION: SEND/EDIT COLLECTION PAGE
# ==========================================
async def send_collection_page(update, context, user_id, page):
    conn = db_connect(DB_NAME)
    cursor = conn.cursor()

    # യൂസറുടെ ഒറിജിനൽ പേര് സെറ്റ് ചെയ്യുന്നു
    if update.message:
        name_to_show = update.effective_user.first_name
        context.user_data['full_name'] = name_to_show
    else:
        name_to_show = context.user_data.get('full_name')
        if not name_to_show:
            cursor.execute("SELECT username FROM users WHERE user_id = ?", (user_id,))
            user_row = cursor.fetchone()
            name_to_show = user_row[0] if user_row and user_row[0] else f"User {user_id}"

    # യൂസർ സെറ്റ് ചെയ്ത HMode പ്രിഫറൻസ് ഡാറ്റാബേസിൽ നിന്നും നോക്കുന്നു
    pref = get_user_pref(user_id)
    current_mode = pref[1] if pref else "anime"
    
    anime_filter = context.user_data.get('anime_filter')
    if anime_filter:
        current_mode = "anime"

    # ഫേവറിറ്റ് ക്യാരക്ടർ ഐഡി എടുക്കുന്നു
    cursor.execute("SELECT favorite FROM users WHERE user_id = ?", (user_id,))
    user_row = cursor.fetchone()
    fav_char_id = user_row[0] if user_row else None

    # HMODE പ്രകാരം ടോട്ടൽ ഐറ്റം കൗണ്ട് ചെയ്യുന്നു
    if anime_filter:
        cursor.execute("""
            SELECT IFNULL(SUM(uc.count), 0) FROM user_collection uc
            JOIN characters c ON uc.character_id = c.id
            WHERE uc.user_id = ? AND c.anime LIKE ?
        """, (user_id, f"%{anime_filter}%"))
    elif current_mode in ["anime", "recent", "fav"]:
        cursor.execute("SELECT IFNULL(SUM(count), 0) FROM user_collection WHERE user_id = ?", (user_id,))
    else:
        cursor.execute("""
            SELECT IFNULL(SUM(uc.count), 0) FROM user_collection uc
            JOIN characters c ON uc.character_id = c.id
            WHERE uc.user_id = ? AND LOWER(c.rarity) = ?
        """, (user_id, current_mode.lower()))
    
    total_items = cursor.fetchone()[0]

    if total_items == 0:
        conn.close()
        filter_text = f"[{current_mode.upper()}] " if current_mode not in ["anime", "recent", "fav"] else ""
        empty_text = f"🎒 <b>Your {filter_text}{f'{anime_filter} ' if anime_filter else ''}collection is empty.</b>"
        if update.message:
            return await update.message.reply_text(empty_text, parse_mode="HTML")
        else:
            return await update.callback_query.message.edit_text(empty_text, parse_mode="HTML")

    ITEMS_PER_PAGE = 10

    # യൂണീക് ക്യാരക്ടർ കൗണ്ട് ചെയ്യുന്നു
    if anime_filter:
        cursor.execute("""
            SELECT COUNT(DISTINCT uc.character_id) FROM user_collection uc
            JOIN characters c ON uc.character_id = c.id
            WHERE uc.user_id = ? AND c.anime LIKE ?
        """, (user_id, f"%{anime_filter}%"))
    elif current_mode in ["anime", "recent", "fav"]:
        cursor.execute("SELECT COUNT(DISTINCT character_id) FROM user_collection WHERE user_id = ?", (user_id,))
    else:
        cursor.execute("""
            SELECT COUNT(DISTINCT uc.character_id) FROM user_collection uc
            JOIN characters c ON uc.character_id = c.id
            WHERE uc.user_id = ? AND LOWER(c.rarity) = ?
        """, (user_id, current_mode.lower()))
        
    unique_chars_count = cursor.fetchone()[0]
    total_pages = (unique_chars_count + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    page = max(0, min(page, total_pages - 1))

    # ഫേവറിറ്റ് ക്യാരക്ടർ മീഡിയ ഐഡി എടുക്കുന്നു
    fav_media_id = None
    if fav_char_id and not anime_filter:
        cursor.execute("SELECT image_url FROM characters WHERE id = ?", (fav_char_id,))
        fav_char = cursor.fetchone()
        if fav_char:
            fav_media_id = fav_char[0]

    offset = page * ITEMS_PER_PAGE

    # HMode പ്രകാരം ഡാറ്റ ക്വറി ചെയ്യുന്നു
    if anime_filter:
        cursor.execute("""
            SELECT c.id, c.name, c.anime, c.rarity, uc.count
            FROM user_collection uc
            JOIN characters c ON uc.character_id = c.id
            WHERE uc.user_id = ? AND c.anime LIKE ?
            ORDER BY c.anime ASC, CAST(c.id AS INTEGER) ASC
            LIMIT ? OFFSET ?
        """, (user_id, f"%{anime_filter}%", ITEMS_PER_PAGE, offset))
        
    elif current_mode == "anime":
        cursor.execute("""
            SELECT c.id, c.name, c.anime, c.rarity, uc.count
            FROM user_collection uc
            JOIN characters c ON uc.character_id = c.id
            WHERE uc.user_id = ?
            ORDER BY c.anime ASC, CAST(c.id AS INTEGER) ASC
            LIMIT ? OFFSET ?
        """, (user_id, ITEMS_PER_PAGE, offset))

    elif current_mode == "recent":
        cursor.execute("""
            SELECT c.id, c.name, c.anime, c.rarity, uc.count
            FROM user_collection uc
            JOIN characters c ON uc.character_id = c.id
            WHERE uc.user_id = ?
            ORDER BY uc.id DESC
            LIMIT ? OFFSET ?
        """, (user_id, ITEMS_PER_PAGE, offset))

    elif current_mode == "fav":
        cursor.execute("""
            SELECT c.id, c.name, c.anime, c.rarity, uc.count,
                   (CASE WHEN c.id = ? THEN 1 ELSE 0 END) as is_fav
            FROM user_collection uc
            JOIN characters c ON uc.character_id = c.id
            WHERE uc.user_id = ?
            ORDER BY is_fav DESC, c.anime ASC, CAST(c.id AS INTEGER) ASC
            LIMIT ? OFFSET ?
        """, (fav_char_id, user_id, ITEMS_PER_PAGE, offset))

    else:
        cursor.execute("""
            SELECT c.id, c.name, c.anime, c.rarity, uc.count
            FROM user_collection uc
            JOIN characters c ON uc.character_id = c.id
            WHERE uc.user_id = ? AND LOWER(c.rarity) = ?
            ORDER BY c.anime ASC, CAST(c.id AS INTEGER) ASC
            LIMIT ? OFFSET ?
        """, (user_id, current_mode.lower(), ITEMS_PER_PAGE, offset))

    db_rows = cursor.fetchall()

        # 🎯 FIX: 'fav' മോഡിൽ വരുന്ന 6-ാമത്തെ കോളം (is_fav) കൂടി ഇവിടെ കൃത്യമായി ഹാൻഡിൽ ചെയ്യുന്നു!
    anime_groups = {}
    for row in db_rows:
        # ഡാറ്റയിൽ 5 കോളം ഉണ്ടായാലും 6 കോളം ഉണ്ടായാലും ആദ്യത്തെ 5 എണ്ണം മാത്രം എടുക്കുന്നു
        char_id, name, anime_name, rarity_text, count = row[0], row[1], row[2], row[3], row[4]
        
        if anime_name not in anime_groups:
            anime_groups[anime_name] = []
        anime_groups[anime_name].append({
            "id": char_id, "name": name, "rarity": rarity_text, "count": count
        })


    title_mode = f" | {current_mode.upper()}" if current_mode not in ["anime", "recent", "fav"] else f" | {current_mode.capitalize()}"
    if anime_filter: title_mode = f" | {anime_filter}"
        
    text = f"🎒 <b>{name_to_show}'s Collection</b>{title_mode} (Total: {total_items})\n\n"

    # ഗ്രൂപ്പ് ചെയ്ത അനിമൈകൾ ഓരോന്നായി പഴയ സ്റ്റൈലിൽ ഫോർമാറ്റ് ചെയ്യുന്നു (No Blockquote!)
    for anime_name, chars_list in anime_groups.items():
        cursor.execute("""
            SELECT COUNT(DISTINCT uc.character_id) FROM user_collection uc
            JOIN characters c ON uc.character_id = c.id
            WHERE uc.user_id = ? AND c.anime = ?
        """, (user_id, anime_name))
        owned_in_anime = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM characters WHERE anime = ?", (anime_name,))
        total_in_anime = cursor.fetchone()[0]

        text += f" <b>{anime_name}</b>  {owned_in_anime}/{total_in_anime}\n"
        
        for char in chars_list:
            r_id = get_rarity_id(char["rarity"])
            emoji = RARITY_EMOJI.get(r_id, "⭐")
            # 🎯 FIX: പഴയത് പോലെ നേരിട്ട് ടെക്സ്റ്റിലേക്ക് ആഡ് ചെയ്യുന്നു
            text += f"◈ {char['id']} ⌠{emoji}⌡ {char['name']} ×{char['count']}\n"
        text += "\n"

    conn.close()
    text += f"<b>Page: {page+1}/{total_pages}</b>"

        # 🎨 ഇൻലൈൻ ബട്ടണുകൾ വിത്ത് കളർ സ്റ്റൈൽസ് (PTB v21+)
    row1 = [
        InlineKeyboardButton("🌐", switch_inline_query_current_chat=f"collection.{user_id}"),
        InlineKeyboardButton("🎬", switch_inline_query_current_chat=f"collection.{user_id}.amv")
    ]

    row2 = []
    
    # പുറകോട്ട് പോകാനുള്ള ബട്ടൺ
    if page > 0:
        row2.append(InlineKeyboardButton("⬅️", callback_data=f"col_{user_id}_{page-1}"))
    else:
        row2.append(InlineKeyboardButton("🚫", callback_data="ignore"))

    # പേജ് നമ്പർ കാണിക്കുന്ന നടുവിലെ ബട്ടൺ
    row2.append(InlineKeyboardButton(f"{page+1} / {total_pages}", callback_data="ignore"))

    # മുന്നോട്ട് പോകാനുള്ള ബട്ടൺ
    if page < total_pages - 1:
        row2.append(InlineKeyboardButton("➡️", callback_data=f"col_{user_id}_{page+1}"))
    else:
        row2.append(InlineKeyboardButton("🚫", callback_data="ignore"))

    keyboard = InlineKeyboardMarkup([row1, row2])


    # മീഡിയ സെൻഡിങ് / എഡിറ്റിങ് പാർട്ട് 
    if update.message:
        if fav_media_id and not anime_filter:
            await send_character_media(context.bot, update.effective_chat.id, fav_media_id, text, reply_markup=keyboard)
        else:
            await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        try:
            await update.callback_query.message.edit_caption(caption=text, reply_markup=keyboard, parse_mode="HTML")
        except Exception:
            try:
                await update.callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            except Exception:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=keyboard, parse_mode="HTML")


# ==========================================
# 🎮 PAGE NAVIGATION CONTROLLER
# ==========================================
async def collection_nav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "ignore":
        return

    _, target_user_id, target_page = query.data.split("_")
    target_user_id, target_page = int(target_user_id), int(target_page)

    if query.from_user.id != target_user_id:
        return await query.answer("❌ This is not your collection menu!", show_alert=True)

    if query.message.photo:
        try:
            await query.message.delete()
        except Exception:
            pass

    await send_collection_page(update, context, target_user_id, target_page)

# ==========================
# /CHECK
# ==========================
async def check_character(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update): 
        return                                                                                    
    
    if not context.args: 
        return await update.message.reply_text("Usage: /check <character_id>")
    
    char_id = context.args[0]
    conn = db_connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT name, anime, rarity, image_url FROM characters WHERE id=?", (char_id,))
    char = cursor.fetchone()
    conn.close()                                                                                                          
    
    if not char: 
        return await update.message.reply_text("❌ Character not found.")
    
    name, anime, rarity, image_url = char
    
    # 👑 നിന്റെ കൃത്യമായ ഡിസൈൻ ഫോർമാറ്റ് (Info blockquote-ൽ ഒതുക്കി നിർത്തിയിരിക്കുന്നു)
    text = (
        f"🔍 <b>Character Info</b>\n\n"
        f"<blockquote>"
        f"👤 <b>Name:</b> {name}\n"
        f"🎌 <b>Anime:</b> {anime}\n"
        f"⭐ <b>Rarity:</b> {rarity}\n"
        f"🆔 <b>ID:</b> {char_id}"
        f"</blockquote>"
    )
    
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("👥 View Owners", callback_data=f"owners_{char_id}")]])
    
    try:
        await send_character_media(context.bot, update.effective_chat.id, image_url, text, reply_markup=keyboard)
    except Exception:
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")

import collections

# ==========================================================
# 👥 VIEW OWNERS CALLBACK (owners_<char_id>)
# ==========================================================
async def owner_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        char_id = query.data.replace("owners_", "", 1)

        conn = db_connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT u.user_id, u.username, uc.count
            FROM user_collection uc
            LEFT JOIN users u ON uc.user_id = u.user_id
            WHERE CAST(uc.character_id AS TEXT) = CAST(? AS TEXT)
            ORDER BY uc.count DESC
            LIMIT 10
        """, (char_id,))

        owners = cursor.fetchall()
        conn.close()

        text = f"👥 <b>Top Owners for Character (ID: {char_id})</b>\n"
        text += "━━━━━━━━━━━━━━━━━━━━\n\n"

        if not owners:
            text += "<i>No one owns this character yet!</i>"
        else:
            for index, (u_id, username, count) in enumerate(owners, start=1):

                if username and username != "Unknown":
                    user_text = f"@{username}"
                else:
                    user_text = f"<a href='tg://user?id={u_id}'>User {u_id}</a>"

                text += f"<b>{index:02d}.</b> {user_text} — <b>×{count}</b>\n"

        text += "\n━━━━━━━━━━━━━━━━━━━━"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data=f"backcheck_{char_id}")]
        ])

        try:
            await query.edit_message_caption(
                caption=text,
                parse_mode="HTML",
                reply_markup=keyboard
            )
        except Exception:
            await query.edit_message_text(
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard
            )

    except Exception as e:
        logger.exception(f"owner_callback error: {e}")

        try:
            await query.edit_message_caption(
                caption=f"❌ Error:\n<code>{e}</code>",
                parse_mode="HTML"
            )
        except Exception:
            await query.edit_message_text(
                text=f"❌ Error:\n<code>{e}</code>",
                parse_mode="HTML"
            )


# ==========================================================
# 🔙 BACK CALLBACK (backcheck_<char_id>)
# ==========================================================
async def back_check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        char_id = query.data.replace("backcheck_", "", 1)

        conn = db_connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT name, anime, rarity FROM characters WHERE id=?",
            (char_id,)
        )

        char = cursor.fetchone()
        conn.close()

        if not char:
            try:
                await query.edit_message_caption(
                    caption="❌ Character not found."
                )
            except Exception:
                await query.edit_message_text(
                    text="❌ Character not found."
                )
            return

        name, anime, rarity = char

        text = (
            f"🔍 <b>Character Info</b>\n\n"
            f"<blockquote>"
            f"👤 <b>Name:</b> {name}\n"
            f"🎌 <b>Anime:</b> {anime}\n"
            f"⭐ <b>Rarity:</b> {rarity}\n"
            f"🆔 <b>ID:</b> {char_id}"
            f"</blockquote>"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "👥 View Owners",
                callback_data=f"owners_{char_id}"
            )]
        ])

        try:
            await query.edit_message_caption(
                caption=text,
                parse_mode="HTML",
                reply_markup=keyboard
            )
        except Exception:
            await query.edit_message_text(
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard
            )

    except Exception as e:
        logger.exception(f"back_check_callback error: {e}")

        try:
            await query.edit_message_caption(
                caption=f"❌ Error:\n<code>{e}</code>",
                parse_mode="HTML"
            )
        except Exception:
            await query.edit_message_text(
                text=f"❌ Error:\n<code>{e}</code>",
                parse_mode="HTML"
            )

    
async def owners(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    char_id = query.data.split("_")[1]
    
    conn = db_connect(DB_NAME)
    cursor = conn.cursor()
    
    # 🎯 Joined query to fetch usernames instead of raw IDs
    cursor.execute("""
        SELECT u.user_id, u.username, uc.count 
        FROM user_collection uc
        LEFT JOIN users u ON uc.user_id = u.user_id
        WHERE uc.character_id = ?
        ORDER BY uc.count DESC
    """, (char_id,))
    
    owner_list = cursor.fetchall()
    conn.close()
    
    text = f"👥 <b>Owners List for (ID: {char_id})</b>\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n\n"
    
    if owner_list:
        for u_id, username, count in owner_list:
            display_name = f"@{username}" if username else f"ID: <code>{u_id}</code>"
            text += f"• {display_name} — <b>x{count}</b>\n"
    else:
        text += "• No owners yet"
        
    await query.edit_message_text(text, parse_mode="HTML")

# ==========================
# /SEARCH
# ==========================
async def search_character(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update):
        return
    if not context.args:
        return await update.message.reply_text("Use: /search <name>")

    # Search query formatting
    search_query = "%" + "%".join(context.args) + "%"
    
    rows = fetch_all(
        "SELECT id, name, anime, rarity FROM characters WHERE name LIKE ?", 
        (search_query,)
    )
    
    if not rows:
        return await update.message.reply_text("❌ No match found.", parse_mode=ParseMode.HTML)

    # ഒരേ സമയം ഒരു പേജിൽ 10 ക്യാരക്ടറുകൾ വീതം കാണിക്കുന്നു
    per_page = 10
    total_pages = (len(rows) + per_page - 1) // per_page
    current_page = 1

    # ഡാറ്റയും സെർച്ച് ക്വറിയും താല്ക്കാലികമായി context-ൽ സൂക്ഷിക്കുന്നു
    context.user_data["search_results"] = rows
    context.user_data["search_query"] = " ".join(context.args)

    # ആദ്യ പേജിലെ ടെക്സ്റ്റും ബട്ടണുകളും ഉണ്ടാക്കുന്നു
    text, reply_markup = _build_search_page(rows, current_page, per_page, total_pages, context.user_data["search_query"])

    await update.message.reply_text(
        text, 
        parse_mode=ParseMode.HTML, 
        reply_markup=reply_markup
    )


# 2️⃣ HELPER FUNCTION: പേജ് ഡിസൈൻ ചെയ്യാൻ വേണ്ടി മാത്രം
def _build_search_page(rows, page, per_page, total_pages, query_text):
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_items = rows[start_idx:end_idx]

    text = f"🔍 <b>SEARCH RESULTS FOR:</b> <code>{query_text}</code>\n\n"
    
    for cid, name, anime, rarity in page_items:
        text += (
            f"• <b>{name}</b>\n"
            f"<blockquote>🎌 {anime}\n"
            f"🏅 Rarity: {rarity}\n"
            f"🆔 ID: <code>{cid}</code></blockquote>\n"
        )
    
    text += f"\n📊 <b>Page:</b> {page}/{total_pages} (Total: {len(rows)})"

    # ഇൻലൈൻ കീബോർഡ് ബട്ടണുകൾ ഉണ്ടാക്കുന്നു
    buttons = []
    if page > 1:
        buttons.append(InlineKeyboardButton("⬅️ Back", callback_data=f"srch_{page-1}"))
    if page < total_pages:
        buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"srch_{page+1}"))

    reply_markup = InlineKeyboardMarkup([buttons]) if buttons else None
    return text, reply_markup


# 3️⃣ CALLBACK HANDLER FOR NEXT/BACK BUTTONS
async def search_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Next / Back ബട്ടണുകൾ പ്രസ്സ് ചെയ്യുമ്പോൾ പേജ് മാറ്റാനുള്ള ലോജിക്"""
    query = update.callback_query
    await query.answer()

    # ഫയൽ റീസ്റ്റാർട്ട് ആവുകയോ മറ്റോ ചെയ്താൽ ഡാറ്റ നഷ്ടപ്പെടാതിരിക്കാൻ
    rows = context.user_data.get("search_results")
    query_text = context.user_data.get("search_query", "Search")
    if not rows:
        return await query.message.edit_text("❌ Search session expired. Please search again.")

    # ക്ലിക്ക് ചെയ്ത പേജ് നമ്പർ എടുക്കുന്നു
    try:
        target_page = int(query.data.split("_")[1])
    except (IndexError, ValueError):
        return

    per_page = 10
    total_pages = (len(rows) + per_page - 1) // per_page

    text, reply_markup = _build_search_page(rows, target_page, per_page, total_pages, query_text)

    try:
        await query.message.edit_text(
            text, 
            parse_mode=ParseMode.HTML, 
            reply_markup=reply_markup
        )
    except Exception:
        pass

# ==========================
# /FAV
# ==========================
async def favorite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update): return
    if not context.args: 
        return await update.message.reply_text("💡 Usage: <code>/fav <character_id></code>", parse_mode="HTML")       
    char_id = context.args[0]
    user_id = update.effective_user.id
    
    conn = db_connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. ക്യാരക്ടർ ഡാറ്റാബേസിൽ ഉണ്ടോ എന്നും അതിന്റെ വിവരങ്ങളും മീഡിയയും എടുക്കുന്നു
    cursor.execute("SELECT name, anime, image_url FROM characters WHERE id=?", (char_id,))
    char_data = cursor.fetchone()
    
    if not char_data:
        conn.close()
        return await update.message.reply_text("❌ Character not found in database.")
        
    char_name, anime_name, media_id = char_data
    
    # 2. യൂസറുടെ കളക്ഷനിൽ ഈ ക്യാരക്ടർ ഉണ്ടോ എന്ന് നോക്കുന്നു
    cursor.execute("SELECT 1 FROM user_collection WHERE user_id=? AND character_id=?", (user_id, char_id))
    if not cursor.fetchone():
        conn.close()
        return await update.message.reply_text("❌ You don't own that character in your collection.")
        
    # 3. ഫേവറിറ്റ് ആയി അപ്‌ഡേറ്റ് ചെയ്യുന്നു
    cursor.execute("UPDATE users SET favorite=? WHERE user_id=?", (char_id, user_id))
    conn.commit()
    conn.close()

    # 4. ഭംഗിയുള്ള ഫോർമാറ്റ് റെഡിയാക്കുന്നു
    fav_text = (
        "💖 <b>New Favorite Set!</b>\n\n"
        f"<blockquote><b>• Character: {char_name} (ID: {char_id})\n"
        f"• Anime: {anime_name}</b></blockquote>\n"
        "This character will now feature at the top of your collection!"
    )

    # 5. ക്യാരക്ടറിന്റെ ഫോട്ടോ/വീഡിയോ സഹിതം മെസ്സേജ് അയക്കുന്നു
    try:
        await send_character_media(context.bot, update.effective_chat.id, media_id, fav_text)
    except Exception:
        await update.message.reply_text(fav_text, parse_mode="HTML")

# ==========================
# /GIVE
# ==========================
async def give_character(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: 
        return

    # Check for reply and character ID
    if not update.message.reply_to_message or not context.args:
        return await update.message.reply_text("💡 Usage: Reply to a user with <code>/give <character_id></code>", parse_mode="HTML")

    char_id = context.args[0]
    target = update.message.reply_to_message.from_user
    target_user_id = target.id  # Target user-ude ID

    conn = db_connect(DB_NAME)
    cursor = conn.cursor()

    # 1. Database-il ninnu character details edukkunnu
    cursor.execute("SELECT name, anime, image_url FROM characters WHERE id=?", (char_id,))
    char_data = cursor.fetchone()

    if not char_data:
        conn.close()
        return await update.message.reply_text("❌ Character not found in database.")

    char_name, anime_name, media_id = char_data

    # 2. User-ude collection-ilekk add cheyyunnu (Count +1 aക്കുന്നു)
    cursor.execute("""
        INSERT INTO user_collection (user_id, character_id, count)
        VALUES (?, ?, 1)
        ON CONFLICT(user_id, character_id)
        DO UPDATE SET count = count + 1
    """, (target_user_id, char_id))
    
    conn.commit()
    conn.close()

    # 3. Nee paraja athe format: Aa randu varikal mathram blockquote-il!
    give_text = (
        "🎁 <b>Character Added Successfully!</b>\n\n"
        f"<blockquote>• Character: {char_name} (ID: {char_id})\n"
        f"• Added to: {target.first_name}</blockquote>\n\n"
        "The character has been generated and added to the user's collection!"
    )

    # 4. Character media send cheyyunnu
    try:
        await send_character_media(context.bot, update.effective_chat.id, media_id, give_text)
    except Exception:
        await update.message.reply_text(give_text, parse_mode="HTML")

async def gift_character(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update): 
        return

    # Reply-um ID-um undo enn nokkunnu
    if not update.message.reply_to_message or not context.args:
        return await update.message.reply_text("💡 Usage: Reply to a user with <code>/gift <character_id></code>", parse_mode="HTML")

    giver_id = update.effective_user.id
    target = update.message.reply_to_message.from_user

    if giver_id == target.id:
        return await update.message.reply_text("❌ Cannot gift to yourself!")

    char_id = context.args[0]

    conn = db_connect(DB_NAME)
    cursor = conn.cursor()

    # 1. Character database-il undo enn nokkunnu
    cursor.execute("SELECT name, anime, image_url FROM characters WHERE id=?", (char_id,))
    char_data = cursor.fetchone()

    if not char_data:
        conn.close()
        return await update.message.reply_text("❌ Character not found in database.")

    char_name, anime_name, media_id = char_data

    # 2. Giver-ude kayyil ee character undo, ethra count undennum nokkunnu
    cursor.execute("SELECT count FROM user_collection WHERE user_id=? AND character_id=?", (giver_id, char_id))
    giver_row = cursor.fetchone()

    if not giver_row:
        conn.close()
        return await update.message.reply_text("❌ You don't own this character.")

    giver_count = giver_row[0]

    # 3. Target user-ne register cheyyunnu (DB-il illel)
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (target.id, target.username))

    # 4. Giver-ude kayyil ninnu count kuraykkunnu / delete cheyyunnu
    if giver_count > 1:
        cursor.execute("UPDATE user_collection SET count = count - 1 WHERE user_id=? AND character_id=?", (giver_id, char_id))
    else:
        cursor.execute("DELETE FROM user_collection WHERE user_id=? AND character_id=?", (giver_id, char_id))

    # 5. Receiver-ude (Target) collection-ilekk add cheyyunnu (Count +1 aക്കുന്നു)
    cursor.execute("""
        INSERT INTO user_collection (user_id, character_id, count)
        VALUES (?, ?, 1)
        ON CONFLICT(user_id, character_id)
        DO UPDATE SET count = count + 1
    """, (target.id, char_id))

    conn.commit()
    conn.close()

    # 6. Aa randu varikal mathram blockquote-il ulla premium layout!
    gift_text = (
        "✅ <b>Gift Delivered!</b>\n\n"
        f"<blockquote>• Character: {char_name} (ID: {char_id})\n"
        f"• Sent to: {target.first_name}</blockquote>\n\n"
        "Your character has been successfully transferred!"
    )

    # 7. Character media send cheyyunnu
    try:
        await send_character_media(context.bot, update.effective_chat.id, media_id, gift_text)
    except Exception:
        await update.message.reply_text(gift_text, parse_mode="HTML")

# ==========================
# /PAY
# ==========================
async def pay_money(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 👥 ഇത് എല്ലാവർക്കും ഉപയോഗിക്കാം
    user_id = update.effective_user.id
    reply = update.message.reply_to_message

    # ഫോർമാറ്റ് ചെക്ക് (ഒന്നുകിൽ റിപ്ലൈ ചെയ്യണം, അല്ലെങ്കിൽ ID കൊടുക്കണം)
    if not reply and len(context.args) < 2:
        return await update.message.reply_text(
            "💡 <b>Usage:</b>\n"
            "1️⃣ Reply to a user: <code>/pay [amount]</code>\n"
            "2️⃣ Or use ID: <code>/pay [user_id] [amount]</code>", 
            parse_mode="HTML"
        )

    try:
        if reply:
            target_id = reply.from_user.id
            amount = int(context.args[0])
        else:
            target_id = int(context.args[0])
            amount = int(context.args[1])
    except (ValueError, IndexError):
        return await update.message.reply_text("❌ Invalid details or amount format!")

    if amount <= 0:
        return await update.message.reply_text("❌ Amount must be greater than 0!")

    if target_id == user_id:
        return await update.message.reply_text("❌ You cannot pay money to yourself! 🪙")

    conn = db_connect(DB_NAME)
    cursor = conn.cursor()

    # അയക്കുന്ന ആളുടെ ബാലൻസ് ചെക്ക്
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    sender = cursor.fetchone()
    if not sender or sender[0] < amount:
        conn.close()
        return await update.message.reply_text("❌ Insufficient balance! You don't have enough coins.")

    # വാങ്ങുന്ന ആൾ ഡാറ്റാബേസിൽ ഉണ്ടോ എന്ന് നോക്കുന്നു
    cursor.execute("SELECT username FROM users WHERE user_id = ?", (target_id,))
    receiver = cursor.fetchone()
    if not receiver:
        conn.close()
        return await update.message.reply_text("❌ Target user hasn't started the bot yet!")

    # പൈസ അങ്ങോട്ടും ഇങ്ങോട്ടും മാറ്റുന്നു (Transaction)
    cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target_id))
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"💸 <b>Transaction Successful!</b>\n\n"
        f"<blockquote>👤 <b>From:</b> {update.effective_user.mention_html()}\n"
        f"🎯 <b>To:</b> <a href='tg://user?id={target_id}'>User</a>\n"
        f"💰 <b>Amount:</b> {amount} Coins</blockquote>\n"
        f"✨ Paid successfully!",
        parse_mode="HTML"
    )

async def give_money(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 👑 ഓണർക്ക് മാത്രമുള്ള ചെക്ക്
    if update.effective_user.id != OWNER_ID:
        return await update.message.reply_text("❌ Not allowed")

    if len(context.args) < 2:
        return await update.message.reply_text("💡 Usage: <code>/givemoney [user_id] [amount]</code>", parse_mode="HTML")

    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
    except ValueError:
        return await update.message.reply_text("❌ Invalid user ID or amount number!")

    conn = db_connect(DB_NAME)
    cursor = conn.cursor()
    
    # യൂസർ ഡാറ്റാബേസിൽ ഉണ്ടോ എന്ന് നോക്കുന്നു
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (target_id,))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return await update.message.reply_text("❌ User not found in database!")

    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target_id))
    conn.commit()
    conn.close()

    await update.message.reply_text(	
        f"💰 <b>Added Money!</b>\n\n"
        f"<blockquote>👤 <b>User ID:</b> <code>{target_id}</code>\n"
        f"💵 <b>Added:</b> +{amount} Coins</blockquote>\n"
        f"✅ Balance updated successfully!",
        parse_mode="HTML"
    )


async def rm_money(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 👑 ഓണർക്ക് മാത്രമുള്ള ചെക്ക്
    if update.effective_user.id != OWNER_ID:
        return await update.message.reply_text("❌ Not allowed")

    if len(context.args) < 2:
        return await update.message.reply_text("💡 Usage: <code>/rmmoney [user_id] [amount]</code>", parse_mode="HTML")

    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
    except ValueError:
        return await update.message.reply_text("❌ Invalid user ID or amount number!")

    conn = db_connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (target_id,))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return await update.message.reply_text("❌ User not found in database!")

    current_balance = user[0]
    if current_balance < amount:
        amount = current_balance # പൈസ മൈനസ് (-) ആകതിരിക്കാൻ വേണ്ടിയുള്ള സേഫ്റ്റി

    cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, target_id))
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"🔻 <b>Removed Money!</b>\n\n"
        f"<blockquote>👤 <b>User ID:</b> <code>{target_id}</code>\n"
        f"📉 <b>Deducted:</b> -{amount} Coins</blockquote>\n"
        f"✅ Balance updated successfully!",
        parse_mode="HTML"
    )

# ==========================================
# 1. /SHOP COMMAND (മെയിൻ കമാൻഡ്)
# ==========================================
async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ആദ്യത്തെ കോഡിലെ ബാൻ ചെക്ക് ഇവിടെ നിലനിർത്തിയിരിക്കുന്നു
    if 'check_ban' in globals() and await check_ban(update):
        return

    text = (
        "🛒 <b>WELCOME TO SHOP</b>\n\n"
        "<blockquote>🎴 Tap open shop to view all rarities</blockquote>"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛍️ Open Shop", callback_data="open_shop")]
    ])

    # SHOP_IMAGE നിങ്ങളുടെ ഫയലിൽ ഡിഫൈൻ ചെയ്ത ഇമേജ് ലിങ്ക്/ഐഡി ആയിരിക്കണം
    shop_img = SHOP_IMAGE if 'SHOP_IMAGE' in globals() else "https://telegra.ph/file/default.jpg"

    await update.message.reply_photo(
        photo=shop_img,
        caption=text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

# ==========================================
# 2. OPEN SHOP CALLBACK
# ==========================================
async def open_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # PRICE ഡിക്ഷണറിയിലെ റാരിറ്റികൾ എടുക്കുന്നു
    rarities = list(PRICE.keys()) if 'PRICE' in globals() else ["UR", "SSR", "SR", "R"]

    keyboard = []
    row = []

    # ബട്ടണുകൾ 2 എണ്ണം വീതമുള്ള വരികളാക്കുന്നു
    for i, r in enumerate(rarities, start=1):
        row.append(InlineKeyboardButton(r, callback_data=f"rarity_{r}"))
        if i % 2 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    try:
        await query.message.edit_caption(
            caption="🛒 <b>SELECT RARITY</b>\n\n🎴 Choose a rarity",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception:
        # ഒരുവേള ഫോട്ടോ ഇല്ലെങ്കിൽ ടെക്സ്റ്റ് മെസ്സേജ് ആയി എഡിറ്റ് ചെയ്യാൻ
        await query.message.edit_text(
            text="🛒 <b>SELECT RARITY</b>\n\n🎴 Choose a rarity",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# ==========================================
# 3. RARITY PICK CALLBACK (ക്യാരക്ടർ സെലക്ഷൻ)
# ==========================================
async def rarity_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    rarity = query.data.replace("rarity_", "")
    db_file = DB_NAME

    conn = db_connect(db_file)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, name, anime, rarity, image_url
        FROM characters
        WHERE rarity=?
        ORDER BY RANDOM()
        LIMIT 1
    """, (rarity,))

    char = cursor.fetchone()
    conn.close()

    if not char:
        return await query.answer("❌ No character found for this rarity!", show_alert=True)

    char_id, name, anime, rarity, image_url = char
    price_dict = PRICE if 'PRICE' in globals() else {}
    price = price_dict.get(rarity, 15000)

    text = (
        f"🛒 <b>SHOP CHARACTER</b>\n\n"
        f"<blockquote>"
        f"🆔 <b>ID:</b> <code>{char_id}</code>\n"
        f"👤 <b>Name:</b> {name}\n"
        f"🎌 <b>Anime:</b> {anime}\n"
        f"⭐ <b>Rarity:</b> {rarity}\n"
        f"💰 <b>Price:</b> {price:,} Coins"
        f"</blockquote>"
    )

    buttons = []
    allowed_refresh = REFRESH_ALLOWED if 'REFRESH_ALLOWED' in globals() else ["UR", "SSR"]

    # 🔄 റീഫ്രഷ് ബട്ടൺ അനുമതിയുള്ള റാരിറ്റികൾക്ക് മാത്രം
    if rarity in allowed_refresh:
        buttons.append([InlineKeyboardButton("🔄 Refresh (10k)", callback_data=f"refresh_{rarity}")])

    buttons.append([InlineKeyboardButton("🛒 Buy", callback_data=f"buy_{char_id}_{price}")])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="open_shop")])

    # പഴയ മെസ്സേജ് സ്പാം ആകാതിരിക്കാൻ ഡിലീറ്റ് ചെയ്യുന്നു
    try:
        await query.message.delete()
    except Exception:
        pass

    # ക്യാരക്ടർ മീഡിയ ഫയൽ സെൻഡ് ചെയ്യുന്നു
    if 'send_character_media' in globals():
        await send_character_media(
            bot=context.bot,
            chat_id=update.effective_chat.id,
            image_url=image_url,
            caption=text,
            reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(buttons)
        )

# ==========================================
# 4. REFRESH CALLBACK
# ==========================================
async def refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    rarity = query.data.replace("refresh_", "")
    user = query.from_user
    db_file = DB_NAME if 'DB_NAME' in globals() else "summon_collection.db"

    conn = db_connect(db_file)
    cursor = conn.cursor()

    # കോയിൻ ബാലൻസ് ചെക്ക് ചെയ്യുന്നു
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (user.id,))
    bal = cursor.fetchone()

    if not bal or bal[0] < 10000:
        conn.close()
        return await query.answer("❌ Need 10,000 Coins to refresh!", show_alert=True)

    # 10k കോയിൻസ് കുറയ്ക്കുന്നു
    cursor.execute("UPDATE users SET balance = balance - 10000 WHERE user_id=?", (user.id,))

    # വീണ്ടും മറ്റൊരു ക്യാരക്ടറിനെ റാൻഡം ആയി എടുക്കുന്നു
    cursor.execute("""
        SELECT id, name, anime, rarity, image_url
        FROM characters
        WHERE rarity=?
        ORDER BY RANDOM()
        LIMIT 1
    """, (rarity,))

    char = cursor.fetchone()
    conn.commit()
    conn.close()

    if not char:
        return await query.answer("❌ No character found!", show_alert=True)

    char_id, name, anime, rarity, image_url = char
    price_dict = PRICE if 'PRICE' in globals() else {}
    price = price_dict.get(rarity, 15000)

    text = (
        f"🎴 <b>REFRESH RESULT</b>\n\n"
        f"<blockquote>"
        f"🆔 <b>ID:</b> <code>{char_id}</code>\n"
        f"👤 <b>Name:</b> {name}\n"
        f"🎌 <b>Anime:</b> {anime}\n"
        f"⭐ <b>Rarity:</b> {rarity}\n"
        f"💰 <b>Price:</b> {price:,} Coins"
        f"</blockquote>"
    )

    buttons = []
    allowed_refresh = REFRESH_ALLOWED if 'REFRESH_ALLOWED' in globals() else ["UR", "SSR"]

    if rarity in allowed_refresh:
        buttons.append([InlineKeyboardButton("🔄 Refresh (10k)", callback_data=f"refresh_{rarity}")])

    buttons.append([InlineKeyboardButton("🛒 Buy", callback_data=f"buy_{char_id}_{price}")])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="open_shop")])

    try:
        await query.message.delete()
    except Exception:
        pass

    if 'send_character_media' in globals():
        await update.message.reply_text(
            bot=context.bot,
            chat_id=update.effective_chat.id,
            image_url=image_url,
            caption=text,
            reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(buttons)
        )

# ==========================================
# 5. BUY CALLBACK (ക്യാരക്ടർ വാങ്ങൽ)
# ==========================================
async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # callback_data സ്പ്ലിറ്റ് ചെയ്ത് ഡാറ്റ വേർതിരിക്കുന്നു
    try:
        # ഡാറ്റ ഫോർമാറ്റ്: buy_charid_price (ഉദാഹരണത്തിന്: buy_01_15000)
        parts = query.data.split("_")
        char_id = parts[1]
        price = int(parts[2])
    except Exception:
        return await query.answer("❌ Invalid request", show_alert=True)

    user = query.from_user
    db_file = DB_NAME

    conn = db_connect(db_file)
    cursor = conn.cursor()

    cursor.execute("SELECT balance FROM users WHERE user_id=?", (user.id,))
    bal = cursor.fetchone()

    if not bal or bal[0] < price:
        conn.close()
        return await query.answer("❌ Not enough coins to purchase!", show_alert=True)

    cursor.execute("SELECT name, anime, rarity FROM characters WHERE id=?", (char_id,))
    char = cursor.fetchone()

    if not char:
        conn.close()
        return await query.answer("❌ Character not found in database!", show_alert=True)

    name, anime, rarity = char

    # പണം കുറയ്ക്കുകയും കളക്ഷനിലേക്ക് ആഡ് ചെയ്യുകയും ചെയ്യുന്നു (ON CONFLICT ഉണ്ടെങ്കിൽ കൗണ്ട് കൂട്ടും)
    cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (price, user.id))
    cursor.execute("""
        INSERT INTO user_collection (user_id, character_id, count)
        VALUES (?, ?, 1)
        ON CONFLICT(user_id, character_id)
        DO UPDATE SET count = count + 1
    """, (user.id, char_id))

    conn.commit()
    conn.close()

    text = (
        f"✅ <b>PURCHASE SUCCESSFUL</b>\n\n"
        f"<blockquote>"
        f"👤 {user.mention_html()}\n"
        f"🎴 <b>Character:</b> {name}\n"
        f"⭐ <b>Rarity:</b> {rarity}\n"
        f"💰 <b>Spent:</b> {price:,} Coins\n"
        f"</blockquote>"
    )

    try:
        await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML)
    except Exception:
        await query.message.edit_text(text=text, parse_mode=ParseMode.HTML)


# ==========================================
# 1. /TOP COMMAND (മെയിൻ കമാൻഡ്)
# ==========================================
async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ആദ്യ കോഡിലെ ബാൻ ചെക്ക് ഇവിടെ നിലനിർത്തിയിരിക്കുന്നു
    if 'check_ban' in globals() and await check_ban(update):
        return

    text = (
        "🏆 <b>SUMMON WORLD LEADERBOARD</b> 🏆\n\n"
        "<blockquote>🔮 Check out the strongest summoners in the system!</blockquote>"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✨ Character Top", callback_data="top_char"),
            InlineKeyboardButton("💰 Money Top", callback_data="top_money")
        ],
        [
            InlineKeyboardButton("💬 Group Top", callback_data="top_group")
        ]
    ])

    # TOP_IMAGE ഗ്ലോബൽ വേരിയബിൾ ഉണ്ടെങ്കിൽ അത് എടുക്കും, ഇല്ലെങ്കിൽ ടെക്സ്റ്റ് അയക്കും
    top_img = TOP_IMAGE if 'TOP_IMAGE' in globals() else None

    if top_img:
        try:
            return await update.message.reply_photo(
                photo=top_img,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )
        except Exception:
            pass
            
    await update.message.reply_text(
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )

# ==========================================
# 2. TOP CALLBACK HANDLER (ഡാറ്റ കാണിക്കുന്ന ഭാഗം)
# ==========================================
async def top_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # തിരിച്ചു പോകാനുള്ള ബട്ടൺ അമർത്തുമ്പോൾ
    if data == "top_back":
        return await top_back_handler(update, context)

    db_file = DB_NAME
    conn = db_connect(db_file)
    cursor = conn.cursor()

    text = ""
    
    # 💰 MONEY TOP
    if data == "top_money":
        cursor.execute("""
            SELECT user_id, username, balance
            FROM users
            ORDER BY balance DESC
            LIMIT 10
        """)
        rows = cursor.fetchall()
        text = "🏆 <b>GLOBAL MONEY LEADERBOARD</b> 💰\n\n<blockquote>"
        for i, (user_id, username, balance) in enumerate(rows, 1):
            name = f"@{username}" if username else f"<a href='tg://user?id={user_id}'>User</a>"
            text += f"{i}. {name} — <b>{balance:,} Coins</b>\n"
        text += "</blockquote>"

    # 🔮 CHARACTER TOP
    elif data == "top_char":
        cursor.execute("""
            SELECT u.user_id, u.username, COUNT(uc.character_id)
            FROM users u
            JOIN user_collection uc ON u.user_id = uc.user_id
            GROUP BY u.user_id
            ORDER BY COUNT(uc.character_id) DESC
            LIMIT 10
        """)
        rows = cursor.fetchall()
        text = "🏆 <b>Global character leaderboard</b> 🔮\n\n<blockquote>"
        for i, (user_id, username, count) in enumerate(rows, 1):
            name = f"@{username}" if username else f"<a href='tg://user?id={user_id}'>User</a>"
            text += f"{i}. {name} — <b>{count} Characters</b>\n"
        text += "</blockquote>"

    # 💬 GROUP TOP
    elif data == "top_group":
        cursor.execute("""
            SELECT user_id, username, balance
            FROM users
            ORDER BY balance DESC
            LIMIT 10
        """)
        rows = cursor.fetchall()
        text = "🏆 <b>Group leaderboards</b> 💬\n\n<blockquote>"
        for i, (user_id, username, balance) in enumerate(rows, 1):
            name = f"@{username}" if username else f"<a href='tg://user?id={user_id}'>User</a>"
            text += f"{i}. {name} — <b>{balance:,} Coins</b>\n"
        text += "</blockquote>"

    conn.close()

    back_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="top_back")]])

    try:
        await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=back_keyboard)
    except Exception:
        await query.message.edit_text(text=text, parse_mode=ParseMode.HTML, reply_markup=back_keyboard)

# ==========================================
# 3. TOP BACK HANDLER (തിരിച്ചു മെയിൻ പേജിലേക്ക്)
# ==========================================
async def top_back_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    text = (
        "🏆 <b>Summon leaderboards</b> 🏆\n\n"
        "<blockquote>🔮 Choose a category below!</blockquote>"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✨ Character Top", callback_data="top_char"),
            InlineKeyboardButton("💰 Money Top", callback_data="top_money")
        ],
        [
            InlineKeyboardButton("💬 Group Top", callback_data="top_group")
        ]
    ])

    try:
        await query.message.edit_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    except Exception:
        await query.message.edit_text(text=text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

# ==========================
# /STREAK
# ==========================
async def streak_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update):
        return
    user = update.effective_user
    user_id = user.id
    check_and_register_user(user_id, user.username, user.first_name)
    streak = get_streak(user_id)
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now()

    # Case 1: പുതിയ സ്ട്രീക്ക് തുടങ്ങുമ്പോൾ
    if not streak:
        update_streak(user_id, 1, today, 1)
        bonus = STREAK_BONUS_TIERS.get(1, 500)
        add_balance(user_id, bonus)
        
        text = (
            "🔥 <b>STREAK STARTED!</b>\n\n"
            "<blockquote>"
            "📅 Current Streak: 1 Day\n"
            f"💰 Daily Bonus: +{bonus:,} Coins"
            "</blockquote>"
        )
        return await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    streak_count, last_date, highest = streak[0], streak[1], streak[2]

    # Case 2: ഇന്ന് ഓൾറെഡി ക്ലെയിം ചെയ്തതാണെങ്കിൽ
    if last_date and last_date.startswith(today):
        text = (
            "🔥 <b>STREAK STATUS</b>\n\n"
            "<blockquote>"
            f"📅 Current: {streak_count} Days\n"
            f"🏆 Highest: {highest or streak_count} Days\n\n"
            "✨ You have already claimed today's bonus! Come back tomorrow."
            "</blockquote>"
        )
        return await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    # Case 3: പുതിയ ദിവസം ക്ലെയിം ചെയ്യുമ്പോൾ (or reset)
    if last_date:
        try:
            last_dt = datetime.strptime(last_date, "%Y-%m-%d")
            days_diff = (now.date() - last_dt.date()).days
            new_count = streak_count + 1 if days_diff <= STREAK_RESET_DAYS else 1
        except Exception:
            new_count = 1
    else:
        new_count = 1

    new_highest = max(highest or 0, new_count)
    bonus = STREAK_BONUS_TIERS.get(new_count if new_count <= 7 else 1, 500)
    update_streak(user_id, new_count, today, new_highest)
    add_balance(user_id, bonus)
    
    # Reset ആയോ അതോ സ്ട്രീക്ക് കൂടിയോ എന്ന് നോക്കുന്നു
    status_title = "STREAK UPDATED!" if new_count > 1 else "STREAK RESET! 😭"
    
    text = (
        f"🔥 <b>{status_title}</b>\n\n"
        "<blockquote>"
        f"📅 Current Streak: {new_count} Days\n"
        f"🏆 Highest Streak: {new_highest} Days\n"
        f"💰 Reward: +{bonus:,} Coins"
        "</blockquote>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# 2️⃣ STREAK CALLBACK (POPUP ALERT)
async def streak_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user_id = q.from_user.id
    streak = get_streak(user_id)
    
    if not streak:
        return await q.answer("❌ You don't have an active streak yet!", show_alert=True)
        
    # Screen-ൽ മനോഹരമായ ഒരു പോപ്പ്അപ്പ് വിൻഡോ കാണിക്കുന്നു
    alert_text = (
        "⌜ Your Daily Streak ⌟ 🔥\n\n"
        f"📅 Current: {streak[0]} Days\n"
        f"🏆 Highest: {streak[2] or streak[0]} Days"
    )
    await q.answer(alert_text, show_alert=True)

# ==========================
# /ACHIEVEMENTS
# ==========================
async def achievements_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update):
        return
    user = update.effective_user
    user_id = user.id
    check_and_register_user(user_id, user.username, user.first_name)

    char_count = get_user_unique_count(user_id)
    bal = get_balance(user_id)
    streak = get_streak(user_id)
    streak_count = streak[0] if streak else 0

    # 1️⃣ Character Collection Achievements Check
    for ach_id, threshold in [("first_char", 1), ("collector_5", 5), ("collector_10", 10),
                              ("collector_25", 25), ("collector_50", 50), ("collector_100", 100)]:
        if char_count >= threshold and not has_achievement(user_id, ach_id):
            unlock_achievement(user_id, ach_id)

    # 2️⃣ Balance Achievements Check
    for ach_id, threshold in [("rich_1k", 1000), ("rich_10k", 10000), ("rich_100k", 100000)]:
        if bal >= threshold and not has_achievement(user_id, ach_id):
            unlock_achievement(user_id, ach_id)

    # 3️⃣ Streak Achievements Check
    for ach_id, threshold in [("streak_3", 3), ("streak_7", 7), ("streak_30", 30)]:
        if streak_count >= threshold and not has_achievement(user_id, ach_id):
            unlock_achievement(user_id, ach_id)

    # Fetch all unlocked achievements for the user
    unlocked = [a[0] for a in fetch_all("SELECT achievement_id FROM user_achievements WHERE user_id = ?", (user_id,))]

    # 🎯 FIX: കറക്റ്റ് HTML ടാഗുകളും blockquote ലേഔട്ടും
    text = (
        "🏅 <b>YOUR ACHIEVEMENTS</b>\n\n"
        f"📊 <b>Progress:</b> <code>{len(unlocked)}/{len(ACHIEVEMENTS)}</code> Unlocked\n\n"
    )

    # ഓരോ അച്ചീവ്‌മെന്റും ഭംഗിയുള്ള ഒരു ലിസ്റ്റ് ആക്കുന്നു
    for ach_id, ach in ACHIEVEMENTS.items():
        status = "✅" if ach_id in unlocked else "🔒"
        text += (
            f"{status} <b>{ach['name']}</b>\n"
            f"<blockquote><i>{ach['desc']}</i></blockquote>\n"
        )

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# ==========================
# /STATS
# ==========================
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update):
        return

    # 🤫 ഓണർ ഐഡി അല്ലെങ്കിൽ ബോട്ട് ഒന്നും മിണ്ടാതെ കമാൻഡ് നിർത്തും (Silent)
    if update.effective_user.id != OWNER_ID:
        return

    text = (
        "📊 <b>SERVER STATS</b>\n\n"
        "<blockquote>"
        f"👥 Users: {get_total_users():,}\n"
        f"💰 Total Coins: {get_total_coins():,}\n"
        f"🎴 Chars: {get_character_count():,}\n"
        f"💬 Groups: {get_total_groups():,}"
        "</blockquote>\n"
        f"⏳ <b>Uptime:</b> {get_uptime()}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# ==========================
# /MARKET
# ==========================
async def cshop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update):
        return
    user = update.effective_user
    user_id = user.id
    check_and_register_user(user_id, user.username, user.first_name)

    pool = get_market_pool()
    if not pool:
        clear_market_pool()
        all_chars = fetch_all("SELECT id, name, anime, rarity, image_url FROM characters ORDER BY RANDOM() LIMIT ?", (MARKET_POOL_SIZE,))
        for c in all_chars:
            add_to_market_pool(c[0])
        pool = all_chars

    bal = get_balance(user_id)
    text = f"🛒 <b>MARKET</b>\n💰 <b>Balance:</b> <code>{bal:,}</code> coins\n\n<blockquote>"
    buttons = []
    for char_id, name, anime, rarity, image_url in pool:
        price = int(PRICE.get(rarity, 15000) * 1.2)
        text += f"• {name} ({rarity}) — <code>{price:,}</code>\n"
        buttons.append([InlineKeyboardButton(f"🛒 Buy {name[:15]}", callback_data=f"market_buy_{char_id}_{price}")])
    text += "</blockquote>"
    
    buttons.append([InlineKeyboardButton(f"🔄 Refresh ({MARKET_REFRESH_PRICE:,})", callback_data="market_refresh")])
    buttons.append([InlineKeyboardButton("💰 Sell Menu", callback_data="market_sell_menu")])
    
    # parse_mode ചേർത്തു, update.message.reply_text എറർ മാറ്റി
    await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons))


async def cshop_callback(update, context):
    q = update.callback_query
    user_id = q.from_user.id
    data = q.data

    if data == "market_refresh":
        if not remove_balance(user_id, MARKET_REFRESH_PRICE):
            return await q.answer("❌ You don't have enough coins to refresh!", show_alert=True)
        clear_market_pool()
        all_chars = fetch_all("SELECT id, name, anime, rarity, image_url FROM characters ORDER BY RANDOM() LIMIT ?", (MARKET_POOL_SIZE,))
        for c in all_chars:
            add_to_market_pool(c[0])
        await q.answer("✅ Market Refreshed!")
        return await cshop(update, context)

    if data == "market_sell_menu":
        rows = get_user_collection(user_id)
        if not rows:
            return await q.answer("❌ Your harem is empty! Nothing to sell.", show_alert=True)
        text = "💰 <b>SELL CHARACTERS</b>\n\n"
        buttons = []
        for cid, name, anime, rarity, image_url, count in rows[:15]:
            price = int(PRICE.get(rarity, 15000) * MARKET_SELL_BACK_PERCENT / 100)
            text += f"• {name} — <code>{price:,}</code> coins\n"
            buttons.append([InlineKeyboardButton(f"💰 Sell {name[:15]}", callback_data=f"market_sell_{cid}")])
            
        try:
            await q.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons))
        except Exception:
            await q.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons))
        return

    if data.startswith("market_buy_"):
        parts = data.replace("market_buy_", "").split("_")
        char_id = parts[0]
        price = int(parts[1]) if len(parts) > 1 else 0
        if owns_character(user_id, char_id):
            return await q.answer("❌ You already own this character!", show_alert=True)
        if not remove_balance(user_id, price):
            return await q.answer("❌ Insufficient balance to buy this!", show_alert=True)
            
        add_to_collection(user_id, char_id)
        remove_from_market_pool(char_id)
        log_market_transaction(user_id, char_id, "buy", price)
        await q.answer("✅ Purchase Successful!")
        return await cshop(update, context)

    if data.startswith("market_sell_"):
        char_id = data.replace("market_sell_", "")
        if not owns_character(user_id, char_id):
            return await q.answer("❌ You don't own this character anymore!", show_alert=True)
            
        char = get_character(char_id)
        price = int(PRICE.get(char[3], 15000) * MARKET_SELL_BACK_PERCENT / 100)
        remove_from_collection(user_id, char_id)
        add_balance(user_id, price)
        log_market_transaction(user_id, char_id, "sell", price)
        await q.answer(f"💰 Sold for +{price:,} coins!")
        return await cshop(update, context)

async def sell_command(update, context):
    if await check_ban(update):
        return
    if not context.args:
        return await update.message.reply_text("💡 <b>Use:</b> <code>/sell [character_id]</code>", parse_mode=ParseMode.HTML)
        
    user_id = update.effective_user.id
    cid = context.args[0]
    
    if not owns_character(user_id, cid):
        return await update.message.reply_text("❌ <b>Not Owned!</b>\nYou don't own this character in your collection.", parse_mode=ParseMode.HTML)
        
    char = get_character(cid)
    if not char:
        return await update.message.reply_text("❌ <b>Character Not Found!</b>", parse_mode=ParseMode.HTML)
        
    # char[3] എന്നത് റാരിറ്റി (Rarity) ആണ്
    price = int(PRICE.get(char[3], 15000) * MARKET_SELL_BACK_PERCENT / 100)
    
    # കളക്ഷനിൽ നിന്ന് മാറ്റുന്നു, ബാലൻസ് ആഡ് ചെയ്യുന്നു
    remove_from_collection(user_id, cid)
    add_balance(user_id, price)
    log_market_transaction(user_id, cid, "sell", price)
    
    # കാണിക്കേണ്ട ക്യാപ്ഷൻ ടെക്സ്റ്റ് (char[1] എന്നത് കാരക്ടറിന്റെ പേര്)
    caption_text = (
        f"💰 <b>CHARACTER SOLD!</b> 💰\n\n"
        f"<blockquote>👤 <b>Seller:</b> {update.effective_user.mention_html()}\n"
        f"🎴 <b>Character:</b> {char[1]} (ID: {cid})\n"
        f"💵 <b>Earned:</b> +{price:,} coins</blockquote>\n"
        f"✨ Successfully removed from your /harem."
    )
    
    image_url = char[4] if len(char) > 4 else None
    await send_character_media(
        context.bot,
        update.effective_chat.id,
        image_url,
        caption_text,
    )

# ==========================
# /PROFILE
# ==========================
async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update):
        return
    user = update.effective_user
    user_id = user.id
    check_and_register_user(user_id, user.username, user.first_name)

    bal = get_balance(user_id)
    char_count = get_user_unique_count(user_id)
    fav = fetch_one("SELECT favorite FROM users WHERE user_id = ?", (user_id,))
    fav_char = get_character(fav[0]) if fav and fav[0] else None

    streak = get_streak(user_id)
    streak_count = streak[0] if streak else 0
    highest = streak[2] if streak else 0

    pref = get_user_pref(user_id)
    glow = pref[2] if pref and pref[2] is not None else 1

    fav_name = fav_char[1] if fav_char else "None"
    fav_rarity = fav_char[3] if fav_char else "—"

    # 🎯 FIX: കറക്റ്റ് HTML ടാഗുകളും അടിപൊളി ലേഔട്ടും
    text = (
        f"👤 <b>USER PROFILE</b>\n\n"
        f"<blockquote>"
        f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
        f"💰 <b>Balance:</b> {bal:,} Coins\n"
        f"🎴 <b>Characters:</b> {char_count}\n"
        f"💖 <b>Favorite:</b> {fav_name} ({fav_rarity})\n"
        f"🔥 <b>Streak:</b> {streak_count} Days (Max: {highest})\n"
        f"💫 <b>Glow Status:</b> {'🟢 ON' if glow else '🔴 OFF'}"
        f"</blockquote>"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💫 Toggle Glow", callback_data="profile_toggle_glow")],
        [InlineKeyboardButton("🎛 HMode Menu", callback_data="hmode_menu")],
    ])
    
    # FIX: reply_text-ൽ നിന്നും തെറ്റായ 'update' ആർഗ്യുമെന്റ് ഒഴിവാക്കി, parse_mode ചേർത്തു
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


async def profile_glow_toggle(update, context):
    q = update.callback_query
    new_state = toggle_profile_glow(q.from_user.id)
    # ബട്ടൺ ഞെക്കുമ്പോൾ പോപ്പ്അപ്പ് അലേർട്ട് ആയി പുതിയ സ്റ്റേറ്റ് കാണിക്കും
    await q.answer(f"💫 Glow: {'ON' if new_state else 'OFF'}", show_alert=True)


async def profile_hmode_callback(update, context):
    # ഹാൻഡ്‌ലറുകൾ തമ്മിൽ ശരിയായി വർക്ക് ചെയ്യാൻ callback_query-ക്കും മറുപടി നൽകുന്നു
    q = update.callback_query
    await q.answer()
    return await hmode_command(update, context)



# ==========================
# /HMODE COMMAND & CALLBACKS
# ==========================
async def hmode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_ban(update):
        return
        
    user = update.effective_user
    user_id = user.id
    check_and_register_user(user_id, user.username, user.first_name)

    # 1️⃣ മെയിൻ മോഡുകൾ (Rarity ഞെക്കിയാൽ സബ് മെനുവിലേക്ക് പോകും)
    modes = [
        ("anime", "🎌 Anime"), 
        ("rarity_menu", "⭐ Rarity"), # This triggers the rarity sub-menu
        ("recent", "🆕 Recent"), 
        ("fav", "❤️ Fav")
    ]
    
    pref = get_user_pref(user_id)
    current = pref[1] if pref else "anime"

    # കറന്റ് മോഡ് ഏതാണോ അതിന് നേരെ ✅ കാണിക്കും
    keyboard = []
    for mode_id, mode_name in modes:
        if mode_id == "rarity_menu":
            # Rarity-യുടെ മെയിൻ ബട്ടൺ (നിലവിൽ ഏതെങ്കിലും നിർദ്ദിഷ്ട റാരിറ്റി ആണെങ്കിൽ അത് കാണിക്കും)
            is_rarity_active = current not in ["anime", "recent", "fav"]
            status = "✅" if is_rarity_active else "⚪"
            keyboard.append([InlineKeyboardButton(f"{status} {mode_name} ➡️", callback_data="hmode_show_rarities")])
        else:
            status = "✅" if mode_id == current else "⚪"
            keyboard.append([InlineKeyboardButton(f"{status} {mode_name}", callback_data=f"hmode_set_{mode_id}")])

    # പ്രൊഫൈലിലേക്ക് തിരിച്ചു പോകാൻ ഒരു ബാക്ക് ബട്ടൺ
    keyboard.append([InlineKeyboardButton("⬅️ Back to Profile", callback_data="profile_back")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = (
        "🎛 <b>COLLECTION DISPLAY MODE (HMODE)</b>\n\n"
        "Select how you want to sort and view your characters in collection:\n\n"
        f"📊 Current Mode: <code>{current.upper()}</code>"
    )

    if update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


async def hmode_show_rarities_callback(update, context):
    """DB-ൽ ഉള്ള മുഴുവൻ റാരിറ്റികളും ബട്ടണുകളായി കാണിക്കുന്ന സബ് മെനു"""
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id

    pref = get_user_pref(user_id)
    current_mode = pref[1] if pref else "anime"

    # 2️⃣ ഡാറ്റാബേസിൽ നിന്നും നിലവിലുള്ള എല്ലാ തരം റാരിറ്റികളും എടുക്കുന്നു (Duplicates ഒഴിവാക്കി)
    try:
        conn = db_connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT rarity FROM characters WHERE rarity IS NOT NULL AND rarity != ''")
        rarities = [row[0] for row in cursor.fetchall()]
        conn.close()
    except Exception as e:
        logger.error(f"Error fetching rarities for hmode: {e}")
        rarities = ["Common", "Rare", "Legendary"] # Fallback if DB fails

    keyboard = []
    # ഓരോ റാരിറ്റിക്കും ഓരോ ബട്ടൺ വീതം (ഗ്രിഡ് ലേഔട്ട് വേണമെങ്കിൽ രണ്ട് ബട്ടൺ വീതം വെക്കാം)
    for rarity in rarities:
        status = "✅" if current_mode.lower() == rarity.lower() else "⚪"
        keyboard.append([InlineKeyboardButton(f"{status} {rarity}", callback_data=f"hmode_set_rarity_{rarity.lower()}")])

    # മെയിൻ എച്ച്മോഡ് മെനുവിലേക്ക് തിരിച്ചു പോകാൻ ഒരു ബാക്ക് ബട്ടൺ
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="hmode_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await q.message.edit_text(
        "⭐ <b>SELECT RARITY FILTER</b>\n\n"
        "Choose a specific rarity to display only those characters in your collection:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )


async def hmode_set_callback(update, context):
    """യൂസർ സെലക്ട് ചെയ്ത മോഡ് (Anime, Recent, Fav അല്ലെങ്കിൽ പ്രത്യേക Rarity) സേവ് ചെയ്യുന്ന ഫങ്ഷൻ"""
    q = update.callback_query
    callback_data = q.data

    if callback_data.startswith("hmode_set_rarity_"):
        # പ്രത്യേക ഒരു റാരിറ്റി ആണ് സെലക്ട് ചെയ്തതെങ്കിൽ (eg: hmode_set_rarity_legendary)
        mode = callback_data.replace("hmode_set_rarity_", "")
    else:
        # ജനറൽ മോഡുകൾ ആണെങ്കിൽ (Anime, Recent, Fav)
        mode = callback_data.replace("hmode_set_", "")

    # യൂസറുടെ പ്രെഫറൻസ് ഡാറ്റാബേസിലേക്ക് അപ്ഡേറ്റ് ചെയ്യുന്നു
    set_collection_mode(q.from_user.id, mode)
    
    # Screen-ൽ മനോഹരമായ ഒരു പോപ്പ്അപ്പ് വിൻഡോ കാണിക്കുന്നു
    await q.answer(f"✅ Collection Mode: {mode.upper()}", show_alert=True)
    
    # മെയിൻ എച്ച്മോഡ് മെനുവിലേക്ക് തന്നെ യൂസറെ തിരിച്ചു കൊണ്ടുപോകുന്നു (അപ്പൊൾ ✅ മാറിയിട്ടുണ്ടാകും)
    return await hmode_command(update, context)

# ==========================================
# 🎨 /FONT COMMAND
# ==========================================
async def font_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'check_ban' in globals() and await check_ban(update):
        return
        
    user = update.effective_user
    user_id = user.id
    
    if 'check_and_register_user' in globals():
        check_and_register_user(user_id, user.username, user.first_name)

    # FONT_MAPS നിങ്ങളുടെ ഗ്ലോബൽ ഡിക്ഷണറി ആയിരിക്കണം (e.g., FONT_MAPS = ["mono", "fraktur", "script", "double"])
    allowed_fonts = FONT_MAPS if 'FONT_MAPS' in globals() else ["mono", "fraktur", "script", "double"]

    # യൂസർ ആർഗ്യുമെന്റ് ഒന്നും നൽകിയിട്ടില്ലെങ്കിൽ ഇൻലൈൻ മെനു കാണിക്കുന്നു
    if not context.args:
        text = (
            "🎨 <b>CUSTOM FONT STYLES</b>\n\n"
            "<blockquote>"
            "✨ Select your preferred custom text font from the buttons below or use the command:\n\n"
            "📌 <code>/font [style_name]</code>\n\n"
            "<b>Available Fonts:</b>\n"
            "• <code>mono</code>\n"
            "• <code>fraktur</code>\n"
            "• <code>script</code>\n"
            "• <code>double</code>"
            "</blockquote>"
        )
        
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Mono", callback_data="font_set_mono"), 
                InlineKeyboardButton("Fraktur", callback_data="font_set_fraktur")
            ],
            [
                InlineKeyboardButton("Script", callback_data="font_set_script"), 
                InlineKeyboardButton("Double", callback_data="font_set_double")
            ]
        ])
        
        try:
            if 'send' in globals():
                return await update.message.reply_text(update, text, reply_markup=kb)
            else:
                return await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            return

    # /font mono എന്നിങ്ങനെ ടൈപ്പ് ചെയ്ത് മാറ്റാൻ നോക്കുമ്പോൾ
    font = context.args[0].lower()
    if font not in allowed_fonts:
        error_text = "❌ <b>Unknown Font Style!</b>\n\nChoose from: <code>mono, fraktur, script, double</code>"
        if 'send' in globals():
            return await update.message.reply_text(update, error_text)
        else:
            return await update.message.reply_text(error_text, parse_mode=ParseMode.HTML)

    if 'set_font_pref' in globals():
        set_font_pref(user_id, font)
        
    success_text = f"✅ <b>Font preference successfully updated to:</b> <code>{font.upper()}</code>"
    if 'send' in globals():
        await update.message.reply_text(update, success_text)
    else:
        await update.message.reply_text(success_text, parse_mode=ParseMode.HTML)


# ==========================================
# 🎯 FONT CALLBACK HANDLER
# ==========================================
async def font_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    font = query.data.replace("font_set_", "")
    allowed_fonts = FONT_MAPS if 'FONT_MAPS' in globals() else ["mono", "fraktur", "script", "double"]
    
    if font not in allowed_fonts:
        return await query.answer("❌ Invalid Font Style!", show_alert=True)
        
    if 'set_font_pref' in globals():
        set_font_pref(query.from_user.id, font)
        
    text = f"✅ <b>Font preference successfully updated to:</b> <code>{font.upper()}</code>"
    
    try:
        await query.message.edit_text(text, parse_mode=ParseMode.HTML)
    except Exception:
        await query.message.reply_text(text, parse_mode=ParseMode.HTML)
