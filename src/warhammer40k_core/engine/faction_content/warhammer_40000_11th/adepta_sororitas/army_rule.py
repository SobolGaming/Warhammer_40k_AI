from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollSpec,
    DiceRollState,
    DiceRollStatePayload,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battle_round_hooks import (
    BattleRoundStartHookBinding,
    BattleRoundStartRequestContext,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.faction_rule_states import FactionRuleState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, SetupStep
from warhammer40k_core.engine.unit_destroyed_hooks import (
    UnitDestroyedContext,
    UnitDestroyedHookBinding,
)
from warhammer40k_core.engine.unit_factory import UnitInstance

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


ADEPTA_SORORITAS_FACTION_ID = "adepta-sororitas"
ADEPTA_SORORITAS_FACTION_KEYWORD = "ADEPTA SORORITAS"
ACTS_OF_FAITH_ABILITY_NAME = "Acts of Faith"
SOURCE_RULE_ID = "phase17f:phase17e:adepta-sororitas:army-rule"

HOOK_ID = "warhammer_40000_11th:adepta_sororitas:army_rule:acts_of_faith"
CONTRIBUTION_ID = HOOK_ID
BATTLE_ROUND_START_HOOK_ID = f"{HOOK_ID}:battle-round-start"
UNIT_DESTROYED_HOOK_ID = f"{HOOK_ID}:unit-destroyed"
MIRACLE_DIE_GAIN_ROLL_TYPE = "adepta_sororitas_miracle_die_gain"
MIRACLE_DIE_GAIN_STATE_KIND = "adepta_sororitas_miracle_die_gain"
MIRACLE_DIE_SPEND_STATE_KIND = "adepta_sororitas_miracle_die_spent"
MIRACLE_DIE_GAINED_EVENT = "adepta_sororitas_miracle_die_gained"
MIRACLE_DIE_SPENT_EVENT = "adepta_sororitas_miracle_die_spent"
BATTLE_ROUND_START_TRIGGER = "battle_round_start"
UNIT_DESTROYED_TRIGGER = "adepta_sororitas_unit_destroyed"
_SUPPORTED_GAIN_TRIGGERS = frozenset({BATTLE_ROUND_START_TRIGGER, UNIT_DESTROYED_TRIGGER})


@dataclass(frozen=True, slots=True)
class MiracleDie:
    miracle_die_id: str
    player_id: str
    value: int
    gain_trigger: str
    source_id: str
    battle_round: int
    phase: BattlePhase
    roll_state: DiceRollState

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "miracle_die_id",
            _validate_identifier("MiracleDie miracle_die_id", self.miracle_die_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("MiracleDie player_id", self.player_id),
        )
        object.__setattr__(self, "gain_trigger", _validate_gain_trigger(self.gain_trigger))
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("MiracleDie source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("MiracleDie battle_round", self.battle_round),
        )
        object.__setattr__(self, "phase", _battle_phase_from_token(self.phase))
        if type(self.roll_state) is not DiceRollState:
            raise GameLifecycleError("MiracleDie roll_state must be DiceRollState.")
        if self.value != self.roll_state.current_total:
            raise GameLifecycleError("MiracleDie value must match the Miracle dice roll.")
        if self.value < 1 or self.value > 6:
            raise GameLifecycleError("MiracleDie value must be between 1 and 6.")

    def to_payload(self) -> dict[str, JsonValue]:
        return {
            "miracle_die_id": self.miracle_die_id,
            "player_id": self.player_id,
            "value": self.value,
            "gain_trigger": self.gain_trigger,
            "source_id": self.source_id,
            "battle_round": self.battle_round,
            "phase": self.phase.value,
            "roll_state": validate_json_value(self.roll_state.to_payload()),
        }

    @classmethod
    def from_payload(cls, payload: object) -> MiracleDie:
        payload_object = _payload_object(payload, field_name="MiracleDie payload")
        return cls(
            miracle_die_id=_payload_string(payload_object, key="miracle_die_id"),
            player_id=_payload_string(payload_object, key="player_id"),
            value=_payload_int(payload_object, key="value"),
            gain_trigger=_payload_string(payload_object, key="gain_trigger"),
            source_id=_payload_string(payload_object, key="source_id"),
            battle_round=_payload_int(payload_object, key="battle_round"),
            phase=_battle_phase_from_token(_payload_string(payload_object, key="phase")),
            roll_state=DiceRollState.from_payload(
                cast(
                    DiceRollStatePayload,
                    _payload_object(payload_object.get("roll_state"), field_name="roll_state"),
                )
            ),
        )

    @classmethod
    def from_state(cls, state: FactionRuleState) -> MiracleDie:
        if type(state) is not FactionRuleState:
            raise GameLifecycleError("MiracleDie state must be FactionRuleState.")
        if state.faction_id != ADEPTA_SORORITAS_FACTION_ID:
            raise GameLifecycleError("MiracleDie state faction drift.")
        if state.source_rule_id != SOURCE_RULE_ID:
            raise GameLifecycleError("MiracleDie state source drift.")
        if state.state_kind != MIRACLE_DIE_GAIN_STATE_KIND:
            raise GameLifecycleError("MiracleDie state kind drift.")
        return cls.from_payload(state.payload)


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        battle_round_start_hook_bindings=(
            BattleRoundStartHookBinding(
                hook_id=BATTLE_ROUND_START_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                request_handler=resolve_battle_round_start,
            ),
        ),
        unit_destroyed_hook_bindings=(
            UnitDestroyedHookBinding(
                hook_id=UNIT_DESTROYED_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=resolve_adepta_sororitas_unit_destroyed,
            ),
        ),
    )


