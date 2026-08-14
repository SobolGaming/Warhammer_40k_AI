from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from warhammer40k_core.core.battlefield_regions import BattlefieldRegion, BattlefieldRegionKind
from warhammer40k_core.core.missions import ObjectiveMarkerRole
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlStatus,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_destruction_evidence import (
    RulesUnitObjectiveProximityWitness,
)
from warhammer40k_core.engine.primary_scoring_conditions import (
    PrimaryUnitDestructionEvidence,
    cross_turn_destruction_comparison_evidence,
    opponent_home_control_evidence,
    primary_score_count_evidence,
)
from warhammer40k_core.engine.primary_scoring_spatial_evidence import (
    PrimaryScoringSpatialEvidence,
    objective_control_record_hash,
)

SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS = frozenset(
    {
        "control_central_and_expansion_objectives",
        "control_enemy_home_objective",
        "control_more_objectives_than_opponent_first_and_second_battle_round",
        "control_more_objectives_than_opponent_from_battle_round_two",
        "control_one_or_more_central_objectives",
        "control_one_or_more_central_objectives_end_of_battle",
        "control_one_or_more_new_non_home_objectives",
        "control_one_or_more_non_home_objectives_from_battle_round_two",
        "control_opponent_home_objective",
        "control_opponent_home_objective_end_of_battle",
        "control_three_or_more_objectives",
        "control_two_or_more_objectives_from_battle_round_two",
        "each_controlled_objective",
        "each_controlled_objective_from_battle_round_two",
        "each_controlled_objective_in_opponent_territory",
        "each_enemy_unit_destroyed_this_turn",
        "each_newly_controlled_non_home_objective_this_turn",
        "each_non_home_objective_controlled_battle_round_four_onwards",
        "each_non_home_objective_controlled_battle_rounds_two_and_three",
        "each_non_home_objective_controlled_battle_rounds_two_to_four",
        "each_non_home_objective_controlled_first_battle_round",
        "each_non_home_objective_controlled_from_battle_round_two",
        "each_non_home_objective_controlled_if_home_objective_controlled",
        "each_non_home_objective_controlled_round_five",
        "each_objective_controlled_from_battle_round_two",
        "four_or_more_friendly_units_wholly_within_four_different_table_quarters_not_within_six_of_center",
        "more_enemy_units_destroyed_than_friendly_previous_turn",
        "no_enemy_units_wholly_within_own_territory_end_of_battle",
        "one_or_more_enemy_units_destroyed_by_friendly_unit_on_objective_this_turn",
        "one_or_more_enemy_units_destroyed_this_turn",
        "one_or_more_enemy_units_started_turn_within_central_objective_range_destroyed_this_turn",
        "one_or_more_enemy_units_started_turn_within_objective_destroyed_this_turn",
        "one_or_more_enemy_units_started_turn_in_terrain_area_destroyed_this_turn",
        "three_or_more_friendly_units_wholly_within_three_different_table_quarters_not_within_six_of_center",
    }
)

PRIMARY_SCORING_TURN_START_OBJECTIVE_CONDITIONS = frozenset(
    {
        "control_one_or_more_new_non_home_objectives",
        "each_newly_controlled_non_home_objective_this_turn",
    }
)


@dataclass(frozen=True, slots=True)
class PrimaryScoringConditionContext:
    record: ObjectiveControlRecord
    mission_setup: MissionSetup
    turn_order: tuple[str, ...]
    player_id: str
    turn_start_controlled_objective_ids: tuple[str, ...] | None = None
    destruction_evidence: tuple[PrimaryUnitDestructionEvidence, ...] = ()
    spatial_evidence: PrimaryScoringSpatialEvidence | None = None
    end_of_battle: bool = False

    def __post_init__(self) -> None:
        if type(self.record) is not ObjectiveControlRecord:
            raise GameLifecycleError(
                "Primary scoring condition context requires an ObjectiveControlRecord."
            )
        if type(self.mission_setup) is not MissionSetup:
            raise GameLifecycleError("Primary scoring condition context requires MissionSetup.")
        ordered_players = _validate_identifier_tuple(
            "Primary scoring condition turn_order",
            self.turn_order,
            preserve_order=True,
        )
        if len(ordered_players) != 2:
            raise GameLifecycleError(
                "Primary scoring condition turn_order must contain exactly two players."
            )
        setup_players = {
            self.mission_setup.attacker_player_id,
            self.mission_setup.defender_player_id,
        }
        if set(ordered_players) != setup_players:
            raise GameLifecycleError(
                "Primary scoring condition turn_order must match MissionSetup players."
            )
        object.__setattr__(self, "turn_order", ordered_players)
        requested_player = _validate_identifier(
            "Primary scoring condition player_id",
            self.player_id,
        )
        if requested_player not in ordered_players:
            raise GameLifecycleError("Primary scoring condition player is missing from turn_order.")
        object.__setattr__(self, "player_id", requested_player)
        if self.record.active_player_id not in ordered_players:
            raise GameLifecycleError(
                "Primary scoring condition active player is missing from turn_order."
            )
        if type(self.end_of_battle) is not bool:
            raise GameLifecycleError("Primary scoring condition end_of_battle must be a bool.")
        if not self.end_of_battle and requested_player != self.record.active_player_id:
            raise GameLifecycleError(
                "Ordinary Primary scoring conditions must evaluate for the active player."
            )
        if self.turn_start_controlled_objective_ids is not None:
            object.__setattr__(
                self,
                "turn_start_controlled_objective_ids",
                _validate_identifier_tuple(
                    "Primary scoring turn-start controlled objective IDs",
                    self.turn_start_controlled_objective_ids,
                ),
            )
        object.__setattr__(
            self,
            "destruction_evidence",
            _validate_destruction_evidence(
                self.destruction_evidence,
                player_ids=ordered_players,
                current_battle_round=self.record.battle_round,
            ),
        )
        if self.spatial_evidence is not None:
            if type(self.spatial_evidence) is not PrimaryScoringSpatialEvidence:
                raise GameLifecycleError(
                    "Primary scoring condition spatial evidence must be typed evidence."
                )
            if self.spatial_evidence.player_id != requested_player:
                raise GameLifecycleError(
                    "Primary scoring condition spatial evidence belongs to another player."
                )
            if (
                self.spatial_evidence.game_id != self.record.game_id
                or self.spatial_evidence.battlefield_id != self.record.battlefield_id
                or self.spatial_evidence.battle_round != self.record.battle_round
                or self.spatial_evidence.active_player_id != self.record.active_player_id
                or self.spatial_evidence.phase != self.record.phase
                or self.spatial_evidence.timing is not self.record.timing
                or self.spatial_evidence.objective_control_record_id != self.record.record_id
                or self.spatial_evidence.objective_control_record_hash
                != objective_control_record_hash(self.record)
            ):
                raise GameLifecycleError(
                    "Primary scoring condition spatial evidence context drift."
                )
        _validate_objective_control_record(
            record=self.record,
            mission_setup=self.mission_setup,
            player_ids=ordered_players,
        )
        expected_objective_ids = {
            marker.objective_marker_id for marker in self.mission_setup.objective_markers
        }
        if (
            self.turn_start_controlled_objective_ids is not None
            and not set(self.turn_start_controlled_objective_ids) <= expected_objective_ids
        ):
            raise GameLifecycleError(
                "Primary scoring turn-start evidence references an unknown objective."
            )
        if any(
            not set(row.started_turn_objective_marker_ids) <= expected_objective_ids
            or (
                row.source_rules_unit_objective_proximity_witness is not None
                and not set(row.source_rules_unit_objective_proximity_witness.objective_marker_ids)
                <= expected_objective_ids
            )
            for row in self.destruction_evidence
        ):
            raise GameLifecycleError(
                "Primary scoring destruction evidence references an unknown objective."
            )


@dataclass(frozen=True, slots=True)
class _ObjectiveEvidence:
    controlled_ids: tuple[str, ...]
    opponent_controlled_ids: tuple[str, ...]
    home_ids: tuple[str, ...]
    non_home_ids: tuple[str, ...]
    central_ids: tuple[str, ...]
    expansion_ids: tuple[str, ...]


