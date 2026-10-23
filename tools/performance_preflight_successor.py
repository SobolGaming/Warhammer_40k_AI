"""Exact preflight and static successor; historical measurement anchors remain fixed."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, cast

BASE = "fc1f186aeb0d143983e22382778177f4648438fd"
BASE_SOURCE = "36ab649ef5a6ab747587dc25d05336252db5a4eb148dc24619e6881c38efec42"
SELF = "tools/performance_preflight_successor.py"
ASSESSMENT = "docs/performance/change-assessment.json"
CI_WORKFLOW = ".github/workflows/ci.yml"
INVENTORY = "data/source_audits/order135/current-inventory-category-migration.json"
FREEZE_COMMIT: str | None = None
# Filled from exact reviewed implementation bytes before the immutable freeze.
_PIN_ROWS = (
    (
        ".github/workflows/ci.yml",
        "ee0d1a9d331a06195836847d291184b82b94a5d9cfc36bb7485cfabb6bd1c0fe",
    ),
    (
        "data/source_audits/order135/current-inventory-category-migration.json",
        "c0460f930be48c49dcbef7568ea1af5e2319ca374d658b6abdb8eadd38869c16",
    ),
    (
        "docs/CORE_RULES_REMEDIATION_ROADMAP.md",
        "3078440364a17fcb8ae09a7e8aad2217789a70968bde4ca9c560fcf34382ed52",
    ),
    (
        "docs/performance/ci-compatibility-successor49c.json",
        "87a053390797d9eec3c833a9fffaf571d528565886ad27f412d0237da7d78fe1",
    ),
    (
        "docs/performance/ci-format-successor49b.json",
        "00d1fb9f7dd5199decb969ed730261bf9cc1dc4eaf6e9040e3e34ecd0eee435e",
    ),
    (
        "docs/performance/ci-runtime-successor51.json",
        "63350c6f60f38970d695ff3c8bcacf29e51737fda5d1d3216d2b1cdd9461a9b5",
    ),
    (
        "docs/performance/ci-successor49.json",
        "ea9fd6be7ca6371b78461291d95c85ba2371838b82e4e2f3a7a391212f9d879c",
    ),
    (
        "docs/performance/ci-transport-successor49d.json",
        "b5ce1cda52ac28878942943c16f8e0db3f793560ae1c0c3d9b5af68231c3849d",
    ),
    (
        "docs/performance/policy-v3/operation-map.json",
        "d18e059bfde5abae9d9196cc16ebb46e417d0e8a4aa5fb810ee1b630c58c5b8f",
    ),
    (
        "docs/performance/static-successor48.json",
        "b834787bc3f8bcf503ea3ae985d1a6f46e598a6350e8f1b5621e3d41d25f3c33",
    ),
    (
        "scripts/__init__.py",
        "8d5e4e6f7bebd9df2e7c317a68f93d634913012d661987474a65739976b9b4ec",
    ),
    (
        "scripts/benchmark_order88_strength.py",
        "c2d5d84ed6f56e9852046f6acf87214883f0236afe61a77210e0e9489fe0e762",
    ),
    (
        "scripts/check_performance_policy.py",
        "ce2c1e27152f0eb030b867078f543bb94472a7b3b0cf3cd0d5e2cc1102111209",
    ),
    (
        "scripts/performance_smoke.py",
        "0380ba2c9ab5c1e045f281f810f0e6e582b0738a3db8eab7a18ecfc34fe6c4d8",
    ),
    (
        "tests/category_migration_preservation.py",
        "ac412880e4214d29d298622a8cfd11e774905470bcaa5c38e278753c14b91f59",
    ),
    (
        "tests/code_quality/__init__.py",
        "8d5e4e6f7bebd9df2e7c317a68f93d634913012d661987474a65739976b9b4ec",
    ),
    (
        "tests/code_quality/test_category_migration_preservation.py",
        "bf8dc4a958f77bfa2837395fa759ea63b77dccdd3a6f5d6221dafa5d038273ac",
    ),
    (
        "tests/code_quality/test_ci_history_input.py",
        "762bfc9bd8d6094dc53205da38ecbbf11058dd8948a583d725e5b79b6fad4fcb",
    ),
    (
        "tests/code_quality/test_ci_runtime_successor.py",
        "331f50966c0573f3e95705dd7f2756cb9ed9c25b6c7ab1e102b34c203de4254d",
    ),
    (
        "tests/code_quality/test_cumulative_preservation.py",
        "b27516e78bf1a911aa5f814b8f6bda1cc76ba404558715be843a47caa66b6629",
    ),
    (
        "tests/code_quality/test_d07_geometry_containment.py",
        "7de3292b5ac379ece05285fc4e94eab943af5dfc55f6961b5a0e42644384fdd4",
    ),
    (
        "tests/code_quality/test_faction_content_runtime_structure.py",
        "82c715824387446f1fc2abd20f6fd957a3644b5cde0eb13f1204b8e94215079c",
    ),
    (
        "tests/code_quality/test_order34_action_restrictions.py",
        "47d450c66f0b0c801c5963d71fc182bb0eced3354dda416228c60038209da1c4",
    ),
    (
        "tests/code_quality/test_order97_faction_relocation.py",
        "0ee571c76b471dd9940f2a716c0c1f71ebc8a766f90ce2ae94c8239d47feda22",
    ),
    (
        "tests/code_quality/test_performance_integration_batch.py",
        "bbdff0e56ccb7f90101363c02431db19e4ffd93d181af06d8a92f5a62eb2ccdd",
    ),
    (
        "tests/code_quality/test_performance_preflight.py",
        "b6924bdca684374749f2a86d7e086192de3ace2b6eac595aa558deb8117c57e6",
    ),
    (
        "tests/code_quality/test_performance_static_successor.py",
        "4aa98bd59b00a15f65efddd433d4b9c3fa2d748a6ff6fee1581cd7dad848e128",
    ),
    (
        "tests/code_quality/test_qualification40_successor.py",
        "bc50d496af49cd36d88e33cea60c01bf64f5ad040ff41b1f66d1f6353fa7a890",
    ),
    (
        "tests/support/section08_native_mission.py",
        "c5cd5422243cc6a2b849b30c03743afc52a8535245b739ae00bde656c9e9feec",
    ),
    (
        "tools/core_rules_order97_inventory.py",
        "a2244c13bb62a966807801bd21929b60004d4f89260c3e1a7fde852d0721f0b5",
    ),
    (
        "tools/cumulative_preservation.py",
        "0aed6e5a524e891710bc85c2eda40565ca1f5cfc5c07f268acdb6ec727c060f3",
    ),
    (
        "tools/generate_aeldari_datasheet_semantic_coverage.py",
        "1e49fd40cf7f9841054315e1db8eb4e6ba4c92c94db9080a9efab375b254b3bc",
    ),
    (
        "tools/performance_policy.py",
        "fb1bf3b9b983df3301edd047f5855efd1352507934f37bd88005e4b4eafe5a2e",
    ),
    (
        "tools/performance_preflight.py",
        "68231d01c2be7c1a1c1951dd0a178acaf97738ddfc937e5aac88a921fd7048a8",
    ),
    (
        "tools/performance_qualification_successor.py",
        "45ba0c6dd10afb1f49f42e1cfe8ae77dab08b66436f2e9b4d8517415db28ed2a",
    ),
    (
        "tools/thousand_sons_perils_preservation.py",
        "2e9ef0110809dde8b380e04a7b608095672c10ea39b8cfc9aff8318002320894",
    ),
)
PINS: dict[str, str] = dict(_PIN_ROWS)

ANCHORS = {
    "tests/__init__.py": ("01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b"),
}
QUALITY_BOOTSTRAP = "tests/code_quality/__init__.py"


STATIC_BASE = "b150e426c70d4705da100bc75f1d253483e021c7"
STATIC_RECORD = "docs/performance/static-successor48.json"
STATIC_TEST = "tests/code_quality/test_order34_action_restrictions.py"
STATIC_FIXTURE = "tests/support/section08_native_mission.py"
_STATIC_BEFORE_ROWS = (
    (
        "tests/code_quality/test_cumulative_preservation.py",
        "a761f02992373d610f0df01b3c2b419c4825b61f86b4222f73560542e8d379da",
    ),
    (
        "tests/code_quality/test_d07_geometry_containment.py",
        "241b0a96741494bb06ef77613a2cf4a1fcc4c60d12cb41bde1589efb491a91b0",
    ),
    (
        "tests/code_quality/test_order34_action_restrictions.py",
        "42b011550184e5377296d5a325381a30f3912728846e61f8a6fab86244430124",
    ),
    (
        "tests/code_quality/test_order97_faction_relocation.py",
        "39833a0fb545a8121c4aa9d1ce74bcedae3c8790ea0f7624c25ed543b4547e7f",
    ),
    (
        "tests/code_quality/test_performance_preflight.py",
        "5618fbac9cfbefae31c8ddeda8a6d5646026a01d48debc4c89379a6140e34e9f",
    ),
    (
        "tests/code_quality/test_qualification40_successor.py",
        "5a1f745da1d751f9c0be22ade0500831862381687c5de23d248e7269b64561d3",
    ),
    (
        "tests/support/section08_native_mission.py",
        "a4282eba8e4bfccb18ad17417e43ef9b9cd9063285777c155e13b0955be2ccc9",
    ),
    (
        "tools/core_rules_order97_inventory.py",
        "a9fcf75cffde412df9bd0aea2bfa99fcb2b9deb2c1a1e88cd870c00a459a39e6",
    ),
    (
        "tools/cumulative_preservation.py",
        "b3e21ddadefb08e1a26c2a0f0d702252bd2ef23ebb2f2593b821cc000fc13e5a",
    ),
)
STATIC_BEFORE: dict[str, str] = dict(_STATIC_BEFORE_ROWS)


CI_BASE = "d1d37f45c17e7ecc4d60b990b011d4c725ac4d1c"
CI_RECORD = "docs/performance/ci-successor49.json"
CI_NEW = "scripts/__init__.py"
CI_ROADMAP = "docs/CORE_RULES_REMEDIATION_ROADMAP.md"
_CI_BEFORE_ROWS = (
    (
        "tests/__init__.py",
        "01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b",
    ),
    (
        "tools/generate_aeldari_datasheet_semantic_coverage.py",
        "59c535dbeac16d8aad6d413558fb20269ebb020d1cf5ec0927ff372ca44a220d",
    ),
    (
        "docs/performance/policy-v3/operation-map.json",
        "f330487a339f4e3d58f4301afd6a6c21f64d9ed47e1f46742ebcbdf3e3b867b9",
    ),
    (
        "docs/CORE_RULES_REMEDIATION_ROADMAP.md",
        "df1b90a433e4f38aa0e2cd0974a9428f9d230c6bbce1d9079a0276ee16dc7442",
    ),
)
CI_BEFORE: dict[str, str] = dict(_CI_BEFORE_ROWS)


CI_FORMAT_BASE = "d330382d40cd0487fec3b13e4ac315f817bad694"
CI_FORMAT_RECORD = "docs/performance/ci-format-successor49b.json"
_CI_FORMAT_BEFORE_ROWS = (
    (
        "scripts/benchmark_order88_strength.py",
        "e216b66054625f434b62944f50c545f772af88610498b818b39f0c1d6c34abcb",
    ),
    (
        "scripts/check_performance_policy.py",
        "211658e8b50b0bb1f443b5389d815a221e1e218c1d475f909b32fa2959cb4d75",
    ),
    (
        "scripts/performance_smoke.py",
        "f3934ba9961ee31c80582ad1a2f8dc5a66cd56f1f05f4803f397f125f6502174",
    ),
)
CI_FORMAT_BEFORE: dict[str, str] = dict(_CI_FORMAT_BEFORE_ROWS)


CI_COMPAT_BASE = "856b74a69676fdc1cc7a8d7e54ab6adb2fbfa2c3"
CI_COMPAT_RECORD = "docs/performance/ci-compatibility-successor49c.json"
_CI_COMPAT_BEFORE_ROWS = (
    (
        "tests/__init__.py",
        "8d5e4e6f7bebd9df2e7c317a68f93d634913012d661987474a65739976b9b4ec",
    ),
    (
        "tests/code_quality/__init__.py",
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    ),
    (
        "docs/performance/policy-v3/operation-map.json",
        "5323c1736433605c84d150bb43371a85db5ee8d726b57fbe1ec1df600a1012a0",
    ),
    (
        "tools/performance_qualification_successor.py",
        "8306fec5f45dbddee62d899ff500a2d9d94799ad8ca2e6f09a23487b4c8f161c",
    ),
    (
        "tests/code_quality/test_qualification40_successor.py",
        "dbc224be55ff45ba4d86eef3648ba641f4e6c350f84a58c0e5a6751229c550bc",
    ),
    (
        "tests/code_quality/test_performance_preflight.py",
        "d313ad37d9836bd55d0e40026aca88445727b462f0e1b367781ffd4222114e31",
    ),
    (
        "tests/code_quality/test_performance_static_successor.py",
        "e9c05fedb6a5aa657955b76115685daeb734af3500d06ed1df2543547749f050",
    ),
    (
        "docs/CORE_RULES_REMEDIATION_ROADMAP.md",
        "59d0624883ffa435a267416718d508a30994b175b7bf239ddce2ec235b07f7c5",
    ),
)
CI_COMPAT_BEFORE: dict[str, str] = dict(_CI_COMPAT_BEFORE_ROWS)


CI_TRANSPORT_BASE = "599161cc0f76010c5ade3e257d6f700d72fc5c0b"
CI_TRANSPORT_RECORD = "docs/performance/ci-transport-successor49d.json"
_CI_TRANSPORT_BEFORE_ROWS = (
    (
        "tools/cumulative_preservation.py",
        "fd56f9037e9b5c1ae1466eed49195ee40be44ba32772a729c9ff724bc0c734e0",
    ),
)
CI_TRANSPORT_BEFORE: dict[str, str] = dict(_CI_TRANSPORT_BEFORE_ROWS)


CI_RUNTIME_BASE = "9746a372344322abd77a496d2b9621629b79e7be"
CI_RUNTIME_RECORD = "docs/performance/ci-runtime-successor51.json"
CI_RUNTIME_NEW = "tests/code_quality/test_ci_runtime_successor.py"
_CI_RUNTIME_BEFORE_ROWS = (
    (
        ".github/workflows/ci.yml",
        "60707f6e9ad8ad933297fdab2eab98b733f412680b78eb7c2a5253561df1679b",
    ),
    (
        "docs/CORE_RULES_REMEDIATION_ROADMAP.md",
        "fcde2b057946e9915403949209d2d39618aabdb09f8c3e5eafbc72c09d4ef061",
    ),
    (
        "tests/category_migration_preservation.py",
        "bb8fe47800cff5556d6b05d729224f3a4b22b099c8f07432012e6fa60e204519",
    ),
    (
        "tests/code_quality/test_category_migration_preservation.py",
        "341020dd1e9a8d6f64e5bfad83d444af19802b4a8eb04973755f75a2008c1fb5",
    ),
    (
        "tests/code_quality/test_ci_history_input.py",
        "fb94f5cef3b48fdafc4547f2a52493f315d2a8587a6cf83c6552861bac4e39bb",
    ),
    (
        "tests/code_quality/test_faction_content_runtime_structure.py",
        "9df6552a38bb198beab562cb1649e32ee14e9499e58cf0e44e5552b14f175577",
    ),
)
CI_RUNTIME_BEFORE: dict[str, str] = dict(_CI_RUNTIME_BEFORE_ROWS)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _git(root: Path, *args: str, payload: bytes | None = None) -> bytes:
    return subprocess.check_output(["git", *args], cwd=root, input=payload, timeout=60)


def _blobs(root: Path, revision: str, names: list[str]) -> dict[str, bytes]:
    """Read exact immutable members afresh; never cache Git or filesystem results."""
    if len(revision) != 40 or set(revision) - set("0123456789abcdef"):
        raise ValueError("Preflight Git revision must be an exact SHA1 selector.")
    if not names or len(set(names)) != len(names):
        raise ValueError("Preflight Git selection must contain unique members.")
    for name in names:
        if any(part in {"", ".", ".."} for part in name.split("/")) or any(
            character in name for character in "\\\x00\r\n"
        ):
            raise ValueError("Preflight Git member must be a canonical literal path.")
    tree = _git(root, "--literal-pathspecs", "ls-tree", "-r", "-z", revision, "--", *names)
    if not tree.endswith(b"\0"):
        raise ValueError("Preflight Git tree membership is incomplete.")
    objects: dict[str, str] = {}
    for row in tree[:-1].split(b"\0"):
        metadata, separator, encoded_name = row.partition(b"\t")
        fields = metadata.split(b" ")
        if not separator or len(fields) != 3:
            raise ValueError("Preflight Git tree row is malformed.")
        mode, kind, encoded_oid = fields
        name, oid = encoded_name.decode(), encoded_oid.decode("ascii")
        if (
            mode not in {b"100644", b"100755"}
            or kind != b"blob"
            or len(oid) != 40
            or set(oid) - set("0123456789abcdef")
            or name not in names
            or name in objects
        ):
            raise ValueError("Preflight Git member identity or type changed.")
        objects[name] = oid
    if objects.keys() != set(names):
        raise ValueError("Preflight Git tree membership is incomplete.")
    raw = _git(
        root,
        "cat-file",
        "--batch",
        payload="".join(objects[name] + "\n" for name in names).encode(),
    )
    result: dict[str, bytes] = {}
    offset = 0
    for name in names:
        boundary = raw.find(b"\n", offset)
        if boundary == -1:
            raise ValueError("Preflight Git blob header is incomplete.")
        fields = raw[offset:boundary].split(b" ")
        if len(fields) != 3:
            raise ValueError("Preflight Git blob header is malformed.")
        encoded_oid, kind, size = fields
        if encoded_oid != objects[name].encode() or kind != b"blob":
            raise ValueError("Preflight Git blob identity or type changed.")
        if not size.isdigit() or (len(size) > 1 and size.startswith(b"0")):
            raise ValueError("Preflight Git blob size is not canonical.")
        start = boundary + 1
        end = start + int(size)
        if end >= len(raw) or raw[end : end + 1] != b"\n":
            raise ValueError("Preflight Git blob payload is incomplete.")
        content = raw[start:end]
        object_hash = hashlib.sha1(b"blob " + size + b"\0", usedforsecurity=False)
        object_hash.update(content)
        if object_hash.hexdigest() != objects[name]:
            raise ValueError("Preflight Git blob bytes differ from the selected object.")
        result[name] = content
        offset = end + 1
    if offset != len(raw):
        raise ValueError("Preflight Git blob payload has trailing data.")
    return result


def read_frozen_blobs(root: Path, revision: str, names: list[str]) -> dict[str, bytes]:
    """Read a literal immutable group afresh with the complete existing Git checks."""
    return _blobs(root, revision, names)


def _read(root: Path, name: str) -> bytes:
    from tests.d07_geometry_containment import read_owned_geometry_member

    if root.absolute() != root.resolve(strict=True):
        raise ValueError("Aliased preflight successor root.")
    return read_owned_geometry_member(root, name)


def preceding_control(root: Path, name: str, raw: bytes) -> bytes:
    """Exact byte projection; the complete successor freeze is admitted separately."""
    if name not in PINS and name != ASSESSMENT:
        return raw
    actual = _read(root, name)
    if name == ASSESSMENT:
        _assessment(root, _freeze(root))
    elif _sha(actual) != PINS[name]:
        raise ValueError(
            "Reviewed migration source/data changed: "
            "Qualification / Perils successor / Preflight source: " + name
        )
    old = _git(root, "show", BASE + ":" + name)
    if raw not in (actual, old):
        raise ValueError("Preflight control caller supplied unrelated bytes.")
    return old


def assert_static_transition(name: str, before: bytes, current: bytes, row: dict[str, Any]) -> None:
    """Check one finite static edit against its independent immutable preimage."""
    from tools.cumulative_preservation import assert_recipe

    if (
        name not in STATIC_BEFORE
        or row.keys() != {"before_sha256", "after_sha256", "recipe"}
        or row["before_sha256"] != STATIC_BEFORE[name]
        or _sha(before) != STATIC_BEFORE[name]
        or row["after_sha256"] != _sha(current)
    ):
        raise ValueError("Static transition identity or bytes changed.")
    recipe: dict[str, Any] = row["recipe"]
    if (
        not isinstance(recipe, dict)
        or recipe.keys() != {"edits"}
        or not isinstance(recipe["edits"], list)
    ):
        raise ValueError("Static transition recipe is malformed.")
    for edit in cast(list[dict[str, Any]], recipe["edits"]):
        if not isinstance(edit, dict) or "kind" not in edit:
            raise ValueError("Static transition edit is malformed.")
        kind = edit.get("kind")
        keys = {"kind", "at", "before", "after"}
        if kind == "splice":
            keys |= {"start", "end"}
        if (
            kind not in {"replace", "splice"}
            or edit.keys() != keys
            or not isinstance(edit["at"], list)
            or not edit["at"]
            or any(type(part) not in {str, int} for part in edit["at"])
        ):
            raise ValueError("Static transition edit is malformed.")
        if kind == "splice" and (
            type(edit["start"]) is not int
            or type(edit["end"]) is not int
            or not 0 <= edit["start"] <= edit["end"]
            or not isinstance(edit["before"], list)
            or not isinstance(edit["after"], list)
        ):
            raise ValueError("Static transition splice is malformed.")
    assert_recipe(before, current, recipe)


def _static_transitions(root: Path, frozen_members: dict[str, bytes]) -> None:
    record: dict[str, Any] = json.loads(frozen_members[STATIC_RECORD])
    if (
        record.keys() != {"schema", "base", "changes"}
        or record["schema"] != "exact-static-successor-v1"
        or record["base"] != STATIC_BASE
        or record["changes"].keys() != STATIC_BEFORE.keys()
    ):
        raise ValueError("Static transition membership or base changed.")
    previous = _blobs(root, STATIC_BASE, list(STATIC_BEFORE))
    for name in STATIC_BEFORE:
        assert_static_transition(
            name, previous[name], frozen_members[name], record["changes"][name]
        )


def assert_ci_transition(
    name: str, before: bytes | None, current: bytes, row: dict[str, Any]
) -> None:
    """Admit only the frozen CI import/bootstrap edits and exact map additions."""
    allowed = CI_BEFORE | CI_FORMAT_BEFORE
    if name not in allowed and name != CI_NEW:
        raise ValueError("CI transition identity or bytes changed.")
    _assert_ci_edits(before, current, row, allowed.get(name), name == CI_NEW)


def assert_ci_compatibility_transition(
    name: str, before: bytes, current: bytes, row: dict[str, Any]
) -> None:
    """Validate only this finite historical-consumer repair against immutable 856."""
    if name not in CI_COMPAT_BEFORE:
        raise ValueError("CI transition identity or bytes changed.")
    _assert_ci_edits(before, current, row, CI_COMPAT_BEFORE[name], False)


def assert_ci_transport_transition(
    name: str, before: bytes, current: bytes, row: dict[str, Any]
) -> None:
    """Admit only the exact immutable integration-member transport repair."""
    if name not in CI_TRANSPORT_BEFORE:
        raise ValueError("CI transition identity or bytes changed.")
    _assert_ci_edits(before, current, row, CI_TRANSPORT_BEFORE[name], False)


def assert_ci_runtime_transition(
    name: str, before: bytes | None, current: bytes, row: dict[str, Any]
) -> None:
    """Admit only the measured, finite quality-runtime edits against immutable CI50."""
    if name not in CI_RUNTIME_BEFORE and name != CI_RUNTIME_NEW:
        raise ValueError("CI transition identity or bytes changed.")
    _assert_ci_edits(before, current, row, CI_RUNTIME_BEFORE.get(name), name == CI_RUNTIME_NEW)


def _runtime_transitions(root: Path, frozen_members: dict[str, bytes]) -> dict[str, bytes]:
    record: dict[str, Any] = json.loads(frozen_members[CI_RUNTIME_RECORD])
    if (
        record.keys() != {"schema", "base", "changes"}
        or record["schema"] != "exact-ci-successor-v1"
        or record["base"] != CI_RUNTIME_BASE
        or record["changes"].keys() != CI_RUNTIME_BEFORE.keys() | {CI_RUNTIME_NEW}
    ):
        raise ValueError("CI runtime membership or base changed.")
    previous = _blobs(root, CI_RUNTIME_BASE, list(CI_RUNTIME_BEFORE))
    if _git(
        root, "--literal-pathspecs", "ls-tree", "-r", "-z", CI_RUNTIME_BASE, "--", CI_RUNTIME_NEW
    ):
        raise ValueError("CI runtime guard predecessor was not absent.")
    for name in record["changes"]:
        assert_ci_runtime_transition(
            name, previous.get(name), frozen_members[name], record["changes"][name]
        )
    return frozen_members | previous


def _assert_ci_edits(
    before: bytes | None,
    current: bytes,
    row: dict[str, Any],
    expected: str | None,
    added: bool,
) -> None:
    if (
        row.keys() != {"before_sha256", "after_sha256", "edits"}
        or row["before_sha256"] != expected
        or (before is None) != added
        or (before is not None and _sha(before) != expected)
        or row["after_sha256"] != _sha(current)
        or not isinstance(row["edits"], list)
        or not row["edits"]
    ):
        raise ValueError("CI transition identity or bytes changed.")
    projected = b"" if before is None else before
    for edit in cast(list[dict[str, Any]], row["edits"]):
        if (
            not isinstance(edit, dict)
            or edit.keys() != {"before", "after"}
            or not isinstance(edit["before"], str)
            or not isinstance(edit["after"], str)
        ):
            raise ValueError("CI transition edit is malformed.")
        old, new = edit["before"].encode(), edit["after"].encode()
        if projected.count(old) != 1:
            raise ValueError("CI transition edit does not have one exact occurrence.")
        projected = projected.replace(old, new, 1)
    if projected != current:
        raise ValueError("CI transition changed outside the exact reviewed edits.")


def _ci_transitions(root: Path, frozen_members: dict[str, bytes]) -> dict[str, bytes]:
    comparison = _runtime_transitions(root, frozen_members)
    transport: dict[str, Any] = json.loads(frozen_members[CI_TRANSPORT_RECORD])
    if (
        transport.keys() != {"schema", "base", "changes"}
        or transport["schema"] != "exact-ci-successor-v1"
        or transport["base"] != CI_TRANSPORT_BASE
        or transport["changes"].keys() != CI_TRANSPORT_BEFORE.keys()
    ):
        raise ValueError("CI transport membership or base changed.")
    previous = _blobs(root, CI_TRANSPORT_BASE, list(CI_TRANSPORT_BEFORE))
    for name in CI_TRANSPORT_BEFORE:
        assert_ci_transport_transition(
            name, previous[name], comparison[name], transport["changes"][name]
        )
    comparison |= previous
    record: dict[str, Any] = json.loads(frozen_members[CI_COMPAT_RECORD])
    if (
        record.keys() != {"schema", "base", "changes"}
        or record["schema"] != "exact-ci-successor-v1"
        or record["base"] != CI_COMPAT_BASE
        or record["changes"].keys() != CI_COMPAT_BEFORE.keys()
    ):
        raise ValueError("CI compatibility membership or base changed.")
    previous = _blobs(root, CI_COMPAT_BASE, list(CI_COMPAT_BEFORE))
    for name in CI_COMPAT_BEFORE:
        assert_ci_compatibility_transition(
            name, previous[name], comparison[name], record["changes"][name]
        )
    # Current bytes have already passed their immutable freeze and physical reads.
    # Only this finite comparison view feeds the unchanged earlier recipes.
    comparison |= previous
    specifications: tuple[tuple[str, str, dict[str, str], set[str]], ...] = (
        (CI_BASE, CI_RECORD, CI_BEFORE, {CI_NEW}),
        (CI_FORMAT_BASE, CI_FORMAT_RECORD, CI_FORMAT_BEFORE, set()),
    )
    for base, record_path, pins, added in specifications:
        record = json.loads(frozen_members[record_path])
        if (
            record.keys() != {"schema", "base", "changes"}
            or record["schema"] != "exact-ci-successor-v1"
            or record["base"] != base
            or record["changes"].keys() != pins.keys() | added
        ):
            raise ValueError("CI transition membership or base changed.")
        for name in added:
            if _git(root, "--literal-pathspecs", "ls-tree", "-r", "-z", base, "--", name):
                raise ValueError("CI bootstrap predecessor was not absent.")
        previous = _blobs(root, base, list(pins))
        for name in record["changes"]:
            assert_ci_transition(
                name, previous.get(name), comparison[name], record["changes"][name]
            )
    return comparison


def ci_comparison(root: Path, name: str, raw: bytes) -> bytes:
    """Authenticate a finite later edit before its unchanged earlier recipe."""
    if (
        name not in CI_COMPAT_BEFORE
        and name not in CI_TRANSPORT_BEFORE
        and name not in CI_RUNTIME_BEFORE
    ):
        return raw
    _freeze(root)
    if raw != _read(root, name):
        raise ValueError("Static comparison caller supplied unrelated bytes.")
    if name in CI_COMPAT_BEFORE:
        base, pin = CI_COMPAT_BASE, CI_COMPAT_BEFORE[name]
    elif name in CI_TRANSPORT_BEFORE:
        base, pin = CI_TRANSPORT_BASE, CI_TRANSPORT_BEFORE[name]
    else:
        base, pin = CI_RUNTIME_BASE, CI_RUNTIME_BEFORE[name]
    before = _git(root, "show", base + ":" + name)
    if _sha(before) != pin:
        raise ValueError("Static comparison immutable bytes changed.")
    return before


def static_predecessor(root: Path, name: str, raw: bytes) -> bytes:
    """Expose only the reviewed Order34 annotation and exact quality bootstrap history."""
    if name not in {STATIC_TEST, QUALITY_BOOTSTRAP}:
        return raw
    _freeze(root)
    live = _read(root, name)
    if raw not in (live, live.replace(b"\r\n", b"\n")):
        raise ValueError("Static predecessor caller supplied unrelated bytes.")
    base = STATIC_BASE if name == STATIC_TEST else CI_COMPAT_BASE
    pin = STATIC_BEFORE[name] if name == STATIC_TEST else CI_COMPAT_BEFORE[name]
    before = _git(root, "show", base + ":" + name)
    if _sha(before) != pin:
        raise ValueError("Static predecessor immutable bytes changed.")
    return before.replace(b"\r\n", b"\n") if raw != live else before


def _freeze(root: Path) -> str:
    freeze = FREEZE_COMMIT
    if freeze is None or len(freeze) != 40 or set(freeze) - set("0123456789abcdef"):
        raise ValueError("Preflight successor awaits its exact source freeze.")
    _git(root, "merge-base", "--is-ancestor", BASE, freeze)
    _git(root, "merge-base", "--is-ancestor", freeze, "HEAD")
    _git(root, "merge-base", "--is-ancestor", STATIC_BASE, freeze)
    _git(root, "merge-base", "--is-ancestor", CI_BASE, freeze)
    _git(root, "merge-base", "--is-ancestor", CI_FORMAT_BASE, freeze)
    _git(root, "merge-base", "--is-ancestor", CI_COMPAT_BASE, freeze)
    _git(root, "merge-base", "--is-ancestor", CI_TRANSPORT_BASE, freeze)
    _git(root, "merge-base", "--is-ancestor", CI_RUNTIME_BASE, freeze)
    names = _git(root, "diff", "--name-only", BASE, freeze).decode().splitlines()
    if set(names) != PINS.keys() | {SELF, ASSESSMENT} or len(names) != len(PINS) + 2:
        raise ValueError("Preflight successor finite membership changed.")
    frozen_members = _blobs(root, freeze, [SELF, *PINS, *ANCHORS])
    frozen = frozen_members[SELF]
    marker = b"\nFREEZE_COMMIT: str | None = None"
    if frozen.count(marker) != 1 or _read(root, SELF) != frozen.replace(
        marker, f'\nFREEZE_COMMIT: str | None = "{freeze}"'.encode(), 1
    ):
        raise ValueError("Preflight successor activation changed.")
    for name, pin in PINS.items():
        if _sha(_read(root, name)) != pin or _sha(frozen_members[name]) != pin:
            raise ValueError(
                "Reviewed migration source/data changed: "
                "Qualification / Perils successor / Preflight source: " + name
            )
    anchor_before = _blobs(root, BASE, list(ANCHORS))
    for name, pin in ANCHORS.items():
        if (
            _sha(anchor_before[name]) != pin
            or _read(root, name) != anchor_before[name]
            or frozen_members[name] != anchor_before[name]
        ):
            raise ValueError("Preflight unchanged owned anchor changed: " + name)
    comparison = _ci_transitions(root, frozen_members)
    _static_transitions(root, comparison)
    return freeze


def _assessment(root: Path, freeze: str) -> bytes:
    from tools.performance_policy import owner_hashes

    assessment = json.loads(_git(root, "show", freeze + ":" + ASSESSMENT))
    current = _read(root, SELF)
    change = assessment["changes"][SELF]
    change["after_sha256"] = _sha(current)
    change["owners"]["@module"]["after"] = owner_hashes(SELF, current)["@module"]
    raw_assessment = _read(root, ASSESSMENT)
    if json.loads(raw_assessment) != assessment:
        raise ValueError("Preflight assessment changed outside exact anchor derivation.")
    return raw_assessment


def current_source(root: Path, previous: dict[str, str]) -> dict[str, str]:
    if _sha(json.dumps(previous, sort_keys=True, separators=(",", ":")).encode()) != BASE_SOURCE:
        raise ValueError("Preflight successor preceding complete source changed.")
    freeze = _freeze(root)
    return (
        previous
        | PINS
        | {SELF: _sha(_read(root, SELF)), ASSESSMENT: _sha(_assessment(root, freeze))}
    )


def measurement_inputs(root: Path, current: dict[str, str]) -> dict[str, str]:
    """Expose exact historical comparison inputs after current-source admission.

    The finite static recipes also admit the Command-end fixture's explicit
    export list; its functions, source-ID import and initializers remain exact.
    This is a changed recorded fixture input, not a byte-identical measurement.
    The CI successor also changes package bootstrap to prevent generated bytecode
    and imports the same generator function from its canonical owner. Its three
    exact module mappings add no detailed families or altered workload semantics.
    Exact later import-block edits retain all benchmark functions and constants;
    reordered imports have separate current entry-point controls.
    Current collectors and a fresh smoke receipt still bind the actual source.
    """
    from tools import thousand_sons_perils_preservation as perils

    _freeze(root)
    # The audit, proof records and CI workflow are outside runtime_inputs; their
    # bytes remain authenticated by _freeze and the complete live source scan.
    controls = (
        (
            PINS.keys()
            - {
                INVENTORY,
                STATIC_RECORD,
                CI_RECORD,
                CI_FORMAT_RECORD,
                CI_COMPAT_RECORD,
                CI_TRANSPORT_RECORD,
                CI_RUNTIME_RECORD,
                CI_ROADMAP,
                CI_WORKFLOW,
            }
        )
        | ANCHORS.keys()
        | {SELF}
    )
    if not controls <= current.keys():
        raise ValueError("Preflight actual input collector omitted current inputs.")
    actual = {name: _sha(_read(root, name)) for name in controls}
    projected = dict(current)
    prior_names = set(_git(root, "ls-tree", "-r", "--name-only", BASE).decode().splitlines())
    for name in controls:
        if name not in current:
            continue
        if current[name] != actual[name]:
            raise ValueError("Preflight actual input collector omitted current control bytes.")
        if name in prior_names:
            projected[name] = _sha(_git(root, "show", BASE + ":" + name))
        else:
            del projected[name]
    # These five exact paths are already authenticated by the native Perils
    # admission. Its added test is not a measured driver or imported fixture.
    perils._freeze(root)
    for name in perils.CHANGED:
        raw = _git(root, "show", BASE + ":" + name)
        if projected.get(name) != _sha(raw):
            raise ValueError("Preflight Perils producing projection changed.")
        if name in {perils.SELF, perils.GUARD}:
            del projected[name]
        elif name == perils.TEST:
            projected[name] = _sha(perils.preceding_test(root, name, _read(root, name)))
        else:
            projected[name] = _sha(perils.preceding_control(root, name, _read(root, name)))
    return projected
