from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.charge_distance_helpers import add_modifier
from tests.charge_target_selection_helpers import choose_charge_targets
from tests.fight_on_death_helpers import retain_destroyed_model_for_fixture
from tests.phase15a_charge_test_support import (
    _ATTACHED_CHARGE_TARGET_ID,  # pyright: ignore[reportPrivateUsage]
    _END_PHASE_CHARGE_GRANT_ID,  # pyright: ignore[reportPrivateUsage]
    _END_TURN_CHARGE_GRANT_ID,  # pyright: ignore[reportPrivateUsage]
    _advanced_unit_state,
    _assert_invalid_charge_submission_keeps_pending_clean,
    _charge_lifecycle,
    _charge_lifecycle_with_declaration_grants,
    _charge_modifier_ignore_ability_record,
    _charge_modifier_ignore_registry,
    _charge_move_proposal_request_for_value_tests,
    _charge_move_request_after_selection,
    _charge_path_witness_for_unit,
    _charge_roll_request,
    _charge_roll_result,
    _compact_test_unit_poses,
    _conditional_charge_ability_record,
    _conditional_charge_lifecycle,
    _conditional_charge_pair_options,
    _decision_request,
    _destroy_unit_models_for_test,
    _end_charge_heroic_session,
    _event_payloads,
    _first_proposal_validation_violation,
    _generated_snarling_protector_charge_lifecycle,
    _heroic_proposal_from_request,
    _ignored_charge_modifier_ids,
    _install_charge_declaration_registry,
    _install_charge_modifier_ignore_runtime,
    _last_event_payload,
    _payload_has_displacements,
    _require_pending_request,
    _resolved_charge_move_for_tests,
    _roll_result_from_event,
    _set_snarling_source_state_for_heroic_test,
    _state,
    _stratagem_use_for_result_id,
    _submit_charge_move_proposal,
    _submit_end_charge_heroic_target,
    _submit_heroic_intervention_no_move,
    _submit_option,
    _unit_placement_at,
)
from tests.support.selected_target_charge_fixtures import (
    selected_target_charge_persisting_effect,
)

from warhammer40k_core.adapters.contracts import FiniteOptionSubmission, ParameterizedSubmission
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.dice import RerollComponentSelectionPolicy
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    MovementMode,
    RulesetDescriptor,
)
from warhammer40k_core.engine.abilities import (
    AbilityCatalogIndex,
)
from warhammer40k_core.engine.actions import MissionActionState
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    ModelDisplacementKind,
    UnitPlacement,
)
from warhammer40k_core.engine.catalog_command_point_support import (
    CATALOG_IR_STRATAGEM_COST_MODIFIER_CONSUMER_ID,
)
from warhammer40k_core.engine.catalog_conditional_charge_runtime import (
    stratagem_records_with_source_backed_phase_use_exceptions,
)
from warhammer40k_core.engine.catalog_conditional_charge_support import (
    CATALOG_IR_FRIENDLY_ENGAGED_ANCHOR_CHARGE_CONSUMER_ID,
    CATALOG_IR_STRATAGEM_PHASE_USE_EXCEPTION_CONSUMER_ID,
)
from warhammer40k_core.engine.catalog_conditional_charge_support import (
    consumer_ids_for_clause as conditional_charge_consumer_ids_for_clause,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_ir_consumers_for_clause,
)
from warhammer40k_core.engine.catalog_selected_target_charge_effects import (
    selected_target_charge_constraint_for_unit,
)
from warhammer40k_core.engine.charge_declaration import (
    CHARGE_MOVE_PENDING_STATUS,
    CHARGE_NO_MOVE_POSSIBLE_STATUS,
    ChargeDistanceState,
    ChargeRollRequest,
    ChargeRollResult,
    ChargeTargetCandidate,
    ChargeTargetCandidatePayload,
)
from warhammer40k_core.engine.charge_declaration_hooks import (
    DECLINE_CHARGE_DECLARATION_GRANT_OPTION_ID,
    SELECT_CHARGE_DECLARATION_GRANT_DECISION_TYPE,
    ChargeDeclarationHookRegistry,
)
from warhammer40k_core.engine.charge_required_targets import (
    CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY,
)
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.damage_allocation import DamageKind, apply_damage_to_model
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE, DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.charge import (
    COMPLETE_CHARGE_PHASE_OPTION_ID,
    SELECT_CHARGING_UNIT_DECISION_TYPE,
    ChargeEndpointWitness,
    ChargeMoveProposal,
    ChargePhaseState,
    ChargingUnitSelection,
    _unit_is_engaged,
    legal_charge_target_unit_instance_ids,
    resolve_charge_move,
)
from warhammer40k_core.engine.phases.charge_reactions import (
    request_end_opponent_charge_heroic_intervention_if_available,
)
from warhammer40k_core.engine.phases.movement import (
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    FellBackUnitState,
)
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.reserves import ReserveKind, ReserveState
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
)
from warhammer40k_core.engine.stratagem_catalog import (
    eleventh_edition_core_stratagem_catalog_records,
)
from warhammer40k_core.engine.stratagem_phase_use_exceptions import (
    stratagem_phase_use_exception,
)
from warhammer40k_core.engine.stratagems import (
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    StratagemTargetProposal,
    StratagemTargetProposalPayload,
    stratagem_decline_payload,
)
from warhammer40k_core.engine.transports import (
    DisembarkedUnitState,
    DisembarkModeKind,
    TransportMovementStatus,
    TransportRestrictionOverride,
    TransportRestrictionOverrideKind,
)
from warhammer40k_core.engine.unit_coherency import MovementRollbackRecord, UnitCoherencyResult
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.pathing import (
    PathValidationResult,
    PathWitness,
    TerrainPathLegalityResult,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model, ModelVolume


def test_source_backed_conditional_charge_rule_ir_classifies_and_overlays_heroic() -> None:
    record, clauses = _conditional_charge_ability_record()

    assert conditional_charge_consumer_ids_for_clause(clauses[0]) == (
        CATALOG_IR_STRATAGEM_PHASE_USE_EXCEPTION_CONSUMER_ID,
    )
    assert catalog_rule_ir_consumers_for_clause(clauses[0]) == (
        CATALOG_IR_STRATAGEM_PHASE_USE_EXCEPTION_CONSUMER_ID,
    )
    assert catalog_rule_ir_consumers_for_clause(clauses[1]) == (
        CATALOG_IR_STRATAGEM_COST_MODIFIER_CONSUMER_ID,
    )
    assert conditional_charge_consumer_ids_for_clause(clauses[2]) == (
        CATALOG_IR_FRIENDLY_ENGAGED_ANCHOR_CHARGE_CONSUMER_ID,
    )
    assert catalog_rule_ir_consumers_for_clause(clauses[2]) == (
        CATALOG_IR_FRIENDLY_ENGAGED_ANCHOR_CHARGE_CONSUMER_ID,
    )

    base_records = eleventh_edition_core_stratagem_catalog_records()
    base_heroic = next(
        item for item in base_records if item.definition.stratagem_id == "heroic-intervention"
    )
    overlaid = stratagem_records_with_source_backed_phase_use_exceptions(
        ability_indexes_by_player_id={
            "player-a": AbilityCatalogIndex.from_records((record,)),
        },
        stratagem_records=(),
    )
    assert tuple(item.definition.stratagem_id for item in overlaid) == ("heroic-intervention",)
    heroic = next(
        item for item in overlaid if item.definition.stratagem_id == "heroic-intervention"
    )
    exception = stratagem_phase_use_exception(heroic.definition)

    assert exception is not None
    assert exception.source_ability_id == record.definition.ability_id
    assert exception.source_id == record.definition.source_id
    assert exception.eligible_datasheet_ids == ("core-intercessor-like-infantry",)
    assert exception.frequency_scope == "phase_per_unit"
    assert exception.bypass_same_stratagem_per_phase is True
    assert exception.does_not_block_other_units is True
    assert isinstance(base_heroic.definition.effect_payload, dict)
    assert isinstance(heroic.definition.effect_payload, dict)
    assert (
        heroic.definition.effect_payload["modes"] == base_heroic.definition.effect_payload["modes"]
    )


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
    assert "<" not in json.dumps(lifecycle_payload, sort_keys=True)


def test_generated_thousand_sons_maulerfiend_charge_reroll_loads_through_bundle() -> None:
    lifecycle, units = _generated_snarling_protector_charge_lifecycle(
        game_id="phase15a-generated-thousand-sons-maulerfiend-charge-reroll"
    )
    maulerfiend = units["maulerfiend"]
    assert maulerfiend.datasheet_id == "000001029"
    assert len(maulerfiend.own_models) == 1

    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    grant_request = _decision_request(
        _submit_option(
            lifecycle,
            request=selection_request,
            option_id=maulerfiend.unit_instance_id,
            result_id="phase15a-generated-thousand-sons-maulerfiend-selected",
        )
    )
    pair_options = _conditional_charge_pair_options(grant_request)
    enemy_id = units["enemy"].unit_instance_id
    source_payload = pair_options[enemy_id]

    assert grant_request.decision_type == SELECT_CHARGE_DECLARATION_GRANT_DECISION_TYPE
    assert source_payload["ability_id"] == "000001029:snarling-protector"
    assert source_payload["source_rule_id"] == (
        "data-package:core-v2:wahapedia-" + "1" + "0" + "e-bridge:phase17k-generated:"
        "Datasheets_abilities:000001029:2"
    )
    assert source_payload["clause_id"] == (
        "phase17k:thousand-sons:maulerfiend:datasheet:000001029:2:clause:003"
    )
    assert source_payload["source_component_unit_instance_id"] == maulerfiend.unit_instance_id
    assert source_payload["anchor_unit_instance_id"] == units["psyker-anchor"].unit_instance_id
    assert source_payload[CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY] == [enemy_id]

    reroll_request = _decision_request(
        _submit_option(
            lifecycle,
            request=grant_request,
            option_id=cast(str, source_payload["hook_id"]),
            result_id="phase15a-generated-thousand-sons-maulerfiend-grant-selected",
        )
    )
    assert reroll_request.decision_type == DICE_REROLL_DECISION_TYPE


def test_end_charge_heroic_ordinary_opportunity_is_independent_of_snarling_state() -> None:
    without_source, without_source_units = _end_charge_heroic_session(
        game_id="phase15a-ordinary-heroic-without-snarling",
        maulerfiend_selection_ids=(),
        ordinary_selection_ids=("ordinary",),
        command_points=1,
    )
    with_source, with_source_units = _end_charge_heroic_session(
        game_id="phase15a-ordinary-heroic-with-snarling",
        maulerfiend_selection_ids=("maulerfiend",),
        ordinary_selection_ids=("ordinary",),
        command_points=1,
    )
    cases: list[tuple[str, LocalGameSession, dict[str, UnitInstance]]] = [
        ("absent", without_source, without_source_units),
        ("eligible", with_source.fork(), with_source_units),
        ("engaged", with_source.fork(), with_source_units),
        ("out_of_range", with_source.fork(), with_source_units),
        ("unplaced", with_source.fork(), with_source_units),
        ("destroyed", with_source.fork(), with_source_units),
    ]
    opportunity_signatures: list[tuple[str, str, str | None]] = []

    for source_state, session, units in cases:
        state = _state(session.lifecycle)
        source = units.get("maulerfiend")
        if source is not None:
            _set_snarling_source_state_for_heroic_test(
                state=state,
                unit=source,
                source_state=source_state,
            )
        request = _decision_request(session.advance_until_decision_or_terminal())
        proposal = _heroic_proposal_from_request(request)
        opportunity_signatures.append(
            (
                request.decision_type,
                proposal.stratagem_id,
                proposal.context.timing_window_id,
            )
        )

        assert request.actor_id == "player-a"
        assert request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE
        if source is not None and source_state not in {"eligible"}:
            invalid_result_id = f"phase15a-{source_state}-snarling-target-invalid"
            invalid = _submit_end_charge_heroic_target(
                session,
                request=request,
                target_unit_instance_id=source.unit_instance_id,
                result_id=invalid_result_id,
            )
            assert invalid.status_kind is LifecycleStatusKind.INVALID
            assert session.lifecycle.pending_decision_request() == request
            assert all(use.result_id != invalid_result_id for use in state.stratagem_use_records)

        ordinary_result_id = f"phase15a-{source_state}-ordinary-heroic-selected"
        movement_status = _submit_end_charge_heroic_target(
            session,
            request=request,
            target_unit_instance_id=units["ordinary"].unit_instance_id,
            result_id=ordinary_result_id,
        )
        ordinary_use = _stratagem_use_for_result_id(
            state,
            result_id=ordinary_result_id,
        )

        assert _decision_request(movement_status).decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
        assert ordinary_use.command_point_cost == 1
        assert ordinary_use.command_point_modifier_ids == ()
        assert state.command_point_total("player-a") == 0

    assert len(set(opportunity_signatures)) == 1


@pytest.mark.parametrize("enemy_context", ["unplaced", "out_of_range"])
@pytest.mark.parametrize("command_points", [1, 2])
def test_end_charge_heroic_reaction_requires_concrete_legal_affordable_target(
    enemy_context: str,
    command_points: int,
) -> None:
    lifecycle, units = _generated_snarling_protector_charge_lifecycle(
        game_id=(f"phase15a-snarling-protector-no-legal-target-{enemy_context}-{command_points}-cp")
    )
    state = _state(lifecycle)
    state.active_player_id = "player-b"
    state.gain_command_points(
        player_id="player-a",
        amount=command_points,
        source_id=(f"phase15a:snarling-protector:{enemy_context}:{command_points}-cp"),
        source_kind=CommandPointSourceKind.OTHER,
    )
    assert state.battlefield_state is not None
    if enemy_context == "unplaced":
        state.battlefield_state = state.battlefield_state.without_unit_placement(
            units["enemy"].unit_instance_id
        )
    else:
        state.replace_battlefield_state(
            state.battlefield_state.with_unit_placement(
                _unit_placement_at(
                    units["enemy"],
                    army_id="army-beta",
                    player_id="player-b",
                    poses=_compact_test_unit_poses(
                        origin=Pose.at(70.0, 70.0),
                        model_count=len(units["enemy"].own_models),
                    ),
                )
            )
        )
    bundle = object.__getattribute__(lifecycle, "_runtime_content_bundle")
    assert isinstance(bundle, RuntimeContentBundle)

    status = request_end_opponent_charge_heroic_intervention_if_available(
        state=state,
        decisions=lifecycle.decision_controller,
        reaction_queue=lifecycle.reaction_queue,
        stratagem_index=bundle.stratagem_indexes_by_player_id["player-a"],
        stratagem_cost_modifier_registry=bundle.stratagem_cost_modifier_registry,
    )

    assert status is None
    assert lifecycle.reaction_queue.frames == ()
    assert lifecycle.decision_controller.queue.pending_requests == ()


def test_generated_snarling_protector_heroic_uses_charge_adapter_and_replay_path() -> None:
    session, units = _end_charge_heroic_session(
        game_id="phase15a-generated-snarling-protector-heroic",
        maulerfiend_selection_ids=("maulerfiend",),
        ordinary_selection_ids=("ordinary",),
        command_points=1,
    )
    lifecycle = session.lifecycle
    state = _state(lifecycle)
    maulerfiend = units["maulerfiend"]
    ordinary = units["ordinary"]
    for unit in (maulerfiend, ordinary):
        add_modifier(
            state,
            effect_id=f"test:heroic-fixture:{unit.unit_instance_id}",
            kind="modify_dice_roll",
            delta=20,
            unit_instance_id=unit.unit_instance_id,
        )
    assert maulerfiend.datasheet_id == "000001029"
    assert state.command_point_total("player-a") == 1
    bundle = object.__getattribute__(lifecycle, "_runtime_content_bundle")
    assert isinstance(bundle, RuntimeContentBundle)
    heroic = next(
        record
        for record in bundle.stratagem_indexes_by_player_id["player-a"].all_records()
        if record.definition.stratagem_id == "heroic-intervention"
    )
    exception = stratagem_phase_use_exception(heroic.definition)
    assert exception is not None
    assert exception.eligible_datasheet_ids == ("000001029",)
    request = _decision_request(session.advance_until_decision_or_terminal())
    request_payload = cast(dict[str, JsonValue], request.payload)
    proposal = StratagemTargetProposal.from_payload(
        cast(StratagemTargetProposalPayload, request_payload["proposal_request"])
    )
    reaction_window = cast(dict[str, JsonValue], request_payload["reaction_window"])
    parent = cast(dict[str, JsonValue], request_payload["parent"])

    assert request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE
    assert request.actor_id == "player-a"
    assert request_payload["declinable"] is True
    assert proposal.stratagem_id == "heroic-intervention"
    assert proposal.context.timing_window_id == (
        "heroic-intervention-end-charge-round-01-active-player-b-player-player-a"
    )
    timing_window = cast(dict[str, JsonValue], reaction_window["timing_window"])
    assert timing_window["window_id"] == proposal.context.timing_window_id
    assert parent["step"] == "charge_phase_end_reactions"
    checkpoint = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    assert restored.lifecycle.to_payload() == session.lifecycle.to_payload()
    assert restored.lifecycle.pending_decision_request() == request
    assert "<" not in json.dumps(checkpoint, sort_keys=True)

    decline_session = restored.fork()
    decline_request = decline_session.lifecycle.pending_decision_request()
    assert decline_request is not None
    assert decline_request == request
    declined = decline_session.submit_parameterized_payload(
        request_id=decline_request.request_id,
        payload=stratagem_decline_payload(),
        result_id="phase15a-generated-snarling-protector-heroic-declined",
    )
    declined_state = _state(decline_session.lifecycle)
    assert declined.status_kind is not LifecycleStatusKind.INVALID
    assert declined_state.current_battle_phase is BattlePhase.FIGHT
    assert decline_session.lifecycle.reaction_queue.frames == ()
    assert len(_event_payloads(decline_session.lifecycle, "stratagem_window_declined")) == 1
    assert all(
        pending.decision_type != STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE
        for pending in decline_session.lifecycle.decision_controller.queue.pending_requests
    )

    targets = {
        "ordinary": ordinary.unit_instance_id,
        "snarling": maulerfiend.unit_instance_id,
    }
    expected_costs = {"ordinary": 1, "snarling": 0}
    for order in (("ordinary", "snarling"), ("snarling", "ordinary")):
        branch = restored.fork()
        first_kind, second_kind = order
        first_result_id = f"phase15a-generated-heroic-{first_kind}-first"
        first_movement = _submit_end_charge_heroic_target(
            branch,
            request=_require_pending_request(branch),
            target_unit_instance_id=targets[first_kind],
            result_id=first_result_id,
        )
        first_movement_request = _decision_request(first_movement)
        first_use = _stratagem_use_for_result_id(
            _state(branch.lifecycle),
            result_id=first_result_id,
        )
        assert first_use.request_id == request.request_id
        assert first_use.command_point_cost == expected_costs[first_kind]
        assert first_use.command_point_modifier_source_ids == (
            () if first_kind == "ordinary" else (exception.source_id,)
        )
        if first_kind == "ordinary":
            branch = LocalGameSession.from_persistence_payload(branch.to_persistence_payload())
            assert (
                _stratagem_use_for_result_id(
                    _state(branch.lifecycle),
                    result_id=first_result_id,
                )
                == first_use
            )
            assert _require_pending_request(branch) == first_movement_request
            first_movement_request = _require_pending_request(branch)
        second_window_status = _submit_heroic_intervention_no_move(
            branch,
            movement_request=first_movement_request,
            result_id=f"phase15a-generated-heroic-{first_kind}-first-no-move",
        )
        second_request = _decision_request(second_window_status)
        second_proposal = _heroic_proposal_from_request(second_request)
        assert second_proposal.context.timing_window_id == proposal.context.timing_window_id

        second_result_id = f"phase15a-generated-heroic-{second_kind}-second"
        second_movement = _submit_end_charge_heroic_target(
            branch,
            request=second_request,
            target_unit_instance_id=targets[second_kind],
            result_id=second_result_id,
        )
        second_use = _stratagem_use_for_result_id(
            _state(branch.lifecycle),
            result_id=second_result_id,
        )
        assert second_use.command_point_cost == expected_costs[second_kind]
        assert second_use.command_point_modifier_source_ids == (
            () if second_kind == "ordinary" else (exception.source_id,)
        )
        completed = _submit_heroic_intervention_no_move(
            branch,
            movement_request=_decision_request(second_movement),
            result_id=f"phase15a-generated-heroic-{second_kind}-second-no-move",
        )
        branch_state = _state(branch.lifecycle)
        assert completed.status_kind is not LifecycleStatusKind.INVALID
        assert branch_state.current_battle_phase is BattlePhase.FIGHT
        assert branch_state.command_point_total("player-a") == 0
        assert branch.lifecycle.reaction_queue.frames == ()
        replay = ReplayRunner.from_payload(
            branch.replay_artifact(
                artifact_id=f"replay:phase15a:heroic:{first_kind}-then-{second_kind}"
            )
        ).run()
        assert replay.status is ReplayRunStatus.REPRODUCED


def test_end_charge_heroic_two_snarling_units_each_use_exception_once() -> None:
    session, units = _end_charge_heroic_session(
        game_id="phase15a-two-snarling-protectors",
        maulerfiend_selection_ids=("maulerfiend-1", "maulerfiend-2"),
        ordinary_selection_ids=(),
        command_points=0,
    )
    state = _state(session.lifecycle)
    first_request = _decision_request(session.advance_until_decision_or_terminal())
    first_result_id = "phase15a-two-snarling-first-selected"
    first_movement = _submit_end_charge_heroic_target(
        session,
        request=first_request,
        target_unit_instance_id=units["maulerfiend-1"].unit_instance_id,
        result_id=first_result_id,
    )
    second_window_status = _submit_heroic_intervention_no_move(
        session,
        movement_request=_decision_request(first_movement),
        result_id="phase15a-two-snarling-first-no-move",
    )
    second_request = _decision_request(second_window_status)
    records_before_repeat = len(session.lifecycle.decision_controller.records)

    repeated = _submit_end_charge_heroic_target(
        session,
        request=second_request,
        target_unit_instance_id=units["maulerfiend-1"].unit_instance_id,
        result_id="phase15a-two-snarling-first-repeated",
    )

    assert repeated.status_kind is LifecycleStatusKind.INVALID
    assert repeated.payload == {"invalid_reason": "source_ability_once_per_phase_per_unit"}
    assert session.lifecycle.pending_decision_request() == second_request
    assert len(session.lifecycle.decision_controller.records) == records_before_repeat
    assert len(state.stratagem_use_records) == 1

    second_result_id = "phase15a-two-snarling-second-selected"
    second_movement = _submit_end_charge_heroic_target(
        session,
        request=second_request,
        target_unit_instance_id=units["maulerfiend-2"].unit_instance_id,
        result_id=second_result_id,
    )
    completed = _submit_heroic_intervention_no_move(
        session,
        movement_request=_decision_request(second_movement),
        result_id="phase15a-two-snarling-second-no-move",
    )
    uses = tuple(
        _stratagem_use_for_result_id(state, result_id=result_id)
        for result_id in (first_result_id, second_result_id)
    )

    assert completed.status_kind is not LifecycleStatusKind.INVALID
    assert state.current_battle_phase is BattlePhase.FIGHT
    assert tuple(use.command_point_cost for use in uses) == (0, 0)
    assert tuple(use.target_binding.target_unit_instance_id for use in uses) == (
        units["maulerfiend-1"].unit_instance_id,
        units["maulerfiend-2"].unit_instance_id,
    )
    assert state.command_point_total("player-a") == 0
    assert session.lifecycle.reaction_queue.frames == ()


def test_source_backed_conditional_charge_rejects_stale_selected_anchor() -> None:
    lifecycle, units = _conditional_charge_lifecycle(
        game_id="phase15a-source-backed-conditional-charge-stale"
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    grant_request = _decision_request(
        _submit_option(
            lifecycle,
            request=selection_request,
            option_id=units["charger"].unit_instance_id,
            result_id="phase15a-source-backed-conditional-charge-stale-select",
        )
    )
    pair_options = _conditional_charge_pair_options(grant_request)
    selected = pair_options[units["enemy-1"].unit_instance_id]
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    anchor = units["psyker-anchor-1"]
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        _unit_placement_at(
            anchor,
            army_id="army-alpha",
            player_id="player-a",
            poses=_compact_test_unit_poses(
                origin=Pose.at(50.0, 50.0),
                model_count=len(anchor.own_models),
            ),
        )
    )
    records_before = len(lifecycle.decision_controller.records)

    invalid = _submit_option(
        lifecycle,
        request=grant_request,
        option_id=cast(str, selected["hook_id"]),
        result_id="phase15a-source-backed-conditional-charge-stale-result",
    )

    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert "not available" in cast(str, cast(dict[str, object], invalid.payload)["detail"])
    assert lifecycle.decision_controller.queue.pending_requests == (grant_request,)
    assert len(lifecycle.decision_controller.records) == records_before
    assert state.persisting_effects_for_unit(units["charger"].unit_instance_id) == ()


def test_charge_declaration_grant_selection_records_end_phase_unit_effect() -> None:
    lifecycle, units = _charge_lifecycle_with_declaration_grants(
        game_id="phase15a-charge-grant-end-phase"
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    grant_request = _decision_request(
        _submit_option(
            lifecycle,
            request=selection_request,
            option_id=units["intercessor-1"].unit_instance_id,
            result_id="phase15a-charge-grant-end-phase-selection",
        )
    )

    assert grant_request.decision_type == SELECT_CHARGE_DECLARATION_GRANT_DECISION_TYPE
    assert {option.option_id for option in grant_request.options} == {
        DECLINE_CHARGE_DECLARATION_GRANT_OPTION_ID,
        _END_PHASE_CHARGE_GRANT_ID,
        _END_TURN_CHARGE_GRANT_ID,
    }

    continued = _submit_option(
        lifecycle,
        request=grant_request,
        option_id=_END_PHASE_CHARGE_GRANT_ID,
        result_id="phase15a-charge-grant-end-phase-result",
    )

    assert continued.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    effects = _state(lifecycle).persisting_effects_for_unit(units["intercessor-1"].unit_instance_id)
    assert len(effects) == 1
    assert effects[0].source_rule_id == "phase15a:test-charge-grant-source:end-phase"
    assert effects[0].expiration.expiration_kind.value == "end_phase"
    resolved = _last_event_payload(lifecycle, "charge_declaration_grant_decision_resolved")
    assert resolved["selected_option_id"] == _END_PHASE_CHARGE_GRANT_ID
    assert len(cast(list[object], resolved["persisting_effects"])) == 1


def test_charge_declaration_grant_selection_honors_explicit_targets_and_end_turn() -> None:
    lifecycle, units = _charge_lifecycle_with_declaration_grants(
        game_id="phase15a-charge-grant-end-turn"
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    grant_request = _decision_request(
        _submit_option(
            lifecycle,
            request=selection_request,
            option_id=units["intercessor-1"].unit_instance_id,
            result_id="phase15a-charge-grant-end-turn-selection",
        )
    )

    continued = _submit_option(
        lifecycle,
        request=grant_request,
        option_id=_END_TURN_CHARGE_GRANT_ID,
        result_id="phase15a-charge-grant-end-turn-result",
    )

    assert continued.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    target_effects = _state(lifecycle).persisting_effects_for_unit(units["enemy"].unit_instance_id)
    assert len(target_effects) == 1
    assert target_effects[0].source_rule_id == "phase15a:test-charge-grant-source:end-turn"
    assert target_effects[0].target_unit_instance_ids == (units["enemy"].unit_instance_id,)
    assert target_effects[0].expiration.expiration_kind.value == "end_turn"


def test_declining_charge_declaration_grant_resumes_roll_without_effect() -> None:
    lifecycle, units = _charge_lifecycle_with_declaration_grants(
        game_id="phase15a-charge-grant-decline"
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    grant_request = _decision_request(
        _submit_option(
            lifecycle,
            request=selection_request,
            option_id=units["intercessor-1"].unit_instance_id,
            result_id="phase15a-charge-grant-decline-selection",
        )
    )

    continued = _submit_option(
        lifecycle,
        request=grant_request,
        option_id=DECLINE_CHARGE_DECLARATION_GRANT_OPTION_ID,
        result_id="phase15a-charge-grant-decline-result",
    )

    assert continued.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert (
        _state(lifecycle).persisting_effects_for_unit(units["intercessor-1"].unit_instance_id) == ()
    )
    resolved = _last_event_payload(lifecycle, "charge_declaration_grant_decision_resolved")
    assert resolved["selected_charge_declaration_grants"] == []
    assert resolved["persisting_effects"] == []
    assert _event_payloads(lifecycle, "charge_roll_resolved")


def test_charge_declaration_grant_rejects_source_ineligibility_without_queue_pop() -> None:
    lifecycle, units = _charge_lifecycle_with_declaration_grants(
        game_id="phase15a-charge-grant-ineligible"
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    grant_request = _decision_request(
        _submit_option(
            lifecycle,
            request=selection_request,
            option_id=units["intercessor-1"].unit_instance_id,
            result_id="phase15a-charge-grant-ineligible-selection",
        )
    )
    state = _state(lifecycle)
    state.record_advanced_unit_state(_advanced_unit_state(units["intercessor-1"].unit_instance_id))
    records_before = len(lifecycle.decision_controller.records)

    invalid = _submit_option(
        lifecycle,
        request=grant_request,
        option_id=_END_PHASE_CHARGE_GRANT_ID,
        result_id="phase15a-charge-grant-ineligible-result",
    )

    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert cast(dict[str, object], invalid.payload)["field"] == "eligibility_context"
    assert lifecycle.decision_controller.queue.pending_requests == (grant_request,)
    assert len(lifecycle.decision_controller.records) == records_before
    assert state.persisting_effects_for_unit(units["intercessor-1"].unit_instance_id) == ()


def test_charge_declaration_grant_rejects_missing_active_selection_without_queue_pop() -> None:
    lifecycle, units = _charge_lifecycle_with_declaration_grants(
        game_id="phase15a-charge-grant-missing-selection"
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    grant_request = _decision_request(
        _submit_option(
            lifecycle,
            request=selection_request,
            option_id=units["intercessor-1"].unit_instance_id,
            result_id="phase15a-charge-grant-missing-selection-select",
        )
    )
    state = _state(lifecycle)
    state.replace_charge_phase_state(
        ChargePhaseState(battle_round=state.battle_round, active_player_id="player-a")
    )
    records_before = len(lifecycle.decision_controller.records)

    invalid = _submit_option(
        lifecycle,
        request=grant_request,
        option_id=_END_PHASE_CHARGE_GRANT_ID,
        result_id="phase15a-charge-grant-missing-selection-result",
    )

    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert cast(dict[str, object], invalid.payload)["field"] == "charge_phase_state"
    assert lifecycle.decision_controller.queue.pending_requests == (grant_request,)
    assert len(lifecycle.decision_controller.records) == records_before


def test_charge_declaration_grant_rejects_provider_drift_without_queue_pop() -> None:
    lifecycle, units = _charge_lifecycle_with_declaration_grants(
        game_id="phase15a-charge-grant-provider-drift"
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    grant_request = _decision_request(
        _submit_option(
            lifecycle,
            request=selection_request,
            option_id=units["intercessor-1"].unit_instance_id,
            result_id="phase15a-charge-grant-provider-drift-selection",
        )
    )
    _install_charge_declaration_registry(lifecycle, ChargeDeclarationHookRegistry.empty())
    records_before = len(lifecycle.decision_controller.records)

    invalid = _submit_option(
        lifecycle,
        request=grant_request,
        option_id=_END_PHASE_CHARGE_GRANT_ID,
        result_id="phase15a-charge-grant-provider-drift-result",
    )

    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert "not available" in cast(str, cast(dict[str, object], invalid.payload)["detail"])
    assert lifecycle.decision_controller.queue.pending_requests == (grant_request,)
    assert len(lifecycle.decision_controller.records) == records_before


def test_charge_declaration_grant_rejects_malformed_finite_result_without_queue_pop() -> None:
    lifecycle, units = _charge_lifecycle_with_declaration_grants(
        game_id="phase15a-charge-grant-malformed-result"
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    grant_request = _decision_request(
        _submit_option(
            lifecycle,
            request=selection_request,
            option_id=units["intercessor-1"].unit_instance_id,
            result_id="phase15a-charge-grant-malformed-selection",
        )
    )
    result = FiniteOptionSubmission(
        request_id=grant_request.request_id,
        selected_option_id=_END_PHASE_CHARGE_GRANT_ID,
        result_id="phase15a-charge-grant-malformed-result",
    ).to_result(grant_request)
    records_before = len(lifecycle.decision_controller.records)

    invalid = lifecycle.submit_decision(replace(result, payload=None))

    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert "payload must match" in cast(str, cast(dict[str, object], invalid.payload)["detail"])
    assert lifecycle.decision_controller.queue.pending_requests == (grant_request,)
    assert len(lifecycle.decision_controller.records) == records_before


@pytest.mark.parametrize(
    ("schema_case", "expected_field"),
    [
        ("non_object", "payload"),
        ("proposal_kind", "proposal_kind"),
        ("movement_mode", "movement_mode"),
        ("movement_phase_action", "movement_phase_action"),
        ("charge_targets", "charge_target_unit_instance_ids"),
        ("witness", "witness"),
    ],
)
def test_charge_move_submission_reports_precise_schema_field_without_queue_pop(
    schema_case: str,
    expected_field: str,
) -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(
            origin=Pose.at(20.0, 20.0),
            model_count=5,
        ),
        game_id="phase15a-success-charge-order47",
    )
    request = _charge_move_request_after_selection(
        lifecycle,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        result_id=f"phase15a-charge-schema-{schema_case}-selection",
    )
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    proposal = ChargeMoveProposal(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=proposal_request.proposal_kind,
        unit_instance_id=proposal_request.unit_instance_id,
        movement_phase_action="charge_move",
        movement_mode=MovementMode.CHARGE,
        charge_target_unit_instance_ids=(units["enemy"].unit_instance_id,),
        witness=_charge_path_witness_for_unit(
            lifecycle,
            unit_instance_id=units["intercessor-1"].unit_instance_id,
            dx=3.0,
        ),
    )
    payload: JsonValue = cast(
        JsonValue,
        json.loads(json.dumps(proposal.to_payload(), sort_keys=True)),
    )
    if schema_case == "non_object":
        payload = None
    else:
        payload_object = cast(dict[str, JsonValue], payload)
        if schema_case == "proposal_kind":
            payload_object["proposal_kind"] = ProposalKind.NORMAL_MOVE.value
        elif schema_case == "movement_mode":
            payload_object["movement_mode"] = MovementMode.NORMAL.value
        elif schema_case == "movement_phase_action":
            payload_object["movement_phase_action"] = "normal_move"
        elif schema_case == "charge_targets":
            payload_object["charge_target_unit_instance_ids"] = [
                units["enemy"].unit_instance_id,
                units["enemy"].unit_instance_id,
            ]
        elif schema_case == "witness":
            payload_object["witness"] = {"model_paths": []}
    records_before = len(lifecycle.decision_controller.records)

    invalid = lifecycle.submit_decision(
        ParameterizedSubmission(
            request_id=request.request_id,
            result_id=f"phase15a-charge-schema-{schema_case}-result",
            payload=payload,
        ).to_result(request)
    )

    assert invalid.status_kind is LifecycleStatusKind.INVALID
    violation = _first_proposal_validation_violation(invalid)
    assert violation["violation_code"] == "proposal_payload_malformed"
    assert violation["field"] == expected_field
    assert lifecycle.decision_controller.queue.pending_requests == (request,)
    assert len(lifecycle.decision_controller.records) == records_before


@pytest.mark.parametrize(
    ("stale_case", "expected_violation"),
    [
        ("phase_state_missing", "charge_phase_state_missing"),
        ("distance_state_missing", "charge_distance_state_missing"),
        ("required_target_drift", "charge_required_targets_drift"),
        ("witness_unit_drift", "charge_witness_unit_drift"),
        ("witness_start_drift", "charge_witness_start_drift"),
    ],
)
def test_charge_move_submission_rejects_stale_context_without_authoritative_mutation(
    stale_case: str,
    expected_violation: str,
) -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(
            origin=Pose.at(20.0, 20.0),
            model_count=5,
        ),
        game_id="phase15a-success-charge-order47",
    )
    charger_id = units["intercessor-1"].unit_instance_id
    target_id = units["enemy"].unit_instance_id
    request = _charge_move_request_after_selection(
        lifecycle,
        unit_instance_id=charger_id,
        result_id=f"phase15a-charge-stale-{stale_case}-selection",
    )
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    state = _state(lifecycle)
    target_ids: tuple[str, ...] = ()
    witness: PathWitness | None = None
    if stale_case == "phase_state_missing":
        state.replace_charge_phase_state(None)
    elif stale_case == "distance_state_missing":
        state.replace_charge_phase_state(
            ChargePhaseState(
                battle_round=state.battle_round,
                active_player_id="player-a",
                selected_unit_ids=(charger_id,),
            )
        )
    elif stale_case == "required_target_drift":
        state.record_persisting_effect(
            selected_target_charge_persisting_effect(
                state=state,
                effect_id=f"phase15a-charge-stale-{stale_case}:effect",
                owner_player_id="player-a",
                source_rules_unit_instance_id=charger_id,
                source_component_unit_instance_id=charger_id,
                selected_target_unit_instance_id=target_id,
            )
        )
    elif stale_case == "witness_unit_drift":
        target_ids = (target_id,)
        witness = _charge_path_witness_for_unit(
            lifecycle,
            unit_instance_id=target_id,
            dx=-0.25,
        )
    elif stale_case == "witness_start_drift":
        target_ids = (target_id,)
        current_witness = _charge_path_witness_for_unit(
            lifecycle,
            unit_instance_id=charger_id,
            dx=0.25,
        )
        witness = PathWitness.for_paths(
            tuple(
                (
                    model_id,
                    (
                        Pose.at(
                            poses[0].position.x + 0.1,
                            poses[0].position.y,
                            poses[0].position.z,
                            facing_degrees=poses[0].facing.degrees,
                        ),
                        *poses[1:],
                    ),
                )
                for model_id, poses in current_witness.model_paths
            )
        )
    records_before = len(lifecycle.decision_controller.records)

    invalid = _submit_charge_move_proposal(
        lifecycle,
        request=request,
        result_id=f"phase15a-charge-stale-{stale_case}-result",
        proposal=ChargeMoveProposal(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
            unit_instance_id=proposal_request.unit_instance_id,
            movement_phase_action="charge_move",
            movement_mode=MovementMode.CHARGE,
            charge_target_unit_instance_ids=target_ids,
            witness=witness,
        ),
    )

    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert _first_proposal_validation_violation(invalid)["violation_code"] == (expected_violation)
    assert lifecycle.decision_controller.queue.pending_requests == (request,)
    assert len(lifecycle.decision_controller.records) == records_before


@pytest.mark.parametrize(
    ("endpoint_case", "expected_violation"),
    [
        ("not_closer", "charge_not_closer_to_target"),
        ("not_engaged", "charge_target_not_engaged"),
        ("distance_exceeded", "movement_distance_exceeded"),
        ("coherency_broken", "unit_coherency_broken"),
    ],
)
def test_charge_move_submission_records_rule_invalid_endpoint_and_emits_retry(
    endpoint_case: str,
    expected_violation: str,
) -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(
            origin=Pose.at(20.0, 20.0),
            model_count=5,
        ),
        game_id="phase15a-success-charge",
    )
    charger_id = units["intercessor-1"].unit_instance_id
    target_id = units["enemy"].unit_instance_id
    request = _charge_move_request_after_selection(
        lifecycle,
        unit_instance_id=charger_id,
        result_id=f"phase15a-charge-endpoint-{endpoint_case}-selection",
    )
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    context = cast(dict[str, JsonValue], proposal_request.context)
    maximum_distance = context["maximum_distance_inches"]
    assert isinstance(maximum_distance, (int, float))
    if endpoint_case == "not_closer":
        witness = _charge_path_witness_for_unit(lifecycle, unit_instance_id=charger_id, dx=-0.5)
    elif endpoint_case == "not_engaged":
        witness = _charge_path_witness_for_unit(lifecycle, unit_instance_id=charger_id, dx=0.5)
    elif endpoint_case == "distance_exceeded":
        witness = _charge_path_witness_for_unit(
            lifecycle,
            unit_instance_id=charger_id,
            dx=-(maximum_distance + 0.5),
        )
    else:
        baseline = _charge_path_witness_for_unit(
            lifecycle,
            unit_instance_id=charger_id,
            dx=3.0,
        )
        last_model_id = baseline.model_ids()[-1]
        witness = PathWitness.for_paths(
            tuple(
                (
                    model_id,
                    (
                        poses
                        if model_id != last_model_id
                        else (
                            poses[0],
                            Pose.at(
                                poses[1].position.x,
                                poses[1].position.y + 1.5,
                                poses[1].position.z,
                            ),
                            Pose.at(
                                poses[2].position.x,
                                poses[2].position.y + 3.0,
                                poses[2].position.z,
                            ),
                        )
                    ),
                )
                for model_id, poses in baseline.model_paths
            )
        )
    records_before = len(lifecycle.decision_controller.records)

    invalid = _submit_charge_move_proposal(
        lifecycle,
        request=request,
        result_id=f"phase15a-charge-endpoint-{endpoint_case}-result",
        proposal=ChargeMoveProposal(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
            unit_instance_id=proposal_request.unit_instance_id,
            movement_phase_action="charge_move",
            movement_mode=MovementMode.CHARGE,
            charge_target_unit_instance_ids=(target_id,),
            witness=witness,
        ),
    )

    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert cast(dict[str, object], invalid.payload)["violation_code"] == expected_violation
    retry = lifecycle.decision_controller.queue.pending_requests[0]
    assert retry.request_id != request.request_id
    assert lifecycle.decision_controller.queue.pending_requests == (retry,)
    assert len(lifecycle.decision_controller.records) == records_before + 1


def test_charging_unit_selection_rolls_immediately_and_uses_lifecycle_records() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="phase15a-records",
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    assert selection_request.decision_type == SELECT_CHARGING_UNIT_DECISION_TYPE
    assert selection_request.actor_id == "player-a"
    assert {
        units["intercessor-1"].unit_instance_id,
        COMPLETE_CHARGE_PHASE_OPTION_ID,
    } == {option.option_id for option in selection_request.options}

    unit_option = selection_request.option_by_id(units["intercessor-1"].unit_instance_id)
    unit_payload = cast(dict[str, object], unit_option.payload)
    eligibility_context = cast(dict[str, object], unit_payload["eligibility_context"])
    target_candidates = cast(list[dict[str, object]], eligibility_context["target_candidates"])
    assert target_candidates[0]["target_unit_instance_id"] == units["enemy"].unit_instance_id
    assert target_candidates[0]["is_legal"] is True

    status = _submit_option(
        lifecycle,
        request=selection_request,
        option_id=units["intercessor-1"].unit_instance_id,
        result_id="phase15a-select-charger",
    )
    status = choose_charge_targets(
        lifecycle,
        request=_decision_request(status),
        target_ids=(units["enemy"].unit_instance_id,),
        result_id="charge-targets-selected",
    )
    event_types = [event.event_type for event in lifecycle.decision_controller.event_log.records]
    roll_result = _roll_result_from_event(lifecycle, "charge_roll_resolved")
    lifecycle_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    proposal = MovementProposalRequest.from_decision_request_payload(
        status.decision_request.payload
    )
    assert status.decision_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    assert proposal.proposal_kind is ProposalKind.CHARGE_MOVE
    assert proposal.phase == BattlePhase.CHARGE.value
    assert proposal.movement_phase_action == "charge_move"
    assert proposal.unit_instance_id == units["intercessor-1"].unit_instance_id
    assert cast(dict[str, object], proposal.context)["movement_mode"] == "charge"
    assert [record.request.decision_type for record in lifecycle.decision_controller.records] == [
        SELECT_CHARGING_UNIT_DECISION_TYPE,
        "select_charge_targets",
    ]
    assert "charging_unit_selected" in event_types
    assert "charge_declaration_accepted" not in event_types
    assert "charge_roll_resolved" in event_types
    assert "charge_move_required" in event_types
    assert "charge_move_proposal_requested" in event_types
    assert roll_result.request.unit_instance_id == units["intercessor-1"].unit_instance_id
    assert roll_result.move_available is True
    assert units["enemy"].unit_instance_id in roll_result.reachable_target_distances_inches
    assert 2 <= roll_result.value <= 12
    assert GameLifecycle.from_payload(lifecycle_payload).to_payload() == lifecycle_payload


@pytest.mark.parametrize(
    ("ignored_modifier_id", "expected_modifier_ids"),
    [
        (
            "test:modifier-ignore:charge-penalty",
            ("test:modifier-ignore:charge-bonus",),
        ),
        (
            "test:modifier-ignore:charge-bonus",
            ("test:modifier-ignore:charge-penalty",),
        ),
    ],
)
def test_charging_unit_modifier_ignore_subsets_use_finite_lifecycle_and_round_trip(
    ignored_modifier_id: str,
    expected_modifier_ids: tuple[str, ...],
) -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(
            origin=Pose.at(20.0, 20.0),
            model_count=5,
        ),
        game_id=f"phase15a-modifier-ignore-{ignored_modifier_id.rsplit(':', maxsplit=1)[1]}",
    )
    source_unit = units["intercessor-1"]
    ability_index = AbilityCatalogIndex.from_records(
        (_charge_modifier_ignore_ability_record(datasheet_id=source_unit.datasheet_id),)
    )
    _install_charge_modifier_ignore_runtime(
        lifecycle,
        ability_index=ability_index,
        registry=_charge_modifier_ignore_registry(),
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    unit_options = tuple(
        option
        for option in selection_request.options
        if isinstance(option.payload, dict)
        and option.payload.get("submission_kind") == SELECT_CHARGING_UNIT_DECISION_TYPE
    )
    assert len(unit_options) == 4
    selected_option = next(
        option
        for option in unit_options
        if _ignored_charge_modifier_ids(option) == (ignored_modifier_id,)
    )
    restored_request = DecisionRequest.from_payload(
        json.loads(json.dumps(selection_request.to_payload(), sort_keys=True))
    )
    assert restored_request == selection_request

    status = _submit_option(
        lifecycle,
        request=selection_request,
        option_id=selected_option.option_id,
        result_id=(
            f"phase15a-modifier-ignore-select-{ignored_modifier_id.rsplit(':', maxsplit=1)[1]}"
        ),
    )
    roll_result = _roll_result_from_event(lifecycle, "charge_roll_resolved")
    assert (
        tuple(modifier.modifier_id for modifier in roll_result.request.roll_modifiers)
        == expected_modifier_ids
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert lifecycle.decision_controller.records[-1].result.payload == selected_option.payload
    modifier_events = _event_payloads(lifecycle, "modifier_ignores_selected")
    assert len(modifier_events) == 1
    effect_payload = cast(dict[str, object], modifier_events[0]["modifier_ignore_effect"])
    assert effect_payload["source_rule_id"] == "core:modifier-ignore-selection"
    lifecycle_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    restored = GameLifecycle.from_payload(
        lifecycle_payload,
        runtime_content_bundle=lifecycle._runtime_content_bundle,  # pyright: ignore[reportPrivateUsage]
    )
    assert restored.to_payload() == lifecycle_payload
    assert "object at 0x" not in json.dumps(lifecycle_payload, sort_keys=True)


def test_charging_unit_modifier_ignore_option_drift_rejects_before_queue_pop() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(
            origin=Pose.at(20.0, 20.0),
            model_count=5,
        ),
        game_id="phase15a-modifier-ignore-stale",
    )
    source_unit = units["intercessor-1"]
    ability_index = AbilityCatalogIndex.from_records(
        (_charge_modifier_ignore_ability_record(datasheet_id=source_unit.datasheet_id),)
    )
    _install_charge_modifier_ignore_runtime(
        lifecycle,
        ability_index=ability_index,
        registry=_charge_modifier_ignore_registry(),
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    stale_option = next(
        option
        for option in selection_request.options
        if _ignored_charge_modifier_ids(option) == ("test:modifier-ignore:charge-penalty",)
    )
    _install_charge_modifier_ignore_runtime(
        lifecycle,
        ability_index=ability_index,
        registry=RuntimeModifierRegistry.empty(),
    )

    status = _submit_option(
        lifecycle,
        request=selection_request,
        option_id=stale_option.option_id,
        result_id="phase15a-modifier-ignore-stale-select",
    )

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(status.payload, dict)
    assert status.payload["invalid_reason"] == "charging_unit_option_drift"
    assert status.payload["field"] == "modifier_ignore_context"
    assert lifecycle.decision_controller.queue.pending_requests == (selection_request,)
    assert lifecycle.decision_controller.records == ()
    assert _event_payloads(lifecycle, "modifier_ignores_selected") == ()
    assert _event_payloads(lifecycle, "charge_roll_resolved") == ()


def test_successful_charge_roll_creates_phase15b_movement_boundary() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="phase15a-success-charge",
    )
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    before_battlefield = state.battlefield_state.to_payload()
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())

    status = _submit_option(
        lifecycle,
        request=selection_request,
        option_id=units["intercessor-1"].unit_instance_id,
        result_id="phase15a-success-submit",
    )
    status = choose_charge_targets(
        lifecycle,
        request=_decision_request(status),
        target_ids=(units["enemy"].unit_instance_id,),
        result_id="successful-charge-targets",
    )
    roll_result = _roll_result_from_event(lifecycle, "charge_move_required")
    after_state = _state(lifecycle)
    assert after_state.battlefield_state is not None
    assert after_state.charge_phase_state is not None
    pending_distance_state = after_state.charge_phase_state.move_pending_distance_state()
    repeated_status = lifecycle.advance_until_decision_or_terminal()
    status_payload = cast(dict[str, object], status.payload)
    repeated_payload = cast(dict[str, object], repeated_status.payload)

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    proposal = MovementProposalRequest.from_decision_request_payload(
        status.decision_request.payload
    )
    assert status.decision_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    assert proposal.proposal_kind is ProposalKind.CHARGE_MOVE
    assert proposal.unit_instance_id == units["intercessor-1"].unit_instance_id
    assert status_payload["phase_body_status"] == "charge_move_proposal_required"
    assert status_payload["reachable_target_unit_instance_ids"] == [units["enemy"].unit_instance_id]
    assert repeated_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert repeated_status.decision_request == status.decision_request
    assert repeated_payload["pending_request_id"] == status.decision_request.request_id
    assert roll_result.move_available is True
    assert roll_result.status == CHARGE_MOVE_PENDING_STATUS
    assert pending_distance_state is not None
    assert pending_distance_state.roll_result == roll_result
    assert after_state.battlefield_state.to_payload() == before_battlefield
    assert _event_payloads(lifecycle, "charge_no_move_possible") == ()
    assert all(
        not _payload_has_displacements(cast(dict[str, object], event.payload))
        for event in lifecycle.decision_controller.event_log.records
    )


def test_charge_roll_with_no_reachable_targets_resolves_without_model_movement() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(27.0, 20.0), model_count=5),
        game_id="phase15a-no-move-charge",
    )
    add_modifier(
        _state(lifecycle),
        effect_id="test:charge-fixture:test_charge_roll_with_no_reachable_targets_resolves_without_model_movement",
        kind="modify_dice_roll",
        delta=-20,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
    )
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    before_battlefield = state.battlefield_state.to_payload()
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())

    status = _submit_option(
        lifecycle,
        request=selection_request,
        option_id=units["intercessor-1"].unit_instance_id,
        result_id="phase15a-no-move-submit",
    )
    roll_result = _roll_result_from_event(lifecycle, "charge_no_move_possible")
    after_state = _state(lifecycle)
    assert after_state.battlefield_state is not None

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    assert status.decision_request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    assert after_state.current_battle_phase is BattlePhase.MOVEMENT
    assert after_state.charge_phase_state is None
    assert roll_result.move_available is False
    assert roll_result.status == CHARGE_NO_MOVE_POSSIBLE_STATUS
    assert roll_result.reachable_target_distances_inches == {}
    assert after_state.battlefield_state.to_payload() == before_battlefield
    assert _event_payloads(lifecycle, "charge_move_required") == ()
    assert all(
        not _payload_has_displacements(cast(dict[str, object], event.payload))
        for event in lifecycle.decision_controller.event_log.records
    )


def test_phase15b_charge_move_proposal_applies_witness_records_displacements_and_fights_first() -> (
    None
):
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(10.0, 25.0), model_count=5),
        game_id="phase15a-success-charge",
    )
    proposal_request = _charge_move_request_after_selection(
        lifecycle,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        result_id="phase15b-select-success",
    )
    proposal = MovementProposalRequest.from_decision_request_payload(proposal_request.payload)
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    before_battlefield = state.battlefield_state.to_payload()
    target_unit_id = units["enemy"].unit_instance_id
    witness = _charge_path_witness_for_unit(
        lifecycle,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        dx=0.0,
        dy=3.0,
    )

    status = _submit_charge_move_proposal(
        lifecycle,
        request=proposal_request,
        result_id="phase15b-submit-success",
        proposal=ChargeMoveProposal(
            proposal_request_id=proposal.request_id,
            proposal_kind=proposal.proposal_kind,
            unit_instance_id=proposal.unit_instance_id,
            movement_phase_action="charge_move",
            movement_mode=MovementMode.CHARGE,
            charge_target_unit_instance_ids=(target_unit_id,),
            witness=witness,
        ),
    )
    completed = _last_event_payload(lifecycle, "charge_move_completed")
    transition_batch = cast(dict[str, object], completed["transition_batch"])
    displacements = cast(list[dict[str, object]], transition_batch["displacements"])
    endpoint_witness = cast(dict[str, object], completed["endpoint_witness"])
    persisting_effect = cast(dict[str, object], completed["persisting_effect"])
    effect_payload = cast(dict[str, object], persisting_effect["effect_payload"])
    after_state = _state(lifecycle)
    assert after_state.battlefield_state is not None

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    assert status.decision_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    fight_movement_request = MovementProposalRequest.from_decision_request_payload(
        status.decision_request.payload
    )
    assert fight_movement_request.proposal_kind is ProposalKind.PILE_IN
    assert after_state.current_battle_phase is BattlePhase.FIGHT
    assert after_state.charge_phase_state is None
    assert after_state.battlefield_state.to_payload() != before_battlefield
    assert len(displacements) == len(units["intercessor-1"].own_models)
    assert {record["displacement_kind"] for record in displacements} == {"charge_move"}
    assert {record["source_phase"] for record in displacements} == {"charge"}
    assert {record["source_step"] for record in displacements} == {"charge_move"}
    assert all(record["path_witness"] is not None for record in displacements)
    assert endpoint_witness["engaged_target_unit_instance_ids"] == [target_unit_id]
    assert endpoint_witness["preferred_distance_target_unit_instance_ids"] == [target_unit_id]
    assert endpoint_witness["non_target_engaged_unit_instance_ids"] == []
    assert persisting_effect["started_phase"] == "charge"
    assert cast(dict[str, object], persisting_effect["expiration"])["expiration_kind"] == "end_turn"
    assert effect_payload["effect_kind"] == "charge_grants_fights_first"
    assert after_state.persisting_effects_for_unit(units["intercessor-1"].unit_instance_id)
    assert [record.request.decision_type for record in lifecycle.decision_controller.records] == [
        SELECT_CHARGING_UNIT_DECISION_TYPE,
        "select_charge_targets",
        MOVEMENT_PROPOSAL_DECISION_TYPE,
    ]
    assert _event_payloads(lifecycle, "charge_move_invalid") == ()


