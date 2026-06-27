from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice import D3RollResult, DiceExpression, DiceRollSpec
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battle_round_hooks import (
    SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
    BattleRoundStartHookBinding,
    BattleRoundStartRequestContext,
    BattleRoundStartResultContext,
)
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockForcedTestContext,
    BattleShockHookBinding,
    BattleShockOutcomeContext,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    PlacementError,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.damage_allocation import apply_mortal_wounds_to_unit
from warhammer40k_core.engine.decision_request import DecisionError, DecisionOption, DecisionRequest
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.faction_rule_states import FactionRuleState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, SetupStep
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierBinding,
    HitRollModifierContext,
    UnitCharacteristicModifierBinding,
    UnitCharacteristicModifierContext,
    WoundRollModifierBinding,
    WoundRollModifierContext,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext, StartingStrengthRecord
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.volume import Model as GeometryModel

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

CONTRIBUTION_ID = "warhammer_40000_11th:chaos_knights:army_rule:scaffold"
HOOK_ID = "warhammer_40000_11th:chaos_knights:army_rule:harbingers_of_dread"
BATTLE_SHOCK_HOOK_ID = f"{HOOK_ID}:battle-shock"
LEADERSHIP_MODIFIER_ID = f"{HOOK_ID}:leadership"
DARKNESS_HIT_MODIFIER_ID = f"{HOOK_ID}:darkness:hit-roll"
DOOM_WOUND_MODIFIER_ID = f"{HOOK_ID}:doom:wound-roll"
SOURCE_RULE_ID = "phase17f:phase17e:chaos-knights:army-rule"
CHAOS_KNIGHTS_FACTION_ID = "chaos-knights"
CHAOS_KNIGHTS_FACTION_KEYWORD = "CHAOS KNIGHTS"
HARBINGERS_STATE_KIND = "chaos_knights_harbingers_of_dread_selection"
HARBINGERS_SELECTION_KIND = "select_chaos_knights_harbingers_of_dread"
HARBINGERS_EFFECT_KIND = "chaos_knights_harbingers_of_dread"
HARBINGERS_DREAD_ROLL_TYPE = "chaos_knights_harbingers_of_dread"
HARBINGERS_DELIRIUM_D3_ROLL_TYPE = "chaos_knights_delirium_mortal_wounds_d3"
ROLL_SELECTION_OPTION_ID = "chaos_knights:harbingers_of_dread:roll"
DREAD_SELECTION_BATTLE_ROUNDS = frozenset({1, 3, 5})
DREAD_AURA_RANGE_INCHES = 9.0
DREAD_AURA_RANGE_WITH_DOMINION_INCHES = 12.0
DARKNESS_RULE_UPDATE_SOURCE = (
    "warhammer_40000_11th:chaos_knights:faction_pack:rules_updates:darkness"
)


class DreadAbility(StrEnum):
    DEATHLY_TERROR = "deathly_terror"
    DESPAIR = "despair"
    DOOM = "doom"
    DARKNESS = "darkness"
    DISMAY = "dismay"
    DELIRIUM = "delirium"
    DOMINION = "dominion"


@dataclass(frozen=True, slots=True)
class DreadAbilityDefinition:
    ability: DreadAbility
    label: str
    effect_summary: str
    roll_result: int | None = None
    is_aura: bool = False

    def __post_init__(self) -> None:
        if type(self.ability) is not DreadAbility:
            raise GameLifecycleError("Dread ability definition ability drift.")
        if type(self.label) is not str or not self.label.strip():
            raise GameLifecycleError("Dread ability definition label must be non-empty.")
        if type(self.effect_summary) is not str or not self.effect_summary.strip():
            raise GameLifecycleError("Dread ability definition summary must be non-empty.")
        if self.roll_result is not None and (
            type(self.roll_result) is not int or not 1 <= self.roll_result <= 6
        ):
            raise GameLifecycleError("Dread ability roll_result must be a D6 face.")
        if type(self.is_aura) is not bool:
            raise GameLifecycleError("Dread ability is_aura must be a bool.")


