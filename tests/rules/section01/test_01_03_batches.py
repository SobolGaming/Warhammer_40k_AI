"""New triggers wait for the original population; ownership scopes consumption."""

import pytest

from tests.support.section01_fixtures import core_rule
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.engine.event_log import EventLog
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rule_frequency import (
    consume_optional_ability_frequency,
    optional_ability_frequency_unavailable_reason,
)
from warhammer40k_core.engine.sequencing import (
    SequencingConflictContext,
    SequencingParticipant,
    SequencingRequirement,
    SequencingRuleOrigin,
)
from warhammer40k_core.engine.timing_batch_state import TimingBatch
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)


def test_01_03_02_new_trigger_waits_until_original_rules_finish() -> None:
    window = TimingWindow(
        "window",
        TimingWindowDescriptor(
            "descriptor",
            TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT,
            "core:01.03.02",
            phase=BattlePhaseKind.SHOOTING,
        ),
        "section01",
        1,
        "owner",
        BattlePhaseKind.SHOOTING,
    )
    context = SequencingConflictContext(
        "conflict", "section01", window, ("owner", "opponent"), "owner"
    )
    first = SequencingParticipant("first", "owner", "source:first", SequencingRequirement.MANDATORY)
    last = SequencingParticipant("last", "opponent", "source:last", SequencingRequirement.OPTIONAL)
    new = SequencingParticipant("new", "owner", "source:new", SequencingRequirement.MANDATORY)
    batch = (
        TimingBatch.open(context=context, participants=(last, first))
        .select("first")
        .defer((new,))
        .complete("first")
    )
    assert batch.eligible_participants() == (last,)
    with pytest.raises(GameLifecycleError, match="before the batch completes"):
        batch.release_deferred()
    with pytest.raises(GameLifecycleError, match="not eligible"):
        batch.select("new")
    subsequent = batch.select("last").complete("last").release_deferred()
    assert subsequent is not None
    assert subsequent.generation == 1
    assert subsequent.eligible_participants() == (new,)
    assert subsequent.select("new").complete("new").release_deferred() is None


@pytest.mark.parametrize("other_unit", ["same-unit", "different-unit"])
def test_01_03_01_frequency_is_owned_and_not_shared_between_players(
    other_unit: str,
) -> None:
    rule = core_rule(
        "Once per battle, in your Shooting phase, this unit can use this ability. "
        "If it does, add 1 to the Attacks characteristic of ranged weapons "
        "equipped by models in this unit."
    )
    (clause,) = rule.clauses
    log = EventLog()
    events = consume_optional_ability_frequency(
        rule_ir=rule,
        clause=clause,
        event_log=log,
        player_id="owner",
        source_unit_instance_id="same-unit",
        source_model_instance_id=None,
        battle_round=1,
        phase=BattlePhaseKind.SHOOTING,
        active_player_id="owner",
        timing_window_id="window",
    )
    assert len(events) == 1
    assert (
        optional_ability_frequency_unavailable_reason(
            rule_ir=rule,
            clause=clause,
            event_log=log,
            player_id="owner",
            source_unit_instance_id="same-unit",
            source_model_instance_id=None,
        )
        == "frequency_limit_exhausted:battle"
    )
    assert (
        optional_ability_frequency_unavailable_reason(
            rule_ir=rule,
            clause=clause,
            event_log=log,
            player_id="opponent",
            source_unit_instance_id=other_unit,
            source_model_instance_id=None,
        )
        is None
    )


def test_01_03_01_owned_mission_rule_uses_its_player_tier() -> None:
    from warhammer40k_core.engine.sequencing import eligible_sequencing_participants

    window = TimingWindow(
        "window",
        TimingWindowDescriptor(
            "descriptor",
            TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT,
            "core:01.03.02",
            phase=BattlePhaseKind.SHOOTING,
        ),
        "section01",
        1,
        "owner",
        BattlePhaseKind.SHOOTING,
    )
    context = SequencingConflictContext(
        "conflict", "section01", window, ("owner", "opponent"), "owner"
    )
    active = SequencingParticipant(
        "active", "owner", "source:active", SequencingRequirement.MANDATORY
    )
    owned = SequencingParticipant(
        "mission",
        "opponent",
        "source:mission",
        SequencingRequirement.MANDATORY,
        origin=SequencingRuleOrigin.MISSION,
    )
    assert eligible_sequencing_participants(context=context, participants=(owned, active)) == (
        active,
    )
    assert eligible_sequencing_participants(context=context, participants=(owned,)) == (owned,)
