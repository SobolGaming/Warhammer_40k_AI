"""Shared Order 59 empty Dedicated Transport fixtures."""

from __future__ import annotations

from dataclasses import replace

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import DatasheetKeywordSet
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import (
    ArmyMusterRequest,
    DedicatedTransportCapacityProfile,
    DedicatedTransportManifest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import DetachmentSelection, UnitMusterSelection
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import LifecycleStatus, SetupStep
from warhammer40k_core.engine.reserve_declarations import SELECT_RESERVE_DECLARATION_DECISION_TYPE
from warhammer40k_core.engine.reserves import ReserveUnitPointValue
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack

EMPTY_DEDICATED_TRANSPORTS_DESTROYED_EVENT_TYPE = "empty_dedicated_transports_destroyed"
ORDER59_EMPTY_TRANSPORT_UNIT_ID = "army-alpha:transport-unit"
ORDER59_CARGO_TRANSPORT_UNIT_ID = "army-alpha:cargo-transport"
COMPLETE_RESERVE_DECLARATIONS_OPTION_ID = "complete_reserve_declarations"


def order59_empty_transport_config(
    *,
    game_id: str = "order59-empty-transport",
    include_cargo_transport: bool = False,
) -> GameConfig:
    catalog = _dedicated_transport_catalog()
    player_a_units = [
        _unit_selection(
            unit_selection_id="transport-unit",
            datasheet_id="core-transport",
            model_profile_id="core-transport",
            model_count=1,
        ),
        _unit_selection(unit_selection_id="bodyguard-unit"),
        _unit_selection(unit_selection_id="reserve-unit"),
    ]
    manifests = [
        DedicatedTransportManifest(
            transport_unit_selection_id="transport-unit",
            embarked_unit_selection_ids=(),
            capacity_profile=_transport_capacity(),
            source_id="manifest:empty",
        )
    ]
    if include_cargo_transport:
        player_a_units.append(
            _unit_selection(
                unit_selection_id="cargo-transport",
                datasheet_id="core-transport",
                model_profile_id="core-transport",
                model_count=1,
            )
        )
        manifests.append(
            DedicatedTransportManifest(
                transport_unit_selection_id="cargo-transport",
                embarked_unit_selection_ids=("bodyguard-unit",),
                capacity_profile=_transport_capacity(),
                source_id="manifest:cargo",
            )
        )
    return GameConfig(
        game_id=game_id,
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-order59-test"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            ArmyMusterRequest(
                army_id="army-alpha",
                player_id="player-a",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id="core-marine-force",
                    detachment_ids=("core-combined-arms",),
                ),
                force_disposition_id="take-and-hold",
                unit_selections=tuple(player_a_units),
                dedicated_transport_manifests=tuple(manifests),
            ),
            ArmyMusterRequest(
                army_id="army-beta",
                player_id="player-b",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id="core-marine-force",
                    detachment_ids=("core-combined-arms",),
                ),
                force_disposition_id="purge-the-foe",
                unit_selections=(_unit_selection(unit_selection_id="intercessor-unit-2"),),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        reserve_unit_points=(
            ReserveUnitPointValue(
                unit_instance_id="army-alpha:reserve-unit",
                points=100,
                source_id="order59-reserve-points",
            ),
        ),
        mission_setup=MissionSetup.from_mission_pack(
            mission_pack=chapter_approved_2026_27_mission_pack(),
            mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
            terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
            attacker_player_id="player-a",
            attacker_force_disposition_id="take-and-hold",
            defender_player_id="player-b",
            defender_force_disposition_id="purge-the-foe",
        ),
    )


