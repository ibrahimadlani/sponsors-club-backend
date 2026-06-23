# REST API Integration Patterns

Django REST Framework (DRF) provides the HTTP surface for every domain app. This guide documents the shared configuration, the lightweight django-filter stub used in tests, pagination patterns, and serializer conventions you should follow when adding new endpoints.

## Framework configuration

- `REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES']` enables both session and JWT authentication so browsers and API clients can coexist.
- `REST_FRAMEWORK['DEFAULT_FILTER_BACKENDS']` points to `django_filters.rest_framework.DjangoFilterBackend`, giving every viewset access to request-driven filtering hooks.
- The custom user model is registered via `AUTH_USER_MODEL = "users.User"`, ensuring DRF serializers resolve the correct relationships across apps.

These settings live in `core.settings` and are inherited automatically by all DRF views.

## django-filter stub

The repository provides a minimal `DjangoFilterBackend` implementation in `django_filters.rest_framework`. It satisfies DRF's import requirement during testing without pulling the real dependency. The stub exposes a `filter_queryset` method that simply returns the input queryset untouched. When the real package is installed, it can override the stub seamlessly.

## Pagination strategy

Apps define `PageNumberPagination` subclasses close to their views so page size decisions remain domain-specific:

| App | Pagination class | Page size |
| --- | ---------------- | --------- |
| Analytics | `DailyStatsPagination` | 30 (max 100) |
| Contracts | `ContractPagination` | 20 (max 100) |
| Messaging | `ThreadPagination`, `ThreadMessagesPagination` | 20 (threads) / 50 (messages, max 200) |
| Notifications | `NotificationPagination` | 25 (max 100) |

Each list view or viewset assigns its pagination class via `pagination_class`, while detail endpoints either disable pagination or paginate manually (e.g., `ThreadMessagesView` instantiates the paginator for ad-hoc responses). Tests in `organisations` also demonstrate how to override pagination during unit tests to assert deterministic payloads.

## Serializer conventions

- Prefer `ModelSerializer` for ORM-backed resources and declare `read_only_fields` for immutable attributes such as `id`, timestamps, and foreign keys.
- Compose nested serializers for related models (e.g., analytics embeds `AthletePublicSerializer` and `SocialPlatformSerializer` for richer payloads).
- When returning computed dictionaries, simple `Serializer` subclasses (like `DailyStatsSummarySerializer`) can override `to_representation` to pass through pre-built data structures without requiring model instances.
- Update serializers (e.g., `MeUpdateSerializer`) ensure partial updates keep related models in sync, typically via overridden `update` methods.

Following these patterns keeps the API surface consistent and makes it easy to layer new domain features without rethinking infrastructure concerns.
