"""Authenticated death retention, visible physical presence and phase-end cleanup."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section05_retained_permission import (
    retained_permission_index,
)
from tests.support.section05_retention import retain, terminal_retention
from tests.support.section05_sequence import payloads
from warhammer40k_core.engine.abilities import AbilitySourceKind
from warhammer40k_core.engine.catalog_modifier_ignore import (
    ModifierIgnoreKind,
    modifier_ignore_permissions_for_subject,
)
from warhammer40k_core.engine.damage_allocation import model_by_id
from warhammer40k_core.engine.retained_destruction_cleanup import (
    begin_retained_destruction_cleanup,
)
from warhammer40k_core.engine.retained_destruction_state import (
    RetainedDestructionStage,
    retained_destruction_for_model,
)
from warhammer40k_core.engine.retained_model_presence import (
    model_is_present_on_battlefield,
)
from warhammer40k_core.engine.rules_unit_geometry import geometry_models_for_rules_unit


@pytest.mark.parametrize("demise", [False, True])
def test_retained_model_keeps_geometry_then_phase_end_removes_it(
    section05_definitions: Section02Definitions, demise: bool
) -> None:
    state, target, decisions, request = terminal_retention(section05_definitions, demise=demise)
    mid = target.own_model_ids()[0]
    assert not model_by_id(state=state, model_instance_id=mid).is_alive
    assert not payloads(decisions, "model_destroyed")
    assert not payloads(decisions, "destruction_reaction_resolved")
    record = retain(state, decisions, request)
    assert record.stage is RetainedDestructionStage.WAITING
    assert model_is_present_on_battlefield(state=state, model_instance_id=mid)
    assert {
        g.model_id
        for g in geometry_models_for_rules_unit(
            state=state, unit_instance_id=target.unit_instance_id
        )
    } == {mid}
    assert state.battlefield_state is not None
    assert state.battlefield_state.model_placement_by_id(mid) == record.placement
    status = begin_retained_destruction_cleanup(
        state=state, decisions=decisions, reason="phase_end"
    )
    assert status is None
    assert not model_is_present_on_battlefield(state=state, model_instance_id=mid)
    assert mid in state.battlefield_state.removed_model_ids
    assert len(payloads(decisions, "model_destroyed")) == 1
    done = retained_destruction_for_model(state=state, model_instance_id=mid)
    assert done is None
    if demise:
        events = decisions.event_log.records
        ready = next(
            i for i, e in enumerate(events) if e.event_type == "fight_on_death_destruction_ready"
        )
        reaction = next(
            i for i, e in enumerate(events) if e.event_type == "destruction_reaction_resolved"
        )
        assert ready < reaction


def test_faq49_datasheet_permission_needs_authenticated_retention(
    section05_definitions: Section02Definitions,
) -> None:
    state, target, decisions, request = terminal_retention(section05_definitions)
    mid = target.own_model_ids()[0]
    # Reuse immutable typed RuleIR contract only; native model and all state are fresh.
    index = retained_permission_index(target, AbilitySourceKind.DATASHEET)
    assert (
        modifier_ignore_permissions_for_subject(
            state=state,
            ability_index=index,
            unit_instance_id=target.unit_instance_id,
            model_instance_id=mid,
            kind=ModifierIgnoreKind.HIT_ROLL,
        )
        == ()
    )
    retain(state, decisions, request)
    assert (
        len(
            modifier_ignore_permissions_for_subject(
                state=state,
                ability_index=index,
                unit_instance_id=target.unit_instance_id,
                model_instance_id=mid,
                kind=ModifierIgnoreKind.HIT_ROLL,
            )
        )
        == 1
    )
