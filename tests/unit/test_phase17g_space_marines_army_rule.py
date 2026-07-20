from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from typing import TypedDict, cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import DatasheetDefinition, DatasheetKeywordSet
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.dice import RerollPermission
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import (
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponProfile,
)
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
    RosterLegalityViolation,
    WarlordSelection,
    muster_army,
    validate_roster_legality,
)
from warhammer40k_core.engine.command_phase_start_hooks import (
    SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
    CommandPhaseStartContext,
    CommandPhaseStartHookBinding,
    CommandPhaseStartHookRegistry,
    CommandPhaseStartRequestContext,
    CommandPhaseStartResultContext,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.space_marines import (
    army_rule,
)
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    GameStatePayload,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.runtime_modifiers import WoundRollModifierContext
from warhammer40k_core.engine.setup_completion import SetupCompletionGate
from warhammer40k_core.engine.source_backed_rerolls import (
    SourceBackedRerollPermissionContext,
    source_backed_reroll_permission_context_for_unit,
    source_backed_reroll_permission_effect_payload,
    source_backed_reroll_permission_for_unit,
    source_payload_from_reroll_effect_payload,
)
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack

SPACE_MARINES_UNIT_ID = "army-alpha:intercessors"
SPACE_MARINES_DATASHEET_ID = "phase17g-space-marines-intercessors"
ENEMY_TARGET_ID = "army-beta:enemy-unit"
ENEMY_OTHER_ID = "army-beta:enemy-unit-2"


class RosterDatasheetPayload(TypedDict):
    name: str
    keywords: tuple[str, ...]
    faction_keywords: tuple[str, ...]


def _command_phase_start_test_request(
    context: CommandPhaseStartRequestContext,
) -> DecisionRequest:
    return DecisionRequest(
        request_id=context.state.next_decision_request_id(),
        decision_type=SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
        actor_id=context.active_player_id,
        payload={
            "hook_id": "phase17g:command-start:hook",
            "active_player_id": context.active_player_id,
        },
        options=(
            DecisionOption(
                option_id="phase17g:command-start:test",
                label="Command start test",
                payload={
                    "hook_id": "phase17g:command-start:hook",
                    "active_player_id": context.active_player_id,
                },
            ),
        ),
    )


def _malformed_command_phase_start_request_handler(
    _context: CommandPhaseStartRequestContext,
) -> object:
    return object()


def _malformed_command_phase_start_result_handler(
    _context: CommandPhaseStartResultContext,
) -> str:
    return "yes"


def test_lifecycle_requests_oath_target_and_records_effects() -> None:
    lifecycle = _battle_ready_lifecycle()
    contribution = army_rule.runtime_contribution()
    assert contribution.contribution_id == army_rule.CONTRIBUTION_ID
    assert not contribution.contribution_id.endswith(":scaffold")

    status = lifecycle.advance_until_decision_or_terminal()

    request = status.decision_request
    assert request is not None
    assert request.decision_type == SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE
    assert request.actor_id == "player-a"
    assert {option.option_id for option in request.options} == {
        f"space_marines:oath_of_moment:{ENEMY_TARGET_ID}",
        f"space_marines:oath_of_moment:{ENEMY_OTHER_ID}",
    }

    lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-space-marines-oath-target",
            request=request,
            selected_option_id=f"space_marines:oath_of_moment:{ENEMY_TARGET_ID}",
        )
    )

    state = _require_state(lifecycle)
    assert (
        army_rule.oath_of_moment_target_unit_id_for_player(
            state,
            player_id="player-a",
        )
        == ENEMY_TARGET_ID
    )
    permission_context = source_backed_reroll_permission_context_for_unit(
        state=state,
        player_id="player-a",
        unit_instance_id=SPACE_MARINES_UNIT_ID,
        roll_type="attack_sequence.hit",
        timing_window="attack_sequence.hit",
        target_unit_instance_id=ENEMY_TARGET_ID,
    )
    assert permission_context is not None
    assert permission_context.source_payload["target_unit_instance_id"] == ENEMY_TARGET_ID
    assert (
        source_backed_reroll_permission_context_for_unit(
            state=state,
            player_id="player-a",
            unit_instance_id=SPACE_MARINES_UNIT_ID,
            roll_type="attack_sequence.hit",
            timing_window="attack_sequence.hit",
            target_unit_instance_id=ENEMY_OTHER_ID,
        )
        is None
    )
    restored = cast(GameStatePayload, json.loads(json.dumps(state.to_payload())))
    assert restored == state.to_payload()


def test_command_phase_start_hook_registry_routes_requests_and_results() -> None:
    lifecycle = _battle_ready_lifecycle()
    state = _require_state(lifecycle)
    decisions = DecisionController()
    handled_active_players: list[str] = []

    def handler(context: CommandPhaseStartContext) -> None:
        handled_active_players.append(context.active_player_id)

    def request_handler(context: CommandPhaseStartRequestContext) -> DecisionRequest:
        return _command_phase_start_test_request(context)

    def result_handler(context: CommandPhaseStartResultContext) -> bool:
        return context.result.selected_option_id == "phase17g:command-start:test"

    registry = CommandPhaseStartHookRegistry.from_bindings(
        (
            CommandPhaseStartHookBinding(
                hook_id="phase17g:command-start:hook",
                source_id="phase17g:command-start:source",
                handler=handler,
                request_handler=request_handler,
                result_handler=result_handler,
            ),
        )
    )

    registry.resolve(
        CommandPhaseStartContext(
            state=state,
            decisions=decisions,
            active_player_id="player-a",
        )
    )
    request = registry.next_request_for(
        CommandPhaseStartRequestContext(
            state=state,
            decisions=decisions,
            active_player_id="player-a",
        )
    )
    assert request is not None
    result = DecisionResult.for_request(
        result_id="phase17g-command-start-result",
        request=request,
        selected_option_id="phase17g:command-start:test",
    )
    handled = registry.apply_result(
        CommandPhaseStartResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
            active_player_id="player-a",
        )
    )

    assert handled_active_players == ["player-a"]
    assert handled


