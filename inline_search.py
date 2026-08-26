"""URL-only inline character search for Summon-bot."""
from __future__ import annotations

import hashlib
import logging

from telegram import InlineQueryResultArticle, InlineQueryResultPhoto, InputTextMessageContent, Update
from telegram.ext import ContextTypes

from config import DB_NAME, RARITY_EMOJI
from media_urls import is_allowed_character_image_url
from storage import connect as db_connect


logger = logging.getLogger(__name__)


def rarity_emoji(rarity: str) -> str:
    labels = {"Common": 1, "Rare": 2, "Special": 3, "Legendary": 4, "Mythic": 5, "Valentine": 6, "Summer": 7, "Rainy": 8, "Halloween": 9, "Christmas": 10, "Winter": 11, "New Year": 12, "Festival": 13, "AMV": 14, "Event": 15, "Celestial": 16, "Luxury": 17, "Limited": 18}
    return next((RARITY_EMOJI[value] for label, value in labels.items() if label.lower() in rarity.lower()), "⭐")


def character_result(char_id: str, name: str, anime: str, rarity: str, image_url: str, count: int | None = None, owner_id: int | None = None) -> InlineQueryResultArticle | InlineQueryResultPhoto:
    caption = (
        f"<b>{name}</b>{f' ×{count}' if count else ''}\n"
        f"<blockquote>🆔 <code>{char_id}</code>\n🎌 {anime}\n{rarity_emoji(rarity)} {rarity}</blockquote>"
    )
    result_id = hashlib.sha256(f"{owner_id or 'catalog'}:{char_id}:{count or 0}".encode()).hexdigest()[:32]
    if is_allowed_character_image_url(image_url):
        return InlineQueryResultPhoto(
            id=result_id,
            photo_url=image_url,
            thumbnail_url=image_url,
            title=f"{rarity} — {name}",
            description=anime,
            caption=caption,
            parse_mode="HTML",
        )
    return InlineQueryResultArticle(
        id=result_id,
        title=f"{rarity} — {name}",
        description=anime,
        input_message_content=InputTextMessageContent(caption, parse_mode="HTML"),
    )


async def inline_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = (update.inline_query.query if update.inline_query else "").strip()
    conn = db_connect(DB_NAME)
    try:
        cursor = conn.cursor()
        if query.lower().startswith("collection."):
            header, *rest = query.split(maxsplit=1)
            try:
                owner_id = int(header.split(".", 1)[1])
            except (IndexError, ValueError):
                owner_id = update.effective_user.id
            keyword = rest[0] if rest else ""
            cursor.execute(
                """SELECT c.id, c.name, c.anime, c.rarity, c.image_url, uc.count
                   FROM user_collection uc JOIN characters c ON c.id = uc.character_id
                   WHERE uc.user_id = ? AND (c.name ILIKE ? OR c.anime ILIKE ?)
                   ORDER BY c.name LIMIT 25""",
                (owner_id, f"%{keyword}%", f"%{keyword}%"),
            )
            results = [character_result(*row, owner_id=owner_id) for row in cursor.fetchall()]
        else:
            cursor.execute(
                """SELECT id, name, anime, rarity, image_url
                   FROM characters WHERE name ILIKE ? OR anime ILIKE ?
                   ORDER BY name LIMIT 25""",
                (f"%{query}%", f"%{query}%"),
            )
            results = [character_result(*row) for row in cursor.fetchall()]
    except Exception as exc:
        logger.exception("Inline character search failed: %s", exc)
        results = []
    finally:
        conn.close()
    await update.inline_query.answer(results, cache_time=2)


collection_inline = inline_search
