"""Saved addresses: the model's rules and the address book pages."""

from http import HTTPStatus

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.urls import reverse

from .models import Address

WORK = {
    "name": "Casey Monroe",
    "street": "77 Cortex Lane",
    "line2": "Suite 300",
    "city": "Amarillo",
    "state": "TX",
    "zip": "79101",
}


@pytest.fixture
def other_customer(db):
    return get_user_model().objects.create_user(username="other", password="x")


# --- The model ----------------------------------------------------------------


def test_a_first_address_becomes_the_default(address):
    assert address.is_default


def test_later_addresses_are_not_the_default(customer, address):
    work = Address.objects.create(user=customer, **WORK)

    assert not work.is_default


def test_make_default_moves_the_flag(customer, address):
    work = Address.objects.create(user=customer, **WORK)

    work.make_default()

    address.refresh_from_db()
    assert work.is_default
    assert not address.is_default


def test_the_database_allows_one_default_per_user(customer, address):
    with pytest.raises(IntegrityError):
        Address.objects.create(user=customer, is_default=True, **WORK)


def test_deleting_the_default_promotes_nothing(customer, address):
    Address.objects.create(user=customer, **WORK)

    address.delete()

    assert not Address.objects.filter(user=customer, is_default=True).exists()


def test_save_for_skips_an_exact_match(customer, address):
    data = {name: getattr(address, name) for name in Address.FIELDS}

    found, created = Address.objects.save_for(customer, data)

    assert not created
    assert found == address
    assert Address.objects.count() == 1


def test_save_for_creates_a_new_address(customer, address):
    saved, created = Address.objects.save_for(customer, WORK)

    assert created
    assert saved.street == "77 Cortex Lane"
    assert Address.objects.count() == 2


def test_save_for_does_not_match_another_users_address(other_customer, address):
    data = {name: getattr(address, name) for name in Address.FIELDS}

    _, created = Address.objects.save_for(other_customer, data)

    assert created


def test_as_initial_and_fields_from_round_trip(address):
    initial = address.as_initial("billing")

    assert initial["billing_street"] == "214 Synapse Street"
    assert initial["billing_zip"] == "79015"
    assert Address.fields_from(initial, "billing") == {
        name: getattr(address, name) for name in Address.FIELDS
    }


def test_str_leads_with_the_label(customer, address):
    unlabeled = Address.objects.create(user=customer, **WORK)

    assert str(address) == "Home — 214 Synapse Street, Canyon, TX 79015"
    assert str(unlabeled) == "77 Cortex Lane, Amarillo, TX 79101"


# --- The address book pages -----------------------------------------------------


def test_the_address_book_requires_login(client, db):
    response = client.get(reverse("accounts:addresses"))

    assert response.status_code == HTTPStatus.FOUND
    assert reverse("accounts:login") in response.url


def test_an_empty_address_book_has_a_designed_empty_state(client, customer):
    client.force_login(customer)

    page = client.get(reverse("accounts:addresses")).content.decode()

    assert "No saved addresses yet" in page


def test_the_address_book_lists_only_your_addresses(client, other_customer, address):
    Address.objects.create(user=other_customer, **WORK)
    client.force_login(address.user)

    page = client.get(reverse("accounts:addresses")).content.decode()

    assert "214 Synapse Street" in page
    assert "77 Cortex Lane" not in page


def test_adding_an_address(client, customer):
    client.force_login(customer)

    response = client.post(
        reverse("accounts:address_create"), {"label": "Work", **WORK}
    )

    assert response.status_code == HTTPStatus.FOUND
    saved = Address.objects.get()
    assert saved.user == customer
    assert saved.is_default  # the first one


def test_adding_an_invalid_address_shows_field_errors(client, customer):
    client.force_login(customer)

    response = client.post(reverse("accounts:address_create"), {**WORK, "zip": "790"})

    assert response.status_code == HTTPStatus.OK
    assert response.context["form"].errors["zip"]
    assert not Address.objects.exists()


def test_editing_an_address(client, address):
    client.force_login(address.user)

    client.post(reverse("accounts:address_update", args=[address.pk]), WORK)

    address.refresh_from_db()
    assert address.street == "77 Cortex Lane"


def test_deleting_an_address(client, address):
    client.force_login(address.user)

    client.post(reverse("accounts:address_delete", args=[address.pk]))

    assert not Address.objects.exists()


def test_making_an_address_the_default(client, customer, address):
    work = Address.objects.create(user=customer, **WORK)
    client.force_login(customer)

    client.post(reverse("accounts:address_default", args=[work.pk]))

    work.refresh_from_db()
    assert work.is_default


@pytest.mark.parametrize(
    ("name", "method"),
    [
        ("accounts:address_update", "get"),
        ("accounts:address_delete", "post"),
        ("accounts:address_default", "post"),
    ],
)
def test_another_customers_address_is_a_404(
    client, other_customer, address, name, method
):
    client.force_login(other_customer)

    response = getattr(client, method)(reverse(name, args=[address.pk]))

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert Address.objects.filter(pk=address.pk, is_default=True).exists()


def test_the_navbar_links_to_the_address_book(client, customer):
    client.force_login(customer)

    page = client.get(reverse("products:catalog")).content.decode()

    assert reverse("accounts:addresses") in page
