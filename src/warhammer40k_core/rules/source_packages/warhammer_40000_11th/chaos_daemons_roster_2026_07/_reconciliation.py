from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Final, TypedDict, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.rules.data_package import DataPackageId


class ChaosDaemonsRosterReconciliationError(ValueError):
    """Raised when the exact-roster official-PDF reconciliation is invalid."""


class _OfficialPdfPayload(TypedDict):
    source_package_id: str
    local_pdf: str
    sha256: str


class _GeneratorInputsPayload(TypedDict):
    artifact_hashes: dict[str, str]


class _DatasheetReviewPayload(TypedDict):
    datasheet_id: str
    name: str
    page_start: int
    page_end: int
    official_source_id: str
    reviewed_field_families: list[str]
    generator_input_payload_hash: str
    catalog_gameplay_hash: str
    expected_keywords: list[str]
    expected_faction_keywords: list[str]
    expected_damaged_wounds_max: int | None


class _ReconciliationPayload(TypedDict):
    schema_version: str
    package_id: str
    official_pdf: _OfficialPdfPayload
    generator_inputs: _GeneratorInputsPayload
    datasheets: list[_DatasheetReviewPayload]
    artifact_hash: str


SCHEMA_VERSION: Final = "chaos-daemons-exact-roster-pdf-reconciliation-v2"
PACKAGE_ID: Final = "data-package:core-v2:chaos-daemons-exact-roster-pdf-reconciliation:2026-07"
OFFICIAL_SOURCE_PACKAGE_ID: Final = "gw-11e-chaos-daemons-faction-pack-2026-07"
OFFICIAL_LOCAL_PDF: Final = (
    "data/raw/faction_packs/"
    "eng_22-07_warhammer_40,000_faction_pack_chaos_daemons-lycqqrymwe-qogh4b5yly.pdf"
)
OFFICIAL_PDF_SHA256: Final = "818f7ef144691b9eef6b3c5b5d0a39793690af5a958037b7055215e6675e6a2c"
REVIEWED_SOURCE_PACKAGE_ID: Final = DataPackageId(
    namespace="core-v2",
    package_name="chaos-daemons-exact-roster-official-review",
    version="2026-07",
)
REVIEWED_FIELD_FAMILIES: Final = (
    "abilities",
    "composition",
    "damaged_profile",
    "datasheet_keywords",
    "faction_keywords",
    "model_characteristics",
    "mustering_options",
    "wargear_options",
    "weapon_profiles",
)
EXPECTED_REVIEW_ROWS: Final = {
    "000001115": (
        "Bloodcrushers",
        30,
        31,
        ("BLOODCRUSHERS", "CHAOS", "DAEMON", "KHORNE", "MOUNTED"),
        ("LEGIONES DAEMONICA",),
        None,
    ),
    "000001120": (
        "Lord of Change",
        40,
        41,
        (
            "CHAOS",
            "CHARACTER",
            "DAEMON",
            "FLY",
            "LORD OF CHANGE",
            "MONSTER",
            "PSYKER",
            "TZEENTCH",
        ),
        ("LEGIONES DAEMONICA",),
        7,
    ),
    "000001132": (
        "Plaguebearers",
        78,
        79,
        ("BATTLELINE", "CHAOS", "DAEMON", "INFANTRY", "NURGLE", "PLAGUEBEARERS"),
        ("LEGIONES DAEMONICA",),
        None,
    ),
    "000001148": (
        "Be'lakor",
        112,
        113,
        (
            "BE'LAKOR",
            "CHAOS",
            "CHARACTER",
            "DAEMON",
            "EPIC HERO",
            "FLY",
            "MONSTER",
            "PSYKER",
        ),
        ("LEGIONES DAEMONICA",),
        7,
    ),
    "000002582": (
        "Bloodthirster",
        16,
        17,
        (
            "BLOODTHIRSTER",
            "CHAOS",
            "CHARACTER",
            "DAEMON",
            "FLY",
            "KHORNE",
            "MONSTER",
        ),
        ("LEGIONES DAEMONICA",),
        6,
    ),
}

