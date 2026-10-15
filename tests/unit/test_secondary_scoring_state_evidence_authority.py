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


def test_cleanse_one_completed_objective_cannot_be_rehashed_as_two() -> None:
    state = _scored_secondary_state("cleanse")
    transaction = _secondary_transaction(state, secondary_mission_id="cleanse")
    assert transaction.amount == 2
    assert state.mission_setup is not None
    genuine = state.secondary_objective_cleanse_states[0]
    fabricated_marker_id = next(
        marker.objective_marker_id
        for marker in state.mission_setup.objective_markers
        if marker.objective_marker_id != genuine.objective_marker_id
    )

    payload = deepcopy(state.to_payload())
    GameState.from_payload(deepcopy(payload))

    def rewrite_as_two_cleansed_objectives(
        evidence: SecondaryScoringStateEvidencePayload,
        transaction_payload: VictoryPointTransactionPayload,
    ) -> None:
        assert len(evidence["objective_cleanse_states"]) == 1
        fabricated = deepcopy(evidence["objective_cleanse_states"][0])
        fabricated["cleanse_id"] = f"{fabricated['cleanse_id']}:fabricated"
        fabricated["objective_marker_id"] = fabricated_marker_id
        fabricated["action_id"] = f"{fabricated['action_id']}:fabricated"
        fabricated["source_id"] = f"{fabricated['source_id']}:fabricated"
        evidence["objective_cleanse_states"].append(fabricated)
        _replace_single_rule_projection(
            evidence=evidence,
            transaction=transaction_payload,
            rule_id="cleanse-tactical-two-objectives",
            condition="two_or_more_objectives_cleansed_this_turn",
            source_id=(
                "gw-11e-warhammer-event-companion-v1-1-2026-07:secondary:cleanse:"
                "scoring-rule:cleanse-tactical-two-objectives"
            ),
            amount=5,
            rule_evidence=_empty_rule_evidence(
                objective_marker_ids=(genuine.objective_marker_id, fabricated_marker_id)
            ),
        )

    _coordinated_rehash(
        payload,
        secondary_mission_id="cleanse",
        mutate=rewrite_as_two_cleansed_objectives,
    )

    with pytest.raises(GameLifecycleError, match=_AUTHORITY_DRIFT_ERROR):
        GameState.from_payload(payload)


def test_cleanse_fabricated_completed_action_and_exact_projection_cannot_be_rehashed() -> None:
    state = _scored_secondary_state("cleanse")
    transaction = _secondary_transaction(state, secondary_mission_id="cleanse")
    assert transaction.amount == 2
    assert state.mission_setup is not None
    genuine = state.secondary_objective_cleanse_states[0]
    fabricated_marker_id = next(
        marker.objective_marker_id
        for marker in state.mission_setup.objective_markers
        if marker.objective_marker_id != genuine.objective_marker_id
    )

    payload = deepcopy(state.to_payload())
    GameState.from_payload(deepcopy(payload))
    assert len(payload["objective_control_record_authorities"]) == 2
    genuine_checkpoints = deepcopy(
        [row["boundary_checkpoint"] for row in payload["objective_control_record_authorities"]]
    )
    action_matches = [
        action
        for action in payload["mission_action_states"]
        if action["action_id"] == genuine.action_id
    ]
    assert len(action_matches) == 1
    fabricated_action = deepcopy(action_matches[0])
    fabricated_action_id = f"{genuine.action_id}:fabricated-second-objective"
    fabricated_action["action_id"] = fabricated_action_id
    fabricated_action["target_id"] = fabricated_marker_id
    fabricated_action["condition_target_id"] = fabricated_marker_id
    payload["mission_action_states"].append(fabricated_action)

    fabricated_cleanse = deepcopy(genuine.to_payload())
    fabricated_cleanse["cleanse_id"] = (
        f"secondary-objective-cleanse:{state.game_id}:round-{state.battle_round:02d}:"
        f"{_SCORING_PLAYER_ID}:{fabricated_marker_id}"
    )
    fabricated_cleanse["objective_marker_id"] = fabricated_marker_id
    fabricated_cleanse["action_id"] = fabricated_action_id
    payload["secondary_objective_cleanse_states"].append(fabricated_cleanse)
    payload["secondary_objective_cleanse_states"].sort(key=lambda cleanse: cleanse["cleanse_id"])

    def rewrite_with_fabricated_completed_action(
        evidence: SecondaryScoringStateEvidencePayload,
        transaction_payload: VictoryPointTransactionPayload,
    ) -> None:
        evidence["objective_cleanse_states"].append(deepcopy(fabricated_cleanse))
        evidence["objective_cleanse_states"].sort(key=lambda cleanse: cleanse["cleanse_id"])
        _replace_single_rule_projection(
            evidence=evidence,
            transaction=transaction_payload,
            rule_id="cleanse-tactical-two-objectives",
            condition="two_or_more_objectives_cleansed_this_turn",
            source_id=(
                "gw-11e-warhammer-event-companion-v1-1-2026-07:secondary:cleanse:"
                "scoring-rule:cleanse-tactical-two-objectives"
            ),
            amount=5,
            rule_evidence=_empty_rule_evidence(
                objective_marker_ids=tuple(
                    sorted((genuine.objective_marker_id, fabricated_marker_id))
                )
            ),
        )

    _coordinated_rehash(
        payload,
        secondary_mission_id="cleanse",
        mutate=rewrite_with_fabricated_completed_action,
    )
    assert [
        row["boundary_checkpoint"] for row in payload["objective_control_record_authorities"]
    ] == genuine_checkpoints

    with pytest.raises(GameLifecycleError, match=_AUTHORITY_DRIFT_ERROR):
        GameState.from_payload(payload)


