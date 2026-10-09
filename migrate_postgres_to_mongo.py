"""Copy the live PostgreSQL data into MongoDB without changing the source.

This is an explicit, reviewable cutover tool. It never runs as part of the bot
and never silently falls back to a local database. Run it first without
``--apply`` to inspect counts, then run with ``--apply`` against a fresh
MongoDB database. The source PostgreSQL database is left untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:  # pragma: no cover - deployment dependency
    psycopg2 = None
    RealDictCursor = None

try:
    from pymongo import MongoClient, ReplaceOne
except ImportError:  # pragma: no cover - deployment dependency
    MongoClient = None
    ReplaceOne = None


SYSTEM_TABLES = {"pg_stat_statements"}


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        # All current money/count columns are integer-valued. Preserve other
        # decimals as strings rather than introducing binary-float loss.
        return int(value) if value == value.to_integral_value() else str(value)
    if isinstance(value, memoryview):
        return bytes(value).hex()
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _stable_id(table: str, row: dict[str, Any], primary_key: tuple[str, ...]) -> str:
    if primary_key and all(row.get(column) is not None for column in primary_key):
        key = {column: _json_value(row.get(column)) for column in primary_key}
    else:
        key = {column: _json_value(row[column]) for column in sorted(row)}
    encoded = json.dumps(key, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return f"{table}:{digest}"


def _table_names(connection) -> list[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        )
        return [row[0] for row in cursor.fetchall() if row[0] not in SYSTEM_TABLES]


def _primary_key(connection, table: str) -> tuple[str, ...]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
             AND tc.table_name = kcu.table_name
            WHERE tc.table_schema = 'public'
              AND tc.table_name = %s
              AND tc.constraint_type = 'PRIMARY KEY'
            ORDER BY kcu.ordinal_position
            """,
            (table,),
        )
        return tuple(row[0] for row in cursor.fetchall())


def _read_table(connection, table: str, primary_key: tuple[str, ...]) -> list[dict[str, Any]]:
    with connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(f'SELECT * FROM "{table}"')
        rows = []
        for raw in cursor.fetchall():
            row = {str(key): _json_value(value) for key, value in dict(raw).items()}
            row["_id"] = _stable_id(table, row, primary_key)
            row["_legacy_table"] = table
            rows.append(row)
        return rows


def migrate(source_url: str, mongo_uri: str, mongo_db_name: str, apply: bool) -> dict[str, int]:
    if psycopg2 is None:
        raise RuntimeError("Install psycopg2-binary to read PostgreSQL.")
    if MongoClient is None or ReplaceOne is None:
        raise RuntimeError("Install pymongo to write MongoDB.")
    if not source_url.startswith(("postgres://", "postgresql://")):
        raise ValueError("SOURCE_DATABASE_URL must be a PostgreSQL URL.")
    if not mongo_uri:
        raise ValueError("MONGO_URI is required.")
    if not mongo_db_name:
        raise ValueError("MONGO_DB_NAME is required.")

    source = psycopg2.connect(source_url, sslmode="require")
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=10_000)
    try:
        client.admin.command("ping")
        database = client[mongo_db_name]
        counts: dict[str, int] = {}
        for table in _table_names(source):
            primary_key = _primary_key(source, table)
            rows = _read_table(source, table, primary_key)
            counts[table] = len(rows)
            if not apply:
                continue
            collection = database[table]
            operations = [ReplaceOne({"_id": row["_id"]}, row, upsert=True) for row in rows]
            if operations:
                collection.bulk_write(operations, ordered=False)
            # The migration is a snapshot. Remove only documents explicitly
            # belonging to this legacy table that were not in this snapshot.
            keep_ids = [row["_id"] for row in rows]
            if keep_ids:
                collection.delete_many({"_legacy_table": table, "_id": {"$nin": keep_ids}})
            else:
                collection.delete_many({"_legacy_table": table})
        return counts
    finally:
        source.close()
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-url", default=os.getenv("SOURCE_DATABASE_URL", os.getenv("DATABASE_URL", "")))
    parser.add_argument("--mongo-uri", default=os.getenv("MONGO_URI", ""))
    parser.add_argument("--mongo-db-name", default=os.getenv("MONGO_DB_NAME", "summon_bot"))
    parser.add_argument("--apply", action="store_true", help="Write the snapshot; default is a dry run.")
    args = parser.parse_args()
    counts = migrate(args.source_url, args.mongo_uri, args.mongo_db_name, args.apply)
    mode = "written" if args.apply else "found"
    print(json.dumps({"mode": mode, "tables": counts}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
