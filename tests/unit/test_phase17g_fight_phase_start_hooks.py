from __future__ import annotations

from typing import cast

import pytest
from tests.phase11c_command_phase_helpers import (
    battle_state,
)

from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.faction_content.bundle_validation import (
    validate_identifier,
    validate_tuple,
)
from warhammer40k_core.engine.fight_phase_start_hooks import (
    SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE,
    FightPhaseStartHookBinding,
    FightPhaseStartHookRegistry,
    FightPhaseStartRequestContext,
    FightPhaseStartRequestHandler,
    FightPhaseStartResultContext,
    FightPhaseStartResultHandler,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)


def test_fight_phase_start_hook_registry_routes_one_request_and_one_result() -> None:
    state, decisions = _fight_phase_state()
    request = _fight_start_request("hook-a")

    registry = FightPhaseStartHookRegistry.from_bindings(
        (
            FightPhaseStartHookBinding(
                hook_id="hook-b",
                source_id="source-b",
                request_handler=lambda _context: None,
                result_handler=lambda _context: False,
            ),
            FightPhaseStartHookBinding(
                hook_id="hook-a",
                source_id="source-a",
                request_handler=lambda _context: request,
                result_handler=lambda context: context.request.request_id == request.request_id,
            ),
        )
    )

    assert [binding.hook_id for binding in registry.all_bindings()] == ["hook-a", "hook-b"]
    resolved_request = registry.next_request_for(
        FightPhaseStartRequestContext(state=state, decisions=decisions)
    )
    result = DecisionResult.for_request(
        result_id="fight-start-result",
        request=request,
        selected_option_id="use",
    )

    assert resolved_request == request
    assert (
        registry.apply_result(
            FightPhaseStartResultContext(
                state=state,
                decisions=decisions,
                request=request,
                result=result,
            )
        )
        is True
    )


