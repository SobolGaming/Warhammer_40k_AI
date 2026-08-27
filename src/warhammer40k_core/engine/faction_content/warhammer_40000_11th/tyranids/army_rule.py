from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import RangeProfileKind, WeaponProfile
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battle_shock import (
    BattleShockResult,
    BattleShockResultPayload,
    BattleShockTestReason,
)
from warhammer40k_core.engine.battle_shock_historical_authority import (
    HistoricalBattleShockAuthorityContext,
)
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockDiceExpressionContext,
    BattleShockHookBinding,
    BattleShockModifierApplicationAuthorityContext,
    BattleShockModifierContext,
    BattleShockPendingOutcomeAuthorityContext,
    HistoricalBattleShockContribution,
    battle_shock_modifier_applications_from_modifiers,
)
from warhammer40k_core.engine.battle_shock_resolution import BattleShockPassedStatePolicy
from warhammer40k_core.engine.battle_shock_resolution_authority import (
    PendingBattleShockRerollAuthority,
    parse_pending_battle_shock_reroll_authority,
)
from warhammer40k_core.engine.battle_shock_test_service import (
    BattleShockTestRuntime,
    resolve_battle_shock_test,
)
from warhammer40k_core.engine.command_phase_start_hooks import (
    COMMAND_PHASE_START_BATTLE_SHOCK_SOURCE_KIND,
    SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
    CommandPhaseStartCompletedBattleShockAuthorityContext,
    CommandPhaseStartHookBinding,
    CommandPhaseStartNestedPendingAuthorityContext,
    CommandPhaseStartNestedResultContext,
    CommandPhaseStartRequestContext,
    CommandPhaseStartResultContext,
)
from warhammer40k_core.engine.decision import DICE_REROLL_DECISION_TYPE
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionError, DecisionOption, DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.faction_content.common import (
    payload_identifier,
    payload_identifier_tuple,
    payload_object,
)
from warhammer40k_core.engine.faction_rule_states import (
    FactionRuleState,
    FactionRuleStatePayload,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    LifecycleStatus,
    SetupStep,
)
from warhammer40k_core.engine.rules_unit_geometry import (
    placed_alive_geometry_models_for_component_unit,
    placed_alive_geometry_models_for_rules_unit,
)
from warhammer40k_core.engine.rules_units import (
    placed_alive_rules_unit_views,
    rules_unit_view_by_id,
)
from warhammer40k_core.engine.runtime_modifiers import (
    WeaponProfileModifierBinding,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.volume import Model as GeometryModel


def _payload_object(value: object) -> dict[str, JsonValue]:
    return payload_object(value)


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    return payload_identifier(payload, key)


def _payload_string_list(payload: dict[str, JsonValue], *, key: str) -> tuple[str, ...]:
    return payload_identifier_tuple(payload, key, field_name="payload")


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
                nested_result_handler=apply_shadow_in_the_warp_nested_result,
                nested_pending_authority_validator=(
                    validate_shadow_in_the_warp_nested_pending_authority
                ),
                completed_battle_shock_authority_validator=(
                    validate_completed_shadow_in_the_warp_battle_shock_authority
                ),
            ),
        ),
        battle_shock_hook_bindings=(
            BattleShockHookBinding(
                hook_id=BATTLE_SHOCK_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                dice_expression_handler=synapse_battle_shock_dice_expression,
                modifier_handler=shadow_in_the_warp_battle_shock_modifiers,
                modifier_application_validator=(
                    validate_shadow_in_the_warp_battle_shock_modifier_application
                ),
                historical_contribution_handler=historical_synapse_battle_shock_contribution,
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
    continue_shadow_in_the_warp_battle_shock_tests(
        state=context.state,
        decisions=context.decisions,
        active_player_id=context.active_player_id,
        source_state=state_record,
        runtime=BattleShockTestRuntime(
            ability_indexes_by_player_id=context.ability_indexes_by_player_id,
            runtime_modifier_registry=context.runtime_modifier_registry,
            battle_shock_hook_registry=context.battle_shock_hooks,
        ),
    )
    return True


def apply_shadow_in_the_warp_nested_result(
    context: CommandPhaseStartNestedResultContext,
) -> bool:
    if type(context) is not CommandPhaseStartNestedResultContext:
        raise GameLifecycleError("Shadow in the Warp requires nested result context.")
    source_state = _shadow_source_state_from_nested_request(
        context=context,
    )
    if source_state is None:
        return False
    continue_shadow_in_the_warp_battle_shock_tests(
        state=context.state,
        decisions=context.decisions,
        active_player_id=context.active_player_id,
        source_state=source_state,
        runtime=BattleShockTestRuntime(
            ability_indexes_by_player_id=context.ability_indexes_by_player_id,
            runtime_modifier_registry=context.runtime_modifier_registry,
            battle_shock_hook_registry=context.battle_shock_hooks,
        ),
    )
    return True


def validate_shadow_in_the_warp_nested_pending_authority(
    context: CommandPhaseStartNestedPendingAuthorityContext,
) -> bool:
    if type(context) is not CommandPhaseStartNestedPendingAuthorityContext:
        raise GameLifecycleError("Shadow in the Warp requires nested pending authority context.")
    source_state = _shadow_source_state_from_nested_request(context=context)
    if source_state is None:
        return False
    if context.request.decision_type != DICE_REROLL_DECISION_TYPE:
        return True
    authority = parse_pending_battle_shock_reroll_authority(context.request)
    next_request_id = _validate_shadow_continuation_prefix(
        state=context.state,
        decisions=context.decisions,
        active_player_id=context.active_player_id,
        source_state=source_state,
    )
    if next_request_id is None or authority.test_request.request_id != next_request_id:
        raise GameLifecycleError("Shadow in the Warp pending target order drifted.")
    return True


def validate_completed_shadow_in_the_warp_battle_shock_authority(
    context: CommandPhaseStartCompletedBattleShockAuthorityContext,
) -> None:
    if type(context) is not CommandPhaseStartCompletedBattleShockAuthorityContext:
        raise GameLifecycleError("Shadow in the Warp requires completed authority context.")
    historical = context.historical
    source_state = context.source_state
    record = context.source_decision_record
    request = context.request
    army = historical.army_for_player(source_state.player_id)
    source_unit_ids = tuple(
        unit.unit_instance_id
        for unit in army.units
        if _unit_has_shadow_in_the_warp(unit)
        and historical.component_placed_alive_model_ids(unit.unit_instance_id)
    )
    target_unit_ids = tuple(
        rules_unit.unit_instance_id
        for rules_unit in historical.all_rules_units()
        if rules_unit.owner_player_id != source_state.player_id
        and historical.placed_alive_model_ids(rules_unit.unit_instance_id)
    )
    common_payload = validate_json_value(
        {
            "game_id": historical.game_id,
            "battle_round": request.battle_round,
            "phase": BattlePhase.COMMAND.value,
            "active_player_id": historical.active_player_id,
            "actor_may_be_non_active": True,
            "player_id": source_state.player_id,
            "faction_id": TYRANIDS_FACTION_ID,
            "source_rule_id": SOURCE_RULE_ID,
            "hook_id": HOOK_ID,
            "selection_kind": SHADOW_SELECTION_KIND,
            "effect_kind": SHADOW_EFFECT_KIND,
            "source_unit_instance_ids": list(source_unit_ids),
            "target_enemy_unit_instance_ids": list(target_unit_ids),
            "rules_update_source": RULE_UPDATE_SOURCE,
        }
    )
    unleash_payload = validate_json_value(
        {
            **cast(dict[str, JsonValue], common_payload),
            "submission_kind": SHADOW_SELECTION_KIND,
            "selected_shadow_option": "unleash",
        }
    )
    decline_payload = validate_json_value(
        {
            **cast(dict[str, JsonValue], common_payload),
            "submission_kind": SHADOW_SELECTION_KIND,
            "selected_shadow_option": "decline",
        }
    )
    expected_option_authority = tuple(
        sorted(
            (
                (SHADOW_UNLEASH_OPTION_ID, unleash_payload),
                (SHADOW_DECLINE_OPTION_ID, decline_payload),
            )
        )
    )
    option_authority = tuple(
        (option.option_id, option.payload) for option in record.request.options
    )
    expected_state_payload = validate_json_value(
        {
            "selection_kind": SHADOW_SELECTION_KIND,
            "effect_kind": SHADOW_EFFECT_KIND,
            "selected_shadow_option": "unleash",
            "selected_option_id": SHADOW_UNLEASH_OPTION_ID,
            "game_id": historical.game_id,
            "battle_round": request.battle_round,
            "phase": BattlePhase.COMMAND.value,
            "active_player_id": historical.active_player_id,
            "player_id": source_state.player_id,
            "faction_id": TYRANIDS_FACTION_ID,
            "source_rule_id": SOURCE_RULE_ID,
            "hook_id": HOOK_ID,
            "source_unit_instance_ids": list(source_unit_ids),
            "target_enemy_unit_instance_ids": list(target_unit_ids),
            "phase_start_battle_shocked_unit_ids": list(
                historical.phase_start_battle_shocked_unit_ids
            ),
            "rules_update_source": RULE_UPDATE_SOURCE,
        }
    )
    prior_target_ids = _historical_shadow_resolved_target_ids(
        historical=historical,
        source_state=source_state,
    )
    if (
        not source_unit_ids
        or not target_unit_ids
        or army.detachment_selection.faction_id != TYRANIDS_FACTION_ID
        or source_state.state_id != f"{HOOK_ID}:{source_state.player_id}:unleashed"
        or source_state.faction_id != TYRANIDS_FACTION_ID
        or source_state.source_rule_id != SOURCE_RULE_ID
        or source_state.state_kind != SHADOW_STATE_KIND
        or source_state.setup_step is not SetupStep.DECLARE_BATTLE_FORMATIONS
        or source_state.request_id != record.request.request_id
        or source_state.result_id != record.result.result_id
        or source_state.payload != expected_state_payload
        or record.request.decision_type
        != SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE
        or record.request.actor_id != source_state.player_id
        or record.request.payload != common_payload
        or option_authority != expected_option_authority
        or record.result.request_id != record.request.request_id
        or record.result.decision_type != record.request.decision_type
        or record.result.actor_id != source_state.player_id
        or record.result.selected_option_id != SHADOW_UNLEASH_OPTION_ID
        or record.result.payload != unleash_payload
        or request.game_id != historical.game_id
        or request.player_id == source_state.player_id
        or request.reason is not BattleShockTestReason.FORCED_BY_ARMY_RULE
        or prior_target_ids != target_unit_ids[: len(prior_target_ids)]
        or len(prior_target_ids) >= len(target_unit_ids)
        or request.unit_instance_id != target_unit_ids[len(prior_target_ids)]
        or request.player_id != historical.rules_unit(request.unit_instance_id).owner_player_id
        or request.request_id
        != "".join(
            (
                _shadow_request_prefix(
                    battle_round=request.battle_round,
                    tyranids_player_id=source_state.player_id,
                ),
                request.unit_instance_id,
            )
        )
    ):
        raise GameLifecycleError("Completed Shadow in the Warp authority drifted.")


def _historical_shadow_resolved_target_ids(
    *,
    historical: HistoricalBattleShockAuthorityContext,
    source_state: FactionRuleState,
) -> tuple[str, ...]:
    source_payload = source_state.to_payload()
    target_ids: list[str] = []
    for event in historical.event_records[: historical.boundary_event_index]:
        if event.event_type != "battle_shock_test_resolved" or not isinstance(event.payload, dict):
            continue
        if event.payload.get("source_faction_rule_state") != source_payload:
            continue
        result_payload = event.payload.get("battle_shock_result")
        if not isinstance(result_payload, dict):
            raise GameLifecycleError("Historical Shadow result payload is invalid.")
        result = BattleShockResult.from_payload(cast(BattleShockResultPayload, result_payload))
        target_ids.append(result.request.unit_instance_id)
    return tuple(target_ids)


def _shadow_source_state_from_nested_request(
    *,
    context: CommandPhaseStartNestedResultContext | CommandPhaseStartNestedPendingAuthorityContext,
) -> FactionRuleState | None:
    request = context.request
    if request.decision_type == DICE_REROLL_DECISION_TYPE:
        authority = parse_pending_battle_shock_reroll_authority(request)
        if authority.source_kind != COMMAND_PHASE_START_BATTLE_SHOCK_SOURCE_KIND:
            return None
        return _shadow_source_state_from_pending_authority(
            state=context.state,
            authority=authority,
        )
    outcome = context.battle_shock_hooks.pending_outcome_authority_for(
        BattleShockPendingOutcomeAuthorityContext(
            state=context.state,
            decisions=context.decisions,
            request=request,
        )
    )
    if outcome is None:
        return None
    resolved_event = context.decisions.event_log.records[outcome.resolved_event_index]
    resolved_payload = _payload_object(resolved_event.payload)
    if (
        resolved_event.event_type != "battle_shock_test_resolved"
        or resolved_payload.get("battle_shock_result") != outcome.result.to_payload()
    ):
        raise GameLifecycleError("Shadow in the Warp outcome result authority drifted.")
    raw_source_state = resolved_payload.get("source_faction_rule_state")
    if not isinstance(raw_source_state, dict):
        raise GameLifecycleError("Shadow in the Warp outcome lacks source-state authority.")
    source_state = FactionRuleState.from_payload(cast(FactionRuleStatePayload, raw_source_state))
    if source_state not in context.state.faction_rule_states:
        raise GameLifecycleError("Shadow in the Warp outcome source state drifted.")
    _validate_shadow_continuation_occurrence(
        state=context.state,
        decisions=context.decisions,
        active_player_id=context.active_player_id,
        source_state=source_state,
    )
    _validate_shadow_outcome_result_prefix(
        state=context.state,
        decisions=context.decisions,
        source_state=source_state,
        result=outcome.result,
    )
    return source_state


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
    rules_unit = rules_unit_view_by_id(
        state=context.state,
        unit_instance_id=context.unit_instance_id,
    )
    army = context.state.army_definition_for_player(rules_unit.owner_player_id)
    if army is None:
        raise GameLifecycleError("Synapse Battle-shock rules unit has no army.")
    if rules_unit.owner_player_id != context.player_id:
        raise GameLifecycleError("Synapse Battle-shock dice expression player drift.")
    if army.detachment_selection.faction_id != TYRANIDS_FACTION_ID:
        return None
    if TYRANIDS_FACTION_KEYWORD not in rules_unit.faction_keywords:
        return None
    if not tyranids_unit_within_synapse_range(
        context.state,
        tyranids_army=army,
        unit_instance_id=rules_unit.unit_instance_id,
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
        target_rules_unit = rules_unit_view_by_id(
            state=context.state,
            unit_instance_id=context.request.unit_instance_id,
        )
        if target_rules_unit.owner_player_id == tyranids_army.player_id:
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


def historical_synapse_battle_shock_contribution(
    context: HistoricalBattleShockAuthorityContext,
) -> HistoricalBattleShockContribution:
    if type(context) is not HistoricalBattleShockAuthorityContext:
        raise GameLifecycleError("Synapse historical authority requires a typed context.")
    target = context.rules_unit(context.request.unit_instance_id)
    target_army = context.army_for_player(target.owner_player_id)
    dice_expression = None
    if (
        target.owner_player_id == context.request.player_id
        and target_army.detachment_selection.faction_id == TYRANIDS_FACTION_ID
        and TYRANIDS_FACTION_KEYWORD in target.faction_keywords
        and _historical_unit_within_synapse_range(
            context=context,
            tyranids_army=target_army,
            target_unit_instance_id=target.unit_instance_id,
        )
    ):
        dice_expression = DiceExpression(quantity=3, sides=6)
    modifiers: list[RollModifier] = []
    for army in context.armies:
        if army.detachment_selection.faction_id != TYRANIDS_FACTION_ID:
            continue
        if not context.request.request_id.startswith(
            _shadow_request_prefix(
                battle_round=context.request.battle_round,
                tyranids_player_id=army.player_id,
            )
        ):
            continue
        if target.owner_player_id == army.player_id:
            raise GameLifecycleError("Shadow in the Warp historical target owner drifted.")
        if not _historical_unit_within_synapse_range(
            context=context,
            tyranids_army=army,
            target_unit_instance_id=target.unit_instance_id,
        ):
            continue
        modifiers.append(
            RollModifier(
                modifier_id=(
                    f"{BATTLE_SHOCK_HOOK_ID}:shadow-penalty:"
                    f"{context.request.request_id}:{army.player_id}"
                ),
                source_id=SOURCE_RULE_ID,
                operand=-1,
            )
        )
    return HistoricalBattleShockContribution(
        dice_expression=dice_expression,
        modifiers=tuple(modifiers),
    )


def _historical_unit_within_synapse_range(
    *,
    context: HistoricalBattleShockAuthorityContext,
    tyranids_army: ArmyDefinition,
    target_unit_instance_id: str,
) -> bool:
    target_models = context.geometry_models(target_unit_instance_id)
    if not target_models:
        return False
    for source_unit in tyranids_army.units:
        if not _unit_has_synapse(source_unit):
            continue
        for source_model in context.component_geometry_models(source_unit.unit_instance_id):
            if any(
                shapely_backend.base_footprint_distance(
                    source_model.base,
                    source_model.pose,
                    target_model.base,
                    target_model.pose,
                )
                <= SYNAPSE_RANGE_INCHES
                for target_model in target_models
            ):
                return True
    return False


def validate_shadow_in_the_warp_battle_shock_modifier_application(
    context: BattleShockModifierApplicationAuthorityContext,
) -> None:
    if type(context) is not BattleShockModifierApplicationAuthorityContext:
        raise GameLifecycleError("Shadow in the Warp modifier authority requires context.")
    application = context.application
    if application.hook_id != BATTLE_SHOCK_HOOK_ID or application.source_id != SOURCE_RULE_ID:
        raise GameLifecycleError("Shadow in the Warp Battle-shock modifier source drifted.")
    prefix = f"{BATTLE_SHOCK_HOOK_ID}:shadow-penalty:{context.request.request_id}:"
    for modifier in application.modifiers:
        if (
            modifier.operand != -1
            or not modifier.modifier_id.startswith(prefix)
            or not modifier.modifier_id.removeprefix(prefix)
        ):
            raise GameLifecycleError("Shadow in the Warp Battle-shock modifier operand drifted.")
    expected = battle_shock_modifier_applications_from_modifiers(
        provider_id=BATTLE_SHOCK_HOOK_ID,
        modifiers=shadow_in_the_warp_battle_shock_modifiers(
            BattleShockModifierContext(
                state=context.state,
                request=context.request,
                active_player_id=context.active_player_id,
                phase=context.phase,
                phase_start_battle_shocked_unit_ids=(context.phase_start_battle_shocked_unit_ids),
            )
        ),
    )
    if application not in expected:
        raise GameLifecycleError("Shadow in the Warp Battle-shock modifier predicate drifted.")


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


def continue_shadow_in_the_warp_battle_shock_tests(
    *,
    state: GameState,
    decisions: DecisionController,
    active_player_id: str,
    source_state: FactionRuleState,
    runtime: BattleShockTestRuntime,
) -> LifecycleStatus | None:
    return _continue_shadow_in_the_warp_battle_shock_tests(
        state=state,
        decisions=decisions,
        active_player_id=active_player_id,
        source_state=source_state,
        runtime=runtime,
    )


def _shadow_source_state_from_pending_authority(
    *,
    state: GameState,
    authority: PendingBattleShockRerollAuthority,
) -> FactionRuleState | None:
    raw_source_state = authority.base_payload.get("source_faction_rule_state")
    if not isinstance(raw_source_state, dict):
        raise GameLifecycleError("Command-start Battle-shock lacks source state authority.")
    source_state = FactionRuleState.from_payload(cast(FactionRuleStatePayload, raw_source_state))
    matches = tuple(
        candidate for candidate in state.faction_rule_states if candidate == source_state
    )
    if len(matches) != 1:
        raise GameLifecycleError("Command-start Battle-shock source state is ambiguous.")
    source_payload = _payload_object(source_state.payload)
    if (
        source_state.source_rule_id != SOURCE_RULE_ID
        or source_state.state_kind != SHADOW_STATE_KIND
        or source_payload.get("hook_id") != HOOK_ID
    ):
        return None
    return source_state


def _validate_shadow_outcome_result_prefix(
    *,
    state: GameState,
    decisions: DecisionController,
    source_state: FactionRuleState,
    result: BattleShockResult,
) -> None:
    payload = _payload_object(source_state.payload)
    target_ids = _payload_string_list(payload, key="target_enemy_unit_instance_ids")
    resolved_request_ids: list[str] = []
    encountered_missing = False
    for target_id in target_ids:
        request_id = _shadow_test_request_id(
            state=state,
            tyranids_player_id=source_state.player_id,
            target_unit_instance_id=target_id,
        )
        resolved = _shadow_result_payloads_for_request(
            decisions=decisions,
            request_id=request_id,
            target_unit_instance_id=target_id,
        )
        if not resolved:
            encountered_missing = True
            continue
        if encountered_missing:
            raise GameLifecycleError("Shadow in the Warp outcome result prefix drifted.")
        resolved_request_ids.append(request_id)
    if not resolved_request_ids or resolved_request_ids[-1] != result.request.request_id:
        raise GameLifecycleError("Shadow in the Warp outcome target order drifted.")


def _validate_shadow_continuation_prefix(
    *,
    state: GameState,
    decisions: DecisionController,
    active_player_id: str,
    source_state: FactionRuleState,
) -> str | None:
    _validate_shadow_continuation_occurrence(
        state=state,
        decisions=decisions,
        active_player_id=active_player_id,
        source_state=source_state,
    )
    source_payload = _payload_object(source_state.payload)
    target_unit_ids = _payload_string_list(
        source_payload,
        key="target_enemy_unit_instance_ids",
    )
    tyranids_army = _tyranids_army_for_player(state, player_id=source_state.player_id)
    if tyranids_army is None:
        raise GameLifecycleError("Shadow in the Warp continuation army is missing.")
    first_missing_request_id: str | None = None
    for target_unit_id in target_unit_ids:
        target_rules_unit = rules_unit_view_by_id(
            state=state,
            unit_instance_id=target_unit_id,
        )
        if target_rules_unit.owner_player_id == tyranids_army.player_id:
            raise GameLifecycleError("Shadow in the Warp target unit owner drift.")
        request_id = _shadow_test_request_id(
            state=state,
            tyranids_player_id=tyranids_army.player_id,
            target_unit_instance_id=target_rules_unit.unit_instance_id,
        )
        resolved = _shadow_result_payloads_for_request(
            decisions=decisions,
            request_id=request_id,
            target_unit_instance_id=target_rules_unit.unit_instance_id,
        )
        if resolved and first_missing_request_id is not None:
            raise GameLifecycleError("Shadow in the Warp result prefix is non-contiguous.")
        if not resolved and first_missing_request_id is None:
            first_missing_request_id = request_id
    return first_missing_request_id


def _validate_shadow_continuation_occurrence(
    *,
    state: GameState,
    decisions: DecisionController,
    active_player_id: str,
    source_state: FactionRuleState,
) -> None:
    if type(source_state) is not FactionRuleState or source_state not in state.faction_rule_states:
        raise GameLifecycleError("Shadow in the Warp continuation source state drifted.")
    if (
        source_state.state_kind != SHADOW_STATE_KIND
        or source_state.source_rule_id != SOURCE_RULE_ID
        or source_state.state_id != f"{HOOK_ID}:{source_state.player_id}:unleashed"
        or source_state.faction_id != TYRANIDS_FACTION_ID
        or source_state.setup_step is not SetupStep.DECLARE_BATTLE_FORMATIONS
        or state.active_player_id != active_player_id
        or state.current_battle_phase is not BattlePhase.COMMAND
    ):
        raise GameLifecycleError("Shadow in the Warp continuation occurrence drifted.")
    tyranids_army = _tyranids_army_for_player(state, player_id=source_state.player_id)
    if tyranids_army is None:
        raise GameLifecycleError("Shadow in the Warp continuation army is missing.")
    records = tuple(
        record
        for record in decisions.records
        if record.request.request_id == source_state.request_id
        and record.result.result_id == source_state.result_id
    )
    if len(records) != 1:
        raise GameLifecycleError("Shadow in the Warp source decision authority drifted.")
    record = records[0]
    expected_common = _shadow_common_payload(
        state=state,
        active_player_id=active_player_id,
        player_id=source_state.player_id,
        source_unit_ids=_eligible_shadow_source_unit_ids(state=state, army=tyranids_army),
        target_unit_ids=_enemy_unit_ids_on_battlefield(state, tyranids_army=tyranids_army),
    )
    expected_result_payload = validate_json_value(
        {
            **expected_common,
            "submission_kind": SHADOW_SELECTION_KIND,
            "selected_shadow_option": "unleash",
        }
    )
    if (
        record.request.decision_type != SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE
        or record.request.actor_id != source_state.player_id
        or record.request.payload != validate_json_value(expected_common)
        or record.result.actor_id != source_state.player_id
        or record.result.selected_option_id != SHADOW_UNLEASH_OPTION_ID
        or record.result.payload != expected_result_payload
        or record.request.option_by_id(SHADOW_UNLEASH_OPTION_ID).payload != expected_result_payload
    ):
        raise GameLifecycleError("Shadow in the Warp source decision context drifted.")
    phase_start_ids = _shadow_phase_start_battle_shocked_unit_ids(
        state=state,
        decisions=decisions,
        source_state=source_state,
    )
    expected_state_payload = validate_json_value(
        {
            "selection_kind": SHADOW_SELECTION_KIND,
            "effect_kind": SHADOW_EFFECT_KIND,
            "selected_shadow_option": "unleash",
            "selected_option_id": SHADOW_UNLEASH_OPTION_ID,
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.COMMAND.value,
            "active_player_id": active_player_id,
            "player_id": source_state.player_id,
            "faction_id": TYRANIDS_FACTION_ID,
            "source_rule_id": SOURCE_RULE_ID,
            "hook_id": HOOK_ID,
            "source_unit_instance_ids": expected_common["source_unit_instance_ids"],
            "target_enemy_unit_instance_ids": expected_common["target_enemy_unit_instance_ids"],
            "phase_start_battle_shocked_unit_ids": list(phase_start_ids),
            "rules_update_source": RULE_UPDATE_SOURCE,
        }
    )
    if source_state.payload != expected_state_payload:
        raise GameLifecycleError("Shadow in the Warp source-state payload drifted.")


def _shadow_phase_start_battle_shocked_unit_ids(
    *,
    state: GameState,
    decisions: DecisionController,
    source_state: FactionRuleState,
) -> tuple[str, ...]:
    matching_request_indices = tuple(
        index
        for index, event in enumerate(decisions.event_log.records)
        if event.event_type == "battle_shock_test_requested"
        and isinstance(event.payload, dict)
        and event.payload.get("source_faction_rule_state") == source_state.to_payload()
    )
    if not matching_request_indices:
        values = tuple(state.battle_shocked_unit_ids)
    else:
        from warhammer40k_core.engine.battle_shock_state_history import (
            battle_shock_state_authority_before_event,
        )

        values = battle_shock_state_authority_before_event(
            state=state,
            event_records=decisions.event_log.records,
            decision_records=decisions.records,
            event_index=matching_request_indices[0],
        ).battle_shocked_unit_ids
    if values != tuple(sorted(set(values))):
        raise GameLifecycleError("Shadow in the Warp phase-start state drifted.")
    return values


def _shadow_test_request_id(
    *,
    state: GameState,
    tyranids_player_id: str,
    target_unit_instance_id: str,
) -> str:
    return "".join(
        (
            _shadow_request_prefix(
                battle_round=state.battle_round,
                tyranids_player_id=tyranids_player_id,
            ),
            target_unit_instance_id,
        )
    )


def _continue_shadow_in_the_warp_battle_shock_tests(
    *,
    state: GameState,
    decisions: DecisionController,
    active_player_id: str,
    source_state: FactionRuleState,
    runtime: BattleShockTestRuntime,
) -> LifecycleStatus | None:
    _validate_shadow_continuation_occurrence(
        state=state,
        decisions=decisions,
        active_player_id=active_player_id,
        source_state=source_state,
    )
    source_payload = _payload_object(source_state.payload)
    target_unit_ids = _payload_string_list(
        source_payload,
        key="target_enemy_unit_instance_ids",
    )
    source_unit_ids = _payload_string_list(
        source_payload,
        key="source_unit_instance_ids",
    )
    phase_start_battle_shocked_unit_ids = _payload_string_list(
        source_payload,
        key="phase_start_battle_shocked_unit_ids",
    )
    tyranids_army = _tyranids_army_for_player(state, player_id=source_state.player_id)
    if tyranids_army is None:
        raise GameLifecycleError("Shadow in the Warp continuation army is missing.")
    result_ids: list[str] = []
    encountered_missing = False
    for target_unit_id in target_unit_ids:
        target_rules_unit = rules_unit_view_by_id(
            state=state,
            unit_instance_id=target_unit_id,
        )
        if target_rules_unit.owner_player_id == tyranids_army.player_id:
            raise GameLifecycleError("Shadow in the Warp target unit owner drift.")
        request_id = _shadow_test_request_id(
            state=state,
            tyranids_player_id=tyranids_army.player_id,
            target_unit_instance_id=target_rules_unit.unit_instance_id,
        )
        resolved = _shadow_result_payloads_for_request(
            decisions=decisions,
            request_id=request_id,
            target_unit_instance_id=target_rules_unit.unit_instance_id,
        )
        if resolved:
            if encountered_missing:
                raise GameLifecycleError("Shadow in the Warp result prefix is non-contiguous.")
            result_ids.append(_payload_string(resolved[0], key="result_id"))
            continue
        encountered_missing = True
        execution = resolve_battle_shock_test(
            runtime=runtime,
            state=state,
            decisions=decisions,
            request_id=request_id,
            target_unit_instance_id=target_rules_unit.unit_instance_id,
            reason=BattleShockTestReason.FORCED_BY_ARMY_RULE,
            active_player_id=active_player_id,
            phase=BattlePhase.COMMAND,
            phase_start_battle_shocked_unit_ids=phase_start_battle_shocked_unit_ids,
            passed_state_policy=BattleShockPassedStatePolicy.PRESERVE,
            source_kind="command_phase_start_battle_shock",
            source_payload={
                "source_faction_rule_state": validate_json_value(source_state.to_payload()),
            },
            resolved_event_types=("battle_shock_test_resolved",),
            pending_phase_body_status="command_phase_start_battle_shock_reroll_pending",
        )
        if execution.resolution.pending_status is not None:
            return execution.resolution.pending_status
        pending_requests = decisions.queue.pending_requests
        if len(pending_requests) > 1:
            raise GameLifecycleError("Shadow in the Warp outcome queued multiple decisions.")
        if pending_requests:
            pending_request = pending_requests[0]
            return LifecycleStatus.waiting_for_decision(
                stage=state.stage,
                decision_request=pending_request,
                payload={
                    "phase": BattlePhase.COMMAND.value,
                    "phase_body_status": "command_phase_start_battle_shock_outcome_pending",
                    "battle_round": state.battle_round,
                    "active_player_id": active_player_id,
                    "pending_request_id": pending_request.request_id,
                },
            )
        result_ids.append(f"{request_id}:result")
        encountered_missing = False
    existing_completion = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == "tyranids_shadow_in_the_warp_unleashed"
        and isinstance(event.payload, dict)
        and event.payload.get("faction_rule_state") == source_state.to_payload()
    )
    if existing_completion:
        if len(existing_completion) != 1:
            raise GameLifecycleError("Shadow in the Warp completion is duplicated.")
        expected_completion_payload = validate_json_value(
            _shadow_completion_payload(
                state=state,
                active_player_id=active_player_id,
                source_state=source_state,
                source_unit_ids=source_unit_ids,
                target_unit_ids=target_unit_ids,
                result_ids=tuple(result_ids),
            )
        )
        if existing_completion[0].payload != expected_completion_payload:
            raise GameLifecycleError("Shadow in the Warp completion payload drifted.")
        return None
    decisions.event_log.append(
        "tyranids_shadow_in_the_warp_unleashed",
        _shadow_completion_payload(
            state=state,
            active_player_id=active_player_id,
            source_state=source_state,
            source_unit_ids=source_unit_ids,
            target_unit_ids=target_unit_ids,
            result_ids=tuple(result_ids),
        ),
    )
    return None


def _shadow_result_payloads_for_request(
    *,
    decisions: DecisionController,
    request_id: str,
    target_unit_instance_id: str,
) -> tuple[dict[str, JsonValue], ...]:
    matches: list[dict[str, JsonValue]] = []
    for event in decisions.event_log.records:
        if event.event_type != "battle_shock_test_resolved" or not isinstance(event.payload, dict):
            continue
        raw_result = event.payload.get("battle_shock_result")
        if not isinstance(raw_result, dict):
            raise GameLifecycleError("Shadow in the Warp result payload is invalid.")
        raw_request = raw_result.get("request")
        if not isinstance(raw_request, dict) or raw_request.get("request_id") != request_id:
            continue
        if (
            raw_request.get("unit_instance_id") != target_unit_instance_id
            or raw_result.get("result_id") != f"{request_id}:result"
        ):
            raise GameLifecycleError("Shadow in the Warp result identity drifted.")
        matches.append(raw_result)
    if len(matches) > 1:
        raise GameLifecycleError("Shadow in the Warp result is duplicated.")
    return tuple(matches)


def _shadow_completion_payload(
    *,
    state: GameState,
    active_player_id: str,
    source_state: FactionRuleState,
    source_unit_ids: tuple[str, ...],
    target_unit_ids: tuple[str, ...],
    result_ids: tuple[str, ...],
) -> dict[str, JsonValue]:
    return cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "active_player_id": active_player_id,
                "player_id": source_state.player_id,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
                "source_unit_instance_ids": list(source_unit_ids),
                "target_enemy_unit_instance_ids": list(target_unit_ids),
                "battle_shock_result_ids": list(result_ids),
                "faction_rule_state": source_state.to_payload(),
            }
        ),
    )


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
                "phase_start_battle_shocked_unit_ids": sorted(
                    context.state.battle_shocked_unit_ids
                ),
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
    return tuple(
        rules_unit.unit_instance_id
        for rules_unit in placed_alive_rules_unit_views(state=state)
        if rules_unit.owner_player_id != tyranids_army.player_id
    )


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
            placed_alive_geometry_models_for_component_unit(
                state=state,
                component_unit_instance_id=source_unit.unit_instance_id,
            )
        )
    return tuple(models)


