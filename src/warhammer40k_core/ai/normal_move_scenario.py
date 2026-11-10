"""One witnessed legal alternative to preservation, without tactical qualification."""

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
from warhammer40k_core.ai.preserve_scenario import (
    _CONTINUATION,  # pyright: ignore[reportPrivateUsage]
    EXPLOITER_UNIT_ID,
    PRESERVE_SCENARIO_DEFINITION_HASH,
    SCREEN_UNIT_ID,
    _continue_preservation,  # pyright: ignore[reportPrivateUsage]
    _require,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.ai.preserve_scenario import (
    _require_definition as _require_preserve_definition,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.ai.training_admission import TrainingAdmissionError, VerifiedEpisodeOrigin
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.movement_proposals import MovementProposalPayload, ProposalKind
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.geometry.pathing import ModelPathEndpoint, PathWitness
from warhammer40k_core.geometry.pose import Pose, PosePayload

NORMAL_MOVE_SCENARIO_ID = "canonical-witnessed-normal-move-v1"
NORMAL_MOVE_SCENARIO_SCHEMA = "normal-move-scenario-admission-v1"
_SELECT_UNIT = PolicyRoute("player-a", "select_movement_unit", "battle", None, "movement", None)
_SELECT_ACTION = PolicyRoute("player-a", "select_movement_action", "battle", None, "movement", None)
_PROPOSE = PolicyRoute(
    "player-a", "submit_movement_proposal", "battle", None, "movement", "normal_move"
)


def normal_move_scenario_definition() -> dict[str, JsonValue]:
    preserve = _require_preserve_definition()
    return cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "scenario_id": NORMAL_MOVE_SCENARIO_ID,
                "configuration_hash": CANONICAL_DEPLOYMENT_CONFIG_HASH,
                "preservation_definition_hash": PRESERVE_SCENARIO_DEFINITION_HASH,
                "common_prefix_record_count": 15,
                "deployment_recipe": preserve["deployment_recipe"],
                "common_continuation": [asdict(choice) for choice in _CONTINUATION[:4]],
                "choices": [
                    {"route": asdict(_SELECT_UNIT), "option_id": SCREEN_UNIT_ID},
                    {"route": asdict(_SELECT_ACTION), "option_id": "normal_move"},
                ],
                "proposal_route": asdict(_PROPOSE),
                "witness_recipe": {
                    "translation_inches": {"x": -1.0, "y": 0.0, "z": 0.0},
                    "path": "straight-line-from-each-observed-model-pose",
                    "model_order": "observed-model-placement-order",
                    "facing": "unchanged",
                    "model_count": 5,
                },
                "roles": preserve["roles"],
                "role_meaning": preserve["role_meaning"],
                "required_prefix_mechanics": [
                    "ordinary-setup-deployment",
                    "decline-redeploy-and-scouts",
                    "first-command-boundary",
                    "select-S-and-engine-validate-witnessed-normal-move",
                ],
                "required_tactical_mechanics": preserve["required_tactical_mechanics"],
                "pending_tactical_route_obligations": cast(
                    list[JsonValue], preserve["pending_tactical_route_obligations"]
                )[1:],
                "pending_route_scope": preserve["pending_route_scope"],
                "scoring_obligation": preserve["scoring_obligation"],
                "endpoint": "round-one-player-a-movement-after-S-normal-move",
                "reference_target": None,
                "qualification": "reachable-normal-move-feasibility-prefix-not-useful-reference",
            }
        ),
    )


NORMAL_MOVE_SCENARIO_DEFINITION_HASH = (
    "12c50a37c861dbf138e8e89e90fbdd1931283d31ccff3442872582846eaa7c81"
)


def _require_definition() -> dict[str, JsonValue]:
    definition = normal_move_scenario_definition()
    _require(
        payload_digest(definition) == NORMAL_MOVE_SCENARIO_DEFINITION_HASH,
        "Normal move scenario definition drifted; review and version the fixture.",
    )
    return definition


