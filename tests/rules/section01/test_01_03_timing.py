"""Active context and native finite sequencing choices, without phase traversal."""

from dataclasses import replace

import pytest

from tests.support.section01_fixtures import minimal_state
from tests.support.section02_fixtures import Section02Definitions
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.engine.active_player import effective_active_player_id
from warhammer40k_core.engine.active_player_scopes import (
    ActivePlayerScope,
    ActivePlayerScopeKind,
    pop_scope,
    push_scope,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.phase import GameLifecycleError
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


@pytest.mark.parametrize("kind", list(ActivePlayerScopeKind))
def test_01_03_selected_controller_and_nested_completion(
    section01_definitions: Section02Definitions, kind: ActivePlayerScopeKind
) -> None:
    state = minimal_state(section01_definitions)
    unit = state.army_definitions[0].units[0]
    state.active_player_id = "opponent"
    assert state.effective_active_player_id() == "opponent"
    outer = ActivePlayerScope(
        kind, "owner", unit.unit_instance_id, "core:01.03", "selection", "result"
    )
    inner = replace(outer, selection_request_id="nested", selection_result_id="nested-result")
    push_scope(state, outer)
    push_scope(state, inner)
    assert state.effective_active_player_id() == "owner"
    assert state.active_player_id == "opponent"
    with pytest.raises(GameLifecycleError, match="nested scope"):
        pop_scope(state, outer)
    pop_scope(state, inner)
    assert state.effective_active_player_id() == "owner"
    pop_scope(state, outer)
    assert state.effective_active_player_id() == "opponent"


@pytest.mark.parametrize(
    "trigger",
    [TimingTriggerKind.START_BATTLE_ROUND, TimingTriggerKind.END_BATTLE_ROUND],
)
@pytest.mark.parametrize("first", ["owner", "opponent"])
def test_01_03_between_turns_first_player(
    section01_definitions: Section02Definitions, trigger: TimingTriggerKind, first: str
) -> None:
    state = minimal_state(section01_definitions)
    state.turn_order = (first, "opponent" if first == "owner" else "owner")
    state.active_player_id = state.turn_order[1]
    assert effective_active_player_id(state, trigger_kind=trigger) == first


@pytest.mark.parametrize("active", ["owner", "opponent"])
def test_01_03_02_mission_then_four_tiers_each_owners_choice(active: str) -> None:
    other = "opponent" if active == "owner" else "owner"
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
        active,
        BattlePhaseKind.SHOOTING,
    )
    context = SequencingConflictContext(
        "conflict", "section01", window, ("owner", "opponent"), active
    )
    tiers = (
        (None, SequencingRequirement.MANDATORY),
        (active, SequencingRequirement.MANDATORY),
        (active, SequencingRequirement.OPTIONAL),
        (other, SequencingRequirement.MANDATORY),
        (other, SequencingRequirement.OPTIONAL),
    )
    participants: tuple[SequencingParticipant, ...] = tuple(
        SequencingParticipant(
            f"tier-{i}:{j}",
            owner,
            f"source:{i}:{j}",
            requirement,
            origin=SequencingRuleOrigin.MISSION if owner is None else SequencingRuleOrigin.PLAYER,
        )
        for i, (owner, requirement) in enumerate(tiers)
        for j in range(2)
    )
    previous: tuple[str, ...] = ()
    for i, (owner, _) in enumerate(tiers):
        for j in (1, 0):
            request = create_select_next_sequencing_participant_request(
                request_id=f"request:{i}:{j}",
                context=context,
                previously_selected_participant_ids=previous,
                remaining_participants=participants,
            )
            assert request.actor_id == (active if owner is None else owner)
            assert {o.option_id for o in request.options} == {
                f"next:tier-{i}:{k}" for k in range(j + 1)
            }
            selected = f"tier-{i}:{j}"
            decision = apply_select_next_sequencing_participant_from_request(
                request=request,
                result=DecisionResult.for_request(
                    result_id=f"chosen:{i}:{j}",
                    request=request,
                    selected_option_id=f"next:{selected}",
                ),
            )
            assert decision.selected_participant_id == selected
            previous += (selected,)
            participants = tuple(p for p in participants if p.participant_id != selected)
    assert len(previous) == 10