def test_command_phase_start_hook_registry_rejects_ambiguous_hooks() -> None:
    lifecycle = _battle_ready_lifecycle()
    state = _require_state(lifecycle)
    decisions = DecisionController()
    context = CommandPhaseStartRequestContext(
        state=state,
        decisions=decisions,
        active_player_id="player-a",
    )
    result_context_request = _command_phase_start_test_request(context)
    result = DecisionResult.for_request(
        result_id="phase17g-command-start-ambiguous-result",
        request=result_context_request,
        selected_option_id="phase17g:command-start:test",
    )
    result_context = CommandPhaseStartResultContext(
        state=state,
        decisions=decisions,
        request=result_context_request,
        result=result,
        active_player_id="player-a",
    )

    empty_registry = CommandPhaseStartHookRegistry.empty()
    assert empty_registry.next_request_for(context) is None
    assert not empty_registry.apply_result(result_context)
    with pytest.raises(GameLifecycleError, match="requires a handler"):
        CommandPhaseStartHookBinding(
            hook_id="phase17g:command-start:empty",
            source_id="phase17g:command-start:source",
        )
    with pytest.raises(GameLifecycleError, match="unique"):
        CommandPhaseStartHookRegistry.from_bindings(
            (
                CommandPhaseStartHookBinding(
                    hook_id="phase17g:command-start:duplicate",
                    source_id="phase17g:command-start:source",
                    handler=lambda _context: None,
                ),
                CommandPhaseStartHookBinding(
                    hook_id="phase17g:command-start:duplicate",
                    source_id="phase17g:command-start:source",
                    handler=lambda _context: None,
                ),
            )
        )

    duplicate_request_registry = CommandPhaseStartHookRegistry.from_bindings(
        (
            CommandPhaseStartHookBinding(
                hook_id="phase17g:command-start:request-a",
                source_id="phase17g:command-start:source",
                request_handler=_command_phase_start_test_request,
            ),
            CommandPhaseStartHookBinding(
                hook_id="phase17g:command-start:request-b",
                source_id="phase17g:command-start:source",
                request_handler=_command_phase_start_test_request,
            ),
        )
    )
    with pytest.raises(GameLifecycleError, match="multiple simultaneous requests"):
        duplicate_request_registry.next_request_for(context)

    duplicate_result_registry = CommandPhaseStartHookRegistry.from_bindings(
        (
            CommandPhaseStartHookBinding(
                hook_id="phase17g:command-start:result-a",
                source_id="phase17g:command-start:source",
                result_handler=lambda _context: True,
            ),
            CommandPhaseStartHookBinding(
                hook_id="phase17g:command-start:result-b",
                source_id="phase17g:command-start:source",
                result_handler=lambda _context: True,
            ),
        )
    )
    with pytest.raises(GameLifecycleError, match="handled by multiple hooks"):
        duplicate_result_registry.apply_result(result_context)


