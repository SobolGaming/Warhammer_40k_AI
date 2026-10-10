"""Combat setup applies authoritative status, independently of its turn charge lock."""

# pyright: reportPrivateUsage=false

import copy
from dataclasses import replace

import pytest
from tests.d04_combat_helpers import combat_proposal, combat_session
from tests.order128_helpers import assert_checkpoint
from tests.order135_transport_helpers import (
    PASSENGER,
    cargo_proposal,
    reach_disembark,
    starting_cargo_session,
)
from tests.psychic_modifier_helpers import pending_request

from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.mission_action_eligibility import (
    mission_action_pre_oc_ineligibility_reason,
    mission_action_unit_ineligibility_reason,
)
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.rules_units import rules_unit_is_battle_shocked
from warhammer40k_core.engine.unit_objective_control import current_unit_objective_control


def test_native_combat_survivor_enters_shared_shock_without_test_and_restores() -> None:
    session = combat_session()
    request = pending_request(session)
    before = tuple(session.lifecycle.decision_controller.event_log.records)
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="d04:combat",
        payload=validate_json_value(combat_proposal(session).to_payload()),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    state = session.lifecycle.state
    assert state is not None
    assert rules_unit_is_battle_shocked(state=state, unit_instance_id=PASSENGER)
    assert len(state.battle_shocked_unit_states) == 1
    row = state.battle_shocked_unit_states[0]
    assert row.source_result_id == "d04:combat"
    assert row.battle_round_started == 1
    assert row.unit_instance_id == PASSENGER
    assert not current_unit_objective_control(
        state=state,
        unit_instance_id=PASSENGER,
    ).has_positive_objective_control
    for gate in (
        mission_action_pre_oc_ineligibility_reason,
        mission_action_unit_ineligibility_reason,
    ):
        assert gate(
            state=state,
            player_id="player-a",
            unit_instance_id=PASSENGER,
            runtime_modifier_registry=session.lifecycle._require_runtime_content_bundle().runtime_modifier_registry,
        ) == ("mission_action_unit_battle_shocked")
    from warhammer40k_core.engine.stratagem_catalog import (
        eleventh_edition_core_stratagem_catalog_records,
    )
    from warhammer40k_core.engine.stratagems_model import (
        StratagemTargetBinding,
        StratagemTargetKind,
    )
    from warhammer40k_core.engine.stratagems_targeting import _target_binding_error

    definition = next(
        record.definition
        for record in eleventh_edition_core_stratagem_catalog_records()
        if record.definition.stratagem_id == "epic-challenge"
    )
    assert (
        _target_binding_error(
            state=state,
            player_id="player-a",
            target_spec=definition.target_spec,
            policy=definition.restriction_policy,
            target_binding=StratagemTargetBinding(
                target_kind=StratagemTargetKind.FRIENDLY_UNIT,
                target_player_id="player-a",
                target_unit_instance_id=PASSENGER,
            ),
            context=None,
            ruleset_descriptor=session.lifecycle.config.ruleset_descriptor,
            army_catalog=session.lifecycle.config.army_catalog,
        )
        == "friendly_battle_shocked_unit"
    )
    new_events = session.lifecycle.decision_controller.event_log.records[len(before) :]
    assert not any(e.event_type.startswith("battle_shock_test") for e in new_events)
    disembark = state.disembarked_unit_states[0]
    assert disembark.can_declare_charge is False
    assert disembark.battle_shocked_until == "until_cleared"
    assert_checkpoint(session)


def test_native_ground_tactical_remains_unshocked_positive() -> None:
    session = starting_cargo_session()
    request = reach_disembark(session)
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="d04:tactical",
        payload=validate_json_value(cargo_proposal(session).to_payload()),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    state = session.lifecycle.state
    assert state is not None
    assert not rules_unit_is_battle_shocked(state=state, unit_instance_id=PASSENGER)
    assert current_unit_objective_control(
        state=state, unit_instance_id=PASSENGER
    ).has_positive_objective_control
    assert_checkpoint(session)


