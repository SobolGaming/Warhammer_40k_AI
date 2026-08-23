from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING or __package__:
    from tools import generate_aeldari_aspect_warriors_rule_ir as aeldari_aspect_warriors
    from tools import generate_aeldari_autarchs_rule_ir as aeldari_autarchs
    from tools import (
        generate_aeldari_banshees_phoenix_lords_spiritseer_rule_ir as aeldari_banshees,
    )
    from tools import generate_aeldari_corsair_skyreavers_rule_ir as aeldari_skyreavers
    from tools import generate_aeldari_corsair_void_units_rule_ir as aeldari_void_units
    from tools import generate_aeldari_kharseth_rule_ir as aeldari_kharseth
    from tools import generate_aeldari_night_spinner_rule_ir as aeldari_night_spinner
    from tools import (
        generate_aeldari_shroud_runners_wraithblades_rule_ir as aeldari_shroud_wraith,
    )
    from tools import (
        generate_aeldari_war_walkers_wraithlord_rule_ir as aeldari_war_walkers_wraithlord,
    )
    from tools import (
        generate_aeldari_wave_serpent_shining_spears_eldrad_dire_avengers_rule_ir as aeldari_four,
    )
    from tools import (
        generate_aeldari_yriel_vypers_starfangs_rule_ir as aeldari_yriel_vypers_starfangs,
    )
    from tools import generate_chaos_daemons_datasheet_rule_ir as chaos_daemons
    from tools import generate_emperors_children_fulgrim_rule_ir as emperors_children_fulgrim
    from tools import (
        generate_emperors_children_infractors_tormentors_rule_ir as emperors_children_battleline,
    )
    from tools import generate_emperors_children_lucius_rule_ir as emperors_children_lucius
    from tools.faction_rule_ir_bundle import (
        build_rule_ir_shard_artifact,
        canonical_package_hash,
        check_json_artifact,
        datasheet_faction_ids_from_source_snapshot,
        render_json_artifact,
        rendered_artifact_sha256,
        write_json_artifact,
    )
    from tools.generate_emperors_children_lord_exultant_maulerfiend_spawn_rule_ir import (
        generated_artifact_payload as generate_emperors_children_lord_spawn,
    )
else:
    import generate_aeldari_aspect_warriors_rule_ir as aeldari_aspect_warriors
    import generate_aeldari_autarchs_rule_ir as aeldari_autarchs
    import generate_aeldari_banshees_phoenix_lords_spiritseer_rule_ir as aeldari_banshees
    import generate_aeldari_corsair_skyreavers_rule_ir as aeldari_skyreavers
    import generate_aeldari_corsair_void_units_rule_ir as aeldari_void_units
    import generate_aeldari_kharseth_rule_ir as aeldari_kharseth
    import generate_aeldari_night_spinner_rule_ir as aeldari_night_spinner
    import generate_aeldari_shroud_runners_wraithblades_rule_ir as aeldari_shroud_wraith
    import generate_aeldari_war_walkers_wraithlord_rule_ir as aeldari_war_walkers_wraithlord
    import generate_aeldari_wave_serpent_shining_spears_eldrad_dire_avengers_rule_ir as aeldari_four
    import generate_aeldari_yriel_vypers_starfangs_rule_ir as aeldari_yriel_vypers_starfangs
    import generate_chaos_daemons_datasheet_rule_ir as chaos_daemons
    import generate_emperors_children_fulgrim_rule_ir as emperors_children_fulgrim
    import generate_emperors_children_infractors_tormentors_rule_ir as emperors_children_battleline
    import generate_emperors_children_lucius_rule_ir as emperors_children_lucius
    from faction_rule_ir_bundle import (
        build_rule_ir_shard_artifact,
        canonical_package_hash,
        check_json_artifact,
        datasheet_faction_ids_from_source_snapshot,
        render_json_artifact,
        rendered_artifact_sha256,
        write_json_artifact,
    )
    from generate_emperors_children_lord_exultant_maulerfiend_spawn_rule_ir import (
        generated_artifact_payload as generate_emperors_children_lord_spawn,
    )

