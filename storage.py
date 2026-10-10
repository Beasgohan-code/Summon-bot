"""MongoDB persistence layer for Summon-bot.

The command modules historically expressed their reads and writes as small SQL
statements.  This module keeps that public cursor-shaped interface so the bot's
UI and feature handlers remain stable, but every operation is translated to
MongoDB documents.  No local database, SQL server, or silent fallback is used.

MongoDB is the only runtime source of truth.  ``MONGO_URI`` and
``MONGO_DB_NAME`` are the only settings used to connect to it.
"""
from __future__ import annotations

import contextvars
import datetime as _dt
import random
import re
import threading
from collections.abc import Iterator
from typing import Any

from config import MONGO_DB_NAME as CONFIG_MONGO_DB_NAME
from config import MONGO_URI as CONFIG_MONGO_URI

try:  # The dependency is required in production; keeping import-time errors clear helps smoke tests.
    from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument
    from pymongo.errors import DuplicateKeyError, PyMongoError
except ImportError:  # pragma: no cover - exercised only in minimal lint environments
    ASCENDING = 1
    DESCENDING = -1
    MongoClient = None
    ReturnDocument = None

    class DuplicateKeyError(Exception):
        pass

    class PyMongoError(Exception):
        pass


MONGO_URI = CONFIG_MONGO_URI
MONGO_DB_NAME = CONFIG_MONGO_DB_NAME
_bound_params = contextvars.ContextVar("summon_bound_params", default=())
_client = None
_client_lock = threading.Lock()


# The document collections deliberately retain the legacy table names.  This
# makes the PostgreSQL snapshot migration lossless and keeps collection names
# predictable for operators inspecting Atlas.
_PRIMARY_KEYS: dict[str, tuple[str, ...]] = {
    "users": ("user_id",),
    "warnings": ("user_id",),
    "group_settings": ("chat_id",),
    "user_collection": ("user_id", "character_id"),
    "characters": ("id",),
    "redeem_codes": ("code",),
    "banned_users": ("user_id",),
    "claim_list": ("rarity_id",),
    "rarity_chances": ("rarity_id",),
    "groups": ("chat_id",),
    "sudo_users": ("user_id",),
    "sudo_admins": ("user_id",),
    "premium": ("user_id",),
    "cooldowns": ("user_id", "command"),
    "user_inventory": ("id",),
    "auctions": ("id",),
    "auction_bids": ("id",),
    "auction_bid_input": ("user_id",),
    "user_streaks": ("user_id",),
    "user_achievements": ("user_id", "achievement_id"),
    "market_transactions": ("id",),
    "market_pool": ("char_id",),
    "user_preferences": ("user_id",),
    "gift_log": ("id",),
    "activity_log": ("id",),
    "miniapp_rewards": ("event_id",),
}

# Used for PRAGMA compatibility in the few legacy handlers that inspect the
# users schema.  It is metadata only; MongoDB does not execute DDL here.
_SCHEMA_COLUMNS: dict[str, list[str]] = {
    "users": [
        "user_id", "username", "balance", "banned", "favorite", "last_daily",
        "last_hclaim", "last_spin", "font_pref", "first_name", "last_hclaim_count",
    ],
    "characters": ["id", "name", "anime", "rarity", "image_url", "created_at"],
    "user_collection": ["id", "user_id", "character_id", "count", "obtained_at"],
}


def configure(mongo_uri: str | None = None, db_name: str | None = None) -> None:
    """Configure the MongoDB target for the current process.

    This helper is primarily useful for tests and process bootstrapping.  It
    never accepts a file path and never changes the configured database to a
    local fallback.
    """
    global MONGO_URI, MONGO_DB_NAME, _client
    if mongo_uri is not None:
        MONGO_URI = mongo_uri.strip()
    if db_name is not None:
        MONGO_DB_NAME = db_name.strip()
    if _client is not None:
        _client.close()
        _client = None


def using_mongo() -> bool:
    return MONGO_URI.startswith(("mongodb://", "mongodb+srv://"))


# Backwards-compatible name used by a few operational checks.  It describes
# the active backend; it does not imply SQL support.
def using_postgres() -> bool:
    return False


def _require_driver() -> None:
    if MongoClient is None:
        raise RuntimeError("MongoDB support requires pymongo. Install requirements.txt first.")


def _require_config() -> None:
    if not using_mongo():
        raise RuntimeError(
            "MONGO_URI must be configured with a mongodb:// or mongodb+srv:// URL. "
            "Summon-bot has no SQLite, PostgreSQL, or local-file fallback."
        )
    if not MONGO_DB_NAME:
        raise RuntimeError("MONGO_DB_NAME must be configured and non-empty.")
    _require_driver()


def _get_client():
    global _client
    _require_config()
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = MongoClient(
                    MONGO_URI,
                    serverSelectionTimeoutMS=10_000,
                    connectTimeoutMS=10_000,
                    retryWrites=True,
                )
    return _client


def ping() -> None:
    """Fail fast if MongoDB cannot be reached."""
    _get_client().admin.command("ping")


def _utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None, microsecond=0).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def _normalise_value(value: Any) -> Any:
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value


class HybridRow:
    """Tuple-compatible row with SQLite-style name access for old handlers."""

    def __init__(self, values: tuple[Any, ...], columns: list[str]):
        self._values = tuple(_normalise_value(value) for value in values)
        self._columns = list(columns)
        self._index = {column: index for index, column in enumerate(self._columns)}

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


