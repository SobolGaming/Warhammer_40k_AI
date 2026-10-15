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


def test_runtime_hook_binding_validation_and_lookup_paths() -> None:
    typed_binding = _fall_back_binding("hook-a", source_id="source-a")
    runtime_binding = RuntimeHookBinding(
        lifecycle_event=LifecycleHookEvent.FALL_BACK_ELIGIBILITY,
        binding=typed_binding,
    )
    generic_binding = _generic_binding("generic-a")
    generic_runtime_binding = RuntimeHookBinding(
        lifecycle_event=LifecycleHookEvent.STRATAGEM_COST_CHOICE,
        binding=generic_binding,
    )

    assert runtime_binding.hook_id == "hook-a"
    assert runtime_binding.source_id == "source-a"
    assert lifecycle_event_for_hook_binding(runtime_binding) is (
        LifecycleHookEvent.FALL_BACK_ELIGIBILITY
    )
    assert lifecycle_event_for_hook_binding(typed_binding) is (
        LifecycleHookEvent.FALL_BACK_ELIGIBILITY
    )
    assert runtime_hook_binding_for(runtime_binding) == runtime_binding
    assert runtime_hook_binding_for(typed_binding) == runtime_binding
    assert hook_bindings_for_event(
        (runtime_binding, generic_runtime_binding),
        LifecycleHookEvent.FALL_BACK_ELIGIBILITY,
        FallBackEligibilityHookBinding,
    ) == (typed_binding,)

    with pytest.raises(GameLifecycleError, match="lifecycle_event is invalid"):
        RuntimeHookBinding(
            lifecycle_event=cast(LifecycleHookEvent, "bad-event"),
            binding=typed_binding,
        )
    with pytest.raises(GameLifecycleError, match="binding is invalid"):
        RuntimeHookBinding(
            lifecycle_event=LifecycleHookEvent.FALL_BACK_ELIGIBILITY,
            binding=cast(HookBindingShape, object()),
        )
    with pytest.raises(GameLifecycleError, match="does not match binding type"):
        RuntimeHookBinding(
            lifecycle_event=LifecycleHookEvent.ADVANCE_MOVE,
            binding=typed_binding,
        )
    with pytest.raises(GameLifecycleError, match="contains invalid values"):
        lifecycle_event_for_hook_binding(object())
    with pytest.raises(GameLifecycleError, match="contains invalid values"):
        runtime_hook_binding_for(object())


def test_any_hook_binding_validation_sorts_and_rejects_invalid_values() -> None:
    fall_back_b = _fall_back_binding("hook-b")
    fall_back_a = _fall_back_binding("hook-a")
    generic_runtime_binding = RuntimeHookBinding(
        lifecycle_event=LifecycleHookEvent.STRATAGEM_COST_CHOICE,
        binding=_generic_binding("generic-a"),
    )

    assert validate_any_hook_bindings((fall_back_b, generic_runtime_binding, fall_back_a)) == (
        RuntimeHookBinding(
            lifecycle_event=LifecycleHookEvent.FALL_BACK_ELIGIBILITY,
            binding=fall_back_a,
        ),
        RuntimeHookBinding(
            lifecycle_event=LifecycleHookEvent.FALL_BACK_ELIGIBILITY,
            binding=fall_back_b,
        ),
        generic_runtime_binding,
    )

    with pytest.raises(GameLifecycleError, match="hook_bindings must be a tuple"):
        validate_any_hook_bindings(cast(tuple[object, ...], []))
    with pytest.raises(GameLifecycleError, match="unique per lifecycle event"):
        validate_any_hook_bindings(
            (
                _fall_back_binding("duplicate-hook", source_id="source-a"),
                _fall_back_binding("duplicate-hook", source_id="source-b"),
            )
        )
    with pytest.raises(GameLifecycleError, match="Stratagem cost choice hook binding IDs"):
        combine_any_hook_bindings(
            (
                RuntimeHookBinding(
                    lifecycle_event=LifecycleHookEvent.STRATAGEM_COST_CHOICE,
                    binding=_generic_binding("duplicate-generic", source_id="source-a"),
                ),
                RuntimeHookBinding(
                    lifecycle_event=LifecycleHookEvent.STRATAGEM_COST_CHOICE,
                    binding=_generic_binding("duplicate-generic", source_id="source-b"),
                ),
            )
        )


