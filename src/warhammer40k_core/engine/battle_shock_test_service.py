from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Self, cast

from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.battle_shock import (
    BattleShockTestReason,
    BattleShockTestRequest,
    battle_shock_leadership_target_for_rules_unit,
)
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockDiceExpressionContext,
    BattleShockHookRegistry,
    BattleShockModifierApplication,
)
from warhammer40k_core.engine.battle_shock_resolution import (
    BattleShockPassedStatePolicy,
    BattleShockResolutionResult,
    apply_battle_shock_reroll_resolution_decision,
    is_battle_shock_reroll_request,
    resolve_battle_shock_test_with_optional_reroll,
)
from warhammer40k_core.engine.battlefield_state import BattlefieldRemovalKind
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rules_unit_geometry import (
    placed_alive_geometry_models_for_rules_unit,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
    from warhammer40k_core.engine.game_state import GameState


STRATAGEM_BATTLE_SHOCK_SOURCE_KIND = "stratagem_battle_shock"

_RESERVED_SOURCE_PAYLOAD_KEYS = frozenset(
    {
        "game_id",
        "battle_round",
        "active_player_id",
        "phase",
        "source_kind",
        "battle_shock_test_request",
    }
)


@dataclass(frozen=True, slots=True)
class BattleShockTestRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    runtime_modifier_registry: RuntimeModifierRegistry
    battle_shock_hook_registry: BattleShockHookRegistry

    def __post_init__(self) -> None:
        raw_indexes = cast(object, self.ability_indexes_by_player_id)
        if not isinstance(raw_indexes, Mapping):
            raise GameLifecycleError("Battle-shock runtime ability indexes must be a mapping.")
        indexes: dict[str, AbilityCatalogIndex] = {}
        for raw_player_id, raw_index in cast(Mapping[object, object], raw_indexes).items():
            player_id = _validate_identifier("player_id", raw_player_id)
            if type(raw_index) is not AbilityCatalogIndex:
                raise GameLifecycleError("Battle-shock runtime ability index is invalid.")
            indexes[player_id] = raw_index
        object.__setattr__(self, "ability_indexes_by_player_id", MappingProxyType(indexes))
        if type(self.runtime_modifier_registry) is not RuntimeModifierRegistry:
            raise GameLifecycleError("Battle-shock runtime modifier registry is invalid.")
        if type(self.battle_shock_hook_registry) is not BattleShockHookRegistry:
            raise GameLifecycleError("Battle-shock runtime hook registry is invalid.")

    @classmethod
    def from_runtime_content_bundle(cls, bundle: RuntimeContentBundle) -> Self:
        from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle

        if type(bundle) is not RuntimeContentBundle:
            raise GameLifecycleError("Battle-shock runtime requires RuntimeContentBundle.")
        return cls(
            ability_indexes_by_player_id=bundle.ability_indexes_by_player_id,
            runtime_modifier_registry=bundle.runtime_modifier_registry,
            battle_shock_hook_registry=bundle.battle_shock_hook_registry,
        )


@dataclass(frozen=True, slots=True)
class BattleShockTestExecution:
    request: BattleShockTestRequest
    resolution: BattleShockResolutionResult

    def __post_init__(self) -> None:
        if type(self.request) is not BattleShockTestRequest:
            raise GameLifecycleError("Battle-shock execution requires a typed request.")
        if type(self.resolution) is not BattleShockResolutionResult:
            raise GameLifecycleError("Battle-shock execution requires a typed resolution.")


def materialize_battle_shock_test_request(
    *,
    runtime: BattleShockTestRuntime,
    state: GameState,
    request_id: str,
    target_unit_instance_id: str,
    reason: BattleShockTestReason,
    active_player_id: str,
    phase: BattlePhase,
    phase_start_battle_shocked_unit_ids: tuple[str, ...],
) -> BattleShockTestRequest:
    """Materialize one test from current authoritative state immediately before its roll."""
    from warhammer40k_core.engine.game_state import GameState

    if type(runtime) is not BattleShockTestRuntime:
        raise GameLifecycleError("Battle-shock test requires BattleShockTestRuntime.")
    if type(state) is not GameState:
        raise GameLifecycleError("Battle-shock test requires GameState.")
    requested_id = _validate_identifier("request_id", request_id)
    target_id = _validate_identifier("target_unit_instance_id", target_unit_instance_id)
    active_player = _validate_identifier("active_player_id", active_player_id)
    if type(reason) is not BattleShockTestReason:
        raise GameLifecycleError("Battle-shock test reason is invalid.")
    if type(phase) is not BattlePhase or state.current_battle_phase is not phase:
        raise GameLifecycleError("Battle-shock test phase does not match live state.")
    if state.active_player_id != active_player:
        raise GameLifecycleError("Battle-shock test active player does not match live state.")
    target_rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=target_id)
    canonical_target_id = target_rules_unit.unit_instance_id
    all_alive_model_ids = tuple(
        sorted(model.model_instance_id for model in target_rules_unit.alive_models())
    )
    placed_model_ids = tuple(
        sorted(
            model.model_id
            for model in placed_alive_geometry_models_for_rules_unit(
                state=state,
                unit_instance_id=canonical_target_id,
            )
        )
    )
    alive_model_id_set = set(all_alive_model_ids)
    placed_model_id_set = set(placed_model_ids)
    absent_alive_model_ids = alive_model_id_set - placed_model_id_set
    destroyed_departure_model_ids = {
        model_id
        for departure in state.primary_battlefield_departure_states
        if departure.removal_kind is BattlefieldRemovalKind.DESTROYED
        and departure.rules_unit_instance_id == canonical_target_id
        for model_id in departure.removed_model_instance_ids
    }
    if (
        not placed_model_ids
        or not placed_model_id_set <= alive_model_id_set
        or not absent_alive_model_ids <= destroyed_departure_model_ids
    ):
        raise GameLifecycleError(
            "Battle-shock target does not have every alive model on the battlefield or lacks "
            "destroyed-departure authority for an absent model."
        )
    current_model_ids = placed_model_ids
    player_id = target_rules_unit.owner_player_id
    ability_index = runtime.ability_indexes_by_player_id.get(player_id)
    if ability_index is None:
        raise GameLifecycleError("Battle-shock target lacks a loaded ability index.")
    phase_start_ids = _validate_identifier_tuple(
        "phase_start_battle_shocked_unit_ids",
        phase_start_battle_shocked_unit_ids,
    )
    if phase_start_ids != tuple(sorted(phase_start_ids)):
        raise GameLifecycleError("Battle-shock phase-start identities must be sorted.")
    dice_expression = runtime.battle_shock_hook_registry.dice_expression_for(
        BattleShockDiceExpressionContext(
            state=state,
            player_id=player_id,
            unit_instance_id=canonical_target_id,
            reason=reason,
            active_player_id=active_player,
            phase=phase,
            default_expression=DiceExpression(quantity=2, sides=6),
            phase_start_battle_shocked_unit_ids=phase_start_ids,
        )
    )
    return BattleShockTestRequest.for_unit(
        request_id=requested_id,
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id=player_id,
        unit_instance_id=canonical_target_id,
        reason=reason,
        leadership_target=battle_shock_leadership_target_for_rules_unit(
            target_rules_unit,
            current_model_ids=current_model_ids,
            ability_index=ability_index,
            state=state,
            runtime_modifier_registry=runtime.runtime_modifier_registry,
        ),
        below_half_strength_context=BelowHalfStrengthContext.from_rules_unit(
            rules_unit=target_rules_unit,
            starting_strength=state.starting_strength_record_for_unit(canonical_target_id),
            current_model_ids=current_model_ids,
        ),
        dice_expression=dice_expression,
    )


