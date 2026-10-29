from __future__ import annotations

from tests.factions.aeldari.army_rule_helpers import (
    _AELDARI_ASPECT_DATASHEET_ID,
    _AELDARI_ASPECT_MODEL_PROFILE_ID,
    _AELDARI_DETACHMENT_ID,
    _AELDARI_UNIT_ID,
    _AELDARI_UNIT_SELECTION_ID,
    _ASPECT_SHRINE_TOKEN_OPTION_ID,
    _ASPECT_SHRINE_TOKEN_WARGEAR_ID,
    _ENEMY_UNIT_ID,
    _OTHER_AELDARI_DETACHMENT_ID,
    ASPECT_SHRINE_TOKEN_RESOURCE_KIND,
    DICE_RESULT_OVERRIDE_DECISION_TYPE,
    DICE_RESULT_OVERRIDE_EVENT_TYPE,
    UNIT_RESOURCE_SPENT_EVENT_TYPE,
    ArmyMusteringError,
    ArmyMusterRequest,
    BattlePhase,
    DecisionController,
    DecisionResult,
    DiceExpression,
    DiceRollManager,
    DiceRollSpec,
    GameLifecycle,
    GameLifecycleError,
    GameLifecyclePayload,
    GameState,
    JsonValue,
    LifecycleStatusKind,
    ListValidationError,
    LocalGameSession,
    UnitResourceStatus,
    WargearSelection,
    _advance_to_movement_unit_selection,
    _aeldari_catalog,
    _aeldari_config,
    _army_muster_request,
    _aspect_shrine_lifecycle_override_request,
    _decision_request,
    _decline_stratagem_window_if_present,
    _event_payload,
    _state,
    apply_dice_result_override_decision,
    army_rule,
    cast,
    json,
    muster_army,
    pytest,
    replace,
    request_dice_result_override_if_available,
    spend_unit_resource,
    unit_resource_starting_total,
    unit_resource_total,
)


def test_aspect_shrine_tokens_seed_project_and_round_trip() -> None:
    config = _aeldari_config(aspect_shrine_token_count=2)
    lifecycle, _status = _advance_to_movement_unit_selection(config)
    state = _state(lifecycle)

    assert (
        unit_resource_starting_total(
            state=state,
            unit_instance_id=_AELDARI_UNIT_ID,
            resource_kind=ASPECT_SHRINE_TOKEN_RESOURCE_KIND,
        )
        == 2
    )
    assert (
        unit_resource_total(
            state=state,
            unit_instance_id=_AELDARI_UNIT_ID,
            resource_kind=ASPECT_SHRINE_TOKEN_RESOURCE_KIND,
        )
        == 2
    )
    assert GameState.from_payload(state.to_payload()).unit_resource_ledgers == (
        state.unit_resource_ledgers
    )
    view = LocalGameSession(lifecycle=lifecycle).view(viewer_player_id="player-a")
    assert view["unit_display_by_id"][_AELDARI_UNIT_ID]["resources"] == [
        {
            "resource_kind": ASPECT_SHRINE_TOKEN_RESOURCE_KIND,
            "starting_amount": 2,
            "remaining_amount": 2,
        }
    ]


@pytest.mark.parametrize(("model_count", "token_count"), [(4, 1), (5, 2), (10, 3)])
def test_aspect_shrine_token_wargear_selection_rejects_excessive_count(
    model_count: int,
    token_count: int,
) -> None:
    catalog = _aeldari_catalog(include_aspect_shrine_token=True)
    request = _army_muster_request(
        catalog=catalog,
        army_id="army-alpha",
        player_id="player-a",
        faction_id=army_rule.AELDARI_FACTION_ID,
        detachment_id=_AELDARI_DETACHMENT_ID,
        unit_selection_id=_AELDARI_UNIT_SELECTION_ID,
        datasheet_id=_AELDARI_ASPECT_DATASHEET_ID,
        model_profile_id=_AELDARI_ASPECT_MODEL_PROFILE_ID,
        model_count=model_count,
        wargear_selections=(
            WargearSelection(
                option_id=_ASPECT_SHRINE_TOKEN_OPTION_ID,
                model_profile_id=_AELDARI_ASPECT_MODEL_PROFILE_ID,
                wargear_ids=(_ASPECT_SHRINE_TOKEN_WARGEAR_ID,),
                selection_count=token_count,
            ),
        ),
    )

    with pytest.raises(ArmyMusteringError, match="unit selection is invalid"):
        muster_army(catalog=catalog, request=request)


