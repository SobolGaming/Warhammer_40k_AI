from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError


class _HealingStepLike(Protocol):
    @property
    def step_kind(self) -> object: ...

    @property
    def model_instance_id(self) -> str | None: ...


class _HealingModelLike(Protocol):
    @property
    def model_instance_id(self) -> str: ...

    @property
    def is_alive(self) -> bool: ...

    @property
    def wounds_remaining(self) -> int: ...

    @property
    def starting_wounds(self) -> int: ...


def selected_wounded_healing_model_ids(
    source_context: JsonValue,
    resolved_steps: Iterable[_HealingStepLike],
    heal_wound_step_kind: object,
    models: Iterable[_HealingModelLike],
    allows_multiple_wounded_models: bool,
) -> tuple[str, ...]:
    if healing_source_context_bool(source_context, "revive_destroyed_models_only"):
        return ()
    locked_model_id = _locked_healing_model_id(
        source_context=source_context,
        resolved_steps=resolved_steps,
        heal_wound_step_kind=heal_wound_step_kind,
    )
    wounded_model_ids = tuple(
        sorted(
            model.model_instance_id
            for model in models
            if model.is_alive
            and model.wounds_remaining < model.starting_wounds
            and (locked_model_id is None or model.model_instance_id == locked_model_id)
        )
    )
    if len(wounded_model_ids) > 1 and not allows_multiple_wounded_models:
        raise GameLifecycleError(
            "Multiple wounded models require an attached-unit healing decision."
        )
    return wounded_model_ids


def healing_source_context_bool(source_context: JsonValue, key: str) -> bool:
    if not isinstance(source_context, dict):
        return False
    value = source_context.get(key)
    if value is None:
        return False
    if type(value) is not bool:
        raise GameLifecycleError("Healing source-context flag must be a bool.")
    return value


def healing_source_context_identifier_tuple(
    source_context: JsonValue,
    key: str,
) -> tuple[str, ...] | None:
    if not isinstance(source_context, dict):
        return None
    value = source_context.get(key)
    if value is None:
        return None
    if not isinstance(value, list):
        raise GameLifecycleError("Healing source-context identifier collection must be a list.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for item in value:
        if type(item) is not str or not item.strip() or item != item.strip():
            raise GameLifecycleError(
                "Healing source-context identifier collection contains an invalid identifier."
            )
        if item in seen:
            raise GameLifecycleError(
                "Healing source-context identifier collection contains duplicates."
            )
        identifiers.append(item)
        seen.add(item)
    return tuple(identifiers)


def revival_wounds_remaining(source_context: JsonValue, starting_wounds: int) -> int:
    if healing_source_context_bool(source_context, "revive_model_full_health"):
        return starting_wounds
    return 1


def _locked_healing_model_id(
    *,
    source_context: JsonValue,
    resolved_steps: Iterable[_HealingStepLike],
    heal_wound_step_kind: object,
) -> str | None:
    if not healing_source_context_bool(source_context, "single_model_heal"):
        return None
    for step in resolved_steps:
        if step.step_kind == heal_wound_step_kind and step.model_instance_id is not None:
            return step.model_instance_id
    return None
