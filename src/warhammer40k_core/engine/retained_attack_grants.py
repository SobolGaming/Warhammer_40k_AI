"""Source-neutral retained-attack grants from catalog and persisting RuleIR."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.damage_allocation import DestructionReactionSource
from warhammer40k_core.engine.destruction_reaction_kind import DestructionReactionKind
from warhammer40k_core.engine.effects import GENERIC_RULE_EFFECT_KIND
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleEffectKind,
    RuleEffectSpec,
    RuleEffectSpecPayload,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.catalog_attack_context_rule_runtime import (
        CatalogDatasheetClauseSource,
    )
    from warhammer40k_core.engine.game_state import GameState

RETAINED_ATTACK_ABILITY = "retained_destruction_attack"
RETAINED_ATTACK_TEMPLATE_ID = "retained-attack:model-destruction-grant"
RETAINED_ATTACK_CONSUMER_ID = "catalog-ir:retained-destruction-attack-source"
_identifier = IdentifierValidator(GameLifecycleError)


@dataclass(frozen=True, slots=True)
class RetainedAttackGrant:
    reaction_kind: DestructionReactionKind
    trigger_roll_threshold: int
    requires_not_shot_or_fought_this_phase: bool
    shooting_hazardous_tests_automatically_pass: bool

    def source_payload(self) -> dict[str, JsonValue]:
        return {
            "trigger_roll_threshold": self.trigger_roll_threshold,
            "requires_not_shot_or_fought_this_phase": self.requires_not_shot_or_fought_this_phase,
            "shooting_hazardous_tests_automatically_pass": (
                self.shooting_hazardous_tests_automatically_pass
            ),
        }


def retained_attack_grant_for_effect(effect: RuleEffectSpec) -> RetainedAttackGrant | None:
    parameters = parameter_payload(effect.parameters)
    if (
        effect.kind is not RuleEffectKind.GRANT_ABILITY
        or parameters.get("ability") != RETAINED_ATTACK_ABILITY
    ):
        return None
    if set(parameters) != {
        "ability",
        "actions",
        "optional",
        "trigger_roll_threshold",
        "requires_not_shot_or_fought_this_phase",
        "shooting_hazardous_tests_automatically_pass",
    }:
        raise GameLifecycleError("Retained attack RuleIR grant parameters drift.")
    kinds: dict[tuple[str, ...], DestructionReactionKind] = {
        ("shoot",): DestructionReactionKind.SHOOT_ON_DEATH,
        ("fight",): DestructionReactionKind.FIGHT_ON_DEATH,
        ("shoot", "fight"): DestructionReactionKind.SHOOT_OR_FIGHT_ON_DEATH,
    }
    actions = parameters["actions"]
    if not isinstance(actions, tuple) or actions not in kinds:
        raise GameLifecycleError("Retained attack grant action combination is unsupported.")
    threshold = parameters["trigger_roll_threshold"]
    previous = parameters["requires_not_shot_or_fought_this_phase"]
    hazardous = parameters["shooting_hazardous_tests_automatically_pass"]
    if (
        parameters["optional"] is not True
        or type(threshold) is not int
        or not 2 <= threshold <= 6
        or type(previous) is not bool
        or type(hazardous) is not bool
        or (hazardous and "shoot" not in actions)
    ):
        raise GameLifecycleError("Retained attack grant permissions are invalid.")
    return RetainedAttackGrant(kinds[actions], threshold, previous, hazardous)


def retained_attack_descriptor_for_clause(clause: RuleClause) -> RetainedAttackGrant | None:
    if clause.template_id != RETAINED_ATTACK_TEMPLATE_ID:
        return None
    if (
        not clause.is_supported
        or clause.trigger is None
        or clause.trigger.kind is not RuleTriggerKind.MODEL_DESTROYED
        or parameter_payload(clause.trigger.parameters)
        != {
            "destroyed_target": "this_model",
            "timing_window": "after_attacking_unit_finished_attacks",
        }
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.THIS_MODEL
        or clause.target.parameters
        or clause.conditions
        or clause.duration is not None
        or len(clause.effects) != 1
    ):
        raise GameLifecycleError("Retained attack catalog clause shape is unsupported.")
    descriptor = retained_attack_grant_for_effect(clause.effects[0])
    if descriptor is None:
        raise GameLifecycleError("Retained attack catalog clause must grant retained attacks.")
    return descriptor


def static_retained_attack_source(
    *,
    source: CatalogDatasheetClauseSource,
    descriptor: RetainedAttackGrant,
    model_instance_id: str,
) -> DestructionReactionSource:
    return DestructionReactionSource(
        source_id=f"{source.rule_ir.source_id}:{source.clause.clause_id}:{model_instance_id}:retained-attack",
        source_rule_id=source.rule_ir.source_id,
        reaction_kind=descriptor.reaction_kind,
        payload={
            **descriptor.source_payload(),
            "catalog_record_id": source.record.record_id,
            "clause_id": source.clause.clause_id,
            "consumer_id": RETAINED_ATTACK_CONSUMER_ID,
            "rule_ir_hash": source.rule_ir.ir_hash(),
            "unit_instance_id": source.unit.unit_instance_id,
            "model_instance_id": model_instance_id,
        },
    )


def persisted_retained_attack_sources(
    *,
    state: GameState,
    model_instance_id: str,
) -> tuple[DestructionReactionSource, ...]:
    from warhammer40k_core.engine.rules_unit_effects import (
        rules_unit_effect_applications_from_inventory,
    )
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    owners = [
        unit
        for army in state.army_definitions
        for unit in army.units
        if model_instance_id in unit.own_model_ids()
    ]
    if len(owners) != 1:
        raise GameLifecycleError("Retained attack source query requires one physical model owner.")
    view = rules_unit_view_by_id(state=state, unit_instance_id=owners[0].unit_instance_id)
    result: list[DestructionReactionSource] = []
    applications = rules_unit_effect_applications_from_inventory(
        armies=tuple(state.army_definitions),
        effects=tuple(state.persisting_effects),
        rules_unit=view,
    )
    for application in applications:
        effect = application.effect
        payload = effect.effect_payload
        if not isinstance(payload, dict) or payload.get("effect_kind") != GENERIC_RULE_EFFECT_KIND:
            continue
        raw_effect = payload.get("effect")
        if not isinstance(raw_effect, dict):
            raise GameLifecycleError("Generic RuleIR persisted effect lacks its effect descriptor.")
        grant = retained_attack_grant_for_effect(
            RuleEffectSpec.from_payload(cast(RuleEffectSpecPayload, raw_effect))
        )
        if grant is None:
            continue
        if effect.owner_player_id != view.owner_player_id:
            raise GameLifecycleError(
                "Retained attack effect owner differs from its friendly target."
            )
        result.append(
            DestructionReactionSource(
                source_id=f"{effect.effect_id}:{model_instance_id}:retained-attack",
                source_rule_id=effect.source_rule_id,
                reaction_kind=grant.reaction_kind,
                payload={
                    **grant.source_payload(),
                    "rule_ir_hash": _identifier("rule_ir_hash", payload.get("rule_ir_hash")),
                    "clause_id": _identifier("clause_id", payload.get("clause_id")),
                    "requires_active_persisting_effect": {"effect_id": effect.effect_id},
                    "model_instance_id": model_instance_id,
                },
            )
        )
    return tuple(sorted(result, key=lambda source: source.source_id))


def destruction_reaction_sources_for_model(
    *, state: GameState, model_instance_id: str
) -> tuple[DestructionReactionSource, ...]:
    model_id = _identifier("model_instance_id", model_instance_id)
    sources = (
        *state.destruction_reaction_sources_by_model_id.get(model_id, ()),
        *persisted_retained_attack_sources(state=state, model_instance_id=model_id),
    )
    if len({source.source_id for source in sources}) != len(sources):
        raise GameLifecycleError("Retained attack source identity is duplicated.")
    return sources
