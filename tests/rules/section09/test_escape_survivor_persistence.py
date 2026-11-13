"""Natural hazard casualties preserve accepted paths through full session persistence.

The initial canonical mustered checkpoint is constructed before Command; all
hazards, wounds, removals, movement and later decisions are engine-generated.
"""

import json
from copy import deepcopy
from dataclasses import replace
from functools import cache
from typing import cast

import pytest

from tests.phase15a_charge_config_helpers import _config, _mustered_armies
from tests.phase15a_charge_test_support import (
    _compact_test_unit_poses,
    _unit_placement_at,
)
from tests.setup_completion_helpers import (
    ensure_army_mustered_events_for_fixture,
    record_current_battlefield_placements_for_fixture,
    record_primary_turn_start_evidence_for_fixture,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.game_state import (
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.movement_decision_authority import (
    validate_movement_completion_decision_authority,
)
from warhammer40k_core.engine.movement_proposals import MovementProposalPayload, ProposalKind
from warhammer40k_core.engine.phase import (
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.replay import ReplayArtifactPayload, ReplayRunner
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


@cache
def _completed_escape(kind: str) -> dict[str, JsonValue]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    if kind == "complete":
        # Explicit singleton composition contract; the canonical one-wound
        # Boyz-like profile and actual equipment are unchanged.
        catalog = replace(
            catalog,
            datasheets=tuple(
                replace(
                    sheet,
                    composition=tuple(
                        replace(row, min_models=1, max_models=1) for row in sheet.composition
                    ),
                )
                if sheet.datasheet_id == "core-boyz-like-infantry"
                else sheet
                for sheet in catalog.datasheets
            ),
        )
    config = _config(
        game_id={
            "partial": "escape-survivor-partial-fixture-0",
            "complete": "escape-survivor-complete-fixture-2",
            "retry": "escape-survivor-retry-fixture-0",
            "retry_prefix": "escape-survivor-retry-fixture-0",
        }[kind],
        alpha_unit_ids=("retreat", "spare"),
        enemy_unit_ids=("enemy",),
        catalog=catalog,
        alpha_datasheet_ids_by_selection_id=(
            {"retreat": "core-boyz-like-infantry"} if kind == "complete" else None
        ),
    )
    armies = _mustered_armies(config)
    mission = config.mission_setup
    assert mission is not None
    battlefield = create_deterministic_battlefield_scenario(
        battlefield_id="escape-survivor-battlefield",
        armies=armies,
        battlefield_width_inches=mission.battlefield_width_inches,
        battlefield_depth_inches=mission.battlefield_depth_inches,
    ).battlefield_state
    units = {u.unit_instance_id.split(":", maxsplit=1)[1]: u for a in armies for u in a.units}
    for name, unit in units.items():
        player = "player-b" if name == "enemy" else "player-a"
        army_id = "army-beta" if name == "enemy" else "army-alpha"
        origin = Pose.at(10, 22.5 if name == "enemy" else 35 if name == "spare" else 20)
        poses = (
            tuple(Pose.at(10 + 2 * i, 20) for i in range(len(unit.own_models)))
            if kind in ("retry", "retry_prefix") and name == "retreat"
            else _compact_test_unit_poses(origin=origin, model_count=len(unit.own_models))
        )
        battlefield = battlefield.with_unit_placement(
            _unit_placement_at(unit, army_id=army_id, player_id=player, poses=poses)
        )
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    state.record_battlefield_state(battlefield)
    for player in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=player,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=("assassination", "bring_it_down"),
            )
        )
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = 0
    state.battle_round = 1
    state.active_player_id = "player-a"
    decisions = GameLifecycle().decision_controller
    ensure_army_mustered_events_for_fixture(state, decisions=decisions)
    record_current_battlefield_placements_for_fixture(state, decisions=decisions)
    record_primary_turn_start_evidence_for_fixture(state, decisions=decisions)
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
    session = LocalGameSession(lifecycle)
    session.advance_until_decision_or_terminal()
    retreat = units["retreat"].unit_instance_id
    retried = False
    pre_hazard_rejected = False
    original_hazards: list[EventRecord] | None = None
    for _ in range(35):
        request = session.lifecycle.pending_decision_request()
        assert request is not None
        count = session.decision_record_count()
        active_state = session.lifecycle.state
        assert active_state is not None
        events = session.lifecycle.decision_controller.event_log.records
        if any(e.event_type == "movement_activation_completed" for e in events):
            assert request.decision_type == "select_movement_unit"
            break
        if request.decision_type == "submit_movement_proposal":
            assert active_state.battlefield_state is not None
            placements = active_state.battlefield_state.unit_placement_by_id(
                retreat
            ).model_placements
            proposal = request.payload
            assert isinstance(proposal, dict)
            nested = proposal["proposal_request"]
            assert isinstance(nested, dict)
            context = nested["context"]
            assert isinstance(context, dict)
            retry = "desperate_escape_completed_packet_id" in context
            reject_prefix = kind == "retry_prefix" and not pre_hazard_rejected
            distance = 50 if reject_prefix else 5
            paths: list[tuple[str, tuple[Pose, ...]]] = []
            for index, model in enumerate(placements):
                x = 12 + 2 * index if retry else model.pose.position.x
                start = model.pose
                end = Pose.at(x, model.pose.position.y - distance)
                midpoint = Pose.at((start.position.x + x) / 2, start.position.y - distance / 2)
                paths.append((model.model_instance_id, (start, midpoint, end)))
            witness = PathWitness.for_paths(tuple(paths))
            retried = retried or retry
            payload = MovementProposalPayload(
                proposal_request_id=request.request_id,
                proposal_kind=ProposalKind.FALL_BACK,
                unit_instance_id=retreat,
                movement_phase_action="fall_back",
                movement_mode="fall_back",
                fall_back_mode="desperate_escape",
                witness=witness,
            ).to_payload()
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"escape:{count}",
                payload=cast(JsonValue, payload),
            )
        else:
            if request.decision_type == "select_movement_unit":
                option = retreat
            elif request.decision_type == "select_movement_action":
                option = "fall_back:desperate_escape"
            else:
                declines = [
                    o.option_id
                    for o in request.options
                    if o.option_id in ("decline", "keep", "decline_stratagem_window")
                    or o.option_id.endswith(":decline")
                ]
                if declines:
                    assert len(declines) == 1
                    option = declines[0]
                else:
                    assert (
                        request.decision_type == "select_mortal_wound_model"
                        or len(request.options) == 1
                    )
                    if (
                        kind in ("retry", "retry_prefix")
                        and request.decision_type == "select_mortal_wound_model"
                    ):
                        middle = units["retreat"].own_models[2].model_instance_id
                        option = (
                            middle
                            if any(o.option_id == middle for o in request.options)
                            else min(o.option_id for o in request.options)
                        )
                    else:
                        option = min(o.option_id for o in request.options)
            status = session.submit_option(
                request_id=request.request_id, result_id=f"escape:{count}", option_id=option
            )
        if status.status_kind is LifecycleStatusKind.INVALID:
            assert kind in ("retry", "retry_prefix")
            assert not retried
            assert isinstance(status.payload, dict)
            if kind == "retry_prefix" and not pre_hazard_rejected:
                assert status.payload["violation_code"] == "movement_distance_exceeded"
                pre_hazard_rejected = True
                session.advance_until_decision_or_terminal()
                continue
            assert status.payload["violation_code"] == "unit_coherency_broken"
            original_hazards = [
                e
                for e in session.lifecycle.decision_controller.event_log.records
                if e.event_type
                in ("desperate_escape_roll_resolved", "desperate_escape_hazard_mortals_resolved")
            ]
            session.advance_until_decision_or_terminal()
    else:
        raise AssertionError("Natural Fall Back did not complete")
    if kind == "retry_prefix":
        assert pre_hazard_rejected
    if kind in ("retry", "retry_prefix"):
        assert retried
        assert original_hazards is not None
        assert [
            e
            for e in session.lifecycle.decision_controller.event_log.records
            if e.event_type
            in ("desperate_escape_roll_resolved", "desperate_escape_hazard_mortals_resolved")
        ] == original_hazards
    return cast(dict[str, JsonValue], json.loads(json.dumps(session.to_persistence_payload())))


