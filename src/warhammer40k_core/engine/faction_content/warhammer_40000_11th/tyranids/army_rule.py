from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.core.weapon_profiles import RangeProfileKind, WeaponProfile
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battle_shock import (
    BattleShockResult,
    BattleShockTestReason,
    BattleShockTestRequest,
    battle_shock_leadership_target_for_unit,
)
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockDiceExpressionContext,
    BattleShockHookBinding,
    BattleShockModifierContext,
    BattleShockOutcomeContext,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    PlacementError,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.command_phase_start_hooks import (
    SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
    CommandPhaseStartHookBinding,
    CommandPhaseStartRequestContext,
    CommandPhaseStartResultContext,
)
from warhammer40k_core.engine.decision_request import DecisionError, DecisionOption, DecisionRequest
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.faction_rule_states import FactionRuleState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, SetupStep
from warhammer40k_core.engine.runtime_modifiers import (
    WeaponProfileModifierBinding,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext, StartingStrengthRecord
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.volume import Model as GeometryModel

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

CONTRIBUTION_ID = "warhammer_40000_11th:tyranids:army_rule:shadow_in_the_warp"
HOOK_ID = "warhammer_40000_11th:tyranids:army_rule:shadow_in_the_warp"
BATTLE_SHOCK_HOOK_ID = f"{HOOK_ID}:battle-shock"
WEAPON_PROFILE_MODIFIER_ID = f"{HOOK_ID}:synapse:weapon-profile"
SOURCE_RULE_ID = "phase17f:phase17e:tyranids:army-rule"
TYRANIDS_FACTION_ID = "tyranids"
TYRANIDS_FACTION_KEYWORD = "TYRANIDS"
SYNAPSE_KEYWORD = "SYNAPSE"
SYNAPSE_RANGE_INCHES = 6.0
SHADOW_STATE_KIND = "tyranids_shadow_in_the_warp_unleashed"
SHADOW_DECLINE_STATE_KIND = "tyranids_shadow_in_the_warp_declined_command_phase"
SHADOW_EFFECT_KIND = "tyranids_shadow_in_the_warp"
SHADOW_SELECTION_KIND = "tyranids_shadow_in_the_warp"
SHADOW_UNLEASH_OPTION_ID = "tyranids:shadow_in_the_warp:unleash"
SHADOW_DECLINE_OPTION_ID = "tyranids:shadow_in_the_warp:decline"
RULE_UPDATE_SOURCE = (
    "warhammer_40000_11th:tyranids:faction_pack:rules_updates:shadow_in_the_warp_synapse"
)


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        command_phase_start_hook_bindings=(
            CommandPhaseStartHookBinding(
                hook_id=HOOK_ID,
                source_id=SOURCE_RULE_ID,
                request_handler=shadow_in_the_warp_request,
                result_handler=apply_shadow_in_the_warp_result,
            ),
        ),
        battle_shock_hook_bindings=(
            BattleShockHookBinding(
                hook_id=BATTLE_SHOCK_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                dice_expression_handler=synapse_battle_shock_dice_expression,
                modifier_handler=shadow_in_the_warp_battle_shock_modifiers,
            ),
        ),
        weapon_profile_modifier_bindings=(
            WeaponProfileModifierBinding(
                modifier_id=WEAPON_PROFILE_MODIFIER_ID,
                source_id=SOURCE_RULE_ID,
                handler=synapse_weapon_profile_modifier,
            ),
        ),
    )


