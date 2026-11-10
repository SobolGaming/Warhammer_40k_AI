"""One frozen operator fixture, reproduced through the ordinary player runner."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import cast

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.replay import submit_replay_record
from warhammer40k_core.adapters.setup_smoke import canonical_setup_prebattle_smoke_config
from warhammer40k_core.ai.player_policy import (
    PlayerDecisionContext,
    PolicyAction,
    PolicyRegistration,
    PolicyRoute,
    PolicyRouter,
    payload_digest,
)
from warhammer40k_core.ai.runner import BoundedPolicyRunner, RunBoundary, RunLimits, RunReport
from warhammer40k_core.ai.training_admission import TrainingAdmissionError, VerifiedEpisodeOrigin
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.phase import LifecycleStatusKind

CANONICAL_DEPLOYMENT_ID = "canonical-deployment-v1"
CANONICAL_DEPLOYMENT_CONFIG_HASH = (
    "adfdb1ee885d9de34ddbe6ef7fe1be64c728f86d3529dc2e82b7523132926409"
)
CANONICAL_DEPLOYMENT_SCHEMA = "canonical-deployment-admission-v1"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TrainingAdmissionError(message)


@dataclass(frozen=True, slots=True)
class _Step:
    actor: str
    decision_type: str
    setup_step: str
    option_id: str | None
    unit_id: str | None = None
    model_count: int = 0
    x: float = 0.0
    y: float = 0.0

    @property
    def route(self) -> PolicyRoute:
        return PolicyRoute(
            self.actor,
            self.decision_type,
            "setup",
            self.setup_step,
            None,
            "deployment_placement" if self.option_id is None else None,
        )


# A fixed recipe, not a first-legal policy or a search over deployment alternatives.
_STEPS = (
    _Step(
        "player-a",
        "select_secondary_missions",
        "select_secondary_missions",
        "fixed:assassination:bring_it_down",
    ),
    _Step(
        "player-b",
        "select_secondary_missions",
        "select_secondary_missions",
        "fixed:assassination:bring_it_down",
    ),
    _Step(
        "player-a",
        "select_reserve_declaration",
        "declare_battle_formations",
        "complete_reserve_declarations",
    ),
    _Step(
        "player-b",
        "select_deployment_unit",
        "deploy_armies",
        "deploy:army-beta:scout-redeploy-unit",
    ),
    _Step(
        "player-b",
        "submit_deployment_placement",
        "deploy_armies",
        None,
        "army-beta:scout-redeploy-unit",
        5,
        3.0,
        3.0,
    ),
    _Step(
        "player-a", "select_deployment_unit", "deploy_armies", "deploy:army-alpha:deep-strike-unit"
    ),
    _Step(
        "player-a",
        "submit_deployment_placement",
        "deploy_armies",
        None,
        "army-alpha:deep-strike-unit",
        3,
        3.0,
        45.0,
    ),
    _Step(
        "player-a",
        "select_deployment_unit",
        "deploy_armies",
        "deploy:army-alpha:scout-redeploy-unit",
    ),
    _Step(
        "player-a",
        "submit_deployment_placement",
        "deploy_armies",
        None,
        "army-alpha:scout-redeploy-unit",
        5,
        3.0,
        51.0,
    ),
    _Step(
        "player-a",
        "select_deployment_unit",
        "deploy_armies",
        "deploy:army-alpha:strategic-reserve-unit",
    ),
    _Step(
        "player-a",
        "submit_deployment_placement",
        "deploy_armies",
        None,
        "army-alpha:strategic-reserve-unit",
        1,
        7.0,
        57.0,
    ),
)


def canonical_deployment_config() -> GameConfig:
    """Reconstruct the exact published test configuration, including its fixed seed."""
    config = canonical_setup_prebattle_smoke_config(game_id=CANONICAL_DEPLOYMENT_ID)
    _require(
        payload_digest(config.to_payload()) == CANONICAL_DEPLOYMENT_CONFIG_HASH,
        "Canonical deployment configuration drifted; review and version the fixture.",
    )
    return config


def _recipe_payload() -> JsonValue:
    return validate_json_value([asdict(step) for step in _STEPS])


class _RecipePolicy:
    """State is only a fixed recipe cursor; inputs remain detached actor views."""

    def __init__(self, steps: tuple[_Step, ...] = _STEPS) -> None:
        self.steps = steps
        self.index = 0

    def choose(self, context: PlayerDecisionContext) -> PolicyAction:
        _require(self.index < len(self.steps), "Canonical deployment recipe exhausted.")
        step = self.steps[self.index]
        _require(context.route == step.route, "Canonical deployment route order drifted.")
        if step.option_id is not None:
            _require(
                step.option_id in {option["option_id"] for option in context.request["options"]},
                "Canonical deployment finite option is unavailable.",
            )
            action = context.select_option(step.option_id)
        else:
            proposal = context.observation["pending_proposal"]
            if not isinstance(proposal, dict):
                raise TrainingAdmissionError("Canonical deployment proposal is unavailable.")
            _require(
                proposal["unit_instance_id"] == step.unit_id
                and isinstance(proposal["model_instance_ids"], list)
                and len(proposal["model_instance_ids"]) == step.model_count,
                "Canonical deployment formation drifted.",
            )
            assert step.unit_id is not None
            models = cast(list[str], proposal["model_instance_ids"])
            payload = {
                key: proposal[key]
                for key in (
                    "proposal_kind",
                    "game_id",
                    "ruleset_descriptor_hash",
                    "setup_step",
                    "player_id",
                    "unit_instance_id",
                    "placement_kind",
                    "context",
                )
            }
            payload["proposal_request_id"] = proposal["request_id"]
            payload["model_placements"] = [
                {
                    "army_id": step.unit_id.split(":", maxsplit=1)[0],
                    "player_id": step.actor,
                    "unit_instance_id": step.unit_id,
                    "model_instance_id": model,
                    "pose": {
                        "position": {
                            "x": step.x + (index // 3) * 1.8,
                            "y": step.y + (index % 3) * 1.8,
                            "z": 0.0,
                        },
                        "facing": {"degrees": 180.0 if step.actor == "player-b" else 0.0},
                    },
                }
                for index, model in enumerate(models)
            ]
            action = context.propose(payload)
        self.index += 1
        return action


def reproduce_canonical_deployment() -> tuple[LocalGameSession, RunReport]:
    """Execute exactly eleven ordinary choices and stop before any redeploy choice.

    Timing in the returned diagnostic report is not component-cost qualification.
    No input checkpoint, caller policy, state mutation or alternate recipe is admitted.
    """
    return _reproduce_recipe(_STEPS, recipe_id=CANONICAL_DEPLOYMENT_ID)


def _reproduce_recipe(
    steps: tuple[_Step, ...], *, recipe_id: str
) -> tuple[LocalGameSession, RunReport]:
    """Shared ordinary runner for explicitly declared operator recipes."""
    session = LocalGameSession()
    session.start(canonical_deployment_config())
    policy = _RecipePolicy(steps)
    routes = tuple(dict.fromkeys(step.route for step in steps))
    router = PolicyRouter(
        tuple(
            PolicyRegistration(
                route,
                recipe_id,
                canonical_json({"recipe": validate_json_value([asdict(step) for step in steps])}),
                policy,
            )
            for route in routes
        )
    )
    report = BoundedPolicyRunner(
        session=session,
        router=router,
        limits=RunLimits(policy_seed=7, max_decisions=len(steps), max_seconds=120.0),
    ).run(stop_at=RunBoundary("setup", "redeploy_units"))
    _require(
        report.stop_reason == "requested_boundary"
        and len(report.decisions) == len(steps)
        and tuple(attempt.route for attempt in report.decisions)
        == tuple(step.route for step in steps)
        and all(
            attempt.accepted and attempt.recorded_decisions == 1 for attempt in report.decisions
        )
        and session.decision_record_count() == len(steps),
        "Canonical deployment accepted trace drifted.",
    )
    return session, report


def canonical_deployment_prefixes(
    session: LocalGameSession, report: RunReport
) -> tuple[tuple[LocalGameSession, PlayerDecisionContext, PolicyAction], ...]:
    """Reconstruct the exact admitted recipe's before-choice states for operators.

    Replay uses the existing ordinary adapter owner; no lifecycle is edited.
    These private forks are never policy inputs. The final checkpoint must match
    the separately reproduced runner endpoint before any prefix is returned.
    """
    return _recipe_prefixes(session, report, steps=_STEPS)


def _recipe_prefixes(
    session: LocalGameSession, report: RunReport, *, steps: tuple[_Step, ...]
) -> tuple[tuple[LocalGameSession, PlayerDecisionContext, PolicyAction], ...]:
    """Replay every accepted record and bind the independently reproduced endpoint."""
    fresh = LocalGameSession()
    fresh.start(canonical_deployment_config())
    fresh.advance_until_decision_or_terminal()
    policy = _RecipePolicy(steps)
    records = session.lifecycle.decision_controller.records
    _require(
        len(records) == len(report.decisions) == len(steps),
        "Canonical coverage requires the complete recipe trace.",
    )
    prefixes: list[tuple[LocalGameSession, PlayerDecisionContext, PolicyAction]] = []
    for index, (record, attempt) in enumerate(zip(records, report.decisions, strict=True)):
        context = PlayerDecisionContext.from_view(
            fresh.view(viewer_player_id=attempt.route.actor_id), choice_seed=attempt.choice_seed
        )
        _require(
            context.route == steps[index].route == attempt.route
            and context.observation_hash == attempt.observation_hash
            and fresh.decision_record_count() == index,
            "Canonical coverage prefix drifted.",
        )
        action = policy.choose(context)
        prefixes.append((fresh.fork(), context, action))
        status = submit_replay_record(session=fresh, record=record)
        if status.status_kind is LifecycleStatusKind.ADVANCED:
            status = fresh.advance_until_decision_or_terminal()
        _require(
            status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
            and fresh.lifecycle.decision_controller.records[-1] == record,
            "Canonical coverage prefix replay failed.",
        )
    _require(
        canonical_json(fresh.to_persistence_payload())
        == canonical_json(session.to_persistence_payload()),
        "Canonical coverage endpoint drifted.",
    )
    return tuple(prefixes)


@dataclass(frozen=True, slots=True, init=False)
class CanonicalDeploymentAdmission:
    """Exact-fixture operator evidence, not arbitrary workload or dataset admission.

    The receipt binds a separately supplied session to fresh ordinary reproduction
    and strict startup/save/load replay. It grants no additional actor information.
    """

    _payload_json: str

    def __init__(self) -> None:
        raise TrainingAdmissionError("Admit the canonical fixture through its ordinary session.")

    @classmethod
    def from_session(cls, session: LocalGameSession) -> CanonicalDeploymentAdmission:
        _require(type(session) is LocalGameSession, "Canonical admission requires a local session.")
        config = canonical_deployment_config()
        _require(
            payload_digest(session.lifecycle.config.to_payload())
            == CANONICAL_DEPLOYMENT_CONFIG_HASH,
            "Session is outside the frozen canonical deployment configuration.",
        )
        expected, report = reproduce_canonical_deployment()
        checkpoint = session.to_persistence_payload()
        _require(
            canonical_json(checkpoint) == canonical_json(expected.to_persistence_payload()),
            "Session differs from the exact canonical deployment trace or endpoint.",
        )
        origin = VerifiedEpisodeOrigin.from_session(session, config=config)
        required = list(dict.fromkeys(step.route for step in _STEPS))
        observed = list(dict.fromkeys(attempt.route for attempt in report.decisions))
        request = session.lifecycle.pending_decision_request()
        assert request is not None
        assert request.actor_id is not None
        endpoint = PolicyRoute.from_view(session.view(viewer_player_id=request.actor_id))
        payload = {
            "schema_version": CANONICAL_DEPLOYMENT_SCHEMA,
            "fixture_id": CANONICAL_DEPLOYMENT_ID,
            "configuration": config.to_payload(),
            "configuration_hash": CANONICAL_DEPLOYMENT_CONFIG_HASH,
            "recipe": _recipe_payload(),
            "policy_seed": 7,
            "origin": origin.to_payload(),
            "accepted_trace": [
                {
                    "index": index,
                    "route": asdict(attempt.route),
                    "record": record.to_payload(),
                    "observation_hash": attempt.observation_hash,
                }
                for index, (attempt, record) in enumerate(
                    zip(
                        report.decisions, session.lifecycle.decision_controller.records, strict=True
                    )
                )
            ],
            "required_routes": [asdict(route) for route in required],
            "observed_routes": [asdict(route) for route in observed],
            "unobserved_required_routes": [
                asdict(route) for route in required if route not in observed
            ],
            "endpoint_route": asdict(endpoint),
            "replay_artifact_hash": payload_digest(
                session.replay_artifact(artifact_id=CANONICAL_DEPLOYMENT_ID)
            ),
            "scope": "one-reproduced-setup-deployment-prefix-not-exhaustive-reachability",
            "episode_end": "truncated",
            "stop_reason": "before-redeploy",
            "source_obligations": {
                "rules": "configured-11e-setup-secondary-reserve-deployment-validation",
                "mission": "July-2026-Event-Companion-v1.1-mission-and-scoring-identities",
                "geometry": (
                    "October-2026-v1.3-layout-with-project-modeling-and-legacy-model-volumes"
                ),
                "scoring": "fixed-secondary-selection-only-no-scoring-window-or-outcome-label",
                "authority": "ordinary-viewer-submission-engine-acceptance-and-strict-replay",
            },
            "fixture_exceptions": [
                "synthetic-phase9a-core-catalog-not-an-official-faction-roster",
                "allow_legacy_non_strict_rosters-true",
                "setup-smoke-REDEPLOY-and-SCOUTS-overlay-retained-not-exercised",
                "legacy-model-volumes-not-source-measured-model-heights",
                "one-explicit-300-point-reserve-value-not-a-complete-points-roster",
                "public-fixed-test-private-rng-seed-not-a-competitive-game-seed",
            ],
            "unsupported_by_recipe": [
                "redeploy-and-scout-movement",
                "reserves-and-deep-strike-arrival",
                "tactical-secondary-draws",
                "attachments-and-transports",
                "battle-movement-shooting-charge-fight-reactions-and-scoring",
            ],
            "pending_stage2_evidence": [
                "candidate-reference-alternative-coverage",
                "component-costs",
            ],
            "qualification": "prefix-only-no-full-game-learning-or-performance-certification",
        }
        result = object.__new__(cls)
        object.__setattr__(result, "_payload_json", canonical_json(validate_json_value(payload)))
        return result

    @classmethod
    def from_payload(
        cls, payload: object, *, session: LocalGameSession
    ) -> CanonicalDeploymentAdmission:
        expected = cls.from_session(session)
        _require(
            canonical_json(validate_json_value(payload)) == expected._payload_json,
            "Canonical deployment admission payload drifted.",
        )
        return expected

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], json.loads(self._payload_json))

    @property
    def content_hash(self) -> str:
        return payload_digest(self.to_payload())
