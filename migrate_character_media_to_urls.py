"""Migrate Summon character media to verified Catbox/ImgBB image URLs.

This script never invents a URL for a Telegram file ID. It can copy only already
valid approved URLs from legacy columns. Review its report, upload unresolved
media to Catbox or ImgBB, then update those rows with /update before using
--finalize to remove legacy media columns.
"""
from __future__ import annotations

import argparse
import os
from collections.abc import Iterable

import psycopg2

from media_urls import is_allowed_character_image_url


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--apply", action="store_true", help="Write validated URLs to image_url")
    parser.add_argument(
        "--finalize",
        action="store_true",
        help="Drop msg_id/img_url/img_url2 only when every character has an approved image_url",
    )
    return parser.parse_args()


def first_approved_url(values: Iterable[object]) -> str | None:
    for value in values:
        if is_allowed_character_image_url(value):
            return str(value).strip()
    return None


def main() -> None:
    args = parse_args()
    if not args.database_url or not args.database_url.startswith(("postgres://", "postgresql://")):
        raise SystemExit("Provide a PostgreSQL DATABASE_URL or --database-url.")
    if args.finalize and not args.apply:
        raise SystemExit("Use --apply before --finalize.")

    conn = psycopg2.connect(args.database_url, sslmode="require")
    try:
        with conn.cursor() as cursor:
            cursor.execute("ALTER TABLE characters ADD COLUMN IF NOT EXISTS image_url TEXT")
            cursor.execute(
                "SELECT id, image_url, img_url, img_url2, msg_id FROM characters ORDER BY id"
            )
            rows = cursor.fetchall()

            migrated = 0
            unresolved: list[str] = []
            for char_id, image_url, img_url, img_url2, legacy_msg_id in rows:
                approved = first_approved_url((image_url, img_url, img_url2, legacy_msg_id))
                if approved is None:
                    unresolved.append(str(char_id))
                    continue
                if args.apply and image_url != approved:
                    cursor.execute("UPDATE characters SET image_url = %s WHERE id = %s", (approved, char_id))
                    migrated += 1

            if args.apply:
                conn.commit()

            print(f"Characters scanned: {len(rows)}")
            print(f"Approved image URLs written: {migrated}")
            print(f"Unresolved character IDs: {', '.join(unresolved) or 'none'}")

            if args.finalize:
                if unresolved:
                    raise SystemExit("Cannot finalize: every character needs an approved Catbox/ImgBB image URL.")
                cursor.execute(
                    "SELECT COUNT(*) FROM characters WHERE image_url IS NULL OR image_url = ''"
                )
                if cursor.fetchone()[0]:
                    raise SystemExit("Cannot finalize: image_url still has empty values.")
                cursor.execute("ALTER TABLE characters ALTER COLUMN image_url SET NOT NULL")
                cursor.execute(
                    """DO $$
                    BEGIN
                      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'characters_image_url_allowlist') THEN
                        ALTER TABLE characters ADD CONSTRAINT characters_image_url_allowlist
                        CHECK (image_url ~ '^https://(files\\.catbox\\.moe|i\\.ibb\\.co)/.+');
                      END IF;
                    END $$"""
                )
                cursor.execute("ALTER TABLE characters DROP COLUMN IF EXISTS msg_id")
                cursor.execute("ALTER TABLE characters DROP COLUMN IF EXISTS img_url")
                cursor.execute("ALTER TABLE characters DROP COLUMN IF EXISTS img_url2")
                conn.commit()
                print("Legacy media columns removed. Character media is now URL-only.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
