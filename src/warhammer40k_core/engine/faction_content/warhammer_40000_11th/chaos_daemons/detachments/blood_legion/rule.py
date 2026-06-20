from __future__ import annotations

from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.movement_end_surge_hooks import (
    MovementEndSurgeContext,
    MovementEndSurgeGrant,
    MovementEndSurgeHookBinding,
)
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.sticky_objective_control import (
    PhaseEndObjectiveControlContext,
    PhaseEndObjectiveControlHookBinding,
    StickyObjectiveControlState,
)
from warhammer40k_core.engine.unit_factory import UnitInstance

CONTRIBUTION_ID = "warhammer_40000_11th:chaos_daemons:detachment:blood_legion:rule:scaffold"
MURDERCALL_HOOK_ID = "warhammer_40000_11th:chaos_daemons:detachment:blood_legion:murdercall"
BLOOD_TAINTED_HOOK_ID = "warhammer_40000_11th:chaos_daemons:detachment:blood_legion:blood_tainted"
SOURCE_RULE_ID = "phase17f:phase17e:chaos-daemons:blood-legion:rule"
CHAOS_DAEMONS_FACTION_ID = "chaos-daemons"
BLOOD_LEGION_DETACHMENT_ID = "blood-legion"
LEGIONES_DAEMONICA = "LEGIONES DAEMONICA"
KHORNE = "KHORNE"
AIRCRAFT = "AIRCRAFT"
MURDERCALL_RANGE_INCHES = 8.0


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        movement_end_surge_hook_bindings=(
            MovementEndSurgeHookBinding(
                hook_id=MURDERCALL_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=murdercall_surge_grants,
            ),
        ),
        phase_end_objective_control_hook_bindings=(
            PhaseEndObjectiveControlHookBinding(
                hook_id=BLOOD_TAINTED_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=blood_tainted_sticky_states,
            ),
        ),
    )


def murdercall_surge_grants(
    context: MovementEndSurgeContext,
) -> tuple[MovementEndSurgeGrant, ...]:
    if type(context) is not MovementEndSurgeContext:
        raise GameLifecycleError("Murdercall requires a movement-end surge context.")
    army = _army_for_player(context.state, player_id=context.reacting_player_id)
    if not _army_has_blood_legion_detachment(army):
        return ()
    scenario = _battlefield_scenario(context.state)
    triggering_placement = scenario.battlefield_state.unit_placement_by_id(
        context.triggering_unit_instance_id
    )
    triggering_unit = scenario.unit_instance_for_placement(triggering_placement)
    if _unit_has_keyword(triggering_unit, AIRCRAFT):
        return ()
    grants: list[MovementEndSurgeGrant] = []
    for unit in army.units:
        if not _unit_is_legiones_daemonica_khorne(unit):
            continue
        if unit.unit_instance_id in context.state.battle_shocked_unit_ids:
            continue
        unit_placement = _placed_unit_for_army(
            scenario=scenario,
            player_id=context.reacting_player_id,
            unit_instance_id=unit.unit_instance_id,
        )
        if unit_placement is None:
            continue
        if not _unit_placements_within(
            scenario=scenario,
            first=unit_placement,
            second=triggering_placement,
            distance_inches=MURDERCALL_RANGE_INCHES,
        ):
            continue
        grants.append(
            MovementEndSurgeGrant(
                hook_id=MURDERCALL_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                unit_instance_id=unit.unit_instance_id,
                replay_payload={
                    "effect_kind": "murdercall",
                    "detachment_id": BLOOD_LEGION_DETACHMENT_ID,
                    "reacting_player_id": context.reacting_player_id,
                    "triggering_player_id": context.triggering_player_id,
                    "triggering_unit_instance_id": context.triggering_unit_instance_id,
                    "trigger_event_id": context.trigger_event_id,
                    "movement_phase_action": context.movement_phase_action,
                    "range_inches": MURDERCALL_RANGE_INCHES,
                    "required_faction_keyword": LEGIONES_DAEMONICA,
                    "required_keyword": KHORNE,
                },
            )
        )
    return tuple(sorted(grants, key=lambda grant: grant.unit_instance_id))