def _authority_inputs(
    saved: dict[str, JsonValue],
) -> tuple[tuple[EventRecord, ...], tuple[DecisionRecord, ...], int, dict[str, JsonValue]]:
    raw = cast(GameLifecyclePayload, saved["lifecycle"])
    events = tuple(EventRecord.from_payload(row) for row in raw["decisions"]["event_log"])
    decisions = tuple(DecisionRecord.from_payload(row) for row in raw["decisions"]["records"])
    index = next(i for i, e in enumerate(events) if e.event_type == "movement_activation_completed")
    payload = events[index].payload
    assert isinstance(payload, dict)
    return events, decisions, index, payload


@pytest.mark.parametrize("kind", ["partial", "complete"])
def test_natural_escape_survivor_checkpoint_roundtrips(kind: str) -> None:
    saved = deepcopy(_completed_escape(kind))
    events, decisions, index, payload = _authority_inputs(saved)
    destroyed = payload["destroyed_model_ids"]
    assert isinstance(destroyed, list)
    assert destroyed, payload
    authority = validate_movement_completion_decision_authority(
        event_records=events, decision_records=decisions, mutation_index=index, payload=payload
    )
    assert authority is not None
    original = authority.proposal.witness.model_paths
    if kind == "complete":
        assert len(destroyed) == len(original)
        assert authority.witness is None
    else:
        assert 0 < len(destroyed) < len(original)
        assert authority.witness is not None
        assert authority.witness.model_paths == tuple(p for p in original if p[0] not in destroyed)
    restored = LocalGameSession.from_persistence_payload(saved)
    assert restored.to_persistence_payload() == saved
    replay = (
        ReplayRunner.from_payload(cast(ReplayArtifactPayload, saved["replay_artifact"]))
        .run()
        .to_payload()
    )
    assert replay["status"] == "reproduced", replay


