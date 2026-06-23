from __future__ import annotations

from typing import cast

from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.core.faction_aliases import CHAOS_DAEMONS_FACTION_ID
from warhammer40k_core.engine.army_mustering import ArmyDefinition, EnhancementAssignment
from warhammer40k_core.engine.battlefield_state import PlacementError
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.enhancement_effects import (
    EnhancementDatasheetAbilityGrant,
    EnhancementEffectBinding,
    EnhancementEffectContext,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.reserves import ReserveOrigin
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.turn_end_hooks import (
    SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
    TurnEndHookBinding,
    TurnEndRequestContext,
    TurnEndResultContext,
)
from warhammer40k_core.engine.unit_destroyed_hooks import (
    UnitDestroyedContext,
    UnitDestroyedHookBinding,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_proximity import unit_within_enemy_engagement_range

CONTRIBUTION_ID = (
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:enhancement:fade_to_darkness"
)

DETACHMENT_ID = "shadow-legion"
SHADOW_LEGION_KEYWORD = "SHADOW LEGION"

LEAPING_SHADOWS_ENHANCEMENT_ID = "000009980002"
LEAPING_SHADOWS_SOURCE_RULE_ID = (
    "phase17f:phase17e:enhancement:chaos-daemons:shadow-legion:000009980002"
)
LEAPING_SHADOWS_EFFECT_ID = (
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:"
    "enhancement:leaping_shadows:scouts_9"
)
LEAPING_SHADOWS_ABILITY_ID = "chaos-daemons:shadow-legion:leaping-shadows:scouts-9"
LEAPING_SHADOWS_SCOUTS_DISTANCE = '9"'

FADE_TO_DARKNESS_ENHANCEMENT_ID = "000009980004"
FADE_TO_DARKNESS_SOURCE_RULE_ID = (
    "phase17f:phase17e:enhancement:chaos-daemons:shadow-legion:000009980004"
)
SOURCE_RULE_ID = FADE_TO_DARKNESS_SOURCE_RULE_ID
ENHANCEMENT_ID = FADE_TO_DARKNESS_ENHANCEMENT_ID
HOOK_ID = "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:enhancement:fade_to_darkness"
UNIT_DESTROYED_HOOK_ID = f"{HOOK_ID}:unit-destroyed"
TURN_END_HOOK_ID = f"{HOOK_ID}:turn-end-reserves"
SUBMISSION_KIND = "chaos_daemons_shadow_legion_fade_to_darkness_turn_end"
ELIGIBLE_EVENT = "chaos_daemons_shadow_legion_fade_to_darkness_eligible"
USED_EVENT = "chaos_daemons_shadow_legion_fade_to_darkness_used"
DECLINED_EVENT = "chaos_daemons_shadow_legion_fade_to_darkness_declined"


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        enhancement_effect_bindings=(
            EnhancementEffectBinding(
                effect_id=LEAPING_SHADOWS_EFFECT_ID,
                source_id=LEAPING_SHADOWS_SOURCE_RULE_ID,
                enhancement_id=LEAPING_SHADOWS_ENHANCEMENT_ID,
                handler=leaping_shadows_effect,
            ),
        ),
        unit_destroyed_hook_bindings=(
            UnitDestroyedHookBinding(
                hook_id=UNIT_DESTROYED_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=record_fade_to_darkness_destroyed_enemy_unit,
            ),
        ),
        turn_end_hook_bindings=(
            TurnEndHookBinding(
                hook_id=TURN_END_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                request_handler=fade_to_darkness_turn_end_request,
                result_handler=apply_fade_to_darkness_turn_end_result,
            ),
        ),
    )


def leaping_shadows_effect(
    context: EnhancementEffectContext,
) -> tuple[EnhancementDatasheetAbilityGrant, ...]:
    if type(context) is not EnhancementEffectContext:
        raise GameLifecycleError("Leaping Shadows requires an EnhancementEffectContext.")
    if context.assignment.enhancement_id != LEAPING_SHADOWS_ENHANCEMENT_ID:
        return ()
    if not (
        context.army.detachment_selection.faction_id == CHAOS_DAEMONS_FACTION_ID
        and DETACHMENT_ID in context.army.detachment_selection.detachment_ids
    ):
        raise GameLifecycleError("Leaping Shadows requires Shadow Legion.")
    if not _unit_has_keyword(context.target_unit, SHADOW_LEGION_KEYWORD):
        raise GameLifecycleError("Leaping Shadows requires a Shadow Legion model.")
    view = rules_unit_view_by_id(
        state=context.state,
        unit_instance_id=context.target_unit.unit_instance_id,
    )
    if view.owner_player_id != context.army.player_id:
        raise GameLifecycleError("Leaping Shadows rules unit owner drift.")
    descriptor = _leaping_shadows_scouts_descriptor()
    return tuple(
        EnhancementDatasheetAbilityGrant(
            effect_id=LEAPING_SHADOWS_EFFECT_ID,
            source_id=LEAPING_SHADOWS_SOURCE_RULE_ID,
            enhancement_id=LEAPING_SHADOWS_ENHANCEMENT_ID,
            target_unit_instance_id=component.unit.unit_instance_id,
            datasheet_ability=descriptor,
            replay_payload={
                "effect_kind": "leaping_shadows_scouts_9",
                "assignment_source_id": context.assignment.source_id,
                "target_unit_selection_id": context.assignment.target_unit_selection_id,
                "bearer_unit_instance_id": context.target_unit.unit_instance_id,
                "target_rules_unit_instance_id": view.unit_instance_id,
                "component_unit_instance_id": component.unit.unit_instance_id,
                "scouts_distance_inches": 9,
            },
        )
        for component in view.components
    )


def record_fade_to_darkness_destroyed_enemy_unit(context: UnitDestroyedContext) -> None:
    if type(context) is not UnitDestroyedContext:
        raise GameLifecycleError("Fade to Darkness requires a unit-destroyed context.")
    if context.completed_phase is not BattlePhase.FIGHT:
        return
    attacking_unit_value = context.model_destroyed_payload.get("attacking_unit_instance_id")
    if type(attacking_unit_value) is not str or not attacking_unit_value.strip():
        return
    attacking_unit_id = _validate_identifier("attacking_unit_instance_id", attacking_unit_value)
    for army in _shadow_legion_armies(context.state):
        if army.player_id != context.destroying_player_id:
            continue
        if not _assigned_fade_unit_id_matches(army, unit_instance_id=attacking_unit_id):
            continue
        if _eligible_event_recorded_for_destroyed_unit(
            context,
            unit_instance_id=attacking_unit_id,
            destroyed_unit_instance_id=context.destroyed_unit_instance_id,
        ):
            return
        context.decisions.event_log.append(
            ELIGIBLE_EVENT,
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "active_player_id": context.state.active_player_id,
                "phase": context.completed_phase.value,
                "player_id": army.player_id,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": UNIT_DESTROYED_HOOK_ID,
                "enhancement_id": ENHANCEMENT_ID,
                "target_unit_instance_id": attacking_unit_id,
                "destroyed_enemy_unit_instance_id": context.destroyed_unit_instance_id,
                "destroyed_player_id": context.destroyed_player_id,
                "model_destroyed_event_id": context.model_destroyed_event_id,
            },
        )
        return


