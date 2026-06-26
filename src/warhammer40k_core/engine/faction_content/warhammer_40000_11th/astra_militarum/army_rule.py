from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import DatasheetAbilityDescriptor
from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.core.weapon_profiles import (
    AbilityKind,
    AttackProfile,
    RangeProfileKind,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockHookBinding,
    BattleShockOutcomeContext,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    BattlefieldScenario,
    ModelPlacement,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.command_phase_start_hooks import (
    SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
    CommandPhaseStartHookBinding,
    CommandPhaseStartRequestContext,
    CommandPhaseStartResultContext,
)
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.faction_rule_states import FactionRuleState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, SetupStep
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_id_for_unit_id,
    rules_unit_view_by_id,
)
from warhammer40k_core.engine.runtime_modifiers import (
    MovementBudgetModifierBinding,
    MovementBudgetModifierContext,
    ObjectiveControlModifierBinding,
    ObjectiveControlModifierContext,
    SaveOptionModifierBinding,
    SaveOptionModifierContext,
    UnitCharacteristicModifierBinding,
    UnitCharacteristicModifierContext,
    WeaponProfileModifierBinding,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.saves import SaveKind, SaveOption
from warhammer40k_core.engine.unit_factory import UnitInstance

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


CONTRIBUTION_ID = "warhammer_40000_11th:astra_militarum:army_rule:voice_of_command"
HOOK_ID = "warhammer_40000_11th:astra_militarum:army_rule:voice_of_command"
BATTLE_SHOCK_HOOK_ID = f"{HOOK_ID}:battle-shock"
UNIT_CHARACTERISTIC_MODIFIER_ID = f"{HOOK_ID}:unit-characteristic"
MOVEMENT_MODIFIER_ID = f"{HOOK_ID}:movement"
OBJECTIVE_CONTROL_MODIFIER_ID = f"{HOOK_ID}:objective-control"
SAVE_OPTION_MODIFIER_ID = f"{HOOK_ID}:save-option"
WEAPON_PROFILE_MODIFIER_ID = f"{HOOK_ID}:weapon-profile"
SOURCE_RULE_ID = "phase17f:phase17e:astra-militarum:army-rule"
ASTRA_MILITARUM_FACTION_ID = "astra-militarum"
ASTRA_MILITARUM_FACTION_KEYWORD = "ASTRA MILITARUM"
OFFICER_KEYWORD = "OFFICER"
ORDERS_ABILITY_NAME = "Orders"
VOICE_OF_COMMAND_EFFECT_KIND = "astra_militarum_voice_of_command_order"
VOICE_OF_COMMAND_ISSUE_STATE_KIND = "astra_militarum_voice_of_command_order_issued"
VOICE_OF_COMMAND_DONE_STATE_KIND = "astra_militarum_voice_of_command_command_phase_done"
VOICE_OF_COMMAND_SELECTION_KIND = "astra_militarum_voice_of_command_issue"
ORDERS_PROFILE_KIND = "astra_militarum_voice_of_command_orders_profile"
VOICE_OF_COMMAND_DONE_OPTION_ID = "astra_militarum:voice_of_command:done"
ORDER_RANGE_INCHES = 6.0


class VoiceOfCommandOrder(StrEnum):
    MOVE_MOVE_MOVE = "move_move_move"
    FIX_BAYONETS = "fix_bayonets"
    TAKE_AIM = "take_aim"
    FIRST_RANK_FIRE_SECOND_RANK_FIRE = "first_rank_fire_second_rank_fire"
    TAKE_COVER = "take_cover"
    DUTY_AND_HONOUR = "duty_and_honour"


ORDER_LABELS: dict[VoiceOfCommandOrder, str] = {
    VoiceOfCommandOrder.MOVE_MOVE_MOVE: "Move! Move! Move!",
    VoiceOfCommandOrder.FIX_BAYONETS: "Fix Bayonets!",
    VoiceOfCommandOrder.TAKE_AIM: "Take Aim!",
    VoiceOfCommandOrder.FIRST_RANK_FIRE_SECOND_RANK_FIRE: ("First Rank, Fire! Second Rank, Fire!"),
    VoiceOfCommandOrder.TAKE_COVER: "Take Cover!",
    VoiceOfCommandOrder.DUTY_AND_HONOUR: "Duty and Honour!",
}
ORDER_SEQUENCE = tuple(VoiceOfCommandOrder)


@dataclass(frozen=True, slots=True)
class VoiceOfCommandOrdersProfile:
    orders_per_battle_round: int
    eligible_target_keywords: tuple[str, ...]
    allowed_order_ids: tuple[VoiceOfCommandOrder, ...]

    def __post_init__(self) -> None:
        if type(self.orders_per_battle_round) is not int or self.orders_per_battle_round < 1:
            raise GameLifecycleError(
                "Voice of Command orders_per_battle_round must be a positive integer."
            )
        object.__setattr__(
            self,
            "eligible_target_keywords",
            _validate_identifier_tuple(
                "eligible_target_keywords",
                self.eligible_target_keywords,
                min_length=1,
            ),
        )
        object.__setattr__(
            self,
            "allowed_order_ids",
            _validate_order_tuple(self.allowed_order_ids),
        )


@dataclass(frozen=True, slots=True)
class VoiceOfCommandIssueOption:
    officer_unit: UnitInstance
    officer_profile: VoiceOfCommandOrdersProfile
    target_rules_unit: RulesUnitView
    order: VoiceOfCommandOrder
    issued_count_before: int

    def __post_init__(self) -> None:
        if type(self.officer_unit) is not UnitInstance:
            raise GameLifecycleError("Voice of Command issue option requires officer unit.")
        if type(self.officer_profile) is not VoiceOfCommandOrdersProfile:
            raise GameLifecycleError("Voice of Command issue option requires officer profile.")
        if type(self.target_rules_unit) is not RulesUnitView:
            raise GameLifecycleError("Voice of Command issue option requires target rules unit.")
        object.__setattr__(self, "order", _order_from_token(self.order))
        if type(self.issued_count_before) is not int or self.issued_count_before < 0:
            raise GameLifecycleError("Voice of Command issued_count_before must be non-negative.")


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        command_phase_start_hook_bindings=(
            CommandPhaseStartHookBinding(
                hook_id=HOOK_ID,
                source_id=SOURCE_RULE_ID,
                request_handler=voice_of_command_request,
                result_handler=apply_voice_of_command_result,
            ),
        ),
        battle_shock_hook_bindings=(
            BattleShockHookBinding(
                hook_id=BATTLE_SHOCK_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                outcome_handler=voice_of_command_battle_shock_outcome,
            ),
        ),
        unit_characteristic_modifier_bindings=(
            UnitCharacteristicModifierBinding(
                modifier_id=UNIT_CHARACTERISTIC_MODIFIER_ID,
                source_id=SOURCE_RULE_ID,
                handler=voice_of_command_unit_characteristic_modifier,
            ),
        ),
        movement_budget_modifier_bindings=(
            MovementBudgetModifierBinding(
                modifier_id=MOVEMENT_MODIFIER_ID,
                source_id=SOURCE_RULE_ID,
                handler=voice_of_command_movement_modifier,
            ),
        ),
        objective_control_modifier_bindings=(
            ObjectiveControlModifierBinding(
                modifier_id=OBJECTIVE_CONTROL_MODIFIER_ID,
                source_id=SOURCE_RULE_ID,
                handler=voice_of_command_objective_control_modifier,
            ),
        ),
        save_option_modifier_bindings=(
            SaveOptionModifierBinding(
                modifier_id=SAVE_OPTION_MODIFIER_ID,
                source_id=SOURCE_RULE_ID,
                handler=voice_of_command_save_option_modifier,
            ),
        ),
        weapon_profile_modifier_bindings=(
            WeaponProfileModifierBinding(
                modifier_id=WEAPON_PROFILE_MODIFIER_ID,
                source_id=SOURCE_RULE_ID,
                handler=voice_of_command_weapon_profile_modifier,
            ),
        ),
    )


