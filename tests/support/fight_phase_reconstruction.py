"""Exact retained fixture helpers for the complete Fight regression workload."""

from __future__ import annotations

import json
from typing import cast

from tests.phase15c_fight_order_helpers import (
    compact_test_unit_poses as _compact_test_unit_poses,
)
from tests.phase15c_fight_order_helpers import (
    mission_setup as _mission_setup,
)
from tests.phase15c_fight_order_helpers import (
    mustered_armies as _mustered_armies,
)
from tests.phase15c_fight_order_helpers import (
    record_fight_interrupt_effect as _record_fight_interrupt_effect,
)
from tests.phase15c_fight_order_helpers import (
    record_fights_first_effect as _record_fights_first_effect,
)
from tests.phase15c_fight_order_helpers import (
    submit_minimal_melee_declaration as _submit_minimal_melee_declaration,
)
from tests.phase15c_fight_order_helpers import (
    unit_placement_at as _unit_placement_at,
)
from tests.phase15c_fight_order_helpers import (
    unit_selection_for_id as _unit_selection_for_id,
)
from tests.sequential_translation_helpers import leading_first_translation_paths
from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture

from warhammer40k_core.adapters.contracts import FiniteOptionSubmission, ParameterizedSubmission
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.fight_order import (
    CHARGE_FIGHTS_FIRST_EFFECT_KIND,
    FIGHT_ACTIVATION_DECISION_TYPE,
    FIGHT_INTERRUPT_DECISION_TYPE,
    FIGHTS_FIRST_EFFECT_KIND,
    FightPhaseStatePayload,
)
from warhammer40k_core.engine.fight_resolution import SUBMIT_MELEE_DECLARATION_DECISION_TYPE
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import AttachmentDeclaration, DetachmentSelection
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


def _p12_forge_continuation(
    original: GameLifecyclePayload, *, drift: str, later_unit_id: str
) -> GameLifecyclePayload:
    forged = cast(GameLifecyclePayload, json.loads(json.dumps(original)))
    state = forged["state"]
    assert state is not None
    fight = state["fight_phase_state"]
    assert fight is not None
    snapshots = [fight.get("suspended_state", fight)]
    for raw_event in forged["decisions"]["event_log"]:
        if drift.startswith("checkpoint_") and raw_event["event_type"] == "fight_step_completed":
            snapshots.append(
                cast(
                    FightPhaseStatePayload,
                    cast(dict[str, JsonValue], raw_event["payload"])["fight_phase_state"],
                )
            )
        if raw_event["event_type"] in {
            "forced_fight_activation_queue_started",
            "forced_fight_activation_queue_completed",
        }:
            event_payload = cast(dict[str, JsonValue], raw_event["payload"])
            key = (
                "suspended_state"
                if raw_event["event_type"].endswith("started")
                else "resumed_state"
            )
            snapshots.append(cast(FightPhaseStatePayload, event_payload[key]))
    drift = drift.removeprefix("checkpoint_")
    for snapshot in snapshots:
        order = snapshot["fight_order_state"]
        movement = snapshot["consolidate_state"]
        assert movement is not None
        if drift == "next_player":
            order["next_player_id"] = (
                "player-b" if order["next_player_id"] == "player-a" else "player-a"
            )
        elif drift == "selected_inventory":
            order["selected_to_fight_unit_ids"].append(later_unit_id)
        elif drift == "extra_completed":
            movement["completed_unit_ids"].append(later_unit_id)
        elif drift == "omitted_completed":
            movement["completed_unit_ids"].pop(0)
        elif drift == "ordering_flag":
            order["remaining_combats_activation_since_band_entry"] = not order[
                "remaining_combats_activation_since_band_entry"
            ]
        elif drift == "step_status":
            snapshot["step_states"][0]["status"] = "pending"
        elif drift == "source_identity":
            order["fights_first_registry"]["sources"][0]["source_rule_id"] = "p12-forged-source"
        else:
            raise AssertionError(drift)
    return forged


