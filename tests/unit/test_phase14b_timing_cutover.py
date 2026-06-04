from __future__ import annotations

import json
from typing import TypedDict, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage, PlaceholderPhaseHandler
from warhammer40k_core.engine.phases.movement import (
    MovementPhaseActionKind,
    MovementPhaseState,
    MovementUnitSelection,
)
from warhammer40k_core.engine.phases.shooting import (
    OutOfPhaseShootingState,
    ShootingPhaseState,
    ShootingUnitSelection,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reserves import (
    ReserveDestructionTimingPolicy,
    ReserveKind,
    ReserveState,
)
from warhammer40k_core.engine.stratagems import (
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    stratagem_decline_payload,
)
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    TimingWindow,
    TimingWindowPayload,
)
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2025_26_mission_pack


class _ResolvedTimingWindow(TypedDict):
    trigger_kind: str
    window_id: str
    resolution_order: list[str]


def test_phase14b_timing_window_records_are_json_safe_and_round_trip() -> None:
    state = _battle_state()
    decisions = DecisionController()

    _placeholder_flow().advance(state=state, decisions=decisions)

    timing_window_payloads = _timing_window_payloads(decisions)
    blob = json.dumps(decisions.event_log.to_payload(), sort_keys=True)
    assert timing_window_payloads
    assert "<" not in blob
    assert "object at 0x" not in blob
    assert tuple(
        TimingWindow.from_payload(payload).to_payload() for payload in timing_window_payloads
    ) == tuple(timing_window_payloads)


def test_phase14b_end_window_order_is_deterministic_non_mission_before_mission() -> None:
    state = _battle_state()
    decisions = DecisionController()
    flow = _placeholder_flow()

    for _index in range(10):
        flow.advance(state=state, decisions=decisions)

    resolved = _resolved_timing_windows(decisions)
    last_round_windows = tuple(
        entry for entry in resolved if entry["window_id"].startswith("timing-window:phase14b-game")
    )

    assert state.battle_round == 2
    assert last_round_windows[-3:] == (
        {
            "trigger_kind": TimingTriggerKind.END_PHASE.value,
            "window_id": ("timing-window:phase14b-game:round-01:turn:player-b:phase:fight:end"),
            "resolution_order": ["non_mission_rules", "mission_rules"],
        },
        {
            "trigger_kind": TimingTriggerKind.END_TURN.value,
            "window_id": "timing-window:phase14b-game:round-01:turn:player-b:end",
            "resolution_order": ["non_mission_rules", "mission_rules"],
        },
        {
            "trigger_kind": TimingTriggerKind.END_BATTLE_ROUND.value,
            "window_id": "timing-window:phase14b-game:round-01:battle-round:end",
            "resolution_order": ["non_mission_rules", "mission_rules"],
        },
    )


def test_phase14b_end_phase_effects_expire_before_mission_objective_scoring() -> None:
    state = _battle_state()
    state.record_persisting_effect(
        PersistingEffect(
            effect_id="phase14b-end-phase-effect",
            source_rule_id="phase14b-source",
            owner_player_id="player-a",
            target_unit_instance_ids=("army-alpha:intercessor-unit-1",),
            started_battle_round=1,
            started_phase=BattlePhase.COMMAND,
            expiration=EffectExpiration.end_phase(
                battle_round=1,
                phase=BattlePhase.COMMAND,
                player_id="player-a",
            ),
            effect_payload={"phase14b": "expires_before_mission"},
        )
    )

    _placeholder_flow().advance(state=state, decisions=DecisionController())

    assert state.persisting_effects == []
    assert state.objective_control_records[-1].timing.value == "phase_end"