_validate_identifier = IdentifierValidator(ChaosDaemonsRosterReconciliationError)
_PROVENANCE_KEYS: Final = frozenset(
    {
        "source_id",
        "source_ids",
        "source_span",
    }
)


@dataclass(frozen=True, slots=True)
class OfficialPdfSource:
    source_package_id: str
    local_pdf: str
    sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_package_id",
            _validate_identifier("Official PDF source_package_id", self.source_package_id),
        )
        object.__setattr__(
            self,
            "local_pdf",
            _validate_identifier("Official PDF local_pdf", self.local_pdf),
        )
        object.__setattr__(self, "sha256", _validate_sha256("Official PDF sha256", self.sha256))

    def to_payload(self) -> _OfficialPdfPayload:
        return {
            "source_package_id": self.source_package_id,
            "local_pdf": self.local_pdf,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class GeneratorInputProvenance:
    artifact_hashes: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if type(self.artifact_hashes) is not tuple or not self.artifact_hashes:
            raise ChaosDaemonsRosterReconciliationError(
                "Generator input artifact_hashes must be a non-empty tuple."
            )
        seen: set[str] = set()
        validated: list[tuple[str, str]] = []
        for table_name, artifact_hash in self.artifact_hashes:
            table = _validate_identifier("Generator input artifact table", table_name)
            if table in seen:
                raise ChaosDaemonsRosterReconciliationError(
                    "Generator input artifact_hashes must not duplicate tables."
                )
            seen.add(table)
            validated.append(
                (table, _validate_sha256("Generator input artifact hash", artifact_hash))
            )
        object.__setattr__(self, "artifact_hashes", tuple(sorted(validated)))

    def to_payload(self) -> _GeneratorInputsPayload:
        return {"artifact_hashes": dict(self.artifact_hashes)}


@dataclass(frozen=True, slots=True)
class DatasheetReview:
    datasheet_id: str
    name: str
    page_start: int
    page_end: int
    official_source_id: str
    reviewed_field_families: tuple[str, ...]
    generator_input_payload_hash: str
    catalog_gameplay_hash: str
    expected_keywords: tuple[str, ...]
    expected_faction_keywords: tuple[str, ...]
    expected_damaged_wounds_max: int | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "datasheet_id",
            _validate_identifier("Datasheet review datasheet_id", self.datasheet_id),
        )
        object.__setattr__(self, "name", _validate_identifier("Datasheet review name", self.name))
        if type(self.page_start) is not int or type(self.page_end) is not int:
            raise ChaosDaemonsRosterReconciliationError(
                "Datasheet review page references must be integers."
            )
        if self.page_start <= 0 or self.page_end < self.page_start:
            raise ChaosDaemonsRosterReconciliationError(
                "Datasheet review page references are invalid."
            )
        object.__setattr__(
            self,
            "official_source_id",
            _validate_identifier("Datasheet review official_source_id", self.official_source_id),
        )
        object.__setattr__(
            self,
            "reviewed_field_families",
            _validate_identifier_tuple(
                "Datasheet review reviewed_field_families",
                self.reviewed_field_families,
            ),
        )
        object.__setattr__(
            self,
            "generator_input_payload_hash",
            _validate_sha256(
                "Datasheet review generator_input_payload_hash",
                self.generator_input_payload_hash,
            ),
        )
        object.__setattr__(
            self,
            "catalog_gameplay_hash",
            _validate_sha256(
                "Datasheet review catalog_gameplay_hash",
                self.catalog_gameplay_hash,
            ),
        )
        object.__setattr__(
            self,
            "expected_keywords",
            _validate_identifier_tuple(
                "Datasheet review expected_keywords",
                self.expected_keywords,
            ),
        )
        object.__setattr__(
            self,
            "expected_faction_keywords",
            _validate_identifier_tuple(
                "Datasheet review expected_faction_keywords",
                self.expected_faction_keywords,
            ),
        )
        if self.expected_damaged_wounds_max is not None and (
            type(self.expected_damaged_wounds_max) is not int
            or self.expected_damaged_wounds_max <= 0
        ):
            raise ChaosDaemonsRosterReconciliationError(
                "Datasheet review expected_damaged_wounds_max must be positive or null."
            )

    def to_payload(self) -> _DatasheetReviewPayload:
        return {
            "datasheet_id": self.datasheet_id,
            "name": self.name,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "official_source_id": self.official_source_id,
            "reviewed_field_families": list(self.reviewed_field_families),
            "generator_input_payload_hash": self.generator_input_payload_hash,
            "catalog_gameplay_hash": self.catalog_gameplay_hash,
            "expected_keywords": list(self.expected_keywords),
            "expected_faction_keywords": list(self.expected_faction_keywords),
            "expected_damaged_wounds_max": self.expected_damaged_wounds_max,
        }


