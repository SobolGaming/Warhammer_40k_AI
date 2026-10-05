"""P03G: complete model moves use the submitted physical occupancy order."""

from __future__ import annotations

import pytest
from tests.core_clause_evidence_helpers import clause_session
from tests.order126_movement_helpers import (
    assert_session_roundtrips,
    select_move,
    sequential_session,
    submit_path,
)
from tests.psychic_modifier_helpers import pending_request

from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.phases.movement import resolve_normal_move
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
from warhammer40k_core.engine.rules_units import rules_unit_view_from_armies
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("reverse", [False, True])
def test_cyclic_exchange_cannot_complete_either_model_first(reverse: bool) -> None:
    session = clause_session(phase=BattlePhase.MOVEMENT)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    placement = state.battlefield_state.unit_placement_by_id("army-alpha:mover")
    first, second, *others = placement.model_placements
    paths = (
        (first.model_instance_id, (first.pose, second.pose)),
        (second.model_instance_id, (second.pose, first.pose)),
    )
    witness = PathWitness.for_paths(
        (
            *(reversed(paths) if reverse else paths),
            *((row.model_instance_id, (row.pose, row.pose)) for row in others),
        )
    )
    before = state.battlefield_state.to_payload()
    resolution = resolve_normal_move(
        scenario=BattlefieldScenario(
            armies=tuple(state.army_definitions), battlefield_state=state.battlefield_state
        ),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=placement,
        path_witness=witness,
    )
    assert not resolution.is_valid
    assert any(
        result.violations and result.violations[0].violation_code == "end_on_model_overlap"
        for result in resolution.path_validation_results
    )
    assert state.battlefield_state.to_payload() == before


