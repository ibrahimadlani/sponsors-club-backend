# Contracts domain

## Overview
The contracts app manages reusable clause templates and the lifecycle of
contracts between organisations and athletes. It enforces collaborator plan
requirements for drafting, updating, and maintaining contract documents, and it
captures version history with every status change or clause edit.

## Data model
- **`ClauseTemplate`** stores reusable clause content with tokenised placeholders
  and version numbers. Only one active template per `identifier` is expected,
  with optional `mandatory` flags for UI guidance.
- **`Contract`** links an `Organisation`, `Athlete`, and creating `Collaborator`.
  It tracks monetary amounts, currency, start/end dates, and a workflow status
  (`DRAFT`, `AGREEMENT`, `VERIFICATION`, `ACTIVE`, `TERMINATED`). Indexes
  optimise lookups by organisation, athlete, and start date.
- **`ContractClause`** binds a template to a contract with stored placeholder
  `values` and an `order_index`. A unique constraint prevents duplicates per
  `(contract, template, order_index)`.
- **`ContractVersion`** snapshots the rendered contract and clause ordering every
  time `_create_version()` is invoked. Version numbers auto-increment per
  contract.
- **`ContractStatusHistory`** records transitions between workflow states,
  including the acting user and optional reasons.

## Serializers and business rules
- `ContractCreateSerializer` attaches the organisation and athlete, validates the
  requester is an organisation owner, checks the
  `COLLABORATOR_FEATURES["contract_management"]` requirement, and enforces a
  clause template lookup before creating `ContractClause` entries.
- `ContractSerializer` exposes the full contract, clause list, and status history
  for read operations.
- `ContractStatusUpdateSerializer` validates transitions; `_is_valid_transition`
  restricts movement to the defined workflow graph.
- `ContractClauseUpsertSerializer` drives the clause management endpoint,
  allowing owners to create or overwrite clauses in-place.

## Permissions and entitlements
`ContractsViewSet` requires authentication for all actions. Additional controls
include:
- Only organisation owners (or staff) may create contracts, update statuses,
  modify clauses, or render text.
- Each privileged action checks the `contract_management` feature via
  `collaborator_meets_requirement()` and responds with
  `requirement_denied_payload()` when the plan disallows access.

## API surface
Routes are mounted under `/api/contracts/` by the router.

| Method | Route | Description | Auth |
| --- | --- | --- | --- |
| `GET` | `/contracts/` | Paginated contracts visible to the requester (owner, collaborator, or relevant agent). Supports `?status=`, `?organisation=`, `?athlete=` filtering. | Authenticated |
| `POST` | `/contracts/` | Create a contract, initial version snapshot, and optional clauses. | Organisation owner with contract feature |
| `GET` | `/contracts/<id>/` | Retrieve a single contract, clauses, and status history. | Authenticated and related |
| `PATCH` | `/contracts/<id>/status/` | Transition the workflow status with reason logging. | Organisation owner with contract feature |
| `GET` | `/contracts/<id>/versions/` | List historical versions ordered newest first. | Authenticated and related |
| `POST` | `/contracts/<id>/clauses/` | Create or update a clause by template/order index. | Organisation owner with contract feature |
| `POST` | `/contracts/<id>/render/` | Render the contract text with placeholder substitution. | Organisation owner or staff |

All list responses use `ContractPagination` (20 items per page, adjustable up to
100).
