from __future__ import annotations

from dataclasses import replace
from typing import TypedDict

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import CatalogAbilitySourceKind
from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.faction_aliases import CHAOS_DAEMONS_FACTION_ID
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import AttackProfile, RangeProfileKind, WeaponProfile
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockHookBinding,
    BattleShockModifierContext,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
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
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.faction_content.common import (
    army_for_player as _shared_army_for_player,
)
from warhammer40k_core.engine.faction_content.common import canonical_keyword as _canonical_keyword
from warhammer40k_core.engine.faction_content.common import payload_bool as _payload_bool
from warhammer40k_core.engine.faction_content.common import (
    payload_identifier as _payload_string,
)
from warhammer40k_core.engine.faction_content.common import (
    payload_identifier_tuple as _payload_string_tuple,
)
from warhammer40k_core.engine.faction_content.common import payload_object as _payload_object
from warhammer40k_core.engine.fight_phase_end_hooks import (
    SELECT_FACTION_RULE_FIGHT_PHASE_END_OPTION_DECISION_TYPE,
    FightPhaseEndHookBinding,
    FightPhaseEndRequestContext,
    FightPhaseEndResultContext,
)
from warhammer40k_core.engine.mortal_wound_feel_no_pain_hooks import (
    MortalWoundFeelNoPainContinuationContext,
    MortalWoundFeelNoPainContinuationHookBinding,
)
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierBinding,
    HitRollModifierContext,
    MovementBudgetModifierBinding,
    MovementBudgetModifierContext,
    ObjectiveControlModifierBinding,
    ObjectiveControlModifierContext,
    WeaponProfileModifierBinding,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.sticky_objective_control import (
    PhaseEndObjectiveControlContext,
    PhaseEndObjectiveControlHookBinding,
    StickyObjectiveControlState,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.volume import Model as GeometryModel


class _RelentlessCarnageMortalWoundSourceContextPayload(TypedDict):
    source_kind: str
    phase: str
    resolution_payload: dict[str, JsonValue]


CONTRIBUTION_ID = "warhammer_40000_11th:chaos_daemons:datasheets"

LEGIONES_DAEMONICA = _canonical_keyword("Legiones Daemonica")
KHORNE = _canonical_keyword("Khorne")
TZEENTCH = _canonical_keyword("Tzeentch")
NURGLE = _canonical_keyword("Nurgle")
SLAANESH = _canonical_keyword("Slaanesh")

_DATASHEET_ABILITY_SOURCE_PREFIX = (
    "data-package:"
    + "waha"
    + "pedia:source-mirror:"
    + "1"
    + "0"
    + "th-edition-2026-06-14:Datasheets_abilities:"
)
BLOODTHIRSTER_DAEMON_LORD_SOURCE_ID = f"{_DATASHEET_ABILITY_SOURCE_PREFIX}000002582:4:description"
BLOODTHIRSTER_RELENTLESS_CARNAGE_SOURCE_ID = (
    f"{_DATASHEET_ABILITY_SOURCE_PREFIX}000002582:5:description"
)
BLOODTHIRSTER_GREATER_DAEMON_SOURCE_ID = (
    f"{_DATASHEET_ABILITY_SOURCE_PREFIX}000002582:6:description"
)
SKARBRAND_GREATER_DAEMON_SOURCE_ID = f"{_DATASHEET_ABILITY_SOURCE_PREFIX}000001105:4:description"
SKARBRAND_RAGE_EMBODIED_SOURCE_ID = f"{_DATASHEET_ABILITY_SOURCE_PREFIX}000001105:5:description"
LORD_OF_CHANGE_DAEMON_LORD_SOURCE_ID = f"{_DATASHEET_ABILITY_SOURCE_PREFIX}000001120:4:description"
LORD_OF_CHANGE_GREATER_DAEMON_SOURCE_ID = (
    f"{_DATASHEET_ABILITY_SOURCE_PREFIX}000001120:6:description"
)
KAIROS_GREATER_DAEMON_SOURCE_ID = f"{_DATASHEET_ABILITY_SOURCE_PREFIX}000001117:4:description"
GREAT_UNCLEAN_ONE_GREATER_DAEMON_SOURCE_ID = (
    f"{_DATASHEET_ABILITY_SOURCE_PREFIX}000001130:5:description"
)
PLAGUEBEARERS_INFECTED_OUTBREAK_SOURCE_ID = (
    f"{_DATASHEET_ABILITY_SOURCE_PREFIX}000001132:5:description"
)
KEEPER_DAEMON_LORD_SLAANESH_SOURCE_ID = f"{_DATASHEET_ABILITY_SOURCE_PREFIX}000001137:5:description"
KEEPER_GREATER_DAEMON_SOURCE_ID = f"{_DATASHEET_ABILITY_SOURCE_PREFIX}000001137:7:description"
ROTIGUS_GREATER_DAEMON_SOURCE_ID = f"{_DATASHEET_ABILITY_SOURCE_PREFIX}000001465:5:description"
ROTIGUS_DELUGE_SOURCE_ID = f"{_DATASHEET_ABILITY_SOURCE_PREFIX}000001465:7:description"
NURGLINGS_MISCHIEF_MAKERS_SOURCE_ID = f"{_DATASHEET_ABILITY_SOURCE_PREFIX}000001133:4:description"
POXBRINGER_FECULENT_DESPAIR_SOURCE_ID = f"{_DATASHEET_ABILITY_SOURCE_PREFIX}000001467:6:description"
SHALAXI_GREATER_DAEMON_SOURCE_ID = f"{_DATASHEET_ABILITY_SOURCE_PREFIX}000001648:4:description"
GREATER_DAEMON_SHADOW_AURA_SOURCE_IDS = (
    BLOODTHIRSTER_GREATER_DAEMON_SOURCE_ID,
    SKARBRAND_GREATER_DAEMON_SOURCE_ID,
    LORD_OF_CHANGE_GREATER_DAEMON_SOURCE_ID,
    KAIROS_GREATER_DAEMON_SOURCE_ID,
    GREAT_UNCLEAN_ONE_GREATER_DAEMON_SOURCE_ID,
    ROTIGUS_GREATER_DAEMON_SOURCE_ID,
    KEEPER_GREATER_DAEMON_SOURCE_ID,
    SHALAXI_GREATER_DAEMON_SOURCE_ID,
)

KHORNE_HIT_MODIFIER_ID = (
    "warhammer_40000_11th:chaos_daemons:datasheet:bloodthirster:daemon_lord_of_khorne"
)
RAGE_EMBODIED_ATTACKS_MODIFIER_ID = (
    "warhammer_40000_11th:chaos_daemons:datasheet:skarbrand:rage_embodied"
)
TZEENTCH_STRENGTH_MODIFIER_ID = (
    "warhammer_40000_11th:chaos_daemons:datasheet:lord_of_change:daemon_lord_of_tzeentch"
)
SLAANESH_AP_MODIFIER_ID = (
    "warhammer_40000_11th:chaos_daemons:datasheet:keeper_of_secrets:daemon_lord_of_slaanesh"
)
DELUGE_MOVEMENT_MODIFIER_ID = (
    "warhammer_40000_11th:chaos_daemons:datasheet:rotigus:deluge_of_nurgle:movement"
)
DELUGE_OBJECTIVE_CONTROL_MODIFIER_ID = (
    "warhammer_40000_11th:chaos_daemons:datasheet:rotigus:deluge_of_nurgle:objective_control"
)
MISCHIEF_MAKERS_HIT_MODIFIER_ID = (
    "warhammer_40000_11th:chaos_daemons:datasheet:nurglings:mischief_makers"
)
FECULENT_DESPAIR_HOOK_ID = (
    "warhammer_40000_11th:chaos_daemons:datasheet:poxbringer:feculent_despair"
)
INFECTED_OUTBREAK_HOOK_ID = (
    "warhammer_40000_11th:chaos_daemons:datasheet:plaguebearers:infected_outbreak"
)
RELENTLESS_CARNAGE_HOOK_ID = (
    "warhammer_40000_11th:chaos_daemons:datasheet:bloodthirster:relentless_carnage"
)
RELENTLESS_CARNAGE_FNP_HOOK_ID = f"{RELENTLESS_CARNAGE_HOOK_ID}:mortal-wound-fnp"
RELENTLESS_CARNAGE_SOURCE_KIND = "chaos_daemons_bloodthirster_relentless_carnage"
RELENTLESS_CARNAGE_SUBMISSION_KIND = "chaos_daemons_bloodthirster_relentless_carnage"
RELENTLESS_CARNAGE_ROLL_TYPE = "chaos_daemons.bloodthirster.relentless_carnage"
RELENTLESS_CARNAGE_DECLINED_EVENT = "chaos_daemons_bloodthirster_relentless_carnage_declined"
RELENTLESS_CARNAGE_PENDING_EVENT = (
    "chaos_daemons_bloodthirster_relentless_carnage_mortal_wounds_pending"
)
RELENTLESS_CARNAGE_RESOLVED_EVENT = "chaos_daemons_bloodthirster_relentless_carnage_resolved"
RELENTLESS_CARNAGE_DECLINE_OPTION_SUFFIX = "decline"


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        hit_roll_modifier_bindings=(
            HitRollModifierBinding(
                modifier_id=KHORNE_HIT_MODIFIER_ID,
                source_id=BLOODTHIRSTER_DAEMON_LORD_SOURCE_ID,
                handler=daemon_lord_of_khorne_hit_roll_modifier,
            ),
            HitRollModifierBinding(
                modifier_id=MISCHIEF_MAKERS_HIT_MODIFIER_ID,
                source_id=NURGLINGS_MISCHIEF_MAKERS_SOURCE_ID,
                handler=mischief_makers_hit_roll_modifier,
            ),
        ),
        movement_budget_modifier_bindings=(
            MovementBudgetModifierBinding(
                modifier_id=DELUGE_MOVEMENT_MODIFIER_ID,
                source_id=ROTIGUS_DELUGE_SOURCE_ID,
                handler=deluge_movement_budget_modifier,
            ),
        ),
        objective_control_modifier_bindings=(
            ObjectiveControlModifierBinding(
                modifier_id=DELUGE_OBJECTIVE_CONTROL_MODIFIER_ID,
                source_id=ROTIGUS_DELUGE_SOURCE_ID,
                handler=deluge_objective_control_modifier,
            ),
        ),
        weapon_profile_modifier_bindings=(
            WeaponProfileModifierBinding(
                modifier_id=RAGE_EMBODIED_ATTACKS_MODIFIER_ID,
                source_id=SKARBRAND_RAGE_EMBODIED_SOURCE_ID,
                handler=rage_embodied_weapon_profile_modifier,
            ),
            WeaponProfileModifierBinding(
                modifier_id=SLAANESH_AP_MODIFIER_ID,
                source_id=KEEPER_DAEMON_LORD_SLAANESH_SOURCE_ID,
                handler=daemon_lord_of_slaanesh_weapon_profile_modifier,
            ),
            WeaponProfileModifierBinding(
                modifier_id=TZEENTCH_STRENGTH_MODIFIER_ID,
                source_id=LORD_OF_CHANGE_DAEMON_LORD_SOURCE_ID,
                handler=daemon_lord_of_tzeentch_weapon_profile_modifier,
            ),
        ),
        phase_end_objective_control_hook_bindings=(
            PhaseEndObjectiveControlHookBinding(
                hook_id=INFECTED_OUTBREAK_HOOK_ID,
                source_id=PLAGUEBEARERS_INFECTED_OUTBREAK_SOURCE_ID,
                handler=infected_outbreak_sticky_objective_states,
            ),
        ),
        fight_phase_end_hook_bindings=(
            FightPhaseEndHookBinding(
                hook_id=RELENTLESS_CARNAGE_HOOK_ID,
                source_id=BLOODTHIRSTER_RELENTLESS_CARNAGE_SOURCE_ID,
                request_handler=relentless_carnage_fight_phase_end_request,
                result_handler=apply_relentless_carnage_fight_phase_end_result,
            ),
        ),
        mortal_wound_feel_no_pain_hook_bindings=(
            MortalWoundFeelNoPainContinuationHookBinding(
                hook_id=RELENTLESS_CARNAGE_FNP_HOOK_ID,
                source_id=BLOODTHIRSTER_RELENTLESS_CARNAGE_SOURCE_ID,
                source_kind=RELENTLESS_CARNAGE_SOURCE_KIND,
                handler=apply_relentless_carnage_mortal_wound_feel_no_pain_decision,
            ),
        ),
        battle_shock_hook_bindings=(
            BattleShockHookBinding(
                hook_id=FECULENT_DESPAIR_HOOK_ID,
                source_id=POXBRINGER_FECULENT_DESPAIR_SOURCE_ID,
                modifier_handler=feculent_despair_battle_shock_modifiers,
            ),
        ),
    )


