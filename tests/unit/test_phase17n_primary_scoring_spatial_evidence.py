from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import replace
from typing import Any, cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.battlefield_regions import BattlefieldRegionKind
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
    muster_army,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
    BattlefieldRuntimeState,
    BattlefieldScenario,
    ModelPlacement,
    PlacedArmy,
    UnitPlacement,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.destruction_provenance import (
    DestructionSourceKind,
    ModelDestructionAttribution,
)
from warhammer40k_core.engine.event_log import EventRecordPayload, JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.missions import mission_scoring_policies_from_setup
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.primary_battlefield_departure import (
    PrimaryBattlefieldDepartureState,
    primary_battlefield_departure_id,
)
from warhammer40k_core.engine.primary_destruction_evidence import (
    rules_unit_objective_proximity_witness,
)
from warhammer40k_core.engine.primary_historical_events import (
    PRIMARY_BATTLEFIELD_DEPARTURE_RECORDED_EVENT,
    PRIMARY_UNIT_DESTRUCTION_RECORDED_EVENT,
    record_new_primary_battlefield_departure_events,
    record_new_primary_turn_start_evidence_events,
    record_primary_unit_destruction_event,
)
from warhammer40k_core.engine.primary_scoring_spatial_evidence import (
    PRIMARY_SCORING_NO_ENEMY_IN_OWN_TERRITORY_CONDITION,
    PRIMARY_SCORING_OPPONENT_TERRITORY_OBJECTIVE_CONDITION,
    PRIMARY_SCORING_SPATIAL_CONDITIONS,
    PRIMARY_SCORING_TABLE_QUARTER_CONDITIONS,
    TABLE_QUARTER_IDS,
    PrimaryScoringSpatialEvidence,
    PrimaryTableQuarterUnitWitness,
    PrimaryTerritoryUnitWitness,
    build_primary_scoring_spatial_evidence,
    objective_control_record_hash,
)
from warhammer40k_core.engine.primary_scoring_state_evidence import (
    build_primary_scoring_state_evidence,
    record_primary_scoring_state_evidence,
)
from warhammer40k_core.engine.primary_turn_start_evidence import (
    record_primary_turn_start_evidence,
)
from warhammer40k_core.engine.primary_unit_destruction_tracking import (
    record_primary_destroyed_model_departures,
    record_primary_unit_destructions_for_destroyed_models,
)
from warhammer40k_core.engine.primary_victory_point_policy import (
    validate_primary_victory_point_transaction,
    validate_victory_point_ledger_policy,
)
from warhammer40k_core.engine.reserve_arrival_requirements import (
    reposition_destruction_policy,
)
from warhammer40k_core.engine.reserves import (
    ReserveKind,
    ReserveState,
)
from warhammer40k_core.engine.scoring import PrimaryUnitDestructionState, VictoryPointLedger
from warhammer40k_core.engine.starting_attached_units import (
    starting_attached_unit_records_for_army,
)
from warhammer40k_core.engine.transports import (
    TransportCapacityProfile,
    TransportCargoState,
)
from warhammer40k_core.engine.turn_cleanup import resolve_end_turn_cleanup
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)


@pytest.mark.parametrize(
    ("corruption", "expected_error"),
    [
        ("quarter_id", "quarter_id is unsupported"),
        ("unrequested_quarter", "unrequested table-quarter witnesses"),
        ("unrequested_territory", "unrequested territory witnesses"),
        ("unrequested_objectives", "unrequested territory objectives"),
        ("unsupported_condition", "requested_condition_ids are unsupported"),
        ("quarters_not_tuple", "table-quarter witnesses must be a tuple"),
        ("quarter_untyped", "table-quarter witnesses are invalid"),
        ("quarter_duplicate_unit", "rules units must have one table-quarter witness"),
        ("quarters_unsorted", "table-quarter witnesses must be sorted"),
        ("territories_not_tuple", "territory witnesses must be a tuple"),
        ("territory_untyped", "territory witnesses are invalid"),
        ("territory_duplicate_unit", "territory witness units must be unique"),
        ("territories_unsorted", "territory witnesses must be sorted"),
        ("conditions_not_tuple", "requested_condition_ids must be a tuple"),
        ("conditions_empty", "requested_condition_ids must not be empty"),
        ("conditions_duplicate", "requested_condition_ids must not contain duplicates"),
        ("conditions_unsorted", "requested_condition_ids must be sorted"),
        ("battle_round", "battle_round must be a positive integer"),
        ("timing", "timing must be ObjectiveControlTiming"),
    ],
)
def test_primary_spatial_evidence_constructor_fails_closed(
    corruption: str,
    expected_error: str,
) -> None:
    with pytest.raises(GameLifecycleError, match=expected_error):
        _run_primary_spatial_evidence_constructor_corruption(corruption)


def _run_primary_spatial_evidence_constructor_corruption(corruption: str) -> None:
    first_quarter = PrimaryTableQuarterUnitWitness(
        rules_unit_instance_id="rules-unit:quarter-a",
        quarter_id=TABLE_QUARTER_IDS[0],
        model_instance_ids=("model:quarter-a",),
    )
    second_quarter = PrimaryTableQuarterUnitWitness(
        rules_unit_instance_id="rules-unit:quarter-b",
        quarter_id=TABLE_QUARTER_IDS[1],
        model_instance_ids=("model:quarter-b",),
    )
    first_territory = PrimaryTerritoryUnitWitness(
        rules_unit_instance_id="rules-unit:territory-a",
        model_instance_ids=("model:territory-a",),
    )
    second_territory = PrimaryTerritoryUnitWitness(
        rules_unit_instance_id="rules-unit:territory-b",
        model_instance_ids=("model:territory-b",),
    )
    parameters: dict[str, Any] = {
        "game_id": "game:spatial-validation",
        "battlefield_id": "battlefield:spatial-validation",
        "battle_round": 2,
        "active_player_id": "player-a",
        "phase": BattlePhase.COMMAND.value,
        "timing": ObjectiveControlTiming.PHASE_END,
        "objective_control_record_id": "record:spatial-validation",
        "objective_control_record_hash": "hash:spatial-validation",
        "player_id": "player-a",
        "requested_condition_ids": tuple(sorted(PRIMARY_SCORING_SPATIAL_CONDITIONS)),
        "table_quarter_unit_witnesses": tuple(
            sorted(
                (first_quarter, second_quarter),
                key=lambda witness: (witness.quarter_id, witness.rules_unit_instance_id),
            )
        ),
        "enemy_units_wholly_within_own_territory": (
            first_territory,
            second_territory,
        ),
        "opponent_territory_objective_ids": ("objective:opponent",),
    }
    if corruption == "quarter_id":
        PrimaryTableQuarterUnitWitness(
            rules_unit_instance_id="rules-unit:quarter-invalid",
            quarter_id="quarter:invalid",
            model_instance_ids=("model:quarter-invalid",),
        )
    elif corruption == "unrequested_quarter":
        parameters["requested_condition_ids"] = (
            PRIMARY_SCORING_NO_ENEMY_IN_OWN_TERRITORY_CONDITION,
        )
        parameters["enemy_units_wholly_within_own_territory"] = ()
        parameters["opponent_territory_objective_ids"] = ()
    elif corruption == "unrequested_territory":
        parameters["requested_condition_ids"] = (
            sorted(PRIMARY_SCORING_TABLE_QUARTER_CONDITIONS)[0],
        )
        parameters["table_quarter_unit_witnesses"] = ()
        parameters["opponent_territory_objective_ids"] = ()
    elif corruption == "unrequested_objectives":
        parameters["requested_condition_ids"] = (
            sorted(PRIMARY_SCORING_TABLE_QUARTER_CONDITIONS)[0],
        )
        parameters["table_quarter_unit_witnesses"] = ()
        parameters["enemy_units_wholly_within_own_territory"] = ()
    elif corruption == "unsupported_condition":
        parameters["requested_condition_ids"] = ("condition:unsupported",)
        parameters["table_quarter_unit_witnesses"] = ()
        parameters["enemy_units_wholly_within_own_territory"] = ()
        parameters["opponent_territory_objective_ids"] = ()
    elif corruption == "quarters_not_tuple":
        parameters["table_quarter_unit_witnesses"] = []
    elif corruption == "quarter_untyped":
        parameters["table_quarter_unit_witnesses"] = (object(),)
    elif corruption == "quarter_duplicate_unit":
        parameters["table_quarter_unit_witnesses"] = tuple(
            sorted(
                (
                    first_quarter,
                    replace(first_quarter, quarter_id=TABLE_QUARTER_IDS[1]),
                ),
                key=lambda witness: (witness.quarter_id, witness.rules_unit_instance_id),
            )
        )
    elif corruption == "quarters_unsorted":
        parameters["table_quarter_unit_witnesses"] = tuple(
            sorted(
                (first_quarter, second_quarter),
                key=lambda witness: (witness.quarter_id, witness.rules_unit_instance_id),
                reverse=True,
            )
        )
    elif corruption == "territories_not_tuple":
        parameters["enemy_units_wholly_within_own_territory"] = []
    elif corruption == "territory_untyped":
        parameters["enemy_units_wholly_within_own_territory"] = (object(),)
    elif corruption == "territory_duplicate_unit":
        parameters["enemy_units_wholly_within_own_territory"] = (
            first_territory,
            replace(first_territory, model_instance_ids=("model:territory-c",)),
        )
    elif corruption == "territories_unsorted":
        parameters["enemy_units_wholly_within_own_territory"] = (
            second_territory,
            first_territory,
        )
    elif corruption == "conditions_not_tuple":
        parameters["requested_condition_ids"] = list(PRIMARY_SCORING_SPATIAL_CONDITIONS)
    elif corruption == "conditions_empty":
        parameters["requested_condition_ids"] = ()
        parameters["table_quarter_unit_witnesses"] = ()
        parameters["enemy_units_wholly_within_own_territory"] = ()
        parameters["opponent_territory_objective_ids"] = ()
    elif corruption == "conditions_duplicate":
        condition = sorted(PRIMARY_SCORING_SPATIAL_CONDITIONS)[0]
        parameters["requested_condition_ids"] = (condition, condition)
    elif corruption == "conditions_unsorted":
        parameters["requested_condition_ids"] = tuple(
            sorted(PRIMARY_SCORING_SPATIAL_CONDITIONS, reverse=True)
        )
    elif corruption == "battle_round":
        parameters["battle_round"] = 0
    elif corruption == "timing":
        parameters["timing"] = ObjectiveControlTiming.PHASE_END.value
    else:
        raise AssertionError(f"unsupported spatial constructor corruption: {corruption}")

    if corruption != "quarter_id":
        PrimaryScoringSpatialEvidence(**parameters)


