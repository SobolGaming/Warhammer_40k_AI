from __future__ import annotations

from types import MappingProxyType

from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleCondition,
    RuleConditionKind,
    RuleDuration,
    RuleDurationKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleIRPayload,
    RuleParameter,
    RuleParameterValue,
    RuleTargetKind,
    RuleTargetSpec,
    RuleTrigger,
    RuleTriggerKind,
)

SOURCE_PACKAGE_ID = "gw-11e-chaos-daemons-datasheet-ir-2026-27"
PARSER_VERSION = "manual-source-backed-rule-ir:v1"

BELAKOR_DATASHEET_ID = "000001148"
BELAKOR_DARK_MASTER_ROW_ID = "000001148:5"
BELAKOR_SHADOW_FORM_ROW_ID = "000001148:6"
BELAKOR_WREATHED_IN_SHADOWS_ROW_ID = "000001148:8"
BELAKOR_PALL_OF_DESPAIR_ROW_ID = "000001148:9"
BELAKOR_SHADOW_LORD_ROW_ID = "000001148:10"
DAEMON_PRINCE_ROW_IDS = tuple(f"000001149:{line}" for line in range(4, 12))
WINGED_DAEMON_PRINCE_ROW_IDS = tuple(f"000002758:{line}" for line in range(4, 11))
SOUL_GRINDER_ALLEGIANCE_ROW_ID = "000001151:5"

BELAKOR_DARK_MASTER_SOURCE_ID = f"{SOURCE_PACKAGE_ID}:datasheet:{BELAKOR_DARK_MASTER_ROW_ID}"
BELAKOR_SHADOW_FORM_SOURCE_ID = f"{SOURCE_PACKAGE_ID}:datasheet:{BELAKOR_SHADOW_FORM_ROW_ID}"
BELAKOR_WREATHED_IN_SHADOWS_SOURCE_ID = (
    f"{SOURCE_PACKAGE_ID}:datasheet:{BELAKOR_WREATHED_IN_SHADOWS_ROW_ID}"
)
BELAKOR_PALL_OF_DESPAIR_SOURCE_ID = (
    f"{SOURCE_PACKAGE_ID}:datasheet:{BELAKOR_PALL_OF_DESPAIR_ROW_ID}"
)
BELAKOR_SHADOW_LORD_SOURCE_ID = f"{SOURCE_PACKAGE_ID}:datasheet:{BELAKOR_SHADOW_LORD_ROW_ID}"

BELAKOR_SHADOW_FORM_SELECTABLE_SOURCE_IDS = (
    BELAKOR_WREATHED_IN_SHADOWS_SOURCE_ID,
    BELAKOR_PALL_OF_DESPAIR_SOURCE_ID,
    BELAKOR_SHADOW_LORD_SOURCE_ID,
)

LEGIONES_DAEMONICA_KEYWORD = "LEGIONES DAEMONICA"
SHADOW_LEGION_KEYWORD = "SHADOW LEGION"

_DARK_MASTER_TEXT = (
    "The area of the battlefield within 6\" of this model is within your army's Shadow of Chaos."
)
_SHADOW_FORM_TEXT = (
    "At the start of the battle round, select one Shadow Form ability (see below). Until the "
    "end of the battle round, this model has that ability."
)
_WREATHED_IN_SHADOWS_TEXT = (
    'While a friendly Legiones Daemonica unit or Shadow Legion unit is within 6" of this model, '
    'that unit can only be targeted by a ranged attack if the attacking model is within 18".'
)
_PALL_OF_DESPAIR_TEXT = (
    "In the Battle-shock step of your opponent's Command phase, if an enemy unit that is below "
    'its Starting Strength is within 9" of this model, that unit must take a Battle-shock test. '
    "For the purposes of this ability, if a unit has a Starting Strength of 1, it is considered "
    "to be below its Starting Strength while it has lost one or more wounds. In addition, for "
    'each enemy unit that fails a Battle-shock test within 9" of this model, this model regains '
    "up to D3 lost wounds."
)
_SHADOW_LORD_TEXT = (
    'While a friendly Legiones Daemonica or Shadow Legion unit is within 6" of this model, each '
    "time a model in that unit makes an attack, re-roll a Hit roll of 1."
)

