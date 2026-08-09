from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

from warhammer40k_core.adapters.battlefield_projection import (
    BATTLEFIELD_COORDINATE_SPACE,
    BATTLEFIELD_COORDINATE_SPEC_VERSION,
    BATTLEFIELD_VIEW_SCHEMA_VERSION,
    BattlefieldAuthoritativeEntitiesPayload,
    BattlefieldBoundsPayload,
    BattlefieldViewPayload,
    authoritative_geometry_hash,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.projection import GameViewPayload
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    MovementMode,
    RulesetDescriptor,
)
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest
from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind, ModelPlacement
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.deployment import (
    SELECT_DEPLOYMENT_UNIT_DECISION_TYPE,
    SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE,
    DeploymentPlacementProposal,
    DeploymentPlacementRequest,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_resolution import (
    MELEE_DECLARATION_PROPOSAL_KIND,
    MeleeDeclarationProposal,
    MeleeTargetAllocation,
    MeleeWeaponDeclaration,
)
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalPayload,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.opportunity_windows import (
    OpportunityActionKind,
    OpportunityLegalAction,
    OpportunityWindow,
)
from warhammer40k_core.engine.phase import (
    GameLifecycleError,
    LifecycleStatus,
    LifecycleStatusKind,
    SetupStep,
)
from warhammer40k_core.engine.phases.charge import CHARGE_MOVE_ACTION, ChargeMoveProposal
from warhammer40k_core.engine.phases.movement import (
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    MovementPhaseActionKind,
)
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)
from warhammer40k_core.engine.unit_factory import ModelInstance
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.engine.weapon_declaration import (
    SHOOTING_DECLARATION_PROPOSAL_KIND,
    ShootingDeclarationProposal,
    WeaponDeclaration,
)
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose, PosePayload
from warhammer40k_core.rules.mission_pack_import import (
    chapter_approved_2026_27_mission_pack,
)

UI_FIXTURE_DIR = Path("contracts/examples/projections")
BATTLEFIELD_EXAMPLE_DIR = Path("contracts/examples/battlefield")
DECISION_EXAMPLE_DIR = Path("contracts/examples/decisions")
PROPOSAL_EXAMPLE_DIR = DECISION_EXAMPLE_DIR / "proposals"

FIXED_SECONDARY_OPTION_ID = "fixed:assassination:bring_it_down"
PLAYER_A = "player-a"
PLAYER_B = "player-b"
ARMY_ALPHA = "army-alpha"
ARMY_BETA = "army-beta"
UNIT_ALPHA = "army-alpha:intercessor-unit-1"
UNIT_BETA = "army-beta:intercessor-unit-2"
MODEL_ALPHA_1 = "army-alpha:intercessor-unit-1:core-intercessor-like:001"
MODEL_BETA_1 = "army-beta:intercessor-unit-2:core-intercessor-like:001"


@dataclass(frozen=True, slots=True)
class UiContractBundle:
    fixtures: dict[str, JsonValue]
    battlefield_examples: dict[str, JsonValue]
    proposal_payload_examples: dict[str, JsonValue]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export stable UI contract fixtures from the LocalGameSession facade.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root to write canonical contracts/examples payloads under.",
    )
    args = parser.parse_args(argv)

    written_paths = export_ui_contract_files(output_root=args.output_root)
    for path in written_paths:
        print(path.as_posix())
    return 0


def export_ui_contract_files(*, output_root: Path) -> tuple[Path, ...]:
    bundle = build_ui_contract_bundle()
    written: list[Path] = []
    for name, payload in sorted(bundle.fixtures.items()):
        fixture_directory = (
            DECISION_EXAMPLE_DIR if name == "pending_movement_request.json" else UI_FIXTURE_DIR
        )
        path = output_root / fixture_directory / name
        _write_json(path, payload)
        written.append(path)
    for name, payload in sorted(bundle.battlefield_examples.items()):
        path = output_root / BATTLEFIELD_EXAMPLE_DIR / name
        _write_json(path, payload)
        written.append(path)
    for name, payload in sorted(bundle.proposal_payload_examples.items()):
        example_directory = (
            DECISION_EXAMPLE_DIR if name == "opportunity_window.json" else PROPOSAL_EXAMPLE_DIR
        )
        path = output_root / example_directory / name
        _write_json(path, payload)
        written.append(path)
    return tuple(written)


