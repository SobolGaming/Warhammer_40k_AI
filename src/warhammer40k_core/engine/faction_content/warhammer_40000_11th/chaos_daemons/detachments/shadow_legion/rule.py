from __future__ import annotations

from warhammer40k_core.core.faction_aliases import CHAOS_DAEMONS_FACTION_ID
from warhammer40k_core.core.weapon_profiles import RangeProfileKind
from warhammer40k_core.engine.advance_eligibility_hooks import (
    AdvanceEligibilityContext,
    AdvanceEligibilityGrant,
    AdvanceEligibilityHookBinding,
)
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedHookBinding,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (
    army_rule as dark_pacts,
)
from warhammer40k_core.engine.fight_unit_selected_hooks import (
    FightUnitSelectedContext,
    FightUnitSelectedGrant,
    FightUnitSelectedGrantBinding,
)
from warhammer40k_core.engine.mortal_wound_feel_no_pain_hooks import (
    MortalWoundFeelNoPainContinuationHookBinding,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierBinding,
    HitRollModifierContext,
    WeaponProfileModifierBinding,
    WoundRollModifierBinding,
    WoundRollModifierContext,
)
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.shooting_unit_selected_hooks import (
    ShootingUnitSelectedContext,
    ShootingUnitSelectedGrant,
    ShootingUnitSelectedGrantBinding,
)
from warhammer40k_core.engine.target_restriction_hooks import (
    ShootingTargetRestrictionContext,
    ShootingTargetRestrictionHookBinding,
    TargetRestriction,
)
from warhammer40k_core.engine.unit_factory import UnitInstance

CONTRIBUTION_ID = "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:rule"
SOURCE_RULE_ID = dark_pacts.SHADOW_LEGION_SOURCE_RULE_ID
HOOK_ID = "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:rule"

DETACHMENT_ID = "shadow-legion"
SHADOW_LEGION_KEYWORD = "SHADOW LEGION"
UNDIVIDED_KEYWORD = "UNDIVIDED"
KHORNE_KEYWORD = "KHORNE"
TZEENTCH_KEYWORD = "TZEENTCH"
NURGLE_KEYWORD = "NURGLE"
SLAANESH_KEYWORD = "SLAANESH"

