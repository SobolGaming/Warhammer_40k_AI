"""18.01/18.02: every embark predicate, capacities and FAQ exceptions."""

# pyright: reportPrivateUsage=false
from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section09_fixtures import add_unit, unplace
from tests.support.section18_fixtures import AVENGERS, LORD, transport_scene
from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.phase_movement_history import PhaseMovementRecord
from warhammer40k_core.engine.transport_embark_context import NoMovementEmbarkContext
from warhammer40k_core.engine.transport_embark_validation import _model_within_any_transport_model
from warhammer40k_core.engine.transport_source_embark import no_movement_embark_permission_effect
from warhammer40k_core.engine.transports import (
    EmbarkResolution,
    EmbarkSelection,
    TransportMovementStatus,
    TransportRestrictionOverride,
    TransportRestrictionOverrideKind,
    apply_embark_to_battlefield,
    resolve_embark,
)
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model, ModelVolume


@pytest.mark.parametrize(
    "action",
    [
        TransportMovementStatus.NORMAL_MOVE,
        TransportMovementStatus.ADVANCE,
        TransportMovementStatus.FALL_BACK,
    ],
)
def test_each_permitted_move_can_embark_whole_unit_and_remove_its_placement(
    section18_definitions: Section02Definitions,
    action: TransportMovementStatus,
) -> None:
    s = transport_scene(section18_definitions, embarked=False)
    before = s.scenario.battlefield_state
    result = resolve_embark(
        scenario=s.scenario,
        cargo_state=s.cargo,
        selection=EmbarkSelection(
            "owner", 1, s.passenger.unit_instance_id, s.transport.unit_instance_id, action
        ),
        unit_placement=before.unit_placement_by_id(s.passenger.unit_instance_id),
        transport_placement=s.carrier_placement,
        movement_history=(),
        turn_player_id="owner",
    )
    assert result.is_valid, result.violations
    assert result.updated_cargo_state is not None
    assert result.updated_cargo_state.embarked_unit_instance_ids == (s.passenger.unit_instance_id,)
    assert result.transition_batch is not None
    assert {r.model_instance_id for r in result.transition_batch.removals} == set(
        s.passenger.own_model_ids()
    )
    assert {r.destination_id for r in result.transition_batch.removals} == {
        s.transport.unit_instance_id
    }
    after = apply_embark_to_battlefield(battlefield_state=before, embark=result)
    assert after.unit_placement_or_none(s.passenger.unit_instance_id) is None
    assert before.unit_placement_or_none(s.passenger.unit_instance_id) is not None
    assert EmbarkResolution.from_payload(result.to_payload()) == result


@pytest.mark.parametrize(
    ("horizontal", "vertical", "valid"),
    [
        (4.96, 0, True),
        (4.97, 0, False),
        (1, 3, True),
        (1, 3.001, False),
        (4.36, 1.8, True),
        (4.37, 1.8, False),
    ],
)
def test_embark_each_model_uses_actual_three_dimensional_three_inch_distance(
    section18_definitions: Section02Definitions,
    horizontal: float,
    vertical: float,
    valid: bool,
) -> None:
    s = transport_scene(
        section18_definitions,
        embarked=False,
        passenger_poses=(Pose.at(20 + horizontal, 20, vertical),),
    )
    result = resolve_embark(
        scenario=s.scenario,
        cargo_state=s.cargo,
        selection=EmbarkSelection(
            "owner",
            1,
            s.passenger.unit_instance_id,
            s.transport.unit_instance_id,
            TransportMovementStatus.NORMAL_MOVE,
        ),
        unit_placement=s.scenario.battlefield_state.unit_placement_by_id(
            s.passenger.unit_instance_id
        ),
        transport_placement=s.carrier_placement,
        movement_history=(),
        turn_player_id="owner",
    )
    assert result.is_valid is valid, result.violations
    assert {v.violation_code.value for v in result.violations} == (
        set() if valid else {"embark_distance"}
    )
    if not valid:
        assert result.updated_cargo_state is None
        assert result.transition_batch is None


