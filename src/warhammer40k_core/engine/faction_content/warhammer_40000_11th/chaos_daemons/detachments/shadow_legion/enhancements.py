from __future__ import annotations

from typing import TypedDict, cast

from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.faction_aliases import CHAOS_DAEMONS_FACTION_ID
from warhammer40k_core.engine.army_mustering import ArmyDefinition, EnhancementAssignment
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    PlacementError,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.damage_allocation import (
    SELECT_FEEL_NO_PAIN_DECISION_TYPE,
    MortalWoundApplication,
    MortalWoundApplicationProgress,
    continue_mortal_wound_application,
    resolve_mortal_wound_feel_no_pain_decision,
    unit_owner_player_id,
)
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.enhancement_effects import (
    EnhancementDatasheetAbilityGrant,
    EnhancementEffectBinding,
    EnhancementEffectContext,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.fight_phase_start_hooks import (
    SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE,
    FightPhaseStartHookBinding,
    FightPhaseStartRequestContext,
    FightPhaseStartResultContext,
)
from warhammer40k_core.engine.mortal_wound_feel_no_pain_hooks import (
    MortalWoundFeelNoPainContinuationContext,
    MortalWoundFeelNoPainContinuationHookBinding,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.reserves import ReserveOrigin
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id
from warhammer40k_core.engine.turn_end_hooks import (
    SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
    TurnEndHookBinding,
    TurnEndRequestContext,
    TurnEndResultContext,
)
from warhammer40k_core.engine.unit_destroyed_hooks import (
    UnitDestroyedContext,
    UnitDestroyedHookBinding,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_proximity import unit_within_enemy_engagement_range
from warhammer40k_core.geometry.volume import Model as GeometryModel


class _MaliceMadeManifestMortalWoundSourceContextPayload(TypedDict):
    source_kind: str
    phase: str
    resolution_payload: dict[str, JsonValue]


CONTRIBUTION_ID = "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:enhancements"

DETACHMENT_ID = "shadow-legion"
SHADOW_LEGION_KEYWORD = "SHADOW LEGION"

LEAPING_SHADOWS_ENHANCEMENT_ID = "000009980002"
LEAPING_SHADOWS_SOURCE_RULE_ID = (
    "phase17f:phase17e:enhancement:chaos-daemons:shadow-legion:000009980002"
)
LEAPING_SHADOWS_EFFECT_ID = (
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:"
    "enhancement:leaping_shadows:scouts_9"
)
LEAPING_SHADOWS_ABILITY_ID = "chaos-daemons:shadow-legion:leaping-shadows:scouts-9"
LEAPING_SHADOWS_SCOUTS_DISTANCE = '9"'

MALICE_MADE_MANIFEST_ENHANCEMENT_ID = "000009980005"
MALICE_MADE_MANIFEST_SOURCE_RULE_ID = (
    "phase17f:phase17e:enhancement:chaos-daemons:shadow-legion:000009980005"
)
MALICE_MADE_MANIFEST_HOOK_ID = (
    "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:enhancement:malice_made_manifest"
)
MALICE_MADE_MANIFEST_MORTAL_WOUND_FNP_HOOK_ID = f"{MALICE_MADE_MANIFEST_HOOK_ID}:mortal-wound-fnp"
MALICE_MADE_MANIFEST_MORTAL_WOUNDS_SOURCE_KIND = (
    "chaos_daemons_shadow_legion_malice_made_manifest_mortal_wounds"
)
MALICE_MADE_MANIFEST_SUBMISSION_KIND = "chaos_daemons_shadow_legion_malice_made_manifest"
MALICE_MADE_MANIFEST_D6_ROLL_TYPE = "chaos_daemons.shadow_legion.malice_made_manifest_d6"
MALICE_MADE_MANIFEST_D3_ROLL_TYPE = (
    "chaos_daemons.shadow_legion.malice_made_manifest_mortal_wounds_d3"
)
MALICE_MADE_MANIFEST_NO_EFFECT_EVENT = "chaos_daemons_shadow_legion_malice_made_manifest_no_effect"
MALICE_MADE_MANIFEST_PENDING_EVENT = (
    "chaos_daemons_shadow_legion_malice_made_manifest_mortal_wounds_pending"
)
MALICE_MADE_MANIFEST_RESOLVED_EVENT = "chaos_daemons_shadow_legion_malice_made_manifest_resolved"

FADE_TO_DARKNESS_ENHANCEMENT_ID = "000009980004"
FADE_TO_DARKNESS_SOURCE_RULE_ID = (
    "phase17f:phase17e:enhancement:chaos-daemons:shadow-legion:000009980004"
)
SOURCE_RULE_ID = FADE_TO_DARKNESS_SOURCE_RULE_ID
ENHANCEMENT_ID = FADE_TO_DARKNESS_ENHANCEMENT_ID
HOOK_ID = "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:enhancement:fade_to_darkness"
UNIT_DESTROYED_HOOK_ID = f"{HOOK_ID}:unit-destroyed"
TURN_END_HOOK_ID = f"{HOOK_ID}:turn-end-reserves"
SUBMISSION_KIND = "chaos_daemons_shadow_legion_fade_to_darkness_turn_end"
ELIGIBLE_EVENT = "chaos_daemons_shadow_legion_fade_to_darkness_eligible"
USED_EVENT = "chaos_daemons_shadow_legion_fade_to_darkness_used"
DECLINED_EVENT = "chaos_daemons_shadow_legion_fade_to_darkness_declined"


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        enhancement_effect_bindings=(
            EnhancementEffectBinding(
                effect_id=LEAPING_SHADOWS_EFFECT_ID,
                source_id=LEAPING_SHADOWS_SOURCE_RULE_ID,
                enhancement_id=LEAPING_SHADOWS_ENHANCEMENT_ID,
                handler=leaping_shadows_effect,
            ),
        ),
        unit_destroyed_hook_bindings=(
            UnitDestroyedHookBinding(
                hook_id=UNIT_DESTROYED_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=record_fade_to_darkness_destroyed_enemy_unit,
            ),
        ),
        turn_end_hook_bindings=(
            TurnEndHookBinding(
                hook_id=TURN_END_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                request_handler=fade_to_darkness_turn_end_request,
                result_handler=apply_fade_to_darkness_turn_end_result,
            ),
        ),
        fight_phase_start_hook_bindings=(
            FightPhaseStartHookBinding(
                hook_id=MALICE_MADE_MANIFEST_HOOK_ID,
                source_id=MALICE_MADE_MANIFEST_SOURCE_RULE_ID,
                request_handler=malice_made_manifest_fight_phase_start_request,
                result_handler=apply_malice_made_manifest_fight_phase_start_result,
            ),
        ),
        mortal_wound_feel_no_pain_hook_bindings=(
            MortalWoundFeelNoPainContinuationHookBinding(
                hook_id=MALICE_MADE_MANIFEST_MORTAL_WOUND_FNP_HOOK_ID,
                source_id=MALICE_MADE_MANIFEST_SOURCE_RULE_ID,
                source_kind=MALICE_MADE_MANIFEST_MORTAL_WOUNDS_SOURCE_KIND,
                handler=apply_malice_made_manifest_mortal_wound_feel_no_pain_decision,
            ),
        ),
    )


def leaping_shadows_effect(
    context: EnhancementEffectContext,
) -> tuple[EnhancementDatasheetAbilityGrant, ...]:
    if type(context) is not EnhancementEffectContext:
        raise GameLifecycleError("Leaping Shadows requires an EnhancementEffectContext.")
    if context.assignment.enhancement_id != LEAPING_SHADOWS_ENHANCEMENT_ID:
        return ()
    if not (
        context.army.detachment_selection.faction_id == CHAOS_DAEMONS_FACTION_ID
        and DETACHMENT_ID in context.army.detachment_selection.detachment_ids
    ):
        raise GameLifecycleError("Leaping Shadows requires Shadow Legion.")
    if not _unit_has_keyword(context.target_unit, SHADOW_LEGION_KEYWORD):
        raise GameLifecycleError("Leaping Shadows requires a Shadow Legion model.")
    view = rules_unit_view_by_id(
        state=context.state,
        unit_instance_id=context.target_unit.unit_instance_id,
    )
    if view.owner_player_id != context.army.player_id:
        raise GameLifecycleError("Leaping Shadows rules unit owner drift.")
    descriptor = _leaping_shadows_scouts_descriptor()
    return tuple(
        EnhancementDatasheetAbilityGrant(
            effect_id=LEAPING_SHADOWS_EFFECT_ID,
            source_id=LEAPING_SHADOWS_SOURCE_RULE_ID,
            enhancement_id=LEAPING_SHADOWS_ENHANCEMENT_ID,
            target_unit_instance_id=component.unit.unit_instance_id,
            datasheet_ability=descriptor,
            replay_payload={
                "effect_kind": "leaping_shadows_scouts_9",
                "assignment_source_id": context.assignment.source_id,
                "target_unit_selection_id": context.assignment.target_unit_selection_id,
                "bearer_unit_instance_id": context.target_unit.unit_instance_id,
                "target_rules_unit_instance_id": view.unit_instance_id,
                "component_unit_instance_id": component.unit.unit_instance_id,
                "scouts_distance_inches": 9,
            },
        )
        for component in view.components
    )


def malice_made_manifest_fight_phase_start_request(
    context: FightPhaseStartRequestContext,
) -> DecisionRequest | None:
    if type(context) is not FightPhaseStartRequestContext:
        raise GameLifecycleError("Malice Made Manifest requires a Fight-start context.")
    if context.state.current_battle_phase is not BattlePhase.FIGHT:
        return None
    active_player_id = _active_player_id(context.state)
    for army in _shadow_legion_armies(context.state):
        for _assignment, unit in _assigned_units(
            army,
            enhancement_id=MALICE_MADE_MANIFEST_ENHANCEMENT_ID,
        ):
            if not _unit_has_keyword(unit, SHADOW_LEGION_KEYWORD):
                raise GameLifecycleError("Malice Made Manifest requires a Shadow Legion model.")
            bearer_rules_unit = rules_unit_view_by_id(
                state=context.state,
                unit_instance_id=unit.unit_instance_id,
            )
            if bearer_rules_unit.owner_player_id != army.player_id:
                raise GameLifecycleError("Malice Made Manifest rules unit owner drift.")
            if _malice_made_manifest_recorded_this_fight_start(
                context=context,
                bearer_rules_unit_instance_id=bearer_rules_unit.unit_instance_id,
            ):
                continue
            eligible_enemy_unit_ids = _enemy_rules_unit_ids_within_engagement_range(
                state=context.state,
                bearer_unit_instance_id=unit.unit_instance_id,
            )
            if not eligible_enemy_unit_ids:
                continue
            return DecisionRequest(
                request_id=context.state.next_decision_request_id(),
                decision_type=SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE,
                actor_id=army.player_id,
                payload={
                    "game_id": context.state.game_id,
                    "battle_round": context.state.battle_round,
                    "active_player_id": active_player_id,
                    "phase": BattlePhase.FIGHT.value,
                    "player_id": army.player_id,
                    "source_rule_id": MALICE_MADE_MANIFEST_SOURCE_RULE_ID,
                    "hook_id": MALICE_MADE_MANIFEST_HOOK_ID,
                    "enhancement_id": MALICE_MADE_MANIFEST_ENHANCEMENT_ID,
                    "bearer_unit_instance_id": unit.unit_instance_id,
                    "bearer_rules_unit_instance_id": bearer_rules_unit.unit_instance_id,
                    "eligible_enemy_unit_instance_ids": list(eligible_enemy_unit_ids),
                },
                options=tuple(
                    _malice_made_manifest_target_option(
                        game_id=context.state.game_id,
                        battle_round=context.state.battle_round,
                        active_player_id=active_player_id,
                        player_id=army.player_id,
                        bearer_unit_instance_id=unit.unit_instance_id,
                        bearer_rules_unit_instance_id=bearer_rules_unit.unit_instance_id,
                        target_enemy_unit_instance_id=enemy_unit_id,
                    )
                    for enemy_unit_id in eligible_enemy_unit_ids
                ),
            )
    return None


def apply_malice_made_manifest_fight_phase_start_result(
    context: FightPhaseStartResultContext,
) -> bool | LifecycleStatus:
    if type(context) is not FightPhaseStartResultContext:
        raise GameLifecycleError("Malice Made Manifest requires a Fight-start result context.")
    request_payload = _payload_object(context.request.payload)
    if request_payload.get("hook_id") != MALICE_MADE_MANIFEST_HOOK_ID:
        return False
    result_payload = _payload_object(context.result.payload)
    _validate_malice_made_manifest_result_payload_matches_request(
        request_payload=request_payload,
        result_payload=result_payload,
    )
    player_id = _payload_string(result_payload, "player_id")
    bearer_unit_id = _payload_string(result_payload, "bearer_unit_instance_id")
    bearer_rules_unit_id = _payload_string(result_payload, "bearer_rules_unit_instance_id")
    target_enemy_unit_id = _payload_string(result_payload, "target_enemy_unit_instance_id")
    eligible_enemy_unit_ids = _payload_string_tuple(
        request_payload,
        key="eligible_enemy_unit_instance_ids",
    )
    if target_enemy_unit_id not in eligible_enemy_unit_ids:
        raise GameLifecycleError("Malice Made Manifest target was not in the request snapshot.")
    army = _army_for_player(tuple(context.state.army_definitions), player_id=player_id)
    if not _assigned_malice_made_manifest_unit_id_matches(
        army,
        unit_instance_id=bearer_unit_id,
    ):
        raise GameLifecycleError("Malice Made Manifest assignment no longer matches unit.")
    bearer_rules_unit = rules_unit_view_by_id(
        state=context.state,
        unit_instance_id=bearer_unit_id,
    )
    if bearer_rules_unit.unit_instance_id != bearer_rules_unit_id:
        raise GameLifecycleError("Malice Made Manifest bearer rules unit drift.")
    if target_enemy_unit_id not in _enemy_rules_unit_ids_within_engagement_range(
        state=context.state,
        bearer_unit_instance_id=bearer_unit_id,
    ):
        raise GameLifecycleError("Malice Made Manifest target is no longer eligible.")

    dice_manager = DiceRollManager(context.state.game_id, event_log=context.decisions.event_log)
    d6_result = dice_manager.roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason="Malice Made Manifest",
            roll_type=MALICE_MADE_MANIFEST_D6_ROLL_TYPE,
            actor_id=bearer_rules_unit_id,
        )
    )
    if d6_result.current_total == 1:
        context.decisions.event_log.append(
            MALICE_MADE_MANIFEST_NO_EFFECT_EVENT,
            _malice_made_manifest_resolution_payload(
                context=context,
                player_id=player_id,
                bearer_unit_instance_id=bearer_unit_id,
                bearer_rules_unit_instance_id=bearer_rules_unit_id,
                target_enemy_unit_instance_id=target_enemy_unit_id,
                d6_result=validate_json_value(d6_result.to_payload()),
                d3_result=None,
                mortal_wounds=0,
            ),
        )
        return True

    d3_payload: JsonValue = None
    if d6_result.current_total == 6:
        mortal_wounds = 3
    else:
        d3_result = dice_manager.roll_d3(
            reason="Malice Made Manifest mortal wounds",
            roll_type=MALICE_MADE_MANIFEST_D3_ROLL_TYPE,
            actor_id=target_enemy_unit_id,
        )
        mortal_wounds = d3_result.value
        d3_payload = validate_json_value(d3_result.to_payload())
    resolution_payload = _malice_made_manifest_resolution_payload(
        context=context,
        player_id=player_id,
        bearer_unit_instance_id=bearer_unit_id,
        bearer_rules_unit_instance_id=bearer_rules_unit_id,
        target_enemy_unit_instance_id=target_enemy_unit_id,
        d6_result=validate_json_value(d6_result.to_payload()),
        d3_result=d3_payload,
        mortal_wounds=mortal_wounds,
    )
    progress = MortalWoundApplicationProgress.start(
        application_id=(
            f"malice-made-manifest:{context.state.game_id}:"
            f"round-{context.state.battle_round:02d}:"
            f"{bearer_rules_unit_id}:{target_enemy_unit_id}:{context.result.result_id}"
        ),
        source_rule_id=MALICE_MADE_MANIFEST_SOURCE_RULE_ID,
        source_context=_malice_made_manifest_mortal_wound_source_context(
            resolution_payload=resolution_payload
        ),
        target_unit_instance_id=target_enemy_unit_id,
        defender_player_id=unit_owner_player_id(
            state=context.state,
            unit_instance_id=target_enemy_unit_id,
        ),
        mortal_wounds=mortal_wounds,
        spill_over=True,
    )
    routed = continue_mortal_wound_application(
        state=context.state,
        request_id=context.state.next_decision_request_id(),
        progress=progress,
        dice_manager=dice_manager,
    )
    routed_status = _resolve_routed_malice_made_manifest_mortal_wounds(
        state=context.state,
        decisions=context.decisions,
        feel_no_pain_result_id=None,
        routed_request=routed.request,
        routed_application=routed.application,
        routed_progress=routed.progress,
    )
    return True if routed_status is None else routed_status


