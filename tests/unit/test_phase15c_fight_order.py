from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.adapters.contracts import FiniteOptionSubmission, ParameterizedSubmission
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.missions import ObjectiveMarkerDefinition
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    ConsolidationModeKind,
    FightEligibilityKind,
    FightPhaseStepKind,
    FightPolicyDescriptor,
    FightTypeKind,
    MovementMode,
    RulesetDescriptor,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.attack_sequence import (
    ATTACK_ALLOCATION_DECISION_TYPES,
    ATTACK_RESOLUTION_SELECTION_DECISION_TYPES,
)
from warhammer40k_core.engine.battlefield_state import ModelPlacement, UnitPlacement
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.fight_order import (
    CHARGE_FIGHTS_FIRST_EFFECT_KIND,
    DECLINE_FIGHT_INTERRUPT_OPTION_ID,
    ELIGIBLE_TO_FIGHT_PASS_OPTION_ID,
    FIGHT_ACTIVATION_DECISION_TYPE,
    FIGHT_INTERRUPT_DECISION_TYPE,
    FIGHT_INTERRUPT_EFFECT_KIND,
    FIGHTS_FIRST_EFFECT_KIND,
    EligibleToFightPass,
    FightActivationSelection,
    FightOrderState,
    FightPhaseState,
    FightsFirstRegistry,
    FightsFirstSource,
    ResolvedFightInterrupt,
    fight_activation_option_id,
)
from warhammer40k_core.engine.fight_resolution import (
    CONSOLIDATE_ACTION,
    PILE_IN_ACTION,
    SUBMIT_MELEE_DECLARATION_DECISION_TYPE,
    FightMovementProposal,
    MeleeDeclarationProposalRequest,
)
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.fight import (
    invalid_fight_activation_status,
    invalid_fight_interrupt_status,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2025_26_mission_pack

_ATTACK_SEQUENCE_DECISION_TYPES = frozenset(
    (*ATTACK_RESOLUTION_SELECTION_DECISION_TYPES, *ATTACK_ALLOCATION_DECISION_TYPES)
)


def test_fight_phase_exposes_source_steps_and_records_json_safe_activation() -> None:
    lifecycle, units = _fight_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_ids=("enemy",),
        origins={
            "intercessor-1": Pose.at(10.0, 20.0),
            "enemy": Pose.at(13.0, 20.0),
        },
        game_id="phase15c-basic",
    )

    request = _advance_to_fight_order_request(lifecycle)
    request_payload = cast(dict[str, object], request.payload)
    option_id = fight_activation_option_id(
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        fight_type=RulesetDescriptor.warhammer_40000_eleventh().fight_policy.fight_types[0],
    )
    status = _submit_option(
        lifecycle,
        request=request,
        option_id=option_id,
        result_id="phase15c-basic-activation",
    )
    activation_event = _last_event_payload(lifecycle, "fight_activation_selected")
    lifecycle_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )

    assert request.decision_type == FIGHT_ACTIVATION_DECISION_TYPE
    assert request.actor_id == "player-a"
    request_steps = [
        step["step"] for step in cast(list[dict[str, object]], request_payload["step_states"])
    ]
    assert request_steps == [
        "start",
        "pile_in",
        "fight",
        "consolidate",
        "end",
    ]
    assert option_id in {option.option_id for option in request.options}
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert "phase15d_resolution" not in activation_event
    assert status.decision_request is not None
    assert status.decision_request.decision_type == FIGHT_ACTIVATION_DECISION_TYPE
    assert lifecycle.decision_controller.records[-1].request.decision_type == (
        FIGHT_ACTIVATION_DECISION_TYPE
    )
    assert GameLifecycle.from_payload(lifecycle_payload).to_payload() == lifecycle_payload


def test_phase15d_lifecycle_accepts_melee_declaration_for_engaged_character() -> None:
    lifecycle, units = _fight_lifecycle(
        alpha_unit_ids=("attacker",),
        enemy_unit_ids=("enemy",),
        origins={
            "attacker": Pose.at(10.0, 20.0),
            "enemy": Pose.at(12.0, 20.0),
        },
        game_id="phase15d-lifecycle-melee",
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
    )

    activation_request = _advance_to_fight_order_request(lifecycle)
    melee_status = _submit_option(
        lifecycle,
        request=activation_request,
        option_id=fight_activation_option_id(
            unit_instance_id=units["attacker"].unit_instance_id,
            fight_type=RulesetDescriptor.warhammer_40000_eleventh().fight_policy.fight_types[0],
        ),
        result_id="phase15d-lifecycle-melee-activation",
    )
    melee_request = _decision_request(melee_status)
    accepted_status = _submit_minimal_melee_declaration(
        lifecycle,
        request=melee_request,
        result_id="phase15d-lifecycle-melee-declaration",
    )
    requested = _last_event_payload(lifecycle, "melee_declaration_requested")
    accepted = _last_event_payload(lifecycle, "melee_declaration_accepted")

    assert melee_request.decision_type == SUBMIT_MELEE_DECLARATION_DECISION_TYPE
    assert requested["available_weapon_count"] == 1
    assert accepted["attack_sequence_id"] == (
        "melee-sequence:phase15d-lifecycle-melee:round-01:"
        f"{units['attacker'].unit_instance_id}:phase15d-lifecycle-melee-declaration"
    )
    assert accepted_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION


def test_phase15d_fight_activation_prevalidation_rejects_drifted_results() -> None:
    lifecycle, units = _fight_lifecycle(
        alpha_unit_ids=("attacker",),
        enemy_unit_ids=("enemy",),
        origins={
            "attacker": Pose.at(10.0, 20.0),
            "enemy": Pose.at(12.0, 20.0),
        },
        game_id="phase15d-activation-prevalidation",
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
    )
    request = _advance_to_fight_order_request(lifecycle)
    result = DecisionResult.for_request(
        result_id="phase15d-valid-activation-result",
        request=request,
        selected_option_id=fight_activation_option_id(
            unit_instance_id=units["attacker"].unit_instance_id,
            fight_type=RulesetDescriptor.warhammer_40000_eleventh().fight_policy.fight_types[0],
        ),
    )
    state = _state(lifecycle)
    ruleset = RulesetDescriptor.warhammer_40000_eleventh()

    cases = (
        (replace(result, request_id="phase15d-other-request"), "request_id"),
        (replace(result, decision_type="other_decision_type"), "decision_type"),
        (replace(result, actor_id="player-b"), "actor_id"),
        (replace(result, selected_option_id="phase15d-missing-option"), "selected_option_id"),
        (replace(result, payload=cast(JsonValue, {"submission_kind": "drifted"})), "payload"),
    )

    for drifted, expected_field in cases:
        status = invalid_fight_activation_status(
            state=state,
            request=request,
            result=drifted,
            ruleset_descriptor=ruleset,
        )

        assert status is not None
        assert cast(dict[str, object], status.payload)["field"] == expected_field

    selected_option = request.option_by_id(result.selected_option_id)
    payload = cast(dict[str, JsonValue], result.payload)
    current_band = cast(str, payload["ordering_band"])
    other_band = "fights_first" if current_band == "remaining_combats" else "remaining_combats"
    missing_unit_id = "army-alpha:missing-fight-unit"
    missing_unit_option_id = fight_activation_option_id(
        unit_instance_id=missing_unit_id,
        fight_type=FightTypeKind.NORMAL,
    )
    overrun_option_id = fight_activation_option_id(
        unit_instance_id=units["attacker"].unit_instance_id,
        fight_type=FightTypeKind.OVERRUN,
    )
    context_payload = cast(dict[str, JsonValue], payload["eligibility_context"])
    stale_context_payload: dict[str, JsonValue] = {
        **context_payload,
        "closest_enemy_distance_inches": 99.0,
        "more_than_pass_distance_from_all_enemies": True,
    }
    payload_cases = (
        (
            {**payload, "fight_type": FightTypeKind.OVERRUN.value},
            result.selected_option_id,
            "selected_option_id",
        ),
        ({**payload, "player_id": "player-b"}, result.selected_option_id, "player_id"),
        ({**payload, "ordering_band": other_band}, result.selected_option_id, "ordering_band"),
        (
            {**payload, "unit_instance_id": missing_unit_id},
            missing_unit_option_id,
            "unit_instance_id",
        ),
        (
            {**payload, "eligibility_context": stale_context_payload},
            result.selected_option_id,
            "eligibility_context",
        ),
        (
            {**payload, "fight_type": FightTypeKind.OVERRUN.value},
            overrun_option_id,
            "fight_type",
        ),
    )

    for drifted_payload, option_id, expected_field in payload_cases:
        drifted_option = replace(
            selected_option,
            option_id=option_id,
            payload=cast(JsonValue, drifted_payload),
        )
        status = invalid_fight_activation_status(
            state=state,
            request=replace(request, options=(drifted_option,)),
            result=replace(
                result,
                selected_option_id=option_id,
                payload=cast(JsonValue, drifted_payload),
            ),
            ruleset_descriptor=ruleset,
        )

        assert status is not None
        assert cast(dict[str, object], status.payload)["field"] == expected_field

    state.fight_phase_state = None
    missing_state = invalid_fight_activation_status(
        state=state,
        request=request,
        result=result,
        ruleset_descriptor=ruleset,
    )

    assert missing_state is not None
    assert cast(dict[str, object], missing_state.payload)["field"] == "fight_phase_state"


def test_phase15d_fight_activation_prevalidation_rejects_stale_eligible_pass_payloads() -> None:
    lifecycle, _units = _fight_lifecycle(
        alpha_unit_ids=("attacker",),
        enemy_unit_ids=("enemy",),
        origins={
            "attacker": Pose.at(10.0, 20.0),
            "enemy": Pose.at(30.0, 20.0),
        },
        game_id="phase15d-pass-prevalidation",
        charge_fights_first_unit_keys=("attacker",),
    )
    request = _advance_to_fight_order_request(lifecycle)
    result = DecisionResult.for_request(
        result_id="phase15d-valid-pass-result",
        request=request,
        selected_option_id=ELIGIBLE_TO_FIGHT_PASS_OPTION_ID,
    )
    payload = cast(dict[str, JsonValue], result.payload)
    state = _state(lifecycle)
    ruleset = RulesetDescriptor.warhammer_40000_eleventh()

    cases = (
        ({**payload, "eligible_unit_ids": []}, "eligible_unit_ids"),
        ({**payload, "player_id": "player-b"}, "player_id"),
        ({**payload, "pass_distance_inches": 99.0}, "pass_distance_inches"),
    )

    for drifted_payload, expected_field in cases:
        drifted_options = tuple(
            replace(option, payload=cast(JsonValue, drifted_payload))
            if option.option_id == ELIGIBLE_TO_FIGHT_PASS_OPTION_ID
            else option
            for option in request.options
        )
        drifted_request = replace(request, options=drifted_options)
        status = invalid_fight_activation_status(
            state=state,
            request=drifted_request,
            result=replace(result, payload=cast(JsonValue, drifted_payload)),
            ruleset_descriptor=ruleset,
        )

        assert status is not None
        assert cast(dict[str, object], status.payload)["field"] == expected_field


def test_phase15d_lifecycle_rejects_malformed_and_invalid_fight_movement_submission() -> None:
    lifecycle, _units = _fight_lifecycle(
        alpha_unit_ids=("attacker",),
        enemy_unit_ids=("enemy",),
        origins={
            "attacker": Pose.at(10.0, 20.0),
            "enemy": Pose.at(12.0, 20.0),
        },
        game_id="phase15d-lifecycle-invalid-movement",
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
    )
    request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    context = cast(dict[str, JsonValue], proposal_request.context)

    malformed_status = lifecycle.submit_decision(
        ParameterizedSubmission(
            request_id=request.request_id,
            result_id="phase15d-malformed-fight-movement",
            payload=cast(JsonValue, {}),
        ).to_result(request)
    )
    missing_witness_status = lifecycle.submit_decision(
        ParameterizedSubmission(
            request_id=request.request_id,
            result_id="phase15d-invalid-fight-movement-no-witness",
            payload=cast(
                JsonValue,
                {
                    "proposal_request_id": proposal_request.request_id,
                    "proposal_kind": proposal_request.proposal_kind.value,
                    "unit_instance_id": proposal_request.unit_instance_id,
                    "movement_phase_action": proposal_request.movement_phase_action,
                    "movement_mode": context["movement_mode"],
                    "pile_in_target_unit_instance_ids": ["army-beta:enemy"],
                },
            ),
        ).to_result(request)
    )
    stale_status = lifecycle.submit_decision(
        ParameterizedSubmission(
            request_id=request.request_id,
            result_id="phase15d-stale-fight-movement",
            payload=cast(
                JsonValue,
                {
                    "proposal_request_id": f"{proposal_request.request_id}:stale",
                    "proposal_kind": proposal_request.proposal_kind.value,
                    "unit_instance_id": proposal_request.unit_instance_id,
                    "movement_phase_action": proposal_request.movement_phase_action,
                    "movement_mode": context["movement_mode"],
                },
            ),
        ).to_result(request)
    )

    malformed_payload = cast(dict[str, object], malformed_status.payload)
    malformed_validation = cast(
        dict[str, object],
        malformed_payload["proposal_validation"],
    )
    malformed_violations = cast(list[dict[str, object]], malformed_validation["violations"])
    missing_witness_payload = cast(dict[str, object], missing_witness_status.payload)
    missing_witness_validation = cast(
        dict[str, object],
        missing_witness_payload["proposal_validation"],
    )
    missing_witness_violations = cast(
        list[dict[str, object]],
        missing_witness_validation["violations"],
    )
    stale_payload = cast(dict[str, object], stale_status.payload)
    stale_validation = cast(
        dict[str, object],
        stale_payload["proposal_validation"],
    )
    stale_violations = cast(list[dict[str, object]], stale_validation["violations"])

    assert request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    assert malformed_status.status_kind is LifecycleStatusKind.INVALID
    assert malformed_violations[0]["violation_code"] == "proposal_payload_missing_field"
    assert missing_witness_status.status_kind is LifecycleStatusKind.INVALID
    assert missing_witness_violations[0]["violation_code"] == "fight_movement_witness_required"
    assert stale_status.status_kind is LifecycleStatusKind.INVALID
    assert stale_violations[0]["violation_code"] == "stale_proposal_request"
    assert lifecycle.decision_controller.records == ()
    assert lifecycle.decision_controller.queue.pending_requests == (request,)


def test_phase15d_endpoint_only_pile_in_records_rejected_attempt_and_retries() -> None:
    lifecycle, units = _fight_lifecycle(
        alpha_unit_ids=("attacker",),
        enemy_unit_ids=("enemy",),
        origins={
            "attacker": Pose.at(10.0, 20.0),
            "enemy": Pose.at(12.0, 20.0),
        },
        game_id="phase15d-endpoint-only-retry",
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
    )
    request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    before_placement = _unit_placement_payload(lifecycle, units["attacker"])
    assert proposal_request.movement_phase_action == PILE_IN_ACTION
    proposal = FightMovementProposal(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=ProposalKind.PILE_IN,
        unit_instance_id=proposal_request.unit_instance_id,
        movement_phase_action=PILE_IN_ACTION,
        movement_mode=MovementMode.PILE_IN,
        pile_in_target_unit_instance_ids=(units["enemy"].unit_instance_id,),
        witness=_fight_movement_witness_for_unit(
            lifecycle=lifecycle,
            unit=units["attacker"],
            dx=0.25,
            endpoint_only=True,
        ),
    )

    status = _submit_fight_movement_proposal(
        lifecycle,
        request=request,
        proposal=proposal,
        result_id="phase15d-endpoint-only-pile-in",
    )

    retry_request = lifecycle.decision_controller.queue.pending_requests[0]
    retry_proposal_request = MovementProposalRequest.from_decision_request_payload(
        retry_request.payload
    )
    invalid_payload = _last_event_payload(lifecycle, "fight_movement_invalid")
    invalid_validation = cast(dict[str, object], invalid_payload["proposal_validation"])
    invalid_violations = cast(list[dict[str, object]], invalid_validation["violations"])
    status_payload = cast(dict[str, object], status.payload)

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert status_payload["violation_code"] == "endpoint_only_path"
    assert status_payload["next_request_id"] == retry_request.request_id
    assert len(lifecycle.decision_controller.records) == 1
    assert lifecycle.decision_controller.records[0].request == request
    assert lifecycle.decision_controller.records[0].result.result_id == (
        "phase15d-endpoint-only-pile-in"
    )
    assert invalid_payload["result_id"] == "phase15d-endpoint-only-pile-in"
    assert invalid_violations[0]["violation_code"] == "endpoint_only_path"
    assert _unit_placement_payload(lifecycle, units["attacker"]) == before_placement
    assert retry_request.request_id != request.request_id
    assert retry_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    assert retry_proposal_request.proposal_kind is ProposalKind.PILE_IN
    assert retry_proposal_request.unit_instance_id == proposal_request.unit_instance_id
    assert retry_proposal_request.source_decision_request_id == (
        proposal_request.source_decision_request_id
    )
    assert retry_proposal_request.source_decision_result_id == (
        proposal_request.source_decision_result_id
    )


def test_phase15d_over_distance_consolidate_records_rejected_attempt_and_retries() -> None:
    lifecycle, units = _fight_lifecycle(
        alpha_unit_ids=("charger",),
        enemy_unit_ids=("enemy",),
        origins={
            "charger": Pose.at(10.0, 20.0),
            "enemy": Pose.at(14.0, 20.0),
        },
        game_id="phase15d-consolidate-retry",
        charge_fights_first_unit_keys=("charger",),
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
    )
    _start_consolidate_step(lifecycle)
    request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    before_placement = _unit_placement_payload(lifecycle, units["charger"])
    assert proposal_request.movement_phase_action == CONSOLIDATE_ACTION
    proposal = FightMovementProposal(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=ProposalKind.CONSOLIDATE,
        unit_instance_id=proposal_request.unit_instance_id,
        movement_phase_action=CONSOLIDATE_ACTION,
        movement_mode=MovementMode.CONSOLIDATE,
        consolidation_mode=ConsolidationModeKind.ENGAGING,
        consolidate_target_unit_instance_ids=(units["enemy"].unit_instance_id,),
        witness=_fight_movement_witness_for_unit(
            lifecycle=lifecycle,
            unit=units["charger"],
            dx=3.5,
            endpoint_only=False,
        ),
    )

    status = _submit_fight_movement_proposal(
        lifecycle,
        request=request,
        proposal=proposal,
        result_id="phase15d-over-distance-consolidate",
    )

    retry_request = lifecycle.decision_controller.queue.pending_requests[0]
    retry_proposal_request = MovementProposalRequest.from_decision_request_payload(
        retry_request.payload
    )
    invalid_payload = _last_event_payload(lifecycle, "fight_movement_invalid")
    invalid_validation = cast(dict[str, object], invalid_payload["proposal_validation"])
    invalid_violations = cast(list[dict[str, object]], invalid_validation["violations"])
    status_payload = cast(dict[str, object], status.payload)

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert status_payload["violation_code"] == "movement_distance_exceeded"
    assert status_payload["next_request_id"] == retry_request.request_id
    assert len(lifecycle.decision_controller.records) == 1
    assert lifecycle.decision_controller.records[0].request == request
    assert lifecycle.decision_controller.records[0].result.result_id == (
        "phase15d-over-distance-consolidate"
    )
    assert invalid_payload["result_id"] == "phase15d-over-distance-consolidate"
    assert invalid_violations[0]["violation_code"] == "movement_distance_exceeded"
    assert _unit_placement_payload(lifecycle, units["charger"]) == before_placement
    assert retry_request.request_id != request.request_id
    assert retry_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    assert retry_proposal_request.proposal_kind is ProposalKind.CONSOLIDATE
    assert retry_proposal_request.unit_instance_id == proposal_request.unit_instance_id


def test_phase15d_lifecycle_rejects_malformed_and_rule_invalid_melee_declarations() -> None:
    lifecycle, units = _fight_lifecycle(
        alpha_unit_ids=("attacker",),
        enemy_unit_ids=("enemy",),
        origins={
            "attacker": Pose.at(10.0, 20.0),
            "enemy": Pose.at(12.0, 20.0),
        },
        game_id="phase15d-lifecycle-invalid-melee",
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
    )
    activation_request = _advance_to_fight_order_request(lifecycle)
    melee_status = _submit_option(
        lifecycle,
        request=activation_request,
        option_id=fight_activation_option_id(
            unit_instance_id=units["attacker"].unit_instance_id,
            fight_type=RulesetDescriptor.warhammer_40000_eleventh().fight_policy.fight_types[0],
        ),
        result_id="phase15d-invalid-melee-activation",
    )
    melee_request = _decision_request(melee_status)
    proposal_request = MeleeDeclarationProposalRequest.from_decision_request(melee_request)

    malformed_status = lifecycle.submit_decision(
        ParameterizedSubmission(
            request_id=melee_request.request_id,
            result_id="phase15d-malformed-melee",
            payload=cast(JsonValue, {}),
        ).to_result(melee_request)
    )
    empty_declaration_status = lifecycle.submit_decision(
        ParameterizedSubmission(
            request_id=melee_request.request_id,
            result_id="phase15d-empty-melee",
            payload=cast(
                JsonValue,
                {
                    "proposal_request_id": proposal_request.request_id,
                    "proposal_kind": proposal_request.proposal_kind,
                    "player_id": proposal_request.actor_id,
                    "battle_round": proposal_request.battle_round,
                    "unit_instance_id": proposal_request.unit_instance_id,
                    "source_decision_request_id": (proposal_request.source_decision_request_id),
                    "source_decision_result_id": proposal_request.source_decision_result_id,
                    "declarations": [],
                },
            ),
        ).to_result(melee_request)
    )

    malformed_payload = cast(dict[str, object], malformed_status.payload)
    malformed_validation = cast(dict[str, object], malformed_payload["proposal_validation"])
    malformed_violations = cast(list[dict[str, object]], malformed_validation["violations"])
    empty_payload = cast(dict[str, object], empty_declaration_status.payload)
    empty_validation = cast(dict[str, object], empty_payload["proposal_validation"])
    empty_violations = cast(list[dict[str, object]], empty_validation["violations"])

    assert melee_request.decision_type == SUBMIT_MELEE_DECLARATION_DECISION_TYPE
    assert malformed_status.status_kind is LifecycleStatusKind.INVALID
    assert malformed_violations[0]["violation_code"] == "proposal_payload_malformed"
    assert empty_declaration_status.status_kind is LifecycleStatusKind.INVALID
    assert empty_violations[0]["violation_code"] == "melee_declaration_required"
    assert lifecycle.decision_controller.queue.pending_requests == (melee_request,)


def test_fights_first_resolves_before_remaining_combats_with_active_player_alternation() -> None:
    lifecycle, units = _fight_lifecycle(
        alpha_unit_ids=("alpha-first", "alpha-remaining"),
        enemy_unit_ids=("enemy-first", "enemy-remaining"),
        origins={
            "alpha-first": Pose.at(10.0, 20.0),
            "enemy-first": Pose.at(13.0, 20.0),
            "alpha-remaining": Pose.at(10.0, 40.0),
            "enemy-remaining": Pose.at(13.0, 40.0),
        },
        game_id="phase15c-fights-first",
        fights_first_unit_keys=("alpha-first", "enemy-first"),
    )

    first_request = _advance_to_fight_order_request(lifecycle)
    first_payload = cast(dict[str, object], first_request.payload)
    first_status = _submit_normal_fight(
        lifecycle,
        request=first_request,
        unit=units["alpha-first"],
        result_id="phase15c-alpha-first",
    )
    second_request = _decision_request(first_status)
    second_payload = cast(dict[str, object], second_request.payload)
    second_status = _submit_normal_fight(
        lifecycle,
        request=second_request,
        unit=units["enemy-first"],
        result_id="phase15c-enemy-first",
    )
    third_request = _decision_request(second_status)
    third_payload = cast(dict[str, object], third_request.payload)

    assert first_request.actor_id == "player-a"
    assert first_payload["ordering_band"] == "fights_first"
    assert _request_unit_ids(first_request) == [units["alpha-first"].unit_instance_id]
    assert second_request.actor_id == "player-b"
    assert second_payload["ordering_band"] == "fights_first"
    assert _request_unit_ids(second_request) == [units["enemy-first"].unit_instance_id]
    assert third_request.actor_id == "player-a"
    assert third_payload["ordering_band"] == "remaining_combats"
    assert _request_unit_ids(third_request) == [units["alpha-remaining"].unit_instance_id]


def test_remaining_combat_returns_to_fights_first_when_new_fights_first_unit_is_eligible() -> None:
    lifecycle, units = _fight_lifecycle(
        alpha_unit_ids=("alpha-remaining", "alpha-late"),
        enemy_unit_ids=("enemy-remaining", "enemy-late-first"),
        origins={
            "alpha-remaining": Pose.at(10.0, 20.0),
            "enemy-remaining": Pose.at(13.0, 20.0),
            "alpha-late": Pose.at(70.0, 70.0),
            "enemy-late-first": Pose.at(86.0, 70.0),
        },
        game_id="phase15c-return-to-fights-first",
        fights_first_unit_keys=("enemy-late-first",),
    )
    first_request = _advance_to_fight_order_request(lifecycle)
    first_payload = cast(dict[str, object], first_request.payload)

    _move_unit_to(lifecycle, unit=units["enemy-late-first"], origin=Pose.at(73.0, 70.0))
    after_remaining_status = _submit_normal_fight(
        lifecycle,
        request=first_request,
        unit=units["alpha-remaining"],
        result_id="phase15c-alpha-remaining-before-late-first",
    )
    next_request = _decision_request(after_remaining_status)
    next_payload = cast(dict[str, object], next_request.payload)

    assert first_request.actor_id == "player-a"
    assert first_payload["ordering_band"] == "remaining_combats"
    assert _request_unit_ids(first_request) == [units["alpha-remaining"].unit_instance_id]
    assert next_request.actor_id == "player-b"
    assert next_payload["ordering_band"] == "fights_first"
    assert _request_unit_ids(next_request) == [units["enemy-late-first"].unit_instance_id]


def test_eligible_to_fight_pass_is_offered_only_when_all_eligible_units_are_more_than_five() -> (
    None
):
    close_lifecycle, _close_units = _fight_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_ids=("enemy",),
        origins={
            "intercessor-1": Pose.at(10.0, 20.0),
            "enemy": Pose.at(13.0, 20.0),
        },
        game_id="phase15c-pass-close",
    )
    close_request = _advance_to_fight_order_request(close_lifecycle)

    far_lifecycle, far_units = _fight_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_ids=("enemy",),
        origins={
            "intercessor-1": Pose.at(10.0, 20.0),
            "enemy": Pose.at(30.0, 20.0),
        },
        game_id="phase15c-pass-far",
        charge_fights_first_unit_keys=("intercessor-1",),
    )
    far_request = _advance_to_fight_order_request(far_lifecycle)
    pass_status = _submit_option(
        far_lifecycle,
        request=far_request,
        option_id=ELIGIBLE_TO_FIGHT_PASS_OPTION_ID,
        result_id="phase15c-pass",
    )
    pass_payload = _last_event_payload(far_lifecycle, "eligible_to_fight_pass_recorded")

    assert ELIGIBLE_TO_FIGHT_PASS_OPTION_ID not in {
        option.option_id for option in close_request.options
    }
    assert ELIGIBLE_TO_FIGHT_PASS_OPTION_ID in {option.option_id for option in far_request.options}
    assert _request_unit_ids(far_request) == [far_units["intercessor-1"].unit_instance_id]
    assert pass_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert cast(dict[str, object], pass_payload["eligible_pass"])["eligible_unit_ids"] == [
        far_units["intercessor-1"].unit_instance_id
    ]


def test_fights_first_pass_does_not_reoffer_same_unit_before_remaining_activation() -> None:
    lifecycle, units = _fight_lifecycle(
        alpha_unit_ids=("alpha-first", "alpha-remaining"),
        enemy_unit_ids=("enemy",),
        origins={
            "alpha-first": Pose.at(10.0, 20.0),
            "alpha-remaining": Pose.at(10.0, 40.0),
            "enemy": Pose.at(13.0, 40.0),
        },
        game_id="phase15c-pass-before-remaining",
        charge_fights_first_unit_keys=("alpha-first",),
    )
    first_request = _advance_to_fight_order_request(lifecycle)
    first_payload = cast(dict[str, object], first_request.payload)

    after_pass_status = _submit_option(
        lifecycle,
        request=first_request,
        option_id=ELIGIBLE_TO_FIGHT_PASS_OPTION_ID,
        result_id="phase15c-pass-before-remaining",
    )
    next_request = _decision_request(after_pass_status)
    next_payload = cast(dict[str, object], next_request.payload)

    assert first_request.actor_id == "player-a"
    assert first_payload["ordering_band"] == "fights_first"
    assert _request_unit_ids(first_request) == [units["alpha-first"].unit_instance_id]
    assert next_request.actor_id == "player-a"
    assert next_payload["ordering_band"] == "remaining_combats"
    assert _request_unit_ids(next_request) == [units["alpha-remaining"].unit_instance_id]
    assert _event_payloads(lifecycle, "fight_activation_selection_requested")[-1][
        "eligible_unit_ids"
    ] == [units["alpha-remaining"].unit_instance_id]


def test_fights_first_pass_completes_phase_when_no_remaining_units_exist() -> None:
    lifecycle, units = _fight_lifecycle(
        alpha_unit_ids=("alpha-first",),
        enemy_unit_ids=("enemy",),
        origins={
            "alpha-first": Pose.at(10.0, 20.0),
            "enemy": Pose.at(30.0, 20.0),
        },
        game_id="phase15c-pass-completes",
        charge_fights_first_unit_keys=("alpha-first",),
    )
    first_request = _advance_to_fight_order_request(lifecycle)

    status = _submit_option(
        lifecycle,
        request=first_request,
        option_id=ELIGIBLE_TO_FIGHT_PASS_OPTION_ID,
        result_id="phase15c-pass-completes",
    )
    requested_fight_activations = _event_payloads(
        lifecycle,
        "fight_activation_selection_requested",
    )
    completion_payload = _last_event_payload(lifecycle, "fight_phase_completed")
    fight_phase_payload = cast(dict[str, object], completion_payload["fight_phase_state"])

    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert fight_phase_payload["phase_complete"] is True
    assert requested_fight_activations == (
        {
            "game_id": "phase15c-pass-completes",
            "battle_round": 1,
            "phase": "fight",
            "active_player_id": "player-a",
            "player_id": "player-a",
            "ordering_band": "fights_first",
            "request_id": first_request.request_id,
            "eligible_unit_ids": [units["alpha-first"].unit_instance_id],
            "eligible_pass_available": True,
            "phase_body_status": "fight_activation_required",
        },
    )
    assert len(_event_payloads(lifecycle, "fight_phase_completed")) == 1


def test_fight_activation_options_follow_normal_and_overrun_source_eligibility() -> None:
    engaged_lifecycle, engaged_units = _fight_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_ids=("enemy",),
        origins={
            "intercessor-1": Pose.at(10.0, 20.0),
            "enemy": Pose.at(13.0, 20.0),
        },
        game_id="phase15c-fight-type-engaged",
    )
    engaged_request = _advance_to_fight_order_request(engaged_lifecycle)
    engaged_unit_id = engaged_units["intercessor-1"].unit_instance_id

    charged_lifecycle, charged_units = _fight_lifecycle(
        alpha_unit_ids=("charger",),
        enemy_unit_ids=("enemy",),
        origins={
            "charger": Pose.at(10.0, 20.0),
            "enemy": Pose.at(30.0, 20.0),
        },
        game_id="phase15c-fight-type-overrun",
        charge_fights_first_unit_keys=("charger",),
    )
    charged_request = _advance_to_fight_order_request(charged_lifecycle)
    charged_unit_id = charged_units["charger"].unit_instance_id

    assert fight_activation_option_id(
        unit_instance_id=engaged_unit_id,
        fight_type=FightTypeKind.NORMAL,
    ) in _request_option_ids(engaged_request)
    assert fight_activation_option_id(
        unit_instance_id=engaged_unit_id,
        fight_type=FightTypeKind.OVERRUN,
    ) not in _request_option_ids(engaged_request)
    assert fight_activation_option_id(
        unit_instance_id=charged_unit_id,
        fight_type=FightTypeKind.NORMAL,
    ) not in _request_option_ids(charged_request)
    assert fight_activation_option_id(
        unit_instance_id=charged_unit_id,
        fight_type=FightTypeKind.OVERRUN,
    ) in _request_option_ids(charged_request)


