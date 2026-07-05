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
    RuleTriggerPayload,
)
from warhammer40k_core.rules.rule_templates import (
    CHARACTERISTIC_MODIFIER_TEMPLATE_ID,
    DICE_ROLL_MODIFIER_TEMPLATE_ID,
    GRANT_ABILITY_TEMPLATE_ID,
    KEYWORD_GATE_TEMPLATE_ID,
    MOVEMENT_DISTANCE_TEMPLATE_ID,
    REROLL_PERMISSION_TEMPLATE_ID,
)

SOURCE_PACKAGE_ID = "gw-11e-phase17e-faction-coverage-2026-27"
STRATAGEM_SOURCE_PACKAGE_ID = "gw-11e-phase17e-exact-faction-subrules-2026-27"
STRATAGEM_TARGET_BINDING_TEMPLATE_ID = "phase17s:stratagem-activation-target-binding"

EMPERORS_CHILDREN_KEYWORD = "EMPEROR'S CHILDREN"
DAEMON_KEYWORD = "DAEMON"
DAEMON_PRINCE_KEYWORD = "DAEMON PRINCE"
FULGRIM_KEYWORD = "FULGRIM"
LORD_EXULTANT_KEYWORD = "LORD EXULTANT"
CHARACTER_KEYWORD = "CHARACTER"
TRIGGERED_NORMAL_MOVE_ABILITY = "triggered_normal_move"

COURT_OF_THE_PHOENICIAN_DETACHMENT_RULE_DESCRIPTOR_ID = (
    "phase17e:emperors-children:court-of-the-phoenician:rule"
)
COURT_OF_THE_PHOENICIAN_ENHANCEMENT_DESCRIPTOR_IDS = (
    "phase17e:enhancement:emperors-children:court-of-the-phoenician:000010654002",
    "phase17e:enhancement:emperors-children:court-of-the-phoenician:000010654003",
    "phase17e:enhancement:emperors-children:court-of-the-phoenician:000010654004",
    "phase17e:enhancement:emperors-children:court-of-the-phoenician:000010654005",
)
COURT_OF_THE_PHOENICIAN_STRATAGEM_DESCRIPTOR_IDS = (
    "phase17e:stratagem:emperors-children:court-of-the-phoenician:000010655002",
    "phase17e:stratagem:emperors-children:court-of-the-phoenician:000010655003",
    "phase17e:stratagem:emperors-children:court-of-the-phoenician:000010655004",
    "phase17e:stratagem:emperors-children:court-of-the-phoenician:000010655005",
    "phase17e:stratagem:emperors-children:court-of-the-phoenician:000010655006",
    "phase17e:stratagem:emperors-children:court-of-the-phoenician:000010655007",
)
COURT_OF_THE_PHOENICIAN_STRATAGEM_PROFILE_IDS = (
    "phase17s:stratagem:emperors-children:court-of-the-phoenician:000010655002",
    "phase17s:stratagem:emperors-children:court-of-the-phoenician:000010655003",
    "phase17s:stratagem:emperors-children:court-of-the-phoenician:000010655004",
    "phase17s:stratagem:emperors-children:court-of-the-phoenician:000010655005",
    "phase17s:stratagem:emperors-children:court-of-the-phoenician:000010655006",
    "phase17s:stratagem:emperors-children:court-of-the-phoenician:000010655007",
)


