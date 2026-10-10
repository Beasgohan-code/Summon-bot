"""
auto_spawn.py
=============
Isolated spawn logic module.

  • trigger_spawn()         — manual /spawn (owner-only). PURE RANDOM from full DB.
  • trigger_weighted_spawn() — auto-spawn path. Uses get_rarity() weights from /chance.
  • hint_callback()         — "💡 Hint" inline button (one-shot per spawn).
  • auto_spawn_watcher()    — counts group messages, calls trigger_weighted_spawn() at limit.

Reuses:
  • get_rarity()           — from commands_admin.py (weighted rarity pick)
  • get_random_character() — from commands_admin.py (random char from that rarity)
  • send_character_media() — from commands_user.py (media sending)

Self-contained. Delete this file → bot still works.
"""
from storage import connect as db_connect

import logging
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import DB_NAME, OWNER_ID

from commands_user import send_character_media

logger = logging.getLogger(__name__)


# ==========================
# HELPERS
# ==========================
def _get_global(name):
    """Get a globally-defined function (e.g. from commands_admin.py)."""
    import builtins
    fn = getattr(builtins, name, None) or globals().get(name)
    if fn is None:
        import sys
        for mod in sys.modules.values():
            fn = getattr(mod, name, None)
            if fn is not None:
                return fn
    return fn


def _pick_random_character():
    """Pick any random character from full DB. (Manual /spawn)"""
    conn = db_connect(DB_NAME)
    cursor = conn.cursor()
    
    # 🎯 FIX: Using SELECT * and handling the tuple safely later
    cursor.execute("SELECT * FROM characters ORDER BY RANDOM() LIMIT 1")
    char = cursor.fetchone()
    conn.close()
    return char


def _pick_weighted_character():
    """
    Auto-spawn picker. Uses rarity_chances weights (set via /chance).
    Logic: get_rarity() → weighted pick of rarity_name → random char from that rarity.
    Falls back to any random char if the chosen rarity is empty.
    """
    get_random_character = _get_global("get_random_character")
    if get_random_character is None:
        logger.warning("get_random_character not found in globals, using pure random")
        return _pick_random_character()

    try:
        char = get_random_character()
        return char
    except Exception as e:
        logger.error(f"get_random_character() failed: {e}")
        return _pick_random_character()


async def _post_spawn(context, chat_id, char, source: str = "manual"):
    """
    Common posting logic: save spawn state + send media with hint button.
    `source` is just for logging: 'manual' | 'auto'.
    """
    if not char:
        logger.warning(f"[{source}] No character returned for chat {chat_id}")
        return

    # 🎯 FIX: Safe Unpacking!
    # No matter how many columns your DB returns, we grab the first 5 and ignore the rest.
    try:
        char_id = char[0]
        name = char[1]
        anime = char[2]
        rarity = char[3]
        image_url = char[4]
    except IndexError:
        logger.error(f"[{source}] Database row does not have 5 columns! Row data: {char}")
        return

    # Save state for /summon
    context.chat_data["active_spawn"] = {
        "id": char_id,
        "name": name.strip().lower(),
        "claimed": False,
    }
    context.bot_data["last_spawn"] = {"char_id": char_id, "chat_id": chat_id}

    text = (
        "🌠 <b>A Character has been spawned!</b>\n\n"
        "<blockquote>"
        f"🎌 <b>Anime:</b> {anime}\n"
        f"🏅 <b>Rarity:</b> {rarity}\n\n"
        f"⚡ Type <code>/summon [name]</code> to catch!"
        "</blockquote>"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💡 Hint", callback_data=f"hint_{chat_id}_{char_id}")]
    ])

    media_sent = False
    
    # Try to use send_character_media from commands_user.py
    media_sender = _get_global("send_character_media") or send_character_media
    if media_sender is not None:
        try:
            await media_sender(
                bot=context.bot,
                chat_id=chat_id,
                image_url=image_url,
                caption=text,
                reply_markup=keyboard,
            )
            media_sent = True
        except Exception as e:
            logger.error(f"[{source}] send_character_media failed: {e}")

    # Fallback: text-only message if media failed
    if not media_sent:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
        except Exception as e:
            logger.error(f"[{source}] text fallback failed: {e}")



