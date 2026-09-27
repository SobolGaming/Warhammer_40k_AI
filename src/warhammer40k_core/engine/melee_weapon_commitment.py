"""Order 92's provisional, melee-only pre-target random-A convention.

Accepted finite choices commit all physical weapons/profiles before any A dice.
The commitment event is the persistent authority; requests only project it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice import (
    RandomCharacteristicRoll,
    RandomCharacteristicRollPayload,
    RandomCharacteristicTiming,
)
from warhammer40k_core.core.weapon_profiles import (
    AttackProfile,
    AttackProfilePayload,
    WeaponProfile,
    WeaponProfilePayload,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_order import FightActivationSelection
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

SELECT_MELEE_WEAPON_DECISION_TYPE = "select_melee_weapon"
MELEE_COMMITMENT_EVENT = "melee_weapons_committed"
MELEE_CONVENTION_ID = "core-rules-owner-convention:order92:random-melee-pretarget:2026-09-27"
COMMITMENT_KEY = "melee_weapon_commitment"


def object_payload(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Melee commitment requires an object.")
    return value


def identifier(row: dict[str, JsonValue], key: str) -> str:
    value = row[key]
    if type(value) is not str or not value or value.strip() != value:
        raise GameLifecycleError("Melee commitment identifier is invalid.")
    return value


def weapon_profile(row: dict[str, JsonValue]) -> WeaponProfile:
    return WeaponProfile.from_payload(
        cast(WeaponProfilePayload, object_payload(row["weapon_profile"]))
    )


@dataclass(frozen=True, slots=True)
class MeleeAttackBudget:
    weapon_instance_id: str
    model_instance_id: str
    wargear_id: str
    weapon_profile_id: str
    source_attack_profile: AttackProfile
    roll: RandomCharacteristicRoll | None

    def __post_init__(self) -> None:
        for value in (
            self.weapon_instance_id,
            self.model_instance_id,
            self.wargear_id,
            self.weapon_profile_id,
        ):
            if type(value) is not str or not value or value.strip() != value:
                raise GameLifecycleError("Melee budget requires physical weapon identifiers.")
        if type(self.source_attack_profile) is not AttackProfile:
            raise GameLifecycleError("Melee budget requires its source attack profile.")
        expression = self.source_attack_profile.dice_expression
        if expression is None:
            if self.roll is not None:
                raise GameLifecycleError("Fixed melee Attacks must not acquire dice.")
        elif (
            self.roll is None
            or self.roll.characteristic is not Characteristic.ATTACKS
            or self.roll.timing is not RandomCharacteristicTiming.PER_WEAPON
            or self.roll.roll_state.original_result.spec.expression != expression
        ):
            raise GameLifecycleError("Random melee budget lacks its source roll.")
        if self.base_attacks < 1:
            raise GameLifecycleError("Melee attack budget must be positive.")

    @property
    def base_attacks(self) -> int:
        if self.roll is not None:
            return self.roll.value
        value = self.source_attack_profile.fixed_attacks
        if value is None:
            raise GameLifecycleError("Melee budget has no attack count.")
        return value

    def attacks_for(self, profile: WeaponProfile) -> int:
        """Apply current source-backed profile changes without replacing the roll."""
        if profile.profile_id != self.weapon_profile_id:
            raise GameLifecycleError("Committed melee profile cannot change.")
        current = profile.attack_profile
        if current.fixed_attacks is not None:
            return current.fixed_attacks
        original, expression = self.source_attack_profile.dice_expression, current.dice_expression
        if (
            original is None
            or expression is None
            or (original.quantity != expression.quantity or original.sides != expression.sides)
        ):
            raise GameLifecycleError("Melee attack dice expression changed after commitment.")
        return max(1, self.base_attacks + expression.modifier - original.modifier)

    def to_payload(self) -> dict[str, JsonValue]:
        return object_payload(
            validate_json_value(
                {
                    "weapon_instance_id": self.weapon_instance_id,
                    "model_instance_id": self.model_instance_id,
                    "wargear_id": self.wargear_id,
                    "weapon_profile_id": self.weapon_profile_id,
                    "source_attack_profile": self.source_attack_profile.to_payload(),
                    "roll": None if self.roll is None else self.roll.to_payload(),
                    "base_attacks": self.base_attacks,
                }
            )
        )

    @classmethod
    def from_payload(cls, value: JsonValue) -> MeleeAttackBudget:
        row = object_payload(value)
        if set(row) != {
            "weapon_instance_id",
            "model_instance_id",
            "wargear_id",
            "weapon_profile_id",
            "source_attack_profile",
            "roll",
            "base_attacks",
        }:
            raise GameLifecycleError("Melee budget fields drifted.")
        raw_roll = row["roll"]
        budget = cls(
            weapon_instance_id=identifier(row, "weapon_instance_id"),
            model_instance_id=identifier(row, "model_instance_id"),
            wargear_id=identifier(row, "wargear_id"),
            weapon_profile_id=identifier(row, "weapon_profile_id"),
            source_attack_profile=AttackProfile.from_payload(
                cast(AttackProfilePayload, object_payload(row["source_attack_profile"]))
            ),
            roll=None
            if raw_roll is None
            else RandomCharacteristicRoll.from_payload(
                cast(RandomCharacteristicRollPayload, object_payload(raw_roll))
            ),
        )
        if type(row["base_attacks"]) is not int or row["base_attacks"] != budget.base_attacks:
            raise GameLifecycleError("Melee budget total drifted from its dice.")
        return budget


def commitment_for_activation(
    decisions: DecisionController,
    activation_id: str,
) -> dict[str, JsonValue] | None:
    matches = [
        object_payload(event.payload)
        for event in decisions.event_log.records
        if event.event_type == MELEE_COMMITMENT_EVENT
        and object_payload(event.payload).get("activation_result_id") == activation_id
    ]
    if len(matches) > 1:
        raise GameLifecycleError("Melee activation has duplicate commitments.")
    return matches[0] if matches else None


def budgets_from_commitment(value: JsonValue) -> dict[str, MeleeAttackBudget]:
    entries = object_payload(value)["weapons"]
    if not isinstance(entries, list):
        raise GameLifecycleError("Melee commitment requires weapons.")
    budgets = tuple(MeleeAttackBudget.from_payload(entry) for entry in entries)
    result = {budget.weapon_instance_id: budget for budget in budgets}
    if len(result) != len(budgets):
        raise GameLifecycleError("Melee commitment duplicated a physical weapon.")
    return result


def selection_records(
    decisions: DecisionController, activation_id: str
) -> tuple[DecisionRecord, ...]:
    return tuple(
        record
        for record in decisions.records
        if record.request.decision_type == SELECT_MELEE_WEAPON_DECISION_TYPE
        and object_payload(record.request.payload).get("activation_result_id") == activation_id
    )


def selection_stages(
    rows: tuple[JsonValue, ...],
) -> tuple[tuple[str, tuple[dict[str, JsonValue], ...], bool], ...]:
    eligible = [
        object_payload(row)
        for row in rows
        if object_payload(row)["engaged_target_unit_instance_ids"]
    ]
    stages: list[tuple[str, tuple[dict[str, JsonValue], ...], bool]] = []
    for model_id in sorted({identifier(row, "model_instance_id") for row in eligible}):
        model_rows = [row for row in eligible if row["model_instance_id"] == model_id]
        primary = tuple(row for row in model_rows if row["is_extra_attacks"] is False)
        if primary:
            stages.append((f"{model_id}:primary", primary, False))
        extra_ids = sorted(
            {
                identifier(row, "weapon_instance_id")
                for row in model_rows
                if row["is_extra_attacks"] is True
            }
        )
        for weapon_id in extra_ids:
            extra = tuple(
                row
                for row in model_rows
                if row["is_extra_attacks"] is True and row["weapon_instance_id"] == weapon_id
            )
            stages.append((f"{model_id}:extra:{weapon_id}", extra, True))
    return tuple(stages)


def selection_request(
    *,
    request_id: str,
    activation: FightActivationSelection,
    rows: tuple[JsonValue, ...],
    index: int,
    previous: tuple[DecisionRecord, ...] = (),
) -> DecisionRequest:
    stage_id, candidates, optional = selection_stages(rows)[index]
    used = {identifier(row, "weapon_instance_id") for row in chosen_rows(rows, previous)}
    options = tuple(
        DecisionOption(
            option_id=(
                f"weapon:{identifier(row, 'weapon_instance_id')}:"
                f"{identifier(row, 'weapon_profile_id')}"
            ),
            label=weapon_profile(row).name,
            payload={
                key: row[key]
                for key in (
                    "model_instance_id",
                    "weapon_instance_id",
                    "wargear_id",
                    "weapon_profile_id",
                )
            },
        )
        for row in candidates
        if row["weapon_instance_id"] not in used
    )
    if optional:
        options += (
            DecisionOption(
                option_id="skip_extra", label="Do not use this Extra Attacks weapon", payload=None
            ),
        )
    return DecisionRequest(
        request_id=request_id,
        decision_type=SELECT_MELEE_WEAPON_DECISION_TYPE,
        actor_id=activation.player_id,
        payload={
            "convention_id": MELEE_CONVENTION_ID,
            "activation_result_id": activation.result_id,
            "activation_request_id": activation.request_id,
            "unit_instance_id": activation.unit_instance_id,
            "stage_id": stage_id,
            "stage_index": index,
            "available_weapons": list(rows),
        },
        options=options,
    )


def chosen_rows(
    rows: tuple[JsonValue, ...], records: tuple[DecisionRecord, ...]
) -> tuple[dict[str, JsonValue], ...]:
    selected: list[dict[str, JsonValue]] = []
    seen: set[str] = set()
    for record in records:
        selection = record.result.payload
        if selection is None:
            continue
        body = object_payload(selection)
        matches = [
            object_payload(row)
            for row in rows
            if all(
                object_payload(row)[key] == body[key]
                for key in (
                    "model_instance_id",
                    "weapon_instance_id",
                    "wargear_id",
                    "weapon_profile_id",
                )
            )
        ]
        if len(matches) != 1:
            raise GameLifecycleError("Melee commitment lost its physical weapon/profile.")
        row = matches[0]
        weapon_id = identifier(row, "weapon_instance_id")
        if weapon_id in seen:
            raise GameLifecycleError("A physical melee weapon cannot use multiple profiles.")
        seen.add(weapon_id)
        selected.append(row)
    return tuple(selected)


def requires_melee_commitment(rows: tuple[JsonValue, ...]) -> bool:
    return any(
        weapon_profile(object_payload(row)).attack_profile.dice_expression is not None
        and bool(object_payload(row)["engaged_target_unit_instance_ids"])
        for row in rows
    )


def prepare_melee_commitment(
    *,
    state: GameState,
    decisions: DecisionController,
    activation: FightActivationSelection,
    rows: tuple[JsonValue, ...],
) -> LifecycleStatus | None:
    if commitment_for_activation(decisions, activation.result_id) is not None:
        return None
    records = selection_records(decisions, activation.result_id)
    if not records and not requires_melee_commitment(rows):
        return None
    stages = selection_stages(rows)
    for index, record in enumerate(records):
        expected = selection_request(
            request_id=record.request.request_id,
            activation=activation,
            rows=rows,
            index=index,
            previous=records[:index],
        )
        if record.request != expected:
            raise GameLifecycleError("Committed melee weapon inventory drifted.")
    if len(records) < len(stages):
        request = selection_request(
            request_id=state.next_decision_request_id(),
            activation=activation,
            rows=rows,
            index=len(records),
            previous=records,
        )
        decisions.request_decision(request)
        return LifecycleStatus.waiting_for_decision(
            stage=state.stage,
            decision_request=request,
            payload={"phase": "fight", "phase_body_status": "melee_weapon_commitment_required"},
        )
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    budgets: list[MeleeAttackBudget] = []
    for row in chosen_rows(rows, records):
        profile = weapon_profile(row)
        weapon_id = identifier(row, "weapon_instance_id")
        expression = profile.attack_profile.dice_expression
        roll = (
            None
            if expression is None
            else manager.roll_random_characteristic(
                characteristic=Characteristic.ATTACKS,
                timing=RandomCharacteristicTiming.PER_WEAPON,
                scope_id=f"melee-commitment:{activation.result_id}:{weapon_id}:{profile.profile_id}",
                expression=expression,
                reason=f"Committed melee Attacks for {profile.profile_id}",
                actor_id=activation.player_id,
            )
        )
        budgets.append(
            MeleeAttackBudget(
                weapon_id,
                identifier(row, "model_instance_id"),
                identifier(row, "wargear_id"),
                profile.profile_id,
                profile.attack_profile,
                roll,
            )
        )
    decisions.event_log.append(
        MELEE_COMMITMENT_EVENT,
        {
            "convention_id": MELEE_CONVENTION_ID,
            "activation_result_id": activation.result_id,
            "activation_request_id": activation.request_id,
            "unit_instance_id": activation.unit_instance_id,
            "player_id": activation.player_id,
            "selection_result_ids": [record.result.result_id for record in records],
            "weapons": [budget.to_payload() for budget in budgets],
        },
    )
    return None