def daemon_lord_of_khorne_hit_roll_modifier(context: HitRollModifierContext) -> int:
    if type(context) is not HitRollModifierContext:
        raise GameLifecycleError("Daemon Lord of Khorne requires a HitRollModifierContext.")
    if context.weapon_profile.range_profile.kind is not RangeProfileKind.MELEE:
        return 0
    return (
        1
        if _friendly_keyworded_rules_unit_within_source_aura(
            state=context.state,
            target_unit_instance_id=context.attacking_unit_instance_id,
            source_ability_id=BLOODTHIRSTER_DAEMON_LORD_SOURCE_ID,
            required_god_keyword=KHORNE,
        )
        else 0
    )


def daemon_lord_of_tzeentch_weapon_profile_modifier(
    context: WeaponProfileModifierContext,
) -> WeaponProfile:
    if type(context) is not WeaponProfileModifierContext:
        raise GameLifecycleError("Daemon Lord of Tzeentch requires a WeaponProfileModifierContext.")
    if context.weapon_profile.range_profile.kind is not RangeProfileKind.DISTANCE:
        return context.weapon_profile
    if not _friendly_keyworded_rules_unit_within_source_aura(
        state=context.state,
        target_unit_instance_id=context.attacking_unit_instance_id,
        source_ability_id=LORD_OF_CHANGE_DAEMON_LORD_SOURCE_ID,
        required_god_keyword=TZEENTCH,
    ):
        return context.weapon_profile
    return _profile_with_strength_modifier(
        profile=context.weapon_profile,
        source_id=LORD_OF_CHANGE_DAEMON_LORD_SOURCE_ID,
    )


