# Organisations domain

## Purpose
The `organisations` app models partner organisations and their collaborator memberships. It exposes endpoints for creating organisations, managing collaborator rosters, issuing invitation codes, and transferring ownership while enforcing plan-based limits defined in the `payments` app.

## Data model
- **`Organisation`** – Rich organisation profile with unique `slug`, enumerated `type`, `industry`, optional media (`logo`, `banner_image`), contact fields, address segmentation, `social_links` JSON, and business metrics (`founded_year`, `employees_count`, `budget_range`, `sponsoring_focus`). The `owner` field is a foreign key to the `Collaborator` representing the owner. `get_owner_id()` safely resolves the owner collaborator even if the in-memory FK becomes stale.
- **`Collaborator`** – Connects a `User` to an organisation with a `role` (`OWNER` or `MEMBER`) and `job_title`. A unique constraint guarantees only one owner per organisation. Instance-level `delete()` promotes cascade deletion when the owner collaborator is removed directly in code, matching legacy expectations.
- **`OrganisationInvite`** – Time-bound invitation code issued by a collaborator. Tracks the creator (`created_by`), expiry (`expires_at`), usage state (`is_used`, `used_at`, `used_by`), and the consuming user. Includes a computed `status` property (`active`, `expired`, `used`) and custom queryset methods for filtering.
- **`OrganisationInviteQuerySet`** – Custom manager with `.active()`, `.expired()`, and `.used()` methods for efficient status-based filtering.

## Serializers & service objects
- **`OrganisationSerializer`** – Read serializer that exposes full metadata plus both `owner_id` (collaborator UUID) and the owning user via a derived property.
- **`OrganisationCreateSerializer`** – Validates that the requester is a collaborator account (or staff), creates the organisation, and immediately persists the owner `Collaborator` record before assigning the FK.
- **`OrganisationListFilter`** – Supports optional `type`, `industry`, and `address_country` filters used by `OrganisationViewSet.list`.
- **`CollaboratorSerializer` / `CollaboratorCreateSerializer`** – Serialise collaborator metadata and invite existing users by email. Validation prevents duplicate memberships and disallows assigning the owner role through invites.
- **Invitation serializers** – `OrganisationInviteCreateSerializer`, `OrganisationInviteSerializer`, and `OrganisationJoinSerializer` manage invite issuance, introspection, and redemption. The join serializer now uses `select_for_update()` to prevent race conditions during concurrent redemption attempts.
- **Invitation security** – Codes are generated using cryptographic randomness (`secrets` module) with 8-character length from a 33-character alphabet. Validation is case-insensitive and trims whitespace automatically.
- **Maintenance serializers** – `CollaboratorJobTitleSerializer` for job title updates and `OwnershipTransferSerializer` to hand over owner status between collaborators.

## Permissions & entitlements
- **Listing** requires staff via `IsAdminUser`.
- **Creation** requires `IsOrganisationCreator` (staff or collaborator without an organisation).
- **Write operations** on an organisation enforce `IsOrganisationOwner`.
- **Collaborator endpoints** use `IsAuthenticatedCollaborator` for read access and additional ownership checks for mutations.
- **Feature gate checks** leverage `core.permissions.get_collaborator_plan_features()` and the `COLLABORATOR_FEATURES` matrix. When limits are exceeded, the API returns a structured denial payload via `requirement_denied_payload()` so the client can surface upgrade messaging.
- **Rate limiting** – Invitation creation is throttled to 10/hour per user (`InviteCreateThrottle`), and joining via invite code is limited to 20/hour per user (`InviteJoinThrottle`) to prevent brute force attacks and spam.

