from __future__ import annotations

import ast
import importlib
import pathlib
import sys
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parent
PY_MODULES = sorted(ROOT.glob("*.py")) + sorted((ROOT / "plugins").glob("*.py"))

for path in PY_MODULES:
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
print(f"AST parse passed for {len(PY_MODULES)} Python files")

sys.path.insert(0, str(ROOT))
storage = importlib.import_module("storage")

storage.configure("")
try:
    storage.connect()
except RuntimeError as exc:
    assert "no longer supports SQLite" in str(exc)
else:
    raise AssertionError("Storage accepted an empty DATABASE_URL")

storage.configure("postgresql://example.invalid/summon_bot")
assert storage.using_postgres()
assert "ON CONFLICT DO NOTHING" in storage._translate_sql(
    "INSERT OR IGNORE INTO users (user_id) VALUES (?)"
)
assert "CURRENT_TIMESTAMP" in storage._translate_sql(
    "SELECT * FROM premium WHERE expires_at > datetime('now')"
)

with patch.object(storage, "PostgresConnection", return_value="postgres-connection"):
    assert storage.connect() == "postgres-connection"

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

print("PostgreSQL-only smoke tests passed")
