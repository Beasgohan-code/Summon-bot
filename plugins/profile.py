from storage import connect as db_connect
import io
import os  # 👈 ഫോണ്ട് ചെക്ക് ചെയ്യാൻ പുതിയതായി ചേർത്തു
from pathlib import Path
import math
import random
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ParseMode
from config import DB_NAME

DB = DB_NAME
BASE_DIR = Path(__file__).resolve().parent.parent

# ==================== AUTOMATIC FONT DOWNLOADER ====================
def download_fonts():
    """Termux-ൽ ഡിസൈൻ ബ്രേക്ക് ആകാതിരിക്കാൻ ഫോണ്ടുകൾ ഇല്ലെങ്കിൽ തനിയെ ഡൗൺലോഡ് ചെയ്യും"""
    fonts = {
        "Poppins-Bold.ttf": "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Bold.ttf",
        "Poppins-Medium.ttf": "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Medium.ttf",
        "Poppins-Regular.ttf": "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Regular.ttf"
    }
    for name, url in fonts.items():
        target = BASE_DIR / name
        if not target.exists():
            try:
                print(f"📥 Downloading {name}...")
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                target.write_bytes(response.content)
            except Exception as exc:
                print(f"❌ Failed to download {name}: {exc}")

# ബോട്ട് റൺ ചെയ്യുമ്പോൾ തന്നെ ഫോണ്ടുകൾ ഉണ്ടെന്ന് ഉറപ്പാക്കുന്നു
download_fonts()

# ==================== MODERN VIBRANT PALETTE ====================
PURPLE       = (167, 139, 250, 255)
PURPLE_DEEP  = (124, 58, 237, 255)
PINK         = (244, 114, 182, 255)
PINK_DEEP    = (219, 39, 119, 255)
BLUE         = (96, 165, 250, 255)
CYAN         = (34, 211, 238, 255)
GOLD         = (250, 204, 21, 255)
GREEN        = (74, 222, 128, 255)
ORANGE       = (251, 146, 60, 255)
WHITE        = (255, 255, 255, 255)
DIM          = (180, 170, 200, 255)
MUTE         = (130, 120, 155, 255)
CARD_BG      = (22, 16, 32, 240)
BG_DARK      = (8, 6, 12, 255)

# Rarity → color
RARITY_COLORS = {
    "N":         (160, 160, 160, 255),  # Normal — gray
    "R":         (96, 165, 250, 255),   # Rare — blue
    "SR":        (167, 139, 250, 255),  # Super Rare — purple
    "SSR":       (244, 114, 182, 255),  # SSR — pink
    "UR":        (250, 204, 21, 255),   # Ultra Rare — gold
    "LR":        (251, 146, 60, 255),   # Legendary — orange
    "MYTHIC":    (239, 68, 68, 255),    # Mythic — red
    "LIMITED":   (34, 211, 238, 255),   # Limited — cyan
    "EVENT":     (34, 211, 238, 255),   # Event — cyan
    "EXCLUSIVE": (217, 70, 239, 255),   # Exclusive — magenta
}

# ==================== HELPERS ====================
def progress_bar(pct, length=10):
    pct = max(0, min(100, pct))
    filled = int(length * pct / 100)
    return "▰" * filled + "▱" * (length - filled)

def get_conn():
    return db_connect(DB)

def lerp(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(4))

def load_font(candidates, size):
    for name in candidates:
        candidates_to_try = [str(BASE_DIR / name), name]
        try:
            return ImageFont.truetype(candidates_to_try[0], size)
        except IOError:
            try:
                return ImageFont.truetype(candidates_to_try[1], size)
            except IOError:
                continue
    return ImageFont.load_default()

def smart_truncate(draw, text, font, max_w, suffix="…"):
    if draw.textlength(text, font=font) <= max_w:
        return text
    while len(text) > 1 and draw.textlength(text + suffix, font=font) > max_w:
        text = text[:-1]
    return text + suffix