DREAD_DEFINITIONS: tuple[DreadAbilityDefinition, ...] = (
    DreadAbilityDefinition(
        ability=DreadAbility.DEATHLY_TERROR,
        label="Deathly Terror",
        effect_summary='Enemy units within 9" worsen Leadership by 1.',
        is_aura=True,
    ),
    DreadAbilityDefinition(
        ability=DreadAbility.DESPAIR,
        label="Despair",
        effect_summary='Enemy units within 9" worsen Leadership by 1.',
        roll_result=1,
        is_aura=True,
    ),
    DreadAbilityDefinition(
        ability=DreadAbility.DOOM,
        label="Doom",
        effect_summary="Add 1 to wound rolls when targeting Battle-shocked units.",
        roll_result=2,
    ),
    DreadAbilityDefinition(
        ability=DreadAbility.DARKNESS,
        label="Darkness",
        effect_summary="Chaos Knights models have Stealth.",
        roll_result=3,
    ),
    DreadAbilityDefinition(
        ability=DreadAbility.DISMAY,
        label="Dismay",
        effect_summary=(
            "In the opponent's Command phase, below Starting Strength enemy units within "
            '9" must take a Battle-shock test.'
        ),
        roll_result=4,
        is_aura=True,
    ),
    DreadAbilityDefinition(
        ability=DreadAbility.DELIRIUM,
        label="Delirium",
        effect_summary=(
            'Below Half-strength enemy units within 9" suffer D3 mortal wounds after '
            "failing a Battle-shock test."
        ),
        roll_result=5,
        is_aura=True,
    ),
    DreadAbilityDefinition(
        ability=DreadAbility.DOMINION,
        label="Dominion",
        effect_summary='Add 3" to the range of Harbingers of Dread Aura abilities.',
        roll_result=6,
    ),
)
_DEFINITIONS_BY_DREAD = {definition.ability: definition for definition in DREAD_DEFINITIONS}
ROLLABLE_DREAD_ABILITIES: tuple[DreadAbility, ...] = tuple(
    definition.ability for definition in DREAD_DEFINITIONS if definition.roll_result is not None
)
_DREAD_BY_ROLL = {
    definition.roll_result: definition.ability
    for definition in DREAD_DEFINITIONS
    if definition.roll_result is not None
}


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        battle_round_start_hook_bindings=(
            BattleRoundStartHookBinding(
                hook_id=HOOK_ID,
                source_id=SOURCE_RULE_ID,
                request_handler=harbingers_selection_request,
                result_handler=apply_harbingers_selection_result,
            ),
        ),
        battle_shock_hook_bindings=(
            BattleShockHookBinding(
                hook_id=BATTLE_SHOCK_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                forced_test_handler=harbingers_forced_battle_shock_unit_ids,
                outcome_handler=resolve_harbingers_battle_shock_outcome,
            ),
        ),
        unit_characteristic_modifier_bindings=(
            UnitCharacteristicModifierBinding(
                modifier_id=LEADERSHIP_MODIFIER_ID,
                source_id=SOURCE_RULE_ID,
                handler=harbingers_leadership_modifier,
            ),
        ),
        hit_roll_modifier_bindings=(
            HitRollModifierBinding(
                modifier_id=DARKNESS_HIT_MODIFIER_ID,
                source_id=SOURCE_RULE_ID,
                handler=harbingers_darkness_hit_roll_modifier,
            ),
        ),
        wound_roll_modifier_bindings=(
            WoundRollModifierBinding(
                modifier_id=DOOM_WOUND_MODIFIER_ID,
                source_id=SOURCE_RULE_ID,
                handler=harbingers_doom_wound_roll_modifier,
            ),
        ),
    )


def harbingers_selection_request(
    context: BattleRoundStartRequestContext,
) -> DecisionRequest | None:
    if type(context) is not BattleRoundStartRequestContext:
        raise GameLifecycleError("Harbingers of Dread requires request context.")
    if context.state.battle_round not in DREAD_SELECTION_BATTLE_ROUNDS:
        return None
    for army in _chaos_knights_armies(context.state):
        if _selection_recorded_for_round(
            context.state,
            player_id=army.player_id,
            battle_round=context.state.battle_round,
        ):
            continue
        target_unit_ids = _eligible_harbingers_unit_ids_for_army(army)
        if not target_unit_ids:
            continue
        active = active_dread_abilities_for_player(context.state, player_id=army.player_id)
        available = _available_dread_abilities(active)
        if not available:
            continue
        common_payload = _selection_common_payload(
            state=context.state,
            player_id=army.player_id,
            target_unit_ids=target_unit_ids,
            active=active,
            available=available,
        )
        return DecisionRequest(
            request_id=context.state.next_decision_request_id(),
            decision_type=SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
            actor_id=army.player_id,
            payload=validate_json_value(common_payload),
            options=harbingers_selection_options(
                common_payload=common_payload,
                available=available,
            ),
        )
    return None


