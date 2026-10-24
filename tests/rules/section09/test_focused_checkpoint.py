"""Fresh bounded controls for the approved defect checkpoint, using native definitions.

Initial phase/retention/permission checkpoints remain explicitly constructed. These
checks add no roster admission, named faction provider or whole-game claim.
"""

import math
from copy import deepcopy
from dataclasses import replace
from fractions import Fraction

import pytest

from tests.support.section01_fixtures import core_rule, minimal_state
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import (
    axis_endpoint_within_range,
    geometry,
    native_state,
    scenario,
)
from tests.support.section03_session import movement_session
from tests.support.section04_fixtures import pending
from tests.support.section05_fixtures import replace_unit
from tests.support.section05_retention import retain, terminal_retention
from tests.support.section09_fixtures import (
    add_unit,
    anchor_hazard_scene,
    attach_mission,
    choose,
    events,
    finish_hazard_choices,
    movement_case,
    propose,
    select,
)
from tests.support.section11_fixtures import choose as charge_choose
from tests.support.section11_fixtures import modifier, section11_definitions, witness
from tests.support.section11_fixtures import propose as charge_propose
from tests.support.section11_reactive import reactive_case
from tests.support.section12_fixtures import engaged_case, set_pose
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.ruleset_descriptor import (
    ConsolidationModeKind,
    FightEligibilityKind,
    FightOrderingBandKind,
    FightTypeKind,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.destroyed_referent_measurement import (
    former_footprint_for_destroyed_model,
)
from warhammer40k_core.engine.fight_order import (
    EligibleToFightPass,
    FightActivationSelection,
    FightOrderState,
)
from warhammer40k_core.engine.fight_rules_unit_movement import legal_rules_unit_consolidation_modes
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.phases.movement_handler import MovementPhaseHandler
from warhammer40k_core.engine.retained_destruction_cleanup import begin_retained_destruction_cleanup
from warhammer40k_core.engine.retained_model_presence import model_is_present_on_battlefield
from warhammer40k_core.engine.rule_execution import RuleExecutionContext, execute_rule_ir
from warhammer40k_core.engine.stealth import stealth_source_inventory
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model, ModelVolume

__all__ = ("section11_definitions",)


@pytest.mark.parametrize("spelling", ["STEALTH", "sTeAlTh"])
def test_repair_stealth_is_canonical_before_the_native_consumer(
    section09_definitions: Section02Definitions,
    spelling: str,
) -> None:
    unit = section09_definitions.unit("000004078")
    state = minimal_state(section09_definitions, unit)
    rule = core_rule(f"This unit gains {spelling} until the end of the phase.")
    grants = [
        p.value
        for clause in rule.clauses
        for effect in clause.effects
        for p in effect.parameters
        if p.key == "ability"
    ]
    assert grants == ["stealth"]
    execute_rule_ir(
        rule_ir=rule,
        context=RuleExecutionContext(
            game_id=state.game_id,
            player_id="owner",
            battle_round=1,
            phase=BattlePhase.COMMAND,
            active_player_id="owner",
            source_unit_instance_id=unit.unit_instance_id,
            state=state,
        ),
    )
    assert stealth_source_inventory(state=state, target_unit_instance_id=unit.unit_instance_id)[
        1
    ] == set(unit.own_model_ids())


@pytest.mark.parametrize("origin", [2.0, 10.0, 30.0])
@pytest.mark.parametrize("distance", [2.0, 3.0, 2.125])
@pytest.mark.parametrize("outside", [False, True])
def test_repair_native_inclusive_proximity_keeps_tight_exterior_rejection(
    section09_definitions: Section02Definitions,
    origin: float,
    distance: float,
    outside: bool,
) -> None:
    unit = section09_definitions.unit("000004078")
    first = geometry(unit, (Pose.at(origin, 10),))[0]
    assert isinstance(first.base, CircularBase)
    delta = 1e-10 if outside else 0.0
    second = replace(
        first,
        model_id="native-boundary-peer",
        pose=Pose.at(
            axis_endpoint_within_range(origin, first.base.radius, first.base.radius, distance)
            + delta,
            10,
        ),
    )
    assert first.is_within_range(second, distance) is (not outside)
    assert first.is_within_engagement_range(second, distance, 5) is (not outside)
    raised = replace(
        second, pose=Pose.at(second.pose.position.x, 10, first.volume.height + 5 + 1e-10)
    )
    assert not first.is_within_engagement_range(raised, distance, 5)


def test_repair_ordered_retreat_rejects_transit_then_accepts_native_retry(
    section09_definitions: Section02Definitions,
) -> None:
    session, state, unit = movement_case(section09_definitions, engaged=True)
    request = choose(session, select(session, unit), "fall_back:ordered_retreat")
    before = state.battlefield_state
    result = propose(session, request, unit, (Pose.at(10, 18), Pose.at(12.5, 18)))
    assert result.status_kind is LifecycleStatusKind.INVALID
    assert state.battlefield_state == before
    retry = session.advance_until_decision_or_terminal().decision_request
    assert retry is not None
    result = propose(
        session, retry, unit, (Pose.at(10, 6), Pose.at(12.5, 6)), result_id="retreat-retry"
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID
    assert not events(session, "desperate_escape_roll_resolved")
    assert len(events(session, "movement_activation_completed")) == 1


def test_repair_pending_hazard_packet_roundtrips_and_continues_exactly_once(
    section09_definitions: Section02Definitions,
) -> None:
    session, state, unit = movement_case(section09_definitions, engaged=True)
    state.game_id = "focused-hazard-valid-custom-pending-4"
    assert state.mission_setup is not None
    # Empty geometry is an explicit custom checkpoint, not the source layout.
    state.mission_setup = replace(
        state.mission_setup,
        deployment_map_id="constructed:focused:deployment",
        terrain_layout_id="constructed:focused:empty",
    )
    state.ruleset_descriptor_hash = state.runtime_ruleset_descriptor().descriptor_hash
    state.starting_strength_records.sort(key=lambda row: (row.player_id, row.unit_instance_id))
    # Recreate the config with this fixed natural RNG identity before recording.
    session = movement_session(section09_definitions, state)
    request = choose(session, select(session, unit), "fall_back:desperate_escape")
    status = propose(session, request, unit, (Pose.at(10, 6), Pose.at(12.5, 6)))
    allocation = status.decision_request
    assert allocation is not None
    assert allocation.decision_type == "select_mortal_wound_model"
    assert state.battlefield_state is not None
    assert state.battlefield_state.model_placement_by_id(unit.own_model_ids()[0]).pose == Pose.at(
        10, 10
    )
    anchor_hazard_scene(session)
    payload = session.lifecycle.to_payload()
    # This declared non-roster kernel is not admitted by full muster restore.
    # Round-trip its typed state and decision packet, then rebuild the same kernel.
    cloned_state = GameState.from_payload(deepcopy(state.to_payload()))
    config = session.lifecycle.config
    assert config is not None
    restored = LocalGameSession(
        GameLifecycle(
            state=cloned_state,
            _config=config,
            _movement_phase_handler=MovementPhaseHandler(
                ruleset_descriptor=config.ruleset_descriptor, army_catalog=config.army_catalog
            ),
            decision_controller=DecisionController.from_payload(
                deepcopy(session.lifecycle.decision_controller.to_payload())
            ),
            _modifier_evaluation_history_origin=deepcopy(
                session.lifecycle._modifier_evaluation_history_origin  # pyright: ignore[reportPrivateUsage]
            ),
        )
    )
    assert restored.lifecycle.state is not None
    assert restored.lifecycle.state.to_payload() == payload["state"]
    assert (
        restored.lifecycle.decision_controller.to_payload()
        == session.lifecycle.decision_controller.to_payload()
    )
    restored_status = restored.advance_until_decision_or_terminal()
    assert restored_status.decision_request == allocation
    # Both continuations use the exact same recorded option and natural dice.
    for scene, current in ((session, status), (restored, restored_status)):
        choice = current.decision_request
        assert choice is not None
        before = scene.lifecycle.state.to_payload() if scene.lifecycle.state is not None else None
        wrong = replace(
            DecisionResult.for_request(
                request=choice,
                result_id="wrong-hazard-actor",
                selected_option_id=choice.options[0].option_id,
            ),
            actor_id="opponent",
        )
        invalid = scene.lifecycle.submit_decision(wrong)
        assert invalid.status_kind is LifecycleStatusKind.INVALID
        assert scene.lifecycle.decision_controller.queue.peek_next() == choice
        assert scene.lifecycle.state is not None
        assert scene.lifecycle.state.to_payload() == before
        finish_hazard_choices(scene, current)
        assert len(events(scene, "desperate_escape_hazard_mortals_resolved")) == 1
        assert len(events(scene, "movement_activation_completed")) == 1
    assert session.lifecycle.to_payload() == restored.lifecycle.to_payload()


def test_repair_hazard_lethal_wound_uses_native_casualty_authority_before_movement(
    section09_definitions: Section02Definitions,
) -> None:
    _old, state, unit = movement_case(section09_definitions, engaged=True)
    state.game_id = "focused-hazard-wounded-2"
    unit = replace(
        unit, own_models=(replace(unit.own_models[0], wounds_remaining=1), unit.own_models[1])
    )
    replace_unit(state, unit)
    state.battle_shocked_unit_ids.append(unit.unit_instance_id)
    session = movement_session(section09_definitions, state)
    request = choose(session, select(session, unit), "fall_back:desperate_escape")
    anchor_hazard_scene(session)
    status = propose(session, request, unit, (Pose.at(10, 6), Pose.at(12.5, 6)))
    status = finish_hazard_choices(session, status)
    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert state.battlefield_state is not None
    assert unit.own_model_ids()[0] in state.battlefield_state.removed_model_ids
    assert state.battlefield_state.model_placement_by_id(unit.own_model_ids()[1]).pose == Pose.at(
        12.5, 6
    )
    assert len(events(session, "model_destroyed")) == 1
    assert all(c.is_consumed for c in state.model_destruction_cause_authorities)


@pytest.mark.parametrize("shocked", [False, True])
def test_repair_native_defiler_auto_pass_reaches_public_movement_completion(
    section09_definitions: Section02Definitions,
    shocked: bool,
) -> None:
    unit = section09_definitions.unit("000000969")
    enemy = section09_definitions.unit("000004090", identity="enemy", army_id="enemy")
    state = native_state(
        section09_definitions,
        unit,
        (Pose.at(20, 10),),
        enemy=enemy,
        enemy_poses=(Pose.at(20, 14), Pose.at(22.5, 14)),
    )
    attach_mission(state)
    add_unit(state, section09_definitions.unit("000004078", identity="spare"), (Pose.at(35, 30),))
    if shocked:
        state.battle_shocked_unit_ids.append(unit.unit_instance_id)
    session = movement_session(section09_definitions, state)
    request = choose(session, select(session, unit), "fall_back:desperate_escape")
    status = propose(session, request, unit, (Pose.at(20, 22),))
    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert not events(session, "desperate_escape_roll_resolved")
    assert len(events(session, "movement_activation_completed")) == 1


def test_repair_charge_decline_still_rejects_a_witness_without_targets(
    section11_definitions: Section02Definitions,
) -> None:
    session, state, unit, _enemy = reactive_case(section11_definitions)
    modifier(state, unit.unit_instance_id, 12)
    pending(session)
    charge_choose(session, "charge", result_id="checkpoint-reactive-charge")
    before = state.battlefield_state
    invalid = charge_propose(
        session,
        unit.unit_instance_id,
        (),
        witness(state, unit.unit_instance_id, 0),
        result_id="checkpoint-bad-decline",
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert state.battlefield_state == before
    valid = charge_propose(session, unit.unit_instance_id, (), None, result_id="checkpoint-decline")
    assert valid.status_kind is not LifecycleStatusKind.INVALID


def test_repair_combat_breaks_pass_sequence_without_erasing_pass_history(
    section09_definitions: Section02Definitions,
) -> None:
    unit = section09_definitions.unit("000004078")
    enemy = section09_definitions.unit("000004078", identity="enemy", army_id="enemy")
    band = FightOrderingBandKind.REMAINING_COMBATS
    order = FightOrderState((band,), 0, "opponent", (unit.unit_instance_id, enemy.unit_instance_id))
    passed = EligibleToFightPass(
        "owner", 1, band, "checkpoint-pass", "checkpoint-pass-result", 5, (unit.unit_instance_id,)
    )
    order = order.with_eligible_pass(passed)
    order = FightOrderState.from_payload(order.to_payload())
    chosen = FightActivationSelection(
        "opponent",
        1,
        enemy.unit_instance_id,
        band,
        FightTypeKind.NORMAL,
        (FightEligibilityKind.ENGAGED_AT_FIGHT_STEP_START,),
        "checkpoint-fight",
        "checkpoint-fight-result",
    )
    after = order.with_activation(chosen)
    assert after.passed_player_ids == ()
    assert after.eligible_passes == (passed,)
    assert after.selected_to_fight_unit_ids == (enemy.unit_instance_id,)
    assert FightOrderState.from_payload(after.to_payload()) == after


def test_repair_after_removal_demise_keeps_the_authenticated_former_footprint(
    section09_definitions: Section02Definitions,
) -> None:
    state, unit, decisions, request = terminal_retention(
        section09_definitions, demise=True, melee=True, distance=2.5
    )
    retain(state, decisions, request)
    mid = unit.own_model_ids()[0]
    assert model_is_present_on_battlefield(state=state, model_instance_id=mid)
    former = former_footprint_for_destroyed_model(
        state=state, event_records=decisions.event_log.records, model_instance_id=mid
    )
    assert (
        begin_retained_destruction_cleanup(
            state=state,
            decisions=decisions,
            reason="unit_fight_completed",
            unit_instance_id=unit.unit_instance_id,
        )
        is None
    )
    assert not model_is_present_on_battlefield(state=state, model_instance_id=mid)
    after = former_footprint_for_destroyed_model(
        state=state, event_records=decisions.event_log.records, model_instance_id=mid
    )
    assert after == former
    types = [e.event_type for e in decisions.event_log.records]
    assert types.index("model_destroyed") < types.index("destruction_reaction_resolved")


def test_repair_hazard_survivor_coherency_retry_keeps_the_completed_packet(
    section09_definitions: Section02Definitions,
) -> None:
    unit = section09_definitions.unit("000004080")
    unit = replace(
        unit,
        own_models=tuple(
            replace(m, wounds_remaining=1) if i == 1 else m for i, m in enumerate(unit.own_models)
        ),
    )
    enemy = section09_definitions.unit("000004090", identity="enemy", army_id="enemy")
    starts = tuple(Pose.at(10 + 2 * i, 10) for i in range(5))
    state = native_state(
        section09_definitions,
        unit,
        starts,
        enemy=enemy,
        enemy_poses=(Pose.at(10, 12), Pose.at(12.5, 12)),
    )
    state.game_id = "focused-survivor-coherency-1"
    state.battle_shocked_unit_ids.append(unit.unit_instance_id)
    attach_mission(state)
    add_unit(state, section09_definitions.unit("000004078", identity="spare"), (Pose.at(35, 30),))
    session = movement_session(section09_definitions, state)
    request = choose(session, select(session, unit), "fall_back:desperate_escape")
    anchor_hazard_scene(session)
    status = finish_hazard_choices(
        session, propose(session, request, unit, tuple(Pose.at(10 + 2 * i, 6) for i in range(5)))
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(status.payload, dict)
    assert status.payload["violation_code"] == "unit_coherency_broken"
    assert state.battlefield_state is not None
    removed = state.battlefield_state.removed_model_ids
    assert removed == (unit.own_model_ids()[1],)
    survivors = replace(
        unit, own_models=tuple(m for m in unit.own_models if m.model_instance_id not in removed)
    )
    original_rolls = deepcopy(events(session, "desperate_escape_roll_resolved"))
    original_damage = deepcopy(events(session, "desperate_escape_hazard_mortals_resolved"))
    retry_request = session.advance_until_decision_or_terminal().decision_request
    assert retry_request is not None
    # Another incoherent witness remains invalid and retains this same packet.
    invalid = propose(
        session,
        retry_request,
        survivors,
        (Pose.at(10, 6), Pose.at(14, 6), Pose.at(16, 6), Pose.at(18, 6)),
        result_id="survivor-invalid",
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    retry_request = session.advance_until_decision_or_terminal().decision_request
    assert retry_request is not None
    valid = propose(
        session,
        retry_request,
        survivors,
        (Pose.at(12, 6), Pose.at(14, 6), Pose.at(16, 6), Pose.at(18, 6)),
        result_id="survivor-valid",
    )
    assert valid.status_kind is not LifecycleStatusKind.INVALID
    assert len(events(session, "movement_activation_completed")) == 1
    assert events(session, "desperate_escape_roll_resolved") == original_rolls
    assert events(session, "desperate_escape_hazard_mortals_resolved") == original_damage
    assert len(original_rolls) == 5
    assert len(original_damage) == 1
    assert state.battlefield_state.removed_model_ids == removed


@pytest.mark.parametrize("origin", [0.0, 10.0, 30.0, 1048576.0])
@pytest.mark.parametrize("scale", [2.0**-20, 1.0, 2.0**20])
def test_review_r1_binary_exterior_and_interior_use_authoritative_inputs(
    origin: float, scale: float
) -> None:
    # Independent Fraction oracle, including the reviewer's 2/3/5-inch cases.
    for radius in (0.5 * scale, (20 / 25.4) * scale):
        first = Model("a", Pose.at(origin, origin), CircularBase(radius), ModelVolume(scale))
        for limit in (2 * scale, 3 * scale, 5 * scale):
            rounded = origin + 2 * radius + limit
            for x in (
                math.nextafter(rounded, -math.inf),
                rounded,
                math.nextafter(rounded, math.inf),
            ):
                second = replace(first, model_id="b", pose=Pose.at(x, origin))
                exact_dx = Fraction(x) - Fraction(origin)
                exact_reach = 2 * Fraction(radius) + Fraction(limit)
                expected = exact_dx**2 <= exact_reach**2
                assert first.is_within_range(second, limit) is expected
                assert first.is_within_engagement_range(second, limit, 5 * scale) is expected
                assert second.is_within_range(first, limit) is expected


@pytest.mark.parametrize("origin", [-30.0, 0.0, 2.0, 10.0, 30.0, 1048576.0])
@pytest.mark.parametrize("scale", [2.0**-20, 1.0, 2.0**20])
def test_review_r1_true_translated_axis_and_diagonal_equality(origin: float, scale: float) -> None:
    first = Model("a", Pose.at(origin, origin), CircularBase(0.5 * scale), ModelVolume(scale))
    # Exact dyadic 3-4-5 equality; edge distance is 4 after subtracting the radii.
    for dx, dy in ((5 * scale, 0.0), (3 * scale, 4 * scale)):
        second = replace(first, model_id="b", pose=Pose.at(origin + dx, origin + dy))
        exact_dx = Fraction(second.pose.position.x) - Fraction(origin)
        exact_dy = Fraction(second.pose.position.y) - Fraction(origin)
        assert exact_dx**2 + exact_dy**2 == Fraction(5 * scale) ** 2
        assert first.is_within_range(second, 4 * scale)
        assert first.is_within_engagement_range(second, 4 * scale, 5 * scale)
        exterior = replace(
            second,
            pose=Pose.at(math.nextafter(second.pose.position.x, math.inf), second.pose.position.y),
        )
        assert not first.is_within_range(exterior, 4 * scale)
        assert not first.is_within_engagement_range(exterior, 4 * scale, 5 * scale)


@pytest.mark.parametrize("origin", [0.0, 10.0, 30.0])
def test_review_r1_vertical_equality_and_next_float_exterior(origin: float) -> None:
    first = Model("a", Pose.at(origin, origin, origin), CircularBase(0.5), ModelVolume(1))
    second = replace(first, model_id="b", pose=Pose.at(origin + 4, origin, origin + 5))
    assert first.is_within_range(second, 5)
    assert first.is_within_engagement_range(second, 3, 4)
    exterior = replace(
        second, pose=Pose.at(origin + 4, origin, math.nextafter(origin + 5, math.inf))
    )
    assert not first.is_within_range(exterior, 5)
    assert not first.is_within_engagement_range(exterior, 3, 4)


@pytest.mark.parametrize("origin", [2.0, 10.0, 30.0])
@pytest.mark.parametrize("limit", [2.0, 3.0])
def test_review_r1_native_consolidation_rejects_strict_exterior(
    section09_definitions: Section02Definitions, origin: float, limit: float
) -> None:
    # Same native LORD consumer as independent review. Phase checkpoint is constructed.
    state, unit, enemy = engaged_case(section09_definitions)
    first = geometry(unit, (Pose.at(origin, 10),))[0]
    second = geometry(enemy, (Pose.at(origin, 10),), enemy=True)[0]
    radius_a, radius_b = first.base.max_radius(), second.base.max_radius()
    x = math.nextafter(origin + radius_a + radius_b + limit, math.inf)
    assert Fraction(x) - Fraction(origin) - Fraction(radius_a) - Fraction(radius_b) > limit
    set_pose(state, unit, (Pose.at(origin, 10),))
    set_pose(state, enemy, (Pose.at(x, 10),), enemy=True)
    modes = legal_rules_unit_consolidation_modes(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_instance_id=unit.unit_instance_id,
        objective_markers=(),
        state=state,
    )
    rejected = ConsolidationModeKind.ONGOING if limit == 2 else ConsolidationModeKind.ENGAGING
    assert rejected not in modes


def test_spatial_review_rejects_rounded_sqrt_exterior() -> None:
    first = Model("a", Pose.at(0, 10), CircularBase(0.5), ModelVolume(1))
    second = replace(first, model_id="b", pose=Pose.at(1 + math.sqrt(8), 10, 2))
    edge = Fraction(second.pose.position.x) - 1
    assert edge**2 + 1 > 9
    assert first.range_to(second) == 3  # Reporting scalar is intentionally approximate.
    assert not first.is_within_range(second, 3)
    assert not second.is_within_range(first, 3)
    assert first.is_within_range(second, 10)


@pytest.mark.parametrize("origin", [-30.0, 0.0, 2.0, 10.0, 30.0])
@pytest.mark.parametrize("scale", [2.0**-12, 1.0, 2.0**12])
def test_spatial_exact_axis_boundary_and_adjacent_inputs(origin: float, scale: float) -> None:
    first = Model("a", Pose.at(origin, 10, origin), CircularBase(0.5 * scale), ModelVolume(scale))
    # Horizontal disk gap3 and vertical gap4: exactly5, independently of sqrt.
    boundary_x = origin + 4 * scale
    for x in (
        math.nextafter(boundary_x, -math.inf),
        boundary_x,
        math.nextafter(boundary_x, math.inf),
    ):
        second = replace(first, model_id="b", pose=Pose.at(x, 10, origin + 5 * scale))
        horizontal = Fraction(x) - Fraction(origin) - Fraction(scale)
        vertical = Fraction(second.pose.position.z) - Fraction(origin) - Fraction(scale)
        expected = horizontal**2 + vertical**2 <= Fraction(5 * scale) ** 2
        assert first.is_within_range(second, 5 * scale) is expected
        assert second.is_within_range(first, 5 * scale) is expected
    overlap = replace(first, model_id="overlap", pose=Pose.at(origin, 10, origin + 6 * scale))
    assert first.is_within_range(overlap, 5 * scale)
    exterior = replace(
        overlap, pose=Pose.at(origin, 10, math.nextafter(overlap.pose.position.z, math.inf))
    )
    assert not first.is_within_range(exterior, 5 * scale)


@pytest.mark.parametrize("origin", [0.0, 10.0, 30.0])
def test_spatial_exact_diagonal_boundary_and_adjacent_exterior(origin: float) -> None:
    first = Model("a", Pose.at(origin, origin), CircularBase(1), ModelVolume(1))
    second = replace(first, model_id="b", pose=Pose.at(origin + 3, origin + 4, 5))
    # Center separation5, summed radii2, vertical gap4 => spatial range5.
    assert first.is_within_range(second, 5)
    exterior = replace(second, pose=Pose.at(math.nextafter(origin + 3, math.inf), origin + 4, 5))
    assert not first.is_within_range(exterior, 5)


def test_spatial_range_does_not_replace_cylindrical_engagement() -> None:
    first = Model("a", Pose.at(0, 10), CircularBase(0.5), ModelVolume(1))
    second = replace(first, model_id="b", pose=Pose.at(3, 10, 6))
    assert first.is_within_engagement_range(second, 2, 5)
    assert not first.is_within_range(second, 3)
    touching = replace(second, pose=Pose.at(1, 10, 1))
    assert first.is_within_range(touching, 0)
    overlap = replace(second, pose=Pose.at(0, 10, 0.5))
    assert first.is_within_range(overlap, 0)


@pytest.mark.parametrize("horizontal", [2.5, 2.9])
def test_spatial_native_consolidation_uses_elevated_distance(
    section09_definitions: Section02Definitions, horizontal: float
) -> None:
    # Constructed phase checkpoint with native geometry; no new roster/faction admission.
    state, unit, enemy = engaged_case(section09_definitions)
    first = geometry(unit, (Pose.at(10, 10),))[0]
    peer = geometry(enemy, (Pose.at(10, 10),), enemy=True)[0]
    x = 10 + first.base.max_radius() + peer.base.max_radius() + horizontal
    z = first.volume.height + 1
    second = geometry(enemy, (Pose.at(x, 10, z),), enemy=True)[0]
    edge = Fraction(x) - 10 - Fraction(first.base.max_radius()) - Fraction(peer.base.max_radius())
    vertical = Fraction(z) - Fraction(first.volume.height)
    expected = edge**2 + vertical**2 <= 9
    assert not first.is_within_engagement_range(second, 2, 5)
    assert first.is_within_range(second, 3) is expected
    set_pose(state, enemy, (second.pose,), enemy=True)
    modes = legal_rules_unit_consolidation_modes(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_instance_id=unit.unit_instance_id,
        objective_markers=(),
        state=state,
    )
    assert (ConsolidationModeKind.ENGAGING in modes) is expected
