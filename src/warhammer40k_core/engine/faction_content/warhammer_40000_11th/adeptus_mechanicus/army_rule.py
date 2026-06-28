from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import cast

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    RangeProfileKind,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battle_round_hooks import (
    SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
    BattleRoundStartHookBinding,
    BattleRoundStartRequestContext,
    BattleRoundStartResultContext,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    PlacementError,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.decision_request import (
    DecisionError,
    DecisionOption,
    DecisionRequest,
)
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.faction_rule_states import FactionRuleState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, SetupStep
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_view_by_id,
)
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierBinding,
    HitRollModifierContext,
    WeaponProfileModifierBinding,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.volume import Model as GeometryModel

SOURCE_RULE_ID = "phase17f:phase17e:adeptus-mechanicus:army-rule"
HOOK_ID = "warhammer_40000_11th:adeptus_mechanicus:army_rule:doctrina_imperatives"
CONTRIBUTION_ID = HOOK_ID
WEAPON_PROFILE_MODIFIER_ID = f"{HOOK_ID}:weapon-profile"
PROTECTOR_HIT_MODIFIER_ID = f"{HOOK_ID}:protector:melee-hit-roll"

ADEPTUS_MECHANICUS_FACTION_ID = "adeptus-mechanicus"
ADEPTUS_MECHANICUS_FACTION_KEYWORD = "ADEPTUS MECHANICUS"
BATTLELINE_KEYWORD = "BATTLELINE"
DOCTRINA_IMPERATIVES_ABILITY_NAME = "Doctrina Imperatives"
DOCTRINA_EFFECT_KIND = "adeptus_mechanicus_doctrina_imperatives_active"
DOCTRINA_SELECTION_KIND = "adeptus_mechanicus_doctrina_imperatives_selection"
DOCTRINA_SELECTION_STATE_KIND = "adeptus_mechanicus_doctrina_imperatives_selected"
DOCTRINA_DECLINE_OPTION_ID = "adeptus_mechanicus:doctrina_imperatives:decline"
DOCTRINA_BATTLELINE_AURA_RANGE_INCHES = 6.0


class DoctrinaImperative(StrEnum):
    PROTECTOR = "protector"
    CONQUEROR = "conqueror"