def voice_of_command_request(
    context: CommandPhaseStartRequestContext,
) -> DecisionRequest | None:
    if type(context) is not CommandPhaseStartRequestContext:
        raise GameLifecycleError("Voice of Command requires request context.")
    army = _astra_militarum_army_for_player(context.state, player_id=context.active_player_id)
    if army is None:
        return None
    if _voice_of_command_done_this_command_phase(context.state, player_id=army.player_id):
        return None

    issues = _eligible_voice_of_command_issues(context.state, army=army)
    if not issues:
        return None

    common_payload = _payload_object(
        validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "active_player_id": army.player_id,
                "player_id": army.player_id,
                "faction_id": ASTRA_MILITARUM_FACTION_ID,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
                "effect_kind": VOICE_OF_COMMAND_EFFECT_KIND,
                "selection_kind": VOICE_OF_COMMAND_SELECTION_KIND,
                "order_range_inches": ORDER_RANGE_INCHES,
                "eligible_issue_option_ids": [_voice_issue_option_id(issue) for issue in issues],
                "expires_at_battle_round": _next_own_turn_battle_round(context.state),
            }
        )
    )
    options = tuple(_voice_issue_decision_option(issue, common_payload) for issue in issues)
    return DecisionRequest(
        request_id=context.state.next_decision_request_id(),
        decision_type=SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
        actor_id=army.player_id,
        payload=validate_json_value(common_payload),
        options=(
            *options,
            DecisionOption(
                option_id=VOICE_OF_COMMAND_DONE_OPTION_ID,
                label="No more Orders",
                payload=validate_json_value(
                    {
                        **common_payload,
                        "submission_kind": VOICE_OF_COMMAND_SELECTION_KIND,
                        "selected_voice_of_command_option": "done",
                    }
                ),
            ),
        ),
    )


def apply_voice_of_command_result(context: CommandPhaseStartResultContext) -> bool:
    if type(context) is not CommandPhaseStartResultContext:
        raise GameLifecycleError("Voice of Command requires result context.")
    if (
        context.request.decision_type
        != SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE
    ):
        return False
    request_payload = _payload_object(context.request.payload)
    if request_payload.get("hook_id") != HOOK_ID:
        return False

    result = context.result
    if result.actor_id is None:
        raise GameLifecycleError("Voice of Command result requires an actor.")
    player_id = result.actor_id
    army = _astra_militarum_army_for_player(context.state, player_id=player_id)
    if army is None:
        raise GameLifecycleError("Voice of Command actor does not own Astra Militarum.")
    if _voice_of_command_done_this_command_phase(context.state, player_id=player_id):
        raise GameLifecycleError("Voice of Command was already completed this Command phase.")

    payload = _payload_object(result.payload)
    selected = _payload_string(payload, key="selected_voice_of_command_option")
    if selected == "done":
        if result.selected_option_id != VOICE_OF_COMMAND_DONE_OPTION_ID:
            raise GameLifecycleError("Voice of Command done option ID drift.")
        _record_voice_of_command_done(context, player_id=player_id)
        return True
    if selected != "issue":
        raise GameLifecycleError("Voice of Command selection is unsupported.")

    order = _order_from_token(_payload_string(payload, key="order_id"))
    officer_unit_id = _payload_string(payload, key="issuing_officer_unit_instance_id")
    target_rules_unit_id = _payload_string(payload, key="ordered_rules_unit_instance_id")
    current_issues = {
        _voice_issue_option_id(issue): issue
        for issue in _eligible_voice_of_command_issues(context.state, army=army)
    }
    issue = current_issues.get(result.selected_option_id)
    if issue is None:
        raise GameLifecycleError("Voice of Command issue is no longer eligible.")
    if issue.order is not order:
        raise GameLifecycleError("Voice of Command order payload drift.")
    if issue.officer_unit.unit_instance_id != officer_unit_id:
        raise GameLifecycleError("Voice of Command officer payload drift.")
    if issue.target_rules_unit.unit_instance_id != target_rules_unit_id:
        raise GameLifecycleError("Voice of Command target payload drift.")

    _record_voice_of_command_issue(context, player_id=player_id, issue=issue)
    return True


