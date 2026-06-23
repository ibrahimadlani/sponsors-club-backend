"""Canonical definition of feature flags and entitlements per account type.

The constants in this module power entitlement checks throughout the project.
Adding structured docstrings ensures downstream tooling can inspect the fields
and helps developers reason about how each feature is exposed to agents and
collaborators.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass(frozen=True)
class FeatureRequirement:
    """Describe the feature flag needed to unlock a capability.

    Attributes:
        key: Identifier of the feature stored on the subscription plan.
        allowed_values: Optional tuple limiting which plan values satisfy the
            requirement.
        label: Human readable label suitable for presenting in the UI.
        description: Additional context clarifying what the feature controls.
        denied_message: Optional message explaining why access was refused.
        upgrade_url: URL pointing to the relevant pricing or upgrade page.
        recommended_plans: Plans the product team suggests for unlocking the
            feature.
    """

    key: str
    allowed_values: Optional[Sequence[str]] = None
    label: str = ""
    description: str = ""
    denied_message: str = ""
    upgrade_url: str = ""
    recommended_plans: Sequence[str] = ()


# Agent entitlements define the capabilities that individual agents can access
# through their personal subscription plans.
AGENT_FEATURES = {
    "messaging_initiate": FeatureRequirement(
        key="messaging_tier",
        allowed_values=("limited", "pro_plus", "enterprise"),
        label="Messaging (initiate threads)",
        description=(
            "Allows an agent to initiate new messaging threads with collaborators."
        ),
        denied_message=(
            "Messaging upgrade required: switch to Agent Pro+ "
            "(messaging_tier=pro_plus) to open new conversations."
        ),
        upgrade_url="https://app.sponsorsclub.com/plans/agent",
        recommended_plans=("Agent Pro+", "Agent Enterprise"),
    ),
    "subscription_management": FeatureRequirement(
        key="agent_subscription_management",
        label="Manage agent subscription",
        description="Allows an agent to manage their own subscription.",
        denied_message=(
            "Upgrade to an agent subscription plan to manage billing from the dashboard."
        ),
        upgrade_url="https://app.sponsorsclub.com/plans/agent",
    ),
    "contract_management": FeatureRequirement(
        key="contract_tools",
        allowed_values=("enabled",),
        label="Contract workspace",
        description="Allows an agent to collaborate on contracts for their athletes.",
        denied_message=(
            "Contract workspace is locked. Upgrade your agent plan "
            "(contract_tools=enabled) to continue."
        ),
        upgrade_url="https://app.sponsorsclub.com/plans/agent",
        recommended_plans=("Agent Pro+", "Agent Enterprise"),
    ),
    "notification_center": FeatureRequirement(
        key="notification_center",
        label="Notification center",
        description="Allows an agent to receive in-app notifications and alerts.",
        denied_message=(
            "Enable the notification center add-on in your agent plan to view alerts."
        ),
        upgrade_url="https://app.sponsorsclub.com/plans/agent",
        recommended_plans=("Agent Pro+", "Agent Enterprise"),
    ),
    "athlete_slots": FeatureRequirement(
        key="max_athletes",
        label="Athlete roster slots",
        description="Defines how many athletes an agent can manage simultaneously.",
        denied_message=(
            "Athlete limit reached. Upgrade to Agent Pro or Agency for additional roster slots."
        ),
        upgrade_url="https://app.sponsorsclub.com/plans/agent",
        recommended_plans=("Agent Pro", "Agent Agency"),
    ),
}


# Collaborator entitlements define the capabilities available to organisation
# members working inside a shared workspace.
COLLABORATOR_FEATURES = {
    "athlete_stats_all": FeatureRequirement(
        key="athlete_stats_scope",
        allowed_values=("all",),
        label="Athlete statistics (all)",
        description=(
            "Allows organisation collaborators to view athlete statistics platform-wide."
        ),
        denied_message=(
            "Requires organisation subscription with athlete_stats_scope=all "
            "(Organisation Pro or higher) to unlock athlete insights."
        ),
        upgrade_url="https://app.sponsorsclub.com/plans/organisation",
        recommended_plans=("Organisation Pro", "Organisation Enterprise"),
    ),
    "collaborator_invites": FeatureRequirement(
        key="collaborator_invites",
        label="Invite collaborators",
        description="Allows organisation owners to invite new collaborators.",
        denied_message=(
            "Upgrade your organisation plan to invite additional collaborators."
        ),
        upgrade_url="https://app.sponsorsclub.com/plans/organisation",
    ),
    "organisation_subscription_management": FeatureRequirement(
        key="organisation_subscription_management",
        label="Manage organisation subscription",
        description="Allows organisation owners to manage billing and subscriptions.",
        denied_message=(
            "Upgrade your organisation plan to manage billing inside Sponsors Club."
        ),
        upgrade_url="https://app.sponsorsclub.com/plans/organisation",
        recommended_plans=("Organisation Pro", "Organisation Enterprise"),
    ),
    "contract_management": FeatureRequirement(
        key="contract_tools",
        allowed_values=("enabled",),
        label="Contract workspace",
        description="Allows organisation owners to negotiate and sign contracts with athletes.",
        denied_message=(
            "Unlock the contract workspace by upgrading to Organisation Pro "
            "(contract_tools=enabled)."
        ),
        upgrade_url="https://app.sponsorsclub.com/plans/organisation",
        recommended_plans=("Organisation Pro", "Organisation Enterprise"),
    ),
    "notification_center": FeatureRequirement(
        key="notification_center",
        label="Notification center",
        description="Allows collaborators to receive in-app notifications and alerts.",
        denied_message=(
            "Upgrade your organisation plan to receive notifications in Sponsors Club."
        ),
        upgrade_url="https://app.sponsorsclub.com/plans/organisation",
        recommended_plans=("Organisation Pro", "Organisation Enterprise"),
    ),
    "follow_slots": FeatureRequirement(
        key="max_follows",
        label="Tracked athletes",
        description="Controls how many athletes the organisation can follow from the marketplace.",
        denied_message=(
            "Follow limit reached. Upgrade your organisation plan to track more athletes."
        ),
        upgrade_url="https://app.sponsorsclub.com/plans/organisation",
        recommended_plans=("Organisation Pro", "Organisation Enterprise"),
    ),
    "collaborator_slots": FeatureRequirement(
        key="max_collaborators",
        label="Collaborator seats",
        description=(
            "Defines how many teammates can collaborate under the organisation workspace."
        ),
        denied_message=(
            "Collaborator limit reached. Upgrade your organisation plan to add more teammates."
        ),
        upgrade_url="https://app.sponsorsclub.com/plans/organisation",
        recommended_plans=("Organisation Pro", "Organisation Enterprise"),
    ),
}


FEATURE_MATRIX = {
    "agent": AGENT_FEATURES,
    "collaborator": COLLABORATOR_FEATURES,
}
