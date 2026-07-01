from __future__ import annotations

from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.event_log import canonical_json
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.sticky_objective_control import (
    PhaseEndObjectiveControlContext,
    PhaseEndObjectiveControlHookBinding,
    StickyObjectiveControlState,
    apply_sticky_objective_control,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_move_completed_hooks import (
    UnitMoveCompletedContext,
    UnitMoveCompletedMortalWoundEffect,
    UnitMoveCompletedMortalWoundHookBinding,
)

CONTRIBUTION_ID = "warhammer_40000_11th:aeldari:detachment:corsair_coterie:rule:scaffold"
SOURCE_RULE_ID = "phase17g:aeldari:corsair-coterie:relentless-raiders"
RELENTLESS_RAIDERS_HOOK_ID = (
    "warhammer_40000_11th:aeldari:detachment:corsair_coterie:relentless_raiders"
)
VOID_THIEVES_HOOK_ID = "warhammer_40000_11th:aeldari:detachment:corsair_coterie:void_thieves"
CORSAIR_COTERIE_DETACHMENT_ID = "corsair-coterie"
RELENTLESS_RAIDERS_EFFECT_KIND = "aeldari_corsair_coterie_relentless_raiders"
VOID_THIEVES_EFFECT_KIND = "aeldari_corsair_coterie_void_thieves"
ANHRATHE = "ANHRATHE"


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        unit_move_completed_mortal_wound_hook_bindings=(
            UnitMoveCompletedMortalWoundHookBinding(
                hook_id=RELENTLESS_RAIDERS_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=relentless_raiders_mortal_wound_effects,
            ),
        ),
        phase_end_objective_control_hook_bindings=(
            PhaseEndObjectiveControlHookBinding(
                hook_id=VOID_THIEVES_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=void_thieves_sticky_states,
            ),
        ),
    )


def relentless_raiders_mortal_wound_effects(
    context: UnitMoveCompletedContext,
) -> tuple[UnitMoveCompletedMortalWoundEffect, ...]:
    if type(context) is not UnitMoveCompletedContext:
        raise GameLifecycleError("Relentless Raiders requires a movement completion context.")
    record = _objective_control_record_for_state(
        state_context=context.state,
        completed_phase=context.completed_phase,
        ruleset_descriptor=context.ruleset_descriptor,
        runtime_modifier_registry=context.runtime_modifier_registry,
    )
    if record is None:
        return ()
    effects: list[UnitMoveCompletedMortalWoundEffect] = []
    for army in context.state.army_definitions:
        if not _army_has_corsair_coterie(army):
            continue
        if army.player_id == context.triggering_player_id:
            continue
        for result in record.results:
            if result.controlled_by_player_id != army.player_id:
                continue
            if not _result_has_unit_in_range(
                result=result,
                unit_instance_id=context.triggering_unit_instance_id,
            ):
                continue
            effects.append(
                UnitMoveCompletedMortalWoundEffect(
                    hook_id=RELENTLESS_RAIDERS_HOOK_ID,
                    source_id=SOURCE_RULE_ID,
                    source_rule_id=SOURCE_RULE_ID,
                    target_unit_instance_id=context.triggering_unit_instance_id,
                    target_player_id=context.triggering_player_id,
                    rolling_player_id=army.player_id,
                    trigger_event_id=context.trigger_event_id,
                    roll_threshold=2,
                    mortal_wounds_expression=DiceExpression(quantity=1, sides=3),
                    replay_payload={
                        "effect_kind": RELENTLESS_RAIDERS_EFFECT_KIND,
                        "detachment_id": CORSAIR_COTERIE_DETACHMENT_ID,
                        "objective_id": result.objective_id,
                        "controlling_player_id": army.player_id,
                        "triggering_player_id": context.triggering_player_id,
                        "triggering_unit_instance_id": context.triggering_unit_instance_id,
                        "trigger_event_id": context.trigger_event_id,
                        "movement_action": context.movement_action,
                    },
                )
            )
    return tuple(
        sorted(
            effects,
            key=lambda effect: (
                effect.target_unit_instance_id,
                canonical_json(effect.replay_payload),
            ),
        )
    )


def void_thieves_sticky_states(
    context: PhaseEndObjectiveControlContext,
) -> tuple[StickyObjectiveControlState, ...]:
    if type(context) is not PhaseEndObjectiveControlContext:
        raise GameLifecycleError("Void Thieves requires a phase-end objective context.")
    record = _objective_control_record_for_state(
        state_context=context.state,
        completed_phase=context.completed_phase,
        ruleset_descriptor=context.state.runtime_ruleset_descriptor(),
        runtime_modifier_registry=context.runtime_modifier_registry,
    )
    if record is None:
        return ()
    states: list[StickyObjectiveControlState] = []
    for army in context.state.army_definitions:
        if not _army_has_corsair_coterie(army):
            continue
        states.extend(_void_thieves_states_for_army(context=context, army=army, record=record))
    return tuple(sorted(states, key=lambda state: state.state_id))


