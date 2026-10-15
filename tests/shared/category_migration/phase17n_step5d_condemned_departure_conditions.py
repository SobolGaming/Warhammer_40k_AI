from __future__ import annotations

from dataclasses import replace

import pytest

from tests.phase11c_command_phase_helpers import default_unit_selection, with_model_offsets
from tests.phase17n_primary_mission_helpers import (
    phase17n_event_setup,
    phase17n_punishment_pending_fixture,
)
from warhammer40k_core.core.missions import ObjectiveMarkerRole
from warhammer40k_core.engine.battlefield_state import BattlefieldRemovalKind
from warhammer40k_core.engine.damage_allocation import destroy_model_by_rule
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import EventLog
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import UnitMusterSelection
from warhammer40k_core.engine.mission_action_policies import primary_mission_choice_rule_for_id
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.missions import (
    mission_scoring_policies_from_setup,
    primary_scoring_rules_from_definition,
)
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_battlefield_departure import (
    PrimaryBattlefieldDepartureState,
    primary_battlefield_departure_id,
    record_primary_battlefield_departure,
)
from warhammer40k_core.engine.primary_historical_events import (
    record_primary_battlefield_departure_event,
)
from warhammer40k_core.engine.primary_mission_choice_payloads import PrimaryMissionChoiceData
from warhammer40k_core.engine.primary_mission_choices import PUNISHMENT_CHOICE_RULE_ID
from warhammer40k_core.engine.primary_mission_state import (
    PrimaryCondemnedSelectionState,
    PrimaryMissionProgressState,
    primary_condemned_selection_id,
)
from warhammer40k_core.engine.primary_scoring_boundary import (
    score_primary_objective_control_boundary,
)
from warhammer40k_core.engine.primary_scoring_boundary_inventory import (
    required_primary_scoring_boundary_kinds,
)
from warhammer40k_core.engine.primary_scoring_commit_checkpoint import (
    PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT,
)
from warhammer40k_core.engine.primary_scoring_condition_evaluator import (
    SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS,
    PrimaryScoringConditionContext,
    evaluate_primary_scoring_condition,
)
from warhammer40k_core.engine.primary_scoring_departure_conditions import (
    CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
    PRIMARY_SCORING_DEPARTURE_CONDITIONS,
    condemned_selection_source_identity,
    evaluate_departure_scoring_condition,
)
from warhammer40k_core.engine.primary_scoring_state_evidence import PrimaryScoringBoundaryKind
from warhammer40k_core.engine.primary_scoring_turn_keys import primary_own_turn_interval_contains
from warhammer40k_core.engine.primary_scoring_turn_scope import (
    ANY_PLAYER_TURN,
    OWN_PLAYER_TURN,
    PRIMARY_SCORING_ANY_PLAYER_TURN_CONDITIONS,
    primary_scoring_rule_applies_at_record,
    primary_scoring_turn_scope_for_condition,
)
from warhammer40k_core.engine.primary_unit_destruction_tracking import (
    record_primary_destroyed_model_departures,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.scoring import VictoryPointSourceKind
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    event_companion_primary_scoring_2026_06 as event_primary_scoring,
)


def _punishment_setup(
    *,
    attacker_player_id: str = "player-a",
    defender_player_id: str = "player-b",
) -> MissionSetup:
    return phase17n_event_setup(
        layout_id="purge-the-foe-vs-disruption-layout-1",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="disruption",
        attacker_player_id=attacker_player_id,
        defender_player_id=defender_player_id,
    )


def _progress(
    *selections: PrimaryCondemnedSelectionState,
) -> PrimaryMissionProgressState:
    return PrimaryMissionProgressState(
        markers=(),
        condemned_selections=selections,
        consecration_designations=(),
    )


