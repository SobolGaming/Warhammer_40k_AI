from __future__ import annotations

from dataclasses import dataclass
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
_GENERIC_RULE_IR_SOURCE_KIND = "fixed_secondary"
_GENERIC_RULE_IR_SOURCE_ID_KEY = "source_id"
_GENERIC_RULE_IR_HASH_KEY = "rule_ir_hash"
_GENERIC_RULE_IR_EFFECT_INDEX_KEY = "effect_index"
_GENERIC_RULE_IR_EXECUTION_EVENT_ID_KEY = "execution_event_id"
_GENERIC_RULE_IR_EXECUTION_CONTEXT_KEY = "execution_context"
_SHA256_HEX = frozenset("0123456789abcdef")
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


@dataclass(frozen=True, slots=True)
class RegisteredPhase11FCapProbe:
    source_id: str
    scoring_rule_id: str
    source_kind: str
    scoring_timing: str
    amount: int
    player_id: str
    battle_round: int
    phase: str


_REGISTERED_PHASE11F_CAP_PROBES = {
    ("assassination", "phase11f-secondary-cap"): RegisteredPhase11FCapProbe(
        source_id="assassination",
        scoring_rule_id="phase11f-secondary-cap",
        source_kind="tactical_secondary",
        scoring_timing="secondary_mission_score",
        amount=46,
        player_id="player-a",
        battle_round=4,
        phase="command",
    ),
    ("assassination", "phase11f-opponent-secondary-cap"): RegisteredPhase11FCapProbe(
        source_id="assassination",
        scoring_rule_id="phase11f-opponent-secondary-cap",
        source_kind="tactical_secondary",
        scoring_timing="secondary_mission_score",
        amount=60,
        player_id="player-b",
        battle_round=4,
        phase="command",
    ),
    ("cleanse", "phase11f-secondary-action-base"): RegisteredPhase11FCapProbe(
        source_id="cleanse",
        scoring_rule_id="phase11f-secondary-action-base",
        source_kind="tactical_secondary",
        scoring_timing="secondary_mission_score",
        amount=44,
        player_id="player-a",
        battle_round=4,
        phase="command",
    ),
}


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


def registered_phase11f_cap_probe(
    *,
    source_id: str,
    scoring_rule_id: str,
) -> RegisteredPhase11FCapProbe | None:
    return _REGISTERED_PHASE11F_CAP_PROBES.get((source_id, scoring_rule_id))


def is_registered_phase11f_cap_probe(*, source_id: str, scoring_rule_id: str) -> bool:
    return (
        registered_phase11f_cap_probe(source_id=source_id, scoring_rule_id=scoring_rule_id)
        is not None
    )


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
    probe = registered_phase11f_cap_probe(
        source_id=award.source_id,
        scoring_rule_id=scoring_rule_id,
    )
    if probe is not None:
        _validate_registered_phase11f_cap_probe(award=award, probe=probe)
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
    if award.source_kind.value != _GENERIC_RULE_IR_SOURCE_KIND:
        raise GameLifecycleError(
            "Generic RuleIR Secondary VP requires source_kind fixed_secondary."
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
    source_id = raw.get(_GENERIC_RULE_IR_SOURCE_ID_KEY)
    if type(source_id) is not str or source_id != award.source_id:
        raise GameLifecycleError("Generic RuleIR Secondary VP source_id drifted from the award.")
    _validate_identifier("Generic RuleIR Secondary VP source_id", source_id)
    rule_ir_hash = raw.get(_GENERIC_RULE_IR_HASH_KEY)
    if (
        type(rule_ir_hash) is not str
        or len(rule_ir_hash) != 64
        or any(character not in _SHA256_HEX for character in rule_ir_hash)
    ):
        raise GameLifecycleError("Generic RuleIR Secondary VP requires a SHA-256 rule_ir_hash.")
    effect_index = raw.get(_GENERIC_RULE_IR_EFFECT_INDEX_KEY)
    if type(effect_index) is not int or effect_index < 0:
        raise GameLifecycleError(
            "Generic RuleIR Secondary VP requires a non-negative effect_index."
        )
    execution_event_id = raw.get(_GENERIC_RULE_IR_EXECUTION_EVENT_ID_KEY)
    if type(execution_event_id) is not str or not execution_event_id:
        raise GameLifecycleError("Generic RuleIR Secondary VP requires execution_event_id.")
    _validate_identifier(
        "Generic RuleIR Secondary VP execution_event_id",
        execution_event_id,
    )
    execution_context = raw.get(_GENERIC_RULE_IR_EXECUTION_CONTEXT_KEY)
    if not isinstance(execution_context, dict):
        raise GameLifecycleError("Generic RuleIR Secondary VP execution_context must be an object.")
    if execution_context.get("player_id") != award.player_id:
        raise GameLifecycleError("Generic RuleIR Secondary VP execution_context player_id drifted.")
    if execution_context.get("battle_round") != award.battle_round:
        raise GameLifecycleError(
            "Generic RuleIR Secondary VP execution_context battle_round drifted."
        )
    if execution_context.get("phase") != award.phase:
        raise GameLifecycleError("Generic RuleIR Secondary VP execution_context phase drifted.")


def _validate_registered_phase11f_cap_probe(
    *,
    award: VictoryPointAward,
    probe: RegisteredPhase11FCapProbe,
) -> None:
    if award.source_id != probe.source_id:
        raise GameLifecycleError("Registered Phase 11F Secondary VP source_id drifted.")
    if award.source_kind.value != probe.source_kind:
        raise GameLifecycleError("Registered Phase 11F Secondary VP source_kind drifted.")
    if award.scoring_timing != probe.scoring_timing:
        raise GameLifecycleError("Registered Phase 11F Secondary VP scoring_timing drifted.")
    if award.amount != probe.amount:
        raise GameLifecycleError("Registered Phase 11F Secondary VP amount drifted.")
    if award.player_id != probe.player_id:
        raise GameLifecycleError("Registered Phase 11F Secondary VP player_id drifted.")
    if award.battle_round != probe.battle_round:
        raise GameLifecycleError("Registered Phase 11F Secondary VP battle_round drifted.")
    if award.phase != probe.phase:
        raise GameLifecycleError("Registered Phase 11F Secondary VP phase drifted.")


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
    "RegisteredPhase11FCapProbe",
    "SecondaryScoringProviderKind",
    "is_registered_phase11f_cap_probe",
    "registered_phase11f_cap_probe",
    "secondary_scoring_provider_kind_from_metadata",
    "secondary_scoring_provider_kind_from_token",
    "validate_generic_rule_ir_secondary_award",
    "validate_legacy_phase11f_secondary_award",
)