def test_primary_spatial_evidence_public_validation_fails_closed() -> None:
    state = _spatial_evidence_state()
    record = _authoritative_spatial_record(state)

    with pytest.raises(GameLifecycleError, match="requires GameState"):
        build_primary_scoring_spatial_evidence(
            state=cast(GameState, object()),
            player_id="player-a",
            record=record,
            requested_condition_ids=tuple(sorted(PRIMARY_SCORING_SPATIAL_CONDITIONS)),
        )
    with pytest.raises(GameLifecycleError, match="requires an ObjectiveControlRecord"):
        build_primary_scoring_spatial_evidence(
            state=state,
            player_id="player-a",
            record=cast(ObjectiveControlRecord, object()),
            requested_condition_ids=tuple(sorted(PRIMARY_SCORING_SPATIAL_CONDITIONS)),
        )
    with pytest.raises(GameLifecycleError, match="player_id is not in this game"):
        build_primary_scoring_spatial_evidence(
            state=state,
            player_id="player-c",
            record=record,
            requested_condition_ids=tuple(sorted(PRIMARY_SCORING_SPATIAL_CONDITIONS)),
        )
    with pytest.raises(GameLifecycleError, match="record hash requires an ObjectiveControlRecord"):
        objective_control_record_hash(cast(ObjectiveControlRecord, object()))


@pytest.mark.parametrize(
    ("corruption", "expected_error"),
    [
        ("mission_missing", "requires mission and battlefield state"),
        ("placed_unavailable", "placed model marked unavailable"),
        ("alive_unplaced", "alive rules unit with no accounted placement"),
        ("mission_player", "player_id is not in MissionSetup"),
        ("territory_missing", "exactly one territory for each player role"),
        ("dimensions", "battlefield dimensions drifted from MissionSetup"),
        ("boundary_missing", "requires an active battle boundary"),
        ("record_drift", "ObjectiveControlRecord drifted from GameState"),
        ("record_unstored", "requires the authoritative ObjectiveControlRecord"),
    ],
)
def test_primary_spatial_evidence_state_integrity_fails_closed(
    corruption: str,
    expected_error: str,
) -> None:
    with pytest.raises(GameLifecycleError, match=expected_error):
        _run_primary_spatial_evidence_state_corruption(corruption)


def _run_primary_spatial_evidence_state_corruption(corruption: str) -> None:
    state = _spatial_evidence_state()
    record = _authoritative_spatial_record(state)
    battlefield = state.battlefield_state
    mission_setup = state.mission_setup
    if battlefield is None or mission_setup is None:
        raise AssertionError("spatial integrity test requires mission battlefield state")
    if corruption == "mission_missing":
        state.mission_setup = None
    elif corruption == "placed_unavailable":
        state.reserve_states.append(
            replace(
                state.reserve_states[0],
                unit_instance_id="army-alpha:east",
            )
        )
    elif corruption == "alive_unplaced":
        state.replace_battlefield_state(battlefield.without_unit_placement("army-alpha:east"))
    elif corruption == "mission_player":
        state.mission_setup = MissionSetup.from_mission_pack(
            mission_pack=warhammer_event_companion_2026_07_mission_pack(),
            mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-1",
            terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-1",
            attacker_player_id="player-c",
            attacker_force_disposition_id="purge-the-foe",
            defender_player_id="player-d",
            defender_force_disposition_id="take-and-hold",
        )
    elif corruption == "territory_missing":
        state.mission_setup = replace(
            mission_setup,
            battlefield_regions=tuple(
                region
                for region in mission_setup.battlefield_regions
                if region.region_kind is not BattlefieldRegionKind.TERRITORY
            ),
        )
    elif corruption == "dimensions":
        state.battlefield_state = replace(
            battlefield,
            battlefield_width_inches=battlefield.battlefield_width_inches + 1.0,
        )
    elif corruption == "boundary_missing":
        state.active_player_id = None
    elif corruption == "record_drift":
        record = replace(record, game_id="game:forged")
    elif corruption == "record_unstored":
        record = replace(record, record_id="record:forged")
    else:
        raise AssertionError(f"unsupported spatial state corruption: {corruption}")
    build_primary_scoring_spatial_evidence(
        state=state,
        player_id="player-a",
        record=record,
        requested_condition_ids=tuple(sorted(PRIMARY_SCORING_SPATIAL_CONDITIONS)),
    )


def test_primary_spatial_evidence_is_group_aware_exact_and_deterministic() -> None:
    state = _spatial_evidence_state()
    record = _authoritative_spatial_record(state)

    first = build_primary_scoring_spatial_evidence(
        state=state,
        player_id="player-a",
        record=record,
        requested_condition_ids=tuple(sorted(PRIMARY_SCORING_SPATIAL_CONDITIONS)),
    )
    second = build_primary_scoring_spatial_evidence(
        state=state,
        player_id="player-a",
        record=record,
        requested_condition_ids=tuple(sorted(PRIMARY_SCORING_SPATIAL_CONDITIONS)),
    )

    assert first == second
    assert {witness.quarter_id for witness in first.table_quarter_unit_witnesses} == set(
        TABLE_QUARTER_IDS
    )
    assert {witness.rules_unit_instance_id for witness in first.table_quarter_unit_witnesses} == {
        "attached-unit:army-alpha:body",
        "army-alpha:east",
        "army-alpha:south",
        "army-alpha:southeast",
    }
    attached_witness = next(
        witness
        for witness in first.table_quarter_unit_witnesses
        if witness.rules_unit_instance_id == "attached-unit:army-alpha:body"
    )
    assert len(attached_witness.model_instance_ids) == 6
    assert not {
        "army-alpha:body",
        "army-alpha:leader",
    }.intersection(witness.rules_unit_instance_id for witness in first.table_quarter_unit_witnesses)
    assert tuple(
        witness.rules_unit_instance_id for witness in first.enemy_units_wholly_within_own_territory
    ) == ("army-beta:enemy",)
    assert first.opponent_territory_objective_ids == (
        "take-and-hold-vs-purge-the-foe-layout-1-central-01",
        "take-and-hold-vs-purge-the-foe-layout-1-defender-home-01",
        "take-and-hold-vs-purge-the-foe-layout-1-expansion-01",
    )
    assert first.to_payload() == second.to_payload()

    near_model = _unit(state, "army-alpha:near").own_models[0]
    assert state.battlefield_state is not None
    near_pose = state.battlefield_state.model_placement_by_id(near_model.model_instance_id).pose
    assert math.hypot(near_pose.position.x - 22.0, near_pose.position.y - 30.0) > 6.0
    assert "army-alpha:near" not in {
        witness.rules_unit_instance_id for witness in first.table_quarter_unit_witnesses
    }
    assert {
        "army-alpha:reserve",
        "army-alpha:embarked",
        "army-alpha:destroyed",
    }.isdisjoint(witness.rules_unit_instance_id for witness in first.table_quarter_unit_witnesses)


def test_primary_spatial_evidence_rejects_partial_alive_rules_unit_placement() -> None:
    state = _spatial_evidence_state()
    assert state.battlefield_state is not None
    placement = state.battlefield_state.unit_placement_by_id("army-alpha:east")
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        placement.with_model_placements(placement.model_placements[:-1])
    )
    record = _authoritative_spatial_record(state)

    with pytest.raises(
        GameLifecycleError,
        match="requires every alive model in a rules unit to be placed",
    ):
        build_primary_scoring_spatial_evidence(
            state=state,
            player_id="player-a",
            record=record,
            requested_condition_ids=tuple(sorted(PRIMARY_SCORING_TABLE_QUARTER_CONDITIONS)),
        )


