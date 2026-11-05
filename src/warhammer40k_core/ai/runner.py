"""Trusted bounded orchestration over the shared adapter decision authority."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from time import perf_counter

from warhammer40k_core.adapters.contracts import AdapterGameSession
from warhammer40k_core.adapters.projection import GameViewPayload
from warhammer40k_core.ai.player_policy import (
    PlayerDecisionContext,
    PolicyAction,
    PolicyError,
    PolicyRoute,
    PolicyRouter,
    payload_digest,
)
from warhammer40k_core.build_identity import current_engine_build_id
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.event_log import EventLogError, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus, LifecycleStatusKind


@dataclass(frozen=True, slots=True)
class RunLimits:
    policy_seed: int
    max_decisions: int
    max_seconds: float

    def __post_init__(self) -> None:
        if type(self.policy_seed) is not int or self.policy_seed < 0:
            raise PolicyError("Runner policy seed must be a nonnegative integer.")
        if type(self.max_decisions) is not int or self.max_decisions <= 0:
            raise PolicyError("Runner decision limit must be a positive integer.")
        if type(self.max_seconds) not in (int, float) or (
            not math.isfinite(self.max_seconds) or self.max_seconds <= 0
        ):
            raise PolicyError("Runner time limit must be finite and positive.")


@dataclass(frozen=True, slots=True)
class RunBoundary:
    """An explicit successful stop before choosing at a setup or battle boundary."""

    stage: str
    context: str

    def __post_init__(self) -> None:
        if self.stage not in ("setup", "battle") or not self.context.strip():
            raise PolicyError("Runner boundary requires setup/battle and a context.")

    def matches(self, view: GameViewPayload) -> bool:
        context = (
            view["current_setup_step"] if self.stage == "setup" else view["current_battle_phase"]
        )
        return view["stage"] == self.stage and context == self.context


@dataclass(frozen=True, slots=True)
class DecisionTiming:
    request_id: str
    route: PolicyRoute
    policy_id: str
    choice_seconds: float
    submit_seconds: float
    accepted: bool


@dataclass(frozen=True, slots=True)
class RunReport:
    run_id: str
    stop_reason: str
    decisions: tuple[DecisionTiming, ...]
    elapsed_seconds: float


class RunnerError(PolicyError):
    def __init__(self, message: str, *, report: RunReport) -> None:
        super().__init__(message)
        self.report = report


class BoundedPolicyRunner:
    """Single-use synchronous runner. Limits are checked between engine/policy calls.

    The caller owns the session exclusively for the duration of the run. This does
    not interrupt a blocking policy/engine call or sandbox arbitrary Python code.
    No hypothetical search, game-state fork or RNG is passed to policies.
    """

    def __init__(
        self, *, session: AdapterGameSession, router: PolicyRouter, limits: RunLimits
    ) -> None:
        self._session = session
        self._router = router
        self._limits = limits
        self._used = False
        self._timings: list[DecisionTiming] = []
        self._started = 0.0
        self._run_id = "unstarted"

    def _report(self, reason: str) -> RunReport:
        return RunReport(self._run_id, reason, tuple(self._timings), perf_counter() - self._started)

    def _fail(self, message: str) -> RunnerError:
        return RunnerError(message, report=self._report("error"))

    def _check_time(self) -> None:
        if perf_counter() - self._started >= self._limits.max_seconds:
            raise self._fail("Runner elapsed-time progress limit reached.")

    def _check_status(self, status: LifecycleStatus) -> None:
        if status.status_kind not in (
            LifecycleStatusKind.WAITING_FOR_DECISION,
            LifecycleStatusKind.TERMINAL,
        ):
            raise self._fail(f"Engine stopped with {status.status_kind}: {status.message}")

    def run(self, *, stop_at: RunBoundary | None = None) -> RunReport:
        if self._used:
            raise PolicyError("A bounded policy runner is single-use.")
        self._used = True
        self._started = perf_counter()
        try:
            # The checkpoint commitment includes initial engine seed/state, but is
            # operator-only. Policies receive only their separate choice seed.
            identity = self._session.authoritative_identity_payload()
            self._run_id = payload_digest(
                {
                    "schema": "bounded-player-policy-run-v1",
                    "engine_build_id": current_engine_build_id(),
                    "initial_checkpoint": payload_digest(self._session.to_persistence_payload()),
                    "session_identity": identity,
                    "router_identity": self._router.identity,
                    "policy_seed": self._limits.policy_seed,
                    "max_decisions": self._limits.max_decisions,
                    "max_seconds": self._limits.max_seconds,
                    "stop_at": None if stop_at is None else [stop_at.stage, stop_at.context],
                }
            )
            status = self._session.advance_until_decision_or_terminal()
            while True:
                self._check_status(status)
                self._check_time()
                if status.status_kind is LifecycleStatusKind.TERMINAL:
                    return self._report("terminal")
                request = status.decision_request
                if request is None or request.actor_id not in identity["player_ids"]:
                    raise self._fail("Pending decision has no configured player actor.")
                actor_id = request.actor_id
                assert actor_id is not None
                view = self._session.view(viewer_player_id=actor_id)
                context = PlayerDecisionContext.from_view(
                    view,
                    choice_seed=int(
                        payload_digest(
                            [
                                self._limits.policy_seed,
                                len(self._timings),
                                actor_id,
                                request.request_id,
                            ]
                        ),
                        16,
                    ),
                )
                if (
                    context.request["request_id"] != request.request_id
                    or context.route.actor_id != actor_id
                    or context.route.decision_type != request.decision_type
                    or context.request["is_parameterized"]
                    != request.is_parameterized_submission_request()
                ):
                    raise self._fail(
                        "Player observation and authoritative pending request drifted."
                    )
                if stop_at is not None and stop_at.matches(view):
                    return self._report("requested_boundary")
                if len(self._timings) >= self._limits.max_decisions:
                    raise self._fail("Runner decision progress limit reached.")
                entry = self._router.resolve(context.route)
                choice_started = perf_counter()
                choice_seconds = submit_seconds = 0.0
                accepted = False
                try:
                    action = entry.policy.choose(context)
                    choice_seconds = perf_counter() - choice_started
                    self._check_time()
                    self._validate_action(action, context)
                    # Compare detached snapshots immediately before committing. A
                    # stale choice is an error, never a request to choose again.
                    if payload_digest(self._session.view(viewer_player_id=actor_id)) != (
                        context.observation_hash
                    ):
                        raise self._fail("Policy observation became stale before submission.")
                    before = self._session.decision_record_count()
                    submit_started = perf_counter()
                    try:
                        result_id = f"ai:{self._run_id}:{len(self._timings)}"
                        if action.option_id is not None:
                            status = self._session.submit_option(
                                request_id=action.request_id,
                                option_id=action.option_id,
                                result_id=result_id,
                            )
                        else:
                            assert action.proposal_json is not None
                            status = self._session.submit_parameterized_payload(
                                request_id=action.request_id,
                                payload=validate_json_value(json.loads(action.proposal_json)),
                                result_id=result_id,
                            )
                        # An accepted policy result may also cause engine-owned
                        # automatic selections. They remain authoritative records.
                        accepted = self._session.decision_record_count() > before
                        if not accepted:
                            self._check_status(status)
                            raise self._fail("Submission produced no accepted decision record.")
                        if status.status_kind is LifecycleStatusKind.ADVANCED:
                            status = self._session.advance_until_decision_or_terminal()
                    except (KeyError, TypeError) as exc:
                        raise self._fail("Engine rejected a malformed submission payload.") from exc
                    finally:
                        submit_seconds = perf_counter() - submit_started
                    self._check_status(status)
                    if status.decision_request is not None and (
                        status.decision_request.request_id == request.request_id
                    ):
                        raise self._fail("Accepted decision made no request progress.")
                finally:
                    if choice_seconds == 0.0:
                        choice_seconds = perf_counter() - choice_started
                    self._timings.append(
                        DecisionTiming(
                            request.request_id,
                            context.route,
                            entry.policy_id,
                            choice_seconds,
                            submit_seconds,
                            accepted,
                        )
                    )
        except RunnerError as exc:
            # Refresh after the decision's finally block appends failure timing.
            raise self._fail(str(exc)) from exc
        except (PolicyError, DecisionError, GameLifecycleError, EventLogError) as exc:
            raise self._fail(str(exc)) from exc

    def _validate_action(self, action: PolicyAction, context: PlayerDecisionContext) -> None:
        if type(action) is not PolicyAction:
            raise self._fail("Policy returned a malformed action.")
        if (
            action.actor_id != context.route.actor_id
            or action.request_id != context.request["request_id"]
            or action.observation_hash != context.observation_hash
        ):
            raise self._fail("Policy action actor, request or observation binding drifted.")
        if context.request["is_parameterized"] != (action.proposal_json is not None):
            raise self._fail("Policy action submission kind does not match request.")
