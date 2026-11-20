from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[2]
ENGINE_ROOT = ROOT / "src" / "warhammer40k_core" / "engine"

_SHARED_RESOLUTION_FUNCTIONS = frozenset(
    {
        "resolve_battle_shock_test_with_optional_reroll",
        "apply_battle_shock_reroll_resolution_decision",
        "record_battle_shock_result_and_outcome_events",
        "resolve_battle_shock_after_modifier_choices",
    }
)


class _Policy(StrEnum):
    BOTH_FIELDS = "both_fields"
    FORWARD_WHOLE_RESULT = "forward_whole_result"
    EXPLICIT_PARENT_PROOF = "explicit_parent_proof"


@dataclass(frozen=True, slots=True)
class _ExpectedCall:
    policy: _Policy
    proof: str = ""


_EXPECTED_CALLS = {
    (
        "battle_shock_test_service.py",
        "resolve_battle_shock_test",
        "resolve_battle_shock_after_modifier_choices",
    ): _ExpectedCall(_Policy.FORWARD_WHOLE_RESULT),
    (
        "battle_shock_modifier_continuation.py",
        "resolve_battle_shock_after_modifier_choices",
        "resolve_battle_shock_test_with_optional_reroll",
    ): _ExpectedCall(_Policy.FORWARD_WHOLE_RESULT),
    (
        "battle_shock_modifier_continuation.py",
        "resume_battle_shock_modifier_choices",
        "resolve_battle_shock_after_modifier_choices",
    ): _ExpectedCall(_Policy.FORWARD_WHOLE_RESULT),
    (
        "battle_shock_test_service.py",
        "apply_stratagem_battle_shock_reroll_decision",
        "apply_battle_shock_reroll_resolution_decision",
    ): _ExpectedCall(
        _Policy.EXPLICIT_PARENT_PROOF,
        "A Stratagem Battle-shock occurrence has no sibling-effect parent; the outcome provider "
        "owns any queued request and lifecycle queue dispatch resumes globally.",
    ),
    (
        "catalog_selected_target_battle_shock.py",
        "resolve_selected_target_battle_shock_effect",
        "resolve_battle_shock_after_modifier_choices",
    ): _ExpectedCall(_Policy.FORWARD_WHOLE_RESULT),
    (
        "catalog_selected_target_battle_shock_reroll.py",
        "apply_catalog_selected_target_battle_shock_reroll_decision",
        "apply_battle_shock_reroll_resolution_decision",
    ): _ExpectedCall(_Policy.FORWARD_WHOLE_RESULT),
    (
        "unit_move_completed_hooks.py",
        "apply_unit_move_completed_battle_shock_reroll_decision",
        "apply_battle_shock_reroll_resolution_decision",
    ): _ExpectedCall(
        _Policy.EXPLICIT_PARENT_PROOF,
        "Move-completed Battle-shock processing is keyed by resolved event evidence; it has no "
        "later sibling effect, and provider requests re-enter through the event cursor.",
    ),
    (
        "unit_move_completed_hooks.py",
        "resolve_battle_shock_effect",
        "resolve_battle_shock_after_modifier_choices",
    ): _ExpectedCall(_Policy.BOTH_FIELDS),
    (
        "phases/command.py",
        "apply_decision",
        "apply_battle_shock_reroll_resolution_decision",
    ): _ExpectedCall(
        _Policy.EXPLICIT_PARENT_PROOF,
        "The command-start source hook owns its ordered parent state and receives the nested "
        "result through apply_nested_result; provider requests remain the lifecycle queue head.",
    ),
    (
        "phases/command.py",
        "_resolve_battle_shock_step",
        "resolve_battle_shock_test_with_optional_reroll",
    ): _ExpectedCall(_Policy.BOTH_FIELDS),
    (
        "phases/command.py",
        "_resolve_battle_shock_step",
        "record_battle_shock_result_and_outcome_events",
    ): _ExpectedCall(_Policy.BOTH_FIELDS),
    (
        "phases/command_battle_shock_rerolls.py",
        "apply_battle_shock_reroll_decision",
        "apply_battle_shock_reroll_resolution_decision",
    ): _ExpectedCall(
        _Policy.EXPLICIT_PARENT_PROOF,
        "The Command step stores completion by Battle-shock request ID and has no sibling-effect "
        "remainder; provider requests are independently queue-owned.",
    ),
    (
        "phases/movement_options_dice.py",
        "_resolve_forced_desperate_escape_battle_shock",
        "resolve_battle_shock_after_modifier_choices",
    ): _ExpectedCall(_Policy.FORWARD_WHOLE_RESULT),
    (
        "phases/movement_resolution_flow.py",
        "_apply_desperate_escape_battle_shock_reroll_decision",
        "apply_battle_shock_reroll_resolution_decision",
    ): _ExpectedCall(_Policy.FORWARD_WHOLE_RESULT),
    (
        "phases/movement_resolution_flow.py",
        "_apply_forced_desperate_escape_battle_shock_reroll_decision",
        "apply_battle_shock_reroll_resolution_decision",
    ): _ExpectedCall(_Policy.FORWARD_WHOLE_RESULT),
}


