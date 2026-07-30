import sqlite3
import random
import re
from datetime import datetime, timedelta
from collections import defaultdict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.constants import ParseMode

DB = "summon.db"
DB_NAME = "summon.db"  
OWNER_ID = 6265999542  

# ==================== ITEM CATALOG ====================
ITEMS = {
    "bomb":    {"name": "💣 Bomb",         "cost": 100000, "max": 1,  "desc": "Steal random char from /harem"},
    "lucky":   {"name": "🎟️ Lucky Ticket", "cost": 15000,  "max": 5,  "desc": "+rarity chance (5 summons)"},
    "skip":    {"name": "⏰ Skip Cooldown", "cost": 25000,   "max": 10, "desc": "Skip cooldown or activate shields"},
    "magnet":  {"name": "💰 Coin Magnet",   "cost": 10000,  "max": 5,  "desc": "+2,000 bonus on /daily"},
    "sshield": {"name": "🔒 Steal Shield",  "cost": 8000,   "max": 5,  "desc": "Block 5 incoming /steal"},
    "bshield": {"name": "🛡️ Bomb Shield",   "cost": 9000,   "max": 3,  "desc": "Block 3 incoming /bomb"},
    "xp":      {"name": "⚡ XP Boost",      "cost": 12000,  "max": 5,  "desc": "2× rewards (5 summons)"},
}

COOLDOWN_BOMB = 24 * 3600
COOLDOWN_STEAL = 3600
HCLAIM_COOLDOWN_HOURS = 24

# 🚫 Anti-Spam Detector
user_spam_counter = defaultdict(list)

# ഹൈ-റാരിറ്റി ലിസ്റ്റ് (പ്രീമിയം ബൂസ്റ്റിന് വേണ്ടി)
HIGH_RARITIES = ["legendary", "mythic", "celestial", "luxury", "limited", "special", "event"]

RARITY_EMOJI = {
    "common": "⚪", "rare": "🔵", "special": "💮", "legendary": "⭐",
    "mythic": "🛸", "valentine": "💝", "summer": "🏖️", "rainy": "🌧️",
    "halloween": "🎃", "christmas": "🎄", "winter": "❄️", "new year": "🎇",
    "festival": "🎍", "amv": "🎥", "event": "🎉", "celestial": "🌌",
    "luxury": "💎", "limited": "🔮",
}

def rarity_emoji(r):
    if not r: return "⚪"
    rt = r.lower()
    for k, e in RARITY_EMOJI.items():
        if k in rt: return e
    return "⚪"

def fmt(n):
    try: return f"{int(n):,}"
    except: return str(n)

def get_conn():
    return sqlite3.connect(DB)

# ==================== DB HELPERS ====================
def is_premium(user_id):
    conn = get_conn()
    row = conn.execute("""
        SELECT 1 FROM premium
        WHERE user_id=? AND expires_at > datetime('now')
    """, (user_id,)).fetchone()
    conn.close()
    return bool(row)

def premium_left(user_id):
    conn = get_conn()
    row = conn.execute("""
        SELECT CAST((julianday(expires_at) - julianday('now')) * 24 AS INT)
        FROM premium
        WHERE user_id=? AND expires_at > datetime('now')
    """, (user_id,)).fetchone()
    conn.close()
    return row[0] if row else 0

def cooldown_left(user_id, command):
    conn = get_conn()
    row = conn.execute("""
        SELECT last_used FROM cooldowns WHERE user_id=? AND command=?
    """, (user_id, command)).fetchone()
    conn.close()
    if not row: return 0
    try:
        last = datetime.fromisoformat(row[0].replace(" ", "T"))
        cd_secs = COOLDOWN_BOMB if command == "bomb" else COOLDOWN_STEAL
        elapsed = (datetime.utcnow() - last).total_seconds()
        return max(0, int(cd_secs - elapsed))
    except Exception:
        return 0

def set_cooldown(user_id, command):
    conn = get_conn()
    conn.execute("""
        INSERT INTO cooldowns (user_id, command, last_used)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(user_id, command) DO UPDATE SET last_used=datetime('now')
    """, (user_id, command))
    conn.commit()
    conn.close()

def get_target(update, context):
    if update.message.reply_to_message:
        target = update.message.reply_to_message.from_user
        return target.id, target.first_name, update.message.reply_to_message.message_id

    if context.args:
        arg = context.args[0].lstrip("@")
        if arg.isdigit():
            conn = get_conn()
            row = conn.execute("SELECT first_name FROM users WHERE user_id=?", (int(arg),)).fetchone()
            conn.close()
            name = row[0] if row else f"user_{arg}"
            return int(arg), name, None
        else:
            conn = get_conn()
            row = conn.execute(
                "SELECT user_id, first_name FROM users WHERE username=?",
                (arg,)).fetchone()
            conn.close()
            if row:
                return row[0], row[1], None
            return None, arg, None

    return None, None, None

def get_random_character_by_rarity_id(rarity_id: int):
    conn = get_conn()
    # claim_list-ൽ നിന്ന് റാരിറ്റിയുടെ പേര് എടുക്കുന്നു
    rn = conn.execute("SELECT rarity_name FROM claim_list WHERE rarity_id = ?", (rarity_id,)).fetchone()
    if not rn:
        conn.close()
        return None
    
    # LIKE ഉപയോഗിച്ച് Case-Insensitive ആക്കുന്നു (ചെറിയ അക്ഷരവും വലിയ അക്ഷരവും ഒരുപോലെ നോക്കും)
    char = conn.execute("""
        SELECT id, name, anime, rarity, msg_id 
        FROM characters 
        WHERE rarity LIKE ? 
        ORDER BY RANDOM() LIMIT 1
    """, (rn[0],)).fetchone()
    
    conn.close()
    return char

# ==================== 🏪 /market ====================
async def market_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    prem = is_premium(user_id)

    conn = get_conn()
    cur = conn.cursor()
    balance = 0
    r = cur.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()
    if r: balance = r[0]

    owned = {}
    for iid in ITEMS:
        r = cur.execute("""
            SELECT COALESCE(SUM(uses_remaining),0)
            FROM user_inventory
            WHERE user_id=? AND item_id=? AND expires_at>datetime('now')
        """, (user_id, iid)).fetchone()
        owned[iid] = r[0] if r else 0
    conn.close()

    text = f"🏪 <b>SUMMON BOT MARKET</b>\n"
    text += f"💰 <b>Your Balance:</b> <code>{fmt(balance)}</code> coins\n"
    if prem:
        text += f"👑 <b>Premium Mode Active:</b> All items are FREE!\n"
    text += "\n─── 🛒 <b>ITEMS AVAILABLE</b> ───\n"

    kb = []
    for iid, it in ITEMS.items():
        cost_str = "Free ✨" if prem else f"{fmt(it['cost'])} coins"
        text += f"\n{it['name']} — <b>{cost_str}</b> (Max: {it['max']})\n"
        text += f"<blockquote>{it['desc']}\n🛍️ <i>Owned: {owned[iid]}/{it['max']}</i></blockquote>"

        kb.append([InlineKeyboardButton(f"💰 {it['name']} ({cost_str})", callback_data=f"mi:{iid}")])

    await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))

async def market_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data == "m_inv":
        await inv_via_query(q, context)
    elif data == "m_back":
        await rerender_market(q, context)
    elif data.startswith("mi:"):
        await buy_item(q, context, data.split(":", 1)[1])

async def buy_item(q, context, item_id):
    if item_id not in ITEMS:
        await q.answer("❌ Unknown item", show_alert=True)
        return
    it = ITEMS[item_id]
    user_id = q.from_user.id
    prem = is_premium(user_id)
    cost = 0 if prem else it["cost"]

    conn = get_conn()
    cur = conn.cursor()
    if cost > 0:
        r = cur.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not r or r[0] < cost:
            conn.close()
            await q.answer(f"❌ You need {fmt(cost)} coins!", show_alert=True)
            return

    owned = cur.execute("""
        SELECT COALESCE(SUM(uses_remaining),0)
        FROM user_inventory
        WHERE user_id=? AND item_id=? AND expires_at>datetime('now')
    """, (user_id, item_id)).fetchone()[0] or 0

    if owned >= it["max"]:
        conn.close()
        await q.answer(f"❌ Purchase Limit reached ({it['max']})", show_alert=True)
        return

    cur.execute("""
        INSERT INTO user_inventory
        (user_id, item_id, uses_remaining, purchased_at, expires_at)
        VALUES (?, ?, ?, datetime('now'), datetime('now', '+24 hours'))
    """, (user_id, item_id, it["max"]))
    if cost > 0:
        cur.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (cost, user_id))
    conn.commit()
    conn.close()

    extra = " (Premium Offer)" if prem else f" (-{fmt(cost)} coins)"
    await q.answer(f"✅ Successfully bought {it['name']}{extra}!", show_alert=False)
    await rerender_market(q, context)

async def rerender_market(q, context):
    user_id = q.from_user.id
    prem = is_premium(user_id)

    conn = get_conn()
    cur = conn.cursor()
    balance = 0
    r = cur.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()
    if r: balance = r[0]
    owned = {}
    for iid in ITEMS:
        r = cur.execute("""
            SELECT COALESCE(SUM(uses_remaining),0)
            FROM user_inventory
            WHERE user_id=? AND item_id=? AND expires_at>datetime('now')
        """, (user_id, iid)).fetchone()
        owned[iid] = r[0] if r else 0
    conn.close()

    text = f"🏪 <b>SUMMON BOT MARKET</b>\n"
    text += f"💰 <b>Your Balance:</b> <code>{fmt(balance)}</code> coins\n"
    if prem:
        text += f"👑 <b>Premium Mode Active:</b> All items are FREE!\n"
    text += "\n─── 🛒 <b>ITEMS AVAILABLE</b> ───\n"

    kb = []
    for iid, it in ITEMS.items():
        cost_str = "Free ✨" if prem else f"{fmt(it['cost'])} coins"
        text += f"\n{it['name']} — <b>{cost_str}</b> (Max: {it['max']})\n"
        text += f"<blockquote>{it['desc']}\n🛍️ <i>Owned: {owned[iid]}/{it['max']}</i></blockquote>"
        kb.append([InlineKeyboardButton(f"💰 Buy {it['name']} ({cost_str})", callback_data=f"mi:{iid}")])

    try:
        await q.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
    except Exception:
        pass

# ==================== 🎒 /inv ====================
async def inv_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = build_inv_text(user_id)
    await update.message.reply_text(text, parse_mode="HTML")

async def inv_via_query(q, context):
    user_id = q.from_user.id
    text = build_inv_text(user_id)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🛒 Back to Market", callback_data="m_back")]])
    try:
        await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass

def build_inv_text(user_id):
    conn = get_conn()
    cur = conn.cursor()
    rows = cur.execute("""
        SELECT item_id, uses_remaining,
               CAST((julianday(expires_at) - julianday('now')) * 24 AS INT) as h
        FROM user_inventory
        WHERE user_id=? AND expires_at>datetime('now')
    """, (user_id,)).fetchall()
    coll = cur.execute("""
        SELECT COUNT(*), COUNT(DISTINCT character_id)
        FROM user_collection WHERE user_id=?
    """, (user_id,)).fetchone()
    total_copies = coll[0] or 0
    unique_chars = coll[1] or 0
    conn.close()

    prem = is_premium(user_id)
    hours_left = premium_left(user_id)

    text = "🎒 <b>YOUR INVENTORY & STATS</b>\n\n"
    if prem:
        if hours_left >= 24:
            d, h = divmod(hours_left, 24)
            text += f"👑 <b>Premium status:</b> <code>Active</code> ({d}d {h}h left)\n"
        else:
            text += f"👑 <b>Premium status:</b> <code>Active</code> ({hours_left}h left)\n"
    else:
        text += "⭐ <b>Premium status:</b> <code>Not Active</code> (Ask admin for /premium)\n"

    text += f"🎴 <b>Harem Size:</b> <code>{unique_chars}</code> unique / <code>{total_copies}</code> total copies\n"
    text += "\n─── 🎒 <b>OWNED BAG ITEMS</b> ───\n"

    if not rows:
        text += "\n<i>Your backpack is empty. Buy items from /market!</i>\n"
    else:
        for item_id, uses, h in rows:
            if item_id not in ITEMS: continue
            it = ITEMS[item_id]
            text += f"\n{it['name']} <b>x{uses}</b> (⌛ <code>{max(0,h)}h</code> left)\n"
            text += f"<blockquote>{it['desc']}</blockquote>"

    text += "\n\n💡 <i>Use <code>/bomb [reply/@user]</code> to attack (24h CD)</i>\n"
    text += f"💡 <i>Use <code>/skip [1/2/3]</code> to clear CD or load shields</i>\n"
    text += f"💡 <i>Use <code>/steal [reply/@user]</code> to loot coins (1h CD)</i>"
    return text

# ==================== 💖 /HCLAIM (WITH PREMIUM 2X CLAIMS & CHANCE+) ====================
async def hclaim_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    username = update.effective_user.username

    if 'check_ban' in globals() and await check_ban(update):
        return

    # Anti-Spam
    now_time = datetime.now()
    user_spam_counter[user_id] = [t for t in user_spam_counter[user_id] if now_time - t < timedelta(minutes=1)]
    user_spam_counter[user_id].append(now_time)

    if len(user_spam_counter[user_id]) > 10:
        conn = get_conn()
        conn.execute("INSERT OR REPLACE INTO banned_users (user_id, username) VALUES (?, ?)", (user_id, username))
        conn.commit()
        conn.close()
        return await update.message.reply_text(
            "🚨 <b>You have been BANNED for spamming /hclaim!</b>\n\n"
            "⚠️ <i>Reason: Triggered command more than 10 times in a minute.</i>",
            parse_mode=ParseMode.HTML
        )

    # Official Group Check
    if 'SUPPORT_GROUP_ID' in globals() and chat_id != SUPPORT_GROUP_ID:
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("💬 Join", url=globals().get('GROUP_LINK', "https://t.me/summon_official"))]])
        return await update.message.reply_text("👋 <b>Join our official group to claim characters!</b>", reply_markup=keyboard, parse_mode=ParseMode.HTML)

    prem = is_premium(user_id)
    max_claims = 2 if prem else 1

    conn = get_conn()
    cur = conn.cursor()

    # കോളം വെരിഫിക്കേഷൻ
    cur.execute("PRAGMA table_info(users)")
    cols = [c[1] for c in cur.fetchall()]
    if "last_hclaim" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN last_hclaim TEXT")
    if "last_hclaim_count" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN last_hclaim_count INTEGER DEFAULT 0")
    conn.commit()

    cur.execute("SELECT last_hclaim, last_hclaim_count FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    
    last_time_str, claim_count = (row[0], row[1]) if row else (None, 0)
    is_locked = False

    if last_time_str:
        last_time = datetime.strptime(last_time_str, "%Y-%m-%d %H:%M:%S")
        if now_time < last_time + timedelta(hours=HCLAIM_COOLDOWN_HOURS):
            if claim_count >= max_claims:
                is_locked = True
        else:
            claim_count = 0  

    if is_locked:
        last_time = datetime.strptime(last_time_str, "%Y-%m-%d %H:%M:%S")
        time_left = (last_time + timedelta(hours=HCLAIM_COOLDOWN_HOURS)) - now_time
        hours, remainder = divmod(int(time_left.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)
        conn.close()
        limit_msg = f"{max_claims} random characters" if max_claims > 1 else "1 random character"
        return await update.message.reply_text(
            f"⏳ <b>Daily Limit Reached!</b>\n\n"
            f"<blockquote>⚠️ You can only claim {limit_msg} per day!\n"
            f"🕒 Come back after: <b>{hours}h {minutes}m</b></blockquote>",
            parse_mode=ParseMode.HTML
        )

    # WEIGHTED SELECTION LOGIC WITH PREMIUM CHANCE+
    cur.execute("SELECT rarity_id, chance, rarity_name FROM claim_list WHERE chance > 0")
    weights = cur.fetchall()
    if not weights:
        conn.close()
        return await update.message.reply_text("❌ All claimable editions are currently turned OFF!")

    processed_weights = []
    total = 0
    for rid, chance, rname in weights:
        final_chance = chance
        # 👑 Premium പ്ലെയർ ആണെങ്കിൽ ഹൈ-റാരിറ്റികൾക്ക് 3x ചാൻസ് ബൂസ്റ്റ്!
        if prem and any(hr in rname.lower() for hr in HIGH_RARITIES):
            final_chance = chance * 3.0
        total += final_chance
        processed_weights.append((rid, final_chance))

    pick = random.uniform(0, total)
    cumulative = 0
    chosen_rarity = None

    for rid, chance in processed_weights:
        cumulative += chance
        if pick <= cumulative:
            chosen_rarity = rid
            break

    char = get_random_character_by_rarity_id(chosen_rarity) if chosen_rarity else None
        # 🔄 FALLBACK LOGIC: സെലക്ട് ചെയ്ത റാരിറ്റിയിൽ കാരക്ടർ ഇല്ലെങ്കിൽ ഡാറ്റാബേസിലുള്ള ഏതെങ്കിലും ഒന്നിനെ എടുക്കും!
    if not char:
        char = cur.execute("""
            SELECT id, name, anime, rarity, msg_id 
            FROM characters 
            ORDER BY RANDOM() LIMIT 1
        """).fetchone()

    if not char:
        conn.close()
        return await update.message.reply_text("❌ ഡാറ്റാബേസിൽ ഒരു കാരക്ടർ പോലും ഇല്ല അളിയാ! ആദ്യം കുറച്ചെണ്ണം ആഡ് ചെയ്യ്.")

    char_id, name, anime, rarity, db_file_value = char

    # DB UPDATE
    now_str = now_time.strftime("%Y-%m-%d %H:%M:%S")
    new_count = claim_count + 1
    cur.execute("UPDATE users SET last_hclaim = ?, last_hclaim_count = ? WHERE user_id = ?", (now_str, new_count, user_id))

    cur.execute("""
        INSERT INTO user_collection (user_id, character_id, count)
        VALUES (?, ?, 1)
        ON CONFLICT(user_id, character_id) DO UPDATE SET count = count + 1
    """, (user_id, char_id))
    conn.commit()
    conn.close()

    premium_tag = "👑 <b>Premium Claim Active (High Rarity Chance+ Boosted)</b>\n" if prem else ""
    emoji = rarity_emoji(rarity)
    text = (
        f"💖 <b>DAILY CHARACTER CLAIMED!</b> 💖\n\n"
        f"<blockquote>{premium_tag}"
        f"👤 <b>Harem Master:</b> {update.effective_user.mention_html()}\n"
        f"👤 <b>Name:</b> {name} (ID: {char_id})\n"
        f"🎌 <b>Anime:</b> {anime}\n"
        f"{emoji} <b>Rarity:</b> {rarity}\n"
        f"📊 <b>Claims Today:</b> {new_count}/{max_claims}</blockquote>\n\n"
        f"✨ Character successfully added to your /harem!"
    )

    try:
        db_val = str(db_file_value).strip()
        if db_val.startswith("http://") or db_val.startswith("https://"):
            if any(ext in db_val.lower() for ext in [".mp4", ".mkv", ".mov"]):
                await update.message.reply_video(video=db_val, caption=text, parse_mode=ParseMode.HTML)
            elif ".gif" in db_val.lower():
                await update.message.reply_animation(animation=db_val, caption=text, parse_mode=ParseMode.HTML)
            else:
                await update.message.reply_photo(photo=db_val, caption=text, parse_mode=ParseMode.HTML)
        else:
            if "_" in db_val:
                file_type, file_id = db_val.split("_", 1)
                if file_type == "video":
                    await update.message.reply_video(video=file_id, caption=text, parse_mode=ParseMode.HTML)
                elif file_type == "animation":
                    await update.message.reply_animation(animation=file_id, caption=text, parse_mode=ParseMode.HTML)
                else:
                    await update.message.reply_photo(photo=file_id, caption=text, parse_mode=ParseMode.HTML)
            else:
                await update.message.reply_photo(photo=db_val, caption=text, parse_mode=ParseMode.HTML)
    except Exception:
        await update.message.reply_text(text=text, parse_mode=ParseMode.HTML)

# ==================== 💣 /bomb ====================
async def bomb_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    cd = cooldown_left(user_id, "bomb")
    if cd > 0:
        h, m = divmod(cd // 60, 60)
        return await update.message.reply_text(f"⏳ <b>Bomb is on Cooldown!</b>\n\n<blockquote>⏰ {h}h {m}m remaining.</blockquote>", parse_mode="HTML")

    target_id, target_name, reply_to = get_target(update, context)
    if not target_id:
        return await update.message.reply_text("💡 <b>Usage Examples:</b>\n• Reply to a user's message with <code>/bomb</code>\n• <code>/bomb @username</code>", parse_mode="HTML")

    if target_id == user_id:
        return await update.message.reply_text("❌ You cannot bomb your own harem!", parse_mode="HTML")

    conn = get_conn()
    cur = conn.cursor()

    has_bomb = cur.execute("""
        SELECT id FROM user_inventory
        WHERE user_id=? AND item_id='bomb' AND uses_remaining>0
              AND expires_at>datetime('now')
        ORDER BY expires_at ASC LIMIT 1
    """, (user_id,)).fetchone()
    if not has_bomb:
        conn.close()
        return await update.message.reply_text("❌ <b>Bomb missing!</b>\nYou don't own any bombs. Buy one from /market.", parse_mode="HTML")

    shield = cur.execute("""
        SELECT id FROM user_inventory
        WHERE user_id=? AND item_id='bshield' AND uses_remaining>0
              AND expires_at>datetime('now')
        ORDER BY expires_at ASC LIMIT 1
    """, (target_id,)).fetchone()

    kwargs = {"reply_to_message_id": reply_to} if reply_to else {}

    if shield:
        cur.execute("UPDATE user_inventory SET uses_remaining = uses_remaining - 1 WHERE id=?", (shield[0],))
        cur.execute("UPDATE user_inventory SET uses_remaining = uses_remaining - 1 WHERE id=?", (has_bomb[0],))
        cur.execute("DELETE FROM user_inventory WHERE id=? AND uses_remaining<=0", (shield[0],))
        cur.execute("DELETE FROM user_inventory WHERE id=? AND uses_remaining<=0", (has_bomb[0],))
        conn.commit()
        conn.close()
        set_cooldown(user_id, "bomb")
        return await update.message.reply_text(f"🛡️ <b>Attack Blocked!</b>\n\n<blockquote>{target_name} used a <b>Bomb Shield</b>! Your bomb was destroyed.</blockquote>", parse_mode="HTML", **kwargs)

    target_char = cur.execute("""
        SELECT c.id, c.name, c.rarity, uc.count
        FROM user_collection uc
        JOIN characters c ON c.id = uc.character_id
        WHERE uc.user_id=? AND uc.count > 0
        ORDER BY RANDOM() LIMIT 1
    """, (target_id,)).fetchone()

    if not target_char:
        conn.close()
        return await update.message.reply_text(f"❌ <b>Target is safe!</b>\n\n{target_name} has no characters in their harem.", parse_mode="HTML", **kwargs)

    char_id, char_name, char_rarity, char_count = target_char
    emoji = rarity_emoji(char_rarity)

    cur.execute("UPDATE user_inventory SET uses_remaining = uses_remaining - 1 WHERE id=?", (has_bomb[0],))
    cur.execute("DELETE FROM user_inventory WHERE id=? AND uses_remaining<=0", (has_bomb[0],))
    cur.execute("UPDATE user_collection SET count = count - 1 WHERE user_id=? AND character_id=?", (target_id, char_id))
    cur.execute("""
        INSERT INTO user_collection (user_id, character_id, count)
        VALUES (?, ?, 1)
        ON CONFLICT(user_id, character_id) DO UPDATE SET count = count + 1
    """, (user_id, char_id))
    conn.commit()
    conn.close()
    set_cooldown(user_id, "bomb")

    await update.message.reply_text(
        f"💥 <b>💥 BOMB EXPLODED! 💥</b>\n\n"
        f"<blockquote>You successfully sneaked into {target_name}'s harem and hijacked: \n\n"
        f"{emoji} <b>{char_name}</b> ({char_rarity.title()})</blockquote>",
        parse_mode="HTML", **kwargs)

# ==================== 💸 /steal (MONEY STEAL Heist) ====================
async def steal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    cd = cooldown_left(user_id, "steal")
    if cd > 0:
        m, s = divmod(cd, 60)
        return await update.message.reply_text(f"⏳ <b>Steal is on Cooldown!</b>\n\n<blockquote>⏰ {m}m {s}s left.</blockquote>", parse_mode="HTML")

    target_id, target_name, reply_to = get_target(update, context)
    if not target_id:
        return await update.message.reply_text("💡 <b>Usage Examples:</b>\n• Reply with <code>/steal</code>\n• <code>/steal @username</code>", parse_mode="HTML")

    if target_id == user_id:
        return await update.message.reply_text("❌ You cannot rob yourself!", parse_mode="HTML")

    conn = get_conn()
    cur = conn.cursor()

    row = cur.execute("SELECT balance FROM users WHERE user_id=?", (target_id,)).fetchone()
    kwargs = {"reply_to_message_id": reply_to} if reply_to else {}

    if not row or row[0] < 100:
        conn.close()
        return await update.message.reply_text(f"❌ <b>Too poor!</b>\n\n{target_name} has less than 100 coins to steal.", parse_mode="HTML", **kwargs)

    target_balance = row[0]

    shield = cur.execute("""
        SELECT id, uses_remaining FROM user_inventory
        WHERE user_id=? AND item_id='sshield' AND uses_remaining>0
              AND expires_at>datetime('now')
        ORDER BY expires_at ASC LIMIT 1
    """, (target_id,)).fetchone()

    if shield:
        cur.execute("UPDATE user_inventory SET uses_remaining = uses_remaining - 1 WHERE id=?", (shield[0],))
        cur.execute("DELETE FROM user_inventory WHERE id=? AND uses_remaining<=0", (shield[0],))
        conn.commit()
        conn.close()
        set_cooldown(user_id, "steal")
        return await update.message.reply_text(f"🔒 <b>Robbery Blocked!</b>\n\n<blockquote>{target_name} is protected by a <b>Steal Shield</b>!</blockquote>", parse_mode="HTML", **kwargs)

    if target_balance < 1000:
        s_min, s_max = int(target_balance * 0.20), int(target_balance * 0.70)
    elif target_balance < 100000:
        s_min, s_max = int(target_balance * 0.10), int(target_balance * 0.30)
    elif target_balance < 1000000:
        s_min, s_max = int(target_balance * 0.05), int(target_balance * 0.20)
    else:
        s_min, s_max = 1000, 50000

    stolen = random.randint(s_min, s_max)

    cur.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (stolen, target_id))
    cur.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (stolen, user_id))
    conn.commit()
    conn.close()
    set_cooldown(user_id, "steal")

    await update.message.reply_text(
        f"💸 <b>HEIST SUCCESSFUL!</b>\n\n"
        f"<blockquote>You looted 💰 <code>{fmt(stolen)}</code> coins out of {target_name}'s pocket!</blockquote>",
        parse_mode="HTML", **kwargs)

# ==================== 🎁 /daily ====================
async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'check_ban' in globals() and await check_ban(update):
        return

    user = update.effective_user
    user_id = user.id

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(users)")
    columns = [c[1] for c in cursor.fetchall()]
    if "last_daily" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN last_daily TEXT")
        conn.commit()

    cursor.execute("SELECT last_daily FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    now = datetime.now()
    reward = random.randint(100, 300)

    if row and row[0]:
        try: last_time = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
        except Exception: last_time = None

        if last_time and now < last_time + timedelta(hours=24):
            time_left = (last_time + timedelta(hours=24)) - now
            hours, remainder = divmod(int(time_left.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)
            conn.close()
            return await update.message.reply_text(f"⏳ <b>Cooldown Active!</b>\n\n<blockquote>⚠️ You already claimed daily reward!\n🕒 Come back after: <b>{hours}h {minutes}m</b></blockquote>", parse_mode="HTML")

    has_magnet = cursor.execute("""
        SELECT id, uses_remaining FROM user_inventory
        WHERE user_id=? AND item_id='magnet' AND uses_remaining>0
              AND expires_at>datetime('now')
        ORDER BY expires_at ASC LIMIT 1
    """, (user_id,)).fetchone()

    magnet_text = ""
    if has_magnet:
        magnet_id, current_uses = has_magnet
        reward += 2000
        new_uses = current_uses - 1
        cursor.execute("UPDATE user_inventory SET uses_remaining = ? WHERE id=?", (new_uses, magnet_id))
        cursor.execute("DELETE FROM user_inventory WHERE id=? AND uses_remaining<=0", (magnet_id,))
        magnet_text = f"\n🧲 <b>Coin Magnet:</b> Activated (Remaining: {new_uses})"

    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE users SET balance = COALESCE(balance, 0) + ?, last_daily = ? WHERE user_id = ?", (reward, now_str, user_id))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"🎁 <b>DAILY REWARD CLAIMED!</b>\n\n<blockquote>👤 <b>User:</b> {user.mention_html()}\n💰 <b>Reward:</b> +{reward} Coins{magnet_text}</blockquote>\n✨ Come back tomorrow!", parse_mode="HTML")

# ==================== ⏰ /skip (MULTI-PURPOSE COOLDOWN REFRESH) ====================
async def skip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not context.args or context.args[0] not in ["1", "2", "3"]:
        return await update.message.reply_text(
            "💡 <b>Multi-Purpose Skip Cooldown Usage:</b>\n"
            "• <code>/skip 1</code> ➡️ Reset /daily Reward Cooldown\n"
            "• <code>/skip 2</code> ➡️ Consume ticket & load 1 🛡️ Bomb Shield\n"
            "• <code>/skip 3</code> ➡️ Consume ticket & load 1 🔒 Steal Shield", 
            parse_mode="HTML"
        )

    mode = context.args[0]
    conn = get_conn()
    cur = conn.cursor()

    has_skip = cur.execute("""
        SELECT id, uses_remaining FROM user_inventory
        WHERE user_id=? AND item_id='skip' AND uses_remaining>0
              AND expires_at>datetime('now')
        ORDER BY expires_at ASC LIMIT 1
    """, (user_id,)).fetchone()

    if not has_skip:
        conn.close()
        return await update.message.reply_text("❌ <b>Skip Ticket Missing!</b>\nYou don't own any skip tickets. Buy one from /market.", parse_mode="HTML")

    ticket_id, current_uses = has_skip
    new_uses = current_uses - 1

    if mode == "1":
        # /daily കോൾഡൗൺ കംപ്ലീറ്റ് ആയി ക്ലിയർ ചെയ്യുന്നു
        cur.execute("SELECT last_daily FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        if not row or not row[0]:
            conn.close()
            return await update.message.reply_text("❌ Your <code>/daily</code> reward is already available to claim!", parse_mode="HTML")

        cur.execute("UPDATE users SET last_daily = NULL WHERE user_id = ?", (user_id,))
        msg = "⏰ <b>Daily Cooldown Skipped!</b>\n\n<blockquote>Your <code>/daily</code> reward timer has been reset successfully! Claim your daily coins now.</blockquote>"

    elif mode == "2":
        # Bomb shield ഇൻവെന്ററിയിലേക്ക് കയറ്റുന്നു
        cur.execute("""
            INSERT INTO user_inventory (user_id, item_id, uses_remaining, purchased_at, expires_at)
            VALUES (?, 'bshield', 1, datetime('now'), datetime('now', '+24 hours'))
        """, (user_id,))
        msg = "🛡️ <b>Bomb Shield Activated!</b>\n\n<blockquote>1 Bomb Shield has been injected into your inventory via Skip Ticket.</blockquote>"

    elif mode == "3":
        # Steal shield ഇൻവെന്ററിയിലേക്ക് കയറ്റുന്നു
        cur.execute("""
            INSERT INTO user_inventory (user_id, item_id, uses_remaining, purchased_at, expires_at)
            VALUES (?, 'sshield', 1, datetime('now'), datetime('now', '+24 hours'))
        """, (user_id,))
        msg = "🔒 <b>Steal Shield Activated!</b>\n\n<blockquote>1 Steal Shield has been injected into your inventory via Skip Ticket.</blockquote>"

    # ടിക്കറ്റ് അപ്‌ഡേറ്റ്
    cur.execute("UPDATE user_inventory SET uses_remaining=? WHERE id=?", (new_uses, ticket_id))
    cur.execute("DELETE FROM user_inventory WHERE id=? AND uses_remaining<=0", (ticket_id,))
    
    conn.commit()
    conn.close()

    await update.message.reply_text(f"{msg}\n🎟️ <i>Skip Tickets left: {new_uses}</i>", parse_mode="HTML")

# ==================== 🎴 /summon ====================
async def summon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'check_ban' in globals() and await check_ban(update): return
    user_id = update.effective_user.id

    spawn = context.chat_data.get("active_spawn")
    if not spawn or spawn.get("claimed"):
        return await update.message.reply_text("❌ No active character available to summon right now.")

    if not context.args:
        return await update.message.reply_text("💡 Usage: <code>/summon [character_name]</code>", parse_mode="HTML")

    guessed_name = " ".join(context.args).strip().lower()
    if len(guessed_name) < 3:
        return await update.message.reply_text("⚠️ Name must be at least 3 characters long!")

    spawn_parts = [part.strip() for part in spawn["name"].lower().split()]
    if guessed_name not in spawn_parts and guessed_name != spawn["name"].lower():
        return await update.message.reply_text("❌ Wrong name! Try again.")
    
    spawn["claimed"] = True
    char_id = spawn["id"]

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT name, rarity FROM characters WHERE id=?", (char_id,))
    char = cursor.fetchone()
    name, rarity = char if char else ("Unknown", "⭐")

    reward = random.randint(20, 60)
    item_notices = ""

    has_xp = cursor.execute("""
        SELECT id, uses_remaining FROM user_inventory
        WHERE user_id=? AND item_id='xp' AND uses_remaining>0 AND expires_at>datetime('now')
        ORDER BY expires_at ASC LIMIT 1
    """, (user_id,)).fetchone()

    if has_xp:
        xp_id, xp_uses = has_xp
        reward *= 2
        new_xp_uses = xp_uses - 1
        cursor.execute("UPDATE user_inventory SET uses_remaining = ? WHERE id=?", (new_xp_uses, xp_id))
        cursor.execute("DELETE FROM user_inventory WHERE id=? AND uses_remaining<=0", (xp_id,))
        item_notices += f"\n⚡ <b>XP Boost:</b> Active (2x Coins! Left: {new_xp_uses})"

    has_lucky = cursor.execute("""
        SELECT id, uses_remaining FROM user_inventory
        WHERE user_id=? AND item_id='lucky' AND uses_remaining>0 AND expires_at>datetime('now')
        ORDER BY expires_at ASC LIMIT 1
    """, (user_id,)).fetchone()

    copies_to_add = 1
    if has_lucky:
        lucky_id, lucky_uses = has_lucky
        copies_to_add = 2
        reward += 50
        new_lucky_uses = lucky_uses - 1
        cursor.execute("UPDATE user_inventory SET uses_remaining = ? WHERE id=?", (new_lucky_uses, lucky_id))
        cursor.execute("DELETE FROM user_inventory WHERE id=? AND uses_remaining<=0", (lucky_id,))
        item_notices += f"\n🎟️ <b>Lucky Ticket:</b> Active (Double Copy! Left: {new_lucky_uses})"

    cursor.execute("UPDATE users SET balance = COALESCE(balance, 0) + ? WHERE user_id = ?", (reward, user_id))
    cursor.execute("""
        INSERT INTO user_collection (user_id, character_id, count)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, character_id) DO UPDATE SET count = count + ?
    """, (user_id, char_id, copies_to_add, copies_to_add))
    conn.commit()
    conn.close()

    copy_text = f" (x{copies_to_add})" if copies_to_add > 1 else ""
    emoji = rarity_emoji(rarity)

    await update.message.reply_text(
        f"🎉 <b>Character Summoned!</b>\n\n<blockquote>👤 <b>Summoner:</b> {update.effective_user.mention_html()}\n• Character: {name} (ID: {char_id}){copy_text}\n{emoji} <b>Rarity:</b> {rarity}\n💰 <b>Reward:</b> +{reward} Coins{item_notices}</blockquote>\n\n✨ Nice pull!",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎒 See collection", switch_inline_query_current_chat=f"collection.{user_id}")]]))

# ==================== 👑 /premium (GRANT PREMIUM ACCESS) ====================
async def premium_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return await update.message.reply_text("❌ Admin only.")

    target_id, target_name, reply_to = get_target(update, context)
    if not target_id:
        return await update.message.reply_text("💡 <b>Usage:</b> <code>/premium 4d @username</code>\n• Units: h (hour), d (day), w (week)", parse_mode="HTML")

    duration_str = None
    if context.args:
        for a in context.args:
            if re.match(r"^\d+[dwh]$", a.lower()):
                duration_str = a.lower()
                break

    if not duration_str:
        return await update.message.reply_text("❌ Specify duration format! Example: <code>/premium 4d</code> (h/d/w)", parse_mode="HTML")

    m = re.match(r"^(\d+)([dwh])$", duration_str)
    num, unit = int(m.group(1)), m.group(2)

    delta = timedelta(hours=num) if unit == "h" else timedelta(days=num) if unit == "d" else timedelta(weeks=num)
    secs = int(delta.total_seconds())

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO premium (user_id, expires_at, granted_at, granted_by)
        VALUES (?, datetime('now', ?), datetime('now'), ?)
        ON CONFLICT(user_id) DO UPDATE SET
            expires_at = CASE WHEN expires_at > datetime('now') THEN datetime(expires_at, ?) ELSE datetime('now', ?) END
    """, (target_id, f"+{secs} seconds", update.effective_user.id, f"+{secs} seconds", f"+{secs} seconds"))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"👑 <b>Premium Access Granted!</b>\n\n<blockquote>👤 <b>User:</b> {target_name} (<code>{target_id}</code>)\n⏳ <b>Added:</b> {duration_str}</blockquote>", parse_mode="HTML")

# ==================== ℹ️ /pinfo (CHECK PREMIUM VALIDITY) ====================
async def pinfo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = get_conn()
    row = conn.execute("SELECT expires_at FROM premium WHERE user_id=? AND expires_at > datetime('now')", (user_id,)).fetchone()
    conn.close()

    if not row:
        return await update.message.reply_text("⭐ <b>Premium status:</b> <code>Not Active</code>\nContact Admin to purchase premium access!", parse_mode="HTML")

    exp_time = datetime.fromisoformat(row[0].replace(" ", "T"))
    time_left = exp_time - datetime.utcnow()
    days = time_left.days
    hours, remainder = divmod(time_left.seconds, 3600)
    minutes, _ = divmod(remainder, 60)

    await update.message.reply_text(
        f"👑 <b>PREMIUM PLAN DETAILS</b> 👑\n\n"
        f"<blockquote>👤 <b>User:</b> {update.effective_user.mention_html()}\n"
        f"📊 <b>Status:</b> <code>Active</code>\n"
        f"⏳ <b>Time Remaining:</b> <code>{days}d {hours}h {minutes}m</code>\n"
        f"📅 <b>Expires On:</b> <code>{row[0]} UTC</code></blockquote>\n"
        f"✨ Enjoy unlimited store freebies, 2x daily claims and boosted high rarity drop chances!",
        parse_mode="HTML"
    )

# ==================== ❌ /unpremium ====================
async def unpremium_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return await update.message.reply_text("❌ Admin only.")

    target_id, target_name, reply_to = get_target(update, context)
    if not target_id:
        return await update.message.reply_text("💡 <b>Usage:</b> <code>/unpremium @username</code>", parse_mode="HTML")

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM premium WHERE user_id=?", (target_id,))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"🚫 <b>Premium Access Removed!</b>\n\n<blockquote>👤 <b>User:</b> {target_name} (<code>{target_id}</code>)</blockquote>", parse_mode="HTML")

# ==================== REGISTER ====================
def register(app):
    app.add_handler(CommandHandler("market", market_cmd))
    app.add_handler(CommandHandler("inv", inv_cmd))
    app.add_handler(CommandHandler("inventory", inv_cmd))
    app.add_handler(CommandHandler(["hclaim", "claim"], hclaim_command))
    app.add_handler(CommandHandler("bomb", bomb_cmd))
    app.add_handler(CommandHandler("steal", steal_cmd))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("skip", skip_cmd))
    app.add_handler(CommandHandler("pinfo", pinfo_cmd))
    app.add_handler(CommandHandler(["summon", "guess", "grab", "collect"], summon))
    app.add_handler(CommandHandler("premium", premium_cmd))
    app.add_handler(CommandHandler("unpremium", unpremium_cmd))
    app.add_handler(CallbackQueryHandler(market_cb, pattern=r"^(mi:|m_inv|m_back)"))