def _unit_geometry_models(
    *,
    state: GameState,
    unit_instance_id: str,
) -> tuple[GeometryModel, ...]:
    return placed_alive_geometry_models_for_rules_unit(
        state=state,
        unit_instance_id=unit_instance_id,
    )


def _current_battlefield_model_ids(
    state: GameState,
    *,
    unit: UnitInstance,
) -> tuple[str, ...]:
    if state.battlefield_state is None:
        raise GameLifecycleError("Battlefield model lookup requires battlefield_state.")
    placement = state.battlefield_state.unit_placement_or_none(unit.unit_instance_id)
    if placement is None:
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
    return any(ability.source_id == SOURCE_RULE_ID for ability in unit.datasheet_abilities)


def _unit_has_synapse(unit: UnitInstance) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Synapse requires a UnitInstance.")
    return _unit_has_keyword(unit, SYNAPSE_KEYWORD)


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    requested_keyword = _validate_identifier("keyword", keyword)
    return requested_keyword in (*unit.keywords, *unit.faction_keywords)


def _unit_has_faction_keyword(unit: UnitInstance, keyword: str) -> bool:
    requested_keyword = _validate_identifier("keyword", keyword)
    return requested_keyword in unit.faction_keywords


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


def _shadow_request_prefix(*, battle_round: int, tyranids_player_id: str) -> str:
    requested_round = _validate_positive_int("battle_round", battle_round)
    requested_player_id = _validate_identifier("tyranids_player_id", tyranids_player_id)
    return f"{HOOK_ID}:shadow:{requested_player_id}:round-{requested_round:02d}:"


def _payload_int(payload: dict[str, JsonValue], *, key: str) -> int:
    value = payload.get(key)
    return _validate_positive_int(key, value)


def _validate_game_state(state: object) -> None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Tyranids army rule requires GameState.")


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"Tyranids army rule {field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"Tyranids army rule {field_name} must be positive.")
    return value
