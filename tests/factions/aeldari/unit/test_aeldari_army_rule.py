from __future__ import annotations

from tests.factions.aeldari.army_rule_helpers import (
    _AELDARI_FIGHT_DATASHEET_ID,
    _AELDARI_FIGHT_SQUAD_DATASHEET_ID,
    _AELDARI_UNIT_ID,
    _AELDARI_UNIT_SELECTION_ID,
    _ENEMY_UNIT_ID,
    _ENEMY_UNIT_SELECTION_ID,
    CONSOLIDATE_ACTION,
    DECLINE_MOVEMENT_ACTION_GRANT_OPTION_ID,
    FIGHT_ACTIVATION_ABILITY_DECISION_TYPE,
    FIGHT_ACTIVATION_DECISION_TYPE,
    FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND,
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_ACTION_GRANT_DECISION_TYPE,
    SUBMIT_MELEE_DECLARATION_DECISION_TYPE,
    SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
    BattlePhase,
    BattlePhaseKind,
    ChargeDeclarationContext,
    ConsolidationModeKind,
    DamageKind,
    DecisionError,
    DecisionResult,
    EffectExpirationKind,
    FightActivationAbilityContext,
    FightActivationSelection,
    FightEligibilityKind,
    FightMovementProposal,
    FightMovementStepState,
    FightOrderingBandKind,
    FightPhaseStepKind,
    FightTypeKind,
    JsonValue,
    LifecycleStatusKind,
    LocalGameSession,
    MeleeDeclarationProposalRequest,
    MovementEndSurgeContext,
    MovementEndSurgeGrant,
    MovementMode,
    MovementPhaseActionKind,
    MovementProposalRequest,
    ParameterizedSubmission,
    Pose,
    ProposalKind,
    ShootingType,
    WeaponKeyword,
    _advance_to_movement_unit_selection,
    _aeldari_config,
    _aeldari_vehicle_is_selectable_to_shoot,
    _decision_request,
    _decline_stratagem_window_if_present,
    _displacement_batch_for_unit,
    _drain_fight_movement_requests,
    _event_payload,
    _last_event_payload,
    _persisting_effects_for_unit_by_kind,
    _place_unit_poses,
    _prepared_aeldari_state_at_phase,
    _rehydrate_lifecycle_with_empty_decisions,
    _runtime_content_bundle,
    _select_aeldari_vehicle_for_movement,
    _shooting_declaration_request_for_aeldari_vehicle,
    _single_persisting_effect_for_unit_by_kind,
    _state,
    _unit_line_poses,
    _wahapedia_aeldari_battle_focus_row,
    apply_damage_to_model,
    army_rule,
    cast,
    fight_activation_option_id,
    fight_lifecycle,
    fight_movement_maximum_distance_inches,
    json,
    pytest,
    retain_destroyed_model_for_fixture,
    straight_line_witness_for_unit,
    submit_movement_proposal,
    unit_by_id,
)


def test_aeldari_battle_focus_agile_manoeuvres_text_is_source_backed_from_json() -> None:
    row = _wahapedia_aeldari_battle_focus_row()
    fields = cast(dict[str, JsonValue], row["fields"])
    description = cast(str, fields["description"])

    assert row["source_row_id"] == "000009894:AE"
    assert "AGILE MANOEUVRES\nSWIFT AS THE WIND" in description
    assert "FLITTING SHADOWS\nTRIGGER: When an eligible unit from your army" in description
    assert (
        "STAR ENGINES\n"
        "TRIGGER: When an eligible VEHICLE unit from your army is selected to make an "
        "Advance move.\n"
        "EFFECT: Until the end of the turn, Ranged weapons equipped by this unit have "
        "the [ASSAULT] ability."
    ) in description
    assert "SUDDEN STRIKE\nTRIGGER: When an eligible unit from your army is selected to fight." in (
        description
    )
    assert "OPPORTUNITY SEIZED\nTRIGGER: When an enemy unit ends a Fall Back move." in description
    assert "FADE BACK\nTRIGGER: In your opponent" in description
    assert "Shooting phase, just after an enemy unit has shot." in description


