from __future__ import annotations

from typing import cast

from tests.shared.category_migration.secondary_scoring_state_evidence_authority import (
    _AUTHORITY_DRIFT_ERROR,
    _LAYOUT_ROW,
    _SCORING_PLAYER_ID,
    SCORING_COMMIT_CHECKPOINT_HASH_KEY,
    SCORING_COMMIT_CHECKPOINT_ID_KEY,
    SECONDARY_SCORING_STATE_EVIDENCE_HASH_KEY,
    SECONDARY_SCORING_STATE_EVIDENCE_ID_KEY,
    BattlefieldRemovalKind,
    BattlePhase,
    Callable,
    DecisionController,
    EvidenceTransactionMutation,
    GameLifecycleError,
    GameState,
    GameStatePayload,
    JsonValue,
    ModelPlacement,
    Pose,
    PrimaryBattlefieldDepartureState,
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionChoice,
    SecondaryMissionLifecycleCertificationRow,
    SecondaryMissionMode,
    SecondaryScoringStateEvidencePayload,
    UnitInstance,
    UnitMusterSelection,
    VictoryPointLedgerPayload,
    VictoryPointSourceKind,
    VictoryPointTransaction,
    VictoryPointTransactionPayload,
    _authority_unit_selections,
    _coordinated_rehash,
    _empty_rule_evidence,
    _intercessors,
    _place_near_unit,
    _place_unit_at,
    _reduce_engage_presence_to_three_quarters,
    _rehash_primary_evidence_with_destruction,
    _replace_single_rule_projection,
    _required_metadata,
    _required_object,
    _required_string_list,
    _scored_secondary_state,
    _secondary_transaction,
    _secondary_transaction_payload,
    active_player_id_for_row,
    canonical_json,
    canonical_payload_sha256,
    copy,
    deepcopy,
    default_unit_selection,
    event_companion_pairing_lifecycle_certification_rows,
    phase17n_event_setup,
    phase17n_state_with_setup,
    primary_battlefield_departure_id,
    primary_unit_destruction_id,
    pytest,
    record_primary_turn_start_evidence_for_fixture,
    replace,
    resolved_secondary_mission_selection_for_card,
    secondary_unit_destruction_from_primary,
    seed_positive_secondary_condition,
    unit_selection,
)


def test_engage_three_quarters_cannot_be_rehashed_as_four() -> None:
    state = _scored_secondary_state(
        "engage-on-all-fronts",
        after_positive_seed=_reduce_engage_presence_to_three_quarters,
    )
    transaction = _secondary_transaction(state, secondary_mission_id="engage-on-all-fronts")
    assert transaction.amount == 3

    payload = deepcopy(state.to_payload())
    GameState.from_payload(deepcopy(payload))

    def rewrite_as_four_quarters(
        evidence: SecondaryScoringStateEvidencePayload,
        transaction_payload: VictoryPointTransactionPayload,
    ) -> None:
        occupancy = _required_object(evidence["occupancy"], name="Engage occupancy")
        quarter_ids = _required_string_list(
            occupancy.get("presence_quarter_ids"),
            name="Engage presence quarters",
        )
        missing = tuple(
            quarter_id
            for quarter_id in (
                "table-quarter:north-east",
                "table-quarter:north-west",
                "table-quarter:south-east",
                "table-quarter:south-west",
            )
            if quarter_id not in quarter_ids
        )
        assert len(missing) == 1
        occupancy["presence_quarter_ids"] = sorted((*quarter_ids, missing[0]))
        _replace_single_rule_projection(
            evidence=evidence,
            transaction=transaction_payload,
            rule_id="engage-on-all-fronts-tactical-four-quarters",
            condition="presence_in_four_table_quarters",
            source_id=(
                "gw-11e-warhammer-event-companion-v1-1-2026-07:secondary:"
                "engage-on-all-fronts:scoring-rule:"
                "engage-on-all-fronts-tactical-four-quarters"
            ),
            amount=5,
            rule_evidence=_empty_rule_evidence(),
        )

    _coordinated_rehash(
        payload,
        secondary_mission_id="engage-on-all-fronts",
        mutate=rewrite_as_four_quarters,
    )

    with pytest.raises(GameLifecycleError, match=_AUTHORITY_DRIFT_ERROR):
        GameState.from_payload(payload)


