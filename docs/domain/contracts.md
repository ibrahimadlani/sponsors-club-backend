# Contracts domain

## Overview

The `contracts` app manages the full lifecycle of sponsorship agreements between
organisations and athletes. It covers clause drafting, multi-party negotiation,
legal review, DocuSign e-signature, and a marketplace fee layer — with an
immutable audit trail on every action.

## Contract lifecycle

```
DRAFT → NEGOTIATION → AGREEMENT → LEGAL_REVIEW → SIGNING → ACTIVE → EXPIRED
                                                                    ↘ TERMINATED
```

State transitions are validated by `_is_valid_transition()`. Only the status
action (`PATCH /status/`) or dedicated workflow actions can move a contract
forward.

## Data model

### Core

| Model | Purpose | Key fields / methods |
|-------|---------|---------------------|
| `ClauseTemplate` | Reusable clause blueprints | `category` (10 choices), `content` (with `{{placeholders}}`), `is_mandatory`, `version` |
| `Contract` | Root agreement record | `organisation`, `agent`, `athlete`, `status`, `current_version_number`; `add_mandatory_clauses()`, `has_full_agreement()`, `record_agreement()`, `bump_version()`, `generate_platform_fee()` |
| `ContractClause` | Contract-bound clause | `template`, `placeholder_values`, `locked_placeholders`; `render_content()`, `can_modify_placeholder()` |

### Phase 1 — Negotiation & Versioning

| Model | Purpose | Key fields / methods |
|-------|---------|---------------------|
| `ContractRevision` | Proposed clause change by one party | `proposed_by`, `clauses_changed` (M2M), `accepted` (tri-state null/True/False) |
| `ContractVersion` | Immutable snapshot of the contract at a given step | `number`, `clauses_snapshot` (JSON), `agreement_status` (JSON); `capture_snapshot()` |
| `ContractComment` | Annotation on a specific version or clause | `version`, `clause`, `author`, `body` |

### Phase 2 — Legal Compliance & Marketplace

| Model | Purpose | Key fields / methods |
|-------|---------|---------------------|
| `ContractCounterpart` | Financial nature of the deal | `type` (CASH / EQUIPMENT_DOTATION / EXPENSE_REIMBURSEMENT), `estimated_value`; separates cash from material for URSSAF compliance |
| `PerformanceBonus` | Conditional bonus tied to a result | `trigger_condition`, `bonus_amount`, `is_achieved`; must be separate from fixed compensation to avoid employment requalification |
| `ImageRightsScope` | Territorial and temporal scope of image rights | `territory`, `duration_months`, `allowed_media`, `excludes_club_gear`; mandatory per French IP law (CA Paris, 2 févr. 2010) |
| `ContractAuditLog` | Immutable action log | `actor`, `action` (23 choices), `action_details`, `ip_address`, `user_agent`; written on every state change for electronic contract traceability |

### Signing & Export

| Model | Purpose | Key fields / methods |
|-------|---------|---------------------|
| `ContractSigning` | DocuSign envelope tracking | `envelope_id`, `status` (INITIATED / COMPLETED / DECLINED / ERROR), `last_payload` |
| `ContractLegalReview` | Legal review lifecycle | `requested_by`, `verified_by`, `verified_at`, `verification_notes` |
| `ContractFile` | Signed contract export | `pdf` FileField (1:1 with Contract) |

### Minor athlete compliance

`Contract` carries additional fields when the athlete is a minor:
`is_athlete_minor`, `legal_guardian_name`, `legal_guardian_email`,
`legal_guardian_agreed_at`, `requires_escrow_deposit`. These are computed by
`compute_minor_status()` at creation time.

## Mandate validation at signing

Before `signing/init/` creates a DocuSign envelope, `_has_valid_mandate()` queries
`athletes.RepresentationMandate` for the agent:

```python
RepresentationMandate.objects.filter(
    representative__user=contract.agent.user,
    role=RepresentationMandate.Role.LICENSED_AGENT,
    is_active=True,
    verified=True,
    valid_from__lte=today,
    valid_until__gte=today,
).exists()
```

If no valid mandate is found, the endpoint returns `HTTP 403` with a structured
`missing_mandates` payload listing the blocking party.

## Platform fee (marketplace paywall)

`Contract.generate_platform_fee()` is called at AGREEMENT status and creates a
`payments.PlatformFee` record. The fee blocks DocuSign envelope creation until
`PlatformFee.status == PAID`.