ADVANCE_ELIGIBILITY_HOOK_ID = f"{HOOK_ID}:murderers-cowl:advance-eligibility"
TZEENTCH_HIT_MODIFIER_ID = f"{HOOK_ID}:penumbral-puppetry:hit-roll"
NURGLE_WOUND_MODIFIER_ID = f"{HOOK_ID}:gloam-rot:wound-roll"
SLAANESH_TARGET_RESTRICTION_HOOK_ID = f"{HOOK_ID}:shadows-caress:snap-target-restriction"
SHOOTING_LETHAL_HITS_HOOK_ID = f"{HOOK_ID}:disciples-of-belakor:shooting:lethal_hits"
SHOOTING_SUSTAINED_HITS_HOOK_ID = f"{HOOK_ID}:disciples-of-belakor:shooting:sustained_hits_1"
FIGHT_LETHAL_HITS_HOOK_ID = f"{HOOK_ID}:disciples-of-belakor:fight:lethal_hits"
FIGHT_SUSTAINED_HITS_HOOK_ID = f"{HOOK_ID}:disciples-of-belakor:fight:sustained_hits_1"
ATTACK_SEQUENCE_COMPLETED_HOOK_ID = dark_pacts.SHADOW_LEGION_ATTACK_SEQUENCE_COMPLETED_HOOK_ID
MORTAL_WOUND_FEEL_NO_PAIN_HOOK_ID = f"{HOOK_ID}:disciples-of-belakor:mortal-wound-fnp"
WEAPON_PROFILE_MODIFIER_ID = f"{HOOK_ID}:disciples-of-belakor:weapon-profile"


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        advance_eligibility_hook_bindings=(
            AdvanceEligibilityHookBinding(
                hook_id=ADVANCE_ELIGIBILITY_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=murderers_cowl_advance_eligibility,
            ),
        ),
        shooting_target_restriction_hook_bindings=(
            ShootingTargetRestrictionHookBinding(
                hook_id=SLAANESH_TARGET_RESTRICTION_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=shadows_caress_snap_target_restriction,
            ),
        ),
        shooting_unit_selected_grant_hook_bindings=(
            ShootingUnitSelectedGrantBinding(
                hook_id=SHOOTING_LETHAL_HITS_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=shooting_lethal_hits_dark_pact_grant,
            ),
            ShootingUnitSelectedGrantBinding(
                hook_id=SHOOTING_SUSTAINED_HITS_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=shooting_sustained_hits_dark_pact_grant,
            ),
        ),
        fight_unit_selected_grant_hook_bindings=(
            FightUnitSelectedGrantBinding(
                hook_id=FIGHT_LETHAL_HITS_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=fight_lethal_hits_dark_pact_grant,
            ),
            FightUnitSelectedGrantBinding(
                hook_id=FIGHT_SUSTAINED_HITS_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=fight_sustained_hits_dark_pact_grant,
            ),
        ),
        attack_sequence_completed_hook_bindings=(
            AttackSequenceCompletedHookBinding(
                hook_id=ATTACK_SEQUENCE_COMPLETED_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=dark_pacts.resolve_dark_pact_attack_sequence_completion,
            ),
        ),
        mortal_wound_feel_no_pain_hook_bindings=(
            MortalWoundFeelNoPainContinuationHookBinding(
                hook_id=MORTAL_WOUND_FEEL_NO_PAIN_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                source_kind=dark_pacts.SHADOW_LEGION_DARK_PACT_MORTAL_WOUNDS_SOURCE_KIND,
                handler=dark_pacts.apply_dark_pact_mortal_wound_feel_no_pain_decision,
            ),
        ),
        hit_roll_modifier_bindings=(
            HitRollModifierBinding(
                modifier_id=TZEENTCH_HIT_MODIFIER_ID,
                source_id=SOURCE_RULE_ID,
                handler=penumbral_puppetry_hit_roll_modifier,
            ),
        ),
        wound_roll_modifier_bindings=(
            WoundRollModifierBinding(
                modifier_id=NURGLE_WOUND_MODIFIER_ID,
                source_id=SOURCE_RULE_ID,
                handler=gloam_rot_wound_roll_modifier,
            ),
        ),
        weapon_profile_modifier_bindings=(
            WeaponProfileModifierBinding(
                modifier_id=WEAPON_PROFILE_MODIFIER_ID,
                source_id=SOURCE_RULE_ID,
                handler=dark_pacts.dark_pact_weapon_profile_modifier,
            ),
        ),
    )


def murderers_cowl_advance_eligibility(
    context: AdvanceEligibilityContext,
) -> AdvanceEligibilityGrant | None:
    if type(context) is not AdvanceEligibilityContext:
        raise GameLifecycleError("Murderer's Cowl Advance eligibility requires context.")
    if not _rules_unit_has_shadow_legion_god_keyword(
        state=context.state,
        player_id=context.player_id,
        unit_instance_id=context.unit_instance_id,
        god_keyword=KHORNE_KEYWORD,
    ):
        return None
    return AdvanceEligibilityGrant(
        hook_id=ADVANCE_ELIGIBILITY_HOOK_ID,
        source_id=SOURCE_RULE_ID,
        can_shoot=True,
        can_declare_charge=True,
        replay_payload=_shadow_legion_replay_payload(context.battle_round),
    )


