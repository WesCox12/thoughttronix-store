"""Project-wide pytest fixtures.

Shared test data lives here as plain fixtures — no factories. The suite
grows with the project; only tests specifically verifying seed behavior
may invoke the seed command.
"""

from decimal import Decimal
from io import BytesIO

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from accounts.models import Address
from orders.models import Cart, CartItem
from products.models import Category, Product, Tag


@pytest.fixture
def customer(db):
    return get_user_model().objects.create_user(
        username="customer", password="customer123"
    )


@pytest.fixture
def address(customer):
    """The customer's first saved address — and so their default."""
    return Address.objects.create(
        user=customer,
        label="Home",
        name="Casey Monroe",
        street="214 Synapse Street",
        city="Canyon",
        state="TX",
        zip="79015",
    )


@pytest.fixture
def staff_user(db):
    return get_user_model().objects.create_user(
        username="employee",
        password="employee123",
        is_staff=True,
        job_title="Junior Thought Curator",
    )


@pytest.fixture
def category(db):
    return Category.objects.create(name="Home Assistants", slug="home-assistants")


@pytest.fixture
def product(category):
    return Product.objects.create(
        name="Seraphine Home Hub",
        slug="seraphine-home-hub",
        tagline="She's always listening. In a good way.",
        description="The flagship Seraphine hub with a seven-microphone array.",
        price=Decimal("349.99"),
        category=category,
    )


@pytest.fixture
def unavailable_product(category):
    return Product.objects.create(
        name="EchoPatch",
        slug="echopatch",
        tagline="Never miss a word. Anyone's.",
        price=Decimal("139.00"),
        is_available=False,
        category=category,
    )


@pytest.fixture
def tag(db):
    return Tag.objects.create(name="bestseller", slug="bestseller")


@pytest.fixture
def media_root(settings, tmp_path):
    """Point MEDIA_ROOT at a temporary folder so tests never write to ``media/``."""
    settings.MEDIA_ROOT = tmp_path / "media"
    return settings.MEDIA_ROOT


def make_image_upload(
    name="upload.png", size=(600, 800), image_format="PNG", color="#c0ffee"
):
    """An in-memory image upload built with Pillow — no binary fixtures."""
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format=image_format)
    content_type = f"image/{image_format.lower()}"
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=content_type)


@pytest.fixture
def image_upload():
    """A valid 600×800 PNG upload; call ``make_image_upload`` for variants."""
    return make_image_upload()


@pytest.fixture
def cart(customer):
    return Cart.for_user(customer)


@pytest.fixture
def cart_item(cart, product):
    return CartItem.objects.create(cart=cart, product=product, quantity=2)
