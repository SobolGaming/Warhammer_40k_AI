from __future__ import annotations

from typing import cast

import msgspec

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.rules.rule_ir import (
    RuleEffectKind,
    RuleIR,
    RuleIRError,
    RuleIRPayload,
    parameter_payload,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_execution_2026_27 import (
    Phase17FExecutionRecord,
    Phase17FExecutionRecordPayload,
    Phase17FExecutionStatus,
)
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
JULY_EXALTED_PATRON_SCHEMA = "core-v2-july-emperors-children-exalted-patron-v1"
JULY_THOUSAND_SONS_DEFILER_SCHEMA = "core-v2-july-thousand-sons-defiler-v1"


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
        if self.provider_activation_status != "current_default":
            raise JulyFactionPackStagingError(
                "July Daemonic Manifestation provider must be current."
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
            != "warhammer_40000_11th:chaos_daemons:faction_manifest:july_2026"
            or self.provider_activation_status != "current_default"
        ):
            raise JulyFactionPackStagingError(
                "July Chaos Daemons runtime provider must be current."
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


class JulyThousandSonsDefilerOverlayOperation(msgspec.Struct, frozen=True):
    op_id: str
    order_index: int
    operation_kind: str
    source_table: str
    source_row_id: str
    expected_preimage_hash: str
    reason: str
    fields: dict[str, str]


class JulyThousandSonsDefilerArtifact(msgspec.Struct, frozen=True):
    artifact_schema: str
    artifact_id: str
    audited_chaos_space_marines_datasheet_id: str
    source_package_id: str
    source_date: str
    source_pdf_package_id: str
    source_pdf_page: int
    datasheet_id: str
    source_rule_row_id: str
    source_ability_id: str
    source_rule_name: str
    removed_ability_id: str
    aligned_defiler_datasheet_ids: list[str]
    load_support_status: str
    semantic_execution_status: str
    old_rule_ir_semantics: str
    counteroffensive_stratagem_id: str
    counteroffensive_handler_id: str
    runtime_consumer_ids: list[str]
    runtime_provider_id: str
    provider_activation_status: str
    operations: list[JulyThousandSonsDefilerOverlayOperation]

    def validate(self) -> None:
        if (
            self.artifact_schema != JULY_THOUSAND_SONS_DEFILER_SCHEMA
            or self.artifact_id != "gw-11e-july-thousand-sons-defiler-2026-07"
        ):
            raise JulyFactionPackStagingError(
                "July Thousand Sons Defiler artifact identity drifted."
            )
        if (
            self.source_package_id != JULY_FACTION_PACK_SOURCE_PACKAGE_ID
            or self.source_date != JULY_FACTION_PACK_SOURCE_DATE
            or self.source_pdf_package_id != "gw-11e-thousand-sons-faction-pack-2026-07"
            or self.source_pdf_page != 7
        ):
            raise JulyFactionPackStagingError(
                "July Thousand Sons Defiler source identity is invalid."
            )
        if (
            self.datasheet_id != "000001030"
            or self.audited_chaos_space_marines_datasheet_id != "000000969"
            or self.source_rule_row_id != "000001030:4"
            or self.source_ability_id != "000001030:destroyer-of-futures"
            or self.source_rule_name != "Destroyer of Futures"
            or self.removed_ability_id != "000008338"
        ):
            raise JulyFactionPackStagingError("July Thousand Sons Defiler source rows drifted.")
        _validate_exact_identifier_list(
            "Thousand Sons aligned Defiler datasheet IDs",
            self.aligned_defiler_datasheet_ids,
            expected=("000001030", "000004207", "000004208", "000004209"),
        )
        if (
            self.load_support_status != "loaded"
            or self.semantic_execution_status != "executable_generic_runtime"
            or self.old_rule_ir_semantics != "removed_minimum_hit_threshold"
        ):
            raise JulyFactionPackStagingError(
                "July Thousand Sons Defiler support status is invalid."
            )
        if (
            self.counteroffensive_stratagem_id != "counteroffensive"
            or self.counteroffensive_handler_id != "core:counteroffensive"
        ):
            raise JulyFactionPackStagingError(
                "July Thousand Sons Defiler must retain core Counteroffensive."
            )
        _validate_exact_identifier_list(
            "Thousand Sons Defiler runtime consumer IDs",
            self.runtime_consumer_ids,
            expected=(
                "warhammer_40000_11th:thousand_sons:defiler:"
                "destroyer-of-futures:phase-use-exception",
                "warhammer_40000_11th:thousand_sons:defiler:"
                "destroyer-of-futures:counteroffensive-discount",
            ),
        )
        if (
            self.runtime_provider_id
            != "warhammer_40000_11th:thousand_sons:faction_manifest:july_2026"
            or self.provider_activation_status != "current_default"
        ):
            raise JulyFactionPackStagingError(
                "July Thousand Sons Defiler provider must be current."
            )
        self._validate_operations()

    def _validate_operations(self) -> None:
        expected = {
            "july-thousand-sons-defiler-remove-empty-keyword": (
                10,
                "supersede_row",
                "Datasheets_keywords",
                "000001030:blank-keyword:global:true:4079",
                "a131c8969fe780eefdb815c36fb247c299d9231321e0a90f2ad5ce06b524c978",
            ),
            "july-world-eaters-defiler-remove-empty-keyword": (
                20,
                "supersede_row",
                "Datasheets_keywords",
                "000004207:blank-keyword:global:true:15727",
                "e8c91f47e38689afa7b59c36721643fee719c36c9440f7cb96ba72f9951a67bc",
            ),
            "july-emperors-children-defiler-remove-empty-keyword": (
                30,
                "supersede_row",
                "Datasheets_keywords",
                "000004208:blank-keyword:global:true:15734",
                "bb0bd82976f6829978c930144924225dff06654ffae55fde2df78865d2dcde52",
            ),
            "july-death-guard-defiler-remove-empty-keyword": (
                40,
                "supersede_row",
                "Datasheets_keywords",
                "000004209:blank-keyword:global:true:15742",
                "fca69bb8584c336c3e97a9ca4cbb64dd1eb515ee48c871e7c3b5ee28aaefa342",
            ),
            "july-thousand-sons-defiler-remove-feel-no-pain": (
                50,
                "supersede_row",
                "Datasheets_abilities",
                "000001030:2",
                "ec4cc4309f022b6727d380d7cd123b6e0984d3c7e57d3e529084356abd5749ca",
            ),
            "july-thousand-sons-defiler-replace-destroyer-of-futures": (
                60,
                "update_row",
                "Datasheets_abilities",
                "000001030:4",
                "6a984fb7a66ef5b2deebc2aa7974ab7089435c3e573d309859cf0d764b8a47ce",
            ),
        }
        if len(self.operations) != len(expected):
            raise JulyFactionPackStagingError(
                "July Thousand Sons Defiler overlay operation set drifted."
            )
        seen_operation_ids: set[str] = set()
        for operation in self.operations:
            _validate_identifier("Thousand Sons Defiler overlay op_id", operation.op_id)
            if operation.op_id in seen_operation_ids:
                raise JulyFactionPackStagingError(
                    "July Thousand Sons Defiler overlay operation IDs must be unique."
                )
            seen_operation_ids.add(operation.op_id)
            actual = (
                operation.order_index,
                operation.operation_kind,
                operation.source_table,
                operation.source_row_id,
                operation.expected_preimage_hash,
            )
            if expected.get(operation.op_id) != actual:
                raise JulyFactionPackStagingError(
                    "July Thousand Sons Defiler overlay operation drifted."
                )
            if operation.operation_kind == "update_row":
                expected_description = (
                    "Once per phase, per unit: You can target this unit with the "
                    "Counteroffensive stratagem, regardless of any other uses of that "
                    "stratagem this phase. If you do: That use is -1 CP. That use does "
                    "not prevent any uses of that stratagem on other units this phase."
                )
                if operation.fields != {"description": expected_description}:
                    raise JulyFactionPackStagingError(
                        "July Destroyer of Futures replacement text drifted."
                    )
            elif operation.fields:
                raise JulyFactionPackStagingError(
                    "July Defiler supersede operations must not edit fields."
                )
        if seen_operation_ids != set(expected):
            raise JulyFactionPackStagingError(
                "July Thousand Sons Defiler overlay operation set drifted."
            )


def july_thousand_sons_defiler_from_json_bytes(
    raw: bytes,
) -> JulyThousandSonsDefilerArtifact:
    try:
        artifact = msgspec.json.decode(raw, type=JulyThousandSonsDefilerArtifact)
    except msgspec.DecodeError as exc:
        raise JulyFactionPackStagingError(
            "July Thousand Sons Defiler artifact is invalid."
        ) from exc
    artifact.validate()
    return artifact


class JulyExaltedPatronArtifact(msgspec.Struct, frozen=True):
    artifact_schema: str
    artifact_id: str
    source_package_id: str
    source_date: str
    source_pdf_package_id: str
    source_pdf_page: int
    source_row_id: str
    predecessor_source_row_id: str
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
    target_required_keywords: list[str]
    removed_ability_ids: list[str]
    rule_ir_payload: dict[str, object]
    execution_record_payload: dict[str, object]

    def validate(self) -> None:
        if self.artifact_schema != JULY_EXALTED_PATRON_SCHEMA:
            raise JulyFactionPackStagingError("July Exalted Patron artifact schema is unsupported.")
        if self.artifact_id != "gw-11e-july-emperors-children-exalted-patron-2026-07":
            raise JulyFactionPackStagingError("July Exalted Patron artifact identity drifted.")
        if (
            self.source_package_id != JULY_FACTION_PACK_SOURCE_PACKAGE_ID
            or self.source_date != JULY_FACTION_PACK_SOURCE_DATE
            or self.source_pdf_package_id != "gw-11e-emperors-children-faction-pack-2026-07"
            or self.source_pdf_page != 1
        ):
            raise JulyFactionPackStagingError("July Exalted Patron source identity is invalid.")
        if self.source_row_id != (
            f"{JULY_FACTION_PACK_SOURCE_PACKAGE_ID}:enhancement:"
            "emperors-children:court-of-the-phoenician:000010654003"
        ):
            raise JulyFactionPackStagingError("July Exalted Patron source row identity drifted.")
        if self.predecessor_source_row_id != (
            "enhancement:emperors-children:court-of-the-phoenician:000010654003"
        ):
            raise JulyFactionPackStagingError("July Exalted Patron predecessor source row drifted.")
        if self.rule_name != "Exalted Patron":
            raise JulyFactionPackStagingError("July Exalted Patron rule name drifted.")
        try:
            normalized_text = normalize_rule_text(self.raw_rule_text)
        except TextNormalizationError as exc:
            raise JulyFactionPackStagingError(
                "July Exalted Patron source text is invalid."
            ) from exc
        if self.normalized_rule_text != normalized_text:
            raise JulyFactionPackStagingError("July Exalted Patron normalized text is stale.")
        expected_descriptor_id = (
            "phase17e:enhancement:emperors-children:court-of-the-phoenician:000010654003"
        )
        if self.phase17e_descriptor_id != expected_descriptor_id:
            raise JulyFactionPackStagingError("July Exalted Patron descriptor identity drifted.")
        if self.phase17f_execution_id != f"phase17f:{expected_descriptor_id}":
            raise JulyFactionPackStagingError("July Exalted Patron execution identity drifted.")
        if (
            self.load_support_status != "loaded"
            or self.semantic_execution_status != "executable_generic_ir"
        ):
            raise JulyFactionPackStagingError("July Exalted Patron support status is invalid.")
        _validate_exact_identifier_list(
            "Exalted Patron runtime_consumer_ids",
            self.runtime_consumer_ids,
            expected=(
                "warhammer_40000_11th:generic-enhancement-effects",
                "warhammer_40000_11th:generic-rule-movement-modifier",
            ),
        )
        if (
            self.runtime_provider_id
            != "warhammer_40000_11th:emperors_children:faction_manifest:july_2026"
            or self.provider_activation_status != "current_default"
        ):
            raise JulyFactionPackStagingError("July Exalted Patron provider must be current.")
        _validate_exact_identifier_list(
            "Exalted Patron target_required_keywords",
            self.target_required_keywords,
            expected=("LORD EXULTANT",),
        )
        _validate_exact_identifier_list(
            "Exalted Patron removed_ability_ids",
            self.removed_ability_ids,
            expected=("may_attach_to_flawless_blades",),
        )
        rule_ir = self.rule_ir()
        if (
            rule_ir.source_id
            != f"{JULY_FACTION_PACK_SOURCE_PACKAGE_ID}:{expected_descriptor_id}:source-text"
            or rule_ir.normalized_text != self.normalized_rule_text
            or len(rule_ir.clauses) != 2
        ):
            raise JulyFactionPackStagingError("July Exalted Patron RuleIR identity drifted.")
        effect_kinds = tuple(effect.kind for clause in rule_ir.clauses for effect in clause.effects)
        if effect_kinds != (RuleEffectKind.MODIFY_MOVE_DISTANCE,):
            raise JulyFactionPackStagingError("July Exalted Patron RuleIR effects drifted.")
        move_parameters = parameter_payload(rule_ir.clauses[1].effects[0].parameters)
        if move_parameters != {"delta": 1}:
            raise JulyFactionPackStagingError("July Exalted Patron Move modifier drifted.")
        record = self.execution_record()
        if (
            record.execution_id != self.phase17f_execution_id
            or record.coverage_descriptor_id != self.phase17e_descriptor_id
            or record.execution_status is not Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR
            or record.rule_ir_hash != rule_ir.ir_hash()
            or record.source_pdf_package_id != self.source_pdf_package_id
            or self.source_row_id not in record.source_ids
            or record.runtime_consumer_ids != tuple(self.runtime_consumer_ids)
        ):
            raise JulyFactionPackStagingError(
                "July Exalted Patron execution record is inconsistent."
            )

    def rule_ir(self) -> RuleIR:
        try:
            return RuleIR.from_payload(cast(RuleIRPayload, self.rule_ir_payload))
        except (KeyError, RuleIRError, TypeError) as exc:
            raise JulyFactionPackStagingError("July Exalted Patron RuleIR is invalid.") from exc

    def execution_record(self) -> Phase17FExecutionRecord:
        try:
            return Phase17FExecutionRecord.from_payload(
                cast(Phase17FExecutionRecordPayload, self.execution_record_payload)
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise JulyFactionPackStagingError(
                "July Exalted Patron execution record is invalid."
            ) from exc


def july_exalted_patron_from_json_bytes(raw: bytes) -> JulyExaltedPatronArtifact:
    try:
        artifact = msgspec.json.decode(raw, type=JulyExaltedPatronArtifact)
    except msgspec.DecodeError as exc:
        raise JulyFactionPackStagingError("July Exalted Patron artifact is invalid.") from exc
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
