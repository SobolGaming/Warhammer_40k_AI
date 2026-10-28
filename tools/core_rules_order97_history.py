"""Bounded historical Order 97 inputs, never new live semantic evidence."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

MAPPING = "data/source_audits/v963_shock/historical-inputs.json"
MAPPING_SHA256 = "51689e786d64ca281d7513bdd4e6b968aed65eeefd73a6dad1bb591d05de29b7"

ORDER102_MAPPING = "data/source_audits/order102/historical-inputs.json"
ORDER102_MAPPING_SHA256 = "c8e782fcab38c6944174b981cf8ebc9d37e2d4e8f073b3ed722ba759f8d54362"


ORDER103_MAPPING = "data/source_audits/order103/historical-inputs.json"
ORDER103_MAPPING_SHA256 = "af890dd01ff20bfafd61db06b3e6f5a546a97fc55dd06985be79b3c8a794b6df"


ISSUE535_MAPPING = "data/source_audits/issue535/historical-inputs.json"
ISSUE535_MAPPING_SHA256 = "5c0f44902158da51de3279bc7d44c9e2a13a2f4c2d3ce1c67d02925e3e851c95"


ISSUE534_MAPPING = "data/source_audits/issue534/historical-inputs.json"
ISSUE534_MAPPING_SHA256 = "49d81bcbb38b6b29ad24a4ab24742854b987fca858070e82dcd7cc0f5e87a45f"


ORDER104_MAPPING = "data/source_audits/order104/historical-inputs.json"
ORDER104_MAPPING_SHA256 = "229bf8b5f6803dc7857ed44fc3cf997cf944ab5c8d900234dd7b8dd0d4df6263"


ORDER107_MAPPING = "data/source_audits/order107/historical-inputs.json"
ORDER107_MAPPING_SHA256 = "abff3f6516cd2489ed63009bf2253d8a06a7487b1501343cb650e626c423baec"

ORDER108_MAPPING = "data/source_audits/order108/historical-inputs.json"
ORDER108_MAPPING_SHA256 = "36849bc5a2a436eee161e961f16e8445612bccfef82f46a99be4548c5f528606"


ORDER110_MAPPING = "data/source_audits/order110/historical-inputs.json"
ORDER110_MAPPING_SHA256 = "98057295d7c92a1f19b76befb40679f214731417315a205cb4985d990cc7e77f"


ORDER112_MAPPING = "data/source_audits/order112/historical-inputs.json"
ORDER112_MAPPING_SHA256 = "f409d4e5acf6d391ee4bb38df985ba6992806a7032b66dafeb5ae325777e6259"


ORDER113_MAPPING = "data/source_audits/order113/historical-inputs.json"
ORDER113_MAPPING_SHA256 = "c594f1e301bc4203505ab9785b21d549aa4867745e3477a4aa11f35509e54129"


ORDER114_MAPPING = "data/source_audits/order114/historical-inputs.json"
ORDER114_MAPPING_SHA256 = "4c38d99defecfc2cc4758eff7c0cae877ee726b70a0fbf6921472c2f7b65113e"


V963_SNAP_MAPPING = "data/source_audits/v963_snap/historical-inputs.json"
V963_SNAP_MAPPING_SHA256 = "aed57834c1788dd3bce03ef27338c9896e6ed642bbec335a24e40c602de52e78"


ORDER117_MAPPING = "data/source_audits/order117/historical-inputs.json"
ORDER117_MAPPING_SHA256 = "5e95332bb27eb2ce984013ac4c796da5ac91413dc7fe6f9d94975c75db5225fc"

ORDER118_MAPPING = "data/source_audits/order118/historical-inputs.json"
ORDER118_MAPPING_SHA256 = "f57a5b49be9a7d17e51768636cd5a5e1d2f7138af355da274ceec625e3d6ea07"


ORDER119_MAPPING = "data/source_audits/order119/historical-inputs.json"
ORDER119_MAPPING_SHA256 = "7a4f2b4a274e8973e2f924a3ec1ea03bfcead9240218f0313c5299f4798184a4"


ORDER121_MAPPING = "data/source_audits/order121/historical-inputs.json"
ORDER121_MAPPING_SHA256 = "11c76db17f02f733159a3545e437d86f8839a7969567db41d739c9d968c1cc00"


ORDER122_MAPPING = "data/source_audits/order122/historical-inputs.json"
ORDER122_MAPPING_SHA256 = "4927ddb34e5697e93975fb0da8b977d2615649a2a5408a7d91ce9a227907f8a8"


ORDER123_MAPPING = "data/source_audits/order123/historical-inputs.json"
ORDER123_MAPPING_SHA256 = "b7b6bf8e1a44454e31da5f08b7431ab05ee706448e16edd25aff2d8176ffb6f6"


ORDER126_MAPPING = "data/source_audits/order126/historical-inputs.json"
ORDER126_MAPPING_SHA256 = "4664ea3c444ce541d57e7c066dfa8a41a21890d65cddbc774bb39f4ad581a7a5"


ORDER135_MAPPING = "data/source_audits/order135/historical-inputs.json"
ORDER135_MAPPING_SHA256 = "5e6088ea869552c2e508fa676842b40ada02cf3c8de07f30732f34e3471a46f9"

ORDER135_D02_MAPPING = "data/source_audits/order135/d02-historical-inputs.json"
ORDER135_D02_MAPPING_SHA256 = "f44d9c658e2ef3980ecd9cd9bbdbfd9fa7c51ad9863d36b9d5ba026bc1027a02"


ORDER135_FINAL_FIXTURE_MAPPING = "data/source_audits/order135/final-fixture-historical-inputs.json"
ORDER135_FINAL_FIXTURE_MAPPING_SHA256 = (
    "e0fea4bc8a7e84071b5ded77f25710234a1e3d87711ea64e8556de98efbc3942"
)


ORDER135_FINAL_QUALITY_MAPPING = "data/source_audits/order135/final-quality-historical-inputs.json"
ORDER135_FINAL_QUALITY_MAPPING_SHA256 = (
    "5a531ffd9a716f83aacdf090079c2e8a593e7bcad168247cce6cf6d483ad7c34"
)


PHYSICAL_HISTORY_RESTORE_MAPPING = (
    "data/source_audits/physical-history-restore/historical-inputs.json"
)
PHYSICAL_HISTORY_RESTORE_MAPPING_SHA256 = (
    "c9c4030a4b06bf684600ddb1741ca769da40cf29bc90196ee40e3d0fe09f60f2"
)


ORDER135_D07_MAPPING = "data/source_audits/order135/d07-historical-inputs.json"
ORDER135_D07_MAPPING_SHA256 = "347097fb7a159d7e640014e00e309621c56b013a74028df2cdf02b2068469c7e"


INTEGRATION_INVENTORY_PREIMAGES: dict[str, tuple[str, str, str]] = {
    "tests/unit/test_order60_emergency_disembark.py": (
        "data/source_audits/integration_2026_10_19/order97/tests/unit/test_order60_emergency_disembark.py.before.py.txt",
        "c69fe087121a994906469306df957c6846b193e590a2aed51faafb12d13b7548",
        "9fbf5fdc576a4fed4bbe5d36de1309b4ecae9fb30498cff1cd81a5b7cc968449",
    ),
    "tests/unit/test_phase11b_objective_control.py": (
        "data/source_audits/integration_2026_10_19/order97/tests/unit/test_phase11b_objective_control.py.before.py.txt",
        "021ae6324df6db332fe417a141ce21c90836d2c618ed72b4a738a8c2d3c1b568",
        "cef54e6222976e0336827a41dbf9b91b75a6e33ebbcb5902aa92741099c53c28",
    ),
}


REVIEWED_INVENTORY_FIXTURES: dict[str, tuple[str, str, str, str]] = {
    "tests/conftest.py": (
        "data/source_audits/integration_2026_10_19/order97-fixtures/tests/conftest.py.before.py.txt",
        "db7fe5a9246d0aa44cc115b59840781806bdd5228b115bbd9dce8309d28292b7",
        "data/source_audits/integration_2026_10_19/order97-fixtures/tests/conftest.py.reviewed.py.txt",
        "3785219e822d61ca902a568cb792f0a227685bc27c2d6509cec89ef4cf64180b",
    ),
    "tests/indirect_shooting_helpers.py": (
        "data/source_audits/integration_2026_10_19/order97-fixtures/tests/indirect_shooting_helpers.py.before.py.txt",
        "14f45bb1315eaa7a17156e70a1ee77b717af3a7ed4b7f6fd772849bc850feaa9",
        "data/source_audits/integration_2026_10_19/order97-fixtures/tests/indirect_shooting_helpers.py.reviewed.py.txt",
        "dbca147e17f121e989e9e558326aec85e7e550a3822a80efe8919dcf1c6bbf1b",
    ),
    "tests/psychic_modifier_helpers.py": (
        "data/source_audits/integration_2026_10_19/order97-fixtures/tests/psychic_modifier_helpers.py.before.py.txt",
        "250e1f8a846662a937b7c0b7e3862788e6591e88a2e2b520332cc1526ec7da54",
        "data/source_audits/integration_2026_10_19/order97-fixtures/tests/psychic_modifier_helpers.py.reviewed.py.txt",
        "d387946cc6731484807c410f8e452dd4cb23e1f24ffaa98b89a95ecd4e4a3f93",
    ),
    "tests/support/ability_presence_fixtures.py": (
        "data/source_audits/integration_2026_10_19/order97-fixtures/tests/support/ability_presence_fixtures.py.before.py.txt",
        "d7d01d57258bab1c80c4c8c9d8030534c6a9cf2b440ccb25c9756b9690adf902",
        "data/source_audits/integration_2026_10_19/order97-fixtures/tests/support/ability_presence_fixtures.py.reviewed.py.txt",
        "7cabadf4c1e596682b4809628e42e7b7f40a714a3e79f4cb70da83f168971f4f",
    ),
    "tests/unit/test_phase12a_timing_reactions_effects.py": (
        "data/source_audits/integration_2026_10_19/order97-fixtures/tests/unit/test_phase12a_timing_reactions_effects.py.before.py.txt",
        "06cd0c34b4495f6a17077aa58c7440bb0e35d5319386f802b0a54d294a66184d",
        "data/source_audits/integration_2026_10_19/order97-fixtures/tests/unit/test_phase12a_timing_reactions_effects.py.reviewed.py.txt",
        "8a0291e4732431622461e0dbfba79d3d748a0e57a9d9db3d7109e634aeccfc1a",
    ),
}


def assert_reviewed_inventory_fixture_ast(accepted: bytes, current: bytes) -> None:
    if ast.dump(ast.parse(accepted)) != ast.dump(ast.parse(current)):
        raise ValueError("Reviewed inventory fixture AST drifted.")


def reviewed_inventory_fixture_history(reference: str, *, root: Path) -> Path | None:
    if reference not in REVIEWED_INVENTORY_FIXTURES:
        return None
    archive, old_hash, accepted_archive, accepted_hash = REVIEWED_INVENTORY_FIXTURES[reference]
    path = root / archive
    reviewed = root / accepted_archive
    if not path.resolve().is_relative_to(root.resolve()) or not reviewed.resolve().is_relative_to(
        root.resolve()
    ):
        raise ValueError("Reviewed inventory fixture history escaped the repository.")
    before = path.read_bytes()
    accepted = reviewed.read_bytes()
    from tools.performance_ci69_members import retired_test_source

    retired = retired_test_source(root, reference)
    current = retired[1] if retired is not None else (root / reference).read_bytes()
    if (
        hashlib.sha256(before).hexdigest() != old_hash
        or hashlib.sha256(accepted).hexdigest() != accepted_hash
        or hashlib.sha256(current).hexdigest() != accepted_hash
    ):
        raise ValueError("Exact reviewed inventory fixture bytes drifted.")
    assert_reviewed_inventory_fixture_ast(accepted, current)
    return path


def integration_inventory_history(reference: str, *, root: Path) -> Path | None:
    if reference not in INTEGRATION_INVENTORY_PREIMAGES:
        return reviewed_inventory_fixture_history(reference, root=root)
    archive, before_sha256, current_sha256 = INTEGRATION_INVENTORY_PREIMAGES[reference]
    path = root / archive
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Integration inventory history escaped the repository.")
    before = path.read_bytes()
    from tools.performance_ci69_members import retired_test_source

    retired = retired_test_source(root, reference)
    current = retired[1] if retired is not None else (root / reference).read_bytes()
    if (
        hashlib.sha256(before).hexdigest() != before_sha256
        or hashlib.sha256(current).hexdigest() != current_sha256
    ):
        raise ValueError("Exact integration inventory input bytes drifted.")
    assert_integration_inventory_ast(reference, before, current)
    return path


def assert_integration_inventory_ast(reference: str, before: bytes, current: bytes) -> None:
    """Authenticate current source changes before exposing reviewed history."""
    expected, actual = ast.parse(before), ast.parse(current)

    def function(name: str) -> ast.FunctionDef:
        values = [n for n in expected.body if isinstance(n, ast.FunctionDef) and n.name == name]
        if len(values) != 1:
            raise ValueError("Integration inventory function membership drifted.")
        return values[0]

    if reference == "tests/unit/test_order60_emergency_disembark.py":
        owner = function("test_emergency_disembark_places_every_survivor_on_the_closest_ring")
        values = [
            n for n in ast.walk(owner) if isinstance(n, ast.Constant) and n.value == "end_of_turn"
        ]
        if len(values) != 1:
            raise ValueError("Original Emergency Battle-shock expectation drifted.")
        values[0].value = "until_cleared"
    elif reference == "tests/unit/test_phase11b_objective_control.py":
        owner = function("test_objective_control_records_update_at_phase_and_turn_end")
        calls = [
            n
            for n in ast.walk(owner)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "_battle_state_with_center_objective_positions"
        ]
        if len(calls) != 1 or len(calls[0].keywords) != 1:
            raise ValueError("Objective physical fixture preimage drifted.")
        keyword = calls[0].keywords[0]
        if keyword.arg != "player_a_offsets" or ast.dump(keyword.value) != ast.dump(
            ast.parse("((2.0, 0.0),)", mode="eval").body
        ):
            raise ValueError("Objective physical fixture position drifted.")
        keyword.value = ast.parse(
            "((2.0, 0.0), (3.4, 0.0), (4.8, 0.0), (2.0, 1.4), (3.4, 1.4))",
            mode="eval",
        ).body
        owner = function("test_p14_objective_query_uses_closest_vertical_part")
        arguments = [n for n in owner.args.args if n.arg == "expected"]
        if len(arguments) != 1:
            raise ValueError("Objective marker parameter preimage drifted.")
        arguments[0].arg = "marker_expected"
        values = [
            n
            for d in owner.decorator_list
            for n in ast.walk(d)
            if isinstance(n, ast.Constant) and n.value == "expected"
        ]
        if len(values) != 1:
            raise ValueError("Objective marker decorator preimage drifted.")
        values[0].value = "marker_expected"
        loops = [n for n in owner.body if isinstance(n, ast.For)]
        if len(loops) != 1 or not isinstance(loops[0].iter, ast.Tuple):
            raise ValueError("Objective kind fixture preimage drifted.")
        loop = loops[0]
        sequence = loop.iter
        if not isinstance(sequence, ast.Tuple):
            raise ValueError("Objective kind tuple drifted.")
        if len(sequence.elts) != 2 or not isinstance(loop.target, ast.Name):
            raise ValueError("Objective kind membership drifted.")
        marker, terrain = sequence.elts
        loop.target = ast.Tuple(
            elts=[
                ast.Name(id="objective", ctx=ast.Store()),
                ast.Name(id="expected", ctx=ast.Store()),
            ],
            ctx=ast.Store(),
        )
        loop.iter = ast.Tuple(
            elts=[
                ast.Tuple(
                    elts=[marker, ast.Name(id="marker_expected", ctx=ast.Load())], ctx=ast.Load()
                ),
                ast.Tuple(elts=[terrain, ast.Constant(value=True)], ctx=ast.Load()),
            ],
            ctx=ast.Load(),
        )
        owner = function(
            "test_p14_objective_query_rejects_missing_shape_and_drifted_marker_identity"
        )
        calls = [
            n
            for n in ast.walk(owner)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "ObjectiveModelDistance"
        ]
        if len(calls) != 1 or any(k.arg == "closest_distance_inches" for k in calls[0].keywords):
            raise ValueError("Objective invalid-distance fixture preimage drifted.")
        calls[0].keywords.append(ast.keyword(arg="closest_distance_inches", value=ast.Constant(0)))
    else:
        raise ValueError("Unknown integration inventory predecessor.")
    if ast.dump(expected) != ast.dump(actual):
        raise ValueError("Integration inventory whole-module AST drifted.")


def historical_evidence_path(reference: str, *, root: Path) -> Path | None:
    """Resolve only the reviewed mapping; missing or corrupt history never falls back."""
    for mapping_name, expected_sha256 in (
        (MAPPING, MAPPING_SHA256),
        (ORDER102_MAPPING, ORDER102_MAPPING_SHA256),
        (ORDER103_MAPPING, ORDER103_MAPPING_SHA256),
        (ISSUE535_MAPPING, ISSUE535_MAPPING_SHA256),
        (ISSUE534_MAPPING, ISSUE534_MAPPING_SHA256),
        (ORDER104_MAPPING, ORDER104_MAPPING_SHA256),
        (ORDER107_MAPPING, ORDER107_MAPPING_SHA256),
        (ORDER108_MAPPING, ORDER108_MAPPING_SHA256),
        (ORDER110_MAPPING, ORDER110_MAPPING_SHA256),
        (ORDER112_MAPPING, ORDER112_MAPPING_SHA256),
        (ORDER113_MAPPING, ORDER113_MAPPING_SHA256),
        (ORDER114_MAPPING, ORDER114_MAPPING_SHA256),
        (V963_SNAP_MAPPING, V963_SNAP_MAPPING_SHA256),
        (ORDER117_MAPPING, ORDER117_MAPPING_SHA256),
        (ORDER118_MAPPING, ORDER118_MAPPING_SHA256),
        (ORDER119_MAPPING, ORDER119_MAPPING_SHA256),
        (ORDER121_MAPPING, ORDER121_MAPPING_SHA256),
        (ORDER122_MAPPING, ORDER122_MAPPING_SHA256),
        (ORDER123_MAPPING, ORDER123_MAPPING_SHA256),
        (ORDER126_MAPPING, ORDER126_MAPPING_SHA256),
        (ORDER135_MAPPING, ORDER135_MAPPING_SHA256),
        (ORDER135_D02_MAPPING, ORDER135_D02_MAPPING_SHA256),
        (ORDER135_FINAL_FIXTURE_MAPPING, ORDER135_FINAL_FIXTURE_MAPPING_SHA256),
        (ORDER135_FINAL_QUALITY_MAPPING, ORDER135_FINAL_QUALITY_MAPPING_SHA256),
        (PHYSICAL_HISTORY_RESTORE_MAPPING, PHYSICAL_HISTORY_RESTORE_MAPPING_SHA256),
        (ORDER135_D07_MAPPING, ORDER135_D07_MAPPING_SHA256),
    ):
        raw = (root / mapping_name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise ValueError("Order 97 historical-input mapping drifted.")
        mapping = json.loads(raw)
        for item in mapping["files"]:
            if item["path"] != reference:
                continue
            path = root / str(item["historical_path"])
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError("Order 97 historical evidence escaped the repository.")
            retained = path.read_bytes()
            if (
                len(retained) != item["bytes"]
                or hashlib.sha256(retained).hexdigest() != item["sha256"]
            ):
                raise ValueError("Order 97 immutable historical input drifted.")
            return path
    return integration_inventory_history(reference, root=root)
