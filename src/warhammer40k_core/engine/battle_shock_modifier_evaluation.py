"""Battle-shock modifier preparation and pure occurrence-bound selection readers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.battle_shock import BattleShockTestReason, BattleShockTestRequest
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockHookRegistry,
    BattleShockModifierApplication,
    BattleShockModifierContext,
)
from warhammer40k_core.engine.battle_shock_model_authority import (
    battle_shock_model_ids,
    command_test_allows_off_battlefield,
)
from warhammer40k_core.engine.catalog_modifier_ignore import ModifierIgnoreKind
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.modifier_evaluation import (
    ModifierEvaluationSubject,
    selected_modifiers_for_occurrence,
)
from warhammer40k_core.engine.nonattack_modifier_evaluation import evaluate_leadership_modifiers
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


@dataclass(frozen=True, slots=True)
class BattleShockModifierEvaluation:
    request: BattleShockTestRequest
    pending_status: LifecycleStatus | None


def prepare_battle_shock_modifiers(
    *,
    state: GameState,
    decisions: DecisionController,
    request: BattleShockTestRequest,
    ability_index: AbilityCatalogIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
    battle_shock_hooks: BattleShockHookRegistry,
    active_player_id: str,
    phase: BattlePhase,
    phase_start_battle_shocked_unit_ids: tuple[str, ...],
    additional_modifier_applications: tuple[BattleShockModifierApplication, ...] = (),
    source_context: dict[str, JsonValue] | None = None,
) -> BattleShockModifierEvaluation:
    if state.battlefield_state is None:
        raise GameLifecycleError("Battle-shock modifier preflight requires battlefield state.")
    unit = rules_unit_view_by_id(state=state, unit_instance_id=request.unit_instance_id)
    model_ids = battle_shock_model_ids(
        rules_unit=unit,
        battlefield=state.battlefield_state,
        state=state,
        allow_off_battlefield=command_test_allows_off_battlefield(
            reason=request.reason,
            phase=phase,
            player_id=request.player_id,
            active_player_id=active_player_id,
        ),
    )
    applications = battle_shock_hooks.modifier_applications_for(
        BattleShockModifierContext(
            state=state,
            request=request,
            active_player_id=active_player_id,
            phase=phase,
            phase_start_battle_shocked_unit_ids=phase_start_battle_shocked_unit_ids,
        )
    )
    evaluation = evaluate_leadership_modifiers(
        state=state,
        decisions=decisions,
        unit_instance_id=request.unit_instance_id,
        occurrence_id=request.request_id,
        ability_index=ability_index,
        runtime_modifier_registry=runtime_modifier_registry,
        model_instance_ids=model_ids,
        roll_modifiers=tuple(
            modifier
            for application in (*applications, *additional_modifier_applications)
            for modifier in application.modifiers
        ),
        roll_kind=ModifierIgnoreKind.BATTLE_SHOCK_ROLL,
        source_context=source_context
        if source_context is not None
        else {
            "continuation": "phase",
            "source_kind": "battle_shock",
            "battle_shock_request_id": request.request_id,
        },
    )
    if evaluation.pending_status is not None:
        return BattleShockModifierEvaluation(request, evaluation.pending_status)
    return BattleShockModifierEvaluation(
        replace(request, leadership_target=evaluation.leadership_target), None
    )


def selected_battle_shock_roll_modifiers(
    *,
    decision_records: tuple[DecisionRecord, ...],
    request: BattleShockTestRequest,
    modifiers: tuple[RollModifier, ...],
) -> tuple[RollModifier, ...]:
    return selected_modifiers_for_occurrence(
        decision_records=decision_records,
        occurrence_id=f"{request.request_id}:test-roll",
        subject=ModifierEvaluationSubject(
            unit_instance_id=request.unit_instance_id, kind=ModifierIgnoreKind.BATTLE_SHOCK_ROLL
        ),
        modifiers=modifiers,
    )


def pending_command_modifier_has_candidate_authority(
    *,
    state: GameState,
    pending_requests: tuple[DecisionRequest, ...],
    unit_instance_id: str,
    reason: BattleShockTestReason,
) -> bool:
    """Recognize the explicit pre-roll cursor before an in-flight test exists."""
    from warhammer40k_core.engine.command_battle_shock_candidates import (
        command_battle_shock_request_id,
    )
    from warhammer40k_core.engine.modifier_evaluation import SELECT_MODIFIER_IGNORES_DECISION_TYPE

    if len(pending_requests) != 1:
        return False
    request = pending_requests[0]
    if request.decision_type != SELECT_MODIFIER_IGNORES_DECISION_TYPE:
        return False
    if state.active_player_id is None or not isinstance(request.payload, dict):
        raise GameLifecycleError("Command modifier preflight lacks battle context.")
    test_id = command_battle_shock_request_id(
        battle_round=state.battle_round,
        active_player_id=state.active_player_id,
        unit_instance_id=unit_instance_id,
        reason=reason,
    )
    payload = request.payload
    subject = ModifierEvaluationSubject.from_payload(payload["subject"])
    if (
        payload["source_context"]
        != {
            "continuation": "phase",
            "source_kind": "battle_shock",
            "battle_shock_request_id": test_id,
        }
        or subject.unit_instance_id != unit_instance_id
    ):
        raise GameLifecycleError("Command modifier preflight candidate drifted.")
    expected_scope = (
        f"{test_id}:leadership:{subject.model_instance_id}"
        if subject.kind is ModifierIgnoreKind.LEADERSHIP_CHARACTERISTIC
        else f"{test_id}:test-roll"
    )
    if (
        subject.kind
        not in {ModifierIgnoreKind.LEADERSHIP_CHARACTERISTIC, ModifierIgnoreKind.BATTLE_SHOCK_ROLL}
        or payload["occurrence_id"] != expected_scope
    ):
        raise GameLifecycleError("Command modifier preflight occurrence drifted.")
    return True