def test_aspect_shrine_token_allocations_are_per_unit_and_detachment_independent() -> None:
    catalog = _aeldari_catalog(include_aspect_shrine_token=True)
    request = _army_muster_request(
        catalog=catalog,
        army_id="army-alpha",
        player_id="player-a",
        faction_id=army_rule.AELDARI_FACTION_ID,
        detachment_id=_OTHER_AELDARI_DETACHMENT_ID,
        unit_selection_id="aspect-unit-1",
        datasheet_id=_AELDARI_ASPECT_DATASHEET_ID,
        model_profile_id=_AELDARI_ASPECT_MODEL_PROFILE_ID,
        model_count=10,
        wargear_selections=(
            WargearSelection(
                option_id=_ASPECT_SHRINE_TOKEN_OPTION_ID,
                model_profile_id=_AELDARI_ASPECT_MODEL_PROFILE_ID,
                wargear_ids=(_ASPECT_SHRINE_TOKEN_WARGEAR_ID,),
                selection_count=2,
            ),
        ),
    )
    first_selection = request.unit_selections[0]
    request = replace(
        request,
        unit_selections=(
            first_selection,
            replace(first_selection, unit_selection_id="aspect-unit-2"),
        ),
    )

    army = muster_army(catalog=catalog, request=request)

    assert {
        unit.unit_instance_id: tuple(
            (allocation.resource_kind, allocation.amount) for allocation in unit.starting_resources
        )
        for unit in army.units
    } == {
        "army-alpha:aspect-unit-1": ((ASPECT_SHRINE_TOKEN_RESOURCE_KIND, 2),),
        "army-alpha:aspect-unit-2": ((ASPECT_SHRINE_TOKEN_RESOURCE_KIND, 2),),
    }


def test_unit_muster_payload_rejects_caller_supplied_starting_resources() -> None:
    request = _army_muster_request(
        catalog=_aeldari_catalog(include_aspect_shrine_token=True),
        army_id="army-alpha",
        player_id="player-a",
        faction_id=army_rule.AELDARI_FACTION_ID,
        detachment_id=_AELDARI_DETACHMENT_ID,
        unit_selection_id=_AELDARI_UNIT_SELECTION_ID,
        datasheet_id=_AELDARI_ASPECT_DATASHEET_ID,
        model_profile_id=_AELDARI_ASPECT_MODEL_PROFILE_ID,
        model_count=5,
    )
    payload = request.to_payload()
    selection_payload = cast(dict[str, object], payload["unit_selections"][0])
    selection_payload["starting_resources"] = [
        {"resource_kind": ASPECT_SHRINE_TOKEN_RESOURCE_KIND, "amount": 1000}
    ]

    with pytest.raises(ListValidationError, match="engine-derived from wargear choices"):
        ArmyMusterRequest.from_payload(payload)


def test_aspect_shrine_token_rehydration_rejects_resource_allocation_tampering() -> None:
    lifecycle, _status = _advance_to_movement_unit_selection(
        _aeldari_config(aspect_shrine_token_count=1)
    )
    unit_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload())),
    )
    alpha_army = unit_payload["state"]["army_definitions"][0]
    alpha_unit = next(
        unit for unit in alpha_army["units"] if unit["unit_instance_id"] == _AELDARI_UNIT_ID
    )
    alpha_unit["starting_resources"][0]["amount"] = 1000

    with pytest.raises(GameLifecycleError, match="army definitions do not match config"):
        GameLifecycle.from_payload(unit_payload)

    ledger_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload())),
    )
    ledger = ledger_payload["state"]["unit_resource_ledgers"][0]
    ledger["starting_resources"][ASPECT_SHRINE_TOKEN_RESOURCE_KIND] = 1000
    ledger["resources"][ASPECT_SHRINE_TOKEN_RESOURCE_KIND] = 1000
    ledger["transactions"][0]["amount"] = 1000

    with pytest.raises(GameLifecycleError, match="source-backed roster choices"):
        GameLifecycle.from_payload(ledger_payload)


def test_aspect_shrine_token_engine_decision_spends_and_records_override() -> None:
    config = _aeldari_config(aspect_shrine_token_count=2)
    lifecycle, _status = _advance_to_movement_unit_selection(config)
    state = _state(lifecycle)
    source_unit = next(
        unit
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == _AELDARI_UNIT_ID
    )
    attacker_model = source_unit.own_models[0]
    wargear = next(
        item
        for item in config.army_catalog.wargear
        if item.wargear_id in attacker_model.wargear_ids
    )
    profile = wargear.weapon_profiles[0]
    decisions = DecisionController()
    manager = DiceRollManager("aspect-shrine-token-test", event_log=decisions.event_log)
    roll_state = manager.roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason=f"{profile.profile_id} for Aspect Shrine Token test",
            roll_type="attack_sequence.hit",
            actor_id="player-a",
        )
    )
    request = request_dice_result_override_if_available(
        state=state,
        decisions=decisions,
        roll_state=roll_state,
        roll_type="hit",
        roll_successful=False,
        roll_critical=False,
        source_phase=BattlePhase.SHOOTING.value,
        sequence_id="aspect-token-sequence",
        attack_context_id="aspect-token-attack",
        pool_index=0,
        attack_index=0,
        attacking_unit_instance_id=_AELDARI_UNIT_ID,
        attacker_model_instance_id=attacker_model.model_instance_id,
        target_unit_instance_id=_ENEMY_UNIT_ID,
        weapon_profile_id=profile.profile_id,
        weapon_profile=profile,
        target_keywords=("INFANTRY",),
    )
    assert request is not None
    decisions.request_decision(request)
    result = DecisionResult.for_request(
        result_id="aspect-token-result",
        request=request,
        selected_option_id="use",
    )
    decisions.submit_result(result)
    apply_dice_result_override_decision(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
    )

    assert (
        unit_resource_total(
            state=state,
            unit_instance_id=_AELDARI_UNIT_ID,
            resource_kind=ASPECT_SHRINE_TOKEN_RESOURCE_KIND,
        )
        == 1
    )
    assert {event.event_type for event in decisions.event_log.records} >= {
        UNIT_RESOURCE_SPENT_EVENT_TYPE,
        DICE_RESULT_OVERRIDE_EVENT_TYPE,
    }


