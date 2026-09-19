"""Accepted moves and Surge locks scoped to an actual player's phase occurrence."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import msgspec

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.engine.battlefield_state import BattlefieldRuntimeState
    from warhammer40k_core.engine.decision_record import DecisionRecord
    from warhammer40k_core.engine.game_state import GameState


class PhaseMovementRecord(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    event_id: str
    battle_round: int
    turn_player_id: str
    phase: BattlePhase
    unit_instance_id: str
    model_instance_ids: tuple[str, ...]
    is_surge: bool
    is_ingress: bool
    setup_kind: BattlefieldPlacementKind | None

    def __post_init__(self) -> None:
        validate = IdentifierValidator(GameLifecycleError)
        for name in ("event_id", "turn_player_id", "unit_instance_id"):
            validate(name, getattr(self, name))
        if type(self.battle_round) is not int or self.battle_round < 1:
            raise GameLifecycleError("Phase movement requires a positive round.")
        if type(self.phase) is not BattlePhase or type(self.is_surge) is not bool:
            raise GameLifecycleError("Phase movement requires a typed phase and Surge flag.")
        if type(self.is_ingress) is not bool or (
            self.is_ingress and (self.setup_kind is None or self.is_surge)
        ):
            raise GameLifecycleError("Phase movement requires a valid Ingress classification.")
        if self.setup_kind is not None and (
            type(self.setup_kind) is not BattlefieldPlacementKind or self.is_surge
        ):
            raise GameLifecycleError("Phase movement setup kind is invalid.")
        if (
            not self.model_instance_ids
            or tuple(sorted(set(self.model_instance_ids))) != self.model_instance_ids
        ):
            raise GameLifecycleError("Phase movement requires sorted unique physical model IDs.")
        for model_id in self.model_instance_ids:
            validate("model_instance_id", model_id)

    def to_payload(self) -> dict[str, JsonValue]:
        return {
            "event_id": self.event_id,
            "battle_round": self.battle_round,
            "turn_player_id": self.turn_player_id,
            "phase": self.phase.value,
            "unit_instance_id": self.unit_instance_id,
            "model_instance_ids": list(self.model_instance_ids),
            "is_surge": self.is_surge,
            "is_ingress": self.is_ingress,
            "setup_kind": None if self.setup_kind is None else self.setup_kind.value,
        }

    @classmethod
    def from_payload(cls, value: object) -> PhaseMovementRecord:
        try:
            return msgspec.convert(value, type=cls, strict=True)
        except (msgspec.ValidationError, TypeError) as exc:
            raise GameLifecycleError("Phase movement history schema drifted.") from exc


def current_unit_moves(state: GameState, unit_instance_id: str) -> tuple[PhaseMovementRecord, ...]:
    view = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    models = {model.model_instance_id for model in view.alive_models()}
    return tuple(
        row
        for row in state.phase_movement_history
        if (
            row.battle_round == state.battle_round
            and row.turn_player_id == state.active_player_id
            and row.phase is state.current_battle_phase
            and (
                row.unit_instance_id == view.unit_instance_id
                or models.intersection(row.model_instance_ids)
            )
        )
    )


def surge_locked(state: GameState, unit_instance_id: str) -> bool:
    # No unit can be locked until this phase occurrence contains a Surge.
    # Ordinary movement must not pay for reconstructing attached-unit identity.
    if not any(
        row.is_surge
        and row.battle_round == state.battle_round
        and row.turn_player_id == state.active_player_id
        and row.phase is state.current_battle_phase
        for row in state.phase_movement_history
    ):
        return False
    return any(row.is_surge for row in current_unit_moves(state, unit_instance_id))


def validate_battlefield_movement_locks(
    *,
    state: GameState,
    updated: BattlefieldRuntimeState,
) -> None:
    """Backstop all movement owners at the authoritative placement mutation boundary."""
    from warhammer40k_core.engine.ingress_lifetimes import validate_ingress_movement_mutation

    validate_ingress_movement_mutation(state=state, updated=updated)
    locked_models = {
        model_id
        for row in state.phase_movement_history
        if row.is_surge
        and row.battle_round == state.battle_round
        and row.turn_player_id == state.active_player_id
        and row.phase is state.current_battle_phase
        for model_id in row.model_instance_ids
    }
    if not locked_models:
        return
    current = state.battlefield_state
    if current is None:
        raise GameLifecycleError("Surge movement locks require battlefield authority.")
    before = {
        model.model_instance_id: model.pose
        for army in current.placed_armies
        for unit in army.unit_placements
        for model in unit.model_placements
        if model.model_instance_id in locked_models
    }
    for army in updated.placed_armies:
        for unit in army.unit_placements:
            for model in unit.model_placements:
                if (
                    model.model_instance_id in locked_models
                    and before.get(model.model_instance_id) != model.pose
                ):
                    raise GameLifecycleError("surge_movement_locked_this_phase")


def completion_phase_record(
    *, state: GameState, event: EventRecord, turn_player_id: str
) -> PhaseMovementRecord | None:
    from warhammer40k_core.engine.battlefield_state import (
        BattlefieldTransitionBatch,
        BattlefieldTransitionBatchPayload,
        UnitPlacement,
        UnitPlacementPayload,
    )
    from warhammer40k_core.engine.model_movement_history import distances_from_completion

    payload = event.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Phase movement requires completion payload.")
    if event.event_type == "movement_activation_completed" and payload.get(
        "movement_phase_action"
    ) in {"remain_stationary", "ingress", "disembark", "combat_disembark"}:
        return None
    if event.event_type == "return_on_death_set_back_up_completed":
        if type(payload.get("unit_set_up")) is not bool:
            raise GameLifecycleError("Returned-unit setup requires unit presence evidence.")
        if not payload["unit_set_up"]:
            return None
        raw_placement = payload.get("placement")
        if not isinstance(raw_placement, dict):
            raise GameLifecycleError("Returned-unit setup requires placement evidence.")
        placement = UnitPlacement.from_payload(cast(UnitPlacementPayload, raw_placement))
        model_ids = tuple(sorted(row.model_instance_id for row in placement.model_placements))
        setup_kind = BattlefieldPlacementKind.RETURN_TO_BATTLEFIELD
    elif event.event_type in {"unit_disembarked", "reinforcement_unit_arrived"}:
        raw = payload.get("transition_batch")
        if not isinstance(raw, dict):
            raise GameLifecycleError("Phase setup history requires placement evidence.")
        transition = BattlefieldTransitionBatch.from_payload(
            cast(BattlefieldTransitionBatchPayload, raw)
        )
        model_ids = tuple(sorted(row.model_instance_id for row in transition.placements))
        kinds = {row.placement_kind for row in transition.placements}
        if len(kinds) != 1:
            raise GameLifecycleError("Phase setup history requires one placement kind.")
        setup_kind = kinds.pop()
    else:
        setup_kind = None
        model_ids = tuple(
            row.model_instance_id
            for row in distances_from_completion(
                event,
                turn_player_id=turn_player_id,
            )
        )
        # Ineligible Fight movement records its skipped step with no path.
        # A witnessed zero-distance move still has per-model distance rows.
        if event.event_type == "fight_movement_completed" and not model_ids:
            resolution = payload.get("resolution")
            if isinstance(resolution, dict) and resolution.get("witness") is None:
                return None
    if not model_ids:
        raise GameLifecycleError("Phase movement requires physical model evidence.")
    return PhaseMovementRecord(
        event_id=event.event_id,
        battle_round=cast(int, payload["battle_round"]),
        turn_player_id=turn_player_id,
        phase=BattlePhase(cast(str, payload["phase"])),
        unit_instance_id=cast(str, payload["unit_instance_id"]),
        model_instance_ids=model_ids,
        is_surge=event.event_type == "triggered_movement_resolved"
        and payload.get("triggered_movement_kind") == "surge",
        is_ingress=event.event_type == "reinforcement_unit_arrived",
        setup_kind=setup_kind,
    )


def validate_phase_movement_history(*, state: GameState, events: tuple[EventRecord, ...]) -> None:
    from warhammer40k_core.engine.interrupted_charge import charge_turn_owner_at_event
    from warhammer40k_core.engine.move_completion_triggers import MOVE_COMPLETION_EVENT_TYPES

    expected: list[PhaseMovementRecord] = []
    for index, event in enumerate(events):
        if event.event_type not in (
            *MOVE_COMPLETION_EVENT_TYPES,
            "return_on_death_set_back_up_completed",
        ):
            continue
        if not isinstance(event.payload, dict) or not isinstance(
            event.payload.get("active_player_id"), str
        ):
            raise GameLifecycleError("Phase movement completion requires its turn owner.")
        owner = cast(str, event.payload["active_player_id"])
        if event.event_type == "charge_move_completed":
            owner = charge_turn_owner_at_event(
                event_records=events, event_index=index, actor_id=owner
            )
        row = completion_phase_record(state=state, event=event, turn_player_id=owner)
        if row is not None:
            from warhammer40k_core.engine.ingress_lifetimes import validate_ingress_movement_history

            validate_ingress_movement_history(state, expected, row)
            for prior in expected:
                same_occurrence = (prior.battle_round, prior.turn_player_id, prior.phase) == (
                    row.battle_round,
                    row.turn_player_id,
                    row.phase,
                )
                same_unit = prior.unit_instance_id == row.unit_instance_id or bool(
                    set(prior.model_instance_ids).intersection(row.model_instance_ids)
                )
                if same_occurrence and same_unit and (prior.is_surge or row.is_surge):
                    raise GameLifecycleError(
                        "Surge phase movement history violates the movement lock."
                    )
            expected.append(row)
    if state.phase_movement_history != expected:
        raise GameLifecycleError("Phase movement history differs from accepted movement evidence.")


def validate_phase_movement_state(state: GameState) -> None:
    rows = state.phase_movement_history
    if type(rows) is not list or any(type(row) is not PhaseMovementRecord for row in rows):
        raise GameLifecycleError("Phase movement requires typed history.")
    if len({row.event_id for row in rows}) != len(rows) or any(
        row.turn_player_id not in state.player_ids or row.battle_round > state.battle_round
        for row in rows
    ):
        raise GameLifecycleError("Phase movement history identity drifted.")


def validate_return_on_death_setup_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    """Authenticate setup classification before trusting completion-derived history.

    The shared timeline authenticates return decisions, pending occurrences and
    destruction causes, then reverses subsequent mutations. The completion flag
    is only an assertion of that independently reconstructed pre-return state.
    """
    from warhammer40k_core.engine.fight_model_authority_history import (
        build_model_authority_timeline,
        historical_rules_unit_model_ids,
    )
    from warhammer40k_core.engine.return_on_death import (
        RETURN_ON_DEATH_SET_BACK_UP_COMPLETED_EVENT_TYPE,
        PendingReturnOnDeath,
        PendingReturnOnDeathPayload,
    )

    completions = tuple(
        (index, event)
        for index, event in enumerate(event_records)
        if event.event_type == RETURN_ON_DEATH_SET_BACK_UP_COMPLETED_EVENT_TYPE
    )
    if not completions:
        return
    timeline = build_model_authority_timeline(
        state=state, event_records=event_records, decision_records=decision_records
    )
    for index, event in completions:
        payload = event.payload
        if not isinstance(payload, dict) or not isinstance(payload.get("pending"), dict):
            raise GameLifecycleError("Return-on-death setup requires pending authority.")
        # The timeline has bound this pending occurrence to the accepted request,
        # roll, placement and stored pending state. Do not select the rules unit
        # from the completion's unauthenticated unit_instance_id.
        pending = PendingReturnOnDeath.from_payload(
            cast(PendingReturnOnDeathPayload, payload["pending"])
        )
        view = rules_unit_view_by_id(
            state=state, unit_instance_id=pending.destroyed_unit_instance_id
        )
        if payload.get("unit_instance_id") != view.unit_instance_id:
            raise GameLifecycleError("Return-on-death setup rules-unit authority drifted.")
        model_ids = historical_rules_unit_model_ids(
            state=state, event_records=event_records, unit_instance_id=view.unit_instance_id
        )
        unit_set_up = not any(
            timeline.has_living_model_before_event(model_instance_id=model_id, event_index=index)
            for model_id in sorted(model_ids)
        )
        if payload.get("unit_set_up") is not unit_set_up:
            raise GameLifecycleError("Return-on-death setup differs from pre-return authority.")