def test_primary_spatial_evidence_computes_only_requested_families() -> None:
    objective_state = _spatial_evidence_state()
    _make_unit_placement_partial(objective_state, unit_instance_id="army-alpha:east")
    objective_record = _authoritative_spatial_record(objective_state)

    objective_evidence = build_primary_scoring_spatial_evidence(
        state=objective_state,
        player_id="player-a",
        record=objective_record,
        requested_condition_ids=(PRIMARY_SCORING_OPPONENT_TERRITORY_OBJECTIVE_CONDITION,),
    )

    assert objective_evidence.opponent_territory_objective_ids
    assert objective_evidence.table_quarter_unit_witnesses == ()
    assert objective_evidence.enemy_units_wholly_within_own_territory == ()

    quarter_state = _spatial_evidence_state()
    _make_unit_placement_partial(quarter_state, unit_instance_id="army-beta:enemy")
    quarter_record = _authoritative_spatial_record(quarter_state)

    quarter_evidence = build_primary_scoring_spatial_evidence(
        state=quarter_state,
        player_id="player-a",
        record=quarter_record,
        requested_condition_ids=tuple(sorted(PRIMARY_SCORING_TABLE_QUARTER_CONDITIONS)),
    )

    assert quarter_evidence.table_quarter_unit_witnesses
    assert quarter_evidence.enemy_units_wholly_within_own_territory == ()
    assert quarter_evidence.opponent_territory_objective_ids == ()

    territory_state = _spatial_evidence_state()
    _make_unit_placement_partial(territory_state, unit_instance_id="army-alpha:east")
    territory_record = _authoritative_spatial_record(territory_state)

    territory_evidence = build_primary_scoring_spatial_evidence(
        state=territory_state,
        player_id="player-a",
        record=territory_record,
        requested_condition_ids=(PRIMARY_SCORING_NO_ENEMY_IN_OWN_TERRITORY_CONDITION,),
    )

    assert territory_evidence.enemy_units_wholly_within_own_territory
    assert territory_evidence.table_quarter_unit_witnesses == ()
    assert territory_evidence.opponent_territory_objective_ids == ()


def test_primary_spatial_evidence_excludes_removed_wounds_alive_reserve() -> None:
    state = _spatial_evidence_state()
    assert state.battlefield_state is not None
    reserve_state = state.reserve_states[0]
    reserve_unit = _unit(state, reserve_state.unit_instance_id)
    reserve_model_ids = tuple(sorted(model.model_instance_id for model in reserve_unit.own_models))
    assert all(model.is_alive for model in reserve_unit.own_models)

    state.reserve_states = [reserve_state.mark_destroyed(battle_round=state.battle_round)]
    state.battlefield_state = state.battlefield_state.with_unplaced_models_marked_removed(
        reserve_model_ids
    )
    record = _authoritative_spatial_record(state)

    evidence = build_primary_scoring_spatial_evidence(
        state=state,
        player_id="player-a",
        record=record,
        requested_condition_ids=tuple(sorted(PRIMARY_SCORING_TABLE_QUARTER_CONDITIONS)),
    )

    assert set(reserve_model_ids) <= set(state.battlefield_state.removed_model_ids)
    assert reserve_unit.unit_instance_id not in {
        witness.rules_unit_instance_id for witness in evidence.table_quarter_unit_witnesses
    }


def test_primary_spatial_evidence_counts_survivors_after_coherency_cleanup() -> None:
    state = _spatial_evidence_state(
        player_a_force_disposition_id="reconnaissance",
        player_b_force_disposition_id="take-and-hold",
        mission_setup=_mission_setup(
            mission_pool_entry_id="mission-take-and-hold-vs-reconnaissance-layout-1",
            terrain_layout_id="take-and-hold-vs-reconnaissance-layout-1",
            attacker_force_disposition_id="reconnaissance",
            defender_force_disposition_id="take-and-hold",
        ),
    )
    assert state.battlefield_state is not None
    east_placement = state.battlefield_state.unit_placement_by_id("army-alpha:east")
    isolated = replace(
        east_placement.model_placements[-1],
        pose=Pose.at(42.0, 57.0),
    )
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        east_placement.with_model_placements((*east_placement.model_placements[:-1], isolated))
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    cleanup, updated_battlefield = resolve_end_turn_cleanup(
        game_id=state.game_id,
        scenario=BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=state.battlefield_state,
        ),
        ruleset_descriptor=state.ruleset_descriptor_for_runtime_policy(),
        battle_round=state.battle_round,
        active_player_id="player-a",
        phase=BattlePhase.FIGHT,
    )
    state.battlefield_state = updated_battlefield
    state.end_turn_cleanup_states.append(cleanup)
    record = _authoritative_spatial_record(
        state,
        timing=ObjectiveControlTiming.TURN_END,
    )

    assert isolated.model_instance_id in state.battlefield_state.removed_model_ids
    assert next(
        model
        for model in _unit(state, "army-alpha:east").own_models
        if model.model_instance_id == isolated.model_instance_id
    ).is_alive
    evidence = build_primary_scoring_spatial_evidence(
        state=state,
        player_id="player-a",
        record=record,
        requested_condition_ids=tuple(sorted(PRIMARY_SCORING_TABLE_QUARTER_CONDITIONS)),
    )
    east_witness = next(
        witness
        for witness in evidence.table_quarter_unit_witnesses
        if witness.rules_unit_instance_id == "army-alpha:east"
    )
    assert east_witness.model_instance_ids == tuple(
        sorted(
            placement.model_instance_id
            for placement in east_placement.model_placements
            if placement.model_instance_id != isolated.model_instance_id
        )
    )


def test_reconnaissance_sweep_scores_exclusive_quarters_through_lifecycle() -> None:
    state = _spatial_evidence_state(
        player_a_force_disposition_id="reconnaissance",
        player_b_force_disposition_id="take-and-hold",
        mission_setup=_mission_setup(
            mission_pool_entry_id="mission-take-and-hold-vs-reconnaissance-layout-1",
            terrain_layout_id="take-and-hold-vs-reconnaissance-layout-1",
            attacker_force_disposition_id="reconnaissance",
            defender_force_disposition_id="take-and-hold",
        ),
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)

    state.advance_to_next_battle_phase()

    ledger = state.victory_point_ledger_for_player("player-a")
    assert ledger.victory_points == 6
    assert len(ledger.transactions) == 1
    metadata = ledger.transactions[0].metadata
    assert isinstance(metadata, dict)
    assert metadata["scoring_rule_id"] == "reconnaissance-sweep-four-quarters-turn-end"
    assert metadata["primary_scoring_achieved_rule_ids"] == [
        "reconnaissance-sweep-four-quarters-turn-end",
        "reconnaissance-sweep-three-quarters-turn-end",
    ]
    assert metadata["primary_scoring_suppressed_rule_ids"] == [
        "reconnaissance-sweep-three-quarters-turn-end"
    ]


def test_determined_acquisition_scores_exact_opponent_territory_through_lifecycle() -> None:
    state = _spatial_evidence_state(
        player_a_force_disposition_id="take-and-hold",
        player_b_force_disposition_id="disruption",
        mission_setup=_mission_setup(
            mission_pool_entry_id="mission-take-and-hold-vs-disruption-layout-1",
            terrain_layout_id="take-and-hold-vs-disruption-layout-1",
            attacker_force_disposition_id="take-and-hold",
            defender_force_disposition_id="disruption",
        ),
    )
    state.battle_round = 2
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.COMMAND)

    state.advance_to_next_battle_phase()

    ledger = state.victory_point_ledger_for_player("player-a")
    assert ledger.victory_points == 15
    amounts_by_rule_id = {
        metadata["scoring_rule_id"]: transaction.amount
        for transaction in ledger.transactions
        if isinstance((metadata := transaction.metadata), dict)
    }
    assert amounts_by_rule_id == {
        "determined-acquisition-each-objective": 9,
        "determined-acquisition-opponent-territory-bonus": 6,
    }
    territory_transaction = next(
        transaction
        for transaction in ledger.transactions
        if isinstance(transaction.metadata, dict)
        and transaction.metadata["scoring_rule_id"]
        == "determined-acquisition-opponent-territory-bonus"
    )
    assert isinstance(territory_transaction.metadata, dict)
    assert territory_transaction.metadata["opponent_territory_objective_ids"] == [
        "take-and-hold-vs-disruption-layout-1-defender-home-01",
        "take-and-hold-vs-disruption-layout-1-expansion-01",
    ]
    assert territory_transaction.metadata["primary_scoring_selected_rule_ids"] == [
        "determined-acquisition-each-objective",
        "determined-acquisition-opponent-territory-bonus",
    ]