def apply_malice_made_manifest_mortal_wound_feel_no_pain_decision(
    context: MortalWoundFeelNoPainContinuationContext,
) -> LifecycleStatus | None:
    if type(context) is not MortalWoundFeelNoPainContinuationContext:
        raise GameLifecycleError("Malice Made Manifest FNP continuation requires context.")
    routed = resolve_mortal_wound_feel_no_pain_decision(
        state=context.state,
        request=context.request,
        result=context.result,
        next_request_id=context.state.next_decision_request_id(),
        dice_manager=context.dice_manager,
    )
    return _resolve_routed_malice_made_manifest_mortal_wounds(
        state=context.state,
        decisions=context.decisions,
        feel_no_pain_result_id=context.result.result_id,
        routed_request=routed.request,
        routed_application=routed.application,
        routed_progress=routed.progress,
    )


def record_fade_to_darkness_destroyed_enemy_unit(context: UnitDestroyedContext) -> None:
    if type(context) is not UnitDestroyedContext:
        raise GameLifecycleError("Fade to Darkness requires a unit-destroyed context.")
    if context.completed_phase is not BattlePhase.FIGHT:
        return
    attacking_unit_value = context.model_destroyed_payload.get("attacking_unit_instance_id")
    if type(attacking_unit_value) is not str or not attacking_unit_value.strip():
        return
    attacking_unit_id = _validate_identifier("attacking_unit_instance_id", attacking_unit_value)
    for army in _shadow_legion_armies(context.state):
        if army.player_id != context.destroying_player_id:
            continue
        if not _assigned_fade_unit_id_matches(army, unit_instance_id=attacking_unit_id):
            continue
        if _eligible_event_recorded_for_destroyed_unit(
            context,
            unit_instance_id=attacking_unit_id,
            destroyed_unit_instance_id=context.destroyed_unit_instance_id,
        ):
            return
        context.decisions.event_log.append(
            ELIGIBLE_EVENT,
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "active_player_id": context.state.active_player_id,
                "phase": context.completed_phase.value,
                "player_id": army.player_id,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": UNIT_DESTROYED_HOOK_ID,
                "enhancement_id": ENHANCEMENT_ID,
                "target_unit_instance_id": attacking_unit_id,
                "destroyed_enemy_unit_instance_id": context.destroyed_unit_instance_id,
                "destroyed_player_id": context.destroyed_player_id,
                "model_destroyed_event_id": context.model_destroyed_event_id,
            },
        )
        return


