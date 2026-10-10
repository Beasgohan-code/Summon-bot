import asyncio
import logging
import signal
import sys
from datetime import datetime
from urllib.parse import urlsplit

from storage import ping as ping_database


from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    InlineQueryHandler,
    MessageHandler,
    filters,
)	
# ==================== CONFIG & MODULES ====================
from config import (
    BOT_TOKEN, OWNER_ID, BOT_USERNAME, MONGO_URI, MONGO_DB_NAME,
    PRICE, HIGH_TIER, SPIN_COOLDOWN_HOURS, HCLAIM_COOLDOWN_HOURS,
    SPAM_LIMIT, DAILY_REWARD,
    ENABLE_STREAK, ENABLE_ACHIEVEMENTS, ENABLE_MARKET, ENABLE_FONT,
    LOGGER_ID, PORT, KEEPALIVE_URL, WEBAPP_ENABLED,
    WEBHOOK_URL, WEBHOOK_SECRET,
)
from health import HealthServer, HealthState, KeepAlive, Watchdog
from logging_utils import install_telegram_log_handler, send_startup_log
from database import init_db, ACHIEVEMENTS, STREAK_BONUS_TIERS, MARKET_POOL_SIZE, MARKET_REFRESH_PRICE

from plugins.profile import profile_cmd
from plugins.profile import register as profile_register
from plugins.market import register as market_register


# User commands
from commands_user import (
    # helpers
    check_ban, send_character_media,
    get_uptime, loading_animation, ping_command,
    # user commands
    start_command, help_command, help_callback,
    view_balance, daily, spin, cshop, cshop_callback, 
    set_claim_chance, view_claim_list,
    collection_command, check_character, back_check_callback, owner_callback, search_character,
    favorite, give_character, gift_character,
    pay_money, give_money, rm_money,
    shop, open_shop, rarity_pick, refresh, buy,
    top_command, top_callback_handler, collection_nav,
    streak_command, streak_callback, search_page_callback,
    achievements_command, stats_command,
    sell_command,
    hmode_command, hmode_set_callback, hmode_show_rarities_callback,
    profile_glow_toggle, profile_hmode_callback,
    font_command, font_callback,
)

# Admin commands (sudo+)
from commands_admin import (
    ban, unban, warn, remove, delete,
    trigger_spawn,
    checkspawn, changetime,
    change_chance, chance_list, sudo_callback_handler,
    sudolist_command, editsudo_command, addsudo_command,
    upload_character, add_character, update_character,
    removeall, removeall_callback,
    transfer, gen_code, redeem_code,
    broadcast, save_group,
)

# Owner panel
from commands_owner import owner_panel, ownerpanel_callback, restart_bot

from auto_spawn import hint_callback, auto_spawn_watcher

# Inline + catch-all
from inline_search import inline_search
from catch_all import track_messages_and_save_group

logger = logging.getLogger(__name__)
_telegram_log_handler = None


# ==================== POST INIT ====================