def test_command_phase_start_hook_contract_rejects_malformed_inputs() -> None:
    lifecycle = _battle_ready_lifecycle()
    state = _require_state(lifecycle)
    decisions = DecisionController()
    valid_binding = CommandPhaseStartHookBinding(
        hook_id="phase17g:command-start:valid",
        source_id="phase17g:command-start:source",
        handler=lambda _context: None,
    )
    valid_registry = CommandPhaseStartHookRegistry.from_bindings((valid_binding,))

    with pytest.raises(GameLifecycleError, match="state must be GameState"):
        CommandPhaseStartContext(
            state=cast(GameState, object()),
            decisions=decisions,
            active_player_id="player-a",
        )
    with pytest.raises(GameLifecycleError, match="state must be GameState"):
        CommandPhaseStartRequestContext(
            state=cast(GameState, object()),
            decisions=decisions,
            active_player_id="player-a",
        )
    with pytest.raises(GameLifecycleError, match="state must be GameState"):
        CommandPhaseStartResultContext(
            state=cast(GameState, object()),
            decisions=decisions,
            request=_command_phase_start_test_request(
                CommandPhaseStartRequestContext(
                    state=state,
                    decisions=decisions,
                    active_player_id="player-a",
                )
            ),
            result=DecisionResult(
                result_id="phase17g-command-start-state-result",
                request_id="phase17g-command-start-state-request",
                decision_type=SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
                actor_id="player-a",
                selected_option_id="phase17g:command-start:test",
                payload={},
            ),
            active_player_id="player-a",
        )
    with pytest.raises(GameLifecycleError, match="decisions must be DecisionController"):
        CommandPhaseStartRequestContext(
            state=state,
            decisions=cast(DecisionController, object()),
            active_player_id="player-a",
        )
    with pytest.raises(GameLifecycleError, match="decisions must be DecisionController"):
        CommandPhaseStartResultContext(
            state=state,
            decisions=cast(DecisionController, object()),
            request=_command_phase_start_test_request(
                CommandPhaseStartRequestContext(
                    state=state,
                    decisions=decisions,
                    active_player_id="player-a",
                )
            ),
            result=DecisionResult(
                result_id="phase17g-command-start-decisions-result",
                request_id="phase17g-command-start-decisions-request",
                decision_type=SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
                actor_id="player-a",
                selected_option_id="phase17g:command-start:test",
                payload={},
            ),
            active_player_id="player-a",
        )
    with pytest.raises(GameLifecycleError, match="request must be DecisionRequest"):
        CommandPhaseStartResultContext(
            state=state,
            decisions=decisions,
            request=cast(DecisionRequest, object()),
            result=DecisionResult(
                result_id="phase17g-command-start-request-result",
                request_id="phase17g-command-start-request",
                decision_type=SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
                actor_id="player-a",
                selected_option_id="phase17g:command-start:test",
                payload={},
            ),
            active_player_id="player-a",
        )
    result_request = _command_phase_start_test_request(
        CommandPhaseStartRequestContext(
            state=state,
            decisions=decisions,
            active_player_id="player-a",
        )
    )
    with pytest.raises(GameLifecycleError, match="result must be DecisionResult"):
        CommandPhaseStartResultContext(
            state=state,
            decisions=decisions,
            request=result_request,
            result=cast(DecisionResult, object()),
            active_player_id="player-a",
        )
    with pytest.raises(GameLifecycleError, match="active player drift"):
        CommandPhaseStartResultContext(
            state=state,
            decisions=decisions,
            request=_command_phase_start_test_request(
                CommandPhaseStartRequestContext(
                    state=state,
                    decisions=decisions,
                    active_player_id="player-a",
                )
            ),
            result=DecisionResult(
                result_id="phase17g-command-start-drift-result",
                request_id="phase17g-command-start-drift-request",
                decision_type=SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
                actor_id="player-a",
                selected_option_id="phase17g:command-start:test",
                payload={},
            ),
            active_player_id="player-b",
        )
    movement_phase_state = _require_state(_battle_ready_lifecycle())
    movement_phase_state.battle_phase_index = movement_phase_state.battle_phase_sequence.index(
        BattlePhase.MOVEMENT
    )
    with pytest.raises(GameLifecycleError, match="require Command phase"):
        CommandPhaseStartContext(
            state=movement_phase_state,
            decisions=decisions,
            active_player_id="player-a",
        )
    with pytest.raises(GameLifecycleError, match="require Command phase"):
        CommandPhaseStartRequestContext(
            state=movement_phase_state,
            decisions=decisions,
            active_player_id="player-a",
        )

    with pytest.raises(GameLifecycleError, match="handler must be callable"):
        CommandPhaseStartHookBinding(
            hook_id="phase17g:command-start:bad-handler",
            source_id="phase17g:command-start:source",
            handler=cast(Callable[[CommandPhaseStartContext], None], object()),
        )
    with pytest.raises(GameLifecycleError, match="request_handler must be callable"):
        CommandPhaseStartHookBinding(
            hook_id="phase17g:command-start:bad-request-handler",
            source_id="phase17g:command-start:source",
            request_handler=cast(
                Callable[[CommandPhaseStartRequestContext], DecisionRequest | None],
                object(),
            ),
        )
    with pytest.raises(GameLifecycleError, match="result_handler must be callable"):
        CommandPhaseStartHookBinding(
            hook_id="phase17g:command-start:bad-result-handler",
            source_id="phase17g:command-start:source",
            result_handler=cast(
                Callable[[CommandPhaseStartResultContext], bool],
                object(),
            ),
        )
    with pytest.raises(GameLifecycleError, match="hook_id must not be empty"):
        CommandPhaseStartHookBinding(
            hook_id=" ",
            source_id="phase17g:command-start:source",
            handler=lambda _context: None,
        )
    with pytest.raises(GameLifecycleError, match="source_id must be a string"):
        CommandPhaseStartHookBinding(
            hook_id="phase17g:command-start:bad-source-id",
            source_id=cast(str, object()),
            handler=lambda _context: None,
        )

    with pytest.raises(GameLifecycleError, match="bindings must be a tuple"):
        CommandPhaseStartHookRegistry(
            bindings=cast(tuple[CommandPhaseStartHookBinding, ...], [valid_binding])
        )
    with pytest.raises(GameLifecycleError, match="must contain hook bindings"):
        CommandPhaseStartHookRegistry(
            bindings=cast(tuple[CommandPhaseStartHookBinding, ...], (object(),))
        )
    with pytest.raises(GameLifecycleError, match="require context"):
        valid_registry.resolve(cast(CommandPhaseStartContext, object()))
    with pytest.raises(GameLifecycleError, match="request hooks require context"):
        valid_registry.next_request_for(cast(CommandPhaseStartRequestContext, object()))
    with pytest.raises(GameLifecycleError, match="result hooks require context"):
        valid_registry.apply_result(cast(CommandPhaseStartResultContext, object()))

    request_context = CommandPhaseStartRequestContext(
        state=state,
        decisions=decisions,
        active_player_id="player-a",
    )
    none_request_registry = CommandPhaseStartHookRegistry.from_bindings(
        (
            CommandPhaseStartHookBinding(
                hook_id="phase17g:command-start:none-request",
                source_id="phase17g:command-start:source",
                request_handler=lambda _context: None,
            ),
            CommandPhaseStartHookBinding(
                hook_id="phase17g:command-start:no-result-handler",
                source_id="phase17g:command-start:source",
                request_handler=_command_phase_start_test_request,
            ),
        )
    )
    assert none_request_registry.next_request_for(request_context) is not None
    malformed_request_registry = CommandPhaseStartHookRegistry.from_bindings(
        (
            CommandPhaseStartHookBinding(
                hook_id="phase17g:command-start:malformed-request",
                source_id="phase17g:command-start:source",
                request_handler=cast(
                    Callable[[CommandPhaseStartRequestContext], DecisionRequest | None],
                    _malformed_command_phase_start_request_handler,
                ),
            ),
        )
    )
    with pytest.raises(GameLifecycleError, match="must return DecisionRequest or None"):
        malformed_request_registry.next_request_for(request_context)

    result_request = _command_phase_start_test_request(request_context)
    malformed_result_registry = CommandPhaseStartHookRegistry.from_bindings(
        (
            CommandPhaseStartHookBinding(
                hook_id="phase17g:command-start:malformed-result",
                source_id="phase17g:command-start:source",
                result_handler=cast(
                    Callable[[CommandPhaseStartResultContext], bool],
                    _malformed_command_phase_start_result_handler,
                ),
            ),
        )
    )
    with pytest.raises(GameLifecycleError, match="must return bool"):
        malformed_result_registry.apply_result(
            CommandPhaseStartResultContext(
                state=state,
                decisions=decisions,
                request=result_request,
                result=DecisionResult.for_request(
                    result_id="phase17g-command-start-malformed-result",
                    request=result_request,
                    selected_option_id="phase17g:command-start:test",
                ),
                active_player_id="player-a",
            )
        )


def test_oath_target_drift_rejects_before_queue_pop() -> None:
    lifecycle = _battle_ready_lifecycle()
    status = lifecycle.advance_until_decision_or_terminal()
    request = status.decision_request
    assert request is not None

    state = _require_state(lifecycle)
    state.army_definitions = [
        replace(
            army,
            units=tuple(unit for unit in army.units if unit.unit_instance_id != ENEMY_TARGET_ID),
        )
        if army.player_id == "player-b"
        else army
        for army in state.army_definitions
    ]

    rejected = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-space-marines-stale-oath-target",
            request=request,
            selected_option_id=f"space_marines:oath_of_moment:{ENEMY_TARGET_ID}",
        )
    )

    assert rejected.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(rejected.payload, dict)
    assert rejected.payload["invalid_reason"] == "target_unit_missing"
    assert lifecycle.decision_controller.queue.peek_next().request_id == request.request_id


