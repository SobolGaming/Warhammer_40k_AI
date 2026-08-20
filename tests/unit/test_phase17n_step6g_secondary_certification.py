from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import cast

import pytest
from tests.phase11c_command_phase_helpers import (
    army_muster_request,
    complete_setup_through_gate,
    default_unit_selection,
    mustered_armies,
    phase11c_config,
    unit_selection,
)
from tests.phase17n_primary_mission_helpers import (
    phase17n_event_setup,
    phase17n_state_with_setup,
)
from tests.phase17n_secondary_certification_fixtures import (
    TURN_CAP_TACTICAL_IDS,
    SecondaryPositiveExpectation,
    active_player_id_for_row,
    certification_unit_selections,
    seed_positive_secondary_condition,
    seed_sequential_tactical_turn_cap_conditions,
)
from tests.phase17n_secondary_mission_helpers import resolved_secondary_mission_selection_for_card
from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.missions import ObjectiveMarkerRole
from warhammer40k_core.engine.attached_unit_reconciliation import (
    split_attached_rules_unit_if_required,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import EventLog
from warhammer40k_core.engine.fight_order import FightPhaseState, FightsFirstRegistry
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.mission_decisions import TACTICAL_SECONDARY_SCORE_DECISION_TYPE
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.objective_control import ObjectiveControlTiming
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage, LifecycleStatusKind
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.primary_mission_choices import (
    SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE,
)
from warhammer40k_core.engine.primary_scoring_commit_checkpoint import (
    PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT,
)
from warhammer40k_core.engine.primary_scoring_pairing_certification import (
    event_companion_pairing_lifecycle_certification_rows,
)
from warhammer40k_core.engine.primary_scoring_state_evidence import (
    PrimaryScoringBoundaryKind,
    PrimaryScoringStateEvidence,
)
from warhammer40k_core.engine.scoring import (
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionCardStatus,
    VictoryPointSourceKind,
    VictoryPointTransaction,
)
from warhammer40k_core.engine.secondary_mission_selection import SecondaryMissionSelection
from warhammer40k_core.engine.secondary_scoring_boundary import (
    score_turn_end_mission_scoring_boundary,
)
from warhammer40k_core.engine.secondary_scoring_inventory import (
    SECONDARY_CARD_MODE_CERTIFICATION_COUNT,
    SECONDARY_LIFECYCLE_CERTIFICATION_COUNT,
    SECONDARY_MISSION_COUNT,
    SecondaryMissionLifecycleCertificationRow,
    secondary_mission_inventory_rows,
    secondary_mission_lifecycle_certification_rows,
)
from warhammer40k_core.engine.secondary_when_drawn import (
    apply_tactical_secondary_when_drawn,
    next_tactical_secondary_when_drawn_request,
)
from warhammer40k_core.geometry.pose import Pose

_SCORING_PLAYER_IDS = ("player-a", "player-b")
_EVENT_COMPANION_FORCE_DISPOSITION_IDS = (
    "take-and-hold",
    "purge-the-foe",
    "disruption",
    "reconnaissance",
    "priority-assets",
)
_LAYOUT_ROW = event_companion_pairing_lifecycle_certification_rows()[0]
_LIFECYCLE_CERTIFICATION_ROWS = secondary_mission_lifecycle_certification_rows(
    layout_id=_LAYOUT_ROW.layout_id
)
_TACTICAL_CERTIFICATION_ROWS = tuple(
    row for row in _LIFECYCLE_CERTIFICATION_ROWS if row.mode == "tactical"
)
_ALLOWED_SCORING_DECISION_TYPES = frozenset(
    {
        SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE,
        TACTICAL_SECONDARY_SCORE_DECISION_TYPE,
    }
)


def test_phase17n_step6g_inventory_covers_every_secondary_card_and_mode() -> None:
    rows = secondary_mission_inventory_rows()
    assert len(rows) == SECONDARY_MISSION_COUNT
    assert sum(len(row.modes) for row in rows) == SECONDARY_CARD_MODE_CERTIFICATION_COUNT
    assert all(row.state_backed for row in rows)
    assert {row.secondary_mission_id for row in rows} == {
        "a-grievous-blow",
        "a-tempting-target",
        "assassination",
        "beacon",
        "behind-enemy-lines",
        "bring-it-down",
        "burden-of-trust",
        "centre-ground",
        "cleanse",
        "defend-stronghold",
        "display-of-might",
        "engage-on-all-fronts",
        "forward-position",
        "no-prisoners",
        "outflank",
        "overwhelming-force",
        "plunder",
        "secure-no-mans-land",
    }
    assert len(_LIFECYCLE_CERTIFICATION_ROWS) == SECONDARY_LIFECYCLE_CERTIFICATION_COUNT
    assert {row.layout_id for row in _LIFECYCLE_CERTIFICATION_ROWS} == {_LAYOUT_ROW.layout_id}
    assert {row.scoring_player_id for row in _LIFECYCLE_CERTIFICATION_ROWS} == set(
        _SCORING_PLAYER_IDS
    )


@pytest.mark.parametrize(
    "row",
    _LIFECYCLE_CERTIFICATION_ROWS,
    ids=tuple(
        f"{row.secondary_mission_id}:{row.mode}:{row.scoring_player_id}"
        for row in _LIFECYCLE_CERTIFICATION_ROWS
    ),
)
def test_phase17n_step6g_secondary_scores_through_lifecycle_restore_and_views(
    row: SecondaryMissionLifecycleCertificationRow,
) -> None:
    session, initial_payload, expectation = _secondary_certification_session(row)
    initial_state = session.lifecycle.state
    assert initial_state is not None
    assert initial_state.active_player_id == active_player_id_for_row(row)
    _drive_secondary_scoring_through_facade(
        session,
        row=row,
        score_tactical=True,
    )

    state = session.lifecycle.state
    assert state is not None
    _assert_positive_secondary_outcome(state, row=row, expectation=expectation, scored=True)
    _assert_primary_commit_precedes_secondary(session, row=row)
    _assert_secondary_boundary_is_idempotent(state, row=row)

    restored_initial = GameLifecycle.from_payload(initial_payload)
    restored_initial_state = restored_initial.state
    assert restored_initial_state is not None
    assert restored_initial_state.primary_scoring_state_evidence_records == []
    assert restored_initial_state.secondary_scoring_state_evidence_records == []
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
        assert public_payload["secondary_scoring_state_evidence_records"] == []
        _assert_opponent_selection_payloads_are_redacted(
            public_payload["secondary_mission_card_states"],
            viewer_player_id=viewer_player_id,
        )
        view = session.view(viewer_player_id=viewer_player_id)
        assert "primary_scoring_state_evidence_records" not in view
        assert view["viewer_player_id"] == viewer_player_id
        _assert_public_primary_commitments_are_opaque(view["public_victory_point_ledgers"], state)

    player_a_events = session.events_since(EventStreamCursor(0), viewer_player_id="player-a")
    player_b_events = session.events_since(EventStreamCursor(0), viewer_player_id="player-b")
    assert player_a_events["viewer_player_id"] == "player-a"
    assert player_b_events["viewer_player_id"] == "player-b"
    assert player_a_events["events"]
    assert player_b_events["events"]


@pytest.mark.parametrize(
    "row",
    _TACTICAL_CERTIFICATION_ROWS,
    ids=tuple(
        f"{row.secondary_mission_id}:retain:{row.scoring_player_id}"
        for row in _TACTICAL_CERTIFICATION_ROWS
    ),
)
def test_phase17n_step6g_tactical_retain_leaves_card_active_without_transaction(
    row: SecondaryMissionLifecycleCertificationRow,
) -> None:
    session, _initial_payload, expectation = _secondary_certification_session(row)
    _drive_secondary_scoring_through_facade(
        session,
        row=row,
        score_tactical=False,
    )
    state = session.lifecycle.state
    assert state is not None
    _assert_positive_secondary_outcome(state, row=row, expectation=expectation, scored=False)
    declined = tuple(
        event
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == "tactical_secondary_mission_score_declined"
    )
    scored_events = tuple(
        event
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == "tactical_secondary_mission_scored"
    )
    assert declined
    assert scored_events == ()


def _secondary_certification_session(
    row: SecondaryMissionLifecycleCertificationRow,
) -> tuple[LocalGameSession, GameLifecyclePayload, SecondaryPositiveExpectation]:
    setup = _setup_for_layout()
    active_player_id = active_player_id_for_row(row)
    state = phase17n_state_with_setup(
        setup=setup,
        active_player_id=active_player_id,
        phase=BattlePhase.FIGHT,
        battle_round=2,
        player_a_units=certification_unit_selections(player_id="player-a"),
        player_b_units=certification_unit_selections(player_id="player-b"),
    )
    _seed_certified_secondary(state, row)
    _seed_completed_fight_phase(state)
    expectation = seed_positive_secondary_condition(state, row)
    decisions = record_primary_turn_start_evidence_for_fixture(state)
    config = _secondary_certification_config(setup_game_id=state.game_id)
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
    return LocalGameSession(lifecycle=lifecycle), initial_payload, expectation


def _seed_certified_secondary(
    state: GameState,
    row: SecondaryMissionLifecycleCertificationRow,
) -> None:
    scoring_player_id = row.scoring_player_id
    state.secondary_mission_choices = [
        choice
        for choice in state.secondary_mission_choices
        if choice.player_id != scoring_player_id
    ]
    state.secondary_mission_card_states = [
        card for card in state.secondary_mission_card_states if card.player_id != scoring_player_id
    ]
    if row.mode == "fixed":
        paired = "assassination" if row.secondary_mission_id == "bring-it-down" else "bring-it-down"
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=scoring_player_id,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=(row.secondary_mission_id, paired),
            )
        )
        card = state.secondary_mission_card_state(
            player_id=scoring_player_id,
            secondary_mission_id=row.secondary_mission_id,
            mode=SecondaryMissionCardMode.FIXED,
        )
        if card is None:
            raise AssertionError("Step 6G fixed certification card was not recorded.")
        state.replace_secondary_mission_card_state(
            card.with_selection(resolved_secondary_mission_selection_for_card(state, card))
        )
        return
    state.record_secondary_mission_choice(
        SecondaryMissionChoice(player_id=scoring_player_id, mode=SecondaryMissionMode.TACTICAL)
    )
    card = SecondaryMissionCardState.active_tactical(
        player_id=scoring_player_id,
        secondary_mission_id=row.secondary_mission_id,
        battle_round=state.battle_round,
        source_result_id=f"phase17n-step6g-{row.secondary_mission_id}",
    )
    state.record_secondary_mission_card_state(
        card.with_selection(resolved_secondary_mission_selection_for_card(state, card))
    )


