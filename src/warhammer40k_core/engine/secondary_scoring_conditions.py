from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from warhammer40k_core.core.missions import ObjectiveMarkerRole
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlStatus,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_state import StartingStrengthRecord

if TYPE_CHECKING:
    from warhammer40k_core.engine.scoring import (
        SecondaryDestroyedModelState,
        SecondaryObjectiveCleanseState,
        SecondaryTerrainPlunderState,
        SecondaryUnitDestructionState,
    )
    from warhammer40k_core.engine.secondary_scoring_occupancy import SecondaryBattlefieldOccupancy

_validate_identifier = IdentifierValidator(GameLifecycleError)

GENERIC_SECONDARY_SCORING_CONDITIONS = frozenset(
    {
        "fixed_secondary_condition",
        "tactical_secondary_condition",
    }
)

SUPPORTED_SECONDARY_SCORING_RULE_CONDITIONS = frozenset(
    {
        "each_enemy_model_w10_or_more_destroyed_this_turn",
        "control_home_objective",
        "no_enemy_units_within_own_deployment_zone",
        "each_enemy_unit_starting_strength_13_or_more_destroyed_this_turn",
        "each_enemy_unit_destroyed_this_turn",
        "each_enemy_unit_started_turn_in_range_of_objective_destroyed",
        "one_or_more_objectives_cleansed_this_turn",
        "two_or_more_objectives_cleansed_this_turn",
        "one_or_more_terrain_areas_plundered_this_turn",
        "control_two_or_more_no_mans_land_objectives_excluding_home",
        "control_tempting_target_objective",
        "each_enemy_character_model_destroyed_this_turn",
        "each_enemy_character_model_w4_or_more_destroyed_this_turn",
        "one_or_more_enemy_character_models_destroyed_this_turn",
        "all_enemy_character_models_destroyed_during_battle",
        "beacon_unit_on_battlefield_outside_own_deployment_zone",
        "beacon_unit_on_battlefield_outside_own_territory",
        "each_friendly_non_aircraft_non_battleshocked_unit_wholly_within_opponent_deployment_zone",
        "each_objective_guarded_by_your_army",
        "friendly_non_aircraft_non_battleshocked_unit_within_3_of_center_and_no_enemy_within_3",
        "friendly_non_aircraft_non_battleshocked_unit_within_3_of_center_and_no_enemy_within_6",
        "more_friendly_than_enemy_units_wholly_within_no_mans_land",
        "presence_in_three_table_quarters",
        "presence_in_four_table_quarters",
        "control_opponent_home_objective_or_each_expansion_objective",
        "one_or_more_friendly_non_aircraft_non_battleshocked_units_within_6_of_battlefield_edge_not_within_own_territory",
        "two_or_more_friendly_non_aircraft_non_battleshocked_units_within_6_of_opposite_battlefield_edges_with_one_not_within_own_territory",
    }
)

SUPPORTED_SECONDARY_SCORING_TIMINGS = frozenset(
    {
        "mission_condition_met",
        "turn_end",
        "your_turn_end",
        "opponent_turn_end",
        "opponent_turn_end_or_round_five_turn_end",
        "either_player_turn_end",
        "while_active",
    }
)

_OCCUPANCY_REQUIRED_SECONDARY_CONDITIONS = frozenset(
    {
        "beacon_unit_on_battlefield_outside_own_deployment_zone",
        "beacon_unit_on_battlefield_outside_own_territory",
        "each_friendly_non_aircraft_non_battleshocked_unit_wholly_within_opponent_deployment_zone",
        "each_objective_guarded_by_your_army",
        "friendly_non_aircraft_non_battleshocked_unit_within_3_of_center_and_no_enemy_within_3",
        "friendly_non_aircraft_non_battleshocked_unit_within_3_of_center_and_no_enemy_within_6",
        "more_friendly_than_enemy_units_wholly_within_no_mans_land",
        "presence_in_three_table_quarters",
        "presence_in_four_table_quarters",
        "one_or_more_friendly_non_aircraft_non_battleshocked_units_within_6_of_battlefield_edge_not_within_own_territory",
        "two_or_more_friendly_non_aircraft_non_battleshocked_units_within_6_of_opposite_battlefield_edges_with_one_not_within_own_territory",
        "control_tempting_target_objective",
        "each_enemy_character_model_destroyed_this_turn",
        "each_enemy_character_model_w4_or_more_destroyed_this_turn",
        "one_or_more_enemy_character_models_destroyed_this_turn",
        "all_enemy_character_models_destroyed_during_battle",
    }
)


