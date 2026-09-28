"""Bounded facade counterexamples, not assertions that defects are correct rules.

Uses canonical fixtures and the public decision path. No runtime objects or
controllers are patched. Run with ``python -m tools.core_rules_order95_probes``.
"""

from __future__ import annotations

import json
from typing import Any, cast

from tests.absent_strength_helpers import strength_session
from tests.empty_shooting_helpers import SHOOTER, empty_shooting_session
from tests.lethal_hits_helpers import attack_steps, complete_attack
from tests.phase13b_shooting_declaration_helpers import _proposal_from_request

from tools.core_rules_order84_capture import fingerprint
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner


def decline_all_targets() -> dict[str, Any]:
    session = empty_shooting_session(reachable=True, spare=True)
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    request = session.submit_option(
        request_id=request.request_id, option_id=SHOOTER, result_id="order95:unit"
    ).decision_request
    assert request is not None
    request = session.submit_option(
        request_id=request.request_id, option_id="normal", result_id="order95:type"
    ).decision_request
    assert request is not None
    proposal = _proposal_from_request(request=request, target_unit_id="army-beta:enemy")
    payload = proposal.to_payload()
    payload["declarations"] = []
    before = session.lifecycle.to_payload()
    rejected = session.submit_parameterized_payload(
        request_id=request.request_id, payload=payload, result_id="order95:decline-all"
    )
    unchanged = before == session.lifecycle.to_payload()
    # The same live request accepts its legal, nonempty control declaration.
    control = session.submit_parameterized_payload(
        request_id=request.request_id,
        payload=proposal.to_payload(),
        result_id="order95:legal-target-control",
    )
    return {
        "decision_type": request.decision_type,
        "options": [option.option_id for option in request.options],
        "decline_status": rejected.status_kind.value,
        "decline_diagnostic": rejected.payload,
        "rejection_preserves_authoritative_state": unchanged,
        "nonempty_control_status": control.status_kind.value,
        "scope": "ordinary_shooting_facade; retained_host_is_consumer_trace_only",
    }


def twin_linked(phase: BattlePhase) -> dict[str, Any]:
    session = strength_session(phase)
    session.advance_until_decision_or_terminal()
    initial = session.lifecycle.to_payload()
    complete_attack(session)
    controller = session.lifecycle.decision_controller
    rerolls = [
        event
        for event in controller.event_log.records
        if event.event_type == "weapon_ability_reroll_resolved"
    ]
    recorded_request_ids = {record.request.request_id for record in controller.records}
    unsubmitted = [
        event
        for event in rerolls
        if cast(dict[str, Any], event.payload)["reroll_request"]["request_id"]
        not in recorded_request_ids
    ]
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    replay = ReplayRunner.from_payload(
        ReplayArtifact.capture(
            artifact_id=f"order95-twin-linked-{phase.value}",
            initial_lifecycle_payload=initial,
            final_lifecycle=session.lifecycle,
        ).to_payload()
    ).run()
    return {
        "phase": phase.value,
        "wound_count": len(attack_steps(session, "wound")),
        "automatic_reroll_count": len(rerolls),
        "rerolls_without_submitted_decision": len(unsubmitted),
        "submitted_decision_types": [record.request.decision_type for record in controller.records],
        "reroll_events_sha256": fingerprint([event.to_payload() for event in rerolls]),
        "exact_restore": restored.to_persistence_payload() == checkpoint,
        "both_viewers_restore": all(
            restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
            and restored.events_since(EventStreamCursor(), viewer_player_id=viewer)
            == session.events_since(EventStreamCursor(), viewer_player_id=viewer)
            for viewer in ("player-a", "player-b")
        ),
        "replay_status": replay.status.value,
        "scope": "facade_shooting_and_fight; successful_roll_exclusion_is_consumer_trace",
    }


def probe_results() -> dict[str, Any]:
    return {
        "schema": "core-v2-order95-probes-v1",
        "decline_all_targets": decline_all_targets(),
        "twin_linked": [twin_linked(phase) for phase in (BattlePhase.SHOOTING, BattlePhase.FIGHT)],
    }


if __name__ == "__main__":
    print(json.dumps(probe_results(), indent=2, sort_keys=True))