@dataclass(frozen=True, slots=True)
class ExactRosterReconciliation:
    package_id: str
    official_pdf: OfficialPdfSource
    generator_inputs: GeneratorInputProvenance
    datasheets: tuple[DatasheetReview, ...]
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "package_id",
            _validate_identifier("Reconciliation package_id", self.package_id),
        )
        if type(self.official_pdf) is not OfficialPdfSource:
            raise ChaosDaemonsRosterReconciliationError(
                "Reconciliation official_pdf must be OfficialPdfSource."
            )
        if type(self.generator_inputs) is not GeneratorInputProvenance:
            raise ChaosDaemonsRosterReconciliationError(
                "Reconciliation generator_inputs must be GeneratorInputProvenance."
            )
        if type(self.datasheets) is not tuple:
            raise ChaosDaemonsRosterReconciliationError(
                "Reconciliation datasheets must be a tuple."
            )
        if any(type(row) is not DatasheetReview for row in self.datasheets):
            raise ChaosDaemonsRosterReconciliationError(
                "Reconciliation datasheets must contain DatasheetReview values."
            )
        ids = tuple(row.datasheet_id for row in self.datasheets)
        if len(ids) != len(set(ids)):
            raise ChaosDaemonsRosterReconciliationError(
                "Reconciliation datasheets must not duplicate IDs."
            )
        object.__setattr__(
            self, "datasheets", tuple(sorted(self.datasheets, key=lambda row: row.datasheet_id))
        )
        object.__setattr__(
            self,
            "schema_version",
            _validate_identifier("Reconciliation schema_version", self.schema_version),
        )
        _validate_fixed_identity(self)

    def artifact_hash(self) -> str:
        return _sha256_json(self._payload_without_hash())

    def to_payload(self) -> _ReconciliationPayload:
        payload = self._payload_without_hash()
        payload["artifact_hash"] = self.artifact_hash()
        return payload

    def _payload_without_hash(self) -> _ReconciliationPayload:
        return {
            "schema_version": self.schema_version,
            "package_id": self.package_id,
            "official_pdf": self.official_pdf.to_payload(),
            "generator_inputs": self.generator_inputs.to_payload(),
            "datasheets": [row.to_payload() for row in self.datasheets],
            "artifact_hash": "",
        }

    def review_for_datasheet(self, datasheet_id: str) -> DatasheetReview:
        requested_id = _validate_identifier("datasheet_id", datasheet_id)
        for row in self.datasheets:
            if row.datasheet_id == requested_id:
                return row
        raise ChaosDaemonsRosterReconciliationError(
            "Reconciliation datasheet review was not found."
        )


