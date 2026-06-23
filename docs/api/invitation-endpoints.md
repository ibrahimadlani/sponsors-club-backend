# Invitation System API Endpoints - Quick Reference

## Base URL
```
https://api.example.com/api
```

## Authentication
All endpoints require authentication via JWT token:
```
Authorization: Bearer <your_token_here>
```

---

## 1. Create Invitation

**Endpoint:** `POST /organisations/{organisation_id}/invites/`

**Permission:** Organisation Owner only

**Request Body:**
```json
{
  "expires_in_hours": 48  // Optional, default: 72, range: 1-168
}
```

**Response (201 Created):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "code": "ABCD1234",
  "created_at": "2026-01-07T10:00:00Z",
  "expires_at": "2026-01-09T10:00:00Z",
  "is_used": false,
  "used_at": null,
  "created_by": "owner@example.com",
  "status": "active"
}
```

**Rate Limit:** 10 requests/hour per user

**cURL Example:**
```bash
curl -X POST "https://api.example.com/api/organisations/550e8400-e29b-41d4-a716-446655440000/invites/" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "expires_in_hours": 48
  }'
```

---

## 2. List Invitations

**Endpoint:** `GET /organisations/{organisation_id}/invites/`

**Permission:** Organisation Owner only

**Query Parameters:**
- `status` (optional): Filter by status
  - `active` - Active invitations only
  - `expired` - Expired invitations only
  - `used` - Used invitations only

**Response (200 OK):**
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "code": "ABCD1234",
    "created_at": "2026-01-07T10:00:00Z",
    "expires_at": "2026-01-09T10:00:00Z",
    "is_used": false,
    "used_at": null,
    "created_by": "owner@example.com",
    "status": "active"
  },
  {
    "id": "660e8400-e29b-41d4-a716-446655440001",
    "code": "EFGH5678",
    "created_at": "2026-01-05T10:00:00Z",
    "expires_at": "2026-01-06T10:00:00Z",
    "is_used": false,
    "used_at": null,
    "created_by": "owner@example.com",
    "status": "expired"
  }
]
```

**cURL Examples:**
```bash
# All invitations
curl "https://api.example.com/api/organisations/550e8400.../invites/" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Active only
curl "https://api.example.com/api/organisations/550e8400.../invites/?status=active" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Expired only
curl "https://api.example.com/api/organisations/550e8400.../invites/?status=expired" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Used only
curl "https://api.example.com/api/organisations/550e8400.../invites/?status=used" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## 3. Revoke Invitation

**Endpoint:** `DELETE /organisations/{organisation_id}/invites/{invite_id}/`

**Permission:** Organisation Owner only

**Response (204 No Content)** - Success, no body returned

**Errors:**
- `400 Bad Request` - Cannot revoke already used invitation
- `403 Forbidden` - Not organization owner
- `404 Not Found` - Invitation not found

**cURL Example:**
```bash
curl -X DELETE "https://api.example.com/api/organisations/550e8400.../invites/invite-uuid/" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## 4. Join Organisation

**Endpoint:** `POST /organisations/join/`

**Permission:** Authenticated COLLABORATOR account

**Request Body:**
```json
{
  "code": "ABCD1234",
  "job_title": "Software Engineer"  // Optional, default: "Member"
}
```

**Response (201 Created):**
```json
{
  "id": "collaborator-uuid",
  "user": "user-uuid",
  "user_email": "user@example.com",
  "user_full_name": "John Doe",
  "role": "MEMBER",
  "job_title": "Software Engineer",
  "created_at": "2026-01-07T11:00:00Z",
  "updated_at": "2026-01-07T11:00:00Z"
}
```

**Rate Limit:** 20 requests/hour per user

**cURL Example:**
```bash
curl -X POST "https://api.example.com/api/organisations/join/" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "ABCD1234",
    "job_title": "Software Engineer"
  }'
```

---

## Error Responses

### 400 Bad Request

#### Invalid Code
```json
{
  "code": ["Invalid invitation code."]
}
```

#### Expired Code
```json
{
  "code": ["Invitation has expired."]
}
```

#### Already Used
```json
{
  "code": ["Invitation has already been used."]
}
```

#### Wrong Account Type
```json
{
  "code": ["Only collaborator accounts may join organisations."]
}
```

#### Already Member
```json
{
  "code": ["User already belongs to an organisation."]
}
```

#### Cannot Revoke Used Invitation
```json
{
  "detail": "Cannot revoke an invitation that has already been used."
}
```

---

### 403 Forbidden

#### Not Owner
```json
{
  "detail": "Only organisation owners can create invitation codes."
}
```

```json
{
  "detail": "Only organisation owners can revoke invitations."
}
```

#### Feature Not Available
```json
{
  "detail": "Upgrade your organisation plan to invite additional collaborators.",
  "required_feature": "collaborator_invites",
  "upgrade_url": "/pricing"
}
```

#### Collaborator Limit Reached
```json
{
  "detail": "Collaborator limit reached. Upgrade your organisation plan to add more teammates.",
  "required_feature": "max_collaborators",
  "upgrade_url": "/pricing"
}
```

---

### 404 Not Found

```json
{
  "detail": "Invitation not found."
}
```

---

### 429 Too Many Requests

```json
{
  "detail": "Request was throttled. Expected available in 3600 seconds."
}
```

---

## HTTP Status Codes Summary