type PayloadFactory = Callable[[], dict[str, object]]

REPO_ROOT = Path(__file__).resolve().parents[1]
DATASHEETS_SOURCE_PATH = (
    REPO_ROOT
    / "data"
    / "source_snapshots"
    / "wahapedia"
    / "10th-edition"
    / "2026-06-14"
    / "json"
    / "Datasheets.json"
)
SHARD_ARTIFACT_DIRECTORY = (
    REPO_ROOT
    / "src"
    / "warhammer40k_core"
    / "rules"
    / "source_packages"
    / "warhammer_40000_11th"
    / "faction_pack_rule_ir"
    / "artifacts"
    / "shards"
)
PACKAGE_OUTPUT_PATH = SHARD_ARTIFACT_DIRECTORY.parent / "package.json"
AELDARI_OUTPUT_PATH = SHARD_ARTIFACT_DIRECTORY / "aeldari.json"
CHAOS_DAEMONS_OUTPUT_PATH = SHARD_ARTIFACT_DIRECTORY / "chaos-daemons.json"
EMPERORS_CHILDREN_OUTPUT_PATH = SHARD_ARTIFACT_DIRECTORY / "emperors-children.json"

AELDARI_SOURCE_PACKAGE_FACTORIES: tuple[PayloadFactory, ...] = (
    aeldari_aspect_warriors.generated_artifact_payload,
    aeldari_autarchs.generated_artifact_payload,
    aeldari_banshees.generated_artifact_payload,
    aeldari_skyreavers.generated_artifact_payload,
    aeldari_void_units.generated_artifact_payload,
    aeldari_kharseth.generated_artifact_payload,
    aeldari_night_spinner.generated_artifact_payload,
    aeldari_shroud_wraith.generated_artifact_payload,
    aeldari_war_walkers_wraithlord.generated_artifact_payload,
    aeldari_four.generated_artifact_payload,
    aeldari_yriel_vypers_starfangs.generated_artifact_payload,
)
EMPERORS_CHILDREN_SOURCE_PACKAGE_FACTORIES: tuple[PayloadFactory, ...] = (
    emperors_children_fulgrim.generated_artifact_payload,
    emperors_children_battleline.generated_artifact_payload,
    generate_emperors_children_lord_spawn,
    emperors_children_lucius.generated_artifact_payload,
)
CHAOS_DAEMONS_SOURCE_PACKAGE_FACTORIES: tuple[PayloadFactory, ...] = (
    chaos_daemons.generated_artifact_payload,
)

_OUTPUT_PATH_BY_SHARD_ID = {
    "aeldari": AELDARI_OUTPUT_PATH,
    "chaos-daemons": CHAOS_DAEMONS_OUTPUT_PATH,
    "emperors-children": EMPERORS_CHILDREN_OUTPUT_PATH,
}
_SOURCE_PACKAGE_FACTORIES_BY_SHARD_ID = {
    "aeldari": AELDARI_SOURCE_PACKAGE_FACTORIES,
    "chaos-daemons": CHAOS_DAEMONS_SOURCE_PACKAGE_FACTORIES,
    "emperors-children": EMPERORS_CHILDREN_SOURCE_PACKAGE_FACTORIES,
}
_CANONICAL_FACTION_ID_BY_SOURCE_ID = {
    "AE": "aeldari",
    "CD": "chaos-daemons",
    "EC": "emperors-children",
    "TS": "thousand-sons",
}

PACKAGE_ARTIFACT_SCHEMA = "core-v2-faction-pack-rule-ir-package-v1"
REGISTRY_ID = "warhammer-40000-11th-faction-pack-rule-ir"


class RuleIrPackageGenerationError(RuntimeError):
    """Raised when a complete RuleIR package cannot be published safely."""


def generated_rule_ir_shard_artifacts() -> dict[Path, dict[str, object]]:
    return generated_rule_ir_shard_artifacts_for_shards(
        shard_ids=tuple(sorted(_OUTPUT_PATH_BY_SHARD_ID))
    )