def resolve_battle_round_start(
    context: BattleRoundStartRequestContext,
) -> DecisionRequest | None:
    if type(context) is not BattleRoundStartRequestContext:
        raise GameLifecycleError("Acts of Faith battle-round start requires hook context.")
    active_player_id = _active_player_id(context.state)
    for army in context.state.army_definitions:
        if army.detachment_selection.faction_id != ADEPTA_SORORITAS_FACTION_ID:
            continue
        gain_miracle_die(
            context.state,
            context.decisions,
            player_id=army.player_id,
            trigger=BATTLE_ROUND_START_TRIGGER,
            source_id=_battle_round_start_source_id(
                player_id=army.player_id,
                battle_round=context.state.battle_round,
            ),
            source_context={
                "active_player_id": active_player_id,
                "timing": "start_of_battle_round",
            },
        )
    return None


def resolve_adepta_sororitas_unit_destroyed(context: UnitDestroyedContext) -> None:
    if type(context) is not UnitDestroyedContext:
        raise GameLifecycleError("Acts of Faith unit-destroyed hook requires context.")
    army = _adepta_sororitas_army_for_player(context.state, player_id=context.destroyed_player_id)
    if army is None:
        return
    destroyed_unit = _unit_by_id(army, unit_instance_id=context.destroyed_unit_instance_id)
    if destroyed_unit is None:
        raise GameLifecycleError("Destroyed Adepta Sororitas unit was not found in its army.")
    if not _is_adepta_sororitas_unit(destroyed_unit):
        return
    gain_miracle_die(
        context.state,
        context.decisions,
        player_id=context.destroyed_player_id,
        trigger=UNIT_DESTROYED_TRIGGER,
        source_id=_unit_destroyed_source_id(
            player_id=context.destroyed_player_id,
            model_destroyed_event_id=context.model_destroyed_event_id,
        ),
        source_context={
            "completed_phase": context.completed_phase.value,
            "destroying_player_id": context.destroying_player_id,
            "destroyed_player_id": context.destroyed_player_id,
            "destroyed_unit_instance_id": context.destroyed_unit_instance_id,
            "model_destroyed_event_id": context.model_destroyed_event_id,
            "model_destroyed_payload": validate_json_value(context.model_destroyed_payload),
        },
    )


