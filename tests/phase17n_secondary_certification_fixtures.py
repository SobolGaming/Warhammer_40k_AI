from __future__ import annotations

from dataclasses import dataclass

from tests.phase11c_command_phase_helpers import default_unit_selection, unit_selection
from tests.phase17n_secondary_mission_helpers import resolved_secondary_mission_selection_for_card
from tests.secondary_destruction_helpers import record_secondary_destruction_for_fixture
from warhammer40k_core.core.battlefield_regions import BattlefieldRegionKind
from warhammer40k_core.core.missions import ObjectiveMarkerDefinition, ObjectiveMarkerRole
from warhammer40k_core.engine.actions import MissionActionState
from warhammer40k_core.engine.battlefield_state import ModelPlacement
from warhammer40k_core.engine.event_log import EventLog
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.list_validation import UnitMusterSelection
from warhammer40k_core.engine.mission_terrain import (
    MissionLogicalTerrainArea,
    logical_terrain_area_within_player_territory,
    mission_logical_terrain_areas,
)
from warhammer40k_core.engine.missions import mission_pack_for_id
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.primary_scoring_spatial_evidence import (
    TABLE_QUARTER_NORTH_EAST,
    TABLE_QUARTER_NORTH_WEST,
    TABLE_QUARTER_SOUTH_EAST,
    TABLE_QUARTER_SOUTH_WEST,
)
from warhammer40k_core.engine.scoring import SecondaryMissionCardMode
from warhammer40k_core.engine.secondary_scoring_inventory import (
    SecondaryMissionLifecycleCertificationRow,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose

_OPPONENT_TURN_CARD_IDS = frozenset(
    {
        "beacon",
        "burden-of-trust",
        "defend-stronghold",
    }
)
TURN_CAP_TACTICAL_IDS = (
    "a-tempting-target",
    "centre-ground",
    "plunder",
    "behind-enemy-lines",
)
_QUARTER_IDS = (
    TABLE_QUARTER_NORTH_WEST,
    TABLE_QUARTER_NORTH_EAST,
    TABLE_QUARTER_SOUTH_WEST,
    TABLE_QUARTER_SOUTH_EAST,
)


@dataclass(frozen=True, slots=True)
class SecondaryPositiveExpectation:
    expected_amount: int
    expected_rule_ids: frozenset[str]
    opponent_turn: bool


def certification_unit_selections(*, player_id: str) -> tuple[UnitMusterSelection, ...]:
    prefix = "a" if player_id == "player-a" else "b"
    return (
        default_unit_selection(f"intercessor-unit-{prefix}1"),
        default_unit_selection(f"intercessor-unit-{prefix}2"),
        default_unit_selection(f"intercessor-unit-{prefix}3"),
        default_unit_selection(f"intercessor-unit-{prefix}4"),
        unit_selection(
            unit_selection_id=f"character-unit-{prefix}",
            datasheet_id="core-character-leader",
            model_profile_id="core-character-leader",
            model_count=1,
        ),
        unit_selection(
            unit_selection_id=f"vehicle-unit-{prefix}",
            datasheet_id="core-vehicle-monster",
            model_profile_id="core-vehicle-monster",
            model_count=1,
        ),
        unit_selection(
            unit_selection_id=f"horde-unit-{prefix}",
            datasheet_id="core-boyz-like-infantry",
            model_profile_id="core-boyz-like",
            model_count=20,
        ),
    )


def certification_unit_selections_for_row(
    row: SecondaryMissionLifecycleCertificationRow,
    *,
    player_id: str,
) -> tuple[UnitMusterSelection, ...]:
    if row.secondary_mission_id not in {*_DESTRUCTION_SEEDERS, *_SEEDERS}:
        raise AssertionError(
            "Step 6G matrix roster has no fixture for Secondary mission "
            f"{row.secondary_mission_id}."
        )
    if player_id not in {"player-a", "player-b"}:
        raise AssertionError(f"Step 6G matrix roster has unsupported player {player_id}.")

    scoring_intercessor_counts = {
        "engage-on-all-fronts": 4,
        "outflank": 2,
        "secure-no-mans-land": 2,
    }
    intercessor_count = (
        scoring_intercessor_counts.get(row.secondary_mission_id, 1)
        if player_id == row.scoring_player_id
        else 1
    )
    prefix = "a" if player_id == "player-a" else "b"
    selections = tuple(
        default_unit_selection(f"intercessor-unit-{prefix}{index}")
        for index in range(1, intercessor_count + 1)
    )
    if player_id == row.scoring_player_id:
        return selections

    destruction_target_specs = {
        "a-grievous-blow": (
            "horde-unit",
            "core-boyz-like-infantry",
            "core-boyz-like",
            20,
        ),
        "assassination": (
            "character-unit",
            "core-character-leader",
            "core-character-leader",
            1,
        ),
        "bring-it-down": (
            "vehicle-unit",
            "core-vehicle-monster",
            "core-vehicle-monster",
            1,
        ),
        "no-prisoners": (
            "vehicle-unit",
            "core-vehicle-monster",
            "core-vehicle-monster",
            1,
        ),
        "overwhelming-force": (
            "vehicle-unit",
            "core-vehicle-monster",
            "core-vehicle-monster",
            1,
        ),
    }
    target_spec = destruction_target_specs.get(row.secondary_mission_id)
    if target_spec is None:
        return selections
    selection_prefix, datasheet_id, model_profile_id, model_count = target_spec
    return (
        *selections,
        unit_selection(
            unit_selection_id=f"{selection_prefix}-{prefix}",
            datasheet_id=datasheet_id,
            model_profile_id=model_profile_id,
            model_count=model_count,
        ),
    )


def active_player_id_for_row(row: SecondaryMissionLifecycleCertificationRow) -> str:
    if row.secondary_mission_id in _OPPONENT_TURN_CARD_IDS:
        return opponent_player_id(row.scoring_player_id)
    return row.scoring_player_id


def opponent_player_id(player_id: str) -> str:
    if player_id == "player-a":
        return "player-b"
    return "player-a"


def seed_positive_secondary_condition(
    state: GameState,
    row: SecondaryMissionLifecycleCertificationRow,
    *,
    event_log: EventLog | None = None,
) -> SecondaryPositiveExpectation:
    _park_units_in_safe_zones(state, scoring_player_id=row.scoring_player_id)
    destruction_seeder = _DESTRUCTION_SEEDERS.get(row.secondary_mission_id)
    expectation = (
        _SEEDERS[row.secondary_mission_id](state, row)
        if destruction_seeder is None
        else destruction_seeder(state, row, event_log)
    )
    _bind_card_selection(state, row)
    return expectation


def seed_sequential_tactical_turn_cap_conditions(state: GameState) -> None:
    scoring_player_id = "player-a"
    _park_units_in_safe_zones(state, scoring_player_id=scoring_player_id)
    tempting_marker = _no_mans_land_non_home_markers(state, player_id=scoring_player_id)[0]
    intercessors = _intercessors(state, player_id=scoring_player_id)
    _place_unit_at(
        state,
        intercessors[0].unit_instance_id,
        tempting_marker.x_inches,
        tempting_marker.y_inches,
    )
    assert state.mission_setup is not None
    _place_unit_at(
        state,
        intercessors[1].unit_instance_id,
        state.mission_setup.battlefield_width_inches / 2.0,
        state.mission_setup.battlefield_depth_inches / 2.0,
    )
    area = _first_plunderable_area(state, player_id=scoring_player_id)
    _record_plunder(
        state,
        player_id=scoring_player_id,
        terrain_feature_id=area.logical_terrain_area_id,
    )
    opponent_home = _home_marker(state, player_id=opponent_player_id(scoring_player_id))
    _place_unit_at(
        state,
        intercessors[2].unit_instance_id,
        opponent_home.x_inches,
        opponent_home.y_inches,
    )
    tempting_card = state.secondary_mission_card_state(
        player_id=scoring_player_id,
        secondary_mission_id="a-tempting-target",
        mode=SecondaryMissionCardMode.TACTICAL,
    )
    if tempting_card is None:
        raise AssertionError("Sequential Secondary turn-cap fixture is missing Tempting Target.")
    _rebind_tempting_target(
        state,
        SecondaryMissionLifecycleCertificationRow(
            secondary_mission_id="a-tempting-target",
            mode="tactical",
            scoring_player_id=scoring_player_id,
            layout_id="layout-a",
        ),
    )


def _park_units_in_safe_zones(state: GameState, *, scoring_player_id: str) -> None:
    own_home = _home_marker(state, player_id=scoring_player_id)
    opponent_home = _home_marker(state, player_id=opponent_player_id(scoring_player_id))
    for unit in _units_for_player(state, scoring_player_id):
        _place_unit_at(state, unit.unit_instance_id, own_home.x_inches, own_home.y_inches)
    for unit in _units_for_player(state, opponent_player_id(scoring_player_id)):
        _place_unit_at(
            state,
            unit.unit_instance_id,
            opponent_home.x_inches,
            opponent_home.y_inches,
        )


def _bind_card_selection(
    state: GameState,
    row: SecondaryMissionLifecycleCertificationRow,
) -> None:
    mode = (
        SecondaryMissionCardMode.FIXED if row.mode == "fixed" else SecondaryMissionCardMode.TACTICAL
    )
    card = state.secondary_mission_card_state(
        player_id=row.scoring_player_id,
        secondary_mission_id=row.secondary_mission_id,
        mode=mode,
    )
    if card is None:
        raise AssertionError("Step 6G positive fixture is missing its certified card.")
    state.replace_secondary_mission_card_state(
        card.with_selection(resolved_secondary_mission_selection_for_card(state, card))
    )
    if row.secondary_mission_id == "a-tempting-target":
        _rebind_tempting_target(state, row)
    elif row.secondary_mission_id == "beacon":
        _rebind_beacon(state, row)
    elif row.secondary_mission_id == "burden-of-trust":
        _rebind_burden(state, row)


def _seed_grievous(
    state: GameState,
    row: SecondaryMissionLifecycleCertificationRow,
    event_log: EventLog | None,
) -> SecondaryPositiveExpectation:
    horde = _unit_by_datasheet(
        state,
        player_id=opponent_player_id(row.scoring_player_id),
        datasheet_id="core-boyz-like-infantry",
    )
    _record_destruction(state, destroyed_unit=horde, event_log=event_log)
    rule_id = "a-grievous-blow-fixed" if row.mode == "fixed" else "a-grievous-blow-tactical"
    amount = 4 if row.mode == "fixed" else 5
    return SecondaryPositiveExpectation(
        expected_amount=amount,
        expected_rule_ids=frozenset({rule_id}),
        opponent_turn=False,
    )


def _seed_tempting(
    state: GameState,
    row: SecondaryMissionLifecycleCertificationRow,
) -> SecondaryPositiveExpectation:
    marker = _no_mans_land_non_home_markers(state, player_id=row.scoring_player_id)[0]
    unit = _intercessors(state, player_id=row.scoring_player_id)[0]
    _place_unit_at(state, unit.unit_instance_id, marker.x_inches, marker.y_inches)
    return SecondaryPositiveExpectation(
        expected_amount=5,
        expected_rule_ids=frozenset({"a-tempting-target-tactical"}),
        opponent_turn=False,
    )


def _seed_assassination(
    state: GameState,
    row: SecondaryMissionLifecycleCertificationRow,
    event_log: EventLog | None,
) -> SecondaryPositiveExpectation:
    character = _unit_by_datasheet(
        state,
        player_id=opponent_player_id(row.scoring_player_id),
        datasheet_id="core-character-leader",
    )
    _record_destruction(state, destroyed_unit=character, event_log=event_log)
    if row.mode == "fixed":
        return SecondaryPositiveExpectation(
            expected_amount=4,
            expected_rule_ids=frozenset(
                {
                    "assassination-fixed-character-destroyed",
                    "assassination-fixed-character-w4-plus",
                }
            ),
            opponent_turn=False,
        )
    return SecondaryPositiveExpectation(
        expected_amount=5,
        expected_rule_ids=frozenset({"assassination-tactical-all-characters-destroyed"}),
        opponent_turn=False,
    )


def _seed_beacon(
    state: GameState,
    row: SecondaryMissionLifecycleCertificationRow,
) -> SecondaryPositiveExpectation:
    marker = _home_marker(state, player_id=opponent_player_id(row.scoring_player_id))
    unit = _intercessors(state, player_id=row.scoring_player_id)[0]
    _place_unit_at(state, unit.unit_instance_id, marker.x_inches, marker.y_inches)
    return SecondaryPositiveExpectation(
        expected_amount=5,
        expected_rule_ids=frozenset({"beacon-source-outside-territory"}),
        opponent_turn=True,
    )


def _seed_behind_enemy_lines(
    state: GameState,
    row: SecondaryMissionLifecycleCertificationRow,
) -> SecondaryPositiveExpectation:
    marker = _home_marker(state, player_id=opponent_player_id(row.scoring_player_id))
    unit = _intercessors(state, player_id=row.scoring_player_id)[0]
    _place_unit_at(state, unit.unit_instance_id, marker.x_inches, marker.y_inches)
    return SecondaryPositiveExpectation(
        expected_amount=3,
        expected_rule_ids=frozenset({"behind-enemy-lines-source-each-unit"}),
        opponent_turn=False,
    )


def _seed_bring_it_down(
    state: GameState,
    row: SecondaryMissionLifecycleCertificationRow,
    event_log: EventLog | None,
) -> SecondaryPositiveExpectation:
    vehicle = _unit_by_datasheet(
        state,
        player_id=opponent_player_id(row.scoring_player_id),
        datasheet_id="core-vehicle-monster",
    )
    _record_destruction(state, destroyed_unit=vehicle, event_log=event_log)
    rule_id = "bring-it-down-fixed" if row.mode == "fixed" else "bring-it-down-tactical"
    amount = 4 if row.mode == "fixed" else 5
    return SecondaryPositiveExpectation(
        expected_amount=amount,
        expected_rule_ids=frozenset({rule_id}),
        opponent_turn=False,
    )


def _seed_burden(
    state: GameState,
    row: SecondaryMissionLifecycleCertificationRow,
) -> SecondaryPositiveExpectation:
    marker = _home_marker(state, player_id=row.scoring_player_id)
    unit = _intercessors(state, player_id=row.scoring_player_id)[0]
    _place_unit_at(state, unit.unit_instance_id, marker.x_inches, marker.y_inches)
    return SecondaryPositiveExpectation(
        expected_amount=2,
        expected_rule_ids=frozenset({"burden-of-trust-source-each-guarded-objective"}),
        opponent_turn=True,
    )


def _seed_centre_ground(
    state: GameState,
    row: SecondaryMissionLifecycleCertificationRow,
) -> SecondaryPositiveExpectation:
    assert state.mission_setup is not None
    unit = _intercessors(state, player_id=row.scoring_player_id)[0]
    _place_unit_at(
        state,
        unit.unit_instance_id,
        state.mission_setup.battlefield_width_inches / 2.0,
        state.mission_setup.battlefield_depth_inches / 2.0,
    )
    return SecondaryPositiveExpectation(
        expected_amount=5,
        expected_rule_ids=frozenset({"centre-ground-source-no-enemy-within-six"}),
        opponent_turn=False,
    )


def _seed_cleanse(
    state: GameState,
    row: SecondaryMissionLifecycleCertificationRow,
) -> SecondaryPositiveExpectation:
    marker = _no_mans_land_non_home_markers(state, player_id=row.scoring_player_id)[0]
    _record_cleanse(
        state,
        player_id=row.scoring_player_id,
        objective_marker_id=marker.objective_marker_id,
    )
    return SecondaryPositiveExpectation(
        expected_amount=2,
        expected_rule_ids=frozenset({"cleanse-tactical-one-objective"}),
        opponent_turn=False,
    )


def _seed_defend_stronghold(
    state: GameState,
    row: SecondaryMissionLifecycleCertificationRow,
) -> SecondaryPositiveExpectation:
    marker = _home_marker(state, player_id=row.scoring_player_id)
    unit = _intercessors(state, player_id=row.scoring_player_id)[0]
    _place_unit_at(state, unit.unit_instance_id, marker.x_inches, marker.y_inches)
    return SecondaryPositiveExpectation(
        expected_amount=5,
        expected_rule_ids=frozenset(
            {
                "defend-stronghold-home-objective",
                "defend-stronghold-no-enemy-in-deployment-zone",
            }
        ),
        opponent_turn=True,
    )


def _seed_display_of_might(
    state: GameState,
    row: SecondaryMissionLifecycleCertificationRow,
) -> SecondaryPositiveExpectation:
    marker = _no_mans_land_non_home_markers(state, player_id=row.scoring_player_id)[0]
    unit = _intercessors(state, player_id=row.scoring_player_id)[0]
    _place_unit_at(state, unit.unit_instance_id, marker.x_inches, marker.y_inches)
    return SecondaryPositiveExpectation(
        expected_amount=2,
        expected_rule_ids=frozenset({"display-of-might-source-your-turn"}),
        opponent_turn=False,
    )


def _seed_engage(
    state: GameState,
    row: SecondaryMissionLifecycleCertificationRow,
) -> SecondaryPositiveExpectation:
    assert state.mission_setup is not None
    width = state.mission_setup.battlefield_width_inches
    depth = state.mission_setup.battlefield_depth_inches
    anchors = {
        TABLE_QUARTER_NORTH_WEST: (width * 0.25, depth * 0.75),
        TABLE_QUARTER_NORTH_EAST: (width * 0.75, depth * 0.75),
        TABLE_QUARTER_SOUTH_WEST: (width * 0.25, depth * 0.25),
        TABLE_QUARTER_SOUTH_EAST: (width * 0.75, depth * 0.25),
    }
    for unit, quarter_id in zip(
        _intercessors(state, player_id=row.scoring_player_id),
        _QUARTER_IDS,
        strict=True,
    ):
        x_inches, y_inches = anchors[quarter_id]
        _place_unit_at(state, unit.unit_instance_id, x_inches, y_inches)
    if row.mode == "fixed":
        return SecondaryPositiveExpectation(
            expected_amount=4,
            expected_rule_ids=frozenset({"engage-on-all-fronts-fixed-four-quarters"}),
            opponent_turn=False,
        )
    return SecondaryPositiveExpectation(
        expected_amount=5,
        expected_rule_ids=frozenset({"engage-on-all-fronts-tactical-four-quarters"}),
        opponent_turn=False,
    )


def _seed_forward_position(
    state: GameState,
    row: SecondaryMissionLifecycleCertificationRow,
) -> SecondaryPositiveExpectation:
    opponent_id = opponent_player_id(row.scoring_player_id)
    scoring_home = _home_marker(state, player_id=row.scoring_player_id)
    opponent_home = _home_marker(state, player_id=opponent_id)
    for unit in _units_for_player(state, opponent_id):
        _place_unit_at(
            state,
            unit.unit_instance_id,
            scoring_home.x_inches,
            scoring_home.y_inches,
        )
    scoring_unit = _intercessors(state, player_id=row.scoring_player_id)[0]
    _place_unit_at(
        state,
        scoring_unit.unit_instance_id,
        opponent_home.x_inches,
        opponent_home.y_inches,
    )
    return SecondaryPositiveExpectation(
        expected_amount=5,
        expected_rule_ids=frozenset({"forward-position-source-control-forward-objective"}),
        opponent_turn=False,
    )


def _seed_no_prisoners(
    state: GameState,
    row: SecondaryMissionLifecycleCertificationRow,
    event_log: EventLog | None,
) -> SecondaryPositiveExpectation:
    vehicle = _unit_by_datasheet(
        state,
        player_id=opponent_player_id(row.scoring_player_id),
        datasheet_id="core-vehicle-monster",
    )
    _record_destruction(state, destroyed_unit=vehicle, event_log=event_log)
    return SecondaryPositiveExpectation(
        expected_amount=2,
        expected_rule_ids=frozenset({"no-prisoners-tactical"}),
        opponent_turn=False,
    )


def _seed_outflank(
    state: GameState,
    row: SecondaryMissionLifecycleCertificationRow,
) -> SecondaryPositiveExpectation:
    assert state.mission_setup is not None
    width = state.mission_setup.battlefield_width_inches
    depth = state.mission_setup.battlefield_depth_inches
    west, east = _intercessors(state, player_id=row.scoring_player_id)[:2]
    _place_unit_at(state, west.unit_instance_id, 3.0, depth / 2.0)
    _place_unit_at(state, east.unit_instance_id, width - 3.0, depth / 2.0)
    return SecondaryPositiveExpectation(
        expected_amount=5,
        expected_rule_ids=frozenset({"outflank-source-opposite-edges"}),
        opponent_turn=False,
    )


def _seed_overwhelming_force(
    state: GameState,
    row: SecondaryMissionLifecycleCertificationRow,
    event_log: EventLog | None,
) -> SecondaryPositiveExpectation:
    marker = _no_mans_land_non_home_markers(state, player_id=row.scoring_player_id)[0]
    vehicle = _unit_by_datasheet(
        state,
        player_id=opponent_player_id(row.scoring_player_id),
        datasheet_id="core-vehicle-monster",
    )
    _place_unit_at(
        state,
        vehicle.unit_instance_id,
        marker.x_inches,
        marker.y_inches,
    )
    _record_destruction(
        state,
        destroyed_unit=vehicle,
        started_turn_objective_marker_ids=(marker.objective_marker_id,),
        event_log=event_log,
    )
    return SecondaryPositiveExpectation(
        expected_amount=3,
        expected_rule_ids=frozenset({"overwhelming-force-tactical"}),
        opponent_turn=False,
    )


def _seed_plunder(
    state: GameState,
    row: SecondaryMissionLifecycleCertificationRow,
) -> SecondaryPositiveExpectation:
    area = _first_plunderable_area(state, player_id=row.scoring_player_id)
    _record_plunder(
        state,
        player_id=row.scoring_player_id,
        terrain_feature_id=area.logical_terrain_area_id,
    )
    return SecondaryPositiveExpectation(
        expected_amount=5,
        expected_rule_ids=frozenset({"plunder-tactical"}),
        opponent_turn=False,
    )


def _seed_secure_no_mans_land(
    state: GameState,
    row: SecondaryMissionLifecycleCertificationRow,
) -> SecondaryPositiveExpectation:
    markers = _no_mans_land_non_home_markers(state, player_id=row.scoring_player_id)[:2]
    units = _intercessors(state, player_id=row.scoring_player_id)[:2]
    if len(markers) < 2:
        raise AssertionError("Step 6G Secure No Man's Land needs two No Man's Land objectives.")
    for unit, marker in zip(units, markers, strict=True):
        _place_unit_at(state, unit.unit_instance_id, marker.x_inches, marker.y_inches)
    return SecondaryPositiveExpectation(
        expected_amount=5,
        expected_rule_ids=frozenset({"secure-no-mans-land-tactical"}),
        opponent_turn=False,
    )


def _rebind_tempting_target(
    state: GameState,
    row: SecondaryMissionLifecycleCertificationRow,
) -> None:
    from warhammer40k_core.engine.secondary_mission_selection import SecondaryMissionSelection

    marker = _no_mans_land_non_home_markers(state, player_id=row.scoring_player_id)[0]
    card = state.secondary_mission_card_state(
        player_id=row.scoring_player_id,
        secondary_mission_id="a-tempting-target",
        mode=SecondaryMissionCardMode.TACTICAL,
    )
    if card is None:
        raise AssertionError("Tempting Target certification card is missing.")
    state.replace_secondary_mission_card_state(
        card.with_selection(
            SecondaryMissionSelection().with_tempting_objective(marker.objective_marker_id)
        )
    )


def _rebind_beacon(state: GameState, row: SecondaryMissionLifecycleCertificationRow) -> None:
    from warhammer40k_core.engine.secondary_mission_selection import SecondaryMissionSelection

    unit = _intercessors(state, player_id=row.scoring_player_id)[0]
    card = state.secondary_mission_card_state(
        player_id=row.scoring_player_id,
        secondary_mission_id="beacon",
        mode=SecondaryMissionCardMode.TACTICAL,
    )
    if card is None:
        raise AssertionError("Beacon certification card is missing.")
    state.replace_secondary_mission_card_state(
        card.with_selection(SecondaryMissionSelection().with_beacon_unit(unit.unit_instance_id))
    )


def _rebind_burden(state: GameState, row: SecondaryMissionLifecycleCertificationRow) -> None:
    from warhammer40k_core.engine.secondary_mission_selection import SecondaryMissionSelection

    marker = _home_marker(state, player_id=row.scoring_player_id)
    unit = _intercessors(state, player_id=row.scoring_player_id)[0]
    card = state.secondary_mission_card_state(
        player_id=row.scoring_player_id,
        secondary_mission_id="burden-of-trust",
        mode=SecondaryMissionCardMode.TACTICAL,
    )
    if card is None:
        raise AssertionError("Burden of Trust certification card is missing.")
    assert state.mission_setup is not None
    state.replace_secondary_mission_card_state(
        card.with_selection(
            SecondaryMissionSelection().with_guards(
                guarded_objective_unit_ids=((marker.objective_marker_id, unit.unit_instance_id),),
                resolved_guard_objective_ids=tuple(
                    objective.objective_marker_id
                    for objective in state.mission_setup.objective_markers
                ),
                battle_round=state.battle_round,
            )
        )
    )


def _record_destruction(
    state: GameState,
    *,
    destroyed_unit: UnitInstance,
    started_turn_objective_marker_ids: tuple[str, ...] | None = None,
    destroying_player_id: str | None = None,
    event_log: EventLog | None = None,
) -> None:
    record_secondary_destruction_for_fixture(
        state,
        destroying_player_id=destroying_player_id,
        destroyed_unit_instance_id=destroyed_unit.unit_instance_id,
        source_id=f"phase17n-step6g:{destroyed_unit.unit_instance_id}:destroyed",
        event_log=event_log,
        expected_started_turn_objective_marker_ids=started_turn_objective_marker_ids,
    )


def _record_cleanse(state: GameState, *, player_id: str, objective_marker_id: str) -> None:
    action_id = f"phase17n-step6g-cleanse:{objective_marker_id}"
    source_id = _record_completed_zero_vp_mission_action(
        state,
        mission_action_id="cleanse-objective",
        action_id=action_id,
        target_id=objective_marker_id,
        player_id=player_id,
    )
    state.record_secondary_objective_cleanse(
        player_id=player_id,
        objective_marker_id=objective_marker_id,
        action_id=action_id,
        phase=BattlePhase.FIGHT,
        source_id=source_id,
    )


def _record_plunder(state: GameState, *, player_id: str, terrain_feature_id: str) -> None:
    action_id = f"phase17n-step6g-plunder:{terrain_feature_id}"
    source_id = _record_completed_zero_vp_mission_action(
        state,
        mission_action_id="plunder-terrain",
        action_id=action_id,
        target_id=terrain_feature_id,
        player_id=player_id,
    )
    state.record_secondary_terrain_plunder(
        player_id=player_id,
        terrain_feature_id=terrain_feature_id,
        action_id=action_id,
        phase=BattlePhase.SHOOTING,
        source_id=source_id,
    )


def _record_completed_zero_vp_mission_action(
    state: GameState,
    *,
    mission_action_id: str,
    action_id: str,
    target_id: str,
    player_id: str,
) -> str:
    if state.mission_setup is None:
        raise AssertionError("Step 6G mission action fixture requires MissionSetup.")
    mission_action = mission_pack_for_id(state.mission_setup.mission_pack_id).mission_action(
        mission_action_id
    )
    unit_instance_id = _units_for_player(state, player_id)[0].unit_instance_id
    started = MissionActionState.start(
        action_id=action_id,
        mission_action_id=mission_action.mission_action_id,
        player_id=player_id,
        unit_instance_id=unit_instance_id,
        target_id=target_id,
        condition_target_id=target_id,
        mission_id=mission_action.mission_id,
        battle_round=state.battle_round,
        phase=mission_action.start_phase,
        start_timing=mission_action.start_timing,
        completion_timing=mission_action.completion_timing,
        eligible_unit_instance_ids=(unit_instance_id,),
        interruption_conditions=mission_action.interruption_conditions,
        scoring_source_id=mission_action.scoring_source_id,
        victory_points=mission_action.victory_points,
    )
    completion_phase = (
        BattlePhase.FIGHT.value
        if mission_action.completion_timing == "turn_end"
        else mission_action.start_phase
    )
    completed = started.complete_without_award(
        battle_round=state.battle_round,
        phase=completion_phase,
        completion_timing=mission_action.completion_timing,
    )
    state.record_mission_action_state(completed)
    return mission_action.source_id


def _first_plunderable_area(state: GameState, *, player_id: str) -> MissionLogicalTerrainArea:
    if state.mission_setup is None:
        raise AssertionError("Step 6G plunder fixture requires MissionSetup.")
    for area in mission_logical_terrain_areas(state.mission_setup):
        if not logical_terrain_area_within_player_territory(
            area,
            mission_setup=state.mission_setup,
            player_id=player_id,
        ):
            return area
    raise AssertionError("Step 6G plunder fixture has no plunderable terrain.")


def _place_unit_at(
    state: GameState,
    unit_instance_id: str,
    x_inches: float,
    y_inches: float,
) -> None:
    if state.battlefield_state is None:
        raise AssertionError("Step 6G placement requires battlefield state.")
    unit_placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    placements: list[ModelPlacement] = []
    columns = 5
    for index, placement in enumerate(unit_placement.model_placements):
        column = index % columns
        row = index // columns
        placements.append(
            placement.with_pose(
                Pose.at(
                    x_inches + (column * 0.45),
                    y_inches + (row * 0.45),
                    placement.pose.position.z,
                    facing_degrees=placement.pose.facing.degrees,
                )
            )
        )
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        unit_placement.with_model_placements(tuple(placements))
    )