async def post_init(application: Application):
    """Set bot commands + startup banner + notify owner."""
    # Bot menu
    commands = [
        BotCommand("start", "👋 Start the bot"),
        BotCommand("ping", "🏓 Check bot latency"),
        BotCommand("help", "📖 Show help menu"),
        BotCommand("balance", "💰 Check your coins"),
        BotCommand("daily", "📅 Daily reward"),
        BotCommand("spin", "🎰 Daily spin"),
        BotCommand("hclaim", "💖 Claim daily character"),
        BotCommand("collection", "📚 View your collection"),
        BotCommand("harem", "👥 View your harem"),
        BotCommand("shop", "🛒 Buy characters"),
        BotCommand("market", "🛒 Open market"),
        BotCommand("sell", "💰 Sell a character"),
        BotCommand("top", "🏆 Leaderboard"),
        BotCommand("profile", "👤 Your profile"),
    ]

    if ENABLE_STREAK:
        commands.extend([
            BotCommand("streak", "🔥 Daily streak"),
        ])

    if ENABLE_ACHIEVEMENTS:
        commands.extend([
            BotCommand("achievements", "🏅 Your badges"),
        ])

    commands.extend([
        BotCommand("stats", "📊 Server stats"),
        BotCommand("hmode", "🎛 Collection filter"),
    ])

    if ENABLE_FONT:
        commands.append(BotCommand("font", "🎨 Change font"))

    commands.extend([
        BotCommand("fav", "⭐ Set favorite"),
        BotCommand("gift", "🎁 Give a character"),
        BotCommand("check", "🔎 Check character info"),
        BotCommand("search", "🔍 Search characters"),
        BotCommand("summon", "⚡ Claim spawned character"),
        BotCommand("redeem", "🎁 Redeem a code"),
        BotCommand("owner", "👑 Owner panel"),
    ])

    await application.bot.set_my_commands(commands)

    # Startup banner
    bot = await application.bot.get_me()
    print(f"""
╔══════════════════════════════════════════╗
║  🤖  SUMMON CHARACTER BOT                ║
╠══════════════════════════════════════════╣
║  🆔  Bot:    @{bot.username}              ║
║  👑  Owner:  {OWNER_ID}                  ║
║  💾  DB:     Initialized                  ║
║  🎨  Font:   Loaded                      ║
║  🟢  Status: ONLINE                      ║
╚══════════════════════════════════════════╝
    """)

    # Send an immediate operational card to LOGGER_ID. This is separate from
    # the background warning/error queue, so every clean boot is visible.
    await send_startup_log(
        application.bot,
        bot_username=bot.username or BOT_USERNAME,
        database="MongoDB",
        port=PORT,
        keepalive_url=KEEPALIVE_URL,
        webapp_enabled=WEBAPP_ENABLED,
        chat_id=LOGGER_ID,
    )

    # Notify owner
    try:
        await application.bot.send_message(
            chat_id=OWNER_ID,
            text=(
                f"🤖 <b>Bot Started</b>\n\n"
                f"🆔 @{bot.username}\n"
                f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"Could not notify owner: {e}")


# ==================== ERROR HANDLER ====================

async def error_handler(update: object, context):
    """Log errors + try to inform user."""
    logger.error(f"Update {update} caused error: {context.error}", exc_info=context.error)

    try:
        if update and isinstance(update, Update) and update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=(
                    "❌ <b>𝖠𝗇 𝖾𝗋𝗋𝗈𝗋 𝗈𝖼𝖼𝗎𝗋𝗋𝖾𝖽.</b>\n"
                    "𝖳𝗁𝖾 𝖽𝖾𝗏𝖾𝗅𝗈𝗉𝖾𝗋 𝗁𝖺𝗌 𝖻𝖾𝖾𝗇 𝗇𝗈𝗍𝗂𝖿𝗂𝖾𝖽."
                ),
                parse_mode="HTML",
            )
    except Exception:
        pass


# ==================== REGISTER HANDLERS ====================

