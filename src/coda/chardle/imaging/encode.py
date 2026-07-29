"""Turning a composed board into bytes Discord will accept.

A board is re-uploaded on every guess, so a live board is downscaled and encoded
lossily. Only the finished board -- uploaded once, and the one people screenshot
-- is worth full resolution.
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image

LIVE_WIDTH = 1200
LIVE_QUALITY = 80
FINAL_QUALITY = 95


def encode(image: Image.Image, *, final: bool) -> bytes:
    """WebP bytes for one board."""
    if not final:
        image = _downscale(image, LIVE_WIDTH)
    buffer = BytesIO()
    # Flattened onto the plate's own dark backing: Discord renders a transparent
    # PNG against the user's theme, which makes the 72-grey values vanish in
    # dark mode.
    _flatten(image).save(
        buffer,
        format="WEBP",
        quality=FINAL_QUALITY if final else LIVE_QUALITY,
        method=4,
    )
    return buffer.getvalue()


def _downscale(image: Image.Image, width: int) -> Image.Image:
    if image.width <= width:
        return image
    height = round(image.height * width / image.width)
    return image.resize((width, height), Image.LANCZOS) # type: ignore


def _flatten(image: Image.Image) -> Image.Image:
    backing = Image.new("RGBA", image.size, (24, 24, 28, 255))
    backing.alpha_composite(image)
    return backing.convert("RGB")
