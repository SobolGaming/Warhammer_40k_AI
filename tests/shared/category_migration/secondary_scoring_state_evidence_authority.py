from __future__ import annotations

from collections.abc import Callable
from copy import copy, deepcopy
from dataclasses import replace
from typing import cast

import pytest

from tests.phase11c_command_phase_helpers import default_unit_selection, unit_selection
from tests.phase17n_primary_mission_helpers import phase17n_event_setup, phase17n_state_with_setup
from tests.phase17n_secondary_certification_fixtures import (
    active_player_id_for_row,
    seed_positive_secondary_condition,
)
from tests.phase17n_secondary_mission_helpers import resolved_secondary_mission_selection_for_card
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
from warhammer40k_core.engine.primary_unit_destruction_tracking import primary_unit_destruction_id
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
    seed_positive_secondary_condition(
        state, row, event_log=decisions.event_log, decisions=decisions
    )
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


__all__: list[str] = []
__all__ += ["BattlePhase", "BattlefieldRemovalKind", "Callable", "DecisionController"]
__all__ += ["EvidenceTransactionMutation", "GameLifecycleError", "GameState", "GameStatePayload"]
__all__ += ["JsonValue", "ModelPlacement", "Pose", "PrimaryBattlefieldDepartureState"]
__all__ += ["SCORING_COMMIT_CHECKPOINT_HASH_KEY", "SCORING_COMMIT_CHECKPOINT_ID_KEY"]
__all__ += ["SECONDARY_SCORING_STATE_EVIDENCE_HASH_KEY"]
__all__ += ["SECONDARY_SCORING_STATE_EVIDENCE_ID_KEY", "SecondaryMissionCardMode"]
__all__ += ["SecondaryMissionCardState", "SecondaryMissionChoice"]
__all__ += ["SecondaryMissionLifecycleCertificationRow", "SecondaryMissionMode"]
__all__ += ["SecondaryScoringStateEvidencePayload", "UnitInstance", "UnitMusterSelection"]
__all__ += ["VictoryPointLedgerPayload", "VictoryPointSourceKind", "VictoryPointTransaction"]
__all__ += ["_AUTHORITY_DRIFT_ERROR", "_LAYOUT_ROW", "VictoryPointTransactionPayload"]
__all__ += ["_SCORING_PLAYER_ID", "_authority_unit_selections", "_coordinated_rehash"]
__all__ += ["_empty_rule_evidence", "_intercessors", "_place_near_unit", "_place_unit_at"]
__all__ += ["_reduce_engage_presence_to_three_quarters"]
__all__ += ["_rehash_primary_evidence_with_destruction", "_replace_single_rule_projection"]
__all__ += ["_required_metadata", "_required_object", "_required_string_list"]
__all__ += ["_scored_secondary_state", "_secondary_transaction", "_secondary_transaction_payload"]
__all__ += ["active_player_id_for_row", "canonical_json", "canonical_payload_sha256", "cast"]
__all__ += ["copy", "deepcopy", "default_unit_selection"]
__all__ += ["event_companion_pairing_lifecycle_certification_rows", "phase17n_event_setup"]
__all__ += ["phase17n_state_with_setup", "primary_battlefield_departure_id"]
__all__ += ["primary_unit_destruction_id", "pytest"]
__all__ += ["record_primary_turn_start_evidence_for_fixture", "replace"]
__all__ += ["resolved_secondary_mission_selection_for_card"]
__all__ += ["secondary_unit_destruction_from_primary", "seed_positive_secondary_condition"]
__all__ += ["unit_selection"]