def evaluate_primary_scoring_condition(
    *,
    condition: str,
    context: PrimaryScoringConditionContext,
) -> dict[str, JsonValue]:
    condition_id = _validate_identifier("Primary scoring condition", condition)
    if condition_id not in SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS:
        raise GameLifecycleError(f"Unsupported primary scoring condition: {condition_id}.")
    if type(context) is not PrimaryScoringConditionContext:
        raise GameLifecycleError("Primary scoring condition evaluation requires a typed context.")
    objective = _objective_evidence(context)
    record = context.record

    if condition_id == "each_controlled_objective":
        return _objective_count_evidence(objective.controlled_ids)
    if condition_id in {
        "each_controlled_objective_from_battle_round_two",
        "each_objective_controlled_from_battle_round_two",
    }:
        return _objective_count_evidence(
            objective.controlled_ids if record.battle_round >= 2 else ()
        )
    if condition_id == "each_non_home_objective_controlled_from_battle_round_two":
        return _non_home_count_evidence(
            objective,
            objective.non_home_ids if record.battle_round >= 2 else (),
        )
    if condition_id == "control_one_or_more_non_home_objectives_from_battle_round_two":
        matching = objective.non_home_ids if record.battle_round >= 2 else ()
        return _non_home_binary_evidence(objective, matching)
    if condition_id == "control_one_or_more_central_objectives":
        controlled_central_ids = _intersection(
            objective.controlled_ids,
            objective.central_ids,
        )
        return _binary_objective_evidence(controlled_central_ids)
    if condition_id == "control_one_or_more_central_objectives_end_of_battle":
        controlled_central_ids = (
            _intersection(objective.controlled_ids, objective.central_ids)
            if context.end_of_battle
            else ()
        )
        return _binary_objective_evidence(controlled_central_ids)
    if condition_id == "each_non_home_objective_controlled_battle_rounds_two_to_four":
        matching = objective.non_home_ids if 2 <= record.battle_round <= 4 else ()
        return _non_home_count_evidence(objective, matching)
    if condition_id == "each_non_home_objective_controlled_round_five":
        matching = objective.non_home_ids if record.battle_round == 5 else ()
        return _non_home_count_evidence(objective, matching)
    if condition_id == "one_or_more_enemy_units_destroyed_this_turn":
        return _destruction_evidence(context, count_each=False)
    if condition_id == "each_enemy_unit_destroyed_this_turn":
        return _destruction_evidence(context, count_each=True)
    if condition_id == (
        "one_or_more_enemy_units_destroyed_by_friendly_unit_on_objective_this_turn"
    ):
        return _destroyed_by_friendly_unit_on_objective_evidence(context)
    if condition_id == (
        "one_or_more_enemy_units_started_turn_within_objective_destroyed_this_turn"
    ):
        return _started_turn_objective_destruction_evidence(
            context,
            allowed_objective_ids=None,
        )
    if condition_id == (
        "one_or_more_enemy_units_started_turn_within_central_objective_range_destroyed_this_turn"
    ):
        return _started_turn_objective_destruction_evidence(
            context,
            allowed_objective_ids=objective.central_ids,
        )
    if condition_id == "control_one_or_more_new_non_home_objectives":
        matching, turn_start_ids = _newly_controlled_non_home_ids(context, objective)
        return primary_score_count_evidence(
            score_count=1 if matching else 0,
            controlled_objective_ids=matching,
            home_objective_ids=objective.home_ids,
            turn_start_controlled_objective_ids=turn_start_ids,
        )
    if condition_id == "each_newly_controlled_non_home_objective_this_turn":
        matching, turn_start_ids = _newly_controlled_non_home_ids(context, objective)
        return primary_score_count_evidence(
            score_count=len(matching),
            controlled_objective_ids=matching,
            home_objective_ids=objective.home_ids,
            turn_start_controlled_objective_ids=turn_start_ids,
        )
    if condition_id == "more_enemy_units_destroyed_than_friendly_previous_turn":
        return cross_turn_destruction_comparison_evidence(
            turn_order=context.turn_order,
            battle_round=record.battle_round,
            active_player_id=record.active_player_id,
            scoring_player_id=context.player_id,
            destruction_evidence=context.destruction_evidence,
        )
    if condition_id in {"control_opponent_home_objective", "control_enemy_home_objective"}:
        return opponent_home_control_evidence(
            mission_setup=context.mission_setup,
            player_id=context.player_id,
            controlled_objective_ids=objective.controlled_ids,
        )
    if condition_id == "control_opponent_home_objective_end_of_battle":
        return opponent_home_control_evidence(
            mission_setup=context.mission_setup,
            player_id=context.player_id,
            controlled_objective_ids=(objective.controlled_ids if context.end_of_battle else ()),
        )
    if condition_id == "control_more_objectives_than_opponent_first_and_second_battle_round":
        return _control_more_evidence(
            objective if record.battle_round in {1, 2} else _empty_objective_evidence(objective)
        )
    if condition_id == "control_more_objectives_than_opponent_from_battle_round_two":
        return _control_more_evidence(
            objective if record.battle_round >= 2 else _empty_objective_evidence(objective)
        )
    if condition_id == "each_non_home_objective_controlled_if_home_objective_controlled":
        controlled_home_ids = _intersection(objective.controlled_ids, objective.home_ids)
        matching = objective.non_home_ids if controlled_home_ids else ()
        evidence = _non_home_count_evidence(objective, matching)
        evidence["controlled_home_objective_ids"] = list(controlled_home_ids)
        return evidence
    if condition_id == "control_central_and_expansion_objectives":
        controlled_central_ids = _intersection(
            objective.controlled_ids,
            objective.central_ids,
        )
        controlled_expansion_ids = _intersection(
            objective.controlled_ids,
            objective.expansion_ids,
        )
        evidence = primary_score_count_evidence(
            score_count=1 if controlled_central_ids and controlled_expansion_ids else 0,
            controlled_objective_ids=tuple(
                sorted((*controlled_central_ids, *controlled_expansion_ids))
            ),
        )
        evidence["controlled_central_objective_ids"] = list(controlled_central_ids)
        evidence["controlled_expansion_objective_ids"] = list(controlled_expansion_ids)
        return evidence
    if condition_id == "each_controlled_objective_in_opponent_territory":
        spatial = _required_spatial_evidence(context, condition=condition_id)
        expected_ids = _opponent_territory_objective_ids(context)
        if spatial.opponent_territory_objective_ids != expected_ids:
            raise GameLifecycleError(
                "Primary scoring spatial evidence opponent-territory objectives drifted "
                "from MissionSetup."
            )
        matching = _intersection(
            objective.controlled_ids,
            spatial.opponent_territory_objective_ids,
        )
        evidence = _objective_count_evidence(matching)
        evidence["opponent_territory_objective_ids"] = list(
            spatial.opponent_territory_objective_ids
        )
        evidence["opponent_player_id"] = _opponent_player_id(context)
        return evidence
    if condition_id == "control_three_or_more_objectives":
        return _threshold_objective_evidence(objective.controlled_ids, threshold=3)
    if condition_id == "control_two_or_more_objectives_from_battle_round_two":
        controlled_ids = objective.controlled_ids if record.battle_round >= 2 else ()
        return _threshold_objective_evidence(controlled_ids, threshold=2)
    if condition_id == "each_non_home_objective_controlled_first_battle_round":
        matching = objective.non_home_ids if record.battle_round == 1 else ()
        return _non_home_count_evidence(objective, matching)
    if condition_id == "each_non_home_objective_controlled_battle_rounds_two_and_three":
        matching = objective.non_home_ids if record.battle_round in {2, 3} else ()
        return _non_home_count_evidence(objective, matching)
    if condition_id == "each_non_home_objective_controlled_battle_round_four_onwards":
        matching = objective.non_home_ids if record.battle_round >= 4 else ()
        return _non_home_count_evidence(objective, matching)
    if condition_id == (
        "three_or_more_friendly_units_wholly_within_three_different_table_quarters_"
        "not_within_six_of_center"
    ):
        return _table_quarter_evidence(
            context,
            condition=condition_id,
            threshold=3,
        )
    if condition_id == (
        "four_or_more_friendly_units_wholly_within_four_different_table_quarters_"
        "not_within_six_of_center"
    ):
        return _table_quarter_evidence(
            context,
            condition=condition_id,
            threshold=4,
        )
    if condition_id == ("one_or_more_enemy_units_started_turn_in_terrain_area_destroyed_this_turn"):
        destruction_matches = tuple(
            row
            for row in _enemy_destructions_this_turn(context)
            if row.started_turn_terrain_feature_ids
        )
        terrain_ids = tuple(
            sorted(
                {
                    terrain_id
                    for row in destruction_matches
                    for terrain_id in row.started_turn_terrain_feature_ids
                }
            )
        )
        evidence = primary_score_count_evidence(
            score_count=1 if destruction_matches else 0,
            trapped_terrain_feature_ids=terrain_ids,
            destroyed_unit_instance_ids=tuple(
                sorted({row.destroyed_unit_instance_id for row in destruction_matches})
            ),
            destruction_ids=tuple(row.destruction_id for row in destruction_matches),
        )
        evidence["started_turn_terrain_feature_ids"] = list(terrain_ids)
        return evidence
    if condition_id == "no_enemy_units_wholly_within_own_territory_end_of_battle":
        spatial = _required_spatial_evidence(context, condition=condition_id)
        witnesses = spatial.enemy_units_wholly_within_own_territory if context.end_of_battle else ()
        score_count = 1 if context.end_of_battle and not witnesses else 0
        evidence = primary_score_count_evidence(score_count=score_count)
        evidence["enemy_unit_instance_ids"] = [
            witness.rules_unit_instance_id for witness in witnesses
        ]
        evidence["enemy_units_wholly_within_own_territory"] = cast(
            JsonValue,
            [witness.to_payload() for witness in witnesses],
        )
        evidence["own_territory_region_id"] = _territory_region_id(
            context,
            player_id=context.player_id,
        )
        return evidence
    raise GameLifecycleError(f"Unsupported primary scoring condition: {condition_id}.")