def generated_rule_ir_shard_artifacts_for_shards(
    *, shard_ids: Iterable[str]
) -> dict[Path, dict[str, object]]:
    artifacts: dict[Path, dict[str, object]] = {}
    requested_shard_ids = _validated_registered_shard_ids(shard_ids)
    for shard_id in requested_shard_ids:
        output_path = _OUTPUT_PATH_BY_SHARD_ID[shard_id]
        factories = _SOURCE_PACKAGE_FACTORIES_BY_SHARD_ID[shard_id]
        source_packages = _generated_source_packages(factories)
        datasheet_ids = tuple(
            sorted(
                {
                    datasheet_id
                    for source_package in source_packages
                    for datasheet_id in _datasheet_ids(source_package)
                }
            )
        )
        datasheet_faction_ids, provenance = datasheet_faction_ids_from_source_snapshot(
            source_snapshot_path=DATASHEETS_SOURCE_PATH,
            datasheet_ids=datasheet_ids,
            canonical_faction_id_by_source_id=_CANONICAL_FACTION_ID_BY_SOURCE_ID,
        )
        artifacts[output_path] = build_rule_ir_shard_artifact(
            shard_id=shard_id,
            source_packages=source_packages,
            datasheet_faction_ids=datasheet_faction_ids,
            datasheet_faction_ids_provenance=provenance,
        )
    return artifacts


def generated_package_artifact(
    shard_artifacts: dict[Path, dict[str, object]],
) -> dict[str, object]:
    expected_paths = set(_OUTPUT_PATH_BY_SHARD_ID.values())
    if set(shard_artifacts) != expected_paths:
        raise ValueError("RuleIR package manifest requires every registered physical shard.")
    shard_entries: dict[str, object] = {}
    for shard_id in sorted(_OUTPUT_PATH_BY_SHARD_ID):
        artifact_path = _OUTPUT_PATH_BY_SHARD_ID[shard_id]
        artifact = shard_artifacts[artifact_path]
        source_packages = _source_packages(artifact, shard_id=shard_id)
        datasheet_faction_ids = _datasheet_faction_ids(artifact, shard_id=shard_id)
        source_package_datasheet_ids = {
            datasheet_id
            for source_package in source_packages.values()
            for datasheet_id in _datasheet_ids(source_package)
        }
        if set(datasheet_faction_ids) != source_package_datasheet_ids:
            raise ValueError(
                "RuleIR shard datasheet_faction_ids do not match source-package inventories."
            )
        shard_entries[shard_id] = {
            "path": artifact_path.relative_to(PACKAGE_OUTPUT_PATH.parent).as_posix(),
            "sha256": rendered_artifact_sha256(artifact),
            "source_package_ids": sorted(source_packages),
            "datasheet_ids": sorted(datasheet_faction_ids),
            "source_row_ids": sorted(
                {
                    source_row_id
                    for source_package in source_packages.values()
                    for source_row_id in _source_row_ids(source_package)
                }
            ),
        }
    payload: dict[str, object] = {
        "artifact_schema": PACKAGE_ARTIFACT_SCHEMA,
        "edition": 11,
        "registry_id": REGISTRY_ID,
        "shard_artifacts": shard_entries,
        "package_hash": "",
    }
    payload["package_hash"] = canonical_package_hash(payload)
    return payload


def generated_rule_ir_artifacts() -> dict[Path, dict[str, object]]:
    shard_artifacts = generated_rule_ir_shard_artifacts()
    return {
        **shard_artifacts,
        PACKAGE_OUTPUT_PATH: generated_package_artifact(shard_artifacts),
    }


def _source_packages(
    artifact: dict[str, object],
    *,
    shard_id: str,
) -> dict[str, dict[str, object]]:
    if artifact.get("shard_id") != shard_id:
        raise ValueError("RuleIR shard identity does not match its registry entry.")
    source_packages = artifact.get("source_packages")
    if not isinstance(source_packages, dict) or not source_packages:
        raise ValueError("RuleIR shard artifact source_packages are missing.")
    validated: dict[str, dict[str, object]] = {}
    typed_source_packages = cast(dict[str, object], source_packages)
    for source_package_id, source_package in typed_source_packages.items():
        if type(source_package_id) is not str or not isinstance(source_package, dict):
            raise ValueError("RuleIR shard source package entry is malformed.")
        validated[source_package_id] = source_package
    return validated