def test_aeldari_star_engines_grants_advanced_vehicle_assault_until_end_of_turn() -> None:
    config = _aeldari_config()
    lifecycle, movement_status = _advance_to_movement_unit_selection(config)
    bundle = _runtime_content_bundle(lifecycle)
    summary = bundle.to_summary_payload()
    assert {
        army_rule.SWIFT_AS_THE_WIND_HOOK_ID,
        army_rule.FLITTING_SHADOWS_HOOK_ID,
        army_rule.STAR_ENGINES_HOOK_ID,
    } <= set(summary["advance_move_hook_ids"])
    assert army_rule.OPPORTUNITY_SEIZED_HOOK_ID in summary["movement_end_surge_hook_ids"]
    assert army_rule.FLITTING_SHADOWS_HOOK_ID in summary["charge_declaration_hook_ids"]
    assert army_rule.FADE_BACK_HOOK_ID in summary["shooting_end_surge_hook_ids"]
    assert army_rule.SUDDEN_STRIKE_HOOK_ID in summary["fight_activation_ability_hook_ids"]

    action_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-aeldari-select-vehicle",
            request=_decision_request(movement_status),
            selected_option_id=_AELDARI_UNIT_ID,
        )
    )
    action_status = _decline_stratagem_window_if_present(
        lifecycle,
        action_status,
        result_id="phase17g-aeldari-decline-selected-to-move",
    )
    action_request = _decision_request(action_status)
    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE

    grant_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-aeldari-advance-action",
            request=action_request,
            selected_option_id=MovementPhaseActionKind.ADVANCE.value,
        )
    )
    grant_request = _decision_request(grant_status)
    assert grant_request.decision_type == SELECT_MOVEMENT_ACTION_GRANT_DECISION_TYPE
    assert {option.option_id for option in grant_request.options} == {
        DECLINE_MOVEMENT_ACTION_GRANT_OPTION_ID,
        army_rule.SWIFT_AS_THE_WIND_HOOK_ID,
        army_rule.FLITTING_SHADOWS_HOOK_ID,
        army_rule.HOOK_ID,
    }

    proposal_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-aeldari-star-engines",
            request=grant_request,
            selected_option_id=army_rule.HOOK_ID,
        )
    )
    proposal_request = _decision_request(proposal_status)
    assert proposal_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    advance_status = submit_movement_proposal(
        lifecycle,
        request=proposal_request,
        result_id="phase17g-aeldari-advance-proposal",
        unit_instance_id=_AELDARI_UNIT_ID,
        movement_phase_action=MovementPhaseActionKind.ADVANCE,
        movement_mode=MovementMode.ADVANCE,
        witness=straight_line_witness_for_unit(
            lifecycle,
            unit_instance_id=_AELDARI_UNIT_ID,
            dx=6.0,
        ),
    )
    _decline_stratagem_window_if_present(
        lifecycle,
        advance_status,
        result_id="phase17g-aeldari-decline-after-advance",
    )

    state = _state(lifecycle)
    advanced_state = state.advanced_unit_state_for_unit(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=_AELDARI_UNIT_ID,
    )
    assert advanced_state is not None
    assert not advanced_state.can_shoot

    spend_effect = _single_persisting_effect_for_unit_by_kind(
        state,
        _AELDARI_UNIT_ID,
        army_rule.BATTLE_FOCUS_TOKEN_SPENT_EFFECT_KIND,
    )
    spend_payload = cast(dict[str, JsonValue], spend_effect.effect_payload)
    assert spend_effect.source_rule_id == army_rule.SOURCE_RULE_ID
    assert spend_effect.owner_player_id == "player-a"
    assert spend_effect.expiration.expiration_kind is EffectExpirationKind.END_BATTLE_ROUND
    assert spend_payload == {
        "turn_player_id": "player-a",
        "effect_kind": army_rule.BATTLE_FOCUS_TOKEN_SPENT_EFFECT_KIND,
        "maneuver": army_rule.STAR_ENGINES_MANEUVER,
        "unit_instance_id": _AELDARI_UNIT_ID,
        "battle_focus_token_cost": 1,
        "movement_action_request_id": action_request.request_id,
        "movement_action_result_id": "phase17g-aeldari-advance-action",
    }

    grant_event = _event_payload(lifecycle, "movement_action_grant_decision_resolved")
    effect = _single_persisting_effect_for_unit_by_kind(
        state,
        _AELDARI_UNIT_ID,
        "ranged_weapon_keyword_grant",
    )
    effect_payload = cast(dict[str, JsonValue], effect.effect_payload)
    assert effect.source_rule_id == army_rule.SOURCE_RULE_ID
    assert effect.owner_player_id == "player-a"
    assert effect.target_unit_instance_ids == (_AELDARI_UNIT_ID,)
    assert effect.expiration.expiration_kind is EffectExpirationKind.END_TURN
    assert effect_payload == {
        "effect_kind": "ranged_weapon_keyword_grant",
        "granted_weapon_keywords": [WeaponKeyword.ASSAULT.value],
        "source_movement_request_id": action_request.request_id,
        "source_movement_result_id": "phase17g-aeldari-advance-action",
    }

    grants = cast(list[JsonValue], grant_event["selected_grants"])
    grant = cast(dict[str, JsonValue], grants[0])
    assert grant["hook_id"] == army_rule.HOOK_ID
    assert grant["source_id"] == army_rule.SOURCE_RULE_ID
    assert grant["label"] == "Battle Focus: Star Engines"
    assert grant["granted_ranged_weapon_keywords"] == [WeaponKeyword.ASSAULT.value]

    declaration_request = _shooting_declaration_request_for_aeldari_vehicle(
        state=state,
        config=config,
    )
    declaration_payload = cast(dict[str, JsonValue], declaration_request.payload)
    proposal = cast(dict[str, JsonValue], declaration_payload["proposal_request"])
    available_weapons = cast(list[JsonValue], proposal["available_weapons"])
    heavy_cannon = cast(dict[str, JsonValue], available_weapons[0])
    weapon_profile = cast(dict[str, JsonValue], heavy_cannon["weapon_profile"])

    assert declaration_request.decision_type == SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE
    assert proposal["selected_shooting_type"] == ShootingType.ASSAULT.value
    assert heavy_cannon["wargear_id"] == "core-heavy-cannon"
    assert weapon_profile["keywords"] == [
        WeaponKeyword.ASSAULT.value,
        WeaponKeyword.HEAVY.value,
    ]
    assert army_rule.SOURCE_RULE_ID in cast(list[JsonValue], weapon_profile["source_ids"])


