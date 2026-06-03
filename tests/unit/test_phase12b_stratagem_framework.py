from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, cast

import pytest

from warhammer40k_core.adapters.projection import project_game_view
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.command_points import (
    CommandPointGainStatus,
    CommandPointLedger,
    CommandPointRefundResult,
    CommandPointRefundStatus,
    CommandPointSourceKind,
    CommandPointSpendResult,
    CommandPointSpendStatus,
    command_point_refund_status_from_token,
    command_point_spend_status_from_token,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionOption,
    DecisionRequest,
    parameterized_decision_option,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameConfig, GameState, GameStatePayload
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.stratagem_catalog import (
    build_player_stratagem_index,
    eleventh_edition_core_stratagem_catalog_records,
    eleventh_edition_core_stratagem_index,
    eleventh_edition_detachment_stratagem_catalog_records,
    eleventh_edition_stratagem_catalog_records,
    eleventh_edition_stratagem_index,
)
from warhammer40k_core.engine.stratagems import (
    STRATAGEM_DECISION_TYPE,
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    StratagemAvailabilityKind,
    StratagemCatalogIndex,
    StratagemCatalogRecord,
    StratagemCategory,
    StratagemDefinition,
    StratagemEligibilityContext,
    StratagemRestrictionPolicy,
    StratagemTargetBinding,
    StratagemTargetKind,
    StratagemTargetProposal,
    StratagemTargetProposalPayload,
    StratagemTargetSpec,
    StratagemTimingDescriptor,
    StratagemUseRecord,
    StratagemUseRequest,
    create_stratagem_use_decision_request,
    invalid_stratagem_use_status,
    request_stratagem_target_proposal,
    request_stratagem_use,
    request_stratagem_use_from_index,
    stratagem_use_options,
    stratagem_use_options_for_handler_from_index,
    stratagem_use_options_from_index,
)
from warhammer40k_core.engine.timing_windows import (
    ReactionWindow,
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)
from warhammer40k_core.engine.unit_state import StartingStrengthRecord
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2025_26_mission_pack
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_stratagems as source_stratagems,
)


def test_finite_stratagem_use_round_trips_through_lifecycle_and_spends_cp() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    _grant_cp(state, player_id="player-a", amount=1)
    context = _context(state=state, player_id="player-a")
    catalog = (_core_stratagem(stratagem_id="command-reroll", command_point_cost=1),)

    waiting = request_stratagem_use(
        state=state,
        decisions=lifecycle.decision_controller,
        catalog_records=catalog,
        context=context,
    )
    request = _decision_request(waiting)
    result = DecisionResult.for_request(
        result_id="phase12b-use-result",
        request=request,
        selected_option_id=request.options[0].option_id,
    )

    lifecycle.submit_decision(result)

    assert state.command_point_total("player-a") == 0
    assert len(state.stratagem_use_records) == 1
    use_record = state.stratagem_use_records[0]
    assert use_record.stratagem_id == "command-reroll"
    assert use_record.command_point_cost == 1
    assert use_record.command_point_transaction_id is not None
    assert _last_event_payload(lifecycle.decision_controller, "stratagem_used") == (
        use_record.to_payload()
    )
    assert "<" not in json.dumps(lifecycle.to_payload(), sort_keys=True)
    assert GameLifecycle.from_payload(_lifecycle_payload_copy(lifecycle)).to_payload() == (
        lifecycle.to_payload()
    )


def test_source_backed_core_stratagem_catalog_snapshot_and_availability() -> None:
    source_identity = source_stratagems.source_package_identity_payload()
    source_catalog = eleventh_edition_stratagem_catalog_records()
    core_catalog = eleventh_edition_core_stratagem_catalog_records()
    detachment_catalog = eleventh_edition_detachment_stratagem_catalog_records()
    snapshot = tuple(
        (
            record.record_id,
            record.definition.stratagem_id,
            record.definition.command_point_cost,
            record.definition.category.value,
            record.definition.source_id,
            record.definition.target_spec.target_policy_id,
            record.definition.handler_id,
            record.availability_kind.value,
            record.detachment_id,
        )
        for record in source_catalog
    )
    assert source_identity["edition_id"] == "warhammer_40000_11th"
    assert source_identity["source_package_id"] == "gw-11e-core-stratagems"
    assert snapshot == (
        (
            "gw-11e-core-stratagems:core:command-reroll",
            "command-reroll",
            1,
            "battle_tactic",
            "gw-11e-core-stratagems:core:command-reroll",
            "none",
            "core:command-reroll",
            "core",
            None,
        ),
        (
            "gw-11e-core-stratagems:core:counteroffensive",
            "counteroffensive",
            2,
            "strategic_ploy",
            "gw-11e-core-stratagems:core:counteroffensive",
            "unsupported:phase-14g:fight-order-interrupt-unit",
            "unsupported:phase-14g:counteroffensive",
            "core",
            None,
        ),
        (
            "gw-11e-core-stratagems:core:crushing-impact",
            "crushing-impact",
            1,
            "strategic_ploy",
            "gw-11e-core-stratagems:core:crushing-impact",
            "unsupported:phase-14g:vehicle-charge-target-binding",
            "unsupported:phase-14g:crushing-impact",
            "core",
            None,
        ),
        (
            "gw-11e-core-stratagems:core:epic-challenge",
            "epic-challenge",
            1,
            "epic_deed",
            "gw-11e-core-stratagems:core:epic-challenge",
            "unsupported:phase-14g:character-model-fight-binding",
            "unsupported:phase-14g:epic-challenge",
            "core",
            None,
        ),
        (
            "gw-11e-core-stratagems:core:explosives",
            "explosives",
            1,
            "wargear",
            "gw-11e-core-stratagems:core:explosives",
            "explosives_unit_and_enemy_target",
            "core:explosives",
            "core",
            None,
        ),
        (
            "gw-11e-core-stratagems:core:fire-overwatch",
            "fire-overwatch",
            1,
            "strategic_ploy",
            "gw-11e-core-stratagems:core:fire-overwatch",
            "out_of_phase_shooting_unit",
            "core:fire-overwatch",
            "core",
            None,
        ),
        (
            "gw-11e-core-stratagems:core:heroic-intervention",
            "heroic-intervention",
            1,
            "strategic_ploy",
            "gw-11e-core-stratagems:core:heroic-intervention",
            "unsupported:phase-14g:heroic-intervention-charge-unit",
            "unsupported:phase-14g:heroic-intervention",
            "core",
            None,
        ),
        (
            "gw-11e-core-stratagems:core:insane-bravery",
            "insane-bravery",
            1,
            "epic_deed",
            "gw-11e-core-stratagems:core:insane-bravery",
            "battle_shock_test_unit",
            "core:insane-bravery",
            "core",
            None,
        ),
        (
            "gw-11e-core-stratagems:core:new-orders",
            "new-orders",
            1,
            "strategic_ploy",
            "gw-11e-core-stratagems:core:new-orders",
            "active_tactical_secondary_card",
            "core:new-orders",
            "core",
            None,
        ),
        (
            "gw-11e-core-stratagems:core:rapid-ingress",
            "rapid-ingress",
            1,
            "strategic_ploy",
            "gw-11e-core-stratagems:core:rapid-ingress",
            "reserves_unit",
            "core:rapid-ingress",
            "core",
            None,
        ),
        (
            "gw-11e-core-stratagems:core:smokescreen",
            "smokescreen",
            1,
            "wargear",
            "gw-11e-core-stratagems:core:smokescreen",
            "selected_target_smoke_unit",
            "core:smokescreen",
            "core",
            None,
        ),
        (
            "gw-11e-core-stratagems:detachment:armour-of-contempt",
            "armour-of-contempt",
            1,
            "battle_tactic",
            "gw-11e-core-stratagems:detachment:gladius-task-force:armour-of-contempt",
            "unsupported:phase-13:selected-target-unit",
            "unsupported:phase-13:armour-of-contempt",
            "detachment",
            "gladius-task-force",
        ),
    )
    assert len(core_catalog) == 11
    assert len(detachment_catalog) == 1

    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    _grant_cp(state, player_id="player-a", amount=1)
    context = _context(
        state=state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
    )
    unavailable = request_stratagem_use(
        state=state,
        decisions=lifecycle.decision_controller,
        catalog_records=source_catalog,
        context=context,
    )

    assert unavailable.status_kind is LifecycleStatusKind.UNSUPPORTED
    assert unavailable.decision_request is None
    assert state.command_point_total("player-a") == 1
    assert state.stratagem_use_records == []
    _assert_no_pending(lifecycle)