def penumbral_puppetry_hit_roll_modifier(context: HitRollModifierContext) -> int:
    if type(context) is not HitRollModifierContext:
        raise GameLifecycleError("Penumbral Puppetry hit modifier requires context.")
    if not _rules_unit_has_shadow_legion_god_keyword(
        state=context.state,
        player_id=_owner_player_id(context.state, context.target_unit_instance_id),
        unit_instance_id=context.target_unit_instance_id,
        god_keyword=TZEENTCH_KEYWORD,
    ):
        return 0
    if context.weapon_profile.range_profile.kind is RangeProfileKind.MELEE:
        return -1
    if context.source_phase is BattlePhase.SHOOTING:
        return -1
    return 0


def gloam_rot_wound_roll_modifier(context: WoundRollModifierContext) -> int:
    if type(context) is not WoundRollModifierContext:
        raise GameLifecycleError("Gloam Rot wound modifier requires context.")
    if not _rules_unit_has_shadow_legion_god_keyword(
        state=context.state,
        player_id=_owner_player_id(context.state, context.target_unit_instance_id),
        unit_instance_id=context.target_unit_instance_id,
        god_keyword=NURGLE_KEYWORD,
    ):
        return 0
    if context.strength > context.toughness:
        return -1
    return 0


def shadows_caress_snap_target_restriction(
    context: ShootingTargetRestrictionContext,
) -> TargetRestriction | None:
    if type(context) is not ShootingTargetRestrictionContext:
        raise GameLifecycleError("Shadow's Caress target restriction requires context.")
    if context.shooting_type is not ShootingType.SNAP:
        return None
    if not _rules_unit_has_shadow_legion_god_keyword(
        state=context.state,
        player_id=_owner_player_id(context.state, context.target_unit_instance_id),
        unit_instance_id=context.target_unit_instance_id,
        god_keyword=SLAANESH_KEYWORD,
    ):
        return None
    return TargetRestriction(
        hook_id=SLAANESH_TARGET_RESTRICTION_HOOK_ID,
        source_id=SOURCE_RULE_ID,
        violation_code="shadow_legion_shadows_caress_snap_target_forbidden",
        message="Shadow Legion Slaanesh units cannot be targeted by Snap Shooting attacks.",
        replay_payload=validate_json_value(
            {
                "battle_round": context.battle_round,
                "attacking_unit_instance_id": context.attacking_unit_instance_id,
                "target_unit_instance_id": context.target_unit_instance_id,
                "shooting_type": ShootingType.SNAP.value,
            }
        ),
    )


def shooting_lethal_hits_dark_pact_grant(
    context: ShootingUnitSelectedContext,
) -> ShootingUnitSelectedGrant | None:
    return _shooting_dark_pact_grant(
        context,
        hook_id=SHOOTING_LETHAL_HITS_HOOK_ID,
        pact=dark_pacts.DarkPactKind.LETHAL_HITS,
        label="Dark Pacts: Lethal Hits",
    )


def shooting_sustained_hits_dark_pact_grant(
    context: ShootingUnitSelectedContext,
) -> ShootingUnitSelectedGrant | None:
    return _shooting_dark_pact_grant(
        context,
        hook_id=SHOOTING_SUSTAINED_HITS_HOOK_ID,
        pact=dark_pacts.DarkPactKind.SUSTAINED_HITS_1,
        label="Dark Pacts: Sustained Hits 1",
    )


def fight_lethal_hits_dark_pact_grant(
    context: FightUnitSelectedContext,
) -> FightUnitSelectedGrant | None:
    return _fight_dark_pact_grant(
        context,
        hook_id=FIGHT_LETHAL_HITS_HOOK_ID,
        pact=dark_pacts.DarkPactKind.LETHAL_HITS,
        label="Dark Pacts: Lethal Hits",
    )


def fight_sustained_hits_dark_pact_grant(
    context: FightUnitSelectedContext,
) -> FightUnitSelectedGrant | None:
    return _fight_dark_pact_grant(
        context,
        hook_id=FIGHT_SUSTAINED_HITS_HOOK_ID,
        pact=dark_pacts.DarkPactKind.SUSTAINED_HITS_1,
        label="Dark Pacts: Sustained Hits 1",
    )


