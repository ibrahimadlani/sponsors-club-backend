"""Shared pytest fixtures for the Sponsors Club test suite."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import sys
import types
from collections.abc import Generator
from contextlib import contextmanager

import django
import pytest


def _stub_module(name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__spec__ = importlib.machinery.ModuleSpec(name, loader=None)
    return module


def _ensure_channels_stub() -> None:
    """Provide a minimal Channels stub when the dependency is absent."""

    if importlib.util.find_spec("channels") is not None:
        return

    channels = _stub_module("channels")
    channels.__file__ = __file__
    channels.__path__ = [os.getcwd()]
    generic = _stub_module("channels.generic")
    websocket = _stub_module("channels.generic.websocket")

    class _StubAsyncJsonWebsocketConsumer:
        def __init__(self):
            self.scope = {}
            self.channel_layer = None
            self.channel_name = "test-channel"
            self.accepted = False
            self.closed_code = None
            self.sent_messages = []
            self.disconnected_code = None

        async def accept(self):
            self.accepted = True

        async def close(self, code: int = 1000):
            self.closed_code = code

        async def send_json(self, content):
            self.sent_messages.append(content)

        async def disconnect(self, code):
            self.disconnected_code = code

    websocket.AsyncJsonWebsocketConsumer = _StubAsyncJsonWebsocketConsumer
    generic.websocket = websocket
    channels.generic = generic

    auth = _stub_module("channels.auth")

    def AuthMiddlewareStack(application):  # pragma: no cover - test stub
        return application

    auth.AuthMiddlewareStack = AuthMiddlewareStack

    db = _stub_module("channels.db")

    def database_sync_to_async(func):  # pragma: no cover - test stub
        async def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return wrapper

    db.database_sync_to_async = database_sync_to_async

    layers = _stub_module("channels.layers")

    class InMemoryChannelLayer:  # pragma: no cover - test stub
        async def group_send(self, group, message):
            return None

        async def group_add(self, group, channel):
            return None

        async def group_discard(self, group, channel):
            return None

    def get_channel_layer():  # pragma: no cover - test stub
        return InMemoryChannelLayer()

    layers.InMemoryChannelLayer = InMemoryChannelLayer
    layers.get_channel_layer = get_channel_layer

    routing = _stub_module("channels.routing")

    class ProtocolTypeRouter(dict):  # pragma: no cover - test stub
        pass

    def URLRouter(routes):  # pragma: no cover - test stub
        return routes

    routing.ProtocolTypeRouter = ProtocolTypeRouter
    routing.URLRouter = URLRouter

    security_pkg = _stub_module("channels.security")
    security_websocket = _stub_module("channels.security.websocket")

    def AllowedHostsOriginValidator(application):  # pragma: no cover - stub
        return application

    security_websocket.AllowedHostsOriginValidator = AllowedHostsOriginValidator
    security_pkg.websocket = security_websocket

    from django.apps import AppConfig  # imported lazily to avoid setup issues

    class ChannelsConfig(AppConfig):  # pragma: no cover - test stub
        name = "channels"
        label = "channels"
        path = os.getcwd()

    apps_module = _stub_module("channels.apps")
    apps_module.ChannelsConfig = ChannelsConfig

    channels.auth = auth
    channels.db = db
    channels.layers = layers
    channels.routing = routing
    channels.security = security_pkg
    channels.apps = apps_module
    channels.default_app_config = "channels.apps.ChannelsConfig"

    sys.modules["channels"] = channels
    sys.modules["channels.generic"] = generic
    sys.modules["channels.generic.websocket"] = websocket
    sys.modules["channels.auth"] = auth
    sys.modules["channels.db"] = db
    sys.modules["channels.layers"] = layers
    sys.modules["channels.routing"] = routing
    sys.modules["channels.security"] = security_pkg
    sys.modules["channels.security.websocket"] = security_websocket
    sys.modules["channels.apps"] = apps_module


def _ensure_optional_dependency_stubs() -> None:
    """Stub optional third-party packages that are not installed."""

    if importlib.util.find_spec("corsheaders") is None:
        corsheaders = _stub_module("corsheaders")
        corsheaders.__file__ = __file__
        corsheaders.__path__ = [os.getcwd()]

        middleware = _stub_module("corsheaders.middleware")

        class CorsMiddleware:  # pragma: no cover - test stub
            def __init__(self, get_response):
                self.get_response = get_response

            def __call__(self, request):
                return self.get_response(request)

        middleware.CorsMiddleware = CorsMiddleware
        corsheaders.middleware = middleware

        sys.modules["corsheaders"] = corsheaders
        sys.modules["corsheaders.middleware"] = middleware

    if importlib.util.find_spec("boto3") is None:
        boto3 = _stub_module("boto3")
        boto3.__file__ = __file__
        boto3.__path__ = [os.getcwd()]

        def client(service_name: str, **kwargs):  # pragma: no cover - stub
            class _DummyClient:
                def __init__(self):
                    self.service_name = service_name
                    self.kwargs = kwargs
                    self.sent_requests: list[dict[str, object]] = []

                def send_email(self, **request):
                    self.sent_requests.append(request)

            return _DummyClient()

        boto3.client = client

        botocore = _stub_module("botocore")
        exceptions = _stub_module("botocore.exceptions")

        class BotoCoreError(Exception):  # pragma: no cover - stub
            pass

        class ClientError(Exception):  # pragma: no cover - stub
            pass

        exceptions.BotoCoreError = BotoCoreError
        exceptions.ClientError = ClientError
        botocore.exceptions = exceptions

        sys.modules["boto3"] = boto3
        sys.modules["botocore"] = botocore
        sys.modules["botocore.exceptions"] = exceptions


_ensure_channels_stub()
_ensure_optional_dependency_stubs()

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()


if importlib.util.find_spec("pytest_django") is None:  # pragma: no cover - stub

    @pytest.fixture
    def django_db_blocker():
        class _Blocker:
            def unblock(self):
                @contextmanager
                def _noop():
                    yield

                return _noop()

        return _Blocker()

from django.contrib.auth import get_user_model  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.utils import timezone  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402

from organisations.models import Collaborator, Organisation  # noqa: E402
from payments.models import Subscription, SubscriptionPlan  # noqa: E402
from users.models import AgentProfile  # noqa: E402


@pytest.fixture(autouse=True)
def reset_db(django_db_blocker) -> Generator[None, None, None]:
    """Flush the database after each test to guarantee isolation."""

    yield
    with django_db_blocker.unblock():
        call_command("flush", verbosity=0, interactive=False)


@pytest.fixture
def api_client() -> APIClient:
    """Return a DRF API client for convenience in tests."""

    return APIClient()


@pytest.fixture(name="user_model")
def fixture_user_model():
    """Expose the Django user model to dependent fixtures."""

    return get_user_model()


@pytest.fixture(name="agent_user")
def fixture_agent_user(user_model):
    """Create and return a test agent user with profile."""

    user = user_model.objects.create_user(
        email="agent@test.com",
        password="pass1234",
        first_name="Agent",
        last_name="User",
        account_type=user_model.AccountType.AGENT,
    )
    AgentProfile.objects.create(user=user, display_name="Agent One")
    return user


@pytest.fixture
def owner_user(organisations_setup):
    """Return the organisation owner generated by organisations_setup."""

    return organisations_setup["owner"]


@pytest.fixture(name="organisations_setup")
def fixture_organisations_setup(user_model):
    """Create an organisation, collaborator owner, and active subscription."""

    owner = user_model.objects.create_user(
        email="owner@test.com",
        password="pass1234",
        first_name="Owner",
        last_name="User",
        account_type=user_model.AccountType.COLLABORATOR,
    )
    organisation = Organisation.objects.create(
        owner=owner,
        name="Test Org",
        type=Organisation.Type.BRAND,
        industry="Tech",
        description="Organisation description",
        website_url="https://test.org",
        email_contact="contact@test.org",
        phone_contact="+33102030405",
        address_city="Paris",
        address_country="FR",
        address_postal_code="75000",
        social_links={"linkedin": "https://linkedin.com/company/test-org"},
        founded_year=2010,
        employees_count=25,
        budget_range="10k-100k",
        sponsoring_focus=["sports collectifs"],
    )
    collaborator = Collaborator.objects.create(
        user=owner,
        organisation=organisation,
        role=Collaborator.Role.OWNER,
        job_title="Owner",
    )

    plan = SubscriptionPlan.objects.get(code="org-enterprise")
    subscription = Subscription.objects.create(
        organisation=organisation,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        start_at=timezone.now(),
        current_period_end=timezone.now(),
    )
    return {
        "owner": owner,
        "organisation": organisation,
        "collaborator": collaborator,
        "subscription": subscription,
    }


@pytest.fixture(name="agent_subscription")
def fixture_agent_subscription(agent_user):
    """Create an agent subscription tied to the agent_user fixture."""

    plan = SubscriptionPlan.objects.get(code="agent-agency")
    subscription = Subscription.objects.create(
        agent=agent_user.agent_profile,
        plan=plan,
        status=Subscription.Status.ACTIVE,
        start_at=timezone.now(),
        current_period_end=timezone.now(),
    )
    return subscription


@pytest.fixture
def organisation_subscription(organisations_setup):
    """Return the active organisation subscription fixture."""

    return organisations_setup["subscription"]
