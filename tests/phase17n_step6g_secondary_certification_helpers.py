from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from typing import cast

from tests.phase11c_command_phase_helpers import army_muster_request, phase11c_config
from tests.phase17n_primary_mission_helpers import (
    phase17n_event_setup,
    phase17n_state_with_setup,
)
from tests.phase17n_secondary_certification_fixtures import (
    SecondaryPositiveExpectation,
    active_player_id_for_row,
    certification_unit_selections,
    certification_unit_selections_for_row,
    seed_positive_secondary_condition,
)
from tests.phase17n_secondary_mission_helpers import resolved_secondary_mission_selection_for_card
from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import EventLog
from warhammer40k_core.engine.fight_order import FightPhaseState, FightsFirstRegistry
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import UnitMusterSelection
from warhammer40k_core.engine.mission_decisions import TACTICAL_SECONDARY_SCORE_DECISION_TYPE
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.objective_control import ObjectiveControlTiming
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleStage,
    LifecycleStatusKind,
)
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
from warhammer40k_core.engine.secondary_scoring_boundary import (
    score_turn_end_mission_scoring_boundary,
)
from warhammer40k_core.engine.secondary_scoring_inventory import (
    SecondaryMissionLifecycleCertificationRow,
    secondary_mission_lifecycle_certification_rows,
)

STEP6G_SCORING_PLAYER_IDS = ("player-a", "player-b")
_EVENT_COMPANION_FORCE_DISPOSITION_IDS = (
    "take-and-hold",
    "purge-the-foe",
    "disruption",
    "reconnaissance",
    "priority-assets",
)
STEP6G_LAYOUT_ROW = event_companion_pairing_lifecycle_certification_rows()[0]
STEP6G_LIFECYCLE_CERTIFICATION_ROWS = secondary_mission_lifecycle_certification_rows(
    layout_id=STEP6G_LAYOUT_ROW.layout_id
)
STEP6G_TACTICAL_CERTIFICATION_ROWS = tuple(
    row for row in STEP6G_LIFECYCLE_CERTIFICATION_ROWS if row.mode == "tactical"
)
_ALLOWED_SCORING_DECISION_TYPES = frozenset(
    {
        SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE,
        TACTICAL_SECONDARY_SCORE_DECISION_TYPE,
    }
)

STEP6G_A_GRIEVOUS_THROUGH_BEACON_MISSION_IDS = frozenset(
    {
        "a-grievous-blow",
        "a-tempting-target",
        "assassination",
        "beacon",
    }
)
STEP6G_BEHIND_THROUGH_CLEANSE_MISSION_IDS = frozenset(
    {
        "behind-enemy-lines",
        "bring-it-down",
        "burden-of-trust",
        "centre-ground",
        "cleanse",
    }
)
STEP6G_DEFEND_THROUGH_FORWARD_MISSION_IDS = frozenset(
    {
        "defend-stronghold",
        "display-of-might",
        "engage-on-all-fronts",
        "forward-position",
    }
)
STEP6G_NO_PRISONERS_THROUGH_SECURE_MISSION_IDS = frozenset(
    {
        "no-prisoners",
        "outflank",
        "overwhelming-force",
        "plunder",
        "secure-no-mans-land",
    }
)
STEP6G_MISSION_PARTITIONS = (
    STEP6G_A_GRIEVOUS_THROUGH_BEACON_MISSION_IDS,
    STEP6G_BEHIND_THROUGH_CLEANSE_MISSION_IDS,
    STEP6G_DEFEND_THROUGH_FORWARD_MISSION_IDS,
    STEP6G_NO_PRISONERS_THROUGH_SECURE_MISSION_IDS,
)

Step6GMatrixCaseKey = tuple[str, str, str, str]


def step6g_lifecycle_certification_rows(
    mission_ids: frozenset[str],
) -> tuple[SecondaryMissionLifecycleCertificationRow, ...]:
    return tuple(
        row
        for row in STEP6G_LIFECYCLE_CERTIFICATION_ROWS
        if row.secondary_mission_id in mission_ids
    )