def build_ui_contract_bundle() -> UiContractBundle:
    initial_session, _initial_status = _fresh_started_session(game_id="ui-contract-initial")

    hidden_session, hidden_status = _fresh_started_session(game_id="ui-contract-hidden-redaction")
    hidden_request = _decision_request(hidden_status)
    _assert_decision_type(hidden_request, SECONDARY_MISSION_DECISION_TYPE)
    hidden_session.submit_option(
        request_id=hidden_request.request_id,
        option_id=FIXED_SECONDARY_OPTION_ID,
        result_id="ui-contract-hidden-redaction-secondary-a",
    )

    post_deployment_session, _post_deployment_status = build_local_session_at_movement_request(
        game_id="ui-contract-post-deployment"
    )
    post_deployment_view = post_deployment_session.view(viewer_player_id=PLAYER_A)
    pending_movement = post_deployment_view["pending_decision"]
    if pending_movement is None:
        raise GameLifecycleError("UI contract movement fixture requires a pending decision.")

    hidden_reserve_session, _hidden_reserve_status = build_local_session_at_movement_request(
        game_id="ui-contract-terrain-snapshot-hidden-reserve"
    )
    _session_state(hidden_reserve_session).reposition_unit_to_strategic_reserves(
        player_id=PLAYER_B,
        unit_instance_id=UNIT_BETA,
        source_rule_ids=("ui-contract:fixture:hidden-reserve",),
    )

    modifier_session, _modifier_status = build_local_session_at_movement_request(
        game_id="ui-contract-visible-modifier"
    )
    _inject_fixture_movement_modifier(
        modifier_session,
        modifier_id="ui-contract-move-plus-one",
        movement=7,
    )

    fixtures: dict[str, JsonValue] = {
        "hidden_secondary_redaction_view.json": validate_json_value(
            cast(JsonValue, hidden_session.view(viewer_player_id=PLAYER_B))
        ),
        "initial_setup_view_player1.json": validate_json_value(
            cast(JsonValue, initial_session.view(viewer_player_id=PLAYER_A))
        ),
        "initial_setup_view_player2.json": validate_json_value(
            cast(JsonValue, initial_session.view(viewer_player_id=PLAYER_B))
        ),
        "pending_movement_request.json": validate_json_value(cast(JsonValue, pending_movement)),
        "post_deployment_view.json": validate_json_value(cast(JsonValue, post_deployment_view)),
        "rules_catalog_view.json": validate_json_value(
            cast(JsonValue, initial_session.rules_catalog_view())
        ),
        "terrain_snapshot_hidden_reserve_view_player_a.json": validate_json_value(
            cast(JsonValue, hidden_reserve_session.view(viewer_player_id=PLAYER_A))
        ),
        "terrain_snapshot_hidden_reserve_view_player_b.json": validate_json_value(
            cast(JsonValue, hidden_reserve_session.view(viewer_player_id=PLAYER_B))
        ),
        "visible_modifier_datacard_view.json": validate_json_value(
            cast(JsonValue, modifier_session.view(viewer_player_id=PLAYER_A))
        ),
    }
    return UiContractBundle(
        fixtures=fixtures,
        battlefield_examples={
            "geometry-conformance.json": validate_json_value(
                cast(JsonValue, _battlefield_geometry_conformance_example())
            )
        },
        proposal_payload_examples=_proposal_payload_examples(),
    )


