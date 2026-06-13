from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.core.deployment_zones import DeploymentZoneShape, DeploymentZoneShapePayload


class BattlefieldRegionError(ValueError):
    """Raised when battlefield-region data violates CORE V2 invariants."""


class BattlefieldRegionKind(StrEnum):
    DEPLOYMENT_ZONE = "deployment_zone"
    TERRITORY = "territory"
    NO_MANS_LAND = "no_mans_land"


class BattlefieldRegionPayload(TypedDict):
    region_id: str
    region_kind: str
    owner_role: str | None
    shape: DeploymentZoneShapePayload
    derived_from: list[str]
    source_id: str


@dataclass(frozen=True, slots=True)
class BattlefieldRegion:
    region_id: str
    region_kind: BattlefieldRegionKind
    owner_role: str | None
    shape: DeploymentZoneShape
    derived_from: tuple[str, ...]
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "region_id",
            _validate_unprefixed_identifier(
                "BattlefieldRegion region_id",
                self.region_id,
                reserved_prefix="battlefield-region:",
            ),
        )
        region_kind = battlefield_region_kind_from_token(self.region_kind)
        object.__setattr__(self, "region_kind", region_kind)
        object.__setattr__(
            self,
            "owner_role",
            _validate_owner_role(region_kind=region_kind, owner_role=self.owner_role),
        )
        if type(self.shape) is not DeploymentZoneShape:
            raise BattlefieldRegionError("BattlefieldRegion shape must be a DeploymentZoneShape.")
        object.__setattr__(self, "shape", self.shape)
        object.__setattr__(
            self,
            "derived_from",
            _validate_identifier_tuple("BattlefieldRegion derived_from", self.derived_from),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("BattlefieldRegion source_id", self.source_id),
        )

    def contains_point(self, x: float, y: float) -> bool:
        return self.shape.contains_point(x, y)

    def bounds(self) -> tuple[float, float, float, float]:
        return self.shape.bounds()

    def to_payload(self) -> BattlefieldRegionPayload:
        return {
            "region_id": self.region_id,
            "region_kind": self.region_kind.value,
            "owner_role": self.owner_role,
            "shape": self.shape.to_payload(),
            "derived_from": list(self.derived_from),
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if not isinstance(payload, dict):
            raise BattlefieldRegionError("Battlefield region payload must be a mapping.")
        raw_payload = cast(BattlefieldRegionPayload, payload)
        return cls(
            region_id=raw_payload["region_id"],
            region_kind=battlefield_region_kind_from_token(raw_payload["region_kind"]),
            owner_role=raw_payload["owner_role"],
            shape=DeploymentZoneShape.from_payload(raw_payload["shape"]),
            derived_from=tuple(raw_payload["derived_from"]),
            source_id=raw_payload["source_id"],
        )


def battlefield_region_kind_from_token(token: object) -> BattlefieldRegionKind:
    if type(token) is BattlefieldRegionKind:
        return token
    if type(token) is not str:
        raise BattlefieldRegionError("BattlefieldRegionKind token must be a string.")
    try:
        return BattlefieldRegionKind(token)
    except ValueError as exc:
        raise BattlefieldRegionError(f"Unsupported BattlefieldRegionKind token: {token}.") from exc


def _validate_owner_role(
    *,
    region_kind: BattlefieldRegionKind,
    owner_role: object,
) -> str | None:
    if owner_role is None:
        if region_kind is not BattlefieldRegionKind.NO_MANS_LAND:
            raise BattlefieldRegionError("Owned battlefield regions must include owner_role.")
        return None
    if type(owner_role) is not str:
        raise BattlefieldRegionError("BattlefieldRegion owner_role must be a string or None.")
    stripped = owner_role.strip()
    if stripped not in {"attacker", "defender"}:
        raise BattlefieldRegionError("BattlefieldRegion owner_role must be attacker or defender.")
    if region_kind is BattlefieldRegionKind.NO_MANS_LAND:
        raise BattlefieldRegionError("No-man's-land battlefield regions must not have owner_role.")
    return stripped


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise BattlefieldRegionError(f"{field_name} must be a tuple.")
    identifiers = tuple(
        _validate_identifier(f"{field_name} item", value)
        for value in cast(tuple[object, ...], values)
    )
    if len(set(identifiers)) != len(identifiers):
        raise BattlefieldRegionError(f"{field_name} must not contain duplicates.")
    return tuple(sorted(identifiers))


def _validate_unprefixed_identifier(
    field_name: str,
    value: object,
    *,
    reserved_prefix: str,
) -> str:
    identifier = _validate_identifier(field_name, value)
    if identifier.startswith(reserved_prefix):
        raise BattlefieldRegionError(f"{field_name} must not include the stable identity prefix.")
    return identifier


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise BattlefieldRegionError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise BattlefieldRegionError(f"{field_name} must not be empty.")
    return stripped