def test_hook_bindings_by_event_validation_and_source_combining() -> None:
    typed_binding = _fall_back_binding("hook-a")
    runtime_binding = RuntimeHookBinding(
        lifecycle_event=LifecycleHookEvent.FALL_BACK_ELIGIBILITY,
        binding=typed_binding,
    )
    generic_runtime_binding = RuntimeHookBinding(
        lifecycle_event=LifecycleHookEvent.STRATAGEM_COST_CHOICE,
        binding=_generic_binding("generic-a"),
    )

    by_event = hook_bindings_by_event_from_sources(
        emitted_bindings=(typed_binding,),
        contribution_bindings=(generic_runtime_binding,),
    )
    assert by_event[LifecycleHookEvent.FALL_BACK_ELIGIBILITY] == (runtime_binding,)
    assert by_event[LifecycleHookEvent.STRATAGEM_COST_CHOICE] == (generic_runtime_binding,)
    assert validate_hook_bindings_by_event(by_event) == by_event

    with pytest.raises(GameLifecycleError, match="must be a mapping"):
        validate_hook_bindings_by_event([])
    with pytest.raises(GameLifecycleError, match="contains invalid events"):
        validate_hook_bindings_by_event({"bad-event": (runtime_binding,)})
    with pytest.raises(GameLifecycleError, match="contains mismatched events"):
        validate_hook_bindings_by_event({LifecycleHookEvent.ADVANCE_MOVE: (runtime_binding,)})


def test_registry_owner_binding_projection_accepts_generic_extras_and_rejects_drift() -> None:
    typed_binding = _fall_back_binding("hook-a", source_id="source-a")
    registry_owner = _HookRegistryOwner(
        fall_back_hook_registry=_StubHookRegistry((typed_binding,)),
    )
    runtime_binding = RuntimeHookBinding(
        lifecycle_event=LifecycleHookEvent.FALL_BACK_ELIGIBILITY,
        binding=typed_binding,
    )
    generic_runtime_binding = RuntimeHookBinding(
        lifecycle_event=LifecycleHookEvent.STRATAGEM_COST_CHOICE,
        binding=_generic_binding("generic-a"),
    )

    by_event = hook_bindings_by_event_from_registry_owner(
        owner=registry_owner,
        extra_bindings_by_event={
            LifecycleHookEvent.STRATAGEM_COST_CHOICE: (generic_runtime_binding,)
        },
    )
    assert by_event[LifecycleHookEvent.FALL_BACK_ELIGIBILITY] == (runtime_binding,)
    assert by_event[LifecycleHookEvent.STRATAGEM_COST_CHOICE] == (generic_runtime_binding,)

    with pytest.raises(GameLifecycleError, match="missing from hook registries"):
        hook_bindings_by_event_from_registry_owner(
            owner=registry_owner,
            extra_bindings_by_event={
                LifecycleHookEvent.FALL_BACK_ELIGIBILITY: (
                    RuntimeHookBinding(
                        lifecycle_event=LifecycleHookEvent.FALL_BACK_ELIGIBILITY,
                        binding=_fall_back_binding("missing-hook"),
                    ),
                )
            },
        )
    with pytest.raises(GameLifecycleError, match="does not match hook registry"):
        hook_bindings_by_event_from_registry_owner(
            owner=registry_owner,
            extra_bindings_by_event={
                LifecycleHookEvent.FALL_BACK_ELIGIBILITY: (
                    RuntimeHookBinding(
                        lifecycle_event=LifecycleHookEvent.FALL_BACK_ELIGIBILITY,
                        binding=_fall_back_binding("hook-a", source_id="source-b"),
                    ),
                )
            },
        )
    with pytest.raises(GameLifecycleError, match="owner must be a dataclass"):
        hook_bindings_by_event_from_registry_owner(
            owner=object(),
            extra_bindings_by_event={},
        )
    with pytest.raises(GameLifecycleError, match="fields must expose all_bindings"):
        hook_bindings_by_event_from_registry_owner(
            owner=_InvalidHookRegistryOwner(fall_back_hook_registry=object()),
            extra_bindings_by_event={},
        )


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
