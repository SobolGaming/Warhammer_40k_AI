from __future__ import annotations

from dataclasses import replace

from warhammer40k_core.core.attributes import CharacteristicValue
from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollSpec,
    RerollComponentSelectionPolicy,
    RerollPermission,
)
from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    AbilityKind,
    AbilityParameter,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battlefield_state import PlacementError, geometry_model_for_placement
from warhammer40k_core.engine.core_stratagem_effects import SMOKESCREEN_EFFECT_KIND
from warhammer40k_core.engine.damage_allocation import apply_mortal_wounds_to_unit
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.faction_content.common import (
    canonical_keyword as _canonical_keyword,
)
from warhammer40k_core.engine.faction_content.stratagem_handlers import (
    StratagemHandlerContext,
    StratagemHandlerExecutionResult,
)
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.phases.charge import CHARGE_AFTER_FALL_BACK_EFFECT_KIND
from warhammer40k_core.engine.reaction_windows import ReactionWindow, ReactionWindowKind
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.source_backed_rerolls import (
    source_backed_reroll_permission_effect_payload,
)
from warhammer40k_core.engine.stratagems import (
    DESTROYED_ENEMY_UNIT_CONTEXT_KEY,
    DESTROYED_TARGET_UNIT_CONTEXT_KEY,
    ENGAGED_ENEMY_UNIT_CONTEXT_KEY,
    ENGAGED_ENEMY_UNIT_EFFECT_SELECTION_KIND,
    ENGAGED_ENEMY_UNIT_IDS_CONTEXT_KEY,
    GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
    JUST_FELL_BACK_UNIT_CONTEXT_KEY,
    JUST_FELL_BACK_UNIT_TARGET_POLICY_ID,
    JUST_SHOT_UNIT_CONTEXT_KEY,
    JUST_SHOT_UNIT_TARGET_POLICY_ID,
    NOT_SELECTED_TO_FIGHT_TARGET_POLICY_ID,
    NOT_SELECTED_TO_SHOOT_TARGET_POLICY_ID,
    SELECTED_TARGET_CONTROLLED_OBJECTIVE_INFANTRY_TARGET_POLICY_ID,
    StratagemAvailabilityKind,
    StratagemCatalogRecord,
    StratagemCategory,
    StratagemDefinition,
    StratagemRestrictionPolicy,
    StratagemTargetKind,
    StratagemTargetSpec,
    StratagemTimingDescriptor,
    destroyed_enemy_unit_ids_from_context,
    destroyed_target_unit_ids_from_context,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.triggered_movement import (
    TriggeredMovementDescriptor,
    TriggeredMovementEligibleUnit,
    TriggeredMovementKind,
    triggered_movement_unit_selection_request,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_aeldari_corsair_coterie_ir_support_2026_27 as corsair_coterie_ir,
)

from .rule import ANHRATHE, CORSAIR_COTERIE_DETACHMENT_ID

CONTRIBUTION_ID = "warhammer_40000_11th:aeldari:detachment:corsair_coterie:stratagems:scaffold"
SOURCE_RULE_ID = "phase17g:aeldari:corsair-coterie:stratagems"
AELDARI_FACTION_ID = "aeldari"
AELDARI = "AELDARI"
INFANTRY = "INFANTRY"
RANGERS = "RANGERS"
SHROUD_RUNNERS = "SHROUD RUNNERS"
CHARACTER = "CHARACTER"

PIRATES_DUE_STRATAGEM_ID = "aeldari:corsair-coterie:pirates-due"
LETHAL_RUSE_STRATAGEM_ID = "aeldari:corsair-coterie:lethal-ruse"
OUTCAST_AMBUSH_STRATAGEM_ID = "aeldari:corsair-coterie:outcast-ambush"
INTO_THE_BREACH_STRATAGEM_ID = "aeldari:corsair-coterie:into-the-breach"
CLOAK_AND_SHADOW_STRATAGEM_ID = "aeldari:corsair-coterie:cloak-and-shadow"
VENGEFUL_SORROW_STRATAGEM_ID = "aeldari:corsair-coterie:vengeful-sorrow"

PIRATES_DUE_HANDLER_ID = "warhammer_40000_11th:aeldari:detachment:corsair_coterie:pirates_due"
LETHAL_RUSE_HANDLER_ID = "warhammer_40000_11th:aeldari:detachment:corsair_coterie:lethal_ruse"
OUTCAST_AMBUSH_HANDLER_ID = "warhammer_40000_11th:aeldari:detachment:corsair_coterie:outcast_ambush"
INTO_THE_BREACH_HANDLER_ID = (
    "warhammer_40000_11th:aeldari:detachment:corsair_coterie:into_the_breach"
)
CLOAK_AND_SHADOW_HANDLER_ID = (
    "warhammer_40000_11th:aeldari:detachment:corsair_coterie:cloak_and_shadow"
)
VENGEFUL_SORROW_HANDLER_ID = (
    "warhammer_40000_11th:aeldari:detachment:corsair_coterie:vengeful_sorrow"
)

PIRATES_DUE_RECORD_ID = f"{SOURCE_RULE_ID}:{PIRATES_DUE_STRATAGEM_ID}"
LETHAL_RUSE_RECORD_ID = f"{SOURCE_RULE_ID}:{LETHAL_RUSE_STRATAGEM_ID}"
OUTCAST_AMBUSH_RECORD_ID = f"{SOURCE_RULE_ID}:{OUTCAST_AMBUSH_STRATAGEM_ID}"
INTO_THE_BREACH_RECORD_ID = f"{SOURCE_RULE_ID}:{INTO_THE_BREACH_STRATAGEM_ID}"
CLOAK_AND_SHADOW_RECORD_ID = f"{SOURCE_RULE_ID}:{CLOAK_AND_SHADOW_STRATAGEM_ID}"
VENGEFUL_SORROW_RECORD_ID = f"{SOURCE_RULE_ID}:{VENGEFUL_SORROW_STRATAGEM_ID}"

PIRATES_DUE_EFFECT_KIND = "aeldari_corsair_coterie_pirates_due"
LETHAL_RUSE_EFFECT_KIND = "aeldari_corsair_coterie_lethal_ruse"
OUTCAST_AMBUSH_EFFECT_KIND = "aeldari_corsair_coterie_outcast_ambush"
CLOAK_AND_SHADOW_EFFECT_KIND = "aeldari_corsair_coterie_cloak_and_shadow"

OUTCAST_AMBUSH_WEAPON_PROFILE_MODIFIER_ID = f"{SOURCE_RULE_ID}:outcast-ambush:weapon-profile"
CLOAK_AND_SHADOW_MAX_RANGE_INCHES = 18.0


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        stratagem_records=(
            _pirates_due_record(),
            _lethal_ruse_record(),
            _outcast_ambush_record(),
            _into_the_breach_record(),
            _cloak_and_shadow_record(),
            _vengeful_sorrow_record(),
        ),
    )


