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
    GRANT_ABILITY_TEMPLATE_ID,
    KEYWORD_GATE_TEMPLATE_ID,
    REROLL_PERMISSION_TEMPLATE_ID,
    WEAPON_ABILITY_GRANT_TEMPLATE_ID,
)

SOURCE_PACKAGE_ID = "gw-11e-phase17e-faction-coverage-2026-27"

ANHRATHE_KEYWORD = "ANHRATHE"
CHARACTER_KEYWORD = "CHARACTER"
INFANTRY_KEYWORD = "INFANTRY"

ARCHRAIDER_ENHANCEMENT_ID = "archraider"
ARCHRAIDER_SOURCE_ROW_ID = "enhancement:aeldari:corsair-coterie:archraider"
ARCHRAIDER_ENHANCEMENT_DESCRIPTOR_ID = f"phase17e:{ARCHRAIDER_SOURCE_ROW_ID}"
ARCHRAIDER_SOURCE_RULE_ID = f"phase17f:{ARCHRAIDER_ENHANCEMENT_DESCRIPTOR_ID}"
ARCHRAIDER_MARKER_ABILITY = "aeldari:corsair-coterie:archraider:marker"
ARCHRAIDER_MODEL_SELECTION_ABILITY = "aeldari:corsair-coterie:archraider:model-selection"
ARCHRAIDER_STRATAGEM_COST_CHOICE_ABILITY = (
    "aeldari:corsair-coterie:archraider:stratagem-cost-choice"
)
ARCHRAIDER_STRATAGEM_COST_MODIFIER_ABILITY = (
    "aeldari:corsair-coterie:archraider:stratagem-cost-modifier"
)

INFAMY_ENHANCEMENT_ID = "infamy"
INFAMY_SOURCE_ROW_ID = "enhancement:aeldari:corsair-coterie:infamy"
INFAMY_ENHANCEMENT_DESCRIPTOR_ID = f"phase17e:{INFAMY_SOURCE_ROW_ID}"
INFAMY_SOURCE_RULE_ID = f"phase17f:{INFAMY_ENHANCEMENT_DESCRIPTOR_ID}"
INFAMY_MARKER_ABILITY = "aeldari:corsair-coterie:infamy:marker"
INFAMY_OBJECTIVE_CONTROL_ABILITY = "aeldari:corsair-coterie:infamy:objective-control"

VOIDSTONE_ENHANCEMENT_ID = "voidstone"
VOIDSTONE_SOURCE_ROW_ID = "enhancement:aeldari:corsair-coterie:voidstone"
VOIDSTONE_ENHANCEMENT_DESCRIPTOR_ID = f"phase17e:{VOIDSTONE_SOURCE_ROW_ID}"
VOIDSTONE_SOURCE_RULE_ID = f"phase17f:{VOIDSTONE_ENHANCEMENT_DESCRIPTOR_ID}"
VOIDSTONE_MARKER_ABILITY = "aeldari:corsair-coterie:voidstone:marker"
VOIDSTONE_SAVE_OPTION_ABILITY = "aeldari:corsair-coterie:voidstone:save-option"

WEBWAY_PATHSTONE_ENHANCEMENT_ID = "webway-pathstone"
WEBWAY_PATHSTONE_SOURCE_ROW_ID = "enhancement:aeldari:corsair-coterie:webway-pathstone"
WEBWAY_PATHSTONE_ENHANCEMENT_DESCRIPTOR_ID = f"phase17e:{WEBWAY_PATHSTONE_SOURCE_ROW_ID}"
WEBWAY_PATHSTONE_SOURCE_RULE_ID = f"phase17f:{WEBWAY_PATHSTONE_ENHANCEMENT_DESCRIPTOR_ID}"
WEBWAY_PATHSTONE_MARKER_ABILITY = "aeldari:corsair-coterie:webway-pathstone:marker"
WEBWAY_PATHSTONE_DEEP_STRIKE_ABILITY = "aeldari:corsair-coterie:webway-pathstone:deep-strike"
WEBWAY_PATHSTONE_RESERVES_ABILITY = "aeldari:corsair-coterie:webway-pathstone:reserves"

