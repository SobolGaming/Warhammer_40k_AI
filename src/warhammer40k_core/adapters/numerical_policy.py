"""Explicit numerical configuration for registered Linux execution."""

from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.geometry.numerical_identity import (
    CURRENT_NUMERICAL_POLICY_ID as CURRENT_NUMERICAL_POLICY_ID,
)


class NumericalPolicyError(ValueError):
    """The requested numerical policy is not admitted for execution."""


@dataclass(frozen=True, slots=True)
class NumericalPolicyConfiguration:
    numerical_policy_id: str = CURRENT_NUMERICAL_POLICY_ID

    def __post_init__(self) -> None:
        if (
            type(self.numerical_policy_id) is not str
            or self.numerical_policy_id != CURRENT_NUMERICAL_POLICY_ID
        ):
            raise NumericalPolicyError(
                f"Unsupported numerical policy; expected {CURRENT_NUMERICAL_POLICY_ID}."
            )

    def checkpoint_cache_identity(
        self, *, execution_profile_hash: str, inner_checkpoint_hash: str
    ) -> tuple[str, str, str]:
        """Separate cached outer envelopes by policy, executor and exact inner state."""
        return self.numerical_policy_id, execution_profile_hash, inner_checkpoint_hash


CURRENT_NUMERICAL_POLICY = NumericalPolicyConfiguration()
