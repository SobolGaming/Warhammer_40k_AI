"""Order 50: the Stratagem authorizes the ordinary Charge decision pipeline."""

from __future__ import annotations

import json
import math
from dataclasses import replace
from typing import cast

import pytest
from tests.charge_distance_helpers import request_from
from tests.charge_reroll_helpers import heroic_session
from tests.heroic_intervention_helpers import latest_heroic_roll, start_heroic
from tests.phase15a_charge_test_support import _heroic_proposal_from_request

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.stratagems import StratagemTargetBinding, StratagemTargetKind


def test_heroic_intervention_enters_shared_charge_declaration() -> None:
    session, unit_id = heroic_session(natural=False)
    request = request_from(session.advance_until_decision_or_terminal())
    proposal = replace(
        _heroic_proposal_from_request(request),
        target_binding=StratagemTargetBinding(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_player_id="player-a",
            target_unit_instance_id=unit_id,
        ),
        effect_selection={"mode": "into_the_fray"},
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order50-use",
        payload=validate_json_value({"proposal": proposal.to_payload()}),
    )
    declaration = request_from(status)
    assert declaration.decision_type == "select_charging_unit"
    assert unit_id in {option.option_id for option in declaration.options}

    targets = request_from(
        session.submit_option(
            request_id=declaration.request_id, option_id=unit_id, result_id="order50-declare"
        )
    )
    assert targets.decision_type == "select_charge_targets"
    assert session.lifecycle.state is not None
    assert session.lifecycle.state.active_player_id == "player-b"
    assert session.lifecycle.state.effective_active_player_id() == "player-a"


@pytest.mark.parametrize(("delta", "expected"), [(20, 6), (-20, 1), (0, None)])
def test_heroic_roll_modifiers_are_applied_before_source_cap(
    delta: int, expected: int | None
) -> None:
    session, unit_id, declaration = start_heroic(delta=delta)
    session.submit_option(
        request_id=declaration.request_id, option_id=unit_id, result_id="order50-declare"
    )
    roll = latest_heroic_roll(session)
    raw = roll.roll_state.current_total
    assert roll.value == (expected if expected is not None else min(raw, 6))
    assert roll.movement_budget.maximum_distance_inches == roll.value
    assert roll.movement_budget.roll_limit is not None
    assert roll.movement_budget.modified_roll.unmodified.value == raw
    assert roll.movement_budget.modified_roll.unbounded_value == raw + delta


@pytest.mark.parametrize("accept", [False, True])
def test_heroic_shared_reroll_targets_decline_restore_and_exact_replay(accept: bool) -> None:
    session, unit_id, declaration = start_heroic(natural=True, delta=20)
    reroll = request_from(
        session.submit_option(
            request_id=declaration.request_id, option_id=unit_id, result_id="order50-declare"
        )
    )
    assert reroll.decision_type == "select_dice_reroll"
    restored = LocalGameSession(
        GameLifecycle.from_payload(
            cast(GameLifecyclePayload, json.loads(json.dumps(session.lifecycle.to_payload())))
        )
    )
    for branch in (session, restored):
        targets = request_from(
            branch.submit_option(
                request_id=reroll.request_id,
                option_id="reroll:0,1" if accept else "decline",
                result_id="order50-native",
            )
        )
        assert targets.decision_type == "select_charge_targets"
        roll = latest_heroic_roll(branch)
        assert len(roll.roll_state.rerolls) == int(accept)
        assert roll.value == 6
        state = branch.lifecycle.state
        assert state is not None
        assert state.command_point_total("player-a") == 0
        branch.submit_option(
            request_id=targets.request_id,
            option_id="decline_charge_targets",
            result_id="order50-decline",
        )
        assert all(scope.kind.value != "charge" for scope in state.active_player_scopes)
    assert session.lifecycle.to_payload() == restored.lifecycle.to_payload()
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="order50-replay"))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )


def test_heroic_movement_modifiers_follow_the_limited_roll() -> None:
    session, unit_id, declaration = start_heroic(delta=20, movement_delta=2.5)
    request_from(
        session.submit_option(
            request_id=declaration.request_id, option_id=unit_id, result_id="order50-declare"
        )
    )
    roll = latest_heroic_roll(session)
    assert roll.value == 6
    assert roll.movement_budget.maximum_distance_inches == 8.5
    assert len(roll.movement_budget.distance_modifiers) == 1


@pytest.mark.parametrize(("distance", "legal"), [(5.999, True), (6.001, False)])
def test_fray_target_range_remains_six_with_extra_movement(distance: float, legal: bool) -> None:
    from tests.core_stratagem_helpers import _replace_unit_poses

    from warhammer40k_core.engine.charge_targets import charge_target_candidates
    from warhammer40k_core.geometry.pose import Pose

    session, unit_id, _ = start_heroic(delta=20, movement_delta=3)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    before = charge_target_candidates(
        state=state, unit_instance_id=unit_id, ruleset_descriptor=state.runtime_ruleset_descriptor()
    )[0]
    placement = state.battlefield_state.unit_placement_by_id(before.target_unit_instance_id)
    shift = distance - before.closest_distance_inches
    _replace_unit_poses(
        state,
        unit_instance_id=before.target_unit_instance_id,
        poses=tuple(
            Pose.at(m.pose.position.x, m.pose.position.y + shift)
            for m in placement.model_placements
        ),
    )
    candidate = charge_target_candidates(
        state=state, unit_instance_id=unit_id, ruleset_descriptor=state.runtime_ruleset_descriptor()
    )[0]
    assert math.isclose(candidate.closest_distance_inches, distance, abs_tol=1e-9)
    assert candidate.is_legal is legal
    if not legal:
        assert candidate.violation_code == "charge_source_target_out_of_range"


def test_heroic_witness_move_restores_replays_and_expires_on_opponents_turn() -> None:
    from warhammer40k_core.core.ruleset_descriptor import MovementMode
    from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
    from warhammer40k_core.engine.charge_movement_source import charge_movement_placement
    from warhammer40k_core.engine.movement_proposals import ProposalKind
    from warhammer40k_core.engine.phases.charge import ChargeMoveProposal
    from warhammer40k_core.geometry.pathing import PathWitness
    from warhammer40k_core.geometry.pose import Pose

    session, unit_id, declaration = start_heroic(delta=20)
    targets = request_from(
        session.submit_option(
            request_id=declaration.request_id, option_id=unit_id, result_id="order50-declare"
        )
    )
    target = next(o for o in targets.options if o.option_id != "decline_charge_targets")
    movement = request_from(
        session.submit_option(
            request_id=targets.request_id, option_id=target.option_id, result_id="order50-targets"
        )
    )
    assert session.lifecycle.state is not None
    state = session.lifecycle.state
    placement = charge_movement_placement(
        scenario=battlefield_scenario_for_state(state=state), unit_instance_id=unit_id
    )
    witness = PathWitness.for_paths(
        tuple(
            (
                m.model_instance_id,
                (
                    m.pose,
                    Pose.at(m.pose.position.x, m.pose.position.y + 2),
                    Pose.at(m.pose.position.x, m.pose.position.y + 4),
                ),
            )
            for m in placement.model_placements
        )
    )
    assert isinstance(target.payload, dict)
    payload = target.payload["target_ids"]
    assert isinstance(payload, list)
    proposal = ChargeMoveProposal(
        proposal_request_id=movement.request_id,
        unit_instance_id=unit_id,
        proposal_kind=ProposalKind.CHARGE_MOVE,
        movement_phase_action="charge_move",
        movement_mode=MovementMode.CHARGE,
        charge_target_unit_instance_ids=tuple(str(t) for t in payload),
        witness=witness,
    )
    restored = LocalGameSession(
        GameLifecycle.from_payload(
            cast(GameLifecyclePayload, json.loads(json.dumps(session.lifecycle.to_payload())))
        )
    )
    for branch in (session, restored):
        status = branch.submit_parameterized_payload(
            request_id=movement.request_id,
            payload=validate_json_value(proposal.to_payload()),
            result_id="order50-move",
        )
        from warhammer40k_core.engine.phase import LifecycleStatusKind

        assert status.status_kind is not LifecycleStatusKind.INVALID, status
        assert branch.lifecycle.state is not None
        effects = branch.lifecycle.state.persisting_effects_for_unit(unit_id)
        effect = next(
            e
            for e in effects
            if isinstance(e.effect_payload, dict)
            and e.effect_payload.get("effect_kind") == "charge_grants_fights_first"
        )
        assert effect.owner_player_id == "player-a"
        assert effect.expiration.player_id == "player-b"
    assert session.lifecycle.to_payload() == restored.lifecycle.to_payload()
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="order50-move-replay"))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize(
    "field", ["source_result_id", "target_range_inches", "roll_limit", "allowed_target_ids"]
)
def test_heroic_restore_rejects_source_restriction_drift(field: str) -> None:
    from warhammer40k_core.engine.phase import GameLifecycleError

    session, _, _ = start_heroic()
    payload = json.loads(json.dumps(session.lifecycle.to_payload()))
    source = payload["state"]["charge_phase_state"]["interruption"]
    source[field] = {
        "source_result_id": "forged-use",
        "target_range_inches": 12.0,
        "roll_limit": None,
        "allowed_target_ids": ["army-beta:enemy"],
    }[field]
    with pytest.raises(GameLifecycleError):
        GameLifecycle.from_payload(payload)


def test_completed_heroic_restore_rejects_forged_mode_limit_in_history() -> None:
    from warhammer40k_core.engine.phase import GameLifecycleError

    session, unit_id, declaration = start_heroic(delta=20)
    targets = request_from(
        session.submit_option(
            request_id=declaration.request_id, option_id=unit_id, result_id="declare"
        )
    )
    session.submit_option(
        request_id=targets.request_id, option_id="decline_charge_targets", result_id="decline"
    )
    payload = json.loads(json.dumps(session.lifecycle.to_payload()))
    for event in payload["decisions"]["event_log"]:
        if event["event_type"] in {"interrupted_charge_started", "interrupted_charge_completed"}:
            event["payload"]["source"]["roll_limit"] = None
    with pytest.raises(GameLifecycleError, match="Interrupted Charge"):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize(
    ("keywords", "allowed"),
    [
        (("Vehicle",), False),
        (("Vehicle", "Character"), True),
        (("Vehicle", "Walker"), True),
        (("Aircraft",), False),
    ],
)
def test_heroic_uses_vehicle_exceptions_and_ordinary_aircraft_restriction(
    keywords: tuple[str, ...], allowed: bool
) -> None:
    from tests.core_stratagem_helpers import _replace_unit_keywords

    from warhammer40k_core.engine.phase import LifecycleStatusKind

    session, unit_id = heroic_session(natural=False)
    request = request_from(session.advance_until_decision_or_terminal())
    state = session.lifecycle.state
    assert state is not None
    _replace_unit_keywords(state, unit_instance_id=unit_id, keywords=keywords)
    before_cp = state.command_point_total("player-a")
    proposal = _heroic_proposal_from_request(request).with_binding(
        StratagemTargetBinding(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_player_id="player-a",
            target_unit_instance_id=unit_id,
        ),
        effect_selection={"mode": "into_the_fray"},
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="vehicle-use",
        payload=validate_json_value({"proposal": proposal.to_payload()}),
    )
    if allowed:
        assert request_from(status).decision_type == "select_charging_unit"
    else:
        assert status.status_kind is LifecycleStatusKind.INVALID
        assert state.command_point_total("player-a") == before_cp
        assert session.lifecycle.decision_controller.queue.peek_next() == request