def fade_to_darkness_turn_end_request(context: TurnEndRequestContext) -> DecisionRequest | None:
    if type(context) is not TurnEndRequestContext:
        raise GameLifecycleError("Fade to Darkness requires a turn-end request context.")
    if context.completed_phase is not BattlePhase.FIGHT:
        return None
    active_player_id = _active_player_id(context.state)
    for army in _shadow_legion_armies(context.state):
        for _assignment, unit in _assigned_units(army, enhancement_id=ENHANCEMENT_ID):
            destroyed_enemy_unit_ids = _destroyed_enemy_unit_ids_for_fade_unit(
                context,
                player_id=army.player_id,
                unit_instance_id=unit.unit_instance_id,
            )
            if not destroyed_enemy_unit_ids:
                continue
            if _decision_recorded_this_phase(
                context,
                unit_instance_id=unit.unit_instance_id,
            ):
                continue
            if not _unit_can_enter_strategic_reserves(
                context.state,
                unit_instance_id=unit.unit_instance_id,
            ):
                continue
            return DecisionRequest(
                request_id=context.state.next_decision_request_id(),
                decision_type=SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
                actor_id=army.player_id,
                payload={
                    "game_id": context.state.game_id,
                    "battle_round": context.state.battle_round,
                    "active_player_id": active_player_id,
                    "phase": context.completed_phase.value,
                    "player_id": army.player_id,
                    "source_rule_id": SOURCE_RULE_ID,
                    "hook_id": TURN_END_HOOK_ID,
                    "enhancement_id": ENHANCEMENT_ID,
                    "target_unit_instance_id": unit.unit_instance_id,
                    "destroyed_enemy_unit_instance_ids": list(destroyed_enemy_unit_ids),
                },
                options=(
                    _fade_to_darkness_option(
                        player_id=army.player_id,
                        unit_instance_id=unit.unit_instance_id,
                        use_ability=True,
                    ),
                    _fade_to_darkness_option(
                        player_id=army.player_id,
                        unit_instance_id=unit.unit_instance_id,
                        use_ability=False,
                    ),
                ),
            )
    return None


