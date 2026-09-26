from __future__ import annotations

from math import isclose

import pytest
from tests.order57_destroyed_referent_helpers import (
    destroy_and_remove_order57_model,
    order57_alpha_models,
    order57_alpha_unit,
    order57_battle_state,
    order57_beta_models,
    order57_beta_unit,
    ordinary_order57_distance,
    record_order57_logical_death,
    replace_order57_model_geometry,
    set_order57_model_wounds,
)

from warhammer40k_core.engine.battlefield_state import (
    ModelPlacement,
    PlacementError,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.damage_allocation import model_by_id
from warhammer40k_core.engine.deadly_demise import deadly_demise_target_unit_ids
from warhammer40k_core.engine.destroyed_referent_measurement import (
    MEASURING_TO_DESTROYED_SOURCE_ID,
    distance_to_destroyed_model,
    distance_to_destroyed_unit,
    former_footprint_for_destroyed_model,
    former_footprint_for_destroyed_unit,
)
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.retained_model_presence import model_is_present_on_battlefield
from warhammer40k_core.geometry.measurement import DistanceMeasurementContext
from warhammer40k_core.geometry.model_geometry import (
    BaseFootprintKind,
    FootprintPart,
    GeometrySourceKind,
    HeightSourceKind,
    ModelGeometry,
)
from warhammer40k_core.geometry.pose import Pose


def test_destroyed_model_measurement_uses_authenticated_former_footprint() -> None:
    state, event_log = order57_battle_state()
    source = order57_alpha_models(state)[0]
    target = order57_beta_models(state)[0]
    expected = ordinary_order57_distance(state=state, source=source, target=target)
    destroy_and_remove_order57_model(
        state=state, event_log=event_log, model=target, cause_id="cause-one"
    )

    footprint = former_footprint_for_destroyed_model(
        state=state,
        event_records=event_log.records,
        model_instance_id=target.model_instance_id,
    )
    measured = distance_to_destroyed_model(
        state=state,
        event_records=event_log.records,
        source_model_instance_id=source.model_instance_id,
        destroyed_model_instance_id=target.model_instance_id,
    )

    assert footprint.source_rule_id == MEASURING_TO_DESTROYED_SOURCE_ID
    assert isclose(measured, expected, abs_tol=1e-9)
    assert state.battlefield_state is not None
    assert target.model_instance_id not in state.battlefield_state.placed_model_ids()
    assert not model_is_present_on_battlefield(
        state=state, model_instance_id=target.model_instance_id
    )
    with pytest.raises(PlacementError):
        state.battlefield_state.model_placement_by_id(target.model_instance_id)


def test_destroyed_unit_measurement_uses_last_destroyed_model() -> None:
    state, event_log = order57_battle_state()
    source = order57_alpha_models(state)[0]
    first, *_, last = order57_beta_models(state)
    unit = order57_beta_unit(state)
    first_distance = ordinary_order57_distance(state=state, source=source, target=first)
    last_distance = ordinary_order57_distance(state=state, source=source, target=last)
    assert not isclose(first_distance, last_distance, abs_tol=1e-9)
    destroy_and_remove_order57_model(
        state=state, event_log=event_log, model=first, cause_id="cause-first"
    )
    for index, model in enumerate(order57_beta_models(state)[1:-1], start=2):
        destroy_and_remove_order57_model(
            state=state,
            event_log=event_log,
            model=model,
            cause_id=f"cause-middle-{index}",
        )
    destroy_and_remove_order57_model(
        state=state, event_log=event_log, model=last, cause_id="cause-last"
    )

    footprint = former_footprint_for_destroyed_unit(
        state=state,
        event_records=event_log.records,
        unit_instance_id=unit.unit_instance_id,
    )
    measured = distance_to_destroyed_unit(
        state=state,
        event_records=event_log.records,
        source_model_instance_id=source.model_instance_id,
        destroyed_unit_instance_id=unit.unit_instance_id,
    )

    assert footprint.model_instance_id == last.model_instance_id
    assert isclose(measured, last_distance, abs_tol=1e-9)
    assert not isclose(measured, first_distance, abs_tol=1e-9)


def test_destroyed_model_measurement_uses_catalog_hull_not_a_center_point() -> None:
    state, event_log = order57_battle_state()
    source = order57_alpha_models(state)[0]
    target = order57_beta_models(state)[0]
    circular_distance = ordinary_order57_distance(state=state, source=source, target=target)
    hull = ModelGeometry(
        footprint_kind=BaseFootprintKind.HULL,
        parts=(
            FootprintPart(
                part_id="hull",
                footprint_kind=BaseFootprintKind.HULL,
                radius_x_inches=8.0,
                radius_y_inches=2.0,
            ),
        ),
        height_inches=3.0,
        geometry_source_kind=GeometrySourceKind.MANUAL_OVERRIDE,
        geometry_source_id=None,
        height_source_kind=HeightSourceKind.MANUAL_OVERRIDE,
        height_source_id=None,
    )
    replace_order57_model_geometry(
        state=state, model_instance_id=target.model_instance_id, geometry=hull
    )
    hull_model = model_by_id(state=state, model_instance_id=target.model_instance_id)
    hull_distance = ordinary_order57_distance(state=state, source=source, target=hull_model)
    assert not isclose(circular_distance, hull_distance, abs_tol=1e-9)
    destroy_and_remove_order57_model(
        state=state,
        event_log=event_log,
        model=hull_model,
        cause_id="cause-hull",
    )

    measured = distance_to_destroyed_model(
        state=state,
        event_records=event_log.records,
        source_model_instance_id=source.model_instance_id,
        destroyed_model_instance_id=target.model_instance_id,
    )
    footprint = former_footprint_for_destroyed_model(
        state=state,
        event_records=event_log.records,
        model_instance_id=target.model_instance_id,
    )

    assert footprint.geometry.base.to_payload() == hull.base_shape().to_payload()
    assert isclose(measured, hull_distance, abs_tol=1e-9)


def test_destroyed_referent_measurement_fail_closed_paths() -> None:
    state, event_log = order57_battle_state()
    source = order57_alpha_models(state)[0]
    living = order57_beta_models(state)[0]
    with pytest.raises(GameLifecycleError, match="requires a destroyed model"):
        former_footprint_for_destroyed_model(
            state=state,
            event_records=event_log.records,
            model_instance_id=living.model_instance_id,
        )
    with pytest.raises(GameLifecycleError, match="requires a destroyed rules unit"):
        former_footprint_for_destroyed_unit(
            state=state,
            event_records=event_log.records,
            unit_instance_id=order57_beta_unit(state).unit_instance_id,
        )
    with pytest.raises(GameLifecycleError, match="unknown"):
        former_footprint_for_destroyed_model(
            state=state,
            event_records=event_log.records,
            model_instance_id="forged-model",
        )
    set_order57_model_wounds(state, model_instance_id=living.model_instance_id, wounds_remaining=0)
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.with_removed_models(
        (living.model_instance_id,)
    )
    with pytest.raises(GameLifecycleError, match="missing authenticated former placement"):
        former_footprint_for_destroyed_model(
            state=state,
            event_records=event_log.records,
            model_instance_id=living.model_instance_id,
        )
    with pytest.raises(GameLifecycleError, match="source model must remain placed"):
        distance_to_destroyed_model(
            state=state,
            event_records=event_log.records,
            source_model_instance_id=living.model_instance_id,
            destroyed_model_instance_id=source.model_instance_id,
        )


def test_retained_destroyed_model_former_footprint_matches_current_placement() -> None:
    state, event_log = order57_battle_state()
    source = order57_alpha_models(state)[0]
    target = order57_beta_models(state)[0]
    expected = ordinary_order57_distance(state=state, source=source, target=target)
    record_order57_logical_death(
        state=state,
        event_log=event_log,
        model=target,
        cause_id="cause-retained",
        placement_retained=True,
        wounds_remaining=0,
        remove=False,
    )
    measured = distance_to_destroyed_model(
        state=state,
        event_records=event_log.records,
        source_model_instance_id=source.model_instance_id,
        destroyed_model_instance_id=target.model_instance_id,
    )
    assert isclose(measured, expected, abs_tol=1e-9)
    assert state.battlefield_state is not None
    assert target.model_instance_id in state.battlefield_state.placed_model_ids()


def test_deadly_demise_can_measure_from_removed_destroyed_model() -> None:
    state, event_log = order57_battle_state()
    exploding = order57_beta_models(state)[0]
    own_unit_id = order57_beta_unit(state).unit_instance_id
    enemy_unit_id = order57_alpha_unit(state).unit_instance_id
    destroy_and_remove_order57_model(
        state=state,
        event_log=event_log,
        model=exploding,
        cause_id="cause-demise",
    )
    target_ids = deadly_demise_target_unit_ids(
        state=state,
        source_model_instance_id=exploding.model_instance_id,
        range_inches=6.0,
        event_records=event_log.records,
    )
    assert own_unit_id in target_ids
    assert enemy_unit_id not in target_ids


def test_destroyed_referent_measurement_survives_state_and_event_restore() -> None:
    state, event_log = order57_battle_state()
    source = order57_alpha_models(state)[0]
    target = order57_beta_models(state)[0]
    destroy_and_remove_order57_model(
        state=state, event_log=event_log, model=target, cause_id="cause-save"
    )
    measured = distance_to_destroyed_model(
        state=state,
        event_records=event_log.records,
        source_model_instance_id=source.model_instance_id,
        destroyed_model_instance_id=target.model_instance_id,
    )
    restored_state = GameState.from_payload(state.to_payload())
    restored_records = tuple(
        EventRecord.from_payload(event.to_payload()) for event in event_log.records
    )
    restored = distance_to_destroyed_model(
        state=restored_state,
        event_records=restored_records,
        source_model_instance_id=source.model_instance_id,
        destroyed_model_instance_id=target.model_instance_id,
    )
    assert isclose(restored, measured, abs_tol=1e-9)
    assert restored_state.battlefield_state is not None
    context = DistanceMeasurementContext.from_models(
        geometry_model_for_placement(
            model=model_by_id(state=restored_state, model_instance_id=source.model_instance_id),
            placement=restored_state.battlefield_state.model_placement_by_id(
                source.model_instance_id
            ),
        ),
        former_footprint_for_destroyed_model(
            state=restored_state,
            event_records=restored_records,
            model_instance_id=target.model_instance_id,
        ).geometry,
    )
    assert (
        context.to_payload()
        == DistanceMeasurementContext.from_payload(context.to_payload()).to_payload()
    )


def test_destroyed_referent_uses_latest_occurrence_after_return() -> None:
    state, event_log = order57_battle_state()
    source = order57_alpha_models(state)[0]
    target = order57_beta_models(state)[0]
    own_unit = order57_beta_unit(state)
    enemy_unit_id = order57_alpha_unit(state).unit_instance_id
    first_distance = ordinary_order57_distance(state=state, source=source, target=target)
    starting_wounds = target.current_wounds
    assert state.battlefield_state is not None
    first_placement = state.battlefield_state.model_placement_by_id(target.model_instance_id)
    returned_placement = first_placement.with_pose(
        Pose.at(
            x=20.0,
            y=first_placement.pose.position.y,
            z=first_placement.pose.position.z,
            facing_degrees=first_placement.pose.facing.degrees,
        )
    )
    destroy_and_remove_order57_model(
        state=state, event_log=event_log, model=target, cause_id="cause-first-life"
    )
    _return_order57_model(
        state=state,
        model_instance_id=target.model_instance_id,
        placement=returned_placement,
        wounds_remaining=starting_wounds,
    )
    returned = model_by_id(state=state, model_instance_id=target.model_instance_id)
    latest_distance = ordinary_order57_distance(state=state, source=source, target=returned)
    assert not isclose(first_distance, latest_distance, abs_tol=1e-9)
    for index, model in enumerate(order57_beta_models(state)[1:], start=2):
        destroy_and_remove_order57_model(
            state=state,
            event_log=event_log,
            model=model,
            cause_id=f"cause-squad-{index}",
        )
    destroy_and_remove_order57_model(
        state=state, event_log=event_log, model=returned, cause_id="cause-second-life"
    )

    footprint = former_footprint_for_destroyed_model(
        state=state,
        event_records=event_log.records,
        model_instance_id=target.model_instance_id,
    )
    measured = distance_to_destroyed_model(
        state=state,
        event_records=event_log.records,
        source_model_instance_id=source.model_instance_id,
        destroyed_model_instance_id=target.model_instance_id,
    )
    target_ids = deadly_demise_target_unit_ids(
        state=state,
        source_model_instance_id=target.model_instance_id,
        range_inches=6.0,
        event_records=event_log.records,
    )
    unit_footprint = former_footprint_for_destroyed_unit(
        state=state,
        event_records=event_log.records,
        unit_instance_id=own_unit.unit_instance_id,
    )
    unit_measured = distance_to_destroyed_unit(
        state=state,
        event_records=event_log.records,
        source_model_instance_id=source.model_instance_id,
        destroyed_unit_instance_id=own_unit.unit_instance_id,
    )

    assert footprint.logical_death.cause_id == "cause-second-life"
    assert footprint.logical_death.boundary_id != ""
    assert footprint.geometry.pose.to_payload() == returned_placement.pose.to_payload()
    assert isclose(measured, latest_distance, abs_tol=1e-9)
    assert not isclose(measured, first_distance, abs_tol=1e-9)
    assert enemy_unit_id in target_ids
    assert own_unit.unit_instance_id not in target_ids
    assert unit_footprint.model_instance_id == target.model_instance_id
    assert unit_footprint.logical_death.cause_id == "cause-second-life"
    assert isclose(unit_measured, latest_distance, abs_tol=1e-9)


def test_destroyed_referent_measurement_rejects_duplicate_cause_or_boundary() -> None:
    state, event_log = order57_battle_state()
    target = order57_beta_models(state)[0]
    destroy_and_remove_order57_model(
        state=state, event_log=event_log, model=target, cause_id="cause-duplicate"
    )
    duplicated = (*event_log.records, event_log.records[-1])
    with pytest.raises(GameLifecycleError, match="duplicate logical-death records"):
        former_footprint_for_destroyed_model(
            state=state,
            event_records=duplicated,
            model_instance_id=target.model_instance_id,
        )
    for index, model in enumerate(order57_beta_models(state)[1:], start=2):
        destroy_and_remove_order57_model(
            state=state,
            event_log=event_log,
            model=model,
            cause_id=f"cause-duplicate-squad-{index}",
        )
    duplicated_unit = (*event_log.records, event_log.records[-1])
    with pytest.raises(GameLifecycleError, match="duplicate logical-death records"):
        former_footprint_for_destroyed_unit(
            state=state,
            event_records=duplicated_unit,
            unit_instance_id=order57_beta_unit(state).unit_instance_id,
        )


def _return_order57_model(
    *,
    state: GameState,
    model_instance_id: str,
    placement: ModelPlacement,
    wounds_remaining: int,
) -> None:
    set_order57_model_wounds(
        state,
        model_instance_id=model_instance_id,
        wounds_remaining=wounds_remaining,
    )
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.with_returned_model_placement(placement)
