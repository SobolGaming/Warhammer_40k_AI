from __future__ import annotations

import msgspec

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.rules.text_normalization import (
    TextNormalizationError,
    normalize_rule_text,
)

from ._artifacts import (
    JULY_FACTION_PACK_SOURCE_DATE,
    JULY_FACTION_PACK_SOURCE_PACKAGE_ID,
    JulyFactionPackStagingError,
)

JULY_DAEMONIC_MANIFESTATION_SCHEMA = "core-v2-july-chaos-daemons-daemonic-manifestation-v1"
JULY_CHAOS_DAEMONS_RUNTIME_SCHEMA = "core-v2-july-chaos-daemons-runtime-updates-v1"


class JulyDaemonicManifestationArtifact(msgspec.Struct, frozen=True):
    artifact_schema: str
    artifact_id: str
    source_package_id: str
    source_date: str
    source_pdf_package_id: str
    source_pdf_page: int
    source_row_id: str
    predecessor_source_rule_id: str
    rule_name: str
    raw_rule_text: str
    normalized_rule_text: str
    phase17e_descriptor_id: str
    phase17f_execution_id: str
    load_support_status: str
    semantic_execution_status: str
    runtime_consumer_ids: list[str]
    runtime_provider_id: str
    provider_activation_status: str
    named_handler_classification: str
    named_handler_budget_execution_id: str
    bespoke_subsystem_justification: str
    decision_types: list[str]
    adapter_contract_path: str

    def validate(self) -> None:
        if self.artifact_schema != JULY_DAEMONIC_MANIFESTATION_SCHEMA:
            raise JulyFactionPackStagingError(
                "July Daemonic Manifestation artifact schema is unsupported."
            )
        _validate_identifier("Daemonic Manifestation artifact_id", self.artifact_id)
        if self.source_package_id != JULY_FACTION_PACK_SOURCE_PACKAGE_ID:
            raise JulyFactionPackStagingError(
                "July Daemonic Manifestation belongs to the wrong source package."
            )
        if self.source_date != JULY_FACTION_PACK_SOURCE_DATE:
            raise JulyFactionPackStagingError("July Daemonic Manifestation source date is stale.")
        if self.source_pdf_package_id != "gw-11e-chaos-daemons-faction-pack-2026-07":
            raise JulyFactionPackStagingError(
                "July Daemonic Manifestation requires Chaos Daemons PDF evidence."
            )
        if self.source_pdf_page != 1:
            raise JulyFactionPackStagingError(
                "July Daemonic Manifestation source page is unexpected."
            )
        _validate_identifier("Daemonic Manifestation source_row_id", self.source_row_id)
        if not self.source_row_id.startswith(f"{JULY_FACTION_PACK_SOURCE_PACKAGE_ID}:"):
            raise JulyFactionPackStagingError(
                "July Daemonic Manifestation source row must be staged."
            )
        _validate_identifier(
            "Daemonic Manifestation predecessor_source_rule_id",
            self.predecessor_source_rule_id,
        )
        if self.rule_name != "Daemonic Manifestation":
            raise JulyFactionPackStagingError("July Daemonic Manifestation rule name drifted.")
        try:
            normalized = normalize_rule_text(self.raw_rule_text)
        except TextNormalizationError as exc:
            raise JulyFactionPackStagingError(
                "July Daemonic Manifestation source text is invalid."
            ) from exc
        if self.normalized_rule_text != normalized:
            raise JulyFactionPackStagingError(
                "July Daemonic Manifestation normalized text is stale."
            )
        _validate_identifier(
            "Daemonic Manifestation phase17e_descriptor_id",
            self.phase17e_descriptor_id,
        )
        _validate_identifier(
            "Daemonic Manifestation phase17f_execution_id",
            self.phase17f_execution_id,
        )
        if self.load_support_status != "loaded":
            raise JulyFactionPackStagingError("July Daemonic Manifestation must be load-supported.")
        if self.semantic_execution_status != "executable_named_handler":
            raise JulyFactionPackStagingError(
                "July Daemonic Manifestation execution status is incorrect."
            )
        _validate_exact_identifier_list(
            "Daemonic Manifestation runtime_consumer_ids",
            self.runtime_consumer_ids,
            expected=("warhammer_40000_11th:chaos_daemons:army_rule:shadow_of_chaos:july_2026",),
        )
        _validate_identifier(
            "Daemonic Manifestation runtime_provider_id",
            self.runtime_provider_id,
        )
        if self.provider_activation_status != "candidate_only":
            raise JulyFactionPackStagingError(
                "July Daemonic Manifestation provider must remain candidate-only."
            )
        if (
            self.named_handler_classification
            != "approved_successor_of_existing_army_rule_orchestrator"
        ):
            raise JulyFactionPackStagingError(
                "July Daemonic Manifestation named-handler classification is incorrect."
            )
        if self.named_handler_budget_execution_id != self.predecessor_source_rule_id:
            raise JulyFactionPackStagingError(
                "July Daemonic Manifestation must retain the predecessor handler budget entry."
            )
        if self.bespoke_subsystem_justification != (
            "Shadow of Chaos owns army-wide objective-region state and cross-player "
            "Battle-shock orchestration; its model-return sub-effect delegates to the "
            "generic typed healing and revival decision services."
        ):
            raise JulyFactionPackStagingError(
                "July Daemonic Manifestation bespoke-subsystem justification drifted."
            )
        _validate_exact_identifier_list(
            "Daemonic Manifestation decision_types",
            self.decision_types,
            expected=(
                "select_healing_model",
                "submit_healing_revival_placement",
            ),
        )
        if self.adapter_contract_path != "docs/ADAPTER_DECISION_CONTRACT.md":
            raise JulyFactionPackStagingError(
                "July Daemonic Manifestation adapter contract path is unexpected."
            )