def apply_pirates_due(context: StratagemHandlerContext) -> StratagemHandlerExecutionResult:
    validation = validate_pirates_due(context)
    if validation.reason is not None:
        return validation
    unit_id = _target_unit_id(context)
    unit = _unit_by_id(context, unit_instance_id=unit_id)
    permission = RerollPermission(
        source_id=f"{context.use_record.use_id}:wound-reroll",
        timing_window="attack_sequence.wound",
        owning_player_id=context.use_record.player_id,
        eligible_roll_type="attack_sequence.wound",
        component_selection_policy=RerollComponentSelectionPolicy.COMPONENT_SELECTION,
        allowed_component_selections=((0,),),
    )
    effect = PersistingEffect(
        effect_id=f"{context.use_record.use_id}:pirates-due:{unit_id}",
        source_rule_id=SOURCE_RULE_ID,
        owner_player_id=context.use_record.player_id,
        target_unit_instance_ids=(unit_id,),
        started_battle_round=context.state.battle_round,
        started_phase=BattlePhase.FIGHT,
        expiration=EffectExpiration.end_phase(
            battle_round=context.state.battle_round,
            phase=BattlePhase.FIGHT,
            player_id=_active_player_id(context),
        ),
        effect_payload=source_backed_reroll_permission_effect_payload(
            target_unit_instance_ids=(unit_id,),
            permission=permission,
            source_payload={
                "effect_kind": PIRATES_DUE_EFFECT_KIND,
                "stratagem_id": PIRATES_DUE_STRATAGEM_ID,
                "stratagem_use_id": context.use_record.use_id,
                "conditional_wound_reroll": {
                    "reroll_unmodified_values": [1],
                    "full_reroll_if_target_within_objective_range": _unit_has_keyword(
                        unit,
                        ANHRATHE,
                    ),
                    "full_reroll_required_attacker_keyword": ANHRATHE,
                },
            },
        ),
    )
    context.state.record_persisting_effect(effect)
    context.decisions.event_log.append(
        "aeldari_corsair_coterie_pirates_due_applied",
        _effect_event_payload(context=context, effect=effect),
    )
    return StratagemHandlerExecutionResult.applied(
        handler_id=PIRATES_DUE_HANDLER_ID,
        replay_payload={
            "effect_kind": PIRATES_DUE_EFFECT_KIND,
            "unit_instance_id": unit_id,
            "persisting_effect_id": effect.effect_id,
        },
    )


def validate_pirates_due(context: StratagemHandlerContext) -> StratagemHandlerExecutionResult:
    result = _validate_corsair_stratagem(
        context,
        stratagem_id=PIRATES_DUE_STRATAGEM_ID,
        handler_id=PIRATES_DUE_HANDLER_ID,
        trigger_kind=TimingTriggerKind.DURING_PHASE,
        phase=BattlePhase.FIGHT,
        require_active_player=False,
    )
    if result.reason is not None:
        return result
    unit_id = _target_unit_id(context)
    if _unit_selected_to_fight(context, unit_instance_id=unit_id):
        return StratagemHandlerExecutionResult.invalid(
            handler_id=PIRATES_DUE_HANDLER_ID,
            reason="target_already_selected_to_fight",
        )
    return StratagemHandlerExecutionResult.applied(handler_id=PIRATES_DUE_HANDLER_ID)


def apply_lethal_ruse(context: StratagemHandlerContext) -> StratagemHandlerExecutionResult:
    validation = validate_lethal_ruse(context)
    if validation.reason is not None:
        return validation
    unit_id = _target_unit_id(context)
    effect = PersistingEffect(
        effect_id=f"{context.use_record.use_id}:lethal-ruse:{unit_id}",
        source_rule_id=SOURCE_RULE_ID,
        owner_player_id=context.use_record.player_id,
        target_unit_instance_ids=(unit_id,),
        started_battle_round=context.state.battle_round,
        started_phase=BattlePhase.MOVEMENT,
        expiration=EffectExpiration.end_turn(
            battle_round=context.state.battle_round,
            player_id=context.use_record.player_id,
        ),
        effect_payload={
            "effect_kind": CHARGE_AFTER_FALL_BACK_EFFECT_KIND,
            "source_effect_kind": LETHAL_RUSE_EFFECT_KIND,
            "stratagem_id": LETHAL_RUSE_STRATAGEM_ID,
            "stratagem_use_id": context.use_record.use_id,
        },
    )
    context.state.record_persisting_effect(effect)
    mortal_payload = _apply_lethal_ruse_mortal_wounds(context)
    context.decisions.event_log.append(
        "aeldari_corsair_coterie_lethal_ruse_applied",
        validate_json_value(
            {
                **_effect_event_payload_object(context=context, effect=effect),
                "mortal_wound_resolution": mortal_payload,
            }
        ),
    )
    return StratagemHandlerExecutionResult.applied(
        handler_id=LETHAL_RUSE_HANDLER_ID,
        replay_payload={
            "effect_kind": LETHAL_RUSE_EFFECT_KIND,
            "unit_instance_id": unit_id,
            "persisting_effect_id": effect.effect_id,
            "mortal_wound_resolution": mortal_payload,
        },
    )


def validate_lethal_ruse(context: StratagemHandlerContext) -> StratagemHandlerExecutionResult:
    result = _validate_corsair_stratagem(
        context,
        stratagem_id=LETHAL_RUSE_STRATAGEM_ID,
        handler_id=LETHAL_RUSE_HANDLER_ID,
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_FALLS_BACK,
        phase=BattlePhase.MOVEMENT,
        require_active_player=True,
    )
    if result.reason is not None:
        return result
    unit_id = _target_unit_id(context)
    if unit_id != _fell_back_unit_id(context):
        return StratagemHandlerExecutionResult.invalid(
            handler_id=LETHAL_RUSE_HANDLER_ID,
            reason="target_not_fell_back_unit",
        )
    unit = _unit_by_id(context, unit_instance_id=unit_id)
    if _unit_has_keyword(unit, ANHRATHE):
        selected_enemy_id = _engaged_enemy_unit_id(context)
        if selected_enemy_id not in _engaged_enemy_unit_ids(context):
            return StratagemHandlerExecutionResult.invalid(
                handler_id=LETHAL_RUSE_HANDLER_ID,
                reason="selected_enemy_not_start_engaged",
            )
        if _unit_owner(context, unit_instance_id=selected_enemy_id) == context.use_record.player_id:
            return StratagemHandlerExecutionResult.invalid(
                handler_id=LETHAL_RUSE_HANDLER_ID,
                reason="selected_unit_not_enemy",
            )
    return StratagemHandlerExecutionResult.applied(handler_id=LETHAL_RUSE_HANDLER_ID)