def test_aeldari_star_engines_decline_does_not_grant_assault() -> None:
    config = _aeldari_config()
    lifecycle, movement_status = _advance_to_movement_unit_selection(config)
    action_request = _select_aeldari_vehicle_for_movement(lifecycle, movement_status)

    grant_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-aeldari-decline-advance-action",
            request=action_request,
            selected_option_id=MovementPhaseActionKind.ADVANCE.value,
        )
    )
    grant_request = _decision_request(grant_status)
    assert grant_request.decision_type == SELECT_MOVEMENT_ACTION_GRANT_DECISION_TYPE

    proposal_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-aeldari-decline-star-engines",
            request=grant_request,
            selected_option_id=DECLINE_MOVEMENT_ACTION_GRANT_OPTION_ID,
        )
    )
    proposal_request = _decision_request(proposal_status)
    assert proposal_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    advance_status = submit_movement_proposal(
        lifecycle,
        request=proposal_request,
        result_id="phase17g-aeldari-decline-advance-proposal",
        unit_instance_id=_AELDARI_UNIT_ID,
        movement_phase_action=MovementPhaseActionKind.ADVANCE,
        movement_mode=MovementMode.ADVANCE,
        witness=straight_line_witness_for_unit(
            lifecycle,
            unit_instance_id=_AELDARI_UNIT_ID,
            dx=6.0,
        ),
    )
    _decline_stratagem_window_if_present(
        lifecycle,
        advance_status,
        result_id="phase17g-aeldari-decline-after-declined-advance",
    )

    state = _state(lifecycle)
    assert (
        _persisting_effects_for_unit_by_kind(
            state,
            _AELDARI_UNIT_ID,
            army_rule.BATTLE_FOCUS_TOKEN_SPENT_EFFECT_KIND,
        )
        == ()
    )
    assert (
        _persisting_effects_for_unit_by_kind(
            state,
            _AELDARI_UNIT_ID,
            "ranged_weapon_keyword_grant",
        )
        == ()
    )
    assert not _aeldari_vehicle_is_selectable_to_shoot(state=state, config=config)


def test_aeldari_star_engines_rejects_invented_advance_grant_option() -> None:
    config = _aeldari_config()
    lifecycle, movement_status = _advance_to_movement_unit_selection(config)
    action_request = _select_aeldari_vehicle_for_movement(lifecycle, movement_status)

    grant_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-aeldari-invalid-advance-action",
            request=action_request,
            selected_option_id=MovementPhaseActionKind.ADVANCE.value,
        )
    )
    grant_request = _decision_request(grant_status)
    assert grant_request.decision_type == SELECT_MOVEMENT_ACTION_GRANT_DECISION_TYPE

    with pytest.raises(DecisionError):
        lifecycle.submit_decision(
            DecisionResult(
                result_id="phase17g-aeldari-invented-star-engines",
                request_id=grant_request.request_id,
                decision_type=grant_request.decision_type,
                actor_id=grant_request.actor_id,
                selected_option_id="invented_star_engines",
                payload={
                    "submission_kind": SELECT_MOVEMENT_ACTION_GRANT_DECISION_TYPE,
                    "unit_instance_id": _AELDARI_UNIT_ID,
                    "movement_phase_action": MovementPhaseActionKind.ADVANCE.value,
                    "movement_mode": MovementMode.ADVANCE.value,
                    "source_decision_request_id": action_request.request_id,
                    "source_decision_result_id": "phase17g-aeldari-invalid-advance-action",
                    "selected_movement_action_grants": [],
                },
            )
        )

    assert (
        _persisting_effects_for_unit_by_kind(
            _state(lifecycle),
            _AELDARI_UNIT_ID,
            army_rule.BATTLE_FOCUS_TOKEN_SPENT_EFFECT_KIND,
        )
        == ()
    )