def step6g_tactical_certification_rows(
    mission_ids: frozenset[str],
) -> tuple[SecondaryMissionLifecycleCertificationRow, ...]:
    return tuple(
        row for row in step6g_lifecycle_certification_rows(mission_ids) if row.mode == "tactical"
    )


def step6g_matrix_case_keys(
    mission_ids: frozenset[str],
) -> frozenset[Step6GMatrixCaseKey]:
    scoring_keys = tuple(
        (row.secondary_mission_id, row.mode, row.scoring_player_id, "score")
        for row in step6g_lifecycle_certification_rows(mission_ids)
    )
    retain_keys = tuple(
        (row.secondary_mission_id, row.mode, row.scoring_player_id, "retain")
        for row in step6g_tactical_certification_rows(mission_ids)
    )
    return frozenset((*scoring_keys, *retain_keys))


def assert_secondary_scores_through_lifecycle_restore_and_views(
    row: SecondaryMissionLifecycleCertificationRow,
) -> None:
    session, initial_payload, expectation = secondary_certification_session(row)
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
        _assert_public_primary_commitments_are_opaque(
            public_payload["victory_point_ledgers"],
            state,
        )
        _assert_private_scoring_authority_commitments_are_absent(public_payload, state=state)
        _assert_opponent_selection_payloads_are_redacted(
            public_payload["secondary_mission_card_states"],
            viewer_player_id=viewer_player_id,
        )
        view = session.view(viewer_player_id=viewer_player_id)
        assert "primary_scoring_state_evidence_records" not in view
        assert view["viewer_player_id"] == viewer_player_id
        _assert_public_primary_commitments_are_opaque(view["public_victory_point_ledgers"], state)
        _assert_private_scoring_authority_commitments_are_absent(view, state=state)

    player_a_events = session.events_since(EventStreamCursor(0), viewer_player_id="player-a")
    player_b_events = session.events_since(EventStreamCursor(0), viewer_player_id="player-b")
    assert player_a_events["viewer_player_id"] == "player-a"
    assert player_b_events["viewer_player_id"] == "player-b"
    assert player_a_events["events"]
    assert player_b_events["events"]
    _assert_private_scoring_authority_commitments_are_absent(player_a_events, state=state)
    _assert_private_scoring_authority_commitments_are_absent(player_b_events, state=state)


def assert_tactical_retain_leaves_card_active_without_transaction(
    row: SecondaryMissionLifecycleCertificationRow,
) -> None:
    session, _initial_payload, expectation = secondary_certification_session(row)
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


def secondary_certification_session(
    row: SecondaryMissionLifecycleCertificationRow,
) -> tuple[LocalGameSession, GameLifecyclePayload, SecondaryPositiveExpectation]:
    setup = setup_for_layout()
    active_player_id = active_player_id_for_row(row)
    player_a_units = certification_unit_selections_for_row(row, player_id="player-a")
    player_b_units = certification_unit_selections_for_row(row, player_id="player-b")
    state = phase17n_state_with_setup(
        setup=setup,
        active_player_id=active_player_id,
        phase=BattlePhase.FIGHT,
        battle_round=2,
        player_a_units=player_a_units,
        player_b_units=player_b_units,
    )
    decisions = DecisionController()
    _seed_certified_secondary(state, row)
    seed_completed_fight_phase(state)
    expectation = seed_positive_secondary_condition(
        state,
        row,
        event_log=decisions.event_log,
    )
    if not any(
        snapshot.active_player_id == state.active_player_id
        and snapshot.battle_round == state.battle_round
        for snapshot in state.primary_rules_unit_turn_start_snapshots
    ):
        record_primary_turn_start_evidence_for_fixture(state, decisions=decisions)
    config = _secondary_certification_config_for_units(
        setup_game_id=state.game_id,
        player_a_units=player_a_units,
        player_b_units=player_b_units,
    )
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


