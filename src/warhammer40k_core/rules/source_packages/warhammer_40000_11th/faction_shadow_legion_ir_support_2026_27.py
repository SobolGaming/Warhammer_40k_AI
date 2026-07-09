from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import cast

from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleClausePayload,
    RuleConditionPayload,
    RuleDurationPayload,
    RuleEffectSpecPayload,
    RuleIR,
    RuleIRPayload,
    RuleParameterPayload,
    RuleTargetSpecPayload,
)
from warhammer40k_core.rules.rule_templates import (
    CHARACTERISTIC_MODIFIER_TEMPLATE_ID,
    CONTEXTUAL_STATUS_TEMPLATE_ID,
    DICE_ROLL_MODIFIER_TEMPLATE_ID,
    GRANT_ABILITY_TEMPLATE_ID,
    KEYWORD_GATE_TEMPLATE_ID,
    PLACEMENT_TEMPLATE_ID,
    RETURN_ON_DEATH_TEMPLATE_ID,
    WEAPON_ABILITY_GRANT_TEMPLATE_ID,
)

SOURCE_PACKAGE_ID = "gw-11e-phase17e-faction-coverage-2026-27"
STRATAGEM_SOURCE_PACKAGE_ID = "gw-11e-phase17e-exact-faction-subrules-2026-27"
STRATAGEM_TARGET_BINDING_TEMPLATE_ID = "phase17s:stratagem-activation-target-binding"