def test_oath_request_and_result_defensive_paths() -> None:
    lifecycle = _battle_ready_lifecycle()
    status = lifecycle.advance_until_decision_or_terminal()
    request = status.decision_request
    assert request is not None
    state = _require_state(lifecycle)
    context = CommandPhaseStartRequestContext(
        state=state,
        decisions=lifecycle.decision_controller,
        active_player_id="player-a",
    )

    player_b_lifecycle = _battle_ready_lifecycle()
    player_b_state = _require_state(player_b_lifecycle)
    player_b_state.active_player_id = "player-b"
    assert (
        army_rule.oath_of_moment_target_request(
            CommandPhaseStartRequestContext(
                state=player_b_state,
                decisions=player_b_lifecycle.decision_controller,
                active_player_id="player-b",
            )
        )
        is None
    )

    no_target_lifecycle = _battle_ready_lifecycle()
    no_target_state = _require_state(no_target_lifecycle)
    no_target_state.army_definitions = [
        replace(
            army,
            units=tuple(
                replace(
                    unit,
                    own_models=tuple(
                        replace(model, wounds_remaining=0) for model in unit.own_models
                    ),
                )
                for unit in army.units
            ),
        )
        if army.player_id == "player-b"
        else army
        for army in no_target_state.army_definitions
    ]
    assert (
        army_rule.oath_of_moment_target_request(
            CommandPhaseStartRequestContext(
                state=no_target_state,
                decisions=no_target_lifecycle.decision_controller,
                active_player_id="player-a",
            )
        )
        is None
    )

    wrong_type_request = DecisionRequest(
        request_id="phase17g-space-marines-wrong-type",
        decision_type="other_decision",
        actor_id="player-a",
        payload={"hook_id": army_rule.HOOK_ID},
        options=(
            DecisionOption(
                option_id="ignored",
                label="Ignored",
                payload={},
            ),
        ),
    )
    wrong_type_result = DecisionResult(
        result_id="phase17g-space-marines-wrong-type-result",
        request_id=wrong_type_request.request_id,
        decision_type=wrong_type_request.decision_type,
        actor_id="player-a",
        selected_option_id="ignored",
        payload={},
    )
    assert not army_rule.apply_oath_of_moment_target_result(
        CommandPhaseStartResultContext(
            state=state,
            decisions=lifecycle.decision_controller,
            request=wrong_type_request,
            result=wrong_type_result,
            active_player_id="player-a",
        )
    )

    wrong_hook_request = replace(request, payload={"hook_id": "other-hook"})
    wrong_hook_result = DecisionResult.for_request(
        result_id="phase17g-space-marines-wrong-hook-result",
        request=wrong_hook_request,
        selected_option_id=f"space_marines:oath_of_moment:{ENEMY_TARGET_ID}",
    )
    assert not army_rule.apply_oath_of_moment_target_result(
        CommandPhaseStartResultContext(
            state=state,
            decisions=lifecycle.decision_controller,
            request=wrong_hook_request,
            result=wrong_hook_result,
            active_player_id="player-a",
        )
    )

    lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-space-marines-oath-defensive-target",
            request=request,
            selected_option_id=f"space_marines:oath_of_moment:{ENEMY_TARGET_ID}",
        )
    )
    assert army_rule.oath_of_moment_target_request(context) is None


def test_oath_result_and_lookup_reject_invalid_payloads_and_ambiguous_targets() -> None:
    lifecycle = _battle_ready_lifecycle()
    status = lifecycle.advance_until_decision_or_terminal()
    request = status.decision_request
    assert request is not None
    state = _require_state(lifecycle)

    with pytest.raises(GameLifecycleError, match="requires result context"):
        army_rule.apply_oath_of_moment_target_result(cast(CommandPhaseStartResultContext, object()))
    with pytest.raises(GameLifecycleError, match="requires request context"):
        army_rule.oath_of_moment_target_request(cast(CommandPhaseStartRequestContext, object()))
    with pytest.raises(GameLifecycleError, match="requires an actor"):
        army_rule.apply_oath_of_moment_target_result(
            CommandPhaseStartResultContext(
                state=state,
                decisions=lifecycle.decision_controller,
                request=request,
                result=DecisionResult(
                    result_id="phase17g-space-marines-missing-actor",
                    request_id=request.request_id,
                    decision_type=request.decision_type,
                    actor_id=None,
                    selected_option_id=f"space_marines:oath_of_moment:{ENEMY_TARGET_ID}",
                    payload=request.option_by_id(
                        f"space_marines:oath_of_moment:{ENEMY_TARGET_ID}"
                    ).payload,
                ),
                active_player_id="player-a",
            )
        )
    with pytest.raises(GameLifecycleError, match="does not own Space Marines"):
        army_rule.apply_oath_of_moment_target_result(
            CommandPhaseStartResultContext(
                state=state,
                decisions=lifecycle.decision_controller,
                request=request,
                result=DecisionResult(
                    result_id="phase17g-space-marines-wrong-actor",
                    request_id=request.request_id,
                    decision_type=request.decision_type,
                    actor_id="player-b",
                    selected_option_id=f"space_marines:oath_of_moment:{ENEMY_TARGET_ID}",
                    payload=request.option_by_id(
                        f"space_marines:oath_of_moment:{ENEMY_TARGET_ID}"
                    ).payload,
                ),
                active_player_id="player-a",
            )
        )
    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        army_rule.apply_oath_of_moment_target_result(
            CommandPhaseStartResultContext(
                state=state,
                decisions=lifecycle.decision_controller,
                request=request,
                result=DecisionResult(
                    result_id="phase17g-space-marines-scalar-payload",
                    request_id=request.request_id,
                    decision_type=request.decision_type,
                    actor_id="player-a",
                    selected_option_id=f"space_marines:oath_of_moment:{ENEMY_TARGET_ID}",
                    payload="not-an-object",
                ),
                active_player_id="player-a",
            )
        )
    with pytest.raises(GameLifecycleError, match="missing required key"):
        army_rule.apply_oath_of_moment_target_result(
            CommandPhaseStartResultContext(
                state=state,
                decisions=lifecycle.decision_controller,
                request=request,
                result=DecisionResult(
                    result_id="phase17g-space-marines-missing-target-owner",
                    request_id=request.request_id,
                    decision_type=request.decision_type,
                    actor_id="player-a",
                    selected_option_id=f"space_marines:oath_of_moment:{ENEMY_TARGET_ID}",
                    payload={"target_unit_instance_id": ENEMY_TARGET_ID},
                ),
                active_player_id="player-a",
            )
        )

    stale_target_lifecycle = _battle_ready_lifecycle()
    stale_request = stale_target_lifecycle.advance_until_decision_or_terminal().decision_request
    assert stale_request is not None
    stale_state = _require_state(stale_target_lifecycle)
    stale_state.army_definitions = [
        replace(
            army,
            units=tuple(unit for unit in army.units if unit.unit_instance_id != ENEMY_TARGET_ID),
        )
        if army.player_id == "player-b"
        else army
        for army in stale_state.army_definitions
    ]
    with pytest.raises(GameLifecycleError, match="no longer eligible"):
        army_rule.apply_oath_of_moment_target_result(
            CommandPhaseStartResultContext(
                state=stale_state,
                decisions=stale_target_lifecycle.decision_controller,
                request=stale_request,
                result=DecisionResult.for_request(
                    result_id="phase17g-space-marines-stale-direct",
                    request=stale_request,
                    selected_option_id=f"space_marines:oath_of_moment:{ENEMY_TARGET_ID}",
                ),
                active_player_id="player-a",
            )
        )

    with pytest.raises(GameLifecycleError, match="requires GameState"):
        army_rule.oath_of_moment_target_unit_id_for_player(
            cast(GameState, object()),
            player_id="player-a",
        )
    with pytest.raises(GameLifecycleError, match="player_id must be a string"):
        army_rule.oath_of_moment_target_unit_id_for_player(
            state,
            player_id=cast(str, object()),
        )
    with pytest.raises(GameLifecycleError, match="player_id must not be empty"):
        army_rule.oath_of_moment_target_unit_id_for_player(
            state,
            player_id=" ",
        )
    applied_result = DecisionResult.for_request(
        result_id="phase17g-space-marines-ambiguous-target",
        request=request,
        selected_option_id=f"space_marines:oath_of_moment:{ENEMY_TARGET_ID}",
    )
    assert army_rule.apply_oath_of_moment_target_result(
        CommandPhaseStartResultContext(
            state=state,
            decisions=lifecycle.decision_controller,
            request=request,
            result=applied_result,
            active_player_id="player-a",
        )
    )
    assert (
        army_rule.oath_of_moment_target_unit_id_for_player(
            state,
            player_id="player-b",
        )
        is None
    )
    with pytest.raises(GameLifecycleError, match="already active"):
        army_rule.apply_oath_of_moment_target_result(
            CommandPhaseStartResultContext(
                state=state,
                decisions=lifecycle.decision_controller,
                request=request,
                result=DecisionResult.for_request(
                    result_id="phase17g-space-marines-target-already-active",
                    request=request,
                    selected_option_id=f"space_marines:oath_of_moment:{ENEMY_TARGET_ID}",
                ),
                active_player_id="player-a",
            )
        )
    target_effect = next(
        effect
        for effect in state.persisting_effects
        if _effect_payload_kind(effect) == army_rule.OATH_OF_MOMENT_EFFECT_KIND
    )
    state.record_persisting_effect(
        replace(
            target_effect,
            effect_id=f"{target_effect.effect_id}:malformed-payload",
            target_unit_instance_ids=(ENEMY_OTHER_ID,),
            effect_payload="not-an-object",
        )
    )
    assert (
        army_rule.oath_of_moment_target_unit_id_for_player(state, player_id="player-a")
        == ENEMY_TARGET_ID
    )
    state.record_persisting_effect(
        replace(
            target_effect,
            effect_id=f"{target_effect.effect_id}:duplicate",
            target_unit_instance_ids=(ENEMY_OTHER_ID,),
        )
    )
    with pytest.raises(GameLifecycleError, match="Multiple Oath of Moment targets"):
        army_rule.oath_of_moment_target_unit_id_for_player(state, player_id="player-a")