PIRATES_DUE_SOURCE_ROW_ID = "stratagem:aeldari:corsair-coterie:aeldari:corsair-coterie:pirates-due"
LETHAL_RUSE_SOURCE_ROW_ID = "stratagem:aeldari:corsair-coterie:aeldari:corsair-coterie:lethal-ruse"
OUTCAST_AMBUSH_SOURCE_ROW_ID = (
    "stratagem:aeldari:corsair-coterie:aeldari:corsair-coterie:outcast-ambush"
)
INTO_THE_BREACH_SOURCE_ROW_ID = (
    "stratagem:aeldari:corsair-coterie:aeldari:corsair-coterie:into-the-breach"
)
CLOAK_AND_SHADOW_SOURCE_ROW_ID = (
    "stratagem:aeldari:corsair-coterie:aeldari:corsair-coterie:cloak-and-shadow"
)
VENGEFUL_SORROW_SOURCE_ROW_ID = (
    "stratagem:aeldari:corsair-coterie:aeldari:corsair-coterie:vengeful-sorrow"
)

PIRATES_DUE_DESCRIPTOR_ID = f"phase17e:{PIRATES_DUE_SOURCE_ROW_ID}"
LETHAL_RUSE_DESCRIPTOR_ID = f"phase17e:{LETHAL_RUSE_SOURCE_ROW_ID}"
OUTCAST_AMBUSH_DESCRIPTOR_ID = f"phase17e:{OUTCAST_AMBUSH_SOURCE_ROW_ID}"
INTO_THE_BREACH_DESCRIPTOR_ID = f"phase17e:{INTO_THE_BREACH_SOURCE_ROW_ID}"
CLOAK_AND_SHADOW_DESCRIPTOR_ID = f"phase17e:{CLOAK_AND_SHADOW_SOURCE_ROW_ID}"
VENGEFUL_SORROW_DESCRIPTOR_ID = f"phase17e:{VENGEFUL_SORROW_SOURCE_ROW_ID}"

PIRATES_DUE_EFFECT_KIND = "aeldari_corsair_coterie_pirates_due"
LETHAL_RUSE_EFFECT_KIND = "aeldari_corsair_coterie_lethal_ruse"
OUTCAST_AMBUSH_EFFECT_KIND = "aeldari_corsair_coterie_outcast_ambush"
CLOAK_AND_SHADOW_EFFECT_KIND = "aeldari_corsair_coterie_cloak_and_shadow"
CLOAK_AND_SHADOW_MAX_RANGE_INCHES = 18.0

IGNORES_COVER_WEAPON_ABILITY = "IGNORES_COVER"
RAPID_FIRE_WEAPON_ABILITY = "RAPID_FIRE"


class AeldariCorsairCoterieIrSupportError(ValueError):
    """Raised when static Corsair Coterie RuleIR metadata is inconsistent."""


def coverage_rule_ir_payload_by_descriptor_id(
    coverage_descriptor_id: str,
) -> RuleIRPayload | None:
    return _COVERAGE_RULE_IR_PAYLOADS_BY_DESCRIPTOR_ID.get(coverage_descriptor_id)


def coverage_rule_ir_hash_by_descriptor_id(coverage_descriptor_id: str) -> str | None:
    payload = coverage_rule_ir_payload_by_descriptor_id(coverage_descriptor_id)
    if payload is None:
        return None
    return payload["ir_hash"]


def supported_coverage_descriptor_ids() -> tuple[str, ...]:
    return tuple(sorted(_COVERAGE_RULE_IR_PAYLOADS_BY_DESCRIPTOR_ID))


def _archraider_payload() -> RuleIRPayload:
    normalized_text = (
        "ANHRATHE CHARACTER bearer gains the Archraider marker, selects an enemy model "
        "for Lord of Deceit before the battle, can choose Lord of Deceit when an eligible "
        "Stratagem is used, and increases that Stratagem's Command Point cost by 1."
    )
    return _enhancement_payload(
        source_row_id=ARCHRAIDER_SOURCE_ROW_ID,
        normalized_text=normalized_text,
        keyword_text="ANHRATHE CHARACTER",
        required_keyword_sequence=(ANHRATHE_KEYWORD, CHARACTER_KEYWORD),
        ability_clauses=(
            _ability_clause_spec(
                source_text="gains the Archraider marker",
                effect_text="gains the Archraider marker",
                ability=ARCHRAIDER_MARKER_ABILITY,
                hook_family="enhancement_effect",
            ),
            _ability_clause_spec(
                source_text="selects an enemy model for Lord of Deceit before the battle",
                effect_text="selects an enemy model for Lord of Deceit before the battle",
                ability=ARCHRAIDER_MODEL_SELECTION_ABILITY,
                hook_family="battle_formation",
            ),
            _ability_clause_spec(
                source_text="can choose Lord of Deceit when an eligible Stratagem is used",
                effect_text="can choose Lord of Deceit when an eligible Stratagem is used",
                ability=ARCHRAIDER_STRATAGEM_COST_CHOICE_ABILITY,
                hook_family="stratagem_cost_choice",
            ),
            _ability_clause_spec(
                source_text="increases that Stratagem's Command Point cost by 1",
                effect_text="increases that Stratagem's Command Point cost by 1",
                ability=ARCHRAIDER_STRATAGEM_COST_MODIFIER_ABILITY,
                hook_family="stratagem_cost_modifier",
                extra_parameters=(_parameter("command_point_cost_delta", 1),),
            ),
        ),
    )