def blood_tainted_sticky_states(
    context: PhaseEndObjectiveControlContext,
) -> tuple[StickyObjectiveControlState, ...]:
    if type(context) is not PhaseEndObjectiveControlContext:
        raise GameLifecycleError("Blood Tainted requires a phase-end objective context.")
    states: list[StickyObjectiveControlState] = []
    for army in context.state.army_definitions:
        if not _army_has_blood_legion_detachment(army):
            continue
        states.extend(_blood_tainted_states_for_army(context=context, army=army))
    return tuple(sorted(states, key=lambda state: state.state_id))


def _blood_tainted_states_for_army(
    *,
    context: PhaseEndObjectiveControlContext,
    army: ArmyDefinition,
) -> tuple[StickyObjectiveControlState, ...]:
    objective_ids_by_unit = _phase_start_objective_ids_by_unit(context)
    if not objective_ids_by_unit:
        return ()
    objective_record = _current_objective_control_record(context)
    states: list[StickyObjectiveControlState] = []
    seen_state_keys: set[tuple[str, str, str]] = set()
    for event_id, payload in _unit_destruction_completion_events_for_phase(context):
        attacking_unit_id = _payload_string(payload, "attacking_unit_instance_id")
        if not _unit_id_is_in_army(army, unit_instance_id=attacking_unit_id):
            continue
        attacking_unit = _unit_in_army_by_id(army, unit_instance_id=attacking_unit_id)
        if not _unit_is_legiones_daemonica_khorne(attacking_unit):
            continue
        destroyed_unit_id = _payload_string(payload, "target_unit_instance_id")
        if _army_owner_for_unit(
            context.state.army_definitions, unit_instance_id=destroyed_unit_id
        ) == (army.player_id):
            continue
        for objective_id in objective_ids_by_unit.get(destroyed_unit_id, ()):
            state_key = (objective_id, attacking_unit_id, destroyed_unit_id)
            if state_key in seen_state_keys:
                continue
            result = objective_record.result_by_objective_id(objective_id)
            attacking_unit_loc = _unit_level_of_control(
                result=result,
                unit_instance_id=attacking_unit_id,
            )
            opponent_loc = _highest_opponent_level_of_control(
                result=result,
                player_id=army.player_id,
            )
            if attacking_unit_loc <= opponent_loc:
                continue
            seen_state_keys.add(state_key)
            states.append(
                StickyObjectiveControlState(
                    state_id=(
                        f"blood-tainted:{context.state.game_id}:"
                        f"round-{context.state.battle_round:02d}:"
                        f"{context.state.active_player_id}:{context.completed_phase.value}:"
                        f"{objective_id}:{attacking_unit_id}:{destroyed_unit_id}"
                    ),
                    game_id=context.state.game_id,
                    player_id=army.player_id,
                    objective_id=objective_id,
                    source_rule_id=SOURCE_RULE_ID,
                    source_event_id=event_id,
                    battle_round=context.state.battle_round,
                    phase=context.completed_phase.value,
                    active_player_id=_active_player_id(context),
                    originating_unit_instance_id=attacking_unit_id,
                    destroyed_unit_instance_id=destroyed_unit_id,
                    replay_payload={
                        "effect_kind": "blood_tainted",
                        "detachment_id": BLOOD_LEGION_DETACHMENT_ID,
                        "attacking_unit_instance_id": attacking_unit_id,
                        "destroyed_unit_instance_id": destroyed_unit_id,
                        "objective_id": objective_id,
                        "attacking_unit_level_of_control": attacking_unit_loc,
                        "opponent_level_of_control": opponent_loc,
                        "model_destroyed_event_id": event_id,
                        "unit_destruction_completion_event_id": event_id,
                        "required_faction_keyword": LEGIONES_DAEMONICA,
                        "required_keyword": KHORNE,
                    },
                )
            )
    return tuple(sorted(states, key=lambda state: state.state_id))


def _current_objective_control_record(
    context: PhaseEndObjectiveControlContext,
) -> ObjectiveControlRecord:
    return resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            context.state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=context.completed_phase,
            ruleset_descriptor=context.state.runtime_ruleset_descriptor(),
            runtime_modifier_registry=context.runtime_modifier_registry,
        )
    )


def _model_destroyed_events_for_phase(
    context: PhaseEndObjectiveControlContext,
) -> tuple[tuple[str, dict[str, JsonValue]], ...]:
    events: list[tuple[str, dict[str, JsonValue]]] = []
    for record in context.event_log.records:
        if record.event_type != "model_destroyed":
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
        events.append((record.event_id, payload))
    return tuple(events)