SHADOW_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID = "phase17e:chaos-daemons:shadow-legion:rule"
SHADOW_LEGION_KEYWORD = "SHADOW LEGION"
HERETIC_ASTARTES_KEYWORD = "HERETIC ASTARTES"
LEGIONES_DAEMONICA_KEYWORD = "LEGIONES DAEMONICA"
CHARACTER_KEYWORD = "CHARACTER"
KHORNE_KEYWORD = "KHORNE"
TZEENTCH_KEYWORD = "TZEENTCH"
NURGLE_KEYWORD = "NURGLE"
SLAANESH_KEYWORD = "SLAANESH"
UNDIVIDED_KEYWORD = "UNDIVIDED"
CAN_ADVANCE_AND_SHOOT_AND_CHARGE_ABILITY = "can_advance_and_shoot_and_charge"
SNAP_SHOOTING_TARGET_FORBIDDEN_ABILITY = "cannot_be_targeted_by_snap_shooting"
SHADOW_LEGION_DARK_PACT_LETHAL_HITS_CHOICE_ABILITY = "dark_pact_lethal_hits_choice"
SHADOW_LEGION_DARK_PACT_SUSTAINED_HITS_1_CHOICE_ABILITY = "dark_pact_sustained_hits_1_choice"
LEAPING_SHADOWS_ENHANCEMENT_ID = "000009980002"
LEAPING_SHADOWS_SOURCE_ROW_ID = "enhancement:chaos-daemons:shadow-legion:000009980002"
LEAPING_SHADOWS_ENHANCEMENT_DESCRIPTOR_ID = f"phase17e:{LEAPING_SHADOWS_SOURCE_ROW_ID}"
LEAPING_SHADOWS_SOURCE_RULE_ID = (
    "phase17f:phase17e:enhancement:chaos-daemons:shadow-legion:000009980002"
)
LEAPING_SHADOWS_SCOUTS_ABILITY = "chaos-daemons:shadow-legion:leaping-shadows:scouts-9"
MANTLE_OF_GLOOM_ENHANCEMENT_ID = "000009980003"
MANTLE_OF_GLOOM_SOURCE_ROW_ID = "enhancement:chaos-daemons:shadow-legion:000009980003"
MANTLE_OF_GLOOM_ENHANCEMENT_DESCRIPTOR_ID = f"phase17e:{MANTLE_OF_GLOOM_SOURCE_ROW_ID}"
MANTLE_OF_GLOOM_SOURCE_RULE_ID = (
    "phase17f:phase17e:enhancement:chaos-daemons:shadow-legion:000009980003"
)
MANTLE_OF_GLOOM_OBJECTIVE_CONTROL_ABILITY = (
    "chaos-daemons:shadow-legion:mantle-of-gloom:objective-control"
)
FADE_TO_DARKNESS_ENHANCEMENT_ID = "000009980004"
FADE_TO_DARKNESS_SOURCE_ROW_ID = "enhancement:chaos-daemons:shadow-legion:000009980004"
FADE_TO_DARKNESS_ENHANCEMENT_DESCRIPTOR_ID = f"phase17e:{FADE_TO_DARKNESS_SOURCE_ROW_ID}"
FADE_TO_DARKNESS_SOURCE_RULE_ID = (
    "phase17f:phase17e:enhancement:chaos-daemons:shadow-legion:000009980004"
)
FADE_TO_DARKNESS_RESERVES_ABILITY = "chaos-daemons:shadow-legion:fade-to-darkness:reserves"
MALICE_MADE_MANIFEST_ENHANCEMENT_ID = "000009980005"
MALICE_MADE_MANIFEST_SOURCE_ROW_ID = "enhancement:chaos-daemons:shadow-legion:000009980005"
MALICE_MADE_MANIFEST_ENHANCEMENT_DESCRIPTOR_ID = f"phase17e:{MALICE_MADE_MANIFEST_SOURCE_ROW_ID}"
MALICE_MADE_MANIFEST_SOURCE_RULE_ID = (
    "phase17f:phase17e:enhancement:chaos-daemons:shadow-legion:000009980005"
)
MALICE_MADE_MANIFEST_MORTAL_WOUNDS_ABILITY = (
    "chaos-daemons:shadow-legion:malice-made-manifest:mortal-wounds"
)
MALICE_MADE_MANIFEST_MORTAL_WOUNDS_SOURCE_KIND = (
    "chaos_daemons_shadow_legion_malice_made_manifest_mortal_wounds"
)
SPITEFUL_DEMISE_STRATAGEM_ID = "000009979002"
CHANNELLED_WRATH_STRATAGEM_ID = "000009979003"
DEATH_DENIED_STRATAGEM_ID = "000009979004"
ENCROACHING_DARKNESS_STRATAGEM_ID = "000009979005"
SHADE_PATH_STRATAGEM_ID = "000009979006"
BINDING_SHADOW_STRATAGEM_ID = "000009979007"
SHADOW_LEGION_STRATAGEM_IDS = (
    SPITEFUL_DEMISE_STRATAGEM_ID,
    CHANNELLED_WRATH_STRATAGEM_ID,
    DEATH_DENIED_STRATAGEM_ID,
    ENCROACHING_DARKNESS_STRATAGEM_ID,
    SHADE_PATH_STRATAGEM_ID,
    BINDING_SHADOW_STRATAGEM_ID,
)
SPITEFUL_DEMISE_SOURCE_ROW_ID = (
    f"stratagem:chaos-daemons:shadow-legion:{SPITEFUL_DEMISE_STRATAGEM_ID}"
)
CHANNELLED_WRATH_SOURCE_ROW_ID = (
    f"stratagem:chaos-daemons:shadow-legion:{CHANNELLED_WRATH_STRATAGEM_ID}"
)
DEATH_DENIED_SOURCE_ROW_ID = f"stratagem:chaos-daemons:shadow-legion:{DEATH_DENIED_STRATAGEM_ID}"
ENCROACHING_DARKNESS_SOURCE_ROW_ID = (
    f"stratagem:chaos-daemons:shadow-legion:{ENCROACHING_DARKNESS_STRATAGEM_ID}"
)
SHADE_PATH_SOURCE_ROW_ID = f"stratagem:chaos-daemons:shadow-legion:{SHADE_PATH_STRATAGEM_ID}"
BINDING_SHADOW_SOURCE_ROW_ID = (
    f"stratagem:chaos-daemons:shadow-legion:{BINDING_SHADOW_STRATAGEM_ID}"
)
SHADOW_LEGION_STRATAGEM_SOURCE_ROW_IDS = (
    SPITEFUL_DEMISE_SOURCE_ROW_ID,
    CHANNELLED_WRATH_SOURCE_ROW_ID,
    DEATH_DENIED_SOURCE_ROW_ID,
    ENCROACHING_DARKNESS_SOURCE_ROW_ID,
    SHADE_PATH_SOURCE_ROW_ID,
    BINDING_SHADOW_SOURCE_ROW_ID,
)
SHADOW_LEGION_STRATAGEM_DESCRIPTOR_IDS = tuple(
    f"phase17e:{source_row_id}" for source_row_id in SHADOW_LEGION_STRATAGEM_SOURCE_ROW_IDS
)
SHADOW_LEGION_STRATAGEM_PROFILE_IDS = tuple(
    f"phase17s:stratagem:chaos-daemons:shadow-legion:{stratagem_id}"
    for stratagem_id in SHADOW_LEGION_STRATAGEM_IDS
)
SHADOW_LEGION_SELECTED_COMPANION_UNIT_EFFECT_SELECTION_KIND = "selected_friendly_companion_unit"
SHADOW_LEGION_SELECTED_COMPANION_UNIT_CONTEXT_KEY = "companion_unit_instance_id"
SHADOW_LEGION_CHARGING_UNIT_CONTEXT_KEY = "charging_unit_instance_id"
SHADOW_LEGION_DESTROYED_LAST_MODEL_CONTEXT_KEY = "destroyed_last_model_instance_id"
SHADOW_LEGION_ENGAGED_ENEMY_UNITS_CONTEXT_KEY = "engaged_enemy_unit_instance_ids"


class ShadowLegionIrSupportError(ValueError):
    """Raised when static Shadow Legion RuleIR support metadata is inconsistent."""


def coverage_rule_ir_payload_by_descriptor_id(
    coverage_descriptor_id: str,
) -> RuleIRPayload | None:
    return _COVERAGE_RULE_IR_PAYLOADS_BY_DESCRIPTOR_ID.get(coverage_descriptor_id)


def coverage_rule_ir_hash_by_descriptor_id(coverage_descriptor_id: str) -> str | None:
    payload = coverage_rule_ir_payload_by_descriptor_id(coverage_descriptor_id)
    if payload is None:
        return None
    return payload["ir_hash"]


def stratagem_activation_rule_ir_payload_by_profile_id(
    profile_id: str,
) -> RuleIRPayload | None:
    return _STRATAGEM_ACTIVATION_RULE_IR_PAYLOADS_BY_PROFILE_ID.get(profile_id)


def supported_coverage_descriptor_ids() -> tuple[str, ...]:
    return tuple(sorted(_COVERAGE_RULE_IR_PAYLOADS_BY_DESCRIPTOR_ID))


