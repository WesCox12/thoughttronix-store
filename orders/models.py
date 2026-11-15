from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.validators import (
    MaxValueValidator,
    MinValueValidator,
    RegexValidator,
)
from django.db import models
from django.utils import dateformat, timezone

from products.models import Product

CENT = Decimal("0.01")

code_validator = RegexValidator(
    r"^[A-Z0-9_-]{3,30}$",
    "Use 3–30 letters, digits, hyphens, or underscores.",
)


class InvalidCoupon(ValueError):
    """A coupon code that can't be used on this cart right now.

    The message is customer-facing — safe to show under the code box.
    """


class CouponQuerySet(models.QuerySet):
    """Filters matching ``Coupon.status`` — retired outranks the dates."""

    def retired(self):
        return self.filter(is_active=False)

    def scheduled(self, now=None):
        return self.filter(is_active=True, starts_at__gt=now or timezone.now())

    def expired(self, now=None):
        return self.filter(is_active=True, expires_at__lte=now or timezone.now())

    def active(self, now=None):
        now = now or timezone.now()
        return self.filter(is_active=True, starts_at__lte=now, expires_at__gt=now)

    def with_status(self, status, now=None):
        """Filter by a ``Coupon.Status`` value; anything else is a no-op."""
        method = {
            Coupon.Status.ACTIVE: self.active,
            Coupon.Status.SCHEDULED: self.scheduled,
            Coupon.Status.EXPIRED: self.expired,
        }.get(status)
        if method:
            return method(now)
        if status == Coupon.Status.RETIRED:
            return self.retired()
        return self

    def redeemable(self, code, product_ids, now=None):
        """The coupon behind ``code``, if it can discount these products now.

        ``code`` is normalized first (trimmed, uppercased). Raises
        ``InvalidCoupon`` with a customer-facing message otherwise.
        Unknown, retired, and not-yet-started codes share one message —
        guessing codes reveals nothing about which exist.
        """
        code = Coupon.normalize_code(code)
        now = now or timezone.now()
        coupon = self.filter(code=code).first()
        if coupon is None or not coupon.is_active or coupon.starts_at > now:
            raise InvalidCoupon(
                f"We don't recognize the code {code}. Check it for typos."
            )
        if coupon.expires_at <= now:
            expired_on = dateformat.format(
                timezone.localtime(coupon.expires_at), "M j, Y"
            )
            raise InvalidCoupon(f"{code} expired on {expired_on}.")
        if coupon.scope == Coupon.Scope.PRODUCTS:
            targets = coupon.target_ids()
            if not targets & set(product_ids):
                names = list(coupon.products.values_list("name", flat=True))
                if not names:
                    raise InvalidCoupon(
                        f"{code} was for products we no longer sell."
                    )
                raise InvalidCoupon(
                    f"{code} applies only to {' or '.join(names)} — "
                    "add it to your cart to use this code."
                )
        return coupon


class Coupon(models.Model):
    """A percentage-off promotion code, for the whole order or chosen products.

    Orders snapshot their discount, so editing, retiring, or expiring a
    coupon never changes a placed order's totals. A coupon any order has
    used is protected from deletion — retire it instead.
    """

    class Scope(models.TextChoices):
        ORDER = "ORDER", "Whole order"
        PRODUCTS = "PRODUCTS", "Specific products"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        SCHEDULED = "SCHEDULED", "Scheduled"
        EXPIRED = "EXPIRED", "Expired"
        RETIRED = "RETIRED", "Retired"

    code = models.CharField(
        max_length=30,
        unique=True,
        validators=[code_validator],
        help_text="What customers type at checkout. Not case-sensitive.",
    )
    description = models.CharField(
        max_length=200,
        blank=True,
        help_text="Internal note for staff — customers never see it.",
    )
    percent_off = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="A whole number from 1 to 100.",
    )
    scope = models.CharField(
        "Applies to", max_length=10, choices=Scope.choices, default=Scope.ORDER
    )
    products = models.ManyToManyField(
        Product,
        blank=True,
        related_name="coupons",
        help_text="Only for “Specific products”. Ctrl/Cmd-click to pick several.",
    )
    starts_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(
        "Active",
        default=True,
        help_text="Untick to retire the coupon. You can reactivate it later.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = CouponQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(percent_off__gte=1, percent_off__lte=100),
                name="coupon_percent_off_1_to_100",
            ),
            models.CheckConstraint(
                condition=models.Q(expires_at__gt=models.F("starts_at")),
                name="coupon_expires_after_start",
            ),
        ]

    def __str__(self):
        return self.code

    @staticmethod
    def normalize_code(code):
        """Codes match case-insensitively: trimmed and uppercased."""
        return (code or "").strip().upper()

    def save(self, *args, **kwargs):
        self.code = self.normalize_code(self.code)
        super().save(*args, **kwargs)

    @property
    def status(self):
        now = timezone.now()
        if not self.is_active:
            return self.Status.RETIRED
        if self.starts_at > now:
            return self.Status.SCHEDULED
        if self.expires_at <= now:
            return self.Status.EXPIRED
        return self.Status.ACTIVE

    @property
    def is_used(self):
        return self.orders.exists()

    def target_ids(self):
        """Primary keys of the targeted products (empty for whole-order)."""
        return set(self.products.values_list("pk", flat=True))

    def discount_on(self, amount):
        """This coupon's discount on ``amount``, rounded half-up to the cent."""
        return (amount * self.percent_off / 100).quantize(CENT, ROUND_HALF_UP)


