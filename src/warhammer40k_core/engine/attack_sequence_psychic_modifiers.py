"""Finite source-by-source Psychic choices shared by every attack host."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.engine.attack_modifier_snapshots import attack_modifier_snapshots
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.psychic_modifier_selection import (
    AttackModifierSnapshot,
    PsychicAttackModifierIgnoreSelection,
)
from warhammer40k_core.engine.weapon_abilities import is_psychic_weapon_profile
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_modifiers_2026_09 import (
    IGNORE_MODIFIERS_SOURCE_ID,
    PSYCHIC_MODIFIERS_SOURCE_ID,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.attack_sequence_state import AttackSequence
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
    from warhammer40k_core.engine.weapon_declaration import RangedAttackPool

DECISION_TYPE = "select_psychic_attack_modifier_ignores"
_CONTEXT_KEYS = frozenset(
    {
        "submission_kind",
        "attack_context_id",
        "attacking_unit_instance_id",
        "attacker_model_instance_id",
        "target_unit_instance_id",
        "weapon_profile_id",
        "source_phase",
        "pool_sha256",
        "effect_snapshot_sha256",
        "source_rule_ids",
    }
)

__all__ = (
    "_has_beneficial_psychic_modifier",
    "_has_detrimental_psychic_modifier",
    "_psychic_attack_modifier_ignore_options",
    "_psychic_attack_modifier_ignore_request",
    "_psychic_attack_modifier_ignore_selection_for_attack",
    "validate_psychic_attack_modifier_ignore_decision",
)


def _psychic_attack_modifier_ignore_request(
    *,
    state: GameState,
    pool: RangedAttackPool,
    attacker_player_id: str,
    attacking_unit_instance_id: str,
    attack_context_id: str,
    source_phase: BattlePhase,
    runtime_modifier_registry: RuntimeModifierRegistry,
    previous_selection: PsychicAttackModifierIgnoreSelection | None = None,
    request_id: str | None = None,
) -> DecisionRequest | None:
    if not is_psychic_weapon_profile(pool.weapon_profile):
        if previous_selection is not None:
            raise GameLifecycleError("Psychic weapon permission drift.")
        return None
    modifiers = attack_modifier_snapshots(
        state=state,
        pool=pool,
        source_phase=source_phase,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    selection = PsychicAttackModifierIgnoreSelection(
        "pending",
        pool.weapon_profile.skill.raw,
        pool.weapon_profile.skill.characteristic,
        modifiers,
        (),
        (),
    )
    if previous_selection is not None:
        if (
            previous_selection.modifiers != modifiers
            or previous_selection.skill_base != selection.skill_base
            or previous_selection.skill_characteristic != selection.skill_characteristic
        ):
            raise GameLifecycleError("Psychic modifier source snapshot drift.")
        selection = replace(previous_selection, option_id="pending")
    if not modifiers or selection.complete:
        return None
    context: dict[str, JsonValue] = {
        "submission_kind": DECISION_TYPE,
        "attack_context_id": attack_context_id,
        "attacking_unit_instance_id": attacking_unit_instance_id,
        "attacker_model_instance_id": pool.attacker_model_instance_id,
        "target_unit_instance_id": pool.target_unit_instance_id,
        "weapon_profile_id": pool.weapon_profile_id,
        "source_phase": source_phase.value,
        "pool_sha256": sha256(canonical_json(pool.to_payload()).encode()).hexdigest(),
        "effect_snapshot_sha256": sha256(
            canonical_json(
                validate_json_value(
                    [
                        effect.to_payload()
                        for effect in sorted(
                            state.persisting_effects, key=lambda effect: effect.effect_id
                        )
                    ]
                )
            ).encode()
        ).hexdigest(),
        "source_rule_ids": [PSYCHIC_MODIFIERS_SOURCE_ID, IGNORE_MODIFIERS_SOURCE_ID],
    }
    payload = {**context, **selection.to_payload()}
    return DecisionRequest(
        request_id=state.next_decision_request_id() if request_id is None else request_id,
        decision_type=DECISION_TYPE,
        actor_id=attacker_player_id,
        payload=payload,
        options=_psychic_attack_modifier_ignore_options(selection=selection, context=context),
    )


def _psychic_attack_modifier_ignore_options(
    *,
    selection: PsychicAttackModifierIgnoreSelection,
    context: dict[str, JsonValue],
) -> tuple[DecisionOption, ...]:
    ids = tuple(item.modifier_id for item in selection.modifiers)
    remaining = selection.modifiers[len(selection.decided_modifier_ids) :]
    if not remaining:
        raise GameLifecycleError("Psychic choice requires an undecided modifier.")
    current = remaining[0]
    suffix = sha256(canonical_json(current.to_payload()).encode()).hexdigest()[:24]
    characteristic_label = (
        "BS" if selection.skill_characteristic is Characteristic.BALLISTIC_SKILL else "WS"
    )
    modifier_label = (
        f"{characteristic_label if current.kind == 'skill' else 'hit roll'} "
        f"{current.modifier.operation.value} {current.modifier.operand:+d} "
        f"from {current.modifier.source_id}"
    )
    candidates = [
        ("keep-all-modifiers", "Keep all remaining modifiers", ids, ()),
        (
            "ignore-detrimental-modifiers",
            "Ignore detrimental remaining modifiers",
            ids,
            tuple(item.modifier_id for item in remaining if _is_detrimental(item)),
        ),
        (
            "ignore-beneficial-modifiers",
            "Ignore beneficial remaining modifiers",
            ids,
            tuple(item.modifier_id for item in remaining if _is_beneficial(item)),
        ),
        (
            "ignore-all-modifiers",
            "Ignore all remaining modifiers",
            ids,
            tuple(item.modifier_id for item in remaining),
        ),
        (
            f"keep-modifier:{suffix}",
            f"Keep {modifier_label}",
            (*selection.decided_modifier_ids, current.modifier_id),
            (),
        ),
        (
            f"ignore-modifier:{suffix}",
            f"Ignore {modifier_label}",
            (*selection.decided_modifier_ids, current.modifier_id),
            (current.modifier_id,),
        ),
    ]
    options: list[DecisionOption] = []
    seen: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
    for option_id, label, decided, ignored in candidates:
        ignored_ids = tuple(sorted((*selection.ignored_modifier_ids, *ignored)))
        identity = (decided, ignored_ids)
        if identity in seen:
            continue
        seen.add(identity)
        answer = replace(
            selection,
            option_id=option_id,
            decided_modifier_ids=decided,
            ignored_modifier_ids=ignored_ids,
        )
        options.append(
            DecisionOption(
                option_id=option_id,
                label=label,
                payload={**context, **answer.to_payload()},
            )
        )
    return tuple(sorted(options, key=lambda item: item.option_id))


def _is_detrimental(item: AttackModifierSnapshot) -> bool:
    return item.modifier.operation.value == "add" and _has_detrimental_psychic_modifier(
        skill_modifier=item.modifier.operand if item.kind == "skill" else 0,
        hit_roll_modifier=item.modifier.operand if item.kind == "hit_roll" else 0,
    )


def _is_beneficial(item: AttackModifierSnapshot) -> bool:
    return item.modifier.operation.value == "add" and _has_beneficial_psychic_modifier(
        skill_modifier=item.modifier.operand if item.kind == "skill" else 0,
        hit_roll_modifier=item.modifier.operand if item.kind == "hit_roll" else 0,
    )


def selection_from_payload(payload: JsonValue) -> PsychicAttackModifierIgnoreSelection:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Psychic selection payload must be an object.")
    try:
        raw_modifiers = payload["modifiers"]
        if not isinstance(raw_modifiers, list):
            raise GameLifecycleError("Psychic modifiers must be a list.")
        selection = PsychicAttackModifierIgnoreSelection(
            option_id=_string(payload, "option_id"),
            skill_base=cast(int, payload["skill_base"]),
            skill_characteristic=Characteristic(_string(payload, "skill_characteristic")),
            modifiers=tuple(AttackModifierSnapshot.from_payload(item) for item in raw_modifiers),
            decided_modifier_ids=_strings(payload, "decided_modifier_ids"),
            ignored_modifier_ids=_strings(payload, "ignored_modifier_ids"),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise GameLifecycleError("Psychic selection schema is invalid.") from exc
    if set(payload) not in (
        set(selection.to_payload()),
        set(selection.to_payload()) | _CONTEXT_KEYS,
    ):
        raise GameLifecycleError("Psychic selection fields drift.")
    if "submission_kind" in payload:
        if (
            payload["submission_kind"] != DECISION_TYPE
            or payload["source_rule_ids"]
            != [PSYCHIC_MODIFIERS_SOURCE_ID, IGNORE_MODIFIERS_SOURCE_ID]
            or payload["source_phase"] not in {BattlePhase.SHOOTING.value, BattlePhase.FIGHT.value}
        ):
            raise GameLifecycleError("Psychic selection source context drift.")
        for key in _CONTEXT_KEYS - {"source_rule_ids"}:
            _string(payload, key)
        for key in ("pool_sha256", "effect_snapshot_sha256"):
            digest = _string(payload, key)
            if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
                raise GameLifecycleError("Psychic selection source digest is invalid.")
    for key, value in selection.to_payload().items():
        if key not in payload or canonical_json(payload[key]) != canonical_json(value):
            raise GameLifecycleError("Psychic selection arithmetic or identity drift.")
    return selection


def _psychic_attack_modifier_ignore_selection_for_attack(
    *,
    decisions: DecisionController,
    attack_context_id: str,
) -> PsychicAttackModifierIgnoreSelection | None:
    previous: PsychicAttackModifierIgnoreSelection | None = None
    previous_context: dict[str, JsonValue] | None = None
    actor_id: str | None = None
    for record in decisions.records:
        if record.request.decision_type != DECISION_TYPE:
            continue
        payload = record.request.payload
        if not isinstance(payload, dict) or payload.get("attack_context_id") != attack_context_id:
            continue
        pending = selection_from_payload(payload)
        if previous is None:
            if pending.decided_modifier_ids:
                raise GameLifecycleError(
                    "Psychic selection history starts after its source cursor."
                )
        elif replace(previous, option_id="pending") != pending or previous.complete:
            raise GameLifecycleError("Psychic selection history or source snapshot drift.")
        context = {key: value for key, value in payload.items() if key not in pending.to_payload()}
        if frozenset(context) != _CONTEXT_KEYS or pending.option_id != "pending":
            raise GameLifecycleError("Psychic history requires closed pending context.")
        if previous_context is not None and (
            previous_context != context or actor_id != record.request.actor_id
        ):
            raise GameLifecycleError("Psychic history actor or attack context drift.")
        previous_context, actor_id = context, record.request.actor_id
        expected_options = _psychic_attack_modifier_ignore_options(
            selection=pending, context=context
        )
        if tuple(canonical_json(option.to_payload()) for option in expected_options) != tuple(
            canonical_json(option.to_payload()) for option in record.request.options
        ):
            raise GameLifecycleError("Psychic recorded options differ from source selections.")
        record.result.validate_for_request(record.request)
        previous = selection_from_payload(record.result.payload)
    return previous


def validate_psychic_attack_modifier_ignore_decision(
    *,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    result: DecisionResult,
) -> None:
    record = decisions.record_for_result(result)
    if record.request.decision_type != DECISION_TYPE:
        raise GameLifecycleError("Psychic modifier ignore decision has wrong request type.")
    payload = record.request.payload
    if (
        not isinstance(payload, dict)
        or payload.get("attack_context_id") != attack_sequence.attack_context_id()
    ):
        raise GameLifecycleError("Psychic modifier ignore decision attack context drift.")
    selection = _psychic_attack_modifier_ignore_selection_for_attack(
        decisions=decisions,
        attack_context_id=attack_sequence.attack_context_id(),
    )
    if selection is None or selection.option_id != result.selected_option_id:
        raise GameLifecycleError("Psychic modifier ignore decision option drift.")


def _string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload[key]
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"Psychic selection {key} requires an identifier.")
    return value


def _strings(payload: dict[str, JsonValue], key: str) -> tuple[str, ...]:
    value = payload[key]
    if not isinstance(value, list) or any(type(item) is not str for item in value):
        raise GameLifecycleError(f"Psychic selection {key} requires identifiers.")
    return tuple(cast(list[str], value))


def _has_detrimental_psychic_modifier(*, skill_modifier: int, hit_roll_modifier: int) -> bool:
    return skill_modifier > 0 or hit_roll_modifier < 0


def _has_beneficial_psychic_modifier(*, skill_modifier: int, hit_roll_modifier: int) -> bool:
    return skill_modifier < 0 or hit_roll_modifier > 0
