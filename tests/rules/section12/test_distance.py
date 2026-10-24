"""FAQ10-12 belong to their Pile In and Consolidation consumers."""

from __future__ import annotations

from typing import cast

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section12_fixtures import (
    begin,
    checkpoint,
    engaged_case,
    events,
    paths,
    select_fight,
    session_for,
    set_pose,
    submit_move,
)
from warhammer40k_core.core.ruleset_descriptor import ConsolidationModeKind, FightPhaseStepKind
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.fight_activation_abilities import (
    FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND,
)
from warhammer40k_core.engine.fight_resolution import fight_movement_maximum_distance_inches
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest, ProposalKind
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


def _distance(s: GameState, unit_id: str) -> None:
    source = "constructed:section12:extra-distance"
    s.record_persisting_effect(
        PersistingEffect(
            effect_id=source,
            source_rule_id=source,
            owner_player_id="owner",
            target_unit_instance_ids=(unit_id,),
            started_battle_round=1,
            started_phase=BattlePhase.FIGHT,
            expiration=EffectExpiration.end_phase(
                battle_round=1, phase=BattlePhase.FIGHT, player_id="owner"
            ),
            effect_payload={
                "effect_kind": FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND,
                "source_id": source,
                "pile_in_distance_inches": 6.0,
                "consolidate_distance_inches": 5.0,
            },
        )
    )


@pytest.mark.parametrize("kind", [ProposalKind.PILE_IN, ProposalKind.CONSOLIDATE])
@pytest.mark.parametrize("step", list(FightPhaseStepKind))
@pytest.mark.parametrize("phase", [BattlePhase.FIGHT, BattlePhase.SHOOTING])
def test_extra_distance_is_only_consumed_in_its_matching_fight_step(
    section12_definitions: Section02Definitions,
    kind: ProposalKind,
    step: FightPhaseStepKind,
    phase: BattlePhase,
) -> None:
    s, u, _ = engaged_case(section12_definitions)
    _distance(s, u.unit_instance_id)
    checkpoint(s, step)
    s.battle_phase_index = s.battle_phase_sequence.index(phase)
    matching = (
        FightPhaseStepKind.PILE_IN
        if kind is ProposalKind.PILE_IN
        else FightPhaseStepKind.CONSOLIDATE
    )
    actual = fight_movement_maximum_distance_inches(
        state=s, unit_instance_id=u.unit_instance_id, proposal_kind=kind
    )
    assert actual == (
        (6 if kind is ProposalKind.PILE_IN else 5)
        if step is matching and phase is BattlePhase.FIGHT
        else 3
    )


@pytest.mark.parametrize("kind", [ProposalKind.PILE_IN, ProposalKind.CONSOLIDATE])
@pytest.mark.parametrize("extra", [False, True])
def test_actual_witness_budget_changes_with_extra_distance_at_matching_step(
    section12_definitions: Section02Definitions, kind: ProposalKind, extra: bool
) -> None:
    s, u, e = engaged_case(section12_definitions)
    if extra:
        _distance(s, u.unit_instance_id)
    checkpoint(
        s,
        FightPhaseStepKind.PILE_IN
        if kind is ProposalKind.PILE_IN
        else FightPhaseStepKind.CONSOLIDATE,
    )
    session = session_for(section12_definitions, s)
    r = begin(session)
    m = MovementProposalRequest.from_decision_request_payload(r.payload)
    assert m.context is not None
    assert m.context["maximum_distance_inches"] == (
        (6 if kind is ProposalKind.PILE_IN else 5) if extra else 3
    )
    witness = PathWitness.for_paths(
        (
            (
                u.own_model_ids()[0],
                (Pose.at(10, 10), Pose.at(10, 11.6), Pose.at(10.25, 11.6), Pose.at(10.25, 10)),
            ),
        )
    )
    before = s.battlefield_state
    result = submit_move(
        session,
        targets=(e.unit_instance_id,),
        mode=ConsolidationModeKind.ONGOING if kind is ProposalKind.CONSOLIDATE else None,
        witness=witness,
    )
    assert (result.status_kind is not LifecycleStatusKind.INVALID) == extra, result.to_payload()
    assert (s.battlefield_state != before) == extra
    if not extra:
        result = submit_move(session, identity="decline")
        assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
    assert len(events(session, "fight_movement_completed")) == 1


@pytest.mark.parametrize("kind", [ProposalKind.PILE_IN, ProposalKind.CONSOLIDATE])
def test_extra_movement_does_not_expand_native_enemy_target_selection_distance(
    section12_definitions: Section02Definitions, kind: ProposalKind
) -> None:
    s, u, e = engaged_case(section12_definitions)
    _distance(s, u.unit_instance_id)
    limit = 5 if kind is ProposalKind.PILE_IN else 3
    set_pose(s, e, (Pose.at(10 + 1.574803149606299 + limit + 0.001, 10),), enemy=True)
    # A charge permission at this explicit checkpoint admits unengaged Pile In.
    if kind is ProposalKind.PILE_IN:
        s.record_persisting_effect(
            PersistingEffect(
                effect_id="constructed:charged",
                source_rule_id="constructed:charged",
                owner_player_id="owner",
                target_unit_instance_ids=(u.unit_instance_id,),
                started_battle_round=1,
                started_phase=BattlePhase.CHARGE,
                expiration=EffectExpiration.end_turn(battle_round=1, player_id="owner"),
                effect_payload={"effect_kind": "charge_grants_fights_first"},
            )
        )
    checkpoint(
        s,
        FightPhaseStepKind.PILE_IN
        if kind is ProposalKind.PILE_IN
        else FightPhaseStepKind.CONSOLIDATE,
    )
    from tests.support.section03_fixtures import scenario
    from tests.support.section12_fixtures import LORD, add_native
    from warhammer40k_core.engine.fight_rules_unit_movement import (
        legal_rules_unit_consolidation_modes,
        legal_rules_unit_pile_in_target_unit_ids,
    )

    if kind is ProposalKind.PILE_IN:
        assert e.unit_instance_id not in legal_rules_unit_pile_in_target_unit_ids(
            scenario=scenario(s),
            ruleset_descriptor=s.runtime_ruleset_descriptor(),
            unit_instance_id=u.unit_instance_id,
            state=s,
        )
    else:
        assert not legal_rules_unit_consolidation_modes(
            scenario=scenario(s),
            ruleset_descriptor=s.runtime_ruleset_descriptor(),
            unit_instance_id=u.unit_instance_id,
            objective_markers=(),
            state=s,
        )
    # A second engaged pair keeps continuation inside this Fight boundary.
    spare = section12_definitions.unit(LORD, identity="z-sentinel")
    foe = section12_definitions.unit(LORD, identity="z-sentinel", army_id="enemy")
    add_native(s, spare, (Pose.at(10, 30),))
    add_native(s, foe, (Pose.at(13, 30),), enemy=True)
    session = session_for(section12_definitions, s)
    r = begin(session)
    assert all(
        cast(str, x["unit_instance_id"]) != u.unit_instance_id
        for x in events(session, "fight_movement_requested")
    )
    m = MovementProposalRequest.from_decision_request_payload(r.payload)
    assert m.unit_instance_id == spare.unit_instance_id
    result = submit_move(session, identity="continue")
    assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()


def test_overrun_additional_pile_in_keeps_three_inches_despite_extra_step_permission(
    section12_definitions: Section02Definitions,
) -> None:
    s, u, e = engaged_case(section12_definitions)
    _distance(s, u.unit_instance_id)
    set_pose(s, e, (Pose.at(14.5, 10),), enemy=True)
    checkpoint(s, FightPhaseStepKind.FIGHT)
    session = session_for(section12_definitions, s)
    begin(session)
    r = select_fight(session, u.unit_instance_id, "overrun")
    m = MovementProposalRequest.from_decision_request_payload(r.payload)
    assert m.context is not None
    assert m.context["fight_movement_timing"] == "overrun"
    assert m.context["maximum_distance_inches"] == 3
    witness = PathWitness.for_paths(
        (
            (
                u.own_model_ids()[0],
                (Pose.at(10, 10), Pose.at(10, 11.5), Pose.at(11, 11.5), Pose.at(11, 10)),
            ),
        )
    )
    before = s.battlefield_state
    result = submit_move(session, targets=(e.unit_instance_id,), witness=witness)
    assert result.status_kind is LifecycleStatusKind.INVALID, result.to_payload()
    assert s.battlefield_state == before
    result = submit_move(
        session,
        targets=(e.unit_instance_id,),
        witness=paths(s, (u.unit_instance_id,), 1),
        identity="core-three",
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
