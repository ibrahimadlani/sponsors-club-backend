"""Project level URL routing definition."""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("api/users/", include("users.urls")),
    path("api/", include("organisations.urls")),
    path("api/", include("athletes.urls")),
    path("api/", include("follows.urls")),
    path("api/messaging/", include("messaging.urls")),
    path("api/", include("contracts.urls")),
    path("api/", include("analytics.urls")),
    path("api/payments/", include("payments.urls")),
    path("api/notifications/", include("notifications.urls")),
    path(
        "poc/login/",
        TemplateView.as_view(template_name="poc/login.html"),
        name="poc-login",
    ),
]

if getattr(settings, "DRF_YASG_ENABLED", False):
    try:
        from drf_yasg import openapi
        from drf_yasg.views import get_schema_view
        from rest_framework import permissions
    except ImportError:
        pass
    else:
        SchemaView = get_schema_view(
            openapi.Info(
                title="Sponsors Club API",
                default_version="v1",
                description=(
                    "Interactive API documentation for the Sponsors Club platform."
                ),
            ),
            public=True,
            permission_classes=(permissions.AllowAny,),
        )

        urlpatterns += [
            path(
                "api/schema/",
                SchemaView.without_ui(cache_timeout=0),
                name="schema-json",
            ),
            path(
                "api/docs/",
                SchemaView.with_ui("swagger", cache_timeout=0),
                name="schema-swagger-ui",
            ),
            path(
                "api/redoc/",
                SchemaView.with_ui("redoc", cache_timeout=0),
                name="schema-redoc",
            ),
        ]