def test_source_backed_stratagem_index_matches_tuple_options_for_trigger_windows() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _grant_cp(state, player_id="player-a", amount=10)
    catalog = eleventh_edition_stratagem_catalog_records()
    index = eleventh_edition_stratagem_index()
    phase_by_trigger = {
        TimingTriggerKind.START_PHASE: BattlePhase.COMMAND,
        TimingTriggerKind.END_PHASE: BattlePhase.MOVEMENT,
        TimingTriggerKind.AFTER_UNIT_SELECTED_AS_TARGET: BattlePhase.SHOOTING,
        TimingTriggerKind.AFTER_ENEMY_UNIT_ENDS_MOVE: BattlePhase.MOVEMENT,
        TimingTriggerKind.AFTER_UNIT_ENDS_CHARGE_MOVE: BattlePhase.CHARGE,
        TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_HAS_FOUGHT: BattlePhase.FIGHT,
    }

    assert index.all_records() == tuple(sorted(catalog, key=lambda record: record.record_id))
    for trigger_kind in TimingTriggerKind:
        _set_current_battle_phase(
            state,
            phase_by_trigger.get(trigger_kind, BattlePhase.MOVEMENT),
        )
        context = _context(state=state, player_id="player-a", trigger_kind=trigger_kind)

        assert stratagem_use_options_from_index(state=state, index=index, context=context) == (
            stratagem_use_options(state=state, catalog_records=catalog, context=context)
        )


def test_stratagem_catalog_index_partitions_by_trigger_and_rejects_invalid_inputs() -> None:
    start_alpha = _core_stratagem(stratagem_id="start-alpha", command_point_cost=0)
    start_zulu = _core_stratagem(stratagem_id="start-zulu", command_point_cost=0)
    after_dice = _core_stratagem(
        stratagem_id="after-dice",
        command_point_cost=0,
        timing=StratagemTimingDescriptor(trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL),
    )
    catalog = (start_zulu, after_dice, start_alpha)
    index = StratagemCatalogIndex.from_records(catalog)

    assert index == StratagemCatalogIndex.from_records(catalog)
    assert index.all_records() == tuple(sorted(catalog, key=lambda record: record.record_id))
    assert index.records_for(TimingTriggerKind.START_PHASE) == (start_alpha, start_zulu)
    assert index.records_for(TimingTriggerKind.AFTER_DICE_ROLL) == (after_dice,)
    assert index.records_for(TimingTriggerKind.END_TURN) == ()
    state = _battle_state()
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    context = _context(state=state, player_id="player-a")
    handler_options = stratagem_use_options_for_handler_from_index(
        state=state,
        index=index,
        context=context,
        handler_id="record_only",
    )
    assert tuple(option.option_id for option in handler_options) == (
        "use-stratagem:start-alpha:target:none",
        "use-stratagem:start-zulu:target:none",
    )
    assert (
        stratagem_use_options_for_handler_from_index(
            state=state,
            index=index,
            context=context,
            handler_id="missing-handler",
        )
        == ()
    )
    assert eleventh_edition_core_stratagem_index().all_records() == tuple(
        sorted(
            eleventh_edition_core_stratagem_catalog_records(),
            key=lambda record: record.record_id,
        )
    )

    with pytest.raises(GameLifecycleError, match="duplicate IDs"):
        StratagemCatalogIndex.from_records((start_alpha, start_alpha))
    with pytest.raises(GameLifecycleError, match="StratagemCatalogRecord values"):
        StratagemCatalogIndex.from_records(cast(tuple[StratagemCatalogRecord, ...], (object(),)))
    with pytest.raises(GameLifecycleError, match="requires a TimingTriggerKind"):
        index.records_for(cast(TimingTriggerKind, "start_phase"))
    with pytest.raises(GameLifecycleError, match="require a StratagemCatalogIndex"):
        stratagem_use_options_from_index(
            state=_battle_state(),
            index=cast(StratagemCatalogIndex, object()),
            context=_context(state=_battle_state(), player_id="player-a"),
        )
    with pytest.raises(GameLifecycleError, match="require a StratagemCatalogIndex"):
        stratagem_use_options_for_handler_from_index(
            state=state,
            index=cast(StratagemCatalogIndex, object()),
            context=context,
            handler_id="record_only",
        )
    with pytest.raises(GameLifecycleError, match="require an eligibility context"):
        stratagem_use_options_for_handler_from_index(
            state=state,
            index=index,
            context=cast(StratagemEligibilityContext, object()),
            handler_id="record_only",
        )


def test_stratagem_catalog_index_preserves_any_phase_exact_match_semantics() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    catalog = (
        _core_stratagem(stratagem_id="movement-start", command_point_cost=0),
        _core_stratagem(
            stratagem_id="any-phase",
            command_point_cost=0,
            timing=StratagemTimingDescriptor(trigger_kind=TimingTriggerKind.ANY_PHASE),
        ),
    )
    index = StratagemCatalogIndex.from_records((catalog[1], catalog[0]))

    start_context = _context(state=state, player_id="player-a")
    any_phase_context = _context(
        state=state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.ANY_PHASE,
    )

    assert tuple(
        option.option_id
        for option in stratagem_use_options_from_index(
            state=state,
            index=index,
            context=start_context,
        )
    ) == ("use-stratagem:movement-start:target:none",)
    assert stratagem_use_options_from_index(state=state, index=index, context=start_context) == (
        stratagem_use_options(state=state, catalog_records=catalog, context=start_context)
    )
    assert tuple(
        option.option_id
        for option in stratagem_use_options_from_index(
            state=state,
            index=index,
            context=any_phase_context,
        )
    ) == ("use-stratagem:any-phase:target:none",)
    assert stratagem_use_options_from_index(
        state=state,
        index=index,
        context=any_phase_context,
    ) == stratagem_use_options(state=state, catalog_records=catalog, context=any_phase_context)


def test_stratagem_request_from_index_has_empty_bucket_parity_with_tuple_scan() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    record = _core_stratagem(stratagem_id="movement-start", command_point_cost=0)
    index = StratagemCatalogIndex.from_records((record,))
    context = _context(state=state, player_id="player-a", trigger_kind=TimingTriggerKind.END_TURN)

    tuple_status = request_stratagem_use(
        state=state,
        decisions=DecisionController(),
        catalog_records=(record,),
        context=context,
    )
    index_status = request_stratagem_use_from_index(
        state=state,
        decisions=DecisionController(),
        index=index,
        context=context,
    )

    assert index_status.status_kind is LifecycleStatusKind.UNSUPPORTED
    assert index_status.message == tuple_status.message
    assert index_status.payload == tuple_status.payload


def test_player_stratagem_index_filters_detachments_without_changing_options() -> None:
    state = _battle_state()
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    _grant_cp(state, player_id="player-a", amount=3)
    alpha = state.army_definitions[0]
    state.army_definitions[0] = replace(
        alpha,
        detachment_selection=DetachmentSelection(
            faction_id=alpha.detachment_selection.faction_id,
            detachment_id=alpha.detachment_selection.detachment_id,
            stratagem_ids=("detachment-ambush",),
        ),
    )
    catalog = (
        _core_stratagem(stratagem_id="command-reroll", command_point_cost=1),
        _detachment_stratagem(
            stratagem_id="detachment-ambush",
            command_point_cost=1,
            detachment_id=alpha.detachment_selection.detachment_id,
        ),
        _detachment_stratagem(
            stratagem_id="wrong-detachment-only",
            command_point_cost=1,
            detachment_id="other-detachment",
        ),
    )
    player_index = build_player_stratagem_index(
        catalog,
        detachment_id=alpha.detachment_selection.detachment_id,
        stratagem_ids=("detachment-ambush",),
    )
    context = _context(state=state, player_id="player-a")

    assert tuple(record.definition.stratagem_id for record in player_index.all_records()) == (
        "command-reroll",
        "detachment-ambush",
    )
    assert stratagem_use_options_from_index(state=state, index=player_index, context=context) == (
        stratagem_use_options(state=state, catalog_records=catalog, context=context)
    )


