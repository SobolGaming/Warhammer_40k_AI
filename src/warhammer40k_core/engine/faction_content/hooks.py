from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from types import MappingProxyType
from typing import Protocol, cast, runtime_checkable

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
from warhammer40k_core.engine.fight_phase_end_hooks import FightPhaseEndHookBinding
from warhammer40k_core.engine.fight_phase_start_hooks import FightPhaseStartHookBinding
from warhammer40k_core.engine.fight_unit_selected_hooks import (
    FightUnitSelectedGrantBinding,
    FightUnitSelectedHookBinding,
)
from warhammer40k_core.engine.lifecycle_hooks import (
    HookBinding,
    HookBindingShape,
    LifecycleHookEvent,
)
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
    UnitMoveCompletedBattleShockHookBinding,
    UnitMoveCompletedMortalWoundHookBinding,
)


@dataclass(frozen=True, slots=True)
class RuntimeHookBinding:
    lifecycle_event: LifecycleHookEvent
    binding: HookBindingShape

    def __post_init__(self) -> None:
        if type(self.lifecycle_event) is not LifecycleHookEvent:
            raise GameLifecycleError("RuntimeHookBinding lifecycle_event is invalid.")
        binding_type = type(self.binding)
        if binding_type is HookBinding:
            binding_event = None
        else:
            binding_event = _HOOK_EVENT_BY_BINDING_TYPE.get(binding_type)
        if binding_type is not HookBinding and binding_event is None:
            raise GameLifecycleError("RuntimeHookBinding binding is invalid.")
        if binding_event is not None and binding_event != self.lifecycle_event:
            raise GameLifecycleError(
                "RuntimeHookBinding lifecycle_event does not match binding type."
            )
        _validate_identifier("hook_id", self.binding.hook_id)
        _validate_identifier("source_id", self.binding.source_id)

    @property
    def hook_id(self) -> str:
        return self.binding.hook_id

    @property
    def source_id(self) -> str:
        return self.binding.source_id


type AnyHookBinding = RuntimeHookBinding
type AnyHookBindingInput = RuntimeHookBinding | HookBindingShape
type RuntimeHookBindings = tuple[AnyHookBinding, ...]
type RuntimeHookBindingsByEvent = Mapping[LifecycleHookEvent, RuntimeHookBindings]
EMPTY_HOOK_BINDINGS_BY_EVENT: RuntimeHookBindingsByEvent = MappingProxyType({})


@runtime_checkable
class RuntimeHookRegistryShape(Protocol):
    def all_bindings(self) -> tuple[HookBindingShape, ...]: ...


