# Plan de Développement - Négociation de Contrats de Sponsoring

## 🎯 Objectif Global

Permettre une négociation complète et conforme au droit français entre une organisation (via ses collaborateurs) et un athlète (via son agent) pour des contrats de sponsoring, avec signature électronique simple et validation juridique.

---

## 📋 Récapitulatif des Exigences

### Workflow de Négociation
- **Initiation** : Seules les organisations peuvent créer un draft de contrat
- **Type** : Propositions/contre-propositions avec révisions (Option A)
- **Accord** : Si une partie modifie après accord partiel → révocation automatique + nouveau cycle
- **Clauses obligatoires** : Non modifiables, non supprimables (conformité légale)
- **Clauses custom** : Les deux parties peuvent ajouter des clauses personnalisées
- **Placeholders** : Initiateur remplit, les deux peuvent modifier (sauf champs protégés)

### Signature & Validation
- **Type de signature** : Simple (clic "J'accepte" avec horodatage)
- **Templates** : Pré-validés par un juriste
- **Mandat** : Agent doit prouver mandat de représentation, collaborateur aussi
- **Ordre** : Signature séquentielle (une partie puis l'autre)
- **Revue légale** : Obligatoire après accord mutuel, validation par staff uniquement

### Auditabilité & Traçabilité
- **Versioning** : Snapshot complet à chaque proposition de révision
- **Audit** : 100% auditable (IP, user-agent, timestamps, snapshots)
- **Archive** : Conservation des contrats expirés/terminés

### Notifications
- Nouvelle proposition
- Modification de clause
- Accord partiel
- Accord complet
- Signature complétée
- Revue légale requise

### UX
- Diff visuel entre versions
- Commentaires inline sur clauses
- Chat/messaging intégré au contrat

### Contraintes Métier
- Durée déterminée uniquement
- Visibilité : Collaborateurs + Agent + Staff uniquement
- 1 contrat = 1 athlète (pas de contrats multi-athlètes)

---

## 🏗️ Architecture Proposée

### État Actuel (Existant)

✅ **Modèles complets** :
- `ClauseTemplate` avec catégories et placeholders
- `Contract` avec statuts workflow et dual agreement
- `ContractClause` avec tracking de modifications
- `ContractRevision` pour propositions de changements
- `ContractVersion` pour snapshots
- `ContractComment` pour collaboration
- `ContractLegalReview` pour validation juridique
- `ContractSigning` pour signature électronique
- `ContractFile` pour PDFs signés

✅ **Workflow de base** :
- DRAFT → NEGOTIATION → AGREEMENT → LEGAL_REVIEW → SIGNING → ACTIVE
- Création par collaborateur avec clauses obligatoires auto-ajoutées
- Système de révisions avec acceptation
- Accord dual (owner_agreed_at, agent_agreed_at)

### Lacunes Identifiées

❌ **Manquant pour négociation complète** :
1. Rejet de révision (pas d'endpoint)
2. Snapshots de clauses dans ContractVersion (pas de contenu stocké)
3. Agents ne peuvent pas éditer les clauses directement
4. Pas de comparaison de versions (diff)
5. Pas de gestion des placeholders protégés vs modifiables
6. Pas de système de notifications
7. Pas de chat/messaging intégré
8. Pas de vérification de mandat de représentation
9. Révocation d'accord partiel pas automatique
10. Pas d'audit logging IP/user-agent

---

## 📐 Plan de Développement Structuré

### 🔴 **PHASE 1 - Fondations Critiques** (Priorité Haute)

#### 1.1 - Amélioration du Modèle ContractVersion

**Objectif** : Capturer un snapshot complet du contrat à chaque révision

**Modifications** :
```python
# contracts/models.py

class ContractVersion(BaseModel):
    # ... champs existants ...

    # AJOUT : Snapshot des clauses
    clauses_snapshot = models.JSONField(
        default=dict,
        help_text="Snapshot complet des clauses au moment de la version"
    )

    # AJOUT : Métadonnées d'accord
    agreement_status = models.JSONField(
        default=dict,
        help_text="État des accords (owner_agreed, agent_agreed) au moment du snapshot"
    )

    def capture_snapshot(self, contract):
        """Capture l'état complet du contrat."""
        clauses_data = []
        for clause in contract.clauses.all():
            clauses_data.append({
                'id': str(clause.id),
                'title': clause.title,
                'content': clause.content,
                'is_mandatory': clause.is_mandatory,
                'is_modified': clause.is_modified,
                'template_id': str(clause.template_id) if clause.template else None,
                'category': clause.template.category if clause.template else 'custom',
            })

        self.clauses_snapshot = {
            'clauses': clauses_data,
            'title': contract.title,
            'effective_date': contract.effective_date.isoformat() if contract.effective_date else None,
            'expiration_date': contract.expiration_date.isoformat() if contract.expiration_date else None,
        }

        self.agreement_status = {
            'owner_agreed_at': contract.owner_agreed_at.isoformat() if contract.owner_agreed_at else None,
            'agent_agreed_at': contract.agent_agreed_at.isoformat() if contract.agent_agreed_at else None,
        }

        self.save(update_fields=['clauses_snapshot', 'agreement_status', 'updated_at'])
```

**Migration** :
```bash
python manage.py makemigrations contracts --name add_version_snapshots
```

**Tests** :
- Test que capture_snapshot sauvegarde toutes les clauses
- Test que les snapshots sont immuables
- Test de récupération d'un snapshot pour comparaison

---

#### 1.2 - Système d'Audit Complet

**Objectif** : Traçabilité 100% pour conformité légale

**Nouveau modèle** :
```python
# contracts/models.py

class ContractAuditLog(BaseModel):
    """Log d'audit pour toutes les opérations sur un contrat."""

    ACTION_CHOICES = [
        ('CONTRACT_CREATED', 'Contract Created'),
        ('CLAUSE_ADDED', 'Clause Added'),
        ('CLAUSE_MODIFIED', 'Clause Modified'),
        ('CLAUSE_DELETED', 'Clause Deleted'),
        ('REVISION_PROPOSED', 'Revision Proposed'),
        ('REVISION_ACCEPTED', 'Revision Accepted'),
        ('REVISION_REJECTED', 'Revision Rejected'),
        ('AGREEMENT_RECORDED', 'Agreement Recorded'),
        ('AGREEMENT_REVOKED', 'Agreement Revoked'),
        ('STATUS_CHANGED', 'Status Changed'),
        ('COMMENT_ADDED', 'Comment Added'),
        ('LEGAL_REVIEW_REQUESTED', 'Legal Review Requested'),
        ('LEGAL_REVIEW_VERIFIED', 'Legal Review Verified'),
        ('SIGNING_INITIATED', 'Signing Initiated'),
        ('SIGNATURE_COMPLETED', 'Signature Completed'),
    ]

    contract = models.ForeignKey(
        'Contract',
        on_delete=models.CASCADE,
        related_name='audit_logs'
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )

    # Métadonnées de sécurité
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    # Détails de l'action
    metadata = models.JSONField(
        default=dict,
        help_text="Détails spécifiques à l'action (ex: clause_id, old_value, new_value)"
    )

    # Snapshot au moment de l'action
    contract_snapshot = models.JSONField(
        default=dict,
        help_text="État du contrat au moment de l'action"
    )

    class Meta:
        db_table = 'contract_audit_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['contract', '-created_at']),
            models.Index(fields=['action', '-created_at']),
        ]
```

**Service d'audit** :
```python
# contracts/services.py

def log_contract_action(
    contract,
    action,
    user,
    request=None,
    **metadata
):
    """Enregistre une action d'audit avec toutes les métadonnées."""
    from contracts.models import ContractAuditLog

    log_data = {
        'contract': contract,
        'action': action,
        'performed_by': user,
        'metadata': metadata,
    }

    if request:
        log_data['ip_address'] = request.META.get('REMOTE_ADDR')
        log_data['user_agent'] = request.META.get('HTTP_USER_AGENT', '')

    # Snapshot minimal du contrat
    log_data['contract_snapshot'] = {
        'status': contract.status,
        'version': contract.current_version_number,
        'owner_agreed': bool(contract.owner_agreed_at),
        'agent_agreed': bool(contract.agent_agreed_at),
    }

    return ContractAuditLog.objects.create(**log_data)
```

---

#### 1.3 - Révocation Automatique d'Accord

**Objectif** : Si une partie modifie après accord partiel → révocation auto

**Implémentation** :
```python
# contracts/serializers.py

class ContractClauseUpdateSerializer(serializers.ModelSerializer):
    # ... champs existants ...

    def update(self, instance, validated_data):
        contract = instance.contract
        user = self.context['request'].user

        # Vérifier si une partie avait déjà donné son accord
        owner_had_agreed = bool(contract.owner_agreed_at)
        agent_had_agreed = bool(contract.agent_agreed_at)

        # Déterminer qui modifie
        is_owner_modifying = # ... logique pour identifier
        is_agent_modifying = # ... logique pour identifier

        # Révocation automatique de l'accord de l'autre partie
        if is_owner_modifying and agent_had_agreed:
            contract.agent_agreed_at = None
            contract.save(update_fields=['agent_agreed_at', 'updated_at'])

            # Log audit
            log_contract_action(
                contract=contract,
                action='AGREEMENT_REVOKED',
                user=user,
                request=self.context.get('request'),
                revoked_party='agent',
                reason='clause_modified_by_owner',
                clause_id=str(instance.id)
            )

        elif is_agent_modifying and owner_had_agreed:
            contract.owner_agreed_at = None
            contract.save(update_fields=['owner_agreed_at', 'updated_at'])

            log_contract_action(
                contract=contract,
                action='AGREEMENT_REVOKED',
                user=user,
                request=self.context.get('request'),
                revoked_party='owner',
                reason='clause_modified_by_agent',
                clause_id=str(instance.id)
            )

        # Mise à jour de la clause
        instance = super().update(instance, validated_data)

        # Log de modification
        log_contract_action(
            contract=contract,
            action='CLAUSE_MODIFIED',
            user=user,
            request=self.context.get('request'),
            clause_id=str(instance.id),
            clause_title=instance.title
        )

        return instance
```

---

#### 1.4 - Permission d'Édition pour les Agents

**Objectif** : Permettre aux agents d'éditer les clauses pendant la négociation

**Modification** :
```python
# contracts/views.py

class ContractViewSet(viewsets.ModelViewSet):

    def _can_edit_clauses(self, user, contract) -> bool:
        """Vérifie si l'utilisateur peut éditer les clauses."""
        # Collaborateurs pendant DRAFT/NEGOTIATION
        if self._is_collaborator(user, contract.organisation):
            return contract.status in [Contract.Status.DRAFT, Contract.Status.NEGOTIATION]

        # NOUVEAU : Agents pendant NEGOTIATION
        if contract.agent and contract.agent.user == user:
            return contract.status == Contract.Status.NEGOTIATION

        return False
```

---

#### 1.5 - Rejet de Révision

**Objectif** : Endpoint pour rejeter une révision proposée

**Nouveau endpoint** :
```python
# contracts/views.py

@action(
    detail=True,
    methods=['post'],
    url_path='revisions/(?P<revision_id>[^/.]+)/reject',
)
def reject_revision(self, request, pk=None, revision_id=None):
    """Rejette une révision proposée."""
    contract = self.get_object()

    try:
        revision = ContractRevision.objects.get(
            id=revision_id,
            contract=contract
        )
    except ContractRevision.DoesNotExist:
        return Response(
            {'detail': 'Revision not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    # Vérifier que la révision est en attente
    if revision.accepted is not None:
        return Response(
            {'detail': 'Revision already processed'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Vérifier les permissions (pas le proposeur)
    if revision.proposed_by == request.user:
        return Response(
            {'detail': 'Cannot reject your own revision'},
            status=status.HTTP_403_FORBIDDEN
        )

    if not self._can_respond_to_revision(request.user, contract):
        return Response(
            {'detail': 'Not authorized to reject revisions'},
            status=status.HTTP_403_FORBIDDEN
        )

    # Marquer comme rejetée
    revision.accepted = False
    revision.save(update_fields=['accepted', 'updated_at'])

    # Log audit
    log_contract_action(
        contract=contract,
        action='REVISION_REJECTED',
        user=request.user,
        request=request,
        revision_id=str(revision.id),
        rejected_by=request.user.email
    )

    # TODO: Notification au proposeur

    return Response(
        ContractRevisionSerializer(revision).data,
        status=status.HTTP_200_OK
    )
```

---

### 🟡 **PHASE 2 - Gestion des Placeholders** (Priorité Moyenne)

#### 2.1 - Modèle de Placeholder avec Contraintes

**Objectif** : Différencier les placeholders modifiables des protégés

**Extension du modèle** :
```python
# contracts/models.py

class ContractClause(BaseModel):
    # ... champs existants ...

    # AJOUT : Valeurs des placeholders
    placeholder_values = models.JSONField(
        default=dict,
        help_text="Valeurs des placeholders {key: value}"
    )

    # AJOUT : Placeholders verrouillés
    locked_placeholders = models.JSONField(
        default=list,
        help_text="Liste des clés de placeholders non modifiables"
    )

    def render_content(self):
        """Rend le contenu avec les placeholders remplacés."""
        rendered = self.content
        for key, value in self.placeholder_values.items():
            placeholder = f"{{{{{key}}}}}"
            rendered = rendered.replace(placeholder, str(value))
        return rendered

    def can_modify_placeholder(self, placeholder_key):
        """Vérifie si un placeholder peut être modifié."""
        return placeholder_key not in self.locked_placeholders
```

**Serializer** :
```python
# contracts/serializers.py

class PlaceholderValueSerializer(serializers.Serializer):
    """Valide les mises à jour de placeholders."""

    placeholder_values = serializers.JSONField()

    def validate_placeholder_values(self, value):
        clause = self.context['clause']

        # Vérifier que tous les placeholders fournis existent
        template_placeholders = clause.template.placeholders if clause.template else []
        valid_keys = set(p['key'] for p in template_placeholders) if template_placeholders else set()

        for key in value.keys():
            if valid_keys and key not in valid_keys:
                raise serializers.ValidationError(
                    f"Placeholder '{key}' not found in template"
                )

            # Vérifier verrouillage
            if not clause.can_modify_placeholder(key):
                raise serializers.ValidationError(
                    f"Placeholder '{key}' is locked and cannot be modified"
                )

        return value
```

---

#### 2.2 - Vérification de Mandat de Représentation

**Objectif** : S'assurer que l'agent a mandat pour l'athlète et le collaborateur pour l'organisation

**Nouveau modèle** :
```python
# contracts/models.py

class RepresentationMandate(BaseModel):
    """Preuve de mandat de représentation."""

    # Pour agents
    agent = models.ForeignKey(
        AgentProfile,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='mandates'
    )
    athlete = models.ForeignKey(
        'athletes.Athlete',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='mandates'
    )

    # Pour collaborateurs
    collaborator = models.ForeignKey(
        Collaborator,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='mandates'
    )
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='mandates'
    )

    # Preuve
    document = models.FileField(
        upload_to='mandates/',
        help_text="Document de mandat (PDF)"
    )
    verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_mandates'
    )
    verified_at = models.DateTimeField(null=True, blank=True)

    valid_from = models.DateField()
    valid_until = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            # XOR : soit agent+athlete, soit collaborator+organisation
            models.CheckConstraint(
                check=(
                    models.Q(agent__isnull=False, athlete__isnull=False, collaborator__isnull=True, organisation__isnull=True) |
                    models.Q(agent__isnull=True, athlete__isnull=True, collaborator__isnull=False, organisation__isnull=False)
                ),
                name='mandate_xor_agent_or_collaborator'
            )
        ]
```

**Validation lors de la signature** :
```python
# contracts/views.py

@action(detail=True, methods=['post'], url_path='signing/init')
def init_signing(self, request, pk=None):
    contract = self.get_object()

    # Vérifier les mandats
    if not self._has_valid_mandate(contract):
        return Response(
            {
                'detail': 'Valid representation mandate required for signing',
                'missing_mandates': self._get_missing_mandates(contract)
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    # ... reste de la logique
```

---

### 🟢 **PHASE 3 - UX Avancée** (Priorité Basse)

#### 3.1 - Comparaison de Versions (Diff)

**Endpoint** :
```python
@action(
    detail=True,
    methods=['get'],
    url_path='versions/(?P<version1>[0-9]+)/compare/(?P<version2>[0-9]+)',
)
def compare_versions(self, request, pk=None, version1=None, version2=None):
    """Compare deux versions et retourne un diff."""
    contract = self.get_object()

    try:
        v1 = ContractVersion.objects.get(contract=contract, number=version1)
        v2 = ContractVersion.objects.get(contract=contract, number=version2)
    except ContractVersion.DoesNotExist:
        return Response(
            {'detail': 'Version not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    # Générer le diff
    diff = generate_version_diff(v1, v2)

    return Response({
        'version1': version1,
        'version2': version2,
        'diff': diff,
        'summary': {
            'clauses_added': len(diff['added']),
            'clauses_removed': len(diff['removed']),
            'clauses_modified': len(diff['modified']),
        }
    })
```

---

#### 3.2 - Commentaires Inline avec Threading

**Extension du modèle** :
```python
class ContractComment(BaseModel):
    # ... champs existants ...

    # AJOUT : Threading
    parent_comment = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replies'
    )

    # AJOUT : Statut résolu
    is_resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_comments'
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
```

---

#### 3.3 - Système de Notifications

**Nouveau modèle** :
```python
# contracts/models.py

class ContractNotification(BaseModel):
    """Notifications liées aux contrats."""

    NOTIFICATION_TYPES = [
        ('CONTRACT_PROPOSED', 'New contract proposed'),
        ('CLAUSE_MODIFIED', 'Clause modified'),
        ('REVISION_PROPOSED', 'Revision proposed'),
        ('REVISION_ACCEPTED', 'Revision accepted'),
        ('REVISION_REJECTED', 'Revision rejected'),
        ('AGREEMENT_PARTIAL', 'Partial agreement reached'),
        ('AGREEMENT_FULL', 'Full agreement reached'),
        ('LEGAL_REVIEW_REQUIRED', 'Legal review required'),
        ('SIGNATURE_READY', 'Ready for signature'),
        ('SIGNATURE_COMPLETED', 'Signature completed'),
        ('COMMENT_ADDED', 'Comment added'),
    ]

    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='contract_notifications'
    )
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPES)

    # Contenu
    title = models.CharField(max_length=255)
    message = models.TextField()
    metadata = models.JSONField(default=dict)

    # Statut
    read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'read', '-created_at']),
        ]
```

**Service de notification** :
```python
# contracts/services.py

def send_contract_notification(
    contract,
    recipients,
    notification_type,
    title,
    message,
    **metadata
):
    """Envoie une notification à plusieurs destinataires."""
    from contracts.models import ContractNotification

    notifications = []
    for recipient in recipients:
        notification = ContractNotification.objects.create(
            contract=contract,
            recipient=recipient,
            notification_type=notification_type,
            title=title,
            message=message,
            metadata=metadata
        )
        notifications.append(notification)

    # TODO: Envoyer email/push notification

    return notifications
```

---

## 📅 Chronologie de Développement

### Sprint 1 (2-3 semaines) - Fondations
- ✅ Snapshots dans ContractVersion
- ✅ Système d'audit complet
- ✅ Révocation automatique d'accord
- ✅ Permission édition pour agents
- ✅ Endpoint de rejet de révision
- ✅ Tests unitaires et d'intégration

### Sprint 2 (2 semaines) - Placeholders & Mandats
- ✅ Gestion des placeholders avec verrouillage
- ✅ Modèle RepresentationMandate
- ✅ Validation des mandats
- ✅ Interface d'upload de documents
- ✅ Tests

### Sprint 3 (2 semaines) - UX & Notifications
- ✅ Endpoint de comparaison de versions
- ✅ Threading de commentaires
- ✅ Système de notifications
- ✅ Intégration avec système de messaging existant
- ✅ Tests

### Sprint 4 (1 semaine) - Polissage & Documentation
- ✅ Documentation API complète
- ✅ Guide utilisateur
- ✅ Tests E2E
- ✅ Performance tuning

---

## 🧪 Stratégie de Tests

### Tests Unitaires
- Snapshots de ContractVersion
- Révocation automatique d'accord
- Validation de placeholders verrouillés
- Génération de diffs
- Threading de commentaires

### Tests d'Intégration
- Workflow complet de négociation
- Acceptation/rejet de révisions
- Système d'audit
- Notifications

### Tests E2E
- Scénario complet : Proposition → Négociation → Accord → Revue → Signature
- Scénario avec rejets multiples
- Scénario avec révocation d'accord

---

## 📚 Documentation Requise

1. **Guide API** : Tous les nouveaux endpoints avec exemples
2. **Guide Utilisateur** : Workflow de négociation illustré
3. **Guide Conformité** : Aspects légaux et auditabilité
4. **Guide Admin** : Validation des mandats, revue légale
5. **Architecture Decision Records** : Choix techniques

---

## 🔒 Checklist de Conformité Juridique

### Droit des Contrats (France)
- [ ] Mentions légales obligatoires dans templates
- [ ] Durée déterminée clairement définie
- [ ] Conditions de résiliation explicites
- [ ] Juridiction compétente mentionnée
- [ ] Consentement libre et éclairé (double vérification)
- [ ] Conservation des preuves (10 ans minimum)
- [ ] Horodatage certifié des signatures

### RGPD
- [ ] Consentement tracé pour traitement de données
- [ ] Droit d'accès aux logs d'audit
- [ ] Anonymisation après archivage
- [ ] Suppression sur demande (avec contraintes légales)

### Signature Électronique (eIDAS)
- [ ] Identification du signataire
- [ ] Horodatage qualifié
- [ ] Intégrité du document
- [ ] Conservation sécurisée

---

## 🎯 Métriques de Succès

### Techniques
- Couverture de tests > 90%
- Temps de réponse API < 200ms
- Zéro perte de données dans les snapshots
- 100% des actions auditées

### Métier
- Taux de signature des contrats > 80%
- Temps moyen de négociation < 7 jours
- Satisfaction utilisateur > 4/5
- Conformité juridique 100%

---

## 🚀 Prochaines Étapes Immédiates

1. **Valider ce plan** avec l'équipe juridique
2. **Créer les tickets JIRA** pour Sprint 1
3. **Préparer l'environnement de dev**
4. **Démarrer par les migrations** (snapshots + audit)
5. **Développer les tests** en TDD

---

## ❓ Questions Ouvertes pour Affinage

1. **Délai de révocation** : Combien de temps une partie a-t-elle pour réagir à une révision ?
2. **Limite de révisions** : Y a-t-il un nombre maximum d'allers-retours ?
3. **Escalade** : Que se passe-t-il si les parties ne trouvent pas d'accord après X révisions ?
4. **Templates** : Qui crée et valide les templates de clauses (staff uniquement) ?
5. **Langue** : Support multilingue ou français uniquement ?
6. **Montants** : Gestion de devise pour clauses financières ?
7. **Calculs automatiques** : Certains placeholders dépendent d'autres (ex: taxes) ?

---

**Prêt à démarrer le développement ? Dites-moi par quelle phase commencer !** 🚀
