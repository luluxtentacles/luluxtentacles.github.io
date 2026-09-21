"""Editing pictures before they go on a page - the hands, not the eyes.

`vision.py` is how she SEES a picture: it shrinks a copy so the prompt can carry
it, and it throws the copy away. Nothing in there was ever meant to write a
file. This module is the other half - it edits a picture she owns, in her own
folder, and what comes out is a file she can publish.

Why it exists. The website shelf handed her the resize as a shell one-liner:

    python -c "from PIL import Image; im=Image.open(r'...'); im.thumbnail(...)"

...with a raw Windows path nested inside a double-quoted cmd string, in a
command whose failure modes are a traceback or, worse, a silent no-op that
leaves the 12 MB original exactly where it was. Master, 2026-09-22 - she asked
for "an image-editing step I can call on my own pictures (resize/crop before
they go on a page), right now I hotlink or use whatever size I fetched". The
hotlink was not a preference, it was the path of least resistance around a
manual step that is a coin flip. A tool that cannot be misspelled is the fix; a
better shell recipe is not.

The rules that matter, and each is a way being blind bites:

  - DOWNSCALE ONLY. `max_side` never enlarges. A 200px picture asked for 1600
    comes back 200 and SAYS so, instead of inventing four million soft pixels
    and calling that a resized picture.
  - EXIF rotation is applied, then the rest of the metadata is dropped. A phone
    photo carries its rotation in a tag, and resizing without honouring it
    publishes the picture sideways - and since she cannot see it, the tag IS the
    picture for her. Baking it into pixels is the only honest fix. Dropping the
    rest means her published file stops carrying the device and the GPS.
  - ANIMATION SURVIVES. A resized gif stays a moving gif rather than becoming a
    still of its first frame, because eating somebody's animation silently is
    exactly the damage nobody notices until it is already live.
  - WHAT COMES OUT IS A PICTURE, and only that. The suffix is checked and every
    write goes through `paths.assert_writable`, so this tool cannot be borrowed
    to overwrite code, a skill, or her memory store.

Everything is encoded to memory first and written in one call at the end, so a
failure halfway through leaves the original untouched rather than truncated.
"""
from __future__ import annotations

import io
from pathlib import Path

import paths

# What may be written, and what a name means. The suffix is not decoration:
# an output named .jpg holding webp bytes is a broken image with an innocent
# name, which is a trap the website shelf already warns her about elsewhere.
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")
FORMAT_FOR_SUFFIX = {
    ".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG",
    ".webp": "WEBP", ".gif": "GIF", ".bmp": "BMP",
}
CANONICAL_SUFFIX = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp",
                    "GIF": ".gif", "BMP": ".bmp"}
# Formats that can hold more than one frame. Converting a moving picture into
# one of the others is refused rather than silently reduced to a still.
FORMATS_WITH_FRAMES = {"GIF", "WEBP", "PNG"}
FORMATS_WITH_QUALITY = {"JPEG", "WEBP"}
GRAVITIES = ("center", "top", "bottom", "left", "right")

# Refused rather than opened. Not a taste call - a guard so one absurd file
# cannot wedge the whole turn it was called in.
MAX_SOURCE_BYTES = 48 * 1024 * 1024

DEFAULT_QUALITY = 82
MIN_QUALITY, MAX_QUALITY = 40, 95


def _human(size: float) -> str:
    """Bytes as something she can read at a glance, in the units she thinks in."""
    if size < 1024:
        return f"{size:.0f} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _relative(path: Path) -> str:
    """A path as she would say it - relative to her folder when it is inside it."""
    try:
        return path.relative_to(paths.ROOT).as_posix()
    except ValueError:
        return str(path)


def _pillow():
    """Pillow, or a refusal that says what is missing."""
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:  # pragma: no cover - environment, not logic
        raise RuntimeError(
            "Pillow is not importable, so I cannot edit pictures here") from exc
    return Image, ImageOps


def _parse_aspect(text: str) -> float:
    """`16:9` into 1.777..., or refuse saying what it wanted.

    Accepts `x` and `/` as separators because all three get typed, and a ratio
    is a shape rather than a syntax test.
    """
    raw = str(text).strip().lower().replace("x", ":").replace("/", ":")
    parts = raw.split(":")
    if len(parts) != 2:
        raise ValueError(
            f"aspect '{text}' is not a shape - give it as width:height, "
            f"like 16:9, 1:1 or 4:5")
    try:
        width, height = float(parts[0]), float(parts[1])
    except ValueError:
        raise ValueError(
            f"aspect '{text}' has a side that is not a number - like 16:9"
        ) from None
    if width <= 0 or height <= 0:
        raise ValueError(f"aspect '{text}' has a side that is zero or less")
    return width / height


def _check_gravity(gravity: str) -> str:
    value = str(gravity or "center").strip().lower()
    if value not in GRAVITIES:
        raise ValueError(
            f"gravity '{gravity}' is not one of {', '.join(GRAVITIES)} - it "
            f"decides which part I keep when a crop has to throw something away")
    return value