def apply_harbingers_selection_result(context: BattleRoundStartResultContext) -> bool:
    if type(context) is not BattleRoundStartResultContext:
        raise GameLifecycleError("Harbingers of Dread requires result context.")
    if context.request.decision_type != SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE:
        return False
    request_payload = _payload_object(context.request.payload)
    if request_payload.get("hook_id") != HOOK_ID:
        return False
    if result_actor_is_missing(context):
        raise GameLifecycleError("Harbingers of Dread selection requires an actor.")
    player_id = cast(str, context.result.actor_id)
    army = _chaos_knights_army_for_player(context.state, player_id=player_id)
    if army is None:
        raise GameLifecycleError("Harbingers of Dread actor does not own Chaos Knights.")
    if context.state.battle_round not in DREAD_SELECTION_BATTLE_ROUNDS:
        raise GameLifecycleError("Harbingers of Dread selection is not available this round.")
    if _selection_recorded_for_round(
        context.state,
        player_id=player_id,
        battle_round=context.state.battle_round,
    ):
        raise GameLifecycleError("Harbingers of Dread selection is already recorded this round.")
    _validate_request_matches_current_state(context=context, army=army)
    try:
        expected_option = context.request.option_by_id(context.result.selected_option_id)
    except DecisionError as exc:
        raise GameLifecycleError("Harbingers of Dread selected option is not available.") from exc
    if context.result.payload != expected_option.payload:
        raise GameLifecycleError("Harbingers of Dread selected option payload drift.")

    payload = _payload_object(context.result.payload)
    selection_mode = _payload_string(payload, key="selection_mode")
    active = active_dread_abilities_for_player(context.state, player_id=player_id)
    dice_values: tuple[int, ...] = ()
    roll_payload: JsonValue = None
    if selection_mode == "select":
        selected = tuple(
            _dread_from_token(token)
            for token in _payload_string_list(payload, key="selected_dread_ability_ids")
        )
        _validate_manual_selection(selected=selected, active=active)
    elif selection_mode == "roll_2d6":
        roll_state = DiceRollManager(
            context.state.game_id,
            event_log=context.decisions.event_log,
        ).roll(
            DiceRollSpec(
                expression=DiceExpression(quantity=2, sides=6),
                reason="Harbingers of Dread",
                roll_type=HARBINGERS_DREAD_ROLL_TYPE,
                actor_id=player_id,
            )
        )
        dice_values = tuple(roll_state.current_values)
        roll_payload = validate_json_value(roll_state.to_payload())
        selected = _dread_abilities_from_dice_values(dice_values, active=active)
    else:
        raise GameLifecycleError("Harbingers of Dread selection mode is unsupported.")

    state_record = _harbingers_selection_state(
        context=context,
        player_id=player_id,
        selected=selected,
        selection_mode=selection_mode,
        dice_values=dice_values,
        roll_payload=roll_payload,
    )
    context.state.record_faction_rule_state(state_record)
    context.decisions.event_log.append(
        "chaos_knights_harbingers_of_dread_selected",
        validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "player_id": player_id,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
                "selection_mode": selection_mode,
                "selected_dread_ability_ids": [ability.value for ability in selected],
                "dice_values": list(dice_values),
                "faction_rule_state": state_record.to_payload(),
            }
        ),
    )
    return True


def result_actor_is_missing(context: BattleRoundStartResultContext) -> bool:
    if type(context) is not BattleRoundStartResultContext:
        raise GameLifecycleError("Harbingers of Dread result actor check requires context.")
    return context.result.actor_id is None


def harbingers_selection_options(
    *,
    common_payload: dict[str, JsonValue],
    available: tuple[DreadAbility, ...],
) -> tuple[DecisionOption, ...]:
    payload = validate_json_value(common_payload)
    if not isinstance(payload, dict):
        raise GameLifecycleError("Harbingers of Dread common payload must be an object.")
    options = [
        DecisionOption(
            option_id=ROLL_SELECTION_OPTION_ID,
            label="Roll 2D6",
            payload=validate_json_value(
                {
                    **payload,
                    "submission_kind": HARBINGERS_SELECTION_KIND,
                    "selection_mode": "roll_2d6",
                    "selected_dread_ability_ids": [],
                    "selected_dread_ability_labels": [],
                }
            ),
        )
    ]
    for ability in available:
        definition = _DEFINITIONS_BY_DREAD[ability]
        options.append(
            DecisionOption(
                option_id=f"chaos_knights:harbingers_of_dread:{ability.value}",
                label=definition.label,
                payload=validate_json_value(
                    {
                        **payload,
                        "submission_kind": HARBINGERS_SELECTION_KIND,
                        "selection_mode": "select",
                        "selected_dread_ability_ids": [ability.value],
                        "selected_dread_ability_labels": [definition.label],
                        "selected_dread_ability_summary": definition.effect_summary,
                    }
                ),
            )
        )
    return tuple(options)