@dataclass(frozen=True, slots=True)
class SecondaryScoringConditionContext:
    record: ObjectiveControlRecord
    mission_setup: MissionSetup
    player_id: str
    unit_destruction_states: tuple[object, ...]
    objective_cleanse_states: tuple[object, ...]
    terrain_plunder_states: tuple[object, ...]
    enemy_unit_ids_in_player_deployment_zone: tuple[str, ...]
    starting_strength_records: tuple[StartingStrengthRecord, ...]
    occupancy: SecondaryBattlefieldOccupancy | None = None
    game_length_battle_rounds: int | None = None

    def __post_init__(self) -> None:
        if type(self.record) is not ObjectiveControlRecord:
            raise GameLifecycleError(
                "Secondary scoring condition context requires an ObjectiveControlRecord."
            )
        if type(self.mission_setup) is not MissionSetup:
            raise GameLifecycleError("Secondary scoring condition context requires MissionSetup.")
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("Secondary scoring player_id", self.player_id),
        )


def secondary_scoring_rule_applies_at_record(
    *,
    timing: str,
    record: ObjectiveControlRecord,
    player_id: str,
    game_length_battle_rounds: int,
) -> bool:
    requested_player = _validate_identifier("player_id", player_id)
    if timing not in SUPPORTED_SECONDARY_SCORING_TIMINGS:
        raise GameLifecycleError("Unsupported secondary scoring rule timing.")
    if timing == "mission_condition_met":
        return True
    if record.timing is not ObjectiveControlTiming.TURN_END:
        return False
    if timing in {"turn_end", "either_player_turn_end", "while_active"}:
        return True
    if timing == "your_turn_end":
        return record.active_player_id == requested_player
    if timing == "opponent_turn_end":
        return record.active_player_id != requested_player
    return record.active_player_id != requested_player or (
        record.battle_round == game_length_battle_rounds
    )


