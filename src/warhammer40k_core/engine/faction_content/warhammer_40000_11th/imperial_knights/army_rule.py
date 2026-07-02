from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollSpec,
    DiceRollState,
    RerollComponentSelectionPolicy,
    RerollPermission,
)
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battle_formation_hooks import (
    SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE,
    BattleFormationHookBinding,
    BattleFormationRequestContext,
    BattleFormationResultContext,
)
from warhammer40k_core.engine.command_phase_start_hooks import CommandPhaseStartHookBinding
from warhammer40k_core.engine.command_points import (
    CommandPointGainStatus,
    CommandPointSourceKind,
)
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import EventLog, EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.faction_content.events import (
    RuntimeContentEventContext,
    RuntimeContentEventHandlerBinding,
    RuntimeContentEventResult,
    RuntimeContentEventSubscription,
)
from warhammer40k_core.engine.faction_rule_states import FactionRuleState
from warhammer40k_core.engine.fight_unit_selected_hooks import (
    FightUnitSelectedContext,
    FightUnitSelectedEffectGrant,
    FightUnitSelectedHookBinding,
)
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, SetupStep
from warhammer40k_core.engine.runtime_modifiers import (
    ChargeRollModifierBinding,
    ChargeRollModifierContext,
    MovementBudgetModifierBinding,
    MovementBudgetModifierContext,
    ObjectiveControlModifierBinding,
    ObjectiveControlModifierContext,
    UnitCharacteristicModifierBinding,
    UnitCharacteristicModifierContext,
)
from warhammer40k_core.engine.shooting_unit_selected_hooks import (
    ShootingUnitSelectedContext,
    ShootingUnitSelectedEffectGrant,
    ShootingUnitSelectedHookBinding,
)
from warhammer40k_core.engine.source_backed_rerolls import (
    source_backed_reroll_permission_effect_payload,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_destroyed_hooks import (
    UnitDestroyedContext,
    UnitDestroyedHookBinding,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance

from .bondsman import (
    ARMIGER_KEYWORD as ARMIGER_KEYWORD,
)
from .bondsman import (
    BONDSMAN_ABILITY_NAME as BONDSMAN_ABILITY_NAME,
)
from .bondsman import (
    BONDSMAN_APPLIED_EVENT as BONDSMAN_APPLIED_EVENT,
)
from .bondsman import (
    BONDSMAN_APPLIED_STATE_KIND as BONDSMAN_APPLIED_STATE_KIND,
)
from .bondsman import (
    BONDSMAN_DONE_EVENT as BONDSMAN_DONE_EVENT,
)
from .bondsman import (
    BONDSMAN_DONE_OPTION_ID as BONDSMAN_DONE_OPTION_ID,
)
from .bondsman import (
    BONDSMAN_DONE_STATE_KIND as BONDSMAN_DONE_STATE_KIND,
)
from .bondsman import (
    BONDSMAN_EFFECT_KIND as BONDSMAN_EFFECT_KIND,
)
from .bondsman import (
    BONDSMAN_HOOK_ID as BONDSMAN_HOOK_ID,
)
from .bondsman import (
    BONDSMAN_RANGE_INCHES as BONDSMAN_RANGE_INCHES,
)
from .bondsman import (
    BONDSMAN_SELECTION_KIND as BONDSMAN_SELECTION_KIND,
)
from .bondsman import (
    BONDSMAN_SOURCE_RULE_ID as BONDSMAN_SOURCE_RULE_ID,
)
from .bondsman import (
    active_bondsman_ability_id_for_model as active_bondsman_ability_id_for_model,
)
from .bondsman import (
    apply_bondsman_result as apply_bondsman_result,
)
from .bondsman import (
    bondsman_request as bondsman_request,
)
from .bondsman import (
    model_is_affected_by_bondsman as model_is_affected_by_bondsman,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

CONTRIBUTION_ID = "warhammer_40000_11th:imperial_knights:army_rule:code_chivalric"
HOOK_ID = CONTRIBUTION_ID
SETUP_HOOK_ID = f"{HOOK_ID}:oath-selection"
UNIT_DESTROYED_HOOK_ID = f"{HOOK_ID}:enemy-unit-destroyed"
END_TURN_EVENT_HANDLER_ID = f"{HOOK_ID}:end-turn"
END_BATTLE_ROUND_EVENT_HANDLER_ID = f"{HOOK_ID}:end-battle-round"
END_TURN_SUBSCRIPTION_ID = f"{HOOK_ID}:subscription:end-turn"
END_BATTLE_ROUND_SUBSCRIPTION_ID = f"{HOOK_ID}:subscription:end-battle-round"
SOURCE_RULE_ID = "phase17f:phase17e:imperial-knights:army-rule"
RULE_UPDATE_SOURCE = (
    "warhammer_40000_11th:imperial_knights:rules_update:code_chivalric_reap_a_great_tally"
)
IMPERIAL_KNIGHTS_FACTION_ID = "imperial-knights"
IMPERIAL_KNIGHTS_FACTION_KEYWORD = "IMPERIAL KNIGHTS"
CHARACTER_KEYWORD = "CHARACTER"
CODE_CHIVALRIC_ABILITY_NAME = "Code Chivalric"
CODE_CHIVALRIC_STATE_KIND = "imperial_knights_code_chivalric_oath"
CODE_CHIVALRIC_FULFILLED_STATE_KIND = "imperial_knights_code_chivalric_fulfilled"
CODE_CHIVALRIC_SELECTION_KIND = "imperial_knights_code_chivalric_oath"
CODE_CHIVALRIC_EFFECT_KIND = "imperial_knights_code_chivalric"
CODE_CHIVALRIC_ENEMY_DESTROYED_EVENT = "imperial_knights_code_chivalric_enemy_unit_destroyed"
CODE_CHIVALRIC_SELECTED_EVENT = "imperial_knights_code_chivalric_oath_selected"
CODE_CHIVALRIC_FULFILLED_EVENT = "imperial_knights_code_chivalric_oath_fulfilled"

_END_TURN_SUBSCRIPTION = RuntimeContentEventSubscription(
    subscription_id=END_TURN_SUBSCRIPTION_ID,
    source_rule_id=SOURCE_RULE_ID,
    trigger_kind=TimingTriggerKind.END_TURN,
    handler_id=END_TURN_EVENT_HANDLER_ID,
)
_END_BATTLE_ROUND_SUBSCRIPTION = RuntimeContentEventSubscription(
    subscription_id=END_BATTLE_ROUND_SUBSCRIPTION_ID,
    source_rule_id=SOURCE_RULE_ID,
    trigger_kind=TimingTriggerKind.END_BATTLE_ROUND,
    handler_id=END_BATTLE_ROUND_EVENT_HANDLER_ID,
)


class CodeChivalricDeed(StrEnum):
    LAY_LOW_THE_TYRANT = "lay_low_the_tyrant"
    RECLAIM_THE_REALM = "reclaim_the_realm"
    REAP_A_GREAT_TALLY = "reap_a_great_tally"


class CodeChivalricQuality(StrEnum):
    MARTIAL_VALOUR = "martial_valour"
    EAGER_FOR_THE_CHALLENGE = "eager_for_the_challenge"
    LEGACY_UNSULLIED = "legacy_unsullied"


class OathSelectionMode(StrEnum):
    SELECTED = "selected"
    ROLL_D6 = "roll_d6"


_DEED_LABELS = {
    CodeChivalricDeed.LAY_LOW_THE_TYRANT: "We vow to lay low the tyrant",
    CodeChivalricDeed.RECLAIM_THE_REALM: "We swear to reclaim the realm",
    CodeChivalricDeed.REAP_A_GREAT_TALLY: "We pledge to reap a great tally",
}
_QUALITY_LABELS = {
    CodeChivalricQuality.MARTIAL_VALOUR: "with our martial valour risen over all",
    CodeChivalricQuality.EAGER_FOR_THE_CHALLENGE: "and we are eager for the challenge",
    CodeChivalricQuality.LEGACY_UNSULLIED: "yet shall our legacy be unsullied",
}
_FIXED_DEEDS = (
    CodeChivalricDeed.LAY_LOW_THE_TYRANT,
    CodeChivalricDeed.RECLAIM_THE_REALM,
    CodeChivalricDeed.REAP_A_GREAT_TALLY,
)
_FIXED_QUALITIES = (
    CodeChivalricQuality.MARTIAL_VALOUR,
    CodeChivalricQuality.EAGER_FOR_THE_CHALLENGE,
    CodeChivalricQuality.LEGACY_UNSULLIED,
)


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        event_subscriptions=(_END_TURN_SUBSCRIPTION, _END_BATTLE_ROUND_SUBSCRIPTION),
        event_handler_bindings=(
            RuntimeContentEventHandlerBinding(
                handler_id=END_TURN_EVENT_HANDLER_ID,
                handler=resolve_code_chivalric_end_turn,
            ),
            RuntimeContentEventHandlerBinding(
                handler_id=END_BATTLE_ROUND_EVENT_HANDLER_ID,
                handler=resolve_code_chivalric_end_battle_round,
            ),
        ),
        battle_formation_hook_bindings=(
            BattleFormationHookBinding(
                hook_id=SETUP_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                request_handler=code_chivalric_oath_request,
                result_handler=apply_code_chivalric_oath_result,
            ),
        ),
        command_phase_start_hook_bindings=(
            CommandPhaseStartHookBinding(
                hook_id=BONDSMAN_HOOK_ID,
                source_id=BONDSMAN_SOURCE_RULE_ID,
                request_handler=bondsman_request,
                result_handler=apply_bondsman_result,
            ),
        ),
        unit_destroyed_hook_bindings=(
            UnitDestroyedHookBinding(
                hook_id=UNIT_DESTROYED_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=record_code_chivalric_enemy_unit_destroyed,
            ),
        ),
        shooting_unit_selected_hook_bindings=(
            ShootingUnitSelectedHookBinding(
                hook_id=f"{HOOK_ID}:martial-valour:shooting",
                source_id=SOURCE_RULE_ID,
                handler=code_chivalric_martial_valour_shooting_grants,
            ),
        ),
        fight_unit_selected_hook_bindings=(
            FightUnitSelectedHookBinding(
                hook_id=f"{HOOK_ID}:martial-valour:fight",
                source_id=SOURCE_RULE_ID,
                handler=code_chivalric_martial_valour_fight_grants,
            ),
        ),
        movement_budget_modifier_bindings=(
            MovementBudgetModifierBinding(
                modifier_id=f"{HOOK_ID}:eager:movement-budget",
                source_id=SOURCE_RULE_ID,
                handler=code_chivalric_eager_movement_modifier,
            ),
        ),
        charge_roll_modifier_bindings=(
            ChargeRollModifierBinding(
                modifier_id=f"{HOOK_ID}:eager:charge-roll",
                source_id=SOURCE_RULE_ID,
                handler=code_chivalric_eager_charge_modifier,
            ),
        ),
        objective_control_modifier_bindings=(
            ObjectiveControlModifierBinding(
                modifier_id=f"{HOOK_ID}:legacy:objective-control",
                source_id=SOURCE_RULE_ID,
                handler=code_chivalric_legacy_objective_control_modifier,
            ),
        ),
        unit_characteristic_modifier_bindings=(
            UnitCharacteristicModifierBinding(
                modifier_id=f"{HOOK_ID}:legacy:leadership",
                source_id=SOURCE_RULE_ID,
                handler=code_chivalric_legacy_leadership_modifier,
            ),
        ),
    )


def code_chivalric_oath_request(
    context: BattleFormationRequestContext,
) -> DecisionRequest | None:
    if type(context) is not BattleFormationRequestContext:
        raise GameLifecycleError("Code Chivalric oath selection requires request context.")
    for army in _imperial_knights_armies(context.state):
        if selected_oath_state_for_player(context.state, player_id=army.player_id) is not None:
            continue
        options = _code_chivalric_oath_options(state=context.state, army=army)
        if not options:
            continue
        return DecisionRequest(
            request_id=context.state.next_decision_request_id(),
            decision_type=SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE,
            actor_id=army.player_id,
            payload=validate_json_value(
                {
                    "game_id": context.state.game_id,
                    "setup_step": SetupStep.DECLARE_BATTLE_FORMATIONS.value,
                    "player_id": army.player_id,
                    "faction_id": IMPERIAL_KNIGHTS_FACTION_ID,
                    "source_rule_id": SOURCE_RULE_ID,
                    "hook_id": SETUP_HOOK_ID,
                    "state_kind": CODE_CHIVALRIC_STATE_KIND,
                    "submission_kind": CODE_CHIVALRIC_SELECTION_KIND,
                    "eligible_code_chivalric_unit_instance_ids": list(
                        _eligible_code_chivalric_unit_ids(army)
                    ),
                    "eligible_lay_low_target_model_instance_ids": [
                        target_model.model_instance_id
                        for target_model, _target_unit in _eligible_lay_low_targets(
                            context.state,
                            player_id=army.player_id,
                        )
                    ],
                }
            ),
            options=options,
        )
    return None


def apply_code_chivalric_oath_result(context: BattleFormationResultContext) -> bool:
    if type(context) is not BattleFormationResultContext:
        raise GameLifecycleError("Code Chivalric oath selection requires result context.")
    if context.request.decision_type != SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE:
        return False
    request_payload = _payload_object(context.request.payload)
    if request_payload.get("hook_id") != SETUP_HOOK_ID:
        return False
    context.result.validate_for_request(context.request)
    if context.result.actor_id is None:
        raise GameLifecycleError("Code Chivalric oath selection requires an actor.")
    player_id = context.result.actor_id
    army = _imperial_knights_army_for_player(context.state, player_id=player_id)
    if army is None:
        raise GameLifecycleError("Code Chivalric actor does not own Imperial Knights.")
    if selected_oath_state_for_player(context.state, player_id=player_id) is not None:
        raise GameLifecycleError("Code Chivalric oath is already selected.")
    payload = _payload_object(context.result.payload)
    _validate_oath_payload_context(
        context=context,
        request_payload=request_payload,
        payload=payload,
    )

    deed_mode = _selection_mode_from_token(_payload_string(payload, key="deed_selection_mode"))
    quality_mode = _selection_mode_from_token(
        _payload_string(payload, key="quality_selection_mode")
    )
    deed_roll_payload: JsonValue = None
    quality_roll_payload: JsonValue = None
    if deed_mode is OathSelectionMode.ROLL_D6:
        deed_roll = _roll_code_chivalric_d6(
            context=context,
            player_id=player_id,
            reason="Code Chivalric deed determination",
            roll_type="imperial_knights_code_chivalric_deed",
        )
        deed = _deed_from_d6(deed_roll.current_total)
        deed_roll_payload = validate_json_value(deed_roll.original_result.to_payload())
    else:
        deed = _deed_from_token(_payload_string(payload, key="deed_id"))

    if quality_mode is OathSelectionMode.ROLL_D6:
        quality_roll = _roll_code_chivalric_d6(
            context=context,
            player_id=player_id,
            reason="Code Chivalric quality determination",
            roll_type="imperial_knights_code_chivalric_quality",
        )
        quality = _quality_from_d6(quality_roll.current_total)
        quality_roll_payload = validate_json_value(quality_roll.original_result.to_payload())
    else:
        quality = _quality_from_token(_payload_string(payload, key="quality_id"))

    target_model_id = _payload_optional_string(payload, key="lay_low_target_model_instance_id")
    target_unit_id = _payload_optional_string(payload, key="lay_low_target_unit_instance_id")
    if deed is CodeChivalricDeed.LAY_LOW_THE_TYRANT:
        if target_model_id is None or target_unit_id is None:
            raise GameLifecycleError("Code Chivalric Lay Low the Tyrant requires a target.")
        _assert_lay_low_target_valid(
            context.state,
            player_id=player_id,
            target_model_instance_id=target_model_id,
            target_unit_instance_id=target_unit_id,
        )
    elif target_model_id is not None or target_unit_id is not None:
        if target_model_id is None or target_unit_id is None:
            raise GameLifecycleError("Code Chivalric Lay Low target payload is incomplete.")
        _assert_lay_low_target_valid(
            context.state,
            player_id=player_id,
            target_model_instance_id=_validate_identifier(
                "lay_low_target_model_instance_id",
                target_model_id,
            ),
            target_unit_instance_id=_validate_identifier(
                "lay_low_target_unit_instance_id",
                target_unit_id,
            ),
        )

    random_selection = (
        deed_mode is OathSelectionMode.ROLL_D6 or quality_mode is OathSelectionMode.ROLL_D6
    )
    reward_amount = 3 if random_selection else 2
    state_record = FactionRuleState(
        state_id=f"{HOOK_ID}:{player_id}:oath",
        player_id=player_id,
        faction_id=IMPERIAL_KNIGHTS_FACTION_ID,
        source_rule_id=SOURCE_RULE_ID,
        state_kind=CODE_CHIVALRIC_STATE_KIND,
        setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
        request_id=context.request.request_id,
        result_id=context.result.result_id,
        payload=validate_json_value(
            {
                "selection_kind": CODE_CHIVALRIC_SELECTION_KIND,
                "effect_kind": CODE_CHIVALRIC_EFFECT_KIND,
                "game_id": context.state.game_id,
                "setup_step": SetupStep.DECLARE_BATTLE_FORMATIONS.value,
                "player_id": player_id,
                "faction_id": IMPERIAL_KNIGHTS_FACTION_ID,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": SETUP_HOOK_ID,
                "selected_option_id": context.result.selected_option_id,
                "deed_selection_mode": deed_mode.value,
                "selected_deed_id": deed.value,
                "selected_deed_label": _DEED_LABELS[deed],
                "deed_roll": deed_roll_payload,
                "quality_selection_mode": quality_mode.value,
                "selected_quality_id": quality.value,
                "selected_quality_label": _QUALITY_LABELS[quality],
                "quality_roll": quality_roll_payload,
                "lay_low_target_model_instance_id": target_model_id,
                "lay_low_target_unit_instance_id": target_unit_id,
                "random_selection": random_selection,
                "command_point_reward_amount": reward_amount,
                "rules_update_sources": [RULE_UPDATE_SOURCE],
            }
        ),
    )
    context.state.record_faction_rule_state(state_record)
    context.decisions.event_log.append(
        CODE_CHIVALRIC_SELECTED_EVENT,
        {
            "game_id": context.state.game_id,
            "setup_step": SetupStep.DECLARE_BATTLE_FORMATIONS.value,
            "player_id": player_id,
            "source_rule_id": SOURCE_RULE_ID,
            "hook_id": SETUP_HOOK_ID,
            "faction_rule_state": validate_json_value(state_record.to_payload()),
        },
    )
    return True


def record_code_chivalric_enemy_unit_destroyed(context: UnitDestroyedContext) -> None:
    if type(context) is not UnitDestroyedContext:
        raise GameLifecycleError("Code Chivalric unit-destroyed hook requires context.")
    army = _imperial_knights_army_for_player(
        context.state,
        player_id=context.destroying_player_id,
    )
    if army is None:
        return
    source_id = (
        f"{SOURCE_RULE_ID}:enemy-unit-destroyed:"
        f"{context.model_destroyed_event_id}:player-{army.player_id}"
    )
    if _event_with_source_id_exists(context.decisions.event_log, source_id=source_id):
        return
    context.decisions.event_log.append(
        CODE_CHIVALRIC_ENEMY_DESTROYED_EVENT,
        {
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "phase": context.completed_phase.value,
            "active_player_id": _active_player_id(context.state),
            "player_id": army.player_id,
            "source_rule_id": source_id,
            "hook_id": UNIT_DESTROYED_HOOK_ID,
            "enemy_player_id": context.destroyed_player_id,
            "enemy_unit_instance_id": context.destroyed_unit_instance_id,
            "model_destroyed_event_id": context.model_destroyed_event_id,
            "model_destroyed_payload": validate_json_value(context.model_destroyed_payload),
        },
    )


def resolve_code_chivalric_end_turn(
    context: RuntimeContentEventContext,
) -> RuntimeContentEventResult:
    if type(context) is not RuntimeContentEventContext:
        raise GameLifecycleError("Code Chivalric end-turn handler requires context.")
    replay_payload = _resolve_code_chivalric_timing(
        context=context,
        trigger_kind=TimingTriggerKind.END_TURN,
    )
    return RuntimeContentEventResult.applied(
        _END_TURN_SUBSCRIPTION,
        replay_payload=replay_payload,
    )


def resolve_code_chivalric_end_battle_round(
    context: RuntimeContentEventContext,
) -> RuntimeContentEventResult:
    if type(context) is not RuntimeContentEventContext:
        raise GameLifecycleError("Code Chivalric end-battle-round handler requires context.")
    replay_payload = _resolve_code_chivalric_timing(
        context=context,
        trigger_kind=TimingTriggerKind.END_BATTLE_ROUND,
    )
    return RuntimeContentEventResult.applied(
        _END_BATTLE_ROUND_SUBSCRIPTION,
        replay_payload=replay_payload,
    )


def code_chivalric_eager_movement_modifier(context: MovementBudgetModifierContext) -> float:
    if type(context) is not MovementBudgetModifierContext:
        raise GameLifecycleError("Code Chivalric movement modifier requires context.")
    if not unit_has_code_chivalric_quality(
        context.state,
        unit_instance_id=context.unit_instance_id,
        quality=CodeChivalricQuality.EAGER_FOR_THE_CHALLENGE,
    ):
        return context.current_movement_inches
    return context.current_movement_inches + 2.0


def code_chivalric_eager_charge_modifier(
    context: ChargeRollModifierContext,
) -> tuple[RollModifier, ...]:
    if type(context) is not ChargeRollModifierContext:
        raise GameLifecycleError("Code Chivalric charge modifier requires context.")
    if not unit_has_code_chivalric_quality(
        context.state,
        unit_instance_id=context.unit_instance_id,
        quality=CodeChivalricQuality.EAGER_FOR_THE_CHALLENGE,
    ):
        return context.current_roll_modifiers
    return (
        *context.current_roll_modifiers,
        RollModifier(
            modifier_id=f"{HOOK_ID}:eager:charge-roll:{context.unit_instance_id}",
            source_id=SOURCE_RULE_ID,
            operand=1,
        ),
    )


def code_chivalric_legacy_objective_control_modifier(
    context: ObjectiveControlModifierContext,
) -> int:
    if type(context) is not ObjectiveControlModifierContext:
        raise GameLifecycleError("Code Chivalric OC modifier requires context.")
    if not unit_has_code_chivalric_quality(
        context.state,
        unit_instance_id=context.unit_instance_id,
        quality=CodeChivalricQuality.LEGACY_UNSULLIED,
    ):
        return context.current_objective_control
    return context.current_objective_control + 2


def code_chivalric_legacy_leadership_modifier(
    context: UnitCharacteristicModifierContext,
) -> int:
    if type(context) is not UnitCharacteristicModifierContext:
        raise GameLifecycleError("Code Chivalric Leadership modifier requires context.")
    if context.characteristic is not Characteristic.LEADERSHIP:
        return context.current_value
    if not unit_has_code_chivalric_quality(
        context.state,
        unit_instance_id=context.unit_instance_id,
        quality=CodeChivalricQuality.LEGACY_UNSULLIED,
    ):
        return context.current_value
    return max(1, context.current_value - 1)


def code_chivalric_martial_valour_shooting_grants(
    context: ShootingUnitSelectedContext,
) -> tuple[ShootingUnitSelectedEffectGrant, ...]:
    if type(context) is not ShootingUnitSelectedContext:
        raise GameLifecycleError("Code Chivalric shooting grant requires context.")
    if not unit_has_code_chivalric_quality(
        context.state,
        unit_instance_id=context.unit_instance_id,
        quality=CodeChivalricQuality.MARTIAL_VALOUR,
    ):
        return ()
    effects = _martial_valour_reroll_effects(
        state=context.state,
        player_id=context.player_id,
        unit_instance_id=context.unit_instance_id,
        selection_result_id=context.result_id,
        started_phase=BattlePhaseKind.SHOOTING,
        expiration=EffectExpiration.end_phase(
            battle_round=context.battle_round,
            phase=BattlePhaseKind.SHOOTING,
            player_id=context.player_id,
        ),
    )
    return tuple(
        ShootingUnitSelectedEffectGrant(
            hook_id=f"{HOOK_ID}:martial-valour:shooting",
            source_id=SOURCE_RULE_ID,
            unit_instance_id=context.unit_instance_id,
            persisting_effect=effect,
            replay_payload=_martial_valour_replay_payload(
                phase=BattlePhase.SHOOTING,
                player_id=context.player_id,
                unit_instance_id=context.unit_instance_id,
                selection_result_id=context.result_id,
            ),
        )
        for effect in effects
    )


def code_chivalric_martial_valour_fight_grants(
    context: FightUnitSelectedContext,
) -> tuple[FightUnitSelectedEffectGrant, ...]:
    if type(context) is not FightUnitSelectedContext:
        raise GameLifecycleError("Code Chivalric fight grant requires context.")
    if not unit_has_code_chivalric_quality(
        context.state,
        unit_instance_id=context.unit_instance_id,
        quality=CodeChivalricQuality.MARTIAL_VALOUR,
    ):
        return ()
    effects = _martial_valour_reroll_effects(
        state=context.state,
        player_id=context.player_id,
        unit_instance_id=context.unit_instance_id,
        selection_result_id=context.result_id,
        started_phase=BattlePhaseKind.FIGHT,
        expiration=EffectExpiration.end_phase(
            battle_round=context.battle_round,
            phase=BattlePhaseKind.FIGHT,
            player_id=context.player_id,
        ),
    )
    return tuple(
        FightUnitSelectedEffectGrant(
            hook_id=f"{HOOK_ID}:martial-valour:fight",
            source_id=SOURCE_RULE_ID,
            unit_instance_id=context.unit_instance_id,
            persisting_effect=effect,
            replay_payload=_martial_valour_replay_payload(
                phase=BattlePhase.FIGHT,
                player_id=context.player_id,
                unit_instance_id=context.unit_instance_id,
                selection_result_id=context.result_id,
            ),
        )
        for effect in effects
    )


def selected_oath_state_for_player(
    state: GameState,
    *,
    player_id: str,
) -> FactionRuleState | None:
    _validate_game_state(state)
    states = state.faction_rule_states_for_player(
        player_id=player_id,
        state_kind=CODE_CHIVALRIC_STATE_KIND,
    )
    if len(states) > 1:
        raise GameLifecycleError("Code Chivalric lookup found multiple selected oaths.")
    return states[0] if states else None


def selected_deed_for_player(
    state: GameState,
    *,
    player_id: str,
) -> CodeChivalricDeed | None:
    state_record = selected_oath_state_for_player(state, player_id=player_id)
    if state_record is None:
        return None
    payload = _payload_object(state_record.payload)
    return _deed_from_token(_payload_string(payload, key="selected_deed_id"))


def selected_quality_for_player(
    state: GameState,
    *,
    player_id: str,
) -> CodeChivalricQuality | None:
    state_record = selected_oath_state_for_player(state, player_id=player_id)
    if state_record is None:
        return None
    payload = _payload_object(state_record.payload)
    return _quality_from_token(_payload_string(payload, key="selected_quality_id"))


def army_is_honoured(state: GameState, *, player_id: str) -> bool:
    _validate_game_state(state)
    states = state.faction_rule_states_for_player(
        player_id=player_id,
        state_kind=CODE_CHIVALRIC_FULFILLED_STATE_KIND,
    )
    if len(states) > 1:
        raise GameLifecycleError("Code Chivalric lookup found multiple fulfilment states.")
    return bool(states)


def unit_has_code_chivalric_quality(
    state: GameState,
    *,
    unit_instance_id: str,
    quality: CodeChivalricQuality,
) -> bool:
    _validate_game_state(state)
    resolved_quality = _quality_from_token(quality)
    unit, army = _unit_and_army_by_id(state, unit_instance_id=unit_instance_id)
    if not _unit_has_code_chivalric(unit):
        return False
    return selected_quality_for_player(state, player_id=army.player_id) is resolved_quality


def _resolve_code_chivalric_timing(
    *,
    context: RuntimeContentEventContext,
    trigger_kind: TimingTriggerKind,
) -> JsonValue:
    if context.event.trigger_kind is not trigger_kind:
        raise GameLifecycleError("Code Chivalric timing trigger drift.")
    player_id = context.event.player_id
    army = _imperial_knights_army_for_player(context.state, player_id=player_id)
    if army is None:
        return {"resolution": "ignored_non_imperial_knights_player", "player_id": player_id}
    if army_is_honoured(context.state, player_id=player_id):
        return {"resolution": "already_honoured", "player_id": player_id}
    oath_state = selected_oath_state_for_player(context.state, player_id=player_id)
    if oath_state is None:
        return {"resolution": "no_selected_oath", "player_id": player_id}
    deed = _deed_from_token(
        _payload_string(_payload_object(oath_state.payload), key="selected_deed_id")
    )
    evidence = _deed_completion_evidence(
        context=context,
        player_id=player_id,
        deed=deed,
        trigger_kind=trigger_kind,
    )
    if evidence is None:
        return {
            "resolution": "deed_not_completed",
            "player_id": player_id,
            "deed_id": deed.value,
            "trigger_kind": trigger_kind.value,
        }
    return _fulfil_code_chivalric_oath(
        context=context,
        oath_state=oath_state,
        player_id=player_id,
        deed=deed,
        evidence=evidence,
    )


def _deed_completion_evidence(
    *,
    context: RuntimeContentEventContext,
    player_id: str,
    deed: CodeChivalricDeed,
    trigger_kind: TimingTriggerKind,
) -> dict[str, JsonValue] | None:
    if deed is CodeChivalricDeed.LAY_LOW_THE_TYRANT:
        if trigger_kind is not TimingTriggerKind.END_TURN:
            return None
        return _lay_low_completion_evidence(context=context, player_id=player_id)
    if deed is CodeChivalricDeed.RECLAIM_THE_REALM:
        if trigger_kind is not TimingTriggerKind.END_TURN:
            return None
        return _reclaim_completion_evidence(context=context, player_id=player_id)
    if deed is CodeChivalricDeed.REAP_A_GREAT_TALLY:
        if trigger_kind is not TimingTriggerKind.END_BATTLE_ROUND:
            return None
        return _tally_completion_evidence(context=context, player_id=player_id)
    raise GameLifecycleError("Unsupported Code Chivalric deed.")


def _lay_low_completion_evidence(
    *,
    context: RuntimeContentEventContext,
    player_id: str,
) -> dict[str, JsonValue] | None:
    oath_payload = _payload_object(_require_oath_state(context.state, player_id=player_id).payload)
    target_model_id = _payload_optional_string(
        oath_payload,
        key="lay_low_target_model_instance_id",
    )
    if target_model_id is None:
        raise GameLifecycleError("Code Chivalric Lay Low oath missing target model.")
    record = _model_destroyed_event(
        context.decisions.event_log,
        game_id=context.state.game_id,
        model_instance_id=target_model_id,
    )
    if record is None:
        return None
    return {
        "deed_completion_kind": CodeChivalricDeed.LAY_LOW_THE_TYRANT.value,
        "target_model_instance_id": target_model_id,
        "model_destroyed_event_id": record.event_id,
        "model_destroyed_payload": record.payload,
    }


def _reclaim_completion_evidence(
    *,
    context: RuntimeContentEventContext,
    player_id: str,
) -> dict[str, JsonValue] | None:
    active_player_id = context.event.active_player_id
    if active_player_id is None:
        raise GameLifecycleError("Code Chivalric Reclaim requires active_player_id.")
    if active_player_id == player_id:
        return None
    current_phase = context.state.current_battle_phase
    if current_phase is None:
        raise GameLifecycleError("Code Chivalric Reclaim requires a current phase.")
    record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            context.state,
            timing=ObjectiveControlTiming.TURN_END,
            phase=current_phase,
            ruleset_descriptor=context.ruleset_descriptor,
            runtime_modifier_registry=context.runtime_modifier_registry,
        )
    )
    player_objectives = sum(
        1 for result in record.results if result.controlled_by_player_id == player_id
    )
    opponent_objectives = sum(
        1
        for result in record.results
        if result.controlled_by_player_id is not None
        and result.controlled_by_player_id != player_id
    )
    if player_objectives <= opponent_objectives:
        return None
    return {
        "deed_completion_kind": CodeChivalricDeed.RECLAIM_THE_REALM.value,
        "player_controlled_objective_count": player_objectives,
        "opponent_controlled_objective_count": opponent_objectives,
        "objective_control_record": validate_json_value(record.to_payload()),
    }