def _validate_definition_text(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Doctrina Imperatives {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Doctrina Imperatives {field_name} must not be empty.")
    return stripped


@dataclass(frozen=True, slots=True)
class DoctrinaImperativeDefinition:
    imperative: DoctrinaImperative
    label: str
    effect_summary: str

    def __post_init__(self) -> None:
        imperative: object = self.imperative
        if type(imperative) is str:
            try:
                imperative = DoctrinaImperative(imperative)
            except ValueError as exc:
                raise GameLifecycleError(f"Unsupported Doctrina Imperative: {imperative}.") from exc
        if type(imperative) is not DoctrinaImperative:
            raise GameLifecycleError("Doctrina Imperatives imperative must be a string.")
        object.__setattr__(
            self,
            "imperative",
            imperative,
        )
        object.__setattr__(self, "label", _validate_definition_text("label", self.label))
        object.__setattr__(
            self,
            "effect_summary",
            _validate_definition_text("effect_summary", self.effect_summary),
        )

    @property
    def option_id(self) -> str:
        return f"adeptus_mechanicus:doctrina_imperatives:{self.imperative.value}"


DOCTRINA_DEFINITIONS: tuple[DoctrinaImperativeDefinition, ...] = (
    DoctrinaImperativeDefinition(
        imperative=DoctrinaImperative.PROTECTOR,
        label="Protector Imperative",
        effect_summary=(
            "Ranged weapons gain Heavy and improve Ballistic Skill; eligible "
            "Battleline-supported units impose -1 to melee Hit rolls that target them."
        ),
    ),
    DoctrinaImperativeDefinition(
        imperative=DoctrinaImperative.CONQUEROR,
        label="Conqueror Imperative",
        effect_summary=(
            "Ranged weapons gain Assault and melee weapons improve Weapon Skill; eligible "
            "Battleline-supported units improve attack AP by 1."
        ),
    ),
)
_DEFINITION_BY_IMPERATIVE = {
    definition.imperative: definition for definition in DOCTRINA_DEFINITIONS
}


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        battle_round_start_hook_bindings=(
            BattleRoundStartHookBinding(
                hook_id=HOOK_ID,
                source_id=SOURCE_RULE_ID,
                request_handler=doctrina_selection_request,
                result_handler=apply_doctrina_selection_result,
            ),
        ),
        weapon_profile_modifier_bindings=(
            WeaponProfileModifierBinding(
                modifier_id=WEAPON_PROFILE_MODIFIER_ID,
                source_id=SOURCE_RULE_ID,
                handler=doctrina_weapon_profile_modifier,
            ),
        ),
        hit_roll_modifier_bindings=(
            HitRollModifierBinding(
                modifier_id=PROTECTOR_HIT_MODIFIER_ID,
                source_id=SOURCE_RULE_ID,
                handler=protector_imperative_hit_roll_modifier,
            ),
        ),
    )


def doctrina_selection_request(
    context: BattleRoundStartRequestContext,
) -> DecisionRequest | None:
    if type(context) is not BattleRoundStartRequestContext:
        raise GameLifecycleError("Doctrina Imperatives requires request context.")
    for army in _adeptus_mechanicus_armies(context.state):
        if _doctrina_selection_recorded_for_round(
            context.state,
            player_id=army.player_id,
            battle_round=context.state.battle_round,
        ):
            continue
        target_unit_ids = _eligible_doctrina_rules_unit_ids_for_army(
            state=context.state,
            army=army,
        )
        if not target_unit_ids:
            continue
        common_payload = doctrina_common_payload(
            state=context.state,
            player_id=army.player_id,
            target_unit_ids=target_unit_ids,
        )
        return DecisionRequest(
            request_id=context.state.next_decision_request_id(),
            decision_type=SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
            actor_id=army.player_id,
            payload=validate_json_value(common_payload),
            options=doctrina_selection_options(common_payload=common_payload),
        )
    return None


def apply_doctrina_selection_result(context: BattleRoundStartResultContext) -> bool:
    if type(context) is not BattleRoundStartResultContext:
        raise GameLifecycleError("Doctrina Imperatives requires result context.")
    if context.request.decision_type != SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE:
        return False
    request_payload = _payload_object(context.request.payload)
    if request_payload.get("hook_id") != HOOK_ID:
        return False
    result = context.result
    if result.actor_id is None:
        raise GameLifecycleError("Doctrina Imperatives selection requires an actor.")
    player_id = result.actor_id
    army = _adeptus_mechanicus_army_for_player(context.state, player_id=player_id)
    if army is None:
        raise GameLifecycleError("Doctrina Imperatives actor does not own Adeptus Mechanicus.")
    if _doctrina_selection_recorded_for_round(
        context.state,
        player_id=player_id,
        battle_round=context.state.battle_round,
    ):
        raise GameLifecycleError("Doctrina Imperatives selection is already recorded this round.")
    _validate_request_matches_current_state(context=context, army=army)
    try:
        expected_option = context.request.option_by_id(result.selected_option_id)
    except DecisionError as exc:
        raise GameLifecycleError("Doctrina Imperatives selected option is not available.") from exc
    if result.payload != expected_option.payload:
        raise GameLifecycleError("Doctrina Imperatives selected option payload drift.")
    payload = _payload_object(result.payload)
    selection_mode = _payload_string(payload, key="selection_mode")
    target_unit_ids = _eligible_doctrina_rules_unit_ids_for_army(
        state=context.state,
        army=army,
    )
    if not target_unit_ids:
        raise GameLifecycleError("Doctrina Imperatives selection has no eligible units.")

    if selection_mode == "decline":
        if result.selected_option_id != DOCTRINA_DECLINE_OPTION_ID:
            raise GameLifecycleError("Doctrina Imperatives decline option ID drift.")
        state_record = _doctrina_selection_state(
            context=context,
            player_id=player_id,
            target_unit_ids=target_unit_ids,
            selected_imperative=None,
        )
        context.state.record_faction_rule_state(state_record)
        context.decisions.event_log.append(
            "adeptus_mechanicus_doctrina_imperatives_declined",
            validate_json_value(
                {
                    "game_id": context.state.game_id,
                    "battle_round": context.state.battle_round,
                    "phase": BattlePhase.COMMAND.value,
                    "player_id": player_id,
                    "source_rule_id": SOURCE_RULE_ID,
                    "hook_id": HOOK_ID,
                    "faction_rule_state": state_record.to_payload(),
                }
            ),
        )
        return True

    if selection_mode != "select":
        raise GameLifecycleError("Doctrina Imperatives selection mode is unsupported.")
    selected_imperative = _imperative_from_token(
        _payload_string(payload, key="selected_doctrina_imperative_id")
    )
    definition = _DEFINITION_BY_IMPERATIVE[selected_imperative]
    expected_option_id = definition.option_id
    if result.selected_option_id != expected_option_id:
        raise GameLifecycleError("Doctrina Imperatives selected option ID drift.")

    state_record = _doctrina_selection_state(
        context=context,
        player_id=player_id,
        target_unit_ids=target_unit_ids,
        selected_imperative=selected_imperative,
    )
    effect = _doctrina_active_effect(
        context=context,
        player_id=player_id,
        target_unit_ids=target_unit_ids,
        selected_imperative=selected_imperative,
    )
    context.state.record_faction_rule_state(state_record)
    context.state.record_persisting_effect(effect)
    context.decisions.event_log.append(
        "adeptus_mechanicus_doctrina_imperative_selected",
        validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "player_id": player_id,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
                "selected_doctrina_imperative_id": selected_imperative.value,
                "selected_doctrina_imperative_label": definition.label,
                "faction_rule_state": state_record.to_payload(),
                "persisting_effect": effect.to_payload(),
            }
        ),
    )
    return True


