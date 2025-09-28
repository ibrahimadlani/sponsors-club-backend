"""Unit tests covering the custom pytest fixtures and stubs in ``conftest``."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _purge_modules(monkeypatch: pytest.MonkeyPatch, names: list[str]) -> None:
    """Remove modules from ``sys.modules`` for the duration of the test."""

    for name in names:
        monkeypatch.delitem(sys.modules, name, raising=False)


def _load_isolated_conftest(
    monkeypatch: pytest.MonkeyPatch,
    overrides: dict[str, Any] | None = None,
    *,
    remove: list[str] | None = None,
):
    """Import ``conftest`` under a unique module name with optional overrides."""

    if remove:
        _purge_modules(monkeypatch, remove)

    overrides = overrides or {}
    module_name = f"_conftest_copy_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(
        module_name, _PROJECT_ROOT / "conftest.py"
    )
    module = importlib.util.module_from_spec(spec)

    original_find_spec = importlib.util.find_spec

    def fake_find_spec(name: str, *args, **kwargs):  # type: ignore[override]
        if name in overrides:
            return overrides[name]
        return original_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    assert spec and spec.loader, "Failed to load conftest module specification"
    spec.loader.exec_module(module)
    return module


_DEFAULT_OVERRIDES = {
    "channels": None,
    "corsheaders": None,
    "boto3": None,
    "pytest_django": None,
}

_MODULES_TO_REMOVE = [
    "channels",
    "channels.generic",
    "channels.generic.websocket",
    "channels.auth",
    "channels.db",
    "channels.layers",
    "channels.routing",
    "channels.security",
    "channels.security.websocket",
    "channels.apps",
    "corsheaders",
    "corsheaders.middleware",
    "boto3",
    "botocore",
    "botocore.exceptions",
]


def _call_fixture(func, *args, **kwargs):
    """Invoke a pytest fixture function directly via its wrapped callable."""

    target = getattr(func, "__wrapped__", func)
    return target(*args, **kwargs)


def test_stub_module_sets_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    """The helper should return a module with an import specification."""

    module = _load_isolated_conftest(
        monkeypatch, _DEFAULT_OVERRIDES, remove=_MODULES_TO_REMOVE
    )
    stub = module._stub_module("tests.example")
    assert stub.__spec__ is not None
    assert stub.__spec__.name == "tests.example"


def test_channels_stub_consumer_behaviour(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Channels fallback exposes the async consumer behaviour used in tests."""

    _load_isolated_conftest(monkeypatch, _DEFAULT_OVERRIDES, remove=_MODULES_TO_REMOVE)

    consumer_cls = sys.modules["channels.generic.websocket"].AsyncJsonWebsocketConsumer
    consumer = consumer_cls()
    asyncio.run(consumer.accept())
    assert consumer.accepted is True

    asyncio.run(consumer.close(code=4321))
    assert consumer.closed_code == 4321

    asyncio.run(consumer.send_json({"type": "ping"}))
    assert consumer.sent_messages[-1] == {"type": "ping"}

    asyncio.run(consumer._base_send({"type": "custom"}))
    assert consumer.sent_messages[-1] == {"type": "custom"}

    asyncio.run(consumer.disconnect(3999))
    assert consumer.disconnected_code == 3999

    sync_wrapper = sys.modules["channels.db"].database_sync_to_async(lambda: "ok")
    assert asyncio.run(sync_wrapper()) == "ok"

    layer = sys.modules["channels.layers"].get_channel_layer()
    asyncio.run(layer.group_add("group", "channel"))
    asyncio.run(layer.group_send("group", {"msg": "hi"}))
    asyncio.run(layer.group_discard("group", "channel"))

    routing = sys.modules["channels.routing"]
    router = routing.ProtocolTypeRouter({"websocket": "handler"})
    assert router["websocket"] == "handler"
    assert routing.URLRouter(["/ws/"]) == ["/ws/"]

    validator = sys.modules["channels.security.websocket"].AllowedHostsOriginValidator
    assert validator("app") == "app"