def supported_stratagem_profile_ids() -> tuple[str, ...]:
    return tuple(sorted(_STRATAGEM_ACTIVATION_RULE_IR_PAYLOADS_BY_PROFILE_ID))


def _detachment_rule_payload() -> RuleIRPayload:
    source_row_id = "chaos-daemons:shadow-legion:rule"
    normalized_text = (
        "Shadow Legion Khorne units can shoot and declare a charge in a turn in which "
        "they Advanced. Each time an attack targets a Shadow Legion Tzeentch unit, "
        "subtract 1 from the Hit roll for Shooting phase ranged attacks. Each time an "
        "attack targets a Shadow Legion Tzeentch unit, subtract 1 from the Hit roll for "
        "melee attacks. "
        "Each time an attack targets a Shadow Legion Nurgle unit, subtract 1 from the "
        "Wound roll if the Strength characteristic of that attack is greater than the "
        "Toughness characteristic of that unit. Enemy units cannot target Shadow Legion "
        "Slaanesh units with Snap Shooting attacks. Each time a Shadow Legion Undivided unit "
        "is selected to shoot or fight, it can make a Dark Pact to gain Lethal Hits until "
        "the end of the phase. Each time a Shadow Legion Undivided unit is selected to "
        "shoot or fight, it can make a Dark Pact to gain Sustained Hits 1 until the end "
        "of the phase."
    )
    return _coverage_payload(
        source_row_id,
        normalized_text,
        (
            _ability_clause(
                clause_id=_coverage_clause_id(source_row_id, "effect:001"),
                normalized_text=normalized_text,
                source_text=(
                    "Shadow Legion Khorne units can shoot and declare a charge in a turn in "
                    "which they Advanced."
                ),
                effect_text="can shoot and declare a charge in a turn in which they Advanced",
                ability=CAN_ADVANCE_AND_SHOOT_AND_CHARGE_ABILITY,
                required_keyword_sequence=(SHADOW_LEGION_KEYWORD, KHORNE_KEYWORD),
            ),
            _dice_modifier_clause(
                clause_id=_coverage_clause_id(source_row_id, "effect:002"),
                normalized_text=normalized_text,
                source_text=(
                    "Each time an attack targets a Shadow Legion Tzeentch unit, subtract 1 "
                    "from the Hit roll for Shooting phase ranged attacks"
                ),
                effect_text="subtract 1 from the Hit roll",
                roll_type="hit",
                delta=-1,
                required_keyword_sequence=(SHADOW_LEGION_KEYWORD, TZEENTCH_KEYWORD),
                extra_parameters=(
                    _parameter("attack_role", "target"),
                    _parameter("source_phase", "shooting"),
                    _parameter("weapon_scope", "ranged"),
                ),
            ),
            _dice_modifier_clause(
                clause_id=_coverage_clause_id(source_row_id, "effect:003"),
                normalized_text=normalized_text,
                source_text=(
                    "Each time an attack targets a Shadow Legion Tzeentch unit, subtract 1 "
                    "from the Hit roll for melee attacks"
                ),
                effect_text="subtract 1 from the Hit roll",
                roll_type="hit",
                delta=-1,
                required_keyword_sequence=(SHADOW_LEGION_KEYWORD, TZEENTCH_KEYWORD),
                extra_parameters=(
                    _parameter("attack_role", "target"),
                    _parameter("weapon_scope", "melee"),
                ),
            ),
            _dice_modifier_clause(
                clause_id=_coverage_clause_id(source_row_id, "effect:004"),
                normalized_text=normalized_text,
                source_text=(
                    "Each time an attack targets a Shadow Legion Nurgle unit, subtract 1 "
                    "from the Wound roll if the Strength characteristic of that attack is "
                    "greater than the Toughness characteristic of that unit."
                ),
                effect_text="subtract 1 from the Wound roll",
                roll_type="wound",
                delta=-1,
                required_keyword_sequence=(SHADOW_LEGION_KEYWORD, NURGLE_KEYWORD),
                extra_parameters=(
                    _parameter("attack_role", "target"),
                    _parameter(
                        "target_constraint",
                        "attack_strength_greater_than_target_toughness",
                    ),
                ),
            ),
            _ability_clause(
                clause_id=_coverage_clause_id(source_row_id, "effect:005"),
                normalized_text=normalized_text,
                source_text=(
                    "Enemy units cannot target Shadow Legion Slaanesh units with Snap "
                    "Shooting attacks."
                ),
                effect_text="cannot target Shadow Legion Slaanesh units with Snap Shooting",
                ability=SNAP_SHOOTING_TARGET_FORBIDDEN_ABILITY,
                required_keyword_sequence=(SHADOW_LEGION_KEYWORD, SLAANESH_KEYWORD),
            ),
            _ability_clause(
                clause_id=_coverage_clause_id(source_row_id, "effect:006"),
                normalized_text=normalized_text,
                source_text=(
                    "Each time a Shadow Legion Undivided unit is selected to shoot or fight, "
                    "it can make a Dark Pact to gain Lethal Hits until the end of the phase."
                ),
                effect_text="make a Dark Pact to gain Lethal Hits",
                ability=SHADOW_LEGION_DARK_PACT_LETHAL_HITS_CHOICE_ABILITY,
                required_keyword_sequence=(SHADOW_LEGION_KEYWORD, UNDIVIDED_KEYWORD),
            ),
            _ability_clause(
                clause_id=_coverage_clause_id(source_row_id, "effect:007"),
                normalized_text=normalized_text,
                source_text=(
                    "Each time a Shadow Legion Undivided unit is selected to shoot or fight, "
                    "it can make a Dark Pact to gain Sustained Hits 1 until the end of the phase."
                ),
                effect_text="make a Dark Pact to gain Sustained Hits 1",
                ability=SHADOW_LEGION_DARK_PACT_SUSTAINED_HITS_1_CHOICE_ABILITY,
                required_keyword_sequence=(SHADOW_LEGION_KEYWORD, UNDIVIDED_KEYWORD),
            ),
        ),
    )


