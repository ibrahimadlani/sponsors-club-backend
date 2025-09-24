"""URL routing for notification endpoints.

The routes mirror the mobile client's expectations: a collection endpoint for
listing notifications and an item endpoint for read state updates.
"""

from django.urls import path

from .views import NotificationListView, NotificationReadView

urlpatterns = [
    # The base path exposes a paginated feed of the authenticated user's
    # notifications.
    path("", NotificationListView.as_view(), name="notifications-list"),
    # The read endpoint performs a partial update on a single notification.
    path(
        "<uuid:notification_id>/read/",
        NotificationReadView.as_view(),
        name="notifications-read",
    ),
]