def _home_marker(state: GameState, *, player_id: str) -> ObjectiveMarkerDefinition:
    if state.mission_setup is None:
        raise AssertionError("Step 6G home-objective fixture requires MissionSetup.")
    role = (
        ObjectiveMarkerRole.ATTACKER_HOME
        if player_id == state.mission_setup.attacker_player_id
        else ObjectiveMarkerRole.DEFENDER_HOME
    )
    for marker in state.mission_setup.objective_markers:
        if marker.objective_role is role:
            return marker
    raise AssertionError("Step 6G fixture is missing a home objective.")


def _no_mans_land_non_home_markers(
    state: GameState,
    *,
    player_id: str,
) -> tuple[ObjectiveMarkerDefinition, ...]:
    if state.mission_setup is None:
        raise AssertionError("Step 6G No Man's Land fixture requires MissionSetup.")
    nml_regions = tuple(
        region
        for region in state.mission_setup.battlefield_regions
        if region.region_kind is BattlefieldRegionKind.NO_MANS_LAND
    )
    if not nml_regions:
        raise AssertionError("Step 6G layout is missing a No Man's Land region.")
    home_id = _home_marker(state, player_id=player_id).objective_marker_id
    return tuple(
        marker
        for marker in state.mission_setup.objective_markers
        if marker.objective_marker_id != home_id
        and any(region.contains_point(marker.x_inches, marker.y_inches) for region in nml_regions)
    )