def test_channels_stub_noop_when_dependency_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Calling the helper with a discovered module should exit early."""

    module = _load_isolated_conftest(
        monkeypatch, _DEFAULT_OVERRIDES, remove=_MODULES_TO_REMOVE
    )

    sentinel = object()

    def fake_find_spec(name: str, *args, **kwargs):  # noqa: ANN001
        if name == "channels":
            return sentinel
        return None

    monkeypatch.setattr(module.importlib.util, "find_spec", fake_find_spec)
    module._ensure_channels_stub()


def test_optional_dependency_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    """corsheaders and boto3 are stubbed when the real packages are missing."""

    _load_isolated_conftest(monkeypatch, _DEFAULT_OVERRIDES, remove=_MODULES_TO_REMOVE)

    middleware_cls = sys.modules["corsheaders.middleware"].CorsMiddleware
    seen_request: list[str] = []

    def _get_response(request):  # noqa: ANN001
        seen_request.append(request)
        return {"request": request}

    middleware = middleware_cls(_get_response)
    assert middleware("payload") == {"request": "payload"}
    assert seen_request == ["payload"]

    client = sys.modules["boto3"].client("ses", region_name="eu-west-3")
    client.send_email(Source="source@example.com")
    assert client.sent_requests[-1]["Source"] == "source@example.com"

    exceptions = sys.modules["botocore.exceptions"]
    assert issubclass(exceptions.BotoCoreError, Exception)
    assert issubclass(exceptions.ClientError, Exception)


def test_django_db_blocker_stub_and_reset_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fallback django_db_blocker yields a context manager used by reset_db."""

    module = _load_isolated_conftest(
        monkeypatch, _DEFAULT_OVERRIDES, remove=_MODULES_TO_REMOVE
    )

    blocker = _call_fixture(module.django_db_blocker)
    with blocker.unblock():
        pass

    calls: dict[str, Any] = {}

    def fake_call_command(name: str, **kwargs):  # noqa: ANN001
        calls["name"] = name
        calls["kwargs"] = kwargs

    monkeypatch.setattr(module, "call_command", fake_call_command)

    gen = _call_fixture(module.reset_db, blocker)
    next(gen)
    with pytest.raises(StopIteration):
        next(gen)

    assert calls == {
        "name": "flush",
        "kwargs": {"verbosity": 0, "interactive": False},
    }


def test_api_client_fixture_returns_drf_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure the shared API client fixture uses DRF's test client factory."""

    module = _load_isolated_conftest(
        monkeypatch, _DEFAULT_OVERRIDES, remove=_MODULES_TO_REMOVE
    )
    client = _call_fixture(module.api_client)

    from rest_framework.test import APIClient

    assert isinstance(client, APIClient)


def test_user_model_fixture_matches_django(monkeypatch: pytest.MonkeyPatch) -> None:
    """The exported user model fixture should mirror Django's lookup helper."""

    module = _load_isolated_conftest(
        monkeypatch, _DEFAULT_OVERRIDES, remove=_MODULES_TO_REMOVE
    )
    sentinel = object()
    monkeypatch.setattr(module, "get_user_model", lambda: sentinel)

    assert _call_fixture(module.fixture_user_model) is sentinel


def test_agent_user_fixture_creates_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """The agent_user fixture should create a profile and attach it to the user."""

    module = _load_isolated_conftest(
        monkeypatch, _DEFAULT_OVERRIDES, remove=_MODULES_TO_REMOVE
    )

    class FakeUserModel:
        class AccountType:
            AGENT = "agent"
            COLLABORATOR = "collaborator"

        def __init__(self) -> None:
            self.created: list[SimpleNamespace] = []
            self.objects = SimpleNamespace(create_user=self._create_user)

        def _create_user(self, **kwargs):  # noqa: ANN001
            user = SimpleNamespace(**kwargs)
            self.created.append(user)
            return user

    created_profiles: list[SimpleNamespace] = []

    def fake_profile_create(*, user, display_name, **kwargs):  # noqa: ANN001
        profile = SimpleNamespace(user=user, display_name=display_name, extra=kwargs)
        user.agent_profile = profile
        created_profiles.append(profile)
        return profile

    monkeypatch.setattr(
        module,
        "AgentProfile",
        SimpleNamespace(objects=SimpleNamespace(create=fake_profile_create)),
    )

    user_model = FakeUserModel()
    agent = _call_fixture(module.fixture_agent_user, user_model)

    assert user_model.created and user_model.created[0] is agent
    assert created_profiles and created_profiles[0].display_name == "Agent One"
    assert getattr(agent, "agent_profile").display_name == "Agent One"