def test_every_shared_battle_shock_resolution_caller_has_an_explicit_parent_policy() -> None:
    calls = _shared_resolution_calls()

    assert set(calls) == set(_EXPECTED_CALLS)
    for key, node in calls.items():
        expected = _EXPECTED_CALLS[key]
        function = _enclosing_function(node, calls.parents_by_node)
        assert function is not None
        if expected.policy is _Policy.BOTH_FIELDS:
            assigned_name = _assigned_name(node, calls.parents_by_node)
            assert assigned_name is not None, f"{key} must bind the typed resolution result"
            attributes = {
                child.attr
                for child in ast.walk(function)
                if isinstance(child, ast.Attribute)
                and isinstance(child.value, ast.Name)
                and child.value.id == assigned_name
            }
            assert {"resolved_payload", "pending_status"} <= attributes, (
                f"{key} must consume both BattleShockResolutionResult fields"
            )
        elif expected.policy is _Policy.FORWARD_WHOLE_RESULT:
            assert _whole_result_is_forwarded(node, calls.parents_by_node), (
                f"{key} must forward the complete BattleShockResolutionResult"
            )
        else:
            assert len(expected.proof) >= 80, f"{key} lacks a substantive no-local-parent proof"


def test_shared_battle_shock_parent_continuations_consume_both_result_fields() -> None:
    for module, function_name, argument_name in (
        (
            "catalog_selected_target_battle_shock_reroll.py",
            "continue_catalog_selected_target_battle_shock_resolution",
            "battle_shock_resolution",
        ),
        (
            "phases/movement_battle_shock_continuation.py",
            "record_desperate_escape_battle_shock_resolution",
            "resolution",
        ),
    ):
        tree = ast.parse((ENGINE_ROOT / module).read_text(encoding="utf-8"))
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == function_name
        )
        argument = next(arg for arg in function.args.kwonlyargs if arg.arg == argument_name)
        assert isinstance(argument.annotation, ast.Name)
        assert argument.annotation.id == "BattleShockResolutionResult"
        attributes = {
            node.attr
            for node in ast.walk(function)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == argument_name
        }
        assert {"resolved_payload", "pending_status"} <= attributes, function_name


class _CallInventory(dict[tuple[str, str, str], ast.Call]):
    parents_by_node: dict[ast.AST, ast.AST]


def _shared_resolution_calls() -> _CallInventory:
    inventory = _CallInventory()
    inventory.parents_by_node = {}
    for path in sorted(ENGINE_ROOT.rglob("*.py")):
        if path.name == "battle_shock_resolution.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parents = {
            child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)
        }
        inventory.parents_by_node.update(parents)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            callee = _callee_name(node)
            if callee not in _SHARED_RESOLUTION_FUNCTIONS:
                continue
            function = _enclosing_function(node, parents)
            if function is None or function.name == callee:
                continue
            key = (path.relative_to(ENGINE_ROOT).as_posix(), function.name, callee)
            assert key not in inventory, f"Duplicate shared Battle-shock call policy key: {key}"
            inventory[key] = node
    return inventory