def active_voice_of_command_order_id_for_unit(
    state: GameState,
    *,
    unit_instance_id: str,
) -> str | None:
    _validate_game_state(state)
    order = _active_voice_of_command_order_for_unit(state, unit_instance_id=unit_instance_id)
    return None if order is None else order.value


def voice_of_command_battle_shock_outcome(context: BattleShockOutcomeContext) -> None:
    if type(context) is not BattleShockOutcomeContext:
        raise GameLifecycleError("Voice of Command Battle-shock outcome requires context.")
    if context.result.passed:
        return
    rules_unit_id = rules_unit_id_for_unit_id(
        armies=tuple(context.state.army_definitions),
        unit_instance_id=context.result.request.unit_instance_id,
    )
    removed = _clear_active_voice_of_command_order_effects(
        context.state,
        target_rules_unit_instance_id=rules_unit_id,
    )
    if not removed:
        return
    context.decisions.event_log.append(
        "astra_militarum_voice_of_command_order_ceased_battle_shock",
        {
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "phase": context.phase.value,
            "player_id": context.result.request.player_id,
            "target_rules_unit_instance_id": rules_unit_id,
            "battle_shock_result_id": context.result.result_id,
            "removed_effect_ids": [effect.effect_id for effect in removed],
            "source_rule_id": SOURCE_RULE_ID,
            "hook_id": BATTLE_SHOCK_HOOK_ID,
        },
    )


def voice_of_command_unit_characteristic_modifier(
    context: UnitCharacteristicModifierContext,
) -> int:
    if type(context) is not UnitCharacteristicModifierContext:
        raise GameLifecycleError("Voice of Command characteristic modifier requires context.")
    order = _active_voice_of_command_order_for_unit(
        context.state,
        unit_instance_id=context.unit_instance_id,
    )
    if order is VoiceOfCommandOrder.TAKE_COVER and context.characteristic is Characteristic.SAVE:
        return _improve_save(context.current_value)
    if (
        order is VoiceOfCommandOrder.DUTY_AND_HONOUR
        and context.characteristic is Characteristic.LEADERSHIP
    ):
        return _improve_leadership(context.current_value)
    if (
        order is VoiceOfCommandOrder.DUTY_AND_HONOUR
        and context.characteristic is Characteristic.OBJECTIVE_CONTROL
    ):
        return context.current_value + 1
    return context.current_value


def voice_of_command_movement_modifier(context: MovementBudgetModifierContext) -> float:
    if type(context) is not MovementBudgetModifierContext:
        raise GameLifecycleError("Voice of Command movement modifier requires context.")
    order = _active_voice_of_command_order_for_unit(
        context.state,
        unit_instance_id=context.unit_instance_id,
    )
    if order is not VoiceOfCommandOrder.MOVE_MOVE_MOVE:
        return context.current_movement_inches
    return context.current_movement_inches + 3.0


def voice_of_command_objective_control_modifier(
    context: ObjectiveControlModifierContext,
) -> int:
    if type(context) is not ObjectiveControlModifierContext:
        raise GameLifecycleError("Voice of Command Objective Control modifier requires context.")
    order = _active_voice_of_command_order_for_unit(
        context.state,
        unit_instance_id=context.unit_instance_id,
    )
    if order is not VoiceOfCommandOrder.DUTY_AND_HONOUR:
        return context.current_objective_control
    return context.current_objective_control + 1


def voice_of_command_save_option_modifier(
    context: SaveOptionModifierContext,
) -> tuple[SaveOption, ...]:
    if type(context) is not SaveOptionModifierContext:
        raise GameLifecycleError("Voice of Command save option modifier requires context.")
    order = _active_voice_of_command_order_for_unit(
        context.state,
        unit_instance_id=context.target_unit_instance_id,
    )
    if order is not VoiceOfCommandOrder.TAKE_COVER:
        return context.save_options
    return tuple(_improve_armour_save_option(option) for option in context.save_options)


def voice_of_command_weapon_profile_modifier(
    context: WeaponProfileModifierContext,
) -> WeaponProfile:
    if type(context) is not WeaponProfileModifierContext:
        raise GameLifecycleError("Voice of Command weapon profile modifier requires context.")
    order = _active_voice_of_command_order_for_unit(
        context.state,
        unit_instance_id=context.attacking_unit_instance_id,
    )
    if order is VoiceOfCommandOrder.FIX_BAYONETS:
        if context.source_phase is not BattlePhase.FIGHT:
            return context.weapon_profile
        if context.weapon_profile.range_profile.kind is not RangeProfileKind.MELEE:
            return context.weapon_profile
        return replace(
            context.weapon_profile,
            skill=_improve_weapon_skill(context.weapon_profile.skill),
            source_ids=_source_ids_with_voice_of_command(context.weapon_profile.source_ids),
        )
    if order is VoiceOfCommandOrder.TAKE_AIM:
        if context.source_phase is not BattlePhase.SHOOTING:
            return context.weapon_profile
        if context.weapon_profile.range_profile.kind is not RangeProfileKind.DISTANCE:
            return context.weapon_profile
        return replace(
            context.weapon_profile,
            skill=_improve_ballistic_skill(context.weapon_profile.skill),
            source_ids=_source_ids_with_voice_of_command(context.weapon_profile.source_ids),
        )
    if order is VoiceOfCommandOrder.FIRST_RANK_FIRE_SECOND_RANK_FIRE:
        if context.source_phase is not BattlePhase.SHOOTING:
            return context.weapon_profile
        if context.weapon_profile.range_profile.kind is not RangeProfileKind.DISTANCE:
            return context.weapon_profile
        if not _profile_has_rapid_fire(context.weapon_profile):
            return context.weapon_profile
        return replace(
            context.weapon_profile,
            attack_profile=_attack_profile_with_plus_one(context.weapon_profile.attack_profile),
            source_ids=_source_ids_with_voice_of_command(context.weapon_profile.source_ids),
        )
    return context.weapon_profile


