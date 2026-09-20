"""Canonical loaded-Transport declarations submitted through the adapter facade."""

from __future__ import annotations

from tests.phase13b_shooting_declaration_helpers import (
    _decision_request,
    _proposal_from_request,
    _shooting_lifecycle,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.phase import LifecycleStatus
from warhammer40k_core.engine.weapon_declaration import ShootingDeclarationProposal

PASSENGERS = ("army-alpha:passenger-1", "army-alpha:passenger-2")
TRANSPORT = "army-alpha:transport-1"


def firing_deck_session(
    *,
    contribute: bool = True,
    attached: bool = False,
) -> tuple[LocalGameSession, DecisionRequest, ShootingDeclarationProposal]:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("passenger-1", "passenger-2", "transport-1"),
        alpha_datasheets={
            "passenger-1": ("core-intercessor-like-infantry", "core-intercessor-like", 5),
            "passenger-2": (
                ("core-character-leader", "core-character-leader", 1)
                if attached
                else ("core-intercessor-like-infantry", "core-intercessor-like", 5)
            ),
            "transport-1": ("core-transport", "core-transport", 1),
        },
        embarked_unit_ids=("passenger-1", "passenger-2"),
        alpha_attachment_declarations=(
            (
                AttachmentDeclaration(
                    source_unit_selection_id="passenger-2",
                    bodyguard_unit_selection_id="passenger-1",
                ),
            )
            if attached
            else ()
        ),
    )
    session = LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload()))
    selection = _decision_request(session.advance_until_decision_or_terminal())
    kind = _decision_request(
        session.submit_option(
            request_id=selection.request_id,
            option_id=TRANSPORT,
            result_id="order65-transport",
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


def submit_firing_deck(
    session: LocalGameSession,
    request: DecisionRequest,
    proposal: ShootingDeclarationProposal,
) -> LifecycleStatus:
    return session.submit_parameterized_payload(
        request_id=request.request_id,
        payload=validate_json_value(proposal.to_payload()),
        result_id="order65-declaration",
    )
