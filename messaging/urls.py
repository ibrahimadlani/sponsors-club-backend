"""URL routing for messaging API endpoints."""

from django.urls import path

from .views import MessageReadView, ThreadListView, ThreadMessagesView

app_name = "messaging"

urlpatterns = [
    path("threads/", ThreadListView.as_view(), name="thread-list"),
    path(
        "threads/<uuid:thread_id>/messages/",
        ThreadMessagesView.as_view(),
        name="thread-messages",
    ),
    path(
        "messages/<uuid:message_id>/read/",
        MessageReadView.as_view(),
        name="message-read",
    ),
]
