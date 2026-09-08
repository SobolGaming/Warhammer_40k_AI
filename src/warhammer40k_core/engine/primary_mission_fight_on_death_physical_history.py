from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.geometry.pose import Pose


@dataclass(frozen=True, slots=True)
class PhysicalAuthorityState:
    presence: str | None
    pose: Pose | None
    wounds_remaining: int | None
