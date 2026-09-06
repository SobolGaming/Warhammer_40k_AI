"""Authenticate Psychic usage against canonical lineage and recorded decisions."""

from __future__ import annotations

from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_record_source_matches_unit,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.psychic_ability_usage import PsychicAbilityUse, psychic_uses
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_rule_ir_authority import RuntimeRuleIRAuthorityIndex
from warhammer40k_core.rules.psychic_ability_identity import psychic_ability_level


def validate_psychic_usage_history(
    *,
    state: GameState,
    decisions: DecisionController,
    authority: RuntimeRuleIRAuthorityIndex | None,
) -> None:
    uses = psychic_uses(decisions.event_log)
    if uses and authority is None:
        raise GameLifecycleError("Psychic use restore requires authoritative catalog sources.")
    if authority is None:
        return
    psychic_sources = {
        (ir.source_id, ir.ir_hash())
        for ir in authority.all_rule_irs()
        if psychic_ability_level(ir) is not None
    }
    if not uses and not psychic_sources:
        return
    by_result: dict[str, PsychicAbilityUse] = {}
    for use in uses:
        if use.game_id != state.game_id or use.player_id not in state.player_ids:
            raise GameLifecycleError("Psychic use game or player identity drifted.")
        if use.active_player_id not in state.turn_order or use.battle_round > state.battle_round:
            raise GameLifecycleError("Psychic use phase identity is invalid.")
        ir = authority.rule_ir_for_player(
            source_id=use.ability_source_id,
            rule_ir_hash=use.source_rule_ir_hash,
            player_id=use.player_id,
        )
        if psychic_ability_level(ir) != use.psychic_level or ir.rule_id != use.source_rule_id:
            raise GameLifecycleError("Psychic use source descriptor drifted.")
        components = _historical_components(state, use)
        if tuple(sorted(components)) != use.component_unit_instance_ids:
            raise GameLifecycleError("Psychic use canonical component lineage drifted.")
        if use.source_instance_id not in (use.rules_unit_instance_id, *components):
            raise GameLifecycleError("Psychic use source instance is outside its lineage.")
        units = tuple(
            unit
            for army in state.army_definitions
            if army.player_id == use.player_id
            for unit in army.units
            if unit.unit_instance_id in components
        )
        if len(units) != len(components):
            raise GameLifecycleError("Psychic use component owner drifted.")
        if not any("PSYKER" in unit.keywords for unit in units):
            raise GameLifecycleError("Psychic use lineage has no PSYKER source.")
        source_units = tuple(
            unit for unit in units if unit.unit_instance_id == use.source_component_unit_instance_id
        )
        if use.source_model_instance_id is not None:
            if (
                len(source_units) != 1
                or use.source_model_instance_id not in source_units[0].own_model_ids()
            ):
                raise GameLifecycleError("Psychic use model/component ownership drifted.")
            if use.source_instance_id not in (
                use.rules_unit_instance_id,
                source_units[0].unit_instance_id,
            ):
                raise GameLifecycleError("Psychic use selected component does not own its model.")
        elif use.source_component_unit_instance_id is not None and len(source_units) != 1:
            raise GameLifecycleError("Psychic use selected component is unknown.")
        records = tuple(
            record
            for record in authority.ability_records_for_player(
                source_id=use.ability_source_id,
                rule_ir_hash=use.source_rule_ir_hash,
                player_id=use.player_id,
            )
            if record.record_id == use.catalog_record_id
        )
        if len(records) != 1 or not any(
            catalog_rule_record_source_matches_unit(
                record=records[0],
                unit=unit,
                current_model_instance_ids=(
                    unit.own_model_ids()
                    if use.source_model_instance_id is None
                    else (use.source_model_instance_id,)
                ),
            )
            for unit in (source_units if source_units else units)
        ):
            raise GameLifecycleError("Psychic use source instance is not a catalog provider.")
        matches = tuple(
            record
            for record in decisions.records
            if record.request.request_id == use.request_id
            and record.result.result_id == use.result_id
        )
        if len(matches) != 1:
            raise GameLifecycleError("Psychic use has no unique accepted decision.")
        record = matches[0]
        payload = record.result.payload
        if not isinstance(payload, dict) or payload.get("activate") is not True:
            raise GameLifecycleError("Psychic use decision did not activate the ability.")
        expected = {
            "game_id": use.game_id,
            "player_id": use.player_id,
            "battle_round": use.battle_round,
            "active_player_id": use.active_player_id,
            "phase": use.phase.value,
            "catalog_record_id": use.catalog_record_id,
            "rule_ir_hash": use.source_rule_ir_hash,
            "source_model_instance_id": use.source_model_instance_id,
        }
        if record.request.actor_id != use.player_id or any(
            payload.get(k) != v for k, v in expected.items()
        ):
            raise GameLifecycleError("Psychic use decision source or phase evidence drifted.")
        if payload.get("source_unit_instance_id") not in (
            use.source_instance_id,
            use.source_component_unit_instance_id,
        ):
            raise GameLifecycleError("Psychic use decision component evidence drifted.")
        recorded_index = next(
            (
                i
                for i, event in enumerate(decisions.event_log.records)
                if event.event_type == "decision_recorded" and event.payload == record.to_payload()
            ),
            None,
        )
        use_index = next(
            i
            for i, event in enumerate(decisions.event_log.records)
            if event.event_type == "psychic_ability_used" and event.payload == use.to_payload()
        )
        if recorded_index is None or recorded_index >= use_index:
            raise GameLifecycleError("Psychic use precedes its accepted decision.")
        if use.result_id is None or use.result_id in by_result:
            raise GameLifecycleError("Psychic use result identity is duplicated.")
        by_result[use.result_id] = use
    # Removing the usage event must not unlock a previously accepted use.
    for record in decisions.records:
        payload = record.result.payload
        if not isinstance(payload, dict) or payload.get("activate") is not True:
            continue
        source_id, ir_hash = payload.get("source_rule_id"), payload.get("rule_ir_hash")
        if type(source_id) is not str or type(ir_hash) is not str:
            continue
        if (source_id, ir_hash) in psychic_sources and record.result.result_id not in by_result:
            raise GameLifecycleError("Accepted Psychic activation is missing its phase-use record.")


def _historical_components(state: GameState, use: PsychicAbilityUse) -> tuple[str, ...]:
    for record in state.starting_attached_unit_records:
        if record.attached_unit_instance_id == use.rules_unit_instance_id:
            return record.component_unit_instance_ids
        if use.rules_unit_instance_id in record.component_unit_instance_ids:
            raise GameLifecycleError(
                "Psychic use substitutes a component for its canonical rules unit."
            )
    unit = rules_unit_view_by_id(state=state, unit_instance_id=use.rules_unit_instance_id)
    if unit.unit_instance_id != use.rules_unit_instance_id:
        raise GameLifecycleError("Psychic use rules-unit identity is not canonical.")
    return unit.component_unit_instance_ids
