from storage import connect as db_connect
import sqlite3
from datetime import datetime, timezone, timedelta
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from config import DB_NAME

DB = DB_NAME

COOLDOWN_BOMB  = 6 * 3600      # 6 hours
COOLDOWN_STEAL = 24 * 3600     # 24 hours

# ==================== RARITY ====================
RARITY_DISPLAY = {
    1: "⚪ Common", 2: "🔵 Rare", 3: "💮 Special Edition",
    4: "⭐ Legendary", 5: "🛸 Mythic Edition",
    6: "💝 Valentine Edition", 7: "🏖️ Summer Edition", 8: "🌧️ Rainy Edition",
    9: "🎃 Halloween Edition", 10: "🎄 Christmas Edition", 11: "❄️ Winter Edition",
    12: "🎇 New Year Edition",
    13: "🎍 Festival Edition", 14: "🎥 AMV Edition", 15: "🎉 Event Edition",
    16: "🌌 Celestial Edition", 17: "💎 Luxury Edition", 18: "🔮 Limited Edition",
}

RARITY_EMOJI = {
    "common": "⚪", "rare": "🔵", "special": "💮", "legendary": "⭐",
    "mythic": "🛸", "valentine": "💝", "summer": "🏖️", "rainy": "🌧️",
    "halloween": "🎃", "christmas": "🎄", "winter": "❄️", "new year": "🎇",
    "festival": "🎍", "amv": "🎥", "event": "🎉", "celestial": "🌌",
    "luxury": "💎", "limited": "🔮",
}

# ==================== ACHIEVEMENTS ====================
ACHIEVEMENTS = {
    "first_char":     {"name": "🎯 First Catch",     "desc": "Claim your first character",          "check": "chars_gte_1"},
    "collector_5":    {"name": "📚 Beginner",        "desc": "Collect 5 unique characters",         "check": "chars_gte_5"},
    "collector_10":   {"name": "📖 Hobbyist",        "desc": "Collect 10 unique characters",        "check": "chars_gte_10"},
    "collector_25":   {"name": "🎓 Enthusiast",      "desc": "Collect 25 unique characters",        "check": "chars_gte_25"},
    "collector_50":   {"name": "💎 Expert",          "desc": "Collect 50 unique characters",        "check": "chars_gte_50"},
    "collector_100":  {"name": "👑 Master",          "desc": "Collect 100 unique characters",       "check": "chars_gte_100"},
    "epic_owner":     {"name": "💜 Epic Hunter",     "desc": "Own at least one EPIC character",     "check": "owns_rarity_epic"},
    "legend_owner":   {"name": "🌟 Legendary",       "desc": "Own at least one LEGENDARY character","check": "owns_rarity_legendary"},
    "mythic_owner":   {"name": "🔮 Mythic Touched",  "desc": "Own at least one MYTHIC character",   "check": "owns_rarity_mythic"},
    "rich_1k":        {"name": "💰 Pocket Money",    "desc": "Reach 1,000 coins balance",           "check": "balance_gte_1000"},
    "rich_10k":       {"name": "💸 Tycoon",          "desc": "Reach 10,000 coins balance",          "check": "balance_gte_10000"},
    "rich_100k":      {"name": "🤑 Mogul",           "desc": "Reach 100,000 coins balance",         "check": "balance_gte_100000"},
    "streak_3":       {"name": "🔥 3-Day Streak",    "desc": "Login 3 days in a row",               "check": "streak_gte_3"},
    "streak_7":       {"name": "🔥 7-Day Streak",    "desc": "Login 7 days in a row",               "check": "streak_gte_7"},
    "streak_30":      {"name": "⚡ 30-Day Streak",   "desc": "Login 30 days in a row",              "check": "streak_gte_30"},
    "shopaholic":     {"name": "🛍️ Shopaholic",      "desc": "Make 10 purchases from /shop",        "check": "purchases_gte_10"},
}