def _datasheet_faction_ids(
    artifact: dict[str, object],
    *,
    shard_id: str,
) -> dict[str, str]:
    value = artifact.get("datasheet_faction_ids")
    if not isinstance(value, dict) or not value:
        raise ValueError(f"RuleIR shard {shard_id} datasheet_faction_ids are missing.")
    validated: dict[str, str] = {}
    for datasheet_id, faction_id in cast(dict[str, object], value).items():
        if type(datasheet_id) is not str or not datasheet_id:
            raise ValueError("RuleIR shard datasheet faction datasheet ID is malformed.")
        if type(faction_id) is not str or not faction_id:
            raise ValueError("RuleIR shard datasheet faction ID is malformed.")
        validated[datasheet_id] = faction_id
    return validated


def _datasheet_ids(source_package: dict[str, object]) -> tuple[str, ...]:
    datasheet_ids: set[str] = set()
    datasheet_id = source_package.get("datasheet_id")
    if type(datasheet_id) is str and datasheet_id:
        datasheet_ids.add(datasheet_id)
    datasheets = source_package.get("datasheets")
    if isinstance(datasheets, dict):
        typed_datasheets = cast(dict[str, object], datasheets)
        for candidate in typed_datasheets:
            if type(candidate) is not str or not candidate:
                raise ValueError("RuleIR shard datasheet ID is malformed.")
            datasheet_ids.add(candidate)
    elif isinstance(datasheets, list):
        typed_datasheets_list = cast(list[object], datasheets)
        for datasheet in typed_datasheets_list:
            if not isinstance(datasheet, dict):
                raise TypeError("RuleIR shard datasheet entry must be an object.")
            typed_datasheet = cast(dict[str, object], datasheet)
            listed_datasheet_id = typed_datasheet.get("datasheet_id")
            if type(listed_datasheet_id) is not str or not listed_datasheet_id:
                raise ValueError("RuleIR shard datasheet ID is malformed.")
            datasheet_ids.add(listed_datasheet_id)
    elif datasheets is not None:
        raise ValueError("RuleIR shard datasheets inventory is malformed.")
    if not datasheet_ids:
        raise ValueError("RuleIR shard source package has no datasheet inventory.")
    return tuple(sorted(datasheet_ids))


def _source_row_ids(source_package: dict[str, object]) -> tuple[str, ...]:
    records = source_package.get("records")
    if not isinstance(records, dict) or not records:
        raise ValueError("RuleIR shard source package records are missing.")
    source_row_ids: list[str] = []
    typed_records = cast(dict[str, object], records)
    for source_row_id in typed_records:
        if type(source_row_id) is not str or not source_row_id:
            raise ValueError("RuleIR shard source row ID is malformed.")
        source_row_ids.append(source_row_id)
    return tuple(sorted(source_row_ids))


def _generated_source_packages(
    factories: Sequence[PayloadFactory],
) -> tuple[dict[str, object], ...]:
    return tuple(factory() for factory in factories)


def generate_rule_ir_package_artifacts(
    *,
    requested_shard_ids: Iterable[str],
    check: bool,
) -> None:
    _validated_registered_shard_ids(requested_shard_ids)
    artifacts = generated_rule_ir_artifacts()
    shard_output_paths = tuple(
        _OUTPUT_PATH_BY_SHARD_ID[shard_id] for shard_id in sorted(_OUTPUT_PATH_BY_SHARD_ID)
    )
    if check:
        for output_path in shard_output_paths:
            check_json_artifact(output_path=output_path, payload=artifacts[output_path])
        check_json_artifact(
            output_path=PACKAGE_OUTPUT_PATH,
            payload=artifacts[PACKAGE_OUTPUT_PATH],
        )
        _verify_persisted_rule_ir_package(package_artifact=artifacts[PACKAGE_OUTPUT_PATH])
        _validate_persisted_package_with_real_loader()
        return
    _publish_rule_ir_package_artifacts(
        artifacts=artifacts,
        shard_output_paths=shard_output_paths,
    )


