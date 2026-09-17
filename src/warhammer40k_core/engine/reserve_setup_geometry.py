"""Oversized reserve setup through shared engine-owned validation."""

from __future__ import annotations

# pyright: reportPrivateUsage=false
from warhammer40k_core.engine.reserves import (
    BattlefieldEdge,
    LargeModelReservePlacementException,
    ReservePlacementViolation,
    ReservePlacementViolationCode,
    StrategicReserveRule,
    model_touches_edge,
    model_wholly_within_any_edge_band,
)
from warhammer40k_core.geometry.volume import Model


def append_strategic_reserves_edge_violations(
    *,
    violations: list[ReservePlacementViolation],
    models: tuple[Model, ...],
    battle_round: int,
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
    strategic_reserve_rule: StrategicReserveRule,
    qualifying_edges: tuple[BattlefieldEdge, ...],
    large_model_exceptions: tuple[LargeModelReservePlacementException, ...],
) -> None:
    if battle_round == 1:
        return
    exception_by_model_id = {
        exception.model_instance_id: exception for exception in large_model_exceptions
    }
    model_ids = {model.model_id for model in models}
    for exception in large_model_exceptions:
        model = next(
            (
                candidate
                for candidate in models
                if candidate.model_id == exception.model_instance_id
            ),
            None,
        )
        if model is None:
            violations.append(
                ReservePlacementViolation(
                    violation_code=ReservePlacementViolationCode.UNIT_PLACEMENT_DRIFT,
                    message="Large-model exception references a model outside the placement.",
                    model_instance_id=exception.model_instance_id,
                )
            )
            continue
        if exception.battlefield_edge not in qualifying_edges:
            violations.append(
                ReservePlacementViolation(
                    violation_code=(
                        ReservePlacementViolationCode.LARGE_MODEL_EXCEPTION_EDGE_NOT_QUALIFYING
                    ),
                    message="Large-model exception edge is not a qualifying edge.",
                    model_instance_id=model.model_id,
                    battlefield_edge=exception.battlefield_edge,
                )
            )
        if model_wholly_within_any_edge_band(
            model,
            edges=qualifying_edges,
            distance_inches=strategic_reserve_rule.edge_distance_inches,
            battlefield_width_inches=battlefield_width_inches,
            battlefield_depth_inches=battlefield_depth_inches,
        ):
            violations.append(
                ReservePlacementViolation(
                    violation_code=ReservePlacementViolationCode.LARGE_MODEL_EXCEPTION_UNNEEDED,
                    message="Model already satisfies Strategic Reserves edge distance.",
                    model_instance_id=model.model_id,
                    battlefield_edge=exception.battlefield_edge,
                )
            )
        from warhammer40k_core.engine.large_model_setup import base_fits_edge_band

        if base_fits_edge_band(
            model,
            edge=exception.battlefield_edge,
            distance_inches=strategic_reserve_rule.edge_distance_inches,
            battlefield_width_inches=battlefield_width_inches,
            battlefield_depth_inches=battlefield_depth_inches,
        ):
            violations.append(
                ReservePlacementViolation(
                    violation_code=(
                        ReservePlacementViolationCode.LARGE_MODEL_EXCEPTION_MODEL_CAN_FIT
                    ),
                    message="Model can physically fit wholly within the required edge area.",
                    model_instance_id=model.model_id,
                    battlefield_edge=exception.battlefield_edge,
                )
            )
        if not model_touches_edge(
            model,
            edge=exception.battlefield_edge,
            battlefield_width_inches=battlefield_width_inches,
            battlefield_depth_inches=battlefield_depth_inches,
        ):
            violations.append(
                ReservePlacementViolation(
                    violation_code=(
                        ReservePlacementViolationCode.LARGE_MODEL_EXCEPTION_EDGE_CONTACT_MISSING
                    ),
                    message="Large-model exception requires touching the battlefield edge.",
                    model_instance_id=model.model_id,
                    battlefield_edge=exception.battlefield_edge,
                )
            )
    for model in models:
        if model.model_id in exception_by_model_id:
            continue
        if model_wholly_within_any_edge_band(
            model,
            edges=qualifying_edges,
            distance_inches=strategic_reserve_rule.edge_distance_inches,
            battlefield_width_inches=battlefield_width_inches,
            battlefield_depth_inches=battlefield_depth_inches,
        ):
            continue
        violations.append(
            ReservePlacementViolation(
                violation_code=ReservePlacementViolationCode.STRATEGIC_RESERVES_EDGE_DISTANCE,
                message="Strategic Reserves model is not wholly within 6 inches of an edge.",
                model_instance_id=model.model_id,
            )
        )
    if set(exception_by_model_id).difference(model_ids):
        return
