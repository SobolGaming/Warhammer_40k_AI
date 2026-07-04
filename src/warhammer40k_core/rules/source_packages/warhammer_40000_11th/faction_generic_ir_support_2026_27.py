from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.rules.rule_ir import (
    RuleClausePayload,
    RuleConditionPayload,
    RuleEffectKind,
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
    WEAPON_ABILITY_GRANT_TEMPLATE_ID,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27,
    faction_more_dakka_ir_support_2026_27,
    faction_subrules_2026_27,
)

SOURCE_PACKAGE_ID = "gw-11e-phase17e-faction-coverage-2026-27"
_SUPPORTED_CONDITIONAL_WEAPON_ABILITY_ENHANCEMENT_SOURCE_ROW_IDS = frozenset(
    {
        "enhancement:chaos-space-marines:renegade-warband:000010694003",
        "enhancement:imperial-knights:freeblade-company:000010755003",
        "enhancement:necrons:starshatter-arsenal:000009749003",
        "enhancement:orks:freebooter-krew:000010712003",
        "enhancement:orks:more-dakka:000009991002",
        "enhancement:orks:more-dakka:000009991003",
        "enhancement:space-marines:ceramite-sentinels:000010759004",
    }
)
_SUPPORTED_GRANT_ABILITY_ENHANCEMENT_SOURCE_ROW_IDS = frozenset(
    {
        "enhancement:genestealer-cults:outlander-claw:000009079002",
        "enhancement:orks:more-dakka:000009991005",
        "enhancement:tyranids:warrior-bioform-onslaught:000009737005",
    }
)
_SUPPORTED_CHARACTERISTIC_MODIFICATION_ENHANCEMENT_SOURCE_ROW_IDS = frozenset(
    {
        "enhancement:necrons:cryptek-conclave:000010664004",
    }
)
_SUPPORTED_DICE_ROLL_MODIFICATION_ENHANCEMENT_SOURCE_ROW_IDS = frozenset(
    {
        "enhancement:adeptus-custodes:talons-of-the-emperor:000008921004",
        "enhancement:adeptus-custodes:talons-of-the-emperor:000008921005",
        "enhancement:chaos-space-marines:fellhammer-siege-host:000008976004",
        "enhancement:genestealer-cults:host-of-ascension:000009067005",
        "enhancement:leagues-of-votann:persecution-prospect:000010439002",
        "enhancement:necrons:obeisance-phalanx:000008550004",
        "enhancement:orks:more-dakka:000009991004",
    }
)
_SUPPORTED_CONDITIONAL_WEAPON_ABILITY_TEMPLATE_IDS = frozenset(
    {
        KEYWORD_GATE_TEMPLATE_ID,
        WEAPON_ABILITY_GRANT_TEMPLATE_ID,
    }
)
_SUPPORTED_GRANT_ABILITY_TEMPLATE_IDS = frozenset(
    {
        GRANT_ABILITY_TEMPLATE_ID,
        KEYWORD_GATE_TEMPLATE_ID,
    }
)
_SUPPORTED_CHARACTERISTIC_MODIFICATION_TEMPLATE_IDS = frozenset(
    {
        CHARACTERISTIC_MODIFIER_TEMPLATE_ID,
        KEYWORD_GATE_TEMPLATE_ID,
    }
)
_SUPPORTED_DICE_ROLL_MODIFICATION_TEMPLATE_IDS = frozenset(
    {
        DICE_ROLL_MODIFIER_TEMPLATE_ID,
        KEYWORD_GATE_TEMPLATE_ID,
    }
)


class Phase17FGenericIrSupportError(ValueError):
    """Raised when Phase 17F generic IR support metadata is inconsistent."""


def generic_supported_enhancement_rule_ir(
    source_row: faction_subrules_2026_27.SourceEnhancementRow,
) -> RuleIR | None:
    if type(source_row) is not faction_subrules_2026_27.SourceEnhancementRow:
        raise Phase17FGenericIrSupportError("Generic enhancement support requires source row.")
    if source_row.source_row_id not in _supported_enhancement_source_row_ids():
        return None
    rule_ir = generic_rule_ir_by_coverage_descriptor_id(f"phase17e:{source_row.source_row_id}")
    _validate_supported_enhancement_ir(
        rule_ir=rule_ir,
        source_row=source_row,
    )
    return rule_ir


def generic_supported_enhancement_rule_ir_hash(
    source_row: faction_subrules_2026_27.SourceEnhancementRow,
) -> str | None:
    rule_ir = generic_supported_enhancement_rule_ir(source_row)
    if rule_ir is None:
        return None
    return rule_ir.ir_hash()


def generic_supported_detachment_rule_ir_hash(
    detachment_row: faction_detachments_2026_27.SourceDetachmentRow,
) -> str | None:
    if type(detachment_row) is not faction_detachments_2026_27.SourceDetachmentRow:
        raise Phase17FGenericIrSupportError("Generic detachment support requires source row.")
    descriptor_id = f"phase17e:{detachment_row.faction_id}:{detachment_row.detachment_id}:rule"
    return faction_more_dakka_ir_support_2026_27.coverage_rule_ir_hash_by_descriptor_id(
        descriptor_id
    )


def generic_supported_stratagem_rule_ir_hash(
    source_row: faction_subrules_2026_27.SourceStratagemRow,
) -> str | None:
    if type(source_row) is not faction_subrules_2026_27.SourceStratagemRow:
        raise Phase17FGenericIrSupportError("Generic Stratagem support requires source row.")
    return faction_more_dakka_ir_support_2026_27.coverage_rule_ir_hash_by_descriptor_id(
        f"phase17e:{source_row.source_row_id}"
    )


def generic_rule_ir_by_coverage_descriptor_id(coverage_descriptor_id: str) -> RuleIR:
    descriptor_id = _validate_identifier("coverage_descriptor_id", coverage_descriptor_id)
    payload = _STATIC_GENERIC_RULE_IR_PAYLOADS_BY_COVERAGE_DESCRIPTOR_ID.get(descriptor_id)
    if payload is None:
        payload = faction_more_dakka_ir_support_2026_27.coverage_rule_ir_payload_by_descriptor_id(
            descriptor_id
        )
    if payload is None:
        raise Phase17FGenericIrSupportError("Generic IR coverage descriptor is not registered.")
    return RuleIR.from_payload(payload)


def generic_rule_ir_hash_by_coverage_descriptor_id(coverage_descriptor_id: str) -> str:
    return generic_rule_ir_by_coverage_descriptor_id(coverage_descriptor_id).ir_hash()


def supported_conditional_weapon_ability_enhancement_source_row_ids() -> tuple[str, ...]:
    return tuple(sorted(_SUPPORTED_CONDITIONAL_WEAPON_ABILITY_ENHANCEMENT_SOURCE_ROW_IDS))


def supported_grant_ability_enhancement_source_row_ids() -> tuple[str, ...]:
    return tuple(sorted(_SUPPORTED_GRANT_ABILITY_ENHANCEMENT_SOURCE_ROW_IDS))


