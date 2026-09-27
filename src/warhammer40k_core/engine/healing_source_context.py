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
    def current_wounds(self) -> int: ...

    @property
    def initial_wounds(self) -> int: ...


def selected_wounded_healing_model_ids(
    source_context: JsonValue,
    resolved_steps: Iterable[_HealingStepLike],
    heal_wound_step_kind: object,
    models: Iterable[_HealingModelLike],
) -> tuple[str, ...]:
    if healing_source_context_bool(source_context, "revive_destroyed_models_only"):
        return ()
    locked_model_id = _locked_healing_model_id(
        source_context=source_context,
        resolved_steps=resolved_steps,
        heal_wound_step_kind=heal_wound_step_kind,
    )
    return tuple(
        sorted(
            model.model_instance_id
            for model in models
            if model.is_alive
            and model.current_wounds < model.initial_wounds
            and (locked_model_id is None or model.model_instance_id == locked_model_id)
        )
    )


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
    model_id = healing_model_instance_id(source_context)
    if model_id is not None:
        return model_id
    if not healing_source_context_bool(source_context, "single_model_heal"):
        return None
    for step in resolved_steps:
        if step.step_kind == heal_wound_step_kind and step.model_instance_id is not None:
            return step.model_instance_id
    return None


def healing_model_instance_id(source_context: JsonValue) -> str | None:
    if not isinstance(source_context, dict) or "healing_model_instance_id" not in source_context:
        return None
    value = source_context["healing_model_instance_id"]
    if type(value) is not str or not value or value != value.strip():
        raise GameLifecycleError("Healing model identity must be a non-empty identifier.")
    return value


def healing_is_model_scoped(source_context: JsonValue) -> bool:
    model_id = healing_model_instance_id(source_context)
    single_model = healing_source_context_bool(source_context, "single_model_heal")
    wounded_only = healing_source_context_bool(source_context, "heal_wounded_models_only")
    return model_id is not None or single_model or wounded_only


def validate_healing_source_scope(source_context: JsonValue) -> None:
    model_scoped = healing_is_model_scoped(source_context)
    revive_only = healing_source_context_bool(source_context, "revive_destroyed_models_only")
    if model_scoped and revive_only:
        raise GameLifecycleError("Model healing cannot also request explicit revival.")
    if healing_source_context_bool(source_context, "revive_model_full_health") and not revive_only:
        raise GameLifecycleError("Full-health revival requires explicit revival scope.")
