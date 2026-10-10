from __future__ import annotations

import ast
import importlib
import pathlib
import sys


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
    assert "MONGO_URI" in str(exc)
else:
    raise AssertionError("Storage accepted an empty MONGO_URI")

storage.configure("mongodb://example.invalid/summon_bot", "summon_bot")
assert storage.using_mongo()
assert not storage.using_postgres()
assert "__PARAM0__" in storage._bind_params(
    "SELECT * FROM users WHERE user_id = ?", (123,)
)

media_urls = importlib.import_module("media_urls")
assert media_urls.telegram_media_reference("photo", "file-123") == "telegram:photo:file-123"
assert media_urls.parse_telegram_media_reference("telegram:animation:file-123") == (
    "animation",
    "file-123",
)
assert media_urls.parse_telegram_media_reference("telegram:photo:file:with-colon") is None

webapp = importlib.import_module("webapp")
for asset_path in ("/app", "/app/styles.css", "/app/app.js", "/app/manifest.webmanifest"):
    asset_response = webapp.handle_request("GET", asset_path, "", {})
    assert asset_response and asset_response[0] == 200
try:
    webapp.validate_init_data("")
except ValueError:
    pass
else:
    raise AssertionError("WebApp accepted empty Telegram init data")

for module_name in (
    "health",
    "webapp",
    "logging_utils",
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
    try:
        importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        # Telegram/request extras may not be installed in the lightweight
        # checker; AST parsing above still validates every module.
        print(f"Import skipped for {module_name}: {exc}")
    else:
        print(f"Import passed: {module_name}")

print("MongoDB-only storage and operations smoke tests passed")