def _publish_rule_ir_package_artifacts(
    *,
    artifacts: dict[Path, dict[str, object]],
    shard_output_paths: tuple[Path, ...],
) -> None:
    output_paths = (*shard_output_paths, PACKAGE_OUTPUT_PATH)
    original_bytes = {
        output_path: output_path.read_bytes() if output_path.is_file() else None
        for output_path in output_paths
    }
    PACKAGE_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        dir=PACKAGE_OUTPUT_PATH.parent,
        prefix=".faction-rule-ir-stage-",
    ) as staging_directory_value:
        staging_directory = Path(staging_directory_value)
        staged_paths: dict[Path, Path] = {}
        for output_path in output_paths:
            relative_path = output_path.relative_to(PACKAGE_OUTPUT_PATH.parent)
            staged_path = staging_directory / relative_path
            write_json_artifact(output_path=staged_path, payload=artifacts[output_path])
            staged_paths[output_path] = staged_path
        _verify_rule_ir_package_bytes(
            manifest_bytes=staged_paths[PACKAGE_OUTPUT_PATH].read_bytes(),
            shard_bytes_by_id={
                shard_id: staged_paths[_OUTPUT_PATH_BY_SHARD_ID[shard_id]].read_bytes()
                for shard_id in sorted(_OUTPUT_PATH_BY_SHARD_ID)
            },
            package_artifact=artifacts[PACKAGE_OUTPUT_PATH],
        )
        try:
            for output_path in output_paths:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                _replace_staged_artifact(staged_paths[output_path], output_path)
            _verify_persisted_rule_ir_package(package_artifact=artifacts[PACKAGE_OUTPUT_PATH])
            _validate_persisted_package_with_real_loader()
        except (OSError, RuleIrPackageGenerationError) as exc:
            try:
                _restore_rule_ir_package_artifacts(original_bytes)
            except OSError as restore_exc:
                raise ExceptionGroup(
                    "RuleIR package publication and rollback both failed.",
                    (exc, restore_exc),
                ) from exc
            raise RuleIrPackageGenerationError(
                "RuleIR package publication failed; the original artifact set was restored."
            ) from exc


def _replace_staged_artifact(staged_path: Path, output_path: Path) -> None:
    staged_path.replace(output_path)


def _restore_rule_ir_package_artifacts(original_bytes: dict[Path, bytes | None]) -> None:
    for output_path, content in original_bytes.items():
        if content is None:
            output_path.unlink(missing_ok=True)
        else:
            output_path.write_bytes(content)