def _leaping_shadows_payload() -> RuleIRPayload:
    normalized_text = "Shadow Legion bearer grants Scouts 9 to its attached rules unit."
    effect_text = "grants Scouts 9 to its attached rules unit"
    return _enhancement_ability_payload(
        source_row_id=LEAPING_SHADOWS_SOURCE_ROW_ID,
        normalized_text=normalized_text,
        source_text=effect_text,
        effect_text=effect_text,
        ability=LEAPING_SHADOWS_SCOUTS_ABILITY,
        hook_family="enhancement_effect",
    )


def _mantle_of_gloom_payload() -> RuleIRPayload:
    normalized_text = (
        "Shadow Legion bearer reduces Objective Control by 1 for enemy units within "
        "Engagement Range of its attached rules unit."
    )
    effect_text = "reduces Objective Control by 1 for enemy units within Engagement Range"
    return _enhancement_ability_payload(
        source_row_id=MANTLE_OF_GLOOM_SOURCE_ROW_ID,
        normalized_text=normalized_text,
        source_text=effect_text,
        effect_text=effect_text,
        ability=MANTLE_OF_GLOOM_OBJECTIVE_CONTROL_ABILITY,
        hook_family="objective_control_modifier",
    )


def _fade_to_darkness_payload() -> RuleIRPayload:
    normalized_text = (
        "Shadow Legion bearer can enter Strategic Reserves at the end of the Fight phase "
        "after destroying one or more enemy units."
    )
    effect_text = "can enter Strategic Reserves at the end of the Fight phase"
    return _enhancement_ability_payload(
        source_row_id=FADE_TO_DARKNESS_SOURCE_ROW_ID,
        normalized_text=normalized_text,
        source_text=effect_text,
        effect_text=effect_text,
        ability=FADE_TO_DARKNESS_RESERVES_ABILITY,
        hook_family="turn_end",
    )


def _malice_made_manifest_payload() -> RuleIRPayload:
    normalized_text = (
        "At the start of the Fight phase, Shadow Legion bearer can select an enemy unit "
        "within Engagement Range and roll one D6 to inflict mortal wounds."
    )
    effect_text = "select an enemy unit within Engagement Range and roll one D6"
    return _enhancement_ability_payload(
        source_row_id=MALICE_MADE_MANIFEST_SOURCE_ROW_ID,
        normalized_text=normalized_text,
        source_text=effect_text,
        effect_text=effect_text,
        ability=MALICE_MADE_MANIFEST_MORTAL_WOUNDS_ABILITY,
        hook_family="fight_phase_start",
    )


def _stratagem_coverage_payload(stratagem_id: str) -> RuleIRPayload:
    source_row_id = f"stratagem:chaos-daemons:shadow-legion:{stratagem_id}"
    rule_id = f"{SOURCE_PACKAGE_ID}:phase17e:{source_row_id}:source-text"
    return _stratagem_payload_by_id(stratagem_id, rule_id=rule_id, source_id=rule_id)


def _stratagem_activation_payload(profile_id: str) -> RuleIRPayload:
    stratagem_id = profile_id.rsplit(":", maxsplit=1)[-1]
    source_id = (
        f"{STRATAGEM_SOURCE_PACKAGE_ID}:stratagem:chaos-daemons:shadow-legion:{stratagem_id}"
    )
    return _stratagem_payload_by_id(stratagem_id, rule_id=profile_id, source_id=source_id)


def _stratagem_payload_by_id(
    stratagem_id: str,
    *,
    rule_id: str,
    source_id: str,
) -> RuleIRPayload:
    if stratagem_id == SPITEFUL_DEMISE_STRATAGEM_ID:
        return _spiteful_demise_payload(rule_id=rule_id, source_id=source_id)
    if stratagem_id == CHANNELLED_WRATH_STRATAGEM_ID:
        return _channelled_wrath_payload(rule_id=rule_id, source_id=source_id)
    if stratagem_id == DEATH_DENIED_STRATAGEM_ID:
        return _death_denied_payload(rule_id=rule_id, source_id=source_id)
    if stratagem_id == ENCROACHING_DARKNESS_STRATAGEM_ID:
        return _encroaching_darkness_payload(rule_id=rule_id, source_id=source_id)
    if stratagem_id == SHADE_PATH_STRATAGEM_ID:
        return _shade_path_payload(rule_id=rule_id, source_id=source_id)
    if stratagem_id == BINDING_SHADOW_STRATAGEM_ID:
        return _binding_shadow_payload(rule_id=rule_id, source_id=source_id)
    raise ShadowLegionIrSupportError("Unsupported Shadow Legion Stratagem id.")


