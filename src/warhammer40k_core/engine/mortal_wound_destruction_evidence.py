from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
    BattlefieldTransitionBatch,
    ModelPlacement,
    ModelRemovalRecord,
    PlacementError,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.destruction_provenance import (
    DestructionSourceKind,
    ModelDestructionAttribution,
    ModelDestructionAttributionPayload,
)
from warhammer40k_core.engine.destruction_source_attribution import (
    resolve_non_attack_destruction_source_identity,
    validate_destruction_source_identity,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_destruction_evidence import (
    destruction_source_objective_proximity_witness,
    rules_unit_objective_proximity_witness,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.engine.damage_allocation import (
        MortalWoundApplication,
        MortalWoundApplicationProgress,
    )
    from warhammer40k_core.engine.game_state import GameState


MORTAL_WOUND_MODEL_DESTRUCTIONS_FINALIZED_EVENT = "mortal_wound_model_destructions_finalized"


class MortalWoundDestructionEvidencePayload(TypedDict):
    destruction_attribution: ModelDestructionAttributionPayload
    action_phase: str
    parent_battle_phase: str
    source_step: str


@dataclass(frozen=True, slots=True)
class MortalWoundDestructionEvidence:
    destruction_attribution: ModelDestructionAttribution
    action_phase: BattlePhase
    parent_battle_phase: BattlePhase
    source_step: str

    @classmethod
    def for_non_attack_state(
        cls,
        *,
        state: GameState,
        destroying_player_id: str,
        source_rules_unit_instance_id: str | None,
        source_model_instance_id: str | None,
        destruction_source_kind: DestructionSourceKind,
        action_phase: BattlePhase,
        source_step: str,
    ) -> Self:
        parent_phase = state.current_battle_phase
        if parent_phase is None:
            raise GameLifecycleError(
                "Mortal wound destruction evidence requires a current battle phase."
            )
        canonical_source_id, source_model_id = resolve_non_attack_destruction_source_identity(
            state=state,
            source_rules_unit_instance_id=source_rules_unit_instance_id,
            source_model_instance_id=source_model_instance_id,
            destroying_player_id=destroying_player_id,
        )
        return cls(
            destruction_attribution=ModelDestructionAttribution.for_non_attack(
                destroying_player_id=destroying_player_id,
                source_kind=destruction_source_kind,
                source_rules_unit_instance_id=canonical_source_id,
                source_model_instance_id=source_model_id,
            ),
            action_phase=action_phase,
            parent_battle_phase=parent_phase,
            source_step=source_step,
        )

    @classmethod
    def for_attack_state(
        cls,
        *,
        state: GameState,
        destroying_player_id: str,
        attacking_unit_instance_id: str,
        attacking_model_instance_id: str,
        weapon_profile: WeaponProfile,
        attack_context_id: str,
        action_phase: BattlePhase,
        source_step: str,
    ) -> Self:
        parent_phase = state.current_battle_phase
        if parent_phase is None:
            raise GameLifecycleError(
                "Mortal wound destruction evidence requires a current battle phase."
            )
        canonical_source_id, source_model_id = resolve_non_attack_destruction_source_identity(
            state=state,
            source_rules_unit_instance_id=attacking_unit_instance_id,
            source_model_instance_id=attacking_model_instance_id,
            destroying_player_id=destroying_player_id,
        )
        if canonical_source_id is None or source_model_id is None:
            raise GameLifecycleError("Attack mortal wound evidence requires exact source identity.")
        return cls(
            destruction_attribution=ModelDestructionAttribution.for_attack(
                destroying_player_id=destroying_player_id,
                attacking_unit_instance_id=canonical_source_id,
                attacking_model_instance_id=source_model_id,
                weapon_profile=weapon_profile,
                attack_context_id=attack_context_id,
            ),
            action_phase=action_phase,
            parent_battle_phase=parent_phase,
            source_step=source_step,
        )

    def __post_init__(self) -> None:
        if type(self.destruction_attribution) is not ModelDestructionAttribution:
            raise GameLifecycleError(
                "Mortal wound destruction evidence requires typed attribution."
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

    @property
    def destroying_player_id(self) -> str:
        return self.destruction_attribution.destroying_player_id

    @property
    def source_rules_unit_instance_id(self) -> str | None:
        return self.destruction_attribution.source_rules_unit_instance_id

    @property
    def source_model_instance_id(self) -> str | None:
        return self.destruction_attribution.source_model_instance_id

    @property
    def destruction_source_kind(self) -> DestructionSourceKind:
        return self.destruction_attribution.destruction_provenance.destruction_source_kind

    def validate_for_state(self, state: GameState) -> None:
        validate_destruction_source_identity(
            state=state,
            source_rules_unit_instance_id=self.source_rules_unit_instance_id,
            source_model_instance_id=self.source_model_instance_id,
            destroying_player_id=self.destroying_player_id,
        )

    def to_payload(self) -> MortalWoundDestructionEvidencePayload:
        return {
            "destruction_attribution": self.destruction_attribution.to_payload(),
            "action_phase": self.action_phase.value,
            "parent_battle_phase": self.parent_battle_phase.value,
            "source_step": self.source_step,
        }

    @classmethod
    def from_payload(cls, payload: MortalWoundDestructionEvidencePayload) -> Self:
        expected_fields = {
            "destruction_attribution",
            "action_phase",
            "parent_battle_phase",
            "source_step",
        }
        if set(payload) != expected_fields:
            raise GameLifecycleError("Mortal wound destruction evidence fields are invalid.")
        try:
            action_phase = BattlePhase(payload["action_phase"])
            parent_phase = BattlePhase(payload["parent_battle_phase"])
        except ValueError as exc:
            raise GameLifecycleError(
                "Mortal wound destruction evidence contains an unsupported token."
            ) from exc
        return cls(
            destruction_attribution=ModelDestructionAttribution.from_model_destroyed_payload(
                payload["destruction_attribution"]
            ),
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
    existing_model_destroyed_event_ids: tuple[str, ...],
    destroyed_model_placements: tuple[ModelPlacement, ...],
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
    evidence.validate_for_state(state)
    if state.current_battle_phase is not evidence.parent_battle_phase:
        raise GameLifecycleError("Mortal wound destruction parent phase drift.")
    if any(
        record.event_type == MORTAL_WOUND_MODEL_DESTRUCTIONS_FINALIZED_EVENT
        and isinstance(record.payload, dict)
        and record.payload.get("application_id") == requested_application_id
        for record in decisions.event_log.records
    ):
        raise GameLifecycleError("Mortal wound destruction application was finalized twice.")
    validated_source_context = validate_json_value(source_context)
    validated_application = validate_json_value(application_payload)
    existing_events_by_model = _existing_model_destroyed_events_by_model(
        decisions=decisions,
        event_ids=existing_model_destroyed_event_ids,
        evidence=evidence,
    )
    if not set(existing_events_by_model) <= set(model_ids):
        raise GameLifecycleError(
            "Existing mortal wound model-destroyed events contain an unrelated model."
        )
    placements_by_model = _destroyed_model_placements_by_model(destroyed_model_placements)
    required_placement_model_ids = set(model_ids) - set(existing_events_by_model)
    if set(placements_by_model) != required_placement_model_ids:
        raise GameLifecycleError(
            "Mortal wound destroyed-model placement evidence does not match new destructions."
        )
    removals: list[ModelRemovalRecord] = []
    physical_unit_ids: set[str] = set()
    rules_unit_ids: set[str] = set()
    canonical_model_destroyed_event_ids: list[str] = []
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
        removal = ModelRemovalRecord(
            model_instance_id=model_id,
            removal_kind=BattlefieldRemovalKind.DESTROYED,
            source_phase=evidence.parent_battle_phase.value,
            source_step=evidence.source_step,
            source_rule_id=requested_rule_id,
            source_event_id=requested_application_id,
        )
        removals.append(removal)
        existing_event_id = existing_events_by_model.get(model_id)
        if existing_event_id is not None:
            canonical_model_destroyed_event_ids.append(existing_event_id)
            continue
        damage_application = _destroyed_damage_application_for_model(
            application_payload=validated_application,
            model_instance_id=model_id,
        )
        destroyed_model_placement = placements_by_model[model_id]
        if destroyed_model_placement.unit_instance_id != physical_unit_id:
            raise GameLifecycleError("Mortal wound destroyed-model placement unit drift.")
        destroyed_rules_unit_objective_witness = rules_unit_objective_proximity_witness(
            state=state,
            rules_unit_instance_id=rules_unit_id,
            included_destroyed_model_placement=destroyed_model_placement,
        )
        source_rules_unit_objective_witness = destruction_source_objective_proximity_witness(
            state=state,
            event_log=decisions.event_log,
            attribution=evidence.destruction_attribution,
            destroyed_model_placement=destroyed_model_placement,
        )
        transition_batch = BattlefieldTransitionBatch(removals=(removal,))
        destroyed_event = decisions.event_log.append(
            "model_destroyed",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "active_player_id": state.active_player_id,
                    "phase": evidence.parent_battle_phase.value,
                    **evidence.destruction_attribution.to_payload(),
                    "source_rules_unit_objective_proximity_witness": (
                        None
                        if source_rules_unit_objective_witness is None
                        else source_rules_unit_objective_witness.to_payload()
                    ),
                    "destroyed_rules_unit_objective_proximity_witness": (
                        destroyed_rules_unit_objective_witness.to_payload()
                    ),
                    "sequence_id": _optional_source_context_identifier(
                        validated_source_context,
                        "sequence_id",
                    ),
                    "attack_context_id": (
                        evidence.destruction_attribution.destruction_provenance.attack_context_id
                    ),
                    "target_unit_instance_id": physical_unit_id,
                    "rules_unit_instance_id": rules_unit_id,
                    "model_instance_id": model_id,
                    "damage_kind": "mortal",
                    "damage_event_id": None,
                    "source_rule_id": requested_rule_id,
                    "source_effect_ids": [],
                    "mortal_wound_application_id": requested_application_id,
                    "source_context": validated_source_context,
                    "removal_record": removal.to_payload(),
                    "transition_batch": transition_batch.to_payload(),
                    "destroyed_model_placement": destroyed_model_placement.to_payload(),
                    "damage_application": damage_application,
                    "destroyed_model_rules_triggered": False,
                }
            ),
        )
        canonical_model_destroyed_event_ids.append(destroyed_event.event_id)
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
                "source_context": validated_source_context,
                "target_unit_instance_id": requested_target_id,
                "destroyed_model_instance_ids": list(model_ids),
                "model_destroyed_event_ids": canonical_model_destroyed_event_ids,
                "physical_unit_instance_ids": sorted(physical_unit_ids),
                "rules_unit_instance_ids": sorted(rules_unit_ids),
                "application": validated_application,
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
        destroyed_model_placements=progress.destroyed_model_placements,
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
    destroyed_model_placements: tuple[ModelPlacement, ...],
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
        existing_model_destroyed_event_ids=(),
        destroyed_model_placements=destroyed_model_placements,
    )


def pre_removal_model_placement_for_mortal_wound_destruction(
    *,
    state: GameState,
    model_instance_id: str,
) -> ModelPlacement:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError(
            "Mortal wound destruction placement evidence requires battlefield state."
        )
    try:
        return battlefield.model_placement_by_id(model_instance_id)
    except PlacementError as exc:
        raise GameLifecycleError(
            "Mortal wound destruction placement evidence requires a placed model."
        ) from exc


def _destroyed_model_placements_by_model(
    placements: tuple[ModelPlacement, ...],
) -> dict[str, ModelPlacement]:
    if type(placements) is not tuple:
        raise GameLifecycleError("Destroyed-model placements must be a tuple.")
    placements_by_model: dict[str, ModelPlacement] = {}
    for placement in placements:
        if type(placement) is not ModelPlacement:
            raise GameLifecycleError(
                "Destroyed-model placements must contain ModelPlacement values."
            )
        if placement.model_instance_id in placements_by_model:
            raise GameLifecycleError("Destroyed-model placements must not duplicate models.")
        placements_by_model[placement.model_instance_id] = placement
    return placements_by_model


def validate_mortal_wound_destroyed_model_placements(
    *,
    placements: object,
    destroyed_model_instance_ids: tuple[str, ...],
    has_destruction_evidence: bool,
) -> tuple[ModelPlacement, ...]:
    if type(placements) is not tuple:
        raise GameLifecycleError("Destroyed-model placements must be a tuple.")
    if type(has_destruction_evidence) is not bool:
        raise GameLifecycleError("Destruction-evidence presence must be a bool.")
    placements_by_model = _destroyed_model_placements_by_model(
        cast(tuple[ModelPlacement, ...], placements)
    )
    destroyed_model_ids = set(
        _validate_identifier_tuple(
            "destroyed_model_instance_ids",
            destroyed_model_instance_ids,
        )
    )
    if not has_destruction_evidence and placements_by_model:
        raise GameLifecycleError("Mortal wound placement evidence requires destruction evidence.")
    if has_destruction_evidence and set(placements_by_model) != destroyed_model_ids:
        raise GameLifecycleError("Mortal wound destroyed-model placement drift.")
    return tuple(placements_by_model.values())


def _existing_model_destroyed_events_by_model(
    *,
    decisions: DecisionController,
    event_ids: tuple[str, ...],
    evidence: MortalWoundDestructionEvidence,
) -> dict[str, str]:
    requested_event_ids = _validate_identifier_tuple(
        "existing_model_destroyed_event_ids",
        event_ids,
    )
    records_by_id = {record.event_id: record for record in decisions.event_log.records}
    events_by_model: dict[str, str] = {}
    for event_id in requested_event_ids:
        record = records_by_id.get(event_id)
        if record is None or record.event_type != "model_destroyed":
            raise GameLifecycleError("Existing mortal wound model-destroyed event is missing.")
        if not isinstance(record.payload, dict):
            raise GameLifecycleError(
                "Existing mortal wound model-destroyed payload must be an object."
            )
        attribution = ModelDestructionAttribution.from_model_destroyed_payload(record.payload)
        if attribution != evidence.destruction_attribution:
            raise GameLifecycleError("Existing mortal wound model-destroyed attribution drift.")
        model_id = _validate_identifier(
            "existing_model_destroyed_model_instance_id",
            record.payload.get("model_instance_id"),
        )
        if model_id in events_by_model:
            raise GameLifecycleError("Existing mortal wound model-destroyed model is duplicated.")
        events_by_model[model_id] = event_id
    return events_by_model


def _destroyed_damage_application_for_model(
    *,
    application_payload: JsonValue,
    model_instance_id: str,
) -> dict[str, JsonValue]:
    if not isinstance(application_payload, dict):
        raise GameLifecycleError("Mortal wound application payload must be an object.")
    applications = application_payload.get("applications")
    if not isinstance(applications, list):
        raise GameLifecycleError("Mortal wound application damage list must be a list.")
    matches = tuple(
        item
        for item in applications
        if isinstance(item, dict)
        and item.get("model_instance_id") == model_instance_id
        and item.get("destroyed") is True
    )
    if len(matches) != 1:
        raise GameLifecycleError("Mortal wound destroyed-model damage attribution is not unique.")
    return dict(matches[0])


def _optional_source_context_identifier(
    source_context: JsonValue,
    key: str,
) -> str | None:
    if not isinstance(source_context, dict):
        return None
    value = source_context.get(key)
    if value is None:
        return None
    return _validate_identifier(key, value)


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
    "pre_removal_model_placement_for_mortal_wound_destruction",
    "record_finalized_mortal_wound_application_destructions",
    "record_finalized_mortal_wound_model_destructions",
    "record_finalized_mortal_wound_progress_destructions",
    "validate_mortal_wound_destroyed_model_placements",
    "validate_mortal_wound_destruction_evidence_mode",
)