def _battlefield_geometry_conformance_example() -> BattlefieldViewPayload:
    bounds = cast(
        BattlefieldBoundsPayload,
        validate_json_value(
            {
                "min_x_inches": 0.0,
                "min_y_inches": 0.0,
                "min_z_inches": 0.0,
                "max_x_inches": 60.0,
                "max_y_inches": 44.0,
            }
        ),
    )
    circle_model_id = "geometry-conformance-circle-model"
    oval_model_id = "geometry-conformance-oval-model"
    hull_model_id = "geometry-conformance-hull-model"
    region_shape = {
        "polygons": [
            [
                _conformance_point(0.0, 0.0),
                _conformance_point(20.0, 0.0),
                _conformance_point(20.0, 12.0),
                _conformance_point(0.0, 12.0),
            ]
        ],
        "circle_cutouts": [
            _conformance_shape(
                kind="circle",
                center=_conformance_point(5.0, 5.0),
                radius=1.5,
            )
        ],
        "polygon_cutouts": [
            _conformance_shape(
                kind="polygon",
                vertices=[
                    _conformance_point(10.0, 2.0),
                    _conformance_point(13.0, 2.0),
                    _conformance_point(11.5, 4.0),
                ],
            )
        ],
    }
    authoritative = cast(
        BattlefieldAuthoritativeEntitiesPayload,
        validate_json_value(
            {
                "models_by_id": {
                    circle_model_id: _conformance_model(
                        model_id=circle_model_id,
                        unit_id="geometry-conformance-circle-unit",
                        pose=_conformance_pose(8.0, 8.0, facing=30.0),
                        measurement_basis="base",
                        measurement_shapes=[
                            _conformance_shape(
                                kind="circle",
                                center=_conformance_point(0.0, 0.0),
                                radius=0.63,
                            )
                        ],
                        support_shape=_conformance_shape(
                            kind="circle",
                            center=_conformance_point(0.0, 0.0),
                            radius=0.63,
                        ),
                        geometry_source_id="geometry-conformance-circle-source",
                    ),
                    oval_model_id: _conformance_model(
                        model_id=oval_model_id,
                        unit_id="geometry-conformance-oval-unit",
                        pose=_conformance_pose(18.0, 10.0, facing=45.0),
                        measurement_basis="base",
                        measurement_shapes=[
                            _conformance_shape(
                                kind="ellipse",
                                center=_conformance_point(0.25, 0.0),
                                length=2.95,
                                width=1.65,
                                rotation=15.0,
                            )
                        ],
                        support_shape=_conformance_shape(
                            kind="ellipse",
                            center=_conformance_point(0.0, 0.0),
                            length=2.95,
                            width=1.65,
                        ),
                        geometry_source_id="geometry-conformance-oval-source",
                    ),
                    hull_model_id: _conformance_model(
                        model_id=hull_model_id,
                        unit_id="geometry-conformance-hull-unit",
                        pose=_conformance_pose(32.0, 18.0, z=0.5, facing=135.0),
                        measurement_basis="hull",
                        measurement_shapes=[
                            _conformance_shape(
                                kind="rectangle",
                                center=_conformance_point(0.0, 0.0),
                                length=5.0,
                                width=2.5,
                                rotation=10.0,
                            )
                        ],
                        support_shape=_conformance_shape(
                            kind="circle",
                            center=_conformance_point(0.0, 0.0),
                            radius=1.25,
                        ),
                        geometry_source_id="geometry-conformance-hull-source",
                    ),
                },
                "terrain_features_by_id": {
                    "geometry-conformance-terrain": {
                        "entity_kind": "terrain_feature",
                        "terrain_feature_id": "geometry-conformance-terrain",
                        "terrain_feature_kind": "ruins",
                        "classification": "unknown",
                        "footprint": _conformance_shape(
                            kind="rectangle",
                            center=_conformance_point(42.0, 25.0),
                            length=8.0,
                            width=6.0,
                            rotation=25.0,
                        ),
                        "volumes": [
                            {
                                "volume_id": "geometry-conformance-wall",
                                "volume_kind": "wall",
                                "bottom_center": _conformance_position(42.0, 27.0, 0.0),
                                "width_inches": 6.0,
                                "depth_inches": 0.25,
                                "height_inches": 4.0,
                                "rotation_degrees": 25.0,
                            },
                            {
                                "volume_id": "geometry-conformance-floor",
                                "volume_kind": "floor",
                                "bottom_center": _conformance_position(42.0, 25.0, 2.0),
                                "width_inches": 6.0,
                                "depth_inches": 4.0,
                                "height_inches": 0.25,
                                "rotation_degrees": 25.0,
                            },
                        ],
                        "source_id": "geometry-conformance-terrain-source",
                    }
                },
                "terrain_areas_by_id": {
                    "geometry-conformance-area": {
                        "entity_kind": "terrain_area",
                        "terrain_area_id": "geometry-conformance-area",
                        "classification": "crater",
                        "footprint": _conformance_shape(
                            kind="polygon",
                            vertices=[
                                _conformance_point(22.0, 30.0),
                                _conformance_point(28.0, 30.0),
                                _conformance_point(27.0, 35.0),
                                _conformance_point(23.0, 35.0),
                            ],
                        ),
                        "source_id": "geometry-conformance-area-source",
                    }
                },
                "objectives_by_id": {
                    "geometry-conformance-objective": {
                        "entity_kind": "objective",
                        "objective_id": "geometry-conformance-objective",
                        "objective_role": "primary",
                        "position": _conformance_position(30.0, 22.0, 0.0),
                        "marker_diameter_inches": 1.574803149606299,
                        "measurement_anchor": "marker_edge",
                        "source_id": "geometry-conformance-objective-source",
                    }
                },
                "deployment_zones_by_id": {
                    "geometry-conformance-zone": {
                        "entity_kind": "deployment_zone",
                        "deployment_zone_id": "geometry-conformance-zone",
                        "owner_player_id": PLAYER_A,
                        "shape": region_shape,
                    }
                },
                "battlefield_regions_by_id": {
                    "geometry-conformance-region": {
                        "entity_kind": "battlefield_region",
                        "region_id": "geometry-conformance-region",
                        "region_kind": "mission_area",
                        "owner_role": None,
                        "shape": region_shape,
                        "source_id": "geometry-conformance-region-source",
                    }
                },
            }
        ),
    )
    return cast(
        BattlefieldViewPayload,
        validate_json_value(
            {
                "schema_version": BATTLEFIELD_VIEW_SCHEMA_VERSION,
                "coordinate_spec_version": BATTLEFIELD_COORDINATE_SPEC_VERSION,
                "coordinate_space": BATTLEFIELD_COORDINATE_SPACE,
                "battlefield_id": "geometry-conformance-battlefield",
                "bounds": bounds,
                "authoritative_geometry_hash": authoritative_geometry_hash(
                    bounds=bounds,
                    authoritative=authoritative,
                ),
                "authoritative": authoritative,
                "interaction": {
                    "request_id": "geometry-conformance-request",
                    "selected_or_acting_entity_ids": [circle_model_id],
                    "legal_candidate_refs": [
                        {
                            "reference_kind": "decision_option",
                            "reference_id": "geometry-conformance-option",
                        }
                    ],
                    "measurement_overlays": [
                        {
                            "overlay_id": "geometry-conformance-measurement",
                            "start": _conformance_position(8.0, 8.0, 0.0),
                            "end": _conformance_position(18.0, 10.0, 0.0),
                            "distance_inches": 10.198039027185569,
                        }
                    ],
                    "path_overlays": [
                        {
                            "overlay_id": "geometry-conformance-path",
                            "model_instance_id": circle_model_id,
                            "segments": [
                                {
                                    "segment_kind": "line",
                                    "start": _conformance_pose(8.0, 8.0, facing=30.0),
                                    "end": _conformance_pose(12.0, 9.0, facing=75.0),
                                },
                                {
                                    "segment_kind": "line",
                                    "start": _conformance_pose(12.0, 9.0, facing=75.0),
                                    "end": _conformance_pose(15.0, 12.0, facing=120.0),
                                },
                            ],
                        }
                    ],
                },
                "render": {
                    "hit_regions_by_entity_id": {
                        "geometry-conformance-terrain": {
                            "entity_id": "geometry-conformance-terrain",
                            "shape": _conformance_shape(
                                kind="polygon",
                                vertices=[
                                    _conformance_point(38.0, 22.0),
                                    _conformance_point(46.0, 22.0),
                                    _conformance_point(46.0, 28.0),
                                    _conformance_point(38.0, 28.0),
                                ],
                            ),
                        }
                    },
                    "hints_by_entity_id": {
                        "geometry-conformance-terrain": {
                            "entity_id": "geometry-conformance-terrain",
                            "asset_id": "geometry-conformance-terrain-asset",
                        }
                    },
                },
            }
        ),
    )


