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


def _handler_a(value: str) -> str:
    return f"a:{value}"


def _handler_b(value: str) -> str:
    return f"b:{value}"


__all__: list[str] = []
__all__ += ["Callable", "GameLifecycleError", "HookBinding", "HookRegistry", "LifecycleHookEvent"]
__all__ += ["TestHookHandler", "_handler_a", "_handler_b", "cast", "json", "pytest"]
__all__ += ["validate_hook_bindings"]