def test_organisations_setup_fixture_returns_entities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """organisations_setup should return the owner, organisation and subscription."""

    module = _load_isolated_conftest(
        monkeypatch, _DEFAULT_OVERRIDES, remove=_MODULES_TO_REMOVE
    )

    class FakeUserModel:
        class AccountType:
            AGENT = "agent"
            COLLABORATOR = "collaborator"

        def __init__(self) -> None:
            self.objects = SimpleNamespace(create_user=self._create_user)
            self.created: list[SimpleNamespace] = []

        def _create_user(self, **kwargs):  # noqa: ANN001
            user = SimpleNamespace(**kwargs)
            self.created.append(user)
            return user

    plan = SimpleNamespace(code="org-enterprise")
    monkeypatch.setattr(
        module.SubscriptionPlan,
        "objects",
        SimpleNamespace(get_or_create=lambda **kwargs: (plan, True)),
    )

    created_orgs: list[SimpleNamespace] = []

    def fake_org_create(**kwargs):  # noqa: ANN001
        organisation = SimpleNamespace(**kwargs)
        created_orgs.append(organisation)
        return organisation

    monkeypatch.setattr(
        module,
        "Organisation",
        SimpleNamespace(
            Type=SimpleNamespace(BRAND="brand"),
            objects=SimpleNamespace(create=fake_org_create),
        ),
    )

    created_collaborators: list[SimpleNamespace] = []

    def fake_collaborator_create(**kwargs):  # noqa: ANN001
        collaborator = SimpleNamespace(**kwargs)
        created_collaborators.append(collaborator)
        return collaborator

    monkeypatch.setattr(
        module,
        "Collaborator",
        SimpleNamespace(
            Role=SimpleNamespace(OWNER="owner"),
            objects=SimpleNamespace(create=fake_collaborator_create),
        ),
    )

    created_subscriptions: list[SimpleNamespace] = []

    def fake_subscription_create(**kwargs):  # noqa: ANN001
        subscription = SimpleNamespace(**kwargs)
        created_subscriptions.append(subscription)
        return subscription

    monkeypatch.setattr(
        module,
        "Subscription",
        SimpleNamespace(
            Status=SimpleNamespace(ACTIVE="active"),
            objects=SimpleNamespace(create=fake_subscription_create),
        ),
    )

    user_model = FakeUserModel()
    data = _call_fixture(module.fixture_organisations_setup, user_model)

    assert data["owner"] is user_model.created[0]
    assert data["organisation"] is created_orgs[0]
    assert data["collaborator"] is created_collaborators[0]
    assert data["subscription"] is created_subscriptions[0]


def test_owner_user_fixture_aliases_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    """owner_user should expose the owner created by organisations_setup."""

    module = _load_isolated_conftest(
        monkeypatch, _DEFAULT_OVERRIDES, remove=_MODULES_TO_REMOVE
    )
    owner = SimpleNamespace(name="owner")
    organisations_setup = {"owner": owner}

    assert _call_fixture(module.owner_user, organisations_setup=organisations_setup) is owner


def test_agent_subscription_fixture_uses_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    """The agent subscription fixture should link the agent to the agency plan."""

    module = _load_isolated_conftest(
        monkeypatch, _DEFAULT_OVERRIDES, remove=_MODULES_TO_REMOVE
    )

    plan = SimpleNamespace(code="agent-agency")
    monkeypatch.setattr(
        module.SubscriptionPlan,
        "objects",
        SimpleNamespace(get_or_create=lambda **kwargs: (plan, True)),
    )

    created_subscriptions: list[SimpleNamespace] = []

    def fake_subscription_create(**kwargs):  # noqa: ANN001
        subscription = SimpleNamespace(**kwargs)
        created_subscriptions.append(subscription)
        return subscription

    monkeypatch.setattr(
        module,
        "Subscription",
        SimpleNamespace(
            Status=SimpleNamespace(ACTIVE="active"),
            objects=SimpleNamespace(create=fake_subscription_create),
        ),
    )

    agent_user = SimpleNamespace(agent_profile=SimpleNamespace())

    subscription = _call_fixture(module.fixture_agent_subscription, agent_user)

    assert created_subscriptions and subscription is created_subscriptions[0]
    assert subscription.plan is plan
    assert subscription.agent is agent_user.agent_profile


def test_organisation_subscription_fixture_matches_setup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The organisation subscription fixture should match organisations_setup."""

    module = _load_isolated_conftest(
        monkeypatch, _DEFAULT_OVERRIDES, remove=_MODULES_TO_REMOVE
    )
    subscription = SimpleNamespace()
    organisations_setup = {"subscription": subscription}

    result = _call_fixture(
        module.organisation_subscription, organisations_setup=organisations_setup
    )

    assert result is subscription
