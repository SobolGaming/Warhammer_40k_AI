from __future__ import annotations

import hashlib

from warhammer40k_core.engine.catalog_selected_target_decisions import (
    SelectedTargetGroup,
    post_shoot_group_participant_id,
    post_shoot_group_stable_identity_payload,
)
from warhammer40k_core.engine.event_log import JsonValue, canonical_json
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.sequencing import SequencingParticipant, SequencingRequirement


def selected_target_group_participant(group: SelectedTargetGroup) -> SequencingParticipant:
    payload: dict[str, JsonValue]
    if group.attack_sequence is not None:
        payload = post_shoot_group_stable_identity_payload(group)
        participant_id = post_shoot_group_participant_id(group)
    else:
        if group.attack_sequence_completed_event_id is not None:
            raise GameLifecycleError("Phase-start group has unrelated attack-completion authority.")
        payload = {
            "catalog_record_id": group.record.record_id,
            "source_rule_id": group.record.definition.source_id,
            "source_unit_instance_id": group.unit.unit_instance_id,
            "source_model_instance_id": group.source_model_instance_id,
            "selection_clause_id": group.selection_clause.clause_id,
            "effect_clause_ids": [clause.clause_id for clause in group.effect_clauses],
            "phase": group.phase.value,
            "hook_id": group.hook_id,
        }
        digest = hashlib.sha256(canonical_json(payload).encode()).hexdigest()
        participant_id = f"catalog-phase-start-group:{digest}"
    return SequencingParticipant(
        participant_id=participant_id,
        player_id=group.player_id,
        source_rule_id=group.record.definition.source_id,
        requirement=SequencingRequirement.OPTIONAL
        if group.optional
        else SequencingRequirement.MANDATORY,
        payload=payload,
        label=group.record.definition.name,
    )
