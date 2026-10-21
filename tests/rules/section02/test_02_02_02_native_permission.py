"""Native Siege Crawler permission and recorded any-subset decisions."""

from typing import cast

import pytest

from tests.support.section02_consumers import combat_state
from tests.support.section02_fixtures import MAULERFIEND, Section02Definitions
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.ability_catalog import catalog_ability_records_from_catalog
from warhammer40k_core.engine.catalog_modifier_ignore import (
    ModifierIgnoreKind,
    catalog_modifier_ignore_permissions_for_unit,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.modifier_evaluation import ModifierEvaluationSubject, select_modifiers


@pytest.mark.parametrize("ignored", [(), ("bonus",), ("penalty",), ("bonus", "penalty")])
def test_02_02_02_native_permission_allows_each_recorded_subset(
    section02_definitions: Section02Definitions, ignored: tuple[str, ...]
) -> None:
    unit = section02_definitions.unit(MAULERFIEND)
    records = catalog_ability_records_from_catalog(section02_definitions.package.army_catalog)
    index = AbilityCatalogIndex.from_records(records)
    permissions = catalog_modifier_ignore_permissions_for_unit(
        ability_index=index, unit=unit, current_model_instance_ids=unit.own_model_ids()
    )
    assert len(permissions) == 1
    assert set(permissions[0].modifier_kinds) == {
        ModifierIgnoreKind.MOVEMENT_CHARACTERISTIC,
        ModifierIgnoreKind.ADVANCE_ROLL,
        ModifierIgnoreKind.CHARGE_ROLL,
    }
    assert not permissions[0].supports(ModifierIgnoreKind.HIT_ROLL)
    state = combat_state(
        section02_definitions,
        unit,
        section02_definitions.unit(identity="target", army_id="opponent-army"),
    )
    decisions = DecisionController()
    modifiers = (
        RollModifier("bonus", 2, "core:02.02.02"),
        RollModifier("penalty", -3, "core:02.02.02"),
    )
    subject = ModifierEvaluationSubject(unit.unit_instance_id, ModifierIgnoreKind.ADVANCE_ROLL)
    result = None
    for iteration in range(3):
        result = select_modifiers(
            state=state,
            decisions=decisions,
            ability_index=index,
            occurrence_id="advance",
            subject=subject,
            modifiers=modifiers,
            source_context={},
        )
        if result.pending_status is None:
            break
        request = decisions.queue.peek_next()
        assert request.actor_id == "owner"
        payload = cast(dict[str, JsonValue], request.payload)
        decided = cast(list[str], payload["decided_modifier_ids"])
        next_ids = [m.modifier_id for m in modifiers][: len(decided) + 1]
        next_ignored = sorted(set(next_ids) & set(ignored))
        option = next(
            o
            for o in request.options
            if isinstance(o.payload, dict)
            and o.payload["decided_modifier_ids"] == next_ids
            and o.payload["ignored_modifier_ids"] == next_ignored
        )
        decisions.submit_result(
            DecisionResult.for_request(
                result_id=f"choice-{iteration}",
                request=request,
                selected_option_id=option.option_id,
            )
        )
    assert result is not None
    assert result.pending_status is None
    assert result.ignored_modifier_ids == tuple(sorted(ignored))
    assert result.modifiers == tuple(m for m in modifiers if m.modifier_id not in ignored)
    assert len(decisions.records) == 2