def apply_outcast_ambush(context: StratagemHandlerContext) -> StratagemHandlerExecutionResult:
    validation = validate_outcast_ambush(context)
    if validation.reason is not None:
        return validation
    unit_id = _target_unit_id(context)
    effect = PersistingEffect(
        effect_id=f"{context.use_record.use_id}:outcast-ambush:{unit_id}",
        source_rule_id=SOURCE_RULE_ID,
        owner_player_id=context.use_record.player_id,
        target_unit_instance_ids=(unit_id,),
        started_battle_round=context.state.battle_round,
        started_phase=BattlePhase.SHOOTING,
        expiration=EffectExpiration.end_phase(
            battle_round=context.state.battle_round,
            phase=BattlePhase.SHOOTING,
            player_id=context.use_record.player_id,
        ),
        effect_payload={
            "effect_kind": OUTCAST_AMBUSH_EFFECT_KIND,
            "stratagem_id": OUTCAST_AMBUSH_STRATAGEM_ID,
            "stratagem_use_id": context.use_record.use_id,
        },
    )
    context.state.record_persisting_effect(effect)
    context.decisions.event_log.append(
        "aeldari_corsair_coterie_outcast_ambush_applied",
        _effect_event_payload(context=context, effect=effect),
    )
    return StratagemHandlerExecutionResult.applied(
        handler_id=OUTCAST_AMBUSH_HANDLER_ID,
        replay_payload={
            "effect_kind": OUTCAST_AMBUSH_EFFECT_KIND,
            "unit_instance_id": unit_id,
            "persisting_effect_id": effect.effect_id,
        },
    )


def validate_outcast_ambush(context: StratagemHandlerContext) -> StratagemHandlerExecutionResult:
    result = _validate_corsair_stratagem(
        context,
        stratagem_id=OUTCAST_AMBUSH_STRATAGEM_ID,
        handler_id=OUTCAST_AMBUSH_HANDLER_ID,
        trigger_kind=TimingTriggerKind.DURING_PHASE,
        phase=BattlePhase.SHOOTING,
        require_active_player=True,
    )
    if result.reason is not None:
        return result
    unit = _unit_by_id(context, unit_instance_id=_target_unit_id(context))
    if not (_unit_has_keyword(unit, RANGERS) or _unit_has_keyword(unit, SHROUD_RUNNERS)):
        return StratagemHandlerExecutionResult.invalid(
            handler_id=OUTCAST_AMBUSH_HANDLER_ID,
            reason="target_missing_rangers_or_shroud_runners",
        )
    if _unit_selected_to_shoot(context, unit_instance_id=unit.unit_instance_id):
        return StratagemHandlerExecutionResult.invalid(
            handler_id=OUTCAST_AMBUSH_HANDLER_ID,
            reason="target_already_selected_to_shoot",
        )
    return StratagemHandlerExecutionResult.applied(handler_id=OUTCAST_AMBUSH_HANDLER_ID)


def apply_into_the_breach(context: StratagemHandlerContext) -> StratagemHandlerExecutionResult:
    validation = validate_into_the_breach(context)
    if validation.reason is not None:
        return validation
    unit_id = _target_unit_id(context)
    request, distance_roll_payload = _request_triggered_move(
        context=context,
        handler_id=INTO_THE_BREACH_HANDLER_ID,
        unit_instance_id=unit_id,
        roll_type="corsair_coterie.into_the_breach_distance",
        source_step="into_the_breach",
        movement_kind=TriggeredMovementKind.TRIGGERED,
        allow_battle_shocked=True,
        replay_effect_kind="into_the_breach_move",
    )
    context.decisions.event_log.append(
        "aeldari_corsair_coterie_into_the_breach_move_requested",
        _triggered_move_event_payload(
            context=context,
            request_id=request.request_id,
            distance_roll=distance_roll_payload,
        ),
    )
    return StratagemHandlerExecutionResult.applied(
        handler_id=INTO_THE_BREACH_HANDLER_ID,
        replay_payload={
            "effect_kind": "into_the_breach",
            "unit_instance_id": unit_id,
            "distance_roll": distance_roll_payload,
            "triggered_movement_request_id": request.request_id,
        },
    )


def validate_into_the_breach(context: StratagemHandlerContext) -> StratagemHandlerExecutionResult:
    result = _validate_corsair_stratagem(
        context,
        stratagem_id=INTO_THE_BREACH_STRATAGEM_ID,
        handler_id=INTO_THE_BREACH_HANDLER_ID,
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT,
        phase=BattlePhase.SHOOTING,
        require_active_player=True,
    )
    if result.reason is not None:
        return result
    if _target_unit_id(context) != _shot_unit_id(context):
        return StratagemHandlerExecutionResult.invalid(
            handler_id=INTO_THE_BREACH_HANDLER_ID,
            reason="target_not_just_shot",
        )
    unit = _unit_by_id(context, unit_instance_id=_target_unit_id(context))
    if not _unit_has_keyword(unit, ANHRATHE):
        return StratagemHandlerExecutionResult.invalid(
            handler_id=INTO_THE_BREACH_HANDLER_ID,
            reason="target_not_anhrathe",
        )
    if not destroyed_enemy_unit_ids_from_context(context.eligibility_context):
        return StratagemHandlerExecutionResult.invalid(
            handler_id=INTO_THE_BREACH_HANDLER_ID,
            reason="no_enemy_unit_destroyed",
        )
    return StratagemHandlerExecutionResult.applied(handler_id=INTO_THE_BREACH_HANDLER_ID)


def apply_cloak_and_shadow(context: StratagemHandlerContext) -> StratagemHandlerExecutionResult:
    validation = validate_cloak_and_shadow(context)
    if validation.reason is not None:
        return validation
    unit_id = _target_unit_id(context)
    effect = PersistingEffect(
        effect_id=f"{context.use_record.use_id}:cloak-and-shadow:{unit_id}",
        source_rule_id=SOURCE_RULE_ID,
        owner_player_id=context.use_record.player_id,
        target_unit_instance_ids=(unit_id,),
        started_battle_round=context.state.battle_round,
        started_phase=BattlePhase.SHOOTING,
        expiration=EffectExpiration.end_phase(
            battle_round=context.state.battle_round,
            phase=BattlePhase.SHOOTING,
            player_id=_active_player_id(context),
        ),
        effect_payload={
            "effect_kind": SMOKESCREEN_EFFECT_KIND,
            "source_effect_kind": CLOAK_AND_SHADOW_EFFECT_KIND,
            "stratagem_id": CLOAK_AND_SHADOW_STRATAGEM_ID,
            "stratagem_use_id": context.use_record.use_id,
            "hit_roll_modifier": -1,
            "targeting_max_range_inches": CLOAK_AND_SHADOW_MAX_RANGE_INCHES,
        },
    )
    context.state.record_persisting_effect(effect)
    context.decisions.event_log.append(
        "aeldari_corsair_coterie_cloak_and_shadow_applied",
        _effect_event_payload(context=context, effect=effect),
    )
    return StratagemHandlerExecutionResult.applied(
        handler_id=CLOAK_AND_SHADOW_HANDLER_ID,
        replay_payload={
            "effect_kind": CLOAK_AND_SHADOW_EFFECT_KIND,
            "unit_instance_id": unit_id,
            "persisting_effect_id": effect.effect_id,
        },
    )


