"""P02K keeps dash-M immobility separate from a numeric-zero movement budget."""

import json
from dataclasses import replace

import pytest
from tests.absent_movement_helpers import movement_catalog, movement_session, movement_witness
from tests.core_clause_evidence_helpers import assert_persistence_viewers_replay
from tests.lethal_hits_helpers import complete_attack, reach_lethal_choice
from tests.phase15c_fight_order_helpers import fight_lifecycle
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.dice import DiceRollResult, DiceRollState
from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    AttackProfile,
    DamageProfile,
    WeaponKeyword,
)
from warhammer40k_core.engine.advance_roll import AdvanceRollRequest, AdvanceRollResult
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    ModelDisplacementKind,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.model_movement_permission import model_movement_path_context
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalPayload,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.phases.movement import resolve_advance_move, resolve_normal_move
from warhammer40k_core.engine.reaction_windows import ReactionWindow, ReactionWindowKind
from warhammer40k_core.engine.triggered_movement import (
    TriggeredMovementDescriptor,
    TriggeredMovementHandler,
    TriggeredMovementKind,
)
from warhammer40k_core.engine.triggered_movement_resolution import resolve_triggered_movement
from warhammer40k_core.geometry.movement_reachability import (
    MovementGoal,
    MovementReachabilityQuery,
    MovementReachabilityStatus,
    movement_reachability,
)
from warhammer40k_core.geometry.pathing import PathValidationContext, PathWitness
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("replacement", [False, True])
@pytest.mark.parametrize("kind", ["translate", "return", "rotate"])
def test_absent_movement_cannot_advance_or_use_a_normal_move_bonus(
    replacement: bool, kind: str
) -> None:
    movement = (
        CharacteristicValue.replacement_dash(Characteristic.MOVEMENT)
        if replacement
        else CharacteristicValue.source_dash(Characteristic.MOVEMENT)
    )
    session = movement_session(movement)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions), battlefield_state=state.battlefield_state
    )
    placement = state.battlefield_state.unit_placement_by_id("army-alpha:mover")
    witness = movement_witness(session, kind=kind)
    request = AdvanceRollRequest.for_unit(
        request_id="order115:advance",
        game_id=state.game_id,
        battle_round=1,
        player_id="player-a",
        unit_instance_id=placement.unit_instance_id,
    )
    roll = AdvanceRollResult.from_roll_state(
        request=request,
        roll_state=DiceRollState.from_result(
            DiceRollResult.from_values(
                roll_id="order115:roll", spec=request.spec, values=(3,), source="fixed"
            )
        ),
    )
    for result in (
        resolve_normal_move(
            scenario=scenario,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            unit_placement=placement,
            path_witness=witness,
            movement_bonus_inches=3,
        ),
        resolve_advance_move(
            scenario=scenario,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            unit_placement=placement,
            path_witness=witness,
            advance_roll=roll,
        ),
    ):
        assert not result.is_valid
        assert all(
            row.violations[0].violation_code == "model_pose_fixed"
            for row in result.path_validation_results
        )


@pytest.mark.parametrize("absent", [False, True])
@pytest.mark.parametrize("kind", ["translate", "return", "rotate", "hold"])
def test_fixed_distance_reaction_preserves_per_model_absence(absent: bool, kind: str) -> None:
    movement = (
        CharacteristicValue.source_dash(Characteristic.MOVEMENT)
        if absent
        else CharacteristicValue.from_raw(Characteristic.MOVEMENT, 0)
    )
    session = movement_session(movement)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    before = state.to_payload()
    resolution = resolve_triggered_movement(
        scenario=BattlefieldScenario(
            armies=tuple(state.army_definitions), battlefield_state=state.battlefield_state
        ),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=state.battlefield_state.unit_placement_by_id("army-alpha:mover"),
        descriptor=TriggeredMovementDescriptor(
            movement_kind=TriggeredMovementKind.TRIGGERED,
            source_rule_id="test:order115:reactive-movement",
            trigger_timing=ReactionWindow(
                phase=BattlePhase.MOVEMENT,
                window_kind=ReactionWindowKind.RULE_TRIGGER,
                source_step=None,
                source_event_id=None,
            ),
            max_distance_inches=3,
        ),
        path_witness=movement_witness(session, kind=kind),
        battle_round=1,
        turn_player_id="player-a",
    )
    assert resolution.is_valid is (not absent or kind == "hold")
    if absent and kind != "hold":
        assert all(
            row.violations[0].violation_code == "model_pose_fixed"
            for row in resolution.path_validation_results
        )
    assert state.to_payload() == before