def _fight_lifecycle(
    *,
    alpha_unit_ids: tuple[str, ...],
    enemy_unit_ids: tuple[str, ...],
    origins: dict[str, Pose],
    game_id: str,
    fights_first_unit_keys: tuple[str, ...] = (),
    charge_fights_first_unit_keys: tuple[str, ...] = (),
    fight_interrupt_unit_keys: tuple[str, ...] = (),
    datasheet_id: str = "core-intercessor-like-infantry",
    model_profile_id: str = "core-intercessor-like",
    model_count: int = 5,
    alpha_unit_specs: dict[str, tuple[str, str, int]] | None = None,
    enemy_unit_specs: dict[str, tuple[str, str, int]] | None = None,
    alpha_attachment_declarations: tuple[AttachmentDeclaration, ...] = (),
    catalog: ArmyCatalog | None = None,
) -> tuple[GameLifecycle, dict[str, UnitInstance]]:
    config = _config(
        game_id=game_id,
        alpha_unit_ids=alpha_unit_ids,
        enemy_unit_ids=enemy_unit_ids,
        datasheet_id=datasheet_id,
        model_profile_id=model_profile_id,
        model_count=model_count,
        alpha_unit_specs=alpha_unit_specs,
        enemy_unit_specs=enemy_unit_specs,
        alpha_attachment_declarations=alpha_attachment_declarations,
        catalog=catalog,
    )
    armies = _mustered_armies(config)
    mission_setup = config.mission_setup
    assert mission_setup is not None
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id=f"{game_id}-battlefield",
        armies=armies,
        battlefield_width_inches=mission_setup.battlefield_width_inches,
        battlefield_depth_inches=mission_setup.battlefield_depth_inches,
    )
    units = {
        unit.unit_instance_id.split(":", maxsplit=1)[1]: unit
        for army in armies
        for unit in army.units
    }
    battlefield = scenario.battlefield_state
    for key, unit in units.items():
        army_id = unit.unit_instance_id.split(":", maxsplit=1)[0]
        player_id = "player-a" if army_id == "army-alpha" else "player-b"
        battlefield = battlefield.with_unit_placement(
            _unit_placement_at(
                unit,
                army_id=army_id,
                player_id=player_id,
                poses=_compact_test_unit_poses(
                    origin=origins[key],
                    model_count=len(unit.own_models),
                ),
            )
        )
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    state.record_battlefield_state(battlefield)
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    state.battle_round = 1
    state.active_player_id = "player-a"
    for player_id in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=player_id,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=("assassination", "bring_it_down"),
            )
        )
    decisions = DecisionController()
    record_primary_turn_start_evidence_for_fixture(state, decisions=decisions)
    for key in fights_first_unit_keys:
        _record_fights_first_effect(
            state=state,
            unit=units[key],
            effect_kind=FIGHTS_FIRST_EFFECT_KIND,
        )
    for key in charge_fights_first_unit_keys:
        _record_fights_first_effect(
            state=state,
            unit=units[key],
            effect_kind=CHARGE_FIGHTS_FIRST_EFFECT_KIND,
        )
    for key in fight_interrupt_unit_keys:
        _record_fight_interrupt_effect(state=state, unit=units[key])
    payload = cast(
        GameLifecyclePayload,
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": decisions.to_payload(),
            "reaction_queue": {"frames": []},
        },
    )
    return GameLifecycle.from_payload(payload), units


def _config(
    *,
    game_id: str,
    alpha_unit_ids: tuple[str, ...],
    enemy_unit_ids: tuple[str, ...],
    datasheet_id: str,
    model_profile_id: str,
    model_count: int,
    alpha_unit_specs: dict[str, tuple[str, str, int]] | None = None,
    enemy_unit_specs: dict[str, tuple[str, str, int]] | None = None,
    alpha_attachment_declarations: tuple[AttachmentDeclaration, ...] = (),
    catalog: ArmyCatalog | None = None,
) -> GameConfig:
    resolved_catalog = ArmyCatalog.phase9a_canonical_content_pack() if catalog is None else catalog
    return GameConfig(
        game_id=game_id,
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase15c-test"
        ),
        army_catalog=resolved_catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=resolved_catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=alpha_unit_ids,
                datasheet_id=datasheet_id,
                model_profile_id=model_profile_id,
                model_count=model_count,
                unit_specs=alpha_unit_specs,
                attachment_declarations=alpha_attachment_declarations,
            ),
            _army_muster_request(
                catalog=resolved_catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=enemy_unit_ids,
                datasheet_id=datasheet_id,
                model_profile_id=model_profile_id,
                model_count=model_count,
                unit_specs=enemy_unit_specs,
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=_mission_setup(),
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_ids: tuple[str, ...],
    datasheet_id: str,
    model_profile_id: str,
    model_count: int,
    unit_specs: dict[str, tuple[str, str, int]] | None = None,
    attachment_declarations: tuple[AttachmentDeclaration, ...] = (),
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        force_disposition_id="purge-the-foe",
        unit_selections=tuple(
            _unit_selection_for_id(
                unit_id,
                unit_specs=unit_specs,
                default_datasheet_id=datasheet_id,
                default_model_profile_id=model_profile_id,
                default_model_count=model_count,
            )
            for unit_id in unit_selection_ids
        ),
        attachment_declarations=attachment_declarations,
    )


