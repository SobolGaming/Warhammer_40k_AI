"""Closed source snapshots and finite per-modifier selection records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.modifiers import (
    Modifier,
    ModifierPayload,
    ModifierStack,
    RollModifier,
    RollModifierPayload,
)
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError


@dataclass(frozen=True, slots=True)
class AttackModifierSnapshot:
    kind: Literal["skill", "hit_roll"]
    modifier: Modifier | RollModifier

    def __post_init__(self) -> None:
        expected = Modifier if self.kind == "skill" else RollModifier
        if self.kind not in {"skill", "hit_roll"} or type(self.modifier) is not expected:
            raise GameLifecycleError("Attack modifier kind or operation type drift.")
        if self.modifier.source_id is None:
            raise GameLifecycleError("Attack modifier requires source identity.")
        if self.kind == "hit_roll" and self.modifier.operation.value != "add":
            raise GameLifecycleError("Hit modifier source requires an additive operation.")

    @property
    def modifier_id(self) -> str:
        return f"{self.kind}:{self.modifier.modifier_id}"

    def to_payload(self) -> dict[str, JsonValue]:
        return {"kind": self.kind, "modifier": validate_json_value(self.modifier.to_payload())}

    @classmethod
    def from_payload(cls, value: object) -> AttackModifierSnapshot:
        if not isinstance(value, dict):
            raise GameLifecycleError("Attack modifier snapshot fields drifted.")
        payload = cast(dict[str, object], value)
        if set(payload) != {"kind", "modifier"}:
            raise GameLifecycleError("Attack modifier snapshot fields drifted.")
        raw = payload["modifier"]
        if not isinstance(raw, dict):
            raise GameLifecycleError("Attack modifier operation must be an object.")
        if payload["kind"] == "skill":
            item = cls("skill", Modifier.from_payload(cast(ModifierPayload, raw)))
        elif payload["kind"] == "hit_roll":
            item = cls("hit_roll", RollModifier.from_payload(cast(RollModifierPayload, raw)))
        else:
            raise GameLifecycleError("Attack modifier snapshot kind is invalid.")
        if canonical_json(item.to_payload()) != canonical_json(validate_json_value(payload)):
            raise GameLifecycleError("Attack modifier snapshot is not canonical.")
        return item


@dataclass(frozen=True, slots=True)
class PsychicAttackModifierIgnoreSelection:
    option_id: str
    skill_base: int
    skill_characteristic: Characteristic
    modifiers: tuple[AttackModifierSnapshot, ...]
    decided_modifier_ids: tuple[str, ...]
    ignored_modifier_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.option_id) is not str or not self.option_id.strip():
            raise GameLifecycleError("Psychic selection requires an option identifier.")
        if (
            type(self.decided_modifier_ids) is not tuple
            or type(self.ignored_modifier_ids) is not tuple
        ):
            raise GameLifecycleError("Psychic selection requires identifier tuples.")
        if type(self.skill_base) is not int or self.skill_base < 1:
            raise GameLifecycleError("Psychic modifier base skill is invalid.")
        if self.skill_characteristic not in {
            Characteristic.BALLISTIC_SKILL,
            Characteristic.WEAPON_SKILL,
        }:
            raise GameLifecycleError("Psychic modifier characteristic is invalid.")
        if type(self.modifiers) is not tuple or any(
            type(item) is not AttackModifierSnapshot for item in self.modifiers
        ):
            raise GameLifecycleError("Psychic selection requires typed modifiers.")
        for item in self.modifiers:
            if item.kind == "skill":
                modifier = cast(Modifier, item.modifier)
                if (
                    modifier.scope.characteristics != frozenset({self.skill_characteristic})
                    or modifier.scope.target_ids is not None
                ):
                    raise GameLifecycleError("Psychic skill modifier scope drift.")
        ids = tuple(item.modifier_id for item in self.modifiers)
        if ids != tuple(sorted(set(ids))):
            raise GameLifecycleError("Psychic modifiers must have unique canonical identities.")
        if self.decided_modifier_ids != ids[: len(self.decided_modifier_ids)]:
            raise GameLifecycleError("Psychic selection cursor drift.")
        if self.ignored_modifier_ids != tuple(sorted(set(self.ignored_modifier_ids))):
            raise GameLifecycleError("Psychic ignored modifiers must be unique and canonical.")
        if not set(self.ignored_modifier_ids).issubset(self.decided_modifier_ids):
            raise GameLifecycleError("Psychic ignored modifier is foreign or undecided.")

    @property
    def complete(self) -> bool:
        return len(self.decided_modifier_ids) == len(self.modifiers)

    def skill_value(self, *, ignored_ids: tuple[str, ...]) -> int:
        resolved = ModifierStack(
            self.skill_characteristic,
            self.skill_base,
            tuple(
                cast(Modifier, item.modifier)
                for item in self.modifiers
                if item.kind == "skill" and item.modifier_id not in ignored_ids
            ),
        ).resolve()
        if not resolved.is_numeric:
            raise GameLifecycleError("Psychic skill modifiers require a numeric resolution.")
        return resolved.final

    @property
    def skill_modifier(self) -> int:
        return self.skill_value(ignored_ids=()) - self.skill_base

    @property
    def effective_skill_modifier(self) -> int:
        return self.skill_value(ignored_ids=self.ignored_modifier_ids) - self.skill_base

    @property
    def hit_roll_modifier(self) -> int:
        return sum(item.modifier.operand for item in self.modifiers if item.kind == "hit_roll")

    @property
    def effective_hit_roll_modifier(self) -> int:
        return sum(
            item.modifier.operand
            for item in self.modifiers
            if item.kind == "hit_roll" and item.modifier_id not in self.ignored_modifier_ids
        )

    def to_payload(self) -> dict[str, JsonValue]:
        return {
            "option_id": self.option_id,
            "skill_base": self.skill_base,
            "skill_characteristic": self.skill_characteristic.value,
            "modifiers": [item.to_payload() for item in self.modifiers],
            "decided_modifier_ids": list(self.decided_modifier_ids),
            "ignored_modifier_ids": list(self.ignored_modifier_ids),
            "skill_modifier": self.skill_modifier,
            "hit_roll_modifier": self.hit_roll_modifier,
            "effective_skill_modifier": self.effective_skill_modifier,
            "effective_hit_roll_modifier": self.effective_hit_roll_modifier,
            "ignored_skill_modifier": self.skill_modifier - self.effective_skill_modifier,
            "ignored_hit_roll_modifier": self.hit_roll_modifier - self.effective_hit_roll_modifier,
        }
