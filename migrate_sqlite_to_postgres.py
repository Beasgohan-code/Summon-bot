"""Migrate Summon-bot data from SQLite to PostgreSQL.

Usage:
    DATABASE_URL='postgresql://user:password@host:5432/dbname' \
        python migrate_sqlite_to_postgres.py --source summon.db

The script is intentionally explicit and does not delete or modify the source
SQLite database. Run it once, verify the row counts, then start the bot with the
same DATABASE_URL.
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import storage


TABLES = (
    "users",
    "user_collection",
    "characters",
    "redeem_codes",
    "banned_users",
    "warnings",
    "group_settings",
    "claim_list",
    "rarity_chances",
    "groups",
    "sudo_users",
    "sudo_admins",
    "premium",
    "cooldowns",
    "user_inventory",
    "user_streaks",
    "user_achievements",
    "market_transactions",
    "market_pool",
    "user_preferences",
    "gift_log",
    "activity_log",
    "auctions",
    "auction_bids",
    "auction_bid_input",
)
SERIAL_TABLES = {
    "user_collection",
    "user_achievements",
    "market_transactions",
    "user_inventory",
    "gift_log",
    "activity_log",
    "auctions",
    "auction_bids",
}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="summon.db", help="SQLite database path")
    parser.add_argument("--database-url", default=None, help="PostgreSQL connection URL")
    return parser.parse_args()


def sqlite_columns(conn, table: str) -> list[str]:
    rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    return [row[1] for row in rows]


def postgres_columns(conn, table: str) -> set[str]:
    rows = conn.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = ?
        """,
        (table,),
    ).fetchall()
    return {row[0] for row in rows}


def migrate_table(source, target, table: str) -> int:
    source_exists = source.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (table,)
    ).fetchone()
    if not source_exists:
        return 0

    source_cols = sqlite_columns(source, table)
    target_cols = postgres_columns(target, table)
    columns = [column for column in source_cols if column in target_cols]
    if not columns:
        return 0

    quoted_columns = ", ".join(f'"{column}"' for column in columns)
    placeholders = ", ".join("?" for _ in columns)
    insert_sql = (
        f'INSERT INTO "{table}" ({quoted_columns}) VALUES ({placeholders}) '
        "ON CONFLICT DO NOTHING"
    )

    rows = source.execute(
        f'SELECT {quoted_columns} FROM "{table}"'
    ).fetchall()
    for offset in range(0, len(rows), 250):
        batch = rows[offset : offset + 250]
        target.executemany(insert_sql, batch)
        target.commit()
    return len(rows)


def reset_sequences(target):
    raw = target._connection
    with raw.cursor() as cursor:
        for table in sorted(SERIAL_TABLES):
            sequence = f"{table}_id_seq"
            cursor.execute(
                "SELECT setval(%s, COALESCE((SELECT MAX(id) FROM \"%s\"), 1), true)"
                % ("%s", table),
                (sequence,),
            )
    raw.commit()


def main():
    args = parse_args()
    source_path = Path(args.source)
    if not source_path.exists():
        raise SystemExit(f"Source SQLite database not found: {source_path}")

    database_url = (args.database_url or storage.DATABASE_URL).strip()
    if not database_url.startswith(("postgres://", "postgresql://")):
        raise SystemExit("Provide a PostgreSQL URL with --database-url or DATABASE_URL")

    storage.configure(database_url)
    import database

    database.init_db()
    source = sqlite3.connect(source_path)
    target = storage.connect()
    try:
        totals = {}
        for table in TABLES:
            totals[table] = migrate_table(source, target, table)
        reset_sequences(target)
    finally:
        source.close()
        target.close()

    print("Migration complete. Rows copied by table:")
    for table, count in totals.items():
        if count:
            print(f"  {table}: {count}")


if __name__ == "__main__":
    main()
