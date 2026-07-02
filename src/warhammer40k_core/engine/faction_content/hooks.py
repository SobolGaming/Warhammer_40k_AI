from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.advance_eligibility_hooks import AdvanceEligibilityHookBinding
from warhammer40k_core.engine.advance_hooks import AdvanceMoveHookBinding
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedHookBinding,
)
from warhammer40k_core.engine.battle_formation_hooks import BattleFormationHookBinding
from warhammer40k_core.engine.battle_round_hooks import BattleRoundStartHookBinding
from warhammer40k_core.engine.battle_shock_hooks import BattleShockHookBinding
from warhammer40k_core.engine.charge_declaration_hooks import ChargeDeclarationHookBinding
from warhammer40k_core.engine.command_phase_start_hooks import CommandPhaseStartHookBinding
from warhammer40k_core.engine.fall_back_hooks import FallBackEligibilityHookBinding
from warhammer40k_core.engine.fight_activation_abilities import (
    FightActivationAbilityHookBinding,
)
from warhammer40k_core.engine.fight_phase_start_hooks import FightPhaseStartHookBinding
from warhammer40k_core.engine.fight_unit_selected_hooks import (
    FightUnitSelectedGrantBinding,
    FightUnitSelectedHookBinding,
)
from warhammer40k_core.engine.lifecycle_hooks import HookBindingShape, LifecycleHookEvent
from warhammer40k_core.engine.mortal_wound_feel_no_pain_hooks import (
    MortalWoundFeelNoPainContinuationHookBinding,
)
from warhammer40k_core.engine.movement_end_surge_hooks import MovementEndSurgeHookBinding
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.reserve_arrival_hooks import ReserveArrivalDistanceHookBinding
from warhammer40k_core.engine.shooting_end_surge_hooks import ShootingEndSurgeHookBinding
from warhammer40k_core.engine.shooting_phase_start_hooks import ShootingPhaseStartHookBinding
from warhammer40k_core.engine.shooting_unit_selected_hooks import (
    ShootingUnitSelectedGrantBinding,
    ShootingUnitSelectedHookBinding,
)
from warhammer40k_core.engine.sticky_objective_control import (
    PhaseEndObjectiveControlHookBinding,
)
from warhammer40k_core.engine.stratagem_cost_choice_hooks import StratagemCostChoiceHookBinding
from warhammer40k_core.engine.target_restriction_hooks import (
    ChargeTargetRestrictionHookBinding,
    ShootingTargetRestrictionHookBinding,
)
from warhammer40k_core.engine.turn_end_hooks import TurnEndHookBinding
from warhammer40k_core.engine.unit_destroyed_hooks import UnitDestroyedHookBinding
from warhammer40k_core.engine.unit_move_completed_hooks import (
    UnitMoveCompletedMortalWoundHookBinding,
)

type AnyHookBinding = HookBindingShape

_HOOK_EVENT_BY_BINDING_TYPE: Mapping[type[object], LifecycleHookEvent] = MappingProxyType(
    {
        BattleFormationHookBinding: LifecycleHookEvent.BATTLE_FORMATION,
        BattleRoundStartHookBinding: LifecycleHookEvent.BATTLE_ROUND_START,
        TurnEndHookBinding: LifecycleHookEvent.TURN_END,
        CommandPhaseStartHookBinding: LifecycleHookEvent.COMMAND_PHASE_START,
        FightPhaseStartHookBinding: LifecycleHookEvent.FIGHT_PHASE_START,
        ShootingPhaseStartHookBinding: LifecycleHookEvent.SHOOTING_PHASE_START,
        UnitDestroyedHookBinding: LifecycleHookEvent.UNIT_DESTROYED,
        BattleShockHookBinding: LifecycleHookEvent.BATTLE_SHOCK,
        AdvanceEligibilityHookBinding: LifecycleHookEvent.ADVANCE_ELIGIBILITY,
        AdvanceMoveHookBinding: LifecycleHookEvent.ADVANCE_MOVE,
        FallBackEligibilityHookBinding: LifecycleHookEvent.FALL_BACK_ELIGIBILITY,
        MovementEndSurgeHookBinding: LifecycleHookEvent.MOVEMENT_END_SURGE,
        ReserveArrivalDistanceHookBinding: LifecycleHookEvent.RESERVE_ARRIVAL_DISTANCE,
        UnitMoveCompletedMortalWoundHookBinding: (
            LifecycleHookEvent.UNIT_MOVE_COMPLETED_MORTAL_WOUND
        ),
        MortalWoundFeelNoPainContinuationHookBinding: (
            LifecycleHookEvent.MORTAL_WOUND_FEEL_NO_PAIN_CONTINUATION
        ),
        ChargeDeclarationHookBinding: LifecycleHookEvent.CHARGE_DECLARATION,
        ShootingTargetRestrictionHookBinding: LifecycleHookEvent.SHOOTING_TARGET_RESTRICTION,
        ChargeTargetRestrictionHookBinding: LifecycleHookEvent.CHARGE_TARGET_RESTRICTION,
        ShootingUnitSelectedHookBinding: LifecycleHookEvent.SHOOTING_UNIT_SELECTED,
        ShootingUnitSelectedGrantBinding: LifecycleHookEvent.SHOOTING_UNIT_SELECTED_GRANT,
        AttackSequenceCompletedHookBinding: LifecycleHookEvent.ATTACK_SEQUENCE_COMPLETED,
        ShootingEndSurgeHookBinding: LifecycleHookEvent.SHOOTING_END_SURGE,
        FightActivationAbilityHookBinding: LifecycleHookEvent.FIGHT_ACTIVATION_ABILITY,
        FightUnitSelectedHookBinding: LifecycleHookEvent.FIGHT_UNIT_SELECTED,
        FightUnitSelectedGrantBinding: LifecycleHookEvent.FIGHT_UNIT_SELECTED_GRANT,
        PhaseEndObjectiveControlHookBinding: LifecycleHookEvent.PHASE_END_OBJECTIVE_CONTROL,
        StratagemCostChoiceHookBinding: LifecycleHookEvent.STRATAGEM_COST_CHOICE,
    }
)