def test_phase15d_overrun_activation_requests_overrun_pile_in_proposal() -> None:
    lifecycle, units = _fight_lifecycle(
        alpha_unit_ids=("charger",),
        enemy_unit_ids=("enemy",),
        origins={
            "charger": Pose.at(10.0, 20.0),
            "enemy": Pose.at(30.0, 20.0),
        },
        game_id="phase15d-overrun-pile-in",
        charge_fights_first_unit_keys=("charger",),
    )
    request = _advance_to_fight_order_request(lifecycle)
    charger_id = units["charger"].unit_instance_id
    status = _submit_option(
        lifecycle,
        request=request,
        option_id=fight_activation_option_id(
            unit_instance_id=charger_id,
            fight_type=FightTypeKind.OVERRUN,
        ),
        result_id="phase15d-overrun-activation",
    )
    movement_request = _decision_request(status)
    proposal_request = MovementProposalRequest.from_decision_request_payload(
        movement_request.payload
    )
    context = cast(dict[str, JsonValue], proposal_request.context)
    event_payload = _last_event_payload(lifecycle, "overrun_pile_in_requested")
    activation_payload = cast(dict[str, JsonValue], event_payload["activation_selection"])

    assert movement_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    assert proposal_request.proposal_kind is ProposalKind.PILE_IN
    assert proposal_request.unit_instance_id == charger_id
    assert proposal_request.source_decision_request_id == request.request_id
    assert proposal_request.source_decision_result_id == "phase15d-overrun-activation"
    assert context["fight_movement_timing"] == "overrun"
    assert context["movement_mode"] == ProposalKind.PILE_IN.value
    assert event_payload["proposal_kind"] == ProposalKind.PILE_IN.value
    assert activation_payload["fight_type"] == FightTypeKind.OVERRUN.value


def test_fight_activation_rejects_when_engagement_context_is_stale() -> None:
    lifecycle, units = _fight_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_ids=("enemy",),
        origins={
            "intercessor-1": Pose.at(10.0, 20.0),
            "enemy": Pose.at(13.0, 20.0),
        },
        game_id="phase15c-overrun-stale",
    )
    request = _advance_to_fight_order_request(lifecycle)
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.without_unit_placement(
        units["enemy"].unit_instance_id
    )
    option_id = fight_activation_option_id(
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        fight_type=FightTypeKind.NORMAL,
    )

    status = _submit_option(
        lifecycle,
        request=request,
        option_id=option_id,
        result_id="phase15c-stale-overrun",
    )
    status_payload = cast(dict[str, object], status.payload)

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert status_payload["invalid_reason"] == "invalid_fight_activation_result"
    assert status_payload["field"] == "eligibility_context"
    assert lifecycle.decision_controller.queue.pending_requests == (request,)
    assert all(
        record.request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
        for record in lifecycle.decision_controller.records
    )


def test_fight_interrupt_uses_reaction_queue_once_and_resumes_parent_sequence() -> None:
    lifecycle, units = _fight_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_ids=("enemy",),
        origins={
            "intercessor-1": Pose.at(10.0, 20.0),
            "enemy": Pose.at(13.0, 20.0),
        },
        game_id="phase15c-interrupt",
        fight_interrupt_unit_keys=("enemy",),
    )
    first_request = _advance_to_fight_order_request(lifecycle)
    interrupt_status = _submit_normal_fight(
        lifecycle,
        request=first_request,
        unit=units["intercessor-1"],
        result_id="phase15c-trigger-interrupt",
    )
    interrupt_request = _decision_request(interrupt_status)
    interrupt_option_id = fight_activation_option_id(
        unit_instance_id=units["enemy"].unit_instance_id,
        fight_type=RulesetDescriptor.warhammer_40000_eleventh().fight_policy.fight_types[0],
    )
    completed_status = _resolve_phase15d_activation(
        lifecycle,
        _submit_option(
            lifecycle,
            request=interrupt_request,
            option_id=interrupt_option_id,
            result_id="phase15c-resolve-interrupt",
        ),
    )

    assert interrupt_request.decision_type == FIGHT_INTERRUPT_DECISION_TYPE
    assert interrupt_request.actor_id == "player-b"
    assert DECLINE_FIGHT_INTERRUPT_OPTION_ID in {
        option.option_id for option in interrupt_request.options
    }
    assert len(lifecycle.reaction_queue.frames) == 0
    assert completed_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert len(_event_payloads(lifecycle, "fight_interrupt_requested")) == 1
    assert len(_event_payloads(lifecycle, "reaction_parent_resumed")) == 1
    assert len(_event_payloads(lifecycle, "fight_interrupt_activation_selected")) == 1


def test_phase15d_interrupt_melee_declaration_continues_reaction_to_attack_sequence() -> None:
    lifecycle, units = _fight_lifecycle(
        alpha_unit_ids=("parent", "interrupt-target"),
        enemy_unit_ids=("parent-target", "interrupter"),
        origins={
            "parent": Pose.at(50.0, 20.0),
            "parent-target": Pose.at(52.0, 20.0),
            "interrupter": Pose.at(10.0, 20.0),
            "interrupt-target": Pose.at(12.0, 20.0),
        },
        game_id="phase15d-interrupt-melee-continuation",
        fight_interrupt_unit_keys=("interrupter",),
        enemy_unit_specs={
            "interrupter": (
                "core-character-leader",
                "core-character-leader",
                1,
            ),
        },
    )
    first_request = _advance_to_fight_order_request(lifecycle)
    interrupt_status = _submit_normal_fight(
        lifecycle,
        request=first_request,
        unit=units["parent"],
        result_id="phase15d-trigger-interrupt-melee-continuation",
    )
    interrupt_request = _decision_request(interrupt_status)
    melee_status = _submit_option(
        lifecycle,
        request=interrupt_request,
        option_id=fight_activation_option_id(
            unit_instance_id=units["interrupter"].unit_instance_id,
            fight_type=FightTypeKind.NORMAL,
        ),
        result_id="phase15d-accept-interrupt-melee-continuation",
    )
    melee_request = _decision_request(melee_status)

    assert melee_request.decision_type == SUBMIT_MELEE_DECLARATION_DECISION_TYPE
    assert _active_reaction_frame_request_id(lifecycle) == melee_request.request_id

    declaration_status = _submit_minimal_melee_declaration(
        lifecycle,
        request=melee_request,
        result_id="phase15d-interrupt-melee-declaration",
    )
    attack_request = _decision_request(declaration_status)

    assert attack_request.decision_type in _ATTACK_SEQUENCE_DECISION_TYPES
    assert _event_payloads(lifecycle, "reaction_window_continued")[-1]["next_request_id"] == (
        attack_request.request_id
    )
    assert _active_reaction_frame_request_id(lifecycle) == attack_request.request_id

    completed_status = _resolve_phase15d_activation(lifecycle, declaration_status)

    assert completed_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert lifecycle.reaction_queue.frames == ()
    assert len(_event_payloads(lifecycle, "reaction_parent_resumed")) == 1


def test_phase15d_interrupt_overrun_pile_in_continues_reaction_to_melee_declaration() -> None:
    lifecycle, units = _overrun_interrupt_lifecycle(
        game_id="phase15d-interrupt-overrun-continuation"
    )
    interrupt_request = _trigger_overrun_interrupt_request(
        lifecycle,
        units=units,
        result_id="phase15d-trigger-overrun-continuation",
    )
    movement_status = _submit_option(
        lifecycle,
        request=interrupt_request,
        option_id=fight_activation_option_id(
            unit_instance_id=units["interrupter"].unit_instance_id,
            fight_type=FightTypeKind.OVERRUN,
        ),
        result_id="phase15d-accept-overrun-continuation",
    )
    movement_request = _decision_request(movement_status)
    assert movement_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    assert _active_reaction_frame_request_id(lifecycle) == movement_request.request_id

    pile_in_status = _submit_overrun_pile_in(
        lifecycle,
        request=movement_request,
        interrupter=units["interrupter"],
        target=units["overrun-target"],
        result_id="phase15d-valid-overrun-pile-in-continuation",
        endpoint_only=False,
    )
    melee_request = _decision_request(pile_in_status)

    assert melee_request.decision_type == SUBMIT_MELEE_DECLARATION_DECISION_TYPE
    assert _active_reaction_frame_request_id(lifecycle) == melee_request.request_id


def test_phase15d_interrupt_overrun_endpoint_only_retry_continues_reaction() -> None:
    lifecycle, units = _overrun_interrupt_lifecycle(
        game_id="phase15d-interrupt-overrun-retry-continuation"
    )
    interrupt_request = _trigger_overrun_interrupt_request(
        lifecycle,
        units=units,
        result_id="phase15d-trigger-overrun-retry-continuation",
    )
    movement_status = _submit_option(
        lifecycle,
        request=interrupt_request,
        option_id=fight_activation_option_id(
            unit_instance_id=units["interrupter"].unit_instance_id,
            fight_type=FightTypeKind.OVERRUN,
        ),
        result_id="phase15d-accept-overrun-retry-continuation",
    )
    movement_request = _decision_request(movement_status)
    record_count_before = len(lifecycle.decision_controller.records)

    invalid_status = _submit_overrun_pile_in(
        lifecycle,
        request=movement_request,
        interrupter=units["interrupter"],
        target=units["overrun-target"],
        result_id="phase15d-endpoint-only-overrun-pile-in-continuation",
        endpoint_only=True,
    )
    retry_request = lifecycle.decision_controller.queue.pending_requests[0]
    invalid_payload = _last_event_payload(lifecycle, "fight_movement_invalid")

    assert invalid_status.status_kind is LifecycleStatusKind.INVALID
    assert invalid_status.decision_request is None
    assert cast(dict[str, object], invalid_status.payload)["next_request_id"] == (
        retry_request.request_id
    )
    assert len(lifecycle.decision_controller.records) == record_count_before + 1
    assert invalid_payload["result_id"] == "phase15d-endpoint-only-overrun-pile-in-continuation"
    assert retry_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    assert _active_reaction_frame_request_id(lifecycle) == retry_request.request_id


