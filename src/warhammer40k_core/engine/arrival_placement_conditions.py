"""Source-selected, replayable geometry conditions for reserve distance grants."""

from __future__ import annotations

import msgspec

from warhammer40k_core.core.deployment_zones import DeploymentZone
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model


class ArrivalAnchor(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    model_instance_id: str
    pose: tuple[float, float, float, float]

    @classmethod
    def from_model(cls, model: Model) -> ArrivalAnchor:
        return cls(
            model.model_id,
            (
                model.pose.position.x,
                model.pose.position.y,
                model.pose.position.z,
                model.pose.facing.degrees,
            ),
        )


class ArrivalPlacementCondition(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    """Whole unit in a zone union OR every model within an eligible anchor's range.

    Empty conditions explicitly mean an unconditional grant. Anchor eligibility is
    resolved by the source provider against the arriving rules unit, never cargo.
    """

    deployment_zone_ids: tuple[str, ...]
    includes_no_mans_land: bool
    anchors: tuple[ArrivalAnchor, ...]
    anchor_distance_inches: float | None

    def __post_init__(self) -> None:
        import math

        if type(self.includes_no_mans_land) is not bool:
            raise GameLifecycleError("Arrival region no-man's-land flag is invalid.")
        if len(set(self.deployment_zone_ids)) != len(self.deployment_zone_ids):
            raise GameLifecycleError("Arrival region has duplicate deployment zones.")
        if bool(self.anchors) != (self.anchor_distance_inches is not None):
            raise GameLifecycleError("Arrival anchors require exactly one range.")
        if self.anchor_distance_inches is not None and (
            not math.isfinite(self.anchor_distance_inches) or self.anchor_distance_inches <= 0
        ):
            raise GameLifecycleError("Arrival anchor range must be positive and finite.")
        for anchor in self.anchors:
            if not anchor.model_instance_id or any(not math.isfinite(v) for v in anchor.pose):
                raise GameLifecycleError("Arrival anchor identity or pose is invalid.")

    @classmethod
    def unconditional(cls) -> ArrivalPlacementCondition:
        return cls((), False, (), None)

    def allows(
        self,
        *,
        models: tuple[Model, ...],
        scenario: BattlefieldScenario,
        deployment_zones: tuple[DeploymentZone, ...],
    ) -> bool:
        if self == self.unconditional():
            return True
        if not models:
            return False
        zones = {zone.deployment_zone_id: zone for zone in deployment_zones}
        if not set(self.deployment_zone_ids).issubset(zones):
            raise GameLifecycleError("Arrival region refers to an unknown deployment zone.")
        surface = None
        for zone_id in self.deployment_zone_ids:
            zone_surface = shapely_backend.footprint_for_deployment_zone(zones[zone_id])
            surface = zone_surface if surface is None else surface.union(zone_surface)
        if self.includes_no_mans_land:
            battlefield = scenario.battlefield_state
            no_mans_land = shapely_backend.footprint_for_no_mans_land(
                battlefield_bounds=(
                    0,
                    0,
                    battlefield.battlefield_width_inches,
                    battlefield.battlefield_depth_inches,
                ),
                deployment_zones=deployment_zones,
            )
            surface = no_mans_land if surface is None else surface.union(no_mans_land)
        if surface is not None and all(
            surface.covers(shapely_backend.footprint_for_base(model.base, model.pose))
            for model in models
        ):
            return True
        if self.anchor_distance_inches is None:
            return False
        anchors: list[Model] = []
        for anchor in self.anchors:
            # The source's placement is fixed at ingress; its catalog geometry is
            # still authoritative even if it subsequently moved or was removed.
            source = next(
                (
                    model
                    for army in scenario.armies
                    for unit in army.units
                    for model in unit.own_models
                    if model.model_instance_id == anchor.model_instance_id
                ),
                None,
            )
            if source is None:
                raise GameLifecycleError("Arrival anchor has unknown model identity.")
            from warhammer40k_core.engine.battlefield_state import (
                ModelPlacement,
                geometry_model_for_placement,
            )

            owner = next(
                (army, unit)
                for army in scenario.armies
                for unit in army.units
                if source in unit.own_models
            )
            anchors.append(
                geometry_model_for_placement(
                    model=source,
                    placement=ModelPlacement(
                        army_id=owner[0].army_id,
                        player_id=owner[0].player_id,
                        unit_instance_id=owner[1].unit_instance_id,
                        model_instance_id=anchor.model_instance_id,
                        pose=Pose.at(*anchor.pose),
                    ),
                )
            )
        return all(
            any(
                shapely_backend.base_footprint_distance(
                    model.base, model.pose, anchor.base, anchor.pose
                )
                <= self.anchor_distance_inches
                for anchor in anchors
            )
            for model in models
        )