def _drive_secondary_scoring_through_facade(
    session: LocalGameSession,
    *,
    row: SecondaryMissionLifecycleCertificationRow,
    score_tactical: bool,
) -> None:
    resolved_tactical_score = False
    for step_index in range(24):
        pending = session.lifecycle.pending_decision_request()
        if pending is not None and pending.decision_type in _ALLOWED_SCORING_DECISION_TYPES:
            if not pending.options:
                raise AssertionError("Step 6G secondary certification requires a finite option.")
            option_id = pending.options[0].option_id
            if pending.decision_type == TACTICAL_SECONDARY_SCORE_DECISION_TYPE:
                prefix = "score:" if score_tactical else "retain:"
                option_id = next(
                    (
                        option.option_id
                        for option in pending.options
                        if option.option_id.startswith(prefix)
                    ),
                    option_id,
                )
                resolved_tactical_score = True
            status = session.submit_option(
                request_id=pending.request_id,
                option_id=option_id,
                result_id=(f"phase17n-step6g-{row.scoring_player_id}-choice-{step_index:02d}"),
            )
            if status.status_kind is LifecycleStatusKind.INVALID:
                raise AssertionError("Step 6G secondary certification rejected a legal choice.")
            continue
        state = session.lifecycle.state
        tactical_ready = row.mode == "fixed" or resolved_tactical_score
        if (
            state is not None
            and tactical_ready
            and _secondary_outcome_ready(
                state,
                row=row,
                scored=score_tactical,
            )
        ):
            return
        if pending is not None:
            raise AssertionError(
                "Step 6G secondary certification encountered an unexpected pending decision "
                f"{pending.decision_type} before scoring."
            )
        status = session.advance_until_decision_or_terminal()
        if status.status_kind is LifecycleStatusKind.INVALID:
            raise AssertionError("Step 6G secondary certification lifecycle advance was invalid.")
        if status.status_kind is LifecycleStatusKind.UNSUPPORTED:
            raise AssertionError(
                "Step 6G secondary certification lifecycle advance was unsupported."
            )
        if status.status_kind is LifecycleStatusKind.TERMINAL:
            return
    raise AssertionError(
        "Step 6G secondary certification did not persist the certified Secondary outcome."
    )