def test_phase15b_charge_move_no_move_choice_records_decline_without_mutation() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="phase15a-success-charge",
    )
    proposal_request = _charge_move_request_after_selection(
        lifecycle,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        result_id="phase15b-select-no-move",
    )
    proposal = MovementProposalRequest.from_decision_request_payload(proposal_request.payload)
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    before_battlefield = state.battlefield_state.to_payload()

    status = _submit_charge_move_proposal(
        lifecycle,
        request=proposal_request,
        result_id="phase15b-submit-no-move",
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
    declined = _last_event_payload(lifecycle, "charge_move_declined")
    after_state = _state(lifecycle)
    assert after_state.battlefield_state is not None

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    assert status.decision_request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    assert after_state.current_battle_phase is BattlePhase.MOVEMENT
    assert after_state.charge_phase_state is None
    assert after_state.battlefield_state.to_payload() == before_battlefield
    assert after_state.persisting_effects_for_unit(units["intercessor-1"].unit_instance_id) == ()
    assert declined["phase_body_status"] == "charge_move_declined"
    assert _event_payloads(lifecycle, "charge_move_completed") == ()
    assert _event_payloads(lifecycle, "charge_move_invalid") == ()


def test_phase15f_charge_completion_gate_runs_for_both_players() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="phase15f-charge-both-players",
    )

    player_a_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    player_a_status = _submit_option(
        lifecycle,
        request=player_a_request,
        option_id=COMPLETE_CHARGE_PHASE_OPTION_ID,
        result_id="phase15f-player-a-complete-charge",
    )
    state = _state(lifecycle)
    player_a_movement_request = _decision_request(player_a_status)
    assert state.current_battle_phase is BattlePhase.MOVEMENT
    assert state.active_player_id == "player-b"
    assert state.charge_phase_state is None
    assert player_a_movement_request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE

    lifecycle.decision_controller.queue.remove_by_id(player_a_movement_request.request_id)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.CHARGE)
    state.active_player_id = "player-b"

    player_b_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    player_b_status = _submit_option(
        lifecycle,
        request=player_b_request,
        option_id=COMPLETE_CHARGE_PHASE_OPTION_ID,
        result_id="phase15f-player-b-complete-charge",
    )
    player_b_completed = _last_event_payload(lifecycle, "charge_phase_completed")

    assert player_b_request.actor_id == "player-b"
    assert units["enemy"].unit_instance_id in {
        option.option_id for option in player_b_request.options
    }
    assert _decision_request(player_b_status).decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    assert player_b_completed["active_player_id"] == "player-b"
    assert len(_event_payloads(lifecycle, "charge_phase_completed")) == 2
    assert [record.request.decision_type for record in lifecycle.decision_controller.records].count(
        SELECT_CHARGING_UNIT_DECISION_TYPE
    ) == 2


