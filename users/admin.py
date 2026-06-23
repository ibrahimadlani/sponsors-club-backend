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
                    "avatar",
                    "phone_country_code",
                    "phone_number",
                    "date_of_birth",
                    "gender",
                    "country",
                    "language",
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
                    "avatar",
                    "phone_country_code",
                    "phone_number",
                    "date_of_birth",
                    "gender",
                    "country",
                    "language",
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

    list_display = ("user", "agent_name", "is_self_represented")
    list_filter = ("is_self_represented",)
    search_fields = (
        "user__email",
        "user__first_name",
        "user__last_name",
    )

    @admin.display(description="Name")
    def agent_name(self, obj):  # noqa: D401
        """Return the friendly name derived from the related user."""

        return obj.name