@pytest.mark.parametrize(
    ("capacity", "occupied", "valid"),
    [(5, False, True), (4, False, False), (6, True, True), (5, True, False)],
)
def test_type_and_remaining_capacity_count_all_models_and_multiple_units(
    section18_definitions: Section02Definitions,
    capacity: int,
    occupied: bool,
    valid: bool,
) -> None:
    # Five native Avengers in coherent positions, each within the carrier's 3".
    s = transport_scene(
        section18_definitions,
        embarked=False,
        passenger_sheet=AVENGERS,
        capacity=capacity,
        passenger_poses=(
            Pose.at(22, 18),
            Pose.at(23.3, 18.5),
            Pose.at(23.5, 20),
            Pose.at(23.3, 21.5),
            Pose.at(22, 22),
        ),
    )
    if occupied:
        other = section18_definitions.unit(LORD, identity="other-cargo")
        add_unit(s.state, other, (Pose.at(30, 20),))
        s.state.replace_battlefield_state(unplace(s.state, other))
        s.state.replace_transport_cargo_state(
            replace(s.cargo, embarked_unit_instance_ids=(other.unit_instance_id,))
        )
    result = resolve_embark(
        scenario=s.scenario,
        cargo_state=s.cargo,
        selection=EmbarkSelection(
            "owner",
            1,
            s.passenger.unit_instance_id,
            s.transport.unit_instance_id,
            TransportMovementStatus.NORMAL_MOVE,
        ),
        unit_placement=s.scenario.battlefield_state.unit_placement_by_id(
            s.passenger.unit_instance_id
        ),
        transport_placement=s.carrier_placement,
        movement_history=(),
        turn_player_id="owner",
    )
    assert result.is_valid is valid, result.violations
    assert {v.violation_code.value for v in result.violations} == (
        set() if valid else {"capacity_exceeded"}
    )
    if valid:
        assert result.updated_cargo_state is not None
        assert len(result.updated_cargo_state.embarked_unit_instance_ids) == 1 + int(occupied)
    else:
        assert result.updated_cargo_state is None
        assert result.transition_batch is None


@pytest.mark.parametrize(
    ("allowed", "excluded", "valid"),
    [
        (("INFANTRY",), (), True),
        (("VEHICLE",), (), False),
        (("INFANTRY",), ("CHARACTER",), False),
        (("INFANTRY",), ("PRINCE",), True),
    ],
)
def test_capacity_type_gates_use_exact_keywords(
    section18_definitions: Section02Definitions,
    allowed: tuple[str, ...],
    excluded: tuple[str, ...],
    valid: bool,
) -> None:
    s = transport_scene(section18_definitions, embarked=False)
    cargo = replace(
        s.cargo,
        capacity_profile=replace(
            s.cargo.capacity_profile, allowed_keywords=allowed, excluded_keywords=excluded
        ),
    )
    result = resolve_embark(
        scenario=s.scenario,
        cargo_state=cargo,
        selection=EmbarkSelection(
            "owner",
            1,
            s.passenger.unit_instance_id,
            s.transport.unit_instance_id,
            TransportMovementStatus.NORMAL_MOVE,
        ),
        unit_placement=s.scenario.battlefield_state.unit_placement_by_id(
            s.passenger.unit_instance_id
        ),
        transport_placement=s.carrier_placement,
        movement_history=(),
        turn_player_id="owner",
    )
    assert result.is_valid is valid, result.violations
    assert {v.violation_code.value for v in result.violations} == (
        set() if valid else {"capacity_exceeded"}
    )


@pytest.mark.parametrize(
    "setup",
    [
        BattlefieldPlacementKind.DISEMBARK,
        BattlefieldPlacementKind.STRATEGIC_RESERVES,
        BattlefieldPlacementKind.DEEP_STRIKE,
    ],
)
@pytest.mark.parametrize("same_turn", [True, False])
def test_all_current_turn_battlefield_setups_forbid_embark_but_expire_by_actual_turn(
    section18_definitions: Section02Definitions,
    setup: BattlefieldPlacementKind,
    same_turn: bool,
) -> None:
    s = transport_scene(section18_definitions, embarked=False)
    history = (
        PhaseMovementRecord(
            "constructed:s18:prior-setup",
            1,
            "owner" if same_turn else "opponent",
            BattlePhase.MOVEMENT,
            s.passenger.unit_instance_id,
            s.passenger.own_model_ids(),
            False,
            False,
            setup_kind=setup,
        ),
    )
    result = resolve_embark(
        scenario=s.scenario,
        cargo_state=s.cargo,
        selection=EmbarkSelection(
            "owner",
            1,
            s.passenger.unit_instance_id,
            s.transport.unit_instance_id,
            TransportMovementStatus.NORMAL_MOVE,
        ),
        unit_placement=s.scenario.battlefield_state.unit_placement_by_id(
            s.passenger.unit_instance_id
        ),
        transport_placement=s.carrier_placement,
        movement_history=history,
        turn_player_id="owner",
    )
    assert result.is_valid is not same_turn, result.violations
    assert {v.violation_code.value for v in result.violations} == (
        {"embark_after_setup_forbidden"} if same_turn else set()
    )