def _secondary_certification_config(*, setup_game_id: str) -> GameConfig:
    setup = _setup_for_layout()
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
                    unit_selections=certification_unit_selections(player_id="player-a"),
                ),
                force_disposition_id=_LAYOUT_ROW.attacker_force_disposition_id,
            ),
            replace(
                army_muster_request(
                    catalog=catalog,
                    player_id="player-b",
                    army_id="army-beta",
                    unit_selections=certification_unit_selections(player_id="player-b"),
                ),
                force_disposition_id=_LAYOUT_ROW.defender_force_disposition_id,
            ),
        ),
    )


def _setup_for_layout() -> MissionSetup:
    return phase17n_event_setup(
        layout_id=_LAYOUT_ROW.layout_id,
        attacker_force_disposition_id=_LAYOUT_ROW.attacker_force_disposition_id,
        defender_force_disposition_id=_LAYOUT_ROW.defender_force_disposition_id,
    )


def _seed_completed_fight_phase(state: GameState) -> None:
    if state.active_player_id is None:
        raise AssertionError("Step 6G secondary fixture requires an active player.")
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
            "Step 6G secondary certification found multiple ordinary turn-end evidence "
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
            "Step 6G secondary certification did not persist ordinary turn-end evidence "
            f"for {scoring_player_id}."
        )
    return evidence


def _secondary_transactions(
    state: GameState, *, player_id: str, source_id: str
) -> tuple[VictoryPointTransaction, ...]:
    ledger = state.victory_point_ledger_for_player(player_id)
    return tuple(
        transaction
        for transaction in ledger.transactions
        if transaction.source_kind
        in {VictoryPointSourceKind.FIXED_SECONDARY, VictoryPointSourceKind.TACTICAL_SECONDARY}
        and transaction.source_id == source_id
    )


def _certified_card_or_none(
    state: GameState,
    row: SecondaryMissionLifecycleCertificationRow,
) -> SecondaryMissionCardState | None:
    mode = (
        SecondaryMissionCardMode.FIXED if row.mode == "fixed" else SecondaryMissionCardMode.TACTICAL
    )
    matches = tuple(
        card
        for card in state.secondary_mission_card_states
        if card.player_id == row.scoring_player_id
        and card.secondary_mission_id == row.secondary_mission_id
        and card.mode is mode
    )
    if not matches:
        return None
    if len(matches) > 1:
        raise AssertionError("Step 6G found multiple certified cards for one row.")
    return matches[0]


def _certified_card(
    state: GameState,
    row: SecondaryMissionLifecycleCertificationRow,
) -> SecondaryMissionCardState:
    card = _certified_card_or_none(state, row)
    if card is None:
        raise AssertionError("Step 6G certified card is missing after scoring.")
    return card