def _condemned_selection(
    *,
    selected_ids: tuple[str, ...],
    candidate_ids: tuple[str, ...] | None = None,
    battle_round: int = 1,
    owner_player_id: str = "player-a",
    mission_id: str = "primary-punishment",
    source_rule_id: str | None = None,
    source_descriptor_id: str | None = None,
    selection_index: int = 1,
) -> PrimaryCondemnedSelectionState:
    catalog_source, catalog_descriptor = condemned_selection_source_identity()
    candidates = selected_ids if candidate_ids is None else candidate_ids
    if not candidates:
        minimum = maximum = 0
        request_id = None
        result_id = None
    else:
        minimum = 1
        maximum = min(3, len(candidates))
        request_id = f"step5d-condemned-request-{selection_index:02d}"
        result_id = f"step5d-condemned-result-{selection_index:02d}"
    source_rule = catalog_source if source_rule_id is None else source_rule_id
    source_descriptor = catalog_descriptor if source_descriptor_id is None else source_descriptor_id
    descriptor = primary_mission_choice_rule_for_id(PUNISHMENT_CHOICE_RULE_ID)
    policy_id = descriptor.target_policy
    source_event_id = f"step5d-condemned-event-{selection_index:02d}"
    selection_id = primary_condemned_selection_id(
        game_id="step5d-game",
        owner_player_id=owner_player_id,
        mission_id=mission_id,
        source_rule_id=source_rule,
        source_descriptor_id=source_descriptor,
        battle_round=battle_round,
        active_player_id=owner_player_id,
        candidate_policy_id=policy_id,
        candidate_rules_unit_instance_ids=candidates,
        candidate_evidence_ids=(),
        selected_rules_unit_instance_ids=selected_ids,
        minimum_selection_count=minimum,
        maximum_selection_count=maximum,
        used_fallback_candidates=False,
        selection_request_id=request_id,
        selection_result_id=result_id,
        source_event_id=source_event_id,
    )
    return PrimaryCondemnedSelectionState(
        selection_id=selection_id,
        game_id="step5d-game",
        owner_player_id=owner_player_id,
        mission_id=mission_id,
        source_rule_id=source_rule,
        source_descriptor_id=source_descriptor,
        battle_round=battle_round,
        active_player_id=owner_player_id,
        candidate_policy_id=policy_id,
        candidate_rules_unit_instance_ids=candidates,
        candidate_evidence_ids=(),
        selected_rules_unit_instance_ids=selected_ids,
        minimum_selection_count=minimum,
        maximum_selection_count=maximum,
        used_fallback_candidates=False,
        selection_request_id=request_id,
        selection_result_id=result_id,
        source_event_id=source_event_id,
    )


def _departure(
    *,
    rules_unit_instance_id: str,
    owner_player_id: str = "player-b",
    battle_round: int = 1,
    active_player_id: str = "player-a",
    occurrence_id: str = "step5d-departure",
    departed: bool = True,
    component_ids: tuple[str, ...] | None = None,
    departed_ids: tuple[str, ...] | None = None,
    removal_kind: BattlefieldRemovalKind = BattlefieldRemovalKind.DESTROYED,
) -> PrimaryBattlefieldDepartureState:
    components = (rules_unit_instance_id,) if component_ids is None else component_ids
    if departed_ids is None:
        departed_component_ids = components if departed else ()
    else:
        departed_component_ids = departed_ids
    affected = components if departed_component_ids else (components[0],)
    if departed_component_ids:
        affected = tuple(
            component_id
            for component_id in components
            if component_id in set(departed_component_ids)
        )
        if not affected:
            affected = departed_component_ids
    removed_model_ids = tuple(f"{component_id}-model-{occurrence_id}" for component_id in affected)
    source_id = f"{occurrence_id}-source"
    departure_id = primary_battlefield_departure_id(
        game_id="step5d-game",
        rules_unit_instance_id=rules_unit_instance_id,
        affected_component_unit_instance_ids=affected,
        departed_component_unit_instance_ids=departed_component_ids,
        removed_model_instance_ids=removed_model_ids,
        battle_round=battle_round,
        active_player_id=active_player_id,
        phase=BattlePhase.FIGHT.value,
        removal_kind=removal_kind,
        occurrence_id=occurrence_id,
        source_id=source_id,
    )
    return PrimaryBattlefieldDepartureState(
        departure_id=departure_id,
        game_id="step5d-game",
        owner_player_id=owner_player_id,
        rules_unit_instance_id=rules_unit_instance_id,
        component_unit_instance_ids=components,
        affected_component_unit_instance_ids=affected,
        departed_component_unit_instance_ids=departed_component_ids,
        removed_model_instance_ids=removed_model_ids,
        battle_round=battle_round,
        active_player_id=active_player_id,
        phase=BattlePhase.FIGHT.value,
        removal_kind=removal_kind,
        occurrence_id=occurrence_id,
        source_id=source_id,
    )