def _void_thieves_states_for_army(
    *,
    context: PhaseEndObjectiveControlContext,
    army: ArmyDefinition,
    record: ObjectiveControlRecord,
) -> tuple[StickyObjectiveControlState, ...]:
    anhrathe_unit_ids = {
        unit.unit_instance_id for unit in army.units if _unit_has_keyword(unit, ANHRATHE)
    }
    if not anhrathe_unit_ids:
        return ()
    states: list[StickyObjectiveControlState] = []
    seen_state_keys: set[tuple[str, str]] = set()
    for result in record.results:
        if result.controlled_by_player_id != army.player_id:
            continue
        for unit_instance_id in sorted(anhrathe_unit_ids):
            if not _result_has_unit_in_range(result=result, unit_instance_id=unit_instance_id):
                continue
            state_key = (result.objective_id, unit_instance_id)
            if state_key in seen_state_keys:
                continue
            seen_state_keys.add(state_key)
            states.append(
                StickyObjectiveControlState(
                    state_id=(
                        f"void-thieves:{context.state.game_id}:"
                        f"round-{context.state.battle_round:02d}:"
                        f"{_active_player_id(context)}:{context.completed_phase.value}:"
                        f"{result.objective_id}:{unit_instance_id}"
                    ),
                    game_id=context.state.game_id,
                    player_id=army.player_id,
                    objective_id=result.objective_id,
                    source_rule_id=SOURCE_RULE_ID,
                    source_event_id=(
                        f"void-thieves-phase-end:{context.state.game_id}:"
                        f"round-{context.state.battle_round:02d}:"
                        f"{_active_player_id(context)}:{context.completed_phase.value}"
                    ),
                    battle_round=context.state.battle_round,
                    phase=context.completed_phase.value,
                    active_player_id=_active_player_id(context),
                    originating_unit_instance_id=unit_instance_id,
                    destroyed_unit_instance_id=unit_instance_id,
                    replay_payload={
                        "effect_kind": VOID_THIEVES_EFFECT_KIND,
                        "detachment_id": CORSAIR_COTERIE_DETACHMENT_ID,
                        "objective_id": result.objective_id,
                        "originating_unit_instance_id": unit_instance_id,
                        "controlling_player_id": army.player_id,
                        "required_keyword": ANHRATHE,
                    },
                )
            )
    return tuple(sorted(states, key=lambda state: state.state_id))


def _objective_control_record_for_state(
    *,
    state_context: object,
    completed_phase: BattlePhase,
    ruleset_descriptor: RulesetDescriptor,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> ObjectiveControlRecord | None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state_context) is not GameState:
        raise GameLifecycleError("Corsair Coterie objective control requires GameState.")
    if type(completed_phase) is not BattlePhase:
        raise GameLifecycleError("Corsair Coterie objective control requires BattlePhase.")
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Corsair Coterie objective control requires RulesetDescriptor.")
    if type(runtime_modifier_registry) is not RuntimeModifierRegistry:
        raise GameLifecycleError(
            "Corsair Coterie objective control requires RuntimeModifierRegistry."
        )
    if state_context.mission_setup is None or state_context.battlefield_state is None:
        return None
    record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state_context,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=completed_phase,
            ruleset_descriptor=ruleset_descriptor,
            runtime_modifier_registry=runtime_modifier_registry,
        )
    )
    return apply_sticky_objective_control(
        record=record,
        states=tuple(state_context.sticky_objective_control_states),
    )


def _result_has_unit_in_range(
    *,
    result: ObjectiveControlResult,
    unit_instance_id: str,
) -> bool:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    return any(
        contribution.unit_instance_id == requested_unit_id for contribution in result.contributors
    )


def _army_has_corsair_coterie(army: ArmyDefinition) -> bool:
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError("Corsair Coterie requires ArmyDefinition.")
    return CORSAIR_COTERIE_DETACHMENT_ID in army.detachment_selection.detachment_ids


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Corsair Coterie keyword check requires UnitInstance.")
    requested_keyword = _canonical_keyword(keyword)
    return any(
        _canonical_keyword(stored_keyword) == requested_keyword
        for stored_keyword in (*unit.keywords, *unit.faction_keywords)
    )


def _active_player_id(context: PhaseEndObjectiveControlContext) -> str:
    active_player_id = context.state.active_player_id
    if active_player_id is None:
        raise GameLifecycleError("Corsair Coterie requires an active player.")
    return active_player_id


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Corsair Coterie {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Corsair Coterie {field_name} must not be empty.")
    return stripped


def _canonical_keyword(keyword: str) -> str:
    return _validate_identifier("keyword", keyword).upper().replace("_", " ")
