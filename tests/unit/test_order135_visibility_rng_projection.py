"""Approved unchanged scalar LOS preserves dice without weakening physical proof."""

import json
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
from typing import cast

import pytest
from tests.order128_helpers import assert_checkpoint
from tests.order135_rng_helpers import native_scalar_shooting_request
from tests.phase13b_shooting_declaration_helpers import _proposal_from_request
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.visibility import (
    TerrainVisibilityContext,
    TerrainVisibilityContextPayload,
)
from warhammer40k_core.core.visibility_records import LineOfSightWitness, LineOfSightWitnessPayload
from warhammer40k_core.engine.decision import (
    _rng_payload_history_token,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.model_body import ModelBodyPart
from warhammer40k_core.geometry.physical_visibility import BattlefieldVisibilityBounds
from warhammer40k_core.geometry.pose import GeometryError, Pose

ROOT = Path(__file__).resolve().parents[2]


def _context() -> TerrainVisibilityContext:
    baseline = json.loads(
        (ROOT / "data/source_audits/order135/los-rng-base-control.json").read_text()
    )
    payload = baseline["context"] | {
        "battlefield_bounds": {"min_x": "0", "min_y": "0", "max_x": "12", "max_y": "12"}
    }
    return TerrainVisibilityContext.from_payload(cast(TerrainVisibilityContextPayload, payload))


def test_scalar_projection_matches_actual_base_token_and_keeps_current_authority() -> None:
    baseline = json.loads(
        (ROOT / "data/source_audits/order135/los-rng-base-control.json").read_text()
    )
    context = _context()
    witness = context.resolve_line_of_sight()
    payload = witness.to_payload()
    assert witness.rng_compatibility_projection is not None
    assert payload["context_fingerprint"] != baseline["witness"]["context_fingerprint"]
    assert payload["model_records"][0]["evidence"]["algorithm_id"].endswith(":2")
    assert (
        payload["model_records"][0]["evidence"]["input_fingerprint"]
        != (baseline["witness"]["model_records"][0]["evidence"]["input_fingerprint"])
    )
    assert _rng_payload_history_token(validate_json_value(payload)) == baseline["rng_history_token"]
    assert LineOfSightWitness.from_payload(json.loads(json.dumps(payload))) == witness
    assert witness.to_payload() == payload
    altered_bounds = replace(
        context,
        battlefield_bounds=BattlefieldVisibilityBounds(
            Fraction(0), Fraction(0), Fraction(14), Fraction(12)
        ),
    )
    alternate = altered_bounds.resolve_line_of_sight()
    assert alternate.context_fingerprint != witness.context_fingerprint
    assert alternate.model_records[0].evidence.input_fingerprint != (
        witness.model_records[0].evidence.input_fingerprint
    )
    assert (
        _rng_payload_history_token(validate_json_value(alternate.to_payload()))
        == (baseline["rng_history_token"])
    )


@pytest.mark.parametrize("subject", ["observer", "target", "blocker", "clipped"])
def test_changed_physical_domains_have_no_legacy_rng_projection(subject: str) -> None:
    context = _context()
    body = ModelBodyPart("body", CircularBase(1), 0, 0, 0, 2, "analytical:body")
    if subject == "observer":
        context = replace(
            context, observer_model=replace(context.observer_model, body_parts=(body,))
        )
    elif subject == "target":
        context = replace(
            context, target_models=(replace(context.target_models[0], body_parts=(body,)),)
        )
    elif subject == "blocker":
        blocker = replace(
            context.target_models[0], model_id="blocker", pose=Pose.at(10, 10), body_parts=(body,)
        )
        context = replace(context, dynamic_model_blockers=(blocker,))
    else:
        context = replace(
            context, observer_model=replace(context.observer_model, pose=Pose.at(0, 2))
        )
    witness = context.resolve_line_of_sight()
    assert witness.rng_compatibility_projection is None
    assert "rng_compatibility_projection" not in witness.to_payload()
    assert LineOfSightWitness.from_payload(witness.to_payload()) == witness
    assert witness.context_fingerprint in _rng_payload_history_token(
        validate_json_value(witness.to_payload())
    )


@pytest.mark.parametrize("change", ["missing", "hash", "target", "version", "extra"])
def test_projection_is_strict_and_bound_to_fresh_authoritative_witness(change: str) -> None:
    context = _context()
    payload = json.loads(json.dumps(context.resolve_line_of_sight().to_payload()))
    if change == "missing":
        del payload["rng_compatibility_projection"]
    elif change == "hash":
        payload["rng_compatibility_projection"]["context_fingerprint"] = "0" * 64
    elif change == "target":
        payload["rng_compatibility_projection"]["pairs"][0]["target_model_id"] = "different-target"
    elif change == "version":
        payload["rng_compatibility_projection"]["version"] = "unapproved:2"
    else:
        payload["rng_compatibility_projection"]["unknown"] = True
    with pytest.raises(GeometryError):
        context.benefit_of_cover(
            LineOfSightWitness.from_payload(cast(LineOfSightWitnessPayload, payload))
        )


def test_native_scalar_projection_preserves_pending_completed_save_fork_and_replay() -> None:
    session, request = native_scalar_shooting_request()
    proposal = _proposal_from_request(request=request, target_unit_id="army-beta:scalar")
    proposal_request = cast(
        dict[str, object], cast(dict[str, object], request.payload)["proposal_request"]
    )
    candidates = cast(list[dict[str, object]], proposal_request["target_candidates"])
    assert candidates
    assert all(
        LineOfSightWitness.from_payload(
            cast(LineOfSightWitnessPayload, row["line_of_sight_witness"])
        ).rng_compatibility_projection
        is not None
        for row in candidates
    )
    assert_checkpoint(session)
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    recovered = LocalGameSession.from_persistence_payload(checkpoint)
    forked = session.fork()
    for current in (session, recovered, forked):
        accepted = current.submit_parameterized_payload(
            request_id=request.request_id,
            result_id="order135-rng:declaration",
            payload=validate_json_value(proposal.to_payload()),
        )
        assert accepted.status_kind is not LifecycleStatusKind.INVALID, accepted.to_payload()
        for _ in range(40):
            if any(
                event.event_type == "attack_sequence_completed"
                for event in current.lifecycle.decision_controller.event_log.records
            ):
                break
            submit_fixture_request(current, pending_request(current))
        else:
            raise AssertionError("Native scalar attack did not complete.")
    assert any(
        event.event_type == "dice_rolled"
        for event in session.lifecycle.decision_controller.event_log.records
    )
    assert (
        recovered.to_persistence_payload()
        == forked.to_persistence_payload()
        == session.to_persistence_payload()
    )
    assert_checkpoint(session)