def fade_to_darkness_turn_end_request(context: TurnEndRequestContext) -> DecisionRequest | None:
    if type(context) is not TurnEndRequestContext:
        raise GameLifecycleError("Fade to Darkness requires a turn-end request context.")
    if context.completed_phase is not BattlePhase.FIGHT:
        return None
    active_player_id = _active_player_id(context.state)
    for army in _shadow_legion_armies(context.state):
        for _assignment, unit in _assigned_units(army, enhancement_id=ENHANCEMENT_ID):
            destroyed_enemy_unit_ids = _destroyed_enemy_unit_ids_for_fade_unit(
                context,
                player_id=army.player_id,
                unit_instance_id=unit.unit_instance_id,
            )
            if not destroyed_enemy_unit_ids:
                continue
            if _decision_recorded_this_phase(
                context,
                unit_instance_id=unit.unit_instance_id,
            ):
                continue
            if not _unit_can_enter_strategic_reserves(
                context.state,
                unit_instance_id=unit.unit_instance_id,
            ):
                continue
            return DecisionRequest(
                request_id=context.state.next_decision_request_id(),
                decision_type=SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
                actor_id=army.player_id,
                payload={
                    "game_id": context.state.game_id,
                    "battle_round": context.state.battle_round,
                    "active_player_id": active_player_id,
                    "phase": context.completed_phase.value,
                    "player_id": army.player_id,
                    "source_rule_id": SOURCE_RULE_ID,
                    "hook_id": TURN_END_HOOK_ID,
                    "enhancement_id": ENHANCEMENT_ID,
                    "target_unit_instance_id": unit.unit_instance_id,
                    "destroyed_enemy_unit_instance_ids": list(destroyed_enemy_unit_ids),
                },
                options=(
                    _fade_to_darkness_option(
                        player_id=army.player_id,
                        unit_instance_id=unit.unit_instance_id,
                        use_ability=True,
                    ),
                    _fade_to_darkness_option(
                        player_id=army.player_id,
                        unit_instance_id=unit.unit_instance_id,
                        use_ability=False,
                    ),
                ),
            )
    return None


