from __future__ import annotations

from dataclasses import replace
from enum import StrEnum
from typing import cast

from warhammer40k_core.core.faction_aliases import (
    ADEPTUS_CUSTODES_FACTION_ID,
    faction_reference_matches,
)
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
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
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import (
    WeaponProfileModifierBinding,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.unit_factory import UnitInstance

CONTRIBUTION_ID = "warhammer_40000_11th:adeptus_custodes:army_rule:scaffold"
SOURCE_RULE_ID = "phase17f:phase17e:adeptus-custodes:army-rule"
HOOK_ID = "warhammer_40000_11th:adeptus_custodes:army_rule:martial_katah"
DACATARAI_HOOK_ID = f"{HOOK_ID}:dacatarai"
RENDAX_HOOK_ID = f"{HOOK_ID}:rendax"
WEAPON_PROFILE_MODIFIER_ID = f"{HOOK_ID}:weapon-profile"

MARTIAL_KATAH_EFFECT_KIND = "adeptus_custodes_martial_katah"
MARTIAL_KATAH_ABILITY_NAME = "Martial Ka'tah"


class MartialKatahStance(StrEnum):
    DACATARAI = "dacatarai"
    RENDAX = "rendax"


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        fight_unit_selected_grant_hook_bindings=(
            FightUnitSelectedGrantBinding(
                hook_id=DACATARAI_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=dacatarai_martial_katah_grant,
            ),
            FightUnitSelectedGrantBinding(
                hook_id=RENDAX_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=rendax_martial_katah_grant,
            ),
        ),
        weapon_profile_modifier_bindings=(
            WeaponProfileModifierBinding(
                modifier_id=WEAPON_PROFILE_MODIFIER_ID,
                source_id=SOURCE_RULE_ID,
                handler=martial_katah_weapon_profile_modifier,
            ),
        ),
    )


def dacatarai_martial_katah_grant(
    context: FightUnitSelectedContext,
) -> FightUnitSelectedGrant | None:
    return _martial_katah_grant(
        context,
        hook_id=DACATARAI_HOOK_ID,
        stance=MartialKatahStance.DACATARAI,
        label="Martial Ka'tah: Dacatarai Stance",
    )


def rendax_martial_katah_grant(
    context: FightUnitSelectedContext,
) -> FightUnitSelectedGrant | None:
    return _martial_katah_grant(
        context,
        hook_id=RENDAX_HOOK_ID,
        stance=MartialKatahStance.RENDAX,
        label="Martial Ka'tah: Rendax Stance",
    )


def martial_katah_effect_payload(
    *,
    unit_instance_id: str,
    target_unit_instance_ids: tuple[str, ...],
    trigger: str,
    phase: BattlePhase,
    selected_martial_katah: MartialKatahStance,
    source_context: JsonValue,
) -> JsonValue:
    return validate_json_value(
        {
            "effect_kind": MARTIAL_KATAH_EFFECT_KIND,
            "unit_instance_id": _validate_identifier("unit_instance_id", unit_instance_id),
            "target_unit_instance_ids": list(
                _validate_identifier_tuple(
                    "target_unit_instance_ids",
                    target_unit_instance_ids,
                )
            ),
            "trigger": _validate_identifier("trigger", trigger),
            "phase": _battle_phase_from_token(phase).value,
            "selected_martial_katah": _stance_from_token(selected_martial_katah).value,
            "source_context": validate_json_value(source_context),
        }
    )


def martial_katah_target_unit_ids(state: object, *, unit_instance_id: str) -> tuple[str, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Martial Ka'tah target lookup requires GameState.")
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=_validate_identifier("unit_instance_id", unit_instance_id),
    )
    return tuple(
        dict.fromkeys((rules_unit.unit_instance_id, *rules_unit.component_unit_instance_ids))
    )


def active_martial_katah_for_unit(
    state: object,
    *,
    unit_instance_id: str,
) -> MartialKatahStance | None:
    effect = _active_martial_katah_effect_for_unit(state, unit_instance_id=unit_instance_id)
    if effect is None:
        return None
    payload = _martial_katah_payload(effect.effect_payload)
    return _stance_from_token(payload["selected_martial_katah"])


