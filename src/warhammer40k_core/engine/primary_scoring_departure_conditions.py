from __future__ import annotations

from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_battlefield_departure import (
    PrimaryBattlefieldDepartureState,
)
from warhammer40k_core.engine.primary_mission_state import (
    PrimaryCondemnedSelectionState,
    PrimaryMissionProgressState,
)
from warhammer40k_core.engine.primary_scoring_conditions import primary_score_count_evidence
from warhammer40k_core.engine.primary_scoring_turn_keys import (
    primary_own_turn_interval_contains,
)

CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN = (
    "one_or_more_condemned_enemy_units_left_battlefield_this_turn"
)

PRIMARY_SCORING_DEPARTURE_CONDITIONS = frozenset(
    {
        CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
    }
)


def condemned_selection_source_identity() -> tuple[str, str]:
    from warhammer40k_core.engine.mission_action_policies import (
        primary_mission_choice_rule_for_id,
    )
    from warhammer40k_core.engine.primary_mission_choices import PUNISHMENT_CHOICE_RULE_ID

    descriptor = primary_mission_choice_rule_for_id(PUNISHMENT_CHOICE_RULE_ID)
    return (descriptor.source_id, descriptor.choice_rule_id)


def evaluate_departure_scoring_condition(
    *,
    condition_id: str,
    progress: PrimaryMissionProgressState,
    departures: tuple[PrimaryBattlefieldDepartureState, ...],
    mission_setup: MissionSetup,
    player_id: str,
    battle_round: int,
    active_player_id: str,
    turn_order: tuple[str, ...],
) -> dict[str, JsonValue]:
    if condition_id not in PRIMARY_SCORING_DEPARTURE_CONDITIONS:
        raise GameLifecycleError(f"Unsupported primary scoring condition: {condition_id}.")
    if type(progress) is not PrimaryMissionProgressState:
        raise GameLifecycleError("Primary departure scoring requires PrimaryMissionProgressState.")
    if type(departures) is not tuple:
        raise GameLifecycleError(
            "Primary departure scoring requires PrimaryBattlefieldDepartureState tuples."
        )
    if type(mission_setup) is not MissionSetup:
        raise GameLifecycleError("Primary departure scoring requires MissionSetup.")
    if type(battle_round) is not int or battle_round < 1:
        raise GameLifecycleError("Primary departure scoring battle_round must be a positive int.")
    this_turn = _this_turn_departures(
        departures,
        battle_round=battle_round,
        active_player_id=active_player_id,
    )
    selection = _active_condemned_selection(
        progress,
        mission_setup=mission_setup,
        player_id=player_id,
        battle_round=battle_round,
        active_player_id=active_player_id,
        turn_order=turn_order,
    )
    condemned_ids = () if selection is None else selection.selected_rules_unit_instance_ids
    departed_ids: list[str] = []
    matching_rows: list[PrimaryBattlefieldDepartureState] = []
    for unit_id in condemned_ids:
        contributing = _condemned_unit_departures_when_fully_left(
            rules_unit_instance_id=unit_id,
            departures=this_turn,
            scoring_player_id=player_id,
        )
        if contributing is None:
            continue
        departed_ids.append(unit_id)
        matching_rows.extend(contributing)
    evidence = primary_score_count_evidence(score_count=int(bool(departed_ids)))
    evidence["condemned_rules_unit_instance_ids"] = list(condemned_ids)
    evidence["departed_condemned_rules_unit_instance_ids"] = list(departed_ids)
    matching_departure_ids = tuple(sorted({departure.departure_id for departure in matching_rows}))
    evidence["matching_departure_ids"] = list(matching_departure_ids)
    return evidence


def _this_turn_departures(
    departures: tuple[PrimaryBattlefieldDepartureState, ...],
    *,
    battle_round: int,
    active_player_id: str,
) -> tuple[PrimaryBattlefieldDepartureState, ...]:
    matching: list[PrimaryBattlefieldDepartureState] = []
    seen_ids: set[str] = set()
    for departure in departures:
        if type(departure) is not PrimaryBattlefieldDepartureState:
            raise GameLifecycleError(
                "Primary scoring departures must be typed PrimaryBattlefieldDepartureState."
            )
        if departure.departure_id in seen_ids:
            raise GameLifecycleError("Primary scoring departures must not duplicate departure_id.")
        seen_ids.add(departure.departure_id)
        if departure.battle_round != battle_round or departure.active_player_id != active_player_id:
            continue
        matching.append(departure)
    return tuple(matching)


