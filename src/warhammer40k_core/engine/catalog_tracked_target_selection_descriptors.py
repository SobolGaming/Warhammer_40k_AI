from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.engine.tracked_targets import TrackedTargetOwnerScope, TrackedTargetRole
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleEffectKind,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)

START_BATTLE_TRACKED_TARGET_SELECTION_TEMPLATE_ID = "phase17c:start-battle-tracked-target-selection"


@dataclass(frozen=True, slots=True)
class CatalogTrackedTargetSelectionDescriptor:
    owner_scope: TrackedTargetOwnerScope
    role: TrackedTargetRole
    target_allegiance: str
    target_scope: str
    replacement: bool


def clause_has_invalid_exact_tracked_target_selection_shape(clause: RuleClause) -> bool:
    return (
        clause.template_id == START_BATTLE_TRACKED_TARGET_SELECTION_TEMPLATE_ID
        and tracked_target_selection_descriptor_for_clause(clause) is None
    )


def tracked_target_selection_descriptor_for_clause(
    clause: RuleClause,
) -> CatalogTrackedTargetSelectionDescriptor | None:
    if (
        not clause.is_supported
        or clause.template_id != START_BATTLE_TRACKED_TARGET_SELECTION_TEMPLATE_ID
        or clause.trigger is None
        or clause.trigger.kind is not RuleTriggerKind.TIMING_WINDOW
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.ENEMY_UNIT
        or clause.target.parameters
        or clause.conditions
        or clause.duration is not None
        or len(clause.effects) != 1
    ):
        return None
    effect = clause.effects[0]
    if (
        parameter_payload(clause.trigger.parameters)
        != {
            "edge": "start",
            "owner": "controlling_player",
            "phase": "battle",
            "subject": "this_unit",
            "timing_window": "start_battle",
        }
        or effect.kind is not RuleEffectKind.SELECT_TRACKED_TARGET
        or parameter_payload(effect.parameters)
        != {
            "replacement": False,
            "selection_kind": "select_one",
            "target_allegiance": "enemy",
            "target_lifecycle": "until_destroyed",
            "target_scope": "enemy_unit",
            "tracked_target_owner": "this_unit",
            "tracked_target_role": "prey",
        }
    ):
        return None
    return CatalogTrackedTargetSelectionDescriptor(
        owner_scope=TrackedTargetOwnerScope.THIS_UNIT,
        role=TrackedTargetRole.PREY,
        target_allegiance="enemy",
        target_scope="enemy_unit",
        replacement=False,
    )