class CourtOfThePhoenicianIrSupportError(ValueError):
    """Raised when static Court of the Phoenician RuleIR metadata is inconsistent."""


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
    source_row_id = "emperors-children:court-of-the-phoenician:rule"
    sensational = (
        "Sensational Performance: Each time this unit is selected to fight, if this unit "
        "made a Charge move this turn, it can use this ability. If it does, until the end "
        "of the phase: this unit cannot target a unit it was within Engagement Range of at "
        "the start of the turn; this unit cannot target a unit that was the target of another "
        "unit's attack this phase; improve the Strength and Armour Penetration characteristics "
        "of this unit's melee weapons by 1."
    )
    master = (
        "Master of the Pageant: Once per battle round, when you target a Fulgrim unit from "
        "your army with the Sinuous Breach or Prideful Superiority Stratagem, you can reduce "
        "the CP cost of that use of that Stratagem by 1CP."
    )
    normalized_text = f"{sensational} {master}"
    clauses = (
        _ability_clause(
            clause_id=_coverage_clause_id(source_row_id, "effect:001"),
            template_id=GRANT_ABILITY_TEMPLATE_ID,
            normalized_text=normalized_text,
            source_text=sensational,
            target_kind="friendly_unit",
            target_text="this unit",
            effect_text="Sensational Performance",
            ability="sensational_performance",
            duration=_permanent_duration(normalized_text),
            extra_parameters=(
                _parameter("required_faction_keyword", EMPERORS_CHILDREN_KEYWORD),
                _parameter("activation_timing", "unit_selected_to_fight"),
                _parameter("requires_charge_move_this_turn", True),
                _parameter("forbidden_target_engaged_at_turn_start", True),
                _parameter("forbidden_target_attacked_by_another_unit_this_phase", True),
            ),
        ),
        _characteristic_modifier_clause(
            clause_id=_coverage_clause_id(source_row_id, "effect:002"),
            normalized_text=normalized_text,
            source_text=(
                "improve the Strength and Armour Penetration characteristics of this unit's "
                "melee weapons by 1"
            ),
            effect_text="improve the Strength",
            characteristic="strength",
            delta=1,
            weapon_scope="melee",
            duration=_end_phase_duration(normalized_text),
            extra_parameters=(
                _parameter("ability_required", "sensational_performance"),
                _parameter("requires_charge_move_this_turn", True),
            ),
        ),
        _characteristic_modifier_clause(
            clause_id=_coverage_clause_id(source_row_id, "effect:003"),
            normalized_text=normalized_text,
            source_text=(
                "improve the Strength and Armour Penetration characteristics of this unit's "
                "melee weapons by 1"
            ),
            effect_text="Armour Penetration",
            characteristic="armor_penetration",
            delta=1,
            weapon_scope="melee",
            duration=_end_phase_duration(normalized_text),
            extra_parameters=(
                _parameter("ability_required", "sensational_performance"),
                _parameter("requires_charge_move_this_turn", True),
            ),
        ),
        _ability_clause(
            clause_id=_coverage_clause_id(source_row_id, "effect:004"),
            template_id=GRANT_ABILITY_TEMPLATE_ID,
            normalized_text=normalized_text,
            source_text=master,
            target_kind="player",
            target_text="you",
            effect_text="reduce the CP cost of that use of that Stratagem by 1CP",
            ability="stratagem_cp_cost_reduction",
            duration=_permanent_duration(normalized_text),
            extra_parameters=(
                _parameter("cost_reduction", 1),
                _parameter("frequency", "once_per_battle_round"),
                _parameter("required_target_keyword", FULGRIM_KEYWORD),
                _parameter(
                    "stratagem_ids",
                    (
                        "000010655003",
                        "000010655004",
                    ),
                ),
            ),
        ),
    )
    return _coverage_payload(source_row_id, normalized_text, clauses)


def _tears_of_the_phoenix_payload() -> RuleIRPayload:
    source_row_id = "enhancement:emperors-children:court-of-the-phoenician:000010654002"
    normalized_text = (
        "EMPEROR'S CHILDREN model only. Each time a model in the bearer's unit makes a melee "
        "attack, you can ignore any or all modifiers to that attack's Weapon Skill "
        "characteristic and any or all modifiers to the Hit roll and Wound roll."
    )
    clauses = (
        _keyword_gate_clause(
            clause_id=_coverage_clause_id(source_row_id, "gate:001"),
            normalized_text=normalized_text,
            source_text="EMPEROR'S CHILDREN model only",
            keyword_text="EMPEROR'S CHILDREN",
            required_keyword=EMPERORS_CHILDREN_KEYWORD,
        ),
        _ability_clause(
            clause_id=_coverage_clause_id(source_row_id, "effect:001"),
            template_id=GRANT_ABILITY_TEMPLATE_ID,
            normalized_text=normalized_text,
            source_text=(
                "Each time a model in the bearer's unit makes a melee attack, you can ignore "
                "any or all modifiers to that attack's Weapon Skill characteristic and any or "
                "all modifiers to the Hit roll and Wound roll."
            ),
            target_kind="this_unit",
            target_text="bearer's unit",
            effect_text="ignore any or all modifiers",
            ability="ignore_melee_attack_ws_hit_wound_modifiers",
            duration=None,
            extra_parameters=(
                _parameter("attack_scope", "melee"),
                _parameter("characteristics", ("weapon_skill",)),
                _parameter("roll_types", ("hit", "wound")),
            ),
        ),
    )
    return _coverage_payload(source_row_id, normalized_text, clauses)


