"""Order 85 preflight: source-backed physical geometry reaches a real Charge facade."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from tests.charge_distance_helpers import add_modifier, request_from, select_targets
from tests.phase15c_fight_order_helpers import fight_config, unit_placement_at
from tests.setup_completion_helpers import (
    ensure_army_mustered_events_for_fixture,
    record_completed_command_occurrences_for_fixture,
    record_current_battlefield_placements_for_fixture,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.model_geometry_catalog import (
    GeometryEvidenceKind,
    GeometryMeasurementKind,
    GeometryRulesFootprintPolicy,
    GeometrySourceUnits,
    ModelFootprintDefinition,
    ModelFootprintKind,
    ModelFootprintPartDefinition,
    ModelGeometryCatalogRecord,
    ModelGeometrySourceEvidence,
    ModelHeightDefinition,
)
from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.army_mustering import muster_army
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.game_state import (
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.movement_proposals import ProposalKind
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage
from warhammer40k_core.engine.phases.charge import ChargeMoveProposal
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


def evidence(
    label: str, kind: GeometryMeasurementKind, dimension: str, value: float
) -> ModelGeometrySourceEvidence:
    return ModelGeometrySourceEvidence.from_source_dimensions(
        evidence_id=f"order85-fixture:{label}",
        evidence_kind=GeometryEvidenceKind.MANUAL_MEASUREMENT,
        measurement_kind=kind,
        source_id="order85-fixture:solid-cylinder",
        source_units=GeometrySourceUnits.INCHES,
        source_dimensions=((dimension, value),),
        document_reference="Synthetic fixture: solid cylinder, 8 inch body on 120 mm base",
    )


def footprint(label: str, source: ModelGeometrySourceEvidence) -> ModelFootprintDefinition:
    return ModelFootprintDefinition.single_part(
        footprint_id=f"order85-fixture:{label}",
        footprint_kind=ModelFootprintKind.CIRCULAR,
        part=ModelFootprintPartDefinition.from_evidence(
            part_id=label, footprint_kind=ModelFootprintKind.CIRCULAR, evidence=source
        ),
    )


def overhang_session(
    *,
    phase: BattlePhase = BattlePhase.CHARGE,
    start_y: float = 8.0,
    consolidate: bool = False,
    attached: bool = False,
    turn_owner: str = "player-a",
    second_enemy: bool = False,
) -> LocalGameSession:
    from warhammer40k_core.engine.list_validation import AttachmentDeclaration

    body = evidence("body", GeometryMeasurementKind.FOOTPRINT, "diameter", 8.0)
    base = evidence("base", GeometryMeasurementKind.SUPPORT_BASE, "diameter", 120.0 / 25.4)
    height = evidence("height", GeometryMeasurementKind.HEIGHT, "height", 2.0)
    record = ModelGeometryCatalogRecord(
        model_geometry_id="order85-overhang",
        model_profile_id="core-vehicle-monster",
        rules_footprint_policy=GeometryRulesFootprintPolicy.USE_SUPPORT_BASE,
        footprint=footprint("body", body),
        support_base=footprint("base", base),
        z_offset=None,
        height=ModelHeightDefinition.from_evidence(height),
        evidence=(body, base, height),
        source_ids=("order85-fixture:solid-cylinder",),
    )
    config = replace(
        fight_config(
            game_id="order85-preflight",
            alpha_unit_ids=("source", "bodyguard") if attached else ("source",),
            alpha_unit_specs={
                "bodyguard": ("core-intercessor-like-infantry", "core-intercessor-like", 5)
            }
            if attached
            else None,
            alpha_attachment_declarations=(AttachmentDeclaration("source", "bodyguard"),)
            if attached
            else (),
            enemy_unit_ids=("enemy", "second") if second_enemy else ("enemy",),
            datasheet_id="core-character-leader",
            model_profile_id="core-character-leader",
            model_count=1,
            enemy_unit_specs={"enemy": ("core-vehicle-monster", "core-vehicle-monster", 1)},
        ),
        model_geometries=(record,),
    )
    from warhammer40k_core.engine.mission_state_validation import (
        runtime_ruleset_descriptor_for_mission_setup,
    )

    config = replace(
        config,
        ruleset_descriptor=runtime_ruleset_descriptor_for_mission_setup(
            config.mission_setup, rules_overlay_ids=config.ruleset_descriptor.rules_overlay_ids
        ),
    )
    armies = tuple(
        muster_army(
            catalog=config.army_catalog, request=request, model_geometries=config.model_geometries
        )
        for request in config.army_muster_requests
    )
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="order85-battlefield",
        armies=armies,
        battlefield_width_inches=100,
        battlefield_depth_inches=100,
    )
    battlefield = scenario.battlefield_state
    for army, pose in zip(armies, (Pose.at(10, start_y), Pose.at(10, 14)), strict=True):
        for unit in army.units:
            unit_poses = (
                (
                    Pose.at(12, start_y),
                    Pose.at(12, start_y - 1.5),
                    Pose.at(10.5, start_y - 1.5),
                    Pose.at(9, start_y - 1.5),
                    Pose.at(9, start_y - 3),
                )
                if unit.unit_instance_id.endswith(":bodyguard")
                else (pose,)
            )
            if unit.unit_instance_id.endswith(":second"):
                unit_poses = (Pose.at(12, 9.2),)
            battlefield = battlefield.with_unit_placement(
                unit_placement_at(
                    unit, army_id=army.army_id, player_id=army.player_id, poses=unit_poses
                )
            )
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    state.record_battlefield_state(battlefield)
    for player_id in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=player_id,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=("assassination", "bring_it_down"),
            )
        )
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(phase)
    state.battle_round = 1
    state.active_player_id = turn_owner
    decisions = DecisionController()
    ensure_army_mustered_events_for_fixture(state, decisions=decisions)
    record_current_battlefield_placements_for_fixture(state, decisions=decisions)
    record_completed_command_occurrences_for_fixture(state, decisions=decisions, config=config)
    add_modifier(state, effect_id="order85-fixture-budget", kind="modify_dice_roll", delta=10)
    lifecycle = GameLifecycle.from_payload(
        cast(
            GameLifecyclePayload,
            {
                "config": config.to_payload(),
                "parameterized_movement_proposals": True,
                "state": state.to_payload(),
                "decisions": decisions.to_payload(),
                "reaction_queue": {"frames": []},
            },
        )
    )
    if consolidate:
        seed_consolidation(lifecycle)
    return LocalGameSession(lifecycle)


def overhang_charge_session() -> tuple[LocalGameSession, ChargeMoveProposal]:
    session = overhang_session()
    state = session.lifecycle.state
    assert state is not None
    armies = state.army_definitions
    request = request_from(session.advance_until_decision_or_terminal())
    request = request_from(
        session.submit_option(
            request_id=request.request_id,
            option_id="army-alpha:source",
            result_id="order85-select-source",
        )
    )
    request = select_targets(session, request, ("army-beta:enemy",), result_id="order85-targets")
    model_id = armies[0].units[0].own_models[0].model_instance_id
    source_radius = 20.0 / 25.4
    end = Pose.at(10, 14 - 4.0 - source_radius)
    proposal = ChargeMoveProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.CHARGE_MOVE,
        unit_instance_id="army-alpha:source",
        movement_phase_action="charge_move",
        movement_mode=MovementMode.CHARGE,
        charge_target_unit_instance_ids=("army-beta:enemy",),
        witness=PathWitness.for_paths(((model_id, (Pose.at(10, 8), end)),)),
    )
    return session, proposal


def seed_consolidation(lifecycle: GameLifecycle) -> None:
    """Canonical initial fixture at the start of the universal Consolidate step."""
    from warhammer40k_core.core.ruleset_descriptor import FightPhaseStepKind
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.fight_order import FightPhaseState, FightsFirstRegistry

    state = lifecycle.state
    assert state is not None
    assert state.active_player_id is not None
    policy = state.runtime_ruleset_descriptor().fight_policy
    started = FightPhaseState.start(
        battle_round=state.battle_round,
        active_player_id=state.active_player_id,
        policy=policy,
        engaged_at_fight_step_start_unit_ids=(),
        fights_first_registry=FightsFirstRegistry.from_state(state),
    )
    common = {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "active_player_id": state.active_player_id,
        "phase": "fight",
    }
    lifecycle.decision_controller.event_log.append(
        "fight_phase_started",
        validate_json_value(
            {
                **common,
                "phase_body_status": "fight_phase_started",
                "fight_phase_state": started.to_payload(),
            }
        ),
    )
    movement = started.pile_in_state
    assert movement is not None
    for player in state.player_ids:
        movement = movement.with_completed_player(
            next_player_id=state.player_ids[
                (state.player_ids.index(player) + 1) % len(state.player_ids)
            ]
        )
    state.fight_phase_state = (
        started.with_pile_in_state(movement)
        .with_ordering_band(
            ordering_band=policy.ordering_bands[-1], next_player_id=state.player_ids[-1]
        )
        .with_current_step(current_step=FightPhaseStepKind.CONSOLIDATE, policy=policy)
    )
    lifecycle.decision_controller.event_log.append(
        "fight_step_completed",
        validate_json_value(
            {
                **common,
                "phase_body_status": "fight_step_completed",
                "fight_phase_state": state.fight_phase_state.to_payload(),
            }
        ),
    )