def july_daemonic_manifestation_from_json_bytes(
    raw: bytes,
) -> JulyDaemonicManifestationArtifact:
    try:
        artifact = msgspec.json.decode(raw, type=JulyDaemonicManifestationArtifact)
    except msgspec.DecodeError as exc:
        raise JulyFactionPackStagingError(
            "July Daemonic Manifestation artifact is invalid."
        ) from exc
    artifact.validate()
    return artifact


class JulyChaosDaemonsRuntimeRow(msgspec.Struct, frozen=True):
    row_id: str
    row_kind: str
    source_row_id: str
    predecessor_source_row_id: str
    datasheet_id: str | None
    rule_name: str
    source_pdf_page: int
    raw_rule_text: str
    normalized_rule_text: str
    load_support_status: str
    semantic_execution_status: str
    runtime_consumer_ids: list[str]
    replacement_keywords: list[str]

    def validate(self) -> None:
        _validate_identifier("Chaos Daemons runtime row_id", self.row_id)
        if self.row_kind not in {
            "datasheet_ability",
            "keyword_overlay",
            "stratagem",
            "unsupported_datasheet_ability",
        }:
            raise JulyFactionPackStagingError("July Chaos Daemons runtime row kind is unsupported.")
        _validate_identifier("Chaos Daemons runtime source_row_id", self.source_row_id)
        if not self.source_row_id.startswith(f"{JULY_FACTION_PACK_SOURCE_PACKAGE_ID}:"):
            raise JulyFactionPackStagingError(
                "July Chaos Daemons runtime source row must be staged."
            )
        _validate_identifier(
            "Chaos Daemons runtime predecessor_source_row_id",
            self.predecessor_source_row_id,
        )
        if self.datasheet_id is not None:
            _validate_identifier("Chaos Daemons runtime datasheet_id", self.datasheet_id)
        if not self.rule_name.strip() or self.source_pdf_page <= 0:
            raise JulyFactionPackStagingError(
                "July Chaos Daemons runtime source identity is invalid."
            )
        try:
            normalized = normalize_rule_text(self.raw_rule_text)
        except TextNormalizationError as exc:
            raise JulyFactionPackStagingError(
                "July Chaos Daemons runtime source text is invalid."
            ) from exc
        if self.normalized_rule_text != normalized:
            raise JulyFactionPackStagingError(
                "July Chaos Daemons runtime normalized text is stale."
            )
        if self.load_support_status != "loaded":
            raise JulyFactionPackStagingError(
                "July Chaos Daemons runtime row must be load-supported."
            )
        if self.semantic_execution_status not in {
            "executable_generic_rule_ir",
            "executable_keyword_overlay",
            "unsupported",
        }:
            raise JulyFactionPackStagingError(
                "July Chaos Daemons runtime execution status is invalid."
            )
        for consumer_id in self.runtime_consumer_ids:
            _validate_identifier("Chaos Daemons runtime consumer_id", consumer_id)
        for keyword in self.replacement_keywords:
            _validate_identifier("Chaos Daemons replacement keyword", keyword)
        if self.row_kind == "keyword_overlay":
            if self.replacement_keywords != [
                "BEAST",
                "FLY",
                "CHAOS",
                "DAEMON",
                "TZEENTCH",
                "SCREAMERS",
            ]:
                raise JulyFactionPackStagingError("July Screamers replacement keywords drifted.")
        elif self.replacement_keywords:
            raise JulyFactionPackStagingError(
                "Only a keyword overlay can declare replacement keywords."
            )


