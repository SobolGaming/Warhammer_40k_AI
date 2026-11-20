"""Executable inner identity for binary poses and once-rounded movement budgets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict, cast

from warhammer40k_core.geometry.pose import GeometryError

CURRENT_NUMERICAL_POLICY_ID = "binary-inch-milli-inch-movement-budget-v1"
COORDINATE_REPRESENTATION_ID = "binary-float-pose-v1"
NUMERICAL_IDENTITY_VERSION = "engine-numerical-identity-v1"


class NumericalIdentityPayload(TypedDict):
    version: str
    numerical_policy_id: str
    coordinate_representation_id: str


@dataclass(frozen=True, slots=True)
class NumericalIdentity:
    numerical_policy_id: str = CURRENT_NUMERICAL_POLICY_ID
    coordinate_representation_id: str = COORDINATE_REPRESENTATION_ID

    def __post_init__(self) -> None:
        if (
            type(self.numerical_policy_id) is not str
            or self.numerical_policy_id != CURRENT_NUMERICAL_POLICY_ID
            or type(self.coordinate_representation_id) is not str
            or self.coordinate_representation_id != COORDINATE_REPRESENTATION_ID
        ):
            raise GeometryError("Unsupported engine numerical identity.")

    def to_payload(self) -> NumericalIdentityPayload:
        return {
            "version": NUMERICAL_IDENTITY_VERSION,
            "numerical_policy_id": self.numerical_policy_id,
            "coordinate_representation_id": self.coordinate_representation_id,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if type(payload) is not dict:
            raise GeometryError("Engine numerical identity must be an object.")
        values = cast(dict[str, object], payload)
        if (
            set(values) != {"version", "numerical_policy_id", "coordinate_representation_id"}
            or values["version"] != NUMERICAL_IDENTITY_VERSION
        ):
            raise GeometryError(
                "Missing or incompatible engine numerical identity; retain the original executor."
            )
        policy = values["numerical_policy_id"]
        coordinates = values["coordinate_representation_id"]
        if type(policy) is not str or type(coordinates) is not str:
            raise GeometryError("Engine numerical identity fields must be strings.")
        return cls(numerical_policy_id=policy, coordinate_representation_id=coordinates)


CURRENT_NUMERICAL_IDENTITY = NumericalIdentity()


def validate_numerical_identity(value: object) -> NumericalIdentity:
    if type(value) is not NumericalIdentity:
        raise GeometryError("Engine numerical identity must be a NumericalIdentity.")
    # Reconstruct to validate even the mutable state owner's current binding.
    NumericalIdentity(value.numerical_policy_id, value.coordinate_representation_id)
    return value
