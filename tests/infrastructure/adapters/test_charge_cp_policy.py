"""Exercise the opt-in Dense-wall policy through native viewer decisions and replay."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import cast

import pytest

from tests.support.faction_batch01 import Scene, anchor, locate, scene, selection
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section11_fixtures import begin, propose, roll, targets
from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.charge_declaration_session import ChargeDeclarationSession
from warhammer40k_core.ai.charge_cp_policy import (
    DenseWallChargeChoice,
    choose_dense_wall_charge,
    select_late_onslaught,
    submit_dense_wall_charge,
)
from warhammer40k_core.ai.charge_flight_admission import (
    ChargeFlightRollBound,
    ChargeFlightUnresolved,
    ChargeFlightUnresolvedReason,
    inspect_charge_flight_offer,
)
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyError, payload_digest
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.engine.charge_declaration import ChargeRollResult
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner
from warhammer40k_core.engine.stratagems_model import DECLINE_STRATAGEM_WINDOW_OPTION_ID
from warhammer40k_core.engine.stratagems_requests import stratagem_window_context_from_request
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainWallDefinition
from warhammer40k_core.geometry.terrain_classification import TerrainAreaClassification
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_daemons_cavalcade_2026_11,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_blood_legion_ir_support_2026_27 as ir,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27 as identities,
)

OWNER = "owner"
MOVER = "own:first"
TARGET = "foe:target"
START = Pose.at(10, 20)
BLOODTHIRSTER = "000002582"
VIEWER = ViewerContext.for_player(OWNER)


@pytest.fixture(scope="module")
def definitions() -> Section02Definitions:
    package = chaos_daemons_cavalcade_2026_11.catalog_package()
    catalog = package.army_catalog
    row = next(r for r in identities.detachment_rows() if r.detachment_id == "blood-legion")
    if not any(d.detachment_id == row.detachment_id for d in catalog.detachments):
        detachment = DetachmentDefinition(
            canonical_detachment_id=row.detachment_id,
            detachment_id=row.detachment_id,
            name=row.name,
            faction_id="chaos-daemons",
            detachment_point_cost=row.detachment_point_cost,
            unit_datasheet_ids=tuple(s.datasheet_id for s in catalog.datasheets),
            force_disposition_ids=tuple(
                sorted({row.force_disposition_id, "take-and-hold", "purge-the-foe"})
            ),
            source_ids=row.source_ids,
        )
        package = replace(
            package, army_catalog=replace(catalog, detachments=(*catalog.detachments, detachment))
        )
    return Section02Definitions(package, 0.0)


def _wall() -> TerrainFeatureDefinition:
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=13.25,
        center_y_inches=20,
        width_inches=1,
        depth_inches=24,
        display_template_id=None,
    )
    return TerrainFeatureDefinition(
        "charge-barrier",
        TerrainFeatureKind.BATTLEFIELD_DEBRIS_AND_STATUARY,
        13.25,
        20,
        1,
        24,
        display.footprint_polygon,
        display,
        walls=(TerrainWallDefinition("wall", 13.25, 20, 0, 1, 24, 10.5),),
        classification=TerrainAreaClassification.DENSE,
    )


@dataclass
class _ChargeScene(Scene):
    declaration: ChargeDeclarationSession


def _battle(
    definitions: Section02Definitions, cp: int, *, rng: str, y: float = START.position.y
) -> _ChargeScene:
    b = scene(
        definitions,
        (selection(definitions, BLOODTHIRSTER, "first"),),
        (selection(definitions, BLOODTHIRSTER, "target"),),
        phase=BattlePhase.CHARGE,
        detachment_id_by_faction={"chaos-daemons": "blood-legion"},
        seed="gore-hungry-onslaught",
        rng_seed_label=rng,
        terrain_features=(_wall(),),
    )
    locate(b, MOVER, (Pose.at(START.position.x, y),))
    locate(b, TARGET, (Pose.at(21, y),))
    if cp:
        b.state.gain_command_points(
            player_id=OWNER,
            amount=cp,
            source_id="charge-flight-timing:fixture",
            source_kind=CommandPointSourceKind.OTHER,
            cap_exempt=True,
        )
    anchor(b)
    return _ChargeScene(b.session, b.state, b.units, ChargeDeclarationSession(b.session))


def _context(b: Scene) -> PlayerDecisionContext:
    return PlayerDecisionContext.from_view(b.session.view_for_context(viewer=VIEWER), choice_seed=0)


def _select(b: Scene, option: str, *, result_id: str) -> None:
    status = b.session.submit_viewer_option(
        viewer=VIEWER,
        request_id=_context(b).request["request_id"],
        option_id=option,
        result_id=result_id,
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status


def _decline_before_roll(b: Scene) -> None:
    begin(b.session)
    for index in range(4):
        if _context(b).route.decision_type == "select_charging_unit":
            return
        assert _context(b).route.decision_type == "use_stratagem"
        _select(b, DECLINE_STRATAGEM_WINDOW_OPTION_ID, result_id=f"rehearse:early-{index}")
    pytest.fail("No ordinary Charge declaration")


def _witness(b: Scene, *, start: Pose = START) -> PathWitness:
    offer = inspect_charge_flight_offer(_context(b), unit_id=MOVER, target_id=TARGET).offer
    assert offer is not None
    end = Pose.at(start.position.x + offer.target_filter_distance_inches, start.position.y)
    return PathWitness.for_paths(((offer.model_id, (start, end)),))


def _assert_replay(b: Scene, *, completed: bool = True) -> None:
    events = tuple(e.event_type for e in b.session.lifecycle.decision_controller.event_log.records)
    assert events.count("dice_rolled") == 1
    assert events.index("charging_unit_selected") < events.index("dice_rolled")
    assert ("charge_move_completed" in events) is completed
    result = ReplayRunner.from_payload(
        b.session.replay_artifact(artifact_id="charge-cp-policy")
    ).run()
    assert result.reproduced_exactly, result


def _natural_roll(b: _ChargeScene, choice: DenseWallChargeChoice | None = None) -> ChargeRollResult:
    request = b.session.lifecycle.pending_decision_request()
    assert request is not None
    if request.decision_type == "use_stratagem":
        timing = stratagem_window_context_from_request(request)
        if timing.trigger_kind is TimingTriggerKind.AFTER_DICE_ROLL:
            if choice is not None:
                assert select_late_onslaught(b.declaration, _context(b), choice=choice) is None
            _select(b, DECLINE_STRATAGEM_WINDOW_OPTION_ID, result_id="finish:decline-reroll")
    return roll(b.session)


def _finish(
    b: _ChargeScene,
    witness: PathWitness,
    choice: DenseWallChargeChoice | None,
    *,
    wrong_mode: DenseWallChargeChoice | None = None,
) -> int:
    spent = 0
    for index in range(5):
        context = _context(b)
        if context.route.decision_type == "select_charge_targets":
            targets(b.session, (TARGET,))
        elif context.route.decision_type == "use_stratagem":
            before = b.session.to_persistence_payload()
            if wrong_mode is not None:
                assert select_late_onslaught(b.declaration, context, choice=wrong_mode) is None
            if choice is None:
                assert not any(
                    row["option_id"].startswith(
                        f"use-stratagem:{ir.GORE_HUNGRY_ONSLAUGHT_STRATAGEM_ID}:"
                    )
                    for row in context.request["options"]
                )
            action = (
                None
                if choice is None
                else select_late_onslaught(b.declaration, context, choice=choice)
            )
            assert b.session.to_persistence_payload() == before
            if action is None:
                _select(b, DECLINE_STRATAGEM_WINDOW_OPTION_ID, result_id=f"finish:decline-{index}")
            else:
                assert action.request_id == context.request["request_id"]
                assert action.observation_hash == context.observation_hash
                assert action.option_id is not None
                _select(b, action.option_id, result_id="finish:accept")
                assert choice is not None
                assert select_late_onslaught(b.declaration, context, choice=choice) is None
                spent += 1
        else:
            assert context.route.decision_type == "submit_movement_proposal"
            status = propose(b.session, MOVER, (TARGET,), witness)
            assert status.status_kind is not LifecycleStatusKind.INVALID, status
            return spent
    pytest.fail("No native Charge path request")


@pytest.mark.parametrize(
    ("cp", "allow_spend", "rng", "flies", "expected_roll"),
    [
        (1, False, "dense-cp-policy-7", True, 10),
        (1, True, "dense-cp-policy-0", False, 8),
        (0, True, "dense-cp-policy-5", True, 9),
        (1, True, "dense-cp-policy-11", False, 6),
    ],
    ids=["keep-cp", "conditional-ground", "unaffordable", "short-roll"],
)
def test_dense_wall_policy_submits_native_modes_and_costs(
    definitions: Section02Definitions,
    *,
    cp: int,
    allow_spend: bool,
    rng: str,
    flies: bool,
    expected_roll: int,
) -> None:
    b = _battle(definitions, cp, rng=rng)
    _decline_before_roll(b)
    witness = _witness(b)
    context = _context(b)
    before = b.session.to_persistence_payload()
    choice = choose_dense_wall_charge(
        b.session,
        context,
        unit_id=MOVER,
        target_id=TARGET,
        witness=witness,
        allow_late_onslaught=allow_spend,
    )
    assert isinstance(choice, DenseWallChargeChoice), choice
    wrong_mode = None
    if not allow_spend:
        alternative = choose_dense_wall_charge(
            b.session,
            context,
            unit_id=MOVER,
            target_id=TARGET,
            witness=witness,
            allow_late_onslaught=True,
        )
        assert isinstance(alternative, DenseWallChargeChoice)
        assert alternative.conditional_ground is not None
        wrong_mode = alternative
    assert b.session.to_persistence_payload() == before
    assert b.state.command_point_total(OWNER) == cp
    assert not b.state.stratagem_use_records
    assert choice.no_spend.flight_lower_bound == ChargeFlightRollBound((9, 10, 11, 12), 10)
    assert choice.no_spend.ground_upper_bound == ChargeFlightRollBound((11, 12), 3)
    assert choice.conditional_ground == (
        None if flies else ChargeFlightRollBound((7, 8, 9, 10, 11, 12), 21)
    )
    assert choice.declaration.request_id == context.request["request_id"]
    assert choice.declaration.observation_hash == context.observation_hash
    status = submit_dense_wall_charge(b.declaration, choice=choice)
    assert status.status_kind is not LifecycleStatusKind.INVALID, status

    actual = _natural_roll(b, choice)
    assert actual.value == expected_roll
    assert actual.request.take_to_the_skies is flies
    assert actual.movement_budget.maximum_distance_inches == actual.value - 2 * int(flies)
    short = expected_roll < 7
    if short:
        assert not actual.move_available
        assert select_late_onslaught(b.declaration, _context(b), choice=choice) is None
        spent = 0
    else:
        assert actual.move_available, actual.value
        spent = _finish(b, witness, choice, wrong_mode=wrong_mode)
    assert spent == int(not (short or flies))
    assert b.state.command_point_total(OWNER) == cp - spent
    assert [
        (use.stratagem_id, use.targeted_unit_instance_ids, use.command_point_cost)
        for use in b.state.stratagem_use_records
    ] == [(ir.GORE_HUNGRY_ONSLAUGHT_STRATAGEM_ID, (MOVER,), 1)] * spent
    _assert_replay(b, completed=not short)


def test_used_phase_allowance_cannot_be_spent_again(definitions: Section02Definitions) -> None:
    b = _battle(definitions, 2, rng="dense-cp-policy-0")
    early = begin(b.session)
    (option,) = tuple(
        row.option_id
        for row in early.options
        if row.option_id.startswith(f"use-stratagem:{ir.GORE_HUNGRY_ONSLAUGHT_STRATAGEM_ID}:")
    )
    _select(b, option, result_id="rehearse:early-0")
    witness = _witness(b)
    context = _context(b)
    before = b.session.to_persistence_payload()
    result = choose_dense_wall_charge(
        b.session,
        context,
        unit_id=MOVER,
        target_id=TARGET,
        witness=witness,
        allow_late_onslaught=True,
    )
    assert result == ChargeFlightUnresolved(ChargeFlightUnresolvedReason.UNSUPPORTED_PROOF_CONTEXT)
    assert b.session.to_persistence_payload() == before
    offer = inspect_charge_flight_offer(context, unit_id=MOVER, target_id=TARGET).offer
    assert offer is not None
    _select(b, offer.ground_option_id, result_id="rehearse:ground")
    actual = _natural_roll(b)
    assert actual.value == 7
    assert actual.move_available
    assert _finish(b, witness, None) == 0
    assert len(b.state.stratagem_use_records) == 1
    assert b.state.command_point_total(OWNER) == 1
    _assert_replay(b)


@pytest.mark.parametrize("value", ["false", 1, None], ids=["string-false", "integer", "null"])
def test_late_onslaught_opt_in_requires_boolean(
    definitions: Section02Definitions, value: object
) -> None:
    b = _battle(definitions, 1, rng="dense-cp-policy-1")
    _decline_before_roll(b)
    before = b.session.to_persistence_payload()
    with pytest.raises(PolicyError, match="allow_late_onslaught requires a Boolean"):
        choose_dense_wall_charge(
            b.session,
            _context(b),
            unit_id=MOVER,
            target_id=TARGET,
            witness=_witness(b),
            allow_late_onslaught=cast(bool, value),
        )
    assert b.session.to_persistence_payload() == before


def _conditional_plan(b: Scene) -> DenseWallChargeChoice:
    choice = choose_dense_wall_charge(
        b.session,
        _context(b),
        unit_id=MOVER,
        target_id=TARGET,
        witness=_witness(b),
        allow_late_onslaught=True,
    )
    assert isinstance(choice, DenseWallChargeChoice)
    assert choice.conditional_ground is not None
    return choice


def _assert_live_onslaught_offer(context: PlayerDecisionContext) -> None:
    assert any(
        row["option_id"].startswith(f"use-stratagem:{ir.GORE_HUNGRY_ONSLAUGHT_STRATAGEM_ID}:")
        for row in context.request["options"]
    )


def test_late_onslaught_rejects_charge_plan_from_different_position(
    definitions: Section02Definitions,
) -> None:
    origin = _battle(definitions, 1, rng="dense-cp-policy-11")
    _decline_before_roll(origin)
    initial = _context(origin)
    choice = _conditional_plan(origin)

    clear = _battle(definitions, 1, rng="dense-cp-policy-11", y=36)
    _decline_before_roll(clear)
    visible = _context(clear)
    clear_witness = _witness(clear, start=Pose.at(START.position.x, 36))
    assert visible.observation["game_id"] == initial.observation["game_id"]
    assert visible.route == initial.route
    assert visible.request == initial.request
    assert visible.observation_hash != initial.observation_hash
    before = clear.session.to_persistence_payload()
    with pytest.raises(PolicyError, match="declaration no longer matches its observation"):
        submit_dense_wall_charge(clear.declaration, choice=choice)
    assert clear.session.to_persistence_payload() == before

    # Recompute the former result-ID binding using the stale plan and live board.
    # The session accepts the native declaration on the live observation only.
    battlefield = visible.observation["battlefield_view"]
    assert battlefield is not None
    action = choice.declaration
    supplied_id = "dense-wall-charge:" + payload_digest(
        [
            choice.game_id,
            action.actor_id,
            action.request_id,
            action.observation_hash,
            action.option_id,
            TARGET,
            choice.no_spend.witness_sha256,
            battlefield["authoritative"],
        ]
    )
    status = clear.declaration.submit_observed_charge_declaration(
        viewer=VIEWER,
        request_id=action.request_id,
        option_id=choice.no_spend.offer.ground_option_id,
        result_id=supplied_id,
        expected_observation_hash=visible.observation_hash,
    )
    assert status is not None
    assert status.status_kind is not LifecycleStatusKind.INVALID
    actual = _natural_roll(clear, choice)
    assert actual.request.source_decision_result_id == supplied_id
    assert actual.move_available
    _assert_live_onslaught_offer(_context(clear))
    assert _finish(clear, clear_witness, choice) == 0
    assert clear.state.command_point_total(OWNER) == 1
    assert not clear.state.stratagem_use_records
    _assert_replay(clear)


def test_late_onslaught_rejects_charge_plan_when_cp_changed_before_declaration(
    definitions: Section02Definitions,
) -> None:
    rng = "dense-cp-policy-0"
    origin = _battle(definitions, 1, rng=rng)
    _decline_before_roll(origin)
    initial = _context(origin)
    choice = _conditional_plan(origin)
    assert submit_dense_wall_charge(origin.declaration, choice=choice).status_kind is not (
        LifecycleStatusKind.INVALID
    )
    original = _natural_roll(origin, choice)
    assert original.move_available

    prepared = _battle(definitions, 2, rng=rng)
    _decline_before_roll(prepared)
    visible = _context(prepared)
    assert visible.observation["battlefield_view"] == initial.observation["battlefield_view"]
    assert visible.observation["game_id"] == initial.observation["game_id"]
    assert visible.route == initial.route
    assert visible.request == initial.request
    assert visible.observation_hash != initial.observation_hash
    before = prepared.session.to_persistence_payload()
    with pytest.raises(PolicyError, match="declaration no longer matches its observation"):
        submit_dense_wall_charge(prepared.declaration, choice=choice)
    assert prepared.session.to_persistence_payload() == before

    status = prepared.declaration.submit_observed_charge_declaration(
        viewer=VIEWER,
        request_id=choice.declaration.request_id,
        option_id=choice.no_spend.offer.ground_option_id,
        result_id=original.request.source_decision_result_id,
        expected_observation_hash=visible.observation_hash,
    )
    assert status is not None
    assert status.status_kind is not LifecycleStatusKind.INVALID
    actual = _natural_roll(prepared, choice)
    assert actual.request.source_decision_result_id == original.request.source_decision_result_id
    assert actual.move_available
    late = _context(prepared)
    _assert_live_onslaught_offer(late)
    before = prepared.session.to_persistence_payload()
    assert select_late_onslaught(prepared.declaration, late, choice=choice) is None
    assert prepared.session.to_persistence_payload() == before
    _select(prepared, DECLINE_STRATAGEM_WINDOW_OPTION_ID, result_id="finish:decline-onslaught")
    assert prepared.state.command_point_total(OWNER) == 2
    assert not prepared.state.stratagem_use_records
    _assert_replay(prepared, completed=False)
