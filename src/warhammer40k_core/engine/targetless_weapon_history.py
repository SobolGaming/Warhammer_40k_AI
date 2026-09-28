"""Authenticate targetless selections against accepted proposals and request inventories."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.attack_sequence_model import AttackSequencePayload
from warhammer40k_core.engine.attack_sequence_state import AttackSequence
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.targetless_weapon_validation import validate_targetless_weapon
from warhammer40k_core.engine.targetless_weapons import TargetlessWeapon, TargetlessWeaponPayload
from warhammer40k_core.engine.weapon_abilities import has_weapon_keyword
from warhammer40k_core.engine.weapon_declaration import (
    ShootingProposalValidationResult,
    shooting_declaration_proposal_from_json,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_record import DecisionRecord
    from warhammer40k_core.engine.game_state import GameState


def validate_targetless_weapon_history(
    *, state: GameState, events: tuple[EventRecord, ...], decisions: tuple[DecisionRecord, ...]
) -> None:
    records = {record.result.result_id: record for record in decisions}
    expected: dict[str, tuple[TargetlessWeapon, ...] | None] = {}
    sequences: list[AttackSequence] = []
    for event in events:
        if event.event_type == "attack_sequence_completion_state_recorded":
            if not isinstance(event.payload, dict):
                raise GameLifecycleError("Selected weapon completion requires an object.")
            sequences.append(
                AttackSequence.from_payload(cast(AttackSequencePayload, event.payload))
            )
        if event.event_type not in {
            "shooting_declaration_accepted",
            "out_of_phase_shooting_declaration_accepted",
        }:
            continue
        payload = event.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Selected weapon history requires an object.")
        result_id = payload.get("result_id")
        if not isinstance(result_id, str) or result_id not in records:
            raise GameLifecycleError("Selected weapons lack an accepted declaration.")
        record = records[result_id]
        proposal = shooting_declaration_proposal_from_json(record.result.payload)
        rows = payload.get("weapons_without_attacks", [])
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise GameLifecycleError("Selected weapon inventory is missing or malformed.")
        selections = tuple(
            TargetlessWeapon.from_payload(cast(TargetlessWeaponPayload, row)) for row in rows
        )
        if tuple(row.declaration for row in selections) != tuple(
            row for row in proposal.declarations if row.target_unit_instance_id is None
        ):
            raise GameLifecycleError("Selected weapon inventory differs from its accepted choice.")
        pools = payload.get("attack_pools")
        if not isinstance(pools, list):
            raise GameLifecycleError("Selected weapons require an explicit attack pool inventory.")
        for index, selected in enumerate(selections, start=len(pools) + 1):
            validation = validate_targetless_weapon(
                declaration=selected.declaration,
                weapon_profile=selected.source_profile,
                proposal=proposal,
                pending_request=record.request,
                selected_type=selected.declaration.shooting_type,
            )
            if isinstance(validation, ShootingProposalValidationResult):
                raise GameLifecycleError(
                    "Selected weapon source inventory differs from its request."
                )
            if has_weapon_keyword(selected.weapon_profile, WeaponKeyword.ONE_SHOT):
                matching = tuple(
                    row
                    for row in state.one_shot_weapon_use_records
                    if row.selection_id == f"{result_id}:one-shot-pool-{index:03d}"
                )
                if (
                    len(matching) != 1
                    or matching[0].weapon_instance_id != selected.weapon_instance_id
                    or matching[0].weapon_profile_id != selected.weapon_profile_id
                    or matching[0].model_instance_id
                    != (
                        selected.firing_deck_source_model_instance_id
                        or selected.attacker_model_instance_id
                    )
                ):
                    raise GameLifecycleError("Selected targetless One Shot expenditure drifted.")
        prefix = "out-of-phase-" if event.event_type.startswith("out_of_phase") else ""
        if not pools and "weapons_without_attacks" not in payload:
            raise GameLifecycleError("Empty shooting declaration lacks its selected inventory.")
        expected[f"{prefix}attack-sequence:{result_id}"] = (
            selections if "weapons_without_attacks" in payload else None
        )
    for owner in (state.shooting_phase_state, state.out_of_phase_shooting_state):
        if owner is not None:
            for sequence in (owner.attack_sequence, owner.pending_completed_attack_sequence):
                if sequence is not None:
                    sequences.append(sequence)
    from warhammer40k_core.engine.shooting_selection_completion import selection_completion_origin

    for sequence in sequences:
        origin = selection_completion_origin(events=events, sequence_id=sequence.sequence_id)
        if origin is not None:
            if sequence != origin[1]:
                raise GameLifecycleError("Automatic selection completion inventory drifted.")
        elif sequence.sequence_id in expected:
            if sequence.weapons_without_attacks != expected[sequence.sequence_id]:
                raise GameLifecycleError("Executor selected weapon inventory drifted.")
        elif sequence.weapons_without_attacks is not None:
            raise GameLifecycleError("Targetless executor inventory lacks declaration authority.")