def test_starting_strength_source_id_cannot_be_coordinately_rehashed() -> None:
    state = _scored_secondary_state("engage-on-all-fronts")
    payload = deepcopy(state.to_payload())
    GameState.from_payload(deepcopy(payload))
    assert len(payload["objective_control_record_authorities"]) == 1
    genuine_checkpoint = deepcopy(
        payload["objective_control_record_authorities"][0]["boundary_checkpoint"]
    )
    target_unit_id = "army-alpha:character-unit-a"
    fabricated_source_id = "coordinated-forged-static-authority:character-a"
    registry_matches = [
        record
        for record in payload["starting_strength_records"]
        if record["unit_instance_id"] == target_unit_id
    ]
    assert len(registry_matches) == 1
    registry_matches[0]["source_id"] = fabricated_source_id

    def rewrite_starting_strength_source(
        evidence: SecondaryScoringStateEvidencePayload,
        _transaction_payload: VictoryPointTransactionPayload,
    ) -> None:
        evidence_matches = [
            record
            for record in evidence["starting_strength_records"]
            if record["unit_instance_id"] == target_unit_id
        ]
        assert len(evidence_matches) == 1
        evidence_matches[0]["source_id"] = fabricated_source_id

    _coordinated_rehash(
        payload,
        secondary_mission_id="engage-on-all-fronts",
        mutate=rewrite_starting_strength_source,
    )
    assert (
        payload["objective_control_record_authorities"][0]["boundary_checkpoint"]
        == genuine_checkpoint
    )

    with pytest.raises(GameLifecycleError, match=_AUTHORITY_DRIFT_ERROR):
        GameState.from_payload(payload)


def test_starting_strength_registry_must_match_the_genuine_boundary_witness() -> None:
    state = _scored_secondary_state("engage-on-all-fronts")
    payload = deepcopy(state.to_payload())
    GameState.from_payload(deepcopy(payload))
    assert len(payload["objective_control_record_authorities"]) == 1
    genuine_checkpoint = deepcopy(
        payload["objective_control_record_authorities"][0]["boundary_checkpoint"]
    )
    target_unit_id = "army-alpha:character-unit-a"
    registry_matches = [
        record
        for record in payload["starting_strength_records"]
        if record["unit_instance_id"] == target_unit_id
    ]
    assert len(registry_matches) == 1
    registry_matches[0]["source_id"] = "fabricated-static-authority:character-a"
    assert (
        payload["objective_control_record_authorities"][0]["boundary_checkpoint"]
        == genuine_checkpoint
    )

    with pytest.raises(GameLifecycleError, match=_AUTHORITY_DRIFT_ERROR):
        GameState.from_payload(payload)


