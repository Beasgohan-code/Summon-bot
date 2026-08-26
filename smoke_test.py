from __future__ import annotations

import ast
import importlib
import os
import pathlib
import sys
import tempfile


ROOT = pathlib.Path(__file__).resolve().parent
PY_MODULES = sorted(ROOT.glob("*.py")) + sorted((ROOT / "plugins").glob("*.py"))

for path in PY_MODULES:
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
print(f"AST parse passed for {len(PY_MODULES)} Python files")

with tempfile.TemporaryDirectory() as temp_dir:
    os.chdir(temp_dir)
    sys.path.insert(0, str(ROOT))

    config = importlib.import_module("config")
    config.DB_NAME = str(pathlib.Path(temp_dir) / "fresh.db")
    storage = importlib.import_module("storage")
    assert "ON CONFLICT DO NOTHING" in storage._translate_sql(
        "INSERT OR IGNORE INTO users (user_id) VALUES (?)"
    )
    assert "CURRENT_TIMESTAMP" in storage._translate_sql(
        "SELECT * FROM premium WHERE expires_at > datetime('now')"
    )

    database = importlib.import_module("database")
    database.DB_NAME = config.DB_NAME
    database.init_db()

    required_tables = {
        "users",
        "user_collection",
        "characters",
        "groups",
        "group_settings",
        "sudo_users",
        "sudo_admins",
        "premium",
        "cooldowns",
        "user_inventory",
    }
    rows = database.fetch_all("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in rows}
    missing = required_tables - tables
    if missing:
        raise AssertionError(f"Fresh DB is missing tables: {sorted(missing)}")
    database.ensure_group(123, "Test Group")
    print("Fresh database initialization passed")

for module_name in (
    "plugins.market",
    "plugins.profile",
    "plugins.nguess",
    "commands_owner",
    "commands_admin",
    "commands_auction",
    "commands_hstats",
    "commands_user",
    "auto_spawn",
    "catch_all",
    "hstats",
    "inline_search",
):
    importlib.import_module(module_name)
    print(f"Import passed: {module_name}")

print("Smoke tests passed")
