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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--miniapp-contract", default="../summon-miniapp/sql/summon_miniapp_contract.sql")
    args = parser.parse_args()
    if not args.database_url or not args.database_url.startswith(("postgres://", "postgresql://")):
        raise SystemExit("Set DATABASE_URL to the intended Summon PostgreSQL connection URL.")

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