class MongoCursor:
    def __init__(self, connection: "MongoConnection"):
        self.connection = connection
        self._rows: list[HybridRow] = []
        self._columns: list[str] = []
        self._rowcount = 0
        self.lastrowid = None

    @property
    def rowcount(self) -> int:
        return self._rowcount

    def execute(self, query: str, params: tuple[Any, ...] | list[Any] = ()):
        self._rows = []
        self._columns = []
        self._rowcount = 0
        self.lastrowid = None
        bound = _bind_params(query.strip(), tuple(params or ()))
        upper = bound.upper()

        if not bound:
            return self
        if upper.startswith("SELECT") or upper.startswith("PRAGMA"):
            self._rows, self._columns = self._select(bound, tuple(params or ()))
        elif upper.startswith("INSERT"):
            self._rowcount, self.lastrowid = self._insert(bound)
        elif upper.startswith("UPDATE"):
            self._rowcount = self._update(bound)
        elif upper.startswith("DELETE"):
            self._rowcount = self._delete(bound)
        elif upper.startswith(("CREATE ", "ALTER ", "DROP ", "DO ", "TRUNCATE ")):
            # Schema is represented by collections and indexes.  DDL strings
            # from legacy modules are intentionally harmless no-ops.
            self._rowcount = 0
        else:
            raise ValueError(f"Unsupported database statement: {query[:100]}")
        return self

    def executemany(self, query: str, params_seq):
        total = 0
        for params in params_seq:
            self.execute(query, params)
            total += max(0, self._rowcount)
        self._rowcount = total
        return self

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows

    def __iter__(self):
        return iter(self.fetchall())

    def close(self):
        self._rows = []

    # ---------- statement implementations ----------
    def _collection(self, table: str):
        return self.connection.database[table]

    def _select(self, query: str, params: tuple[Any, ...]):
        if query.upper().startswith("PRAGMA"):
            match = re.search(r"table_info\s*\(\s*([\w]+)\s*\)", query, re.I)
            table = match.group(1) if match else ""
            names = _SCHEMA_COLUMNS.get(table, [])
            return [HybridRow((index, name, "TEXT", 0, None, 0), ["cid", "name", "type", "notnull", "dflt_value", "pk"]) for index, name in enumerate(names)], ["cid", "name", "type", "notnull", "dflt_value", "pk"]

        # Two nested aggregate forms are used only for Mini App/global rank.
        if re.search(r"FROM\s*\(\s*SELECT", query, re.I):
            return self._select_nested_rank(query, params)

        match = re.match(r"SELECT\s+(.*?)\s+FROM\s+(.+)$", query, re.I | re.S)
        if not match:
            expressions = _split_csv(query[6:].strip())
            values = [_eval_expression(expr, {}, [], self.connection.database, params) for expr in expressions]
            columns = [_expression_name(expr) for expr in expressions]
            return [HybridRow(tuple(values), columns)], columns

        select_part, from_rest = match.groups()
        clauses = _split_clauses(from_rest)
        records = _join_records(clauses["from"], self.connection.database)
        where = clauses.get("where")
        if where:
            records = [record for record in records if _match_condition(where, record, self.connection.database, params)]

        group_part = clauses.get("group")
        groups: list[list[dict[str, Any]]]
        if group_part:
            group_exprs = _split_csv(group_part)
            grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
            for record in records:
                key = tuple(_eval_expression(expr, record, records, self.connection.database, params) for expr in group_exprs)
                grouped.setdefault(key, []).append(record)
            groups = list(grouped.values())
        elif _has_aggregate(select_part) or clauses.get("having"):
            groups = [records]
        else:
            groups = [[record] for record in records]

        if clauses.get("having"):
            groups = [group for group in groups if _match_condition(clauses["having"], group[0] if group else {}, self.connection.database, params, group=group)]

        expressions = _split_csv(select_part)
        columns = _projection_columns(expressions, groups[0][0] if groups and groups[0] else {})
        output: list[HybridRow] = []
        for group in groups:
            record = group[0] if group else {}
            values: list[Any] = []
            for expression in expressions:
                clean, alias = _split_alias(expression)
                if clean == "*" or clean.endswith(".*"):
                    prefix = clean[:-2] if clean.endswith(".*") else ""
                    for field in _expanded_fields(clean, record):
                        values.append(record.get(f"{prefix}.{field}" if prefix else field))
                else:
                    values.append(_eval_expression(clean, record, records, self.connection.database, params, group=group))
            output.append(HybridRow(tuple(values), columns))

        order = clauses.get("order")
        if order:
            output = _sort_rows(output, order, columns, records, self.connection.database, params)
        if clauses.get("offset"):
            output = output[_integer_value(clauses["offset"], params):]
        if clauses.get("limit"):
            output = output[:_integer_value(clauses["limit"], params)]
        return output, columns

    def _select_nested_rank(self, query: str, params: tuple[Any, ...]):
        # The bot uses this shape for collection rank. Evaluate it directly so
        # nested SQL never becomes a second persistence engine.
        if re.search(r"COUNT\s*\(\s*DISTINCT\s+character_id\s*\).*FROM\s+user_collection", query, re.I | re.S):
            threshold = params[0] if params else 0
            counts: dict[Any, set[Any]] = {}
            for document in self._collection("user_collection").find({}):
                counts.setdefault(document.get("user_id"), set()).add(document.get("character_id"))
            rank = sum(len(characters) > int(threshold) for characters in counts.values()) + 1
            return [HybridRow((rank,), ["count"])], ["count"]
        return [], []

    def _insert(self, query: str):
        header = re.match(r"INSERT\s+(?P<mode>OR\s+(?:IGNORE|REPLACE)\s+)?INTO\s+(?P<table>[\w]+)\s*", query, re.I)
        if not header:
            raise ValueError(f"Unsupported INSERT statement: {query[:160]}")
        mode = (header.group("mode") or "").upper()
        table = header.group("table")
        position = header.end()
        raw_columns = None
        if position < len(query) and query[position] == "(":
            raw_columns, position = _parenthesized(query, position)
        values_keyword = re.match(r"\s*VALUES\s*", query[position:], re.I)
        if not values_keyword:
            raise ValueError(f"Unsupported INSERT statement: {query[:160]}")
        position += values_keyword.end()
        if position >= len(query) or query[position] != "(":
            raise ValueError(f"Unsupported INSERT values: {query[:160]}")
        raw_values, position = _parenthesized(query, position)
        tail = query[position:]
        if raw_columns:
            columns = [item.strip().strip('"') for item in _split_csv(raw_columns)]
        else:
            columns = {
                "rarity_chances": ["rarity_id", "rarity_name", "chance_value"],
                "claim_list": ["rarity_id", "chance", "rarity_name"],
            }.get(table, [])
        values = [_literal_value(item, query) for item in _split_csv(raw_values)]
        if not columns or len(columns) != len(values):
            raise ValueError(f"INSERT into {table} requires a known column list")
        document = _with_defaults(table, dict(zip(columns, values)))
        conflict_target, conflict_assignments = _parse_conflict(tail)
        if conflict_target is None:
            conflict_target = _PRIMARY_KEYS.get(table, ())
        existing = self._find_one(table, document, conflict_target)

        if existing is not None:
            if mode == "OR IGNORE" and not conflict_assignments:
                return 0, None
            if mode == "OR REPLACE":
                replacement = dict(existing)
                replacement.update(document)
                self._replace(table, existing, replacement)
                return 1, replacement.get("id")
            if conflict_assignments:
                updates = _evaluate_assignments(
                    conflict_assignments, existing, query, self.connection.database, document,
                )
                self._update_document(table, existing, updates)
                return 1, existing.get("id")
            return 0, None

        if "id" in _PRIMARY_KEYS.get(table, ()) and document.get("id") is None:
            document["id"] = self._next_id(table)
        document["_id"] = _document_id(table, document)
        try:
            self._collection(table).insert_one(document)
        except DuplicateKeyError:
            return 0, None
        self.lastrowid = document.get("id")
        returning = re.search(r"\bRETURNING\s+([\w]+)", tail, re.I)
        return 1, document.get(returning.group(1)) if returning else document.get("id")

    def _update(self, query: str):
        match = re.match(r"UPDATE\s+(?P<table>[\w]+)\s+SET\s+(?P<set>.+?)(?:\s+WHERE\s+(?P<where>.+))?$", query, re.I | re.S)
        if not match:
            raise ValueError(f"Unsupported UPDATE statement: {query[:160]}")
        table, assignment_text, where = match.group("table"), match.group("set"), match.group("where")
        docs = list(self._collection(table).find({}))
        changed = 0
        for document in docs:
            if where and not _match_condition(where, _record_for_document(document, table), self.connection.database, _bound_params.get()):
                continue
            updates = _evaluate_assignments(_split_csv(assignment_text), document, query, self.connection.database)
            if updates:
                self._update_document(table, document, updates)
                changed += 1
        return changed

    def _delete(self, query: str):
        match = re.match(r"DELETE\s+FROM\s+(?P<table>[\w]+)(?:\s+WHERE\s+(?P<where>.+))?$", query, re.I | re.S)
        if not match:
            raise ValueError(f"Unsupported DELETE statement: {query[:160]}")
        table, where = match.group("table"), match.group("where")
        docs = list(self._collection(table).find({}))
        removed = 0
        for document in docs:
            if where and not _match_condition(where, _record_for_document(document, table), self.connection.database, _bound_params.get()):
                continue
            self._collection(table).delete_one({"_id": document["_id"]})
            removed += 1
        return removed

    def _find_one(self, table: str, document: dict[str, Any], keys: tuple[str, ...]):
        if not keys:
            return None
        filter_doc = {key: document.get(key) for key in keys if document.get(key) is not None}
        if len(filter_doc) != len(keys):
            return None
        return self._collection(table).find_one(filter_doc)

    def _replace(self, table: str, old: dict[str, Any], new: dict[str, Any]):
        new["_id"] = old["_id"]
        self._collection(table).replace_one({"_id": old["_id"]}, new)

    def _update_document(self, table: str, old: dict[str, Any], updates: dict[str, Any]):
        if not updates:
            return
        self._collection(table).update_one({"_id": old["_id"]}, {"$set": updates})

    def _next_id(self, table: str) -> int:
        counter = self.connection.database["_counters"].find_one_and_update(
            {"_id": table}, {"$inc": {"value": 1}}, upsert=True,
            return_document=ReturnDocument.AFTER if ReturnDocument is not None else None,
        )
        return int(counter["value"])