def active_dread_abilities_for_player(
    state: GameState,
    *,
    player_id: str,
) -> tuple[DreadAbility, ...]:
    _validate_game_state(state)
    active = {DreadAbility.DEATHLY_TERROR}
    for state_record in _dread_selection_states_for_player(state, player_id=player_id):
        payload = _payload_object(state_record.payload)
        for token in _payload_string_list(payload, key="selected_dread_ability_ids"):
            ability = _dread_from_token(token)
            if ability is DreadAbility.DEATHLY_TERROR:
                raise GameLifecycleError("Deathly Terror must not be selected.")
            if ability in active:
                raise GameLifecycleError("Harbingers of Dread active lookup found duplicates.")
            active.add(ability)
    return tuple(
        definition.ability for definition in DREAD_DEFINITIONS if definition.ability in active
    )


def unit_has_active_dread(
    state: GameState,
    *,
    unit_instance_id: str,
    dread: DreadAbility,
) -> bool:
    _validate_game_state(state)
    requested_dread = _dread_from_token(dread)
    unit, army = _unit_and_army_by_id(state, unit_instance_id=unit_instance_id)
    if not _unit_has_harbingers(unit):
        return False
    if _chaos_knights_army_for_player(state, player_id=army.player_id) is None:
        return False
    return requested_dread in active_dread_abilities_for_player(state, player_id=army.player_id)


def harbingers_leadership_modifier(context: UnitCharacteristicModifierContext) -> int:
    if type(context) is not UnitCharacteristicModifierContext:
        raise GameLifecycleError("Harbingers of Dread Leadership modifier requires context.")
    if context.characteristic is not Characteristic.LEADERSHIP:
        return context.current_value
    _target_unit, target_army = _unit_and_army_by_id(
        context.state,
        unit_instance_id=context.unit_instance_id,
    )
    modifier = 0
    for chaos_knights_army in _chaos_knights_armies(context.state):
        if chaos_knights_army.player_id == target_army.player_id:
            continue
        active = active_dread_abilities_for_player(
            context.state,
            player_id=chaos_knights_army.player_id,
        )
        if not _unit_within_dread_aura(
            state=context.state,
            dread_army=chaos_knights_army,
            target_unit_instance_id=context.unit_instance_id,
        ):
            continue
        if DreadAbility.DEATHLY_TERROR in active:
            modifier += 1
        if DreadAbility.DESPAIR in active:
            modifier += 1
    return context.current_value + modifier


def harbingers_darkness_hit_roll_modifier(context: HitRollModifierContext) -> int:
    if type(context) is not HitRollModifierContext:
        raise GameLifecycleError("Harbingers of Dread Darkness hit modifier requires context.")
    if context.source_phase is not BattlePhase.SHOOTING:
        return 0
    _attacker, attacker_army = _unit_and_army_by_id(
        context.state,
        unit_instance_id=context.attacking_unit_instance_id,
    )
    target_unit, target_army = _unit_and_army_by_id(
        context.state,
        unit_instance_id=context.target_unit_instance_id,
    )
    if attacker_army.player_id == target_army.player_id:
        return 0
    if not _unit_has_harbingers(target_unit):
        return 0
    if _chaos_knights_army_for_player(context.state, player_id=target_army.player_id) is None:
        return 0
    if DreadAbility.DARKNESS not in active_dread_abilities_for_player(
        context.state,
        player_id=target_army.player_id,
    ):
        return 0
    return -1


def harbingers_doom_wound_roll_modifier(context: WoundRollModifierContext) -> int:
    if type(context) is not WoundRollModifierContext:
        raise GameLifecycleError("Harbingers of Dread Doom wound modifier requires context.")
    if context.target_unit_instance_id not in context.state.battle_shocked_unit_ids:
        return 0
    if not unit_has_active_dread(
        context.state,
        unit_instance_id=context.attacking_unit_instance_id,
        dread=DreadAbility.DOOM,
    ):
        return 0
    _attacker, attacker_army = _unit_and_army_by_id(
        context.state,
        unit_instance_id=context.attacking_unit_instance_id,
    )
    _target, target_army = _unit_and_army_by_id(
        context.state,
        unit_instance_id=context.target_unit_instance_id,
    )
    if attacker_army.player_id == target_army.player_id:
        return 0
    return 1