def _infamy_payload() -> RuleIRPayload:
    normalized_text = (
        "ANHRATHE bearer gains the Infamy marker and reduces Objective Control by 1 "
        "for enemy units within 3 inches."
    )
    return _enhancement_payload(
        source_row_id=INFAMY_SOURCE_ROW_ID,
        normalized_text=normalized_text,
        keyword_text="ANHRATHE",
        required_keyword_sequence=(ANHRATHE_KEYWORD,),
        ability_clauses=(
            _ability_clause_spec(
                source_text="gains the Infamy marker",
                effect_text="gains the Infamy marker",
                ability=INFAMY_MARKER_ABILITY,
                hook_family="enhancement_effect",
            ),
            _ability_clause_spec(
                source_text="reduces Objective Control by 1 for enemy units within 3 inches",
                effect_text="reduces Objective Control by 1",
                ability=INFAMY_OBJECTIVE_CONTROL_ABILITY,
                hook_family="objective_control_modifier",
                extra_parameters=(_parameter("objective_control_delta", -1),),
            ),
        ),
    )


def _voidstone_payload() -> RuleIRPayload:
    normalized_text = (
        "ANHRATHE INFANTRY bearer gains the Voidstone marker and gains a 5+ invulnerable save."
    )
    return _enhancement_payload(
        source_row_id=VOIDSTONE_SOURCE_ROW_ID,
        normalized_text=normalized_text,
        keyword_text="ANHRATHE INFANTRY",
        required_keyword_sequence=(ANHRATHE_KEYWORD, INFANTRY_KEYWORD),
        ability_clauses=(
            _ability_clause_spec(
                source_text="gains the Voidstone marker",
                effect_text="gains the Voidstone marker",
                ability=VOIDSTONE_MARKER_ABILITY,
                hook_family="enhancement_effect",
            ),
            _ability_clause_spec(
                source_text="gains a 5+ invulnerable save",
                effect_text="gains a 5+ invulnerable save",
                ability=VOIDSTONE_SAVE_OPTION_ABILITY,
                hook_family="save_option_modifier",
                extra_parameters=(_parameter("invulnerable_save_target", 5),),
            ),
        ),
    )


def _webway_pathstone_payload() -> RuleIRPayload:
    normalized_text = (
        "ANHRATHE bearer gains the Webway Pathstone marker, gains Deep Strike, and can "
        "enter Strategic Reserves at the end of the Fight phase in the opponent's turn."
    )
    return _enhancement_payload(
        source_row_id=WEBWAY_PATHSTONE_SOURCE_ROW_ID,
        normalized_text=normalized_text,
        keyword_text="ANHRATHE",
        required_keyword_sequence=(ANHRATHE_KEYWORD,),
        ability_clauses=(
            _ability_clause_spec(
                source_text="gains the Webway Pathstone marker",
                effect_text="gains the Webway Pathstone marker",
                ability=WEBWAY_PATHSTONE_MARKER_ABILITY,
                hook_family="enhancement_effect",
            ),
            _ability_clause_spec(
                source_text="gains Deep Strike",
                effect_text="gains Deep Strike",
                ability=WEBWAY_PATHSTONE_DEEP_STRIKE_ABILITY,
                hook_family="enhancement_effect",
            ),
            _ability_clause_spec(
                source_text="can enter Strategic Reserves at the end of the Fight phase",
                effect_text="can enter Strategic Reserves at the end of the Fight phase",
                ability=WEBWAY_PATHSTONE_RESERVES_ABILITY,
                hook_family="turn_end",
            ),
        ),
    )