class MongoConnection:
    """Small connection facade backed exclusively by a MongoDB database."""

    def __init__(self, database_name: str | None = None):
        client = _get_client()
        self.client = client
        self.database = client[database_name or MONGO_DB_NAME]
        self.row_factory = None
        self._closed = False

    def cursor(self) -> MongoCursor:
        if self._closed:
            raise RuntimeError("MongoDB connection is closed")
        return MongoCursor(self)

    def execute(self, query: str, params: tuple[Any, ...] | list[Any] = ()):
        cursor = self.cursor()
        cursor.execute(query, params)
        return cursor

    def executemany(self, query: str, params_seq):
        cursor = self.cursor()
        cursor.executemany(query, params_seq)
        return cursor

    def executescript(self, script: str):
        for statement in _split_statements(script):
            if statement.strip():
                self.execute(statement)
        return self

    def commit(self):
        # Mongo writes are durable once acknowledged. Critical balance and
        # collection helpers use atomic update operators below.
        return None

    def rollback(self):
        # There is no client-side write buffer to silently discard.
        return None

    def close(self):
        self._closed = True


def connect(database: str | None = None) -> MongoConnection:
    """Open a MongoDB-backed connection; never opens a local file database."""
    return MongoConnection(database)


# ---------- public Mongo-native helpers for critical paths ----------
def public_miniapp_snapshot(limit: int = 10) -> dict[str, Any]:
    """Return deliberately non-personal public Mini App data.

    Guest mode never calls the user dashboard or registers a visitor. Only
    aggregate catalogue metadata and the already-public money leaderboard are
    returned; Telegram IDs, collections, reward history, and account fields
    are intentionally omitted.
    """
    limit = max(1, min(int(limit), 50))
    database = _get_client()[MONGO_DB_NAME]

    rarity_counts: dict[str, int] = {}
    for document in database["characters"].find({}, {"rarity": 1}):
        rarity = str(document.get("rarity") or "Unknown")
        rarity_counts[rarity] = rarity_counts.get(rarity, 0) + 1
    rarities = [
        {"name": rarity, "count": count}
        for rarity, count in sorted(rarity_counts.items(), key=lambda item: (-item[1], item[0]))
    ]

    leaderboard = []
    cursor = database["users"].find(
        {"banned": {"$ne": 1}},
        {"username": 1, "first_name": 1, "balance": 1, "_id": 0},
    ).sort("balance", DESCENDING).limit(limit)
    for rank, document in enumerate(cursor, 1):
        username = str(document.get("username") or "").lstrip("@") or None
        name = str(document.get("first_name") or username or "Summoner")
        leaderboard.append({
            "rank": rank,
            "name": name,
            "username": username,
            "balance": int(document.get("balance") or 0),
        })
    return {
        "catalogue": {"total": sum(rarity_counts.values()), "rarities": rarities},
        "leaderboard": leaderboard,
    }


def premium_expiry(user_id: int) -> str | None:
    """Read premium expiry directly from MongoDB."""
    document = _get_client()[MONGO_DB_NAME]["premium"].find_one(
        {"user_id": int(user_id)}, {"expires_at": 1, "_id": 0},
    )
    return str(document["expires_at"]) if document and document.get("expires_at") else None


def revoke_premium(user_id: int) -> bool:
    """Remove premium access directly from MongoDB."""
    result = _get_client()[MONGO_DB_NAME]["premium"].delete_one({"user_id": int(user_id)})
    return result.deleted_count == 1