def rage_embodied_weapon_profile_modifier(
    context: WeaponProfileModifierContext,
) -> WeaponProfile:
    if type(context) is not WeaponProfileModifierContext:
        raise GameLifecycleError("Rage Embodied requires a WeaponProfileModifierContext.")
    if context.weapon_profile.range_profile.kind is not RangeProfileKind.MELEE:
        return context.weapon_profile
    if not _friendly_keyworded_rules_unit_within_source_aura(
        state=context.state,
        target_unit_instance_id=context.attacking_unit_instance_id,
        source_ability_id=SKARBRAND_RAGE_EMBODIED_SOURCE_ID,
        required_god_keyword=KHORNE,
    ):
        return context.weapon_profile
    return _profile_with_attack_modifier(
        profile=context.weapon_profile,
        source_id=SKARBRAND_RAGE_EMBODIED_SOURCE_ID,
    )


def daemon_lord_of_slaanesh_weapon_profile_modifier(
    context: WeaponProfileModifierContext,
) -> WeaponProfile:
    if type(context) is not WeaponProfileModifierContext:
        raise GameLifecycleError("Daemon Lord of Slaanesh requires a WeaponProfileModifierContext.")
    if context.weapon_profile.range_profile.kind is not RangeProfileKind.MELEE:
        return context.weapon_profile
    if not _friendly_keyworded_rules_unit_within_source_aura(
        state=context.state,
        target_unit_instance_id=context.attacking_unit_instance_id,
        source_ability_id=KEEPER_DAEMON_LORD_SLAANESH_SOURCE_ID,
        required_god_keyword=SLAANESH,
    ):
        return context.weapon_profile
    return _profile_with_ap_modifier(
        profile=context.weapon_profile,
        source_id=KEEPER_DAEMON_LORD_SLAANESH_SOURCE_ID,
    )


def deluge_movement_budget_modifier(context: MovementBudgetModifierContext) -> float:
    if type(context) is not MovementBudgetModifierContext:
        raise GameLifecycleError("Deluge of Nurgle requires a MovementBudgetModifierContext.")
    if not _enemy_rules_unit_within_source_aura(
        state=context.state,
        target_unit_instance_id=context.unit_instance_id,
        source_ability_id=ROTIGUS_DELUGE_SOURCE_ID,
    ):
        return context.current_movement_inches
    return max(0.0, context.current_movement_inches - 2.0)


def deluge_objective_control_modifier(context: ObjectiveControlModifierContext) -> int:
    if type(context) is not ObjectiveControlModifierContext:
        raise GameLifecycleError("Deluge of Nurgle requires an ObjectiveControlModifierContext.")
    if not _enemy_rules_unit_within_source_aura(
        state=context.state,
        target_unit_instance_id=context.unit_instance_id,
        source_ability_id=ROTIGUS_DELUGE_SOURCE_ID,
    ):
        return context.current_objective_control
    return max(0, context.current_objective_control - 1)


def mischief_makers_hit_roll_modifier(context: HitRollModifierContext) -> int:
    if type(context) is not HitRollModifierContext:
        raise GameLifecycleError("Mischief Makers requires a HitRollModifierContext.")
    if context.source_phase is not BattlePhase.FIGHT:
        return 0
    if context.weapon_profile.range_profile.kind is not RangeProfileKind.MELEE:
        return 0
    attacking_rules_unit = rules_unit_view_by_id(
        state=context.state,
        unit_instance_id=context.attacking_unit_instance_id,
    )
    if _rules_unit_has_keywords(attacking_rules_unit, required_keywords=("titanic",)):
        return 0
    return (
        -1
        if _enemy_rules_unit_within_source_engagement_range(
            state=context.state,
            target_unit_instance_id=context.attacking_unit_instance_id,
            source_ability_id=NURGLINGS_MISCHIEF_MAKERS_SOURCE_ID,
        )
        else 0
    )


def feculent_despair_battle_shock_modifiers(
    context: BattleShockModifierContext,
) -> tuple[RollModifier, ...]:
    if type(context) is not BattleShockModifierContext:
        raise GameLifecycleError("Feculent Despair requires a BattleShockModifierContext.")
    source_player_ids = _enemy_source_aura_player_ids(
        state=context.state,
        target_unit_instance_id=context.request.unit_instance_id,
        source_ability_id=POXBRINGER_FECULENT_DESPAIR_SOURCE_ID,
    )
    return tuple(
        RollModifier(
            modifier_id=(
                f"{FECULENT_DESPAIR_HOOK_ID}:{context.request.request_id}:{source_player_id}"
            ),
            source_id=POXBRINGER_FECULENT_DESPAIR_SOURCE_ID,
            operand=-1,
        )
        for source_player_id in source_player_ids
    )


