from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import PlacementError
from warhammer40k_core.engine.damage_allocation import (
    DamageApplication,
    DamageKind,
    DestructionReactionKind,
    model_by_id,
    model_owner_player_id,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.destruction_provenance import DestructionSourceKind
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
    MortalWoundDestructionEvidence,
    MortalWoundDestructionEvidencePayload,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rule_deadly_demise_continuation import (
    RULE_MODEL_DESTRUCTION_APPLIED_DAMAGE_COMPLETION_KIND,
    RULE_MODEL_DESTRUCTION_CONTEXT_KIND,
    damage_application_from_rule_context,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.engine.rule_model_destruction import RuleModelDestructionResult


def continue_applied_mortal_wound_destruction_with_rule_reactions(
    *,
    state: GameState,
    decisions: DecisionController,
    damage_application: DamageApplication,
    rules_unit_instance_id: str,
    source_rule_id: str,
    source_result_id: str,
    completion_event_type: str,
    completion_event_payload: JsonValue,
    destruction_evidence: MortalWoundDestructionEvidence,
) -> RuleModelDestructionResult:
    if type(state) is not GameState:
        raise GameLifecycleError("Applied mortal-wound destruction requires GameState.")
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Applied mortal-wound destruction requires DecisionController.")
    if type(damage_application) is not DamageApplication:
        raise GameLifecycleError("Applied mortal-wound destruction requires DamageApplication.")
    if type(destruction_evidence) is not MortalWoundDestructionEvidence:
        raise GameLifecycleError(
            "Applied mortal-wound destruction requires typed destruction evidence."
        )
    requested_rules_unit_id = _validate_identifier("rules_unit_instance_id", rules_unit_instance_id)
    requested_rule_id = _validate_identifier("source_rule_id", source_rule_id)
    requested_result_id = _validate_identifier("source_result_id", source_result_id)
    requested_completion_event_type = _validate_identifier(
        "completion_event_type", completion_event_type
    )
    completion_payload = _object_payload(
        completion_event_payload,
        "completion_event_payload",
    )
    destruction_evidence.validate_for_state(state)
    if state.current_battle_phase is not destruction_evidence.parent_battle_phase:
        raise GameLifecycleError("Applied mortal-wound destruction parent phase drift.")
    if destruction_evidence.destruction_source_kind is DestructionSourceKind.ATTACK:
        raise GameLifecycleError(
            "Applied mortal-wound rule destruction requires non-attack provenance."
        )
    target_view = rules_unit_view_by_id(
        state=state,
        unit_instance_id=requested_rules_unit_id,
    )
    if target_view.unit_instance_id != requested_rules_unit_id:
        raise GameLifecycleError(
            "Applied mortal-wound destruction requires canonical rules-unit identity."
        )
    physical_unit_id = state.unit_instance_id_for_model(damage_application.model_instance_id)
    if physical_unit_id not in target_view.component_unit_instance_ids:
        raise GameLifecycleError(
            "Applied mortal-wound destruction model is not in the target rules unit."
        )
    if damage_application.target_unit_instance_id != requested_rules_unit_id:
        raise GameLifecycleError("Applied mortal-wound destruction target identity drift.")
    _validate_destroyed_damage_matches_state(
        state=state,
        damage_application=damage_application,
    )
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Applied mortal-wound destruction requires battlefield state.")
    try:
        placement = battlefield.model_placement_by_id(damage_application.model_instance_id)
    except PlacementError as exc:
        raise GameLifecycleError(
            "Applied mortal-wound destruction requires an already-zero placed model."
        ) from exc
    if state.active_player_id is None:
        raise GameLifecycleError("Applied mortal-wound destruction requires active player.")
    sources = state.destruction_reaction_sources_for_model(
        model_instance_id=damage_application.model_instance_id
    )
    mandatory_sources = tuple(source for source in sources if not source.optional)
    root_context = cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "context_kind": RULE_MODEL_DESTRUCTION_CONTEXT_KIND,
                "completion_kind": RULE_MODEL_DESTRUCTION_APPLIED_DAMAGE_COMPLETION_KIND,
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": destruction_evidence.parent_battle_phase.value,
                "action_phase": destruction_evidence.action_phase.value,
                "source_step": destruction_evidence.source_step,
                "source_rule_id": requested_rule_id,
                "source_effect_ids": [],
                "source_result_id": requested_result_id,
                "rules_unit_instance_id": requested_rules_unit_id,
                "target_unit_instance_id": physical_unit_id,
                "model_instance_id": damage_application.model_instance_id,
                "destroying_player_id": destruction_evidence.destroying_player_id,
                "source_rules_unit_instance_id": (
                    destruction_evidence.source_rules_unit_instance_id
                ),
                "source_model_instance_id": destruction_evidence.source_model_instance_id,
                "destroyed_model_controller_player_id": model_owner_player_id(
                    state=state,
                    model_instance_id=damage_application.model_instance_id,
                ),
                "destroyed_model_placement": placement.to_payload(),
                "damage_application": damage_application.to_payload(),
                "mortal_wound_destruction_evidence": destruction_evidence.to_payload(),
                "completion_event_type": requested_completion_event_type,
                "completion_event_payload": completion_payload,
                "post_removal_mandatory_sources": [
                    source.to_payload()
                    for source in mandatory_sources
                    if source.reaction_kind is not DestructionReactionKind.DEADLY_DEMISE
                ],
            }
        ),
    )
    validate_applied_damage_rule_destruction_context(state=state, context=root_context)
    deadly_demise_sources = tuple(
        source
        for source in mandatory_sources
        if source.reaction_kind is DestructionReactionKind.DEADLY_DEMISE
    )
    from warhammer40k_core.engine.rule_model_destruction import (
        RuleModelDestructionResult,
        continue_rule_deadly_demise_sources,
        remove_rule_destroyed_model_and_continue,
    )

    status = continue_rule_deadly_demise_sources(
        state=state,
        decisions=decisions,
        root_context=root_context,
        sources=deadly_demise_sources,
    )
    if status is not None:
        return RuleModelDestructionResult(
            model_destroyed_event_id=None,
            removal_record=None,
            transition_batch=None,
            status=status,
        )
    return remove_rule_destroyed_model_and_continue(
        state=state,
        decisions=decisions,
        root_context=root_context,
    )


