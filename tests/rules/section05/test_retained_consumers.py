"""Retained native models remain visible, measurable and constrain consolidation."""

import pytest

from tests.support.section02_fixtures import LORD_EXULTANT, Section02Definitions
from tests.support.section05_retention import retain, terminal_retention
from warhammer40k_core.core.ruleset_descriptor import ConsolidationModeKind
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.damage_allocation import unit_by_id
from warhammer40k_core.engine.destroyed_referent_measurement import (
    distance_to_destroyed_model,
)
from warhammer40k_core.engine.fight_resolution import legal_consolidation_modes
from warhammer40k_core.engine.physical_engagement import (
    current_physically_engaged_enemy_rules_unit_ids,
)
from warhammer40k_core.engine.retained_destruction_cleanup import (
    begin_retained_destruction_cleanup,
)
from warhammer40k_core.engine.shooting_targets import (
    shooting_target_candidate_for_model,
)


@pytest.mark.parametrize(
    ("distance", "engaged", "mode"),
    [
        (4.0, False, ConsolidationModeKind.ENGAGING),
        (2.0, True, ConsolidationModeKind.ONGOING),
    ],
)
def test_faq49_retained_native_geometry_and_enemy_consolidation(
    section05_definitions: Section02Definitions,
    distance: float,
    engaged: bool,
    mode: ConsolidationModeKind,
) -> None:
    state, target, decisions, request = terminal_retention(section05_definitions, distance=distance)
    retain(state, decisions, request)
    source = unit_by_id(state=state, unit_instance_id="section02:subject")
    mid = target.own_model_ids()[0]
    candidate = shooting_target_candidate_for_model(
        scenario=battlefield_scenario_for_state(state=state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attacker_unit=source,
        attacker_model_instance_id=source.own_model_ids()[0],
        weapon_profile=section05_definitions.weapon(f"{LORD_EXULTANT}:bolt-pistol"),
        target_unit_id=target.unit_instance_id,
    )
    assert mid in candidate.target_visible_model_ids
    assert mid in candidate.target_in_range_model_ids
    measured = distance_to_destroyed_model(
        state=state,
        event_records=decisions.event_log.records,
        source_model_instance_id=source.own_model_ids()[0],
        destroyed_model_instance_id=mid,
    )
    assert measured > 0
    assert measured < distance
    assert (
        bool(
            current_physically_engaged_enemy_rules_unit_ids(
                state=state, unit_instance_id=source.unit_instance_id
            )
        )
        is engaged
    )
    modes = legal_consolidation_modes(
        scenario=battlefield_scenario_for_state(state=state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_instance_id=source.unit_instance_id,
        objective_markers=(),
        state=state,
    )
    assert modes == (mode,)
    begin_retained_destruction_cleanup(state=state, decisions=decisions, reason="phase_end")
    assert (
        current_physically_engaged_enemy_rules_unit_ids(
            state=state, unit_instance_id=source.unit_instance_id
        )
        == ()
    )
    assert (
        legal_consolidation_modes(
            scenario=battlefield_scenario_for_state(state=state),
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            unit_instance_id=source.unit_instance_id,
            objective_markers=(),
            state=state,
        )
        == ()
    )