def validate_cloak_and_shadow(context: StratagemHandlerContext) -> StratagemHandlerExecutionResult:
    result = _validate_corsair_stratagem(
        context,
        stratagem_id=CLOAK_AND_SHADOW_STRATAGEM_ID,
        handler_id=CLOAK_AND_SHADOW_HANDLER_ID,
        trigger_kind=TimingTriggerKind.AFTER_UNIT_SELECTED_AS_TARGET,
        phase=BattlePhase.SHOOTING,
        require_active_player=False,
    )
    if result.reason is not None:
        return result
    unit_id = _target_unit_id(context)
    unit = _unit_by_id(context, unit_instance_id=unit_id)
    if not _unit_has_keyword(unit, INFANTRY):
        return StratagemHandlerExecutionResult.invalid(
            handler_id=CLOAK_AND_SHADOW_HANDLER_ID,
            reason="target_not_infantry",
        )
    if not _unit_within_controlled_objective_range(context, unit_instance_id=unit_id):
        return StratagemHandlerExecutionResult.invalid(
            handler_id=CLOAK_AND_SHADOW_HANDLER_ID,
            reason="target_not_within_controlled_objective",
        )
    return StratagemHandlerExecutionResult.applied(handler_id=CLOAK_AND_SHADOW_HANDLER_ID)


def apply_vengeful_sorrow(context: StratagemHandlerContext) -> StratagemHandlerExecutionResult:
    validation = validate_vengeful_sorrow(context)
    if validation.reason is not None:
        return validation
    unit_id = _target_unit_id(context)
    request, distance_roll_payload = _request_triggered_move(
        context=context,
        handler_id=VENGEFUL_SORROW_HANDLER_ID,
        unit_instance_id=unit_id,
        roll_type="corsair_coterie.vengeful_sorrow_distance",
        source_step="vengeful_sorrow",
        movement_kind=TriggeredMovementKind.SURGE,
        allow_battle_shocked=False,
        replay_effect_kind="vengeful_sorrow_surge",
    )
    context.decisions.event_log.append(
        "aeldari_corsair_coterie_vengeful_sorrow_surge_requested",
        _triggered_move_event_payload(
            context=context,
            request_id=request.request_id,
            distance_roll=distance_roll_payload,
        ),
    )
    return StratagemHandlerExecutionResult.applied(
        handler_id=VENGEFUL_SORROW_HANDLER_ID,
        replay_payload={
            "effect_kind": "vengeful_sorrow",
            "unit_instance_id": unit_id,
            "distance_roll": distance_roll_payload,
            "triggered_movement_request_id": request.request_id,
        },
    )


def validate_vengeful_sorrow(context: StratagemHandlerContext) -> StratagemHandlerExecutionResult:
    result = _validate_corsair_stratagem(
        context,
        stratagem_id=VENGEFUL_SORROW_STRATAGEM_ID,
        handler_id=VENGEFUL_SORROW_HANDLER_ID,
        trigger_kind=TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_HAS_SHOT,
        phase=BattlePhase.SHOOTING,
        require_active_player=False,
    )
    if result.reason is not None:
        return result
    unit_id = _target_unit_id(context)
    unit = _unit_by_id(context, unit_instance_id=unit_id)
    if not _unit_has_keyword(unit, INFANTRY):
        return StratagemHandlerExecutionResult.invalid(
            handler_id=VENGEFUL_SORROW_HANDLER_ID,
            reason="target_not_infantry",
        )
    if unit_id not in destroyed_target_unit_ids_from_context(context.eligibility_context):
        return StratagemHandlerExecutionResult.invalid(
            handler_id=VENGEFUL_SORROW_HANDLER_ID,
            reason="target_models_not_destroyed",
        )
    if unit_id in context.state.battle_shocked_unit_ids:
        return StratagemHandlerExecutionResult.invalid(
            handler_id=VENGEFUL_SORROW_HANDLER_ID,
            reason="target_battle_shocked",
        )
    if _unit_is_engaged(context, unit_instance_id=unit_id):
        return StratagemHandlerExecutionResult.invalid(
            handler_id=VENGEFUL_SORROW_HANDLER_ID,
            reason="target_within_engagement_range",
        )
    return StratagemHandlerExecutionResult.applied(handler_id=VENGEFUL_SORROW_HANDLER_ID)


def outcast_ambush_weapon_profile_modifier(
    context: WeaponProfileModifierContext,
) -> WeaponProfile:
    if type(context) is not WeaponProfileModifierContext:
        raise GameLifecycleError("Outcast Ambush requires a weapon profile modifier context.")
    if context.source_phase is not BattlePhase.SHOOTING:
        return context.weapon_profile
    if not _unit_has_effect(
        context.state,
        unit_instance_id=context.attacking_unit_instance_id,
        effect_kind=OUTCAST_AMBUSH_EFFECT_KIND,
    ):
        return context.weapon_profile
    profile = context.weapon_profile
    return replace(
        profile,
        armor_penetration=_improved_ap(profile.armor_penetration),
        keywords=tuple(
            sorted(
                {
                    *profile.keywords,
                    WeaponKeyword.IGNORES_COVER,
                    WeaponKeyword.RAPID_FIRE,
                }
            )
        ),
        abilities=_abilities_with_rapid_fire_one(profile.abilities),
        source_ids=tuple(sorted({*profile.source_ids, OUTCAST_AMBUSH_WEAPON_PROFILE_MODIFIER_ID})),
    )


def _pirates_due_record() -> StratagemCatalogRecord:
    return _stratagem_record(
        record_id=PIRATES_DUE_RECORD_ID,
        stratagem_id=PIRATES_DUE_STRATAGEM_ID,
        name="Pirates' Due",
        category=StratagemCategory.BATTLE_TACTIC,
        when_descriptor="The Fight phase.",
        target_descriptor="One Aeldari unit from your army that has not been selected to fight.",
        effect_descriptor=(
            "Until the end of the phase, attacks re-roll Wound rolls of 1. ANHRATHE attacks "
            "targeting an enemy unit within range of an objective marker can re-roll Wound rolls."
        ),
        timing=StratagemTimingDescriptor(
            trigger_kind=TimingTriggerKind.DURING_PHASE,
            phase=BattlePhase.FIGHT,
        ),
        target_spec=StratagemTargetSpec(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            enumerable=True,
            target_policy_id=NOT_SELECTED_TO_FIGHT_TARGET_POLICY_ID,
            required_faction_keywords=(AELDARI,),
        ),
        effect_payload=_generic_rule_ir_payload(
            corsair_coterie_ir.PIRATES_DUE_DESCRIPTOR_ID,
        ),
    )