def test_phase15d_normal_subdecisions_do_not_mutate_reaction_frames() -> None:
    movement_lifecycle, _movement_units = _fight_lifecycle(
        alpha_unit_ids=("attacker",),
        enemy_unit_ids=("enemy",),
        origins={
            "attacker": Pose.at(10.0, 20.0),
            "enemy": Pose.at(12.0, 20.0),
        },
        game_id="phase15d-normal-movement-no-reaction",
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
    )
    movement_request = _decision_request(movement_lifecycle.advance_until_decision_or_terminal())
    movement_status = _submit_fight_movement_no_move(
        movement_lifecycle,
        request=movement_request,
        result_id="phase15d-normal-movement-no-reaction",
    )

    assert movement_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    assert movement_status.status_kind is not LifecycleStatusKind.INVALID
    assert movement_lifecycle.reaction_queue.frames == ()

    melee_lifecycle, melee_units = _fight_lifecycle(
        alpha_unit_ids=("attacker",),
        enemy_unit_ids=("enemy",),
        origins={
            "attacker": Pose.at(10.0, 20.0),
            "enemy": Pose.at(12.0, 20.0),
        },
        game_id="phase15d-normal-melee-no-reaction",
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
    )
    activation_request = _advance_to_fight_order_request(melee_lifecycle)
    melee_status = _submit_option(
        melee_lifecycle,
        request=activation_request,
        option_id=fight_activation_option_id(
            unit_instance_id=melee_units["attacker"].unit_instance_id,
            fight_type=FightTypeKind.NORMAL,
        ),
        result_id="phase15d-normal-activation-no-reaction",
    )
    melee_request = _decision_request(melee_status)
    declaration_status = _submit_minimal_melee_declaration(
        melee_lifecycle,
        request=melee_request,
        result_id="phase15d-normal-melee-declaration-no-reaction",
    )

    assert melee_request.decision_type == SUBMIT_MELEE_DECLARATION_DECISION_TYPE
    assert declaration_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert melee_lifecycle.reaction_queue.frames == ()


def test_fight_interrupt_source_is_not_offered_again_after_accepted_interrupt() -> None:
    lifecycle, units = _fight_lifecycle(
        alpha_unit_ids=("alpha-1", "alpha-2"),
        enemy_unit_ids=("enemy-1", "enemy-2", "enemy-3"),
        origins={
            "alpha-1": Pose.at(10.0, 20.0),
            "enemy-1": Pose.at(13.0, 20.0),
            "alpha-2": Pose.at(10.0, 40.0),
            "enemy-2": Pose.at(13.0, 40.0),
            "enemy-3": Pose.at(14.5, 40.0),
        },
        game_id="phase15c-interrupt-source-accepted",
        fight_interrupt_unit_keys=("enemy-1",),
    )
    first_request = _advance_to_fight_order_request(lifecycle)
    interrupt_status = _submit_normal_fight(
        lifecycle,
        request=first_request,
        unit=units["alpha-1"],
        result_id="phase15c-trigger-accepted-source-interrupt",
    )
    interrupt_request = _decision_request(interrupt_status)
    interrupt_source_effect_id = _interrupt_source_effect_id(interrupt_request)
    after_interrupt_status = _submit_normal_fight(
        lifecycle,
        request=interrupt_request,
        unit=units["enemy-1"],
        result_id="phase15c-accepted-source-interrupt",
    )
    enemy_normal_request = _decision_request(after_interrupt_status)
    after_enemy_normal_status = _submit_normal_fight(
        lifecycle,
        request=enemy_normal_request,
        unit=units["enemy-2"],
        result_id="phase15c-enemy-normal-after-interrupt",
    )
    alpha_second_request = _decision_request(after_enemy_normal_status)
    stale_source_request = _retriggered_interrupt_request(interrupt_request)
    stale_interrupt_result = FiniteOptionSubmission(
        request_id=stale_source_request.request_id,
        selected_option_id=DECLINE_FIGHT_INTERRUPT_OPTION_ID,
        result_id="phase15c-replayed-accepted-source-interrupt",
    ).to_result(stale_source_request)
    stale_source_status = invalid_fight_interrupt_status(
        state=_state(lifecycle),
        request=stale_source_request,
        result=stale_interrupt_result,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
    )
    after_alpha_second_status = _submit_normal_fight(
        lifecycle,
        request=alpha_second_request,
        unit=units["alpha-2"],
        result_id="phase15c-alpha-second-after-interrupt",
    )
    resumed_request = _decision_request(after_alpha_second_status)
    pending_before_replayed_submit = lifecycle.decision_controller.queue.pending_requests
    replayed_submit_status = lifecycle.submit_decision(stale_interrupt_result)
    state = _state(lifecycle)

    assert stale_source_status is not None
    assert stale_source_status.status_kind is LifecycleStatusKind.INVALID
    assert stale_source_status.payload == {
        "invalid_reason": "invalid_fight_interrupt_result",
        "field": "source_effect_id",
    }
    assert resumed_request.decision_type == FIGHT_ACTIVATION_DECISION_TYPE
    assert resumed_request.actor_id == "player-b"
    assert _request_unit_ids(resumed_request) == [units["enemy-3"].unit_instance_id]
    assert replayed_submit_status.status_kind is LifecycleStatusKind.INVALID
    assert lifecycle.decision_controller.queue.pending_requests == pending_before_replayed_submit
    assert state.fight_phase_state is not None
    assert state.fight_phase_state.fight_order_state.resolved_interrupt_source_effect_ids == (
        interrupt_source_effect_id,
    )
    assert len(_event_payloads(lifecycle, "fight_interrupt_requested")) == 1
    assert len(_event_payloads(lifecycle, "fight_interrupt_activation_selected")) == 1


def test_fight_interrupt_decline_records_once_and_resumes_parent_sequence() -> None:
    lifecycle, units = _fight_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_ids=("enemy",),
        origins={
            "intercessor-1": Pose.at(10.0, 20.0),
            "enemy": Pose.at(13.0, 20.0),
        },
        game_id="phase15c-interrupt-decline",
        fight_interrupt_unit_keys=("enemy",),
    )
    first_request = _advance_to_fight_order_request(lifecycle)
    interrupt_status = _submit_normal_fight(
        lifecycle,
        request=first_request,
        unit=units["intercessor-1"],
        result_id="phase15c-trigger-declined-interrupt",
    )
    interrupt_request = _decision_request(interrupt_status)
    resumed_status = _submit_option(
        lifecycle,
        request=interrupt_request,
        option_id=DECLINE_FIGHT_INTERRUPT_OPTION_ID,
        result_id="phase15c-decline-interrupt",
    )
    resumed_request = _decision_request(resumed_status)
    state = _state(lifecycle)

    assert resumed_request.decision_type == FIGHT_ACTIVATION_DECISION_TYPE
    assert resumed_request.actor_id == "player-b"
    assert state.fight_phase_state is not None
    assert state.fight_phase_state.fight_order_state.resolved_interrupt_ids
    assert state.fight_phase_state.fight_order_state.resolved_interrupt_source_effect_ids
    assert len(_event_payloads(lifecycle, "fight_interrupt_declined")) == 1
    assert len(_event_payloads(lifecycle, "fight_interrupt_activation_selected")) == 0
    assert len(_event_payloads(lifecycle, "reaction_parent_resumed")) == 1


def test_fight_interrupt_source_is_not_offered_again_after_decline() -> None:
    lifecycle, units = _fight_lifecycle(
        alpha_unit_ids=("alpha-1", "alpha-2"),
        enemy_unit_ids=("enemy-1", "enemy-2"),
        origins={
            "alpha-1": Pose.at(10.0, 20.0),
            "enemy-1": Pose.at(13.0, 20.0),
            "alpha-2": Pose.at(10.0, 40.0),
            "enemy-2": Pose.at(13.0, 40.0),
        },
        game_id="phase15c-interrupt-source-declined",
        fight_interrupt_unit_keys=("enemy-1",),
    )
    first_request = _advance_to_fight_order_request(lifecycle)
    interrupt_status = _submit_normal_fight(
        lifecycle,
        request=first_request,
        unit=units["alpha-1"],
        result_id="phase15c-trigger-declined-source-interrupt",
    )
    interrupt_request = _decision_request(interrupt_status)
    interrupt_source_effect_id = _interrupt_source_effect_id(interrupt_request)
    after_decline_status = _submit_option(
        lifecycle,
        request=interrupt_request,
        option_id=DECLINE_FIGHT_INTERRUPT_OPTION_ID,
        result_id="phase15c-declined-source-interrupt",
    )
    enemy_normal_request = _decision_request(after_decline_status)
    after_enemy_normal_status = _submit_normal_fight(
        lifecycle,
        request=enemy_normal_request,
        unit=units["enemy-1"],
        result_id="phase15c-enemy-normal-after-decline",
    )
    alpha_second_request = _decision_request(after_enemy_normal_status)
    stale_source_request = _retriggered_interrupt_request(interrupt_request)
    stale_interrupt_result = FiniteOptionSubmission(
        request_id=stale_source_request.request_id,
        selected_option_id=DECLINE_FIGHT_INTERRUPT_OPTION_ID,
        result_id="phase15c-replayed-declined-source-interrupt",
    ).to_result(stale_source_request)
    stale_source_status = invalid_fight_interrupt_status(
        state=_state(lifecycle),
        request=stale_source_request,
        result=stale_interrupt_result,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
    )
    after_alpha_second_status = _submit_normal_fight(
        lifecycle,
        request=alpha_second_request,
        unit=units["alpha-2"],
        result_id="phase15c-alpha-second-after-decline",
    )
    resumed_request = _decision_request(after_alpha_second_status)
    pending_before_replayed_submit = lifecycle.decision_controller.queue.pending_requests
    replayed_submit_status = lifecycle.submit_decision(stale_interrupt_result)
    state = _state(lifecycle)

    assert stale_source_status is not None
    assert stale_source_status.status_kind is LifecycleStatusKind.INVALID
    assert stale_source_status.payload == {
        "invalid_reason": "invalid_fight_interrupt_result",
        "field": "source_effect_id",
    }
    assert resumed_request.decision_type == FIGHT_ACTIVATION_DECISION_TYPE
    assert resumed_request.actor_id == "player-b"
    assert _request_unit_ids(resumed_request) == [units["enemy-2"].unit_instance_id]
    assert replayed_submit_status.status_kind is LifecycleStatusKind.INVALID
    assert lifecycle.decision_controller.queue.pending_requests == pending_before_replayed_submit
    assert state.fight_phase_state is not None
    assert state.fight_phase_state.fight_order_state.resolved_interrupt_source_effect_ids == (
        interrupt_source_effect_id,
    )
    assert len(_event_payloads(lifecycle, "fight_interrupt_requested")) == 1
    assert len(_event_payloads(lifecycle, "fight_interrupt_declined")) == 1
    assert len(_event_payloads(lifecycle, "fight_interrupt_activation_selected")) == 0