HOOK_BINDING_COMBINE_NAME_BY_EVENT: Mapping[LifecycleHookEvent, str] = MappingProxyType(
    {
        LifecycleHookEvent.BATTLE_FORMATION: "battle formation hook binding",
        LifecycleHookEvent.BATTLE_ROUND_START: "battle-round start hook binding",
        LifecycleHookEvent.TURN_END: "turn-end hook binding",
        LifecycleHookEvent.COMMAND_PHASE_START: "Command-phase start hook binding",
        LifecycleHookEvent.FIGHT_PHASE_START: "Fight-phase start hook binding",
        LifecycleHookEvent.SHOOTING_PHASE_START: "Shooting-phase start hook binding",
        LifecycleHookEvent.UNIT_DESTROYED: "Unit-destroyed hook binding",
        LifecycleHookEvent.BATTLE_SHOCK: "Battle-shock hook binding",
        LifecycleHookEvent.ADVANCE_ELIGIBILITY: "Advance eligibility hook binding",
        LifecycleHookEvent.ADVANCE_MOVE: "Advance hook binding",
        LifecycleHookEvent.FALL_BACK_ELIGIBILITY: "Fall Back eligibility hook binding",
        LifecycleHookEvent.MOVEMENT_END_SURGE: "movement-end surge hook binding",
        LifecycleHookEvent.RESERVE_ARRIVAL_DISTANCE: "reserve arrival distance hook binding",
        LifecycleHookEvent.UNIT_MOVE_COMPLETED_MORTAL_WOUND: (
            "unit move completed mortal wound hook binding"
        ),
        LifecycleHookEvent.MORTAL_WOUND_FEEL_NO_PAIN_CONTINUATION: (
            "mortal wound Feel No Pain hook binding"
        ),
        LifecycleHookEvent.CHARGE_DECLARATION: "charge declaration hook binding",
        LifecycleHookEvent.SHOOTING_TARGET_RESTRICTION: "shooting target restriction hook binding",
        LifecycleHookEvent.CHARGE_TARGET_RESTRICTION: "charge target restriction hook binding",
        LifecycleHookEvent.SHOOTING_UNIT_SELECTED: "shooting-unit-selected hook binding",
        LifecycleHookEvent.SHOOTING_UNIT_SELECTED_GRANT: (
            "shooting-unit-selected grant hook binding"
        ),
        LifecycleHookEvent.ATTACK_SEQUENCE_COMPLETED: "attack-sequence-completed hook binding",
        LifecycleHookEvent.SHOOTING_END_SURGE: "shooting-end surge hook binding",
        LifecycleHookEvent.FIGHT_ACTIVATION_ABILITY: "Fight activation ability hook binding",
        LifecycleHookEvent.FIGHT_UNIT_SELECTED: "fight-unit-selected hook binding",
        LifecycleHookEvent.FIGHT_UNIT_SELECTED_GRANT: "fight-unit-selected grant hook binding",
        LifecycleHookEvent.PHASE_END_OBJECTIVE_CONTROL: (
            "phase-end objective-control hook binding"
        ),
        LifecycleHookEvent.STRATAGEM_COST_CHOICE: "Stratagem cost choice hook binding",
    }
)


def lifecycle_event_for_hook_binding(value: object) -> LifecycleHookEvent:
    event = _HOOK_EVENT_BY_BINDING_TYPE.get(type(value))
    if event is None:
        raise GameLifecycleError(
            "RuntimeContentContribution hook_bindings contains invalid values."
        )
    return event


def validate_any_hook_bindings(value: object) -> tuple[AnyHookBinding, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("RuntimeContentContribution hook_bindings must be a tuple.")
    bindings: list[AnyHookBinding] = []
    seen: set[tuple[LifecycleHookEvent, str]] = set()
    for raw_binding in cast(tuple[object, ...], value):
        event = lifecycle_event_for_hook_binding(raw_binding)
        binding = cast(AnyHookBinding, raw_binding)
        hook_id = _validate_identifier("hook binding id", binding.hook_id)
        key = (event, hook_id)
        if key in seen:
            raise GameLifecycleError(
                "Runtime content hook binding IDs must be unique per lifecycle event."
            )
        seen.add(key)
        bindings.append(binding)
    return tuple(sorted(bindings, key=_hook_binding_sort_key))


def hook_bindings_for_event[BindingT: HookBindingShape](
    bindings: tuple[AnyHookBinding, ...],
    event: LifecycleHookEvent,
    binding_type: type[BindingT],
) -> tuple[BindingT, ...]:
    return tuple(
        binding
        for binding in bindings
        if lifecycle_event_for_hook_binding(binding) == event and type(binding) is binding_type
    )


def _hook_binding_sort_key(binding: AnyHookBinding) -> tuple[str, str]:
    return (lifecycle_event_for_hook_binding(binding).value, binding.hook_id)


_validate_identifier = IdentifierValidator(GameLifecycleError)
