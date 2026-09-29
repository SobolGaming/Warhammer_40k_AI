"""Exercise singular/plural keyword text through normalization and a real unit gate."""

from __future__ import annotations

import json

from tests.support.ability_presence_fixtures import ability_presence_fixture
from warhammer40k_core.engine.rule_target_resolution import unit_has_required_keywords
from warhammer40k_core.engine.unit_keyword_queries import unit_has_keyword
from warhammer40k_core.rules.rule_keyword_sequences import keyword_sequence_tokens


def keyword_number_observation() -> dict[str, object]:
    _config, state, _decisions = ability_presence_fixture(embarked=False)
    unit = state.army_definitions[0].unit_by_id("army-alpha:leader")
    assert "CHARACTER" in unit.keywords
    singular = keyword_sequence_tokens("CHARACTER", source_keyword_sequence_parts=("CHARACTER",))
    plural = keyword_sequence_tokens("CHARACTERS", source_keyword_sequence_parts=("CHARACTER",))
    matches = [
        unit_has_required_keywords(
            unit_keywords=unit.keywords,
            faction_keywords=unit.faction_keywords,
            required_keywords=required,
        )
        for required in (singular, plural)
    ]
    assert matches == [True, False]
    assert unit_has_keyword(unit, "CHARACTER")
    assert not unit_has_keyword(unit, "CHARACTERS")
    return {
        "requirement_id": "02.05.01-obligation-12",
        "source_inputs": ["CHARACTER", "CHARACTERS"],
        "normalized_tokens": [list(singular), list(plural)],
        "unit_instance_id": unit.unit_instance_id,
        "unit_keywords": list(unit.keywords),
        "target_gate_matches": matches,
        "expected_target_gate_matches": [True, True],
        "qualification": (
            "The source keyword-sequence normalizer preserves different tokens for the "
            "singular and plural, and the actual typed unit target gate fails the plural. "
            "This is keyword identity, distinct from model-owner label pluralization."
        ),
    }


if __name__ == "__main__":
    print(json.dumps(keyword_number_observation(), ensure_ascii=False, indent=2))
