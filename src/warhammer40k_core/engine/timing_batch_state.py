from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Self, TypedDict

from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.sequencing import (
    SequencingConflictContext,
    SequencingConflictContextPayload,
    SequencingParticipant,
    SequencingParticipantPayload,
    eligible_sequencing_participants,
)


class TimingBatchPayload(TypedDict):
    context: SequencingConflictContextPayload
    generation: int
    participants: list[SequencingParticipantPayload]
    completed_participant_ids: list[str]
    selected_participant_id: str | None
    deferred_participants: list[SequencingParticipantPayload]


@dataclass(frozen=True, slots=True)
class TimingBatch:
    """A fixed timing population, one active rule, and a subsequent trigger population."""

    context: SequencingConflictContext
    generation: int
    participants: tuple[SequencingParticipant, ...]
    completed_participant_ids: tuple[str, ...] = ()
    selected_participant_id: str | None = None
    deferred_participants: tuple[SequencingParticipant, ...] = ()

    def __post_init__(self) -> None:
        if type(self.context) is not SequencingConflictContext:
            raise GameLifecycleError("Timing batch requires a conflict context.")
        if type(self.generation) is not int or self.generation < 0:
            raise GameLifecycleError("Timing batch generation must be a non-negative integer.")
        if type(self.participants) is not tuple or not self.participants:
            raise GameLifecycleError("Timing batch requires an immutable participant population.")
        if type(self.deferred_participants) is not tuple:
            raise GameLifecycleError("Timing batch deferred population must be a tuple.")
        all_participants = self.participants + self.deferred_participants
        # Shared source/owner/duplicate validation applies before a batch can be restored.
        eligible_sequencing_participants(context=self.context, participants=all_participants)
        participant_ids = tuple(participant.participant_id for participant in self.participants)
        if (
            type(self.completed_participant_ids) is not tuple
            or any(type(identifier) is not str for identifier in self.completed_participant_ids)
            or len(set(self.completed_participant_ids)) != len(self.completed_participant_ids)
            or not set(self.completed_participant_ids).issubset(participant_ids)
        ):
            raise GameLifecycleError("Timing batch completed prefix is invalid.")
        remaining = self.participants
        for identifier in self.completed_participant_ids:
            eligible = eligible_sequencing_participants(
                context=self.context, participants=remaining
            )
            if identifier not in {participant.participant_id for participant in eligible}:
                raise GameLifecycleError("Timing batch completed prefix violates tier authority.")
            remaining = tuple(
                participant for participant in remaining if participant.participant_id != identifier
            )
        if self.selected_participant_id is not None:
            if type(self.selected_participant_id) is not str:
                raise GameLifecycleError("Timing batch selected participant must be an identifier.")
            if self.selected_participant_id not in {
                participant.participant_id for participant in self.eligible_participants()
            }:
                raise GameLifecycleError("Timing batch selected participant is not eligible.")

    @classmethod
    def open(
        cls, *, context: SequencingConflictContext, participants: tuple[SequencingParticipant, ...]
    ) -> Self:
        return cls(context=context, generation=0, participants=participants)

    @property
    def batch_id(self) -> str:
        return f"timing-batch:{self.context.conflict_id}:generation-{self.generation}"

    @property
    def current_batch_complete(self) -> bool:
        return len(self.completed_participant_ids) == len(self.participants)

    def eligible_participants(self) -> tuple[SequencingParticipant, ...]:
        remaining = tuple(
            participant
            for participant in self.participants
            if participant.participant_id not in self.completed_participant_ids
        )
        if not remaining:
            return ()
        return eligible_sequencing_participants(context=self.context, participants=remaining)

    def select(self, participant_id: str) -> Self:
        if self.selected_participant_id is not None:
            raise GameLifecycleError("Timing batch already has a selected rule to finish.")
        if participant_id not in {
            participant.participant_id for participant in self.eligible_participants()
        }:
            raise GameLifecycleError("Timing batch selection is not eligible in the current tier.")
        return replace(self, selected_participant_id=participant_id)

    def complete(self, participant_id: str) -> Self:
        if self.selected_participant_id != participant_id:
            raise GameLifecycleError("Only the selected timing rule can complete.")
        return replace(
            self,
            completed_participant_ids=(*self.completed_participant_ids, participant_id),
            selected_participant_id=None,
        )

    def defer(self, participants: tuple[SequencingParticipant, ...]) -> Self:
        if self.current_batch_complete:
            raise GameLifecycleError("A completed timing batch cannot acquire new triggers.")
        return replace(self, deferred_participants=(*self.deferred_participants, *participants))

    def release_deferred(self) -> Self | None:
        if not self.current_batch_complete:
            raise GameLifecycleError("Deferred rules cannot trigger before the batch completes.")
        if not self.deferred_participants:
            return None
        return type(self)(
            context=self.context,
            generation=self.generation + 1,
            participants=self.deferred_participants,
        )

    def to_payload(self) -> TimingBatchPayload:
        return {
            "context": self.context.to_payload(),
            "generation": self.generation,
            "participants": [participant.to_payload() for participant in self.participants],
            "completed_participant_ids": list(self.completed_participant_ids),
            "selected_participant_id": self.selected_participant_id,
            "deferred_participants": [
                participant.to_payload() for participant in self.deferred_participants
            ],
        }

    @classmethod
    def from_payload(cls, payload: TimingBatchPayload) -> Self:
        if set(payload) != {
            "context",
            "generation",
            "participants",
            "completed_participant_ids",
            "selected_participant_id",
            "deferred_participants",
        }:
            raise GameLifecycleError("Timing batch payload schema drifted.")
        return cls(
            context=SequencingConflictContext.from_payload(payload["context"]),
            generation=payload["generation"],
            participants=tuple(
                SequencingParticipant.from_payload(row) for row in payload["participants"]
            ),
            completed_participant_ids=tuple(payload["completed_participant_ids"]),
            selected_participant_id=payload["selected_participant_id"],
            deferred_participants=tuple(
                SequencingParticipant.from_payload(row) for row in payload["deferred_participants"]
            ),
        )
