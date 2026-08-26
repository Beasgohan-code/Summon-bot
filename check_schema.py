#!/usr/bin/env python3
"""Validate the Summon-bot PostgreSQL schema without using local SQLite files."""
from __future__ import annotations

import os

import psycopg2


EXPECTED_SCHEMA = {
    "users": {"user_id", "username", "balance", "banned", "favorite", "last_daily", "last_hclaim", "last_spin", "font_pref", "first_name"},
    "user_collection": {"id", "user_id", "character_id", "count", "obtained_at"},
    "characters": {"id", "name", "anime", "rarity", "image_url", "created_at"},
    "economy_transactions": {"id", "user_id", "type", "amount", "balance_after", "metadata", "created_at"},
    "daily_claims": {"user_id", "claimed_on", "reward", "created_at"},
    "debates": {"id", "topic", "prompt", "side_a_label", "side_b_label", "status", "ends_at", "created_at"},
    "debate_positions": {"id", "debate_id", "user_id", "side", "body", "created_at"},
    "debate_votes": {"debate_id", "user_id", "position_id", "created_at"},
    "game_rounds": {"id", "user_id", "target", "choice", "reward_cap", "reward", "expires_at", "settled_at", "created_at"},
}


def main() -> None:
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url.startswith(("postgres://", "postgresql://")):
        raise SystemExit("Set DATABASE_URL to the target Summon PostgreSQL connection URL.")
    conn = psycopg2.connect(database_url, sslmode="require")
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'public'"
            )
            columns: dict[str, set[str]] = {}
            for table, column in cursor.fetchall():
                columns.setdefault(table, set()).add(column)
    finally:
        conn.close()

    failed = False
    for table, required in EXPECTED_SCHEMA.items():
        missing = required - columns.get(table, set())
        if missing:
            failed = True
            print(f"❌ {table}: missing {', '.join(sorted(missing))}")
        else:
            print(f"✅ {table}")
    if failed:
        raise SystemExit("PostgreSQL schema is incomplete. Apply the documented migration before starting the bot.")
    print("✅ Summon PostgreSQL schema contract is complete.")


if __name__ == "__main__":
    main()
