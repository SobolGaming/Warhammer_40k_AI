"""Source-authorized empty Dedicated Transport destruction at formation reveal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypedDict, cast

from warhammer40k_core.engine.battlefield_state import PlacementError
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError, SetupStep
from warhammer40k_core.engine.rule_model_destruction_unplaced import (
    destroy_unplaced_model_without_reactions,
)
from warhammer40k_core.engine.unit_keyword_queries import (
    unit_has_keyword,
    unit_has_roster_keyword,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_empty_dedicated_transport_2026_09 as empty_dedicated_transport_source,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState

EMPTY_DEDICATED_TRANSPORT_SOURCE_ID = (
    empty_dedicated_transport_source.EMPTY_DEDICATED_TRANSPORT_SOURCE_ID
)
DESTRUCTION_POLICY = empty_dedicated_transport_source.DESTRUCTION_POLICY
EMPTY_DEDICATED_TRANSPORTS_DESTROYED_EVENT_TYPE = "empty_dedicated_transports_destroyed"
_DEDICATED_TRANSPORT_KEYWORD = "DEDICATED TRANSPORT"


class EmptyDedicatedTransportDestructionUnitPayload(TypedDict):
    player_id: str
    transport_unit_instance_id: str
    model_instance_ids: list[str]


class EmptyDedicatedTransportDestructionResultPayload(TypedDict):
    source_rule_id: str
    setup_step: str
    destroyed_model_rules_triggered: bool
    destroyed_units: list[EmptyDedicatedTransportDestructionUnitPayload]


@dataclass(frozen=True, slots=True)
class EmptyDedicatedTransportDestructionUnit:
    player_id: str
    transport_unit_instance_id: str
    model_instance_ids: tuple[str, ...]

    def to_payload(self) -> EmptyDedicatedTransportDestructionUnitPayload:
        return {
            "player_id": self.player_id,
            "transport_unit_instance_id": self.transport_unit_instance_id,
            "model_instance_ids": list(self.model_instance_ids),
        }


@dataclass(frozen=True, slots=True)
class EmptyDedicatedTransportDestructionResult:
    source_rule_id: str
    setup_step: SetupStep
    destroyed_model_rules_triggered: bool
    destroyed_units: tuple[EmptyDedicatedTransportDestructionUnit, ...]

    def to_payload(self) -> EmptyDedicatedTransportDestructionResultPayload:
        return {
            "source_rule_id": self.source_rule_id,
            "setup_step": self.setup_step.value,
            "destroyed_model_rules_triggered": self.destroyed_model_rules_triggered,
            "destroyed_units": [unit.to_payload() for unit in self.destroyed_units],
        }


def apply_empty_dedicated_transport_destruction(
    *,
    state: GameState,
    decisions: DecisionController,
) -> EmptyDedicatedTransportDestructionResult:
    """Destroy empty Dedicated Transports at the end of Declare Battle Formations."""

    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState

    _assert_destruction_policy()
    if type(state) is not GameState:
        raise GameLifecycleError("Empty Dedicated Transport destruction requires GameState.")
    if type(decisions) is not DecisionController:
        raise GameLifecycleError(
            "Empty Dedicated Transport destruction requires DecisionController."
        )
    if state.current_setup_step is not SetupStep.DECLARE_BATTLE_FORMATIONS:
        raise GameLifecycleError(
            "Empty Dedicated Transport destruction requires Declare Battle Formations."
        )
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError(
            "Empty Dedicated Transport destruction requires battlefield state."
        )
    placed_model_ids = set(battlefield.placed_model_ids())
    removed_model_ids = set(battlefield.removed_model_ids)
    destroyed_units: list[EmptyDedicatedTransportDestructionUnit] = []
    newly_removed_model_ids: list[str] = []
    for army in sorted(state.army_definitions, key=lambda army: army.player_id):
        for unit in sorted(army.units, key=lambda candidate: candidate.unit_instance_id):
            if not unit_has_keyword(unit, _DEDICATED_TRANSPORT_KEYWORD):
                continue
            cargo_state = state.transport_cargo_state_for_transport(unit.unit_instance_id)
            if cargo_state is not None and cargo_state.embarked_unit_instance_ids:
                continue
            living_model_ids = tuple(
                model.model_instance_id for model in unit.own_models if model.is_alive
            )
            destroyed_model_ids = tuple(
                model.model_instance_id for model in unit.own_models if not model.is_alive
            )
            if living_model_ids and destroyed_model_ids:
                raise GameLifecycleError(
                    "Empty Dedicated Transport cannot mix living and destroyed models."
                )
            model_ids = living_model_ids or destroyed_model_ids
            if not model_ids:
                raise GameLifecycleError("Empty Dedicated Transport has no models.")
            if any(model_id in placed_model_ids for model_id in model_ids):
                raise GameLifecycleError(
                    "Empty Dedicated Transport cannot be placed before it is destroyed."
                )
            if not living_model_ids and all(
                model_id in removed_model_ids for model_id in destroyed_model_ids
            ):
                continue
            for model_id in living_model_ids:
                destroy_unplaced_model_without_reactions(
                    state=state,
                    model_instance_id=model_id,
                )
            for model_id in model_ids:
                if model_id in removed_model_ids:
                    continue
                newly_removed_model_ids.append(model_id)
                removed_model_ids.add(model_id)
            destroyed_units.append(
                EmptyDedicatedTransportDestructionUnit(
                    player_id=army.player_id,
                    transport_unit_instance_id=unit.unit_instance_id,
                    model_instance_ids=model_ids,
                )
            )
    if newly_removed_model_ids:
        current_battlefield = state.battlefield_state
        if current_battlefield is None:
            raise GameLifecycleError(
                "Empty Dedicated Transport destruction requires battlefield state."
            )
        try:
            state.replace_battlefield_state(
                current_battlefield.with_unplaced_models_marked_removed(
                    tuple(sorted(newly_removed_model_ids))
                )
            )
        except PlacementError as exc:
            raise GameLifecycleError("Empty Dedicated Transport removal failed.") from exc
    result = EmptyDedicatedTransportDestructionResult(
        source_rule_id=EMPTY_DEDICATED_TRANSPORT_SOURCE_ID,
        setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
        destroyed_model_rules_triggered=False,
        destroyed_units=tuple(destroyed_units),
    )
    if destroyed_units:
        decisions.event_log.append(
            EMPTY_DEDICATED_TRANSPORTS_DESTROYED_EVENT_TYPE,
            _event_payload(state=state, result=result),
        )
    return result


def authenticated_empty_dedicated_transport_casualty_model_ids(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
) -> frozenset[str]:
    """Return empty Dedicated Transport models authenticated by the public event."""

    from warhammer40k_core.engine.game_state import GameState

    _assert_destruction_policy()
    if type(state) is not GameState:
        raise GameLifecycleError("Empty Dedicated Transport restore requires GameState.")
    events = tuple(
        event
        for event in event_records
        if event.event_type == EMPTY_DEDICATED_TRANSPORTS_DESTROYED_EVENT_TYPE
    )
    if not events:
        return frozenset()
    if len(events) != 1:
        raise GameLifecycleError("Empty Dedicated Transport destruction events are duplicated.")
    return _casualty_model_ids_from_destruction_event(state=state, event=events[0])


def _casualty_model_ids_from_destruction_event(
    *,
    state: GameState,
    event: EventRecord,
) -> frozenset[str]:
    payload = event.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Empty Dedicated Transport destruction event payload drifted.")
    required = {
        "game_id",
        "setup_step",
        "source_rule_id",
        "destroyed_model_rules_triggered",
        "destroyed_units",
    }
    if set(payload) != required:
        raise GameLifecycleError("Empty Dedicated Transport destruction event payload drifted.")
    if payload["game_id"] != state.game_id:
        raise GameLifecycleError("Empty Dedicated Transport destruction event game_id drifted.")
    if payload["setup_step"] != SetupStep.DECLARE_BATTLE_FORMATIONS.value:
        raise GameLifecycleError("Empty Dedicated Transport destruction event setup step drifted.")
    if payload["source_rule_id"] != EMPTY_DEDICATED_TRANSPORT_SOURCE_ID:
        raise GameLifecycleError("Empty Dedicated Transport destruction event source drifted.")
    if payload["destroyed_model_rules_triggered"] is not False:
        raise GameLifecycleError(
            "Empty Dedicated Transport destruction event must not trigger destroyed-model rules."
        )
    destroyed_units = payload["destroyed_units"]
    if not isinstance(destroyed_units, list) or not destroyed_units:
        raise GameLifecycleError("Empty Dedicated Transport destruction event units drifted.")
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError(
            "Empty Dedicated Transport destruction event requires battlefield state."
        )
    placed_model_ids = set(battlefield.placed_model_ids())
    removed_model_ids = set(battlefield.removed_model_ids)
    units_by_id = {
        unit.unit_instance_id: (army.player_id, unit)
        for army in state.army_definitions
        for unit in army.units
    }
    casualty_model_ids: set[str] = set()
    seen_transport_ids: set[str] = set()
    for row in destroyed_units:
        if not isinstance(row, dict) or set(row) != {
            "player_id",
            "transport_unit_instance_id",
            "model_instance_ids",
        }:
            raise GameLifecycleError("Empty Dedicated Transport destruction event unit drifted.")
        player_id = row["player_id"]
        transport_unit_id = row["transport_unit_instance_id"]
        model_ids = row["model_instance_ids"]
        if type(player_id) is not str or type(transport_unit_id) is not str:
            raise GameLifecycleError("Empty Dedicated Transport destruction event unit drifted.")
        if not isinstance(model_ids, list) or not model_ids:
            raise GameLifecycleError("Empty Dedicated Transport destruction event models drifted.")
        if any(type(model_id) is not str for model_id in model_ids):
            raise GameLifecycleError("Empty Dedicated Transport destruction event models drifted.")
        if transport_unit_id in seen_transport_ids:
            raise GameLifecycleError(
                "Empty Dedicated Transport destruction event units duplicated."
            )
        seen_transport_ids.add(transport_unit_id)
        owner = units_by_id.get(transport_unit_id)
        if owner is None:
            raise GameLifecycleError(
                "Empty Dedicated Transport destruction event Transport unknown."
            )
        owner_player_id, unit = owner
        if owner_player_id != player_id:
            raise GameLifecycleError("Empty Dedicated Transport destruction event player drifted.")
        if not unit_has_roster_keyword(unit, _DEDICATED_TRANSPORT_KEYWORD):
            raise GameLifecycleError(
                "Empty Dedicated Transport destruction event requires a Dedicated Transport."
            )
        cargo_state = state.transport_cargo_state_for_transport(transport_unit_id)
        if cargo_state is not None and cargo_state.embarked_unit_instance_ids:
            raise GameLifecycleError(
                "Empty Dedicated Transport destruction event Transport still has cargo."
            )
        expected_model_ids = unit.own_model_ids()
        if tuple(model_ids) != expected_model_ids:
            raise GameLifecycleError("Empty Dedicated Transport destruction event models drifted.")
        if any(model.is_alive or model.wounds_remaining != 0 for model in unit.own_models):
            raise GameLifecycleError(
                "Empty Dedicated Transport destruction event requires destroyed models."
            )
        if any(model_id in placed_model_ids for model_id in expected_model_ids):
            raise GameLifecycleError(
                "Empty Dedicated Transport destruction event models are still placed."
            )
        if any(model_id not in removed_model_ids for model_id in expected_model_ids):
            raise GameLifecycleError(
                "Empty Dedicated Transport destruction event models must be removed."
            )
        overlapping = casualty_model_ids.intersection(expected_model_ids)
        if overlapping:
            raise GameLifecycleError(
                "Empty Dedicated Transport destruction event models duplicated."
            )
        casualty_model_ids.update(expected_model_ids)
    return frozenset(casualty_model_ids)


def _assert_destruction_policy() -> None:
    if (
        DESTRUCTION_POLICY.source_rule_id != EMPTY_DEDICATED_TRANSPORT_SOURCE_ID
        or DESTRUCTION_POLICY.destroys_at_declare_battle_formations_end is not True
        or DESTRUCTION_POLICY.triggers_destroyed_model_rules is not False
        or DESTRUCTION_POLICY.requires_embarked_unit is not True
    ):
        raise GameLifecycleError("Empty Dedicated Transport destruction policy drifted.")


def _event_payload(
    *,
    state: GameState,
    result: EmptyDedicatedTransportDestructionResult,
) -> dict[str, JsonValue]:
    payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "setup_step": result.setup_step.value,
        "source_rule_id": result.source_rule_id,
        "destroyed_model_rules_triggered": result.destroyed_model_rules_triggered,
        "destroyed_units": cast(
            JsonValue,
            [unit.to_payload() for unit in result.destroyed_units],
        ),
    }
    validated = validate_json_value(payload)
    if not isinstance(validated, dict):
        raise GameLifecycleError("Empty Dedicated Transport destruction event payload drifted.")
    return validated
