"""Section05-owned FAQ20 interaction assertions at retained Fight completion.

No new semantic owner: the approved after-removal expectation is SF05-002.
The second rule-caused death is an explicitly labelled checkpoint.
"""

from dataclasses import replace

import pytest

from tests.fight_on_death_helpers import retain_destroyed_model_for_fixture
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section05_fixtures import replace_unit
from tests.support.section05_retention import SOURCE, retain
from tests.support.section05_sequence import fixed_sequence_dice, native_sequence, resolve
from tests.support.section12_fixtures import LORD, add_native
from warhammer40k_core.engine.damage_allocation import (
    DestructionReactionSource,
    destroy_model_by_rule,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.destruction_reaction_kind import DestructionReactionKind
from warhammer40k_core.engine.event_log import EventLog, EventRecord
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.retained_destruction_cleanup import begin_retained_destruction_cleanup
from warhammer40k_core.engine.retained_destruction_state import (
    RetainedDestructionStage,
    retained_destruction_for_model,
)
from warhammer40k_core.engine.retained_model_presence import model_is_present_on_battlefield
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose


def _retained_demise(d: Section02Definitions) -> tuple[GameState, UnitInstance, DecisionController]:
    s, target, sequence = native_sequence(d, distance=2.5, melee=True)
    target = replace(target, own_models=(replace(target.own_models[0], wounds_remaining=1),))
    replace_unit(s, target)
    s.record_model_destruction_reaction_sources(
        model_instance_id=target.own_model_ids()[0],
        sources=(
            SOURCE,
            DestructionReactionSource(
                source_id="constructed:s12:demise",
                source_rule_id="constructed:s12:demise",
                reaction_kind=DestructionReactionKind.DEADLY_DEMISE,
                optional=False,
                payload={
                    "trigger_roll_threshold": 1,
                    "range_inches": 6.0,
                    "mortal_wounds": {"kind": "fixed", "value": 1},
                },
            ),
        ),
    )
    decisions, remaining, status = resolve(
        s, sequence, fixed_sequence_dice(sequence, target, (6,), (6,), (1,))
    )
    assert remaining is not None
    assert status is not None
    assert status.decision_request is not None
    retain(s, decisions, status.decision_request)
    return s, target, decisions


def test_section05_faq20_independent_enemy_retention_survives_other_cleanup_and_demise(
    section12_definitions: Section02Definitions,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    s, target, decisions = _retained_demise(section12_definitions)
    mid = target.own_model_ids()[0]
    # A separate authenticated generic rule-death checkpoint with its own real
    # source/result/retention cause, not universal protection from mutual FOD.
    other = section12_definitions.unit(LORD, identity="independent-retained")
    add_native(s, other, (Pose.at(10, 13),))
    assert s.battlefield_state is not None
    other_mid = other.own_model_ids()[0]
    placement = s.battlefield_state.model_placement_by_id(other_mid)
    destroy_model_by_rule(state=s, model_instance_id=other_mid, remove_from_battlefield=False)
    retain_destroyed_model_for_fixture(
        state=s,
        placement=placement,
        effect_id="constructed:s12:independent-fod",
        source_rule_id="constructed:s12:independent-fod",
        source_phase=BattlePhase.FIGHT,
        decisions=decisions,
    )
    record = retained_destruction_for_model(state=s, model_instance_id=other_mid)
    assert record is not None
    assert record.stage is RetainedDestructionStage.WAITING
    observed: list[tuple[bool, bool]] = []
    original_append = EventLog.append

    def observe(log: EventLog, event_type: str, payload: object) -> EventRecord:
        if log is decisions.event_log and event_type == "destruction_reaction_resolved":
            assert s.battlefield_state is not None
            observed.append(
                (
                    mid in s.battlefield_state.removed_model_ids,
                    model_is_present_on_battlefield(state=s, model_instance_id=other_mid),
                )
            )
        return original_append(log, event_type, payload)

    monkeypatch.setattr(EventLog, "append", observe)
    assert (
        begin_retained_destruction_cleanup(
            state=s,
            decisions=decisions,
            reason="unit_fight_completed",
            unit_instance_id=target.unit_instance_id,
        )
        is None
    )
    assert model_is_present_on_battlefield(state=s, model_instance_id=other_mid)
    assert retained_destruction_for_model(state=s, model_instance_id=other_mid) == record
    assert observed == [(True, True)]
