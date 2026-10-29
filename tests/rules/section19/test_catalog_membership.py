"""Roster ability admission is stable through actual attached casualties.

Loaded content membership is separate from live keyword/ability eligibility.
No destroyed model gains live rules authority by retaining a catalog record.
"""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section19_fixtures import attached_scene, destroy
from warhammer40k_core.engine.abilities import KeywordGate, movement_capability_flags_from_index
from warhammer40k_core.engine.ability_catalog import (
    build_player_ability_index,
    eleventh_edition_core_ability_catalog_records,
)
from warhammer40k_core.engine.decision_controller import DecisionController


@pytest.mark.parametrize("casualties", ["none", "leader", "bodyguard", "all"])
def test_actual_casualties_preserve_selected_content_but_remove_live_keywords(
    section19_definitions: Section02Definitions,
    casualties: str,
) -> None:
    s = attached_scene(section19_definitions)
    records = eleventh_edition_core_ability_catalog_records()
    army = s.state.army_definition_for_player("owner")
    assert army is not None
    initial = build_player_ability_index(
        records, army=army, catalog=s.definitions.package.army_catalog
    )
    initial_ids = tuple(r.record_id for r in initial.all_records())
    # The canonical Core-leader record belongs to its canonical datasheet; it
    # must not be invented as native Lord Exultant admission.
    assert "gw-11e-core-abilities:datasheet:core-leader" not in initial_ids
    assert "gw-11e-core-abilities:keyword:keyword-infantry" in initial_ids
    decisions = DecisionController()
    doomed = (
        s.leader.own_model_ids()
        if casualties == "leader"
        else s.body.own_model_ids()
        if casualties == "bodyguard"
        else tuple(m.model_instance_id for m in s.view.alive_models())
        if casualties == "all"
        else ()
    )
    for model_id in doomed:
        destroy(s, decisions, model_id)
    current_army = s.state.army_definition_for_player("owner")
    assert current_army is not None
    rebuilt = build_player_ability_index(
        records, army=current_army, catalog=s.definitions.package.army_catalog
    )
    assert tuple(r.record_id for r in rebuilt.all_records()) == initial_ids
    if casualties in {"leader", "all"}:
        assert "CHARACTER" not in s.view.keywords
    if casualties == "all":
        assert s.view.keywords == ()
        assert s.view.alive_models() == ()
        assert movement_capability_flags_from_index(index=rebuilt, keywords=s.view.keywords) == ()
    # Unselected content remains absent even when its base record is a Core
    # family. Retaining admitted records does not turn admission into allow-all.
    infantry = next(r for r in records if r.record_id.endswith("keyword:keyword-infantry"))
    unselected = replace(
        infantry,
        definition=replace(
            infantry.definition, keyword_gate=KeywordGate(required_keywords=("TRANSPORT",))
        ),
    )
    absent = build_player_ability_index(
        (unselected,), army=current_army, catalog=s.definitions.package.army_catalog
    )
    assert absent.all_records() == ()