def order59_lifecycle_at_reserve_request(
    *,
    game_id: str = "order59-empty-transport",
    include_cargo_transport: bool = False,
) -> tuple[GameLifecycle, LifecycleStatus]:
    lifecycle = GameLifecycle()
    lifecycle.start(
        order59_empty_transport_config(
            game_id=game_id,
            include_cargo_transport=include_cargo_transport,
        )
    )
    status = lifecycle.advance_until_decision_or_terminal()
    status = _resolve_secondary_missions(lifecycle, status)
    request = status.decision_request
    assert request is not None
    assert request.decision_type == SELECT_RESERVE_DECLARATION_DECISION_TYPE, request.decision_type
    return lifecycle, status


def complete_order59_declare_battle_formations(
    lifecycle: GameLifecycle,
    status: LifecycleStatus,
    *,
    result_id_prefix: str = "order59-complete-reserves",
) -> LifecycleStatus:
    result_index = 1
    while (
        status.decision_request is not None
        and status.decision_request.decision_type == SELECT_RESERVE_DECLARATION_DECISION_TYPE
    ):
        request = status.decision_request
        status = lifecycle.submit_decision(
            DecisionResult.for_request(
                result_id=f"{result_id_prefix}-{result_index:02d}",
                request=request,
                selected_option_id=COMPLETE_RESERVE_DECLARATIONS_OPTION_ID,
            )
        )
        result_index += 1
    return status


def order59_lifecycle_after_declare_battle_formations(
    *,
    game_id: str = "order59-empty-transport",
    include_cargo_transport: bool = False,
) -> GameLifecycle:
    lifecycle, status = order59_lifecycle_at_reserve_request(
        game_id=game_id,
        include_cargo_transport=include_cargo_transport,
    )
    complete_order59_declare_battle_formations(lifecycle, status)
    assert lifecycle.state is not None
    assert lifecycle.state.current_setup_step is SetupStep.DEPLOY_ARMIES
    return lifecycle


def order59_transport_unit(state: GameState, unit_instance_id: str) -> UnitInstance:
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                return unit
    raise AssertionError(f"missing unit {unit_instance_id}")


def order59_destruction_events(lifecycle: GameLifecycle) -> tuple[EventRecord, ...]:
    return tuple(
        event
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == EMPTY_DEDICATED_TRANSPORTS_DESTROYED_EVENT_TYPE
    )


def _resolve_secondary_missions(
    lifecycle: GameLifecycle,
    status: LifecycleStatus,
) -> LifecycleStatus:
    result_index = 1
    while (
        status.decision_request is not None
        and status.decision_request.decision_type == SECONDARY_MISSION_DECISION_TYPE
    ):
        request = status.decision_request
        status = lifecycle.submit_decision(
            DecisionResult.for_request(
                result_id=f"order59-secondary-{result_index:02d}",
                request=request,
                selected_option_id="tactical",
            )
        )
        result_index += 1
    return status


def _dedicated_transport_catalog() -> ArmyCatalog:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    datasheets = tuple(
        replace(
            datasheet,
            keywords=DatasheetKeywordSet(
                keywords=("Dedicated Transport", "Transport", "Vehicle")
                if datasheet.datasheet_id == "core-transport"
                else datasheet.keywords.keywords,
                faction_keywords=datasheet.keywords.faction_keywords,
            ),
        )
        for datasheet in catalog.datasheets
    )
    return replace(catalog, datasheets=datasheets)


def _transport_capacity() -> DedicatedTransportCapacityProfile:
    return DedicatedTransportCapacityProfile(
        transport_datasheet_id="core-transport",
        max_model_count=6,
        allowed_keywords=("Infantry",),
        excluded_keywords=(),
        source_id="transport-capacity:core-transport:6",
    )


def _unit_selection(
    *,
    unit_selection_id: str,
    datasheet_id: str = "core-intercessor-like-infantry",
    model_profile_id: str = "core-intercessor-like",
    model_count: int = 5,
) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id=datasheet_id,
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id=model_profile_id,
                model_count=model_count,
            ),
        ),
    )


def typed_state(lifecycle: GameLifecycle) -> GameState:
    state = lifecycle.state
    assert state is not None
    return state