def test_unsupported_source_handlers_reject_finite_and_parameterized_submissions() -> None:
    finite_lifecycle = _battle_lifecycle()
    finite_state = _state(finite_lifecycle)
    _set_current_battle_phase(finite_state, BattlePhase.CHARGE)
    _grant_cp(finite_state, player_id="player-a", amount=1)
    finite_context = _context(
        state=finite_state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.AFTER_UNIT_ENDS_CHARGE_MOVE,
    )
    deferred_core_stratagem = _source_stratagem_record("crushing-impact")
    finite_request = create_stratagem_use_decision_request(
        state=finite_state,
        context=finite_context,
        options=(
            _stratagem_option_for_record(
                record=deferred_core_stratagem,
                context=finite_context,
                binding=_friendly_binding(),
            ),
        ),
    )
    finite_lifecycle.decision_controller.request_decision(finite_request)
    rejected_finite = finite_lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase12b-unsupported-source-finite",
            request=finite_request,
            selected_option_id=finite_request.options[0].option_id,
        )
    )

    assert rejected_finite.status_kind is LifecycleStatusKind.INVALID
    assert rejected_finite.payload == {"invalid_reason": "unsupported_handler"}
    assert finite_state.command_point_total("player-a") == 1
    assert finite_state.stratagem_use_records == []
    assert finite_lifecycle.decision_controller.queue.pending_requests == (finite_request,)

    parameterized_lifecycle = _battle_lifecycle()
    parameterized_state = _state(parameterized_lifecycle)
    _set_current_battle_phase(parameterized_state, BattlePhase.CHARGE)
    _grant_cp(parameterized_state, player_id="player-a", amount=1)
    deferred_core_stratagem = _source_stratagem_record("crushing-impact")
    parameterized_context = _context(
        state=parameterized_state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.AFTER_UNIT_ENDS_CHARGE_MOVE,
    )
    proposal_request = StratagemTargetProposal.for_request(
        context=parameterized_context,
        catalog_record=deferred_core_stratagem,
    )
    unavailable_proposal = request_stratagem_target_proposal(
        state=parameterized_state,
        decisions=parameterized_lifecycle.decision_controller,
        proposal_request=proposal_request,
    )

    assert unavailable_proposal.status_kind is LifecycleStatusKind.UNSUPPORTED
    assert unavailable_proposal.payload == {
        "player_id": "player-a",
        "stratagem_id": "crushing-impact",
        "unavailable_reason": "unsupported_handler",
    }
    assert parameterized_state.command_point_total("player-a") == 1
    assert parameterized_state.stratagem_use_records == []
    _assert_no_pending(parameterized_lifecycle)

    pending_proposal_request = DecisionRequest(
        request_id=parameterized_state.next_decision_request_id(),
        decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
        actor_id=proposal_request.player_id,
        payload=validate_json_value({"proposal_request": proposal_request.to_payload()}),
        options=(parameterized_decision_option(),),
    )
    parameterized_lifecycle.decision_controller.request_decision(pending_proposal_request)
    rejected_parameterized = parameterized_lifecycle.submit_decision(
        _proposal_result(
            request=pending_proposal_request,
            result_id="phase12b-unsupported-source-parameterized",
            proposal=proposal_request.with_binding(_friendly_binding()),
        )
    )

    assert rejected_parameterized.status_kind is LifecycleStatusKind.INVALID
    assert rejected_parameterized.payload == {"invalid_reason": "unsupported_handler"}
    assert parameterized_state.command_point_total("player-a") == 1
    assert parameterized_state.stratagem_use_records == []
    assert parameterized_lifecycle.decision_controller.queue.pending_requests == (
        pending_proposal_request,
    )


def test_stratagem_spend_prevalidation_rejects_cp_drift_without_underflow() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    context = _context(state=state, player_id="player-a")
    catalog = (_core_stratagem(stratagem_id="smoke", command_point_cost=1),)

    unavailable = request_stratagem_use(
        state=state,
        decisions=lifecycle.decision_controller,
        catalog_records=catalog,
        context=context,
    )
    assert unavailable.status_kind is LifecycleStatusKind.UNSUPPORTED
    _assert_no_pending(lifecycle)

    _grant_cp(state, player_id="player-a", amount=1)
    waiting = request_stratagem_use(
        state=state,
        decisions=lifecycle.decision_controller,
        catalog_records=catalog,
        context=context,
    )
    request = _decision_request(waiting)
    spend = state.spend_command_points(
        player_id="player-a",
        amount=1,
        source_id="phase12b-drift-source",
    )
    assert spend.status is CommandPointSpendStatus.APPLIED

    result = DecisionResult.for_request(
        result_id="phase12b-drift-result",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    rejected = lifecycle.submit_decision(result)

    assert rejected.status_kind is LifecycleStatusKind.INVALID
    assert rejected.payload == {"invalid_reason": "insufficient_command_points"}
    assert state.command_point_total("player-a") == 0
    assert state.stratagem_use_records == []
    pending_requests = lifecycle.decision_controller.queue.pending_requests
    assert len(pending_requests) == 1
    assert pending_requests[0] == request


def test_cp_ledger_spend_refund_and_gain_cap_are_typed_and_replay_safe() -> None:
    state = _battle_state()
    _set_current_battle_phase(state, BattlePhase.COMMAND)

    command_gain = state.gain_command_points(
        player_id="player-a",
        amount=1,
        source_id="command-phase-start",
        source_kind=CommandPointSourceKind.COMMAND_PHASE_START,
    )
    spend = state.spend_command_points(
        player_id="player-a",
        amount=1,
        source_id="phase12b-stratagem-spend",
    )
    refund = state.refund_command_points(
        player_id="player-a",
        amount=1,
        source_id="phase12b-refund",
    )
    capped_gain = state.gain_command_points(
        player_id="player-a",
        amount=1,
        source_id="phase12b-extra-gain",
        source_kind=CommandPointSourceKind.OTHER,
    )
    capped_refund = state.refund_command_points(
        player_id="player-a",
        amount=1,
        source_id="phase12b-extra-refund",
    )
    exempt_refund = state.refund_command_points(
        player_id="player-a",
        amount=1,
        source_id="phase12b-exempt-refund",
        cap_exempt=True,
    )

    assert command_gain.status is CommandPointGainStatus.APPLIED
    assert spend.status is CommandPointSpendStatus.APPLIED
    assert refund.status is CommandPointRefundStatus.APPLIED
    assert capped_gain.status is CommandPointGainStatus.CAPPED
    assert capped_refund.status is CommandPointRefundStatus.CAPPED
    assert exempt_refund.status is CommandPointRefundStatus.APPLIED
    assert CommandPointSpendResult.from_payload(spend.to_payload()) == spend
    assert state.command_point_total("player-a") == 2
    assert GameState.from_payload(_game_state_payload_copy(state)).to_payload() == (
        state.to_payload()
    )


def test_same_phase_duplicate_and_battle_shocked_targeting_suppress_options() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    _grant_cp(state, player_id="player-a", amount=3)
    context = _context(state=state, player_id="player-a")
    unit_id = "army-alpha:intercessor-unit-1"
    target_spec = StratagemTargetSpec(target_kind=StratagemTargetKind.FRIENDLY_UNIT)
    catalog = (
        _core_stratagem(
            stratagem_id="armor-of-contempt",
            command_point_cost=1,
            target_spec=target_spec,
        ),
    )

    request = _decision_request(
        request_stratagem_use(
            state=state,
            decisions=lifecycle.decision_controller,
            catalog_records=catalog,
            context=context,
        )
    )
    result = DecisionResult.for_request(
        result_id="phase12b-first-targeted-use",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    lifecycle.submit_decision(result)

    duplicate = request_stratagem_use(
        state=state,
        decisions=lifecycle.decision_controller,
        catalog_records=catalog,
        context=context,
    )
    assert duplicate.status_kind is LifecycleStatusKind.UNSUPPORTED

    shocked_lifecycle = _battle_lifecycle()
    shocked_state = _state(shocked_lifecycle)
    _set_current_battle_phase(shocked_state, BattlePhase.MOVEMENT)
    _grant_cp(shocked_state, player_id="player-a", amount=2)
    shocked_context = _context(state=shocked_state, player_id="player-a")
    fresh_catalog = (
        _core_stratagem(
            stratagem_id="rapid-ingress",
            command_point_cost=1,
            target_spec=target_spec,
        ),
    )
    shocked_state.battle_shocked_unit_ids = [unit_id]
    shocked_options = stratagem_use_options(
        state=shocked_state,
        catalog_records=fresh_catalog,
        context=shocked_context,
    )
    allowed_shocked_options = stratagem_use_options(
        state=shocked_state,
        catalog_records=(
            _core_stratagem(
                stratagem_id="inspiring-command",
                command_point_cost=1,
                target_spec=target_spec,
                restriction_policy=StratagemRestrictionPolicy(allow_battle_shocked_targets=True),
            ),
        ),
        context=shocked_context,
    )

    assert shocked_options == ()
    assert len(allowed_shocked_options) == 1
    assert cast(dict[str, JsonValue], allowed_shocked_options[0].payload)["target_binding"] == {
        "target_kind": "friendly_unit",
        "target_player_id": "player-a",
        "target_unit_instance_id": unit_id,
    }


def test_different_stratagem_same_unit_same_phase_suppresses_options() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    _grant_cp(state, player_id="player-a", amount=3)
    context = _context(state=state, player_id="player-a")
    unit_id = "army-alpha:intercessor-unit-1"
    target_spec = StratagemTargetSpec(target_kind=StratagemTargetKind.FRIENDLY_UNIT)
    first_catalog = (
        _core_stratagem(
            stratagem_id="first-targeted-buff",
            command_point_cost=1,
            target_spec=target_spec,
        ),
    )

    request = _decision_request(
        request_stratagem_use(
            state=state,
            decisions=lifecycle.decision_controller,
            catalog_records=first_catalog,
            context=context,
        )
    )
    lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase12b-first-affected-unit-use",
            request=request,
            selected_option_id=_option_id_for_target(request, unit_id),
        )
    )
    first_use = state.stratagem_use_records[0]

    assert first_use.affected_unit_instance_ids == (unit_id,)
    assert StratagemUseRecord.from_payload(first_use.to_payload()) == first_use
    assert first_use.to_payload()["affected_unit_instance_ids"] == [unit_id]
    second_catalog = (
        _core_stratagem(
            stratagem_id="second-targeted-buff",
            command_point_cost=1,
            target_spec=target_spec,
        ),
    )
    duplicate = request_stratagem_use(
        state=state,
        decisions=lifecycle.decision_controller,
        catalog_records=second_catalog,
        context=context,
    )

    assert duplicate.status_kind is LifecycleStatusKind.UNSUPPORTED
    assert (
        stratagem_use_options(
            state=state,
            catalog_records=second_catalog,
            context=context,
        )
        == ()
    )

    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    shooting_context = _context(state=state, player_id="player-a")
    shooting_catalog = (
        _core_stratagem(
            stratagem_id="second-targeted-buff",
            command_point_cost=1,
            timing=StratagemTimingDescriptor(
                trigger_kind=TimingTriggerKind.START_PHASE,
                phase=BattlePhase.SHOOTING,
            ),
            target_spec=target_spec,
        ),
    )

    assert (
        len(
            stratagem_use_options(
                state=state,
                catalog_records=shooting_catalog,
                context=shooting_context,
            )
        )
        == 1
    )