def shadow_in_the_warp_request(
    context: CommandPhaseStartRequestContext,
) -> DecisionRequest | None:
    if type(context) is not CommandPhaseStartRequestContext:
        raise GameLifecycleError("Shadow in the Warp requires request context.")
    for army in _tyranids_armies(context.state):
        if shadow_in_the_warp_unleashed_for_player(context.state, player_id=army.player_id):
            continue
        if _shadow_declined_this_command_phase(context.state, player_id=army.player_id):
            continue
        source_unit_ids = _eligible_shadow_source_unit_ids(
            state=context.state,
            army=army,
        )
        if not source_unit_ids:
            continue
        target_unit_ids = _enemy_unit_ids_on_battlefield(context.state, tyranids_army=army)
        if not target_unit_ids:
            continue
        common_payload = _shadow_common_payload(
            state=context.state,
            active_player_id=context.active_player_id,
            player_id=army.player_id,
            source_unit_ids=source_unit_ids,
            target_unit_ids=target_unit_ids,
        )
        return DecisionRequest(
            request_id=context.state.next_decision_request_id(),
            decision_type=SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
            actor_id=army.player_id,
            payload=validate_json_value(common_payload),
            options=(
                DecisionOption(
                    option_id=SHADOW_UNLEASH_OPTION_ID,
                    label="Unleash Shadow in the Warp",
                    payload=validate_json_value(
                        {
                            **common_payload,
                            "submission_kind": SHADOW_SELECTION_KIND,
                            "selected_shadow_option": "unleash",
                        }
                    ),
                ),
                DecisionOption(
                    option_id=SHADOW_DECLINE_OPTION_ID,
                    label="Do not unleash Shadow in the Warp",
                    payload=validate_json_value(
                        {
                            **common_payload,
                            "submission_kind": SHADOW_SELECTION_KIND,
                            "selected_shadow_option": "decline",
                        }
                    ),
                ),
            ),
        )
    return None


def apply_shadow_in_the_warp_result(context: CommandPhaseStartResultContext) -> bool:
    if type(context) is not CommandPhaseStartResultContext:
        raise GameLifecycleError("Shadow in the Warp requires result context.")
    if (
        context.request.decision_type
        != SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE
    ):
        return False
    request_payload = _payload_object(context.request.payload)
    if request_payload.get("hook_id") != HOOK_ID:
        return False
    if context.result.actor_id is None:
        raise GameLifecycleError("Shadow in the Warp requires an actor.")
    player_id = context.result.actor_id
    army = _tyranids_army_for_player(context.state, player_id=player_id)
    if army is None:
        raise GameLifecycleError("Shadow in the Warp actor does not own Tyranids.")
    if shadow_in_the_warp_unleashed_for_player(context.state, player_id=player_id):
        raise GameLifecycleError("Shadow in the Warp has already been unleashed this battle.")
    if _shadow_declined_this_command_phase(context.state, player_id=player_id):
        raise GameLifecycleError("Shadow in the Warp has already been declined this Command phase.")
    _validate_shadow_request_matches_current_state(context=context, army=army)
    try:
        expected_option = context.request.option_by_id(context.result.selected_option_id)
    except DecisionError as exc:
        raise GameLifecycleError("Shadow in the Warp selected option is not available.") from exc
    if context.result.payload != expected_option.payload:
        raise GameLifecycleError("Shadow in the Warp selected option payload drift.")

    payload = _payload_object(context.result.payload)
    selection = _payload_string(payload, key="selected_shadow_option")
    if selection == "decline":
        _record_shadow_decline(context, player_id=player_id)
        return True
    if selection != "unleash":
        raise GameLifecycleError("Shadow in the Warp selection is unsupported.")
    if context.result.selected_option_id != SHADOW_UNLEASH_OPTION_ID:
        raise GameLifecycleError("Shadow in the Warp unleash option ID drift.")

    source_unit_ids = _payload_string_list(payload, key="source_unit_instance_ids")
    target_unit_ids = _payload_string_list(payload, key="target_enemy_unit_instance_ids")
    state_record = _shadow_unleashed_state(
        context=context,
        player_id=player_id,
        source_unit_ids=source_unit_ids,
        target_unit_ids=target_unit_ids,
    )
    context.state.record_faction_rule_state(state_record)
    battle_shock_results = _resolve_shadow_battle_shock_tests(
        context=context,
        tyranids_army=army,
        target_unit_ids=target_unit_ids,
        source_state=state_record,
    )
    context.decisions.event_log.append(
        "tyranids_shadow_in_the_warp_unleashed",
        validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "active_player_id": context.active_player_id,
                "player_id": player_id,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
                "source_unit_instance_ids": list(source_unit_ids),
                "target_enemy_unit_instance_ids": list(target_unit_ids),
                "battle_shock_result_ids": [result.result_id for result in battle_shock_results],
                "faction_rule_state": state_record.to_payload(),
            }
        ),
    )
    return True