@pytest.mark.parametrize("override", [False, True])
@pytest.mark.parametrize(
    "setup", [BattlefieldPlacementKind.DISEMBARK, BattlefieldPlacementKind.STRATEGIC_RESERVES]
)
def test_faq14_exception_changes_only_the_disembark_setup_condition(
    section18_definitions: Section02Definitions,
    override: bool,
    setup: BattlefieldPlacementKind,
) -> None:
    s = transport_scene(section18_definitions, embarked=False)
    history = (
        PhaseMovementRecord(
            "constructed:s18:setup",
            1,
            "owner",
            BattlePhase.MOVEMENT,
            s.passenger.unit_instance_id,
            s.passenger.own_model_ids(),
            False,
            False,
            setup_kind=setup,
        ),
    )
    selection = EmbarkSelection(
        "owner",
        1,
        s.passenger.unit_instance_id,
        s.transport.unit_instance_id,
        TransportMovementStatus.NORMAL_MOVE,
        (
            TransportRestrictionOverride(
                TransportRestrictionOverrideKind.ALLOW_EMBARK_AFTER_DISEMBARK,
                "faq:fae8a959-9cbe-46e3-a721-029b23b24e24",
            ),
        )
        if override
        else (),
    )
    result = resolve_embark(
        scenario=s.scenario,
        cargo_state=s.cargo,
        selection=selection,
        unit_placement=s.scenario.battlefield_state.unit_placement_by_id(
            s.passenger.unit_instance_id
        ),
        transport_placement=s.carrier_placement,
        movement_history=history,
        turn_player_id="owner",
    )
    assert result.is_valid is (override and setup is BattlefieldPlacementKind.DISEMBARK), (
        result.violations
    )


@pytest.mark.parametrize("allowed", [True, False])
def test_faq1_source_owned_no_move_occasion_obeys_other_unchanged_conditions(
    section18_definitions: Section02Definitions,
    allowed: bool,
) -> None:
    s = transport_scene(section18_definitions, embarked=False)
    context = NoMovementEmbarkContext(
        "faq:c2df3e97-f21e-4fc9-943e-37072c08c10e",
        "constructed:s18:permission",
        "constructed:s18:occasion",
        1,
        "owner",
        BattlePhase.MOVEMENT,
        s.passenger.unit_instance_id,
    )
    effect = no_movement_embark_permission_effect(
        context=context, owner_player_id="owner", allow_after_disembark=True
    )
    override = TransportRestrictionOverride(
        TransportRestrictionOverrideKind.ALLOW_EMBARK_AFTER_DISEMBARK, context.source_rule_id
    )
    cargo = (
        s.cargo
        if allowed
        else replace(
            s.cargo,
            capacity_profile=replace(s.cargo.capacity_profile, allowed_keywords=("VEHICLE",)),
        )
    )
    history = (
        PhaseMovementRecord(
            "constructed:s18:setup",
            1,
            "owner",
            BattlePhase.MOVEMENT,
            s.passenger.unit_instance_id,
            s.passenger.own_model_ids(),
            False,
            False,
            setup_kind=BattlefieldPlacementKind.DISEMBARK,
        ),
    )
    selection = EmbarkSelection(
        "owner",
        1,
        s.passenger.unit_instance_id,
        s.transport.unit_instance_id,
        TransportMovementStatus.NOT_MOVED,
        (override,),
        context,
    )
    result = resolve_embark(
        scenario=s.scenario,
        cargo_state=cargo,
        selection=selection,
        unit_placement=s.scenario.battlefield_state.unit_placement_by_id(
            s.passenger.unit_instance_id
        ),
        transport_placement=s.carrier_placement,
        movement_history=history,
        turn_player_id="owner",
        persisting_effects=(effect,),
    )
    assert result.is_valid is allowed, result.violations
    assert selection.source_context == context
    assert selection.movement_phase_action is TransportMovementStatus.NOT_MOVED