def configured_step6g_lifecycle(
    *,
    state: GameState,
    decisions: DecisionController,
) -> GameLifecycle:
    config = _secondary_certification_config(setup_game_id=state.game_id)
    return GameLifecycle.from_payload(
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


def _secondary_certification_config(*, setup_game_id: str) -> GameConfig:
    return _secondary_certification_config_for_units(
        setup_game_id=setup_game_id,
        player_a_units=certification_unit_selections(player_id="player-a"),
        player_b_units=certification_unit_selections(player_id="player-b"),
    )


def _secondary_certification_config_for_units(
    *,
    setup_game_id: str,
    player_a_units: tuple[UnitMusterSelection, ...],
    player_b_units: tuple[UnitMusterSelection, ...],
) -> GameConfig:
    setup = setup_for_layout()
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
                    unit_selections=player_a_units,
                ),
                force_disposition_id=STEP6G_LAYOUT_ROW.attacker_force_disposition_id,
            ),
            replace(
                army_muster_request(
                    catalog=catalog,
                    player_id="player-b",
                    army_id="army-beta",
                    unit_selections=player_b_units,
                ),
                force_disposition_id=STEP6G_LAYOUT_ROW.defender_force_disposition_id,
            ),
        ),
    )


def setup_for_layout() -> MissionSetup:
    return phase17n_event_setup(
        layout_id=STEP6G_LAYOUT_ROW.layout_id,
        attacker_force_disposition_id=STEP6G_LAYOUT_ROW.attacker_force_disposition_id,
        defender_force_disposition_id=STEP6G_LAYOUT_ROW.defender_force_disposition_id,
    )


def seed_completed_fight_phase(state: GameState) -> None:
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
    return next(iter(matches))


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


def secondary_transactions(
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
    matches: tuple[SecondaryMissionCardState, ...] = tuple(
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
    return next(iter(matches))


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
    transactions = secondary_transactions(
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
    transactions = secondary_transactions(
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
    before = secondary_transactions(
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
    after = secondary_transactions(
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


def _assert_private_scoring_authority_commitments_are_absent(
    payload: object,
    *,
    state: GameState,
) -> None:
    private_values = {
        value
        for authority in state.objective_control_record_authorities
        for value in (
            authority.boundary_checkpoint.checkpoint_id,
            authority.boundary_checkpoint.checkpoint_hash,
        )
    }
    private_values.update(
        value
        for evidence in state.secondary_scoring_state_evidence_records
        for value in (evidence.evidence_id, evidence.evidence_hash)
    )
    for ledger in state.victory_point_ledgers:
        for transaction in ledger.transactions:
            metadata = transaction.metadata
            if not isinstance(metadata, dict):
                continue
            for key in (
                "scoring_commit_checkpoint_id",
                "scoring_commit_checkpoint_hash",
                "secondary_scoring_state_evidence_id",
                "secondary_scoring_state_evidence_hash",
            ):
                value = metadata.get(key)
                if type(value) is str:
                    private_values.add(value)
    serialized = json.dumps(payload, sort_keys=True)
    assert all(value not in serialized for value in private_values)


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


def lifecycle_row(
    secondary_mission_id: str,
    *,
    mode: str,
    scoring_player_id: str,
) -> SecondaryMissionLifecycleCertificationRow:
    matches = tuple(
        row
        for row in STEP6G_LIFECYCLE_CERTIFICATION_ROWS
        if row.secondary_mission_id == secondary_mission_id
        and row.mode == mode
        and row.scoring_player_id == scoring_player_id
    )
    if len(matches) != 1:
        raise AssertionError("Step 6G review fixture could not resolve a certification row.")
    return matches[0]


def score_certified_row_from_state(
    row: SecondaryMissionLifecycleCertificationRow,
) -> tuple[GameState, EventLog, SecondaryPositiveExpectation]:
    session, _payload, expectation = secondary_certification_session(row)
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
