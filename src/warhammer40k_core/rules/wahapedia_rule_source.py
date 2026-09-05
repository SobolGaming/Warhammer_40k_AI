"""Retain normalized historical source rows without applying later-edition aliases."""

from __future__ import annotations

from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.wahapedia_schema import NormalizedSourceRow


def historical_rule_source_text_from_row_field(
    *,
    row: NormalizedSourceRow,
    column_name: str,
) -> RuleSourceText:
    for text_field in row.text_fields:
        if text_field.column_name == column_name:
            return RuleSourceText(
                objective_scope=ObjectiveRuleScope.HISTORICAL_TEXT,
                source_id=text_field.source_text_id,
                raw_text=text_field.sanitized_text,
                normalized_text=text_field.normalized_text,
                parsed_tokens=text_field.parsed_tokens,
            )
    return RuleSourceText.from_raw(
        objective_scope=ObjectiveRuleScope.HISTORICAL_TEXT,
        source_id=f"{row.stable_source_id()}:{column_name}",
        raw_text=row.runtime_fields_payload().get(column_name, ""),
    )
