# Summon-bot

Summon-bot is a Telegram character-collection bot with collections, economy,
market, auctions, moderation, streaks, achievements, inline search, games,
and a same-origin Telegram Mini App.

## Runtime architecture

- **python-telegram-bot only** — webhook runtime, no polling.
- **MongoDB only** — all users, balances, collections, characters, inventory,
  auctions, market state, moderation, logs, and Mini App rewards use
  `MONGO_URI` and `MONGO_DB_NAME`.
- No SQLite, PostgreSQL runtime connection, local database file, token-bearing
  media URL, or silent storage fallback exists.
- The Mongo repository creates unique identity/economy indexes at startup and
  uses atomic balance, collection, and Mini App reward updates.
- Telegram WebApp init data is validated server-side. Mini App winnings are
  credited to the same MongoDB user balance used by bot commands.
- `TELEGRAM_GUEST_MODE=true` enables a same-origin, read-only public preview
  at `/app/`. Guests can see aggregate catalogue metadata and the public coin
  leaderboard only. Balances, private collections, account identity, reward
  history, and all game/reward endpoints remain behind Telegram WebApp
  init-data validation. Set it to `false` to disable the public preview.

Use MongoDB Atlas or another durable replica-set deployment with backups and
point-in-time recovery enabled. “Lossless” operation still requires the
operator to configure backups and test restores.

## Configuration

Copy `.env.example` to `.env`. Required production values include:

```text
BOT_TOKEN=...
OWNER_ID=...
OWNER_PANEL_PASSWORD=...
MONGO_URI=mongodb+srv://...
MONGO_DB_NAME=summon_bot
WEBHOOK_URL=https://summon-bot-wngc.onrender.com/telegram/webhook
WEBHOOK_SECRET=...  # recommended; an ephemeral secret is generated if omitted
LOGGER_ID=...
```

The supplied Render URL remains the default keep-alive target. Override it with
`KEEPALIVE_URL` when deploying elsewhere. The HTTP server binds to
`0.0.0.0:$PORT` and serves health, webhook, and Mini App routes on the same
origin.

## Migrating existing data

`migrate_postgres_to_mongo.py` is an explicit, source-preserving migration
utility for a legacy PostgreSQL deployment. It is not imported or run by the
bot. Install the optional migration dependency from
`requirements-migration.txt`, then run a dry run first:

```bash
export SOURCE_DATABASE_URL='postgresql://...'
export MONGO_URI='mongodb+srv://...'
export MONGO_DB_NAME='summon_bot'
python migrate_postgres_to_mongo.py
python migrate_postgres_to_mongo.py --apply
```

The dry run reports source row counts and `--apply` upserts stable document IDs
without modifying the source. Review counts and backups before cutover. After
migration, redeploy this MongoDB-only revision; an older PostgreSQL instance
may still expose the obsolete `/premium` `granted_at` schema error.

## Admin character upload

The owner and delegated sudo admins can add a character from Telegram media:

```text
/upload Yelan Genshin-impact 5   # reply to a photo, video, GIF, or media document
/add Yelan Genshin-impact 5       # same media flow
```

If metadata is omitted, `/upload` or `/add` starts a guided wizard. Send the
media first or reply to the wizard prompts with the name, anime, and rarity ID.
`/cancelupload` and `/canceladd` cancel an active wizard. `/addchar` and the
four-argument `/add` form remain available for approved external HTTPS image
URLs.

Telegram media references are stored in MongoDB. No upload directory or bot
token URL is created.

## Reliability

`KeepAlive` follows the Videl-style periodic health request behavior.
`Watchdog` pings MongoDB and updates `/readyz`; it does not hide database
failures. Telegram warnings/errors are batched to `LOGGER_ID`. Webhook POSTs
require `X-Telegram-Bot-Api-Secret-Token` matching the process secret. Set
`WEBHOOK_SECRET` for a stable secret across restarts; when it is omitted, the
process generates a private ephemeral secret before registering the webhook.

## Validation

```bash
python -m compileall -q .
python smoke_test.py
python -m unittest discover -q
```

The bot intentionally fails fast when `BOT_TOKEN`, `OWNER_ID`,
`OWNER_PANEL_PASSWORD`, `MONGO_URI`, `MONGO_DB_NAME`, or `WEBHOOK_URL` is
missing or invalid. A supplied `WEBHOOK_SECRET` must be 1–256 characters;
when it is omitted, a process-local secret is generated so Render can still
bind the health/webhook port safely.
