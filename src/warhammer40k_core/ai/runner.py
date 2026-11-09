"""Trusted bounded orchestration over the shared adapter decision authority."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from time import perf_counter
from typing import cast

from warhammer40k_core.adapters.access_control import ViewerContext
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
from warhammer40k_core.engine.event_log import (
    EventLogError,
    JsonValue,
    canonical_json,
    validate_json_value,
)
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
    policy_id: str | None
    choice_seconds: float
    submit_seconds: float
    accepted: bool
    viewer_request_id: str
    observation_hash: str
    choice_seed: int
    submission_outcome: str
    recorded_decisions: int
    failure_stage: str | None


@dataclass(frozen=True, slots=True)
class RunManifest:
    """Operator-only producer evidence; declarations do not authenticate policy code."""

    _canonical_json: str

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], json.loads(self._canonical_json))

    @property
    def run_id(self) -> str:
        return payload_digest(self.to_payload())


@dataclass(frozen=True, slots=True)
class RunReport:
    run_id: str
    stop_reason: str
    decisions: tuple[DecisionTiming, ...]
    elapsed_seconds: float
    manifest: RunManifest | None
    failure_reason: str | None

    def to_payload(self) -> dict[str, JsonValue]:
        """Detached diagnostics for trusted operators, never a player projection."""
        return cast(
            dict[str, JsonValue],
            validate_json_value(
                {
                    "schema": "bounded-player-policy-report-v2",
                    "run_id": self.run_id,
                    "manifest": None if self.manifest is None else self.manifest.to_payload(),
                    "stop_reason": self.stop_reason,
                    "failure_reason": self.failure_reason,
                    "decisions": [asdict(attempt) for attempt in self.decisions],
                    "elapsed_seconds": self.elapsed_seconds,
                }
            ),
        )


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
        self._manifest: RunManifest | None = None
        self._failure_reason: str | None = None

    def _report(self, reason: str) -> RunReport:
        return RunReport(
            self._run_id,
            reason,
            tuple(self._timings),
            perf_counter() - self._started,
            self._manifest,
            self._failure_reason,
        )

    def _fail(self, message: str, reason: str | None = None) -> RunnerError:
        self._failure_reason = reason or self._failure_reason or "contract_error"
        return RunnerError(message, report=self._report("error"))

    def _check_time(self) -> None:
        if perf_counter() - self._started >= self._limits.max_seconds:
            raise self._fail("Runner elapsed-time progress limit reached.", "time_limit")

    def _check_status(self, status: LifecycleStatus) -> None:
        if status.status_kind not in (
            LifecycleStatusKind.WAITING_FOR_DECISION,
            LifecycleStatusKind.TERMINAL,
        ):
            raise self._fail(
                f"Engine stopped with {status.status_kind}: {status.message}",
                "unsupported_engine"
                if status.status_kind is LifecycleStatusKind.UNSUPPORTED
                else "engine_status",
            )

    def run(self, *, stop_at: RunBoundary | None = None) -> RunReport:
        if self._used:
            raise PolicyError("A bounded policy runner is single-use.")
        self._used = True
        self._started = perf_counter()
        try:
            # The checkpoint commitment includes initial engine seed/state, but is
            # operator-only. Policies receive only their separate choice seed.
            identity = self._session.authoritative_identity_payload()
            checkpoint = self._session.to_persistence_payload()
            if not isinstance(checkpoint, dict) or not isinstance(
                checkpoint.get("rng_state"), dict
            ):
                raise self._fail("Runner requires authoritative private RNG checkpoint identity.")
            rng_state = checkpoint["rng_state"]
            assert isinstance(rng_state, dict)
            private_seed = rng_state.get("seed")
            if type(private_seed) is not str or len(private_seed) != 64:
                raise self._fail("Runner requires current private RNG authority.")
            self._manifest = RunManifest(
                canonical_json(
                    {
                        "schema": "bounded-player-policy-run-v2",
                        "engine_build_id": current_engine_build_id(),
                        "initial_checkpoint": payload_digest(checkpoint),
                        "session_identity": identity,
                        "router_identity": self._router.identity,
                        "declared_registrations": self._router.to_manifest_payload(),
                        "registration_evidence": "declared-unverified",
                        "time_limit_enforcement": "cooperative-between-calls",
                        "policy_seed": self._limits.policy_seed,
                        "max_decisions": self._limits.max_decisions,
                        "max_seconds": self._limits.max_seconds,
                        "stop_at": None if stop_at is None else [stop_at.stage, stop_at.context],
                    }
                )
            )
            self._run_id = self._manifest.run_id
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
                pending_view = view["pending_decision"]
                if pending_view is None:
                    raise self._fail("Player observation has no pending decision.")
                choice_identity = payload_digest(
                    [
                        "player-policy-choice-v1",
                        self._limits.policy_seed,
                        view["game_id"],
                        actor_id,
                        pending_view["request_id"],
                    ]
                )
                context = PlayerDecisionContext.from_view(
                    view,
                    choice_seed=int(choice_identity, 16),
                )
                if private_seed in context.observation_json:
                    raise self._fail("Private RNG authority appears in the player projection.")
                if (
                    context.route.actor_id != actor_id
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
                    raise self._fail("Runner decision progress limit reached.", "decision_limit")
                status = self._attempt(context, request.request_id, choice_identity)
        except RunnerError as exc:
            # Refresh after the decision's finally block appends failure timing.
            raise self._fail(str(exc)) from exc
        except (PolicyError, DecisionError, GameLifecycleError, EventLogError) as exc:
            raise self._fail(str(exc), self._failure_reason or "contract_error") from exc

    def _attempt(
        self, context: PlayerDecisionContext, request_id: str, choice_identity: str
    ) -> LifecycleStatus:
        policy_id = None
        choice_seconds = submit_seconds = 0.0
        recorded = 0
        outcome = "not_submitted"
        stage: str | None = "routing"
        before: int | None = None
        try:
            try:
                entry = self._router.resolve(context.route)
            except PolicyError:
                self._failure_reason = "unsupported_route"
                raise
            policy_id = entry.policy_id
            stage = "choice"
            started = perf_counter()
            try:
                action = entry.policy.choose(context)
            finally:
                choice_seconds = perf_counter() - started
            self._check_time()
            stage = "validation"
            self._validate_action(action, context)
            actor_id = context.route.actor_id
            if payload_digest(self._session.view(viewer_player_id=actor_id)) != (
                context.observation_hash
            ):
                raise self._fail("Policy observation became stale before submission.")
            before = self._session.decision_record_count()
            stage = "submission"
            outcome = "unverified"
            started = perf_counter()
            try:
                result_id = f"ai:{choice_identity}"
                if action.option_id is not None:
                    status = self._session.submit_viewer_option(
                        viewer=ViewerContext.for_player(actor_id),
                        request_id=action.request_id,
                        option_id=action.option_id,
                        result_id=result_id,
                    )
                else:
                    assert action.proposal_json is not None
                    status = self._session.submit_viewer_parameterized_payload(
                        viewer=ViewerContext.for_player(actor_id),
                        request_id=action.request_id,
                        payload=validate_json_value(json.loads(action.proposal_json)),
                        result_id=result_id,
                    )
                recorded = self._session.decision_record_count() - before
                # Recorded rule-invalid attempts are not accepted transitions.
                # Other failed statuses do not establish whether a commit occurred.
                if status.status_kind is LifecycleStatusKind.INVALID:
                    outcome = "rejected"
                    raise self._fail(
                        f"Engine rejected invalid submission: {status.message}",
                        "submission_rejected",
                    )
                if status.status_kind not in (
                    LifecycleStatusKind.ADVANCED,
                    LifecycleStatusKind.WAITING_FOR_DECISION,
                    LifecycleStatusKind.TERMINAL,
                ):
                    self._check_status(status)
                if recorded <= 0:
                    raise self._fail(
                        "Submission produced no accepted decision record.", "no_record_progress"
                    )
                outcome = "accepted"
                stage = "progress"
                if status.status_kind is LifecycleStatusKind.ADVANCED:
                    status = self._session.advance_until_decision_or_terminal()
            except (KeyError, TypeError) as exc:
                raise self._fail(
                    "Engine rejected a malformed submission payload.", "malformed_submission"
                ) from exc
            finally:
                submit_seconds = perf_counter() - started
            self._check_status(status)
            if status.decision_request is not None and (
                status.decision_request.request_id == request_id
            ):
                raise self._fail(
                    "Accepted decision made no request progress.", "no_request_progress"
                )
            stage = None
            return status
        finally:
            if before is not None:
                recorded = self._session.decision_record_count() - before
            self._timings.append(
                DecisionTiming(
                    request_id,
                    context.route,
                    policy_id,
                    choice_seconds,
                    submit_seconds,
                    outcome == "accepted",
                    context.request["request_id"],
                    context.observation_hash,
                    context.choice_seed,
                    outcome,
                    recorded,
                    stage,
                )
            )

    def _validate_action(self, action: PolicyAction, context: PlayerDecisionContext) -> None:
        if type(action) is not PolicyAction:
            raise self._fail("Policy returned a malformed action.")
        request = context.request
        if (
            action.actor_id != context.route.actor_id
            or action.request_id != request["request_id"]
            or action.observation_hash != context.observation_hash
        ):
            raise self._fail("Policy action actor, request or observation binding drifted.")
        if request["is_parameterized"] != (action.proposal_json is not None):
            raise self._fail("Policy action submission kind does not match request.")
