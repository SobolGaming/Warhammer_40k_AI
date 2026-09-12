"""Shared strict identity validation for typed runtime modifier and ability bindings."""

from typing import Protocol, cast

from warhammer40k_core.engine.phase import GameLifecycleError


class RuntimeBindingIdentity(Protocol):
    @property
    def modifier_id(self) -> str: ...


def validate_bindings[T: RuntimeBindingIdentity](
    field_name: str, value: object, binding_type: type[T]
) -> tuple[T, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    bindings: list[T] = []
    seen: set[str] = set()
    for binding in cast(tuple[object, ...], value):
        if type(binding) is not binding_type:
            raise GameLifecycleError(f"{field_name} must contain {binding_type.__name__}.")
        if binding.modifier_id in seen:
            raise GameLifecycleError(f"{field_name} modifier IDs must be unique.")
        seen.add(binding.modifier_id)
        bindings.append(binding)
    return tuple(sorted(bindings, key=lambda binding: binding.modifier_id))
