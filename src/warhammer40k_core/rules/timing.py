from __future__ import annotations

from warhammer40k_core.core.modifiers import ModifierTiming

__all__ = ["ModifierTiming", "ordered_modifier_timings"]


def ordered_modifier_timings() -> tuple[ModifierTiming, ...]:
    return ModifierTiming.ordered()