def premium_remaining_seconds(user_id: int) -> int:
    """Return active premium time without querying a relational schema."""
    document = _get_client()[MONGO_DB_NAME]["premium"].find_one(
        {"user_id": int(user_id)}, {"expires_at": 1, "_id": 0},
    )
    expiry = _parse_datetime(document.get("expires_at")) if document else None
    if expiry is None:
        return 0
    now = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
    return max(0, int((expiry - now).total_seconds()))


def initialize_database() -> None:
    """Create indexes and verify the configured MongoDB before bot startup."""
    connection = connect()
    database = connection.database
    ping()
    indexes = {
        "users": [([("user_id", ASCENDING)], {"unique": True})],
        "characters": [([("id", ASCENDING)], {"unique": True})],
        "user_collection": [([("user_id", ASCENDING), ("character_id", ASCENDING)], {"unique": True})],
        "miniapp_rewards": [([("event_id", ASCENDING)], {"unique": True}), ([("user_id", ASCENDING), ("created_at", DESCENDING)], {})],
        "auctions": [([("id", ASCENDING)], {"unique": True}), ([("status", ASCENDING), ("end_time", ASCENDING)], {})],
        "auction_bids": [([("auction_id", ASCENDING), ("bidder_id", ASCENDING), ("amount", ASCENDING)], {})],
        "sudo_users": [([("user_id", ASCENDING)], {"unique": True})],
        "sudo_admins": [([("user_id", ASCENDING)], {"unique": True})],
        "banned_users": [([("user_id", ASCENDING)], {"unique": True})],
        "warnings": [([("user_id", ASCENDING)], {"unique": True})],
        "group_settings": [([("chat_id", ASCENDING)], {"unique": True})],
        "groups": [([("chat_id", ASCENDING)], {"unique": True})],
        "claim_list": [([("rarity_id", ASCENDING)], {"unique": True})],
        "rarity_chances": [([("rarity_id", ASCENDING)], {"unique": True})],
        "redeem_codes": [([("code", ASCENDING)], {"unique": True})],
        "auction_bid_input": [([("user_id", ASCENDING)], {"unique": True})],
        "user_streaks": [([("user_id", ASCENDING)], {"unique": True})],
        "user_achievements": [([("user_id", ASCENDING), ("achievement_id", ASCENDING)], {"unique": True})],
        "market_pool": [([("char_id", ASCENDING)], {})],
        "user_preferences": [([("user_id", ASCENDING)], {"unique": True})],
        "premium": [([("user_id", ASCENDING)], {"unique": True})],
        "cooldowns": [([("user_id", ASCENDING), ("command", ASCENDING)], {"unique": True})],
    }
    for collection_name, specs in indexes.items():
        for fields, options in specs:
            try:
                database[collection_name].create_index(fields, **options)
            except PyMongoError as exc:
                # An existing non-unique legacy index should not be silently
                # accepted for identity/economy data.
                if options.get("unique"):
                    raise RuntimeError(f"Could not create required unique index on {collection_name}: {exc}") from exc
    connection.close()


def atomic_increment(table: str, key: dict[str, Any], field: str, amount: int, *, minimum: int | None = None) -> bool:
    """Atomically change a numeric field in MongoDB."""
    collection = _get_client()[MONGO_DB_NAME][table]
    filter_doc = dict(key)
    if minimum is not None:
        filter_doc[field] = {"$gte": minimum}
    result = collection.update_one(filter_doc, {"$inc": {field: amount}})
    return result.modified_count == 1


def increment_collection(user_id: int, character_id: str, amount: int = 1) -> bool:
    """Atomically add copies to a user's collection, creating the row once."""
    collection = _get_client()[MONGO_DB_NAME]["user_collection"]
    now = _utc_now()
    result = collection.update_one(
        {"user_id": user_id, "character_id": character_id},
        {"$inc": {"count": amount}, "$setOnInsert": {"user_id": user_id, "character_id": character_id, "obtained_at": now}},
        upsert=True,
    )
    return bool(result.acknowledged)


def decrement_collection(user_id: int, character_id: str) -> bool:
    """Remove exactly one copy without allowing concurrent over-removal."""
    collection = _get_client()[MONGO_DB_NAME]["user_collection"]
    if ReturnDocument is None:
        return False
    updated = collection.find_one_and_update(
        {"user_id": user_id, "character_id": character_id, "count": {"$gte": 1}},
        {"$inc": {"count": -1}},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        return False
    if int(updated.get("count", 0)) <= 0:
        collection.delete_one({"_id": updated["_id"], "count": {"$lte": 0}})
    return True


def transfer_balance(sender_id: int, receiver_id: int, amount: int) -> bool:
    """Move coins between users in one MongoDB transaction."""
    if amount <= 0 or sender_id == receiver_id:
        return False
    client = _get_client()
    database = client[MONGO_DB_NAME]
    try:
        with client.start_session() as session:
            with session.start_transaction():
                debit = database["users"].update_one(
                    {"user_id": sender_id, "balance": {"$gte": amount}},
                    {"$inc": {"balance": -amount}}, session=session,
                )
                if debit.modified_count != 1:
                    return False
                credit = database["users"].update_one(
                    {"user_id": receiver_id}, {"$inc": {"balance": amount}}, session=session,
                )
                if credit.modified_count != 1:
                    raise RuntimeError("Receiver disappeared during balance transfer")
        return True
    except PyMongoError:
        # MongoDB deployments without transactions are not accepted as a
        # production configuration; never silently downgrade an economy write.
        raise RuntimeError("MongoDB transactions are required for balance transfers")


def transfer_collection(sender_id: int, receiver_id: int, character_id: str) -> bool:
    """Move one character copy atomically between users."""
    if sender_id == receiver_id:
        return False
    client = _get_client()
    database = client[MONGO_DB_NAME]
    if ReturnDocument is None:
        return False
    try:
        with client.start_session() as session:
            with session.start_transaction():
                source = database["user_collection"].find_one_and_update(
                    {"user_id": sender_id, "character_id": character_id, "count": {"$gte": 1}},
                    {"$inc": {"count": -1}}, return_document=ReturnDocument.AFTER, session=session,
                )
                if not source:
                    return False
                if int(source.get("count", 0)) <= 0:
                    database["user_collection"].delete_one({"_id": source["_id"]}, session=session)
                database["user_collection"].update_one(
                    {"user_id": receiver_id, "character_id": character_id},
                    {"$inc": {"count": 1}, "$setOnInsert": {"user_id": receiver_id, "character_id": character_id, "obtained_at": _utc_now()}},
                    upsert=True, session=session,
                )
        return True
    except PyMongoError:
        raise RuntimeError("MongoDB transactions are required for collection transfers")


def grant_premium(user_id: int, duration_seconds: int, granted_by: int) -> str:
    """Grant or extend premium access in MongoDB without schema assumptions.

    This replaces the old SQL ``granted_at`` insert path. Existing documents
    from an older deployment remain valid because MongoDB documents are
    schema-flexible; the timestamp is added with ``$set`` on every grant.
    """
    if duration_seconds <= 0:
        raise ValueError("Premium duration must be positive")
    database = _get_client()[MONGO_DB_NAME]
    collection = database["premium"]
    now = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None, microsecond=0)
    existing = collection.find_one({"user_id": user_id})
    current_expiry = _parse_datetime(existing.get("expires_at")) if existing else None
    if current_expiry and current_expiry > now:
        expiry = current_expiry + _dt.timedelta(seconds=duration_seconds)
    else:
        expiry = now + _dt.timedelta(seconds=duration_seconds)
    values = {
        "user_id": user_id,
        "expires_at": expiry.strftime("%Y-%m-%d %H:%M:%S"),
        "granted_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "granted_by": granted_by,
    }
    if existing:
        collection.update_one({"_id": existing["_id"]}, {"$set": values})
    else:
        values["_id"] = _document_id("premium", values)
        collection.insert_one(values)
    return values["expires_at"]


