from __future__ import annotations

from dataclasses import replace
from typing import cast

from warhammer40k_core.engine.faction_content.stratagem_activation import (
    source_backed_detachment_stratagem_activation_records,
    source_backed_stratagem_activation_source_package_id,
)
from warhammer40k_core.engine.faction_content.stratagem_record_merge import (
    merge_stratagem_records_with_contribution_overrides,
)
from warhammer40k_core.engine.rule_execution import GENERIC_RULE_IR_STRATAGEM_HANDLER_ID
from warhammer40k_core.engine.stratagems import StratagemCatalogIndex
from warhammer40k_core.rules.rule_ir import RuleIR, RuleIRPayload
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_stratagem_activation_2026_27,
    faction_subrules_2026_27,
)


def test_ws14_stratagem_activation_profiles_cover_source_only_detachment_rows() -> None:
    source_only_rows = tuple(
        row for row in faction_subrules_2026_27.stratagem_rows() if not row.runtime_consumer_ids
    )
    profiles = faction_stratagem_activation_2026_27.stratagem_activation_profiles()

    assert len(source_only_rows) == 1077
    assert len(profiles) == 1077
    assert {profile.source_row_id for profile in profiles} == {
        row.source_row_id for row in source_only_rows
    }

    for profile in profiles:
        rule_ir = RuleIR.from_payload(cast(RuleIRPayload, profile.rule_ir_payload()))
        assert rule_ir.is_supported
        assert rule_ir.ir_hash() == profile.rule_ir_hash


def test_ws14_source_backed_stratagem_activation_records_are_runtime_loadable() -> None:
    records = source_backed_detachment_stratagem_activation_records()
    profiles = faction_stratagem_activation_2026_27.stratagem_activation_profiles()

    assert source_backed_stratagem_activation_source_package_id() == (
        faction_stratagem_activation_2026_27.SOURCE_PACKAGE_ID
    )
    assert len(records) == sum(len(profile.phase_tokens) for profile in profiles)
    assert len(records) == 1261
    assert StratagemCatalogIndex.from_records(records).all_records() == tuple(
        sorted(records, key=lambda record: record.record_id)
    )
    assert {record.definition.handler_id for record in records} == {
        GENERIC_RULE_IR_STRATAGEM_HANDLER_ID
    }

    more_dakka = {
        record.definition.stratagem_id: record
        for record in records
        if record.detachment_id == "more-dakka"
    }
    get_stuck_in = more_dakka["000009992003"]
    assert get_stuck_in.definition.target_spec.target_policy_id == "friendly_unit"
    assert get_stuck_in.definition.target_spec.excluded_keywords == ("GRETCHIN",)
    huge_show_offs = more_dakka["000009992004"]
    assert huge_show_offs.definition.target_spec.required_keywords == ("WALKER",)
    assert huge_show_offs.definition.target_spec.excluded_keywords == ("KILLA KANS",)

    for record in more_dakka.values():
        payload = record.definition.effect_payload
        assert isinstance(payload, dict)
        rule_ir_payload = payload["rule_ir"]
        assert isinstance(rule_ir_payload, dict)
        RuleIR.from_payload(cast(RuleIRPayload, rule_ir_payload))


def test_ws14_source_backed_stratagem_activation_does_not_shadow_named_records() -> None:
    records = source_backed_detachment_stratagem_activation_records()
    source_backed = next(
        record
        for record in records
        if record.detachment_id == "more-dakka" and record.definition.stratagem_id == "000009992003"
    )
    retained = next(
        record
        for record in records
        if record.detachment_id == "more-dakka" and record.definition.stratagem_id == "000009992004"
    )
    named_record = replace(
        source_backed,
        record_id="ws14:named-handler:more-dakka:000009992003",
        definition=replace(
            source_backed.definition,
            handler_id="ws14:named-handler",
        ),
    )

    merged = merge_stratagem_records_with_contribution_overrides(records, (named_record,))

    assert named_record in merged
    assert retained in merged
    assert tuple(
        record
        for record in merged
        if record.detachment_id == "more-dakka" and record.definition.stratagem_id == "000009992003"
    ) == (named_record,)