# ==========================
# MANUAL /SPAWN (owner-only, pure random)
# ==========================
async def trigger_spawn(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int = None):
    if update is not None and chat_id is None:
        if update.effective_user.id != OWNER_ID:
            return await update.message.reply_text("❌ Restricted Command!")

    if chat_id is None:
        chat_id = update.effective_chat.id

    char = _pick_random_character()
    if not char:
        if update:
            await update.message.reply_text("❌ No characters in database.")
        return

    await _post_spawn(context, chat_id, char, source="manual")


# ==========================
# AUTO-SPAWN (weighted by /chance)
# ==========================
async def trigger_weighted_spawn(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    char = _pick_weighted_character()
    if not char:
        logger.warning(f"[auto] Weighted pick returned None for chat {chat_id}")
        return

    await _post_spawn(context, chat_id, char, source="auto")


# ==========================
# HINT BUTTON CALLBACK (UPDATED WITH POPUP ALERT)
# ==========================
async def hint_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reveal first letter + length of active spawn via a beautiful popup alert."""
    query = update.callback_query

    parts = query.data.split("_")
    if len(parts) < 3:
        await query.answer()
        return
    try:
        target_chat = int(parts[1])
    except ValueError:
        await query.answer()
        return

    if query.message.chat.id != target_chat:
        await query.answer("❌ This button is not for you!", show_alert=True)
        return

    active = context.chat_data.get("active_spawn")
    if not active or active.get("claimed"):
        await query.answer("❌ No active spawn or already claimed!", show_alert=True)
        return

    name = active["name"]
    first_letter = name[0].upper() if name else "?"
    
    
    blanks = "_" * (len(name) - 1)

    
    alert_text = (
        "Ｓᴜᴍᴍᴏɴ Ｂᴏᴛ\n\n"
        f"🔍 HINT: {first_letter}{blanks}\n\n"
    )

    
    try:
        await query.answer(text=alert_text, show_alert=True)
    except Exception as e:
        logger.error(f"Alert hint failed: {e}")
        await query.answer() # Fallback to clear loading state

    
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass



# ==========================
# AUTO-SPAWN WATCHER
# ==========================
async def auto_spawn_watcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.type not in ("group", "supergroup"):
        return
    if update.effective_user.is_bot:
        return
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id

    conn = db_connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT message_count, spawn_limit FROM group_settings WHERE chat_id = ?",
        (chat_id,),
    )
    row = cursor.fetchone()

    if not row:
        cursor.execute(
            "INSERT INTO group_settings (chat_id, message_count, spawn_limit) VALUES (?, 1, 100)",
            (chat_id,),
        )
        conn.commit()
        conn.close()
        return

    current_count, spawn_limit = row
    new_count = current_count + 1

    if new_count >= spawn_limit:
        cursor.execute("UPDATE group_settings SET message_count = 0 WHERE chat_id = ?", (chat_id,))
        conn.commit()
        conn.close()
        logger.info(f"[auto-spawn] {chat_id}: threshold {spawn_limit} reached, firing spawn")

        if context.chat_data.get("active_spawn") and not context.chat_data["active_spawn"].get("claimed"):
            return

        try:
            await trigger_weighted_spawn(context, chat_id)
        except Exception as e:
            logger.error(f"auto-spawn failed in {chat_id}: {e}")
    else:
        cursor.execute(
            "UPDATE group_settings SET message_count = ? WHERE chat_id = ?",
            (new_count, chat_id),
        )
        conn.commit()
        conn.close()


# ==========================
# REGISTRATION HELPER
# ==========================
def register(application):
    from telegram.ext import MessageHandler, CallbackQueryHandler, filters

    application.add_handler(CallbackQueryHandler(hint_callback, pattern=r"^hint_"))
    application.add_handler(
        MessageHandler(filters.ChatType.GROUPS & ~filters.COMMAND, auto_spawn_watcher),
        group=999,
    )