def _spiteful_demise_payload(*, rule_id: str, source_id: str) -> RuleIRPayload:
    normalized_text = (
        "stratagem_activation_target_binding\n"
        "Roll one D6 for each enemy unit that is within Engagement Range of the last model "
        "in your unit, adding 2 to the result if your unit has the Slaanesh keyword: on a "
        "4-5, that enemy unit suffers D3 mortal wounds; on a 6+, that enemy unit suffers "
        "3 mortal wounds."
    )
    effect_text = (
        "Roll one D6 for each enemy unit that is within Engagement Range of the last model "
        "in your unit"
    )
    return _payload(
        rule_id,
        source_id,
        normalized_text,
        (
            _stratagem_target_binding_clause(rule_id, normalized_text),
            _effect_clause(
                clause_id=f"{rule_id}:effect:001",
                template_id="phase17c:timing-window",
                normalized_text=normalized_text,
                source_text=normalized_text.split("\n", maxsplit=1)[1],
                target=None,
                effects=(
                    _effect(
                        "inflict_mortal_wounds",
                        normalized_text,
                        effect_text,
                        (
                            _parameter("resolution_kind", "roll_per_engaged_enemy_unit"),
                            _parameter(
                                "source_model_context_key",
                                SHADOW_LEGION_DESTROYED_LAST_MODEL_CONTEXT_KEY,
                            ),
                            _parameter(
                                "target_unit_context_key",
                                SHADOW_LEGION_ENGAGED_ENEMY_UNITS_CONTEXT_KEY,
                            ),
                            _parameter("roll_type", "spiteful_demise_mortal_wounds"),
                            _parameter("roll_quantity", 1),
                            _parameter("roll_sides", 6),
                            _parameter("bonus_if_source_has_keyword", SLAANESH_KEYWORD),
                            _parameter("bonus", 2),
                            _parameter("mortal_wounds_on_4_5", "D3"),
                            _parameter("mortal_wounds_on_6_plus", 3),
                            _parameter("spill_over", True),
                            _parameter("replay_effect_kind", "shadow_legion_spiteful_demise"),
                        ),
                    ),
                ),
                duration=None,
            ),
        ),
        _stratagem_parser_version(),
    )


def _channelled_wrath_payload(*, rule_id: str, source_id: str) -> RuleIRPayload:
    normalized_text = (
        "stratagem_activation_target_binding\n"
        "Until the end of the phase, melee weapons equipped by models in your unit have "
        "the [LANCE] ability. If your unit has the Khorne keyword, until the end of the "
        "phase, improve the Armour Penetration characteristic of those weapons by 1 as well."
    )
    duration = _end_phase_duration(normalized_text)
    return _payload(
        rule_id,
        source_id,
        normalized_text,
        (
            _stratagem_target_binding_clause(rule_id, normalized_text),
            _weapon_ability_clause(
                clause_id=f"{rule_id}:effect:001",
                normalized_text=normalized_text,
                source_text=(
                    "melee weapons equipped by models in your unit have the [LANCE] ability"
                ),
                effect_text=(
                    "melee weapons equipped by models in your unit have the [LANCE] ability"
                ),
                weapon_ability="Lance",
                weapon_scope="melee",
                duration=duration,
            ),
            _effect_clause(
                clause_id=f"{rule_id}:effect:002",
                template_id=CHARACTERISTIC_MODIFIER_TEMPLATE_ID,
                normalized_text=normalized_text,
                source_text="improve the Armour Penetration characteristic of those weapons by 1",
                target=None,
                effects=(
                    _effect(
                        "modify_characteristic",
                        normalized_text,
                        "improve the Armour Penetration characteristic",
                        (
                            _parameter("characteristic", "armor_penetration"),
                            _parameter("delta", 1),
                            _parameter("weapon_scope", "melee"),
                            _parameter("attack_role", "attacker"),
                            _parameter(
                                "required_keyword_sequence",
                                (SHADOW_LEGION_KEYWORD, KHORNE_KEYWORD),
                            ),
                        ),
                    ),
                ),
                duration=duration,
            ),
        ),
        _stratagem_parser_version(),
    )


def _death_denied_payload(*, rule_id: str, source_id: str) -> RuleIRPayload:
    normalized_text = (
        "stratagem_activation_target_binding\n"
        "One model in your unit regains up to 3 lost wounds. In addition, if your unit "
        "has the Tzeentch keyword, return up to one destroyed model (excluding Character "
        "models) to your unit with its full wounds remaining."
    )
    return _payload(
        rule_id,
        source_id,
        normalized_text,
        (
            _stratagem_target_binding_clause(rule_id, normalized_text),
            _effect_clause(
                clause_id=f"{rule_id}:effect:001",
                template_id=None,
                normalized_text=normalized_text,
                source_text="One model in your unit regains up to 3 lost wounds",
                target=None,
                effects=(
                    _effect(
                        "restore_lost_wounds",
                        normalized_text,
                        "regains up to 3 lost wounds",
                        (
                            _parameter("amount", 3),
                            _parameter("cap", "lost_wounds"),
                            _parameter("target", "one_model_in_target_unit"),
                            _parameter("optional", True),
                            _parameter("selection_actor", "owner"),
                        ),
                    ),
                ),
                duration=None,
            ),
            _effect_clause(
                clause_id=f"{rule_id}:effect:002",
                template_id=RETURN_ON_DEATH_TEMPLATE_ID,
                normalized_text=normalized_text,
                source_text=(
                    "return up to one destroyed model (excluding Character models) to your "
                    "unit with its full wounds remaining"
                ),
                target=None,
                effects=(
                    _effect(
                        "return_destroyed_target",
                        normalized_text,
                        "return up to one destroyed model",
                        (
                            _parameter("target", "one_destroyed_model_in_target_unit"),
                            _parameter("target_scope", "destroyed_model"),
                            _parameter("target_lifecycle", "destroyed"),
                            _parameter("restore_wounds_mode", "full_health"),
                            _parameter("excluded_keyword", CHARACTER_KEYWORD),
                            _parameter(
                                "required_keyword_sequence",
                                (SHADOW_LEGION_KEYWORD, TZEENTCH_KEYWORD),
                            ),
                            _parameter("selection_actor", "owner"),
                        ),
                    ),
                ),
                duration=None,
            ),
        ),
        _stratagem_parser_version(),
    )