def _exalted_patron_payload() -> RuleIRPayload:
    source_row_id = "enhancement:emperors-children:court-of-the-phoenician:000010654003"
    normalized_text = (
        "LORD EXULTANT model only. Add 1 inch to the Move characteristic of the bearer. "
        "In the Declare Battle Formations step, the bearer can be attached to a Flawless "
        "Blades unit."
    )
    clauses = (
        _keyword_gate_clause(
            clause_id=_coverage_clause_id(source_row_id, "gate:001"),
            normalized_text=normalized_text,
            source_text="LORD EXULTANT model only",
            keyword_text="LORD EXULTANT",
            required_keyword=LORD_EXULTANT_KEYWORD,
        ),
        _move_modifier_clause(
            clause_id=_coverage_clause_id(source_row_id, "effect:001"),
            normalized_text=normalized_text,
            source_text="Add 1 inch to the Move characteristic of the bearer.",
            target_kind="this_model",
            target_text="bearer",
            effect_text="Add 1 inch to the Move characteristic",
            delta=1,
            duration=None,
        ),
        _ability_clause(
            clause_id=_coverage_clause_id(source_row_id, "effect:002"),
            template_id=GRANT_ABILITY_TEMPLATE_ID,
            normalized_text=normalized_text,
            source_text=(
                "In the Declare Battle Formations step, the bearer can be attached to a "
                "Flawless Blades unit."
            ),
            target_kind="this_model",
            target_text="bearer",
            effect_text="can be attached to a Flawless Blades unit",
            ability="may_attach_to_flawless_blades",
            duration=None,
            extra_parameters=(
                _parameter("timing_step", "declare_battle_formations"),
                _parameter("allowed_bodyguard_keyword", "FLAWLESS BLADES"),
            ),
        ),
    )
    return _coverage_payload(source_row_id, normalized_text, clauses)


def _soulstain_made_manifest_payload() -> RuleIRPayload:
    source_row_id = "enhancement:emperors-children:court-of-the-phoenician:000010654004"
    normalized_text = (
        "EMPEROR'S CHILDREN model only. At the start of the Fight phase, you can select one "
        "enemy unit within Engagement Range of the bearer; that unit must take a "
        "Battle-shock test, subtracting 1 from the result."
    )
    clauses = (
        _keyword_gate_clause(
            clause_id=_coverage_clause_id(source_row_id, "gate:001"),
            normalized_text=normalized_text,
            source_text="EMPEROR'S CHILDREN model only",
            keyword_text="EMPEROR'S CHILDREN",
            required_keyword=EMPERORS_CHILDREN_KEYWORD,
        ),
        _ability_clause(
            clause_id=_coverage_clause_id(source_row_id, "effect:001"),
            template_id=GRANT_ABILITY_TEMPLATE_ID,
            normalized_text=normalized_text,
            source_text=(
                "At the start of the Fight phase, you can select one enemy unit within "
                "Engagement Range of the bearer; that unit must take a Battle-shock test, "
                "subtracting 1 from the result."
            ),
            target_kind="this_model",
            target_text="bearer",
            effect_text="that unit must take a Battle-shock test",
            ability="start_fight_enemy_engagement_battleshock",
            duration=None,
            extra_parameters=(
                _parameter("timing", "start_fight_phase"),
                _parameter("target_allegiance", "enemy"),
                _parameter("range_kind", "engagement_range"),
                _parameter("battle_shock_result_modifier", -1),
            ),
        ),
    )
    return _coverage_payload(source_row_id, normalized_text, clauses)