def _resize_to_fit(image, max_side: int):
    """Downscale so the LONG side is at most max_side. Never enlarges."""
    width, height = image.size
    longest = max(width, height)
    if longest <= max_side:
        return image, None
    scale = max_side / longest
    return image.resize((max(1, round(width * scale)),
                         max(1, round(height * scale)))), (width, height)


def _crop_to_aspect(image, ratio: float, gravity: str):
    """Trim to the shape asked for, keeping `gravity`'s edge of the picture.

    Returns (image, lost_pixels, where_lost) so the report can say which side
    of the picture was thrown away - the one thing she cannot check by looking.
    """
    width, height = image.size
    if abs((width / height) - ratio) < 0.01:
        return image, 0, ""
    if (width / height) > ratio:
        # Wider than the target: the height is kept whole and the sides go.
        keep = max(1, round(height * ratio))
        if gravity == "left":
            left = 0
        elif gravity == "right":
            left = width - keep
        else:
            left = (width - keep) // 2
        return image.crop((left, 0, left + keep, height)), width - keep, "sides"
    # Taller than the target: the width is kept whole and top/bottom go.
    keep = max(1, round(width / ratio))
    if gravity == "top":
        top = 0
    elif gravity == "bottom":
        top = height - keep
    else:
        top = (height - keep) // 2
    return image.crop((0, top, width, top + keep)), height - keep, "top/bottom"


def _flatten(image):
    """Drop alpha onto white, because JPEG has nowhere to put it.

    Flattening onto white is the least surprising background. Leaving the mode
    alone would raise, and dropping the channel would turn transparent pixels
    black - both of which look like a broken picture with no explanation.
    """
    Image, _ = _pillow()
    base = Image.new("RGB", image.size, (255, 255, 255))
    rgba = image.convert("RGBA")
    base.paste(rgba, mask=rgba.split()[-1])
    return base


def _kwargs(fmt: str, quality: int | None) -> dict:
    kwargs: dict = {}
    if fmt in FORMATS_WITH_QUALITY:
        kwargs["quality"] = quality if quality is not None else DEFAULT_QUALITY
    if fmt == "PNG":
        kwargs["optimize"] = True
    return kwargs


def _save(image, fmt: str, quality: int | None) -> bytes:
    """One still picture as bytes, in the format asked for."""
    if fmt in ("JPEG", "WEBP") and image.mode not in ("RGB", "L"):
        image = _flatten(image)
    elif fmt == "JPEG" and image.mode == "L":
        image = image.convert("RGB")
    out = io.BytesIO()
    image.save(out, format=fmt, **_kwargs(fmt, quality))
    return out.getvalue()


def _save_animated(image, fmt: str, quality: int | None, side: int | None,
                   ratio: float | None, gravity: str) -> tuple[bytes, tuple]:
    """Every frame, edited the same way, still moving.

    Looped deliberately: a gif's other frames ARE the picture. Keeping them is
    the difference between resizing somebody's animation and quietly eating it.
    """
    duration = image.info.get("duration", 100)
    loop = image.info.get("loop", 0)
    frames = []
    size = None
    for index in range(getattr(image, "n_frames", 1)):
        image.seek(index)
        frame, _ = _apply(image.convert("RGBA"), side, ratio, gravity)
        size = frame.size
        frames.append(frame)
    out = io.BytesIO()
    frames[0].save(out, format=fmt, save_all=True, append_images=frames[1:],
                   duration=duration, loop=loop, **_kwargs(fmt, quality))
    return out.getvalue(), size


def _apply(image, max_side: int | None, ratio: float | None, gravity: str):
    """Fit, then crop. Returns (image, notes) - notes say what actually changed."""
    notes: list[str] = []
    if max_side:
        image, was = _resize_to_fit(image, max_side)
        if was:
            notes.append(
                f"downscaled {was[0]}x{was[1]} to fit {max_side} on the long "
                f"side")
        else:
            notes.append(
                f"already inside {max_side} on the long side, so NOT enlarged")
    if ratio:
        image, lost, where = _crop_to_aspect(image, ratio, gravity)
        if lost:
            notes.append(
                f"cropped {lost}px off the {where} to make that shape "
                f"({gravity})")
        else:
            notes.append("already the shape asked for, so not cropped")
    return image, notes