def _shooting_dark_pact_grant(
    context: ShootingUnitSelectedContext,
    *,
    hook_id: str,
    pact: dark_pacts.DarkPactKind,
    label: str,
) -> ShootingUnitSelectedGrant | None:
    if type(context) is not ShootingUnitSelectedContext:
        raise GameLifecycleError("Shadow Legion shooting Dark Pacts requires context.")
    if not _dark_pacts_available(
        state=context.state,
        player_id=context.player_id,
        unit_instance_id=context.unit_instance_id,
        phase=BattlePhase.SHOOTING,
    ):
        return None
    target_unit_ids = dark_pacts.dark_pact_target_unit_ids(
        context.state,
        unit_instance_id=context.unit_instance_id,
    )
    return ShootingUnitSelectedGrant(
        hook_id=hook_id,
        source_id=SOURCE_RULE_ID,
        label=label,
        replay_payload={
            "effect_kind": dark_pacts.DARK_PACT_EFFECT_KIND,
            "selected_dark_pact": pact.value,
            "trigger": "selected_to_shoot",
            "unit_instance_id": context.unit_instance_id,
            "selection_request_id": context.request_id,
            "selection_result_id": context.result_id,
            "source_rule_id": SOURCE_RULE_ID,
        },
        unit_effect_payload=dark_pacts.dark_pact_effect_payload(
            unit_instance_id=context.unit_instance_id,
            target_unit_instance_ids=target_unit_ids,
            trigger="selected_to_shoot",
            phase=BattlePhase.SHOOTING,
            selected_dark_pact=pact,
            source_context={
                "source_rule_id": SOURCE_RULE_ID,
                "selection_request_id": context.request_id,
                "selection_result_id": context.result_id,
            },
            leadership_test_auto_pass=_rules_unit_is_belakor(
                state=context.state,
                unit_instance_id=context.unit_instance_id,
            ),
        ),
        unit_effect_expiration="end_phase",
    )


def _fight_dark_pact_grant(
    context: FightUnitSelectedContext,
    *,
    hook_id: str,
    pact: dark_pacts.DarkPactKind,
    label: str,
) -> FightUnitSelectedGrant | None:
    if type(context) is not FightUnitSelectedContext:
        raise GameLifecycleError("Shadow Legion Fight Dark Pacts requires context.")
    if not _dark_pacts_available(
        state=context.state,
        player_id=context.player_id,
        unit_instance_id=context.unit_instance_id,
        phase=BattlePhase.FIGHT,
    ):
        return None
    target_unit_ids = dark_pacts.dark_pact_target_unit_ids(
        context.state,
        unit_instance_id=context.unit_instance_id,
    )
    return FightUnitSelectedGrant(
        hook_id=hook_id,
        source_id=SOURCE_RULE_ID,
        label=label,
        replay_payload={
            "effect_kind": dark_pacts.DARK_PACT_EFFECT_KIND,
            "selected_dark_pact": pact.value,
            "trigger": "selected_to_fight",
            "unit_instance_id": context.unit_instance_id,
            "activation_request_id": context.request_id,
            "activation_result_id": context.result_id,
            "fight_type": context.fight_type,
            "ordering_band": context.ordering_band,
            "source_rule_id": SOURCE_RULE_ID,
        },
        unit_effect_payload=dark_pacts.dark_pact_effect_payload(
            unit_instance_id=context.unit_instance_id,
            target_unit_instance_ids=target_unit_ids,
            trigger="selected_to_fight",
            phase=BattlePhase.FIGHT,
            selected_dark_pact=pact,
            source_context={
                "source_rule_id": SOURCE_RULE_ID,
                "activation_request_id": context.request_id,
                "activation_result_id": context.result_id,
                "fight_type": context.fight_type,
                "ordering_band": context.ordering_band,
            },
            leadership_test_auto_pass=_rules_unit_is_belakor(
                state=context.state,
                unit_instance_id=context.unit_instance_id,
            ),
        ),
        unit_effect_expiration="end_phase",
    )


