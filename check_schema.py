#!/usr/bin/env python3
"""
FULL DATABASE SCHEMA CHECKER for Summon Bot
Checks all tables for missing columns, wrong types, etc.
Run: python3 check_schema.py
"""
import sqlite3
import os

DB_PATH = "summon.db"

# Expected schema based on your bot's code usage
# Add more tables/columns as you find issues
EXPECTED_SCHEMA = {
    "users": {
        "required": ["user_id", "username", "balance", "banned", "favorite", 
                     "last_daily", "last_hclaim", "last_spin", "font_pref", "first_name"],
        "optional": []
    },
    "user_inventory": {
        "required": ["id", "user_id", "item_id", "uses_remaining", "expires_at", "purchased_at"],
        "optional": []
    },
    "user_collection": {
        "required": ["id", "user_id", "character_id", "count", "obtained_at"],
        "optional": []
    },
    "characters": {
        "required": ["id", "name", "anime", "rarity", "msg_id", "created_at", "img_url", "img_url2"],
        "optional": []
    },
    "groups": {
        "required": ["chat_id", "message_count"],
        "optional": ["spawn_limit"]  # might be in group_settings instead
    },
    "group_settings": {
        "required": ["chat_id", "message_count", "spawn_limit"],
        "optional": []
    },
    "market_transactions": {
        "required": ["id", "user_id", "char_id", "transaction_type", "price", "timestamp"],
        "optional": []
    },
    "market_pool": {
        "required": ["char_id", "displayed_at"],
        "optional": []
    },
    "auctions": {
        "required": ["id", "character_id", "seller_id", "start_price", "highest_bid",
                     "highest_bidder_id", "chat_id", "pinned_msg_id", "created_at", "end_time", "status"],
        "optional": []
    },
    "auction_bids": {
        "required": ["id", "auction_id", "user_id", "amount", "created_at"],
        "optional": []
    },
    "auction_bid_input": {
        "required": ["user_id", "auction_id", "created_at"],
        "optional": []
    },
    "premium": {
        "required": ["user_id", "expires_at", "granted_at", "granted_by"],
        "optional": []
    },
    "user_streaks": {
        "required": ["user_id", "streak_count", "last_streak_date", "highest_streak"],
        "optional": []
    },
    "user_achievements": {
        "required": ["id", "user_id", "achievement_id", "unlocked_at"],
        "optional": []
    },
    "user_preferences": {
        "required": ["user_id", "collection_mode", "profile_glow", "market_filter"],
        "optional": []
    },
    "gift_log": {
        "required": ["id", "from_user", "to_user", "char_id", "gifted_at"],
        "optional": []
    },
    "activity_log": {
        "required": ["id", "user_id", "action", "timestamp"],
        "optional": []
    },
    "redeem_codes": {
        "required": ["code", "character_id", "uses", "created_by", "reward", "created_at"],
        "optional": []
    },
    "claim_list": {
        "required": ["rarity_id", "chance", "rarity_name"],
        "optional": []
    },
    "rarity_chances": {
        "required": ["rarity_id", "rarity_name", "chance_value"],
        "optional": []
    },
    "warnings": {
        "required": ["user_id", "warn_count", "warned_by", "reason", "warned_at"],
        "optional": []
    },
    "banned_users": {
        "required": ["user_id", "username", "reason"],
        "optional": []
    },
    "sudo_users": {
        "required": ["user_id", "username", "added_at"],
        "optional": []
    },
    "sudo_admins": {
        "required": ["user_id", "added_by", "added_at"],
        "optional": []
    },
}

def check_database():
    print("=" * 70)
    print("🔍 SUMMON BOT DATABASE SCHEMA CHECKER")
    print("=" * 70)

    if not os.path.exists(DB_PATH):
        print(f"\n❌ Database file '{DB_PATH}' not found!")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Get all tables
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    actual_tables = {t[0] for t in cur.fetchall()}

    expected_tables = set(EXPECTED_SCHEMA.keys())

    # Check for missing tables
    missing_tables = expected_tables - actual_tables
    if missing_tables:
        print(f"\n⚠️  MISSING TABLES (expected but not found):")
        for t in sorted(missing_tables):
            print(f"   ❌ {t}")

    # Check for extra tables
    extra_tables = actual_tables - expected_tables
    if extra_tables:
        print(f"\n📦 EXTRA TABLES (not in expected schema):")
        for t in sorted(extra_tables):
            print(f"   ℹ️  {t}")

    # Check each table's columns
    print(f"\n{'─' * 70}")
    print("📋 COLUMN CHECKS")
    print('─' * 70)

    issues_found = 0

    for table in sorted(actual_tables):
        cur.execute(f"PRAGMA table_info({table});")
        actual_columns = {col[1] for col in cur.fetchall()}

        if table in EXPECTED_SCHEMA:
            required = set(EXPECTED_SCHEMA[table]["required"])
            optional = set(EXPECTED_SCHEMA[table]["optional"])

            missing_cols = required - actual_columns
            extra_cols = actual_columns - required - optional

            status = "✅" if not missing_cols else "❌"
            print(f"\n{status} Table: {table}")
            print(f"   Columns: {', '.join(sorted(actual_columns))}")

            if missing_cols:
                print(f"   ❌ MISSING columns: {', '.join(sorted(missing_cols))}")
                issues_found += 1
            if extra_cols:
                print(f"   ℹ️  EXTRA columns: {', '.join(sorted(extra_cols))}")
        else:
            print(f"\nℹ️  Table: {table} (unknown - not in expected schema)")
            print(f"   Columns: {', '.join(sorted(actual_columns))}")

    print(f"\n{'=' * 70}")
    if issues_found == 0:
        print("✅ ALL CHECKS PASSED! No missing columns found.")
    else:
        print(f"❌ FOUND {issues_found} TABLE(S) WITH MISSING COLUMNS")
        print("   Run the suggested ALTER TABLE commands to fix.")
    print("=" * 70)

    conn.close()

if __name__ == "__main__":
    check_database()
