from __future__ import annotations

import re

import pytest

from warhammer40k_core.engine.catalog_selected_target_battle_shock import (
    payload_optional_string,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.rule_ir import RuleIRError
from warhammer40k_core.rules.rule_parser_token_helpers import (
    ability_token,
    battle_round_number,
    catalog_like_token,
    contextual_status_target_scope_token,
    object_kind_token,
    owner_token,
    post_shoot_subject_token,
    range_kind_token,
    roll_type,
    subject_token,
)


def test_rule_parser_token_helpers_cover_numeric_and_optional_paths() -> None:
    assert owner_token(None) is None
    assert owner_token("your opponent's") == "opponent"
    assert owner_token("your") == "active_player"
    assert owner_token("another") is None

    assert battle_round_number("3rd") == 3
    assert battle_round_number("fifth") == 5
    with pytest.raises(RuleIRError, match="Unsupported battle round ordinal"):
        battle_round_number("last")

    assert roll_type("Wound Roll") == "wound_roll"
    assert subject_token("this-model") == "this_model"
    assert post_shoot_subject_token("the bearer") == "bearer"
    with pytest.raises(RuleIRError, match="Unsupported post-shoot subject"):
        post_shoot_subject_token("the target")


def test_rule_parser_token_helpers_cover_scope_and_object_branches() -> None:
    model_match = re.search(r"(?P<subject>models in selected unit)", "models in selected unit")
    assert model_match is not None
    assert contextual_status_target_scope_token(model_match) == "models_in_selected_unit"

    unit_match = re.search(r"(?P<subject>that enemy unit)", "that enemy unit")
    assert unit_match is not None
    assert contextual_status_target_scope_token(unit_match) == "selected_unit"

    bad_match = re.search(r"(?P<subject>the battlefield)", "the battlefield")
    assert bad_match is not None
    with pytest.raises(RuleIRError, match="Unsupported contextual status target"):
        contextual_status_target_scope_token(bad_match)

    assert range_kind_token('6"') == "numeric_range"
    assert range_kind_token("Engagement Range") == "engagement_range"
    assert object_kind_token("objective markers") == "objective_marker"
    assert object_kind_token("models") == "model"
    assert object_kind_token("units") == "unit"
    with pytest.raises(RuleIRError, match="Unsupported distance relation object kind"):
        object_kind_token("terrain features")

    assert ability_token(' [ Scouts 6" ], ') == 'Scouts 6"'
    assert catalog_like_token("Shadow-of Chaos") == "shadow_of_chaos"


def test_selected_target_battle_shock_optional_payload_string_is_fail_fast() -> None:
    assert payload_optional_string({}, key="missing") is None
    assert payload_optional_string({"source": None}, key="source") is None
    assert payload_optional_string({"source": "rule-a"}, key="source") == "rule-a"
    with pytest.raises(GameLifecycleError, match="must be a string"):
        payload_optional_string({"source": 1}, key="source")