def apply_fade_to_darkness_turn_end_result(context: TurnEndResultContext) -> bool:
    if type(context) is not TurnEndResultContext:
        raise GameLifecycleError("Fade to Darkness requires a turn-end result context.")
    request_payload = _payload_object(context.request.payload)
    if request_payload.get("hook_id") != TURN_END_HOOK_ID:
        return False
    result_payload = _payload_object(context.result.payload)
    _validate_result_payload_matches_request(
        request_payload=request_payload,
        result_payload=result_payload,
    )
    player_id = _payload_string(result_payload, "player_id")
    unit_instance_id = _payload_string(result_payload, "target_unit_instance_id")
    use_ability = _payload_bool(result_payload, "use_ability")
    army = _army_for_player(tuple(context.state.army_definitions), player_id=player_id)
    if not _assigned_fade_unit_id_matches(army, unit_instance_id=unit_instance_id):
        raise GameLifecycleError("Fade to Darkness assignment no longer matches unit.")
    if not use_ability:
        context.decisions.event_log.append(
            DECLINED_EVENT,
            _fade_to_darkness_event_payload(
                context=context,
                player_id=player_id,
                unit_instance_id=unit_instance_id,
                reserve_state_payload=None,
                use_ability=False,
            ),
        )
        return True
    if not _destroyed_enemy_unit_ids_for_fade_unit(
        context,
        player_id=player_id,
        unit_instance_id=unit_instance_id,
    ):
        raise GameLifecycleError("Fade to Darkness unit no longer has a destroyed enemy unit.")
    if not _unit_can_enter_strategic_reserves(context.state, unit_instance_id=unit_instance_id):
        raise GameLifecycleError("Fade to Darkness unit is no longer eligible.")
    reserve_state = context.state.reposition_unit_to_strategic_reserves(
        player_id=player_id,
        unit_instance_id=unit_instance_id,
        reserve_origin=ReserveOrigin.DURING_BATTLE_ABILITY,
        source_rule_ids=(SOURCE_RULE_ID,),
    )
    context.decisions.event_log.append(
        USED_EVENT,
        _fade_to_darkness_event_payload(
            context=context,
            player_id=player_id,
            unit_instance_id=unit_instance_id,
            reserve_state_payload=cast(JsonValue, reserve_state.to_payload()),
            use_ability=True,
        ),
    )
    return True