def test_bring_it_down_cannot_insert_a_rehashed_fabricated_destruction() -> None:
    state = _scored_secondary_state("bring-it-down")
    transaction = _secondary_transaction(state, secondary_mission_id="bring-it-down")
    assert transaction.amount == 5

    payload = deepcopy(state.to_payload())
    GameState.from_payload(deepcopy(payload))

    def insert_fabricated_destruction(
        evidence: SecondaryScoringStateEvidencePayload,
        transaction_payload: VictoryPointTransactionPayload,
    ) -> None:
        assert len(evidence["unit_destruction_states"]) == 1
        fabricated = deepcopy(evidence["unit_destruction_states"][0])
        fabricated_unit_id = "fabricated-destroyed-infantry-unit"
        fabricated["destruction_id"] = "secondary-destruction:fabricated-infantry"
        fabricated["source_primary_destruction_id"] = "primary-destruction:fabricated-infantry"
        fabricated["destroyed_unit_instance_id"] = fabricated_unit_id
        fabricated["destroyed_models"] = [
            {
                "model_instance_id": "fabricated-destroyed-infantry-model",
                "starting_wounds": 1,
            }
        ]
        fabricated["started_turn_objective_marker_ids"] = []
        fabricated["source_id"] = "secondary-destruction-source:fabricated-infantry"
        evidence["unit_destruction_states"].append(fabricated)

        metadata = _required_metadata(transaction_payload)
        evidence_by_rule = _required_object(
            metadata.get("evidence_by_rule"),
            name="Bring It Down evidence_by_rule",
        )
        rule_evidence = _required_object(
            evidence_by_rule.get("bring-it-down-tactical"),
            name="Bring It Down rule evidence",
        )
        destroyed_unit_ids = _required_string_list(
            rule_evidence.get("destroyed_unit_instance_ids"),
            name="Bring It Down destroyed units",
        )
        rule_evidence["destroyed_unit_instance_ids"] = [
            *destroyed_unit_ids,
            fabricated_unit_id,
        ]

    _coordinated_rehash(
        payload,
        secondary_mission_id="bring-it-down",
        mutate=insert_fabricated_destruction,
    )

    with pytest.raises(GameLifecycleError, match=_AUTHORITY_DRIFT_ERROR):
        GameState.from_payload(payload)


def test_bring_it_down_cannot_rehash_a_fabricated_primary_destruction() -> None:
    state = _scored_secondary_state("bring-it-down")
    transaction = _secondary_transaction(state, secondary_mission_id="bring-it-down")
    assert transaction.amount == 5

    payload = deepcopy(state.to_payload())
    GameState.from_payload(deepcopy(payload))
    assert len(payload["objective_control_record_authorities"]) == 1
    genuine_checkpoint = deepcopy(
        payload["objective_control_record_authorities"][0]["boundary_checkpoint"]
    )

    target_unit_id = "army-beta:character-unit-b"
    target_matches = tuple(
        unit
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == target_unit_id
    )
    assert len(target_matches) == 1
    removed_model_ids = tuple(model.model_instance_id for model in target_matches[0].own_models)
    source_id = (
        "core-rules:primary-unit-destruction-tracking:event-fabricated:army-beta:character-unit-b"
    )
    occurrence_id = "event-fabricated:army-beta:character-unit-b"
    active_player_id = state.active_player_id
    assert active_player_id is not None
    departure_id = primary_battlefield_departure_id(
        game_id=state.game_id,
        rules_unit_instance_id=target_unit_id,
        affected_component_unit_instance_ids=(target_unit_id,),
        departed_component_unit_instance_ids=(target_unit_id,),
        removed_model_instance_ids=removed_model_ids,
        battle_round=state.battle_round,
        active_player_id=active_player_id,
        phase=BattlePhase.FIGHT.value,
        removal_kind=BattlefieldRemovalKind.DESTROYED,
        occurrence_id=occurrence_id,
        source_id=source_id,
    )
    departure = PrimaryBattlefieldDepartureState(
        departure_id=departure_id,
        game_id=state.game_id,
        owner_player_id="player-b",
        rules_unit_instance_id=target_unit_id,
        component_unit_instance_ids=(target_unit_id,),
        affected_component_unit_instance_ids=(target_unit_id,),
        departed_component_unit_instance_ids=(target_unit_id,),
        removed_model_instance_ids=removed_model_ids,
        battle_round=state.battle_round,
        active_player_id=active_player_id,
        phase=BattlePhase.FIGHT.value,
        removal_kind=BattlefieldRemovalKind.DESTROYED,
        occurrence_id=occurrence_id,
        source_id=source_id,
    )
    assert len(state.primary_unit_destruction_states) == 1
    destruction_id = primary_unit_destruction_id(
        game_id=state.game_id,
        source_id=source_id,
        destroyed_unit_instance_id=target_unit_id,
    )
    primary_destruction = replace(
        state.primary_unit_destruction_states[0],
        destruction_id=destruction_id,
        source_model_destroyed_event_id="event-fabricated",
        source_battlefield_departure_ids=(departure_id,),
        destroyed_unit_instance_id=target_unit_id,
        source_id=source_id,
    )
    projection_state = copy(state)
    projection_state.primary_battlefield_departure_states = [
        *state.primary_battlefield_departure_states,
        departure,
    ]
    projection_state.primary_unit_destruction_states = [
        *state.primary_unit_destruction_states,
        primary_destruction,
    ]
    secondary_destruction = secondary_unit_destruction_from_primary(
        state=projection_state,
        primary_destruction=primary_destruction,
    )

    payload["primary_battlefield_departure_states"].append(departure.to_payload())
    payload["primary_battlefield_departure_states"].sort(key=lambda row: row["departure_id"])
    payload["primary_unit_destruction_states"].append(primary_destruction.to_payload())
    payload["primary_unit_destruction_states"].sort(key=lambda row: row["destruction_id"])
    payload["secondary_unit_destruction_states"].append(secondary_destruction.to_payload())
    payload["secondary_unit_destruction_states"].sort(key=lambda row: row["destruction_id"])
    _rehash_primary_evidence_with_destruction(
        payload,
        departure=departure,
        destruction_id=destruction_id,
    )

    def insert_exact_secondary_projection(
        evidence: SecondaryScoringStateEvidencePayload,
        transaction_payload: VictoryPointTransactionPayload,
    ) -> None:
        evidence["unit_destruction_states"].append(secondary_destruction.to_payload())
        evidence["unit_destruction_states"].sort(key=lambda row: row["destruction_id"])
        metadata = _required_metadata(transaction_payload)
        evidence_by_rule = _required_object(
            metadata.get("evidence_by_rule"),
            name="Bring It Down evidence_by_rule",
        )
        rule_evidence = _required_object(
            evidence_by_rule.get("bring-it-down-tactical"),
            name="Bring It Down rule evidence",
        )
        rule_evidence["destroyed_unit_instance_ids"] = [
            row["destroyed_unit_instance_id"] for row in evidence["unit_destruction_states"]
        ]

    _coordinated_rehash(
        payload,
        secondary_mission_id="bring-it-down",
        mutate=insert_exact_secondary_projection,
    )
    assert (
        payload["objective_control_record_authorities"][0]["boundary_checkpoint"]
        == genuine_checkpoint
    )

    with pytest.raises(GameLifecycleError, match=_AUTHORITY_DRIFT_ERROR):
        GameState.from_payload(payload)


