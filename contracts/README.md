# `contracts/` — Full sponsorship contract lifecycle: drafting, negotiation, legal review, and DocuSign signing.

## Responsibility

- Manage reusable clause templates and the full lifecycle of sponsorship agreements.
- Support multi-party negotiation with version-controlled clause revisions.
- Enforce legal compliance: URSSAF-aligned counterpart types, image rights scoping,
  minor athlete rules, and sports agency law (Art. L222-5 Code du sport).
- Gate DocuSign envelope creation on mandate validation and platform fee payment.
- Maintain an immutable audit trail of every action.

## Models

### Core

| Model | Purpose | Key fields / methods |
|-------|---------|---------------------|
| `ClauseTemplate` | Reusable clause with `{{placeholders}}` | `category`, `title`, `content`, `is_mandatory`, `version` |
| `Contract` | Root agreement record | `organisation`, `agent`, `athlete`, `status` (8 states), `current_version_number`; `add_mandatory_clauses()`, `has_full_agreement()`, `generate_platform_fee()`, `bump_version()`, `compute_minor_status()` |
| `ContractClause` | Clause bound to a contract | `template`, `placeholder_values`, `locked_placeholders`; `render_content()`, `can_modify_placeholder()` |

### Negotiation (Phase 1)

| Model | Purpose |
|-------|---------|
| `ContractRevision` | Clause change proposed by one party; accepted/rejected by the other |
| `ContractVersion` | Immutable snapshot at each negotiation step; `capture_snapshot()` |
| `ContractComment` | Annotation on a version or clause |

### Legal & Marketplace (Phase 2)

| Model | Purpose |
|-------|---------|
| `ContractCounterpart` | Financial nature: CASH / EQUIPMENT_DOTATION / EXPENSE_REIMBURSEMENT (URSSAF compliance) |
| `PerformanceBonus` | Conditional bonus; separate from fixed pay to avoid employment requalification |
| `ImageRightsScope` | Territory, duration, media scope (CA Paris, 2 févr. 2010) |
| `ContractAuditLog` | Immutable log: actor, action (23 choices), IP, user-agent |

### Signing & Export

| Model | Purpose |
|-------|---------|
| `ContractSigning` | DocuSign envelope tracking: `envelope_id`, status, `last_payload` |
| `ContractLegalReview` | Legal review lifecycle: requested_by, verified_by, verified_at |
| `ContractFile` | Signed PDF export (1:1 with Contract) |

## Contract lifecycle

```
DRAFT → NEGOTIATION → AGREEMENT → LEGAL_REVIEW → SIGNING → ACTIVE → EXPIRED
                                                                    ↘ TERMINATED
```

## API Endpoints

| Method | URL | Auth | Description |
|--------|-----|------|-------------|
| `GET` | `/api/contracts/` | Required | List contracts visible to the user |
| `POST` | `/api/contracts/` | Required | Create contract with mandatory clauses |
| `GET` | `/api/contracts/<id>/` | Required | Retrieve single contract |
| `GET` | `/api/contracts/options/` | Required | Creation options / metadata |
| `POST` | `/api/contracts/<id>/clauses/` | Required | Add a clause |
| `PATCH` | `/api/contracts/<id>/clauses/<clause_id>/` | Required | Update a clause |
| `PATCH` | `/api/contracts/<id>/clauses/<clause_id>/placeholders/` | Required | Update placeholder values |
| `DELETE` | `/api/contracts/<id>/clauses/<clause_id>/` | Required | Remove a clause |
| `POST` | `/api/contracts/<id>/revisions/` | Required | Propose a revision |
| `GET` | `/api/contracts/<id>/revisions/` | Required | List revisions |
| `POST` | `/api/contracts/<id>/revisions/<id>/accept/` | Required | Accept revision |
| `POST` | `/api/contracts/<id>/revisions/<id>/reject/` | Required | Reject revision |
| `POST` | `/api/contracts/<id>/agree/` | Required | Record party agreement |
| `POST` | `/api/contracts/<id>/legal/review/` | Required | Submit for legal review |
| `PATCH` | `/api/contracts/<id>/legal/verify/` | Required | Complete legal review |
| `POST` | `/api/contracts/<id>/signing/init/` | Required | Initiate DocuSign (mandate + fee required) |
| `GET` | `/api/contracts/<id>/signing/status/` | Required | Check signing status |
| `POST` | `/api/contracts/<id>/signing/webhook/` | Public | DocuSign webhook |
| `POST` | `/api/contracts/<id>/expire/` | Required | Manually expire contract |
| `GET` | `/api/contracts/<id>/versions/` | Required | List version snapshots |
| `GET` | `/api/contracts/<id>/versions/<id>/comments/` | Required | Version comments |
| `PATCH` | `/api/contracts/<id>/status/` | Required | Transition contract status |
| `GET` | `/api/contracts/<id>/export/` | Required | Export contract as PDF |
| `GET` | `/api/clause-templates/` | Required | List clause templates |

## Permissions & Roles

- **`IsAuthenticated`** required on all endpoints (except DocuSign webhook).
- **`contract_management` gate** (`COLLABORATOR_FEATURES`) checked on write actions.
- Organisation owner creates and drives the contract; agent can read and counter-propose.
- During negotiation, either party can propose revisions.

## Key Workflows

1. **Draft → Negotiation** — Owner creates contract; mandatory clauses are auto-attached;
   first `ContractVersion` snapshot is captured.
2. **Negotiation loop** — Either party proposes a `ContractRevision`; the other accepts or
   rejects. On acceptance, `bump_version()` creates a new snapshot.
3. **Agreement** — Both parties call `agree/`; once `has_full_agreement()` is true,
   `generate_platform_fee()` creates a `PlatformFee` record.
4. **Legal review** — Submitted for review; staff verifies; status moves to SIGNING.
5. **Signing** — `signing/init/` validates `RepresentationMandate.is_valid()` and
   `PlatformFee.status == PAID` before creating a DocuSign envelope. Returns `HTTP 402`
   if fee is unpaid, `HTTP 403` if mandate is missing.
6. **Active** — DocuSign webhook completes signing; `ContractFile` PDF is attached.

## Dependencies

**Requires:** `organisations` (Organisation, Collaborator), `athletes` (Athlete,
RepresentationMandate), `users` (User), `payments` (PlatformFee)

**Used by:** `payments` (triggers PlatformFee via `generate_platform_fee()`)
