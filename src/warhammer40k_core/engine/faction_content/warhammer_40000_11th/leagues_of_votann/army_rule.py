from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.command_phase_start_hooks import (
    CommandPhaseStartContext,
    CommandPhaseStartHookBinding,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.faction_content.common import canonical_keyword as _canonical_keyword
from warhammer40k_core.engine.faction_resources import FactionResourceStatus
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlStatus,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierBinding,
    HitRollModifierContext,
    WoundRollModifierBinding,
    WoundRollModifierContext,
)
from warhammer40k_core.engine.unit_factory import UnitInstance

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

CONTRIBUTION_ID = "warhammer_40000_11th:leagues_of_votann:army_rule:prioritised_efficiency"
HOOK_ID = "warhammer_40000_11th:leagues_of_votann:army_rule:prioritised_efficiency"
SOURCE_RULE_ID = "phase17f:phase17e:leagues-of-votann:army-rule"
COMMAND_PHASE_START_HOOK_ID = f"{HOOK_ID}:command-phase-start"
PRIORITISED_EFFICIENCY_HIT_MODIFIER_ID = f"{HOOK_ID}:hit-roll"
PRIORITISED_EFFICIENCY_WOUND_MODIFIER_ID = f"{HOOK_ID}:wound-roll"
LEAGUES_OF_VOTANN_FACTION_ID = "leagues-of-votann"
LEAGUES_OF_VOTANN_FACTION_KEYWORD = "LEAGUES OF VOTANN"
YIELD_POINT_RESOURCE_KIND = "leagues_of_votann_yield_points"
FORTIFY_TAKEOVER_YIELD_POINT_THRESHOLD = 7


class PrioritisedEfficiencyMode(StrEnum):
    HOSTILE_ACQUISITION = "hostile_acquisition"
    FORTIFY_TAKEOVER = "fortify_takeover"


@dataclass(frozen=True, slots=True)
class PrioritisedEfficiencyObjectiveSummary:
    objective_control_record_id: str
    controlled_objective_ids: tuple[str, ...]
    own_deployment_controlled_objective_ids: tuple[str, ...]
    outside_own_deployment_controlled_objective_ids: tuple[str, ...]
    opponent_max_controlled_objective_count: int
    yield_points: int


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        command_phase_start_hook_bindings=(
            CommandPhaseStartHookBinding(
                hook_id=COMMAND_PHASE_START_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=resolve_command_phase_start,
            ),
        ),
        hit_roll_modifier_bindings=(
            HitRollModifierBinding(
                modifier_id=PRIORITISED_EFFICIENCY_HIT_MODIFIER_ID,
                source_id=SOURCE_RULE_ID,
                handler=prioritised_efficiency_hit_roll_modifier,
            ),
        ),
        wound_roll_modifier_bindings=(
            WoundRollModifierBinding(
                modifier_id=PRIORITISED_EFFICIENCY_WOUND_MODIFIER_ID,
                source_id=SOURCE_RULE_ID,
                handler=prioritised_efficiency_wound_roll_modifier,
            ),
        ),
    )


def resolve_command_phase_start(context: CommandPhaseStartContext) -> None:
    if type(context) is not CommandPhaseStartContext:
        raise GameLifecycleError("Prioritised Efficiency requires command-phase context.")
    army = _leagues_of_votann_army_for_player(
        context.state,
        player_id=context.active_player_id,
    )
    if army is None:
        return

    mode_before = prioritised_efficiency_mode_for_player(
        context.state,
        player_id=army.player_id,
    )
    summary = prioritised_efficiency_objective_summary(
        context.state,
        player_id=army.player_id,
    )
    faction_resource_result: JsonValue = None
    if summary.yield_points > 0:
        gain = context.state.gain_faction_resource(
            player_id=army.player_id,
            resource_kind=YIELD_POINT_RESOURCE_KIND,
            amount=summary.yield_points,
            source_id=(
                f"{SOURCE_RULE_ID}:command-phase-start:"
                f"round-{context.state.battle_round}:player-{army.player_id}"
            ),
        )
        if gain.status is not FactionResourceStatus.APPLIED:
            raise GameLifecycleError("Prioritised Efficiency Yield Point gain was not applied.")
        faction_resource_result = validate_json_value(gain.to_payload())
    mode_after = prioritised_efficiency_mode_for_player(
        context.state,
        player_id=army.player_id,
    )
    context.decisions.event_log.append(
        "leagues_of_votann_prioritised_efficiency_resolved",
        {
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "phase": BattlePhase.COMMAND.value,
            "player_id": army.player_id,
            "source_rule_id": SOURCE_RULE_ID,
            "hook_id": COMMAND_PHASE_START_HOOK_ID,
            "objective_control_record_id": summary.objective_control_record_id,
            "controlled_objective_ids": list(summary.controlled_objective_ids),
            "own_deployment_controlled_objective_ids": list(
                summary.own_deployment_controlled_objective_ids
            ),
            "outside_own_deployment_controlled_objective_ids": list(
                summary.outside_own_deployment_controlled_objective_ids
            ),
            "opponent_max_controlled_objective_count": (
                summary.opponent_max_controlled_objective_count
            ),
            "yield_points_gained": summary.yield_points,
            "yield_points_total": yield_points_available(context.state, player_id=army.player_id),
            "mode_before": mode_before.value,
            "mode_after": mode_after.value,
            "faction_resource_result": faction_resource_result,
        },
    )


