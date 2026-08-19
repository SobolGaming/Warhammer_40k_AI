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
from tests.phase17n_secondary_mission_helpers import resolved_secondary_mission_selection_for_card
from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.event_log import EventLog
from warhammer40k_core.engine.fight_order import FightPhaseState, FightsFirstRegistry
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.mission_decisions import TACTICAL_SECONDARY_SCORE_DECISION_TYPE
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.missions import mission_scoring_policies_from_setup
from warhammer40k_core.engine.objective_control import ObjectiveControlTiming
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage, LifecycleStatusKind
from warhammer40k_core.engine.primary_mission_choices import (
    SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE,
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
    VictoryPointSourceKind,
)
from warhammer40k_core.engine.secondary_scoring_inventory import (
    SECONDARY_CARD_MODE_CERTIFICATION_COUNT,
    SECONDARY_LIFECYCLE_CERTIFICATION_COUNT,
    SECONDARY_MISSION_COUNT,
    SecondaryMissionLifecycleCertificationRow,
    secondary_mission_inventory_rows,
    secondary_mission_lifecycle_certification_rows,
)

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
    session, initial_payload = _secondary_certification_session(row)
    initial_state = session.lifecycle.state
    assert initial_state is not None
    assert initial_state.active_player_id == row.scoring_player_id
    _drive_secondary_scoring_through_facade(session, scoring_player_id=row.scoring_player_id)

    state = session.lifecycle.state
    assert state is not None
    policies = mission_scoring_policies_from_setup(_setup_for_layout())
    evidence = _ordinary_turn_end_evidence_for_player(state, row.scoring_player_id)
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
            "Step 6G secondary certification ordinary evidence is missing its "
            "objective-control record."
        )
    scoring_player_ids = policies.scoring_player_ids_for_record(
        record=record,
        turn_order=tuple(state.turn_order),
        end_of_battle=False,
    )
    assert row.scoring_player_id in scoring_player_ids

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


def _secondary_certification_session(
    row: SecondaryMissionLifecycleCertificationRow,
) -> tuple[LocalGameSession, GameLifecyclePayload]:
    setup = _setup_for_layout()
    state = phase17n_state_with_setup(
        setup=setup,
        active_player_id=row.scoring_player_id,
        phase=BattlePhase.FIGHT,
        battle_round=2,
    )
    _seed_certified_secondary(state, row)
    _seed_completed_fight_phase(state)
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
    return LocalGameSession(lifecycle=lifecycle), initial_payload


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
    scoring_player_id: str,
) -> None:
    for step_index in range(24):
        pending = session.lifecycle.pending_decision_request()
        if pending is not None and pending.decision_type in _ALLOWED_SCORING_DECISION_TYPES:
            if not pending.options:
                raise AssertionError("Step 6G secondary certification requires a finite option.")
            option_id = pending.options[0].option_id
            if pending.decision_type == TACTICAL_SECONDARY_SCORE_DECISION_TYPE:
                option_id = next(
                    (
                        option.option_id
                        for option in pending.options
                        if option.option_id.startswith("retain:")
                    ),
                    option_id,
                )
            status = session.submit_option(
                request_id=pending.request_id,
                option_id=option_id,
                result_id=(f"phase17n-step6g-{scoring_player_id}-choice-{step_index:02d}"),
            )
            if status.status_kind is LifecycleStatusKind.INVALID:
                raise AssertionError("Step 6G secondary certification rejected a legal choice.")
            continue
        state = session.lifecycle.state
        if state is not None and _ordinary_turn_end_evidence_for_player_or_none(
            state,
            scoring_player_id,
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
        "Step 6G secondary certification did not persist the scoring player's ordinary "
        "turn-end evidence."
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
                    unit_selections=(default_unit_selection("intercessor-unit-1"),),
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