@pytest.mark.parametrize("use_grant", [False, True])
def test_movement_grant_batch_restores_and_replays_through_the_session(use_grant: bool) -> None:
    from warhammer40k_core.adapters.event_stream import EventStreamCursor
    from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
    from warhammer40k_core.engine.timing_batch_runtime import timing_batch_from_event

    session = LocalGameSession()
    lifecycle, status = _advance_to_movement_unit_selection(_aeldari_config(), session=session)
    action = _select_aeldari_vehicle_for_movement(lifecycle, status)
    status = session.submit_option(
        request_id=action.request_id,
        option_id=MovementPhaseActionKind.ADVANCE.value,
        result_id="grant-batch:advance",
    )
    request = _decision_request(status)
    assert request.decision_type == SELECT_MOVEMENT_ACTION_GRANT_DECISION_TYPE
    assert isinstance(request.payload, dict)
    assert request.payload["source_decision_result_id"] == "grant-batch:advance"
    participant_id = request.payload["timing_participant_id"]
    for player_id in ("player-a", "player-b"):
        assert session.view(viewer_player_id=player_id)["pending_decision"] is not None
        assert "timing_batch_transition" not in json.dumps(
            session.events_since(EventStreamCursor(), viewer_player_id=player_id)
        )
    session = session.fork()
    assert session.lifecycle.pending_decision_request() == request
    status = session.submit_option(
        request_id=request.request_id,
        option_id=army_rule.STAR_ENGINES_HOOK_ID
        if use_grant
        else DECLINE_MOVEMENT_ACTION_GRANT_OPTION_ID,
        result_id="grant-batch:answer",
    )
    assert _decision_request(status).decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    decisions = session.lifecycle.decision_controller
    assert (
        sum(
            event.event_type == "movement_action_grant_decision_resolved"
            and isinstance(event.payload, dict)
            and event.payload.get("timing_participant_id") == participant_id
            for event in decisions.event_log.records
        )
        == 1
    )
    batch = next(
        timing_batch_from_event(event)
        for event in reversed(decisions.event_log.records)
        if event.event_type == "timing_batch_transition"
    )
    assert batch.current_batch_complete
    assert participant_id in batch.completed_participant_ids
    replay = ReplayRunner.from_payload(
        session.replay_artifact(artifact_id=f"grant-batch:{use_grant}")
    ).run()
    assert replay.status is ReplayRunStatus.REPRODUCED


def test_aeldari_swift_as_the_wind_adds_two_inches_to_normal_move() -> None:
    config = _aeldari_config()
    lifecycle, movement_status = _advance_to_movement_unit_selection(config)
    action_request = _select_aeldari_vehicle_for_movement(lifecycle, movement_status)

    grant_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-aeldari-swift-normal-action",
            request=action_request,
            selected_option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        )
    )
    grant_request = _decision_request(grant_status)
    assert grant_request.decision_type == SELECT_MOVEMENT_ACTION_GRANT_DECISION_TYPE
    assert {option.option_id for option in grant_request.options} == {
        DECLINE_MOVEMENT_ACTION_GRANT_OPTION_ID,
        army_rule.SWIFT_AS_THE_WIND_HOOK_ID,
        army_rule.FLITTING_SHADOWS_HOOK_ID,
    }

    proposal_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-aeldari-swift-selected",
            request=grant_request,
            selected_option_id=army_rule.SWIFT_AS_THE_WIND_HOOK_ID,
        )
    )
    proposal_request = _decision_request(proposal_status)
    assert proposal_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE

    move_status = submit_movement_proposal(
        lifecycle,
        request=proposal_request,
        result_id="phase17g-aeldari-swift-move-proposal",
        unit_instance_id=_AELDARI_UNIT_ID,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
        movement_mode=MovementMode.NORMAL,
        witness=straight_line_witness_for_unit(
            lifecycle,
            unit_instance_id=_AELDARI_UNIT_ID,
            dx=12.0,
        ),
    )
    _decline_stratagem_window_if_present(
        lifecycle,
        move_status,
        result_id="phase17g-aeldari-decline-after-swift",
    )

    state = _state(lifecycle)
    agile_effect = _single_persisting_effect_for_unit_by_kind(
        state,
        _AELDARI_UNIT_ID,
        army_rule.AGILE_MANOEUVRE_EFFECT_KIND,
    )
    payload = cast(dict[str, JsonValue], agile_effect.effect_payload)
    assert agile_effect.expiration.expiration_kind is EffectExpirationKind.END_PHASE
    assert payload["maneuver"] == army_rule.SWIFT_AS_THE_WIND_MANEUVER
    assert payload["movement_bonus_inches"] == 2


def test_aeldari_flitting_shadows_movement_blocks_fire_overwatch_until_end_of_turn() -> None:
    config = _aeldari_config()
    lifecycle, movement_status = _advance_to_movement_unit_selection(config)
    action_request = _select_aeldari_vehicle_for_movement(lifecycle, movement_status)

    grant_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-aeldari-flitting-normal-action",
            request=action_request,
            selected_option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        )
    )
    grant_request = _decision_request(grant_status)
    proposal_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-aeldari-flitting-selected",
            request=grant_request,
            selected_option_id=army_rule.FLITTING_SHADOWS_HOOK_ID,
        )
    )
    proposal_request = _decision_request(proposal_status)
    move_status = submit_movement_proposal(
        lifecycle,
        request=proposal_request,
        result_id="phase17g-aeldari-flitting-move-proposal",
        unit_instance_id=_AELDARI_UNIT_ID,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
        movement_mode=MovementMode.NORMAL,
        witness=straight_line_witness_for_unit(
            lifecycle,
            unit_instance_id=_AELDARI_UNIT_ID,
            dx=6.0,
        ),
    )
    _decline_stratagem_window_if_present(
        lifecycle,
        move_status,
        result_id="phase17g-aeldari-decline-after-flitting",
    )

    effect = _single_persisting_effect_for_unit_by_kind(
        _state(lifecycle),
        _AELDARI_UNIT_ID,
        army_rule.AGILE_MANOEUVRE_EFFECT_KIND,
    )
    payload = cast(dict[str, JsonValue], effect.effect_payload)
    assert effect.expiration.expiration_kind is EffectExpirationKind.END_TURN
    assert payload["maneuver"] == army_rule.FLITTING_SHADOWS_MANEUVER
    assert payload["fire_overwatch_forbidden"] is True