def resolve_battle_shock_test(
    *,
    runtime: BattleShockTestRuntime,
    state: GameState,
    decisions: DecisionController,
    request_id: str,
    target_unit_instance_id: str,
    reason: BattleShockTestReason,
    active_player_id: str,
    phase: BattlePhase,
    phase_start_battle_shocked_unit_ids: tuple[str, ...],
    passed_state_policy: BattleShockPassedStatePolicy,
    source_kind: str,
    source_payload: dict[str, JsonValue],
    resolved_event_types: tuple[str, ...],
    pending_phase_body_status: str,
    additional_modifier_applications: tuple[BattleShockModifierApplication, ...] = (),
) -> BattleShockTestExecution:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Battle-shock test requires DecisionController.")
    active_player = _validate_identifier("active_player_id", active_player_id)
    source = _validate_identifier("source_kind", source_kind)
    if type(source_payload) is not dict:
        raise GameLifecycleError("Battle-shock source payload must be an object.")
    conflicting_keys = _RESERVED_SOURCE_PAYLOAD_KEYS.intersection(source_payload)
    if conflicting_keys:
        raise GameLifecycleError("Battle-shock source payload contains reserved fields.")
    source_context = cast(dict[str, JsonValue], validate_json_value(source_payload))
    phase_start_ids = _validate_identifier_tuple(
        "phase_start_battle_shocked_unit_ids",
        phase_start_battle_shocked_unit_ids,
    )
    request = materialize_battle_shock_test_request(
        runtime=runtime,
        state=state,
        request_id=request_id,
        target_unit_instance_id=target_unit_instance_id,
        reason=reason,
        active_player_id=active_player,
        phase=phase,
        phase_start_battle_shocked_unit_ids=phase_start_ids,
    )
    base_payload = cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": active_player,
                "phase": phase.value,
                "source_kind": source,
                **source_context,
            }
        ),
    )
    decisions.event_log.append(
        "battle_shock_test_requested",
        {
            **base_payload,
            "battle_shock_test_request": validate_json_value(request.to_payload()),
        },
    )
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    resolution = resolve_battle_shock_test_with_optional_reroll(
        state=state,
        decisions=decisions,
        manager=manager,
        battle_shock_hooks=runtime.battle_shock_hook_registry,
        request=request,
        roll_state=manager.roll(request.spec),
        active_player_id=active_player,
        phase=phase,
        phase_start_battle_shocked_unit_ids=phase_start_ids,
        passed_state_policy=passed_state_policy,
        source_kind=source,
        base_payload=base_payload,
        resolved_event_types=resolved_event_types,
        pending_phase_body_status=pending_phase_body_status,
        additional_modifier_applications=additional_modifier_applications,
    )
    return BattleShockTestExecution(request=request, resolution=resolution)


