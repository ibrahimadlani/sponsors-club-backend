"""Websocket routing for the messaging application."""

from django.urls import re_path

from .consumers import ThreadConsumer

websocket_urlpatterns = [
    re_path(r"^ws/threads/(?P<thread_id>[0-9a-fA-F-]+)/$", ThreadConsumer.as_asgi()),
]