def test_opponent_stratagem_affecting_unit_blocks_same_phase_stratagem() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    _grant_cp(state, player_id="player-a", amount=1)
    _grant_cp(state, player_id="player-b", amount=1)
    unit_id = "army-alpha:intercessor-unit-1"
    player_b_context = _context(state=state, player_id="player-b")
    player_b_catalog = (
        _core_stratagem(
            stratagem_id="opponent-any-unit-effect",
            command_point_cost=1,
            target_spec=StratagemTargetSpec(target_kind=StratagemTargetKind.ANY_UNIT),
        ),
    )

    opponent_request = _decision_request(
        request_stratagem_use(
            state=state,
            decisions=lifecycle.decision_controller,
            catalog_records=player_b_catalog,
            context=player_b_context,
        )
    )
    lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase12b-opponent-affects-unit",
            request=opponent_request,
            selected_option_id=_option_id_for_target(opponent_request, unit_id),
        )
    )

    assert state.stratagem_use_records[0].player_id == "player-b"
    assert state.stratagem_use_records[0].affected_unit_instance_ids == (unit_id,)
    player_a_context = _context(state=state, player_id="player-a")
    player_a_catalog = (
        _core_stratagem(
            stratagem_id="player-friendly-unit-effect",
            command_point_cost=1,
            target_spec=StratagemTargetSpec(target_kind=StratagemTargetKind.FRIENDLY_UNIT),
        ),
    )

    blocked = request_stratagem_use(
        state=state,
        decisions=lifecycle.decision_controller,
        catalog_records=player_a_catalog,
        context=player_a_context,
    )

    assert blocked.status_kind is LifecycleStatusKind.UNSUPPORTED
    assert (
        stratagem_use_options(
            state=state,
            catalog_records=player_a_catalog,
            context=player_a_context,
        )
        == ()
    )


def test_stratagem_use_record_rejects_duplicate_affected_unit_ids() -> None:
    unit_id = "army-alpha:intercessor-unit-1"

    with pytest.raises(GameLifecycleError, match="affected_unit_instance_ids must be unique"):
        StratagemUseRecord(
            use_id="phase12b-duplicate-affected-unit",
            player_id="player-a",
            stratagem_id="duplicate-affected-unit-test",
            source_id="source:duplicate-affected-unit-test",
            battle_round=1,
            phase=BattlePhase.MOVEMENT,
            timing_window_id=None,
            request_id="phase12b-duplicate-affected-unit-request",
            result_id="phase12b-duplicate-affected-unit-result",
            selected_option_id="phase12b-duplicate-affected-unit-option",
            target_binding=StratagemTargetBinding(
                target_kind=StratagemTargetKind.FRIENDLY_UNIT,
                target_player_id="player-a",
                target_unit_instance_id=unit_id,
            ),
            affected_unit_instance_ids=(unit_id, unit_id),
            command_point_cost=0,
            command_point_transaction_id=None,
            handler_id="record_only",
        )


def test_attached_unit_components_share_one_stratagem_affected_key() -> None:
    bodyguard_id = "army-alpha:intercessor-unit-1"
    leader_id = "army-alpha:captain-unit"
    attached_id = "attached-unit:army-alpha:captain-intercessors"
    lifecycle = _battle_lifecycle(config=_attached_unit_config())
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    _grant_cp(state, player_id="player-a", amount=3)
    _mark_attached_unit_join(
        state,
        player_id="player-a",
        attached_unit_instance_id=attached_id,
        component_unit_instance_ids=(bodyguard_id, leader_id),
    )
    context = _context(state=state, player_id="player-a")
    target_spec = StratagemTargetSpec(target_kind=StratagemTargetKind.FRIENDLY_UNIT)
    first_catalog = (
        _core_stratagem(
            stratagem_id="bodyguard-stratagem",
            command_point_cost=1,
            target_spec=target_spec,
        ),
    )

    request = _decision_request(
        request_stratagem_use(
            state=state,
            decisions=lifecycle.decision_controller,
            catalog_records=first_catalog,
            context=context,
        )
    )
    lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase12b-attached-bodyguard-use",
            request=request,
            selected_option_id=_option_id_for_target(request, bodyguard_id),
        )
    )

    assert state.stratagem_use_records[0].affected_unit_instance_ids == (attached_id,)
    second_catalog = (
        _core_stratagem(
            stratagem_id="leader-stratagem",
            command_point_cost=1,
            target_spec=target_spec,
        ),
    )
    options = stratagem_use_options(
        state=state,
        catalog_records=second_catalog,
        context=context,
    )

    assert options == ()


def test_parameterized_stratagem_target_proposals_validate_before_queue_pop() -> None:
    valid_lifecycle = _battle_lifecycle()
    valid_state = _state(valid_lifecycle)
    valid_request = _parameterized_request(valid_lifecycle)
    proposal_request = _proposal_request_from_decision(valid_request)
    valid_result = _proposal_result(
        request=valid_request,
        result_id="phase12b-valid-proposal",
        proposal=proposal_request.with_binding(_friendly_binding()),
    )

    valid_status = valid_lifecycle.submit_decision(valid_result)

    assert valid_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert valid_state.command_point_total("player-a") == 0
    assert len(valid_state.stratagem_use_records) == 1
    use_record = valid_state.stratagem_use_records[0]
    assert use_record.stratagem_id == "parameterized-barrage"
    assert use_record.command_point_cost == 1
    assert use_record.command_point_transaction_id is not None
    assert (
        _last_event_payload(
            valid_lifecycle.decision_controller,
            "stratagem_target_proposal_accepted",
        )["result_id"]
        == "phase12b-valid-proposal"
    )
    assert _last_event_payload(valid_lifecycle.decision_controller, "stratagem_used") == (
        use_record.to_payload()
    )
    assert GameLifecycle.from_payload(_lifecycle_payload_copy(valid_lifecycle)).to_payload() == (
        valid_lifecycle.to_payload()
    )

    malformed_lifecycle = _battle_lifecycle()
    malformed_state = _state(malformed_lifecycle)
    malformed_request = _parameterized_request(malformed_lifecycle)
    malformed = malformed_lifecycle.submit_decision(
        DecisionResult(
            result_id="phase12b-malformed-proposal",
            request_id=malformed_request.request_id,
            decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
            actor_id=malformed_request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload={"not_proposal": True},
        )
    )
    assert malformed.status_kind is LifecycleStatusKind.INVALID
    assert malformed.payload == {"invalid_reason": "malformed_payload"}
    assert malformed_state.command_point_total("player-a") == 1
    assert malformed_state.stratagem_use_records == []
    assert malformed_lifecycle.decision_controller.queue.pending_requests == (malformed_request,)

    schema_lifecycle = _battle_lifecycle()
    schema_request = _parameterized_request(schema_lifecycle)
    schema_proposal = _proposal_request_from_decision(schema_request)
    schema = schema_lifecycle.submit_decision(
        _proposal_result(
            request=schema_request,
            result_id="phase12b-schema-proposal",
            proposal=schema_proposal,
        )
    )
    assert schema.status_kind is LifecycleStatusKind.INVALID
    assert schema.payload == {"invalid_reason": "schema"}

    unknown_target_lifecycle = _battle_lifecycle()
    unknown_target_state = _state(unknown_target_lifecycle)
    unknown_target_request = _parameterized_request(unknown_target_lifecycle)
    unknown_target_proposal = _proposal_request_from_decision(unknown_target_request).with_binding(
        StratagemTargetBinding(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_player_id="player-a",
            target_unit_instance_id="army-alpha:missing-unit",
        )
    )
    unknown_target = unknown_target_lifecycle.submit_decision(
        _proposal_result(
            request=unknown_target_request,
            result_id="phase12b-unknown-target-proposal",
            proposal=unknown_target_proposal,
        )
    )
    assert unknown_target.status_kind is LifecycleStatusKind.INVALID
    assert unknown_target.payload == {"invalid_reason": "unknown_target_unit"}
    assert unknown_target_state.command_point_total("player-a") == 1
    assert unknown_target_state.stratagem_use_records == []
    assert unknown_target_lifecycle.decision_controller.queue.pending_requests == (
        unknown_target_request,
    )

    wrong_context_lifecycle = _battle_lifecycle()
    wrong_context_request = _parameterized_request(wrong_context_lifecycle)
    wrong_context_base = _proposal_request_from_decision(wrong_context_request).with_binding(
        _friendly_binding()
    )
    wrong_context_proposal = replace(
        wrong_context_base,
        context=replace(wrong_context_base.context, player_id="player-b"),
    )
    wrong_context = wrong_context_lifecycle.submit_decision(
        _proposal_result(
            request=wrong_context_request,
            result_id="phase12b-wrong-context-proposal",
            proposal=wrong_context_proposal,
        )
    )
    assert wrong_context.status_kind is LifecycleStatusKind.INVALID
    assert wrong_context.payload == {"invalid_reason": "wrong_context"}

    stale_lifecycle = _battle_lifecycle()
    stale_request = _parameterized_request(stale_lifecycle)
    stale_state = _state(stale_lifecycle)
    _set_current_battle_phase(stale_state, BattlePhase.SHOOTING)
    stale_proposal = _proposal_request_from_decision(stale_request).with_binding(
        _friendly_binding()
    )
    stale = stale_lifecycle.submit_decision(
        _proposal_result(
            request=stale_request,
            result_id="phase12b-stale-proposal",
            proposal=stale_proposal,
        )
    )
    assert stale.status_kind is LifecycleStatusKind.INVALID
    assert stale.payload == {"invalid_reason": "stale_phase"}