def reconciliation_from_json_bytes(raw: bytes) -> ExactRosterReconciliation:
    if type(raw) is not bytes:
        raise ChaosDaemonsRosterReconciliationError("Reconciliation artifact input must be bytes.")
    try:
        decoded: object = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ChaosDaemonsRosterReconciliationError(
            "Reconciliation artifact is not valid JSON."
        ) from exc
    if not isinstance(decoded, dict):
        raise ChaosDaemonsRosterReconciliationError(
            "Reconciliation artifact must be a JSON object."
        )
    payload = cast(dict[str, object], decoded)
    _require_exact_keys(
        payload,
        {
            "schema_version",
            "package_id",
            "official_pdf",
            "generator_inputs",
            "datasheets",
            "artifact_hash",
        },
        "Reconciliation artifact",
    )
    official_payload = _required_mapping(payload, "official_pdf")
    _require_exact_keys(
        official_payload,
        {"source_package_id", "local_pdf", "sha256"},
        "Reconciliation official_pdf",
    )
    generator_inputs_payload = _required_mapping(payload, "generator_inputs")
    _require_exact_keys(
        generator_inputs_payload,
        {"artifact_hashes"},
        "Reconciliation generator_inputs",
    )
    artifact_hash_payload = _required_mapping(generator_inputs_payload, "artifact_hashes")
    if any(
        type(table_name) is not str or type(artifact_hash) is not str
        for table_name, artifact_hash in artifact_hash_payload.items()
    ):
        raise ChaosDaemonsRosterReconciliationError(
            "Reconciliation generator input artifact_hashes must map strings to strings."
        )
    validated_artifact_hashes = cast(dict[str, str], artifact_hash_payload)
    datasheet_payloads_value = payload["datasheets"]
    if not isinstance(datasheet_payloads_value, list):
        raise ChaosDaemonsRosterReconciliationError(
            "Reconciliation datasheets must be a JSON array."
        )
    datasheet_payloads = cast(list[object], datasheet_payloads_value)
    datasheets: list[DatasheetReview] = []
    for value in datasheet_payloads:
        if not isinstance(value, dict):
            raise ChaosDaemonsRosterReconciliationError(
                "Reconciliation datasheet rows must be JSON objects."
            )
        row = cast(dict[str, object], value)
        _require_exact_keys(
            row,
            {
                "datasheet_id",
                "name",
                "page_start",
                "page_end",
                "official_source_id",
                "reviewed_field_families",
                "generator_input_payload_hash",
                "catalog_gameplay_hash",
                "expected_keywords",
                "expected_faction_keywords",
                "expected_damaged_wounds_max",
            },
            "Reconciliation datasheet row",
        )
        datasheets.append(
            DatasheetReview(
                datasheet_id=_required_str(row, "datasheet_id"),
                name=_required_str(row, "name"),
                page_start=_required_int(row, "page_start"),
                page_end=_required_int(row, "page_end"),
                official_source_id=_required_str(row, "official_source_id"),
                reviewed_field_families=_required_str_tuple(row, "reviewed_field_families"),
                generator_input_payload_hash=_required_str(row, "generator_input_payload_hash"),
                catalog_gameplay_hash=_required_str(row, "catalog_gameplay_hash"),
                expected_keywords=_required_str_tuple(row, "expected_keywords"),
                expected_faction_keywords=_required_str_tuple(row, "expected_faction_keywords"),
                expected_damaged_wounds_max=_required_optional_int(
                    row, "expected_damaged_wounds_max"
                ),
            )
        )
    reconciliation = ExactRosterReconciliation(
        package_id=_required_str(payload, "package_id"),
        official_pdf=OfficialPdfSource(
            source_package_id=_required_str(official_payload, "source_package_id"),
            local_pdf=_required_str(official_payload, "local_pdf"),
            sha256=_required_str(official_payload, "sha256"),
        ),
        generator_inputs=GeneratorInputProvenance(
            artifact_hashes=tuple(validated_artifact_hashes.items()),
        ),
        datasheets=tuple(datasheets),
        schema_version=_required_str(payload, "schema_version"),
    )
    supplied_hash = _required_str(payload, "artifact_hash")
    if supplied_hash != reconciliation.artifact_hash():
        raise ChaosDaemonsRosterReconciliationError("Reconciliation artifact_hash is stale.")
    return reconciliation


def raw_reconciliation_artifact_hash(raw: bytes) -> str:
    if type(raw) is not bytes:
        raise ChaosDaemonsRosterReconciliationError("Reconciliation artifact input must be bytes.")
    return hashlib.sha256(raw).hexdigest()


def catalog_datasheet_gameplay_hash(*, catalog: ArmyCatalog, datasheet_id: str) -> str:
    if type(catalog) is not ArmyCatalog:
        raise ChaosDaemonsRosterReconciliationError("catalog must be ArmyCatalog.")
    requested_id = _validate_identifier("datasheet_id", datasheet_id)
    matches = tuple(
        datasheet for datasheet in catalog.datasheets if datasheet.datasheet_id == requested_id
    )
    if len(matches) != 1:
        raise ChaosDaemonsRosterReconciliationError(
            "Catalog must contain exactly one reviewed datasheet."
        )
    payload = {
        "datasheet": matches[0].to_payload(),
        "wargear": [
            wargear.to_payload()
            for wargear in catalog.wargear
            if wargear.wargear_id.startswith(f"{requested_id}:")
        ],
    }
    return _sha256_json(_without_provenance(payload))