def _unit_destruction_completion_events_for_phase(
    context: PhaseEndObjectiveControlContext,
) -> tuple[tuple[str, dict[str, JsonValue]], ...]:
    phase_start_removed_model_ids = _phase_start_removed_model_ids(context)
    final_removed_model_ids = _removed_model_ids(context)
    destroyed_model_ids_by_unit: dict[str, set[str]] = {}
    completed_unit_ids: set[str] = set()
    completion_events: list[tuple[str, dict[str, JsonValue]]] = []
    for event_id, payload in _model_destroyed_events_for_phase(context):
        target_unit_id = _payload_string(payload, "target_unit_instance_id")
        target_unit = _unit_by_id(context.state.army_definitions, unit_instance_id=target_unit_id)
        target_model_ids = {model.model_instance_id for model in target_unit.own_models}
        if not target_model_ids <= final_removed_model_ids:
            continue
        if target_unit_id in completed_unit_ids:
            raise GameLifecycleError("Blood Tainted saw destruction after unit completion.")
        model_id = _payload_string(payload, "model_instance_id")
        if model_id not in target_model_ids:
            raise GameLifecycleError("Blood Tainted model-destroyed event target drift.")
        destroyed_model_ids = destroyed_model_ids_by_unit.setdefault(
            target_unit_id,
            set(target_model_ids & phase_start_removed_model_ids),
        )
        if model_id in destroyed_model_ids:
            raise GameLifecycleError("Blood Tainted saw duplicate destroyed-model attribution.")
        destroyed_model_ids.add(model_id)
        if target_model_ids <= destroyed_model_ids:
            completed_unit_ids.add(target_unit_id)
            completion_events.append((event_id, payload))
    return tuple(completion_events)


def _phase_start_objective_ids_by_unit(
    context: PhaseEndObjectiveControlContext,
) -> dict[str, tuple[str, ...]]:
    payload = _phase_start_snapshot_payload(context)
    if payload is None:
        return {}
    raw_mapping = payload.get("objective_ids_by_unit_instance_id")
    if not isinstance(raw_mapping, dict):
        raise GameLifecycleError("Blood Tainted phase-start snapshot is malformed.")
    mapping: dict[str, tuple[str, ...]] = {}
    for raw_unit_id, raw_objective_ids in raw_mapping.items():
        if type(raw_unit_id) is not str or not isinstance(raw_objective_ids, list):
            raise GameLifecycleError("Blood Tainted phase-start snapshot has invalid entries.")
        mapping[raw_unit_id] = tuple(
            _validate_identifier("objective_id", objective_id) for objective_id in raw_objective_ids
        )
    return mapping


def _phase_start_removed_model_ids(context: PhaseEndObjectiveControlContext) -> set[str]:
    payload = _phase_start_snapshot_payload(context)
    if payload is None:
        return set()
    raw_model_ids = payload.get("removed_model_ids")
    if not isinstance(raw_model_ids, list):
        raise GameLifecycleError("Blood Tainted phase-start snapshot missing removed models.")
    return {
        _validate_identifier("removed_model_id", raw_model_id) for raw_model_id in raw_model_ids
    }


def _phase_start_snapshot_payload(
    context: PhaseEndObjectiveControlContext,
) -> dict[str, JsonValue] | None:
    active_player_id = _active_player_id(context)
    snapshot_id = (
        f"objective-proximity:{context.state.game_id}:"
        f"round-{context.state.battle_round:02d}:turn:{active_player_id}:"
        f"phase:{context.completed_phase.value}:start"
    )
    for record in reversed(context.event_log.records):
        if record.event_type != "objective_marker_phase_start_proximity_snapshot":
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        if payload.get("snapshot_id") != snapshot_id:
            continue
        return payload
    return None


def _removed_model_ids(context: PhaseEndObjectiveControlContext) -> set[str]:
    battlefield_state = context.state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Blood Tainted requires battlefield_state.")
    return set(battlefield_state.removed_model_ids)