def test_phase15b_charge_target_without_witness_rejects_before_queue_pop() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="phase15a-success-charge",
    )
    proposal_request = _charge_move_request_after_selection(
        lifecycle,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        result_id="phase15b-select-missing-witness",
    )
    proposal = MovementProposalRequest.from_decision_request_payload(proposal_request.payload)
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    before_battlefield = state.battlefield_state.to_payload()

    status = _submit_charge_move_proposal(
        lifecycle,
        request=proposal_request,
        result_id="phase15b-submit-missing-witness",
        proposal=ChargeMoveProposal(
            proposal_request_id=proposal.request_id,
            proposal_kind=proposal.proposal_kind,
            unit_instance_id=proposal.unit_instance_id,
            movement_phase_action="charge_move",
            movement_mode=MovementMode.CHARGE,
            charge_target_unit_instance_ids=(units["enemy"].unit_instance_id,),
            witness=None,
        ),
    )
    assert _event_payloads(lifecycle, "charge_move_proposal_invalid") == ()
    invalid = cast(dict[str, object], status.payload)
    proposal_validation = cast(dict[str, object], invalid["proposal_validation"])
    violations = cast(list[dict[str, object]], proposal_validation["violations"])
    after_state = _state(lifecycle)
    assert after_state.battlefield_state is not None

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert lifecycle.decision_controller.queue.pending_requests == (proposal_request,)
    assert len(lifecycle.decision_controller.records) == 2
    assert after_state.battlefield_state.to_payload() == before_battlefield
    assert violations[0]["violation_code"] == "charge_move_witness_required"
    assert _event_payloads(lifecycle, "charge_move_invalid") == ()