def gain_miracle_die(
    state: GameState,
    decisions: DecisionController,
    *,
    player_id: str,
    trigger: str,
    source_id: str,
    source_context: object,
) -> MiracleDie | None:
    _validate_state(state)
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Acts of Faith requires a DecisionController.")
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_source_id = _validate_identifier("source_id", source_id)
    requested_trigger = _validate_gain_trigger(trigger)
    validated_source_context = _payload_object(source_context, field_name="source_context")
    if _adepta_sororitas_army_for_player(state, player_id=requested_player_id) is None:
        raise GameLifecycleError("Acts of Faith can gain Miracle dice only for Adepta Sororitas.")
    if _gain_source_exists(state, player_id=requested_player_id, source_id=requested_source_id):
        return None
    current_phase = state.current_battle_phase
    if current_phase is None:
        raise GameLifecycleError("Acts of Faith Miracle dice gain requires a battle phase.")

    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    roll_state = manager.roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason="Acts of Faith Miracle dice gain",
            roll_type=MIRACLE_DIE_GAIN_ROLL_TYPE,
            actor_id=requested_player_id,
            reroll_forbidden_rule_ids=(SOURCE_RULE_ID,),
        )
    )
    die_index = _next_miracle_die_index(state, player_id=requested_player_id)
    die = MiracleDie(
        miracle_die_id=f"{requested_player_id}:miracle-die-{die_index:06d}",
        player_id=requested_player_id,
        value=roll_state.current_total,
        gain_trigger=requested_trigger,
        source_id=requested_source_id,
        battle_round=state.battle_round,
        phase=current_phase,
        roll_state=roll_state,
    )
    state_record = FactionRuleState(
        state_id=f"{HOOK_ID}:{requested_player_id}:miracle-die-{die_index:06d}",
        player_id=requested_player_id,
        faction_id=ADEPTA_SORORITAS_FACTION_ID,
        source_rule_id=SOURCE_RULE_ID,
        state_kind=MIRACLE_DIE_GAIN_STATE_KIND,
        setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
        request_id=f"{requested_source_id}:request",
        result_id=f"{requested_source_id}:result",
        payload=validate_json_value(
            {
                **die.to_payload(),
                "pool_index": die_index,
                "source_context": validate_json_value(validated_source_context),
            }
        ),
    )
    state.record_faction_rule_state(state_record)
    decisions.event_log.append(
        MIRACLE_DIE_GAINED_EVENT,
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": current_phase.value,
            "player_id": requested_player_id,
            "faction_id": ADEPTA_SORORITAS_FACTION_ID,
            "source_rule_id": SOURCE_RULE_ID,
            "hook_id": HOOK_ID,
            "trigger": requested_trigger,
            "source_id": requested_source_id,
            "miracle_die": die.to_payload(),
            "faction_rule_state": state_record.to_payload(),
            "source_context": validate_json_value(validated_source_context),
        },
    )
    return die


