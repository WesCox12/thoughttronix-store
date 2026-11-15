from collections.abc import Mapping
from typing import Any

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models, transaction

# US-only addressing, shared by the address book and checkout.
US_STATES = [
    ("AL", "Alabama"),
    ("AK", "Alaska"),
    ("AZ", "Arizona"),
    ("AR", "Arkansas"),
    ("CA", "California"),
    ("CO", "Colorado"),
    ("CT", "Connecticut"),
    ("DE", "Delaware"),
    ("DC", "District of Columbia"),
    ("FL", "Florida"),
    ("GA", "Georgia"),
    ("HI", "Hawaii"),
    ("ID", "Idaho"),
    ("IL", "Illinois"),
    ("IN", "Indiana"),
    ("IA", "Iowa"),
    ("KS", "Kansas"),
    ("KY", "Kentucky"),
    ("LA", "Louisiana"),
    ("ME", "Maine"),
    ("MD", "Maryland"),
    ("MA", "Massachusetts"),
    ("MI", "Michigan"),
    ("MN", "Minnesota"),
    ("MS", "Mississippi"),
    ("MO", "Missouri"),
    ("MT", "Montana"),
    ("NE", "Nebraska"),
    ("NV", "Nevada"),
    ("NH", "New Hampshire"),
    ("NJ", "New Jersey"),
    ("NM", "New Mexico"),
    ("NY", "New York"),
    ("NC", "North Carolina"),
    ("ND", "North Dakota"),
    ("OH", "Ohio"),
    ("OK", "Oklahoma"),
    ("OR", "Oregon"),
    ("PA", "Pennsylvania"),
    ("RI", "Rhode Island"),
    ("SC", "South Carolina"),
    ("SD", "South Dakota"),
    ("TN", "Tennessee"),
    ("TX", "Texas"),
    ("UT", "Utah"),
    ("VT", "Vermont"),
    ("VA", "Virginia"),
    ("WA", "Washington"),
    ("WV", "West Virginia"),
    ("WI", "Wisconsin"),
    ("WY", "Wyoming"),
]

zip_validator = RegexValidator(
    r"^\d{5}(-\d{4})?$", "Enter a ZIP code like 79016 or 79016-1234."
)


class User(AbstractUser):
    """The store's user model.

    Roles use Django's own vocabulary and nothing else: customers are
    plain users, employees are ``is_staff``, the admin is ``is_superuser``.
    """

    # Nullable per the PRD: an absent job title is unknown, not empty.
    job_title = models.CharField(max_length=150, null=True, blank=True)  # noqa: DJ001


class AddressManager(models.Manager):
    def save_for(self, user, data: Mapping[str, Any]) -> tuple["Address", bool]:
        """Save an address to ``user``'s book unless an identical one exists.

        ``data`` holds the unprefixed address fields (``Address.FIELDS``).
        Returns ``(address, created)``, the same contract as
        ``get_or_create``. The optional label isn't part of the match.
        """
        fields = {name: data[name] for name in Address.FIELDS}
        existing = self.filter(user=user, **fields).first()
        if existing:
            return existing, False
        return self.create(user=user, **fields), True


class Address(models.Model):
    """A saved address in a customer's address book.

    Untyped: any saved address can fill checkout's shipping or billing
    section. Orders copy the fields, so editing or deleting an address
    never touches order history. At most one address per user is the
    default; a user's first address becomes it automatically.
    """

    # The fields an address shares with an order's shipping_*/billing_* set.
    FIELDS = ["name", "street", "line2", "city", "state", "zip"]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="addresses",
    )
    label = models.CharField(
        max_length=50, blank=True, help_text="Optional, like “Home” or “Work”."
    )
    name = models.CharField("full name", max_length=100)
    street = models.CharField("street address", max_length=200)
    line2 = models.CharField("apt, suite, etc.", max_length=200, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2, choices=US_STATES)
    zip = models.CharField("ZIP code", max_length=10, validators=[zip_validator])
    is_default = models.BooleanField(default=False)

    objects = AddressManager()

    class Meta:
        ordering = ["-is_default", "pk"]
        verbose_name_plural = "addresses"
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(is_default=True),
                name="one_default_address_per_user",
            )
        ]

    def __str__(self):
        place = f"{self.street}, {self.city}, {self.state} {self.zip}"
        return f"{self.label} — {place}" if self.label else place

    def save(self, *args, **kwargs):
        # A user's first address becomes their default.
        if self._state.adding and not Address.objects.filter(user=self.user).exists():
            self.is_default = True
        super().save(*args, **kwargs)

    @transaction.atomic
    def make_default(self):
        """Make this the user's default, clearing the previous one first."""
        Address.objects.filter(user=self.user, is_default=True).exclude(
            pk=self.pk
        ).update(is_default=False)
        self.is_default = True
        self.save(update_fields=["is_default"])

    def as_initial(self, prefix: str) -> dict[str, str]:
        """This address as checkout initial data, e.g. ``shipping_city``."""
        return {f"{prefix}_{name}": getattr(self, name) for name in self.FIELDS}

    @classmethod
    def fields_from(cls, data: Mapping[str, Any], prefix: str) -> dict[str, Any]:
        """The inverse of ``as_initial``: pull one checkout section's fields."""
        return {name: data[f"{prefix}_{name}"] for name in cls.FIELDS}
