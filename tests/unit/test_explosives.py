"""Order 41: selected-model Explosives through the shared decision path."""

from dataclasses import replace

import pytest
from tests.core_stratagem_helpers import _replace_unit_keywords, _replace_unit_poses
from tests.explosives_helpers import explosives_scene

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.explosives_selection import ExplosivesSelection
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.stratagem_catalog import (
    eleventh_edition_core_stratagem_catalog_records,
)
from warhammer40k_core.geometry.pose import Pose


def test_explosives_source_uses_during_phase_finite_selection() -> None:
    row = next(
        r
        for r in eleventh_edition_core_stratagem_catalog_records()
        if r.definition.stratagem_id == "explosives"
    )
    assert row.definition.timing.trigger_kind.value == "during_phase"
    assert row.definition.target_spec.enumerable


@pytest.mark.parametrize("keyword", ["EXPLOSIVES", "GRENADES"])
def test_explosives_offers_each_matching_source_model(keyword: str) -> None:
    lifecycle, units = explosives_scene(keyword=keyword)
    session = LocalGameSession(lifecycle=lifecycle)
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    assert request.decision_type == "use_stratagem"
    options = [o for o in request.options if o.option_id.startswith("use-stratagem:explosives:")]
    assert len(options) == 2
    selections = [o.payload["effect_selection"] for o in options if isinstance(o.payload, dict)]
    assert {ExplosivesSelection.from_payload(s).source_model_instance_id for s in selections} == {
        m.model_instance_id for m in units["source"].own_models
    }


