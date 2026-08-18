from __future__ import annotations

from dataclasses import replace

import pytest
from tests.phase17n_primary_mission_helpers import (
    phase17n_event_setup,
    phase17n_punishment_pending_fixture,
)

from warhammer40k_core.engine.battlefield_state import BattlefieldRemovalKind
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.mission_action_policies import (
    primary_mission_choice_rule_for_id,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.missions import primary_scoring_rules_from_definition
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
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.scoring import VictoryPointSourceKind
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)


def test_phase17n_step5d_departure_conditions_are_registered() -> None:
    assert PRIMARY_SCORING_DEPARTURE_CONDITIONS <= SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS
    assert CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN in (
        SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS
    )


def test_phase17n_step5d_promotes_punishment() -> None:
    package = warhammer_event_companion_2026_07_mission_pack()
    primary_by_id = {primary.primary_mission_id: primary for primary in package.primary_missions}
    rules = primary_scoring_rules_from_definition(primary_by_id["primary-punishment"])
    assert rules
    assert all(rule.condition in SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS for rule in rules)
    assert any(rule.condition == CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN for rule in rules)


def test_phase17n_step5d_keeps_remaining_condition_pending_missions_fail_closed() -> None:
    package = warhammer_event_companion_2026_07_mission_pack()
    primary_by_id = {primary.primary_mission_id: primary for primary in package.primary_missions}
    for mission_id in (
        "primary-gather-intel",
        "primary-extract-relic",
        "primary-surveil-the-foe",
        "primary-locate-and-deny",
        "primary-vital-link",
    ):
        assert (
            primary_scoring_rules_from_definition(
                primary_by_id[mission_id],
                require_supported=False,
            )
            == ()
        )
        with pytest.raises(
            GameLifecycleError,
            match="source is known but engine implementation is pending",
        ):
            primary_scoring_rules_from_definition(primary_by_id[mission_id])


def test_phase17n_step5d_departure_conditions_require_state_evidence() -> None:
    setup = _punishment_setup()
    context = _objective_context(setup=setup, battle_round=1)
    with pytest.raises(GameLifecycleError, match="requires state evidence"):
        evaluate_primary_scoring_condition(
            condition=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
            context=context,
        )


def test_phase17n_step5d_scores_boolean_once_when_condemned_unit_fully_left() -> None:
    setup = _punishment_setup()
    condemned = _condemned_selection(
        selected_ids=("enemy-unit-1", "enemy-unit-2"),
    )
    matching = evaluate_departure_scoring_condition(
        condition_id=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
        progress=_progress(condemned),
        departures=(
            _departure(rules_unit_instance_id="enemy-unit-1", occurrence_id="left-1"),
            _departure(rules_unit_instance_id="enemy-unit-2", occurrence_id="left-2"),
            _departure(
                rules_unit_instance_id="enemy-unit-3",
                occurrence_id="non-condemned",
            ),
        ),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        active_player_id="player-a",
    )
    assert matching["score_count"] == 1
    assert matching["departed_condemned_rules_unit_instance_ids"] == [
        "enemy-unit-1",
        "enemy-unit-2",
    ]


def test_phase17n_step5d_empty_or_missing_condemned_selection_scores_zero() -> None:
    setup = _punishment_setup()
    empty = evaluate_departure_scoring_condition(
        condition_id=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
        progress=_progress(_condemned_selection(selected_ids=())),
        departures=(_departure(rules_unit_instance_id="enemy-unit-1"),),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        active_player_id="player-a",
    )
    missing = evaluate_departure_scoring_condition(
        condition_id=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
        progress=PrimaryMissionProgressState.empty(),
        departures=(_departure(rules_unit_instance_id="enemy-unit-1"),),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        active_player_id="player-a",
    )
    assert empty["score_count"] == 0
    assert missing["score_count"] == 0