def validate_catalog_against_reconciliation(
    *,
    catalog: ArmyCatalog,
    reconciliation: ExactRosterReconciliation,
) -> None:
    if type(catalog) is not ArmyCatalog:
        raise ChaosDaemonsRosterReconciliationError("catalog must be ArmyCatalog.")
    if type(reconciliation) is not ExactRosterReconciliation:
        raise ChaosDaemonsRosterReconciliationError(
            "reconciliation must be ExactRosterReconciliation."
        )
    datasheets = {datasheet.datasheet_id: datasheet for datasheet in catalog.datasheets}
    if tuple(sorted(datasheets)) != tuple(EXPECTED_REVIEW_ROWS):
        raise ChaosDaemonsRosterReconciliationError("Catalog reviewed datasheet closure drifted.")
    for review in reconciliation.datasheets:
        datasheet = datasheets[review.datasheet_id]
        if datasheet.name != review.name:
            raise ChaosDaemonsRosterReconciliationError("Catalog reviewed datasheet name drifted.")
        if datasheet.keywords.keywords != review.expected_keywords:
            raise ChaosDaemonsRosterReconciliationError(
                "Catalog reviewed datasheet keyword inventory drifted."
            )
        if datasheet.keywords.faction_keywords != review.expected_faction_keywords:
            raise ChaosDaemonsRosterReconciliationError(
                "Catalog reviewed datasheet faction-keyword inventory drifted."
            )
        if "SHADOW LEGION" in datasheet.keywords.keywords:
            raise ChaosDaemonsRosterReconciliationError(
                "Catalog must not bake the detachment-granted SHADOW LEGION keyword into a "
                "base datasheet."
            )
        damaged_maxima = tuple(effect.wounds_max for effect in datasheet.damaged_effects)
        expected_maximum = review.expected_damaged_wounds_max
        if expected_maximum is None:
            if damaged_maxima:
                raise ChaosDaemonsRosterReconciliationError(
                    "Catalog reviewed datasheet damaged profile drifted."
                )
        elif damaged_maxima != (expected_maximum,):
            raise ChaosDaemonsRosterReconciliationError(
                "Catalog reviewed datasheet damaged profile drifted."
            )
        if review.official_source_id not in datasheet.source_ids:
            raise ChaosDaemonsRosterReconciliationError(
                "Catalog reviewed datasheet official page source is missing."
            )
        if (
            catalog_datasheet_gameplay_hash(
                catalog=catalog,
                datasheet_id=review.datasheet_id,
            )
            != review.catalog_gameplay_hash
        ):
            raise ChaosDaemonsRosterReconciliationError(
                "Catalog reviewed datasheet gameplay payload drifted."
            )


def _validate_fixed_identity(reconciliation: ExactRosterReconciliation) -> None:
    if reconciliation.schema_version != SCHEMA_VERSION:
        raise ChaosDaemonsRosterReconciliationError("Reconciliation schema_version drifted.")
    if reconciliation.package_id != PACKAGE_ID:
        raise ChaosDaemonsRosterReconciliationError("Reconciliation package_id drifted.")
    if reconciliation.official_pdf != OfficialPdfSource(
        source_package_id=OFFICIAL_SOURCE_PACKAGE_ID,
        local_pdf=OFFICIAL_LOCAL_PDF,
        sha256=OFFICIAL_PDF_SHA256,
    ):
        raise ChaosDaemonsRosterReconciliationError("Reconciliation official PDF identity drifted.")
    if tuple(row.datasheet_id for row in reconciliation.datasheets) != tuple(EXPECTED_REVIEW_ROWS):
        raise ChaosDaemonsRosterReconciliationError(
            "Reconciliation exact datasheet closure drifted."
        )
    for row in reconciliation.datasheets:
        name, page_start, page_end, keywords, faction_keywords, damaged_maximum = (
            EXPECTED_REVIEW_ROWS[row.datasheet_id]
        )
        expected_source_id = (
            f"{OFFICIAL_SOURCE_PACKAGE_ID}:datasheet:{row.datasheet_id}:"
            f"pages-{page_start}-{page_end}"
        )
        if (
            row.name != name
            or row.page_start != page_start
            or row.page_end != page_end
            or row.official_source_id != expected_source_id
            or row.reviewed_field_families != REVIEWED_FIELD_FAMILIES
            or row.expected_keywords != keywords
            or row.expected_faction_keywords != faction_keywords
            or row.expected_damaged_wounds_max != damaged_maximum
        ):
            raise ChaosDaemonsRosterReconciliationError(
                "Reconciliation exact datasheet review identity drifted."
            )


