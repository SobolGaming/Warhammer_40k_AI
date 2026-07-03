# ruff: noqa: I001
# pyright: reportUnusedImport=false
from __future__ import annotations

from types import ModuleType

from warhammer40k_core.engine.phases import (
    movement_model as movement_model,
    movement_state as movement_state,
    movement_handler as movement_handler,
    movement_reactions as movement_reactions,
    movement_reinforcements as movement_reinforcements,
    movement_transports as movement_transports,
    movement_placement_proposals as movement_placement_proposals,
    movement_action_decisions as movement_action_decisions,
    movement_resolution_flow as movement_resolution_flow,
    movement_fall_back_embark as movement_fall_back_embark,
    movement_options_dice as movement_options_dice,
    movement_resolvers as movement_resolvers,
    movement_geometry as movement_geometry,
    movement_validation as movement_validation,
)

_MOVEMENT_MODULES: tuple[ModuleType, ...] = (
    movement_model,
    movement_state,
    movement_handler,
    movement_reactions,
    movement_reinforcements,
    movement_transports,
    movement_placement_proposals,
    movement_action_decisions,
    movement_resolution_flow,
    movement_fall_back_embark,
    movement_options_dice,
    movement_resolvers,
    movement_geometry,
    movement_validation,
)


def bind_movement_modules() -> None:
    shared_globals: dict[str, object] = {}
    for module in _MOVEMENT_MODULES:
        for name in module.__all__:
            shared_globals[name] = getattr(module, name)
    for module in _MOVEMENT_MODULES:
        module.__dict__.update(shared_globals)
