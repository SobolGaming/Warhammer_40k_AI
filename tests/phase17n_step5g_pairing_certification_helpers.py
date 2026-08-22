from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from typing import cast

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
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.event_log import EventLog, JsonValue, validate_json_value
from warhammer40k_core.engine.fight_order import (
    ELIGIBLE_TO_FIGHT_PASS_OPTION_ID,
    FIGHT_ACTIVATION_DECISION_TYPE,
    FightPhaseState,
    FightsFirstRegistry,
)
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.mission_decisions import TACTICAL_SECONDARY_SCORE_DECISION_TYPE
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.missions import mission_scoring_policies_from_setup
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
)
from warhammer40k_core.engine.objective_control import ObjectiveControlTiming
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage, LifecycleStatusKind
from warhammer40k_core.engine.primary_mission_choices import (
    SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE,
)
from warhammer40k_core.engine.primary_scoring_pairing_certification import (
    EventCompanionPairingLifecycleCertificationRow,
)
from warhammer40k_core.engine.primary_scoring_state_evidence import (
    PrimaryScoringBoundaryKind,
    PrimaryScoringStateEvidence,
)
from warhammer40k_core.engine.replay import (
    ReplayArtifact,
    ReplayArtifactPayload,
    ReplayRunner,
    ReplayRunStatus,
    replay_event_log_hash,
)
from warhammer40k_core.engine.scoring import VictoryPointSourceKind

EVENT_COMPANION_FORCE_DISPOSITION_IDS = (
    "take-and-hold",
    "purge-the-foe",
    "disruption",
    "reconnaissance",
    "priority-assets",
)
SCORING_PLAYER_IDS = ("player-a", "player-b")


def assert_pairing_scores_through_lifecycle_restore_views_and_replay(
    row: EventCompanionPairingLifecycleCertificationRow,
    *,
    scoring_player_id: str,
) -> None:
    session, initial_payload = pairing_certification_session(
        row,
        scoring_player_id=scoring_player_id,
    )
    initial_state = session.lifecycle.state
    assert initial_state is not None
    assert initial_state.active_player_id == scoring_player_id
    drive_pairing_scoring_through_facade(session, scoring_player_id=scoring_player_id)

    state = session.lifecycle.state
    assert state is not None
    setup = setup_for_lifecycle_row(row)
    expected_mission_id = (
        row.attacker_primary_mission_id
        if scoring_player_id == "player-a"
        else row.defender_primary_mission_id
    )
    assert setup.primary_mission_id_for_player(scoring_player_id) == expected_mission_id
    policies = mission_scoring_policies_from_setup(setup)
    evidence = ordinary_turn_end_evidence_for_player(state, scoring_player_id)
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
        assert_public_primary_commitments_are_opaque(
            view["public_victory_point_ledgers"],
            state,
        )

    player_a_events = session.events_since(EventStreamCursor(0), viewer_player_id="player-a")
    player_b_events = session.events_since(EventStreamCursor(0), viewer_player_id="player-b")
    assert player_a_events["viewer_player_id"] == "player-a"
    assert player_b_events["viewer_player_id"] == "player-b"
    assert player_a_events["events"]
    assert player_b_events["events"]

    artifact_payload = cast(
        ReplayArtifactPayload,
        json.loads(
            json.dumps(
                session.replay_artifact(
                    artifact_id=(f"replay:phase17n-step5g:{row.layout_id}:{scoring_player_id}")
                ),
                sort_keys=True,
            )
        ),
    )
    artifact = ReplayArtifact.from_payload(artifact_payload)
    assert artifact.to_payload() == artifact_payload
    assert artifact.initial_lifecycle_payload == initial_payload
    assert artifact.decision_records
    assert artifact.decision_records[0].request.decision_type == FIGHT_ACTIVATION_DECISION_TYPE
    assert (
        artifact.decision_records[0].result.selected_option_id == ELIGIBLE_TO_FIGHT_PASS_OPTION_ID
    )
    assert artifact.event_records
    assert any(
        event.event_type == "primary_scoring_commit_checkpoint_recorded"
        for event in artifact.event_records
    )

    replay_result = ReplayRunner.from_payload(deepcopy(artifact_payload)).run()
    assert replay_result.status is ReplayRunStatus.REPRODUCED
    assert replay_result.reproduced_exactly
    assert replay_result.diagnostics == ()
    assert replay_result.reproduced_decision_count == len(artifact.decision_records)
    assert replay_result.reproduced_event_count == session.event_record_count()
    assert replay_result.final_event_log_hash == replay_event_log_hash(session.lifecycle)


def pairing_certification_session(
    row: EventCompanionPairingLifecycleCertificationRow,
    *,
    scoring_player_id: str,
) -> tuple[LocalGameSession, GameLifecyclePayload]:
    if scoring_player_id not in SCORING_PLAYER_IDS:
        raise AssertionError("Step 5G pairing fixture scoring_player_id is unsupported.")
    setup = setup_for_lifecycle_row(row)
    state = phase17n_state_with_setup(
        setup=setup,
        active_player_id=scoring_player_id,
        phase=BattlePhase.FIGHT,
        battle_round=2,
    )
    seed_replayable_fight_phase(state)
    decisions = record_primary_turn_start_evidence_for_fixture(state)
    config = pairing_certification_config(row=row, setup_game_id=state.game_id)
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
    session = LocalGameSession(lifecycle=lifecycle)
    status = session.advance_until_decision_or_terminal()
    request = status.decision_request
    if request is None or request.decision_type != FIGHT_ACTIVATION_DECISION_TYPE:
        raise AssertionError("Step 5G replay fixture requires a Fight activation DecisionRequest.")
    if ELIGIBLE_TO_FIGHT_PASS_OPTION_ID not in {option.option_id for option in request.options}:
        raise AssertionError("Step 5G replay fixture requires the engine-enumerated Fight pass.")
    initial_payload = deepcopy(session.lifecycle.to_payload())
    return session, initial_payload


