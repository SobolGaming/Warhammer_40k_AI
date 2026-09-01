from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.descriptor_hash import canonical_payload_sha256
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
    BattlefieldRuntimeState,
    PlacementError,
    battlefield_removal_kind_from_token,
)
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.rules_units import rules_unit_view_from_armies

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


class PrimaryBattlefieldDepartureStatePayload(TypedDict):
    departure_id: str
    game_id: str
    owner_player_id: str
    rules_unit_instance_id: str
    component_unit_instance_ids: list[str]
    affected_component_unit_instance_ids: list[str]
    departed_component_unit_instance_ids: list[str]
    removed_model_instance_ids: list[str]
    battle_round: int
    active_player_id: str
    phase: str
    removal_kind: str
    occurrence_id: str
    source_id: str


@dataclass(frozen=True, slots=True)
class PrimaryBattlefieldDepartureState:
    """One authoritative occurrence in which unit models leave the battlefield.

    The rules-unit identity records the group at the mutation boundary while the
    affected-component IDs identify the physical owners of the exact models removed
    by this occurrence.  Departed-component IDs are the subset whose current models
    have all left the battlefield.  Destruction, Embark and reserve transitions all
    use this one evidence family; pre-battle removals are outside its battle-only
    scope.
    """

    departure_id: str
    game_id: str
    owner_player_id: str
    rules_unit_instance_id: str
    component_unit_instance_ids: tuple[str, ...]
    affected_component_unit_instance_ids: tuple[str, ...]
    departed_component_unit_instance_ids: tuple[str, ...]
    removed_model_instance_ids: tuple[str, ...]
    battle_round: int
    active_player_id: str
    phase: str
    removal_kind: BattlefieldRemovalKind
    occurrence_id: str
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "departure_id",
            _validate_identifier("Primary departure departure_id", self.departure_id),
        )
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("Primary departure game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "owner_player_id",
            _validate_identifier("Primary departure owner_player_id", self.owner_player_id),
        )
        object.__setattr__(
            self,
            "rules_unit_instance_id",
            _validate_identifier(
                "Primary departure rules_unit_instance_id",
                self.rules_unit_instance_id,
            ),
        )
        component_ids = _validate_identifier_tuple(
            "Primary departure component_unit_instance_ids",
            self.component_unit_instance_ids,
        )
        affected_component_ids = _validate_identifier_tuple(
            "Primary departure affected_component_unit_instance_ids",
            self.affected_component_unit_instance_ids,
        )
        departed_component_ids = _validate_identifier_tuple(
            "Primary departure departed_component_unit_instance_ids",
            self.departed_component_unit_instance_ids,
            require_non_empty=False,
        )
        if not set(affected_component_ids) <= set(component_ids):
            raise GameLifecycleError(
                "Primary departure affected components must belong to the rules unit."
            )
        if not set(departed_component_ids) <= set(affected_component_ids):
            raise GameLifecycleError(
                "Primary departure departed components must be affected by the occurrence."
            )
        object.__setattr__(self, "component_unit_instance_ids", component_ids)
        object.__setattr__(
            self,
            "affected_component_unit_instance_ids",
            affected_component_ids,
        )
        object.__setattr__(
            self,
            "departed_component_unit_instance_ids",
            departed_component_ids,
        )
        object.__setattr__(
            self,
            "removed_model_instance_ids",
            _validate_identifier_tuple(
                "Primary departure removed_model_instance_ids",
                self.removed_model_instance_ids,
            ),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("Primary departure battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier(
                "Primary departure active_player_id",
                self.active_player_id,
            ),
        )
        object.__setattr__(
            self,
            "phase",
            _validate_identifier("Primary departure phase", self.phase),
        )
        object.__setattr__(
            self,
            "removal_kind",
            _primary_removal_kind(self.removal_kind),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("Primary departure source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "occurrence_id",
            _validate_identifier("Primary departure occurrence_id", self.occurrence_id),
        )

    def to_payload(self) -> PrimaryBattlefieldDepartureStatePayload:
        return {
            "departure_id": self.departure_id,
            "game_id": self.game_id,
            "owner_player_id": self.owner_player_id,
            "rules_unit_instance_id": self.rules_unit_instance_id,
            "component_unit_instance_ids": list(self.component_unit_instance_ids),
            "affected_component_unit_instance_ids": list(self.affected_component_unit_instance_ids),
            "departed_component_unit_instance_ids": list(self.departed_component_unit_instance_ids),
            "removed_model_instance_ids": list(self.removed_model_instance_ids),
            "battle_round": self.battle_round,
            "active_player_id": self.active_player_id,
            "phase": self.phase,
            "removal_kind": self.removal_kind.value,
            "occurrence_id": self.occurrence_id,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        raw = _required_payload_mapping(
            payload,
            required_keys=(
                "departure_id",
                "game_id",
                "owner_player_id",
                "rules_unit_instance_id",
                "component_unit_instance_ids",
                "affected_component_unit_instance_ids",
                "departed_component_unit_instance_ids",
                "removed_model_instance_ids",
                "battle_round",
                "active_player_id",
                "phase",
                "removal_kind",
                "occurrence_id",
                "source_id",
            ),
        )
        return cls(
            departure_id=cast(str, raw["departure_id"]),
            game_id=cast(str, raw["game_id"]),
            owner_player_id=cast(str, raw["owner_player_id"]),
            rules_unit_instance_id=cast(str, raw["rules_unit_instance_id"]),
            component_unit_instance_ids=_payload_identifier_tuple(
                raw["component_unit_instance_ids"],
                field_name="Primary departure component_unit_instance_ids",
            ),
            affected_component_unit_instance_ids=_payload_identifier_tuple(
                raw["affected_component_unit_instance_ids"],
                field_name="Primary departure affected_component_unit_instance_ids",
            ),
            departed_component_unit_instance_ids=_payload_identifier_tuple(
                raw["departed_component_unit_instance_ids"],
                field_name="Primary departure departed_component_unit_instance_ids",
            ),
            removed_model_instance_ids=_payload_identifier_tuple(
                raw["removed_model_instance_ids"],
                field_name="Primary departure removed_model_instance_ids",
            ),
            battle_round=cast(int, raw["battle_round"]),
            active_player_id=cast(str, raw["active_player_id"]),
            phase=cast(str, raw["phase"]),
            removal_kind=_primary_removal_kind(raw["removal_kind"]),
            occurrence_id=cast(str, raw["occurrence_id"]),
            source_id=cast(str, raw["source_id"]),
        )


def primary_battlefield_departure_id(
    *,
    game_id: str,
    rules_unit_instance_id: str,
    affected_component_unit_instance_ids: tuple[str, ...],
    departed_component_unit_instance_ids: tuple[str, ...],
    removed_model_instance_ids: tuple[str, ...],
    battle_round: int,
    active_player_id: str,
    phase: str,
    removal_kind: BattlefieldRemovalKind,
    occurrence_id: str,
    source_id: str,
) -> str:
    requested_game_id = _validate_identifier("game_id", game_id)
    requested_rules_unit_id = _validate_identifier(
        "rules_unit_instance_id",
        rules_unit_instance_id,
    )
    requested_affected_components = _validate_identifier_tuple(
        "affected_component_unit_instance_ids",
        affected_component_unit_instance_ids,
    )
    requested_departed_components = _validate_identifier_tuple(
        "departed_component_unit_instance_ids",
        departed_component_unit_instance_ids,
        require_non_empty=False,
    )
    if not set(requested_departed_components) <= set(requested_affected_components):
        raise GameLifecycleError(
            "Departed components must be affected by the departure occurrence."
        )
    requested_removed_models = _validate_identifier_tuple(
        "removed_model_instance_ids",
        removed_model_instance_ids,
    )
    requested_battle_round = _validate_positive_int("battle_round", battle_round)
    requested_active_player_id = _validate_identifier(
        "active_player_id",
        active_player_id,
    )
    requested_phase = _validate_identifier("phase", phase)
    kind = _primary_removal_kind(removal_kind)
    requested_occurrence_id = _validate_identifier("occurrence_id", occurrence_id)
    requested_source_id = _validate_identifier("source_id", source_id)
    occurrence_hash = canonical_payload_sha256(
        {
            "game_id": requested_game_id,
            "rules_unit_instance_id": requested_rules_unit_id,
            "affected_component_unit_instance_ids": list(requested_affected_components),
            "departed_component_unit_instance_ids": list(requested_departed_components),
            "removed_model_instance_ids": list(requested_removed_models),
            "battle_round": requested_battle_round,
            "active_player_id": requested_active_player_id,
            "phase": requested_phase,
            "removal_kind": kind.value,
            "occurrence_id": requested_occurrence_id,
            "source_id": requested_source_id,
        }
    )
    return f"primary-battlefield-departure:{occurrence_hash}"


def record_primary_battlefield_departure(
    *,
    state: GameState,
    rules_unit_instance_id: str,
    affected_component_unit_instance_ids: tuple[str, ...],
    departed_component_unit_instance_ids: tuple[str, ...],
    removed_model_instance_ids: tuple[str, ...],
    removal_kind: BattlefieldRemovalKind,
    occurrence_id: str,
    source_id: str,
) -> PrimaryBattlefieldDepartureState | None:
    """Record battle-only departure evidence after an accepted engine mutation."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary battlefield departure tracking requires GameState.")
    departure = prepare_primary_battlefield_departure(
        state=state,
        battlefield_state=state.battlefield_state,
        rules_unit_instance_id=rules_unit_instance_id,
        affected_component_unit_instance_ids=affected_component_unit_instance_ids,
        departed_component_unit_instance_ids=departed_component_unit_instance_ids,
        removed_model_instance_ids=removed_model_instance_ids,
        removal_kind=removal_kind,
        occurrence_id=occurrence_id,
        source_id=source_id,
    )
    record_prepared_primary_battlefield_departure(state=state, departure=departure)
    return departure


def prepare_primary_battlefield_departure(
    *,
    state: GameState,
    battlefield_state: BattlefieldRuntimeState | None,
    rules_unit_instance_id: str,
    affected_component_unit_instance_ids: tuple[str, ...],
    departed_component_unit_instance_ids: tuple[str, ...],
    removed_model_instance_ids: tuple[str, ...],
    removal_kind: BattlefieldRemovalKind,
    occurrence_id: str,
    source_id: str,
) -> PrimaryBattlefieldDepartureState | None:
    """Build and validate departure evidence against a prospective battlefield."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary battlefield departure tracking requires GameState.")
    if state.mission_setup is None:
        return None
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("Primary battlefield departures can only occur during battle.")
    if state.active_player_id is None or state.current_battle_phase is None:
        raise GameLifecycleError(
            "Primary battlefield departure tracking requires active-player phase state."
        )
    requested_rules_unit_id = _validate_identifier(
        "rules_unit_instance_id",
        rules_unit_instance_id,
    )
    (
        canonical_rules_unit_id,
        owner_player_id,
        component_unit_instance_ids,
    ) = _authoritative_rules_unit_identity(
        state=state,
        rules_unit_instance_id=requested_rules_unit_id,
    )
    affected_component_ids = _validate_identifier_tuple(
        "affected_component_unit_instance_ids",
        affected_component_unit_instance_ids,
    )
    if not set(affected_component_ids) <= set(component_unit_instance_ids):
        raise GameLifecycleError(
            "Primary battlefield departure affected components do not belong to the rules unit."
        )
    departed_component_ids = _validate_identifier_tuple(
        "departed_component_unit_instance_ids",
        departed_component_unit_instance_ids,
        require_non_empty=False,
    )
    if not set(departed_component_ids) <= set(affected_component_ids):
        raise GameLifecycleError(
            "Primary battlefield departure departed components must be affected."
        )
    removed_model_ids = _validate_identifier_tuple(
        "removed_model_instance_ids",
        removed_model_instance_ids,
    )
    physical_units_by_id = {
        unit.unit_instance_id: unit for army in state.army_definitions for unit in army.units
    }
    known_models_by_component = {
        component_id: {
            model.model_instance_id for model in physical_units_by_id[component_id].own_models
        }
        for component_id in component_unit_instance_ids
    }
    known_affected_model_ids = {
        model_id
        for component_id in affected_component_ids
        for model_id in known_models_by_component[component_id]
    }
    if not set(removed_model_ids) <= known_affected_model_ids:
        raise GameLifecycleError(
            "Primary battlefield departure removed models do not belong to an affected component."
        )
    battlefield = battlefield_state
    if type(battlefield) is not BattlefieldRuntimeState:
        raise GameLifecycleError("Primary battlefield departure requires battlefield_state.")
    if set(removed_model_ids).intersection(battlefield.placed_model_ids()):
        raise GameLifecycleError(
            "Primary battlefield departure removed models must have left the battlefield."
        )
    placed_model_ids = set(battlefield.placed_model_ids())
    if any(
        known_models_by_component[component_id].intersection(placed_model_ids)
        for component_id in departed_component_ids
    ):
        raise GameLifecycleError(
            "A departed component must have no current model on the battlefield."
        )
    if any(
        not known_models_by_component[component_id].intersection(removed_model_ids)
        for component_id in affected_component_ids
    ):
        raise GameLifecycleError(
            "Every affected component must contribute a removed model to the occurrence."
        )
    kind = _primary_removal_kind(removal_kind)
    requested_occurrence_id = _validate_identifier("occurrence_id", occurrence_id)
    requested_source_id = _validate_identifier("source_id", source_id)
    departure = PrimaryBattlefieldDepartureState(
        departure_id=primary_battlefield_departure_id(
            game_id=state.game_id,
            rules_unit_instance_id=canonical_rules_unit_id,
            affected_component_unit_instance_ids=affected_component_ids,
            departed_component_unit_instance_ids=departed_component_ids,
            removed_model_instance_ids=removed_model_ids,
            battle_round=state.battle_round,
            active_player_id=state.active_player_id,
            phase=state.current_battle_phase.value,
            removal_kind=kind,
            occurrence_id=requested_occurrence_id,
            source_id=requested_source_id,
        ),
        game_id=state.game_id,
        owner_player_id=owner_player_id,
        rules_unit_instance_id=canonical_rules_unit_id,
        component_unit_instance_ids=component_unit_instance_ids,
        affected_component_unit_instance_ids=affected_component_ids,
        departed_component_unit_instance_ids=departed_component_ids,
        removed_model_instance_ids=removed_model_ids,
        battle_round=state.battle_round,
        active_player_id=state.active_player_id,
        phase=state.current_battle_phase.value,
        removal_kind=kind,
        occurrence_id=requested_occurrence_id,
        source_id=requested_source_id,
    )
    if any(
        existing.departure_id == departure.departure_id
        for existing in state.primary_battlefield_departure_states
    ):
        raise GameLifecycleError("Primary battlefield departure occurrence already exists.")
    return departure


def record_prepared_primary_battlefield_departure(
    *,
    state: GameState,
    departure: PrimaryBattlefieldDepartureState | None,
) -> None:
    """Commit evidence that was validated before its authoritative mutation."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary battlefield departure tracking requires GameState.")
    if departure is None:
        if state.mission_setup is not None:
            raise GameLifecycleError("Mission play requires prepared departure evidence.")
        return
    if type(departure) is not PrimaryBattlefieldDepartureState:
        raise GameLifecycleError("Prepared primary battlefield departure must be typed evidence.")
    if departure.game_id != state.game_id:
        raise GameLifecycleError("Prepared primary battlefield departure game_id drift.")
    if any(
        existing.departure_id == departure.departure_id
        for existing in state.primary_battlefield_departure_states
    ):
        raise GameLifecycleError("Primary battlefield departure occurrence already exists.")
    state.primary_battlefield_departure_states.append(departure)
    state.primary_battlefield_departure_states.sort(key=lambda value: value.departure_id)


def primary_battlefield_departure_states_from_payload(
    payload: object,
) -> list[PrimaryBattlefieldDepartureState]:
    if type(payload) is not list:
        raise GameLifecycleError("Primary battlefield departure payloads must be a list.")
    return [
        PrimaryBattlefieldDepartureState.from_payload(value)
        for value in cast(list[object], payload)
    ]


def _authoritative_rules_unit_identity(
    *,
    state: GameState,
    rules_unit_instance_id: str,
) -> tuple[str, str, tuple[str, ...]]:
    historical_matches = tuple(
        record
        for record in state.starting_attached_unit_records
        if record.attached_unit_instance_id == rules_unit_instance_id
    )
    if len(historical_matches) > 1:
        raise GameLifecycleError(
            "Primary battlefield departure historical rules-unit identity is ambiguous."
        )
    if historical_matches:
        historical = historical_matches[0]
        return (
            historical.attached_unit_instance_id,
            historical.player_id,
            tuple(sorted(historical.component_unit_instance_ids)),
        )
    rules_unit = rules_unit_view_from_armies(
        armies=tuple(state.army_definitions),
        unit_instance_id=rules_unit_instance_id,
    )
    return (
        rules_unit.unit_instance_id,
        rules_unit.owner_player_id,
        tuple(sorted(rules_unit.component_unit_instance_ids)),
    )


def validate_primary_battlefield_departure_states(
    values: object,
    *,
    game_id: str,
    player_ids: tuple[str, ...],
    owner_by_unit_id: dict[str, str],
    model_ids_by_unit_id: dict[str, tuple[str, ...]],
    known_rules_unit_components_by_id: dict[str, tuple[str, ...]],
) -> list[PrimaryBattlefieldDepartureState]:
    if not isinstance(values, list):
        raise GameLifecycleError("Primary battlefield departure states must be a list.")
    requested_game_id = _validate_identifier("game_id", game_id)
    known_players = set(player_ids)
    seen_ids: set[str] = set()
    validated: list[PrimaryBattlefieldDepartureState] = []
    for value in cast(list[object], values):
        if type(value) is not PrimaryBattlefieldDepartureState:
            raise GameLifecycleError(
                "Primary battlefield departure states must contain typed values."
            )
        if value.game_id != requested_game_id:
            raise GameLifecycleError("Primary battlefield departure game_id drift.")
        if (
            value.owner_player_id not in known_players
            or value.active_player_id not in known_players
        ):
            raise GameLifecycleError("Primary battlefield departure references an unknown player.")
        expected_components = known_rules_unit_components_by_id.get(value.rules_unit_instance_id)
        if expected_components is None:
            raise GameLifecycleError(
                "Primary battlefield departure references an unknown rules unit."
            )
        if value.component_unit_instance_ids != tuple(sorted(expected_components)):
            raise GameLifecycleError("Primary battlefield departure component identity drift.")
        if any(
            owner_by_unit_id.get(component_id) != value.owner_player_id
            for component_id in value.component_unit_instance_ids
        ):
            raise GameLifecycleError("Primary battlefield departure owner drift.")
        known_affected_model_ids = {
            model_id
            for component_id in value.affected_component_unit_instance_ids
            for model_id in model_ids_by_unit_id.get(component_id, ())
        }
        if not set(value.removed_model_instance_ids) <= known_affected_model_ids:
            raise GameLifecycleError(
                "Primary battlefield departure references a model outside its affected components."
            )
        if any(
            not set(model_ids_by_unit_id.get(component_id, ())).intersection(
                value.removed_model_instance_ids
            )
            for component_id in value.affected_component_unit_instance_ids
        ):
            raise GameLifecycleError(
                "Every affected component must contribute a removed model to the occurrence."
            )
        expected_id = primary_battlefield_departure_id(
            game_id=value.game_id,
            rules_unit_instance_id=value.rules_unit_instance_id,
            affected_component_unit_instance_ids=(value.affected_component_unit_instance_ids),
            departed_component_unit_instance_ids=(value.departed_component_unit_instance_ids),
            removed_model_instance_ids=value.removed_model_instance_ids,
            battle_round=value.battle_round,
            active_player_id=value.active_player_id,
            phase=value.phase,
            removal_kind=value.removal_kind,
            occurrence_id=value.occurrence_id,
            source_id=value.source_id,
        )
        if value.departure_id != expected_id:
            raise GameLifecycleError("Primary battlefield departure_id drift.")
        if value.departure_id in seen_ids:
            raise GameLifecycleError("Primary battlefield departure states must be unique.")
        seen_ids.add(value.departure_id)
        validated.append(value)
    return sorted(validated, key=lambda value: value.departure_id)


def _required_payload_mapping(
    payload: object,
    *,
    required_keys: tuple[str, ...],
) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Primary battlefield departure payload must be an object.")
    raw = cast(dict[str, object], payload)
    missing = tuple(key for key in required_keys if key not in raw)
    if missing:
        raise GameLifecycleError(
            f"Primary battlefield departure payload is missing required field: {missing[0]}."
        )
    unexpected = tuple(sorted(set(raw).difference(required_keys)))
    if unexpected:
        raise GameLifecycleError(
            f"Primary battlefield departure payload contains unexpected field: {unexpected[0]}."
        )
    return raw


def _payload_identifier_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    if type(value) is not list:
        raise GameLifecycleError(f"{field_name} must be a list.")
    return tuple(cast(list[str], value))


def _validate_identifier_tuple(
    field_name: str,
    value: object,
    *,
    require_non_empty: bool = True,
) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers = tuple(
        _validate_identifier(f"{field_name} value", item)
        for item in cast(tuple[object, ...], value)
    )
    if require_non_empty and not identifiers:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    if len(set(identifiers)) != len(identifiers):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return tuple(sorted(identifiers))


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int or value < 1:
        raise GameLifecycleError(f"{field_name} must be a positive integer.")
    return value


def _primary_removal_kind(value: object) -> BattlefieldRemovalKind:
    try:
        return battlefield_removal_kind_from_token(value)
    except PlacementError as exc:
        raise GameLifecycleError(
            "Primary battlefield departure removal kind is unsupported."
        ) from exc


_validate_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "PrimaryBattlefieldDepartureState",
    "PrimaryBattlefieldDepartureStatePayload",
    "primary_battlefield_departure_id",
    "primary_battlefield_departure_states_from_payload",
    "record_primary_battlefield_departure",
    "validate_primary_battlefield_departure_states",
)