@pytest.mark.parametrize(
    ("decline", "attached", "fnp"),
    [(True, False, False), (False, False, False), (False, True, True)],
)
def test_explosives_facade_restores_replays_and_resumes_shooting(
    decline: bool, attached: bool, fnp: bool
) -> None:
    from warhammer40k_core.engine.damage_allocation import FeelNoPainSource
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    lifecycle, units = explosives_scene(attached=attached)
    state = lifecycle.state
    assert state is not None
    if fnp:
        for unit in units.values():
            if unit.unit_instance_id.startswith("army-beta:"):
                for model in unit.own_models:
                    state.record_model_feel_no_pain_sources(
                        model_instance_id=model.model_instance_id,
                        sources=(FeelNoPainSource(source_id="order41:fnp", threshold=5),),
                        decline_allowed=True,
                    )
    source_id = rules_unit_view_by_id(
        state=state, unit_instance_id=units["source"].unit_instance_id
    ).unit_instance_id
    target_id = rules_unit_view_by_id(
        state=state, unit_instance_id=units["target"].unit_instance_id
    ).unit_instance_id
    session = LocalGameSession(lifecycle=lifecycle)
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    pending = session.to_persistence_payload()
    session = LocalGameSession.from_persistence_payload(pending)
    assert session.to_persistence_payload() == pending
    option = request.options[-1] if decline else request.options[0]
    if decline:
        option = next(o for o in request.options if o.option_id == "decline_stratagem_window")
    else:
        option = next(
            o for o in request.options if o.option_id.startswith("use-stratagem:explosives:")
        )
    if attached:
        option = next(
            o
            for o in request.options
            if units["leader"].own_models[0].model_instance_id in o.option_id
        )
    status = session.submit_option(
        request_id=request.request_id, result_id="order41:use", option_id=option.option_id
    )
    observed_fnp = False
    # Allocation and Feel No Pain remain defender-owned shared decisions.
    while status.decision_request is not None and status.decision_request.decision_type in {
        "select_mortal_wound_model",
        "select_feel_no_pain",
    }:
        nested = status.decision_request
        observed_fnp |= nested.decision_type == "select_feel_no_pain"
        assert nested.actor_id == "player-b"
        persisted = session.to_persistence_payload()
        session = LocalGameSession.from_persistence_payload(persisted)
        assert session.to_persistence_payload() == persisted
        status = session.submit_option(
            request_id=nested.request_id,
            result_id=f"order41:{nested.request_id}",
            option_id=nested.options[0].option_id,
        )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    state = session.lifecycle.state
    assert state is not None
    assert state.command_point_total("player-a") == (2 if decline else 1)
    assert len(state.stratagem_use_records) == (0 if decline else 1)
    events = [
        r.payload
        for r in session.lifecycle.decision_controller.event_log.records
        if r.event_type == "explosives_resolved"
    ]
    if not decline:
        assert len(events) == 1
        event = events[0]
        assert isinstance(event, dict)
        assert isinstance(option.payload, dict)
        selection = option.payload["effect_selection"]
        assert isinstance(selection, dict)
        assert event["source_model_instance_id"] == selection["source_model_instance_id"]
        assert event["target_unit_instance_id"] == target_id
        assert state.stratagem_use_records[0].affected_unit_instance_ids == (
            source_id,
            target_id,
        )
        assert state.stratagem_use_records[0].targeted_unit_instance_ids == (source_id,)
        assert isinstance(event["mortal_wounds"], int)
        assert 0 <= event["mortal_wounds"] <= 6
    else:
        assert not events
    assert observed_fnp == fnp
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    assert request.decision_type == "select_shooting_unit"
    assert any(source_id in o.option_id for o in request.options)
    for viewer in ("player-a", "player-b"):
        from warhammer40k_core.engine.event_log import canonical_json

        assert "object at 0x" not in canonical_json(session.view(viewer_player_id=viewer))
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="order41:replay"))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize(
    "drift",
    [
        "keyword",
        "model_removed",
        "all_source_removed",
        "model_keyword",
        "target_engaged",
        "target_removed",
        "range",
        "engaged",
        "shot",
        "fell_back",
        "cp",
        "phase",
        "action",
    ],
)
def test_explosives_revalidates_before_queue_pop_or_spend(drift: str) -> None:
    from warhammer40k_core.engine.phases.movement import FellBackUnitState
    from warhammer40k_core.engine.phases.shooting import ShootingPhaseState

    lifecycle, units = explosives_scene(extra_friendly=drift == "target_engaged")
    session = LocalGameSession(lifecycle=lifecycle)
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    option = next(o for o in request.options if o.option_id.startswith("use-stratagem:explosives:"))
    state = lifecycle.state
    assert state is not None
    if drift == "keyword":
        _replace_unit_keywords(
            state, unit_instance_id=units["source"].unit_instance_id, keywords=("INFANTRY",)
        )
    elif drift in {"model_removed", "all_source_removed", "target_removed"}:
        assert state.battlefield_state is not None
        removed = tuple(
            m.model_instance_id
            for m in units["target" if drift == "target_removed" else "source"].own_models
        )
        if drift == "model_removed":
            assert isinstance(option.payload, dict)
            selected_model = ExplosivesSelection.from_payload(
                option.payload["effect_selection"]
            ).source_model_instance_id
            removed = (selected_model,)
        state.battlefield_state = state.battlefield_state.with_removed_models(removed)
    elif drift == "model_keyword":
        assert isinstance(option.payload, dict)
        selected_model = ExplosivesSelection.from_payload(
            option.payload["effect_selection"]
        ).source_model_instance_id
        source = units["source"]
        changed = replace(
            source,
            own_models=tuple(
                replace(m, keyword_assignment=replace(m.keyword_assignment, keywords=("INFANTRY",)))
                if m.model_instance_id == selected_model
                else m
                for m in source.own_models
            ),
        )
        state.army_definitions[0] = replace(state.army_definitions[0], units=(changed,))
    elif drift == "target_engaged":
        _replace_unit_poses(
            state, unit_instance_id=units["other"].unit_instance_id, poses=(Pose.at(17.8, 10),)
        )
    elif drift in {"range", "engaged"}:
        x = 30 if drift == "range" else 10.8
        _replace_unit_poses(
            state,
            unit_instance_id=units["target"].unit_instance_id,
            poses=(Pose.at(x, 10), Pose.at(x, 12)),
        )
    elif drift == "shot":
        state.shooting_phase_state = ShootingPhaseState(
            battle_round=state.battle_round,
            active_player_id="player-a",
            shot_unit_ids=(units["source"].unit_instance_id,),
        )
    elif drift == "fell_back":
        state.record_fell_back_unit_state(
            FellBackUnitState(
                player_id="player-a",
                battle_round=state.battle_round,
                unit_instance_id=units["source"].unit_instance_id,
                can_shoot=False,
            )
        )
    elif drift == "action":
        from warhammer40k_core.engine.actions import MissionActionState
        from warhammer40k_core.engine.activity_restrictions import record_action_restriction

        source_id = units["source"].unit_instance_id
        action = MissionActionState.start(
            action_id="order41:action",
            mission_action_id="order41:mission-action",
            player_id="player-a",
            unit_instance_id=source_id,
            target_id="order41:target",
            condition_target_id=None,
            mission_id="order41:mission",
            battle_round=state.battle_round,
            phase="shooting",
            start_timing="during_phase",
            completion_timing="end_turn",
            eligible_unit_instance_ids=(source_id,),
            interruption_conditions=(),
            scoring_source_id="order41:source",
            victory_points=0,
        )
        record_action_restriction(state=state, action=action)
    elif drift == "cp":
        state.spend_command_points(player_id="player-a", amount=2, source_id="order41:spent")
    else:
        assert state.battle_phase_index is not None
        state.battle_phase_index += 1
    before = lifecycle.to_payload()
    status = session.submit_option(
        request_id=request.request_id, result_id="order41:stale", option_id=option.option_id
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert lifecycle.to_payload() == before
    assert not state.stratagem_use_records
    assert lifecycle.decision_controller.queue.pending_requests == (request,)


@pytest.mark.parametrize("can_shoot", [False, True])
def test_explosives_advance_is_absolute_but_fall_back_uses_shoot_permission(
    can_shoot: bool,
) -> None:
    from tests.phase13b_shooting_declaration_helpers import _advanced_unit_state

    from warhammer40k_core.engine.phases.movement import FellBackUnitState

    lifecycle, units = explosives_scene()
    state = lifecycle.state
    assert state is not None
    state.record_fell_back_unit_state(
        FellBackUnitState(
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=units["source"].unit_instance_id,
            can_shoot=can_shoot,
        )
    )
    session = LocalGameSession(lifecycle=lifecycle)
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    assert (
        any(o.option_id.startswith("use-stratagem:explosives:") for o in request.options)
        == can_shoot
    )
    lifecycle, units = explosives_scene()
    state = lifecycle.state
    assert state is not None
    state.record_advanced_unit_state(
        _advanced_unit_state(units["source"].unit_instance_id, can_shoot=can_shoot)
    )
    request = (
        LocalGameSession(lifecycle=lifecycle).advance_until_decision_or_terminal().decision_request
    )
    assert request is not None
    assert not any(o.option_id.startswith("use-stratagem:explosives:") for o in request.options)


def test_explosives_range_and_keywords_belong_to_the_selected_model() -> None:
    lifecycle, units = explosives_scene(target_x=19)
    state = lifecycle.state
    assert state is not None
    _replace_unit_poses(
        state,
        unit_instance_id=units["source"].unit_instance_id,
        poses=(Pose.at(5, 10), Pose.at(12, 10)),
    )
    request = (
        LocalGameSession(lifecycle=lifecycle).advance_until_decision_or_terminal().decision_request
    )
    assert request is not None
    options = [o for o in request.options if o.option_id.startswith("use-stratagem:explosives:")]
    assert len(options) == 1
    assert units["source"].own_models[1].model_instance_id in options[0].option_id
    lifecycle, units = explosives_scene()
    state = lifecycle.state
    assert state is not None
    source = units["source"]
    first, second = source.own_models
    replacement = replace(
        source,
        own_models=(
            replace(
                first, keyword_assignment=replace(first.keyword_assignment, keywords=("INFANTRY",))
            ),
            second,
        ),
    )
    state.army_definitions[0] = replace(state.army_definitions[0], units=(replacement,))
    request = (
        LocalGameSession(lifecycle=lifecycle).advance_until_decision_or_terminal().decision_request
    )
    assert request is not None
    options = [o for o in request.options if o.option_id.startswith("use-stratagem:explosives:")]
    assert len(options) == 1
    assert second.model_instance_id in options[0].option_id


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "extra",
        "kind",
        "model_type",
        "model_blank",
        "model_unknown",
        "target_unknown",
        "target_friendly",
    ],
)
def test_explosives_malformed_or_wrong_selection_is_invalid_without_mutation(change: str) -> None:
    from warhammer40k_core.engine.decision_result import DecisionResult
    from warhammer40k_core.engine.stratagems import invalid_stratagem_use_status

    lifecycle, units = explosives_scene()
    session = LocalGameSession(lifecycle=lifecycle)
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    option = next(o for o in request.options if o.option_id.startswith("use-stratagem:explosives:"))
    result = DecisionResult.for_request(
        result_id="order41:malformed", request=request, selected_option_id=option.option_id
    )
    assert isinstance(result.payload, dict)
    original = result.payload["effect_selection"]
    assert isinstance(original, dict)
    selection = dict(original)
    if change == "missing":
        del selection["source_model_instance_id"]
    elif change == "extra":
        selection["extra"] = True
    elif change == "kind":
        selection["effect_selection_kind"] = "wrong"
    elif change == "model_type":
        selection["source_model_instance_id"] = 3
    elif change == "model_blank":
        selection["source_model_instance_id"] = " "
    elif change == "model_unknown":
        selection["source_model_instance_id"] = "unknown"
    else:
        selection["enemy_target_unit_instance_id"] = (
            units["source"].unit_instance_id if change == "target_friendly" else "unknown"
        )
    bad = replace(result, payload={**result.payload, "effect_selection": selection})
    state = lifecycle.state
    assert state is not None
    before = lifecycle.to_payload()
    status = invalid_stratagem_use_status(
        state=state, request=request, result=bad, decisions=lifecycle.decision_controller
    )
    assert status is not None
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert lifecycle.to_payload() == before
    assert lifecycle.decision_controller.queue.pending_requests == (request,)