def evaluate_secondary_scoring_condition(
    *,
    condition: str,
    context: SecondaryScoringConditionContext,
) -> dict[str, JsonValue]:
    requested_condition = _validate_identifier("condition", condition)
    if requested_condition in GENERIC_SECONDARY_SCORING_CONDITIONS:
        raise GameLifecycleError(
            "Generic secondary scoring condition tokens cannot award victory points."
        )
    if requested_condition not in SUPPORTED_SECONDARY_SCORING_RULE_CONDITIONS:
        raise GameLifecycleError("Unsupported secondary scoring rule condition.")
    if (
        requested_condition in _OCCUPANCY_REQUIRED_SECONDARY_CONDITIONS
        and context.occupancy is None
    ):
        raise GameLifecycleError(
            f"Secondary scoring condition {requested_condition} requires battlefield occupancy."
        )
    record = context.record
    player_id = context.player_id
    controlled_objective_ids = _controlled_objective_ids(record, player_id=player_id)
    home_objective_ids = _home_objective_ids(context.mission_setup, player_id=player_id)
    central_objective_ids = _central_objective_ids(context.mission_setup)
    if requested_condition == "each_enemy_model_w10_or_more_destroyed_this_turn":
        matching = _enemy_destructions_this_turn(context)
        model_ids = tuple(
            model.model_instance_id
            for state in matching
            for model in state.destroyed_models
            if model.starting_wounds >= 10
        )
        return _score_count_evidence(
            score_count=len(model_ids),
            destroyed_unit_instance_ids=tuple(
                state.destroyed_unit_instance_id for state in matching
            ),
            destroyed_model_instance_ids=model_ids,
        )
    if requested_condition == "each_enemy_unit_starting_strength_13_or_more_destroyed_this_turn":
        matching = tuple(
            state
            for state in _enemy_destructions_this_turn(context)
            if _starting_strength_for_destroyed_unit(
                context,
                state.destroyed_unit_instance_id,
            )
            >= 13
        )
        return _score_count_evidence(
            score_count=len(matching),
            destroyed_unit_instance_ids=tuple(
                state.destroyed_unit_instance_id for state in matching
            ),
        )
    if requested_condition == "each_enemy_unit_destroyed_this_turn":
        matching = _enemy_destructions_this_turn(context)
        return _score_count_evidence(
            score_count=len(matching),
            destroyed_unit_instance_ids=tuple(
                state.destroyed_unit_instance_id for state in matching
            ),
        )
    if requested_condition == "control_home_objective":
        controlled_home_ids = tuple(
            objective_id
            for objective_id in controlled_objective_ids
            if objective_id in home_objective_ids
        )
        return _score_count_evidence(
            score_count=1 if controlled_home_ids else 0,
            controlled_objective_ids=controlled_home_ids,
            home_objective_ids=home_objective_ids,
        )
    if requested_condition == "no_enemy_units_within_own_deployment_zone":
        player_zones = tuple(
            zone
            for zone in context.mission_setup.deployment_zones
            if zone.player_id == context.player_id
        )
        if not player_zones:
            raise GameLifecycleError("Deployment-zone secondary scoring requires player zone.")
        return _score_count_evidence(
            score_count=0 if context.enemy_unit_ids_in_player_deployment_zone else 1,
            enemy_unit_instance_ids=context.enemy_unit_ids_in_player_deployment_zone,
        )
    if requested_condition == "each_enemy_unit_started_turn_in_range_of_objective_destroyed":
        matching = tuple(
            state
            for state in _enemy_destructions_this_turn(context)
            if state.started_turn_objective_marker_ids
        )
        objective_ids = tuple(
            sorted(
                {
                    objective_id
                    for state in matching
                    for objective_id in state.started_turn_objective_marker_ids
                }
            )
        )
        return _score_count_evidence(
            score_count=len(matching),
            destroyed_unit_instance_ids=tuple(
                state.destroyed_unit_instance_id for state in matching
            ),
            objective_marker_ids=objective_ids,
        )
    if requested_condition == "control_two_or_more_no_mans_land_objectives_excluding_home":
        no_mans_land_objective_ids = tuple(
            objective_id
            for objective_id in controlled_objective_ids
            if objective_id in central_objective_ids
        )
        return _score_count_evidence(
            score_count=1 if len(no_mans_land_objective_ids) >= 2 else 0,
            controlled_objective_ids=no_mans_land_objective_ids,
            home_objective_ids=home_objective_ids,
        )
    if requested_condition == "one_or_more_objectives_cleansed_this_turn":
        cleanses = _cleanses_this_turn(context)
        return _score_count_evidence(
            score_count=1 if cleanses else 0,
            objective_marker_ids=tuple(state.objective_marker_id for state in cleanses),
        )
    if requested_condition == "two_or_more_objectives_cleansed_this_turn":
        cleanses = _cleanses_this_turn(context)
        return _score_count_evidence(
            score_count=1 if len(cleanses) >= 2 else 0,
            objective_marker_ids=tuple(state.objective_marker_id for state in cleanses),
        )
    if requested_condition == "one_or_more_terrain_areas_plundered_this_turn":
        plunders = _plunders_this_turn(context)
        return _score_count_evidence(
            score_count=1 if plunders else 0,
            terrain_feature_ids=tuple(state.terrain_feature_id for state in plunders),
        )
    return _evaluate_promoted_condition(
        condition=requested_condition,
        context=context,
        controlled_objective_ids=controlled_objective_ids,
    )


