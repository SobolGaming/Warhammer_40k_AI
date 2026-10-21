"""Destroy through the live rule owner, then measure authenticated former geometry."""

import pytest

from tests.generic_modifier_helpers import generic_effect
from tests.support.section02_fixtures import (
    INFRACTORS,
    LORD_EXULTANT,
    MAULERFIEND,
    Section02Definitions,
)
from tests.support.section04_fixtures import combat_state
from warhammer40k_core.engine.battlefield_state import geometry_model_for_placement
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.destroyed_referent_measurement import (
    distance_to_destroyed_model,
    distance_to_destroyed_unit,
    former_footprint_for_destroyed_model,
    former_footprint_for_destroyed_unit,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.retained_model_presence import (
    model_is_present_on_battlefield,
)
from warhammer40k_core.engine.rule_model_destruction import (
    destroy_model_with_rule_reactions,
)
from warhammer40k_core.geometry.measurement import DistanceMeasurementContext


@pytest.mark.parametrize("datasheet", [LORD_EXULTANT, MAULERFIEND, "000000599", INFRACTORS])
def test_former_base_or_hull_and_last_destroyed_member(
    section05_definitions: Section02Definitions, datasheet: str
) -> None:
    d = section05_definitions
    source = d.unit(LORD_EXULTANT)
    target = d.unit(datasheet, army_id="enemy", identity="target")
    state = combat_state(d, source, target=target, distance=20)
    assert state.battlefield_state is not None
    bf = state.battlefield_state
    source_geometry = geometry_model_for_placement(
        model=source.own_models[0],
        placement=bf.model_placement_by_id(source.own_model_ids()[0]),
    )
    expected = {
        m.model_instance_id: DistanceMeasurementContext.from_models(
            source_geometry,
            geometry_model_for_placement(
                model=m, placement=bf.model_placement_by_id(m.model_instance_id)
            ),
        ).closest_distance_inches()
        for m in target.own_models
    }
    decisions = DecisionController()
    for i, model in enumerate(target.own_models):
        effect_id = f"constructed:s05:destroy:{i}"
        state.record_persisting_effect(
            generic_effect(
                effect_id=effect_id,
                owner_player_id="owner",
                target_unit_instance_ids=(target.unit_instance_id,),
                target_kind="selected_unit",
                effect_kind="set_contextual_status",
                parameters={"status": "s05_destruction_liability"},
            )
        )
        outcome = destroy_model_with_rule_reactions(
            state=state,
            decisions=decisions,
            model_instance_id=model.model_instance_id,
            rules_unit_instance_id=target.unit_instance_id,
            destroying_player_id="owner",
            source_rule_id="constructed:s05:destroy",
            source_effect_ids=(effect_id,),
            source_phase=BattlePhase.SHOOTING,
            source_step="s05:rule",
            source_result_id=f"s05:destroy:{i}",
            completion_event_type="section05_rule_completed",
            completion_event_payload={"index": i},
        )
        assert outcome.status is None
        mid = model.model_instance_id
        assert distance_to_destroyed_model(
            state=state,
            event_records=decisions.event_log.records,
            source_model_instance_id=source.own_model_ids()[0],
            destroyed_model_instance_id=mid,
        ) == pytest.approx(expected[mid], abs=1e-9)  # pyright: ignore[reportUnknownMemberType]
        assert not model_is_present_on_battlefield(state=state, model_instance_id=mid)
        footprint = former_footprint_for_destroyed_model(
            state=state,
            event_records=decisions.event_log.records,
            model_instance_id=mid,
        )
        assert footprint.geometry == geometry_model_for_placement(
            model=model, placement=bf.model_placement_by_id(mid)
        )
        if i + 1 < len(target.own_models):
            with pytest.raises(GameLifecycleError, match="destroyed rules unit"):
                former_footprint_for_destroyed_unit(
                    state=state,
                    event_records=decisions.event_log.records,
                    unit_instance_id=target.unit_instance_id,
                )
    footprint = former_footprint_for_destroyed_unit(
        state=state,
        event_records=decisions.event_log.records,
        unit_instance_id=target.unit_instance_id,
    )
    assert footprint.model_instance_id == target.own_model_ids()[-1]
    assert distance_to_destroyed_unit(
        state=state,
        event_records=decisions.event_log.records,
        source_model_instance_id=source.own_model_ids()[0],
        destroyed_unit_instance_id=target.unit_instance_id,
    ) == pytest.approx(expected[target.own_model_ids()[-1]])  # pyright: ignore[reportUnknownMemberType]
    if len(target.own_models) > 1:
        assert expected[target.own_model_ids()[0]] != expected[target.own_model_ids()[-1]]
    # The query cannot fabricate an authenticated footprint from missing death evidence.
    with pytest.raises(GameLifecycleError):
        former_footprint_for_destroyed_model(
            state=state, event_records=(), model_instance_id=target.own_model_ids()[0]
        )