def _validate_persisted_package_with_real_loader() -> None:
    completed = subprocess.run(
        (
            sys.executable,
            "-c",
            (
                "from warhammer40k_core.rules.source_packages.warhammer_40000_11th "
                "import faction_pack_rule_ir as registry; "
                "assert registry.PACKAGE_HASH == registry.EXPECTED_PACKAGE_HASH"
            ),
        ),
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        details = completed.stderr.strip() or completed.stdout.strip()
        raise RuleIrPackageGenerationError(
            "Generated RuleIR package failed the real runtime loader validation.\n" + details
        )


def _verify_persisted_rule_ir_package(*, package_artifact: dict[str, object]) -> None:
    if not PACKAGE_OUTPUT_PATH.is_file():
        raise RuleIrPackageGenerationError(
            f"Generated RuleIR package manifest is missing: {PACKAGE_OUTPUT_PATH}"
        )
    shard_bytes_by_id: dict[str, bytes] = {}
    for shard_id in sorted(_OUTPUT_PATH_BY_SHARD_ID):
        output_path = _OUTPUT_PATH_BY_SHARD_ID[shard_id]
        if not output_path.is_file():
            raise RuleIrPackageGenerationError(
                f"Generated RuleIR shard artifact is missing: {output_path}"
            )
        shard_bytes_by_id[shard_id] = output_path.read_bytes()
    _verify_rule_ir_package_bytes(
        manifest_bytes=PACKAGE_OUTPUT_PATH.read_bytes(),
        shard_bytes_by_id=shard_bytes_by_id,
        package_artifact=package_artifact,
    )


def _verify_rule_ir_package_bytes(
    *,
    manifest_bytes: bytes,
    shard_bytes_by_id: dict[str, bytes],
    package_artifact: dict[str, object],
) -> None:
    if manifest_bytes != render_json_artifact(package_artifact):
        raise RuleIrPackageGenerationError(
            "Generated RuleIR package manifest bytes differ from the generated payload."
        )
    shard_artifacts_value = package_artifact.get("shard_artifacts")
    if not isinstance(shard_artifacts_value, dict):
        raise TypeError("RuleIR package manifest shard_artifacts must be an object.")
    shard_artifacts = cast(dict[str, object], shard_artifacts_value)
    if set(shard_artifacts) != set(_OUTPUT_PATH_BY_SHARD_ID):
        raise ValueError("RuleIR package manifest must reference every registered shard.")
    if set(shard_bytes_by_id) != set(_OUTPUT_PATH_BY_SHARD_ID):
        raise ValueError("RuleIR package bytes must include every registered shard.")
    for shard_id in sorted(_OUTPUT_PATH_BY_SHARD_ID):
        reference_value = shard_artifacts[shard_id]
        if not isinstance(reference_value, dict):
            raise TypeError("RuleIR package manifest shard reference must be an object.")
        reference = cast(dict[str, object], reference_value)
        output_path = _OUTPUT_PATH_BY_SHARD_ID[shard_id]
        expected_relative_path = output_path.relative_to(PACKAGE_OUTPUT_PATH.parent).as_posix()
        if reference.get("path") != expected_relative_path:
            raise ValueError("RuleIR package manifest shard path does not match its output path.")
        expected_sha256 = reference.get("sha256")
        if type(expected_sha256) is not str:
            raise TypeError("RuleIR package manifest shard sha256 must be text.")
        actual_sha256 = hashlib.sha256(shard_bytes_by_id[shard_id]).hexdigest()
        if actual_sha256 != expected_sha256:
            raise RuleIrPackageGenerationError(
                f"Generated RuleIR package manifest references stale shard artifact: {output_path}"
            )


def _validated_registered_shard_ids(shard_ids: Iterable[str]) -> tuple[str, ...]:
    requested_shard_ids = tuple(sorted(shard_ids))
    if not requested_shard_ids:
        raise ValueError("At least one RuleIR shard artifact must be requested.")
    if len(set(requested_shard_ids)) != len(requested_shard_ids):
        raise ValueError("RuleIR shard artifact request contains duplicate shard IDs.")
    for shard_id in requested_shard_ids:
        if (
            shard_id not in _OUTPUT_PATH_BY_SHARD_ID
            or shard_id not in _SOURCE_PACKAGE_FACTORIES_BY_SHARD_ID
        ):
            raise ValueError(f"RuleIR shard artifact is not registered: {shard_id}.")
    return requested_shard_ids


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Generate deterministic physical datasheet RuleIR shard artifacts."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if a committed RuleIR shard artifact is missing or stale.",
    )
    parser.add_argument(
        "--shard",
        action="append",
        choices=tuple(sorted(_OUTPUT_PATH_BY_SHARD_ID)),
        dest="shard_ids",
        help=(
            "Identify the requesting physical shard; the command still generates/checks the "
            "complete package. Repeat only to validate multiple requesting shard IDs."
        ),
    )
    args = parser.parse_args(argv)
    shard_ids = (
        tuple(sorted(_OUTPUT_PATH_BY_SHARD_ID)) if args.shard_ids is None else tuple(args.shard_ids)
    )
    generate_rule_ir_package_artifacts(
        requested_shard_ids=shard_ids,
        check=args.check,
    )


if __name__ == "__main__":
    main()
