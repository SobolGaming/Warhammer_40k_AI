"""Recorded subset choices at explicit engine-owned modifier evaluation boundaries.

The caller owns the continuation and supplies an unfiltered inventory. Queries
and adapters never call this mutating preparation service.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.modifiers import (
    Modifier,
    ModifierPayload,
    RollModifier,
    RollModifierPayload,
)
from warhammer40k_core.engine.catalog_modifier_ignore import (
    ModifierIgnoreKind,
    modifier_ignore_permissions_for_subject,
)
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.modifier_permission_context import ModifierPermissionAttackContext
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus

if TYPE_CHECKING:
    from warhammer40k_core.engine.abilities import AbilityCatalogIndex
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.decision_record import DecisionRecord
    from warhammer40k_core.engine.game_state import GameState

SELECT_MODIFIER_IGNORES_DECISION_TYPE = "select_modifier_ignores"


@dataclass(frozen=True, slots=True)
class ModifierEvaluationSubject:
    unit_instance_id: str
    kind: ModifierIgnoreKind
    model_instance_id: str | None = None
    weapon_profile_id: str | None = None

    def __post_init__(self) -> None:
        _identifier(self.unit_instance_id)
        if type(self.kind) is not ModifierIgnoreKind:
            raise GameLifecycleError("Modifier evaluation requires a typed kind.")
        if self.model_instance_id is not None:
            _identifier(self.model_instance_id)
        if self.weapon_profile_id is not None:
            _identifier(self.weapon_profile_id)
            if self.model_instance_id is None:
                raise GameLifecycleError("Weapon modifier evaluation requires its model owner.")

    def to_payload(self) -> dict[str, JsonValue]:
        return {
            "unit_instance_id": self.unit_instance_id,
            "kind": self.kind.value,
            "model_instance_id": self.model_instance_id,
            "weapon_profile_id": self.weapon_profile_id,
        }

    @classmethod
    def from_payload(cls, payload: object) -> ModifierEvaluationSubject:
        if not isinstance(payload, dict) or set(cast(dict[str, object], payload)) != {
            "unit_instance_id",
            "kind",
            "model_instance_id",
            "weapon_profile_id",
        }:
            raise GameLifecycleError("Modifier evaluation subject fields drifted.")
        row = cast(dict[str, object], payload)
        return cls(
            unit_instance_id=_identifier(row["unit_instance_id"]),
            kind=ModifierIgnoreKind(_identifier(row["kind"])),
            model_instance_id=None
            if row["model_instance_id"] is None
            else _identifier(row["model_instance_id"]),
            weapon_profile_id=None
            if row["weapon_profile_id"] is None
            else _identifier(row["weapon_profile_id"]),
        )


@dataclass(frozen=True, slots=True)
class ModifierEvaluationResult[T: Modifier | RollModifier]:
    modifiers: tuple[T, ...]
    ignored_modifier_ids: tuple[str, ...] = ()
    pending_status: LifecycleStatus | None = None


def select_modifiers[T: Modifier | RollModifier](
    *,
    state: GameState,
    decisions: DecisionController,
    ability_index: AbilityCatalogIndex,
    occurrence_id: str,
    subject: ModifierEvaluationSubject,
    modifiers: tuple[T, ...],
    source_context: dict[str, JsonValue],
    attack_context: ModifierPermissionAttackContext | None = None,
) -> ModifierEvaluationResult[T]:
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    _identifier(occurrence_id)
    inventory = modifier_inventory_payload(modifiers)
    previous = selection_history(
        decision_records=decisions.records,
        occurrence_id=occurrence_id,
        subject=subject,
    )
    if not modifiers and previous is None:
        return ModifierEvaluationResult(modifiers)
    if "permission_attack_context" in source_context:
        raise GameLifecycleError("Modifier permission attack context is owned by its evaluator.")
    if (source_context.get("continuation") == "attack") != (attack_context is not None):
        raise GameLifecycleError("Attack modifier evaluation requires its occurrence context.")
    permissions = modifier_ignore_permissions_for_subject(
        state=state,
        ability_index=ability_index,
        unit_instance_id=subject.unit_instance_id,
        kind=subject.kind,
        model_instance_id=subject.model_instance_id,
        weapon_profile_id=subject.weapon_profile_id,
        attack_context=attack_context,
    )
    if not permissions and previous is None:
        return ModifierEvaluationResult(modifiers)
    if attack_context is not None:
        source_context = {
            **source_context,
            "permission_attack_context": attack_context.to_payload(),
        }
    context = _object(
        validate_json_value(
            {
                "occurrence_id": occurrence_id,
                "subject": subject.to_payload(),
                "modifiers": inventory,
                "permissions": [permission.to_payload() for permission in permissions],
                "source_context": source_context,
            }
        )
    )
    if previous is not None:
        if _evaluation_context(previous) != context:
            raise GameLifecycleError("Modifier evaluation source inventory or permission drift.")
        decided = _ids(previous["decided_modifier_ids"])
        ignored = _ids(previous["ignored_modifier_ids"])
        if len(decided) == len(modifiers):
            return ModifierEvaluationResult(
                tuple(item for item in modifiers if item.modifier_id not in ignored), ignored
            )
    else:
        decided, ignored = (), ()
    if not modifiers or not permissions:
        if previous is not None:
            raise GameLifecycleError("Modifier evaluation permission disappeared during selection.")
        return ModifierEvaluationResult(modifiers)
    owner = rules_unit_view_by_id(state=state, unit_instance_id=subject.unit_instance_id)
    payload: dict[str, JsonValue] = {
        **context,
        "decided_modifier_ids": list(decided),
        "ignored_modifier_ids": list(ignored),
    }
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_MODIFIER_IGNORES_DECISION_TYPE,
        actor_id=owner.owner_player_id,
        payload=payload,
        options=modifier_evaluation_options(payload),
    )
    decisions.request_decision(request)
    return ModifierEvaluationResult(
        modifiers,
        ignored,
        LifecycleStatus.waiting_for_decision(stage=state.stage, decision_request=request),
    )


def modifier_inventory_payload(
    modifiers: tuple[Modifier | RollModifier, ...],
) -> list[JsonValue]:
    if type(modifiers) is not tuple or any(
        type(item) not in {Modifier, RollModifier} for item in modifiers
    ):
        raise GameLifecycleError("Modifier evaluation requires typed source operations.")
    if len({item.modifier_id for item in modifiers}) != len(modifiers):
        raise GameLifecycleError("Modifier evaluation source identities are duplicated.")
    return [
        validate_json_value(
            {
                "operation_type": "characteristic" if type(item) is Modifier else "roll",
                "operation": item.to_payload(),
            }
        )
        for item in modifiers
    ]


def modifier_evaluation_options(payload: dict[str, JsonValue]) -> tuple[DecisionOption, ...]:
    _validate_selection_payload(payload)
    inventory = _inventory_ids(payload)
    decided = _ids(payload["decided_modifier_ids"])
    ignored = _ids(payload["ignored_modifier_ids"])
    if len(decided) == len(inventory):
        raise GameLifecycleError("Modifier evaluation has no remaining choice.")
    current = inventory[len(decided)]
    suffix = sha256(current.encode()).hexdigest()[:20]
    candidates = (
        ("keep-remaining", "Keep all remaining modifiers", inventory, ignored),
        (
            "ignore-remaining",
            "Ignore all remaining modifiers",
            inventory,
            (*ignored, *inventory[len(decided) :]),
        ),
        (f"keep:{suffix}", f"Keep {current}", (*decided, current), ignored),
        (f"ignore:{suffix}", f"Ignore {current}", (*decided, current), (*ignored, current)),
    )
    options: list[DecisionOption] = []
    seen: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
    for option_id, label, next_decided, next_ignored in candidates:
        identity = next_decided, tuple(sorted(next_ignored))
        if identity in seen:
            continue
        seen.add(identity)
        options.append(
            DecisionOption(
                option_id=option_id,
                label=label,
                payload={
                    **payload,
                    "decided_modifier_ids": list(identity[0]),
                    "ignored_modifier_ids": list(identity[1]),
                },
            )
        )
    return tuple(sorted(options, key=lambda option: option.option_id))


def selection_history(
    *,
    decision_records: tuple[DecisionRecord, ...],
    occurrence_id: str,
    subject: ModifierEvaluationSubject,
) -> dict[str, JsonValue] | None:
    previous: dict[str, JsonValue] | None = None
    actor_id: str | None = None
    for record in decision_records:
        if record.request.decision_type != SELECT_MODIFIER_IGNORES_DECISION_TYPE:
            continue
        pending = _object(record.request.payload)
        if (
            pending.get("occurrence_id") != occurrence_id
            or pending.get("subject") != subject.to_payload()
        ):
            continue
        _validate_selection_payload(pending)
        if previous is None:
            if pending["decided_modifier_ids"] or pending["ignored_modifier_ids"]:
                raise GameLifecycleError(
                    "Modifier selection history starts after its source cursor."
                )
        elif pending != previous or actor_id != record.request.actor_id:
            raise GameLifecycleError("Modifier selection history cursor, actor or source drift.")
        expected_options = modifier_evaluation_options(pending)
        if record.request.options != expected_options:
            raise GameLifecycleError(
                "Modifier selection recorded options differ from their inventory."
            )
        record.result.validate_for_request(record.request)
        previous = _object(record.result.payload)
        actor_id = record.request.actor_id
    return previous


def selected_modifiers_for_occurrence[T: Modifier | RollModifier](
    *,
    decision_records: tuple[DecisionRecord, ...],
    occurrence_id: str,
    subject: ModifierEvaluationSubject,
    modifiers: tuple[T, ...],
) -> tuple[T, ...]:
    selected = selection_history(
        decision_records=decision_records, occurrence_id=occurrence_id, subject=subject
    )
    if selected is None:
        return modifiers
    if selected["modifiers"] != modifier_inventory_payload(modifiers) or len(
        _ids(selected["decided_modifier_ids"])
    ) != len(modifiers):
        raise GameLifecycleError("Historical modifier evaluation inventory or completion drift.")
    ignored = _ids(selected["ignored_modifier_ids"])
    return tuple(item for item in modifiers if item.modifier_id not in ignored)


def _evaluation_context(payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {
        key: payload[key]
        for key in ("occurrence_id", "subject", "modifiers", "permissions", "source_context")
    }


def _validate_selection_payload(payload: dict[str, JsonValue]) -> None:
    if set(payload) != {
        "occurrence_id",
        "subject",
        "modifiers",
        "permissions",
        "source_context",
        "decided_modifier_ids",
        "ignored_modifier_ids",
    }:
        raise GameLifecycleError("Modifier evaluation payload fields drifted.")
    _identifier(payload["occurrence_id"])
    ModifierEvaluationSubject.from_payload(payload["subject"])
    permission_attack_context_from_source(_object(payload["source_context"]))
    inventory = _inventory_ids(payload)
    if not inventory or len(set(inventory)) != len(inventory):
        raise GameLifecycleError("Modifier evaluation inventory is empty or duplicated.")
    permissions = payload["permissions"]
    if (
        not isinstance(permissions, list)
        or not permissions
        or any(not isinstance(item, dict) for item in permissions)
    ):
        raise GameLifecycleError("Modifier evaluation requires source permission evidence.")
    decided = _ids(payload["decided_modifier_ids"])
    ignored = _ids(payload["ignored_modifier_ids"])
    if decided != inventory[: len(decided)] or not set(ignored).issubset(decided):
        raise GameLifecycleError("Modifier evaluation subset or cursor drift.")


def permission_attack_context_from_source(
    source_context: dict[str, JsonValue],
) -> ModifierPermissionAttackContext | None:
    if source_context.get("continuation") == "attack":
        return ModifierPermissionAttackContext.from_payload(
            source_context.get("permission_attack_context")
        )
    if "permission_attack_context" in source_context:
        raise GameLifecycleError(
            "Non-attack modifier occurrence contains attack permission context."
        )
    return None


def _inventory_ids(payload: dict[str, JsonValue]) -> tuple[str, ...]:
    raw = payload["modifiers"]
    if not isinstance(raw, list):
        raise GameLifecycleError("Modifier evaluation inventory must be a list.")
    ids: list[str] = []
    for entry in raw:
        row = _object(entry)
        if set(row) != {"operation_type", "operation"} or row["operation_type"] not in {
            "characteristic",
            "roll",
        }:
            raise GameLifecycleError("Modifier evaluation operation kind or fields drifted.")
        operation = _object(row["operation"])
        parsed: Modifier | RollModifier
        parsed = (
            Modifier.from_payload(cast(ModifierPayload, operation))
            if row["operation_type"] == "characteristic"
            else RollModifier.from_payload(cast(RollModifierPayload, operation))
        )
        if parsed.source_id is None or validate_json_value(parsed.to_payload()) != operation:
            raise GameLifecycleError("Modifier evaluation source operation evidence drifted.")
        subject = ModifierEvaluationSubject.from_payload(payload["subject"])
        if subject.kind.value.endswith("_characteristic"):
            if (
                not isinstance(parsed, Modifier)
                or parsed.scope.characteristics is None
                or (
                    {item.value for item in parsed.scope.characteristics}
                    != {subject.kind.value.removesuffix("_characteristic")}
                )
            ):
                raise GameLifecycleError("Modifier evaluation characteristic scope drifted.")
        elif not isinstance(parsed, RollModifier):
            raise GameLifecycleError("Modifier evaluation roll scope drifted.")
        ids.append(parsed.modifier_id)
    return tuple(ids)


def _ids(value: JsonValue) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise GameLifecycleError("Modifier evaluation IDs must be a list.")
    identifiers = tuple(_identifier(item) for item in value)
    if len(set(identifiers)) != len(identifiers):
        raise GameLifecycleError("Modifier evaluation IDs are duplicated.")
    return identifiers


def _object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Modifier evaluation payload must be an object.")
    return value


def _identifier(value: object) -> str:
    if type(value) is not str or not value.strip():
        raise GameLifecycleError("Modifier evaluation requires a nonempty identifier.")
    return value
