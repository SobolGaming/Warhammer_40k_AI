from __future__ import annotations

from typing import cast

from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.advance_hooks import (
    AdvanceMoveContext,
    AdvanceMoveGrant,
    AdvanceMoveHookBinding,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    BattlefieldTransitionBatchPayload,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.charge_declaration_hooks import (
    ChargeDeclarationContext,
    ChargeDeclarationGrant,
    ChargeDeclarationHookBinding,
)
from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.faction_content.common import canonical_keyword as _canonical_keyword
from warhammer40k_core.engine.fight_activation_abilities import (
    FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND,
    FightActivationAbilityContext,
    FightActivationAbilityHookBinding,
    FightActivationAbilityOption,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.list_validation import BattleSize
from warhammer40k_core.engine.movement_end_surge_hooks import (
    MovementEndSurgeContext,
    MovementEndSurgeGrant,
    MovementEndSurgeHookBinding,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.ranged_weapon_keyword_effects import (
    ranged_weapon_keyword_grant_payload,
)
from warhammer40k_core.engine.shooting_end_surge_hooks import (
    ShootingEndSurgeContext,
    ShootingEndSurgeGrant,
    ShootingEndSurgeHookBinding,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.volume import Model as GeometryModel

CONTRIBUTION_ID = "warhammer_40000_11th:aeldari:army_rule:scaffold"
SWIFT_AS_THE_WIND_HOOK_ID = "warhammer_40000_11th:aeldari:army_rule:swift_as_the_wind"
FLITTING_SHADOWS_HOOK_ID = "warhammer_40000_11th:aeldari:army_rule:flitting_shadows"
STAR_ENGINES_HOOK_ID = "warhammer_40000_11th:aeldari:army_rule:star_engines"
SUDDEN_STRIKE_HOOK_ID = "warhammer_40000_11th:aeldari:army_rule:sudden_strike"
OPPORTUNITY_SEIZED_HOOK_ID = "warhammer_40000_11th:aeldari:army_rule:opportunity_seized"
FADE_BACK_HOOK_ID = "warhammer_40000_11th:aeldari:army_rule:fade_back"
HOOK_ID = STAR_ENGINES_HOOK_ID
SOURCE_RULE_ID = "phase17f:phase17e:aeldari:army-rule"
BATTLE_FOCUS_TOKEN_SPENT_EFFECT_KIND = "aeldari_battle_focus_token_spent"
AGILE_MANOEUVRE_EFFECT_KIND = "aeldari_agile_manoeuvre"
SWIFT_AS_THE_WIND_MANEUVER = "swift_as_the_wind"
FLITTING_SHADOWS_MANEUVER = "flitting_shadows"
STAR_ENGINES_MANEUVER = "star_engines"
SUDDEN_STRIKE_MANEUVER = "sudden_strike"
OPPORTUNITY_SEIZED_MANEUVER = "opportunity_seized"
FADE_BACK_MANEUVER = "fade_back"
AELDARI_FACTION_ID = "aeldari"
ASURYANI = "ASURYANI"
AELDARI = "AELDARI"
VEHICLE = "VEHICLE"
TITANIC = "TITANIC"
_BATTLE_FOCUS_TOKENS_BY_BATTLE_SIZE = {BattleSize.STRIKE_FORCE: 4}
_SWIFT_MOVEMENT_BONUS_INCHES = 2
_SUDDEN_STRIKE_FIGHT_MOVE_DISTANCE_INCHES = 6.0
_AGILE_SURGE_DISTANCE_BONUS_INCHES = 1


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        advance_move_hook_bindings=(
            AdvanceMoveHookBinding(
                hook_id=SWIFT_AS_THE_WIND_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=swift_as_the_wind_movement_grant,
            ),
            AdvanceMoveHookBinding(
                hook_id=FLITTING_SHADOWS_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=flitting_shadows_movement_grant,
            ),
            AdvanceMoveHookBinding(
                hook_id=STAR_ENGINES_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=star_engines_movement_grant,
            ),
        ),
        movement_end_surge_hook_bindings=(
            MovementEndSurgeHookBinding(
                hook_id=OPPORTUNITY_SEIZED_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=opportunity_seized_surge_grants,
            ),
        ),
        charge_declaration_hook_bindings=(
            ChargeDeclarationHookBinding(
                hook_id=FLITTING_SHADOWS_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=flitting_shadows_charge_declaration_grant,
            ),
        ),
        shooting_end_surge_hook_bindings=(
            ShootingEndSurgeHookBinding(
                hook_id=FADE_BACK_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=fade_back_surge_grants,
            ),
        ),
        fight_activation_ability_hook_bindings=(
            FightActivationAbilityHookBinding(
                hook_id=SUDDEN_STRIKE_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=sudden_strike_fight_activation_option,
            ),
        ),
    )


def swift_as_the_wind_movement_grant(context: AdvanceMoveContext) -> AdvanceMoveGrant | None:
    if type(context) is not AdvanceMoveContext:
        raise GameLifecycleError("Aeldari Swift as the Wind requires an AdvanceMoveContext.")
    if context.movement_phase_action not in {"normal_move", "advance", "fall_back"}:
        return None
    army, unit = _eligible_agile_manoeuvre_army_and_unit(
        state=context.state,
        player_id=context.player_id,
        unit_instance_id=context.unit_instance_id,
        error_label="Aeldari Swift as the Wind",
    )
    if army is None or unit is None:
        return None
    if _battle_focus_tokens_remaining(state=context.state, army=army) <= 0:
        return None
    if _unit_already_performed_agile_manoeuvre_this_phase(
        state=context.state,
        player_id=context.player_id,
        battle_round=context.battle_round,
        phase=BattlePhaseKind.MOVEMENT,
        unit=unit,
    ):
        return None
    return AdvanceMoveGrant(
        hook_id=SWIFT_AS_THE_WIND_HOOK_ID,
        source_id=SOURCE_RULE_ID,
        label="Battle Focus: Swift as the Wind",
        granted_ranged_weapon_keywords=(),
        movement_bonus_inches=_SWIFT_MOVEMENT_BONUS_INCHES,
        replay_payload=_movement_replay_payload(
            maneuver=SWIFT_AS_THE_WIND_MANEUVER,
            unit=unit,
            context=context,
        ),
        decision_effect_payload=_battle_focus_spend_payload_for_context(
            maneuver=SWIFT_AS_THE_WIND_MANEUVER,
            unit=unit,
            context=context,
        ),
        unit_effect_payload={
            "effect_kind": AGILE_MANOEUVRE_EFFECT_KIND,
            "maneuver": SWIFT_AS_THE_WIND_MANEUVER,
            "unit_instance_id": unit.unit_instance_id,
            "movement_bonus_inches": _SWIFT_MOVEMENT_BONUS_INCHES,
            "movement_action_request_id": context.movement_request_id,
            "movement_action_result_id": context.movement_result_id,
        },
        unit_effect_expiration="end_phase",
    )


def flitting_shadows_movement_grant(context: AdvanceMoveContext) -> AdvanceMoveGrant | None:
    if type(context) is not AdvanceMoveContext:
        raise GameLifecycleError("Aeldari Flitting Shadows requires an AdvanceMoveContext.")
    if context.movement_phase_action not in {"normal_move", "advance", "fall_back"}:
        return None
    army, unit = _eligible_agile_manoeuvre_army_and_unit(
        state=context.state,
        player_id=context.player_id,
        unit_instance_id=context.unit_instance_id,
        error_label="Aeldari Flitting Shadows",
    )
    if army is None or unit is None:
        return None
    if _battle_focus_tokens_remaining(state=context.state, army=army) <= 0:
        return None
    if _unit_already_performed_agile_manoeuvre_this_phase(
        state=context.state,
        player_id=context.player_id,
        battle_round=context.battle_round,
        phase=BattlePhaseKind.MOVEMENT,
        unit=unit,
    ):
        return None
    if _maneuver_already_used_this_phase(
        state=context.state,
        player_id=context.player_id,
        battle_round=context.battle_round,
        phase=BattlePhaseKind.MOVEMENT,
        maneuver=FLITTING_SHADOWS_MANEUVER,
    ):
        return None
    return AdvanceMoveGrant(
        hook_id=FLITTING_SHADOWS_HOOK_ID,
        source_id=SOURCE_RULE_ID,
        label="Battle Focus: Flitting Shadows",
        granted_ranged_weapon_keywords=(),
        replay_payload=_movement_replay_payload(
            maneuver=FLITTING_SHADOWS_MANEUVER,
            unit=unit,
            context=context,
        ),
        decision_effect_payload=_battle_focus_spend_payload_for_context(
            maneuver=FLITTING_SHADOWS_MANEUVER,
            unit=unit,
            context=context,
        ),
        unit_effect_payload={
            "effect_kind": AGILE_MANOEUVRE_EFFECT_KIND,
            "maneuver": FLITTING_SHADOWS_MANEUVER,
            "unit_instance_id": unit.unit_instance_id,
            "fire_overwatch_forbidden": True,
            "movement_action_request_id": context.movement_request_id,
            "movement_action_result_id": context.movement_result_id,
        },
        unit_effect_expiration="end_turn",
    )


def flitting_shadows_charge_declaration_grant(
    context: ChargeDeclarationContext,
) -> ChargeDeclarationGrant | None:
    if type(context) is not ChargeDeclarationContext:
        raise GameLifecycleError("Aeldari Flitting Shadows requires a ChargeDeclarationContext.")
    army, unit = _eligible_agile_manoeuvre_army_and_unit(
        state=context.state,
        player_id=context.player_id,
        unit_instance_id=context.unit_instance_id,
        error_label="Aeldari Flitting Shadows",
    )
    if army is None or unit is None:
        return None
    if _battle_focus_tokens_remaining(state=context.state, army=army) <= 0:
        return None
    if _unit_already_performed_agile_manoeuvre_this_phase(
        state=context.state,
        player_id=context.player_id,
        battle_round=context.battle_round,
        phase=BattlePhaseKind.CHARGE,
        unit=unit,
    ):
        return None
    if _maneuver_already_used_this_phase(
        state=context.state,
        player_id=context.player_id,
        battle_round=context.battle_round,
        phase=BattlePhaseKind.CHARGE,
        maneuver=FLITTING_SHADOWS_MANEUVER,
    ):
        return None
    return ChargeDeclarationGrant(
        hook_id=FLITTING_SHADOWS_HOOK_ID,
        source_id=SOURCE_RULE_ID,
        label="Battle Focus: Flitting Shadows",
        replay_payload={
            "effect_kind": AGILE_MANOEUVRE_EFFECT_KIND,
            "maneuver": FLITTING_SHADOWS_MANEUVER,
            "unit_instance_id": unit.unit_instance_id,
            "selection_request_id": context.selection_request_id,
            "selection_result_id": context.selection_result_id,
        },
        decision_effect_payload={
            "effect_kind": BATTLE_FOCUS_TOKEN_SPENT_EFFECT_KIND,
            "maneuver": FLITTING_SHADOWS_MANEUVER,
            "unit_instance_id": unit.unit_instance_id,
            "battle_focus_token_cost": 1,
            "selection_request_id": context.selection_request_id,
            "selection_result_id": context.selection_result_id,
        },
        unit_effect_payload={
            "effect_kind": AGILE_MANOEUVRE_EFFECT_KIND,
            "maneuver": FLITTING_SHADOWS_MANEUVER,
            "unit_instance_id": unit.unit_instance_id,
            "fire_overwatch_forbidden": True,
            "selection_request_id": context.selection_request_id,
            "selection_result_id": context.selection_result_id,
        },
        unit_effect_expiration="end_turn",
    )


def star_engines_movement_grant(context: AdvanceMoveContext) -> AdvanceMoveGrant | None:
    if type(context) is not AdvanceMoveContext:
        raise GameLifecycleError("Aeldari Star Engines requires an AdvanceMoveContext.")
    if context.movement_phase_action != "advance":
        return None
    army, unit = _eligible_agile_manoeuvre_army_and_unit(
        state=context.state,
        player_id=context.player_id,
        unit_instance_id=context.unit_instance_id,
        error_label="Aeldari Star Engines",
    )
    if army is None or unit is None:
        return None
    if not _unit_has_keyword(unit, VEHICLE):
        return None
    if _battle_focus_tokens_remaining(state=context.state, army=army) <= 0:
        return None
    if _unit_already_performed_agile_manoeuvre_this_phase(
        state=context.state,
        player_id=context.player_id,
        battle_round=context.battle_round,
        phase=BattlePhaseKind.MOVEMENT,
        unit=unit,
    ):
        return None
    if _maneuver_already_used_this_phase(
        state=context.state,
        player_id=context.player_id,
        battle_round=context.battle_round,
        phase=BattlePhaseKind.MOVEMENT,
        maneuver=STAR_ENGINES_MANEUVER,
    ):
        return None
    return AdvanceMoveGrant(
        hook_id=STAR_ENGINES_HOOK_ID,
        source_id=SOURCE_RULE_ID,
        label="Battle Focus: Star Engines",
        granted_ranged_weapon_keywords=(WeaponKeyword.ASSAULT.value,),
        replay_payload=_movement_replay_payload(
            maneuver=STAR_ENGINES_MANEUVER,
            unit=unit,
            context=context,
        ),
        decision_effect_payload=_battle_focus_spend_payload_for_context(
            maneuver=STAR_ENGINES_MANEUVER,
            unit=unit,
            context=context,
        ),
        unit_effect_payload=ranged_weapon_keyword_grant_payload(
            granted_keywords=(WeaponKeyword.ASSAULT,),
            source_movement_request_id=context.movement_request_id,
            source_movement_result_id=context.movement_result_id,
        ),
        unit_effect_expiration="end_turn",
    )


def opportunity_seized_surge_grants(
    context: MovementEndSurgeContext,
) -> tuple[MovementEndSurgeGrant, ...]:
    if type(context) is not MovementEndSurgeContext:
        raise GameLifecycleError("Aeldari Opportunity Seized requires a surge context.")
    if context.movement_phase_action != "fall_back":
        return ()
    army = _army_for_player(context.state, player_id=context.reacting_player_id)
    if army.detachment_selection.faction_id != AELDARI_FACTION_ID:
        return ()
    if _battle_focus_tokens_remaining(state=context.state, army=army) <= 0:
        return ()
    if _maneuver_already_used_this_phase(
        state=context.state,
        player_id=context.reacting_player_id,
        battle_round=context.state.battle_round,
        phase=BattlePhaseKind.MOVEMENT,
        maneuver=OPPORTUNITY_SEIZED_MANEUVER,
    ):
        return ()
    scenario = _battlefield_scenario(context.state)
    triggering_start = _triggering_unit_start_placement(
        scenario=scenario,
        context=context,
    )
    grants: list[MovementEndSurgeGrant] = []
    for unit in army.units:
        if not _unit_is_eligible_agile_manoeuvre_unit(army=army, unit=unit):
            continue
        if _unit_has_keyword(unit, TITANIC):
            continue
        if _unit_already_performed_agile_manoeuvre_this_phase(
            state=context.state,
            player_id=context.reacting_player_id,
            battle_round=context.state.battle_round,
            phase=BattlePhaseKind.MOVEMENT,
            unit=unit,
        ):
            continue
        unit_placement = _placed_unit_or_none(
            scenario=scenario,
            player_id=context.reacting_player_id,
            unit_instance_id=unit.unit_instance_id,
        )
        if unit_placement is None:
            continue
        if not _unit_placements_within_engagement_range(
            scenario=scenario,
            ruleset_context=context,
            first=unit_placement,
            second=triggering_start,
        ):
            continue
        grants.append(
            MovementEndSurgeGrant(
                hook_id=OPPORTUNITY_SEIZED_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                unit_instance_id=unit.unit_instance_id,
                max_distance_bonus_inches=_AGILE_SURGE_DISTANCE_BONUS_INCHES,
                replay_payload={
                    "effect_kind": AGILE_MANOEUVRE_EFFECT_KIND,
                    "maneuver": OPPORTUNITY_SEIZED_MANEUVER,
                    "unit_instance_id": unit.unit_instance_id,
                    "triggering_unit_instance_id": context.triggering_unit_instance_id,
                    "trigger_event_id": context.trigger_event_id,
                    "movement_phase_action": context.movement_phase_action,
                },
                decision_effect_payload=_surge_battle_focus_spend_payload(
                    maneuver=OPPORTUNITY_SEIZED_MANEUVER,
                    unit=unit,
                    trigger_event_id=context.trigger_event_id,
                    triggering_unit_instance_id=context.triggering_unit_instance_id,
                ),
            )
        )
    return tuple(sorted(grants, key=lambda grant: grant.unit_instance_id))


def fade_back_surge_grants(
    context: ShootingEndSurgeContext,
) -> tuple[ShootingEndSurgeGrant, ...]:
    if type(context) is not ShootingEndSurgeContext:
        raise GameLifecycleError("Aeldari Fade Back requires a shooting-end surge context.")
    army = _army_for_player(context.state, player_id=context.reacting_player_id)
    if army.detachment_selection.faction_id != AELDARI_FACTION_ID:
        return ()
    if _battle_focus_tokens_remaining(state=context.state, army=army) <= 0:
        return ()
    if _maneuver_already_used_this_phase(
        state=context.state,
        player_id=context.reacting_player_id,
        battle_round=context.state.battle_round,
        phase=BattlePhaseKind.SHOOTING,
        maneuver=FADE_BACK_MANEUVER,
    ):
        return ()
    hit_unit_ids = set(context.hit_target_unit_instance_ids)
    grants: list[ShootingEndSurgeGrant] = []
    for unit in army.units:
        if unit.unit_instance_id not in hit_unit_ids:
            continue
        if not _unit_is_eligible_agile_manoeuvre_unit(army=army, unit=unit):
            continue
        if _unit_has_keyword(unit, TITANIC):
            continue
        if _unit_already_performed_agile_manoeuvre_this_phase(
            state=context.state,
            player_id=context.reacting_player_id,
            battle_round=context.state.battle_round,
            phase=BattlePhaseKind.SHOOTING,
            unit=unit,
        ):
            continue
        grants.append(
            ShootingEndSurgeGrant(
                hook_id=FADE_BACK_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                unit_instance_id=unit.unit_instance_id,
                max_distance_bonus_inches=_AGILE_SURGE_DISTANCE_BONUS_INCHES,
                replay_payload={
                    "effect_kind": AGILE_MANOEUVRE_EFFECT_KIND,
                    "maneuver": FADE_BACK_MANEUVER,
                    "unit_instance_id": unit.unit_instance_id,
                    "shooting_unit_instance_id": context.shooting_unit_instance_id,
                    "trigger_event_id": context.trigger_event_id,
                },
                decision_effect_payload=_surge_battle_focus_spend_payload(
                    maneuver=FADE_BACK_MANEUVER,
                    unit=unit,
                    trigger_event_id=context.trigger_event_id,
                    triggering_unit_instance_id=context.shooting_unit_instance_id,
                ),
            )
        )
    return tuple(sorted(grants, key=lambda grant: grant.unit_instance_id))


def sudden_strike_fight_activation_option(
    context: FightActivationAbilityContext,
) -> FightActivationAbilityOption | None:
    if type(context) is not FightActivationAbilityContext:
        raise GameLifecycleError("Aeldari Sudden Strike requires a FightActivationAbilityContext.")
    army, unit = _eligible_agile_manoeuvre_army_and_unit(
        state=context.state,
        player_id=context.player_id,
        unit_instance_id=context.unit_instance_id,
        error_label="Aeldari Sudden Strike",
    )
    if army is None or unit is None:
        return None
    if _battle_focus_tokens_remaining(state=context.state, army=army) <= 0:
        return None
    if _unit_already_performed_agile_manoeuvre_this_phase(
        state=context.state,
        player_id=context.player_id,
        battle_round=context.battle_round,
        phase=BattlePhaseKind.FIGHT,
        unit=unit,
    ):
        return None
    if _maneuver_already_used_this_phase(
        state=context.state,
        player_id=context.player_id,
        battle_round=context.battle_round,
        phase=BattlePhaseKind.FIGHT,
        maneuver=SUDDEN_STRIKE_MANEUVER,
    ):
        return None
    return FightActivationAbilityOption(
        hook_id=SUDDEN_STRIKE_HOOK_ID,
        source_id=SOURCE_RULE_ID,
        ability_id=SUDDEN_STRIKE_MANEUVER,
        enhancement_id="aeldari_army_rule",
        effect_kind=FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND,
        pile_in_distance_inches=_SUDDEN_STRIKE_FIGHT_MOVE_DISTANCE_INCHES,
        consolidate_distance_inches=_SUDDEN_STRIKE_FIGHT_MOVE_DISTANCE_INCHES,
        replay_payload={
            "effect_kind": AGILE_MANOEUVRE_EFFECT_KIND,
            "maneuver": SUDDEN_STRIKE_MANEUVER,
            "unit_instance_id": unit.unit_instance_id,
            "activation_request_id": context.activation.request_id,
            "activation_result_id": context.activation.result_id,
            "pile_in_distance_inches": _SUDDEN_STRIKE_FIGHT_MOVE_DISTANCE_INCHES,
            "consolidate_distance_inches": _SUDDEN_STRIKE_FIGHT_MOVE_DISTANCE_INCHES,
        },
        decision_effect_payload={
            "effect_kind": BATTLE_FOCUS_TOKEN_SPENT_EFFECT_KIND,
            "maneuver": SUDDEN_STRIKE_MANEUVER,
            "unit_instance_id": unit.unit_instance_id,
            "battle_focus_token_cost": 1,
            "activation_request_id": context.activation.request_id,
            "activation_result_id": context.activation.result_id,
        },
    )


def _eligible_agile_manoeuvre_army_and_unit(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
    error_label: str,
) -> tuple[ArmyDefinition | None, UnitInstance | None]:
    army = state.army_definition_for_player(player_id)
    if army is None:
        raise GameLifecycleError(f"{error_label} player army is missing.")
    if army.detachment_selection.faction_id != AELDARI_FACTION_ID:
        return (None, None)
    unit = _unit_by_id(state, unit_instance_id)
    if not _army_contains_unit(army=army, unit=unit):
        raise GameLifecycleError(f"{error_label} unit is not in the acting army.")
    if not (_unit_has_faction_keyword(unit, ASURYANI) or _unit_has_faction_keyword(unit, AELDARI)):
        return (None, None)
    return (army, unit)


def _movement_replay_payload(
    *,
    maneuver: str,
    unit: UnitInstance,
    context: AdvanceMoveContext,
) -> JsonValue:
    return {
        "effect_kind": AGILE_MANOEUVRE_EFFECT_KIND,
        "maneuver": maneuver,
        "unit_instance_id": unit.unit_instance_id,
        "movement_phase_action": context.movement_phase_action,
        "movement_action_request_id": context.movement_request_id,
        "movement_action_result_id": context.movement_result_id,
    }


def _battle_focus_spend_payload_for_context(
    *,
    maneuver: str,
    unit: UnitInstance,
    context: AdvanceMoveContext,
) -> JsonValue:
    return {
        "effect_kind": BATTLE_FOCUS_TOKEN_SPENT_EFFECT_KIND,
        "maneuver": maneuver,
        "unit_instance_id": unit.unit_instance_id,
        "battle_focus_token_cost": 1,
        "movement_action_request_id": context.movement_request_id,
        "movement_action_result_id": context.movement_result_id,
    }


def _battle_focus_tokens_remaining(*, state: GameState, army: ArmyDefinition) -> int:
    tokens = _battle_focus_token_count(army)
    spent = sum(
        1
        for effect in _battle_focus_spend_effects(state=state, player_id=army.player_id)
        if effect.started_battle_round == state.battle_round
    )
    return max(0, tokens - spent)


def _battle_focus_token_count(army: ArmyDefinition) -> int:
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError("Aeldari Battle Focus token count requires an ArmyDefinition.")
    token_count = _BATTLE_FOCUS_TOKENS_BY_BATTLE_SIZE.get(army.battle_size)
    if token_count is None:
        raise GameLifecycleError("Aeldari Battle Focus battle size is unsupported.")
    return token_count


def _unit_already_performed_agile_manoeuvre_this_phase(
    *,
    state: GameState,
    player_id: str,
    battle_round: int,
    phase: BattlePhaseKind,
    unit: UnitInstance,
) -> bool:
    for effect in _battle_focus_spend_effects(state=state, player_id=player_id):
        if effect.started_battle_round != battle_round:
            continue
        if effect.started_phase is not phase:
            continue
        payload = _battle_focus_spend_payload(effect.effect_payload)
        if payload["unit_instance_id"] == unit.unit_instance_id:
            return True
    return False


def _maneuver_already_used_this_phase(
    *,
    state: GameState,
    player_id: str,
    battle_round: int,
    phase: BattlePhaseKind,
    maneuver: str,
) -> bool:
    requested_maneuver = _validate_identifier("maneuver", maneuver)
    for effect in _battle_focus_spend_effects(state=state, player_id=player_id):
        if effect.started_battle_round != battle_round:
            continue
        if effect.started_phase is not phase:
            continue
        payload = _battle_focus_spend_payload(effect.effect_payload)
        if payload["maneuver"] == requested_maneuver:
            return True
    return False


def _battle_focus_spend_effects(
    *, state: GameState, player_id: str
) -> tuple[PersistingEffect, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    effects: list[PersistingEffect] = []
    for effect in state.persisting_effects:
        if effect.owner_player_id != requested_player_id:
            continue
        if effect.source_rule_id != SOURCE_RULE_ID:
            continue
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Aeldari Battle Focus spend effect payload is malformed.")
        if payload.get("effect_kind") != BATTLE_FOCUS_TOKEN_SPENT_EFFECT_KIND:
            continue
        _battle_focus_spend_payload(payload)
        effects.append(effect)
    return tuple(sorted(effects, key=lambda effect: effect.effect_id))


def _battle_focus_spend_payload(payload: JsonValue) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Aeldari Battle Focus spend effect payload must be an object.")
    if payload.get("effect_kind") != BATTLE_FOCUS_TOKEN_SPENT_EFFECT_KIND:
        raise GameLifecycleError("Aeldari Battle Focus spend effect kind drift.")
    maneuver = payload.get("maneuver")
    unit_instance_id = payload.get("unit_instance_id")
    if type(maneuver) is not str or type(unit_instance_id) is not str:
        raise GameLifecycleError("Aeldari Battle Focus spend effect payload is incomplete.")
    return {
        "maneuver": _validate_identifier("maneuver", maneuver),
        "unit_instance_id": _validate_identifier("unit_instance_id", unit_instance_id),
    }


def _army_for_player(state: GameState, *, player_id: str) -> ArmyDefinition:
    army = state.army_definition_for_player(_validate_identifier("player_id", player_id))
    if army is None:
        raise GameLifecycleError("Aeldari Agile Manoeuvres player army is missing.")
    return army


def _unit_is_eligible_agile_manoeuvre_unit(*, army: ArmyDefinition, unit: UnitInstance) -> bool:
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError("Aeldari Agile Manoeuvres army must be an ArmyDefinition.")
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Aeldari Agile Manoeuvres unit must be a UnitInstance.")
    if army.detachment_selection.faction_id != AELDARI_FACTION_ID:
        return False
    if not _army_contains_unit(army=army, unit=unit):
        raise GameLifecycleError("Aeldari Agile Manoeuvres unit is not in the acting army.")
    return _unit_has_faction_keyword(unit, ASURYANI) or _unit_has_faction_keyword(unit, AELDARI)


def _battlefield_scenario(state: GameState) -> BattlefieldScenario:
    if state.battlefield_state is None:
        raise GameLifecycleError("Aeldari Agile Manoeuvres requires battlefield state.")
    return BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )


def _triggering_unit_start_placement(
    *, scenario: BattlefieldScenario, context: MovementEndSurgeContext
) -> UnitPlacement:
    current = scenario.battlefield_state.unit_placement_by_id(context.triggering_unit_instance_id)
    trigger_payload = context.trigger_event_payload
    if not isinstance(trigger_payload, dict):
        raise GameLifecycleError("Aeldari Opportunity Seized trigger payload is malformed.")
    raw_batch = trigger_payload.get("transition_batch")
    if not isinstance(raw_batch, dict):
        raise GameLifecycleError("Aeldari Opportunity Seized trigger transition batch is missing.")
    transition_batch = BattlefieldTransitionBatch.from_payload(
        cast(BattlefieldTransitionBatchPayload, raw_batch)
    )
    start_poses = {
        record.model_instance_id: record.start_pose for record in transition_batch.displacements
    }
    start_model_placements = tuple(
        placement.with_pose(start_poses.get(placement.model_instance_id, placement.pose))
        for placement in current.model_placements
    )
    return current.with_model_placements(start_model_placements)


def _placed_unit_or_none(
    *,
    scenario: BattlefieldScenario,
    player_id: str,
    unit_instance_id: str,
) -> UnitPlacement | None:
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id != requested_player_id:
            continue
        for unit_placement in placed_army.unit_placements:
            if unit_placement.unit_instance_id == requested_unit_id:
                return unit_placement
    return None


def _unit_placements_within_engagement_range(
    *,
    scenario: BattlefieldScenario,
    ruleset_context: MovementEndSurgeContext,
    first: UnitPlacement,
    second: UnitPlacement,
) -> bool:
    first_models = _geometry_models_for_unit_placement(
        scenario=scenario,
        unit_placement=first,
    )
    second_models = _geometry_models_for_unit_placement(
        scenario=scenario,
        unit_placement=second,
    )
    engagement_policy = ruleset_context.ruleset_descriptor.engagement_policy
    for first_model in first_models:
        for second_model in second_models:
            if first_model.is_within_engagement_range(
                second_model,
                horizontal_inches=engagement_policy.horizontal_inches,
                vertical_inches=engagement_policy.vertical_inches,
            ):
                return True
    return False


def _geometry_models_for_unit_placement(
    *, scenario: BattlefieldScenario, unit_placement: UnitPlacement
) -> tuple[GeometryModel, ...]:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("Aeldari Agile Manoeuvres scenario is malformed.")
    if type(unit_placement) is not UnitPlacement:
        raise GameLifecycleError("Aeldari Agile Manoeuvres unit placement is malformed.")
    return tuple(
        geometry_model_for_placement(
            model=scenario.model_instance_for_placement(model_placement),
            placement=model_placement,
        )
        for model_placement in unit_placement.model_placements
    )


def _surge_battle_focus_spend_payload(
    *,
    maneuver: str,
    unit: UnitInstance,
    trigger_event_id: str,
    triggering_unit_instance_id: str,
) -> JsonValue:
    return {
        "effect_kind": BATTLE_FOCUS_TOKEN_SPENT_EFFECT_KIND,
        "maneuver": _validate_identifier("maneuver", maneuver),
        "unit_instance_id": unit.unit_instance_id,
        "battle_focus_token_cost": 1,
        "trigger_event_id": _validate_identifier("trigger_event_id", trigger_event_id),
        "triggering_unit_instance_id": _validate_identifier(
            "triggering_unit_instance_id",
            triggering_unit_instance_id,
        ),
    }


def _army_contains_unit(*, army: ArmyDefinition, unit: UnitInstance) -> bool:
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError("Aeldari Agile Manoeuvres army must be an ArmyDefinition.")
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Aeldari Agile Manoeuvres unit must be a UnitInstance.")
    return any(stored.unit_instance_id == unit.unit_instance_id for stored in army.units)


def _unit_by_id(state: GameState, unit_instance_id: str) -> UnitInstance:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return unit
    raise GameLifecycleError("Aeldari Agile Manoeuvres target unit is unknown.")


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Aeldari Agile Manoeuvres keyword lookup requires a UnitInstance.")
    canonical = _canonical_keyword(keyword)
    return any(_canonical_keyword(stored) == canonical for stored in unit.keywords)


def _unit_has_faction_keyword(unit: UnitInstance, keyword: str) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError(
            "Aeldari Agile Manoeuvres faction keyword lookup requires a UnitInstance."
        )
    canonical = _canonical_keyword(keyword)
    return any(_canonical_keyword(stored) == canonical for stored in unit.faction_keywords)


_validate_identifier = IdentifierValidator(GameLifecycleError)