def doctrina_common_payload(
    *,
    state: object,
    player_id: str,
    target_unit_ids: tuple[str, ...],
) -> dict[str, JsonValue]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Doctrina Imperatives payload requires GameState.")
    requested_player_id = _validate_identifier("player_id", player_id)
    return cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "player_id": requested_player_id,
                "faction_id": ADEPTUS_MECHANICUS_FACTION_ID,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
                "effect_kind": DOCTRINA_EFFECT_KIND,
                "selection_kind": DOCTRINA_SELECTION_KIND,
                "target_unit_instance_ids": list(
                    _validate_identifier_tuple("target_unit_ids", target_unit_ids)
                ),
                "expires_at": EffectExpiration.end_battle_round(
                    battle_round=state.battle_round
                ).to_payload(),
            }
        ),
    )


def doctrina_selection_options(
    *,
    common_payload: dict[str, JsonValue],
) -> tuple[DecisionOption, ...]:
    payload = _json_object("Doctrina Imperatives common payload", common_payload)
    options = [
        DecisionOption(
            option_id=definition.option_id,
            label=definition.label,
            payload=validate_json_value(
                {
                    **payload,
                    "submission_kind": DOCTRINA_SELECTION_KIND,
                    "selection_mode": "select",
                    "selected_doctrina_imperative_id": definition.imperative.value,
                    "selected_doctrina_imperative_label": definition.label,
                    "effect_summary": definition.effect_summary,
                }
            ),
        )
        for definition in DOCTRINA_DEFINITIONS
    ]
    options.append(
        DecisionOption(
            option_id=DOCTRINA_DECLINE_OPTION_ID,
            label="Do not select a Doctrina Imperative",
            payload=validate_json_value(
                {
                    **payload,
                    "submission_kind": DOCTRINA_SELECTION_KIND,
                    "selection_mode": "decline",
                    "selected_doctrina_imperative_id": None,
                    "selected_doctrina_imperative_label": None,
                    "effect_summary": "No Doctrina Imperative is active for this army.",
                }
            ),
        )
    )
    return tuple(options)


def active_doctrina_imperative_for_player(
    state: object,
    *,
    player_id: str,
) -> DoctrinaImperative | None:
    effect = _active_doctrina_effect_for_player(state, player_id=player_id)
    if effect is None:
        return None
    payload = _doctrina_effect_payload(effect.effect_payload)
    return _imperative_from_token(_payload_string(payload, key="selected_doctrina_imperative_id"))


def active_doctrina_imperative_for_unit(
    state: object,
    *,
    unit_instance_id: str,
) -> DoctrinaImperative | None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Doctrina Imperatives unit lookup requires GameState.")
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=requested_unit_id)
    if not _rules_unit_has_doctrina_imperatives(rules_unit):
        return None
    effect = _active_doctrina_effect_for_player(state, player_id=rules_unit.owner_player_id)
    if effect is None:
        return None
    if rules_unit.unit_instance_id not in effect.target_unit_instance_ids:
        return None
    payload = _doctrina_effect_payload(effect.effect_payload)
    return _imperative_from_token(_payload_string(payload, key="selected_doctrina_imperative_id"))


def doctrina_weapon_profile_modifier(context: WeaponProfileModifierContext) -> WeaponProfile:
    if type(context) is not WeaponProfileModifierContext:
        raise GameLifecycleError("Doctrina Imperatives weapon profile modifier requires context.")
    imperative = active_doctrina_imperative_for_unit(
        context.state,
        unit_instance_id=context.attacking_unit_instance_id,
    )
    if imperative is None:
        return context.weapon_profile
    if imperative is DoctrinaImperative.PROTECTOR:
        return _protector_weapon_profile(context.weapon_profile)
    if imperative is DoctrinaImperative.CONQUEROR:
        return _conqueror_weapon_profile(context)
    raise GameLifecycleError("Doctrina Imperatives selected imperative is unsupported.")