def _dark_pacts_available(
    *,
    state: object,
    player_id: str,
    unit_instance_id: str,
    phase: BattlePhase,
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Shadow Legion Dark Pacts requires GameState.")
    if type(phase) is not BattlePhase:
        raise GameLifecycleError("Shadow Legion Dark Pacts requires a BattlePhase.")
    if not _army_uses_shadow_legion(state=state, player_id=player_id):
        return False
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    if rules_unit.owner_player_id != player_id:
        raise GameLifecycleError("Shadow Legion Dark Pacts unit owner drift.")
    if not (
        _rules_unit_has_keyword(rules_unit, SHADOW_LEGION_KEYWORD)
        and _rules_unit_has_keyword(rules_unit, UNDIVIDED_KEYWORD)
    ):
        return False
    return (
        dark_pacts.active_dark_pact_for_unit(
            state,
            unit_instance_id=unit_instance_id,
            phase=phase,
        )
        is None
    )


def _rules_unit_has_shadow_legion_god_keyword(
    *,
    state: object,
    player_id: str,
    unit_instance_id: str,
    god_keyword: str,
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Shadow Legion keyword lookup requires GameState.")
    if not _army_uses_shadow_legion(state=state, player_id=player_id):
        return False
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    if rules_unit.owner_player_id != player_id:
        raise GameLifecycleError("Shadow Legion keyword lookup unit owner drift.")
    return _rules_unit_has_keyword(
        rules_unit,
        SHADOW_LEGION_KEYWORD,
    ) and _rules_unit_has_keyword(rules_unit, god_keyword)


def _army_uses_shadow_legion(*, state: object, player_id: str) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Shadow Legion army lookup requires GameState.")
    army = state.army_definition_for_player(_validate_identifier("player_id", player_id))
    if army is None:
        raise GameLifecycleError("Shadow Legion player army is missing.")
    return (
        army.detachment_selection.faction_id == CHAOS_DAEMONS_FACTION_ID
        and DETACHMENT_ID in army.detachment_selection.detachment_ids
    )


def _owner_player_id(state: object, unit_instance_id: str) -> str:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Shadow Legion owner lookup requires GameState.")
    return rules_unit_view_by_id(
        state=state,
        unit_instance_id=_validate_identifier("unit_instance_id", unit_instance_id),
    ).owner_player_id


def _rules_unit_has_keyword(rules_unit: RulesUnitView, keyword: str) -> bool:
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Shadow Legion keyword lookup requires RulesUnitView.")
    requested_keyword = _canonical_keyword(keyword)
    return requested_keyword in {_canonical_keyword(stored) for stored in rules_unit.keywords}


def _rules_unit_is_belakor(*, state: object, unit_instance_id: str) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Shadow Legion Be'lakor lookup requires GameState.")
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    return any(_unit_is_belakor(component.unit) for component in rules_unit.components)


def _unit_is_belakor(unit: UnitInstance) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Shadow Legion Be'lakor lookup requires UnitInstance.")
    return _canonical_name(unit.name) == "BELAKOR"


def _shadow_legion_replay_payload(battle_round: int) -> JsonValue:
    if type(battle_round) is not int or battle_round < 1:
        raise GameLifecycleError("Shadow Legion battle_round must be positive.")
    return validate_json_value(
        {
            "source_rule_id": SOURCE_RULE_ID,
            "battle_round": battle_round,
        }
    )


def _canonical_keyword(value: str) -> str:
    return _validate_identifier("keyword", value).upper().replace("_", " ").replace("-", " ")


def _canonical_name(value: str) -> str:
    return "".join(
        character
        for character in _validate_identifier("name", value).upper()
        if character.isalnum()
    )


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Shadow Legion {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Shadow Legion {field_name} must not be empty.")
    return stripped
