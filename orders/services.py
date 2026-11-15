"""Order placement — one of the codebase's two deliberate deep modules.

The interface is the product: ``place_order`` turns a cart and a
validated checkout into an order, all-or-nothing, and ``quote_cart``
prices a cart (with an optional coupon) exactly the way ``place_order``
will — so the checkout preview and the placed order can never disagree.
Callers never touch ``Order`` construction or discount math directly.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction

from accounts.models import Address

from .models import Cart, CartItem, Coupon, InvalidCoupon, Order, OrderItem

__all__ = ["InvalidCoupon", "PricedLine", "Quote", "place_order", "quote_cart"]

ZERO = Decimal("0.00")

ADDRESS_FIELDS = [
    "email",
    "shipping_name",
    "shipping_street",
    "shipping_line2",
    "shipping_city",
    "shipping_state",
    "shipping_zip",
    "billing_name",
    "billing_street",
    "billing_line2",
    "billing_city",
    "billing_state",
    "billing_zip",
]


@dataclass(frozen=True)
class PricedLine:
    """One cart line with its share of the coupon's discount."""

    item: CartItem
    discount: Decimal

    @property
    def subtotal(self) -> Decimal:
        return self.item.line_total

    @property
    def total(self) -> Decimal:
        return self.subtotal - self.discount


@dataclass(frozen=True)
class Quote:
    """A cart's price with an optional coupon applied.

    ``discount`` is the sum of the lines' discounts, so the numbers
    always reconcile: ``total == subtotal - discount``.
    """

    lines: list[PricedLine]
    coupon: Coupon | None
    subtotal: Decimal
    discount: Decimal
    total: Decimal


def quote_cart(cart: Cart, coupon_code: str | None = None) -> Quote:
    """Price the cart, applying ``coupon_code`` if one is given.

    A blank or missing code means no coupon. A whole-order coupon
    discounts every line; a specific-products coupon discounts only its
    products' lines (every unit on them). Each line's discount is
    ``line_total × percent_off / 100``, rounded half-up to the cent.

    Raises ``InvalidCoupon`` — with a message safe to show the customer —
    if the code is unknown, retired, not yet started, expired, or targets
    none of the products in the cart.
    """
    items = list(cart.lines())
    coupon = None
    if Coupon.normalize_code(coupon_code):
        coupon = Coupon.objects.redeemable(
            coupon_code, [item.product_id for item in items]
        )

    targets = None
    if coupon is not None and coupon.scope == Coupon.Scope.PRODUCTS:
        targets = coupon.target_ids()

    lines = []
    for item in items:
        eligible = coupon is not None and (
            targets is None or item.product_id in targets
        )
        discount = coupon.discount_on(item.line_total) if eligible else ZERO
        lines.append(PricedLine(item=item, discount=discount))

    subtotal = sum((line.subtotal for line in lines), ZERO)
    discount = sum((line.discount for line in lines), ZERO)
    return Quote(
        lines=lines,
        coupon=coupon,
        subtotal=subtotal,
        discount=discount,
        total=subtotal - discount,
    )


@transaction.atomic
def place_order(
    cart: Cart,
    user: AbstractBaseUser,
    checkout_data: Mapping[str, Any],
    *,
    coupon_code: str | None = None,
) -> Order:
    """Create an order from the cart's contents, then empty the cart.

    ``checkout_data`` is the ``cleaned_data`` of a valid ``CheckoutForm``.
    Addresses and line prices are denormalized onto the order — an order
    is a snapshot, immune to later catalog or address edits. Of the card,
    only the last four digits are stored; the full number and CVV never
    touch the database.

    When ``save_shipping`` or ``save_billing`` is true in
    ``checkout_data``, that section's address is saved to the user's
    address book (shipping first), skipping any address the book already
    holds verbatim. Missing flags count as false.

    ``coupon_code`` is priced by ``quote_cart`` — the same math the
    checkout preview showed. The coupon, its normalized code, and each
    line's discount are snapshotted onto the order, so later edits to
    or retirement of the coupon never change it. The code is checked
    again here, at placement time: a coupon that expired or was retired
    after the customer applied it is caught, not silently honored.

    All-or-nothing: runs in a transaction, so a failure partway through
    leaves no partial order, no newly saved address, and the cart intact.

    Raises ``ValueError`` if the cart is empty or holds a product that is
    no longer available, and ``InvalidCoupon`` (a ``ValueError``) if the
    coupon can't be used — the order is never placed at a price other
    than the one quoted.
    """
    items = list(cart.lines())
    if not items:
        raise ValueError("Cannot place an order from an empty cart.")
    unavailable = [item.product.name for item in items if not item.product.is_available]
    if unavailable:
        raise ValueError(
            f"No longer available: {', '.join(unavailable)}. "
            "Remove them from the cart to check out."
        )

    quote = quote_cart(cart, coupon_code)
    card_digits = checkout_data["card_number"].replace(" ", "").replace("-", "")
    order = Order.objects.create(
        user=user,
        subtotal=quote.subtotal,
        discount=quote.discount,
        total=quote.total,
        coupon=quote.coupon,
        coupon_code=quote.coupon.code if quote.coupon else "",
        card_last4=card_digits[-4:],
        **{name: checkout_data[name] for name in ADDRESS_FIELDS},
    )
    for line in quote.lines:
        OrderItem.objects.create(
            order=order,
            product=line.item.product,
            product_name=line.item.product.name,
            unit_price=line.item.product.price,
            quantity=line.item.quantity,
            discount=line.discount,
        )
    for section in ("shipping", "billing"):
        if checkout_data.get(f"save_{section}"):
            Address.objects.save_for(user, Address.fields_from(checkout_data, section))
    cart.items.all().delete()
    return order
