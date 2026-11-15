"""The product-image field pair: one model field, one form field.

Django's ``forms.ImageField`` checks uploads with Pillow *before* any model
validator runs, and rejects anything unreadable with its own generic
wording. Both the back-office ``ProductForm`` and the Django admin build
their form field from the model field's ``formfield()``, so that is the one
place that reaches both forms: ``ProductImageField`` hands every form a
``ProductImageFormField`` with the readable message and the ``accept``
hint. The rules themselves stay in ``products/validators.py``.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.db import models

from .validators import UNUSABLE_IMAGE_MESSAGE, validate_usable_image

ACCEPTED_TYPES = "image/png,image/jpeg,image/webp"


class ProductImageFormField(forms.ImageField):
    """``forms.ImageField`` with readable errors and a PNG/JPEG/WebP file picker."""

    default_error_messages = {"invalid_image": UNUSABLE_IMAGE_MESSAGE}

    def to_python(self, data):
        try:
            return super().to_python(data)
        except ValidationError as error:
            # Django's check hides *why* Pillow refused the file. Re-run our
            # own check so a decompression bomb gets its specific message.
            if error.code == "invalid_image":
                validate_usable_image(data)
            raise

    def widget_attrs(self, widget):
        """Offer only the accepted formats in the file picker (a hint, not a rule)."""
        attrs = super().widget_attrs(widget)
        if isinstance(widget, forms.FileInput) and "accept" not in widget.attrs:
            attrs["accept"] = ACCEPTED_TYPES
        return attrs


class ProductImageField(models.ImageField):
    """``models.ImageField`` whose forms use ``ProductImageFormField``."""

    def formfield(self, **kwargs):
        return super().formfield(**{"form_class": ProductImageFormField, **kwargs})