def shadow_in_the_warp_unleashed_for_player(state: GameState, *, player_id: str) -> bool:
    _validate_game_state(state)
    requested_player_id = _validate_identifier("player_id", player_id)
    states = tuple(
        state_record
        for state_record in state.faction_rule_states_for_player(
            player_id=requested_player_id,
            state_kind=SHADOW_STATE_KIND,
        )
        if state_record.source_rule_id == SOURCE_RULE_ID
    )
    if len(states) > 1:
        raise GameLifecycleError("Shadow in the Warp lookup found multiple unleashed states.")
    return bool(states)


def synapse_battle_shock_dice_expression(
    context: BattleShockDiceExpressionContext,
) -> DiceExpression | None:
    if type(context) is not BattleShockDiceExpressionContext:
        raise GameLifecycleError("Synapse Battle-shock dice expression requires context.")
    unit, army = _unit_and_army_by_id(context.state, unit_instance_id=context.unit_instance_id)
    if army.player_id != context.player_id:
        raise GameLifecycleError("Synapse Battle-shock dice expression player drift.")
    if army.detachment_selection.faction_id != TYRANIDS_FACTION_ID:
        return None
    if not _unit_has_faction_keyword(unit, TYRANIDS_FACTION_KEYWORD):
        return None
    if not tyranids_unit_within_synapse_range(
        context.state,
        tyranids_army=army,
        unit_instance_id=unit.unit_instance_id,
    ):
        return None
    return DiceExpression(quantity=3, sides=6)


def shadow_in_the_warp_battle_shock_modifiers(
    context: BattleShockModifierContext,
) -> tuple[RollModifier, ...]:
    if type(context) is not BattleShockModifierContext:
        raise GameLifecycleError("Shadow in the Warp Battle-shock modifiers require context.")
    modifiers: list[RollModifier] = []
    for tyranids_army in _tyranids_armies(context.state):
        if not context.request.request_id.startswith(
            _shadow_request_prefix(
                battle_round=context.request.battle_round,
                tyranids_player_id=tyranids_army.player_id,
            )
        ):
            continue
        _target_unit, target_army = _unit_and_army_by_id(
            context.state,
            unit_instance_id=context.request.unit_instance_id,
        )
        if target_army.player_id == tyranids_army.player_id:
            raise GameLifecycleError("Shadow in the Warp target unit owner drift.")
        if not tyranids_unit_within_synapse_range(
            context.state,
            tyranids_army=tyranids_army,
            unit_instance_id=context.request.unit_instance_id,
        ):
            continue
        modifiers.append(
            RollModifier(
                modifier_id=(
                    f"{BATTLE_SHOCK_HOOK_ID}:shadow-penalty:"
                    f"{context.request.request_id}:{tyranids_army.player_id}"
                ),
                source_id=SOURCE_RULE_ID,
                operand=-1,
            )
        )
    return tuple(modifiers)