def test_parameterized_stratagem_proposal_uses_actual_restriction_policy() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    state.battle_shocked_unit_ids = ["army-alpha:intercessor-unit-1"]
    request = _parameterized_request(
        lifecycle,
        restriction_policy=StratagemRestrictionPolicy(allow_battle_shocked_targets=True),
    )
    proposal = _proposal_request_from_decision(request).with_binding(_friendly_binding())

    accepted = lifecycle.submit_decision(
        _proposal_result(
            request=request,
            result_id="phase12b-parameterized-policy",
            proposal=proposal,
        )
    )

    assert accepted.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert len(state.stratagem_use_records) == 1


def test_non_active_stratagem_can_resolve_inside_reaction_window_after_restore() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    _grant_cp(state, player_id="player-b", amount=1)
    context = _context(
        state=state,
        player_id="player-b",
        trigger_kind=TimingTriggerKind.AFTER_ENEMY_UNIT_ENDS_MOVE,
    )
    catalog = (
        _core_stratagem(
            stratagem_id="reactive-smoke",
            command_point_cost=1,
            timing=StratagemTimingDescriptor(
                trigger_kind=TimingTriggerKind.AFTER_ENEMY_UNIT_ENDS_MOVE,
                phase=BattlePhase.MOVEMENT,
            ),
        ),
    )
    reaction_window = ReactionWindow(
        timing_window=_timing_window(
            state=state,
            trigger_kind=TimingTriggerKind.AFTER_ENEMY_UNIT_ENDS_MOVE,
            phase=BattlePhase.MOVEMENT,
            window_id="phase12b-reactive-window",
        ),
        eligible_player_ids=("player-b",),
    )
    options = stratagem_use_options(state=state, catalog_records=catalog, context=context)
    triggered = lifecycle.reaction_queue.emit_decision_request(
        state=state,
        decisions=lifecycle.decision_controller,
        reaction_window=reaction_window,
        parent_phase=BattlePhase.MOVEMENT,
        parent_step="move_units",
        resume_token="phase12b-resume-token",
        actor_id="player-b",
        decision_type=STRATAGEM_DECISION_TYPE,
        options=options,
        payload={"source": "phase12b-reactive-stratagem"},
    )
    restored = GameLifecycle.from_payload(_lifecycle_payload_copy(lifecycle))
    waiting = restored.advance_until_decision_or_terminal()
    assert waiting.decision_request == triggered.decision_request
    result = DecisionResult.for_request(
        result_id="phase12b-reactive-result",
        request=triggered.decision_request,
        selected_option_id=triggered.decision_request.options[0].option_id,
    )

    restored.submit_decision(result)

    assert restored.reaction_queue.frames == ()
    assert (
        _last_event_payload(
            restored.decision_controller,
            "reaction_parent_resumed",
        )["resume_token"]
        == "phase12b-resume-token"
    )


def test_core_and_detachment_stratagem_gates_are_reflected_in_options() -> None:
    state = _battle_state()
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    _grant_cp(state, player_id="player-a", amount=3)
    alpha = state.army_definitions[0]
    state.army_definitions[0] = replace(
        alpha,
        detachment_selection=DetachmentSelection(
            faction_id=alpha.detachment_selection.faction_id,
            detachment_id=alpha.detachment_selection.detachment_id,
            stratagem_ids=("detachment-ambush",),
        ),
    )
    context = _context(state=state, player_id="player-a")
    options = stratagem_use_options(
        state=state,
        catalog_records=(
            _core_stratagem(stratagem_id="command-reroll", command_point_cost=1),
            _detachment_stratagem(
                stratagem_id="detachment-ambush",
                command_point_cost=1,
                detachment_id=alpha.detachment_selection.detachment_id,
            ),
            _detachment_stratagem(
                stratagem_id="wrong-detachment-only",
                command_point_cost=1,
                detachment_id="other-detachment",
            ),
        ),
        context=context,
    )

    option_ids = tuple(option.option_id for option in options)
    assert "use-stratagem:command-reroll:target:none" in option_ids
    assert "use-stratagem:detachment-ambush:target:none" in option_ids
    assert "use-stratagem:wrong-detachment-only:target:none" not in option_ids


def test_public_projection_exposes_command_points_and_stratagem_records() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    _grant_cp(state, player_id="player-a", amount=1)
    context = _context(state=state, player_id="player-a")
    request = _decision_request(
        request_stratagem_use(
            state=state,
            decisions=lifecycle.decision_controller,
            catalog_records=(
                _core_stratagem(stratagem_id="projection-stratagem", command_point_cost=1),
            ),
            context=context,
        )
    )

    lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase12b-projection-result",
            request=request,
            selected_option_id=request.options[0].option_id,
        )
    )
    view = project_game_view(lifecycle=lifecycle, viewer_player_id="player-b")

    cp_payload = cast(dict[str, JsonValue], view["public_command_point_ledgers"][0])
    use_payload = cast(dict[str, JsonValue], view["public_stratagem_use_records"][0])
    assert cp_payload["player_id"] == "player-a"
    assert use_payload["stratagem_id"] == "projection-stratagem"


def test_stratagem_command_point_effects_create_ledger_transactions() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    context = _context(state=state, player_id="player-a")
    request = _decision_request(
        request_stratagem_use(
            state=state,
            decisions=lifecycle.decision_controller,
            catalog_records=(
                _core_stratagem(
                    stratagem_id="resourceful-command",
                    command_point_cost=0,
                    effect_payload={
                        "command_point_gain": {"amount": 1},
                        "command_point_refund": {"amount": 1, "cap_exempt": True},
                    },
                ),
            ),
            context=context,
        )
    )

    lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase12b-cp-effect-result",
            request=request,
            selected_option_id=request.options[0].option_id,
        )
    )

    assert state.command_point_total("player-a") == 2
    gain_source = _last_event_payload(lifecycle.decision_controller, "command_points_gained")[
        "source_id"
    ]
    refund_source = _last_event_payload(lifecycle.decision_controller, "command_points_refunded")[
        "source_id"
    ]
    assert type(gain_source) is str
    assert type(refund_source) is str
    assert gain_source.endswith(":cp-gain")
    assert refund_source.endswith(":cp-refund")


