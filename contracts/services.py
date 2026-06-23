"""Service layer functions for contract operations.

This module provides reusable business logic that serializers and views
can call to perform complex operations like audit logging. Keeping these
in a dedicated service layer prevents duplication and makes testing easier.
"""

from typing import Any, Optional

from django.contrib.auth import get_user_model

from .models import Contract, ContractAuditLog

User = get_user_model()


def log_contract_action(
    contract: Contract,
    action: str,
    actor: Optional[User] = None,
    action_details: Optional[dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> ContractAuditLog:
    """Create an immutable audit log entry for a contract action.

    This function should be called after every significant contract operation
    to maintain full traceability. It satisfies French legal requirements for
    electronic contract auditability (RGPD Article 5.2, eIDAS regulation).

    Args:
        contract: The contract instance being acted upon.
        action: The action being performed (must match ContractAuditLog.Action choices).
        actor: The user performing the action (None for system actions).
        action_details: Optional dictionary with additional context about the action.
            Examples:
            - {"clause_id": "uuid", "old_content": "...", "new_content": "..."}
            - {"revision_id": "uuid", "reason": "Rejected due to..."}
            - {"from_status": "draft", "to_status": "negotiation"}
        ip_address: The IP address from which the action originated.
        user_agent: The browser/client user agent string.

    Returns:
        The created ContractAuditLog instance.

    Examples:
        >>> log_contract_action(
        ...     contract=contract,
        ...     action=ContractAuditLog.Action.CONTRACT_CREATED,
        ...     actor=request.user,
        ...     ip_address=get_client_ip(request),
        ...     user_agent=request.META.get('HTTP_USER_AGENT', ''),
        ... )

        >>> log_contract_action(
        ...     contract=contract,
        ...     action=ContractAuditLog.Action.CLAUSE_MODIFIED,
        ...     actor=request.user,
        ...     action_details={
        ...         "clause_id": str(clause.id),
        ...         "field_changed": "content",
        ...         "old_value": old_content,
        ...         "new_value": new_content,
        ...     },
        ...     ip_address=get_client_ip(request),
        ...     user_agent=request.META.get('HTTP_USER_AGENT', ''),
        ... )
    """
    return ContractAuditLog.objects.create(
        contract=contract,
        actor=actor,
        action=action,
        action_details=action_details or {},
        ip_address=ip_address,
        user_agent=user_agent,
    )


def get_client_ip(request) -> Optional[str]:
    """Extract the real client IP from a Django request.

    Handles X-Forwarded-For headers commonly set by reverse proxies
    (nginx, load balancers) to identify the original client IP.

    Args:
        request: Django HttpRequest object.

    Returns:
        The client IP address as a string, or None if not available.
    """
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        # X-Forwarded-For can contain multiple IPs: "client, proxy1, proxy2"
        # We want the first one (the original client)
        ip = x_forwarded_for.split(",")[0].strip()
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip
