"""15.07/15.11/15.12 at their existing interruption and target decision owners."""

import json
from copy import deepcopy
from typing import cast

import pytest

from tests.order135_counteroffensive_helpers import (
    native_combat_session,
    proposal_from_native_request,
    submit_native_combat_choice,
)
from tests.support.cavalcade_native_fight import view_evidence
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section15_fixtures import (
    binding,
    checkpoint,
    context,
    obj,
    offer,
    request,
    submit,
)
from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.ruleset_descriptor import FightPhaseStepKind
from warhammer40k_core.engine.charge_phase_state import ChargePhaseState
from warhammer40k_core.engine.decision_request import DecisionRequest, DecisionRequestPayload
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_order import FightPhaseState, FightsFirstRegistry
from warhammer40k_core.engine.fight_resolution import (
    MeleeDeclarationProposal,
    MeleeDeclarationProposalRequest,
    MeleeTargetAllocation,
    MeleeWeaponDeclaration,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.reserves import ReserveKind, ReserveState
from warhammer40k_core.engine.stratagem_catalog import eleventh_edition_core_stratagem_index
from warhammer40k_core.engine.stratagems import (
    StratagemTargetProposal,
    stratagem_decline_payload,
    stratagem_target_proposal_from_index,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind


@pytest.mark.parametrize("aircraft", [False, True])
def test_rapid_ingress_excludes_aircraft_with_same_native_reserve_control(
    section15_definitions: Section02Definitions, aircraft: bool
) -> None:
    from dataclasses import replace

    from tests.unit_keyword_helpers import with_unit_keywords

    _session, state, unit, _ = checkpoint(
        section15_definitions,
        phase=BattlePhase.MOVEMENT,
        active="opponent",
        materialize=False,
    )
    state.battle_round = 2
    army = state.army_definition_for_player("owner")
    assert army is not None
    native = army.unit_by_id(unit)
    if aircraft:
        # Explicit keyword contract on unchanged supported native models/bases.
        supplemented = with_unit_keywords(native, keywords=(*native.keywords, "AIRCRAFT"))
        assert supplemented.own_model_ids() == native.own_model_ids()
        assert [m.geometry for m in supplemented.own_models] == [
            m.geometry for m in native.own_models
        ]
        state.army_definitions[:] = [
            replace(a, units=(supplemented,)) if a.player_id == "owner" else a
            for a in state.army_definitions
        ]
    assert state.battlefield_state is not None
    state.replace_battlefield_state(state.battlefield_state.without_unit_placement(unit))
    state.record_reserve_state(
        ReserveState.declared_before_battle(
            player_id="owner", unit_instance_id=unit, reserve_kind=ReserveKind.STRATEGIC_RESERVES
        )
    )
    before = state.to_payload()
    proposal = stratagem_target_proposal_from_index(
        state=state,
        index=eleventh_edition_core_stratagem_index(),
        context=context(state, TimingTriggerKind.END_PHASE),
        handler_id="core:rapid-ingress",
        require_legal_affordable_target=True,
    )
    assert (proposal is None) is aircraft
    assert state.to_payload() == before


@pytest.mark.parametrize(
    ("round_number", "active", "kind", "legal"),
    [
        (1, "opponent", ReserveKind.STRATEGIC_RESERVES, False),
        (2, "owner", ReserveKind.STRATEGIC_RESERVES, False),
        (2, "opponent", ReserveKind.RESERVES, False),
        (2, "opponent", ReserveKind.STRATEGIC_RESERVES, True),
    ],
)
def test_rapid_ingress_only_opponent_end_movement_after_round_one_from_strategic_reserves(
    section15_definitions: Section02Definitions,
    round_number: int,
    active: str,
    kind: ReserveKind,
    legal: bool,
) -> None:
    session, state, unit, _ = checkpoint(
        section15_definitions, phase=BattlePhase.MOVEMENT, active=active
    )
    state.battle_round = round_number
    own = state.army_definition_for_player("owner")
    assert own is not None
    assert state.battlefield_state is not None
    state.replace_battlefield_state(state.battlefield_state.without_unit_placement(unit))
    state.record_reserve_state(
        ReserveState.declared_before_battle(
            player_id="owner",
            unit_instance_id=unit,
            reserve_kind=kind,
        )
    )
    ctx = context(state, TimingTriggerKind.END_PHASE)
    before = state.to_payload()
    proposal = stratagem_target_proposal_from_index(
        state=state,
        index=eleventh_edition_core_stratagem_index(),
        context=ctx,
        handler_id="core:rapid-ingress",
        require_legal_affordable_target=True,
    )
    assert (proposal is not None) is legal
    assert state.to_payload() == before
    if legal:
        req = offer(session, state, "rapid-ingress", ctx)
        placement = request(submit(session, req, unit))
        assert placement.decision_type == "submit_placement_proposal"
        assert state.command_point_total("owner") == 3
        reserve = state.reserve_state_for_unit(unit)
        assert reserve is not None
        assert reserve.status.value == "in_reserves"
        assert state.battlefield_state.unit_placement_or_none(unit) is None
        prior = session.lifecycle.to_payload()
        invalid = session.submit_parameterized_payload(
            request_id=placement.request_id,
            result_id="s15:bad-placement",
            payload=None,
        )
        assert invalid.status_kind is LifecycleStatusKind.INVALID
        assert session.lifecycle.to_payload() == prior
        from tests.support.section03_fixtures import placement as native_placement
        from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind
        from warhammer40k_core.engine.movement_proposals import (
            PlacementProposalPayload,
            ProposalKind,
        )
        from warhammer40k_core.geometry.pose import Pose

        placed = native_placement(own.unit_by_id(unit), (Pose.at(1, 22),))
        payload = PlacementProposalPayload(
            placement.request_id,
            ProposalKind.STRATEGIC_RESERVES,
            unit,
            BattlefieldPlacementKind.STRATEGIC_RESERVES,
            attempted_placement=placed,
        )
        status = session.submit_parameterized_payload(
            request_id=placement.request_id,
            result_id="s15:legal-ingress",
            payload=validate_json_value(payload.to_payload()),
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID
        arrived = state.reserve_state_for_unit(unit)
        assert arrived is not None
        assert arrived.status.value == "arrived"
        assert state.battlefield_state.unit_placement_by_id(unit).model_placements[
            0
        ].pose == Pose.at(1, 22)


@pytest.mark.parametrize(("mode", "cp"), [("leap_to_defend", 1), ("into_the_fray", 2)])
def test_heroic_intervention_enters_real_charge_with_mode_chosen_before_roll(
    section15_definitions: Section02Definitions, mode: str, cp: int
) -> None:
    session, state, unit, enemy = checkpoint(
        section15_definitions,
        phase=BattlePhase.CHARGE,
        active="opponent",
        distance=5,
        seed="section15:heroic:private-0",
    )
    # Explicit completed enemy Charge checkpoint; no earlier charge is certified.
    state.charge_phase_state = ChargePhaseState(
        state.battle_round,
        "opponent",
        phase_complete=True,
        declared_target_unit_instance_ids_by_unit={enemy: (unit,)},
    )
    req = offer(session, state, "heroic-intervention", context(state, TimingTriggerKind.END_PHASE))
    selection = request(submit(session, req, unit, effect={"mode": mode}))
    assert selection.decision_type == "select_charging_unit"
    assert unit in {o.option_id for o in selection.options}
    assert state.command_point_total("owner") == 4 - cp
    interrupted = state.charge_phase_state
    assert interrupted is not None
    assert interrupted.interruption is not None
    assert interrupted.interruption.allowed_target_ids == (
        None if mode == "into_the_fray" else (enemy,)
    )
    assert interrupted.interruption.target_range_inches == (6 if mode == "into_the_fray" else 12)
    assert (interrupted.interruption.roll_limit is not None) is (mode == "into_the_fray")
    assert state.active_player_id == "opponent"
    assert state.effective_active_player_id() == "owner"
    targets = request(
        session.submit_option(
            request_id=selection.request_id, result_id="s15:charge", option_id=unit
        )
    )
    assert targets.decision_type == "select_charge_targets"
    assert state.charge_phase_state.distance_states
    roll = state.charge_phase_state.distance_states[-1].roll_result
    assert len(roll.roll_state.current_values) == 2
    if mode == "into_the_fray":
        assert roll.value <= 6


@pytest.mark.parametrize(
    ("sheet", "legal"), [("000004078", True), ("000000968", True), ("000000599", False)]
)
def test_heroic_native_vehicle_exception_requires_character_or_walker(
    section15_definitions: Section02Definitions, sheet: str, legal: bool
) -> None:
    from warhammer40k_core.engine.stratagems_geometry import (
        _heroic_intervention_target_binding_error,
    )

    _session, state, unit, _ = checkpoint(
        section15_definitions, sheet=sheet, phase=BattlePhase.CHARGE, active="opponent", distance=8
    )
    reason = _heroic_intervention_target_binding_error(
        state=state, player_id="owner", target_binding=binding(unit)
    )
    assert (reason is None) is legal
    if not legal:
        assert reason == "heroic_intervention_vehicle_not_character_or_walker"


@pytest.mark.parametrize("active", ["owner", "opponent"])
def test_counteroffensive_own_turn_denial_and_opponent_turn_fights_first_activation(
    section15_definitions: Section02Definitions, active: str
) -> None:
    session, state, unit, enemy = checkpoint(section15_definitions, active=active, distance=2)
    policy = state.runtime_ruleset_descriptor().fight_policy
    state.fight_phase_state = FightPhaseState.start(
        battle_round=state.battle_round,
        active_player_id=active,
        policy=policy,
        engaged_at_fight_step_start_unit_ids=(unit, enemy),
        fights_first_registry=FightsFirstRegistry(),
    ).with_current_step(current_step=FightPhaseStepKind.FIGHT, policy=policy)
    ctx = context(
        state,
        TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_HAS_FOUGHT,
        {"fought_unit_instance_id": enemy, "eligible_unit_instance_ids": [unit]},
    )
    proposal = stratagem_target_proposal_from_index(
        state=state,
        index=eleventh_edition_core_stratagem_index(),
        context=ctx,
        handler_id="core:counteroffensive",
        require_legal_affordable_target=True,
    )
    assert (proposal is not None) is (active == "opponent")
    if active == "opponent":
        req = offer(session, state, "counteroffensive", ctx)
        status = submit(session, req, unit)
        assert status.status_kind is not LifecycleStatusKind.INVALID
        fight = state.fight_phase_state
        assert fight is not None
        assert fight.active_activation is not None
        assert fight.active_activation.unit_instance_id == unit
        assert state.command_point_total("owner") == 2
        assert any(
            isinstance(e.effect_payload, dict)
            and e.effect_payload.get("effect_kind") == "fights_first"
            for e in state.persisting_effects
        )
        _assert_counteroffensive_viewer_branches()


def _assert_counteroffensive_viewer_branches() -> None:
    session = native_combat_session(first_player="player-a")
    for _ in range(100):
        pending = request(session.advance_until_decision_or_terminal())
        if (
            pending.decision_type == "submit_stratagem_target_proposal"
            and proposal_from_native_request(pending).stratagem_id == "counteroffensive"
        ):
            break
        submit_native_combat_choice(session, pending, first_player="player-a")
    else:
        raise AssertionError("Native Counteroffensive reaction was not reached.")

    viewer = ViewerContext.for_player("player-a")
    opponent = ViewerContext.for_player("player-b")
    issued = session.view_for_context(viewer=viewer)["pending_decision"]
    assert issued is not None
    assert issued["actor_id"] == "player-a"
    assert issued["request_id"] != pending.request_id
    assert [option["option_id"] for option in issued["options"]] == ["submit_parameterized_payload"]
    body = obj(issued["payload"])
    assert body["declinable"] is True
    assert body["interrupts_parent"] is True
    proposal = StratagemTargetProposal.from_payload(body["proposal_request"])
    assert proposal.context.active_player_id == "player-b"
    assert proposal.catalog_record.definition.command_point_cost == 2
    trigger = obj(proposal.context.trigger_payload)
    assert trigger["fought_unit_instance_id"] == "army-beta:one"
    assert trigger["eligible_unit_instance_ids"] == ["army-alpha:one", "army-alpha:two"]

    decline = stratagem_decline_payload()
    before = session.lifecycle.to_payload()
    with pytest.raises(GameLifecycleError, match="Viewer does not own the pending decision"):
        session.submit_viewer_parameterized_payload(
            viewer=opponent,
            request_id=issued["request_id"],
            payload=decline,
            result_id="counteroffensive:wrong-viewer",
        )
    with pytest.raises(GameLifecycleError, match="request is stale or unissued"):
        session.submit_viewer_parameterized_payload(
            viewer=viewer,
            request_id=pending.request_id,
            payload=decline,
            result_id="counteroffensive:unissued-request",
        )
    assert session.lifecycle.to_payload() == before
    legal = proposal.with_binding(binding("army-alpha:one", "player-a"))
    drifted = legal.to_payload()
    drifted["context"]["active_player_id"] = "player-a"
    for payload, reason in (
        ({"proposal": None}, "malformed_payload"),
        ({"proposal": drifted}, "wrong_context"),
        (
            {"proposal": proposal.with_binding(binding("army-beta:one", "player-a")).to_payload()},
            "counteroffensive_target_not_eligible_to_fight",
        ),
    ):
        invalid = session.submit_viewer_parameterized_payload(
            viewer=viewer,
            request_id=issued["request_id"],
            payload=validate_json_value(payload),
            result_id=f"counteroffensive:invalid:{reason}",
        )
        assert invalid.status_kind is LifecycleStatusKind.INVALID
        assert invalid.payload == {"invalid_reason": reason}
        assert session.lifecycle.to_payload() == before
    assert session.view_for_context(viewer=viewer)["pending_decision"] == issued

    _assert_counteroffensive_continuation(
        session.fork(),
        viewer=viewer,
        request_id=issued["request_id"],
        payload=decline,
        use=False,
    )
    _assert_counteroffensive_continuation(
        session.fork(),
        viewer=viewer,
        request_id=issued["request_id"],
        payload=validate_json_value({"proposal": legal.to_payload()}),
        use=True,
    )
    assert session.lifecycle.to_payload() == before


def _assert_counteroffensive_continuation(
    session: LocalGameSession,
    *,
    viewer: ViewerContext,
    request_id: str,
    payload: JsonValue,
    use: bool,
) -> None:
    state = session.lifecycle.state
    assert state is not None
    cp = state.command_point_total("player-a")
    opponent_cp = state.command_point_total("player-b")
    controller = session.lifecycle.decision_controller
    event_count = len(controller.event_log.records)
    status = session.submit_viewer_parameterized_payload(
        viewer=viewer,
        request_id=request_id,
        payload=payload,
        result_id="counteroffensive:use" if use else "counteroffensive:decline",
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    next_request = request(status)
    events = [e.event_type for e in controller.event_log.records_since(event_count)]
    assert state.command_point_total("player-b") == opponent_cp
    assert state.fight_phase_state is not None
    if use:
        assert state.command_point_total("player-a") == cp - 2
        (record,) = state.stratagem_use_records
        assert record.command_point_cost == 2
        assert record.targeted_unit_instance_ids == ("army-alpha:one",)
        activation = state.fight_phase_state.active_activation
        assert activation is not None
        assert activation.unit_instance_id == "army-alpha:one"
        assert activation.interrupt_id == f"counteroffensive:{record.use_id}"
        assert events.index("stratagem_used") < events.index("counteroffensive_activation_selected")
        assert next_request.actor_id == "player-a"
        assert proposal_from_native_request(next_request).stratagem_id == "epic-challenge"
    else:
        assert state.command_point_total("player-a") == cp
        assert not state.stratagem_use_records
        assert state.fight_phase_state.active_activation is None
        assert events.index("stratagem_window_declined") < events.index("reaction_parent_resumed")
        assert next_request.decision_type == "select_fight_activation"
        assert next_request.actor_id == "player-b"
        assert [option.option_id for option in next_request.options] == [
            "fight:normal:army-beta:two"
        ]

    checkpoint = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(json.loads(json.dumps(checkpoint)))
    assert restored.to_persistence_payload() == checkpoint
    for player in state.player_ids:
        assert view_evidence(restored, player) == view_evidence(session, player)
    if use:
        _assert_counteroffensive_melee_restore(restored, viewer=viewer)


def _assert_counteroffensive_melee_restore(
    session: LocalGameSession, *, viewer: ViewerContext
) -> None:
    epic = session.view_for_context(viewer=viewer)["pending_decision"]
    assert epic is not None
    prior = session.to_persistence_payload()
    original_frame = session.lifecycle.reaction_queue.frames[-1]
    status = session.submit_viewer_parameterized_payload(
        viewer=viewer,
        request_id=epic["request_id"],
        payload=stratagem_decline_payload(),
        result_id="counteroffensive:decline-epic-challenge",
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    melee = request(status)
    assert melee.decision_type == "submit_melee_declaration"
    assert session.lifecycle.reaction_queue.frames == (
        original_frame.with_request_id(melee.request_id),
    )
    checkpoint = session.to_persistence_payload()
    assert obj(checkpoint)["source_identity"] == obj(prior)["source_identity"]
    rng_before = obj(obj(prior)["rng_state"])
    rng_after = obj(obj(checkpoint)["rng_state"])
    assert rng_after["seed"] == rng_before["seed"]
    assert rng_after["draw_count"] == rng_before["draw_count"]
    assert rng_after["history"][: len(rng_before["history"])] == rng_before["history"]

    drifted_frame = session.lifecycle.to_payload()
    drifted_frame["reaction_queue"]["frames"][-1]["request_id"] = original_frame.request_id
    with pytest.raises(GameLifecycleError, match="active frame request_id drift"):
        GameLifecycle.from_payload(drifted_frame)

    drifted_source = deepcopy(session.lifecycle.to_payload())
    (pending,) = drifted_source["decisions"]["queue"]["pending_requests"]
    obj(obj(pending["payload"])["proposal_request"])["source_decision_result_id"] = (
        "other-fight-activation"
    )
    with pytest.raises(GameLifecycleError, match="pending decision_type drift"):
        GameLifecycle.from_payload(drifted_source)

    for field, value in (("phase", "shooting"), ("decision_type", "submit_shooting_declaration")):
        drifted_request = deepcopy(session.lifecycle.to_payload())
        (pending,) = drifted_request["decisions"]["queue"]["pending_requests"]
        obj(obj(pending["payload"])["proposal_request"])[field] = value
        with pytest.raises(GameLifecycleError, match=f"melee proposal_request {field} drift"):
            GameLifecycle.from_payload(drifted_request)

    drifted_token = session.lifecycle.to_payload()
    drifted_token["reaction_queue"]["frames"][-1]["resume_token"] = "other-resume-token"
    with pytest.raises(GameLifecycleError, match="melee reaction continuation drift"):
        GameLifecycle.from_payload(drifted_token)

    drifted_window = session.lifecycle.to_payload()
    drifted_window["reaction_queue"]["frames"][-1]["reaction_window"]["timing_window"][
        "window_id"
    ] = "other-timing-window"
    with pytest.raises(GameLifecycleError, match="melee reaction continuation drift"):
        GameLifecycle.from_payload(drifted_window)

    restored = LocalGameSession.from_persistence_payload(json.loads(json.dumps(checkpoint)))
    assert restored.to_persistence_payload() == checkpoint
    assert restored.lifecycle.reaction_queue.frames == session.lifecycle.reaction_queue.frames
    for player in ("player-a", "player-b"):
        assert view_evidence(restored, player) == view_evidence(session, player)

    issued = restored.view_for_context(viewer=viewer)["pending_decision"]
    assert issued is not None
    opponent = ViewerContext.for_player("player-b")
    opponent_issued = restored.view_for_context(viewer=opponent)["pending_decision"]
    assert opponent_issued is not None
    assert opponent_issued["actor_id"] == "player-a"
    assert len({issued["request_id"], opponent_issued["request_id"], melee.request_id}) == 3
    with pytest.raises(GameLifecycleError, match="Viewer does not own the pending decision"):
        restored.submit_viewer_parameterized_payload(
            viewer=opponent,
            request_id=opponent_issued["request_id"],
            payload=None,
            result_id="counteroffensive:opponent-declares-melee",
        )
    assert restored.to_persistence_payload() == checkpoint

    proposal = MeleeDeclarationProposalRequest.from_decision_request(
        DecisionRequest.from_payload(cast(DecisionRequestPayload, issued))
    )
    assert proposal.unit_instance_id == "army-alpha:one"
    weapon = obj(proposal.available_weapons[0])
    target = proposal.target_unit_instance_ids[0]
    model_id, gear_id, profile_id, instance_id = (
        weapon[key]
        for key in ("model_instance_id", "wargear_id", "weapon_profile_id", "weapon_instance_id")
    )
    assert isinstance(model_id, str)
    assert isinstance(gear_id, str)
    assert isinstance(profile_id, str)
    assert isinstance(instance_id, str)
    payload = validate_json_value(
        MeleeDeclarationProposal(
            proposal.request_id,
            proposal.proposal_kind,
            proposal.actor_id,
            proposal.battle_round,
            proposal.unit_instance_id,
            proposal.source_decision_request_id,
            proposal.source_decision_result_id,
            (
                MeleeWeaponDeclaration(
                    model_id,
                    gear_id,
                    profile_id,
                    (MeleeTargetAllocation(target),),
                    weapon_instance_id=instance_id,
                ),
            ),
        ).to_payload()
    )
    result_id = "counteroffensive:declare-melee"
    for game in (session, restored):
        status = game.submit_viewer_parameterized_payload(
            viewer=viewer, request_id=issued["request_id"], payload=payload, result_id=result_id
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID
        assert any(
            event.event_type == "melee_declaration_accepted"
            for event in game.lifecycle.decision_controller.event_log.records
            if isinstance(event.payload, dict) and event.payload.get("result_id") == result_id
        )
    assert restored.to_persistence_payload() == session.to_persistence_payload()
