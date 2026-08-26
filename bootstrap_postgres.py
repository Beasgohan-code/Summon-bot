"""Bootstrap the shared Summon PostgreSQL schema without deleting existing data.

Run this only against the intended Summon PostgreSQL database. It creates missing
tables and applies the Mini App contract; it does not copy a legacy SQLite file
or drop character media columns.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg2


REQUIRED_USER_COLUMNS = {"user_id", "username", "balance", "banned", "favorite"}


def assert_target_compatible(connection) -> None:
    """Fail closed before modifying a database that is not a Summon target."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        )
        tables = {row[0] for row in cursor.fetchall()}
        if not tables:
            return
        if "users" not in tables:
            raise SystemExit(
                "Refusing to bootstrap a non-empty PostgreSQL database without the Summon users table. "
                "Use a dedicated empty database or confirm the intended Summon target."
            )
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'users'
            """
        )
        columns = {row[0] for row in cursor.fetchall()}
        missing = REQUIRED_USER_COLUMNS - columns
        if missing:
            formatted = ", ".join(sorted(missing))
            raise SystemExit(
                "Refusing to bootstrap: the existing public.users table is not a Summon users table "
                f"(missing: {formatted}). Confirm a dedicated Summon PostgreSQL target before continuing."
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--miniapp-contract", default="../summon-miniapp/sql/summon_miniapp_contract.sql")
    args = parser.parse_args()
    if not args.database_url or not args.database_url.startswith(("postgres://", "postgresql://")):
        raise SystemExit("Set DATABASE_URL to the intended Summon PostgreSQL connection URL.")

    preflight_connection = psycopg2.connect(args.database_url, sslmode="require")
    try:
        assert_target_compatible(preflight_connection)
    finally:
        preflight_connection.close()

    import storage

    storage.configure(args.database_url)
    import database

    database.init_db()
    contract = Path(args.miniapp_contract).resolve()
    if not contract.exists():
        raise SystemExit(f"Mini App contract not found: {contract}")
    connection = psycopg2.connect(args.database_url, sslmode="require")
    try:
        with connection.cursor() as cursor:
            cursor.execute(contract.read_text(encoding="utf-8"))
        connection.commit()
    finally:
        connection.close()
    print("Summon PostgreSQL bootstrap and Mini App contract completed.")


if __name__ == "__main__":
    main()