def test_phase14b_effective_active_player_scope_restores_after_selected_unit_context() -> None:
    state = _battle_state()
    movement_selection = MovementUnitSelection(
        player_id="player-a",
        battle_round=1,
        unit_instance_id="army-alpha:intercessor-unit-1",
        request_id="phase14b-move-request",
        result_id="phase14b-move-result",
    )
    state.movement_phase_state = MovementPhaseState(
        battle_round=1,
        active_player_id="player-a",
        selected_unit_ids=("army-alpha:intercessor-unit-1",),
        active_selection=movement_selection,
    )
    assert state.effective_active_player_id() == "player-a"
    assert state.effective_opposing_player_ids() == ("player-b",)

    movement_state = state.movement_phase_state
    assert movement_state is not None
    state.movement_phase_state = movement_state.with_activation_complete(
        "army-alpha:intercessor-unit-1"
    )
    shooting_selection = ShootingUnitSelection(
        player_id="player-a",
        battle_round=1,
        unit_instance_id="army-alpha:intercessor-unit-1",
        request_id="phase14b-shoot-request",
        result_id="phase14b-shoot-result",
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=1,
        active_player_id="player-a",
        selected_unit_ids=("army-alpha:intercessor-unit-1",),
        active_selection=shooting_selection,
    )
    assert state.effective_active_player_id() == "player-a"
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=1,
        active_player_id="player-a",
        selected_unit_ids=("army-alpha:intercessor-unit-1",),
        shot_unit_ids=("army-alpha:intercessor-unit-1",),
    )

    state.active_player_id = "player-b"
    state.out_of_phase_shooting_state = OutOfPhaseShootingState(
        battle_round=1,
        player_id="player-a",
        parent_phase=BattlePhase.MOVEMENT,
        source_rule_id="core:fire-overwatch",
        source_decision_request_id="phase14b-overwatch-request",
        source_decision_result_id="phase14b-overwatch-result",
        source_context={"source_kind": "fire_overwatch"},
        selected_unit_instance_id="army-alpha:intercessor-unit-1",
    )
    assert state.effective_active_player_id() == "player-a"
    assert state.effective_opposing_player_ids() == ("player-b",)

    state.out_of_phase_shooting_state = None
    assert state.effective_active_player_id() == "player-b"
    assert state.effective_opposing_player_ids() == ("player-a",)


def test_phase14b_end_opponent_movement_reactions_emit_fire_overwatch_before_rapid_ingress() -> (
    None
):
    lifecycle = _battle_lifecycle(beta_unit_selection_ids=("enemy-unit", "reserve-unit"))
    state = _require_state(lifecycle)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.battle_round = 2
    state.gain_command_points(
        player_id="player-b",
        amount=2,
        source_id="phase14b-cp",
        source_kind=CommandPointSourceKind.OTHER,
        cap_exempt=True,
    )
    _move_unit_to_reserves(
        state,
        player_id="player-b",
        unit_instance_id="army-beta:reserve-unit",
    )
    state.movement_phase_state = MovementPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        reinforcements_completed=True,
        selected_unit_ids=("army-alpha:intercessor-unit-1",),
        moved_unit_ids=("army-alpha:intercessor-unit-1",),
    )
    lifecycle.decision_controller.event_log.append(
        "movement_activation_completed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": "player-a",
            "phase": BattlePhase.MOVEMENT.value,
            "unit_instance_id": "army-alpha:intercessor-unit-1",
            "movement_phase_action": MovementPhaseActionKind.NORMAL_MOVE.value,
            "phase_body_status": "activation_complete",
        },
    )

    fire_status = lifecycle.advance_until_decision_or_terminal()
    fire_request = _decision_request(fire_status.decision_request)
    fire_context = _stratagem_context(fire_request)

    assert fire_request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE
    assert fire_context["trigger_kind"] == TimingTriggerKind.END_PHASE.value
    assert fire_context["timing_window_id"] == (
        "fire-overwatch-end-movement-round-02-unit-army-alpha:intercessor-unit-1-player-player-b"
    )
    assert _active_reaction_window_trigger(lifecycle) == TimingTriggerKind.END_PHASE.value

    rapid_status = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase14b-decline-fire-overwatch",
            request_id=fire_request.request_id,
            decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
            actor_id=fire_request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=stratagem_decline_payload(),
        )
    )
    rapid_request = _decision_request(rapid_status.decision_request)
    rapid_context = _stratagem_context(rapid_request)

    assert rapid_request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE
    assert rapid_context["trigger_kind"] == TimingTriggerKind.END_PHASE.value
    assert rapid_context["timing_window_id"] == (
        "rapid-ingress-end-movement-round-02-player-player-b"
    )
    assert _reaction_window_ids(lifecycle.decision_controller)[:2] == (
        "fire-overwatch-end-movement-round-02-unit-army-alpha:intercessor-unit-1-player-player-b",
        "rapid-ingress-end-movement-round-02-player-player-b",
    )


def _placeholder_flow() -> BattleRoundFlow:
    return BattleRoundFlow(
        phase_handlers={
            BattlePhase.COMMAND: PlaceholderPhaseHandler(BattlePhase.COMMAND),
            BattlePhase.MOVEMENT: PlaceholderPhaseHandler(BattlePhase.MOVEMENT),
            BattlePhase.SHOOTING: PlaceholderPhaseHandler(BattlePhase.SHOOTING),
            BattlePhase.CHARGE: PlaceholderPhaseHandler(BattlePhase.CHARGE),
            BattlePhase.FIGHT: PlaceholderPhaseHandler(BattlePhase.FIGHT),
        }
    )


def _battle_lifecycle(
    *,
    beta_unit_selection_ids: tuple[str, ...] = ("enemy-unit",),
) -> GameLifecycle:
    config = _config(beta_unit_selection_ids=beta_unit_selection_ids)
    state = _battle_state(config)
    return GameLifecycle.from_payload(
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": DecisionController().to_payload(),
            "reaction_queue": {"frames": []},
        }
    )


