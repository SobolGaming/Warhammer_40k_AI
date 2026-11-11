"""Operator-only shooter diagnostics and a bounded ordinary-play attack witness."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import cast

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.canonical_deployment import (
    CANONICAL_DEPLOYMENT_CONFIG_HASH,
    canonical_deployment_config,
)
from warhammer40k_core.ai.followthrough_scenario import (
    FOLLOWTHROUGH_DEFINITION_HASH,
    reproduce_followthrough_pair,
)
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, payload_digest
from warhammer40k_core.ai.preserve_scenario import (
    EXPLOITER_UNIT_ID,
    OPPONENT_UNIT_ID,
    SCREEN_UNIT_ID,
    _require,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.ai.training_admission import TrainingAdmissionError, VerifiedEpisodeOrigin
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.fire_overwatch import fire_overwatch_shooter_ineligibility_reason
from warhammer40k_core.engine.movement_proposals import MovementProposalPayload, ProposalKind
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.shooting_selection_range import target_within_shooting_selection_range
from warhammer40k_core.engine.shooting_targets import (
    shooting_target_candidate_for_model,
    unit_has_line_of_sight_to_target,
)
from warhammer40k_core.engine.shooting_terrain_visibility import shooting_terrain_areas_for_state
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.weapon_declaration import (
    ShootingDeclarationProposal,
    WeaponDeclaration,
)
from warhammer40k_core.geometry.pathing import ModelPathEndpoint, PathWitness
from warhammer40k_core.geometry.pose import Pose, PosePayload

OPPOSING_SHOOTER_ID = "canonical-opposing-shooter-v1"
_VEHICLE = "army-alpha:strategic-reserve-unit"
_TARGETS = (EXPLOITER_UNIT_ID, SCREEN_UNIT_ID, _VEHICLE)
_GAPS = (
    "demonstrated-screen-or-exposure",
    "matched-opponent-response-and-exploiter-benefit",
    "matched-later-outcomes-with-declared-local-horizon",
    "timing-and-cooperation-controls",
    "useful-candidate-coverage-and-scenario-costs",
)


def _diagnose_endpoint(session: LocalGameSession) -> dict[str, JsonValue]:
    """Keep range-short-circuited target candidates separate from actual LOS queries."""
    state, config = session.lifecycle.state, session.lifecycle.config
    _require(state is not None, "Opposing diagnostics require a started session.")
    assert state is not None
    scenario = battlefield_scenario_for_state(state=state)
    shooter = rules_unit_view_by_id(state=state, unit_instance_id=OPPONENT_UNIT_ID)
    _require(len(shooter.components) == 1, "Frozen shooter composition drifted.")
    models = shooter.alive_models()
    _require(len(models) == 5, "Frozen shooter living formation drifted.")
    areas = shooting_terrain_areas_for_state(state)
    features = scenario.battlefield_state.terrain_features
    equipment: list[dict[str, object]] = []
    candidates: list[dict[str, object]] = []
    for model in models:
        _require(model.wargear_ids == ("core-bolt-rifle",), "Frozen shooter equipment drifted.")
        wargear = next(
            item for item in config.army_catalog.wargear if item.wargear_id == "core-bolt-rifle"
        )
        _require(len(wargear.weapon_profiles) == 1, "Frozen rifle profiles drifted.")
        profile = wargear.weapon_profiles[0]
        _require(profile.range_profile.distance_inches == 24, "Frozen rifle range drifted.")
        equipment.append(
            {"model_instance_id": model.model_instance_id, "wargear": wargear.to_payload()}
        )
        for target in _TARGETS:
            candidate = shooting_target_candidate_for_model(
                scenario=scenario,
                ruleset_descriptor=config.ruleset_descriptor,
                attacker_unit=shooter.components[0].unit,
                attacker_model_instance_id=model.model_instance_id,
                weapon_profile=profile,
                target_unit_id=target,
                terrain_features=features,
                terrain_areas=areas,
            )
            candidates.append(
                {"model_instance_id": model.model_instance_id, "candidate": candidate.to_payload()}
            )
    targets = [
        {
            "target_unit_instance_id": target,
            "within_equipped_24_inch_range": target_within_shooting_selection_range(
                scenario=scenario,
                attacking_unit_instance_id=OPPONENT_UNIT_ID,
                target_unit_instance_id=target,
                max_range_inches=24,
                placed_alive_attacker_models_only=True,
                placed_alive_target_models_only=True,
            ),
            "independently_visible": unit_has_line_of_sight_to_target(
                state=state,
                scenario=scenario,
                ruleset_descriptor=config.ruleset_descriptor,
                observing_unit=shooter.components[0].unit,
                target_unit_id=target,
                terrain_features=features,
                terrain_areas=areas,
                placed_alive_models_only=True,
            ),
        }
        for target in _TARGETS
    ]
    return cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "checkpoint_hash": payload_digest(session.to_persistence_payload()),
                "accepted_record_count": session.decision_record_count(),
                "shooter_unit_instance_id": OPPONENT_UNIT_ID,
                "shooter_ineligibility_reason": fire_overwatch_shooter_ineligibility_reason(
                    state=state,
                    player_id="player-b",
                    unit_instance_id=OPPONENT_UNIT_ID,
                    army_catalog=config.army_catalog,
                ),
                "equipped_models": equipment,
                "targets": targets,
                "per_model_candidates": candidates,
                "visibility_policy": (
                    "independent-living-model-query-with-state-terrain-features-and-areas"
                ),
            }
        ),
    )


def _submit(
    session: LocalGameSession,
    *,
    route: tuple[str, str, str],
    option: str | None = None,
    payload: JsonValue | None = None,
) -> dict[str, JsonValue]:
    request = session.lifecycle.pending_decision_request()
    _require(request is not None, "Opposing witness requires a pending decision.")
    assert request is not None
    _require(request.actor_id is not None, "Opposing witness requires a player decision.")
    assert request.actor_id is not None
    context = PlayerDecisionContext.from_view(
        session.view(viewer_player_id=request.actor_id), choice_seed=7
    )
    _require(
        context.route.stage == "battle"
        and (context.route.actor_id, context.route.battle_phase, context.route.decision_type)
        == route,
        "Opposing witness route drifted.",
    )
    index = session.decision_record_count()
    viewer = ViewerContext.for_player(request.actor_id)
    result_id = f"{OPPOSING_SHOOTER_ID}:{index}"
    if option is not None:
        status = session.submit_viewer_option(
            viewer=viewer,
            request_id=context.request["request_id"],
            option_id=option,
            result_id=result_id,
        )
    else:
        _require(payload is not None, "Opposing witness proposal is missing.")
        status = session.submit_viewer_parameterized_payload(
            viewer=viewer,
            request_id=context.request["request_id"],
            payload=payload,
            result_id=result_id,
        )
    if status.status_kind is LifecycleStatusKind.ADVANCED:
        status = session.advance_until_decision_or_terminal()
    appended = session.lifecycle.decision_controller.records[index:]
    expected_types = [context.route.decision_type]
    if context.route.decision_type == "submit_shooting_declaration":
        expected_types.extend(("select_resolve_target_unit", "select_attack_weapon_group"))
    _require(
        status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
        and [record.request.decision_type for record in appended] == expected_types
        and appended[0].result.result_id == result_id,
        f"Opposing witness decision failed: {status.payload}",
    )
    return cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "index": index,
                "route": asdict(context.route),
                "observation_hash": context.observation_hash,
                "selected_option_id": option,
                "submitted_payload": payload,
                "accepted_records": [record.to_payload() for record in appended],
            }
        ),
    )


def _approach_proposal(context: PlayerDecisionContext, battle_round: int) -> JsonValue:
    pending = cast(dict[str, JsonValue], context.observation["pending_proposal"])
    _require(pending["unit_instance_id"] == OPPONENT_UNIT_ID, "Approach unit drifted.")
    battlefield = cast(dict[str, JsonValue], context.observation["battlefield_state"])
    endpoints: list[ModelPathEndpoint] = []
    for army in cast(list[dict[str, JsonValue]], battlefield["placed_armies"]):
        for unit in cast(list[dict[str, JsonValue]], army["unit_placements"]):
            if unit["unit_instance_id"] == OPPONENT_UNIT_ID:
                placements = cast(list[dict[str, JsonValue]], unit["model_placements"])
                if battle_round == 3:
                    placements = sorted(
                        placements,
                        key=lambda row: (
                            -Pose.from_payload(cast(PosePayload, row["pose"])).position.y
                        ),
                    )
                for model in placements:
                    start = Pose.from_payload(cast(PosePayload, model["pose"]))
                    dx, dy = (-2.0, 5.0) if battle_round == 1 else (0.0, 6.0)
                    if battle_round == 3:
                        _require(start.position.x in (1.0, 2.8), "Approach columns drifted.")
                        dx, dy = (0.0, 6.0 if start.position.x == 1.0 else 3.0)
                    end = Pose.at(
                        start.position.x + dx,
                        start.position.y + dy,
                        start.position.z,
                        start.facing.degrees,
                    )
                    endpoints.append((cast(str, model["model_instance_id"]), start, end))
    _require(len(endpoints) == 5, "Approach formation drifted.")
    return validate_json_value(
        MovementProposalPayload(
            proposal_request_id=cast(str, pending["request_id"]),
            proposal_kind=ProposalKind.NORMAL_MOVE,
            unit_instance_id=OPPONENT_UNIT_ID,
            movement_phase_action="normal_move",
            movement_mode="normal",
            witness=PathWitness.for_straight_line_endpoints(tuple(endpoints)),
        ).to_payload()
    )


def _approach(session: LocalGameSession) -> list[dict[str, JsonValue]]:
    trace: list[dict[str, JsonValue]] = []

    def choose(actor: str, phase: str, decision: str, option: str) -> None:
        trace.append(_submit(session, route=(actor, phase, decision), option=option))

    def decline(actor: str) -> None:
        trace.append(
            _submit(
                session,
                route=(actor, "movement", "submit_stratagem_target_proposal"),
                payload={"submission_kind": "decline_stratagem_window"},
            )
        )

    decline("player-b")
    choose("player-a", "shooting", "select_shooting_unit", "complete_shooting_phase")
    for battle_round in (1, 2, 3):
        if battle_round > 1:
            for unit_id in _TARGETS:
                choose("player-a", "movement", "select_movement_unit", unit_id)
                choose("player-a", "movement", "select_movement_action", "remain_stationary")
            decline("player-b")
            choose("player-a", "shooting", "select_shooting_unit", "complete_shooting_phase")
        _require(
            session.lifecycle.state is not None
            and session.lifecycle.state.battle_round == battle_round,
            "Approach round drifted.",
        )
        choose("player-b", "movement", "select_movement_unit", OPPONENT_UNIT_ID)
        choose("player-b", "movement", "select_movement_action", "normal_move")
        context = PlayerDecisionContext.from_view(
            session.view(viewer_player_id="player-b"), choice_seed=7
        )
        trace.append(
            _submit(
                session,
                route=("player-b", "movement", "submit_movement_proposal"),
                payload=_approach_proposal(context, battle_round),
            )
        )
        decline("player-a")
        choose(
            "player-b",
            "shooting",
            "select_shooting_unit",
            OPPONENT_UNIT_ID if battle_round == 3 else "complete_shooting_phase",
        )
    choose("player-b", "shooting", "select_shooting_type", "normal")
    return trace


def opposing_shooter_definition() -> dict[str, JsonValue]:
    return cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "scenario_id": OPPOSING_SHOOTER_ID,
                "configuration_hash": CANONICAL_DEPLOYMENT_CONFIG_HASH,
                "historical_followthrough_definition_hash": FOLLOWTHROUGH_DEFINITION_HASH,
                "matched_endpoint_record_counts": [22, 23],
                "diagnostics": (
                    "all-five-equipped-models-all-three-A-targets-independent-range-and-LOS"
                ),
                "attack_branch": "stationary-only",
                "approach": [
                    {"battle_round": 1, "translation_inches": [-2.0, 5.0, 0.0]},
                    {"battle_round": 2, "translation_inches": [0.0, 6.0, 0.0]},
                    {
                        "battle_round": 3,
                        "x_1_column_y_inches": 6.0,
                        "x_2_8_column_y_inches": 3.0,
                        "model_order": "descending-start-Y-stable-ties",
                    },
                ],
                "movement_path": "straight-line-full-witness-unchanged-height-and-facing",
                "cooperation": "A-remains-stationary-rounds-two-three-all-reactions-declined",
                "shooting": (
                    "A-skips-shooting-B-skips-rounds-one-two-B-model-003-rifle-at-E-round-three"
                ),
                "attack_choices": (
                    "four-B-hit-wound-reroll-declines-one-A-armour-save-reroll-decline-"
                    "A-allocates-to-E-model-001"
                ),
                "automatic_choices": ["select_resolve_target_unit", "select_attack_weapon_group"],
                "horizon": (
                    "attack-sequence-completed-automatic-phase-progress-to-round-four-A-movement"
                ),
                "qualification": (
                    "single-ordinary-attack-feasibility-not-paired-outcomes-or-tactical-value"
                ),
            }
        ),
    )


def _declaration(context: PlayerDecisionContext) -> JsonValue:
    pending = cast(dict[str, JsonValue], context.observation["pending_proposal"])
    model_id = OPPONENT_UNIT_ID + ":core-intercessor-like:003"
    weapons = cast(list[dict[str, JsonValue]], pending["available_weapons"])
    selected = [weapon for weapon in weapons if weapon["model_instance_id"] == model_id]
    _require(len(selected) == 1, "Opposing attack equipped weapon drifted.")
    weapon = selected[0]
    candidates = cast(list[dict[str, JsonValue]], pending["target_candidates"])
    _require(
        any(
            candidate["is_legal"] is True
            and candidate["observer_model_id"] == model_id
            and candidate["target_unit_instance_id"] == EXPLOITER_UNIT_ID
            and candidate["weapon_profile_id"] == weapon["weapon_profile_id"]
            for candidate in candidates
        ),
        "Opposing attack target is not legal.",
    )
    return validate_json_value(
        ShootingDeclarationProposal(
            proposal_request_id=cast(str, pending["request_id"]),
            proposal_kind=cast(str, pending["proposal_kind"]),
            player_id=cast(str, pending["actor_id"]),
            battle_round=cast(int, pending["battle_round"]),
            unit_instance_id=cast(str, pending["unit_instance_id"]),
            source_decision_request_id=cast(str, pending["source_decision_request_id"]),
            source_decision_result_id=cast(str, pending["source_decision_result_id"]),
            visibility_cache_key=cast(str, pending["visibility_cache_key"]),
            declarations=(
                WeaponDeclaration(
                    weapon_instance_id=cast(str, weapon["weapon_instance_id"]),
                    attacker_model_instance_id=model_id,
                    wargear_id=cast(str, weapon["wargear_id"]),
                    weapon_profile_id=cast(str, weapon["weapon_profile_id"]),
                    target_unit_instance_id=EXPLOITER_UNIT_ID,
                    shooting_type=ShootingType.NORMAL,
                ),
            ),
        ).to_payload()
    )


def _finish_attack(session: LocalGameSession) -> list[dict[str, JsonValue]]:
    context = PlayerDecisionContext.from_view(
        session.view(viewer_player_id="player-b"), choice_seed=7
    )
    trace = [
        _submit(
            session,
            route=("player-b", "shooting", "submit_shooting_declaration"),
            payload=_declaration(context),
        )
    ]
    for _ in range(4):
        trace.append(
            _submit(
                session,
                route=("player-b", "shooting", "use_stratagem"),
                option="decline_stratagem_window",
            )
        )
    trace.append(
        _submit(
            session,
            route=("player-a", "shooting", "use_stratagem"),
            option="decline_stratagem_window",
        )
    )
    trace.append(
        _submit(
            session,
            route=("player-a", "shooting", "select_damage_allocation_model"),
            option=EXPLOITER_UNIT_ID + ":core-deep-strike-model:001",
        )
    )
    endpoint = PlayerDecisionContext.from_view(
        session.view(viewer_player_id="player-a"), choice_seed=7
    )
    _require(
        session.lifecycle.state is not None
        and session.lifecycle.state.battle_round == 4
        and endpoint.route.actor_id == "player-a"
        and endpoint.route.battle_phase == "movement"
        and endpoint.route.decision_type == "select_movement_unit",
        "Opposing attack endpoint drifted.",
    )
    return trace


@dataclass(frozen=True, slots=True, init=False)
class OpposingShooterQualification:
    """Closed, export-only operator report; serialized copies cannot admit training data."""

    _payload_json: str

    def __init__(self) -> None:
        raise TrainingAdmissionError("Qualify opposing shooting through exact ordinary sessions.")

    @classmethod
    def from_sessions(
        cls,
        stationary: LocalGameSession,
        moved: LocalGameSession,
    ) -> OpposingShooterQualification:
        sessions = (stationary, moved)
        _require(
            all(type(item) is LocalGameSession for item in sessions),
            "Opposing qualification requires local sessions.",
        )
        _require(
            all(
                payload_digest(item.lifecycle.config.to_payload())
                == CANONICAL_DEPLOYMENT_CONFIG_HASH
                for item in sessions
            ),
            "Opposing qualification configuration drifted.",
        )
        _require(
            tuple(item.decision_record_count() for item in sessions) == (22, 23),
            "Opposing qualification requires exact 22/23-record endpoints.",
        )
        fresh_pair = reproduce_followthrough_pair()
        before = [canonical_json(item.to_persistence_payload()) for item in sessions]
        _require(
            all(
                original == canonical_json(fresh.to_persistence_payload())
                for original, fresh in zip(before, fresh_pair, strict=True)
            ),
            "Opposing qualification endpoints differ from ordinary reproduction.",
        )
        diagnostics = {
            name: _diagnose_endpoint(session)
            for name, session in zip(("stationary", "normal_move"), sessions, strict=True)
        }
        # The attack uses the freshly reproduced stationary branch, leaving both
        # caller-owned endpoints and their historic #660 admissions untouched.
        attack = fresh_pair[0]
        trace = _approach(attack)
        trace.extend(_finish_attack(attack))
        attack_origin = VerifiedEpisodeOrigin.from_session(
            attack, config=canonical_deployment_config()
        )
        moved_origin = VerifiedEpisodeOrigin.from_session(
            moved, config=canonical_deployment_config()
        )
        _require(
            before == [canonical_json(item.to_persistence_payload()) for item in sessions],
            "Opposing qualification changed a supplied endpoint.",
        )
        attack_artifact = attack.replay_artifact(artifact_id=OPPOSING_SHOOTER_ID)
        attack_events = [
            event.to_payload()
            for event in attack.lifecycle.decision_controller.event_log.records
            if event.event_type
            in ("attack_sequence_started", "attack_sequence_step", "attack_sequence_completed")
        ]
        _require(
            any(event["event_type"] == "attack_sequence_completed" for event in attack_events),
            "Opposing witness did not complete an attack sequence.",
        )
        payload = validate_json_value(
            {
                "schema_version": "opposing-shooter-qualification-v1",
                "definition": opposing_shooter_definition(),
                "definition_hash": payload_digest(opposing_shooter_definition()),
                "configuration": canonical_deployment_config().to_payload(),
                "endpoints": diagnostics,
                "normal_move_origin": moved_origin.to_payload(),
                "attack_origin": attack_origin.to_payload(),
                "attack_trace": trace,
                "attack_events": attack_events,
                "attack_replay_artifact": attack_artifact,
                "attack_replay_artifact_hash": payload_digest(attack_artifact),
                "remaining_tactical_gaps": list(_GAPS),
                "source_obligations": {
                    "movement": "gw-11e-core-rules:movement-phase:move-units-step",
                    "reaction": "gw-11e-core-stratagems:core:fire-overwatch",
                    "shooting": (
                        "shared-equipped-weapon-range-visibility-and-ordinary-attack-resolution"
                    ),
                },
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