@pytest.mark.parametrize("attached", [False, True])
def test_facade_occupancy_order_invalid_retry_pending_completed_restore_and_replay(
    attached: bool,
) -> None:
    session = sequential_session(attached=attached)
    request = select_move(session)
    assert_session_roundtrips(session)
    isolated_fork = session.fork()
    fork_before = isolated_fork.to_persistence_payload()
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    view = rules_unit_view_from_armies(
        armies=tuple(state.army_definitions), unit_instance_id=proposal.unit_instance_id
    )
    source = RulesUnitPlacement.from_battlefield(
        view=view, battlefield_state=state.battlefield_state
    )
    first = next(
        row for row in source.model_placements if row.unit_instance_id == "army-alpha:mover"
    )
    second = (
        next(row for row in source.model_placements if row.unit_instance_id == "army-alpha:leader")
        if attached
        else source.model_placements[1]
    )
    others = [row for row in source.model_placements if row not in (first, second)]
    second_end = (
        Pose.at(second.pose.position.x + 1.8, second.pose.position.y)
        if attached
        else Pose.at(second.pose.position.x, second.pose.position.y + 1.4)
    )
    paths = (
        (first.model_instance_id, (first.pose, second.pose)),
        (second.model_instance_id, (second.pose, second_end)),
        *((row.model_instance_id, (row.pose, row.pose)) for row in others),
    )
    before = state.battlefield_state.to_payload()
    invalid = submit_path(
        session, request, PathWitness.for_paths(paths), result_id="order126-blocked"
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert state.battlefield_state.to_payload() == before
    assert state.movement_phase_state is not None
    assert not state.movement_phase_state.movement_distance_records
    assert_session_roundtrips(session)

    retry = pending_request(session)
    assert retry.request_id != request.request_id
    witness = PathWitness.for_paths((paths[1], paths[0], *paths[2:]))
    assert tuple(model_id for model_id, _poses in witness.model_paths)[:2] == (
        second.model_instance_id,
        first.model_instance_id,
    )
    assert PathWitness.from_payload(witness.to_payload()) == witness
    restored = assert_session_roundtrips(session)
    result = submit_path(session, retry, witness, result_id="order126-legal")
    restored_result = submit_path(
        restored, pending_request(restored), witness, result_id="order126-legal"
    )
    assert result == restored_result
    assert state.battlefield_state.to_payload() != before
    current = RulesUnitPlacement.from_battlefield(
        view=view, battlefield_state=state.battlefield_state
    )
    expected = {model_id: poses[-1] for model_id, poses in witness.model_paths}
    assert {row.model_instance_id: row.pose for row in current.model_placements} == expected
    assert session.to_persistence_payload() == restored.to_persistence_payload()
    assert isolated_fork.to_persistence_payload() == fork_before
    assert_session_roundtrips(session)
    events = session.lifecycle.decision_controller.event_log.records
    assert any(
        event.event_type == "movement_activation_completed"
        and isinstance(event.payload, dict)
        and event.payload.get("witness") == validate_json_value(witness.to_payload())
        for event in events
    )


@pytest.mark.parametrize("family", ["scout", "charge", "fight", "triggered"])
@pytest.mark.parametrize("cyclic", [False, True])
def test_shared_path_consumers_accept_vacate_before_follow_and_reject_cyclic_occupancy(
    family: str,
    cyclic: bool,
) -> None:
    from warhammer40k_core.core.ruleset_descriptor import MovementMode
    from warhammer40k_core.engine.battlefield_state import ModelDisplacementKind
    from warhammer40k_core.engine.charge_move_resolution import resolve_charge_move
    from warhammer40k_core.engine.fight_movement_paths import validate_fight_paths
    from warhammer40k_core.engine.fight_resolution import FightMovementProposal
    from warhammer40k_core.engine.movement_proposals import ProposalKind
    from warhammer40k_core.engine.prebattle import PreBattleViolation
    from warhammer40k_core.engine.reaction_windows import ReactionWindow, ReactionWindowKind
    from warhammer40k_core.engine.scout_movement_paths import append_scout_path_violations
    from warhammer40k_core.engine.triggered_movement import (
        TriggeredMovementDescriptor,
        TriggeredMovementKind,
    )
    from warhammer40k_core.engine.triggered_movement_resolution import resolve_triggered_movement

    session = sequential_session()
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    before = state.battlefield_state.unit_placement_by_id("army-alpha:mover")
    first, second, *others = before.model_placements
    second_end = (
        first.pose if cyclic else Pose.at(second.pose.position.x, second.pose.position.y + 1.4)
    )
    moving_paths = (
        (first.model_instance_id, (first.pose, second.pose)),
        (second.model_instance_id, (second.pose, second_end)),
    )
    witness = PathWitness.for_paths(
        (
            *(moving_paths if cyclic else reversed(moving_paths)),
            *((row.model_instance_id, (row.pose, row.pose)) for row in others),
        )
    )
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions), battlefield_state=state.battlefield_state
    )
    ruleset = state.runtime_ruleset_descriptor()
    attempted = before.with_model_placements(
        tuple(
            row.with_pose(witness.final_pose_for_model(row.model_instance_id))
            for row in before.model_placements
        )
    )
    original = state.battlefield_state.to_payload()
    if family == "charge":
        resolution = resolve_charge_move(
            scenario=scenario,
            ruleset_descriptor=ruleset,
            unit_placement=before,
            selected_target_unit_instance_ids=(),
            maximum_distance_inches=6,
            path_witness=witness,
        )
        path_results = resolution.path_validation_results
    elif family == "fight":
        proposal = FightMovementProposal(
            proposal_request_id="order126-fight",
            proposal_kind=ProposalKind.PILE_IN,
            unit_instance_id=before.unit_instance_id,
            movement_phase_action="pile_in",
            movement_mode=MovementMode.PILE_IN,
            witness=witness,
        )
        path_results, _ = validate_fight_paths(
            scenario=scenario,
            ruleset_descriptor=ruleset,
            before=before,
            after=attempted,
            witness=witness,
            movement_mode=MovementMode.PILE_IN,
            displacement_kind=ModelDisplacementKind.PILE_IN,
            distance_budget_inches=3,
            proposal=proposal,
        )
    elif family == "triggered":
        descriptor = TriggeredMovementDescriptor(
            movement_kind=TriggeredMovementKind.TRIGGERED,
            source_rule_id="rule:03:03.01:1",
            trigger_timing=ReactionWindow(
                phase=BattlePhase.MOVEMENT,
                window_kind=ReactionWindowKind.RULE_TRIGGER,
                source_step="move_units",
                source_event_id="order126-core-control",
            ),
            max_distance_inches=6,
        )
        triggered = resolve_triggered_movement(
            scenario=scenario,
            ruleset_descriptor=ruleset,
            unit_placement=before,
            descriptor=descriptor,
            path_witness=witness,
            battle_round=1,
            turn_player_id="player-a",
        )
        path_results = triggered.path_validation_results
    else:
        view = rules_unit_view_from_armies(
            armies=tuple(state.army_definitions), unit_instance_id=before.unit_instance_id
        )
        grouped = RulesUnitPlacement.from_battlefield(
            view=view, battlefield_state=state.battlefield_state
        )
        violations: list[PreBattleViolation] = []
        append_scout_path_violations(
            violations=violations,
            state=state,
            scenario=scenario,
            ruleset_descriptor=ruleset,
            current=grouped,
            attempted=RulesUnitPlacement(
                rules_unit_instance_id=grouped.rules_unit_instance_id,
                component_unit_placements=(attempted,),
            ),
            witness=witness,
            scout_distance_inches=6,
        )
        assert bool(violations) is cyclic
        assert state.battlefield_state.to_payload() == original
        return
    assert all(result.is_valid for result in path_results) is (not cyclic)
    if cyclic:
        assert any(
            row.violations and row.violations[0].violation_code == "end_on_model_overlap"
            for row in path_results
        )
    assert state.battlefield_state.to_payload() == original