def protector_imperative_hit_roll_modifier(context: HitRollModifierContext) -> int:
    if type(context) is not HitRollModifierContext:
        raise GameLifecycleError("Doctrina Imperatives Hit roll modifier requires context.")
    if context.weapon_profile.range_profile.kind is not RangeProfileKind.MELEE:
        return 0
    if (
        active_doctrina_imperative_for_unit(
            context.state,
            unit_instance_id=context.target_unit_instance_id,
        )
        is not DoctrinaImperative.PROTECTOR
    ):
        return 0
    if _rules_unit_has_battleline_or_nearby_admech_battleline(
        context.state,
        unit_instance_id=context.target_unit_instance_id,
    ):
        return -1
    return 0


def _protector_weapon_profile(profile: WeaponProfile) -> WeaponProfile:
    if type(profile) is not WeaponProfile:
        raise GameLifecycleError("Doctrina Imperatives Protector requires WeaponProfile.")
    if profile.range_profile.kind is not RangeProfileKind.DISTANCE:
        return profile
    heavy = AbilityDescriptor.heavy()
    abilities = profile.abilities
    if all(ability.ability_id != heavy.ability_id for ability in abilities):
        abilities = (*abilities, heavy)
    return replace(
        profile,
        keywords=_weapon_keywords_with(profile.keywords, WeaponKeyword.HEAVY),
        abilities=abilities,
        skill=_improve_ballistic_skill(profile.skill),
        source_ids=_source_ids_with_doctrina(profile.source_ids),
    )


def _conqueror_weapon_profile(context: WeaponProfileModifierContext) -> WeaponProfile:
    profile = context.weapon_profile
    keywords = profile.keywords
    skill = profile.skill
    if profile.range_profile.kind is RangeProfileKind.DISTANCE:
        keywords = _weapon_keywords_with(keywords, WeaponKeyword.ASSAULT)
    elif profile.range_profile.kind is RangeProfileKind.MELEE:
        skill = _improve_weapon_skill(skill)
    else:
        raise GameLifecycleError("Doctrina Imperatives profile range kind is unsupported.")
    armor_penetration = profile.armor_penetration
    if _rules_unit_has_battleline_or_nearby_admech_battleline(
        context.state,
        unit_instance_id=context.attacking_unit_instance_id,
    ):
        armor_penetration = _improve_armor_penetration(armor_penetration, bonus=1)
    return replace(
        profile,
        keywords=keywords,
        skill=skill,
        armor_penetration=armor_penetration,
        source_ids=_source_ids_with_doctrina(profile.source_ids),
    )


def _doctrina_selection_state(
    *,
    context: BattleRoundStartResultContext,
    player_id: str,
    target_unit_ids: tuple[str, ...],
    selected_imperative: DoctrinaImperative | None,
) -> FactionRuleState:
    requested_player_id = _validate_identifier("player_id", player_id)
    selected_label = None
    if selected_imperative is not None:
        selected_label = _DEFINITION_BY_IMPERATIVE[selected_imperative].label
    return FactionRuleState(
        state_id=(
            f"{HOOK_ID}:{requested_player_id}:round-{context.state.battle_round:02d}:selection"
        ),
        player_id=requested_player_id,
        faction_id=ADEPTUS_MECHANICUS_FACTION_ID,
        source_rule_id=SOURCE_RULE_ID,
        state_kind=DOCTRINA_SELECTION_STATE_KIND,
        setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
        request_id=context.request.request_id,
        result_id=context.result.result_id,
        payload=validate_json_value(
            {
                "selection_kind": DOCTRINA_SELECTION_KIND,
                "effect_kind": DOCTRINA_EFFECT_KIND,
                "selection_mode": "decline" if selected_imperative is None else "select",
                "selected_option_id": context.result.selected_option_id,
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "player_id": requested_player_id,
                "faction_id": ADEPTUS_MECHANICUS_FACTION_ID,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
                "selected_doctrina_imperative_id": (
                    None if selected_imperative is None else selected_imperative.value
                ),
                "selected_doctrina_imperative_label": selected_label,
                "target_unit_instance_ids": list(
                    _validate_identifier_tuple("target_unit_ids", target_unit_ids)
                ),
            }
        ),
    )


