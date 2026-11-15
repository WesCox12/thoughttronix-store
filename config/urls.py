"""URL configuration for the ThoughtTronix Store.

Every URL is named and every app has a namespace (e.g. ``products:catalog``).
Public catalog URLs use slugs; back-office URLs use pks.
"""

from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

# Static informational pages, namespaced ``pages`` (e.g. ``pages:recall_notices``).
pages_patterns = (
    [
        path(
            "safety/",
            TemplateView.as_view(template_name="pages/recall_notices.html"),
            name="recall_notices",
        ),
    ],
    "pages",
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("", include("dashboard.urls")),
    path("", include("orders.urls")),
    path("", include(pages_patterns)),
    path("", include("products.urls")),
]
