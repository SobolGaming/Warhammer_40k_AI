"""Bind source model labels to existing materialization and replacement IDs."""

from warhammer40k_core.rules.rule_ir import RuleEffectKind, RuleIR, parameter_payload
from warhammer40k_core.rules.wahapedia_schema import NormalizedSourceRow
from warhammer40k_core.rules.wahapedia_static_rule_ir import payload_by_source_row_id


def materialization_keyword_profiles(
    rows: tuple[NormalizedSourceRow, ...], *, datasheet_id: str, error_type: type[ValueError]
) -> tuple[tuple[str, str, str], ...]:
    names: dict[str, str] = {}
    profiles: set[tuple[str, str]] = set()
    for row in rows:
        payload = payload_by_source_row_id(row.source_row_id)
        if payload is None:
            continue
        for clause in RuleIR.from_payload(payload).clauses:
            for effect in clause.effects:
                values = parameter_payload(effect.parameters)
                if effect.kind is RuleEffectKind.MATERIALIZE_MODELS:
                    name = values.get("result_model_name")
                    profile = values.get("result_model_profile_id")
                    descriptor = values.get("result_materialization_descriptor_id")
                    if (
                        type(name) is not str
                        or type(profile) is not str
                        or type(descriptor) is not str
                    ):
                        raise error_type("Materialization keyword identity must be strings.")
                    if descriptor in names and names[descriptor] != name:
                        raise error_type("Materialization keyword model label drifted.")
                    names[descriptor] = name
                    if profile.startswith(f"{datasheet_id}:"):
                        profiles.add((profile, descriptor))
                elif effect.kind is RuleEffectKind.REPLACE_UNIT_DATASHEET:
                    if values.get("replacement_datasheet_id") != datasheet_id:
                        continue
                    profile = values.get("replacement_model_profile_id")
                    count = values.get("replacement_model_variant_count")
                    if type(profile) is not str or type(count) is not int or count < 1:
                        raise error_type("Replacement keyword model variants are invalid.")
                    for index in range(1, count + 1):
                        descriptor = values.get(
                            f"replacement_model_variant_{index}_materialization_descriptor_id"
                        )
                        if type(descriptor) is not str:
                            raise error_type("Replacement keyword materialization ID is invalid.")
                        profiles.add((profile, descriptor))
    if any(descriptor not in names for _, descriptor in profiles):
        raise error_type("Replacement keyword variant lacks its source model label.")
    return tuple(
        (names[descriptor], profile, descriptor) for profile, descriptor in sorted(profiles)
    )
