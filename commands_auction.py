from storage import connect as db_connect
# ============================================================
# commands_auction.py  —  Anime Auction System v2
# Beautified gallery UI + live-updating pinned message
# ============================================================

import time
import sqlite3
import logging
from html import escape

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from config import DB_NAME
from media_urls import is_allowed_character_image_url

logger = logging.getLogger(__name__)

# ==================== CONFIG ====================
DB = DB_NAME
AUCTION_DURATION = 1800          # 30 min default
MIN_BID_INCREMENT = 100          # fallback min increment
ANTI_SNIPE_EXTEND = 60          # +60s if bid in last 60s


# ==================== HELPERS ====================
def fmt(n: int) -> str:
    return f"{int(n):,}".replace(",", ".")


def progress_bar(percent: int) -> str:
    percent = max(0, min(100, int(percent)))
    filled = percent // 10
    return "▓" * filled + "░" * (10 - filled)


def format_time_left(seconds: float) -> str:
    s = max(0, int(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h > 0:
        return f"{h}h {m:02d}m {sec:02d}s"
    return f"{m}m {sec:02d}s"


def get_char(char_id):
    conn = db_connect(DB)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT id, name, anime, rarity, image_url FROM characters WHERE id = ?",
        (str(char_id),),
    ).fetchone()
    conn.close()
    return {key: row[key] for key in row.keys()} if row else None


def _safe_img(char):
    """Return an approved character image URL or ``None``."""
    if not char:
        return None
    url = (char.get("image_url") or "").strip()
    return url if is_allowed_character_image_url(url) else None


# ==================== UI BUILDERS ====================
def build_auction_caption(auc: dict, char: dict, highest_bidder_name: str = None) -> str:
    start = auc.get("start_price", auc.get("highest_bid", 0))
    cur = auc.get("highest_bid", start)
    total_duration = AUCTION_DURATION
    remaining = max(0, auc["end_time"] - time.time())
    elapsed = total_duration - remaining
    pct = max(0, min(100, int(elapsed / total_duration * 100)))

    name = escape(char.get("name", f"#{auc.get('character_id', '?')}"))
    anime = escape(char.get("anime", "Unknown"))
    rarity = escape(char.get("rarity", "—"))

    seller_id = auc.get("seller_id")
    seller_line = (
        f"👤 Seller: <a href='tg://user?id={seller_id}'>Seller</a>"
        if seller_id else ""
    )

    if auc.get("highest_bidder_id"):
        if highest_bidder_name:
            leader = f"👑 Leading: <b>{escape(highest_bidder_name)}</b>"
        else:
            leader = "👑 Leading: <b>Someone</b>"
    else:
        leader = "👑 Leading: <i>—</i>"

    return (
        f"🔔 <b>𝗔 𝗡 𝗘 𝗪   𝗔 𝗨 𝗖 𝗧 𝗜 𝗢 𝗡</b>\n"
        f"─────────────────────\n\n"
        f"┌─────────────────────┐\n"
        f"│  🎴 <b>{name}</b>\n"
        f"│  ⛩️ <i>{anime}</i>\n"
        f"│  ⭐ Rarity: <b>{rarity}</b>\n"
        f"└─────────────────────┘\n\n"
        f"💰 Starting Bid: <code>{fmt(start)}</code> 🪙\n"
        f"{seller_line}\n"
        f"🔖 Auction ID: <code>#{auc.get('id', '?')}</code>\n\n"
        f"⏳ <b>𝗧𝗶𝗺𝗲 𝗥𝗲𝗺𝗮𝗶𝗻𝗶𝗻𝗴:</b>\n"
        f"  {progress_bar(pct)} {format_time_left(remaining)}\n\n"
        f"🔨 <b>𝗛𝗶𝗴𝗵𝗲𝘀𝘁 𝗕𝗶𝗱:</b> <code>{fmt(cur)}</code> 🪙\n"
        f"{leader}\n\n"
        f"─────────────────────\n"
        f"💡 <i>Tap a button below to bid!</i>"
    )


def build_auction_keyboard(auction_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💵 +500",     callback_data=f"bid_add_{auction_id}_500"),
            InlineKeyboardButton("💰 +1,000",   callback_data=f"bid_add_{auction_id}_1000"),
        ],
        [
            InlineKeyboardButton("💎 +5,000",   callback_data=f"bid_add_{auction_id}_5000"),
            InlineKeyboardButton("🔥 +10,000",  callback_data=f"bid_add_{auction_id}_10000"),
        ],
        [
            InlineKeyboardButton("✏️ Custom Bid", callback_data=f"bid_custom_{auction_id}"),
            InlineKeyboardButton("❌ Close",      callback_data="close_menu"),
        ],
    ])


