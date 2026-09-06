"""Canonical, event-backed once-per-phase Psychic ability use authority."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Annotated

import msgspec

from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.engine.event_log import EventLog, EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.rules.psychic_ability_identity import psychic_ability_level
from warhammer40k_core.rules.rule_ir import RuleIR
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_aura_psychic_2026_09 import (
    PSYCHIC_SOURCE_ID,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.rule_execution import RuleExecutionContext

PSYCHIC_ABILITY_USED_EVENT = "psychic_ability_used"
_Id = Annotated[str, msgspec.Meta(min_length=1)]
_Positive = Annotated[int, msgspec.Meta(ge=1)]


class PsychicAbilityUse(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    usage_key: _Id
    restriction_source_id: _Id
    game_id: _Id
    player_id: _Id
    rules_unit_instance_id: _Id
    ability_source_id: _Id
    battle_round: _Positive
    active_player_id: _Id
    phase: BattlePhaseKind
    psychic_level: _Positive
    source_rule_id: _Id
    source_rule_ir_hash: _Id
    source_instance_id: _Id
    source_component_unit_instance_id: str | None
    source_model_instance_id: str | None
    component_unit_instance_ids: tuple[_Id, ...]
    catalog_record_id: str | None
    request_id: str | None
    result_id: str | None

    def canonical_key(self) -> str:
        values = (
            self.game_id,
            self.rules_unit_instance_id,
            self.ability_source_id,
            self.battle_round,
            self.active_player_id,
            self.phase.value,
        )
        return (
            "psychic-use:"
            + hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()
        )

    def to_payload(self) -> JsonValue:
        return validate_json_value(msgspec.to_builtins(self))


def psychic_uses(event_log: EventLog) -> tuple[PsychicAbilityUse, ...]:
    uses: list[PsychicAbilityUse] = []
    seen: set[str] = set()
    for event in event_log.records:
        if event.event_type != PSYCHIC_ABILITY_USED_EVENT:
            continue
        try:
            use = msgspec.convert(event.payload, type=PsychicAbilityUse, strict=True)
        except msgspec.ValidationError as exc:
            raise GameLifecycleError("Psychic ability use event is malformed.") from exc
        if use.restriction_source_id != PSYCHIC_SOURCE_ID:
            raise GameLifecycleError("Psychic use restriction source drifted.")
        if use.usage_key != use.canonical_key() or use.usage_key in seen:
            raise GameLifecycleError("Psychic ability use key drifted or was consumed twice.")
        if (
            not use.component_unit_instance_ids
            or tuple(sorted(set(use.component_unit_instance_ids)))
            != use.component_unit_instance_ids
        ):
            raise GameLifecycleError("Psychic ability component lineage is malformed.")
        seen.add(use.usage_key)
        uses.append(use)
    return tuple(uses)


def psychic_ability_unavailable_reason(
    *,
    rule_ir: RuleIR,
    context: RuleExecutionContext,
) -> str | None:
    if psychic_ability_level(rule_ir) is None:
        return None
    state = context.state
    if state is None:
        return "missing_input:game_state"
    if context.event_log is None:
        return "missing_input:event_log"
    if (
        context.game_id != state.game_id
        or context.battle_round != state.battle_round
        or context.phase != state.current_battle_phase
        or context.active_player_id != state.active_player_id
        or state.current_battle_phase is None
        or state.active_player_id is None
    ):
        return "psychic_ability_phase_context_drift"
    if context.source_unit_instance_id is None:
        return "missing_input:source_unit"
    unit = rules_unit_view_by_id(state=state, unit_instance_id=context.source_unit_instance_id)
    if unit.owner_player_id != context.player_id:
        return "psychic_ability_owner_drift"
    if "PSYKER" not in unit.keywords:
        return "psychic_ability_requires_psyker"
    if not unit.alive_models():
        return "psychic_ability_source_unavailable"
    if context.source_model_instance_id is not None:
        if context.source_model_instance_id not in {
            model.model_instance_id for model in unit.alive_models()
        }:
            return "psychic_ability_source_model_drift"
        component_id = unit.component_unit_id_for_model(context.source_model_instance_id)
        if context.source_unit_instance_id not in (unit.unit_instance_id, component_id):
            return "psychic_ability_source_component_drift"
    use = psychic_use_for_context(rule_ir=rule_ir, context=context)
    if use is None:
        raise GameLifecycleError("Psychic descriptor disappeared during validation.")
    if any(previous.usage_key == use.usage_key for previous in psychic_uses(context.event_log)):
        return "psychic_ability_used_this_phase"
    return None


def psychic_use_for_context(
    *, rule_ir: RuleIR, context: RuleExecutionContext
) -> PsychicAbilityUse | None:
    level = psychic_ability_level(rule_ir)
    if level is None:
        return None
    if (
        context.state is None
        or context.source_unit_instance_id is None
        or context.phase is None
        or context.active_player_id is None
    ):
        raise GameLifecycleError("Psychic use requires a complete source and phase context.")
    unit = rules_unit_view_by_id(
        state=context.state, unit_instance_id=context.source_unit_instance_id
    )
    model_id = context.source_model_instance_id
    trigger = context.trigger_payload
    if trigger is not None and not isinstance(trigger, dict):
        raise GameLifecycleError("Psychic use trigger evidence must be an object.")

    def evidence(key: str) -> str | None:
        value = None if trigger is None else trigger.get(key)
        if value is not None and (type(value) is not str or not value):
            raise GameLifecycleError("Psychic use decision evidence is malformed.")
        return value

    use = PsychicAbilityUse(
        usage_key="pending",
        restriction_source_id=PSYCHIC_SOURCE_ID,
        game_id=context.game_id,
        player_id=context.player_id,
        rules_unit_instance_id=unit.unit_instance_id,
        ability_source_id=rule_ir.source_id,
        battle_round=context.battle_round,
        active_player_id=context.active_player_id,
        phase=context.phase,
        psychic_level=level,
        source_rule_id=rule_ir.rule_id,
        source_rule_ir_hash=rule_ir.ir_hash(),
        source_instance_id=context.source_unit_instance_id,
        source_component_unit_instance_id=(
            unit.component_unit_id_for_model(model_id)
            if model_id is not None
            else context.source_unit_instance_id
            if context.source_unit_instance_id in unit.component_unit_instance_ids
            else None
        ),
        source_model_instance_id=model_id,
        component_unit_instance_ids=tuple(sorted(unit.component_unit_instance_ids)),
        catalog_record_id=evidence("catalog_record_id"),
        request_id=evidence("request_id"),
        result_id=evidence("result_id"),
    )
    return msgspec.structs.replace(use, usage_key=use.canonical_key())


def record_psychic_ability_use(
    *,
    use: PsychicAbilityUse | None,
    event_log: EventLog | None,
) -> tuple[EventRecord, ...]:
    if use is None:
        return ()
    if event_log is None:
        raise GameLifecycleError("Psychic use requires authoritative event history.")
    if any(previous.usage_key == use.usage_key for previous in psychic_uses(event_log)):
        raise GameLifecycleError("Psychic ability use was already consumed.")
    return (event_log.append(PSYCHIC_ABILITY_USED_EVENT, use.to_payload()),)


def psychic_source_unavailable_reason(
    *,
    rule_ir: RuleIR,
    state: GameState,
    event_log: EventLog,
    player_id: str,
    source_unit_instance_id: str,
    source_model_instance_id: str | None,
) -> str | None:
    from warhammer40k_core.engine.rule_execution import RuleExecutionContext

    if psychic_ability_level(rule_ir) is None:
        return None
    return psychic_ability_unavailable_reason(
        rule_ir=rule_ir,
        context=RuleExecutionContext(
            game_id=state.game_id,
            player_id=player_id,
            battle_round=state.battle_round,
            phase=state.current_battle_phase,
            active_player_id=state.active_player_id,
            source_unit_instance_id=source_unit_instance_id,
            source_model_instance_id=source_model_instance_id,
            state=state,
            event_log=event_log,
        ),
    )
