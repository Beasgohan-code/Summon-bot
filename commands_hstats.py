from storage import connect as db_connect
import os
# ~/summon-bot/commands_hstats.py
# /hstats and /me — uses Telegram native <blockquote expandable> for collapse.

import sqlite3
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CommandHandler

logger = logging.getLogger(__name__)

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "summon.db")


def progress_bar(pct, length=10):
    pct = max(0, min(100, pct))
    filled = int(length * pct / 100)
    return "▰" * filled + "▱" * (length - filled)


def fmt(n):
    try:
        return f"{int(n):,}"
    except Exception:
        return str(n)


def escape_html(text):
    return (
        str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


RARITY_EMOJI = {
    "common": "⚪", "rare": "🔵", "special": "💮", "legendary": "⭐",
    "mythic": "🛸", "valentine": "💝", "summer": "🏖️", "rainy": "🌧️",
    "halloween": "🎃", "christmas": "🎄", "winter": "❄️", "new year": "🎇",
    "festival": "🎍", "amv": "🎥", "event": "🎉", "celestial": "🌌",
    "luxury": "💎", "limited": "🔮",
}


def rarity_emoji(rarity_text):
    if not rarity_text:
        return "⚪"
    rt = rarity_text.lower()
    for k, e in RARITY_EMOJI.items():
        if k in rt:
            return e
    return "⚪"


def get_conn():
    return db_connect(DB)


ACHIEVEMENTS = {
    "first_char":    "🎯 First Catch — Claim your first character",
    "collector_5":   "📚 Beginner — Collect 5 unique characters",
    "collector_10":  "📖 Hobbyist — Collect 10 unique characters",
    "collector_25":  "🎓 Enthusiast — Collect 25 unique characters",
    "collector_50":  "💎 Expert — Collect 50 unique characters",
    "collector_100": "👑 Master — Collect 100 unique characters",
    "rich_1k":       "💰 Pocket Money — Reach 1,000 coins",
    "rich_10k":      "💸 Tycoon — Reach 10,000 coins",
    "rich_100k":     "🤑 Mogul — Reach 100,000 coins",
    "streak_3":      "🔥 3-Day Streak",
    "streak_7":      "🔥 7-Day Streak",
    "streak_30":     "⚡ 30-Day Streak",
    "shopaholic":    "🛍 Shopaholic — Make 10 purchases",
}


def get_user_data(user_id):
    conn = db_connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    u = cur.execute(
        "SELECT * FROM users WHERE user_id = ?", (user_id,)
    ).fetchone()
    if not u:
        conn.close()
        return None

    chars = cur.execute("""
        SELECT c.rarity, COUNT(*) as cnt, SUM(uc.count) as total
        FROM user_collection uc
        JOIN characters c ON uc.character_id = c.id
        WHERE uc.user_id = ?
        GROUP BY c.rarity
    """, (user_id,)).fetchall()

    unique_chars = sum(r["cnt"] for r in chars) if chars else 0
    total_summons = sum(r["total"] or 0 for r in chars) if chars else 0

    rank = cur.execute("""
        SELECT COUNT(*) + 1 FROM (
            SELECT user_id, COUNT(DISTINCT character_id) as cnt
            FROM user_collection GROUP BY user_id HAVING cnt > ?
        )
    """, (unique_chars,)).fetchone()[0] or 1

    total_players = cur.execute(
        "SELECT COUNT(DISTINCT user_id) FROM user_collection"
    ).fetchone()[0] or 1
    total_game = cur.execute("SELECT COUNT(*) FROM characters").fetchone()[0] or 1

    streak = 0
    s = cur.execute(
        "SELECT streak_count FROM user_streaks WHERE user_id = ?", (user_id,)
    ).fetchone()
    if s:
        streak = s["streak_count"] or 0

    purchases = cur.execute(
        "SELECT COUNT(*) FROM market_transactions WHERE user_id = ?", (user_id,)
    ).fetchone()[0] or 0

    unlocked = []
    try:
        unlocked = [r["achievement_id"] for r in cur.execute(
            "SELECT achievement_id FROM user_achievements WHERE user_id = ?",
            (user_id,)).fetchall()]
    except Exception:
        pass

    inv = []
    try:
        inv = cur.execute("""
            SELECT item_id, uses_remaining,
                   CAST((julianday(expires_at)-julianday('now'))*24 AS INT) as h
            FROM user_inventory
            WHERE user_id=? AND expires_at>datetime('now')
        """, (user_id,)).fetchall()
    except Exception:
        pass

    conn.close()
    return {
        "user": u, "chars": chars,
        "unique_chars": unique_chars, "total_summons": total_summons,
        "rank": rank, "total_players": total_players,
        "total_game": total_game, "streak": streak,
        "purchases": purchases, "unlocked": unlocked, "inv": inv,
    }


# ==================== HTML BUILDER (native expandable) ====================
def build_hstats_html(user_id, first_name, username):
    data = get_user_data(user_id)
    if not data:
        return "❌ User not found.", None

    u = data["user"]
    balance = u["balance"] or 0
    unique_chars = data["unique_chars"]
    total_summons = data["total_summons"]
    total_game = data["total_game"]
    harem_pct = (unique_chars / total_game * 100) if total_game else 0

    # ============ TOP — always visible ============
    L = []
    L.append("✨ <b>HAREM STATUS</b>")
    L.append("────────────────────")
    L.append(
        f"👤 <b>{escape_html(first_name)}</b> | "
        f"@{escape_html(username or 'unknown')} | "
        f"<code>UID: {user_id}</code>"
    )
    L.append("")

    L.append("🏆 <b>RANKING</b>")
    L.append(f"  • Position: <code>#{fmt(data['rank'])}</code> of {fmt(data['total_players'])}")
    L.append(f"  • Harem: <code>{fmt(unique_chars)}/{fmt(total_game)}</code> ({harem_pct:.1f}%)")
    L.append(f"  • Streak: <code>{data['streak']} 🔥</code>")
    L.append("")

    L.append("💰 <b>CURRENCY</b>")
    L.append(f"  • Balance: <code>{fmt(balance)}</code> coins")
    L.append(f"  • Total Summons: <code>{fmt(total_summons)}</code>")
    L.append(f"  • Purchases: <code>{fmt(data['purchases'])}</code>")
    L.append("")

    L.append("📊 <b>PROGRESS</b>")
    L.append(f"  • Harem   {progress_bar(harem_pct)} <code>{harem_pct:5.1f}%</code>")
    L.append("")

    # ============ BOTTOM — inside <blockquote expandable> ============
    # This is the part that shows ▼ in the corner
    extra_lines = []
    extra_lines.append("<b>🏅 ACHIEVEMENTS</b>")
    for ach_id, desc in ACHIEVEMENTS.items():
        icon = "✅" if ach_id in data["unlocked"] else "🔒"
        extra_lines.append(f"  • {icon} {desc}")
    extra_lines.append("")

    extra_lines.append("<b>🎒 INVENTORY</b>")
    if not data["inv"]:
        extra_lines.append("  • <i>Empty</i>")
    else:
        for item in data["inv"]:
            item_id = item["item_id"] if "item_id" in item.keys() else item[0]
            uses = item["uses_remaining"] if "uses_remaining" in item.keys() else item[1]
            h = item["h"] if "h" in item.keys() else item[2]
            extra_lines.append(
                f"  • 📦 {escape_html(item_id)} ×<code>{uses}</code> ({h}h)"
            )
    extra_lines.append("")

    extra_lines.append("<i>Tap ▼ to collapse · ⓘ for more info</i>")

    # The magic line — wrap everything in expandable blockquote
    L.append("<blockquote expandable>")
    L.append("\n".join(extra_lines))
    L.append("</blockquote>")

    L.append("")
    L.append("<blockquote>Enjoy collecting and trading in Summon World!</blockquote>")

    caption = "\n".join(L)

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Refresh", callback_data=f"hstats_refresh_{user_id}"),
            InlineKeyboardButton("🗑 Close", callback_data="close_menu"),
        ],
    ])

    return caption, keyboard