def infected_outbreak_sticky_objective_states(
    context: PhaseEndObjectiveControlContext,
) -> tuple[StickyObjectiveControlState, ...]:
    if type(context) is not PhaseEndObjectiveControlContext:
        raise GameLifecycleError("Infected Outbreak requires a phase-end context.")
    if context.completed_phase is not BattlePhase.COMMAND:
        return ()
    active_player_id = _active_player_id(context.state)
    objective_record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            context.state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=context.completed_phase,
            ruleset_descriptor=context.state.runtime_ruleset_descriptor(),
            runtime_modifier_registry=context.runtime_modifier_registry,
        )
    )
    states: list[StickyObjectiveControlState] = []
    for army in _chaos_daemons_armies(context.state):
        if army.player_id != active_player_id:
            continue
        for source_unit in army.units:
            if not _unit_has_datasheet_ability_source(
                source_unit,
                PLAGUEBEARERS_INFECTED_OUTBREAK_SOURCE_ID,
            ):
                continue
            if not source_unit.alive_own_models():
                continue
            rules_unit = rules_unit_view_by_id(
                state=context.state,
                unit_instance_id=source_unit.unit_instance_id,
            )
            if rules_unit.owner_player_id != army.player_id:
                raise GameLifecycleError("Infected Outbreak rules-unit owner drift.")
            contributor_unit_ids = frozenset(rules_unit.component_unit_instance_ids)
            for result in objective_record.results:
                if result.controlled_by_player_id != army.player_id:
                    continue
                if not any(
                    contribution.unit_instance_id in contributor_unit_ids
                    for contribution in result.contributors
                ):
                    continue
                states.append(
                    _infected_outbreak_sticky_state(
                        context=context,
                        source_unit=source_unit,
                        player_id=army.player_id,
                        objective_id=result.objective_id,
                    )
                )
    return tuple(sorted(states, key=lambda state: state.state_id))


def relentless_carnage_fight_phase_end_request(
    context: FightPhaseEndRequestContext,
) -> DecisionRequest | None:
    if type(context) is not FightPhaseEndRequestContext:
        raise GameLifecycleError("Relentless Carnage requires a Fight-end request context.")
    active_player_id = _active_player_id(context.state)
    for army in _chaos_daemons_armies(context.state):
        for source_unit in army.units:
            if not _unit_has_datasheet_ability_source(
                source_unit,
                BLOODTHIRSTER_RELENTLESS_CARNAGE_SOURCE_ID,
            ):
                continue
            if not source_unit.alive_own_models():
                continue
            source_rules_unit = rules_unit_view_by_id(
                state=context.state,
                unit_instance_id=source_unit.unit_instance_id,
            )
            if source_rules_unit.owner_player_id != army.player_id:
                raise GameLifecycleError("Relentless Carnage rules-unit owner drift.")
            if _relentless_carnage_recorded_this_fight_end(
                context=context,
                source_unit_instance_id=source_unit.unit_instance_id,
            ):
                continue
            eligible_enemy_unit_ids = _enemy_rules_unit_ids_within_source_engagement_range(
                state=context.state,
                source_unit_instance_id=source_unit.unit_instance_id,
            )
            if not eligible_enemy_unit_ids:
                continue
            return DecisionRequest(
                request_id=context.state.next_decision_request_id(),
                decision_type=SELECT_FACTION_RULE_FIGHT_PHASE_END_OPTION_DECISION_TYPE,
                actor_id=army.player_id,
                payload={
                    "game_id": context.state.game_id,
                    "battle_round": context.state.battle_round,
                    "active_player_id": active_player_id,
                    "phase": BattlePhase.FIGHT.value,
                    "player_id": army.player_id,
                    "source_rule_id": BLOODTHIRSTER_RELENTLESS_CARNAGE_SOURCE_ID,
                    "hook_id": RELENTLESS_CARNAGE_HOOK_ID,
                    "source_unit_instance_id": source_unit.unit_instance_id,
                    "source_rules_unit_instance_id": source_rules_unit.unit_instance_id,
                    "eligible_enemy_unit_instance_ids": list(eligible_enemy_unit_ids),
                },
                options=(
                    _relentless_carnage_decline_option(
                        game_id=context.state.game_id,
                        battle_round=context.state.battle_round,
                        active_player_id=active_player_id,
                        player_id=army.player_id,
                        source_unit_instance_id=source_unit.unit_instance_id,
                        source_rules_unit_instance_id=source_rules_unit.unit_instance_id,
                    ),
                    *(
                        _relentless_carnage_target_option(
                            game_id=context.state.game_id,
                            battle_round=context.state.battle_round,
                            active_player_id=active_player_id,
                            player_id=army.player_id,
                            source_unit_instance_id=source_unit.unit_instance_id,
                            source_rules_unit_instance_id=source_rules_unit.unit_instance_id,
                            target_enemy_unit_instance_id=enemy_unit_id,
                        )
                        for enemy_unit_id in eligible_enemy_unit_ids
                    ),
                ),
            )
    return None


