from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.primary_turn_start_evidence import (
        PrimaryRulesUnitTurnStartMembership,
        PrimaryRulesUnitTurnStartMembershipPayload,
    )


class PrimaryScoringRulesUnitPositionWitnessPayload(TypedDict):
    owner_player_id: str
    rules_unit_membership: PrimaryRulesUnitTurnStartMembershipPayload


@dataclass(frozen=True, slots=True)
class PrimaryScoringRulesUnitPositionWitness:
    """Current group-aware physical membership for one authoritative rules unit."""

    owner_player_id: str
    rules_unit_membership: PrimaryRulesUnitTurnStartMembership

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.primary_turn_start_evidence import (
            PrimaryRulesUnitTurnStartMembership,
        )

        object.__setattr__(
            self,
            "owner_player_id",
            _validate_identifier(
                "Primary scoring position owner_player_id",
                self.owner_player_id,
            ),
        )
        if type(self.rules_unit_membership) is not PrimaryRulesUnitTurnStartMembership:
            raise GameLifecycleError(
                "Primary scoring position witness requires typed rules-unit membership."
            )

    @property
    def rules_unit_instance_id(self) -> str:
        return self.rules_unit_membership.rules_unit_instance_id

    def to_payload(self) -> PrimaryScoringRulesUnitPositionWitnessPayload:
        return {
            "owner_player_id": self.owner_player_id,
            "rules_unit_membership": self.rules_unit_membership.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        from warhammer40k_core.engine.primary_turn_start_evidence import (
            PrimaryRulesUnitTurnStartMembership,
        )

        if not isinstance(payload, dict):
            raise GameLifecycleError(
                "Primary scoring rules-unit position witness payload must be an object."
            )
        untyped_raw = cast(dict[object, object], payload)
        if any(type(key) is not str for key in untyped_raw):
            raise GameLifecycleError(
                "Primary scoring rules-unit position witness payload must be an object."
            )
        raw = cast(dict[str, object], payload)
        if set(raw) != {"owner_player_id", "rules_unit_membership"}:
            raise GameLifecycleError(
                "Primary scoring rules-unit position witness payload fields are invalid."
            )
        return cls(
            owner_player_id=cast(str, raw["owner_player_id"]),
            rules_unit_membership=PrimaryRulesUnitTurnStartMembership.from_payload(
                raw["rules_unit_membership"]
            ),
        )


def validate_primary_scoring_position_witnesses(
    values: object,
) -> tuple[PrimaryScoringRulesUnitPositionWitness, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(
            "PrimaryScoringStateEvidence current position witnesses must be a tuple."
        )
    raw_values = cast(tuple[object, ...], values)
    witnesses: list[PrimaryScoringRulesUnitPositionWitness] = []
    seen_ids: set[str] = set()
    for value in raw_values:
        if type(value) is not PrimaryScoringRulesUnitPositionWitness:
            raise GameLifecycleError(
                "PrimaryScoringStateEvidence positions must contain typed witnesses."
            )
        if value.rules_unit_instance_id in seen_ids:
            raise GameLifecycleError(
                "PrimaryScoringStateEvidence rules-unit positions must be unique."
            )
        seen_ids.add(value.rules_unit_instance_id)
        witnesses.append(value)
    expected = tuple(sorted(witnesses, key=lambda witness: witness.rules_unit_instance_id))
    if raw_values != expected:
        raise GameLifecycleError("PrimaryScoringStateEvidence rules-unit positions must be sorted.")
    return expected


_validate_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "PrimaryScoringRulesUnitPositionWitness",
    "PrimaryScoringRulesUnitPositionWitnessPayload",
    "validate_primary_scoring_position_witnesses",
)