def test_fight_phase_state_wraps_fight_order_state_payloads_round_trip() -> None:
    policy = RulesetDescriptor.warhammer_40000_eleventh().fight_policy
    source = FightsFirstSource(
        unit_instance_id="unit-a",
        effect_id="effect-a",
        source_rule_id="source-a",
        effect_kind=CHARGE_FIGHTS_FIRST_EFFECT_KIND,
    )
    registry = FightsFirstRegistry((source,))
    fight_state = FightPhaseState.start(
        battle_round=1,
        active_player_id="player-a",
        policy=policy,
        engaged_at_fight_step_start_unit_ids=("unit-a",),
        fights_first_registry=registry,
    )
    eligible_pass = EligibleToFightPass(
        player_id="player-a",
        battle_round=1,
        ordering_band=fight_state.current_ordering_band,
        request_id="request-pass",
        result_id="result-pass",
        pass_distance_inches=policy.eligible_pass_distance_inches,
        eligible_unit_ids=("unit-a",),
    )
    activation = FightActivationSelection(
        player_id="player-a",
        battle_round=1,
        unit_instance_id="unit-a",
        ordering_band=fight_state.current_ordering_band,
        fight_type=policy.fight_types[0],
        eligibility_reasons=(FightEligibilityKind.CHARGED_THIS_TURN,),
        request_id="request-activation",
        result_id="result-activation",
        interrupt_id=None,
    )
    populated = (
        fight_state.with_next_player("player-b")
        .with_eligible_pass(eligible_pass)
        .with_activation(activation)
        .with_resolved_interrupt(interrupt_id="interrupt-a", source_effect_id="effect-interrupt-a")
        .with_next_band()
        .with_phase_complete()
    )

    assert registry.has_unit("unit-a")
    assert registry.charged_unit_ids() == ("unit-a",)
    assert FightsFirstSource.from_payload(source.to_payload()) == source
    assert FightsFirstRegistry.from_payload(registry.to_payload()) == registry
    assert "ordering_bands" not in populated.to_payload()
    assert "fight_order_state" in populated.to_payload()
    assert (
        FightOrderState.from_payload(populated.fight_order_state.to_payload())
        == populated.fight_order_state
    )
    assert FightPhaseState.from_payload(populated.to_payload()) == populated


def test_fight_order_state_rejects_drifted_or_malformed_nested_records() -> None:
    policy = RulesetDescriptor.warhammer_40000_eleventh().fight_policy
    base_state = FightPhaseState.start(
        battle_round=1,
        active_player_id="player-a",
        policy=policy,
        engaged_at_fight_step_start_unit_ids=("unit-a",),
        fights_first_registry=FightsFirstRegistry(),
    )
    base_order_state = base_state.fight_order_state
    activation = FightActivationSelection(
        player_id="player-a",
        battle_round=1,
        unit_instance_id="unit-a",
        ordering_band=base_state.current_ordering_band,
        fight_type=policy.fight_types[0],
        eligibility_reasons=(FightEligibilityKind.ENGAGED_AT_FIGHT_STEP_START,),
        request_id="request-activation",
        result_id="result-activation",
        interrupt_id=None,
    )
    drifted_activation = FightActivationSelection(
        player_id="player-a",
        battle_round=2,
        unit_instance_id="unit-b",
        ordering_band=base_state.current_ordering_band,
        fight_type=policy.fight_types[0],
        eligibility_reasons=(FightEligibilityKind.ENGAGED_AT_FIGHT_STEP_START,),
        request_id="request-drifted",
        result_id="result-drifted",
        interrupt_id=None,
    )
    eligible_pass = EligibleToFightPass(
        player_id="player-a",
        battle_round=1,
        ordering_band=policy.ordering_bands[1],
        request_id="request-pass",
        result_id="result-pass",
        pass_distance_inches=policy.eligible_pass_distance_inches,
        eligible_unit_ids=("unit-a",),
    )
    source = FightsFirstSource(
        unit_instance_id="unit-a",
        effect_id="effect-a",
        source_rule_id="source-a",
        effect_kind=FIGHTS_FIRST_EFFECT_KIND,
    )

    with pytest.raises(GameLifecycleError, match="requires a FightPolicyDescriptor"):
        FightPhaseState.start(
            battle_round=1,
            active_player_id="player-a",
            policy=cast(FightPolicyDescriptor, object()),
            engaged_at_fight_step_start_unit_ids=("unit-a",),
            fights_first_registry=FightsFirstRegistry(),
        )
    with pytest.raises(GameLifecycleError, match="sources must be a tuple"):
        FightsFirstRegistry(cast(tuple[FightsFirstSource, ...], []))
    with pytest.raises(GameLifecycleError, match="sources must be unique"):
        FightsFirstRegistry((source, source))
    with pytest.raises(GameLifecycleError, match="step_states must not be empty"):
        FightPhaseState(
            battle_round=1,
            active_player_id="player-a",
            current_step=FightPhaseStepKind.FIGHT,
            step_states=(),
            fight_order_state=base_order_state,
        )
    with pytest.raises(GameLifecycleError, match="current_band_index is out of range"):
        FightOrderState(
            ordering_bands=policy.ordering_bands,
            current_band_index=99,
            next_player_id="player-a",
            engaged_at_fight_step_start_unit_ids=("unit-a",),
        )
    with pytest.raises(GameLifecycleError, match="activation_selections must contain"):
        FightOrderState(
            ordering_bands=policy.ordering_bands,
            current_band_index=0,
            next_player_id="player-a",
            engaged_at_fight_step_start_unit_ids=("unit-a",),
            activation_selections=cast(tuple[FightActivationSelection, ...], ("bad",)),
        )
    with pytest.raises(
        GameLifecycleError,
        match="remaining_combats_activation_since_band_entry must be a bool",
    ):
        FightOrderState(
            ordering_bands=policy.ordering_bands,
            current_band_index=0,
            next_player_id="player-a",
            engaged_at_fight_step_start_unit_ids=("unit-a",),
            remaining_combats_activation_since_band_entry=cast(bool, "false"),
        )
    with pytest.raises(GameLifecycleError, match="eligible_passes must contain"):
        FightOrderState(
            ordering_bands=policy.ordering_bands,
            current_band_index=0,
            next_player_id="player-a",
            engaged_at_fight_step_start_unit_ids=("unit-a",),
            eligible_passes=cast(tuple[EligibleToFightPass, ...], ("bad",)),
        )
    with pytest.raises(GameLifecycleError, match="resolved_interrupts must contain"):
        FightOrderState(
            ordering_bands=policy.ordering_bands,
            current_band_index=0,
            next_player_id="player-a",
            engaged_at_fight_step_start_unit_ids=("unit-a",),
            resolved_interrupts=cast(tuple[ResolvedFightInterrupt, ...], ("bad",)),
        )
    with pytest.raises(GameLifecycleError, match="phase_complete must be a bool"):
        FightPhaseState(
            battle_round=1,
            active_player_id="player-a",
            current_step=FightPhaseStepKind.FIGHT,
            step_states=base_state.step_states,
            fight_order_state=base_order_state,
            phase_complete=cast(bool, "false"),
        )
    with pytest.raises(GameLifecycleError, match="unit IDs must be unique"):
        FightOrderState(
            ordering_bands=policy.ordering_bands,
            current_band_index=0,
            next_player_id="player-a",
            engaged_at_fight_step_start_unit_ids=("unit-a", "unit-a"),
        )
    with pytest.raises(GameLifecycleError, match="battle round drift"):
        base_state.with_activation(drifted_activation)
    with pytest.raises(GameLifecycleError, match="ordering band drift"):
        base_state.with_eligible_pass(eligible_pass)
    with pytest.raises(GameLifecycleError, match="already activated"):
        base_state.with_activation(activation).with_activation(activation)
    with pytest.raises(GameLifecycleError, match="already resolved"):
        base_state.with_resolved_interrupt(
            interrupt_id="interrupt-a",
            source_effect_id="effect-interrupt-a",
        ).with_resolved_interrupt(
            interrupt_id="interrupt-a",
            source_effect_id="effect-interrupt-b",
        )
    with pytest.raises(GameLifecycleError, match="source has already resolved"):
        base_state.with_resolved_interrupt(
            interrupt_id="interrupt-a",
            source_effect_id="effect-interrupt-a",
        ).with_resolved_interrupt(
            interrupt_id="interrupt-b",
            source_effect_id="effect-interrupt-a",
        )
    with pytest.raises(GameLifecycleError, match="source effect IDs must be unique"):
        FightOrderState(
            ordering_bands=policy.ordering_bands,
            current_band_index=0,
            next_player_id="player-a",
            engaged_at_fight_step_start_unit_ids=("unit-a",),
            resolved_interrupts=(
                ResolvedFightInterrupt(
                    interrupt_id="interrupt-a",
                    source_effect_id="effect-interrupt-a",
                ),
                ResolvedFightInterrupt(
                    interrupt_id="interrupt-b",
                    source_effect_id="effect-interrupt-a",
                ),
            ),
        )
    with pytest.raises(GameLifecycleError, match="interrupt IDs must be unique"):
        FightOrderState(
            ordering_bands=policy.ordering_bands,
            current_band_index=0,
            next_player_id="player-a",
            engaged_at_fight_step_start_unit_ids=("unit-a",),
            resolved_interrupts=(
                ResolvedFightInterrupt(
                    interrupt_id="interrupt-a",
                    source_effect_id="effect-interrupt-a",
                ),
                ResolvedFightInterrupt(
                    interrupt_id="interrupt-a",
                    source_effect_id="effect-interrupt-b",
                ),
            ),
        )


