"""Back-office catalog management: access control, CRUD round-trips, validation."""

from decimal import Decimal
from http import HTTPStatus

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils.html import escape
from PIL import Image

from conftest import make_image_upload

from .models import Category, Product, Tag

pytestmark = pytest.mark.django_db


def manage_urls(product, tag):
    """Every staff-only catalog URL, for the access-control sweeps."""
    return [
        reverse("products:manage_products"),
        reverse("products:manage_product_create"),
        reverse("products:manage_product_update", kwargs={"pk": product.pk}),
        reverse("products:manage_product_delete", kwargs={"pk": product.pk}),
        reverse("products:manage_catalog"),
        reverse("products:manage_category_create"),
        reverse("products:manage_category_update", kwargs={"pk": product.category.pk}),
        reverse("products:manage_tag_create"),
        reverse("products:manage_tag_update", kwargs={"pk": tag.pk}),
    ]


def product_data(category, **overrides):
    data = {
        "name": "MindSync Sleep Halo",
        "slug": "mindsync-sleep-halo",
        "tagline": "Dream in someone else's 4K.",
        "description": "A bedside accessory for the MindSync line.",
        "price": "199.99",
        "is_available": "on",
        "category": str(category.pk),
    }
    data.update(overrides)
    return data


# --- Access control ----------------------------------------------------------


def test_anonymous_users_are_sent_to_login(client, product, tag):
    for url in manage_urls(product, tag):
        response = client.get(url)

        assert response.status_code == HTTPStatus.FOUND, url
        assert reverse("accounts:login") in response.url


def test_customers_get_403(client, customer, product, tag):
    client.force_login(customer)

    for url in manage_urls(product, tag):
        assert client.get(url).status_code == HTTPStatus.FORBIDDEN, url


def test_staff_get_200(client, staff_user, product, tag):
    client.force_login(staff_user)

    for url in manage_urls(product, tag):
        response = client.get(url)

        assert response.status_code == HTTPStatus.OK, url
        # A multi-line {# #} comment renders as literal text — guard
        # against template comments leaking onto the page.
        assert "{#" not in response.content.decode(), url


def test_navbar_shows_back_office_to_staff_only(client, staff_user, customer):
    client.force_login(staff_user)
    assert "Back office" in client.get(reverse("products:catalog")).content.decode()

    client.force_login(customer)
    assert "Back office" not in client.get(reverse("products:catalog")).content.decode()


# --- Product CRUD ------------------------------------------------------------


def test_staff_can_create_a_product(client, staff_user, category, tag):
    client.force_login(staff_user)

    response = client.post(
        reverse("products:manage_product_create"),
        product_data(category, tags=[str(tag.pk)]),
        follow=True,
    )

    product = Product.objects.get(slug="mindsync-sleep-halo")
    assert product.price == Decimal("199.99")
    assert product.category == category
    assert list(product.tags.all()) == [tag]
    assert "created." in response.content.decode()


def test_staff_can_upload_an_image(
    client, staff_user, product, media_root, image_upload
):
    client.force_login(staff_user)
    data = product_data(product.category, name=product.name, slug=product.slug)
    data["image"] = image_upload

    response = client.post(
        reverse("products:manage_product_update", kwargs={"pk": product.pk}), data
    )

    assert response.status_code == HTTPStatus.FOUND
    product.refresh_from_db()
    assert product.image.name.startswith("products/")
    assert (media_root / product.image.name).is_file()


def test_product_form_accepts_file_uploads(client, staff_user, product):
    client.force_login(staff_user)

    page = client.get(
        reverse("products:manage_product_update", kwargs={"pk": product.pk})
    ).content.decode()

    assert 'enctype="multipart/form-data"' in page
    assert 'type="file"' in page
    assert "file-input" in page


def test_staff_can_edit_a_price(client, staff_user, product):
    client.force_login(staff_user)
    data = product_data(product.category, name=product.name, slug=product.slug)
    data["price"] = "299.99"

    client.post(
        reverse("products:manage_product_update", kwargs={"pk": product.pk}), data
    )

    product.refresh_from_db()
    assert product.price == Decimal("299.99")


def test_staff_can_mark_a_product_unavailable(client, staff_user, product):
    client.force_login(staff_user)
    data = product_data(product.category, name=product.name, slug=product.slug)
    del data["is_available"]  # an unchecked checkbox is simply absent

    client.post(
        reverse("products:manage_product_update", kwargs={"pk": product.pk}), data
    )

    product.refresh_from_db()
    assert not product.is_available


def test_staff_can_feature_a_product(client, staff_user, product):
    client.force_login(staff_user)
    assert not product.is_featured
    data = product_data(product.category, name=product.name, slug=product.slug)
    data["is_featured"] = "on"

    client.post(
        reverse("products:manage_product_update", kwargs={"pk": product.pk}), data
    )

    product.refresh_from_db()
    assert product.is_featured