def test_phase17n_step5d_ignores_non_condemned_partial_other_round_and_other_turn() -> None:
    setup = _punishment_setup()
    condemned = _condemned_selection(selected_ids=("enemy-unit-1",))
    evidence = evaluate_departure_scoring_condition(
        condition_id=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
        progress=_progress(condemned),
        departures=(
            _departure(
                rules_unit_instance_id="enemy-unit-2",
                occurrence_id="other-unit",
            ),
            _departure(
                rules_unit_instance_id="enemy-unit-1",
                occurrence_id="partial",
                departed=False,
            ),
            _departure(
                rules_unit_instance_id="enemy-unit-1",
                occurrence_id="other-round",
                battle_round=2,
            ),
            _departure(
                rules_unit_instance_id="enemy-unit-1",
                occurrence_id="other-turn",
                active_player_id="player-b",
            ),
        ),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        active_player_id="player-a",
    )
    assert evidence["score_count"] == 0


def test_phase17n_step5d_embark_and_reserves_count_as_left_battlefield() -> None:
    setup = _punishment_setup()
    condemned = _condemned_selection(selected_ids=("enemy-unit-1",))
    embark = evaluate_departure_scoring_condition(
        condition_id=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
        progress=_progress(condemned),
        departures=(
            _departure(
                rules_unit_instance_id="enemy-unit-1",
                occurrence_id="embarked",
                removal_kind=BattlefieldRemovalKind.EMBARK,
            ),
        ),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        active_player_id="player-a",
    )
    reserves = evaluate_departure_scoring_condition(
        condition_id=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
        progress=_progress(condemned),
        departures=(
            _departure(
                rules_unit_instance_id="enemy-unit-1",
                occurrence_id="reserves",
                removal_kind=BattlefieldRemovalKind.INTO_RESERVES,
            ),
        ),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        active_player_id="player-a",
    )
    assert embark["score_count"] == 1
    assert reserves["score_count"] == 1


def test_phase17n_step5d_attached_unit_requires_every_component_to_leave() -> None:
    setup = _punishment_setup()
    condemned = _condemned_selection(selected_ids=("attached-enemy",))
    partial = evaluate_departure_scoring_condition(
        condition_id=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
        progress=_progress(condemned),
        departures=(
            _departure(
                rules_unit_instance_id="attached-enemy",
                occurrence_id="leader-only",
                component_ids=("attached-leader", "attached-bodyguard"),
                departed_ids=("attached-leader",),
            ),
        ),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        active_player_id="player-a",
    )
    complete = evaluate_departure_scoring_condition(
        condition_id=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
        progress=_progress(condemned),
        departures=(
            _departure(
                rules_unit_instance_id="attached-enemy",
                occurrence_id="leader",
                component_ids=("attached-leader", "attached-bodyguard"),
                departed_ids=("attached-leader",),
            ),
            _departure(
                rules_unit_instance_id="attached-enemy",
                occurrence_id="bodyguard",
                component_ids=("attached-leader", "attached-bodyguard"),
                departed_ids=("attached-bodyguard",),
            ),
        ),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        active_player_id="player-a",
    )
    assert partial["score_count"] == 0
    assert complete["score_count"] == 1


def test_phase17n_step5d_ignores_other_mission_round_and_player_selections() -> None:
    setup = _punishment_setup()
    evidence = evaluate_departure_scoring_condition(
        condition_id=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
        progress=_progress(
            _condemned_selection(
                selected_ids=("enemy-unit-1",),
                mission_id="primary-delaying-action",
                selection_index=1,
            ),
            _condemned_selection(
                selected_ids=("enemy-unit-1",),
                battle_round=2,
                selection_index=2,
            ),
            _condemned_selection(
                selected_ids=("enemy-unit-1",),
                owner_player_id="player-b",
                selection_index=3,
            ),
        ),
        departures=(_departure(rules_unit_instance_id="enemy-unit-1"),),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        active_player_id="player-a",
    )
    assert evidence["score_count"] == 0


def test_phase17n_step5d_rejects_duplicate_departure_ids() -> None:
    setup = _punishment_setup()
    departure = _departure(rules_unit_instance_id="enemy-unit-1")
    with pytest.raises(GameLifecycleError, match="must not duplicate departure_id"):
        evaluate_departure_scoring_condition(
            condition_id=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
            progress=_progress(_condemned_selection(selected_ids=("enemy-unit-1",))),
            departures=(departure, departure),
            mission_setup=setup,
            player_id="player-a",
            battle_round=1,
            active_player_id="player-a",
        )