def _pirates_due_payload() -> RuleIRPayload:
    normalized_text = (
        "Aeldari unit that has not fought gains a wound reroll permission until the end "
        "of the Fight phase. Wound rolls of 1 can be rerolled; ANHRATHE attacks can "
        "reroll the Wound roll when the target is within range of an objective marker."
    )
    return _coverage_payload(
        PIRATES_DUE_SOURCE_ROW_ID,
        normalized_text,
        (
            _effect_clause(
                clause_id=_coverage_clause_id(PIRATES_DUE_SOURCE_ROW_ID, "effect:001"),
                template_id=REROLL_PERMISSION_TEMPLATE_ID,
                normalized_text=normalized_text,
                source_text="wound reroll permission",
                target=_target("this_unit", normalized_text, "Aeldari unit"),
                effects=(
                    _effect(
                        "reroll_permission",
                        normalized_text,
                        "wound reroll permission",
                        (
                            _parameter("roll_type", "attack_sequence.wound"),
                            _parameter("timing_window", "attack_sequence.wound"),
                            _parameter("attack_role", "attacker"),
                            _parameter("reroll_unmodified_value", 1),
                            _parameter("full_reroll_if_target_within_objective_range", True),
                            _parameter("full_reroll_required_attacker_keyword", ANHRATHE_KEYWORD),
                        ),
                    ),
                ),
                duration=_timing_endpoint_duration(
                    normalized_text, "end of the Fight phase", "phase"
                ),
            ),
        ),
    )


def _lethal_ruse_payload() -> RuleIRPayload:
    normalized_text = (
        "Aeldari unit that Fell Back is eligible to declare a charge until the end of "
        "the turn. If it is ANHRATHE, select an engaged enemy unit and roll six D6; "
        "each 4+ inflicts one mortal wound."
    )
    return _coverage_payload(
        LETHAL_RUSE_SOURCE_ROW_ID,
        normalized_text,
        (
            _effect_clause(
                clause_id=_coverage_clause_id(LETHAL_RUSE_SOURCE_ROW_ID, "effect:001"),
                template_id=GRANT_ABILITY_TEMPLATE_ID,
                normalized_text=normalized_text,
                source_text="eligible to declare a charge until the end of the turn",
                target=_target("this_unit", normalized_text, "Aeldari unit"),
                effects=(
                    _effect(
                        "grant_ability",
                        normalized_text,
                        "eligible to declare a charge",
                        (
                            _parameter("ability", "charge_after_fall_back"),
                            _parameter("source_effect_kind", LETHAL_RUSE_EFFECT_KIND),
                        ),
                    ),
                ),
                duration=_timing_endpoint_duration(normalized_text, "end of the turn", "turn"),
            ),
            _effect_clause(
                clause_id=_coverage_clause_id(LETHAL_RUSE_SOURCE_ROW_ID, "effect:002"),
                template_id=CONTEXTUAL_STATUS_TEMPLATE_ID,
                normalized_text=normalized_text,
                source_text="roll six D6; each 4+ inflicts one mortal wound",
                target=None,
                effects=(
                    _effect(
                        "inflict_mortal_wounds",
                        normalized_text,
                        "each 4+ inflicts one mortal wound",
                        (
                            _parameter("required_target_keyword", ANHRATHE_KEYWORD),
                            _parameter("effect_selection_kind", "engaged_enemy_unit"),
                            _parameter("roll_quantity", 6),
                            _parameter("roll_sides", 6),
                            _parameter("success_threshold", 4),
                            _parameter("mortal_wounds_per_success", 1),
                            _parameter("spill_over", True),
                            _parameter("roll_type", "generic_rule_ir.lethal_ruse_mortal_wounds"),
                            _parameter(
                                "replay_effect_kind", f"{LETHAL_RUSE_EFFECT_KIND}_mortal_wounds"
                            ),
                        ),
                    ),
                ),
                duration=None,
            ),
        ),
    )


