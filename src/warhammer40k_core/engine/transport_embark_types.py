"""Typed embark requests and outcomes; geometry remains in the shared validator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, NotRequired, Self, TypedDict

from warhammer40k_core.engine.battlefield_state import (
    BattlefieldTransitionBatch,
    BattlefieldTransitionBatchPayload,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.transport_disembark_state import (
    TransportMovementStatus,
    TransportRestrictionOverride,
    TransportRestrictionOverrideKind,
    TransportRestrictionOverridePayload,
    transport_movement_status_from_token,
    transport_restriction_override_kind_from_token,
)
from warhammer40k_core.engine.transport_disembark_state import (
    validate_transport_override_tuple as _validate_transport_override_tuple,
)
from warhammer40k_core.engine.transport_embark_context import (
    NoMovementEmbarkContext,
    NoMovementEmbarkContextPayload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.transports import (
        TransportCargoState,
        TransportCargoStatePayload,
        TransportOperationViolation,
        TransportOperationViolationPayload,
    )


class EmbarkSelectionPayload(TypedDict):
    player_id: str
    battle_round: int
    unit_instance_id: str
    transport_unit_instance_id: str
    movement_phase_action: str
    restriction_overrides: list[TransportRestrictionOverridePayload]
    source_context: NotRequired[NoMovementEmbarkContextPayload]


class EmbarkResolutionPayload(TypedDict):
    selection: EmbarkSelectionPayload
    is_valid: bool
    violations: list[TransportOperationViolationPayload]
    updated_cargo_state: TransportCargoStatePayload | None
    transition_batch: BattlefieldTransitionBatchPayload | None


@dataclass(frozen=True, slots=True)
class EmbarkSelection:
    player_id: str
    battle_round: int
    unit_instance_id: str
    transport_unit_instance_id: str
    movement_phase_action: TransportMovementStatus
    restriction_overrides: tuple[TransportRestrictionOverride, ...] = ()
    source_context: NoMovementEmbarkContext | None = None

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.transports import (
            _validate_identifier,  # pyright: ignore[reportPrivateUsage]
            _validate_positive_int,  # pyright: ignore[reportPrivateUsage]
        )

        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("EmbarkSelection player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("EmbarkSelection battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("EmbarkSelection unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "transport_unit_instance_id",
            _validate_identifier(
                "EmbarkSelection transport_unit_instance_id",
                self.transport_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "movement_phase_action",
            transport_movement_status_from_token(self.movement_phase_action),
        )
        if self.source_context is not None:
            if type(self.source_context) is not NoMovementEmbarkContext:
                raise GameLifecycleError("EmbarkSelection requires typed source context.")
            if (
                self.movement_phase_action is not TransportMovementStatus.NOT_MOVED
                or self.source_context.unit_instance_id != self.unit_instance_id
                or self.source_context.battle_round != self.battle_round
            ):
                raise GameLifecycleError("EmbarkSelection no-movement source context drift.")
        elif self.movement_phase_action not in {
            TransportMovementStatus.NORMAL_MOVE,
            TransportMovementStatus.ADVANCE,
            TransportMovementStatus.FALL_BACK,
        }:
            raise GameLifecycleError(
                "EmbarkSelection requires a Normal, Advance, or Fall Back action."
            )
        object.__setattr__(
            self,
            "restriction_overrides",
            _validate_transport_override_tuple(
                "EmbarkSelection restriction_overrides",
                self.restriction_overrides,
            ),
        )

    def has_override(self, override_kind: TransportRestrictionOverrideKind) -> bool:
        kind = transport_restriction_override_kind_from_token(override_kind)
        return any(override.override_kind is kind for override in self.restriction_overrides)

    def to_payload(self) -> EmbarkSelectionPayload:
        payload: EmbarkSelectionPayload = {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "unit_instance_id": self.unit_instance_id,
            "transport_unit_instance_id": self.transport_unit_instance_id,
            "movement_phase_action": self.movement_phase_action.value,
            "restriction_overrides": [
                override.to_payload() for override in self.restriction_overrides
            ],
        }
        if self.source_context is not None:
            payload["source_context"] = self.source_context.to_payload()
        return payload

    @classmethod
    def from_payload(cls, payload: EmbarkSelectionPayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            unit_instance_id=payload["unit_instance_id"],
            transport_unit_instance_id=payload["transport_unit_instance_id"],
            movement_phase_action=transport_movement_status_from_token(
                payload["movement_phase_action"]
            ),
            restriction_overrides=tuple(
                TransportRestrictionOverride.from_payload(override)
                for override in payload["restriction_overrides"]
            ),
            source_context=(
                NoMovementEmbarkContext.from_payload(payload["source_context"])
                if "source_context" in payload
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class EmbarkResolution:
    selection: EmbarkSelection
    violations: tuple[TransportOperationViolation, ...]
    updated_cargo_state: TransportCargoState | None
    transition_batch: BattlefieldTransitionBatch | None

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.transports import (
            TransportCargoState,
            _validate_transport_violation_tuple,  # pyright: ignore[reportPrivateUsage]
        )

        if type(self.selection) is not EmbarkSelection:
            raise GameLifecycleError("EmbarkResolution selection must be an EmbarkSelection.")
        object.__setattr__(
            self,
            "violations",
            _validate_transport_violation_tuple(
                "EmbarkResolution violations",
                self.violations,
            ),
        )
        if self.updated_cargo_state is not None and type(self.updated_cargo_state) is not (
            TransportCargoState
        ):
            raise GameLifecycleError(
                "EmbarkResolution updated_cargo_state must be a TransportCargoState."
            )
        if self.transition_batch is not None and type(self.transition_batch) is not (
            BattlefieldTransitionBatch
        ):
            raise GameLifecycleError(
                "EmbarkResolution transition_batch must be a BattlefieldTransitionBatch."
            )
        if self.violations and (
            self.updated_cargo_state is not None or self.transition_batch is not None
        ):
            raise GameLifecycleError("Invalid EmbarkResolution cannot include mutation records.")
        if not self.violations and (
            self.updated_cargo_state is None or self.transition_batch is None
        ):
            raise GameLifecycleError("Valid EmbarkResolution requires mutation records.")

    @property
    def is_valid(self) -> bool:
        return not self.violations

    def to_payload(self) -> EmbarkResolutionPayload:
        return {
            "selection": self.selection.to_payload(),
            "is_valid": self.is_valid,
            "violations": [violation.to_payload() for violation in self.violations],
            "updated_cargo_state": (
                None if self.updated_cargo_state is None else self.updated_cargo_state.to_payload()
            ),
            "transition_batch": None
            if self.transition_batch is None
            else self.transition_batch.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: EmbarkResolutionPayload) -> Self:
        from warhammer40k_core.engine.transports import (
            TransportCargoState,
            TransportOperationViolation,
        )

        transition_payload = payload["transition_batch"]
        resolution = cls(
            selection=EmbarkSelection.from_payload(payload["selection"]),
            violations=tuple(
                TransportOperationViolation.from_payload(violation)
                for violation in payload["violations"]
            ),
            updated_cargo_state=(
                None
                if payload["updated_cargo_state"] is None
                else TransportCargoState.from_payload(payload["updated_cargo_state"])
            ),
            transition_batch=(
                None
                if transition_payload is None
                else BattlefieldTransitionBatch.from_payload(transition_payload)
            ),
        )
        if resolution.is_valid != payload["is_valid"]:
            raise GameLifecycleError("EmbarkResolution payload validity drift.")
        return resolution