def _encroaching_darkness_payload(*, rule_id: str, source_id: str) -> RuleIRPayload:
    normalized_text = (
        "stratagem_activation_target_binding\n"
        "Until the end of the phase, weapons equipped by models in your selected units "
        "have the [IGNORES COVER] ability."
    )
    return _payload(
        rule_id,
        source_id,
        normalized_text,
        (
            _stratagem_target_binding_clause(rule_id, normalized_text),
            _weapon_ability_clause(
                clause_id=f"{rule_id}:effect:001",
                normalized_text=normalized_text,
                source_text=normalized_text.split("\n", maxsplit=1)[1],
                effect_text=(
                    "weapons equipped by models in your selected units have the [IGNORES COVER] "
                    "ability"
                ),
                weapon_ability="Ignores Cover",
                weapon_scope="all",
                duration=_end_phase_duration(normalized_text),
                extra_parameters=(
                    _parameter(
                        "additional_target_unit_context_key",
                        SHADOW_LEGION_SELECTED_COMPANION_UNIT_CONTEXT_KEY,
                    ),
                ),
            ),
        ),
        _stratagem_parser_version(),
    )


def _shade_path_payload(*, rule_id: str, source_id: str) -> RuleIRPayload:
    normalized_text = (
        "stratagem_activation_target_binding\n"
        "Until the end of the phase, subtract 2 from Charge rolls made for that enemy "
        "unit. In addition, if your unit has the Nurgle keyword, that enemy unit must "
        "take a Battle-shock test."
    )
    duration = _end_phase_duration(normalized_text)
    return _payload(
        rule_id,
        source_id,
        normalized_text,
        (
            _stratagem_target_binding_clause(rule_id, normalized_text),
            _effect_clause(
                clause_id=f"{rule_id}:effect:001",
                template_id=DICE_ROLL_MODIFIER_TEMPLATE_ID,
                normalized_text=normalized_text,
                source_text="subtract 2 from Charge rolls made for that enemy unit",
                target=None,
                effects=(
                    _effect(
                        "modify_dice_roll",
                        normalized_text,
                        "subtract 2 from Charge rolls",
                        (
                            _parameter("roll_type", "charge"),
                            _parameter("delta", -2),
                            _parameter(
                                "target_unit_context_key",
                                SHADOW_LEGION_CHARGING_UNIT_CONTEXT_KEY,
                            ),
                            _parameter("replay_effect_kind", "shadow_legion_shade_path"),
                        ),
                    ),
                ),
                duration=duration,
            ),
            _effect_clause(
                clause_id=f"{rule_id}:effect:002",
                template_id=CONTEXTUAL_STATUS_TEMPLATE_ID,
                normalized_text=normalized_text,
                source_text="that enemy unit must take a Battle-shock test",
                target=None,
                effects=(
                    _effect(
                        "set_contextual_status",
                        normalized_text,
                        "must take a Battle-shock test",
                        (
                            _parameter("status", "force_battle_shock_test"),
                            _parameter(
                                "target_unit_context_key",
                                SHADOW_LEGION_CHARGING_UNIT_CONTEXT_KEY,
                            ),
                            _parameter("required_source_keyword", NURGLE_KEYWORD),
                            _parameter("roll_modifier", 0),
                        ),
                    ),
                ),
                duration=None,
            ),
        ),
        _stratagem_parser_version(),
    )


def _binding_shadow_payload(*, rule_id: str, source_id: str) -> RuleIRPayload:
    normalized_text = (
        "stratagem_activation_target_binding\n"
        "Remove those selected units from the battlefield and place them into Strategic Reserves."
    )
    return _payload(
        rule_id,
        source_id,
        normalized_text,
        (
            _stratagem_target_binding_clause(rule_id, normalized_text),
            _effect_clause(
                clause_id=f"{rule_id}:effect:001",
                template_id=PLACEMENT_TEMPLATE_ID,
                normalized_text=normalized_text,
                source_text=normalized_text.split("\n", maxsplit=1)[1],
                target=None,
                effects=(
                    _effect(
                        "placement_permission",
                        normalized_text,
                        "place them into Strategic Reserves",
                        (
                            _parameter("placement_kind", "strategic_reserves"),
                            _parameter("operation", "remove_to_reserves"),
                            _parameter("reserve_origin", "during_battle_stratagem"),
                            _parameter(
                                "additional_target_unit_context_key",
                                SHADOW_LEGION_SELECTED_COMPANION_UNIT_CONTEXT_KEY,
                            ),
                        ),
                    ),
                ),
                duration=None,
            ),
        ),
        _stratagem_parser_version(),
    )


