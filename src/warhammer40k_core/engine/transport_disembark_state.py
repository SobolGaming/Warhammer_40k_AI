from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_transports_2026_09,
)

EMERGENCY_DISEMBARK_MOVE_SOURCE_ID = core_transports_2026_09.EMERGENCY_DISEMBARK_MOVE_SOURCE_ID
ASSAULT_DISEMBARK_MOVE_SOURCE_ID = core_transports_2026_09.ASSAULT_DISEMBARK_MOVE_SOURCE_ID
SHOCK_DISEMBARK_MOVE_SOURCE_ID = core_transports_2026_09.SHOCK_DISEMBARK_MOVE_SOURCE_ID
_RAPID_DISEMBARK_RULE_ID = "core_rules_rapid_disembark"
_TACTICAL_DISEMBARK_RULE_ID = "core_rules_tactical_disembark"
_COMBAT_DISEMBARK_RULE_ID = "core_rules_combat_disembark"
_DESTROYED_TRANSPORT_RULE_ID = "core_rules_destroyed_transport"
EMERGENCY_DISEMBARK_RULE_ID = "core_rules_emergency_disembark"


class TransportMovementStatus(StrEnum):
    NOT_MOVED = "not_moved"
    REMAIN_STATIONARY = "remain_stationary"
    NORMAL_MOVE = "normal_move"
    ADVANCE = "advance"
    FALL_BACK = "fall_back"
    INGRESS_MOVE = "ingress_move"


class TransportRestrictionOverrideKind(StrEnum):
    ALLOW_EMBARK_AFTER_DISEMBARK = "allow_embark_after_disembark"
    ALLOW_DISEMBARK_AFTER_ADVANCE_OR_FALL_BACK = "allow_disembark_after_advance_or_fall_back"
    ALLOW_ASSAULT_DISEMBARK_AFTER_NORMAL_MOVE = "allow_assault_disembark_after_normal_move"
    ALLOW_SHOCK_DISEMBARK_AFTER_ADVANCE = "allow_shock_disembark_after_advance"


class DisembarkModeKind(StrEnum):
    RAPID_DISEMBARK = "rapid_disembark"
    ASSAULT_DISEMBARK = "assault_disembark"
    SHOCK_DISEMBARK = "shock_disembark"
    TACTICAL_DISEMBARK = "tactical_disembark"
    COMBAT_DISEMBARK = "combat_disembark"
    DESTROYED_TRANSPORT = "destroyed_transport"
    EMERGENCY_DISEMBARK = "emergency_disembark"


class TransportRestrictionOverridePayload(TypedDict):
    override_kind: str
    source_rule_id: str


class DisembarkedUnitStatePayload(TypedDict):
    player_id: str
    battle_round: int
    turn_player_id: str
    unit_instance_id: str
    transport_unit_instance_id: str
    disembark_mode: str
    can_move_further: bool
    can_choose_remain_stationary: bool
    can_declare_charge: bool
    battle_shocked_until: str | None
    source_rule_id: str
    permission_source_rule_id: str | None
    start_engaged_enemy_unit_instance_ids: list[str]


@dataclass(frozen=True, slots=True)
class TransportRestrictionOverride:
    override_kind: TransportRestrictionOverrideKind
    source_rule_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "override_kind",
            transport_restriction_override_kind_from_token(self.override_kind),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier(
                "TransportRestrictionOverride source_rule_id", self.source_rule_id
            ),
        )

    def to_payload(self) -> TransportRestrictionOverridePayload:
        return {
            "override_kind": self.override_kind.value,
            "source_rule_id": self.source_rule_id,
        }

    @classmethod
    def from_payload(cls, payload: TransportRestrictionOverridePayload) -> Self:
        return cls(
            override_kind=transport_restriction_override_kind_from_token(payload["override_kind"]),
            source_rule_id=payload["source_rule_id"],
        )


