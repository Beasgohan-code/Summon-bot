from storage import connect as db_connect
import sqlite3
import hashlib
import logging
from telegram import (
    InlineQueryResultArticle, 
    InputTextMessageContent, 
    InlineQueryResultCachedPhoto, 
    InlineQueryResultCachedVideo, 
    InlineQueryResultCachedMpeg4Gif, Update
)

from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from database import fetch_all, fetch_one
from config import DB_NAME, RARITY_EMOJI  

logger = logging.getLogger(__name__)

def get_rarity_id(rarity_text):
    rarity_map = {
        "Common": 1, "Rare": 2, "Special Edition": 3, "Legendary": 4, "Mythic Edition": 5,
        "Valentine Edition": 6, "Summer Edition": 7, "Rainy Edition": 8, "Halloween Edition": 9,
        "Christmas Edition": 10, "Winter Edition": 11, "New Year Edition": 12, "Festival Edition": 13,
        "AMV Edition": 14, "Event Edition": 15, "Celestial Edition": 16, "Luxury Edition": 17, "Limited Edition": 18
    }
    for key, value in rarity_map.items():
        if key in rarity_text:
            return value
    return 1


def get_inline_list_result(res_id, char_id, name, anime, rarity, msg_id, count=None, target_user_id=None, u_name=None):
    r_id = get_rarity_id(rarity)
    emoji = RARITY_EMOJI.get(r_id, "⭐")

    title_text = f"{rarity} — {name}"
    desc_text = anime

    if target_user_id and u_name:
        caption_text = (
            f"✨ Check out <a href='tg://user?id={target_user_id}'>{u_name}</a>'s character:\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<blockquote>🆔 <b>Id:</b> <code>{char_id}</code>\n"
            f"👤 <b>Name:</b> {name}" + (f" (x{count})" if count else "") + f"\n"
            f"🌍 <b>Anime:</b> {anime}\n"
            f"🔮 <b>Rarity:</b> {rarity}</blockquote>"
        )
    else:
        caption_text = (
            f"<b>Character Info (Global Search)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<blockquote>🆔 <b>Id:</b> <code>{char_id}</code>\n"
            f"👤 <b>Name:</b> {name}\n"
            f"🌍 <b>Anime:</b> {anime}\n"
            f"🔮 <b>Rarity:</b> {rarity}</blockquote>"
        )

    if not msg_id:
        return InlineQueryResultArticle(
            id=res_id,
            title=title_text,
            description=desc_text,
            input_message_content=InputTextMessageContent(caption_text, parse_mode="HTML")
        )

    file_type = "photo"
    file_id = msg_id

    if "_" in str(msg_id):
        parts = str(msg_id).split("_", 1)
        file_type = parts[0].lower()
        file_id = parts[1]

    try:
        if file_type == "photo" and file_id:
            return InlineQueryResultCachedPhoto(
                id=res_id,
                photo_file_id=file_id,
                title=title_text,
                description=desc_text,
                caption=caption_text,
                parse_mode="HTML"
            )
        elif file_type == "video" and file_id:
            return InlineQueryResultCachedVideo(
                id=res_id,
                video_file_id=file_id,
                title=title_text,
                description=desc_text,
                caption=caption_text,
                parse_mode="HTML"
            )
        elif (file_type == "animation" or file_type == "gif") and file_id:
            return InlineQueryResultCachedMpeg4Gif(
                id=res_id,
                mpeg4_file_id=file_id,
                title=title_text,
                description=desc_text,
                caption=caption_text,
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Error creating cached list result for {name}: {e}")

    return InlineQueryResultArticle(
        id=res_id,
        title=title_text,
        description=desc_text,
        input_message_content=InputTextMessageContent(caption_text, parse_mode="HTML")
    )


# 🚀 MAIN INLINE SEARCH HANDLER (With Robust Datatype Bypass)
async def inline_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        raw_query = update.inline_query.query.strip()
        my_user_id = update.effective_user.id

        conn = db_connect(DB_NAME)
        cursor = conn.cursor()

        inline_results = []

        # 🎯 CASE 1: HAREM / COLLECTION SEARCH (e.g., collection.6265999542)
        if raw_query.lower().startswith("collection"):
            query_parts = raw_query.split(maxsplit=1)
            header_part = query_parts[0]  
            search_keyword = query_parts[1].strip() if len(query_parts) > 1 else ""

            is_amv = False
            raw_id_part = header_part.lower().replace("collection.", "").replace("collection", "").strip(".")
            
            if "amv" in raw_id_part:
                is_amv = True
                raw_id_part = raw_id_part.replace("amv", "").strip(".")

            try:
                target_user_id = int(raw_id_part)
            except ValueError:
                target_user_id = my_user_id

            cursor.execute("SELECT username FROM users WHERE user_id = ?", (target_user_id,))
            u_row = cursor.fetchone()
            u_name = u_row[0] if u_row and u_row[0] else f"User {target_user_id}"

            # 🛠️ FIXED SQL: Using CAST to safely link TEXT character_id and TEXT c.id
            query_str = """
                SELECT c.id, c.name, c.anime, c.rarity, c.msg_id, uc.count
                FROM user_collection uc 
                JOIN characters c ON CAST(uc.character_id AS TEXT) = CAST(c.id AS TEXT)
                WHERE uc.user_id = ?
            """
            params = [target_user_id]

            if is_amv:
                query_str += " AND c.msg_id LIKE 'video_%'"
                
            if search_keyword:
                query_str += " AND (c.name LIKE ? OR c.anime LIKE ?)"
                params.extend([f"%{search_keyword}%", f"%{search_keyword}%"])

            query_str += " ORDER BY c.name ASC LIMIT 25"
            cursor.execute(query_str, tuple(params))
            results = cursor.fetchall()

            if not results:
                err_title = "⚠️ No AMV Characters" if is_amv else "⚠️ No Characters Found"
                inline_results.append(
                    InlineQueryResultArticle(
                        id=hashlib.md5(f"no_res_{target_user_id}_{is_amv}".encode()).hexdigest(),
                        title=err_title,
                        description="Your search returned 0 results.",
                        input_message_content=InputTextMessageContent(
                            f"🎒 <b>{u_name}</b> has no matching characters in their collection.", parse_mode="HTML"
                        )
                    )
                )
            else:
                for char_id, name, anime, rarity, msg_id, count in results:
                    res_hash_id = hashlib.md5(f"coll_{target_user_id}_{char_id}_{count}".encode()).hexdigest()
                    inline_results.append(
                        get_inline_list_result(
                            res_id=res_hash_id, char_id=char_id, name=name, anime=anime, 
                            rarity=rarity, msg_id=msg_id, count=count, target_user_id=target_user_id, u_name=u_name
                        )
                    )

        # 🎯 CASE 2: GLOBAL DATABASE SEARCH (Case-Insensitive using LIKE)
        else:
            if raw_query:
                cursor.execute("""
                    SELECT id, name, anime, rarity, msg_id 
                    FROM characters 
                    WHERE name LIKE ? OR anime LIKE ? 
                    LIMIT 25
                """, (f"%{raw_query}%", f"%{raw_query}%"))
            else:
                cursor.execute("SELECT id, name, anime, rarity, msg_id FROM characters LIMIT 25")

            results = cursor.fetchall()
            for char_id, name, anime, rarity, msg_id in results:
                res_hash_id = hashlib.md5(f"gen_{char_id}".encode()).hexdigest()
                inline_results.append(
                    get_inline_list_result(
                        res_id=res_hash_id, char_id=char_id, name=name, anime=anime, rarity=rarity, msg_id=msg_id
                    )
                )

        conn.close()
        await update.inline_query.answer(inline_results, cache_time=1)
        
    except Exception as outer_err:
        logger.error(f"Critical error in inline query handler: {outer_err}")
        try:
            await update.inline_query.answer([], cache_time=1)
        except Exception:
            pass


# =========================================================================
# 🎒 COLLECTION / HAREM INLINE HANDLER (FIXED FOR ALL MEDIA TYPES)
# =========================================================================
async def collection_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ✅ Required imports are available at module scope.
    from telegram import (
        InlineQueryResultArticle, InputTextMessageContent, 
        InlineQueryResultCachedPhoto, InlineQueryResultCachedVideo, 
        InlineQueryResultCachedMpeg4Gif
    )

    query = update.inline_query.query.strip()
    results = []

    conn = db_connect(DB_NAME)
    cursor = conn.cursor()

    # =========================================================================
    # CASE 1: USER HAREM (Starts with "collection.")
    # =========================================================================
    if query.startswith("collection."):
        raw_parts = query.split(maxsplit=1)
        header_part = raw_parts[0]  
        search_keyword = raw_parts[1].strip() if len(raw_parts) > 1 else ""

        is_amv = False
        raw_id_part = header_part.replace("collection.", "")
        if ".amv" in raw_id_part.lower():
            is_amv = True
            raw_id_part = raw_id_part.lower().replace(".amv", "")

        try:
            target_user_id = int(raw_id_part)
        except ValueError:
            conn.close()
            return

        cursor.execute("SELECT username FROM users WHERE user_id = ?", (target_user_id,))
        user_row = cursor.fetchone()
        user_display_name = user_row[0] if user_row and user_row[0] else f"User {target_user_id}"

        # 🛠️ FIXED SQL: CAST ഉപയോഗിച്ച് ടെക്സ്റ്റ് ഐഡികൾ തമ്മിൽ കൃത്യമായി ലിങ്ക് ചെയ്യുന്നു
        query_str = """
            SELECT c.id, c.name, c.anime, c.rarity, c.msg_id, uc.count 
            FROM user_collection uc
            JOIN characters c ON CAST(uc.character_id AS TEXT) = CAST(c.id AS TEXT)
            WHERE uc.user_id = ?
        """
        params = [target_user_id]

        if is_amv:
            query_str += " AND c.rarity LIKE '%AMV%'"
            
        if search_keyword:
            query_str += " AND (c.name LIKE ? OR c.anime LIKE ?)"
            params.extend([f"%{search_keyword}%", f"%{search_keyword}%"])

        query_str += " ORDER BY c.name ASC LIMIT 50"

        cursor.execute(query_str, tuple(params))
        matching_characters = cursor.fetchall()

        if not matching_characters:
            err_title = "⚠️ No AMV Characters Found" if is_amv else "⚠️ No Characters Found"
            err_desc = "You don't have any AMV Edition characters!" if is_amv else "No characters match your search!"
            results.append(
                InlineQueryResultArticle(
                    id=hashlib.md5(f"no_chars_{query}".encode()).hexdigest(),
                    title=err_title,
                    description=err_desc,
                    input_message_content=InputTextMessageContent(
                        f"🎒 <b>{user_display_name}</b> has no matching characters in their collection.",
                        parse_mode="HTML"
                    )
                )
            )
        else:
            for char_id, char_name, anime, rarity, msg_id, count in matching_characters:
                r_id = get_rarity_id(rarity)
                emoji = RARITY_EMOJI.get(r_id, "⭐")

                share_text = (
                    f"✨ Check out <a href='tg://user?id={target_user_id}'>{user_display_name}</a>'s character:\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"<blockquote>🆔 <b>Id:</b> <code>{char_id}</code>\n"
                    f"👤 <b>Name:</b> {char_name} (x{count})\n"
                    f"🌍 <b>Anime:</b> {anime}\n"
                    f"🔮 <b>Rarity:</b> ⌠{emoji}⌡ {rarity}</blockquote>"
                )

                # 🛠️ MEDIA TYPE DETECTOR (Photo, Video, Animation ഫിക്സ് ചെയ്തത്)
                file_type = "photo"
                file_id = msg_id

                if msg_id and "_" in str(msg_id):
                    parts = str(msg_id).split("_", 1)
                    file_type = parts[0].lower()
                    file_id = parts[1]

                res_id = hashlib.md5(f"user_search_{char_id}_{count}".encode()).hexdigest()

                if not file_id:
                    results.append(
                        InlineQueryResultArticle(
                            id=res_id, title=f"{char_name} (x{count})",
                            description=f"Anime: {anime} | {rarity} (No Image)",
                            input_message_content=InputTextMessageContent(share_text, parse_mode="HTML")
                        )
                    )
                elif file_type == "photo":
                    results.append(InlineQueryResultCachedPhoto(id=res_id, photo_file_id=file_id, title=f"{char_name} (x{count})", description=f"Anime: {anime} | {rarity}", caption=share_text, parse_mode="HTML"))
                elif file_type == "video":
                    results.append(InlineQueryResultCachedVideo(id=res_id, video_file_id=file_id, title=f"{char_name} (x{count})", description=f"Anime: {anime} | {rarity}", caption=share_text, parse_mode="HTML"))
                elif file_type in ["animation", "gif"]:
                    results.append(InlineQueryResultCachedMpeg4Gif(id=res_id, mpeg4_file_id=file_id, title=f"{char_name} (x{count})", description=f"Anime: {anime} | {rarity}", caption=share_text, parse_mode="HTML"))

    # =========================================================================
    # CASE 2: GLOBAL BOT DATABASE SEARCH (Global query search)
    # =========================================================================
    else:
        cursor.execute("""
            SELECT id, name, anime, rarity, msg_id 
            FROM characters 
            WHERE name LIKE ? OR anime LIKE ? 
            ORDER BY name ASC LIMIT 50
        """, (f"%{query}%", f"%{query}%"))
        
        global_characters = cursor.fetchall()
        
        for char_id, char_name, anime, rarity, msg_id in global_characters:
            r_id = get_rarity_id(rarity)
            emoji = RARITY_EMOJI.get(r_id, "⭐")

            global_share_text = (
                f"<b>Character Info</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<blockquote>🆔 <b>Id:</b> <code>{char_id}</code>\n"
                f"👤 <b>Name:</b> {char_name}\n"
                f"🌍 <b>Anime:</b> {anime}\n"
                f"🔮 <b>Rarity:</b> ⌠{emoji}⌡ {rarity}</blockquote>"
            )

            # 🛠️ GLOBAL MEDIA TYPE DETECTOR
            file_type = "photo"
            file_id = msg_id

            if msg_id and "_" in str(msg_id):
                parts = str(msg_id).split("_", 1)
                file_type = parts[0].lower()
                file_id = parts[1]

            res_id = hashlib.md5(f"global_search_{char_id}".encode()).hexdigest()

            if not file_id:
                results.append(
                    InlineQueryResultArticle(
                        id=res_id, title=f"{char_name} (Global Search)",
                        description=f"Anime: {anime} | {rarity} (No Image)",
                        input_message_content=InputTextMessageContent(global_share_text, parse_mode="HTML")
                    )
                )
            elif file_type == "photo":
                results.append(InlineQueryResultCachedPhoto(id=res_id, photo_file_id=file_id, title=f"{char_name} (Global Search)", description=f"Anime: {anime} | {rarity}", caption=global_share_text, parse_mode="HTML"))
            elif file_type == "video":
                results.append(InlineQueryResultCachedVideo(id=res_id, video_file_id=file_id, title=f"{char_name} (Global Search)", description=f"Anime: {anime} | {rarity}", caption=global_share_text, parse_mode="HTML"))
            elif file_type in ["animation", "gif"]:
                results.append(InlineQueryResultCachedMpeg4Gif(id=res_id, mpeg4_file_id=file_id, title=f"{char_name} (Global Search)", description=f"Anime: {anime} | {rarity}", caption=global_share_text, parse_mode="HTML"))

    conn.close()

    if results:
        await update.inline_query.answer(results, cache_time=1)
