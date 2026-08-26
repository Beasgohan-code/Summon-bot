"""PostgreSQL-only connection layer for Summon-bot runtime data.

All player, collection, economy, and transaction state is stored in PostgreSQL.
SQLite is retained only by the explicit offline migration utility as a source
format; the bot never opens a local SQLite database at runtime.
"""
from __future__ import annotations

import datetime as _dt
import re
import sqlite3
from collections.abc import Iterator
from typing import Any

from config import DB_NAME, DATABASE_URL as CONFIG_DATABASE_URL

try:
    import psycopg2
except ImportError:  # pragma: no cover - only needed for PostgreSQL deployments
    psycopg2 = None


DATABASE_URL = CONFIG_DATABASE_URL


def configure(database_url: str | None = None) -> None:
    """Set the active database URL for the current process."""
    global DATABASE_URL
    DATABASE_URL = (database_url or "").strip()


def using_postgres() -> bool:
    return DATABASE_URL.startswith(("postgres://", "postgresql://"))


def _normalise_value(value: Any) -> Any:
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value


class HybridRow:
    """Tuple-compatible row that also supports SQLite-style string indexing."""

    def __init__(self, values: tuple[Any, ...], columns: list[str]):
        self._values = tuple(_normalise_value(value) for value in values)
        self._columns = columns
        self._index = {column: index for index, column in enumerate(columns)}

    def __getitem__(self, key: int | str) -> Any:
        if isinstance(key, str):
            return self._values[self._index[key]]
        return self._values[key]

    def __iter__(self) -> Iterator[Any]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def keys(self) -> list[str]:
        return list(self._columns)

    def values(self) -> tuple[Any, ...]:
        return self._values

    def items(self):
        return ((column, self[column]) for column in self._columns)


class PostgresCursor:
    def __init__(self, connection: "PostgresConnection"):
        self.connection = connection
        self._cursor = connection._connection.cursor()
        self._columns: list[str] = []

    def execute(self, query: str, params: tuple[Any, ...] | list[Any] = ()):
        if _is_table_info_query(query):
            table = re.search(r"table_info\(([^)]+)\)", query, re.IGNORECASE).group(1).strip()
            self._cursor.execute(
                """
                SELECT ordinal_position - 1, column_name, data_type,
                       CASE WHEN is_nullable = 'NO' THEN 1 ELSE 0 END,
                       column_default, 0
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position
                """,
                (table,),
            )
            self._columns = ["cid", "name", "type", "notnull", "dflt_value", "pk"]
            return self

        translated = _translate_sql(query)
        self._cursor.execute("SAVEPOINT summon_statement")
        try:
            self._cursor.execute(translated, tuple(params or ()))
        except Exception as exc:
            self._cursor.execute("ROLLBACK TO SAVEPOINT summon_statement")
            self._cursor.execute("RELEASE SAVEPOINT summon_statement")
            if psycopg2 is not None and isinstance(exc, psycopg2.Error):
                raise sqlite3.OperationalError(str(exc)) from exc
            raise
        self._columns = [description[0] for description in (self._cursor.description or [])]
        return self

    def executemany(self, query: str, params_seq):
        translated = _translate_sql(query)
        self._cursor.execute("SAVEPOINT summon_many")
        try:
            self._cursor.executemany(translated, params_seq)
        except Exception as exc:
            self._cursor.execute("ROLLBACK TO SAVEPOINT summon_many")
            self._cursor.execute("RELEASE SAVEPOINT summon_many")
            if psycopg2 is not None and isinstance(exc, psycopg2.Error):
                raise sqlite3.OperationalError(str(exc)) from exc
            raise
        self._columns = [description[0] for description in (self._cursor.description or [])]
        return self

    def fetchone(self):
        row = self._cursor.fetchone()
        return HybridRow(row, self._columns) if row is not None else None

    def fetchall(self):
        return [HybridRow(row, self._columns) for row in self._cursor.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())

    def close(self):
        self._cursor.close()


