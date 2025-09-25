# Organisations domain

## Overview
The organisations app manages company profiles and collaborator memberships. It
exposes endpoints for creating organisations, inviting teammates, listing
collaborators, and updating organisation details while enforcing subscription
limits on invitations.

## Data model
- **`Organisation`** stores enriched company metadata: a unique `slug`, typed
  `type` (brand, SME, startup, association, individual, agency, other),
  `industry`, optional `logo`/`banner_image`, rich `description`, contact fields
  (`website_url`, `email_contact`, `phone_contact`), address components,
  `social_links` JSON, and business data (`founded_year`, `employees_count`,
  `budget_range`, `sponsoring_focus`). The helper `get_owner_id()` returns the
  collaborator record representing the owner.
- **`Collaborator`** links a `User` to an organisation with a `role` (`OWNER` or
  `MEMBER`) and `job_title`. A unique constraint ensures only one owner per
  organisation.
- **`OrganisationInvite`** stores OTP-style invitation codes. Codes are
  time-bound (`expires_at`), track the creator collaborator, and record when and
  by whom they are consumed.

## Serializers and workflows
- `OrganisationSerializer` is the default read serializer, including an
  `owner_id` and all enriched metadata.
- `OrganisationCreateSerializer` validates that the requester is a collaborator
  account, creates the organisation with optional enrichment fields, and
  immediately persists an owner `Collaborator` record for the user.
- `OrganisationListFilter` validates optional `type`, `industry`, and
  `address_country` filters before applying them to the queryset.
- `CollaboratorSerializer` exposes collaborator metadata along with user email
  and derived full name.
- `CollaboratorCreateSerializer` invites an existing user by email, ensuring the
  role is not `OWNER`, the user has a collaborator account, and the invitee is
  not already a member.
- `OrganisationInviteCreateSerializer`, `OrganisationInviteSerializer`, and
  `OrganisationJoinSerializer` orchestrate OTP generation, listing, and joining
  flows. Invites default to 72-hour expiry but accept custom durations.
- `CollaboratorJobTitleSerializer` and `OwnershipTransferSerializer` handle job
  title updates and ownership transfer requests.

## Permissions and entitlements
`OrganisationViewSet` layers custom permissions per action:
- Listing and creating organisations require an authenticated collaborator or
  staff account (`IsCollaboratorAccount`).
- Updating records requires ownership (`IsOrganisationOwner`).
- Collaborator management endpoints fetch the organisation and require either an
  authenticated collaborator (`IsAuthenticatedCollaborator`) or owner for write
  operations.

Invitation and removal endpoints also enforce plan limits:
- `CollaboratorCreateSerializer` checks the requester's plan via
  `get_collaborator_plan_features()` and blocks invites when
  `max_collaborators` is reached, returning a structured denial using
  `requirement_denied_payload()`.
- The `collaborator_invites` and `collaborator_slots` requirements in
  `COLLABORATOR_FEATURES` gate access to invitation and removal flows.

## API surface
Routes are mounted under `/api/organisations/`.

| Method | Route | Description | Auth |
| --- | --- | --- | --- |
| `GET` | `/organisations/` | List organisations with optional `?sector=`, `?size=`, `?country=` filtering. | Collaborator/staff |
| `POST` | `/organisations/` | Create an organisation; requester becomes owner collaborator. | Collaborator/staff |
| `GET` | `/organisations/<id>/` | Retrieve organisation details. | Collaborator/staff |
| `PUT/PATCH` | `/organisations/<id>/` | Update organisation fields. | Organisation owner |
| `GET` | `/organisations/<id>/collaborators/` | List collaborators for the organisation. | Collaborator on org |
| `POST` | `/organisations/<id>/collaborators/add/` | Invite an existing user as collaborator, respecting plan quotas. | Organisation owner with invite feature |
| `PATCH` | `/organisations/<id>/collaborators/<collaborator_id>/job-title/` | Update a collaborator job title (owner or the collaborator). | Owner/collaborator |
| `POST` | `/organisations/<id>/transfer-ownership/` | Promote a collaborator to owner while demoting the current one. | Organisation owner |
| `DELETE` | `/organisations/collaborators/<collaborator_id>/` | Remove a collaborator, subject to the same plan requirement. | Organisation owner |
| `GET/POST` | `/organisations/<id>/invites/` | List or create invitation OTP codes. | Organisation owner |
| `POST` | `/organisations/join/` | Join an organisation by providing a valid invite code. | Collaborator |

Pagination relies on DRF defaults. All collaborator endpoints execute within
`OrganisationViewSet`, ensuring object lookups are scoped per request.
