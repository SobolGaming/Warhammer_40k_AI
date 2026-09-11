from __future__ import annotations

from functools import partial

from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollSpec,
)
from warhammer40k_core.core.modified_dice import ModifiedRollResult, UnmodifiedRollResult
from warhammer40k_core.engine.attack_completion_sequencing import (
    resolve_attack_completion_candidates,
)
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
)
from warhammer40k_core.engine.catalog_selected_target_test_modifiers import (
    LEADERSHIP_TEST_ROLL_TYPE,
    selected_target_test_roll_modifiers,
)
from warhammer40k_core.engine.damage_allocation import (
    MortalWoundApplicationProgress,
    continue_mortal_wound_application,
)
from warhammer40k_core.engine.destruction_provenance import DestructionSourceKind
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
    MortalWoundDestructionEvidence,
)
from warhammer40k_core.engine.phase import (
    GameLifecycleError,
    LifecycleStatus,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.sequencing import SequencingParticipant, SequencingRequirement
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate

from . import army_rule as _rules


def candidates(context: AttackSequenceCompletedContext) -> tuple[TimingRuleCandidate, ...]:
    effect = _rules.active_dark_pact_effect_for_unit(
        context.state,
        unit_instance_id=context.attack_sequence.attacking_unit_instance_id,
        phase=context.source_phase,
    )
    if effect is None or _rules.dark_pact_already_resolved(
        context=context, effect_id=effect.effect_id
    ):
        return ()
    return (
        TimingRuleCandidate(
            participant=SequencingParticipant(
                participant_id=f"dark-pact-completion:{effect.effect_id}",
                player_id=effect.owner_player_id,
                source_rule_id=effect.source_rule_id,
                requirement=SequencingRequirement.MANDATORY,
                payload={"effect_id": effect.effect_id},
            ),
            activate=partial(_activate, context),
        ),
    )


def resolve(context: AttackSequenceCompletedContext) -> LifecycleStatus | None:
    return resolve_attack_completion_candidates(context, partial(candidates, context))


def _activate(context: AttackSequenceCompletedContext) -> LifecycleStatus | None:
    if type(context) is not AttackSequenceCompletedContext:
        raise GameLifecycleError("Dark Pacts completion hook requires context.")
    effect = _rules.active_dark_pact_effect_for_unit(
        context.state,
        unit_instance_id=context.attack_sequence.attacking_unit_instance_id,
        phase=context.source_phase,
    )
    if effect is None:
        return None
    if _rules.dark_pact_already_resolved(context=context, effect_id=effect.effect_id):
        return None
    rules_unit = rules_unit_view_by_id(
        state=context.state, unit_instance_id=context.attack_sequence.attacking_unit_instance_id
    )
    payload = _rules.dark_pact_payload(effect.effect_payload)
    selected_pact = _rules.dark_pact_kind_from_token(payload["selected_dark_pact"])
    leadership_target = _rules.leadership_target_for_rules_unit(
        context=context, rules_unit=rules_unit
    )
    if _rules.dark_pact_leadership_auto_passes(payload):
        context.decisions.event_log.append(
            "chaos_space_marines_dark_pact_resolved",
            _rules.dark_pact_resolution_payload(
                context=context,
                rules_unit=rules_unit,
                effect=effect,
                selected_pact=selected_pact,
                leadership_target=leadership_target,
                leadership_roll=None,
                leadership_modified_roll=None,
                passed=True,
                d3_result=None,
                mortal_wound_application=None,
                leadership_auto_pass=True,
            ),
        )
        return None
    leadership_roll = context.dice_manager.roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=2, sides=6),
            reason=f"Dark Pact Leadership test for {rules_unit.unit_instance_id}",
            roll_type=_rules.DARK_PACT_LEADERSHIP_ROLL_TYPE,
            actor_id=rules_unit.unit_instance_id,
        )
    )
    modified_leadership_roll = ModifiedRollResult.from_unmodified(
        UnmodifiedRollResult.from_state(leadership_roll),
        modifiers=selected_target_test_roll_modifiers(
            state=context.state,
            unit_instance_id=rules_unit.unit_instance_id,
            roll_type=LEADERSHIP_TEST_ROLL_TYPE,
        ),
    )
    passed = modified_leadership_roll.final_value >= leadership_target
    if passed:
        context.decisions.event_log.append(
            "chaos_space_marines_dark_pact_resolved",
            _rules.dark_pact_resolution_payload(
                context=context,
                rules_unit=rules_unit,
                effect=effect,
                selected_pact=selected_pact,
                leadership_target=leadership_target,
                leadership_roll=validate_json_value(leadership_roll.to_payload()),
                leadership_modified_roll=validate_json_value(modified_leadership_roll.to_payload()),
                passed=True,
                d3_result=None,
                mortal_wound_application=None,
                leadership_auto_pass=False,
            ),
        )
        return None
    d3_result = context.dice_manager.roll_d3(
        reason=f"Dark Pact mortal wounds for {rules_unit.unit_instance_id}",
        roll_type=_rules.DARK_PACT_MORTAL_WOUNDS_ROLL_TYPE,
        actor_id=rules_unit.unit_instance_id,
    )
    base_payload = _rules.dark_pact_resolution_payload(
        context=context,
        rules_unit=rules_unit,
        effect=effect,
        selected_pact=selected_pact,
        leadership_target=leadership_target,
        leadership_roll=validate_json_value(leadership_roll.to_payload()),
        leadership_modified_roll=validate_json_value(modified_leadership_roll.to_payload()),
        passed=False,
        d3_result=validate_json_value(d3_result.to_payload()),
        mortal_wound_application=None,
        leadership_auto_pass=False,
    )
    progress = MortalWoundApplicationProgress.start(
        application_id=f"{context.attack_sequence.sequence_id}:dark-pacts:{effect.effect_id}:mortal-wounds",
        source_rule_id=effect.source_rule_id,
        source_context=_rules.dark_pact_mortal_wound_source_context(
            resolution_payload=base_payload, source_rule_id=effect.source_rule_id
        ),
        target_unit_instance_id=rules_unit.unit_instance_id,
        defender_player_id=rules_unit.owner_player_id,
        mortal_wounds=d3_result.value,
        spill_over=True,
        destruction_evidence=MortalWoundDestructionEvidence.for_non_attack_state(
            state=context.state,
            destroying_player_id=rules_unit.owner_player_id,
            source_rules_unit_instance_id=rules_unit.unit_instance_id,
            source_model_instance_id=None,
            destruction_source_kind=DestructionSourceKind.ABILITY,
            action_phase=context.source_phase,
            source_step="dark_pacts_mortal_wounds",
        ),
    )
    routed = continue_mortal_wound_application(
        state=context.state,
        decisions=context.decisions,
        dice_manager=context.dice_manager,
        request_id=context.state.next_decision_request_id(),
        progress=progress,
    )
    return _rules.resolve_routed_dark_pact_mortal_wounds(
        state=context.state,
        decisions=context.decisions,
        feel_no_pain_result_id=None,
        routed_request=routed.request,
        routed_application=routed.application,
        routed_progress=routed.progress,
        source_phase=context.source_phase,
    )
