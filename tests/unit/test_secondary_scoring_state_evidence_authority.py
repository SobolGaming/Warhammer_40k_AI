from __future__ import annotations

from collections.abc import Callable
from copy import copy, deepcopy
from dataclasses import replace
from typing import cast

import pytest
from tests.phase11c_command_phase_helpers import default_unit_selection, unit_selection
from tests.phase17n_primary_mission_helpers import (
    phase17n_event_setup,
    phase17n_state_with_setup,
)
from tests.phase17n_secondary_certification_fixtures import (
    active_player_id_for_row,
    seed_positive_secondary_condition,
)
from tests.phase17n_secondary_mission_helpers import (
    resolved_secondary_mission_selection_for_card,
)
from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture

from warhammer40k_core.core.descriptor_hash import canonical_payload_sha256
from warhammer40k_core.engine.battlefield_state import BattlefieldRemovalKind, ModelPlacement
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import JsonValue, canonical_json
from warhammer40k_core.engine.game_state import (
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.game_state_payloads import GameStatePayload
from warhammer40k_core.engine.list_validation import UnitMusterSelection
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_battlefield_departure import (
    PrimaryBattlefieldDepartureState,
    primary_battlefield_departure_id,
)
from warhammer40k_core.engine.primary_scoring_pairing_certification import (
    event_companion_pairing_lifecycle_certification_rows,
)
from warhammer40k_core.engine.primary_unit_destruction_tracking import (
    primary_unit_destruction_id,
)
from warhammer40k_core.engine.scoring import (
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    VictoryPointLedgerPayload,
    VictoryPointSourceKind,
    VictoryPointTransaction,
    VictoryPointTransactionPayload,
)
from warhammer40k_core.engine.secondary_deployment_zone_evidence import (
    SCORING_COMMIT_CHECKPOINT_HASH_KEY,
    SCORING_COMMIT_CHECKPOINT_ID_KEY,
)
from warhammer40k_core.engine.secondary_scoring_inventory import (
    SecondaryMissionLifecycleCertificationRow,
)
from warhammer40k_core.engine.secondary_scoring_state_evidence import (
    SECONDARY_SCORING_STATE_EVIDENCE_HASH_KEY,
    SECONDARY_SCORING_STATE_EVIDENCE_ID_KEY,
    SecondaryScoringStateEvidencePayload,
)
from warhammer40k_core.engine.secondary_unit_destruction_tracking import (
    secondary_unit_destruction_from_primary,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose

_AUTHORITY_DRIFT_ERROR = (
    "Secondary scoring state evidence drifted from authoritative boundary state"
)
_LAYOUT_ROW = event_companion_pairing_lifecycle_certification_rows()[0]
_SCORING_PLAYER_ID = "player-a"

EvidenceTransactionMutation = Callable[
    [SecondaryScoringStateEvidencePayload, VictoryPointTransactionPayload],
    None,
]


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
    assert len(payload["objective_control_record_authorities"]) == 1
    genuine_checkpoint = deepcopy(
        payload["objective_control_record_authorities"][0]["boundary_checkpoint"]
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
    assert (
        payload["objective_control_record_authorities"][0]["boundary_checkpoint"]
        == genuine_checkpoint
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


def _scored_secondary_state(
    secondary_mission_id: str,
    *,
    after_positive_seed: Callable[[GameState], None] | None = None,
) -> GameState:
    row = SecondaryMissionLifecycleCertificationRow(
        secondary_mission_id=secondary_mission_id,
        mode="tactical",
        scoring_player_id=_SCORING_PLAYER_ID,
        layout_id=_LAYOUT_ROW.layout_id,
    )
    setup = phase17n_event_setup(
        layout_id=_LAYOUT_ROW.layout_id,
        attacker_force_disposition_id=_LAYOUT_ROW.attacker_force_disposition_id,
        defender_force_disposition_id=_LAYOUT_ROW.defender_force_disposition_id,
    )
    state = phase17n_state_with_setup(
        setup=setup,
        active_player_id=active_player_id_for_row(row),
        phase=BattlePhase.FIGHT,
        battle_round=2,
        player_a_units=_authority_unit_selections(
            secondary_mission_id=secondary_mission_id,
            player_id="player-a",
        ),
        player_b_units=_authority_unit_selections(
            secondary_mission_id=secondary_mission_id,
            player_id="player-b",
        ),
        player_a_secondary=SecondaryMissionMode.TACTICAL,
    )
    state.secondary_mission_choices = [
        choice
        for choice in state.secondary_mission_choices
        if choice.player_id != _SCORING_PLAYER_ID
    ]
    state.secondary_mission_card_states = [
        card for card in state.secondary_mission_card_states if card.player_id != _SCORING_PLAYER_ID
    ]
    state.record_secondary_mission_choice(
        SecondaryMissionChoice(
            player_id=_SCORING_PLAYER_ID,
            mode=SecondaryMissionMode.TACTICAL,
        )
    )
    card = SecondaryMissionCardState.active_tactical(
        player_id=_SCORING_PLAYER_ID,
        secondary_mission_id=secondary_mission_id,
        battle_round=state.battle_round,
        source_result_id=f"secondary-authority:{secondary_mission_id}",
    )
    state.record_secondary_mission_card_state(
        card.with_selection(resolved_secondary_mission_selection_for_card(state, card))
    )
    decisions = DecisionController()
    seed_positive_secondary_condition(state, row, event_log=decisions.event_log)
    if after_positive_seed is not None:
        after_positive_seed(state)
    if not any(
        snapshot.active_player_id == state.active_player_id
        and snapshot.battle_round == state.battle_round
        for snapshot in state.primary_rules_unit_turn_start_snapshots
    ):
        record_primary_turn_start_evidence_for_fixture(state, decisions=decisions)
    state.score_secondary_mission_from_state(
        player_id=_SCORING_PLAYER_ID,
        secondary_mission_id=secondary_mission_id,
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=decisions.event_log,
    )
    return state


def _authority_unit_selections(
    *,
    secondary_mission_id: str,
    player_id: str,
) -> tuple[UnitMusterSelection, ...]:
    prefix = "a" if player_id == "player-a" else "b"
    intercessor_count_by_mission = {
        "beacon": 2 if player_id == _SCORING_PLAYER_ID else 1,
        "bring-it-down": 1,
        "cleanse": 1,
        "engage-on-all-fronts": 4 if player_id == _SCORING_PLAYER_ID else 1,
    }
    intercessor_count = intercessor_count_by_mission[secondary_mission_id]
    selections = [
        default_unit_selection(f"intercessor-unit-{prefix}{index}")
        for index in range(1, intercessor_count + 1)
    ]
    if secondary_mission_id == "engage-on-all-fronts" and player_id == _SCORING_PLAYER_ID:
        selections.append(
            unit_selection(
                unit_selection_id="character-unit-a",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            )
        )
    if secondary_mission_id == "bring-it-down" and player_id != _SCORING_PLAYER_ID:
        selections.extend(
            (
                unit_selection(
                    unit_selection_id="character-unit-b",
                    datasheet_id="core-character-leader",
                    model_profile_id="core-character-leader",
                    model_count=1,
                ),
                unit_selection(
                    unit_selection_id="vehicle-unit-b",
                    datasheet_id="core-vehicle-monster",
                    model_profile_id="core-vehicle-monster",
                    model_count=1,
                ),
            )
        )
    return tuple(selections)


def _coordinated_rehash(
    payload: GameStatePayload,
    *,
    secondary_mission_id: str,
    mutate: EvidenceTransactionMutation,
) -> None:
    evidence_matches = [
        evidence
        for evidence in payload["secondary_scoring_state_evidence_records"]
        if evidence["secondary_mission_id"] == secondary_mission_id
        and evidence["scoring_player_id"] == _SCORING_PLAYER_ID
    ]
    assert len(evidence_matches) == 1
    evidence = evidence_matches[0]
    previous_evidence_id = evidence["evidence_id"]

    ledger, transaction = _secondary_transaction_payload(
        payload,
        secondary_mission_id=secondary_mission_id,
    )
    metadata = _required_metadata(transaction)
    assert metadata.get(SECONDARY_SCORING_STATE_EVIDENCE_ID_KEY) == previous_evidence_id
    amount_before = transaction["amount"]
    mutate(evidence, transaction)
    ledger["victory_points"] += transaction["amount"] - amount_before

    content = dict(evidence)
    content.pop("evidence_id")
    content.pop("evidence_hash")
    evidence_hash = canonical_payload_sha256(content)
    evidence_id = f"secondary-scoring-state-evidence:{evidence_hash}"
    evidence["evidence_hash"] = evidence_hash
    evidence["evidence_id"] = evidence_id
    metadata[SECONDARY_SCORING_STATE_EVIDENCE_ID_KEY] = evidence_id
    metadata[SECONDARY_SCORING_STATE_EVIDENCE_HASH_KEY] = evidence_hash


def _rehash_primary_evidence_with_destruction(
    payload: GameStatePayload,
    *,
    departure: PrimaryBattlefieldDepartureState,
    destruction_id: str,
) -> None:
    assert len(payload["primary_scoring_state_evidence_records"]) == 1
    evidence = payload["primary_scoring_state_evidence_records"][0]
    previous_evidence_id = evidence["evidence_id"]
    evidence["primary_battlefield_departure_states"].append(departure.to_payload())
    evidence["primary_battlefield_departure_states"].sort(key=lambda row: row["departure_id"])
    evidence["primary_unit_destruction_state_ids"].append(destruction_id)
    evidence["primary_unit_destruction_state_ids"].sort()
    content = dict(evidence)
    content.pop("evidence_id")
    content.pop("evidence_hash")
    evidence_hash = canonical_payload_sha256(content)
    evidence_id = f"primary-scoring-state-evidence:{evidence_hash}"
    evidence["evidence_hash"] = evidence_hash
    evidence["evidence_id"] = evidence_id

    lifecycle_matches = [
        lifecycle
        for lifecycle in payload["primary_scoring_boundary_lifecycles"]
        if lifecycle["evidence_id"] == previous_evidence_id
    ]
    assert len(lifecycle_matches) == 1
    lifecycle = lifecycle_matches[0]
    lifecycle["evidence_id"] = evidence_id
    lifecycle_content = dict(lifecycle)
    lifecycle_content.pop("lifecycle_id")
    lifecycle_content.pop("lifecycle_hash")
    lifecycle_hash = canonical_payload_sha256(lifecycle_content)
    lifecycle["lifecycle_hash"] = lifecycle_hash
    lifecycle["lifecycle_id"] = f"primary-scoring-boundary-lifecycle:{lifecycle_hash}"


def _secondary_transaction_payload(
    payload: GameStatePayload,
    *,
    secondary_mission_id: str,
) -> tuple[VictoryPointLedgerPayload, VictoryPointTransactionPayload]:
    ledger_matches = [
        ledger
        for ledger in payload["victory_point_ledgers"]
        if ledger["player_id"] == _SCORING_PLAYER_ID
    ]
    assert len(ledger_matches) == 1
    ledger = ledger_matches[0]
    transaction_matches = [
        transaction
        for transaction in ledger["transactions"]
        if transaction["source_kind"] == VictoryPointSourceKind.TACTICAL_SECONDARY.value
        and transaction["source_id"] == secondary_mission_id
    ]
    assert len(transaction_matches) == 1
    return ledger, transaction_matches[0]


def _secondary_transaction(
    state: GameState,
    *,
    secondary_mission_id: str,
) -> VictoryPointTransaction:
    matches = tuple(
        transaction
        for transaction in state.victory_point_ledger_for_player(_SCORING_PLAYER_ID).transactions
        if transaction.source_kind is VictoryPointSourceKind.TACTICAL_SECONDARY
        and transaction.source_id == secondary_mission_id
    )
    assert len(matches) == 1
    return matches[0]


def _replace_single_rule_projection(
    *,
    evidence: SecondaryScoringStateEvidencePayload,
    transaction: VictoryPointTransactionPayload,
    rule_id: str,
    condition: str,
    source_id: str,
    amount: int,
    rule_evidence: dict[str, JsonValue],
) -> None:
    evidence["scoring_rule_ids"] = [rule_id]
    evidence["scoring_rule_conditions"] = [condition]
    evidence["scoring_rule_source_ids"] = [source_id]
    transaction["amount"] = amount
    metadata = _required_metadata(transaction)
    metadata["scoring_rule_ids"] = [rule_id]
    metadata["scoring_rule_conditions"] = [condition]
    metadata["scoring_rule_source_ids"] = [source_id]
    metadata["score_count_by_rule"] = {rule_id: 1}
    metadata["victory_points_by_rule"] = {rule_id: amount}
    metadata["evidence_by_rule"] = {rule_id: rule_evidence}


def _empty_rule_evidence(
    *,
    objective_marker_ids: tuple[str, ...] = (),
) -> dict[str, JsonValue]:
    return {
        "score_count": 1,
        "controlled_objective_ids": [],
        "home_objective_ids": [],
        "objective_marker_ids": list(objective_marker_ids),
        "terrain_feature_ids": [],
        "destroyed_unit_instance_ids": [],
        "destroyed_model_instance_ids": [],
        "enemy_unit_instance_ids": [],
    }


def _required_metadata(
    transaction: VictoryPointTransactionPayload,
) -> dict[str, JsonValue]:
    return cast(
        dict[str, JsonValue],
        _required_object(transaction["metadata"], name="Secondary transaction metadata"),
    )


def _required_object(value: object, *, name: str) -> dict[str, object]:
    if type(value) is not dict:
        raise AssertionError(f"{name} must be an object.")
    return cast(dict[str, object], value)


def _required_string_list(value: object, *, name: str) -> list[str]:
    if type(value) is not list:
        raise AssertionError(f"{name} must be a string list.")
    values = cast(list[object], value)
    if any(type(item) is not str for item in values):
        raise AssertionError(f"{name} must be a string list.")
    return cast(list[str], values)


def _reduce_engage_presence_to_three_quarters(state: GameState) -> None:
    units = _intercessors(state, player_id=_SCORING_PLAYER_ID)
    assert len(units) == 4
    _place_near_unit(
        state,
        moving_unit_id=units[3].unit_instance_id,
        anchor_unit_id=units[0].unit_instance_id,
    )


def _place_near_unit(
    state: GameState,
    *,
    moving_unit_id: str,
    anchor_unit_id: str,
) -> None:
    if state.battlefield_state is None:
        raise AssertionError("Secondary authority placement requires battlefield state.")
    anchor = state.battlefield_state.unit_placement_by_id(anchor_unit_id)
    anchor_pose = anchor.model_placements[0].pose
    _place_unit_at(
        state,
        moving_unit_id,
        anchor_pose.position.x + 3.0,
        anchor_pose.position.y + 3.0,
    )


def _place_unit_at(
    state: GameState,
    unit_instance_id: str,
    x_inches: float,
    y_inches: float,
) -> None:
    if state.battlefield_state is None:
        raise AssertionError("Secondary authority placement requires battlefield state.")
    unit_placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    placements: list[ModelPlacement] = []
    for index, placement in enumerate(unit_placement.model_placements):
        placements.append(
            placement.with_pose(
                Pose.at(
                    x_inches + ((index % 5) * 0.45),
                    y_inches + ((index // 5) * 0.45),
                    placement.pose.position.z,
                    facing_degrees=placement.pose.facing.degrees,
                )
            )
        )
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        unit_placement.with_model_placements(tuple(placements))
    )


def _intercessors(state: GameState, *, player_id: str) -> tuple[UnitInstance, ...]:
    army_matches = tuple(army for army in state.army_definitions if army.player_id == player_id)
    assert len(army_matches) == 1
    units = tuple(
        unit
        for unit in army_matches[0].units
        if unit.datasheet_id == "core-intercessor-like-infantry"
    )
    assert units
    return units
