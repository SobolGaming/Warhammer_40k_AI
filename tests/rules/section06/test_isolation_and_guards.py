"""Source, decision, placement and mutable-case isolation controls for Section06."""

import pytest

from tests.support.section02_fixtures import LORD_EXULTANT, Section02Definitions
from tests.support.section04_fixtures import combat_state
from tests.support.section06_fixtures import mortal_progress
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.direct_mortal_wound_application import (
    apply_direct_mortal_wounds_to_unit,
)
from warhammer40k_core.engine.mortal_wound_model_allocation import continue_mortal_wound_application
from warhammer40k_core.engine.phase import GameLifecycleError


def test_case_state_isolation_after_real_mortal_mutation(
    section06_definitions: Section02Definitions,
) -> None:
    d = section06_definitions
    unit, twin = d.unit(LORD_EXULTANT), d.unit(LORD_EXULTANT)
    state, other = combat_state(d, unit), combat_state(d, twin)
    before = other.to_payload()
    decisions = DecisionController()
    applied = continue_mortal_wound_application(
        state=state,
        decisions=decisions,
        request_id="s06:isolation",
        progress=mortal_progress(state, unit.unit_instance_id, 1),
    )
    assert applied.application is not None
    assert len(applied.application.applications) == 1
    assert other.to_payload() == before
    assert unit.own_models[0] is not twin.own_models[0]
    assert state.army_definitions is not other.army_definitions
    assert state.persisting_effects is not other.persisting_effects
    assert state.battlefield_state is not other.battlefield_state
    assert DecisionController().event_log.records == ()


def test_wrong_defender_rejected_before_mortal_mutation(
    section06_definitions: Section02Definitions,
) -> None:
    d = section06_definitions
    target = d.unit(LORD_EXULTANT)
    state = combat_state(d, target)
    progress = mortal_progress(state, target.unit_instance_id, 1)
    assert progress.destruction_evidence is not None
    before = state.to_payload()
    decisions = DecisionController()
    with pytest.raises(GameLifecycleError, match="defender player drift"):
        apply_direct_mortal_wounds_to_unit(
            state=state,
            decisions=decisions,
            application_id=progress.application_id,
            source_rule_id=progress.source_rule_id,
            source_context=progress.source_context,
            destruction_evidence=progress.destruction_evidence,
            target_unit_instance_id=target.unit_instance_id,
            mortal_wounds=1,
            defender_player_id="opponent",
        )
    assert state.to_payload() == before
    assert decisions.event_log.records == ()


def test_illegal_mortal_choice_preserves_pending_and_state(
    section06_definitions: Section02Definitions,
) -> None:
    d = section06_definitions
    target = d.unit()
    state = combat_state(d, target)
    decisions = DecisionController()
    routed = continue_mortal_wound_application(
        state=state,
        decisions=decisions,
        request_id="s06:guard",
        progress=mortal_progress(state, target.unit_instance_id, 1),
    )
    request = routed.request
    assert request is not None
    decisions.request_decision(request)
    before = state.to_payload()
    pending = decisions.to_payload()
    with pytest.raises(DecisionError, match="finite action space"):
        decisions.submit_result(
            DecisionResult.for_request(
                result_id="s06:bad", request=request, selected_option_id="absent-model"
            )
        )
    assert state.to_payload() == before
    assert decisions.to_payload() == pending