def harbingers_forced_battle_shock_unit_ids(
    context: BattleShockForcedTestContext,
) -> tuple[str, ...]:
    if type(context) is not BattleShockForcedTestContext:
        raise GameLifecycleError("Harbingers of Dread forced tests require context.")
    if context.phase is not BattlePhase.COMMAND:
        return ()
    active_army = context.state.army_definition_for_player(context.active_player_id)
    if active_army is None:
        raise GameLifecycleError("Harbingers of Dread forced tests require active army.")
    forced_ids: set[str] = set()
    for chaos_knights_army in _chaos_knights_armies(context.state):
        if chaos_knights_army.player_id == context.active_player_id:
            continue
        if DreadAbility.DISMAY not in active_dread_abilities_for_player(
            context.state,
            player_id=chaos_knights_army.player_id,
        ):
            continue
        for target_unit in active_army.units:
            if _unit_within_dread_aura(
                state=context.state,
                dread_army=chaos_knights_army,
                target_unit_instance_id=target_unit.unit_instance_id,
            ):
                forced_ids.add(target_unit.unit_instance_id)
    return tuple(sorted(forced_ids))


def resolve_harbingers_battle_shock_outcome(context: BattleShockOutcomeContext) -> None:
    if type(context) is not BattleShockOutcomeContext:
        raise GameLifecycleError("Harbingers of Dread Battle-shock outcome requires context.")
    result = context.result
    if result.passed:
        return
    target_unit = _unit_by_id(context.state, result.request.unit_instance_id)
    for chaos_knights_army in _chaos_knights_armies(context.state):
        if chaos_knights_army.player_id == result.request.player_id:
            continue
        if DreadAbility.DELIRIUM not in active_dread_abilities_for_player(
            context.state,
            player_id=chaos_knights_army.player_id,
        ):
            continue
        if not _unit_is_below_half_strength(
            context.state,
            player_id=result.request.player_id,
            unit=target_unit,
        ):
            continue
        if not _unit_within_dread_aura(
            state=context.state,
            dread_army=chaos_knights_army,
            target_unit_instance_id=target_unit.unit_instance_id,
        ):
            continue
        _apply_delirium_mortal_wounds(
            context=context,
            chaos_knights_player_id=chaos_knights_army.player_id,
            target_unit=target_unit,
        )


def _apply_delirium_mortal_wounds(
    *,
    context: BattleShockOutcomeContext,
    chaos_knights_player_id: str,
    target_unit: UnitInstance,
) -> None:
    d3_result = _roll_d3(
        context=context,
        reason="Delirium mortal wounds",
        roll_type=HARBINGERS_DELIRIUM_D3_ROLL_TYPE,
        actor_id=target_unit.unit_instance_id,
    )
    if _unit_has_feel_no_pain_choice(context.state, target_unit):
        context.decisions.event_log.append(
            "chaos_knights_delirium_unsupported",
            validate_json_value(
                {
                    "game_id": context.state.game_id,
                    "battle_round": context.state.battle_round,
                    "phase": context.phase.value,
                    "source_rule_id": SOURCE_RULE_ID,
                    "battle_shock_result_id": context.result.result_id,
                    "player_id": chaos_knights_player_id,
                    "target_unit_instance_id": target_unit.unit_instance_id,
                    "unsupported_reason": "mortal_wound_feel_no_pain_requires_decision",
                    "d3_result": d3_result.to_payload(),
                }
            ),
        )
        return
    application = apply_mortal_wounds_to_unit(
        state=context.state,
        target_unit_instance_id=target_unit.unit_instance_id,
        mortal_wounds=d3_result.value,
        spill_over=True,
        dice_manager=context.dice_manager,
        defender_player_id=context.result.request.player_id,
    )
    context.decisions.event_log.append(
        "chaos_knights_delirium_mortal_wounds_applied",
        validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": context.phase.value,
                "source_rule_id": SOURCE_RULE_ID,
                "battle_shock_result_id": context.result.result_id,
                "player_id": chaos_knights_player_id,
                "target_unit_instance_id": target_unit.unit_instance_id,
                "d3_result": d3_result.to_payload(),
                "mortal_wound_application": application.to_payload(),
            }
        ),
    )