def test_aeldari_flitting_shadows_charge_declaration_grant_blocks_overwatch() -> None:
    charge_state = _prepared_aeldari_state_at_phase(BattlePhase.CHARGE)
    context = ChargeDeclarationContext(
        state=charge_state,
        player_id="player-a",
        battle_round=charge_state.battle_round,
        unit_instance_id=_AELDARI_UNIT_ID,
        selection_request_id="phase17g-aeldari-charge-select-request",
        selection_result_id="phase17g-aeldari-charge-select-result",
    )

    grant = army_rule.flitting_shadows_charge_declaration_grant(context)

    assert grant is not None
    assert grant.hook_id == army_rule.FLITTING_SHADOWS_HOOK_ID
    assert grant.unit_effect_expiration == "end_turn"
    payload = cast(dict[str, JsonValue], grant.unit_effect_payload)
    assert payload["maneuver"] == army_rule.FLITTING_SHADOWS_MANEUVER
    assert payload["fire_overwatch_forbidden"] is True


def test_aeldari_sudden_strike_fight_option_extends_pile_in_and_consolidation() -> None:
    fight_state = _prepared_aeldari_state_at_phase(BattlePhase.FIGHT)
    activation = FightActivationSelection(
        player_id="player-a",
        battle_round=fight_state.battle_round,
        unit_instance_id=_AELDARI_UNIT_ID,
        ordering_band=FightOrderingBandKind.REMAINING_COMBATS,
        fight_type=FightTypeKind.NORMAL,
        eligibility_reasons=(FightEligibilityKind.CURRENTLY_ENGAGED,),
        request_id="phase17g-aeldari-fight-activation-request",
        result_id="phase17g-aeldari-fight-activation-result",
    )
    context = FightActivationAbilityContext(
        state=fight_state,
        game_id=fight_state.game_id,
        battle_round=fight_state.battle_round,
        active_player_id="player-a",
        player_id="player-a",
        unit_instance_id=_AELDARI_UNIT_ID,
        activation=activation,
        target_unit_instance_ids=(_ENEMY_UNIT_ID,),
    )

    option = army_rule.sudden_strike_fight_activation_option(context)

    assert option is not None
    assert option.hook_id == army_rule.SUDDEN_STRIKE_HOOK_ID
    assert option.ability_id == army_rule.SUDDEN_STRIKE_MANEUVER
    assert option.effect_kind == FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND
    assert option.model_proximity_inches is None
    assert option.pile_in_distance_inches == 6.0
    assert option.consolidate_distance_inches == 6.0
    spend_payload = cast(dict[str, JsonValue], option.decision_effect_payload)
    assert spend_payload["maneuver"] == army_rule.SUDDEN_STRIKE_MANEUVER
    assert spend_payload["battle_focus_token_cost"] == 1


