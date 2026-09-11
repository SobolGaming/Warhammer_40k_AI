from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.sequencing import SequencingParticipant, SequencingParticipantPayload
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.unit_move_completed_hooks import UnitMoveCompletedContext


@dataclass(frozen=True, slots=True)
class MoveCompletionRuleBinding:
    hook_id: str
    source_rule_id: str
    candidates: Callable[[UnitMoveCompletedContext], tuple[TimingRuleCandidate, ...]]
    participants_at_trigger: Callable[[UnitMoveCompletedContext], tuple[SequencingParticipant, ...]]
    resume: Callable[[UnitMoveCompletedContext, SequencingParticipant], TimingRuleCandidate | None]

    def __post_init__(self) -> None:
        validate = IdentifierValidator(GameLifecycleError)
        validate("hook_id", self.hook_id)
        validate("source_rule_id", self.source_rule_id)
        if (
            not callable(self.candidates)
            or not callable(self.participants_at_trigger)
            or not callable(self.resume)
        ):
            raise GameLifecycleError("Move rule binding requires candidate discovery.")


@dataclass(frozen=True, slots=True)
class MoveCompletionRuleRegistry:
    bindings: tuple[MoveCompletionRuleBinding, ...]

    def __post_init__(self) -> None:
        if type(self.bindings) is not tuple or any(
            type(binding) is not MoveCompletionRuleBinding for binding in self.bindings
        ):
            raise GameLifecycleError("Move rule registry requires typed bindings.")
        if len({binding.hook_id for binding in self.bindings}) != len(self.bindings):
            raise GameLifecycleError("Move rule registry has duplicate bindings.")

    def discover_for(self, context: UnitMoveCompletedContext) -> tuple[TimingRuleCandidate, ...]:
        if type(context) is not UnitMoveCompletedContext or context.decisions is None:
            raise GameLifecycleError("Move rule discovery requires its typed decision context.")
        before = (context.state.to_payload(), context.decisions.to_payload())
        found: list[TimingRuleCandidate] = []
        for binding in self.bindings:
            candidates = binding.candidates(context)
            if type(candidates) is not tuple or any(
                type(candidate) is not TimingRuleCandidate
                or candidate.participant.source_rule_id != binding.source_rule_id
                for candidate in candidates
            ):
                raise GameLifecycleError("Move rule candidate source authority drift.")
            found.extend(candidates)
        if before != (context.state.to_payload(), context.decisions.to_payload()):
            raise GameLifecycleError("Move rule candidate discovery mutated authoritative state.")
        if len({item.participant.participant_id for item in found}) != len(found):
            raise GameLifecycleError("Move rule candidate identity is duplicated.")
        return tuple(found)

    def capture_for(self, context: UnitMoveCompletedContext) -> None:
        decisions = context.decisions
        if decisions is None:
            raise GameLifecycleError("Move rule capture requires decisions.")
        records = decisions.event_log.records
        if (
            len(records) < 2
            or records[-2].event_id != context.trigger_event_id
            or records[-1].event_type != "rule_trigger_observed"
            or not isinstance(records[-1].payload, dict)
        ):
            raise GameLifecycleError("Move rules must be captured at their source observation.")
        source_context = records[-1].payload.get("context")
        if (
            not isinstance(source_context, dict)
            or source_context.get("trigger_event_id") != context.trigger_event_id
        ):
            raise GameLifecycleError("Move rule capture source observation identity drift.")
        if any(
            event.event_type == "move_rule_candidates_observed"
            and isinstance(event.payload, dict)
            and event.payload.get("trigger_event_id") == context.trigger_event_id
            for event in decisions.event_log.records
        ):
            raise GameLifecycleError("Move rule occurrence was already captured.")
        participants = self._participants_at_trigger(context)
        decisions.event_log.append(
            "move_rule_candidates_observed",
            validate_json_value(
                {
                    "game_id": context.state.game_id,
                    "trigger_event_id": context.trigger_event_id,
                    "hook_ids": [binding.hook_id for binding in self.bindings],
                    "participants": [participant.to_payload() for participant in participants],
                }
            ),
        )

    def candidates_for(self, context: UnitMoveCompletedContext) -> tuple[TimingRuleCandidate, ...]:
        if not self.bindings:
            return ()
        decisions = context.decisions
        if decisions is None:
            raise GameLifecycleError("Move rule continuation requires decisions.")
        records = tuple(
            event
            for event in decisions.event_log.records
            if event.event_type == "move_rule_candidates_observed"
            and isinstance(event.payload, dict)
            and event.payload.get("trigger_event_id") == context.trigger_event_id
        )
        if len(records) != 1 or not isinstance(records[0].payload, dict):
            raise GameLifecycleError("Move rules require their unique trigger-time population.")
        source_indices = tuple(
            index
            for index, event in enumerate(decisions.event_log.records)
            if event.event_id == context.trigger_event_id
        )
        if (
            len(source_indices) != 1
            or decisions.event_log.records.index(records[0]) != source_indices[0] + 2
        ):
            raise GameLifecycleError("Move rule capture lost its exact observation boundary.")
        payload = records[0].payload
        if (
            set(payload) != {"game_id", "trigger_event_id", "hook_ids", "participants"}
            or payload["game_id"] != context.state.game_id
            or payload["hook_ids"] != [binding.hook_id for binding in self.bindings]
            or not isinstance(payload["participants"], list)
        ):
            raise GameLifecycleError("Move rule capture schema or provider identity drift.")
        expected = self._participants_at_trigger(context)
        if payload["participants"] != [participant.to_payload() for participant in expected]:
            raise GameLifecycleError("Captured move rule population or source evidence drift.")
        before = (context.state.to_payload(), decisions.to_payload())
        found: list[TimingRuleCandidate] = []
        seen: set[str] = set()
        for raw in payload["participants"]:
            if not isinstance(raw, dict):
                raise GameLifecycleError("Move rule capture requires participant objects.")
            participant = SequencingParticipant.from_payload(
                cast(SequencingParticipantPayload, raw)
            )
            if participant.participant_id in seen:
                raise GameLifecycleError("Captured move rule occurrence is duplicated.")
            seen.add(participant.participant_id)
            bindings = tuple(
                binding
                for binding in self.bindings
                if binding.source_rule_id == participant.source_rule_id
            )
            if len(bindings) != 1:
                raise GameLifecycleError("Captured move rule has no unique loaded source.")
            candidate = bindings[0].resume(context, participant)
            if candidate is not None:
                if (
                    type(candidate) is not TimingRuleCandidate
                    or candidate.participant != participant
                ):
                    raise GameLifecycleError("Resumed move rule identity drift.")
                found.append(candidate)
        if before != (context.state.to_payload(), decisions.to_payload()):
            raise GameLifecycleError(
                "Move rule continuation discovery mutated authoritative state."
            )
        return tuple(found)

    def _participants_at_trigger(
        self, context: UnitMoveCompletedContext
    ) -> tuple[SequencingParticipant, ...]:
        decisions = context.decisions
        if decisions is None:
            raise GameLifecycleError("Move rule qualification requires decisions.")
        before = (context.state.to_payload(), decisions.to_payload())
        participants: list[SequencingParticipant] = []
        for binding in self.bindings:
            found = binding.participants_at_trigger(context)
            if type(found) is not tuple or any(
                type(participant) is not SequencingParticipant
                or participant.source_rule_id != binding.source_rule_id
                for participant in found
            ):
                raise GameLifecycleError("Move rule qualification source authority drift.")
            participants.extend(found)
        if len({participant.participant_id for participant in participants}) != len(participants):
            raise GameLifecycleError("Move rule qualification duplicated a participant.")
        if before != (context.state.to_payload(), decisions.to_payload()):
            raise GameLifecycleError("Move rule qualification mutated authoritative state.")
        return tuple(participants)
