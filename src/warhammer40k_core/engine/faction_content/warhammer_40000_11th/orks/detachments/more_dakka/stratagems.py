from __future__ import annotations

from dataclasses import replace

from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.faction_content.stratagem_activation import (
    source_backed_detachment_stratagem_activation_records,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.stratagems import (
    DESTROYED_TARGET_BY_JUST_SHOT_UNIT_TARGET_POLICY_ID,
    StratagemCatalogRecord,
    StratagemTargetSpec,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_more_dakka_ir_support_2026_27,
)

CONTRIBUTION_ID = "warhammer_40000_11th:orks:detachment:more_dakka:stratagems:scaffold"
MORE_DAKKA_DETACHMENT_ID = "more-dakka"
MORE_DAKKA_PROFILE_PREFIX = "phase17s:stratagem:orks:more-dakka"
CALL_DAT_DAKKA_STRATAGEM_ID = "000009992007"
ORKS_FACTION_KEYWORD = "ORKS"


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        stratagem_records=_more_dakka_stratagem_records(),
    )


def _more_dakka_stratagem_records() -> tuple[StratagemCatalogRecord, ...]:
    records: list[StratagemCatalogRecord] = []
    for record in source_backed_detachment_stratagem_activation_records():
        if record.detachment_id != MORE_DAKKA_DETACHMENT_ID:
            continue
        records.append(_record_with_static_rule_ir(record))
    return tuple(sorted(records, key=lambda record: record.record_id))


def _record_with_static_rule_ir(record: StratagemCatalogRecord) -> StratagemCatalogRecord:
    if type(record) is not StratagemCatalogRecord:
        raise GameLifecycleError("More Dakka Stratagem override requires catalog record.")
    profile_id = f"{MORE_DAKKA_PROFILE_PREFIX}:{record.definition.stratagem_id}"
    rule_ir_payload = (
        faction_more_dakka_ir_support_2026_27.stratagem_activation_rule_ir_payload_by_profile_id(
            profile_id
        )
    )
    if rule_ir_payload is None:
        raise GameLifecycleError("More Dakka Stratagem RuleIR payload is missing.")
    return replace(
        record,
        definition=replace(
            record.definition,
            effect_payload=validate_json_value({"rule_ir": rule_ir_payload}),
            target_spec=_more_dakka_target_spec(record),
        ),
    )


def _more_dakka_target_spec(record: StratagemCatalogRecord) -> StratagemTargetSpec:
    if record.definition.stratagem_id != CALL_DAT_DAKKA_STRATAGEM_ID:
        return record.definition.target_spec
    return replace(
        record.definition.target_spec,
        target_policy_id=DESTROYED_TARGET_BY_JUST_SHOT_UNIT_TARGET_POLICY_ID,
        required_faction_keywords=(ORKS_FACTION_KEYWORD,),
    )
