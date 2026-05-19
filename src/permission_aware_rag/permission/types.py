"""Types for permission decisions.

The permission system is built on pure functions returning explicit
PolicyDecision objects. Every decision carries a human-readable reason
so that audit logs and debug output can explain why access was granted or denied.
"""

from dataclasses import dataclass
from enum import Enum


class Effect(str, Enum):
    """Permission effect - explicit allow or deny."""

    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True)
class PolicyDecision:
    """The outcome of evaluating permission rules for a (principal, document).

    Immutable so that decisions cannot be mutated between evaluation and
    audit logging. The `reason` field is required and must explain which
    rule fired and why.
    """

    effect: Effect
    reason: str
    rule_name: str

    @classmethod
    def allow(cls, rule_name: str, reason: str) -> "PolicyDecision":
        """Factory for allow decisions."""
        return cls(effect=Effect.ALLOW, reason=reason, rule_name=rule_name)

    @classmethod
    def deny(cls, rule_name: str, reason: str) -> "PolicyDecision":
        """Factory for deny decisions."""
        return cls(effect=Effect.DENY, reason=reason, rule_name=rule_name)

    @property
    def is_allowed(self) -> bool:
        return self.effect == Effect.ALLOW