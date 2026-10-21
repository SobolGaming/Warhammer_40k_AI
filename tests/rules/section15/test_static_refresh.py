"""SF15-001: native casualty refresh keeps permanent source evidence immutable."""

from copy import deepcopy
from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section15_fixtures import checkpoint
from warhammer40k_core.engine.damage_allocation import DamageKind, apply_damage_to_model
from warhammer40k_core.engine.phase import GameLifecycleError


@pytest.mark.parametrize("lost", [0, 1, 6])
def test_native_lord_static_evidence_survives_partial_and_complete_damage(
    section15_definitions: Section02Definitions, lost: int
) -> None:
    session, state, unit, _ = checkpoint(section15_definitions)
    own = state.army_definition_for_player("owner")
    assert own is not None
    model = own.unit_by_id(unit).own_models[0]
    effects = tuple(state.persisting_effects)
    assert effects
    if lost:
        apply_damage_to_model(
            state=state,
            target_unit_instance_id=unit,
            model_instance_id=model.model_instance_id,
            damage=lost,
            damage_kind=DamageKind.NORMAL,
        )
    session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    assert tuple(state.persisting_effects) == effects
    # This fixes provenance reconstruction, not live keyword membership.
    current = state.army_definition_for_player("owner")
    assert current is not None
    actual = current.unit_by_id(unit)
    assert bool(actual.keywords) is actual.own_models[0].is_alive
    assert actual.own_models[0].current_wounds == max(0, model.current_wounds - lost)


def test_static_identity_conflicts_still_fail_closed(
    section15_definitions: Section02Definitions,
) -> None:
    session, state, _unit, _ = checkpoint(section15_definitions)
    first = state.persisting_effects[0]
    payload = deepcopy(first.effect_payload)
    assert isinstance(payload, dict)
    payload["descriptor_id"] = "constructed:s15:tampered"
    state.persisting_effects[0] = replace(first, effect_payload=payload)
    # Invoke the shared producer directly so a cached lifecycle cannot mask drift.
    from warhammer40k_core.engine.catalog_conditional_leader_abilities import (
        CatalogConditionalLeaderAbilityRuntime,
    )

    bundle = session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(GameLifecycleError, match="conflicts with state"):
        CatalogConditionalLeaderAbilityRuntime(
            bundle.ability_indexes_by_player_id, tuple(state.army_definitions)
        ).record_static_effects(state=state)