async def _send_auction_photo(context, chat_id, img_input, caption, keyboard):
    """Send an approved Catbox/ImgBB character image or a text fallback."""
    if is_allowed_character_image_url(img_input):
        try:
            return await context.bot.send_photo(
                chat_id=chat_id, photo=img_input,
                caption=caption, parse_mode=ParseMode.HTML, reply_markup=keyboard,
            )
        except Exception as e:
            logger.warning("send_photo failed (%s) — fallback to text", e)

    return await context.bot.send_message(
        chat_id=chat_id, text=caption,
        parse_mode=ParseMode.HTML, reply_markup=keyboard,
    )


async def _update_pinned_message(context, auc: dict, char: dict, keyboard, highest_bidder_name=None):
    """Live-update the pinned auction message in chat."""
    if not auc.get("pinned_msg_id") or not auc.get("chat_id"):
        return
    try:
        await context.bot.edit_message_caption(
            chat_id=auc["chat_id"],
            message_id=auc["pinned_msg_id"],
            caption=build_auction_caption(auc, char, highest_bidder_name),
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.warning("pinned edit failed: %s", e)


# ==================== DB SCHEMA ====================
def ensure_auction_tables():
    conn = db_connect(DB)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS auctions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id    TEXT    NOT NULL,
            seller_id       INTEGER NOT NULL,
            start_price     INTEGER NOT NULL,
            highest_bid     INTEGER NOT NULL,
            highest_bidder_id INTEGER,
            chat_id         INTEGER,
            pinned_msg_id   INTEGER,
            created_at      REAL    NOT NULL,
            end_time        REAL    NOT NULL,
            status          TEXT    DEFAULT 'active'
        );

        CREATE TABLE IF NOT EXISTS auction_bid_input (
            user_id     INTEGER PRIMARY KEY,
            auction_id  INTEGER NOT NULL,
            created_at  REAL    NOT NULL
        );
    """)
    conn.commit()
    conn.close()
    logger.info("auction tables ready")


# ==================== START AUCTION ====================
async def cmd_auction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usage: /auction <char_id> <start_price> [duration_minutes]"""
    ensure_auction_tables()

    user = update.effective_user
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "❌ <b>Usage:</b> <code>/auction &lt;char_id&gt; &lt;start_price&gt; [minutes]</code>\n"
            "Example: <code>/auction 05 5000 30</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    char_id = str(args[0])
    try:
        start_price = int(args[1])
    except ValueError:
        await update.message.reply_text("❌ Start price must be a number.")
        return

    if start_price < 100:
        await update.message.reply_text("❌ Min starting bid: 100 🪙")
        return

    duration_min = 30
    if len(args) >= 3:
        try:
            duration_min = max(5, min(180, int(args[2])))
        except ValueError:
            pass

    char = get_char(char_id)
    if not char:
        await update.message.reply_text(f"❌ Character <code>#{char_id}</code> not found.")
        return

    conn = db_connect(DB)
    try:
        owned = conn.execute(
            "SELECT 1 FROM user_collection WHERE user_id = ? AND character_id = ?",
            (user.id, char_id),
        ).fetchone()
        if not owned:
            await update.message.reply_text(
                f"❌ You don't own character <code>#{char_id}</code>.",
                parse_mode=ParseMode.HTML,
            )
            return

        now = time.time()
        end_time = now + (duration_min * 60)
        cur = conn.execute(
            """INSERT INTO auctions
               (character_id, seller_id, start_price, highest_bid,
                highest_bidder_id, chat_id, created_at, end_time, status)
               VALUES (?, ?, ?, ?, NULL, ?, ?, ?, 'active')
               RETURNING id""",
            (char_id, user.id, start_price, start_price, update.effective_chat.id, now, end_time),
        )
        inserted = cur.fetchone()
        if not inserted:
            raise RuntimeError("Auction insert did not return an ID")
        auc_id = inserted[0]
        conn.execute(
            "DELETE FROM user_collection WHERE user_id = ? AND character_id = ?",
            (user.id, char_id),
        )
        conn.commit()
    finally:
        conn.close()

    auc = {
        "id": auc_id,
        "character_id": char_id,
        "seller_id": user.id,
        "start_price": start_price,
        "highest_bid": start_price,
        "highest_bidder_id": None,
        "chat_id": update.effective_chat.id,
        "pinned_msg_id": None,
        "end_time": end_time,
    }
    caption = build_auction_caption(auc, char, None)
    keyboard = build_auction_keyboard(auc_id)
    msg = await _send_auction_photo(
        context, update.effective_chat.id, _safe_img(char), caption, keyboard
    )

    conn = db_connect(DB)
    try:
        conn.execute("UPDATE auctions SET pinned_msg_id = ? WHERE id = ?", (msg.message_id, auc_id))
        conn.commit()
    finally:
        conn.close()

    try:
        await context.bot.pin_chat_message(
            chat_id=update.effective_chat.id,
            message_id=msg.message_id,
            disable_notification=True,
        )
    except Exception as e:
        logger.warning("pin failed: %s", e)

    await context.bot.send_message(
        chat_id=user.id,
        text=(
            f"✅ <b>Auction #{auc_id} listed!</b>\n"
            f"🎴 <b>{char['name']}</b> ({char['rarity']})\n"
            f"⏳ Duration: {duration_min} min"
        ),
        parse_mode=ParseMode.HTML,
    )