_RULE_TEXT_BY_SOURCE_ROW_ID = {
    "000001149:4": (
        'While this model is within 3" of one or more friendly Legiones Daemonica Infantry '
        "units, this model has the Lone Operative ability."
    ),
    "000001149:5": (
        'While a friendly Legiones Daemonica unit is within 6" of this model, models in that '
        "unit have the Stealth ability."
    ),
    "000001149:6": (
        "Once per battle, at the start of any phase, this model can use this ability. If it "
        "does, until the end of the phase, this model has a 3+ invulnerable save."
    ),
    "000001149:7": (
        "When you select this model to include in your army, you must select one of the following "
        "keywords for it to gain:\n- KHORNE\n- TZEENTCH\n- NURGLE\n- SLAANESH\nThe "
        "keyword you select will also affect some of this model's characteristics, as stated "
        "overleaf."
    ),
    "000001149:8": (
        "If this model has the KHORNE keyword, add 2 to the Strength characteristic of this "
        "model's hellforged weapons."
    ),
    "000001149:9": (
        "If this model has the TZEENTCH keyword, add 3 to the Attacks characteristic of this "
        "model's infernal cannon."
    ),
    "000001149:10": (
        "If this model has the NURGLE keyword, add 1 to this model's Toughness characteristic."
    ),
    "000001149:11": (
        "If this model has the SLAANESH keyword, add 2\" to this model's Move characteristic."
    ),
    "000002758:4": (
        "Once per battle, at the start of the Fight phase, this model can use this ability. If "
        "it does, until the end of the phase, add 3 to the Attacks characteristic of this "
        "model's hellforged weapons."
    ),
    "000002758:5": (
        "Each time this model is selected to fight, select one of the following abilities. Until "
        "the end of the phase, this model's hellforged weapons have that ability:\n- [LETHAL "
        "HITS]\n- [PRECISION]\n- [SUSTAINED HITS 1]"
    ),
    "000002758:6": (
        "When you select this model to include in your army, you must select one of the following "
        "keywords for it to gain:\n- KHORNE\n- TZEENTCH\n- NURGLE\n- SLAANESH\nThe "
        "keyword you select will also affect some of this model's characteristics, as stated "
        "overleaf."
    ),
    "000002758:7": (
        "If this model has the KHORNE keyword, add 2 to the Strength characteristic of this "
        "model's hellforged weapons."
    ),
    "000002758:8": (
        "If this model has the TZEENTCH keyword, add 3 to the Attacks characteristic of this "
        "model's infernal cannon."
    ),
    "000002758:9": (
        "If this model has the NURGLE keyword, add 1 to this model's Toughness characteristic."
    ),
    "000002758:10": (
        "If this model has the SLAANESH keyword, add 2\" to this model's Move characteristic."
    ),
    SOUL_GRINDER_ALLEGIANCE_ROW_ID: (
        "When you select this model to include in your army, you must select one of the keywords "
        "below. Until the end of the battle, this model has that keyword and the additional "
        "wargear stated for that keyword below:\nKHORNE - This model is additionally equipped "
        "with: torrent of burning blood\nTZEENTCH - This model is additionally equipped with: "
        "warp gaze\nNURGLE - This model is additionally equipped with: phlegm bombardment\n"
        "SLAANESH - This model is additionally equipped with: scream of despair"
    ),
}


def supported_datasheet_source_row_ids() -> tuple[str, ...]:
    return tuple(sorted(_RULE_IR_PAYLOADS_BY_SOURCE_ROW_ID))


def datasheet_rule_ir_payload_by_source_row_id(source_row_id: str) -> RuleIRPayload | None:
    return _RULE_IR_PAYLOADS_BY_SOURCE_ROW_ID.get(source_row_id)


def _payload(rule_ir: RuleIR) -> RuleIRPayload:
    return RuleIR.from_payload(rule_ir.to_payload()).to_payload()


def _rule_ir(
    *,
    source_row_id: str,
    normalized_text: str,
    clauses: tuple[RuleClause, ...],
) -> RuleIR:
    return RuleIR(
        rule_id=f"phase17k:chaos-daemons:datasheet:{source_row_id}",
        source_id=f"{SOURCE_PACKAGE_ID}:datasheet:{source_row_id}",
        normalized_text=normalized_text,
        parser_version=PARSER_VERSION,
        clauses=clauses,
    )


def _span(text: str) -> TextSpan:
    return TextSpan(text=text, start=0, end=len(text))


