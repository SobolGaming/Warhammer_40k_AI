"""Declared D07 fixture IDs through the ordinary facade, with no RNG intervention."""

from tests.phase13b_shooting_declaration_helpers import _proposal_from_request
from tests.psychic_modifier_helpers import submit_fixture_request
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import LifecycleStatusKind


def submit_fixed_fixture_request(
    session: LocalGameSession, request: DecisionRequest, *, result_id: str | None
) -> None:
    if result_id is None:
        submit_fixture_request(session, request)
        return
    if request.decision_type == "submit_shooting_declaration":
        proposal = _proposal_from_request(request=request, target_unit_id="army-beta:enemy")
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=result_id,
            payload=validate_json_value(proposal.to_payload()),
        )
    else:
        assert not request.is_parameterized_submission_request()
        assert request.options, request.decision_type
        status = session.submit_option(
            request_id=request.request_id,
            result_id=result_id,
            option_id=request.options[0].option_id,
        )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