def supported_characteristic_modification_enhancement_source_row_ids() -> tuple[str, ...]:
    return tuple(sorted(_SUPPORTED_CHARACTERISTIC_MODIFICATION_ENHANCEMENT_SOURCE_ROW_IDS))


def supported_dice_roll_modification_enhancement_source_row_ids() -> tuple[str, ...]:
    return tuple(sorted(_SUPPORTED_DICE_ROLL_MODIFICATION_ENHANCEMENT_SOURCE_ROW_IDS))


def supported_generic_enhancement_source_row_ids() -> tuple[str, ...]:
    return tuple(sorted(_supported_enhancement_source_row_ids()))


def _validate_supported_enhancement_ir(
    *,
    rule_ir: RuleIR,
    source_row: faction_subrules_2026_27.SourceEnhancementRow,
) -> None:
    if source_row.source_row_id in _SUPPORTED_CONDITIONAL_WEAPON_ABILITY_ENHANCEMENT_SOURCE_ROW_IDS:
        _validate_supported_effect_family_ir(
            rule_ir=rule_ir,
            source_row=source_row,
            expected_template_ids=_SUPPORTED_CONDITIONAL_WEAPON_ABILITY_TEMPLATE_IDS,
            effect_kind=RuleEffectKind.GRANT_WEAPON_ABILITY,
            effect_family_name="weapon ability",
            expected_effect_count=(
                2 if source_row.source_row_id == "enhancement:orks:more-dakka:000009991002" else 1
            ),
        )
    elif source_row.source_row_id in _SUPPORTED_GRANT_ABILITY_ENHANCEMENT_SOURCE_ROW_IDS:
        _validate_supported_effect_family_ir(
            rule_ir=rule_ir,
            source_row=source_row,
            expected_template_ids=_SUPPORTED_GRANT_ABILITY_TEMPLATE_IDS,
            effect_kind=RuleEffectKind.GRANT_ABILITY,
            effect_family_name="ability",
            expected_effect_count=1,
        )
    elif (
        source_row.source_row_id
        in _SUPPORTED_CHARACTERISTIC_MODIFICATION_ENHANCEMENT_SOURCE_ROW_IDS
    ):
        _validate_supported_effect_family_ir(
            rule_ir=rule_ir,
            source_row=source_row,
            expected_template_ids=_SUPPORTED_CHARACTERISTIC_MODIFICATION_TEMPLATE_IDS,
            effect_kind=RuleEffectKind.MODIFY_CHARACTERISTIC,
            effect_family_name="characteristic modifier",
            expected_effect_count=1,
        )
    elif source_row.source_row_id in _SUPPORTED_DICE_ROLL_MODIFICATION_ENHANCEMENT_SOURCE_ROW_IDS:
        _validate_supported_effect_family_ir(
            rule_ir=rule_ir,
            source_row=source_row,
            expected_template_ids=_SUPPORTED_DICE_ROLL_MODIFICATION_TEMPLATE_IDS,
            effect_kind=RuleEffectKind.MODIFY_DICE_ROLL,
            effect_family_name="dice roll modifier",
            expected_effect_count=1,
        )
    else:
        raise Phase17FGenericIrSupportError("Generic enhancement support row is not registered.")


def _validate_supported_effect_family_ir(
    *,
    rule_ir: RuleIR,
    source_row: faction_subrules_2026_27.SourceEnhancementRow,
    expected_template_ids: frozenset[str],
    effect_kind: RuleEffectKind,
    effect_family_name: str,
    expected_effect_count: int,
) -> None:
    if not rule_ir.is_supported:
        raise Phase17FGenericIrSupportError(
            "Generic enhancement support row must deserialize to supported RuleIR."
        )
    template_ids = frozenset(
        clause.template_id for clause in rule_ir.clauses if clause.template_id is not None
    )
    if template_ids != expected_template_ids:
        raise Phase17FGenericIrSupportError(
            "Generic enhancement support row must use only its registered template family."
        )
    effect_count = 0
    for clause in rule_ir.clauses:
        if clause.unsupported_reason is not None or clause.diagnostics:
            raise Phase17FGenericIrSupportError(
                "Generic enhancement support row includes unsupported clause diagnostics."
            )
        for effect in clause.effects:
            if effect.kind is effect_kind:
                effect_count += 1
    if effect_count != expected_effect_count:
        raise Phase17FGenericIrSupportError(
            f"Generic enhancement support row has an unexpected {effect_family_name} effect count."
        )
    expected_source_id = f"{SOURCE_PACKAGE_ID}:phase17e:{source_row.source_row_id}:source-text"
    if rule_ir.source_id != expected_source_id:
        raise Phase17FGenericIrSupportError(
            "Generic enhancement support row produced an unexpected source ID."
        )


def _supported_enhancement_source_row_ids() -> frozenset[str]:
    return frozenset(
        {
            *_SUPPORTED_CONDITIONAL_WEAPON_ABILITY_ENHANCEMENT_SOURCE_ROW_IDS,
            *_SUPPORTED_GRANT_ABILITY_ENHANCEMENT_SOURCE_ROW_IDS,
            *_SUPPORTED_CHARACTERISTIC_MODIFICATION_ENHANCEMENT_SOURCE_ROW_IDS,
            *_SUPPORTED_DICE_ROLL_MODIFICATION_ENHANCEMENT_SOURCE_ROW_IDS,
        }
    )


def _coverage_descriptor_id(source_row_id: str) -> str:
    return f"phase17e:{source_row_id}"


def _source_text_id(source_row_id: str) -> str:
    return f"{SOURCE_PACKAGE_ID}:phase17e:{source_row_id}:source-text"


def _rule_ir_payload(
    *,
    source_row_id: str,
    normalized_text: str,
    clauses: tuple[RuleClausePayload, ...],
    ir_hash: str,
) -> RuleIRPayload:
    source_id = _source_text_id(source_row_id)
    return cast(
        RuleIRPayload,
        {
            "rule_id": source_id,
            "source_id": source_id,
            "normalized_text": normalized_text,
            "parser_version": "phase17c-rule-parser-v1",
            "schema_version": "phase17c-rule-ir-v1",
            "clauses": list(clauses),
            "diagnostics": [],
            "ir_hash": ir_hash,
        },
    )


def _keyword_gate_clause(
    *,
    source_row_id: str,
    clause_number: int,
    source_text: str,
    source_start: int,
    source_end: int,
    keyword_text: str,
    keyword_start: int,
    keyword_end: int,
    required_keywords: tuple[str, ...],
) -> RuleClausePayload:
    return cast(
        RuleClausePayload,
        {
            "clause_id": _clause_id(source_row_id, clause_number),
            "template_id": KEYWORD_GATE_TEMPLATE_ID,
            "source_span": _span(source_text, source_start, source_end),
            "trigger": None,
            "conditions": [
                _keyword_gate_condition(
                    source_text=keyword_text,
                    source_start=keyword_start,
                    source_end=keyword_end,
                    required_keyword=required_keyword,
                )
                for required_keyword in required_keywords
            ],
            "target": None,
            "effects": [],
            "duration": None,
            "unsupported_reason": None,
            "diagnostics": [],
        },
    )