def _without_provenance(value: object) -> object:
    if isinstance(value, dict):
        mapping = cast(dict[object, object], value)
        return {
            str(key): _without_provenance(item)
            for key, item in mapping.items()
            if str(key) not in _PROVENANCE_KEYS
        }
    if isinstance(value, list):
        return [_without_provenance(item) for item in cast(list[object], value)]
    if isinstance(value, tuple):
        return [_without_provenance(item) for item in cast(tuple[object, ...], value)]
    return value


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _validate_sha256(field_name: str, value: object) -> str:
    validated = _validate_identifier(field_name, value)
    if len(validated) != 64 or any(character not in "0123456789abcdef" for character in validated):
        raise ChaosDaemonsRosterReconciliationError(
            f"{field_name} must be a lowercase SHA-256 digest."
        )
    return validated


def _validate_identifier_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise ChaosDaemonsRosterReconciliationError(f"{field_name} must be a tuple.")
    seen: set[str] = set()
    validated: list[str] = []
    for value in values:
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise ChaosDaemonsRosterReconciliationError(
                f"{field_name} must not contain duplicates."
            )
        seen.add(identifier)
        validated.append(identifier)
    return tuple(validated)


def _require_exact_keys(value: dict[str, object], expected: set[str], context: str) -> None:
    if set(value) != expected:
        raise ChaosDaemonsRosterReconciliationError(f"{context} fields drifted.")


def _required_mapping(value: dict[str, object], key: str) -> dict[str, object]:
    selected = value[key]
    if not isinstance(selected, dict):
        raise ChaosDaemonsRosterReconciliationError(f"{key} must be a JSON object.")
    return cast(dict[str, object], selected)


def _required_str(value: dict[str, object], key: str) -> str:
    selected = value[key]
    if type(selected) is not str:
        raise ChaosDaemonsRosterReconciliationError(f"{key} must be a string.")
    return selected


def _required_int(value: dict[str, object], key: str) -> int:
    selected = value[key]
    if type(selected) is not int:
        raise ChaosDaemonsRosterReconciliationError(f"{key} must be an integer.")
    return selected


def _required_optional_int(value: dict[str, object], key: str) -> int | None:
    selected = value[key]
    if selected is not None and type(selected) is not int:
        raise ChaosDaemonsRosterReconciliationError(f"{key} must be an integer or null.")
    return selected


def _required_str_tuple(value: dict[str, object], key: str) -> tuple[str, ...]:
    selected = value[key]
    if not isinstance(selected, list):
        raise ChaosDaemonsRosterReconciliationError(f"{key} must be a string array.")
    selected_items = cast(list[object], selected)
    if any(type(item) is not str for item in selected_items):
        raise ChaosDaemonsRosterReconciliationError(f"{key} must be a string array.")
    return tuple(cast(str, item) for item in selected_items)


__all__ = (
    "OFFICIAL_LOCAL_PDF",
    "OFFICIAL_PDF_SHA256",
    "OFFICIAL_SOURCE_PACKAGE_ID",
    "PACKAGE_ID",
    "REVIEWED_SOURCE_PACKAGE_ID",
    "ChaosDaemonsRosterReconciliationError",
    "DatasheetReview",
    "ExactRosterReconciliation",
    "GeneratorInputProvenance",
    "catalog_datasheet_gameplay_hash",
    "raw_reconciliation_artifact_hash",
    "reconciliation_from_json_bytes",
    "validate_catalog_against_reconciliation",
)