def test_phase15b_endpoint_only_charge_witness_records_rejected_attempt_and_retries() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="phase15a-success-charge",
    )
    add_modifier(
        _state(lifecycle),
        effect_id="test:charge-fixture:test_phase15b_endpoint_only_charge_witness_records_rejected_attempt_and_retries",
        kind="modify_dice_roll",
        delta=20,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
    )
    proposal_request = _charge_move_request_after_selection(
        lifecycle,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        result_id="phase15b-select-success",
    )
    proposal = MovementProposalRequest.from_decision_request_payload(proposal_request.payload)
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    before_battlefield = state.battlefield_state.to_payload()

    status = _submit_charge_move_proposal(
        lifecycle,
        request=proposal_request,
        result_id="phase15b-submit-endpoint-only",
        proposal=ChargeMoveProposal(
            proposal_request_id=proposal.request_id,
            proposal_kind=proposal.proposal_kind,
            unit_instance_id=proposal.unit_instance_id,
            movement_phase_action="charge_move",
            movement_mode=MovementMode.CHARGE,
            charge_target_unit_instance_ids=(units["enemy"].unit_instance_id,),
            witness=_charge_path_witness_for_unit(
                lifecycle,
                unit_instance_id=units["intercessor-1"].unit_instance_id,
                dx=3.0,
                endpoint_only=True,
            ),
        ),
    )
    invalid = _last_event_payload(lifecycle, "charge_move_invalid")
    retry_request = lifecycle.decision_controller.queue.pending_requests[0]
    after_state = _state(lifecycle)
    assert after_state.battlefield_state is not None

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert cast(dict[str, object], status.payload)["violation_code"] == "endpoint_only_path"
    assert invalid["violation_code"] == "endpoint_only_path"
    assert retry_request.request_id != proposal_request.request_id
    assert retry_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    assert len(lifecycle.decision_controller.records) == 3
    assert after_state.battlefield_state.to_payload() == before_battlefield
    assert len(_event_payloads(lifecycle, "charge_move_proposal_requested")) == 2


def test_phase15b_charge_move_rejects_non_target_engagement_without_mutation() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        enemy_unit_ids=("enemy-1", "enemy-2"),
        enemy_origins={
            "enemy-1": Pose.at(20.0, 20.0, facing_degrees=180.0),
            "enemy-2": Pose.at(18.6, 22.1, facing_degrees=180.0),
        },
        game_id="phase15a-success-charge",
    )
    proposal_request = _charge_move_request_after_selection(
        lifecycle,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        target_ids=(units["enemy-1"].unit_instance_id,),
        result_id="phase15b-select-success",
    )
    proposal = MovementProposalRequest.from_decision_request_payload(proposal_request.payload)
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    before_battlefield = state.battlefield_state.to_payload()

    status = _submit_charge_move_proposal(
        lifecycle,
        request=proposal_request,
        result_id="phase15b-submit-non-target-engagement",
        proposal=ChargeMoveProposal(
            proposal_request_id=proposal.request_id,
            proposal_kind=proposal.proposal_kind,
            unit_instance_id=proposal.unit_instance_id,
            movement_phase_action="charge_move",
            movement_mode=MovementMode.CHARGE,
            charge_target_unit_instance_ids=(units["enemy-1"].unit_instance_id,),
            witness=_charge_path_witness_for_unit(
                lifecycle,
                unit_instance_id=units["intercessor-1"].unit_instance_id,
                dx=3.0,
            ),
        ),
    )
    invalid = _last_event_payload(lifecycle, "charge_move_invalid")
    endpoint_witness = cast(dict[str, object], invalid["endpoint_witness"])
    after_state = _state(lifecycle)
    assert after_state.battlefield_state is not None

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert invalid["violation_code"] == "charge_non_target_engaged"
    assert endpoint_witness["non_target_engaged_unit_instance_ids"] == [
        units["enemy-2"].unit_instance_id
    ]
    assert after_state.battlefield_state.to_payload() == before_battlefield
    assert len(lifecycle.decision_controller.records) == 3
    assert lifecycle.decision_controller.queue.pending_requests[0].request_id != (
        proposal_request.request_id
    )


def test_phase15b_charge_movement_legality_applies_fly_transit_policy() -> None:
    ruleset_descriptor = RulesetDescriptor.warhammer_40000_eleventh(
        descriptor_version="core-v2-phase15b-fly-test"
    )
    walking_context = MovementLegalityContext.from_keywords(
        keywords=(),
        ruleset_descriptor=ruleset_descriptor,
        movement_mode=MovementMode.CHARGE,
        movement_phase_action=None,
        displacement_kind=ModelDisplacementKind.CHARGE_MOVE,
    )
    flying_context = MovementLegalityContext.from_keywords(
        keywords=("FLY",),
        ruleset_descriptor=ruleset_descriptor,
        movement_mode=MovementMode.CHARGE,
        movement_phase_action=None,
        displacement_kind=ModelDisplacementKind.CHARGE_MOVE,
        take_to_the_skies=True,
    )

    moving_model = Model(
        model_id="fly-check-model",
        pose=Pose.at(1.0, 1.0),
        base=CircularBase(radius=0.5),
        volume=ModelVolume(height=2.0),
    )
    witness = PathWitness.for_paths((("fly-check-model", (Pose.at(1.0, 1.0), Pose.at(2.0, 1.0))),))
    walking_path_context = walking_context.to_path_validation_context(
        moving_model=moving_model,
        witness=witness,
        battlefield_width_inches=44.0,
        battlefield_depth_inches=44.0,
    )
    flying_path_context = flying_context.to_path_validation_context(
        moving_model=moving_model,
        witness=witness,
        battlefield_width_inches=44.0,
        battlefield_depth_inches=44.0,
    )

    assert walking_path_context.to_payload()["may_transit_enemy_models"] is False
    assert flying_path_context.to_payload()["may_transit_enemy_models"] is True
    assert flying_path_context.to_payload()["may_transit_enemy_engagement"] is True


def test_phase15b_charge_move_proposal_value_object_rejects_request_drift() -> None:
    request = _charge_move_proposal_request_for_value_tests()
    witness = PathWitness.for_paths((("model-a", (Pose.at(1.0, 1.0), Pose.at(2.0, 1.0))),))
    valid_proposal = ChargeMoveProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.CHARGE_MOVE,
        unit_instance_id="unit-a",
        movement_phase_action="charge_move",
        movement_mode=MovementMode.CHARGE,
        charge_target_unit_instance_ids=("target-a",),
        witness=witness,
    )

    round_tripped = ChargeMoveProposal.from_payload(valid_proposal.to_payload())

    assert round_tripped == valid_proposal
    assert valid_proposal.validation_result_for_request(request).is_valid
    assert (
        replace(valid_proposal, proposal_request_id="request-b")
        .validation_result_for_request(request)
        .violations[0]
        .violation_code
        == "stale_proposal_request"
    )
    assert (
        valid_proposal.validation_result_for_request(
            replace(request, proposal_kind=ProposalKind.NORMAL_MOVE)
        )
        .violations[0]
        .violation_code
        == "proposal_kind_drift"
    )
    assert (
        replace(valid_proposal, unit_instance_id="unit-b")
        .validation_result_for_request(request)
        .violations[0]
        .violation_code
        == "proposal_unit_drift"
    )
    assert (
        valid_proposal.validation_result_for_request(
            replace(request, movement_phase_action="normal_move")
        )
        .violations[0]
        .violation_code
        == "proposal_action_drift"
    )
    assert (
        valid_proposal.validation_result_for_request(
            replace(
                request,
                context={
                    **dict(request.context or {}),
                    "movement_mode": "normal",
                },
            )
        )
        .violations[0]
        .violation_code
        == "proposal_movement_mode_drift"
    )
    assert replace(
        valid_proposal,
        charge_target_unit_instance_ids=("target-b",),
    ).validation_result_for_request(request).violations[0].violation_code == (
        "charge_target_not_reachable"
    )
    assert replace(
        valid_proposal,
        charge_target_unit_instance_ids=(),
    ).validation_result_for_request(request).violations[0].violation_code == (
        "no_move_witness_forbidden"
    )
    assert (
        replace(valid_proposal, witness=None)
        .validation_result_for_request(request)
        .violations[0]
        .violation_code
        == "charge_move_witness_required"
    )


def test_charge_move_proposal_requires_every_current_marked_target() -> None:
    base_request = _charge_move_proposal_request_for_value_tests()
    request = replace(
        base_request,
        context={
            **dict(base_request.context or {}),
            "reachable_target_unit_instance_ids": ["target-a", "target-b"],
            "reachable_target_distances_inches": {"target-a": 3.0, "target-b": 4.0},
            CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY: ["target-a", "target-b"],
        },
    )
    witness = PathWitness.for_paths((("model-a", (Pose.at(1.0, 1.0), Pose.at(2.0, 1.0))),))
    one_target = ChargeMoveProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.CHARGE_MOVE,
        unit_instance_id="unit-a",
        movement_phase_action="charge_move",
        movement_mode=MovementMode.CHARGE,
        charge_target_unit_instance_ids=("target-a",),
        witness=witness,
    )
    both_targets = replace(
        one_target,
        charge_target_unit_instance_ids=("target-a", "target-b"),
    )

    assert one_target.validation_result_for_request(request).violations[0].violation_code == (
        "charge_required_target_not_selected"
    )
    assert both_targets.validation_result_for_request(request).is_valid


def test_phase15b_charge_move_proposal_value_object_rejects_malformed_fields() -> None:
    request = _charge_move_proposal_request_for_value_tests()
    witness = PathWitness.for_paths((("model-a", (Pose.at(1.0, 1.0), Pose.at(2.0, 1.0))),))
    valid_proposal = ChargeMoveProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.CHARGE_MOVE,
        unit_instance_id="unit-a",
        movement_phase_action="charge_move",
        movement_mode=MovementMode.CHARGE,
        charge_target_unit_instance_ids=("target-a",),
        witness=witness,
    )

    with pytest.raises(GameLifecycleError, match="proposal_kind must be charge_move"):
        replace(valid_proposal, proposal_kind=ProposalKind.NORMAL_MOVE)
    with pytest.raises(GameLifecycleError, match="movement_mode must be charge"):
        replace(valid_proposal, movement_mode=MovementMode.NORMAL)
    with pytest.raises(GameLifecycleError, match="movement_phase_action must be charge_move"):
        replace(valid_proposal, movement_phase_action="normal_move")
    with pytest.raises(GameLifecycleError, match="must not contain duplicates"):
        replace(valid_proposal, charge_target_unit_instance_ids=("target-a", "target-a"))
    with pytest.raises(GameLifecycleError, match="witness must be a PathWitness"):
        replace(valid_proposal, witness=cast(PathWitness, object()))
    with pytest.raises(GameLifecycleError, match="Unsupported ProposalKind token"):
        ChargeMoveProposal.from_payload(
            {
                **valid_proposal.to_payload(),
                "proposal_kind": "bad-proposal-kind",
            }
        )


def test_phase15b_charge_endpoint_witness_payload_sorts_and_rejects_malformed_fields() -> None:
    witness = ChargeEndpointWitness(
        model_endpoints=(),
        selected_target_unit_instance_ids=("target-b", "target-a"),
        target_distances_before_inches={"target-b": 5.0, "target-a": 3.0},
        target_distances_after_inches={"target-b": 2.0, "target-a": 1.0},
        engaged_target_unit_instance_ids=("target-b",),
        preferred_distance_target_unit_instance_ids=("target-a",),
        non_target_engaged_unit_instance_ids=("enemy-c",),
    )

    payload = witness.to_payload()

    assert payload["selected_target_unit_instance_ids"] == ["target-a", "target-b"]
    assert list(payload["target_distances_before_inches"]) == ["target-a", "target-b"]
    assert list(payload["target_distances_after_inches"]) == ["target-a", "target-b"]
    assert payload["engaged_target_unit_instance_ids"] == ["target-b"]
    assert payload["preferred_distance_target_unit_instance_ids"] == ["target-a"]
    assert payload["non_target_engaged_unit_instance_ids"] == ["enemy-c"]
    with pytest.raises(GameLifecycleError, match="distances must be non-negative"):
        replace(witness, target_distances_after_inches={"target-a": -1.0})
    with pytest.raises(GameLifecycleError, match="must be a tuple"):
        replace(
            witness,
            engaged_target_unit_instance_ids=cast(tuple[str, ...], ["target-a"]),
        )


def test_phase15b_invalid_charge_move_resolution_cannot_emit_transition_batch() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="phase15b-invalid-resolution",
    )
    proposal_request = _charge_move_request_after_selection(
        lifecycle,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        result_id="phase15b-select-invalid-resolution",
    )
    proposal = MovementProposalRequest.from_decision_request_payload(proposal_request.payload)
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    unit_placement = state.battlefield_state.unit_placement_by_id(
        units["intercessor-1"].unit_instance_id
    )
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    proposal_context = cast(dict[str, object], proposal.context)
    maximum_distance = proposal_context["maximum_distance_inches"]
    assert isinstance(maximum_distance, (int, float))

    resolution = resolve_charge_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase15a-test"
        ),
        unit_placement=unit_placement,
        selected_target_unit_instance_ids=(units["enemy"].unit_instance_id,),
        maximum_distance_inches=maximum_distance,
        path_witness=_charge_path_witness_for_unit(
            lifecycle,
            unit_instance_id=units["intercessor-1"].unit_instance_id,
            dx=3.0,
            endpoint_only=True,
        ),
    )

    assert not resolution.is_valid
    with pytest.raises(GameLifecycleError, match="Invalid Charge Move"):
        resolution.transition_batch(before=unit_placement)