def synapse_weapon_profile_modifier(context: WeaponProfileModifierContext) -> WeaponProfile:
    if type(context) is not WeaponProfileModifierContext:
        raise GameLifecycleError("Synapse weapon profile modifier requires context.")
    if context.source_phase is not BattlePhase.FIGHT:
        return context.weapon_profile
    if context.weapon_profile.range_profile.kind is not RangeProfileKind.MELEE:
        return context.weapon_profile
    attacking_unit, attacking_army = _unit_and_army_by_id(
        context.state,
        unit_instance_id=context.attacking_unit_instance_id,
    )
    if attacking_army.detachment_selection.faction_id != TYRANIDS_FACTION_ID:
        return context.weapon_profile
    if not _unit_has_faction_keyword(attacking_unit, TYRANIDS_FACTION_KEYWORD):
        return context.weapon_profile
    if not tyranids_unit_within_synapse_range(
        context.state,
        tyranids_army=attacking_army,
        unit_instance_id=attacking_unit.unit_instance_id,
    ):
        return context.weapon_profile
    return replace(
        context.weapon_profile,
        strength=_strength_with_plus_one(context.weapon_profile.strength),
        source_ids=_source_ids_with_synapse(context.weapon_profile.source_ids),
    )


def tyranids_unit_within_synapse_range(
    state: GameState,
    *,
    tyranids_army: ArmyDefinition,
    unit_instance_id: str,
) -> bool:
    _validate_game_state(state)
    if type(tyranids_army) is not ArmyDefinition:
        raise GameLifecycleError("Synapse range requires an ArmyDefinition.")
    if tyranids_army.detachment_selection.faction_id != TYRANIDS_FACTION_ID:
        return False
    target_models = _unit_geometry_models(state=state, unit_instance_id=unit_instance_id)
    if not target_models:
        return False
    synapse_models = _synapse_geometry_models(state=state, tyranids_army=tyranids_army)
    return any(
        shapely_backend.base_footprint_distance(
            source_model.base,
            source_model.pose,
            target_model.base,
            target_model.pose,
        )
        <= SYNAPSE_RANGE_INCHES
        for source_model in synapse_models
        for target_model in target_models
    )