def _weapon_ability_grant_clause(
    *,
    source_row_id: str,
    clause_number: int,
    source_text: str,
    source_start: int,
    source_end: int,
    target_kind: str,
    target_text: str,
    target_start: int,
    target_end: int,
    effect_text: str,
    effect_start: int,
    effect_end: int,
    weapon_ability: str,
    weapon_ability_value: int | None = None,
) -> RuleClausePayload:
    parameters = [_parameter("weapon_ability", weapon_ability)]
    if weapon_ability_value is not None:
        parameters.append(_parameter("weapon_ability_value", weapon_ability_value))
    parameters.append(_parameter("weapon_scope", "ranged"))
    return _effect_clause(
        source_row_id=source_row_id,
        clause_number=clause_number,
        template_id=WEAPON_ABILITY_GRANT_TEMPLATE_ID,
        source_text=source_text,
        source_start=source_start,
        source_end=source_end,
        target=_target(target_kind, target_text, target_start, target_end),
        effect=_effect("grant_weapon_ability", effect_text, effect_start, effect_end, parameters),
    )


def _grant_ability_clause(
    *,
    source_row_id: str,
    clause_number: int,
    source_text: str,
    source_start: int,
    source_end: int,
    target_text: str,
    target_start: int,
    target_end: int,
    effect_text: str,
    effect_start: int,
    effect_end: int,
    ability: str,
) -> RuleClausePayload:
    return _effect_clause(
        source_row_id=source_row_id,
        clause_number=clause_number,
        template_id=GRANT_ABILITY_TEMPLATE_ID,
        source_text=source_text,
        source_start=source_start,
        source_end=source_end,
        target=_target("this_unit", target_text, target_start, target_end),
        effect=_effect(
            "grant_ability",
            effect_text,
            effect_start,
            effect_end,
            [_parameter("ability", ability)],
        ),
    )


def _characteristic_modifier_clause(
    *,
    source_row_id: str,
    clause_number: int,
    source_text: str,
    source_start: int,
    source_end: int,
    target_text: str,
    target_start: int,
    target_end: int,
    effect_text: str,
    effect_start: int,
    effect_end: int,
    characteristic: str,
    delta: int,
) -> RuleClausePayload:
    return _effect_clause(
        source_row_id=source_row_id,
        clause_number=clause_number,
        template_id=CHARACTERISTIC_MODIFIER_TEMPLATE_ID,
        source_text=source_text,
        source_start=source_start,
        source_end=source_end,
        target=_target("this_unit", target_text, target_start, target_end),
        effect=_effect(
            "modify_characteristic",
            effect_text,
            effect_start,
            effect_end,
            [
                _parameter("characteristic", characteristic),
                _parameter("delta", delta),
            ],
        ),
    )


def _dice_roll_modifier_clause(
    *,
    source_row_id: str,
    clause_number: int,
    source_text: str,
    source_start: int,
    source_end: int,
    trigger_text: str,
    trigger_start: int,
    trigger_end: int,
    target_kind: str,
    target_text: str,
    target_start: int,
    target_end: int,
    effect_text: str,
    effect_start: int,
    effect_end: int,
    roll_type: str,
    delta: int,
    conditions: tuple[RuleConditionPayload, ...] = (),
) -> RuleClausePayload:
    return _effect_clause(
        source_row_id=source_row_id,
        clause_number=clause_number,
        template_id=DICE_ROLL_MODIFIER_TEMPLATE_ID,
        source_text=source_text,
        source_start=source_start,
        source_end=source_end,
        trigger=_dice_roll_trigger(
            source_text=trigger_text,
            source_start=trigger_start,
            source_end=trigger_end,
            roll_type=roll_type,
        ),
        conditions=conditions,
        target=_target(target_kind, target_text, target_start, target_end),
        effect=_effect(
            "modify_dice_roll",
            effect_text,
            effect_start,
            effect_end,
            [
                _parameter("delta", delta),
                _parameter("roll_type", roll_type),
            ],
        ),
    )


def _effect_clause(
    *,
    source_row_id: str,
    clause_number: int,
    template_id: str,
    source_text: str,
    source_start: int,
    source_end: int,
    target: RuleTargetSpecPayload,
    effect: RuleEffectSpecPayload,
    trigger: RuleTriggerPayload | None = None,
    conditions: tuple[RuleConditionPayload, ...] = (),
) -> RuleClausePayload:
    return cast(
        RuleClausePayload,
        {
            "clause_id": _clause_id(source_row_id, clause_number),
            "template_id": template_id,
            "source_span": _span(source_text, source_start, source_end),
            "trigger": trigger,
            "conditions": list(conditions),
            "target": target,
            "effects": [effect],
            "duration": None,
            "unsupported_reason": None,
            "diagnostics": [],
        },
    )


def _dice_roll_trigger(
    *,
    source_text: str,
    source_start: int,
    source_end: int,
    roll_type: str,
) -> RuleTriggerPayload:
    return cast(
        RuleTriggerPayload,
        {
            "kind": "dice_roll",
            "source_span": _span(source_text, source_start, source_end),
            "parameters": [_parameter("roll_type", roll_type)],
        },
    )


def _keyword_gate_condition(
    *,
    source_text: str,
    source_start: int,
    source_end: int,
    required_keyword: str,
) -> RuleConditionPayload:
    return cast(
        RuleConditionPayload,
        {
            "kind": "keyword_gate",
            "source_span": _span(source_text, source_start, source_end),
            "parameters": [_parameter("required_keyword", required_keyword)],
        },
    )


def _distance_predicate_condition(
    *,
    source_text: str,
    source_start: int,
    source_end: int,
    distance_inches: float,
    predicate: str,
    qualifier: str | None = None,
) -> RuleConditionPayload:
    return cast(
        RuleConditionPayload,
        {
            "kind": "distance_predicate",
            "source_span": _span(source_text, source_start, source_end),
            "parameters": [
                _parameter("distance_inches", distance_inches),
                _parameter("predicate", predicate),
                _parameter("qualifier", qualifier),
            ],
        },
    )


def _target(
    kind: str, source_text: str, source_start: int, source_end: int
) -> RuleTargetSpecPayload:
    return cast(
        RuleTargetSpecPayload,
        {
            "kind": kind,
            "source_span": _span(source_text, source_start, source_end),
            "parameters": [],
        },
    )


def _effect(
    kind: str,
    source_text: str,
    source_start: int,
    source_end: int,
    parameters: list[RuleParameterPayload],
) -> RuleEffectSpecPayload:
    return cast(
        RuleEffectSpecPayload,
        {
            "kind": kind,
            "source_span": _span(source_text, source_start, source_end),
            "parameters": parameters,
        },
    )