def _spiritsliver_payload() -> RuleIRPayload:
    source_row_id = "enhancement:emperors-children:court-of-the-phoenician:000010654005"
    normalized_text = (
        "EMPEROR'S CHILDREN DAEMON PRINCE model only. Add 1 to the Strength and Attacks "
        "characteristics of the bearer's melee weapons."
    )
    clauses = (
        _keyword_gate_clause(
            clause_id=_coverage_clause_id(source_row_id, "gate:001"),
            normalized_text=normalized_text,
            source_text="EMPEROR'S CHILDREN DAEMON PRINCE model only",
            keyword_text="EMPEROR'S CHILDREN DAEMON PRINCE",
            required_keyword=EMPERORS_CHILDREN_KEYWORD,
            extra_parameters=(
                _parameter(
                    "required_keyword_sequence",
                    (
                        EMPERORS_CHILDREN_KEYWORD,
                        DAEMON_PRINCE_KEYWORD,
                    ),
                ),
            ),
        ),
        _characteristic_modifier_clause(
            clause_id=_coverage_clause_id(source_row_id, "effect:001"),
            normalized_text=normalized_text,
            source_text=(
                "Add 1 to the Strength and Attacks characteristics of the bearer's melee weapons."
            ),
            effect_text="Strength",
            characteristic="strength",
            delta=1,
            weapon_scope="melee",
            duration=None,
        ),
        _characteristic_modifier_clause(
            clause_id=_coverage_clause_id(source_row_id, "effect:002"),
            normalized_text=normalized_text,
            source_text=(
                "Add 1 to the Strength and Attacks characteristics of the bearer's melee weapons."
            ),
            effect_text="Attacks",
            characteristic="attacks",
            delta=1,
            weapon_scope="melee",
            duration=None,
        ),
    )
    return _coverage_payload(source_row_id, normalized_text, clauses)


def _contemptuous_disregard_payload(*, rule_id: str, source_id: str) -> RuleIRPayload:
    normalized_text = (
        "stratagem_activation_target_binding\n"
        "Until the end of the phase, each time an attack targets your unit, if the Strength "
        "characteristic of that attack is greater than the Toughness characteristic of your "
        "unit, subtract 1 from the Wound roll."
    )
    clauses = (
        _stratagem_target_binding_clause(rule_id, normalized_text),
        _effect_clause(
            clause_id=f"{rule_id}:effect:001",
            template_id=DICE_ROLL_MODIFIER_TEMPLATE_ID,
            normalized_text=normalized_text,
            source_text=normalized_text.split("\n", maxsplit=1)[1],
            trigger=_dice_roll_trigger(
                normalized_text,
                "each time an attack targets your unit",
                roll_type="wound",
            ),
            conditions=(),
            target=None,
            effects=(
                _effect(
                    "modify_dice_roll",
                    normalized_text,
                    "subtract 1 from the Wound roll",
                    (
                        _parameter("delta", -1),
                        _parameter("roll_type", "wound"),
                        _parameter(
                            "target_constraint",
                            "attack_strength_greater_than_target_toughness",
                        ),
                    ),
                ),
            ),
            duration=_end_phase_duration(normalized_text),
        ),
    )
    return _payload(rule_id, source_id, normalized_text, clauses, _stratagem_parser_version())


def _prideful_superiority_payload(*, rule_id: str, source_id: str) -> RuleIRPayload:
    normalized_text = (
        "stratagem_activation_target_binding\n"
        "Until the end of the phase, each time a model in your unit makes an attack that "
        "targets a CHARACTER unit, you can re-roll the Hit roll and you can re-roll the "
        "Wound roll."
    )
    clauses = (
        _stratagem_target_binding_clause(rule_id, normalized_text),
        _effect_clause(
            clause_id=f"{rule_id}:effect:001",
            template_id=REROLL_PERMISSION_TEMPLATE_ID,
            normalized_text=normalized_text,
            source_text=normalized_text.split("\n", maxsplit=1)[1],
            trigger=_dice_roll_trigger(
                normalized_text,
                "each time a model in your unit makes an attack that targets a CHARACTER unit",
                roll_type="wound",
            ),
            conditions=(
                _condition(
                    "keyword_gate",
                    normalized_text,
                    "CHARACTER unit",
                    (_parameter("required_keyword", CHARACTER_KEYWORD),),
                ),
            ),
            target=_target("player", normalized_text, "you"),
            effects=(
                _effect(
                    "reroll_permission",
                    normalized_text,
                    "you can re-roll the Hit roll",
                    (
                        _parameter("roll_type", "hit"),
                        _parameter("target_required_keyword", CHARACTER_KEYWORD),
                    ),
                ),
                _effect(
                    "reroll_permission",
                    normalized_text,
                    "you can re-roll the Wound roll",
                    (
                        _parameter("roll_type", "wound"),
                        _parameter("target_required_keyword", CHARACTER_KEYWORD),
                    ),
                ),
            ),
            duration=_end_phase_duration(normalized_text),
        ),
    )
    return _payload(rule_id, source_id, normalized_text, clauses, _stratagem_parser_version())