@pytest.mark.parametrize(("depth", "count"), [(2.5, 1), (8.0, 0)])
def test_explosives_uses_selected_model_visibility(depth: float, count: int) -> None:
    from tests.phase13b_shooting_declaration_helpers import _display_geometry

    from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
    from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainWallDefinition

    lifecycle, units = explosives_scene()
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    display = _display_geometry(
        center_x_inches=11.5, center_y_inches=10.0, width_inches=0.1, depth_inches=depth
    )
    wall = TerrainFeatureDefinition(
        feature_id="order41:wall",
        feature_kind=TerrainFeatureKind.HILLS,
        footprint_center_x_inches=11.5,
        footprint_center_y_inches=10.0,
        footprint_width_inches=0.1,
        footprint_depth_inches=depth,
        rules_footprint_polygon=display.footprint_polygon,
        display_geometry=display,
        walls=(TerrainWallDefinition("wall", 11.5, 10.0, 0.0, 0.1, depth, 5.0),),
        source_id="order41:wall-source",
    )
    state.battlefield_state = replace(state.battlefield_state, terrain_features=(wall,))
    request = (
        LocalGameSession(lifecycle=lifecycle).advance_until_decision_or_terminal().decision_request
    )
    assert request is not None
    options = [o for o in request.options if o.option_id.startswith("use-stratagem:explosives:")]
    assert len(options) == count
    if count:
        assert units["source"].own_models[1].model_instance_id in options[0].option_id