def _doctrina_active_effect(
    *,
    context: BattleRoundStartResultContext,
    player_id: str,
    target_unit_ids: tuple[str, ...],
    selected_imperative: DoctrinaImperative,
) -> PersistingEffect:
    requested_player_id = _validate_identifier("player_id", player_id)
    imperative = _imperative_from_token(selected_imperative)
    definition = _DEFINITION_BY_IMPERATIVE[imperative]
    expiration = EffectExpiration.end_battle_round(battle_round=context.state.battle_round)
    return PersistingEffect(
        effect_id=f"{HOOK_ID}:{requested_player_id}:round-{context.state.battle_round:02d}:active",
        source_rule_id=SOURCE_RULE_ID,
        owner_player_id=requested_player_id,
        target_unit_instance_ids=_validate_identifier_tuple("target_unit_ids", target_unit_ids),
        started_battle_round=context.state.battle_round,
        started_phase=BattlePhaseKind.COMMAND,
        expiration=expiration,
        effect_payload=validate_json_value(
            {
                "effect_kind": DOCTRINA_EFFECT_KIND,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "player_id": requested_player_id,
                "faction_id": ADEPTUS_MECHANICUS_FACTION_ID,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
                "selected_doctrina_imperative_id": imperative.value,
                "selected_doctrina_imperative_label": definition.label,
                "selected_option_id": context.result.selected_option_id,
                "request_id": context.request.request_id,
                "result_id": context.result.result_id,
                "target_unit_instance_ids": list(target_unit_ids),
                "expires_at": expiration.to_payload(),
            }
        ),
    )


def _active_doctrina_effect_for_player(
    state: object,
    *,
    player_id: str,
) -> PersistingEffect | None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Doctrina Imperatives effect lookup requires GameState.")
    requested_player_id = _validate_identifier("player_id", player_id)
    matching: list[PersistingEffect] = []
    for effect in state.persisting_effects:
        if effect.owner_player_id != requested_player_id:
            continue
        if effect.source_rule_id != SOURCE_RULE_ID:
            continue
        payload = _doctrina_effect_payload(effect.effect_payload)
        if _payload_int(payload, key="battle_round") != state.battle_round:
            continue
        matching.append(effect)
    if len(matching) > 1:
        raise GameLifecycleError("Doctrina Imperatives found multiple active effects.")
    return None if not matching else matching[0]


