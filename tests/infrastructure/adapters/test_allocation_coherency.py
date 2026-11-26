"""Compact policy regression from the native Round 5 Screen Rod fork."""

from __future__ import annotations

import pytest

from tests.support.screen_rod_allocation import (
    CAVALCADE_RULESET,
    SCREEN_ROD_MODEL_IDS,
    screen_rod_allocation_view,
)
from warhammer40k_core.ai.allocation_coherency import AllocationCoherencyPolicy
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyError


def test_screen_rod_allocation_ranks_issued_choices_by_survivor_coherency() -> None:
    context = PlayerDecisionContext.from_view(
        screen_rod_allocation_view(SCREEN_ROD_MODEL_IDS), choice_seed=0
    )
    policy = AllocationCoherencyPolicy(CAVALCADE_RULESET)
    scores = policy.score_options(context)
    issued = [option["option_id"] for option in context.request["options"]]
    assert list(scores) == issued
    assert tuple(scores.values()) == (False, False, True, False, True, False)
    assert policy.choose(context) == context.select_option(issued[2])


@pytest.mark.parametrize(("indices", "coherent"), [((0,), False), ((4, 2), True)])
def test_allocation_honors_only_option_and_retains_issued_order_on_tie(
    indices: tuple[int, ...], coherent: bool
) -> None:
    # The singleton models a constrained option set. Native forced allocation
    # resolves before a policy request. Reversed tied options test issued order.
    context = PlayerDecisionContext.from_view(
        screen_rod_allocation_view(tuple(SCREEN_ROD_MODEL_IDS[index] for index in indices)),
        choice_seed=100,
    )
    policy = AllocationCoherencyPolicy(CAVALCADE_RULESET)
    issued = [option["option_id"] for option in context.request["options"]]
    assert policy.score_options(context) == dict.fromkeys(issued, coherent)
    assert policy.choose(context) == context.select_option(issued[0])


def test_allocation_requires_defender_visible_formation() -> None:
    view = screen_rod_allocation_view(SCREEN_ROD_MODEL_IDS[:2])
    del view["model_display_by_id"][SCREEN_ROD_MODEL_IDS[-1]]
    context = PlayerDecisionContext.from_view(view, choice_seed=0)
    with pytest.raises(PolicyError, match="visible geometry"):
        AllocationCoherencyPolicy(CAVALCADE_RULESET).choose(context)