def _empty_objective_evidence(objective: _ObjectiveEvidence) -> _ObjectiveEvidence:
    return _ObjectiveEvidence(
        controlled_ids=(),
        opponent_controlled_ids=objective.opponent_controlled_ids,
        home_ids=objective.home_ids,
        non_home_ids=objective.non_home_ids,
        central_ids=objective.central_ids,
        expansion_ids=objective.expansion_ids,
    )


def _objective_evidence(context: PrimaryScoringConditionContext) -> _ObjectiveEvidence:
    controlled_ids = tuple(
        result.objective_id
        for result in context.record.results
        if result.status is ObjectiveControlStatus.CONTROLLED
        and result.controlled_by_player_id == context.player_id
    )
    opponent_player_id = _opponent_player_id(context)
    opponent_controlled_ids = tuple(
        result.objective_id
        for result in context.record.results
        if result.status is ObjectiveControlStatus.CONTROLLED
        and result.controlled_by_player_id == opponent_player_id
    )
    home_role = (
        ObjectiveMarkerRole.ATTACKER_HOME
        if context.player_id == context.mission_setup.attacker_player_id
        else ObjectiveMarkerRole.DEFENDER_HOME
    )
    home_ids = tuple(
        marker.objective_marker_id
        for marker in context.mission_setup.objective_markers
        if marker.objective_role is home_role
    )
    central_ids = tuple(
        marker.objective_marker_id
        for marker in context.mission_setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    expansion_ids = tuple(
        marker.objective_marker_id
        for marker in context.mission_setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.EXPANSION
    )
    return _ObjectiveEvidence(
        controlled_ids=controlled_ids,
        opponent_controlled_ids=opponent_controlled_ids,
        home_ids=home_ids,
        non_home_ids=tuple(
            objective_id for objective_id in controlled_ids if objective_id not in home_ids
        ),
        central_ids=central_ids,
        expansion_ids=expansion_ids,
    )


def _validate_objective_control_record(
    *,
    record: ObjectiveControlRecord,
    mission_setup: MissionSetup,
    player_ids: tuple[str, ...],
) -> None:
    expected_ids = tuple(marker.objective_marker_id for marker in mission_setup.objective_markers)
    actual_ids = tuple(result.objective_id for result in record.results)
    if actual_ids != expected_ids:
        raise GameLifecycleError(
            "Primary scoring ObjectiveControlRecord must contain exactly the MissionSetup "
            "objectives."
        )
    known_players = set(player_ids)
    for result in record.results:
        if result.status is ObjectiveControlStatus.UNSUPPORTED:
            raise GameLifecycleError(
                "Primary scoring cannot consume unsupported objective-control results."
            )
        if (
            result.controlled_by_player_id is not None
            and result.controlled_by_player_id not in known_players
        ):
            raise GameLifecycleError(
                "Primary scoring objective control references an unknown controlling player."
            )
        if any(score.player_id not in known_players for score in result.scores):
            raise GameLifecycleError(
                "Primary scoring objective control score references an unknown player."
            )
        if any(contribution.player_id not in known_players for contribution in result.contributors):
            raise GameLifecycleError(
                "Primary scoring objective contribution references an unknown player."
            )


def _validate_destruction_evidence(
    values: object,
    *,
    player_ids: tuple[str, ...],
    current_battle_round: int,
) -> tuple[PrimaryUnitDestructionEvidence, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("Primary scoring destruction evidence must be a tuple.")
    rows: list[PrimaryUnitDestructionEvidence] = []
    seen_ids: set[str] = set()
    known_players = set(player_ids)
    for value in cast(tuple[object, ...], values):
        if type(value) is not PrimaryUnitDestructionEvidence:
            raise GameLifecycleError(
                "Primary scoring destruction evidence must contain typed rows."
            )
        if value.destruction_id in seen_ids:
            raise GameLifecycleError(
                "Primary scoring destruction evidence must not duplicate occurrences."
            )
        if (
            value.active_player_id not in known_players
            or value.destroyed_player_id not in known_players
            or value.destroying_player_id not in {None, *known_players}
        ):
            raise GameLifecycleError(
                "Primary scoring destruction evidence references an unknown player."
            )
        if value.battle_round > current_battle_round:
            raise GameLifecycleError(
                "Primary scoring destruction evidence cannot come from a future battle round."
            )
        seen_ids.add(value.destruction_id)
        rows.append(value)
    return tuple(sorted(rows, key=lambda row: row.destruction_id))


def _objective_count_evidence(
    objective_ids: tuple[str, ...],
) -> dict[str, JsonValue]:
    return primary_score_count_evidence(
        score_count=len(objective_ids),
        controlled_objective_ids=objective_ids,
    )


def _binary_objective_evidence(
    objective_ids: tuple[str, ...],
) -> dict[str, JsonValue]:
    return primary_score_count_evidence(
        score_count=1 if objective_ids else 0,
        controlled_objective_ids=objective_ids,
    )


def _non_home_count_evidence(
    objective: _ObjectiveEvidence,
    matching: tuple[str, ...],
) -> dict[str, JsonValue]:
    return primary_score_count_evidence(
        score_count=len(matching),
        controlled_objective_ids=matching,
        home_objective_ids=objective.home_ids,
    )


def _non_home_binary_evidence(
    objective: _ObjectiveEvidence,
    matching: tuple[str, ...],
) -> dict[str, JsonValue]:
    return primary_score_count_evidence(
        score_count=1 if matching else 0,
        controlled_objective_ids=matching,
        home_objective_ids=objective.home_ids,
    )


def _threshold_objective_evidence(
    matching: tuple[str, ...],
    *,
    threshold: int,
) -> dict[str, JsonValue]:
    evidence = primary_score_count_evidence(
        score_count=1 if len(matching) >= threshold else 0,
        controlled_objective_ids=matching,
    )
    evidence["objective_count_threshold"] = threshold
    return evidence


def _control_more_evidence(
    objective: _ObjectiveEvidence,
) -> dict[str, JsonValue]:
    score_count = 1 if len(objective.controlled_ids) > len(objective.opponent_controlled_ids) else 0
    evidence = primary_score_count_evidence(
        score_count=score_count,
        controlled_objective_ids=objective.controlled_ids,
    )
    evidence["opponent_controlled_objective_ids"] = list(objective.opponent_controlled_ids)
    evidence["controlled_objective_count"] = len(objective.controlled_ids)
    evidence["opponent_controlled_objective_count"] = len(objective.opponent_controlled_ids)
    return evidence


def _newly_controlled_non_home_ids(
    context: PrimaryScoringConditionContext,
    objective: _ObjectiveEvidence,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    turn_start_ids = context.turn_start_controlled_objective_ids
    if turn_start_ids is None:
        raise GameLifecycleError(
            "Primary newly-controlled scoring requires a turn-start objective snapshot."
        )
    return (
        tuple(
            objective_id
            for objective_id in objective.non_home_ids
            if objective_id not in turn_start_ids
        ),
        turn_start_ids,
    )


def _destruction_evidence(
    context: PrimaryScoringConditionContext,
    *,
    count_each: bool,
) -> dict[str, JsonValue]:
    matching = _enemy_destructions_this_turn(context)
    return primary_score_count_evidence(
        score_count=len(matching) if count_each else (1 if matching else 0),
        destroyed_unit_instance_ids=tuple(
            sorted({row.destroyed_unit_instance_id for row in matching})
        ),
        destruction_ids=tuple(row.destruction_id for row in matching),
    )


def _enemy_destructions_this_turn(
    context: PrimaryScoringConditionContext,
) -> tuple[PrimaryUnitDestructionEvidence, ...]:
    return tuple(
        row
        for row in context.destruction_evidence
        if row.destroyed_player_id != context.player_id
        and row.active_player_id == context.record.active_player_id
        and row.battle_round == context.record.battle_round
    )


def _destroyed_by_friendly_unit_on_objective_evidence(
    context: PrimaryScoringConditionContext,
) -> dict[str, JsonValue]:
    matching = tuple(
        row
        for row in _enemy_destructions_this_turn(context)
        if row.destroying_player_id == context.player_id
        and row.destruction_attribution is not None
        and row.destruction_attribution.source_rules_unit_instance_id is not None
        and row.source_rules_unit_objective_proximity_witness is not None
        and row.source_rules_unit_objective_proximity_witness.objective_marker_ids
    )
    objective_ids = tuple(
        sorted(
            {
                objective_id
                for row in matching
                for objective_id in cast(
                    RulesUnitObjectiveProximityWitness,
                    row.source_rules_unit_objective_proximity_witness,
                ).objective_marker_ids
            }
        )
    )
    evidence = primary_score_count_evidence(
        score_count=1 if matching else 0,
        destroyed_unit_instance_ids=tuple(
            sorted({row.destroyed_unit_instance_id for row in matching})
        ),
        destruction_ids=tuple(row.destruction_id for row in matching),
    )
    evidence["source_rules_unit_objective_marker_ids"] = list(objective_ids)
    return evidence


def _started_turn_objective_destruction_evidence(
    context: PrimaryScoringConditionContext,
    *,
    allowed_objective_ids: tuple[str, ...] | None,
) -> dict[str, JsonValue]:
    allowed = None if allowed_objective_ids is None else set(allowed_objective_ids)
    matched_ids_by_destruction: dict[str, tuple[str, ...]] = {}
    matching: list[PrimaryUnitDestructionEvidence] = []
    for row in _enemy_destructions_this_turn(context):
        objective_ids = tuple(
            objective_id
            for objective_id in row.started_turn_objective_marker_ids
            if allowed is None or objective_id in allowed
        )
        if not objective_ids:
            continue
        matching.append(row)
        matched_ids_by_destruction[row.destruction_id] = objective_ids
    objective_ids = tuple(
        sorted(
            {
                objective_id
                for row_ids in matched_ids_by_destruction.values()
                for objective_id in row_ids
            }
        )
    )
    evidence = primary_score_count_evidence(
        score_count=1 if matching else 0,
        destroyed_unit_instance_ids=tuple(
            sorted({row.destroyed_unit_instance_id for row in matching})
        ),
        destruction_ids=tuple(row.destruction_id for row in matching),
    )
    evidence["started_turn_objective_marker_ids"] = list(objective_ids)
    if allowed_objective_ids is not None:
        evidence["central_objective_marker_ids"] = list(allowed_objective_ids)
    return evidence


def _table_quarter_evidence(
    context: PrimaryScoringConditionContext,
    *,
    condition: str,
    threshold: int,
) -> dict[str, JsonValue]:
    spatial = _required_spatial_evidence(
        context,
        condition=condition,
    )
    witnesses = spatial.table_quarter_unit_witnesses
    quarter_ids = tuple(sorted({witness.quarter_id for witness in witnesses}))
    unit_ids = tuple(sorted({witness.rules_unit_instance_id for witness in witnesses}))
    score_count = 1 if len(quarter_ids) >= threshold and len(unit_ids) >= threshold else 0
    evidence = primary_score_count_evidence(score_count=score_count)
    evidence["table_quarter_count_threshold"] = threshold
    evidence["qualifying_table_quarter_ids"] = list(quarter_ids)
    evidence["qualifying_friendly_unit_instance_ids"] = list(unit_ids)
    evidence["table_quarter_unit_witnesses"] = cast(
        JsonValue,
        [witness.to_payload() for witness in witnesses],
    )
    return evidence


def _required_spatial_evidence(
    context: PrimaryScoringConditionContext,
    *,
    condition: str,
) -> PrimaryScoringSpatialEvidence:
    if context.spatial_evidence is None:
        raise GameLifecycleError(
            f"Primary scoring condition {condition} requires spatial evidence."
        )
    if condition not in context.spatial_evidence.requested_condition_ids:
        raise GameLifecycleError(
            f"Primary scoring condition {condition} was not provisioned by spatial evidence."
        )
    return context.spatial_evidence


def _opponent_territory_objective_ids(
    context: PrimaryScoringConditionContext,
) -> tuple[str, ...]:
    opponent_player_id = _opponent_player_id(context)
    opponent_role = (
        "attacker" if opponent_player_id == context.mission_setup.attacker_player_id else "defender"
    )
    territory = _single_territory_region(context, owner_role=opponent_role)
    return tuple(
        marker.objective_marker_id
        for marker in context.mission_setup.objective_markers
        if territory.contains_point(marker.x_inches, marker.y_inches)
    )


def _territory_region_id(
    context: PrimaryScoringConditionContext,
    *,
    player_id: str,
) -> str:
    owner_role = "attacker" if player_id == context.mission_setup.attacker_player_id else "defender"
    return _single_territory_region(context, owner_role=owner_role).region_id


def _single_territory_region(
    context: PrimaryScoringConditionContext,
    *,
    owner_role: str,
) -> BattlefieldRegion:
    matches = tuple(
        region
        for region in context.mission_setup.battlefield_regions
        if region.region_kind is BattlefieldRegionKind.TERRITORY and region.owner_role == owner_role
    )
    if len(matches) != 1:
        raise GameLifecycleError(
            "Primary territory scoring requires exactly one directed territory per player."
        )
    return matches[0]


def _opponent_player_id(context: PrimaryScoringConditionContext) -> str:
    return next(player_id for player_id in context.turn_order if player_id != context.player_id)


def _intersection(
    left: tuple[str, ...],
    right: tuple[str, ...],
) -> tuple[str, ...]:
    right_ids = set(right)
    return tuple(value for value in left if value in right_ids)


def _validate_identifier_tuple(
    field_name: str,
    values: object,
    *,
    preserve_order: bool = False,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        identifiers.append(identifier)
        seen.add(identifier)
    return tuple(identifiers if preserve_order else sorted(identifiers))


_validate_identifier = IdentifierValidator(GameLifecycleError)
