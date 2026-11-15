"""Product-image validators: each rule rejects with its own message."""

import pytest
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from conftest import make_image_upload

from .models import Product
from .validators import (
    validate_image_dimensions,
    validate_image_file_size,
    validate_image_format,
    validate_usable_image,
)

ALL_VALIDATORS = [
    validate_usable_image,
    validate_image_format,
    validate_image_file_size,
    validate_image_dimensions,
]


def messages(validator, upload):
    with pytest.raises(ValidationError) as excinfo:
        validator(upload)
    return excinfo.value.messages


@pytest.mark.parametrize("image_format", ["PNG", "JPEG", "WEBP"])
def test_valid_images_pass_every_validator(image_format):
    upload = make_image_upload(name="ok.img", image_format=image_format)

    for validator in ALL_VALIDATORS:
        validator(upload)


def test_a_renamed_text_file_is_not_a_usable_image():
    upload = SimpleUploadedFile("notes.png", b"Not an image, just notes.")

    assert messages(validate_usable_image, upload) == [
        "This file isn't a usable image. Upload a PNG, JPEG, or WebP file."
    ]


def test_a_truncated_png_is_not_a_usable_image():
    whole = make_image_upload(size=(600, 600)).read()
    upload = SimpleUploadedFile("cut.png", whole[: len(whole) // 2])

    assert messages(validate_usable_image, upload) == [
        "This file isn't a usable image. Upload a PNG, JPEG, or WebP file."
    ]


def test_a_gif_is_rejected_by_format():
    upload = make_image_upload(name="anim.gif", image_format="GIF")

    assert messages(validate_image_format, upload) == [
        "This is a GIF image. Product images must be PNG, JPEG, or WebP."
    ]


def test_format_is_read_from_content_not_extension():
    upload = make_image_upload(name="looks-fine.png", image_format="GIF")

    with pytest.raises(ValidationError):
        validate_image_format(upload)


def test_an_oversized_file_is_rejected():
    png = make_image_upload().read()
    padding = b"\0" * (int(14.2 * 1024 * 1024) - len(png))
    upload = SimpleUploadedFile("huge.png", png + padding)

    assert messages(validate_image_file_size, upload) == [
        "This file is 14.2 MB. Product images must be 10 MB or smaller."
    ]


def test_exactly_ten_megabytes_is_allowed():
    upload = SimpleUploadedFile("edge.png", b"\0" * (10 * 1024 * 1024))

    validate_image_file_size(upload)


def test_a_small_image_is_rejected():
    upload = make_image_upload(size=(300, 200))

    assert messages(validate_image_dimensions, upload) == [
        "This image is 300×200 pixels. "
        "Product images must be at least 400 pixels on each side."
    ]


def test_the_shorter_side_decides():
    validate_image_dimensions(make_image_upload(size=(400, 2000)))

    with pytest.raises(ValidationError):
        validate_image_dimensions(make_image_upload(size=(2000, 399)))


@pytest.mark.parametrize(
    "max_pixels",
    [300_000, 100_000],  # 600×800 = 480,000 px: Pillow warns, then raises
    ids=["warning", "error"],
)
def test_a_decompression_bomb_is_rejected(monkeypatch, max_pixels):
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", max_pixels)

    assert messages(validate_usable_image, make_image_upload(size=(600, 800))) == [
        "This image's dimensions are too large to process."
    ]


def test_an_unreadable_file_is_reported_only_once():
    """Format and dimension checks stay quiet; the usability check reports it."""
    upload = SimpleUploadedFile("notes.png", b"Not an image.")

    validate_image_format(upload)
    validate_image_dimensions(upload)


def test_already_committed_files_are_skipped(product, media_root):
    """A stored image is never re-opened, even one that breaks today's rules."""
    # Write straight to storage: Product.save() would process it into a valid WebP.
    bad = make_image_upload(name="bad.gif", size=(100, 100), image_format="GIF")
    name = default_storage.save("products/bad.gif", bad)
    Product.objects.filter(pk=product.pk).update(image=name)
    product.refresh_from_db()

    for validator in ALL_VALIDATORS:
        validator(product.image)
