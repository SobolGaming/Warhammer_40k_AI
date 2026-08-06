from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
    BattlefieldTransitionBatch,
    ModelRemovalRecord,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.destruction_provenance import DestructionSourceKind
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.engine.damage_allocation import (
        MortalWoundApplication,
        MortalWoundApplicationProgress,
    )
    from warhammer40k_core.engine.game_state import GameState


MORTAL_WOUND_MODEL_DESTRUCTIONS_FINALIZED_EVENT = "mortal_wound_model_destructions_finalized"


class MortalWoundDestructionEvidencePayload(TypedDict):
    destroying_player_id: str
    source_rules_unit_instance_id: str | None
    destruction_source_kind: str
    action_phase: str
    parent_battle_phase: str
    source_step: str


@dataclass(frozen=True, slots=True)
class MortalWoundDestructionEvidence:
    destroying_player_id: str
    source_rules_unit_instance_id: str | None
    destruction_source_kind: DestructionSourceKind
    action_phase: BattlePhase
    parent_battle_phase: BattlePhase
    source_step: str

    @classmethod
    def for_state(
        cls,
        *,
        state: GameState,
        destroying_player_id: str,
        source_rules_unit_instance_id: str | None,
        destruction_source_kind: DestructionSourceKind,
        action_phase: BattlePhase,
        source_step: str,
    ) -> Self:
        parent_phase = state.current_battle_phase
        if parent_phase is None:
            raise GameLifecycleError(
                "Mortal wound destruction evidence requires a current battle phase."
            )
        return cls(
            destroying_player_id=destroying_player_id,
            source_rules_unit_instance_id=source_rules_unit_instance_id,
            destruction_source_kind=destruction_source_kind,
            action_phase=action_phase,
            parent_battle_phase=parent_phase,
            source_step=source_step,
        )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "destroying_player_id",
            _validate_identifier("destroying_player_id", self.destroying_player_id),
        )
        if self.source_rules_unit_instance_id is not None:
            object.__setattr__(
                self,
                "source_rules_unit_instance_id",
                _validate_identifier(
                    "source_rules_unit_instance_id",
                    self.source_rules_unit_instance_id,
                ),
            )
        if type(self.destruction_source_kind) is not DestructionSourceKind:
            raise GameLifecycleError(
                "Mortal wound destruction evidence requires DestructionSourceKind."
            )
        if type(self.action_phase) is not BattlePhase:
            raise GameLifecycleError("Mortal wound destruction evidence requires an action phase.")
        if type(self.parent_battle_phase) is not BattlePhase:
            raise GameLifecycleError(
                "Mortal wound destruction evidence requires a parent battle phase."
            )
        object.__setattr__(
            self,
            "source_step",
            _validate_identifier("source_step", self.source_step),
        )

    def to_payload(self) -> MortalWoundDestructionEvidencePayload:
        return {
            "destroying_player_id": self.destroying_player_id,
            "source_rules_unit_instance_id": self.source_rules_unit_instance_id,
            "destruction_source_kind": self.destruction_source_kind.value,
            "action_phase": self.action_phase.value,
            "parent_battle_phase": self.parent_battle_phase.value,
            "source_step": self.source_step,
        }

    @classmethod
    def from_payload(cls, payload: MortalWoundDestructionEvidencePayload) -> Self:
        try:
            source_kind = DestructionSourceKind(payload["destruction_source_kind"])
            action_phase = BattlePhase(payload["action_phase"])
            parent_phase = BattlePhase(payload["parent_battle_phase"])
        except ValueError as exc:
            raise GameLifecycleError(
                "Mortal wound destruction evidence contains an unsupported token."
            ) from exc
        return cls(
            destroying_player_id=payload["destroying_player_id"],
            source_rules_unit_instance_id=payload["source_rules_unit_instance_id"],
            destruction_source_kind=source_kind,
            action_phase=action_phase,
            parent_battle_phase=parent_phase,
            source_step=payload["source_step"],
        )