def martial_katah_weapon_profile_modifier(
    context: WeaponProfileModifierContext,
) -> WeaponProfile:
    if type(context) is not WeaponProfileModifierContext:
        raise GameLifecycleError("Martial Ka'tah weapon profile modifier requires context.")
    if context.source_phase is not BattlePhase.FIGHT:
        return context.weapon_profile
    if context.weapon_profile.range_profile.kind is not RangeProfileKind.MELEE:
        return context.weapon_profile
    effect = _active_martial_katah_effect_for_unit(
        context.state,
        unit_instance_id=context.attacking_unit_instance_id,
    )
    if effect is None:
        return context.weapon_profile
    payload = _martial_katah_payload(effect.effect_payload)
    stance = _stance_from_token(payload["selected_martial_katah"])
    if stance is MartialKatahStance.DACATARAI:
        return _profile_with_keyword_and_ability(
            context.weapon_profile,
            keyword=WeaponKeyword.SUSTAINED_HITS,
            ability=AbilityDescriptor.sustained_hits(1),
            source_rule_id=effect.source_rule_id,
        )
    if stance is MartialKatahStance.RENDAX:
        return _profile_with_keyword_and_ability(
            context.weapon_profile,
            keyword=WeaponKeyword.LETHAL_HITS,
            ability=AbilityDescriptor.lethal_hits(),
            source_rule_id=effect.source_rule_id,
        )
    raise GameLifecycleError("Martial Ka'tah selected stance is unsupported.")


def _martial_katah_grant(
    context: FightUnitSelectedContext,
    *,
    hook_id: str,
    stance: MartialKatahStance,
    label: str,
) -> FightUnitSelectedGrant | None:
    if type(context) is not FightUnitSelectedContext:
        raise GameLifecycleError("Martial Ka'tah fight grant requires selected unit context.")
    if not _martial_katah_available(
        state=context.state,
        player_id=context.player_id,
        unit_instance_id=context.unit_instance_id,
    ):
        return None
    target_unit_ids = martial_katah_target_unit_ids(
        context.state,
        unit_instance_id=context.unit_instance_id,
    )
    return FightUnitSelectedGrant(
        hook_id=hook_id,
        source_id=SOURCE_RULE_ID,
        label=label,
        replay_payload={
            "effect_kind": MARTIAL_KATAH_EFFECT_KIND,
            "selected_martial_katah": _stance_from_token(stance).value,
            "trigger": "selected_to_fight",
            "unit_instance_id": context.unit_instance_id,
            "activation_request_id": context.request_id,
            "activation_result_id": context.result_id,
            "fight_type": context.fight_type,
            "ordering_band": context.ordering_band,
        },
        unit_effect_payload=martial_katah_effect_payload(
            unit_instance_id=context.unit_instance_id,
            target_unit_instance_ids=target_unit_ids,
            trigger="selected_to_fight",
            phase=BattlePhase.FIGHT,
            selected_martial_katah=stance,
            source_context={
                "activation_request_id": context.request_id,
                "activation_result_id": context.result_id,
                "fight_type": context.fight_type,
                "ordering_band": context.ordering_band,
            },
        ),
        unit_effect_expiration="end_phase",
    )


def _martial_katah_available(
    *,
    state: object,
    player_id: str,
    unit_instance_id: str,
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Martial Ka'tah eligibility requires GameState.")
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    army = state.army_definition_for_player(requested_player_id)
    if army is None:
        raise GameLifecycleError("Martial Ka'tah player army is missing.")
    if army.detachment_selection.faction_id != ADEPTUS_CUSTODES_FACTION_ID:
        return False
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=requested_unit_id)
    if rules_unit.owner_player_id != requested_player_id:
        raise GameLifecycleError("Martial Ka'tah unit is not owned by the acting player.")
    if not _rules_unit_has_martial_katah(rules_unit):
        return False
    return _active_martial_katah_effect_for_unit(state, unit_instance_id=requested_unit_id) is None


def _active_martial_katah_effect_for_unit(
    state: object,
    *,
    unit_instance_id: str,
) -> PersistingEffect | None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Martial Ka'tah effect lookup requires GameState.")
    effects: list[PersistingEffect] = []
    for effect in state.persisting_effects_for_unit(
        _validate_identifier("unit_instance_id", unit_instance_id)
    ):
        if effect.source_rule_id != SOURCE_RULE_ID:
            continue
        payload = _martial_katah_payload(effect.effect_payload)
        if payload["phase"] != BattlePhase.FIGHT.value:
            continue
        effects.append(effect)
    if len(effects) > 1:
        raise GameLifecycleError("Martial Ka'tah found multiple active effects for a unit.")
    return None if not effects else effects[0]


def _rules_unit_has_martial_katah(rules_unit: RulesUnitView) -> bool:
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Martial Ka'tah requires a RulesUnitView.")
    return any(_unit_has_martial_katah(component.unit) for component in rules_unit.components)