| Counterpart type | Fee rule |
|-----------------|---------|
| Any CASH counterpart | 10 % of total cash value, minimum €10 |
| Material only (no cash) | €49 flat fee |

The fee is idempotent — calling `generate_platform_fee()` again only resets the
status to PENDING if the existing fee has not been paid yet.

## API endpoints

All routes are mounted under `/api/`. Authentication is required unless noted.

| Method | URL | Auth | Description |
|--------|-----|------|-------------|
| `GET` | `/api/contracts/` | Required | List contracts visible to the user |
| `POST` | `/api/contracts/` | Required | Create contract with mandatory clauses |
| `GET` | `/api/contracts/<id>/` | Required | Retrieve single contract |
| `GET` | `/api/contracts/options/` | Required | Contract creation options / metadata |
| `POST` | `/api/contracts/<id>/clauses/` | Required | Add a clause |
| `PATCH` | `/api/contracts/<id>/clauses/<clause_id>/` | Required | Update a clause |
| `PATCH` | `/api/contracts/<id>/clauses/<clause_id>/placeholders/` | Required | Update placeholder values |
| `DELETE` | `/api/contracts/<id>/clauses/<clause_id>/` | Required | Remove a clause |
| `POST` | `/api/contracts/<id>/revisions/` | Required | Propose clause revision |
| `GET` | `/api/contracts/<id>/revisions/` | Required | List revisions |
| `POST` | `/api/contracts/<id>/revisions/<revision_id>/accept/` | Required | Accept revision |
| `POST` | `/api/contracts/<id>/revisions/<revision_id>/reject/` | Required | Reject revision |
| `POST` | `/api/contracts/<id>/agree/` | Required | Record party agreement |
| `POST` | `/api/contracts/<id>/legal/review/` | Required | Submit for legal review |
| `PATCH` | `/api/contracts/<id>/legal/verify/` | Required | Complete legal review |
| `POST` | `/api/contracts/<id>/signing/init/` | Required | Initiate DocuSign envelope (paywall) |
| `GET` | `/api/contracts/<id>/signing/status/` | Required | Check signing status |
| `POST` | `/api/contracts/<id>/signing/webhook/` | Public | DocuSign webhook |
| `POST` | `/api/contracts/<id>/expire/` | Required | Manually expire contract |
| `GET` | `/api/contracts/<id>/versions/` | Required | List version snapshots |
| `GET` | `/api/contracts/<id>/versions/<version_id>/comments/` | Required | Version comments |
| `PATCH` | `/api/contracts/<id>/status/` | Required | Transition contract status |
| `GET` | `/api/contracts/<id>/export/` | Required | Export contract as PDF |
| `GET` | `/api/clause-templates/` | Required | List clause templates |

## Permissions & roles

- `IsAuthenticated` is required on all endpoints except the DocuSign webhook.
- `contract_management` feature gate (from `COLLABORATOR_FEATURES`) is checked
  on write operations via `collaborator_meets_requirement()`.
- The creating collaborator and the agent can both read the contract; only the
  organisation owner can transition status or modify clauses during DRAFT.
- During negotiation, either party can propose revisions; the other party
  accepts or rejects.

## Key workflows

1. **Draft → Negotiation** — Owner creates contract, mandatory clauses are auto-attached,
   `ContractVersion` snapshot is captured, status moves to NEGOTIATION.
2. **Negotiation loop** — Any party proposes a `ContractRevision`; the other accepts
   or rejects. On acceptance, `bump_version()` creates a new version snapshot.
3. **Agreement** — Both parties call `agree/`. `has_full_agreement()` checks both
   timestamps; when true, `generate_platform_fee()` is triggered automatically.
4. **Legal review** — Organisation submits review; staff verifies. Status moves to
   LEGAL_REVIEW → SIGNING.
5. **Signing** — `signing/init/` validates mandate + paid fee, creates DocuSign
   envelope. `signing/webhook/` updates `ContractSigning` status asynchronously.
6. **Active** — Signed PDF is attached via `ContractFile`. Contract moves to ACTIVE.

## Dependencies

**Requires:** `organisations` (Organisation, Collaborator), `athletes`
(Athlete, RepresentationMandate), `users` (User), `payments` (PlatformFee)

**Used by:** `payments` (PlatformFee trigger)
