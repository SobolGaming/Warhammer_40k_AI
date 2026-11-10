"""One reachable preservation prefix; tactical reference qualification stays open."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import cast

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.canonical_deployment import (
    _STEPS,  # pyright: ignore[reportPrivateUsage]
    CANONICAL_DEPLOYMENT_CONFIG_HASH,
    CanonicalDeploymentAdmission,
    canonical_deployment_config,
    reproduce_canonical_deployment,
)
from warhammer40k_core.ai.finite_candidates import FiniteCandidateSet
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyRoute, payload_digest
from warhammer40k_core.ai.training_admission import TrainingAdmissionError, VerifiedEpisodeOrigin
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.phase import LifecycleStatusKind

PRESERVE_SCENARIO_ID = "canonical-preserve-prefix-v1"
PRESERVE_SCENARIO_SCHEMA = "preserve-scenario-admission-v1"
SCREEN_UNIT_ID = "army-alpha:scout-redeploy-unit"
EXPLOITER_UNIT_ID = "army-alpha:deep-strike-unit"
OPPONENT_UNIT_ID = "army-beta:scout-redeploy-unit"


@dataclass(frozen=True, slots=True)
class _Choice:
    route: PolicyRoute
    option_id: str


_CONTINUATION = (
    *(
        _Choice(PolicyRoute(actor, decision, "setup", step, None, None), option)
        for decision, step, option in (
            ("select_redeploy_unit", "redeploy_units", "complete_redeploys"),
            ("select_prebattle_action", "resolve_prebattle_actions", "complete_prebattle_actions"),
        )
        for actor in ("player-a", "player-b")
    ),
    _Choice(
        PolicyRoute("player-a", "select_movement_unit", "battle", None, "movement", None),
        SCREEN_UNIT_ID,
    ),
    _Choice(
        PolicyRoute("player-a", "select_movement_action", "battle", None, "movement", None),
        "remain_stationary",
    ),
)

# These are obligations of the proposed useful-reference experiment, not claims
# that this prefix exercises them or that an engine subsystem is unsupported.
_TACTICAL_GAPS = (
    "witnessed-screen-or-exposure-movement-alternative",
    "opponent-threat-reachability-and-attack-resolution",
    "separate-exploiter-follow-through",
    "later-scoring-or-attack-benefit-compared-with-preservation",
    "matched-continuations-and-local-target-with-declared-horizon",
)
_OBSERVED_MECHANICS = (
    "ordinary-setup-deployment",
    "decline-redeploy-and-scouts",
    "first-command-boundary",
    "select-screen-candidate-and-remain-stationary",
)


def preserve_scenario_definition() -> dict[str, JsonValue]:
    return cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "scenario_id": PRESERVE_SCENARIO_ID,
                "configuration_hash": CANONICAL_DEPLOYMENT_CONFIG_HASH,
                "deployment_recipe": [asdict(step) for step in _STEPS],
                "continuation": [asdict(choice) for choice in _CONTINUATION],
                "roles": {
                    "screen_candidate": SCREEN_UNIT_ID,
                    "exploiter_candidate": EXPLOITER_UNIT_ID,
                    "opponent_candidate": OPPONENT_UNIT_ID,
                },
                "role_meaning": "design-roles-not-demonstrated-screen-exploiter-or-threat",
                "required_prefix_mechanics": list(_OBSERVED_MECHANICS),
                "required_tactical_mechanics": list(_TACTICAL_GAPS),
                "pending_tactical_route_obligations": [
                    {
                        "unit_instance_id": unit,
                        "route": asdict(route),
                        "status": "unobserved",
                    }
                    for unit, route in (
                        (
                            SCREEN_UNIT_ID,
                            PolicyRoute(
                                "player-a",
                                "submit_movement_proposal",
                                "battle",
                                None,
                                "movement",
                                "normal_move",
                            ),
                        ),
                        (
                            EXPLOITER_UNIT_ID,
                            PolicyRoute(
                                "player-a",
                                "submit_movement_proposal",
                                "battle",
                                None,
                                "movement",
                                "normal_move",
                            ),
                        ),
                        (
                            OPPONENT_UNIT_ID,
                            PolicyRoute(
                                "player-b",
                                "select_shooting_unit",
                                "battle",
                                None,
                                "shooting",
                                None,
                            ),
                        ),
                    )
                ],
                "pending_route_scope": "minimum-continuation-obligations-not-complete-battle-plan",
                "scoring_obligation": "later-engine-scoring-boundary-after-E-follow-through",
                "endpoint": "round-one-player-a-movement-after-S-remains-stationary",
                "reference_target": None,
                "qualification": "reachable-preserve-feasibility-prefix-not-useful-reference",
            }
        ),
    )


PRESERVE_SCENARIO_DEFINITION_HASH = (
    "fc3cbc047c8f63aeaf39322456e7c7f75927c8de170911a0c8456a06b15f9043"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TrainingAdmissionError(message)


def _require_definition() -> dict[str, JsonValue]:
    definition = preserve_scenario_definition()
    _require(
        payload_digest(definition) == PRESERVE_SCENARIO_DEFINITION_HASH,
        "Preserve scenario definition drifted; review and version the fixture.",
    )
    return definition


def _continue_preservation(
    session: LocalGameSession, *, choices: tuple[_Choice, ...] = _CONTINUATION
) -> list[dict[str, JsonValue]]:
    trace: list[dict[str, JsonValue]] = []
    for index, choice in enumerate(choices):
        context = PlayerDecisionContext.from_view(
            session.view(viewer_player_id=choice.route.actor_id), choice_seed=7
        )
        _require(context.route == choice.route, "Preserve scenario route order drifted.")
        candidates = FiniteCandidateSet.from_context(context)
        _require(
            choice.option_id in candidates.candidate_ids,
            "Preserve scenario finite option is unavailable.",
        )
        before_count = session.decision_record_count()
        before_geometry = payload_digest(context.observation["battlefield_state"])
        status = session.submit_viewer_option(
            viewer=ViewerContext.for_player(choice.route.actor_id),
            request_id=context.request["request_id"],
            option_id=choice.option_id,
            result_id=f"{PRESERVE_SCENARIO_ID}:{index}",
        )
        if status.status_kind is LifecycleStatusKind.ADVANCED:
            status = session.advance_until_decision_or_terminal()
        _require(
            status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
            and session.decision_record_count() == before_count + 1,
            "Preserve scenario ordinary continuation was not accepted.",
        )
        _require(
            payload_digest(
                session.view(viewer_player_id=choice.route.actor_id)["battlefield_state"]
            )
            == before_geometry,
            "Preserve scenario unexpectedly changed battlefield placement.",
        )
        trace.append(
            cast(
                dict[str, JsonValue],
                validate_json_value(
                    {
                        "index": before_count,
                        "route": asdict(context.route),
                        "record": session.lifecycle.decision_controller.records[-1].to_payload(),
                        "observation_hash": context.observation_hash,
                        "finite_candidates": candidates.to_payload(),
                        "selected_candidate_id": choice.option_id,
                        "candidate_scope": "enumerated-options-only-no-continuation-value",
                    }
                ),
            )
        )
    return trace


def reproduce_preserve_scenario() -> LocalGameSession:
    """Execute the frozen prefix exclusively through ordinary viewer submissions."""
    _require_definition()
    session, _ = reproduce_canonical_deployment()
    _continue_preservation(session)
    return session


@dataclass(frozen=True, slots=True, init=False)
class PreserveScenarioAdmission:
    """Closed operator receipt: reachability admitted, useful-reference status gap."""

    _payload_json: str

    def __init__(self) -> None:
        raise TrainingAdmissionError("Admit the preserve scenario through its ordinary session.")

    @classmethod
    def from_session(cls, session: LocalGameSession) -> PreserveScenarioAdmission:
        definition = _require_definition()
        _require(type(session) is LocalGameSession, "Preserve admission requires a local session.")
        _require(
            payload_digest(session.lifecycle.config.to_payload())
            == CANONICAL_DEPLOYMENT_CONFIG_HASH,
            "Session is outside the frozen preserve configuration.",
        )
        _require(session.decision_record_count() == 17, "Preserve scenario requires 17 records.")
        expected, _ = reproduce_canonical_deployment()
        deployment = CanonicalDeploymentAdmission.from_session(expected).to_payload()
        continuation = _continue_preservation(expected)
        _require(
            canonical_json(session.to_persistence_payload())
            == canonical_json(expected.to_persistence_payload()),
            "Session differs from the exact preserve trace or endpoint.",
        )
        origin = VerifiedEpisodeOrigin.from_session(session, config=canonical_deployment_config())
        trace = cast(list[dict[str, JsonValue]], deployment["accepted_trace"]) + continuation
        required = list(
            dict.fromkeys((*[step.route for step in _STEPS], *[c.route for c in _CONTINUATION]))
        )
        observed = [row["route"] for row in trace]
        events = session.lifecycle.decision_controller.event_log.records
        activation = [
            event.to_payload()
            for event in events
            if event.event_type == "movement_activation_completed"
            and isinstance(event.payload, dict)
            and event.payload.get("unit_instance_id") == SCREEN_UNIT_ID
            and event.payload.get("movement_phase_action") == "remain_stationary"
        ]
        _require(len(activation) == 1, "Preserve scenario activation evidence drifted.")
        boundary_events = [
            event.to_payload()
            for event in events
            if event.event_type
            in (
                "setup_completion_gate_passed",
                "command_phase_scoring_hooks_resolved",
                "movement_phase_entered",
            )
        ]
        _require(len(boundary_events) == 3, "Preserve scenario boundary evidence drifted.")
        endpoint = PlayerDecisionContext.from_view(
            session.view(viewer_player_id="player-a"), choice_seed=7
        )
        _require(
            endpoint.route == _CONTINUATION[-2].route
            and SCREEN_UNIT_ID
            not in {option["option_id"] for option in endpoint.request["options"]}
            and EXPLOITER_UNIT_ID
            in {option["option_id"] for option in endpoint.request["options"]},
            "Preserve scenario pending continuation drifted.",
        )
        payload = {
            "schema_version": PRESERVE_SCENARIO_SCHEMA,
            "definition": definition,
            "definition_hash": PRESERVE_SCENARIO_DEFINITION_HASH,
            "configuration": canonical_deployment_config().to_payload(),
            "origin": origin.to_payload(),
            "accepted_trace": trace,
            "required_routes": [asdict(route) for route in required],
            "observed_routes": [asdict(route) for route in required if asdict(route) in observed],
            "unobserved_required_routes": [
                asdict(route) for route in required if asdict(route) not in observed
            ],
            "endpoint_route": asdict(endpoint.route),
            "observed_mechanics": list(_OBSERVED_MECHANICS),
            "unobserved_required_tactical_mechanics": list(_TACTICAL_GAPS),
            "mechanic_evidence": {"boundary_events": boundary_events, "activation": activation},
            "fixture_exceptions": [
                (
                    "setup-smoke-overlay-decline-only-no-redeploy-or-scout-movement"
                    if item == "setup-smoke-REDEPLOY-and-SCOUTS-overlay-retained-not-exercised"
                    else item
                )
                for item in cast(list[str], deployment["fixture_exceptions"])
            ],
            "source_obligations": {
                "deployment": deployment["source_obligations"],
                "movement": "gw-11e-core-rules:movement-phase:move-units-step",
                "scoring": "first-command-boundary-only-no-later-benefit-or-outcome-label",
            },
            "replay_artifact_hash": payload_digest(
                session.replay_artifact(artifact_id=PRESERVE_SCENARIO_ID)
            ),
            "episode_end": "truncated",
            "useful_reference_status": "scoped_gap",
            "gap_meaning": "unmeasured-continuations-not-an-engine-unsupported-verdict",
            "eligible_for_learning": False,
            "reference_target": None,
            "pending_stage2_evidence": [
                "useful-screen-versus-preserve-reference-and-candidate-coverage",
                "scenario-component-costs",
                "broader-workload-qualification",
            ],
        }
        result = object.__new__(cls)
        object.__setattr__(result, "_payload_json", canonical_json(validate_json_value(payload)))
        return result

    @classmethod
    def from_payload(
        cls, payload: object, *, session: LocalGameSession
    ) -> PreserveScenarioAdmission:
        expected = cls.from_session(session)
        _require(
            canonical_json(validate_json_value(payload)) == expected._payload_json,
            "Preserve scenario admission payload drifted.",
        )
        return expected

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], json.loads(self._payload_json))

    @property
    def content_hash(self) -> str:
        return payload_digest(self.to_payload())