def test_starting_strength_checkpoint_witness_cannot_omit_an_authoritative_row() -> None:
    state = _scored_secondary_state("engage-on-all-fronts")
    payload = deepcopy(state.to_payload())
    GameState.from_payload(deepcopy(payload))
    assert len(payload["objective_control_record_authorities"]) == 1
    authority = payload["objective_control_record_authorities"][0]
    checkpoint = authority["boundary_checkpoint"]
    target_unit_id = "army-alpha:character-unit-a"
    target_matches = [
        record
        for record in payload["starting_strength_records"]
        if record["unit_instance_id"] == target_unit_id
    ]
    assert len(target_matches) == 1
    genuine_starting_strength_registry = deepcopy(payload["starting_strength_records"])
    target_json = canonical_json(target_matches[0])
    checkpoint_starting_strength = _required_string_list(
        checkpoint.get("starting_strength_record_jsons"),
        name="Starting Strength checkpoint witness",
    )
    assert checkpoint_starting_strength.count(target_json) == 1
    checkpoint["starting_strength_record_jsons"] = [
        value for value in checkpoint_starting_strength if value != target_json
    ]

    checkpoint_content = dict(checkpoint)
    checkpoint_content.pop("checkpoint_id")
    checkpoint_content.pop("checkpoint_hash")
    checkpoint_hash = canonical_payload_sha256(checkpoint_content)
    checkpoint["checkpoint_id"] = f"primary-mission-boundary:{checkpoint_hash}"
    checkpoint["checkpoint_hash"] = checkpoint_hash
    authority_content = dict(authority)
    authority_content.pop("authority_id")
    authority_content.pop("authority_hash")
    authority_hash = canonical_payload_sha256(authority_content)
    authority["authority_id"] = f"objective-control-record-authority:{authority_hash}"
    authority["authority_hash"] = authority_hash

    def omit_starting_strength_row(
        evidence: SecondaryScoringStateEvidencePayload,
        transaction_payload: VictoryPointTransactionPayload,
    ) -> None:
        evidence["starting_strength_records"] = [
            record
            for record in evidence["starting_strength_records"]
            if record["unit_instance_id"] != target_unit_id
        ]
        metadata = _required_metadata(transaction_payload)
        metadata[SCORING_COMMIT_CHECKPOINT_ID_KEY] = checkpoint["checkpoint_id"]
        metadata[SCORING_COMMIT_CHECKPOINT_HASH_KEY] = checkpoint_hash

    _coordinated_rehash(
        payload,
        secondary_mission_id="engage-on-all-fronts",
        mutate=omit_starting_strength_row,
    )
    assert payload["starting_strength_records"] == genuine_starting_strength_registry

    with pytest.raises(GameLifecycleError, match=_AUTHORITY_DRIFT_ERROR):
        GameState.from_payload(payload)


__all__: list[str] = []
__all__ += ["BattlePhase", "BattlefieldRemovalKind", "Callable", "DecisionController"]
__all__ += ["EvidenceTransactionMutation", "GameStatePayload", "JsonValue", "ModelPlacement"]
__all__ += ["Pose", "PrimaryBattlefieldDepartureState"]
__all__ += ["SECONDARY_SCORING_STATE_EVIDENCE_HASH_KEY"]
__all__ += ["SECONDARY_SCORING_STATE_EVIDENCE_ID_KEY", "SecondaryMissionCardMode"]
__all__ += ["SecondaryMissionCardState", "SecondaryMissionChoice"]
__all__ += ["SecondaryMissionLifecycleCertificationRow", "SecondaryMissionMode", "UnitInstance"]
__all__ += ["UnitMusterSelection", "VictoryPointLedgerPayload", "VictoryPointSourceKind"]
__all__ += ["_LAYOUT_ROW", "VictoryPointTransaction", "_authority_unit_selections"]
__all__ += ["_intercessors", "_place_near_unit", "_place_unit_at"]
__all__ += ["_reduce_engage_presence_to_three_quarters"]
__all__ += ["_rehash_primary_evidence_with_destruction", "_required_object"]
__all__ += ["_secondary_transaction_payload", "active_player_id_for_row", "cast", "copy"]
__all__ += ["default_unit_selection", "event_companion_pairing_lifecycle_certification_rows"]
__all__ += ["phase17n_event_setup", "phase17n_state_with_setup"]
__all__ += ["primary_battlefield_departure_id", "primary_unit_destruction_id"]
__all__ += ["record_primary_turn_start_evidence_for_fixture", "replace"]
__all__ += ["resolved_secondary_mission_selection_for_card"]
__all__ += ["secondary_unit_destruction_from_primary", "seed_positive_secondary_condition"]
__all__ += ["unit_selection"]