def test_search_and_scour_scores_exact_end_of_battle_territory_evidence() -> None:
    setup = _mission_setup(
        mission_pool_entry_id="mission-reconnaissance-vs-priority-assets-layout-1",
        terrain_layout_id="reconnaissance-vs-priority-assets-layout-1",
        attacker_force_disposition_id="reconnaissance",
        defender_force_disposition_id="priority-assets",
    )
    state = _spatial_evidence_state(
        player_a_force_disposition_id="reconnaissance",
        player_b_force_disposition_id="priority-assets",
        mission_setup=setup,
    )
    state.battle_round = 5
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    ordinary_record = _controlled_objective_record(
        state,
        timing=ObjectiveControlTiming.TURN_END,
        controlled_objective_ids=(
            "reconnaissance-vs-priority-assets-layout-1-central-01",
            "reconnaissance-vs-priority-assets-layout-1-expansion-01",
            "reconnaissance-vs-priority-assets-layout-1-expansion-02",
        ),
    )
    policies = mission_scoring_policies_from_setup(setup)
    ordinary_awards = policies.primary_awards_from_objective_control(
        record=ordinary_record,
        authoritative_state=state,
    )
    assert {
        metadata["scoring_rule_id"]: award.amount
        for award in ordinary_awards
        if isinstance((metadata := award.metadata), dict)
    } == {
        "search-and-scour-central-objective-turn-end": 3,
        "search-and-scour-objective-control": 12,
    }
    _record_primary_scoring_evidence(
        state=state,
        record=ordinary_record,
        end_of_battle=False,
    )
    for ordinary_award in ordinary_awards:
        state.award_victory_points(ordinary_award)
    assert state.victory_point_total("player-a") == 15

    _relocate_unit_placement(
        state,
        unit_instance_id="army-beta:enemy",
        anchor=(32.0, 7.0),
    )
    state.turn_order = ("player-b", "player-a")
    record = ordinary_record
    required_conditions = policies.policy_for_player(
        "player-a"
    ).required_primary_spatial_conditions(
        record=record,
        end_of_battle=True,
    )
    spatial_evidence = build_primary_scoring_spatial_evidence(
        state=state,
        player_id="player-a",
        record=record,
        requested_condition_ids=required_conditions,
    )
    state_evidence = build_primary_scoring_state_evidence(
        state=state,
        record=record,
        end_of_battle=True,
    )
    awards = policies.policy_for_player("player-a").primary_awards_from_objective_control(
        record=record,
        mission_setup=setup,
        turn_order=state.turn_order,
        turn_start_states=tuple(state.primary_objective_turn_start_states),
        terrain_trap_states=tuple(state.primary_terrain_trap_states),
        unit_destruction_states=tuple(state.primary_unit_destruction_states),
        state_evidence=state_evidence,
        spatial_evidence=spatial_evidence,
        scoring_player_ids=("player-a",),
        end_of_battle=True,
    )

    assert spatial_evidence.enemy_units_wholly_within_own_territory == ()
    assert len(awards) == 1
    award = awards[0]
    assert award.amount == 5
    assert isinstance(award.metadata, dict)
    assert award.metadata["scoring_rule_id"] == (
        "search-and-scour-no-enemy-in-territory-end-battle"
    )
    assert award.metadata["own_territory_region_id"] == (
        "reconnaissance-vs-priority-assets-layout-1-attacker-territory"
    )
    _record_primary_scoring_evidence(
        state=state,
        record=record,
        end_of_battle=True,
    )
    ledger = state.victory_point_ledger_for_player("player-a")
    applied_amount, transaction_metadata = policies.capped_award_for_ledger(
        ledger=ledger,
        award=award,
        objective_control_records=tuple(state.objective_control_records),
        primary_scoring_state_evidence_records=tuple(state.primary_scoring_state_evidence_records),
        turn_order=state.turn_order,
        current_active_player_id=state.active_player_id,
    )
    updated_ledger, transaction = ledger.award(
        award,
        applied_amount=applied_amount,
        metadata=transaction_metadata,
    )
    assert transaction.amount == 5
    assert transaction.scoring_timing == "end_of_battle"
    assert updated_ledger.victory_points == 20
    restored_ledger = VictoryPointLedger.from_payload(updated_ledger.to_payload())
    assert restored_ledger == updated_ledger
    validate_victory_point_ledger_policy(
        policy=policies.policy_for_player("player-a"),
        ledger=restored_ledger,
        objective_control_records=tuple(state.objective_control_records),
        primary_scoring_state_evidence_records=tuple(state.primary_scoring_state_evidence_records),
        turn_order=state.turn_order,
    )
    assert isinstance(transaction.metadata, dict)
    invalid_transaction = replace(
        transaction,
        amount=100,
        metadata={
            **transaction.metadata,
            "vp_cap_audit": {
                "requested_amount": 5,
                "applied_amount": 100,
            },
        },
    )

    with pytest.raises(GameLifecycleError, match="applied_amount exceeds requested_amount"):
        validate_primary_victory_point_transaction(
            policy=policies.policy_for_player("player-a"),
            transaction=invalid_transaction,
            objective_control_records=tuple(state.objective_control_records),
            primary_scoring_state_evidence_records=tuple(
                state.primary_scoring_state_evidence_records
            ),
            turn_order=state.turn_order,
        )


def test_primary_restore_rejects_forged_round_two_end_of_battle_exemption() -> None:
    setup = _mission_setup(
        mission_pool_entry_id="mission-reconnaissance-vs-priority-assets-layout-1",
        terrain_layout_id="reconnaissance-vs-priority-assets-layout-1",
        attacker_force_disposition_id="reconnaissance",
        defender_force_disposition_id="priority-assets",
    )
    state = _spatial_evidence_state(
        player_a_force_disposition_id="reconnaissance",
        player_b_force_disposition_id="priority-assets",
        mission_setup=setup,
    )
    state.battle_round = 2
    record = _controlled_objective_record(
        state,
        timing=ObjectiveControlTiming.PHASE_END,
        controlled_objective_ids=("reconnaissance-vs-priority-assets-layout-1-expansion-01",),
    )
    policies = mission_scoring_policies_from_setup(setup)
    award = next(
        award
        for award in policies.primary_awards_from_objective_control(
            record=record,
            authoritative_state=state,
        )
        if isinstance(award.metadata, dict)
        and award.metadata["scoring_rule_id"] == "search-and-scour-objective-control"
    )
    _record_primary_scoring_evidence(
        state=state,
        record=record,
        end_of_battle=False,
    )
    state.award_victory_points(award)
    payload = state.to_payload()
    player_ledger = next(
        ledger for ledger in payload["victory_point_ledgers"] if ledger["player_id"] == "player-a"
    )
    player_ledger["transactions"][0]["scoring_timing"] = "end_of_battle"

    with pytest.raises(GameLifecycleError, match="scoring_timing drifted from its source rule"):
        GameState.from_payload(payload)


def test_primary_restore_rejects_more_than_fifteen_ordinary_vp_in_one_round() -> None:
    setup = _mission_setup(
        mission_pool_entry_id="mission-reconnaissance-vs-priority-assets-layout-1",
        terrain_layout_id="reconnaissance-vs-priority-assets-layout-1",
        attacker_force_disposition_id="reconnaissance",
        defender_force_disposition_id="priority-assets",
    )
    state = _spatial_evidence_state(
        player_a_force_disposition_id="reconnaissance",
        player_b_force_disposition_id="priority-assets",
        mission_setup=setup,
    )
    state.battle_round = 5
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    record = _controlled_objective_record(
        state,
        timing=ObjectiveControlTiming.TURN_END,
        controlled_objective_ids=tuple(
            marker.objective_marker_id
            for marker in setup.objective_markers
            if "attacker-home" not in marker.objective_marker_id
        ),
    )
    policies = mission_scoring_policies_from_setup(setup)
    awards = policies.primary_awards_from_objective_control(
        record=record,
        authoritative_state=state,
    )
    assert sum(award.amount for award in awards) == 19
    ledger = VictoryPointLedger.initial(player_id="player-a")
    for award in awards:
        ledger, _ = ledger.award(award)
    state.victory_point_ledgers = [
        ledger if stored.player_id == "player-a" else stored
        for stored in state.victory_point_ledgers
    ]
    _record_primary_scoring_evidence(
        state=state,
        record=record,
        end_of_battle=False,
    )

    with pytest.raises(
        GameLifecycleError,
        match="cap audit drifted from chronological ledger policy",
    ):
        GameState.from_payload(state.to_payload())


@pytest.fixture(scope="module")
def primary_historical_lifecycle_payload() -> GameLifecyclePayload:
    return _primary_historical_destruction_lifecycle_payload()


