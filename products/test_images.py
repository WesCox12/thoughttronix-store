"""Product-image processing in ``Product.save()`` and the stored file's lifecycle."""

from decimal import Decimal
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.urls import reverse
from PIL import Image

from conftest import make_image_upload

from .models import IMAGE_SIZE, Product

pytestmark = pytest.mark.django_db

NAVY = (0x14, 0x18, 0x24)
RED = (200, 30, 30)


def close_to(pixel, expected, tolerance=8):
    """WebP is lossy, so colors are compared with a little slack."""
    return all(
        abs(a - b) <= tolerance for a, b in zip(pixel[:3], expected, strict=True)
    )


def stored_image(product):
    product.image.open("rb")
    try:
        image = Image.open(product.image)
        image.load()
        return image
    finally:
        product.image.close()


def attach(product, upload):
    product.image = upload
    product.save()
    return product


def media_files(media_root):
    return sorted(p.name for p in (media_root / "products").iterdir())


# --- Processing -------------------------------------------------------------


def test_new_upload_is_stored_as_an_800px_webp(product, media_root, image_upload):
    attach(product, image_upload)

    image = stored_image(product)
    assert image.format == "WEBP"
    assert image.size == (IMAGE_SIZE, IMAGE_SIZE)
    assert product.image.name == "products/seraphine-home-hub.webp"


def test_portrait_is_padded_left_and_right_not_cropped(product, media_root):
    attach(product, make_image_upload(size=(600, 1200), color=RED))

    image = stored_image(product).convert("RGB")
    # Fitted to 400×800, centered: navy bars at x < 200 and x >= 600.
    assert close_to(image.getpixel((5, 400)), NAVY)
    assert close_to(image.getpixel((795, 400)), NAVY)
    assert close_to(image.getpixel((400, 3)), RED)  # full height kept
    assert close_to(image.getpixel((400, 796)), RED)


def test_landscape_is_padded_top_and_bottom_not_cropped(product, media_root):
    attach(product, make_image_upload(size=(1536, 1024), color=RED))

    image = stored_image(product).convert("RGB")
    # Fitted to 800×533: navy bars above and below.
    assert close_to(image.getpixel((400, 5)), NAVY)
    assert close_to(image.getpixel((400, 795)), NAVY)
    assert close_to(image.getpixel((3, 400)), RED)  # full width kept
    assert close_to(image.getpixel((796, 400)), RED)


def test_transparent_areas_become_navy(product, media_root):
    source = Image.new("RGBA", (800, 800), (255, 255, 255, 0))
    source.paste(RED + (255,), (300, 300, 500, 500))
    buffer = BytesIO()
    source.save(buffer, format="PNG")
    attach(product, SimpleUploadedFile("clear.png", buffer.getvalue()))

    image = stored_image(product).convert("RGB")
    for corner in [(3, 3), (796, 3), (3, 796), (796, 796)]:
        assert close_to(image.getpixel(corner), NAVY), corner
    assert close_to(image.getpixel((400, 400)), RED)


def test_exif_orientation_is_applied(product, media_root):
    """A 600×800 photo tagged "rotate 90°" is really landscape."""
    source = Image.new("RGB", (600, 800), RED)
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: rotate 90° clockwise
    buffer = BytesIO()
    source.save(buffer, format="JPEG", exif=exif)
    attach(product, SimpleUploadedFile("photo.jpg", buffer.getvalue()))

    image = stored_image(product).convert("RGB")
    assert close_to(image.getpixel((400, 5)), NAVY)  # bars top/bottom, not sides
    assert close_to(image.getpixel((3, 400)), RED)


def test_editing_other_fields_does_not_touch_the_image(
    product, media_root, image_upload
):
    attach(product, image_upload)
    name = product.image.name
    stamp = (media_root / name).stat().st_mtime_ns

    product = Product.objects.get(pk=product.pk)
    product.price = Decimal("1.00")
    product.save()

    assert product.image.name == name
    assert (media_root / name).stat().st_mtime_ns == stamp
    assert media_files(media_root) == ["seraphine-home-hub.webp"]


# --- File lifecycle ----------------------------------------------------------


def test_replacing_deletes_the_old_file_after_commit(
    product, media_root, django_capture_on_commit_callbacks
):
    attach(product, make_image_upload())
    old_name = product.image.name

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        attach(product, make_image_upload(color=RED))
    assert (media_root / old_name).exists()  # still there until commit

    for callback in callbacks:
        callback()

    assert not (media_root / old_name).exists()
    assert product.image.name != old_name  # a new URL, never a stale cache hit
    assert (media_root / product.image.name).exists()


def test_clear_deletes_the_file_and_falls_back_to_placeholder(
    client, staff_user, product, media_root, django_capture_on_commit_callbacks
):
    attach(product, make_image_upload())
    old_path = media_root / product.image.name
    client.force_login(staff_user)
    data = {
        "name": product.name,
        "slug": product.slug,
        "price": "349.99",
        "category": str(product.category.pk),
        "image-clear": "on",
    }

    with django_capture_on_commit_callbacks(execute=True):
        client.post(
            reverse("products:manage_product_update", kwargs={"pk": product.pk}), data
        )

    product.refresh_from_db()
    assert not product.image
    assert not old_path.exists()
    assert product.display_image_url.endswith("placeholders/home-assistants.svg")


def test_deleting_a_product_deletes_its_file(
    product, media_root, django_capture_on_commit_callbacks
):
    attach(product, make_image_upload())
    path = media_root / product.image.name

    with django_capture_on_commit_callbacks(execute=True):
        product.delete()

    assert not path.exists()


def test_queryset_delete_also_deletes_files(
    product, media_root, django_capture_on_commit_callbacks
):
    attach(product, make_image_upload())
    path = media_root / product.image.name

    with django_capture_on_commit_callbacks(execute=True):
        Product.objects.all().delete()

    assert not path.exists()


def test_a_failed_save_leaves_the_previous_image_intact(
    product, category, media_root, django_capture_on_commit_callbacks
):
    attach(product, make_image_upload())
    old_name = product.image.name
    Product.objects.create(name="Taken", slug="taken", price=1, category=category)

    with django_capture_on_commit_callbacks(execute=True):
        with pytest.raises(IntegrityError), transaction.atomic():
            product.slug = "taken"
            attach(product, make_image_upload(color=RED))

    product.refresh_from_db()
    assert product.image.name == old_name
    assert (media_root / old_name).exists()


def test_a_rolled_back_transaction_keeps_the_previous_image(
    product, media_root, django_capture_on_commit_callbacks
):
    """The save itself succeeds, but the transaction around it rolls back."""
    attach(product, make_image_upload())
    old_name = product.image.name

    with django_capture_on_commit_callbacks(execute=True):
        with pytest.raises(RuntimeError), transaction.atomic():
            attach(product, make_image_upload(color=RED))
            raise RuntimeError("a later step in the same transaction fails")

    product.refresh_from_db()
    assert product.image.name == old_name
    assert (media_root / old_name).exists()
