"""Order 48: charge-end authority, capped damage and suspended continuation."""

import pytest
from tests.crushing_impact_helpers import complete_charge, crushing_session

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.damage_allocation import FeelNoPainSource
from warhammer40k_core.engine.event_log import canonical_json
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus


@pytest.mark.parametrize("keyword", ["VEHICLE", "MONSTER"])
@pytest.mark.parametrize("attached", [False, True])
def test_charge_completion_offers_crushing_impact(keyword: str, attached: bool) -> None:
    session = crushing_session(keyword=keyword, attached=attached)
    status = complete_charge(session)
    request = status.decision_request
    assert request is not None
    assert request.decision_type == "use_stratagem"
    options = [
        o for o in request.options if o.option_id.startswith("use-stratagem:crushing-impact:")
    ]
    assert options
    if attached:
        assert any("army-alpha:leader" in o.option_id for o in options)


@pytest.mark.parametrize(
    ("attached", "toughness", "wounds", "fnp", "decline"),
    [
        (False, 4, 2, False, True),
        (False, 4, 2, False, False),
        (False, 96, 20, True, False),
        (False, 96, 1, False, False),
        (True, 96, 1, False, False),
        (True, 12, 2, True, False),
    ],
)
def test_crushing_impact_restores_both_damage_sides_and_resumes_charge(
    attached: bool,
    toughness: int,
    wounds: int,
    fnp: bool,
    decline: bool,
) -> None:
    session = crushing_session(
        attached=attached,
        toughness=toughness,
        wounds=wounds,
        enemy_attached=attached and toughness == 96,
    )
    state = session.lifecycle.state
    assert state is not None
    if fnp:
        for army in state.army_definitions:
            for unit in army.units:
                for model in unit.own_models:
                    state.record_model_feel_no_pain_sources(
                        model_instance_id=model.model_instance_id,
                        sources=(FeelNoPainSource(source_id="order48:fnp", threshold=5),),
                        decline_allowed=True,
                    )
    request = complete_charge(session).decision_request
    assert request is not None
    assert request.decision_type == "use_stratagem"
    before_cp = state.command_point_total("player-a")
    saved = session.to_persistence_payload()
    session = LocalGameSession.from_persistence_payload(saved)
    assert session.to_persistence_payload() == saved
    option = next(
        o
        for o in request.options
        if (
            o.option_id == "decline_stratagem_window"
            if decline
            else (
                o.option_id.startswith("use-stratagem:crushing-impact:")
                and (not attached or "army-alpha:leader" in o.option_id)
            )
        )
    )
    status = session.submit_option(
        request_id=request.request_id, option_id=option.option_id, result_id="order48:use"
    )
    seen_owners: set[str] = set()
    restored_boundaries: set[tuple[str, str, tuple[str, ...]]] = set()
    saw_fnp = False
    while status.decision_request is not None and status.decision_request.decision_type in {
        "select_mortal_wound_model",
        "select_feel_no_pain",
    }:
        nested = status.decision_request
        assert nested.actor_id is not None
        seen_owners.add(nested.actor_id)
        saw_fnp |= nested.decision_type == "select_feel_no_pain"
        assert nested.actor_id in {"player-a", "player-b"}
        for viewer in ("player-a", "player-b"):
            assert "rule_mortal_wound_destruction_evidence" not in canonical_json(
                session.view(viewer_player_id=viewer)
            )
        current_state = session.lifecycle.state
        assert current_state is not None
        living_components = tuple(
            unit.unit_instance_id
            for army in current_state.army_definitions
            for unit in army.units
            if any(model.is_alive for model in unit.own_models)
        )
        boundary = nested.actor_id, nested.decision_type, living_components
        if boundary not in restored_boundaries:
            saved = session.to_persistence_payload()
            session = LocalGameSession.from_persistence_payload(saved)
            assert session.to_persistence_payload() == saved
            restored_boundaries.add(boundary)
        status = session.submit_option(
            request_id=nested.request_id,
            option_id=nested.options[0].option_id,
            result_id=f"order48:{nested.request_id}",
        )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    assert saw_fnp == fnp
    state = session.lifecycle.state
    assert state is not None
    assert state.command_point_total("player-a") == before_cp - (0 if decline else 1)
    assert len(state.stratagem_use_records) == (0 if decline else 1)
    events = [
        e.payload
        for e in session.lifecycle.decision_controller.event_log.records
        if e.event_type == "crushing_impact_resolved"
    ]
    assert len(events) == (0 if decline else 1)
    if not decline:
        event = events[0]
        assert isinstance(event, dict)
        assert isinstance(option.payload, dict)
        binding = option.payload["target_binding"]
        selection = option.payload["effect_selection"]
        assert isinstance(binding, dict)
        assert isinstance(selection, dict)
        assert event["source_unit_instance_id"] == binding["target_unit_instance_id"]
        assert event["target_unit_instance_id"] == selection["enemy_target_unit_instance_id"]
        assert event["source_model_instance_id"] == selection["model_instance_id"]
        roll = event["roll_state"]
        assert isinstance(roll, dict)
        from typing import cast

        from warhammer40k_core.core.dice import DiceRollState, DiceRollStatePayload

        dice = DiceRollState.from_payload(cast(DiceRollStatePayload, roll)).current_values
        assert len(dice) == toughness
        assert event["source_mortal_wounds"] == min(6, dice.count(1))
        assert event["enemy_mortal_wounds"] == min(6, sum(d >= 5 for d in dice))
        if toughness == 96:
            assert dice.count(1) > 6
            assert event["source_mortal_wounds"] == event["enemy_mortal_wounds"] == 6
            assert seen_owners == {"player-a", "player-b"}
        if wounds == 1:
            from tests.crushing_impact_helpers import ENEMY, SOURCE

            from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

            assert not rules_unit_view_by_id(state=state, unit_instance_id=SOURCE).alive_models()
            assert not rules_unit_view_by_id(state=state, unit_instance_id=ENEMY).alive_models()
    next_request = status.decision_request
    assert next_request is not None
    assert next_request.decision_type == "select_charging_unit"
    for viewer in ("player-a", "player-b"):
        from warhammer40k_core.adapters.event_stream import EventStreamCursor

        visible = canonical_json(session.view(viewer_player_id=viewer))
        assert "object at 0x" not in visible
        assert "timing_participant_id" not in visible
        delta = canonical_json(session.events_since(EventStreamCursor(), viewer_player_id=viewer))
        assert "mortal_wound_application_started" not in delta
        assert "logical_death_cause_binding" not in delta
        assert "timing_batch_transition" not in delta
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="order48:replay"))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize(
    "drift",
    [
        "cp",
        "phase",
        "source_keyword",
        "source_model",
        "enemy_models",
        "source_range",
        "enemy_range",
    ],
)
def test_crushing_impact_revalidates_without_spending_or_consuming(drift: str) -> None:
    from tests.core_stratagem_helpers import _replace_unit_keywords, _replace_unit_poses
    from tests.crushing_impact_helpers import ENEMY, SOURCE

    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
    from warhammer40k_core.geometry.pose import Pose

    session = crushing_session()
    request = complete_charge(session).decision_request
    assert request is not None
    option = next(
        o for o in request.options if o.option_id.startswith("use-stratagem:crushing-impact:")
    )
    assert isinstance(option.payload, dict)
    selection = option.payload["effect_selection"]
    assert isinstance(selection, dict)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    if drift == "cp":
        state.spend_command_points(
            player_id="player-a",
            amount=state.command_point_total("player-a"),
            source_id="order48:other-spend",
        )
    elif drift == "phase":
        state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    elif drift == "source_keyword":
        _replace_unit_keywords(state, unit_instance_id=SOURCE, keywords=("INFANTRY",))
    elif drift in {"source_model", "enemy_models"}:
        from typing import cast

        ids = (
            (cast(str, selection["model_instance_id"]),)
            if drift == "source_model"
            else tuple(
                m.model_instance_id
                for m in rules_unit_view_by_id(state=state, unit_instance_id=ENEMY).alive_models()
            )
        )
        state.battlefield_state = state.battlefield_state.with_removed_models(ids)
    else:
        unit_id = SOURCE if drift == "source_range" else ENEMY
        _replace_unit_poses(
            state,
            unit_instance_id=unit_id,
            poses=tuple(Pose.at(60 + i * 1.6, 60) for i in range(5)),
        )
    before = state.to_payload(), session.lifecycle.decision_controller.to_payload()
    status = session.submit_option(
        request_id=request.request_id, option_id=option.option_id, result_id="order48:stale"
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert (state.to_payload(), session.lifecycle.decision_controller.to_payload()) == before


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"model_instance_id": "x"},
        {"model_instance_id": "x", "enemy_target_unit_instance_id": 1},
        {"model_instance_id": "x", "enemy_target_unit_instance_id": "y", "extra": 1},
    ],
)
def test_crushing_impact_selection_is_closed(payload: object) -> None:
    from typing import cast

    from warhammer40k_core.engine.crushing_impact_selection import CrushingImpactSelection
    from warhammer40k_core.engine.event_log import JsonValue
    from warhammer40k_core.engine.phase import GameLifecycleError

    with pytest.raises(GameLifecycleError):
        CrushingImpactSelection.from_payload(cast(JsonValue, payload))