def _conformance_model(
    *,
    model_id: str,
    unit_id: str,
    pose: JsonValue,
    measurement_basis: str,
    measurement_shapes: list[JsonValue],
    support_shape: JsonValue,
    geometry_source_id: str,
) -> JsonValue:
    return {
        "entity_kind": "model",
        "model_instance_id": model_id,
        "unit_instance_id": unit_id,
        "owner_player_id": PLAYER_A,
        "state": "placed",
        "pose": pose,
        "geometry": {
            "measurement_basis": measurement_basis,
            "measurement_shapes": measurement_shapes,
            "support_shape": support_shape,
            "height_inches": 2.0,
            "geometry_source_kind": "manual_override",
            "geometry_source_id": geometry_source_id,
            "height_source_kind": "manual_override",
            "height_source_id": f"{geometry_source_id}-height",
        },
        "state_context": {
            "transport_unit_instance_id": None,
            "reserve_kind": None,
        },
    }


def _conformance_shape(
    *,
    kind: str,
    center: JsonValue = None,
    radius: float | None = None,
    length: float | None = None,
    width: float | None = None,
    rotation: float = 0.0,
    vertices: list[JsonValue] | None = None,
) -> JsonValue:
    return {
        "kind": kind,
        "center": center,
        "rotation_degrees": rotation,
        "radius_inches": radius,
        "length_inches": length,
        "width_inches": width,
        "vertices": [] if vertices is None else vertices,
    }


def _conformance_point(x: float, y: float) -> JsonValue:
    return {"x_inches": x, "y_inches": y}


def _conformance_position(x: float, y: float, z: float) -> JsonValue:
    return {"x_inches": x, "y_inches": y, "z_inches": z}


def _conformance_pose(
    x: float,
    y: float,
    *,
    z: float = 0.0,
    facing: float,
) -> JsonValue:
    return {
        "position": _conformance_position(x, y, z),
        "facing_degrees": facing,
    }