def apply_relentless_carnage_fight_phase_end_result(
    context: FightPhaseEndResultContext,
) -> bool | LifecycleStatus:
    if type(context) is not FightPhaseEndResultContext:
        raise GameLifecycleError("Relentless Carnage requires a Fight-end result context.")
    request_payload = _payload_object(context.request.payload)
    if request_payload.get("hook_id") != RELENTLESS_CARNAGE_HOOK_ID:
        return False
    result_payload = _payload_object(context.result.payload)
    _validate_relentless_carnage_result_payload_matches_request(
        request_payload=request_payload,
        result_payload=result_payload,
    )
    player_id = _payload_string(result_payload, "player_id")
    source_unit_id = _payload_string(result_payload, "source_unit_instance_id")
    source_rules_unit_id = _payload_string(result_payload, "source_rules_unit_instance_id")
    use_ability = _payload_bool(result_payload, "use_ability")
    _validate_current_relentless_carnage_source(
        state=context.state,
        player_id=player_id,
        source_unit_instance_id=source_unit_id,
        source_rules_unit_instance_id=source_rules_unit_id,
    )
    if not use_ability:
        context.decisions.event_log.append(
            RELENTLESS_CARNAGE_DECLINED_EVENT,
            validate_json_value(
                {
                    **_relentless_carnage_base_resolution_payload(
                        context=context,
                        player_id=player_id,
                        source_unit_instance_id=source_unit_id,
                        source_rules_unit_instance_id=source_rules_unit_id,
                        target_enemy_unit_instance_id=None,
                    ),
                    "selected_option_id": context.result.selected_option_id,
                }
            ),
        )
        return True

    target_enemy_unit_id = _relentless_carnage_target_from_payload(result_payload)
    eligible_enemy_unit_ids = _payload_string_tuple(
        request_payload,
        key="eligible_enemy_unit_instance_ids",
    )
    if target_enemy_unit_id not in eligible_enemy_unit_ids:
        raise GameLifecycleError("Relentless Carnage target was not in the request snapshot.")
    if target_enemy_unit_id not in _enemy_rules_unit_ids_within_source_engagement_range(
        state=context.state,
        source_unit_instance_id=source_unit_id,
    ):
        raise GameLifecycleError("Relentless Carnage target is no longer eligible.")

    dice_manager = DiceRollManager(context.state.game_id, event_log=context.decisions.event_log)
    roll_state = dice_manager.roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=8, sides=6),
            reason="Relentless Carnage",
            roll_type=RELENTLESS_CARNAGE_ROLL_TYPE,
            actor_id=source_rules_unit_id,
        )
    )
    mortal_wounds = sum(1 for value in roll_state.current_values if value >= 4)
    resolution_payload = {
        **_relentless_carnage_base_resolution_payload(
            context=context,
            player_id=player_id,
            source_unit_instance_id=source_unit_id,
            source_rules_unit_instance_id=source_rules_unit_id,
            target_enemy_unit_instance_id=target_enemy_unit_id,
        ),
        "d6_result": validate_json_value(roll_state.to_payload()),
        "success_threshold": 4,
        "mortal_wounds": mortal_wounds,
    }
    if mortal_wounds == 0:
        context.decisions.event_log.append(
            RELENTLESS_CARNAGE_RESOLVED_EVENT,
            validate_json_value(
                {
                    **resolution_payload,
                    "mortal_wound_application": None,
                }
            ),
        )
        return True

    progress = MortalWoundApplicationProgress.start(
        application_id=(
            f"relentless-carnage:{context.state.game_id}:"
            f"round-{context.state.battle_round:02d}:"
            f"{source_rules_unit_id}:{target_enemy_unit_id}:{context.result.result_id}"
        ),
        source_rule_id=BLOODTHIRSTER_RELENTLESS_CARNAGE_SOURCE_ID,
        source_context=validate_json_value(
            _relentless_carnage_mortal_wound_source_context(resolution_payload=resolution_payload)
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
    routed_status = _resolve_routed_relentless_carnage_mortal_wounds(
        state=context.state,
        decisions=context.decisions,
        feel_no_pain_result_id=None,
        routed_request=routed.request,
        routed_application=routed.application,
        routed_progress=routed.progress,
    )
    return True if routed_status is None else routed_status


def apply_relentless_carnage_mortal_wound_feel_no_pain_decision(
    context: MortalWoundFeelNoPainContinuationContext,
) -> LifecycleStatus | None:
    if type(context) is not MortalWoundFeelNoPainContinuationContext:
        raise GameLifecycleError("Relentless Carnage FNP continuation requires context.")
    routed = resolve_mortal_wound_feel_no_pain_decision(
        state=context.state,
        request=context.request,
        result=context.result,
        next_request_id=context.state.next_decision_request_id(),
        dice_manager=context.dice_manager,
    )
    return _resolve_routed_relentless_carnage_mortal_wounds(
        state=context.state,
        decisions=context.decisions,
        feel_no_pain_result_id=context.result.result_id,
        routed_request=routed.request,
        routed_application=routed.application,
        routed_progress=routed.progress,
    )


def _friendly_keyworded_rules_unit_within_source_aura(
    *,
    state: object,
    target_unit_instance_id: str,
    source_ability_id: str,
    required_god_keyword: str,
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Chaos Daemons datasheet aura lookup requires GameState.")
    if state.battlefield_state is None:
        raise GameLifecycleError("Chaos Daemons datasheet aura lookup requires battlefield_state.")
    target_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=target_unit_instance_id,
    )
    if not _rules_unit_has_keywords(
        target_rules_unit,
        required_keywords=(LEGIONES_DAEMONICA, required_god_keyword),
    ):
        return False
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    target_models = _alive_geometry_models_for_rules_unit(
        state=state,
        scenario=scenario,
        rules_unit=target_rules_unit,
    )
    if not target_models:
        return False
    for army in _chaos_daemons_armies(state):
        if army.player_id != target_rules_unit.owner_player_id:
            continue
        for source_unit in army.units:
            if not _unit_has_datasheet_ability_source(source_unit, source_ability_id):
                continue
            source_models = _alive_geometry_models_for_unit(
                state=state,
                scenario=scenario,
                unit=source_unit,
            )
            if _models_within_distance(
                first_models=source_models,
                second_models=target_models,
                distance_inches=6.0,
            ):
                return True
    return False


def _enemy_rules_unit_within_source_aura(
    *,
    state: object,
    target_unit_instance_id: str,
    source_ability_id: str,
) -> bool:
    return bool(
        _enemy_source_aura_player_ids(
            state=state,
            target_unit_instance_id=target_unit_instance_id,
            source_ability_id=source_ability_id,
        )
    )


def _enemy_source_aura_player_ids(
    *,
    state: object,
    target_unit_instance_id: str,
    source_ability_id: str,
) -> tuple[str, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Chaos Daemons enemy aura lookup requires GameState.")
    if state.battlefield_state is None:
        raise GameLifecycleError("Chaos Daemons enemy aura lookup requires battlefield_state.")
    target_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=target_unit_instance_id,
    )
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    target_models = _alive_geometry_models_for_rules_unit(
        state=state,
        scenario=scenario,
        rules_unit=target_rules_unit,
    )
    if not target_models:
        return ()
    source_player_ids: set[str] = set()
    for army in _chaos_daemons_armies(state):
        if army.player_id == target_rules_unit.owner_player_id:
            continue
        for source_unit in army.units:
            if not _unit_has_datasheet_ability_source(source_unit, source_ability_id):
                continue
            source_models = _alive_geometry_models_for_unit(
                state=state,
                scenario=scenario,
                unit=source_unit,
            )
            if _models_within_distance(
                first_models=source_models,
                second_models=target_models,
                distance_inches=6.0,
            ):
                source_player_ids.add(army.player_id)
                break
    return tuple(sorted(source_player_ids))


def _enemy_rules_unit_within_source_engagement_range(
    *,
    state: object,
    target_unit_instance_id: str,
    source_ability_id: str,
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Chaos Daemons enemy engagement lookup requires GameState.")
    if state.battlefield_state is None:
        raise GameLifecycleError(
            "Chaos Daemons enemy engagement lookup requires battlefield_state."
        )
    target_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=target_unit_instance_id,
    )
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    target_models = _alive_geometry_models_for_rules_unit(
        state=state,
        scenario=scenario,
        rules_unit=target_rules_unit,
    )
    if not target_models:
        return False
    for army in _chaos_daemons_armies(state):
        if army.player_id == target_rules_unit.owner_player_id:
            continue
        for source_unit in army.units:
            if not _unit_has_datasheet_ability_source(source_unit, source_ability_id):
                continue
            source_models = _alive_geometry_models_for_unit(
                state=state,
                scenario=scenario,
                unit=source_unit,
            )
            if _any_models_within_engagement_range(
                state=state,
                first_models=source_models,
                second_models=target_models,
            ):
                return True
    return False


def _infected_outbreak_sticky_state(
    *,
    context: PhaseEndObjectiveControlContext,
    source_unit: UnitInstance,
    player_id: str,
    objective_id: str,
) -> StickyObjectiveControlState:
    state_id = (
        f"infected-outbreak:{context.state.game_id}:round-{context.state.battle_round:02d}:"
        f"{player_id}:{objective_id}:{source_unit.unit_instance_id}"
    )
    source_event_id = (
        f"infected-outbreak-phase-end:{context.state.game_id}:"
        f"round-{context.state.battle_round:02d}:{player_id}:{objective_id}:"
        f"{source_unit.unit_instance_id}"
    )
    return StickyObjectiveControlState(
        state_id=state_id,
        game_id=context.state.game_id,
        player_id=player_id,
        objective_id=objective_id,
        source_rule_id=PLAGUEBEARERS_INFECTED_OUTBREAK_SOURCE_ID,
        source_event_id=source_event_id,
        battle_round=context.state.battle_round,
        phase=context.completed_phase.value,
        active_player_id=_active_player_id(context.state),
        originating_unit_instance_id=source_unit.unit_instance_id,
        destroyed_unit_instance_id=source_unit.unit_instance_id,
        replay_payload=validate_json_value(
            {
                "effect_kind": "chaos_daemons_plaguebearers_infected_outbreak",
                "source_rule_id": PLAGUEBEARERS_INFECTED_OUTBREAK_SOURCE_ID,
                "hook_id": INFECTED_OUTBREAK_HOOK_ID,
                "player_id": player_id,
                "objective_id": objective_id,
                "unit_instance_id": source_unit.unit_instance_id,
            }
        ),
    )


def _relentless_carnage_decline_option(
    *,
    game_id: str,
    battle_round: int,
    active_player_id: str,
    player_id: str,
    source_unit_instance_id: str,
    source_rules_unit_instance_id: str,
) -> DecisionOption:
    return DecisionOption(
        option_id=(
            f"chaos-daemons:bloodthirster:relentless-carnage:"
            f"{source_rules_unit_instance_id}:{RELENTLESS_CARNAGE_DECLINE_OPTION_SUFFIX}"
        ),
        label="Decline Relentless Carnage",
        payload={
            "submission_kind": RELENTLESS_CARNAGE_SUBMISSION_KIND,
            "game_id": game_id,
            "battle_round": battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.FIGHT.value,
            "player_id": player_id,
            "source_rule_id": BLOODTHIRSTER_RELENTLESS_CARNAGE_SOURCE_ID,
            "hook_id": RELENTLESS_CARNAGE_HOOK_ID,
            "source_unit_instance_id": source_unit_instance_id,
            "source_rules_unit_instance_id": source_rules_unit_instance_id,
            "use_ability": False,
            "target_enemy_unit_instance_id": None,
        },
    )


def _relentless_carnage_target_option(
    *,
    game_id: str,
    battle_round: int,
    active_player_id: str,
    player_id: str,
    source_unit_instance_id: str,
    source_rules_unit_instance_id: str,
    target_enemy_unit_instance_id: str,
) -> DecisionOption:
    return DecisionOption(
        option_id=(
            f"chaos-daemons:bloodthirster:relentless-carnage:"
            f"{source_rules_unit_instance_id}:target:{target_enemy_unit_instance_id}"
        ),
        label=f"Select {target_enemy_unit_instance_id} for Relentless Carnage",
        payload={
            "submission_kind": RELENTLESS_CARNAGE_SUBMISSION_KIND,
            "game_id": game_id,
            "battle_round": battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.FIGHT.value,
            "player_id": player_id,
            "source_rule_id": BLOODTHIRSTER_RELENTLESS_CARNAGE_SOURCE_ID,
            "hook_id": RELENTLESS_CARNAGE_HOOK_ID,
            "source_unit_instance_id": source_unit_instance_id,
            "source_rules_unit_instance_id": source_rules_unit_instance_id,
            "use_ability": True,
            "target_enemy_unit_instance_id": target_enemy_unit_instance_id,
        },
    )


def _resolve_routed_relentless_carnage_mortal_wounds(
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
        raise GameLifecycleError("Relentless Carnage mortal wound routing requires GameState.")
    if type(decisions) is not DecisionController:
        raise GameLifecycleError(
            "Relentless Carnage mortal wound routing requires DecisionController."
        )
    if type(routed_progress) is not MortalWoundApplicationProgress:
        raise GameLifecycleError("Relentless Carnage mortal wound routing requires progress.")
    source_context = _relentless_carnage_mortal_wound_source_context_from_payload(
        routed_progress.source_context
    )
    resolution_payload = source_context["resolution_payload"]
    if routed_request is not None:
        decisions.request_decision(routed_request)
        decisions.event_log.append(
            RELENTLESS_CARNAGE_PENDING_EVENT,
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
                "source_rule_id": BLOODTHIRSTER_RELENTLESS_CARNAGE_SOURCE_ID,
                "source_kind": RELENTLESS_CARNAGE_SOURCE_KIND,
                "target_unit_instance_id": resolution_payload["target_enemy_unit_instance_id"],
                "remaining_mortal_wounds": routed_progress.remaining_mortal_wounds,
            },
        )
    if routed_application is None:
        raise GameLifecycleError("Relentless Carnage routing did not produce application.")
    resolved_payload: dict[str, JsonValue] = {
        **resolution_payload,
        "mortal_wound_application": validate_json_value(routed_application.to_payload()),
    }
    if feel_no_pain_result_id is not None:
        resolved_payload["feel_no_pain_result_id"] = feel_no_pain_result_id
    decisions.event_log.append(
        RELENTLESS_CARNAGE_RESOLVED_EVENT,
        validate_json_value(resolved_payload),
    )
    return None


def _relentless_carnage_base_resolution_payload(
    *,
    context: FightPhaseEndResultContext,
    player_id: str,
    source_unit_instance_id: str,
    source_rules_unit_instance_id: str,
    target_enemy_unit_instance_id: str | None,
) -> dict[str, JsonValue]:
    return {
        "game_id": context.state.game_id,
        "battle_round": context.state.battle_round,
        "active_player_id": _active_player_id(context.state),
        "phase": BattlePhase.FIGHT.value,
        "player_id": player_id,
        "source_rule_id": BLOODTHIRSTER_RELENTLESS_CARNAGE_SOURCE_ID,
        "hook_id": RELENTLESS_CARNAGE_HOOK_ID,
        "source_unit_instance_id": source_unit_instance_id,
        "source_rules_unit_instance_id": source_rules_unit_instance_id,
        "target_enemy_unit_instance_id": target_enemy_unit_instance_id,
        "request_id": context.request.request_id,
        "result_id": context.result.result_id,
    }


def _relentless_carnage_mortal_wound_source_context(
    *,
    resolution_payload: dict[str, JsonValue],
) -> _RelentlessCarnageMortalWoundSourceContextPayload:
    return {
        "source_kind": RELENTLESS_CARNAGE_SOURCE_KIND,
        "phase": BattlePhase.FIGHT.value,
        "resolution_payload": resolution_payload,
    }


def _relentless_carnage_mortal_wound_source_context_from_payload(
    value: JsonValue,
) -> _RelentlessCarnageMortalWoundSourceContextPayload:
    if not isinstance(value, dict):
        raise GameLifecycleError("Relentless Carnage source context must be an object.")
    if value.get("source_kind") != RELENTLESS_CARNAGE_SOURCE_KIND:
        raise GameLifecycleError("Relentless Carnage source kind drift.")
    if value.get("phase") != BattlePhase.FIGHT.value:
        raise GameLifecycleError("Relentless Carnage source phase drift.")
    resolution_payload = value.get("resolution_payload")
    if not isinstance(resolution_payload, dict):
        raise GameLifecycleError("Relentless Carnage source context missing payload.")
    return {
        "source_kind": RELENTLESS_CARNAGE_SOURCE_KIND,
        "phase": BattlePhase.FIGHT.value,
        "resolution_payload": resolution_payload,
    }


def _validate_relentless_carnage_result_payload_matches_request(
    *,
    request_payload: dict[str, JsonValue],
    result_payload: dict[str, JsonValue],
) -> None:
    for key in (
        "source_rule_id",
        "hook_id",
        "source_unit_instance_id",
        "source_rules_unit_instance_id",
    ):
        if request_payload.get(key) != result_payload.get(key):
            raise GameLifecycleError("Relentless Carnage result payload drift.")
    if result_payload.get("submission_kind") != RELENTLESS_CARNAGE_SUBMISSION_KIND:
        raise GameLifecycleError("Relentless Carnage submission kind drift.")


def _validate_current_relentless_carnage_source(
    *,
    state: object,
    player_id: str,
    source_unit_instance_id: str,
    source_rules_unit_instance_id: str,
) -> None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Relentless Carnage source validation requires GameState.")
    army = _shared_army_for_player(
        tuple(state.army_definitions),
        player_id=player_id,
        context="Relentless Carnage",
    )
    source_unit = _unit_by_id(army.units, unit_instance_id=source_unit_instance_id)
    if not _unit_has_datasheet_ability_source(
        source_unit,
        BLOODTHIRSTER_RELENTLESS_CARNAGE_SOURCE_ID,
    ):
        raise GameLifecycleError("Relentless Carnage source ability is missing.")
    if not source_unit.alive_own_models():
        raise GameLifecycleError("Relentless Carnage source unit is not alive.")
    source_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=source_unit_instance_id,
    )
    if source_rules_unit.unit_instance_id != source_rules_unit_instance_id:
        raise GameLifecycleError("Relentless Carnage source rules-unit drift.")
    if source_rules_unit.owner_player_id != player_id:
        raise GameLifecycleError("Relentless Carnage source owner drift.")


def _relentless_carnage_target_from_payload(payload: dict[str, JsonValue]) -> str:
    target = payload.get("target_enemy_unit_instance_id")
    if type(target) is not str or not target.strip():
        raise GameLifecycleError("Relentless Carnage target must be selected.")
    return _validate_identifier("target_enemy_unit_instance_id", target)


def _relentless_carnage_recorded_this_fight_end(
    *,
    context: FightPhaseEndRequestContext,
    source_unit_instance_id: str,
) -> bool:
    requested_unit_id = _validate_identifier("source_unit_instance_id", source_unit_instance_id)
    for event in context.decisions.event_log.records:
        if event.event_type not in {
            RELENTLESS_CARNAGE_DECLINED_EVENT,
            RELENTLESS_CARNAGE_PENDING_EVENT,
            RELENTLESS_CARNAGE_RESOLVED_EVENT,
        }:
            continue
        payload = _payload_object(event.payload, field_name="Relentless Carnage event payload")
        if payload.get("source_rule_id") != BLOODTHIRSTER_RELENTLESS_CARNAGE_SOURCE_ID:
            continue
        if payload.get("phase") != BattlePhase.FIGHT.value:
            continue
        if payload.get("battle_round") != context.state.battle_round:
            continue
        if payload.get("active_player_id") != _active_player_id(context.state):
            continue
        if payload.get("source_unit_instance_id") == requested_unit_id:
            return True
    return False


def _enemy_rules_unit_ids_within_source_engagement_range(
    *,
    state: object,
    source_unit_instance_id: str,
) -> tuple[str, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Relentless Carnage target lookup requires GameState.")
    if state.battlefield_state is None:
        raise GameLifecycleError("Relentless Carnage target lookup requires battlefield_state.")
    source_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=source_unit_instance_id,
    )
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    source_models = _alive_geometry_models_for_rules_unit(
        state=state,
        scenario=scenario,
        rules_unit=source_rules_unit,
    )
    if not source_models:
        return ()
    enemy_rules_unit_ids: set[str] = set()
    checked_rules_unit_ids: set[str] = set()
    for army in state.army_definitions:
        if army.player_id == source_rules_unit.owner_player_id:
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
                first_models=source_models,
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
        raise GameLifecycleError("Rules-unit geometry lookup requires GameState.")
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("Rules-unit geometry lookup requires scenario.")
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Rules-unit geometry lookup requires rules unit.")
    if state.battlefield_state is None:
        raise GameLifecycleError("Rules-unit geometry lookup requires battlefield_state.")
    models: list[GeometryModel] = []
    for component in rules_unit.components:
        unit_placement = state.battlefield_state.unit_placement_or_none(
            component.unit.unit_instance_id
        )
        if unit_placement is None:
            continue
        for model_placement in unit_placement.model_placements:
            model = scenario.model_instance_for_placement(model_placement)
            if not model.is_alive:
                continue
            models.append(geometry_model_for_placement(model=model, placement=model_placement))
    return tuple(models)


def _alive_geometry_models_for_unit(
    *,
    state: object,
    scenario: BattlefieldScenario,
    unit: UnitInstance,
) -> tuple[GeometryModel, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Unit geometry lookup requires GameState.")
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("Unit geometry lookup requires scenario.")
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Unit geometry lookup requires UnitInstance.")
    if state.battlefield_state is None:
        raise GameLifecycleError("Unit geometry lookup requires battlefield_state.")
    unit_placement = state.battlefield_state.unit_placement_or_none(unit.unit_instance_id)
    if unit_placement is None:
        return ()
    return tuple(
        geometry_model_for_placement(
            model=scenario.model_instance_for_placement(model_placement),
            placement=model_placement,
        )
        for model_placement in unit_placement.model_placements
        if scenario.model_instance_for_placement(model_placement).is_alive
    )


def _models_within_distance(
    *,
    first_models: tuple[GeometryModel, ...],
    second_models: tuple[GeometryModel, ...],
    distance_inches: float,
) -> bool:
    for first_model in first_models:
        for second_model in second_models:
            if (
                shapely_backend.base_footprint_distance(
                    first_model.base,
                    first_model.pose,
                    second_model.base,
                    second_model.pose,
                )
                <= distance_inches
            ):
                return True
    return False


def _any_models_within_engagement_range(
    *,
    state: object,
    first_models: tuple[GeometryModel, ...],
    second_models: tuple[GeometryModel, ...],
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Engagement range lookup requires GameState.")
    policy = state.runtime_ruleset_descriptor().engagement_policy
    for first_model in first_models:
        for second_model in second_models:
            if first_model.is_within_engagement_range(
                second_model,
                horizontal_inches=policy.horizontal_inches,
                vertical_inches=policy.vertical_inches,
            ):
                return True
    return False


def _profile_with_strength_modifier(
    *,
    profile: WeaponProfile,
    source_id: str,
) -> WeaponProfile:
    if source_id in profile.source_ids:
        return profile
    if not profile.strength.is_numeric:
        raise GameLifecycleError("Daemon Lord of Tzeentch cannot modify dash Strength.")
    return replace(
        profile,
        strength=CharacteristicValue.from_raw(
            profile.strength.characteristic,
            profile.strength.final + 1,
        ),
        source_ids=tuple(sorted({*profile.source_ids, source_id})),
    )


def _profile_with_attack_modifier(
    *,
    profile: WeaponProfile,
    source_id: str,
) -> WeaponProfile:
    if source_id in profile.source_ids:
        return profile
    return replace(
        profile,
        attack_profile=_attack_profile_with_delta(profile.attack_profile, delta=1),
        source_ids=tuple(sorted({*profile.source_ids, source_id})),
    )


def _attack_profile_with_delta(profile: AttackProfile, *, delta: int) -> AttackProfile:
    if type(profile) is not AttackProfile:
        raise GameLifecycleError("Rage Embodied requires an AttackProfile.")
    if type(delta) is not int:
        raise GameLifecycleError("AttackProfile delta must be an integer.")
    if profile.fixed_attacks is not None:
        return AttackProfile.fixed(max(1, profile.fixed_attacks + delta))
    if profile.dice_expression is None:
        raise GameLifecycleError("AttackProfile requires fixed attacks or dice expression.")
    return AttackProfile.dice(
        replace(
            profile.dice_expression,
            modifier=profile.dice_expression.modifier + delta,
        )
    )


def _profile_with_ap_modifier(
    *,
    profile: WeaponProfile,
    source_id: str,
) -> WeaponProfile:
    if source_id in profile.source_ids:
        return profile
    return replace(
        profile,
        armor_penetration=_armor_penetration_with_delta(
            profile.armor_penetration,
            delta=-1,
        ),
        source_ids=tuple(sorted({*profile.source_ids, source_id})),
    )


def _armor_penetration_with_delta(value: CharacteristicValue, *, delta: int) -> CharacteristicValue:
    if type(value) is not CharacteristicValue:
        raise GameLifecycleError("Daemon Lord of Slaanesh requires CharacteristicValue AP.")
    if value.characteristic is not Characteristic.ARMOR_PENETRATION:
        raise GameLifecycleError("Daemon Lord of Slaanesh requires Armor Penetration.")
    if type(delta) is not int:
        raise GameLifecycleError("Armor Penetration delta must be an integer.")
    if not value.is_numeric:
        raise GameLifecycleError("Daemon Lord of Slaanesh cannot modify dash AP.")
    return CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, value.final + delta)


def _rules_unit_has_keywords(
    rules_unit: RulesUnitView,
    *,
    required_keywords: tuple[str, ...],
) -> bool:
    keyword_tokens = frozenset((*rules_unit.keywords, *rules_unit.faction_keywords))
    return all(_canonical_keyword(keyword) in keyword_tokens for keyword in required_keywords)


def _unit_has_datasheet_ability_source(unit: UnitInstance, source_id: str) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Datasheet ability lookup requires UnitInstance.")
    requested_source_id = _validate_identifier("source_id", source_id)
    return any(
        ability.source_kind is CatalogAbilitySourceKind.DATASHEET
        and ability.source_id == requested_source_id
        for ability in unit.datasheet_abilities
    )


def _chaos_daemons_armies(state: object) -> tuple[ArmyDefinition, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Chaos Daemons army lookup requires GameState.")
    return tuple(
        army
        for army in state.army_definitions
        if army.detachment_selection.faction_id == CHAOS_DAEMONS_FACTION_ID
    )


def _unit_by_id(units: tuple[UnitInstance, ...], *, unit_instance_id: str) -> UnitInstance:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for unit in units:
        if unit.unit_instance_id == requested_unit_id:
            return unit
    raise GameLifecycleError("Unit instance is unknown.")


def _active_player_id(state: object) -> str:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Active player lookup requires GameState.")
    if state.active_player_id is None:
        raise GameLifecycleError("Active player lookup requires active_player_id.")
    return state.active_player_id


_validate_identifier = IdentifierValidator(GameLifecycleError)