def _unit_has_martial_katah(unit: UnitInstance) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Martial Ka'tah requires a UnitInstance.")
    if any(
        faction_reference_matches(
            faction_id=ADEPTUS_CUSTODES_FACTION_ID,
            reference=keyword,
        )
        for keyword in unit.faction_keywords
    ):
        return True
    return any(
        _canonical_rule_token(ability.name) == _canonical_rule_token(MARTIAL_KATAH_ABILITY_NAME)
        for ability in unit.datasheet_abilities
    )


def _martial_katah_payload(payload: JsonValue) -> dict[str, JsonValue]:
    raw = _json_object("Martial Ka'tah effect payload", payload)
    if raw.get("effect_kind") != MARTIAL_KATAH_EFFECT_KIND:
        raise GameLifecycleError("Martial Ka'tah effect kind drift.")
    if type(raw.get("unit_instance_id")) is not str:
        raise GameLifecycleError("Martial Ka'tah effect payload is missing unit_instance_id.")
    _target_unit_ids_from_payload(raw)
    if type(raw.get("trigger")) is not str:
        raise GameLifecycleError("Martial Ka'tah effect payload is missing trigger.")
    if type(raw.get("phase")) is not str:
        raise GameLifecycleError("Martial Ka'tah effect payload is missing phase.")
    _battle_phase_from_token(raw["phase"])
    if type(raw.get("selected_martial_katah")) is not str:
        raise GameLifecycleError("Martial Ka'tah effect payload is missing selected stance.")
    _stance_from_token(raw["selected_martial_katah"])
    if "source_context" not in raw:
        raise GameLifecycleError("Martial Ka'tah effect payload is missing source_context.")
    validate_json_value(raw.get("source_context"))
    return cast(dict[str, JsonValue], raw)


def _target_unit_ids_from_payload(payload: dict[str, object]) -> tuple[str, ...]:
    raw_target_ids = payload.get("target_unit_instance_ids")
    if not isinstance(raw_target_ids, list):
        raise GameLifecycleError("Martial Ka'tah target_unit_instance_ids must be a list.")
    target_ids = tuple(
        _validate_identifier("target_unit_instance_ids value", raw_id)
        for raw_id in cast(list[object], raw_target_ids)
    )
    if not target_ids:
        raise GameLifecycleError("Martial Ka'tah target_unit_instance_ids is empty.")
    if len(set(target_ids)) != len(target_ids):
        raise GameLifecycleError("Martial Ka'tah target_unit_instance_ids are duplicated.")
    return target_ids


def _profile_with_keyword_and_ability(
    profile: WeaponProfile,
    *,
    keyword: WeaponKeyword,
    ability: AbilityDescriptor,
    source_rule_id: str,
) -> WeaponProfile:
    if type(profile) is not WeaponProfile:
        raise GameLifecycleError("Martial Ka'tah weapon profile modifier requires WeaponProfile.")
    requested_source_rule_id = _validate_identifier("source_rule_id", source_rule_id)
    keywords = profile.keywords
    if keyword not in keywords:
        keywords = (*keywords, keyword)
    abilities = profile.abilities
    if all(existing.ability_id != ability.ability_id for existing in abilities):
        abilities = (*abilities, ability)
    source_ids = profile.source_ids
    if requested_source_rule_id not in source_ids:
        source_ids = (*source_ids, requested_source_rule_id)
    return replace(profile, keywords=keywords, abilities=abilities, source_ids=source_ids)


def _stance_from_token(token: object) -> MartialKatahStance:
    if type(token) is MartialKatahStance:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Martial Ka'tah stance must be a string.")
    try:
        return MartialKatahStance(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported Martial Ka'tah stance: {token}.") from exc


def _battle_phase_from_token(token: object) -> BattlePhase:
    if type(token) is BattlePhase:
        return token
    if type(token) is BattlePhaseKind:
        return BattlePhase(token.value)
    if type(token) is not str:
        raise GameLifecycleError("Martial Ka'tah phase must be a BattlePhase.")
    try:
        return BattlePhase(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported Martial Ka'tah phase: {token}.") from exc


def _canonical_rule_token(value: str) -> str:
    return " ".join(_validate_identifier("rule token", value).upper().split())


def _json_object(field_name: str, value: JsonValue) -> dict[str, object]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{field_name} must be an object.")
    return cast(dict[str, object], value)


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Martial Ka'tah {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Martial Ka'tah {field_name} must not be empty.")
    return stripped


def _validate_identifier_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"Martial Ka'tah {field_name} must be a tuple.")
    seen: set[str] = set()
    validated: list[str] = []
    for value in values:
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"Martial Ka'tah {field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    if not validated:
        raise GameLifecycleError(f"Martial Ka'tah {field_name} must not be empty.")
    return tuple(validated)
