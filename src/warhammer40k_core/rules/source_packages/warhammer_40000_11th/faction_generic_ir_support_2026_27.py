from __future__ import annotations

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.rules.rule_ir import RuleEffectKind, RuleIR
from warhammer40k_core.rules.rule_templates import (
    CHARACTERISTIC_MODIFIER_TEMPLATE_ID,
    DICE_ROLL_MODIFIER_TEMPLATE_ID,
    GRANT_ABILITY_TEMPLATE_ID,
    KEYWORD_GATE_TEMPLATE_ID,
    MOVEMENT_DISTANCE_TEMPLATE_ID,
    WEAPON_ABILITY_GRANT_TEMPLATE_ID,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_court_of_the_phoenician_ir_support_2026_27 as court_ir,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27,
    faction_subrules_2026_27,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_generic_ir_static_payloads_2026_27 as static_payloads,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_more_dakka_ir_support_2026_27 as more_dakka_ir,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_spectacle_of_slaughter_ir_support_2026_27 as spectacle_ir,
)

SOURCE_PACKAGE_ID = static_payloads.SOURCE_PACKAGE_ID
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
        "enhancement:emperors-children:court-of-the-phoenician:000010654002",
        "enhancement:emperors-children:court-of-the-phoenician:000010654004",
        "enhancement:emperors-children:spectacle-of-slaughter:000010900002",
        "enhancement:genestealer-cults:outlander-claw:000009079002",
        "enhancement:orks:more-dakka:000009991005",
        "enhancement:tyranids:warrior-bioform-onslaught:000009737005",
    }
)
_SUPPORTED_MOVEMENT_DISTANCE_ENHANCEMENT_SOURCE_ROW_IDS = frozenset(
    {
        "enhancement:emperors-children:spectacle-of-slaughter:000010900003",
    }
)
_SUPPORTED_CHARACTERISTIC_MODIFICATION_ENHANCEMENT_SOURCE_ROW_IDS = frozenset(
    {
        "enhancement:emperors-children:court-of-the-phoenician:000010654005",
        "enhancement:necrons:cryptek-conclave:000010664004",
    }
)
_SUPPORTED_COURT_OF_THE_PHOENICIAN_MIXED_ENHANCEMENT_SOURCE_ROW_IDS = frozenset(
    {
        "enhancement:emperors-children:court-of-the-phoenician:000010654003",
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
_SUPPORTED_MOVEMENT_DISTANCE_TEMPLATE_IDS = frozenset(
    {
        KEYWORD_GATE_TEMPLATE_ID,
        MOVEMENT_DISTANCE_TEMPLATE_ID,
    }
)


class Phase17FGenericIrSupportError(ValueError):
    """Raised when Phase 17F generic IR support metadata is inconsistent."""


_STATIC_GENERIC_RULE_IR_PAYLOADS_BY_COVERAGE_DESCRIPTOR_ID = (
    static_payloads.static_generic_rule_ir_payloads()
)


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
    rule_ir_hash = more_dakka_ir.coverage_rule_ir_hash_by_descriptor_id(descriptor_id)
    if rule_ir_hash is not None:
        return rule_ir_hash
    rule_ir_hash = spectacle_ir.coverage_rule_ir_hash_by_descriptor_id(descriptor_id)
    if rule_ir_hash is not None:
        return rule_ir_hash
    return court_ir.coverage_rule_ir_hash_by_descriptor_id(descriptor_id)


def generic_supported_stratagem_rule_ir_hash(
    source_row: faction_subrules_2026_27.SourceStratagemRow,
) -> str | None:
    if type(source_row) is not faction_subrules_2026_27.SourceStratagemRow:
        raise Phase17FGenericIrSupportError("Generic Stratagem support requires source row.")
    descriptor_id = f"phase17e:{source_row.source_row_id}"
    rule_ir_hash = more_dakka_ir.coverage_rule_ir_hash_by_descriptor_id(descriptor_id)
    if rule_ir_hash is not None:
        return rule_ir_hash
    rule_ir_hash = spectacle_ir.coverage_rule_ir_hash_by_descriptor_id(descriptor_id)
    if rule_ir_hash is not None:
        return rule_ir_hash
    return court_ir.coverage_rule_ir_hash_by_descriptor_id(descriptor_id)


def generic_rule_ir_by_coverage_descriptor_id(coverage_descriptor_id: str) -> RuleIR:
    descriptor_id = _validate_identifier("coverage_descriptor_id", coverage_descriptor_id)
    payload = _STATIC_GENERIC_RULE_IR_PAYLOADS_BY_COVERAGE_DESCRIPTOR_ID.get(descriptor_id)
    if payload is None:
        payload = more_dakka_ir.coverage_rule_ir_payload_by_descriptor_id(descriptor_id)
    if payload is None:
        payload = spectacle_ir.coverage_rule_ir_payload_by_descriptor_id(descriptor_id)
    if payload is None:
        payload = court_ir.coverage_rule_ir_payload_by_descriptor_id(descriptor_id)
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


def supported_movement_distance_enhancement_source_row_ids() -> tuple[str, ...]:
    return tuple(sorted(_SUPPORTED_MOVEMENT_DISTANCE_ENHANCEMENT_SOURCE_ROW_IDS))


def supported_court_of_the_phoenician_mixed_enhancement_source_row_ids() -> tuple[str, ...]:
    return tuple(sorted(_SUPPORTED_COURT_OF_THE_PHOENICIAN_MIXED_ENHANCEMENT_SOURCE_ROW_IDS))


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
        expected_effect_count = (
            2
            if source_row.source_row_id
            == "enhancement:emperors-children:court-of-the-phoenician:000010654005"
            else 1
        )
        _validate_supported_effect_family_ir(
            rule_ir=rule_ir,
            source_row=source_row,
            expected_template_ids=_SUPPORTED_CHARACTERISTIC_MODIFICATION_TEMPLATE_IDS,
            effect_kind=RuleEffectKind.MODIFY_CHARACTERISTIC,
            effect_family_name="characteristic modifier",
            expected_effect_count=expected_effect_count,
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
    elif source_row.source_row_id in _SUPPORTED_MOVEMENT_DISTANCE_ENHANCEMENT_SOURCE_ROW_IDS:
        _validate_supported_effect_family_ir(
            rule_ir=rule_ir,
            source_row=source_row,
            expected_template_ids=_SUPPORTED_MOVEMENT_DISTANCE_TEMPLATE_IDS,
            effect_kind=RuleEffectKind.MODIFY_MOVE_DISTANCE,
            effect_family_name="movement distance modifier",
            expected_effect_count=1,
        )
    elif (
        source_row.source_row_id
        in _SUPPORTED_COURT_OF_THE_PHOENICIAN_MIXED_ENHANCEMENT_SOURCE_ROW_IDS
    ):
        _validate_supported_court_of_the_phoenician_mixed_enhancement_ir(
            rule_ir=rule_ir,
            source_row=source_row,
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


def _validate_supported_court_of_the_phoenician_mixed_enhancement_ir(
    *,
    rule_ir: RuleIR,
    source_row: faction_subrules_2026_27.SourceEnhancementRow,
) -> None:
    if not rule_ir.is_supported:
        raise Phase17FGenericIrSupportError(
            "Court of the Phoenician mixed enhancement RuleIR must deserialize as supported."
        )
    expected_source_id = f"{SOURCE_PACKAGE_ID}:phase17e:{source_row.source_row_id}:source-text"
    if rule_ir.source_id != expected_source_id:
        raise Phase17FGenericIrSupportError(
            "Court of the Phoenician mixed enhancement produced an unexpected source ID."
        )
    template_ids = frozenset(
        clause.template_id for clause in rule_ir.clauses if clause.template_id is not None
    )
    if template_ids != frozenset(
        {
            GRANT_ABILITY_TEMPLATE_ID,
            KEYWORD_GATE_TEMPLATE_ID,
            MOVEMENT_DISTANCE_TEMPLATE_ID,
        }
    ):
        raise Phase17FGenericIrSupportError(
            "Court of the Phoenician mixed enhancement uses an unregistered template family."
        )
    expected_effect_counts = {
        RuleEffectKind.GRANT_ABILITY: 1,
        RuleEffectKind.MODIFY_MOVE_DISTANCE: 1,
    }
    actual_effect_counts = dict.fromkeys(expected_effect_counts, 0)
    for clause in rule_ir.clauses:
        if clause.unsupported_reason is not None or clause.diagnostics:
            raise Phase17FGenericIrSupportError(
                "Court of the Phoenician mixed enhancement includes unsupported diagnostics."
            )
        for effect in clause.effects:
            if effect.kind not in actual_effect_counts:
                raise Phase17FGenericIrSupportError(
                    "Court of the Phoenician mixed enhancement includes an unexpected effect kind."
                )
            actual_effect_counts[effect.kind] += 1
    if actual_effect_counts != expected_effect_counts:
        raise Phase17FGenericIrSupportError(
            "Court of the Phoenician mixed enhancement has unexpected effect counts."
        )


def _supported_enhancement_source_row_ids() -> frozenset[str]:
    return (
        _SUPPORTED_CONDITIONAL_WEAPON_ABILITY_ENHANCEMENT_SOURCE_ROW_IDS
        | _SUPPORTED_GRANT_ABILITY_ENHANCEMENT_SOURCE_ROW_IDS
        | _SUPPORTED_CHARACTERISTIC_MODIFICATION_ENHANCEMENT_SOURCE_ROW_IDS
        | _SUPPORTED_DICE_ROLL_MODIFICATION_ENHANCEMENT_SOURCE_ROW_IDS
        | _SUPPORTED_MOVEMENT_DISTANCE_ENHANCEMENT_SOURCE_ROW_IDS
        | _SUPPORTED_COURT_OF_THE_PHOENICIAN_MIXED_ENHANCEMENT_SOURCE_ROW_IDS
    )


_validate_identifier = IdentifierValidator(Phase17FGenericIrSupportError)
