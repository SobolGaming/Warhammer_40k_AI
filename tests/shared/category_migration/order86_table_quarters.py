# pyright: reportPrivateUsage=false
"""Core 01.04.05: one-millimetre dividers and complete rules-unit occupancy."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from math import hypot, inf, nextafter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

import pytest

from warhammer40k_core.engine.table_quarters import scoring_table_quarter_id_or_none
from warhammer40k_core.geometry.base import BaseShape, CircularBase, OvalBase, RectangularBase
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model, ModelVolume


def _exact_rectangle_contact_facing() -> float:
    """Select a non-cardinal fixture from this runtime's exact rotation coefficients."""
    from warhammer40k_core.geometry.visibility_shapes import rational_rotation

    for degrees in range(1, 90):
        cosine, sine = rational_rotation(float(degrees))
        support = cosine + sine
        # Prove every derived float, not just the radius: multiplying a
        # representable support by three or adding the half-divider can round.
        coordinates = (support, 3 * support, 4 * support + Fraction(1, 8))
        if all(Fraction(float(value)) == value for value in coordinates):
            return float(degrees)
    raise AssertionError("No exactly representable non-cardinal rectangle contact fixture.")


def _analytic_quarter_oracle(
    model: Model, center_x: float, center_y: float, width: float
) -> str | None:
    """Independent oracle using the existing exact polygon/ellipse construction."""
    from warhammer40k_core.geometry.visibility_exact import RationalEllipse
    from warhammer40k_core.geometry.visibility_shapes import model_visibility_prism

    cx, cy, half = Fraction(center_x), Fraction(center_y), Fraction(width) / 2
    footprint = model_visibility_prism(model).footprint
    for name, left, bottom, right, top in (
        ("north-west", Fraction(0), cy + half, cx - half, 2 * cy),
        ("north-east", cx + half, cy + half, 2 * cx, 2 * cy),
        ("south-west", Fraction(0), Fraction(0), cx - half, cy - half),
        ("south-east", cx + half, Fraction(0), 2 * cx, cy - half),
    ):
        if isinstance(footprint, RationalEllipse):
            contained = True
            for axis, lower, upper in ((0, left, right), (1, bottom, top)):
                support_square = footprint.first_axis[axis] ** 2 + footprint.second_axis[axis] ** 2
                for margin in (footprint.center[axis] - lower, upper - footprint.center[axis]):
                    contained = contained and margin >= 0 and support_square <= margin**2
        else:
            contained = all(left <= x <= right and bottom <= y <= top for x, y in footprint)
        if contained:
            return f"table-quarter:{name}"
    return None


def _assert_forged_quarter_witnesses_rejected(state: GameState, player: str) -> None:
    from warhammer40k_core.core.descriptor_hash import canonical_payload_sha256
    from warhammer40k_core.engine.phase import GameLifecycleError
    from warhammer40k_core.engine.primary_scoring_commit_checkpoint_authority import (
        validate_primary_scoring_spatial_rows_from_checkpoint,
    )
    from warhammer40k_core.engine.primary_scoring_state_evidence import PrimaryScoringStateEvidence
    from warhammer40k_core.engine.secondary_scoring_state_evidence import (
        SecondaryScoringStateEvidence,
    )
    from warhammer40k_core.engine.secondary_scoring_state_evidence_authority import (
        validate_secondary_scoring_state_evidence_authority,
    )

    secondary = next(
        e for e in state.secondary_scoring_state_evidence_records if e.scoring_player_id == player
    )
    raw = secondary.to_payload()
    assert raw["occupancy"] is not None
    raw["occupancy"]["presence_quarter_ids"] = sorted(
        (*raw["occupancy"]["presence_quarter_ids"], "table-quarter:north-west")
    )
    content = {k: v for k, v in raw.items() if k not in {"evidence_hash", "evidence_id"}}
    raw["evidence_hash"] = canonical_payload_sha256(content)
    raw["evidence_id"] = f"secondary-scoring-state-evidence:{raw['evidence_hash']}"
    forged_secondary = SecondaryScoringStateEvidence.from_payload(raw)
    validate_secondary_scoring_state_evidence_authority(secondary, state=state)
    with pytest.raises(GameLifecycleError, match="authoritative boundary state"):
        validate_secondary_scoring_state_evidence_authority(forged_secondary, state=state)

    primary = next(
        e for e in state.primary_scoring_state_evidence_records if e.scoring_player_id == player
    )
    primary_raw = primary.to_payload()
    rows = primary_raw["primary_scoring_spatial_evidence_by_player_id"]
    assert len(rows) == 1
    excluded_unit = next(
        u
        for a in state.army_definitions
        if a.player_id == player
        for u in a.units
        if u.unit_instance_id.endswith("1")
    )
    rows[0]["table_quarter_unit_witnesses"].append(
        {
            "rules_unit_instance_id": excluded_unit.unit_instance_id,
            "quarter_id": "table-quarter:north-west",
            "model_instance_ids": sorted(m.model_instance_id for m in excluded_unit.own_models),
        }
    )
    rows[0]["table_quarter_unit_witnesses"].sort(
        key=lambda w: (w["quarter_id"], w["rules_unit_instance_id"])
    )
    content = {k: v for k, v in primary_raw.items() if k not in {"evidence_hash", "evidence_id"}}
    primary_raw["evidence_hash"] = canonical_payload_sha256(content)
    primary_raw["evidence_id"] = f"primary-scoring-state-evidence:{primary_raw['evidence_hash']}"
    forged_primary = PrimaryScoringStateEvidence.from_payload(primary_raw)
    battlefield = state.battlefield_state
    assert battlefield is not None
    placements = tuple(
        p for a in battlefield.placed_armies for u in a.unit_placements for p in u.model_placements
    )
    validate_primary_scoring_spatial_rows_from_checkpoint(
        state=state, evidence=primary, model_placements=placements
    )
    with pytest.raises(GameLifecycleError, match="authenticated scoring checkpoint"):
        validate_primary_scoring_spatial_rows_from_checkpoint(
            state=state, evidence=forged_primary, model_placements=placements
        )


__all__: list[str] = []
__all__ += ["BaseShape", "CircularBase", "Fraction", "GameState", "Model", "ModelVolume"]
__all__ += ["TYPE_CHECKING", "OvalBase", "Pose", "RectangularBase", "_analytic_quarter_oracle"]
__all__ += ["_assert_forged_quarter_witnesses_rejected", "_exact_rectangle_contact_facing"]
__all__ += ["hypot", "inf", "nextafter", "pytest", "replace", "scoring_table_quarter_id_or_none"]
