"""The checkout form — the codebase's showcase of declarative validation.

Every rule is visible at its field declaration, in the style of data
annotations: field types validate (``EmailField``), field arguments
validate (``required``, ``max_length``, ``ChoiceField``), and the
``validators=[...]`` list carries the rest. No ``clean_*`` methods
and no ``clean()`` — none of its current rules need imperative validation.

``CouponForm`` is the back office's coupon editor; its cross-field
rules (dates in order, scope matches products) do need ``clean()``.
"""

from django import forms
from django.conf import settings
from django.core.validators import RegexValidator

from accounts.models import US_STATES, zip_validator
from products.forms import StyledModelForm
from products.models import Product

from .models import Coupon, Order
from .validators import validate_card_number, validate_expiry

cvv_validator = RegexValidator(r"^\d{3,4}$", "Enter the 3- or 4-digit CVV.")

SAVE_LABEL = "Save this address to my account"


class CheckoutForm(forms.Form):
    """One page, one POST: contact, shipping, billing, payment."""

    email = forms.EmailField(label="Email")

    shipping_name = forms.CharField(label="Full name", max_length=100)
    shipping_street = forms.CharField(label="Street address", max_length=200)
    shipping_line2 = forms.CharField(
        label="Apt, suite, etc. (optional)", max_length=200, required=False
    )
    shipping_city = forms.CharField(label="City", max_length=100)
    shipping_state = forms.ChoiceField(label="State", choices=US_STATES)
    shipping_zip = forms.CharField(
        label="ZIP code", max_length=10, validators=[zip_validator]
    )
    save_shipping = forms.BooleanField(label=SAVE_LABEL, required=False)

    billing_name = forms.CharField(label="Full name", max_length=100)
    billing_street = forms.CharField(label="Street address", max_length=200)
    billing_line2 = forms.CharField(
        label="Apt, suite, etc. (optional)", max_length=200, required=False
    )
    billing_city = forms.CharField(label="City", max_length=100)
    billing_state = forms.ChoiceField(label="State", choices=US_STATES)
    billing_zip = forms.CharField(
        label="ZIP code", max_length=10, validators=[zip_validator]
    )
    save_billing = forms.BooleanField(label=SAVE_LABEL, required=False)

    card_number = forms.CharField(
        label="Card number", max_length=23, validators=[validate_card_number]
    )
    card_expiry = forms.CharField(
        label="Expiry (MM/YY)", max_length=5, validators=[validate_expiry]
    )
    card_cvv = forms.CharField(label="CVV", max_length=4, validators=[cvv_validator])

    # Optional. Whether the code is usable depends on the cart and the
    # clock, so ``place_order`` judges it, not the form.
    coupon_code = forms.CharField(label="Promo code", max_length=30, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = "checkbox checkbox-sm"
            elif isinstance(widget, forms.Select):
                widget.attrs["class"] = "select w-full"
            else:
                widget.attrs["class"] = "input w-full"

    # Field groups for the template — the form owns its own structure.

    def address_fields(self, section):
        """One address section's fields — ``"shipping"`` or ``"billing"``."""
        return [self[name] for name in self.fields if name.startswith(f"{section}_")]

    def shipping_fields(self):
        return self.address_fields("shipping")

    def billing_fields(self):
        return self.address_fields("billing")

    def card_fields(self):
        return [self[name] for name in self.fields if name.startswith("card_")]


DATETIME_FORMAT = "%Y-%m-%dT%H:%M"


class CouponForm(StyledModelForm):
    """Create and edit coupons in the back office.

    Codes are normalized (trimmed, uppercased) before the model's own
    validators and uniqueness check run. Once any order has used the
    coupon, the deal itself — percent, scope, products — is locked:
    those fields are disabled, so Django ignores whatever is posted for
    them. Dates, the active switch, and the note stay editable.
    """

    LOCKED_ONCE_USED = ("percent_off", "scope", "products")

    class Meta:
        model = Coupon
        fields = [
            "code",
            "description",
            "percent_off",
            "scope",
            "products",
            "starts_at",
            "expires_at",
            "is_active",
        ]
        widgets = {
            "starts_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format=DATETIME_FORMAT
            ),
            "expires_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format=DATETIME_FORMAT
            ),
        }
        labels = {
            "starts_at": f"Starts at ({settings.TIME_ZONE})",
            "expires_at": f"Expires at ({settings.TIME_ZONE})",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["products"].queryset = Product.objects.order_by("name")
        self.fields["expires_at"].help_text = "The coupon stops working at this moment."
        self.locked = bool(self.instance.pk and self.instance.is_used)
        if self.locked:
            for name in self.LOCKED_ONCE_USED:
                self.fields[name].disabled = True
                self.fields[name].help_text = (
                    "Locked — orders have used this coupon. "
                    "To change the deal, create a new coupon."
                )

    def clean_code(self):
        return Coupon.normalize_code(self.cleaned_data["code"])

    def clean(self):
        cleaned = super().clean()
        starts_at = cleaned.get("starts_at")
        expires_at = cleaned.get("expires_at")
        if starts_at and expires_at and expires_at <= starts_at:
            self.add_error("expires_at", "The expiry must come after the start.")
        if not self.locked:
            scope = cleaned.get("scope")
            products = cleaned.get("products")
            if scope == Coupon.Scope.PRODUCTS and not products:
                self.add_error("products", "Pick at least one product.")
            if scope == Coupon.Scope.ORDER and products:
                self.add_error(
                    "products",
                    "A whole-order coupon can't target products — "
                    "clear these or switch to “Specific products”.",
                )
        return cleaned


class OrderStatusForm(forms.ModelForm):
    """The back-office status dropdown — any of the four states, anytime.

    Guarding the workflow (no un-cancelling, no re-shipping a delivered
    order) is deliberately left as a student exercise.
    """

    class Meta:
        model = Order
        fields = ["status"]
        widgets = {"status": forms.Select(attrs={"class": "select"})}