@dataclass(frozen=True, slots=True)
class DisembarkedUnitState:
    player_id: str
    battle_round: int
    turn_player_id: str
    unit_instance_id: str
    transport_unit_instance_id: str
    disembark_mode: DisembarkModeKind
    can_move_further: bool
    can_choose_remain_stationary: bool
    can_declare_charge: bool
    battle_shocked_until: str | None
    source_rule_id: str
    permission_source_rule_id: str | None = None
    start_engaged_enemy_unit_instance_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("DisembarkedUnitState player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("DisembarkedUnitState battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "turn_player_id",
            _validate_identifier(
                "DisembarkedUnitState turn_player_id",
                self.turn_player_id,
            ),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("DisembarkedUnitState unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "transport_unit_instance_id",
            _validate_identifier(
                "DisembarkedUnitState transport_unit_instance_id",
                self.transport_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "disembark_mode",
            disembark_mode_kind_from_token(self.disembark_mode),
        )
        object.__setattr__(
            self,
            "can_move_further",
            _validate_bool("DisembarkedUnitState can_move_further", self.can_move_further),
        )
        object.__setattr__(
            self,
            "can_choose_remain_stationary",
            _validate_bool(
                "DisembarkedUnitState can_choose_remain_stationary",
                self.can_choose_remain_stationary,
            ),
        )
        object.__setattr__(
            self,
            "can_declare_charge",
            _validate_bool("DisembarkedUnitState can_declare_charge", self.can_declare_charge),
        )
        object.__setattr__(
            self,
            "battle_shocked_until",
            _validate_optional_identifier(
                "DisembarkedUnitState battle_shocked_until",
                self.battle_shocked_until,
            ),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("DisembarkedUnitState source_rule_id", self.source_rule_id),
        )
        object.__setattr__(
            self,
            "permission_source_rule_id",
            _validate_optional_identifier(
                "DisembarkedUnitState permission_source_rule_id",
                self.permission_source_rule_id,
            ),
        )
        object.__setattr__(
            self,
            "start_engaged_enemy_unit_instance_ids",
            _validate_identifier_tuple_allow_empty(
                "DisembarkedUnitState start_engaged_enemy_unit_instance_ids",
                self.start_engaged_enemy_unit_instance_ids,
            ),
        )
        if self.disembark_mode is DisembarkModeKind.ASSAULT_DISEMBARK:
            if self.permission_source_rule_id is None:
                raise GameLifecycleError(
                    "Assault Disembark state requires a permitting source rule ID."
                )
            if (
                self.can_move_further
                or self.can_choose_remain_stationary
                or not self.can_declare_charge
                or self.battle_shocked_until is not None
                or self.source_rule_id != ASSAULT_DISEMBARK_MOVE_SOURCE_ID
            ):
                raise GameLifecycleError("Assault Disembark state flags drifted.")
            if self.start_engaged_enemy_unit_instance_ids:
                raise GameLifecycleError(
                    "Assault Disembark state cannot carry Shock engagement state."
                )
        elif self.disembark_mode is DisembarkModeKind.SHOCK_DISEMBARK:
            if self.permission_source_rule_id is None:
                raise GameLifecycleError(
                    "Shock Disembark state requires a permitting source rule ID."
                )
            if (
                self.can_move_further
                or self.can_choose_remain_stationary
                or self.can_declare_charge
                or self.battle_shocked_until is not None
                or self.source_rule_id != SHOCK_DISEMBARK_MOVE_SOURCE_ID
            ):
                raise GameLifecycleError("Shock Disembark state flags drifted.")
        elif self.permission_source_rule_id is not None:
            raise GameLifecycleError(
                "Only Assault Disembark state or Shock Disembark state may carry a "
                "permitting source rule ID."
            )
        elif self.start_engaged_enemy_unit_instance_ids:
            raise GameLifecycleError("Only Shock Disembark state may carry start engagement state.")

    @classmethod
    def for_mode(
        cls,
        *,
        player_id: str,
        battle_round: int,
        unit_instance_id: str,
        transport_unit_instance_id: str,
        disembark_mode: DisembarkModeKind,
        transport_movement_status: TransportMovementStatus,
        restriction_overrides: tuple[TransportRestrictionOverride, ...] = (),
        start_engaged_enemy_unit_instance_ids: tuple[str, ...] = (),
    ) -> Self:
        mode = disembark_mode_kind_from_token(disembark_mode)
        status = transport_movement_status_from_token(transport_movement_status)
        validate_disembark_mode_status(
            disembark_mode=mode,
            transport_movement_status=status,
        )
        overrides = validate_transport_override_tuple(
            "DisembarkedUnitState restriction_overrides",
            restriction_overrides,
        )
        assault_permission = next(
            (
                override
                for override in overrides
                if override.override_kind
                is TransportRestrictionOverrideKind.ALLOW_ASSAULT_DISEMBARK_AFTER_NORMAL_MOVE
            ),
            None,
        )
        shock_permission = next(
            (
                override
                for override in overrides
                if override.override_kind
                is TransportRestrictionOverrideKind.ALLOW_SHOCK_DISEMBARK_AFTER_ADVANCE
            ),
            None,
        )
        if mode is DisembarkModeKind.ASSAULT_DISEMBARK:
            if assault_permission is None:
                raise GameLifecycleError(
                    "Assault Disembark requires a source-backed permitting rule."
                )
            return cls(
                player_id=player_id,
                battle_round=battle_round,
                turn_player_id=player_id,
                unit_instance_id=unit_instance_id,
                transport_unit_instance_id=transport_unit_instance_id,
                disembark_mode=mode,
                can_move_further=False,
                can_choose_remain_stationary=False,
                can_declare_charge=True,
                battle_shocked_until=None,
                source_rule_id=ASSAULT_DISEMBARK_MOVE_SOURCE_ID,
                permission_source_rule_id=assault_permission.source_rule_id,
            )
        if mode is DisembarkModeKind.SHOCK_DISEMBARK:
            if shock_permission is None:
                raise GameLifecycleError(
                    "Shock Disembark requires a source-backed permitting rule."
                )
            return cls(
                player_id=player_id,
                battle_round=battle_round,
                turn_player_id=player_id,
                unit_instance_id=unit_instance_id,
                transport_unit_instance_id=transport_unit_instance_id,
                disembark_mode=mode,
                can_move_further=False,
                can_choose_remain_stationary=False,
                can_declare_charge=False,
                battle_shocked_until=None,
                source_rule_id=SHOCK_DISEMBARK_MOVE_SOURCE_ID,
                permission_source_rule_id=shock_permission.source_rule_id,
                start_engaged_enemy_unit_instance_ids=(start_engaged_enemy_unit_instance_ids),
            )
        if mode is DisembarkModeKind.RAPID_DISEMBARK:
            return cls(
                player_id=player_id,
                battle_round=battle_round,
                turn_player_id=player_id,
                unit_instance_id=unit_instance_id,
                transport_unit_instance_id=transport_unit_instance_id,
                disembark_mode=mode,
                can_move_further=False,
                can_choose_remain_stationary=False,
                can_declare_charge=False,
                battle_shocked_until=None,
                source_rule_id=_RAPID_DISEMBARK_RULE_ID,
            )
        if mode is DisembarkModeKind.COMBAT_DISEMBARK:
            return cls(
                player_id=player_id,
                battle_round=battle_round,
                turn_player_id=player_id,
                unit_instance_id=unit_instance_id,
                transport_unit_instance_id=transport_unit_instance_id,
                disembark_mode=mode,
                can_move_further=False,
                can_choose_remain_stationary=False,
                can_declare_charge=False,
                battle_shocked_until="end_of_turn",
                source_rule_id=_COMBAT_DISEMBARK_RULE_ID,
            )
        if mode is not DisembarkModeKind.TACTICAL_DISEMBARK:
            raise GameLifecycleError(
                "Normal Disembark requires Tactical, Rapid, Assault, Shock, or Combat mode."
            )
        return cls(
            player_id=player_id,
            battle_round=battle_round,
            turn_player_id=player_id,
            unit_instance_id=unit_instance_id,
            transport_unit_instance_id=transport_unit_instance_id,
            disembark_mode=mode,
            can_move_further=True,
            can_choose_remain_stationary=False,
            can_declare_charge=True,
            battle_shocked_until=None,
            source_rule_id=_TACTICAL_DISEMBARK_RULE_ID,
        )

    @classmethod
    def for_destroyed_transport(
        cls,
        *,
        player_id: str,
        battle_round: int,
        turn_player_id: str,
        unit_instance_id: str,
        transport_unit_instance_id: str,
        disembark_mode: DisembarkModeKind,
    ) -> Self:
        mode = disembark_mode_kind_from_token(disembark_mode)
        if mode not in {
            DisembarkModeKind.DESTROYED_TRANSPORT,
            DisembarkModeKind.EMERGENCY_DISEMBARK,
        }:
            raise GameLifecycleError(
                "Destroyed Transport Disembark requires destroyed or emergency mode."
            )
        return cls(
            player_id=player_id,
            battle_round=battle_round,
            turn_player_id=turn_player_id,
            unit_instance_id=unit_instance_id,
            transport_unit_instance_id=transport_unit_instance_id,
            disembark_mode=mode,
            can_move_further=False,
            can_choose_remain_stationary=False,
            can_declare_charge=False,
            battle_shocked_until="end_of_turn",
            source_rule_id=(
                EMERGENCY_DISEMBARK_RULE_ID
                if mode is DisembarkModeKind.EMERGENCY_DISEMBARK
                else _DESTROYED_TRANSPORT_RULE_ID
            ),
        )

    def to_payload(self) -> DisembarkedUnitStatePayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "turn_player_id": self.turn_player_id,
            "unit_instance_id": self.unit_instance_id,
            "transport_unit_instance_id": self.transport_unit_instance_id,
            "disembark_mode": self.disembark_mode.value,
            "can_move_further": self.can_move_further,
            "can_choose_remain_stationary": self.can_choose_remain_stationary,
            "can_declare_charge": self.can_declare_charge,
            "battle_shocked_until": self.battle_shocked_until,
            "source_rule_id": self.source_rule_id,
            "permission_source_rule_id": self.permission_source_rule_id,
            "start_engaged_enemy_unit_instance_ids": list(
                self.start_engaged_enemy_unit_instance_ids
            ),
        }

    @classmethod
    def from_payload(cls, payload: DisembarkedUnitStatePayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            turn_player_id=payload["turn_player_id"],
            unit_instance_id=payload["unit_instance_id"],
            transport_unit_instance_id=payload["transport_unit_instance_id"],
            disembark_mode=disembark_mode_kind_from_token(payload["disembark_mode"]),
            can_move_further=payload["can_move_further"],
            can_choose_remain_stationary=payload["can_choose_remain_stationary"],
            can_declare_charge=payload["can_declare_charge"],
            battle_shocked_until=payload["battle_shocked_until"],
            source_rule_id=payload["source_rule_id"],
            permission_source_rule_id=payload["permission_source_rule_id"],
            start_engaged_enemy_unit_instance_ids=tuple(
                payload["start_engaged_enemy_unit_instance_ids"]
            ),
        )


def disembarked_unit_state_from_event_payload(payload: object) -> DisembarkedUnitState:
    event_payload = validate_json_value(payload)
    if not isinstance(event_payload, dict):
        raise GameLifecycleError("unit_disembarked event payload must be an object.")
    state_payload = event_payload.get("disembarked_unit_state")
    if not isinstance(state_payload, dict):
        raise GameLifecycleError("unit_disembarked event requires disembarked unit state.")
    try:
        return DisembarkedUnitState.from_payload(cast(DisembarkedUnitStatePayload, state_payload))
    except KeyError as exc:
        raise GameLifecycleError(
            "unit_disembarked event disembarked unit state is malformed."
        ) from exc


def transport_movement_status_from_token(token: object) -> TransportMovementStatus:
    if type(token) is TransportMovementStatus:
        return token
    if type(token) is not str:
        raise GameLifecycleError("TransportMovementStatus token must be a string.")
    try:
        return TransportMovementStatus(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported TransportMovementStatus token: {token}.") from exc


def transport_restriction_override_kind_from_token(
    token: object,
) -> TransportRestrictionOverrideKind:
    if type(token) is TransportRestrictionOverrideKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("TransportRestrictionOverrideKind token must be a string.")
    try:
        return TransportRestrictionOverrideKind(token)
    except ValueError as exc:
        raise GameLifecycleError(
            f"Unsupported TransportRestrictionOverrideKind token: {token}."
        ) from exc


def disembark_mode_kind_from_token(token: object) -> DisembarkModeKind:
    if type(token) is DisembarkModeKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("DisembarkModeKind token must be a string.")
    try:
        return DisembarkModeKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported DisembarkModeKind token: {token}.") from exc


def validate_disembark_mode_status(
    *,
    disembark_mode: DisembarkModeKind,
    transport_movement_status: TransportMovementStatus,
) -> None:
    mode = disembark_mode_kind_from_token(disembark_mode)
    status = transport_movement_status_from_token(transport_movement_status)
    if mode is DisembarkModeKind.TACTICAL_DISEMBARK:
        if status not in {
            TransportMovementStatus.NOT_MOVED,
            TransportMovementStatus.REMAIN_STATIONARY,
        }:
            raise GameLifecycleError(
                "Tactical Disembark requires an unmoved or stationary Transport."
            )
        return
    if mode is DisembarkModeKind.RAPID_DISEMBARK:
        if status not in {
            TransportMovementStatus.NORMAL_MOVE,
            TransportMovementStatus.INGRESS_MOVE,
        }:
            raise GameLifecycleError(
                "Rapid Disembark requires Normal or Ingress Transport movement."
            )
        return
    if mode is DisembarkModeKind.ASSAULT_DISEMBARK:
        if status is not TransportMovementStatus.NORMAL_MOVE:
            raise GameLifecycleError("Assault Disembark requires Normal Transport movement.")
        return
    if mode is DisembarkModeKind.SHOCK_DISEMBARK:
        if status is not TransportMovementStatus.ADVANCE:
            raise GameLifecycleError("Shock Disembark requires an Advanced Transport.")
        return
    if mode is DisembarkModeKind.COMBAT_DISEMBARK:
        if status not in {
            TransportMovementStatus.NOT_MOVED,
            TransportMovementStatus.REMAIN_STATIONARY,
        }:
            raise GameLifecycleError(
                "Combat Disembark requires an unmoved or stationary Transport."
            )
        return
    if mode in {
        DisembarkModeKind.DESTROYED_TRANSPORT,
        DisembarkModeKind.EMERGENCY_DISEMBARK,
    }:
        if status is not TransportMovementStatus.NOT_MOVED:
            raise GameLifecycleError("Destroyed Transport Disembark requires destroyed timing.")
        return
    raise GameLifecycleError("Unsupported DisembarkModeKind.")


def validate_transport_override_tuple(
    field_name: str,
    values: object,
) -> tuple[TransportRestrictionOverride, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    overrides: list[TransportRestrictionOverride] = []
    seen: set[TransportRestrictionOverrideKind] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not TransportRestrictionOverride:
            raise GameLifecycleError(f"{field_name} must contain TransportRestrictionOverride.")
        if value.override_kind in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicate override kinds.")
        seen.add(value.override_kind)
        overrides.append(value)
    return tuple(sorted(overrides, key=lambda override: override.override_kind.value))


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be at least 1.")
    return value


def _validate_bool(field_name: str, value: object) -> bool:
    if type(value) is not bool:
        raise GameLifecycleError(f"{field_name} must be a bool.")
    return value


def _validate_identifier_tuple_allow_empty(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    validated = tuple(
        _validate_identifier(field_name, value) for value in cast(tuple[object, ...], values)
    )
    if len(validated) != len(set(validated)):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return tuple(sorted(validated))


__all__ = (
    "ASSAULT_DISEMBARK_MOVE_SOURCE_ID",
    "EMERGENCY_DISEMBARK_MOVE_SOURCE_ID",
    "EMERGENCY_DISEMBARK_RULE_ID",
    "SHOCK_DISEMBARK_MOVE_SOURCE_ID",
    "DisembarkModeKind",
    "DisembarkedUnitState",
    "DisembarkedUnitStatePayload",
    "TransportMovementStatus",
    "TransportRestrictionOverride",
    "TransportRestrictionOverrideKind",
    "TransportRestrictionOverridePayload",
    "disembark_mode_kind_from_token",
    "disembarked_unit_state_from_event_payload",
    "transport_movement_status_from_token",
    "transport_restriction_override_kind_from_token",
    "validate_disembark_mode_status",
    "validate_transport_override_tuple",
)