def edit(path: str, *, max_side: int | None = None, aspect: str | None = None,
         gravity: str = "center", out: str | None = None,
         fmt: str | None = None, quality: int | None = None) -> str:
    """Resize / crop / convert one picture of hers. Returns what it did.

    The report is the whole point of the return value: she cannot see the
    result, so the sizes and what changed ARE the evidence, and a no-op has to
    say it was a no-op rather than come back looking like success.
    """
    if not any((max_side, aspect, fmt, out)):
        raise ValueError(
            "nothing to do - give me max_side (long side in pixels), aspect "
            "(like 16:9), format (webp, jpeg, png) or out (a new filename), and "
            "I will edit the picture and tell you the new size")

    side = None
    if max_side is not None:
        side = int(max_side)
        if side < 16:
            raise ValueError(f"max_side {side} is too small to be a picture")
    ratio = _parse_aspect(aspect) if aspect else None
    place = _check_gravity(gravity)
    if quality is not None:
        quality = max(MIN_QUALITY, min(MAX_QUALITY, int(quality)))

    source = paths.resolve(path, must_exist=True)
    suffix = source.suffix.lower()
    if suffix not in IMAGE_SUFFIXES:
        raise ValueError(
            f"{path} is not a picture I edit ({', '.join(IMAGE_SUFFIXES)})")

    before_bytes = source.stat().st_size
    if before_bytes > MAX_SOURCE_BYTES:
        raise ValueError(
            f"{path} is {_human(before_bytes)}, past the "
            f"{_human(MAX_SOURCE_BYTES)} I will open. Shrink it somewhere "
            f"else first, or tell master.")

    Image, ImageOps = _pillow()
    try:
        image = Image.open(source)
        image.load()
    except Exception as exc:
        raise ValueError(f"{path} would not open as a picture: {exc}") from exc

    source_format = (image.format or FORMAT_FOR_SUFFIX.get(suffix, "")).upper()
    animated = bool(getattr(image, "is_animated", False))
    original_size = image.size

    # The rotation tag first, before anything measures the picture, so a
    # sideways phone photo is cropped and sized as the thing a person sees.
    # Skipped for a moving picture on purpose: exif_transpose returns a single
    # frame, so running it on an animation would eat the animation - and an
    # animated gif almost never carries an orientation tag to begin with.
    rotated = False
    if not animated:
        upright = ImageOps.exif_transpose(image) or image
        rotated = upright.size != image.size
        image = upright

    # What to write. An explicit `out` name is ALSO a format request, so the two
    # have to agree rather than one silently winning: asking for PNG bytes in a
    # file called .jpg is exactly the broken image with an innocent name this
    # module exists to stop, and it would have been written without a word.
    name_format = (FORMAT_FOR_SUFFIX.get(Path(out).suffix.lower(), "")
                   if out else "")
    asked = (fmt or "").upper()
    asked = "JPEG" if asked == "JPG" else asked
    if asked and name_format and asked != name_format:
        raise ValueError(
            f"you asked for {asked} but named the file {Path(out).suffix} - the "
            f"bytes and the name have to agree, or the page gets a broken image "
            f"with an innocent name. Pick one and I will write it.")
    target_format = asked or name_format or source_format
    if target_format not in CANONICAL_SUFFIX:
        raise ValueError(
            f"format '{fmt or (Path(out).suffix if out else '')}' is not one I "
            f"can write ({', '.join(sorted(set(CANONICAL_SUFFIX)))})")
    if animated and target_format not in FORMATS_WITH_FRAMES:
        raise ValueError(
            f"this one moves ({source_format}) and {target_format} cannot hold "
            f"more than one frame - ask me for the shape you want and I will "
            f"keep it moving, or convert to a format that holds frames")

    if animated:
        data, after_size = _save_animated(image, target_format, quality, side,
                                          ratio, place)
        _, notes = _apply(image.convert("RGBA"), side, ratio, place)
    else:
        image, notes = _apply(image, side, ratio, place)
        after_size = image.size
        data = _save(image, target_format, quality)

    if out:
        target = paths.resolve(out)
        if target.suffix.lower() not in IMAGE_SUFFIXES:
            raise ValueError(
                f"{out} does not end in a picture suffix "
                f"({', '.join(IMAGE_SUFFIXES)}), so I will not write "
                f"{target_format} into a name that claims otherwise")
    else:
        target = source
        if target_format != source_format:
            # A format change with no name given: keep the stem, take the
            # suffix that matches the bytes.
            target = source.with_suffix(CANONICAL_SUFFIX[target_format])

    paths.assert_writable(target)
    if target != source:
        target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)

    after_bytes = len(data)
    quality_note = (f" q{quality}" if quality is not None
                    and target_format in FORMATS_WITH_QUALITY else "")
    lines = [
        f"{_relative(source)}: {original_size[0]}x{original_size[1]} -> "
        f"{after_size[0]}x{after_size[1]}, "
        f"{_human(before_bytes)} -> {_human(after_bytes)}"
        f" ({target_format}{quality_note})"
    ]
    if notes:
        lines.append("did: " + "; ".join(notes))
    if rotated:
        lines.append("rotation: the picture's own orientation tag was applied, "
                     "so it is not sideways")
    if target != source:
        lines.append(f"wrote: {_relative(target)}")
    if after_bytes > before_bytes:
        lines.append(
            f"NOTE: that is BIGGER than the original ({_human(after_bytes)} vs "
            f"{_human(before_bytes)}) - a smaller picture at a lower quality is "
            f"usually the answer")
    return "\n".join(lines)