def _parameter(key: str, value: RuleParameterValue) -> RuleParameter:
    return RuleParameter(key=key, value=value)


def _trigger(
    *,
    text: str,
    kind: RuleTriggerKind,
    parameters: tuple[RuleParameter, ...],
) -> RuleTrigger:
    return RuleTrigger(kind=kind, source_span=_span(text), parameters=parameters)


def _condition(
    *,
    text: str,
    kind: RuleConditionKind,
    parameters: tuple[RuleParameter, ...] = (),
) -> RuleCondition:
    return RuleCondition(kind=kind, source_span=_span(text), parameters=parameters)


def _aura_conditions(
    *,
    text: str,
    distance_inches: int,
    required_keyword: str | None = None,
) -> tuple[RuleCondition, ...]:
    conditions = [
        _condition(text=text, kind=RuleConditionKind.AURA),
        _condition(
            text=text,
            kind=RuleConditionKind.DISTANCE_PREDICATE,
            parameters=(
                _parameter("predicate", "within"),
                _parameter("object_kind", "unit"),
                _parameter("object_reference", "this_model"),
                _parameter("distance_inches", distance_inches),
            ),
        ),
    ]
    if required_keyword is not None:
        conditions.append(
            _condition(
                text=text,
                kind=RuleConditionKind.KEYWORD_GATE,
                parameters=(_parameter("required_keyword", required_keyword),),
            )
        )
    return tuple(conditions)


def _aura_target(
    *,
    text: str,
    allegiance: str,
) -> RuleTargetSpec:
    return RuleTargetSpec(
        kind=RuleTargetKind.AURA_UNITS,
        source_span=_span(text),
        parameters=(_parameter("allegiance", allegiance),),
    )


def _this_unit_target(text: str) -> RuleTargetSpec:
    return RuleTargetSpec(kind=RuleTargetKind.THIS_UNIT, source_span=_span(text))


def _this_model_target(text: str) -> RuleTargetSpec:
    return RuleTargetSpec(kind=RuleTargetKind.THIS_MODEL, source_span=_span(text))


def _effect(
    *,
    text: str,
    kind: RuleEffectKind,
    parameters: tuple[RuleParameter, ...],
) -> RuleEffectSpec:
    return RuleEffectSpec(kind=kind, source_span=_span(text), parameters=parameters)


def _until_end_battle_round(text: str) -> RuleDuration:
    return RuleDuration(
        kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
        source_span=_span(text),
        parameters=(
            _parameter("endpoint", "battle round"),
            _parameter("boundary", "end"),
        ),
    )


def _duration(text: str, kind: RuleDurationKind, **parameters: RuleParameterValue) -> RuleDuration:
    return RuleDuration(
        kind=kind,
        source_span=_span(text),
        parameters=tuple(_parameter(key, value) for key, value in parameters.items()),
    )


def _clause(
    *,
    clause_id: str,
    text: str,
    target: RuleTargetSpec | None,
    effects: tuple[RuleEffectSpec, ...],
    conditions: tuple[RuleCondition, ...] = (),
    trigger: RuleTrigger | None = None,
    duration: RuleDuration | None = None,
    template_id: str | None = None,
) -> RuleClause:
    return RuleClause(
        clause_id=clause_id,
        template_id=template_id,
        source_span=_span(text),
        trigger=trigger,
        conditions=conditions,
        target=target,
        effects=effects,
        duration=duration,
    )


def _dark_master_rule_ir() -> RuleIR:
    return _rule_ir(
        source_row_id=BELAKOR_DARK_MASTER_ROW_ID,
        normalized_text=_DARK_MASTER_TEXT,
        clauses=(
            _clause(
                clause_id="belakor-dark-master-shadow-of-chaos-aura",
                template_id="phase17c:aura",
                text=_DARK_MASTER_TEXT,
                conditions=_aura_conditions(text=_DARK_MASTER_TEXT, distance_inches=6),
                target=_aura_target(text=_DARK_MASTER_TEXT, allegiance="friendly"),
                effects=(
                    _effect(
                        text=_DARK_MASTER_TEXT,
                        kind=RuleEffectKind.SET_CONTEXTUAL_STATUS,
                        parameters=(
                            _parameter("status", "within_shadow_of_chaos"),
                            _parameter("rules_context", "shadow_of_chaos"),
                            _parameter("owner", "your_army"),
                        ),
                    ),
                ),
            ),
        ),
    )