def test_source_backed_reroll_target_filter_and_payload_validation() -> None:
    lifecycle = _battle_ready_lifecycle()
    request = lifecycle.advance_until_decision_or_terminal().decision_request
    assert request is not None
    lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-space-marines-source-backed-target",
            request=request,
            selected_option_id=f"space_marines:oath_of_moment:{ENEMY_TARGET_ID}",
        )
    )
    state = _require_state(lifecycle)

    permission_context = source_backed_reroll_permission_context_for_unit(
        state=state,
        player_id="player-a",
        unit_instance_id=SPACE_MARINES_UNIT_ID,
        roll_type="attack_sequence.hit",
        timing_window="attack_sequence.hit",
        target_unit_instance_id=ENEMY_TARGET_ID,
    )
    assert permission_context is not None
    assert (
        source_backed_reroll_permission_context_for_unit(
            state=state,
            player_id="player-a",
            unit_instance_id=SPACE_MARINES_UNIT_ID,
            roll_type="attack_sequence.hit",
            timing_window="attack_sequence.hit",
        )
        is None
    )
    assert (
        source_backed_reroll_permission_for_unit(
            state=state,
            player_id="player-a",
            unit_instance_id=SPACE_MARINES_UNIT_ID,
            roll_type="attack_sequence.hit",
            timing_window="attack_sequence.hit",
            target_unit_instance_id=ENEMY_TARGET_ID,
        )
        is not None
    )
    assert (
        source_backed_reroll_permission_context_for_unit(
            state=state,
            player_id="player-b",
            unit_instance_id=SPACE_MARINES_UNIT_ID,
            roll_type="attack_sequence.hit",
            timing_window="attack_sequence.hit",
            target_unit_instance_id=ENEMY_TARGET_ID,
        )
        is None
    )
    assert (
        source_backed_reroll_permission_context_for_unit(
            state=state,
            player_id="player-a",
            unit_instance_id=SPACE_MARINES_UNIT_ID,
            roll_type="attack_sequence.wound",
            timing_window="attack_sequence.hit",
            target_unit_instance_id=ENEMY_TARGET_ID,
        )
        is None
    )
    assert (
        source_backed_reroll_permission_context_for_unit(
            state=state,
            player_id="player-a",
            unit_instance_id=SPACE_MARINES_UNIT_ID,
            roll_type="attack_sequence.hit",
            timing_window="attack_sequence.wound",
            target_unit_instance_id=ENEMY_TARGET_ID,
        )
        is None
    )
    with pytest.raises(GameLifecycleError, match="requires GameState"):
        source_backed_reroll_permission_context_for_unit(
            state=object(),
            player_id="player-a",
            unit_instance_id=SPACE_MARINES_UNIT_ID,
            roll_type="attack_sequence.hit",
            timing_window="attack_sequence.hit",
            target_unit_instance_id=ENEMY_TARGET_ID,
        )
    with pytest.raises(GameLifecycleError, match="effect_kind drift"):
        source_payload_from_reroll_effect_payload({"effect_kind": "wrong", "source_payload": {}})
    with pytest.raises(GameLifecycleError, match="source_payload"):
        source_payload_from_reroll_effect_payload(
            {
                "effect_kind": "source_backed_reroll_permission",
                "source_payload": None,
            }
        )
    with pytest.raises(GameLifecycleError, match="RerollPermission"):
        source_backed_reroll_permission_effect_payload(
            target_unit_instance_ids=(SPACE_MARINES_UNIT_ID,),
            permission=cast(RerollPermission, object()),
            source_payload={},
        )
    with pytest.raises(GameLifecycleError, match="target_unit_instance_ids must be a tuple"):
        source_backed_reroll_permission_effect_payload(
            target_unit_instance_ids=cast(tuple[str, ...], [SPACE_MARINES_UNIT_ID]),
            permission=permission_context.permission,
            source_payload={},
        )
    with pytest.raises(GameLifecycleError, match="target_unit_instance_ids must be unique"):
        source_backed_reroll_permission_effect_payload(
            target_unit_instance_ids=(SPACE_MARINES_UNIT_ID, SPACE_MARINES_UNIT_ID),
            permission=permission_context.permission,
            source_payload={},
        )
    with pytest.raises(GameLifecycleError, match="target_unit_instance_ids must not be empty"):
        source_backed_reroll_permission_effect_payload(
            target_unit_instance_ids=(),
            permission=permission_context.permission,
            source_payload={},
        )
    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        source_payload_from_reroll_effect_payload("not-an-object")
    with pytest.raises(GameLifecycleError, match="requires permission"):
        SourceBackedRerollPermissionContext(
            permission=cast(RerollPermission, object()),
            source_payload={},
        )
    with pytest.raises(GameLifecycleError, match="requires source payload"):
        SourceBackedRerollPermissionContext(
            permission=permission_context.permission,
            source_payload=cast(dict[str, JsonValue], []),
        )

    reroll_effect = next(
        effect
        for effect in state.persisting_effects
        if _effect_payload_kind(effect) == "source_backed_reroll_permission"
    )
    state.record_persisting_effect(
        replace(
            reroll_effect,
            effect_id=f"{reroll_effect.effect_id}:duplicate",
        )
    )
    deduplicated_context = source_backed_reroll_permission_context_for_unit(
        state=state,
        player_id="player-a",
        unit_instance_id=SPACE_MARINES_UNIT_ID,
        roll_type="attack_sequence.hit",
        timing_window="attack_sequence.hit",
        target_unit_instance_id=ENEMY_TARGET_ID,
    )
    assert deduplicated_context == permission_context

    malformed_lifecycle = _battle_ready_lifecycle()
    malformed_request = malformed_lifecycle.advance_until_decision_or_terminal().decision_request
    assert malformed_request is not None
    malformed_lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-space-marines-source-backed-malformed-target",
            request=malformed_request,
            selected_option_id=f"space_marines:oath_of_moment:{ENEMY_TARGET_ID}",
        )
    )
    malformed_state = _require_state(malformed_lifecycle)
    malformed_effect = next(
        effect
        for effect in malformed_state.persisting_effects
        if _effect_payload_kind(effect) == "source_backed_reroll_permission"
    )
    malformed_effect_payload = cast(dict[str, JsonValue], malformed_effect.effect_payload).copy()
    malformed_source_payload = cast(
        dict[str, JsonValue],
        malformed_effect_payload["source_payload"],
    ).copy()
    malformed_source_payload["target_unit_instance_id"] = ""
    malformed_effect_payload["source_payload"] = malformed_source_payload
    malformed_state.record_persisting_effect(
        replace(
            malformed_effect,
            effect_id=f"{malformed_effect.effect_id}:malformed-target",
            effect_payload=malformed_effect_payload,
        )
    )
    with pytest.raises(GameLifecycleError, match="target_unit_instance_id must be a string"):
        source_backed_reroll_permission_context_for_unit(
            state=malformed_state,
            player_id="player-a",
            unit_instance_id=SPACE_MARINES_UNIT_ID,
            roll_type="attack_sequence.hit",
            timing_window="attack_sequence.hit",
            target_unit_instance_id=ENEMY_OTHER_ID,
        )