def claim_miniapp_reward(event_id: str, user_id: int, game: str, amount: int, timestamp: str, cooldown_cutoff: str) -> bool:
    """Credit one Mini App event exactly once with an atomic cooldown check."""
    database = _get_client()[MONGO_DB_NAME]
    ledger = database["miniapp_rewards"]
    try:
        ledger.insert_one({"_id": event_id, "event_id": event_id, "user_id": user_id, "game": game, "amount": amount, "created_at": timestamp})
    except DuplicateKeyError:
        return False
    try:
        result = database["users"].update_one(
            {"user_id": user_id, "$or": [{f"last_{game}": {"$exists": False}}, {f"last_{game}": {"$lte": cooldown_cutoff}}]},
            {"$inc": {"balance": amount}, "$set": {f"last_{game}": timestamp}},
        )
        if result.matched_count != 1:
            ledger.delete_one({"_id": event_id})
            return False
    except Exception:
        ledger.delete_one({"_id": event_id})
        raise
    return True


# ---------- SQL-shaped compatibility helpers ----------
def _bind_params(query: str, params: tuple[Any, ...]) -> str:
    iterator = iter(enumerate(params))
    output: list[str] = []
    index = 0
    in_quote = None
    for char in query:
        if char in "'\"":
            if in_quote == char:
                in_quote = None
            elif in_quote is None:
                in_quote = char
            output.append(char)
            continue
        if char == "?" and in_quote is None:
            output.append(f"__PARAM{index}__")
            index += 1
        else:
            output.append(char)
    return "".join(output)


def _extract_markers(text: str) -> tuple[Any, ...]:
    # Query execution paths pass original params to evaluators; this fallback
    # is only used by internal update/delete helpers after binding. Markers are
    # resolved as their integer index where no original tuple is available.
    return tuple(int(value) for value in re.findall(r"__PARAM(\d+)__", text))


def _parenthesized(text: str, start: int) -> tuple[str, int]:
    if start >= len(text) or text[start] != "(":
        raise ValueError("Expected parenthesized SQL segment")
    depth, quote = 0, None
    for index in range(start, len(text)):
        char = text[index]
        if char in "'\"":
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
        elif quote is None:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return text[start + 1:index], index + 1
    raise ValueError("Unclosed SQL parenthesis")


def _split_csv(text: str) -> list[str]:
    result, current, depth, quote = [], [], 0, None
    for char in text:
        if char in "'\"":
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
        elif quote is None:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == "," and depth == 0:
                result.append("".join(current).strip())
                current = []
                continue
        current.append(char)
    if current:
        result.append("".join(current).strip())
    return result


def _split_statements(script: str) -> list[str]:
    return [part.strip() for part in script.split(";") if part.strip()]


def _find_keyword(text: str, keyword: str, start: int = 0) -> int:
    depth, quote = 0, None
    upper = text.upper()
    wanted = keyword.upper()
    index = start
    while index <= len(text) - len(keyword):
        char = text[index]
        if char in "'\"":
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
            index += 1
            continue
        if quote is None:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif depth == 0 and upper.startswith(wanted, index):
                before = index == 0 or not upper[index - 1].isalnum()
                after = index + len(keyword) == len(text) or not upper[index + len(keyword)].isalnum()
                if before and after:
                    return index
        index += 1
    return -1


def _split_clauses(from_rest: str) -> dict[str, str]:
    keys = [("where", "WHERE"), ("group", "GROUP BY"), ("having", "HAVING"), ("order", "ORDER BY"), ("limit", "LIMIT"), ("offset", "OFFSET")]
    locations = [(key, _find_keyword(from_rest, word)) for key, word in keys]
    locations = [(key, position, word) for (key, word), (_, position) in zip(keys, locations) if position >= 0]
    locations.sort(key=lambda item: item[1])
    if not locations:
        return {"from": from_rest.strip()}
    result = {"from": from_rest[:locations[0][1]].strip()}
    for index, (key, position, word) in enumerate(locations):
        end = locations[index + 1][1] if index + 1 < len(locations) else len(from_rest)
        result[key] = from_rest[position + len(word):end].strip()
    return result


def _strip_outer(value: str) -> str:
    value = value.strip()
    while value.startswith("(") and value.endswith(")"):
        depth, valid = 0, True
        for index, char in enumerate(value):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0 and index != len(value) - 1:
                    valid = False
                    break
        if valid:
            value = value[1:-1].strip()
        else:
            break
    return value


def _parse_table_alias(part: str) -> tuple[str, str]:
    tokens = part.strip().split()
    if not tokens:
        return "", ""
    table = tokens[0].strip('"')
    alias = tokens[1] if len(tokens) > 1 and tokens[1].upper() != "AS" else (tokens[2] if len(tokens) > 2 else table)
    return table, alias.strip('"')


