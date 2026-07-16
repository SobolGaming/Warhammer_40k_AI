from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleCondition,
    RuleConditionKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleParameter,
    RuleTargetKind,
    RuleTargetSpec,
)
from warhammer40k_core.rules.wahapedia_schema import NormalizedSourceRow


class WahapediaInvulnerableSaveBridgeError(ValueError):
    """Raised when a conditional model invulnerable save cannot be normalized."""


@dataclass(frozen=True, slots=True)
class ConditionalInvulnerableSaveBridge:
    base_invulnerable_save: str
    ability_id: str
    ability_name: str
    normalized_text: str
    rule_ir: RuleIR
    source_ids: tuple[str, ...]


_RANGED_ONLY_DESCRIPTIONS = frozenset(
    {
        "* against ranged attacks only",
        "against ranged attacks only",
    }
)


def conditional_invulnerable_save_bridge_for_model_row(
    *,
    datasheet_id: str,
    model_source_row: NormalizedSourceRow,
) -> ConditionalInvulnerableSaveBridge | None:
    if type(datasheet_id) is not str or not datasheet_id.strip():
        raise WahapediaInvulnerableSaveBridgeError("datasheet_id must be non-empty text.")
    if type(model_source_row) is not NormalizedSourceRow:
        raise WahapediaInvulnerableSaveBridgeError(
            "model_source_row must be a NormalizedSourceRow."
        )
    fields = model_source_row.runtime_fields_payload()
    description = fields.get("inv_sv_descr", "").strip()
    if description.casefold() not in _RANGED_ONLY_DESCRIPTIONS:
        return None
    value_token = fields.get("inv_sv", "").strip().removesuffix("*")
    if not value_token.isdigit():
        raise WahapediaInvulnerableSaveBridgeError(
            "Conditional ranged invulnerable save must have an integer characteristic."
        )
    target_number = int(value_token)
    if not 2 <= target_number <= 6:
        raise WahapediaInvulnerableSaveBridgeError(
            "Conditional ranged invulnerable save must be between 2+ and 6+."
        )
    source_id = model_source_row.stable_source_id()
    ability_id = f"{datasheet_id}:ranged-invulnerable-save"
    normalized_text = (
        f"This model has a {target_number}+ invulnerable save against ranged attacks only."
    )
    full_span = TextSpan(text=normalized_text, start=0, end=len(normalized_text))
    target_text = "This model"
    target_span = TextSpan(text=target_text, start=0, end=len(target_text))
    condition_text = "against ranged attacks only"
    condition_start = normalized_text.index(condition_text)
    condition_span = TextSpan(
        text=condition_text,
        start=condition_start,
        end=condition_start + len(condition_text),
    )
    value_text = f"{target_number}+ invulnerable save"
    value_start = normalized_text.index(value_text)
    value_span = TextSpan(
        text=value_text,
        start=value_start,
        end=value_start + len(value_text),
    )
    rule_ir = RuleIR(
        rule_id=f"phase17k:model-characteristic:{ability_id}",
        source_id=f"{source_id}:conditional-ranged-invulnerable-save",
        normalized_text=normalized_text,
        parser_version="wahapedia-model-characteristic-bridge:v1",
        clauses=(
            RuleClause(
                clause_id=f"phase17k:model-characteristic:{ability_id}:clause:001",
                template_id="phase17c:conditional-ranged-invulnerable-save",
                source_span=full_span,
                conditions=(
                    RuleCondition(
                        kind=RuleConditionKind.TARGET_CONSTRAINT,
                        source_span=condition_span,
                        parameters=(
                            RuleParameter(key="attack_kind", value="ranged"),
                            RuleParameter(key="gate_subject", value="incoming_attack"),
                        ),
                    ),
                ),
                target=RuleTargetSpec(
                    kind=RuleTargetKind.THIS_MODEL,
                    source_span=target_span,
                ),
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.SET_CHARACTERISTIC,
                        source_span=value_span,
                        parameters=(
                            RuleParameter(key="characteristic", value="invulnerable_save"),
                            RuleParameter(key="value", value=target_number),
                        ),
                    ),
                ),
            ),
        ),
    )
    return ConditionalInvulnerableSaveBridge(
        base_invulnerable_save="-",
        ability_id=ability_id,
        ability_name="Ranged Invulnerable Save",
        normalized_text=normalized_text,
        rule_ir=rule_ir,
        source_ids=(source_id,),
    )