def register_handlers(application: Application):
    """Register all command/callback/inline handlers."""

    # ==================== 👤 USER COMMANDS ====================

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("ping", ping_command))
    application.add_handler(CommandHandler(["help", "menu", "commands"], help_command))
    application.add_handler(CommandHandler(["balance", "bal"], view_balance))
    application.add_handler(CommandHandler("daily", daily))
    application.add_handler(CommandHandler("spin", spin))
    application.add_handler(CommandHandler("claimlist", view_claim_list))
    application.add_handler(CommandHandler("setclaim", set_claim_chance))
    application.add_handler(CommandHandler(["collection", "harem"], collection_command))
    application.add_handler(CommandHandler(["check", "info"], check_character))
    application.add_handler(CommandHandler(["search", "find"], search_character))
    application.add_handler(CommandHandler("fav", favorite))
    application.add_handler(CommandHandler("give", give_character))
    application.add_handler(CommandHandler("pay", pay_money))
    application.add_handler(CommandHandler("givemoney", give_money))
    application.add_handler(CommandHandler("rmmoney", rm_money))
    application.add_handler(CommandHandler("shop", shop))
    application.add_handler(CommandHandler(["top", "rank"], top_command))
    application.add_handler(CommandHandler("gift", gift_character))

    if ENABLE_STREAK:
        application.add_handler(CommandHandler("streak", streak_command))

    if ENABLE_ACHIEVEMENTS:
        application.add_handler(CommandHandler(["achievements", "ach", "badges"], achievements_command))

    application.add_handler(CommandHandler(["stats", "server"], stats_command))
    application.add_handler(CommandHandler("hmode", hmode_command))
    application.add_handler(CommandHandler(["sell", "sellchar"], sell_command))

    if ENABLE_FONT:
        application.add_handler(CommandHandler(["font", "style"], font_command))

    # ==================== 👑 ADMIN COMMANDS ====================

    application.add_handler(CommandHandler("ban", ban))
    application.add_handler(CommandHandler("unban", unban))
    application.add_handler(CommandHandler("warn", warn))
    application.add_handler(CommandHandler("remove", remove))
    application.add_handler(CommandHandler("delete", delete))
    application.add_handler(CommandHandler("spawn", trigger_spawn))
    application.add_handler(CommandHandler("checkspawn", checkspawn))
    application.add_handler(CommandHandler("changetime", changetime))
    application.add_handler(CommandHandler("chance", change_chance))
    application.add_handler(CommandHandler(["chancelist", "clist"], chance_list))
    application.add_handler(CommandHandler("sudolist", sudolist_command))
    application.add_handler(CommandHandler("addsudo", addsudo_command))
    application.add_handler(CommandHandler(["editsudo", "rmsudo"], editsudo_command))
    # /upload is the original media-reply workflow; /addchar and /add are
    # the direct approved-URL workflow.
    application.add_handler(CommandHandler("upload", upload_character))
    application.add_handler(CommandHandler(["addchar", "add"], add_character))
    application.add_handler(CommandHandler(["updatechar", "update"], update_character))
    application.add_handler(CommandHandler("removeall", removeall))
    application.add_handler(CommandHandler("transfer", transfer))
    application.add_handler(CommandHandler(["gen", "gencode"], gen_code))
    application.add_handler(CommandHandler("redeem", redeem_code))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CommandHandler(["savegroup", "reggroup"], save_group))
    application.add_handler(CommandHandler("cshop000000" , cshop))

    # ==================== 👑 OWNER PANEL ====================

    application.add_handler(CommandHandler(["owner", "panel"], owner_panel))
    application.add_handler(CommandHandler("restart", restart_bot))

    # ==================== 📞 CALLBACK QUERIES ====================
    application.add_handler(CallbackQueryHandler(search_page_callback, pattern=r"^srch_"))
    # Help
    application.add_handler(CallbackQueryHandler(help_callback, pattern=r"^(open_help|help_)"))

    # Shop
    application.add_handler(CallbackQueryHandler(collection_nav, pattern="^col_\\d+_-?\\d+$|^ignore$"))
    application.add_handler(CallbackQueryHandler(sudo_callback_handler, pattern="^(manage_sudo_|rem_sudo_|cancel_sudo)"))
    application.add_handler(CallbackQueryHandler(open_shop, pattern="^open_shop$"))
    application.add_handler(CallbackQueryHandler(rarity_pick, pattern="^rarity_"))
    application.add_handler(CallbackQueryHandler(refresh, pattern="^refresh_"))
    application.add_handler(CallbackQueryHandler(buy, pattern="^buy$|^buy_"))

    # Top
    application.add_handler(CallbackQueryHandler(top_callback_handler, pattern=r"^top_"))
    # Market


    # Profile + hmode
    application.add_handler(CallbackQueryHandler(profile_glow_toggle, pattern=r"^profile_toggle_glow$"))
    application.add_handler(CallbackQueryHandler(hmode_command, pattern=r"^hmode_menu$"))
    application.add_handler(CallbackQueryHandler(hmode_show_rarities_callback, pattern=r"^hmode_show_rarities$"))
    application.add_handler(CallbackQueryHandler(hmode_set_callback, pattern=r"^hmode_set_"))
    application.add_handler(CallbackQueryHandler(profile_cmd, pattern=r"^profile_back$"))
    # Streak
    application.add_handler(CallbackQueryHandler(streak_callback, pattern=r"^streak_"))

    # Font
    application.add_handler(CallbackQueryHandler(font_callback, pattern=r"^font_set_"))
    #hint
    application.add_handler(CallbackQueryHandler(hint_callback, pattern=r"^hint_"))
    # Admin confirm
    application.add_handler(CallbackQueryHandler(removeall_callback, pattern=r"^rmall_"))

    #check
    application.add_handler(CallbackQueryHandler(owner_callback, pattern="^owners_"))
    application.add_handler(CallbackQueryHandler(back_check_callback, pattern="^backcheck_"))

    # Owner panel
    application.add_handler(CallbackQueryHandler(ownerpanel_callback, pattern=r"^op_"))
    application.add_handler(CallbackQueryHandler(cshop_callback, pattern=r"^market_"))
    # ==================== 🔍 INLINE QUERIES ====================

    application.add_handler(InlineQueryHandler(inline_search))

    # ==================== 📥 CATCH-ALL (must be last) ====================

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            track_messages_and_save_group,
        )
    )


    import commands_hstats
    commands_hstats.register(application)
    
    import commands_auction
    commands_auction.register(application)
    # ==================== ❌ ERROR HANDLER (must be last) ====================
    profile_register(application)
    market_register(application)

    # ==================== 🎮 NGUESS GAME ====================
    from plugins import nguess
    nguess.register(application)

    application.add_error_handler(error_handler)

    logger.info("✅ All handlers registered")


# ==================== OPERATIONS ====================
def database_probe():
    """Run a live MongoDB ping for readiness/watchdog checks."""
    ping_database()
    return {"ok": True, "backend": "mongodb", "database": MONGO_DB_NAME}


