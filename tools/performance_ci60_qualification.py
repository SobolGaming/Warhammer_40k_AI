"""Finite CI60 qualification; historical engine bytes never become current inputs."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, cast

BASE = "d7b7650fa1c76ee5830a9ffc78522eba3a6a3209"
PR_BASE = "5f509724da25a2f6ded0c2739a8e7c84bdf59c91"
SELF = "tools/performance_ci60_qualification.py"
NAMESPACE = "data/source_audits/ci60_qualification_v1"
ASSESSMENT = "docs/performance/change-assessment.json"
MAP = "docs/performance/policy-v3/operation-map.json"
FREEZE: str | None = None
SUPERSEDED_REPORTS: dict[str, str] = {
    "docs/performance/current/qualification40-dice.json": (
        "84ba455e20996cbd1fdeb246fc5410ab183d61da2ca6e4d760879168d2ddcd2e"
    ),
    "docs/performance/current/qualification40-dice_sustained.json": (
        "76fafa45cf162e140d07134e28e085c56d3b08dcd2947a3e32310bade0b89e5b"
    ),
    "docs/performance/current/qualification40-external_contract_source_reuse.json": (
        "fc87e9a27ca8ae10602db2524d3f8be1c1e3bf429b82bcae018ed9c860c3ed2c"
    ),
    "docs/performance/current/qualification40-fight.json": (
        "27fc3cba9c0da9b312eeb6cf980734f78f9b57f8bd3609d77a3405c511f8b86d"
    ),
    "docs/performance/current/qualification40-movement.json": (
        "bf5a007814b41cf78d1731677a86330eb3538c50c2ee1a95286d045a00b21d42"
    ),
    "docs/performance/current/qualification40-reconstruction.json": (
        "a3a5f2831eb81a2b9c016f5a2debb36157a4e9836eabe253afa8fa786159a7bc"
    ),
    "docs/performance/current/qualification40-setup.json": (
        "c845ab6764fef7f5ef1b91888fa4785cafa38383394d3433294da8632d942d8b"
    ),
    "docs/performance/current/qualification40-shock_reconstruction.json": (
        "18ce976b2063ab3f423574ccb460e0ad4f747e1842987178c78cd0260ee552d8"
    ),
    "docs/performance/current/qualification40-strength.json": (
        "89d57824df2b71b8459012b87f6f58fa5ec750e851fbfd071254da21e2143d70"
    ),
    "docs/performance/current/qualification40-visibility.json": (
        "b22afc0433f2ed9e3ab7078f0cbece7f6c637e1d4cab2139969bd54cab007aa5"
    ),
}
RETAINED = frozenset({"roster", "objective_control"})
CONTROLS = frozenset(
    {
        "ci/quality_shards/all.txt",
        "ci/quality_shards/shard-1.txt",
        "tools/core_rules_order97_inventory.py",
        "tests/category_migration_preservation.py",
        "tests/code_quality/test_category_migration_preservation.py",
        "tests/code_quality/test_cumulative_preservation.py",
        "tests/code_quality/test_performance_preflight.py",
        "tests/code_quality/test_performance_static_successor.py",
        "tools/quality_runtime_successor.py",
        "tools/cumulative_preservation.py",
        "tools/performance_policy.py",
        "tools/performance_history_snapshot.py",
        "scripts/check_performance_policy.py",
        "tests/code_quality/test_qualification40_successor.py",
        "tests/code_quality/test_qualification40_measurements.py",
        "tests/code_quality/test_quality_runtime.py",
        "tests/code_quality/test_performance_policy.py",
        "docs/CORE_RULES_REMEDIATION_ROADMAP.md",
        MAP,
        ASSESSMENT,
    }
)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical(value: object) -> str:
    return digest(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    )


def owned(root: Path, name: str) -> bytes:
    from tests.d07_geometry_containment import read_owned_geometry_member

    return read_owned_geometry_member(root, name)


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=root, timeout=60)


def history(root: Path, *args: str) -> bytes:
    from tools.performance_history_snapshot import historical

    return historical(root, "plain60", args, lambda: git(root, *args))


def admitted(root: Path) -> dict[str, bytes]:
    """Re-read the complete finite transition; no mutable success cache."""
    from tools.performance_policy import owner_hashes
    from tools.performance_preflight_successor import read_frozen_blobs

    freeze = FREEZE
    if freeze is None or len(freeze) != 40 or set(freeze) - set("0123456789abcdef"):
        raise ValueError("CI60 Qualification source freeze is pending.")
    history(root, "merge-base", "--is-ancestor", BASE, freeze)
    git(root, "merge-base", "--is-ancestor", freeze, "HEAD")
    names = history(root, "diff", "--name-only", BASE, freeze).decode().splitlines()
    declaration = NAMESPACE + "/changed-members.json"
    frozen = read_frozen_blobs(root, freeze, names)
    if json.loads(frozen[declaration]) != sorted(names) or len(names) != len(set(names)):
        raise ValueError("CI60 Qualification finite membership changed.")
    marker = b"\nFREEZE: str | None = None"
    if frozen[SELF].count(marker) != 1:
        raise ValueError("CI60 Qualification original activation changed.")
    actual = dict(frozen)
    actual[SELF] = frozen[SELF].replace(marker, f'\nFREEZE: str | None = "{freeze}"'.encode(), 1)
    assessment = json.loads(frozen[ASSESSMENT])
    row = assessment["changes"][SELF]
    row["after_sha256"] = digest(actual[SELF])
    row["owners"]["@module"]["after"] = owner_hashes(SELF, actual[SELF])["@module"]
    if json.loads(owned(root, ASSESSMENT)) != assessment:
        raise ValueError("CI60 Qualification assessment changed outside exact activation.")
    actual[ASSESSMENT] = owned(root, ASSESSMENT)
    for name, raw in actual.items():
        if owned(root, name) != raw:
            raise ValueError("CI60 Qualification Preflight source changed: " + name)
    transitions = json.loads(frozen[NAMESPACE + "/control-transitions.json"])
    if set(transitions) != set(CONTROLS - {ASSESSMENT}):
        raise ValueError("CI60 Qualification control membership changed.")
    old = read_frozen_blobs(root, BASE, sorted(CONTROLS))
    for name, row in transitions.items():
        if row.keys() != {"before_sha256", "after_sha256", "edits"}:
            raise ValueError("CI60 Qualification control recipe schema changed.")
        if digest(old[name]) != row["before_sha256"] or digest(frozen[name]) != row["after_sha256"]:
            raise ValueError("CI60 Qualification control recipe pin changed.")
        projected = old[name]
        for edit in row["edits"]:
            if edit.keys() != {"before", "after"} or not all(
                isinstance(value, str) for value in edit.values()
            ):
                raise ValueError("CI60 Qualification exact edit is malformed.")
            before, after = edit["before"].encode(), edit["after"].encode()
            if projected.count(before) != 1:
                raise ValueError("CI60 Qualification exact edit lacks one preimage.")
            projected = projected.replace(before, after, 1)
        if projected != frozen[name]:
            raise ValueError("CI60 Qualification control changed outside its exact recipe.")
    old_map, new_map = json.loads(old[MAP]), json.loads(frozen[MAP])
    additions = json.loads(frozen[NAMESPACE + "/added-operations.json"])
    if {k: v for k, v in old_map.items() if k != "operations"} != {
        k: v for k, v in new_map.items() if k != "operations"
    }:
        raise ValueError("CI60 Qualification historical families or budgets changed.")
    if new_map["operations"] != old_map["operations"] | additions:
        raise ValueError("CI60 Qualification historical operation changed.")
    for operation in additions.values():
        if (
            not operation["mandatory"]
            or len(operation["paths"]) != 1
            or any(
                any(c in literal for c in "*?[")
                for literal in operation["paths"] + operation["owners"]
            )
        ):
            raise ValueError("CI60 Qualification operation must remain literal and mandatory.")
    return actual


def control_projection(root: Path) -> dict[str, bytes]:
    from tools.performance_preflight_successor import read_frozen_blobs

    admitted(root)
    return read_frozen_blobs(root, BASE, sorted(CONTROLS))


def preceding_control(root: Path, name: str, supplied: bytes) -> bytes:
    if name not in CONTROLS:
        return supplied
    actual = owned(root, name)
    if supplied != actual:
        raise ValueError("CI60 Qualification caller supplied unrelated bytes.")
    projection = control_projection(root)
    return projection[name]


def current_source(root: Path, previous: dict[str, str]) -> dict[str, str]:
    from tools.performance_preflight_successor import read_frozen_blobs

    actual = admitted(root)
    prior_names = sorted(set(actual) & previous.keys())
    before = read_frozen_blobs(root, BASE, prior_names)
    if any(previous[name] != digest(before[name]) for name in prior_names):
        raise ValueError("CI60 Qualification predecessor source changed.")
    return previous | {name: digest(raw) for name, raw in actual.items()}


def measurement_controls(root: Path, current: dict[str, str]) -> dict[str, str]:
    """Only declared control bytes project; every current engine/fixture byte survives."""
    actual = admitted(root)
    projected = control_projection(root)
    result = dict(current)
    for name in (CONTROLS | {SELF}) & current.keys():
        if current[name] != digest(actual[name]):
            raise ValueError("CI60 actual input collector omitted current control bytes.")
        if name == SELF:
            del result[name]
        else:
            result[name] = digest(projected[name])
    return result


def _cohort(actual: dict[str, bytes]) -> dict[str, Any]:
    value: dict[str, Any] = json.loads(actual[NAMESPACE + "/family-plan.json"])
    families: dict[str, Any] = value["families"]
    if (
        value["base"] != PR_BASE
        or len(families) != 12
        or {name for name, row in families.items() if row["disposition"] == "retained"}
        != set(RETAINED)
        or sum(len(row["cases"]) for row in families.values()) != 41
        or sum(len(row["cases"]) * row["samples_per_case"] for row in families.values()) != 247
    ):
        raise ValueError("CI60 Qualification family inventory changed.")
    return families


def comparison_paths(root: Path) -> dict[str, str]:
    return {family: row["comparison"] for family, row in _cohort(admitted(root)).items()}


def applies(root: Path, *, base: str, family: str, path: str) -> bool:
    return base == PR_BASE and comparison_paths(root).get(family) == path


def producing_inputs(root: Path, current: dict[str, str]) -> dict[str, str]:
    return _producing_inputs(admitted(root), current)


def _producing_inputs(actual: dict[str, bytes], current: dict[str, str]) -> dict[str, str]:
    measured: dict[str, str] = json.loads(actual[NAMESPACE + "/producing-inputs.json"])
    activated = f'\nFREEZE: str | None = "{FREEZE}"'.encode()
    marker = b"\nFREEZE: str | None = None"
    if actual[SELF].count(activated) != 1 or measured.get(SELF) != digest(
        actual[SELF].replace(activated, marker, 1)
    ):
        raise ValueError("CI60 producing SELF is not the exact unactivated frozen source.")
    expected = measured | {SELF: digest(actual[SELF])}
    if current != expected:
        raise ValueError("CI60 complete producing inputs differ from the actual current collector.")
    return measured


def extend_catalog(builder: Any) -> None:
    """Append the finite CI60 native objects after the unchanged historical catalog."""
    freeze = FREEZE
    if freeze is None:
        raise ValueError("CI60 Qualification catalog freeze is pending.")
    builder.fact("plain60", ("merge-base", "--is-ancestor", BASE, freeze), "ci60.ancestry")
    raw = builder.fact("plain60", ("diff", "--name-only", BASE, freeze), "ci60.membership")
    names = raw.decode().splitlines()
    frozen = builder.add("plain60", freeze, dict.fromkeys(names), "ci60.freeze")
    if json.loads(frozen[NAMESPACE + "/changed-members.json"]) != sorted(names):
        raise ValueError("CI60 Qualification native membership changed.")
    builder.add("plain60", BASE, dict.fromkeys(CONTROLS), "ci60.control-preimages")
    # current_source verifies the exact original predecessor for every existing member.
    existing = set(builder.all_paths("plain60", BASE)) & set(names)
    builder.add("plain60", BASE, dict.fromkeys(existing), "ci60.source-preimages")


def source_binding(actual: dict[str, bytes], input_digest: str) -> dict[str, Any]:
    spec = json.loads(actual[NAMESPACE + "/tool-input-roles.json"])
    inventories = json.loads(actual[spec["inventories_path"]])
    before, after = inventories["base"], inventories["head"]
    common = {name: pin for name, pin in before.items() if after.get(name) == pin}
    changed = (before.keys() | after.keys()) - common.keys()
    if (
        spec["schema"] != "tool-input-roles-v3"
        or spec["base_revision"] != PR_BASE
        or canonical(inventories) != spec["inventories_sha256"]
        or canonical(common) != spec["common_sha256"]
        or spec["roles"].keys() != changed
        or any(
            role
            not in {"runtime-or-generator-treatment", "side-derived-output", "untimed-governance"}
            for role in spec["roles"].values()
        )
    ):
        raise ValueError("CI60 complete source-token input roles changed.")
    return {
        "schema": spec["schema"],
        "family": "external_contract_source_reuse",
        "base_revision": PR_BASE,
        "head_input_digest": input_digest,
        "role_spec_sha256": canonical(spec),
        "complete_inventories_sha256": canonical(inventories),
        "common_sha256": canonical(common),
        "contract_trees": spec["contract_trees"],
        "runtime_identities": spec["runtime_identities"],
        "shared_dependencies_sha256": spec["shared_dependencies_sha256"],
        "shared_workload_sha256": spec["shared_workload_sha256"],
    }


def retained_role_proof(
    root: Path,
    family: str,
    actual: dict[str, bytes],
    current: dict[str, str],
    measured: dict[str, str],
) -> dict[str, Any]:
    from tools.performance_policy import owner_hashes

    proofs = json.loads(actual[NAMESPACE + "/retained-role-proofs.json"])
    if proofs.keys() != set(RETAINED) or family not in RETAINED:
        raise ValueError("CI60 retained applicability is limited to two exact families.")
    proof: dict[str, Any] = proofs[family]
    changed = {
        name for name in current.keys() | measured.keys() if current.get(name) != measured.get(name)
    }
    if (
        proof["current_input_digest"] != canonical(current)
        or proof["producing_input_digest"] != canonical(measured)
        or proof["changed_inputs"].keys() != changed
    ):
        raise ValueError("CI60 retained family roles omit or invent current inputs.")
    for name, row in proof["changed_inputs"].items():
        if (
            row["before"] != measured.get(name)
            or row["after"] != current.get(name)
            or row["role"]
            not in {
                "uncalled-owner",
                "identity-only",
                "untimed-governance",
                "unchanged-called-owner-in-changed-module",
            }
            or len(row["reason"].strip()) < 30
        ):
            raise ValueError("CI60 retained family changed-input role changed.")
    for name, owners in proof["called_owners"].items():
        current_owners = owner_hashes(name, owned(root, name))
        if any(current_owners.get(owner) != pin for owner, pin in owners.items()):
            raise ValueError("CI60 retained family called owner changed: " + name)
    if not proof["called_owners"] or len(proof["call_path"].strip()) < 100:
        raise ValueError("CI60 retained family call proof is incomplete.")
    return proof


def measurement(
    root: Path,
    *,
    current: dict[str, str],
    report: dict[str, Any],
    family: str,
) -> tuple[dict[str, str], dict[str, object] | None, str, str]:
    """Original runtimes stay original; current applicability is a separate receipt."""
    from tools import cumulative_preservation as cumulative
    from tools import performance_qualification_measurements as measurements
    from tools import performance_qualification_successor as old
    from tools import performance_tool_inputs_v3 as roles
    from warhammer40k_core.build_identity import verified_engine_build_identity

    live = cumulative.verify_live(root)
    actual = admitted(root)
    inputs = _producing_inputs(actual, current)
    families = _cohort(actual)
    plan = families[family]
    binding = None
    proof: dict[str, Any] | None = None
    if family in RETAINED:
        historical_stage = cast(_HistoricalStage, old)
        freeze = _HistoricalStage.freeze(historical_stage, root)
        inputs = json.loads(
            _HistoricalStage.member(
                historical_stage, root, old.NAMESPACE + "/producing-inputs.json", freeze
            )
        )
        if canonical(inputs) != old.PRODUCING_INPUT_DIGEST:
            raise ValueError("CI60 original producing input authority changed.")
        proof = retained_role_proof(
            root, family, actual, _producing_inputs(actual, current), inputs
        )
        provenance = json.loads(
            _HistoricalStage.member(
                historical_stage, root, old.NAMESPACE + "/measurement-provenance.json", freeze
            )
        )
        row = provenance[family]
        original = json.loads(
            _HistoricalStage.member(historical_stage, root, plan["comparison"], freeze)
        )
        if report != original:
            raise ValueError("CI60 retained report changed its original samples or identities.")
        runtime = row["head"]["runtime_build_id"]

        def member(name: str) -> bytes:
            return _HistoricalStage.member(historical_stage, root, name, freeze)
    else:
        provenance = json.loads(actual[NAMESPACE + "/measurement-provenance.json"])
        if set(provenance) != set(families) - RETAINED:
            raise ValueError("CI60 fresh family provenance membership changed.")
        row = provenance[family]
        runtime = verified_engine_build_identity().build_id

        def member(name: str) -> bytes:
            return actual[name]

    if (
        row["base_revision"] != PR_BASE
        or row["head_input_digest"] != canonical(inputs)
        or report["family"] != family
        or report["base_revision"] != PR_BASE
        or report["head_runtime_build_id"] != runtime
    ):
        raise ValueError("CI60 comparison has another producing cohort.")
    for side in ("base", "head"):
        arm = row[side]
        raw = json.loads(member(arm["path"]))
        samples = measurements.samples_from_raw(family, raw)
        if (
            canonical(raw) != arm["canonical_sha256"]
            or samples != arm["samples"]
            or samples != report[side]["samples"]
            or set(samples) != set(plan["cases"])
            or any(len(values) != plan["samples_per_case"] for values in samples.values())
            or report[side]["runtime_build_id"] != arm["runtime_build_id"]
            or arm["completed"] is not True
        ):
            raise ValueError("CI60 raw report lost a sample, case, completion or identity.")
        if not arm["receipt_paths"]:
            raise ValueError("CI60 measured arm lacks a whole-process receipt.")
        for path in arm["receipt_paths"]:
            receipt = json.loads(member(path))
            if receipt["exit_code"] != 0 or receipt["timeout"] or receipt["source_drift"]:
                raise ValueError("CI60 measured arm failed or changed source.")
    if family == "external_contract_source_reuse":
        binding = source_binding(actual, canonical(inputs))
        if report["input_binding"] != binding:
            raise ValueError("CI60 source-token report has unrelated complete roles.")
        roles.validate_generated_evidence(report["generated_output_binding"], binding)
    if cumulative.verify_live(root) != live:
        raise ValueError("CI60 source changed during evidence admission.")
    receipt = canonical(
        {
            "current_source": live,
            "current_inputs": canonical(current),
            "current_runtime": verified_engine_build_identity().build_id,
            "family": family,
            "disposition": plan["disposition"],
            "producing_inputs": canonical(inputs),
            "producing_runtime": runtime,
            "raw_provenance": row,
            "retained_role_proof": proof,
        }
    )
    return inputs, binding, receipt, runtime


def retained_historical_report(*, base: str, path: str, change: dict[str, object]) -> bool:
    """Ten exact immutable former-current records remain historical obligations."""
    return (
        base == PR_BASE
        and path in SUPERSEDED_REPORTS
        and change["before_sha256"] is None
        and change["after_sha256"] == SUPERSEDED_REPORTS[path]
    )


class _HistoricalStage(Protocol):
    def _freeze(self, root: Path) -> str: ...
    def _member(self, root: Path, name: str, freeze: str) -> bytes: ...
    def _read(self, root: Path, name: str) -> bytes: ...

    def freeze(self, root: Path) -> str:
        return self._freeze(root)

    def member(self, root: Path, name: str, freeze: str) -> bytes:
        return self._member(root, name, freeze)

    def read(self, root: Path, name: str) -> bytes:
        return self._read(root, name)


def historical_inputs(root: Path, *, original_controls: bool = False) -> dict[str, str]:
    """Authenticated old dictionary for historical assertions; never current credit."""
    from tools import performance_qualification_successor as old

    stage = cast(_HistoricalStage, old)
    freeze = _HistoricalStage.freeze(stage, root)
    result: dict[str, str] = json.loads(
        _HistoricalStage.member(stage, root, old.NAMESPACE + "/producing-inputs.json", freeze)
    )
    if canonical(result) != old.PRODUCING_INPUT_DIGEST:
        raise ValueError("CI60 original producing input authority changed.")
    if original_controls:
        allowed = {old.SELF, MAP, "tests/code_quality/test_qualification40_successor.py"}
        result |= {name: digest(_HistoricalStage.read(stage, root, name)) for name in allowed}
    return result


def historical_ledger_owners(root: Path, path: str, current: dict[str, str]) -> dict[str, str]:
    """One historical module-import assertion; never a measurement-input projection."""
    name = "src/warhammer40k_core/engine/retained_demise_removal.py"
    if path != name:
        return current
    from tools.performance_policy import owner_hashes

    before = "482b60427ede07c2ef519a7633aa53e463c05dc353290f26e34cfe62594ced83"
    after = "fde9ffe9f023bf0d1fcbfed6c10bdf62481d0915bbaeda34462525a28e51ec79"
    actual = admitted(root)
    if current.get("@module") != after or owner_hashes(name, actual[name]) != current:
        raise ValueError("CI60 current retained-demise owner source changed.")
    raw = actual[name].replace(b"\r\n", b"\n")
    import_line = (
        b"    from warhammer40k_core.engine.retained_destruction_state "
        b"import RetainedModelDestruction\n"
    )
    if (
        raw.count(import_line) != 1
        or owner_hashes(name, raw.replace(import_line, b"", 1)).get("@module") != before
    ):
        raise ValueError("CI60 ledger successor is not the sole reviewed type-only import.")
    original = owner_hashes(name, history(root, "show", BASE + ":" + name))
    if original.get("@module") != before:
        raise ValueError("CI60 original retained-demise ledger owner changed.")
    return current | {"@module": before}


HISTORICAL_TEST_PINS: dict[str, str] = {
    "tests/shared/category_migration/phase11e_mission_scoring_cleanup_configuration.py": (
        "dcf42d1f5991ab5ced6061152472bc00e415117709c4c30846f8f709069a8553"
    ),
    "tests/shared/category_migration/phase11e_mission_scoring_cleanup_history_and_reserves.py": (
        "3f579830b668704ccbfd4b94da524df1c74e297ab52614ae0168ef298e6144da"
    ),
    "tests/integration/test_fight_on_death_presence.py": (
        "c63c3b334a69aa742e86da70d61f602a4eaf5144a51da88c1837bbc228917123"
    ),
    "tests/setup_completion_helpers.py": (
        "928c24e7775f97890720fee9619432029bed4821ff1a5c72871148af02c12c15"
    ),
    "tests/unit/test_phase12b_stratagem_framework.py": (
        "4aace3168598f0a8f8d02f23ece82e611dfb73657629941be99fc5dc0e4c0a64"
    ),
    "tests/unit/test_phase17g_runtime_content.py": (
        "e30343a5fceafc63e3c31f0228d3d3a555882920ea0260623123e9c9bf5fe5fd"
    ),
}
HISTORICAL_CATEGORY_TESTS = frozenset(
    {
        "tests/unit/test_phase17g_runtime_content.py",
        "tests/shared/category_migration/phase11e_mission_scoring_cleanup_configuration.py",
        "tests/shared/category_migration/phase11e_mission_scoring_cleanup_history_and_reserves.py",
    }
)
HISTORICAL_DIRECT_TESTS = frozenset(HISTORICAL_TEST_PINS) - HISTORICAL_CATEGORY_TESTS


def historical_test_preimage(root: Path, path: str, current: bytes) -> bytes:
    """Exact historical assertion view; never a physical pytest or measured input."""
    if path not in HISTORICAL_TEST_PINS:
        return current
    actual = admitted(root)
    if current != actual[path]:
        raise ValueError("CI60 historical test caller supplied unrelated current bytes.")
    before = history(root, "show", BASE + ":" + path)
    if digest(before) != HISTORICAL_TEST_PINS[path]:
        raise ValueError("CI60 historical test native preimage changed.")

    def assertions(raw: bytes) -> Counter[str]:
        return Counter(
            ast.dump(node, include_attributes=False)
            for node in ast.walk(ast.parse(raw))
            if isinstance(node, ast.Assert)
        )

    if assertions(before) - assertions(current):
        raise ValueError("CI60 historical test lost an original assertion.")
    return before


class _HistoricalPrevious(Protocol):
    def __call__(
        self, root: Path, name: str, supplied: bytes, *, predecessor: bytes | None = None
    ) -> bytes: ...


def _historical_ci54_functions(root: Path) -> dict[str, Any]:
    """Original native CI54 function for its explicitly sparse historical test fixture."""
    from tools import quality_runtime_successor as original

    projection = control_projection(root)
    source = ast.parse(projection[original.SELF])
    functions: list[ast.stmt] = [
        node
        for node in source.body
        if isinstance(node, ast.FunctionDef) and node.name in {"admit", "previous"}
    ]
    if {node.name for node in functions if isinstance(node, ast.FunctionDef)} != {
        "admit",
        "previous",
    } or len(functions) != 2:
        raise ValueError("CI60 original CI54 admission owner changed.")
    physical = original.owned

    def historical_read(selected: Path, name: str) -> bytes:
        if selected == root and name in projection:
            return projection[name]
        return physical(selected, name)

    namespace = dict(vars(original)) | {"owned": historical_read}
    exec(
        compile(ast.Module(body=functions, type_ignores=[]), "authenticated-ci54-admit", "exec"),
        namespace,
    )
    return namespace


def historical_ci54_admission(root: Path) -> Callable[[Path], None]:
    return cast(Callable[[Path], None], _historical_ci54_functions(root)["admit"])


def historical_ci54_previous(root: Path) -> _HistoricalPrevious:
    return cast(_HistoricalPrevious, _historical_ci54_functions(root)["previous"])
