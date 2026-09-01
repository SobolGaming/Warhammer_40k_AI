from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollSpec,
    DiceRollState,
    DiceRollStatePayload,
)
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
)
from warhammer40k_core.engine.battle_round_hooks import (
    SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
)
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockForcedTestApplication,
    BattleShockHookRegistry,
)
from warhammer40k_core.engine.catalog_contextual_status_consumption import (
    CATALOG_IR_BATTLE_SHOCK_FORCED_TEST_CONSUMER_ID,
    hook_ids_for_effect,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_clauses_from_record,
    catalog_rule_ir_consumers_for_clause,
    catalog_rule_record_source_matches_unit,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    effect_with_selected_target,
)
from warhammer40k_core.engine.command_battle_shock_candidates import (
    CommandBattleShockCandidate,
    forced_test_applications_from_candidate_inventory,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.effects import (
    GENERIC_RULE_EFFECT_KIND,
    EffectExpirationKind,
    EffectExpirationPayload,
    PersistingEffect,
    PersistingEffectPayload,
)
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.faction_rule_states import (
    FactionRuleState,
    FactionRuleStatePayload,
)
from warhammer40k_core.engine.mutation_decision_authority import (
    validate_mutation_decision_closure,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, SetupStep
from warhammer40k_core.engine.primary_mission_boundary_physical_authority import (
    PhysicalModelAuthority,
    physical_model_authority_before_event,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.geometry.volume import Model as GeometryModel
from warhammer40k_core.geometry.volume import ModelVolume
from warhammer40k_core.rules.rule_ir import RuleEffectSpec, RuleEffectSpecPayload, RuleIRError

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_knights import (
        army_rule as _chaos_knights_types,
    )
    from warhammer40k_core.engine.game_state import GameState

_SELECTED_TARGET_EFFECT_EVENTS = frozenset(
    {
        "catalog_selected_target_effect_selected",
        "catalog_post_shoot_hit_target_effect_selected",
        "catalog_shooting_start_selected_target_effect_selected",
    }
)
_HARBINGERS_SELECTED_EVENT = "chaos_knights_harbingers_of_dread_selected"
_CATALOG_PROVIDER_KEY = (
    CATALOG_IR_BATTLE_SHOCK_FORCED_TEST_CONSUMER_ID,
    CATALOG_IR_BATTLE_SHOCK_FORCED_TEST_CONSUMER_ID,
)


def validate_command_forced_test_applications(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    snapshot_index: int,
    battle_round: int,
    active_player_id: str,
    candidates: tuple[CommandBattleShockCandidate, ...],
    battle_shock_hook_registry: BattleShockHookRegistry,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> None:
    """Recompute every loaded Command forced-test provider at the snapshot boundary."""

    from warhammer40k_core.engine.catalog_battle_shock_runtime import (
        catalog_forced_battle_shock_unit_ids,
    )
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_knights import (
        army_rule as chaos_knights,
    )

    if type(battle_shock_hook_registry) is not BattleShockHookRegistry:
        raise GameLifecycleError("Command forced-test authority requires its loaded registry.")
    if type(snapshot_index) is not int or not 0 <= snapshot_index < len(event_records):
        raise GameLifecycleError("Command forced-test snapshot index is invalid.")
    if type(battle_round) is not int or battle_round < 1:
        raise GameLifecycleError("Command forced-test battle round is invalid.")
    if active_player_id not in state.player_ids:
        raise GameLifecycleError("Command forced-test active player is invalid.")
    physical_rows = physical_model_authority_before_event(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        event_index=snapshot_index,
    )
    expected: list[BattleShockForcedTestApplication] = []
    for binding in battle_shock_hook_registry.bindings:
        handler = binding.forced_test_handler
        if handler is None:
            continue
        provider_key = (binding.hook_id, binding.source_id)
        if provider_key == _CATALOG_PROVIDER_KEY:
            if handler is not catalog_forced_battle_shock_unit_ids:
                raise GameLifecycleError("Command catalog forced-test handler identity drifted.")
            target_ids = _catalog_forced_target_ids(
                state=state,
                event_records=event_records,
                decision_records=decision_records,
                snapshot_index=snapshot_index,
                battle_round=battle_round,
                active_player_id=active_player_id,
                candidates=candidates,
                physical_rows=physical_rows,
                ability_indexes_by_player_id=ability_indexes_by_player_id,
            )
        elif provider_key == (
            chaos_knights.BATTLE_SHOCK_HOOK_ID,
            chaos_knights.SOURCE_RULE_ID,
        ):
            if handler is not chaos_knights.harbingers_forced_battle_shock_unit_ids:
                raise GameLifecycleError("Command Harbingers forced-test handler identity drifted.")
            target_ids = _harbingers_forced_target_ids(
                state=state,
                event_records=event_records,
                decision_records=decision_records,
                snapshot_index=snapshot_index,
                active_player_id=active_player_id,
                candidates=candidates,
                physical_rows=physical_rows,
            )
        else:
            raise GameLifecycleError("Command forced-test provider is not historically supported.")
        if target_ids:
            expected.append(
                BattleShockForcedTestApplication(
                    hook_id=binding.hook_id,
                    source_id=binding.source_id,
                    unit_instance_ids=target_ids,
                )
            )
    expected_applications = tuple(sorted(expected, key=lambda row: (row.hook_id, row.source_id)))
    retained = forced_test_applications_from_candidate_inventory(candidates)
    if retained != expected_applications:
        raise GameLifecycleError("Command Battle-shock forced-test applications drifted.")


def _catalog_forced_target_ids(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    snapshot_index: int,
    battle_round: int,
    active_player_id: str,
    candidates: tuple[CommandBattleShockCandidate, ...],
    physical_rows: tuple[PhysicalModelAuthority, ...],
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> tuple[str, ...]:
    candidate_ids = {candidate.unit_instance_id for candidate in candidates}
    active_effects: list[PersistingEffect] = []
    seen_effect_ids: set[str] = set()
    physical_cache: dict[int, tuple[PhysicalModelAuthority, ...]] = {snapshot_index: physical_rows}
    for event_index, event in enumerate(event_records[:snapshot_index]):
        if event.event_type not in _SELECTED_TARGET_EFFECT_EVENTS:
            continue
        payload = _object(event.payload, context="catalog selected-target event")
        raw_effects = payload.get("persisting_effects")
        if not isinstance(raw_effects, list):
            raise GameLifecycleError("Catalog forced-test effect inventory is invalid.")
        forced_rows = tuple(
            effect
            for raw_effect in raw_effects
            if (effect := _forced_persisting_effect_or_none(raw_effect)) is not None
        )
        if not forced_rows:
            continue
        request_id = _string(payload.get("request_id"), field="catalog request_id")
        result_id = _string(payload.get("result_id"), field="catalog result_id")
        record = validate_mutation_decision_closure(
            event_records=event_records,
            decision_records=decision_records,
            mutation_index=event_index,
            request_id=request_id,
            result_id=result_id,
        )
        expected_rows = _expected_catalog_forced_effects(
            state=state,
            event=event,
            record=record,
            ability_indexes_by_player_id=ability_indexes_by_player_id,
            physical_rows=physical_cache.setdefault(
                event_index,
                physical_model_authority_before_event(
                    state=state,
                    event_records=event_records,
                    decision_records=decision_records,
                    event_index=event_index,
                ),
            ),
        )
        if tuple(sorted(forced_rows, key=lambda effect: effect.effect_id)) != expected_rows:
            raise GameLifecycleError("Catalog forced-test source-effect authority drifted.")
        for effect in forced_rows:
            if effect.effect_id in seen_effect_ids:
                raise GameLifecycleError("Catalog forced-test source effect is duplicated.")
            seen_effect_ids.add(effect.effect_id)
            if _effect_is_active_at_command_snapshot(
                state=state,
                effect=effect,
                battle_round=battle_round,
                active_player_id=active_player_id,
            ):
                active_effects.append(effect)
    forced_ids = {
        unit_id
        for effect in active_effects
        if effect.owner_player_id != active_player_id
        for unit_id in effect.target_unit_instance_ids
        if unit_id in candidate_ids
    }
    return tuple(sorted(forced_ids))


def _expected_catalog_forced_effects(
    *,
    state: GameState,
    event: EventRecord,
    record: DecisionRecord,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    physical_rows: tuple[PhysicalModelAuthority, ...],
) -> tuple[PersistingEffect, ...]:
    payload = _object(event.payload, context="catalog selected-target event")
    player_id = _string(payload.get("player_id"), field="catalog player_id")
    if record.request.request_id != payload.get(
        "request_id"
    ) or record.result.result_id != payload.get("result_id"):
        raise GameLifecycleError("Catalog forced-test decision identity drifted.")
    if record.result.actor_id != player_id:
        raise GameLifecycleError("Catalog forced-test decision actor drifted.")
    if record.result.selected_option_id != payload.get("selected_option_id"):
        raise GameLifecycleError("Catalog forced-test selected option drifted.")
    result_payload = _object(record.result.payload, context="catalog selected-target result")
    effect_records = result_payload.get("generic_rule_effect_records")
    if not isinstance(effect_records, list) or any(
        not isinstance(row, dict) for row in effect_records
    ):
        raise GameLifecycleError("Catalog forced-test result effects are invalid.")
    expected: list[PersistingEffect] = []
    for effect_index, raw_record in enumerate(effect_records):
        effect_record = cast(dict[str, JsonValue], raw_record)
        expected_effect = _catalog_forced_effect_from_record(
            state=state,
            event=event,
            decision_record=record,
            effect_index=effect_index,
            effect_record=effect_record,
            ability_indexes_by_player_id=ability_indexes_by_player_id,
            physical_rows=physical_rows,
        )
        if expected_effect is not None:
            expected.append(expected_effect)
    return tuple(sorted(expected, key=lambda effect: effect.effect_id))


def _catalog_forced_effect_from_record(
    *,
    state: GameState,
    event: EventRecord,
    decision_record: DecisionRecord,
    effect_index: int,
    effect_record: dict[str, JsonValue],
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    physical_rows: tuple[PhysicalModelAuthority, ...],
) -> PersistingEffect | None:
    if effect_record.get("immediate_effect_kind") is not None:
        return None
    raw_effect_payload = effect_record.get("effect_payload")
    if not isinstance(raw_effect_payload, dict):
        return None
    raw_rule_effect = raw_effect_payload.get("effect")
    if not isinstance(raw_rule_effect, dict):
        return None
    try:
        transformed_effect = RuleEffectSpec.from_payload(
            cast(RuleEffectSpecPayload, raw_rule_effect)
        )
    except RuleIRError as exc:
        raise GameLifecycleError("Catalog forced-test RuleIR effect is invalid.") from exc
    if CATALOG_IR_BATTLE_SHOCK_FORCED_TEST_CONSUMER_ID not in _consumer_ids_for_transformed_effect(
        transformed_effect
    ):
        return None
    event_payload = _object(event.payload, context="catalog selected-target event")
    player_id = _string(event_payload.get("player_id"), field="catalog player_id")
    catalog_record_id = _string(event_payload.get("catalog_record_id"), field="catalog_record_id")
    source_record = _loaded_ability_record(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        player_id=player_id,
        record_id=catalog_record_id,
    )
    source_rule_id = _string(event_payload.get("source_rule_id"), field="source_rule_id")
    if (
        source_record.disabled
        or source_record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID
        or source_record.definition.source_id != source_rule_id
        or effect_record.get("source_rule_id") != source_rule_id
    ):
        raise GameLifecycleError("Catalog forced-test loaded source record drifted.")
    source_unit_id = _string(
        event_payload.get("source_unit_instance_id"), field="source_unit_instance_id"
    )
    source_unit = _unit_for_player(state=state, player_id=player_id, unit_id=source_unit_id)
    placed_source_model_ids = tuple(
        sorted(
            model.model_instance_id
            for model in source_unit.own_models
            if _placed_alive(_physical_by_id(physical_rows).get(model.model_instance_id))
        )
    )
    if not placed_source_model_ids or not catalog_rule_record_source_matches_unit(
        record=source_record,
        unit=source_unit,
        current_model_instance_ids=placed_source_model_ids,
    ):
        raise GameLifecycleError("Catalog forced-test source unit authority drifted.")
    source_model_id = event_payload.get("source_model_instance_id")
    if source_model_id is not None and source_model_id not in placed_source_model_ids:
        raise GameLifecycleError("Catalog forced-test source model authority drifted.")
    clause_id = _string(effect_record.get("effect_clause_id"), field="effect_clause_id")
    clause_matches = tuple(
        clause
        for clause in catalog_rule_clauses_from_record(source_record)
        if clause.clause_id == clause_id
    )
    if len(clause_matches) != 1:
        raise GameLifecycleError("Catalog forced-test effect clause authority drifted.")
    clause = clause_matches[0]
    source_effect_index = effect_record.get("effect_index")
    if type(source_effect_index) is not int or not 0 <= source_effect_index < len(clause.effects):
        raise GameLifecycleError("Catalog forced-test effect index authority drifted.")
    selected_target_id = _string(
        event_payload.get("target_unit_instance_id"), field="target_unit_instance_id"
    )
    expected_transformed = effect_with_selected_target(
        clause.effects[source_effect_index],
        selected_target_unit_instance_id=selected_target_id,
        clause=clause,
    )
    if (
        transformed_effect != expected_transformed
        or CATALOG_IR_BATTLE_SHOCK_FORCED_TEST_CONSUMER_ID
        not in catalog_rule_ir_consumers_for_clause(clause)
    ):
        raise GameLifecycleError("Catalog forced-test RuleIR source semantics drifted.")
    if (
        effect_record.get("catalog_record_id") != catalog_record_id
        or effect_record.get("source_unit_instance_id") != source_unit_id
        or effect_record.get("selection_clause_id") != event_payload.get("selection_clause_id")
        or effect_record.get("selected_target_unit_instance_id") != selected_target_id
    ):
        raise GameLifecycleError("Catalog forced-test selected-target binding drifted.")
    try:
        effect = PersistingEffect.from_payload(
            {
                "effect_id": (
                    f"{decision_record.result.result_id}:{event.event_type}:{effect_index:03d}"
                ),
                "source_rule_id": cast(str, effect_record["source_rule_id"]),
                "owner_player_id": cast(str, effect_record["owner_player_id"]),
                "target_unit_instance_ids": cast(
                    list[str], effect_record["target_unit_instance_ids"]
                ),
                "started_battle_round": cast(int, effect_record["started_battle_round"]),
                "started_phase": cast(str | None, effect_record["started_phase"]),
                "expiration": cast(EffectExpirationPayload, effect_record["expiration"]),
                "effect_payload": validate_json_value(raw_effect_payload),
            }
        )
    except KeyError as exc:
        raise GameLifecycleError("Catalog forced-test effect record is incomplete.") from exc
    if (
        effect.owner_player_id != player_id
        or selected_target_id not in effect.target_unit_instance_ids
    ):
        raise GameLifecycleError("Catalog forced-test effect ownership drifted.")
    return effect


def _consumer_ids_for_transformed_effect(effect: RuleEffectSpec) -> tuple[str, ...]:
    return hook_ids_for_effect(effect)


def _forced_persisting_effect_or_none(value: JsonValue) -> PersistingEffect | None:
    if not isinstance(value, dict) or set(value) != {
        "effect_id",
        "source_rule_id",
        "owner_player_id",
        "target_unit_instance_ids",
        "started_battle_round",
        "started_phase",
        "expiration",
        "effect_payload",
    }:
        return None
    effect = PersistingEffect.from_payload(cast(PersistingEffectPayload, value))
    payload = effect.effect_payload
    if not isinstance(payload, dict) or payload.get("effect_kind") != GENERIC_RULE_EFFECT_KIND:
        return None
    raw_effect = payload.get("effect")
    if not isinstance(raw_effect, dict):
        raise GameLifecycleError("Catalog forced-test generic effect payload is missing.")
    try:
        rule_effect = RuleEffectSpec.from_payload(cast(RuleEffectSpecPayload, raw_effect))
    except RuleIRError as exc:
        raise GameLifecycleError("Catalog forced-test generic effect payload is invalid.") from exc
    if CATALOG_IR_BATTLE_SHOCK_FORCED_TEST_CONSUMER_ID not in hook_ids_for_effect(rule_effect):
        return None
    return effect


def _effect_is_active_at_command_snapshot(
    *,
    state: GameState,
    effect: PersistingEffect,
    battle_round: int,
    active_player_id: str,
) -> bool:
    expiration = effect.expiration
    kind = expiration.expiration_kind
    if kind is EffectExpirationKind.END_OF_BATTLE:
        return True
    try:
        player_index = state.turn_order.index(active_player_id)
        command_index = state.battle_phase_sequence.index(BattlePhase.COMMAND)
    except ValueError as exc:
        raise GameLifecycleError("Catalog forced-test snapshot position drifted.") from exc
    current = (battle_round, player_index, command_index, 1)
    if kind in {EffectExpirationKind.START_PHASE, EffectExpirationKind.END_PHASE}:
        if (
            expiration.battle_round is None
            or expiration.player_id is None
            or expiration.phase is None
        ):
            raise GameLifecycleError("Catalog forced-test phase expiration is incomplete.")
        try:
            boundary = (
                expiration.battle_round,
                state.turn_order.index(expiration.player_id),
                state.battle_phase_sequence.index(expiration.phase),
                0 if kind is EffectExpirationKind.START_PHASE else 2,
            )
        except ValueError as exc:
            raise GameLifecycleError("Catalog forced-test phase expiration drifted.") from exc
        return current < boundary
    if kind in {EffectExpirationKind.START_TURN, EffectExpirationKind.END_TURN}:
        if expiration.battle_round is None or expiration.player_id is None:
            raise GameLifecycleError("Catalog forced-test turn expiration is incomplete.")
        try:
            expiration_player_index = state.turn_order.index(expiration.player_id)
        except ValueError as exc:
            raise GameLifecycleError("Catalog forced-test turn expiration drifted.") from exc
        boundary = (
            expiration.battle_round,
            expiration_player_index,
            -1 if kind is EffectExpirationKind.START_TURN else len(state.battle_phase_sequence),
            0 if kind is EffectExpirationKind.START_TURN else 2,
        )
        return current < boundary
    if kind in {EffectExpirationKind.START_BATTLE_ROUND, EffectExpirationKind.END_BATTLE_ROUND}:
        if expiration.battle_round is None:
            raise GameLifecycleError("Catalog forced-test round expiration is incomplete.")
        boundary = (
            expiration.battle_round,
            -1 if kind is EffectExpirationKind.START_BATTLE_ROUND else len(state.turn_order),
            -1
            if kind is EffectExpirationKind.START_BATTLE_ROUND
            else len(state.battle_phase_sequence),
            0 if kind is EffectExpirationKind.START_BATTLE_ROUND else 2,
        )
        return current < boundary
    raise GameLifecycleError("Catalog forced-test expiration kind is unsupported.")


def _harbingers_forced_target_ids(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    snapshot_index: int,
    active_player_id: str,
    candidates: tuple[CommandBattleShockCandidate, ...],
    physical_rows: tuple[PhysicalModelAuthority, ...],
) -> tuple[str, ...]:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_knights import (
        army_rule as chaos_knights,
    )

    active_by_player = historical_harbingers_abilities(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        snapshot_index=snapshot_index,
    )
    candidate_models = {
        candidate.unit_instance_id: _geometry_models(
            state=state,
            model_ids=_model_ids_for_component_unit_ids(
                state=state,
                component_unit_instance_ids=candidate.component_unit_instance_ids,
            ),
            physical_rows=physical_rows,
        )
        for candidate in candidates
    }
    forced_ids: set[str] = set()
    for army in state.army_definitions:
        if (
            army.player_id == active_player_id
            or army.detachment_selection.faction_id != chaos_knights.CHAOS_KNIGHTS_FACTION_ID
        ):
            continue
        active = active_by_player.get(
            army.player_id,
            (chaos_knights.DreadAbility.DEATHLY_TERROR,),
        )
        if chaos_knights.DreadAbility.DISMAY not in active:
            continue
        aura_range = (
            chaos_knights.DREAD_AURA_RANGE_WITH_DOMINION_INCHES
            if chaos_knights.DreadAbility.DOMINION in active
            else chaos_knights.DREAD_AURA_RANGE_INCHES
        )
        source_models = tuple(
            model
            for unit in army.units
            if _unit_has_harbingers(unit)
            for model in _geometry_models(
                state=state,
                model_ids=tuple(model.model_instance_id for model in unit.own_models),
                physical_rows=physical_rows,
            )
        )
        for unit_id, target_models in candidate_models.items():
            if any(
                source.base_distance_to(target) <= aura_range
                for source in source_models
                for target in target_models
            ):
                forced_ids.add(unit_id)
    return tuple(sorted(forced_ids))


def historical_harbingers_abilities(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    snapshot_index: int,
) -> dict[str, tuple[_chaos_knights_types.DreadAbility, ...]]:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_knights import (
        army_rule as chaos_knights,
    )

    active: dict[str, list[_chaos_knights_types.DreadAbility]] = {}
    seen_rounds: set[tuple[str, int]] = set()
    final_states = {row.state_id: row for row in state.faction_rule_states}
    if len(final_states) != len(state.faction_rule_states):
        raise GameLifecycleError("Harbingers faction-rule state inventory is duplicated.")
    for event_index, event in enumerate(event_records[:snapshot_index]):
        if event.event_type != _HARBINGERS_SELECTED_EVENT:
            continue
        payload = _object(event.payload, context="Harbingers selection event")
        if set(payload) != {
            "game_id",
            "battle_round",
            "phase",
            "player_id",
            "source_rule_id",
            "hook_id",
            "selection_mode",
            "selected_dread_ability_ids",
            "dice_values",
            "faction_rule_state",
        }:
            raise GameLifecycleError("Harbingers selection event shape drifted.")
        if (
            payload.get("game_id") != state.game_id
            or payload.get("phase") != BattlePhase.COMMAND.value
        ):
            raise GameLifecycleError("Harbingers selection event context drifted.")
        player_id = _string(payload.get("player_id"), field="Harbingers player_id")
        battle_round = payload.get("battle_round")
        if (
            type(battle_round) is not int
            or battle_round not in chaos_knights.DREAD_SELECTION_BATTLE_ROUNDS
        ):
            raise GameLifecycleError("Harbingers selection battle round drifted.")
        if (player_id, battle_round) in seen_rounds:
            raise GameLifecycleError("Harbingers selection round is duplicated.")
        seen_rounds.add((player_id, battle_round))
        current = active.setdefault(player_id, [chaos_knights.DreadAbility.DEATHLY_TERROR])
        row = _harbingers_state_row(payload)
        if final_states.get(row.state_id) != row:
            raise GameLifecycleError("Harbingers persisted selection state drifted.")
        record = validate_mutation_decision_closure(
            event_records=event_records,
            decision_records=decision_records,
            mutation_index=event_index,
            request_id=row.request_id,
            result_id=row.result_id,
        )
        selected = _validate_harbingers_decision(
            state=state,
            event_records=event_records,
            event_index=event_index,
            payload=payload,
            row=row,
            record=record,
            prior_active=tuple(current),
        )
        if any(ability in current for ability in selected):
            raise GameLifecycleError("Harbingers selected ability was already active.")
        current.extend(selected)
    return {
        player_id: tuple(
            definition.ability
            for definition in chaos_knights.DREAD_DEFINITIONS
            if definition.ability in abilities
        )
        for player_id, abilities in active.items()
    }


def _validate_harbingers_decision(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    event_index: int,
    payload: dict[str, JsonValue],
    row: FactionRuleState,
    record: DecisionRecord,
    prior_active: tuple[_chaos_knights_types.DreadAbility, ...],
) -> tuple[_chaos_knights_types.DreadAbility, ...]:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_knights import (
        army_rule as chaos_knights,
    )

    player_id = row.player_id
    army = state.army_definition_for_player(player_id)
    if (
        army is None
        or army.detachment_selection.faction_id != chaos_knights.CHAOS_KNIGHTS_FACTION_ID
    ):
        raise GameLifecycleError("Harbingers selection owner authority drifted.")
    available = tuple(
        ability for ability in chaos_knights.ROLLABLE_DREAD_ABILITIES if ability not in prior_active
    )
    common_payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "battle_round": cast(int, payload["battle_round"]),
        "phase": BattlePhase.COMMAND.value,
        "player_id": player_id,
        "faction_id": chaos_knights.CHAOS_KNIGHTS_FACTION_ID,
        "source_rule_id": chaos_knights.SOURCE_RULE_ID,
        "hook_id": chaos_knights.HOOK_ID,
        "state_kind": chaos_knights.HARBINGERS_STATE_KIND,
        "effect_kind": chaos_knights.HARBINGERS_EFFECT_KIND,
        "selection_kind": chaos_knights.HARBINGERS_SELECTION_KIND,
        "target_unit_instance_ids": [
            unit.unit_instance_id for unit in army.units if _unit_has_harbingers(unit)
        ],
        "active_dread_ability_ids": [ability.value for ability in prior_active],
        "available_dread_ability_ids": [ability.value for ability in available],
        "rules_update_sources": [chaos_knights.DARKNESS_RULE_UPDATE_SOURCE],
    }
    if (
        record.request.decision_type != SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE
        or record.request.actor_id != player_id
        or record.request.payload != validate_json_value(common_payload)
        or record.request.options
        != tuple(
            sorted(
                chaos_knights.harbingers_selection_options(
                    common_payload=common_payload,
                    available=available,
                ),
                key=lambda option: option.option_id,
            )
        )
    ):
        raise GameLifecycleError("Harbingers selection request authority drifted.")
    if record.result.actor_id != player_id:
        raise GameLifecycleError("Harbingers selection result actor drifted.")
    selection_mode = _string(payload.get("selection_mode"), field="selection_mode")
    if selection_mode == "select":
        selected = _dread_tuple(payload.get("selected_dread_ability_ids"))
        if len(selected) != 1 or selected[0] not in available:
            raise GameLifecycleError("Harbingers manual selection authority drifted.")
        dice_values: tuple[int, ...] = ()
        roll_payload: JsonValue = None
    elif selection_mode == "roll_2d6":
        dice_values, roll_payload = _validated_harbingers_roll(
            event_records=event_records,
            event_index=event_index,
            player_id=player_id,
            raw_state=_object(row.payload, context="Harbingers state").get("roll_state"),
        )
        selected = _dreads_from_roll(dice_values=dice_values, prior_active=prior_active)
    else:
        raise GameLifecycleError("Harbingers selection mode is unsupported.")
    option = record.request.option_by_id(record.result.selected_option_id)
    if record.result.payload != option.payload:
        raise GameLifecycleError("Harbingers selected option payload drifted.")
    expected_state_payload = {
        "selection_kind": chaos_knights.HARBINGERS_SELECTION_KIND,
        "effect_kind": chaos_knights.HARBINGERS_EFFECT_KIND,
        "selection_mode": selection_mode,
        "selected_option_id": record.result.selected_option_id,
        "game_id": state.game_id,
        "battle_round": cast(int, payload["battle_round"]),
        "phase": BattlePhase.COMMAND.value,
        "player_id": player_id,
        "faction_id": chaos_knights.CHAOS_KNIGHTS_FACTION_ID,
        "source_rule_id": chaos_knights.SOURCE_RULE_ID,
        "hook_id": chaos_knights.HOOK_ID,
        "selected_dread_ability_ids": [ability.value for ability in selected],
        "selected_dread_ability_labels": [
            next(
                definition.label
                for definition in chaos_knights.DREAD_DEFINITIONS
                if definition.ability is ability
            )
            for ability in selected
        ],
        "dice_values": list(dice_values),
        "roll_state": roll_payload,
        "rules_update_sources": [chaos_knights.DARKNESS_RULE_UPDATE_SOURCE],
    }
    expected_outer = {
        "game_id": state.game_id,
        "battle_round": cast(int, payload["battle_round"]),
        "phase": BattlePhase.COMMAND.value,
        "player_id": player_id,
        "source_rule_id": chaos_knights.SOURCE_RULE_ID,
        "hook_id": chaos_knights.HOOK_ID,
        "selection_mode": selection_mode,
        "selected_dread_ability_ids": [ability.value for ability in selected],
        "dice_values": list(dice_values),
        "faction_rule_state": row.to_payload(),
    }
    if row.payload != validate_json_value(expected_state_payload) or payload != validate_json_value(
        expected_outer
    ):
        raise GameLifecycleError("Harbingers selection mutation authority drifted.")
    return selected


def _harbingers_state_row(payload: dict[str, JsonValue]) -> FactionRuleState:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_knights import (
        army_rule as chaos_knights,
    )

    raw = payload.get("faction_rule_state")
    if not isinstance(raw, dict):
        raise GameLifecycleError("Harbingers faction-rule state payload is invalid.")
    try:
        row = FactionRuleState.from_payload(cast(FactionRuleStatePayload, raw))
    except KeyError as exc:
        raise GameLifecycleError("Harbingers faction-rule state payload is incomplete.") from exc
    battle_round = payload.get("battle_round")
    expected_id = f"{chaos_knights.HOOK_ID}:{row.player_id}:round-{battle_round:02d}:selection"
    if (
        row.state_id != expected_id
        or row.faction_id != chaos_knights.CHAOS_KNIGHTS_FACTION_ID
        or row.source_rule_id != chaos_knights.SOURCE_RULE_ID
        or row.state_kind != chaos_knights.HARBINGERS_STATE_KIND
        or row.setup_step is not SetupStep.DECLARE_BATTLE_FORMATIONS
    ):
        raise GameLifecycleError("Harbingers faction-rule state identity drifted.")
    return row


def _validated_harbingers_roll(
    *,
    event_records: tuple[EventRecord, ...],
    event_index: int,
    player_id: str,
    raw_state: JsonValue,
) -> tuple[tuple[int, ...], JsonValue]:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_knights import (
        army_rule as chaos_knights,
    )

    if not isinstance(raw_state, dict):
        raise GameLifecycleError("Harbingers roll state is missing.")
    roll_state = DiceRollState.from_payload(cast(DiceRollStatePayload, raw_state))
    expected_spec = DiceRollSpec(
        expression=DiceExpression(quantity=2, sides=6),
        reason="Harbingers of Dread",
        roll_type=chaos_knights.HARBINGERS_DREAD_ROLL_TYPE,
        actor_id=player_id,
    )
    if (
        roll_state.original_result.spec != expected_spec
        or roll_state.rerolls
        or roll_state.result_override is not None
    ):
        raise GameLifecycleError("Harbingers dice semantics drifted.")
    matches = tuple(
        index
        for index, event in enumerate(event_records[:event_index])
        if event.event_type == "dice_rolled"
        and event.payload == roll_state.original_result.to_payload()
    )
    if len(matches) != 1:
        raise GameLifecycleError("Harbingers dice event authority drifted.")
    return roll_state.current_values, validate_json_value(roll_state.to_payload())


def _dreads_from_roll(
    *,
    dice_values: tuple[int, ...],
    prior_active: tuple[_chaos_knights_types.DreadAbility, ...],
) -> tuple[_chaos_knights_types.DreadAbility, ...]:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_knights import (
        army_rule as chaos_knights,
    )

    by_roll = {
        definition.roll_result: definition.ability
        for definition in chaos_knights.DREAD_DEFINITIONS
        if definition.roll_result is not None
    }
    selected: list[_chaos_knights_types.DreadAbility] = []
    for value in dice_values:
        ability = by_roll[value]
        if ability not in prior_active and ability not in selected:
            selected.append(ability)
    return tuple(selected)


def _dread_tuple(value: JsonValue) -> tuple[_chaos_knights_types.DreadAbility, ...]:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_knights import (
        army_rule as chaos_knights,
    )

    if not isinstance(value, list) or any(type(item) is not str for item in value):
        raise GameLifecycleError("Harbingers selected abilities are invalid.")
    try:
        return tuple(chaos_knights.DreadAbility(cast(str, item)) for item in value)
    except ValueError as exc:
        raise GameLifecycleError("Harbingers selected ability is unsupported.") from exc


def _unit_has_harbingers(unit: UnitInstance) -> bool:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_knights import (
        army_rule as chaos_knights,
    )

    return chaos_knights.CHAOS_KNIGHTS_FACTION_KEYWORD in (
        *unit.keywords,
        *unit.faction_keywords,
    ) or any(
        ability.source_id == chaos_knights.SOURCE_RULE_ID for ability in unit.datasheet_abilities
    )


def _geometry_models(
    *,
    state: GameState,
    model_ids: tuple[str, ...],
    physical_rows: tuple[PhysicalModelAuthority, ...],
) -> tuple[GeometryModel, ...]:
    physical_by_id = _physical_by_id(physical_rows)
    models_by_id = _models_by_id(state)
    geometries: list[GeometryModel] = []
    for model_id in model_ids:
        row = physical_by_id.get(model_id)
        if not _placed_alive(row):
            continue
        model = models_by_id.get(model_id)
        if model is None or row is None or row.pose is None:
            raise GameLifecycleError("Command forced-test model identity authority drifted.")
        geometries.append(
            GeometryModel(
                model_id=model_id,
                pose=row.pose,
                base=model.geometry.base_shape(),
                volume=ModelVolume(height=model.geometry.height_inches),
            )
        )
    return tuple(geometries)


def _models_by_id(state: GameState) -> dict[str, ModelInstance]:
    models = {
        model.model_instance_id: model
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
    }
    if len(models) != sum(
        len(unit.own_models) for army in state.army_definitions for unit in army.units
    ):
        raise GameLifecycleError("Command forced-test model identity is duplicated.")
    return models


def _model_ids_for_component_unit_ids(
    *,
    state: GameState,
    component_unit_instance_ids: tuple[str, ...],
) -> tuple[str, ...]:
    units_by_id = {
        unit.unit_instance_id: unit for army in state.army_definitions for unit in army.units
    }
    if any(unit_id not in units_by_id for unit_id in component_unit_instance_ids):
        raise GameLifecycleError("Command forced-test component identity authority drifted.")
    return tuple(
        sorted(
            model.model_instance_id
            for unit_id in component_unit_instance_ids
            for model in units_by_id[unit_id].own_models
        )
    )


def _physical_by_id(
    rows: tuple[PhysicalModelAuthority, ...],
) -> dict[str, PhysicalModelAuthority]:
    return {row.model_instance_id: row for row in rows}


def _placed_alive(row: PhysicalModelAuthority | None) -> bool:
    return row is not None and row.presence == "battlefield" and row.wounds_remaining > 0


def _unit_for_player(*, state: GameState, player_id: str, unit_id: str) -> UnitInstance:
    army = state.army_definition_for_player(player_id)
    if army is None:
        raise GameLifecycleError("Catalog forced-test source army is missing.")
    matching = tuple(unit for unit in army.units if unit.unit_instance_id == unit_id)
    if len(matching) != 1:
        raise GameLifecycleError("Catalog forced-test source unit identity drifted.")
    return matching[0]


def _loaded_ability_record(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    player_id: str,
    record_id: str,
) -> AbilityCatalogRecord:
    index = ability_indexes_by_player_id.get(player_id)
    if type(index) is not AbilityCatalogIndex:
        raise GameLifecycleError("Catalog forced-test ability index is missing.")
    matching = tuple(record for record in index.all_records() if record.record_id == record_id)
    if len(matching) != 1:
        raise GameLifecycleError("Catalog forced-test loaded record identity drifted.")
    return matching[0]


def _object(value: JsonValue, *, context: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{context} payload must be an object.")
    return value


def _string(value: JsonValue, *, field: str) -> str:
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Command forced-test {field} is invalid.")
    return value


__all__ = ("validate_command_forced_test_applications",)
