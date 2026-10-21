"""15.04/FAQ50 use actual Command-step discovery and native health/shock owners."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section08_contracts import command_session
from tests.support.section08_fixtures import command_state, damage_to_count, mark_shocked
from tests.support.section09_fixtures import attach_mission
from tests.support.section15_fixtures import events, request, submit
from warhammer40k_core.engine.phase import LifecycleStatusKind


def test_native_command_discovery_spends_before_auto_passing_the_required_test(
    section15_definitions: Section02Definitions,
) -> None:
    state = command_state(section15_definitions)
    damage_to_count(state, 4)
    attach_mission(state)
    session = command_session(section15_definitions, state)
    req = request(session.advance_until_decision_or_terminal())
    assert req.decision_type == "submit_stratagem_target_proposal"
    own = state.army_definition_for_player("owner")
    assert own is not None
    unit = own.units[0]
    status = submit(session, req, unit.unit_instance_id)
    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert state.command_point_total("owner") == 0
    use = state.stratagem_use_records[-1]
    assert use.stratagem_id == "insane-bravery"
    assert use.targeted_unit_instance_ids == (unit.unit_instance_id,)
    resolved = events(session, "battle_shock_test_resolved")
    assert len(resolved) == 1
    assert resolved[0]["auto_passed"] is True
    assert unit.unit_instance_id not in state.battle_shocked_unit_ids


@pytest.mark.parametrize("drift", [False, True])
def test_faq50_already_shocked_target_is_not_offered_and_live_drift_is_atomic(
    section15_definitions: Section02Definitions, drift: bool
) -> None:
    from copy import deepcopy

    from tests.support.section15_fixtures import context
    from warhammer40k_core.engine.stratagem_catalog import eleventh_edition_core_stratagem_index
    from warhammer40k_core.engine.stratagems import stratagem_target_proposal_from_index
    from warhammer40k_core.engine.timing_windows import TimingTriggerKind

    state = command_state(section15_definitions)
    damage_to_count(state, 4)
    session = command_session(section15_definitions, state)
    session.lifecycle._require_runtime_content_bundle()  # pyright: ignore[reportPrivateUsage]
    req = None
    if drift:
        req = request(session.advance_until_decision_or_terminal())
    unit = mark_shocked(state)
    if drift:
        assert req is not None
        before = deepcopy(session.lifecycle.to_payload())
        status = submit(session, req, unit)
        assert status.status_kind is LifecycleStatusKind.INVALID
        assert session.lifecycle.to_payload() == before
        assert session.lifecycle.decision_controller.queue.pending_requests == (req,)
    else:
        proposal = stratagem_target_proposal_from_index(
            state=state,
            index=eleventh_edition_core_stratagem_index(),
            context=context(state, TimingTriggerKind.START_PHASE),
            handler_id="core:insane-bravery",
            require_legal_affordable_target=True,
        )
        assert proposal is None
    assert state.stratagem_use_records == []
    assert unit in state.battle_shocked_unit_ids