def test_survivor_authority_rejects_missing_survivor() -> None:
    events, decisions, index, payload = _authority_inputs(_completed_escape("partial"))
    damaged = deepcopy(payload)
    witness = cast(dict[str, JsonValue], damaged["witness"])
    paths = cast(list[JsonValue], witness["model_paths"])
    paths.pop()
    with pytest.raises(GameLifecycleError, match="proposal semantics drifted"):
        validate_movement_completion_decision_authority(
            event_records=events, decision_records=decisions, mutation_index=index, payload=damaged
        )


def test_survivor_authority_rejects_unrelated_hazard() -> None:
    events, decisions, index, payload = _authority_inputs(_completed_escape("partial"))
    damaged = {**payload, "desperate_escape_mortal_application_id": "unrelated-hazard"}
    with pytest.raises(GameLifecycleError, match="hazard authority is missing"):
        validate_movement_completion_decision_authority(
            event_records=events, decision_records=decisions, mutation_index=index, payload=damaged
        )


def test_completed_hazard_survivor_retry_roundtrips_without_rerolls() -> None:
    _assert_survivor_retry_roundtrip("retry")


def test_pre_hazard_rejected_proposal_then_survivor_retry_roundtrips() -> None:
    _assert_survivor_retry_roundtrip("retry_prefix")


def _assert_survivor_retry_roundtrip(kind: str) -> None:
    saved = deepcopy(_completed_escape(kind))
    events, decisions, index, payload = _authority_inputs(saved)
    authority = validate_movement_completion_decision_authority(
        event_records=events, decision_records=decisions, mutation_index=index, payload=payload
    )
    assert authority is not None
    assert authority.witness == authority.proposal.witness
    assert LocalGameSession.from_persistence_payload(saved).to_persistence_payload() == saved
    result = (
        ReplayRunner.from_payload(cast(ReplayArtifactPayload, saved["replay_artifact"]))
        .run()
        .to_payload()
    )
    assert result["status"] == "reproduced", result