def _shadow_form_rule_ir() -> RuleIR:
    return _rule_ir(
        source_row_id=BELAKOR_SHADOW_FORM_ROW_ID,
        normalized_text=_SHADOW_FORM_TEXT,
        clauses=(
            _clause(
                clause_id="belakor-shadow-form-battle-round-selection",
                text=_SHADOW_FORM_TEXT,
                trigger=_trigger(
                    text=_SHADOW_FORM_TEXT,
                    kind=RuleTriggerKind.TIMING_WINDOW,
                    parameters=(
                        _parameter("phase", "battle_round"),
                        _parameter("edge", "start"),
                        _parameter("timing_window", "battle_round_start"),
                    ),
                ),
                target=_this_unit_target(_SHADOW_FORM_TEXT),
                effects=(
                    _effect(
                        text=_SHADOW_FORM_TEXT,
                        kind=RuleEffectKind.SET_CONTEXTUAL_STATUS,
                        parameters=(
                            _parameter("status", "catalog_shadow_form_selection"),
                            _parameter("rules_context", "shadow_form"),
                            _parameter(
                                "selectable_source_ids",
                                BELAKOR_SHADOW_FORM_SELECTABLE_SOURCE_IDS,
                            ),
                        ),
                    ),
                ),
                duration=_until_end_battle_round(_SHADOW_FORM_TEXT),
            ),
        ),
    )


def _wreathed_in_shadows_rule_ir() -> RuleIR:
    return _keyworded_aura_rule_ir(
        source_row_id=BELAKOR_WREATHED_IN_SHADOWS_ROW_ID,
        normalized_text=_WREATHED_IN_SHADOWS_TEXT,
        clause_id_prefix="belakor-wreathed-in-shadows",
        distance_inches=6,
        allegiance="friendly",
        effect=_effect(
            text=_WREATHED_IN_SHADOWS_TEXT,
            kind=RuleEffectKind.SET_CONTEXTUAL_STATUS,
            parameters=(
                _parameter("status", "shooting_target_range_restriction"),
                _parameter("rules_context", "targeting"),
                _parameter("source_effect_kind", "wreathed_in_shadows"),
                _parameter("targeting_max_range_inches", 18),
            ),
        ),
    )


def _pall_of_despair_rule_ir() -> RuleIR:
    return _rule_ir(
        source_row_id=BELAKOR_PALL_OF_DESPAIR_ROW_ID,
        normalized_text=_PALL_OF_DESPAIR_TEXT,
        clauses=(
            _clause(
                clause_id="belakor-pall-of-despair-01-forced-battle-shock",
                template_id="phase17c:aura",
                text=_PALL_OF_DESPAIR_TEXT,
                conditions=_aura_conditions(text=_PALL_OF_DESPAIR_TEXT, distance_inches=9),
                target=_aura_target(text=_PALL_OF_DESPAIR_TEXT, allegiance="enemy"),
                effects=(
                    _effect(
                        text=_PALL_OF_DESPAIR_TEXT,
                        kind=RuleEffectKind.SET_CONTEXTUAL_STATUS,
                        parameters=(
                            _parameter("status", "battle_shock_forced_below_starting_strength"),
                            _parameter("rules_context", "battle_shock"),
                            _parameter("force_battle_shock_below_starting_strength", True),
                            _parameter(
                                "single_model_lost_wounds_counts_below_starting_strength",
                                True,
                            ),
                        ),
                    ),
                ),
                duration=_until_end_battle_round(_PALL_OF_DESPAIR_TEXT),
            ),
            _clause(
                clause_id="belakor-pall-of-despair-02-failed-battle-shock-heal",
                template_id="phase17c:aura",
                text=_PALL_OF_DESPAIR_TEXT,
                conditions=_aura_conditions(text=_PALL_OF_DESPAIR_TEXT, distance_inches=9),
                target=_aura_target(text=_PALL_OF_DESPAIR_TEXT, allegiance="enemy"),
                effects=(
                    _effect(
                        text=_PALL_OF_DESPAIR_TEXT,
                        kind=RuleEffectKind.RESTORE_LOST_WOUNDS,
                        parameters=(
                            _parameter("amount", "D3"),
                            _parameter("trigger", "target_failed_battle_shock"),
                            _parameter("source_reference", "aura_source"),
                        ),
                    ),
                ),
                duration=_until_end_battle_round(_PALL_OF_DESPAIR_TEXT),
            ),
        ),
    )