def _fade_to_darkness_option(
    *,
    player_id: str,
    unit_instance_id: str,
    use_ability: bool,
) -> DecisionOption:
    action = "use" if use_ability else "decline"
    return DecisionOption(
        option_id=f"chaos-daemons:shadow-legion:fade-to-darkness:{unit_instance_id}:{action}",
        label="Use Fade to Darkness" if use_ability else "Decline Fade to Darkness",
        payload={
            "submission_kind": SUBMISSION_KIND,
            "player_id": player_id,
            "source_rule_id": SOURCE_RULE_ID,
            "hook_id": TURN_END_HOOK_ID,
            "enhancement_id": ENHANCEMENT_ID,
            "target_unit_instance_id": unit_instance_id,
            "use_ability": use_ability,
        },
    )


def _malice_made_manifest_target_option(
    *,
    game_id: str,
    battle_round: int,
    active_player_id: str,
    player_id: str,
    bearer_unit_instance_id: str,
    bearer_rules_unit_instance_id: str,
    target_enemy_unit_instance_id: str,
) -> DecisionOption:
    return DecisionOption(
        option_id=(
            "chaos-daemons:shadow-legion:malice-made-manifest:"
            f"{bearer_rules_unit_instance_id}:{target_enemy_unit_instance_id}"
        ),
        label=f"Select {target_enemy_unit_instance_id} for Malice Made Manifest",
        payload={
            "submission_kind": MALICE_MADE_MANIFEST_SUBMISSION_KIND,
            "game_id": game_id,
            "battle_round": battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.FIGHT.value,
            "player_id": player_id,
            "source_rule_id": MALICE_MADE_MANIFEST_SOURCE_RULE_ID,
            "hook_id": MALICE_MADE_MANIFEST_HOOK_ID,
            "enhancement_id": MALICE_MADE_MANIFEST_ENHANCEMENT_ID,
            "bearer_unit_instance_id": bearer_unit_instance_id,
            "bearer_rules_unit_instance_id": bearer_rules_unit_instance_id,
            "target_enemy_unit_instance_id": target_enemy_unit_instance_id,
        },
    )


def _resolve_routed_malice_made_manifest_mortal_wounds(
    *,
    state: object,
    decisions: object,
    feel_no_pain_result_id: str | None,
    routed_request: DecisionRequest | None,
    routed_application: MortalWoundApplication | None,
    routed_progress: MortalWoundApplicationProgress,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Malice Made Manifest mortal wound routing requires GameState.")
    if type(decisions) is not DecisionController:
        raise GameLifecycleError(
            "Malice Made Manifest mortal wound routing requires DecisionController."
        )
    if type(routed_progress) is not MortalWoundApplicationProgress:
        raise GameLifecycleError("Malice Made Manifest mortal wound routing requires progress.")
    source_context = _malice_made_manifest_mortal_wound_source_context_from_payload(
        routed_progress.source_context
    )
    resolution_payload = source_context["resolution_payload"]
    if routed_request is not None:
        decisions.request_decision(routed_request)
        decisions.event_log.append(
            MALICE_MADE_MANIFEST_PENDING_EVENT,
            validate_json_value(
                {
                    **resolution_payload,
                    "feel_no_pain_request_id": routed_request.request_id,
                    "remaining_mortal_wounds": routed_progress.remaining_mortal_wounds,
                }
            ),
        )
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=routed_request,
            payload={
                "phase": BattlePhase.FIGHT.value,
                "decision_type": SELECT_FEEL_NO_PAIN_DECISION_TYPE,
                "source_rule_id": MALICE_MADE_MANIFEST_SOURCE_RULE_ID,
                "source_kind": MALICE_MADE_MANIFEST_MORTAL_WOUNDS_SOURCE_KIND,
                "target_unit_instance_id": resolution_payload["target_enemy_unit_instance_id"],
                "remaining_mortal_wounds": routed_progress.remaining_mortal_wounds,
            },
        )
    if routed_application is None:
        raise GameLifecycleError("Malice Made Manifest routing did not produce application.")
    resolved_payload: dict[str, JsonValue] = {
        **resolution_payload,
        "mortal_wound_application": validate_json_value(routed_application.to_payload()),
    }
    if feel_no_pain_result_id is not None:
        resolved_payload["feel_no_pain_result_id"] = feel_no_pain_result_id
    decisions.event_log.append(
        MALICE_MADE_MANIFEST_RESOLVED_EVENT,
        validate_json_value(resolved_payload),
    )
    return None