def test_phase17n_step5d_rejects_condemned_selection_source_identity_drift() -> None:
    setup = _punishment_setup()
    selection = _condemned_selection(
        selected_ids=("enemy-unit-1",),
        source_rule_id="forged-punishment-source",
    )
    with pytest.raises(GameLifecycleError, match="source identity drifted"):
        evaluate_departure_scoring_condition(
            condition_id=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
            progress=_progress(selection),
            departures=(_departure(rules_unit_instance_id="enemy-unit-1"),),
            mission_setup=setup,
            player_id="player-a",
            battle_round=1,
            active_player_id="player-a",
        )


def test_phase17n_step5d_rejects_friendly_condemned_departure_owner() -> None:
    setup = _punishment_setup()
    with pytest.raises(GameLifecycleError, match="condemned departure owner drifted"):
        evaluate_departure_scoring_condition(
            condition_id=CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
            progress=_progress(_condemned_selection(selected_ids=("friendly-unit-1",))),
            departures=(
                _departure(
                    rules_unit_instance_id="friendly-unit-1",
                    owner_player_id="player-a",
                ),
            ),
            mission_setup=setup,
            player_id="player-a",
            battle_round=1,
            active_player_id="player-a",
        )


def test_phase17n_step5d_scores_condemned_departure_through_shared_boundary() -> None:
    state, record = _resolved_condemned_departure()
    score_primary_objective_control_boundary(
        state=state,
        record=record,
        end_of_battle=False,
    )
    awards = _primary_awards_by_condition(state, player_id="player-a")
    assert awards[CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN] == 5
    restored = GameState.from_payload(state.to_payload())
    assert restored.to_payload() == state.to_payload()
    assert restored.primary_scoring_state_evidence_records == (
        state.primary_scoring_state_evidence_records
    )


def test_phase17n_step5d_shared_boundary_scores_zero_without_departure() -> None:
    state, record = _resolved_condemned_departure(depart_selected=False)
    score_primary_objective_control_boundary(
        state=state,
        record=record,
        end_of_battle=False,
    )
    awards = _primary_awards_by_condition(state, player_id="player-a")
    assert CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN not in awards
    restored = GameState.from_payload(state.to_payload())
    assert restored.to_payload() == state.to_payload()


def _punishment_setup() -> MissionSetup:
    return phase17n_event_setup(
        layout_id="purge-the-foe-vs-disruption-layout-1",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="disruption",
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
) -> tuple[GameState, ObjectiveControlRecord]:
    state, decisions, request = phase17n_punishment_pending_fixture()
    option = next(
        candidate
        for candidate in request.options
        if PrimaryMissionChoiceData.from_payload(candidate.payload).selected_target_ids
    )
    GameLifecycle(decision_controller=decisions, state=state).submit_decision(
        DecisionResult.for_request(
            result_id="step5d-condemn-select-result",
            request=request,
            selected_option_id=option.option_id,
        )
    )
    _bind_force_dispositions(state)
    (selection,) = state.primary_mission_progress_state.condemned_selections
    selected_id = selection.selected_rules_unit_instance_ids[0]
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    if depart_selected:
        if state.battlefield_state is None:
            raise AssertionError("Step 5D fixture requires battlefield state.")
        placement = state.battlefield_state.unit_placement_by_id(selected_id)
        removed_model_ids = tuple(
            model_placement.model_instance_id for model_placement in placement.model_placements
        )
        state.battlefield_state = state.battlefield_state.with_removed_models(removed_model_ids)
        departure = record_primary_battlefield_departure(
            state=state,
            rules_unit_instance_id=selected_id,
            affected_component_unit_instance_ids=(selected_id,),
            departed_component_unit_instance_ids=(selected_id,),
            removed_model_instance_ids=removed_model_ids,
            removal_kind=BattlefieldRemovalKind.DESTROYED,
            occurrence_id="step5d-condemned-departure",
            source_id="step5d-condemned-departure-source",
        )
        if departure is None:
            raise AssertionError("Step 5D fixture requires battlefield-departure evidence.")
        record_primary_battlefield_departure_event(
            event_log=decisions.event_log,
            departure=departure,
        )
    record = state.record_objective_control_boundary(
        completed_phase=BattlePhase.FIGHT,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    return state, record


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