def _resolved_condemned_departure(
    *,
    depart_selected: bool = True,
    attacker_player_id: str = "player-a",
    defender_player_id: str = "player-b",
    owner_player_id: str = "player-a",
    selection_battle_round: int = 1,
    departure_battle_round: int | None = None,
    departure_active_player_id: str | None = None,
    removal_kind: BattlefieldRemovalKind = BattlefieldRemovalKind.DESTROYED,
    player_a_units: tuple[UnitMusterSelection, ...] | None = None,
    player_b_units: tuple[UnitMusterSelection, ...] | None = None,
    selected_count: int | None = None,
    depart_unit_index: int = 0,
    score_owner_command: bool = False,
) -> tuple[GameState, ObjectiveControlRecord, DecisionController]:
    state, decisions, request = phase17n_punishment_pending_fixture(
        attacker_player_id=attacker_player_id,
        defender_player_id=defender_player_id,
        owner_player_id=owner_player_id,
        battle_round=selection_battle_round,
        player_a_units=player_a_units,
        player_b_units=player_b_units,
    )
    option = _condemn_option(request, selected_count=selected_count)
    GameLifecycle(decision_controller=decisions, state=state).submit_decision(
        DecisionResult.for_request(
            result_id=(
                f"step5d-condemn-select-result-{selection_battle_round:02d}-{owner_player_id}"
            ),
            request=request,
            selected_option_id=option.option_id,
        )
    )
    _bind_force_dispositions(state)
    if score_owner_command:
        _place_owner_on_expansion(state, owner_player_id=owner_player_id)
        _park_enemy_units_away_from_objectives(state, owner_player_id=owner_player_id)
        state.battle_round = selection_battle_round
        state.active_player_id = owner_player_id
        state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.COMMAND)
        command_record = state.record_objective_control_boundary(
            completed_phase=BattlePhase.COMMAND,
            timing=ObjectiveControlTiming.PHASE_END,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
        score_primary_objective_control_boundary(
            state=state,
            record=command_record,
            end_of_battle=False,
            event_log=decisions.event_log,
        )
    (selection,) = state.primary_mission_progress_state.condemned_selections
    selected_ids = selection.selected_rules_unit_instance_ids
    departure_round = (
        selection_battle_round if departure_battle_round is None else departure_battle_round
    )
    departure_player = (
        owner_player_id if departure_active_player_id is None else departure_active_player_id
    )
    if depart_selected:
        _depart_rules_unit(
            state=state,
            decisions=decisions,
            rules_unit_instance_id=selected_ids[depart_unit_index],
            removal_kind=removal_kind,
            occurrence_id=(
                "step5d-condemned-departure-"
                f"{departure_round:02d}-{departure_player}-{removal_kind.value}"
            ),
            battle_round=departure_round,
            active_player_id=departure_player,
        )
    else:
        state.battle_round = departure_round
        state.active_player_id = departure_player
        state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    record = state.record_objective_control_boundary(
        completed_phase=BattlePhase.FIGHT,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    return state, record, decisions


def _resolved_condemned_attached_component_loss_departure(
    *,
    destroyed_component: str,
    surviving_removal_kind: BattlefieldRemovalKind,
    depart_survivor: bool = True,
) -> tuple[GameState, ObjectiveControlRecord, DecisionController, str, str]:
    player_b_units = (
        default_unit_selection("intercessor-unit-3"),
        default_unit_selection("intercessor-unit-4"),
    )
    state, decisions, request = phase17n_punishment_pending_fixture(
        player_b_units=player_b_units,
        attach_first_two_enemy_units=True,
    )
    enemy_army = next(army for army in state.army_definitions if army.player_id == "player-b")
    (formation,) = enemy_army.attached_units
    attached_id = formation.attached_unit_instance_id
    bodyguard_id = formation.bodyguard_unit_instance_id
    leader_id = formation.leader_unit_instance_ids[0]
    if destroyed_component == "bodyguard":
        destroyed_id = bodyguard_id
        survivor_id = leader_id
    elif destroyed_component == "leader":
        destroyed_id = leader_id
        survivor_id = bodyguard_id
    else:
        raise AssertionError(f"unsupported destroyed component: {destroyed_component}")
    option = _condemn_attached_option(request, attached_id=attached_id)
    GameLifecycle(decision_controller=decisions, state=state).submit_decision(
        DecisionResult.for_request(
            result_id="step5d-attached-component-loss-condemn-result",
            request=request,
            selected_option_id=option.option_id,
        )
    )
    _bind_force_dispositions(state)
    state.battle_round = 1
    state.active_player_id = "player-a"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    _destroy_component_for_scoring(
        state=state,
        decisions=decisions,
        component_id=destroyed_id,
        attached_id=attached_id,
    )
    if depart_survivor:
        _depart_rules_unit(
            state=state,
            decisions=decisions,
            rules_unit_instance_id=attached_id,
            removal_kind=surviving_removal_kind,
            occurrence_id=f"step5d-attached-survivor-{surviving_removal_kind.value}",
            battle_round=1,
            active_player_id="player-a",
        )
    record = state.record_objective_control_boundary(
        completed_phase=BattlePhase.FIGHT,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    return state, record, decisions, attached_id, survivor_id


def _condemn_attached_option(request: DecisionRequest, *, attached_id: str) -> DecisionOption:
    for candidate in request.options:
        selected_ids = PrimaryMissionChoiceData.from_payload(candidate.payload).selected_target_ids
        if selected_ids == (attached_id,):
            return candidate
    raise AssertionError("Step 5D attached fixture requires a condemned Attached Unit option.")


def _destroy_component_for_scoring(
    *,
    state: GameState,
    decisions: DecisionController,
    component_id: str,
    attached_id: str,
) -> None:
    if state.battlefield_state is None:
        raise AssertionError("Step 5D attached fixture requires battlefield state.")
    placement = state.battlefield_state.unit_placement_by_id(component_id)
    removed_model_ids = tuple(
        model_placement.model_instance_id for model_placement in placement.model_placements
    )
    for model_instance_id in removed_model_ids:
        destroy_model_by_rule(state=state, model_instance_id=model_instance_id)
    departures = record_primary_destroyed_model_departures(
        state=state,
        destroyed_model_instance_ids=removed_model_ids,
        source_id=f"step5d-attached-destroy:{component_id}",
        occurrence_id=f"step5d-attached-destroy:{component_id}",
    )
    if not departures:
        raise AssertionError("Step 5D attached fixture requires destroyed-component departure.")
    for departure in departures:
        assert departure.rules_unit_instance_id == attached_id
        assert component_id in departure.departed_component_unit_instance_ids
        record_primary_battlefield_departure_event(
            event_log=decisions.event_log,
            departure=departure,
        )


def _condemn_option(
    request: DecisionRequest,
    *,
    selected_count: int | None,
) -> DecisionOption:
    for candidate in request.options:
        selected_ids = PrimaryMissionChoiceData.from_payload(candidate.payload).selected_target_ids
        if not selected_ids:
            continue
        if selected_count is None or len(selected_ids) == selected_count:
            return candidate
    raise AssertionError("Step 5D fixture requires a condemn option.")


def _depart_rules_unit(
    *,
    state: GameState,
    decisions: DecisionController,
    rules_unit_instance_id: str,
    removal_kind: BattlefieldRemovalKind,
    occurrence_id: str,
    battle_round: int,
    active_player_id: str,
) -> None:
    state.battle_round = battle_round
    state.active_player_id = active_player_id
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    if state.battlefield_state is None:
        raise AssertionError("Step 5D fixture requires battlefield state.")
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=rules_unit_instance_id,
    )
    component_placements = tuple(
        (component_id, state.battlefield_state.unit_placement_or_none(component_id))
        for component_id in rules_unit.component_unit_instance_ids
    )
    affected_component_ids = tuple(
        component_id for component_id, placement in component_placements if placement is not None
    )
    removed_model_ids = tuple(
        model_placement.model_instance_id
        for _component_id, placement in component_placements
        if placement is not None
        for model_placement in placement.model_placements
    )
    state.battlefield_state = state.battlefield_state.with_removed_models(removed_model_ids)
    departure = record_primary_battlefield_departure(
        state=state,
        rules_unit_instance_id=rules_unit_instance_id,
        affected_component_unit_instance_ids=affected_component_ids,
        departed_component_unit_instance_ids=affected_component_ids,
        removed_model_instance_ids=removed_model_ids,
        removal_kind=removal_kind,
        occurrence_id=occurrence_id,
        source_id=f"{occurrence_id}-source",
    )
    if departure is None:
        raise AssertionError("Step 5D fixture requires battlefield-departure evidence.")
    record_primary_battlefield_departure_event(
        event_log=decisions.event_log,
        departure=departure,
    )


def _park_enemy_units_away_from_objectives(
    state: GameState,
    *,
    owner_player_id: str,
) -> None:
    setup = state.mission_setup
    if setup is None or state.battlefield_state is None:
        raise AssertionError("Step 5D fixture requires MissionSetup and battlefield state.")
    marker = next(
        objective
        for objective in setup.objective_markers
        if objective.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    enemy_player_id = next(
        player_id for player_id in state.player_ids if player_id != owner_player_id
    )
    enemies = tuple(
        unit
        for army in state.army_definitions
        if army.player_id == enemy_player_id
        for unit in army.units
        if state.battlefield_state.is_unit_placed(unit.unit_instance_id)
    )
    for enemy_index, enemy in enumerate(enemies):
        placement = state.battlefield_state.unit_placement_by_id(enemy.unit_instance_id)
        shift = 18.0 + float(enemy_index) * 3.0
        state.battlefield_state = state.battlefield_state.with_unit_placement(
            with_model_offsets(
                placement,
                marker,
                offsets=(
                    (shift, shift),
                    (shift + 1.0, shift),
                    (shift + 2.0, shift),
                    (shift, shift + 1.0),
                    (shift + 1.0, shift + 1.0),
                ),
            )
        )


def _place_owner_on_expansion(state: GameState, *, owner_player_id: str) -> None:
    setup = state.mission_setup
    if setup is None or state.battlefield_state is None:
        raise AssertionError("Step 5D fixture requires MissionSetup and battlefield state.")
    target = next(
        marker
        for marker in setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.EXPANSION
    )
    owner_unit = next(
        unit
        for army in state.army_definitions
        if army.player_id == owner_player_id
        for unit in army.units
    )
    placement = state.battlefield_state.unit_placement_by_id(owner_unit.unit_instance_id)
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        with_model_offsets(
            placement,
            target,
            offsets=((0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (0.0, 1.0), (1.0, 1.0)),
        )
    )


def _assert_condemned_boundary_path(
    *,
    state: GameState,
    record: ObjectiveControlRecord,
    decisions: DecisionController,
    owner_player_id: str,
    expected_vp: int,
) -> None:
    setup = state.mission_setup
    if setup is None:
        raise AssertionError("Step 5D fixture requires MissionSetup.")
    policies = mission_scoring_policies_from_setup(setup)
    scoring_ids = policies.scoring_player_ids_for_record(
        record=record,
        turn_order=tuple(state.turn_order),
        end_of_battle=False,
    )
    assert owner_player_id in scoring_ids
    required_kinds = required_primary_scoring_boundary_kinds(
        policies=policies,
        record=record,
        turn_order=tuple(state.turn_order),
    )
    assert PrimaryScoringBoundaryKind.ORDINARY in required_kinds
    score_primary_objective_control_boundary(
        state=state,
        record=record,
        end_of_battle=False,
        event_log=decisions.event_log,
    )
    awards = _primary_awards_by_condition(state, player_id=owner_player_id)
    if expected_vp:
        assert awards[CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN] == expected_vp
        condemned_rows = tuple(
            transaction
            for ledger in state.victory_point_ledgers
            for transaction in ledger.transactions
            if (
                type(transaction.metadata) is dict
                and transaction.metadata.get("scoring_rule_condition")
                == CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN
            )
        )
        assert condemned_rows
        assert all(row.player_id == owner_player_id for row in condemned_rows)
    else:
        assert CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN not in awards
    if record.active_player_id != owner_player_id:
        assert "control_one_or_more_non_home_objectives_from_battle_round_two" not in awards
        assert "control_more_objectives_than_opponent_from_battle_round_two" not in awards
    ledgers_payload = [ledger.to_payload() for ledger in state.victory_point_ledgers]
    evidence_payload = [
        evidence.to_payload() for evidence in state.primary_scoring_state_evidence_records
    ]
    score_primary_objective_control_boundary(
        state=state,
        record=record,
        end_of_battle=False,
        event_log=decisions.event_log,
    )
    assert [ledger.to_payload() for ledger in state.victory_point_ledgers] == ledgers_payload
    assert [
        evidence.to_payload() for evidence in state.primary_scoring_state_evidence_records
    ] == evidence_payload
    restored = GameState.from_payload(state.to_payload())
    assert restored.to_payload() == state.to_payload()
    replayed_log = EventLog.from_payload(decisions.event_log.to_payload())
    assert replayed_log.to_payload() == decisions.event_log.to_payload()
    assert any(
        event.event_type == PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT
        for event in replayed_log.records
    )
    evidence = next(
        row
        for row in restored.primary_scoring_state_evidence_records
        if row.objective_control_record_id == record.record_id
        and row.scoring_player_id == owner_player_id
    )
    reevaluated = policies.primary_awards_from_state_evidence(
        record=record,
        authoritative_state=restored,
        state_evidence=evidence,
    )
    owner_reevaluated = tuple(award for award in reevaluated if award.player_id == owner_player_id)
    reevaluated_condemned = tuple(
        award
        for award in owner_reevaluated
        if type(award.metadata) is dict
        and award.metadata.get("scoring_rule_condition")
        == CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN
    )
    if expected_vp:
        assert len(reevaluated_condemned) == 1
        assert reevaluated_condemned[0].amount == expected_vp
    else:
        assert not reevaluated_condemned


def _bind_force_dispositions(state: GameState) -> None:
    setup = state.mission_setup
    if setup is None:
        raise AssertionError("Step 5D fixture requires MissionSetup.")
    state.army_definitions = [
        replace(
            army,
            force_disposition_id=setup.primary_mission_assignment_for_player(
                army.player_id
            ).force_disposition_id,
        )
        for army in state.army_definitions
    ]


def _objective_context(
    *,
    setup: MissionSetup,
    battle_round: int,
) -> PrimaryScoringConditionContext:
    results = tuple(
        ObjectiveControlResult.from_contributors(
            objective_id=marker.objective_marker_id,
            contributors=(),
        )
        for marker in setup.objective_markers
    )
    record = ObjectiveControlRecord(
        record_id=f"step5d-objective-record-round-{battle_round}",
        game_id="step5d-objective-game",
        battle_round=battle_round,
        active_player_id="player-a",
        timing=ObjectiveControlTiming.TURN_END,
        phase=BattlePhase.FIGHT.value,
        battlefield_id="step5d-objective-battlefield",
        results=results,
    )
    return PrimaryScoringConditionContext(
        record=record,
        mission_setup=setup,
        turn_order=("player-a", "player-b"),
        player_id="player-a",
    )


def _primary_awards_by_condition(state: GameState, *, player_id: str) -> dict[str, int]:
    awards: dict[str, int] = {}
    for ledger in state.victory_point_ledgers:
        for transaction in ledger.transactions:
            if (
                transaction.player_id != player_id
                or transaction.source_kind is not VictoryPointSourceKind.PRIMARY
                or type(transaction.metadata) is not dict
            ):
                continue
            condition = transaction.metadata.get("scoring_rule_condition")
            if type(condition) is not str:
                continue
            awards[condition] = transaction.amount
    return awards


__all__: list[str] = []
__all__ += ["ANY_PLAYER_TURN", "BattlePhase", "BattlefieldRemovalKind"]
__all__ += ["CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN", "DecisionController"]
__all__ += ["DecisionOption", "DecisionRequest", "DecisionResult", "EventLog", "GameLifecycle"]
__all__ += ["OWN_PLAYER_TURN", "GameLifecycleError", "GameState", "MissionSetup"]
__all__ += ["ObjectiveControlRecord", "ObjectiveControlResult", "ObjectiveControlTiming"]
__all__ += ["PRIMARY_SCORING_ANY_PLAYER_TURN_CONDITIONS", "ObjectiveMarkerRole"]
__all__ += ["PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT", "PRIMARY_SCORING_DEPARTURE_CONDITIONS"]
__all__ += ["PUNISHMENT_CHOICE_RULE_ID", "PrimaryBattlefieldDepartureState"]
__all__ += ["PrimaryCondemnedSelectionState", "PrimaryMissionChoiceData"]
__all__ += ["PrimaryMissionProgressState", "PrimaryScoringBoundaryKind"]
__all__ += ["PrimaryScoringConditionContext", "RuntimeModifierRegistry"]
__all__ += ["SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS", "UnitMusterSelection"]
__all__ += ["VictoryPointSourceKind", "_assert_condemned_boundary_path"]
__all__ += ["_bind_force_dispositions", "_condemn_attached_option", "_condemn_option"]
__all__ += ["_condemned_selection", "_depart_rules_unit", "_departure"]
__all__ += ["_destroy_component_for_scoring", "_objective_context"]
__all__ += ["_park_enemy_units_away_from_objectives", "_place_owner_on_expansion"]
__all__ += ["_primary_awards_by_condition", "_progress", "_punishment_setup"]
__all__ += ["_resolved_condemned_attached_component_loss_departure"]
__all__ += ["_resolved_condemned_departure", "condemned_selection_source_identity"]
__all__ += ["default_unit_selection", "destroy_model_by_rule"]
__all__ += ["evaluate_departure_scoring_condition", "evaluate_primary_scoring_condition"]
__all__ += ["event_primary_scoring", "mission_scoring_policies_from_setup"]
__all__ += ["phase17n_event_setup", "phase17n_punishment_pending_fixture"]
__all__ += ["primary_battlefield_departure_id", "primary_condemned_selection_id"]
__all__ += ["primary_mission_choice_rule_for_id", "primary_own_turn_interval_contains"]
__all__ += ["primary_scoring_rule_applies_at_record", "primary_scoring_rules_from_definition"]
__all__ += ["primary_scoring_turn_scope_for_condition", "pytest"]
__all__ += ["record_primary_battlefield_departure", "record_primary_battlefield_departure_event"]
__all__ += ["record_primary_destroyed_model_departures", "replace"]
__all__ += ["required_primary_scoring_boundary_kinds", "rules_unit_view_by_id"]
__all__ += ["score_primary_objective_control_boundary"]
__all__ += ["warhammer_event_companion_2026_07_mission_pack", "with_model_offsets"]