def test_legal_friendly_transit_and_multisegment_rotation_remain_playable() -> None:
    session = sequential_session()
    request = select_move(session)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    source = state.battlefield_state.unit_placement_by_id("army-alpha:mover")
    first, *others = source.model_placements
    # Infantry may pass through friendly bases, but must finish clear of them.
    witness = PathWitness.for_paths(
        (
            (
                first.model_instance_id,
                (
                    first.pose,
                    others[0].pose,
                    Pose.at(12.8, 21.4),
                    Pose.at(12.8, 21.4, facing_degrees=90),
                ),
            ),
            *((row.model_instance_id, (row.pose, row.pose)) for row in others),
        )
    )
    submit_path(session, request, witness, result_id="order126-friendly-transit")
    assert state.battlefield_state.unit_placement_by_id(source.unit_instance_id).model_placements[
        0
    ].pose == witness.final_pose_for_model(first.model_instance_id)
    assert_session_roundtrips(session)


@pytest.mark.parametrize("attached", [False, True])
def test_native_sequential_move_against_overhanging_enemy_restores_and_replays(
    attached: bool,
) -> None:
    from tests.order85_overhang_helpers import overhang_session
    from tests.sequential_translation_helpers import leading_first_translation_paths

    session = overhang_session(phase=BattlePhase.MOVEMENT, start_y=8.0, attached=attached)
    assert_session_roundtrips(session)
    request = pending_request(session)
    unit_id = "attached-unit:army-alpha:bodyguard" if attached else "army-alpha:source"
    selected = session.submit_option(
        request_id=request.request_id, option_id=unit_id, result_id="order126-overhang-select"
    )
    assert selected.status_kind is not LifecycleStatusKind.INVALID
    request = pending_request(session)
    selected = session.submit_option(
        request_id=request.request_id, option_id="normal_move", result_id="order126-overhang-normal"
    )
    assert selected.status_kind is not LifecycleStatusKind.INVALID
    request = pending_request(session)
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    placement = RulesUnitPlacement.from_battlefield(
        view=rules_unit_view_from_armies(
            armies=tuple(state.army_definitions), unit_instance_id=proposal.unit_instance_id
        ),
        battlefield_state=state.battlefield_state,
    )
    paths = tuple(
        (
            row.model_instance_id,
            (
                row.pose,
                Pose.at(
                    row.pose.position.x + 0.2,
                    row.pose.position.y,
                    facing_degrees=row.pose.facing.degrees,
                ),
            ),
        )
        for row in placement.model_placements
    )
    witness = PathWitness.for_paths(leading_first_translation_paths(paths, dx=0.2))
    result = submit_path(session, request, witness, result_id="order126-overhang-legal")
    assert result.status_kind is not LifecycleStatusKind.INVALID
    assert_session_roundtrips(session)
    assert state.battlefield_state is not None
    moved = RulesUnitPlacement.from_battlefield(
        view=rules_unit_view_from_armies(
            armies=tuple(state.army_definitions), unit_instance_id=proposal.unit_instance_id
        ),
        battlefield_state=state.battlefield_state,
    )
    assert all(
        row.pose == witness.final_pose_for_model(row.model_instance_id)
        for row in moved.model_placements
    )