def _secondary_outcome_ready(
    state: GameState,
    *,
    row: SecondaryMissionLifecycleCertificationRow,
    scored: bool,
) -> bool:
    active_player_id = active_player_id_for_row(row)
    if _ordinary_turn_end_evidence_for_player_or_none(state, active_player_id) is None:
        return False
    transactions = _secondary_transactions(
        state,
        player_id=row.scoring_player_id,
        source_id=row.secondary_mission_id,
    )
    if row.mode == "fixed":
        return bool(transactions)
    card = _certified_card_or_none(state, row)
    if card is None:
        return False
    if scored:
        return card.status is SecondaryMissionCardStatus.SCORED and bool(transactions)
    return (
        card.status is SecondaryMissionCardStatus.ACTIVE
        and not state.tactical_secondary_achievement_contexts
        and not transactions
    )


def _assert_positive_secondary_outcome(
    state: GameState,
    *,
    row: SecondaryMissionLifecycleCertificationRow,
    expectation: SecondaryPositiveExpectation,
    scored: bool,
) -> None:
    card = _certified_card(state, row)
    transactions = _secondary_transactions(
        state,
        player_id=row.scoring_player_id,
        source_id=row.secondary_mission_id,
    )
    if row.mode == "fixed" or scored:
        assert len(transactions) == 1
        transaction = transactions[0]
        assert transaction.amount == expectation.expected_amount
        metadata = transaction.metadata
        if type(metadata) is not dict:
            raise AssertionError("Step 6G secondary transaction metadata must be an object.")
        rule_ids = metadata.get("scoring_rule_ids")
        if type(rule_ids) is not list:
            raise AssertionError("Step 6G secondary transaction is missing scoring_rule_ids.")
        assert set(rule_ids) == expectation.expected_rule_ids
        evidence_id = metadata.get("secondary_scoring_state_evidence_id")
        assert type(evidence_id) is str
        assert evidence_id
        assert any(
            stored.evidence_id == evidence_id
            for stored in state.secondary_scoring_state_evidence_records
        )
        if row.mode == "fixed":
            assert card.status is SecondaryMissionCardStatus.ACTIVE
        else:
            assert card.status is SecondaryMissionCardStatus.SCORED
            assert not state.tactical_secondary_achievement_contexts
        return
    assert transactions == ()
    assert card.status is SecondaryMissionCardStatus.ACTIVE
    assert not state.tactical_secondary_achievement_contexts


def _assert_primary_commit_precedes_secondary(
    session: LocalGameSession,
    *,
    row: SecondaryMissionLifecycleCertificationRow,
) -> None:
    events = session.lifecycle.decision_controller.event_log.records
    commit_indexes = tuple(
        index
        for index, event in enumerate(events)
        if event.event_type == PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT
    )
    secondary_indexes = tuple(
        index
        for index, event in enumerate(events)
        if event.event_type
        in {
            "tactical_secondary_mission_scored",
            "tactical_secondary_mission_score_declined",
        }
    )
    assert commit_indexes
    if row.mode != "fixed":
        assert secondary_indexes
    if secondary_indexes:
        assert min(commit_indexes) < min(secondary_indexes)
    state = session.lifecycle.state
    assert state is not None
    active_player_id = active_player_id_for_row(row)
    _ordinary_turn_end_evidence_for_player(state, active_player_id)
    scoring_ledger = state.victory_point_ledger_for_player(row.scoring_player_id)
    primary_indexes = tuple(
        index
        for index, transaction in enumerate(scoring_ledger.transactions)
        if transaction.source_kind is VictoryPointSourceKind.PRIMARY
    )
    secondary_transaction_indexes = tuple(
        index
        for index, transaction in enumerate(scoring_ledger.transactions)
        if transaction.source_kind
        in {VictoryPointSourceKind.FIXED_SECONDARY, VictoryPointSourceKind.TACTICAL_SECONDARY}
        and transaction.source_id == row.secondary_mission_id
    )
    if primary_indexes and secondary_transaction_indexes:
        assert min(primary_indexes) < min(secondary_transaction_indexes)


def _assert_secondary_boundary_is_idempotent(
    state: GameState,
    *,
    row: SecondaryMissionLifecycleCertificationRow,
) -> None:
    evidence = _ordinary_turn_end_evidence_for_player(state, active_player_id_for_row(row))
    record = next(
        (
            stored
            for stored in state.objective_control_records
            if stored.record_id == evidence.objective_control_record_id
        ),
        None,
    )
    if record is None:
        raise AssertionError("Step 6G idempotence check is missing the turn-end record.")
    before = _secondary_transactions(
        state,
        player_id=row.scoring_player_id,
        source_id=row.secondary_mission_id,
    )
    score_turn_end_mission_scoring_boundary(
        state=state,
        record=record,
        end_of_battle=False,
        event_log=EventLog(),
    )
    after = _secondary_transactions(
        state,
        player_id=row.scoring_player_id,
        source_id=row.secondary_mission_id,
    )
    assert tuple(transaction.transaction_id for transaction in after) == tuple(
        transaction.transaction_id for transaction in before
    )


def _assert_public_primary_commitments_are_opaque(
    public_ledgers: object,
    state: GameState,
) -> None:
    if type(public_ledgers) is not list:
        raise AssertionError("Step 6G public victory-point ledgers must be a list.")
    evidence_ids = {
        evidence.evidence_id for evidence in state.primary_scoring_state_evidence_records
    }
    evidence_hashes = {
        evidence.evidence_hash for evidence in state.primary_scoring_state_evidence_records
    }
    for ledger_value in cast(list[object], public_ledgers):
        if type(ledger_value) is not dict:
            raise AssertionError("Step 6G public victory-point ledger must be an object.")
        ledger = cast(dict[str, object], ledger_value)
        transactions_value = ledger.get("transactions")
        if type(transactions_value) is not list:
            raise AssertionError("Step 6G public victory-point transactions must be a list.")
        for transaction_value in cast(list[object], transactions_value):
            if type(transaction_value) is not dict:
                raise AssertionError("Step 6G public victory-point transaction must be an object.")
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


