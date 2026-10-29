"""Full Fight continuation, tamper rejection, restore and replay regression."""

from __future__ import annotations

import json
from typing import cast

import pytest
from tests.phase15c_fight_order_helpers import (
    decision_request as _decision_request,
)
from tests.phase15c_fight_order_helpers import (
    submit_minimal_melee_declaration as _submit_minimal_melee_declaration,
)
from tests.setup_completion_helpers import record_current_battlefield_placements_for_fixture
from tests.support.fight_phase_reconstruction import (
    fight_lifecycle as _fight_lifecycle,
)
from tests.support.fight_phase_reconstruction import (
    fight_movement_witness_for_unit as _fight_movement_witness_for_unit,
)
from tests.support.fight_phase_reconstruction import (
    p12_forge_continuation as _p12_forge_continuation,
)
from tests.support.fight_phase_reconstruction import (
    resolve_phase15d_activation as _resolve_phase15d_activation,
)
from tests.support.fight_phase_reconstruction import (
    state as _state,
)
from tests.support.fight_phase_reconstruction import (
    submit_fight_movement_no_move as _submit_fight_movement_no_move,
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.ruleset_descriptor import ConsolidationModeKind, MovementMode
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.fight_resolution import (
    CONSOLIDATE_ACTION,
    PILE_IN_ACTION,
    SUBMIT_MELEE_DECLARATION_DECISION_TYPE,
    FightMovementProposal,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


def test_p12_full_fight_phase_reconstructs_ordinary_continuation_and_forced_overrun() -> None:
    lifecycle, units = _fight_lifecycle(
        alpha_unit_ids=("source",),
        enemy_unit_ids=("enemy",),
        origins={"source": Pose.at(10.0, 10.0), "enemy": Pose.at(14.2, 10.0)},
        game_id="p12-full-fight-continuation",
        charge_fights_first_unit_keys=("source",),
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
    )
    record_current_battlefield_placements_for_fixture(
        _state(lifecycle), decisions=lifecycle.decision_controller
    )
    session = LocalGameSession(lifecycle=lifecycle)
    status = session.advance_until_decision_or_terminal()
    initial = lifecycle.to_payload()
    for index in range(40):
        request = _decision_request(status)
        if request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE:
            movement = MovementProposalRequest.from_decision_request_payload(request.payload)
            if movement.proposal_kind is ProposalKind.CONSOLIDATE:
                break
            status = _submit_fight_movement_no_move(
                lifecycle, request=request, result_id=f"p12-full-no-move:{index}"
            )
        elif request.decision_type == SUBMIT_MELEE_DECLARATION_DECISION_TYPE:
            status = _submit_minimal_melee_declaration(
                lifecycle, request=request, result_id=f"p12-full-melee:{index}"
            )
        else:
            status = session.submit_option(
                request_id=request.request_id,
                option_id=request.options[0].option_id,
                result_id=f"p12-full-choice:{index}",
            )
    else:
        pytest.fail("The ordinary Fight phase did not reach Consolidation.")
    assert movement.unit_instance_id == units["source"].unit_instance_id
    ordinary = _state(lifecycle).fight_phase_state
    assert ordinary is not None
    assert ordinary.fight_order_state.selected_to_fight_unit_ids == (
        units["source"].unit_instance_id,
    )
    assert ordinary.fight_order_state.engaged_at_fight_step_start_unit_ids == ()
    battlefield = _state(lifecycle).battlefield_state
    assert battlefield is not None
    source_model = battlefield.unit_placement_by_id(movement.unit_instance_id).model_placements[0]
    start = source_model.pose
    loop = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.CONSOLIDATE,
        unit_instance_id=movement.unit_instance_id,
        movement_phase_action=CONSOLIDATE_ACTION,
        movement_mode=MovementMode.CONSOLIDATE,
        consolidation_mode=ConsolidationModeKind.ENGAGING,
        consolidate_target_unit_instance_ids=(units["enemy"].unit_instance_id,),
        witness=PathWitness.for_paths(
            (
                (
                    source_model.model_instance_id,
                    (
                        start,
                        Pose.at(start.position.x - 0.1, start.position.y),
                        start,
                    ),
                ),
            )
        ),
    )
    invalid = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="p12-full-closed-loop",
        payload=cast(JsonValue, loop.to_payload()),
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert "closed_loop_fight_movement" in json.dumps(invalid.payload)
    assert _state(lifecycle).battlefield_state == battlefield
    assert _state(lifecycle).fight_phase_state == ordinary
    assert (
        _decision_request(session.advance_until_decision_or_terminal()).request_id
        == request.request_id
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="p12-full-engaging",
        payload=cast(
            JsonValue,
            FightMovementProposal(
                proposal_request_id=request.request_id,
                proposal_kind=ProposalKind.CONSOLIDATE,
                unit_instance_id=movement.unit_instance_id,
                movement_phase_action=CONSOLIDATE_ACTION,
                movement_mode=MovementMode.CONSOLIDATE,
                consolidation_mode=ConsolidationModeKind.ENGAGING,
                consolidate_target_unit_instance_ids=(units["enemy"].unit_instance_id,),
                witness=_fight_movement_witness_for_unit(
                    lifecycle=lifecycle, unit=units["source"], dx=2.0, endpoint_only=False
                ),
            ).to_payload(),
        ),
    )
    forced_request = _decision_request(status)
    assert {
        cast(str, cast(dict[str, JsonValue], option.payload)["fight_type"])
        for option in forced_request.options
    } == {"normal", "overrun"}
    checkpoint = lifecycle.to_payload()
    assert GameLifecycle.from_payload(checkpoint).to_payload() == checkpoint
    for event_kind in (
        "fight_phase_started",
        "fight_step_completed",
        "fight_activation_selection_requested",
        "fight_activation_selected",
        "fight_selection_completed",
    ):
        forged_history = cast(GameLifecyclePayload, json.loads(json.dumps(checkpoint)))
        event = next(
            event
            for event in forged_history["decisions"]["event_log"]
            if event["event_type"] == event_kind
        )
        event["event_type"] = "p12-erased-preceding-fight-evidence"
        with pytest.raises(GameLifecycleError):
            GameLifecycle.from_payload(forged_history)
    for drift in (
        "next_player",
        "extra_completed",
        "omitted_completed",
        "ordering_flag",
        "step_status",
        "selected_inventory",
        "checkpoint_next_player",
        "checkpoint_source_identity",
    ):
        forged = _p12_forge_continuation(
            checkpoint, drift=drift, later_unit_id=units["enemy"].unit_instance_id
        )
        with pytest.raises(GameLifecycleError):
            GameLifecycle.from_payload(forged)
    option = next(
        option
        for option in forced_request.options
        if cast(dict[str, JsonValue], option.payload)["fight_type"] == "overrun"
    )
    status = session.submit_option(
        request_id=forced_request.request_id,
        option_id=option.option_id,
        result_id="p12-full-overrun",
    )
    overrun_request = _decision_request(status)
    status = session.submit_parameterized_payload(
        request_id=overrun_request.request_id,
        result_id="p12-full-overrun-movement",
        payload=cast(
            JsonValue,
            FightMovementProposal(
                proposal_request_id=overrun_request.request_id,
                proposal_kind=ProposalKind.PILE_IN,
                unit_instance_id=units["enemy"].unit_instance_id,
                movement_phase_action=PILE_IN_ACTION,
                movement_mode=MovementMode.PILE_IN,
                pile_in_target_unit_instance_ids=(units["source"].unit_instance_id,),
                witness=_fight_movement_witness_for_unit(
                    lifecycle=lifecycle, unit=units["enemy"], dx=-0.25, endpoint_only=False
                ),
            ).to_payload(),
        ),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.payload
    _resolve_phase15d_activation(lifecycle, status, drain_movement=False)
    final = lifecycle.to_payload()
    assert GameLifecycle.from_payload(final).to_payload() == final
    artifact = ReplayArtifact.capture(
        artifact_id="p12-full-phase-replay",
        initial_lifecycle_payload=initial,
        final_lifecycle=lifecycle,
    )
    replay = ReplayRunner(artifact).run()
    assert replay.reproduced_exactly, replay.to_payload()