def build_local_session_at_movement_request(
    *, game_id: str
) -> tuple[LocalGameSession, LifecycleStatus]:
    session, status = _fresh_started_session(game_id=game_id)
    status = _submit_fixed_secondary_choices(session=session, status=status, game_id=game_id)
    status = _submit_all_deployments(session=session, status=status, game_id=game_id)
    movement_request = _decision_request(status)
    _assert_decision_type(movement_request, SELECT_MOVEMENT_UNIT_DECISION_TYPE)
    return session, status


def _proposal_payload_examples() -> dict[str, JsonValue]:
    return {
        "charge_move.json": _charge_move_example_payload(),
        "deployment_placement.json": _deployment_placement_example_payload(),
        "melee_declaration.json": _melee_declaration_example_payload(),
        "movement_path_witness.json": _movement_path_witness_example_payload(),
        "opportunity_window.json": _opportunity_window_example_payload(),
        "shooting_target_selection.json": _shooting_declaration_example_payload(),
    }


def _deployment_placement_example_payload() -> JsonValue:
    session, status = _fresh_started_session(game_id="ui-contract-deployment-example")
    status = _submit_fixed_secondary_choices(
        session=session,
        status=status,
        game_id="ui-contract-deployment-example",
    )
    selection_request = _decision_request(status)
    _assert_decision_type(selection_request, SELECT_DEPLOYMENT_UNIT_DECISION_TYPE)
    placement_status = session.submit_option(
        request_id=selection_request.request_id,
        option_id=selection_request.options[0].option_id,
        result_id="ui-contract-deployment-example-unit",
    )
    placement_request = _decision_request(placement_status)
    _assert_decision_type(placement_request, SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE)
    return _deployment_placement_payload_for_request(placement_request)


def _movement_path_witness_example_payload() -> JsonValue:
    session, status = build_local_session_at_movement_request(
        game_id="ui-contract-movement-example"
    )
    movement_request = _decision_request(status)
    action_status = session.submit_option(
        request_id=movement_request.request_id,
        option_id=UNIT_ALPHA,
        result_id="ui-contract-movement-example-select-unit",
    )
    action_request = _decision_request(action_status)
    proposal_status = session.submit_option(
        request_id=action_request.request_id,
        option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        result_id="ui-contract-movement-example-select-action",
    )
    proposal_request = _decision_request(proposal_status)
    _assert_decision_type(proposal_request, MOVEMENT_PROPOSAL_DECISION_TYPE)
    request_context = MovementProposalRequest.from_decision_request_payload(
        proposal_request.payload
    )
    if request_context.movement_phase_action is None:
        raise GameLifecycleError("Movement proposal example requires action context.")
    witness = _unit_path_witness_from_view(
        view=session.view(viewer_player_id=PLAYER_A),
        unit_instance_id=request_context.unit_instance_id,
        delta_x=1.0,
    )
    return validate_json_value(
        MovementProposalPayload(
            proposal_request_id=request_context.request_id,
            proposal_kind=request_context.proposal_kind,
            unit_instance_id=request_context.unit_instance_id,
            movement_phase_action=request_context.movement_phase_action,
            witness=witness,
            movement_mode=MovementMode.NORMAL.value,
        ).to_payload()
    )


def _charge_move_example_payload() -> JsonValue:
    return validate_json_value(
        ChargeMoveProposal(
            proposal_request_id="ui-contract-charge-move-request-000001",
            proposal_kind=ProposalKind.CHARGE_MOVE,
            unit_instance_id=UNIT_ALPHA,
            movement_phase_action=CHARGE_MOVE_ACTION,
            movement_mode=MovementMode.CHARGE,
            charge_target_unit_instance_ids=(UNIT_BETA,),
            witness=PathWitness.for_straight_line_endpoints(
                (
                    (
                        MODEL_ALPHA_1,
                        Pose.at(30.0, 12.0, 0.0, facing_degrees=0.0),
                        Pose.at(36.0, 12.0, 0.0, facing_degrees=0.0),
                    ),
                )
            ),
        ).to_payload()
    )


def _shooting_declaration_example_payload() -> JsonValue:
    return validate_json_value(
        ShootingDeclarationProposal(
            proposal_request_id="ui-contract-shooting-declaration-request-000001",
            proposal_kind=SHOOTING_DECLARATION_PROPOSAL_KIND,
            player_id=PLAYER_A,
            battle_round=1,
            unit_instance_id=UNIT_ALPHA,
            source_decision_request_id="ui-contract-select-shooting-unit-request-000001",
            source_decision_result_id="ui-contract-select-shooting-unit-result-000001",
            declarations=(
                WeaponDeclaration(
                    attacker_model_instance_id=MODEL_ALPHA_1,
                    wargear_id="core-bolt-rifle",
                    weapon_profile_id="core-bolt-rifle:standard",
                    target_unit_instance_id=UNIT_BETA,
                    shooting_type=ShootingType.NORMAL,
                ),
            ),
            visibility_cache_key="ui-contract-visibility-cache-000001",
        ).to_payload()
    )


