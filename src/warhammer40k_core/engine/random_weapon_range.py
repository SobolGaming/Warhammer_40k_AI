"""Selection-scoped Range rolls and read-only weapon inventory resolution."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice import (
    RandomCharacteristicRoll,
    RandomCharacteristicRollPayload,
    RandomCharacteristicTiming,
)
from warhammer40k_core.core.random_profile_values import (
    RandomProfileValue,
    RandomProfileValuePayload,
)
from warhammer40k_core.core.weapon_profiles import RangeProfile, WeaponProfile
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import (
    EventRecord,
    JsonValue,
    canonical_json,
    validate_json_value,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.random_profile_inventory import historical_profile_models
from warhammer40k_core.engine.random_profile_roll_authority import validate_profile_roll
from warhammer40k_core.engine.rules_units import rules_unit_identity_history_contains
from warhammer40k_core.engine.transports import TransportCargoState, TransportCargoStatePayload
from warhammer40k_core.engine.weapon_instances import equipped_weapon_instances_for_model
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_random_profiles_2026_09 as random_source,
)

if TYPE_CHECKING:
    from warhammer40k_core.core.army_catalog import ArmyCatalog
    from warhammer40k_core.engine.decision_request import DecisionRequest
    from warhammer40k_core.engine.game_state import GameConfig, GameState
    from warhammer40k_core.engine.phases.shooting_model import (
        ShootingUnitSelection,
        _AvailableWeapon,
    )
    from warhammer40k_core.engine.weapon_selection_context import WeaponSelectionContext


class WeaponRangeEvaluationPayload(TypedDict):
    selection_result_id: str
    player_id: str
    unit_instance_id: str
    model_instance_id: str
    weapon_instance_id: str
    wargear_id: str
    weapon_profile_id: str
    value: RandomProfileValuePayload


@dataclass(frozen=True, slots=True)
class WeaponRangeEvaluation:
    selection_result_id: str
    player_id: str
    unit_instance_id: str
    model_instance_id: str
    weapon_instance_id: str
    wargear_id: str
    weapon_profile_id: str
    value: RandomProfileValue

    def __post_init__(self) -> None:
        for token in (
            self.selection_result_id,
            self.player_id,
            self.unit_instance_id,
            self.model_instance_id,
            self.weapon_instance_id,
            self.wargear_id,
            self.weapon_profile_id,
        ):
            if type(token) is not str or not token.strip():
                raise GameLifecycleError("Random weapon Range requires stable source identities.")
        if (
            type(self.value) is not RandomProfileValue
            or self.value.characteristic is not Characteristic.RANGE
            or self.value.evaluation is None
            or self.value.evaluation_id != self.scope_id
        ):
            raise GameLifecycleError("Random weapon Range evaluation identity drifted.")

    @property
    def scope_id(self) -> str:
        return (
            f"{self.selection_result_id}:range:{self.weapon_instance_id}:{self.weapon_profile_id}"
        )

    def to_payload(self) -> WeaponRangeEvaluationPayload:
        return {
            "selection_result_id": self.selection_result_id,
            "player_id": self.player_id,
            "unit_instance_id": self.unit_instance_id,
            "model_instance_id": self.model_instance_id,
            "weapon_instance_id": self.weapon_instance_id,
            "wargear_id": self.wargear_id,
            "weapon_profile_id": self.weapon_profile_id,
            "value": self.value.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: WeaponRangeEvaluationPayload) -> Self:
        if set(payload) != set(cls.__dataclass_fields__):
            raise GameLifecycleError("Random weapon Range payload fields drifted.")
        return cls(
            selection_result_id=payload["selection_result_id"],
            player_id=payload["player_id"],
            unit_instance_id=payload["unit_instance_id"],
            model_instance_id=payload["model_instance_id"],
            weapon_instance_id=payload["weapon_instance_id"],
            wargear_id=payload["wargear_id"],
            weapon_profile_id=payload["weapon_profile_id"],
            value=RandomProfileValue.from_payload(payload["value"]),
        )


def evaluate_weapon_ranges(
    *,
    state: GameState,
    decisions: DecisionController,
    selection: ShootingUnitSelection,
    weapons: tuple[_AvailableWeapon, ...],
) -> None:
    manager: DiceRollManager | None = None
    for weapon in weapons:
        profile = weapon["weapon_profile"]
        value = profile.range_profile.random_value
        if value is None:
            continue
        scope = f"{selection.result_id}:range:{weapon['weapon_instance_id']}:{profile.profile_id}"
        if any(record.scope_id == scope for record in state.random_weapon_ranges):
            continue
        if manager is None:
            manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
        roll = manager.roll_random_characteristic(
            characteristic=Characteristic.RANGE,
            timing=RandomCharacteristicTiming.PER_WEAPON,
            scope_id=scope,
            expression=value.expression,
            reason="Weapon profile range",
            actor_id=selection.player_id,
        )
        record = WeaponRangeEvaluation(
            selection_result_id=selection.result_id,
            player_id=selection.player_id,
            unit_instance_id=selection.unit_instance_id,
            model_instance_id=weapon["model_instance_id"],
            weapon_instance_id=weapon["weapon_instance_id"],
            wargear_id=weapon["wargear_id"],
            weapon_profile_id=profile.profile_id,
            value=value.evaluate(
                raw=roll.value, evaluation_id=scope, target_id=weapon["weapon_instance_id"]
            ),
        )
        state.random_weapon_ranges.append(record)
        decisions.event_log.append(
            "random_weapon_range_evaluated",
            validate_json_value(
                {
                    "source_rule_id": random_source.RANDOM_PROFILES_SOURCE_ID,
                    "evaluation": record.to_payload(),
                    "roll": roll.to_payload(),
                }
            ),
        )


def weapon_with_selected_range(
    *,
    state: GameState,
    unit_instance_id: str,
    weapon: _AvailableWeapon,
) -> _AvailableWeapon:
    profile = weapon["weapon_profile"]
    value = profile.range_profile.random_value
    if value is None:
        return weapon
    result_id: str | None = None
    ordinary = state.shooting_phase_state
    if (
        ordinary is not None
        and ordinary.active_selection is not None
        and ordinary.active_selection.unit_instance_id == unit_instance_id
    ):
        result_id = ordinary.active_selection.result_id
    interrupt = state.out_of_phase_shooting_state
    if interrupt is not None and interrupt.selected_unit_instance_id == unit_instance_id:
        result_id = interrupt.source_decision_result_id
    if result_id is None:
        return weapon  # No selection: the inventory still contains an unresolved source expression.
    scope = f"{result_id}:range:{weapon['weapon_instance_id']}:{profile.profile_id}"
    records = [record for record in state.random_weapon_ranges if record.scope_id == scope]
    if not records:
        return (
            weapon  # The engine has not yet reached the selected unit's Range evaluation boundary.
        )
    if len(records) != 1 or replace(records[0].value, evaluation=None, evaluation_id=None) != value:
        raise GameLifecycleError("Selected weapon Range descriptor drifted.")
    return {
        **weapon,
        "weapon_profile": replace(profile, range_profile=RangeProfile.random(records[0].value)),
    }


def validate_weapon_range_history(
    *,
    state: GameState,
    catalog: ArmyCatalog | None,
    events: tuple[EventRecord, ...],
    decisions: tuple[DecisionRecord, ...],
    config: GameConfig | None = None,
    pending_requests: tuple[DecisionRequest, ...] = (),
) -> None:
    if not state.random_weapon_ranges and not any(
        event.event_type == "random_weapon_range_evaluated" for event in events
    ):
        return
    models, owners, physical_units = historical_profile_models(
        state=state,
        config=config,
        requests=(*tuple(record.request for record in decisions), *pending_requests),
    )
    physical_weapons = {
        weapon.weapon_instance_id: weapon
        for model in models.values()
        for weapon in equipped_weapon_instances_for_model(model)
    }
    by_result = {record.result.result_id: record for record in decisions}
    dice: dict[str, JsonValue] = {}
    random_rolls: set[str] = set()
    expected: list[WeaponRangeEvaluation] = []
    cargo_by_transport: dict[str, TransportCargoState] = {}
    for event in events:
        body = event.payload
        if not isinstance(body, dict):
            continue
        if event.event_type == "battle_formations_revealed":
            raw_cargo = body.get("transport_cargo_states")
            if not isinstance(raw_cargo, list):
                raise GameLifecycleError("Random Range initial cargo inventory is invalid.")
            for raw in raw_cargo:
                if not isinstance(raw, dict):
                    raise GameLifecycleError("Random Range initial cargo entry is invalid.")
                cargo = TransportCargoState.from_payload(cast(TransportCargoStatePayload, raw))
                cargo_by_transport[cargo.transport_unit_instance_id] = cargo
        raw_updated_cargo = body.get("updated_cargo_state")
        if isinstance(raw_updated_cargo, dict):
            cargo = TransportCargoState.from_payload(
                cast(TransportCargoStatePayload, raw_updated_cargo)
            )
            cargo_by_transport[cargo.transport_unit_instance_id] = cargo
        if event.event_type == "dice_rolled" and type(body.get("roll_id")) is str:
            dice[cast(str, body["roll_id"])] = body
        elif event.event_type == "random_characteristic_rolled":
            random_rolls.add(canonical_json(body))
        elif event.event_type == "random_weapon_range_evaluated":
            if (
                set(body) != {"source_rule_id", "evaluation", "roll"}
                or body["source_rule_id"] != random_source.RANDOM_PROFILES_SOURCE_ID
                or not isinstance(body["evaluation"], dict)
                or not isinstance(body["roll"], dict)
                or catalog is None
            ):
                raise GameLifecycleError("Random Range source evidence is invalid.")
            record = WeaponRangeEvaluation.from_payload(
                cast(WeaponRangeEvaluationPayload, body["evaluation"])
            )
            weapon = physical_weapons.get(record.weapon_instance_id)
            if (
                weapon is None
                or weapon.wargear_id != record.wargear_id
                or owners.get(weapon.model_instance_id) != record.player_id
                or owners.get(record.model_instance_id) != record.player_id
                or not rules_unit_identity_history_contains(
                    state=state,
                    identity_ids=(record.unit_instance_id,),
                    unit_instance_id=physical_units[record.model_instance_id],
                )
            ):
                raise GameLifecycleError("Random Range physical weapon ownership drifted.")
            if weapon.model_instance_id != record.model_instance_id:
                borrowed_cargo = cargo_by_transport.get(physical_units[record.model_instance_id])
                if (
                    borrowed_cargo is None
                    or borrowed_cargo.player_id != record.player_id
                    or physical_units[weapon.model_instance_id]
                    not in borrowed_cargo.embarked_unit_instance_ids
                ):
                    raise GameLifecycleError(
                        "Random Range borrowed weapon lacks embarked ownership."
                    )
            decision = by_result.get(record.selection_result_id)
            if decision is None or decision.result.actor_id != record.player_id:
                raise GameLifecycleError("Random Range lacks its accepted selection.")
            if decision.request.decision_type == "select_shooting_unit":
                if decision.result.selected_option_id != record.unit_instance_id:
                    raise GameLifecycleError("Random Range selected unit drifted.")
            elif not any(
                e.event_type == "out_of_phase_shooting_started"
                and isinstance(e.payload, dict)
                and e.payload.get("source_decision_result_id") == record.selection_result_id
                and e.payload.get("selected_unit_instance_id") == record.unit_instance_id
                for e in events
            ):
                raise GameLifecycleError("Random Range lacks its interrupt selection.")
            sources = [
                profile.range_profile.random_value
                for item in catalog.wargear
                if item.wargear_id == record.wargear_id
                for profile in item.weapon_profiles
                if profile.profile_id == record.weapon_profile_id
            ]
            if sources != [replace(record.value, evaluation=None, evaluation_id=None)]:
                raise GameLifecycleError("Random Range catalog source drifted.")
            roll = RandomCharacteristicRoll.from_payload(
                cast(RandomCharacteristicRollPayload, body["roll"])
            )
            validate_profile_roll(
                roll=roll,
                value=record.value,
                scope_id=record.scope_id,
                timing=RandomCharacteristicTiming.PER_WEAPON,
                actor_id=record.player_id,
                reason="Weapon profile range",
                physical_rolls=dice,
                random_rolls=random_rolls,
            )
            if record.value.evaluate(
                raw=roll.value, evaluation_id=record.scope_id, target_id=record.weapon_instance_id
            ) != record.value or any(prior.scope_id == record.scope_id for prior in expected):
                raise GameLifecycleError("Random Range value drifted or occurrence duplicated.")
            expected.append(record)
    if state.random_weapon_ranges != expected:
        raise GameLifecycleError("Random Range state inventory is not authenticated.")


def prepare_selected_weapon_ranges(
    *,
    state: GameState,
    decisions: DecisionController,
    selection: ShootingUnitSelection,
    catalog: ArmyCatalog,
) -> None:
    if not any(
        profile.range_profile.random_value is not None
        for wargear in catalog.wargear
        for profile in wargear.weapon_profiles
    ):
        return
    from warhammer40k_core.engine.phases.shooting_firing_deck import (
        _available_weapons_for_rules_unit,
    )
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    weapons = _available_weapons_for_rules_unit(
        state=state,
        rules_unit=rules_unit_view_by_id(state=state, unit_instance_id=selection.unit_instance_id),
        army_catalog=catalog,
        player_id=selection.player_id,
    )
    evaluate_weapon_ranges(state=state, decisions=decisions, selection=selection, weapons=weapons)


def has_unresolved_weapon_range(weapon: _AvailableWeapon) -> bool:
    value = weapon["weapon_profile"].range_profile.random_value
    return value is not None and value.evaluation is None


def weapon_with_committed_range(
    profile: WeaponProfile,
    *,
    context: WeaponSelectionContext,
) -> WeaponProfile:
    """Target replacement retains the original physical Range roll."""
    value = profile.range_profile.random_value
    if value is None:
        return profile
    committed_values = [
        candidate.range_profile.random_value for _, candidate in context.target_profiles
    ]
    if not committed_values or any(
        item is None or item.evaluation is None for item in committed_values
    ):
        raise GameLifecycleError("Target replacement is missing its committed random Range.")
    first = committed_values[0]
    if (
        first is None
        or first.evaluation_id is None
        or any(item != first for item in committed_values)
        or replace(first, modifiers=(), evaluation=None, evaluation_id=None)
        != replace(value, modifiers=(), evaluation=None, evaluation_id=None)
    ):
        raise GameLifecycleError("Target replacement random Range evidence drifted.")
    return replace(
        profile,
        range_profile=RangeProfile.random(
            value.evaluate(
                raw=first.raw,
                evaluation_id=first.evaluation_id,
                target_id=context.weapon_instance_id,
            )
        ),
    )