def _selection_common_payload(
    *,
    state: GameState,
    player_id: str,
    target_unit_ids: tuple[str, ...],
    active: tuple[DreadAbility, ...],
    available: tuple[DreadAbility, ...],
) -> dict[str, JsonValue]:
    return {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "phase": BattlePhase.COMMAND.value,
        "player_id": player_id,
        "faction_id": CHAOS_KNIGHTS_FACTION_ID,
        "source_rule_id": SOURCE_RULE_ID,
        "hook_id": HOOK_ID,
        "state_kind": HARBINGERS_STATE_KIND,
        "effect_kind": HARBINGERS_EFFECT_KIND,
        "selection_kind": HARBINGERS_SELECTION_KIND,
        "target_unit_instance_ids": list(target_unit_ids),
        "active_dread_ability_ids": [ability.value for ability in active],
        "available_dread_ability_ids": [ability.value for ability in available],
        "rules_update_sources": [DARKNESS_RULE_UPDATE_SOURCE],
    }


def _validate_request_matches_current_state(
    *,
    context: BattleRoundStartResultContext,
    army: ArmyDefinition,
) -> None:
    request_payload = _payload_object(context.request.payload)
    if _payload_string(request_payload, key="game_id") != context.state.game_id:
        raise GameLifecycleError("Harbingers of Dread request game_id drift.")
    if _payload_int(request_payload, key="battle_round") != context.state.battle_round:
        raise GameLifecycleError("Harbingers of Dread request battle_round drift.")
    if _payload_string(request_payload, key="player_id") != army.player_id:
        raise GameLifecycleError("Harbingers of Dread request player drift.")
    current_active = active_dread_abilities_for_player(context.state, player_id=army.player_id)
    current_available = _available_dread_abilities(current_active)
    if _payload_string_list(request_payload, key="active_dread_ability_ids") != tuple(
        ability.value for ability in current_active
    ):
        raise GameLifecycleError("Harbingers of Dread request active ability drift.")
    if _payload_string_list(request_payload, key="available_dread_ability_ids") != tuple(
        ability.value for ability in current_available
    ):
        raise GameLifecycleError("Harbingers of Dread request available ability drift.")
    current_targets = _eligible_harbingers_unit_ids_for_army(army)
    if _payload_string_list(request_payload, key="target_unit_instance_ids") != current_targets:
        raise GameLifecycleError("Harbingers of Dread request target unit drift.")


def _validate_manual_selection(
    *,
    selected: tuple[DreadAbility, ...],
    active: tuple[DreadAbility, ...],
) -> None:
    if len(selected) != 1:
        raise GameLifecycleError("Harbingers of Dread manual selection requires one ability.")
    ability = selected[0]
    if ability is DreadAbility.DEATHLY_TERROR:
        raise GameLifecycleError("Harbingers of Dread cannot select Deathly Terror.")
    if ability in active:
        raise GameLifecycleError("Harbingers of Dread ability is already active.")


def _harbingers_selection_state(
    *,
    context: BattleRoundStartResultContext,
    player_id: str,
    selected: tuple[DreadAbility, ...],
    selection_mode: str,
    dice_values: tuple[int, ...],
    roll_payload: JsonValue,
) -> FactionRuleState:
    return FactionRuleState(
        state_id=(f"{HOOK_ID}:{player_id}:round-{context.state.battle_round:02d}:selection"),
        player_id=player_id,
        faction_id=CHAOS_KNIGHTS_FACTION_ID,
        source_rule_id=SOURCE_RULE_ID,
        state_kind=HARBINGERS_STATE_KIND,
        setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
        request_id=context.request.request_id,
        result_id=context.result.result_id,
        payload=validate_json_value(
            {
                "selection_kind": HARBINGERS_SELECTION_KIND,
                "effect_kind": HARBINGERS_EFFECT_KIND,
                "selection_mode": selection_mode,
                "selected_option_id": context.result.selected_option_id,
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "player_id": player_id,
                "faction_id": CHAOS_KNIGHTS_FACTION_ID,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
                "selected_dread_ability_ids": [ability.value for ability in selected],
                "selected_dread_ability_labels": [
                    _DEFINITIONS_BY_DREAD[ability].label for ability in selected
                ],
                "dice_values": list(dice_values),
                "roll_state": roll_payload,
                "rules_update_sources": [DARKNESS_RULE_UPDATE_SOURCE],
            }
        ),
    )