def _record_voice_of_command_issue(
    context: CommandPhaseStartResultContext,
    *,
    player_id: str,
    issue: VoiceOfCommandIssueOption,
) -> None:
    issue_state = _voice_of_command_issue_state(context=context, player_id=player_id, issue=issue)
    target_id = issue.target_rules_unit.unit_instance_id
    replaced_effects = _clear_active_voice_of_command_order_effects(
        context.state,
        target_rules_unit_instance_id=target_id,
    )
    effect = _voice_of_command_order_effect(
        context=context,
        player_id=player_id,
        issue=issue,
        issue_state=issue_state,
    )
    context.state.record_faction_rule_state(issue_state)
    context.state.record_persisting_effect(effect)
    context.decisions.event_log.append(
        "astra_militarum_voice_of_command_order_issued",
        {
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "phase": BattlePhase.COMMAND.value,
            "player_id": player_id,
            "issuing_officer_unit_instance_id": issue.officer_unit.unit_instance_id,
            "ordered_rules_unit_instance_id": target_id,
            "order_id": issue.order.value,
            "order_label": ORDER_LABELS[issue.order],
            "replaced_effect_ids": [stored.effect_id for stored in replaced_effects],
            "faction_rule_state": validate_json_value(issue_state.to_payload()),
            "persisting_effect": validate_json_value(effect.to_payload()),
            "source_rule_id": SOURCE_RULE_ID,
            "hook_id": HOOK_ID,
            "request_id": context.request.request_id,
            "result_id": context.result.result_id,
        },
    )


def _voice_issue_decision_option(
    issue: VoiceOfCommandIssueOption,
    common_payload: dict[str, JsonValue],
) -> DecisionOption:
    option_id = _voice_issue_option_id(issue)
    return DecisionOption(
        option_id=option_id,
        label=(f"Issue {ORDER_LABELS[issue.order]}: {_rules_unit_label(issue.target_rules_unit)}"),
        payload=validate_json_value(
            {
                **common_payload,
                "submission_kind": VOICE_OF_COMMAND_SELECTION_KIND,
                "selected_voice_of_command_option": "issue",
                "selected_option_id": option_id,
                "issuing_officer_unit_instance_id": issue.officer_unit.unit_instance_id,
                "issuing_officer_unit_name": issue.officer_unit.name,
                "ordered_rules_unit_instance_id": issue.target_rules_unit.unit_instance_id,
                "ordered_rules_unit_name": _rules_unit_label(issue.target_rules_unit),
                "ordered_component_unit_instance_ids": list(
                    issue.target_rules_unit.component_unit_instance_ids
                ),
                "order_id": issue.order.value,
                "order_label": ORDER_LABELS[issue.order],
                "orders_per_battle_round": issue.officer_profile.orders_per_battle_round,
                "orders_issued_before": issue.issued_count_before,
                "eligible_target_keywords": list(issue.officer_profile.eligible_target_keywords),
                "allowed_order_ids": [
                    order.value for order in issue.officer_profile.allowed_order_ids
                ],
            }
        ),
    )


def _eligible_voice_of_command_issues(
    state: GameState,
    *,
    army: ArmyDefinition,
) -> tuple[VoiceOfCommandIssueOption, ...]:
    _validate_game_state(state)
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError("Voice of Command issue lookup requires an ArmyDefinition.")
    issues: list[VoiceOfCommandIssueOption] = []
    for officer in army.units:
        if not _unit_has_faction_keyword(officer, ASTRA_MILITARUM_FACTION_KEYWORD):
            continue
        if not _unit_has_keyword(officer, OFFICER_KEYWORD):
            continue
        if not officer.alive_own_models():
            continue
        profile = _voice_of_command_orders_profile_for_unit(officer)
        if profile is None:
            continue
        issued_count = _issued_order_count_for_officer_this_round(
            state,
            player_id=army.player_id,
            officer_unit_instance_id=officer.unit_instance_id,
        )
        if issued_count >= profile.orders_per_battle_round:
            continue
        for target in _eligible_voice_of_command_targets(
            state,
            army=army,
            officer=officer,
            profile=profile,
        ):
            for order in ORDER_SEQUENCE:
                if order not in profile.allowed_order_ids:
                    continue
                issues.append(
                    VoiceOfCommandIssueOption(
                        officer_unit=officer,
                        officer_profile=profile,
                        target_rules_unit=target,
                        order=order,
                        issued_count_before=issued_count,
                    )
                )
    return tuple(sorted(issues, key=_voice_issue_option_id))