def _enhancement_ability_payload(
    *,
    source_row_id: str,
    normalized_text: str,
    source_text: str,
    effect_text: str,
    ability: str,
    hook_family: str,
) -> RuleIRPayload:
    return _coverage_payload(
        source_row_id,
        normalized_text,
        (
            _keyword_gate_clause(
                clause_id=_coverage_clause_id(source_row_id, "gate:001"),
                normalized_text=normalized_text,
                source_text="Shadow Legion",
                keyword_text="Shadow Legion",
                required_keyword=SHADOW_LEGION_KEYWORD,
            ),
            _ability_clause(
                clause_id=_coverage_clause_id(source_row_id, "effect:001"),
                normalized_text=normalized_text,
                source_text=source_text,
                effect_text=effect_text,
                ability=ability,
                required_keyword_sequence=(SHADOW_LEGION_KEYWORD,),
                extra_parameters=(_parameter("hook_family", hook_family),),
            ),
        ),
    )


def _keyword_gate_clause(
    *,
    clause_id: str,
    normalized_text: str,
    source_text: str,
    keyword_text: str,
    required_keyword: str,
) -> RuleClausePayload:
    return cast(
        RuleClausePayload,
        {
            "clause_id": clause_id,
            "template_id": KEYWORD_GATE_TEMPLATE_ID,
            "source_span": _span(normalized_text, source_text),
            "trigger": None,
            "conditions": [
                _keyword_gate_condition(
                    normalized_text=normalized_text,
                    keyword_text=keyword_text,
                    required_keyword=required_keyword,
                )
            ],
            "target": None,
            "effects": [],
            "duration": None,
            "unsupported_reason": None,
            "diagnostics": [],
        },
    )


def _keyword_gate_condition(
    *,
    normalized_text: str,
    keyword_text: str,
    required_keyword: str,
) -> RuleConditionPayload:
    return cast(
        RuleConditionPayload,
        {
            "kind": "keyword_gate",
            "source_span": _span(normalized_text, keyword_text),
            "parameters": [_parameter("required_keyword", required_keyword)],
        },
    )


def _coverage_payload(
    source_row_id: str,
    normalized_text: str,
    clauses: tuple[RuleClausePayload, ...],
) -> RuleIRPayload:
    source_id = f"{SOURCE_PACKAGE_ID}:phase17e:{source_row_id}:source-text"
    return _payload(
        source_id,
        source_id,
        normalized_text,
        clauses,
        "phase17c-rule-parser-v1",
    )


def _payload(
    rule_id: str,
    source_id: str,
    normalized_text: str,
    clauses: tuple[RuleClausePayload, ...],
    parser_version: str,
) -> RuleIRPayload:
    return RuleIR(
        rule_id=rule_id,
        source_id=source_id,
        normalized_text=normalized_text,
        parser_version=parser_version,
        schema_version="phase17c-rule-ir-v1",
        clauses=tuple(RuleClause.from_payload(clause) for clause in clauses),
        diagnostics=(),
    ).to_payload()


def _ability_clause(
    *,
    clause_id: str,
    normalized_text: str,
    source_text: str,
    effect_text: str,
    ability: str,
    required_keyword_sequence: tuple[str, ...],
    extra_parameters: tuple[RuleParameterPayload, ...] = (),
) -> RuleClausePayload:
    return _effect_clause(
        clause_id=clause_id,
        template_id=GRANT_ABILITY_TEMPLATE_ID,
        normalized_text=normalized_text,
        source_text=source_text,
        target=_target("this_unit", normalized_text, source_text),
        effects=(
            _effect(
                "grant_ability",
                normalized_text,
                effect_text,
                (
                    _parameter("ability", ability),
                    _parameter("required_keyword_sequence", required_keyword_sequence),
                    *extra_parameters,
                ),
            ),
        ),
        duration=_permanent_duration(normalized_text),
    )


def _dice_modifier_clause(
    *,
    clause_id: str,
    normalized_text: str,
    source_text: str,
    effect_text: str,
    roll_type: str,
    delta: int,
    required_keyword_sequence: tuple[str, ...],
    extra_parameters: tuple[RuleParameterPayload, ...],
) -> RuleClausePayload:
    return _effect_clause(
        clause_id=clause_id,
        template_id=DICE_ROLL_MODIFIER_TEMPLATE_ID,
        normalized_text=normalized_text,
        source_text=source_text,
        target=_target("this_unit", normalized_text, source_text),
        effects=(
            _effect(
                "modify_dice_roll",
                normalized_text,
                effect_text,
                (
                    _parameter("roll_type", roll_type),
                    _parameter("delta", delta),
                    _parameter("required_keyword_sequence", required_keyword_sequence),
                    *extra_parameters,
                ),
            ),
        ),
        duration=_permanent_duration(normalized_text),
    )