def _lethal_ruse_record() -> StratagemCatalogRecord:
    return _stratagem_record(
        record_id=LETHAL_RUSE_RECORD_ID,
        stratagem_id=LETHAL_RUSE_STRATAGEM_ID,
        name="Lethal Ruse",
        category=StratagemCategory.STRATEGIC_PLOY,
        when_descriptor=(
            "Your Movement phase, just after an Aeldari unit from your army Falls Back."
        ),
        target_descriptor="That Aeldari unit.",
        effect_descriptor=(
            "Until the end of the turn, your unit is eligible to declare a charge in a turn in "
            "which it Fell Back. If it is an ANHRATHE unit, select one enemy unit it was within "
            "Engagement Range of at the start of the phase and roll six D6; each 4+ inflicts 1 "
            "mortal wound."
        ),
        timing=StratagemTimingDescriptor(
            trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_FALLS_BACK,
            phase=BattlePhase.MOVEMENT,
        ),
        target_spec=StratagemTargetSpec(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            enumerable=True,
            target_policy_id=JUST_FELL_BACK_UNIT_TARGET_POLICY_ID,
            required_faction_keywords=(AELDARI,),
        ),
        effect_payload={
            **_generic_rule_ir_payload(corsair_coterie_ir.LETHAL_RUSE_DESCRIPTOR_ID),
            "effect_selection_kind": ENGAGED_ENEMY_UNIT_EFFECT_SELECTION_KIND,
            "effect_selection_required_target_keywords": [ANHRATHE],
        },
    )


def _outcast_ambush_record() -> StratagemCatalogRecord:
    return _stratagem_record(
        record_id=OUTCAST_AMBUSH_RECORD_ID,
        stratagem_id=OUTCAST_AMBUSH_STRATAGEM_ID,
        name="Outcast Ambush",
        category=StratagemCategory.STRATEGIC_PLOY,
        when_descriptor="Your Shooting phase.",
        target_descriptor="One Rangers or Shroud Runners unit that has not been selected to shoot.",
        effect_descriptor=(
            "Until the end of the phase, ranged weapons equipped by models in your unit have "
            "[IGNORES COVER] and [RAPID FIRE 1], and improve AP by 1."
        ),
        timing=StratagemTimingDescriptor(
            trigger_kind=TimingTriggerKind.DURING_PHASE,
            phase=BattlePhase.SHOOTING,
        ),
        target_spec=StratagemTargetSpec(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            enumerable=True,
            target_policy_id=NOT_SELECTED_TO_SHOOT_TARGET_POLICY_ID,
            required_keywords_any=(RANGERS, SHROUD_RUNNERS),
            required_faction_keywords=(AELDARI,),
        ),
        effect_payload=_generic_rule_ir_payload(
            corsair_coterie_ir.OUTCAST_AMBUSH_DESCRIPTOR_ID,
        ),
    )


def _into_the_breach_record() -> StratagemCatalogRecord:
    return _stratagem_record(
        record_id=INTO_THE_BREACH_RECORD_ID,
        stratagem_id=INTO_THE_BREACH_STRATAGEM_ID,
        name="Into the Breach",
        category=StratagemCategory.STRATEGIC_PLOY,
        when_descriptor=(
            "Your Shooting phase, just after an ANHRATHE unit from your army destroyed one or "
            "more enemy units."
        ),
        target_descriptor="That ANHRATHE unit.",
        effect_descriptor=(
            "After your unit has resolved its shooting attacks, it can make a Normal move of "
            'up to D6+1".'
        ),
        timing=StratagemTimingDescriptor(
            trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT,
            phase=BattlePhase.SHOOTING,
        ),
        target_spec=StratagemTargetSpec(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            enumerable=True,
            target_policy_id=JUST_SHOT_UNIT_TARGET_POLICY_ID,
            required_keywords=(ANHRATHE,),
            required_faction_keywords=(AELDARI,),
        ),
        effect_payload={
            **_generic_rule_ir_payload(corsair_coterie_ir.INTO_THE_BREACH_DESCRIPTOR_ID),
            "required_non_empty_trigger_context_keys": [DESTROYED_ENEMY_UNIT_CONTEXT_KEY],
        },
    )


def _cloak_and_shadow_record() -> StratagemCatalogRecord:
    return _stratagem_record(
        record_id=CLOAK_AND_SHADOW_RECORD_ID,
        stratagem_id=CLOAK_AND_SHADOW_STRATAGEM_ID,
        name="Cloak and Shadow",
        category=StratagemCategory.STRATEGIC_PLOY,
        when_descriptor=(
            "Your opponent's Shooting phase, just after an enemy unit has selected its targets."
        ),
        target_descriptor=(
            "One Aeldari Infantry unit within range of an objective marker you control that was "
            "selected as a target."
        ),
        effect_descriptor=(
            "Until the end of the phase, models in your unit have Stealth and your unit can only "
            'be selected as the target of a ranged attack if the attacking model is within 18".'
        ),
        timing=StratagemTimingDescriptor(
            trigger_kind=TimingTriggerKind.AFTER_UNIT_SELECTED_AS_TARGET,
            phase=BattlePhase.SHOOTING,
        ),
        target_spec=StratagemTargetSpec(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            enumerable=True,
            target_policy_id=SELECTED_TARGET_CONTROLLED_OBJECTIVE_INFANTRY_TARGET_POLICY_ID,
            required_keywords=(INFANTRY,),
            required_faction_keywords=(AELDARI,),
        ),
        effect_payload=_generic_rule_ir_payload(
            corsair_coterie_ir.CLOAK_AND_SHADOW_DESCRIPTOR_ID,
        ),
    )