def test_aeldari_sudden_strike_fight_movement_distance_uses_lifecycle_effect() -> None:
    config = _aeldari_config(
        aeldari_datasheet_id=_AELDARI_FIGHT_DATASHEET_ID,
        aeldari_model_profile_id="core-character-leader",
    )
    lifecycle, _units = fight_lifecycle(
        alpha_unit_ids=(_AELDARI_UNIT_SELECTION_ID,),
        enemy_unit_ids=(_ENEMY_UNIT_SELECTION_ID,),
        origins={
            _AELDARI_UNIT_SELECTION_ID: Pose.at(10.0, 20.0),
            _ENEMY_UNIT_SELECTION_ID: Pose.at(12.15, 20.0, facing_degrees=180.0),
        },
        game_id=config.game_id,
        config=config,
    )
    lifecycle = _rehydrate_lifecycle_with_empty_decisions(lifecycle)
    state = _state(lifecycle)
    bundle = _runtime_content_bundle(lifecycle)
    summary = bundle.to_summary_payload()

    assert army_rule.SUDDEN_STRIKE_HOOK_ID in summary["fight_activation_ability_hook_ids"]

    activation_request = _decision_request(
        _drain_fight_movement_requests(
            lifecycle,
            lifecycle.advance_until_decision_or_terminal(),
        )
    )
    assert activation_request.decision_type == FIGHT_ACTIVATION_DECISION_TYPE

    ability_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-aeldari-sudden-strike-activation",
            request=activation_request,
            selected_option_id=fight_activation_option_id(
                unit_instance_id=_AELDARI_UNIT_ID,
                fight_type=FightTypeKind.NORMAL,
            ),
        )
    )
    ability_request = _decision_request(ability_status)
    assert ability_request.decision_type == FIGHT_ACTIVATION_ABILITY_DECISION_TYPE

    melee_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-aeldari-sudden-strike-use",
            request=ability_request,
            selected_option_id=f"use:{army_rule.SUDDEN_STRIKE_MANEUVER}",
        )
    )
    assert melee_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION

    state = _state(lifecycle)
    activation_fight_state = state.fight_phase_state
    assert activation_fight_state is not None
    for kind in (ProposalKind.PILE_IN, ProposalKind.CONSOLIDATE):
        assert (
            fight_movement_maximum_distance_inches(
                state=state, unit_instance_id=_AELDARI_UNIT_ID, proposal_kind=kind
            )
            == 3.0
        )
    state.replace_fight_phase_state(
        activation_fight_state.with_current_step(
            current_step=FightPhaseStepKind.PILE_IN,
            policy=state.runtime_ruleset_descriptor().fight_policy,
        )
    )
    assert (
        fight_movement_maximum_distance_inches(
            state=state,
            unit_instance_id=_AELDARI_UNIT_ID,
            proposal_kind=ProposalKind.PILE_IN,
        )
        == 6.0
    )
    state.replace_fight_phase_state(
        activation_fight_state.with_current_step(
            current_step=FightPhaseStepKind.CONSOLIDATE,
            policy=state.runtime_ruleset_descriptor().fight_policy,
        )
    )
    assert (
        fight_movement_maximum_distance_inches(
            state=state,
            unit_instance_id=_AELDARI_UNIT_ID,
            proposal_kind=ProposalKind.CONSOLIDATE,
        )
        == 6.0
    )
    state.replace_fight_phase_state(activation_fight_state)
    used_event = _last_event_payload(lifecycle, "fight_activation_ability_used")
    persisting_effect = cast(dict[str, JsonValue], used_event["persisting_effect"])
    effect_payload = cast(dict[str, JsonValue], persisting_effect["effect_payload"])
    assert effect_payload["effect_kind"] == FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND
    assert effect_payload["pile_in_distance_inches"] == 6.0
    assert effect_payload["consolidate_distance_inches"] == 6.0

    _place_unit_poses(
        state,
        unit_instance_id=_AELDARI_UNIT_ID,
        poses=(Pose.at(10.0, 20.0, 0.0),),
    )
    _place_unit_poses(
        state,
        unit_instance_id=_ENEMY_UNIT_ID,
        poses=_unit_line_poses(x=14.0, y=20.0),
    )
    fight_state = state.fight_phase_state
    assert fight_state is not None
    policy = state.runtime_ruleset_descriptor().fight_policy
    state.replace_fight_phase_state(
        fight_state.with_active_activation(None)
        .with_consolidate_state(
            FightMovementStepState.start(
                step=FightPhaseStepKind.CONSOLIDATE,
                next_player_id="player-a",
            )
        )
        .with_current_step(current_step=FightPhaseStepKind.CONSOLIDATE, policy=policy)
    )
    lifecycle = _rehydrate_lifecycle_with_empty_decisions(lifecycle)
    consolidate_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    proposal_request = MovementProposalRequest.from_decision_request_payload(
        consolidate_request.payload
    )
    assert proposal_request.proposal_kind is ProposalKind.CONSOLIDATE
    assert proposal_request.context is not None
    assert proposal_request.context["maximum_distance_inches"] == 6.0

    consolidate_status = lifecycle.submit_decision(
        ParameterizedSubmission(
            request_id=consolidate_request.request_id,
            result_id="phase17g-aeldari-sudden-strike-consolidate",
            payload=cast(
                JsonValue,
                FightMovementProposal(
                    proposal_request_id=proposal_request.request_id,
                    proposal_kind=ProposalKind.CONSOLIDATE,
                    unit_instance_id=_AELDARI_UNIT_ID,
                    movement_phase_action=CONSOLIDATE_ACTION,
                    movement_mode=MovementMode.CONSOLIDATE,
                    consolidation_mode=ConsolidationModeKind.ENGAGING,
                    consolidate_target_unit_instance_ids=(_ENEMY_UNIT_ID,),
                    witness=straight_line_witness_for_unit(
                        lifecycle,
                        unit_instance_id=_AELDARI_UNIT_ID,
                        dx=2.5,
                        dy=2.0,
                    ),
                ).to_payload(),
            ),
        ).to_result(consolidate_request)
    )

    completed_event = _last_event_payload(lifecycle, "fight_movement_completed")
    resolution = cast(dict[str, JsonValue], completed_event["resolution"])
    endpoint_state = _state(lifecycle)
    assert endpoint_state.battlefield_state is not None
    assert consolidate_status.status_kind is not LifecycleStatusKind.INVALID
    assert completed_event["result_id"] == "phase17g-aeldari-sudden-strike-consolidate"
    assert completed_event["active_player_id"] == "player-a"
    assert completed_event["movement_endpoint_placement"] == (
        endpoint_state.battlefield_state.unit_placement_by_id(_AELDARI_UNIT_ID).to_payload()
    )
    assert resolution["maximum_distance_inches"] == 6.0