def _join_records(from_part: str, database) -> list[dict[str, Any]]:
    base_match = re.match(r"([\w]+)(?:\s+(?:AS\s+)?([\w]+))?(.*)$", from_part.strip(), re.I | re.S)
    if not base_match:
        return []
    table, alias, remainder = base_match.group(1), base_match.group(2) or base_match.group(1), base_match.group(3)
    records = [_record_for_document(doc, table, alias) for doc in database[table].find({})]
    join_pattern = re.compile(r"\s*(?P<kind>LEFT\s+|INNER\s+)?JOIN\s+(?P<table>[\w]+)(?:\s+(?:AS\s+)?(?P<alias>[\w]+))?\s+ON\s+", re.I)
    while remainder.strip():
        join_match = join_pattern.match(remainder)
        if not join_match:
            break
        on_start = join_match.end()
        next_join = re.search(r"\s+(?:LEFT\s+|INNER\s+)?JOIN\s+", remainder[on_start:], re.I)
        on_end = on_start + next_join.start() if next_join else len(remainder)
        condition = remainder[on_start:on_end].strip()
        join_table = join_match.group("table")
        join_alias = join_match.group("alias") or join_table
        right_docs = [_record_for_document(doc, join_table, join_alias) for doc in database[join_table].find({})]
        joined: list[dict[str, Any]] = []
        for left in records:
            matches = [right for right in right_docs if _match_condition(condition, {**left, **right}, database, ())]
            if matches:
                joined.extend({**left, **right} for right in matches)
            elif (join_match.group("kind") or "").strip().upper().startswith("LEFT"):
                joined.append(left)
        records = joined
        remainder = remainder[on_end:]
    return records


def _record_for_document(document: dict[str, Any], table: str, alias: str | None = None) -> dict[str, Any]:
    result = {f"{alias or table}.{key}": value for key, value in document.items() if key != "_id"}
    for key, value in document.items():
        if key != "_id":
            result.setdefault(key, value)
    result["__table"] = table
    result["__document"] = document
    return result


def _split_alias(expression: str) -> tuple[str, str | None]:
    match = re.match(r"(.+?)\s+AS\s+([\w]+)$", expression.strip(), re.I | re.S)
    if match:
        return match.group(1).strip(), match.group(2)
    return expression.strip(), None


def _expression_name(expression: str) -> str:
    clean, alias = _split_alias(expression)
    if alias:
        return alias
    clean = clean.strip()
    if clean.endswith(".*"):
        return clean[:-2]
    if "." in clean and re.match(r"^[\w.]+$", clean):
        return clean.rsplit(".", 1)[1]
    if clean.upper().startswith("COUNT"):
        return "count"
    return clean


def _expanded_fields(expression: str, record: dict[str, Any]) -> list[str]:
    prefix = expression[:-2] if expression.endswith(".*") else ""
    fields = []
    for key in record:
        if key.startswith("__"):
            continue
        if prefix:
            if not key.startswith(prefix + "."):
                continue
            field = key.split(".", 1)[1]
        else:
            if "." in key:
                continue
            field = key
        if field not in fields:
            fields.append(field)
    return fields


def _projection_columns(expressions: list[str], record: dict[str, Any]) -> list[str]:
    columns: list[str] = []
    for expression in expressions:
        clean, alias = _split_alias(expression)
        if clean == "*" or clean.endswith(".*"):
            columns.extend(_expanded_fields(clean, record))
        else:
            columns.append(alias or _expression_name(clean))
    return columns


def _has_aggregate(text: str) -> bool:
    return bool(re.search(r"\b(COUNT|SUM|AVG|MIN|MAX)\s*\(", text, re.I))


def _field_value(token: str, record: dict[str, Any]) -> Any:
    token = token.strip().strip('"')
    if token in record:
        return record[token]
    marker = re.fullmatch(r"__PARAM(\d+)__", token)
    if marker:
        return _bound_value(token, int(marker.group(1)))
    if token.startswith("LOWER(") and token.endswith(")"):
        value = _field_value(token[6:-1], record)
        return str(value or "").lower()
    if token.startswith("UPPER(") and token.endswith(")"):
        value = _field_value(token[6:-1], record)
        return str(value or "").upper()
    if token.lower().startswith("date(") and token.endswith(")"):
        value = _field_value(token[5:-1], record)
        return str(value or "").replace("T", " ").split(" ", 1)[0]
    if token.startswith("CAST("):
        inner = token[5:-1]
        inner = re.sub(r"\s+AS\s+\w+\s*$", "", inner, flags=re.I)
        return _field_value(inner, record)
    if token.upper() == "CURRENT_TIMESTAMP" or token.lower().startswith("datetime("):
        if token.lower().startswith("datetime(") and token.endswith(")"):
            arguments = _split_csv(token[token.find("(") + 1:-1])
            base = _field_value(arguments[0], record) if arguments else _utc_now()
            parsed = _parse_datetime(base) or _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
            if len(arguments) > 1:
                modifier = str(_field_value(arguments[1], record) or "")
                interval = re.search(r"([+-])\s*(\d+)\s*(hour|hours|day|days|minute|minutes)", modifier, re.I)
                if interval:
                    amount = int(interval.group(2))
                    unit = interval.group(3).lower()
                    seconds = amount * (86400 if unit.startswith("day") else 3600 if unit.startswith("hour") else 60)
                    parsed += _dt.timedelta(seconds=seconds if interval.group(1) == "+" else -seconds)
            return parsed.strftime("%Y-%m-%d %H:%M:%S")
        return _utc_now()
    if token.upper() == "NULL":
        return None
    if re.fullmatch(r"-?\d+", token):
        return int(token)
    if re.fullmatch(r"-?(?:\d+\.\d*|\.\d+)", token):
        return float(token)
    if len(token) >= 2 and token[0] == token[-1] == "'":
        return token[1:-1].replace("''", "'")
    return None


def _literal_value(token: str, query: str, record: dict[str, Any] | None = None) -> Any:
    token = token.strip()
    match = re.fullmatch(r"__PARAM(\d+)__", token)
    if match:
        # Values are bound before parsing; the original value is attached by
        # the query helper below when a marker is encountered.
        return _bound_value(query, int(match.group(1)))
    return _field_value(token, record or {})


def _bound_value(query: str, index: int) -> Any:
    # _bind_params stores actual values in a thread-local-free marker format by
    # replacing markers with repr values in _encode_bound_params. This fallback
    # handles numeric markers generated by internal calls.
    values = _bound_params.get()
    return values[index] if index < len(values) else index


def _encode_bound_params(query: str, params: tuple[Any, ...]) -> str:
    return _bind_params(query, params)


def _coerce_compare(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value)
    parsed_date = _parse_datetime(text)
    if parsed_date is not None:
        return parsed_date
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return text