def test_oath_wound_modifier_applies_only_for_codex_detachment_target() -> None:
    lifecycle = _battle_ready_lifecycle()
    request = lifecycle.advance_until_decision_or_terminal().decision_request
    assert request is not None
    lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-space-marines-wound-bonus-target",
            request=request,
            selected_option_id=f"space_marines:oath_of_moment:{ENEMY_TARGET_ID}",
        )
    )
    state = _require_state(lifecycle)

    assert (
        army_rule.oath_of_moment_wound_roll_modifier(
            _wound_context(state=state, target_unit_id=ENEMY_TARGET_ID)
        )
        == 1
    )
    assert (
        army_rule.oath_of_moment_wound_roll_modifier(
            _wound_context(state=state, target_unit_id=ENEMY_OTHER_ID)
        )
        == 0
    )
    with pytest.raises(GameLifecycleError, match="requires context"):
        army_rule.oath_of_moment_wound_roll_modifier(cast(WoundRollModifierContext, object()))
    assert (
        army_rule.oath_of_moment_wound_roll_modifier(
            _wound_context(
                state=state,
                target_unit_id=ENEMY_TARGET_ID,
                source_phase=BattlePhase.COMMAND,
            )
        )
        == 0
    )
    assert (
        army_rule.oath_of_moment_wound_roll_modifier(
            _wound_context(
                state=state,
                target_unit_id=SPACE_MARINES_UNIT_ID,
                attacking_unit_id=ENEMY_TARGET_ID,
            )
        )
        == 0
    )
    with pytest.raises(GameLifecycleError, match="attacking unit is unknown"):
        army_rule.oath_of_moment_wound_roll_modifier(
            _wound_context(
                state=state,
                target_unit_id=ENEMY_TARGET_ID,
                attacking_unit_id="army-alpha:missing",
            )
        )

    space_marine_army = state.army_definition_for_player("player-a")
    assert space_marine_army is not None
    state.army_definitions = [
        replace(
            army,
            units=tuple(
                replace(unit, faction_keywords=(*unit.faction_keywords, "DARK ANGELS"))
                if unit.unit_instance_id == SPACE_MARINES_UNIT_ID
                else unit
                for unit in army.units
            ),
        )
        if army.player_id == "player-a"
        else army
        for army in state.army_definitions
    ]
    assert (
        army_rule.oath_of_moment_wound_roll_modifier(
            _wound_context(state=state, target_unit_id=ENEMY_TARGET_ID)
        )
        == 0
    )

    non_astartes_lifecycle = _battle_ready_lifecycle()
    non_astartes_request = (
        non_astartes_lifecycle.advance_until_decision_or_terminal().decision_request
    )
    assert non_astartes_request is not None
    non_astartes_lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-space-marines-non-astartes-attacker",
            request=non_astartes_request,
            selected_option_id=f"space_marines:oath_of_moment:{ENEMY_TARGET_ID}",
        )
    )
    non_astartes_state = _require_state(non_astartes_lifecycle)
    non_astartes_state.army_definitions = [
        replace(
            army,
            units=tuple(
                replace(unit, faction_keywords=())
                if unit.unit_instance_id == SPACE_MARINES_UNIT_ID
                else unit
                for unit in army.units
            ),
        )
        if army.player_id == "player-a"
        else army
        for army in non_astartes_state.army_definitions
    ]
    assert (
        army_rule.oath_of_moment_wound_roll_modifier(
            _wound_context(state=non_astartes_state, target_unit_id=ENEMY_TARGET_ID)
        )
        == 0
    )

    keyword_army_lifecycle = _battle_ready_lifecycle()
    keyword_state = _require_state(keyword_army_lifecycle)
    keyword_state.army_definitions = [
        replace(
            army,
            detachment_selection=replace(
                army.detachment_selection,
                faction_id="phase17g-not-space-marines",
            ),
        )
        if army.player_id == "player-a"
        else army
        for army in keyword_state.army_definitions
    ]
    assert (
        army_rule.oath_of_moment_target_request(
            CommandPhaseStartRequestContext(
                state=keyword_state,
                decisions=keyword_army_lifecycle.decision_controller,
                active_player_id="player-a",
            )
        )
        is not None
    )