def _malice_made_manifest_resolution_payload(
    *,
    context: FightPhaseStartResultContext,
    player_id: str,
    bearer_unit_instance_id: str,
    bearer_rules_unit_instance_id: str,
    target_enemy_unit_instance_id: str,
    d6_result: JsonValue,
    d3_result: JsonValue,
    mortal_wounds: int,
) -> dict[str, JsonValue]:
    return {
        "game_id": context.state.game_id,
        "battle_round": context.state.battle_round,
        "active_player_id": _active_player_id(context.state),
        "phase": BattlePhase.FIGHT.value,
        "player_id": player_id,
        "source_rule_id": MALICE_MADE_MANIFEST_SOURCE_RULE_ID,
        "hook_id": MALICE_MADE_MANIFEST_HOOK_ID,
        "enhancement_id": MALICE_MADE_MANIFEST_ENHANCEMENT_ID,
        "bearer_unit_instance_id": bearer_unit_instance_id,
        "bearer_rules_unit_instance_id": bearer_rules_unit_instance_id,
        "target_enemy_unit_instance_id": target_enemy_unit_instance_id,
        "request_id": context.request.request_id,
        "result_id": context.result.result_id,
        "selected_option_id": context.result.selected_option_id,
        "d6_result": d6_result,
        "d3_result": d3_result,
        "mortal_wounds": mortal_wounds,
    }


def _malice_made_manifest_mortal_wound_source_context(
    *,
    resolution_payload: dict[str, JsonValue],
) -> JsonValue:
    return validate_json_value(
        {
            "source_kind": MALICE_MADE_MANIFEST_MORTAL_WOUNDS_SOURCE_KIND,
            "phase": BattlePhase.FIGHT.value,
            "resolution_payload": resolution_payload,
        }
    )


def _malice_made_manifest_mortal_wound_source_context_from_payload(
    value: JsonValue,
) -> _MaliceMadeManifestMortalWoundSourceContextPayload:
    if not isinstance(value, dict):
        raise GameLifecycleError("Malice Made Manifest source context must be an object.")
    if value.get("source_kind") != MALICE_MADE_MANIFEST_MORTAL_WOUNDS_SOURCE_KIND:
        raise GameLifecycleError("Malice Made Manifest source kind drift.")
    if value.get("phase") != BattlePhase.FIGHT.value:
        raise GameLifecycleError("Malice Made Manifest source phase drift.")
    resolution_payload = value.get("resolution_payload")
    if not isinstance(resolution_payload, dict):
        raise GameLifecycleError("Malice Made Manifest source context missing payload.")
    return {
        "source_kind": MALICE_MADE_MANIFEST_MORTAL_WOUNDS_SOURCE_KIND,
        "phase": BattlePhase.FIGHT.value,
        "resolution_payload": resolution_payload,
    }


def _validate_malice_made_manifest_result_payload_matches_request(
    *,
    request_payload: dict[str, JsonValue],
    result_payload: dict[str, JsonValue],
) -> None:
    for key in (
        "source_rule_id",
        "hook_id",
        "enhancement_id",
        "bearer_unit_instance_id",
        "bearer_rules_unit_instance_id",
    ):
        if request_payload.get(key) != result_payload.get(key):
            raise GameLifecycleError("Malice Made Manifest result payload drift.")
    if result_payload.get("submission_kind") != MALICE_MADE_MANIFEST_SUBMISSION_KIND:
        raise GameLifecycleError("Malice Made Manifest submission kind drift.")


def _assigned_malice_made_manifest_unit_id_matches(
    army: ArmyDefinition,
    *,
    unit_instance_id: str,
) -> bool:
    return any(
        unit.unit_instance_id == unit_instance_id
        for _assignment, unit in _assigned_units(
            army,
            enhancement_id=MALICE_MADE_MANIFEST_ENHANCEMENT_ID,
        )
    )


def _malice_made_manifest_recorded_this_fight_start(
    *,
    context: FightPhaseStartRequestContext,
    bearer_rules_unit_instance_id: str,
) -> bool:
    active_player_id = _active_player_id(context.state)
    for record in context.decisions.event_log.records:
        if record.event_type not in {
            MALICE_MADE_MANIFEST_NO_EFFECT_EVENT,
            MALICE_MADE_MANIFEST_PENDING_EVENT,
            MALICE_MADE_MANIFEST_RESOLVED_EVENT,
        }:
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        if payload.get("game_id") != context.state.game_id:
            continue
        if payload.get("battle_round") != context.state.battle_round:
            continue
        if payload.get("active_player_id") != active_player_id:
            continue
        if payload.get("phase") != BattlePhase.FIGHT.value:
            continue
        if payload.get("bearer_rules_unit_instance_id") == bearer_rules_unit_instance_id:
            return True
    return False


