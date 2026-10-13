"""Internal gathering authority remains persisted and absent from every public role surface."""

from tests.s25_gathering_helpers import native_two_bearer_inputs

from warhammer40k_core.adapters.access_control import AuthenticatedPrincipal, PrincipalRole
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.engine.event_log import canonical_json, validate_json_value


def test_native_gathering_proofs_are_internal_on_all_role_views_and_event_deltas() -> None:
    session, _, _ = native_two_bearer_inputs()
    persisted = canonical_json(validate_json_value(session.to_persistence_payload()))
    assert '"native_snapshots"' in persisted
    assert '"source_proof_json"' in persisted
    for role in PrincipalRole:
        players = (
            ("player-a", "player-b")
            if role in {PrincipalRole.PLAYER, PrincipalRole.COACH}
            else (None,)
        )
        for player in players:
            viewer = AuthenticatedPrincipal(
                principal_id=f"s25:{role.value}:{player}", role=role, player_id=player
            ).bind_to_session(player_ids=("player-a", "player-b"))
            view = canonical_json(validate_json_value(session.view_for_context(viewer=viewer)))
            events = canonical_json(
                validate_json_value(
                    session.events_since_for_context(EventStreamCursor(), viewer=viewer)
                )
            )
            for public in (view, events):
                assert '"native_snapshots"' not in public
                assert '"source_proof_json"' not in public
                assert '"rules_json"' not in public
    # The redactor operates on projections/copies, never authoritative history.
    assert canonical_json(validate_json_value(session.to_persistence_payload())) == persisted
