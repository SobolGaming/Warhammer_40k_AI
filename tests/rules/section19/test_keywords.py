"""19.03 including its Anti-Psyker example and FAQs 35/51/64."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section19_fixtures import LORD, attached_scene
from warhammer40k_core.core.weapon_profiles import AbilityDescriptor
from warhammer40k_core.engine.weapon_abilities import anti_keyword_critical_threshold


@pytest.mark.parametrize("source_role", ["leader", "support"])
@pytest.mark.parametrize("alive", [False, True])
def test_keyword_union_anti_psyker_does_not_transfer_physical_model_keywords(
    section19_definitions: Section02Definitions,
    source_role: str,
    alive: bool,
) -> None:
    from tests.support.section19_fixtures import PSYKER

    s = attached_scene(
        section19_definitions,
        support=source_role == "support",
        leader_sheet=PSYKER if source_role == "leader" else LORD,
    )
    source = s.component(source_role)
    assert "PSYKER" in source.own_models[0].keywords
    assert all("PSYKER" not in m.keywords for m in s.body.own_models)
    if not alive:
        s.set_living(source_role, 0)
    assert ("PSYKER" in s.view.keywords) is alive
    assert all("PSYKER" not in m.keywords for m in s.body.own_models)
    native = section19_definitions.weapon(f"{LORD}:bolt-pistol")
    # Stated Section19 Anti-Psyker4+ exemplar as a typed weapon contract.
    anti = replace(native, keywords=(), abilities=(AbilityDescriptor.anti_keyword("PSYKER", 4),))
    assert anti_keyword_critical_threshold(profile=anti, target_keywords=s.view.keywords) == (
        4 if alive else None
    )
    assert anti_keyword_critical_threshold(profile=anti, target_keywords=("PSYKER ELITE",)) is None