@pytest.mark.parametrize("absent", [False, True])
def test_facade_advance_retry_completion_restore_fork_and_replay(absent: bool) -> None:
    session = movement_session(
        CharacteristicValue.source_dash(Characteristic.MOVEMENT)
        if absent
        else CharacteristicValue.from_raw(Characteristic.MOVEMENT, 0)
    )
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    before = state.battlefield_state
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id, result_id="select", option_id="army-alpha:mover"
    )
    request = pending_request(session)
    session.submit_option(request_id=request.request_id, result_id="advance", option_id="advance")
    request = pending_request(session)
    assert request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    assert_persistence_viewers_replay(session)
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)

    def submit(kind: str, result_id: str, *, invalid: bool = False) -> None:
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=result_id,
            payload=validate_json_value(
                MovementProposalPayload(
                    proposal_request_id=request.request_id,
                    proposal_kind=proposal.proposal_kind,
                    unit_instance_id=proposal.unit_instance_id,
                    movement_phase_action="advance",
                    movement_mode="advance",
                    witness=movement_witness(session, kind=kind),
                ).to_payload()
            ),
        )
        assert status.status_kind is (
            LifecycleStatusKind.INVALID if invalid else LifecycleStatusKind.WAITING_FOR_DECISION
        )

    submit("translate", "attempt", invalid=absent)
    if absent:
        assert state.battlefield_state == before
        assert_persistence_viewers_replay(session)
        request = pending_request(session)
        proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
        submit("hold", "retry")
        assert state.battlefield_state == before
    else:
        assert state.battlefield_state != before
    assert any(row.unit_instance_id == "army-alpha:mover" for row in state.advanced_unit_states)
    assert_persistence_viewers_replay(session)
    checkpoint = session.to_persistence_payload()
    forked = session.fork()
    assert forked.to_persistence_payload() == checkpoint
    assert forked.lifecycle.state is not state
    restored = LocalGameSession.from_persistence_payload(json.loads(json.dumps(checkpoint)))
    assert restored.to_persistence_payload() == checkpoint


@pytest.mark.parametrize(
    "mode", [MovementMode.CHARGE, MovementMode.PILE_IN, MovementMode.CONSOLIDATE]
)
def test_shared_permission_serializes_and_proves_fixed_pose_reachability(
    mode: MovementMode,
) -> None:
    session = movement_session(CharacteristicValue.source_dash(Characteristic.MOVEMENT))
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions), battlefield_state=state.battlefield_state
    )
    row = state.battlefield_state.unit_placement_by_id("army-alpha:mover").model_placements[0]
    model = scenario.model_instance_for_placement(row)
    moving = geometry_model_for_placement(model=model, placement=row)
    witness = PathWitness.for_paths(((row.model_instance_id, (row.pose, row.pose)),))
    legality = MovementLegalityContext.from_keywords(
        keywords=(),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        movement_mode=mode,
        movement_phase_action=None,
        displacement_kind={
            MovementMode.CHARGE: ModelDisplacementKind.CHARGE_MOVE,
            MovementMode.PILE_IN: ModelDisplacementKind.PILE_IN,
            MovementMode.CONSOLIDATE: ModelDisplacementKind.CONSOLIDATE,
        }[mode],
    )
    context = model_movement_path_context(
        model=model,
        context=legality.to_path_validation_context(
            moving_model=moving,
            witness=witness,
            battlefield_width_inches=44,
            battlefield_depth_inches=60,
            movement_distance_budget_inches=12,
        ),
    )
    assert context.pose_is_fixed
    assert context.movement_distance_budget_inches == 0
    assert context.validate().is_valid
    assert PathValidationContext.from_payload(context.to_payload()) == context
    query = MovementReachabilityQuery(
        path_context=context,
        terrain_context=legality.to_terrain_path_legality_context(
            moving_model=moving, witness=witness, terrain=(), terrain_features=()
        ),
        goal=MovementGoal(models=(replace(moving, model_id="target", pose=Pose.at(20, 20)),)),
    )
    assert movement_reachability(query).status is MovementReachabilityStatus.UNREACHABLE
    present_goal = replace(query, goal=MovementGoal(models=(moving,)))
    assert movement_reachability(present_goal).status is MovementReachabilityStatus.REACHABLE
    with pytest.raises(GameLifecycleError, match="identity drifted"):
        model_movement_path_context(
            model=replace(model, model_instance_id="other"), context=context
        )