def _outcast_ambush_payload() -> RuleIRPayload:
    normalized_text = (
        "Rangers or Shroud Runners unit that has not shot improves ranged weapons until "
        "the end of the Shooting phase: weapons gain Ignores Cover, gain Rapid Fire 1, "
        "and improve Armour Penetration by 1."
    )
    return _coverage_payload(
        OUTCAST_AMBUSH_SOURCE_ROW_ID,
        normalized_text,
        (
            _effect_clause(
                clause_id=_coverage_clause_id(OUTCAST_AMBUSH_SOURCE_ROW_ID, "effect:001"),
                template_id=WEAPON_ABILITY_GRANT_TEMPLATE_ID,
                normalized_text=normalized_text,
                source_text="weapons gain Ignores Cover",
                target=_target("this_unit", normalized_text, "Rangers or Shroud Runners unit"),
                effects=(
                    _effect(
                        "grant_weapon_ability",
                        normalized_text,
                        "Ignores Cover",
                        (
                            _parameter("weapon_ability", IGNORES_COVER_WEAPON_ABILITY),
                            _parameter("attack_role", "attacker"),
                            _parameter("source_phase", "shooting"),
                        ),
                    ),
                ),
                duration=_timing_endpoint_duration(
                    normalized_text, "end of the Shooting phase", "phase"
                ),
            ),
            _effect_clause(
                clause_id=_coverage_clause_id(OUTCAST_AMBUSH_SOURCE_ROW_ID, "effect:002"),
                template_id=WEAPON_ABILITY_GRANT_TEMPLATE_ID,
                normalized_text=normalized_text,
                source_text="gain Rapid Fire 1",
                target=_target("this_unit", normalized_text, "Rangers or Shroud Runners unit"),
                effects=(
                    _effect(
                        "grant_weapon_ability",
                        normalized_text,
                        "Rapid Fire 1",
                        (
                            _parameter("weapon_ability", RAPID_FIRE_WEAPON_ABILITY),
                            _parameter("weapon_ability_value", 1),
                            _parameter("attack_role", "attacker"),
                            _parameter("source_phase", "shooting"),
                        ),
                    ),
                ),
                duration=_timing_endpoint_duration(
                    normalized_text, "end of the Shooting phase", "phase"
                ),
            ),
            _effect_clause(
                clause_id=_coverage_clause_id(OUTCAST_AMBUSH_SOURCE_ROW_ID, "effect:003"),
                template_id=CHARACTERISTIC_MODIFIER_TEMPLATE_ID,
                normalized_text=normalized_text,
                source_text="improve Armour Penetration by 1",
                target=_target("this_unit", normalized_text, "Rangers or Shroud Runners unit"),
                effects=(
                    _effect(
                        "modify_characteristic",
                        normalized_text,
                        "improve Armour Penetration by 1",
                        (
                            _parameter("characteristic", "armor_penetration"),
                            _parameter("delta", -1),
                            _parameter("attack_role", "attacker"),
                            _parameter("source_phase", "shooting"),
                        ),
                    ),
                ),
                duration=_timing_endpoint_duration(
                    normalized_text, "end of the Shooting phase", "phase"
                ),
            ),
        ),
    )


def _into_the_breach_payload() -> RuleIRPayload:
    normalized_text = (
        "ANHRATHE unit that shot and destroyed an enemy unit can make a Normal move "
        "of up to D6+1 inches."
    )
    return _coverage_payload(
        INTO_THE_BREACH_SOURCE_ROW_ID,
        normalized_text,
        (
            _triggered_move_clause(
                source_row_id=INTO_THE_BREACH_SOURCE_ROW_ID,
                normalized_text=normalized_text,
                source_text="Normal move of up to D6+1 inches",
                source_step="into_the_breach",
                roll_type="generic_rule_ir.into_the_breach_distance",
                distance_bonus=1,
                movement_kind="triggered",
                allow_battle_shocked=True,
                replay_effect_kind="into_the_breach_move",
                phase_body_status="into_the_breach_move_pending",
            ),
        ),
    )


def _cloak_and_shadow_payload() -> RuleIRPayload:
    normalized_text = (
        "Aeldari Infantry unit within range of a controlled objective gains Stealth until "
        "the end of the Shooting phase and can only be selected as the target of a ranged "
        "attack if the attacking model is within 18 inches."
    )
    return _coverage_payload(
        CLOAK_AND_SHADOW_SOURCE_ROW_ID,
        normalized_text,
        (
            _effect_clause(
                clause_id=_coverage_clause_id(CLOAK_AND_SHADOW_SOURCE_ROW_ID, "effect:001"),
                template_id=CONTEXTUAL_STATUS_TEMPLATE_ID,
                normalized_text=normalized_text,
                source_text="gains Stealth until the end of the Shooting phase",
                target=_target("this_unit", normalized_text, "Aeldari Infantry unit"),
                effects=(
                    _effect(
                        "set_contextual_status",
                        normalized_text,
                        "gains Stealth",
                        (
                            _parameter("status", "smokescreen_target_restriction"),
                            _parameter("source_effect_kind", CLOAK_AND_SHADOW_EFFECT_KIND),
                            _parameter("hit_roll_modifier", -1),
                            _parameter(
                                "targeting_max_range_inches", CLOAK_AND_SHADOW_MAX_RANGE_INCHES
                            ),
                        ),
                    ),
                ),
                duration=_timing_endpoint_duration(
                    normalized_text, "end of the Shooting phase", "phase"
                ),
            ),
        ),
    )


def _vengeful_sorrow_payload() -> RuleIRPayload:
    normalized_text = (
        "Aeldari Infantry unit with destroyed models can make a surge move of up to "
        "D6+1 inches if it is not Battle-shocked and not within Engagement Range."
    )
    return _coverage_payload(
        VENGEFUL_SORROW_SOURCE_ROW_ID,
        normalized_text,
        (
            _triggered_move_clause(
                source_row_id=VENGEFUL_SORROW_SOURCE_ROW_ID,
                normalized_text=normalized_text,
                source_text="surge move of up to D6+1 inches",
                source_step="vengeful_sorrow",
                roll_type="generic_rule_ir.vengeful_sorrow_distance",
                distance_bonus=1,
                movement_kind="surge",
                allow_battle_shocked=False,
                replay_effect_kind="vengeful_sorrow_surge",
                phase_body_status="vengeful_sorrow_surge_pending",
            ),
        ),
    )


def _ability_clause_spec(
    *,
    source_text: str,
    effect_text: str,
    ability: str,
    hook_family: str,
    extra_parameters: tuple[RuleParameterPayload, ...] = (),
) -> tuple[str, str, str, str, tuple[RuleParameterPayload, ...]]:
    return source_text, effect_text, ability, hook_family, extra_parameters


def _enhancement_payload(
    *,
    source_row_id: str,
    normalized_text: str,
    keyword_text: str,
    required_keyword_sequence: tuple[str, ...],
    ability_clauses: tuple[tuple[str, str, str, str, tuple[RuleParameterPayload, ...]], ...],
) -> RuleIRPayload:
    clauses: list[RuleClausePayload] = [
        _keyword_gate_clause(
            clause_id=_coverage_clause_id(source_row_id, "gate:001"),
            normalized_text=normalized_text,
            keyword_text=keyword_text,
            required_keyword_sequence=required_keyword_sequence,
        )
    ]
    for index, (source_text, effect_text, ability, hook_family, extra_parameters) in enumerate(
        ability_clauses,
        start=1,
    ):
        clauses.append(
            _ability_clause(
                clause_id=_coverage_clause_id(source_row_id, f"effect:{index:03d}"),
                normalized_text=normalized_text,
                source_text=source_text,
                effect_text=effect_text,
                ability=ability,
                required_keyword_sequence=required_keyword_sequence,
                extra_parameters=(
                    _parameter("hook_family", hook_family),
                    *extra_parameters,
                ),
            )
        )
    return _coverage_payload(source_row_id, normalized_text, tuple(clauses))


def _keyword_gate_clause(
    *,
    clause_id: str,
    normalized_text: str,
    keyword_text: str,
    required_keyword_sequence: tuple[str, ...],
) -> RuleClausePayload:
    return cast(
        RuleClausePayload,
        {
            "clause_id": clause_id,
            "template_id": KEYWORD_GATE_TEMPLATE_ID,
            "source_span": _span(normalized_text, keyword_text),
            "trigger": None,
            "conditions": [
                _keyword_gate_condition(
                    normalized_text=normalized_text,
                    keyword_text=keyword_text,
                    required_keyword_sequence=required_keyword_sequence,
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
    required_keyword_sequence: tuple[str, ...],
) -> RuleConditionPayload:
    return cast(
        RuleConditionPayload,
        {
            "kind": "keyword_gate",
            "source_span": _span(normalized_text, keyword_text),
            "parameters": [_parameter("required_keyword_sequence", required_keyword_sequence)],
        },
    )


def _ability_clause(
    *,
    clause_id: str,
    normalized_text: str,
    source_text: str,
    effect_text: str,
    ability: str,
    required_keyword_sequence: tuple[str, ...],
    extra_parameters: tuple[RuleParameterPayload, ...],
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


def _triggered_move_clause(
    *,
    source_row_id: str,
    normalized_text: str,
    source_text: str,
    source_step: str,
    roll_type: str,
    distance_bonus: int,
    movement_kind: str,
    allow_battle_shocked: bool,
    replay_effect_kind: str,
    phase_body_status: str,
) -> RuleClausePayload:
    return _effect_clause(
        clause_id=_coverage_clause_id(source_row_id, "effect:001"),
        template_id=GRANT_ABILITY_TEMPLATE_ID,
        normalized_text=normalized_text,
        source_text=source_text,
        target=_target("this_unit", normalized_text, "unit"),
        effects=(
            _effect(
                "grant_ability",
                normalized_text,
                source_text,
                (
                    _parameter("ability", "triggered_normal_move"),
                    _parameter("movement_kind", movement_kind),
                    _parameter("movement_mode", "normal"),
                    _parameter("roll_quantity", 1),
                    _parameter("roll_sides", 6),
                    _parameter("distance_bonus", distance_bonus),
                    _parameter("roll_type", roll_type),
                    _parameter("source_step", source_step),
                    _parameter("allow_battle_shocked", allow_battle_shocked),
                    _parameter("allow_within_engagement_range", False),
                    _parameter("optional", True),
                    _parameter("one_per_phase", False),
                    _parameter("replay_effect_kind", replay_effect_kind),
                    _parameter("phase_body_status", phase_body_status),
                ),
            ),
        ),
        duration=None,
    )


def _effect_clause(
    *,
    clause_id: str,
    template_id: str,
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


def _timing_endpoint_duration(
    normalized_text: str,
    source_text: str,
    endpoint: str,
) -> RuleDurationPayload:
    return cast(
        RuleDurationPayload,
        {
            "kind": "until_timing_endpoint",
            "source_span": _span(normalized_text, source_text),
            "parameters": [_parameter("endpoint", endpoint)],
        },
    )


def _coverage_payload(
    source_row_id: str,
    normalized_text: str,
    clauses: tuple[RuleClausePayload, ...],
) -> RuleIRPayload:
    source_id = f"{SOURCE_PACKAGE_ID}:phase17e:{source_row_id}:source-text"
    return RuleIR(
        rule_id=source_id,
        source_id=source_id,
        normalized_text=normalized_text,
        parser_version="phase17c-rule-parser-v1",
        schema_version="phase17c-rule-ir-v1",
        clauses=tuple(RuleClause.from_payload(clause) for clause in clauses),
        diagnostics=(),
    ).to_payload()


def _coverage_clause_id(source_row_id: str, suffix: str) -> str:
    return f"{SOURCE_PACKAGE_ID}:phase17e:{source_row_id}:source-text:{suffix}"


def _parameter(
    key: str,
    value: str | int | float | bool | None | tuple[str, ...],
) -> RuleParameterPayload:
    payload_value = list(value) if type(value) is tuple else value
    return cast(RuleParameterPayload, {"key": key, "value": payload_value})


def _span(normalized_text: str, source_text: str) -> dict[str, str | int]:
    start = normalized_text.index(source_text)
    return {"text": source_text, "start": start, "end": start + len(source_text)}


def _payload_rows() -> Mapping[str, RuleIRPayload]:
    return {
        ARCHRAIDER_ENHANCEMENT_DESCRIPTOR_ID: _archraider_payload(),
        INFAMY_ENHANCEMENT_DESCRIPTOR_ID: _infamy_payload(),
        VOIDSTONE_ENHANCEMENT_DESCRIPTOR_ID: _voidstone_payload(),
        WEBWAY_PATHSTONE_ENHANCEMENT_DESCRIPTOR_ID: _webway_pathstone_payload(),
        PIRATES_DUE_DESCRIPTOR_ID: _pirates_due_payload(),
        LETHAL_RUSE_DESCRIPTOR_ID: _lethal_ruse_payload(),
        OUTCAST_AMBUSH_DESCRIPTOR_ID: _outcast_ambush_payload(),
        INTO_THE_BREACH_DESCRIPTOR_ID: _into_the_breach_payload(),
        CLOAK_AND_SHADOW_DESCRIPTOR_ID: _cloak_and_shadow_payload(),
        VENGEFUL_SORROW_DESCRIPTOR_ID: _vengeful_sorrow_payload(),
    }


_COVERAGE_RULE_IR_PAYLOADS_BY_DESCRIPTOR_ID = MappingProxyType(_payload_rows())
