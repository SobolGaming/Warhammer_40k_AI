# ruff: noqa: I001
# pyright: reportUnusedImport=false
from __future__ import annotations

from types import ModuleType

from warhammer40k_core.engine.phases import (
    shooting_model as shooting_model,
    shooting_handler as shooting_handler,
    shooting_reactions as shooting_reactions,
    shooting_requests as shooting_requests,
    shooting_unit_selection as shooting_unit_selection,
    shooting_decisions as shooting_decisions,
    shooting_declaration_validation as shooting_declaration_validation,
    shooting_targeting as shooting_targeting,
    shooting_firing_deck as shooting_firing_deck,
    shooting_eligibility as shooting_eligibility,
    shooting_validation as shooting_validation,
)

_SHOOTING_MODULES: tuple[ModuleType, ...] = (
    shooting_model,
    shooting_handler,
    shooting_reactions,
    shooting_requests,
    shooting_unit_selection,
    shooting_decisions,
    shooting_declaration_validation,
    shooting_targeting,
    shooting_firing_deck,
    shooting_eligibility,
    shooting_validation,
)


def bind_shooting_modules() -> None:
    shared_globals: dict[str, object] = {}
    for module in _SHOOTING_MODULES:
        for name in module.__all__:
            shared_globals[name] = getattr(module, name)
    for module in _SHOOTING_MODULES:
        module.__dict__.update(shared_globals)