def test_crushing_impact_independent_caps_and_dice_validation() -> None:
    from warhammer40k_core.engine.crushing_impact_selection import crushing_impact_mortal_wounds
    from warhammer40k_core.engine.phase import GameLifecycleError

    assert crushing_impact_mortal_wounds((1,) * 9 + (5,) * 8) == (6, 6)
    assert crushing_impact_mortal_wounds((2, 3, 4)) == (0, 0)
    for invalid in ((), (0,), (7,), (True,)):
        with pytest.raises(GameLifecycleError):
            crushing_impact_mortal_wounds(invalid)


def test_crushing_impact_rolls_the_selected_attached_models_toughness() -> None:
    from dataclasses import replace

    from tests.crushing_impact_helpers import SOURCE
    from tests.generic_modifier_helpers import generic_effect

    from warhammer40k_core.engine.effects import EffectExpiration
    from warhammer40k_core.engine.phase import BattlePhase

    session = crushing_session(attached=True, toughness=4, leader_toughness=9, wounds=20)
    state = session.lifecycle.state
    assert state is not None
    state.record_persisting_effect(
        replace(
            generic_effect(
                effect_id="order48:toughness",
                owner_player_id="player-a",
                target_unit_instance_ids=(f"attached-unit:{SOURCE}",),
                target_kind="this_unit",
                effect_kind="modify_characteristic",
                parameters={"characteristic": "toughness", "delta": 2},
            ),
            started_battle_round=state.battle_round,
            started_phase=BattlePhase.CHARGE,
            expiration=EffectExpiration.end_phase(
                battle_round=state.battle_round, phase=BattlePhase.CHARGE, player_id="player-a"
            ),
        )
    )
    request = complete_charge(session).decision_request
    assert request is not None
    choices = [
        o for o in request.options if o.option_id.startswith("use-stratagem:crushing-impact:")
    ]
    assert len(choices) == 6
    option = next(o for o in choices if "army-alpha:leader" in o.option_id)
    status = session.submit_option(
        request_id=request.request_id,
        option_id=option.option_id,
        result_id="order48:selected-toughness",
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    state = session.lifecycle.state
    assert state is not None
    use = state.stratagem_use_records[-1]
    assert use.targeted_unit_instance_ids == (f"attached-unit:{SOURCE}",)
    from typing import cast

    from warhammer40k_core.core.dice import DiceRollState, DiceRollStatePayload
    from warhammer40k_core.engine.mortal_wound_model_allocation import (
        mortal_wound_resolution_source_context,
    )

    nested = status.decision_request
    assert nested is not None
    context = mortal_wound_resolution_source_context(nested)
    assert isinstance(context, dict)
    roll = DiceRollState.from_payload(cast(DiceRollStatePayload, context["roll_state"]))
    assert len(roll.current_values) == 11


def test_crushing_impact_rejects_a_destroyed_but_retained_selected_model() -> None:
    from tests.crushing_impact_helpers import SOURCE
    from tests.fight_on_death_helpers import retain_destroyed_model_for_fixture

    from warhammer40k_core.engine.damage_allocation import DamageKind, apply_damage_to_model
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    session = crushing_session()
    request = complete_charge(session).decision_request
    assert request is not None
    option = next(
        o for o in request.options if o.option_id.startswith("use-stratagem:crushing-impact:")
    )
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    model = rules_unit_view_by_id(state=state, unit_instance_id=SOURCE).alive_models()[0]
    assert model.model_instance_id in option.option_id
    placement = state.battlefield_state.model_placement_by_id(model.model_instance_id)
    apply_damage_to_model(
        state=state,
        target_unit_instance_id=SOURCE,
        model_instance_id=model.model_instance_id,
        damage=model.wounds_remaining,
        damage_kind=DamageKind.NORMAL,
        remove_destroyed_model=False,
    )
    retain_destroyed_model_for_fixture(
        state=state,
        decisions=session.lifecycle.decision_controller,
        placement=placement,
        effect_id="order48:retained",
        source_rule_id="order48:test:fight-on-death",
        source_phase=BattlePhase.CHARGE,
    )
    before = state.to_payload(), session.lifecycle.decision_controller.to_payload()
    status = session.submit_option(
        request_id=request.request_id, option_id=option.option_id, result_id="order48:retained"
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert (state.to_payload(), session.lifecycle.decision_controller.to_payload()) == before


@pytest.mark.parametrize("duplicated", [False, True])
def test_crushing_impact_finishes_deadly_demise_before_resuming_charge(duplicated: bool) -> None:
    from tests.crushing_impact_helpers import crushing_deadly_demise_session

    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    session = crushing_deadly_demise_session(duplicated=duplicated)
    request = complete_charge(session).decision_request
    assert request is not None
    option = next(
        o for o in request.options if o.option_id.startswith("use-stratagem:crushing-impact:")
    )
    status = session.submit_option(
        request_id=request.request_id, option_id=option.option_id, result_id="order48:demise-use"
    )
    while (request := status.decision_request) is not None:
        if request.decision_type == "select_charging_unit":
            break
        assert request.decision_type in {
            "select_mortal_wound_model",
            "select_destruction_reaction",
        }, request
        if request.decision_type == "select_destruction_reaction":
            assert duplicated
            assert len(request.options) == 2
            assert all(
                option.option_id.startswith("order48:deadly-demise:") for option in request.options
            )
        saved = session.to_persistence_payload()
        session = LocalGameSession.from_persistence_payload(saved)
        assert session.to_persistence_payload() == saved
        status = session.submit_option(
            request_id=request.request_id,
            option_id=request.options[0].option_id,
            result_id=f"order48:demise:{request.request_id}",
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
    assert request is not None
    events = session.lifecycle.decision_controller.event_log.records
    assert sum(e.event_type == "crushing_impact_resolved" for e in events) == 1
    assert any(e.event_type == "destruction_reaction_resolved" for e in events)
    state = session.lifecycle.state
    assert state is not None
    for unit_id in ("army-alpha:next", "army-beta:other"):
        assert len(rules_unit_view_by_id(state=state, unit_instance_id=unit_id).alive_models()) == 4
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="order48:demise-replay"))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize("drift", ["application", "remaining", "missing_start", "early_completion"])
def test_crushing_impact_rejects_destruction_continuation_history_drift(drift: str) -> None:
    from tests.crushing_impact_helpers import crushing_deadly_demise_session

    from warhammer40k_core.engine.event_log import EventLog
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.mortal_wound_model_allocation import (
        mortal_wound_resolution_source_context,
    )
    from warhammer40k_core.engine.phase import GameLifecycleError

    session = crushing_deadly_demise_session()
    request = complete_charge(session).decision_request
    assert request is not None
    option = next(
        o for o in request.options if o.option_id.startswith("use-stratagem:crushing-impact:")
    )
    status = session.submit_option(
        request_id=request.request_id, option_id=option.option_id, result_id="order48:tamper-use"
    )
    while (request := status.decision_request) is not None:
        assert request.decision_type == "select_mortal_wound_model"
        context = mortal_wound_resolution_source_context(request)
        assert isinstance(context, dict)
        if context["source_kind"] == "rule_model_destruction_deadly_demise":
            break
        status = session.submit_option(
            request_id=request.request_id,
            option_id=request.options[0].option_id,
            result_id=f"order48:tamper:{request.request_id}",
        )
    assert request is not None
    payload = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(payload).to_payload() == payload
    events = payload["decisions"]["event_log"]
    start = next(
        event for event in events if event["event_type"] == "rule_mortal_wound_destructions_started"
    )
    body = start["payload"]
    assert isinstance(body, dict)
    progress = body["progress"]
    assert isinstance(progress, dict)
    if drift == "application":
        application = body["application"]
        assert isinstance(application, dict)
        application["mortal_wounds"] = 5
    elif drift == "remaining":
        progress["remaining_mortal_wounds"] = 1
    elif drift == "missing_start":
        start["event_type"] = "altered_completion_start"
    else:
        log = EventLog.from_payload(events)
        log.append(
            "rule_mortal_wound_destructions_completed",
            {"application_id": progress["application_id"]},
        )
        payload["decisions"]["event_log"] = log.to_payload()
    with pytest.raises(GameLifecycleError):
        GameLifecycle.from_payload(payload)


def test_crushing_impact_rejects_a_missing_completed_destruction_receipt() -> None:
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError

    session = crushing_session()
    request = complete_charge(session).decision_request
    assert request is not None
    option = next(
        o for o in request.options if o.option_id.startswith("use-stratagem:crushing-impact:")
    )
    status = session.submit_option(
        request_id=request.request_id, option_id=option.option_id, result_id="order48:receipt-use"
    )
    while (
        request := status.decision_request
    ) is not None and request.decision_type == "select_mortal_wound_model":
        status = session.submit_option(
            request_id=request.request_id,
            option_id=request.options[0].option_id,
            result_id=f"order48:receipt:{request.request_id}",
        )
    payload = session.lifecycle.to_payload()
    events = payload["decisions"]["event_log"]
    completed = next(
        event
        for event in events
        if event["event_type"] == "rule_mortal_wound_destructions_completed"
    )
    completed["event_type"] = "altered_completion_receipt"
    with pytest.raises(GameLifecycleError):
        GameLifecycle.from_payload(payload)
