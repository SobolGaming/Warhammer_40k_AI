# ruff: noqa: I001
# pyright: reportUnusedImport=false
from __future__ import annotations

from types import ModuleType

from warhammer40k_core.engine import (
    stratagems_model as stratagems_model,
    stratagems_requests as stratagems_requests,
    stratagems_apply as stratagems_apply,
    stratagems_selection as stratagems_selection,
    stratagems_eligibility as stratagems_eligibility,
    stratagems_targeting as stratagems_targeting,
    stratagems_geometry as stratagems_geometry,
    stratagems_ingress as stratagems_ingress,
    stratagems_core_handlers as stratagems_core_handlers,
    stratagems_tactical_secondaries as stratagems_tactical_secondaries,
    stratagems_fire_overwatch as stratagems_fire_overwatch,
    stratagems_effect_handlers as stratagems_effect_handlers,
    stratagems_validation as stratagems_validation,
)

_STRATAGEMS_MODULES: tuple[ModuleType, ...] = (
    stratagems_model,
    stratagems_requests,
    stratagems_apply,
    stratagems_selection,
    stratagems_eligibility,
    stratagems_targeting,
    stratagems_geometry,
    stratagems_ingress,
    stratagems_core_handlers,
    stratagems_tactical_secondaries,
    stratagems_fire_overwatch,
    stratagems_effect_handlers,
    stratagems_validation,
)


def bind_stratagems_modules() -> None:
    shared_globals: dict[str, object] = {}
    for module in _STRATAGEMS_MODULES:
        for name in module.__all__:
            shared_globals[name] = getattr(module, name)
    for module in _STRATAGEMS_MODULES:
        module.__dict__.update(shared_globals)