@pytest.mark.parametrize(
    "action",
    [
        TransportMovementStatus.NOT_MOVED,
        TransportMovementStatus.REMAIN_STATIONARY,
        TransportMovementStatus.INGRESS_MOVE,
    ],
)
def test_no_ungranted_move_type_can_construct_an_ordinary_embark(
    action: TransportMovementStatus,
) -> None:
    with pytest.raises(GameLifecycleError, match="Normal, Advance, or Fall Back"):
        EmbarkSelection("owner", 1, "passenger", "carrier", action)


def test_one_remote_model_blocks_whole_unit_without_partial_cargo(
    section18_definitions: Section02Definitions,
) -> None:
    s = transport_scene(
        section18_definitions,
        embarked=False,
        passenger_sheet=AVENGERS,
        passenger_poses=(
            Pose.at(23, 18),
            Pose.at(23, 19.5),
            Pose.at(23, 21),
            Pose.at(23, 22.5),
            Pose.at(30, 20),
        ),
    )
    result = resolve_embark(
        scenario=s.scenario,
        cargo_state=s.cargo,
        selection=EmbarkSelection(
            "owner",
            1,
            s.passenger.unit_instance_id,
            s.transport.unit_instance_id,
            TransportMovementStatus.NORMAL_MOVE,
        ),
        unit_placement=s.scenario.battlefield_state.unit_placement_by_id(
            s.passenger.unit_instance_id
        ),
        transport_placement=s.carrier_placement,
        movement_history=(),
        turn_player_id="owner",
    )
    assert not result.is_valid
    assert {
        v.model_instance_id
        for v in result.violations
        if v.violation_code.value == "embark_distance"
    } == {s.passenger.own_models[-1].model_instance_id}
    assert result.updated_cargo_state is None
    assert result.transition_batch is None


def test_opponent_cannot_embark_a_friendly_pair_and_round_zero_is_not_in_battle(
    section18_definitions: Section02Definitions,
) -> None:
    s = transport_scene(section18_definitions, embarked=False)
    result = resolve_embark(
        scenario=s.scenario,
        cargo_state=s.cargo,
        selection=EmbarkSelection(
            "opponent",
            1,
            s.passenger.unit_instance_id,
            s.transport.unit_instance_id,
            TransportMovementStatus.NORMAL_MOVE,
        ),
        unit_placement=s.scenario.battlefield_state.unit_placement_by_id(
            s.passenger.unit_instance_id
        ),
        transport_placement=s.carrier_placement,
        movement_history=(),
        turn_player_id="opponent",
    )
    assert not result.is_valid
    assert {v.violation_code.value for v in result.violations} == {"friendly_transport_required"}
    assert result.updated_cargo_state is None
    assert result.transition_batch is None
    with pytest.raises(GameLifecycleError, match="at least 1"):
        EmbarkSelection(
            "owner",
            0,
            s.passenger.unit_instance_id,
            s.transport.unit_instance_id,
            TransportMovementStatus.NORMAL_MOVE,
        )


@pytest.mark.parametrize("axis", ["horizontal", "vertical", "diagonal"])
@pytest.mark.parametrize("translation", [(0.0, 0.0, 0.0), (19.0, 11.0, 7.0)])
def test_embark_comparison_allowance_does_not_admit_distance_beyond_envelope(
    axis: str, translation: tuple[float, float, float]
) -> None:
    x, y, z = translation
    carrier = Model("carrier", Pose.at(x, y, z), CircularBase(0.5), ModelVolume(20))
    outside = 3.0 + 2e-9
    endpoint = (
        Pose.at(x + outside + 1, y, z)
        if axis == "horizontal"
        else Pose.at(x, y, z + outside)
        if axis == "vertical"
        else Pose.at(x + 1 + 0.6 * outside, y, z + 0.8 * outside)
    )
    passenger = Model("passenger", endpoint, CircularBase(0.5), ModelVolume(20))
    assert not _model_within_any_transport_model(
        passenger, transport_models=(carrier,), distance_inches=3
    )
