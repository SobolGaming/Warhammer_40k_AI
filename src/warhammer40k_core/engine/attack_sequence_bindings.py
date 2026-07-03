# ruff: noqa: I001
# pyright: reportUnusedImport=false
from __future__ import annotations

from types import ModuleType

from warhammer40k_core.engine import (
    attack_sequence_damage_resolution as attack_sequence_damage_resolution,
    attack_sequence_destroyed_transport as attack_sequence_destroyed_transport,
    attack_sequence_dice_rerolls as attack_sequence_dice_rerolls,
    attack_sequence_dispatch as attack_sequence_dispatch,
    attack_sequence_geometry_targets as attack_sequence_geometry_targets,
    attack_sequence_group_selection as attack_sequence_group_selection,
    attack_sequence_grouped_allocation as attack_sequence_grouped_allocation,
    attack_sequence_hazardous as attack_sequence_hazardous,
    attack_sequence_hit_wound as attack_sequence_hit_wound,
    attack_sequence_model as attack_sequence_model,
    attack_sequence_psychic_modifiers as attack_sequence_psychic_modifiers,
    attack_sequence_selection as attack_sequence_selection,
    attack_sequence_state as attack_sequence_state,
    attack_sequence_validation as attack_sequence_validation,
)

_ATTACK_SEQUENCE_MODULES: tuple[ModuleType, ...] = (
    attack_sequence_model,
    attack_sequence_state,
    attack_sequence_dispatch,
    attack_sequence_destroyed_transport,
    attack_sequence_group_selection,
    attack_sequence_grouped_allocation,
    attack_sequence_damage_resolution,
    attack_sequence_dice_rerolls,
    attack_sequence_psychic_modifiers,
    attack_sequence_hit_wound,
    attack_sequence_hazardous,
    attack_sequence_geometry_targets,
    attack_sequence_selection,
    attack_sequence_validation,
)


def bind_attack_sequence_modules() -> None:
    shared_globals: dict[str, object] = {}
    for module in _ATTACK_SEQUENCE_MODULES:
        for name in module.__all__:
            shared_globals[name] = getattr(module, name)
    for module in _ATTACK_SEQUENCE_MODULES:
        module.__dict__.update(shared_globals)
