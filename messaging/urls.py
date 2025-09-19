"""URL routing for the messaging application."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import MessageReadView, ThreadMessagesView, ThreadViewSet

router = DefaultRouter()
router.register(r'threads', ThreadViewSet, basename='messaging-thread')

urlpatterns = [
    path('', include(router.urls)),
    path(
        'threads/<uuid:thread_id>/messages/',
        ThreadMessagesView.as_view(),
        name='thread-messages',
    ),
    path(
        'messages/<uuid:message_id>/read/',
        MessageReadView.as_view(),
        name='message-read',
    ),
]