def _sinuous_breach_payload(*, rule_id: str, source_id: str) -> RuleIRPayload:
    normalized_text = (
        "stratagem_activation_target_binding\n"
        "Until the end of the phase, each time your unit makes a Normal, Advance or Charge "
        "move, it can move horizontally through terrain features."
    )
    clauses = (
        _stratagem_target_binding_clause(rule_id, normalized_text),
        _effect_clause(
            clause_id=f"{rule_id}:effect:001",
            template_id=GRANT_ABILITY_TEMPLATE_ID,
            normalized_text=normalized_text,
            source_text=normalized_text.split("\n", maxsplit=1)[1],
            target=None,
            effects=(
                _effect(
                    "movement_transit_permission",
                    normalized_text,
                    "move horizontally through terrain features",
                    (
                        _parameter("permission", "move_horizontally_through_terrain_features"),
                        _parameter("movement_modes", ("normal", "advance", "charge")),
                        _parameter("terrain_features", True),
                        _parameter("required_keyword", DAEMON_KEYWORD),
                    ),
                ),
            ),
            duration=_end_phase_duration(normalized_text),
        ),
    )
    return _payload(rule_id, source_id, normalized_text, clauses, _stratagem_parser_version())


def _close_quarters_excruciation_payload(*, rule_id: str, source_id: str) -> RuleIRPayload:
    normalized_text = (
        "stratagem_activation_target_binding\n"
        "Until the end of the phase, each time an EMPEROR'S CHILDREN model in your unit "
        "makes an attack that targets an eligible unit within 12 inches, improve the Strength "
        "and Armour Penetration characteristics of that attack by 1."
    )
    source_text = normalized_text.split("\n", maxsplit=1)[1]
    clauses = (
        _stratagem_target_binding_clause(rule_id, normalized_text),
        _characteristic_modifier_clause(
            clause_id=f"{rule_id}:effect:001",
            normalized_text=normalized_text,
            source_text=source_text,
            effect_text="improve the Strength",
            characteristic="strength",
            delta=1,
            weapon_scope="all",
            duration=_end_phase_duration(normalized_text),
            trigger=_dice_roll_trigger(
                normalized_text,
                "each time an EMPEROR'S CHILDREN model in your unit makes an attack",
                roll_type="attack",
            ),
            conditions=(
                _condition(
                    "distance_predicate",
                    normalized_text,
                    "within 12 inches",
                    (
                        _parameter("distance_inches", 12),
                        _parameter("object_kind", "unit"),
                        _parameter("object_owner", "eligible_target"),
                        _parameter("predicate", "within"),
                        _parameter("range_kind", "inches"),
                    ),
                ),
            ),
            extra_parameters=(
                _parameter("attack_role", "attacker"),
                _parameter("target_constraint", "eligible_unit_within_12"),
            ),
        ),
        _characteristic_modifier_clause(
            clause_id=f"{rule_id}:effect:002",
            normalized_text=normalized_text,
            source_text=source_text,
            effect_text="Armour Penetration",
            characteristic="armor_penetration",
            delta=1,
            weapon_scope="all",
            duration=_end_phase_duration(normalized_text),
            trigger=_dice_roll_trigger(
                normalized_text,
                "each time an EMPEROR'S CHILDREN model in your unit makes an attack",
                roll_type="attack",
            ),
            conditions=(
                _condition(
                    "distance_predicate",
                    normalized_text,
                    "within 12 inches",
                    (
                        _parameter("distance_inches", 12),
                        _parameter("object_kind", "unit"),
                        _parameter("object_owner", "eligible_target"),
                        _parameter("predicate", "within"),
                        _parameter("range_kind", "inches"),
                    ),
                ),
            ),
            extra_parameters=(
                _parameter("attack_role", "attacker"),
                _parameter("target_constraint", "eligible_unit_within_12"),
            ),
        ),
    )
    return _payload(rule_id, source_id, normalized_text, clauses, _stratagem_parser_version())


def _euphoric_inspiration_payload(*, rule_id: str, source_id: str) -> RuleIRPayload:
    normalized_text = (
        "stratagem_activation_target_binding\n"
        "Until the end of the phase, you can re-roll Charge rolls for friendly EMPEROR'S "
        "CHILDREN units within 6 inches of your unit."
    )
    clauses = (
        _stratagem_target_binding_clause(rule_id, normalized_text),
        _effect_clause(
            clause_id=f"{rule_id}:effect:001",
            template_id=REROLL_PERMISSION_TEMPLATE_ID,
            normalized_text=normalized_text,
            source_text=normalized_text.split("\n", maxsplit=1)[1],
            trigger=_dice_roll_trigger(
                normalized_text,
                "Charge rolls for friendly EMPEROR'S CHILDREN units within 6 inches of your unit",
                roll_type="charge",
            ),
            target=_target(
                "friendly_unit",
                normalized_text,
                "friendly EMPEROR'S CHILDREN units within 6 inches of your unit",
            ),
            effects=(
                _effect(
                    "reroll_permission",
                    normalized_text,
                    "you can re-roll Charge rolls",
                    (
                        _parameter("roll_type", "charge"),
                        _parameter("aura_distance_inches", 6),
                        _parameter("required_faction_keyword", EMPERORS_CHILDREN_KEYWORD),
                        _parameter("source_required_keyword", DAEMON_KEYWORD),
                    ),
                ),
            ),
            duration=_end_phase_duration(normalized_text),
        ),
    )
    return _payload(rule_id, source_id, normalized_text, clauses, _stratagem_parser_version())


def _catalytic_stimulus_payload(*, rule_id: str, source_id: str) -> RuleIRPayload:
    normalized_text = (
        "stratagem_activation_target_binding\nYour unit can make a surge move of up to D6 inches."
    )
    clauses = (
        _stratagem_target_binding_clause(rule_id, normalized_text),
        _ability_clause(
            clause_id=f"{rule_id}:effect:001",
            template_id=GRANT_ABILITY_TEMPLATE_ID,
            normalized_text=normalized_text,
            source_text=normalized_text.split("\n", maxsplit=1)[1],
            target_kind="friendly_unit",
            target_text="Your unit",
            effect_text="make a surge move of up to D6 inches",
            ability=TRIGGERED_NORMAL_MOVE_ABILITY,
            duration=None,
            extra_parameters=(
                _parameter("distance_expression", "D6"),
                _parameter("movement_mode", "normal"),
                _parameter("movement_kind", "surge"),
                _parameter("trigger_context", "enemy_shooting_wounds_lost"),
            ),
        ),
    )
    return _payload(rule_id, source_id, normalized_text, clauses, _stratagem_parser_version())


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


def _stratagem_coverage_payload(stratagem_id: str) -> RuleIRPayload:
    source_row_id = f"stratagem:emperors-children:court-of-the-phoenician:{stratagem_id}"
    rule_id = f"{SOURCE_PACKAGE_ID}:phase17e:{source_row_id}:source-text"
    return _stratagem_payload_by_id(stratagem_id, rule_id=rule_id, source_id=rule_id)


def _stratagem_activation_payload(profile_id: str) -> RuleIRPayload:
    stratagem_id = profile_id.rsplit(":", maxsplit=1)[-1]
    source_id = (
        f"{STRATAGEM_SOURCE_PACKAGE_ID}:stratagem:emperors-children:"
        f"court-of-the-phoenician:{stratagem_id}"
    )
    return _stratagem_payload_by_id(stratagem_id, rule_id=profile_id, source_id=source_id)


def _stratagem_payload_by_id(
    stratagem_id: str,
    *,
    rule_id: str,
    source_id: str,
) -> RuleIRPayload:
    if stratagem_id == "000010655002":
        return _contemptuous_disregard_payload(rule_id=rule_id, source_id=source_id)
    if stratagem_id == "000010655003":
        return _prideful_superiority_payload(rule_id=rule_id, source_id=source_id)
    if stratagem_id == "000010655004":
        return _sinuous_breach_payload(rule_id=rule_id, source_id=source_id)
    if stratagem_id == "000010655005":
        return _close_quarters_excruciation_payload(rule_id=rule_id, source_id=source_id)
    if stratagem_id == "000010655006":
        return _euphoric_inspiration_payload(rule_id=rule_id, source_id=source_id)
    if stratagem_id == "000010655007":
        return _catalytic_stimulus_payload(rule_id=rule_id, source_id=source_id)
    raise CourtOfThePhoenicianIrSupportError("Unsupported Court of the Phoenician Stratagem id.")


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


def _effect_clause(
    *,
    clause_id: str,
    template_id: str,
    normalized_text: str,
    source_text: str,
    target: RuleTargetSpecPayload | None,
    effects: tuple[RuleEffectSpecPayload, ...],
    duration: RuleDurationPayload | None,
    trigger: RuleTriggerPayload | None = None,
    conditions: tuple[RuleConditionPayload, ...] = (),
) -> RuleClausePayload:
    return cast(
        RuleClausePayload,
        {
            "clause_id": clause_id,
            "template_id": template_id,
            "source_span": _span(normalized_text, source_text),
            "trigger": trigger,
            "conditions": list(conditions),
            "target": target,
            "effects": list(effects),
            "duration": duration,
            "unsupported_reason": None,
            "diagnostics": [],
        },
    )


def _keyword_gate_clause(
    *,
    clause_id: str,
    normalized_text: str,
    source_text: str,
    keyword_text: str,
    required_keyword: str,
    extra_parameters: tuple[RuleParameterPayload, ...] = (),
) -> RuleClausePayload:
    return cast(
        RuleClausePayload,
        {
            "clause_id": clause_id,
            "template_id": KEYWORD_GATE_TEMPLATE_ID,
            "source_span": _span(normalized_text, source_text),
            "trigger": None,
            "conditions": [
                {
                    "kind": "keyword_gate",
                    "source_span": _span(normalized_text, keyword_text),
                    "parameters": [
                        _parameter("required_keyword", required_keyword),
                        *extra_parameters,
                    ],
                }
            ],
            "target": None,
            "effects": [],
            "duration": None,
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


def _ability_clause(
    *,
    clause_id: str,
    template_id: str,
    normalized_text: str,
    source_text: str,
    target_kind: str,
    target_text: str,
    effect_text: str,
    ability: str,
    duration: RuleDurationPayload | None,
    extra_parameters: tuple[RuleParameterPayload, ...] = (),
) -> RuleClausePayload:
    return _effect_clause(
        clause_id=clause_id,
        template_id=template_id,
        normalized_text=normalized_text,
        source_text=source_text,
        target=_target(target_kind, normalized_text, target_text),
        effects=(
            _effect(
                "grant_ability",
                normalized_text,
                effect_text,
                (_parameter("ability", ability), *extra_parameters),
            ),
        ),
        duration=duration,
    )


def _characteristic_modifier_clause(
    *,
    clause_id: str,
    normalized_text: str,
    source_text: str,
    effect_text: str,
    characteristic: str,
    delta: int,
    weapon_scope: str,
    duration: RuleDurationPayload | None,
    trigger: RuleTriggerPayload | None = None,
    conditions: tuple[RuleConditionPayload, ...] = (),
    extra_parameters: tuple[RuleParameterPayload, ...] = (),
) -> RuleClausePayload:
    return _effect_clause(
        clause_id=clause_id,
        template_id=CHARACTERISTIC_MODIFIER_TEMPLATE_ID,
        normalized_text=normalized_text,
        source_text=source_text,
        trigger=trigger,
        conditions=conditions,
        target=None,
        effects=(
            _effect(
                "modify_characteristic",
                normalized_text,
                effect_text,
                (
                    _parameter("characteristic", characteristic),
                    _parameter("delta", delta),
                    _parameter("weapon_scope", weapon_scope),
                    *extra_parameters,
                ),
            ),
        ),
        duration=duration,
    )


def _move_modifier_clause(
    *,
    clause_id: str,
    normalized_text: str,
    source_text: str,
    target_kind: str,
    target_text: str,
    effect_text: str,
    delta: int,
    duration: RuleDurationPayload | None,
) -> RuleClausePayload:
    return _effect_clause(
        clause_id=clause_id,
        template_id=MOVEMENT_DISTANCE_TEMPLATE_ID,
        normalized_text=normalized_text,
        source_text=source_text,
        target=_target(target_kind, normalized_text, target_text),
        effects=(
            _effect(
                "modify_move_distance",
                normalized_text,
                effect_text,
                (_parameter("delta", delta),),
            ),
        ),
        duration=duration,
    )


def _dice_roll_trigger(
    normalized_text: str,
    source_text: str,
    *,
    roll_type: str,
) -> RuleTriggerPayload:
    return cast(
        RuleTriggerPayload,
        {
            "kind": "dice_roll",
            "source_span": _span(normalized_text, source_text),
            "parameters": [_parameter("roll_type", roll_type)],
        },
    )


def _condition(
    kind: str,
    normalized_text: str,
    source_text: str,
    parameters: tuple[RuleParameterPayload, ...],
) -> RuleConditionPayload:
    return cast(
        RuleConditionPayload,
        {
            "kind": kind,
            "source_span": _span(normalized_text, source_text),
            "parameters": list(parameters),
        },
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
    parameters: tuple[RuleParameterPayload, ...] = (),
) -> RuleTargetSpecPayload:
    return cast(
        RuleTargetSpecPayload,
        {
            "kind": kind,
            "source_span": _span(normalized_text, source_text),
            "parameters": list(parameters),
        },
    )


def _end_phase_duration(normalized_text: str) -> RuleDurationPayload:
    source_text = (
        "Until the end of the phase"
        if "Until the end of the phase" in normalized_text
        else "until the end of the phase"
    )
    return cast(
        RuleDurationPayload,
        {
            "kind": "until_timing_endpoint",
            "source_span": _span(normalized_text, source_text),
            "parameters": [_parameter("endpoint", "phase")],
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
        COURT_OF_THE_PHOENICIAN_DETACHMENT_RULE_DESCRIPTOR_ID: _detachment_rule_payload(),
        COURT_OF_THE_PHOENICIAN_ENHANCEMENT_DESCRIPTOR_IDS[0]: _tears_of_the_phoenix_payload(),
        COURT_OF_THE_PHOENICIAN_ENHANCEMENT_DESCRIPTOR_IDS[1]: _exalted_patron_payload(),
        COURT_OF_THE_PHOENICIAN_ENHANCEMENT_DESCRIPTOR_IDS[2]: (_soulstain_made_manifest_payload()),
        COURT_OF_THE_PHOENICIAN_ENHANCEMENT_DESCRIPTOR_IDS[3]: _spiritsliver_payload(),
    }
    for descriptor_id in COURT_OF_THE_PHOENICIAN_STRATAGEM_DESCRIPTOR_IDS:
        stratagem_id = descriptor_id.rsplit(":", maxsplit=1)[-1]
        payloads[descriptor_id] = _stratagem_coverage_payload(stratagem_id)
    return MappingProxyType(payloads)


def _stratagem_activation_payloads() -> Mapping[str, RuleIRPayload]:
    return MappingProxyType(
        {
            profile_id: _stratagem_activation_payload(profile_id)
            for profile_id in COURT_OF_THE_PHOENICIAN_STRATAGEM_PROFILE_IDS
        }
    )


_COVERAGE_RULE_IR_PAYLOADS_BY_DESCRIPTOR_ID = _coverage_payloads()
_STRATAGEM_ACTIVATION_RULE_IR_PAYLOADS_BY_PROFILE_ID = _stratagem_activation_payloads()
