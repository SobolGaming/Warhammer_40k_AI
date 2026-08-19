from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import cast

import pytest
from tests.phase11c_command_phase_helpers import (
    army_muster_request,
    default_unit_selection,
    phase11c_config,
)
from tests.phase17n_primary_mission_helpers import (
    phase17n_event_setup,
    phase17n_state_with_setup,
)
from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture

from warhammer40k_core.adapters.capability_manifest import CapabilityDimension
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.event_log import EventLog
from warhammer40k_core.engine.fight_order import FightPhaseState, FightsFirstRegistry
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.missions import mission_scoring_policies_from_setup
from warhammer40k_core.engine.objective_control import ObjectiveControlTiming
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage, LifecycleStatusKind
from warhammer40k_core.engine.primary_mission_choices import (
    SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE,
)
from warhammer40k_core.engine.primary_scoring_pairing_certification import (
    EVENT_COMPANION_LAYOUT_INVENTORY_COUNT,
    EVENT_COMPANION_LAYOUT_VARIANT_COUNT,
    EVENT_COMPANION_LIFECYCLE_CERTIFICATION_COUNT,
    EVENT_COMPANION_PAIRING_COUNT,
    EventCompanionPairingLayoutInventoryRow,
    EventCompanionPairingLifecycleCertificationRow,
    event_companion_pairing_layout_inventory_rows,
    event_companion_pairing_lifecycle_certification_rows,
)
from warhammer40k_core.engine.primary_scoring_state_evidence import (
    PrimaryScoringBoundaryKind,
    PrimaryScoringStateEvidence,
)
from warhammer40k_core.engine.scoring import VictoryPointSourceKind
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.event_companion_2026_06 import (
    event_primary_mission_matrix_source_rows,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.event_companion_primary_scoring_2026_06 import (  # noqa: E501
    engine_implemented_primary_mission_ids,
)

_EVENT_COMPANION_FORCE_DISPOSITION_IDS = (
    "take-and-hold",
    "purge-the-foe",
    "disruption",
    "reconnaissance",
    "priority-assets",
)
_SCORING_PLAYER_IDS = ("player-a", "player-b")
_LAYOUT_INVENTORY_ROWS = event_companion_pairing_layout_inventory_rows()
_LIFECYCLE_CERTIFICATION_ROWS = event_companion_pairing_lifecycle_certification_rows()


def test_phase17n_step5g_inventory_covers_every_source_pairing_and_layout() -> None:
    rows = _LAYOUT_INVENTORY_ROWS
    source_rows = event_primary_mission_matrix_source_rows()
    implemented_ids = engine_implemented_primary_mission_ids()

    assert len(source_rows) == EVENT_COMPANION_PAIRING_COUNT
    assert len(rows) == EVENT_COMPANION_LAYOUT_INVENTORY_COUNT
    assert {row.layout_pair_id for row in rows} == {source.layout_pair_id for source in source_rows}
    assert {row.layout_variant for row in rows} == {"a", "b", "c"}
    assert len({row.layout_id for row in rows}) == EVENT_COMPANION_LAYOUT_INVENTORY_COUNT
    assert all(
        row.attacker_primary_mission_id in implemented_ids
        and row.defender_primary_mission_id in implemented_ids
        for row in rows
    )
    pair_counts = {
        source.layout_pair_id: sum(1 for row in rows if row.layout_pair_id == source.layout_pair_id)
        for source in source_rows
    }
    assert set(pair_counts.values()) == {EVENT_COMPANION_LAYOUT_VARIANT_COUNT}
    source_by_pair = {source.layout_pair_id: source for source in source_rows}
    for row in rows:
        source = source_by_pair[row.layout_pair_id]
        assert row.attacker_force_disposition_id == source.source_left_force_disposition_id
        assert row.defender_force_disposition_id == source.source_right_force_disposition_id
        assert row.attacker_primary_mission_id == source.source_left_primary_mission_id
        assert row.defender_primary_mission_id == source.source_right_primary_mission_id
        assert row.layout_id == (
            f"{row.layout_pair_id}-layout-{('a', 'b', 'c').index(row.layout_variant) + 1}"
        )


def test_phase17n_step5g_lifecycle_rows_are_layout_a_only() -> None:
    lifecycle_rows = _LIFECYCLE_CERTIFICATION_ROWS
    layout_a_ids = {row.layout_id for row in _LAYOUT_INVENTORY_ROWS if row.layout_variant == "a"}
    layout_bc_ids = {
        row.layout_id for row in _LAYOUT_INVENTORY_ROWS if row.layout_variant in {"b", "c"}
    }

    assert len(lifecycle_rows) == EVENT_COMPANION_LIFECYCLE_CERTIFICATION_COUNT
    assert {row.layout_id for row in lifecycle_rows} == layout_a_ids
    assert layout_a_ids.isdisjoint(layout_bc_ids)
    assert {row.layout_pair_id for row in lifecycle_rows} == {
        row.layout_pair_id for row in _LAYOUT_INVENTORY_ROWS
    }
    scored_mission_ids = {
        mission_id
        for row in lifecycle_rows
        for mission_id in (
            row.attacker_primary_mission_id,
            row.defender_primary_mission_id,
        )
    }
    assert scored_mission_ids == engine_implemented_primary_mission_ids()


def test_phase17n_step5g_every_layout_instantiates_two_sided_scoring_policies() -> None:
    for row in _LAYOUT_INVENTORY_ROWS:
        setup = _setup_for_inventory_row(row)
        policies = mission_scoring_policies_from_setup(setup)
        assert policies.policy_for_player("player-a").primary_scoring_supported, row.layout_id
        assert policies.policy_for_player("player-b").primary_scoring_supported, row.layout_id
        assert setup.primary_mission_id_for_player("player-a") == row.attacker_primary_mission_id
        assert setup.primary_mission_id_for_player("player-b") == row.defender_primary_mission_id


@pytest.mark.parametrize(
    "row",
    _LIFECYCLE_CERTIFICATION_ROWS,
    ids=tuple(row.layout_pair_id for row in _LIFECYCLE_CERTIFICATION_ROWS),
)
@pytest.mark.parametrize("scoring_player_id", _SCORING_PLAYER_IDS)
def test_phase17n_step5g_pairing_scores_through_lifecycle_restore_and_views(
    row: EventCompanionPairingLifecycleCertificationRow,
    scoring_player_id: str,
) -> None:
    session, initial_payload = _pairing_certification_session(
        row,
        scoring_player_id=scoring_player_id,
    )
    initial_state = session.lifecycle.state
    assert initial_state is not None
    assert initial_state.active_player_id == scoring_player_id
    _drive_pairing_scoring_through_facade(session, scoring_player_id=scoring_player_id)

    state = session.lifecycle.state
    assert state is not None
    setup = _setup_for_lifecycle_row(row)
    expected_mission_id = (
        row.attacker_primary_mission_id
        if scoring_player_id == "player-a"
        else row.defender_primary_mission_id
    )
    assert setup.primary_mission_id_for_player(scoring_player_id) == expected_mission_id
    policies = mission_scoring_policies_from_setup(setup)
    evidence = _ordinary_turn_end_evidence_for_player(state, scoring_player_id)
    record = next(
        (
            stored
            for stored in state.objective_control_records
            if stored.record_id == evidence.objective_control_record_id
        ),
        None,
    )
    if record is None:
        raise AssertionError(
            "Step 5G pairing certification ordinary evidence is missing its "
            "objective-control record."
        )
    scoring_player_ids = policies.scoring_player_ids_for_record(
        record=record,
        turn_order=tuple(state.turn_order),
        end_of_battle=False,
    )
    assert scoring_player_id in scoring_player_ids

    restored_initial = GameLifecycle.from_payload(initial_payload)
    restored_initial_state = restored_initial.state
    assert restored_initial_state is not None
    assert restored_initial_state.primary_scoring_state_evidence_records == []
    restored = GameLifecycle.from_payload(deepcopy(session.lifecycle.to_payload()))
    assert restored.to_payload() == session.lifecycle.to_payload()
    restored_state = restored.state
    assert restored_state is not None
    assert restored_state.to_payload() == state.to_payload()
    restored_log = EventLog.from_payload(
        session.lifecycle.decision_controller.event_log.to_payload()
    )
    assert restored_log.to_payload() == session.lifecycle.decision_controller.event_log.to_payload()

    for viewer_player_id in state.player_ids:
        public_payload = state.to_public_payload(viewer_player_id=viewer_player_id)
        assert public_payload["primary_scoring_state_evidence_records"] == []
        view = session.view(viewer_player_id=viewer_player_id)
        assert "primary_scoring_state_evidence_records" not in view
        assert view["viewer_player_id"] == viewer_player_id
        assert view["primary_mission_progress_state"] == (
            state.primary_mission_progress_state.to_payload()
        )
        _assert_public_primary_commitments_are_opaque(view["public_victory_point_ledgers"], state)

    player_a_events = session.events_since(EventStreamCursor(0), viewer_player_id="player-a")
    player_b_events = session.events_since(EventStreamCursor(0), viewer_player_id="player-b")
    assert player_a_events["viewer_player_id"] == "player-a"
    assert player_b_events["viewer_player_id"] == "player-b"
    assert player_a_events["events"]
    assert player_b_events["events"]


def _pairing_certification_session(
    row: EventCompanionPairingLifecycleCertificationRow,
    *,
    scoring_player_id: str,
) -> tuple[LocalGameSession, GameLifecyclePayload]:
    if scoring_player_id not in _SCORING_PLAYER_IDS:
        raise AssertionError("Step 5G pairing fixture scoring_player_id is unsupported.")
    setup = _setup_for_lifecycle_row(row)
    state = phase17n_state_with_setup(
        setup=setup,
        active_player_id=scoring_player_id,
        phase=BattlePhase.FIGHT,
        battle_round=2,
    )
    _seed_completed_fight_phase(state)
    decisions = record_primary_turn_start_evidence_for_fixture(state)
    config = _pairing_certification_config(row=row, setup_game_id=state.game_id)
    lifecycle = GameLifecycle.from_payload(
        cast(
            GameLifecyclePayload,
            {
                "config": config.to_payload(),
                "parameterized_movement_proposals": True,
                "state": state.to_payload(),
                "decisions": decisions.to_payload(),
                "reaction_queue": {"frames": []},
            },
        )
    )
    initial_payload = deepcopy(lifecycle.to_payload())
    return LocalGameSession(lifecycle=lifecycle), initial_payload


def _drive_pairing_scoring_through_facade(
    session: LocalGameSession,
    *,
    scoring_player_id: str,
) -> None:
    for step_index in range(24):
        state = session.lifecycle.state
        if state is not None and _ordinary_turn_end_evidence_for_player_or_none(
            state,
            scoring_player_id,
        ):
            return
        pending = session.lifecycle.pending_decision_request()
        if pending is not None:
            if pending.decision_type != SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE:
                raise AssertionError(
                    "Step 5G pairing certification encountered an unexpected pending decision "
                    f"{pending.decision_type} before scoring."
                )
            if not pending.options:
                raise AssertionError(
                    "Step 5G pairing certification requires a finite choice option."
                )
            status = session.submit_option(
                request_id=pending.request_id,
                option_id=pending.options[0].option_id,
                result_id=(f"phase17n-step5g-{scoring_player_id}-choice-{step_index:02d}"),
            )
            if status.status_kind is LifecycleStatusKind.INVALID:
                raise AssertionError("Step 5G pairing certification rejected a legal choice.")
            continue
        status = session.advance_until_decision_or_terminal()
        if status.status_kind is LifecycleStatusKind.INVALID:
            raise AssertionError("Step 5G pairing certification lifecycle advance was invalid.")
        if status.status_kind is LifecycleStatusKind.UNSUPPORTED:
            raise AssertionError("Step 5G pairing certification lifecycle advance was unsupported.")
        if status.status_kind is LifecycleStatusKind.TERMINAL:
            return
    raise AssertionError(
        "Step 5G pairing certification did not persist the scoring player's ordinary "
        "turn-end evidence."
    )


def _pairing_certification_config(
    *,
    row: EventCompanionPairingLifecycleCertificationRow,
    setup_game_id: str,
) -> GameConfig:
    setup = _setup_for_lifecycle_row(row)
    base = phase11c_config()
    catalog = replace(
        base.army_catalog,
        detachments=tuple(
            replace(
                detachment,
                force_disposition_ids=tuple(
                    dict.fromkeys(
                        (
                            *detachment.force_disposition_ids,
                            *_EVENT_COMPANION_FORCE_DISPOSITION_IDS,
                        )
                    )
                ),
            )
            if detachment.detachment_id == "core-combined-arms"
            else detachment
            for detachment in base.army_catalog.detachments
        ),
    )
    return replace(
        base,
        game_id=setup_game_id,
        army_catalog=catalog,
        mission_setup=setup,
        army_muster_requests=(
            replace(
                army_muster_request(
                    catalog=catalog,
                    player_id="player-a",
                    army_id="army-alpha",
                    unit_selections=(default_unit_selection("intercessor-unit-1"),),
                ),
                force_disposition_id=row.attacker_force_disposition_id,
            ),
            replace(
                army_muster_request(
                    catalog=catalog,
                    player_id="player-b",
                    army_id="army-beta",
                    unit_selections=(default_unit_selection("intercessor-unit-3"),),
                ),
                force_disposition_id=row.defender_force_disposition_id,
            ),
        ),
    )


def _setup_for_inventory_row(row: EventCompanionPairingLayoutInventoryRow) -> MissionSetup:
    return phase17n_event_setup(
        layout_id=row.layout_id,
        attacker_force_disposition_id=row.attacker_force_disposition_id,
        defender_force_disposition_id=row.defender_force_disposition_id,
    )


def _setup_for_lifecycle_row(row: EventCompanionPairingLifecycleCertificationRow) -> MissionSetup:
    return phase17n_event_setup(
        layout_id=row.layout_id,
        attacker_force_disposition_id=row.attacker_force_disposition_id,
        defender_force_disposition_id=row.defender_force_disposition_id,
    )


def _seed_completed_fight_phase(state: GameState) -> None:
    if state.active_player_id is None:
        raise AssertionError("Step 5G pairing fixture requires an active player.")
    fight_state = FightPhaseState.start(
        battle_round=state.battle_round,
        active_player_id=state.active_player_id,
        policy=state.ruleset_descriptor_for_runtime_policy().fight_policy,
        engaged_at_fight_step_start_unit_ids=(),
        fights_first_registry=FightsFirstRegistry.from_state(state),
    ).with_phase_complete()
    state.replace_fight_phase_state(fight_state)
    state.stage = GameLifecycleStage.BATTLE


def _ordinary_turn_end_evidence_for_player_or_none(
    state: GameState,
    scoring_player_id: str,
) -> PrimaryScoringStateEvidence | None:
    matches = [
        evidence
        for evidence in state.primary_scoring_state_evidence_records
        if evidence.scoring_boundary_kind is PrimaryScoringBoundaryKind.ORDINARY
        and evidence.active_player_id == scoring_player_id
        and evidence.timing is ObjectiveControlTiming.TURN_END
    ]
    if len(matches) > 1:
        raise AssertionError(
            "Step 5G pairing certification found multiple ordinary turn-end evidence "
            f"records for {scoring_player_id}."
        )
    if not matches:
        return None
    return matches[0]


def _ordinary_turn_end_evidence_for_player(
    state: GameState,
    scoring_player_id: str,
) -> PrimaryScoringStateEvidence:
    evidence = _ordinary_turn_end_evidence_for_player_or_none(state, scoring_player_id)
    if evidence is None:
        raise AssertionError(
            "Step 5G pairing certification did not persist ordinary turn-end evidence "
            f"for {scoring_player_id}."
        )
    return evidence


def _assert_public_primary_commitments_are_opaque(
    public_ledgers: object,
    state: GameState,
) -> None:
    if type(public_ledgers) is not list:
        raise AssertionError("Step 5G public victory-point ledgers must be a list.")
    evidence_ids = {
        evidence.evidence_id for evidence in state.primary_scoring_state_evidence_records
    }
    evidence_hashes = {
        evidence.evidence_hash for evidence in state.primary_scoring_state_evidence_records
    }
    for ledger_value in cast(list[object], public_ledgers):
        if type(ledger_value) is not dict:
            raise AssertionError("Step 5G public victory-point ledger must be an object.")
        ledger = cast(dict[str, object], ledger_value)
        transactions_value = ledger.get("transactions")
        if type(transactions_value) is not list:
            raise AssertionError("Step 5G public victory-point transactions must be a list.")
        for transaction_value in cast(list[object], transactions_value):
            if type(transaction_value) is not dict:
                raise AssertionError("Step 5G public victory-point transaction must be an object.")
            transaction = cast(dict[str, object], transaction_value)
            if transaction.get("source_kind") != VictoryPointSourceKind.PRIMARY.value:
                continue
            metadata_value = transaction.get("metadata")
            if type(metadata_value) is not dict:
                continue
            metadata = cast(dict[str, object], metadata_value)
            evidence_id = metadata.get("primary_scoring_state_evidence_id")
            evidence_hash = metadata.get("primary_scoring_state_evidence_hash")
            if evidence_id is not None:
                assert evidence_id in evidence_ids
            if evidence_hash is not None:
                assert evidence_hash in evidence_hashes
            assert "current_rules_unit_position_witnesses" not in metadata
            assert "primary_mission_action_states" not in metadata


def test_phase17n_step5g_capability_rows_are_semantically_executable() -> None:
    row = _LIFECYCLE_CERTIFICATION_ROWS[0]
    session, _initial = _pairing_certification_session(row, scoring_player_id="player-a")
    profile = session.support_profile()
    mission_rows = [
        mission_row
        for mission_row in profile["capability_manifest"]["mission_rows"]
        if mission_row["row_kind"] == "mission"
        and mission_row["metadata"].get("primary_mission_id")
        in {row.attacker_primary_mission_id, row.defender_primary_mission_id}
    ]
    assert len(mission_rows) == 2
    for mission_row in mission_rows:
        semantic = next(
            capability
            for capability in mission_row["capabilities"]
            if capability["dimension"] == CapabilityDimension.SEMANTICALLY_EXECUTABLE.value
        )
        assert semantic["status"] == "supported"
        assert mission_row["semantic_execution"] == "executable"