def test_space_marine_chapters_enforce_black_templars_and_space_wolves() -> None:
    catalog = _space_marines_roster_catalog()
    request = _space_marine_muster_request(
        catalog,
        unit_selection_ids=(
            "black-templars-crusaders",
            "librarian",
            "gladiator-lancer",
            "space-wolves-pack",
            "apothecary",
        ),
    )

    report = validate_roster_legality(catalog=catalog, request=request)
    codes = _violation_codes(report.violations)

    assert "space_marines_multiple_chapters" in codes
    assert "space_marines_black_templars_psyker_forbidden" in codes
    assert "space_marines_black_templars_vehicle_keyword_required" in codes
    assert "space_marines_space_wolves_unit_forbidden" in codes


def test_space_marine_chapters_enforce_deathwatch_restrictions() -> None:
    catalog = _space_marines_roster_catalog()
    request = _space_marine_muster_request(
        catalog,
        unit_selection_ids=(
            "deathwatch-veterans",
            "intercessors",
            "agents-deathwatch",
            "kill-team-cassius",
            "tactical-squad",
        ),
    )

    report = validate_roster_legality(catalog=catalog, request=request)
    codes = _violation_codes(report.violations)

    assert "space_marines_deathwatch_other_chapter_forbidden" in codes
    assert "space_marines_deathwatch_agents_unit_forbidden" in codes
    assert "space_marines_deathwatch_unit_forbidden" in codes
    assert all(
        violation.violation_code != "space_marines_deathwatch_agents_unit_forbidden"
        for violation in report.violations
        if violation.unit_selection_id == "kill-team-cassius"
    )


def _battle_ready_lifecycle() -> GameLifecycle:
    config = _space_marines_config()
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    state = _require_state(lifecycle)
    for army in _mustered_armies(config):
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase17g-space-marines-battlefield",
        armies=tuple(state.army_definitions),
    )
    state.record_battlefield_state(scenario.battlefield_state)
    state.record_secondary_mission_choice(_fixed_secondary_choice(player_id="player-a"))
    state.record_secondary_mission_choice(_fixed_secondary_choice(player_id="player-b"))
    _complete_setup_through_gate(state=state, config=config)
    _runtime_content_bundle(lifecycle)
    return lifecycle


def _space_marines_config() -> GameConfig:
    catalog = _space_marines_lifecycle_catalog()
    return GameConfig(
        game_id="phase17g-space-marines-lifecycle-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
            descriptor_version="core-v2-phase17g-space-marines-test",
        ),
        army_catalog=catalog,
        army_muster_requests=(
            ArmyMusterRequest(
                army_id="army-alpha",
                player_id="player-a",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id=army_rule.SPACE_MARINES_FACTION_ID,
                    detachment_ids=("gladius-task-force",),
                ),
                force_disposition_id="phase17g-force",
                unit_selections=(_unit_selection("intercessors", SPACE_MARINES_DATASHEET_ID),),
            ),
            ArmyMusterRequest(
                army_id="army-beta",
                player_id="player-b",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id="core-marine-force",
                    detachment_ids=("core-combined-arms",),
                ),
                force_disposition_id="purge-the-foe",
                unit_selections=(
                    _unit_selection("enemy-unit", "core-intercessor-like-infantry"),
                    _unit_selection("enemy-unit-2", "core-intercessor-like-infantry"),
                ),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down"),
        mission_setup=_mission_setup(),
    )


def _space_marines_lifecycle_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    return replace(
        base_catalog,
        datasheets=(
            *base_catalog.datasheets,
            _datasheet(
                base_datasheet,
                datasheet_id=SPACE_MARINES_DATASHEET_ID,
                name="Intercessor Squad",
                keywords=("INFANTRY", "BATTLELINE"),
                faction_keywords=("ADEPTUS ASTARTES",),
            ),
        ),
        factions=(
            *base_catalog.factions,
            FactionDefinition(
                faction_id=army_rule.SPACE_MARINES_FACTION_ID,
                name="Space Marines",
                faction_keywords=("ADEPTUS ASTARTES",),
                source_ids=("phase17g:space-marines:faction",),
            ),
        ),
        detachments=(
            *base_catalog.detachments,
            DetachmentDefinition(
                detachment_id="gladius-task-force",
                name="Gladius Task Force",
                faction_id=army_rule.SPACE_MARINES_FACTION_ID,
                detachment_point_cost=1,
                unit_datasheet_ids=(SPACE_MARINES_DATASHEET_ID,),
                force_disposition_ids=("phase17g-force",),
                source_ids=("phase17g:space-marines:detachment:gladius-task-force",),
            ),
        ),
    )


def _space_marines_roster_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    datasheets = tuple(
        _datasheet(base_datasheet, datasheet_id=datasheet_id, **payload)
        for datasheet_id, payload in _roster_datasheet_payloads().items()
    )
    return ArmyCatalog(
        catalog_id="phase17g-space-marines-roster-catalog",
        ruleset_id=base_catalog.ruleset_id,
        source_package_id="phase17g-space-marines-roster-source",
        datasheets=datasheets,
        wargear=base_catalog.wargear,
        factions=(
            FactionDefinition(
                faction_id=army_rule.SPACE_MARINES_FACTION_ID,
                name="Space Marines",
                faction_keywords=("ADEPTUS ASTARTES",),
                source_ids=("phase17g:space-marines:faction",),
            ),
            FactionDefinition(
                faction_id="agents-of-the-imperium",
                name="Agents of the Imperium",
                faction_keywords=("AGENTS OF THE IMPERIUM",),
                source_ids=("phase17g:agents-of-the-imperium:faction",),
            ),
        ),
        detachments=(
            DetachmentDefinition(
                detachment_id="gladius-task-force",
                name="Gladius Task Force",
                faction_id=army_rule.SPACE_MARINES_FACTION_ID,
                detachment_point_cost=1,
                unit_datasheet_ids=tuple(_roster_datasheet_payloads()),
                force_disposition_ids=("phase17g-force",),
                source_ids=("phase17g:space-marines:detachment:gladius-task-force",),
            ),
        ),
        source_ids=("phase17g:space-marines:roster-catalog",),
    )