def spend_miracle_die(
    state: GameState,
    decisions: DecisionController,
    *,
    player_id: str,
    miracle_die_id: str,
    source_id: str,
    source_context: object,
) -> MiracleDie:
    _validate_state(state)
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Acts of Faith requires a DecisionController.")
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_die_id = _validate_identifier("miracle_die_id", miracle_die_id)
    requested_source_id = _validate_identifier("source_id", source_id)
    validated_source_context = _payload_object(source_context, field_name="source_context")
    if _spend_source_exists(state, player_id=requested_player_id, source_id=requested_source_id):
        raise GameLifecycleError("Acts of Faith spend source has already been recorded.")
    current_phase = state.current_battle_phase
    if current_phase is None:
        raise GameLifecycleError("Acts of Faith Miracle dice spend requires a battle phase.")
    for die in miracle_dice_pool(state, player_id=requested_player_id):
        if die.miracle_die_id != requested_die_id:
            continue
        spend_index = _next_miracle_die_spend_index(state, player_id=requested_player_id)
        state_record = FactionRuleState(
            state_id=f"{HOOK_ID}:{requested_player_id}:miracle-die-spent-{spend_index:06d}",
            player_id=requested_player_id,
            faction_id=ADEPTA_SORORITAS_FACTION_ID,
            source_rule_id=SOURCE_RULE_ID,
            state_kind=MIRACLE_DIE_SPEND_STATE_KIND,
            setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
            request_id=f"{requested_source_id}:request",
            result_id=f"{requested_source_id}:result",
            payload=validate_json_value(
                {
                    "miracle_die_id": die.miracle_die_id,
                    "player_id": requested_player_id,
                    "value": die.value,
                    "source_id": requested_source_id,
                    "source_rule_id": SOURCE_RULE_ID,
                    "battle_round": state.battle_round,
                    "phase": current_phase.value,
                    "source_context": validate_json_value(validated_source_context),
                }
            ),
        )
        state.record_faction_rule_state(state_record)
        decisions.event_log.append(
            MIRACLE_DIE_SPENT_EVENT,
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": current_phase.value,
                "player_id": requested_player_id,
                "faction_id": ADEPTA_SORORITAS_FACTION_ID,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
                "source_id": requested_source_id,
                "miracle_die": die.to_payload(),
                "faction_rule_state": state_record.to_payload(),
                "source_context": validate_json_value(validated_source_context),
            },
        )
        return die
    raise GameLifecycleError("Requested Miracle die is not available in the pool.")


def miracle_dice_pool(state: GameState, *, player_id: str) -> tuple[MiracleDie, ...]:
    _validate_state(state)
    requested_player_id = _validate_identifier("player_id", player_id)
    spent_die_ids = _spent_miracle_die_ids(state, player_id=requested_player_id)
    return tuple(
        die
        for die in (
            MiracleDie.from_state(gain_state)
            for gain_state in _miracle_die_gain_states(state, player_id=requested_player_id)
        )
        if die.miracle_die_id not in spent_die_ids
    )


def miracle_dice_values(state: GameState, *, player_id: str) -> tuple[int, ...]:
    return tuple(die.value for die in miracle_dice_pool(state, player_id=player_id))


def _battle_round_start_source_id(*, player_id: str, battle_round: int) -> str:
    return f"{SOURCE_RULE_ID}:battle-round-start:round-{battle_round:02d}:player-{player_id}"


def _unit_destroyed_source_id(*, player_id: str, model_destroyed_event_id: str) -> str:
    requested_event_id = _validate_identifier("model_destroyed_event_id", model_destroyed_event_id)
    return f"{SOURCE_RULE_ID}:unit-destroyed:{requested_event_id}:player-{player_id}"


def _adepta_sororitas_army_for_player(
    state: GameState,
    *,
    player_id: str,
) -> ArmyDefinition | None:
    requested_player_id = _validate_identifier("player_id", player_id)
    army = state.army_definition_for_player(requested_player_id)
    if army is None:
        return None
    if army.detachment_selection.faction_id != ADEPTA_SORORITAS_FACTION_ID:
        return None
    return army


def _unit_by_id(army: ArmyDefinition, *, unit_instance_id: str) -> UnitInstance | None:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for unit in army.units:
        if unit.unit_instance_id == requested_unit_id:
            return unit
    return None


def _is_adepta_sororitas_unit(unit: UnitInstance) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Acts of Faith unit lookup requires UnitInstance.")
    return any(
        _canonical_keyword(keyword) == ADEPTA_SORORITAS_FACTION_KEYWORD
        for keyword in unit.faction_keywords
    )


