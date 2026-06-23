# `users/` — Platform-wide identity layer, email-based auth, and JWT tokens.

## Responsibility

- Custom `User` model (email as username, two account types: AGENT / COLLABORATOR).
- JWT authentication via `rest_framework_simplejwt`.
- Agent-specific profile (`AgentProfile`) and entourage profile (`RepresentativeProfile`).
- Email verification tokens with 48-hour expiry.
- Feature entitlement discovery endpoints (`/me/roles/`, `/me/entitlements/`).

## Models

| Model | Purpose | Key fields / methods |
|-------|---------|---------------------|
| `User` | Primary auth model (email-based) | `email`, `account_type` (AGENT / COLLABORATOR), `email_verified`, `phone_country_code`, `phone_number`, `is_active`, `password_hash`; `set_password()`, `save()` |
| `UserManager` | Custom manager | `create_user()`, `create_superuser()` |
| `AgentProfile` | Agent-specific extension (1:1 with User) | `bio`, `is_self_represented`; `name` property |
| `RepresentativeProfile` | Entourage member profile (1:1 with User) | `is_kyc_verified`, `license_number`, `licensing_federation`; `is_licensed_agent` property, `trust_label` property |
| `EmailVerificationToken` | Email confirmation token (48h expiry) | `token_hash` (SHA-256), `expires_at`, `used_at`; `issue_for_user()`, `verify()` |

## API Endpoints

| Method | URL | Auth | Permission | Description |
|--------|-----|------|------------|-------------|
| `POST` | `/api/users/register/` | Public | `AllowAny` | Create a new user account |
| `POST` | `/api/users/login/` | Public | `AllowAny` | Obtain JWT access + refresh tokens |
| `POST` | `/api/users/refresh/` | Public | `AllowAny` | Refresh an access token |
| `GET` | `/api/users/me/` | Required | `IsAuthenticated` | Retrieve the current user's profile |
| `PATCH` | `/api/users/me/` | Required | `IsAuthenticated` | Update profile fields |
| `GET` | `/api/users/me/roles/` | Required | `IsAuthenticated` | Return the user's roles (agent, collaborator, staff) |
| `GET` | `/api/users/me/entitlements/` | Required | `IsAuthenticated` | Return current plan feature entitlements |
| `POST` | `/api/users/verify-email/` | Required | `IsAuthenticated` | Consume an email verification token |

## Permissions & Roles

- `AccountType.AGENT` → has an `AgentProfile`; may create athletes, manage contracts.
- `AccountType.COLLABORATOR` → linked to an `Organisation` via `Collaborator`; may follow athletes, send messages, and initiate contracts.
- Staff (`is_staff=True`) bypasses all feature gates.

## Key Workflows

1. **Registration** — `POST /register/` creates the user, sends a verification email
   with a one-time token (`EmailVerificationToken.issue_for_user()`).
2. **Email verification** — User calls `POST /verify-email/` with the raw token;
   `EmailVerificationToken.verify()` hashes it and looks up the unexpired record.
3. **JWT login** — `POST /login/` returns `access` + `refresh` tokens with embedded
   profile claims (`TokenObtainPairWithProfileView`).
4. **Entitlement discovery** — `GET /me/entitlements/` resolves the active subscription
   plan and returns a structured dict of allowed features and their limits.

## Dependencies

**Requires:** `core` (feature_matrix for entitlement computation), `payments`
(Subscription, SubscriptionPlan)

**Used by:** every app — `User` is `AUTH_USER_MODEL`; `AgentProfile` is referenced
by `athletes`, `contracts`; `RepresentativeProfile` is referenced by `athletes`
(RepresentationMandate)