def test_phase12b_fail_fast_validation_branches() -> None:
    state = _battle_state()
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    context = _context(state=state, player_id="player-a")
    timing = StratagemTimingDescriptor(
        trigger_kind=TimingTriggerKind.START_PHASE,
        phase=BattlePhase.MOVEMENT,
        timing_window_id="window-a",
    )
    assert timing.matches(replace(context, timing_window_id="window-a"))
    assert not timing.matches(replace(context, timing_window_id="window-b"))
    assert not timing.matches(replace(context, trigger_kind=TimingTriggerKind.END_PHASE))
    assert not timing.matches(replace(context, phase=BattlePhase.SHOOTING))
    with pytest.raises(GameLifecycleError, match="Stratagem timing requires"):
        timing.matches(cast(Any, object()))
    with pytest.raises(GameLifecycleError, match="Targetless StratagemTargetSpec"):
        StratagemTargetSpec(target_kind=StratagemTargetKind.NONE, enumerable=False)
    assert StratagemTargetSpec(target_kind=StratagemTargetKind.FRIENDLY_UNIT).requires_target
    with pytest.raises(GameLifecycleError, match="timing must be a descriptor"):
        StratagemDefinition(
            stratagem_id="bad-timing",
            name="Bad Timing",
            source_id="bad-source",
            command_point_cost=0,
            category=StratagemCategory.BATTLE_TACTIC,
            when_descriptor="bad when",
            target_descriptor="bad target",
            effect_descriptor="bad effect",
            restrictions_descriptor="bad restrictions",
            timing=cast(StratagemTimingDescriptor, object()),
        )
    with pytest.raises(GameLifecycleError, match="restriction_policy must be a policy"):
        StratagemDefinition(
            stratagem_id="bad-policy",
            name="Bad Policy",
            source_id="bad-source",
            command_point_cost=0,
            category=StratagemCategory.BATTLE_TACTIC,
            when_descriptor="bad when",
            target_descriptor="bad target",
            effect_descriptor="bad effect",
            restrictions_descriptor="bad restrictions",
            timing=timing,
            restriction_policy=cast(StratagemRestrictionPolicy, object()),
        )
    with pytest.raises(GameLifecycleError, match="target_spec must be a target spec"):
        StratagemDefinition(
            stratagem_id="bad-target-spec",
            name="Bad Target Spec",
            source_id="bad-source",
            command_point_cost=0,
            category=StratagemCategory.BATTLE_TACTIC,
            when_descriptor="bad when",
            target_descriptor="bad target",
            effect_descriptor="bad effect",
            restrictions_descriptor="bad restrictions",
            timing=timing,
            target_spec=cast(StratagemTargetSpec, object()),
        )
    with pytest.raises(GameLifecycleError, match="Core StratagemCatalogRecord"):
        StratagemCatalogRecord(
            record_id="bad-core-gate",
            definition=_core_stratagem(
                stratagem_id="bad-core",
                command_point_cost=0,
            ).definition,
            detachment_id="not-allowed",
        )
    with pytest.raises(GameLifecycleError, match="Detachment StratagemCatalogRecord requires"):
        StratagemCatalogRecord(
            record_id="bad-detachment-gate",
            definition=_core_stratagem(
                stratagem_id="bad-detachment",
                command_point_cost=0,
            ).definition,
            availability_kind=StratagemAvailabilityKind.DETACHMENT,
        )
    with pytest.raises(GameLifecycleError, match="Targetless StratagemTargetBinding"):
        StratagemTargetBinding(
            target_kind=StratagemTargetKind.NONE,
            target_player_id="player-a",
            target_unit_instance_id="army-alpha:intercessor-unit-1",
        )
    with pytest.raises(GameLifecycleError, match="Unit StratagemTargetBinding requires"):
        StratagemTargetBinding(target_kind=StratagemTargetKind.FRIENDLY_UNIT)
    proposal_record = _core_stratagem(
        stratagem_id="proposal",
        command_point_cost=0,
        target_spec=StratagemTargetSpec(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            enumerable=False,
        ),
    )
    with pytest.raises(GameLifecycleError, match="proposal_kind is unsupported"):
        StratagemTargetProposal(
            proposal_kind="bad-kind",
            context=context,
            catalog_record=proposal_record,
        )
    with pytest.raises(GameLifecycleError, match="context must be an eligibility context"):
        StratagemTargetProposal(
            proposal_kind="stratagem_target_binding",
            context=cast(StratagemEligibilityContext, object()),
            catalog_record=proposal_record,
        )
    with pytest.raises(GameLifecycleError, match="catalog_record must be a catalog record"):
        StratagemTargetProposal(
            proposal_kind="stratagem_target_binding",
            context=context,
            catalog_record=cast(StratagemCatalogRecord, object()),
        )
    with pytest.raises(GameLifecycleError, match="must require parameterized targets"):
        StratagemTargetProposal(
            proposal_kind="stratagem_target_binding",
            context=context,
            catalog_record=_core_stratagem(stratagem_id="finite-proposal", command_point_cost=0),
        )
    with pytest.raises(GameLifecycleError, match="target_binding must be a target binding"):
        StratagemTargetProposal(
            proposal_kind="stratagem_target_binding",
            context=context,
            catalog_record=proposal_record,
            target_binding=cast(StratagemTargetBinding, object()),
        )


def test_command_point_spend_and_refund_results_validate_fail_fast() -> None:
    ledger, gain = CommandPointLedger.initial(player_id="player-a").gain(
        battle_round=1,
        amount=2,
        source_id="phase12b-validation-gain",
        source_kind=CommandPointSourceKind.COMMAND_PHASE_START,
    )
    assert gain.transaction is not None
    spent_ledger, spend = ledger.spend(
        battle_round=1,
        amount=1,
        source_id="phase12b-validation-spend",
    )
    assert spend.transaction is not None
    refunded_ledger, refund = spent_ledger.refund(
        battle_round=1,
        amount=1,
        source_id="phase12b-validation-refund",
        cap_exempt=True,
    )
    assert refund.transaction is not None
    insufficient_ledger, insufficient = refunded_ledger.spend(
        battle_round=1,
        amount=99,
        source_id="phase12b-validation-underflow",
    )

    assert insufficient_ledger is refunded_ledger
    assert insufficient.status is CommandPointSpendStatus.INSUFFICIENT
    assert command_point_spend_status_from_token(CommandPointSpendStatus.APPLIED) == (
        CommandPointSpendStatus.APPLIED
    )
    assert command_point_refund_status_from_token(CommandPointRefundStatus.CAPPED) == (
        CommandPointRefundStatus.CAPPED
    )
    with pytest.raises(GameLifecycleError, match="cannot use stratagem spend/refund"):
        ledger.gain(
            battle_round=1,
            amount=1,
            source_id="phase12b-invalid-generic-refund",
            source_kind=CommandPointSourceKind.STRATAGEM_REFUND,
        )
    with pytest.raises(GameLifecycleError, match="CommandPointSpendStatus token must"):
        command_point_spend_status_from_token(cast(Any, 1))
    with pytest.raises(GameLifecycleError, match="Unsupported CommandPointSpendStatus"):
        command_point_spend_status_from_token("bad")
    with pytest.raises(GameLifecycleError, match="CommandPointRefundStatus token must"):
        command_point_refund_status_from_token(cast(Any, 1))
    with pytest.raises(GameLifecycleError, match="Unsupported CommandPointRefundStatus"):
        command_point_refund_status_from_token("bad")
    with pytest.raises(GameLifecycleError, match="source_kind must be stratagem_spend"):
        CommandPointSpendResult(
            player_id="player-a",
            battle_round=1,
            requested_amount=1,
            applied_amount=1,
            status=CommandPointSpendStatus.APPLIED,
            source_id="bad-spend-source-kind",
            source_kind=CommandPointSourceKind.OTHER,
            transaction=spend.transaction,
        )
    with pytest.raises(GameLifecycleError, match="requires a transaction"):
        CommandPointSpendResult(
            player_id="player-a",
            battle_round=1,
            requested_amount=1,
            applied_amount=1,
            status=CommandPointSpendStatus.APPLIED,
            source_id="bad-spend-missing-transaction",
            source_kind=CommandPointSourceKind.STRATAGEM_SPEND,
        )
    with pytest.raises(GameLifecycleError, match="transaction amount drift"):
        CommandPointSpendResult(
            player_id="player-a",
            battle_round=1,
            requested_amount=2,
            applied_amount=2,
            status=CommandPointSpendStatus.APPLIED,
            source_id="bad-spend-drift",
            source_kind=CommandPointSourceKind.STRATAGEM_SPEND,
            transaction=spend.transaction,
        )
    with pytest.raises(GameLifecycleError, match="cannot have insufficient_reason"):
        CommandPointSpendResult(
            player_id="player-a",
            battle_round=1,
            requested_amount=1,
            applied_amount=1,
            status=CommandPointSpendStatus.APPLIED,
            source_id="bad-spend-reason",
            source_kind=CommandPointSourceKind.STRATAGEM_SPEND,
            transaction=spend.transaction,
            insufficient_reason="not-valid",
        )
    with pytest.raises(GameLifecycleError, match="cannot have a transaction"):
        CommandPointSpendResult(
            player_id="player-a",
            battle_round=1,
            requested_amount=1,
            applied_amount=0,
            status=CommandPointSpendStatus.INSUFFICIENT,
            source_id="bad-insufficient-transaction",
            source_kind=CommandPointSourceKind.STRATAGEM_SPEND,
            transaction=spend.transaction,
            insufficient_reason="insufficient",
        )
    with pytest.raises(GameLifecycleError, match="applies no CP"):
        CommandPointSpendResult(
            player_id="player-a",
            battle_round=1,
            requested_amount=1,
            applied_amount=1,
            status=CommandPointSpendStatus.INSUFFICIENT,
            source_id="bad-insufficient-amount",
            source_kind=CommandPointSourceKind.STRATAGEM_SPEND,
            insufficient_reason="insufficient",
        )
    with pytest.raises(GameLifecycleError, match="requires insufficient_reason"):
        CommandPointSpendResult(
            player_id="player-a",
            battle_round=1,
            requested_amount=1,
            applied_amount=0,
            status=CommandPointSpendStatus.INSUFFICIENT,
            source_id="bad-insufficient-reason",
            source_kind=CommandPointSourceKind.STRATAGEM_SPEND,
        )
    with pytest.raises(GameLifecycleError, match="source_kind must be stratagem_refund"):
        CommandPointRefundResult(
            player_id="player-a",
            battle_round=1,
            requested_amount=1,
            applied_amount=1,
            status=CommandPointRefundStatus.APPLIED,
            source_id="bad-refund-source-kind",
            source_kind=CommandPointSourceKind.OTHER,
            transaction=refund.transaction,
        )
    with pytest.raises(GameLifecycleError, match="requires a transaction"):
        CommandPointRefundResult(
            player_id="player-a",
            battle_round=1,
            requested_amount=1,
            applied_amount=1,
            status=CommandPointRefundStatus.APPLIED,
            source_id="bad-refund-missing-transaction",
            source_kind=CommandPointSourceKind.STRATAGEM_REFUND,
        )
    with pytest.raises(GameLifecycleError, match="transaction amount drift"):
        CommandPointRefundResult(
            player_id="player-a",
            battle_round=1,
            requested_amount=2,
            applied_amount=2,
            status=CommandPointRefundStatus.APPLIED,
            source_id="bad-refund-drift",
            source_kind=CommandPointSourceKind.STRATAGEM_REFUND,
            transaction=refund.transaction,
        )
    with pytest.raises(GameLifecycleError, match="cannot have capped_reason"):
        CommandPointRefundResult(
            player_id="player-a",
            battle_round=1,
            requested_amount=1,
            applied_amount=1,
            status=CommandPointRefundStatus.APPLIED,
            source_id="bad-refund-reason",
            source_kind=CommandPointSourceKind.STRATAGEM_REFUND,
            transaction=refund.transaction,
            capped_reason="not-valid",
        )
    with pytest.raises(GameLifecycleError, match="cannot have a transaction"):
        CommandPointRefundResult(
            player_id="player-a",
            battle_round=1,
            requested_amount=1,
            applied_amount=0,
            status=CommandPointRefundStatus.CAPPED,
            source_id="bad-capped-transaction",
            source_kind=CommandPointSourceKind.STRATAGEM_REFUND,
            transaction=refund.transaction,
            capped_reason="capped",
        )
    with pytest.raises(GameLifecycleError, match="applies no CP"):
        CommandPointRefundResult(
            player_id="player-a",
            battle_round=1,
            requested_amount=1,
            applied_amount=1,
            status=CommandPointRefundStatus.CAPPED,
            source_id="bad-capped-amount",
            source_kind=CommandPointSourceKind.STRATAGEM_REFUND,
            capped_reason="capped",
        )
    with pytest.raises(GameLifecycleError, match="requires capped_reason"):
        CommandPointRefundResult(
            player_id="player-a",
            battle_round=1,
            requested_amount=1,
            applied_amount=0,
            status=CommandPointRefundStatus.CAPPED,
            source_id="bad-capped-reason",
            source_kind=CommandPointSourceKind.STRATAGEM_REFUND,
        )


