"""Core Fall Back hazards use the shared mortal-wound authority before movement."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.damage_allocation import MortalWoundApplicationProgress
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.desperate_escape import DESPERATE_ESCAPE_BATTLE_SHOCK_SOURCE_RULE_ID
from warhammer40k_core.engine.destruction_provenance import DestructionSourceKind
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.hazard import hazard_mortal_wounds_per_failed_roll
from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
    MortalWoundDestructionEvidence,
)
from warhammer40k_core.engine.mortal_wound_destruction_routing import (
    continue_rule_mortal_wound_application,
    queue_rule_mortal_wound_request,
    resolve_rule_mortal_wound_decision,
)
from warhammer40k_core.engine.mortal_wound_feel_no_pain_hooks import (
    MortalWoundApplicationCompletionContext,
    MortalWoundFeelNoPainContinuationContext,
    MortalWoundFeelNoPainContinuationHookBinding,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.phases.movement_state import FallBackActionResult

SOURCE_KIND = "desperate_escape_hazard_mortals"
STARTED = "desperate_escape_hazard_mortals_started"
RESOLVED = "desperate_escape_hazard_mortals_resolved"
CONTINUED = "desperate_escape_hazard_movement_continued"


def desperate_escape_mortal_wound_binding() -> MortalWoundFeelNoPainContinuationHookBinding:
    return MortalWoundFeelNoPainContinuationHookBinding(
        hook_id="core:desperate-escape:hazard-mortals",
        source_id=DESPERATE_ESCAPE_BATTLE_SHOCK_SOURCE_RULE_ID,
        source_kind=SOURCE_KIND,
        handler=_apply_decision,
        completion_handler=_complete,
    )


def begin_escape_mortals(
    *,
    state: GameState,
    decisions: DecisionController,
    fall_back_result: FallBackActionResult,
    action_result: DecisionResult,
    movement_proposal_request_id: str,
) -> LifecycleStatus | None:
    if not fall_back_result.failed_desperate_escape_rolls:
        return None
    unit = rules_unit_view_by_id(state=state, unit_instance_id=fall_back_result.unit_instance_id)
    source: dict[str, JsonValue] = {
        "source_kind": SOURCE_KIND,
        "source_rule_id": DESPERATE_ESCAPE_BATTLE_SHOCK_SOURCE_RULE_ID,
        "phase": BattlePhase.MOVEMENT.value,
        "unit_instance_id": unit.unit_instance_id,
        "movement_proposal_request_id": movement_proposal_request_id,
        "action_result": validate_json_value(action_result.to_payload()),
        "fall_back_result": validate_json_value(fall_back_result.to_payload()),
    }
    application_id = f"desperate-escape:{movement_proposal_request_id}:hazards"
    if any(
        e.event_type == STARTED
        and isinstance(e.payload, dict)
        and e.payload.get("application_id") == application_id
        for e in decisions.event_log.records
    ):
        raise GameLifecycleError("Desperate Escape hazards cannot be applied twice.")
    progress = MortalWoundApplicationProgress.start(
        application_id=application_id,
        source_rule_id=DESPERATE_ESCAPE_BATTLE_SHOCK_SOURCE_RULE_ID,
        source_context=source,
        target_unit_instance_id=unit.unit_instance_id,
        defender_player_id=unit.owner_player_id,
        mortal_wounds=(
            len(fall_back_result.failed_desperate_escape_rolls)
            * hazard_mortal_wounds_per_failed_roll(unit)
        ),
        spill_over=True,
        destruction_evidence=MortalWoundDestructionEvidence.for_non_attack_state(
            state=state,
            destroying_player_id=unit.owner_player_id,
            source_rules_unit_instance_id=None,
            source_model_instance_id=None,
            destruction_source_kind=DestructionSourceKind.ABILITY,
            action_phase=BattlePhase.MOVEMENT,
            source_step="desperate_escape_hazards",
        ),
    )
    decisions.event_log.append(STARTED, {"application_id": application_id, **source})
    routed = continue_rule_mortal_wound_application(
        state=state,
        decisions=decisions,
        request_id=state.next_decision_request_id(),
        progress=progress,
        dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
    )
    if routed.request is not None:
        queue_rule_mortal_wound_request(decisions, routed.request)
        return LifecycleStatus.waiting_for_decision(
            stage=state.stage, decision_request=routed.request
        )
    if routed.application is None:
        raise GameLifecycleError("Desperate Escape hazards did not finish routing.")
    return _complete(
        MortalWoundApplicationCompletionContext(
            state=state,
            decisions=decisions,
            progress=routed.progress,
            application=routed.application,
        )
    )


def _apply_decision(context: MortalWoundFeelNoPainContinuationContext) -> LifecycleStatus | None:
    routed = resolve_rule_mortal_wound_decision(
        state=context.state,
        decisions=context.decisions,
        request=context.request,
        result=context.result,
        next_request_id=context.state.next_decision_request_id(),
        dice_manager=context.dice_manager,
    )
    if routed.request is not None:
        queue_rule_mortal_wound_request(context.decisions, routed.request)
        return LifecycleStatus.waiting_for_decision(
            stage=context.state.stage, decision_request=routed.request
        )
    if routed.application is None:
        raise GameLifecycleError("Desperate Escape mortal-wound decision did not complete.")
    return _complete(
        MortalWoundApplicationCompletionContext(
            state=context.state,
            decisions=context.decisions,
            progress=routed.progress,
            application=routed.application,
        )
    )


def _complete(context: MortalWoundApplicationCompletionContext) -> LifecycleStatus | None:
    source = context.progress.source_context
    if not isinstance(source, dict) or source.get("source_kind") != SOURCE_KIND:
        raise GameLifecycleError("Desperate Escape mortal-wound source drift.")
    _validate_selection(context.state, source)
    context.decisions.event_log.append(
        RESOLVED,
        {
            **source,
            "application_id": context.progress.application_id,
            "mortal_application": validate_json_value(context.application.to_payload()),
        },
    )
    return None


def pending_escape_movement(
    *, state: GameState, decisions: DecisionController
) -> dict[str, JsonValue] | None:
    continued: set[str] = set()
    for event in decisions.event_log.records:
        if event.event_type != CONTINUED:
            continue
        if not isinstance(event.payload, dict):
            raise GameLifecycleError("Desperate Escape continuation receipt is invalid.")
        application_id = event.payload.get("application_id")
        if not isinstance(application_id, str):
            raise GameLifecycleError("Desperate Escape continuation receipt lacks its packet ID.")
        continued.add(application_id)
    pending = [
        e.payload
        for e in decisions.event_log.records
        if e.event_type == RESOLVED
        and isinstance(e.payload, dict)
        and e.payload.get("application_id") not in continued
    ]
    if len(pending) > 1:
        raise GameLifecycleError("Multiple Desperate Escape movements await continuation.")
    if not pending:
        return None
    source = pending[0]
    _validate_selection(state, source)
    return source


def _validate_selection(state: GameState, source: dict[str, JsonValue]) -> None:
    movement = state.movement_phase_state
    if (
        state.current_battle_phase is not BattlePhase.MOVEMENT
        or movement is None
        or movement.active_selection is None
        or movement.active_selection.unit_instance_id != source.get("unit_instance_id")
    ):
        raise GameLifecycleError("Desperate Escape mortal-wound continuation lost its selection.")
