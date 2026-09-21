"""Her eyes.

Turns a picture into OpenAI-shaped image_url content parts, downscaled and
capped so one screenshot cannot eat the context. The model is chosen elsewhere
(brain.py), by the shape of what it is handed: any prompt carrying an image part
is routed to vision_model.

Three ways in, and the point of the last two is that neither one needs a message
- master, 2026-09-20: "make her image reading ability not tied to messages" and
"so she can use it for web browsing".

  collect()   - pictures attached to a Discord message.
  from_url()  - a picture at a public address. This one DOES touch the network,
                and it borrows webtool's address guard instead of growing a
                second one that could drift from it.
  from_file() - a picture already on her own disk: a screenshot she just took,
                an image she made. Added 2026-09-21, because until it existed
                the only way to hold her own work up to her own eyes was a
                script she had written herself.

describe() and describe_file() are the whole capability in one call each: the
picture in, what-is-in-it out as words she can carry into the rest of the turn.

from_file() is the one that is NOT a public read, so it is confined to ROOT and
gated at the tool (see look_at_file in tools.py) rather than being a flag on
describe().

Nothing here trusts a content type. A picture is whatever its first bytes prove
it is - see sniff - so bytes that are not one of the four formats are refused
rather than relabelled and forwarded.
"""
from __future__ import annotations

import base64
import io
import logging
import urllib.error
import urllib.parse
import urllib.request

import brain
import paths
import webtool

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

# And the ceiling on ALL of them together. This one was documented for a while
# before it existed: _shrink bounds each picture, but nothing bounded the sum,
# so three ordinary screenshots on one message went out at full size together.
# A per-image valve is not a budget.
MAX_TOTAL_BYTES = 2_000_000

# Pulling a picture off the internet. Bigger than MAX_IMAGE_BYTES on purpose:
# the ceiling is on what reaches the prompt, and an image has to come down the
# wire before it can be shrunk. Anything past this is refused rather than
# buffered - a 40MB "image" is not a picture, it is a way to eat the box.
FETCH_TIMEOUT_SECONDS = 20
MAX_FETCH_BYTES = 12_000_000
# What one describe() may write back. Generous compared with a chat turn because
# reasoning is billed to the same budget and a description she cannot finish is
# worth less than the call it cost.
DESCRIBE_MAX_TOKENS = 1000

# The formats she will look at, proved by their actual first bytes.
#
# This exists because a content type is a CLAIM, not evidence. Discord sets it
# from the filename, and any server can put whatever it likes next to
# "Content-Type: image/png". The old fallback believed it: whenever Pillow was
# missing or the data would not open, it returned the untouched bytes labelled
# "image/png" - so a non-image was shrunk never AND forwarded anyway, which is a
# lie told to the vision model on request. Now the bytes have to prove what they
# are, and the label sent is the one they earned.
_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


class NotAnImage(Exception):
    """The bytes are not one of the four formats she will look at."""


def sniff(data: bytes) -> str:
    """The mime these bytes actually are, or "" if they are not a picture."""
    for signature, mime in _MAGIC:
        if data.startswith(signature):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return ""


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
    """One PROVEN image, downscaled and re-encoded when Pillow is available.

    Returns (bytes, mime). Raises NotAnImage for anything that is not actually a
    picture - that is the change that matters here. The old fallback returned the
    untouched data labelled "image/png" whenever Pillow was missing or the bytes
    would not open, so a non-image was shrunk never and forwarded anyway.

    A genuine image that Pillow cannot re-encode is still passed through at its
    original size: a heavy picture beats no picture, and collect() holds the
    total line. What is refused is a thing that was never a picture at all.
    """
    mime = sniff(data)
    if not mime:
        raise NotAnImage("not a png, jpeg, gif or webp")
    try:
        from PIL import Image
    except ImportError:
        # Cannot downscale without Pillow, but the bytes proved they are an
        # image, so the label stays honest even at full size.
        return data, mime
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception as exc:
        LOG.warning("vision: could not re-encode a real image: %s", exc)
        return data, mime

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