def _intercessors(state: GameState, *, player_id: str) -> tuple[UnitInstance, ...]:
    return tuple(
        unit
        for unit in _units_for_player(state, player_id)
        if unit.datasheet_id == "core-intercessor-like-infantry"
    )


def _unit_by_datasheet(state: GameState, *, player_id: str, datasheet_id: str) -> UnitInstance:
    matches = tuple(
        unit for unit in _units_for_player(state, player_id) if unit.datasheet_id == datasheet_id
    )
    if len(matches) != 1:
        raise AssertionError(f"Step 6G expected one {datasheet_id} for {player_id}.")
    return matches[0]


def _units_for_player(state: GameState, player_id: str) -> tuple[UnitInstance, ...]:
    for army in state.army_definitions:
        if army.player_id == player_id:
            return army.units
    raise AssertionError(f"Step 6G fixture is missing army for {player_id}.")


_DESTRUCTION_SEEDERS = {
    "a-grievous-blow": _seed_grievous,
    "assassination": _seed_assassination,
    "bring-it-down": _seed_bring_it_down,
    "no-prisoners": _seed_no_prisoners,
    "overwhelming-force": _seed_overwhelming_force,
}

_SEEDERS = {
    "a-tempting-target": _seed_tempting,
    "beacon": _seed_beacon,
    "behind-enemy-lines": _seed_behind_enemy_lines,
    "burden-of-trust": _seed_burden,
    "centre-ground": _seed_centre_ground,
    "cleanse": _seed_cleanse,
    "defend-stronghold": _seed_defend_stronghold,
    "display-of-might": _seed_display_of_might,
    "engage-on-all-fronts": _seed_engage,
    "forward-position": _seed_forward_position,
    "outflank": _seed_outflank,
    "plunder": _seed_plunder,
    "secure-no-mans-land": _seed_secure_no_mans_land,
}


__all__ = [
    "TURN_CAP_TACTICAL_IDS",
    "SecondaryPositiveExpectation",
    "active_player_id_for_row",
    "certification_unit_selections",
    "certification_unit_selections_for_row",
    "opponent_player_id",
    "seed_positive_secondary_condition",
    "seed_sequential_tactical_turn_cap_conditions",
]
