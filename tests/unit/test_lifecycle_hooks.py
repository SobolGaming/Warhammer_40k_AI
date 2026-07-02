import json
from collections.abc import Callable
from typing import cast

import pytest

from warhammer40k_core.engine.lifecycle_hooks import (
    HookBinding,
    HookRegistry,
    LifecycleHookEvent,
    validate_hook_bindings,
)
from warhammer40k_core.engine.phase import GameLifecycleError

type TestHookHandler = Callable[[str], str]


def test_hook_registry_sorts_bindings_and_serializes_payload() -> None:
    binding_b: HookBinding[LifecycleHookEvent, TestHookHandler] = HookBinding(
        hook_id="hook-b",
        source_id="source-b",
        handler=_handler_b,
    )
    binding_a: HookBinding[LifecycleHookEvent, TestHookHandler] = HookBinding(
        hook_id="hook-a",
        source_id="source-a",
        handler=_handler_a,
    )
    registry: HookRegistry[LifecycleHookEvent, HookBinding[LifecycleHookEvent, TestHookHandler]] = (
        HookRegistry[
            LifecycleHookEvent, HookBinding[LifecycleHookEvent, TestHookHandler]
        ].from_bindings(
            LifecycleHookEvent.ADVANCE_MOVE,
            HookBinding,
            (binding_b, binding_a),
        )
    )

    assert [binding.hook_id for binding in registry.all_bindings()] == ["hook-a", "hook-b"]
    assert registry.binding_for_hook_id("hook-a") == registry.all_bindings()[0]
    assert registry.binding_for_hook_id("missing-hook") is None
    assert registry.to_payload() == {
        "lifecycle_event": "advance_move",
        "bindings": [
            {"hook_id": "hook-a", "source_id": "source-a"},
            {"hook_id": "hook-b", "source_id": "source-b"},
        ],
    }
    assert "object at 0x" not in json.dumps(registry.to_payload(), sort_keys=True)


def test_hook_registry_rejects_duplicates_and_invalid_shapes() -> None:
    valid_binding: HookBinding[LifecycleHookEvent, TestHookHandler] = HookBinding(
        hook_id="hook-a",
        source_id="source-a",
        handler=_handler_a,
    )
    duplicate_binding: HookBinding[LifecycleHookEvent, TestHookHandler] = HookBinding(
        hook_id="hook-a",
        source_id="source-b",
        handler=_handler_b,
    )

    with pytest.raises(GameLifecycleError, match=r"lifecycle_event must be LifecycleHookEvent"):
        HookRegistry[LifecycleHookEvent, HookBinding[LifecycleHookEvent, TestHookHandler]](
            lifecycle_event=cast(LifecycleHookEvent, "advance_move"),
            binding_type=HookBinding,
            bindings=(),
        )
    with pytest.raises(GameLifecycleError, match=r"bindings must be a tuple"):
        HookRegistry[
            LifecycleHookEvent, HookBinding[LifecycleHookEvent, TestHookHandler]
        ].from_bindings(
            LifecycleHookEvent.ADVANCE_MOVE,
            HookBinding,
            cast(tuple[HookBinding[LifecycleHookEvent, TestHookHandler], ...], []),
        )
    with pytest.raises(GameLifecycleError, match=r"must contain HookBinding values"):
        HookRegistry[
            LifecycleHookEvent, HookBinding[LifecycleHookEvent, TestHookHandler]
        ].from_bindings(
            LifecycleHookEvent.ADVANCE_MOVE,
            HookBinding,
            cast(tuple[HookBinding[LifecycleHookEvent, TestHookHandler], ...], (object(),)),
        )
    with pytest.raises(GameLifecycleError, match=r"hook IDs must be unique"):
        HookRegistry[
            LifecycleHookEvent, HookBinding[LifecycleHookEvent, TestHookHandler]
        ].from_bindings(
            LifecycleHookEvent.ADVANCE_MOVE,
            HookBinding,
            (
                valid_binding,
                duplicate_binding,
            ),
        )


def test_validate_hook_bindings_uses_custom_registry_messages() -> None:
    binding_b: HookBinding[LifecycleHookEvent, TestHookHandler] = HookBinding(
        hook_id="hook-b",
        source_id="source-b",
        handler=_handler_b,
    )
    binding_a: HookBinding[LifecycleHookEvent, TestHookHandler] = HookBinding(
        hook_id="hook-a",
        source_id="source-a",
        handler=_handler_a,
    )

    assert validate_hook_bindings(
        (binding_b, binding_a),
        lifecycle_event=LifecycleHookEvent.SHOOTING_PHASE_START,
        binding_type=HookBinding,
        registry_name="TestHookRegistry",
        invalid_binding_message="TestHookRegistry requires hook bindings.",
    ) == (binding_a, binding_b)

    with pytest.raises(GameLifecycleError, match=r"requires hook bindings"):
        validate_hook_bindings(
            (object(),),
            lifecycle_event=LifecycleHookEvent.SHOOTING_PHASE_START,
            binding_type=HookBinding,
            registry_name="TestHookRegistry",
            invalid_binding_message="TestHookRegistry requires hook bindings.",
        )


def test_hook_binding_rejects_invalid_values() -> None:
    with pytest.raises(GameLifecycleError, match=r"hook_id must not be empty"):
        HookBinding(
            hook_id=" ",
            source_id="source-a",
            handler=_handler_a,
        )
    with pytest.raises(GameLifecycleError, match=r"source_id must be a string"):
        HookBinding(
            hook_id="hook-a",
            source_id=cast(str, object()),
            handler=_handler_a,
        )
    with pytest.raises(GameLifecycleError, match=r"handler must be callable"):
        HookBinding(
            hook_id="hook-a",
            source_id="source-a",
            handler=cast(TestHookHandler, object()),
        )


def _handler_a(value: str) -> str:
    return f"a:{value}"


def _handler_b(value: str) -> str:
    return f"b:{value}"