def _tally_completion_evidence(
    *,
    context: RuntimeContentEventContext,
    player_id: str,
) -> dict[str, JsonValue] | None:
    destroyed_events = _enemy_unit_destroyed_event_ids_this_battle_round(
        state=context.state,
        event_log=context.decisions.event_log,
        player_id=player_id,
    )
    destroyed_count = len(destroyed_events)
    battle_round_number = context.state.battle_round
    if destroyed_count <= battle_round_number:
        return None
    return {
        "deed_completion_kind": CodeChivalricDeed.REAP_A_GREAT_TALLY.value,
        "enemy_units_destroyed_this_battle_round": destroyed_count,
        "battle_round_number": battle_round_number,
        "destroyed_event_ids": list(destroyed_events),
        "rules_update_source": RULE_UPDATE_SOURCE,
    }


def _fulfil_code_chivalric_oath(
    *,
    context: RuntimeContentEventContext,
    oath_state: FactionRuleState,
    player_id: str,
    deed: CodeChivalricDeed,
    evidence: dict[str, JsonValue],
) -> JsonValue:
    oath_payload = _payload_object(oath_state.payload)
    reward_amount = _payload_int(oath_payload, key="command_point_reward_amount")
    if reward_amount not in {2, 3}:
        raise GameLifecycleError("Code Chivalric CP reward amount drift.")
    source_id = f"{SOURCE_RULE_ID}:oath-fulfilled:{player_id}"
    gain = context.state.gain_command_points(
        player_id=player_id,
        amount=reward_amount,
        source_id=source_id,
        source_kind=CommandPointSourceKind.OTHER,
        cap_exempt=True,
    )
    if gain.status is not CommandPointGainStatus.APPLIED:
        raise GameLifecycleError("Code Chivalric CP reward must not be capped.")
    context.decisions.event_log.append("command_points_gained", gain.to_payload())
    fulfilled_state = FactionRuleState(
        state_id=f"{HOOK_ID}:{player_id}:fulfilled",
        player_id=player_id,
        faction_id=IMPERIAL_KNIGHTS_FACTION_ID,
        source_rule_id=SOURCE_RULE_ID,
        state_kind=CODE_CHIVALRIC_FULFILLED_STATE_KIND,
        setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
        request_id=oath_state.request_id,
        result_id=oath_state.result_id,
        payload=validate_json_value(
            {
                "selection_kind": CODE_CHIVALRIC_SELECTION_KIND,
                "effect_kind": CODE_CHIVALRIC_EFFECT_KIND,
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "player_id": player_id,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
                "selected_deed_id": deed.value,
                "selected_quality_id": _payload_string(oath_payload, key="selected_quality_id"),
                "command_point_reward_amount": reward_amount,
                "command_point_gain": validate_json_value(gain.to_payload()),
                "evidence": evidence,
                "runtime_event_id": context.event.event_id,
                "trigger_kind": context.event.trigger_kind.value,
                "rules_update_sources": [RULE_UPDATE_SOURCE],
            }
        ),
    )
    context.state.record_faction_rule_state(fulfilled_state)
    context.decisions.event_log.append(
        CODE_CHIVALRIC_FULFILLED_EVENT,
        {
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "player_id": player_id,
            "source_rule_id": SOURCE_RULE_ID,
            "hook_id": HOOK_ID,
            "selected_deed_id": deed.value,
            "command_point_gain": validate_json_value(gain.to_payload()),
            "faction_rule_state": validate_json_value(fulfilled_state.to_payload()),
            "evidence": evidence,
        },
    )
    return {
        "resolution": "oath_fulfilled",
        "player_id": player_id,
        "deed_id": deed.value,
        "command_point_reward_amount": reward_amount,
        "fulfilled_state_id": fulfilled_state.state_id,
    }