# ==================== PLACE BID (CALLBACK) ====================
async def cb_place_bid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    parts = data.split("_")
    if len(parts) != 4:
        return

    try:
        auction_id = int(parts[2])
        add_amount = int(parts[3])
    except ValueError:
        return

    user = query.from_user
    now = time.time()

    conn = db_connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        auc = conn.execute(
            "SELECT * FROM auctions WHERE id = ? AND status = 'active'",
            (auction_id,),
        ).fetchone()
        if not auc:
            await query.answer("❌ Auction not active.", show_alert=True)
            return
        auc = dict(auc)

        if auc["end_time"] <= now:
            await query.answer("⏰ Auction ended.", show_alert=True)
            return

        if auc["seller_id"] == user.id:
            await query.answer("🚫 You can't bid on your own auction.", show_alert=True)
            return

        new_bid = auc["highest_bid"] + add_amount

        bal = conn.execute(
            "SELECT balance FROM users WHERE user_id = ?", (user.id,)
        ).fetchone()
        if not bal or bal["balance"] < new_bid:
            await query.answer(
                f"❌ Need {fmt(new_bid)} 🪙 — you have {fmt(bal['balance'] if bal else 0)} 🪙.",
                show_alert=True,
            )
            return

        char = get_char(auc["character_id"])
        if not char:
            await query.answer("❌ Character missing.", show_alert=True)
            return

        prev_bidder = auc.get("highest_bidder_id")
        prev_top_username = None
        if prev_bidder:
            prev_row = conn.execute(
                "SELECT username FROM users WHERE user_id = ?", (prev_bidder,)
            ).fetchone()
            prev_top_username = prev_row["username"] if prev_row else None

        new_end = auc["end_time"]
        if auc["end_time"] - now < ANTI_SNIPE_EXTEND:
            new_end = now + ANTI_SNIPE_EXTEND
            await query.answer("⚡ Anti-snipe: +60s added!", show_alert=False)

        conn.execute(
            """UPDATE auctions
               SET highest_bid = ?, highest_bidder_id = ?, end_time = ?
               WHERE id = ?""",
            (new_bid, user.id, new_end, auction_id),
        )
        conn.execute(
            """INSERT INTO auction_bids (auction_id, bidder_id, amount, bid_time)
               VALUES (?, ?, ?, ?)""",
            (auction_id, user.id, new_bid, now),
        )
        conn.commit()

        top_username = user.username or user.first_name
        auc["highest_bid"] = new_bid
        auc["highest_bidder_id"] = user.id
        auc["end_time"] = new_end
        caption = build_auction_caption(auc, char, top_username)
        keyboard = build_auction_keyboard(auction_id)

        try:
            await query.message.edit_caption(
                caption=caption, parse_mode=ParseMode.HTML, reply_markup=keyboard
            )
        except Exception as e:
            logger.warning("edit clicked caption failed: %s", e)

        await _update_pinned_message(context, auc, char, keyboard, top_username)

        if prev_bidder and prev_bidder != user.id:
            try:
                await context.bot.send_message(
                    chat_id=prev_bidder,
                    text=(
                        f"⚡ <b>𝗬𝗢𝗨 𝗪𝗘𝗥𝗘 𝗢𝗨𝗧𝗕𝗜𝗗!</b>\n\n"
                        f"🎴 <b>{char['name']}</b> ({char['rarity']})\n"
                        f"💰 Your bid: <code>{fmt(auc['highest_bid'] - add_amount)}</code> 🪙\n"
                        f"🔥 New high: <code>{fmt(new_bid)}</code> 🪙\n"
                        f"👤 By: <b>@{escape(user.username or user.first_name)}</b>\n\n"
                        f"⏳ Time left: <b>{format_time_left(new_end - now)}</b>"
                    ),
                    parse_mode=ParseMode.HTML,
                )
            except Exception as e:
                logger.warning("outbid PM failed: %s", e)

    finally:
        conn.close()


