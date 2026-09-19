"""Reconstruct inherited ingress rules from independent pre-ingress authority."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_request import DecisionRequest
    from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload

ORIGIN_KEY = "ingress_placement_history_origin"


def _is_ingress_request(request: DecisionRequest) -> bool:
    from warhammer40k_core.engine.movement_proposals import (
        PLACEMENT_PROPOSAL_DECISION_TYPE,
        MovementProposalRequest,
        MovementProposalRequestPayload,
    )

    if request.decision_type != PLACEMENT_PROPOSAL_DECISION_TYPE:
        return False
    if not isinstance(request.payload, dict):
        raise GameLifecycleError("Ingress placement request requires an object payload.")
    proposal = MovementProposalRequest.from_payload(
        cast(MovementProposalRequestPayload, request.payload["proposal_request"])
    )
    if proposal.context is None or "reserve_state" not in proposal.context:
        return False
    from warhammer40k_core.engine.reserves import ReserveState, ReserveStatePayload

    raw = proposal.context["reserve_state"]
    if not isinstance(raw, dict):
        raise GameLifecycleError("Ingress source requires a ReserveState object.")
    reserve = ReserveState.from_payload(cast(ReserveStatePayload, raw))
    return bool(reserve.embarked_unit_instance_ids)


@dataclass(frozen=True, slots=True)
class IngressPlacementHistoryOrigin:
    initial_lifecycle_json: str

    def to_payload(self) -> dict[str, JsonValue]:
        import json

        value = validate_json_value(json.loads(self.initial_lifecycle_json))
        if not isinstance(value, dict):
            raise GameLifecycleError("Ingress historical origin requires a lifecycle object.")
        return value

    @classmethod
    def from_payload(cls, payload: JsonValue) -> IngressPlacementHistoryOrigin:
        from warhammer40k_core.engine.decision_controller import (
            DecisionController,
            DecisionControllerPayload,
        )

        if not isinstance(payload, dict) or ORIGIN_KEY in payload:
            raise GameLifecycleError("Ingress historical origin cannot contain another origin.")
        raw_decisions = payload.get("decisions")
        if not isinstance(raw_decisions, dict):
            raise GameLifecycleError("Ingress historical origin lacks decision authority.")
        decisions = DecisionController.from_payload(cast(DecisionControllerPayload, raw_decisions))
        if any(_is_ingress_request(record.request) for record in decisions.records):
            raise GameLifecycleError(
                "Ingress historical origin must precede the first loaded-Transport ingress attempt."
            )
        if not decisions.queue.pending_requests or not _is_ingress_request(
            decisions.queue.pending_requests[0]
        ):
            raise GameLifecycleError(
                "Ingress historical origin requires a pending loaded-Transport ingress request."
            )
        return cls(canonical_json(payload))


def capture_ingress_history_origin(
    *,
    lifecycle: GameLifecycle,
    request: DecisionRequest | None,
    existing: IngressPlacementHistoryOrigin | None,
) -> IngressPlacementHistoryOrigin | None:
    if existing is not None or request is None or not _is_ingress_request(request):
        return existing
    return IngressPlacementHistoryOrigin.from_payload(validate_json_value(lifecycle.to_payload()))


def validate_ingress_history_origin(
    *,
    lifecycle: GameLifecycle,
    origin: IngressPlacementHistoryOrigin | None,
) -> None:
    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner

    decisions = lifecycle.decision_controller
    if not any(_is_ingress_request(record.request) for record in decisions.records):
        if origin is not None:
            raise GameLifecycleError("Ingress history has an orphan origin.")
        return
    if origin is None:
        raise GameLifecycleError("Ingress history lacks its pre-ingress authority.")
    payload = origin.to_payload()
    current = lifecycle.to_payload()
    if canonical_json(payload.get("config")) != canonical_json(current["config"]):
        raise GameLifecycleError("Ingress historical origin config/catalog authority drift.")
    original = payload["decisions"]
    present = validate_json_value(current["decisions"])
    if not isinstance(original, dict) or not isinstance(present, dict):
        raise GameLifecycleError("Ingress historical origin requires decision ledgers.")
    for key in ("records", "event_log"):
        prefix, actual = original[key], present[key]
        if (
            not isinstance(prefix, list)
            or not isinstance(actual, list)
            or canonical_json(prefix) != canonical_json(actual[: len(prefix)])
        ):
            raise GameLifecycleError("Ingress historical origin ledger prefix drift.")
    artifact = ReplayArtifact.capture(
        artifact_id="ingress-placement-historical-authority",
        initial_lifecycle_payload=cast("GameLifecyclePayload", payload),
        final_lifecycle=lifecycle,
    )
    replay = ReplayRunner(artifact).run()
    if not replay.reproduced_exactly:
        raise GameLifecycleError(
            "Ingress placement historical reconstruction drifted: "
            + ", ".join(row.diagnostic_code.value for row in replay.diagnostics)
        )
