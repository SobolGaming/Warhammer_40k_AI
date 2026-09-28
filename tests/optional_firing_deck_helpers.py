"""Loaded Firing Deck with another eligible shooter to keep restriction checks in phase."""

from tests.firing_deck_helpers import TRANSPORT
from tests.phase13b_shooting_declaration_helpers import (
    _decision_request,
    _proposal_from_request,
    _shooting_lifecycle,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.weapon_declaration import ShootingDeclarationProposal


def optional_firing_deck_session(
    *, contribute: bool
) -> tuple[LocalGameSession, DecisionRequest, ShootingDeclarationProposal]:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("passenger-1", "passenger-2", "transport-1", "spare"),
        alpha_datasheets={
            **dict.fromkeys(
                ("passenger-1", "passenger-2", "spare"),
                ("core-intercessor-like-infantry", "core-intercessor-like", 5),
            ),
            "transport-1": ("core-transport", "core-transport", 1),
        },
        embarked_unit_ids=("passenger-1", "passenger-2"),
    )
    session = LocalGameSession(GameLifecycle.from_payload(lifecycle.to_payload()))
    selection = _decision_request(session.advance_until_decision_or_terminal())
    kind = _decision_request(
        session.submit_option(
            request_id=selection.request_id, option_id=TRANSPORT, result_id="order65-transport"
        )
    )
    declaration = _decision_request(
        session.submit_option(
            request_id=kind.request_id,
            option_id=kind.options[0].option_id,
            result_id="order65-type",
        )
    )
    proposal = _proposal_from_request(
        request=declaration,
        target_unit_id=units["enemy"].unit_instance_id,
        firing_deck_unit=units["passenger-1"] if contribute else None,
    )
    return session, declaration, proposal
