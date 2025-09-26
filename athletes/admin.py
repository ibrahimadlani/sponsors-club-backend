"""Admin registrations for athletes and sports."""

# Admin configuration focuses on surfacing the most relevant filters for team
# members managing athletes through the Django admin UI.

from django.contrib import admin

from .models import Athlete, Sport, SportDiscipline


class SportDisciplineInline(admin.TabularInline):
    """Inline editor for sport disciplines within the sport admin."""

    model = SportDiscipline
    extra = 1


@admin.register(Sport)
class SportAdmin(admin.ModelAdmin):
    """Expose sport metadata with searchable fields.

    Attributes:
        list_display (tuple[str, ...]): Columns shown in the change list.
        search_fields (tuple[str, ...]): Fields to query when using the admin
            search bar.
    """

    list_display = ("name", "slug", "category")
    list_filter = ("category",)
    search_fields = ("name", "slug")
    inlines = (SportDisciplineInline,)


@admin.register(Athlete)
class AthleteAdmin(admin.ModelAdmin):
    """Provide rich admin filters for athlete management.

    Attributes:
        list_display (tuple[str, ...]): Headline columns for the athlete list.
        list_filter (tuple[str, ...]): Sidebar filters that help staff narrow
            down athletes quickly.
        search_fields (tuple[str, ...]): Fields used when searching athletes by
            name, sport, or agent contact details.
    """

    list_display = ("full_name", "sport", "agent", "nationality")
    list_filter = ("sport", "nationality")
    # Including agent details allows operations staff to resolve enquiries fast.
    search_fields = (
        "full_name",
        "sport__name",
        "agent__display_name",
        "agent__user__email",
    )