## API surface (`/api/organisations/…`)
| Method | Route | Description | Auth | Rate Limit |
| --- | --- | --- | --- | --- |
| `GET` | `/organisations/` | List organisations with optional `type`, `industry`, `address_country` filters. | Staff | - |
| `POST` | `/organisations/` | Create an organisation; requester becomes owner collaborator. | Staff or collaborator without organisation | - |
| `GET` | `/organisations/<id>/` | Retrieve organisation details. | Staff or collaborator on org | - |
| `PUT/PATCH` | `/organisations/<id>/` | Update organisation fields. | Organisation owner | - |
| `GET` | `/organisations/<id>/collaborators/` | List collaborators for the organisation. | Collaborator on org | - |
| `POST` | `/organisations/<id>/collaborators/add/` | Invite an existing user (entitlement checks, plan quotas apply). | Organisation owner | - |
| `PATCH` | `/organisations/<id>/collaborators/<collaborator_id>/job-title/` | Update a collaborator job title. | Owner or collaborator | - |
| `POST` | `/organisations/<id>/transfer-ownership/` | Assign ownership to another collaborator. | Organisation owner | - |
| `DELETE` | `/organisations/collaborators/<collaborator_id>/` | Remove a collaborator (entitlement checks apply). | Organisation owner | - |
| `GET` | `/organisations/<id>/invites/?status=<active\|expired\|used>` | List invitation codes with optional status filtering. | Organisation owner | - |
| `POST` | `/organisations/<id>/invites/` | Issue a new invitation code (expires_in_hours: 1-168, default: 72). | Organisation owner | 10/hour |
| `DELETE` | `/organisations/<id>/invites/<invite_id>/` | Revoke/delete an invitation (cannot revoke used invitations). | Organisation owner | - |
| `POST` | `/organisations/join/` | Join via invite code (validates expiry, usage, account type). | Collaborator | 20/hour |

**New features:**
- **Status filtering** – GET `/organisations/<id>/invites/` now accepts `?status=active|expired|used` query parameter
- **Invitation revocation** – DELETE endpoint allows owners to revoke unused invitations
- **Enhanced response** – All invite responses now include a computed `status` field

**Security improvements:**
- Race condition prevention using database-level row locking (`select_for_update()`)
- Rate limiting on creation (10/hour) and redemption (20/hour)
- Case-insensitive code validation with automatic whitespace trimming

Pagination uses DRF defaults where applicable. `OrganisationViewSet` caches the organisation per request to avoid duplicate lookups.

## Interactions with other domains
- Collaborator entitlements depend on active subscriptions in the `payments` app.
- Invite redemption uses the `users` app for identity and ensures the joining user holds a collaborator account type.
- Follow and messaging domains reference organisation collaborators for permission checks.

## Maintenance & operations

### Management commands
- **`cleanup_expired_invites`** – Removes expired invitation codes older than a specified number of days (default: 30).
  ```bash
  # Dry run to see what would be deleted
  python manage.py cleanup_expired_invites --dry-run

  # Delete expired invites older than 30 days
  python manage.py cleanup_expired_invites --days=30

  # Include used invitations in cleanup
  python manage.py cleanup_expired_invites --include-used
  ```

  **Recommended cron schedule:**
  ```cron
  # Run daily at 2 AM
  0 2 * * * cd /path/to/project && python manage.py cleanup_expired_invites --days=30
  ```

### Invitation lifecycle
1. **Creation** – Owner generates code with optional expiry (1-168 hours, default 72)
2. **Active period** – Code can be used until expiration or first use
3. **Redemption** – User joins organization, code marked as used
4. **Expiration** – Unused codes expire automatically after timeout
5. **Cleanup** – Old expired codes periodically removed via management command

### Monitoring recommendations
- Track invitation conversion rates (used vs. expired)
- Monitor rate limit violations for potential abuse
- Alert on excessive invitation generation by single users
- Track average time-to-redemption for UX optimization

## Testing notes
Extensive pytest coverage lives in `organisations/tests/`. Factory-style fixtures in `conftest.py` provide reusable organisation, owner, and subscription records for integration tests.

**New test suite** – `organisations/tests/test_invitation_edge_cases.py` provides comprehensive coverage:
- Expiration validation and status tracking
- Reuse prevention and concurrent redemption (race conditions)
- Code validation (case-insensitivity, whitespace, invalid formats)
- Account type restrictions (agent vs collaborator)
- Invitation revocation permissions and edge cases
- Status filtering (active/expired/used)
- Rate limiting scenarios

When modifying collaborator or invitation behaviours, update both the serializers and the fixture helpers to keep the docs accurate.
