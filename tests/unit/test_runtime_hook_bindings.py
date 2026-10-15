from __future__ import annotations

from typing import cast

from tests.shared.category_migration.runtime_hook_bindings import (
    Callable,
    FallBackEligibilityContext,
    FallBackEligibilityGrant,
    FallBackEligibilityHookBinding,
    GameLifecycleError,
    HookBinding,
    HookBindingShape,
    LifecycleHookEvent,
    RuntimeHookBinding,
    _fall_back_binding,
    _fall_back_handler,
    _generic_binding,
    _generic_handler,
    _HookRegistryOwner,
    _InvalidHookRegistryOwner,
    _StubHookRegistry,
    combine_any_hook_bindings,
    dataclass,
    hook_bindings_by_event_from_registry_owner,
    hook_bindings_by_event_from_sources,
    hook_bindings_for_event,
    lifecycle_event_for_hook_binding,
    pytest,
    runtime_hook_binding_for,
    validate_any_hook_bindings,
    validate_hook_bindings_by_event,
)


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


__all__: list[str] = []
__all__ += ["Callable", "FallBackEligibilityContext", "FallBackEligibilityGrant"]
__all__ += ["FallBackEligibilityHookBinding", "HookBinding", "HookBindingShape"]
__all__ += ["_fall_back_handler", "_generic_handler", "cast", "combine_any_hook_bindings"]
__all__ += ["dataclass", "hook_bindings_by_event_from_sources", "hook_bindings_for_event"]
__all__ += ["lifecycle_event_for_hook_binding", "runtime_hook_binding_for"]
__all__ += ["validate_any_hook_bindings", "validate_hook_bindings_by_event"]