def _parameter(key: str, value: str | int | float | None) -> RuleParameterPayload:
    return cast(RuleParameterPayload, {"key": key, "value": value})


def _span(text: str, start: int, end: int) -> dict[str, str | int]:
    return {"text": text, "start": start, "end": end}


def _clause_id(source_row_id: str, clause_number: int) -> str:
    return f"{_source_text_id(source_row_id)}:clause:{clause_number:03d}"


def _static_generic_rule_ir_payloads() -> Mapping[str, RuleIRPayload]:
    payloads: dict[str, RuleIRPayload] = {}
    for source_row_id, payload in _STATIC_GENERIC_RULE_IR_PAYLOAD_ROWS:
        descriptor_id = _coverage_descriptor_id(source_row_id)
        if descriptor_id in payloads:
            raise Phase17FGenericIrSupportError(
                "Static generic IR coverage descriptor IDs must be unique."
            )
        payloads[descriptor_id] = payload
    return MappingProxyType(payloads)


_ADEPTUS_CUSTODES_TALONS_GIFT_OF_TERRAN_ARTIFICE = (
    "enhancement:adeptus-custodes:talons-of-the-emperor:000008921004"
)
_ADEPTUS_CUSTODES_TALONS_RADIANT_MANTLE = (
    "enhancement:adeptus-custodes:talons-of-the-emperor:000008921005"
)
_CHAOS_SPACE_MARINES_RENEGADE_WARBAND_EYES_OF_THE_HUNTER = (
    "enhancement:chaos-space-marines:renegade-warband:000010694003"
)
_CHAOS_SPACE_MARINES_FELLHAMMER_IRONBOUND_ENMITY = (
    "enhancement:chaos-space-marines:fellhammer-siege-host:000008976004"
)
_GENESTEALER_CULTS_OUTLANDER_CLAW_SERPENTINE_TACTICS = (
    "enhancement:genestealer-cults:outlander-claw:000009079002"
)
_GENESTEALER_CULTS_HOST_ASSASSINATION_EDICT = (
    "enhancement:genestealer-cults:host-of-ascension:000009067005"
)
_IMPERIAL_KNIGHTS_FREEBLADE_COMPANY_MYSTERIOUS_GUARDIAN = (
    "enhancement:imperial-knights:freeblade-company:000010755003"
)
_LEAGUES_OF_VOTANN_PERSECUTION_EYE_FOR_WEAKNESS = (
    "enhancement:leagues-of-votann:persecution-prospect:000010439002"
)
_NECRONS_CRYPTEK_CONCLAVE_GAUNTLET_OF_COMPRESSION = (
    "enhancement:necrons:cryptek-conclave:000010664004"
)
_NECRONS_OBEISANCE_PHALANX_WARRIOR_NOBLE = "enhancement:necrons:obeisance-phalanx:000008550004"
_NECRONS_STARSHATTER_ARSENAL_MINIATURISED_NEBULOSCOPE = (
    "enhancement:necrons:starshatter-arsenal:000009749003"
)
_ORKS_FREEBOOTER_KREW_SNEAKY_SNEAKIN = "enhancement:orks:freebooter-krew:000010712003"
_ORKS_MORE_DAKKA_KUNNIN_BUT_BRUTAL = "enhancement:orks:more-dakka:000009991003"
_ORKS_MORE_DAKKA_SUPA_CYBORK_BODY = "enhancement:orks:more-dakka:000009991005"
_ORKS_MORE_DAKKA_TARGETIN_SQUIGS = "enhancement:orks:more-dakka:000009991004"
_SPACE_MARINES_CERAMITE_SENTINELS_AUSPEX_INTERFACE = (
    "enhancement:space-marines:ceramite-sentinels:000010759004"
)
_TYRANIDS_WARRIOR_BIOFORM_ONSLAUGHT_ELEVATED_MIGHT = (
    "enhancement:tyranids:warrior-bioform-onslaught:000009737005"
)

