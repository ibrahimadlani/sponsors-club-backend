# Organisations domain

## Purpose
The `organisations` app models partner organisations and their collaborator memberships. It exposes endpoints for creating organisations, managing collaborator rosters, issuing invitation codes, and transferring ownership while enforcing plan-based limits defined in the `payments` app.

## Data model
- **`Organisation`** – Rich organisation profile with unique `slug`, enumerated `type`, `industry`, optional media (`logo`, `banner_image`), contact fields, address segmentation, `social_links` JSON, and business metrics (`founded_year`, `employees_count`, `budget_range`, `sponsoring_focus`). The `owner` field is a foreign key to the `Collaborator` representing the owner. `get_owner_id()` safely resolves the owner collaborator even if the in-memory FK becomes stale.
- **`Collaborator`** – Connects a `User` to an organisation with a `role` (`OWNER` or `MEMBER`) and `job_title`. A unique constraint guarantees only one owner per organisation. Instance-level `delete()` promotes cascade deletion when the owner collaborator is removed directly in code, matching legacy expectations.
- **`OrganisationInvite`** – Time-bound invitation code issued by a collaborator. Tracks the creator (`created_by`), expiry (`expires_at`), usage state, and the consuming user.

## Serializers & service objects
- **`OrganisationSerializer`** – Read serializer that exposes full metadata plus both `owner_id` (collaborator UUID) and the owning user via a derived property.
- **`OrganisationCreateSerializer`** – Validates that the requester is a collaborator account (or staff), creates the organisation, and immediately persists the owner `Collaborator` record before assigning the FK.
- **`OrganisationListFilter`** – Supports optional `type`, `industry`, and `address_country` filters used by `OrganisationViewSet.list`.
- **`CollaboratorSerializer` / `CollaboratorCreateSerializer`** – Serialise collaborator metadata and invite existing users by email. Validation prevents duplicate memberships and disallows assigning the owner role through invites.
- **Invitation serializers** – `OrganisationInviteCreateSerializer`, `OrganisationInviteSerializer`, and `OrganisationJoinSerializer` manage invite issuance, introspection, and redemption.
- **Maintenance serializers** – `CollaboratorJobTitleSerializer` for job title updates and `OwnershipTransferSerializer` to hand over owner status between collaborators.

## Permissions & entitlements
- **Listing / creation** require `IsCollaboratorAccount` (authenticated collaborator or staff).
- **Write operations** on an organisation enforce `IsOrganisationOwner`.
- **Collaborator endpoints** use `IsAuthenticatedCollaborator` for read access and additional ownership checks for mutations.
- **Feature gate checks** leverage `core.permissions.get_collaborator_plan_features()` and the `COLLABORATOR_FEATURES` matrix. When limits are exceeded, the API returns a structured denial payload via `requirement_denied_payload()` so the client can surface upgrade messaging.

## API surface (`/api/organisations/…`)
| Method | Route | Description | Auth |
| --- | --- | --- | --- |
| `GET` | `/organisations/` | List organisations with optional `type`, `industry`, `address_country` filters. | Collaborator/staff |
| `POST` | `/organisations/` | Create an organisation; requester becomes owner collaborator. | Collaborator/staff |
| `GET` | `/organisations/<id>/` | Retrieve organisation details. | Collaborator/staff |
| `PUT/PATCH` | `/organisations/<id>/` | Update organisation fields. | Organisation owner |
| `GET` | `/organisations/<id>/collaborators/` | List collaborators for the organisation. | Collaborator on org |
| `POST` | `/organisations/<id>/collaborators/add/` | Invite an existing user (entitlement checks, plan quotas apply). | Organisation owner |
| `PATCH` | `/organisations/<id>/collaborators/<collaborator_id>/job-title/` | Update a collaborator job title. | Owner or collaborator |
| `POST` | `/organisations/<id>/transfer-ownership/` | Assign ownership to another collaborator. | Organisation owner |
| `DELETE` | `/organisations/collaborators/<collaborator_id>/` | Remove a collaborator (entitlement checks apply). | Organisation owner |
| `GET/POST` | `/organisations/<id>/invites/` | List or issue invitation codes. | Organisation owner |
| `POST` | `/organisations/join/` | Join via invite code. | Collaborator |

Pagination uses DRF defaults where applicable. `OrganisationViewSet` caches the organisation per request to avoid duplicate lookups.

## Interactions with other domains
- Collaborator entitlements depend on active subscriptions in the `payments` app.
- Invite redemption uses the `users` app for identity and ensures the joining user holds a collaborator account type.
- Follow and messaging domains reference organisation collaborators for permission checks.

## Testing notes
Extensive pytest coverage lives in `organisations/tests/`. Factory-style fixtures in `conftest.py` provide reusable organisation, owner, and subscription records for integration tests. When modifying collaborator behaviours, update both the serializers and the fixture helpers to keep the docs accurate.
