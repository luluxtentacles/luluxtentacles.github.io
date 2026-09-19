"""Her eyes.

Turns the image attachments on a Discord message into OpenAI-shaped
image_url content parts, downscaled and capped so one screenshot cannot
eat the context. Nothing here talks to the network: the bytes come from
the caller, the parts go into the prompt, and the vision model is chosen
elsewhere (brain.py) by the shape of what it is handed.
"""
from __future__ import annotations

import base64
import io
import logging

LOG = logging.getLogger("lulu")

# What counts as a picture. Voice notes (.ogg) and text files are excluded
# by both checks here - the content type first, the extension as a fallback
# for the endpoints that send a generic octet-stream.
IMAGE_TYPES = ("image/png", "image/jpeg", "image/webp", "image/gif")
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif")

# The model does not need Discord's full resolution. 1280 on the long side
# keeps text in screenshots readable while cutting a 4K screenshot by ~10x.
MAX_SIDE = 1280

# Ceiling on the base64 one image may add to the prompt. A Discord
# screenshot base64s to megabytes, context is finite, and vision calls
# burn it faster than anything else - so the valve is here, before the
# provider sees it.
MAX_IMAGE_BYTES = 900_000


def is_image_attachment(attachment) -> bool:
    """True for the attachments her eyes can read."""
    ctype = (getattr(attachment, "content_type", "") or "").lower()
    if ctype.split(";")[0].strip() in IMAGE_TYPES:
        return True
    name = (getattr(attachment, "filename", "") or "").lower()
    return name.endswith(IMAGE_EXTS)


def _encode(body: bytes, mime: str) -> str:
    """Bytes as a data URI, the OpenAI wire shape for an inline image."""
    return f"data:{mime};base64," + base64.b64encode(body).decode("ascii")


def _shrink(data: bytes) -> tuple[bytes, str]:
    """One image, downscaled and re-encoded when Pillow is available.

    Returns (bytes, mime). Falls back to the untouched original when Pillow
    is missing or the bytes will not open - a heavy picture beats no
    picture, and the total cap in collect() still holds the line.
    """
    try:
        from PIL import Image
    except ImportError:
        return data, "image/png"
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception as exc:
        LOG.warning("could not open an image: %s", exc)
        return data, "image/png"

    if getattr(image, "is_animated", False):
        image.seek(0)  # first frame of a gif is plenty
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    width, height = image.size
    scale = MAX_SIDE / max(width, height)
    if scale < 1:
        image = image.resize((max(1, round(width * scale)),
                              max(1, round(height * scale))))

    out = io.BytesIO()
    for quality in (85, 70, 50, 35):
        out = io.BytesIO()
        image.save(out, format="JPEG", quality=quality)
        if (len(out.getvalue()) + 2) // 3 * 4 <= MAX_IMAGE_BYTES:
            break
    return out.getvalue(), "image/jpeg"


async def collect(attachments) -> list[dict]:
    """Every readable image on a message as image_url content parts, or [].

    Async only because attachment.read() is. Never raises: an attachment
    that will not download or open costs a log line and her sight of that
    one picture, never the reply.
    """
    parts: list[dict] = []
    total = 0
    for attachment in attachments or []:
        if not is_image_attachment(attachment):
            continue
        name = getattr(attachment, "filename", "?")
        try:
            data = await attachment.read()
        except Exception as exc:
            LOG.warning("vision: could not read %s: %s", name, exc)
            continue
        body, mime = _shrink(data)
        encoded_len = (len(body) + 2) // 3 * 4
        total += encoded_len
        parts.append({"type": "image_url", "image_url": {"url": _encode(body, mime)}})
        LOG.info("vision: %s -> %s, ~%d KB of base64",
                 name, mime, encoded_len // 1024)
    return parts
