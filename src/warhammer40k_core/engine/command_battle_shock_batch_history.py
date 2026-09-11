from __future__ import annotations

from typing import cast

from warhammer40k_core.engine.command_battle_shock_candidates import (
    CommandBattleShockCandidate,
    CommandBattleShockCandidatePayload,
    command_battle_shock_request_id,
)
from warhammer40k_core.engine.command_battle_shock_history_helpers import (
    raw_result_request_id,
    sequencing_request_conflict_id,
)
from warhammer40k_core.engine.command_battle_shock_phase_authority import (
    command_battle_shock_sequencing_context,
    command_battle_shock_sequencing_participants,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rule_trigger_state import RuleTriggerHistory
from warhammer40k_core.engine.timing_batch_runtime import (
    TIMING_BATCH_EVENT_TYPE,
    timing_batch_from_event,
)
from warhammer40k_core.engine.timing_batch_state import TimingBatch


def validate_command_test_batches(
    *, state: GameState, decisions: DecisionController, history: RuleTriggerHistory
) -> None:
    """Bind timing populations and completion to P08's authenticated test snapshots."""
    remaining = {
        batch.batch_id
        for batch in history.batches
        if batch.context.timing_window.descriptor.descriptor_id == "command-battle-shock-test-order"
    }
    events = decisions.event_log.records
    for snapshot_index, event in enumerate(events):
        if event.event_type != "battle_shock_step_snapshot_created":
            continue
        payload = event.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Command test batch snapshot must be an object.")
        game_id, battle_round, active = (
            payload.get("game_id"),
            payload.get("battle_round"),
            payload.get("active_player_id"),
        )
        raw = payload.get("battle_shock_candidate_inventory")
        if (
            game_id != state.game_id
            or type(battle_round) is not int
            or type(active) is not str
            or not isinstance(raw, list)
            or any(not isinstance(row, dict) for row in raw)
        ):
            raise GameLifecycleError("Command test batch snapshot context drifted.")
        candidates = tuple(
            CommandBattleShockCandidate.from_payload(cast(CommandBattleShockCandidatePayload, row))
            for row in raw
        )
        required = tuple(candidate for candidate in candidates if candidate.test_reason is not None)
        context = command_battle_shock_sequencing_context(
            game_id=state.game_id,
            battle_round=battle_round,
            active_player_id=active,
            player_ids=state.player_ids,
        )
        batches = tuple(
            batch for batch in history.batches if batch.context.conflict_id == context.conflict_id
        )
        result_ids = {
            command_battle_shock_request_id(
                battle_round=battle_round,
                active_player_id=active,
                unit_instance_id=candidate.unit_instance_id,
                reason=candidate.test_reason,
            ): f"command-battle-shock-test:{candidate.unit_instance_id}"
            for candidate in required
            if candidate.test_reason is not None
        }
        if not batches:
            # A captured unsupported population can legally stop before selecting any test.
            if any(
                event.event_type == "battle_shock_test_resolved"
                and raw_result_request_id(event.payload) in result_ids
                for event in events
            ) or any(
                sequencing_request_conflict_id(request)
                == f"timing-batch:{context.conflict_id}:generation-0:tier-0"
                for request in (
                    *decisions.queue.pending_requests,
                    *(record.request for record in decisions.records),
                )
            ):
                raise GameLifecycleError("Command test results lack their original timing batch.")
            continue
        if len(batches) != 1 or not required:
            raise GameLifecycleError("Command test timing population differs from its snapshot.")
        batch = batches[0]
        if (
            batch.context != context
            or batch.generation != 0
            or batch.deferred_participants
            or batch.participants
            != command_battle_shock_sequencing_participants(
                active_player_id=active,
                candidates=required,
            )
        ):
            raise GameLifecycleError("Command test timing source population drifted.")
        remaining.discard(batch.batch_id)
        _validate_test_transitions(decisions, batch, snapshot_index, result_ids)
        for trigger in history.observed:
            source = trigger.context
            if not isinstance(source, dict):
                raise GameLifecycleError("Command test trigger context must be an object.")
            request_id = raw_result_request_id(source)
            if request_id in result_ids and (
                trigger.parent_batch_id != batch.batch_id
                or trigger.parent_participant_id != result_ids[request_id]
            ):
                raise GameLifecycleError(
                    "Command outcome bypasses its original required-test batch."
                )
    if remaining:
        raise GameLifecycleError("Command test timing batch lacks its source snapshot.")


def _validate_test_transitions(
    decisions: DecisionController,
    batch: TimingBatch,
    snapshot_index: int,
    result_ids: dict[str, str],
) -> None:
    selected_at: int | None = None
    events = decisions.event_log.records
    for index, event in enumerate(events):
        if event.event_type != TIMING_BATCH_EVENT_TYPE:
            continue
        current = timing_batch_from_event(event)
        if current.batch_id != batch.batch_id:
            continue
        if index <= snapshot_index or not isinstance(event.payload, dict):
            raise GameLifecycleError("Command test timing precedes its source snapshot.")
        transition = event.payload["transition"]
        if transition == "selected":
            selected_at = index
        elif transition == "completed":
            identifier = current.completed_participant_ids[-1]
            matches = tuple(
                resolved_index
                for resolved_index, resolved in enumerate(events[:index])
                if resolved.event_type == "battle_shock_test_resolved"
                and (request_id := raw_result_request_id(resolved.payload)) is not None
                and result_ids.get(request_id) == identifier
            )
            if selected_at is None or len(matches) != 1 or matches[0] <= selected_at:
                raise GameLifecycleError("Command timing rule completed before its required test.")
            selected_at = None
        elif transition != "opened":
            raise GameLifecycleError(
                "Command required tests cannot be deferred or made ineligible."
            )
