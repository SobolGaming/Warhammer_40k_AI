from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from warhammer40k_core.core.dice import (
    RerollComponentSelectionPolicy,
    RerollPermission,
)
from warhammer40k_core.core.faction_aliases import (
    CHAOS_SPACE_MARINES_FACTION_ID,
    faction_reference_matches,
)
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_ability_sources import grant_weapon_ability
from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    RangeProfileKind,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.fight_unit_selected_hooks import (
    FightUnitSelectedContext,
    FightUnitSelectedGrant,
    FightUnitSelectedGrantBinding,
    FightUnitSelectedTimedEffect,
)
from warhammer40k_core.engine.mortal_wound_feel_no_pain_hooks import (
    MortalWoundFeelNoPainContinuationHookBinding,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
)
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_view_by_id,
    rules_unit_view_from_armies,
)
from warhammer40k_core.engine.runtime_modifiers import (
    AttackRerollPermissionBinding,
    AttackRerollPermissionContext,
    WeaponProfileModifierBinding,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.shooting_unit_selected_hooks import (
    ShootingUnitSelectedContext,
    ShootingUnitSelectedGrant,
    ShootingUnitSelectedGrantBinding,
)
from warhammer40k_core.engine.source_backed_rerolls import (
    SourceBackedRerollPermissionContext,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_grant_preparation import (
    UnitGrantPreparation,
    apply_preparation_mortal_wound_decision,
)

if TYPE_CHECKING:
    pass


CONTRIBUTION_ID = "warhammer_40000_11th:chaos_space_marines:army_rule:dark_pacts"
SOURCE_RULE_ID = "phase17f:phase17e:chaos-space-marines:army-rule"
DARK_PACTS_SOURCE_ABILITY_ID = "000008359"
HOOK_ID = "warhammer_40000_11th:chaos_space_marines:army_rule:dark_pacts"
DEFILER_DAEMONFORGE_DATASHEET_ID = "000000969"
DEFILER_DAEMONFORGE_ABILITY_ID = "000000969:daemonforge"
DARK_PACT_EFFECT_KIND = "chaos_space_marines_dark_pact"
DARK_PACT_LEADERSHIP_ROLL_TYPE = "chaos_space_marines.dark_pact_leadership_test"
DARK_PACT_MORTAL_WOUNDS_ROLL_TYPE = "chaos_space_marines.dark_pact_mortal_wounds"
DARK_PACT_MORTAL_WOUNDS_SOURCE_KIND = "chaos_space_marines_dark_pacts"
SHADOW_LEGION_SOURCE_RULE_ID = "phase17f:phase17e:chaos-daemons:shadow-legion:rule"
SHADOW_LEGION_DARK_PACT_MORTAL_WOUNDS_SOURCE_KIND = "chaos_daemons_shadow_legion_dark_pacts"
DARK_PACT_SOURCE_RULE_IDS = (SOURCE_RULE_ID, SHADOW_LEGION_SOURCE_RULE_ID)
DARK_PACT_MORTAL_WOUNDS_SOURCE_KINDS = (
    DARK_PACT_MORTAL_WOUNDS_SOURCE_KIND,
    SHADOW_LEGION_DARK_PACT_MORTAL_WOUNDS_SOURCE_KIND,
)

SHOOTING_LETHAL_HITS_HOOK_ID = f"{HOOK_ID}:shooting:lethal_hits"
SHOOTING_SUSTAINED_HITS_HOOK_ID = f"{HOOK_ID}:shooting:sustained_hits_1"
FIGHT_LETHAL_HITS_HOOK_ID = f"{HOOK_ID}:fight:lethal_hits"
FIGHT_SUSTAINED_HITS_HOOK_ID = f"{HOOK_ID}:fight:sustained_hits_1"
MORTAL_WOUND_FEEL_NO_PAIN_HOOK_ID = f"{HOOK_ID}:mortal_wound_feel_no_pain"
WEAPON_PROFILE_MODIFIER_ID = f"{HOOK_ID}:weapon_profile_modifier"
DEFILER_DAEMONFORGE_WOUND_REROLL_MODIFIER_ID = f"{HOOK_ID}:defiler-daemonforge:wound-reroll"


class DarkPactKind(StrEnum):
    LETHAL_HITS = "lethal_hits"
    SUSTAINED_HITS_1 = "sustained_hits_1"


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
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
        mortal_wound_feel_no_pain_hook_bindings=(
            MortalWoundFeelNoPainContinuationHookBinding(
                hook_id=MORTAL_WOUND_FEEL_NO_PAIN_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                source_kind=DARK_PACT_MORTAL_WOUNDS_SOURCE_KIND,
                handler=apply_preparation_mortal_wound_decision,
            ),
        ),
        weapon_profile_modifier_bindings=(
            WeaponProfileModifierBinding(
                modifier_id=WEAPON_PROFILE_MODIFIER_ID,
                source_id=SOURCE_RULE_ID,
                handler=dark_pact_weapon_profile_modifier,
            ),
        ),
        attack_reroll_permission_bindings=(
            AttackRerollPermissionBinding(
                modifier_id=DEFILER_DAEMONFORGE_WOUND_REROLL_MODIFIER_ID,
                source_id=DEFILER_DAEMONFORGE_ABILITY_ID,
                handler=defiler_daemonforge_wound_reroll_permission,
            ),
        ),
    )


def shooting_lethal_hits_dark_pact_grant(
    context: ShootingUnitSelectedContext,
) -> ShootingUnitSelectedGrant | None:
    return _shooting_dark_pact_grant(
        context,
        hook_id=SHOOTING_LETHAL_HITS_HOOK_ID,
        pact=DarkPactKind.LETHAL_HITS,
        label="Dark Pacts: Lethal Hits",
    )


def shooting_sustained_hits_dark_pact_grant(
    context: ShootingUnitSelectedContext,
) -> ShootingUnitSelectedGrant | None:
    return _shooting_dark_pact_grant(
        context,
        hook_id=SHOOTING_SUSTAINED_HITS_HOOK_ID,
        pact=DarkPactKind.SUSTAINED_HITS_1,
        label="Dark Pacts: Sustained Hits 1",
    )


def fight_lethal_hits_dark_pact_grant(
    context: FightUnitSelectedContext,
) -> FightUnitSelectedGrant | None:
    return _fight_dark_pact_grant(
        context,
        hook_id=FIGHT_LETHAL_HITS_HOOK_ID,
        pact=DarkPactKind.LETHAL_HITS,
        label="Dark Pacts: Lethal Hits",
    )


def fight_sustained_hits_dark_pact_grant(
    context: FightUnitSelectedContext,
) -> FightUnitSelectedGrant | None:
    return _fight_dark_pact_grant(
        context,
        hook_id=FIGHT_SUSTAINED_HITS_HOOK_ID,
        pact=DarkPactKind.SUSTAINED_HITS_1,
        label="Dark Pacts: Sustained Hits 1",
    )


def _shooting_dark_pact_grant(
    context: ShootingUnitSelectedContext,
    *,
    hook_id: str,
    pact: DarkPactKind,
    label: str,
) -> ShootingUnitSelectedGrant | None:
    if type(context) is not ShootingUnitSelectedContext:
        raise GameLifecycleError("Dark Pacts shooting grant requires selected unit context.")
    if not _dark_pacts_available(
        state=context.state,
        player_id=context.player_id,
        unit_instance_id=context.unit_instance_id,
        phase=BattlePhase.SHOOTING,
    ):
        return None
    target_unit_ids = dark_pact_target_unit_ids(
        context.state,
        unit_instance_id=context.unit_instance_id,
    )
    return ShootingUnitSelectedGrant(
        hook_id=hook_id,
        source_id=SOURCE_RULE_ID,
        label=label,
        preparation=dark_pact_preparation(source_rule_id=SOURCE_RULE_ID),
        replay_payload={
            "effect_kind": DARK_PACT_EFFECT_KIND,
            "selected_dark_pact": pact.value,
            "trigger": "selected_to_shoot",
            "unit_instance_id": context.unit_instance_id,
            "selection_request_id": context.request_id,
            "selection_result_id": context.result_id,
        },
        unit_effect_payload=dark_pact_effect_payload(
            unit_instance_id=context.unit_instance_id,
            target_unit_instance_ids=target_unit_ids,
            trigger="selected_to_shoot",
            phase=BattlePhase.SHOOTING,
            selected_dark_pact=pact,
            source_context={
                "selection_request_id": context.request_id,
                "selection_result_id": context.result_id,
            },
        ),
        unit_effect_expiration="end_enclosing_phase",
    )


def _fight_dark_pact_grant(
    context: FightUnitSelectedContext,
    *,
    hook_id: str,
    pact: DarkPactKind,
    label: str,
) -> FightUnitSelectedGrant | None:
    if type(context) is not FightUnitSelectedContext:
        raise GameLifecycleError("Dark Pacts fight grant requires selected unit context.")
    if not _dark_pacts_available(
        state=context.state,
        player_id=context.player_id,
        unit_instance_id=context.unit_instance_id,
        phase=BattlePhase.FIGHT,
    ):
        return None
    return FightUnitSelectedGrant(
        hook_id=hook_id,
        source_id=SOURCE_RULE_ID,
        label=label,
        preparation=dark_pact_preparation(source_rule_id=SOURCE_RULE_ID),
        replay_payload={
            "effect_kind": DARK_PACT_EFFECT_KIND,
            "selected_dark_pact": pact.value,
            "trigger": "selected_to_fight",
            "unit_instance_id": context.unit_instance_id,
            "activation_request_id": context.request_id,
            "activation_result_id": context.result_id,
            "fight_type": context.fight_type,
            "ordering_band": context.ordering_band,
        },
        timed_effects=(
            FightUnitSelectedTimedEffect(
                effect_payload=dark_pact_effect_payload(
                    unit_instance_id=context.unit_instance_id,
                    target_unit_instance_ids=(context.unit_instance_id,),
                    trigger="selected_to_fight",
                    phase=BattlePhase.FIGHT,
                    selected_dark_pact=pact,
                    source_context={
                        "activation_request_id": context.request_id,
                        "activation_result_id": context.result_id,
                        "fight_type": context.fight_type,
                        "ordering_band": context.ordering_band,
                    },
                ),
                expiration="end_phase",
            ),
        ),
    )


def dark_pact_preparation(*, source_rule_id: str, auto_pass: bool = False) -> UnitGrantPreparation:
    source_kinds = {
        SOURCE_RULE_ID: DARK_PACT_MORTAL_WOUNDS_SOURCE_KIND,
        SHADOW_LEGION_SOURCE_RULE_ID: SHADOW_LEGION_DARK_PACT_MORTAL_WOUNDS_SOURCE_KIND,
    }
    if source_rule_id not in source_kinds:
        raise GameLifecycleError("Unknown Dark Pacts source rule.")
    return UnitGrantPreparation(
        source_rule_id=source_rule_id,
        label="Dark Pact",
        leadership_roll_type=DARK_PACT_LEADERSHIP_ROLL_TYPE,
        mortal_wounds_roll_type=DARK_PACT_MORTAL_WOUNDS_ROLL_TYPE,
        mortal_wound_source_kind=source_kinds[source_rule_id],
        resolved_event_type="chaos_space_marines_dark_pact_resolved",
        pending_event_type="chaos_space_marines_dark_pact_mortal_wounds_pending",
        auto_pass=auto_pass,
    )


def dark_pact_effect_payload(
    *,
    unit_instance_id: str,
    target_unit_instance_ids: tuple[str, ...],
    trigger: str,
    phase: BattlePhase,
    selected_dark_pact: DarkPactKind,
    source_context: JsonValue,
    leadership_test_auto_pass: bool = False,
) -> JsonValue:
    if type(leadership_test_auto_pass) is not bool:
        raise GameLifecycleError("Dark Pacts leadership auto-pass flag must be a bool.")
    return validate_json_value(
        {
            "effect_kind": DARK_PACT_EFFECT_KIND,
            "unit_instance_id": _validate_identifier("unit_instance_id", unit_instance_id),
            "target_unit_instance_ids": list(
                _validate_identifier_tuple(
                    "target_unit_instance_ids",
                    target_unit_instance_ids,
                )
            ),
            "trigger": _validate_identifier("trigger", trigger),
            "phase": _battle_phase_from_token(phase).value,
            "selected_dark_pact": dark_pact_kind_from_token(selected_dark_pact).value,
            "source_context": validate_json_value(source_context),
            "leadership_test_auto_pass": leadership_test_auto_pass,
        }
    )


def dark_pact_weapon_profile_modifier(
    context: WeaponProfileModifierContext,
) -> WeaponProfile:
    if type(context) is not WeaponProfileModifierContext:
        raise GameLifecycleError("Dark Pacts weapon profile modifier requires context.")
    if context.source_phase not in (BattlePhase.SHOOTING, BattlePhase.FIGHT):
        return context.weapon_profile
    if context.source_phase is BattlePhase.SHOOTING:
        if context.weapon_profile.range_profile.kind is RangeProfileKind.MELEE:
            return context.weapon_profile
    elif context.weapon_profile.range_profile.kind is not RangeProfileKind.MELEE:
        return context.weapon_profile
    effect = active_dark_pact_effect_for_unit(
        context.state,
        unit_instance_id=context.attacking_unit_instance_id,
        phase=context.source_phase,
    )
    if effect is None:
        return context.weapon_profile
    payload = dark_pact_payload(effect.effect_payload)
    pact = dark_pact_kind_from_token(payload["selected_dark_pact"])
    if pact is DarkPactKind.LETHAL_HITS:
        return _profile_with_keyword_and_ability(
            context.weapon_profile,
            keyword=WeaponKeyword.LETHAL_HITS,
            ability=AbilityDescriptor.lethal_hits(),
            source_rule_id=effect.source_rule_id,
        )
    if pact is DarkPactKind.SUSTAINED_HITS_1:
        return _profile_with_keyword_and_ability(
            context.weapon_profile,
            keyword=WeaponKeyword.SUSTAINED_HITS,
            ability=AbilityDescriptor.sustained_hits(1),
            source_rule_id=effect.source_rule_id,
        )
    raise GameLifecycleError("Dark Pacts selected pact is unsupported.")


def defiler_daemonforge_wound_reroll_permission(
    context: AttackRerollPermissionContext,
) -> SourceBackedRerollPermissionContext | None:
    if type(context) is not AttackRerollPermissionContext:
        raise GameLifecycleError("Defiler Daemonforge wound reroll requires context.")
    if context.source_phase not in (BattlePhase.SHOOTING, BattlePhase.FIGHT):
        return None
    if (
        context.roll_type != "attack_sequence.wound"
        or context.timing_window != "attack_sequence.wound"
        or context.attacker_model_instance_id is None
    ):
        return None
    rules_unit = rules_unit_view_by_id(
        state=context.state,
        unit_instance_id=context.attacking_unit_instance_id,
    )
    if rules_unit.owner_player_id != context.player_id:
        raise GameLifecycleError("Defiler Daemonforge reroll owner drift.")
    attacking_component = rules_unit.component_unit_for_model(context.attacker_model_instance_id)
    if attacking_component.datasheet_id != DEFILER_DAEMONFORGE_DATASHEET_ID or all(
        ability.ability_id != DEFILER_DAEMONFORGE_ABILITY_ID
        for ability in attacking_component.datasheet_abilities
    ):
        return None
    if (
        active_dark_pact_for_unit(
            context.state,
            unit_instance_id=context.attacking_unit_instance_id,
            phase=context.source_phase,
        )
        is None
    ):
        return None
    return SourceBackedRerollPermissionContext(
        permission=RerollPermission(
            source_id=DEFILER_DAEMONFORGE_ABILITY_ID,
            timing_window=context.timing_window,
            owning_player_id=context.player_id,
            eligible_roll_type=context.roll_type,
            component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
        ),
        source_payload={
            "conditional_wound_reroll": {"reroll_unmodified_values": [1]},
            "dark_pacts_source_ability_id": DARK_PACTS_SOURCE_ABILITY_ID,
            "datasheet_id": DEFILER_DAEMONFORGE_DATASHEET_ID,
            "source_ability_id": DEFILER_DAEMONFORGE_ABILITY_ID,
        },
    )


def active_dark_pact_for_unit(
    state: object,
    *,
    unit_instance_id: str,
    phase: BattlePhase,
) -> DarkPactKind | None:
    effect = active_dark_pact_effect_for_unit(
        state,
        unit_instance_id=unit_instance_id,
        phase=phase,
    )
    if effect is None:
        return None
    payload = dark_pact_payload(effect.effect_payload)
    return dark_pact_kind_from_token(payload["selected_dark_pact"])


def dark_pact_target_unit_ids(state: object, *, unit_instance_id: str) -> tuple[str, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Dark Pacts target lookup requires GameState.")
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=_validate_identifier("unit_instance_id", unit_instance_id),
    )
    return tuple(
        dict.fromkeys((rules_unit.unit_instance_id, *rules_unit.component_unit_instance_ids))
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
        raise GameLifecycleError("Dark Pacts eligibility requires GameState.")
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    army = state.army_definition_for_player(requested_player_id)
    if army is None:
        raise GameLifecycleError("Dark Pacts player army is missing.")
    if army.detachment_selection.faction_id != CHAOS_SPACE_MARINES_FACTION_ID:
        return False
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=requested_unit_id)
    if rules_unit.owner_player_id != requested_player_id:
        raise GameLifecycleError("Dark Pacts unit is not owned by the acting player.")
    if not _rules_unit_has_dark_pacts(rules_unit):
        return False
    return (
        active_dark_pact_effect_for_unit(
            state,
            unit_instance_id=requested_unit_id,
            phase=phase,
        )
        is None
    )


def active_dark_pact_effect_for_unit(
    state: object,
    *,
    unit_instance_id: str,
    phase: BattlePhase,
) -> PersistingEffect | None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Dark Pacts effect lookup requires GameState.")
    requested_phase = _battle_phase_from_token(phase)
    effects: list[PersistingEffect] = []
    # A weapon can belong to either component; the pact belongs to the rules unit.
    target_unit_id = rules_unit_view_from_armies(
        armies=tuple(state.army_definitions),
        unit_instance_id=_validate_identifier("unit_instance_id", unit_instance_id),
    ).unit_instance_id
    for effect in state.persisting_effects_for_unit(target_unit_id):
        if effect.source_rule_id not in DARK_PACT_SOURCE_RULE_IDS:
            continue
        payload = dark_pact_payload(effect.effect_payload)
        if payload["phase"] != requested_phase.value:
            continue
        effects.append(effect)
    if len(effects) > 1:
        raise GameLifecycleError("Dark Pacts found multiple active effects for a unit.")
    return None if not effects else effects[0]


def _rules_unit_has_dark_pacts(rules_unit: RulesUnitView) -> bool:
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Dark Pacts requires a RulesUnitView.")
    return any(_unit_has_dark_pacts(component.unit) for component in rules_unit.components)


def _unit_has_dark_pacts(unit: UnitInstance) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Dark Pacts requires a UnitInstance.")
    if any(
        faction_reference_matches(
            faction_id=CHAOS_SPACE_MARINES_FACTION_ID,
            reference=keyword,
        )
        for keyword in unit.faction_keywords
    ):
        return True
    return any(
        ability.source_id in DARK_PACT_SOURCE_RULE_IDS for ability in unit.datasheet_abilities
    )


def _profile_with_keyword_and_ability(
    profile: WeaponProfile,
    *,
    keyword: WeaponKeyword,
    ability: AbilityDescriptor,
    source_rule_id: str,
) -> WeaponProfile:
    if type(profile) is not WeaponProfile:
        raise GameLifecycleError("Dark Pacts weapon profile modifier requires WeaponProfile.")
    requested_source_rule_id = _validate_identifier("source_rule_id", source_rule_id)
    return grant_weapon_ability(
        profile,
        keyword=keyword,
        ability=ability,
        source_id=requested_source_rule_id,
        source_instance_id=requested_source_rule_id,
    )


def dark_pact_payload(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Dark Pacts effect payload must be an object.")
    if payload.get("effect_kind") != DARK_PACT_EFFECT_KIND:
        raise GameLifecycleError("Dark Pacts effect kind drift.")
    if type(payload.get("unit_instance_id")) is not str:
        raise GameLifecycleError("Dark Pacts effect payload is missing unit_instance_id.")
    if type(payload.get("phase")) is not str:
        raise GameLifecycleError("Dark Pacts effect payload is missing phase.")
    if type(payload.get("selected_dark_pact")) is not str:
        raise GameLifecycleError("Dark Pacts effect payload is missing selected_dark_pact.")
    dark_pact_kind_from_token(payload["selected_dark_pact"])
    if type(payload.get("leadership_test_auto_pass")) is not bool:
        raise GameLifecycleError("Dark Pacts effect payload is missing leadership auto-pass.")
    return payload


def dark_pact_kind_from_token(token: object) -> DarkPactKind:
    if type(token) is DarkPactKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Dark Pacts kind must be a string.")
    try:
        return DarkPactKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported Dark Pacts kind: {token}.") from exc


def _battle_phase_from_token(token: object) -> BattlePhase:
    if type(token) is BattlePhase:
        return token
    if type(token) is BattlePhaseKind:
        return BattlePhase(token.value)
    if type(token) is not str:
        raise GameLifecycleError("Dark Pacts phase must be a BattlePhase.")
    try:
        return BattlePhase(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported Dark Pacts phase: {token}.") from exc


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_identifier_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"Dark Pacts {field_name} must be a tuple.")
    seen: set[str] = set()
    validated: list[str] = []
    for value in values:
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"Dark Pacts {field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    return tuple(validated)