@pytest.mark.parametrize(
    ("corruption", "expected_error"),
    [
        (
            "departure_state_missing",
            "Primary battlefield departure recorded event requires a state payload",
        ),
        (
            "departure_id_missing",
            "Primary battlefield departure recorded event requires a departure ID",
        ),
        (
            "departure_payload_drift",
            "Primary battlefield departure recorded-event payload drift",
        ),
        (
            "departure_duplicate",
            "Primary battlefield departure requires exactly one recorded event",
        ),
        (
            "destruction_state_missing",
            "Primary destruction recorded state is malformed",
        ),
        (
            "destruction_id_missing",
            "Primary destruction recorded identity is malformed",
        ),
        (
            "destruction_payload_drift",
            "Primary destruction recorded-event payload drift",
        ),
        (
            "destruction_duplicate",
            "Primary destruction historical state requires exactly one recorded event",
        ),
    ],
)
def test_primary_historical_restore_rejects_recorded_event_graph_corruption(
    primary_historical_lifecycle_payload: GameLifecyclePayload,
    corruption: str,
    expected_error: str,
) -> None:
    payload = deepcopy(primary_historical_lifecycle_payload)
    _corrupt_primary_recorded_event_graph(payload=payload, corruption=corruption)

    with pytest.raises(GameLifecycleError, match=expected_error):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize(
    ("corruption", "expected_error"),
    [
        (
            "attribution",
            "Attributed Primary destruction attribution drifted from model_destroyed evidence",
        ),
        (
            "source_witness_missing",
            "model_destroyed evidence lacks a source witness",
        ),
        (
            "source_witness_none",
            "source witness drifted from model_destroyed evidence",
        ),
        (
            "destroyed_witness_missing",
            "model_destroyed evidence lacks a destroyed witness",
        ),
        (
            "model_malformed",
            "Primary destroyed departure model event is malformed",
        ),
        (
            "model_outside_starting_unit",
            "Primary destroyed departure model component drift",
        ),
        (
            "game",
            "Primary destroyed departure model timing drift",
        ),
        (
            "battle_round",
            "Primary destroyed departure model timing drift",
        ),
        (
            "active_player",
            "Primary destroyed departure model timing drift",
        ),
        (
            "target",
            "Primary destruction target drifted from model_destroyed evidence",
        ),
    ],
)
def test_primary_historical_restore_rejects_final_model_event_corruption(
    primary_historical_lifecycle_payload: GameLifecyclePayload,
    corruption: str,
    expected_error: str,
) -> None:
    payload = deepcopy(primary_historical_lifecycle_payload)
    _corrupt_final_model_destroyed_event(payload=payload, corruption=corruption)

    with pytest.raises(GameLifecycleError, match=expected_error):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize(
    ("removal_kind", "expected_error"),
    [
        (
            BattlefieldRemovalKind.TEMPORARILY_REMOVED,
            "Primary battlefield departure has no authoritative mutation provider",
        ),
        (
            BattlefieldRemovalKind.EMBARK,
            "Primary EMBARK departure requires one authoritative transport mutation event",
        ),
        (
            BattlefieldRemovalKind.INTO_RESERVES,
            "Primary INTO_RESERVES departure requires one authoritative reserve mutation event",
        ),
    ],
)
def test_primary_restore_rejects_departure_relabelled_without_route_provider(
    primary_historical_lifecycle_payload: GameLifecyclePayload,
    removal_kind: BattlefieldRemovalKind,
    expected_error: str,
) -> None:
    payload = deepcopy(primary_historical_lifecycle_payload)
    _relabel_primary_departure(payload=payload, removal_kind=removal_kind)

    with pytest.raises(GameLifecycleError, match=expected_error):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize(
    ("corruption", "expected_error"),
    [
        (
            "snapshot_missing_field",
            "PrimaryRulesUnitTurnStartSnapshot payload is missing required field: source_id",
        ),
        (
            "snapshot_unexpected_field",
            "PrimaryRulesUnitTurnStartSnapshot payload contains unexpected field: forged",
        ),
        (
            "snapshot_memberships_malformed",
            "PrimaryRulesUnitTurnStartSnapshot rules_unit_memberships must be a list",
        ),
        (
            "snapshot_round_malformed",
            "PrimaryRulesUnitTurnStartSnapshot battle_round must be an integer",
        ),
        (
            "snapshot_round_zero",
            "PrimaryRulesUnitTurnStartSnapshot battle_round must be at least 1",
        ),
        (
            "objective_witness_empty",
            "PrimaryObjectiveMarkerWitness requires at least one model",
        ),
        (
            "objective_witness_unevaluated",
            "PrimaryComponentTurnStartMembership objective witness references an unevaluated model",
        ),
        (
            "evaluated_model_duplicate",
            "PrimaryComponentTurnStartMembership evaluated_model_instance_ids must not "
            "contain duplicates",
        ),
        ("snapshot_game", "PrimaryRulesUnitTurnStartSnapshot game_id drift"),
        (
            "snapshot_player",
            "PrimaryRulesUnitTurnStartSnapshot player_id is not in this game",
        ),
        ("snapshot_id", "PrimaryRulesUnitTurnStartSnapshot snapshot_id drift"),
        ("snapshot_source", "PrimaryRulesUnitTurnStartSnapshot source_id drift"),
        (
            "snapshot_duplicate",
            "GameState primary rules-unit turn-start snapshots must be unique",
        ),
        (
            "snapshot_missing_component",
            "Primary rules-unit turn-start snapshot must contain every physical unit",
        ),
        (
            "snapshot_attached_grouping",
            "Primary rules-unit turn-start snapshot has invalid attached-unit grouping",
        ),
        (
            "snapshot_attached_identity_missing",
            "Primary rules-unit turn-start snapshot must preserve its attached identity",
        ),
        (
            "snapshot_independent_grouping",
            "Primary rules-unit turn-start snapshot has invalid independent-unit grouping",
        ),
        (
            "rules_membership_duplicate",
            "PrimaryRulesUnitTurnStartSnapshot rules-unit memberships must be unique",
        ),
        (
            "component_overlap",
            "PrimaryRulesUnitTurnStartSnapshot physical components must not overlap",
        ),
        (
            "component_duplicate",
            "PrimaryRulesUnitTurnStartMembership components must be unique",
        ),
        (
            "component_empty",
            "PrimaryRulesUnitTurnStartMembership requires at least one component",
        ),
        (
            "objective_witness_duplicate",
            "PrimaryComponentTurnStartMembership objective witnesses must be unique",
        ),
        (
            "snapshot_model_outside_component",
            "Primary turn-start snapshot references a model outside its component",
        ),
        (
            "snapshot_unknown_area",
            "Primary turn-start snapshot references an unknown logical terrain area",
        ),
        (
            "snapshot_unknown_objective",
            "Primary turn-start snapshot references an unknown objective marker",
        ),
        (
            "objective_game",
            "PrimaryObjectiveTurnStartState game_id drift",
        ),
        (
            "objective_player",
            "PrimaryObjectiveTurnStartState player_id is not in this game",
        ),
        ("objective_state_id", "PrimaryObjectiveTurnStartState state_id drift"),
        ("objective_source", "PrimaryObjectiveTurnStartState source_id drift"),
        (
            "objective_unknown_marker",
            "PrimaryObjectiveTurnStartState contains an unknown objective marker",
        ),
        (
            "objective_duplicate",
            "GameState primary turn-start states must be unique",
        ),
        (
            "turn_graph_missing_objective",
            "Primary turn-start objective and position evidence turn keys must match exactly",
        ),
        (
            "destruction_missing_snapshot",
            "Primary unit destruction requires exactly one matching turn-start position snapshot",
        ),
        (
            "destruction_terrain_drift",
            "Primary unit destruction terrain evidence does not match its turn snapshot",
        ),
        (
            "destruction_objective_drift",
            "Primary unit destruction objective evidence does not match its turn snapshot",
        ),
    ],
)
def test_primary_restore_rejects_turn_start_evidence_corruption(
    primary_historical_lifecycle_payload: GameLifecyclePayload,
    corruption: str,
    expected_error: str,
) -> None:
    payload = deepcopy(primary_historical_lifecycle_payload)
    _corrupt_primary_turn_start_evidence(payload=payload, corruption=corruption)

    with pytest.raises(GameLifecycleError, match=expected_error):
        GameLifecycle.from_payload(payload)