def _eligible_voice_of_command_targets(
    state: GameState,
    *,
    army: ArmyDefinition,
    officer: UnitInstance,
    profile: VoiceOfCommandOrdersProfile,
) -> tuple[RulesUnitView, ...]:
    seen_rules_unit_ids: set[str] = set()
    targets: list[RulesUnitView] = []
    for unit in army.units:
        rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id)
        if rules_unit.unit_instance_id in seen_rules_unit_ids:
            continue
        seen_rules_unit_ids.add(rules_unit.unit_instance_id)
        if rules_unit.owner_player_id != army.player_id:
            raise GameLifecycleError("Voice of Command friendly rules unit owner drift.")
        if not rules_unit.alive_models():
            continue
        if _rules_unit_is_battle_shocked(state, rules_unit):
            continue
        if not _rules_unit_has_faction_keyword(rules_unit, ASTRA_MILITARUM_FACTION_KEYWORD):
            continue
        if not _rules_unit_has_any_keyword(rules_unit, profile.eligible_target_keywords):
            continue
        if not _rules_unit_is_on_battlefield(state=state, rules_unit=rules_unit):
            continue
        if not _unit_within_voice_of_command_range(
            state=state,
            officer=officer,
            target_rules_unit=rules_unit,
        ):
            continue
        targets.append(rules_unit)
    return tuple(sorted(targets, key=lambda rules_unit: rules_unit.unit_instance_id))


def _unit_within_voice_of_command_range(
    *,
    state: GameState,
    officer: UnitInstance,
    target_rules_unit: RulesUnitView,
) -> bool:
    if state.battlefield_state is None:
        raise GameLifecycleError("Voice of Command requires battlefield_state.")
    source_placement = _unit_placement_or_none(state, unit_instance_id=officer.unit_instance_id)
    if source_placement is None:
        return False
    target_placements = _rules_unit_placements(state=state, rules_unit=target_rules_unit)
    if not target_placements:
        return False
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    for source_model_placement in source_placement.model_placements:
        source_model = geometry_model_for_placement(
            model=scenario.model_instance_for_placement(source_model_placement),
            placement=source_model_placement,
        )
        for target_model_placement in target_placements:
            target_model = geometry_model_for_placement(
                model=scenario.model_instance_for_placement(target_model_placement),
                placement=target_model_placement,
            )
            if source_model.range_to(target_model) <= ORDER_RANGE_INCHES:
                return True
    return False


def _unit_placement_or_none(
    state: GameState,
    *,
    unit_instance_id: str,
) -> UnitPlacement | None:
    battlefield = _battlefield_state(state)
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for placed_army in battlefield.placed_armies:
        for placement in placed_army.unit_placements:
            if placement.unit_instance_id == requested_unit_id:
                return placement
    return None


def _rules_unit_placements(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
) -> tuple[ModelPlacement, ...]:
    battlefield = _battlefield_state(state)
    component_ids = set(rules_unit.component_unit_instance_ids)
    model_ids = {model.model_instance_id for model in rules_unit.own_models}
    placements: list[ModelPlacement] = []
    for placed_army in battlefield.placed_armies:
        if placed_army.player_id != rules_unit.owner_player_id:
            continue
        for unit_placement in placed_army.unit_placements:
            if unit_placement.unit_instance_id not in component_ids:
                continue
            placements.extend(
                placement
                for placement in unit_placement.model_placements
                if placement.model_instance_id in model_ids
            )
    return tuple(sorted(placements, key=lambda placement: placement.model_instance_id))


def _rules_unit_is_on_battlefield(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
) -> bool:
    if not rules_unit.alive_models():
        return False
    placed_model_ids = {
        placement.model_instance_id
        for placement in _rules_unit_placements(state=state, rules_unit=rules_unit)
    }
    return any(model.model_instance_id in placed_model_ids for model in rules_unit.alive_models())


def _voice_of_command_orders_profile_for_unit(
    unit: UnitInstance,
) -> VoiceOfCommandOrdersProfile | None:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Voice of Command profile lookup requires UnitInstance.")
    order_abilities = tuple(
        ability
        for ability in unit.datasheet_abilities
        if _normalise_rule_token(ability.name) == _normalise_rule_token(ORDERS_ABILITY_NAME)
    )
    if len(order_abilities) > 1:
        raise GameLifecycleError("Voice of Command found multiple Orders abilities.")
    if not order_abilities:
        return None
    ability = order_abilities[0]
    if ability.rule_ir_payload is None:
        raise GameLifecycleError("Voice of Command Orders ability requires rule_ir_payload.")
    return _orders_profile_from_ability(ability)


def _orders_profile_from_ability(
    ability: DatasheetAbilityDescriptor,
) -> VoiceOfCommandOrdersProfile:
    if type(ability) is not DatasheetAbilityDescriptor:
        raise GameLifecycleError("Voice of Command Orders profile requires ability descriptor.")
    payload = _catalog_payload_object(ability.rule_ir_payload)
    if payload.get("profile_kind") != ORDERS_PROFILE_KIND:
        raise GameLifecycleError("Voice of Command Orders profile kind is unsupported.")
    return VoiceOfCommandOrdersProfile(
        orders_per_battle_round=_payload_positive_int(payload, key="orders_per_battle_round"),
        eligible_target_keywords=_payload_string_tuple(payload, key="eligible_target_keywords"),
        allowed_order_ids=tuple(
            _order_from_token(order_id)
            for order_id in _payload_string_tuple(payload, key="allowed_order_ids")
        ),
    )


def _record_voice_of_command_done(
    context: CommandPhaseStartResultContext,
    *,
    player_id: str,
) -> None:
    done_state = FactionRuleState(
        state_id=(
            f"astra-militarum:voice-of-command:done:{context.state.game_id}:"
            f"round-{context.state.battle_round:02d}:{player_id}:command"
        ),
        player_id=player_id,
        faction_id=ASTRA_MILITARUM_FACTION_ID,
        source_rule_id=SOURCE_RULE_ID,
        state_kind=VOICE_OF_COMMAND_DONE_STATE_KIND,
        setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
        request_id=context.request.request_id,
        result_id=context.result.result_id,
        payload=validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "active_player_id": context.active_player_id,
                "player_id": player_id,
                "selected_voice_of_command_option": "done",
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
            }
        ),
    )
    context.state.record_faction_rule_state(done_state)
    context.decisions.event_log.append(
        "astra_militarum_voice_of_command_done",
        {
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "phase": BattlePhase.COMMAND.value,
            "player_id": player_id,
            "faction_rule_state": validate_json_value(done_state.to_payload()),
            "source_rule_id": SOURCE_RULE_ID,
            "hook_id": HOOK_ID,
            "request_id": context.request.request_id,
            "result_id": context.result.result_id,
        },
    )


def _voice_of_command_done_this_command_phase(state: GameState, *, player_id: str) -> bool:
    requested_player_id = _validate_identifier("player_id", player_id)
    matching = tuple(
        stored
        for stored in state.faction_rule_states_for_player(
            player_id=requested_player_id,
            state_kind=VOICE_OF_COMMAND_DONE_STATE_KIND,
        )
        if _done_state_matches_current_command_phase(state, stored)
    )
    if len(matching) > 1:
        raise GameLifecycleError("Voice of Command found multiple done states.")
    return bool(matching)


def _done_state_matches_current_command_phase(
    state: GameState,
    stored: FactionRuleState,
) -> bool:
    payload = _payload_object(stored.payload)
    return (
        stored.source_rule_id == SOURCE_RULE_ID
        and payload.get("battle_round") == state.battle_round
        and payload.get("phase") == BattlePhase.COMMAND.value
        and payload.get("selected_voice_of_command_option") == "done"
    )


def _voice_of_command_issue_state(
    context: CommandPhaseStartResultContext,
    *,
    player_id: str,
    issue: VoiceOfCommandIssueOption,
) -> FactionRuleState:
    issued_count_after = issue.issued_count_before + 1
    return FactionRuleState(
        state_id=(
            f"astra-militarum:voice-of-command:issue:{context.state.game_id}:"
            f"round-{context.state.battle_round:02d}:{player_id}:"
            f"{issue.officer_unit.unit_instance_id}:{issued_count_after:02d}"
        ),
        player_id=player_id,
        faction_id=ASTRA_MILITARUM_FACTION_ID,
        source_rule_id=SOURCE_RULE_ID,
        state_kind=VOICE_OF_COMMAND_ISSUE_STATE_KIND,
        setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
        request_id=context.request.request_id,
        result_id=context.result.result_id,
        payload=validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "active_player_id": context.active_player_id,
                "player_id": player_id,
                "issuing_officer_unit_instance_id": issue.officer_unit.unit_instance_id,
                "ordered_rules_unit_instance_id": issue.target_rules_unit.unit_instance_id,
                "order_id": issue.order.value,
                "order_label": ORDER_LABELS[issue.order],
                "orders_issued_after": issued_count_after,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
                "selected_option_id": context.result.selected_option_id,
            }
        ),
    )


def _voice_of_command_order_effect(
    context: CommandPhaseStartResultContext,
    *,
    player_id: str,
    issue: VoiceOfCommandIssueOption,
    issue_state: FactionRuleState,
) -> PersistingEffect:
    target_id = issue.target_rules_unit.unit_instance_id
    issue_state_payload = _payload_object(issue_state.payload)
    issued_count_after = _payload_positive_int(issue_state_payload, key="orders_issued_after")
    expiration_battle_round = _next_own_turn_battle_round(context.state)
    expiration = EffectExpiration.start_turn(
        battle_round=expiration_battle_round,
        player_id=player_id,
    )
    return PersistingEffect(
        effect_id=(
            f"astra-militarum:voice-of-command:order:{context.state.game_id}:"
            f"round-{context.state.battle_round:02d}:{player_id}:"
            f"{issue.officer_unit.unit_instance_id}:{target_id}:"
            f"{issued_count_after:02d}"
        ),
        source_rule_id=SOURCE_RULE_ID,
        owner_player_id=player_id,
        target_unit_instance_ids=(target_id,),
        started_battle_round=context.state.battle_round,
        started_phase=BattlePhaseKind.COMMAND,
        expiration=expiration,
        effect_payload=validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "active_player_id": context.active_player_id,
                "player_id": player_id,
                "effect_kind": VOICE_OF_COMMAND_EFFECT_KIND,
                "issuing_officer_unit_instance_id": issue.officer_unit.unit_instance_id,
                "ordered_rules_unit_instance_id": target_id,
                "ordered_component_unit_instance_ids": list(
                    issue.target_rules_unit.component_unit_instance_ids
                ),
                "order_id": issue.order.value,
                "order_label": ORDER_LABELS[issue.order],
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
                "request_id": context.request.request_id,
                "result_id": context.result.result_id,
                "faction_rule_state_id": issue_state.state_id,
                "selected_option_id": context.result.selected_option_id,
                "expires_at_battle_round": expiration_battle_round,
            }
        ),
    )


def _issued_order_count_for_officer_this_round(
    state: GameState,
    *,
    player_id: str,
    officer_unit_instance_id: str,
) -> int:
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_officer_id = _validate_identifier(
        "officer_unit_instance_id",
        officer_unit_instance_id,
    )
    count = 0
    for stored in state.faction_rule_states_for_player(
        player_id=requested_player_id,
        state_kind=VOICE_OF_COMMAND_ISSUE_STATE_KIND,
    ):
        if stored.source_rule_id != SOURCE_RULE_ID:
            continue
        payload = _payload_object(stored.payload)
        if payload.get("battle_round") != state.battle_round:
            continue
        if payload.get("issuing_officer_unit_instance_id") != requested_officer_id:
            continue
        count += 1
    return count