def _effect_clause(
    *,
    clause_id: str,
    template_id: str | None,
    normalized_text: str,
    source_text: str,
    target: RuleTargetSpecPayload | None,
    effects: tuple[RuleEffectSpecPayload, ...],
    duration: RuleDurationPayload | None,
) -> RuleClausePayload:
    return cast(
        RuleClausePayload,
        {
            "clause_id": clause_id,
            "template_id": template_id,
            "source_span": _span(normalized_text, source_text),
            "trigger": None,
            "conditions": [],
            "target": target,
            "effects": list(effects),
            "duration": duration,
            "unsupported_reason": None,
            "diagnostics": [],
        },
    )


def _stratagem_target_binding_clause(
    rule_id: str,
    normalized_text: str,
) -> RuleClausePayload:
    return cast(
        RuleClausePayload,
        {
            "clause_id": f"{rule_id}:target-binding",
            "template_id": STRATAGEM_TARGET_BINDING_TEMPLATE_ID,
            "source_span": _span(normalized_text, "stratagem_activation_target_binding"),
            "trigger": None,
            "conditions": [],
            "target": _target(
                "friendly_unit",
                normalized_text,
                "stratagem_activation_target_binding",
            ),
            "effects": [],
            "duration": None,
            "unsupported_reason": None,
            "diagnostics": [],
        },
    )


def _weapon_ability_clause(
    *,
    clause_id: str,
    normalized_text: str,
    source_text: str,
    effect_text: str,
    weapon_ability: str,
    weapon_scope: str,
    duration: RuleDurationPayload,
    extra_parameters: tuple[RuleParameterPayload, ...] = (),
) -> RuleClausePayload:
    return _effect_clause(
        clause_id=clause_id,
        template_id=WEAPON_ABILITY_GRANT_TEMPLATE_ID,
        normalized_text=normalized_text,
        source_text=source_text,
        target=None,
        effects=(
            _effect(
                "grant_weapon_ability",
                normalized_text,
                effect_text,
                (
                    _parameter("weapon_ability", weapon_ability),
                    _parameter("weapon_scope", weapon_scope),
                    *extra_parameters,
                ),
            ),
        ),
        duration=duration,
    )


def _effect(
    kind: str,
    normalized_text: str,
    source_text: str,
    parameters: tuple[RuleParameterPayload, ...],
) -> RuleEffectSpecPayload:
    return cast(
        RuleEffectSpecPayload,
        {
            "kind": kind,
            "source_span": _span(normalized_text, source_text),
            "parameters": list(parameters),
        },
    )


def _target(
    kind: str,
    normalized_text: str,
    source_text: str,
) -> RuleTargetSpecPayload:
    return cast(
        RuleTargetSpecPayload,
        {
            "kind": kind,
            "source_span": _span(normalized_text, source_text),
            "parameters": [],
        },
    )


def _permanent_duration(normalized_text: str) -> RuleDurationPayload:
    return cast(
        RuleDurationPayload,
        {
            "kind": "permanent",
            "source_span": _span(normalized_text, normalized_text),
            "parameters": [],
        },
    )


def _end_phase_duration(normalized_text: str) -> RuleDurationPayload:
    return cast(
        RuleDurationPayload,
        {
            "kind": "until_timing_endpoint",
            "source_span": _span(normalized_text, "Until the end of the phase"),
            "parameters": [_parameter("endpoint", "phase")],
        },
    )


def _parameter(key: str, value: object) -> RuleParameterPayload:
    return cast(RuleParameterPayload, {"key": key, "value": value})


def _span(normalized_text: str, source_text: str) -> dict[str, str | int]:
    start = normalized_text.index(source_text)
    return {"text": source_text, "start": start, "end": start + len(source_text)}


def _coverage_clause_id(source_row_id: str, suffix: str) -> str:
    return f"{SOURCE_PACKAGE_ID}:phase17e:{source_row_id}:source-text:{suffix}"


def _stratagem_parser_version() -> str:
    return "phase17s-stratagem-activation-template-v2"


def _coverage_payloads() -> Mapping[str, RuleIRPayload]:
    payloads = {
        SHADOW_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID: _detachment_rule_payload(),
        LEAPING_SHADOWS_ENHANCEMENT_DESCRIPTOR_ID: _leaping_shadows_payload(),
        MANTLE_OF_GLOOM_ENHANCEMENT_DESCRIPTOR_ID: _mantle_of_gloom_payload(),
        FADE_TO_DARKNESS_ENHANCEMENT_DESCRIPTOR_ID: _fade_to_darkness_payload(),
        MALICE_MADE_MANIFEST_ENHANCEMENT_DESCRIPTOR_ID: _malice_made_manifest_payload(),
    }
    for descriptor_id in SHADOW_LEGION_STRATAGEM_DESCRIPTOR_IDS:
        payloads[descriptor_id] = _stratagem_coverage_payload(
            descriptor_id.rsplit(":", maxsplit=1)[-1]
        )
    return MappingProxyType(payloads)


def _stratagem_activation_payloads() -> Mapping[str, RuleIRPayload]:
    return MappingProxyType(
        {
            profile_id: _stratagem_activation_payload(profile_id)
            for profile_id in SHADOW_LEGION_STRATAGEM_PROFILE_IDS
        }
    )


_COVERAGE_RULE_IR_PAYLOADS_BY_DESCRIPTOR_ID = _coverage_payloads()
_STRATAGEM_ACTIVATION_RULE_IR_PAYLOADS_BY_PROFILE_ID = _stratagem_activation_payloads()