def record_finalized_mortal_wound_model_destructions(
    *,
    state: GameState,
    decisions: DecisionController,
    application_id: str,
    source_rule_id: str,
    source_context: JsonValue,
    target_unit_instance_id: str,
    application_payload: JsonValue,
    destroyed_model_instance_ids: tuple[str, ...],
    evidence: MortalWoundDestructionEvidence,
) -> None:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Mortal wound destruction evidence requires decisions.")
    requested_application_id = _validate_identifier("application_id", application_id)
    requested_rule_id = _validate_identifier("source_rule_id", source_rule_id)
    requested_target_id = _validate_identifier("target_unit_instance_id", target_unit_instance_id)
    model_ids = _validate_identifier_tuple(
        "destroyed_model_instance_ids", destroyed_model_instance_ids
    )
    if not model_ids:
        return
    if type(evidence) is not MortalWoundDestructionEvidence:
        raise GameLifecycleError("Mortal wound destruction finalization requires typed evidence.")
    if state.current_battle_phase is not evidence.parent_battle_phase:
        raise GameLifecycleError("Mortal wound destruction parent phase drift.")
    if any(
        record.event_type == MORTAL_WOUND_MODEL_DESTRUCTIONS_FINALIZED_EVENT
        and isinstance(record.payload, dict)
        and record.payload.get("application_id") == requested_application_id
        for record in decisions.event_log.records
    ):
        raise GameLifecycleError("Mortal wound destruction application was finalized twice.")
    removals: list[ModelRemovalRecord] = []
    physical_unit_ids: set[str] = set()
    rules_unit_ids: set[str] = set()
    for model_id in model_ids:
        physical_unit_id = state.unit_instance_id_for_model(model_id)
        rules_unit_id = rules_unit_view_by_id(
            state=state,
            unit_instance_id=physical_unit_id,
        ).unit_instance_id
        physical_unit_ids.add(physical_unit_id)
        rules_unit_ids.add(rules_unit_id)
        battlefield = state.battlefield_state
        if battlefield is None or battlefield.model_placement_or_none(model_id) is not None:
            raise GameLifecycleError(
                "Finalized mortal wound destruction requires battlefield removal."
            )
        removals.append(
            ModelRemovalRecord(
                model_instance_id=model_id,
                removal_kind=BattlefieldRemovalKind.DESTROYED,
                source_phase=evidence.parent_battle_phase.value,
                source_step=evidence.source_step,
                source_rule_id=requested_rule_id,
                source_event_id=requested_application_id,
            )
        )
    transition_batch = BattlefieldTransitionBatch(removals=tuple(removals))
    decisions.event_log.append(
        MORTAL_WOUND_MODEL_DESTRUCTIONS_FINALIZED_EVENT,
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "application_id": requested_application_id,
                "source_rule_id": requested_rule_id,
                "source_context": validate_json_value(source_context),
                "target_unit_instance_id": requested_target_id,
                "destroyed_model_instance_ids": list(model_ids),
                "physical_unit_instance_ids": sorted(physical_unit_ids),
                "rules_unit_instance_ids": sorted(rules_unit_ids),
                "application": validate_json_value(application_payload),
                "destruction_evidence": evidence.to_payload(),
                "transition_batch": transition_batch.to_payload(),
            }
        ),
    )


def evidence_from_json(value: JsonValue) -> MortalWoundDestructionEvidence | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise GameLifecycleError("Mortal wound destruction evidence must be an object or null.")
    return MortalWoundDestructionEvidence.from_payload(
        cast(MortalWoundDestructionEvidencePayload, value)
    )


def evidence_to_json(
    evidence: MortalWoundDestructionEvidence | None,
) -> MortalWoundDestructionEvidencePayload | None:
    return None if evidence is None else evidence.to_payload()


def validate_mortal_wound_destruction_evidence_mode(
    *,
    progress: MortalWoundApplicationProgress,
    remove_destroyed_models: bool,
) -> None:
    if remove_destroyed_models and progress.destruction_evidence is None:
        raise GameLifecycleError("Mortal wound battlefield removal requires destruction evidence.")
    if not remove_destroyed_models and progress.destruction_evidence is not None:
        raise GameLifecycleError(
            "Deferred mortal wound removal cannot record destruction evidence."
        )


def record_finalized_mortal_wound_progress_destructions(
    *,
    state: GameState,
    decisions: DecisionController,
    progress: MortalWoundApplicationProgress,
    remove_destroyed_models: bool,
) -> None:
    if not remove_destroyed_models:
        return
    evidence = progress.destruction_evidence
    if evidence is None:
        raise GameLifecycleError("Mortal wound destruction evidence is missing.")
    record_finalized_mortal_wound_application_destructions(
        state=state,
        decisions=decisions,
        application_id=progress.application_id,
        source_rule_id=progress.source_rule_id,
        source_context=progress.source_context,
        application=progress.to_application(),
        evidence=evidence,
    )


def record_finalized_mortal_wound_application_destructions(
    *,
    state: GameState,
    decisions: DecisionController,
    application_id: str,
    source_rule_id: str,
    source_context: JsonValue,
    application: MortalWoundApplication,
    evidence: MortalWoundDestructionEvidence,
) -> None:
    record_finalized_mortal_wound_model_destructions(
        state=state,
        decisions=decisions,
        application_id=application_id,
        source_rule_id=source_rule_id,
        source_context=source_context,
        target_unit_instance_id=application.target_unit_instance_id,
        application_payload=cast(JsonValue, application.to_payload()),
        destroyed_model_instance_ids=tuple(
            damage.model_instance_id for damage in application.applications if damage.destroyed
        ),
        evidence=evidence,
    )


def _validate_identifier_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    validated = tuple(_validate_identifier(field_name, value) for value in values)
    if len(set(validated)) != len(validated):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return tuple(sorted(validated))


_validate_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "MORTAL_WOUND_MODEL_DESTRUCTIONS_FINALIZED_EVENT",
    "MortalWoundDestructionEvidence",
    "MortalWoundDestructionEvidencePayload",
    "evidence_from_json",
    "evidence_to_json",
    "record_finalized_mortal_wound_application_destructions",
    "record_finalized_mortal_wound_model_destructions",
    "record_finalized_mortal_wound_progress_destructions",
    "validate_mortal_wound_destruction_evidence_mode",
)