def _enemy_rules_unit_ids_within_engagement_range(
    *,
    state: object,
    bearer_unit_instance_id: str,
) -> tuple[str, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Malice Made Manifest target lookup requires GameState.")
    if state.battlefield_state is None:
        raise GameLifecycleError("Malice Made Manifest target lookup requires battlefield_state.")
    bearer_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=bearer_unit_instance_id,
    )
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    bearer_models = _alive_geometry_models_for_rules_unit(
        state=state,
        scenario=scenario,
        rules_unit=bearer_rules_unit,
    )
    if not bearer_models:
        return ()
    enemy_rules_unit_ids: set[str] = set()
    checked_rules_unit_ids: set[str] = set()
    for army in state.army_definitions:
        if army.player_id == bearer_rules_unit.owner_player_id:
            continue
        for unit in army.units:
            enemy_rules_unit = rules_unit_view_by_id(
                state=state,
                unit_instance_id=unit.unit_instance_id,
            )
            if enemy_rules_unit.unit_instance_id in checked_rules_unit_ids:
                continue
            checked_rules_unit_ids.add(enemy_rules_unit.unit_instance_id)
            enemy_models = _alive_geometry_models_for_rules_unit(
                state=state,
                scenario=scenario,
                rules_unit=enemy_rules_unit,
            )
            if _any_models_within_engagement_range(
                state=state,
                first_models=bearer_models,
                second_models=enemy_models,
            ):
                enemy_rules_unit_ids.add(enemy_rules_unit.unit_instance_id)
    return tuple(sorted(enemy_rules_unit_ids))