def _active_voice_of_command_order_for_unit(
    state: GameState,
    *,
    unit_instance_id: str,
) -> VoiceOfCommandOrder | None:
    _validate_game_state(state)
    unit, _army = _unit_and_army_by_id(state, unit_instance_id=unit_instance_id)
    if not _unit_has_faction_keyword(unit, ASTRA_MILITARUM_FACTION_KEYWORD):
        return None
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    if _rules_unit_is_battle_shocked(state, rules_unit):
        return None
    effects = _active_voice_of_command_order_effects(
        state,
        target_rules_unit_instance_id=rules_unit.unit_instance_id,
    )
    if len(effects) == 0:
        return None
    if len(effects) != 1:
        raise GameLifecycleError("Voice of Command found multiple active Orders for a unit.")
    effect = effects[0]
    payload = _payload_object(effect.effect_payload)
    return _order_from_token(_payload_string(payload, key="order_id"))


def _active_voice_of_command_order_effects(
    state: GameState,
    *,
    target_rules_unit_instance_id: str,
) -> tuple[PersistingEffect, ...]:
    requested_target_id = _validate_identifier(
        "target_rules_unit_instance_id",
        target_rules_unit_instance_id,
    )
    matching: list[PersistingEffect] = []
    for effect in state.persisting_effects_for_unit(requested_target_id):
        if effect.source_rule_id != SOURCE_RULE_ID:
            continue
        payload = _payload_object(effect.effect_payload)
        if payload.get("effect_kind") != VOICE_OF_COMMAND_EFFECT_KIND:
            continue
        matching.append(effect)
    return tuple(sorted(matching, key=lambda effect: effect.effect_id))


def _clear_active_voice_of_command_order_effects(
    state: GameState,
    *,
    target_rules_unit_instance_id: str,
) -> tuple[PersistingEffect, ...]:
    effects = _active_voice_of_command_order_effects(
        state,
        target_rules_unit_instance_id=target_rules_unit_instance_id,
    )
    return state.remove_persisting_effects_by_id(tuple(effect.effect_id for effect in effects))


def _rules_unit_is_battle_shocked(state: GameState, rules_unit: RulesUnitView) -> bool:
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Voice of Command Battle-shock check requires rules unit.")
    shocked_ids = set(state.battle_shocked_unit_ids)
    return bool(
        shocked_ids & {rules_unit.unit_instance_id, *rules_unit.component_unit_instance_ids}
    )


def _improve_armour_save_option(option: SaveOption) -> SaveOption:
    if type(option) is not SaveOption:
        raise GameLifecycleError("Voice of Command save option modifier requires SaveOption.")
    if option.save_kind is not SaveKind.ARMOUR:
        return option
    improved_characteristic = _improve_save(option.characteristic_target_number)
    improvement = option.characteristic_target_number - improved_characteristic
    if improvement <= 0:
        return option
    return replace(
        option,
        characteristic_target_number=improved_characteristic,
        target_number=max(2, option.target_number - improvement),
        source_rule_ids=_source_ids_with_voice_of_command(option.source_rule_ids),
    )


def _improve_save(current: int) -> int:
    _validate_non_negative_int("save", current)
    if current <= 3:
        return current
    return current - 1


def _improve_leadership(current: int) -> int:
    _validate_non_negative_int("leadership", current)
    if current <= 4:
        return current
    return current - 1


def _improve_weapon_skill(skill: CharacteristicValue) -> CharacteristicValue:
    if type(skill) is not CharacteristicValue:
        raise GameLifecycleError("Voice of Command weapon skill requires CharacteristicValue.")
    if skill.characteristic is not Characteristic.WEAPON_SKILL:
        raise GameLifecycleError("Voice of Command weapon skill characteristic drift.")
    if not skill.is_numeric:
        raise GameLifecycleError("Voice of Command cannot improve non-numeric Weapon Skill.")
    return CharacteristicValue.from_raw(Characteristic.WEAPON_SKILL, _improve_skill(skill.final))


def _improve_ballistic_skill(skill: CharacteristicValue) -> CharacteristicValue:
    if type(skill) is not CharacteristicValue:
        raise GameLifecycleError("Voice of Command ballistic skill requires CharacteristicValue.")
    if skill.characteristic is not Characteristic.BALLISTIC_SKILL:
        raise GameLifecycleError("Voice of Command ballistic skill characteristic drift.")
    if not skill.is_numeric:
        raise GameLifecycleError("Voice of Command cannot improve non-numeric Ballistic Skill.")
    return CharacteristicValue.from_raw(
        Characteristic.BALLISTIC_SKILL,
        _improve_skill(skill.final),
    )


def _improve_skill(current: int) -> int:
    _validate_non_negative_int("skill", current)
    if current <= 2:
        return current
    return current - 1


def _attack_profile_with_plus_one(profile: AttackProfile) -> AttackProfile:
    if type(profile) is not AttackProfile:
        raise GameLifecycleError("Voice of Command attack profile requires AttackProfile.")
    if profile.fixed_attacks is not None:
        return AttackProfile.fixed(profile.fixed_attacks + 1)
    expression = profile.dice_expression
    if expression is None:
        raise GameLifecycleError("Voice of Command attack profile is missing dice expression.")
    return AttackProfile.dice(
        DiceExpression(
            quantity=expression.quantity,
            sides=expression.sides,
            modifier=expression.modifier + 1,
        )
    )


def _profile_has_rapid_fire(profile: WeaponProfile) -> bool:
    if type(profile) is not WeaponProfile:
        raise GameLifecycleError("Voice of Command Rapid Fire check requires WeaponProfile.")
    return WeaponKeyword.RAPID_FIRE in profile.keywords or any(
        ability.ability_kind is AbilityKind.RAPID_FIRE for ability in profile.abilities
    )