@pytest.mark.parametrize("made_move", [False, True])
def test_leap_targets_completed_charge_moves_not_fights_first_effects(made_move: bool) -> None:
    from tests.heroic_intervention_helpers import use_heroic

    from warhammer40k_core.engine.phase import LifecycleStatusKind

    session, unit_id = heroic_session(natural=False)
    state = session.lifecycle.state
    assert state is not None
    assert state.charge_phase_state is not None
    if not made_move:
        state.replace_charge_phase_state(
            replace(state.charge_phase_state, declared_target_unit_instance_ids_by_unit={})
        )
    request = request_from(session.advance_until_decision_or_terminal())
    if made_move:
        declaration = use_heroic(session, unit_id, mode="leap_to_defend")
        session.submit_option(
            request_id=declaration.request_id, option_id=unit_id, result_id="leap-declare"
        )
        roll = latest_heroic_roll(session)
        assert roll.movement_budget.roll_limit is None
        assert roll.value == roll.movement_budget.modified_roll.final_value
    else:
        proposal = _heroic_proposal_from_request(request).with_binding(
            StratagemTargetBinding(
                target_kind=StratagemTargetKind.FRIENDLY_UNIT,
                target_player_id="player-a",
                target_unit_instance_id=unit_id,
            ),
            effect_selection={"mode": "leap_to_defend"},
        )
        before = state.command_point_total("player-a")
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id="no-charged-enemy",
            payload=validate_json_value({"proposal": proposal.to_payload()}),
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID
        assert state.command_point_total("player-a") == before - 1
        assert len(state.stratagem_use_records) == 1
        assert not any(
            event.event_type in {"charge_roll_resolved", "charge_move_completed"}
            for event in session.lifecycle.decision_controller.event_log.records
        )
        assert any(
            event.event_type == "interrupted_charge_completed"
            for event in session.lifecycle.decision_controller.event_log.records
        )


def test_missing_heroic_mode_is_rejected_before_spend_or_roll() -> None:
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    session, unit_id = heroic_session(natural=False)
    request = request_from(session.advance_until_decision_or_terminal())
    proposal = _heroic_proposal_from_request(request).with_binding(
        StratagemTargetBinding(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_player_id="player-a",
            target_unit_instance_id=unit_id,
        )
    )
    state = session.lifecycle.state
    assert state is not None
    before = state.to_payload()
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="missing-mode",
        payload=validate_json_value({"proposal": proposal.to_payload()}),
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert state.to_payload() == before
    assert session.lifecycle.decision_controller.queue.peek_next() == request


def test_attached_heroic_declaration_uses_shared_actor_and_viewer_contract() -> None:
    from tests.heroic_intervention_helpers import add_heroic_modifier, use_heroic

    from warhammer40k_core.adapters.event_stream import EventStreamCursor

    session, unit_id = heroic_session(natural=False, attached=True)
    add_heroic_modifier(session, unit_id, delta=20)
    declaration = use_heroic(session, unit_id)
    assert [option.option_id for option in declaration.options] == [unit_id]
    targets = request_from(
        session.submit_option(
            request_id=declaration.request_id, option_id=unit_id, result_id="attached-declare"
        )
    )
    assert targets.actor_id == "player-a"
    assert latest_heroic_roll(session).request.unit_instance_id == unit_id
    for viewer in ("player-a", "player-b"):
        visible = json.dumps(session.view(viewer_player_id=viewer))
        delta = json.dumps(session.events_since(EventStreamCursor(), viewer_player_id=viewer))
        assert "object at 0x" not in visible + delta
        assert unit_id in visible
    assert (
        GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
        == session.lifecycle.to_payload()
    )


