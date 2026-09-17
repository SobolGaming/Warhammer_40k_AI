"""Authenticate committed instance choices against their shared decision records."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.core_ability_damage_selection import is_deadly_demise_instance_request
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.weapon_selection_context import (
    WeaponSelectionContext,
    WeaponSelectionContextPayload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.decision_record import DecisionRecord
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.weapon_declaration import RangedAttackPool


def validate_ability_instance_history(*, state: GameState, decisions: DecisionController) -> None:
    pools: list[RangedAttackPool] = []
    for shooting in (state.shooting_phase_state, state.out_of_phase_shooting_state):
        if shooting is not None:
            pools.extend(shooting.attack_pools)
            if shooting.attack_sequence is not None:
                pools.extend(shooting.attack_sequence.attack_pools)
    if state.fight_phase_state is not None and state.fight_phase_state.attack_sequence is not None:
        pools.extend(state.fight_phase_state.attack_sequence.attack_pools)
    from warhammer40k_core.engine.weapon_declaration import (
        RangedAttackPool,
        RangedAttackPoolPayload,
    )

    for event in decisions.event_log.records:
        if event.event_type not in {
            "shooting_declaration_accepted",
            "out_of_phase_shooting_declaration_accepted",
        }:
            continue
        raw_pools = _object(event.payload).get("attack_pools")
        if not isinstance(raw_pools, list):
            raise GameLifecycleError("Accepted weapon declaration requires its pools.")
        for raw in raw_pools:
            raw_pool = _object(raw)
            if raw_pool.get("selected_weapon_ability_ids"):
                pools.append(RangedAttackPool.from_payload(cast(RangedAttackPoolPayload, raw_pool)))
    for pool in pools:
        if pool.selected_weapon_ability_ids:
            validate_weapon_pool_choice(pool, tuple(decisions.records))
    _validate_deadly_demise_events(decisions)


def validate_weapon_pool_choice(
    pool: RangedAttackPool, records: tuple[DecisionRecord, ...]
) -> None:
    context = pool.weapon_selection_context
    if context is None:
        raise GameLifecycleError("Selected weapon instances require their source context.")
    matches: list[tuple[DecisionRecord, dict[str, JsonValue]]] = []
    for record in records:
        if record.request.decision_type not in {
            "submit_shooting_declaration",
            "submit_melee_declaration",
        }:
            continue
        payload = _object(record.result.payload)
        if (
            context.source_request_id != record.request.request_id
            and context.source_request_id != payload.get("source_decision_result_id")
        ):
            continue
        declarations = payload.get("declarations")
        if not isinstance(declarations, list):
            raise GameLifecycleError("Weapon choice history requires declarations.")
        for declaration in declarations:
            row = _object(declaration)
            if (
                row.get("attacker_model_instance_id"),
                row.get("wargear_id"),
                row.get("weapon_profile_id"),
            ) == (pool.attacker_model_instance_id, pool.wargear_id, pool.weapon_profile_id):
                matches.append((record, row))
    if len(matches) != 1 or matches[0][1].get("selected_weapon_ability_ids", []) != list(
        pool.selected_weapon_ability_ids
    ):
        raise GameLifecycleError("Committed weapon instances disagree with their declaration.")
    request = _object(matches[0][0].request.payload)
    proposal = _object(request["proposal_request"])
    rows = proposal.get("target_candidates", proposal.get("available_weapons"))
    if not isinstance(rows, list):
        raise GameLifecycleError("Weapon choice history requires its offered inventory.")
    offered: list[WeaponSelectionContext] = []
    for offered_row in rows:
        raw = _object(offered_row).get("weapon_ability_selection_context")
        if isinstance(raw, dict):
            inventory = WeaponSelectionContext.from_payload(
                cast(WeaponSelectionContextPayload, raw)
            )
            if inventory.weapon_instance_id == context.weapon_instance_id:
                offered.append(inventory)
    if not any(
        all(
            profile in dict(inventory.target_profiles).values()
            for _, profile in context.target_profiles
        )
        for inventory in offered
    ):
        raise GameLifecycleError("Committed weapon inventory differs from its offered sources.")


def _validate_deadly_demise_events(decisions: DecisionController) -> None:
    from warhammer40k_core.engine.ability_instance_selection import DUPLICATED_ABILITIES_SOURCE_ID

    expected: list[JsonValue] = []
    for record in decisions.records:
        if not is_deadly_demise_instance_request(record.request):
            continue
        payload = _object(record.request.payload)
        sources = payload["sources"]
        if not isinstance(sources, list):
            raise GameLifecycleError("Deadly Demise history requires its sources.")
        selected = [
            source
            for source in sources
            if _object(source).get("source_id") == record.result.selected_option_id
        ]
        if len(selected) != 1:
            raise GameLifecycleError("Deadly Demise history selection drift.")
        expected.append(
            validate_json_value(
                {
                    "request_id": record.request.request_id,
                    "result_id": record.result.result_id,
                    "player_id": record.result.actor_id,
                    "ability_family": "deadly_demise",
                    "source_rule_id": DUPLICATED_ABILITIES_SOURCE_ID,
                    "selected_source": selected[0],
                    "destruction_context": payload["destruction_context"],
                }
            )
        )
    actual = [
        event.payload
        for event in decisions.event_log.records
        if event.event_type == "core_ability_instance_selected"
        and isinstance(event.payload, dict)
        and event.payload.get("ability_family") == "deadly_demise"
    ]
    if actual != expected:
        raise GameLifecycleError("Deadly Demise selection event drift.")


def _object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Ability instance history requires an object.")
    return value
