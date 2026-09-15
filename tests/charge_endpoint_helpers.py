"""Real attached-Charge fixtures and facade proposal construction."""

from dataclasses import replace
from typing import cast

from tests.charge_distance_helpers import add_modifier, request_from
from tests.phase15a_charge_declaration_helpers import charge_lifecycle, compact_test_unit_poses
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.charge_movement_source import charge_movement_placement
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.movement_proposals import ProposalKind
from warhammer40k_core.engine.phases.charge import (
    ChargeMoveProposal,
    ChargeMoveResolution,
    resolve_charge_move,
)
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainVolume

ATTACHED_SOURCE = "attached-unit:army-alpha:source"
ATTACHED_TARGET = "army-beta:enemy"


def attached_charge_session() -> LocalGameSession:
    lifecycle, _ = charge_lifecycle(
        alpha_unit_ids=("source", "leader", "next"),
        alpha_attached_unit_ids=("source", "leader"),
        alpha_origins={"leader": Pose.at(17, 20)},
        game_id="order47-attached",
        enemy_model_poses=compact_test_unit_poses(origin=Pose.at(10, 26), model_count=5),
    )
    assert lifecycle.state is not None
    add_modifier(
        lifecycle.state, effect_id="attached-roll-bonus", kind="modify_dice_roll", delta=10
    )
    return LocalGameSession(lifecycle)


def flying_attached_charge_exemption_session() -> tuple[LocalGameSession, RuntimeContentBundle]:
    """Source-assigned FLY on a leader with a vertically distinct distance proof."""
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    sheet = catalog.datasheet_by_id("core-character-leader")
    sheet = replace(
        sheet, keywords=replace(sheet.keywords, keywords=(*sheet.keywords.keywords, "FLY"))
    )
    catalog = replace(
        catalog,
        datasheets=tuple(
            sheet if row.datasheet_id == sheet.datasheet_id else row for row in catalog.datasheets
        ),
        model_keyword_assignments=tuple(
            replace(row, keywords=tuple(sorted((*row.keywords, "FLY"))))
            if row.datasheet_id == sheet.datasheet_id
            else row
            for row in catalog.model_keyword_assignments
        ),
    )
    lifecycle, _ = charge_lifecycle(
        alpha_unit_ids=("source", "leader", "next"),
        alpha_attached_unit_ids=("source", "leader"),
        alpha_origins={"leader": Pose.at(17, 17.6, 4)},
        game_id="order47-exemption-9",
        enemy_model_poses=compact_test_unit_poses(origin=Pose.at(10, 26), model_count=5),
        catalog=catalog,
    )
    assert lifecycle.state is not None
    from warhammer40k_core.engine.ability_catalog import eleventh_edition_ability_catalog_records
    from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
    from warhammer40k_core.engine.lifecycle import GameLifecycle

    armies = tuple(lifecycle.state.army_definitions)
    bundle = RuntimeContentBundle.from_contributions(
        activation=RuntimeContentActivation.from_armies(armies=armies, catalog=catalog),
        armies=armies,
        catalog=catalog,
        contributions=(),
        base_ability_records=eleventh_edition_ability_catalog_records(),
    )
    lifecycle = GameLifecycle.from_payload(lifecycle.to_payload(), runtime_content_bundle=bundle)
    assert lifecycle.state is not None
    add_modifier(lifecycle.state, effect_id="r47-001-roll", kind="modify_dice_roll", delta=20)
    add_modifier(
        lifecycle.state, effect_id="r47-001-distance", kind="modify_move_distance", delta=-5
    )
    return LocalGameSession(lifecycle), bundle


def select_attached_source(
    session: LocalGameSession, *, take_to_the_skies: bool = False
) -> DecisionRequest:
    request = request_from(session.advance_until_decision_or_terminal())
    return request_from(
        session.submit_option(
            request_id=request.request_id,
            option_id=ATTACHED_SOURCE + (":take_to_the_skies" if take_to_the_skies else ""),
            result_id="order47-attached-select",
        )
    )


def attached_move_payload(session: LocalGameSession, request: DecisionRequest) -> JsonValue:
    state = session.lifecycle.state
    assert state is not None
    placement = charge_movement_placement(
        scenario=battlefield_scenario_for_state(state=state), unit_instance_id=ATTACHED_SOURCE
    )
    paths: list[tuple[str, tuple[Pose, ...]]] = []
    for model in placement.model_placements:
        distance = 5 if model.unit_instance_id == "army-alpha:leader" else 4
        paths.append(
            (
                model.model_instance_id,
                (
                    model.pose,
                    Pose.at(model.pose.position.x, model.pose.position.y + distance / 2),
                    Pose.at(model.pose.position.x, model.pose.position.y + distance),
                ),
            )
        )
    return cast(
        JsonValue,
        ChargeMoveProposal(
            proposal_request_id=request.request_id,
            proposal_kind=ProposalKind.CHARGE_MOVE,
            unit_instance_id=ATTACHED_SOURCE,
            movement_phase_action="charge_move",
            movement_mode=MovementMode.CHARGE,
            charge_target_unit_instance_ids=(ATTACHED_TARGET,),
            witness=PathWitness.for_paths(tuple(paths)),
        ).to_payload(),
    )


def endpoint_resolution(
    *,
    distances: tuple[float, ...] = (3, 4, 4, 4, 4),
    maximum: float = 8,
    first_start_y: float = 20,
    terrain: tuple[TerrainVolume, ...] = (),
    ruleset: RulesetDescriptor | None = None,
    targets: tuple[str, ...] = ("army-beta:enemy",),
) -> ChargeMoveResolution:
    """A real five-model Charge with individually specified complete paths."""
    lifecycle, _ = charge_lifecycle(
        alpha_unit_ids=("source",),
        game_id="order47-endpoint-geometry",
        enemy_model_poses=compact_test_unit_poses(origin=Pose.at(10, 26), model_count=5),
    )
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    before = state.battlefield_state.unit_placement_by_id("army-alpha:source")
    first, *others = before.model_placements
    before = before.with_model_placements((first.with_pose(Pose.at(10, first_start_y)), *others))
    scenario = replace(
        battlefield_scenario_for_state(state=state),
        battlefield_state=state.battlefield_state.with_unit_placement(before),
    )
    witness = PathWitness.for_paths(
        tuple(
            (
                model.model_instance_id,
                (
                    model.pose,
                    Pose.at(model.pose.position.x, model.pose.position.y + distance / 2),
                    Pose.at(model.pose.position.x, model.pose.position.y + distance),
                ),
            )
            for model, distance in zip(before.model_placements, distances, strict=True)
        )
    )
    return resolve_charge_move(
        scenario=scenario,
        ruleset_descriptor=state.runtime_ruleset_descriptor() if ruleset is None else ruleset,
        unit_placement=before,
        selected_target_unit_instance_ids=targets,
        maximum_distance_inches=maximum,
        path_witness=witness,
        terrain=terrain,
    )