def apply_fade_to_darkness_turn_end_result(context: TurnEndResultContext) -> bool:
    if type(context) is not TurnEndResultContext:
        raise GameLifecycleError("Fade to Darkness requires a turn-end result context.")
    request_payload = _payload_object(context.request.payload)
    if request_payload.get("hook_id") != TURN_END_HOOK_ID:
        return False
    result_payload = _payload_object(context.result.payload)
    _validate_result_payload_matches_request(
        request_payload=request_payload,
        result_payload=result_payload,
    )
    player_id = _payload_string(result_payload, "player_id")
    unit_instance_id = _payload_string(result_payload, "target_unit_instance_id")
    use_ability = _payload_bool(result_payload, "use_ability")
    army = _army_for_player(tuple(context.state.army_definitions), player_id=player_id)
    if not _assigned_fade_unit_id_matches(army, unit_instance_id=unit_instance_id):
        raise GameLifecycleError("Fade to Darkness assignment no longer matches unit.")
    if not use_ability:
        context.decisions.event_log.append(
            DECLINED_EVENT,
            _fade_to_darkness_event_payload(
                context=context,
                player_id=player_id,
                unit_instance_id=unit_instance_id,
                reserve_state_payload=None,
                use_ability=False,
            ),
        )
        return True
    if not _destroyed_enemy_unit_ids_for_fade_unit(
        context,
        player_id=player_id,
        unit_instance_id=unit_instance_id,
    ):
        raise GameLifecycleError("Fade to Darkness unit no longer has a destroyed enemy unit.")
    if not _unit_can_enter_strategic_reserves(context.state, unit_instance_id=unit_instance_id):
        raise GameLifecycleError("Fade to Darkness unit is no longer eligible.")
    reserve_state = context.state.reposition_unit_to_strategic_reserves(
        player_id=player_id,
        unit_instance_id=unit_instance_id,
        reserve_origin=ReserveOrigin.DURING_BATTLE_ABILITY,
        source_rule_ids=(SOURCE_RULE_ID,),
    )
    context.decisions.event_log.append(
        USED_EVENT,
        _fade_to_darkness_event_payload(
            context=context,
            player_id=player_id,
            unit_instance_id=unit_instance_id,
            reserve_state_payload=cast(JsonValue, reserve_state.to_payload()),
            use_ability=True,
        ),
    )
    return True


def _fade_to_darkness_option(
    *,
    player_id: str,
    unit_instance_id: str,
    use_ability: bool,
) -> DecisionOption:
    action = "use" if use_ability else "decline"
    return DecisionOption(
        option_id=f"chaos-daemons:shadow-legion:fade-to-darkness:{unit_instance_id}:{action}",
        label="Use Fade to Darkness" if use_ability else "Decline Fade to Darkness",
        payload={
            "submission_kind": SUBMISSION_KIND,
            "player_id": player_id,
            "source_rule_id": SOURCE_RULE_ID,
            "hook_id": TURN_END_HOOK_ID,
            "enhancement_id": ENHANCEMENT_ID,
            "target_unit_instance_id": unit_instance_id,
            "use_ability": use_ability,
        },
    )


