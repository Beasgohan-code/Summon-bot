# Summon-bot Architecture Review

**Author:** Manus AI  
**Review date:** 26 August 2026

## Executive assessment

The bot’s main persistence problem is not that SQLite “refreshes” itself after a restart. The problem is that the SQLite file lives on the same filesystem as the bot process. If the host uses an ephemeral filesystem, redeploys from a clean image, or starts the bot from a different working directory, `summon.db` can appear to reset or disappear. The durable fix is to place the primary database on an external service and configure the bot with `DATABASE_URL`.

PostgreSQL is the best primary backend for this repository. The code already uses relational tables, joins, uniqueness constraints, conflict handling, balances, inventory, auctions, and transactions. MongoDB is possible, but it is not a drop-in replacement for this SQL-heavy implementation. Adding MongoDB as a second write target would make balance and inventory consistency harder to guarantee, so this upgrade keeps PostgreSQL as the primary store and leaves MongoDB as an optional future integration rather than creating an unsafe dual-write system.

## Findings and fixes

| Area | Finding | Change implemented | Priority |
|---|---|---|---|
| Fresh database setup | Market, premium, cooldown, inventory, sudo, and auction tables were assumed by handlers but not created by the central initializer. | Added all required tables and legacy-safe migrations to `database.py`. | Critical |
| Group persistence | `ensure_group()` inserted a `title` column that the schema did not create. | Added `groups.title` and a migration for existing databases. | High |
| PostgreSQL support | Runtime modules opened SQLite directly in many files. | Added `storage.py` and routed runtime connections through one SQLite/PostgreSQL selector. | Critical |
| Data migration | No supported path existed for moving existing bot data. | Added `migrate_sqlite_to_postgres.py`; it preserves the SQLite source and copies rows into initialized PostgreSQL tables. | Critical |
| Restarts | A blind fixed-interval restart would create downtime and can interrupt transactions. | Added `supervisor.py` with crash recovery by default and explicit `AUTO_RESTART_MINUTES=10` or `15` support when periodic recycling is truly required. | High |
| Reboot recovery | No service template existed. | Added `summon-bot.service.example` for systemd startup and crash recovery. | High |
| Secrets | Owner ID and owner-panel password were hardcoded in source. | Moved them to environment configuration and added fail-fast startup validation. | Critical |
| Telegram UI | Unsupported `style=` arguments were passed to inline buttons. | Removed unsupported arguments across menus, auctions, hstats, owner panel, and user screens. | High |
| Handler behavior | The daily command and profile handler were registered more than once. | Kept one canonical daily handler and one profile registration. | Medium |
| Asset loading | Profile fonts depended on the current working directory. | Changed font loading to repository-relative paths and validated downloads. | Medium |
| Diagnostics | Operators had no simple latency check. | Added `/ping`, reporting Telegram round-trip latency and uptime. | Medium |

## Database options

| Approach | Tradeoffs | Cost | Setup complexity |
|---|---|---:|---|
| **Managed PostgreSQL, recommended** | Fits the current SQL data model, supports durable storage, backups, constraints, joins, and safe transactions. A free tier may pause when inactive, so production uptime may require a paid tier. | Supabase currently lists Free at $0/month with 500 MB database size and automatic pausing after one week of inactivity. Its Pro plan starts at $25/month, includes 8 GB disk and daily backups for 7 days, and includes $10/month in compute credits; its Micro compute size is listed as 1 GB RAM and 2-core ARM CPU. [1] | Moderate |
| **Managed MongoDB** | Technically possible, but the current code would need a new document repository, rewritten joins and conflict logic, new indexes, transaction review, and a separate migration strategy. Do not dual-write balances and inventory without a consistency design. | Atlas officially provides a perpetual free cluster; official search results identify a 512 MB storage limit for the free tier. Atlas Flex is identified in official documentation as a 5 GB maximum with a monthly cap, but exact paid pricing depends on region and configuration. [2] [3] | High |
| **1 GB cloud server with PostgreSQL installed** | Gives full control and can host both the bot and PostgreSQL, but you must maintain security, backups, updates, monitoring, and disk usage yourself. | The Manus Basic cloud-computer tier is listed at $10/month with 1 GB memory, 2 vCPUs, 35 GB included storage, and 200 GB outbound traffic. [4] | Moderate to high |

The phrase **“1 GB” needs clarification**: 1 GB of RAM is different from 1 GB of database storage. For this bot, 1 GB RAM is usually enough for a small Telegram process and a remote database connection, but it does not make the local SQLite file durable. A managed PostgreSQL service is generally safer than installing both the bot and database on the same small server.

## MongoDB decision

MongoDB can be added later for document-shaped features such as analytics events, flexible user activity documents, or a search index. It should not replace PostgreSQL in this version without a deliberate repository rewrite. The repository now documents `MONGO_URI` and `MONGO_DB_NAME` as reserved configuration values, but they are intentionally not used as a second primary store. This avoids silently creating two sources of truth.

## Restart policy

The recommended policy is **restart on crash, not restart every 10 or 15 minutes**. Telegram polling already maintains a long-lived connection, and scheduled killing introduces unnecessary downtime. The new supervisor supports both policies:

```dotenv
# Recommended
AUTO_RESTART_MINUTES=0

# Only when periodic recycling is justified
AUTO_RESTART_MINUTES=10
# or
AUTO_RESTART_MINUTES=15
```

With `AUTO_RESTART_MINUTES=0`, an unexpected child-process exit is restarted after a short delay. With `10` or `15`, the child is gracefully terminated and relaunched at that interval. The systemd template also starts the supervisor after machine reboots.

## Migration procedure

First create a full copy of the existing SQLite file. Then create a PostgreSQL database with your chosen provider and place its connection string in `DATABASE_URL`. Run the migration from the bot directory:

```bash
cp summon.db summon.db.backup
export DATABASE_URL='postgresql://USER:PASSWORD@HOST:5432/summon_bot'
python3 migrate_sqlite_to_postgres.py --source summon.db
python3 smoke_test.py
```

The migration utility is intentionally non-destructive: it does not delete or modify the SQLite source. Because no PostgreSQL connection URL was supplied in this review session, the live data copy was not executed. The code path, schema initialization, SQL translation rules, command-module imports, and migration CLI were validated locally.

After verifying the copied row counts, run the bot with the same `DATABASE_URL`. Keep the SQLite backup until the PostgreSQL deployment has been observed in production.

## Validation completed

The following checks passed:

```text
python3 -m compileall -q .
python3 smoke_test.py
python3 migrate_sqlite_to_postgres.py --help
git diff --check
```

The smoke suite parses all Python modules, initializes a fresh database, verifies required tables, checks key SQL translations, imports the major bot modules, and does not start Telegram polling.

## Recommended next step

Use **managed PostgreSQL as the single source of truth**, set `AUTO_RESTART_MINUTES=0`, deploy the bot under the supplied systemd template or an equivalent service manager, and only consider MongoDB after a concrete document-oriented feature justifies the additional repository and migration work.

## References

[1]: https://supabase.com/pricing "Supabase Pricing & Fees"
[2]: https://www.mongodb.com/docs/atlas/reference/free-shared-limitations/ "MongoDB Atlas Free Cluster Limits"
[3]: https://www.mongodb.com/docs/atlas/billing/atlas-flex-costs/ "MongoDB Atlas Flex Costs"
[4]: https://manus.im/app#settings/my-computer/create "Manus Cloud Computer settings"
