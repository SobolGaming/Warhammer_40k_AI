"""Trusted validation and opt-in registration for a prepared ground Charge Move."""

from __future__ import annotations

import json
import multiprocessing
import threading
from dataclasses import dataclass
from multiprocessing.connection import Connection
from time import monotonic

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.ground_charge_candidates import (
    GROUND_CHARGE_GENERATOR_ID,
    MAX_ACCEPTED_CANDIDATES,
    MAX_GEOMETRY_WORK,
    MAX_RAW_CANDIDATES,
    ChargeSearchCounts,
    ChargeSearchStop,
    GroundChargeCandidate,
    GroundChargeExhaustedError,
    generate_ground_charge_candidates,
    ground_charge_route,
)
from warhammer40k_core.ai.player_policy import (
    PlayerDecisionContext,
    PolicyAction,
    PolicyError,
    PolicyRegistration,
    payload_digest,
)
from warhammer40k_core.engine.event_log import canonical_json
from warhammer40k_core.engine.phase import LifecycleStatusKind

MAX_NATIVE_SECONDS = 300
MAX_PROBE_SECONDS = 30
DEFAULT_PROBE_SECONDS = 15


@dataclass(frozen=True, slots=True)
class ChargeCandidateValidation:
    candidate_id: str
    status: LifecycleStatusKind | None
    message: str | None
    elapsed_seconds: float


@dataclass(frozen=True, slots=True)
class _PreparedGroundChargePolicy:
    action: PolicyAction

    def choose(self, context: PlayerDecisionContext) -> PolicyAction:
        if (
            context.route != ground_charge_route(self.action.actor_id)
            or context.observation_hash != self.action.observation_hash
            or context.request["request_id"] != self.action.request_id
        ):
            raise PolicyError("Prepared ground charge is stale for this actor request.")
        return self.action


@dataclass(frozen=True, slots=True)
class PreparedGroundCharge:
    """Operator receipt. The registration receives only the selected actor-bound action."""

    registration: PolicyRegistration
    counts: ChargeSearchCounts
    validations: tuple[ChargeCandidateValidation, ...]
    ranked_accepted_ids: tuple[str, ...]
    stop: ChargeSearchStop
    generation_seconds: float
    validation_seconds: float


class GroundChargeValidationExhaustedError(GroundChargeExhaustedError):
    """Validation finished without an accepted candidate, with operator diagnostics."""

    def __init__(
        self,
        reason: ChargeSearchStop,
        counts: ChargeSearchCounts,
        validations: tuple[ChargeCandidateValidation, ...],
        generation_seconds: float,
        validation_seconds: float,
    ) -> None:
        super().__init__(reason, counts)
        self.validations = validations
        self.generation_seconds = generation_seconds
        self.validation_seconds = validation_seconds


def _checkpoint_hash(session: LocalGameSession) -> str:
    # The complete lifecycle includes the private RNG authority and the histories.
    # Compute only on the trusted side; never pass it in the registered policy.
    return payload_digest(session.lifecycle.to_payload())


def _probe(
    session: LocalGameSession, action: PolicyAction, result_id: str, send: Connection
) -> None:
    # This inherited copy lives in a separate OS process. All session writes,
    # including private dice/history effects, are confined to that process.
    assert action.proposal_json is not None
    with send:
        first_event = len(session.lifecycle.decision_controller.event_log.records)
        status = session.submit_viewer_parameterized_payload(
            viewer=ViewerContext.for_player(action.actor_id),
            request_id=action.request_id,
            payload=json.loads(action.proposal_json),
            result_id=result_id,
        )
        completed = any(
            event.event_type == "charge_move_completed"
            and isinstance(event.payload, dict)
            and event.payload.get("result_id") == result_id
            for event in session.lifecycle.decision_controller.event_log.records[first_event:]
        )
        message = None if status.message is None else status.message[:1_000]
        send.send((status.status_kind.value, message, completed))


def _validate_candidate(
    session: LocalGameSession, candidate: GroundChargeCandidate, seconds: float
) -> ChargeCandidateValidation | None:
    context = multiprocessing.get_context("fork")
    receive, send = context.Pipe(duplex=False)
    worker = context.Process(
        target=_probe,
        args=(session, candidate.action, "ground-charge-probe:" + candidate.candidate_id, send),
    )
    started = monotonic()
    with receive, send:
        worker.start()
        send.close()
        try:
            if not receive.poll(max(0.0, seconds - (monotonic() - started))):
                return None
            try:
                status_token, message, completed = receive.recv()
            except EOFError as exc:
                raise PolicyError("Native ground charge worker exited without a receipt.") from exc
            worker.join(max(0.0, seconds - (monotonic() - started)))
            if worker.exitcode is None:
                return None
            if worker.exitcode != 0:
                raise PolicyError("Native ground charge worker exited unsuccessfully.")
        finally:
            if worker.is_alive():
                worker.kill()
                worker.join()
            worker.close()
    status = LifecycleStatusKind(status_token)
    if status not in (
        LifecycleStatusKind.ADVANCED,
        LifecycleStatusKind.WAITING_FOR_DECISION,
        LifecycleStatusKind.TERMINAL,
        LifecycleStatusKind.INVALID,
    ):
        raise PolicyError(f"Native ground charge stopped with {status}: {message}")
    if completed != (status is not LifecycleStatusKind.INVALID):
        raise PolicyError("Native ground charge validation lacked a consistent completion record.")
    return ChargeCandidateValidation(candidate.candidate_id, status, message, monotonic() - started)