class PostgresConnection:
    def __init__(self, database_url: str):
        if psycopg2 is None:
            raise RuntimeError(
                "PostgreSQL support requires psycopg2-binary. Install requirements.txt first."
            )
        self._connection = psycopg2.connect(database_url)
        self.row_factory = None

    def cursor(self) -> PostgresCursor:
        return PostgresCursor(self)

    def execute(self, query: str, params: tuple[Any, ...] | list[Any] = ()):
        cursor = self.cursor()
        cursor.execute(query, params)
        return cursor

    def executemany(self, query: str, params_seq):
        cursor = self.cursor()
        cursor.executemany(query, params_seq)
        return cursor

    def executescript(self, script: str):
        for statement in script.split(";"):
            statement = statement.strip()
            if statement:
                self.execute(statement)

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def close(self):
        self._connection.close()


def connect(database: str | None = None):
    """Return the configured PostgreSQL connection.

    The optional ``database`` argument exists only for legacy helper signatures;
    no local file database is opened by this function.
    """
    if not using_postgres():
        raise RuntimeError(
            "DATABASE_URL must be a postgresql:// or postgres:// URL. "
            "Summon-bot no longer supports SQLite at runtime."
        )
    return PostgresConnection(DATABASE_URL)


def _is_table_info_query(query: str) -> bool:
    return bool(re.match(r"\s*PRAGMA\s+table_info\s*\(", query, re.IGNORECASE))


def _replace_qmark_params(query: str) -> str:
    return query.replace("?", "%s")


def _translate_sql(query: str) -> str:
    sql = query.strip()
    sql = re.sub(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bINSERT\s+OR\s+REPLACE\s+INTO\s+banned_users\b", "INSERT INTO banned_users", sql, flags=re.IGNORECASE)
    sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    sql = re.sub(
        r"\bTEXT\s+DEFAULT\s+CURRENT_TIMESTAMP\b",
        "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        sql,
        flags=re.IGNORECASE,
    )

    sql = sql.replace("datetime('now', '+24 hours')", "(CURRENT_TIMESTAMP + INTERVAL '24 hours')")
    sql = sql.replace("datetime('now')", "CURRENT_TIMESTAMP")
    sql = re.sub(r"datetime\('now',\s*\?\)", "(CURRENT_TIMESTAMP + ?::interval)", sql, flags=re.IGNORECASE)
    sql = re.sub(r"datetime\(expires_at,\s*\?\)", "(expires_at::timestamp + ?::interval)", sql, flags=re.IGNORECASE)
    sql = re.sub(
        r"CAST\(\(julianday\(([^)]+)\)\s*-\s*julianday\('now'\)\)\s*\*\s*24\s+AS\s+INT\)",
        r"CAST(EXTRACT(EPOCH FROM (\1::timestamp - CURRENT_TIMESTAMP)) / 3600 AS INT)",
        sql,
        flags=re.IGNORECASE,
    )

    sql = re.sub(
        r"expires_at\s*>\s*CURRENT_TIMESTAMP",
        "expires_at::timestamp > CURRENT_TIMESTAMP",
        sql,
        flags=re.IGNORECASE,
    )
    sql = _replace_qmark_params(sql)
    upper = sql.upper()
    if upper.startswith("INSERT INTO") and "ON CONFLICT" not in upper:
        if "BANNED_USERS" in upper and "USER_ID" in upper:
            columns_match = re.search(r"\(([^)]+)\)\s*VALUES", sql, re.IGNORECASE | re.DOTALL)
            if columns_match:
                columns = [column.strip() for column in columns_match.group(1).split(",")]
                updates = ", ".join(
                    f"{column} = EXCLUDED.{column}"
                    for column in columns
                    if column.lower() != "user_id"
                )
                sql = f"{sql} ON CONFLICT (user_id) DO UPDATE SET {updates or 'user_id = EXCLUDED.user_id'}"
        elif "OR IGNORE" in query.upper():
            sql = f"{sql} ON CONFLICT DO NOTHING"
    return sql


# Read the configured URL only after all helpers are defined.
configure(DATABASE_URL)