def test_phase15b_charge_move_resolution_value_object_rejects_malformed_fields() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="phase15b-resolution-value-object",
    )
    resolution, _unit_placement = _resolved_charge_move_for_tests(
        lifecycle,
        units=units,
        unit_key="intercessor-1",
        target_key="enemy",
        dx=3.0,
    )

    with pytest.raises(GameLifecycleError, match="attempted_placement unit drift"):
        replace(resolution, unit_instance_id="unit-b")
    with pytest.raises(GameLifecycleError, match="attempted_placement must be UnitPlacement"):
        replace(resolution, attempted_placement=cast(UnitPlacement, object()))
    with pytest.raises(GameLifecycleError, match="witness must be a PathWitness"):
        replace(resolution, witness=cast(PathWitness, object()))
    with pytest.raises(GameLifecycleError, match="endpoint_witness must be ChargeEndpointWitness"):
        replace(resolution, endpoint_witness=cast(ChargeEndpointWitness, object()))
    with pytest.raises(GameLifecycleError, match="path_validation_results must be a tuple"):
        replace(
            resolution,
            path_validation_results=cast(tuple[PathValidationResult, ...], []),
        )
    with pytest.raises(
        GameLifecycleError,
        match="path_validation_results must contain PathValidationResult",
    ):
        replace(
            resolution,
            path_validation_results=cast(tuple[PathValidationResult, ...], (object(),)),
        )
    with pytest.raises(
        GameLifecycleError,
        match="terrain_path_legality_results must be a tuple",
    ):
        replace(
            resolution,
            terrain_path_legality_results=cast(tuple[TerrainPathLegalityResult, ...], []),
        )
    with pytest.raises(
        GameLifecycleError,
        match="terrain_path_legality_results must contain TerrainPathLegalityResult",
    ):
        replace(
            resolution,
            terrain_path_legality_results=cast(
                tuple[TerrainPathLegalityResult, ...],
                (object(),),
            ),
        )
    with pytest.raises(GameLifecycleError, match="coherency_result must be UnitCoherencyResult"):
        replace(resolution, coherency_result=cast(UnitCoherencyResult, object()))
    with pytest.raises(GameLifecycleError, match="rollback_record must be MovementRollbackRecord"):
        replace(resolution, rollback_record=cast(MovementRollbackRecord, object()))
    with pytest.raises(GameLifecycleError, match="movement_payload must be a JSON object"):
        replace(resolution, movement_payload=cast(dict[str, JsonValue], []))


def test_phase15b_resolve_charge_move_rejects_malformed_inputs() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="phase15b-resolve-inputs",
    )
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    unit_placement = state.battlefield_state.unit_placement_by_id(
        units["intercessor-1"].unit_instance_id
    )
    witness = _charge_path_witness_for_unit(
        lifecycle,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        dx=3.0,
    )
    ruleset_descriptor = RulesetDescriptor.warhammer_40000_eleventh(
        descriptor_version="core-v2-phase15a-test"
    )
    selected_target_unit_instance_ids = (units["enemy"].unit_instance_id,)

    with pytest.raises(GameLifecycleError, match="requires a BattlefieldScenario"):
        resolve_charge_move(
            scenario=cast(BattlefieldScenario, object()),
            ruleset_descriptor=ruleset_descriptor,
            unit_placement=unit_placement,
            selected_target_unit_instance_ids=selected_target_unit_instance_ids,
            maximum_distance_inches=6,
            path_witness=witness,
        )
    with pytest.raises(GameLifecycleError, match="requires a RulesetDescriptor"):
        resolve_charge_move(
            scenario=scenario,
            ruleset_descriptor=cast(RulesetDescriptor, object()),
            unit_placement=unit_placement,
            selected_target_unit_instance_ids=selected_target_unit_instance_ids,
            maximum_distance_inches=6,
            path_witness=witness,
        )
    with pytest.raises(GameLifecycleError, match="unit_placement must be a UnitPlacement"):
        resolve_charge_move(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_placement=cast(UnitPlacement, object()),
            selected_target_unit_instance_ids=selected_target_unit_instance_ids,
            maximum_distance_inches=6,
            path_witness=witness,
        )
    with pytest.raises(GameLifecycleError, match="requires a PathWitness"):
        resolve_charge_move(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_placement=unit_placement,
            selected_target_unit_instance_ids=selected_target_unit_instance_ids,
            maximum_distance_inches=6,
            path_witness=cast(PathWitness, object()),
        )
    with pytest.raises(GameLifecycleError, match="maximum distance must be finite and nonnegative"):
        resolve_charge_move(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_placement=unit_placement,
            selected_target_unit_instance_ids=selected_target_unit_instance_ids,
            maximum_distance_inches=float("nan"),
            path_witness=witness,
        )
    with pytest.raises(GameLifecycleError, match="maximum distance must be finite and nonnegative"):
        resolve_charge_move(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_placement=unit_placement,
            selected_target_unit_instance_ids=selected_target_unit_instance_ids,
            maximum_distance_inches=-1,
            path_witness=witness,
        )
    with pytest.raises(
        GameLifecycleError, match="selected_target_unit_instance_ids must be a tuple"
    ):
        resolve_charge_move(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_placement=unit_placement,
            selected_target_unit_instance_ids=cast(
                tuple[str, ...],
                [units["enemy"].unit_instance_id],
            ),
            maximum_distance_inches=6,
            path_witness=witness,
        )
    with pytest.raises(GameLifecycleError, match="witness must match the selected unit models"):
        resolve_charge_move(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_placement=unit_placement,
            selected_target_unit_instance_ids=selected_target_unit_instance_ids,
            maximum_distance_inches=6,
            path_witness=PathWitness.for_paths(
                (("wrong-model", (Pose.at(1.0, 1.0), Pose.at(2.0, 1.0))),)
            ),
        )


def test_phase15b_malformed_charge_move_payload_rejects_before_queue_pop() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="phase15a-success-charge",
    )
    add_modifier(
        _state(lifecycle),
        effect_id="test:charge-fixture:test_phase15b_malformed_charge_move_payload_rejects_before_queue_pop",
        kind="modify_dice_roll",
        delta=20,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
    )
    proposal_request = _charge_move_request_after_selection(
        lifecycle,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        result_id="phase15b-select-success",
    )

    status = lifecycle.submit_decision(
        ParameterizedSubmission(
            request_id=proposal_request.request_id,
            result_id="phase15b-submit-malformed",
            payload={
                "proposal_request_id": proposal_request.request_id,
                "unit_instance_id": units["intercessor-1"].unit_instance_id,
                "movement_phase_action": "charge_move",
                "movement_mode": "charge",
                "charge_target_unit_instance_ids": [units["enemy"].unit_instance_id],
            },
        ).to_result(proposal_request)
    )
    assert _event_payloads(lifecycle, "charge_move_proposal_invalid") == ()
    invalid = cast(dict[str, object], status.payload)
    proposal_validation = cast(dict[str, object], invalid["proposal_validation"])
    violations = cast(list[dict[str, object]], proposal_validation["violations"])

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert lifecycle.decision_controller.queue.pending_requests == (proposal_request,)
    assert len(lifecycle.decision_controller.records) == 2
    assert violations[0]["violation_code"] == "proposal_payload_missing_field"
    assert violations[0]["field"] == "proposal_kind"


def test_charge_phase_completion_option_records_skipped_units_and_advances() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="phase15a-completion",
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())

    status = _submit_option(
        lifecycle,
        request=selection_request,
        option_id=COMPLETE_CHARGE_PHASE_OPTION_ID,
        result_id="phase15a-complete-charge",
    )
    completion_declared = _last_event_payload(lifecycle, "charge_phase_completion_declared")
    completed = _last_event_payload(lifecycle, "charge_phase_completed")
    state = _state(lifecycle)

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    assert status.decision_request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    assert state.current_battle_phase is BattlePhase.MOVEMENT
    assert state.charge_phase_state is None
    assert lifecycle.decision_controller.queue.pending_requests == (status.decision_request,)
    assert completion_declared["phase_body_status"] == "charge_phase_complete"
    assert completion_declared["skipped_unit_ids"] == [units["intercessor-1"].unit_instance_id]
    assert completed["phase_body_status"] == "charge_phase_complete"
    assert _event_payloads(lifecycle, "charge_roll_resolved") == ()


def test_stale_charging_unit_selection_after_advance_rejects_before_queue_pop() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="phase15a-stale-advanced",
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    state = _state(lifecycle)
    state.record_advanced_unit_state(_advanced_unit_state(units["intercessor-1"].unit_instance_id))

    status = _submit_option(
        lifecycle,
        request=selection_request,
        option_id=units["intercessor-1"].unit_instance_id,
        result_id="phase15a-stale-advanced-submit",
    )

    _assert_invalid_charge_submission_keeps_pending_clean(
        lifecycle,
        request=selection_request,
        status=status,
        expected_field="unit_instance_id",
    )


def test_stale_charging_unit_selection_after_target_drift_rejects_before_queue_pop() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="phase15a-stale-target",
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        _unit_placement_at(
            units["enemy"],
            army_id="army-beta",
            player_id="player-b",
            poses=_compact_test_unit_poses(
                origin=Pose.at(80.0, 80.0, facing_degrees=180.0),
                model_count=len(units["enemy"].own_models),
            ),
        )
    )

    status = _submit_option(
        lifecycle,
        request=selection_request,
        option_id=units["intercessor-1"].unit_instance_id,
        result_id="phase15a-stale-target-submit",
    )

    _assert_invalid_charge_submission_keeps_pending_clean(
        lifecycle,
        request=selection_request,
        status=status,
        expected_field="unit_instance_id",
    )


def test_selected_target_charge_constraint_blocks_alternate_legal_target() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_ids=("enemy-marked", "enemy-alternate"),
        enemy_model_poses=_compact_test_unit_poses(
            origin=Pose.at(30.0, 20.0),
            model_count=5,
        ),
        enemy_origins={
            "enemy-marked": Pose.at(30.0, 20.0),
            "enemy-alternate": Pose.at(20.0, 20.0),
        },
        game_id="phase15a-selected-target-blocks-alternate",
    )
    state = _state(lifecycle)
    source = units["intercessor-1"]
    marked = units["enemy-marked"]
    for effect_id, target in (
        ("phase15a-selected-target-blocks-alternate:marked", marked),
        ("phase15a-selected-target-blocks-alternate:legal", units["enemy-alternate"]),
    ):
        state.record_persisting_effect(
            selected_target_charge_persisting_effect(
                state=state,
                effect_id=effect_id,
                owner_player_id="player-a",
                source_rules_unit_instance_id=source.unit_instance_id,
                source_component_unit_instance_id=source.unit_instance_id,
                selected_target_unit_instance_id=target.unit_instance_id,
            )
        )

    lifecycle.advance_until_decision_or_terminal()

    assert state.current_battle_phase is not BattlePhase.CHARGE
    assert _event_payloads(lifecycle, "charging_unit_selected") == ()
    assert _event_payloads(lifecycle, "charge_roll_resolved") == ()


def test_selected_target_charge_constraint_rejects_stale_selection_after_target_moves() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_ids=("enemy-marked", "enemy-alternate"),
        enemy_model_poses=_compact_test_unit_poses(
            origin=Pose.at(20.0, 20.0),
            model_count=5,
        ),
        enemy_origins={
            "enemy-marked": Pose.at(20.0, 20.0),
            "enemy-alternate": Pose.at(22.0, 24.0),
        },
        game_id="phase15a-selected-target-stale-reactive-move",
    )
    state = _state(lifecycle)
    source = units["intercessor-1"]
    marked = units["enemy-marked"]
    state.record_persisting_effect(
        selected_target_charge_persisting_effect(
            state=state,
            effect_id="phase15a-selected-target-stale-reactive-move",
            owner_player_id="player-a",
            source_rules_unit_instance_id=source.unit_instance_id,
            source_component_unit_instance_id=source.unit_instance_id,
            selected_target_unit_instance_id=marked.unit_instance_id,
        )
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        _unit_placement_at(
            marked,
            army_id="army-beta",
            player_id="player-b",
            poses=_compact_test_unit_poses(
                origin=Pose.at(40.0, 20.0),
                model_count=len(marked.own_models),
            ),
        )
    )

    status = _submit_option(
        lifecycle,
        request=selection_request,
        option_id=source.unit_instance_id,
        result_id="phase15a-selected-target-stale-reactive-move-submit",
    )

    _assert_invalid_charge_submission_keeps_pending_clean(
        lifecycle,
        request=selection_request,
        status=status,
        expected_field="unit_instance_id",
    )


def test_selected_target_charge_roll_cannot_fall_back_to_reachable_alternate() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_ids=("enemy-marked", "enemy-alternate"),
        enemy_model_poses=_compact_test_unit_poses(
            origin=Pose.at(27.0, 20.0),
            model_count=5,
        ),
        enemy_origins={
            "enemy-marked": Pose.at(27.0, 20.0),
            "enemy-alternate": Pose.at(20.0, 24.0),
        },
        game_id="phase15a-selected-target-insufficient-roll",
    )
    state = _state(lifecycle)
    source = units["intercessor-1"]
    marked = units["enemy-marked"]
    state.record_persisting_effect(
        selected_target_charge_persisting_effect(
            state=state,
            effect_id="phase15a-selected-target-insufficient-roll",
            owner_player_id="player-a",
            source_rules_unit_instance_id=source.unit_instance_id,
            source_component_unit_instance_id=source.unit_instance_id,
            selected_target_unit_instance_id=marked.unit_instance_id,
        )
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    reroll_status = _submit_option(
        lifecycle,
        request=selection_request,
        option_id=source.unit_instance_id,
        result_id="phase15a-selected-target-insufficient-roll-select",
    )
    reroll_request = _decision_request(reroll_status)
    assert reroll_request.decision_type == DICE_REROLL_DECISION_TYPE

    status = _submit_option(
        lifecycle,
        request=reroll_request,
        option_id="decline",
        result_id="phase15a-selected-target-insufficient-roll-decline",
    )

    assert _roll_result_from_event(lifecycle, "charge_roll_resolved").move_available is False
    assert _event_payloads(lifecycle, "charge_move_required") == ()
    assert len(_event_payloads(lifecycle, "charge_no_move_possible")) == 1
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION


def test_selected_target_charge_reroll_rejects_target_drift_before_queue_pop() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_ids=("enemy-marked", "enemy-alternate"),
        enemy_model_poses=_compact_test_unit_poses(
            origin=Pose.at(20.0, 20.0),
            model_count=5,
        ),
        enemy_origins={
            "enemy-marked": Pose.at(20.0, 20.0),
            "enemy-alternate": Pose.at(22.0, 24.0),
        },
        game_id="phase15a-selected-target-stale-reroll",
    )
    state = _state(lifecycle)
    source = units["intercessor-1"]
    marked = units["enemy-marked"]
    state.record_persisting_effect(
        selected_target_charge_persisting_effect(
            state=state,
            effect_id="phase15a-selected-target-stale-reroll",
            owner_player_id="player-a",
            source_rules_unit_instance_id=source.unit_instance_id,
            source_component_unit_instance_id=source.unit_instance_id,
            selected_target_unit_instance_id=marked.unit_instance_id,
        )
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    reroll_request = _decision_request(
        _submit_option(
            lifecycle,
            request=selection_request,
            option_id=source.unit_instance_id,
            result_id="phase15a-selected-target-stale-reroll-select",
        )
    )
    assert reroll_request.decision_type == DICE_REROLL_DECISION_TYPE
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        _unit_placement_at(
            marked,
            army_id="army-beta",
            player_id="player-b",
            poses=_compact_test_unit_poses(
                origin=Pose.at(40.0, 20.0),
                model_count=len(marked.own_models),
            ),
        )
    )

    status = _submit_option(
        lifecycle,
        request=reroll_request,
        option_id="decline",
        result_id="phase15a-selected-target-stale-reroll-decline",
    )

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert cast(dict[str, object], status.payload)["field"] == ("legal_target_unit_instance_ids")
    assert lifecycle.decision_controller.queue.pending_requests == (reroll_request,)
    assert len(lifecycle.decision_controller.records) == 1