def _vengeful_sorrow_record() -> StratagemCatalogRecord:
    return _stratagem_record(
        record_id=VENGEFUL_SORROW_RECORD_ID,
        stratagem_id=VENGEFUL_SORROW_STRATAGEM_ID,
        name="Vengeful Sorrow",
        category=StratagemCategory.STRATEGIC_PLOY,
        when_descriptor="Your opponent's Shooting phase, just after an enemy unit has shot.",
        target_descriptor=(
            "One Aeldari Infantry unit from your army if one or more models were destroyed by "
            "those attacks and it is neither Battle-shocked nor within Engagement Range."
        ),
        effect_descriptor='Your unit can make a surge move of up to D6+1".',
        timing=StratagemTimingDescriptor(
            trigger_kind=TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_HAS_SHOT,
            phase=BattlePhase.SHOOTING,
        ),
        target_spec=StratagemTargetSpec(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            enumerable=True,
            required_keywords=(INFANTRY,),
            required_faction_keywords=(AELDARI,),
        ),
        effect_payload={
            **_generic_rule_ir_payload(corsair_coterie_ir.VENGEFUL_SORROW_DESCRIPTOR_ID),
            "required_non_empty_trigger_context_keys": [DESTROYED_TARGET_UNIT_CONTEXT_KEY],
            "target_forbidden_if_battle_shocked": True,
            "target_forbidden_if_within_engagement_range": True,
        },
    )


def _stratagem_record(
    *,
    record_id: str,
    stratagem_id: str,
    name: str,
    category: StratagemCategory,
    when_descriptor: str,
    target_descriptor: str,
    effect_descriptor: str,
    timing: StratagemTimingDescriptor,
    target_spec: StratagemTargetSpec,
    effect_payload: JsonValue = None,
) -> StratagemCatalogRecord:
    return StratagemCatalogRecord(
        record_id=record_id,
        definition=StratagemDefinition(
            stratagem_id=stratagem_id,
            name=name,
            source_id=SOURCE_RULE_ID,
            command_point_cost=1,
            category=category,
            when_descriptor=when_descriptor,
            target_descriptor=target_descriptor,
            effect_descriptor=effect_descriptor,
            restrictions_descriptor="Corsair Coterie Stratagem.",
            timing=timing,
            restriction_policy=StratagemRestrictionPolicy(),
            target_spec=target_spec,
            handler_id=GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
            effect_payload=effect_payload,
        ),
        availability_kind=StratagemAvailabilityKind.DETACHMENT,
        detachment_id=CORSAIR_COTERIE_DETACHMENT_ID,
    )


def _validate_corsair_stratagem(
    context: StratagemHandlerContext,
    *,
    stratagem_id: str,
    handler_id: str,
    trigger_kind: TimingTriggerKind,
    phase: BattlePhase,
    require_active_player: bool,
) -> StratagemHandlerExecutionResult:
    if type(context) is not StratagemHandlerContext:
        raise GameLifecycleError("Corsair Coterie requires a Stratagem handler context.")
    if context.definition.stratagem_id != stratagem_id:
        return StratagemHandlerExecutionResult.invalid(
            handler_id=handler_id,
            reason="wrong_stratagem",
        )
    if (
        context.definition.handler_id != handler_id
        and context.definition.handler_id != GENERIC_RULE_IR_STRATAGEM_HANDLER_ID
    ):
        return StratagemHandlerExecutionResult.invalid(
            handler_id=handler_id,
            reason="wrong_handler",
        )
    if context.eligibility_context.trigger_kind is not trigger_kind:
        return StratagemHandlerExecutionResult.invalid(handler_id=handler_id, reason="wrong_timing")
    if context.eligibility_context.phase is not phase:
        return StratagemHandlerExecutionResult.invalid(handler_id=handler_id, reason="wrong_phase")
    if (
        require_active_player
        and context.eligibility_context.active_player_id != context.use_record.player_id
    ):
        return StratagemHandlerExecutionResult.invalid(
            handler_id=handler_id,
            reason="wrong_active_player",
        )
    army = _army_for_player(context)
    if not _army_has_corsair_coterie(army):
        return StratagemHandlerExecutionResult.invalid(
            handler_id=handler_id,
            reason="detachment_missing",
        )
    unit = _unit_in_army(army=army, unit_instance_id=_target_unit_id(context))
    if not _unit_has_faction_keyword(unit, AELDARI):
        return StratagemHandlerExecutionResult.invalid(
            handler_id=handler_id,
            reason="target_not_aeldari",
        )
    return StratagemHandlerExecutionResult.applied(handler_id=handler_id)


def _generic_rule_ir_payload(coverage_descriptor_id: str) -> dict[str, JsonValue]:
    payload = corsair_coterie_ir.coverage_rule_ir_payload_by_descriptor_id(coverage_descriptor_id)
    if payload is None:
        raise GameLifecycleError("Corsair Coterie Stratagem RuleIR descriptor is unknown.")
    return {"rule_ir": validate_json_value(payload)}


def _apply_lethal_ruse_mortal_wounds(context: StratagemHandlerContext) -> JsonValue:
    unit = _unit_by_id(context, unit_instance_id=_target_unit_id(context))
    if not _unit_has_keyword(unit, ANHRATHE):
        return None
    enemy_unit_id = _engaged_enemy_unit_id(context)
    manager = DiceRollManager(context.state.game_id, event_log=context.decisions.event_log)
    rolls = tuple(
        manager.roll(
            DiceRollSpec(
                expression=DiceExpression(quantity=1, sides=6),
                reason=f"Lethal Ruse mortal wound roll {index} for {enemy_unit_id}",
                roll_type="corsair_coterie.lethal_ruse_mortal_wounds",
                actor_id=context.use_record.player_id,
            )
        )
        for index in range(1, 7)
    )
    mortal_wounds = sum(1 for roll in rolls if roll.current_total >= 4)
    applied_mortal_wounds = min(
        mortal_wounds,
        _alive_wounds_for_unit(context, unit_instance_id=enemy_unit_id),
    )
    application_payload: JsonValue = None
    if applied_mortal_wounds:
        application = apply_mortal_wounds_to_unit(
            state=context.state,
            target_unit_instance_id=enemy_unit_id,
            mortal_wounds=applied_mortal_wounds,
            spill_over=True,
            dice_manager=manager,
            defender_player_id=_unit_owner(context, unit_instance_id=enemy_unit_id),
        )
        application_payload = validate_json_value(application.to_payload())
    return validate_json_value(
        {
            "effect_kind": f"{LETHAL_RUSE_EFFECT_KIND}_mortal_wounds",
            "enemy_unit_instance_id": enemy_unit_id,
            "rolls": [roll.to_payload() for roll in rolls],
            "mortal_wounds": mortal_wounds,
            "applied_mortal_wounds": applied_mortal_wounds,
            "mortal_wound_application": application_payload,
        }
    )