def _resolve_shadow_battle_shock_tests(
    *,
    context: CommandPhaseStartResultContext,
    tyranids_army: ArmyDefinition,
    target_unit_ids: tuple[str, ...],
    source_state: FactionRuleState,
) -> tuple[BattleShockResult, ...]:
    manager = DiceRollManager(context.state.game_id, event_log=context.decisions.event_log)
    phase_start_battle_shocked_unit_ids = tuple(context.state.battle_shocked_unit_ids)
    results: list[BattleShockResult] = []
    for target_unit_id in target_unit_ids:
        target_unit, target_army = _unit_and_army_by_id(
            context.state,
            unit_instance_id=target_unit_id,
        )
        if target_army.player_id == tyranids_army.player_id:
            raise GameLifecycleError("Shadow in the Warp target unit owner drift.")
        current_model_ids = _current_battlefield_model_ids(context.state, unit=target_unit)
        if not current_model_ids:
            raise GameLifecycleError("Shadow in the Warp target unit is not on the battlefield.")
        below_half_context = BelowHalfStrengthContext.from_unit(
            player_id=target_army.player_id,
            unit=target_unit,
            starting_strength=_starting_strength_record(
                state=context.state,
                player_id=target_army.player_id,
                unit_instance_id=target_unit.unit_instance_id,
            ),
            current_model_ids=current_model_ids,
        )
        dice_expression = context.battle_shock_hooks.dice_expression_for(
            BattleShockDiceExpressionContext(
                state=context.state,
                player_id=target_army.player_id,
                unit_instance_id=target_unit.unit_instance_id,
                reason=BattleShockTestReason.FORCED_BY_ARMY_RULE,
                active_player_id=context.active_player_id,
                phase=BattlePhase.COMMAND,
                default_expression=DiceExpression(quantity=2, sides=6),
                phase_start_battle_shocked_unit_ids=phase_start_battle_shocked_unit_ids,
            )
        )
        request = BattleShockTestRequest.for_unit(
            request_id=(
                f"{
                    _shadow_request_prefix(
                        battle_round=context.state.battle_round,
                        tyranids_player_id=tyranids_army.player_id,
                    )
                }{target_unit.unit_instance_id}"
            ),
            game_id=context.state.game_id,
            battle_round=context.state.battle_round,
            player_id=target_army.player_id,
            unit_instance_id=target_unit.unit_instance_id,
            reason=BattleShockTestReason.FORCED_BY_ARMY_RULE,
            leadership_target=battle_shock_leadership_target_for_unit(
                target_unit,
                current_model_ids=current_model_ids,
                ability_index=_ability_index_for_player(
                    context.ability_indexes_by_player_id,
                    player_id=target_army.player_id,
                ),
                state=context.state,
                runtime_modifier_registry=context.runtime_modifier_registry,
            ),
            below_half_strength_context=below_half_context,
            dice_expression=dice_expression,
        )
        context.decisions.event_log.append(
            "battle_shock_test_requested",
            validate_json_value(
                {
                    "game_id": context.state.game_id,
                    "battle_round": context.state.battle_round,
                    "active_player_id": context.active_player_id,
                    "phase": BattlePhase.COMMAND.value,
                    "battle_shock_test_request": request.to_payload(),
                    "source_faction_rule_state": source_state.to_payload(),
                }
            ),
        )
        roll_state = manager.roll(request.spec)
        result = BattleShockResult.from_roll_state(
            result_id=f"{request.request_id}:result",
            request=request,
            roll_state=roll_state,
            modifiers=context.battle_shock_hooks.modifiers_for(
                BattleShockModifierContext(
                    state=context.state,
                    request=request,
                    active_player_id=context.active_player_id,
                    phase=BattlePhase.COMMAND,
                    phase_start_battle_shocked_unit_ids=phase_start_battle_shocked_unit_ids,
                )
            ),
        )
        context.state.record_battle_shock_result(result)
        context.decisions.event_log.append(
            "battle_shock_test_resolved",
            validate_json_value(
                {
                    "game_id": context.state.game_id,
                    "battle_round": context.state.battle_round,
                    "active_player_id": context.active_player_id,
                    "phase": BattlePhase.COMMAND.value,
                    "battle_shock_result": result.to_payload(),
                    "auto_passed": False,
                    "source_faction_rule_state": source_state.to_payload(),
                }
            ),
        )
        context.battle_shock_hooks.resolve_outcomes(
            BattleShockOutcomeContext(
                state=context.state,
                decisions=context.decisions,
                dice_manager=manager,
                result=result,
                active_player_id=context.active_player_id,
                phase=BattlePhase.COMMAND,
                auto_passed=False,
                phase_start_battle_shocked_unit_ids=phase_start_battle_shocked_unit_ids,
            )
        )
        results.append(result)
    return tuple(results)


def _record_shadow_decline(
    context: CommandPhaseStartResultContext,
    *,
    player_id: str,
) -> None:
    if context.result.selected_option_id != SHADOW_DECLINE_OPTION_ID:
        raise GameLifecycleError("Shadow in the Warp decline option ID drift.")
    state_record = FactionRuleState(
        state_id=(
            f"{HOOK_ID}:{player_id}:round-{context.state.battle_round:02d}:"
            f"active-{context.active_player_id}:declined"
        ),
        player_id=player_id,
        faction_id=TYRANIDS_FACTION_ID,
        source_rule_id=SOURCE_RULE_ID,
        state_kind=SHADOW_DECLINE_STATE_KIND,
        setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
        request_id=context.request.request_id,
        result_id=context.result.result_id,
        payload=validate_json_value(
            {
                "selection_kind": SHADOW_SELECTION_KIND,
                "effect_kind": SHADOW_EFFECT_KIND,
                "selected_shadow_option": "decline",
                "selected_option_id": context.result.selected_option_id,
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "active_player_id": context.active_player_id,
                "player_id": player_id,
                "faction_id": TYRANIDS_FACTION_ID,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
            }
        ),
    )
    context.state.record_faction_rule_state(state_record)
    context.decisions.event_log.append(
        "tyranids_shadow_in_the_warp_declined",
        validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "active_player_id": context.active_player_id,
                "player_id": player_id,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
                "faction_rule_state": state_record.to_payload(),
            }
        ),
    )