@pytest.mark.parametrize(
    ("game_id", "passed"), [("order135-combat-platform", True), ("d04-command:3", False)]
)
def test_native_combat_persists_until_one_required_own_command_test(
    game_id: str,
    passed: bool,
) -> None:
    from tests.d04_combat_helpers import finish_to_next_own_movement

    session = combat_session(game_id=game_id)
    request = pending_request(session)
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="d04:combat",
        payload=validate_json_value(combat_proposal(session).to_payload()),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    state = session.lifecycle.state
    assert state is not None
    original_shock = tuple(state.battle_shocked_unit_states)
    assert_checkpoint(session)
    finish_to_next_own_movement(session)
    resolved = [
        e.payload
        for e in session.lifecycle.decision_controller.event_log.records
        if e.event_type == "battle_shock_test_resolved"
    ]
    assert len(resolved) == 1
    payload = resolved[0]
    assert isinstance(payload, dict)
    raw_result = payload["battle_shock_result"]
    assert isinstance(raw_result, dict)
    raw_request = raw_result["request"]
    assert isinstance(raw_request, dict)
    assert raw_request["reason"] == "command_phase_required"
    assert raw_request["unit_instance_id"] == PASSENGER
    context = raw_request["below_half_strength_context"]
    assert isinstance(context, dict)
    assert context["is_below_half_strength"] is False
    assert context["is_at_half_strength"] is False
    assert raw_result["passed"] is passed
    assert payload["state_update"] == (
        "cleared_battle_shocked" if passed else "already_battle_shocked"
    )
    assert state.battle_shocked_unit_states == ([] if passed else list(original_shock))
    assert rules_unit_is_battle_shocked(state=state, unit_instance_id=PASSENGER) is not passed
    assert_checkpoint(session)


def test_native_combat_malformed_source_is_atomic_and_retry_applies_once() -> None:
    session = combat_session()
    request = pending_request(session)
    proposal = validate_json_value(combat_proposal(session).to_payload())
    assert isinstance(proposal, dict)
    malformed = {**proposal, "transport_unit_instance_id": "other-transport"}
    before = session.to_persistence_payload()
    invalid = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="d04:wrong-carrier",
        payload=malformed,
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert session.to_persistence_payload() == before
    assert_checkpoint(session)
    accepted = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="d04:retry",
        payload=proposal,
    )
    assert accepted.status_kind is not LifecycleStatusKind.INVALID, accepted.to_payload()
    assert (
        sum(
            e.event_type == "combat_disembark_battle_shock_applied"
            for e in session.lifecycle.decision_controller.event_log.records
        )
        == 1
    )
    assert_checkpoint(session)


def test_native_combat_member_oc_and_normal_objective_resolver_use_shared_status() -> None:
    from warhammer40k_core.core.attributes import CharacteristicValueKind
    from warhammer40k_core.engine.objective_control import (
        ObjectiveControlContext,
        ObjectiveControlTiming,
        model_objective_control_characteristic,
        resolve_objective_control,
    )
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
    from warhammer40k_core.geometry.pose import Pose

    session = combat_session()
    request = pending_request(session)
    proposal = combat_proposal(session)
    assert proposal.attempted_placement is not None
    # A legal Combat decision puts the same passenger within the actual home marker.
    proposal = replace(
        proposal,
        attempted_placement=replace(
            proposal.attempted_placement,
            model_placements=tuple(
                replace(row, pose=Pose.at(6.8, 10, 0))
                for row in proposal.attempted_placement.model_placements
            ),
        ),
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="d04:objective-combat",
        payload=validate_json_value(proposal.to_payload()),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    state = session.lifecycle.state
    assert state is not None
    unit = rules_unit_view_by_id(state=state, unit_instance_id=PASSENGER)
    for model in unit.own_models:
        oc = model_objective_control_characteristic(
            model,
            battle_shocked=rules_unit_is_battle_shocked(state=state, unit_instance_id=PASSENGER),
            state=state,
            unit_instance_id=PASSENGER,
        )
        assert oc.value_kind is CharacteristicValueKind.REPLACEMENT_DASH
        assert oc.final == 0
    before = session.to_persistence_payload()
    record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state, timing=ObjectiveControlTiming.PHASE_END, phase=BattlePhase.MOVEMENT
        )
    )
    contributors = [
        row
        for result in record.results
        for row in result.contributors
        if row.unit_instance_id == PASSENGER
    ]
    assert contributors
    assert all(row.battle_shocked and row.effective_objective_control == 0 for row in contributors)
    assert sum(row.effective_objective_control for row in contributors) == 0
    assert session.to_persistence_payload() == before
    assert_checkpoint(session)


def test_native_combat_restore_requires_the_exact_direct_status_occurrence() -> None:
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError

    session = combat_session()
    request = pending_request(session)
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="d04:restore-authority",
        payload=validate_json_value(combat_proposal(session).to_payload()),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    original = session.lifecycle.to_payload()
    # Simple source/occurrence drift controls, not coordinated edited-history certification.
    for field, wrong in (
        ("source_rule_id", "core_rules_tactical_disembark"),
        ("result_id", "different-result"),
        ("hazard_event_id", "different-hazard"),
        ("state_update", "not_required"),
    ):
        malformed = copy.deepcopy(original)
        events = malformed["decisions"]["event_log"]
        occurrence = next(
            event
            for event in events
            if event["event_type"] == "combat_disembark_battle_shock_applied"
        )
        payload = occurrence["payload"]
        assert isinstance(payload, dict)
        payload[field] = wrong
        with pytest.raises(GameLifecycleError):
            GameLifecycle.from_payload(malformed)
    assert session.lifecycle.to_payload() == original
    assert_checkpoint(session)