def _proposal(context: PlayerDecisionContext) -> MovementProposalPayload:
    """Build only the frozen witness from the actor's projected model poses."""
    _require(context.route == _PROPOSE, "Normal move scenario proposal route drifted.")
    pending = cast(dict[str, JsonValue], context.observation["pending_proposal"])
    _require(pending["unit_instance_id"] == SCREEN_UNIT_ID, "Normal move unit drifted.")
    battlefield = cast(dict[str, JsonValue], context.observation["battlefield_state"])
    endpoints: list[ModelPathEndpoint] = []
    for army in cast(list[dict[str, JsonValue]], battlefield["placed_armies"]):
        for unit in cast(list[dict[str, JsonValue]], army["unit_placements"]):
            if unit["unit_instance_id"] != SCREEN_UNIT_ID:
                continue
            for model in cast(list[dict[str, JsonValue]], unit["model_placements"]):
                start = Pose.from_payload(cast(PosePayload, model["pose"]))
                end = Pose.at(
                    start.position.x - 1.0,
                    start.position.y,
                    start.position.z,
                    start.facing.degrees,
                )
                endpoints.append((cast(str, model["model_instance_id"]), start, end))
    _require(len(endpoints) == 5, "Normal move scenario formation drifted.")
    return MovementProposalPayload(
        proposal_request_id=cast(str, pending["request_id"]),
        proposal_kind=ProposalKind.NORMAL_MOVE,
        unit_instance_id=SCREEN_UNIT_ID,
        movement_phase_action="normal_move",
        movement_mode="normal",
        witness=PathWitness.for_straight_line_endpoints(tuple(endpoints)),
    )


def _continue_normal_move(
    session: LocalGameSession,
) -> tuple[list[dict[str, JsonValue]], str]:
    trace = _continue_preservation(session, choices=_CONTINUATION[:4])
    _require(session.decision_record_count() == 15, "Normal move common prefix drifted.")
    prefix_hash = payload_digest(session.to_persistence_payload())
    for route, option in ((_SELECT_UNIT, SCREEN_UNIT_ID), (_SELECT_ACTION, "normal_move")):
        context = PlayerDecisionContext.from_view(
            session.view(viewer_player_id="player-a"), choice_seed=7
        )
        _require(context.route == route, "Normal move scenario finite route drifted.")
        candidates = FiniteCandidateSet.from_context(context)
        _require(option in candidates.candidate_ids, "Normal move finite choice unavailable.")
        index = session.decision_record_count()
        status = session.submit_viewer_option(
            viewer=ViewerContext.for_player("player-a"),
            request_id=context.request["request_id"],
            option_id=option,
            result_id=f"{NORMAL_MOVE_SCENARIO_ID}:{index}",
        )
        _require(
            status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
            and session.decision_record_count() == index + 1,
            "Normal move finite choice was not accepted.",
        )
        trace.append(
            cast(
                dict[str, JsonValue],
                validate_json_value(
                    {
                        "index": index,
                        "route": asdict(context.route),
                        "record": session.lifecycle.decision_controller.records[-1].to_payload(),
                        "observation_hash": context.observation_hash,
                        "finite_candidates": candidates.to_payload(),
                        "selected_candidate_id": option,
                        "candidate_scope": "enumerated-options-only-no-continuation-value",
                    }
                ),
            )
        )
    context = PlayerDecisionContext.from_view(
        session.view(viewer_player_id="player-a"), choice_seed=7
    )
    proposal = _proposal(context)
    status = session.submit_viewer_parameterized_payload(
        viewer=ViewerContext.for_player("player-a"),
        request_id=context.request["request_id"],
        payload=validate_json_value(proposal.to_payload()),
        result_id=f"{NORMAL_MOVE_SCENARIO_ID}:17",
    )
    if status.status_kind is LifecycleStatusKind.ADVANCED:
        status = session.advance_until_decision_or_terminal()
    _require(
        status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
        and session.decision_record_count() == 18,
        "Normal move witnessed proposal was not engine-accepted.",
    )
    trace.append(
        cast(
            dict[str, JsonValue],
            validate_json_value(
                {
                    "index": 17,
                    "route": asdict(context.route),
                    "record": session.lifecycle.decision_controller.records[-1].to_payload(),
                    "observation_hash": context.observation_hash,
                    "proposal": proposal.to_payload(),
                    "candidate_scope": "one-fixed-witness-no-alternative-coverage-or-value",
                }
            ),
        )
    )
    return trace, prefix_hash


def reproduce_normal_move_scenario() -> LocalGameSession:
    """Execute the frozen alternative through ordinary finite and proposal submissions."""
    _require_definition()
    session, _ = reproduce_canonical_deployment()
    _continue_normal_move(session)
    return session


