"""Reserve deadline and final-turn destruction policy and resolution."""

# pyright: reportPrivateUsage=false
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, cast

from warhammer40k_core.core.ruleset_descriptor import (
    MissionPolicyDescriptor,
    ReserveDestructionTimingKind,
    reserve_destruction_timing_kind_from_token,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
    BattlefieldRuntimeState,
    BattlefieldTransitionBatch,
    ModelRemovalRecord,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_from_armies
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_reserve_lifetimes_2026_09 as source,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.army_mustering import ArmyDefinition
    from warhammer40k_core.engine.reserves import (
        ReserveDestructionResult,
        ReserveDestructionTimingPolicyPayload,
        ReserveState,
    )

_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_bool(name: str, value: object) -> bool:
    if type(value) is not bool:
        raise GameLifecycleError(f"{name} must be a bool.")
    return value


def _validate_positive_int(name: str, value: object) -> int:
    if type(value) is not int or value < 1:
        raise GameLifecycleError(f"{name} must be a positive integer.")
    return value


def _validate_optional_positive_int(name: str, value: object) -> int | None:
    return None if value is None else _validate_positive_int(name, value)


@dataclass(frozen=True, slots=True)
class ReserveDestructionTimingPolicy:
    timing_kind: ReserveDestructionTimingKind
    battle_round: int | None = None
    exclude_during_battle_strategic_reserves: bool = False
    only_declare_battle_formations: bool = False
    source_id: str = "core_rules_reserve_destruction"

    def __post_init__(self) -> None:
        timing = reserve_destruction_timing_kind_from_token(self.timing_kind)
        object.__setattr__(self, "timing_kind", timing)
        object.__setattr__(
            self,
            "battle_round",
            _validate_optional_positive_int(
                "ReserveDestructionTimingPolicy battle_round",
                self.battle_round,
            ),
        )
        object.__setattr__(
            self,
            "exclude_during_battle_strategic_reserves",
            _validate_bool(
                "ReserveDestructionTimingPolicy exclude_during_battle_strategic_reserves",
                self.exclude_during_battle_strategic_reserves,
            ),
        )
        object.__setattr__(
            self,
            "only_declare_battle_formations",
            _validate_bool(
                "ReserveDestructionTimingPolicy only_declare_battle_formations",
                self.only_declare_battle_formations,
            ),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("ReserveDestructionTimingPolicy source_id", self.source_id),
        )
        if timing is ReserveDestructionTimingKind.END_OF_BATTLE and self.battle_round is not None:
            raise GameLifecycleError("END_OF_BATTLE reserve destruction must not set battle_round.")
        if (
            timing is ReserveDestructionTimingKind.END_OF_BATTLE_ROUND_N
            and self.battle_round is None
        ):
            raise GameLifecycleError(
                "END_OF_BATTLE_ROUND_N reserve destruction requires battle_round."
            )

    @classmethod
    def core_rules_default(cls) -> Self:
        return cls(
            timing_kind=ReserveDestructionTimingKind.END_OF_BATTLE_ROUND_N,
            battle_round=source.RESERVE_LIFETIMES_POLICY.destruction_battle_round,
            exclude_during_battle_strategic_reserves=False,
            only_declare_battle_formations=False,
            source_id=source.RESERVE_LIFETIMES_POLICY.arrival_source_id,
        )

    @classmethod
    def chapter_approved_2026_27(cls) -> Self:
        return cls(
            timing_kind=ReserveDestructionTimingKind.END_OF_BATTLE_ROUND_N,
            battle_round=3,
            exclude_during_battle_strategic_reserves=True,
            only_declare_battle_formations=True,
            source_id="chapter_approved_2026_27_reserves_restrictions",
        )

    @classmethod
    def from_mission_policy(
        cls, mission_policy: MissionPolicyDescriptor, *, source_id: str | None = None
    ) -> Self:
        if type(mission_policy) is not MissionPolicyDescriptor:
            raise GameLifecycleError(
                "ReserveDestructionTimingPolicy requires a MissionPolicyDescriptor."
            )
        if source_id is None:
            if mission_policy == MissionPolicyDescriptor.core_rules_default():
                source_id = source.RESERVE_LIFETIMES_POLICY.arrival_source_id
            elif mission_policy == MissionPolicyDescriptor.chapter_approved_2026_27():
                source_id = "chapter_approved_2026_27_reserves_restrictions"
            else:
                raise GameLifecycleError("Reserve policy override requires explicit source_id.")
        return cls(
            timing_kind=mission_policy.reserve_destruction_timing,
            battle_round=mission_policy.reserve_destruction_battle_round,
            exclude_during_battle_strategic_reserves=(
                mission_policy.reserve_destruction_excludes_during_battle_strategic_reserves
            ),
            only_declare_battle_formations=(
                mission_policy.reserve_destruction_only_declare_battle_formations
            ),
            source_id=source_id,
        )

    def applies_at(self, *, battle_round: int, end_of_battle: bool) -> bool:
        requested_round = _validate_positive_int("battle_round", battle_round)
        if self.timing_kind is ReserveDestructionTimingKind.END_OF_BATTLE:
            return _validate_bool("end_of_battle", end_of_battle)
        return (
            not _validate_bool("end_of_battle", end_of_battle)
            and self.battle_round == requested_round
        )

    def applies_to_reserve_state(self, reserve_state: ReserveState) -> bool:
        from warhammer40k_core.engine.reserves import (
            ReserveKind,
            ReserveOrigin,
            ReserveState,
            ReserveStatus,
        )

        if type(reserve_state) is not ReserveState:
            raise GameLifecycleError("reserve_state must be a ReserveState.")
        if reserve_state.status is not ReserveStatus.IN_RESERVES:
            return False
        if (
            self.exclude_during_battle_strategic_reserves
            and reserve_state.reserve_kind is ReserveKind.STRATEGIC_RESERVES
            and reserve_state.reserve_origin
            in {
                ReserveOrigin.DURING_BATTLE_ABILITY,
                ReserveOrigin.DURING_BATTLE_STRATAGEM,
                ReserveOrigin.DURING_BATTLE_OTHER,
            }
        ):
            return False
        return not (
            self.only_declare_battle_formations
            and reserve_state.reserve_origin is not ReserveOrigin.DECLARE_BATTLE_FORMATIONS
        )

    def to_payload(self) -> ReserveDestructionTimingPolicyPayload:
        return {
            "timing_kind": self.timing_kind.value,
            "battle_round": self.battle_round,
            "exclude_during_battle_strategic_reserves": (
                self.exclude_during_battle_strategic_reserves
            ),
            "only_declare_battle_formations": self.only_declare_battle_formations,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: ReserveDestructionTimingPolicyPayload) -> Self:
        return cls(
            timing_kind=reserve_destruction_timing_kind_from_token(payload["timing_kind"]),
            battle_round=payload["battle_round"],
            exclude_during_battle_strategic_reserves=payload[
                "exclude_during_battle_strategic_reserves"
            ],
            only_declare_battle_formations=payload["only_declare_battle_formations"],
            source_id=payload["source_id"],
        )


def resolve_unarrived_reserve_destruction(
    *,
    reserve_states: tuple[ReserveState, ...],
    armies: tuple[ArmyDefinition, ...],
    battlefield_state: BattlefieldRuntimeState,
    policy: ReserveDestructionTimingPolicy,
    battle_round: int,
    end_of_battle: bool,
    exempt_unit_instance_ids: frozenset[str] = frozenset(),
) -> ReserveDestructionResult:
    from warhammer40k_core.engine.reserves import (
        ReserveDestructionResult,
        _validate_reserve_state_tuple,
    )

    states = _validate_reserve_state_tuple("reserve_states", reserve_states)
    if type(battlefield_state) is not BattlefieldRuntimeState:
        raise GameLifecycleError("battlefield_state must be a BattlefieldRuntimeState.")
    if type(policy) is not ReserveDestructionTimingPolicy:
        raise GameLifecycleError("policy must be a ReserveDestructionTimingPolicy.")
    requested_round = _validate_positive_int("battle_round", battle_round)
    end = _validate_bool("end_of_battle", end_of_battle)
    if type(exempt_unit_instance_ids) is not frozenset:
        raise GameLifecycleError("Reserve deadline exemptions must be a frozenset of unit IDs.")
    for unit_id in exempt_unit_instance_ids:
        _validate_identifier("Reserve deadline exemption", unit_id)
    if not exempt_unit_instance_ids.issubset(row.unit_instance_id for row in states):
        raise GameLifecycleError("Reserve deadline exemption references an unknown reserve.")
    if not policy.applies_at(battle_round=requested_round, end_of_battle=end):
        return ReserveDestructionResult(
            policy=policy,
            battle_round=requested_round,
            end_of_battle=end,
            destroyed_unit_instance_ids=(),
            destroyed_model_instance_ids=(),
            transition_batch=BattlefieldTransitionBatch(),
            updated_reserve_states=states,
        )

    army_tuple = _validate_army_tuple("armies", armies)
    unit_by_id = {unit.unit_instance_id: unit for army in army_tuple for unit in army.units}
    destroyed_unit_ids: set[str] = set()
    destroyed_model_ids: set[str] = set()
    updated_states: list[ReserveState] = []
    for reserve_state in states:
        if not policy.applies_to_reserve_state(reserve_state) or (
            not end and reserve_state.unit_instance_id in exempt_unit_instance_ids
        ):
            updated_states.append(reserve_state)
            continue
        try:
            reserve_view = rules_unit_view_from_armies(
                armies=army_tuple,
                unit_instance_id=reserve_state.unit_instance_id,
            )
        except GameLifecycleError as exc:
            raise GameLifecycleError("ReserveState references an unknown unit.") from exc
        destroyed_unit_ids.add(reserve_view.unit_instance_id)
        destroyed_model_ids.update(model.model_instance_id for model in reserve_view.own_models)
        for unit_id in reserve_state.embarked_unit_instance_ids:
            unit = unit_by_id.get(unit_id)
            if unit is None:
                raise GameLifecycleError("ReserveState references an unknown unit.")
            destroyed_unit_ids.add(unit_id)
            destroyed_model_ids.update(model.model_instance_id for model in unit.own_models)
        updated_states.append(
            reserve_state.mark_destroyed(battle_round=requested_round, end_of_battle=end)
        )

    transition_batch = BattlefieldTransitionBatch(
        removals=tuple(
            ModelRemovalRecord(
                model_instance_id=model_id,
                removal_kind=BattlefieldRemovalKind.DESTROYED,
                source_phase=None,
                source_step=None,
                source_rule_id=policy.source_id,
                source_event_id=None,
                destination_id=None,
            )
            for model_id in sorted(destroyed_model_ids)
        )
    )
    return ReserveDestructionResult(
        policy=policy,
        battle_round=requested_round,
        end_of_battle=end,
        destroyed_unit_instance_ids=tuple(sorted(destroyed_unit_ids)),
        destroyed_model_instance_ids=tuple(sorted(destroyed_model_ids)),
        transition_batch=transition_batch,
        updated_reserve_states=tuple(updated_states),
    )


def final_turn_cleanup_policy() -> ReserveDestructionTimingPolicy:
    return ReserveDestructionTimingPolicy(
        timing_kind=ReserveDestructionTimingKind.END_OF_BATTLE,
        source_id=source.RESERVE_LIFETIMES_POLICY.cleanup_source_id,
    )


def destruction_policy_for_terminal_state(
    reserve_state: ReserveState,
) -> ReserveDestructionTimingPolicy:
    return (
        final_turn_cleanup_policy()
        if reserve_state.destroyed_at_end_of_battle
        else reserve_state.destruction_deadline_policy
    )


def _validate_army_tuple(field_name: str, values: object) -> tuple[ArmyDefinition, ...]:
    from warhammer40k_core.engine.army_mustering import ArmyDefinition

    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    armies: list[ArmyDefinition] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not ArmyDefinition:
            raise GameLifecycleError(f"{field_name} must contain ArmyDefinition values.")
        armies.append(value)
    return tuple(sorted(armies, key=lambda army: army.army_id))
