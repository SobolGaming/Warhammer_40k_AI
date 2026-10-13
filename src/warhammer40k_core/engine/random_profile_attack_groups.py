"""Authenticate defensive profile occurrences against selected gathered attacks."""

from __future__ import annotations

from typing import cast

from warhammer40k_core.engine.attack_sequence_model import (
    SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE,
    GatheredAttackGroup,
)
from warhammer40k_core.engine.attack_sequence_selection import (
    _gathered_attack_group_id,
    identical_attack_signature,
    selected_attack_weapon_group_from_result,
)
from warhammer40k_core.engine.attack_sequence_validation import (
    _validate_gathered_group_matches_attack_pools,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, canonical_json
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool, RangedAttackPoolPayload


def validate_profile_attack_group(
    *,
    sequence_id: str,
    pool_index: int,
    attack_index: int | None,
    target_unit_instance_id: str,
    events: tuple[EventRecord, ...],
    decisions: tuple[DecisionRecord, ...],
) -> None:
    """Use only selected groups recorded before this occurrence, never offered groups.

    Declaration and retargeting events own the physical pools. The selected
    finite decision owns their gathered identity; the same contribution and
    signature validators used by live resolution authenticate its total.
    """
    by_result = {record.result.result_id: record for record in decisions}
    by_record = {record.record_id: record for record in decisions}
    pools: tuple[RangedAttackPool, ...] = ()
    actor: str | None = None
    declaration_frame: dict[str, JsonValue] | None = None
    source_phase: BattlePhase | None = None
    selected: GatheredAttackGroup | None = None
    used: set[int] = set()
    for event in events:
        body = event.payload
        if not isinstance(body, dict):
            continue
        if event.event_type in {
            "shooting_declaration_accepted",
            "out_of_phase_shooting_declaration_accepted",
            "melee_declaration_accepted",
        }:
            declared_sequence = (
                f"attack-sequence:{body.get('result_id')}"
                if event.event_type == "shooting_declaration_accepted"
                else body.get("attack_sequence_id")
            )
            if declared_sequence != sequence_id:
                continue
            result_id = body.get("result_id")
            record = by_result.get(result_id) if isinstance(result_id, str) else None
            if (
                record is None
                or record.request.request_id != body.get("request_id")
                or record.result.actor_id is None
                or pools
            ):
                raise GameLifecycleError("Random defensive profile lacks its accepted declaration.")
            actor = record.result.actor_id
            pools = _declared_pools(body)
            source_phase = (
                BattlePhase.FIGHT
                if event.event_type == "melee_declaration_accepted"
                else BattlePhase.SHOOTING
            )
            if event.event_type == "melee_declaration_accepted":
                proposal_request = body.get("proposal_request")
                proposal = body.get("proposal")
                declaration_frame = {
                    "game_id": body.get("game_id"),
                    "battle_round": body.get("battle_round"),
                    "unit_instance_id": proposal_request.get("unit_instance_id")
                    if isinstance(proposal_request, dict)
                    else None,
                    "player_id": proposal.get("player_id") if isinstance(proposal, dict) else None,
                }
            else:
                declaration_frame = {
                    "game_id": body.get("game_id"),
                    "battle_round": body.get("battle_round"),
                    "unit_instance_id": body.get("unit_instance_id"),
                    "player_id": body.get(
                        "player_id"
                        if event.event_type == "out_of_phase_shooting_declaration_accepted"
                        else "active_player_id"
                    ),
                }
        elif event.event_type == "target_replacement_resolved":
            context = body.get("context")
            if isinstance(context, dict) and context.get("action_id") == sequence_id:
                if not pools:
                    raise GameLifecycleError(
                        "Random defensive profile retargeting lacks a declaration."
                    )
                pools = _declared_pools(body)
                used_indices = body.get("used_pool_indices")
                if (
                    not isinstance(used_indices, list)
                    or any(
                        type(index) is not int or not 0 <= index < len(pools)
                        for index in used_indices
                    )
                    or not used.issubset(used_indices)
                ):
                    raise GameLifecycleError(
                        "Random defensive profile retargeted pool inventory drifted."
                    )
                used = set(cast(list[int], used_indices))
                selected = None
        elif event.event_type == "decision_recorded":
            result = body.get("result")
            if not isinstance(result, dict):
                continue
            selection = result.get("payload")
            if (
                result.get("decision_type") != SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE
                or not isinstance(selection, dict)
                or selection.get("sequence_id") != sequence_id
            ):
                continue
            record_id = body.get("record_id")
            record = by_record.get(record_id) if isinstance(record_id, str) else None
            if record is None or canonical_json(record.to_payload()) != canonical_json(body):
                raise GameLifecycleError(
                    "Random defensive profile group lacks its recorded decision."
                )
            request = record.request.payload
            if (
                not isinstance(request, dict)
                or request.get("sequence_id") != sequence_id
                or record.request.actor_id != actor
                or not pools
            ):
                raise GameLifecycleError(
                    "Random defensive profile group selection context drifted."
                )
            selected = selected_attack_weapon_group_from_result(record.result)
            _validate_gathered_group_matches_attack_pools(
                attack_pools=pools,
                used_pool_indices=tuple(sorted(used)),
                gathered_group=selected,
            )
            if selected.native_snapshots:
                from warhammer40k_core.engine.attack_sequence_state import AttackSequence
                from warhammer40k_core.engine.native_attack_gathering import (
                    gathered_groups_for_pending_request,
                )

                first = selected.native_snapshots[0]
                if (
                    actor is None
                    or declaration_frame is None
                    or source_phase is None
                    or first.source_phase is not source_phase
                    or request.get("phase") != source_phase.value
                    or type(declaration_frame.get("game_id")) is not str
                    or request.get("game_id") != declaration_frame.get("game_id")
                    or type(request.get("battle_round")) is not int
                    or request.get("battle_round") != first.battle_round
                    or request.get("battle_round") != declaration_frame.get("battle_round")
                    or declaration_frame.get("player_id") != actor
                    or request.get("attacker_player_id") != actor
                    or type(request.get("attacking_unit_instance_id")) is not str
                    or request.get("attacking_unit_instance_id")
                    != declaration_frame.get("unit_instance_id")
                ):
                    raise GameLifecycleError("Random defensive native group frame drifted.")
                boundary = AttackSequence(
                    sequence_id=sequence_id,
                    source_phase=source_phase,
                    attacker_player_id=actor,
                    attacking_unit_instance_id=cast(str, request["attacking_unit_instance_id"]),
                    attack_pools=pools,
                    used_pool_indices=tuple(sorted(used)),
                )
                groups = gathered_groups_for_pending_request(
                    attack_sequence=boundary,
                    target_unit_instance_id=selected.target_unit_instance_id,
                    target_has_character=selected.target_has_character,
                    request=record.request,
                )
                matches = tuple(group for group in groups if group.group_id == selected.group_id)
                if len(matches) != 1 or matches[0] != selected:
                    raise GameLifecycleError("Random defensive native selected boundary drifted.")
                expected_indices = matches[0].pool_indices
            else:
                expected_indices = tuple(
                    index
                    for index, pool in enumerate(pools)
                    if index not in used
                    and pool.target_unit_instance_id == selected.target_unit_instance_id
                    and identical_attack_signature(
                        pool, target_has_character=selected.target_has_character
                    )
                    == selected.signature
                )
            if (
                selected.pool_indices != expected_indices
                or selected.group_id != record.result.selected_option_id
                or selected.group_id
                != _gathered_attack_group_id(
                    target_unit_instance_id=selected.target_unit_instance_id,
                    target_has_character=selected.target_has_character,
                    signature=selected.signature,
                    pool_indices=selected.pool_indices,
                )
                or request.get("target_unit_instance_id") != selected.target_unit_instance_id
                or selection.get("target_unit_instance_id") != selected.target_unit_instance_id
            ):
                raise GameLifecycleError(
                    "Random defensive profile gathered group identity drifted."
                )
            used.update(selected.pool_indices)
        elif (
            event.event_type == "attack_sequence_completed"
            and body.get("sequence_id") == sequence_id
        ):
            selected = None
    if (
        selected is None
        or selected.primary_pool_index != pool_index
        or selected.target_unit_instance_id != target_unit_instance_id
        or (attack_index is not None and not 0 <= attack_index < selected.total_attacks)
    ):
        raise GameLifecycleError("Random defensive profile lacks its selected gathered attack.")


def _declared_pools(body: dict[str, JsonValue]) -> tuple[RangedAttackPool, ...]:
    raw = body.get("attack_pools")
    if not isinstance(raw, list) or not raw or any(not isinstance(pool, dict) for pool in raw):
        raise GameLifecycleError("Random defensive profile declaration pools are invalid.")
    return tuple(RangedAttackPool.from_payload(cast(RangedAttackPoolPayload, pool)) for pool in raw)