class Cart(models.Model):
    """A customer's cart — one per user, created lazily on first touch."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cart",
    )

    def __str__(self):
        return f"Cart for {self.user.username}"

    @classmethod
    def for_user(cls, user):
        """Return the user's cart, creating it on first touch."""
        cart, _ = cls.objects.get_or_create(user=user)
        return cart

    def add(self, product):
        """Add a product to the cart; a duplicate add increments its line."""
        item, created = self.items.get_or_create(product=product)
        if not created:
            item.quantity += 1
            item.save()
        return item

    def lines(self):
        """Line items with their products loaded, ready for display."""
        return self.items.select_related("product")

    def total(self):
        return sum((item.line_total for item in self.lines()), Decimal("0.00"))

    def item_count(self):
        """Total units across all lines — the navbar badge number."""
        return self.items.aggregate(count=models.Sum("quantity"))["count"] or 0


class CartItem(models.Model):
    """One product line in a cart; the cart–product pair is unique."""

    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["cart", "product"], name="unique_cart_product"
            )
        ]

    def __str__(self):
        return f"{self.quantity} × {self.product.name}"

    @property
    def line_total(self):
        return self.product.price * self.quantity

    def increment(self):
        self.quantity += 1
        self.save()

    def decrement(self):
        """Step the quantity down, stopping at one — removal is explicit."""
        if self.quantity > 1:
            self.quantity -= 1
            self.save()


class Order(models.Model):
    """A placed order — a snapshot, never a live view of the catalog.

    Addresses are flat denormalized fields: the order must not change if
    the customer later edits anything. Of the card, only the last four
    digits survive checkout. A coupon's effect is snapshotted the same
    way: ``coupon_code`` and the money fields are copied, so retiring
    or editing the coupon never changes this order.
    ``total == subtotal - discount``; ``discount`` is the sum of the
    lines' discounts.
    """

    class Status(models.TextChoices):
        PLACED = "PLACED", "Placed"
        SHIPPED = "SHIPPED", "Shipped"
        DELIVERED = "DELIVERED", "Delivered"
        CANCELLED = "CANCELLED", "Cancelled"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="orders",
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PLACED
    )
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    total = models.DecimalField(max_digits=10, decimal_places=2)
    coupon = models.ForeignKey(
        Coupon,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="orders",
    )
    coupon_code = models.CharField(max_length=30, blank=True)
    email = models.EmailField()

    shipping_name = models.CharField(max_length=100)
    shipping_street = models.CharField(max_length=200)
    shipping_line2 = models.CharField(max_length=200, blank=True)
    shipping_city = models.CharField(max_length=100)
    shipping_state = models.CharField(max_length=2)
    shipping_zip = models.CharField(max_length=10)

    billing_name = models.CharField(max_length=100)
    billing_street = models.CharField(max_length=200)
    billing_line2 = models.CharField(max_length=200, blank=True)
    billing_city = models.CharField(max_length=100)
    billing_state = models.CharField(max_length=2)
    billing_zip = models.CharField(max_length=10)

    card_last4 = models.CharField(max_length=4)

    # default (not auto_now_add) so the seed can backdate orders.
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.number

    @property
    def number(self):
        """The customer-facing order number, e.g. ``TT-2026-00042``."""
        return f"TT-{self.created_at.year}-{self.pk:05d}"


class OrderItem(models.Model):
    """One line of an order, priced as of purchase time.

    Name and unit price are denormalized: order history must not change
    when the catalog does. The product FK survives for linking while the
    product exists. ``discount`` is this line's share of the coupon.
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    product_name = models.CharField(max_length=200)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()
    discount = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )

    class Meta:
        ordering = ["pk"]

    def __str__(self):
        return f"{self.quantity} × {self.product_name}"

    @property
    def line_subtotal(self):
        """Full price for the line, before any coupon."""
        return self.unit_price * self.quantity

    @property
    def line_total(self):
        """What the customer paid for the line, after its discount."""
        return self.line_subtotal - self.discount
