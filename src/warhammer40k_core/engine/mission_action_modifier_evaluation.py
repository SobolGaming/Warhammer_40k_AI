"""OC choices owned by a Mission Action option evaluation and its checkpoint."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.descriptor_hash import canonical_payload_sha256
from warhammer40k_core.engine.modifier_evaluation import SELECT_MODIFIER_IGNORES_DECISION_TYPE
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.objective_control_modifier_evaluation import (
    evaluate_objective_control_modifiers,
)
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.random_profile_evaluation import evaluate_unit_profile_characteristics
from warhammer40k_core.engine.rules_units import rules_unit_views_from_armies

if TYPE_CHECKING:
    from warhammer40k_core.core.missions import MissionActionDefinition
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.decision_request import DecisionRequest
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


MISSION_ACTION_OC_SCOPE_KEY = "objective_control_modifier_scope_id"


@dataclass(frozen=True, slots=True)
class MissionActionModifierEvaluation:
    registry: RuntimeModifierRegistry
    occurrence_id: str | None
    pending_status: LifecycleStatus | None = None


def prepare_mission_action_modifiers(
    *,
    state: GameState,
    decisions: DecisionController,
    player_id: str,
    actions: tuple[MissionActionDefinition, ...],
    runtime_modifier_registry: RuntimeModifierRegistry,
    explicit_action_id: str | None = None,
) -> MissionActionModifierEvaluation:
    from warhammer40k_core.engine.mission_action_eligibility import (
        mission_action_pre_oc_ineligibility_reason,
    )
    from warhammer40k_core.engine.random_objective_control import (
        prepare_mission_action_profile_values,
    )

    phase = state.current_battle_phase
    battlefield = state.battlefield_state
    if phase is None or battlefield is None:
        raise GameLifecycleError("Mission Action modifier evaluation requires battle context.")
    previous = next(
        (
            record.result.result_id
            for record in reversed(decisions.records)
            if record.request.decision_type != SELECT_MODIFIER_IGNORES_DECISION_TYPE
        ),
        "initial",
    )
    occurrence_id = "mission-action-oc:" + canonical_payload_sha256(
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "player_id": player_id,
            "phase": phase.value,
            "previous_result_id": previous,
            "actions": sorted(action.mission_action_id for action in actions),
        }
    )
    from warhammer40k_core.engine.catalog_modifier_ignore import (
        ModifierIgnoreKind,
        modifier_ignore_permission_candidates_present,
        modifier_ignore_permissions_for_subject,
    )

    permitted = modifier_ignore_permission_candidates_present(
        state=state,
        ability_indexes=tuple(
            runtime_modifier_registry.modifier_permission_index(owner) for owner in state.player_ids
        ),
    ) and any(
        modifier_ignore_permissions_for_subject(
            state=state,
            ability_index=runtime_modifier_registry.modifier_permission_index(unit.owner_player_id),
            unit_instance_id=unit.unit_instance_id,
            model_instance_id=model.model_instance_id,
            kind=ModifierIgnoreKind.OBJECTIVE_CONTROL_CHARACTERISTIC,
        )
        for unit in rules_unit_views_from_armies(armies=tuple(state.army_definitions))
        for model in unit.alive_models()
    )
    profile_scope = (
        f"mission-action-options:decision-request-{state.decision_request_count + 1:06d}"
    )
    for record in decisions.records:
        payload = record.request.payload
        if record.request.decision_type != SELECT_MODIFIER_IGNORES_DECISION_TYPE or not isinstance(
            payload, dict
        ):
            continue
        source = payload.get("source_context")
        if isinstance(source, dict) and source.get("boundary_id") == occurrence_id:
            saved_scope = source.get("profile_scope_id")
            if not isinstance(saved_scope, str):
                raise GameLifecycleError("Mission Action modifier profile scope drifted.")
            profile_scope = saved_scope
            break
    prepare_mission_action_profile_values(
        state=state,
        decisions=decisions,
        player_id=player_id,
        actions=actions,
        runtime_modifier_registry=runtime_modifier_registry,
        scope_id=profile_scope,
    )
    if not permitted or not any(action.start_phase == phase.value for action in actions):
        return MissionActionModifierEvaluation(runtime_modifier_registry, None)
    placed_ids = frozenset(battlefield.placed_model_ids())
    subjects: list[tuple[str, str]] = []
    for unit in rules_unit_views_from_armies(armies=tuple(state.army_definitions)):
        if (
            mission_action_pre_oc_ineligibility_reason(
                state=state,
                player_id=player_id,
                unit_instance_id=unit.unit_instance_id,
                runtime_modifier_registry=runtime_modifier_registry,
            )
            is not None
        ):
            continue
        model_ids = tuple(
            model.model_instance_id
            for model in unit.alive_models()
            if model.model_instance_id in placed_ids
        )
        evaluate_unit_profile_characteristics(
            state=state,
            decisions=decisions,
            unit_instance_id=unit.unit_instance_id,
            scope_id=profile_scope,
            characteristics=(Characteristic.OBJECTIVE_CONTROL,),
            model_instance_ids=model_ids,
        )
        subjects.extend((unit.unit_instance_id, model_id) for model_id in model_ids)
    evaluated = evaluate_objective_control_modifiers(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=phase,
            runtime_modifier_registry=runtime_modifier_registry,
        ),
        decisions=decisions,
        occurrence_id=occurrence_id,
        ability_indexes_by_player_id={
            owner: runtime_modifier_registry.modifier_permission_index(owner)
            for owner in state.player_ids
        },
        additional_subjects=tuple(subjects),
        prepare_random_profiles=False,
        source_context={
            "continuation": "phase" if explicit_action_id is None else "mission_action",
            "source_kind": "mission_action_objective_control",
            "player_id": player_id,
            "mission_action_id": explicit_action_id,
            "boundary_id": occurrence_id,
            "profile_scope_id": profile_scope,
            "phase": phase.value,
            "battle_round": state.battle_round,
        },
    )
    return MissionActionModifierEvaluation(
        evaluated.context.runtime_modifier_registry,
        occurrence_id if evaluated.context.modifier_traces or evaluated.pending_status else None,
        evaluated.pending_status,
    )


def mission_action_registry_for_request(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> RuntimeModifierRegistry:
    from warhammer40k_core.engine.objective_control_checkpoint_selection import (
        registry_for_checkpoint_selections,
    )
    from warhammer40k_core.engine.primary_mission_boundary_checkpoint import (
        primary_mission_boundary_checkpoint_for_request,
    )

    payload = request.payload
    if not isinstance(payload, dict) or MISSION_ACTION_OC_SCOPE_KEY not in payload:
        raise GameLifecycleError("Mission Action request lacks its OC evaluation occurrence.")
    scope_id = payload[MISSION_ACTION_OC_SCOPE_KEY]
    if scope_id is not None and (type(scope_id) is not str or not scope_id):
        raise GameLifecycleError("Mission Action OC evaluation occurrence is malformed.")
    checkpoint = primary_mission_boundary_checkpoint_for_request(
        event_records=decisions.event_log.records,
        request_id=request.request_id,
    )[1]
    if checkpoint.objective_control_modifier_scope_id != payload[MISSION_ACTION_OC_SCOPE_KEY]:
        raise GameLifecycleError("Mission Action modifier occurrence differs from checkpoint.")
    return registry_for_checkpoint_selections(
        state=state,
        checkpoint=checkpoint,
        decision_records=decisions.records,
        runtime_modifier_registry=runtime_modifier_registry,
    )