_STATIC_GENERIC_RULE_IR_PAYLOAD_ROWS: tuple[tuple[str, RuleIRPayload], ...] = (
    (
        _ADEPTUS_CUSTODES_TALONS_GIFT_OF_TERRAN_ARTIFICE,
        _rule_ir_payload(
            source_row_id=_ADEPTUS_CUSTODES_TALONS_GIFT_OF_TERRAN_ARTIFICE,
            normalized_text=(
                "ADEPTUS CUSTODES model only. Each time the bearer makes a melee "
                "attack, add 1 to the Wound roll."
            ),
            clauses=(
                _keyword_gate_clause(
                    source_row_id=_ADEPTUS_CUSTODES_TALONS_GIFT_OF_TERRAN_ARTIFICE,
                    clause_number=1,
                    source_text="ADEPTUS CUSTODES model only.",
                    source_start=0,
                    source_end=28,
                    keyword_text="ADEPTUS CUSTODES model",
                    keyword_start=0,
                    keyword_end=22,
                    required_keywords=("ADEPTUS_CUSTODES",),
                ),
                _dice_roll_modifier_clause(
                    source_row_id=_ADEPTUS_CUSTODES_TALONS_GIFT_OF_TERRAN_ARTIFICE,
                    clause_number=2,
                    source_text=(
                        "Each time the bearer makes a melee attack, add 1 to the Wound roll."
                    ),
                    source_start=29,
                    source_end=96,
                    trigger_text=(
                        "Each time the bearer makes a melee attack, add 1 to the Wound roll"
                    ),
                    trigger_start=29,
                    trigger_end=95,
                    target_kind="this_model",
                    target_text="the bearer",
                    target_start=39,
                    target_end=49,
                    effect_text="add 1 to the Wound roll",
                    effect_start=72,
                    effect_end=95,
                    roll_type="wound",
                    delta=1,
                ),
            ),
            ir_hash="a5403b9ea1f2b173a9966d5ae275398259e813d3e400a34118d16c0184bbf056",
        ),
    ),
    (
        _ADEPTUS_CUSTODES_TALONS_RADIANT_MANTLE,
        _rule_ir_payload(
            source_row_id=_ADEPTUS_CUSTODES_TALONS_RADIANT_MANTLE,
            normalized_text=(
                "ADEPTUS CUSTODES model only. Each time an attack targets the bearer's "
                'unit, if the attacking model is within 12", subtract 1 from the Hit roll.'
            ),
            clauses=(
                _keyword_gate_clause(
                    source_row_id=_ADEPTUS_CUSTODES_TALONS_RADIANT_MANTLE,
                    clause_number=1,
                    source_text="ADEPTUS CUSTODES model only.",
                    source_start=0,
                    source_end=28,
                    keyword_text="ADEPTUS CUSTODES model",
                    keyword_start=0,
                    keyword_end=22,
                    required_keywords=("ADEPTUS_CUSTODES",),
                ),
                _dice_roll_modifier_clause(
                    source_row_id=_ADEPTUS_CUSTODES_TALONS_RADIANT_MANTLE,
                    clause_number=2,
                    source_text=(
                        "Each time an attack targets the bearer's unit, if the attacking "
                        'model is within 12", subtract 1 from the Hit roll.'
                    ),
                    source_start=29,
                    source_end=143,
                    trigger_text=(
                        "Each time an attack targets the bearer's unit, if the attacking "
                        'model is within 12", subtract 1 from the Hit roll'
                    ),
                    trigger_start=29,
                    trigger_end=142,
                    conditions=(
                        _distance_predicate_condition(
                            source_text='within 12"',
                            source_start=102,
                            source_end=112,
                            distance_inches=12.0,
                            predicate="within",
                        ),
                    ),
                    target_kind="this_unit",
                    target_text="the bearer's unit",
                    target_start=57,
                    target_end=74,
                    effect_text="subtract 1 from the Hit roll",
                    effect_start=114,
                    effect_end=142,
                    roll_type="hit",
                    delta=-1,
                ),
            ),
            ir_hash="9167ed849955784ae4fae5c660bda08e471e286c22f0aaff9c447d0d6dd27de4",
        ),
    ),
    (
        _CHAOS_SPACE_MARINES_FELLHAMMER_IRONBOUND_ENMITY,
        _rule_ir_payload(
            source_row_id=_CHAOS_SPACE_MARINES_FELLHAMMER_IRONBOUND_ENMITY,
            normalized_text=(
                "HERETIC ASTARTES model only. Each time the bearer makes an attack "
                "while within range of an objective marker, add 1 to the Wound roll."
            ),
            clauses=(
                _keyword_gate_clause(
                    source_row_id=_CHAOS_SPACE_MARINES_FELLHAMMER_IRONBOUND_ENMITY,
                    clause_number=1,
                    source_text="HERETIC ASTARTES model only.",
                    source_start=0,
                    source_end=28,
                    keyword_text="HERETIC ASTARTES model",
                    keyword_start=0,
                    keyword_end=22,
                    required_keywords=("HERETIC_ASTARTES",),
                ),
                _dice_roll_modifier_clause(
                    source_row_id=_CHAOS_SPACE_MARINES_FELLHAMMER_IRONBOUND_ENMITY,
                    clause_number=2,
                    source_text=(
                        "Each time the bearer makes an attack while within range of an "
                        "objective marker, add 1 to the Wound roll."
                    ),
                    source_start=29,
                    source_end=133,
                    trigger_text=(
                        "Each time the bearer makes an attack while within range of an "
                        "objective marker, add 1 to the Wound roll"
                    ),
                    trigger_start=29,
                    trigger_end=132,
                    target_kind="this_model",
                    target_text="the bearer",
                    target_start=39,
                    target_end=49,
                    effect_text="add 1 to the Wound roll",
                    effect_start=109,
                    effect_end=132,
                    roll_type="wound",
                    delta=1,
                ),
            ),
            ir_hash="f0480d2475911787aa79e6acae84f9c6f2c5d87e4ab0eb3e56cbbf6e202dc25a",
        ),
    ),
    (
        _GENESTEALER_CULTS_HOST_ASSASSINATION_EDICT,
        _rule_ir_payload(
            source_row_id=_GENESTEALER_CULTS_HOST_ASSASSINATION_EDICT,
            normalized_text=(
                "GENESTEALER CULTS model only. Each time a model in the bearer's unit "
                "makes an attack that targets a CHARACTER unit, add 1 to the Hit roll"
            ),
            clauses=(
                _keyword_gate_clause(
                    source_row_id=_GENESTEALER_CULTS_HOST_ASSASSINATION_EDICT,
                    clause_number=1,
                    source_text="GENESTEALER CULTS model only.",
                    source_start=0,
                    source_end=29,
                    keyword_text="GENESTEALER CULTS model",
                    keyword_start=0,
                    keyword_end=23,
                    required_keywords=("GENESTEALER_CULTS",),
                ),
                _dice_roll_modifier_clause(
                    source_row_id=_GENESTEALER_CULTS_HOST_ASSASSINATION_EDICT,
                    clause_number=2,
                    source_text=(
                        "Each time a model in the bearer's unit makes an attack that "
                        "targets a CHARACTER unit, add 1 to the Hit roll"
                    ),
                    source_start=30,
                    source_end=137,
                    trigger_text=(
                        "Each time a model in the bearer's unit makes an attack that "
                        "targets a CHARACTER unit, add 1 to the Hit roll"
                    ),
                    trigger_start=30,
                    trigger_end=137,
                    conditions=(
                        _keyword_gate_condition(
                            source_text="CHARACTER unit",
                            source_start=100,
                            source_end=114,
                            required_keyword="CHARACTER",
                        ),
                    ),
                    target_kind="this_unit",
                    target_text="the bearer's unit",
                    target_start=51,
                    target_end=68,
                    effect_text="add 1 to the Hit roll",
                    effect_start=116,
                    effect_end=137,
                    roll_type="hit",
                    delta=1,
                ),
            ),
            ir_hash="ace002fc22bfb8831b1c63df2e9b476cc4003b891b9a265a3515375cb53e05a4",
        ),
    ),
    (
        _LEAGUES_OF_VOTANN_PERSECUTION_EYE_FOR_WEAKNESS,
        _rule_ir_payload(
            source_row_id=_LEAGUES_OF_VOTANN_PERSECUTION_EYE_FOR_WEAKNESS,
            normalized_text=(
                "LEAGUES OF VOTANN model only. Each time a model in the bearer's unit "
                "makes an attack that targets an assailed unit, add 1 to the Wound roll."
            ),
            clauses=(
                _keyword_gate_clause(
                    source_row_id=_LEAGUES_OF_VOTANN_PERSECUTION_EYE_FOR_WEAKNESS,
                    clause_number=1,
                    source_text="LEAGUES OF VOTANN model only.",
                    source_start=0,
                    source_end=29,
                    keyword_text="LEAGUES OF VOTANN model",
                    keyword_start=0,
                    keyword_end=23,
                    required_keywords=("LEAGUES_OF_VOTANN",),
                ),
                _dice_roll_modifier_clause(
                    source_row_id=_LEAGUES_OF_VOTANN_PERSECUTION_EYE_FOR_WEAKNESS,
                    clause_number=2,
                    source_text=(
                        "Each time a model in the bearer's unit makes an attack that "
                        "targets an assailed unit, add 1 to the Wound roll."
                    ),
                    source_start=30,
                    source_end=140,
                    trigger_text=(
                        "Each time a model in the bearer's unit makes an attack that "
                        "targets an assailed unit, add 1 to the Wound roll"
                    ),
                    trigger_start=30,
                    trigger_end=139,
                    target_kind="this_unit",
                    target_text="the bearer's unit",
                    target_start=51,
                    target_end=68,
                    effect_text="add 1 to the Wound roll",
                    effect_start=116,
                    effect_end=139,
                    roll_type="wound",
                    delta=1,
                ),
            ),
            ir_hash="182990bed7c68859a63fb558e49103465869d0455a1b172516ee046b55ae230b",
        ),
    ),
    (
        _NECRONS_OBEISANCE_PHALANX_WARRIOR_NOBLE,
        _rule_ir_payload(
            source_row_id=_NECRONS_OBEISANCE_PHALANX_WARRIOR_NOBLE,
            normalized_text=(
                "OVERLORD model only. Each time a melee attack targets the bearer's "
                "unit, subtract 1 from the Hit roll."
            ),
            clauses=(
                _keyword_gate_clause(
                    source_row_id=_NECRONS_OBEISANCE_PHALANX_WARRIOR_NOBLE,
                    clause_number=1,
                    source_text="OVERLORD model only.",
                    source_start=0,
                    source_end=20,
                    keyword_text="OVERLORD model",
                    keyword_start=0,
                    keyword_end=14,
                    required_keywords=("OVERLORD",),
                ),
                _dice_roll_modifier_clause(
                    source_row_id=_NECRONS_OBEISANCE_PHALANX_WARRIOR_NOBLE,
                    clause_number=2,
                    source_text=(
                        "Each time a melee attack targets the bearer's unit, subtract "
                        "1 from the Hit roll."
                    ),
                    source_start=21,
                    source_end=102,
                    trigger_text=(
                        "Each time a melee attack targets the bearer's unit, subtract "
                        "1 from the Hit roll"
                    ),
                    trigger_start=21,
                    trigger_end=101,
                    target_kind="this_unit",
                    target_text="the bearer's unit",
                    target_start=54,
                    target_end=71,
                    effect_text="subtract 1 from the Hit roll",
                    effect_start=73,
                    effect_end=101,
                    roll_type="hit",
                    delta=-1,
                ),
            ),
            ir_hash="c866e3a4228f6034e1795c3c04d6f70b78e30539c78b8fd1cdc78fc7ff687f78",
        ),
    ),
    (
        _ORKS_MORE_DAKKA_TARGETIN_SQUIGS,
        _rule_ir_payload(
            source_row_id=_ORKS_MORE_DAKKA_TARGETIN_SQUIGS,
            normalized_text=(
                "ORKS model only. Each time a model in the bearer's unit makes a "
                "ranged attack, add 1 to the Hit roll."
            ),
            clauses=(
                _keyword_gate_clause(
                    source_row_id=_ORKS_MORE_DAKKA_TARGETIN_SQUIGS,
                    clause_number=1,
                    source_text="ORKS model only.",
                    source_start=0,
                    source_end=16,
                    keyword_text="ORKS model",
                    keyword_start=0,
                    keyword_end=10,
                    required_keywords=("ORKS",),
                ),
                _dice_roll_modifier_clause(
                    source_row_id=_ORKS_MORE_DAKKA_TARGETIN_SQUIGS,
                    clause_number=2,
                    source_text=(
                        "Each time a model in the bearer's unit makes a ranged attack, "
                        "add 1 to the Hit roll."
                    ),
                    source_start=17,
                    source_end=101,
                    trigger_text=(
                        "Each time a model in the bearer's unit makes a ranged attack, "
                        "add 1 to the Hit roll"
                    ),
                    trigger_start=17,
                    trigger_end=100,
                    target_kind="this_unit",
                    target_text="the bearer's unit",
                    target_start=38,
                    target_end=55,
                    effect_text="add 1 to the Hit roll",
                    effect_start=79,
                    effect_end=100,
                    roll_type="hit",
                    delta=1,
                ),
            ),
            ir_hash="b2c2dcc5317f6bb19fcde9e7d13cd35dbd4abe738e5c9826d4443822f7ff415f",
        ),
    ),
    (
        _CHAOS_SPACE_MARINES_RENEGADE_WARBAND_EYES_OF_THE_HUNTER,
        _rule_ir_payload(
            source_row_id=_CHAOS_SPACE_MARINES_RENEGADE_WARBAND_EYES_OF_THE_HUNTER,
            normalized_text=(
                "HERETIC ASTARTES model only. Ranged weapons equipped by models in "
                "the bearer's unit have the [Ignores Cover] ability."
            ),
            clauses=(
                _keyword_gate_clause(
                    source_row_id=_CHAOS_SPACE_MARINES_RENEGADE_WARBAND_EYES_OF_THE_HUNTER,
                    clause_number=1,
                    source_text="HERETIC ASTARTES model only.",
                    source_start=0,
                    source_end=28,
                    keyword_text="HERETIC ASTARTES model",
                    keyword_start=0,
                    keyword_end=22,
                    required_keywords=("HERETIC_ASTARTES",),
                ),
                _weapon_ability_grant_clause(
                    source_row_id=_CHAOS_SPACE_MARINES_RENEGADE_WARBAND_EYES_OF_THE_HUNTER,
                    clause_number=2,
                    source_text=(
                        "Ranged weapons equipped by models in the bearer's unit have "
                        "the [Ignores Cover] ability."
                    ),
                    source_start=29,
                    source_end=117,
                    target_kind="this_unit",
                    target_text="models in the bearer's unit",
                    target_start=56,
                    target_end=83,
                    effect_text=(
                        "Ranged weapons equipped by models in the bearer's unit have "
                        "the [Ignores Cover] ability"
                    ),
                    effect_start=29,
                    effect_end=116,
                    weapon_ability="Ignores Cover",
                ),
            ),
            ir_hash="7b3d97a7f6cc445febfdbc52faad53cf9d3bcf937dc647c26a1a0d6a9366816d",
        ),
    ),
    (
        _GENESTEALER_CULTS_OUTLANDER_CLAW_SERPENTINE_TACTICS,
        _rule_ir_payload(
            source_row_id=_GENESTEALER_CULTS_OUTLANDER_CLAW_SERPENTINE_TACTICS,
            normalized_text=(
                "GENESTEALER CULTS MOUNTED model only. The bearer's unit is eligible "
                "to shoot in a turn in which it Fell Back."
            ),
            clauses=(
                _keyword_gate_clause(
                    source_row_id=_GENESTEALER_CULTS_OUTLANDER_CLAW_SERPENTINE_TACTICS,
                    clause_number=1,
                    source_text="GENESTEALER CULTS MOUNTED model only.",
                    source_start=0,
                    source_end=37,
                    keyword_text="GENESTEALER CULTS MOUNTED model",
                    keyword_start=0,
                    keyword_end=31,
                    required_keywords=("GENESTEALER_CULTS", "MOUNTED"),
                ),
                _grant_ability_clause(
                    source_row_id=_GENESTEALER_CULTS_OUTLANDER_CLAW_SERPENTINE_TACTICS,
                    clause_number=2,
                    source_text=(
                        "The bearer's unit is eligible to shoot in a turn in which it Fell Back."
                    ),
                    source_start=38,
                    source_end=109,
                    target_text="The bearer's unit",
                    target_start=38,
                    target_end=55,
                    effect_text="is eligible to shoot in a turn in which it Fell Back",
                    effect_start=56,
                    effect_end=108,
                    ability="can_fall_back_and_shoot",
                ),
            ),
            ir_hash="e3aa34cc33411062d9313d9487a83729ee278b1a8f5a003652c79e84909f92fe",
        ),
    ),
    (
        _IMPERIAL_KNIGHTS_FREEBLADE_COMPANY_MYSTERIOUS_GUARDIAN,
        _rule_ir_payload(
            source_row_id=_IMPERIAL_KNIGHTS_FREEBLADE_COMPANY_MYSTERIOUS_GUARDIAN,
            normalized_text=(
                "IMPERIAL KNIGHTS model only. Ranged weapons equipped by the bearer "
                "have the [Ignores Cover] ability."
            ),
            clauses=(
                _keyword_gate_clause(
                    source_row_id=_IMPERIAL_KNIGHTS_FREEBLADE_COMPANY_MYSTERIOUS_GUARDIAN,
                    clause_number=1,
                    source_text="IMPERIAL KNIGHTS model only.",
                    source_start=0,
                    source_end=28,
                    keyword_text="IMPERIAL KNIGHTS model",
                    keyword_start=0,
                    keyword_end=22,
                    required_keywords=("IMPERIAL_KNIGHTS",),
                ),
                _weapon_ability_grant_clause(
                    source_row_id=_IMPERIAL_KNIGHTS_FREEBLADE_COMPANY_MYSTERIOUS_GUARDIAN,
                    clause_number=2,
                    source_text=(
                        "Ranged weapons equipped by the bearer have the [Ignores Cover] ability."
                    ),
                    source_start=29,
                    source_end=100,
                    target_kind="this_model",
                    target_text="the bearer",
                    target_start=56,
                    target_end=66,
                    effect_text=(
                        "Ranged weapons equipped by the bearer have the [Ignores Cover] ability"
                    ),
                    effect_start=29,
                    effect_end=99,
                    weapon_ability="Ignores Cover",
                ),
            ),
            ir_hash="8d7b0854604a383c163656331f296a1acf9494242635a3b6b686c9f0d89fca55",
        ),
    ),
    (
        _NECRONS_CRYPTEK_CONCLAVE_GAUNTLET_OF_COMPRESSION,
        _rule_ir_payload(
            source_row_id=_NECRONS_CRYPTEK_CONCLAVE_GAUNTLET_OF_COMPRESSION,
            normalized_text=(
                'NECRONS model only. Add 6" to the Range characteristic of ranged '
                "weapons equipped by models in the bearer's unit."
            ),
            clauses=(
                _keyword_gate_clause(
                    source_row_id=_NECRONS_CRYPTEK_CONCLAVE_GAUNTLET_OF_COMPRESSION,
                    clause_number=1,
                    source_text="NECRONS model only.",
                    source_start=0,
                    source_end=19,
                    keyword_text="NECRONS model",
                    keyword_start=0,
                    keyword_end=13,
                    required_keywords=("NECRONS",),
                ),
                _characteristic_modifier_clause(
                    source_row_id=_NECRONS_CRYPTEK_CONCLAVE_GAUNTLET_OF_COMPRESSION,
                    clause_number=2,
                    source_text=(
                        'Add 6" to the Range characteristic of ranged weapons equipped '
                        "by models in the bearer's unit."
                    ),
                    source_start=20,
                    source_end=113,
                    target_text="models in the bearer's unit",
                    target_start=85,
                    target_end=112,
                    effect_text='Add 6" to the Range characteristic',
                    effect_start=20,
                    effect_end=54,
                    characteristic="range",
                    delta=6,
                ),
            ),
            ir_hash="45a4770c02967f327f0ff1954cc7e4738a3e6482dba09d353737d74fd71973a3",
        ),
    ),
    (
        _NECRONS_STARSHATTER_ARSENAL_MINIATURISED_NEBULOSCOPE,
        _rule_ir_payload(
            source_row_id=_NECRONS_STARSHATTER_ARSENAL_MINIATURISED_NEBULOSCOPE,
            normalized_text=(
                "NECRONS model only. Ranged weapons equipped by models in the bearer's "
                "unit have the [Ignores Cover] ability."
            ),
            clauses=(
                _keyword_gate_clause(
                    source_row_id=_NECRONS_STARSHATTER_ARSENAL_MINIATURISED_NEBULOSCOPE,
                    clause_number=1,
                    source_text="NECRONS model only.",
                    source_start=0,
                    source_end=19,
                    keyword_text="NECRONS model",
                    keyword_start=0,
                    keyword_end=13,
                    required_keywords=("NECRONS",),
                ),
                _weapon_ability_grant_clause(
                    source_row_id=_NECRONS_STARSHATTER_ARSENAL_MINIATURISED_NEBULOSCOPE,
                    clause_number=2,
                    source_text=(
                        "Ranged weapons equipped by models in the bearer's unit have "
                        "the [Ignores Cover] ability."
                    ),
                    source_start=20,
                    source_end=108,
                    target_kind="this_unit",
                    target_text="models in the bearer's unit",
                    target_start=47,
                    target_end=74,
                    effect_text=(
                        "Ranged weapons equipped by models in the bearer's unit have "
                        "the [Ignores Cover] ability"
                    ),
                    effect_start=20,
                    effect_end=107,
                    weapon_ability="Ignores Cover",
                ),
            ),
            ir_hash="e12690d6c901063a18892031a500d686d19442251e3fd784d3e8ba79444a7d9a",
        ),
    ),
    (
        _ORKS_FREEBOOTER_KREW_SNEAKY_SNEAKIN,
        _rule_ir_payload(
            source_row_id=_ORKS_FREEBOOTER_KREW_SNEAKY_SNEAKIN,
            normalized_text=(
                "ORKS model only. Ranged weapons equipped by models in the bearer's "
                "unit have the [Ignores Cover] ability."
            ),
            clauses=(
                _keyword_gate_clause(
                    source_row_id=_ORKS_FREEBOOTER_KREW_SNEAKY_SNEAKIN,
                    clause_number=1,
                    source_text="ORKS model only.",
                    source_start=0,
                    source_end=16,
                    keyword_text="ORKS model",
                    keyword_start=0,
                    keyword_end=10,
                    required_keywords=("ORKS",),
                ),
                _weapon_ability_grant_clause(
                    source_row_id=_ORKS_FREEBOOTER_KREW_SNEAKY_SNEAKIN,
                    clause_number=2,
                    source_text=(
                        "Ranged weapons equipped by models in the bearer's unit have "
                        "the [Ignores Cover] ability."
                    ),
                    source_start=17,
                    source_end=105,
                    target_kind="this_unit",
                    target_text="models in the bearer's unit",
                    target_start=44,
                    target_end=71,
                    effect_text=(
                        "Ranged weapons equipped by models in the bearer's unit have "
                        "the [Ignores Cover] ability"
                    ),
                    effect_start=17,
                    effect_end=104,
                    weapon_ability="Ignores Cover",
                ),
            ),
            ir_hash="13ee41ef514914bff34822c0d3027e2e2aa90807d3356ea932e165a9b775e05a",
        ),
    ),
    (
        _ORKS_MORE_DAKKA_KUNNIN_BUT_BRUTAL,
        _rule_ir_payload(
            source_row_id=_ORKS_MORE_DAKKA_KUNNIN_BUT_BRUTAL,
            normalized_text=(
                "ORKS model only. Ranged weapons equipped by models in the bearer's "
                "unit have the [Rapid Fire 1] ability."
            ),
            clauses=(
                _keyword_gate_clause(
                    source_row_id=_ORKS_MORE_DAKKA_KUNNIN_BUT_BRUTAL,
                    clause_number=1,
                    source_text="ORKS model only.",
                    source_start=0,
                    source_end=16,
                    keyword_text="ORKS model",
                    keyword_start=0,
                    keyword_end=10,
                    required_keywords=("ORKS",),
                ),
                _weapon_ability_grant_clause(
                    source_row_id=_ORKS_MORE_DAKKA_KUNNIN_BUT_BRUTAL,
                    clause_number=2,
                    source_text=(
                        "Ranged weapons equipped by models in the bearer's unit have "
                        "the [Rapid Fire 1] ability."
                    ),
                    source_start=17,
                    source_end=104,
                    target_kind="this_unit",
                    target_text="models in the bearer's unit",
                    target_start=44,
                    target_end=71,
                    effect_text=(
                        "Ranged weapons equipped by models in the bearer's unit have "
                        "the [Rapid Fire 1] ability"
                    ),
                    effect_start=17,
                    effect_end=103,
                    weapon_ability="Rapid Fire",
                    weapon_ability_value=1,
                ),
            ),
            ir_hash="d2c25b8f930b1eb6f3fa2374a2df3d6b31c4c65fcde8ef0d31118a8fe682e05a",
        ),
    ),
    (
        _ORKS_MORE_DAKKA_SUPA_CYBORK_BODY,
        _rule_ir_payload(
            source_row_id=_ORKS_MORE_DAKKA_SUPA_CYBORK_BODY,
            normalized_text=(
                "ORKS model only. The bearer's unit is eligible to shoot in a turn "
                "in which it Fell Back."
            ),
            clauses=(
                _keyword_gate_clause(
                    source_row_id=_ORKS_MORE_DAKKA_SUPA_CYBORK_BODY,
                    clause_number=1,
                    source_text="ORKS model only.",
                    source_start=0,
                    source_end=16,
                    keyword_text="ORKS model",
                    keyword_start=0,
                    keyword_end=10,
                    required_keywords=("ORKS",),
                ),
                _grant_ability_clause(
                    source_row_id=_ORKS_MORE_DAKKA_SUPA_CYBORK_BODY,
                    clause_number=2,
                    source_text=(
                        "The bearer's unit is eligible to shoot in a turn in which it Fell Back."
                    ),
                    source_start=17,
                    source_end=88,
                    target_text="The bearer's unit",
                    target_start=17,
                    target_end=34,
                    effect_text="is eligible to shoot in a turn in which it Fell Back",
                    effect_start=35,
                    effect_end=87,
                    ability="can_fall_back_and_shoot",
                ),
            ),
            ir_hash="e8ab8c02e81a2748968a2cd6b6928c666f3b3259c0774480ee8326593fd11847",
        ),
    ),
    (
        _SPACE_MARINES_CERAMITE_SENTINELS_AUSPEX_INTERFACE,
        _rule_ir_payload(
            source_row_id=_SPACE_MARINES_CERAMITE_SENTINELS_AUSPEX_INTERFACE,
            normalized_text=(
                "ADEPTUS ASTARTES model only. Ranged weapons equipped by models in "
                "the bearer's unit have the [Ignores Cover] ability."
            ),
            clauses=(
                _keyword_gate_clause(
                    source_row_id=_SPACE_MARINES_CERAMITE_SENTINELS_AUSPEX_INTERFACE,
                    clause_number=1,
                    source_text="ADEPTUS ASTARTES model only.",
                    source_start=0,
                    source_end=28,
                    keyword_text="ADEPTUS ASTARTES model",
                    keyword_start=0,
                    keyword_end=22,
                    required_keywords=("ADEPTUS_ASTARTES",),
                ),
                _weapon_ability_grant_clause(
                    source_row_id=_SPACE_MARINES_CERAMITE_SENTINELS_AUSPEX_INTERFACE,
                    clause_number=2,
                    source_text=(
                        "Ranged weapons equipped by models in the bearer's unit have "
                        "the [Ignores Cover] ability."
                    ),
                    source_start=29,
                    source_end=117,
                    target_kind="this_unit",
                    target_text="models in the bearer's unit",
                    target_start=56,
                    target_end=83,
                    effect_text=(
                        "Ranged weapons equipped by models in the bearer's unit have "
                        "the [Ignores Cover] ability"
                    ),
                    effect_start=29,
                    effect_end=116,
                    weapon_ability="Ignores Cover",
                ),
            ),
            ir_hash="1900cf8428b5178aa9722660919e40761c94648073d142d0897133688f384f83",
        ),
    ),
    (
        _TYRANIDS_WARRIOR_BIOFORM_ONSLAUGHT_ELEVATED_MIGHT,
        _rule_ir_payload(
            source_row_id=_TYRANIDS_WARRIOR_BIOFORM_ONSLAUGHT_ELEVATED_MIGHT,
            normalized_text=(
                "TYRANIDS model only. The bearer's unit is eligible to declare a "
                "charge in a turn in which it Advanced."
            ),
            clauses=(
                _keyword_gate_clause(
                    source_row_id=_TYRANIDS_WARRIOR_BIOFORM_ONSLAUGHT_ELEVATED_MIGHT,
                    clause_number=1,
                    source_text="TYRANIDS model only.",
                    source_start=0,
                    source_end=20,
                    keyword_text="TYRANIDS model",
                    keyword_start=0,
                    keyword_end=14,
                    required_keywords=("TYRANIDS",),
                ),
                _grant_ability_clause(
                    source_row_id=_TYRANIDS_WARRIOR_BIOFORM_ONSLAUGHT_ELEVATED_MIGHT,
                    clause_number=2,
                    source_text=(
                        "The bearer's unit is eligible to declare a charge in a turn "
                        "in which it Advanced."
                    ),
                    source_start=21,
                    source_end=102,
                    target_text="The bearer's unit",
                    target_start=21,
                    target_end=38,
                    effect_text=("is eligible to declare a charge in a turn in which it Advanced"),
                    effect_start=39,
                    effect_end=101,
                    ability="can_advance_and_charge",
                ),
            ),
            ir_hash="16c3cce7b8d7c7c5a4c74a111bf3cc9ae48668ba83f2fd18da507edec4e2ad30",
        ),
    ),
)
_STATIC_GENERIC_RULE_IR_PAYLOADS_BY_COVERAGE_DESCRIPTOR_ID = _static_generic_rule_ir_payloads()

_validate_identifier = IdentifierValidator(Phase17FGenericIrSupportError)
