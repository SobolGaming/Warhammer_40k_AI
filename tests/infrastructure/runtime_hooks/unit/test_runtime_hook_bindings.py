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


__all__: list[str] = []
__all__ += ["Callable", "FallBackEligibilityContext", "FallBackEligibilityGrant", "HookBinding"]
__all__ += ["_HookRegistryOwner", "_InvalidHookRegistryOwner", "_StubHookRegistry"]
__all__ += ["_fall_back_handler", "_generic_handler", "dataclass"]
__all__ += ["hook_bindings_by_event_from_registry_owner"]