def _shadow_unleashed_state(
    *,
    context: CommandPhaseStartResultContext,
    player_id: str,
    source_unit_ids: tuple[str, ...],
    target_unit_ids: tuple[str, ...],
) -> FactionRuleState:
    return FactionRuleState(
        state_id=f"{HOOK_ID}:{player_id}:unleashed",
        player_id=player_id,
        faction_id=TYRANIDS_FACTION_ID,
        source_rule_id=SOURCE_RULE_ID,
        state_kind=SHADOW_STATE_KIND,
        setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
        request_id=context.request.request_id,
        result_id=context.result.result_id,
        payload=validate_json_value(
            {
                "selection_kind": SHADOW_SELECTION_KIND,
                "effect_kind": SHADOW_EFFECT_KIND,
                "selected_shadow_option": "unleash",
                "selected_option_id": context.result.selected_option_id,
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "active_player_id": context.active_player_id,
                "player_id": player_id,
                "faction_id": TYRANIDS_FACTION_ID,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
                "source_unit_instance_ids": list(source_unit_ids),
                "target_enemy_unit_instance_ids": list(target_unit_ids),
                "rules_update_source": RULE_UPDATE_SOURCE,
            }
        ),
    )


def _shadow_common_payload(
    *,
    state: GameState,
    active_player_id: str,
    player_id: str,
    source_unit_ids: tuple[str, ...],
    target_unit_ids: tuple[str, ...],
) -> dict[str, JsonValue]:
    return {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "phase": BattlePhase.COMMAND.value,
        "active_player_id": active_player_id,
        "actor_may_be_non_active": True,
        "player_id": player_id,
        "faction_id": TYRANIDS_FACTION_ID,
        "source_rule_id": SOURCE_RULE_ID,
        "hook_id": HOOK_ID,
        "selection_kind": SHADOW_SELECTION_KIND,
        "effect_kind": SHADOW_EFFECT_KIND,
        "source_unit_instance_ids": list(source_unit_ids),
        "target_enemy_unit_instance_ids": list(target_unit_ids),
        "rules_update_source": RULE_UPDATE_SOURCE,
    }


def _validate_shadow_request_matches_current_state(
    *,
    context: CommandPhaseStartResultContext,
    army: ArmyDefinition,
) -> None:
    request_payload = _payload_object(context.request.payload)
    if _payload_string(request_payload, key="game_id") != context.state.game_id:
        raise GameLifecycleError("Shadow in the Warp request game_id drift.")
    if _payload_int(request_payload, key="battle_round") != context.state.battle_round:
        raise GameLifecycleError("Shadow in the Warp request battle_round drift.")
    if _payload_string(request_payload, key="phase") != BattlePhase.COMMAND.value:
        raise GameLifecycleError("Shadow in the Warp request phase drift.")
    if _payload_string(request_payload, key="active_player_id") != context.active_player_id:
        raise GameLifecycleError("Shadow in the Warp request active player drift.")
    if _payload_string(request_payload, key="player_id") != army.player_id:
        raise GameLifecycleError("Shadow in the Warp request player drift.")
    if _payload_string_list(
        request_payload,
        key="source_unit_instance_ids",
    ) != _eligible_shadow_source_unit_ids(state=context.state, army=army):
        raise GameLifecycleError("Shadow in the Warp request source unit drift.")
    if _payload_string_list(
        request_payload,
        key="target_enemy_unit_instance_ids",
    ) != _enemy_unit_ids_on_battlefield(context.state, tyranids_army=army):
        raise GameLifecycleError("Shadow in the Warp request target unit drift.")