def _melee_declaration_example_payload() -> JsonValue:
    return validate_json_value(
        MeleeDeclarationProposal(
            proposal_request_id="ui-contract-melee-declaration-request-000001",
            proposal_kind=MELEE_DECLARATION_PROPOSAL_KIND,
            player_id=PLAYER_A,
            battle_round=1,
            unit_instance_id=UNIT_ALPHA,
            source_decision_request_id="ui-contract-fight-activation-request-000001",
            source_decision_result_id="ui-contract-fight-activation-result-000001",
            declarations=(
                MeleeWeaponDeclaration(
                    attacker_model_instance_id=MODEL_ALPHA_1,
                    wargear_id="core-close-combat-weapon",
                    weapon_profile_id="core-close-combat-weapon:standard",
                    target_allocations=(MeleeTargetAllocation(target_unit_instance_id=UNIT_BETA),),
                ),
            ),
        ).to_payload()
    )


def _opportunity_window_example_payload() -> JsonValue:
    pass_action = OpportunityLegalAction(
        action_id="decline_stratagem_window",
        source_id="core-rules:opportunity-window:pass",
        action_kind=OpportunityActionKind.PASS,
        controller_id=None,
        label="Decline",
        payload={"submission_kind": "decline_stratagem_window"},
    )
    command_reroll_action = OpportunityLegalAction(
        action_id="use-command-reroll",
        source_id="core-rules:stratagem:command-reroll",
        action_kind=OpportunityActionKind.REROLL,
        controller_id=PLAYER_A,
        label="Command Re-roll",
        cost=({"resource": "command_point", "amount": 1},),
        target_ids=("ui-contract-hit-roll-000001",),
        target_spec={
            "target_kind": "dice_roll",
            "roll_id": "ui-contract-hit-roll-000001",
        },
        payload={
            "stratagem_id": "core-command-reroll",
            "reroll_request_id": "ui-contract-reroll-request-000001",
        },
    )
    window = OpportunityWindow(
        window_id="ui-contract-opportunity-window-000001",
        timing_window=TimingWindow(
            window_id="ui-contract-opportunity-window-000001",
            descriptor=TimingWindowDescriptor(
                descriptor_id="ui-contract-opportunity-window-000001:descriptor",
                trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
                source_rule_id="core-rules:stratagem:command-reroll",
                phase=BattlePhaseKind.SHOOTING,
                metadata={"roll_kind": "hit_roll"},
            ),
            game_id="ui-contract-opportunity-example",
            battle_round=1,
            active_player_id=PLAYER_A,
            phase=BattlePhaseKind.SHOOTING,
            trigger_event_id="ui-contract-hit-roll-event-000001",
        ),
        state_hash="ui-contract-opportunity-state-hash-000001",
        sequence_number=12,
        revision=1,
        anchor_event_ids=("ui-contract-hit-roll-event-000001",),
        acting_player_id=PLAYER_A,
        eligible_player_ids=(PLAYER_A,),
        priority_order=(PLAYER_A,),
        legal_actions=(pass_action, command_reroll_action),
        default_action_id=pass_action.action_id,
        metadata={"host": "command_reroll"},
    )
    request = window.decision_request(
        request_id="ui-contract-opportunity-request-000001",
        actor_id=PLAYER_A,
        decision_type="use_stratagem",
    )
    selected_action = window.action_by_id(command_reroll_action.action_id)
    return validate_json_value(
        {
            "decision_request": request.to_payload(),
            "selected_option_id": selected_action.action_id,
            "selected_option_payload": window.submission_payload_for_action(
                action=selected_action,
                player_id=PLAYER_A,
                legal_action_fingerprint=window.legal_action_fingerprint(PLAYER_A),
            ),
        }
    )


def _submit_fixed_secondary_choices(
    *,
    session: LocalGameSession,
    status: LifecycleStatus,
    game_id: str,
) -> LifecycleStatus:
    current = status
    for result_suffix in ("secondary-a", "secondary-b"):
        request = _decision_request(current)
        _assert_decision_type(request, SECONDARY_MISSION_DECISION_TYPE)
        current = session.submit_option(
            request_id=request.request_id,
            option_id=FIXED_SECONDARY_OPTION_ID,
            result_id=f"{game_id}-{result_suffix}",
        )
    return current


