from django.apps import AppConfig
from django.db.models.signals import post_delete


class ProductsConfig(AppConfig):
    name = "products"

    def ready(self):
        from .models import Product, delete_product_image

        post_delete.connect(delete_product_image, sender=Product)