def _dread_selection_states_for_player(
    state: GameState,
    *,
    player_id: str,
) -> tuple[FactionRuleState, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    states = tuple(
        state_record
        for state_record in state.faction_rule_states_for_player(
            player_id=requested_player_id,
            state_kind=HARBINGERS_STATE_KIND,
        )
        if state_record.source_rule_id == SOURCE_RULE_ID
    )
    seen_rounds: set[int] = set()
    for state_record in states:
        payload = _payload_object(state_record.payload)
        battle_round = _payload_int(payload, key="battle_round")
        if battle_round in seen_rounds:
            raise GameLifecycleError(
                "Harbingers of Dread lookup found duplicate battle-round states."
            )
        seen_rounds.add(battle_round)
    return tuple(
        sorted(
            states,
            key=lambda state_record: _payload_int(
                _payload_object(state_record.payload),
                key="battle_round",
            ),
        )
    )


def _selection_recorded_for_round(
    state: GameState,
    *,
    player_id: str,
    battle_round: int,
) -> bool:
    requested_round = _validate_positive_int("battle_round", battle_round)
    return any(
        _payload_int(_payload_object(state_record.payload), key="battle_round") == requested_round
        for state_record in _dread_selection_states_for_player(state, player_id=player_id)
    )


def _available_dread_abilities(active: tuple[DreadAbility, ...]) -> tuple[DreadAbility, ...]:
    active_set = {_dread_from_token(ability) for ability in active}
    return tuple(ability for ability in ROLLABLE_DREAD_ABILITIES if ability not in active_set)


def _dread_abilities_from_dice_values(
    dice_values: tuple[int, ...],
    *,
    active: tuple[DreadAbility, ...],
) -> tuple[DreadAbility, ...]:
    active_set = {_dread_from_token(ability) for ability in active}
    selected: list[DreadAbility] = []
    for value in dice_values:
        if type(value) is not int or not 1 <= value <= 6:
            raise GameLifecycleError("Harbingers of Dread roll values must be D6 results.")
        ability = _DREAD_BY_ROLL[value]
        if ability in active_set:
            continue
        if ability in selected:
            continue
        selected.append(ability)
    return tuple(selected)


def _unit_within_dread_aura(
    *,
    state: GameState,
    dread_army: ArmyDefinition,
    target_unit_instance_id: str,
) -> bool:
    target_models = _unit_geometry_models(state=state, unit_instance_id=target_unit_instance_id)
    if not target_models:
        return False
    aura_range = _dread_aura_range_for_player(state, player_id=dread_army.player_id)
    for source_unit in dread_army.units:
        if not _unit_has_harbingers(source_unit):
            continue
        for source_model in _unit_geometry_models(
            state=state,
            unit_instance_id=source_unit.unit_instance_id,
        ):
            if any(
                shapely_backend.base_footprint_distance(
                    source_model.base,
                    source_model.pose,
                    target_model.base,
                    target_model.pose,
                )
                <= aura_range
                for target_model in target_models
            ):
                return True
    return False


def _dread_aura_range_for_player(state: GameState, *, player_id: str) -> float:
    if DreadAbility.DOMINION in active_dread_abilities_for_player(state, player_id=player_id):
        return DREAD_AURA_RANGE_WITH_DOMINION_INCHES
    return DREAD_AURA_RANGE_INCHES


def _unit_geometry_models(
    *,
    state: GameState,
    unit_instance_id: str,
) -> tuple[GeometryModel, ...]:
    if state.battlefield_state is None:
        raise GameLifecycleError("Harbingers of Dread geometry lookup requires battlefield_state.")
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    try:
        unit_placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    except PlacementError:
        return ()
    return tuple(
        geometry_model_for_placement(
            model=scenario.model_instance_for_placement(model_placement),
            placement=model_placement,
        )
        for model_placement in unit_placement.model_placements
        if scenario.model_instance_for_placement(model_placement).is_alive
    )


def _unit_is_below_half_strength(
    state: GameState,
    *,
    player_id: str,
    unit: UnitInstance,
) -> bool:
    current_model_ids = _current_battlefield_model_ids(state=state, unit=unit)
    if not current_model_ids:
        return False
    context = BelowHalfStrengthContext.from_unit(
        player_id=player_id,
        unit=unit,
        starting_strength=_starting_strength_record(
            state=state,
            player_id=player_id,
            unit_instance_id=unit.unit_instance_id,
        ),
        current_model_ids=current_model_ids,
    )
    return context.is_below_half_strength


def _current_battlefield_model_ids(
    *,
    state: GameState,
    unit: UnitInstance,
) -> tuple[str, ...]:
    if state.battlefield_state is None:
        raise GameLifecycleError("Harbingers of Dread strength lookup requires battlefield_state.")
    try:
        placement = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    except PlacementError:
        return ()
    unit_model_by_id = {model.model_instance_id: model for model in unit.own_models}
    current_model_ids: list[str] = []
    for model_placement in placement.model_placements:
        model = unit_model_by_id.get(model_placement.model_instance_id)
        if model is None:
            raise GameLifecycleError("Battlefield unit placement contains unknown model.")
        if model.is_alive:
            current_model_ids.append(model.model_instance_id)
    return tuple(sorted(current_model_ids))


def _starting_strength_record(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
) -> StartingStrengthRecord:
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    matching = tuple(
        record
        for record in state.starting_strength_records
        if record.player_id == requested_player_id and record.unit_instance_id == requested_unit_id
    )
    if len(matching) != 1:
        raise GameLifecycleError("Harbingers of Dread requires one StartingStrengthRecord.")
    return matching[0]


def _roll_d3(
    *,
    context: BattleShockOutcomeContext,
    reason: str,
    roll_type: str,
    actor_id: str,
) -> D3RollResult:
    roll_state = context.dice_manager.roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason=reason,
            roll_type=roll_type,
            actor_id=actor_id,
        )
    )
    return D3RollResult.from_source_d6_result(roll_state.original_result)


