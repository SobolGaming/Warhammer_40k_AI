from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.core.missions import MissionActionDefinition
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import GameLifecycleError


class PrimaryScoringActionPolicyError(GameLifecycleError):
    """Raised when a source-backed Primary Action scoring policy is invalid."""


_validate_identifier = IdentifierValidator(PrimaryScoringActionPolicyError)


@dataclass(frozen=True, slots=True)
class PrimaryScoringActionPolicy:
    """Mission-pack projection used to validate Primary scoring Action evidence."""

    mission_action_id: str
    primary_mission_id: str
    start_phase: str
    start_timing: str
    completion_timing: str
    interruption_conditions: tuple[str, ...]
    scoring_source_id: str
    victory_points: int
    source_id: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("mission_action_id", self.mission_action_id),
            ("primary_mission_id", self.primary_mission_id),
            ("start_phase", self.start_phase),
            ("start_timing", self.start_timing),
            ("completion_timing", self.completion_timing),
            ("scoring_source_id", self.scoring_source_id),
            ("source_id", self.source_id),
        ):
            _validate_identifier(f"PrimaryScoringActionPolicy {field_name}", value)
        if self.completion_timing not in {"immediate", "turn_end"}:
            raise PrimaryScoringActionPolicyError(
                "Primary scoring Action completion timing is unsupported."
            )
        if (
            type(self.interruption_conditions) is not tuple
            or any(
                type(condition) is not str or not condition.strip()
                for condition in self.interruption_conditions
            )
            or len(set(self.interruption_conditions)) != len(self.interruption_conditions)
        ):
            raise PrimaryScoringActionPolicyError(
                "Primary scoring Action interruption conditions are invalid."
            )
        if type(self.victory_points) is not int or self.victory_points < 0:
            raise PrimaryScoringActionPolicyError(
                "Primary scoring Action victory_points must be a non-negative int."
            )
        if not self.source_id.endswith(f":action:{self.mission_action_id}"):
            raise PrimaryScoringActionPolicyError("Primary scoring Action source identity drifted.")

    @classmethod
    def from_definition(
        cls,
        definition: MissionActionDefinition,
    ) -> PrimaryScoringActionPolicy:
        if type(definition) is not MissionActionDefinition:
            raise PrimaryScoringActionPolicyError(
                "Primary scoring Action policy requires MissionActionDefinition."
            )
        if definition.mission_kind != "primary":
            raise PrimaryScoringActionPolicyError(
                "Primary scoring Action policy requires a Primary mission definition."
            )
        return cls(
            mission_action_id=definition.mission_action_id,
            primary_mission_id=definition.mission_id,
            start_phase=definition.start_phase,
            start_timing=definition.start_timing,
            completion_timing=definition.completion_timing,
            interruption_conditions=definition.interruption_conditions,
            scoring_source_id=definition.scoring_source_id,
            victory_points=definition.victory_points,
            source_id=definition.source_id,
        )


def primary_scoring_action_policies_by_id(
    mission_setup: MissionSetup,
) -> dict[str, PrimaryScoringActionPolicy]:
    """Return every source-declared Primary Action in the configured mission pack."""
    from warhammer40k_core.engine.missions import mission_pack_for_id

    if type(mission_setup) is not MissionSetup:
        raise PrimaryScoringActionPolicyError(
            "Primary scoring Action policies require MissionSetup."
        )
    mission_pack = mission_pack_for_id(mission_setup.mission_pack_id)
    policies = tuple(
        PrimaryScoringActionPolicy.from_definition(definition)
        for definition in mission_pack.mission_actions
        if definition.mission_kind == "primary"
    )
    action_ids = tuple(policy.mission_action_id for policy in policies)
    source_ids = tuple(policy.source_id for policy in policies)
    if len(action_ids) != len(set(action_ids)):
        raise PrimaryScoringActionPolicyError("Primary scoring Action policy IDs must be unique.")
    if len(source_ids) != len(set(source_ids)):
        raise PrimaryScoringActionPolicyError(
            "Primary scoring Action policy source IDs must be unique."
        )
    return {
        policy.mission_action_id: policy
        for policy in sorted(policies, key=lambda policy: policy.mission_action_id)
    }


__all__ = (
    "PrimaryScoringActionPolicy",
    "PrimaryScoringActionPolicyError",
    "primary_scoring_action_policies_by_id",
)