def _assert_opponent_selection_payloads_are_redacted(
    public_cards: object,
    *,
    viewer_player_id: str,
) -> None:
    if type(public_cards) is not list:
        raise AssertionError("Step 6G public secondary card states must be a list.")
    for card_value in cast(list[object], public_cards):
        if type(card_value) is not dict:
            raise AssertionError("Step 6G public secondary card state must be an object.")
        card = cast(dict[str, object], card_value)
        if card.get("player_id") == viewer_player_id:
            continue
        if card.get("hidden") is True:
            continue
        assert card.get("selection_payload") is None


def test_secondary_turn_cap_limits_sequential_tactical_scores_to_fifteen_vp() -> None:
    state = _turn_cap_state()
    decisions = record_primary_turn_start_evidence_for_fixture(state)
    amounts: list[int] = []
    for secondary_mission_id in TURN_CAP_TACTICAL_IDS:
        state.score_secondary_mission_from_state(
            player_id="player-a",
            secondary_mission_id=secondary_mission_id,
            mode=SecondaryMissionCardMode.TACTICAL,
            phase=BattlePhase.FIGHT,
            event_log=decisions.event_log,
        )
        transactions = _secondary_transactions(
            state,
            player_id="player-a",
            source_id=secondary_mission_id,
        )
        assert len(transactions) == 1
        amounts.append(transactions[0].amount)
    assert amounts[:3] == [5, 5, 5]
    assert amounts[3] == 0
    assert sum(amounts) == 15
    final_metadata = _secondary_transactions(
        state,
        player_id="player-a",
        source_id=TURN_CAP_TACTICAL_IDS[-1],
    )[0].metadata
    if type(final_metadata) is not dict:
        raise AssertionError("Capped Secondary transaction metadata must be an object.")
    audit = final_metadata["vp_cap_audit"]
    if type(audit) is not dict:
        raise AssertionError("Capped Secondary transaction must include vp_cap_audit.")
    assert audit["requested_amount"] == 5
    assert audit["applied_amount"] == 0
    assert audit["secondary_turn_vp_cap"] == 15
    assert audit["secondary_turn_points_before"] == 15
    assert audit["secondary_turn_points_after"] == 15
    assert audit["secondary_turn_remaining_capacity"] == 0
    assert "secondary_turn_vp_cap" in cast(list[object], audit["capped_reasons"])
    GameState.from_payload(state.to_payload())


def test_spatial_secondary_restore_survives_later_qualifying_unit_mutation() -> None:
    row = _lifecycle_row("engage-on-all-fronts", mode="tactical", scoring_player_id="player-a")
    state, _event_log, expectation = _score_certified_row_from_state(row)
    qualifying_unit = _first_intercessor(state, player_id="player-a")
    _zero_and_remove_unit(state, qualifying_unit.unit_instance_id)
    restored = GameState.from_payload(state.to_payload())
    transactions = _secondary_transactions(
        restored,
        player_id="player-a",
        source_id="engage-on-all-fronts",
    )
    assert len(transactions) == 1
    assert transactions[0].amount == expectation.expected_amount


def test_unattributed_and_self_destruction_score_bring_it_down() -> None:
    unattributed_row = _lifecycle_row(
        "bring-it-down",
        mode="tactical",
        scoring_player_id="player-a",
    )
    unattributed_state, _event_log, expectation = _score_certified_row_from_state(unattributed_row)
    assert unattributed_state.secondary_unit_destruction_states[0].destroying_player_id is None
    unattributed_transactions = _secondary_transactions(
        unattributed_state,
        player_id="player-a",
        source_id="bring-it-down",
    )
    assert unattributed_transactions[0].amount == expectation.expected_amount

    self_kill_state = _tactical_fight_state()
    _seed_single_tactical_card(self_kill_state, "bring-it-down")
    vehicle = _unit_for(
        self_kill_state,
        player_id="player-b",
        datasheet_id="core-vehicle-monster",
    )
    self_kill_state.record_secondary_unit_destruction(
        destroying_player_id="player-b",
        destroyed_unit_instance_id=vehicle.unit_instance_id,
        destroyed_model_instance_ids=tuple(model.model_instance_id for model in vehicle.own_models),
        started_turn_objective_marker_ids=(),
        source_id="phase17n-self-kill-bring-it-down",
    )
    decisions = record_primary_turn_start_evidence_for_fixture(self_kill_state)
    self_kill_state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="bring-it-down",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=decisions.event_log,
    )
    assert (
        _secondary_transactions(
            self_kill_state,
            player_id="player-a",
            source_id="bring-it-down",
        )[0].amount
        == 5
    )