def _like(value: Any, pattern: Any, insensitive: bool = False) -> bool:
    if value is None or pattern is None:
        return False
    value, pattern = str(value), str(pattern)
    flags = re.I if insensitive else 0
    regex = "^" + re.escape(pattern).replace("%", ".*").replace("_", ".") + "$"
    return re.search(regex, value, flags) is not None


def _split_boolean(expression: str, operator: str) -> list[str]:
    parts, start, depth, quote = [], 0, 0, None
    upper = expression.upper()
    index = 0
    while index < len(expression):
        char = expression[index]
        if char in "'\"":
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
        elif quote is None:
            if char == "(": depth += 1
            elif char == ")": depth -= 1
            elif depth == 0 and upper.startswith(operator, index):
                before = index == 0 or expression[index - 1].isspace()
                after = index + len(operator) == len(expression) or expression[index + len(operator)].isspace()
                if before and after:
                    parts.append(expression[start:index].strip())
                    start = index + len(operator)
                    index += len(operator) - 1
        index += 1
    if parts:
        parts.append(expression[start:].strip())
    return parts


def _match_condition(expression: str, record: dict[str, Any], database, params: tuple[Any, ...], group: list[dict[str, Any]] | None = None) -> bool:
    expression = _strip_outer(expression)
    ors = _split_boolean(expression, "OR")
    if len(ors) > 1:
        return any(_match_condition(part, record, database, params, group) for part in ors)
    ands = _split_boolean(expression, "AND")
    if len(ands) > 1:
        return all(_match_condition(part, record, database, params, group) for part in ands)
    expression = _strip_outer(expression)
    if expression.upper().startswith("NOT "):
        return not _match_condition(expression[4:], record, database, params, group)
    if re.search(r"\s+IS\s+NOT\s+NULL$", expression, re.I):
        return _field_value(re.split(r"\s+IS\s+NOT\s+NULL$", expression, flags=re.I)[0], record) is not None
    if re.search(r"\s+IS\s+NULL$", expression, re.I):
        return _field_value(re.split(r"\s+IS\s+NULL$", expression, flags=re.I)[0], record) is None
    in_match = re.match(r"(.+?)\s+IN\s*\((.+)\)$", expression, re.I | re.S)
    if in_match:
        left = _field_value(in_match.group(1), record)
        inside = in_match.group(2).strip()
        sub = re.search(r"SELECT\s+DISTINCT\s+(\w+)\s+FROM\s+(\w+)\s+WHERE\s+(.+)", inside, re.I | re.S)
        if sub:
            field, table, subwhere = sub.groups()
            values = [_field_value(field, _record_for_document(doc, table),) for doc in database[table].find({}) if _match_condition(subwhere, _record_for_document(doc, table), database, params)]
        else:
            values = [_field_value(item, record) for item in _split_csv(inside)]
        return left in values
    like_match = re.match(r"(.+?)\s+(I?LIKE)\s+(.+)$", expression, re.I | re.S)
    if like_match:
        return _like(_field_value(like_match.group(1), record), _field_value(like_match.group(3), record), like_match.group(2).upper() == "ILIKE")
    comparison = re.match(r"(.+?)\s*(>=|<=|<>|!=|=|>|<)\s*(.+)$", expression, re.S)
    if comparison:
        left_token, right_token = comparison.group(1), comparison.group(3)
        left_value = _eval_expression(left_token, record, [record], database, params, group=group) if _has_aggregate(left_token) else _field_value(left_token, record)
        right_value = _eval_expression(right_token, record, [record], database, params, group=group) if _has_aggregate(right_token) else _field_value(right_token, record)
        left = _coerce_compare(left_value)
        right = _coerce_compare(right_value)
        op = comparison.group(2)
        if left is None or right is None:
            return op == "=" and left is right
        try:
            return {"=": left == right, "!=": left != right, "<>": left != right, ">": left > right, "<": left < right, ">=": left >= right, "<=": left <= right}[op]
        except TypeError:
            left, right = str(left), str(right)
            return {"=": left == right, "!=": left != right, "<>": left != right, ">": left > right, "<": left < right, ">=": left >= right, "<=": left <= right}[op]
    return bool(_field_value(expression, record))


def _eval_expression(expression: str, record: dict[str, Any], records: list[dict[str, Any]], database, params: tuple[Any, ...], group: list[dict[str, Any]] | None = None) -> Any:
    expression = _strip_outer(expression.strip())
    case = re.match(r"CASE\s+WHEN\s+(.+?)\s+THEN\s+(.+?)\s+ELSE\s+(.+?)\s+END$", expression, re.I | re.S)
    if case:
        return _eval_expression(case.group(2), record, records, database, params, group) if _match_condition(case.group(1), record, database, params, group) else _eval_expression(case.group(3), record, records, database, params, group)
    if re.match(r"^(COUNT|SUM|AVG|MIN|MAX)\s*\(", expression, re.I):
        rows = group if group is not None else records
        aggregate = re.match(r"(COUNT|SUM|AVG|MIN|MAX)\s*\((DISTINCT\s+)?(.+?)\)$", expression, re.I | re.S)
        if not aggregate:
            return 0
        function, distinct, operand = aggregate.groups()
        if operand.strip() == "*":
            values = rows
        else:
            values = [_eval_expression(operand, item, records, database, params) for item in rows]
        if distinct:
            unique = []
            for value in values:
                if value not in unique: unique.append(value)
            values = unique
        if function.upper() == "COUNT":
            return sum(value is not None for value in values) if operand.strip() != "*" else len(values)
        numeric = [float(value) for value in values if value is not None]
        if function.upper() == "SUM": return int(sum(numeric)) if numeric and all(float(v).is_integer() for v in numeric) else sum(numeric)
        if function.upper() == "AVG": return sum(numeric) / len(numeric) if numeric else None
        if function.upper() == "MIN": return min(values) if values else None
        return max(values) if values else None
    coalesce = re.match(r"(?:COALESCE|IFNULL)\((.+),\s*(.+)\)$", expression, re.I | re.S)
    if coalesce:
        value = _eval_expression(coalesce.group(1), record, records, database, params, group)
        return value if value is not None else _eval_expression(coalesce.group(2), record, records, database, params, group)
    cast = re.match(r"CAST\((.+)\s+AS\s+(\w+)\)$", expression, re.I | re.S)
    if cast:
        value = _eval_expression(cast.group(1), record, records, database, params, group)
        if cast.group(2).upper() in {"INTEGER", "INT"}:
            try: return int(value)
            except (TypeError, ValueError): return 0
        return str(value) if value is not None else None
    hours = re.search(r"julianday\(([^)]+)\).*?julianday\(['\"]now['\"]\).*?\*\s*24", expression, re.I)
    if hours:
        value = _field_value(hours.group(1), record)
        parsed = _parse_datetime(value)
        if not parsed: return None
        return int((_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None) - parsed).total_seconds() / 3600)
    marker = re.fullmatch(r"__PARAM(\d+)__", expression)
    if marker:
        return _bound_value(expression, int(marker.group(1)))
    # Arithmetic required by rank/aggregate-like projections.
    arithmetic = re.match(r"(.+?)\s*([+-])\s*(\d+)$", expression)
    if arithmetic:
        value = _eval_expression(arithmetic.group(1), record, records, database, params, group)
        return (value or 0) + (int(arithmetic.group(3)) if arithmetic.group(2) == "+" else -int(arithmetic.group(3)))
    return _field_value(expression, record)


