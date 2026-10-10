import os
import sys
import logging
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import OWNER_ID, OWNER_PANEL_PASSWORD
from database import (
    execute, fetch_one, fetch_all, fetch_value,
    get_total_users, get_total_coins, get_total_groups, get_character_count,
)

logger = logging.getLogger(__name__)

# ==========================================
# 🔐 CONFIGURATION
# ==========================================
OWNER_ID = int(OWNER_ID) if OWNER_ID is not None else 0

# Set to keep track of authenticated owners
owner_auth = set()


# ==========================================
# 🔑 THE NUMPAD KEYBOARD LAYOUT
# ==========================================
def get_numpad_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("1", callback_data="op_1"),
            InlineKeyboardButton("2", callback_data="op_2"),
            InlineKeyboardButton("3", callback_data="op_3"),
        ],
        [
            InlineKeyboardButton("4", callback_data="op_4"),
            InlineKeyboardButton("5", callback_data="op_5"),
            InlineKeyboardButton("6", callback_data="op_6"),
        ],
        [
            InlineKeyboardButton("7", callback_data="op_7"),
            InlineKeyboardButton("8", callback_data="op_8"),
            InlineKeyboardButton("9", callback_data="op_9"),
        ],
        [
            InlineKeyboardButton("❌ Clear", callback_data="op_clear"),
            InlineKeyboardButton("0", callback_data="op_0"),
            InlineKeyboardButton("✔️ Login", callback_data="op_done"),
        ]
    ])


# ==========================================
# 👑 OWNER ENTRY COMMAND (/owner)
# ==========================================
async def owner_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return  # Non-owners silent block
    if not OWNER_PANEL_PASSWORD:
        return await update.message.reply_text(
            "❌ Owner panel is disabled until OWNER_PANEL_PASSWORD is configured."
        )

    text = (
        "🔐 <b>OWNER ACCESS PANEL</b>\n\n"
        "<blockquote>Please tap the unlock button below to verify your password.</blockquote>"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔓 Unlock Panel", callback_data="op_start")]
    ])

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


# ==========================================
# 🎮 CALLBACK HANDLER FOR NUMPAD & MENUS
# ==========================================
async def ownerpanel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    data = query.data

    # Security Guard: Only the actual owner can click these numpad/panel buttons
    if uid != OWNER_ID:
        return await query.answer("❌ This panel is restricted!", show_alert=True)

    # 1️⃣ START AUTHENTICATION
    if data == "op_start":
        await query.answer()
        context.user_data["op_password"] = ""
        
        return await query.message.edit_text(
            "🔐 <b>Enter Password:</b>\n\n<i>Waiting for input...</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_numpad_keyboard()
        )

    # 2️⃣ SUB-MENU NAVIGATION ACTIONS (Authenticated Only)
    elif data in ["op_char", "op_users", "op_economy", "op_broadcast", "op_system", "op_back_panel"]:
        await query.answer()

        # Security Bypass: If somehow not authenticated, force login again
        if uid not in owner_auth:
            return await query.message.edit_text(
                "❌ <b>Session Expired!</b> Please unlock again.",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔓 Unlock Panel", callback_data="op_start")]])
            )

        # Back to Main Panel
        if data == "op_back_panel":
            return await open_panel(query)

        # Common Back Button for all Submenus
        back_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Panel", callback_data="op_back_panel")]])

        # 🎴 Character System Menu
        if data == "op_char":
            text = (
                "🎴 <b>CHARACTER SYSTEM</b>\n\n"
                "<blockquote>"
                "/gen — Generate character\n"
                "/upload — Upload new character\n"
                "/update — Update existing character\n"
                "/delete — Delete character\n"
                "/spawn — Spawn character manually"
                "</blockquote>"
            )
            return await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=back_keyboard)

        # 👥 User Management Menu
        elif data == "op_users":
            text = (
                "👥 <b>USER MANAGEMENT</b>\n\n"
                "<blockquote>"
                "/remove — Remove a character\n"
                "/removeall — Remove all characters\n"
                "/transfer — Transfer characters\n"
                "/claimlist — Check user claim history"
                "</blockquote>"
            )
            return await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=back_keyboard)

        # 💰 Economy Menu
        elif data == "op_economy":
            text = (
                "💰 <b>ECONOMY COMMANDS</b>\n\n"
                "<blockquote>"
                "/give — Give items or balance\n"
                "/givemoney — Gift balance to user\n"
                "/rmmoney — Remove balance from user"
                "</blockquote>"
            )
            return await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=back_keyboard)

        # 📢 Broadcast Menu
        elif data == "op_broadcast":
            text = (
                "📢 <b>BROADCAST SYSTEM</b>\n\n"
                "<blockquote>"
                "/broadcast — Send a global notification to all users"
                "</blockquote>"
            )
            return await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=back_keyboard)

        # 🎰 System Settings Menu
        elif data == "op_system":
            text = (
                "🎰 <b>SYSTEM SETTINGS</b>\n\n"
                "<blockquote>"
                "/chance — View claim/drop chances\n"
                "/setclaim — Configure claim options\n"
                "/chancelist — View detailed drop probabilities"
                "</blockquote>"
            )
            return await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=back_keyboard)

    # 3️⃣ NUMPAD PASSCODE ACTIONS (Digiting, Clears, Verifies)
    elif data.startswith("op_"):
        await query.answer()
        password = context.user_data.get("op_password", "")

        # Action: Clear Code
        if data == "op_clear":
            password = ""
            context.user_data["op_password"] = ""
            return await query.message.edit_text(
                "🔐 <b>Enter Password:</b>\n\n<i>Cleared! Waiting for input...</i>",
                parse_mode=ParseMode.HTML,
                reply_markup=get_numpad_keyboard()
            )

        # Action: Authenticate Code
        elif data == "op_done":
            if not OWNER_PANEL_PASSWORD:
                return await query.answer(
                    "Owner panel password is not configured.", show_alert=True
                )
            if password != OWNER_PANEL_PASSWORD:
                context.user_data["op_password"] = ""
                return await query.answer("❌ Wrong Password! Try again.", show_alert=True)

            # Verification Successful!
            owner_auth.add(uid)
            context.user_data["op_password"] = ""
            return await open_panel(query)

        # Action: Standard Digits 0-9
        else:
            digit = data.split("_")[1]
            password += digit
            context.user_data["op_password"] = password

        masked = "•" * len(password) if password else "<i>Waiting for input...</i>"

        return await query.message.edit_text(
            f"🔐 <b>Enter Password</b>\n\n<code>{masked}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=get_numpad_keyboard()
        )


