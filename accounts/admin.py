from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Address, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = (
        *DjangoUserAdmin.fieldsets,
        ("ThoughtTronix", {"fields": ("job_title",)}),
    )
    list_display = ("username", "email", "job_title", "is_staff")


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    """Inspection only — saved addresses have no back-office tab."""

    list_display = ("user", "label", "street", "city", "state", "is_default")
    list_select_related = ("user",)
    search_fields = ("user__username", "street", "city")
