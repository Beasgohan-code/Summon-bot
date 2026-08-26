# Summon-bot Error Audit

**Audit revision:** `ea2e182`  
**Branch:** `main`  
**Status:** Pushed to `origin/main`

## Result

No remaining undefined-name blockers were found by the final static-analysis pass. Compilation, fresh-database initialization, module imports, schema validation, SQL translation checks, and repository formatting all passed.

## Confirmed blockers fixed in this audit

| File or area | Problem | Resolution |
|---|---|---|
| `catch_all.py` | Automatic spawn could call an undefined `send_character_media`. | Imported the shared media sender from `commands_user.py`. |
| `commands_admin.py` | Weighted spawn called undefined `get_rarity`. | Added weighted rarity selection from `rarity_chances`. |
| `commands_admin.py` | Sudo management called undefined `is_owner`. | Restored the configured-owner helper. |
| `commands_admin.py` | Redeem-code generation called undefined `get_character_media`. | Added lookup through the character record. |
| `commands_user.py` | Leaderboard referenced undefined `TOP_IMAGE`. | Imported `TOP_IMAGE` from configuration. |
| `main.py` | Dead code referenced undefined `found` after the main loop. | Removed the stray statement. |
| `auto_spawn.py` | Imported media sender was shadowed by a dynamic assignment. | Renamed the dynamic variable and preserved fallback behavior. |
| `database.py` | Duplicate `get_top_anime` definitions created an unpredictable helper contract. | Kept one implementation. |

## Validation commands that passed

```text
python3 -m compileall -q .
python3 smoke_test.py
python3 check_schema.py
python3 migrate_sqlite_to_postgres.py --help
pyflakes ./*.py ./plugins/*.py
 git diff --check
```

The filtered Pyflakes blocker scan returned no remaining `undefined name`, import-redefinition, or unable-to-import findings. There are still some non-blocking cleanup warnings such as unused legacy imports and cosmetic f-strings; they do not prevent startup or normal command execution.

## Not tested live

A live Telegram polling session was not started because that would require the production `BOT_TOKEN`, a valid positive `OWNER_ID`, and a configured owner-panel password. A real PostgreSQL migration was not executed because no `DATABASE_URL` or PostgreSQL server was supplied. The migration script and adapter were syntax-checked and tested in SQLite mode, but the final production cutover still needs a backup, a real PostgreSQL endpoint, and a controlled migration run.

MongoDB remains optional and inactive. The current bot is SQL- and join-oriented, so PostgreSQL is still the safer primary backend. Adding MongoDB as a second primary write target would require a separate repository implementation and consistency design.
