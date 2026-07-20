from __future__ import annotations

import json

from warhammer40k_core.rules.rule_ir import RuleIRPayload
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    aeldari_aspect_warriors_2026_06 as aeldari_aspect_warriors_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    aeldari_autarchs_2026_06 as aeldari_autarchs_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    aeldari_corsair_skyreavers_2026_06 as aeldari_corsair_skyreavers_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    aeldari_corsair_void_units_2026_06 as aeldari_corsair_void_units_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    aeldari_kharseth_2026_06 as aeldari_kharseth_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    aeldari_night_spinner_2026_06 as aeldari_night_spinner_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    aeldari_shroud_runners_wraithblades_2026_06 as aeldari_shroud_wraith_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    aeldari_war_walkers_wraithlord_2026_06 as aeldari_war_walkers_wraithlord_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    aeldari_yriel_vypers_starfangs_2026_06 as aeldari_yriel_vypers_starfangs_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_daemons_datasheet_ir_support_2026_27 as chaos_daemons_datasheet_ir_source,
)


def compact_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def datasheet_rule_ir_payload_by_source_row_id(source_row_id: str) -> RuleIRPayload | None:
    payloads = tuple(
        payload
        for payload in (
            aeldari_aspect_warriors_source.datasheet_rule_ir_payload_by_source_row_id(
                source_row_id
            ),
            aeldari_autarchs_source.datasheet_rule_ir_payload_by_source_row_id(source_row_id),
            aeldari_corsair_skyreavers_source.datasheet_rule_ir_payload_by_source_row_id(
                source_row_id
            ),
            aeldari_corsair_void_units_source.datasheet_rule_ir_payload_by_source_row_id(
                source_row_id
            ),
            aeldari_kharseth_source.datasheet_rule_ir_payload_by_source_row_id(source_row_id),
            aeldari_night_spinner_source.datasheet_rule_ir_payload_by_source_row_id(source_row_id),
            aeldari_shroud_wraith_source.datasheet_rule_ir_payload_by_source_row_id(source_row_id),
            aeldari_war_walkers_wraithlord_source.datasheet_rule_ir_payload_by_source_row_id(
                source_row_id
            ),
            aeldari_yriel_vypers_starfangs_source.datasheet_rule_ir_payload_by_source_row_id(
                source_row_id
            ),
            chaos_daemons_datasheet_ir_source.datasheet_rule_ir_payload_by_source_row_id(
                source_row_id
            ),
        )
        if payload is not None
    )
    if len(payloads) > 1:
        raise ValueError("Datasheet static RuleIR source-row registrations must be unique.")
    return None if not payloads else payloads[0]


def payload_by_source_row_id(source_row_id: str) -> RuleIRPayload | None:
    return datasheet_rule_ir_payload_by_source_row_id(source_row_id)
