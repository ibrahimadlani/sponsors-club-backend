"""URL routing for notification endpoints."""

from django.urls import path

from .views import NotificationListView, NotificationReadView

urlpatterns = [
    path('', NotificationListView.as_view(), name='notifications-list'),
    path(
        '<uuid:notification_id>/read/',
        NotificationReadView.as_view(),
        name='notifications-read',
    ),
]