def test_beacon_selection_cannot_be_rehashed_to_an_unselected_unit() -> None:
    selected_unit_ids: dict[str, str] = {}

    def place_second_valid_beacon_unit(state: GameState) -> None:
        units = _intercessors(state, player_id=_SCORING_PLAYER_ID)
        assert len(units) == 2
        selected_unit_ids["selected"] = units[0].unit_instance_id
        selected_unit_ids["fabricated"] = units[1].unit_instance_id
        _place_near_unit(
            state,
            moving_unit_id=units[1].unit_instance_id,
            anchor_unit_id=units[0].unit_instance_id,
        )

    state = _scored_secondary_state(
        "beacon",
        after_positive_seed=place_second_valid_beacon_unit,
    )
    assert selected_unit_ids["selected"] != selected_unit_ids["fabricated"]
    transaction = _secondary_transaction(state, secondary_mission_id="beacon")
    assert transaction.amount == 5

    payload = deepcopy(state.to_payload())
    GameState.from_payload(deepcopy(payload))

    def rewrite_beacon_selection(
        evidence: SecondaryScoringStateEvidencePayload,
        _transaction_payload: VictoryPointTransactionPayload,
    ) -> None:
        selection = _required_object(evidence["selection_payload"], name="Beacon selection")
        assert selection.get("beacon_unit_instance_id") == selected_unit_ids["selected"]
        selection["beacon_unit_instance_id"] = selected_unit_ids["fabricated"]

    _coordinated_rehash(
        payload,
        secondary_mission_id="beacon",
        mutate=rewrite_beacon_selection,
    )

    with pytest.raises(GameLifecycleError, match=_AUTHORITY_DRIFT_ERROR):
        GameState.from_payload(payload)


__all__: list[str] = []
__all__ += ["Callable", "DecisionController", "EvidenceTransactionMutation", "GameStatePayload"]
__all__ += ["SCORING_COMMIT_CHECKPOINT_HASH_KEY", "JsonValue", "ModelPlacement", "Pose"]
__all__ += ["SCORING_COMMIT_CHECKPOINT_ID_KEY", "SECONDARY_SCORING_STATE_EVIDENCE_HASH_KEY"]
__all__ += ["SECONDARY_SCORING_STATE_EVIDENCE_ID_KEY", "SecondaryMissionCardMode"]
__all__ += ["SecondaryMissionCardState", "SecondaryMissionChoice"]
__all__ += ["SecondaryMissionLifecycleCertificationRow", "SecondaryMissionMode", "UnitInstance"]
__all__ += ["UnitMusterSelection", "VictoryPointLedgerPayload", "VictoryPointSourceKind"]
__all__ += ["_LAYOUT_ROW", "VictoryPointTransaction", "_authority_unit_selections"]
__all__ += ["_place_unit_at", "_secondary_transaction_payload", "active_player_id_for_row"]
__all__ += ["canonical_json", "canonical_payload_sha256", "cast", "default_unit_selection"]
__all__ += ["event_companion_pairing_lifecycle_certification_rows", "phase17n_event_setup"]
__all__ += ["phase17n_state_with_setup", "record_primary_turn_start_evidence_for_fixture"]
__all__ += ["resolved_secondary_mission_selection_for_card", "seed_positive_secondary_condition"]
__all__ += ["unit_selection"]