@dataclass(frozen=True, slots=True, init=False)
class NormalMoveScenarioAdmission:
    """Closed operator receipt for one legal movement, retaining all tactical gaps."""

    _payload_json: str

    def __init__(self) -> None:
        raise TrainingAdmissionError("Admit the normal move scenario through its ordinary session.")

    @classmethod
    def from_session(cls, session: LocalGameSession) -> NormalMoveScenarioAdmission:
        definition = _require_definition()
        _require(
            type(session) is LocalGameSession, "Normal move admission requires a local session."
        )
        _require(
            payload_digest(session.lifecycle.config.to_payload())
            == CANONICAL_DEPLOYMENT_CONFIG_HASH,
            "Session is outside the frozen normal move configuration.",
        )
        _require(session.decision_record_count() == 18, "Normal move scenario requires 18 records.")
        expected, _ = reproduce_canonical_deployment()
        deployment = CanonicalDeploymentAdmission.from_session(expected).to_payload()
        continuation, prefix_hash = _continue_normal_move(expected)
        _require(
            canonical_json(session.to_persistence_payload())
            == canonical_json(expected.to_persistence_payload()),
            "Session differs from the exact normal move trace or endpoint.",
        )
        origin = VerifiedEpisodeOrigin.from_session(session, config=canonical_deployment_config())
        trace = cast(list[dict[str, JsonValue]], deployment["accepted_trace"]) + continuation
        required = list(
            dict.fromkeys(
                (
                    *[step.route for step in _STEPS],
                    *[choice.route for choice in _CONTINUATION[:4]],
                    _SELECT_UNIT,
                    _SELECT_ACTION,
                    _PROPOSE,
                )
            )
        )
        observed = [row["route"] for row in trace]
        events = session.lifecycle.decision_controller.event_log.records
        activation = [
            event.to_payload()
            for event in events
            if event.event_type == "movement_activation_completed"
            and isinstance(event.payload, dict)
            and event.payload.get("unit_instance_id") == SCREEN_UNIT_ID
            and event.payload.get("movement_phase_action") == "normal_move"
        ]
        _require(len(activation) == 1, "Normal move activation evidence drifted.")
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
        _require(len(boundary_events) == 3, "Normal move boundary evidence drifted.")
        endpoint = PlayerDecisionContext.from_view(
            session.view(viewer_player_id="player-a"), choice_seed=7
        )
        options = {option["option_id"] for option in endpoint.request["options"]}
        _require(
            endpoint.route == _SELECT_UNIT
            and SCREEN_UNIT_ID not in options
            and EXPLOITER_UNIT_ID in options,
            "Normal move pending continuation drifted.",
        )
        payload = {
            "schema_version": NORMAL_MOVE_SCENARIO_SCHEMA,
            "definition": definition,
            "definition_hash": NORMAL_MOVE_SCENARIO_DEFINITION_HASH,
            "configuration": canonical_deployment_config().to_payload(),
            "origin": origin.to_payload(),
            "common_prefix_checkpoint_hash": prefix_hash,
            "accepted_trace": trace,
            "required_routes": [asdict(route) for route in required],
            "observed_routes": [asdict(route) for route in required if asdict(route) in observed],
            "unobserved_required_routes": [
                asdict(route) for route in required if asdict(route) not in observed
            ],
            "endpoint_route": asdict(endpoint.route),
            "observed_mechanics": definition["required_prefix_mechanics"],
            "unobserved_required_tactical_mechanics": definition["required_tactical_mechanics"],
            "mechanic_evidence": {"boundary_events": boundary_events, "activation": activation[0]},
            "fixture_exceptions": deployment["fixture_exceptions"],
            "source_obligations": {
                "deployment": deployment["source_obligations"],
                "movement": "gw-11e-core-rules:movement-phase:move-units-step",
                "scoring": "first-command-boundary-only-no-later-benefit-or-outcome-label",
            },
            "replay_artifact_hash": payload_digest(
                session.replay_artifact(artifact_id=NORMAL_MOVE_SCENARIO_ID)
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
    ) -> NormalMoveScenarioAdmission:
        expected = cls.from_session(session)
        _require(
            canonical_json(validate_json_value(payload)) == expected._payload_json,
            "Normal move scenario admission payload drifted.",
        )
        return expected

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], json.loads(self._payload_json))

    @property
    def content_hash(self) -> str:
        return payload_digest(self.to_payload())
