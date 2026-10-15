from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

import pytest

from warhammer40k_core.engine.faction_content.hooks import (
    RuntimeHookBinding,
    combine_any_hook_bindings,
    hook_bindings_by_event_from_registry_owner,
    hook_bindings_by_event_from_sources,
    hook_bindings_for_event,
    lifecycle_event_for_hook_binding,
    runtime_hook_binding_for,
    validate_any_hook_bindings,
    validate_hook_bindings_by_event,
)
from warhammer40k_core.engine.fall_back_hooks import (
    FallBackEligibilityContext,
    FallBackEligibilityGrant,
    FallBackEligibilityHookBinding,
)
from warhammer40k_core.engine.lifecycle_hooks import (
    HookBinding,
    HookBindingShape,
    LifecycleHookEvent,
)
from warhammer40k_core.engine.phase import GameLifecycleError


@dataclass(frozen=True, slots=True)
class _HookRegistryOwner:
    fall_back_hook_registry: _StubHookRegistry
    ignored_value: str = "not-a-registry"


@dataclass(frozen=True, slots=True)
class _InvalidHookRegistryOwner:
    fall_back_hook_registry: object


class _StubHookRegistry:
    def __init__(self, bindings: tuple[HookBindingShape, ...]) -> None:
        self._bindings = bindings

    def all_bindings(self) -> tuple[HookBindingShape, ...]:
        return self._bindings


def _fall_back_binding(
    hook_id: str,
    *,
    source_id: str = "source-a",
) -> FallBackEligibilityHookBinding:
    return FallBackEligibilityHookBinding(
        hook_id=hook_id,
        source_id=source_id,
        handler=_fall_back_handler,
    )


def _generic_binding(
    hook_id: str,
    *,
    source_id: str = "generic-source",
) -> HookBinding[LifecycleHookEvent, Callable[[], None]]:
    return HookBinding(
        hook_id=hook_id,
        source_id=source_id,
        handler=_generic_handler,
    )


def _fall_back_handler(
    _context: FallBackEligibilityContext,
) -> FallBackEligibilityGrant | None:
    return None


def _generic_handler() -> None:
    return None


__all__: list[str] = []
__all__ += ["Callable", "FallBackEligibilityContext", "FallBackEligibilityGrant"]
__all__ += ["FallBackEligibilityHookBinding", "GameLifecycleError", "HookBinding"]
__all__ += ["HookBindingShape", "LifecycleHookEvent", "RuntimeHookBinding", "_HookRegistryOwner"]
__all__ += ["_InvalidHookRegistryOwner", "_StubHookRegistry", "_fall_back_binding"]
__all__ += ["_fall_back_handler", "_generic_binding", "_generic_handler", "cast"]
__all__ += ["combine_any_hook_bindings", "dataclass"]
__all__ += ["hook_bindings_by_event_from_registry_owner", "hook_bindings_by_event_from_sources"]
__all__ += ["hook_bindings_for_event", "lifecycle_event_for_hook_binding", "pytest"]
__all__ += ["runtime_hook_binding_for", "validate_any_hook_bindings"]
__all__ += ["validate_hook_bindings_by_event"]