# ==================== CUSTOM BID PROMPT ====================
async def cb_custom_bid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    parts = data.split("_")
    if len(parts) != 3:
        return
    try:
        auction_id = int(parts[2])
    except ValueError:
        return

    conn = db_connect(DB)
    try:
        conn.execute(
            """INSERT INTO auction_bid_input (user_id, auction_id, created_at)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET auction_id = ?, created_at = ?""",
            (query.from_user.id, auction_id, time.time(), auction_id, time.time()),
        )
        conn.commit()
    finally:
        conn.close()

    try:
        await query.message.reply_text(
            f"✏️ <b>Enter your bid for auction #{auction_id}:</b>\n"
            f"Reply with just the number (e.g. <code>7500</code>).",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.warning("custom bid prompt failed: %s", e)


# ==================== CUSTOM BID INPUT (TEXT HANDLER) ====================
async def handle_custom_bid_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    now = time.time()

    conn = db_connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT auction_id, created_at FROM auction_bid_input WHERE user_id = ?",
            (user.id,),
        ).fetchone()
        if not row:
            return
        if now - row["created_at"] > 120:
            conn.execute("DELETE FROM auction_bid_input WHERE user_id = ?", (user.id,))
            conn.commit()
            return
        auction_id = row["auction_id"]
        conn.execute("DELETE FROM auction_bid_input WHERE user_id = ?", (user.id,))
        conn.commit()
    finally:
        conn.close()

    text = (update.message.text or "").strip().replace(".", "").replace(",", "")
    if not text.isdigit():
        await update.message.reply_text("❌ Enter a valid number.")
        return
    new_bid = int(text)

    conn = db_connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        auc = conn.execute(
            "SELECT * FROM auctions WHERE id = ? AND status = 'active'", (auction_id,)
        ).fetchone()
        if not auc:
            await update.message.reply_text("❌ Auction not active.")
            return
        auc = dict(auc)

        if auc["end_time"] <= time.time():
            await update.message.reply_text("⏰ Auction ended.")
            return
        if auc["seller_id"] == user.id:
            await update.message.reply_text("🚫 Can't bid on your own auction.")
            return
        if new_bid <= auc["highest_bid"]:
            await update.message.reply_text(
                f"❌ Must beat current bid <code>{fmt(auc['highest_bid'])}</code> 🪙.",
                parse_mode=ParseMode.HTML,
            )
            return

        bal = conn.execute("SELECT balance FROM users WHERE user_id = ?", (user.id,)).fetchone()
        if not bal or bal["balance"] < new_bid:
            await update.message.reply_text(
                f"❌ Need {fmt(new_bid)} 🪙 — you have {fmt(bal['balance'] if bal else 0)} 🪙."
            )
            return

        char = get_char(auc["character_id"])
        if not char:
            await update.message.reply_text("❌ Character missing.")
            return

        prev_bidder = auc["highest_bidder_id"]
        new_end = auc["end_time"]
        if new_end - time.time() < ANTI_SNIPE_EXTEND:
            new_end = time.time() + ANTI_SNIPE_EXTEND

        conn.execute(
            """UPDATE auctions
               SET highest_bid = ?, highest_bidder_id = ?, end_time = ?
               WHERE id = ?""",
            (new_bid, user.id, new_end, auction_id),
        )
        conn.execute(
            """INSERT INTO auction_bids (auction_id, bidder_id, amount, bid_time)
               VALUES (?, ?, ?, ?)""",
            (auction_id, user.id, new_bid, time.time()),
        )
        conn.commit()

        auc["highest_bid"] = new_bid
        auc["highest_bidder_id"] = user.id
        auc["end_time"] = new_end
        caption = build_auction_caption(auc, char, user.username or user.first_name)
        keyboard = build_auction_keyboard(auction_id)

        if auc.get("pinned_msg_id") and auc.get("chat_id"):
            try:
                await context.bot.edit_message_caption(
                    chat_id=auc["chat_id"], message_id=auc["pinned_msg_id"],
                    caption=caption, parse_mode=ParseMode.HTML, reply_markup=keyboard,
                )
            except Exception as e:
                logger.warning("custom pinned edit failed: %s", e)

        await update.message.reply_text(
            f"✅ <b>Bid placed!</b>\n"
            f"🎴 <b>{char['name']}</b>\n"
            f"💰 Your bid: <code>{fmt(new_bid)}</code> 🪙",
            parse_mode=ParseMode.HTML,
        )

        if prev_bidder and prev_bidder != user.id:
            try:
                await context.bot.send_message(
                    chat_id=prev_bidder,
                    text=(
                        f"⚡ <b>𝗬𝗢𝗨 𝗪𝗘𝗥𝗘 𝗢𝗨𝗧𝗕𝗜𝗗!</b>\n\n"
                        f"🎴 <b>{char['name']}</b> ({char['rarity']})\n"
                        f"💰 New high: <code>{fmt(new_bid)}</code> 🪙\n"
                        f"👤 By: <b>@{escape(user.username or user.first_name)}</b>"
                    ),
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass
    finally:
        conn.close()


# ==================== ACTIVE AUCTIONS LIST ====================
async def cmd_auction_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_auction_tables()
    chat_id = update.effective_chat.id
    now = time.time()

    conn = db_connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT a.*, c.name AS c_name, c.rarity AS c_rarity
               FROM auctions a
               LEFT JOIN characters c ON c.id = a.character_id
               WHERE a.status = 'active' AND a.end_time > ?
               ORDER BY a.end_time ASC LIMIT 20""",
            (now,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        await update.message.reply_text(
            "📭 <b>No active auctions right now.</b>\n"
            "💡 Start one: <code>/auction &lt;char_id&gt; &lt;price&gt;</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    lines = ["🔔 <b>𝗔 𝗖 𝘁 𝗶 𝘃 𝗲   𝗔 𝘂 𝗰 𝘁 𝗶 𝗼 𝗻 𝘀</b>\n─────────────────────"]
    kb = []
    for r in rows[:10]:
        d = dict(r)
        name = escape(d.get("c_name") or f"#{d['character_id']}")
        rarity = escape(d.get("c_rarity") or "—")
        rem = d["end_time"] - now
        pct = max(0, min(100, int((AUCTION_DURATION - rem) / AUCTION_DURATION * 100)))

        lines.append(
            f"\n🔨 <code>#{d['id']}</code> • <b>{name}</b> (<b>{rarity}</b>)\n"
            f"   💰 <code>{fmt(d['highest_bid'])}</code> 🪙 • ⏳ {format_time_left(rem)}\n"
            f"   {progress_bar(pct)} {pct}%"
        )
        kb.append([InlineKeyboardButton(
            f"👀 #{d['id']} • {name[:18]}",
            callback_data=f"view_auc_{d['id']}",

        )])

    lines.append("\n─────────────────────")
    lines.append("💡 <i>Tap to view & bid</i>")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(kb) if kb else None,
    )


# ==================== MY BIDS ====================
async def cmd_mybids(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    now = time.time()

    conn = db_connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT a.id, a.highest_bid, a.end_time, a.character_id,
                       a.highest_bidder_id, c.name AS c_name, c.rarity AS c_rarity
               FROM auctions a
               LEFT JOIN characters c ON c.id = a.character_id
               WHERE a.status = 'active' AND a.end_time > ?
                 AND a.id IN (SELECT DISTINCT auction_id FROM auction_bids WHERE bidder_id = ?)
               ORDER BY a.end_time ASC LIMIT 20""",
            (now, user.id),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        await update.message.reply_text(
            "📭 <b>You haven't bid on anything active.</b>",
            parse_mode=ParseMode.HTML,
        )
        return

    lines = ["📜 <b>𝗠 𝘆   𝗕 𝗶 𝗱 𝘀</b>\n─────────────────────"]
    for r in rows:
        d = dict(r)
        name = escape(d.get("c_name") or f"#{d['character_id']}")
        marker = "👑" if d["highest_bidder_id"] == user.id else "👀"
        lines.append(
            f"\n{marker} <code>#{d['id']}</code> • <b>{name}</b> ({escape(d.get('c_rarity') or '—')})\n"
            f"   💰 Current: <code>{fmt(d['highest_bid'])}</code> 🪙 • "
            f"⏳ {format_time_left(d['end_time'] - now)}"
        )
    lines.append("\n─────────────────────")
    lines.append("👑 = you're winning • 👀 = you've been outbid")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


# ==================== CANCEL ====================
async def cmd_cancel_auction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args or []
    if not args or not args[0].isdigit():
        await update.message.reply_text("❌ Usage: <code>/cancelauction &lt;id&gt;</code>", parse_mode=ParseMode.HTML)
        return
    auction_id = int(args[0])

    conn = db_connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        auc = conn.execute("SELECT * FROM auctions WHERE id = ? AND status = 'active'", (auction_id,)).fetchone()
        if not auc:
            await update.message.reply_text("❌ Auction not active.")
            return
        auc = dict(auc)
        if auc["seller_id"] != user.id:
            await update.message.reply_text("🚫 Not your auction.")
            return
        bid_count = conn.execute(
            "SELECT COUNT(*) AS c FROM auction_bids WHERE auction_id = ?", (auction_id,)
        ).fetchone()["c"]
        if bid_count > 0:
            await update.message.reply_text("❌ Already has bids — can't cancel.")
            return

        conn.execute(
            "INSERT OR IGNORE INTO user_collection (user_id, character_id) VALUES (?, ?)",
            (user.id, auc["character_id"]),
        )
        conn.execute("UPDATE auctions SET status = 'cancelled' WHERE id = ?", (auction_id,))
        conn.commit()
    finally:
        conn.close()

    if auc.get("pinned_msg_id") and auc.get("chat_id"):
        try:
            await context.bot.unpin_chat_message(
                chat_id=auc["chat_id"], message_id=auc["pinned_msg_id"]
            )
        except Exception as e:
            logger.warning("unpin cancel failed: %s", e)

    await update.message.reply_text(
        f"✅ <b>Auction #{auction_id} cancelled.</b>\n"
        f"🎴 Character returned to your inventory.",
        parse_mode=ParseMode.HTML,
    )


# ==================== AUTO-CLOSE (JOB) ====================
async def job_close_auctions(context: ContextTypes.DEFAULT_TYPE):
    """Runs every 10s — closes ended auctions, transfers coins & char."""
    now = time.time()
    conn = db_connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT * FROM auctions
               WHERE status = 'active' AND end_time <= ?
               ORDER BY end_time ASC LIMIT 20""",
            (now,),
        ).fetchall()
    finally:
        conn.close()

    for r in rows:
        auc = dict(r)
        await _close_auction(context, auc, reason="ended")


async def _close_auction(context, auc: dict, reason: str = "ended"):
    auction_id = auc["id"]
    char = get_char(auc["character_id"])

    conn = db_connect(DB)
    try:
        conn.execute("UPDATE auctions SET status = 'closed' WHERE id = ?", (auction_id,))
        conn.commit()
    finally:
        conn.close()

    if auc.get("pinned_msg_id") and auc.get("chat_id"):
        try:
            await context.bot.unpin_chat_message(
                chat_id=auc["chat_id"], message_id=auc["pinned_msg_id"]
            )
        except Exception as e:
            logger.warning("unpin close failed: %s", e)

    if not auc.get("highest_bidder_id") or not char:
        try:
            await context.bot.send_message(
                chat_id=auc["chat_id"],
                text=(
                    f"📭 <b>Auction #{auction_id} ended</b> with no bids.\n"
                    f"🎴 <b>{char['name'] if char else '?'}</b> returned to seller."
                ),
                parse_mode=ParseMode.HTML,
            )
            if char:
                conn = db_connect(DB)
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO user_collection (user_id, character_id) VALUES (?, ?)",
                        (auc["seller_id"], auc["character_id"]),
                    )
                    conn.commit()
                finally:
                    conn.close()
        except Exception as e:
            logger.warning("no-bid close notice failed: %s", e)
        return

    winner_id = auc["highest_bidder_id"]
    final_price = auc["highest_bid"]

    conn = db_connect(DB)
    try:
        conn.execute(
            "UPDATE users SET balance = balance - ? WHERE user_id = ?",
            (final_price, winner_id),
        )
        conn.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (final_price, auc["seller_id"]),
        )
        conn.execute(
            "INSERT OR IGNORE INTO user_collection (user_id, character_id) VALUES (?, ?)",
            (winner_id, auc["character_id"]),
        )
        conn.commit()
    finally:
        conn.close()

    seller_name = auc.get("seller_id")
    try:
        await context.bot.send_message(
            chat_id=auc["chat_id"],
            text=(
                f"🏆 <b>𝗖 𝗢 𝗡 𝗚 𝗥 𝗔 𝗧 𝗦 !</b>\n"
                f"─────────────────────\n\n"
                f"🎉 <b>Auction #{auction_id} won!</b>\n\n"
                f"┌─────────────────────┐\n"
                f"│  🎴 <b>{char['name']}</b>\n"
                f"│  ⛩️ <i>{char['anime']}</i>\n"
                f"│  ⭐ Rarity: <b>{char['rarity']}</b>\n"
                f"└─────────────────────┘\n\n"
                f"💰 Final price: <code>{fmt(final_price)}</code> 🪙\n"
                f"👤 Seller: <a href='tg://user?id={auc['seller_id']}'>Seller</a>\n\n"
                f"📦 <b>Character added to winner's inventory!</b>"
            ),
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.warning("win notice failed: %s", e)

    try:
        await context.bot.send_message(
            chat_id=winner_id,
            text=(
                f"🏆 <b>You won auction #{auction_id}!</b>\n"
                f"🎴 <b>{char['name']}</b> ({char['rarity']})\n"
                f"💰 Paid: <code>{fmt(final_price)}</code> 🪙\n"
                f"📦 Added to your inventory."
            ),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass


# ==================== CALLBACK: VIEW AUCTION ====================
async def cb_view_auction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = (query.data or "").split("_")
    if len(parts) != 3 or parts[0] != "view":
        return
    try:
        auction_id = int(parts[2])
    except ValueError:
        return

    conn = db_connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        auc = conn.execute("SELECT * FROM auctions WHERE id = ?", (auction_id,)).fetchone()
    finally:
        conn.close()
    if not auc:
        await query.answer("❌ Auction not found.", show_alert=True)
        return
    auc = dict(auc)
    if auc["status"] != "active" or auc["end_time"] <= time.time():
        await query.answer("⏰ Auction ended.", show_alert=True)
        return

    char = get_char(auc["character_id"])
    if not char:
        return
    top_username = None
    if auc.get("highest_bidder_id"):
        conn = db_connect(DB)
        try:
            r = conn.execute("SELECT username FROM users WHERE user_id = ?", (auc["highest_bidder_id"],)).fetchone()
            top_username = r["username"] if r else None
        finally:
            conn.close()

    caption = build_auction_caption(auc, char, top_username)
    keyboard = build_auction_keyboard(auction_id)
    img = _safe_img(char)
    if img:
        try:
            await context.bot.send_photo(
                chat_id=query.from_user.id, photo=img,
                caption=caption, parse_mode=ParseMode.HTML, reply_markup=keyboard,
            )
            return
        except Exception:
            pass
    await context.bot.send_message(
        chat_id=query.from_user.id,
        text=caption, parse_mode=ParseMode.HTML, reply_markup=keyboard,
    )


# ==================== CLOSE MENU CALLBACK ====================
async def cb_close_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Closed", show_alert=False)
    try:
        await query.message.delete()
    except Exception:
        pass


# ==================== HANDLER REGISTRATION ====================
def register(app):
    ensure_auction_tables()
    app.add_handler(CommandHandler("auction", cmd_auction))
    app.add_handler(CommandHandler("cancelauction", cmd_cancel_auction))
    app.add_handler(CommandHandler("auctionlist", cmd_auction_list))
    app.add_handler(CommandHandler("auction_list", cmd_auction_list))
    app.add_handler(CommandHandler("mybids", cmd_mybids))
    app.add_handler(CallbackQueryHandler(cb_place_bid, pattern=r"^bid_add_\d+_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_custom_bid, pattern=r"^bid_custom_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_view_auction, pattern=r"^view_auc_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_close_menu, pattern=r"^close_menu$"))

    group = 5
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        handle_custom_bid_input,
    ), group=group)
    logger.info("auction handlers registered (group=%d)", group)
