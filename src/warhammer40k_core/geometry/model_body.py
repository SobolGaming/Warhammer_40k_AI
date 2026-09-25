"""Explicit model-body prisms, independent of the base used for rules distances."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Self, TypedDict

from warhammer40k_core.geometry.base import (
    BaseShape,
    BaseShapePayload,
    base_shape_from_payload,
    validate_base_shape,
)
from warhammer40k_core.geometry.pose import GeometryError, Pose, validate_finite_number


class ModelBodyPartPayload(TypedDict):
    part_id: str
    base: BaseShapePayload
    offset_x_inches: float
    offset_y_inches: float
    bottom_inches: float
    height_inches: float
    evidence_id: str


@dataclass(frozen=True, slots=True)
class ModelBodyPart:
    part_id: str
    base: BaseShape
    offset_x_inches: float
    offset_y_inches: float
    bottom_inches: float
    height_inches: float
    evidence_id: str

    def __post_init__(self) -> None:
        for value in (self.part_id, self.evidence_id):
            if type(value) is not str or not value.strip():
                raise GeometryError("Model body requires part and evidence identities.")
        validate_base_shape("Model body footprint", self.base)
        for name in ("offset_x_inches", "offset_y_inches", "bottom_inches", "height_inches"):
            object.__setattr__(self, name, validate_finite_number(name, getattr(self, name)))
        if self.bottom_inches < 0 or self.height_inches <= 0:
            raise GeometryError("Model body requires nonnegative bottom and positive height.")

    def pose_at(self, pose: Pose) -> Pose:
        angle = math.radians(pose.facing.degrees)
        c, s = math.cos(angle), math.sin(angle)
        return Pose.at(
            pose.position.x + c * self.offset_x_inches - s * self.offset_y_inches,
            pose.position.y + s * self.offset_x_inches + c * self.offset_y_inches,
            pose.position.z + self.bottom_inches,
            facing_degrees=pose.facing.degrees,
        )

    def to_payload(self) -> ModelBodyPartPayload:
        return {
            "part_id": self.part_id,
            "base": self.base.to_payload(),
            "offset_x_inches": self.offset_x_inches,
            "offset_y_inches": self.offset_y_inches,
            "bottom_inches": self.bottom_inches,
            "height_inches": self.height_inches,
            "evidence_id": self.evidence_id,
        }

    @classmethod
    def from_payload(cls, payload: ModelBodyPartPayload) -> Self:
        if set(payload) != set(ModelBodyPartPayload.__required_keys__):
            raise GeometryError("Model body payload fields differ from the closed schema.")
        return cls(
            part_id=payload["part_id"],
            base=base_shape_from_payload(payload["base"]),
            offset_x_inches=payload["offset_x_inches"],
            offset_y_inches=payload["offset_y_inches"],
            bottom_inches=payload["bottom_inches"],
            height_inches=payload["height_inches"],
            evidence_id=payload["evidence_id"],
        )


def validate_body_parts(parts: tuple[ModelBodyPart, ...]) -> None:
    if type(parts) is not tuple or any(type(part) is not ModelBodyPart for part in parts):
        raise GeometryError("Model body must contain typed body parts.")
    if len({part.part_id for part in parts}) != len(parts):
        raise GeometryError("Model body part identities must be unique.")
