import random
import os
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ==================== 🔑 BOT TOKEN ====================
# ⚠️ Method 1: Direct (easiest for Termux)
BOT_TOKEN = "8869362388:AAGRAu6BwTi07SWjbWLisBHohB4rwe0PCSk"

# ⚠️ Method 2: Environment variable (safer)
# BOT_TOKEN = os.getenv("BOT_TOKEN", "PUT_YOUR_BOT_TOKEN_HERE")

GUESS_TIMEOUT = 30         # 5 minutes
REWARD_COINS = 20           # coins per correct guess
REACTIONS = ["🔥", "🎉", "👍", "💯", "⚡", "🥳", "👀", "✨"]

# ==================== 👑 OWNER ====================
# ബോട്ടിന്റെ ഉടമയുടെ Telegram ID
OWNER_ID = 6265999542
IMGBB_API_KEY="73adf9298fcf66fd6897d2be9e539670"

# Owner panel പാസ്‌വേഡ് (നമ്പർപാഡ് ഉപയോഗിക്കുമ്പോൾ)
OWNER_PANEL_PASSWORD = "7736"


# ==================== 🤖 BOT IDENTITY ====================
BOT_USERNAME = "Summon_collection_bot"          # BotFather username
OWNER_USERNAME = "og_gohan"                      # നിങ്ങളുടെ username (no @)
SUPPORT_CHAT = "https://t.me/summon_official"
UPDATE_CHANNEL = "https://t.me/Beastxgohan"
DB_CHANNEL_ID = -1003858966339

# ==================== 💾 DATABASE ====================
DB_NAME = "summon.db"

# Group-ൽ എത്ര മെസ്സേജിന് ശേഷം character spawn ചെയ്യണം
DEFAULT_SPAWN_LIMIT = 100


# ==================== 📊 ECONOMY ====================
# പുതിയ യൂസറിന് കിട്ടുന്ന സ്റ്റാർട്ടിംഗ് ബാലൻസ്
STARTING_BALANCE = 500

# Daily claim ൽ കിട്ടുന്ന തുക
DAILY_REWARD = 5000

# Spin ചെയ്യുമ്പോൾ കിട്ടുന്ന റേഞ്ച്
SPIN_MIN_REWARD = 100
SPIN_MAX_REWARD = 1000
SPIN_BONUS_MIN = 500
SPIN_BONUS_MAX = 2000
SPIN_LUCKY_CHANCE = 10  # 1 in 10 chance for bonus
SPIN_COOLDOWN_HOURS = 24

# /hclaim cooldown
HCLAIM_COOLDOWN_HOURS = 24


# ==================== 🛒 SHOP PRICES ====================
# Rarity അനുസരിച്ച് price
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
SPAM_LIMIT = 25  # ഒരു മിനിറ്റിൽ ഇത്ര messages-ൽ കൂടുതൽ വന്നാൽ ban


# ==================== 🖼️ IMAGES ====================
# Channel post IDs (Telegram-ൽ message ആയി forward ചെയ്തത്)
TOP_IMAGE = "https://o.uguu.se/ooABzMzy.jpg"
SHOP_IMAGE = "https://o.uguu.se/ooABzMzy.jpg"
HELP_IMAGE = "https://o.uguu.se/ooABzMzy.jpg"


# ==================== 📢 BROADCAST ====================
# Owner broadcast ചെയ്യാൻ ഉപയോഗിക്കുന്റ channel/group
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
# Bot messages-ന് ഏത് font ഉപയോഗിക്കണം
# 'mono' | 'fraktur' | 'script' | 'double'
DEFAULT_FONT = "mono"


# ==================== ⚙️ FEATURE TOGGLES ====================
# ഏത് features enable ആണ്
ENABLE_STREAK = True
ENABLE_ACHIEVEMENTS = True
ENABLE_MARKET = True
ENABLE_AUTO_BAN = True
ENABLE_FONT = True


# ==================== 📊 LOGGING ====================
DEBUG_MODE = False

if DEBUG_MODE:
    logging.getLogger().setLevel(logging.DEBUG)