def yield_points_available(
    state: GameState,
    *,
    player_id: str,
) -> int:
    _validate_game_state(state)
    return state.faction_resource_total(
        player_id=_validate_identifier("player_id", player_id),
        resource_kind=YIELD_POINT_RESOURCE_KIND,
    )


def prioritised_efficiency_mode_for_player(
    state: GameState,
    *,
    player_id: str,
) -> PrioritisedEfficiencyMode:
    if _leagues_of_votann_army_for_player(state, player_id=player_id) is None:
        raise GameLifecycleError(
            "Prioritised Efficiency mode requires a Leagues of Votann detachment."
        )
    if yield_points_available(state, player_id=player_id) >= FORTIFY_TAKEOVER_YIELD_POINT_THRESHOLD:
        return PrioritisedEfficiencyMode.FORTIFY_TAKEOVER
    return PrioritisedEfficiencyMode.HOSTILE_ACQUISITION


def prioritised_efficiency_objective_summary(
    state: GameState,
    *,
    player_id: str,
) -> PrioritisedEfficiencyObjectiveSummary:
    _validate_game_state(state)
    requested_player_id = _validate_identifier("player_id", player_id)
    objective_record = _objective_control_record(state, phase=BattlePhase.COMMAND)
    controlled_objective_ids = _controlled_objective_ids(
        objective_record,
        player_id=requested_player_id,
    )
    own_deployment_objective_ids = set(
        _own_deployment_objective_ids(state, player_id=requested_player_id)
    )
    own_deployment_controlled_objective_ids = tuple(
        objective_id
        for objective_id in controlled_objective_ids
        if objective_id in own_deployment_objective_ids
    )
    outside_own_deployment_controlled_objective_ids = tuple(
        objective_id
        for objective_id in controlled_objective_ids
        if objective_id not in own_deployment_objective_ids
    )
    opponent_max_controlled_objective_count = _opponent_max_controlled_objective_count(
        state=state,
        objective_record=objective_record,
        player_id=requested_player_id,
    )
    yield_points = _yield_points_from_objectives(
        battle_round=state.battle_round,
        own_deployment_controlled_objective_ids=own_deployment_controlled_objective_ids,
        outside_own_deployment_controlled_objective_ids=(
            outside_own_deployment_controlled_objective_ids
        ),
        controlled_objective_count=len(controlled_objective_ids),
        opponent_max_controlled_objective_count=opponent_max_controlled_objective_count,
    )
    return PrioritisedEfficiencyObjectiveSummary(
        objective_control_record_id=objective_record.record_id,
        controlled_objective_ids=controlled_objective_ids,
        own_deployment_controlled_objective_ids=own_deployment_controlled_objective_ids,
        outside_own_deployment_controlled_objective_ids=(
            outside_own_deployment_controlled_objective_ids
        ),
        opponent_max_controlled_objective_count=opponent_max_controlled_objective_count,
        yield_points=yield_points,
    )


def prioritised_efficiency_hit_roll_modifier(context: HitRollModifierContext) -> int:
    if type(context) is not HitRollModifierContext:
        raise GameLifecycleError("Prioritised Efficiency hit modifier requires context.")
    if context.source_phase not in {BattlePhase.SHOOTING, BattlePhase.FIGHT}:
        return 0
    owner_id, attacking_unit = _unit_owner_and_instance_by_id(
        context.state,
        unit_instance_id=context.attacking_unit_instance_id,
    )
    if owner_id is None or attacking_unit is None:
        raise GameLifecycleError("Prioritised Efficiency attacking unit is unknown.")
    army = _leagues_of_votann_army_for_player(context.state, player_id=owner_id)
    if army is None:
        return 0
    if not _unit_has_faction_keyword(attacking_unit, LEAGUES_OF_VOTANN_FACTION_KEYWORD):
        return 0
    mode = prioritised_efficiency_mode_for_player(context.state, player_id=owner_id)
    if mode is PrioritisedEfficiencyMode.HOSTILE_ACQUISITION:
        if _unit_within_any_objective_range(
            state=context.state,
            unit_instance_id=context.target_unit_instance_id,
            phase=context.source_phase,
        ):
            return 1
        return 0
    if _unit_within_controlled_objective_range(
        state=context.state,
        player_id=army.player_id,
        unit_instance_id=context.attacking_unit_instance_id,
        phase=context.source_phase,
    ):
        return 1
    return 0