def _shadow_declined_this_command_phase(state: GameState, *, player_id: str) -> bool:
    requested_player_id = _validate_identifier("player_id", player_id)
    states = tuple(
        state_record
        for state_record in state.faction_rule_states_for_player(
            player_id=requested_player_id,
            state_kind=SHADOW_DECLINE_STATE_KIND,
        )
        if _decline_state_matches_current_command_phase(state, state_record)
    )
    if len(states) > 1:
        raise GameLifecycleError("Shadow in the Warp lookup found multiple decline states.")
    return bool(states)


def _decline_state_matches_current_command_phase(
    state: GameState,
    state_record: FactionRuleState,
) -> bool:
    payload = _payload_object(state_record.payload)
    return (
        state_record.source_rule_id == SOURCE_RULE_ID
        and payload.get("battle_round") == state.battle_round
        and payload.get("phase") == BattlePhase.COMMAND.value
        and payload.get("active_player_id") == state.active_player_id
        and payload.get("selected_shadow_option") == "decline"
    )


def _eligible_shadow_source_unit_ids(
    *,
    state: GameState,
    army: ArmyDefinition,
) -> tuple[str, ...]:
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError("Shadow in the Warp requires an ArmyDefinition.")
    return tuple(
        unit.unit_instance_id
        for unit in army.units
        if _unit_has_shadow_in_the_warp(unit) and _current_battlefield_model_ids(state, unit=unit)
    )


def _enemy_unit_ids_on_battlefield(
    state: GameState,
    *,
    tyranids_army: ArmyDefinition,
) -> tuple[str, ...]:
    enemy_ids: list[str] = []
    for army in state.army_definitions:
        if army.player_id == tyranids_army.player_id:
            continue
        for unit in army.units:
            if _current_battlefield_model_ids(state, unit=unit):
                enemy_ids.append(unit.unit_instance_id)
    return tuple(sorted(enemy_ids))


def _synapse_geometry_models(
    *,
    state: GameState,
    tyranids_army: ArmyDefinition,
) -> tuple[GeometryModel, ...]:
    models: list[GeometryModel] = []
    for source_unit in tyranids_army.units:
        if not _unit_has_synapse(source_unit):
            continue
        models.extend(
            _unit_geometry_models(
                state=state,
                unit_instance_id=source_unit.unit_instance_id,
            )
        )
    return tuple(models)


def _unit_geometry_models(
    *,
    state: GameState,
    unit_instance_id: str,
) -> tuple[GeometryModel, ...]:
    if state.battlefield_state is None:
        raise GameLifecycleError("Synapse geometry lookup requires battlefield_state.")
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


def _current_battlefield_model_ids(
    state: GameState,
    *,
    unit: UnitInstance,
) -> tuple[str, ...]:
    if state.battlefield_state is None:
        raise GameLifecycleError("Battlefield model lookup requires battlefield_state.")
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
        raise GameLifecycleError("Battle-shock test requires one StartingStrengthRecord.")
    return matching[0]


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
    raise GameLifecycleError("Tyranids army rule unit_instance_id was not found.")


def _tyranids_armies(state: GameState) -> tuple[ArmyDefinition, ...]:
    _validate_game_state(state)
    return tuple(
        army
        for army in state.army_definitions
        if army.detachment_selection.faction_id == TYRANIDS_FACTION_ID
    )


def _tyranids_army_for_player(state: GameState, *, player_id: str) -> ArmyDefinition | None:
    requested_player_id = _validate_identifier("player_id", player_id)
    for army in _tyranids_armies(state):
        if army.player_id == requested_player_id:
            return army
    return None