def _active_condemned_selection(
    progress: PrimaryMissionProgressState,
    *,
    mission_setup: MissionSetup,
    player_id: str,
    battle_round: int,
    active_player_id: str,
    turn_order: tuple[str, ...],
) -> PrimaryCondemnedSelectionState | None:
    catalog_identity = condemned_selection_source_identity()
    mission_id = mission_setup.primary_mission_id_for_player(player_id)
    matches: list[PrimaryCondemnedSelectionState] = []
    for selection in progress.condemned_selections:
        if type(selection) is not PrimaryCondemnedSelectionState:
            raise GameLifecycleError(
                "Primary scoring condemned selections must be typed PrimaryCondemnedSelectionState."
            )
        if selection.owner_player_id != player_id or selection.mission_id != mission_id:
            continue
        if not primary_own_turn_interval_contains(
            owner_player_id=selection.owner_player_id,
            started_battle_round=selection.battle_round,
            query_battle_round=battle_round,
            query_active_player_id=active_player_id,
            turn_order=turn_order,
        ):
            continue
        if selection.active_player_id != selection.owner_player_id:
            raise GameLifecycleError("Punishment condemned selection was not created on own turn.")
        if (selection.source_rule_id, selection.source_descriptor_id) != catalog_identity:
            raise GameLifecycleError("Primary scoring condemned selection source identity drifted.")
        matches.append(selection)
    if len(matches) > 1:
        raise GameLifecycleError("Punishment has duplicate current-turn condemned selections.")
    if not matches:
        return None
    return matches[0]


def _condemned_unit_departures_when_fully_left(
    *,
    rules_unit_instance_id: str,
    departures: tuple[PrimaryBattlefieldDepartureState, ...],
    scoring_player_id: str,
) -> tuple[PrimaryBattlefieldDepartureState, ...] | None:
    direct_matches = tuple(
        departure
        for departure in departures
        if departure.rules_unit_instance_id == rules_unit_instance_id
    )
    if direct_matches:
        _assert_enemy_departures(
            direct_matches,
            scoring_player_id=scoring_player_id,
        )
        component_lineages = {
            frozenset(departure.component_unit_instance_ids) for departure in direct_matches
        }
        if len(component_lineages) != 1:
            raise GameLifecycleError("Punishment condemned departure component identity drifted.")
        historical_components = next(iter(component_lineages))
        if not historical_components:
            raise GameLifecycleError("Punishment condemned departure component identity drifted.")
        related = list(direct_matches)
        for departure in departures:
            if departure.rules_unit_instance_id == rules_unit_instance_id:
                continue
            current_identities = frozenset(
                (departure.rules_unit_instance_id, *departure.component_unit_instance_ids)
            )
            departed_identities = frozenset(departure.departed_component_unit_instance_ids)
            if (
                not current_identities
                or not current_identities <= historical_components
                or not departed_identities
                or not departed_identities <= historical_components
            ):
                continue
            related.append(departure)
        related_matches = tuple(related)
        _assert_enemy_departures(
            related_matches,
            scoring_player_id=scoring_player_id,
        )
        departed_ids = {
            component_id
            for departure in related_matches
            for component_id in departure.departed_component_unit_instance_ids
        }
        if historical_components <= departed_ids:
            return related_matches
        return None
    component_matches = tuple(
        departure
        for departure in departures
        if rules_unit_instance_id in departure.departed_component_unit_instance_ids
    )
    if not component_matches:
        return None
    _assert_enemy_departures(
        component_matches,
        scoring_player_id=scoring_player_id,
    )
    return component_matches


def _assert_enemy_departures(
    departures: tuple[PrimaryBattlefieldDepartureState, ...],
    *,
    scoring_player_id: str,
) -> None:
    owners = {departure.owner_player_id for departure in departures}
    if scoring_player_id in owners:
        raise GameLifecycleError("Punishment condemned departure owner drifted.")
    if len(owners) != 1:
        raise GameLifecycleError("Punishment condemned departure owner drifted.")


__all__ = (
    "CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN",
    "PRIMARY_SCORING_DEPARTURE_CONDITIONS",
    "condemned_selection_source_identity",
    "evaluate_departure_scoring_condition",
)
