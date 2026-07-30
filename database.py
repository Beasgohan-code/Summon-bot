# Step 1: Clean the garbage at lines 
import logging
import sqlite3
from config import DB_NAME, DEFAULT_SPAWN_LIMIT

logger = logging.getLogger(__name__)


# ==========================
# RARITY EMOJIS
# ==========================

RARITY_EMOJI = {
    1: "⚪️",   2: "🔵",   3: "💮",   4: "⭐",
    5: "🛸",   6: "💝",   7: "🏖️",   8: "🌧️",
    9: "🎃",  10: "🎄",  11: "❄️",  12: "🎇",
    13: "🎍", 14: "🎥",  15: "🎉",  16: "🌌",
    17: "💎", 18: "🔮",
}


# ==================== DATABASE SETUP ====================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # 1️⃣ users
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance INTEGER DEFAULT 0,
            banned INTEGER DEFAULT 0,
            favorite TEXT,
            last_daily TEXT,
            last_hclaim TEXT,
            last_spin TEXT,
            font_pref TEXT DEFAULT 'mono',
            first_name TEXT
        )
    """)

    # Safe ALTER for legacy DBs
    for alter in [
        "ALTER TABLE users ADD COLUMN last_daily TEXT",
        "ALTER TABLE users ADD COLUMN last_hclaim TEXT",
        "ALTER TABLE users ADD COLUMN last_spin TEXT",
        "ALTER TABLE users ADD COLUMN font_pref TEXT DEFAULT 'mono'",
        "ALTER TABLE users ADD COLUMN first_name TEXT",
    ]:
        try:
            cursor.execute(alter)
        except sqlite3.OperationalError:
            pass

    # WARNINGS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS warnings (
            user_id INTEGER PRIMARY KEY,
            warn_count INTEGER DEFAULT 0,
            warned_by INTEGER,
            reason TEXT
        )
    """)



    cursor.execute("""
        CREATE TABLE IF NOT EXISTS group_settings (
            chat_id INTEGER PRIMARY KEY,
            message_count INTEGER DEFAULT 0,
            spawn_limit INTEGER DEFAULT 100
        )
    """)

    # 2️⃣ user_collection
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_collection (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            character_id TEXT,
            count INTEGER DEFAULT 1,
            obtained_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, character_id)
        )
    """)
    try:
        cursor.execute("ALTER TABLE user_collection ADD COLUMN count INTEGER DEFAULT 1")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE user_collection ADD COLUMN obtained_at TEXT DEFAULT CURRENT_TIMESTAMP")
    except sqlite3.OperationalError:
        pass

    # 3️⃣ characters
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS characters (
            id TEXT PRIMARY KEY,
            name TEXT,
            anime TEXT,
            rarity TEXT,
            msg_id TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    try:
        cursor.execute("ALTER TABLE characters ADD COLUMN created_at TEXT DEFAULT CURRENT_TIMESTAMP")
    except sqlite3.OperationalError:
        pass

    for migration in [
         "ALTER TABLE characters ADD COLUMN img_url TEXT",
         "ALTER TABLE characters ADD COLUMN img_url2 TEXT",
     ]:
         try:
             cursor.execute(migration)
         except sqlite3.OperationalError:
             pass

    # 4️⃣ redeem_codes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS redeem_codes (
            code TEXT PRIMARY KEY,
            character_id TEXT,
            uses INTEGER DEFAULT 1,
            created_by INTEGER,
            reward INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    try:
        cursor.execute("ALTER TABLE redeem_codes ADD COLUMN reward INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    # 5️⃣ banned_users
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS banned_users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            reason TEXT,
            banned_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    try:
        cursor.execute("ALTER TABLE banned_users ADD COLUMN reason TEXT")
    except sqlite3.OperationalError:
        pass

    # 6️⃣ warnings
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS warnings (
            user_id INTEGER,
            warn_count INTEGER DEFAULT 0,
            warned_by INTEGER,
            reason TEXT,
            warned_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    try:
        cursor.execute("ALTER TABLE warnings ADD COLUMN warn_count INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE warnings ADD COLUMN warned_by INTEGER")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE warnings ADD COLUMN reason TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE warnings ADD COLUMN warned_at TEXT DEFAULT CURRENT_TIMESTAMP")
    except sqlite3.OperationalError:
        pass

    # 7️⃣ group_settings
    cursor.execute("""
            CREATE TABLE IF NOT EXISTS group_settings (
            chat_id INTEGER PRIMARY KEY,
            spawn_limit INTEGER DEFAULT 100
        )
    """)
    try:
        cursor.execute("ALTER TABLE group_settings ADD COLUMN spawn_limit INTEGER DEFAULT 100")
    except sqlite3.OperationalError:
        pass

    # 8️⃣ claim_list (hclaim weights)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS claim_list (
            rarity_id INTEGER PRIMARY KEY,
            chance REAL,
            rarity_name TEXT
        )
    """)
    try:
        cursor.execute("ALTER TABLE claim_list ADD COLUMN rarity_name TEXT")
    except sqlite3.OperationalError:
        pass

    cursor.execute("SELECT COUNT(*) FROM claim_list")
    if cursor.fetchone()[0] == 0:
        exact_chances = [
            (1, 400.0, "Common"),
            (2, 0.0, "Rare"),
            (3, 1200.0, "Special"),
            (4, 600.0, "Legendary"),
            (5, 300.0, "Mythic"),
            (6, 50.0, "Valentine"),
            (7, 50.0, "Summer"),
            (8, 50.0, "Rainy"),
            (9, 50.0, "Halloween"),
            (10, 0.0, "Christmas"),
            (11, 2.0, "Winter"),
            (12, 50.0, "New Year"),
            (13, 40.0, "Festival"),
            (14, 0.0, "AMV"),
            (15, 100.0, "Event"),
            (16, 40.0, "Celestial"),
            (17, 0.0, "Luxury"),
            (18, 20.0, "Limited"),
        ]
        cursor.executemany(
            "INSERT INTO claim_list (rarity_id, chance, rarity_name) VALUES (?, ?, ?)",
            exact_chances,
        )

    # 9️⃣ rarity_chances (main spawn pool)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rarity_chances (
            rarity_id INTEGER PRIMARY KEY,
            rarity_name TEXT,
            chance_value INTEGER
        )
    """)
    cursor.execute("SELECT COUNT(*) FROM rarity_chances")
    if cursor.fetchone()[0] == 0:
        default_chances = [
            (1, "Common", 4500),   (2, "Rare", 2500),
            (3, "Special", 1200),  (4, "Legendary", 600),
            (5, "Mythic", 300),    (6, "Valentine", 50),
            (7, "Summer", 50),     (8, "Rainy", 50),
            (9, "Halloween", 50),  (10, "Christmas", 50),
            (11, "Winter", 50),    (12, "New Year", 50),
            (13, "Festival", 40),  (14, "AMV", 10),
            (15, "Event", 100),    (16, "Celestial", 40),
            (17, "Luxury", 30),    (18, "Limited", 20),
        ]
        cursor.executemany(
            "INSERT OR IGNORE INTO rarity_chances VALUES (?, ?, ?)",
            default_chances,
        )

    # 🔟 groups
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            chat_id INTEGER PRIMARY KEY
        )
    """)

    # ==================== 🆕 NEW FEATURES ====================

    # 🔥 Streak system
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_streaks (
            user_id INTEGER PRIMARY KEY,
            streak_count INTEGER DEFAULT 0,
            last_streak_date TEXT,
            highest_streak INTEGER DEFAULT 0
        )
    """)

    # 🏅 Achievements
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            achievement_id TEXT,
            unlocked_at TEXT,
            UNIQUE(user_id, achievement_id)
        )
    """)

    # 💰 Market transactions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS market_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            char_id TEXT,
            transaction_type TEXT,
            price INTEGER,
            timestamp TEXT
        )
    """)

    # 🛒 Market pool
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS market_pool (
            char_id TEXT,
            displayed_at TEXT
        )
    """)

    # 🎛️ User preferences (collection_mode, glow)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            user_id INTEGER PRIMARY KEY,
            collection_mode TEXT DEFAULT 'anime',
            profile_glow INTEGER DEFAULT 1,
            market_filter TEXT DEFAULT 'all'
        )
    """)

    

    # 🎁 Gift log
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gift_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user INTEGER,
            to_user INTEGER,
            char_id TEXT,
            gifted_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 📊 Activity log
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ==================== 🔧 MIGRATIONS ====================
    # Add new columns to existing tables (idempotent)
    migrations = [
        ("group_settings", "message_count", "INTEGER DEFAULT 0"),
        ("group_settings", "spawn_limit", "INTEGER DEFAULT 100"),
        ("groups", "message_count", "INTEGER DEFAULT 0"),
        ("users", "font_pref", "TEXT DEFAULT 'normal'"),
    ]
    for table, column, col_type in migrations:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            logger.info(f"✅ Added column {table}.{column}")
        except sqlite3.OperationalError:
            pass  # column already exists
    # =========================================================

    conn.commit()
    conn.close()
    logger.info("✅ Database initialized")


def check_and_register_user(user_id: int, username: str = None, first_name: str = None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, username, first_name, balance, banned) VALUES (?, ?, ?, ?, ?)",
        (user_id, username, first_name, 500, 0)
    )
    conn.commit()
    conn.close()


# ==================== 🔥 STREAK CONFIG ====================
STREAK_BONUS_TIERS = {
    1: 1000, 2: 1000, 3: 2000, 4: 2000,
    5: 3000, 6: 3000, 7: 5000,
}
STREAK_RESET_DAYS = 2

# ==================== 🛒 MARKET CONFIG ====================
MARKET_POOL_SIZE = 10
MARKET_REFRESH_PRICE = 5000
MARKET_SELL_BACK_PERCENT = 50

# ==================== 🏅 ACHIEVEMENTS CONFIG ====================
ACHIEVEMENTS = {
    "first_char":     {"name": "🎯 First Catch",      "desc": "Claim your first character",            "check": "chars_gte_1"},
    "collector_5":    {"name": "📚 Beginner",         "desc": "Collect 5 unique characters",            "check": "chars_gte_5"},
    "collector_10":   {"name": "📖 Hobbyist",         "desc": "Collect 10 unique characters",           "check": "chars_gte_10"},
    "collector_25":   {"name": "🎓 Enthusiast",       "desc": "Collect 25 unique characters",           "check": "chars_gte_25"},
    "collector_50":   {"name": "💎 Expert",           "desc": "Collect 50 unique characters",           "check": "chars_gte_50"},
    "collector_100":  {"name": "👑 Master",           "desc": "Collect 100 unique characters",          "check": "chars_gte_100"},
    "epic_owner":     {"name": "💜 Epic Hunter",      "desc": "Own at least one EPIC character",        "check": "owns_rarity_epic"},
    "legend_owner":   {"name": "🌟 Legendary",        "desc": "Own at least one LEGENDARY character",   "check": "owns_rarity_legendary"},
    "mythic_owner":   {"name": "🔮 Mythic Touched",   "desc": "Own at least one MYTHIC character",      "check": "owns_rarity_mythic"},
    "rich_1k":        {"name": "💰 Pocket Money",     "desc": "Reach 1,000 coins balance",              "check": "balance_gte_1000"},
    "rich_10k":       {"name": "💸 Tycoon",           "desc": "Reach 10,000 coins balance",             "check": "balance_gte_10000"},
    "rich_100k":      {"name": "🤑 Mogul",            "desc": "Reach 100,000 coins balance",            "check": "balance_gte_100000"},
    "streak_3":       {"name": "🔥 3-Day Streak",     "desc": "Login 3 days in a row",                  "check": "streak_gte_3"},
    "streak_7":       {"name": "🔥 7-Day Streak",     "desc": "Login 7 days in a row",                  "check": "streak_gte_7"},
    "streak_30":      {"name": "⚡ 30-Day Streak",    "desc": "Login 30 days in a row",                 "check": "streak_gte_30"},
    "shopaholic":     {"name": "🛍️ Shopaholic",       "desc": "Make 10 purchases from /shop",           "check": "purchases_gte_10"},
}


# ==================== HELPER FUNCTIONS (used by commands) ====================

def execute(query: str, params: tuple = ()):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(query, params)
    conn.commit()
    conn.close()


def fetch_one(query: str, params: tuple = ()):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(query, params)
    row = cursor.fetchone()
    conn.close()
    return row


def fetch_all(query: str, params: tuple = ()):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return rows


def fetch_value(query: str, params: tuple = ()):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(query, params)
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


# User helpers
def ensure_user(user_id: int, username: str = None, first_name: str = None):
    execute(
        "INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
        (user_id, username, first_name)
    )


def get_balance(user_id: int) -> int:
    row = fetch_one("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    return row[0] if row else 0


def add_balance(user_id: int, amount: int):
    execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))


def remove_balance(user_id: int, amount: int) -> bool:
    bal = get_balance(user_id)
    if bal < amount:
        return False
    execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
    return True


# Collection helpers
def owns_character(user_id: int, char_id: str) -> bool:
    return fetch_one(
        "SELECT 1 FROM user_collection WHERE user_id = ? AND character_id = ?",
        (user_id, char_id)
    ) is not None


def add_to_collection(user_id: int, char_id: str):
    execute("""
        INSERT INTO user_collection (user_id, character_id, count)
        VALUES (?, ?, 1)
        ON CONFLICT(user_id, character_id) DO UPDATE SET count = count + 1
    """, (user_id, char_id))


def remove_from_collection(user_id: int, char_id: str) -> bool:
    row = fetch_one(
        "SELECT count FROM user_collection WHERE user_id = ? AND character_id = ?",
        (user_id, char_id)
    )
    if not row or row[0] <= 0:
        return False
    if row[0] == 1:
        execute("DELETE FROM user_collection WHERE user_id = ? AND character_id = ?",
                (user_id, char_id))
    else:
        execute("UPDATE user_collection SET count = count - 1 WHERE user_id = ? AND character_id = ?",
                (user_id, char_id))
    return True


# Ban helpers
def is_banned(user_id: int) -> bool:
    return fetch_one("SELECT 1 FROM banned_users WHERE user_id = ?", (user_id,)) is not None


def ban_user(user_id: int, username: str = "", reason: str = ""):
    execute("INSERT OR REPLACE INTO banned_users (user_id, username, reason) VALUES (?, ?, ?)",
            (user_id, username, reason))


def unban_user(user_id: int):
    execute("DELETE FROM banned_users WHERE user_id = ?", (user_id,))


# Sudo helpers
def is_sudo(user_id: int) -> bool:
    return fetch_one("SELECT 1 FROM sudo_admins WHERE user_id = ?", (user_id,)) is not None


def add_sudo_user(user_id: int, username: str = "", added_by: int = 0):
    execute("INSERT OR REPLACE INTO sudo_admins (user_id, username, added_by) VALUES (?, ?, ?)",
            (user_id, username, added_by))


def remove_sudo_user(user_id: int):
    execute("DELETE FROM sudo_admins WHERE user_id = ?", (user_id,))


# Streak helpers
def get_streak(user_id: int):
    return fetch_one("""
        SELECT streak_count, last_streak_date, highest_streak
        FROM user_streaks WHERE user_id = ?
    """, (user_id,))


def update_streak(user_id: int, streak_count: int, last_date: str, highest: int):
    execute("""
        INSERT INTO user_streaks (user_id, streak_count, last_streak_date, highest_streak)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            streak_count = excluded.streak_count,
            last_streak_date = excluded.last_streak_date,
            highest_streak = excluded.highest_streak
    """, (user_id, streak_count, last_date, highest))


# Achievement helpers
def has_achievement(user_id: int, achievement_id: str) -> bool:
    return fetch_one("""
        SELECT 1 FROM user_achievements WHERE user_id = ? AND achievement_id = ?
    """, (user_id, achievement_id)) is not None


def unlock_achievement(user_id: int, achievement_id: str) -> bool:
    try:
        execute("""
            INSERT INTO user_achievements (user_id, achievement_id, unlocked_at)
            VALUES (?, ?, datetime('now'))
        """, (user_id, achievement_id))
        return True
    except Exception:
        return False


# Market helpers
def get_market_pool():
    return fetch_all("""
        SELECT c.id, c.name, c.anime, c.rarity, c.msg_id
        FROM market_pool mp
        JOIN characters c ON mp.char_id = c.id
    """)


def clear_market_pool():
    execute("DELETE FROM market_pool")


def add_to_market_pool(char_id: str):
    execute("INSERT INTO market_pool (char_id, displayed_at) VALUES (?, datetime('now'))", (char_id,))


def remove_from_market_pool(char_id: str):
    execute("DELETE FROM market_pool WHERE char_id = ?", (char_id,))


def log_market_transaction(user_id: int, char_id: str, tx_type: str, price: int):
    execute("""
        INSERT INTO market_transactions (user_id, char_id, transaction_type, price, timestamp)
        VALUES (?, ?, ?, ?, datetime('now'))
    """, (user_id, char_id, tx_type, price))


# Preferences helpers
def get_user_pref(user_id: int):
    return fetch_one("SELECT * FROM user_preferences WHERE user_id = ?", (user_id,))


def set_collection_mode(user_id: int, mode: str):
    execute("""
        INSERT INTO user_preferences (user_id, collection_mode) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET collection_mode = ?
    """, (user_id, mode, mode))


def toggle_profile_glow(user_id: int) -> bool:
    row = get_user_pref(user_id)
    new_state = 0 if (row and row[2]) else 1  # row[2] = profile_glow
    execute("""
        INSERT INTO user_preferences (user_id, profile_glow) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET profile_glow = ?
    """, (user_id, new_state, new_state))
    return bool(new_state)


def set_font_pref(user_id: int, font: str):
    execute("""
        INSERT INTO users (user_id, font_pref) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET font_pref = ?
    """, (user_id, font, font))

def get_user(user_id: int):
    return fetch_one("SELECT * FROM users WHERE user_id = ?", (user_id,))


def get_top_anime():
    return fetch_one("""
        SELECT c.anime, COUNT(uc.character_id) as cnt
        FROM user_collection uc JOIN characters c ON uc.character_id = c.id
        GROUP BY c.anime ORDER BY cnt DESC LIMIT 1
    """)


def get_total_groups() -> int:
    return fetch_value("SELECT COUNT(*) FROM groups") or 0

# Stats helpers
def get_total_users() -> int:
    return fetch_value("SELECT COUNT(*) FROM users") or 0


def get_total_coins() -> int:
    return fetch_value("SELECT SUM(balance) FROM users") or 0


def get_popular_character():
    return fetch_one("""
        SELECT c.name, COUNT(uc.character_id) as cnt
        FROM user_collection uc JOIN characters c ON uc.character_id = c.id
        GROUP BY uc.character_id ORDER BY cnt DESC LIMIT 1
    """)


# Leaderboard helpers
def get_top_by_money(limit: int = 10):
    return fetch_all("""
        SELECT user_id, username, balance FROM users
        ORDER BY balance DESC LIMIT ?
    """, (limit,))


def get_top_by_collection(limit: int = 10):
    return fetch_all("""
        SELECT u.user_id, u.username, COUNT(uc.character_id) as char_count
        FROM users u JOIN user_collection uc ON u.user_id = uc.user_id
        GROUP BY u.user_id ORDER BY char_count DESC LIMIT ?
    """, (limit,))
def get_user_collection(user_id: int):
    """Get all characters owned by user (with rarity info)."""
    return fetch_all("""
        SELECT c.id, c.name, c.anime, c.rarity, c.msg_id, uc.count
        FROM user_collection uc
        JOIN characters c ON uc.character_id = c.id
        WHERE uc.user_id = ?
    """, (user_id,))


def get_user_unique_count(user_id: int) -> int:
    """How many DIFFERENT characters user owns."""
    return fetch_value("""
        SELECT COUNT(*) FROM user_collection WHERE user_id = ?
    """, (user_id,)) or 0


def get_character(char_id: str):
    return fetch_one("SELECT * FROM characters WHERE id = ?", (char_id,))


def get_random_character(rarity: str = None):
    # Specify the exact columns in the exact order needed by your spawn function
    query_columns = "id, name, anime, rarity, msg_id"
    
    if rarity:
        return fetch_one(f"""
            SELECT {query_columns} FROM characters WHERE rarity = ?
            ORDER BY RANDOM() LIMIT 1
        """, (rarity,))
        
    return fetch_one(f"SELECT {query_columns} FROM characters ORDER BY RANDOM() LIMIT 1")

def get_character_count() -> int:
    return fetch_value("SELECT COUNT(*) FROM characters") or 0

# ==========================
# WARN HELPERS
# ==========================
def get_warn_count(user_id: int) -> int:
    row = fetch_one("SELECT warn_count FROM warnings WHERE user_id = ?", (user_id,))
    return row[0] if row else 0


def add_warning(user_id: int, warned_by: int, reason: str = ""):
    """Add a warning. Auto-creates row if missing."""
    execute("""
        INSERT INTO warnings (user_id, warn_count, warned_by, reason)
        VALUES (?, 1, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            warn_count = warn_count + 1,
            warned_by = ?,
            reason = ?
    """, (user_id, warned_by, reason, warned_by, reason))


# ==========================
# GROUP HELPERS
# ==========================
def ensure_group(chat_id: int, title: str = ""):
    execute("INSERT OR IGNORE INTO groups (chat_id, title) VALUES (?, ?)", (chat_id, title))
    execute("INSERT OR IGNORE INTO group_settings (chat_id) VALUES (?)", (chat_id,))



# ==========================
# GET ALL TOP ANIME
# ==========================
def get_top_anime(limit: int = 5):
    return fetch_all("""
        SELECT anime, COUNT(*) as cnt
        FROM characters
        WHERE anime IS NOT NULL AND anime != ''
        GROUP BY anime
        ORDER BY cnt DESC
        LIMIT ?
    """, (limit,))