def _miracle_die_gain_states(state: GameState, *, player_id: str) -> tuple[FactionRuleState, ...]:
    return tuple(
        record
        for record in state.faction_rule_states_for_player(
            player_id=player_id,
            state_kind=MIRACLE_DIE_GAIN_STATE_KIND,
        )
        if record.faction_id == ADEPTA_SORORITAS_FACTION_ID
        and record.source_rule_id == SOURCE_RULE_ID
    )


def _miracle_die_spend_states(state: GameState, *, player_id: str) -> tuple[FactionRuleState, ...]:
    return tuple(
        record
        for record in state.faction_rule_states_for_player(
            player_id=player_id,
            state_kind=MIRACLE_DIE_SPEND_STATE_KIND,
        )
        if record.faction_id == ADEPTA_SORORITAS_FACTION_ID
        and record.source_rule_id == SOURCE_RULE_ID
    )


def _spent_miracle_die_ids(state: GameState, *, player_id: str) -> frozenset[str]:
    spent_ids: set[str] = set()
    for spend_state in _miracle_die_spend_states(state, player_id=player_id):
        payload = _payload_object(spend_state.payload, field_name="Miracle die spend payload")
        spent_ids.add(_payload_string(payload, key="miracle_die_id"))
    return frozenset(spent_ids)


def _gain_source_exists(state: GameState, *, player_id: str, source_id: str) -> bool:
    requested_source_id = _validate_identifier("source_id", source_id)
    for gain_state in _miracle_die_gain_states(state, player_id=player_id):
        payload = _payload_object(gain_state.payload, field_name="Miracle die gain payload")
        if _payload_string(payload, key="source_id") == requested_source_id:
            return True
    return False


def _spend_source_exists(state: GameState, *, player_id: str, source_id: str) -> bool:
    requested_source_id = _validate_identifier("source_id", source_id)
    for spend_state in _miracle_die_spend_states(state, player_id=player_id):
        payload = _payload_object(spend_state.payload, field_name="Miracle die spend payload")
        if _payload_string(payload, key="source_id") == requested_source_id:
            return True
    return False


def _next_miracle_die_index(state: GameState, *, player_id: str) -> int:
    return len(_miracle_die_gain_states(state, player_id=player_id)) + 1


def _next_miracle_die_spend_index(state: GameState, *, player_id: str) -> int:
    return len(_miracle_die_spend_states(state, player_id=player_id)) + 1


def _payload_object(value: object, *, field_name: str) -> dict[str, JsonValue]:
    payload = validate_json_value(value)
    if not isinstance(payload, dict):
        raise GameLifecycleError(f"{field_name} must be a JSON object.")
    return payload


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"{key} must be a non-empty string.")
    return value


def _payload_int(payload: dict[str, JsonValue], *, key: str) -> int:
    value = payload.get(key)
    if type(value) is not int:
        raise GameLifecycleError(f"{key} must be an integer.")
    return value


def _active_player_id(state: GameState) -> str:
    if state.active_player_id is None:
        raise GameLifecycleError("Acts of Faith battle-round start requires active player.")
    return state.active_player_id


def _validate_state(state: object) -> GameState:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Acts of Faith requires GameState.")
    return state


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Acts of Faith {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Acts of Faith {field_name} must not be empty.")
    return stripped


def _validate_gain_trigger(value: object) -> str:
    trigger = _validate_identifier("gain trigger", value)
    if trigger not in _SUPPORTED_GAIN_TRIGGERS:
        raise GameLifecycleError(f"Unsupported Acts of Faith gain trigger: {trigger}.")
    return trigger


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be at least 1.")
    return value


def _battle_phase_from_token(token: object) -> BattlePhase:
    if type(token) is BattlePhase:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Acts of Faith phase must be a BattlePhase token.")
    try:
        return BattlePhase(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported Acts of Faith phase: {token}.") from exc


def _canonical_keyword(keyword: str) -> str:
    return " ".join(keyword.replace("_", " ").upper().split())