def _parse_datetime(value: Any) -> _dt.datetime | None:
    if not value: return None
    if isinstance(value, _dt.datetime):
        return value.astimezone(_dt.timezone.utc).replace(tzinfo=None) if value.tzinfo else value
    try:
        text = str(value).replace("T", " ").split(".", 1)[0].replace("Z", "")
        return _dt.datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            parsed = _dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed.astimezone(_dt.timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed
        except ValueError:
            return None


def _integer_value(value: str, params: tuple[Any, ...]) -> int:
    parsed = _field_value(value.strip(), {})
    try: return int(parsed)
    except (TypeError, ValueError): return 0


def _sort_rows(rows: list[HybridRow], order: str, columns: list[str], records: list[dict[str, Any]], database, params: tuple[Any, ...]) -> list[HybridRow]:
    if re.search(r"RANDOM\s*\(\)", order, re.I):
        random.shuffle(rows)
        return rows
    terms = _split_csv(order)
    for term in reversed(terms):
        parts = term.strip().split()
        descending = len(parts) > 1 and parts[-1].upper() == "DESC"
        key_name = " ".join(parts[:-1]) if descending or (len(parts) > 1 and parts[-1].upper() == "ASC") else term.strip()
        key_name = _expression_name(key_name)
        try:
            index = columns.index(key_name)
        except ValueError:
            index = -1
        def value(row):
            item = row[index] if index >= 0 else None
            coerced = _coerce_compare(item)
            if coerced is None:
                return (1, 2, "")
            if isinstance(coerced, (int, float)):
                return (0, 0, coerced)
            return (0, 1, str(coerced))
        rows.sort(key=value, reverse=descending)
    return rows


def _document_id(table: str, document: dict[str, Any]) -> str:
    keys = _PRIMARY_KEYS.get(table, ())
    if len(keys) == 1 and document.get(keys[0]) is not None:
        return f"{table}:{document[keys[0]]}"
    return f"{table}:" + ":".join(str(document.get(key, "")) for key in keys)


def _with_defaults(table: str, document: dict[str, Any]) -> dict[str, Any]:
    result = dict(document)
    now = _utc_now()
    if table == "users":
        result.setdefault("balance", 0)
        result.setdefault("banned", 0)
        result.setdefault("font_pref", "mono")
    if table == "user_collection":
        result.setdefault("count", 1)
        result.setdefault("obtained_at", now)
    if table in {"characters", "warnings", "redeem_codes", "banned_users", "groups", "sudo_users", "sudo_admins", "claim_list", "rarity_chances", "premium", "user_streaks", "user_preferences", "market_pool"}:
        for field in ("created_at", "added_at", "banned_at", "granted_at", "last_streak_date", "displayed_at"):
            if field in result and result[field] is None:
                result[field] = now
    return result


def _parse_conflict(tail: str) -> tuple[tuple[str, ...] | None, list[str]]:
    match = re.search(r"ON\s+CONFLICT\s*(?:\(([^)]+)\))?\s+DO\s+(?:UPDATE\s+SET\s+(.+)|NOTHING)", tail, re.I | re.S)
    if not match:
        return None, []
    target = tuple(item.strip() for item in _split_csv(match.group(1))) if match.group(1) else None
    return target, _split_csv(match.group(2)) if match.group(2) else []


def _evaluate_assignments(
    assignments: list[str],
    document: dict[str, Any],
    query: str,
    database=None,
    excluded: dict[str, Any] | None = None,
) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    context = dict(document)
    if excluded:
        context.update({f"excluded.{key}": value for key, value in excluded.items()})
    for assignment in assignments:
        if "=" not in assignment:
            continue
        field, expression = assignment.split("=", 1)
        field = field.strip().strip('"')
        expression = expression.strip()
        case = re.match(r"CASE\s+WHEN\s+(.+?)\s+THEN\s+(.+?)\s+ELSE\s+(.+?)\s+END$", expression, re.I | re.S)
        if case:
            condition, true_value, false_value = case.groups()
            selected = true_value if _match_condition(condition, _record_for_document(context, "values"), database, _bound_params.get()) else false_value
            expression = selected.strip()
        coalesce = re.match(r"COALESCE\((\w+),\s*0\)\s*([+-])\s*(.+)$", expression, re.I)
        arithmetic = re.match(r"(\w+)\s*([+-])\s*(.+)$", expression)
        if coalesce:
            base = document.get(coalesce.group(1)) or 0
            amount = _field_value(coalesce.group(3), context)
            updates[field] = base + (amount if coalesce.group(2) == "+" else -amount)
        elif arithmetic:
            base = document.get(arithmetic.group(1)) or 0
            amount = _field_value(arithmetic.group(3), context)
            if isinstance(amount, str) and amount.startswith("__PARAM"):
                amount = _bound_value(query, int(re.search(r"\d+", amount).group()))
            if isinstance(base, (int, float)) and isinstance(amount, str):
                try:
                    amount = int(amount)
                except ValueError:
                    amount = 0
            updates[field] = base + (amount if arithmetic.group(2) == "+" else -amount)
        else:
            updates[field] = _literal_value(expression, query, context) if not expression.startswith("excluded.") else context.get(expression)
    return updates


# Give the binder access to original parameter values without global database
# state.  It is set for the duration of each cursor operation.
_original_execute = MongoCursor.execute


def _execute_with_values(self, query, params=()):
    token = _bound_params.set(tuple(params or ()))
    try:
        return _original_execute(self, query, params)
    finally:
        _bound_params.reset(token)


MongoCursor.execute = _execute_with_values

configure(MONGO_URI, MONGO_DB_NAME)