| Code | Meaning | When |
|------|---------|------|
| 200 | OK | Successful GET request |
| 201 | Created | Invitation created or joined successfully |
| 204 | No Content | Invitation revoked successfully |
| 400 | Bad Request | Invalid data, expired code, already used, etc. |
| 403 | Forbidden | Permission denied, feature not available |
| 404 | Not Found | Invitation or organisation not found |
| 429 | Too Many Requests | Rate limit exceeded |

---

## Testing Checklist

### Create Invitation
- [ ] Create with default expiry (72h)
- [ ] Create with custom expiry (24h)
- [ ] Create with minimum expiry (1h)
- [ ] Create with maximum expiry (168h)
- [ ] Verify rate limit (11th request within 1 hour should fail)
- [ ] Try as non-owner (should fail with 403)
- [ ] Verify unique code generation

### List Invitations
- [ ] List all invitations
- [ ] Filter by status=active
- [ ] Filter by status=expired
- [ ] Filter by status=used
- [ ] Verify status field in response
- [ ] Try as non-owner (should fail with 403)

### Revoke Invitation
- [ ] Revoke active invitation (should succeed)
- [ ] Revoke expired invitation (should succeed)
- [ ] Try to revoke used invitation (should fail with 400)
- [ ] Try as non-owner (should fail with 403)
- [ ] Try with invalid invite ID (should fail with 404)

### Join Organisation
- [ ] Join with valid code and custom job title
- [ ] Join with valid code and default job title
- [ ] Try with expired code (should fail with 400)
- [ ] Try with already used code (should fail with 400)
- [ ] Try with invalid code (should fail with 400)
- [ ] Try with AGENT account (should fail with 400)
- [ ] Try when already in another org (should fail with 400)
- [ ] Test case-insensitivity (lowercase code should work)
- [ ] Test whitespace trimming (code with spaces should work)
- [ ] Verify rate limit (21st request within 1 hour should fail)

### Edge Cases
- [ ] Concurrent join attempts with same code (second should fail)
- [ ] Create invite when at collaborator limit (should fail with 403)
- [ ] Join with code just after expiration
- [ ] Revoke and immediately try to use code

---

## Postman Collection Variables

```json
{
  "base_url": "https://api.example.com/api",
  "token": "your_jwt_token_here",
  "org_id": "your_organisation_uuid",
  "invite_id": "created_invitation_uuid"
}
```

---

## Rate Limits Summary

| Endpoint | Limit | Scope |
|----------|-------|-------|
| POST /invites/ | 10/hour | Per user |
| POST /join/ | 20/hour | Per user |
| GET /invites/ | Unlimited | - |
| DELETE /invites/{id}/ | Unlimited | - |

---

## Common Workflows

### Workflow 1: Owner invites new collaborator

1. Owner creates invitation:
   ```bash
   POST /organisations/{id}/invites/
   → Returns code: "ABCD1234"
   ```

2. Owner shares code with invitee (email, chat, etc.)

3. Invitee joins using code:
   ```bash
   POST /organisations/join/
   Body: { "code": "ABCD1234", "job_title": "Developer" }
   → Returns collaborator record
   ```

4. Owner verifies membership:
   ```bash
   GET /organisations/{id}/collaborators/
   → Shows new collaborator in list
   ```

---

### Workflow 2: Owner manages invitations

1. Owner lists all invitations:
   ```bash
   GET /organisations/{id}/invites/
   ```

2. Owner filters active invitations:
   ```bash
   GET /organisations/{id}/invites/?status=active
   ```

3. Owner revokes unused invitation:
   ```bash
   DELETE /organisations/{id}/invites/{invite_id}/
   ```

4. Owner checks status:
   ```bash
   GET /organisations/{id}/invites/
   → Revoked invitation no longer appears
   ```

---

### Workflow 3: Handle expired invitation

1. User tries to join with expired code:
   ```bash
   POST /organisations/join/
   Body: { "code": "EXPIRED1" }
   → 400 Bad Request: "Invitation has expired"
   ```

2. Owner creates new invitation:
   ```bash
   POST /organisations/{id}/invites/
   Body: { "expires_in_hours": 24 }
   → Returns new code: "NEWCODE1"
   ```

3. User successfully joins with new code:
   ```bash
   POST /organisations/join/
   Body: { "code": "NEWCODE1" }
   → 201 Created
   ```

---

## Development Notes

### Database Queries

```python
# Get active invitations
OrganisationInvite.objects.active()

# Get expired invitations
OrganisationInvite.objects.expired()

# Get used invitations
OrganisationInvite.objects.used()

# Check invitation status
invite.status  # Returns: "active", "expired", or "used"
```

### Management Command

```bash
# Clean up old expired invitations
python manage.py cleanup_expired_invites --days=30

# Dry run to preview deletions
python manage.py cleanup_expired_invites --dry-run

# Include used invitations in cleanup
python manage.py cleanup_expired_invites --include-used
```

---

## Security Notes

1. **Codes are case-insensitive** - "abcd1234" and "ABCD1234" are equivalent
2. **Whitespace is automatically trimmed** - " ABCD1234 " becomes "ABCD1234"
3. **Codes use cryptographic randomness** - Generated with Python's `secrets` module
4. **Row-level locking prevents race conditions** - `select_for_update()` ensures atomicity
5. **Rate limiting protects against brute force** - 20 attempts/hour for joining
6. **Used invitations cannot be revoked** - Maintains audit trail