def test_retained_only_aeldari_keeps_sudden_strike_and_pending_attacks() -> None:
    config = _aeldari_config(
        aeldari_datasheet_id=_AELDARI_FIGHT_DATASHEET_ID,
        aeldari_model_profile_id="core-character-leader",
    )
    lifecycle, _units = fight_lifecycle(
        alpha_unit_ids=(_AELDARI_UNIT_SELECTION_ID,),
        enemy_unit_ids=(_ENEMY_UNIT_SELECTION_ID,),
        origins={
            _AELDARI_UNIT_SELECTION_ID: Pose.at(10.0, 20.0),
            _ENEMY_UNIT_SELECTION_ID: Pose.at(12.15, 20.0, facing_degrees=180.0),
        },
        game_id=config.game_id,
        config=config,
    )
    lifecycle = _rehydrate_lifecycle_with_empty_decisions(lifecycle)
    state = _state(lifecycle)
    fighter = unit_by_id(state=state, unit_instance_id=_AELDARI_UNIT_ID)
    model = fighter.own_models[0]
    battlefield = state.battlefield_state
    assert battlefield is not None
    retained_placement = battlefield.model_placement_by_id(model.model_instance_id)
    apply_damage_to_model(
        state=state,
        target_unit_instance_id=fighter.unit_instance_id,
        model_instance_id=model.model_instance_id,
        damage=model.current_wounds,
        damage_kind=DamageKind.NORMAL,
    )
    retain_destroyed_model_for_fixture(
        decisions=lifecycle.decision_controller,
        state=state,
        placement=retained_placement,
        effect_id="phase17g:aeldari:sudden-strike:retained-only",
        source_rule_id="phase17g:test:fight-on-death",
        source_phase=BattlePhaseKind.FIGHT,
    )

    activation_request = _decision_request(
        _drain_fight_movement_requests(
            lifecycle,
            lifecycle.advance_until_decision_or_terminal(),
        )
    )
    assert activation_request.decision_type == FIGHT_ACTIVATION_DECISION_TYPE
    melee_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-aeldari-retained-only-activation",
            request=activation_request,
            selected_option_id=fight_activation_option_id(
                unit_instance_id=_AELDARI_UNIT_ID,
                fight_type=FightTypeKind.NORMAL,
            ),
        )
    )
    melee_status = _decline_stratagem_window_if_present(
        lifecycle,
        melee_status,
        result_id="phase17g-aeldari-retained-only-decline-stratagem",
    )
    melee_request = _decision_request(melee_status)

    assert melee_request.decision_type == FIGHT_ACTIVATION_ABILITY_DECISION_TYPE
    melee_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            request=melee_request,
            result_id="retained-sudden-strike-selected",
            selected_option_id=f"use:{army_rule.SUDDEN_STRIKE_MANEUVER}",
        )
    )
    melee_request = _decision_request(melee_status)
    assert melee_request.decision_type == SUBMIT_MELEE_DECLARATION_DECISION_TYPE
    proposal_request = MeleeDeclarationProposalRequest.from_decision_request(melee_request)
    assert {
        cast(str, cast(dict[str, JsonValue], row)["model_instance_id"])
        for row in proposal_request.available_weapons
    } == {model.model_instance_id}
    assert any(
        event.event_type == "fight_activation_ability_requested"
        for event in lifecycle.decision_controller.event_log.records
    )