def test_fight_phase_start_hook_registry_allows_empty_and_status_results() -> None:
    state, decisions = _fight_phase_state()
    request = _fight_start_request("hook-a")
    result = DecisionResult.for_request(
        result_id="fight-start-result",
        request=request,
        selected_option_id="use",
    )
    context = FightPhaseStartResultContext(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
    )
    status = LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
    )

    assert (
        FightPhaseStartHookRegistry.empty().next_request_for(
            FightPhaseStartRequestContext(state=state, decisions=decisions)
        )
        is None
    )
    assert FightPhaseStartHookRegistry.empty().apply_result(context) is False
    assert (
        FightPhaseStartHookRegistry.from_bindings(
            (
                FightPhaseStartHookBinding(
                    hook_id="hook-a",
                    source_id="source-a",
                    result_handler=lambda _context: status,
                ),
            )
        ).apply_result(context)
        == status
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION


def test_fight_phase_start_hook_registry_rejects_invalid_bindings() -> None:
    with pytest.raises(GameLifecycleError, match=r"requires a handler"):
        FightPhaseStartHookBinding(hook_id="hook-a", source_id="source-a")
    with pytest.raises(GameLifecycleError, match=r"hook_id must not be empty"):
        FightPhaseStartHookBinding(
            hook_id=" ",
            source_id="source-a",
            request_handler=lambda _context: None,
        )
    with pytest.raises(GameLifecycleError, match=r"request_handler must be callable"):
        FightPhaseStartHookBinding(
            hook_id="hook-a",
            source_id="source-a",
            request_handler=cast(FightPhaseStartRequestHandler, object()),
        )
    with pytest.raises(GameLifecycleError, match=r"result_handler must be callable"):
        FightPhaseStartHookBinding(
            hook_id="hook-a",
            source_id="source-a",
            result_handler=cast(FightPhaseStartResultHandler, object()),
        )
    with pytest.raises(GameLifecycleError, match=r"bindings must be a tuple"):
        FightPhaseStartHookRegistry.from_bindings(cast(tuple[FightPhaseStartHookBinding, ...], []))
    with pytest.raises(GameLifecycleError, match=r"requires hook bindings"):
        FightPhaseStartHookRegistry.from_bindings(
            cast(tuple[FightPhaseStartHookBinding, ...], (object(),))
        )
    with pytest.raises(GameLifecycleError, match=r"hook IDs must be unique"):
        FightPhaseStartHookRegistry.from_bindings(
            (
                FightPhaseStartHookBinding(
                    hook_id="hook-a",
                    source_id="source-a",
                    request_handler=lambda _context: None,
                ),
                FightPhaseStartHookBinding(
                    hook_id="hook-a",
                    source_id="source-b",
                    request_handler=lambda _context: None,
                ),
            )
        )


def test_fight_phase_start_hook_contexts_reject_wrong_state_or_request() -> None:
    state, decisions = _fight_phase_state()
    request = _fight_start_request("hook-a")
    result = DecisionResult.for_request(
        result_id="fight-start-result",
        request=request,
        selected_option_id="use",
    )

    with pytest.raises(GameLifecycleError, match=r"state must be GameState"):
        FightPhaseStartRequestContext(
            state=cast(GameState, object()),
            decisions=decisions,
        )
    with pytest.raises(GameLifecycleError, match=r"decisions must be DecisionController"):
        FightPhaseStartRequestContext(
            state=state,
            decisions=cast(DecisionController, object()),
        )
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    with pytest.raises(GameLifecycleError, match=r"require Fight phase"):
        FightPhaseStartRequestContext(state=state, decisions=decisions)
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    state.stage = GameLifecycleStage.SETUP
    with pytest.raises(GameLifecycleError, match=r"require battle stage"):
        FightPhaseStartResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )

    state, decisions = _fight_phase_state()
    with pytest.raises(GameLifecycleError, match=r"state must be GameState"):
        FightPhaseStartResultContext(
            state=cast(GameState, object()),
            decisions=decisions,
            request=request,
            result=result,
        )
    with pytest.raises(GameLifecycleError, match=r"decisions must be DecisionController"):
        FightPhaseStartResultContext(
            state=state,
            decisions=cast(DecisionController, object()),
            request=request,
            result=result,
        )
    with pytest.raises(GameLifecycleError, match=r"request must be DecisionRequest"):
        FightPhaseStartResultContext(
            state=state,
            decisions=decisions,
            request=cast(DecisionRequest, object()),
            result=result,
        )
    with pytest.raises(GameLifecycleError, match=r"result must be DecisionResult"):
        FightPhaseStartResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=cast(DecisionResult, object()),
        )

    wrong_request = DecisionRequest(
        request_id="wrong-request",
        decision_type="select_other",
        actor_id="player-a",
        payload={},
        options=(DecisionOption(option_id="use", label="Use"),),
    )
    wrong_result = DecisionResult.for_request(
        result_id="wrong-result",
        request=wrong_request,
        selected_option_id="use",
    )
    with pytest.raises(GameLifecycleError, match=r"request decision_type drift"):
        FightPhaseStartResultContext(
            state=state,
            decisions=decisions,
            request=wrong_request,
            result=wrong_result,
        )


