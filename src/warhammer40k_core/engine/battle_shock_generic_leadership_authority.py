"""Reconstruct generic Leadership at the test boundary from loaded source events."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.modifiers import Modifier
from warhammer40k_core.engine.battle_shock_historical_authority import (
    HistoricalBattleShockAuthorityContext,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.generic_rule_attack_hooks import (
    generic_characteristic_operations_from_effects,
    generic_matching_unit_effect_applications,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_unit_effects import (
    rules_unit_effect_applications_from_inventory,
)
from warhammer40k_core.rules.rule_ir import RuleEffectKind

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle


from warhammer40k_core.engine.generic_effect_history import (
    HistoricalEffectAuthority,
    historical_generic_effect_inventory,
)


def historical_generic_leadership_operations(
    *,
    historical: HistoricalBattleShockAuthorityContext,
    runtime_content_bundle: RuntimeContentBundle,
) -> tuple[Modifier, ...]:
    authority = HistoricalEffectAuthority(
        game_id=historical.game_id,
        player_ids=historical.player_ids,
        turn_order=historical.turn_order,
        battle_phase_sequence=historical.battle_phase_sequence,
        armies=historical.armies,
        event_records=historical.event_records,
        decision_records=historical.decision_records,
        boundary_event_index=historical.boundary_event_index,
        player_id=historical.request.player_id,
        battle_round=historical.request.battle_round,
        active_player_id=historical.active_player_id,
        phase=historical.phase,
        rules_unit_at_event=lambda uid, _index: historical.rules_unit_containing_unit(uid),
    )
    effects = historical_generic_effect_inventory(
        historical=authority,
        runtime_content_bundle=runtime_content_bundle,
        matches_payload=_is_leadership_payload,
    )
    applications = rules_unit_effect_applications_from_inventory(
        armies=historical.armies,
        effects=effects,
        rules_unit=historical.rules_unit(historical.request.unit_instance_id),
    )
    return generic_characteristic_operations_from_effects(
        effects=generic_matching_unit_effect_applications(
            applications=applications, effect_kind=RuleEffectKind.MODIFY_CHARACTERISTIC
        ),
        characteristic=Characteristic.LEADERSHIP,
    )


def _is_leadership_payload(payload: dict[str, JsonValue]) -> bool:
    effect = payload.get("effect")
    if (
        not isinstance(effect, dict)
        or effect.get("kind") != RuleEffectKind.MODIFY_CHARACTERISTIC.value
    ):
        return False
    parameters = effect.get("parameters")
    if not isinstance(parameters, list):
        raise GameLifecycleError("Historical generic characteristic parameters are invalid.")
    return any(
        isinstance(parameter, dict)
        and parameter.get("key") == "characteristic"
        and parameter.get("value") == Characteristic.LEADERSHIP.value
        for parameter in parameters
    )
