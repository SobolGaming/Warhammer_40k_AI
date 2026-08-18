from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.scoring import VictoryPointAward

_validate_identifier = IdentifierValidator(GameLifecycleError)

SECONDARY_SCORING_PROVIDER_KIND_KEY = "secondary_scoring_provider_kind"
_GENERIC_RULE_IR_VP_EFFECT_KIND = "add_victory_points"
_REGISTERED_PHASE11F_CAP_PROBE_RULE_IDS = frozenset(
    {
        ("assassination", "phase11f-secondary-cap"),
        ("assassination", "phase11f-opponent-secondary-cap"),
        ("cleanse", "phase11f-secondary-action-base"),
    }
)
_STATE_BACKED_METADATA_KEYS = frozenset(
    {
        "objective_control_record_id",
        "scoring_rule_ids",
        "scoring_rule_conditions",
        "scoring_rule_source_ids",
        "score_count_by_rule",
        "victory_points_by_rule",
        "evidence_by_rule",
        "scoring_commit_checkpoint_id",
        "scoring_commit_checkpoint_hash",
    }
)


class SecondaryScoringProviderKind(StrEnum):
    STATE_BACKED_OBJECTIVE_CONTROL = "state_backed_objective_control"
    LEGACY_PHASE11F = "legacy_phase11f"
    GENERIC_RULE_IR = "generic_rule_ir"


def secondary_scoring_provider_kind_from_token(token: object) -> SecondaryScoringProviderKind:
    if type(token) is SecondaryScoringProviderKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Secondary scoring provider kind must be a string.")
    try:
        return SecondaryScoringProviderKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported Secondary scoring provider kind: {token}.") from exc


def secondary_scoring_provider_kind_from_metadata(
    metadata: JsonValue,
) -> SecondaryScoringProviderKind:
    raw = _require_metadata_object(metadata)
    if SECONDARY_SCORING_PROVIDER_KIND_KEY not in raw:
        raise GameLifecycleError("Secondary VP metadata requires secondary_scoring_provider_kind.")
    return secondary_scoring_provider_kind_from_token(raw[SECONDARY_SCORING_PROVIDER_KIND_KEY])


def is_registered_phase11f_cap_probe(*, source_id: str, scoring_rule_id: str) -> bool:
    return (source_id, scoring_rule_id) in _REGISTERED_PHASE11F_CAP_PROBE_RULE_IDS


def validate_legacy_phase11f_secondary_award(
    *,
    award: VictoryPointAward,
    expected: VictoryPointAward | None,
) -> None:
    """Authenticate a Phase 11F Secondary award by mutation shape or registered probe."""
    raw = _non_state_backed_metadata(
        award.metadata,
        provider=SecondaryScoringProviderKind.LEGACY_PHASE11F,
    )
    if award.scoring_timing != "secondary_mission_score":
        raise GameLifecycleError(
            "Legacy Phase 11F Secondary VP requires scoring_timing secondary_mission_score."
        )
    scoring_rule_id = raw.get("scoring_rule_id")
    if type(scoring_rule_id) is not str or not scoring_rule_id:
        raise GameLifecycleError("Legacy Phase 11F Secondary VP requires scoring_rule_id.")
    probe_key = (award.source_id, scoring_rule_id)
    if probe_key in _REGISTERED_PHASE11F_CAP_PROBE_RULE_IDS:
        return
    if expected is None:
        raise GameLifecycleError(
            "Legacy Phase 11F Secondary VP is not a registered probe or score_secondary_mission."
        )
    if award != expected:
        raise GameLifecycleError(
            "Legacy Phase 11F Secondary VP drifted from score_secondary_mission authority."
        )


def validate_generic_rule_ir_secondary_award(*, award: VictoryPointAward) -> None:
    """Bind a generic RuleIR Secondary award to its execution payload and VP delta."""
    raw = _non_state_backed_metadata(
        award.metadata,
        provider=SecondaryScoringProviderKind.GENERIC_RULE_IR,
    )
    if award.scoring_timing != "generic_rule_execution":
        raise GameLifecycleError(
            "Generic RuleIR Secondary VP requires scoring_timing generic_rule_execution."
        )
    rule_id = raw.get("rule_id")
    clause_id = raw.get("clause_id")
    if type(rule_id) is not str or not rule_id:
        raise GameLifecycleError("Generic RuleIR Secondary VP requires rule_id.")
    if type(clause_id) is not str or not clause_id:
        raise GameLifecycleError("Generic RuleIR Secondary VP requires clause_id.")
    _validate_identifier("Generic RuleIR Secondary VP rule_id", rule_id)
    _validate_identifier("Generic RuleIR Secondary VP clause_id", clause_id)
    effect = raw.get("effect")
    if not isinstance(effect, dict):
        raise GameLifecycleError("Generic RuleIR Secondary VP effect must be an object.")
    kind = effect.get("kind")
    if kind != _GENERIC_RULE_IR_VP_EFFECT_KIND:
        raise GameLifecycleError("Generic RuleIR Secondary VP effect kind drifted.")
    parameters = effect.get("parameters")
    if type(parameters) is not list:
        raise GameLifecycleError("Generic RuleIR Secondary VP effect parameters must be a list.")
    delta: object = None
    for parameter in parameters:
        if not isinstance(parameter, dict):
            raise GameLifecycleError(
                "Generic RuleIR Secondary VP effect parameter must be an object."
            )
        if parameter.get("key") == "delta":
            delta = parameter.get("value")
            break
    if type(delta) is not int or delta != award.amount:
        raise GameLifecycleError(
            "Generic RuleIR Secondary VP amount drifted from the RuleIR effect delta."
        )


def _non_state_backed_metadata(
    metadata: JsonValue,
    *,
    provider: SecondaryScoringProviderKind,
) -> dict[str, JsonValue]:
    raw = _require_metadata_object(metadata)
    actual = secondary_scoring_provider_kind_from_metadata(raw)
    if actual is not provider:
        raise GameLifecycleError("Secondary VP provider kind drifted.")
    forbidden = sorted(_STATE_BACKED_METADATA_KEYS.intersection(raw))
    if forbidden:
        raise GameLifecycleError(
            "Non-state-backed Secondary VP metadata must not carry state-backed authority."
        )
    return raw


def _require_metadata_object(metadata: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(metadata, dict):
        raise GameLifecycleError("Secondary VP metadata must be an object.")
    return metadata


__all__ = (
    "SECONDARY_SCORING_PROVIDER_KIND_KEY",
    "SecondaryScoringProviderKind",
    "is_registered_phase11f_cap_probe",
    "secondary_scoring_provider_kind_from_metadata",
    "secondary_scoring_provider_kind_from_token",
    "validate_generic_rule_ir_secondary_award",
    "validate_legacy_phase11f_secondary_award",
)