def test_assassination_all_destroyed_survives_character_return_to_life() -> None:
    row = _lifecycle_row("assassination", mode="tactical", scoring_player_id="player-a")
    state, _event_log, expectation = _score_certified_row_from_state(row)
    character = _unit_for(
        state,
        player_id="player-b",
        datasheet_id="core-character-leader",
    )
    _restore_unit_wounds(state, character.unit_instance_id)
    restored = GameState.from_payload(state.to_payload())
    transactions = _secondary_transactions(
        restored,
        player_id="player-a",
        source_id="assassination",
    )
    assert transactions[0].amount == expectation.expected_amount
    metadata = transactions[0].metadata
    if type(metadata) is not dict:
        raise AssertionError("Assassination transaction metadata must be an object.")
    assert metadata["scoring_rule_ids"] == ["assassination-tactical-all-characters-destroyed"]


def test_cleanse_when_drawn_shuffle_is_optional_while_plunder_is_active() -> None:
    state = _command_tactical_state(battle_round=2)
    _record_unresolved_tactical(state, "plunder")
    _record_unresolved_tactical(state, "cleanse")
    decisions = DecisionController()
    status = next_tactical_secondary_when_drawn_request(state=state, decisions=decisions)
    assert status is not None
    request = status.decision_request
    assert request is not None
    assert request.payload["secondary_mission_id"] == "cleanse"
    assert [option.option_id for option in request.options] == [
        "keep:cleanse",
        "shuffle:cleanse",
    ]
    apply_tactical_secondary_when_drawn(
        state=state,
        result=DecisionResult.for_request(
            result_id="phase17n-when-drawn-shuffle-cleanse",
            request=request,
            selected_option_id="shuffle:cleanse",
        ),
        decisions=decisions,
    )
    assert (
        state.secondary_mission_card_state(
            player_id="player-a",
            secondary_mission_id="cleanse",
            mode=SecondaryMissionCardMode.TACTICAL,
        )
        is None
    )
    plunder = state.secondary_mission_card_state(
        player_id="player-a",
        secondary_mission_id="plunder",
        mode=SecondaryMissionCardMode.TACTICAL,
    )
    assert plunder is not None
    assert plunder.status is SecondaryMissionCardStatus.ACTIVE


def test_plunder_when_drawn_shuffle_is_optional_while_cleanse_is_active() -> None:
    state = _command_tactical_state(battle_round=2)
    _record_unresolved_tactical(state, "cleanse")
    _record_unresolved_tactical(state, "plunder")
    decisions = DecisionController()
    first = next_tactical_secondary_when_drawn_request(state=state, decisions=decisions)
    assert first is not None
    assert first.decision_request is not None
    apply_tactical_secondary_when_drawn(
        state=state,
        result=DecisionResult.for_request(
            result_id="phase17n-when-drawn-keep-cleanse",
            request=first.decision_request,
            selected_option_id="keep:cleanse",
        ),
        decisions=decisions,
    )
    second = next_tactical_secondary_when_drawn_request(state=state, decisions=decisions)
    assert second is not None
    assert second.decision_request is not None
    assert second.decision_request.payload["secondary_mission_id"] == "plunder"
    assert [option.option_id for option in second.decision_request.options] == [
        "keep:plunder",
        "shuffle:plunder",
    ]
    apply_tactical_secondary_when_drawn(
        state=state,
        result=DecisionResult.for_request(
            result_id="phase17n-when-drawn-keep-plunder",
            request=second.decision_request,
            selected_option_id="keep:plunder",
        ),
        decisions=decisions,
    )
    assert next_tactical_secondary_when_drawn_request(state=state, decisions=decisions) is None
    for secondary_mission_id in ("cleanse", "plunder"):
        card = state.secondary_mission_card_state(
            player_id="player-a",
            secondary_mission_id=secondary_mission_id,
            mode=SecondaryMissionCardMode.TACTICAL,
        )
        assert card is not None
        assert card.status is SecondaryMissionCardStatus.ACTIVE


def test_defend_stronghold_first_round_when_drawn_shuffles_without_keep_option() -> None:
    state = _command_tactical_state(battle_round=1)
    _record_unresolved_tactical(state, "defend-stronghold")
    decisions = DecisionController()
    status = next_tactical_secondary_when_drawn_request(state=state, decisions=decisions)
    assert (
        state.secondary_mission_card_state(
            player_id="player-a",
            secondary_mission_id="defend-stronghold",
            mode=SecondaryMissionCardMode.TACTICAL,
        )
        is None
    )
    shuffled = [
        event
        for event in decisions.event_log.records
        if event.event_type == "tactical_secondary_when_drawn_shuffled"
    ]
    assert len(shuffled) == 1
    payload = shuffled[0].payload
    if type(payload) is not dict:
        raise AssertionError("Defend Stronghold When Drawn event payload must be an object.")
    assert payload["mandatory"] is True
    assert payload["secondary_mission_id"] == "defend-stronghold"
    if status is not None and status.decision_request is not None:
        assert status.decision_request.payload["secondary_mission_id"] != "defend-stronghold"
        assert all(
            not option.option_id.startswith("keep:defend-stronghold")
            for option in status.decision_request.options
        )