def test_stratagem_request_and_prevalidation_guards_are_fail_fast() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    context = _context(state=state, player_id="player-a")
    option = DecisionOption(
        option_id="dummy",
        label="Dummy",
        payload={"submission_kind": "dummy"},
    )
    request = create_stratagem_use_decision_request(
        state=state,
        context=context,
        options=(option,),
    )
    use_request = StratagemUseRequest(context=context, request=request)
    assert use_request.request == request

    with pytest.raises(GameLifecycleError, match="context must be an eligibility context"):
        StratagemUseRequest(context=cast(StratagemEligibilityContext, object()), request=request)
    with pytest.raises(GameLifecycleError, match="request must be a DecisionRequest"):
        StratagemUseRequest(context=context, request=cast(DecisionRequest, object()))
    wrong_type_request = DecisionRequest(
        request_id="phase12b-wrong-type-request",
        decision_type="not_use_stratagem",
        actor_id="player-a",
        payload=None,
        options=(option,),
    )
    with pytest.raises(GameLifecycleError, match="request decision_type drift"):
        StratagemUseRequest(context=context, request=wrong_type_request)
    with pytest.raises(GameLifecycleError, match="eligibility context"):
        create_stratagem_use_decision_request(
            state=state,
            context=cast(StratagemEligibilityContext, object()),
            options=(option,),
        )

    setup_state = GameState.from_config(_config())
    with pytest.raises(GameLifecycleError, match="requires battle stage"):
        StratagemEligibilityContext.from_state(
            state=setup_state,
            player_id="player-a",
            trigger_kind=TimingTriggerKind.START_PHASE,
        )
    no_phase_state = _battle_state()
    no_phase_state.battle_phase_index = None
    with pytest.raises(GameLifecycleError, match="requires a battle phase"):
        StratagemEligibilityContext.from_state(
            state=no_phase_state,
            player_id="player-a",
            trigger_kind=TimingTriggerKind.START_PHASE,
        )

    malformed_result = DecisionResult(
        result_id="phase12b-malformed-use-result",
        request_id=request.request_id,
        decision_type=STRATAGEM_DECISION_TYPE,
        actor_id="player-a",
        selected_option_id="dummy",
        payload=None,
    )
    malformed = invalid_stratagem_use_status(
        state=state,
        request=request,
        result=malformed_result,
    )
    assert malformed is not None
    assert malformed.payload == {"invalid_reason": "malformed_payload"}

    legal_option_request = _decision_request(
        request_stratagem_use(
            state=state,
            decisions=lifecycle.decision_controller,
            catalog_records=(
                _core_stratagem(stratagem_id="actor-drift-test", command_point_cost=0),
            ),
            context=context,
        )
    )
    actor_drift_result = DecisionResult(
        result_id="phase12b-actor-drift-result",
        request_id=legal_option_request.request_id,
        decision_type=STRATAGEM_DECISION_TYPE,
        actor_id="player-b",
        selected_option_id=legal_option_request.options[0].option_id,
        payload=legal_option_request.options[0].payload,
    )
    actor_drift = invalid_stratagem_use_status(
        state=state,
        request=legal_option_request,
        result=actor_drift_result,
    )
    assert actor_drift is not None
    assert actor_drift.payload == {"invalid_reason": "wrong_context"}

    proposal = StratagemTargetProposal.for_request(
        context=context,
        catalog_record=_core_stratagem(
            stratagem_id="guard-proposal",
            command_point_cost=0,
            target_spec=StratagemTargetSpec(
                target_kind=StratagemTargetKind.FRIENDLY_UNIT,
                enumerable=False,
            ),
        ),
    )
    with pytest.raises(GameLifecycleError, match="requires a DecisionController"):
        request_stratagem_target_proposal(
            state=state,
            decisions=cast(DecisionController, object()),
            proposal_request=proposal,
        )
    with pytest.raises(GameLifecycleError, match="must be a StratagemTargetProposal"):
        request_stratagem_target_proposal(
            state=state,
            decisions=lifecycle.decision_controller,
            proposal_request=cast(StratagemTargetProposal, object()),
        )
    with pytest.raises(GameLifecycleError, match="cannot include a target binding"):
        request_stratagem_target_proposal(
            state=state,
            decisions=lifecycle.decision_controller,
            proposal_request=proposal.with_binding(_friendly_binding()),
        )


def _core_stratagem(
    *,
    stratagem_id: str,
    command_point_cost: int,
    timing: StratagemTimingDescriptor | None = None,
    target_spec: StratagemTargetSpec | None = None,
    restriction_policy: StratagemRestrictionPolicy | None = None,
    effect_payload: JsonValue = None,
) -> StratagemCatalogRecord:
    return StratagemCatalogRecord(
        record_id=f"phase12b-core:{stratagem_id}",
        definition=StratagemDefinition(
            stratagem_id=stratagem_id,
            name=stratagem_id.replace("-", " ").title(),
            source_id=f"source:{stratagem_id}",
            command_point_cost=command_point_cost,
            category=StratagemCategory.BATTLE_TACTIC,
            when_descriptor="test timing descriptor",
            target_descriptor="test target descriptor",
            effect_descriptor="test effect descriptor",
            restrictions_descriptor="test restriction descriptor",
            timing=timing
            if timing is not None
            else StratagemTimingDescriptor(
                trigger_kind=TimingTriggerKind.START_PHASE,
                phase=BattlePhase.MOVEMENT,
            ),
            target_spec=target_spec if target_spec is not None else StratagemTargetSpec(),
            restriction_policy=restriction_policy
            if restriction_policy is not None
            else StratagemRestrictionPolicy(),
            effect_payload=effect_payload,
        ),
    )


def _detachment_stratagem(
    *,
    stratagem_id: str,
    command_point_cost: int,
    detachment_id: str,
) -> StratagemCatalogRecord:
    record = _core_stratagem(stratagem_id=stratagem_id, command_point_cost=command_point_cost)
    return StratagemCatalogRecord(
        record_id=f"phase12b-detachment:{stratagem_id}",
        definition=record.definition,
        availability_kind=StratagemAvailabilityKind.DETACHMENT,
        detachment_id=detachment_id,
    )