@pytest.mark.parametrize("replacement_value", [1, 6, 7])
def test_aspect_shrine_token_facade_use_resumes_assigned_hit(replacement_value: int) -> None:
    lifecycle, request = _aspect_shrine_lifecycle_override_request(
        replacement_value=replacement_value
    )

    status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="aspect-token-facade-use",
            request=request,
            selected_option_id="use",
        )
    )

    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert (
        unit_resource_total(
            state=_state(lifecycle),
            unit_instance_id=_AELDARI_UNIT_ID,
            resource_kind=ASPECT_SHRINE_TOKEN_RESOURCE_KIND,
        )
        == 0
    )
    override_payload = _event_payload(lifecycle, DICE_RESULT_OVERRIDE_EVENT_TYPE)
    updated_state = cast(dict[str, JsonValue], override_payload["updated_roll_state"])
    assert updated_state["current_values"] == [replacement_value]
    assert updated_state["current_total"] == replacement_value


@pytest.mark.parametrize("reroll", [False, True])
def test_twin_linked_precedes_wound_assignment_without_reopening_the_die(reroll: bool) -> None:
    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus

    lifecycle, request = _aspect_shrine_lifecycle_override_request(
        replacement_value=7, twin_linked=True
    )
    initial = lifecycle.to_payload()
    session = LocalGameSession(lifecycle)
    assert isinstance(request.payload, dict)
    roll_id = request.payload["roll_id"]
    status = session.submit_option(
        request_id=request.request_id,
        result_id="order96:before-assignment",
        option_id="reroll:0" if reroll else "decline",
    )
    status = _decline_stratagem_window_if_present(
        lifecycle, status, result_id="order96:decline-command-before-assignment"
    )
    assignment = _decision_request(status)
    assert assignment.decision_type == DICE_RESULT_OVERRIDE_DECISION_TYPE
    session = LocalGameSession(GameLifecycle.from_payload(lifecycle.to_payload()))
    status = session.submit_option(
        request_id=assignment.request_id, result_id="order96:assign-wound", option_id="use"
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    payload = _event_payload(session.lifecycle, DICE_RESULT_OVERRIDE_EVENT_TYPE)
    updated = cast(dict[str, JsonValue], payload["updated_roll_state"])
    assert cast(dict[str, JsonValue], updated["original_result"])["roll_id"] == roll_id
    assert updated["current_values"] == [7]
    assert len(cast(list[JsonValue], updated["rerolls"])) == int(reroll)
    choices = [
        row
        for row in session.lifecycle.decision_controller.records
        if row.request.decision_type == "select_dice_reroll"
        and isinstance(row.request.payload, dict)
        and row.request.payload["roll_id"] == roll_id
    ]
    assert len(choices) == 1
    pending = session.lifecycle.pending_decision_request()
    assert pending is None or not (
        pending.decision_type == "select_dice_reroll"
        and isinstance(pending.payload, dict)
        and pending.payload["roll_id"] == roll_id
    )
    replay = ReplayRunner.from_payload(
        ReplayArtifact.capture(
            artifact_id="order96-assignment",
            initial_lifecycle_payload=initial,
            final_lifecycle=session.lifecycle,
        ).to_payload()
    ).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay


def test_aspect_shrine_token_facade_rejects_resource_drift_without_popping_request() -> None:
    lifecycle, request = _aspect_shrine_lifecycle_override_request()
    state = _state(lifecycle)
    spend = spend_unit_resource(
        state=state,
        player_id="player-a",
        unit_instance_id=_AELDARI_UNIT_ID,
        resource_kind=ASPECT_SHRINE_TOKEN_RESOURCE_KIND,
        amount=1,
        source_rule_id="source:aeldari:aspect-shrine-token",
        decision_request_id="aspect-token-concurrent-request",
        decision_result_id="aspect-token-concurrent-result",
    )
    assert spend.status is UnitResourceStatus.APPLIED

    status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="aspect-token-stale-use",
            request=request,
            selected_option_id="use",
        )
    )

    assert status.status_kind is LifecycleStatusKind.INVALID
    invalid_payload = cast(dict[str, JsonValue], status.payload)
    assert invalid_payload["field"] == "current_count"
    assert lifecycle.decision_controller.queue.peek_next() == request
    assert (
        unit_resource_total(
            state=state,
            unit_instance_id=_AELDARI_UNIT_ID,
            resource_kind=ASPECT_SHRINE_TOKEN_RESOURCE_KIND,
        )
        == 0
    )
