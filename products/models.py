from io import BytesIO

from django.core.files.base import ContentFile
from django.db import models, transaction
from django.templatetags.static import static
from django.urls import reverse
from PIL import Image, ImageOps

from .fields import ProductImageField
from .validators import (
    validate_image_dimensions,
    validate_image_file_size,
    validate_image_format,
    validate_usable_image,
)

# Categories with a dedicated placeholder illustration; anything else
# falls back to default.svg. Placeholders are static files chosen by
# category; a product's own uploaded image (``Product.image``) takes
# precedence — see ``Product.display_image_url``.
PLACEHOLDER_CATEGORIES = {
    "home-assistants",
    "neural-implants",
    "neural-wearables",
    "accessories",
    "defense",
    "legacy-products",
}

# Every stored product image is an IMAGE_SIZE square WebP. Uploads are
# fitted inside it without cropping and padded with the storefront navy
# (the placeholder SVGs' background and the ``night`` theme's base).
IMAGE_SIZE = 800
IMAGE_PADDING_COLOR = "#141824"
IMAGE_WEBP_QUALITY = 82


def _process_image(upload, slug: str) -> ContentFile:
    """Turn an upload into the stored form: an 800×800 navy-padded WebP.

    Applies EXIF orientation, takes the first frame of an animated file,
    scales down to fit (never crops, never upscales), centers it on a
    navy canvas — transparent areas become navy — and encodes WebP. The
    result is named ``<slug>.webp``; storage adds a suffix on collision,
    so a replaced image always gets a new URL.
    """
    upload.seek(0)
    with Image.open(upload) as source:  # opens on the first frame
        image = ImageOps.exif_transpose(source).convert("RGBA")
    image.thumbnail((IMAGE_SIZE, IMAGE_SIZE), Image.Resampling.LANCZOS)

    canvas = Image.new("RGB", (IMAGE_SIZE, IMAGE_SIZE), IMAGE_PADDING_COLOR)
    offset = ((IMAGE_SIZE - image.width) // 2, (IMAGE_SIZE - image.height) // 2)
    canvas.paste(image, offset, mask=image)

    buffer = BytesIO()
    canvas.save(buffer, format="WEBP", quality=IMAGE_WEBP_QUALITY)
    return ContentFile(buffer.getvalue(), name=f"{slug or 'product'}.webp")


def _delete_file_after_commit(storage, name: str) -> None:
    """Delete a stored file once the current transaction commits.

    If the transaction rolls back, the callback is discarded and the file
    stays — so a failed save never leaves a row pointing at a deleted file.
    """
    transaction.on_commit(lambda: storage.delete(name))


def delete_product_image(sender, instance, **kwargs) -> None:
    """``post_delete`` receiver: remove a deleted product's image file.

    Fires for queryset deletes too (such as the seed's wipe). Registered
    in ``ProductsConfig.ready()``.
    """
    if instance.image:
        _delete_file_after_commit(instance.image.storage, instance.image.name)


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("products:category", kwargs={"slug": self.slug})

    @property
    def placeholder_image(self):
        """Static path of the placeholder image shown for this category's products."""
        if self.slug in PLACEHOLDER_CATEGORIES:
            return f"images/placeholders/{self.slug}.svg"
        return "images/placeholders/default.svg"


class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ProductQuerySet(models.QuerySet):
    def available(self):
        return self.filter(is_available=True)

    def search(self, text):
        """Simple icontains search over name and description."""
        return self.filter(
            models.Q(name__icontains=text) | models.Q(description__icontains=text)
        )


class Product(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    tagline = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_available = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name="products")
    image = ProductImageField(
        upload_to="products/",
        blank=True,
        validators=[
            validate_usable_image,
            validate_image_format,
            validate_image_file_size,
            validate_image_dimensions,
        ],
    )

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """Save, processing a *new* image upload and cleaning up the old file.

        Two rules make this safe:

        - **New uploads only.** Processing runs only when ``image`` holds an
          uncommitted upload, and runs *before* ``super().save()``, so the
          database row is only ever written with the finished WebP. Saving
          without a new upload (a price edit) does no image work at all.
        - **Delete after commit.** When the stored file changes — replaced
          or cleared — the previous file is deleted via
          ``transaction.on_commit``. Storage writes the new file before the
          row is written, so the worst failure is an unreferenced file in
          ``media/``, never a product pointing at a missing one.
        """
        if self.image and not self.image._committed:
            self.image = _process_image(self.image, self.slug)

        previous_name = (
            Product.objects.filter(pk=self.pk).values_list("image", flat=True).first()
            if self.pk
            else None
        )
        super().save(*args, **kwargs)

        if previous_name and previous_name != self.image.name:
            _delete_file_after_commit(self.image.storage, previous_name)

    def get_absolute_url(self):
        return reverse("products:detail", kwargs={"slug": self.slug})

    @property
    def display_image_url(self):
        """URL of the image to show: the upload if set, else the category placeholder.

        Templates use only this property, never ``image`` or
        ``placeholder_image`` directly.
        """
        if self.image:
            return self.image.url
        return static(self.category.placeholder_image)