def _evaluate_promoted_condition(
    *,
    condition: str,
    context: SecondaryScoringConditionContext,
    controlled_objective_ids: tuple[str, ...],
) -> dict[str, JsonValue]:
    occupancy = context.occupancy
    if condition == "control_tempting_target_objective":
        if occupancy is None or occupancy.tempting_objective_id is None:
            return _score_count_evidence(score_count=0)
        tempting_id = occupancy.tempting_objective_id
        return _score_count_evidence(
            score_count=1 if tempting_id in controlled_objective_ids else 0,
            controlled_objective_ids=(
                (tempting_id,) if tempting_id in controlled_objective_ids else ()
            ),
            objective_marker_ids=(tempting_id,),
        )
    if condition == "control_opponent_home_objective_or_each_expansion_objective":
        opponent_home_ids = _opponent_home_objective_ids(
            context.mission_setup,
            player_id=context.player_id,
        )
        expansion_ids = _expansion_objective_ids(context.mission_setup)
        controlled_opponent_home = tuple(
            objective_id
            for objective_id in controlled_objective_ids
            if objective_id in opponent_home_ids
        )
        controlled_expansion = tuple(
            objective_id
            for objective_id in controlled_objective_ids
            if objective_id in expansion_ids
        )
        all_expansion_controlled = bool(expansion_ids) and set(expansion_ids) <= set(
            controlled_expansion
        )
        score_count = 1 if controlled_opponent_home or all_expansion_controlled else 0
        return _score_count_evidence(
            score_count=score_count,
            controlled_objective_ids=tuple(
                sorted((*controlled_opponent_home, *controlled_expansion))
            ),
            home_objective_ids=opponent_home_ids,
        )
    destroyed_character_models = _destroyed_character_models_this_turn(context)
    if condition == "each_enemy_character_model_destroyed_this_turn":
        return _score_count_evidence(
            score_count=len(destroyed_character_models),
            destroyed_model_instance_ids=tuple(
                model.model_instance_id for model in destroyed_character_models
            ),
        )
    if condition == "each_enemy_character_model_w4_or_more_destroyed_this_turn":
        matching = tuple(
            model for model in destroyed_character_models if model.starting_wounds >= 4
        )
        return _score_count_evidence(
            score_count=len(matching),
            destroyed_model_instance_ids=tuple(model.model_instance_id for model in matching),
        )
    if condition == "all_enemy_character_models_destroyed_during_battle":
        roster = _require_occupancy(occupancy, condition=condition).enemy_character_models
        all_destroyed = bool(roster) and all(model.wounds_remaining == 0 for model in roster)
        return _score_count_evidence(
            score_count=1 if all_destroyed else 0,
            destroyed_model_instance_ids=tuple(model.model_instance_id for model in roster),
        )
    if condition == "one_or_more_enemy_character_models_destroyed_this_turn":
        character_roster = () if occupancy is None else occupancy.enemy_character_models
        all_destroyed = bool(character_roster) and all(
            model.wounds_remaining == 0 for model in character_roster
        )
        score_count = 1 if destroyed_character_models and not all_destroyed else 0
        return _score_count_evidence(
            score_count=score_count,
            destroyed_model_instance_ids=tuple(
                model.model_instance_id for model in destroyed_character_models
            ),
        )
    occupancy = _require_occupancy(occupancy, condition=condition)
    if condition == "beacon_unit_on_battlefield_outside_own_deployment_zone":
        _require_occupancy_region(
            occupancy.own_deployment_resolved,
            region_name="own deployment",
        )
        _require_occupancy_region(
            occupancy.own_territory_resolved,
            region_name="own territory",
        )
        five_vp = occupancy.beacon_on_battlefield and not occupancy.beacon_within_own_territory
        score_count = (
            1
            if occupancy.beacon_on_battlefield
            and not occupancy.beacon_within_own_deployment_zone
            and not five_vp
            else 0
        )
        return _score_count_evidence(score_count=score_count)
    if condition == "beacon_unit_on_battlefield_outside_own_territory":
        _require_occupancy_region(
            occupancy.own_territory_resolved,
            region_name="own territory",
        )
        score_count = (
            1
            if occupancy.beacon_on_battlefield and not occupancy.beacon_within_own_territory
            else 0
        )
        return _score_count_evidence(score_count=score_count)
    if condition == (
        "each_friendly_non_aircraft_non_battleshocked_unit_wholly_within_opponent_deployment_zone"
    ):
        _require_occupancy_region(
            occupancy.opponent_deployment_resolved,
            region_name="opponent deployment",
        )
        unit_ids = occupancy.friendly_wholly_within_opponent_deployment_zone_unit_ids
        return _score_count_evidence(score_count=len(unit_ids), enemy_unit_instance_ids=unit_ids)
    if condition == "each_objective_guarded_by_your_army":
        return _score_count_evidence(
            score_count=len(occupancy.guarded_objective_ids),
            objective_marker_ids=occupancy.guarded_objective_ids,
        )
    five_centre = bool(occupancy.friendly_within_three_of_center_unit_ids) and not bool(
        occupancy.enemy_within_six_of_center_unit_ids
    )
    three_centre = bool(occupancy.friendly_within_three_of_center_unit_ids) and not bool(
        occupancy.enemy_within_three_of_center_unit_ids
    )
    if condition == (
        "friendly_non_aircraft_non_battleshocked_unit_within_3_of_center_and_no_enemy_within_3"
    ):
        return _score_count_evidence(score_count=1 if three_centre and not five_centre else 0)
    if condition == (
        "friendly_non_aircraft_non_battleshocked_unit_within_3_of_center_and_no_enemy_within_6"
    ):
        return _score_count_evidence(score_count=1 if five_centre else 0)
    if condition == "more_friendly_than_enemy_units_wholly_within_no_mans_land":
        _require_occupancy_region(
            occupancy.no_mans_land_resolved,
            region_name="No Man's Land",
        )
        friendly_count = len(occupancy.friendly_wholly_within_no_mans_land_unit_ids)
        enemy_count = len(occupancy.enemy_wholly_within_no_mans_land_unit_ids)
        return _score_count_evidence(score_count=1 if friendly_count > enemy_count else 0)
    quarter_count = len(occupancy.presence_quarter_ids)
    if condition == "presence_in_three_table_quarters":
        return _score_count_evidence(score_count=1 if quarter_count == 3 else 0)
    if condition == "presence_in_four_table_quarters":
        return _score_count_evidence(score_count=1 if quarter_count == 4 else 0)
    five_outflank = len(occupancy.opposite_edge_unit_ids) >= 2
    if condition == (
        "one_or_more_friendly_non_aircraft_non_battleshocked_units_within_6_of_battlefield_edge_not_within_own_territory"
    ):
        _require_occupancy_region(
            occupancy.own_territory_resolved,
            region_name="own territory",
        )
        score_count = (
            1
            if occupancy.friendly_near_edge_outside_own_territory_unit_ids and not five_outflank
            else 0
        )
        return _score_count_evidence(score_count=score_count)
    if condition == (
        "two_or_more_friendly_non_aircraft_non_battleshocked_units_within_6_of_opposite_battlefield_edges_with_one_not_within_own_territory"
    ):
        _require_occupancy_region(
            occupancy.own_territory_resolved,
            region_name="own territory",
        )
        return _score_count_evidence(score_count=1 if five_outflank else 0)
    raise GameLifecycleError("Unsupported secondary scoring rule condition.")


