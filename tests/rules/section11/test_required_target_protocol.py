# pyright: reportPrivateUsage=false
"""Required-target protocol from the seven-case native 563 control batch."""

from __future__ import annotations

import json
from typing import cast

from tests.charge_target_selection_helpers import choose_charge_targets
from tests.phase15a_charge_test_support import (
    _conditional_charge_lifecycle,
    _conditional_charge_pair_options,
    _decision_request,
    _first_proposal_validation_violation,
    _state,
    _submit_charge_move_proposal,
    _submit_option,
)
from warhammer40k_core.core.dice import RerollComponentSelectionPolicy
from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.charge_declaration_hooks import (
    SELECT_CHARGE_DECLARATION_GRANT_DECISION_TYPE,
)
from warhammer40k_core.engine.charge_required_targets import (
    CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY,
)
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.phases.charge import ChargeMoveProposal
from warhammer40k_core.geometry.pathing import PathWitness


def test_source_backed_conditional_charge_selects_pair_and_round_trips_required_target() -> None:
    lifecycle, units = _conditional_charge_lifecycle(
        game_id="phase15a-source-backed-conditional-charge-order47-2"
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    grant_request = _decision_request(
        _submit_option(
            lifecycle,
            request=selection_request,
            option_id=units["charger"].unit_instance_id,
            result_id="phase15a-source-backed-conditional-charge-select",
        )
    )
    pair_options = _conditional_charge_pair_options(grant_request)

    assert grant_request.decision_type == SELECT_CHARGE_DECLARATION_GRANT_DECISION_TYPE
    assert tuple(sorted(pair_options)) == (
        units["enemy-1"].unit_instance_id,
        units["enemy-2"].unit_instance_id,
    )
    assert {
        cast(str, replay_payload["anchor_unit_instance_id"])
        for replay_payload in pair_options.values()
    } == {
        units["psyker-anchor-1"].unit_instance_id,
        units["psyker-anchor-2"].unit_instance_id,
    }
    selected_enemy_id = units["enemy-1"].unit_instance_id
    selected_option_id = cast(str, pair_options[selected_enemy_id]["hook_id"])
    reroll_request = _decision_request(
        _submit_option(
            lifecycle,
            request=grant_request,
            option_id=selected_option_id,
            result_id="phase15a-source-backed-conditional-charge-grant",
        )
    )
    assert reroll_request.decision_type == DICE_REROLL_DECISION_TYPE
    effect = _state(lifecycle).persisting_effects_for_unit(units["charger"].unit_instance_id)[0]
    assert isinstance(effect.effect_payload, dict)
    permission_payload = cast(dict[str, object], effect.effect_payload["permission"])
    assert permission_payload["component_selection_policy"] == (
        RerollComponentSelectionPolicy.WHOLE_ROLL.value
    )
    source_payload = cast(dict[str, object], effect.effect_payload["source_payload"])
    assert source_payload[CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY] == [selected_enemy_id]

    lifecycle_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    restored = GameLifecycle.from_payload(lifecycle_payload)
    assert restored.to_payload() == lifecycle_payload
    restored_reroll_request = _decision_request(restored.advance_until_decision_or_terminal())
    proposal_request = _decision_request(
        _submit_option(
            restored,
            request=restored_reroll_request,
            option_id="decline",
            result_id="phase15a-source-backed-conditional-charge-decline-reroll",
        )
    )
    proposal_request = _decision_request(
        choose_charge_targets(
            restored,
            request=proposal_request,
            target_ids=(selected_enemy_id,),
            result_id="conditional-charge-targets",
        )
    )
    proposal = MovementProposalRequest.from_decision_request_payload(proposal_request.payload)
    proposal_context = cast(dict[str, object], proposal.context)
    assert proposal_context[CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY] == [
        selected_enemy_id
    ]

    before_invalid = restored.to_payload()
    restored_state = _state(restored)
    assert restored_state.battlefield_state is not None
    placement = restored_state.battlefield_state.unit_placement_by_id(proposal.unit_instance_id)
    invalid_witness = _submit_charge_move_proposal(
        restored,
        request=proposal_request,
        result_id="phase15a-source-backed-conditional-charge-no-move-witness",
        proposal=ChargeMoveProposal(
            proposal_request_id=proposal.request_id,
            proposal_kind=proposal.proposal_kind,
            unit_instance_id=proposal.unit_instance_id,
            movement_phase_action="charge_move",
            movement_mode=MovementMode.CHARGE,
            charge_target_unit_instance_ids=(),
            witness=PathWitness.for_paths(
                tuple(
                    (model.model_instance_id, (model.pose, model.pose))
                    for model in placement.model_placements
                )
            ),
        ),
    )
    assert invalid_witness.status_kind is LifecycleStatusKind.INVALID
    assert _first_proposal_validation_violation(invalid_witness)["violation_code"] == (
        "no_move_witness_forbidden"
    )
    assert restored.to_payload() == before_invalid

    invalid = _submit_charge_move_proposal(
        restored,
        request=proposal_request,
        result_id="phase15a-source-backed-conditional-charge-wrong-target",
        proposal=ChargeMoveProposal(
            proposal_request_id=proposal.request_id,
            proposal_kind=proposal.proposal_kind,
            unit_instance_id=proposal.unit_instance_id,
            movement_phase_action="charge_move",
            movement_mode=MovementMode.CHARGE,
            charge_target_unit_instance_ids=(),
            witness=None,
        ),
    )

    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert _first_proposal_validation_violation(invalid)["violation_code"] == (
        "charge_required_target_not_selected"
    )
    assert restored.to_payload() == before_invalid
    assert "<" not in json.dumps(lifecycle_payload, sort_keys=True)
