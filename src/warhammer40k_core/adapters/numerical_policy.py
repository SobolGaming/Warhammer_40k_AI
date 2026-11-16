"""Explicit numerical configuration for registered execution, without history migration.

Only the retained binary-inch behavior is executable. The milli-inch arithmetic
foundation is intentionally not an admitted session policy. This configuration
belongs to the authority envelope, never to a rewritten legacy inner payload.
"""

from __future__ import annotations

from dataclasses import dataclass

LEGACY_NUMERICAL_POLICY_ID = "legacy-binary-inch-v1"


class NumericalPolicyError(ValueError):
    """The requested numerical policy is not admitted for execution."""


@dataclass(frozen=True, slots=True)
class NumericalPolicyConfiguration:
    numerical_policy_id: str = LEGACY_NUMERICAL_POLICY_ID

    def __post_init__(self) -> None:
        if (
            type(self.numerical_policy_id) is not str
            or self.numerical_policy_id != LEGACY_NUMERICAL_POLICY_ID
        ):
            raise NumericalPolicyError(
                "Unsupported numerical policy; only legacy-binary-inch-v1 is executable."
            )

    def checkpoint_cache_identity(
        self, *, execution_profile_hash: str, inner_checkpoint_hash: str
    ) -> tuple[str, str, str]:
        """Separate cached outer envelopes by policy, executor and exact inner state."""
        return self.numerical_policy_id, execution_profile_hash, inner_checkpoint_hash


LEGACY_NUMERICAL_POLICY = NumericalPolicyConfiguration()