def _alive_geometry_models_for_rules_unit(
    *,
    state: object,
    scenario: BattlefieldScenario,
    rules_unit: RulesUnitView,
) -> tuple[GeometryModel, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Malice Made Manifest model lookup requires GameState.")
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("Malice Made Manifest model lookup requires scenario.")
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Malice Made Manifest model lookup requires rules unit.")
    if state.battlefield_state is None:
        raise GameLifecycleError("Malice Made Manifest model lookup requires battlefield_state.")
    models: list[GeometryModel] = []
    for component in rules_unit.components:
        try:
            unit_placement = state.battlefield_state.unit_placement_by_id(
                component.unit.unit_instance_id
            )
        except PlacementError:
            continue
        for model_placement in unit_placement.model_placements:
            model = scenario.model_instance_for_placement(model_placement)
            if not model.is_alive:
                continue
            models.append(
                geometry_model_for_placement(
                    model=model,
                    placement=model_placement,
                )
            )
    return tuple(models)


def _any_models_within_engagement_range(
    *,
    state: object,
    first_models: tuple[GeometryModel, ...],
    second_models: tuple[GeometryModel, ...],
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Malice Made Manifest engagement lookup requires GameState.")
    engagement_policy = state.runtime_ruleset_descriptor().engagement_policy
    for first_model in first_models:
        for second_model in second_models:
            if first_model.is_within_engagement_range(
                second_model,
                horizontal_inches=engagement_policy.horizontal_inches,
                vertical_inches=engagement_policy.vertical_inches,
            ):
                return True
    return False


def _shadow_legion_armies(state: object) -> tuple[ArmyDefinition, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Fade to Darkness requires GameState.")
    return tuple(
        army
        for army in state.army_definitions
        if army.detachment_selection.faction_id == CHAOS_DAEMONS_FACTION_ID
        and DETACHMENT_ID in army.detachment_selection.detachment_ids
    )


def _assigned_units(
    army: ArmyDefinition,
    *,
    enhancement_id: str,
) -> tuple[tuple[EnhancementAssignment, UnitInstance], ...]:
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError("Fade to Darkness requires ArmyDefinition.")
    assignments: list[tuple[EnhancementAssignment, UnitInstance]] = []
    for assignment in army.enhancement_assignments:
        if assignment.enhancement_id != enhancement_id:
            continue
        assignments.append((assignment, _unit_for_assignment(army, assignment=assignment)))
    return tuple(sorted(assignments, key=lambda item: item[1].unit_instance_id))


def _assigned_fade_unit_id_matches(army: ArmyDefinition, *, unit_instance_id: str) -> bool:
    return any(
        unit.unit_instance_id == unit_instance_id
        for _assignment, unit in _assigned_units(army, enhancement_id=ENHANCEMENT_ID)
    )


def _unit_for_assignment(
    army: ArmyDefinition,
    *,
    assignment: EnhancementAssignment,
) -> UnitInstance:
    expected_unit_instance_id = f"{army.army_id}:{assignment.target_unit_selection_id}"
    for unit in army.units:
        if unit.unit_instance_id == expected_unit_instance_id:
            return unit
    raise GameLifecycleError("Fade to Darkness assignment target unit was not mustered.")


def _leaping_shadows_scouts_descriptor() -> DatasheetAbilityDescriptor:
    return DatasheetAbilityDescriptor(
        ability_id=LEAPING_SHADOWS_ABILITY_ID,
        name=f"Scouts {LEAPING_SHADOWS_SCOUTS_DISTANCE}",
        source_id=LEAPING_SHADOWS_SOURCE_RULE_ID,
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description="Leaping Shadows grants Scouts 9.",
        timing_tags=("before_battle", "scouts"),
        parameter_tokens=(LEAPING_SHADOWS_SCOUTS_DISTANCE,),
    )


def _unit_can_enter_strategic_reserves(
    state: object,
    *,
    unit_instance_id: str,
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Fade to Darkness requires GameState.")
    if state.battlefield_state is None:
        raise GameLifecycleError("Fade to Darkness requires battlefield_state.")
    if state.reserve_state_for_unit(unit_instance_id) is not None:
        return False
    try:
        state.battlefield_state.unit_placement_by_id(unit_instance_id)
    except PlacementError:
        return False
    return not unit_within_enemy_engagement_range(state=state, unit_instance_id=unit_instance_id)


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Leaping Shadows keyword lookup requires UnitInstance.")
    requested_keyword = _canonical_keyword(keyword)
    return requested_keyword in {_canonical_keyword(stored) for stored in unit.keywords}


def _destroyed_enemy_unit_ids_for_fade_unit(
    context: TurnEndRequestContext | TurnEndResultContext,
    *,
    player_id: str,
    unit_instance_id: str,
) -> tuple[str, ...]:
    phase = (
        context.completed_phase
        if type(context) is TurnEndRequestContext
        else context.state.current_battle_phase
    )
    if phase is None:
        raise GameLifecycleError("Fade to Darkness requires a current phase.")
    destroyed_unit_ids: set[str] = set()
    for record in context.decisions.event_log.records:
        if record.event_type != ELIGIBLE_EVENT:
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        if payload.get("game_id") != context.state.game_id:
            continue
        if payload.get("battle_round") != context.state.battle_round:
            continue
        if payload.get("active_player_id") != context.state.active_player_id:
            continue
        if payload.get("phase") != phase.value:
            continue
        if payload.get("player_id") != player_id:
            continue
        if payload.get("target_unit_instance_id") != unit_instance_id:
            continue
        destroyed_unit_id = payload.get("destroyed_enemy_unit_instance_id")
        if type(destroyed_unit_id) is str:
            destroyed_unit_ids.add(destroyed_unit_id)
    return tuple(sorted(destroyed_unit_ids))


def _decision_recorded_this_phase(
    context: TurnEndRequestContext,
    *,
    unit_instance_id: str,
) -> bool:
    active_player_id = _active_player_id(context.state)
    for record in context.decisions.event_log.records:
        if record.event_type not in {USED_EVENT, DECLINED_EVENT}:
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        if payload.get("game_id") != context.state.game_id:
            continue
        if payload.get("battle_round") != context.state.battle_round:
            continue
        if payload.get("active_player_id") != active_player_id:
            continue
        if payload.get("phase") != context.completed_phase.value:
            continue
        if payload.get("target_unit_instance_id") == unit_instance_id:
            return True
    return False


def _eligible_event_recorded_for_destroyed_unit(
    context: UnitDestroyedContext,
    *,
    unit_instance_id: str,
    destroyed_unit_instance_id: str,
) -> bool:
    for record in context.decisions.event_log.records:
        if record.event_type != ELIGIBLE_EVENT:
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        if payload.get("game_id") != context.state.game_id:
            continue
        if payload.get("battle_round") != context.state.battle_round:
            continue
        if payload.get("active_player_id") != context.state.active_player_id:
            continue
        if payload.get("phase") != context.completed_phase.value:
            continue
        if payload.get("target_unit_instance_id") != unit_instance_id:
            continue
        if payload.get("destroyed_enemy_unit_instance_id") == destroyed_unit_instance_id:
            return True
    return False


def _validate_result_payload_matches_request(
    *,
    request_payload: dict[str, JsonValue],
    result_payload: dict[str, JsonValue],
) -> None:
    for key in ("source_rule_id", "hook_id", "enhancement_id", "target_unit_instance_id"):
        if request_payload.get(key) != result_payload.get(key):
            raise GameLifecycleError("Fade to Darkness result payload drift.")
    if result_payload.get("submission_kind") != SUBMISSION_KIND:
        raise GameLifecycleError("Fade to Darkness submission kind drift.")


def _fade_to_darkness_event_payload(
    *,
    context: TurnEndResultContext,
    player_id: str,
    unit_instance_id: str,
    reserve_state_payload: JsonValue,
    use_ability: bool,
) -> dict[str, JsonValue]:
    return {
        "game_id": context.state.game_id,
        "battle_round": context.state.battle_round,
        "active_player_id": _active_player_id(context.state),
        "phase": context.state.current_battle_phase.value
        if context.state.current_battle_phase is not None
        else None,
        "player_id": player_id,
        "source_rule_id": SOURCE_RULE_ID,
        "hook_id": TURN_END_HOOK_ID,
        "enhancement_id": ENHANCEMENT_ID,
        "target_unit_instance_id": unit_instance_id,
        "destroyed_enemy_unit_instance_ids": list(
            _destroyed_enemy_unit_ids_for_fade_unit(
                context,
                player_id=player_id,
                unit_instance_id=unit_instance_id,
            )
        ),
        "request_id": context.request.request_id,
        "result_id": context.result.result_id,
        "selected_option_id": context.result.selected_option_id,
        "use_ability": use_ability,
        "reserve_state": reserve_state_payload,
    }


def _army_for_player(armies: tuple[ArmyDefinition, ...], *, player_id: str) -> ArmyDefinition:
    requested_player_id = _validate_identifier("player_id", player_id)
    for army in armies:
        if army.player_id == requested_player_id:
            if not (
                army.detachment_selection.faction_id == CHAOS_DAEMONS_FACTION_ID
                and DETACHMENT_ID in army.detachment_selection.detachment_ids
            ):
                raise GameLifecycleError("Fade to Darkness requires Shadow Legion.")
            return army
    raise GameLifecycleError("Fade to Darkness player army is unknown.")


def _active_player_id(state: object) -> str:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Fade to Darkness requires GameState.")
    if state.active_player_id is None:
        raise GameLifecycleError("Fade to Darkness requires an active player.")
    return state.active_player_id


def _payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Fade to Darkness payload must be an object.")
    return payload


def _payload_string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"Fade to Darkness payload missing string {key}.")
    return _validate_identifier(key, value)


def _payload_bool(payload: dict[str, JsonValue], key: str) -> bool:
    value = payload.get(key)
    if type(value) is not bool:
        raise GameLifecycleError(f"Fade to Darkness payload missing bool {key}.")
    return value


def _payload_string_tuple(payload: dict[str, JsonValue], *, key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise GameLifecycleError(f"Shadow Legion enhancement payload missing list {key}.")
    parsed: list[str] = []
    for item in value:
        parsed.append(_validate_identifier(key, item))
    return tuple(parsed)


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Fade to Darkness {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Fade to Darkness {field_name} must not be empty.")
    return stripped


def _canonical_keyword(value: str) -> str:
    return _validate_identifier("keyword", value).upper().replace("_", " ").replace("-", " ")