def _shadow_lord_rule_ir() -> RuleIR:
    return _keyworded_aura_rule_ir(
        source_row_id=BELAKOR_SHADOW_LORD_ROW_ID,
        normalized_text=_SHADOW_LORD_TEXT,
        clause_id_prefix="belakor-shadow-lord",
        distance_inches=6,
        allegiance="friendly",
        effect=_effect(
            text=_SHADOW_LORD_TEXT,
            kind=RuleEffectKind.REROLL_PERMISSION,
            parameters=(
                _parameter("roll_type", "hit"),
                _parameter("attack_role", "attacker"),
                _parameter("timing_window", "attack_sequence.hit"),
                _parameter("reroll_unmodified_value", 1),
            ),
        ),
    )


def _keyworded_aura_rule_ir(
    *,
    source_row_id: str,
    normalized_text: str,
    clause_id_prefix: str,
    distance_inches: int,
    allegiance: str,
    effect: RuleEffectSpec,
) -> RuleIR:
    clauses = tuple(
        _clause(
            clause_id=f"{clause_id_prefix}-{keyword.lower().replace(' ', '-')}",
            template_id="phase17c:aura",
            text=normalized_text,
            conditions=_aura_conditions(
                text=normalized_text,
                distance_inches=distance_inches,
                required_keyword=keyword,
            ),
            target=_aura_target(text=normalized_text, allegiance=allegiance),
            effects=(effect,),
            duration=_until_end_battle_round(normalized_text),
        )
        for keyword in (LEGIONES_DAEMONICA_KEYWORD, SHADOW_LEGION_KEYWORD)
    )
    return _rule_ir(
        source_row_id=source_row_id,
        normalized_text=normalized_text,
        clauses=clauses,
    )


def _passive_characteristic_rule_ir(
    *,
    source_row_id: str,
    keyword: str,
    characteristic: str,
    delta: int,
    weapon_names: tuple[str, ...] = (),
) -> RuleIR:
    text = _RULE_TEXT_BY_SOURCE_ROW_ID[source_row_id]
    effect_parameters = [
        _parameter("characteristic", characteristic),
        _parameter("delta", delta),
        _parameter("required_keyword", keyword),
    ]
    if weapon_names:
        effect_parameters.append(_parameter("weapon_names", weapon_names))
    return _rule_ir(
        source_row_id=source_row_id,
        normalized_text=text,
        clauses=(
            _clause(
                clause_id=f"daemon-prince-{source_row_id.replace(':', '-')}-modifier",
                text=text,
                conditions=(
                    _condition(
                        text=text,
                        kind=RuleConditionKind.KEYWORD_GATE,
                        parameters=(_parameter("required_keyword", keyword),),
                    ),
                ),
                target=_this_model_target(text),
                effects=(
                    _effect(
                        text=text,
                        kind=RuleEffectKind.MODIFY_CHARACTERISTIC,
                        parameters=tuple(effect_parameters),
                    ),
                ),
                duration=_duration(text, RuleDurationKind.WHILE_CONDITION_TRUE),
            ),
        ),
    )


def _daemonic_allegiance_rule_ir(source_row_id: str) -> RuleIR:
    text = _RULE_TEXT_BY_SOURCE_ROW_ID[source_row_id]
    datasheet_id = source_row_id.split(":", maxsplit=1)[0]
    selection_group_id = f"{datasheet_id}:daemonic-allegiance"
    return _rule_ir(
        source_row_id=source_row_id,
        normalized_text=text,
        clauses=(
            _clause(
                clause_id=f"daemonic-allegiance-{source_row_id.replace(':', '-')}",
                text=text,
                trigger=_trigger(
                    text=text,
                    kind=RuleTriggerKind.SETUP,
                    parameters=(_parameter("timing_window", "army_mustering"),),
                ),
                target=_this_model_target(text),
                effects=(
                    _effect(
                        text=text,
                        kind=RuleEffectKind.MUSTERING_SELECTION,
                        parameters=(
                            _parameter("selection_group_id", selection_group_id),
                            _parameter(
                                "selection_option_ids",
                                tuple(
                                    f"{selection_group_id}:{allegiance}"
                                    for allegiance in ("khorne", "tzeentch", "nurgle", "slaanesh")
                                ),
                            ),
                            _parameter("required", True),
                        ),
                    ),
                ),
                duration=_duration(text, RuleDurationKind.PERMANENT),
            ),
        ),
    )