def _fight_lifecycle(
    *,
    alpha_unit_ids: tuple[str, ...],
    enemy_unit_ids: tuple[str, ...],
    origins: dict[str, Pose],
    game_id: str,
    fights_first_unit_keys: tuple[str, ...] = (),
    charge_fights_first_unit_keys: tuple[str, ...] = (),
    fight_interrupt_unit_keys: tuple[str, ...] = (),
    datasheet_id: str = "core-intercessor-like-infantry",
    model_profile_id: str = "core-intercessor-like",
    model_count: int = 5,
    alpha_unit_specs: dict[str, tuple[str, str, int]] | None = None,
    enemy_unit_specs: dict[str, tuple[str, str, int]] | None = None,
) -> tuple[GameLifecycle, dict[str, UnitInstance]]:
    config = _config(
        game_id=game_id,
        alpha_unit_ids=alpha_unit_ids,
        enemy_unit_ids=enemy_unit_ids,
        datasheet_id=datasheet_id,
        model_profile_id=model_profile_id,
        model_count=model_count,
        alpha_unit_specs=alpha_unit_specs,
        enemy_unit_specs=enemy_unit_specs,
    )
    armies = _mustered_armies(config)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id=f"{game_id}-battlefield",
        armies=armies,
    )
    units = {
        unit.unit_instance_id.split(":", maxsplit=1)[1]: unit
        for army in armies
        for unit in army.units
    }
    battlefield = scenario.battlefield_state
    for key, unit in units.items():
        army_id = unit.unit_instance_id.split(":", maxsplit=1)[0]
        player_id = "player-a" if army_id == "army-alpha" else "player-b"
        battlefield = battlefield.with_unit_placement(
            _unit_placement_at(
                unit,
                army_id=army_id,
                player_id=player_id,
                poses=_compact_test_unit_poses(
                    origin=origins[key],
                    model_count=len(unit.own_models),
                ),
            )
        )
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    state.record_battlefield_state(battlefield)
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    state.battle_round = 1
    state.active_player_id = "player-a"
    for player_id in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=player_id,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=("assassination", "bring_it_down"),
            )
        )
    for key in fights_first_unit_keys:
        _record_fights_first_effect(
            state=state,
            unit=units[key],
            effect_kind=FIGHTS_FIRST_EFFECT_KIND,
        )
    for key in charge_fights_first_unit_keys:
        _record_fights_first_effect(
            state=state,
            unit=units[key],
            effect_kind=CHARGE_FIGHTS_FIRST_EFFECT_KIND,
        )
    for key in fight_interrupt_unit_keys:
        _record_fight_interrupt_effect(state=state, unit=units[key])
    payload = cast(
        GameLifecyclePayload,
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": GameLifecycle().decision_controller.to_payload(),
            "reaction_queue": {"frames": []},
        },
    )
    return GameLifecycle.from_payload(payload), units


def _overrun_interrupt_lifecycle(
    *,
    game_id: str,
) -> tuple[GameLifecycle, dict[str, UnitInstance]]:
    return _fight_lifecycle(
        alpha_unit_ids=("parent", "overrun-target"),
        enemy_unit_ids=("parent-target", "interrupter"),
        origins={
            "parent": Pose.at(50.0, 20.0),
            "parent-target": Pose.at(52.0, 20.0),
            "interrupter": Pose.at(10.0, 20.0),
            "overrun-target": Pose.at(14.0, 20.0),
        },
        game_id=game_id,
        charge_fights_first_unit_keys=("parent", "interrupter"),
        fight_interrupt_unit_keys=("interrupter",),
        enemy_unit_specs={
            "interrupter": (
                "core-character-leader",
                "core-character-leader",
                1,
            ),
        },
    )


def _trigger_overrun_interrupt_request(
    lifecycle: GameLifecycle,
    *,
    units: dict[str, UnitInstance],
    result_id: str,
) -> DecisionRequest:
    first_request = _advance_to_fight_order_request(lifecycle)
    interrupt_status = _submit_normal_fight(
        lifecycle,
        request=first_request,
        unit=units["parent"],
        result_id=result_id,
    )
    return _decision_request(interrupt_status)


def _config(
    *,
    game_id: str,
    alpha_unit_ids: tuple[str, ...],
    enemy_unit_ids: tuple[str, ...],
    datasheet_id: str,
    model_profile_id: str,
    model_count: int,
    alpha_unit_specs: dict[str, tuple[str, str, int]] | None = None,
    enemy_unit_specs: dict[str, tuple[str, str, int]] | None = None,
) -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id=game_id,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase15c-test"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=alpha_unit_ids,
                datasheet_id=datasheet_id,
                model_profile_id=model_profile_id,
                model_count=model_count,
                unit_specs=alpha_unit_specs,
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=enemy_unit_ids,
                datasheet_id=datasheet_id,
                model_profile_id=model_profile_id,
                model_count=model_count,
                unit_specs=enemy_unit_specs,
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=_mission_setup(),
    )


def _mission_setup() -> MissionSetup:
    mission_pack = chapter_approved_2025_26_mission_pack()
    return MissionSetup(
        mission_pack_id=mission_pack.mission_pack_id,
        source_version=mission_pack.source_version,
        source_id=mission_pack.source_id,
        mission_pool_entry_id="mission-a",
        primary_mission_id="take-and-hold",
        deployment_map_id="phase15c-open-map",
        terrain_layout_id="phase15c-open-layout",
        attacker_player_id="player-a",
        defender_player_id="player-b",
        battlefield_width_inches=100.0,
        battlefield_depth_inches=100.0,
        objective_markers=(
            ObjectiveMarkerDefinition(
                objective_marker_id="phase15c-remote-objective",
                name="Phase 15C Remote Objective",
                x_inches=95.0,
                y_inches=95.0,
                source_id="phase15c-test",
            ),
        ),
        deployment_zones=(),
        terrain_features=(),
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_ids: tuple[str, ...],
    datasheet_id: str,
    model_profile_id: str,
    model_count: int,
    unit_specs: dict[str, tuple[str, str, int]] | None = None,
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_id="core-combined-arms",
        ),
        unit_selections=tuple(
            _unit_selection_for_id(
                unit_id,
                unit_specs=unit_specs,
                default_datasheet_id=datasheet_id,
                default_model_profile_id=model_profile_id,
                default_model_count=model_count,
            )
            for unit_id in unit_selection_ids
        ),
    )


def _unit_selection_for_id(
    unit_id: str,
    *,
    unit_specs: dict[str, tuple[str, str, int]] | None,
    default_datasheet_id: str,
    default_model_profile_id: str,
    default_model_count: int,
) -> UnitMusterSelection:
    datasheet_id, model_profile_id, model_count = _unit_selection_spec(
        unit_id=unit_id,
        unit_specs=unit_specs,
        default_datasheet_id=default_datasheet_id,
        default_model_profile_id=default_model_profile_id,
        default_model_count=default_model_count,
    )
    return _unit_selection(
        unit_id,
        datasheet_id=datasheet_id,
        model_profile_id=model_profile_id,
        model_count=model_count,
    )


def _unit_selection_spec(
    *,
    unit_id: str,
    unit_specs: dict[str, tuple[str, str, int]] | None,
    default_datasheet_id: str,
    default_model_profile_id: str,
    default_model_count: int,
) -> tuple[str, str, int]:
    if unit_specs is not None and unit_id in unit_specs:
        return unit_specs[unit_id]
    return (default_datasheet_id, default_model_profile_id, default_model_count)


def _unit_selection(
    unit_selection_id: str,
    *,
    datasheet_id: str,
    model_profile_id: str,
    model_count: int,
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


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )


def _compact_test_unit_poses(*, origin: Pose, model_count: int) -> tuple[Pose, ...]:
    return tuple(
        Pose.at(
            origin.position.x + ((index % 5) * 1.4),
            origin.position.y + ((index // 5) * 1.4),
            origin.position.z,
            facing_degrees=origin.facing.degrees,
        )
        for index in range(model_count)
    )


def _unit_placement_at(
    unit: UnitInstance,
    *,
    army_id: str,
    player_id: str,
    poses: tuple[Pose, ...],
) -> UnitPlacement:
    return UnitPlacement(
        army_id=army_id,
        player_id=player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=army_id,
                player_id=player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=pose,
            )
            for model, pose in zip(unit.own_models, poses, strict=True)
        ),
    )


def _move_unit_to(lifecycle: GameLifecycle, *, unit: UnitInstance, origin: Pose) -> None:
    state = _state(lifecycle)
    battlefield_state = state.battlefield_state
    assert battlefield_state is not None
    army_id = unit.unit_instance_id.split(":", maxsplit=1)[0]
    state.battlefield_state = battlefield_state.with_unit_placement(
        _unit_placement_at(
            unit,
            army_id=army_id,
            player_id=_player_id_for_unit(unit),
            poses=_compact_test_unit_poses(
                origin=origin,
                model_count=len(unit.own_models),
            ),
        )
    )


def _unit_placement_payload(lifecycle: GameLifecycle, unit: UnitInstance) -> JsonValue:
    state = _state(lifecycle)
    battlefield_state = state.battlefield_state
    assert battlefield_state is not None
    return cast(
        JsonValue,
        battlefield_state.unit_placement_by_id(unit.unit_instance_id).to_payload(),
    )


def _fight_movement_witness_for_unit(
    *,
    lifecycle: GameLifecycle,
    unit: UnitInstance,
    dx: float,
    endpoint_only: bool,
) -> PathWitness:
    state = _state(lifecycle)
    battlefield_state = state.battlefield_state
    assert battlefield_state is not None
    unit_placement = battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    model_paths: list[tuple[str, tuple[Pose, ...]]] = []
    for placement in unit_placement.model_placements:
        start = placement.pose
        end = Pose.at(
            start.position.x + dx,
            start.position.y,
            start.position.z,
            facing_degrees=start.facing.degrees,
        )
        if endpoint_only:
            model_paths.append((placement.model_instance_id, (start, end)))
            continue
        midpoint = Pose.at(
            start.position.x + (dx / 2.0),
            start.position.y,
            start.position.z,
            facing_degrees=start.facing.degrees,
        )
        model_paths.append((placement.model_instance_id, (start, midpoint, end)))
    return PathWitness.for_paths(tuple(model_paths))


def _start_consolidate_step(lifecycle: GameLifecycle) -> None:
    state = _state(lifecycle)
    policy = state.runtime_ruleset_descriptor().fight_policy
    active_player_id = state.active_player_id
    assert active_player_id is not None
    state.fight_phase_state = FightPhaseState.start(
        battle_round=state.battle_round,
        active_player_id=active_player_id,
        policy=policy,
        engaged_at_fight_step_start_unit_ids=(),
        fights_first_registry=FightsFirstRegistry.from_state(state),
    ).with_current_step(
        current_step=FightPhaseStepKind.CONSOLIDATE,
        policy=policy,
    )


