"""Product-image validators — small, pure, and unit-testable.

Plain functions that raise ``ValidationError``, attached to
``Product.image`` through ``validators=[...]`` so every ``ModelForm`` —
the back office's ``ProductForm`` and the Django admin's form — runs the
same rules with the same messages.

Every validator skips a file that is already committed to storage: the
rules guard new uploads, so editing a product's price never re-opens its
stored image. Each validator checks one rule; when Pillow can't read a
file at all, only ``validate_usable_image`` reports it.
"""

import warnings

from django.core.exceptions import ValidationError
from PIL import Image

ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MIN_SIDE = 400

UNUSABLE_IMAGE_MESSAGE = (
    "This file isn't a usable image. Upload a PNG, JPEG, or WebP file."
)
DECOMPRESSION_BOMB_MESSAGE = "This image's dimensions are too large to process."


def _is_committed(value) -> bool:
    """True for a file already in storage (a ``FieldFile`` that's been saved)."""
    return getattr(value, "_committed", False)


def _open_header(value) -> Image.Image | None:
    """Open ``value`` lazily (header only), or return None if Pillow can't."""
    try:
        value.seek(0)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            return Image.open(value)
    except Exception:
        return None


def validate_usable_image(value) -> None:
    """Reject a file Pillow can't fully decode, or a decompression bomb.

    The image is fully decoded with ``load()``, not only ``verify()``, so
    a truncated file is rejected here rather than failing later during
    processing. Pillow's pixel-count guard (``Image.MAX_IMAGE_PIXELS``)
    counts as a rejection whether it warns or raises.
    """
    if _is_committed(value):
        return
    try:
        value.seek(0)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(value) as image:
                image.load()
    except (Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise ValidationError(
            DECOMPRESSION_BOMB_MESSAGE, code="decompression_bomb"
        ) from None
    except Exception:
        raise ValidationError(UNUSABLE_IMAGE_MESSAGE, code="invalid_image") from None
    finally:
        value.seek(0)


def validate_image_format(value) -> None:
    """Reject an image whose content (not its extension) isn't PNG, JPEG, or WebP."""
    if _is_committed(value):
        return
    image = _open_header(value)
    if image is None or image.format in ALLOWED_FORMATS:
        return
    raise ValidationError(
        f"This is a {image.format} image. Product images must be PNG, JPEG, or WebP.",
        code="image_format",
    )


def validate_image_file_size(value) -> None:
    """Reject a file larger than 10 MB."""
    if _is_committed(value) or value.size <= MAX_FILE_SIZE:
        return
    megabytes = value.size / (1024 * 1024)
    raise ValidationError(
        f"This file is {megabytes:.1f} MB. Product images must be 10 MB or smaller.",
        code="file_size",
    )


def validate_image_dimensions(value) -> None:
    """Reject an image whose shorter side is under 400 pixels."""
    if _is_committed(value):
        return
    image = _open_header(value)
    if image is None or min(image.size) >= MIN_SIDE:
        return
    width, height = image.size
    raise ValidationError(
        f"This image is {width}×{height} pixels. Product images must be "
        f"at least {MIN_SIDE} pixels on each side.",
        code="image_dimensions",
    )
