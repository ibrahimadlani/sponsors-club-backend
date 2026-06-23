# Système d'Invitations - Guide Utilisateur

## Vue d'ensemble

Le système d'invitations permet aux propriétaires d'organisations d'inviter de nouveaux collaborateurs via des codes uniques et sécurisés à durée limitée.

## Concepts clés

### Types de statuts d'invitation

- **`active`** – Invitation valide et utilisable (non expirée, non utilisée)
- **`expired`** – Invitation expirée (dépassé la date d'expiration)
- **`used`** – Invitation déjà utilisée par un collaborateur

### Durée de validité

- **Par défaut** : 72 heures (3 jours)
- **Minimum** : 1 heure
- **Maximum** : 168 heures (7 jours)

### Sécurité

- **Codes cryptographiques** : Générés avec le module `secrets` de Python
- **Format** : 8 caractères majuscules (alphabet de 33 caractères)
- **Usage unique** : Un code ne peut être utilisé qu'une seule fois
- **Rate limiting** : Protection contre les abus et les attaques brute force

---

## Workflow complet

### 1. Création d'une invitation

**Endpoint :** `POST /api/organisations/{org_id}/invites/`

**Permissions :** Propriétaire de l'organisation uniquement

**Payload :**
```json
{
  "expires_in_hours": 48  // Optionnel, défaut: 72
}
```

**Réponse (201 Created) :**
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

**Exemple cURL :**
```bash
curl -X POST https://api.example.com/api/organisations/550e8400.../invites/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"expires_in_hours": 48}'
```

**Limites :**
- **Rate limit** : 10 créations par heure par utilisateur
- **Plan requis** : La fonctionnalité `collaborator_invites` doit être activée dans votre plan
- **Quota** : Respecte la limite `max_collaborators` de votre plan

---

### 2. Lister les invitations

**Endpoint :** `GET /api/organisations/{org_id}/invites/?status=<active|expired|used>`

**Permissions :** Propriétaire de l'organisation

**Paramètres de requête :**
- `status` (optionnel) : Filtre par statut (`active`, `expired`, `used`)

**Réponse (200 OK) :**
```json
[
  {
    "id": "...",
    "code": "ABCD1234",
    "created_at": "2026-01-07T10:00:00Z",
    "expires_at": "2026-01-09T10:00:00Z",
    "is_used": false,
    "used_at": null,
    "created_by": "owner@example.com",
    "status": "active"
  },
  {
    "id": "...",
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

**Exemples cURL :**
```bash
# Toutes les invitations
curl https://api.example.com/api/organisations/550e8400.../invites/ \
  -H "Authorization: Bearer YOUR_TOKEN"

# Seulement les invitations actives
curl https://api.example.com/api/organisations/550e8400.../invites/?status=active \
  -H "Authorization: Bearer YOUR_TOKEN"

# Seulement les invitations expirées
curl https://api.example.com/api/organisations/550e8400.../invites/?status=expired \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

### 3. Rejoindre une organisation via invitation

**Endpoint :** `POST /api/organisations/join/`

**Permissions :** Utilisateur authentifié avec compte de type COLLABORATOR

**Payload :**
```json
{
  "code": "ABCD1234",
  "job_title": "Software Engineer"  // Optionnel, défaut: "Member"
}
```

**Réponse (201 Created) :**
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

**Exemple cURL :**
```bash
curl -X POST https://api.example.com/api/organisations/join/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "ABCD1234",
    "job_title": "Software Engineer"
  }'
```

**Limites :**
- **Rate limit** : 20 tentatives par heure par utilisateur
- **Compte requis** : Type COLLABORATOR uniquement (pas AGENT)
- **Organisation unique** : Un utilisateur ne peut appartenir qu'à une seule organisation

---

### 4. Révoquer une invitation

**Endpoint :** `DELETE /api/organisations/{org_id}/invites/{invite_id}/`

**Permissions :** Propriétaire de l'organisation uniquement

**Réponse (204 No Content)** – Succès, aucun contenu retourné

**Exemple cURL :**
```bash
curl -X DELETE https://api.example.com/api/organisations/550e8400.../invites/invite-uuid/ \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Restrictions :**
- ❌ Impossible de révoquer une invitation déjà utilisée
- ✅ Possible de révoquer une invitation active ou expirée

---

## Gestion des erreurs

### Erreurs courantes et solutions

#### 400 Bad Request - "Invalid invitation code"
**Cause :** Le code n'existe pas ou est mal formaté

**Solution :**
- Vérifier que le code est correct
- Respecter la casse (le système normalise automatiquement en majuscules)
- Vérifier qu'il n'y a pas d'espaces superflus

#### 400 Bad Request - "Invitation has expired"
**Cause :** Le code a dépassé sa durée de validité

**Solution :**
- Demander au propriétaire de générer un nouveau code
- Utiliser le nouveau code dans les 72 heures (ou durée personnalisée)

#### 400 Bad Request - "Invitation has already been used"
**Cause :** Le code a déjà été utilisé par un autre utilisateur

**Solution :**
- Demander un nouveau code au propriétaire
- Vérifier que vous n'avez pas déjà rejoint l'organisation

#### 400 Bad Request - "Only collaborator accounts may join organisations"
**Cause :** Votre compte est de type AGENT

**Solution :**
- Les comptes AGENT ne peuvent pas rejoindre d'organisations
- Créer un compte COLLABORATOR séparé si nécessaire

#### 400 Bad Request - "User already belongs to an organisation"
**Cause :** Vous êtes déjà membre d'une autre organisation

**Solution :**
- Un utilisateur ne peut appartenir qu'à une seule organisation
- Quitter votre organisation actuelle avant de rejoindre une nouvelle

#### 400 Bad Request - "Cannot revoke an invitation that has already been used"
**Cause :** Tentative de suppression d'une invitation déjà utilisée

**Solution :**
- Les invitations utilisées ne peuvent pas être révoquées (pour des raisons d'audit)
- Retirer le collaborateur de l'organisation si nécessaire

#### 403 Forbidden - "Only organisation owners can..."
**Cause :** Vous n'êtes pas propriétaire de l'organisation

**Solution :**
- Seuls les propriétaires peuvent créer, lister ou révoquer des invitations
- Demander au propriétaire d'effectuer l'action

#### 403 Forbidden - "Upgrade your organisation plan to..."
**Cause :** Votre plan ne permet pas cette fonctionnalité ou limite atteinte

**Solution :**
- Mettre à niveau votre abonnement organisation
- Vérifier les limites de votre plan actuel

#### 404 Not Found - "Invitation not found"
**Cause :** L'ID d'invitation n'existe pas ou ne correspond pas à votre organisation

**Solution :**
- Vérifier l'ID de l'invitation
- S'assurer que l'invitation appartient bien à votre organisation

#### 429 Too Many Requests
**Cause :** Limite de taux dépassée

**Solution :**
- Attendre 1 heure avant de réessayer
- Pour la création : max 10 invitations/heure
- Pour rejoindre : max 20 tentatives/heure

---

## Exemples d'intégration

### React / JavaScript

#### Créer une invitation et copier le lien

```javascript
async function createAndShareInvite(orgId, expiresInHours = 72) {
  const response = await fetch(`/api/organisations/${orgId}/invites/`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${getToken()}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ expires_in_hours: expiresInHours })
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to create invitation');
  }

  const invite = await response.json();

  // Générer l'URL de join
  const joinUrl = `${window.location.origin}/join?code=${invite.code}`;

  // Copier dans le presse-papiers
  await navigator.clipboard.writeText(joinUrl);

  // Afficher notification
  alert(`Lien d'invitation copié !
  Expire le ${new Date(invite.expires_at).toLocaleString()}
  Code: ${invite.code}`);

  return invite;
}
```

#### Lister les invitations actives

```javascript
async function getActiveInvites(orgId) {
  const response = await fetch(
    `/api/organisations/${orgId}/invites/?status=active`,
    {
      headers: {
        'Authorization': `Bearer ${getToken()}`
      }
    }
  );

  if (!response.ok) {
    throw new Error('Failed to fetch invitations');
  }

  return await response.json();
}
```

#### Rejoindre via invitation

```javascript
async function joinOrganisation(code, jobTitle) {
  const response = await fetch('/api/organisations/join/', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${getToken()}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      code: code.trim().toUpperCase(), // Normaliser le code
      job_title: jobTitle
    })
  });

  if (!response.ok) {
    const error = await response.json();

    // Gestion des erreurs spécifiques
    if (error.code) {
      if (error.code[0].includes('expired')) {
        throw new Error('Ce code d\'invitation a expiré. Demandez un nouveau code.');
      } else if (error.code[0].includes('already been used')) {
        throw new Error('Ce code a déjà été utilisé.');
      } else if (error.code[0].includes('Invalid')) {
        throw new Error('Code d\'invitation invalide.');
      }
    }

    throw new Error('Impossible de rejoindre l\'organisation');
  }

  return await response.json();
}
```

#### Révoquer une invitation

```javascript
async function revokeInvite(orgId, inviteId) {
  const response = await fetch(
    `/api/organisations/${orgId}/invites/${inviteId}/`,
    {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${getToken()}`
      }
    }
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to revoke invitation');
  }

  return true; // 204 No Content
}
```

#### Composant React complet

```jsx
import React, { useState, useEffect } from 'react';

function InvitationManager({ orgId }) {
  const [invites, setInvites] = useState([]);
  const [statusFilter, setStatusFilter] = useState('active');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadInvites();
  }, [statusFilter]);

  async function loadInvites() {
    setLoading(true);
    try {
      const data = await getActiveInvites(orgId, statusFilter);
      setInvites(data);
    } catch (error) {
      console.error('Error loading invites:', error);
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateInvite() {
    try {
      await createAndShareInvite(orgId, 48);
      await loadInvites(); // Refresh list
    } catch (error) {
      alert('Erreur lors de la création: ' + error.message);
    }
  }

  async function handleRevoke(inviteId) {
    if (!confirm('Êtes-vous sûr de vouloir révoquer cette invitation ?')) {
      return;
    }

    try {
      await revokeInvite(orgId, inviteId);
      await loadInvites(); // Refresh list
    } catch (error) {
      alert('Erreur lors de la révocation: ' + error.message);
    }
  }

  return (
    <div className="invitation-manager">
      <div className="actions">
        <button onClick={handleCreateInvite}>
          Créer une invitation
        </button>

        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="active">Actives</option>
          <option value="expired">Expirées</option>
          <option value="used">Utilisées</option>
        </select>
      </div>

      {loading ? (
        <p>Chargement...</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Code</th>
              <th>Créé le</th>
              <th>Expire le</th>
              <th>Statut</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {invites.map(invite => (
              <tr key={invite.id}>
                <td><code>{invite.code}</code></td>
                <td>{new Date(invite.created_at).toLocaleDateString()}</td>
                <td>{new Date(invite.expires_at).toLocaleDateString()}</td>
                <td>
                  <span className={`badge badge-${invite.status}`}>
                    {invite.status}
                  </span>
                </td>
                <td>
                  {invite.status === 'active' && (
                    <button
                      onClick={() => handleRevoke(invite.id)}
                      className="btn-danger"
                    >
                      Révoquer
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default InvitationManager;
```

---

## Bonnes pratiques

### Pour les propriétaires d'organisations

✅ **Faire :**
- Générer des codes avec une durée adaptée au contexte (24h pour urgence, 7 jours pour processus long)
- Révoquer les codes non utilisés si le recrutement est annulé
- Surveiller les invitations expirées et les supprimer régulièrement
- Utiliser des durées courtes pour des invitations sensibles

❌ **Éviter :**
- Partager publiquement les codes d'invitation
- Créer trop d'invitations simultanément (rate limit: 10/heure)
- Laisser des invitations actives indéfiniment
- Ignorer les invitations expirées (nettoyage recommandé)

### Pour les utilisateurs rejoignant une organisation

✅ **Faire :**
- Utiliser le code dès réception
- Vérifier que vous êtes connecté avec le bon compte (COLLABORATOR)
- Copier-coller le code pour éviter les erreurs de saisie
- Contacter le propriétaire si le code a expiré

❌ **Éviter :**
- Partager votre code d'invitation avec d'autres
- Attendre trop longtemps avant d'utiliser le code
- Essayer de rejoindre si vous êtes déjà dans une autre organisation

---

## FAQ

### Puis-je modifier la durée d'expiration d'une invitation existante ?
Non, il n'est pas possible de modifier une invitation existante. Révoquez l'ancienne et créez-en une nouvelle avec la durée souhaitée.

### Que se passe-t-il si j'essaie d'utiliser un code expiré ?
Vous recevrez une erreur 400 avec le message "Invitation has expired". Demandez au propriétaire de générer un nouveau code.

### Puis-je voir qui a utilisé une invitation ?
Oui, le champ `used_by` dans la réponse de liste contient l'ID de l'utilisateur qui a utilisé le code. Les propriétaires peuvent également voir la liste des collaborateurs pour identifier les nouveaux membres.

### Combien d'invitations puis-je créer ?
Vous êtes limité à 10 créations par heure. Au-delà, vous devrez attendre avant de pouvoir créer de nouvelles invitations.

### Les codes sont-ils sensibles à la casse ?
Non, les codes sont automatiquement normalisés en majuscules. "abcd1234" et "ABCD1234" sont équivalents.

### Puis-je réutiliser un code révoqué ?
Non, une fois révoqué, un code est supprimé de la base de données. Il faudra générer un nouveau code.

### Que faire si je dépasse le quota de collaborateurs ?
Vous devrez mettre à niveau votre plan d'organisation pour augmenter la limite `max_collaborators`. Consultez `/api/users/me/entitlements/` pour voir vos limites actuelles.

---

## Support et dépannage

### Logs et debugging

Pour les administrateurs système, les opérations d'invitation sont tracées via :
- Logs Django standard (création, utilisation, révocation)
- Possibilité d'activer l'audit logging pour une traçabilité complète

### Monitoring

Métriques recommandées à surveiller :
- Taux de conversion (invitations utilisées vs expirées)
- Temps moyen avant utilisation
- Violations de rate limit
- Invitations expirées non nettoyées

### Maintenance

Nettoyage automatique recommandé :
```bash
# Dans un cron job quotidien
0 2 * * * cd /app && python manage.py cleanup_expired_invites --days=30
```

---

## Changelog des fonctionnalités

### Version 2.0 (Actuelle)
- ✨ Ajout du filtrage par statut (`?status=active|expired|used`)
- ✨ Endpoint de révocation (`DELETE /invites/{id}/`)
- ✨ Propriété `status` calculée dynamiquement
- 🔒 Protection contre les race conditions (`select_for_update`)
- 🔒 Rate limiting (10/heure création, 20/heure utilisation)
- 📦 Management command `cleanup_expired_invites`
- 🧪 Suite de tests complète pour edge cases

### Version 1.0 (Legacy)
- Création d'invitations
- Liste des invitations
- Rejoindre via code
- Validation d'expiration et d'usage unique