def _code_chivalric_oath_options(
    *,
    state: GameState,
    army: ArmyDefinition,
) -> tuple[DecisionOption, ...]:
    target_pairs = _eligible_lay_low_targets(state, player_id=army.player_id)
    options: list[DecisionOption] = []
    deed_choices: tuple[CodeChivalricDeed | None, ...] = (*_FIXED_DEEDS, None)
    quality_choices: tuple[CodeChivalricQuality | None, ...] = (*_FIXED_QUALITIES, None)
    for deed in deed_choices:
        requires_target = deed is None or deed is CodeChivalricDeed.LAY_LOW_THE_TYRANT
        for quality in quality_choices:
            if requires_target:
                for target_model, target_unit in target_pairs:
                    options.append(
                        _code_chivalric_oath_option(
                            player_id=army.player_id,
                            deed=deed,
                            quality=quality,
                            target_model=target_model,
                            target_unit=target_unit,
                        )
                    )
                continue
            options.append(
                _code_chivalric_oath_option(
                    player_id=army.player_id,
                    deed=deed,
                    quality=quality,
                    target_model=None,
                    target_unit=None,
                )
            )
    return tuple(options)


def _code_chivalric_oath_option(
    *,
    player_id: str,
    deed: CodeChivalricDeed | None,
    quality: CodeChivalricQuality | None,
    target_model: ModelInstance | None,
    target_unit: UnitInstance | None,
) -> DecisionOption:
    deed_mode = OathSelectionMode.ROLL_D6 if deed is None else OathSelectionMode.SELECTED
    quality_mode = OathSelectionMode.ROLL_D6 if quality is None else OathSelectionMode.SELECTED
    deed_id = None if deed is None else deed.value
    quality_id = None if quality is None else quality.value
    target_model_id = None if target_model is None else target_model.model_instance_id
    target_unit_id = None if target_unit is None else target_unit.unit_instance_id
    option_id = (
        f"{HOOK_ID}:player:{player_id}:deed:{deed_mode.value}:{deed_id}:"
        f"quality:{quality_mode.value}:{quality_id}:target:{target_model_id}"
    )
    label_parts = [
        "Code Chivalric",
        "roll deed" if deed is None else _DEED_LABELS[deed],
        "roll quality" if quality is None else _QUALITY_LABELS[quality],
    ]
    if target_model is not None:
        label_parts.append(f"Lay Low target {target_model.name}")
    return DecisionOption(
        option_id=option_id,
        label=" | ".join(label_parts),
        payload=validate_json_value(
            {
                "submission_kind": CODE_CHIVALRIC_SELECTION_KIND,
                "player_id": player_id,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": SETUP_HOOK_ID,
                "deed_selection_mode": deed_mode.value,
                "deed_id": deed_id,
                "quality_selection_mode": quality_mode.value,
                "quality_id": quality_id,
                "lay_low_target_model_instance_id": target_model_id,
                "lay_low_target_unit_instance_id": target_unit_id,
            }
        ),
    )


def _roll_code_chivalric_d6(
    *,
    context: BattleFormationResultContext,
    player_id: str,
    reason: str,
    roll_type: str,
) -> DiceRollState:
    return DiceRollManager(context.state.game_id, event_log=context.decisions.event_log).roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason=reason,
            roll_type=roll_type,
            actor_id=player_id,
        )
    )


def _martial_valour_reroll_effects(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
    selection_result_id: str,
    started_phase: BattlePhaseKind,
    expiration: EffectExpiration,
) -> tuple[PersistingEffect, PersistingEffect]:
    return (
        _martial_valour_reroll_effect(
            state=state,
            player_id=player_id,
            unit_instance_id=unit_instance_id,
            selection_result_id=selection_result_id,
            started_phase=started_phase,
            expiration=expiration,
            roll_kind="hit",
            timing_window="attack_sequence.hit",
            eligible_roll_type="attack_sequence.hit",
        ),
        _martial_valour_reroll_effect(
            state=state,
            player_id=player_id,
            unit_instance_id=unit_instance_id,
            selection_result_id=selection_result_id,
            started_phase=started_phase,
            expiration=expiration,
            roll_kind="wound",
            timing_window="attack_sequence.wound",
            eligible_roll_type="attack_sequence.wound",
        ),
    )


def _martial_valour_reroll_effect(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
    selection_result_id: str,
    started_phase: BattlePhaseKind,
    expiration: EffectExpiration,
    roll_kind: str,
    timing_window: str,
    eligible_roll_type: str,
) -> PersistingEffect:
    source_payload = validate_json_value(
        {
            "effect_kind": "imperial_knights_martial_valour_reroll",
            "roll_kind": roll_kind,
            "player_id": player_id,
            "unit_instance_id": unit_instance_id,
            "battle_round": state.battle_round,
            "selection_result_id": selection_result_id,
            "source_rule_id": SOURCE_RULE_ID,
            "hook_id": HOOK_ID,
        }
    )
    permission = RerollPermission(
        source_id=(
            f"{SOURCE_RULE_ID}:martial-valour:{roll_kind}:{unit_instance_id}:{selection_result_id}"
        ),
        timing_window=timing_window,
        owning_player_id=player_id,
        eligible_roll_type=eligible_roll_type,
        component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
    )
    return PersistingEffect(
        effect_id=f"{HOOK_ID}:{unit_instance_id}:{selection_result_id}:{roll_kind}-reroll",
        source_rule_id=SOURCE_RULE_ID,
        owner_player_id=player_id,
        target_unit_instance_ids=(unit_instance_id,),
        started_battle_round=state.battle_round,
        started_phase=started_phase,
        expiration=expiration,
        effect_payload=source_backed_reroll_permission_effect_payload(
            target_unit_instance_ids=(unit_instance_id,),
            permission=permission,
            source_payload=source_payload,
        ),
    )


def _martial_valour_replay_payload(
    *,
    phase: BattlePhase,
    player_id: str,
    unit_instance_id: str,
    selection_result_id: str,
) -> JsonValue:
    return validate_json_value(
        {
            "effect_kind": "imperial_knights_martial_valour_rerolls",
            "phase": phase.value,
            "player_id": player_id,
            "unit_instance_id": unit_instance_id,
            "selection_result_id": selection_result_id,
            "source_rule_id": SOURCE_RULE_ID,
            "hook_id": HOOK_ID,
        }
    )


def _enemy_unit_destroyed_event_ids_this_battle_round(
    *,
    state: GameState,
    event_log: EventLog,
    player_id: str,
) -> tuple[str, ...]:
    event_ids: set[str] = set()
    for record in event_log.records:
        if record.event_type != CODE_CHIVALRIC_ENEMY_DESTROYED_EVENT:
            continue
        payload = _payload_object(record.payload)
        if payload.get("game_id") != state.game_id:
            continue
        if payload.get("battle_round") != state.battle_round:
            continue
        if payload.get("player_id") != player_id:
            continue
        event_ids.add(_payload_string(payload, key="model_destroyed_event_id"))
    for event_id, payload in _unit_destruction_completion_events_for_current_phase(
        state=state,
        event_log=event_log,
    ):
        if _payload_string(payload, key="destroying_player_id") != player_id:
            continue
        target_unit_id = _payload_string(payload, key="target_unit_instance_id")
        if _unit_owner_player_id(state, unit_instance_id=target_unit_id) == player_id:
            continue
        event_ids.add(event_id)
    return tuple(sorted(event_ids))


def _unit_destruction_completion_events_for_current_phase(
    *,
    state: GameState,
    event_log: EventLog,
) -> tuple[tuple[str, dict[str, JsonValue]], ...]:
    if state.battlefield_state is None:
        return ()
    completed_phase = state.current_battle_phase
    if completed_phase is None:
        raise GameLifecycleError("Code Chivalric tally requires a current phase.")
    active_player_id = _active_player_id(state)
    removed_model_ids = set(state.battlefield_state.removed_model_ids)
    events_by_unit: dict[str, list[tuple[int, str, dict[str, JsonValue]]]] = {}
    for event_order, record in enumerate(event_log.records):
        if record.event_type != "model_destroyed":
            continue
        payload = _payload_object(record.payload)
        if payload.get("game_id") != state.game_id:
            continue
        if payload.get("battle_round") != state.battle_round:
            continue
        if payload.get("active_player_id") != active_player_id:
            continue
        if payload.get("phase") != completed_phase.value:
            continue
        target_unit_id = _payload_string(payload, key="target_unit_instance_id")
        events_by_unit.setdefault(target_unit_id, []).append(
            (event_order, record.event_id, dict(payload))
        )
    completions: list[tuple[int, str, dict[str, JsonValue]]] = []
    for target_unit_id, events in events_by_unit.items():
        model_ids = _model_instance_ids_for_unit(state=state, unit_instance_id=target_unit_id)
        if not model_ids:
            continue
        if not model_ids <= removed_model_ids:
            continue
        completions.append(sorted(events, key=lambda item: item[0])[-1])
    return tuple((event_id, payload) for _order, event_id, payload in sorted(completions))


def _eligible_lay_low_targets(
    state: GameState,
    *,
    player_id: str,
) -> tuple[tuple[ModelInstance, UnitInstance], ...]:
    _validate_game_state(state)
    targets: list[tuple[ModelInstance, UnitInstance]] = []
    for army in state.army_definitions:
        if army.player_id == player_id:
            continue
        for unit in army.units:
            if not _unit_has_keyword(unit, CHARACTER_KEYWORD):
                continue
            for model in unit.alive_own_models():
                targets.append((model, unit))
    return tuple(
        sorted(
            targets,
            key=lambda item: (item[1].unit_instance_id, item[0].model_instance_id),
        )
    )


def _assert_lay_low_target_valid(
    state: GameState,
    *,
    player_id: str,
    target_model_instance_id: str,
    target_unit_instance_id: str,
) -> None:
    target_model_id = _validate_identifier(
        "target_model_instance_id",
        target_model_instance_id,
    )
    target_unit_id = _validate_identifier("target_unit_instance_id", target_unit_instance_id)
    for model, unit in _eligible_lay_low_targets(state, player_id=player_id):
        if model.model_instance_id == target_model_id and unit.unit_instance_id == target_unit_id:
            return
    raise GameLifecycleError("Code Chivalric Lay Low target is not eligible.")


def _model_destroyed_event(
    event_log: EventLog,
    *,
    game_id: str,
    model_instance_id: str,
) -> EventRecord | None:
    if type(event_log) is not EventLog:
        raise GameLifecycleError("Code Chivalric model destroyed lookup requires EventLog.")
    model_id = _validate_identifier("model_instance_id", model_instance_id)
    matching: list[EventRecord] = []
    for record in event_log.records:
        if record.event_type != "model_destroyed":
            continue
        payload = _payload_object(record.payload)
        if payload.get("game_id") != game_id:
            continue
        if payload.get("model_instance_id") != model_id:
            continue
        matching.append(record)
    return matching[-1] if matching else None


def _validate_oath_payload_context(
    *,
    context: BattleFormationResultContext,
    request_payload: dict[str, JsonValue],
    payload: dict[str, JsonValue],
) -> None:
    if request_payload.get("game_id") != context.state.game_id:
        raise GameLifecycleError("Code Chivalric request game drift.")
    if request_payload.get("setup_step") != SetupStep.DECLARE_BATTLE_FORMATIONS.value:
        raise GameLifecycleError("Code Chivalric request setup step drift.")
    if _payload_string(payload, key="submission_kind") != CODE_CHIVALRIC_SELECTION_KIND:
        raise GameLifecycleError("Code Chivalric payload submission_kind drift.")
    if _payload_string(payload, key="player_id") != context.result.actor_id:
        raise GameLifecycleError("Code Chivalric payload player drift.")
    if _payload_string(payload, key="hook_id") != SETUP_HOOK_ID:
        raise GameLifecycleError("Code Chivalric payload hook drift.")


def _eligible_code_chivalric_unit_ids(army: ArmyDefinition) -> tuple[str, ...]:
    return tuple(unit.unit_instance_id for unit in army.units if _unit_has_code_chivalric(unit))


def _require_oath_state(state: GameState, *, player_id: str) -> FactionRuleState:
    oath_state = selected_oath_state_for_player(state, player_id=player_id)
    if oath_state is None:
        raise GameLifecycleError("Code Chivalric oath is not selected.")
    return oath_state


def _imperial_knights_armies(state: GameState) -> tuple[ArmyDefinition, ...]:
    _validate_game_state(state)
    return tuple(
        army
        for army in state.army_definitions
        if army.detachment_selection.faction_id == IMPERIAL_KNIGHTS_FACTION_ID
    )


def _imperial_knights_army_for_player(
    state: GameState,
    *,
    player_id: str,
) -> ArmyDefinition | None:
    requested_player_id = _validate_identifier("player_id", player_id)
    matches = tuple(
        army for army in _imperial_knights_armies(state) if army.player_id == requested_player_id
    )
    if len(matches) > 1:
        raise GameLifecycleError("Player has multiple Imperial Knights armies.")
    return matches[0] if matches else None


def _unit_and_army_by_id(
    state: GameState,
    *,
    unit_instance_id: str,
) -> tuple[UnitInstance, ArmyDefinition]:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    matches: list[tuple[UnitInstance, ArmyDefinition]] = []
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                matches.append((unit, army))
    if len(matches) != 1:
        raise GameLifecycleError("Unit lookup failed for Code Chivalric.")
    return matches[0]


def _unit_owner_player_id(state: GameState, *, unit_instance_id: str) -> str:
    _unit, army = _unit_and_army_by_id(state, unit_instance_id=unit_instance_id)
    return army.player_id


def _model_instance_ids_for_unit(
    *,
    state: GameState,
    unit_instance_id: str,
) -> set[str]:
    unit, _army = _unit_and_army_by_id(state, unit_instance_id=unit_instance_id)
    return {model.model_instance_id for model in unit.own_models}


def _unit_has_code_chivalric(unit: UnitInstance) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Code Chivalric unit check requires UnitInstance.")
    if _unit_has_faction_keyword(unit, IMPERIAL_KNIGHTS_FACTION_KEYWORD):
        return True
    return any(ability.name == CODE_CHIVALRIC_ABILITY_NAME for ability in unit.datasheet_abilities)


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    requested_keyword = _canonical_keyword(keyword)
    return requested_keyword in {_canonical_keyword(item) for item in unit.keywords}


def _unit_has_faction_keyword(unit: UnitInstance, keyword: str) -> bool:
    requested_keyword = _canonical_keyword(keyword)
    return requested_keyword in {_canonical_keyword(item) for item in unit.faction_keywords}


def _deed_from_d6(value: int) -> CodeChivalricDeed:
    if value in {1, 2}:
        return CodeChivalricDeed.LAY_LOW_THE_TYRANT
    if value in {3, 4}:
        return CodeChivalricDeed.RECLAIM_THE_REALM
    if value in {5, 6}:
        return CodeChivalricDeed.REAP_A_GREAT_TALLY
    raise GameLifecycleError("Code Chivalric deed roll must be a D6 value.")


def _quality_from_d6(value: int) -> CodeChivalricQuality:
    if value in {1, 2}:
        return CodeChivalricQuality.MARTIAL_VALOUR
    if value in {3, 4}:
        return CodeChivalricQuality.EAGER_FOR_THE_CHALLENGE
    if value in {5, 6}:
        return CodeChivalricQuality.LEGACY_UNSULLIED
    raise GameLifecycleError("Code Chivalric quality roll must be a D6 value.")


def _deed_from_token(token: object) -> CodeChivalricDeed:
    if type(token) is CodeChivalricDeed:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Code Chivalric deed token must be a string.")
    try:
        return CodeChivalricDeed(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported Code Chivalric deed: {token}.") from exc


def _quality_from_token(token: object) -> CodeChivalricQuality:
    if type(token) is CodeChivalricQuality:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Code Chivalric quality token must be a string.")
    try:
        return CodeChivalricQuality(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported Code Chivalric quality: {token}.") from exc


def _selection_mode_from_token(token: object) -> OathSelectionMode:
    if type(token) is OathSelectionMode:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Code Chivalric selection mode must be a string.")
    try:
        return OathSelectionMode(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported Code Chivalric selection mode: {token}.") from exc


def _event_with_source_id_exists(event_log: EventLog, *, source_id: str) -> bool:
    requested_source_id = _validate_identifier("source_id", source_id)
    for record in event_log.records:
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        if payload.get("source_rule_id") == requested_source_id:
            return True
    return False


def _active_player_id(state: GameState) -> str:
    active_player_id = state.active_player_id
    if active_player_id is None:
        raise GameLifecycleError("Code Chivalric requires an active player.")
    return active_player_id


def _validate_game_state(state: object) -> GameState:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Code Chivalric requires GameState.")
    return state


def _payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Code Chivalric payload must be an object.")
    return payload


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    if key not in payload:
        raise GameLifecycleError(f"Code Chivalric payload missing {key}.")
    return _validate_identifier(key, payload[key])


def _payload_optional_string(payload: dict[str, JsonValue], *, key: str) -> str | None:
    if key not in payload:
        raise GameLifecycleError(f"Code Chivalric payload missing {key}.")
    value = payload[key]
    if value is None:
        return None
    return _validate_identifier(key, value)


def _payload_int(payload: dict[str, JsonValue], *, key: str) -> int:
    if key not in payload:
        raise GameLifecycleError(f"Code Chivalric payload missing {key}.")
    value = payload[key]
    if type(value) is not int:
        raise GameLifecycleError(f"Code Chivalric payload {key} must be an int.")
    return value


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _canonical_keyword(value: str) -> str:
    return _validate_identifier("keyword", value).upper().replace("_", " ")
