from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind, RulesetDescriptor
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.catalog_modifier_ignore import (
    ModifierIgnoreKind,
    catalog_modifier_ignore_permissions_for_unit,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_charge_roll_modifiers_for_unit,
)
from warhammer40k_core.engine.charge_declaration import (
    ChargeEligibilityContext,
    ChargeTargetCandidate,
)
from warhammer40k_core.engine.charge_roll_permissions import (
    current_model_instance_ids_for_charge_unit,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.modifier_ignore import (
    ModifierIgnoreSnapshot,
    options_with_modifier_ignore_choices,
    record_modifier_ignore_selection,
)
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus
from warhammer40k_core.engine.runtime_modifiers import (
    ChargeRollModifierContext,
    RuntimeModifierRegistry,
)
from warhammer40k_core.engine.target_restriction_hooks import (
    ChargeTargetRestrictionHookRegistry,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.unit_factory import UnitInstance


SELECT_CHARGING_UNIT_DECISION_TYPE = "select_charging_unit"
COMPLETE_CHARGE_PHASE_OPTION_ID = "complete_charge_phase"
COMPLETE_CHARGE_PHASE_STATUS = "charge_phase_complete"


class _ChargeUnitLookup(Protocol):
    def __call__(
        self,
        *,
        state: GameState,
        unit_instance_id: str,
    ) -> UnitInstance: ...


class _ChargeTargetCandidateProvider(Protocol):
    def __call__(
        self,
        *,
        state: GameState,
        unit_instance_id: str,
        ruleset_descriptor: RulesetDescriptor,
        charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry | None = None,
    ) -> tuple[ChargeTargetCandidate, ...]: ...


def charging_unit_options_with_modifier_ignore_choices(
    *,
    state: GameState,
    unit_ids: tuple[str, ...],
    include_complete: bool,
    ruleset_descriptor: RulesetDescriptor,
    ability_index: AbilityCatalogIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
    active_player_id: str,
    unit_lookup: _ChargeUnitLookup,
    target_candidate_provider: _ChargeTargetCandidateProvider,
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry | None = None,
) -> tuple[DecisionOption, ...]:
    options: list[DecisionOption] = []
    for unit_id in unit_ids:
        unit = unit_lookup(state=state, unit_instance_id=unit_id)
        target_candidates = target_candidate_provider(
            state=state,
            unit_instance_id=unit_id,
            ruleset_descriptor=ruleset_descriptor,
            charge_target_restriction_hooks=charge_target_restriction_hooks,
        )
        eligibility_context = ChargeEligibilityContext(
            player_id=active_player_id,
            battle_round=state.battle_round,
            unit_instance_id=unit_id,
            target_candidates=target_candidates,
        )
        option = DecisionOption(
            option_id=unit_id,
            label=unit.name,
            payload=validate_json_value(
                {
                    "submission_kind": SELECT_CHARGING_UNIT_DECISION_TYPE,
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "phase": BattlePhase.CHARGE.value,
                    "active_player_id": active_player_id,
                    "unit_instance_id": unit_id,
                    "eligibility_context": eligibility_context.to_payload(),
                }
            ),
        )
        current_model_ids = current_model_instance_ids_for_charge_unit(state=state, unit=unit)
        permissions = catalog_modifier_ignore_permissions_for_unit(
            ability_index=ability_index,
            unit=unit,
            current_model_instance_ids=current_model_ids,
        )
        roll_modifiers = charge_roll_modifiers_for_unit(
            state=state,
            ability_index=ability_index,
            unit=unit,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        options.extend(
            options_with_modifier_ignore_choices(
                option=option,
                unit_instance_id=unit_id,
                permissions=permissions,
                available_modifiers=tuple(
                    ModifierIgnoreSnapshot.for_roll_modifier(
                        kind=ModifierIgnoreKind.CHARGE_ROLL,
                        modifier=modifier,
                    )
                    for modifier in roll_modifiers
                ),
            )
        )
    if include_complete:
        options.append(
            DecisionOption(
                option_id=COMPLETE_CHARGE_PHASE_OPTION_ID,
                label="Complete Charge Phase",
                payload=validate_json_value(
                    {
                        "submission_kind": COMPLETE_CHARGE_PHASE_OPTION_ID,
                        "game_id": state.game_id,
                        "battle_round": state.battle_round,
                        "phase": BattlePhase.CHARGE.value,
                        "active_player_id": active_player_id,
                        "phase_body_status": COMPLETE_CHARGE_PHASE_STATUS,
                        "skipped_unit_ids": list(unit_ids),
                    }
                ),
            )
        )
    return tuple(options)


def charge_roll_modifiers_for_unit(
    *,
    state: GameState,
    ability_index: AbilityCatalogIndex,
    unit: UnitInstance,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> tuple[RollModifier, ...]:
    roll_modifiers = catalog_charge_roll_modifiers_for_unit(
        state=state,
        ability_index=ability_index,
        unit=unit,
        current_model_instance_ids=current_model_instance_ids_for_charge_unit(
            state=state,
            unit=unit,
        ),
    )
    return runtime_modifier_registry.charge_roll_modifiers(
        ChargeRollModifierContext(
            state=state,
            unit_instance_id=unit.unit_instance_id,
            current_roll_modifiers=roll_modifiers,
        )
    )


def invalid_charge_modifier_ignore_context_status(
    *,
    state: GameState,
    result: DecisionResult,
    current_options: tuple[DecisionOption, ...],
) -> LifecycleStatus | None:
    current_option = next(
        (option for option in current_options if option.option_id == result.selected_option_id),
        None,
    )
    if current_option is not None and current_option.payload == result.payload:
        return None
    return LifecycleStatus.invalid(
        stage=state.stage,
        message="Charging unit modifier context is stale.",
        payload={
            "invalid_reason": "charging_unit_option_drift",
            "field": "modifier_ignore_context",
        },
    )


def record_charge_modifier_ignore_selection(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    unit_instance_id: str,
) -> PersistingEffect | None:
    effect = record_modifier_ignore_selection(
        state=state,
        result=result,
        unit_instance_id=unit_instance_id,
        phase=BattlePhaseKind.CHARGE,
    )
    if effect is None:
        return None
    decisions.event_log.append(
        "modifier_ignores_selected",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.CHARGE.value,
            "unit_instance_id": unit_instance_id,
            "source_decision_request_id": result.request_id,
            "source_decision_result_id": result.result_id,
            "modifier_ignore_effect": effect.to_payload(),
        },
    )
    return effect
