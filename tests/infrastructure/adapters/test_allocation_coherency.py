"""Compact policy regression from the native Round 5 Screen Rod fork."""

from __future__ import annotations

from typing import cast

import pytest

from warhammer40k_core.adapters.battlefield_projection import BattlefieldViewPayload
from warhammer40k_core.adapters.projection import (
    PROJECTION_SCHEMA_VERSION,
    DecisionRequestViewPayload,
    GameViewPayload,
    ModelDisplayPayload,
)
from warhammer40k_core.ai.allocation_coherency import AllocationCoherencyPolicy
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyError
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.damage_allocation import SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE

_ACTOR = "player-b"
_UNIT = "defending-formation"
_DECISION = SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE
_RULESET = RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
    descriptor_version="cavalcade-v995-mirror"
)
# Fork 000396, in issued order (five Bloodcrushers and one Bloodhunter).
# Fork-board SHA-256: 1e755b22eaffd5d6e87e88f1c2bcd6ad0d8ac57f08031c4b75c1b61917f95b8c.
# The six bases share the same dimensions, height, elevation and facing.
_POSITIONS = (
    (17.66, 35.62),
    (19.90, 36.04),
    (15.70, 37.02),
    (21.58, 38.65),
    (19.38, 43.46),
    (21.52, 42.24),
)
_MODEL_IDS = tuple(f"model-{index}" for index in range(len(_POSITIONS)))


def _screen_rod_view(issued_model_ids: tuple[str, ...]) -> GameViewPayload:
    """Keep just the projected fields used by the policy, with remapped identities."""
    geometry = {
        "footprint_kind": "oval",
        "geometry_source_id": "fixture-oval",
        "geometry_source_kind": "catalog_geometry_record",
        "height_inches": 2.75,
        "height_source_id": "fixture-height",
        "height_source_kind": "catalog_geometry_record",
        "parts": [
            {
                "footprint_kind": "oval",
                "offset_x_inches": 0.0,
                "offset_y_inches": 0.0,
                "part_id": "base",
                "radius_x_inches": 1.7716535433070868,
                "radius_y_inches": 1.033464566929134,
            }
        ],
    }
    models = {
        model_id: {
            "owner_player_id": _ACTOR,
            "rules_unit_instance_id": _UNIT,
            "unit_instance_id": _UNIT,
            "state": "placed",
            "pose": {
                "position": {"x_inches": x, "y_inches": y, "z_inches": 0.0},
                "facing_degrees": 90.0,
            },
        }
        for model_id, (x, y) in zip(_MODEL_IDS, _POSITIONS, strict=True)
    }
    request = cast(
        DecisionRequestViewPayload,
        {
            "actor_id": _ACTOR,
            "request_id": "view-allocation",
            "decision_type": _DECISION,
            "interaction": {"proposal_kind": None},
            "is_parameterized": False,
            "payload": {
                "allocation_context": {
                    "target_unit_instance_id": _UNIT,
                    "alive_model_ids": list(_MODEL_IDS),
                },
            },
            "options": [
                {
                    "option_id": f"select-{model_id}",
                    "label": model_id,
                    "payload": {"selected_model_id": model_id, "submission_kind": _DECISION},
                }
                for model_id in issued_model_ids
            ],
        },
    )
    displays = {
        model_id: cast(
            ModelDisplayPayload,
            {"geometry": geometry, "keywords": [], "redaction": {"hidden": False}},
        )
        for model_id in _MODEL_IDS
    }
    battlefield = cast(BattlefieldViewPayload, {"authoritative": {"models_by_id": models}})
    return cast(
        GameViewPayload,
        {
            "projection_schema": PROJECTION_SCHEMA_VERSION,
            "stage": "battle",
            "current_setup_step": None,
            "current_battle_phase": "shooting",
            "viewer_role": "player",
            "viewer_player_id": _ACTOR,
            "player_ids": ["player-a", _ACTOR],
            "pending_decision": request,
            "battlefield_view": battlefield,
            "model_display_by_id": displays,
        },
    )


def test_screen_rod_allocation_ranks_issued_choices_by_survivor_coherency() -> None:
    context = PlayerDecisionContext.from_view(_screen_rod_view(_MODEL_IDS), choice_seed=0)
    policy = AllocationCoherencyPolicy(_RULESET)
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
        _screen_rod_view(tuple(_MODEL_IDS[index] for index in indices)),
        choice_seed=100,
    )
    policy = AllocationCoherencyPolicy(_RULESET)
    issued = [option["option_id"] for option in context.request["options"]]
    assert policy.score_options(context) == dict.fromkeys(issued, coherent)
    assert policy.choose(context) == context.select_option(issued[0])


def test_allocation_requires_defender_visible_formation() -> None:
    view = _screen_rod_view(_MODEL_IDS[:2])
    del view["model_display_by_id"][_MODEL_IDS[-1]]
    context = PlayerDecisionContext.from_view(view, choice_seed=0)
    with pytest.raises(PolicyError, match="visible geometry"):
        AllocationCoherencyPolicy(_RULESET).choose(context)