def _require_occupancy(
    occupancy: SecondaryBattlefieldOccupancy | None,
    *,
    condition: str,
) -> SecondaryBattlefieldOccupancy:
    if occupancy is None:
        raise GameLifecycleError(
            f"Secondary scoring condition {condition} requires battlefield occupancy."
        )
    return occupancy


def _require_occupancy_region(resolved: bool, *, region_name: str) -> None:
    if type(resolved) is not bool:
        raise GameLifecycleError("Occupancy region resolution must be a bool.")
    if not resolved:
        raise GameLifecycleError(f"Secondary scoring requires a {region_name} battlefield region.")


def _destroyed_character_models_this_turn(
    context: SecondaryScoringConditionContext,
) -> tuple[SecondaryDestroyedModelState, ...]:
    occupancy = context.occupancy
    character_ids = {
        model.model_instance_id
        for model in (() if occupancy is None else occupancy.enemy_character_models)
    }
    if occupancy is None:
        raise GameLifecycleError(
            "Character secondary scoring requires battlefield occupancy with the enemy roster."
        )
    matching: list[SecondaryDestroyedModelState] = []
    for state in _enemy_destructions_this_turn(context):
        for model in state.destroyed_models:
            if model.model_instance_id in character_ids:
                matching.append(model)
    return tuple(matching)


def _enemy_destructions_this_turn(
    context: SecondaryScoringConditionContext,
) -> tuple[SecondaryUnitDestructionState, ...]:
    from warhammer40k_core.engine.scoring import SecondaryUnitDestructionState

    requested_player = context.player_id
    requested_round = context.record.battle_round
    requested_active = context.record.active_player_id
    matching: list[SecondaryUnitDestructionState] = []
    for value in context.unit_destruction_states:
        if type(value) is not SecondaryUnitDestructionState:
            raise GameLifecycleError(
                "Secondary scoring requires SecondaryUnitDestructionState values."
            )
        if (
            value.destroying_player_id == requested_player
            and value.destroyed_player_id != requested_player
            and value.active_player_id == requested_active
            and value.battle_round == requested_round
        ):
            matching.append(value)
    return tuple(matching)


def _cleanses_this_turn(
    context: SecondaryScoringConditionContext,
) -> tuple[SecondaryObjectiveCleanseState, ...]:
    from warhammer40k_core.engine.scoring import SecondaryObjectiveCleanseState

    matching: list[SecondaryObjectiveCleanseState] = []
    for value in context.objective_cleanse_states:
        if type(value) is not SecondaryObjectiveCleanseState:
            raise GameLifecycleError(
                "Secondary scoring requires SecondaryObjectiveCleanseState values."
            )
        if (
            value.player_id == context.player_id
            and value.active_player_id == context.record.active_player_id
            and value.battle_round == context.record.battle_round
        ):
            matching.append(value)
    return tuple(matching)