# ==================== /HSTATS COMMAND ====================
async def hstats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    target_id = user_id
    target_first = user.first_name or "User"
    target_username = user.username

    # Optional /hstats @username or /hstats 123456
    if context.args:
        arg = context.args[0].lstrip("@")
        if arg.isdigit():
            target_id = int(arg)
        else:
            conn = get_conn()
            row = conn.execute(
                "SELECT user_id, first_name, username FROM users WHERE username = ?",
                (arg,),
            ).fetchone()
            conn.close()
            if row:
                target_id, target_first, target_username = row

    caption, keyboard = build_hstats_html(target_id, target_first, target_username)
    await update.message.reply_text(
        text=caption, parse_mode=ParseMode.HTML, reply_markup=keyboard
    )


# ==================== REFRESH CALLBACK ====================
from telegram.ext import CallbackQueryHandler


async def hstats_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass

    data = query.data
    user = query.from_user

    # close button
    if data == "close_menu":
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    # refresh button
    if data.startswith("hstats_refresh_"):
        try:
            target_id = int(data.rsplit("_", 1)[1])
        except Exception:
            return

        # only owner can refresh their own
        if user.id != target_id:
            try:
                await query.answer("❌ Not your profile.", show_alert=True)
            except Exception:
                pass
            return

        conn = get_conn()
        row = conn.execute(
            "SELECT first_name, username FROM users WHERE user_id = ?", (target_id,)
        ).fetchone()
        conn.close()

        first_name = (row["first_name"] if row else None) or user.first_name
        username = (row["username"] if row else None) or user.username

        caption, keyboard = build_hstats_html(target_id, first_name, username)

        try:
            await query.message.edit_text(
                text=caption, parse_mode=ParseMode.HTML, reply_markup=keyboard
            )
        except Exception as e:
            logger.warning("edit_text failed: %s", e)


# ==================== REGISTER ====================
def register(app):
    app.add_handler(CommandHandler("hstats", hstats_cmd))
    app.add_handler(CommandHandler("me", hstats_cmd))
    app.add_handler(
        CallbackQueryHandler(hstats_callback_handler, pattern="^hstats_refresh_")
    )
    app.add_handler(
        CallbackQueryHandler(hstats_callback_handler, pattern="^close_menu$")
    )
