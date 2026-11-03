"""Native current-source units at canonical battle checkpoints, using real facade actions."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from tests.support.faction_batch01 import FACTIONS, Scene, request
from tests.support.section02_fixtures import Section02Definitions
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest
from warhammer40k_core.engine.phase import LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27 as identities,
)

AUTARCH = "000000577"
VOIDSCARRED = "000002532"


def definitions(
    index: Path | None,
    *,
    datasheet_ids: tuple[str, ...] = (
        AUTARCH,
        VOIDSCARRED,
        "000000593",
        "000004078",
        "000002759",
        "000000600",
    ),
) -> Section02Definitions:
    package = _ability_support_catalog_package(
        datasheet_ids=datasheet_ids,
        source_index_dir=index,
    )
    catalog = package.army_catalog
    factions: list[FactionDefinition] = []
    detachments: list[DetachmentDefinition] = []
    for source in catalog.factions:
        faction_id, detachment_id = FACTIONS[source.faction_id]
        faction = next(row for row in identities.faction_rows() if row.faction_id == faction_id)
        detachment = next(
            row for row in identities.detachment_rows() if row.detachment_id == detachment_id
        )
        factions.append(
            FactionDefinition(
                faction_id=faction_id,
                name=faction.name,
                faction_keywords=source.faction_keywords,
                source_ids=(*faction.source_ids, *source.source_ids),
            )
        )
        detachments.append(
            DetachmentDefinition(
                canonical_detachment_id=detachment.detachment_id,
                detachment_id=detachment.detachment_id,
                name=detachment.name,
                faction_id=faction_id,
                detachment_point_cost=detachment.detachment_point_cost,
                unit_datasheet_ids=tuple(
                    s.datasheet_id
                    for s in catalog.datasheets
                    if set(s.keywords.faction_keywords) & set(source.faction_keywords)
                ),
                force_disposition_ids=tuple(
                    sorted({detachment.force_disposition_id, "take-and-hold", "purge-the-foe"})
                ),
                source_ids=detachment.source_ids,
            )
        )
    return Section02Definitions(
        replace(
            package,
            army_catalog=replace(catalog, factions=tuple(factions), detachments=tuple(detachments)),
        ),
        0.0,
    )


def charge(
    s: Scene,
    unit_id: str,
    enemy_id: str,
    dx: float,
    *,
    endpoints: dict[str, Pose] | None = None,
    use_flitting: bool = False,
) -> LifecycleStatus:
    r = s.session.lifecycle.pending_decision_request()
    if r is None:
        r = request(s.session.advance_until_decision_or_terminal(), "select_charging_unit")
    assert r.decision_type == "select_charging_unit"
    status = s.session.submit_option(
        request_id=r.request_id, option_id=unit_id, result_id=f"{r.request_id}:select"
    )
    for _ in range(12):
        r = request(status)
        if r.decision_type == "submit_movement_proposal":
            break
        if r.decision_type == "select_charge_targets":
            option = next(
                o
                for o in r.options
                if isinstance(o.payload, dict) and o.payload.get("target_ids") == [enemy_id]
            )
        elif r.decision_type in {"select_core_ability_instance", "resolve_sequencing_order"}:
            option = r.options[0]
        elif r.decision_type == "select_charge_declaration_grant" and use_flitting:
            option = next(o for o in r.options if "flitting_shadows" in o.option_id)
        else:
            option = next(o for o in r.options if "decline" in o.option_id)
        status = s.session.submit_option(
            request_id=r.request_id, option_id=option.option_id, result_id=f"{r.request_id}:choice"
        )
    else:
        raise AssertionError("Charge move proposal not reached")
    move = MovementProposalRequest.from_decision_request_payload(r.payload)
    assert move.proposal_kind.value == "charge_move"
    assert s.state.battlefield_state is not None
    placed = RulesUnitPlacement.from_battlefield(
        view=rules_unit_view_by_id(state=s.state, unit_instance_id=unit_id),
        battlefield_state=s.state.battlefield_state,
    )
    status = s.session.submit_parameterized_payload(
        request_id=r.request_id,
        result_id=f"{r.request_id}:move",
        payload={
            "proposal_request_id": move.request_id,
            "proposal_kind": "charge_move",
            "unit_instance_id": unit_id,
            "movement_phase_action": "charge_move",
            "movement_mode": "charge",
            "charge_target_unit_instance_ids": [enemy_id],
            "witness": validate_json_value(
                PathWitness.for_paths(
                    tuple(
                        (
                            p.model_instance_id,
                            (
                                p.pose,
                                Pose.at(p.pose.position.x + dx, p.pose.position.y)
                                if endpoints is None
                                else endpoints[p.model_instance_id],
                            ),
                        )
                        for p in placed.model_placements
                    )
                ).to_payload()
            ),
        },
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    return status
