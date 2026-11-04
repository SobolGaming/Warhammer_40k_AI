from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace

import pytest

from tests.phase17n_step6g_secondary_certification_helpers import seed_completed_fight_phase
from tests.secondary_destruction_helpers import record_secondary_destruction_for_fixture
from tests.support.faction_batch01 import INFRACTORS, LORD, anchor, locate, scene, selection
from tests.support.section02_fixtures import Section02Definitions
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.mission_state_validation import (
    runtime_ruleset_descriptor_for_mission_setup,
)
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.scoring import VictoryPointTransaction
from warhammer40k_core.engine.stratagems import stratagem_decline_payload
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)


def assert_native_secondary_round_cap(
    d: Section02Definitions, *, scoring: str, first_count: int
) -> None:
    """Native authored deaths; facade phases and replay start after the last premise."""
    survivor = (selection(d, INFRACTORS, "survivor"),)
    characters = tuple(selection(d, LORD, f"lord-{i}") for i in range(first_count + 1)) + survivor
    other = "opponent" if scoring == "owner" else "owner"
    prefix = "foe" if scoring == "owner" else "own"
    s = scene(
        d,
        survivor if scoring == "owner" else characters,
        characters if scoring == "owner" else survivor,
        active=scoring,
        phase=BattlePhase.FIGHT,
        seed=f"event-cap-native:{scoring}:{first_count}",
    )
    s.state.turn_order = (scoring, other)
    mission = MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="owner",
        defender_player_id="opponent",
        attacker_force_disposition_id="take-and-hold",
        defender_force_disposition_id="purge-the-foe",
    )
    descriptor = runtime_ruleset_descriptor_for_mission_setup(mission, rules_overlay_ids=())
    s.state.mission_setup = mission
    s.state.ruleset_descriptor_hash = descriptor.descriptor_hash
    assert s.state.battlefield_state is not None
    s.state.battlefield_state = replace(
        s.state.battlefield_state,
        battlefield_width_inches=mission.battlefield_width_inches,
        battlefield_depth_inches=mission.battlefield_depth_inches,
        terrain_features=mission.terrain_features,
    )
    s.state.battle_round = 2
    for i in range(first_count + 1):
        locate(s, f"{prefix}:lord-{i}", (Pose.at(34, 5 + i * 7),))
    for uid, x, y in [("own:survivor", 5, 5), ("foe:survivor", 34, 45)]:
        locate(
            s,
            uid,
            tuple(
                Pose.at(x + (i % 2) * 1.5, y + (i // 2) * 1.5)
                for i in range(len(s.units[uid].own_models))
            ),
        )
    assert s.session.lifecycle._config is not None  # pyright: ignore[reportPrivateUsage]
    config = replace(
        s.session.lifecycle._config,  # pyright: ignore[reportPrivateUsage]
        mission_setup=mission,
        ruleset_descriptor=descriptor,
        turn_order=(scoring, other),
    )
    s.session = LocalGameSession(
        GameLifecycle.from_payload(
            {
                "config": config.to_payload(),
                "parameterized_movement_proposals": True,
                "state": s.state.to_payload(),
                "decisions": s.session.lifecycle.decision_controller.to_payload(),
                "reaction_queue": {"frames": []},
            }
        )
    )
    restored_state = s.session.lifecycle.state
    assert restored_state is not None
    s.state = restored_state
    anchor(s)
    for i in range(first_count):
        record_secondary_destruction_for_fixture(
            s.state,
            destroyed_unit_instance_id=f"{prefix}:lord-{i}",
            destroying_player_id=scoring,
            source_id=f"repro:{i}",
            event_log=s.session.lifecycle.decision_controller.event_log,
        )
    seed_completed_fight_phase(s.state)

    def txs() -> list[VictoryPointTransaction]:
        return [
            t
            for ledger in s.state.victory_point_ledgers
            if ledger.player_id == scoring
            for t in ledger.transactions
            if t.source_id == "assassination"
        ]

    last_destroyed = False
    initial = None
    for step in range(90):
        state = s.state
        pending = s.session.lifecycle.pending_decision_request()
        if state.battle_round == 3:
            break
        if state.active_player_id == other and not last_destroyed:
            record_secondary_destruction_for_fixture(
                state,
                destroyed_unit_instance_id=f"{prefix}:lord-{first_count}",
                destroying_player_id=scoring,
                source_id="repro:last",
                event_log=s.session.lifecycle.decision_controller.event_log,
            )
            last_destroyed = True
            initial = deepcopy(s.session.lifecycle.to_payload())
            assert GameLifecycle.from_payload(initial).to_payload() == initial
        if pending and pending.decision_type == "submit_stratagem_target_proposal":
            result = s.session.submit_parameterized_payload(
                request_id=pending.request_id,
                payload=stratagem_decline_payload(),
                result_id=f"cap-native:{step}",
            )
            assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
            continue
        if pending:
            choices = [o.option_id for o in pending.options]
            if pending.decision_type == "select_movement_unit":
                preferred = next(
                    (v for v in choices if "end" in v or "done" in v or v.startswith("complete_")),
                    next((v for v in choices if "survivor" in v), None),
                )
            elif pending.decision_type == "select_movement_action":
                preferred = "remain_stationary" if "remain_stationary" in choices else None
            elif (
                pending.decision_type == "select_shooting_unit"
                or pending.decision_type == "select_charge_unit"
            ):
                preferred = next(
                    (v for v in choices if "end" in v or "done" in v or v.startswith("complete_")),
                    next((v for v in choices if "survivor" in v), None),
                )
            elif "sequenc" in pending.decision_type:
                preferred = choices[0]
            elif pending.decision_type == "mission_action_opportunity":
                preferred = next((v for v in choices if "decline" in v), None)
            else:
                preferred = next(
                    (v for v in choices if v.startswith(("complete_", "end_", "decline", "skip"))),
                    None,
                )
            assert preferred is not None, (pending.decision_type, choices)
            result = s.session.submit_option(
                request_id=pending.request_id, option_id=preferred, result_id=f"cap-native:{step}"
            )
            assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
        else:
            result = s.session.advance_until_decision_or_terminal()
            assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
    else:
        raise AssertionError("drive exhausted")

    assert initial is not None
    transactions = txs()
    assert sum(t.amount for t in transactions) == 15
    assert transactions[0].amount == min(first_count * 4, 15)
    assert all(t.battle_round == 2 for t in transactions)
    if first_count == 3:
        assert [t.amount for t in transactions] == [12, 3]
        metadata = transactions[-1].metadata
        assert isinstance(metadata, dict)
        audit = metadata["vp_cap_audit"]
        assert isinstance(audit, dict)
        assert audit["secondary_battle_round_points_before"] == 12
        assert audit["secondary_battle_round_points_after"] == 15
        assert audit["secondary_battle_round_remaining_capacity"] == 0
    assert (
        GameLifecycle.from_payload(deepcopy(s.session.lifecycle.to_payload())).to_payload()
        == s.session.lifecycle.to_payload()
    )
    artifact = ReplayArtifact.capture(
        artifact_id=f"event-cap:{scoring}:{first_count}",
        initial_lifecycle_payload=initial,
        final_lifecycle=s.session.lifecycle,
    )
    replay = ReplayRunner.from_payload(json.loads(json.dumps(artifact.to_payload()))).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay
    assert replay.reproduced_exactly


def assert_native_two_card_tactical_capacity(d: Section02Definitions) -> None:
    """Two source-valid hands at explicit turn checkpoints; no draw replay claim."""
    from warhammer40k_core.core.missions import ObjectiveMarkerRole
    from warhammer40k_core.engine.game_state import SecondaryMissionChoice, SecondaryMissionMode
    from warhammer40k_core.engine.mission_decisions import request_tactical_secondary_score
    from warhammer40k_core.engine.objective_control import ObjectiveControlTiming
    from warhammer40k_core.engine.scoring import (
        SecondaryMissionCardMode,
        SecondaryMissionCardState,
        SecondaryMissionCardStatus,
    )
    from warhammer40k_core.engine.secondary_mission_selection import SecondaryMissionSelection
    from warhammer40k_core.engine.secondary_scoring_boundary import (
        score_turn_end_mission_scoring_boundary,
    )

    s = scene(
        d,
        tuple(selection(d, LORD, f"lord-{i}") for i in range(5)),
        (selection(d, INFRACTORS, "survivor"),),
        phase=BattlePhase.FIGHT,
        active="opponent",
        seed="event-cap-two-tactical-cards",
    )
    mission = MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="owner",
        defender_player_id="opponent",
        attacker_force_disposition_id="take-and-hold",
        defender_force_disposition_id="purge-the-foe",
    )
    descriptor = runtime_ruleset_descriptor_for_mission_setup(mission, rules_overlay_ids=())
    s.state.mission_setup = mission
    s.state.ruleset_descriptor_hash = descriptor.descriptor_hash
    s.state.battle_round = 3
    s.state.turn_order = ("opponent", "owner")
    assert s.state.battlefield_state is not None
    s.state.battlefield_state = replace(
        s.state.battlefield_state,
        battlefield_width_inches=mission.battlefield_width_inches,
        battlefield_depth_inches=mission.battlefield_depth_inches,
        terrain_features=mission.terrain_features,
    )
    s.state.secondary_mission_card_states = [
        c for c in s.state.secondary_mission_card_states if c.player_id != "owner"
    ]
    s.state.secondary_mission_choices = [
        c for c in s.state.secondary_mission_choices if c.player_id != "owner"
    ]
    s.state.record_secondary_mission_choice(
        SecondaryMissionChoice("owner", SecondaryMissionMode.TACTICAL)
    )
    assert s.session.lifecycle._config is not None  # pyright: ignore[reportPrivateUsage]
    config = replace(
        s.session.lifecycle._config,  # pyright: ignore[reportPrivateUsage]
        mission_setup=mission,
        ruleset_descriptor=descriptor,
        turn_order=("opponent", "owner"),
    )

    def add_card(card_id: str, *, round_drawn: int) -> None:
        card = SecondaryMissionCardState.active_tactical(
            player_id="owner",
            secondary_mission_id=card_id,
            battle_round=round_drawn,
            source_result_id=f"two-card-premise:{card_id}",
        )
        selected = SecondaryMissionSelection().with_when_drawn_resolved()
        if card_id == "beacon":
            selected = selected.with_beacon_unit("own:lord-0")
        s.state.record_secondary_mission_card_state(card.with_selection(selected))
        assert (
            sum(
                c.player_id == "owner" and c.status is SecondaryMissionCardStatus.ACTIVE
                for c in s.state.secondary_mission_card_states
            )
            <= 2
        )

    home = next(
        o
        for o in mission.objective_markers
        if o.objective_role is ObjectiveMarkerRole.ATTACKER_HOME
    )
    enemy_home = next(
        o
        for o in mission.objective_markers
        if o.objective_role is ObjectiveMarkerRole.DEFENDER_HOME
    )
    locate(s, "own:lord-0", (Pose.at(enemy_home.x_inches, enemy_home.y_inches),))
    locate(s, "own:lord-1", (Pose.at(home.x_inches, home.y_inches),))
    markers = [
        o
        for o in mission.objective_markers
        if o.objective_role in {ObjectiveMarkerRole.CENTRAL, ObjectiveMarkerRole.EXPANSION}
    ][:2]
    assert len(markers) == 2
    locate(
        s,
        "own:lord-2",
        (Pose.at(mission.battlefield_width_inches / 2, mission.battlefield_depth_inches / 2),),
    )
    for i, marker in enumerate(markers, start=3):
        locate(s, f"own:lord-{i}", (Pose.at(marker.x_inches, marker.y_inches),))
    locate(
        s,
        "foe:survivor",
        tuple(
            Pose.at(
                enemy_home.x_inches + 3 + (i % 2) * 1.5, enemy_home.y_inches + 3 + (i // 2) * 1.5
            )
            for i in range(len(s.units["foe:survivor"].own_models))
        ),
    )
    add_card("beacon", round_drawn=2)
    add_card("defend-stronghold", round_drawn=2)
    anchor(s)
    decisions = s.session.lifecycle.decision_controller
    for card_id in ("beacon", "defend-stronghold"):
        s.state.score_secondary_mission_from_state(
            player_id="owner",
            secondary_mission_id=card_id,
            mode=SecondaryMissionCardMode.TACTICAL,
            phase=BattlePhase.FIGHT,
            event_log=decisions.event_log,
        )

    def secondary_total() -> int:
        return sum(
            t.amount
            for t in s.state.victory_point_ledger_for_player("owner").transactions
            if t.source_kind.value == "tactical_secondary"
        )

    assert secondary_total() == 10, [
        t.to_payload() for t in s.state.victory_point_ledger_for_player("owner").transactions
    ]
    # Explicit later-turn checkpoint: two earlier scored cards plus two newly held
    # cards. Initial positions and the later turn are premises; the score, preview
    # and retain owners are live.
    s.state.active_player_id = "owner"
    add_card("centre-ground", round_drawn=3)
    add_card("secure-no-mans-land", round_drawn=3)
    s.state.score_secondary_mission_from_state(
        player_id="owner",
        secondary_mission_id="centre-ground",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=decisions.event_log,
    )
    assert secondary_total() == 15
    record = next(
        v
        for v in s.state.objective_control_records
        if v.active_player_id == "owner"
        and v.battle_round == 3
        and v.timing is ObjectiveControlTiming.TURN_END
    )
    score_turn_end_mission_scoring_boundary(
        state=s.state, record=record, end_of_battle=False, event_log=decisions.event_log
    )
    achievement = next(
        c
        for c in s.state.tactical_secondary_achievement_contexts
        if c.player_id == "owner" and c.secondary_mission_id == "secure-no-mans-land"
    )
    status = request_tactical_secondary_score(
        state=s.state, decisions=decisions, achievement_context=achievement
    )
    pending = status.decision_request
    assert pending is not None
    assert [o.option_id for o in pending.options] == ["retain:secure-no-mans-land"]
    lifecycle = GameLifecycle.from_payload(
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": s.state.to_payload(),
            "decisions": decisions.to_payload(),
            "reaction_queue": {"frames": []},
        }
    )
    saved = deepcopy(lifecycle.to_payload())
    assert GameLifecycle.from_payload(saved).to_payload() == saved
    session = LocalGameSession(lifecycle=lifecycle)
    with pytest.raises(DecisionError, match="finite action space"):
        session.submit_option(
            request_id=pending.request_id,
            option_id="score:secure-no-mans-land",
            result_id="two-card-cap:illegal-score",
        )
    assert session.lifecycle.to_payload() == saved
    session.submit_option(
        request_id=pending.request_id,
        option_id="retain:secure-no-mans-land",
        result_id="two-card-cap:retain",
    )
    state = session.lifecycle.state
    assert state is not None
    retained = state.secondary_mission_card_state(
        player_id="owner",
        secondary_mission_id="secure-no-mans-land",
        mode=SecondaryMissionCardMode.TACTICAL,
    )
    assert retained is not None
    assert retained.status is SecondaryMissionCardStatus.ACTIVE
    assert (
        sum(
            t.amount
            for t in state.victory_point_ledger_for_player("owner").transactions
            if t.source_kind.value == "tactical_secondary"
        )
        == 15
    )