def _doctrina_selection_recorded_for_round(
    state: object,
    *,
    player_id: str,
    battle_round: int,
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Doctrina Imperatives selection lookup requires GameState.")
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_round = _validate_positive_int("battle_round", battle_round)
    matching: list[FactionRuleState] = []
    for state_record in state.faction_rule_states_for_player(
        player_id=requested_player_id,
        state_kind=DOCTRINA_SELECTION_STATE_KIND,
    ):
        if state_record.source_rule_id != SOURCE_RULE_ID:
            continue
        payload = _payload_object(state_record.payload)
        if _payload_int(payload, key="battle_round") == requested_round:
            matching.append(state_record)
    if len(matching) > 1:
        raise GameLifecycleError("Doctrina Imperatives found duplicate round states.")
    return bool(matching)


def _eligible_doctrina_rules_unit_ids_for_army(
    *,
    state: object,
    army: ArmyDefinition,
) -> tuple[str, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Doctrina Imperatives eligibility requires GameState.")
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError("Doctrina Imperatives eligibility requires ArmyDefinition.")
    return tuple(
        rules_unit.unit_instance_id
        for rules_unit in _rules_unit_views_for_army(state=state, army=army)
        if _rules_unit_has_doctrina_imperatives(rules_unit)
    )


def _rules_unit_views_for_army(
    *,
    state: object,
    army: ArmyDefinition,
) -> tuple[RulesUnitView, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Doctrina Imperatives rules-unit lookup requires GameState.")
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError("Doctrina Imperatives rules-unit lookup requires ArmyDefinition.")
    views: list[RulesUnitView] = []
    seen: set[str] = set()
    for unit in army.units:
        view = rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id)
        if view.owner_player_id != army.player_id:
            raise GameLifecycleError("Doctrina Imperatives rules-unit owner drift.")
        if view.unit_instance_id in seen:
            continue
        seen.add(view.unit_instance_id)
        views.append(view)
    return tuple(sorted(views, key=lambda view: view.unit_instance_id))


def _rules_unit_has_doctrina_imperatives(rules_unit: RulesUnitView) -> bool:
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Doctrina Imperatives ability lookup requires rules unit.")
    return any(
        _unit_has_doctrina_imperatives(component.unit) for component in rules_unit.components
    )


def _unit_has_doctrina_imperatives(unit: UnitInstance) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Doctrina Imperatives ability lookup requires UnitInstance.")
    return _unit_has_named_ability(unit, DOCTRINA_IMPERATIVES_ABILITY_NAME)


def _rules_unit_has_battleline_or_nearby_admech_battleline(
    state: object,
    *,
    unit_instance_id: str,
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Doctrina Imperatives Battleline lookup requires GameState.")
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=_validate_identifier("unit_instance_id", unit_instance_id),
    )
    if _rules_unit_has_keyword(rules_unit, BATTLELINE_KEYWORD):
        return True
    return _rules_unit_within_friendly_admech_battleline(
        state=state,
        rules_unit=rules_unit,
        distance_inches=DOCTRINA_BATTLELINE_AURA_RANGE_INCHES,
    )


def _rules_unit_within_friendly_admech_battleline(
    *,
    state: object,
    rules_unit: RulesUnitView,
    distance_inches: float,
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Doctrina Imperatives Battleline aura requires GameState.")
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Doctrina Imperatives Battleline aura requires rules unit.")
    requested_distance = _validate_non_negative_float("distance_inches", distance_inches)
    scenario = _battlefield_scenario(state)
    target_models = _alive_geometry_models_for_rules_unit(
        scenario=scenario,
        rules_unit=rules_unit,
    )
    if not target_models:
        return False
    army = state.army_definition_for_player(rules_unit.owner_player_id)
    if army is None:
        raise GameLifecycleError("Doctrina Imperatives Battleline aura army is missing.")
    for candidate in _rules_unit_views_for_army(state=state, army=army):
        if candidate.unit_instance_id == rules_unit.unit_instance_id:
            continue
        if not _rules_unit_has_keyword(candidate, BATTLELINE_KEYWORD):
            continue
        if not _rules_unit_has_faction_keyword(candidate, ADEPTUS_MECHANICUS_FACTION_KEYWORD):
            continue
        candidate_models = _alive_geometry_models_for_rules_unit(
            scenario=scenario,
            rules_unit=candidate,
        )
        if _any_geometry_models_within(
            first=target_models,
            second=candidate_models,
            distance_inches=requested_distance,
        ):
            return True
    return False


def _alive_geometry_models_for_rules_unit(
    *,
    scenario: BattlefieldScenario,
    rules_unit: RulesUnitView,
) -> tuple[GeometryModel, ...]:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("Doctrina Imperatives geometry lookup requires scenario.")
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Doctrina Imperatives geometry lookup requires rules unit.")
    models: list[GeometryModel] = []
    for component in rules_unit.components:
        unit_placement = scenario.battlefield_state.unit_placement_by_id(
            component.unit.unit_instance_id
        )
        for model_placement in unit_placement.model_placements:
            model = scenario.model_instance_for_placement(model_placement)
            if model.is_alive:
                models.append(geometry_model_for_placement(model=model, placement=model_placement))
    return tuple(sorted(models, key=lambda model: model.model_id))


def _any_geometry_models_within(
    *,
    first: tuple[GeometryModel, ...],
    second: tuple[GeometryModel, ...],
    distance_inches: float,
) -> bool:
    for first_model in _validate_geometry_models("first", first):
        for second_model in _validate_geometry_models("second", second):
            if first_model.range_to(second_model) <= distance_inches:
                return True
    return False


def _battlefield_scenario(state: object) -> BattlefieldScenario:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Doctrina Imperatives battlefield lookup requires GameState.")
    if state.battlefield_state is None:
        raise GameLifecycleError("Doctrina Imperatives requires battlefield_state.")
    try:
        return BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=state.battlefield_state,
        )
    except PlacementError as exc:
        raise GameLifecycleError("Doctrina Imperatives battlefield scenario is invalid.") from exc


def _adeptus_mechanicus_army_for_player(
    state: object,
    *,
    player_id: str,
) -> ArmyDefinition | None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Doctrina Imperatives army lookup requires GameState.")
    requested_player_id = _validate_identifier("player_id", player_id)
    army = state.army_definition_for_player(requested_player_id)
    if army is None:
        return None
    if army.detachment_selection.faction_id != ADEPTUS_MECHANICUS_FACTION_ID:
        return None
    return army


def _adeptus_mechanicus_armies(state: object) -> tuple[ArmyDefinition, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Doctrina Imperatives army lookup requires GameState.")
    return tuple(
        army
        for army in state.army_definitions
        if army.detachment_selection.faction_id == ADEPTUS_MECHANICUS_FACTION_ID
    )


def _validate_request_matches_current_state(
    *,
    context: BattleRoundStartResultContext,
    army: ArmyDefinition,
) -> None:
    request_payload = _payload_object(context.request.payload)
    _expect_payload_string(request_payload, key="game_id", expected=context.state.game_id)
    if _payload_int(request_payload, key="battle_round") != context.state.battle_round:
        raise GameLifecycleError("Doctrina Imperatives battle_round drift.")
    _expect_payload_string(request_payload, key="player_id", expected=army.player_id)
    _expect_payload_string(
        request_payload,
        key="faction_id",
        expected=ADEPTUS_MECHANICUS_FACTION_ID,
    )
    _expect_payload_string(request_payload, key="source_rule_id", expected=SOURCE_RULE_ID)
    _expect_payload_string(request_payload, key="hook_id", expected=HOOK_ID)
    expected_targets = _eligible_doctrina_rules_unit_ids_for_army(
        state=context.state,
        army=army,
    )
    request_targets = _payload_string_tuple(request_payload, key="target_unit_instance_ids")
    if request_targets != expected_targets:
        raise GameLifecycleError("Doctrina Imperatives eligible target drift.")


def _doctrina_effect_payload(payload: JsonValue) -> dict[str, JsonValue]:
    raw = _payload_object(payload)
    if raw.get("effect_kind") != DOCTRINA_EFFECT_KIND:
        raise GameLifecycleError("Doctrina Imperatives effect kind drift.")
    _expect_payload_string(raw, key="source_rule_id", expected=SOURCE_RULE_ID)
    _expect_payload_string(raw, key="hook_id", expected=HOOK_ID)
    _payload_int(raw, key="battle_round")
    _imperative_from_token(_payload_string(raw, key="selected_doctrina_imperative_id"))
    _payload_string_tuple(raw, key="target_unit_instance_ids")
    return raw


def _improve_ballistic_skill(skill: CharacteristicValue) -> CharacteristicValue:
    if type(skill) is not CharacteristicValue:
        raise GameLifecycleError("Doctrina Imperatives Ballistic Skill requires value.")
    if skill.characteristic is not Characteristic.BALLISTIC_SKILL:
        raise GameLifecycleError("Doctrina Imperatives Ballistic Skill characteristic drift.")
    if not skill.is_numeric:
        raise GameLifecycleError("Doctrina Imperatives cannot improve non-numeric Ballistic Skill.")
    return CharacteristicValue.from_raw(
        Characteristic.BALLISTIC_SKILL,
        _improve_skill(skill.final),
    )


def _improve_weapon_skill(skill: CharacteristicValue) -> CharacteristicValue:
    if type(skill) is not CharacteristicValue:
        raise GameLifecycleError("Doctrina Imperatives Weapon Skill requires value.")
    if skill.characteristic is not Characteristic.WEAPON_SKILL:
        raise GameLifecycleError("Doctrina Imperatives Weapon Skill characteristic drift.")
    if not skill.is_numeric:
        raise GameLifecycleError("Doctrina Imperatives cannot improve non-numeric Weapon Skill.")
    return CharacteristicValue.from_raw(
        Characteristic.WEAPON_SKILL,
        _improve_skill(skill.final),
    )


def _improve_skill(value: int) -> int:
    current = _validate_positive_int("skill", value)
    if current <= 2:
        return current
    return current - 1


def _improve_armor_penetration(
    armor_penetration: CharacteristicValue,
    *,
    bonus: int,
) -> CharacteristicValue:
    if type(armor_penetration) is not CharacteristicValue:
        raise GameLifecycleError("Doctrina Imperatives AP modifier requires value.")
    if armor_penetration.characteristic is not Characteristic.ARMOR_PENETRATION:
        raise GameLifecycleError("Doctrina Imperatives AP characteristic drift.")
    amount = _validate_positive_int("armor_penetration_bonus", bonus)
    return CharacteristicValue.from_raw(
        Characteristic.ARMOR_PENETRATION,
        armor_penetration.final - amount,
    )


def _weapon_keywords_with(
    keywords: tuple[WeaponKeyword, ...],
    keyword: WeaponKeyword,
) -> tuple[WeaponKeyword, ...]:
    if type(keywords) is not tuple:
        raise GameLifecycleError("Doctrina Imperatives keywords must be a tuple.")
    requested = _weapon_keyword_from_token(keyword)
    for stored in keywords:
        _weapon_keyword_from_token(stored)
    if requested in keywords:
        return keywords
    return tuple(sorted((*keywords, requested)))


def _source_ids_with_doctrina(source_ids: tuple[str, ...]) -> tuple[str, ...]:
    if type(source_ids) is not tuple:
        raise GameLifecycleError("Doctrina Imperatives source_ids must be a tuple.")
    for source_id in source_ids:
        _validate_identifier("source_id", source_id)
    return tuple(sorted({*source_ids, SOURCE_RULE_ID}))


def _rules_unit_has_keyword(rules_unit: RulesUnitView, keyword: str) -> bool:
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Doctrina Imperatives keyword lookup requires rules unit.")
    return _keyword_token_in(
        values=(*rules_unit.keywords, *rules_unit.faction_keywords),
        expected=keyword,
    )


def _rules_unit_has_faction_keyword(rules_unit: RulesUnitView, keyword: str) -> bool:
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Doctrina Imperatives faction keyword lookup requires rules unit.")
    return _keyword_token_in(values=rules_unit.faction_keywords, expected=keyword)


def _unit_has_named_ability(unit: UnitInstance, ability_name: str) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Doctrina Imperatives ability lookup requires UnitInstance.")
    requested_name = _normalise_rule_token(_validate_identifier("ability_name", ability_name))
    return any(
        _normalise_rule_token(ability.name) == requested_name
        for ability in unit.datasheet_abilities
    )


def _keyword_token_in(*, values: tuple[str, ...], expected: str) -> bool:
    if type(values) is not tuple:
        raise GameLifecycleError("Doctrina Imperatives keyword values must be a tuple.")
    normalised_expected = _normalise_rule_token(_validate_identifier("expected", expected))
    return any(_normalise_rule_token(value) == normalised_expected for value in values)


def _normalise_rule_token(value: str) -> str:
    return "".join(character for character in value.upper() if character.isalnum())


def _imperative_from_token(token: object) -> DoctrinaImperative:
    if type(token) is DoctrinaImperative:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Doctrina Imperatives imperative must be a string.")
    try:
        return DoctrinaImperative(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported Doctrina Imperative: {token}.") from exc


def _weapon_keyword_from_token(token: object) -> WeaponKeyword:
    if type(token) is WeaponKeyword:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Doctrina Imperatives weapon keyword must be a string.")
    try:
        return WeaponKeyword(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported Doctrina weapon keyword: {token}.") from exc


def _payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Doctrina Imperatives payload must be an object.")
    return payload


def _json_object(field_name: str, value: object) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{field_name} must be an object.")
    return cast(dict[str, JsonValue], value)


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"Doctrina Imperatives payload {key} must be a string.")
    return value


def _payload_int(payload: dict[str, JsonValue], *, key: str) -> int:
    value = payload.get(key)
    if type(value) is not int:
        raise GameLifecycleError(f"Doctrina Imperatives payload {key} must be an int.")
    return value


def _payload_string_tuple(payload: dict[str, JsonValue], *, key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise GameLifecycleError(f"Doctrina Imperatives payload {key} must be a list.")
    return _validate_identifier_tuple(
        key,
        tuple(_validate_identifier(f"{key} value", item) for item in value),
    )


def _expect_payload_string(
    payload: dict[str, JsonValue],
    *,
    key: str,
    expected: str,
) -> None:
    actual = _payload_string(payload, key=key)
    if actual != expected:
        raise GameLifecycleError(f"Doctrina Imperatives {key} drift.")


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Doctrina Imperatives {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Doctrina Imperatives {field_name} must not be empty.")
    return stripped


def _validate_identifier_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"Doctrina Imperatives {field_name} must be a tuple.")
    seen: set[str] = set()
    validated: list[str] = []
    for value in values:
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"Doctrina Imperatives {field_name} must be unique.")
        seen.add(identifier)
        validated.append(identifier)
    if not validated:
        raise GameLifecycleError(f"Doctrina Imperatives {field_name} must not be empty.")
    return tuple(sorted(validated))


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"Doctrina Imperatives {field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"Doctrina Imperatives {field_name} must be positive.")
    return value


def _validate_non_negative_float(field_name: str, value: object) -> float:
    if type(value) not in {int, float}:
        raise GameLifecycleError(f"Doctrina Imperatives {field_name} must be numeric.")
    numeric = float(cast(int | float, value))
    if numeric < 0.0:
        raise GameLifecycleError(f"Doctrina Imperatives {field_name} must not be negative.")
    return numeric


def _validate_geometry_models(
    field_name: str,
    models: tuple[GeometryModel, ...],
) -> tuple[GeometryModel, ...]:
    if type(models) is not tuple:
        raise GameLifecycleError(f"Doctrina Imperatives {field_name} models must be a tuple.")
    for model in models:
        if type(model) is not GeometryModel:
            raise GameLifecycleError(
                f"Doctrina Imperatives {field_name} models must contain GeometryModel."
            )
    return models