def prioritised_efficiency_wound_roll_modifier(context: WoundRollModifierContext) -> int:
    if type(context) is not WoundRollModifierContext:
        raise GameLifecycleError("Prioritised Efficiency wound modifier requires context.")
    if context.source_phase not in {BattlePhase.SHOOTING, BattlePhase.FIGHT}:
        return 0
    owner_id, target_unit = _unit_owner_and_instance_by_id(
        context.state,
        unit_instance_id=context.target_unit_instance_id,
    )
    if owner_id is None or target_unit is None:
        raise GameLifecycleError("Prioritised Efficiency target unit is unknown.")
    army = _leagues_of_votann_army_for_player(context.state, player_id=owner_id)
    if army is None:
        return 0
    if not _unit_has_faction_keyword(target_unit, LEAGUES_OF_VOTANN_FACTION_KEYWORD):
        return 0
    if (
        prioritised_efficiency_mode_for_player(context.state, player_id=owner_id)
        is not PrioritisedEfficiencyMode.FORTIFY_TAKEOVER
    ):
        return 0
    if _unit_has_keyword(target_unit, "VEHICLE"):
        return 0
    if context.strength <= context.toughness:
        return 0
    return -1


def _yield_points_from_objectives(
    *,
    battle_round: int,
    own_deployment_controlled_objective_ids: tuple[str, ...],
    outside_own_deployment_controlled_objective_ids: tuple[str, ...],
    controlled_objective_count: int,
    opponent_max_controlled_objective_count: int,
) -> int:
    if type(battle_round) is not int:
        raise GameLifecycleError("Prioritised Efficiency battle_round must be an int.")
    if battle_round < 1:
        raise GameLifecycleError("Prioritised Efficiency requires an active battle round.")
    _validate_identifier_tuple(
        "own_deployment_controlled_objective_ids",
        own_deployment_controlled_objective_ids,
    )
    _validate_identifier_tuple(
        "outside_own_deployment_controlled_objective_ids",
        outside_own_deployment_controlled_objective_ids,
    )
    _validate_non_negative_int("controlled_objective_count", controlled_objective_count)
    _validate_non_negative_int(
        "opponent_max_controlled_objective_count",
        opponent_max_controlled_objective_count,
    )
    yield_points = 1 if own_deployment_controlled_objective_ids else 0
    if battle_round < 2:
        return yield_points
    outside_count = len(outside_own_deployment_controlled_objective_ids)
    if outside_count >= 1:
        yield_points += 1
    if outside_count >= 2:
        yield_points += 1
    if controlled_objective_count > opponent_max_controlled_objective_count:
        yield_points += 1
    return yield_points


def _unit_within_any_objective_range(
    *,
    state: GameState,
    unit_instance_id: str,
    phase: BattlePhase,
) -> bool:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    objective_record = _objective_control_record(state, phase=phase)
    return any(
        _objective_result_has_unit(result, unit_instance_id=requested_unit_id)
        for result in objective_record.results
    )


def _unit_within_controlled_objective_range(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
    phase: BattlePhase,
) -> bool:
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    objective_record = _objective_control_record(state, phase=phase)
    return any(
        result.status is ObjectiveControlStatus.CONTROLLED
        and result.controlled_by_player_id == requested_player_id
        and _objective_result_has_unit_for_player(
            result,
            player_id=requested_player_id,
            unit_instance_id=requested_unit_id,
        )
        for result in objective_record.results
    )


def _objective_control_record(
    state: GameState,
    *,
    phase: BattlePhase,
) -> ObjectiveControlRecord:
    _validate_game_state(state)
    if type(phase) is not BattlePhase:
        raise GameLifecycleError("Prioritised Efficiency objective lookup requires a phase.")
    objective_record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=phase,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
        )
    )
    _ensure_objective_control_supported(objective_record)
    return objective_record