def _request_triggered_move(
    *,
    context: StratagemHandlerContext,
    handler_id: str,
    unit_instance_id: str,
    roll_type: str,
    source_step: str,
    movement_kind: TriggeredMovementKind,
    allow_battle_shocked: bool,
    replay_effect_kind: str,
) -> tuple[DecisionRequest, JsonValue]:
    roll_state = DiceRollManager(context.state.game_id, event_log=context.decisions.event_log).roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason=f"{context.definition.name} move distance for {unit_instance_id}",
            roll_type=roll_type,
            actor_id=context.use_record.player_id,
        )
    )
    distance_roll_payload = validate_json_value(roll_state.to_payload())
    descriptor = TriggeredMovementDescriptor(
        movement_kind=movement_kind,
        source_rule_id=SOURCE_RULE_ID,
        trigger_timing=ReactionWindow(
            phase=BattlePhase.SHOOTING,
            window_kind=ReactionWindowKind.RULE_TRIGGER,
            source_step=source_step,
            source_event_id=_trigger_event_id(context),
        ),
        max_distance_inches=float(roll_state.current_total + 1),
        movement_mode=MovementMode.NORMAL,
        allow_battle_shocked=allow_battle_shocked,
        allow_within_engagement_range=False,
        one_per_phase=False,
        optional=True,
    )
    request = triggered_movement_unit_selection_request(
        state=context.state,
        player_id=context.use_record.player_id,
        descriptor=descriptor,
        eligible_units=(
            TriggeredMovementEligibleUnit(
                unit_instance_id=unit_instance_id,
                hook_id=handler_id,
                source_id=SOURCE_RULE_ID,
                replay_payload={
                    "effect_kind": replay_effect_kind,
                    "stratagem_use_id": context.use_record.use_id,
                    "distance_roll": distance_roll_payload,
                },
                decision_effect_payload=None,
            ),
        ),
    )
    context.decisions.request_decision(request)
    return request, distance_roll_payload


def _triggered_move_event_payload(
    *,
    context: StratagemHandlerContext,
    request_id: str,
    distance_roll: JsonValue,
) -> JsonValue:
    return validate_json_value(
        {
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "active_player_id": context.state.active_player_id,
            "phase": BattlePhase.SHOOTING.value,
            "stratagem_use": context.use_record.to_payload(),
            "distance_roll": distance_roll,
            "request_id": request_id,
            "phase_body_status": "corsair_coterie_triggered_movement_pending",
        }
    )


def _improved_ap(value: CharacteristicValue) -> CharacteristicValue:
    if type(value) is not CharacteristicValue:
        raise GameLifecycleError("Outcast Ambush AP modifier requires a CharacteristicValue.")
    return CharacteristicValue.from_raw(value.characteristic, value.final - 1)


def _abilities_with_rapid_fire_one(
    abilities: tuple[AbilityDescriptor, ...],
) -> tuple[AbilityDescriptor, ...]:
    updated: list[AbilityDescriptor] = []
    rapid_fire_added = False
    for ability in abilities:
        if ability.ability_kind is not AbilityKind.RAPID_FIRE:
            updated.append(ability)
            continue
        value = _ability_integer_value(ability)
        updated.append(AbilityDescriptor.rapid_fire(value + 1))
        rapid_fire_added = True
    if not rapid_fire_added:
        updated.append(AbilityDescriptor.rapid_fire(1))
    return tuple(sorted(updated, key=lambda ability: ability.ability_id))


def _ability_integer_value(ability: AbilityDescriptor) -> int:
    if len(ability.parameters) != 1:
        raise GameLifecycleError("Rapid Fire ability requires one value parameter.")
    parameter = ability.parameters[0]
    if type(parameter) is not AbilityParameter or parameter.name != "value":
        raise GameLifecycleError("Rapid Fire ability parameter drift.")
    if type(parameter.value) is not int:
        raise GameLifecycleError("Rapid Fire ability value must be an integer.")
    return parameter.value


def _unit_within_controlled_objective_range(
    context: StratagemHandlerContext,
    *,
    unit_instance_id: str,
) -> bool:
    record = _objective_control_record(context)
    return any(
        result.controlled_by_player_id == context.use_record.player_id
        and _objective_result_has_unit(result=result, unit_instance_id=unit_instance_id)
        for result in record.results
    )


def _objective_control_record(context: StratagemHandlerContext) -> ObjectiveControlRecord:
    if context.state.mission_setup is None or context.state.battlefield_state is None:
        raise GameLifecycleError("Corsair Coterie objective checks require mission setup.")
    return resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            context.state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=context.eligibility_context.phase,
            ruleset_descriptor=context.ruleset_descriptor,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
    )


def _objective_result_has_unit(
    *,
    result: ObjectiveControlResult,
    unit_instance_id: str,
) -> bool:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    return any(
        contribution.unit_instance_id == requested_unit_id for contribution in result.contributors
    )


def _unit_is_engaged(
    context: StratagemHandlerContext,
    *,
    unit_instance_id: str,
) -> bool:
    battlefield = context.state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Corsair Coterie engagement checks require battlefield state.")
    try:
        unit_placement = battlefield.unit_placement_by_id(unit_instance_id)
    except PlacementError as exc:
        raise GameLifecycleError("Corsair Coterie target unit is not placed.") from exc
    friendly_models = tuple(
        geometry_model_for_placement(
            model=_model_instance_by_id(context.state, placement.model_instance_id),
            placement=placement,
        )
        for placement in unit_placement.model_placements
    )
    for placed_army in battlefield.placed_armies:
        if placed_army.player_id == unit_placement.player_id:
            continue
        for enemy_unit_placement in placed_army.unit_placements:
            for enemy_placement in enemy_unit_placement.model_placements:
                enemy_model = geometry_model_for_placement(
                    model=_model_instance_by_id(context.state, enemy_placement.model_instance_id),
                    placement=enemy_placement,
                )
                if any(
                    friendly_model.is_within_engagement_range(
                        enemy_model,
                        horizontal_inches=context.ruleset_descriptor.engagement_policy.horizontal_inches,
                        vertical_inches=context.ruleset_descriptor.engagement_policy.vertical_inches,
                    )
                    for friendly_model in friendly_models
                ):
                    return True
    return False


def _alive_wounds_for_unit(
    context: StratagemHandlerContext,
    *,
    unit_instance_id: str,
) -> int:
    return sum(
        model.wounds_remaining
        for model in rules_unit_view_by_id(
            state=context.state,
            unit_instance_id=unit_instance_id,
        ).alive_models()
    )


def _unit_has_effect(state: object, *, unit_instance_id: str, effect_kind: str) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Corsair Coterie effect lookup requires GameState.")
    for effect in state.persisting_effects_for_unit(unit_instance_id):
        payload = effect.effect_payload
        if isinstance(payload, dict) and payload.get("effect_kind") == effect_kind:
            return True
    return False


def _effect_event_payload(
    *,
    context: StratagemHandlerContext,
    effect: PersistingEffect,
) -> JsonValue:
    return validate_json_value(_effect_event_payload_object(context=context, effect=effect))


