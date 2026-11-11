"""Export-only matched cooperative attack evidence at one common local horizon."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import cast

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.canonical_deployment import (
    CANONICAL_DEPLOYMENT_CONFIG_HASH,
    canonical_deployment_config,
)
from warhammer40k_core.ai.followthrough_scenario import (
    FOLLOWTHROUGH_DEFINITION_HASH,
    reproduce_followthrough_pair,
)
from warhammer40k_core.ai.opposing_shooter_scenario import (
    _approach,  # pyright: ignore[reportPrivateUsage]
    _finish_attack,  # pyright: ignore[reportPrivateUsage]
    opposing_shooter_definition,
)
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, payload_digest
from warhammer40k_core.ai.preserve_scenario import (
    EXPLOITER_UNIT_ID,
    _require,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.ai.training_admission import TrainingAdmissionError, VerifiedEpisodeOrigin
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

MATCHED_ATTACK_ID = "canonical-matched-opposing-attack-v1"


def matched_attack_definition() -> dict[str, JsonValue]:
    return cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "scenario_id": MATCHED_ATTACK_ID,
                "configuration_hash": CANONICAL_DEPLOYMENT_CONFIG_HASH,
                "historical_followthrough_definition_hash": FOLLOWTHROUGH_DEFINITION_HASH,
                "historical_opposing_shooter_definition_hash": payload_digest(
                    opposing_shooter_definition()
                ),
                "initial_record_counts": [22, 23],
                "continuation": "unchanged-opposing-shooter-approach-and-attack-both-branches",
                "cooperation": (
                    "A-stationary-rounds-two-three-A-skips-shooting-all-movement-reactions-"
                    "and-command-rerolls-declined-fixed-E-model-001-allocation"
                ),
                "timing": (
                    "B-approaches-rounds-one-two-three-skips-first-two-shooting-phases-"
                    "model-003-rifle-at-E-round-three"
                ),
                "horizon": "round-four-player-a-movement-select_movement_unit",
                "comparison": "E-model-wounds-survival-and-poses-at-common-local-horizon",
                "qualification": "one-fixed-seed-cooperative-pair-not-tactical-benefit",
            }
        ),
    )


def _exploiter_state(session: LocalGameSession) -> dict[str, JsonValue]:
    state = session.lifecycle.state
    _require(state is not None, "Matched attack requires a started session.")
    assert state is not None
    group = rules_unit_view_by_id(state=state, unit_instance_id=EXPLOITER_UNIT_ID)
    battlefield = battlefield_scenario_for_state(state=state).battlefield_state.to_payload()
    poses = {
        model["model_instance_id"]: model["pose"]
        for army in battlefield["placed_armies"]
        for unit in army["unit_placements"]
        if unit["unit_instance_id"] == EXPLOITER_UNIT_ID
        for model in unit["model_placements"]
    }
    models = group.own_models
    return cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "unit_instance_id": EXPLOITER_UNIT_ID,
                "alive_model_count": len(group.alive_models()),
                "survives": bool(group.alive_models()),
                "total_wounds_remaining": sum(model.current_wounds for model in models),
                "models": [
                    {
                        "model_instance_id": model.model_instance_id,
                        "starting_wounds": model.initial_wounds,
                        "wounds_remaining": model.current_wounds,
                        "is_alive": model.is_alive,
                        "pose": poses.get(model.model_instance_id),
                    }
                    for model in models
                ],
            }
        ),
    )


def _boundary(session: LocalGameSession) -> dict[str, JsonValue]:
    state = session.lifecycle.state
    assert state is not None
    request = session.lifecycle.pending_decision_request()
    _require(request is not None and request.actor_id is not None, "Matched boundary drifted.")
    assert request is not None
    assert request.actor_id is not None
    context = PlayerDecisionContext.from_view(
        session.view(viewer_player_id=request.actor_id), choice_seed=7
    )
    return cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "route": asdict(context.route),
            }
        ),
    )


def _controlled_choices(trace: list[dict[str, JsonValue]]) -> list[dict[str, JsonValue]]:
    """Compare actual choices and paths without branch-specific request identities."""
    choices: list[dict[str, JsonValue]] = []
    for row in trace:
        route = cast(dict[str, JsonValue], row["route"])
        proposal = row["submitted_payload"]
        semantics: JsonValue = None
        if proposal is not None:
            submitted = cast(dict[str, JsonValue], proposal)
            if route["decision_type"] == "submit_movement_proposal":
                semantics = {
                    key: submitted[key]
                    for key in (
                        "unit_instance_id",
                        "movement_phase_action",
                        "movement_mode",
                        "witness",
                    )
                }
            elif route["decision_type"] == "submit_shooting_declaration":
                semantics = {
                    key: submitted[key]
                    for key in ("battle_round", "unit_instance_id", "declarations")
                }
            else:
                semantics = submitted
        choices.append(
            {"route": route, "option_id": row["selected_option_id"], "proposal": semantics}
        )
    return choices


@dataclass(frozen=True, slots=True, init=False)
class MatchedAttackComparison:
    """Closed report constructed only from reproduced ordinary sessions; no importer."""

    _payload_json: str

    def __init__(self) -> None:
        raise TrainingAdmissionError("Compare matched attacks through exact ordinary sessions.")

    @classmethod
    def from_sessions(
        cls, stationary: LocalGameSession, moved: LocalGameSession
    ) -> MatchedAttackComparison:
        sessions = (stationary, moved)
        _require(
            all(type(item) is LocalGameSession for item in sessions),
            "Matched attack requires local sessions.",
        )
        _require(
            all(
                payload_digest(item.lifecycle.config.to_payload())
                == CANONICAL_DEPLOYMENT_CONFIG_HASH
                for item in sessions
            ),
            "Matched attack configuration drifted.",
        )
        _require(
            tuple(item.decision_record_count() for item in sessions) == (22, 23),
            "Matched attack requires exact 22/23-record endpoints.",
        )
        before = [canonical_json(item.to_persistence_payload()) for item in sessions]
        fresh_pair = reproduce_followthrough_pair()
        _require(
            before == [canonical_json(item.to_persistence_payload()) for item in fresh_pair],
            "Matched attack endpoints differ from ordinary reproduction.",
        )
        branches: dict[str, dict[str, JsonValue]] = {}
        for name, session in zip(("stationary", "normal_move"), fresh_pair, strict=True):
            initial = _exploiter_state(session)
            initial_boundary = _boundary(session)
            checkpoint_hash = payload_digest(session.to_persistence_payload())
            trace = _approach(session)
            attack_boundary = _boundary(session)
            before_attack = _exploiter_state(session)
            trace.extend(_finish_attack(session))
            final = _exploiter_state(session)
            origin = VerifiedEpisodeOrigin.from_session(
                session, config=canonical_deployment_config()
            )
            artifact = session.replay_artifact(artifact_id=f"{MATCHED_ATTACK_ID}:{name}")
            events = [
                event.to_payload()
                for event in session.lifecycle.decision_controller.event_log.records
                if event.event_type
                in ("attack_sequence_started", "attack_sequence_step", "attack_sequence_completed")
            ]
            _require(
                sum(event["event_type"] == "attack_sequence_completed" for event in events) == 1,
                "Matched attack must complete exactly one attack sequence per branch.",
            )
            branches[name] = cast(
                dict[str, JsonValue],
                validate_json_value(
                    {
                        "initial_checkpoint_hash": checkpoint_hash,
                        "initial_boundary": initial_boundary,
                        "attack_boundary": attack_boundary,
                        "horizon": _boundary(session),
                        "initial_exploiter": initial,
                        "before_attack_exploiter": before_attack,
                        "final_exploiter": final,
                        "wounds_lost": cast(int, before_attack["total_wounds_remaining"])
                        - cast(int, final["total_wounds_remaining"]),
                        "attack_trace": trace,
                        "controlled_choices": _controlled_choices(trace),
                        "attack_events": events,
                        "origin": origin.to_payload(),
                        "replay_artifact": artifact,
                        "replay_artifact_hash": payload_digest(artifact),
                    }
                ),
            )
        left, right = branches["stationary"], branches["normal_move"]
        for key in ("initial_boundary", "attack_boundary", "horizon", "controlled_choices"):
            _require(left[key] == right[key], f"Matched attack {key} differs across branches.")
        left_final = cast(dict[str, JsonValue], left["final_exploiter"])
        right_final = cast(dict[str, JsonValue], right["final_exploiter"])
        _require(
            before == [canonical_json(item.to_persistence_payload()) for item in sessions],
            "Matched attack changed a supplied endpoint.",
        )
        comparison: dict[str, JsonValue] = {
            "same_initial_exploiter": left["initial_exploiter"] == right["initial_exploiter"],
            "same_before_attack_exploiter": (
                left["before_attack_exploiter"] == right["before_attack_exploiter"]
            ),
            "same_final_exploiter": left_final == right_final,
            "normal_move_minus_stationary_wounds": (
                cast(int, right_final["total_wounds_remaining"])
                - cast(int, left_final["total_wounds_remaining"])
            ),
            "normal_move_minus_stationary_alive_models": (
                cast(int, right_final["alive_model_count"])
                - cast(int, left_final["alive_model_count"])
            ),
            "tactical_benefit": "not-established-by-one-fixed-seed-cooperative-pair",
        }
        payload = validate_json_value(
            {
                "schema_version": "matched-attack-comparison-v1",
                "definition": matched_attack_definition(),
                "definition_hash": payload_digest(matched_attack_definition()),
                "configuration": canonical_deployment_config().to_payload(),
                "branches": branches,
                "comparison": comparison,
                "remaining_tactical_gaps": [
                    "demonstrated-screen-or-exposure",
                    "exploiter-benefit-after-opponent-response",
                    "adversarial-and-alternative-timing-controls",
                    "useful-candidate-coverage-and-scenario-costs",
                ],
                "fixture_exceptions": [
                    "synthetic-phase9a-core-catalog-not-an-official-faction-roster",
                    "allow_legacy_non_strict_rosters-true",
                    "redeploy-and-scouts-declined-not-exercised",
                    "legacy-model-volumes-not-source-measured-model-heights",
                    "July-mission-scoring-with-October-layout-geometry",
                    "one-explicit-300-point-reserve-value-not-a-complete-points-roster",
                    "public-fixed-test-private-rng-seed-not-a-competitive-game-seed",
                    "cooperative-A-stationary-and-declined-reactions-not-an-adversarial-policy",
                ],
                "source_obligations": {
                    "authority": "unchanged-viewer-submissions-engine-validation-and-exact-replay",
                    "movement": "gw-11e-core-rules:movement-phase:move-units-step",
                    "reaction": "gw-11e-core-stratagems:core:fire-overwatch",
                    "shooting": "shared-equipped-weapon-range-visibility-and-attack-resolution",
                },
                "episode_end": "truncated",
                "useful_reference_status": "scoped_gap",
                "reference_target": None,
                "eligible_for_learning": False,
            }
        )
        result = object.__new__(cls)
        object.__setattr__(result, "_payload_json", canonical_json(payload))
        return result

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], json.loads(self._payload_json))

    @property
    def content_hash(self) -> str:
        return payload_digest(self.to_payload())
