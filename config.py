import random
import os
import logging
from urllib.parse import urlsplit, urlunsplit

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ==================== 🔑 BOT TOKEN ====================


# ⚠️ Method 2: Environment variable (safer)
BOT_TOKEN = os.getenv("BOT_TOKEN", "PUT_YOUR_BOT_TOKEN_HERE")

GUESS_TIMEOUT = 30         # seconds
REWARD_COINS = 20           # coins per correct guess
REACTIONS = ["🔥", "🎉", "👍", "💯", "⚡", "🥳", "👀", "✨"]

# ==================== 👑 OWNER ====================
# Telegram ID
_raw_owner_id = os.getenv("OWNER_ID", "0")
try:
    OWNER_ID = int(_raw_owner_id)
except ValueError as exc:
    raise RuntimeError("OWNER_ID must be a numeric Telegram user ID") from exc
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY")

# Owner panel password must be supplied through the environment.
OWNER_PANEL_PASSWORD = os.getenv("OWNER_PANEL_PASSWORD", "")


# ==================== 🤖 BOT IDENTITY ====================
BOT_USERNAME = os.getenv("BOT_USERNAME", "Summon_collection_bot").lstrip("@").strip()
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "og_gohan").lstrip("@").strip()
SUPPORT_CHAT = os.getenv("SUPPORT_CHAT", "https://t.me/summon_official").strip()
UPDATE_CHANNEL = os.getenv("UPDATE_CHANNEL", "https://t.me/Beastxgohan").strip()
DB_CHANNEL_ID = int(os.getenv("DB_CHANNEL_ID", "-1003858966339"))

# ==================== 💾 DATABASE ====================
# PostgreSQL is the only production runtime database. DB_NAME remains as a
# compatibility argument for existing helpers and is never used as a file path.
DB_NAME = os.getenv("DATABASE_NAME", "summon_bot")
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
MONGO_URI = os.getenv("MONGO_URI", "").strip()
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "summon_bot").strip() or "summon_bot"

# ==================== 🩺 OPERATIONS / WEB APP ====================
def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


LOGGER_ID = _int_env("LOGGER_ID", 0)
LOG_TELEGRAM_LEVEL = os.getenv("LOG_TELEGRAM_LEVEL", "WARNING").upper()
LOG_BATCH_SECONDS = max(0.2, float(os.getenv("LOG_BATCH_SECONDS", "1.5")))
PORT = _int_env("PORT", 8080)
KEEPALIVE_URL = os.getenv("KEEPALIVE_URL", "https://summon-bot-wngc.onrender.com").strip()


def _default_webhook_url() -> str:
    parsed = urlsplit(KEEPALIVE_URL)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, "/telegram/webhook", "", ""))


WEBHOOK_URL = os.getenv("WEBHOOK_URL", _default_webhook_url()).strip()
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()
KEEPALIVE_INTERVAL_SECONDS = max(30, _int_env("KEEPALIVE_INTERVAL_SECONDS", 300))
KEEPALIVE_TIMEOUT_SECONDS = max(2, _int_env("KEEPALIVE_TIMEOUT_SECONDS", 10))
WATCHDOG_INTERVAL_SECONDS = max(15, _int_env("WATCHDOG_INTERVAL_SECONDS", 60))
WATCHDOG_TIMEOUT_SECONDS = max(30, _int_env("WATCHDOG_TIMEOUT_SECONDS", 180))
WEBAPP_ENABLED = os.getenv("WEBAPP_ENABLED", "true").strip().lower() not in {"0", "false", "no"}

#  character spawn time
DEFAULT_SPAWN_LIMIT = 100


# ==================== 📊 ECONOMY ====================
STARTING_BALANCE = 500

# Daily claim
DAILY_REWARD = 5000

# Spin 
SPIN_MIN_REWARD = 100
SPIN_MAX_REWARD = 1000
SPIN_BONUS_MIN = 500
SPIN_BONUS_MAX = 2000
SPIN_LUCKY_CHANCE = 10  # 1 in 10 chance for bonus
SPIN_COOLDOWN_HOURS = 24