def test_explosives_reopens_after_another_unit_shoots_through_the_facade() -> None:
    from typing import cast

    from tests.phase13b_shooting_declaration_helpers import (
        _proposal_from_declarations,
        _weapon_payload_to_declaration_payload,
    )

    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.weapon_declaration import WeaponDeclaration

    lifecycle, units = explosives_scene(extra_friendly=True)
    session = LocalGameSession(lifecycle=lifecycle)
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    status = session.submit_option(
        request_id=request.request_id,
        result_id="order41:later-decline",
        option_id="decline_stratagem_window",
    )
    request = status.decision_request
    assert request is not None
    assert request.decision_type == "select_shooting_unit"
    status = session.submit_option(
        request_id=request.request_id,
        result_id="order41:other-unit",
        option_id=units["other"].unit_instance_id,
    )
    request = status.decision_request
    assert request is not None
    assert request.decision_type == "select_shooting_type"
    status = session.submit_option(
        request_id=request.request_id, result_id="order41:normal", option_id="normal"
    )
    request = status.decision_request
    assert request is not None
    assert request.decision_type == "submit_shooting_declaration"
    payload = cast(dict[str, object], request.payload)
    proposal_request = cast(dict[str, object], payload["proposal_request"])
    weapons = cast(list[dict[str, object]], proposal_request["available_weapons"])
    proposal = _proposal_from_declarations(
        request=request,
        declarations=(
            WeaponDeclaration.from_payload(
                _weapon_payload_to_declaration_payload(
                    weapon=weapons[0], target_unit_id=units["target"].unit_instance_id
                )
            ),
        ),
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order41:shoot",
        payload=validate_json_value(proposal.to_payload()),
    )
    for _ in range(40):
        request = status.decision_request
        assert request is not None
        if any(o.option_id.startswith("use-stratagem:explosives:") for o in request.options):
            break
        option = next(
            (o for o in request.options if o.option_id == "decline_stratagem_window"),
            request.options[0],
        )
        status = session.submit_option(
            request_id=request.request_id,
            result_id=f"order41:other:{request.request_id}",
            option_id=option.option_id,
        )
    else:
        pytest.fail("Other unit shooting did not reach the next Explosives opportunity.")
    state = lifecycle.state
    assert state is not None
    assert state.shooting_phase_state is not None
    assert units["other"].unit_instance_id in state.shooting_phase_state.shot_unit_ids
    assert units["source"].unit_instance_id not in state.shooting_phase_state.shot_unit_ids
    option = next(o for o in request.options if o.option_id.startswith("use-stratagem:explosives:"))
    status = session.submit_option(
        request_id=request.request_id, result_id="order41:later-use", option_id=option.option_id
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert len(state.stratagem_use_records) == 1
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="order41:later")).run().status
        is ReplayRunStatus.REPRODUCED
    )