def _ensure_objective_control_supported(objective_record: ObjectiveControlRecord) -> None:
    if type(objective_record) is not ObjectiveControlRecord:
        raise GameLifecycleError("Prioritised Efficiency requires objective control record.")
    for result in objective_record.results:
        if result.status is ObjectiveControlStatus.UNSUPPORTED:
            raise GameLifecycleError(
                "Prioritised Efficiency cannot use unsupported objective control."
            )


def _controlled_objective_ids(
    objective_record: ObjectiveControlRecord,
    *,
    player_id: str,
) -> tuple[str, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    _ensure_objective_control_supported(objective_record)
    return tuple(
        result.objective_id
        for result in objective_record.results
        if result.status is ObjectiveControlStatus.CONTROLLED
        and result.controlled_by_player_id == requested_player_id
    )


def _opponent_max_controlled_objective_count(
    *,
    state: GameState,
    objective_record: ObjectiveControlRecord,
    player_id: str,
) -> int:
    _validate_game_state(state)
    requested_player_id = _validate_identifier("player_id", player_id)
    opponent_counts = tuple(
        len(_controlled_objective_ids(objective_record, player_id=opponent_id))
        for opponent_id in state.player_ids
        if opponent_id != requested_player_id
    )
    return max(opponent_counts) if opponent_counts else 0


def _objective_result_has_unit(
    result: ObjectiveControlResult,
    *,
    unit_instance_id: str,
) -> bool:
    if type(result) is not ObjectiveControlResult:
        raise GameLifecycleError("Prioritised Efficiency requires objective result.")
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    return any(
        contribution.unit_instance_id == requested_unit_id for contribution in result.contributors
    )


def _objective_result_has_unit_for_player(
    result: ObjectiveControlResult,
    *,
    player_id: str,
    unit_instance_id: str,
) -> bool:
    if type(result) is not ObjectiveControlResult:
        raise GameLifecycleError("Prioritised Efficiency requires objective result.")
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    return any(
        contribution.player_id == requested_player_id
        and contribution.unit_instance_id == requested_unit_id
        for contribution in result.contributors
    )


def _own_deployment_objective_ids(
    state: GameState,
    *,
    player_id: str,
) -> tuple[str, ...]:
    _validate_game_state(state)
    if state.mission_setup is None:
        raise GameLifecycleError("Prioritised Efficiency objective lookup requires MissionSetup.")
    requested_player_id = _validate_identifier("player_id", player_id)
    own_zones = tuple(
        zone
        for zone in state.mission_setup.deployment_zones
        if zone.player_id == requested_player_id
    )
    if not own_zones:
        raise GameLifecycleError("Prioritised Efficiency requires the player's deployment zone.")
    return tuple(
        sorted(
            marker.objective_marker_id
            for marker in state.mission_setup.objective_markers
            if any(zone.contains_point(marker.x_inches, marker.y_inches) for zone in own_zones)
        )
    )


def _leagues_of_votann_army_for_player(
    state: GameState,
    *,
    player_id: str,
) -> ArmyDefinition | None:
    _validate_game_state(state)
    requested_player_id = _validate_identifier("player_id", player_id)
    army = state.army_definition_for_player(requested_player_id)
    if army is None:
        return None
    if army.detachment_selection.faction_id == LEAGUES_OF_VOTANN_FACTION_ID:
        return army
    return None


def _unit_owner_and_instance_by_id(
    state: GameState,
    *,
    unit_instance_id: str,
) -> tuple[str | None, UnitInstance | None]:
    _validate_game_state(state)
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return army.player_id, unit
    return None, None


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Prioritised Efficiency keyword lookup requires UnitInstance.")
    canonical = _canonical_keyword(keyword)
    return canonical in {_canonical_keyword(stored) for stored in unit.keywords}


def _unit_has_faction_keyword(unit: UnitInstance, keyword: str) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Prioritised Efficiency keyword lookup requires UnitInstance.")
    canonical = _canonical_keyword(keyword)
    return canonical in {_canonical_keyword(stored) for stored in unit.faction_keywords}


def _validate_game_state(state: object) -> None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Prioritised Efficiency requires GameState.")


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_identifier_tuple(
    field_name: str,
    value: object,
) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"Prioritised Efficiency {field_name} must be a tuple.")
    return tuple(_validate_identifier(field_name, item) for item in cast(tuple[object, ...], value))


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"Prioritised Efficiency {field_name} must be an int.")
    if value < 0:
        raise GameLifecycleError(f"Prioritised Efficiency {field_name} must be non-negative.")
    return value