# ==================== HELPERS ====================
def progress_bar(pct, length=10):
    pct = max(0, min(100, pct))
    filled = int(length * pct / 100)
    return "▰" * filled + "▱" * (length - filled)


def rarity_emoji(rarity_text):
    if not rarity_text:
        return "⚪"
    rt = rarity_text.lower()
    for key, emoji in RARITY_EMOJI.items():
        if key in rt:
            return emoji
    return "⚪"


def rarity_name(rarity_text):
    if not rarity_text:
        return "Common"
    rt = rarity_text.lower()
    for name in RARITY_DISPLAY.values():
        parts = name.split(" ", 1)
        if len(parts) == 2 and parts[1].lower() in rt:
            return name
    return rarity_text.title()


def fmt(n):
    try:
        return f"{int(n):,}"
    except Exception:
        return str(n)


def get_conn():
    return db_connect(DB)


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
    if not row:
        return 0
    try:
        last = datetime.fromisoformat(row[0].replace(" ", "T"))
        cd_secs = COOLDOWN_BOMB if command == "bomb" else COOLDOWN_STEAL
        elapsed = (datetime.utcnow() - last).total_seconds()
        return max(0, int(cd_secs - elapsed))
    except Exception:
        return 0


def get_inventory_rows(user_id):
    conn = get_conn()
    cur = conn.cursor()
    rows = cur.execute("""
        SELECT item_id, uses_remaining,
               CAST((julianday(expires_at) - julianday('now')) * 24 AS INT) as h
        FROM user_inventory
        WHERE user_id=? AND expires_at>datetime('now')
    """, (user_id,)).fetchall()
    conn.close()
    return rows


def item_emoji(item_id):
    if not item_id:
        return "🎒"
    it = str(item_id).lower()
    emoji_map = {
        "shield": "🛡️", "bomb": "💣", "lucky": "🎟️", "skip": "⏰",
        "key": "🔑", "potion": "🧪", "scroll": "📜", "gem": "💎",
        "box": "🎁", "token": "🪙", "ring": "💍", "crown": "👑",
        "chest": "📦", "ticket": "🎫", "boost": "⚡", "amulet": "📿",
        "star": "🌟", "heart": "❤️", "fire": "🔥", "ice": "❄️",
        "thunder": "⚡", "light": "💡", "dark": "🌑", "water": "💧",
        "earth": "🌍", "wind": "💨", "leaf": "🍃", "flower": "🌸",
        "rose": "🌹", "candy": "🍬", "cake": "🎂", "cookie": "🍪",
        "tea": "🍵", "coffee": "☕", "book": "📚", "map": "🗺️",
        "compass": "🧭", "sword": "⚔️", "bow": "🏹", "arrow": "➳",
        "hammer": "🔨", "rocket": "🚀", "ufo": "🛸", "car": "🚗",
        "plane": "✈️", "ship": "🚢", "train": "🚂", "bike": "🚲",
        "dragon": "🐉", "wolf": "🐺", "fox": "🦊", "tiger": "🐅",
        "bear": "🐻", "panda": "🐼", "lion": "🦁", "unicorn": "🦄",
        "phoenix": "🔥", "ghost": "👻", "skull": "💀", "alien": "👽",
        "robot": "🤖", "wizard": "🧙", "fairy": "🧚", "angel": "👼",
        "king": "🤴", "queen": "👸", "knight": "🛡️", "ninja": "🥷",
        "pirate": "🏴‍☠️", "astronaut": "🧑‍🚀", "scientist": "🧑‍🔬",
    }
    for k, e in emoji_map.items():
        if k in it:
            return e
    return "🎒"


def item_display_name(item_id):
    if not item_id:
        return "Unknown"
    return str(item_id).replace("_", " ").replace("-", " ").title()


# ==================== MARKDOWNV2 ESCAPER ====================
MD2_ESCAPE = r"_*[]()~`>#+-=|{}.!"


def md2(text: str) -> str:
    """Escape reserved MarkdownV2 chars in plain text."""
    out = []
    for ch in text:
        if ch in MD2_ESCAPE:
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