def _callee_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _enclosing_function(
    node: ast.AST,
    parents: dict[ast.AST, ast.AST],
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    current: ast.AST | None = node
    while current is not None:
        if isinstance(current, ast.FunctionDef | ast.AsyncFunctionDef):
            return current
        current = parents.get(current)
    return None


def _assigned_name(node: ast.Call, parents: dict[ast.AST, ast.AST]) -> str | None:
    parent = parents.get(node)
    if not isinstance(parent, ast.Assign) or len(parent.targets) != 1:
        return None
    target = parent.targets[0]
    return target.id if isinstance(target, ast.Name) else None


def _whole_result_is_forwarded(node: ast.Call, parents: dict[ast.AST, ast.AST]) -> bool:
    parent = parents.get(node)
    if isinstance(parent, ast.Return):
        return True
    assigned_name = _assigned_name(node, parents)
    if assigned_name is None:
        return False
    function = _enclosing_function(node, parents)
    if function is None:
        return False
    return any(
        isinstance(child, ast.Name)
        and child.id == assigned_name
        and isinstance(parents.get(child), ast.keyword)
        and cast(ast.keyword, parents[child]).arg in {"resolution", "battle_shock_resolution"}
        for child in ast.walk(function)
    )


def test_indexed_placement_producer_keeps_exact_and_causal_authority() -> None:
    import pytest

    from tests.phase11c_command_phase_helpers import battle_state
    from warhammer40k_core.engine.battle_shock_hooks import (
        BattleShockPendingOutcomeAuthorityContext,
    )
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
    from warhammer40k_core.engine.decision_result import DecisionResult
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import (
        army_rule,
        battle_shock_outcome_authority,
    )
    from warhammer40k_core.engine.healing import (
        SELECT_HEALING_MODEL_DECISION_TYPE,
        HealingEffect,
        HealingStepKind,
    )
    from warhammer40k_core.engine.mutation_decision_authority import (
        validate_mutation_decision_closure,
    )
    from warhammer40k_core.engine.phase import GameLifecycleError

    state = battle_state()
    hook_id = army_rule.JULY_HOOK_ID
    source_rule_id = army_rule.JULY_SOURCE_RULE_ID
    effect = HealingEffect(
        effect_id=f"{hook_id}:daemonic-manifestation-battleline:fixture",
        target_unit_instance_id="fixture-unit",
        amount=1,
        opposing_player_id="player-b",
        selection_actor_player_id="player-a",
        source_rule_id=source_rule_id,
        source_context={
            "effect_kind": "daemonic_manifestation_battleline_revival",
            "hook_id": hook_id,
            "battle_shock_result_id": "fixture-shock-result",
        },
    )
    request = DecisionRequest(
        request_id="fixture-healing-selection",
        decision_type=SELECT_HEALING_MODEL_DECISION_TYPE,
        actor_id="player-a",
        payload=validate_json_value({"effect": effect.to_payload()}),
        options=(
            DecisionOption(
                option_id="revive",
                label="Revive model",
                payload={
                    "selection_kind": HealingStepKind.REVIVE_MODEL.value,
                    "model_instance_id": "fixture-model",
                },
            ),
        ),
    )
    decisions = DecisionController()
    decisions.request_decision(request)
    decisions.event_log.append(
        "chaos_daemons_daemonic_manifestation_revival_pending",
        {
            "decision_request_id": request.request_id,
            "healing_effect": effect.to_payload(),
            "battle_shock_result_id": "fixture-shock-result",
            "source_rule_id": source_rule_id,
        },
    )
    producer = decisions.submit_result(
        DecisionResult.for_request(
            result_id="fixture-healing-result", request=request, selected_option_id="revive"
        )
    )

    def identifies_provider(controller: DecisionController) -> bool:
        return battle_shock_outcome_authority._placement_producer_identifies_provider(  # pyright: ignore[reportPrivateUsage]
            context=BattleShockPendingOutcomeAuthorityContext(state, controller, request),
            hook_id=hook_id,
            source_rule_id=source_rule_id,
        )

    assert (
        validate_mutation_decision_closure(
            event_records=decisions.event_log.records,
            decision_records=decisions.records,
            mutation_index=len(decisions.event_log.records),
            request_id=request.request_id,
            result_id=producer.result.result_id,
        )
        is producer
    )
    # The valid producer is authenticated and an absent placement child is rejected.
    with pytest.raises(GameLifecycleError, match="placement chronology drifted"):
        identifies_provider(decisions)

    ambiguous = DecisionController.from_payload(decisions.to_payload())
    ambiguous._records.append(producer)  # pyright: ignore[reportPrivateUsage]
    assert not identifies_provider(ambiguous)

    requested, marker, recorded = decisions.event_log.records
    forged = DecisionController.from_payload(decisions.to_payload())
    forged_payload = producer.to_payload()
    forged_payload["result"]["result_id"] = "forged-result-id"
    forged.event_log.replace_records(
        (requested, marker, replace(recorded, payload=validate_json_value(forged_payload)))
    )
    assert not identifies_provider(forged)

    forged_scalar = DecisionController.from_payload(decisions.to_payload())
    changed_scalar = deepcopy(producer.to_payload())
    forged_request = changed_scalar["request"]["payload"]
    assert isinstance(forged_request, dict)
    forged_effect = forged_request["effect"]
    assert isinstance(forged_effect, dict)
    forged_effect["amount"] = True
    forged_scalar.event_log.replace_records(
        (requested, marker, replace(recorded, payload=validate_json_value(changed_scalar)))
    )
    assert not identifies_provider(forged_scalar)

    inverted = DecisionController.from_payload(decisions.to_payload())
    inverted.event_log.replace_records(
        (
            replace(marker, event_id=requested.event_id),
            replace(requested, event_id=marker.event_id),
            recorded,
        )
    )
    with pytest.raises(GameLifecycleError, match="initial decision authority drifted"):
        identifies_provider(inverted)


def test_read_only_authorities_detect_nested_and_same_length_mutations() -> None:
    from collections.abc import Callable

    import pytest

    from tests.phase11c_command_phase_helpers import battle_state
    from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
    from warhammer40k_core.engine.battle_shock_hooks import (
        BattleShockCompletedOutcomeAuthorityContext,
        BattleShockHookBinding,
        BattleShockHookRegistry,
        BattleShockPendingOutcomeAuthorityContext,
    )
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
    from warhammer40k_core.engine.decision_result import DecisionResult
    from warhammer40k_core.engine.event_log import JsonValue
    from warhammer40k_core.engine.phase import GameLifecycleError
    from warhammer40k_core.engine.reaction_queue import ReactionQueue, ReactionQueueFrame
    from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
    from warhammer40k_core.engine.timing_windows import (
        ReactionWindow,
        TimingTriggerKind,
        TimingWindow,
        TimingWindowDescriptor,
    )
    from warhammer40k_core.engine.turn_end_hooks import (
        TurnEndHookBinding,
        TurnEndHookRegistry,
        TurnEndRequestContext,
    )

    class LocalLabel(str):
        pass

    original_state = battle_state()

    def overwrite_nested(payload: JsonValue, value: JsonValue = "changed") -> None:
        assert isinstance(payload, dict)
        values = payload["values"]
        assert isinstance(values, list)
        values[0] = value

    def check(surface: str, target: str) -> None:
        state = deepcopy(original_state)
        phase = state.current_battle_phase
        assert phase is not None
        ledger = DecisionController()
        request = DecisionRequest(
            request_id="runtime-read-only:completed",
            decision_type="runtime-read-only",
            actor_id="player-a",
            payload={
                "values": [LocalLabel("changed") if target == "decision string type" else "before"]
            },
            options=(DecisionOption("continue", "Continue", {"values": ["before"]}),),
        )
        ledger.request_decision(request)
        record = ledger.submit_result(
            DecisionResult.for_request(
                result_id="runtime-read-only:result",
                request=request,
                selected_option_id="continue",
            )
        )
        queued = ledger.request_decision(replace(request, request_id="runtime-read-only:pending"))
        event = ledger.event_log.append(
            "runtime-read-only",
            {
                "values": [LocalLabel("changed") if target == "event string type" else True],
                "large": 2**100 if target == "large int" else None,
            },
        )
        phase_kind = BattlePhaseKind(phase.value)
        descriptor = TimingWindowDescriptor(
            "runtime-read-only:window",
            TimingTriggerKind.END_TURN,
            "runtime-read-only:source",
            metadata={"values": ["before"]},
        )
        reactions = ReactionQueue(
            [
                ReactionQueueFrame(
                    ReactionWindow(
                        TimingWindow(
                            "runtime-read-only:occurrence",
                            descriptor,
                            state.game_id,
                            state.battle_round,
                            state.active_player_id,
                        ),
                        (request.actor_id or "player-a",),
                    ),
                    phase_kind,
                    "fixture-step",
                    "fixture-resume",
                )
            ]
        )
        model = state.army_definitions[0].units[0].own_models[0]
        mutations: dict[str, Callable[[], None]] = {
            "state": lambda: object.__setattr__(model, "name", "changed"),
            "stage type": lambda: object.__setattr__(state, "stage", state.stage.value),
            "state container type": lambda: object.__setattr__(
                state, "command_point_ledgers", tuple(state.command_point_ledgers)
            ),
            "decision queue": lambda: overwrite_nested(queued.payload),
            "decision string type": lambda: overwrite_nested(queued.payload),
            "event string type": lambda: overwrite_nested(event.payload),
            "decision result": lambda: overwrite_nested(record.result.payload),
            "event": lambda: overwrite_nested(event.payload),
            "event row": lambda: ledger.event_log.replace_records(
                (*ledger.event_log.records[:-1], replace(event, event_type="changed"))
            ),
            "large int": lambda: overwrite_nested(event.payload, 1),
            "event container type": lambda: object.__setattr__(
                event, "payload", {"values": (True,), "large": None}
            ),
            "event occurrence": lambda: ledger.event_log.replace_records(
                tuple(replace(row) for row in ledger.event_log.records)
            ),
            "reaction queue": lambda: overwrite_nested(descriptor.metadata),
        }
        action = mutations[target]

        def discover(_context: TurnEndRequestContext) -> tuple[TimingRuleCandidate, ...]:
            action()
            return ()

        if surface == "turn-end":
            turn_context = TurnEndRequestContext(state, ledger, phase, reaction_queue=reactions)
            registry = TurnEndHookRegistry.from_bindings(
                (TurnEndHookBinding("read-only", "source", candidate_handler=discover),)
            )
            assert TurnEndHookRegistry.empty().candidates_for(turn_context) == ()
            with pytest.raises(GameLifecycleError, match="mutated engine state"):
                registry.candidates_for(turn_context)
            return

        shock_registry = BattleShockHookRegistry.from_bindings(
            (
                BattleShockHookBinding(
                    "read-only",
                    "source",
                    outcome_handler=lambda _context: None,
                    pending_outcome_authority_validator=lambda _context: action(),
                    completed_outcome_authority_validator=lambda _context: action(),
                ),
            )
        )
        if surface == "pending":
            with pytest.raises(GameLifecycleError, match="mutated runtime state"):
                shock_registry.pending_outcome_authority_for(
                    BattleShockPendingOutcomeAuthorityContext(state, ledger, queued)
                )
        else:
            with pytest.raises(GameLifecycleError, match="mutated runtime state"):
                shock_registry.validate_completed_outcome_authority(
                    BattleShockCompletedOutcomeAuthorityContext(state, ledger)
                )

    for surface in ("pending", "completed", "turn-end"):
        for target in (
            "state",
            "stage type",
            "state container type",
            "decision queue",
            "decision string type",
            "decision result",
            "event string type",
            "event",
            "event row",
            "event container type",
            "event occurrence",
            "large int",
        ):
            check(surface, target)
    check("turn-end", "reaction queue")