def _require_limit(value: int, maximum: int) -> None:
    if type(value) is not int or not 0 < value <= maximum:
        raise PolicyError(f"Ground charge validation limit must be an integer in [1, {maximum}].")


def prepare_ground_charge_policy(
    session: LocalGameSession,
    context: PlayerDecisionContext,
    *,
    raw_limit: int = MAX_RAW_CANDIDATES,
    geometry_limit: int = MAX_GEOMETRY_WORK,
    validation_limit: int = MAX_RAW_CANDIDATES,
    accepted_limit: int = MAX_ACCEPTED_CANDIDATES,
    native_seconds: int = MAX_NATIVE_SECONDS,
    per_probe_seconds: int = DEFAULT_PROBE_SECONDS,
) -> PreparedGroundCharge:
    """Prepare one registration against an exclusively owned Linux local session.

    Forking keeps each native submission disposable and separately killable.
    Invoke from a single-threaded host, before starting the ordinary policy runner.
    """
    if type(session) is not LocalGameSession:
        raise PolicyError("Ground charge validation requires a local session.")
    if "fork" not in multiprocessing.get_all_start_methods() or threading.active_count() != 1:
        raise PolicyError("Ground charge validation requires a single-threaded fork-capable host.")
    for value, maximum in (
        (validation_limit, MAX_RAW_CANDIDATES),
        (accepted_limit, MAX_ACCEPTED_CANDIDATES),
        (native_seconds, MAX_NATIVE_SECONDS),
        (per_probe_seconds, MAX_PROBE_SECONDS),
    ):
        _require_limit(value, maximum)
    actor = context.route.actor_id
    if payload_digest(session.view(viewer_player_id=actor)) != context.observation_hash:
        raise PolicyError("Ground charge validation does not match the current actor view.")
    checkpoint = _checkpoint_hash(session)
    started = monotonic()
    generated = generate_ground_charge_candidates(
        context, raw_limit=raw_limit, geometry_limit=geometry_limit
    )
    generation_seconds = monotonic() - started
    started = monotonic()
    validations: list[ChargeCandidateValidation] = []
    accepted: list[GroundChargeCandidate] = []
    stop = generated.stop
    for candidate in generated.candidates:
        if len(accepted) == accepted_limit:
            stop = ChargeSearchStop.ACCEPTED_LIMIT
            break
        if len(validations) == validation_limit:
            stop = ChargeSearchStop.VALIDATION_LIMIT
            break
        remaining = native_seconds - (monotonic() - started)
        if remaining <= 0:
            stop = ChargeSearchStop.NATIVE_TIMEOUT
            break
        probe_started = monotonic()
        receipt = _validate_candidate(session, candidate, min(per_probe_seconds, remaining))
        if receipt is None:
            validations.append(
                ChargeCandidateValidation(
                    candidate.candidate_id,
                    None,
                    "Native probe wall limit reached.",
                    monotonic() - probe_started,
                )
            )
            continue
        validations.append(receipt)
        if receipt.status is not LifecycleStatusKind.INVALID:
            accepted.append(candidate)
    validation_seconds = monotonic() - started
    if _checkpoint_hash(session) != checkpoint:
        raise PolicyError("Live ground charge checkpoint changed during validation.")
    counts = ChargeSearchCounts(
        raw=len(generated.candidates),
        geometry_work=generated.geometry_work,
        accepted=len(accepted),
        rejected=sum(probe.status is LifecycleStatusKind.INVALID for probe in validations),
        timed_out=sum(probe.status is None for probe in validations),
    )
    if not accepted:
        if counts.timed_out:
            stop = ChargeSearchStop.NATIVE_TIMEOUT
        raise GroundChargeValidationExhaustedError(
            stop,
            counts,
            tuple(validations),
            generation_seconds,
            validation_seconds,
        )
    ranked = sorted(
        accepted,
        key=lambda candidate: (
            candidate.longest_path_inches,
            candidate.total_path_inches,
        ),
    )
    configuration = {
        "raw_limit": raw_limit,
        "geometry_limit": geometry_limit,
        "validation_limit": validation_limit,
        "accepted_limit": accepted_limit,
        "native_seconds": native_seconds,
        "per_probe_seconds": per_probe_seconds,
        "request_id": ranked[0].action.request_id,
    }
    registration = PolicyRegistration(
        ground_charge_route(actor),
        GROUND_CHARGE_GENERATOR_ID,
        canonical_json(configuration),
        _PreparedGroundChargePolicy(ranked[0].action),
    )
    return PreparedGroundCharge(
        registration,
        counts,
        tuple(validations),
        tuple(candidate.candidate_id for candidate in ranked),
        stop,
        generation_seconds,
        validation_seconds,
    )