def test_fight_phase_start_hook_registry_rejects_bad_handler_outputs_and_ambiguity() -> None:
    state, decisions = _fight_phase_state()
    request = _fight_start_request("hook-a")
    request_context = FightPhaseStartRequestContext(state=state, decisions=decisions)
    result = DecisionResult.for_request(
        result_id="fight-start-result",
        request=request,
        selected_option_id="use",
    )
    result_context = FightPhaseStartResultContext(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
    )

    with pytest.raises(GameLifecycleError, match=r"request hooks require context"):
        FightPhaseStartHookRegistry.empty().next_request_for(
            cast(FightPhaseStartRequestContext, object())
        )
    with pytest.raises(GameLifecycleError, match=r"result hooks require context"):
        FightPhaseStartHookRegistry.empty().apply_result(
            cast(FightPhaseStartResultContext, object())
        )
    with pytest.raises(GameLifecycleError, match=r"must return DecisionRequest or None"):
        FightPhaseStartHookRegistry.from_bindings(
            (
                FightPhaseStartHookBinding(
                    hook_id="hook-a",
                    source_id="source-a",
                    request_handler=lambda _context: cast(DecisionRequest, object()),
                ),
            )
        ).next_request_for(request_context)
    with pytest.raises(GameLifecycleError, match=r"multiple simultaneous requests"):
        FightPhaseStartHookRegistry.from_bindings(
            (
                FightPhaseStartHookBinding(
                    hook_id="hook-a",
                    source_id="source-a",
                    request_handler=lambda _context: request,
                ),
                FightPhaseStartHookBinding(
                    hook_id="hook-b",
                    source_id="source-b",
                    request_handler=lambda _context: _fight_start_request("hook-b"),
                ),
            )
        ).next_request_for(request_context)
    with pytest.raises(GameLifecycleError, match=r"must return bool or status"):
        FightPhaseStartHookRegistry.from_bindings(
            (
                FightPhaseStartHookBinding(
                    hook_id="hook-a",
                    source_id="source-a",
                    result_handler=lambda _context: cast(bool, object()),
                ),
            )
        ).apply_result(result_context)
    with pytest.raises(GameLifecycleError, match=r"handled by multiple hooks"):
        FightPhaseStartHookRegistry.from_bindings(
            (
                FightPhaseStartHookBinding(
                    hook_id="hook-a",
                    source_id="source-a",
                    result_handler=lambda _context: True,
                ),
                FightPhaseStartHookBinding(
                    hook_id="hook-b",
                    source_id="source-b",
                    result_handler=lambda _context: True,
                ),
            )
        ).apply_result(result_context)


def test_fight_phase_start_hook_and_bundle_validation_guards() -> None:
    state, decisions = _fight_phase_state()
    request = _fight_start_request("hook-a")
    result = DecisionResult.for_request(
        result_id="fight-start-result",
        request=request,
        selected_option_id="use",
    )

    with pytest.raises(GameLifecycleError, match=r"source_id must be a string"):
        FightPhaseStartHookBinding(
            hook_id="hook-a",
            source_id=cast(str, object()),
            request_handler=lambda _context: None,
        )
    assert (
        FightPhaseStartHookRegistry.from_bindings(
            (
                FightPhaseStartHookBinding(
                    hook_id="hook-a",
                    source_id="source-a",
                    result_handler=lambda _context: False,
                ),
            )
        ).next_request_for(FightPhaseStartRequestContext(state=state, decisions=decisions))
        is None
    )
    assert (
        FightPhaseStartHookRegistry.from_bindings(
            (
                FightPhaseStartHookBinding(
                    hook_id="hook-a",
                    source_id="source-a",
                    request_handler=lambda _context: None,
                ),
            )
        ).apply_result(
            FightPhaseStartResultContext(
                state=state,
                decisions=decisions,
                request=request,
                result=result,
            )
        )
        is False
    )

    with pytest.raises(GameLifecycleError, match=r"test tuple must be a tuple"):
        validate_tuple("test tuple", cast(tuple[str, ...], []), str)
    with pytest.raises(GameLifecycleError, match=r"test tuple contains invalid values"):
        validate_tuple("test tuple", (object(),), str)
    with pytest.raises(GameLifecycleError, match=r"must not be empty"):
        validate_identifier("test id", " ")


def _fight_phase_state() -> tuple[GameState, DecisionController]:
    state = battle_state()
    state.stage = GameLifecycleStage.BATTLE
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    return state, DecisionController()


def _set_current_battle_phase(state: GameState, phase: BattlePhase) -> None:
    state.battle_phase_index = state.battle_phase_sequence.index(phase)


def _fight_start_request(hook_id: str) -> DecisionRequest:
    return DecisionRequest(
        request_id=f"fight-start-request:{hook_id}",
        decision_type=SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE,
        actor_id="player-a",
        payload={"hook_id": hook_id},
        options=(
            DecisionOption(
                option_id="use",
                label="Use",
                payload={"hook_id": hook_id, "use": True},
            ),
        ),
    )