def _corrupt_primary_turn_start_evidence(
    *,
    payload: GameLifecyclePayload,
    corruption: str,
) -> None:
    state_payload = payload["state"]
    snapshot_rows = state_payload["primary_rules_unit_turn_start_snapshots"]
    objective_rows = state_payload["primary_objective_turn_start_states"]
    destruction_rows = state_payload["primary_unit_destruction_states"]
    assert len(snapshot_rows) == 1
    assert len(objective_rows) == 1
    assert len(destruction_rows) == 1
    snapshot = cast(dict[str, JsonValue], snapshot_rows[0])
    objective = cast(dict[str, JsonValue], objective_rows[0])
    destruction = cast(dict[str, JsonValue], destruction_rows[0])
    memberships = cast(list[dict[str, JsonValue]], snapshot["rules_unit_memberships"])

    if corruption == "snapshot_missing_field":
        snapshot.pop("source_id")
        return
    if corruption == "snapshot_unexpected_field":
        snapshot["forged"] = True
        return
    if corruption == "snapshot_memberships_malformed":
        snapshot["rules_unit_memberships"] = None
        return
    if corruption == "snapshot_round_malformed":
        snapshot["battle_round"] = "1"
        return
    if corruption == "snapshot_round_zero":
        snapshot["battle_round"] = 0
        return
    if corruption in {
        "objective_witness_empty",
        "objective_witness_unevaluated",
        "snapshot_unknown_objective",
    }:
        component = next(
            cast(dict[str, JsonValue], raw_component)
            for membership in memberships
            for raw_component in cast(list[JsonValue], membership["component_memberships"])
            if cast(dict[str, JsonValue], raw_component)["objective_marker_witnesses"]
        )
        witnesses = cast(
            list[dict[str, JsonValue]],
            component["objective_marker_witnesses"],
        )
        if corruption == "objective_witness_empty":
            witnesses[0]["model_instance_ids"] = []
        elif corruption == "objective_witness_unevaluated":
            witnesses[0]["model_instance_ids"] = ["forged-model-instance"]
        else:
            witnesses[0]["objective_marker_id"] = "objective:forged"
        return
    if corruption == "evaluated_model_duplicate":
        component = next(
            cast(dict[str, JsonValue], raw_component)
            for membership in memberships
            for raw_component in cast(list[JsonValue], membership["component_memberships"])
            if cast(dict[str, JsonValue], raw_component)["evaluated_model_instance_ids"]
        )
        model_ids = cast(list[JsonValue], component["evaluated_model_instance_ids"])
        model_ids.append(model_ids[0])
        return
    if corruption == "snapshot_game":
        snapshot["game_id"] = "game:forged"
        return
    if corruption == "snapshot_player":
        snapshot["active_player_id"] = "player:forged"
        return
    if corruption == "snapshot_id":
        snapshot["snapshot_id"] = "snapshot:forged"
        return
    if corruption == "snapshot_source":
        snapshot["source_id"] = "source:forged"
        return
    if corruption == "snapshot_duplicate":
        snapshot_rows.append(deepcopy(snapshot_rows[0]))
        return
    if corruption == "snapshot_missing_component":
        memberships.pop(0)
        return
    if corruption == "snapshot_attached_grouping":
        attached = next(
            membership
            for membership in memberships
            if cast(str, membership["rules_unit_instance_id"]).startswith("attached-unit:")
        )
        independent = next(
            membership
            for membership in memberships
            if membership["rules_unit_instance_id"] == "army-alpha:east"
        )
        attached_components = cast(list[JsonValue], attached["component_memberships"])
        independent_components = cast(list[JsonValue], independent["component_memberships"])
        attached_components[0], independent_components[0] = (
            independent_components[0],
            attached_components[0],
        )
        return
    if corruption == "snapshot_attached_identity_missing":
        attached = next(
            membership
            for membership in memberships
            if cast(str, membership["rules_unit_instance_id"]).startswith("attached-unit:")
        )
        attached["rules_unit_instance_id"] = "rules-unit:forged"
        return
    if corruption == "snapshot_independent_grouping":
        independent = next(
            membership
            for membership in memberships
            if membership["rules_unit_instance_id"] == "army-alpha:east"
        )
        independent["rules_unit_instance_id"] = "rules-unit:forged"
        return
    if corruption == "rules_membership_duplicate":
        memberships.append(deepcopy(memberships[0]))
        return
    if corruption == "component_overlap":
        first_components = cast(list[JsonValue], memberships[0]["component_memberships"])
        memberships[1]["component_memberships"] = [deepcopy(first_components[0])]
        return
    if corruption == "component_duplicate":
        components = cast(list[JsonValue], memberships[0]["component_memberships"])
        components.append(deepcopy(components[0]))
        return
    if corruption == "component_empty":
        memberships[0]["component_memberships"] = []
        return
    if corruption == "objective_witness_duplicate":
        component = next(
            cast(dict[str, JsonValue], raw_component)
            for membership in memberships
            for raw_component in cast(list[JsonValue], membership["component_memberships"])
            if cast(dict[str, JsonValue], raw_component)["objective_marker_witnesses"]
        )
        raw_witnesses = cast(list[JsonValue], component["objective_marker_witnesses"])
        raw_witnesses.append(deepcopy(raw_witnesses[0]))
        return
    if corruption == "snapshot_model_outside_component":
        target = next(
            membership
            for membership in memberships
            if membership["rules_unit_instance_id"] == "army-alpha:east"
        )
        source = next(
            membership
            for membership in memberships
            if membership["rules_unit_instance_id"] == "army-alpha:near"
        )
        target_component = cast(
            dict[str, JsonValue],
            cast(list[JsonValue], target["component_memberships"])[0],
        )
        source_component = cast(
            dict[str, JsonValue],
            cast(list[JsonValue], source["component_memberships"])[0],
        )
        target_models = cast(list[JsonValue], target_component["evaluated_model_instance_ids"])
        source_models = cast(list[JsonValue], source_component["evaluated_model_instance_ids"])
        target_models.append(source_models[0])
        return
    if corruption == "snapshot_unknown_area":
        membership = next(
            membership
            for membership in memberships
            if membership["rules_unit_instance_id"] == "army-alpha:east"
        )
        component = cast(
            dict[str, JsonValue],
            cast(list[JsonValue], membership["component_memberships"])[0],
        )
        cast(list[JsonValue], component["logical_terrain_area_ids"]).append("terrain-area:forged")
        return
    source_record = cast(dict[str, JsonValue], objective["source_objective_control_record"])
    if corruption == "objective_game":
        objective["game_id"] = "game:forged"
        source_record["game_id"] = "game:forged"
        return
    if corruption == "objective_player":
        objective["player_id"] = "player:forged"
        objective["active_player_id"] = "player:forged"
        objective["controlled_objective_ids"] = []
        source_record["active_player_id"] = "player:forged"
        return
    if corruption == "objective_state_id":
        objective["state_id"] = "state:forged"
        return
    if corruption == "objective_source":
        objective["source_id"] = "source:forged"
        return
    if corruption == "objective_unknown_marker":
        results = cast(list[JsonValue], source_record["results"])
        forged_result = deepcopy(cast(dict[str, JsonValue], results[0]))
        forged_result["objective_id"] = "objective:forged"
        results.append(forged_result)
        controlled_ids = cast(list[JsonValue], objective["controlled_objective_ids"])
        controlled_ids.append("objective:forged")
        return
    if corruption == "objective_duplicate":
        objective_rows.append(deepcopy(objective_rows[0]))
        return
    if corruption == "turn_graph_missing_objective":
        objective_rows.clear()
        return
    if corruption == "destruction_missing_snapshot":
        objective_rows.clear()
        snapshot_rows.clear()
        return
    if corruption == "destruction_terrain_drift":
        destruction["started_turn_terrain_feature_ids"] = []
        return
    if corruption == "destruction_objective_drift":
        destruction["started_turn_objective_marker_ids"] = []
        return
    raise AssertionError(f"unsupported turn-start evidence corruption: {corruption}")


def _primary_historical_destruction_lifecycle_payload() -> GameLifecyclePayload:
    state = _spatial_evidence_state()
    battlefield = state.battlefield_state
    if battlefield is None:
        raise AssertionError("historical evidence test requires battlefield state")
    reserve_state = state.reserve_states[0]
    reserve_unit = _unit(state, reserve_state.unit_instance_id)
    player_a = state.army_definition_for_player("player-a")
    if player_a is None:
        raise AssertionError("historical evidence test requires player-a army")
    state.replace_battlefield_state(
        battlefield.with_added_unit_placement(
            _unit_placement(player_a, reserve_unit, anchor=(50.0, 30.0))
        )
    )
    state.reserve_states.clear()

    decisions = DecisionController()
    lifecycle = GameLifecycle(state=state, decision_controller=decisions)
    objective_state_ids_before = tuple(
        value.state_id for value in state.primary_objective_turn_start_states
    )
    snapshot_ids_before = tuple(
        value.snapshot_id for value in state.primary_rules_unit_turn_start_snapshots
    )
    record_primary_turn_start_evidence(state=state)
    record_new_primary_turn_start_evidence_events(
        state=state,
        event_log=decisions.event_log,
        objective_state_ids_before=objective_state_ids_before,
        snapshot_ids_before=snapshot_ids_before,
    )

    attacker = _unit(state, "army-alpha:near")
    target = _unit(state, "army-beta:enemy")
    source_witness = rules_unit_objective_proximity_witness(
        state=state,
        rules_unit_instance_id=attacker.unit_instance_id,
    )
    attribution = ModelDestructionAttribution.for_non_attack(
        destroying_player_id="player-a",
        source_kind=DestructionSourceKind.ABILITY,
        source_rules_unit_instance_id=attacker.unit_instance_id,
        source_model_instance_id=attacker.own_models[0].model_instance_id,
    )
    destructions: tuple[PrimaryUnitDestructionState, ...] = ()
    tracking_rule_id = "core-rules:primary-unit-destruction-tracking"
    for model_id in target.own_model_ids():
        destroyed_witness = rules_unit_objective_proximity_witness(
            state=state,
            rules_unit_instance_id=target.unit_instance_id,
        )
        _set_model_wounds_remaining(
            state=state,
            unit_instance_id=target.unit_instance_id,
            model_instance_id=model_id,
            wounds_remaining=0,
        )
        current_battlefield = state.battlefield_state
        if current_battlefield is None:
            raise AssertionError("historical evidence test requires battlefield state")
        state.replace_battlefield_state(current_battlefield.with_removed_models((model_id,)))
        model_destroyed_event = decisions.event_log.append(
            "model_destroyed",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": BattlePhase.MOVEMENT.value,
                **attribution.to_payload(),
                "source_rules_unit_objective_proximity_witness": source_witness.to_payload(),
                "destroyed_rules_unit_objective_proximity_witness": (
                    destroyed_witness.to_payload()
                ),
                "target_unit_instance_id": target.unit_instance_id,
                "model_instance_id": model_id,
            },
        )
        departure_ids_before = tuple(
            value.departure_id for value in state.primary_battlefield_departure_states
        )
        record_primary_destroyed_model_departures(
            state=state,
            destroyed_model_instance_ids=(model_id,),
            source_id=f"{tracking_rule_id}:{model_destroyed_event.event_id}",
            occurrence_id=model_destroyed_event.event_id,
        )
        destructions = record_primary_unit_destructions_for_destroyed_models(
            state=state,
            destroyed_model_instance_ids=(model_id,),
            destruction_attribution=attribution,
            source_model_destroyed_event_id=model_destroyed_event.event_id,
            source_rules_unit_objective_proximity_witness=source_witness,
            destroyed_rules_unit_objective_proximity_witness=destroyed_witness,
            unattributed_cause=None,
            source_mutation_id=None,
            left_battlefield=False,
            source_id=f"{tracking_rule_id}:{model_destroyed_event.event_id}",
        )
        record_new_primary_battlefield_departure_events(
            state=state,
            event_log=decisions.event_log,
            departure_ids_before=departure_ids_before,
        )
    if len(destructions) != 1:
        raise AssertionError("historical evidence test requires one completed destruction")
    record_primary_unit_destruction_event(
        event_log=decisions.event_log,
        destruction=destructions[0],
    )
    payload = lifecycle.to_payload()
    if GameLifecycle.from_payload(deepcopy(payload)).to_payload() != payload:
        raise AssertionError("historical evidence lifecycle failed exact round trip")
    return payload


def _set_model_wounds_remaining(
    *,
    state: GameState,
    unit_instance_id: str,
    model_instance_id: str,
    wounds_remaining: int,
) -> None:
    unit = _unit(state, unit_instance_id)
    state.replace_army_definitions(
        [
            replace(
                army,
                units=tuple(
                    replace(
                        candidate,
                        own_models=tuple(
                            replace(model, wounds_remaining=wounds_remaining)
                            if model.model_instance_id == model_instance_id
                            else model
                            for model in candidate.own_models
                        ),
                    )
                    if candidate.unit_instance_id == unit.unit_instance_id
                    else candidate
                    for candidate in army.units
                ),
            )
            for army in state.army_definitions
        ]
    )