def _effect_event_payload_object(
    *,
    context: StratagemHandlerContext,
    effect: PersistingEffect,
) -> dict[str, JsonValue]:
    stratagem_use_payload = validate_json_value(context.use_record.to_payload())
    persisting_effect_payload = validate_json_value(effect.to_payload())
    return {
        "game_id": context.state.game_id,
        "battle_round": context.state.battle_round,
        "active_player_id": context.state.active_player_id,
        "phase": context.eligibility_context.phase.value,
        "stratagem_use": stratagem_use_payload,
        "persisting_effect": persisting_effect_payload,
    }


def _active_player_id(context: StratagemHandlerContext) -> str:
    active_player_id = context.state.active_player_id
    if active_player_id is None:
        raise GameLifecycleError("Corsair Coterie requires an active player.")
    return active_player_id


def _target_unit_id(context: StratagemHandlerContext) -> str:
    target_unit_id = context.target_binding.target_unit_instance_id
    if target_unit_id is None:
        raise GameLifecycleError("Corsair Coterie Stratagem requires a target unit.")
    return target_unit_id


def _trigger_payload(context: StratagemHandlerContext) -> dict[str, JsonValue]:
    payload = context.eligibility_context.trigger_payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Corsair Coterie requires trigger context payload.")
    return payload


def _fell_back_unit_id(context: StratagemHandlerContext) -> str:
    trigger_payload = _trigger_payload(context)
    raw_unit_id = trigger_payload.get(JUST_FELL_BACK_UNIT_CONTEXT_KEY)
    if type(raw_unit_id) is not str:
        raise GameLifecycleError("Corsair Coterie Fall Back context is missing unit id.")
    return _validate_identifier("fell_back_unit_instance_id", raw_unit_id)


def _shot_unit_id(context: StratagemHandlerContext) -> str:
    trigger_payload = _trigger_payload(context)
    raw_unit_id = trigger_payload.get(JUST_SHOT_UNIT_CONTEXT_KEY)
    if type(raw_unit_id) is not str:
        raise GameLifecycleError("Corsair Coterie shot context is missing unit id.")
    return _validate_identifier("shot_unit_instance_id", raw_unit_id)


def _trigger_event_id(context: StratagemHandlerContext) -> str:
    trigger_payload = _trigger_payload(context)
    for key in ("attack_sequence_completed_event_id", "movement_activation_completed_event_id"):
        raw_event_id = trigger_payload.get(key)
        if type(raw_event_id) is str:
            return _validate_identifier(key, raw_event_id)
    return context.use_record.use_id


def _engaged_enemy_unit_id(context: StratagemHandlerContext) -> str:
    selection = context.use_record.effect_selection
    if not isinstance(selection, dict):
        raise GameLifecycleError("Lethal Ruse requires engaged enemy effect selection.")
    if selection.get("effect_selection_kind") != ENGAGED_ENEMY_UNIT_EFFECT_SELECTION_KIND:
        raise GameLifecycleError("Lethal Ruse effect selection kind drift.")
    raw_unit_id = selection.get(ENGAGED_ENEMY_UNIT_CONTEXT_KEY)
    if type(raw_unit_id) is not str:
        raise GameLifecycleError("Lethal Ruse effect selection is missing enemy unit.")
    return _validate_identifier("engaged_enemy_unit_instance_id", raw_unit_id)


def _engaged_enemy_unit_ids(context: StratagemHandlerContext) -> tuple[str, ...]:
    raw_unit_ids = _trigger_payload(context).get(ENGAGED_ENEMY_UNIT_IDS_CONTEXT_KEY)
    if not isinstance(raw_unit_ids, list):
        return ()
    return tuple(
        sorted(_validate_identifier("engaged_enemy_unit_id", value) for value in raw_unit_ids)
    )


def _unit_selected_to_fight(
    context: StratagemHandlerContext,
    *,
    unit_instance_id: str,
) -> bool:
    fight_state = context.state.fight_phase_state
    if fight_state is None:
        return False
    return unit_instance_id in fight_state.fight_order_state.selected_to_fight_unit_ids


def _unit_selected_to_shoot(
    context: StratagemHandlerContext,
    *,
    unit_instance_id: str,
) -> bool:
    shooting_state = context.state.shooting_phase_state
    if shooting_state is None:
        return False
    return (
        unit_instance_id in shooting_state.selected_unit_ids
        or unit_instance_id in shooting_state.shot_unit_ids
    )


def _army_for_player(context: StratagemHandlerContext) -> ArmyDefinition:
    for army in context.state.army_definitions:
        if army.player_id == context.use_record.player_id:
            return army
    raise GameLifecycleError("Corsair Coterie player army is unknown.")


def _army_has_corsair_coterie(army: ArmyDefinition) -> bool:
    return (
        army.detachment_selection.faction_id == AELDARI_FACTION_ID
        and CORSAIR_COTERIE_DETACHMENT_ID in army.detachment_selection.detachment_ids
    )


def _unit_in_army(*, army: ArmyDefinition, unit_instance_id: str) -> UnitInstance:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for unit in army.units:
        if unit.unit_instance_id == requested_unit_id:
            return unit
    raise GameLifecycleError("Corsair Coterie target unit is not in the selected army.")


def _unit_by_id(context: StratagemHandlerContext, *, unit_instance_id: str) -> UnitInstance:
    return _unit_by_id_for_state(context.state, unit_instance_id=unit_instance_id)


def _unit_by_id_for_state(state: object, *, unit_instance_id: str) -> UnitInstance:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Corsair Coterie unit lookup requires GameState.")
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return unit
    raise GameLifecycleError("Corsair Coterie unit is unknown.")


def _unit_owner(context: StratagemHandlerContext, *, unit_instance_id: str) -> str:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in context.state.army_definitions:
        if any(unit.unit_instance_id == requested_unit_id for unit in army.units):
            return army.player_id
    raise GameLifecycleError("Corsair Coterie unit owner is unknown.")


def _model_instance_by_id(state: object, model_instance_id: str) -> ModelInstance:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    for army in _armies_for_state(state):
        for unit in army.units:
            for model in unit.own_models:
                if model.model_instance_id == requested_model_id:
                    return model
    raise GameLifecycleError("Corsair Coterie model is unknown.")


def _armies_for_state(state: object) -> tuple[ArmyDefinition, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Corsair Coterie army lookup requires GameState.")
    return tuple(state.army_definitions)


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    canonical = _canonical_keyword(keyword)
    return any(_canonical_keyword(stored) == canonical for stored in unit.keywords)


def _unit_has_faction_keyword(unit: UnitInstance, keyword: str) -> bool:
    canonical = _canonical_keyword(keyword)
    return any(_canonical_keyword(stored) == canonical for stored in unit.faction_keywords)


_validate_identifier = IdentifierValidator(GameLifecycleError)
