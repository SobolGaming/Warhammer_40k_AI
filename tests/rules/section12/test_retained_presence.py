"""FAQ49 physical engagement at Fight after actual lethal melee and accepted retention."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section05_retention import retain, terminal_retention
from tests.support.section12_fixtures import (
    begin,
    checkpoint,
    events,
    paths,
    session_for,
    submit_move,
)
from tests.support.section12_retention import public_retained_scene
from warhammer40k_core.core.ruleset_descriptor import FightEligibilityKind, FightPhaseStepKind
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.fight_order import (
    fight_eligibility_reasons_for_unit,
    unit_is_currently_engaged,
)
from warhammer40k_core.engine.fight_resolution import legal_consolidation_modes
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.physical_engagement import (
    current_physically_engaged_enemy_rules_unit_ids,
)
from warhammer40k_core.engine.retained_destruction_cleanup import begin_retained_destruction_cleanup
from warhammer40k_core.engine.retained_model_presence import model_is_present_on_battlefield


def test_retained_enemy_still_engages_both_sides_and_constrains_fight_movement_until_cleanup(
    section12_definitions: Section02Definitions,
) -> None:
    # This shared native kernel starts engaged (centre distance2.5), executes a
    # real lethal melee attack, then accepts an explicit generic FOD permission.
    s, target, decisions, request = terminal_retention(
        section12_definitions, distance=2.5, melee=True
    )
    source = "section02:subject"
    assert not unit_is_currently_engaged(state=s, unit_instance_id=source)
    retain(s, decisions, request)
    assert unit_is_currently_engaged(state=s, unit_instance_id=source)
    assert unit_is_currently_engaged(state=s, unit_instance_id=target.unit_instance_id)
    assert current_physically_engaged_enemy_rules_unit_ids(state=s, unit_instance_id=source) == (
        target.unit_instance_id,
    )
    assert current_physically_engaged_enemy_rules_unit_ids(
        state=s, unit_instance_id=target.unit_instance_id
    ) == (source,)
    assert s.fight_phase_state is not None
    reasons = fight_eligibility_reasons_for_unit(
        state=s,
        fight_state=s.fight_phase_state,
        unit_instance_id=target.unit_instance_id,
        policy=s.runtime_ruleset_descriptor().fight_policy,
    )
    assert FightEligibilityKind.CURRENTLY_ENGAGED in reasons
    assert model_is_present_on_battlefield(state=s, model_instance_id=target.own_model_ids()[0])
    modes = legal_consolidation_modes(
        scenario=battlefield_scenario_for_state(state=s),
        ruleset_descriptor=s.runtime_ruleset_descriptor(),
        unit_instance_id=source,
        objective_markers=(),
        state=s,
    )
    assert [m.value for m in modes] == ["ongoing"]
    assert (
        begin_retained_destruction_cleanup(state=s, decisions=decisions, reason="phase_end") is None
    )
    assert not current_physically_engaged_enemy_rules_unit_ids(state=s, unit_instance_id=source)
    assert not model_is_present_on_battlefield(state=s, model_instance_id=target.own_model_ids()[0])


@pytest.mark.parametrize("retained", [True, False])
def test_retained_enemy_controls_public_pile_in_rejection_and_legal_retry(
    section12_definitions: Section02Definitions,
    retained: bool,
) -> None:
    s, target, living, decisions = public_retained_scene(section12_definitions)
    if not retained:
        assert (
            begin_retained_destruction_cleanup(state=s, decisions=decisions, reason="phase_end")
            is None
        )
    checkpoint(s, FightPhaseStepKind.PILE_IN)
    session = session_for(section12_definitions, s, decisions=decisions)
    r = begin(session)
    assert r.decision_type == "submit_movement_proposal"
    m = MovementProposalRequest.from_decision_request_payload(r.payload)
    assert m.unit_instance_id == "section02:subject"
    before = s.battlefield_state
    targets = (
        (target.unit_instance_id, living.unit_instance_id)
        if retained
        else (living.unit_instance_id,)
    )
    # Within3 inches and closer to the living enemy, but breaks the retained
    # enemy's engagement. The post-cleanup control accepts the identical path.
    status = submit_move(
        session, targets=targets, witness=paths(s, (m.unit_instance_id,), -1.1, 1.8)
    )
    if retained:
        assert status.status_kind is LifecycleStatusKind.INVALID, status.to_payload()
        assert s.battlefield_state == before
        assert not events(session, "fight_movement_completed")
        assert model_is_present_on_battlefield(state=s, model_instance_id=target.own_model_ids()[0])
        status = submit_move(
            session,
            targets=targets,
            witness=paths(s, (m.unit_instance_id,), 0.25, 0.25),
            identity="legal-retry",
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
        assert model_is_present_on_battlefield(state=s, model_instance_id=target.own_model_ids()[0])
    else:
        assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    assert len(events(session, "fight_movement_completed")) == 1
    assert unit_is_currently_engaged(state=s, unit_instance_id=m.unit_instance_id)