def _unit_has_feel_no_pain_choice(state: GameState, unit: UnitInstance) -> bool:
    return any(
        state.feel_no_pain_sources_for_model(model_instance_id=model.model_instance_id)
        or state.feel_no_pain_decline_allowed_for_model(model_instance_id=model.model_instance_id)
        for model in unit.own_models
        if model.is_alive
    )


def _eligible_harbingers_unit_ids_for_army(army: ArmyDefinition) -> tuple[str, ...]:
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError("Harbingers of Dread requires an ArmyDefinition.")
    return tuple(unit.unit_instance_id for unit in army.units if _unit_has_harbingers(unit))


def _unit_has_harbingers(unit: UnitInstance) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Harbingers of Dread requires a UnitInstance.")
    if _unit_has_keyword(unit, CHAOS_KNIGHTS_FACTION_KEYWORD):
        return True
    return any(
        _canonical_keyword(ability.name) == _canonical_keyword("Harbingers of Dread")
        for ability in unit.datasheet_abilities
    )


def _unit_by_id(state: GameState, unit_instance_id: str) -> UnitInstance:
    unit, _army = _unit_and_army_by_id(state, unit_instance_id=unit_instance_id)
    return unit


def _unit_and_army_by_id(
    state: GameState,
    *,
    unit_instance_id: str,
) -> tuple[UnitInstance, ArmyDefinition]:
    _validate_game_state(state)
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return unit, army
    raise GameLifecycleError("Harbingers of Dread unit_instance_id was not found.")


def _chaos_knights_armies(state: GameState) -> tuple[ArmyDefinition, ...]:
    _validate_game_state(state)
    return tuple(
        army
        for army in state.army_definitions
        if army.detachment_selection.faction_id == CHAOS_KNIGHTS_FACTION_ID
    )


def _chaos_knights_army_for_player(
    state: GameState,
    *,
    player_id: str,
) -> ArmyDefinition | None:
    requested_player_id = _validate_identifier("player_id", player_id)
    for army in _chaos_knights_armies(state):
        if army.player_id == requested_player_id:
            return army
    return None


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    requested_keyword = _canonical_keyword(keyword)
    return any(
        _canonical_keyword(stored_keyword) == requested_keyword
        for stored_keyword in (*unit.keywords, *unit.faction_keywords)
    )


def _dread_from_token(token: object) -> DreadAbility:
    if type(token) is DreadAbility:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Dread ability token must be a string.")
    try:
        return DreadAbility(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported Dread ability: {token}.") from exc


def _payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Harbingers of Dread payload must be an object.")
    return payload


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    value = payload.get(key)
    return _validate_identifier(key, value)


def _payload_string_list(payload: dict[str, JsonValue], *, key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise GameLifecycleError(f"Harbingers of Dread payload {key} must be a list.")
    strings: list[str] = []
    for item in value:
        if type(item) is not str or not item.strip():
            raise GameLifecycleError(f"Harbingers of Dread payload {key} must contain strings.")
        strings.append(item)
    return tuple(strings)


def _payload_int(payload: dict[str, JsonValue], *, key: str) -> int:
    value = payload.get(key)
    return _validate_positive_int(key, value)


def _validate_game_state(state: object) -> None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Harbingers of Dread requires GameState.")


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Harbingers of Dread {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Harbingers of Dread {field_name} must not be empty.")
    return stripped


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"Harbingers of Dread {field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"Harbingers of Dread {field_name} must be positive.")
    return value


def _canonical_keyword(value: str) -> str:
    return _validate_identifier("keyword", value).replace("_", " ").replace("-", " ").upper()