_ALLOWED_SCORING_DECISION_TYPES = frozenset(
    {
        FIGHT_ACTIVATION_DECISION_TYPE,
        SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE,
        TACTICAL_SECONDARY_SCORE_DECISION_TYPE,
    }
)


def drive_pairing_scoring_through_facade(
    session: LocalGameSession,
    *,
    scoring_player_id: str,
) -> None:
    for step_index in range(24):
        pending = session.lifecycle.pending_decision_request()
        if pending is not None and pending.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE:
            proposal = MovementProposalRequest.from_decision_request_payload(pending.payload)
            context = cast(dict[str, JsonValue], proposal.context)
            status = session.submit_parameterized_payload(
                request_id=pending.request_id,
                payload=validate_json_value(
                    {
                        "proposal_request_id": proposal.request_id,
                        "proposal_kind": proposal.proposal_kind.value,
                        "unit_instance_id": proposal.unit_instance_id,
                        "movement_phase_action": proposal.movement_phase_action,
                        "movement_mode": context["movement_mode"],
                    }
                ),
                result_id=(f"phase17n-step5g-{scoring_player_id}-movement-{step_index:02d}"),
            )
            if status.status_kind in {
                LifecycleStatusKind.INVALID,
                LifecycleStatusKind.UNSUPPORTED,
            }:
                raise AssertionError(
                    "Step 5G pairing certification rejected a legal Fight movement response."
                )
            continue
        if pending is not None and pending.decision_type in _ALLOWED_SCORING_DECISION_TYPES:
            if not pending.options:
                raise AssertionError(
                    "Step 5G pairing certification requires a finite choice option."
                )
            if pending.decision_type == FIGHT_ACTIVATION_DECISION_TYPE:
                option_id = ELIGIBLE_TO_FIGHT_PASS_OPTION_ID
            elif pending.decision_type == TACTICAL_SECONDARY_SCORE_DECISION_TYPE:
                option_id = next(
                    (
                        option.option_id
                        for option in pending.options
                        if option.option_id.startswith("retain:")
                    ),
                    pending.options[0].option_id,
                )
            else:
                option_id = pending.options[0].option_id
            status = session.submit_option(
                request_id=pending.request_id,
                option_id=option_id,
                result_id=(f"phase17n-step5g-{scoring_player_id}-choice-{step_index:02d}"),
            )
            if status.status_kind in {
                LifecycleStatusKind.INVALID,
                LifecycleStatusKind.UNSUPPORTED,
            }:
                raise AssertionError("Step 5G pairing certification rejected a legal choice.")
            continue
        state = session.lifecycle.state
        if state is not None and ordinary_turn_end_evidence_for_player_or_none(
            state,
            scoring_player_id,
        ):
            return
        if pending is not None:
            raise AssertionError(
                "Step 5G pairing certification encountered an unexpected pending decision "
                f"{pending.decision_type} before scoring."
            )
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


def pairing_certification_config(
    *,
    row: EventCompanionPairingLifecycleCertificationRow,
    setup_game_id: str,
) -> GameConfig:
    setup = setup_for_lifecycle_row(row)
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
                            *EVENT_COMPANION_FORCE_DISPOSITION_IDS,
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


def setup_for_lifecycle_row(
    row: EventCompanionPairingLifecycleCertificationRow,
) -> MissionSetup:
    return phase17n_event_setup(
        layout_id=row.layout_id,
        attacker_force_disposition_id=row.attacker_force_disposition_id,
        defender_force_disposition_id=row.defender_force_disposition_id,
    )


def seed_replayable_fight_phase(state: GameState) -> None:
    active_player_id = state.active_player_id
    if active_player_id is None:
        raise AssertionError("Step 5G replay fixture requires an active player.")
    active_unit = next(
        unit
        for army in state.army_definitions
        if army.player_id == active_player_id
        for unit in army.units
    )
    state.replace_fight_phase_state(
        FightPhaseState.start(
            battle_round=state.battle_round,
            active_player_id=active_player_id,
            policy=state.ruleset_descriptor_for_runtime_policy().fight_policy,
            engaged_at_fight_step_start_unit_ids=(active_unit.unit_instance_id,),
            fights_first_registry=FightsFirstRegistry.from_state(state),
        )
    )
    state.stage = GameLifecycleStage.BATTLE


def ordinary_turn_end_evidence_for_player_or_none(
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


def ordinary_turn_end_evidence_for_player(
    state: GameState,
    scoring_player_id: str,
) -> PrimaryScoringStateEvidence:
    evidence = ordinary_turn_end_evidence_for_player_or_none(state, scoring_player_id)
    if evidence is None:
        raise AssertionError(
            "Step 5G pairing certification did not persist ordinary turn-end evidence "
            f"for {scoring_player_id}."
        )
    return evidence


def assert_public_primary_commitments_are_opaque(
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