def _fight_movement_witness_for_unit(
    *,
    lifecycle: GameLifecycle,
    unit: UnitInstance,
    dx: float,
    endpoint_only: bool,
) -> PathWitness:
    state = _state(lifecycle)
    battlefield_state = state.battlefield_state
    assert battlefield_state is not None
    unit_placement = battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    model_paths: list[tuple[str, tuple[Pose, ...]]] = []
    for placement in unit_placement.model_placements:
        start = placement.pose
        end = Pose.at(
            start.position.x + dx,
            start.position.y,
            start.position.z,
            facing_degrees=start.facing.degrees,
        )
        if endpoint_only:
            model_paths.append((placement.model_instance_id, (start, end, end)))
            continue
        midpoint = Pose.at(
            start.position.x + (dx / 2.0),
            start.position.y,
            start.position.z,
            facing_degrees=start.facing.degrees,
        )
        model_paths.append((placement.model_instance_id, (start, midpoint, end)))
    return PathWitness.for_paths(leading_first_translation_paths(tuple(model_paths), dx=dx))


def _drain_fight_movement_requests(
    lifecycle: GameLifecycle,
    status: LifecycleStatus,
) -> LifecycleStatus:
    current = status
    submission_count = 0
    while (
        current.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
        and current.decision_request is not None
        and current.decision_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    ):
        submission_count += 1
        assert submission_count <= 8, (
            current,
            lifecycle.decision_controller.event_log.records[-3:],
        )
        request = current.decision_request
        proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
        assert proposal_request.proposal_kind in {
            ProposalKind.PILE_IN,
            ProposalKind.CONSOLIDATE,
        }
        context = cast(dict[str, JsonValue], proposal_request.context)
        current = lifecycle.submit_decision(
            ParameterizedSubmission(
                request_id=request.request_id,
                result_id=f"{request.request_id}:phase15c-no-move",
                payload=cast(
                    JsonValue,
                    {
                        "proposal_request_id": proposal_request.request_id,
                        "proposal_kind": proposal_request.proposal_kind.value,
                        "unit_instance_id": proposal_request.unit_instance_id,
                        "movement_phase_action": proposal_request.movement_phase_action,
                        "movement_mode": context["movement_mode"],
                    },
                ),
            ).to_result(request)
        )
    return current


def _resolve_phase15d_activation(
    lifecycle: GameLifecycle,
    status: LifecycleStatus,
    *,
    drain_movement: bool = True,
) -> LifecycleStatus:
    current = status
    submission_count = 0
    decision_index = 0
    while (
        current.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
        and current.decision_request is not None
    ):
        if _state(lifecycle).current_battle_phase is not BattlePhase.FIGHT:
            return current
        submission_count += 1
        assert submission_count <= 64, (
            current,
            lifecycle.decision_controller.event_log.records[-3:],
        )
        request = current.decision_request
        if request.decision_type in {
            FIGHT_ACTIVATION_DECISION_TYPE,
            FIGHT_INTERRUPT_DECISION_TYPE,
        }:
            return current
        if request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE:
            return _drain_fight_movement_requests(lifecycle, current) if drain_movement else current
        if request.decision_type == SUBMIT_MELEE_DECLARATION_DECISION_TYPE:
            current = _submit_minimal_melee_declaration(
                lifecycle,
                request=request,
                result_id=f"{request.request_id}:phase15c-melee",
            )
            assert current.status_kind is not LifecycleStatusKind.INVALID, current
            assert current.decision_request is None or (
                current.decision_request.decision_type != SUBMIT_MELEE_DECLARATION_DECISION_TYPE
            ), (current, lifecycle.decision_controller.event_log.records[-3:])
            continue
        if request.is_parameterized_submission_request():
            return current
        if not request.options:
            return current
        current = _submit_option(
            lifecycle,
            request=request,
            option_id=request.options[0].option_id,
            result_id=f"{request.request_id}:phase15c-auto-{decision_index:03d}",
        )
        decision_index += 1
    return current


def _submit_fight_movement_no_move(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    result_id: str,
) -> LifecycleStatus:
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    context = cast(dict[str, JsonValue], proposal_request.context)
    return lifecycle.submit_decision(
        ParameterizedSubmission(
            request_id=request.request_id,
            result_id=result_id,
            payload=cast(
                JsonValue,
                {
                    "proposal_request_id": proposal_request.request_id,
                    "proposal_kind": proposal_request.proposal_kind.value,
                    "unit_instance_id": proposal_request.unit_instance_id,
                    "movement_phase_action": proposal_request.movement_phase_action,
                    "movement_mode": context["movement_mode"],
                },
            ),
        ).to_result(request)
    )


def _submit_option(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    option_id: str,
    result_id: str,
) -> LifecycleStatus:
    return lifecycle.submit_decision(
        FiniteOptionSubmission(
            request_id=request.request_id,
            selected_option_id=option_id,
            result_id=result_id,
        ).to_result(request)
    )


def _state(lifecycle: GameLifecycle) -> GameState:
    assert lifecycle.state is not None
    return lifecycle.state


# Typed public seams preserve the exact retained helper implementations.
fight_lifecycle = _fight_lifecycle
fight_movement_witness_for_unit = _fight_movement_witness_for_unit
p12_forge_continuation = _p12_forge_continuation
resolve_phase15d_activation = _resolve_phase15d_activation
state = _state
submit_fight_movement_no_move = _submit_fight_movement_no_move
