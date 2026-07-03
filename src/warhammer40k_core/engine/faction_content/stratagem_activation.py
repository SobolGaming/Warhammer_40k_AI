from __future__ import annotations

from functools import cache

from warhammer40k_core.core.ruleset_descriptor import battle_phase_kind_from_token
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.stratagems import (
    GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
    StratagemAvailabilityKind,
    StratagemCatalogRecord,
    StratagemCategory,
    StratagemDefinition,
    StratagemRestrictionPolicy,
    StratagemTargetKind,
    StratagemTargetSpec,
    StratagemTimingDescriptor,
)
from warhammer40k_core.engine.timing_windows import timing_trigger_kind_from_token
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_stratagem_activation_2026_27,
)

__all__ = (
    "source_backed_detachment_stratagem_activation_records",
    "source_backed_stratagem_activation_source_package_id",
)

SourceStratagemActivationProfile = (
    faction_stratagem_activation_2026_27.SourceStratagemActivationProfile
)


def source_backed_stratagem_activation_source_package_id() -> str:
    return faction_stratagem_activation_2026_27.SOURCE_PACKAGE_ID


@cache
def source_backed_detachment_stratagem_activation_records() -> tuple[StratagemCatalogRecord, ...]:
    return tuple(
        record
        for profile in faction_stratagem_activation_2026_27.stratagem_activation_profiles()
        for record in _records_for_profile(profile)
    )


def _records_for_profile(
    profile: SourceStratagemActivationProfile,
) -> tuple[StratagemCatalogRecord, ...]:
    if type(profile) is not SourceStratagemActivationProfile:
        raise GameLifecycleError("Stratagem activation record requires a source profile.")
    if not profile.phase_tokens:
        raise GameLifecycleError("Stratagem activation profile must declare phases.")
    return tuple(
        _record_for_phase(profile=profile, phase_token=phase) for phase in profile.phase_tokens
    )


def _record_for_phase(
    *,
    profile: SourceStratagemActivationProfile,
    phase_token: str,
) -> StratagemCatalogRecord:
    phase = None if phase_token == "any" else battle_phase_kind_from_token(phase_token)
    phase_suffix = "any" if phase is None else phase.value
    return StratagemCatalogRecord(
        record_id=(
            f"{faction_stratagem_activation_2026_27.SOURCE_PACKAGE_ID}:"
            f"{profile.profile_id}:phase:{phase_suffix}"
        ),
        definition=StratagemDefinition(
            stratagem_id=profile.stratagem_id,
            name=profile.name,
            source_id=profile.source_id,
            command_point_cost=profile.command_point_cost,
            category=StratagemCategory(profile.category),
            when_descriptor=profile.when_descriptor,
            target_descriptor=profile.target_descriptor,
            effect_descriptor=profile.effect_descriptor,
            restrictions_descriptor=profile.restrictions_descriptor,
            timing=StratagemTimingDescriptor(
                trigger_kind=timing_trigger_kind_from_token(profile.trigger_kind),
                phase=phase,
            ),
            restriction_policy=StratagemRestrictionPolicy(
                same_unit_target_per_phase=True,
            ),
            target_spec=StratagemTargetSpec(
                target_kind=StratagemTargetKind(profile.target_kind),
                enumerable=True,
                target_policy_id=profile.target_policy_id,
                required_keywords=profile.required_keywords,
                required_keywords_any=profile.required_keywords_any,
                required_faction_keywords=profile.required_faction_keywords,
                excluded_keywords=profile.excluded_keywords,
                excluded_faction_keywords=profile.excluded_faction_keywords,
            ),
            handler_id=GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
            effect_payload=validate_json_value(profile.effect_payload()),
        ),
        availability_kind=StratagemAvailabilityKind.DETACHMENT,
        detachment_id=profile.detachment_id,
        disabled=False,
    )