def test_heroic_declaration_loads_modifier_ignore_permission_from_catalog() -> None:
    from tests.heroic_intervention_helpers import add_heroic_modifier, use_heroic
    from tests.phase15a_charge_test_support import _charge_modifier_ignore_ability_record

    from warhammer40k_core.core.army_catalog import ArmyCatalog
    from warhammer40k_core.core.datasheet import (
        CatalogAbilitySourceKind,
        CatalogAbilitySupport,
        CatalogJsonObject,
        DatasheetAbilityDescriptor,
    )

    base = ArmyCatalog.phase9a_canonical_content_pack()
    sheet = base.datasheet_by_id("core-intercessor-like-infantry")
    definition = _charge_modifier_ignore_ability_record(datasheet_id=sheet.datasheet_id).definition
    assert isinstance(definition.replay_payload, dict)
    ability = DatasheetAbilityDescriptor(
        ability_id=definition.ability_id,
        name=definition.name,
        source_id=definition.source_id,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description=definition.effect_descriptor,
        rule_ir_payload=cast(CatalogJsonObject, definition.replay_payload["rule_ir"]),
    )
    catalog = replace(
        base,
        datasheets=tuple(
            replace(row, abilities=(*row.abilities, ability))
            if row.datasheet_id == sheet.datasheet_id
            else row
            for row in base.datasheets
        ),
    )
    session, unit_id = heroic_session(natural=False, catalog=catalog)
    add_heroic_modifier(session, unit_id, delta=-20)
    declaration = use_heroic(session, unit_id)
    options = [o for o in declaration.options if o.option_id != unit_id]
    assert len(options) == 1
    session.submit_option(
        request_id=declaration.request_id,
        option_id=options[0].option_id,
        result_id="ignore-penalty",
    )
    state = session.lifecycle.state
    assert state is not None
    ignore_effect = next(
        e
        for e in state.persisting_effects_for_unit(unit_id)
        if e.source_rule_id == "core:modifier-ignore-selection"
    )
    assert ignore_effect.owner_player_id == "player-a"
    assert ignore_effect.expiration.player_id == "player-b"
    roll = latest_heroic_roll(session)
    assert roll.value == min(roll.roll_state.current_total, 6)
    assert roll.movement_budget.modified_roll.unbounded_value == roll.roll_state.current_total


def test_heroic_loads_conditional_declaration_grant_and_reroll_from_source_bundle() -> None:
    from tests.heroic_intervention_helpers import use_heroic
    from tests.phase15a_charge_test_support import _generated_snarling_protector_charge_lifecycle

    from warhammer40k_core.engine.charge_phase_state import ChargePhaseState

    lifecycle, units = _generated_snarling_protector_charge_lifecycle(
        game_id="order50-source-grant"
    )
    state = lifecycle.state
    assert state is not None
    state.active_player_id = "player-b"
    state.replace_charge_phase_state(
        ChargePhaseState(
            battle_round=state.battle_round,
            active_player_id="player-b",
            selected_unit_ids=(units["enemy"].unit_instance_id,),
            declared_target_unit_instance_ids_by_unit={
                units["enemy"].unit_instance_id: (units["psyker-anchor"].unit_instance_id,)
            },
            phase_complete=True,
        )
    )
    session = LocalGameSession(lifecycle)
    declaration = use_heroic(session, units["maulerfiend"].unit_instance_id, mode="leap_to_defend")
    grant = request_from(
        session.submit_option(
            request_id=declaration.request_id,
            option_id=units["maulerfiend"].unit_instance_id,
            result_id="source-declare",
        )
    )
    assert grant.decision_type == "select_charge_declaration_grant"
    restored = LocalGameSession(GameLifecycle.from_payload(lifecycle.to_payload()))
    option = next(o for o in grant.options if o.option_id != "decline_charge_declaration_grant")
    for branch in (session, restored):
        reroll = request_from(
            branch.submit_option(
                request_id=grant.request_id, option_id=option.option_id, result_id="source-grant"
            )
        )
        assert reroll.decision_type == "select_dice_reroll"
        assert {o.option_id for o in reroll.options} == {"decline", "reroll:0,1"}
        assert branch.lifecycle.state is not None
        effects = branch.lifecycle.state.persisting_effects_for_unit(
            units["maulerfiend"].unit_instance_id
        )
        grant_effect = next(e for e in effects if e.effect_id.startswith("source-grant:"))
        assert grant_effect.owner_player_id == "player-a"
        assert grant_effect.expiration.player_id == "player-b"
    assert session.lifecycle.to_payload() == restored.lifecycle.to_payload()