def _corrupt_primary_recorded_event_graph(
    *,
    payload: GameLifecyclePayload,
    corruption: str,
) -> None:
    event_type = (
        PRIMARY_BATTLEFIELD_DEPARTURE_RECORDED_EVENT
        if corruption.startswith("departure_")
        else PRIMARY_UNIT_DESTRUCTION_RECORDED_EVENT
    )
    event = _recorded_event_for_corruption(payload=payload, event_type=event_type)
    events = payload["decisions"]["event_log"]
    if corruption.endswith("_duplicate"):
        duplicate = deepcopy(event)
        duplicate["event_id"] = f"event-{len(events) + 1:06d}"
        events.append(duplicate)
        return
    event_payload = _event_payload(event)
    state_key = (
        "primary_battlefield_departure_state"
        if event_type == PRIMARY_BATTLEFIELD_DEPARTURE_RECORDED_EVENT
        else "primary_unit_destruction_state"
    )
    if corruption.endswith("_state_missing"):
        event_payload[state_key] = None
        return
    raw_state = event_payload.get(state_key)
    assert isinstance(raw_state, dict)
    state_payload = raw_state
    if corruption.endswith("_id_missing"):
        identity_key = (
            "departure_id"
            if event_type == PRIMARY_BATTLEFIELD_DEPARTURE_RECORDED_EVENT
            else "destruction_id"
        )
        state_payload.pop(identity_key)
        return
    if corruption.endswith("_payload_drift"):
        state_payload["phase"] = BattlePhase.FIGHT.value
        return
    raise AssertionError(f"unsupported historical recorded-event corruption: {corruption}")


def _corrupt_final_model_destroyed_event(
    *,
    payload: GameLifecyclePayload,
    corruption: str,
) -> None:
    destruction_rows = payload["state"]["primary_unit_destruction_states"]
    if len(destruction_rows) != 1:
        raise AssertionError("historical evidence test requires one destruction row")
    final_event_id = destruction_rows[0]["source_model_destroyed_event_id"]
    if type(final_event_id) is not str:
        raise AssertionError("historical evidence test requires an attributed destruction")
    event = next(
        value for value in payload["decisions"]["event_log"] if value["event_id"] == final_event_id
    )
    event_payload = _event_payload(event)
    if corruption == "attribution":
        event_payload["destroying_player_id"] = "player-b"
    elif corruption == "source_witness_missing":
        event_payload.pop("source_rules_unit_objective_proximity_witness")
    elif corruption == "source_witness_none":
        event_payload["source_rules_unit_objective_proximity_witness"] = None
    elif corruption == "destroyed_witness_missing":
        event_payload.pop("destroyed_rules_unit_objective_proximity_witness")
    elif corruption == "model_malformed":
        event_payload["model_instance_id"] = 17
    elif corruption == "model_outside_starting_unit":
        event_payload["model_instance_id"] = event_payload["source_model_instance_id"]
    elif corruption == "game":
        event_payload["game_id"] = "forged-game"
    elif corruption == "battle_round":
        event_payload["battle_round"] = 2
    elif corruption == "active_player":
        event_payload["active_player_id"] = "player-b"
    elif corruption == "target":
        event_payload["target_unit_instance_id"] = "army-alpha:near"
    else:
        raise AssertionError(f"unsupported model_destroyed corruption: {corruption}")


def _relabel_primary_departure(
    *,
    payload: GameLifecyclePayload,
    removal_kind: BattlefieldRemovalKind,
) -> None:
    departure_rows = payload["state"]["primary_battlefield_departure_states"]
    if not departure_rows:
        raise AssertionError("historical evidence test requires departure rows")
    original = PrimaryBattlefieldDepartureState.from_payload(departure_rows[0])
    updated = replace(
        original,
        departure_id=primary_battlefield_departure_id(
            game_id=original.game_id,
            rules_unit_instance_id=original.rules_unit_instance_id,
            affected_component_unit_instance_ids=(original.affected_component_unit_instance_ids),
            departed_component_unit_instance_ids=(original.departed_component_unit_instance_ids),
            removed_model_instance_ids=original.removed_model_instance_ids,
            battle_round=original.battle_round,
            active_player_id=original.active_player_id,
            phase=original.phase,
            removal_kind=removal_kind,
            occurrence_id=original.occurrence_id,
            source_id=original.source_id,
        ),
        removal_kind=removal_kind,
    )
    departure_rows[0] = updated.to_payload()
    recorded_event = _recorded_departure_event(
        payload=payload,
        departure_id=original.departure_id,
    )
    _event_payload(recorded_event)["primary_battlefield_departure_state"] = cast(
        dict[str, JsonValue], updated.to_payload()
    )
    linked_destructions = tuple(
        destruction
        for destruction in payload["state"]["primary_unit_destruction_states"]
        if original.departure_id in destruction["source_battlefield_departure_ids"]
    )
    if len(linked_destructions) != 1:
        raise AssertionError("historical evidence test requires one linked destruction")
    linked_destruction = linked_destructions[0]
    linked_destruction["source_battlefield_departure_ids"] = [
        updated.departure_id if departure_id == original.departure_id else departure_id
        for departure_id in linked_destruction["source_battlefield_departure_ids"]
    ]
    destruction_event = _recorded_event_for_corruption(
        payload=payload,
        event_type=PRIMARY_UNIT_DESTRUCTION_RECORDED_EVENT,
    )
    event_destruction = _event_payload(destruction_event).get("primary_unit_destruction_state")
    if not isinstance(event_destruction, dict):
        raise TypeError("historical evidence test requires a recorded destruction payload")
    event_departure_ids = event_destruction.get("source_battlefield_departure_ids")
    if not isinstance(event_departure_ids, list):
        raise TypeError("historical evidence test requires destruction departure IDs")
    event_destruction["source_battlefield_departure_ids"] = [
        updated.departure_id if departure_id == original.departure_id else departure_id
        for departure_id in event_departure_ids
    ]


def _recorded_event_for_corruption(
    *,
    payload: GameLifecyclePayload,
    event_type: str,
) -> EventRecordPayload:
    matches = tuple(
        event for event in payload["decisions"]["event_log"] if event["event_type"] == event_type
    )
    if not matches:
        raise AssertionError(f"historical evidence test requires a {event_type} event")
    if event_type == PRIMARY_UNIT_DESTRUCTION_RECORDED_EVENT and len(matches) != 1:
        raise AssertionError("historical evidence test requires one destruction event")
    return matches[-1]


def _recorded_departure_event(
    *,
    payload: GameLifecyclePayload,
    departure_id: str,
) -> EventRecordPayload:
    matches: list[EventRecordPayload] = []
    for event in payload["decisions"]["event_log"]:
        if event["event_type"] != PRIMARY_BATTLEFIELD_DEPARTURE_RECORDED_EVENT:
            continue
        recorded_payload = _event_payload(event)
        raw_departure = recorded_payload.get("primary_battlefield_departure_state")
        if isinstance(raw_departure, dict) and raw_departure.get("departure_id") == departure_id:
            matches.append(event)
    if len(matches) != 1:
        raise AssertionError("historical evidence test requires one matching departure event")
    return matches[0]


def _event_payload(event: EventRecordPayload) -> dict[str, JsonValue]:
    assert isinstance(event["payload"], dict)
    return event["payload"]


def _spatial_evidence_state(
    *,
    player_a_force_disposition_id: str = "purge-the-foe",
    player_b_force_disposition_id: str = "take-and-hold",
    mission_setup: MissionSetup | None = None,
) -> GameState:
    catalog = _catalog()
    player_a = muster_army(
        catalog=catalog,
        request=_muster_request(
            catalog=catalog,
            player_id="player-a",
            army_id="army-alpha",
            force_disposition_id=player_a_force_disposition_id,
            unit_selections=(
                _infantry_selection("body"),
                _character_selection("leader"),
                _infantry_selection("east"),
                _infantry_selection("south"),
                _infantry_selection("southeast"),
                _character_selection("near"),
                _infantry_selection("reserve"),
                _infantry_selection("embarked"),
                _character_selection("destroyed"),
                _transport_selection("transport"),
            ),
            attachment_declarations=(
                AttachmentDeclaration(
                    source_unit_selection_id="leader",
                    bodyguard_unit_selection_id="body",
                ),
            ),
        ),
    )
    player_a = _with_destroyed_unit(player_a, unit_instance_id="army-alpha:destroyed")
    player_b = muster_army(
        catalog=catalog,
        request=_muster_request(
            catalog=catalog,
            player_id="player-b",
            army_id="army-beta",
            force_disposition_id=player_b_force_disposition_id,
            unit_selections=(_infantry_selection("enemy"),),
        ),
    )
    resolved_mission_setup = _mission_setup() if mission_setup is None else mission_setup
    battlefield = BattlefieldRuntimeState(
        battlefield_id="phase17n-spatial-evidence-battlefield",
        battlefield_width_inches=resolved_mission_setup.battlefield_width_inches,
        battlefield_depth_inches=resolved_mission_setup.battlefield_depth_inches,
        terrain_features=resolved_mission_setup.terrain_features,
        placed_armies=(
            PlacedArmy(
                army_id=player_a.army_id,
                player_id=player_a.player_id,
                unit_placements=tuple(
                    _unit_placement(player_a, unit, anchor=_PLAYER_A_ANCHORS[unit.unit_instance_id])
                    for unit in player_a.units
                    if unit.unit_instance_id in _PLAYER_A_ANCHORS
                ),
            ),
            PlacedArmy(
                army_id=player_b.army_id,
                player_id=player_b.player_id,
                unit_placements=(_unit_placement(player_b, player_b.units[0], anchor=(8.0, 48.0)),),
            ),
        ),
        removed_model_ids=tuple(
            sorted(
                model.model_instance_id
                for model in player_a.unit_by_id("army-alpha:destroyed").own_models
            )
        ),
    )
    descriptor = RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
        descriptor_version="core-v2-phase17n-spatial-evidence-test"
    )
    return GameState(
        game_id="phase17n-spatial-evidence-game",
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(descriptor.setup_sequence.steps),
        battle_phase_sequence=tuple(descriptor.battle_phase_sequence.phases),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
        setup_step_index=None,
        battle_phase_index=0,
        battle_round=1,
        active_player_id="player-a",
        army_definitions=[player_a, player_b],
        starting_attached_unit_records=[
            record
            for army in (player_a, player_b)
            for record in starting_attached_unit_records_for_army(army)
        ],
        battlefield_state=battlefield,
        mission_setup=resolved_mission_setup,
        reserve_states=[
            ReserveState.declared_before_battle(
                player_id="player-a",
                unit_instance_id="army-alpha:reserve",
                reserve_kind=ReserveKind.STRATEGIC_RESERVES,
                destruction_deadline_policy=reposition_destruction_policy(
                    mission_setup=resolved_mission_setup,
                    destruction_deadline_policy=None,
                ),
            )
        ],
        transport_cargo_states=[
            TransportCargoState(
                player_id="player-a",
                transport_unit_instance_id="army-alpha:transport",
                capacity_profile=TransportCapacityProfile(
                    transport_datasheet_id="core-transport",
                    max_model_count=10,
                    allowed_keywords=("INFANTRY",),
                ),
                embarked_unit_instance_ids=("army-alpha:embarked",),
            )
        ],
    )