def _source_ids_with_voice_of_command(source_ids: tuple[str, ...]) -> tuple[str, ...]:
    if type(source_ids) is not tuple:
        raise GameLifecycleError("Voice of Command source IDs must be a tuple.")
    if SOURCE_RULE_ID in source_ids:
        return source_ids
    return tuple(sorted((*source_ids, SOURCE_RULE_ID)))


def _voice_issue_option_id(issue: VoiceOfCommandIssueOption) -> str:
    return (
        "astra_militarum:voice_of_command:"
        f"{issue.officer_unit.unit_instance_id}:"
        f"{issue.order.value}:"
        f"{issue.target_rules_unit.unit_instance_id}"
    )


def _rules_unit_label(rules_unit: RulesUnitView) -> str:
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Voice of Command label requires rules unit.")
    return " + ".join(component.unit.name for component in rules_unit.components)


def _astra_militarum_army_for_player(
    state: GameState,
    *,
    player_id: str,
) -> ArmyDefinition | None:
    _validate_game_state(state)
    requested_player_id = _validate_identifier("player_id", player_id)
    army = state.army_definition_for_player(requested_player_id)
    if army is None:
        return None
    if army.detachment_selection.faction_id == ASTRA_MILITARUM_FACTION_ID:
        return army
    return None


def _unit_and_army_by_id(
    state: GameState,
    *,
    unit_instance_id: str,
) -> tuple[UnitInstance, ArmyDefinition]:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return unit, army
    raise GameLifecycleError("Voice of Command unit_instance_id was not found.")


def _rules_unit_has_any_keyword(
    rules_unit: RulesUnitView,
    keywords: tuple[str, ...],
) -> bool:
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Voice of Command keyword lookup requires rules unit.")
    all_keywords = (*rules_unit.keywords, *rules_unit.faction_keywords)
    return any(_keyword_token_in(values=all_keywords, expected=keyword) for keyword in keywords)


def _rules_unit_has_faction_keyword(rules_unit: RulesUnitView, keyword: str) -> bool:
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Voice of Command faction keyword lookup requires rules unit.")
    return _keyword_token_in(values=rules_unit.faction_keywords, expected=keyword)


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Voice of Command keyword lookup requires UnitInstance.")
    return _keyword_token_in(values=unit.keywords, expected=keyword)


def _unit_has_faction_keyword(unit: UnitInstance, keyword: str) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Voice of Command faction keyword lookup requires UnitInstance.")
    return _keyword_token_in(values=unit.faction_keywords, expected=keyword)


def _keyword_token_in(*, values: tuple[str, ...], expected: str) -> bool:
    normalised_expected = _normalise_rule_token(expected)
    return any(_normalise_rule_token(value) == normalised_expected for value in values)


def _normalise_rule_token(value: str) -> str:
    return "".join(character for character in value.upper() if character.isalnum())


def _battlefield_state(state: GameState) -> BattlefieldRuntimeState:
    if state.battlefield_state is None:
        raise GameLifecycleError("Voice of Command requires battlefield_state.")
    return state.battlefield_state


def _next_own_turn_battle_round(state: GameState) -> int:
    _validate_game_state(state)
    return state.battle_round + 1


def _catalog_payload_object(payload: object) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Voice of Command Orders profile payload must be an object.")
    return cast(dict[str, JsonValue], payload)


def _payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Voice of Command payload must be an object.")
    return payload


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"Voice of Command payload {key} must be a string.")
    return value


def _payload_string_tuple(payload: dict[str, JsonValue], *, key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise GameLifecycleError(f"Voice of Command payload {key} must be a list.")
    items: list[str] = []
    for item in value:
        if type(item) is not str or not item.strip():
            raise GameLifecycleError(f"Voice of Command payload {key} values must be strings.")
        items.append(item.strip())
    return _validate_identifier_tuple(key, tuple(items), min_length=1)


def _payload_positive_int(payload: dict[str, JsonValue], *, key: str) -> int:
    value = payload.get(key)
    if type(value) is not int or value < 1:
        raise GameLifecycleError(f"Voice of Command payload {key} must be a positive integer.")
    return value


def _order_from_token(token: object) -> VoiceOfCommandOrder:
    if type(token) is VoiceOfCommandOrder:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Voice of Command order token must be a string.")
    try:
        return VoiceOfCommandOrder(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported Voice of Command order: {token}.") from exc


def _validate_order_tuple(value: object) -> tuple[VoiceOfCommandOrder, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("Voice of Command allowed_order_ids must be a tuple.")
    orders = tuple(_order_from_token(order) for order in cast(tuple[object, ...], value))
    if not orders:
        raise GameLifecycleError("Voice of Command allowed_order_ids must not be empty.")
    if len(set(orders)) != len(orders):
        raise GameLifecycleError("Voice of Command allowed_order_ids must not contain duplicates.")
    return tuple(order for order in ORDER_SEQUENCE if order in set(orders))


def _validate_identifier_tuple(
    field_name: str,
    values: tuple[str, ...],
    *,
    min_length: int = 0,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"Voice of Command {field_name} must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    for value in values:
        identifier = _validate_identifier(f"{field_name} value", value)
        normalised = _normalise_rule_token(identifier)
        if normalised in seen:
            raise GameLifecycleError(f"Voice of Command {field_name} must not contain duplicates.")
        seen.add(normalised)
        validated.append(identifier)
    if len(validated) < min_length:
        raise GameLifecycleError(
            f"Voice of Command {field_name} must contain at least {min_length} values."
        )
    return tuple(validated)


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Voice of Command {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Voice of Command {field_name} must not be empty.")
    return stripped


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"Voice of Command {field_name} must be an integer.")
    if value < 0:
        raise GameLifecycleError(f"Voice of Command {field_name} must not be negative.")
    return value


def _validate_game_state(state: object) -> None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Voice of Command requires GameState.")