class JulyChaosDaemonsRuntimeArtifact(msgspec.Struct, frozen=True):
    artifact_schema: str
    artifact_id: str
    source_package_id: str
    source_date: str
    source_pdf_package_id: str
    runtime_provider_id: str
    provider_activation_status: str
    ingress_decision_type: str
    stratagem_cost_decision_type: str
    adapter_contract_status: str
    rows: list[JulyChaosDaemonsRuntimeRow]

    def validate(self) -> None:
        if self.artifact_schema != JULY_CHAOS_DAEMONS_RUNTIME_SCHEMA:
            raise JulyFactionPackStagingError(
                "July Chaos Daemons runtime artifact schema is unsupported."
            )
        if self.artifact_id != "gw-11e-july-chaos-daemons-runtime-updates-2026-07":
            raise JulyFactionPackStagingError(
                "July Chaos Daemons runtime artifact identity drifted."
            )
        if (
            self.source_package_id != JULY_FACTION_PACK_SOURCE_PACKAGE_ID
            or self.source_date != JULY_FACTION_PACK_SOURCE_DATE
            or self.source_pdf_package_id != "gw-11e-chaos-daemons-faction-pack-2026-07"
        ):
            raise JulyFactionPackStagingError(
                "July Chaos Daemons runtime source identity is invalid."
            )
        if (
            self.runtime_provider_id
            != "warhammer_40000_11th:chaos_daemons:faction_manifest:july_2026_candidate"
            or self.provider_activation_status != "candidate_only"
        ):
            raise JulyFactionPackStagingError(
                "July Chaos Daemons runtime provider must remain candidate-only."
            )
        if (
            self.ingress_decision_type != "submit_placement_proposal"
            or self.stratagem_cost_decision_type != "select_stratagem_cost_modifier_option"
            or self.adapter_contract_status != "existing_contract_unchanged"
        ):
            raise JulyFactionPackStagingError(
                "July Chaos Daemons runtime decision contract drifted."
            )
        expected_rows = {
            "chaos-daemons:fluxmaster:altered-reality",
            "chaos-daemons:fluxmaster:fluxmaster",
            "chaos-daemons:kairos-fateweaver:one-head-looks-back",
            "chaos-daemons:screamers:keywords",
            "chaos-daemons:the-realm-of-chaos",
        }
        row_ids = {row.row_id for row in self.rows}
        if row_ids != expected_rows or len(row_ids) != len(self.rows):
            raise JulyFactionPackStagingError(
                "July Chaos Daemons runtime artifact row set drifted."
            )
        for row in self.rows:
            row.validate()


def july_chaos_daemons_runtime_from_json_bytes(
    raw: bytes,
) -> JulyChaosDaemonsRuntimeArtifact:
    try:
        artifact = msgspec.json.decode(raw, type=JulyChaosDaemonsRuntimeArtifact)
    except msgspec.DecodeError as exc:
        raise JulyFactionPackStagingError(
            "July Chaos Daemons runtime artifact is invalid."
        ) from exc
    artifact.validate()
    return artifact


def _validate_exact_identifier_list(
    field_name: str,
    value: list[str],
    *,
    expected: tuple[str, ...],
) -> None:
    if tuple(value) != expected:
        raise JulyFactionPackStagingError(
            f"July faction-pack {field_name} does not match the approved exact set."
        )
    for item in value:
        _validate_identifier(field_name, item)


_validate_identifier = IdentifierValidator(
    JulyFactionPackStagingError,
    pattern_message="July faction-pack {field_name} must be a stable identifier.",
)