def _source_stratagem_record(stratagem_id: str) -> StratagemCatalogRecord:
    for record in eleventh_edition_stratagem_catalog_records():
        if record.definition.stratagem_id == stratagem_id:
            return record
    raise AssertionError(f"Missing source stratagem record: {stratagem_id}")


def _stratagem_option_for_record(
    *,
    record: StratagemCatalogRecord,
    context: StratagemEligibilityContext,
    binding: StratagemTargetBinding,
) -> DecisionOption:
    return DecisionOption(
        option_id=f"use-stratagem:{record.definition.stratagem_id}:target:none",
        label=record.definition.name,
        payload=validate_json_value(
            {
                "submission_kind": STRATAGEM_DECISION_TYPE,
                "context": context.to_payload(),
                "catalog_record": record.to_payload(),
                "target_binding": binding.to_payload(),
            }
        ),
    )


def _parameterized_request(
    lifecycle: GameLifecycle,
    *,
    restriction_policy: StratagemRestrictionPolicy | None = None,
) -> DecisionRequest:
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    _grant_cp(state, player_id="player-a", amount=1)
    record = _core_stratagem(
        stratagem_id="parameterized-barrage",
        command_point_cost=1,
        target_spec=StratagemTargetSpec(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            enumerable=False,
        ),
        restriction_policy=restriction_policy,
    )
    proposal = StratagemTargetProposal.for_request(
        context=_context(state=state, player_id="player-a"),
        catalog_record=record,
    )
    waiting = request_stratagem_target_proposal(
        state=state,
        decisions=lifecycle.decision_controller,
        proposal_request=proposal,
    )
    request = _decision_request(waiting)
    assert request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE
    return request


def _proposal_request_from_decision(request: DecisionRequest) -> StratagemTargetProposal:
    payload = cast(dict[str, JsonValue], request.payload)
    return StratagemTargetProposal.from_payload(
        cast(StratagemTargetProposalPayload, payload["proposal_request"])
    )


def _proposal_result(
    *,
    request: DecisionRequest,
    result_id: str,
    proposal: StratagemTargetProposal,
) -> DecisionResult:
    return DecisionResult(
        result_id=result_id,
        request_id=request.request_id,
        decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
        actor_id=request.actor_id,
        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
        payload=validate_json_value({"proposal": proposal.to_payload()}),
    )


def _friendly_binding() -> StratagemTargetBinding:
    return StratagemTargetBinding(
        target_kind=StratagemTargetKind.FRIENDLY_UNIT,
        target_player_id="player-a",
        target_unit_instance_id="army-alpha:intercessor-unit-1",
    )


def _context(
    *,
    state: GameState,
    player_id: str,
    trigger_kind: TimingTriggerKind = TimingTriggerKind.START_PHASE,
) -> StratagemEligibilityContext:
    return StratagemEligibilityContext.from_state(
        state=state,
        player_id=player_id,
        trigger_kind=trigger_kind,
    )


def _battle_lifecycle(config: GameConfig | None = None) -> GameLifecycle:
    config = _config() if config is None else config
    state = _battle_state(config=config)
    return GameLifecycle.from_payload(
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": False,
            "state": state.to_payload(),
            "decisions": DecisionController().to_payload(),
            "reaction_queue": ReactionQueue().to_payload(),
        }
    )


def _battle_state(config: GameConfig | None = None) -> GameState:
    resolved_config = _config() if config is None else config
    armies = _mustered_armies(resolved_config)
    state = GameState.from_config(resolved_config)
    for army in armies:
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase12b-battlefield",
        armies=armies,
    )
    state.record_battlefield_state(scenario.battlefield_state)
    while state.current_setup_step is not None:
        state.complete_current_setup_step()
    assert state.stage is GameLifecycleStage.BATTLE
    return state


def _config() -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id="phase12b-game",
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2025_26(
            descriptor_version="core-v2-phase12b-test"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_id="intercessor-unit-1",
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_id="enemy-unit",
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down", "cleanse"),
        mission_setup=MissionSetup.from_mission_pack(
            mission_pack=chapter_approved_2025_26_mission_pack(),
            mission_pool_entry_id="mission-a",
            terrain_layout_id="layout-1",
            attacker_player_id="player-a",
            defender_player_id="player-b",
        ),
    )


def _attached_unit_config() -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id="phase12b-attached-game",
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2025_26(
            descriptor_version="core-v2-phase12b-attached-test"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            ArmyMusterRequest(
                army_id="army-alpha",
                player_id="player-a",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id="core-marine-force",
                    detachment_id="core-combined-arms",
                ),
                unit_selections=(
                    UnitMusterSelection(
                        unit_selection_id="intercessor-unit-1",
                        datasheet_id="core-intercessor-like-infantry",
                        model_profile_selections=(
                            ModelProfileSelection(
                                model_profile_id="core-intercessor-like",
                                model_count=5,
                            ),
                        ),
                    ),
                    UnitMusterSelection(
                        unit_selection_id="captain-unit",
                        datasheet_id="core-character-leader",
                        model_profile_selections=(
                            ModelProfileSelection(
                                model_profile_id="core-character-leader",
                                model_count=1,
                            ),
                        ),
                    ),
                ),
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_id="enemy-unit",
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down", "cleanse"),
        mission_setup=MissionSetup.from_mission_pack(
            mission_pack=chapter_approved_2025_26_mission_pack(),
            mission_pool_entry_id="mission-a",
            terrain_layout_id="layout-1",
            attacker_player_id="player-a",
            defender_player_id="player-b",
        ),
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_id: str,
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
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
        ),
    )


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )


def _grant_cp(state: GameState, *, player_id: str, amount: int) -> None:
    result = state.gain_command_points(
        player_id=player_id,
        amount=amount,
        source_id=f"phase12b-grant:{player_id}:{amount}",
        source_kind=CommandPointSourceKind.COMMAND_PHASE_START,
    )
    assert result.status is CommandPointGainStatus.APPLIED


def _timing_window(
    *,
    state: GameState,
    trigger_kind: TimingTriggerKind,
    phase: BattlePhase,
    window_id: str,
) -> TimingWindow:
    descriptor = TimingWindowDescriptor(
        descriptor_id=f"{window_id}:descriptor",
        trigger_kind=trigger_kind,
        source_rule_id=f"{window_id}:source",
        phase=phase,
    )
    return TimingWindow(
        window_id=window_id,
        descriptor=descriptor,
        game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id=state.active_player_id,
        phase=phase,
        trigger_event_id="event-source-000001",
    )


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def _option_id_for_target(request: DecisionRequest, target_unit_instance_id: str) -> str:
    for option in request.options:
        payload = cast(dict[str, JsonValue], option.payload)
        binding = cast(dict[str, JsonValue], payload["target_binding"])
        if binding["target_unit_instance_id"] == target_unit_instance_id:
            return option.option_id
    raise AssertionError(f"Missing Stratagem option for target {target_unit_instance_id}.")


def _mark_attached_unit_join(
    state: GameState,
    *,
    player_id: str,
    attached_unit_instance_id: str,
    component_unit_instance_ids: tuple[str, ...],
) -> None:
    source_id = f"attached-unit-join:{attached_unit_instance_id}"
    component_id_set = set(component_unit_instance_ids)
    component_starting_model_count = 0
    updated_records: list[StartingStrengthRecord] = []
    for record in state.starting_strength_records:
        if record.unit_instance_id not in component_id_set:
            updated_records.append(record)
            continue
        component_starting_model_count += record.starting_model_count
        updated_records.append(replace(record, source_id=source_id))
    if component_starting_model_count == 0:
        raise AssertionError("Attached-unit test fixture did not find component records.")
    updated_records.append(
        StartingStrengthRecord(
            player_id=player_id,
            unit_instance_id=attached_unit_instance_id,
            starting_model_count=component_starting_model_count,
            single_model_starting_wounds=None,
            source_id=source_id,
        )
    )
    state.starting_strength_records = sorted(
        updated_records,
        key=lambda record: record.unit_instance_id,
    )


def _state(lifecycle: GameLifecycle) -> GameState:
    state = lifecycle.state
    assert state is not None
    return state


def _assert_no_pending(lifecycle: GameLifecycle) -> None:
    assert len(lifecycle.decision_controller.queue.pending_requests) == 0


def _set_current_battle_phase(state: GameState, phase: BattlePhase) -> None:
    state.battle_phase_index = state.battle_phase_sequence.index(phase)


def _lifecycle_payload_copy(lifecycle: GameLifecycle) -> GameLifecyclePayload:
    return cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )


def _game_state_payload_copy(state: GameState) -> GameStatePayload:
    return cast(GameStatePayload, json.loads(json.dumps(state.to_payload(), sort_keys=True)))


def _last_event_payload(
    decisions: DecisionController,
    event_type: str,
) -> dict[str, JsonValue]:
    for event in reversed(decisions.event_log.records):
        if event.event_type == event_type:
            return cast(dict[str, JsonValue], event.payload)
    raise AssertionError(f"Missing event type: {event_type}")