def _build(data: bytes, name: str) -> tuple[dict, int]:
    """One picture's bytes as one image_url part, plus what it costs.

    The cost comes back rather than being recomputed by the caller, so the part
    and the budget can never disagree about what a picture weighs.
    """
    body, mime = _shrink(data)
    encoded_len = (len(body) + 2) // 3 * 4
    LOG.info("vision: %s -> %s, ~%d KB of base64",
             name, mime, encoded_len // 1024)
    part = {"type": "image_url", "image_url": {"url": _encode(body, mime)}}
    return part, encoded_len


def from_url(url: str) -> list[dict]:
    """One picture at a public address, as image_url parts.

    Raises ValueError for anything that is not a usable picture, and
    webtool.Blocked for an address that is not public. Both are text the caller
    hands back to the model, not a crash.

    The address guard is webtool's on purpose: one wall for every fetch she
    makes, so a hole in it cannot open in two places and a fix lands for both.
    Redirects are followed by hand for the same reason - every hop re-checked
    rather than trusted, because a public host that points at 169.254.x is the
    whole trick this guards against.
    """
    target = (url or "").strip()
    if not target:
        raise ValueError("no url given")
    if "://" not in target:
        target = "https://" + target

    for _ in range(webtool.MAX_REDIRECTS + 1):
        webtool._check(target)
        request = urllib.request.Request(target, headers={
            "User-Agent": webtool.USER_AGENT,
            "Accept": "image/*,*/*;q=0.5",
        })
        try:
            with webtool._OPENER.open(request,
                                      timeout=FETCH_TIMEOUT_SECONDS) as response:
                ctype = ((response.headers.get("Content-Type") or "")
                         .split(";")[0].strip().lower())
                data = response.read(MAX_FETCH_BYTES + 1)
        except urllib.error.HTTPError as exc:
            if exc.code in webtool._REDIRECT_CODES:
                location = exc.headers.get("Location")
                if not location:
                    raise ValueError(
                        f"redirected nowhere (HTTP {exc.code})") from exc
                target = urllib.parse.urljoin(target, location)
                continue
            raise ValueError(f"HTTP {exc.code} from {target}") from exc

        if len(data) > MAX_FETCH_BYTES:
            raise ValueError(
                f"bigger than {MAX_FETCH_BYTES // 1_000_000}MB - not a picture "
                f"I will pull down")
        path = urllib.parse.urlparse(target).path.lower()
        if ctype and not ctype.startswith("image/") and not path.endswith(IMAGE_EXTS):
            raise ValueError(f"that address is {ctype}, not an image")
        name = path.rsplit("/", 1)[-1][:60] or target
        try:
            part, _ = _build(data, name)
        except NotAnImage as exc:
            raise ValueError(
                f"that address answered with something that is not an image "
                f"({exc})") from exc
        return [part]
    raise ValueError("too many redirects")


def from_file(path: str) -> list[dict]:
    """One picture off my own disk, as image_url parts.

    The door that was MISSING, and the reason research/_eyes.py existed at all:
    every other way in needs a PUBLIC address - collect() wants a Discord
    attachment, from_url() refuses file:// on purpose - so a screenshot of her
    own page had nothing in the box that could look at it. Master, 2026-09-21:
    "did we add for any website she can screenshot it to see it if she needs
    it". This is that.

    Confined to her own folder, and deliberately NOT to paths.EXTERNAL_ROOTS:
    that tuple exists so resolve() can reach her interpreter and the whisper
    tree, and neither is a place to read pictures from. Outside ROOT is refused
    rather than fetched.

    Raises ValueError for anything that is not a usable picture, and
    paths.SandboxError for a path that is not hers to read. Both are text a
    caller can hand straight back to the model, not a crash.
    """
    name = str(path or "").strip()
    if not name:
        raise ValueError("no path given")
    target = paths.resolve(name)
    try:
        target.relative_to(paths.ROOT)
    except ValueError:
        raise ValueError("that is outside my own folder") from None
    if not target.is_file():
        raise ValueError(f"no file at {name}")
    if target.stat().st_size > MAX_FETCH_BYTES:
        raise ValueError(f"bigger than {MAX_FETCH_BYTES // 1_000_000}MB - not a "
                         f"picture I will read")
    try:
        part, _ = _build(target.read_bytes(), target.name)
    except NotAnImage as exc:
        # Wrapped, the way from_url() wraps it, so both doors fail with the one
        # exception the docstrings promise. A file named .png that is really
        # text is refused by its bytes here, not by its name.
        raise ValueError(f"that file is not an image ({exc})") from exc
    return [part]


def describe_file(path: str, question: str = "",
                  brain_config: dict | None = None) -> str:
    """Look at one picture FILE of mine and answer a question about it.

    Same shape and the same reasoning as describe() below: the picture goes to
    the vision model and NOT into her own conversation, so one image costs one
    call instead of being resent on every round of a tool loop that can run
    forty deep.

    Never raises. Every failure is a sentence she can read and act on,
    including the boring ones - a path that is not there, or not a picture.
    """
    config = brain_config or {}
    if not config.get("base_url") or not config.get("model"):
        return "[I have no brain configured to look at images with]"
    try:
        parts = from_file(path)
    except paths.SandboxError as exc:
        return f"refused: {exc}"
    except Exception as exc:
        return f"[could not look at that file: {exc}]"
    if not parts:
        return "[nothing in that file I could read as an image]"
    ask = (question or "").strip() or (
        "What is in this image? Be specific, briefly.")
    messages = [{"role": "user",
                 "content": [{"type": "text", "text": ask}] + parts}]
    reply = brain.complete(config, messages, max_tokens=DESCRIBE_MAX_TOKENS)
    text = (reply.get("content") or "").strip()
    return text or "[the vision model had nothing to say about it]"


def describe(url: str, question: str = "",
             brain_config: dict | None = None) -> str:
    """Look at one picture and answer a question about it. Returns text.

    This is what makes her eyes usable anywhere - a page she fetched, a
    screenshot someone linked, anything public - because the answer comes back
    as words she can carry into the rest of what she is doing.

    The picture goes to the vision model and NOT into her own conversation: one
    image costs one call here, instead of being resent on every round of a tool
    loop that can run forty deep. That is the whole reason this shape was
    chosen over injecting the image into the prompt.

    Never raises. Every failure is a sentence she can read and act on.
    """
    config = brain_config or {}
    if not config.get("base_url") or not config.get("model"):
        return "[I have no brain configured to look at images with]"
    try:
        parts = from_url(url)
    except webtool.Blocked as exc:
        return f"refused: {exc}"
    except Exception as exc:
        return f"[could not look at that image: {exc}]"
    if not parts:
        return "[nothing at that address I could read as an image]"
    ask = (question or "").strip() or "What is in this image? Be specific, briefly."
    messages = [{"role": "user",
                 "content": [{"type": "text", "text": ask}] + parts}]
    reply = brain.complete(config, messages, max_tokens=DESCRIBE_MAX_TOKENS)
    text = (reply.get("content") or "").strip()
    return text or "[the vision model had nothing to say about it]"


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
        try:
            part, encoded_len = _build(data, name)
        except NotAnImage as exc:
            LOG.warning("vision: %s is not an image (%s); ignored", name, exc)
            continue
        if total and total + encoded_len > MAX_TOTAL_BYTES:
            # She still gets the first pictures rather than none - an empty
            # answer because a message was image-heavy helps nobody.
            LOG.warning("vision: %s would push the prompt past %d KB; left out",
                        name, MAX_TOTAL_BYTES // 1024)
            continue
        total += encoded_len
        parts.append(part)
    return parts