def test_staff_can_delete_a_product(client, staff_user, product):
    client.force_login(staff_user)

    response = client.post(
        reverse("products:manage_product_delete", kwargs={"pk": product.pk})
    )

    assert response.url == reverse("products:manage_products")
    assert not Product.objects.exists()


def test_manage_list_shows_unavailable_products(
    client, staff_user, unavailable_product
):
    client.force_login(staff_user)

    page = client.get(reverse("products:manage_products")).content.decode()

    assert unavailable_product.name in page
    assert "Unavailable" in page


# --- Image validation --------------------------------------------------------

UNUSABLE = "This file isn't a usable image. Upload a PNG, JPEG, or WebP file."
TOO_SMALL = (
    "This image is 300×200 pixels. "
    "Product images must be at least 400 pixels on each side."
)
WRONG_FORMAT = "This is a GIF image. Product images must be PNG, JPEG, or WebP."
BOMB = "This image's dimensions are too large to process."

BAD_UPLOADS = {
    "renamed-text": (lambda: SimpleUploadedFile("notes.png", b"Just notes."), UNUSABLE),
    "too-small": (lambda: make_image_upload(size=(300, 200)), TOO_SMALL),
    "gif": (lambda: make_image_upload(name="a.gif", image_format="GIF"), WRONG_FORMAT),
}


@pytest.mark.parametrize("kind", BAD_UPLOADS)
def test_backoffice_rejects_bad_uploads_readably(
    client, staff_user, category, media_root, kind
):
    build_upload, message = BAD_UPLOADS[kind]
    client.force_login(staff_user)
    data = product_data(category, image=build_upload())

    response = client.post(reverse("products:manage_product_create"), data)

    assert response.status_code == HTTPStatus.OK
    page = response.content.decode()
    assert escape(message) in page
    assert 'value="MindSync Sleep Halo"' in page  # the rest of the input survives
    assert not Product.objects.exists()


def test_backoffice_names_a_decompression_bomb(
    client, staff_user, category, media_root, monkeypatch
):
    """Even when Pillow refuses outright, the bomb gets its own message."""
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100_000)
    client.force_login(staff_user)
    data = product_data(category, image=make_image_upload(size=(600, 800)))

    response = client.post(reverse("products:manage_product_create"), data)

    assert response.status_code == HTTPStatus.OK
    assert escape(BOMB) in response.content.decode()
    assert not Product.objects.exists()


@pytest.mark.parametrize("kind", ["renamed-text", "gif"])
def test_admin_rejects_bad_uploads_with_the_same_messages(
    admin_client, product, media_root, kind
):
    build_upload, message = BAD_UPLOADS[kind]
    data = product_data(product.category, name=product.name, slug=product.slug)
    data["image"] = build_upload()

    response = admin_client.post(
        reverse("admin:products_product_change", args=[product.pk]), data
    )

    assert response.status_code == HTTPStatus.OK
    assert escape(message) in response.content.decode()
    product.refresh_from_db()
    assert not product.image


@pytest.mark.parametrize(
    "url_name", ["products:manage_product_create", "admin:products_product_add"]
)
def test_file_picker_offers_only_accepted_formats(admin_client, url_name):
    page = admin_client.get(reverse(url_name)).content.decode()

    assert 'accept="image/png,image/jpeg,image/webp"' in page


# --- Image preview, thumbnails, and the full cycle ---------------------------

PLACEHOLDER_NOTE = "No image — showing the category placeholder."


def edit_page(client, product):
    return client.get(
        reverse("products:manage_product_update", kwargs={"pk": product.pk})
    ).content.decode()


def test_edit_page_previews_the_placeholder_with_a_note(client, staff_user, product):
    client.force_login(staff_user)

    page = edit_page(client, product)

    assert product.display_image_url in page
    assert PLACEHOLDER_NOTE in page


def test_edit_page_previews_the_stored_image(
    client, staff_user, product, media_root, image_upload
):
    product.image = image_upload
    product.save()
    client.force_login(staff_user)

    page = edit_page(client, product)

    assert product.image.url in page
    assert PLACEHOLDER_NOTE not in page


def test_preview_after_a_rejected_upload_shows_what_is_stored(
    client, staff_user, product, media_root
):
    """A refused GIF never appears as the "current" image."""
    client.force_login(staff_user)
    data = product_data(product.category, name=product.name, slug=product.slug)
    data["image"] = make_image_upload(name="refused.gif", image_format="GIF")

    response = client.post(
        reverse("products:manage_product_update", kwargs={"pk": product.pk}), data
    )

    page = response.content.decode()
    assert escape(WRONG_FORMAT) in page
    assert "refused" not in page
    assert product.display_image_url in page
    assert PLACEHOLDER_NOTE in page


