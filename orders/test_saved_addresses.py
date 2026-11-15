"""Saved addresses at checkout: prefill, the HTMX picker, and saving."""

from http import HTTPStatus

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from accounts.models import Address
from products.models import Product

from .models import Order, OrderItem
from .services import place_order
from .test_checkout_form import VALID_DATA

# --- Prefill ------------------------------------------------------------------


def test_checkout_prefills_both_sections_from_the_default(client, address, cart_item):
    client.force_login(address.user)

    form = client.get(reverse("orders:checkout")).context["form"]

    assert form.initial["shipping_street"] == "214 Synapse Street"
    assert form.initial["billing_zip"] == "79015"


def test_save_starts_ticked_for_an_empty_address_book(client, customer, cart_item):
    client.force_login(customer)

    form = client.get(reverse("orders:checkout")).context["form"]

    assert form.initial["save_shipping"] is True
    assert form.initial["save_billing"] is True
    assert "shipping_street" not in form.initial


def test_save_starts_unticked_once_addresses_exist(client, address, cart_item):
    client.force_login(address.user)

    form = client.get(reverse("orders:checkout")).context["form"]

    assert form.initial["save_shipping"] is False
    assert form.initial["save_billing"] is False


def test_the_picker_lists_saved_addresses(client, address, cart_item):
    client.force_login(address.user)

    page = client.get(reverse("orders:checkout")).content.decode()

    assert "Use a saved address" in page
    assert reverse("orders:checkout_address", args=["shipping"]) in page


def test_no_picker_without_saved_addresses(client, customer, cart_item):
    client.force_login(customer)

    page = client.get(reverse("orders:checkout")).content.decode()

    assert "Use a saved address" not in page


# --- The HTMX picker endpoint ----------------------------------------------------


def test_the_picker_returns_the_section_filled_in(client, address):
    client.force_login(address.user)

    response = client.get(
        reverse("orders:checkout_address", args=["billing"]),
        {"address": address.pk},
    )

    assert response.status_code == HTTPStatus.OK
    page = response.content.decode()
    assert 'name="billing_street"' in page
    assert 'value="214 Synapse Street"' in page
    assert "shipping_" not in page
    assert "<html" not in page  # a partial, never base.html


def test_an_empty_pick_returns_the_section_blank(client, address):
    client.force_login(address.user)

    response = client.get(
        reverse("orders:checkout_address", args=["shipping"]), {"address": ""}
    )

    page = response.content.decode()
    assert 'name="shipping_street"' in page
    assert "214 Synapse Street" not in page


def test_another_customers_address_is_a_404(client, address):
    other = get_user_model().objects.create_user(username="other", password="x")
    client.force_login(other)

    response = client.get(
        reverse("orders:checkout_address", args=["shipping"]),
        {"address": address.pk},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.parametrize(
    ("section", "pk"), [("payment", ""), ("shipping", "abc"), ("shipping", "999")]
)
def test_bad_picker_requests_are_a_404(client, customer, section, pk):
    client.force_login(customer)

    response = client.get(
        reverse("orders:checkout_address", args=[section]), {"address": pk}
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_the_picker_requires_login(client, db):
    response = client.get(reverse("orders:checkout_address", args=["shipping"]))

    assert response.status_code == HTTPStatus.FOUND


# --- Saving through place_order ----------------------------------------------------


def test_ticked_addresses_are_saved(cart, cart_item):
    data = {
        **VALID_DATA,
        "billing_street": "77 Cortex Lane",
        "save_shipping": True,
        "save_billing": True,
    }

    place_order(cart, cart.user, data)

    shipping, billing = Address.objects.filter(user=cart.user).order_by("pk")
    assert shipping.street == "12 Cortex Lane"
    assert shipping.line2 == "Unit 7"
    assert shipping.is_default  # shipping is saved first
    assert billing.street == "77 Cortex Lane"
    assert not billing.is_default


def test_unticked_or_missing_flags_save_nothing(cart, cart_item):
    place_order(cart, cart.user, {**VALID_DATA, "save_shipping": False})

    assert not Address.objects.exists()


def test_the_same_address_ticked_twice_is_saved_once(cart, cart_item):
    same = {**VALID_DATA, "billing_line2": "Unit 7", "billing_zip": "79015"}

    place_order(cart, cart.user, {**same, "save_shipping": True, "save_billing": True})

    assert Address.objects.count() == 1


def test_a_failed_order_saves_no_address(cart, cart_item, category, monkeypatch):
    cart.add(
        Product.objects.create(
            name="Charging Pillow", slug="charging-pillow", price=69, category=category
        )
    )
    original = OrderItem.objects.create
    calls = {"count": 0}

    def create_then_explode(**kwargs):
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("boom")
        return original(**kwargs)

    monkeypatch.setattr(OrderItem.objects, "create", create_then_explode)

    with pytest.raises(RuntimeError):
        place_order(cart, cart.user, {**VALID_DATA, "save_shipping": True})

    assert not Order.objects.exists()
    assert not Address.objects.exists()


def test_editing_a_saved_address_leaves_the_order_alone(client, customer, cart_item):
    client.force_login(customer)
    client.post(reverse("orders:checkout"), {**VALID_DATA, "save_shipping": "on"})
    saved = Address.objects.get(user=customer)

    saved.street = "1 New Street"
    saved.save()

    assert Order.objects.get().shipping_street == "12 Cortex Lane"