# ==================== MAIN ====================
def validate_config():
    if not BOT_TOKEN or BOT_TOKEN == "PUT_YOUR_BOT_TOKEN_HERE":
        raise RuntimeError("BOT_TOKEN is not configured. Set it in the environment before starting the bot.")
    if OWNER_ID <= 0:
        raise RuntimeError("OWNER_ID must be a positive Telegram user ID.")
    if not MONGO_URI.startswith(("mongodb://", "mongodb+srv://")):
        raise RuntimeError(
            "MONGO_URI must be configured with a mongodb:// or mongodb+srv:// URL. "
            "No PostgreSQL, SQLite, or local-file fallback is available."
        )
    if not MONGO_DB_NAME.strip():
        raise RuntimeError("MONGO_DB_NAME must be configured and non-empty.")
    webhook = urlsplit(WEBHOOK_URL)
    if webhook.scheme != "https" or not webhook.netloc or not webhook.path:
        raise RuntimeError(
            "WEBHOOK_URL must be a public HTTPS URL, for example "
            "https://summon-bot-wngc.onrender.com/telegram/webhook."
        )
    if not 1 <= len(WEBHOOK_SECRET) <= 256:
        raise RuntimeError("WEBHOOK_SECRET must be a 1-256 character Telegram webhook secret.")


async def async_main():
    global _telegram_log_handler
    validate_config()
    telegram_log_handler = install_telegram_log_handler(BOT_TOKEN, LOGGER_ID)
    _telegram_log_handler = telegram_log_handler

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    application_holder: dict[str, Application] = {}

    def enqueue_webhook(payload: dict, headers: dict[str, str]) -> bool:
        """Validate and enqueue a webhook update from the HTTP worker thread."""
        supplied_secret = next(
            (value for key, value in headers.items() if key.lower() == "x-telegram-bot-api-secret-token"),
            "",
        )
        if supplied_secret != WEBHOOK_SECRET or not isinstance(payload, dict):
            return False
        application = application_holder.get("application")
        if application is None:
            return False
        try:
            update = Update.de_json(payload, application.bot)
            if update is None:
                return False
        except Exception:
            logger.warning("Rejected malformed Telegram webhook update", exc_info=True)
            return False

        def put_update() -> None:
            try:
                application.update_queue.put_nowait(update)
            except Exception:
                logger.exception("Could not enqueue Telegram webhook update")

        loop.call_soon_threadsafe(put_update)
        return True

    webhook_path = urlsplit(WEBHOOK_URL).path
    health_state = HealthState()
    health_server = HealthServer(
        health_state,
        PORT,
        webhook_path=webhook_path,
        webhook_handler=enqueue_webhook,
    )
    watchdog = Watchdog(health_state, database_probe)
    keepalive = KeepAlive(health_state)

    # Start HTTP health/web-app/webhook routes before database boot so Render
    # sees a liveness response while the bot is still initializing.
    health_server.start()
    watchdog.start()
    keepalive.start()
    application: Application | None = None
    application_started = False
    try:
        print("🔧 Initializing database...")
        init_db()
        health_state.mark_ready({"ok": True, "backend": "mongodb", "database": MONGO_DB_NAME, "runtime": "webhook"})
        print("✅ Database ready")
        print("🔧 Building application...")
        application = Application.builder().token(BOT_TOKEN).build()
        application_holder["application"] = application

        print("🔧 Registering handlers...")
        register_handlers(application)
        await application.initialize()
        await post_init(application)
        await application.start()
        application_started = True

        webhook_kwargs = {
            "url": WEBHOOK_URL,
            "secret_token": WEBHOOK_SECRET,
            "allowed_updates": ["message", "edited_message", "callback_query", "inline_query"],
            "drop_pending_updates": True,
        }
        await application.bot.set_webhook(**webhook_kwargs)
        logger.info("Telegram webhook active at %s", WEBHOOK_URL)
        print("🚀 Webhook runtime active with health/watchdog services")

        for signal_name in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(signal_name, stop_event.set)
            except (NotImplementedError, RuntimeError):
                pass
        await stop_event.wait()
    finally:
        application_holder.clear()
        if application is not None:
            try:
                await application.bot.delete_webhook(drop_pending_updates=False)
            except Exception:
                logger.warning("Could not delete Telegram webhook during shutdown", exc_info=True)
            try:
                if application_started:
                    await application.stop()
            finally:
                await application.shutdown()
        keepalive.stop()
        watchdog.stop()
        health_server.stop()


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if _telegram_log_handler:
            _telegram_log_handler.close()