def test_charge_targets_use_canonical_attached_rules_unit_identity_after_round_trip() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_ids=("marked-bodyguard", "marked-leader"),
        enemy_model_poses=_compact_test_unit_poses(
            origin=Pose.at(10.0, 25.0),
            model_count=5,
        ),
        enemy_origins={
            "marked-bodyguard": Pose.at(10.0, 25.0),
            "marked-leader": Pose.at(17.0, 25.0),
        },
        enemy_attached_unit_ids=("marked-bodyguard", "marked-leader"),
        selected_attached_target_effect_id="phase15a-canonical-attached-charge-target",
        game_id="phase15a-canonical-attached-charge-target-order47",
    )
    source_id = units["intercessor-1"].unit_instance_id
    component_ids = {
        units["marked-bodyguard"].unit_instance_id,
        units["marked-leader"].unit_instance_id,
    }

    target_ids = legal_charge_target_unit_instance_ids(
        state=_state(lifecycle),
        unit_instance_id=source_id,
        ruleset_descriptor=_state(lifecycle).runtime_ruleset_descriptor(),
    )
    restored = GameLifecycle.from_payload(
        cast(
            GameLifecyclePayload,
            json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
        )
    )
    restored_target_ids = legal_charge_target_unit_instance_ids(
        state=_state(restored),
        unit_instance_id=source_id,
        ruleset_descriptor=_state(restored).runtime_ruleset_descriptor(),
    )

    assert target_ids == (_ATTACHED_CHARGE_TARGET_ID,)
    assert component_ids.isdisjoint(target_ids)
    assert restored_target_ids == target_ids

    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    reroll_request = _decision_request(
        _submit_option(
            lifecycle,
            request=selection_request,
            option_id=source_id,
            result_id="phase15a-canonical-attached-charge-target-selection",
        )
    )
    assert reroll_request.decision_type == DICE_REROLL_DECISION_TYPE
    request = _decision_request(
        _submit_option(
            lifecycle,
            request=reroll_request,
            option_id="decline",
            result_id="phase15a-canonical-attached-charge-target-reroll-decline",
        )
    )
    request = _decision_request(
        choose_charge_targets(
            lifecycle,
            request=request,
            target_ids=(_ATTACHED_CHARGE_TARGET_ID,),
            result_id="attached-charge-targets",
        )
    )
    assert request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    status = _submit_charge_move_proposal(
        lifecycle,
        request=request,
        result_id="phase15a-canonical-attached-charge-target-move",
        proposal=ChargeMoveProposal(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
            unit_instance_id=source_id,
            movement_phase_action="charge_move",
            movement_mode=MovementMode.CHARGE,
            charge_target_unit_instance_ids=(_ATTACHED_CHARGE_TARGET_ID,),
            witness=_charge_path_witness_for_unit(
                lifecycle,
                unit_instance_id=source_id,
                dx=0.0,
                dy=3.0,
            ),
        ),
    )
    completed = _last_event_payload(lifecycle, "charge_move_completed")
    endpoint_witness = cast(dict[str, object], completed["endpoint_witness"])

    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert endpoint_witness["selected_target_unit_instance_ids"] == [_ATTACHED_CHARGE_TARGET_ID]
    assert endpoint_witness["non_target_engaged_unit_instance_ids"] == []


def test_charge_targets_include_retained_units_and_measure_mixed_retained_geometry() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_ids=("retained-only", "mixed-target"),
        enemy_model_poses=_compact_test_unit_poses(
            origin=Pose.at(40.0, 20.0),
            model_count=5,
        ),
        enemy_origins={
            "retained-only": Pose.at(44.0, 20.0),
            "mixed-target": Pose.at(40.0, 30.0),
        },
        game_id="phase15a-retained-charge-target-authority",
    )
    state = _state(lifecycle)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    battlefield = state.battlefield_state
    assert battlefield is not None
    retained_only = units["retained-only"]
    mixed_target = units["mixed-target"]
    retained_placement = battlefield.unit_placement_by_id(retained_only.unit_instance_id)
    mixed_placement = battlefield.unit_placement_by_id(mixed_target.unit_instance_id)
    retained_model_placement = retained_placement.model_placements[0].with_pose(Pose.at(11.0, 20.0))
    mixed_model_placement = mixed_placement.model_placements[0].with_pose(Pose.at(20.0, 20.0))
    state.replace_battlefield_state(
        battlefield.with_unit_placement(
            retained_placement.with_model_placements(
                (retained_model_placement, *retained_placement.model_placements[1:])
            )
        ).with_unit_placement(
            mixed_placement.with_model_placements(
                (mixed_model_placement, *mixed_placement.model_placements[1:])
            )
        )
    )
    for model in retained_only.own_models:
        apply_damage_to_model(
            state=state,
            target_unit_instance_id=retained_only.unit_instance_id,
            model_instance_id=model.model_instance_id,
            damage=model.wounds_remaining,
            damage_kind=DamageKind.NORMAL,
        )
    retain_destroyed_model_for_fixture(
        decisions=lifecycle.decision_controller,
        state=state,
        placement=retained_model_placement,
        effect_id="phase15a:fight-on-death:retained-only-charge-target",
        source_rule_id="phase15a:test:fight-on-death",
        source_phase=BattlePhaseKind.FIGHT,
    )
    mixed_model = mixed_target.own_models[0]
    apply_damage_to_model(
        state=state,
        target_unit_instance_id=mixed_target.unit_instance_id,
        model_instance_id=mixed_model.model_instance_id,
        damage=mixed_model.wounds_remaining,
        damage_kind=DamageKind.NORMAL,
    )
    retain_destroyed_model_for_fixture(
        decisions=lifecycle.decision_controller,
        state=state,
        placement=mixed_model_placement,
        effect_id="phase15a:fight-on-death:mixed-charge-target",
        source_rule_id="phase15a:test:fight-on-death",
        source_phase=BattlePhaseKind.FIGHT,
    )

    target_ids = legal_charge_target_unit_instance_ids(
        state=state,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
    )

    assert _unit_is_engaged(
        state=state,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        player_id="player-a",
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
    )
    assert mixed_target.unit_instance_id in target_ids
    assert retained_only.unit_instance_id in target_ids


def test_repeated_selected_target_charge_effects_coalesce_one_reroll_and_require_all_targets() -> (
    None
):
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_ids=("enemy-1", "enemy-2"),
        enemy_model_poses=_compact_test_unit_poses(
            origin=Pose.at(10.0, 25.0),
            model_count=5,
        ),
        enemy_origins={
            "enemy-1": Pose.at(10.0, 25.0, facing_degrees=180.0),
            "enemy-2": Pose.at(17.0, 24.4, facing_degrees=180.0),
        },
        game_id="phase15a-success-charge",
    )
    state = _state(lifecycle)
    source = units["intercessor-1"]
    target_ids = tuple(
        sorted((units["enemy-1"].unit_instance_id, units["enemy-2"].unit_instance_id))
    )
    for index, target_id in enumerate(target_ids, start=1):
        state.record_persisting_effect(
            selected_target_charge_persisting_effect(
                state=state,
                effect_id=f"phase15a-selected-target-repeat:{index}",
                owner_player_id="player-a",
                source_rules_unit_instance_id=source.unit_instance_id,
                source_component_unit_instance_id=source.unit_instance_id,
                selected_target_unit_instance_id=target_id,
            )
        )
    constraint = selected_target_charge_constraint_for_unit(
        state=state,
        unit_instance_id=source.unit_instance_id,
    )
    assert constraint is not None
    assert constraint.required_target_unit_instance_ids == target_ids
    assert constraint.source_effect_ids == (
        "phase15a-selected-target-repeat:1",
        "phase15a-selected-target-repeat:2",
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    reroll_request = _decision_request(
        _submit_option(
            lifecycle,
            request=selection_request,
            option_id=source.unit_instance_id,
            result_id="phase15a-selected-target-repeat-select",
        )
    )
    charge_context = cast(dict[str, object], reroll_request.payload)["charge_context"]
    constraint_payload = cast(dict[str, object], charge_context)[
        "selected_target_charge_constraint"
    ]
    assert cast(dict[str, object], charge_context)[
        CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY
    ] == list(target_ids)
    assert cast(dict[str, object], constraint_payload)["source_effect_ids"] == list(
        constraint.source_effect_ids
    )
    lifecycle_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    assert GameLifecycle.from_payload(lifecycle_payload).to_payload() == lifecycle_payload
    proposal_request = _decision_request(
        _submit_option(
            lifecycle,
            request=reroll_request,
            option_id="decline",
            result_id="phase15a-selected-target-repeat-decline",
        )
    )
    proposal_request = _decision_request(
        choose_charge_targets(
            lifecycle,
            request=proposal_request,
            target_ids=target_ids,
            result_id="repeated-charge-targets",
        )
    )
    proposal = MovementProposalRequest.from_decision_request_payload(proposal_request.payload)
    assert cast(dict[str, object], proposal.context)[
        CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY
    ] == list(target_ids)

    status = _submit_charge_move_proposal(
        lifecycle,
        request=proposal_request,
        result_id="phase15a-selected-target-repeat-move",
        proposal=ChargeMoveProposal(
            proposal_request_id=proposal.request_id,
            proposal_kind=proposal.proposal_kind,
            unit_instance_id=proposal.unit_instance_id,
            movement_phase_action="charge_move",
            movement_mode=MovementMode.CHARGE,
            charge_target_unit_instance_ids=target_ids,
            witness=_charge_path_witness_for_unit(
                lifecycle,
                unit_instance_id=source.unit_instance_id,
                dx=0.0,
                dy=3.0,
            ),
        ),
    )
    completed = _last_event_payload(lifecycle, "charge_move_completed")
    endpoint_witness = cast(dict[str, object], completed["endpoint_witness"])

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert endpoint_witness["engaged_target_unit_instance_ids"] == list(target_ids)


def test_duplicate_selected_target_charge_effects_preserve_all_source_effect_ids() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="phase15a-selected-target-duplicate",
    )
    state = _state(lifecycle)
    source = units["intercessor-1"]
    target = units["enemy"]
    for suffix in ("first", "second"):
        state.record_persisting_effect(
            selected_target_charge_persisting_effect(
                state=state,
                effect_id=f"phase15a-selected-target-duplicate:{suffix}",
                owner_player_id="player-a",
                source_rules_unit_instance_id=source.unit_instance_id,
                source_component_unit_instance_id=source.unit_instance_id,
                selected_target_unit_instance_id=target.unit_instance_id,
            )
        )

    constraint = selected_target_charge_constraint_for_unit(
        state=state,
        unit_instance_id=source.unit_instance_id,
    )

    assert constraint is not None
    assert constraint.required_target_unit_instance_ids == (target.unit_instance_id,)
    assert constraint.source_effect_ids == (
        "phase15a-selected-target-duplicate:first",
        "phase15a-selected-target-duplicate:second",
    )


def test_destroyed_selected_target_remains_an_explicit_unavailable_charge_obligation() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_ids=("enemy-marked", "enemy-alternate"),
        enemy_model_poses=_compact_test_unit_poses(
            origin=Pose.at(20.0, 20.0),
            model_count=5,
        ),
        enemy_origins={
            "enemy-marked": Pose.at(20.0, 20.0),
            "enemy-alternate": Pose.at(22.0, 24.0),
        },
        game_id="phase15a-selected-target-destroyed",
    )
    state = _state(lifecycle)
    source = units["intercessor-1"]
    marked = units["enemy-marked"]
    state.record_persisting_effect(
        selected_target_charge_persisting_effect(
            state=state,
            effect_id="phase15a-selected-target-destroyed",
            owner_player_id="player-a",
            source_rules_unit_instance_id=source.unit_instance_id,
            source_component_unit_instance_id=source.unit_instance_id,
            selected_target_unit_instance_id=marked.unit_instance_id,
        )
    )
    _destroy_unit_models_for_test(state, unit_instance_id=marked.unit_instance_id)

    constraint = selected_target_charge_constraint_for_unit(
        state=state,
        unit_instance_id=source.unit_instance_id,
    )

    assert constraint is not None
    assert constraint.required_target_unit_instance_ids == ()
    assert constraint.unavailable_target_identity_ids == (marked.unit_instance_id,)
    assert constraint.destroyed_target_identity_ids == (marked.unit_instance_id,)
    assert not constraint.is_satisfied_by((units["enemy-alternate"].unit_instance_id,))


def test_stale_charge_phase_completion_rejects_skipped_unit_drift_before_queue_pop() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="phase15a-stale-complete",
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    state = _state(lifecycle)
    state.record_advanced_unit_state(_advanced_unit_state(units["intercessor-1"].unit_instance_id))

    status = _submit_option(
        lifecycle,
        request=selection_request,
        option_id=COMPLETE_CHARGE_PHASE_OPTION_ID,
        result_id="phase15a-stale-complete-submit",
    )

    _assert_invalid_charge_submission_keeps_pending_clean(
        lifecycle,
        request=selection_request,
        status=status,
        expected_field="skipped_unit_ids",
    )
    assert _event_payloads(lifecycle, "charge_phase_completion_declared") == ()