def test_burden_of_trust_still_scores_after_attached_unit_split() -> None:
    state = _attached_burden_state()
    formation = state.army_definitions[0].attached_units[0]
    attached_id = formation.attached_unit_instance_id
    bodyguard_id = formation.bodyguard_unit_instance_id
    leader_id = formation.leader_unit_instance_ids[0]
    home = _home_objective(state, player_id="player-a")
    _place_unit(state, bodyguard_id, home.x_inches, home.y_inches)
    _place_unit(state, leader_id, home.x_inches, home.y_inches)
    card = SecondaryMissionCardState.active_tactical(
        player_id="player-a",
        secondary_mission_id="burden-of-trust",
        battle_round=state.battle_round,
        source_result_id="phase17n-burden-split",
    )
    assert state.mission_setup is not None
    state.record_secondary_mission_card_state(
        card.with_selection(
            SecondaryMissionSelection().with_guards(
                guarded_objective_unit_ids=((home.objective_marker_id, attached_id),),
                resolved_guard_objective_ids=tuple(
                    marker.objective_marker_id for marker in state.mission_setup.objective_markers
                ),
                battle_round=state.battle_round,
            )
        )
    )
    bodyguard = _unit_by_id(state, bodyguard_id)
    _zero_and_remove_unit(state, bodyguard.unit_instance_id)
    surviving = split_attached_rules_unit_if_required(
        state=state,
        event_log=EventLog(),
        rules_unit_instance_id=attached_id,
    )
    assert leader_id in surviving
    _place_unit(state, leader_id, home.x_inches, home.y_inches)
    decisions = record_primary_turn_start_evidence_for_fixture(state)
    state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="burden-of-trust",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=decisions.event_log,
    )
    transactions = _secondary_transactions(
        state,
        player_id="player-a",
        source_id="burden-of-trust",
    )
    assert len(transactions) == 1
    assert transactions[0].amount == 2


def _lifecycle_row(
    secondary_mission_id: str,
    *,
    mode: str,
    scoring_player_id: str,
) -> SecondaryMissionLifecycleCertificationRow:
    matches = tuple(
        row
        for row in _LIFECYCLE_CERTIFICATION_ROWS
        if row.secondary_mission_id == secondary_mission_id
        and row.mode == mode
        and row.scoring_player_id == scoring_player_id
    )
    if len(matches) != 1:
        raise AssertionError("Step 6G review fixture could not resolve a certification row.")
    return matches[0]


def _score_certified_row_from_state(
    row: SecondaryMissionLifecycleCertificationRow,
) -> tuple[GameState, EventLog, SecondaryPositiveExpectation]:
    session, _payload, expectation = _secondary_certification_session(row)
    state = session.lifecycle.state
    assert state is not None
    event_log = session.lifecycle.decision_controller.event_log
    mode = (
        SecondaryMissionCardMode.FIXED if row.mode == "fixed" else SecondaryMissionCardMode.TACTICAL
    )
    state.score_secondary_mission_from_state(
        player_id=row.scoring_player_id,
        secondary_mission_id=row.secondary_mission_id,
        mode=mode,
        phase=BattlePhase.FIGHT,
        event_log=event_log,
    )
    return state, event_log, expectation


def _turn_cap_state() -> GameState:
    state = _tactical_fight_state()
    state.secondary_mission_card_states = [
        card for card in state.secondary_mission_card_states if card.player_id != "player-a"
    ]
    for secondary_mission_id in TURN_CAP_TACTICAL_IDS:
        card = SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id=secondary_mission_id,
            battle_round=state.battle_round,
            source_result_id=f"phase17n-turn-cap-{secondary_mission_id}",
        )
        state.record_secondary_mission_card_state(
            card.with_selection(resolved_secondary_mission_selection_for_card(state, card))
        )
    seed_sequential_tactical_turn_cap_conditions(state)
    return state


def _tactical_fight_state() -> GameState:
    state = phase17n_state_with_setup(
        setup=_setup_for_layout(),
        active_player_id="player-a",
        phase=BattlePhase.FIGHT,
        battle_round=2,
        player_a_secondary=SecondaryMissionMode.TACTICAL,
        player_a_units=certification_unit_selections(player_id="player-a"),
        player_b_units=certification_unit_selections(player_id="player-b"),
    )
    _seed_completed_fight_phase(state)
    return state


def _command_tactical_state(*, battle_round: int) -> GameState:
    return phase17n_state_with_setup(
        setup=_setup_for_layout(),
        active_player_id="player-a",
        phase=BattlePhase.COMMAND,
        battle_round=battle_round,
        player_a_secondary=SecondaryMissionMode.TACTICAL,
        player_a_units=certification_unit_selections(player_id="player-a"),
        player_b_units=certification_unit_selections(player_id="player-b"),
    )


def _seed_single_tactical_card(state: GameState, secondary_mission_id: str) -> None:
    state.secondary_mission_card_states = [
        card for card in state.secondary_mission_card_states if card.player_id != "player-a"
    ]
    card = SecondaryMissionCardState.active_tactical(
        player_id="player-a",
        secondary_mission_id=secondary_mission_id,
        battle_round=state.battle_round,
        source_result_id=f"phase17n-review-{secondary_mission_id}",
    )
    state.record_secondary_mission_card_state(
        card.with_selection(resolved_secondary_mission_selection_for_card(state, card))
    )


def _record_unresolved_tactical(state: GameState, secondary_mission_id: str) -> None:
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id=secondary_mission_id,
            battle_round=state.battle_round,
            source_result_id=f"phase17n-when-drawn-{secondary_mission_id}",
        )
    )