def _submit_all_deployments(
    *,
    session: LocalGameSession,
    status: LifecycleStatus,
    game_id: str,
) -> LifecycleStatus:
    current = status
    result_number = 1
    while current.decision_request is not None and current.decision_request.decision_type in {
        SELECT_DEPLOYMENT_UNIT_DECISION_TYPE,
        SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE,
    }:
        request = current.decision_request
        result_id = f"{game_id}-deploy-{result_number:06d}"
        if request.decision_type == SELECT_DEPLOYMENT_UNIT_DECISION_TYPE:
            current = session.submit_option(
                request_id=request.request_id,
                option_id=request.options[0].option_id,
                result_id=result_id,
            )
        else:
            current = session.submit_parameterized_payload(
                request_id=request.request_id,
                payload=_deployment_placement_payload_for_request(request),
                result_id=result_id,
            )
        result_number += 1
    return current


def _deployment_placement_payload_for_request(request: DecisionRequest) -> dict[str, JsonValue]:
    _assert_decision_type(request, SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE)
    request_context = DeploymentPlacementRequest.from_decision_request_payload(request.payload)
    placements: list[ModelPlacement] = []
    army_id = _army_id_from_unit_id(request_context.unit_instance_id)
    for index, model_instance_id in enumerate(request_context.model_instance_ids):
        placements.append(
            ModelPlacement(
                army_id=army_id,
                player_id=request_context.player_id,
                unit_instance_id=request_context.unit_instance_id,
                model_instance_id=model_instance_id,
                pose=_default_deployment_pose(
                    index=index,
                    player_id=request_context.player_id,
                    unit_instance_id=request_context.unit_instance_id,
                ),
            )
        )
    payload = validate_json_value(
        DeploymentPlacementProposal(
            proposal_request_id=request_context.request_id,
            proposal_kind=request_context.proposal_kind,
            game_id=request_context.game_id,
            ruleset_descriptor_hash=request_context.ruleset_descriptor_hash,
            setup_step=SetupStep.DEPLOY_ARMIES,
            player_id=request_context.player_id,
            unit_instance_id=request_context.unit_instance_id,
            placement_kind=BattlefieldPlacementKind.DEPLOYMENT,
            model_placements=tuple(placements),
            context=request_context.context,
        ).to_payload()
    )
    if not isinstance(payload, dict):
        raise GameLifecycleError("Deployment placement example must be a JSON object.")
    return payload


def _unit_path_witness_from_view(
    *,
    view: GameViewPayload,
    unit_instance_id: str,
    delta_x: float,
) -> PathWitness:
    unit_placement = _unit_placement_from_view(view=view, unit_instance_id=unit_instance_id)
    model_placements = _json_list(unit_placement, key="model_placements")
    endpoints: list[tuple[str, Pose, Pose]] = []
    for model_placement_value in model_placements:
        model_placement = _json_object("model placement", model_placement_value)
        model_id = _json_string(model_placement, key="model_instance_id")
        start_pose = Pose.from_payload(cast(PosePayload, model_placement["pose"]))
        endpoints.append(
            (
                model_id,
                start_pose,
                Pose.at(
                    start_pose.position.x + delta_x,
                    start_pose.position.y,
                    start_pose.position.z,
                    facing_degrees=start_pose.facing.degrees,
                ),
            )
        )
    return PathWitness.for_straight_line_endpoints(tuple(endpoints))


def _unit_placement_from_view(
    *,
    view: GameViewPayload,
    unit_instance_id: str,
) -> dict[str, JsonValue]:
    battlefield = _json_object("battlefield_state", view["battlefield_state"])
    for placed_army_value in _json_list(battlefield, key="placed_armies"):
        placed_army = _json_object("placed army", placed_army_value)
        for unit_placement_value in _json_list(placed_army, key="unit_placements"):
            unit_placement = _json_object("unit placement", unit_placement_value)
            if unit_placement.get("unit_instance_id") == unit_instance_id:
                return unit_placement
    raise GameLifecycleError("Unit placement not found in projected battlefield state.")


def _inject_fixture_movement_modifier(
    session: LocalGameSession,
    *,
    modifier_id: str,
    movement: int,
) -> None:
    state = _session_state(session)
    _replace_first_model(
        state,
        _model_with_movement_modifier(
            _first_model(state),
            modifier_id=modifier_id,
            movement=movement,
        ),
    )


