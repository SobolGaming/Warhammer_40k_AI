"""Native lethal melee with a labelled minimal turn-identity checkpoint."""

from dataclasses import replace

from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section05_fixtures import replace_unit
from tests.support.section05_retention import SOURCE, retain
from tests.support.section05_sequence import fixed_sequence_dice, native_sequence
from tests.support.section09_fixtures import attach_mission
from tests.support.section12_fixtures import LORD, add_native

from warhammer40k_core.engine.attack_sequence import resolve_attack_sequence_until_blocked
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose


def public_retained_scene(
    d: Section02Definitions,
) -> tuple[GameState, UnitInstance, UnitInstance, DecisionController]:
    s, target, sequence = native_sequence(d, distance=2.5, melee=True)
    living = d.unit(LORD, army_id="enemy", identity="living-target")
    add_native(s, living, (Pose.at(10, 13.5),), enemy=True)
    target = replace(target, own_models=(replace(target.own_models[0], wounds_remaining=1),))
    replace_unit(s, target)
    attach_mission(s)
    decisions = DecisionController()
    # Identity only: no Command, mustering, mission or preceding Charge is run.
    record_primary_turn_start_evidence_for_fixture(s, decisions=decisions)
    s.record_model_destruction_reaction_sources(
        model_instance_id=target.own_model_ids()[0], sources=(SOURCE,)
    )
    remaining, _, status = resolve_attack_sequence_until_blocked(
        state=s,
        decisions=decisions,
        ruleset_descriptor=s.runtime_ruleset_descriptor(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "s12-retention",
            event_log=decisions.event_log,
            injected_results=fixed_sequence_dice(sequence, target, (6,), (6,), (1,)),
        ),
    )
    assert remaining is not None
    assert status is not None
    assert status.decision_request is not None
    retain(s, decisions, status.decision_request)
    return s, target, living, decisions