def _shadow_legion_armies(state: object) -> tuple[ArmyDefinition, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Fade to Darkness requires GameState.")
    return tuple(
        army
        for army in state.army_definitions
        if army.detachment_selection.faction_id == CHAOS_DAEMONS_FACTION_ID
        and DETACHMENT_ID in army.detachment_selection.detachment_ids
    )


def _assigned_units(
    army: ArmyDefinition,
    *,
    enhancement_id: str,
) -> tuple[tuple[EnhancementAssignment, UnitInstance], ...]:
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError("Fade to Darkness requires ArmyDefinition.")
    assignments: list[tuple[EnhancementAssignment, UnitInstance]] = []
    for assignment in army.enhancement_assignments:
        if assignment.enhancement_id != enhancement_id:
            continue
        assignments.append((assignment, _unit_for_assignment(army, assignment=assignment)))
    return tuple(sorted(assignments, key=lambda item: item[1].unit_instance_id))


def _assigned_fade_unit_id_matches(army: ArmyDefinition, *, unit_instance_id: str) -> bool:
    return any(
        unit.unit_instance_id == unit_instance_id
        for _assignment, unit in _assigned_units(army, enhancement_id=ENHANCEMENT_ID)
    )


def _unit_for_assignment(
    army: ArmyDefinition,
    *,
    assignment: EnhancementAssignment,
) -> UnitInstance:
    expected_unit_instance_id = f"{army.army_id}:{assignment.target_unit_selection_id}"
    for unit in army.units:
        if unit.unit_instance_id == expected_unit_instance_id:
            return unit
    raise GameLifecycleError("Fade to Darkness assignment target unit was not mustered.")


def _leaping_shadows_scouts_descriptor() -> DatasheetAbilityDescriptor:
    return DatasheetAbilityDescriptor(
        ability_id=LEAPING_SHADOWS_ABILITY_ID,
        name=f"Scouts {LEAPING_SHADOWS_SCOUTS_DISTANCE}",
        source_id=LEAPING_SHADOWS_SOURCE_RULE_ID,
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description="Leaping Shadows grants Scouts 9.",
        timing_tags=("before_battle", "scouts"),
        parameter_tokens=(LEAPING_SHADOWS_SCOUTS_DISTANCE,),
    )


def _unit_can_enter_strategic_reserves(
    state: object,
    *,
    unit_instance_id: str,
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Fade to Darkness requires GameState.")
    if state.battlefield_state is None:
        raise GameLifecycleError("Fade to Darkness requires battlefield_state.")
    if state.reserve_state_for_unit(unit_instance_id) is not None:
        return False
    try:
        state.battlefield_state.unit_placement_by_id(unit_instance_id)
    except PlacementError:
        return False
    return not unit_within_enemy_engagement_range(state=state, unit_instance_id=unit_instance_id)


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Leaping Shadows keyword lookup requires UnitInstance.")
    requested_keyword = _canonical_keyword(keyword)
    return requested_keyword in {_canonical_keyword(stored) for stored in unit.keywords}


def _destroyed_enemy_unit_ids_for_fade_unit(
    context: TurnEndRequestContext | TurnEndResultContext,
    *,
    player_id: str,
    unit_instance_id: str,
) -> tuple[str, ...]:
    phase = (
        context.completed_phase
        if type(context) is TurnEndRequestContext
        else context.state.current_battle_phase
    )
    if phase is None:
        raise GameLifecycleError("Fade to Darkness requires a current phase.")
    destroyed_unit_ids: set[str] = set()
    for record in context.decisions.event_log.records:
        if record.event_type != ELIGIBLE_EVENT:
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        if payload.get("game_id") != context.state.game_id:
            continue
        if payload.get("battle_round") != context.state.battle_round:
            continue
        if payload.get("active_player_id") != context.state.active_player_id:
            continue
        if payload.get("phase") != phase.value:
            continue
        if payload.get("player_id") != player_id:
            continue
        if payload.get("target_unit_instance_id") != unit_instance_id:
            continue
        destroyed_unit_id = payload.get("destroyed_enemy_unit_instance_id")
        if type(destroyed_unit_id) is str:
            destroyed_unit_ids.add(destroyed_unit_id)
    return tuple(sorted(destroyed_unit_ids))


def _decision_recorded_this_phase(
    context: TurnEndRequestContext,
    *,
    unit_instance_id: str,
) -> bool:
    active_player_id = _active_player_id(context.state)
    for record in context.decisions.event_log.records:
        if record.event_type not in {USED_EVENT, DECLINED_EVENT}:
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        if payload.get("game_id") != context.state.game_id:
            continue
        if payload.get("battle_round") != context.state.battle_round:
            continue
        if payload.get("active_player_id") != active_player_id:
            continue
        if payload.get("phase") != context.completed_phase.value:
            continue
        if payload.get("target_unit_instance_id") == unit_instance_id:
            return True
    return False


def _eligible_event_recorded_for_destroyed_unit(
    context: UnitDestroyedContext,
    *,
    unit_instance_id: str,
    destroyed_unit_instance_id: str,
) -> bool:
    for record in context.decisions.event_log.records:
        if record.event_type != ELIGIBLE_EVENT:
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        if payload.get("game_id") != context.state.game_id:
            continue
        if payload.get("battle_round") != context.state.battle_round:
            continue
        if payload.get("active_player_id") != context.state.active_player_id:
            continue
        if payload.get("phase") != context.completed_phase.value:
            continue
        if payload.get("target_unit_instance_id") != unit_instance_id:
            continue
        if payload.get("destroyed_enemy_unit_instance_id") == destroyed_unit_instance_id:
            return True
    return False


def _validate_result_payload_matches_request(
    *,
    request_payload: dict[str, JsonValue],
    result_payload: dict[str, JsonValue],
) -> None:
    for key in ("source_rule_id", "hook_id", "enhancement_id", "target_unit_instance_id"):
        if request_payload.get(key) != result_payload.get(key):
            raise GameLifecycleError("Fade to Darkness result payload drift.")
    if result_payload.get("submission_kind") != SUBMISSION_KIND:
        raise GameLifecycleError("Fade to Darkness submission kind drift.")


def _fade_to_darkness_event_payload(
    *,
    context: TurnEndResultContext,
    player_id: str,
    unit_instance_id: str,
    reserve_state_payload: JsonValue,
    use_ability: bool,
) -> dict[str, JsonValue]:
    return {
        "game_id": context.state.game_id,
        "battle_round": context.state.battle_round,
        "active_player_id": _active_player_id(context.state),
        "phase": context.state.current_battle_phase.value
        if context.state.current_battle_phase is not None
        else None,
        "player_id": player_id,
        "source_rule_id": SOURCE_RULE_ID,
        "hook_id": TURN_END_HOOK_ID,
        "enhancement_id": ENHANCEMENT_ID,
        "target_unit_instance_id": unit_instance_id,
        "destroyed_enemy_unit_instance_ids": list(
            _destroyed_enemy_unit_ids_for_fade_unit(
                context,
                player_id=player_id,
                unit_instance_id=unit_instance_id,
            )
        ),
        "request_id": context.request.request_id,
        "result_id": context.result.result_id,
        "selected_option_id": context.result.selected_option_id,
        "use_ability": use_ability,
        "reserve_state": reserve_state_payload,
    }


def _army_for_player(armies: tuple[ArmyDefinition, ...], *, player_id: str) -> ArmyDefinition:
    requested_player_id = _validate_identifier("player_id", player_id)
    for army in armies:
        if army.player_id == requested_player_id:
            if not (
                army.detachment_selection.faction_id == CHAOS_DAEMONS_FACTION_ID
                and DETACHMENT_ID in army.detachment_selection.detachment_ids
            ):
                raise GameLifecycleError("Fade to Darkness requires Shadow Legion.")
            return army
    raise GameLifecycleError("Fade to Darkness player army is unknown.")


def _active_player_id(state: object) -> str:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Fade to Darkness requires GameState.")
    if state.active_player_id is None:
        raise GameLifecycleError("Fade to Darkness requires an active player.")
    return state.active_player_id


def _payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Fade to Darkness payload must be an object.")
    return payload


def _payload_string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"Fade to Darkness payload missing string {key}.")
    return _validate_identifier(key, value)


def _payload_bool(payload: dict[str, JsonValue], key: str) -> bool:
    value = payload.get(key)
    if type(value) is not bool:
        raise GameLifecycleError(f"Fade to Darkness payload missing bool {key}.")
    return value


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Fade to Darkness {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Fade to Darkness {field_name} must not be empty.")
    return stripped


def _canonical_keyword(value: str) -> str:
    return _validate_identifier("keyword", value).upper().replace("_", " ").replace("-", " ")