def _roster_datasheet_payloads() -> dict[str, RosterDatasheetPayload]:
    return {
        "black-templars-crusaders": {
            "name": "Black Templars Crusaders",
            "keywords": ("CHARACTER", "INFANTRY"),
            "faction_keywords": ("ADEPTUS ASTARTES", "BLACK TEMPLARS"),
        },
        "librarian": {
            "name": "Librarian",
            "keywords": ("CHARACTER", "INFANTRY", "PSYKER"),
            "faction_keywords": ("ADEPTUS ASTARTES",),
        },
        "gladiator-lancer": {
            "name": "Gladiator Lancer",
            "keywords": ("VEHICLE",),
            "faction_keywords": ("ADEPTUS ASTARTES",),
        },
        "space-wolves-pack": {
            "name": "Space Wolves Pack",
            "keywords": ("CHARACTER", "INFANTRY"),
            "faction_keywords": ("ADEPTUS ASTARTES", "SPACE WOLVES"),
        },
        "apothecary": {
            "name": "Apothecary",
            "keywords": ("CHARACTER", "INFANTRY"),
            "faction_keywords": ("ADEPTUS ASTARTES",),
        },
        "deathwatch-veterans": {
            "name": "Deathwatch Veterans",
            "keywords": ("CHARACTER", "INFANTRY"),
            "faction_keywords": ("ADEPTUS ASTARTES", "DEATHWATCH"),
        },
        "intercessors": {
            "name": "Intercessor Squad",
            "keywords": ("CHARACTER", "INFANTRY"),
            "faction_keywords": ("ADEPTUS ASTARTES",),
        },
        "agents-deathwatch": {
            "name": "Deathwatch Imperial Agent",
            "keywords": ("CHARACTER", "INFANTRY", "DEATHWATCH"),
            "faction_keywords": ("AGENTS OF THE IMPERIUM", "DEATHWATCH"),
        },
        "kill-team-cassius": {
            "name": "Kill Team Cassius",
            "keywords": ("CHARACTER", "INFANTRY", "DEATHWATCH"),
            "faction_keywords": ("AGENTS OF THE IMPERIUM", "DEATHWATCH"),
        },
        "tactical-squad": {
            "name": "Tactical Squad",
            "keywords": ("CHARACTER", "INFANTRY"),
            "faction_keywords": ("ADEPTUS ASTARTES",),
        },
    }


def _space_marine_muster_request(
    catalog: ArmyCatalog,
    *,
    unit_selection_ids: tuple[str, ...],
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id="army-alpha",
        player_id="player-a",
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=army_rule.SPACE_MARINES_FACTION_ID,
            detachment_ids=("gladius-task-force",),
        ),
        force_disposition_id="phase17g-force",
        unit_selections=tuple(
            _unit_selection(selection_id, selection_id) for selection_id in unit_selection_ids
        ),
        warlord_selection=WarlordSelection(
            unit_selection_id=unit_selection_ids[0],
            source_id="phase17g:space-marines:test-warlord",
        ),
    )


def _datasheet(
    base_datasheet: DatasheetDefinition,
    *,
    datasheet_id: str,
    name: str,
    keywords: tuple[str, ...],
    faction_keywords: tuple[str, ...],
) -> DatasheetDefinition:
    return replace(
        base_datasheet,
        datasheet_id=datasheet_id,
        name=name,
        keywords=DatasheetKeywordSet(
            keywords=keywords,
            faction_keywords=faction_keywords,
        ),
        source_ids=(f"phase17g:space-marines:datasheet:{datasheet_id}",),
    )


def _unit_selection(unit_selection_id: str, datasheet_id: str) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id=datasheet_id,
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id="core-intercessor-like",
                model_count=5,
            ),
        ),
    )


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )


def _fixed_secondary_choice(*, player_id: str) -> SecondaryMissionChoice:
    return SecondaryMissionChoice(
        player_id=player_id,
        mode=SecondaryMissionMode.FIXED,
        fixed_mission_ids=("assassination", "bring_it_down"),
    )


def _complete_setup_through_gate(*, state: GameState, config: GameConfig) -> None:
    final_setup_step = state.setup_sequence[-1]
    while state.current_setup_step is not final_setup_step:
        state.complete_current_setup_step()
    SetupCompletionGate().complete_setup_and_enter_battle(
        state=state,
        decisions=DecisionController(),
        config=config,
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )


def _wound_context(
    *,
    state: GameState,
    target_unit_id: str,
    attacking_unit_id: str = SPACE_MARINES_UNIT_ID,
    source_phase: BattlePhase = BattlePhase.SHOOTING,
) -> WoundRollModifierContext:
    return WoundRollModifierContext(
        state=state,
        source_phase=source_phase,
        attacking_unit_instance_id=attacking_unit_id,
        attacker_model_instance_id=f"{attacking_unit_id}:model-001",
        target_unit_instance_id=target_unit_id,
        weapon_profile=_weapon_profile(),
        strength=4,
        toughness=4,
    )


def _weapon_profile() -> WeaponProfile:
    return WeaponProfile(
        profile_id="phase17g-space-marines-bolt-rifle",
        name="Bolt rifle",
        range_profile=RangeProfile.distance(24),
        attack_profile=AttackProfile.fixed(1),
        skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 3),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
        damage_profile=DamageProfile.fixed(1),
        source_ids=("phase17g:space-marines:test-weapon",),
    )


def _require_state(lifecycle: GameLifecycle) -> GameState:
    if lifecycle.state is None:
        raise AssertionError("lifecycle state is required")
    return lifecycle.state


def _runtime_content_bundle(lifecycle: GameLifecycle) -> RuntimeContentBundle:
    require_runtime_content_bundle = cast(
        Callable[[], RuntimeContentBundle],
        object.__getattribute__(lifecycle, "_require_runtime_content_bundle"),
    )
    return require_runtime_content_bundle()


def _violation_codes(violations: tuple[RosterLegalityViolation, ...]) -> set[str]:
    return {violation.violation_code for violation in violations}


def _effect_payload_kind(effect: PersistingEffect) -> str | None:
    payload = effect.effect_payload
    if not isinstance(payload, dict):
        return None
    kind = payload.get("effect_kind")
    return kind if isinstance(kind, str) else None