def _daemon_prince_special_rule_ir(source_row_id: str) -> RuleIR:
    text = _RULE_TEXT_BY_SOURCE_ROW_ID[source_row_id]
    if source_row_id == "000001149:4":
        clause = _clause(
            clause_id="daemon-prince-daemonic-lord",
            text=text,
            conditions=(
                _condition(
                    text=text,
                    kind=RuleConditionKind.DISTANCE_PREDICATE,
                    parameters=(
                        _parameter("predicate", "within"),
                        _parameter("distance_inches", 3),
                        _parameter("allegiance", "friendly"),
                        _parameter(
                            "required_keyword_sequence",
                            ("LEGIONES DAEMONICA", "INFANTRY"),
                        ),
                    ),
                ),
            ),
            target=_this_model_target(text),
            effects=(
                _effect(
                    text=text,
                    kind=RuleEffectKind.GRANT_ABILITY,
                    parameters=(_parameter("ability", "lone_operative"),),
                ),
            ),
            duration=_duration(text, RuleDurationKind.WHILE_CONDITION_TRUE),
        )
    elif source_row_id == "000001149:5":
        clause = _clause(
            clause_id="daemon-prince-prince-of-darkness",
            template_id="phase17c:aura",
            text=text,
            conditions=_aura_conditions(
                text=text,
                distance_inches=6,
                required_keyword=LEGIONES_DAEMONICA_KEYWORD,
            ),
            target=_aura_target(text=text, allegiance="friendly"),
            effects=(
                _effect(
                    text=text,
                    kind=RuleEffectKind.GRANT_ABILITY,
                    parameters=(_parameter("ability", "stealth"),),
                ),
            ),
            duration=_duration(text, RuleDurationKind.WHILE_CONDITION_TRUE),
        )
    else:
        clause = _once_per_battle_clause(
            source_row_id=source_row_id,
            phase="any",
            characteristic="invulnerable_save",
            value=3,
        )
    return _rule_ir(source_row_id=source_row_id, normalized_text=text, clauses=(clause,))


def _once_per_battle_clause(
    *,
    source_row_id: str,
    phase: str,
    characteristic: str,
    value: int,
    weapon_names: tuple[str, ...] = (),
) -> RuleClause:
    text = _RULE_TEXT_BY_SOURCE_ROW_ID[source_row_id]
    effect_parameters = [
        _parameter("characteristic", characteristic),
        _parameter("value" if characteristic == "invulnerable_save" else "delta", value),
    ]
    if weapon_names:
        effect_parameters.append(_parameter("weapon_names", weapon_names))
    return _clause(
        clause_id=f"daemon-prince-{source_row_id.replace(':', '-')}-once-per-battle",
        text=text,
        trigger=_trigger(
            text=text,
            kind=RuleTriggerKind.TIMING_WINDOW,
            parameters=(_parameter("phase", phase), _parameter("edge", "start")),
        ),
        conditions=(
            _condition(
                text=text,
                kind=RuleConditionKind.FREQUENCY_LIMIT,
                parameters=(
                    _parameter("activation_kind", "optional_ability_use"),
                    _parameter("max_uses", 1),
                    _parameter("scope", "battle"),
                    _parameter("usage_subject", "this_model"),
                ),
            ),
        ),
        target=_this_model_target(text),
        effects=(
            _effect(
                text=text,
                kind=(
                    RuleEffectKind.SET_CHARACTERISTIC
                    if characteristic == "invulnerable_save"
                    else RuleEffectKind.MODIFY_CHARACTERISTIC
                ),
                parameters=tuple(effect_parameters),
            ),
        ),
        duration=_duration(
            text,
            RuleDurationKind.UNTIL_TIMING_ENDPOINT,
            endpoint="phase",
            boundary="end",
        ),
    )