def _model_with_movement_modifier(
    model: ModelInstance,
    *,
    modifier_id: str,
    movement: int,
) -> ModelInstance:
    characteristics: list[CharacteristicValue] = []
    for value in model.characteristics:
        if value.characteristic is Characteristic.MOVEMENT:
            characteristics.append(
                CharacteristicValue(
                    characteristic=value.characteristic,
                    raw=value.raw,
                    base=value.base,
                    final=movement,
                    applied_modifier_ids=(modifier_id,),
                    value_kind=value.value_kind,
                )
            )
            continue
        characteristics.append(value)
    return replace(model, characteristics=tuple(characteristics))


def _replace_first_model(state: GameState, model: ModelInstance) -> None:
    army = state.army_definitions[0]
    unit = army.units[0]
    updated_unit = replace(unit, own_models=(model, *unit.own_models[1:]))
    updated_army = replace(army, units=(updated_unit, *army.units[1:]))
    state.army_definitions = [updated_army, *state.army_definitions[1:]]


def _first_model(state: GameState) -> ModelInstance:
    return state.army_definitions[0].units[0].own_models[0]


def _session_state(session: LocalGameSession) -> GameState:
    # WS5 fixture-authoring exemption: this script mutates authoritative state only to
    # synthesize stable UI projection fixtures, never as an adapter runtime path.
    state = session.lifecycle.state
    if state is None:
        raise GameLifecycleError("UI contract fixture session must be started.")
    return state


def _fresh_started_session(*, game_id: str) -> tuple[LocalGameSession, LifecycleStatus]:
    session = LocalGameSession()
    session.start(_config(game_id=game_id))
    return session, session.advance_until_decision_or_terminal()


def _config(*, game_id: str) -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id=game_id,
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-ui-contract-fixtures"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id=PLAYER_A,
                army_id=ARMY_ALPHA,
                unit_selection_id="intercessor-unit-1",
            ),
            _army_muster_request(
                catalog=catalog,
                player_id=PLAYER_B,
                army_id=ARMY_BETA,
                unit_selection_id="intercessor-unit-2",
            ),
        ),
        player_ids=(PLAYER_A, PLAYER_B),
        turn_order=(PLAYER_A, PLAYER_B),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=MissionSetup.from_mission_pack(
            mission_pack=chapter_approved_2026_27_mission_pack(),
            mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
            terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
            attacker_player_id=PLAYER_A,
            defender_player_id=PLAYER_B,
        ),
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_id: str,
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        force_disposition_id="purge-the-foe",
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
        ),
    )


def _default_deployment_pose(
    *,
    index: int,
    player_id: str,
    unit_instance_id: str,
) -> Pose:
    row = index // 3
    column = index % 3
    base_y = _deployment_base_y_for_unit(unit_instance_id)
    if player_id == PLAYER_B:
        return Pose.at(57.0 - (row * 1.8), base_y + (column * 1.8), 0.0, facing_degrees=180.0)
    return Pose.at(3.0 + (row * 1.8), base_y + (column * 1.8), 0.0, facing_degrees=0.0)


def _deployment_base_y_for_unit(unit_instance_id: str) -> float:
    slots = (24.0, 3.0, 13.5, 32.0)
    return slots[_unit_slot(unit_instance_id) % len(slots)]


def _unit_slot(unit_instance_id: str) -> int:
    digits = ""
    for character in reversed(unit_instance_id):
        if character.isdigit():
            digits = f"{character}{digits}"
            continue
        if digits:
            break
    if not digits:
        return 0
    return max(int(digits) - 1, 0)


def _army_id_from_unit_id(unit_instance_id: str) -> str:
    if ":" not in unit_instance_id:
        raise GameLifecycleError("UI contract fixture unit_instance_id must include army prefix.")
    return unit_instance_id.split(":", 1)[0]


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    if status.status_kind is not LifecycleStatusKind.WAITING_FOR_DECISION:
        raise GameLifecycleError("UI contract fixture expected a pending DecisionRequest.")
    if status.decision_request is None:
        raise GameLifecycleError("UI contract fixture status is missing DecisionRequest.")
    return status.decision_request


def _assert_decision_type(request: DecisionRequest, decision_type: str) -> None:
    if request.decision_type != decision_type:
        raise GameLifecycleError(f"Expected {decision_type} request, got {request.decision_type}.")


def _json_object(field_name: str, value: JsonValue) -> dict[str, JsonValue]:
    payload = validate_json_value(value)
    if not isinstance(payload, dict):
        raise GameLifecycleError(f"{field_name} must be a JSON object.")
    return payload


def _json_list(payload: dict[str, JsonValue], *, key: str) -> list[JsonValue]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise GameLifecycleError(f"{key} must be a JSON list.")
    return value


def _json_string(payload: dict[str, JsonValue], *, key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"{key} must be a string.")
    return value


def _write_json(path: Path, payload: JsonValue) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(validate_json_value(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
