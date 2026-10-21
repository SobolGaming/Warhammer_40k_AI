"""Loaded native Command-end rules at an explicit post-setup component boundary.

The shared scene keeps source mission objectives/scoring and admits native EC
providers. Its small rosters and open terrain remain component qualifications.
No mission occurrence or ordering answer is injected into the sequencer.
"""

from tests.support.faction_batch01 import TORMENTORS, Scene, anchor, locate, scene, selection
from tests.support.section02_fixtures import Section02Definitions

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.geometry.pose import Pose

STICKY_SOURCE_ID = (
    "data-package:core-v2:wahapedia-10e-bridge:phase17k-generated:Datasheets_abilities:000004079:3"
)


def native_command_scene(definitions: Section02Definitions, *, active: str, reverse: bool) -> Scene:
    own: tuple[str, ...] = ("a", "b")
    enemy: tuple[str, ...] = ("c", "d")
    if reverse:
        own, enemy = tuple(reversed(own)), tuple(reversed(enemy))
    s = scene(
        definitions,
        tuple(selection(definitions, TORMENTORS, name) for name in own),
        tuple(selection(definitions, TORMENTORS, name) for name in enemy),
        phase=BattlePhase.COMMAND,
        active=active,
        seed="section08-native-command",
    )
    s.state.battle_round = 2
    for player, ids in (("owner", ("own:a", "own:b")), ("opponent", ("foe:c", "foe:d"))):
        for index, uid in enumerate(ids):
            x = (27.0, 32.5)[index] if player == active else (45.0, 49.0)[index]
            unit = s.units[uid]
            locate(
                s,
                uid,
                tuple(
                    Pose.at(x + (i % 2) * 1.3, 21.0 + (i // 2) * 1.3)
                    for i in range(len(unit.own_models))
                ),
            )
    # Muster input order is reversed above; state retains canonical army order.
    anchor(s)
    return s


def assert_native_command_outcome(session: LocalGameSession, *, active: str) -> None:
    state = session.lifecycle.state
    assert state is not None
    assert state.current_battle_phase is BattlePhase.MOVEMENT
    sticky = state.sticky_objective_control_states
    assert len(sticky) == 2
    assert {item.source_rule_id for item in sticky} == {STICKY_SOURCE_ID}
    assert {item.player_id for item in sticky} == {active}
    assert {item.originating_unit_instance_id for item in sticky} == (
        {"own:a", "own:b"} if active == "owner" else {"foe:c", "foe:d"}
    )
    assert len({item.objective_id for item in sticky}) == 1
    expected = 5 if active == "owner" else 4
    other = "opponent" if active == "owner" else "owner"
    ledger = state.victory_point_ledger_for_player(active)
    assert ledger.victory_points == expected
    assert state.victory_point_ledger_for_player(other).victory_points == 0
    assert len(ledger.transactions) == 1
    transaction = ledger.transactions[0]
    assert transaction.amount == expected
    assert transaction.phase == BattlePhase.COMMAND.value
    assert isinstance(transaction.metadata, dict)
    assert transaction.metadata["controlled_objective_ids"] == [sticky[0].objective_id]
    assert transaction.metadata["scoring_rule_source_id"] == (
        "gw-11e-chapter-approved-2026-27:primary:primary-immovable-object:"
        "scoring-rule:immovable-object-rounds-two-to-four-command"
        if active == "owner"
        else "gw-11e-chapter-approved-2026-27:primary:primary-unstoppable-force:"
        "scoring-rule:unstoppable-force-objectives"
    )
    events = session.lifecycle.decision_controller.event_log.records
    sticky_indices = [
        i
        for i, event in enumerate(events)
        if event.event_type == "sticky_objective_control_state_recorded"
    ]
    commits = [
        i
        for i, event in enumerate(events)
        if event.event_type == "primary_scoring_commit_checkpoint_recorded"
    ]
    assert len(sticky_indices) == 2
    assert len(commits) == 1
    assert max(sticky_indices) < commits[0]
    # Source mission scoring is a later phase-advance operation, not a discovered
    # mission candidate in the native non-mission batch.
    transitions = [event for event in events if event.event_type == "timing_batch_transition"]
    assert transitions
    for event in transitions:
        assert isinstance(event.payload, dict)
        batch = event.payload["batch"]
        assert isinstance(batch, dict)
        participants = batch["participants"]
        assert isinstance(participants, list)
        for participant in participants:
            assert isinstance(participant, dict)
            assert participant["origin"] == "player"
            assert participant["source_rule_id"] == STICKY_SOURCE_ID