# ==========================================
# 😎 OPEN MAIN AUTHENTICATED OWNER PANEL
# ==========================================
async def open_panel(query):
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎴 Characters", callback_data="op_char"),
            InlineKeyboardButton("👥 Users", callback_data="op_users")
        ],
        [
            InlineKeyboardButton("💰 Economy", callback_data="op_economy"),
            InlineKeyboardButton("📢 Broadcast", callback_data="op_broadcast")
        ],
        [
            InlineKeyboardButton("🎰 System", callback_data="op_system")
        ]
    ])

    # ഫംഗ്ഷനുകൾ ഫയലിൽ ഇല്ലെങ്കിൽ എറർ വരാതിരിക്കാനുള്ള മുൻകരുതൽ
    total_users = get_total_users() if 'get_total_users' in globals() else 0
    total_chars = get_character_count() if 'get_character_count' in globals() else 0
    total_groups = get_total_groups() if 'get_total_groups' in globals() else 0
    total_coins = get_total_coins() if 'get_total_coins' in globals() else 0

    text = (
        "👑 <b>𝖮𝖶𝖭𝖤𝖱 𝖯𝖠𝖭𝖤𝖫</b>\n\n"
        "<blockquote>"
        f"👥 𝖴𝗌𝖾𝗋𝗌: {total_users:,}\n"
        f"💬 𝖦𝗋𝗈𝗎𝗉𝗌: {total_groups:,}\n"
        f"🎴 𝖢𝗁𝖺𝗋𝗌: {total_chars:,}\n"
        f"💰 𝖳𝗈𝗍𝖺𝗅 𝖼𝗈𝗂𝗇𝗌: {total_coins:,}"
        "</blockquote>\n\n"
        "<i>𝖲𝖾𝗅𝖾𝖼𝗍 𝖺𝗇 𝖺𝖼𝗍𝗂𝗈𝗇:</i>"
    )

    await query.message.edit_text(
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


async def restart_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return  # Non-owners silent block

    await update.message.reply_text("🔄 <b>Restarting bot...</b>", parse_mode="HTML")

    # Respawn: replace current process with a new one running main.py
    os.execv(sys.executable, [sys.executable, "main.py"])