# ==================== MAIN COMMAND ====================
async def hstats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    target_id = user_id
    target_first = user.first_name or "User"
    target_username = user.username

    if context.args:
        arg = context.args[0].lstrip("@")
        if arg.isdigit():
            target_id = int(arg)
        else:
            conn = get_conn()
            row = conn.execute(
                "SELECT user_id, first_name, username FROM users WHERE username = ?",
                (arg,)).fetchone()
            conn.close()
            if row:
                target_id, target_first, target_username = row

    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # User
    u = cur.execute("SELECT * FROM users WHERE user_id = ?", (target_id,)).fetchone()
    if not u:
        await update.message.reply_text("❌ User not found.")
        conn.close()
        return

    balance = u["balance"] or 0
    first_name = u["first_name"] or target_first
    username = u["username"] or target_username
    last_daily = u["last_daily"]

    # Chars
    chars = cur.execute("""
        SELECT c.rarity, COUNT(*) as cnt, SUM(uc.count) as total
        FROM user_collection uc
        JOIN characters c ON uc.character_id = c.id
        WHERE uc.user_id = ?
        GROUP BY c.rarity
    """, (target_id,)).fetchall()

    unique_chars = sum(r["cnt"] for r in chars) if chars else 0
    total_summons = sum(r["total"] or 0 for r in chars) if chars else 0
    total_game = cur.execute("SELECT COUNT(*) FROM characters").fetchone()[0] or 1
    harem_pct = (unique_chars / total_game * 100) if total_game else 0

    # Rank
    rank_row = cur.execute("""
        SELECT COUNT(*) + 1 FROM (
            SELECT user_id, COUNT(DISTINCT character_id) as cnt
            FROM user_collection GROUP BY user_id
            HAVING COUNT(DISTINCT character_id) > ?
        )
    """, (unique_chars,)).fetchone()
    rank = rank_row[0] if rank_row else 1

    total_players_row = cur.execute(
        "SELECT COUNT(DISTINCT user_id) FROM user_collection").fetchone()
    total_players = total_players_row[0] or 1

    # Streak
    streak = 0
    s = cur.execute("SELECT streak_count FROM user_streaks WHERE user_id = ?",
                    (target_id,)).fetchone()
    if s:
        streak = s["streak_count"] or 0

    # Purchases
    purchases = cur.execute(
        "SELECT COUNT(*) FROM market_transactions WHERE user_id = ?",
        (target_id,)).fetchone()[0] or 0

    # Achievements
    unlocked = {}
    try:
        rows = cur.execute(
            "SELECT achievement_id, unlocked_at FROM user_achievements WHERE user_id = ?",
            (target_id,)).fetchall()
        for r in rows:
            unlocked[r["achievement_id"]] = r["unlocked_at"]
    except Exception:
        pass

    # Inventory (light)
    inv_items = []
    try:
        inv_rows = cur.execute(
            "SELECT item_id, count FROM user_inventory WHERE user_id = ?",
            (target_id,)).fetchall()
        for r in inv_rows:
            inv_items.append((r["item_id"], r["count"]))
    except Exception:
        inv_items = []

    # Activity
    today_count = 0
    week_count = 0
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        today_count = cur.execute(
            "SELECT COUNT(*) FROM activity_log WHERE user_id = ? AND date(timestamp) = ?",
            (target_id, today)).fetchone()[0] or 0
        week_count = cur.execute(
            "SELECT COUNT(*) FROM activity_log WHERE user_id = ? AND date(timestamp) >= ?",
            (target_id, week_ago)).fetchone()[0] or 0
    except Exception:
        pass

    conn.close()

    # Achievement check
    def check_achievement(check_id):
        if check_id == "chars_gte_1": return unique_chars >= 1
        if check_id == "chars_gte_5": return unique_chars >= 5
        if check_id == "chars_gte_10": return unique_chars >= 10
        if check_id == "chars_gte_25": return unique_chars >= 25
        if check_id == "chars_gte_50": return unique_chars >= 50
        if check_id == "chars_gte_100": return unique_chars >= 100
        if check_id == "balance_gte_1000": return balance >= 1000
        if check_id == "balance_gte_10000": return balance >= 10000
        if check_id == "balance_gte_100000": return balance >= 100000
        if check_id == "streak_gte_3": return streak >= 3
        if check_id == "streak_gte_7": return streak >= 7
        if check_id == "streak_gte_30": return streak >= 30
        if check_id == "purchases_gte_10": return purchases >= 10
        if check_id == "owns_rarity_epic":
            return any("rare" in (r["rarity"] or "").lower() for r in chars)
        if check_id == "owns_rarity_legendary":
            return any("legend" in (r["rarity"] or "").lower() for r in chars)
        if check_id == "owns_rarity_mythic":
            return any("mythic" in (r["rarity"] or "").lower() for r in chars)
        return False

    rarity_rows = sorted(chars, key=lambda r: r["cnt"], reverse=True) if chars else []

    def rarity_pct(needle):
        for r in rarity_rows:
            if needle in (r["rarity"] or "").lower():
                return r["cnt"] / total_game * 100 if total_game else 0
        return 0

    mythic_pct = rarity_pct("mythic")
    legend_pct = rarity_pct("legend")

    # Top 5 rarities
    top_rarities = []
    for r in rarity_rows[:5]:
        cnt = r["cnt"]
        pct = cnt / unique_chars * 100 if unique_chars else 0
        top_rarities.append({
            "emoji": rarity_emoji(r["rarity"]),
            "name": rarity_name(r["rarity"]),
            "cnt": cnt,
            "pct": pct,
        })

    # Unlocked count
    unlocked_count = 0
    for ach_id in ACHIEVEMENTS:
        if ach_id in unlocked or check_achievement(ACHIEVEMENTS[ach_id]["check"]):
            unlocked_count += 1
    total_ach = len(ACHIEVEMENTS)

    # Premium + cooldowns
    prem = is_premium(target_id)
    hours_left = premium_left(target_id)
    bomb_cd  = cooldown_left(target_id, "bomb")
    steal_cd = cooldown_left(target_id, "steal")

    # Full inventory (with hours)
    inv_full = get_inventory_rows(target_id)
    item_map = {}
    for item_id, uses, h in inv_full:
        cur_entry = item_map.get(item_id, {"uses": 0, "h": h})
        cur_entry["uses"] = max(cur_entry["uses"], uses or 0)
        cur_entry["h"] = max(cur_entry["h"], h or 0)
        item_map[item_id] = cur_entry

    # ==================== BUILD OUTPUT (MarkdownV2) ====================
    L = []
    L.append("✨ *HAREM STATUS*")
    L.append("")

    # Header
    L.append(f"👤 *{md2(first_name)}* \\| @{md2(username or 'unknown')} \\| `UID: {target_id}`")
    L.append("")

    # Premium
    L.append("👑 *PREMIUM*")
    if prem:
        L.append(f"  • Status: ✅ *Active* \\- `{hours_left}h` remaining")
    else:
        L.append("  • Status: ❌ _Inactive_")
    L.append("")

    # Cooldowns
    L.append("⏰ *COOLDOWNS*")
    bomb_str = "Ready ✓" if bomb_cd == 0 else f"{bomb_cd // 3600}h {(bomb_cd % 3600) // 60}m"
    steal_str = "Ready ✓" if steal_cd == 0 else f"{steal_cd // 3600}h {(steal_cd % 3600) // 60}m"
    L.append(f"  • 💣 Bomb:  `{bomb_str}`")
    L.append(f"  • 🥷 Steal: `{steal_str}`")
    L.append("")

    # Ranking
    L.append("🏆 *RANKING*")
    L.append(f"  • Position: `#{fmt(rank)}` of {fmt(total_players)}")
    L.append(f"  • Harem: `{fmt(unique_chars)}/{fmt(total_game)}` \\({harem_pct:.1f}%\\)")
    L.append(f"  • Streak: `{streak} 🔥`")
    L.append("")

    # Currency
    L.append("💰 *CURRENCY*")
    L.append(f"  • Balance: `{fmt(balance)}` coins")
    L.append(f"  • All\\-time Summons: `{fmt(total_summons)}`")
    L.append(f"  • Purchases: `{fmt(purchases)}`")
    L.append("")

    # Progress bars
    L.append("📊 *PROGRESS*")
    L.append(f"  • Harem   {progress_bar(harem_pct)} `{harem_pct:5.1f}%`")
    L.append(f"  • Mythics {progress_bar(mythic_pct)} `{mythic_pct:5.1f}%`")
    L.append(f"  • Legends {progress_bar(legend_pct)} `{legend_pct:5.1f}%`")
    L.append("")

    # Rarity breakdown
    if top_rarities:
        L.append("🎴 *RARITY BREAKDOWN*")
        for r in top_rarities:
            bar = progress_bar(r["pct"], length=8)
            L.append(f"  {r['emoji']} {md2(r['name'])} \\- `{r['cnt']:>4}` {bar} `{r['pct']:4.1f}%`")
        L.append("")

    # Achievements — single expandable blockquote
    L.append(f"🏅 *ACHIEVEMENTS* \\({unlocked_count}/{total_ach}\\)")
    L.append("<blockquote expandable>")
    for ach_id, ach in ACHIEVEMENTS.items():
        is_unlocked = ach_id in unlocked or check_achievement(ach["check"])
        icon = "✅" if is_unlocked else "🔒"
        L.append(f"{icon} {ach['name']} - {ach['desc']}")
    L.append("</blockquote>")
    L.append("")

    # Inventory — top 5 inline
    if not item_map:
        L.append("🎒 *INVENTORY*")
        L.append("  • _Empty_")
    else:
        sorted_items = sorted(item_map.items(), key=lambda x: x[1]["h"], reverse=True)
        L.append(f"🎒 *INVENTORY* \\({len(sorted_items)} types\\)")
        for item_id, info in sorted_items[:5]:
            emoji = item_emoji(item_id)
            name = item_display_name(item_id)
            uses = info["uses"]
            h = info["h"]
            time_str = f"{h}h" if h else "∞"
            L.append(f"  {emoji} {md2(name)} ×`{uses}` \\| `{time_str}`")
        # Rest in expandable blockquote
        if len(sorted_items) > 5:
            L.append("")
            L.append("<blockquote expandable>")
            for item_id, info in sorted_items[5:]:
                emoji = item_emoji(item_id)
                name = item_display_name(item_id)
                uses = info["uses"]
                h = info["h"]
                time_str = f"{h}h" if h else "∞"
                L.append(f"{emoji} {md2(name)} ×`{uses}` \\| `{time_str}`")
            L.append("</blockquote>")
    L.append("")

    # Activity
    L.append("📈 *ACTIVITY*")
    L.append(f"  • Today: `{fmt(today_count)}`")
    L.append(f"  • This week: `{fmt(week_count)}`")
    L.append(f"  • All\\-time: `{fmt(total_summons)}` summons")

    text = "\n".join(L)

    # Telegram limit
    if len(text) > 4000:
        marker = "🏅 *ACHIEVEMENTS*"
        idx = text.find(marker)
        if idx > 0:
            part1 = text[:idx].rstrip() + "\n\n_Use /hstats again to view achievements_"
            part2 = text[idx:]
            await update.message.reply_text(part1, parse_mode="MarkdownV2")
            await update.message.reply_text(part2, parse_mode="MarkdownV2")
            return

    await update.message.reply_text(text, parse_mode="MarkdownV2")


# ==================== REGISTER ====================
def register(app):
    app.add_handler(CommandHandler("hstats", hstats_cmd))
    app.add_handler(CommandHandler("me", hstats_cmd))
