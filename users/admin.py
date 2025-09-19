"""Admin registrations for user and agent profile models."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import AgentProfile, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Customize the admin interface for the custom user model."""

    model = User
    list_display = (
        "email",
        "first_name",
        "last_name",
        "account_type",
        "is_staff",
        "is_active",
    )
    list_filter = ("account_type", "is_staff", "is_active")
    ordering = ("email",)
    search_fields = ("email", "first_name", "last_name")
    readonly_fields = ("password_hash", "created_at", "updated_at", "last_login")

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "email",
                    "password",
                    "password_hash",
                    "account_type",
                    "email_verified",
                )
            },
        ),
        (
            "Personal info",
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "phone_number",
                    "date_of_birth",
                )
            },
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "first_name",
                    "last_name",
                    "phone_number",
                    "date_of_birth",
                    "account_type",
                    "email_verified",
                    "password1",
                    "password2",
                    "is_staff",
                    "is_active",
                ),
            },
        ),
    )


@admin.register(AgentProfile)
class AgentProfileAdmin(admin.ModelAdmin):
    """Admin configuration for managing agent profiles."""

    list_display = ("user", "display_name")
    search_fields = (
        "display_name",
        "user__email",
        "user__first_name",
        "user__last_name",
    )