def test_native_combat_all_killed_cargo_records_no_surviving_shock() -> None:
    from tests.d04_combat_helpers import canonical_cargo_proposal, canonical_mob_cargo_config
    from tests.psychic_modifier_helpers import submit_fixture_request

    from warhammer40k_core.engine.mortal_wound_model_allocation import (
        is_mortal_wound_resolution_request,
    )

    session = combat_session(game_id="d04-canonical-mob", cargo_config=canonical_mob_cargo_config())
    request = pending_request(session)
    # Deterministic result identity selected before submission from a detached forecast.
    # The actual public engine rolls below, never injected dice, establish this control.
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="d04:all-killed-result:45999",
        payload=validate_json_value(canonical_cargo_proposal(session).to_payload()),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    rolls = [
        event.payload
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == "dice_rolled"
    ]
    assert len(rolls) == 10
    assert all(isinstance(roll, dict) and roll["source"] == "rng" for roll in rolls)
    assert [roll["values"] for roll in rolls if isinstance(roll, dict)] == [
        [2],
        [2],
        [1],
        [1],
        [2],
        [1],
        [1],
        [1],
        [1],
        [2],
    ]
    state = session.lifecycle.state
    assert state is not None
    assert not state.battle_shocked_unit_ids
    assert_checkpoint(session)
    for index in range(20):
        allocation_request = session.lifecycle.pending_decision_request()
        if allocation_request is None or not is_mortal_wound_resolution_request(allocation_request):
            break
        submit_fixture_request(session, allocation_request)
        if index == 4:
            assert_checkpoint(session)
    else:
        raise AssertionError("Combat hazard did not finish allocation")
    army = state.army_definition_for_player("player-a")
    assert army is not None
    passenger = next(unit for unit in army.units if unit.unit_instance_id == PASSENGER)
    assert len(passenger.own_models) == 10
    assert all(not model.is_alive for model in passenger.own_models)
    assert not state.battle_shocked_unit_ids
    assert not state.battle_shocked_unit_states
    occurrences = [
        event.payload
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == "combat_disembark_battle_shock_applied"
    ]
    assert len(occurrences) == 1
    assert isinstance(occurrences[0], dict)
    assert occurrences[0]["state_update"] == "not_required"
    assert_checkpoint(session)


def test_native_attached_combat_uses_one_identity_and_shared_status_is_idempotent() -> None:
    from tests.d04_combat_helpers import canonical_attached_cargo_config, canonical_cargo_proposal

    from warhammer40k_core.engine.battle_shock_state import (
        BATTLE_SHOCK_STATE_ALREADY,
        apply_direct_battle_shock_state,
    )
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    session = combat_session(
        game_id="d04-canonical-attached", cargo_config=canonical_attached_cargo_config()
    )
    request = pending_request(session)
    proposal = canonical_cargo_proposal(session)
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="d04:canonical-cargo",
        payload=validate_json_value(proposal.to_payload()),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    state = session.lifecycle.state
    assert state is not None
    view = rules_unit_view_by_id(state=state, unit_instance_id=proposal.unit_instance_id)
    assert view.unit_instance_id == "attached-unit:army-alpha:bodyguard"
    assert state.battle_shocked_unit_ids == [view.unit_instance_id]
    assert len(state.battle_shocked_unit_states) == 1
    shock = state.battle_shocked_unit_states[0]
    assert len(shock.model_instance_ids) == 6
    assert shock.source_result_id == "d04:canonical-cargo"
    for component in view.component_unit_instance_ids:
        assert rules_unit_is_battle_shocked(state=state, unit_instance_id=component)
        assert not current_unit_objective_control(
            state=state, unit_instance_id=component
        ).has_positive_objective_control
    assert_checkpoint(session)
    before = session.lifecycle.to_payload()
    # Shared-owner idempotence on native status. No second Combat occurrence is fabricated.
    assert (
        apply_direct_battle_shock_state(
            state=state,
            decisions=session.lifecycle.decision_controller,
            player_id="player-a",
            unit_instance_id=view.unit_instance_id,
            source_result_id=shock.source_result_id,
            battle_round=state.battle_round,
        )
        == BATTLE_SHOCK_STATE_ALREADY
    )
    assert session.lifecycle.to_payload() == before
    assert_checkpoint(session)
