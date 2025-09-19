"""Data models for contract templates, drafts, and history tracking."""

# pylint: disable=missing-class-docstring,too-few-public-methods

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Max

from athletes.models import Athlete
from organisations.models import Collaborator, Organisation


class BaseModel(models.Model):
    """Abstract base model providing UUID primary key and timestamps."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ClauseTemplate(BaseModel):
    """Reusable clause template supporting tokenised content and versioning."""

    class ClauseType(models.TextChoices):
        OBLIGATION = 'obligation', 'Obligation'
        CONDITION = 'condition', 'Condition'
        PAIEMENT = 'paiement', 'Paiement'
        DUREE = 'duree', 'Durée'
        LEGAL = 'legal', 'Légal'

    identifier = models.CharField(max_length=100, unique=True)
    title = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=ClauseType.choices)
    content = models.TextField(
        help_text='Content supporting placeholder tokens like [key].',
    )
    placeholders = models.JSONField(default=list, blank=True)
    mandatory = models.BooleanField(default=False)
    version = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('identifier', 'version')

    def __str__(self):
        return f"{self.identifier} v{self.version}"


class Contract(BaseModel):
    """Represents a contract between an organisation and an athlete."""

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        AGREEMENT = 'AGREEMENT', 'Agreement'
        VERIFICATION = 'VERIFICATION', 'Verification'
        ACTIVE = 'ACTIVE', 'Active'
        TERMINATED = 'TERMINATED', 'Terminated'

    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='contracts',
    )
    athlete = models.ForeignKey(
        Athlete,
        on_delete=models.CASCADE,
        related_name='contracts',
    )
    created_by = models.ForeignKey(
        Collaborator,
        on_delete=models.CASCADE,
        related_name='created_contracts',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=10, default='EUR')

    class Meta:
        indexes = [
            models.Index(
                fields=('organisation', 'status'),
                name='contract_org_status_idx',
            ),
            models.Index(fields=('athlete',), name='contract_athlete_idx'),
            models.Index(fields=('start_date',), name='contract_start_idx'),
        ]
        ordering = ('-created_at',)

    def __str__(self):
        return f"Contract {self.organisation} ↔ {self.athlete} ({self.status})"


class ContractClause(BaseModel):
    """Concrete clause bound to a specific contract instance."""

    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name='clauses',
    )
    template = models.ForeignKey(
        ClauseTemplate,
        on_delete=models.PROTECT,
        related_name='contract_clauses',
    )
    values = models.JSONField(default=dict, blank=True)
    order_index = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('contract', 'template', 'order_index'),
                name='unique_contract_clause_order',
            ),
        ]
        ordering = ('contract', 'order_index')

    def __str__(self):
        return f"Clause {self.template.identifier} for {self.contract}"  # pylint: disable=no-member


class ContractVersion(BaseModel):
    """Snapshot of a contract at a specific version number."""

    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name='versions',
    )
    version_number = models.PositiveIntegerField()
    snapshot = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('contract', 'version_number'),
                name='unique_contract_version_number',
            ),
        ]
        ordering = ('contract', '-version_number')

    def __str__(self):
        return f"{self.contract} v{self.version_number}"

    def save(self, *args, **kwargs):
        if self.pk is None and not self.version_number:
            last_version = (
                type(self).objects.filter(contract=self.contract)  # pylint: disable=no-member
                .aggregate(max_version=Max('version_number'))
                .get('max_version')
            )
            self.version_number = (last_version or 0) + 1
        super().save(*args, **kwargs)


class ContractStatusHistory(BaseModel):
    """Audit trail of status transitions for a contract."""

    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name='status_history',
    )
    from_status = models.CharField(
        max_length=20,
        choices=Contract.Status.choices,
        blank=True,
        null=True,
    )
    to_status = models.CharField(max_length=20, choices=Contract.Status.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='contract_status_changes',
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    reason = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=('contract', 'changed_at')),
        ]
        ordering = ('-changed_at',)

    def __str__(self):
        return f"{self.contract} {self.from_status} -> {self.to_status}"
