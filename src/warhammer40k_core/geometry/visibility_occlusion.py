"""Shared source-group attribution for terrain-caused incomplete visibility.

Owner ruling COV32-01 accepts an independently sufficient terrain cause. Joint
causes additionally require the SAME target part to become visible when that
source group is removed; unrelated hidden parts do not invalidate the cause.
"""

from __future__ import annotations

from functools import lru_cache

from warhammer40k_core.geometry.continuous_visibility import resolve_visibility_pair
from warhammer40k_core.geometry.visibility_certificates import full_visibility_by_observer_caps
from warhammer40k_core.geometry.visibility_exact import VisibilityPrism
from warhammer40k_core.geometry.visibility_formulas import (
    ModelDomain,
    decide_same_part_counterfactual,
    decide_target_part_visible,
)
from warhammer40k_core.geometry.visibility_witnesses import (
    point_has_self_visible_origin,
    self_visible_corridors_blocked,
    target_part_candidates,
)


@lru_cache(maxsize=4096)
def source_group_obscures(
    observer: VisibilityPrism,
    target: VisibilityPrism,
    selected: tuple[VisibilityPrism, ...],
    remaining: tuple[VisibilityPrism, ...],
) -> bool:
    if not selected:
        return False
    alone = resolve_visibility_pair(observer, target, selected, selected)
    if not alone.model_fully_visible:
        return True
    if not remaining:
        return False
    if all(
        blocker.lower <= min(observer.lower, target.lower)
        and blocker.upper >= max(observer.upper, target.upper)
        for blocker in remaining
    ) and full_visibility_by_observer_caps(observer, target, selected):
        # The cap proof preserves the XY position of every self-valid origin.
        # Remaining full-height blockers depend only on the XY strip, so moving
        # any remaining-clear origin to that cap also avoids selected terrain.
        # Consequently no SAME target part can be jointly hidden by selected.
        return False
    blockers = (*selected, *remaining)
    combined = resolve_visibility_pair(observer, target, blockers, blockers)
    if combined.model_fully_visible:
        return False
    origin, destination = ModelDomain.from_prism(observer), ModelDomain.from_prism(target)
    candidates = (
        (combined.hidden_target_part,)
        if combined.hidden_target_part is not None
        else target_part_candidates(origin, destination, blockers)
    )
    for point in candidates:
        if not point_has_self_visible_origin(origin, destination, point):
            continue
        hidden = (
            not combined.model_visible
            or point == combined.hidden_target_part
            or self_visible_corridors_blocked(observer, destination, point, blockers)
        )
        if hidden and decide_target_part_visible(origin, destination, point, remaining):
            return True
    return decide_same_part_counterfactual(origin, destination, blockers, remaining)