def test_attached_movement_keeps_dash_bodyguard_fixed_and_numeric_leader_mobile() -> None:
    poses = {
        "source": tuple(Pose.at(10, 10 + i * 1.8) for i in range(5)),
        "leader": (Pose.at(10, 8.2),),
        "enemy": tuple(Pose.at(30, 10 + i * 1.8) for i in range(5)),
    }
    lifecycle, _ = fight_lifecycle(
        alpha_unit_ids=("source", "leader"),
        enemy_unit_ids=("enemy",),
        origins={key: value[0] for key, value in poses.items()},
        poses_by_unit_key=poses,
        game_id="order115-attached",
        alpha_unit_specs={"leader": ("core-character-leader", "core-character-leader", 1)},
        alpha_attachment_declarations=(AttachmentDeclaration("leader", "source"),),
        catalog=movement_catalog(CharacteristicValue.source_dash(Characteristic.MOVEMENT)),
        battle_phase=BattlePhase.MOVEMENT,
        record_deployment=True,
    )
    session = LocalGameSession(lifecycle)
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    before = state.battlefield_state
    body = before.unit_placement_by_id("army-alpha:source")
    leader = before.unit_placement_by_id("army-alpha:leader")
    session.advance_until_decision_or_terminal()
    assert_persistence_viewers_replay(session)
    request = pending_request(session)
    canonical_id = request.options[0].option_id
    for result_id, option_id in (("select", canonical_id), ("move", "normal_move")):
        request = pending_request(session)
        session.submit_option(
            request_id=request.request_id, result_id=result_id, option_id=option_id
        )
    request = pending_request(session)
    move = MovementProposalRequest.from_decision_request_payload(request.payload)
    witness = PathWitness.for_paths(
        tuple((row.model_instance_id, (row.pose, row.pose)) for row in body.model_placements)
        + tuple(
            (
                row.model_instance_id,
                (row.pose, Pose.at(row.pose.position.x + 0.25, row.pose.position.y)),
            )
            for row in leader.model_placements
        )
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="accepted",
        payload=validate_json_value(
            MovementProposalPayload(
                proposal_request_id=request.request_id,
                proposal_kind=move.proposal_kind,
                unit_instance_id=move.unit_instance_id,
                movement_phase_action="normal_move",
                movement_mode="normal",
                witness=witness,
            ).to_payload()
        ),
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert state.battlefield_state.unit_placement_by_id("army-alpha:source").model_placements == (
        body.model_placements
    )
    assert state.battlefield_state.unit_placement_by_id("army-alpha:leader") != leader
    assert_persistence_viewers_replay(session)
    assert session.fork().to_persistence_payload() == session.to_persistence_payload()


def test_dash_reactive_hold_is_an_engine_created_restorable_completion() -> None:
    session = movement_session(CharacteristicValue.source_dash(Characteristic.MOVEMENT))
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    before = state.battlefield_state
    handler = TriggeredMovementHandler(ruleset_descriptor=state.runtime_ruleset_descriptor())
    request = handler.request_from_state(
        state=state,
        unit_instance_id="army-alpha:mover",
        descriptor=TriggeredMovementDescriptor(
            movement_kind=TriggeredMovementKind.TRIGGERED,
            source_rule_id="test:order115:reactive-movement",
            trigger_timing=ReactionWindow(
                phase=BattlePhase.MOVEMENT,
                window_kind=ReactionWindowKind.RULE_TRIGGER,
                source_step=None,
                source_event_id=None,
            ),
            max_distance_inches=3,
        ),
        candidate_witnesses=(movement_witness(session, kind="hold"),),
    )
    lifecycle = session.lifecycle
    lifecycle.decision_controller.request_decision(request)
    session = LocalGameSession(lifecycle)
    session.advance_until_decision_or_terminal()
    assert_persistence_viewers_replay(session)
    option = next(row for row in request.options if row.option_id != "decline_triggered_movement")
    status = session.submit_option(
        request_id=request.request_id, result_id="reaction", option_id=option.option_id
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert state.battlefield_state == before
    assert any(
        row.event_type == "triggered_movement_resolved"
        for row in lifecycle.decision_controller.event_log.records
    )
    assert_persistence_viewers_replay(session)
    assert session.fork().to_persistence_payload() == session.to_persistence_payload()


def test_dash_fighter_completes_lethal_attacks_and_post_destruction_continuation() -> None:
    catalog = movement_catalog(
        CharacteristicValue.source_dash(Characteristic.MOVEMENT),
        datasheet_id="core-character-leader",
    )
    catalog = replace(
        catalog,
        wargear=tuple(
            replace(
                item,
                weapon_profiles=tuple(
                    replace(
                        profile,
                        attack_profile=AttackProfile.fixed(18),
                        damage_profile=DamageProfile.fixed(10),
                        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 1),
                        keywords=(WeaponKeyword.LETHAL_HITS,),
                        abilities=(AbilityDescriptor.lethal_hits(),),
                    )
                    for profile in item.weapon_profiles
                ),
            )
            for item in catalog.wargear
        ),
    )
    lifecycle, _ = fight_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_ids=("enemy",),
        origins={"intercessor-1": Pose.at(10, 10), "enemy": Pose.at(12, 10)},
        game_id="order115-dash-fight",
        model_count=1,
        catalog=catalog,
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        fights_first_unit_keys=("intercessor-1",),
        record_deployment=True,
    )
    session = LocalGameSession(lifecycle)
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    before = state.battlefield_state.unit_placement_by_id("army-alpha:intercessor-1")
    reach_lethal_choice(session)
    assert_persistence_viewers_replay(session)
    complete_attack(session)
    assert state.battlefield_state.unit_placement_by_id("army-alpha:intercessor-1") == before
    assert not state.army_definitions[1].units[0].alive_own_models()
    assert_persistence_viewers_replay(session)
    for _ in range(20):
        request = pending_request(session)
        if request.decision_type != MOVEMENT_PROPOSAL_DECISION_TYPE:
            break
        submit_fixture_request(session, request)
    else:
        raise AssertionError("Post-destruction Fight movement did not complete.")
    assert_persistence_viewers_replay(session)
    assert session.fork().to_persistence_payload() == session.to_persistence_payload()