def _unit_has_shadow_in_the_warp(unit: UnitInstance) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Shadow in the Warp requires a UnitInstance.")
    if _unit_has_faction_keyword(unit, TYRANIDS_FACTION_KEYWORD):
        return True
    return any(
        _canonical_keyword(ability.name) == _canonical_keyword("Shadow in the Warp")
        for ability in unit.datasheet_abilities
    )


def _unit_has_synapse(unit: UnitInstance) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Synapse requires a UnitInstance.")
    return _unit_has_keyword(unit, SYNAPSE_KEYWORD) or any(
        _canonical_keyword(ability.name) == _canonical_keyword("Synapse")
        for ability in unit.datasheet_abilities
    )


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    canonical = _canonical_keyword(keyword)
    return any(
        _canonical_keyword(stored_keyword) == canonical
        for stored_keyword in (*unit.keywords, *unit.faction_keywords)
    )


def _unit_has_faction_keyword(unit: UnitInstance, keyword: str) -> bool:
    canonical = _canonical_keyword(keyword)
    return any(
        _canonical_keyword(stored_keyword) == canonical for stored_keyword in unit.faction_keywords
    )


def _strength_with_plus_one(strength: CharacteristicValue) -> CharacteristicValue:
    if type(strength) is not CharacteristicValue:
        raise GameLifecycleError("Synapse strength requires CharacteristicValue.")
    if strength.characteristic is not Characteristic.STRENGTH:
        raise GameLifecycleError("Synapse strength characteristic drift.")
    if not strength.is_numeric:
        raise GameLifecycleError("Synapse cannot modify non-numeric Strength.")
    return CharacteristicValue.from_raw(Characteristic.STRENGTH, strength.final + 1)


def _source_ids_with_synapse(source_ids: tuple[str, ...]) -> tuple[str, ...]:
    if type(source_ids) is not tuple:
        raise GameLifecycleError("Synapse source IDs must be a tuple.")
    if SOURCE_RULE_ID in source_ids:
        return source_ids
    return (*source_ids, SOURCE_RULE_ID)


def _ability_index_for_player(
    indexes: object,
    *,
    player_id: str,
) -> AbilityCatalogIndex:
    requested_player_id = _validate_identifier("player_id", player_id)
    if not isinstance(indexes, Mapping):
        raise GameLifecycleError("Synapse ability index lookup requires a mapping.")
    mapped_indexes = cast(Mapping[str, AbilityCatalogIndex], indexes)
    index = mapped_indexes.get(requested_player_id)
    if index is None:
        return AbilityCatalogIndex.from_records(())
    if type(index) is not AbilityCatalogIndex:
        raise GameLifecycleError("Synapse ability index lookup found an invalid index.")
    return index


def _shadow_request_prefix(*, battle_round: int, tyranids_player_id: str) -> str:
    requested_round = _validate_positive_int("battle_round", battle_round)
    requested_player_id = _validate_identifier("tyranids_player_id", tyranids_player_id)
    return f"{HOOK_ID}:shadow:{requested_player_id}:round-{requested_round:02d}:"


def _payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Tyranids army rule payload must be an object.")
    return payload


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    value = payload.get(key)
    return _validate_identifier(key, value)


def _payload_string_list(payload: dict[str, JsonValue], *, key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise GameLifecycleError(f"Tyranids army rule payload {key} must be a list.")
    strings: list[str] = []
    for item in value:
        strings.append(_validate_identifier(f"{key} value", item))
    return tuple(strings)


def _payload_int(payload: dict[str, JsonValue], *, key: str) -> int:
    value = payload.get(key)
    return _validate_positive_int(key, value)


def _validate_game_state(state: object) -> None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Tyranids army rule requires GameState.")


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Tyranids army rule {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Tyranids army rule {field_name} must not be empty.")
    return stripped


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"Tyranids army rule {field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"Tyranids army rule {field_name} must be positive.")
    return value


def _canonical_keyword(value: str) -> str:
    return _validate_identifier("keyword", value).replace("_", " ").replace("-", " ").upper()
