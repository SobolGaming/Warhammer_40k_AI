"""Matched movement feasibility and a rejected opposing shot, without value labels."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import cast

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.canonical_deployment import (
    _STEPS,  # pyright: ignore[reportPrivateUsage]
    CANONICAL_DEPLOYMENT_CONFIG_HASH,
    canonical_deployment_config,
    reproduce_canonical_deployment,
)
from warhammer40k_core.ai.finite_candidates import FiniteCandidateSet
from warhammer40k_core.ai.normal_move_scenario import (
    NORMAL_MOVE_SCENARIO_DEFINITION_HASH,
    _continue_normal_move,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyRoute, payload_digest
from warhammer40k_core.ai.preserve_scenario import (
    _CONTINUATION,  # pyright: ignore[reportPrivateUsage]
    EXPLOITER_UNIT_ID,
    OPPONENT_UNIT_ID,
    PRESERVE_SCENARIO_DEFINITION_HASH,
    _continue_preservation,  # pyright: ignore[reportPrivateUsage]
    _require,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.ai.training_admission import TrainingAdmissionError, VerifiedEpisodeOrigin
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.movement_proposals import MovementProposalPayload, ProposalKind
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.geometry.pathing import ModelPathEndpoint, PathWitness
from warhammer40k_core.geometry.pose import Pose, PosePayload

FOLLOWTHROUGH_ID = "canonical-paired-followthrough-v1"
FOLLOWTHROUGH_SCHEMA = "paired-followthrough-admission-v1"
_SELECT = PolicyRoute("player-a", "select_movement_unit", "battle", None, "movement", None)
_ACTION = PolicyRoute("player-a", "select_movement_action", "battle", None, "movement", None)
_MOVE = PolicyRoute(
    "player-a", "submit_movement_proposal", "battle", None, "movement", "normal_move"
)
_OPPONENT = PolicyRoute(
    "player-b",
    "submit_stratagem_target_proposal",
    "battle",
    None,
    "movement",
    "stratagem_target_binding",
)
_VEHICLE = "army-alpha:strategic-reserve-unit"
_GAPS = (
    "demonstrated-screen-or-exposure",
    "opponent-attack-resolution",
    "exploiter-benefit-after-opponent-response",
    "matched-later-outcomes-with-declared-local-horizon",
    "timing-and-cooperation-controls",
    "useful-candidate-coverage-and-scenario-costs",
)


def followthrough_definition() -> dict[str, JsonValue]:
    return cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "scenario_id": FOLLOWTHROUGH_ID,
                "configuration_hash": CANONICAL_DEPLOYMENT_CONFIG_HASH,
                "stationary_definition_hash": PRESERVE_SCENARIO_DEFINITION_HASH,
                "normal_move_definition_hash": NORMAL_MOVE_SCENARIO_DEFINITION_HASH,
                "common_prefix_record_count": 15,
                "continuation": [
                    {"route": asdict(_SELECT), "option_id": EXPLOITER_UNIT_ID},
                    {"route": asdict(_ACTION), "option_id": "normal_move"},
                    {
                        "route": asdict(_MOVE),
                        "unit_instance_id": EXPLOITER_UNIT_ID,
                        "model_count": 3,
                        "translation_inches": {"x": -1.0, "y": 0.0, "z": 0.0},
                        "path": "straight-line-observed-model-order-unchanged-facing",
                    },
                    {"route": asdict(_SELECT), "option_id": _VEHICLE},
                    {"route": asdict(_ACTION), "option_id": "remain_stationary"},
                ],
                "endpoint_route": asdict(_OPPONENT),
                "endpoint": "round-one-A-end-movement-before-B-overwatch-response",
                "opponent_probe": {
                    "unit_instance_id": OPPONENT_UNIT_ID,
                    "stratagem_id": "fire-overwatch",
                    "submission": "ordinary-viewer-target-binding-on-independent-fork",
                    "required_invalid_reason": "fire_overwatch_no_legal_shooting_declaration",
                },
                "qualification": "paired-movement-and-negative-shot-feasibility-not-tactical-value",
                "remaining_tactical_gaps": list(_GAPS),
            }
        ),
    )


FOLLOWTHROUGH_DEFINITION_HASH = "ab9d979f84349259decf176864e7e35a0ddb46ca21fa72ab7bebd72e3ed2a9d9"


def _definition() -> dict[str, JsonValue]:
    result = followthrough_definition()
    _require(
        payload_digest(result) == FOLLOWTHROUGH_DEFINITION_HASH,
        "Followthrough definition drifted; review and version the fixture.",
    )
    return result


def _exploiter_proposal(context: PlayerDecisionContext) -> MovementProposalPayload:
    _require(context.route == _MOVE, "Followthrough movement route drifted.")
    pending = cast(dict[str, JsonValue], context.observation["pending_proposal"])
    _require(pending["unit_instance_id"] == EXPLOITER_UNIT_ID, "Followthrough unit drifted.")
    battlefield = cast(dict[str, JsonValue], context.observation["battlefield_state"])
    endpoints: list[ModelPathEndpoint] = []
    for army in cast(list[dict[str, JsonValue]], battlefield["placed_armies"]):
        for unit in cast(list[dict[str, JsonValue]], army["unit_placements"]):
            if unit["unit_instance_id"] == EXPLOITER_UNIT_ID:
                for model in cast(list[dict[str, JsonValue]], unit["model_placements"]):
                    start = Pose.from_payload(cast(PosePayload, model["pose"]))
                    end = Pose.at(
                        start.position.x - 1.0,
                        start.position.y,
                        start.position.z,
                        start.facing.degrees,
                    )
                    endpoints.append((cast(str, model["model_instance_id"]), start, end))
    _require(len(endpoints) == 3, "Followthrough formation drifted.")
    return MovementProposalPayload(
        proposal_request_id=cast(str, pending["request_id"]),
        proposal_kind=ProposalKind.NORMAL_MOVE,
        unit_instance_id=EXPLOITER_UNIT_ID,
        movement_phase_action="normal_move",
        movement_mode="normal",
        witness=PathWitness.for_straight_line_endpoints(tuple(endpoints)),
    )


def _continue(session: LocalGameSession) -> list[dict[str, JsonValue]]:
    trace: list[dict[str, JsonValue]] = []
    for route, option in (
        (_SELECT, EXPLOITER_UNIT_ID),
        (_ACTION, "normal_move"),
        (_MOVE, None),
        (_SELECT, _VEHICLE),
        (_ACTION, "remain_stationary"),
    ):
        context = PlayerDecisionContext.from_view(
            session.view(viewer_player_id="player-a"), choice_seed=7
        )
        _require(context.route == route, "Followthrough continuation route drifted.")
        index = session.decision_record_count()
        candidates = FiniteCandidateSet.from_context(context) if option is not None else None
        proposal = _exploiter_proposal(context) if option is None else None
        if option is not None:
            assert candidates is not None
            _require(option in candidates.candidate_ids, "Followthrough option unavailable.")
            status = session.submit_viewer_option(
                viewer=ViewerContext.for_player("player-a"),
                request_id=context.request["request_id"],
                option_id=option,
                result_id=f"{FOLLOWTHROUGH_ID}:{index}",
            )
        else:
            assert proposal is not None
            status = session.submit_viewer_parameterized_payload(
                viewer=ViewerContext.for_player("player-a"),
                request_id=context.request["request_id"],
                payload=validate_json_value(proposal.to_payload()),
                result_id=f"{FOLLOWTHROUGH_ID}:{index}",
            )
        if status.status_kind is LifecycleStatusKind.ADVANCED:
            status = session.advance_until_decision_or_terminal()
        _require(
            status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
            and session.decision_record_count() == index + 1,
            "Followthrough ordinary decision was not accepted.",
        )
        trace.append(
            cast(
                dict[str, JsonValue],
                validate_json_value(
                    {
                        "index": index,
                        "route": asdict(context.route),
                        "observation_hash": context.observation_hash,
                        "record": session.lifecycle.decision_controller.records[-1].to_payload(),
                        "finite_candidates": None
                        if candidates is None
                        else candidates.to_payload(),
                        "selected_candidate_id": option,
                        "proposal": None if proposal is None else proposal.to_payload(),
                        "candidate_scope": "fixed-feasibility-recipe-no-coverage-or-value",
                    }
                ),
            )
        )
    return trace


def _reproduce() -> tuple[tuple[LocalGameSession, list[dict[str, JsonValue]]], ...]:
    branches: list[tuple[LocalGameSession, list[dict[str, JsonValue]]]] = []
    for moved in (False, True):
        session, report = reproduce_canonical_deployment()
        trace = cast(
            list[dict[str, JsonValue]],
            [
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
        )
        if moved:
            continuation, _ = _continue_normal_move(session)
        else:
            continuation = _continue_preservation(session)
        trace.extend(continuation)
        trace.extend(_continue(session))
        branches.append((session, trace))
    return tuple(branches)


def reproduce_followthrough_pair() -> tuple[LocalGameSession, LocalGameSession]:
    """Reach both endpoints through their unchanged original branch and five choices."""
    _definition()
    stationary, moved = _reproduce()
    return stationary[0], moved[0]


def _opponent_probe(session: LocalGameSession) -> dict[str, JsonValue]:
    clone = session.fork()
    context = PlayerDecisionContext.from_view(
        clone.view(viewer_player_id="player-b"), choice_seed=7
    )
    _require(context.route == _OPPONENT, "Followthrough opposing reaction route drifted.")
    pending = cast(dict[str, JsonValue], context.observation["pending_proposal"])
    catalog = cast(dict[str, JsonValue], pending["catalog_record"])
    definition = cast(dict[str, JsonValue], catalog["definition"])
    _require(definition["stratagem_id"] == "fire-overwatch", "Opposing window drifted.")
    proposal = {
        key: pending[key]
        for key in ("proposal_kind", "context", "catalog_record", "effect_selection")
    }
    proposal["target_binding"] = {
        "target_kind": "friendly_unit",
        "target_player_id": "player-b",
        "target_unit_instance_id": OPPONENT_UNIT_ID,
    }
    before = payload_digest(clone.to_persistence_payload())
    records = clone.decision_record_count()
    events = len(clone.lifecycle.decision_controller.event_log.records)
    status = clone.submit_viewer_parameterized_payload(
        viewer=ViewerContext.for_player("player-b"),
        request_id=context.request["request_id"],
        payload=validate_json_value({"proposal": proposal}),
        result_id=f"{FOLLOWTHROUGH_ID}:opponent-probe",
    )
    _require(
        status.status_kind is LifecycleStatusKind.INVALID
        and status.payload == {"invalid_reason": "fire_overwatch_no_legal_shooting_declaration"},
        "Followthrough opposing shot diagnostic drifted; review the fixture.",
    )
    after = payload_digest(clone.to_persistence_payload())
    record_delta = clone.decision_record_count() - records
    event_delta = len(clone.lifecycle.decision_controller.event_log.records) - events
    _require(
        before == after and record_delta == event_delta == 0,
        "Rejected opposing shot changed its checkpoint.",
    )
    return cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "route": asdict(context.route),
                "request_hash": payload_digest(context.request),
                "submitted_payload": {"proposal": proposal},
                "status": status.status_kind.value,
                "message": status.message,
                "diagnostic": status.payload,
                "before_checkpoint_hash": before,
                "after_checkpoint_hash": after,
                "checkpoint_unchanged": before == after,
                "accepted_record_count_delta": record_delta,
                "event_count_delta": event_delta,
                "scope": "one-fixed-shooter-at-this-window-not-global-threat-unreachability",
            }
        ),
    )


@dataclass(frozen=True, slots=True, init=False)
class FollowthroughPairAdmission:
    """Closed operator evidence for two reachable endpoints and negative shot probes."""

    _payload_json: str

    def __init__(self) -> None:
        raise TrainingAdmissionError("Admit the followthrough pair through its ordinary sessions.")

    @classmethod
    def from_sessions(
        cls, stationary: LocalGameSession, moved: LocalGameSession
    ) -> FollowthroughPairAdmission:
        definition = _definition()
        sessions = (stationary, moved)
        _require(
            all(type(session) is LocalGameSession for session in sessions),
            "Followthrough admission requires local sessions.",
        )
        _require(
            all(
                payload_digest(session.lifecycle.config.to_payload())
                == CANONICAL_DEPLOYMENT_CONFIG_HASH
                for session in sessions
            ),
            "Session is outside the frozen followthrough configuration.",
        )
        _require(
            tuple(session.decision_record_count() for session in sessions) == (22, 23),
            "Followthrough pair requires 22 and 23 records in branch order.",
        )
        expected = _reproduce()
        branches = {}
        common_records = [
            record.to_payload() for record in stationary.lifecycle.decision_controller.records[:15]
        ]
        for name, session, (fresh, trace) in zip(
            ("stationary", "normal_move"), sessions, expected, strict=True
        ):
            _require(
                canonical_json(session.to_persistence_payload())
                == canonical_json(fresh.to_persistence_payload()),
                "Session differs from the exact followthrough trace or endpoint.",
            )
            _require(
                [
                    record.to_payload()
                    for record in session.lifecycle.decision_controller.records[:15]
                ]
                == common_records,
                "Followthrough common accepted prefix drifted.",
            )
            origin = VerifiedEpisodeOrigin.from_session(
                session, config=canonical_deployment_config()
            )
            required = list(
                dict.fromkeys(
                    (
                        *[step.route for step in _STEPS],
                        *[choice.route for choice in _CONTINUATION],
                        _MOVE,
                    )
                )
            )
            observed = [row["route"] for row in trace]
            events = session.lifecycle.decision_controller.event_log.records
            branches[name] = {
                "origin": origin.to_payload(),
                "common_prefix_records_hash": payload_digest(common_records),
                "accepted_trace": trace,
                "accepted_records": [
                    record.to_payload() for record in session.lifecycle.decision_controller.records
                ],
                "required_routes": [asdict(route) for route in required],
                "observed_routes": [
                    asdict(route) for route in required if asdict(route) in observed
                ],
                "unobserved_required_routes": [
                    asdict(route) for route in required if asdict(route) not in observed
                ],
                "endpoint_route": asdict(_OPPONENT),
                "movement_activations": [
                    event.to_payload()
                    for event in events
                    if event.event_type == "movement_activation_completed"
                ],
                "opponent_probe": _opponent_probe(session),
                "replay_artifact_hash": payload_digest(
                    session.replay_artifact(artifact_id=f"{FOLLOWTHROUGH_ID}:{name}")
                ),
            }
        payload = {
            "schema_version": FOLLOWTHROUGH_SCHEMA,
            "definition": definition,
            "definition_hash": FOLLOWTHROUGH_DEFINITION_HASH,
            "configuration": canonical_deployment_config().to_payload(),
            "branches": branches,
            "remaining_tactical_gaps": list(_GAPS),
            "source_obligations": {
                "movement": "gw-11e-core-rules:movement-phase:move-units-step",
                "reaction": "gw-11e-core-stratagems:core:fire-overwatch",
                "authority": "ordinary-viewer-submissions-engine-validation-and-exact-replay",
            },
            "fixture_exceptions": [
                "synthetic-phase9a-core-catalog-not-an-official-faction-roster",
                "allow_legacy_non_strict_rosters-true",
                "redeploy-and-scouts-declined-not-exercised",
                "legacy-model-volumes-not-source-measured-model-heights",
                "July-mission-scoring-with-October-layout-geometry",
                "one-explicit-300-point-reserve-value-not-a-complete-points-roster",
                "public-fixed-test-private-rng-seed-not-a-competitive-game-seed",
            ],
            "episode_end": "truncated",
            "useful_reference_status": "scoped_gap",
            "reference_target": None,
            "eligible_for_learning": False,
        }
        result = object.__new__(cls)
        object.__setattr__(result, "_payload_json", canonical_json(validate_json_value(payload)))
        return result

    @classmethod
    def from_payload(
        cls, payload: object, stationary: LocalGameSession, moved: LocalGameSession
    ) -> FollowthroughPairAdmission:
        value = validate_json_value(payload)
        _require(
            isinstance(value, dict)
            and value.get("eligible_for_learning") is False
            and value.get("reference_target") is None
            and value.get("useful_reference_status") == "scoped_gap",
            "Followthrough admission payload drifted.",
        )
        expected = cls.from_sessions(stationary, moved)
        _require(
            canonical_json(value) == expected._payload_json,
            "Followthrough admission payload drifted.",
        )
        return expected

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], json.loads(self._payload_json))

    @property
    def content_hash(self) -> str:
        return payload_digest(self.to_payload())
