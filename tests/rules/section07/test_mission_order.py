"""Default source-owned sequencing policy, independent of input and display order."""

from dataclasses import replace

import pytest

from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.sequencing import (
    SequencingConflictContext,
    SequencingParticipant,
    SequencingRequirement,
    SequencingRuleOrigin,
    apply_select_next_sequencing_participant_from_request,
    create_select_next_sequencing_participant_request,
)
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)


@pytest.mark.parametrize(
    "trigger", [TimingTriggerKind.END_TURN, TimingTriggerKind.END_BATTLE_ROUND]
)
@pytest.mark.parametrize("active", ["owner", "opponent"])
@pytest.mark.parametrize("reverse", [False, True])
def test_nonmission_rules_finish_before_both_players_mission_rules(
    trigger: TimingTriggerKind, active: str, reverse: bool
) -> None:
    window = TimingWindow(
        window_id="constructed:s07:boundary",
        game_id="s07",
        battle_round=2,
        active_player_id=active,
        descriptor=TimingWindowDescriptor(
            descriptor_id="constructed:s07:timing",
            trigger_kind=trigger,
            source_rule_id="constructed:s07:boundary",
        ),
    )
    context = SequencingConflictContext(
        conflict_id=window.window_id,
        game_id="s07",
        timing_window=window,
        player_ids=("owner", "opponent"),
        active_player_id=active,
    )
    # These are typed source-occurrence contracts, not invented scoring results.
    participants = tuple(
        SequencingParticipant(
            participant_id=f"{origin.value}:{player}",
            player_id=player,
            source_rule_id=f"constructed:s07:{origin.value}:{player}",
            requirement=SequencingRequirement.MANDATORY,
            origin=origin,
            label="a" if origin is SequencingRuleOrigin.MISSION else "z",
        )
        for origin in (SequencingRuleOrigin.MISSION, SequencingRuleOrigin.PLAYER)
        for player in ("owner", "opponent")
    )
    remaining = tuple(reversed(participants)) if reverse else participants
    observed: list[str] = []
    previous: tuple[str, ...] = ()
    while remaining:
        request = create_select_next_sequencing_participant_request(
            request_id=f"s07-order-{len(previous)}",
            context=context,
            previously_selected_participant_ids=previous,
            remaining_participants=remaining,
        )
        assert len(request.options) == 1
        result = DecisionResult.for_request(
            result_id=f"s07-result-{len(previous)}",
            request=request,
            selected_option_id=request.options[0].option_id,
        )
        with pytest.raises(DecisionError, match="actor"):
            apply_select_next_sequencing_participant_from_request(
                request=request, result=replace(result, actor_id="intruder")
            )
        selected = apply_select_next_sequencing_participant_from_request(
            request=request, result=result
        )
        observed.append(selected.selected_participant_id)
        previous = (*previous, selected.selected_participant_id)
        remaining = tuple(
            p for p in remaining if p.participant_id != selected.selected_participant_id
        )
    other = "opponent" if active == "owner" else "owner"
    assert observed == [
        f"player:{active}",
        f"player:{other}",
        f"mission:{active}",
        f"mission:{other}",
    ]
    assert context.sequence_exception_source_id is not None