def test_mixed_aeldari_with_retained_model_keeps_sudden_strike_authority() -> None:
    config = _aeldari_config(
        aeldari_datasheet_id=_AELDARI_FIGHT_SQUAD_DATASHEET_ID,
        aeldari_model_profile_id="core-intercessor-like",
        aeldari_model_count=5,
    )
    lifecycle, _units = fight_lifecycle(
        alpha_unit_ids=(_AELDARI_UNIT_SELECTION_ID,),
        enemy_unit_ids=(_ENEMY_UNIT_SELECTION_ID,),
        origins={
            _AELDARI_UNIT_SELECTION_ID: Pose.at(10.0, 20.0),
            _ENEMY_UNIT_SELECTION_ID: Pose.at(12.15, 20.0, facing_degrees=180.0),
        },
        game_id=config.game_id,
        config=config,
    )
    lifecycle = _rehydrate_lifecycle_with_empty_decisions(lifecycle)
    state = _state(lifecycle)
    _place_unit_poses(
        state,
        unit_instance_id=_AELDARI_UNIT_ID,
        poses=_unit_line_poses(x=10.0, y=20.0),
    )
    _place_unit_poses(
        state,
        unit_instance_id=_ENEMY_UNIT_ID,
        poses=_unit_line_poses(x=12.15, y=20.0),
    )
    fighter = unit_by_id(state=state, unit_instance_id=_AELDARI_UNIT_ID)
    destroyed_model = fighter.own_models[-1]
    battlefield = state.battlefield_state
    assert battlefield is not None
    retained_placement = battlefield.model_placement_by_id(destroyed_model.model_instance_id)
    apply_damage_to_model(
        state=state,
        target_unit_instance_id=fighter.unit_instance_id,
        model_instance_id=destroyed_model.model_instance_id,
        damage=destroyed_model.current_wounds,
        damage_kind=DamageKind.NORMAL,
    )
    retain_destroyed_model_for_fixture(
        decisions=lifecycle.decision_controller,
        state=state,
        placement=retained_placement,
        effect_id="phase17g:aeldari:sudden-strike:mixed",
        source_rule_id="phase17g:test:fight-on-death",
        source_phase=BattlePhaseKind.FIGHT,
    )

    activation_request = _decision_request(
        _drain_fight_movement_requests(
            lifecycle,
            lifecycle.advance_until_decision_or_terminal(),
        )
    )
    ability_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-aeldari-mixed-activation",
            request=activation_request,
            selected_option_id=fight_activation_option_id(
                unit_instance_id=_AELDARI_UNIT_ID,
                fight_type=FightTypeKind.NORMAL,
            ),
        )
    )

    ability_request = _decision_request(ability_status)
    assert ability_request.decision_type == FIGHT_ACTIVATION_ABILITY_DECISION_TYPE
    assert f"use:{army_rule.SUDDEN_STRIKE_MANEUVER}" in {
        option.option_id for option in ability_request.options
    }


def test_opportunity_seized_requires_living_unit_but_measures_retained_physical_base() -> None:
    def grants_for_state(*, destroy_all: bool) -> tuple[MovementEndSurgeGrant, ...]:
        config = _aeldari_config(aspect_shrine_token_count=1)
        lifecycle, _movement_status = _advance_to_movement_unit_selection(config)
        state = _state(lifecycle)
        friendly_poses = (
            Pose.at(20.0, 20.0),
            Pose.at(40.0, 20.0),
            Pose.at(40.0, 22.0),
            Pose.at(40.0, 24.0),
            Pose.at(40.0, 26.0),
        )
        _place_unit_poses(
            state,
            unit_instance_id=_AELDARI_UNIT_ID,
            poses=friendly_poses,
        )
        enemy_start_poses = _unit_line_poses(x=22.0, y=20.0)
        enemy_end_poses = _unit_line_poses(x=34.0, y=20.0)
        _place_unit_poses(state, unit_instance_id=_ENEMY_UNIT_ID, poses=enemy_end_poses)
        transition_batch = _displacement_batch_for_unit(
            state=state,
            unit_instance_id=_ENEMY_UNIT_ID,
            start_poses=enemy_start_poses,
            end_poses=enemy_end_poses,
        )
        friendly_unit = unit_by_id(state=state, unit_instance_id=_AELDARI_UNIT_ID)
        battlefield = state.battlefield_state
        assert battlefield is not None
        retained_model = friendly_unit.own_models[0]
        retained_placement = battlefield.model_placement_by_id(retained_model.model_instance_id)
        models_to_destroy = friendly_unit.own_models if destroy_all else (retained_model,)
        for model in models_to_destroy:
            apply_damage_to_model(
                state=state,
                target_unit_instance_id=friendly_unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                damage=model.current_wounds,
                damage_kind=DamageKind.NORMAL,
            )
        retain_destroyed_model_for_fixture(
            decisions=lifecycle.decision_controller,
            state=state,
            placement=retained_placement,
            effect_id=(
                "phase17g:aeldari:opportunity-seized:retained-only"
                if destroy_all
                else "phase17g:aeldari:opportunity-seized:mixed"
            ),
            source_rule_id="phase17g:test:fight-on-death",
            source_phase=BattlePhaseKind.MOVEMENT,
        )
        return army_rule.opportunity_seized_surge_grants(
            MovementEndSurgeContext(
                state=state,
                ruleset_descriptor=config.ruleset_descriptor,
                triggering_unit_instance_id=_ENEMY_UNIT_ID,
                triggering_player_id="player-b",
                reacting_player_id="player-a",
                trigger_event_id=(
                    "phase17g-aeldari-retained-only-fall-back"
                    if destroy_all
                    else "phase17g-aeldari-mixed-fall-back"
                ),
                movement_phase_action=MovementPhaseActionKind.FALL_BACK.value,
                trigger_event_payload={
                    "transition_batch": cast(JsonValue, transition_batch.to_payload())
                },
            )
        )

    assert grants_for_state(destroy_all=True) == ()
    mixed_grants = grants_for_state(destroy_all=False)
    assert len(mixed_grants) == 1
    assert mixed_grants[0].unit_instance_id == _AELDARI_UNIT_ID