def _winged_daemon_prince_rule_ir(source_row_id: str) -> RuleIR:
    text = _RULE_TEXT_BY_SOURCE_ROW_ID[source_row_id]
    if source_row_id == "000002758:4":
        clause = _once_per_battle_clause(
            source_row_id=source_row_id,
            phase="fight",
            characteristic="attacks",
            value=3,
            weapon_names=("Hellforged weapons - strike", "Hellforged weapons - sweep"),
        )
        return _rule_ir(source_row_id=source_row_id, normalized_text=text, clauses=(clause,))
    effects = tuple(
        _effect(
            text=text,
            kind=RuleEffectKind.GRANT_WEAPON_ABILITY,
            parameters=(
                _parameter("selection_group_id", "harbinger_of_death"),
                _parameter("selection_kind", "select_one"),
                _parameter("selection_option_id", option_id),
                _parameter("selection_option_index", option_index),
                _parameter("target_scope", "this_model"),
                _parameter("weapon_ability", ability),
                _parameter(
                    "weapon_names",
                    ("Hellforged weapons - strike", "Hellforged weapons - sweep"),
                ),
                *((_parameter("weapon_ability_value", ability_value),) if ability_value else ()),
            ),
        )
        for option_index, (option_id, ability, ability_value) in enumerate(
            (
                ("lethal_hits", "Lethal Hits", 0),
                ("precision", "Precision", 0),
                ("sustained_hits_1", "Sustained Hits", 1),
            ),
            start=1,
        )
    )
    return _rule_ir(
        source_row_id=source_row_id,
        normalized_text=text,
        clauses=(
            _clause(
                clause_id="daemon-prince-harbinger-of-death",
                text=text,
                trigger=_trigger(
                    text=text,
                    kind=RuleTriggerKind.UNIT_SELECTED,
                    parameters=(
                        _parameter("phase", "fight"),
                        _parameter("timing_window", "selected_to_fight"),
                    ),
                ),
                target=_this_model_target(text),
                effects=effects,
                duration=_duration(
                    text,
                    RuleDurationKind.UNTIL_TIMING_ENDPOINT,
                    endpoint="phase",
                    boundary="end",
                ),
            ),
        ),
    )


def _daemon_prince_characteristic_payloads() -> dict[str, RuleIRPayload]:
    rows: dict[str, RuleIRPayload] = {}
    for row_prefix, first_line in (("000001149", 8), ("000002758", 7)):
        specifications = (
            (
                "KHORNE",
                "strength",
                2,
                ("Hellforged weapons - strike", "Hellforged weapons - sweep"),
            ),
            ("TZEENTCH", "attacks", 3, ("Infernal cannon",)),
            ("NURGLE", "toughness", 1, ()),
            ("SLAANESH", "movement", 2, ()),
        )
        for line_offset, (keyword, characteristic, delta, weapon_names) in enumerate(
            specifications
        ):
            source_row_id = f"{row_prefix}:{first_line + line_offset}"
            rows[source_row_id] = _payload(
                _passive_characteristic_rule_ir(
                    source_row_id=source_row_id,
                    keyword=keyword,
                    characteristic=characteristic,
                    delta=delta,
                    weapon_names=weapon_names,
                )
            )
    return rows


_RULE_IR_PAYLOADS_BY_SOURCE_ROW_ID = MappingProxyType(
    {
        BELAKOR_DARK_MASTER_ROW_ID: _payload(_dark_master_rule_ir()),
        BELAKOR_SHADOW_FORM_ROW_ID: _payload(_shadow_form_rule_ir()),
        BELAKOR_WREATHED_IN_SHADOWS_ROW_ID: _payload(_wreathed_in_shadows_rule_ir()),
        BELAKOR_PALL_OF_DESPAIR_ROW_ID: _payload(_pall_of_despair_rule_ir()),
        BELAKOR_SHADOW_LORD_ROW_ID: _payload(_shadow_lord_rule_ir()),
        "000001149:4": _payload(_daemon_prince_special_rule_ir("000001149:4")),
        "000001149:5": _payload(_daemon_prince_special_rule_ir("000001149:5")),
        "000001149:6": _payload(_daemon_prince_special_rule_ir("000001149:6")),
        "000001149:7": _payload(_daemonic_allegiance_rule_ir("000001149:7")),
        "000002758:4": _payload(_winged_daemon_prince_rule_ir("000002758:4")),
        "000002758:5": _payload(_winged_daemon_prince_rule_ir("000002758:5")),
        "000002758:6": _payload(_daemonic_allegiance_rule_ir("000002758:6")),
        SOUL_GRINDER_ALLEGIANCE_ROW_ID: _payload(
            _daemonic_allegiance_rule_ir(SOUL_GRINDER_ALLEGIANCE_ROW_ID)
        ),
        **_daemon_prince_characteristic_payloads(),
    }
)