def validate_applied_damage_rule_destruction_context(
    *,
    state: GameState,
    context: dict[str, JsonValue],
) -> bool:
    if context.get("completion_kind") != RULE_MODEL_DESTRUCTION_APPLIED_DAMAGE_COMPLETION_KIND:
        return False
    damage = damage_application_from_rule_context(context)
    if damage is None:
        raise GameLifecycleError("Applied mortal-wound destruction requires damage.")
    _validate_destroyed_damage_matches_state(state=state, damage_application=damage)
    rules_unit_id = _payload_identifier(context, "rules_unit_instance_id")
    if damage.target_unit_instance_id != rules_unit_id:
        raise GameLifecycleError("Applied mortal-wound destruction target context drift.")
    target_view = rules_unit_view_by_id(state=state, unit_instance_id=rules_unit_id)
    if target_view.unit_instance_id != rules_unit_id:
        raise GameLifecycleError(
            "Applied mortal-wound destruction context requires canonical rules-unit identity."
        )
    if state.unit_instance_id_for_model(damage.model_instance_id) not in (
        target_view.component_unit_instance_ids
    ):
        raise GameLifecycleError("Applied mortal-wound destruction rules-unit context drift.")
    evidence_payload = _object_payload(
        context.get("mortal_wound_destruction_evidence"),
        "mortal_wound_destruction_evidence",
    )
    evidence = MortalWoundDestructionEvidence.from_payload(
        cast(MortalWoundDestructionEvidencePayload, evidence_payload)
    )
    evidence.validate_for_state(state)
    if evidence.destruction_source_kind is DestructionSourceKind.ATTACK:
        raise GameLifecycleError("Applied mortal-wound destruction provenance drift.")
    if (
        context.get("phase") != evidence.parent_battle_phase.value
        or context.get("action_phase") != evidence.action_phase.value
        or context.get("source_step") != evidence.source_step
        or context.get("destroying_player_id") != evidence.destroying_player_id
        or context.get("source_rules_unit_instance_id") != evidence.source_rules_unit_instance_id
        or context.get("source_model_instance_id") != evidence.source_model_instance_id
    ):
        raise GameLifecycleError("Applied mortal-wound destruction evidence context drift.")
    source_effect_ids = context.get("source_effect_ids")
    if source_effect_ids != []:
        raise GameLifecycleError(
            "Applied mortal-wound destruction cannot consume source liabilities."
        )
    _payload_identifier(context, "source_rule_id")
    _payload_identifier(context, "source_result_id")
    _payload_identifier(context, "completion_event_type")
    _object_payload(context.get("completion_event_payload"), "completion_event_payload")
    return True


def _validate_destroyed_damage_matches_state(
    *,
    state: GameState,
    damage_application: DamageApplication,
) -> None:
    if damage_application.damage_kind is not DamageKind.MORTAL:
        raise GameLifecycleError("Applied mortal-wound destruction requires mortal damage.")
    if not damage_application.destroyed:
        raise GameLifecycleError("Applied mortal-wound destruction requires lethal damage.")
    model = model_by_id(state=state, model_instance_id=damage_application.model_instance_id)
    if model.wounds_remaining != damage_application.final_wounds_remaining or model.is_alive:
        raise GameLifecycleError("Applied mortal-wound destruction damage state drift.")


def _object_payload(value: object, field_name: str) -> dict[str, JsonValue]:
    payload = validate_json_value(value)
    if not isinstance(payload, dict):
        raise GameLifecycleError(
            f"Applied mortal-wound destruction {field_name} must be an object."
        )
    return payload


def _payload_identifier(payload: dict[str, JsonValue], key: str) -> str:
    return _validate_identifier(key, payload.get(key))


_validate_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "continue_applied_mortal_wound_destruction_with_rule_reactions",
    "validate_applied_damage_rule_destruction_context",
)