def test_charge_phase_filters_ineligible_units() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=(
            "intercessor-1",
            "intercessor-2",
            "intercessor-3",
            "intercessor-4",
            "intercessor-5",
        ),
        alpha_origins={
            "intercessor-1": Pose.at(10.0, 10.0),
            "intercessor-2": Pose.at(10.0, 25.0),
            "intercessor-3": Pose.at(10.0, 40.0),
            "intercessor-4": Pose.at(10.0, 55.0),
            "intercessor-5": Pose.at(10.0, 70.0),
        },
        enemy_model_poses=(
            Pose.at(20.0, 10.0, facing_degrees=180.0),
            Pose.at(21.4, 10.0, facing_degrees=180.0),
            Pose.at(22.8, 10.0, facing_degrees=180.0),
            Pose.at(24.2, 10.0, facing_degrees=180.0),
            Pose.at(25.6, 10.0, facing_degrees=180.0),
        ),
        enemy_unit_ids=("enemy-1", "enemy-2", "enemy-3", "enemy-4", "enemy-5"),
        enemy_origins={
            "enemy-1": Pose.at(20.0, 10.0, facing_degrees=180.0),
            "enemy-2": Pose.at(20.0, 25.0, facing_degrees=180.0),
            "enemy-3": Pose.at(11.0, 40.0, facing_degrees=180.0),
            "enemy-4": Pose.at(20.0, 55.0, facing_degrees=180.0),
            "enemy-5": Pose.at(20.0, 70.0, facing_degrees=180.0),
        },
        game_id="phase15a-eligibility",
    )
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    state.record_advanced_unit_state(_advanced_unit_state(units["intercessor-1"].unit_instance_id))
    state.record_fell_back_unit_state(
        FellBackUnitState(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=units["intercessor-2"].unit_instance_id,
        )
    )
    state.battlefield_state = state.battlefield_state.without_unit_placement(
        units["intercessor-4"].unit_instance_id
    )
    state.record_reserve_state(
        ReserveState.declared_before_battle(
            player_id="player-a",
            unit_instance_id=units["intercessor-4"].unit_instance_id,
            reserve_kind=ReserveKind.RESERVES,
        )
    )

    request = _decision_request(lifecycle.advance_until_decision_or_terminal())

    assert request.decision_type == SELECT_CHARGING_UNIT_DECISION_TYPE
    assert {option.option_id for option in request.options} == {
        units["intercessor-5"].unit_instance_id,
        COMPLETE_CHARGE_PHASE_OPTION_ID,
    }


def test_charge_phase_consumes_disembark_charge_eligibility_state() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("rapid-passenger", "assault-passenger"),
        alpha_origins={
            "rapid-passenger": Pose.at(10.0, 20.0),
            "assault-passenger": Pose.at(10.0, 25.0),
        },
        enemy_model_poses=_compact_test_unit_poses(
            origin=Pose.at(20.0, 22.5),
            model_count=5,
        ),
        game_id="phase18d-disembark-charge-eligibility",
    )
    state = _state(lifecycle)
    rapid_id = units["rapid-passenger"].unit_instance_id
    assault_id = units["assault-passenger"].unit_instance_id
    state.record_disembarked_unit_state(
        DisembarkedUnitState.for_mode(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=rapid_id,
            transport_unit_instance_id=assault_id,
            disembark_mode=DisembarkModeKind.RAPID_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NORMAL_MOVE,
        )
    )
    state.record_disembarked_unit_state(
        DisembarkedUnitState.for_mode(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=assault_id,
            transport_unit_instance_id=rapid_id,
            disembark_mode=DisembarkModeKind.ASSAULT_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NORMAL_MOVE,
            restriction_overrides=(
                TransportRestrictionOverride(
                    override_kind=(TransportRestrictionOverrideKind.ALLOW_ASSAULT_DISEMBARK),
                    source_rule_id="test:assault-disembark-permitting-rule",
                ),
            ),
        )
    )

    request = _decision_request(lifecycle.advance_until_decision_or_terminal())

    assert request.decision_type == SELECT_CHARGING_UNIT_DECISION_TYPE
    assert {option.option_id for option in request.options} == {
        assault_id,
        COMPLETE_CHARGE_PHASE_OPTION_ID,
    }


@pytest.mark.parametrize("action_status", ["started", "completed", "interrupted"])
def test_unit_that_started_action_this_turn_cannot_declare_charge(action_status: str) -> None:
    from warhammer40k_core.engine.event_log import validate_json_value

    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1", "intercessor-2"),
        alpha_origins={
            "intercessor-1": Pose.at(10.0, 20.0),
            "intercessor-2": Pose.at(10.0, 25.0),
        },
        enemy_model_poses=_compact_test_unit_poses(
            origin=Pose.at(20.0, 22.5),
            model_count=5,
        ),
        game_id=f"phase15a-action-{action_status}",
    )
    state = _state(lifecycle)
    unit_id = units["intercessor-1"].unit_instance_id
    action_state = MissionActionState.start(
        action_id=f"phase15a-action-{action_status}",
        mission_action_id="phase15a-action",
        player_id="player-a",
        unit_instance_id=unit_id,
        target_id="phase15a-action-target",
        condition_target_id="phase15a-action-target",
        mission_id="phase15a-action-mission",
        battle_round=state.battle_round,
        phase=BattlePhase.SHOOTING.value,
        start_timing="shooting_phase",
        completion_timing="immediate",
        eligible_unit_instance_ids=(unit_id,),
        interruption_conditions=("unit_moved",),
        scoring_source_id="phase15a-action-source",
        victory_points=0,
    )
    if action_status == "completed":
        action_state = action_state.complete_without_award(
            battle_round=state.battle_round,
            phase=BattlePhase.SHOOTING.value,
            completion_timing="immediate",
        )
    elif action_status == "interrupted":
        action_state = action_state.interrupt(reason="unit_moved")
    state.record_mission_action_state(action_state)
    if action_status == "started":
        lifecycle.decision_controller.event_log.append(
            "mission_action_started",
            {
                "game_id": state.game_id,
                "mission_action_state": validate_json_value(action_state.to_payload()),
            },
        )

    request = _decision_request(lifecycle.advance_until_decision_or_terminal())

    assert request.decision_type == SELECT_CHARGING_UNIT_DECISION_TYPE
    assert {option.option_id for option in request.options} == {
        units["intercessor-2"].unit_instance_id,
        COMPLETE_CHARGE_PHASE_OPTION_ID,
    }


def test_charge_roll_without_cp_has_no_command_reroll_request() -> None:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="phase15a-no-command-reroll",
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())

    _submit_option(
        lifecycle,
        request=selection_request,
        option_id=units["intercessor-1"].unit_instance_id,
        result_id="phase15a-no-reroll-submit",
    )
    roll_result = _roll_result_from_event(lifecycle, "charge_roll_resolved")
    requested_decision_types = {
        cast(dict[str, object], event.payload)["decision_type"]
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "decision_requested"
    }

    assert roll_result.request.spec.reroll_forbidden_rule_ids == ()
    assert DICE_REROLL_DECISION_TYPE not in requested_decision_types
    assert {
        request.decision_type for request in lifecycle.decision_controller.queue.pending_requests
    } != {DICE_REROLL_DECISION_TYPE}


def test_charge_roll_and_phase_state_value_objects_reject_drift() -> None:
    request = _charge_roll_request(player_id="player-a", unit_instance_id="unit-a")
    roll_state = DiceRollManager("phase15a-value-objects").roll_fixed(request.spec, [3, 4])
    roll_result = ChargeRollResult.from_roll_state(
        request=request,
        roll_state=roll_state,
        reachable_target_distances_inches={"target-a": 3.0},
    )
    assert roll_result.move_available is True

    with pytest.raises(GameLifecycleError, match="is_legal must be a bool"):
        ChargeTargetCandidate(
            target_unit_instance_id="target-x",
            closest_distance_inches=3.0,
            is_legal=cast(bool, "true"),
        )
    with pytest.raises(GameLifecycleError, match="must not carry violation_code"):
        ChargeTargetCandidate(
            target_unit_instance_id="target-x",
            closest_distance_inches=3.0,
            is_legal=True,
            violation_code="target_out_of_declaration_range",
        )
    with pytest.raises(GameLifecycleError, match="requires violation_code"):
        ChargeTargetCandidate(
            target_unit_instance_id="target-x",
            closest_distance_inches=13.0,
            is_legal=False,
        )
    with pytest.raises(GameLifecycleError, match="payload missing target_unit_instance_id"):
        ChargeTargetCandidate.from_payload(cast(ChargeTargetCandidatePayload, {}))

    request_payload = request.to_payload()
    spec_payload = cast(dict[str, object], request_payload["spec"])
    spec_payload["roll_type"] = "wrong-roll-type"
    with pytest.raises(GameLifecycleError, match="spec payload drift"):
        ChargeRollRequest.from_payload(request_payload)
    with pytest.raises(GameLifecycleError, match="value must match"):
        replace(roll_result, value=8)
    with pytest.raises(GameLifecycleError, match="exceeds roll"):
        replace(roll_result, reachable_target_distances_inches={"target-a": 8.0})
    with pytest.raises(GameLifecycleError, match="move_available flag drift"):
        replace(roll_result, move_available=False)
    with pytest.raises(GameLifecycleError, match="status drift"):
        replace(roll_result, status=CHARGE_NO_MOVE_POSSIBLE_STATUS)
    with pytest.raises(GameLifecycleError, match="source request drift"):
        ChargeDistanceState(
            roll_result=roll_result,
            source_decision_request_id="source-request-b",
            source_decision_result_id=request.source_decision_result_id,
        )
    with pytest.raises(GameLifecycleError, match="source result drift"):
        ChargeDistanceState(
            roll_result=roll_result,
            source_decision_request_id=request.source_decision_request_id,
            source_decision_result_id="source-result-b",
        )

    selection = ChargingUnitSelection(
        player_id="player-a",
        battle_round=1,
        unit_instance_id="unit-a",
        request_id="select-request",
        result_id="select-result",
    )
    phase_state = ChargePhaseState(
        battle_round=1,
        active_player_id="player-a",
    )
    selected_state = phase_state.with_unit_selection(selection)
    pending_state = selected_state.with_charge_roll_result(roll_result)

    assert pending_state.move_pending_distance_state() is not None
    with pytest.raises(GameLifecycleError, match="phase_complete must be a bool"):
        ChargePhaseState(
            battle_round=1,
            active_player_id="player-a",
            phase_complete=cast(bool, "false"),
        )
    with pytest.raises(GameLifecycleError, match="active_selection must be ChargingUnitSelection"):
        ChargePhaseState(
            battle_round=1,
            active_player_id="player-a",
            selected_unit_ids=("unit-a",),
            active_selection=cast(ChargingUnitSelection, object()),
        )
    with pytest.raises(GameLifecycleError, match="active player drift"):
        ChargePhaseState(
            battle_round=1,
            active_player_id="player-a",
            selected_unit_ids=("unit-a",),
            active_selection=replace(selection, player_id="player-b"),
        )
    with pytest.raises(GameLifecycleError, match="battle round drift"):
        ChargePhaseState(
            battle_round=1,
            active_player_id="player-a",
            selected_unit_ids=("unit-a",),
            active_selection=replace(selection, battle_round=2),
        )
    with pytest.raises(GameLifecycleError, match="active_selection must be selected"):
        ChargePhaseState(
            battle_round=1,
            active_player_id="player-a",
            selected_unit_ids=("unit-b",),
            active_selection=selection,
        )
    with pytest.raises(GameLifecycleError, match="selection must be ChargingUnitSelection"):
        phase_state.with_unit_selection(cast(ChargingUnitSelection, object()))
    with pytest.raises(GameLifecycleError, match="Cannot select"):
        ChargePhaseState(
            battle_round=1,
            active_player_id="player-a",
            phase_complete=True,
        ).with_unit_selection(selection)
    with pytest.raises(GameLifecycleError, match="requires no active selection"):
        selected_state.with_unit_selection(replace(selection, unit_instance_id="unit-b"))
    with pytest.raises(GameLifecycleError, match="selection player drift"):
        phase_state.with_unit_selection(replace(selection, player_id="player-b"))
    with pytest.raises(GameLifecycleError, match="selection battle round drift"):
        phase_state.with_unit_selection(replace(selection, battle_round=2))
    with pytest.raises(GameLifecycleError, match="already selected"):
        replace(phase_state, selected_unit_ids=("unit-a",)).with_unit_selection(selection)
    with pytest.raises(GameLifecycleError, match="roll result must be ChargeRollResult"):
        selected_state.with_charge_roll_result(cast(ChargeRollResult, object()))
    with pytest.raises(GameLifecycleError, match="after phase completion"):
        replace(selected_state, phase_complete=True, active_selection=None).with_charge_roll_result(
            roll_result
        )
    with pytest.raises(GameLifecycleError, match="requires active_selection"):
        phase_state.with_charge_roll_result(roll_result)
    with pytest.raises(GameLifecycleError, match="roll player drift"):
        selected_state.with_charge_roll_result(
            _charge_roll_result(player_id="player-b", unit_instance_id="unit-a")
        )
    with pytest.raises(GameLifecycleError, match="roll battle round drift"):
        selected_state.with_charge_roll_result(
            replace(roll_result, request=replace(roll_result.request, battle_round=2))
        )
    with pytest.raises(GameLifecycleError, match="roll unit drift"):
        selected_state.with_charge_roll_result(
            _charge_roll_result(player_id="player-a", unit_instance_id="unit-b")
        )
    with pytest.raises(GameLifecycleError, match="after phase completion"):
        ChargePhaseState(
            battle_round=1,
            active_player_id="player-a",
            phase_complete=True,
        ).with_charge_move_resolved("unit-a")
    with pytest.raises(GameLifecycleError, match="requires active_selection"):
        phase_state.with_charge_move_resolved("unit-a")
    with pytest.raises(GameLifecycleError, match="resolution unit drift"):
        pending_state.with_charge_move_resolved("unit-b")
    with pytest.raises(GameLifecycleError, match="requires pending distance state"):
        selected_state.with_charge_move_resolved("unit-a")
    with pytest.raises(GameLifecycleError, match="completion requires no active selection"):
        selected_state.with_phase_complete()
    with pytest.raises(GameLifecycleError, match="cannot have active_selection"):
        replace(pending_state, phase_complete=True)


def test_charge_roll_value_objects_reject_malformed_scalars_and_mappings() -> None:
    request = _charge_roll_request(player_id="player-a", unit_instance_id="unit-a")
    roll_state = DiceRollManager("phase15a-malformed-value-objects").roll_fixed(
        request.spec,
        [2, 3],
    )
    roll_result = ChargeRollResult.from_roll_state(
        request=request,
        roll_state=roll_state,
        reachable_target_distances_inches={"target-a": 3.0},
    )

    with pytest.raises(GameLifecycleError, match="payload missing candidate"):
        ChargeTargetCandidate.from_payload(cast(ChargeTargetCandidatePayload, "bad-candidate"))
    with pytest.raises(GameLifecycleError, match="request_id must be a string"):
        replace(request, request_id=cast(str, 1))
    with pytest.raises(GameLifecycleError, match="battle_round must be greater than zero"):
        replace(request, battle_round=0)
    with pytest.raises(GameLifecycleError, match="reachable target distances must be a dict"):
        replace(roll_result, reachable_target_distances_inches=cast(dict[str, float], []))
    with pytest.raises(GameLifecycleError, match="reachable target key must be a string"):
        replace(
            roll_result,
            reachable_target_distances_inches={cast(str, 1): 3.0},
        )
    with pytest.raises(GameLifecycleError, match="must be finite"):
        replace(roll_result, reachable_target_distances_inches={"target-a": float("inf")})
    with pytest.raises(GameLifecycleError, match="must not be negative"):
        replace(roll_result, reachable_target_distances_inches={"target-a": -1.0})
    with pytest.raises(GameLifecycleError, match="move_available must be a bool"):
        replace(roll_result, move_available=cast(bool, "true"))
