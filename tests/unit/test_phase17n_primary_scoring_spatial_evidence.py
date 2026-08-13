from __future__ import annotations

import math
from dataclasses import replace

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
    muster_army,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    BattlefieldScenario,
    ModelPlacement,
    PlacedArmy,
    UnitPlacement,
)
from warhammer40k_core.engine.game_state import GameState
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
from warhammer40k_core.engine.primary_scoring_spatial_evidence import (
    PRIMARY_SCORING_NO_ENEMY_IN_OWN_TERRITORY_CONDITION,
    PRIMARY_SCORING_OPPONENT_TERRITORY_OBJECTIVE_CONDITION,
    PRIMARY_SCORING_SPATIAL_CONDITIONS,
    PRIMARY_SCORING_TABLE_QUARTER_CONDITIONS,
    TABLE_QUARTER_IDS,
    build_primary_scoring_spatial_evidence,
)
from warhammer40k_core.engine.reserves import (
    ReserveDestructionTimingPolicy,
    ReserveKind,
    ReserveState,
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
    _relocate_unit_placement(
        state,
        unit_instance_id="army-beta:enemy",
        anchor=(32.0, 7.0),
    )
    state.battle_round = 5
    state.active_player_id = "player-b"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    record = _authoritative_spatial_record(
        state,
        timing=ObjectiveControlTiming.TURN_END,
    )
    policies = mission_scoring_policies_from_setup(setup)
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

    awards = policies.primary_awards_from_objective_control(
        record=record,
        mission_setup=setup,
        turn_order=state.turn_order,
        turn_start_states=tuple(state.primary_objective_turn_start_states),
        terrain_trap_states=tuple(state.primary_terrain_trap_states),
        unit_destruction_states=tuple(state.primary_unit_destruction_states),
        spatial_evidence_by_player_id=(spatial_evidence,),
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
    transaction = state.award_victory_points(award)
    assert transaction.amount == 5
    assert transaction.scoring_timing == "end_of_battle"


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
                (
                    *(
                        model.model_instance_id
                        for model in player_a.unit_by_id("army-alpha:embarked").own_models
                    ),
                    *(
                        model.model_instance_id
                        for model in player_a.unit_by_id("army-alpha:destroyed").own_models
                    ),
                )
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
        battlefield_state=battlefield,
        mission_setup=resolved_mission_setup,
        reserve_states=[
            ReserveState.declared_before_battle(
                player_id="player-a",
                unit_instance_id="army-alpha:reserve",
                reserve_kind=ReserveKind.STRATEGIC_RESERVES,
                destruction_deadline_policy=(
                    ReserveDestructionTimingPolicy.chapter_approved_2026_27()
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
