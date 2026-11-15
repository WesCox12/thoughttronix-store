"""Coupons, and the discount snapshot on orders.

Orders placed before coupons existed had no discount, so their
subtotal is their total.
"""

from decimal import Decimal

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


def backfill_subtotals(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    Order.objects.update(subtotal=models.F("total"))


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0002_order_orderitem"),
        ("products", "0003_product_is_featured"),
    ]

    operations = [
        migrations.CreateModel(
            name="Coupon",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "code",
                    models.CharField(
                        help_text="What customers type at checkout. Not case-sensitive.",
                        max_length=30,
                        unique=True,
                        validators=[
                            django.core.validators.RegexValidator(
                                "^[A-Z0-9_-]{3,30}$",
                                "Use 3–30 letters, digits, hyphens, or underscores.",
                            )
                        ],
                    ),
                ),
                (
                    "description",
                    models.CharField(
                        blank=True,
                        help_text="Internal note for staff — customers never see it.",
                        max_length=200,
                    ),
                ),
                (
                    "percent_off",
                    models.PositiveSmallIntegerField(
                        help_text="A whole number from 1 to 100.",
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(100),
                        ],
                    ),
                ),
                (
                    "scope",
                    models.CharField(
                        choices=[
                            ("ORDER", "Whole order"),
                            ("PRODUCTS", "Specific products"),
                        ],
                        default="ORDER",
                        max_length=10,
                        verbose_name="Applies to",
                    ),
                ),
                (
                    "starts_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                ("expires_at", models.DateTimeField()),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="Untick to retire the coupon. You can reactivate it later.",
                        verbose_name="Active",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "products",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Only for “Specific products”. Ctrl/Cmd-click to pick several.",
                        related_name="coupons",
                        to="products.product",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            ("percent_off__gte", 1), ("percent_off__lte", 100)
                        ),
                        name="coupon_percent_off_1_to_100",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("expires_at__gt", models.F("starts_at"))
                        ),
                        name="coupon_expires_after_start",
                    ),
                ],
            },
        ),
        migrations.AddField(
            model_name="order",
            name="subtotal",
            field=models.DecimalField(
                decimal_places=2, default=Decimal("0.00"), max_digits=10
            ),
            preserve_default=False,
        ),
        migrations.RunPython(backfill_subtotals, migrations.RunPython.noop),
        migrations.AddField(
            model_name="order",
            name="discount",
            field=models.DecimalField(
                decimal_places=2, default=Decimal("0.00"), max_digits=10
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="coupon",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="orders",
                to="orders.coupon",
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="coupon_code",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="discount",
            field=models.DecimalField(
                decimal_places=2, default=Decimal("0.00"), max_digits=10
            ),
        ),
    ]
