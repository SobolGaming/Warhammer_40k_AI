"""15.07/15.11/15.12 at their existing interruption and target decision owners."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section15_fixtures import binding, checkpoint, context, offer, request, submit
from warhammer40k_core.core.ruleset_descriptor import FightPhaseStepKind
from warhammer40k_core.engine.charge_phase_state import ChargePhaseState
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.fight_order import FightPhaseState, FightsFirstRegistry
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.reserves import ReserveKind, ReserveState
from warhammer40k_core.engine.stratagem_catalog import eleventh_edition_core_stratagem_index
from warhammer40k_core.engine.stratagems import stratagem_target_proposal_from_index
from warhammer40k_core.engine.timing_windows import TimingTriggerKind


@pytest.mark.parametrize("aircraft", [False, True])
def test_rapid_ingress_excludes_aircraft_with_same_native_reserve_control(
    section15_definitions: Section02Definitions, aircraft: bool
) -> None:
    from dataclasses import replace

    from tests.unit_keyword_helpers import with_unit_keywords

    _session, state, unit, _ = checkpoint(
        section15_definitions,
        phase=BattlePhase.MOVEMENT,
        active="opponent",
        materialize=False,
    )
    state.battle_round = 2
    army = state.army_definition_for_player("owner")
    assert army is not None
    native = army.unit_by_id(unit)
    if aircraft:
        # Explicit keyword contract on unchanged supported native models/bases.
        supplemented = with_unit_keywords(native, keywords=(*native.keywords, "AIRCRAFT"))
        assert supplemented.own_model_ids() == native.own_model_ids()
        assert [m.geometry for m in supplemented.own_models] == [
            m.geometry for m in native.own_models
        ]
        state.army_definitions[:] = [
            replace(a, units=(supplemented,)) if a.player_id == "owner" else a
            for a in state.army_definitions
        ]
    assert state.battlefield_state is not None
    state.replace_battlefield_state(state.battlefield_state.without_unit_placement(unit))
    state.record_reserve_state(
        ReserveState.declared_before_battle(
            player_id="owner", unit_instance_id=unit, reserve_kind=ReserveKind.STRATEGIC_RESERVES
        )
    )
    before = state.to_payload()
    proposal = stratagem_target_proposal_from_index(
        state=state,
        index=eleventh_edition_core_stratagem_index(),
        context=context(state, TimingTriggerKind.END_PHASE),
        handler_id="core:rapid-ingress",
        require_legal_affordable_target=True,
    )
    assert (proposal is None) is aircraft
    assert state.to_payload() == before


@pytest.mark.parametrize(
    ("round_number", "active", "kind", "legal"),
    [
        (1, "opponent", ReserveKind.STRATEGIC_RESERVES, False),
        (2, "owner", ReserveKind.STRATEGIC_RESERVES, False),
        (2, "opponent", ReserveKind.RESERVES, False),
        (2, "opponent", ReserveKind.STRATEGIC_RESERVES, True),
    ],
)
def test_rapid_ingress_only_opponent_end_movement_after_round_one_from_strategic_reserves(
    section15_definitions: Section02Definitions,
    round_number: int,
    active: str,
    kind: ReserveKind,
    legal: bool,
) -> None:
    session, state, unit, _ = checkpoint(
        section15_definitions, phase=BattlePhase.MOVEMENT, active=active
    )
    state.battle_round = round_number
    own = state.army_definition_for_player("owner")
    assert own is not None
    assert state.battlefield_state is not None
    state.replace_battlefield_state(state.battlefield_state.without_unit_placement(unit))
    state.record_reserve_state(
        ReserveState.declared_before_battle(
            player_id="owner",
            unit_instance_id=unit,
            reserve_kind=kind,
        )
    )
    ctx = context(state, TimingTriggerKind.END_PHASE)
    before = state.to_payload()
    proposal = stratagem_target_proposal_from_index(
        state=state,
        index=eleventh_edition_core_stratagem_index(),
        context=ctx,
        handler_id="core:rapid-ingress",
        require_legal_affordable_target=True,
    )
    assert (proposal is not None) is legal
    assert state.to_payload() == before
    if legal:
        req = offer(session, state, "rapid-ingress", ctx)
        placement = request(submit(session, req, unit))
        assert placement.decision_type == "submit_placement_proposal"
        assert state.command_point_total("owner") == 3
        reserve = state.reserve_state_for_unit(unit)
        assert reserve is not None
        assert reserve.status.value == "in_reserves"
        assert state.battlefield_state.unit_placement_or_none(unit) is None
        prior = session.lifecycle.to_payload()
        invalid = session.submit_parameterized_payload(
            request_id=placement.request_id,
            result_id="s15:bad-placement",
            payload=None,
        )
        assert invalid.status_kind is LifecycleStatusKind.INVALID
        assert session.lifecycle.to_payload() == prior
        from tests.support.section03_fixtures import placement as native_placement
        from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind
        from warhammer40k_core.engine.movement_proposals import (
            PlacementProposalPayload,
            ProposalKind,
        )
        from warhammer40k_core.geometry.pose import Pose

        placed = native_placement(own.unit_by_id(unit), (Pose.at(1, 22),))
        payload = PlacementProposalPayload(
            placement.request_id,
            ProposalKind.STRATEGIC_RESERVES,
            unit,
            BattlefieldPlacementKind.STRATEGIC_RESERVES,
            attempted_placement=placed,
        )
        status = session.submit_parameterized_payload(
            request_id=placement.request_id,
            result_id="s15:legal-ingress",
            payload=validate_json_value(payload.to_payload()),
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID
        arrived = state.reserve_state_for_unit(unit)
        assert arrived is not None
        assert arrived.status.value == "arrived"
        assert state.battlefield_state.unit_placement_by_id(unit).model_placements[
            0
        ].pose == Pose.at(1, 22)


@pytest.mark.parametrize(("mode", "cp"), [("leap_to_defend", 1), ("into_the_fray", 2)])
def test_heroic_intervention_enters_real_charge_with_mode_chosen_before_roll(
    section15_definitions: Section02Definitions, mode: str, cp: int
) -> None:
    session, state, unit, enemy = checkpoint(
        section15_definitions, phase=BattlePhase.CHARGE, active="opponent", distance=5
    )
    # Explicit completed enemy Charge checkpoint; no earlier charge is certified.
    state.charge_phase_state = ChargePhaseState(
        state.battle_round,
        "opponent",
        phase_complete=True,
        declared_target_unit_instance_ids_by_unit={enemy: (unit,)},
    )
    req = offer(session, state, "heroic-intervention", context(state, TimingTriggerKind.END_PHASE))
    selection = request(submit(session, req, unit, effect={"mode": mode}))
    assert selection.decision_type == "select_charging_unit"
    assert unit in {o.option_id for o in selection.options}
    assert state.command_point_total("owner") == 4 - cp
    interrupted = state.charge_phase_state
    assert interrupted is not None
    assert interrupted.interruption is not None
    assert interrupted.interruption.allowed_target_ids == (
        None if mode == "into_the_fray" else (enemy,)
    )
    assert interrupted.interruption.target_range_inches == (6 if mode == "into_the_fray" else 12)
    assert (interrupted.interruption.roll_limit is not None) is (mode == "into_the_fray")
    assert state.active_player_id == "opponent"
    assert state.effective_active_player_id() == "owner"
    targets = request(
        session.submit_option(
            request_id=selection.request_id, result_id="s15:charge", option_id=unit
        )
    )
    assert targets.decision_type == "select_charge_targets"
    assert state.charge_phase_state.distance_states
    roll = state.charge_phase_state.distance_states[-1].roll_result
    assert len(roll.roll_state.current_values) == 2
    if mode == "into_the_fray":
        assert roll.value <= 6


@pytest.mark.parametrize(
    ("sheet", "legal"), [("000004078", True), ("000000968", True), ("000000599", False)]
)
def test_heroic_native_vehicle_exception_requires_character_or_walker(
    section15_definitions: Section02Definitions, sheet: str, legal: bool
) -> None:
    from warhammer40k_core.engine.stratagems_geometry import (
        _heroic_intervention_target_binding_error,
    )

    _session, state, unit, _ = checkpoint(
        section15_definitions, sheet=sheet, phase=BattlePhase.CHARGE, active="opponent", distance=8
    )
    reason = _heroic_intervention_target_binding_error(
        state=state, player_id="owner", target_binding=binding(unit)
    )
    assert (reason is None) is legal
    if not legal:
        assert reason == "heroic_intervention_vehicle_not_character_or_walker"


@pytest.mark.parametrize("active", ["owner", "opponent"])
def test_counteroffensive_own_turn_denial_and_opponent_turn_fights_first_activation(
    section15_definitions: Section02Definitions, active: str
) -> None:
    session, state, unit, enemy = checkpoint(section15_definitions, active=active, distance=2)
    policy = state.runtime_ruleset_descriptor().fight_policy
    state.fight_phase_state = FightPhaseState.start(
        battle_round=state.battle_round,
        active_player_id=active,
        policy=policy,
        engaged_at_fight_step_start_unit_ids=(unit, enemy),
        fights_first_registry=FightsFirstRegistry(),
    ).with_current_step(current_step=FightPhaseStepKind.FIGHT, policy=policy)
    ctx = context(
        state,
        TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_HAS_FOUGHT,
        {"fought_unit_instance_id": enemy, "eligible_unit_instance_ids": [unit]},
    )
    proposal = stratagem_target_proposal_from_index(
        state=state,
        index=eleventh_edition_core_stratagem_index(),
        context=ctx,
        handler_id="core:counteroffensive",
        require_legal_affordable_target=True,
    )
    assert (proposal is not None) is (active == "opponent")
    if active == "opponent":
        req = offer(session, state, "counteroffensive", ctx)
        status = submit(session, req, unit)
        assert status.status_kind is not LifecycleStatusKind.INVALID
        fight = state.fight_phase_state
        assert fight is not None
        assert fight.active_activation is not None
        assert fight.active_activation.unit_instance_id == unit
        assert state.command_point_total("owner") == 2
        assert any(
            isinstance(e.effect_payload, dict)
            and e.effect_payload.get("effect_kind") == "fights_first"
            for e in state.persisting_effects
        )