def _battle_state(config: GameConfig | None = None) -> GameState:
    resolved_config = _config() if config is None else config
    state = GameState.from_config(resolved_config)
    armies = tuple(
        muster_army(catalog=resolved_config.army_catalog, request=request)
        for request in resolved_config.army_muster_requests
    )
    for army in armies:
        state.record_army_definition(army)
    state.record_battlefield_state(
        create_deterministic_battlefield_scenario(
            battlefield_id="phase14b-battlefield",
            armies=armies,
        ).battlefield_state
    )
    while state.current_setup_step is not None:
        state.complete_current_setup_step()
    assert state.stage is GameLifecycleStage.BATTLE
    return state


def _config(
    *,
    beta_unit_selection_ids: tuple[str, ...] = ("enemy-unit",),
) -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id="phase14b-game",
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2025_26(
            descriptor_version="core-v2-phase14b-test"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=("intercessor-unit-1",),
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=beta_unit_selection_ids,
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=MissionSetup.from_mission_pack(
            mission_pack=chapter_approved_2025_26_mission_pack(),
            mission_pool_entry_id="mission-a",
            terrain_layout_id="layout-1",
            attacker_player_id="player-a",
            defender_player_id="player-b",
        ),
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_ids: tuple[str, ...],
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_id="core-combined-arms",
        ),
        unit_selections=tuple(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            )
            for unit_selection_id in unit_selection_ids
        ),
    )


def _move_unit_to_reserves(
    state: GameState,
    *,
    player_id: str,
    unit_instance_id: str,
) -> ReserveState:
    battlefield_state = state.battlefield_state
    assert battlefield_state is not None
    state.replace_battlefield_state(battlefield_state.without_unit_placement(unit_instance_id))
    reserve_state = ReserveState.declared_before_battle(
        player_id=player_id,
        unit_instance_id=unit_instance_id,
        reserve_kind=ReserveKind.RESERVES,
        destruction_deadline_policy=ReserveDestructionTimingPolicy.chapter_approved_2025_26(),
    )
    state.record_reserve_state(reserve_state)
    return reserve_state


def _timing_window_payloads(decisions: DecisionController) -> tuple[TimingWindowPayload, ...]:
    payloads: list[TimingWindowPayload] = []
    for record in decisions.event_log.records:
        if record.event_type != "timing_window_opened":
            continue
        payload = _event_payload_object(record.payload)
        timing_window = payload["timing_window"]
        assert isinstance(timing_window, dict)
        payloads.append(cast(TimingWindowPayload, timing_window))
    return tuple(payloads)


def _resolved_timing_windows(decisions: DecisionController) -> tuple[_ResolvedTimingWindow, ...]:
    entries: list[_ResolvedTimingWindow] = []
    for record in decisions.event_log.records:
        if record.event_type != "timing_window_resolved":
            continue
        payload = _event_payload_object(record.payload)
        timing_window = _json_object(payload["timing_window"])
        descriptor = _json_object(timing_window["descriptor"])
        resolution_order = payload["resolution_order"]
        assert isinstance(resolution_order, list)
        assert all(isinstance(item, str) for item in resolution_order)
        entries.append(
            {
                "trigger_kind": cast(str, descriptor["trigger_kind"]),
                "window_id": cast(str, timing_window["window_id"]),
                "resolution_order": cast(list[str], resolution_order),
            }
        )
    return tuple(entries)


def _reaction_window_ids(decisions: DecisionController) -> tuple[str, ...]:
    window_ids: list[str] = []
    for record in decisions.event_log.records:
        if record.event_type != "reaction_window_opened":
            continue
        payload = _event_payload_object(record.payload)
        reaction_window = _json_object(payload["reaction_window"])
        timing_window = _json_object(reaction_window["timing_window"])
        window_ids.append(cast(str, timing_window["window_id"]))
    return tuple(window_ids)


def _active_reaction_window_trigger(lifecycle: GameLifecycle) -> str:
    frame = lifecycle.reaction_queue.frames[-1]
    return frame.reaction_window.timing_window.descriptor.trigger_kind.value


def _decision_request(request: DecisionRequest | None) -> DecisionRequest:
    assert request is not None
    return request


def _stratagem_context(request: DecisionRequest) -> dict[str, JsonValue]:
    payload = _event_payload_object(request.payload)
    proposal_request = _json_object(payload["proposal_request"])
    return _json_object(proposal_request["context"])


def _require_state(lifecycle: GameLifecycle) -> GameState:
    state = lifecycle.state
    assert state is not None
    return state


def _event_payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(payload, dict)
    return payload


def _json_object(payload: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(payload, dict)
    return payload