def is_stratagem_battle_shock_reroll_request(request: DecisionRequest) -> bool:
    return is_battle_shock_reroll_request(
        request,
        source_kind=STRATAGEM_BATTLE_SHOCK_SOURCE_KIND,
    )


def apply_stratagem_battle_shock_reroll_decision(
    *,
    runtime: BattleShockTestRuntime,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
) -> None:
    if type(runtime) is not BattleShockTestRuntime:
        raise GameLifecycleError("Stratagem Battle-shock reroll requires runtime authority.")
    apply_battle_shock_reroll_resolution_decision(
        state=state,
        decisions=decisions,
        result=result,
        battle_shock_hooks=runtime.battle_shock_hook_registry,
        expected_source_kind=STRATAGEM_BATTLE_SHOCK_SOURCE_KIND,
        expected_passed_state_policy=BattleShockPassedStatePolicy.PRESERVE,
    )


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"Battle-shock {field_name} must be a tuple.")
    identifiers = tuple(
        _validate_identifier(f"{field_name} value", value)
        for value in cast(tuple[object, ...], values)
    )
    if len(set(identifiers)) != len(identifiers):
        raise GameLifecycleError(f"Battle-shock {field_name} contains duplicates.")
    return identifiers


__all__ = (
    "STRATAGEM_BATTLE_SHOCK_SOURCE_KIND",
    "BattleShockTestExecution",
    "BattleShockTestRuntime",
    "apply_stratagem_battle_shock_reroll_decision",
    "is_stratagem_battle_shock_reroll_request",
    "materialize_battle_shock_test_request",
    "resolve_battle_shock_test",
)