def test_create_page_has_no_preview(client, staff_user, category):
    client.force_login(staff_user)

    page = client.get(reverse("products:manage_product_create")).content.decode()

    assert PLACEHOLDER_NOTE not in page


def test_list_shows_a_thumbnail_per_product(
    client, staff_user, product, unavailable_product, media_root, image_upload
):
    product.image = image_upload
    product.save()
    client.force_login(staff_user)

    page = client.get(reverse("products:manage_products")).content.decode()

    assert page.count('width="48" height="48"') == 2
    assert product.image.url in page
    assert unavailable_product.display_image_url in page  # the placeholder


def test_staff_upload_replace_and_clear_cycle(
    client, staff_user, product, media_root, django_capture_on_commit_callbacks
):
    client.force_login(staff_user)
    url = reverse("products:manage_product_update", kwargs={"pk": product.pk})
    base = product_data(product.category, name=product.name, slug=product.slug)

    with django_capture_on_commit_callbacks(execute=True):
        client.post(url, {**base, "image": make_image_upload()})
        product.refresh_from_db()
        first = product.image.name

        client.post(url, {**base, "image": make_image_upload(size=(900, 500))})
        product.refresh_from_db()
        second = product.image.name

        client.post(url, {**base, "image-clear": "on"})
        product.refresh_from_db()

    assert first != second
    assert not product.image
    assert list((media_root / "products").iterdir()) == []
    assert PLACEHOLDER_NOTE in edit_page(client, product)


def test_admin_upload_is_validated_and_processed(admin_client, product, media_root):
    data = product_data(product.category, name=product.name, slug=product.slug)
    data["image"] = make_image_upload(size=(1200, 600))

    response = admin_client.post(
        reverse("admin:products_product_change", args=[product.pk]), data
    )

    assert response.status_code == HTTPStatus.FOUND
    product.refresh_from_db()
    assert product.image.name == "products/seraphine-home-hub.webp"
    with Image.open(media_root / product.image.name) as stored:
        assert (stored.format, stored.size) == ("WEBP", (800, 800))


def test_admin_add_form_processes_too(admin_client, category, media_root):
    data = product_data(category, image=make_image_upload())

    response = admin_client.post(reverse("admin:products_product_add"), data)

    assert response.status_code == HTTPStatus.FOUND
    product = Product.objects.get(slug="mindsync-sleep-halo")
    assert product.image.name.endswith(".webp")


# --- Form validation ---------------------------------------------------------


def test_price_must_be_positive(client, staff_user, category):
    client.force_login(staff_user)

    response = client.post(
        reverse("products:manage_product_create"),
        product_data(category, price="-12.00"),
    )

    assert response.status_code == HTTPStatus.OK
    assert "greater than or equal to 0.01" in response.content.decode()
    assert not Product.objects.exists()


def test_slug_must_be_unique(client, staff_user, product):
    client.force_login(staff_user)

    response = client.post(
        reverse("products:manage_product_create"),
        product_data(product.category, slug=product.slug),
    )

    assert response.status_code == HTTPStatus.OK
    assert "already exists" in response.content.decode()
    assert Product.objects.count() == 1


def test_name_is_required(client, staff_user, category):
    client.force_login(staff_user)

    response = client.post(
        reverse("products:manage_product_create"), product_data(category, name="")
    )

    assert response.status_code == HTTPStatus.OK
    assert "This field is required." in response.content.decode()
    assert not Product.objects.exists()


# --- Categories and tags -----------------------------------------------------


def test_staff_can_create_and_edit_a_category(client, staff_user):
    client.force_login(staff_user)

    client.post(
        reverse("products:manage_category_create"),
        {"name": "Defense", "slug": "defense"},
    )
    category = Category.objects.get(slug="defense")

    client.post(
        reverse("products:manage_category_update", kwargs={"pk": category.pk}),
        {"name": "Home Defense", "slug": "defense"},
    )

    category.refresh_from_db()
    assert category.name == "Home Defense"


def test_staff_can_create_and_edit_a_tag(client, staff_user):
    client.force_login(staff_user)

    client.post(
        reverse("products:manage_tag_create"),
        {"name": "new arrival", "slug": "new-arrival"},
    )
    tag = Tag.objects.get(slug="new-arrival")

    client.post(
        reverse("products:manage_tag_update", kwargs={"pk": tag.pk}),
        {"name": "just landed", "slug": "new-arrival"},
    )

    tag.refresh_from_db()
    assert tag.name == "just landed"


def test_manage_catalog_lists_categories_and_tags(client, staff_user, product, tag):
    client.force_login(staff_user)

    page = client.get(reverse("products:manage_catalog")).content.decode()

    assert product.category.name in page
    assert tag.name in page