def draw_glow_rect(img, xy, color, radius=18, glow_size=8, border_width=3):
    """Glowing rounded border around a box."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for i in range(glow_size, 0, -1):
        alpha = int(90 * (1 - i / glow_size))
        expand = (glow_size - i) * 2
        od.rounded_rectangle(
            [xy[0] - expand, xy[1] - expand, xy[2] + expand, xy[3] + expand],
            radius=radius + expand,
            outline=(*color[:3], alpha),
            width=2,
        )
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=3))
    img.alpha_composite(overlay)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(xy, radius=radius, outline=color, width=border_width)

def rarity_color(rarity):
    if not rarity:
        return (187, 134, 252, 255) # default purple glow if no rarity
    return RARITY_COLORS.get(rarity.upper().strip(), (187, 134, 252, 255))

def draw_rarity_ring(base, char_x1, char_y1, char_x2, char_y2, color, pad=6, glow_size=10):
    """Outer soft glow + sharp inner ring around a rounded portrait box."""
    ring_glow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    rgd = ImageDraw.Draw(ring_glow)
    for i in range(glow_size, 0, -1):
        alpha = int(85 * (1 - i / glow_size))
        e = (glow_size - i) * 2
        rgd.rounded_rectangle(
            [char_x1 - pad - e, char_y1 - pad - e,
             char_x2 + pad + e, char_y2 + pad + e],
            radius=32 + pad + e,
            outline=(*color[:3], alpha),
            width=3,
        )
    ring_glow = ring_glow.filter(ImageFilter.GaussianBlur(radius=4))
    base.alpha_composite(ring_glow)
    draw = ImageDraw.Draw(base)
    draw.rounded_rectangle(
        [char_x1 - pad, char_y1 - pad,
         char_x2 + pad, char_y2 + pad],
        radius=32 + pad,
        outline=color,
        width=3,
    )
    # faint inner highlight
    draw.rounded_rectangle(
        [char_x1 + 5, char_y1 + 5, char_x2 - 5, char_y2 - 5],
        radius=27, outline=(*WHITE[:3], 40), width=1,
    )

def draw_rarity_badge(draw, char_x1, char_y1, rarity, font_badge):
    """Pill badge in the corner of the portrait + gold star for high rarities."""
    if not rarity:
        return
    color = rarity_color(rarity)
    badge_text = rarity.upper()
    tw = draw.textlength(badge_text, font=font_badge)
    pad_x, pad_y = 12, 8
    bx1 = char_x1 + 12
    by1 = char_y1 + 12
    bx2 = bx1 + tw + pad_x * 2
    by2 = by1 + font_badge.size + pad_y * 2
    draw.rounded_rectangle([bx1, by1, bx2, by2], radius=14, fill=color)
    draw.text((bx1 + pad_x, by1 + pad_y - 1), badge_text, fill=(15, 10, 25, 255), font=font_badge)

    # gold star for SSR and above
    if rarity.upper() in ("SSR", "UR", "LR", "MYTHIC", "LIMITED", "EXCLUSIVE"):
        sx = bx2 + 6
        sy = by1 + 4
        draw.polygon([
            (sx + 6, sy),
            (sx + 7, sy + 5),
            (sx + 12, sy + 5),
            (sx + 8, sy + 8),
            (sx + 10, sy + 14),
            (sx + 6, sy + 10),
            (sx + 2, sy + 14),
            (sx + 4, sy + 8),
            (sx, sy + 5),
            (sx + 5, sy + 5),
        ], fill=GOLD)

# ==================== MAIN COMMAND ====================
async def profile_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    target_id = user_id
    target_first = user.first_name or "User"
    target_username = user.username

    if context.args:
        arg = context.args[0].lstrip("@")
        if arg.isdigit():
            target_id = int(arg)
        else:
            conn = get_conn()
            row = conn.execute(
                "SELECT user_id, first_name, username FROM users WHERE username = ?",
                (arg,),
            ).fetchone()
            conn.close()
            if row:
                target_id, target_first, target_username = row

    conn = get_conn()
    cur = conn.cursor()

    u = cur.execute("SELECT * FROM users WHERE user_id = ?", (target_id,)).fetchone()
    if not u:
        await update.message.reply_text("❌ User not found.")
        conn.close()
        return

    balance = u["balance"] or 0
    first_name = u["first_name"] or target_first
    username = u["username"] or target_username
    last_daily = u["last_daily"]

    # Collection stats
    chars = cur.execute(
        "SELECT COUNT(DISTINCT character_id) as cnt, SUM(count) as total "
        "FROM user_collection WHERE user_id = ?",
        (target_id,),
    ).fetchone()
    unique_chars = chars["cnt"] or 0
    total_summons = chars["total"] or 0
    total_game = cur.execute("SELECT COUNT(*) FROM characters").fetchone()[0] or 1
    harem_pct = (unique_chars / total_game * 100) if total_game else 0

    # Rank
    rank_row = cur.execute(
        "SELECT COUNT(*) + 1 FROM ("
        " SELECT user_id, COUNT(DISTINCT character_id) as cnt "
        " FROM user_collection GROUP BY user_id "
        "HAVING COUNT(DISTINCT character_id) > ?)",
        (unique_chars,),
    ).fetchone()
    rank = rank_row[0] if rank_row else 1

    # Streak
    streak = 0
    s = cur.execute("SELECT streak_count FROM user_streaks WHERE user_id = ?", (target_id,)).fetchone()
    if s:
        streak = s["streak_count"] or 0

    # Purchases
    purchases = cur.execute(
        "SELECT COUNT(*) FROM market_transactions WHERE user_id = ?", (target_id,)
    ).fetchone()[0] or 0

    # Achievements
    unlocked_ach = 0
    try:
        unlocked_ach = cur.execute(
            "SELECT COUNT(*) FROM user_achievements WHERE user_id = ?", (target_id,)
        ).fetchone()[0] or 0
    except Exception:
        pass

    # Inventory
    inv_count = 0
    try:
        inv_count = cur.execute(
            "SELECT SUM(count) FROM user_inventory WHERE user_id = ?", (target_id,)
        ).fetchone()[0] or 0
    except Exception:
        pass

    # Favorite character
    fav_char = None
    fav_rarity = None
    fav_name = None
    try:
        fav_id = u["favorite"]
        if fav_id:
            fav_char = cur.execute("SELECT * FROM characters WHERE id = ?", (fav_id,)).fetchone()
            if fav_char and len(fav_char) > 3:
                fav_rarity = (fav_char[3] or "").upper().strip() or None
            if fav_char and len(fav_char) > 1:
                fav_name = (fav_char[1] or "").strip() or None
    except Exception:
        pass

    conn.close()

    ring_col = rarity_color(fav_rarity)

    # ==================== BUILD CARD ====================
    W, H = 1000, 540
    base = Image.new("RGBA", (W, H), BG_DARK)

    # Background gradient
    bg_overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bg_overlay)
    for y in range(H):
        t = y / H
        c = lerp((20, 12, 35, 255), (8, 6, 18, 255), t)
        bd.line([(0, y), (W, y)], fill=c)
    base = Image.alpha_composite(base, bg_overlay)

    # Load favorite character image (or fallback to Telegram avatar)
    fav_img_loaded = None
    if fav_char:
        for url in (
            fav_char[6] if len(fav_char) > 6 else None,
            fav_char[7] if len(fav_char) > 7 else None,
        ):
            if url and isinstance(url, str) and url.startswith(("http://", "https://")):
                try:
                    r = requests.get(url, timeout=5)
                    fav_img_loaded = Image.open(io.BytesIO(r.content)).convert("RGBA")
                    break
                except Exception:
                    continue

    if not fav_img_loaded:
        try:
            user_photos = await user.get_profile_photos(limit=1)
            if user_photos.total_count > 0:
                file_id = user_photos.photos[0][-1].file_id
                tg_file = await context.bot.get_file(file_id)
                file_bytes = await tg_file.download_as_bytearray()
                fav_img_loaded = Image.open(io.BytesIO(file_bytes)).convert("RGBA")
        except Exception:
            pass

    # Blurred image background
    if fav_img_loaded:
        try:
            blurred = fav_img_loaded.copy().resize((W, H), Image.LANCZOS)
            blurred = blurred.filter(ImageFilter.GaussianBlur(radius=40))
            base = Image.alpha_composite(blurred, Image.new("RGBA", (W, H), (10, 7, 18, 220)))
        except Exception:
            pass

    draw = ImageDraw.Draw(base)

    # ── Fonts ──
    font_title     = load_font(["Poppins-Bold.ttf", "Inter-Bold.ttf", "DejaVuSans-Bold.ttf"], 40)
    font_sub       = load_font(["Poppins-Regular.ttf", "Inter-Regular.ttf", "DejaVuSans.ttf"], 17)
    font_box_title = load_font(["Poppins-Medium.ttf", "Inter-Medium.ttf", "DejaVuSans.ttf"], 17)
    font_box_val   = load_font(["Poppins-Bold.ttf", "Inter-Bold.ttf", "DejaVuSans-Bold.ttf"], 32)
    font_small     = load_font(["Poppins-Regular.ttf", "Inter-Regular.ttf", "DejaVuSans.ttf"], 14)
    font_badge     = load_font(["Poppins-Bold.ttf", "Inter-Bold.ttf", "DejaVuSans-Bold.ttf"], 13)

    # ── OUTER GRADIENT FRAME ──
    frame_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fd = ImageDraw.Draw(frame_layer)
    thickness = 4
    for x in range(W):
        t = x / W
        fd.line([(x, 0), (x, thickness)], fill=lerp(PURPLE_DEEP, PINK_DEEP, t))
        fd.line([(x, H - thickness), (x, H)], fill=lerp(BLUE, CYAN, t))
    for y in range(H):
        t = y / H
        fd.line([(0, y), (thickness, y)], fill=lerp(PURPLE_DEEP, BLUE, t))
        fd.line([(W - thickness, y), (W, y)], fill=lerp(PINK_DEEP, CYAN, t))
    base = Image.alpha_composite(base, frame_layer)
    draw = ImageDraw.Draw(base)

    # Corner accent triangles
    cs = 18
    draw.polygon([(0, 0), (cs, 0), (0, cs)], fill=GOLD)
    draw.polygon([(W, 0), (W - cs, 0), (W, cs)], fill=PINK)
    draw.polygon([(0, H), (cs, H), (0, H - cs)], fill=CYAN)
    draw.polygon([(W, H), (W - cs, H), (W, H - cs)], fill=PURPLE)

    # ==================== CHARACTER IMAGE BOX (left) ====================
    char_x1, char_y1, char_x2, char_y2 = 28, 28, 428, 488
    if fav_img_loaded:
        try:
            ci = fav_img_loaded.copy()
            sw, sh = ci.size
            crop_size = min(sw, sh)
            left = (sw - crop_size) // 2
            top = (sh - crop_size) // 2
            ci = ci.crop((left, top, left + crop_size, top + crop_size))
            ci = ci.resize((400, 460), Image.LANCZOS)
            mask = Image.new("L", (400, 460), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, 400, 460], radius=32, fill=255)
            ci.putalpha(mask)
            base.paste(ci, (char_x1, char_y1), ci)
        except Exception:
            draw.rounded_rectangle([char_x1, char_y1, char_x2, char_y2], radius=32, fill=CARD_BG)
    else:
        draw.rounded_rectangle([char_x1, char_y1, char_x2, char_y2], radius=32, fill=CARD_BG)

    # ── RARITY RING ──
    draw_rarity_ring(base, char_x1, char_y1, char_x2, char_y2, ring_col, pad=6, glow_size=10)

    # ── RARITY BADGE in corner of portrait ──
    draw_rarity_badge(draw, char_x1, char_y1, fav_rarity, font_badge)

    # ==================== HEADER (Name + UID + Badge) ====================
    display_name = f"@{username}" if username else first_name
    name_text = smart_truncate(draw, display_name, font_title, 470)
    draw.text((460, 34), name_text, fill=WHITE, font=font_title)
    draw.text((460, 84), f"UID: {target_id}", fill=DIM, font=font_sub)

    # PROFILE pill badge
    draw.rounded_rectangle([460, 114, 555, 138], radius=12, fill=PURPLE_DEEP)
    draw.text((472, 118), "✦ PROFILE", fill=WHITE, font=font_small)

    # Fav character name under the badge
    if fav_name:
        fav_text = smart_truncate(draw, f"★ Favorite: {fav_name}", font_small, 470)
        draw.text((460, 146), fav_text, fill=ring_col, font=font_small)

    # ==================== STAT CARDS ====================
    # 1. Rank
    rx1, ry1, rx2, ry2 = 460, 180, 700, 295
    draw.rounded_rectangle([rx1, ry1, rx2, ry2], radius=20, fill=CARD_BG)
    draw_glow_rect(base, [rx1, ry1, rx2, ry2], GOLD, radius=20, glow_size=6, border_width=2)
    draw.text((rx1 + 22, ry1 + 16), "🏆 RANKING", fill=GOLD, font=font_box_title)
    draw.text((rx1 + 22, ry1 + 46), f"#{rank}", fill=WHITE, font=font_box_val)
    draw.text((rx1 + 22, ry2 - 26), "Global Leaderboard", fill=MUTE, font=font_small)

    # 2. Aestrite
    bx1, by1, bx2, by2 = 720, 180, 960, 295
    draw.rounded_rectangle([bx1, by1, bx2, by2], radius=20, fill=CARD_BG)
    draw_glow_rect(base, [bx1, by1, bx2, by2], PURPLE, radius=20, glow_size=6, border_width=2)
    draw.text((bx1 + 22, by1 + 16), "💎 Balance", fill=PURPLE, font=font_box_title)
    draw.text((bx1 + 22, by1 + 46), f"{balance:,}", fill=WHITE, font=font_box_val)
    draw.text((bx1 + 22, by2 - 26), "Currency Balance", fill=MUTE, font=font_small)

    # 3. Collection
    cx1, cy1, cx2, cy2 = 460, 315, 960, 480
    draw.rounded_rectangle([cx1, cy1, cx2, cy2], radius=22, fill=CARD_BG)
    draw_glow_rect(base, [cx1, cy1, cx2, cy2], CYAN, radius=22, glow_size=6, border_width=2)
    draw.text((cx1 + 22, cy1 + 16), "👑Collected Characters", fill=CYAN, font=font_box_title)
    count_text = f"{unique_chars} / {total_game}"
    draw.text((cx1 + 22, cy1 + 48), count_text, fill=WHITE, font=font_box_val)
    pct_text = f"{harem_pct:.1f}%"
    pct_w = draw.textlength(pct_text, font=font_box_val)
    draw.text((cx2 - 22 - pct_w, cy1 + 48), pct_text, fill=PINK, font=font_box_val)

    # Multi-color gradient progress bar
    bar_x1, bar_x2 = cx1 + 22, cx2 - 22
    bar_y = cy1 + 112
    bar_w = bar_x2 - bar_x1
    bar_h = 14
    draw.rounded_rectangle([bar_x1, bar_y, bar_x2, bar_y + bar_h], radius=bar_h // 2, fill=(45, 35, 60, 255))

    if harem_pct > 0:
        fill_w = max(2, int(bar_w * harem_pct / 100))
        grad = Image.new("RGBA", (fill_w, bar_h), (0, 0, 0, 0))
        gd = ImageDraw.Draw(grad)
        for x in range(fill_w):
            t = x / max(1, fill_w)
            gd.line([(x, 0), (x, bar_h)], fill=lerp(PURPLE, PINK, t))
        bar_mask = Image.new("L", (fill_w, bar_h), 0)
        ImageDraw.Draw(bar_mask).rounded_rectangle([0, 0, fill_w, bar_h], radius=bar_h // 2, fill=255)
        grad.putalpha(bar_mask)
        
        # Pink glow
        glow = Image.new("RGBA", (fill_w + 40, bar_h + 20), (0, 0, 0, 0))
        gd2 = ImageDraw.Draw(glow)
        gd2.rounded_rectangle([0, 0, fill_w, bar_h], radius=bar_h // 2, fill=(*PINK[:3], 110))
        glow = glow.filter(ImageFilter.GaussianBlur(radius=7))
        base.alpha_composite(glow, (bar_x1 - 20, bar_y - 10))
        base.paste(grad, (bar_x1, bar_y), grad)
        
        # Knob
        knob_x = bar_x1 + fill_w
        draw.ellipse([knob_x - 8, bar_y - 4, knob_x + 8, bar_y + bar_h + 4], fill=WHITE)
        draw.ellipse([knob_x - 5, bar_y - 1, knob_x + 5, bar_y + bar_h + 1], fill=PINK)

    draw.text((cx1 + 22, cy1 + 142), "Harem Progress", fill=MUTE, font=font_small)

    # ==================== CAPTION (clean HTML) ====================
    last_daily_str = last_daily[:10] if last_daily else "Never"
    extra_lines = []
    if fav_name:
        extra_lines.append(f"💖 <b>Favorite:</b> {fav_name}")
    if fav_rarity:
        extra_lines.append(f"🌟 <b>Rarity:</b> {fav_rarity}")
    extra = "\n".join(extra_lines)
    if extra:
        extra += "\n"

    caption_text = (
        f"✨ <b>Passport Profile of {first_name}</b>\n\n"
        f"<blockquote expandable>"
        f"🏅 <b>Achievements:</b> {unlocked_ach} Unlocked\n"
        f"🔥 <b>Daily Streak:</b> {streak} Days\n"
        f"🎒 <b>Inventory Items:</b> {inv_count} Total\n"
        f"🛒 <b>Market Trades:</b> {purchases} Done\n"
        f"📊 <b>All-time Summons:</b> {total_summons:,}\n"
        f"🕒 <b>Last Daily Claimed:</b> {last_daily_str}\n"
        f"{extra}"
        f"────────────────────\n"
        f"Progress: {progress_bar(harem_pct, 12)} {harem_pct:.1f}%"
        f"</blockquote>"
    )

    bio = io.BytesIO()
    bio.name = "profile.png"
    base.convert("RGB").save(bio, "PNG", quality=95)
    bio.seek(0)

    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎒 Check Collection", switch_inline_query_current_chat=f"collection.{user_id}")]
    ])

    await update.message.reply_photo(
        photo=bio,
        caption=caption_text,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup,
    )

def register(app):
    app.add_handler(CommandHandler("profile", profile_cmd))
