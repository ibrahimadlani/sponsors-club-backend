# Organisations domain

## Overview
The organisations app manages company profiles and collaborator memberships. It
exposes endpoints for creating organisations, inviting teammates, listing
collaborators, and updating organisation details while enforcing subscription
limits on invitations.

## Data model
- **`Organisation`** stores company metadata (sector, size, budget ranges,
  country, optional logo) and tracks an owner `User`. The helper `get_owner_id()`
  returns the collaborator record representing the owner.
- **`Collaborator`** links a `User` to an organisation with a `role` (`OWNER` or
  `MEMBER`) and `job_title`. A unique constraint ensures only one owner per
  organisation.

## Serializers and workflows
- `OrganisationSerializer` is the default read serializer, including an
  `owner_id` for UI use.
- `OrganisationCreateSerializer` validates that the requester is a collaborator
  account, creates the organisation, and immediately persists an owner
  `Collaborator` record for the user.
- `OrganisationListFilter` validates optional `sector`, `size`, and `country`
  filters before applying them to the queryset.
- `CollaboratorSerializer` exposes collaborator metadata along with user email
  and derived full name.
- `CollaboratorCreateSerializer` invites an existing user by email, ensuring the
  role is not `OWNER`, the user has a collaborator account, and the invitee is
  not already a member.

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
| `DELETE` | `/organisations/collaborators/<collaborator_id>/` | Remove a collaborator, subject to the same plan requirement. | Organisation owner |

Pagination relies on DRF defaults. All collaborator endpoints execute within
`OrganisationViewSet`, ensuring object lookups are scoped per request.