def _unit_placements_within(
    *,
    scenario: BattlefieldScenario,
    first: UnitPlacement,
    second: UnitPlacement,
    distance_inches: float,
) -> bool:
    for first_placement in first.model_placements:
        first_model = geometry_model_for_placement(
            model=scenario.model_instance_for_placement(first_placement),
            placement=first_placement,
        )
        for second_placement in second.model_placements:
            second_model = geometry_model_for_placement(
                model=scenario.model_instance_for_placement(second_placement),
                placement=second_placement,
            )
            if first_model.range_to(second_model) <= distance_inches:
                return True
    return False


def _unit_level_of_control(
    *,
    result: ObjectiveControlResult,
    unit_instance_id: str,
) -> int:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    return sum(
        contribution.effective_objective_control
        for contribution in result.contributors
        if contribution.unit_instance_id == requested_unit_id
    )


def _highest_opponent_level_of_control(
    *,
    result: ObjectiveControlResult,
    player_id: str,
) -> int:
    requested_player_id = _validate_identifier("player_id", player_id)
    opponent_scores = tuple(
        score.score for score in result.scores if score.player_id != requested_player_id
    )
    return 0 if not opponent_scores else max(opponent_scores)


def _battlefield_scenario(state: object) -> BattlefieldScenario:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Blood Legion requires GameState.")
    if state.battlefield_state is None:
        raise GameLifecycleError("Blood Legion requires battlefield_state.")
    return BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )


def _placed_unit_for_army(
    *,
    scenario: BattlefieldScenario,
    player_id: str,
    unit_instance_id: str,
) -> UnitPlacement | None:
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id != requested_player_id:
            continue
        for placement in placed_army.unit_placements:
            if placement.unit_instance_id == requested_unit_id:
                return placement
    return None


def _army_has_blood_legion_detachment(army: ArmyDefinition) -> bool:
    return (
        army.detachment_selection.faction_id == CHAOS_DAEMONS_FACTION_ID
        and BLOOD_LEGION_DETACHMENT_ID in army.detachment_selection.detachment_ids
    )


def _army_for_player(state: object, *, player_id: str) -> ArmyDefinition:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Blood Legion requires GameState.")
    requested_player_id = _validate_identifier("player_id", player_id)
    for army in state.army_definitions:
        if army.player_id == requested_player_id:
            return army
    raise GameLifecycleError("Blood Legion player army is unknown.")


def _unit_in_army_by_id(army: ArmyDefinition, *, unit_instance_id: str) -> UnitInstance:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for unit in army.units:
        if unit.unit_instance_id == requested_unit_id:
            return unit
    raise GameLifecycleError("Blood Legion unit is not in the selected player army.")


def _unit_id_is_in_army(army: ArmyDefinition, *, unit_instance_id: str) -> bool:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    return any(unit.unit_instance_id == requested_unit_id for unit in army.units)


def _unit_by_id(
    army_definitions: tuple[ArmyDefinition, ...] | list[ArmyDefinition],
    *,
    unit_instance_id: str,
) -> UnitInstance:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return unit
    raise GameLifecycleError("Blood Legion unit_instance_id was not found.")


def _army_owner_for_unit(
    army_definitions: tuple[ArmyDefinition, ...] | list[ArmyDefinition],
    *,
    unit_instance_id: str,
) -> str:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return army.player_id
    raise GameLifecycleError("Blood Legion unit owner was not found.")


def _unit_is_legiones_daemonica_khorne(unit: UnitInstance) -> bool:
    return _unit_has_faction_keyword(unit, LEGIONES_DAEMONICA) and _unit_has_keyword(
        unit,
        KHORNE,
    )


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    canonical = _canonical_keyword(keyword)
    return any(_canonical_keyword(stored) == canonical for stored in unit.keywords)


def _unit_has_faction_keyword(unit: UnitInstance, keyword: str) -> bool:
    canonical = _canonical_keyword(keyword)
    return any(_canonical_keyword(stored) == canonical for stored in unit.faction_keywords)


def _active_player_id(context: PhaseEndObjectiveControlContext) -> str:
    active_player_id = context.state.active_player_id
    if active_player_id is None:
        raise GameLifecycleError("Blood Tainted requires active_player_id.")
    return active_player_id


def _payload_string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"Blood Legion event payload missing string key: {key}.")
    return value


def _canonical_keyword(value: str) -> str:
    return value.strip().replace("_", " ").replace("-", " ").upper()


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped
