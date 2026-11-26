"""Native Counteroffensive after an enemy Overrun newly engages a unit."""

import json
from typing import cast

import pytest

from tests.order135_counteroffensive_helpers import proposal_from_native_request
from tests.support.faction_batch01 import (
    LORD,
    anchor,
    faction_definitions,
    locate,
    scene,
    selection,
)
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section04_fixtures import pending
from tests.support.section12_fixtures import (
    begin,
    checkpoint,
    melee_payload,
    paths,
    select_fight,
    submit_move,
)
from tests.support.section15_fixtures import binding
from tests.twin_linked_helpers import submit_next
from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.ruleset_descriptor import FightEligibilityKind, FightPhaseStepKind
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.decision_request import DecisionRequestPayload
from warhammer40k_core.engine.effects import EffectExpiration
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.fight_order import (
    FIGHTS_FIRST_EFFECT_KIND,
    unit_is_currently_engaged,
)
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest, ProposalKind
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.stratagems import (
    StratagemTargetProposal,
    StratagemTargetProposalPayload,
    stratagem_decline_payload,
)
from warhammer40k_core.geometry.pose import Pose

__all__ = ("faction_definitions",)

LATE = "foe:late-first"
ORIGINAL = "foe:target"
REACTOR = "opponent"


def _after_enemy_overrun(
    definitions: Section02Definitions, *, single_overrun: bool
) -> LocalGameSession:
    prepared = scene(
        definitions,
        (selection(definitions, LORD, "subject"),),
        (selection(definitions, LORD, "target"), selection(definitions, LORD, "late-first")),
        phase=BattlePhase.FIGHT,
        seed="section12",
    )
    state = prepared.state
    session = prepared.session
    attacker = prepared.units["own:subject"]
    locate(prepared, attacker.unit_instance_id, (Pose.at(10, 10),))
    locate(prepared, ORIGINAL, (Pose.at(13, 10),))
    locate(prepared, LATE, (Pose.at(10, 15.2 if single_overrun else 14.3),))
    assert not unit_is_currently_engaged(state=state, unit_instance_id=LATE)
    # For the sole Overrun case, LATE was engaged at Fight-step start and now has
    # no enemy in Engagement Range. The earlier disengagement is a fixture premise.
    checkpoint(
        state,
        FightPhaseStepKind.FIGHT,
        engaged_ids=(LATE, ORIGINAL) if single_overrun else (ORIGINAL,),
    )
    state.gain_command_points(
        player_id=REACTOR,
        amount=4,
        source_id="counteroffensive-test:starting-cp",
        source_kind=CommandPointSourceKind.OTHER,
        cap_exempt=True,
    )
    anchor(prepared)
    select_fight(session, attacker.unit_instance_id, "overrun")
    move = submit_move(
        session,
        targets=(ORIGINAL,),
        witness=paths(state, (attacker.unit_instance_id,), 0.25, 0.8),
    )
    assert move.status_kind is not LifecycleStatusKind.INVALID, move
    assert unit_is_currently_engaged(state=state, unit_instance_id=LATE) == (not single_overrun)
    melee = pending(session)
    assert melee.decision_type == "submit_melee_declaration"
    payload = melee_payload(melee)
    assert isinstance(payload, dict)
    declarations = payload["declarations"]
    assert isinstance(declarations, list)
    (declaration,) = declarations
    assert isinstance(declaration, dict)
    declaration["target_allocations"] = [{"target_unit_instance_id": ORIGINAL}]
    attack = session.submit_parameterized_payload(
        request_id=melee.request_id,
        result_id="counteroffensive-test:enemy-attack",
        payload=validate_json_value(payload),
    )
    assert attack.status_kind is not LifecycleStatusKind.INVALID, attack
    for _ in range(30):
        request = begin(session)
        if request.decision_type == "submit_stratagem_target_proposal":
            proposal = proposal_from_native_request(request)
            if proposal.stratagem_id == "counteroffensive":
                assert request.actor_id == REACTOR
                trigger = proposal.context.trigger_payload
                assert isinstance(trigger, dict)
                assert trigger["fought_unit_instance_id"] == attacker.unit_instance_id
                assert trigger["eligible_unit_instance_ids"] == [LATE, ORIGINAL]
                return session
        assert request.decision_type not in {
            "select_fight_activation",
            "submit_melee_declaration",
            "submit_movement_proposal",
        }, request
        submit_next(session, request)
    raise AssertionError("Enemy Overrun did not reach the native Counteroffensive window.")


def _restore(session: LocalGameSession) -> LocalGameSession:
    # Loading verifies the persisted decisions and event tail by replay.
    payload = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(payload)
    assert restored.to_persistence_payload() == payload
    return restored


def _viewer_request(session: LocalGameSession, viewer: ViewerContext) -> DecisionRequestPayload:
    visible = session.view_for_context(viewer=viewer)["pending_decision"]
    assert visible is not None
    return visible


@pytest.mark.parametrize("branch", ["decline", "normal", "overrun", "single-overrun"])
def test_counteroffensive_preserves_native_fight_type(
    faction_definitions: Section02Definitions, branch: str
) -> None:
    single_overrun = branch == "single-overrun"
    session = _after_enemy_overrun(faction_definitions, single_overrun=single_overrun)
    state = session.lifecycle.state
    assert state is not None
    assert state.fight_phase_state is not None
    next_player = state.fight_phase_state.fight_order_state.next_player_id
    viewer = ViewerContext.for_player(REACTOR)
    other_viewer = ViewerContext.for_player("owner")
    issued = _viewer_request(session, viewer)
    assert isinstance(issued["payload"], dict)
    proposal = StratagemTargetProposal.from_payload(
        cast(StratagemTargetProposalPayload, issued["payload"]["proposal_request"])
    )
    proposal = proposal.with_binding(binding(LATE, REACTOR))
    status = session.submit_viewer_parameterized_payload(
        viewer=viewer,
        request_id=issued["request_id"],
        result_id=f"counteroffensive-test:{branch}",
        payload=(
            stratagem_decline_payload()
            if branch == "decline"
            else validate_json_value({"proposal": proposal.to_payload()})
        ),
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION, status
    assert state.command_point_total(REACTOR) == (4 if branch == "decline" else 2)
    request = pending(session)
    if branch == "decline":
        assert not state.stratagem_use_records
        assert request.decision_type == "select_fight_activation"
        assert request.actor_id == REACTOR
        late_options = [o.option_id for o in request.options if o.option_id.endswith(LATE)]
        assert late_options == [f"fight:normal:{LATE}", f"fight:overrun:{LATE}"]
        _restore(session)
        return

    (use,) = state.stratagem_use_records
    assert use.targeted_unit_instance_ids == (LATE,)
    assert use.command_point_cost == 2
    (effect,) = (
        effect
        for effect in state.persisting_effects_for_unit(LATE)
        if effect.effect_id == f"{use.use_id}:counteroffensive:fights-first"
    )
    assert effect.source_rule_id == use.source_id
    assert effect.owner_player_id == REACTOR
    assert isinstance(effect.effect_payload, dict)
    assert effect.effect_payload["effect_kind"] == FIGHTS_FIRST_EFFECT_KIND
    assert effect.expiration == EffectExpiration.end_phase(
        battle_round=1, phase=BattlePhase.FIGHT, player_id="owner"
    )
    if not single_overrun:
        assert state.fight_phase_state is not None
        assert state.fight_phase_state.active_activation is None
        assert request.decision_type == "select_fight_activation"
        assert request.actor_id == REACTOR
        assert [option.option_id for option in request.options] == [
            f"fight:normal:{LATE}",
            f"fight:overrun:{LATE}",
        ]
        choice = _viewer_request(session, viewer)
        assert _viewer_request(session, other_viewer)["actor_id"] == REACTOR
        with pytest.raises(GameLifecycleError, match="Viewer does not own the pending decision"):
            session.submit_viewer_option(
                viewer=other_viewer,
                request_id=choice["request_id"],
                option_id=choice["options"][0]["option_id"],
                result_id="counteroffensive-test:wrong-viewer",
            )
        session = _restore(session)
        assert _viewer_request(session, viewer) == choice
        restored_state = session.lifecycle.state
        assert restored_state is not None
        assert effect in restored_state.persisting_effects_for_unit(LATE)
        status = session.submit_viewer_option(
            viewer=viewer,
            request_id=choice["request_id"],
            option_id=next(
                option["option_id"]
                for option in choice["options"]
                if isinstance(option["payload"], dict) and option["payload"]["fight_type"] == branch
            ),
            result_id=f"counteroffensive-test:choose-{branch}",
        )
        assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION, status

    state = session.lifecycle.state
    assert state is not None
    assert state.fight_phase_state is not None
    activation = state.fight_phase_state.active_activation
    assert activation is not None
    assert activation.unit_instance_id == LATE
    expected_type = "normal" if branch == "normal" else "overrun"
    assert activation.fight_type.value == expected_type
    if single_overrun:
        assert activation.eligibility_reasons == (FightEligibilityKind.ENGAGED_AT_FIGHT_STEP_START,)
    assert activation.interrupt_id == f"counteroffensive:{use.use_id}"
    assert state.fight_phase_state.fight_order_state.next_player_id == next_player
    assert state.command_point_total(REACTOR) == 2
    assert state.stratagem_use_records == [use]
    assert effect in state.persisting_effects_for_unit(LATE)
    request = pending(session)
    assert request.actor_id == REACTOR
    if expected_type == "overrun":
        assert request.decision_type == "submit_movement_proposal"
        pile_in = MovementProposalRequest.from_decision_request_payload(request.payload)
        assert pile_in.proposal_kind is ProposalKind.PILE_IN
        assert pile_in.unit_instance_id == LATE
        assert pile_in.context is not None
        assert pile_in.context["fight_movement_timing"] == "overrun"
        session = _restore(session)
        state = session.lifecycle.state
        assert state is not None
        assert state.fight_phase_state is not None
        attacker = state.fight_phase_state.fight_order_state.activation_selections[0]
        move = submit_move(
            session,
            targets=(attacker.unit_instance_id,),
            witness=paths(state, (LATE,), 0, -1.3 if single_overrun else -0.5),
        )
        assert move.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION, move
        assert state.fight_phase_state.overrun_pile_in_is_completed(
            activation_result_id=activation.result_id
        )
        request = pending(session)
        assert request.actor_id == REACTOR
    assert proposal_from_native_request(request).stratagem_id == "epic-challenge"
    _restore(session)