# /hclaim cooldown
HCLAIM_COOLDOWN_HOURS = 24


# ==================== 🛒 SHOP PRICES ====================
# Rarity price
PRICE = {
    "⚪ Common": 15000,
    "🔵 Rare": 25000,
    "💮 Special Edition": 50000,
    "⭐ Legendary": 90000,
    "🛸 Mythic Edition": 150000,

    "💝 Valentine Edition": 250000,
    "🏖️ Summer Edition": 250000,
    "🌧️ Rainy Edition": 250000,

    "🎃 Halloween Edition": 350000,
    "🎄 Christmas Edition": 350000,

    "❄️ Winter Edition": 400000,
    "🎇 New Year Edition": 450000,

    "🎍 Festival Edition": 550000,
    "🎉 Event Edition": 650000,

    "🌌 Celestial Edition": 1000000,
    "💎 Luxury Edition": 1500000,
    "🔮 Limited Edition": 2000000
}

# 🔄 refresh allowed only these
REFRESH_ALLOWED = {
    "⚪ Common",
    "🔵 Rare",
    "💮 Special Edition",
    "⭐ Legendary",
    "🛸 Mythic Edition"
}

HIGH_TIER = {
    "💝 Valentine Edition",
    "🏖️ Summer Edition",
    "🌧️ Rainy Edition",
    "🎃 Halloween Edition",
    "🎄 Christmas Edition",
    "❄️ Winter Edition",
    "🎇 New Year Edition",
    "🎍 Festival Edition",
    "🎉 Event Edition",
    "🌌 Celestial Edition",
    "💎 Luxury Edition",
    "🔮 Limited Edition"
}

REFRESH_PRICE = 10000


# ==================== 🛡️ ANTI-SPAM ====================
SPAM_LIMIT = 20 # ഒരു മിനിറ്റിൽ ഇത്ര messages-ൽ കൂടുതൽ വന്നാൽ ban


# ==================== 🖼️ IMAGES ====================
# Channel post IDs 
TOP_IMAGE = "https://o.uguu.se/ooABzMzy.jpg"
SHOP_IMAGE = "https://o.uguu.se/ooABzMzy.jpg"
HELP_IMAGE = "https://o.uguu.se/ooABzMzy.jpg"


# ==================== 📢 BROADCAST ====================
# Owner broadcast channel/group
SUPPORT_GROUP_ID = -1003908312302
GROUP_LINK = "https://t.me/summon_official"

GROUP_IDS = []  # Auto-filled below with your group chat ID


# ==================== 🎬 START MEDIA ====================
START_MEDIA = [
    "https://files.catbox.moe/g0xwn9.mp4",
    "https://files.catbox.moe/rzunme.mp4",
    "https://files.catbox.moe/g9r59s.mp4",
    "https://files.catbox.moe/8bau4o.mp4",
    "https://files.catbox.moe/r1wa5s.mp4",
]

RARITY_EMOJI = {
    1: "⚪️", 2: "🔵", 3: "💮", 4: "⭐", 5: "🛸",
    6: "💝", 7: "🏖️", 8: "🌧️", 9: "🎃", 10: "🎄",
    11: "❄️", 12: "🎇", 13: "🎍", 14: "🎥", 15: "🎉",
    16: "🌌", 17: "💎", 18: "🔮"
}

# ==================== 🎨 FONT ====================
# Bot messages
# 'mono' | 'fraktur' | 'script' | 'double'
DEFAULT_FONT = "mono"


# ==================== ⚙️ FEATURE TOGGLES ====================
#
ENABLE_STREAK = True
ENABLE_ACHIEVEMENTS = True
ENABLE_MARKET = True
ENABLE_AUTO_BAN = True
ENABLE_FONT = True


# ==================== 📊 LOGGING ====================
DEBUG_MODE = False

if DEBUG_MODE:
    logging.getLogger().setLevel(logging.DEBUG)