_HOOK_EVENT_BY_BINDING_TYPE: Mapping[type[object], LifecycleHookEvent] = MappingProxyType(
    {
        BattleFormationHookBinding: LifecycleHookEvent.BATTLE_FORMATION,
        BattleRoundStartHookBinding: LifecycleHookEvent.BATTLE_ROUND_START,
        TurnEndHookBinding: LifecycleHookEvent.TURN_END,
        CommandPhaseStartHookBinding: LifecycleHookEvent.COMMAND_PHASE_START,
        FightPhaseStartHookBinding: LifecycleHookEvent.FIGHT_PHASE_START,
        FightPhaseEndHookBinding: LifecycleHookEvent.FIGHT_PHASE_END,
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
        UnitMoveCompletedBattleShockHookBinding: (
            LifecycleHookEvent.UNIT_MOVE_COMPLETED_BATTLE_SHOCK
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
        LifecycleHookEvent.FIGHT_PHASE_END: "Fight-phase end hook binding",
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
        LifecycleHookEvent.UNIT_MOVE_COMPLETED_BATTLE_SHOCK: (
            "unit move completed Battle-shock hook binding"
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
    if type(value) is RuntimeHookBinding:
        return value.lifecycle_event
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
        binding = runtime_hook_binding_for(raw_binding)
        event = binding.lifecycle_event
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
        binding.binding
        for binding in bindings
        if binding.lifecycle_event == event and type(binding.binding) is binding_type
    )


def runtime_hook_binding_for(value: object) -> RuntimeHookBinding:
    if type(value) is RuntimeHookBinding:
        return value
    event = _HOOK_EVENT_BY_BINDING_TYPE.get(type(value))
    if event is None:
        raise GameLifecycleError(
            "RuntimeContentContribution hook_bindings contains invalid values."
        )
    return RuntimeHookBinding(lifecycle_event=event, binding=cast(HookBindingShape, value))


def hook_bindings_by_event_from_sources(
    *,
    emitted_bindings: tuple[HookBindingShape, ...],
    contribution_bindings: tuple[AnyHookBinding, ...],
) -> Mapping[LifecycleHookEvent, tuple[AnyHookBinding, ...]]:
    combined = (
        *(runtime_hook_binding_for(binding) for binding in emitted_bindings),
        *contribution_bindings,
    )
    return hook_bindings_by_event_from_bindings(combined)


def hook_bindings_by_event_from_registry_owner(
    *,
    owner: object,
    extra_bindings_by_event: object,
) -> RuntimeHookBindingsByEvent:
    registry_bindings = _hook_bindings_from_registry_owner(owner)
    registry_bindings_by_key = {
        (binding.lifecycle_event, binding.hook_id): binding for binding in registry_bindings
    }
    extra_bindings: list[RuntimeHookBinding] = []
    for bindings in validate_hook_bindings_by_event(extra_bindings_by_event).values():
        for binding in bindings:
            key = (binding.lifecycle_event, binding.hook_id)
            registry_binding = registry_bindings_by_key.get(key)
            if type(binding.binding) is HookBinding:
                extra_bindings.append(binding)
            elif registry_binding is None:
                raise GameLifecycleError(
                    "RuntimeContentBundle hook_bindings_by_event contains typed binding "
                    "missing from hook registries."
                )
            elif binding != registry_binding:
                raise GameLifecycleError(
                    "RuntimeContentBundle hook_bindings_by_event does not match hook registry."
                )
    return hook_bindings_by_event_from_bindings((*registry_bindings, *extra_bindings))


def combine_any_hook_bindings(
    bindings: tuple[AnyHookBinding, ...],
) -> tuple[AnyHookBinding, ...]:
    combined: list[AnyHookBinding] = []
    for event in LifecycleHookEvent:
        field_name = HOOK_BINDING_COMBINE_NAME_BY_EVENT.get(
            event,
            f"{event.value} hook binding",
        )
        combined.extend(
            _combine_unique_hook_bindings(
                field_name,
                tuple(binding for binding in bindings if binding.lifecycle_event == event),
            )
        )
    return validate_any_hook_bindings(tuple(combined))


def hook_bindings_by_event_from_bindings(
    bindings: tuple[AnyHookBindingInput, ...],
) -> Mapping[LifecycleHookEvent, tuple[AnyHookBinding, ...]]:
    grouped: dict[LifecycleHookEvent, list[AnyHookBinding]] = {}
    for binding in validate_any_hook_bindings(bindings):
        grouped.setdefault(binding.lifecycle_event, []).append(binding)
    return validate_hook_bindings_by_event(
        {event: tuple(event_bindings) for event, event_bindings in grouped.items()}
    )


def validate_hook_bindings_by_event(
    value: object,
) -> Mapping[LifecycleHookEvent, tuple[AnyHookBinding, ...]]:
    if not isinstance(value, Mapping):
        raise GameLifecycleError("RuntimeContentBundle hook_bindings_by_event must be a mapping.")
    validated: dict[LifecycleHookEvent, tuple[AnyHookBinding, ...]] = {}
    for raw_event, raw_bindings in cast(Mapping[object, object], value).items():
        if type(raw_event) is not LifecycleHookEvent:
            raise GameLifecycleError(
                "RuntimeContentBundle hook_bindings_by_event contains invalid events."
            )
        event = raw_event
        bindings = validate_any_hook_bindings(raw_bindings)
        for binding in bindings:
            if binding.lifecycle_event != event:
                raise GameLifecycleError(
                    "RuntimeContentBundle hook_bindings_by_event contains mismatched events."
                )
        validated[event] = bindings
    return MappingProxyType(dict(sorted(validated.items(), key=lambda item: item[0].value)))


def _hook_binding_sort_key(binding: AnyHookBinding) -> tuple[str, str]:
    return (binding.lifecycle_event.value, binding.hook_id)


def _hook_bindings_from_registry_owner(owner: object) -> tuple[RuntimeHookBinding, ...]:
    if not is_dataclass(owner) or isinstance(owner, type):
        raise GameLifecycleError("RuntimeContentBundle hook registry owner must be a dataclass.")
    bindings: list[RuntimeHookBinding] = []
    for field in fields(owner):
        if not field.name.endswith("_hook_registry"):
            continue
        registry = getattr(owner, field.name)
        if not isinstance(registry, RuntimeHookRegistryShape):
            raise GameLifecycleError(
                "RuntimeContentBundle hook registry fields must expose all_bindings."
            )
        bindings.extend(runtime_hook_binding_for(binding) for binding in registry.all_bindings())
    return tuple(bindings)


def _combine_unique_hook_bindings(
    field_name: str,
    bindings: tuple[AnyHookBinding, ...],
) -> tuple[AnyHookBinding, ...]:
    seen: set[str] = set()
    combined: list[AnyHookBinding] = []
    for binding in bindings:
        hook_id = _validate_identifier(f"{field_name} id", binding.hook_id)
        if hook_id in seen:
            raise GameLifecycleError(f"Runtime content {field_name} IDs must be unique.")
        seen.add(hook_id)
        combined.append(binding)
    return tuple(combined)


_validate_identifier = IdentifierValidator(GameLifecycleError)
