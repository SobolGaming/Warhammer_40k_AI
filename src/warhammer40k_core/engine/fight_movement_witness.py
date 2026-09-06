"""Shared Fight witness validation before movement rules or authoritative mutation."""

from __future__ import annotations

from warhammer40k_core.engine.movement_proposals import (
    MovementProposalRequest,
    ProposalValidationResult,
)
from warhammer40k_core.geometry.pathing import (
    PathValidationResult,
    PathWitness,
    TerrainPathLegalityResult,
    is_degenerate_endpoint_only_real_movement_path,
)


def closed_loop_fight_model_id(witness: PathWitness | None) -> str | None:
    if witness is None:
        return None
    for model_id in witness.model_ids():
        path = witness.poses_for_model(model_id)
        if path[0] == path[-1] and any(pose != path[0] for pose in path[1:]):
            return model_id
    return None


def validate_fight_witness_shape(
    request: MovementProposalRequest, witness: PathWitness
) -> ProposalValidationResult:
    if closed_loop_fight_model_id(witness) is not None:
        return _invalid(
            request,
            "closed_loop_fight_movement",
            "Fight movement cannot depart from and return to the same model pose.",
        )
    if any(
        is_degenerate_endpoint_only_real_movement_path(witness.poses_for_model(model_id))
        for model_id in witness.model_ids()
    ):
        return _invalid(
            request,
            "endpoint_only_path",
            "Fight movement PathWitness must not repeat only endpoint poses.",
        )
    return ProposalValidationResult.valid(
        proposal_request_id=request.request_id, proposal_kind=request.proposal_kind
    )


def fight_movement_path_violation(
    *,
    request: MovementProposalRequest,
    witness: PathWitness | None,
    path_results: tuple[PathValidationResult, ...],
    terrain_results: tuple[TerrainPathLegalityResult, ...],
    coherency_invalid: bool,
) -> ProposalValidationResult | None:
    if witness is not None:
        shape = validate_fight_witness_shape(request, witness)
        if not shape.is_valid:
            return shape
    for path_result in path_results:
        if not path_result.is_valid:
            violation = path_result.violations[0]
            return _invalid(request, violation.violation_code, violation.message)
    for terrain_result in terrain_results:
        if not terrain_result.is_valid:
            terrain_violation = terrain_result.violations[0]
            return _invalid(request, terrain_violation.violation_code, terrain_violation.message)
    if coherency_invalid:
        return _invalid(
            request, "unit_coherency_invalid", "Fight movement endpoint violates unit coherency."
        )
    return None


def _invalid(request: MovementProposalRequest, code: str, message: str) -> ProposalValidationResult:
    return ProposalValidationResult.invalid(
        proposal_request_id=request.request_id,
        proposal_kind=request.proposal_kind,
        violation_code=code,
        message=message,
        field="witness",
    )