def _plunders_this_turn(
    context: SecondaryScoringConditionContext,
) -> tuple[SecondaryTerrainPlunderState, ...]:
    from warhammer40k_core.engine.scoring import SecondaryTerrainPlunderState

    matching: list[SecondaryTerrainPlunderState] = []
    for value in context.terrain_plunder_states:
        if type(value) is not SecondaryTerrainPlunderState:
            raise GameLifecycleError(
                "Secondary scoring requires SecondaryTerrainPlunderState values."
            )
        if (
            value.player_id == context.player_id
            and value.active_player_id == context.record.active_player_id
            and value.battle_round == context.record.battle_round
        ):
            matching.append(value)
    return tuple(matching)


def _starting_strength_for_destroyed_unit(
    context: SecondaryScoringConditionContext,
    unit_instance_id: str,
) -> int:
    requested_unit = _validate_identifier("unit_instance_id", unit_instance_id)
    matches = tuple(
        record
        for record in context.starting_strength_records
        if record.unit_instance_id == requested_unit
    )
    if len(matches) != 1:
        raise GameLifecycleError("Secondary scoring missing StartingStrengthRecord.")
    return matches[0].starting_model_count


def _controlled_objective_ids(
    record: ObjectiveControlRecord,
    *,
    player_id: str,
) -> tuple[str, ...]:
    requested_player = _validate_identifier("player_id", player_id)
    return tuple(
        result.objective_id
        for result in record.results
        if result.status is ObjectiveControlStatus.CONTROLLED
        and result.controlled_by_player_id == requested_player
    )


def _home_objective_ids(mission_setup: MissionSetup, *, player_id: str) -> tuple[str, ...]:
    role = (
        ObjectiveMarkerRole.ATTACKER_HOME
        if player_id == mission_setup.attacker_player_id
        else ObjectiveMarkerRole.DEFENDER_HOME
    )
    return tuple(
        sorted(
            marker.objective_marker_id
            for marker in mission_setup.objective_markers
            if marker.objective_role is role
        )
    )


def _opponent_home_objective_ids(mission_setup: MissionSetup, *, player_id: str) -> tuple[str, ...]:
    role = (
        ObjectiveMarkerRole.DEFENDER_HOME
        if player_id == mission_setup.attacker_player_id
        else ObjectiveMarkerRole.ATTACKER_HOME
    )
    return tuple(
        sorted(
            marker.objective_marker_id
            for marker in mission_setup.objective_markers
            if marker.objective_role is role
        )
    )


def _central_objective_ids(mission_setup: MissionSetup) -> tuple[str, ...]:
    return tuple(
        sorted(
            marker.objective_marker_id
            for marker in mission_setup.objective_markers
            if marker.objective_role is ObjectiveMarkerRole.CENTRAL
        )
    )


def _expansion_objective_ids(mission_setup: MissionSetup) -> tuple[str, ...]:
    return tuple(
        sorted(
            marker.objective_marker_id
            for marker in mission_setup.objective_markers
            if marker.objective_role is ObjectiveMarkerRole.EXPANSION
        )
    )


def _score_count_evidence(
    *,
    score_count: int,
    controlled_objective_ids: tuple[str, ...] = (),
    home_objective_ids: tuple[str, ...] = (),
    objective_marker_ids: tuple[str, ...] = (),
    terrain_feature_ids: tuple[str, ...] = (),
    destroyed_unit_instance_ids: tuple[str, ...] = (),
    destroyed_model_instance_ids: tuple[str, ...] = (),
    enemy_unit_instance_ids: tuple[str, ...] = (),
) -> dict[str, JsonValue]:
    if type(score_count) is not int or score_count < 0:
        raise GameLifecycleError("score_count must be a non-negative int.")
    return {
        "score_count": score_count,
        "controlled_objective_ids": list(controlled_objective_ids),
        "home_objective_ids": list(home_objective_ids),
        "objective_marker_ids": list(objective_marker_ids),
        "terrain_feature_ids": list(terrain_feature_ids),
        "destroyed_unit_instance_ids": list(destroyed_unit_instance_ids),
        "destroyed_model_instance_ids": list(destroyed_model_instance_ids),
        "enemy_unit_instance_ids": list(enemy_unit_instance_ids),
    }
