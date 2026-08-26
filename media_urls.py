"""Character image URL validation shared by Summon-bot media flows.

Only direct HTTPS assets from Catbox and ImgBB are accepted. Telegram file IDs,
data URIs, localhost URLs, redirects, and arbitrary third-party image hosts are
not valid character media.
"""
from __future__ import annotations

from urllib.parse import urlsplit


ALLOWED_IMAGE_HOSTS = {"files.catbox.moe", "i.ibb.co"}


def is_allowed_character_image_url(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    parsed = urlsplit(value.strip())
    return (
        parsed.scheme == "https"
        and parsed.hostname in ALLOWED_IMAGE_HOSTS
        and not parsed.username
        and not parsed.password
        and bool(parsed.path and parsed.path != "/")
    )


def require_character_image_url(value: object) -> str:
    if not is_allowed_character_image_url(value):
        raise ValueError(
            "Character image URL must be an HTTPS files.catbox.moe or i.ibb.co URL."
        )
    return str(value).strip()