def _record_fights_first_effect(
    *,
    state: GameState,
    unit: UnitInstance,
    effect_kind: str,
) -> None:
    player_id = _player_id_for_unit(unit)
    state.record_persisting_effect(
        PersistingEffect(
            effect_id=f"{unit.unit_instance_id}:{effect_kind}",
            source_rule_id=f"phase15c:{effect_kind}",
            owner_player_id=player_id,
            target_unit_instance_ids=(unit.unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhaseKind.CHARGE,
            expiration=EffectExpiration.end_turn(
                battle_round=state.battle_round,
                player_id=player_id,
            ),
            effect_payload={"effect_kind": effect_kind},
        )
    )


def _record_fight_interrupt_effect(*, state: GameState, unit: UnitInstance) -> None:
    player_id = _player_id_for_unit(unit)
    state.record_persisting_effect(
        PersistingEffect(
            effect_id=f"{unit.unit_instance_id}:fight-interrupt",
            source_rule_id="phase15c:counter-offensive",
            owner_player_id=player_id,
            target_unit_instance_ids=(unit.unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhaseKind.FIGHT,
            expiration=EffectExpiration.end_phase(
                battle_round=state.battle_round,
                phase=BattlePhaseKind.FIGHT,
                player_id=player_id,
            ),
            effect_payload={
                "effect_kind": FIGHT_INTERRUPT_EFFECT_KIND,
                "source_rule_id": "phase15c:counter-offensive",
            },
        )
    )


def _player_id_for_unit(unit: UnitInstance) -> str:
    army_id = unit.unit_instance_id.split(":", maxsplit=1)[0]
    return "player-a" if army_id == "army-alpha" else "player-b"


def _advance_to_fight_order_request(lifecycle: GameLifecycle) -> DecisionRequest:
    return _decision_request(
        _drain_fight_movement_requests(
            lifecycle,
            lifecycle.advance_until_decision_or_terminal(),
        )
    )


def _drain_fight_movement_requests(
    lifecycle: GameLifecycle,
    status: LifecycleStatus,
) -> LifecycleStatus:
    current = status
    while (
        current.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
        and current.decision_request is not None
        and current.decision_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    ):
        request = current.decision_request
        proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
        assert proposal_request.proposal_kind in {
            ProposalKind.PILE_IN,
            ProposalKind.CONSOLIDATE,
        }
        context = cast(dict[str, JsonValue], proposal_request.context)
        current = lifecycle.submit_decision(
            ParameterizedSubmission(
                request_id=request.request_id,
                result_id=f"{request.request_id}:phase15c-no-move",
                payload=cast(
                    JsonValue,
                    {
                        "proposal_request_id": proposal_request.request_id,
                        "proposal_kind": proposal_request.proposal_kind.value,
                        "unit_instance_id": proposal_request.unit_instance_id,
                        "movement_phase_action": proposal_request.movement_phase_action,
                        "movement_mode": context["movement_mode"],
                    },
                ),
            ).to_result(request)
        )
    return current


def _submit_normal_fight(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    unit: UnitInstance,
    result_id: str,
) -> LifecycleStatus:
    status = _submit_option(
        lifecycle,
        request=request,
        option_id=fight_activation_option_id(
            unit_instance_id=unit.unit_instance_id,
            fight_type=RulesetDescriptor.warhammer_40000_eleventh().fight_policy.fight_types[0],
        ),
        result_id=result_id,
    )
    return _resolve_phase15d_activation(lifecycle, status)


def _resolve_phase15d_activation(
    lifecycle: GameLifecycle,
    status: LifecycleStatus,
) -> LifecycleStatus:
    current = status
    decision_index = 0
    while (
        current.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
        and current.decision_request is not None
    ):
        request = current.decision_request
        if request.decision_type in {
            FIGHT_ACTIVATION_DECISION_TYPE,
            FIGHT_INTERRUPT_DECISION_TYPE,
        }:
            return current
        if request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE:
            return _drain_fight_movement_requests(lifecycle, current)
        if request.decision_type == SUBMIT_MELEE_DECLARATION_DECISION_TYPE:
            current = _submit_minimal_melee_declaration(
                lifecycle,
                request=request,
                result_id=f"{request.request_id}:phase15c-melee",
            )
            continue
        if request.is_parameterized_submission_request():
            return current
        if not request.options:
            return current
        current = _submit_option(
            lifecycle,
            request=request,
            option_id=request.options[0].option_id,
            result_id=f"{request.request_id}:phase15c-auto-{decision_index:03d}",
        )
        decision_index += 1
    return current


def _submit_minimal_melee_declaration(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    result_id: str,
) -> LifecycleStatus:
    proposal_request = MeleeDeclarationProposalRequest.from_decision_request(request)
    declarations: list[dict[str, object]] = []
    primary_model_ids: set[str] = set()
    for weapon in proposal_request.available_weapons:
        weapon_payload = cast(dict[str, object], weapon)
        model_id = cast(str, weapon_payload["model_instance_id"])
        if model_id in primary_model_ids:
            continue
        if weapon_payload["is_extra_attacks"] is True:
            continue
        engaged_target_ids = cast(
            list[str],
            weapon_payload["engaged_target_unit_instance_ids"],
        )
        if not engaged_target_ids:
            continue
        primary_model_ids.add(model_id)
        declarations.append(
            {
                "attacker_model_instance_id": model_id,
                "wargear_id": weapon_payload["wargear_id"],
                "weapon_profile_id": weapon_payload["weapon_profile_id"],
                "target_allocations": [
                    {"target_unit_instance_id": engaged_target_ids[0]},
                ],
            }
        )
    return lifecycle.submit_decision(
        ParameterizedSubmission(
            request_id=request.request_id,
            result_id=result_id,
            payload=cast(
                JsonValue,
                {
                    "proposal_request_id": proposal_request.request_id,
                    "proposal_kind": proposal_request.proposal_kind,
                    "player_id": proposal_request.actor_id,
                    "battle_round": proposal_request.battle_round,
                    "unit_instance_id": proposal_request.unit_instance_id,
                    "source_decision_request_id": (proposal_request.source_decision_request_id),
                    "source_decision_result_id": proposal_request.source_decision_result_id,
                    "declarations": declarations,
                },
            ),
        ).to_result(request)
    )


def _submit_fight_movement_proposal(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    proposal: FightMovementProposal,
    result_id: str,
) -> LifecycleStatus:
    return lifecycle.submit_decision(
        ParameterizedSubmission(
            request_id=request.request_id,
            result_id=result_id,
            payload=cast(JsonValue, proposal.to_payload()),
        ).to_result(request)
    )


def _submit_fight_movement_no_move(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    result_id: str,
) -> LifecycleStatus:
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    context = cast(dict[str, JsonValue], proposal_request.context)
    return lifecycle.submit_decision(
        ParameterizedSubmission(
            request_id=request.request_id,
            result_id=result_id,
            payload=cast(
                JsonValue,
                {
                    "proposal_request_id": proposal_request.request_id,
                    "proposal_kind": proposal_request.proposal_kind.value,
                    "unit_instance_id": proposal_request.unit_instance_id,
                    "movement_phase_action": proposal_request.movement_phase_action,
                    "movement_mode": context["movement_mode"],
                },
            ),
        ).to_result(request)
    )


def _submit_overrun_pile_in(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    interrupter: UnitInstance,
    target: UnitInstance,
    result_id: str,
    endpoint_only: bool,
) -> LifecycleStatus:
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    assert proposal_request.proposal_kind is ProposalKind.PILE_IN
    proposal = FightMovementProposal(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=ProposalKind.PILE_IN,
        unit_instance_id=interrupter.unit_instance_id,
        movement_phase_action=PILE_IN_ACTION,
        movement_mode=MovementMode.PILE_IN,
        pile_in_target_unit_instance_ids=(target.unit_instance_id,),
        witness=_fight_movement_witness_for_unit(
            lifecycle=lifecycle,
            unit=interrupter,
            dx=2.0,
            endpoint_only=endpoint_only,
        ),
    )
    return _submit_fight_movement_proposal(
        lifecycle,
        request=request,
        proposal=proposal,
        result_id=result_id,
    )


def _submit_option(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    option_id: str,
    result_id: str,
) -> LifecycleStatus:
    return lifecycle.submit_decision(
        FiniteOptionSubmission(
            request_id=request.request_id,
            selected_option_id=option_id,
            result_id=result_id,
        ).to_result(request)
    )


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def _request_unit_ids(request: DecisionRequest) -> list[str]:
    payload = cast(dict[str, object], request.payload)
    contexts = cast(list[dict[str, object]], payload["eligible_contexts"])
    return [cast(str, context["unit_instance_id"]) for context in contexts]


def _request_option_ids(request: DecisionRequest) -> set[str]:
    return {option.option_id for option in request.options}


def _active_reaction_frame_request_id(lifecycle: GameLifecycle) -> str:
    assert lifecycle.reaction_queue.frames
    request_id = lifecycle.reaction_queue.frames[-1].request_id
    assert request_id is not None
    return request_id


def _interrupt_source_effect_id(request: DecisionRequest) -> str:
    payload = cast(dict[str, object], request.payload)
    handler_payload = cast(dict[str, object], payload["handler_payload"])
    interrupt = cast(dict[str, object], handler_payload["interrupt"])
    return cast(str, interrupt["source_effect_id"])


def _retriggered_interrupt_request(request: DecisionRequest) -> DecisionRequest:
    payload = cast(dict[str, object], request.payload)
    handler_payload = cast(dict[str, object], payload["handler_payload"])
    original_interrupt = cast(dict[str, object], handler_payload["interrupt"])
    interrupt = dict(original_interrupt)
    interrupt_id = cast(str, interrupt["interrupt_id"])
    trigger_event_id = cast(str, interrupt["trigger_event_id"])
    interrupt["interrupt_id"] = f"{interrupt_id}:later-trigger"
    interrupt["trigger_event_id"] = f"{trigger_event_id}:later-trigger"

    retriggered_handler_payload = dict(handler_payload)
    retriggered_handler_payload["interrupt"] = interrupt
    retriggered_payload = dict(payload)
    retriggered_payload["handler_payload"] = retriggered_handler_payload
    retriggered_payload["interrupt"] = interrupt

    return DecisionRequest(
        request_id=f"{request.request_id}:later-trigger",
        decision_type=FIGHT_INTERRUPT_DECISION_TYPE,
        actor_id=request.actor_id,
        payload=cast(JsonValue, retriggered_payload),
        options=(
            DecisionOption(
                option_id=DECLINE_FIGHT_INTERRUPT_OPTION_ID,
                label="Decline Fight Interrupt",
                payload=cast(
                    JsonValue,
                    {
                        "submission_kind": "decline_fight_interrupt",
                        "interrupt": interrupt,
                    },
                ),
            ),
        ),
    )


def _state(lifecycle: GameLifecycle) -> GameState:
    assert lifecycle.state is not None
    return lifecycle.state


def _last_event_payload(lifecycle: GameLifecycle, event_type: str) -> dict[str, object]:
    for event in reversed(lifecycle.decision_controller.event_log.records):
        if event.event_type == event_type:
            return cast(dict[str, object], event.payload)
    raise AssertionError(f"Missing event type {event_type}.")


def _event_payloads(lifecycle: GameLifecycle, event_type: str) -> tuple[dict[str, object], ...]:
    return tuple(
        cast(dict[str, object], event.payload)
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == event_type
    )