def _authoritative_spatial_record(
    state: GameState,
    *,
    timing: ObjectiveControlTiming = ObjectiveControlTiming.PHASE_END,
) -> ObjectiveControlRecord:
    phase = state.current_battle_phase
    if phase is None:
        raise AssertionError("spatial evidence test requires a current phase")
    return state.record_objective_control_boundary(
        completed_phase=phase,
        timing=timing,
        runtime_modifier_registry=None,
    )


def _controlled_objective_record(
    state: GameState,
    *,
    timing: ObjectiveControlTiming,
    controlled_objective_ids: tuple[str, ...],
) -> ObjectiveControlRecord:
    if state.mission_setup is None or state.battlefield_state is None:
        raise AssertionError("controlled-objective test record requires mission battlefield state")
    phase = state.current_battle_phase
    if phase is None or state.active_player_id is None:
        raise AssertionError("controlled-objective test record requires an active phase")
    controlled_ids = frozenset(controlled_objective_ids)
    known_ids = frozenset(
        marker.objective_marker_id for marker in state.mission_setup.objective_markers
    )
    if not controlled_ids <= known_ids:
        raise AssertionError("controlled-objective test record contains an unknown objective")
    controlling_unit_ids = (
        "army-alpha:east",
        "army-alpha:south",
        "army-alpha:southeast",
        "army-alpha:near",
    )
    if len(controlled_ids) > len(controlling_unit_ids):
        raise AssertionError("controlled-objective test record needs more placed units")
    player_a_placement_ids = tuple(
        placement.unit_instance_id
        for army in state.battlefield_state.placed_armies
        if army.player_id == "player-a"
        for placement in army.unit_placements
    )
    for unit_instance_id in player_a_placement_ids:
        _relocate_unit_placement(
            state,
            unit_instance_id=unit_instance_id,
            anchor=(21.0, 56.0),
        )
    markers_by_id = {
        marker.objective_marker_id: marker for marker in state.mission_setup.objective_markers
    }
    for unit_instance_id, objective_id in zip(
        controlling_unit_ids[: len(controlled_objective_ids)],
        controlled_objective_ids,
        strict=True,
    ):
        marker = markers_by_id[objective_id]
        _relocate_unit_placement(
            state,
            unit_instance_id=unit_instance_id,
            anchor=(marker.x_inches, marker.y_inches),
        )
    record = state.record_objective_control_boundary(
        completed_phase=phase,
        timing=timing,
        runtime_modifier_registry=None,
    )
    player_a_controlled_ids = frozenset(
        result.objective_id
        for result in record.results
        if result.controlled_by_player_id == "player-a"
    )
    if player_a_controlled_ids != controlled_ids:
        raise AssertionError("controlled-objective test placement did not resolve exact control")
    return record


def _catalog() -> ArmyCatalog:
    source = ArmyCatalog.phase9a_canonical_content_pack()
    return replace(
        source,
        detachments=tuple(
            replace(
                detachment,
                force_disposition_ids=(
                    "disruption",
                    "priority-assets",
                    "purge-the-foe",
                    "reconnaissance",
                    "take-and-hold",
                ),
            )
            if detachment.detachment_id == "core-combined-arms"
            else detachment
            for detachment in source.detachments
        ),
    )


def _muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    force_disposition_id: str,
    unit_selections: tuple[UnitMusterSelection, ...],
    attachment_declarations: tuple[AttachmentDeclaration, ...] = (),
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        force_disposition_id=force_disposition_id,
        unit_selections=unit_selections,
        attachment_declarations=attachment_declarations,
    )


def _infantry_selection(unit_selection_id: str) -> UnitMusterSelection:
    return _unit_selection(
        unit_selection_id=unit_selection_id,
        datasheet_id="core-intercessor-like-infantry",
        model_profile_id="core-intercessor-like",
        model_count=5,
    )


def _character_selection(unit_selection_id: str) -> UnitMusterSelection:
    return _unit_selection(
        unit_selection_id=unit_selection_id,
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
    )


def _transport_selection(unit_selection_id: str) -> UnitMusterSelection:
    return _unit_selection(
        unit_selection_id=unit_selection_id,
        datasheet_id="core-transport",
        model_profile_id="core-transport",
        model_count=1,
    )


def _unit_selection(
    *,
    unit_selection_id: str,
    datasheet_id: str,
    model_profile_id: str,
    model_count: int,
) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id=datasheet_id,
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id=model_profile_id,
                model_count=model_count,
            ),
        ),
    )


def _with_destroyed_unit(
    army: ArmyDefinition,
    *,
    unit_instance_id: str,
) -> ArmyDefinition:
    return replace(
        army,
        units=tuple(
            replace(
                unit,
                own_models=tuple(replace(model, wounds_remaining=0) for model in unit.own_models),
            )
            if unit.unit_instance_id == unit_instance_id
            else unit
            for unit in army.units
        ),
    )


def _record_primary_scoring_evidence(
    *,
    state: GameState,
    record: ObjectiveControlRecord,
    end_of_battle: bool,
) -> None:
    record_primary_scoring_state_evidence(
        state=state,
        evidence=build_primary_scoring_state_evidence(
            state=state,
            record=record,
            end_of_battle=end_of_battle,
        ),
    )


def _mission_setup(
    *,
    mission_pool_entry_id: str = "mission-take-and-hold-vs-purge-the-foe-layout-1",
    terrain_layout_id: str = "take-and-hold-vs-purge-the-foe-layout-1",
    attacker_force_disposition_id: str = "purge-the-foe",
    defender_force_disposition_id: str = "take-and-hold",
) -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id=mission_pool_entry_id,
        terrain_layout_id=terrain_layout_id,
        attacker_player_id="player-a",
        attacker_force_disposition_id=attacker_force_disposition_id,
        defender_player_id="player-b",
        defender_force_disposition_id=defender_force_disposition_id,
    )


def _unit_placement(
    army: ArmyDefinition,
    unit: UnitInstance,
    *,
    anchor: tuple[float, float],
) -> UnitPlacement:
    runtime_unit = army.unit_by_id(unit.unit_instance_id)
    x_inches, y_inches = anchor
    return UnitPlacement(
        army_id=army.army_id,
        player_id=army.player_id,
        unit_instance_id=runtime_unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_instance_id=runtime_unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=Pose.at(
                    x_inches + ((index % 3) * 1.5),
                    y_inches + ((index // 3) * 1.5),
                ),
            )
            for index, model in enumerate(runtime_unit.own_models)
        ),
    )


def _unit(state: GameState, unit_instance_id: str) -> UnitInstance:
    return next(
        unit
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == unit_instance_id
    )


def _make_unit_placement_partial(state: GameState, *, unit_instance_id: str) -> None:
    if state.battlefield_state is None:
        raise AssertionError("spatial evidence test requires battlefield state")
    placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        placement.with_model_placements(placement.model_placements[:-1])
    )


def _relocate_unit_placement(
    state: GameState,
    *,
    unit_instance_id: str,
    anchor: tuple[float, float],
) -> None:
    if state.battlefield_state is None:
        raise AssertionError("spatial evidence test requires battlefield state")
    placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    x_inches, y_inches = anchor
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        placement.with_model_placements(
            tuple(
                replace(
                    model_placement,
                    pose=Pose.at(
                        x_inches + ((index % 3) * 1.5),
                        y_inches + ((index // 3) * 1.5),
                    ),
                )
                for index, model_placement in enumerate(placement.model_placements)
            )
        )
    )


_PLAYER_A_ANCHORS = {
    "army-alpha:body": (6.0, 48.0),
    "army-alpha:leader": (13.0, 48.0),
    "army-alpha:east": (34.0, 48.0),
    "army-alpha:south": (6.0, 12.0),
    "army-alpha:southeast": (34.0, 12.0),
    "army-alpha:near": (26.4, 34.4),
    "army-alpha:transport": (22.0, 30.0),
}
