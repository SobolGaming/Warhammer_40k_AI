from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.objective_control import ObjectiveControlRecord
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.scoring import (
    VictoryPointCapBucket,
    VictoryPointSourceKind,
    victory_point_source_kind_from_token,
)

_validate_identifier = IdentifierValidator(GameLifecycleError)

if TYPE_CHECKING:
    from warhammer40k_core.engine.event_log import JsonValue
    from warhammer40k_core.engine.scoring import (
        MissionScoringPolicy,
        VictoryPointAward,
        VictoryPointTransaction,
    )

_SECONDARY_SOURCE_KINDS = frozenset(
    {
        VictoryPointSourceKind.FIXED_SECONDARY,
        VictoryPointSourceKind.TACTICAL_SECONDARY,
    }
)


def require_source_backed_secondary_cap_bucket(
    *,
    policy: MissionScoringPolicy,
    source_kind: VictoryPointSourceKind,
    source_id: str,
) -> VictoryPointCapBucket:
    kind = victory_point_source_kind_from_token(source_kind)
    if kind not in _SECONDARY_SOURCE_KINDS:
        raise GameLifecycleError("Secondary VP cap bucket requires a Secondary source kind.")
    requested = _validate_identifier("source_id", source_id)
    if not any(
        rule.secondary_mission_id == requested and rule.source_kind is kind
        for rule in policy.secondary_scoring_rules
    ):
        raise GameLifecycleError("Secondary VP source is not source-backed.")
    return VictoryPointCapBucket.SECONDARY


def state_backed_secondary_binding_identity(
    *,
    player_id: str,
    source_kind: VictoryPointSourceKind,
    source_id: str,
    metadata: JsonValue,
) -> tuple[str, VictoryPointSourceKind, str, str] | None:
    kind = victory_point_source_kind_from_token(source_kind)
    if kind not in _SECONDARY_SOURCE_KINDS:
        return None
    record_id = state_backed_secondary_objective_control_record_id(metadata)
    if record_id is None:
        return None
    return (player_id, kind, source_id, record_id)


def state_backed_secondary_objective_control_record_id(metadata: JsonValue) -> str | None:
    if not isinstance(metadata, dict):
        raise GameLifecycleError("Secondary VP metadata must be an object.")
    if "objective_control_record_id" not in metadata:
        return None
    record_id = metadata["objective_control_record_id"]
    if type(record_id) is not str or not record_id:
        raise GameLifecycleError("Secondary VP metadata requires objective_control_record_id.")
    return record_id


def validate_state_backed_secondary_ledger_binding(
    *,
    transaction: VictoryPointTransaction,
    objective_control_records: Sequence[ObjectiveControlRecord],
) -> tuple[str, VictoryPointSourceKind, str, str]:
    binding = state_backed_secondary_binding_identity(
        player_id=transaction.player_id,
        source_kind=transaction.source_kind,
        source_id=transaction.source_id,
        metadata=transaction.metadata,
    )
    if binding is None:
        raise GameLifecycleError("State-backed Secondary VP transaction requires a boundary.")
    record = _objective_control_record(
        objective_control_records,
        record_id=binding[3],
    )
    if (
        transaction.battle_round != record.battle_round
        or transaction.phase != record.phase
        or transaction.scoring_timing != record.timing.value
    ):
        raise GameLifecycleError(
            "Secondary VP transaction timing drifted from its objective-control boundary."
        )
    return binding


def validate_state_backed_secondary_award_binding(
    *,
    award: VictoryPointAward,
    objective_control_records: Sequence[ObjectiveControlRecord],
) -> tuple[str, VictoryPointSourceKind, str, str]:
    binding = state_backed_secondary_binding_identity(
        player_id=award.player_id,
        source_kind=award.source_kind,
        source_id=award.source_id,
        metadata=award.metadata,
    )
    if binding is None:
        raise GameLifecycleError("State-backed Secondary VP award requires a boundary.")
    record = _objective_control_record(
        objective_control_records,
        record_id=binding[3],
    )
    if (
        award.battle_round != record.battle_round
        or award.phase != record.phase
        or award.scoring_timing != record.timing.value
    ):
        raise GameLifecycleError(
            "Secondary VP award timing drifted from its objective-control boundary."
        )
    return binding


def _objective_control_record(
    records: Sequence[ObjectiveControlRecord],
    *,
    record_id: str,
) -> ObjectiveControlRecord:
    matches = tuple(record for record in records if record.record_id == record_id)
    if len(matches) != 1:
        raise GameLifecycleError(
            "Secondary VP transaction requires one objective-control boundary."
        )
    return matches[0]


__all__ = (
    "require_source_backed_secondary_cap_bucket",
    "state_backed_secondary_binding_identity",
    "state_backed_secondary_objective_control_record_id",
    "validate_state_backed_secondary_award_binding",
    "validate_state_backed_secondary_ledger_binding",
)