def _attached_burden_state() -> GameState:
    setup = _setup_for_layout()
    catalog = phase11c_config().army_catalog
    config = replace(
        phase11c_config(),
        game_id="phase17n-burden-split",
        mission_setup=setup,
        army_muster_requests=(
            replace(
                army_muster_request(
                    catalog=catalog,
                    player_id="player-a",
                    army_id="army-alpha",
                    unit_selections=(
                        default_unit_selection("bodyguard-unit"),
                        unit_selection(
                            unit_selection_id="leader-unit",
                            datasheet_id="core-character-leader",
                            model_profile_id="core-character-leader",
                            model_count=1,
                        ),
                    ),
                    attachment_declarations=(
                        AttachmentDeclaration(
                            source_unit_selection_id="leader-unit",
                            bodyguard_unit_selection_id="bodyguard-unit",
                        ),
                    ),
                ),
                force_disposition_id=_LAYOUT_ROW.attacker_force_disposition_id,
            ),
            replace(
                army_muster_request(
                    catalog=catalog,
                    player_id="player-b",
                    army_id="army-beta",
                    unit_selections=(default_unit_selection("intercessor-unit-3"),),
                ),
                force_disposition_id=_LAYOUT_ROW.defender_force_disposition_id,
            ),
        ),
    )
    state = GameState.from_config(config)
    for army in mustered_armies(config):
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase17n-burden-split-battlefield",
        armies=tuple(state.army_definitions),
        battlefield_width_inches=setup.battlefield_width_inches,
        battlefield_depth_inches=setup.battlefield_depth_inches,
        terrain_features=setup.terrain_features,
    )
    state.record_battlefield_state(scenario.battlefield_state)
    state.record_secondary_mission_choice(
        SecondaryMissionChoice(player_id="player-a", mode=SecondaryMissionMode.TACTICAL)
    )
    state.record_secondary_mission_choice(
        SecondaryMissionChoice(
            player_id="player-b",
            mode=SecondaryMissionMode.FIXED,
            fixed_mission_ids=("assassination", "bring-it-down"),
        )
    )
    complete_setup_through_gate(state=state, decisions=DecisionController(), config=config)
    assert state.battlefield_state is not None
    state.mission_setup = setup
    state.battlefield_state = replace(
        state.battlefield_state,
        battlefield_width_inches=setup.battlefield_width_inches,
        battlefield_depth_inches=setup.battlefield_depth_inches,
        terrain_features=setup.terrain_features,
    )
    state.stage = GameLifecycleStage.BATTLE
    state.battle_round = 2
    state.active_player_id = "player-b"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    _seed_completed_fight_phase(state)
    return state


def _place_unit(state: GameState, unit_instance_id: str, x_inches: float, y_inches: float) -> None:
    if state.battlefield_state is None:
        raise AssertionError("Review fixture placement requires battlefield state.")
    unit_placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    placements = []
    for index, placement in enumerate(unit_placement.model_placements):
        placements.append(
            placement.with_pose(
                Pose.at(
                    x_inches + (index * 0.45),
                    y_inches,
                    placement.pose.position.z,
                    facing_degrees=placement.pose.facing.degrees,
                )
            )
        )
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        unit_placement.with_model_placements(tuple(placements))
    )


def _home_objective(state: GameState, *, player_id: str):
    if state.mission_setup is None:
        raise AssertionError("Review fixture requires MissionSetup.")
    role = (
        ObjectiveMarkerRole.ATTACKER_HOME
        if player_id == state.mission_setup.attacker_player_id
        else ObjectiveMarkerRole.DEFENDER_HOME
    )
    for marker in state.mission_setup.objective_markers:
        if marker.objective_role is role:
            return marker
    raise AssertionError("Review fixture is missing a home objective.")


def _zero_and_remove_unit(state: GameState, unit_instance_id: str) -> None:
    armies = []
    removed_ids: list[str] = []
    for army in state.army_definitions:
        units = []
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                removed_ids.extend(model.model_instance_id for model in unit.own_models)
                unit = replace(
                    unit,
                    own_models=tuple(
                        replace(model, wounds_remaining=0) for model in unit.own_models
                    ),
                )
            units.append(unit)
        armies.append(replace(army, units=tuple(units)))
    state.army_definitions = armies
    if state.battlefield_state is not None and removed_ids:
        state.replace_battlefield_state(
            state.battlefield_state.with_removed_models(tuple(removed_ids))
        )


def _restore_unit_wounds(state: GameState, unit_instance_id: str) -> None:
    armies = []
    for army in state.army_definitions:
        units = []
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                unit = replace(
                    unit,
                    own_models=tuple(
                        replace(model, wounds_remaining=model.starting_wounds)
                        for model in unit.own_models
                    ),
                )
            units.append(unit)
        armies.append(replace(army, units=tuple(units)))
    state.army_definitions = armies


def _first_intercessor(state: GameState, *, player_id: str):
    return _unit_for(
        state,
        player_id=player_id,
        datasheet_id="core-intercessor-like-infantry",
    )


def _unit_for(state: GameState, *, player_id: str, datasheet_id: str):
    matches = tuple(
        unit
        for army in state.army_definitions
        if army.player_id == player_id
        for unit in army.units
        if unit.datasheet_id == datasheet_id
    )
    if not matches:
        raise AssertionError(f"Review fixture is missing {datasheet_id} for {player_id}.")
    return matches[0]


def _unit_by_id(state: GameState, unit_instance_id: str):
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                return unit
    raise AssertionError(f"Review fixture is missing unit {unit_instance_id}.")
